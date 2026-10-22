"""The digital twin: a 2D top-down occupancy grid of a home, in centimetres.

A twin is a set of blocked cells on a fixed-resolution grid plus the trip the chair
must make (start -> goal). Everything downstream (the planner, the rule engine, the
auditor) reads measurements off this grid, never off an LLM.
"""
from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Tuple

from .rules import DoorSpec, RouteSpec

CELL_CM = 5  # grid resolution; 5 cm is fine for doorway/turning decisions


def _cells(cm: int) -> int:
    """Round DOWN: a twin never gives the chair more room than the spec claims."""
    return max(1, cm // CELL_CM)


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
    thresholds: FrozenSet[Tuple[int, int]] = frozenset()  # doorway cells carrying a step
    threshold_mm: int = 0            # height of that step
    headings: int = 4                # 4: door twins (90-degree pivots); 8: routes (45-degree steps + reverse)
    goal_heading: Optional[int] = None  # route turnarounds: arrive facing this way (in `headings` units)
    kind: str = "door"               # "door" | "s_route" | "hammerhead"
    width_cm: int = 0                # routes: hallway clear width
    bar_cm: int = 0                  # hammerhead: length of the T's bar


def two_room_template(door_cm: int, threshold_mm: int = 0) -> Twin:
    """Two 300x300 cm rooms separated by a 10 cm wall with a single doorway.

    The chair starts in the centre of the left room and must reach the centre of the
    right room. The door's clear width and an optional threshold step vary, so the
    planner's verdict isolates the doorway as the cause.
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
    gap_cells = _cells(door_cm)
    gap_lo = mid - gap_cells // 2
    gap_hi = gap_lo + gap_cells
    thresholds = set()
    for cx in wall_cols:
        for y in range(1, H - 1):
            if gap_lo <= y < gap_hi:
                if threshold_mm > 0:
                    thresholds.add((cx, y))
            else:
                blocked.add((cx, y))

    start = (1 + room // 2, mid, 0)                     # centre of left room, facing +x
    goal = (wall_cols[-1] + 1 + room // 2, mid)         # centre of right room
    return Twin(
        blocked=frozenset(blocked), W=W, H=H, start=start, goal=goal,
        door_cm=door_cm, wall_cols=wall_cols,
        thresholds=frozenset(thresholds), threshold_mm=threshold_mm,
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


# ---- routes: an S-shaped hallway, or a dead end with a T (hammerhead) --------------------

_DIRS = {"E": (1, 0), "S": (0, 1), "W": (-1, 0), "N": (0, -1)}
# Routes use 16 headings (22.5 degrees): with only 45-degree steps the chair must at some
# instant be fully diagonal, which overstates the width a real chair needs to take a bend.
ROUTE_HEADINGS = 16
_HEADING = {d: i * ROUTE_HEADINGS // 4 for i, d in enumerate("ESWN")}   # index facing each way
_END_CELLS = 20      # 100 cm of hallway behind the start and past the goal (chairs up to 160 cm)
_STEM_CELLS = 60     # the hammerhead's approach hallway: 300 cm
_MARGIN = 3


def _band(x0: int, y0: int, x1: int, y1: int, wc: int) -> set:
    """Open cells of a straight hallway `wc` cells wide along a horizontal or vertical segment.

    Each end is extended by half a width so consecutive legs meet in a square corner.
    """
    lo = -(wc // 2)
    if y0 == y1:
        xa, xb = sorted((x0, x1))
        return {(x, y) for x in range(xa + lo, xb + lo + wc) for y in range(y0 + lo, y0 + lo + wc)}
    ya, yb = sorted((y0, y1))
    return {(x, y) for y in range(ya + lo, yb + lo + wc) for x in range(x0 + lo, x0 + lo + wc)}


def _materialise(open_cells: set, start, goal, goal_heading, **fields) -> Twin:
    """Shift open cells to positive coordinates with a wall margin; everything else is wall."""
    xs = [x for x, _ in open_cells]
    ys = [y for _, y in open_cells]
    ox, oy = _MARGIN - min(xs), _MARGIN - min(ys)
    shifted = {(x + ox, y + oy) for x, y in open_cells}
    W, H = max(xs) + ox + 1 + _MARGIN, max(ys) + oy + 1 + _MARGIN
    blocked = frozenset((x, y) for x in range(W) for y in range(H) if (x, y) not in shifted)
    return Twin(blocked=blocked, W=W, H=H,
                start=(start[0] + ox, start[1] + oy, start[2]), goal=(goal[0] + ox, goal[1] + oy),
                door_cm=0, headings=ROUTE_HEADINGS, goal_heading=goal_heading, **fields)


def _s_route(spec: RouteSpec) -> Twin:
    wc = _cells(spec.width_cm)
    pts = [(0, 0)]
    for d, length in spec.legs:
        dx, dy = _DIRS[d]
        x, y = pts[-1]
        pts.append((x + dx * _cells(length), y + dy * _cells(length)))
    (fx, fy), (lx, ly) = _DIRS[spec.legs[0][0]], _DIRS[spec.legs[-1][0]]
    path = [(-fx * _END_CELLS, -fy * _END_CELLS)] + pts + [(pts[-1][0] + lx * _END_CELLS, pts[-1][1] + ly * _END_CELLS)]
    cells = set()
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        cells |= _band(x0, y0, x1, y1, wc)
    return _materialise(cells, start=(0, 0, _HEADING[spec.legs[0][0]]), goal=pts[-1], goal_heading=None,
                        kind="s_route", width_cm=spec.width_cm)


def _hammerhead(spec: RouteSpec) -> Twin:
    """A hallway ending in a T. The chair drives in facing the T and must leave facing out."""
    wc, bc = _cells(spec.width_cm), _cells(spec.bar_cm)
    cells = {(x, y) for x in range(-(bc // 2), -(bc // 2) + bc) for y in range(wc)}            # the bar
    cells |= {(x, y) for x in range(-(wc // 2), -(wc // 2) + wc) for y in range(wc, wc + _STEM_CELLS)}
    sy = wc + _STEM_CELLS - _END_CELLS
    return _materialise(cells, start=(0, sy, _HEADING["N"]), goal=(0, sy), goal_heading=_HEADING["S"],
                        kind="hammerhead", width_cm=spec.width_cm, bar_cm=spec.bar_cm)


def twin_for(spec) -> Twin:
    """The twin a spec describes: the single place that turns measurements into geometry."""
    if isinstance(spec, RouteSpec):
        return _hammerhead(spec) if spec.kind == "hammerhead" else _s_route(spec)
    return two_room_template(door_cm=spec.clear_width_cm, threshold_mm=spec.threshold_mm)
