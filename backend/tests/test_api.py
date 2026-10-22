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

    def test_live_run_is_refused_unless_allowed(self):
        with mock.patch.dict(os.environ, {"CLEARWAY_ALLOW_LIVE": ""}):
            r = self.client.post("/api/run", json={"door_cm": 65, "live": True})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
