"""Route gate: a full run on each route preset produces a genuine refusal, end to end.

The chair is a real one from its published spec (Quantum Q6 Edge 3 Stretto, mid-wheel:
54.6 x 82.6 cm, turning radius 53.3 cm, EASTIN database). The cost-greedy stub proposes
the cheapest width that physically works; it is under the ADA minimum, so the Auditor
refuses it on code; the code-size fix passes both checks.
"""
import unittest

from clearway.catalogue import FixOp, validate
from clearway.orchestrator import run
from clearway.planner import Chair, analyze
from clearway.rules import RouteSpec
from clearway.serialize import run_to_dict
from clearway.twin import twin_for

Q6 = Chair(55, 83, name="Quantum Q6 Edge 3 Stretto", axle_offset_cm=0, turning_diameter_cm=107)
S_HALL = RouteSpec("s_route", 70, legs=(("E", 300), ("S", 200), ("E", 300)))
HAMMERHEAD = RouteSpec("hammerhead", 95, bar_cm=90)


class TestRouteGate(unittest.TestCase):
    def test_s_hallway_cheap_fix_refused_on_code_then_code_fix_accepted(self):
        r = run(S_HALL, Q6)
        self.assertTrue(r.accepted)
        self.assertEqual(r.refused_count, 1)
        refusal = next(e for e in r.ledger if e.action == "refuse")
        self.assertIn("403.5.1", refusal.detail)
        self.assertEqual(r.accepted_fix, [FixOp("widen_corridor", params={"target_cm": 95})])

    def test_hammerhead_cheap_fix_refused_on_code_then_code_fix_accepted(self):
        r = run(HAMMERHEAD, Q6)
        self.assertTrue(r.accepted)
        self.assertEqual(r.refused_count, 1)
        refusal = next(e for e in r.ledger if e.action == "refuse")
        self.assertIn("304.3.2", refusal.detail)
        self.assertEqual(r.accepted_fix, [FixOp("extend_turning_bar", params={"target_cm": 155})])

    def test_route_jams_are_classified_from_the_route(self):
        jam = analyze(twin_for(S_HALL), Q6)
        self.assertEqual(jam.reason, "turn_radius")
        self.assertEqual(jam.measured, 70)
        self.assertEqual(analyze(twin_for(HAMMERHEAD), Q6).reason, "turning_space")

    def test_fixes_only_apply_to_their_kind(self):
        self.assertTrue(validate([FixOp("widen_frame", params={"target_cm": 90})], kind="s_route"))
        self.assertTrue(validate([FixOp("widen_corridor", params={"target_cm": 95})], kind="door"))
        self.assertTrue(validate([FixOp("extend_turning_bar", params={"target_cm": 155})], kind="s_route"))
        self.assertFalse(validate([FixOp("widen_corridor", params={"target_cm": 95})], kind="hammerhead"))

    def test_route_payload_carries_what_the_ui_needs(self):
        d = run_to_dict(run(S_HALL, Q6), Q6)
        twin = d["before"]["twin"]
        self.assertEqual((twin["kind"], twin["headings"], twin["width_cm"]), ("s_route", 16, 70))
        self.assertTrue(d["after"]["plan"]["reached"])
        self.assertEqual(d["chair"]["axle_offset_cm"], 0)


if __name__ == "__main__":
    unittest.main()
