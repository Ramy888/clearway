"""Pilot: a footprint- and orientation-aware path planner over the twin grid.

This is the deterministic ground truth. The chair is a rectangle (width x length) that
occupies real cells at every pose; it moves forward along its heading or turns 90 deg
in place, and a turn is only allowed when the rotated footprint is itself collision
free (that is turning clearance). If no pose sequence reaches the goal, the chair jams,
and we classify why from the grid — never from a model.

shortcut: 4 headings (orthogonal) for D1; D2 widens to 8 headings for diagonal moves.
"""
from dataclasses import dataclass
from typing import List, Tuple
import heapq
import math

from .twin import Twin, CELL_CM, max_free_run

# heading 0=+x, 1=+y, 2=-x, 3=-y
_DX = (1, 0, -1, 0)
_DY = (0, 1, 0, -1)


@dataclass(frozen=True)
class Chair:
    width_cm: int
    length_cm: int
    caster_climb_mm: int = 20   # step height the front casters can roll over
    name: str = "chair"

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


def _fits(blocked, W, H, state, wc, lc) -> bool:
    cx, cy, h = state
    x0, y0, lx, ly = _footprint(cx, cy, h, wc, lc)
    if x0 < 0 or y0 < 0 or x0 + lx > W or y0 + ly > H:
        return False
    for xx in range(x0, x0 + lx):
        for yy in range(y0, y0 + ly):
            if (xx, yy) in blocked:
                return False
    return True


def _neighbors(state, blocked, W, H, wc, lc):
    cx, cy, h = state
    out = []
    fwd = (cx + _DX[h], cy + _DY[h], h)
    if _fits(blocked, W, H, fwd, wc, lc):
        out.append(fwd)
    for nh in ((h + 1) % 4, (h - 1) % 4):   # turn in place needs clearance
        turned = (cx, cy, nh)
        if _fits(blocked, W, H, turned, wc, lc):
            out.append(turned)
    return out


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


def _reconstruct(came, s):
    path = [s]
    while s in came:
        s = came[s]
        path.append(s)
    return path[::-1]


def plan(twin: Twin, chair: Chair) -> Plan:
    """A* over (x, y, heading). On a jam, the path to the closest reachable pose."""
    wc, lc = chair.width_cells, chair.length_cells
    blocked, W, H = _effective_blocked(twin, chair), twin.W, twin.H
    start, goal = twin.start, twin.goal
    if not _fits(blocked, W, H, start, wc, lc):
        return Plan(False, [start])
    openh = [(_heur(start, goal), 0, start)]
    best = {start: 0}
    came = {}
    closest = (_heur(start, goal), 0, start)   # (distance, moves, pose): ties -> fewest moves
    while openh:
        _, g, s = heapq.heappop(openh)
        if g > best.get(s, 1 << 30):
            continue
        if (s[0], s[1]) == goal:
            return Plan(True, _reconstruct(came, s))
        if (_heur(s, goal), g) < closest[:2]:
            closest = (_heur(s, goal), g, s)
        for ns in _neighbors(s, blocked, W, H, wc, lc):
            ng = g + 1
            if ng < best.get(ns, 1 << 30):
                best[ns] = ng
                came[ns] = s
                heapq.heappush(openh, (ng + _heur(ns, goal), ng, ns))
    return Plan(False, _reconstruct(came, closest[2]))


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
