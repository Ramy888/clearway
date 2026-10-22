"""T1: a footprint-aware wheelchair either clears a doorway or it jams.

This is the kill-switch spike: the whole product rests on the planner telling the
truth about where a chair physically cannot go. A door wider than the chair must be
passable; a door narrower than the chair must jam with reason "clear_width".
"""
import unittest

from clearway.twin import two_room_template
from clearway.planner import Chair, analyze


class TestFootprintPlanner(unittest.TestCase):
    def setUp(self):
        # A common power wheelchair: 70 cm wide, 110 cm long.
        self.power = Chair(width_cm=70, length_cm=110, name="power")

    def test_wide_door_is_passable(self):
        jam = analyze(two_room_template(door_cm=90), self.power)
        self.assertIsNone(jam, "a 90 cm door should be passable by a 70 cm chair")

    def test_narrow_door_jams_on_clear_width(self):
        jam = analyze(two_room_template(door_cm=65), self.power)
        self.assertIsNotNone(jam, "a 65 cm door must jam a 70 cm chair")
        self.assertEqual(jam.reason, "clear_width")
        self.assertEqual(jam.measured_cm, 65)

    def test_door_equal_to_chair_width_just_passes(self):
        jam = analyze(two_room_template(door_cm=70), self.power)
        self.assertIsNone(jam, "a door equal to the chair width should just pass")


if __name__ == "__main__":
    unittest.main()
