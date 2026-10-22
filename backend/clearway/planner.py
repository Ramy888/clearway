"""Pilot: a footprint- and orientation-aware path planner over the twin grid.

This is the deterministic ground truth. The chair is a rectangle (width x length) that
occupies real cells at every pose; it moves forward along its heading or turns 90 deg
in place, and a turn is only allowed when the rotated footprint is itself collision
free (that is turning clearance). If no pose sequence reaches the goal, the chair jams,
and we classify why from the grid — never from a model.

Door twins use 4 headings (90-degree pivots), as above. Route twins use 8 headings: a turn is
a 45-degree step whose footprint must fit, so a 180-degree turnaround is four checked steps;
the chair may also reverse, and a twin may require a final heading (turn around, then leave).
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Tuple
import heapq
import math

from .twin import Twin, CELL_CM, max_free_run

# heading 0=+x, 1=+y, 2=-x, 3=-y
_DX = (1, 0, -1, 0)
_DY = (0, 1, 0, -1)
# 8 headings, 45 degrees apart: 0=+x, 2=+y, 4=-x, 6=-y; odd = diagonals
_DX8 = (1, 1, 0, -1, -1, -1, 0, 1)
_DY8 = (0, 1, 1, 1, 0, -1, -1, -1)
_REVERSE_COST = 1.5   # a chair can back up, but prefers driving forward


@dataclass(frozen=True)
class Chair:
    width_cm: int
    length_cm: int
    caster_climb_mm: int = 20   # step height the front casters can roll over
    name: str = "chair"
    axle_offset_cm: int = 0     # drive axle relative to the centre: 0 mid-wheel, negative rear-wheel
    turning_diameter_cm: int = 0  # from the spec sheet; 0 = unknown, so corners stay square (worst case)

    @property
    def width_cells(self) -> int:
        return max(1, round(self.width_cm / CELL_CM))

    @property
    def length_cells(self) -> int:
        return max(1, round(self.length_cm / CELL_CM))


@dataclass(frozen=True)
class Jam:
    reason: str          # "clear_width" | "turn_radius" | "threshold"
    measured: int        # what the home actually offers (in `unit`)
    required: int        # what the chair needs (in `unit`)
    unit: str = "cm"
    detail: str = ""


def _footprint(cx, cy, heading, wc, lc):
    """Axis-aligned cell rectangle the chair covers at this pose."""
    if heading % 2 == 0:        # facing +x / -x: length runs along x
        lx, ly = lc, wc
    else:                       # facing +y / -y: length runs along y
        lx, ly = wc, lc
    return cx - lx // 2, cy - ly // 2, lx, ly


class _Grid:
    """Summed-area table over blocked cells: any rectangle's blocked count in O(1).

    The hosted container has a quarter of a CPU; checking every footprint cell made a run
    take ~6 s there.
    """

    def __init__(self, blocked, W: int, H: int):
        self.W, self.H = W, H
        sat = [[0] * (W + 1) for _ in range(H + 1)]
        for y in range(H):
            row = 0
            for x in range(W):
                row += (x, y) in blocked
                sat[y + 1][x + 1] = sat[y][x + 1] + row
        self._sat = sat

    def free(self, x0: int, y0: int, lx: int, ly: int) -> bool:
        if x0 < 0 or y0 < 0 or x0 + lx > self.W or y0 + ly > self.H:
            return False
        s = self._sat
        return s[y0 + ly][x0 + lx] - s[y0][x0 + lx] - s[y0 + ly][x0] + s[y0][x0] == 0


def _fits(grid: _Grid, state, wc, lc) -> bool:
    return grid.free(*_footprint(*state, wc, lc))


def _neighbors(state, grid: _Grid, wc, lc):
    cx, cy, h = state
    out = []
    fwd = (cx + _DX[h], cy + _DY[h], h)
    if _fits(grid, fwd, wc, lc):
        out.append(fwd)
    for nh in ((h + 1) % 4, (h - 1) % 4):   # turn in place needs clearance
        turned = (cx, cy, nh)
        if _fits(grid, turned, wc, lc):
            out.append(turned)
    return out


# Forward step per heading for 16-heading twins: the smallest grid vector within ~4 degrees.
_BASE16 = ((1, 0), (2, 1), (1, 1), (1, 2))   # 0, 22.5, 45, 67.5 degrees


@lru_cache(maxsize=4)
def _step_vectors(n: int):
    if n == 8:
        return tuple(zip(_DX8, _DY8))
    out = []
    for i in range(16):
        q, r = divmod(i, 4)
        x, y = _BASE16[r]
        for _ in range(q):        # rotate a quarter turn: +x -> +y
            x, y = -y, x
        out.append((x, y))
    return tuple(out)


def _mask_runs(wc: int, lc: int, h8: int):
    """Row runs of the footprint at 8-heading index `h8` (kept for the 8-heading API)."""
    return _mask_runs_deg(wc, lc, 45.0 * h8)


@lru_cache(maxsize=256)
def _mask_runs_deg(wc: int, lc: int, deg: float):
    """Cells under the chair at an angled heading, as row runs (dy, dx0, width) from the pivot.

    A cell is covered when its centre lies inside the rotated rectangle (length along the
    heading, width across it). Rows let the summed-area table check each run in O(1).
    """
    ang = math.radians(deg)
    ux, uy, vx, vy = math.cos(ang), math.sin(ang), -math.sin(ang), math.cos(ang)
    hl, hw = lc / 2 - 1e-9, wc / 2 - 1e-9
    r = math.ceil(math.hypot(lc, wc) / 2) + 1
    runs = []
    for dy in range(-r, r + 1):
        xs = [dx for dx in range(-r, r + 1)
              if abs((dx + .5) * ux + (dy + .5) * uy) < hl and abs((dx + .5) * vx + (dy + .5) * vy) < hw]
        if xs:   # a convex shape: each row is one contiguous run
            runs.append((dy, xs[0], xs[-1] - xs[0] + 1))
    return tuple(runs)


def _fits_n(grid: _Grid, state, wc, lc, n: int) -> bool:
    cx, cy, h = state
    q = n // 4
    if h % q == 0:   # axis-aligned: the same footprint as the 4-heading planner, O(1)
        return grid.free(*_footprint(cx, cy, h // q, wc, lc))
    return all(grid.free(cx + dx0, cy + dy, w, 1) for dy, dx0, w in _mask_runs_deg(wc, lc, 360.0 * h / n))


def _fits8(grid: _Grid, state, wc, lc) -> bool:
    return _fits_n(grid, state, wc, lc, 8)


def _neighbors_n(state, grid: _Grid, wc, lc, n: int):
    """(next pose, cost): forward, reverse, or one heading step (360/n degrees) in place."""
    cx, cy, h = state
    dx, dy = _step_vectors(n)[h]
    step = math.hypot(dx, dy)
    for nxt, cost in (((cx + dx, cy + dy, h), step),
                      ((cx - dx, cy - dy, h), step * _REVERSE_COST),
                      ((cx, cy, (h + 1) % n), 1.0),
                      ((cx, cy, (h - 1) % n), 1.0)):
        if _fits_n(grid, nxt, wc, lc, n):
            yield nxt, cost


def _heur(state, goal):
    return math.hypot(state[0] - goal[0], state[1] - goal[1])


def _effective_blocked(twin: Twin, chair: Chair):
    """Grid cells the chair cannot occupy: walls, plus any threshold it can't climb."""
    if twin.thresholds and twin.threshold_mm > chair.caster_climb_mm:
        return twin.blocked | twin.thresholds
    return twin.blocked


@dataclass(frozen=True)
class Plan:
    reached: bool
    poses: List[Tuple[int, int, int]]   # start ... goal, or start ... furthest progress
    exhausted: bool = False             # search budget ran out: undetermined, NOT a jam


def _reconstruct(came, s):
    path = [s]
    while s in came:
        s = came[s]
        path.append(s)
    return path[::-1]


def plan(twin: Twin, chair: Chair) -> Plan:
    """A* over (x, y, heading). On a jam, the path to the closest reachable pose.

    Door twins (4 headings) use the pivot-in-place model below. Route twins need real turning
    and go to the wheelchair kinematics in kinematics.py.
    """
    if twin.headings != 4:
        from .kinematics import plan_route
        return plan_route(twin, chair)
    wc, lc = chair.width_cells, chair.length_cells
    grid = _Grid(_effective_blocked(twin, chair), twin.W, twin.H)
    start, goal, want_h = twin.start, twin.goal, twin.goal_heading
    fits, neighbors = _fits, lambda s, g, w, l: ((n, 1) for n in _neighbors(s, g, w, l))
    if not fits(grid, start, wc, lc):
        return Plan(False, [start])
    openh = [(_heur(start, goal), 0, start)]
    best = {start: 0}
    came = {}
    closest = (_heur(start, goal), 0, start)   # (distance, cost, pose): ties -> cheapest
    while openh:
        _, g, s = heapq.heappop(openh)
        if g > best.get(s, 1 << 30):
            continue
        if (s[0], s[1]) == goal and (want_h is None or s[2] == want_h):
            return Plan(True, _reconstruct(came, s))
        if (_heur(s, goal), g) < closest[:2]:
            closest = (_heur(s, goal), g, s)
        for ns, cost in neighbors(s, grid, wc, lc):
            ng = g + cost
            if ng < best.get(ns, 1 << 30):
                best[ns] = ng
                came[ns] = s
                heapq.heappush(openh, (ng + _heur(ns, goal), ng, ns))
    return Plan(False, _reconstruct(came, closest[2]))


def _pivot_radius(chair: Chair, c: float) -> float:
    """Farthest footprint vertex from the axle, with corners trimmed by `c` cm."""
    far, half_w = chair.length_cm / 2 + abs(chair.axle_offset_cm), chair.width_cm / 2
    return max(math.hypot(far, half_w - c), math.hypot(far - c, half_w))


def chamfer_cm(chair: Chair) -> float:
    """Corner trim that makes the footprint's pivot circle match the spec-sheet turning diameter.

    Real chairs have rounded casters, footplates and backrests, so a full rectangle sweeps more
    than they do. With no spec (0) the corners stay square: the conservative worst case.
    """
    target = chair.turning_diameter_cm / 2
    cmax = min(chair.length_cm, chair.width_cm) / 2
    if target <= 0 or _pivot_radius(chair, 0) <= target:
        return 0.0
    if _pivot_radius(chair, cmax) >= target:
        return cmax          # the spec is tighter than this footprint allows: trim as far as it can
    lo, hi = 0.0, cmax
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _pivot_radius(chair, mid) > target else (lo, mid)
    return hi


def pivot_diameter_cm(chair: Chair) -> float:
    """Clear circle a chair sweeps spinning on the spot about its axle."""
    return 2 * _pivot_radius(chair, chamfer_cm(chair))


def drive(twin: Twin, chair: Chair) -> bool:
    """True if the chair can reach the goal from the start, else False (it jams)."""
    return plan(twin, chair).reached


def analyze(twin: Twin, chair: Chair) -> Jam | None:
    """Return None if the chair reaches the goal, else a classified Jam."""
    if drive(twin, chair):
        return None
    # Jammed: measure the real opening from the grid and classify, in priority order.
    gap_cells = max((max_free_run(twin, c) for c in twin.wall_cols), default=0)
    measured_cm = gap_cells * twin.cell_cm
    if gap_cells < chair.width_cells:
        return Jam(
            reason="clear_width",
            measured=measured_cm,
            required=chair.width_cm,
            unit="cm",
            detail=f"doorway clear width {measured_cm} cm < chair width {chair.width_cm} cm",
        )
    if twin.thresholds and twin.threshold_mm > chair.caster_climb_mm:
        return Jam(
            reason="threshold",
            measured=twin.threshold_mm,
            required=chair.caster_climb_mm,
            unit="mm",
            detail=f"doorway step {twin.threshold_mm} mm > casters climb {chair.caster_climb_mm} mm",
        )
    return Jam(
        reason="turn_radius",
        measured=measured_cm,
        required=chair.width_cm,
        unit="cm",
        detail="chair cannot maneuver through the route despite adequate door width",
    )
