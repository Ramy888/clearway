"""Each ledger step names what actually did the work (judges asked to see which model does what).

The label comes from what ran, not from the design doc: offline, the Builder is the
deterministic stub and must not be called Nemotron.
"""
import unittest

from clearway.builder import make_llm_maker
from clearway.orchestrator import run
from clearway.planner import Chair
from clearway.research import TavilyResearch
from clearway.rules import DoorSpec
from clearway.serialize import run_to_dict

CHAIR = Chair(70, 110, name="power")
ADA = [{"title": "ADA 404", "url": "https://up.codes/s/doors", "content": "Door clear width 815 mm minimum."}]


def engines(result, agent):
    return [e.engine for e in result.ledger if e.agent == agent]


class TestEngineLabels(unittest.TestCase):
    def test_offline_builder_is_labelled_as_code_not_a_model(self):
        r = run(DoorSpec(clear_width_cm=65), CHAIR)
        for label in engines(r, "Builder"):
            self.assertIn("code", label)
            self.assertNotIn("Nemotron", label)
        self.assertTrue(all("code" in e for e in engines(r, "Auditor")))
        self.assertTrue(all("code" in e for e in engines(r, "Pilot")))

    def test_live_builder_names_the_nemotron_model_and_platform(self):
        maker = make_llm_maker(chat=lambda tier, m, **kw: ('{"ops":[{"fix_id":"widen_frame","params":{"target_cm":90}}]}', {}))
        r = run(DoorSpec(clear_width_cm=65), CHAIR, maker=maker)
        self.assertEqual(engines(r, "Builder"), ["Nemotron 3 Super · Nebius Token Factory"])

    def test_tavily_evidence_is_credited(self):
        r = run(DoorSpec(clear_width_cm=65), CHAIR, research=TavilyResearch(post=lambda p, k: {"results": ADA}))
        self.assertIn("Tavily", engines(r, "Inspector")[0])

    def test_engine_reaches_the_ui_payload(self):
        d = run_to_dict(run(DoorSpec(clear_width_cm=65), CHAIR), CHAIR)
        self.assertTrue(all(e["engine"] for e in d["ledger"]))


if __name__ == "__main__":
    unittest.main()
