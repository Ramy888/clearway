"""Calibration: the route planner must agree with geometry before it judges any home.

A wheelchair is a rigid rectangle that turns about its drive axle, drives arcs, and
reverses. These tests pin the planner to closed-form truths, so it can be neither
optimistic (a chair squeezing through what no rigid body could) nor pessimistic (a chair
trapped where real motion fits), which is how the previous centre-pivot model failed.
"""
import math
import unittest

from clearway.planner import Chair, pivot_diameter_cm, plan
from clearway.rules import RouteSpec
from clearway.twin import CELL_CM, ROUTE_HEADINGS, Twin, twin_for

MID = Chair(70, 110, name="power", axle_offset_cm=0)      # mid-wheel drive: turns about its centre
REAR = Chair(64, 100, name="manual", axle_offset_cm=-25)  # rear-wheel drive: axle 25 cm behind centre


def size(chair):
    """The chair's true footprint in cm (the kinematic model uses exact dimensions)."""
    return chair.width_cm, chair.length_cm


def up5(cm):
    return int(math.ceil(cm / CELL_CM) * CELL_CM)


def down5(cm):
    return int(math.floor(cm / CELL_CM) * CELL_CM)


def corner_bound(chair):
    """Narrowest equal-width L-corner any rigid W x L rectangle can pass: (L/2 + W) / sqrt(2)."""
    w, l = size(chair)
    return (l / 2 + w) / math.sqrt(2)


def reached(spec_or_twin, chair):
    twin = spec_or_twin if isinstance(spec_or_twin, Twin) else twin_for(spec_or_twin)
    return plan(twin, chair).reached


def straight(width):
    return RouteSpec("s_route", width, legs=(("E", 400),))


def corner(width, legs=(("E", 300), ("S", 300))):
    return RouteSpec("s_route", width, legs=legs)


def room(side_cm):
    """A square room; the chair's axle starts at the centre and must leave facing the other way."""
    s = side_cm // CELL_CM
    W = H = s + 6
    open_cells = {(x, y) for x in range(3, 3 + s) for y in range(3, 3 + s)}
    blocked = frozenset((x, y) for x in range(W) for y in range(H) if (x, y) not in open_cells)
    c = 3 + s // 2
    return Twin(blocked=blocked, W=W, H=H, start=(c, c, 0), goal=(c, c), door_cm=0,
                headings=ROUTE_HEADINGS, goal_heading=ROUTE_HEADINGS // 2, kind="room")


class TestStraight(unittest.TestCase):
    def test_never_narrower_than_the_chair_and_at_most_one_cell_pessimistic(self):
        for chair in (MID, REAR):
            w, _ = size(chair)
            narrower = up5(w) - CELL_CM if up5(w) - CELL_CM < w else down5(w) - CELL_CM
            self.assertFalse(reached(straight(narrower), chair), (chair.name, narrower))
            self.assertTrue(reached(straight(up5(w) + CELL_CM), chair), chair.name)


class TestCorner(unittest.TestCase):
    def test_no_rigid_body_passes_below_the_bound(self):
        for chair in (MID, REAR):
            self.assertFalse(reached(corner(down5(corner_bound(chair)) - CELL_CM), chair), chair.name)

    def test_a_mid_wheel_chair_passes_within_ten_cm_of_the_bound(self):
        self.assertTrue(reached(corner(up5(corner_bound(MID)) + 10), MID))

    def test_wider_never_hurts_and_mirroring_never_matters(self):
        mirrored = (("W", 300), ("S", 300))
        for chair in (MID, REAR):
            verdicts = [reached(corner(w), chair) for w in range(80, 135, 5)]
            self.assertEqual(verdicts, sorted(verdicts), chair.name)   # False...False, True...True
            for w in (90, 100, 110):
                self.assertEqual(reached(corner(w), chair), reached(corner(w, mirrored), chair), (chair.name, w))


class TestTurnaround(unittest.TestCase):
    def test_room_bounds_for_a_mid_wheel_chair(self):
        w, l = size(MID)
        self.assertFalse(reached(room(down5((l + w) / math.sqrt(2)) - CELL_CM), MID))   # 45-degree pose can't fit
        self.assertTrue(reached(room(up5(math.hypot(l, w)) + CELL_CM), MID))             # rotates about its centre

    def test_a_rear_axle_chair_needs_a_bigger_pivot_circle(self):
        self.assertAlmostEqual(pivot_diameter_cm(MID), 2 * math.hypot(55, 35), delta=1)
        self.assertAlmostEqual(pivot_diameter_cm(REAR), 2 * math.hypot(50 + 25, 32.5), delta=1)

    def test_a_spec_sheet_turning_diameter_calibrates_the_footprint(self):
        # Real chairs have rounded corners; the spec-sheet turning diameter trims the rectangle
        # until its pivot circle matches, instead of assuming square corners (the worst case).
        spec = Chair(70, 110, name="power", axle_offset_cm=0, turning_diameter_cm=115)
        self.assertAlmostEqual(pivot_diameter_cm(spec), 115, delta=1)
        self.assertLess(pivot_diameter_cm(spec), pivot_diameter_cm(MID))
        # it turns around in a square room the size of its turning circle, as the spec promises
        self.assertTrue(reached(room(up5(115) + CELL_CM), spec))
        # and never below the room any rigid body needs (its widest diagonal extent at 45 degrees)
        self.assertFalse(reached(room(80), spec))

    def test_a_bigger_t_never_hurts(self):
        for chair in (MID, REAR):
            verdicts = [reached(RouteSpec("hammerhead", 95, bar_cm=b), chair) for b in range(100, 240, 20)]
            self.assertEqual(verdicts, sorted(verdicts), chair.name)


if __name__ == "__main__":
    unittest.main()
