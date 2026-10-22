"""T13: the contractor brief — code owns every figure, the model only narrates.

Facts (measurements, clauses, the fix, cited prices) are rendered by code. Ultra may
add a plain-language paragraph, but if it contains any number that is not in the
facts it is withheld. The model is injected, so no credits are spent here.
"""
import unittest

from clearway.catalogue import FixOp
from clearway.planner import Chair
from clearway.rules import DoorSpec
from clearway.scribe import approved_brief, escalation_brief

CHAIR = Chair(70, 110, name="power")
BEFORE = DoorSpec(clear_width_cm=65)
FIX = [FixOp("widen_frame", params={"target_cm": 82})]
AFTER = DoorSpec(clear_width_cm=82)
CARDS = [{"kind": "price", "subject": "widen_frame", "title": "Widening a Doorway",
          "url": "https://www.blockrenovation.com/guides/widening-a-doorway",
          "price_range": "$600 to $2,000", "price_quote": "Most homeowners pay $600 to $2,000"}]


def fake(text):
    return lambda tier, messages, **kw: (text, {})


class TestApprovedBrief(unittest.TestCase):
    def test_facts_are_rendered_by_code(self):
        b = approved_brief(BEFORE, AFTER, FIX, CHAIR, "ADA", CARDS)
        md = b["markdown"]
        for fact in ("65 cm", "82 cm", "ADA 404.2.3", "815 mm", "widen frame to 82 cm",
                     "$600 to $2,000", "https://www.blockrenovation.com/guides/widening-a-doorway"):
            self.assertIn(fact, md)
        self.assertEqual(b["narrative_source"], "none")

    def test_supported_narrative_is_included(self):
        prose = "Ask the contractor to widen the bathroom door frame to 82 cm so the power chair clears it."
        b = approved_brief(BEFORE, AFTER, FIX, CHAIR, "ADA", CARDS, chat=fake(prose))
        self.assertIn(prose, b["markdown"])
        self.assertEqual(b["narrative_source"], "ultra")
        self.assertFalse(b["withheld"])

    def test_narrative_with_an_invented_number_is_withheld(self):
        prose = "This usually takes 3 days and costs about $5,000."
        b = approved_brief(BEFORE, AFTER, FIX, CHAIR, "ADA", CARDS, chat=fake(prose))
        self.assertNotIn("$5,000", b["markdown"])
        self.assertTrue(b["withheld"])
        self.assertEqual(b["narrative_source"], "none")

    def test_model_failure_degrades_to_code_only(self):
        from clearway.llm import LLMError

        def boom(tier, messages, **kw):
            raise LLMError("HTTP 503")
        b = approved_brief(BEFORE, AFTER, FIX, CHAIR, "ADA", CARDS, chat=boom)
        self.assertIn("82 cm", b["markdown"])
        self.assertEqual(b["narrative_source"], "none")


class TestEscalationBrief(unittest.TestCase):
    def test_escalation_states_the_gap_and_hands_off(self):
        md = escalation_brief(BEFORE, CHAIR, "ADA")["markdown"]
        self.assertIn("65 cm", md)
        self.assertIn("815 mm", md)
        self.assertIn("contractor", md.lower())


if __name__ == "__main__":
    unittest.main()
