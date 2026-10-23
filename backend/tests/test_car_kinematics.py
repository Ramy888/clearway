"""Calibration: a car must move like a car before it judges any driveway.

A wheelchair-accessible van is a rigid rectangle keyed on its rear axle. Unlike a wheelchair it
cannot pivot on the spot: it drives straight or along arcs no tighter than its minimum turning
radius. These tests pin that model to closed-form geometry.
"""
import math
import time
import unittest

from clearway.kinematics import SIENNA, Vehicle, arc_checks, plan_route
from clearway.planner import Chair
from clearway.twin import CELL_CM, ROUTE_HEADINGS, Twin

MID = Chair(70, 110, name="power", axle_offset_cm=0)


def ring(van: Vehicle, inner_cells: float, outer_cells: float, quarter=1) -> Twin:
    """An annular track around (c, c). The van's rear axle starts on the radius-R circle heading
    +y, tangent to it, and must drive `quarter` quarter-circles round (counter-clockwise on screen)."""
    R = van.radius_cells
    c = int(math.ceil(outer_cells)) + 4
    W = H = 2 * c + 1
    open_cells = {(x, y) for x in range(W) for y in range(H)
                  if inner_cells <= math.hypot(x + 0.5 - c, y + 0.5 - c) and
                  math.hypot(x + 0.5 - c, y + 0.5 - c) <= outer_cells and
                  # every cell must lie fully inside the ring: test the corners too
                  all(inner_cells <= math.hypot(x + dx - c, y + dy - c) <= outer_cells
                      for dx in (0, 1) for dy in (0, 1))}
    blocked = frozenset((x, y) for x in range(W) for y in range(H) if (x, y) not in open_cells)
    q = ROUTE_HEADINGS // 4
    start = (c + R, c, q)                                 # heading +y (index 4 of 16)
    # a left turn about the centre: after a quarter the axle is at (c, c + R) heading -x
    ends = {1: ((c, c + R), 2 * q), 2: ((c - R, c), 3 * q)}
    goal, gh = ends[quarter]
    return Twin(blocked=blocked, W=W, H=H, start=start, goal=goal, door_cm=0,
                headings=ROUTE_HEADINGS, goal_heading=gh, kind="ring")


def swept(van: Vehicle):
    """Closed-form annulus a forward min-radius turn sweeps: [R - W/2, sqrt((R + W/2)^2 + a^2)]."""
    R = van.radius_cells
    hw = van.width_cm / 2 / CELL_CM
    a = (van.length_cm / 2 - van.axle_offset_cm) / CELL_CM   # rear axle to front bumper
    return R - hw, math.hypot(R + hw, a)


class TestVehicleSpec(unittest.TestCase):
    def test_sienna_numbers_come_from_the_spec_sheet(self):
        # Toyota Sienna: 5174 x 1994 mm, wheelbase 3061 mm; BraunAbility ramp 52 in x 30.3 in
        self.assertEqual((SIENNA.length_cm, SIENNA.width_cm), (517, 199))
        self.assertEqual((SIENNA.ramp_length_cm, SIENNA.ramp_width_cm), (132, 77))
        # rear-axle path radius from the 5.8 m tyre radius: sqrt(5.8^2 - 3.061^2) - track/2
        self.assertAlmostEqual(SIENNA.min_radius_cm, math.sqrt(580 ** 2 - 306.1 ** 2) - 86, delta=1)


class TestCarCalibration(unittest.TestCase):
    def test_a_ring_just_wider_than_the_swept_annulus_is_driveable(self):
        lo, hi = swept(SIENNA)
        self.assertTrue(plan_route(ring(SIENNA, lo - 2, hi + 2), SIENNA).reached)

    def test_a_ring_narrower_than_the_swept_annulus_jams(self):
        lo, hi = swept(SIENNA)
        p = plan_route(ring(SIENNA, lo - 2, hi - 3), SIENNA)
        self.assertFalse(p.reached)
        self.assertFalse(p.exhausted, "a narrow ring must be decided, not run out of budget")

    def test_the_search_itself_drives_a_half_ring_the_direct_manoeuvre_cannot(self):
        lo, hi = swept(SIENNA)
        p = plan_route(ring(SIENNA, lo - 2, hi + 2, quarter=2), SIENNA)
        self.assertTrue(p.reached)
        for (x0, y0, h0), (x1, y1, h1) in zip(p.poses, p.poses[1:]):
            self.assertFalse((x0, y0) == (x1, y1) and h0 != h1, f"pivot at {(x0, y0)}")
        self.assertFalse(plan_route(ring(SIENNA, lo - 2, hi - 3, quarter=2), SIENNA).reached)

    def test_a_van_never_pivots_on_the_spot(self):
        lo, hi = swept(SIENNA)
        poses = plan_route(ring(SIENNA, lo - 2, hi + 2), SIENNA).poses
        for (x0, y0, h0), (x1, y1, h1) in zip(poses, poses[1:]):
            self.assertFalse((x0, y0) == (x1, y1) and h0 != h1, f"pivot at {(x0, y0)}")

    def test_a_room_a_chair_turns_around_in_is_no_turnaround_for_a_van(self):
        s = 620 // CELL_CM                       # 6.2 m square: longer than the van, far tighter than its turn
        W = H = s + 6
        open_cells = {(x, y) for x in range(3, 3 + s) for y in range(3, 3 + s)}
        blocked = frozenset((x, y) for x in range(W) for y in range(H) if (x, y) not in open_cells)
        c = 3 + s // 2
        room = Twin(blocked=blocked, W=W, H=H, start=(c, c, 0), goal=(c, c), door_cm=0,
                    headings=ROUTE_HEADINGS, goal_heading=ROUTE_HEADINGS // 2, kind="room")
        self.assertTrue(plan_route(room, MID).reached)
        self.assertFalse(plan_route(room, SIENNA).reached)


class TestSweep(unittest.TestCase):
    def test_long_arcs_are_checked_densely_enough_that_no_wall_slips_through(self):
        # uncovered sliver between checked poses: r * theta^2 / 8 <= half a cell
        step = math.radians(360 / ROUTE_HEADINGS)
        lo, hi = swept(SIENNA)
        k = arc_checks(SIENNA, ROUTE_HEADINGS)
        self.assertLessEqual(hi * (step / k) ** 2 / 8, 0.5)

    def test_chairs_keep_two_checks_per_arc(self):
        self.assertEqual(arc_checks(MID, ROUTE_HEADINGS), 2)


class TestCost(unittest.TestCase):
    def test_a_quarter_turn_plans_quickly(self):
        lo, hi = swept(SIENNA)
        track = ring(SIENNA, lo - 2, hi + 2)    # building the test ring is not the planner's cost
        t = time.perf_counter()
        plan_route(track, SIENNA)
        self.assertLess(time.perf_counter() - t, 2.0)


if __name__ == "__main__":
    unittest.main()
