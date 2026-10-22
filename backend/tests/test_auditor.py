"""T5: the Auditor refuses a fix that does not clear BOTH independent checks.

This is the product's spine and the D3 kill-switch deliverable: a genuine refusal.
The Auditor sees only the original measurement, the Builder's structured diff, and the
chair. It rebuilds the twin from those raw numbers (never a maker-supplied artifact),
re-drives the chair (physics) and re-checks the code (rules). A cheap fix that lets the
chair squeeze through but stays below code is REFUSED.
"""
import unittest

from clearway.rules import DoorSpec
from clearway.catalogue import FixOp
from clearway.planner import Chair
from clearway.auditor import audit


class TestAuditor(unittest.TestCase):
    def setUp(self):
        self.power = Chair(width_cm=70, length_cm=110, name="power")
        self.jamming_door = DoorSpec(clear_width_cm=65)   # original: chair does not fit

    def test_cheap_fix_clears_physics_but_fails_code_is_refused(self):
        r = audit(self.jamming_door, [FixOp("offset_hinges")], self.power)  # 65 -> 70 cm
        self.assertFalse(r.accepted)
        self.assertTrue(r.physics_ok, "70 cm chair squeezes a 70 cm door in the sim")
        self.assertFalse(r.code_ok, "700 mm is below the 815 mm code")
        self.assertIn("404", r.failing_clause)
        self.assertTrue(r.reason.startswith("code fail"))

    def test_real_fix_clears_both_is_accepted(self):
        r = audit(self.jamming_door, [FixOp("widen_frame", params={"target_cm": 90})], self.power)
        self.assertTrue(r.accepted)
        self.assertTrue(r.physics_ok and r.code_ok)
        self.assertEqual(r.after.clear_width_cm, 90)

    def test_noop_fix_is_refused(self):
        r = audit(DoorSpec(clear_width_cm=90, threshold_mm=40), [], self.power)
        self.assertFalse(r.accepted)   # threshold still violates code

    def test_threshold_removal_is_accepted(self):
        chair = Chair(width_cm=70, length_cm=110, caster_climb_mm=20)
        r = audit(DoorSpec(clear_width_cm=90, threshold_mm=40), [FixOp("remove_threshold")], chair)
        self.assertTrue(r.accepted)

    def test_invalid_diff_is_refused_not_applied(self):
        r = audit(self.jamming_door, [FixOp("teleport_chair")], self.power)
        self.assertFalse(r.accepted)
        self.assertIn("invalid fix", r.reason)


if __name__ == "__main__":
    unittest.main()
