"""The O(1) footprint check must agree exactly with checking every cell.

Speed matters (the hosted container has 1/4 vCPU), but the planner's verdict is the
product's ground truth, so the fast path is checked against a brute-force oracle.
"""
import random
import unittest

from clearway.planner import Chair, _Grid, _fits
from clearway.twin import two_room_template


def brute_fits(blocked, W, H, state, wc, lc):
    cx, cy, h = state
    lx, ly = (lc, wc) if h % 2 == 0 else (wc, lc)
    x0, y0 = cx - lx // 2, cy - ly // 2
    if x0 < 0 or y0 < 0 or x0 + lx > W or y0 + ly > H:
        return False
    return not any((x, y) in blocked for x in range(x0, x0 + lx) for y in range(y0, y0 + ly))


class TestGrid(unittest.TestCase):
    def test_fast_fit_matches_brute_force(self):
        rng = random.Random(7)
        for door, step in ((65, 0), (70, 0), (90, 40)):
            t = two_room_template(door_cm=door, threshold_mm=step)
            blocked = t.blocked | t.thresholds
            grid = _Grid(blocked, t.W, t.H)
            for chair in (Chair(70, 110), Chair(64, 100), Chair(40, 60)):
                wc, lc = chair.width_cells, chair.length_cells
                for _ in range(3000):
                    s = (rng.randrange(-5, t.W + 5), rng.randrange(-5, t.H + 5), rng.randrange(4))
                    self.assertEqual(_fits(grid, s, wc, lc), brute_fits(blocked, t.W, t.H, s, wc, lc), (door, chair, s))


if __name__ == "__main__":
    unittest.main()
