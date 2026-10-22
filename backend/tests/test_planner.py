"""T1/T2: a footprint-aware wheelchair either clears the route or it jams.

The kill-switch spike: the product rests on the planner telling the truth about where
a chair physically cannot go, and why. A door wider than the chair is passable; a
narrower one jams on clear_width; a wide door with a high threshold jams on threshold
unless the chair's casters can climb it.
"""
import unittest

from clearway.twin import two_room_template
from clearway.planner import Chair, analyze


class TestClearWidth(unittest.TestCase):
    def setUp(self):
        self.power = Chair(width_cm=70, length_cm=110, name="power")

    def test_wide_door_is_passable(self):
        self.assertIsNone(analyze(two_room_template(door_cm=90), self.power))

    def test_narrow_door_jams_on_clear_width(self):
        jam = analyze(two_room_template(door_cm=65), self.power)
        self.assertIsNotNone(jam)
        self.assertEqual(jam.reason, "clear_width")
        self.assertEqual(jam.measured, 65)
        self.assertEqual(jam.unit, "cm")

    def test_door_equal_to_chair_width_just_passes(self):
        self.assertIsNone(analyze(two_room_template(door_cm=70), self.power))


class TestThreshold(unittest.TestCase):
    def test_high_threshold_jams_a_wide_door(self):
        chair = Chair(width_cm=70, length_cm=110, caster_climb_mm=20)
        jam = analyze(two_room_template(door_cm=90, threshold_mm=40), chair)
        self.assertIsNotNone(jam, "a 40 mm step must stop casters that climb only 20 mm")
        self.assertEqual(jam.reason, "threshold")
        self.assertEqual(jam.measured, 40)
        self.assertEqual(jam.unit, "mm")

    def test_climbable_threshold_passes(self):
        chair = Chair(width_cm=70, length_cm=110, caster_climb_mm=50)
        self.assertIsNone(analyze(two_room_template(door_cm=90, threshold_mm=40), chair))


if __name__ == "__main__":
    unittest.main()
