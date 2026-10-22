"""Route planner: a wheelchair as a rigid rectangle that turns about its drive axle.

Door twins only need straight passage; routes need turning, and turning is where a naive
model lies. Here the chair is a W x L rectangle whose drive axle sits `axle_offset_cm` from
its centre (0 = mid-wheel, negative = rear-wheel drive). Its state is the axle position on the
5 cm grid plus one of 16 headings, and it moves the way a wheelchair can:

  - straight, forward or in reverse;
  - pivot on the spot about the axle (one heading step);
  - drive an arc about a turn centre beside the axle, forward or in reverse, left or right.

Pivots and arcs also check the halfway pose, so the swept area is covered. Cells are blocked if
the chair overlaps them at all, so the model can be pessimistic by at most one grid cell, never
optimistic. If the search runs out of budget the result is `exhausted` — undetermined, not a jam.
"""
import heapq
import math
from functools import lru_cache

from .planner import Plan, _Grid, _effective_blocked, _reconstruct, _step_vectors, chamfer_cm
from .twin import CELL_CM, Twin

TURN_COST = 1.0        # per heading step when pivoting on the spot
REVERSE_COST = 1.5     # a chair can back up, but prefers driving forward
ARC_RADIUS = 8         # cells (40 cm): radius of the axle's path on an arc
MAX_EXPANSIONS = 400_000


@lru_cache(maxsize=16384)
def _rows(length_cm: int, width_cm: int, chamfer: float, deg: float, fx: float, fy: float):
    """Cells the rotated footprint overlaps, as row runs (row, x0, width) relative to a base cell.

    The footprint is the chair's rectangle with corners trimmed by `chamfer` cm (an octagon;
    a plain rectangle when 0). Its centre is at (fx, fy) inside the base cell. Exact, not
    padded: the offsets that occur are a small finite set (they depend only on the angle and
    the move type), so caching them exactly costs little.
    """
    hl, hw, c = length_cm / (2 * CELL_CM), width_cm / (2 * CELL_CM), chamfer / CELL_CM
    a = math.radians(deg)
    ux, uy, vx, vy = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
    local = [(hl, -(hw - c)), (hl, hw - c), (hl - c, hw), (-(hl - c), hw),
             (-hl, hw - c), (-hl, -(hw - c)), (-(hl - c), -hw), (hl - c, -hw)]
    pts = [(fx + p * ux + q * vx, fy + p * uy + q * vy) for p, q in local]
    ys = [y for _, y in pts]
    runs = []
    for r in range(math.floor(min(ys)), math.ceil(max(ys))):
        xs = [x for x, y in pts if r <= y <= r + 1]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            for yy in (r, r + 1):
                if (y1 - yy) * (y2 - yy) < 0:
                    xs.append(x1 + (x2 - x1) * (yy - y1) / (y2 - y1))
        if xs:
            x0, x1 = math.floor(min(xs)), math.ceil(max(xs)) - 1
            runs.append((r, x0, max(x1, x0) - x0 + 1))
    return tuple(runs)


class _Body:
    """Collision checks for one chair on one grid, at any axle position and angle."""

    def __init__(self, grid: _Grid, chair):
        self.grid, self.L, self.W = grid, chair.length_cm, chair.width_cm
        self.d = chair.axle_offset_cm / CELL_CM
        self.c = round(chamfer_cm(chair), 3)

    def fits(self, ax: float, ay: float, deg: float) -> bool:
        a = math.radians(deg)
        cx, cy = ax - self.d * math.cos(a), ay - self.d * math.sin(a)   # axle = centre + d * heading
        cx, cy = round(cx, 6), round(cy, 6)          # absorb float noise so equal poses share a key
        bx, by = math.floor(cx), math.floor(cy)
        free = self.grid.free
        rows = _rows(self.L, self.W, self.c, round(deg % 360, 4), round(cx - bx, 6), round(cy - by, 6))
        return all(free(bx + x0, by + r, w, 1) for r, x0, w in rows)


def _primitives(ax: int, ay: int, h: int, n: int, body: _Body):
    """(next state, cost) for every move that fits, sweep included."""
    step = 360.0 / n
    deg = h * step
    sx, sy = _step_vectors(n)[h]
    length = math.hypot(sx, sy)
    for s, cost in ((1, length), (-1, length * REVERSE_COST)):            # straight
        if body.fits(ax + s * sx, ay + s * sy, deg):
            yield (ax + s * sx, ay + s * sy, h), cost
    for t in (1, -1):                                                     # pivot about the axle
        if body.fits(ax, ay, deg + t * step / 2) and body.fits(ax, ay, deg + t * step):
            yield (ax, ay, (h + t) % n), TURN_COST
    a = math.radians(deg)
    vx, vy = -math.sin(a), math.cos(a)
    arc = ARC_RADIUS * math.radians(step)
    for side in (1, -1):                                                  # arcs: left / right of the axle
        ccx, ccy = ax + side * ARC_RADIUS * vx, ay + side * ARC_RADIUS * vy
        for direction, cost in ((1, arc), (-1, arc * REVERSE_COST)):
            turn = direction * side                                       # heading change in steps
            ok = True
            for frac in (0.5, 1.0):
                phi = math.radians(turn * step * frac)
                rx, ry = ax - ccx, ay - ccy
                px = ccx + rx * math.cos(phi) - ry * math.sin(phi)
                py = ccy + rx * math.sin(phi) + ry * math.cos(phi)
                if frac == 1.0:
                    px, py = round(px), round(py)
                if not body.fits(px, py, deg + turn * step * frac):
                    ok = False
                    break
            if ok:
                yield (px, py, (h + turn) % n), cost


def plan_route(twin: Twin, chair) -> Plan:
    n = twin.headings
    body = _Body(_Grid(_effective_blocked(twin, chair), twin.W, twin.H), chair)
    start, (gx, gy), want_h = twin.start, twin.goal, twin.goal_heading
    if not body.fits(start[0], start[1], start[2] * 360.0 / n):
        return Plan(False, [start])
    turnaround = want_h is not None and math.hypot(gx - start[0], gy - start[1]) <= 2

    def at_goal(s):
        return max(abs(s[0] - gx), abs(s[1] - gy)) <= 1 and (want_h is None or s[2] == want_h)

    def progress(s, g):   # for a jam: how far it got (a failed turnaround: how far it drove in)
        if turnaround:
            return (-math.hypot(s[0] - start[0], s[1] - start[1]), g)
        return (math.hypot(s[0] - gx, s[1] - gy), g)

    openh = [(math.hypot(start[0] - gx, start[1] - gy), 0.0, start)]
    best, came = {start: 0.0}, {}
    closest = (progress(start, 0.0), start)
    expansions = 0
    while openh:
        _, g, s = heapq.heappop(openh)
        if g > best.get(s, math.inf):
            continue
        if at_goal(s):
            return Plan(True, _reconstruct(came, s))
        expansions += 1
        if expansions > MAX_EXPANSIONS:
            return Plan(False, _reconstruct(came, closest[1]), exhausted=True)
        if progress(s, g) < closest[0]:
            closest = (progress(s, g), s)
        for ns, cost in _primitives(s[0], s[1], s[2], n, body):
            ng = g + cost
            if ng < best.get(ns, math.inf):
                best[ns] = ng
                came[ns] = s
                heapq.heappush(openh, (ng + math.hypot(ns[0] - gx, ns[1] - gy), ng, ns))
    return Plan(False, _reconstruct(came, closest[1]))
