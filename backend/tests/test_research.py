"""T9: Tavily evidence cards — cited, linked, and kept away from the decision.

Clause and price cards are display evidence for the ledger/UI. A price shown is the
text of a cited page (with its URL), never a model's number, and no card ever feeds a
threshold or the Auditor. HTTP is injected, so no Tavily credits are spent here.
"""
import os
import unittest
from unittest import mock

from clearway.research import Card, clause_card, price_card, search, TavilyResearch, ResearchError
from clearway.orchestrator import run
from clearway.planner import Chair
from clearway.rules import DoorSpec


def fake_post(results):
    def post(payload, key):
        return {"results": results}
    return post


ADA = [{"title": "ADA 404.2.3 Clear Width", "url": "https://www.access-board.gov/ada/#ada-404",
        "content": "Door openings shall provide a clear width of 32 inches (815 mm) minimum."}]


class TestCards(unittest.TestCase):
    def test_clause_card_is_cited(self):
        c = clause_card("ADA 404.2.3", post=fake_post(ADA))
        self.assertEqual(c.kind, "clause")
        self.assertTrue(c.url.startswith("https://"))
        self.assertIn("clear width", c.snippet)

    def test_cards_carry_no_threshold_field(self):
        self.assertNotIn("threshold", Card.__dataclass_fields__)
        self.assertNotIn("required_mm", Card.__dataclass_fields__)

    def test_price_card_prefers_a_result_that_states_a_price(self):
        results = [
            {"title": "Hinges explained", "url": "https://a.example", "content": "Offset hinges swing the door clear."},
            {"title": "Cairo handyman prices", "url": "https://b.example",
             "content": "Installing offset hinges costs EGP 900–1,400 including labour."},
        ]
        c = price_card("offset_hinges", post=fake_post(results))
        self.assertEqual(c.url, "https://b.example")
        self.assertEqual(c.price_range, "EGP 900–1,400")

    def test_price_card_without_a_stated_price_shows_none(self):
        c = price_card("reverse_swing", post=fake_post([
            {"title": "Reversing a door swing", "url": "https://c.example", "content": "Call for a quote."}]))
        self.assertIsNone(c.price_range)
        self.assertEqual(c.url, "https://c.example")

    def test_price_comes_from_the_cost_sentence_not_the_first_number(self):
        # Seen live: the first figure was a whole-renovation range, not the per-door cost.
        live = {"title": "Widening a Doorway: Cost, Design, and Accessibility Guide",
                "url": "https://www.blockrenovation.com/guides/widening-a-doorway",
                "content": "Doorways need 32 inches of clear width; accessible routes need 36. "
                           "$30,000 to $40,000 range. Most homeowners pay $600 to $2,000, with a"}
        c = price_card("widen_frame", post=fake_post([live]))
        self.assertEqual(c.price_range, "$600 to $2,000")
        self.assertIn("homeowners pay", c.price_quote)

    def test_a_stated_range_beats_a_single_worst_case_figure(self):
        # Seen live: "$5,000" (a structural worst case) was shown instead of the page's range.
        live = {"title": "Widening a Doorway for Aging in Place | Aging Safe at Home",
                "url": "https://agingsafehome.com/widening-doorway-for-aging-in-place",
                "content": "As a contractor, widening a doorway for wheelchair access is often the first thing "
                           "families ask me about. They assume it's a simple Saturday afternoon job. I wish that "
                           "were true. Let's walk through why widening that “simple 6 inches” can go from a "
                           "$1,000 retrofit to a $5,000 “structural” job. If you find yourself in Scenario B "
                           "and the $5,000 price tag isn't in the budget, don't give up on home accessibility."}
        c = price_card("widen_frame", post=fake_post([live]))
        self.assertEqual(c.price_range, "$1,000 to $5,000")
        self.assertIn("$1,000 retrofit to a $5,000", c.price_quote)

    def test_irrelevant_page_with_a_price_is_ignored(self):
        # Seen live: a cost-of-living page surfaced "$798" for widen_frame.
        junk = {"title": "Cost of Living in San Francisco", "url": "https://junk.example",
                "content": "Rent $4110 vs $798 in Suzhou"}
        good = {"title": "Widening a doorway", "url": "https://good.example",
                "content": "Widening an interior door frame is a common accessibility job."}
        c = price_card("widen_frame", post=fake_post([junk, good]))
        self.assertEqual(c.url, "https://good.example")
        self.assertIsNone(c.price_range)
        self.assertIsNone(price_card("widen_frame", post=fake_post([junk])))

    def test_missing_key_raises(self):
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
            with self.assertRaises(ResearchError):
                search("anything")


class TestResearchInTheRun(unittest.TestCase):
    def test_cards_annotate_ledger_but_never_change_the_verdict(self):
        chair = Chair(70, 110, name="power")
        plain = run(DoorSpec(clear_width_cm=65), chair)
        cited = run(DoorSpec(clear_width_cm=65), chair, research=TavilyResearch(post=fake_post(ADA)))
        self.assertEqual((plain.accepted, plain.refused_count), (cited.accepted, cited.refused_count))
        inspector = next(e for e in cited.ledger if e.agent == "Inspector")
        self.assertEqual(inspector.card.kind, "clause")
        proposals = [e for e in cited.ledger if e.action == "propose"]
        self.assertTrue(all(e.card is not None and e.card.kind == "price" for e in proposals))

    def test_research_failure_degrades_to_no_card(self):
        def boom(payload, key):
            raise ResearchError("HTTP 432: out of credits")
        r = run(DoorSpec(clear_width_cm=65), Chair(70, 110), research=TavilyResearch(post=boom))
        self.assertTrue(r.accepted)
        self.assertIsNone(next(e for e in r.ledger if e.agent == "Inspector").card)


if __name__ == "__main__":
    unittest.main()
