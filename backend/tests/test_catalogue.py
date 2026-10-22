"""T4: the Builder may only emit catalogue fixes, and its diff is validated first.

The Builder is an LLM, so its output is untrusted. Nothing applies a fix until it is
checked against the catalogue (known id, valid params, permitted preconditions). This
is the AgentHandshake trust boundary: the checker never sees prose, only structured
ops it can verify.
"""
import unittest

from clearway.rules import DoorSpec
from clearway.catalogue import FixOp, validate, apply, InvalidFix


class TestEffects(unittest.TestCase):
    def test_offset_hinges_adds_5cm(self):
        d = apply(DoorSpec(clear_width_cm=70), [FixOp("offset_hinges")])
        self.assertEqual(d.clear_width_cm, 75)

    def test_widen_frame_sets_target(self):
        d = apply(DoorSpec(clear_width_cm=70), [FixOp("widen_frame", params={"target_cm": 90})])
        self.assertEqual(d.clear_width_cm, 90)

    def test_remove_threshold_zeroes_step(self):
        d = apply(DoorSpec(clear_width_cm=90, threshold_mm=40), [FixOp("remove_threshold")])
        self.assertEqual(d.threshold_mm, 0)


class TestTrustBoundary(unittest.TestCase):
    def test_unknown_fix_is_rejected(self):
        self.assertTrue(validate([FixOp("teleport_chair")]))
        with self.assertRaises(InvalidFix):
            apply(DoorSpec(clear_width_cm=70), [FixOp("teleport_chair")])

    def test_widen_frame_needs_target_in_range(self):
        self.assertTrue(validate([FixOp("widen_frame")]))                      # missing
        self.assertTrue(validate([FixOp("widen_frame", params={"target_cm": 300})]))  # too wide
        self.assertFalse(validate([FixOp("widen_frame", params={"target_cm": 90})]))  # ok

    def test_unexpected_param_is_rejected(self):
        self.assertTrue(validate([FixOp("offset_hinges", params={"nudge": 99})]))

    def test_wall_removal_needs_permission(self):
        self.assertTrue(validate([FixOp("remove_wall_segment")]))              # no context
        self.assertFalse(validate([FixOp("remove_wall_segment")], context={"allow_wall_removal": True}))


if __name__ == "__main__":
    unittest.main()
