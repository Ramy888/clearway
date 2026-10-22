"""T6 / D3 gate: a full run drives, refuses the cheap fix, then accepts a real one.

The maker here is a deterministic cost-greedy stub (no LLM yet) so the whole pipeline
is free to run and test. It proves the D3 kill-switch deliverable end to end: a chair
driving + a genuine refusal + a per-agent ledger, with a countable "refused N" number.
"""
import unittest

from clearway.rules import DoorSpec
from clearway.planner import Chair
from clearway.orchestrator import run


class TestRun(unittest.TestCase):
    def setUp(self):
        self.power = Chair(width_cm=70, length_cm=110, name="power")

    def test_d3_refuses_cheap_then_accepts_real(self):
        r = run(DoorSpec(clear_width_cm=65), self.power)
        self.assertTrue(r.accepted)
        self.assertEqual(r.refused_count, 1)
        self.assertEqual(r.accepted_fix[0].fix_id, "widen_frame")
        actions = [(e.agent, e.action) for e in r.ledger]
        self.assertIn(("Auditor", "refuse"), actions)
        self.assertIn(("Auditor", "accept"), actions)
        # the refusal comes before the acceptance
        self.assertLess(actions.index(("Auditor", "refuse")), actions.index(("Auditor", "accept")))

    def test_escalation_is_an_honest_outcome(self):
        r = run(DoorSpec(clear_width_cm=65), self.power, max_rounds=1)  # only the cheap fix tried
        self.assertFalse(r.accepted)
        self.assertTrue(r.escalated)
        self.assertEqual(r.refused_count, 1)
        self.assertEqual(r.ledger[-1].agent, "Scribe")

    def test_already_accessible_needs_no_fix(self):
        r = run(DoorSpec(clear_width_cm=90), self.power)
        self.assertTrue(r.accepted)
        self.assertEqual(r.refused_count, 0)
        self.assertEqual(r.accepted_fix, [])


if __name__ == "__main__":
    unittest.main()
