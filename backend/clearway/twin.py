"""The digital twin: a 2D top-down occupancy grid of a home, in centimetres.

A twin is a set of blocked cells on a fixed-resolution grid plus the trip the chair
must make (start -> goal). Everything downstream (the planner, the rule engine, the
auditor) reads measurements off this grid, never off an LLM.
"""
from dataclasses import dataclass, field
from typing import FrozenSet, Tuple

CELL_CM = 5  # grid resolution; 5 cm is fine for doorway/turning decisions


@dataclass(frozen=True)
class Twin:
    blocked: FrozenSet[Tuple[int, int]]
    W: int
    H: int
    start: Tuple[int, int, int]      # (x, y, heading) heading 0=+x,1=+y,2=-x,3=-y
    goal: Tuple[int, int]            # (x, y)
    door_cm: int                     # the clear width of the doorway on the route
    wall_cols: Tuple[int, ...] = ()  # x-columns of the interior wall (to measure the gap)
    cell_cm: int = CELL_CM


def two_room_template(door_cm: int) -> Twin:
    """Two 300x300 cm rooms separated by a 10 cm wall with a single doorway.

    The chair starts in the centre of the left room and must reach the centre of the
    right room. Only the door's clear width varies, so the planner's verdict isolates
    the doorway as the cause.
    """
    room = 300 // CELL_CM          # 60 cells per room side
    wall_thick = 10 // CELL_CM     # 2 cells
    W = 1 + room + wall_thick + room + 1   # border + roomA + wall + roomB + border
    H = 1 + room + 1
    mid = H // 2

    blocked = set()
    # outer border
    for x in range(W):
        blocked.add((x, 0)); blocked.add((x, H - 1))
    for y in range(H):
        blocked.add((0, y)); blocked.add((W - 1, y))

    wall_cols = tuple(1 + room + i for i in range(wall_thick))  # e.g. (61, 62)
    gap_cells = round(door_cm / CELL_CM)
    gap_lo = mid - gap_cells // 2
    gap_hi = gap_lo + gap_cells
    for cx in wall_cols:
        for y in range(1, H - 1):
            if not (gap_lo <= y < gap_hi):
                blocked.add((cx, y))

    start = (1 + room // 2, mid, 0)                     # centre of left room, facing +x
    goal = (wall_cols[-1] + 1 + room // 2, mid)         # centre of right room
    return Twin(
        blocked=frozenset(blocked), W=W, H=H, start=start, goal=goal,
        door_cm=door_cm, wall_cols=wall_cols,
    )


def max_free_run(twin: Twin, col: int) -> int:
    """Longest vertical run of free cells in a wall column — the real clear opening."""
    best = run = 0
    for y in range(twin.H):
        if (col, y) in twin.blocked:
            run = 0
        else:
            run += 1
            best = max(best, run)
    return best
