"""T10b: the HTTP API validates input and never spends credits unless allowed."""
import os
import unittest
from unittest import mock

try:
    from fastapi.testclient import TestClient
except ImportError:  # only a missing fastapi skips; a broken clearway.api must fail
    TestClient = None


@unittest.skipIf(TestClient is None, "fastapi not installed (use: uv run)")
class TestApi(unittest.TestCase):
    def setUp(self):
        from clearway.api import app
        self.client = TestClient(app)

    def test_health(self):
        self.assertEqual(self.client.get("/api/health").json(), {"ok": True})

    def test_offline_run_refuses_then_accepts(self):
        r = self.client.post("/api/run", json={"door_cm": 65, "chair": {"width_cm": 70, "length_cm": 110}})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["verdict"]["accepted"])
        self.assertEqual(d["verdict"]["refused_count"], 1)
        self.assertFalse(d["before"]["plan"]["reached"])
        self.assertTrue(d["after"]["plan"]["reached"])

    def test_out_of_range_input_is_rejected(self):
        self.assertEqual(self.client.post("/api/run", json={"door_cm": 5}).status_code, 422)
        self.assertEqual(self.client.post("/api/run", json={"door_cm": 80, "standard": "XYZ"}).status_code, 422)
        bad_chair = {"door_cm": 80, "chair": {"width_cm": 500, "length_cm": 110}}
        self.assertEqual(self.client.post("/api/run", json=bad_chair).status_code, 422)

    def _brief(self, **over):
        body = {"door_cm": 65, "chair": {"width_cm": 70, "length_cm": 110},
                "fix": [{"fix_id": "widen_frame", "params": {"target_cm": 82}}], "cards": []}
        body.update(over)
        return self.client.post("/api/brief", json=body)

    def test_brief_for_an_audited_fix(self):
        r = self._brief()
        self.assertEqual(r.status_code, 200)
        self.assertIn("82 cm", r.json()["markdown"])

    def test_brief_refuses_a_fix_the_auditor_rejects(self):
        r = self._brief(fix=[{"fix_id": "offset_hinges", "params": {}}])
        self.assertEqual(r.status_code, 409)

    def test_brief_drops_non_http_card_links(self):
        card = {"kind": "price", "subject": "widen_frame", "title": "x", "url": "javascript:alert(1)",
                "price_range": "$1", "price_quote": "pay $1"}
        md = self._brief(cards=[card]).json()["markdown"]
        self.assertNotIn("javascript:", md)

    def test_escalation_brief_when_no_fix(self):
        r = self._brief(fix=[])
        self.assertEqual(r.status_code, 200)
        self.assertIn("contractor", r.json()["markdown"].lower())

    def test_live_brief_is_refused_unless_allowed(self):
        with mock.patch.dict(os.environ, {"CLEARWAY_ALLOW_LIVE": ""}):
            self.assertEqual(self._brief(live=True).status_code, 403)

    def test_live_run_is_refused_unless_allowed(self):
        with mock.patch.dict(os.environ, {"CLEARWAY_ALLOW_LIVE": ""}):
            r = self.client.post("/api/run", json={"door_cm": 65, "live": True})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
