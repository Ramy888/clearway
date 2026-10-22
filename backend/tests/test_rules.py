"""T3: the standards rule engine decides CODE compliance, independent of the chair.

This is the checker that cannot be talked into anything: the thresholds (ADA 404 /
EN 17210) live here as numbers in code, never in a prompt or a Tavily result. A door
a narrow manual chair physically fits can still FAIL code because a power chair or a
future occupant would not — which is exactly why the Auditor can refuse a cheap fix.
"""
import unittest

from clearway.rules import DoorSpec, evaluate, complies, RULE_PACK_VERSION


class TestClearWidthRule(unittest.TestCase):
    def test_narrow_door_fails_ada(self):
        f = {x.rule_id: x for x in evaluate(DoorSpec(clear_width_cm=70))}
        self.assertFalse(f["clear_width"].passed)
        self.assertEqual(f["clear_width"].required_mm, 815)
        self.assertEqual(f["clear_width"].measured_mm, 700)
        self.assertIn("404", f["clear_width"].clause)

    def test_offset_hinge_width_still_fails_ada(self):
        # The crux refusal: 75 cm clears a slim manual chair but is below the 815 mm code.
        self.assertFalse(complies(DoorSpec(clear_width_cm=75)))

    def test_wide_door_passes_ada(self):
        self.assertTrue(complies(DoorSpec(clear_width_cm=90)))


class TestThresholdAndStandard(unittest.TestCase):
    def test_high_threshold_fails(self):
        self.assertFalse(complies(DoorSpec(clear_width_cm=90, threshold_mm=40)))

    def test_flush_threshold_passes(self):
        self.assertTrue(complies(DoorSpec(clear_width_cm=90, threshold_mm=10)))

    def test_en_standard_is_stricter_on_width(self):
        self.assertFalse(complies(DoorSpec(clear_width_cm=84), standard="EN17210"))
        self.assertTrue(complies(DoorSpec(clear_width_cm=86), standard="EN17210"))

    def test_ada_turning_circle_is_1525_mm(self):
        # ADA 304.3.1: 60 inch (1525 mm) diameter, checked against access-board.gov text.
        f = {x.rule_id: x for x in evaluate(DoorSpec(clear_width_cm=90, turning_diameter_cm=150))}
        self.assertFalse(f["turning"].passed)
        self.assertEqual(f["turning"].required_mm, 1525)
        self.assertIn("304.3", f["turning"].clause)
        self.assertTrue(complies(DoorSpec(clear_width_cm=90, turning_diameter_cm=155)))

    def test_rule_pack_is_versioned(self):
        self.assertTrue(RULE_PACK_VERSION)


if __name__ == "__main__":
    unittest.main()
