"""T8: the LLM Builder only ever yields catalogue ops, and can't bypass the Auditor.

The model call is injected, so these tests use a fake Nemotron — no credits. The maker
is untrusted: garbage parses to nothing, an invented fix is refused at the trust
boundary, and the refusal reason is fed back so the next proposal can improve.
"""
import json
import unittest

from clearway.builder import parse_ops, make_llm_maker, catalogue_text
from clearway.catalogue import CATALOGUE, FixOp
from clearway.orchestrator import run
from clearway.planner import Chair
from clearway.rules import DoorSpec


def fake_chat(replies, seen=None):
    """A stand-in for llm.chat that returns canned replies in order."""
    it = iter(replies)

    def chat(tier, messages, **kw):
        if seen is not None:
            seen.append((tier, messages))
        return next(it), {}
    return chat


class TestParse(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_ops('{"ops":[{"fix_id":"offset_hinges","params":{}}]}'),
                         [FixOp("offset_hinges")])

    def test_json_wrapped_in_prose(self):
        ops = parse_ops('Cheapest option:\n{"ops":[{"fix_id":"widen_frame","params":{"target_cm":82}}]}\nDone.')
        self.assertEqual(ops, [FixOp("widen_frame", params={"target_cm": 82})])

    def test_garbage_yields_nothing(self):
        self.assertEqual(parse_ops("I think you should widen it a bit."), [])
        self.assertEqual(parse_ops('{"ops": "nope"}'), [])


class TestMaker(unittest.TestCase):
    def test_catalogue_prompt_is_derived_from_catalogue(self):
        text = catalogue_text()
        for fix_id in CATALOGUE:
            self.assertIn(fix_id, text)

    def test_maker_uses_super_and_feeds_back_refusals(self):
        seen = []
        maker = make_llm_maker(chat=fake_chat(['{"ops":[{"fix_id":"offset_hinges"}]}'] * 2, seen))
        history = [([FixOp("offset_hinges")], "code fail: clear width 700 mm vs minimum 815 mm")]
        maker(None, Chair(70, 110), "ADA", history)
        tier, messages = seen[-1]
        self.assertEqual(tier, "super")
        prompt = json.dumps(messages)
        self.assertIn("offset_hinges", prompt)
        self.assertIn("815", prompt)


    def test_a_driveway_is_framed_as_the_van_ramp_and_given_room_to_reason(self):
        # Seen live: on a driveway, Super spent all 2048 tokens reasoning and answered nothing.
        from clearway.planner import analyze
        from clearway.presets import Q6
        from clearway.rules import RouteSpec
        from clearway.twin import twin_for
        calls = []

        def chat(tier, messages, **kw):
            calls.append((messages, kw))
            return '{"ops":[{"fix_id":"widen_bay","params":{"target_cm":490}}]}', {}
        spec = RouteSpec("driveway", 350)
        ops = make_llm_maker(chat=chat)(analyze(twin_for(spec), Q6), Q6, "ADA", [], spec)
        self.assertEqual(ops, [FixOp("widen_bay", params={"target_cm": 490})])
        messages, kw = calls[0]
        self.assertGreaterEqual(kw["max_tokens"], 4096)
        self.assertIn("ramp", messages[0]["content"].lower())      # the system prompt covers this case
        self.assertIn("widen_bay", messages[1]["content"])
        self.assertNotIn("widen_frame", messages[1]["content"])    # only fixes for this kind of space


class TestBoundaryHoldsAgainstTheModel(unittest.TestCase):
    def test_invented_fix_is_refused_then_real_fix_accepted(self):
        maker = make_llm_maker(chat=fake_chat([
            '{"ops":[{"fix_id":"teleport_chair","params":{}}]}',
            '{"ops":[{"fix_id":"widen_frame","params":{"target_cm":90}}]}',
        ]))
        r = run(DoorSpec(clear_width_cm=65), Chair(70, 110, name="power"), maker=maker)
        self.assertTrue(r.accepted)
        self.assertEqual(r.refused_count, 1)
        refusal = next(e for e in r.ledger if e.action == "refuse")
        self.assertIn("invalid fix", refusal.detail)


if __name__ == "__main__":
    unittest.main()
