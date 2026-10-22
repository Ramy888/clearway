"""Route-mode planner spike: 8 headings, reverse, and a goal heading (turn around, then leave).

The hammerhead (ADA 304.3.2 T-shaped turning space) only means something if turning has a
cost: with 8 headings a 180-degree turn is four 45-degree steps, and every intermediate
footprint must fit. Door twins keep their 4-heading behaviour.
"""
import math
import unittest

from clearway.planner import Chair, _Grid, _fits8, _mask_runs, plan
from clearway.twin import Twin

CELL = 5


def open_twin(rects, W, H, start, goal, goal_heading=None):
    """Everything blocked except the given open rectangles (x, y, w, h) in cells."""
    open_cells = {(x, y) for (rx, ry, rw, rh) in rects for x in range(rx, rx + rw) for y in range(ry, ry + rh)}
    blocked = frozenset((x, y) for x in range(W) for y in range(H) if (x, y) not in open_cells)
    return Twin(blocked=blocked, W=W, H=H, start=start, goal=goal, door_cm=0,
                headings=8, goal_heading=goal_heading)


def hammerhead(arm_cm, bar_cm, corridor_cells=60):
    """A dead-end corridor `arm_cm` wide ending in a T whose bar is `bar_cm` long."""
    a, b = round(arm_cm / CELL), round(bar_cm / CELL)
    W, H = b + 10, corridor_cells + a + 10
    stem_x = 5 + (b - a) // 2
    bar = (5, 5, b, a)                                  # the top of the T
    stem = (stem_x, 5 + a, a, corridor_cells)           # the corridor leading in
    cx = stem_x + a // 2
    start_y = 5 + a + corridor_cells - 15
    return open_twin([bar, stem], W, H, start=(cx, start_y, 6), goal=(cx, start_y), goal_heading=2)


class TestTurnaround(unittest.TestCase):
    def setUp(self):
        self.power = Chair(70, 110, name="power")

    def test_turns_around_in_an_open_room(self):
        t = open_twin([(5, 5, 60, 60)], 70, 70, start=(35, 35, 0), goal=(35, 35), goal_heading=4)
        p = plan(t, self.power)
        self.assertTrue(p.reached)
        self.assertEqual(p.poses[-1], (35, 35, 4))

    def test_cannot_turn_around_in_a_plain_corridor(self):
        t = open_twin([(5, 5, 19, 120)], 30, 130, start=(14, 80, 6), goal=(14, 80), goal_heading=2)
        self.assertFalse(plan(t, self.power).reached)

    def test_ada_size_hammerhead_lets_the_chair_turn_around(self):
        self.assertTrue(plan(hammerhead(arm_cm=95, bar_cm=155), self.power).reached)

    def test_undersized_hammerhead_does_not(self):
        self.assertFalse(plan(hammerhead(arm_cm=80, bar_cm=110), self.power).reached)


class TestDiagonalFootprint(unittest.TestCase):
    def test_rows_cover_exactly_the_rotated_rectangle(self):
        wc, lc = 14, 22
        for h in (1, 3, 5, 7):
            ang = math.radians(45 * h)
            ux, uy, vx, vy = math.cos(ang), math.sin(ang), -math.sin(ang), math.cos(ang)
            want = {(dx, dy) for dx in range(-20, 21) for dy in range(-20, 21)
                    if abs((dx + .5) * ux + (dy + .5) * uy) < lc / 2 - 1e-9
                    and abs((dx + .5) * vx + (dy + .5) * vy) < wc / 2 - 1e-9}
            got = {(dx0 + i, dy) for dy, dx0, w in _mask_runs(wc, lc, h) for i in range(w)}
            self.assertEqual(got, want)

    def test_fast_diagonal_fit_matches_brute_force(self):
        blocked = frozenset({(30, y) for y in range(60)} | {(x, 30) for x in range(60)})
        grid = _Grid(blocked, 60, 60)
        for h in (1, 3, 5, 7):
            cells = {(dx0 + i, dy) for dy, dx0, w in _mask_runs(14, 22, h) for i in range(w)}
            for cx in range(5, 55, 3):
                for cy in range(5, 55, 3):
                    brute = all(0 <= cx + dx < 60 and 0 <= cy + dy < 60 and (cx + dx, cy + dy) not in blocked
                                for dx, dy in cells)
                    self.assertEqual(_fits8(grid, (cx, cy, h), 14, 22), brute)


if __name__ == "__main__":
    unittest.main()
