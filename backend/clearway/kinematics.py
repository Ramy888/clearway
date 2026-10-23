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

A `Vehicle` (car mode) uses the same body, keyed on its rear axle, but cannot pivot: it drives
straight or along arcs of its minimum turning radius, checked densely enough for long arcs.
"""
import heapq
import math
from dataclasses import dataclass
from functools import lru_cache

from .planner import Plan, _Grid, _effective_blocked, _reconstruct, _step_vectors, chamfer_cm
from .twin import CELL_CM, Twin

TURN_COST = 1.0        # per heading step when pivoting on the spot
REVERSE_COST = 1.5     # a chair can back up, but prefers driving forward
ARC_RADIUS = 8         # cells (40 cm): radius of the axle's path on an arc
MAX_EXPANSIONS = 400_000


@dataclass(frozen=True)
class Vehicle:
    """A car: a rectangle keyed on its rear axle, turning no tighter than `min_radius_cm`."""
    name: str
    length_cm: int
    width_cm: int
    axle_offset_cm: float          # rear axle from the centre, along the heading (negative = behind)
    min_radius_cm: float           # path radius of the rear axle's midpoint at full lock
    ramp_length_cm: int = 0        # side ramp, deployed on the passenger side
    ramp_width_cm: int = 0
    turning_diameter_cm: int = 0   # (chairs only) 0 keeps the footprint a plain rectangle
    caster_climb_mm: int = 0

    @property
    def radius_cells(self) -> int:
        return round(self.min_radius_cm / CELL_CM)


# BraunAbility Toyota Sienna Hybrid, side-entry Power Infloor ramp. Toyota: 5174 x 1994 mm,
# wheelbase 3061 mm, minimum turning radius 5.8 m (tyre); BraunAbility: ramp 52 in long, 30.3 in
# clear. Estimated (unpublished): rear axle 110 cm from the rear bumper, track 172 cm, so the
# rear-axle radius is sqrt(580^2 - 306.1^2) - 86 cm.
SIENNA = Vehicle("BraunAbility Toyota Sienna (side-entry)", length_cm=517, width_cm=199,
                 axle_offset_cm=-(517 / 2 - 110), min_radius_cm=math.sqrt(580 ** 2 - 306.1 ** 2) - 86,
                 ramp_length_cm=132, ramp_width_cm=77)


def _arc_radius(body) -> float:
    return body.radius_cells if isinstance(body, Vehicle) else ARC_RADIUS


def arc_checks(body, n: int) -> int:
    """Poses checked per arc step, so the sliver missed between them (r * theta^2 / 8, r the
    body's farthest point from the turn centre) stays under half a cell. Chairs: 2 (half, end)."""
    hw = body.width_cm / 2 / CELL_CM
    a = body.length_cm / 2 / CELL_CM + abs(body.axle_offset_cm) / CELL_CM
    r = math.hypot(_arc_radius(body) + hw, a)
    return max(2, math.ceil(math.radians(360 / n) / math.sqrt(4 / r)))


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


def _primitives(ax: int, ay: int, h: int, n: int, body: _Body, radius: float, pivots: bool, fracs):
    """(next state, cost) for every move that fits, sweep included."""
    step = 360.0 / n
    deg = h * step
    sx, sy = _step_vectors(n)[h]
    length = math.hypot(sx, sy)
    for s, cost in ((1, length), (-1, length * REVERSE_COST)):            # straight
        if body.fits(ax + s * sx, ay + s * sy, deg):
            yield (ax + s * sx, ay + s * sy, h), cost
    for t in ((1, -1) if pivots else ()):                                 # pivot about the axle
        if body.fits(ax, ay, deg + t * step / 2) and body.fits(ax, ay, deg + t * step):
            yield (ax, ay, (h + t) % n), TURN_COST
    a = math.radians(deg)
    vx, vy = -math.sin(a), math.cos(a)
    arc = radius * math.radians(step)
    for side in (1, -1):                                                  # arcs: left / right of the axle
        ccx, ccy = ax + side * radius * vx, ay + side * radius * vy
        for direction, cost in ((1, arc), (-1, arc * REVERSE_COST)):
            turn = direction * side                                       # heading change in steps
            ok = True
            for frac in fracs:
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


VEHICLE_WEIGHT = 2.0   # cars: weighted A* finds A feasible path fast; parking needs no shortest one


def _wall_distance(twin: Twin, goal) -> dict:
    """Steps from every open cell to the goal, around walls (8-connected BFS): the Hybrid-A* guide."""
    dist, frontier = {goal: 0}, [goal]
    blocked, W, H = twin.blocked, twin.W, twin.H
    while frontier:
        nxt = []
        for x, y in frontier:
            d = dist[(x, y)] + 1
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    c = (x + dx, y + dy)
                    if c not in dist and 0 <= c[0] < W and 0 <= c[1] < H and c not in blocked:
                        dist[c] = d
                        nxt.append(c)
        frontier = nxt
    return dist


def plan_route(twin: Twin, chair) -> Plan:
    n = twin.headings
    body = _Body(_Grid(_effective_blocked(twin, chair), twin.W, twin.H), chair)
    k = arc_checks(chair, n)
    moves = (_arc_radius(chair), not isinstance(chair, Vehicle), tuple(i / k for i in range(1, k + 1)))
    start, (gx, gy), want_h = twin.start, twin.goal, twin.goal_heading
    if isinstance(chair, Vehicle):    # chairs keep exact A*; a car's search needs the guide
        guide, arc = _wall_distance(twin, (gx, gy)), chair.radius_cells * math.radians(360 / n)

        def h(s):
            dh = abs((s[2] - want_h + n // 2) % n - n // 2) if want_h is not None else 0
            return VEHICLE_WEIGHT * (max(math.hypot(s[0] - gx, s[1] - gy),
                                         guide.get((round(s[0]), round(s[1])), math.inf)) + dh * arc)
    else:
        def h(s):
            return math.hypot(s[0] - gx, s[1] - gy)
    if not body.fits(start[0], start[1], start[2] * 360.0 / n):
        return Plan(False, [start])
    turnaround = want_h is not None and math.hypot(gx - start[0], gy - start[1]) <= 2

    def at_goal(s):
        return max(abs(s[0] - gx), abs(s[1] - gy)) <= 1 and (want_h is None or s[2] == want_h)

    def progress(s, g):   # for a jam: how far it got (a failed turnaround: how far it drove in)
        if turnaround:
            return (-math.hypot(s[0] - start[0], s[1] - start[1]), g)
        return (math.hypot(s[0] - gx, s[1] - gy), g)

    openh = [(h(start), 0.0, start)]
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
        for ns, cost in _primitives(s[0], s[1], s[2], n, body, *moves):
            ng = g + cost
            if ng < best.get(ns, math.inf):
                best[ns] = ng
                came[ns] = s
                heapq.heappush(openh, (ng + h(ns), ng, ns))
    return Plan(False, _reconstruct(came, closest[1]))


@lru_cache(maxsize=32)
def van_plan(twin: Twin) -> Plan:
    """The van's own drive into the bay; it does not depend on the chair, so it is planned once."""
    return plan_route(twin, SIENNA)


def ramp_strip(twin: Twin, chair, van: Vehicle = SIENNA):
    """Cells (x0, y0, w, h) the deployed ramp needs on the passenger side of the parked van, plus the
    chair's own length to roll clear of it. shortcut: door centred on the van, chair goes straight
    off the ramp (its turn after that is not modelled)."""
    a = math.radians(twin.goal_heading * 360.0 / twin.headings)
    hx, hy = math.cos(a), math.sin(a)
    d = van.axle_offset_cm / CELL_CM
    cx, cy = twin.goal[0] - d * hx, twin.goal[1] - d * hy        # axle = centre + d * heading
    rx, ry = -hy, hx                                             # passenger side (screen y points down)
    near, far = van.width_cm / 2 / CELL_CM, (van.width_cm / 2 + van.ramp_length_cm + chair.length_cm) / CELL_CM
    half = van.ramp_width_cm / 2 / CELL_CM
    pts = [(cx + rx * t + hx * s, cy + ry * t + hy * s) for t in (near, far) for s in (-half, half)]
    x0, y0 = math.floor(min(p[0] for p in pts) + 1e-9), math.floor(min(p[1] for p in pts) + 1e-9)
    x1, y1 = math.ceil(max(p[0] for p in pts) - 1e-9), math.ceil(max(p[1] for p in pts) - 1e-9)
    return x0, y0, x1 - x0, y1 - y0


def ramp_clear(twin: Twin, chair, van: Vehicle = SIENNA) -> bool:
    return chair.width_cm <= van.ramp_width_cm and _Grid(twin.blocked, twin.W, twin.H).free(*ramp_strip(twin, chair, van))


def plan_driveway(twin: Twin, chair) -> Plan:
    """Physics for car mode: the van parks, then the ramp deploys and the chair rolls off it."""
    p = van_plan(twin)
    return Plan(p.reached and ramp_clear(twin, chair), p.poses, p.exhausted)
