"""T10a: the planner returns the actual pose sequence the UI animates.

A reachable trip is a chain of legal moves from start to goal. A jammed trip still
returns the chair's real progress — it drives up to the doorway and stops there,
which is the moment the demo shows.
"""
import unittest

from clearway.twin import two_room_template
from clearway.planner import Chair, plan, drive

_DX = (1, 0, -1, 0)
_DY = (0, 1, 0, -1)


def legal(a, b) -> bool:
    (x1, y1, h1), (x2, y2, h2) = a, b
    if (x1, y1) == (x2, y2):
        return (h2 - h1) % 4 in (1, 3)                    # a 90-degree turn in place
    return h1 == h2 and (x2 - x1, y2 - y1) == (_DX[h1], _DY[h1])  # one step forward


class TestPlanPath(unittest.TestCase):
    def setUp(self):
        self.power = Chair(70, 110, name="power")

    def test_reachable_path_is_legal_start_to_goal(self):
        t = two_room_template(door_cm=90)
        p = plan(t, self.power)
        self.assertTrue(p.reached)
        self.assertEqual(p.poses[0], t.start)
        self.assertEqual(p.poses[-1][:2], t.goal)
        for a, b in zip(p.poses, p.poses[1:]):
            self.assertTrue(legal(a, b), (a, b))

    def test_jammed_path_drives_up_to_the_doorway_and_stops(self):
        t = two_room_template(door_cm=65)
        p = plan(t, self.power)
        self.assertFalse(p.reached)
        self.assertEqual(p.poses[0], t.start)
        x, y, h = p.poses[-1]
        self.assertEqual(h, 0, "it stops facing the door, not turned sideways")
        # front edge pressed against the wall: centre sits half a chair-length from it
        self.assertEqual(t.wall_cols[0] - x, self.power.length_cells // 2)
        for a, b in zip(p.poses, p.poses[1:]):
            self.assertTrue(legal(a, b), (a, b))

    def test_drive_agrees_with_plan(self):
        for door in (65, 70, 90):
            t = two_room_template(door_cm=door)
            self.assertEqual(drive(t, self.power), plan(t, self.power).reached)


if __name__ == "__main__":
    unittest.main()
