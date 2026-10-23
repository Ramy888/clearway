"""Car mode: a side-entry van parks nose-in at home and deploys its ramp.

Physics (the van's own kinematics, then a clear strip beside it for the ramp and the chair rolling
off it) and ADA 502 (van space + access aisle) are independent checkers that can disagree.
"""
import time
import unittest

from clearway.auditor import audit
from clearway.catalogue import FixOp, validate
from clearway.kinematics import SIENNA, plan_route
from clearway.orchestrator import run
from clearway.planner import Chair, analyze, plan
from clearway.presets import Q6
from clearway.rules import RouteSpec, evaluate
from clearway.twin import twin_for, validate_route

BAY = RouteSpec("driveway", 350)
GAP = 350 - 30 - SIENNA.width_cm                 # parked 30 cm off the driver's wall
NEED = SIENNA.ramp_length_cm + Q6.length_cm      # the ramp, then the chair rolls clear of it


class TestDrivewayPhysics(unittest.TestCase):
    def test_the_van_drives_in_from_the_street_and_parks_nose_in(self):
        t = time.perf_counter()
        p = plan_route(twin_for(BAY), SIENNA)
        self.assertTrue(p.reached)
        self.assertLess(time.perf_counter() - t, 5.0)

    def test_in_a_350_cm_bay_the_ramp_jams_with_the_measured_gap(self):
        jam = analyze(twin_for(BAY), Q6)
        self.assertEqual(jam.reason, "ramp")
        self.assertEqual((jam.measured, jam.required), (GAP, NEED))
        self.assertFalse(plan(twin_for(BAY), Q6).reached)

    def test_a_bay_just_wide_enough_for_ramp_and_chair_passes_physics(self):
        just = 30 + SIENNA.width_cm + NEED + 5
        self.assertTrue(plan(twin_for(RouteSpec("driveway", just)), Q6).reached)
        self.assertFalse(plan(twin_for(RouteSpec("driveway", just - 10)), Q6).reached)

    def test_a_chair_wider_than_the_ramp_cannot_use_it(self):
        wide = Chair(80, 110, name="wide")
        self.assertEqual(analyze(twin_for(RouteSpec("driveway", 600)), wide).reason, "ramp_width")


class TestDrivewayCode(unittest.TestCase):
    def test_ada_502_van_space_plus_aisle(self):
        f = evaluate(RouteSpec("driveway", 485))[0]
        self.assertEqual((f.clause, f.required_mm, f.passed), ("ADA 502.2", 4875, False))
        self.assertTrue(evaluate(RouteSpec("driveway", 490))[0].passed)

    def test_the_physics_minimum_is_refused_and_the_code_size_accepted(self):
        physics_min = 30 + SIENNA.width_cm + NEED + 5
        refused = audit(BAY, [FixOp("widen_bay", params={"target_cm": physics_min})], Q6)
        self.assertTrue(refused.physics_ok)
        self.assertFalse(refused.accepted)
        self.assertEqual(refused.failing_clause, "ADA 502.2")
        self.assertTrue(audit(BAY, [FixOp("widen_bay", params={"target_cm": 490})], Q6).accepted)

    def test_full_run_refuses_one_then_accepts(self):
        r = run(BAY, Q6)
        self.assertTrue(r.accepted)
        self.assertEqual(r.refused_count, 1)
        self.assertEqual(r.accepted_fix[0].params, {"target_cm": 490})

    def test_no_catalogue_fix_widens_a_ramp_so_a_too_wide_chair_escalates(self):
        r = run(RouteSpec("driveway", 600), Chair(80, 110, name="wide"))
        self.assertTrue(r.escalated)


class TestTrustBoundary(unittest.TestCase):
    def test_bay_and_hallway_fixes_stay_in_their_lane(self):
        self.assertEqual(validate([FixOp("widen_bay", params={"target_cm": 490})], kind="driveway"), [])
        self.assertTrue(validate([FixOp("widen_bay", params={"target_cm": 490})], kind="s_route"))
        self.assertTrue(validate([FixOp("widen_corridor", params={"target_cm": 490})], kind="driveway"))

    def test_driveway_specs_are_validated(self):
        self.assertEqual(validate_route(BAY), [])
        self.assertTrue(validate_route(RouteSpec("driveway", 300)))   # needs a multi-point turn
        self.assertTrue(validate_route(RouteSpec("driveway", 300, legs=(("E", 300),))))


if __name__ == "__main__":
    unittest.main()
