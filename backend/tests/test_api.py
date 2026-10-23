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
        from clearway import api
        from clearway.limits import DailyBudget, RateLimiter
        self.api = api
        # fresh, generous limits per test so tests never throttle each other
        for name, value in (("RUN_LIMIT", RateLimiter(1000, 600)), ("LIVE_LIMIT", RateLimiter(1000, 600)),
                            ("LIVE_BUDGET", DailyBudget(1000))):
            patcher = mock.patch.object(api, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(api.app)

    def test_built_ui_is_served_and_api_still_wins(self):
        import pathlib
        import tempfile
        from fastapi import FastAPI
        from clearway.api import mount_web
        dist = pathlib.Path(tempfile.mkdtemp())
        (dist / "index.html").write_text("<title>CLEARWAY</title>")
        app = FastAPI()

        @app.get("/api/health")
        def health():
            return {"ok": True}
        mount_web(app, dist)
        c = TestClient(app)
        self.assertIn("CLEARWAY", c.get("/").text)
        self.assertEqual(c.get("/api/health").json(), {"ok": True})
        mount_web(FastAPI(), dist / "missing")   # no build yet: a no-op, not a crash

    def test_health(self):
        with mock.patch.dict(os.environ, {"CLEARWAY_ALLOW_LIVE": ""}):
            d = self.client.get("/api/health").json()
        self.assertTrue(d["ok"])
        self.assertFalse(d["live"])
        self.assertIn("live_runs_left_today", d)

    def test_runs_are_rate_limited_per_client(self):
        from clearway.limits import RateLimiter
        with mock.patch.object(self.api, "RUN_LIMIT", RateLimiter(2, 600)):
            body = {"door_cm": 90}
            self.assertEqual(self.client.post("/api/run", json=body).status_code, 200)
            self.assertEqual(self.client.post("/api/run", json=body).status_code, 200)
            r = self.client.post("/api/run", json=body)
        self.assertEqual(r.status_code, 429)
        self.assertIn("retry-after", r.headers)

    def test_spoofed_forwarded_for_does_not_dodge_the_limit(self):
        from clearway.limits import RateLimiter
        with mock.patch.object(self.api, "RUN_LIMIT", RateLimiter(1, 600)):
            self.client.post("/api/run", json={"door_cm": 90}, headers={"X-Forwarded-For": "1.1.1.1"})
            r = self.client.post("/api/run", json={"door_cm": 90}, headers={"X-Forwarded-For": "2.2.2.2"})
        self.assertEqual(r.status_code, 429)

    def test_daily_live_budget_stops_spend_before_any_model_call(self):
        from clearway.limits import DailyBudget

        def no_spend(*a, **kw):
            raise AssertionError("a model was called despite an exhausted budget")
        with mock.patch.dict(os.environ, {"CLEARWAY_ALLOW_LIVE": "1"}), \
                mock.patch.object(self.api, "LIVE_BUDGET", DailyBudget(0)), \
                mock.patch("clearway.llm.chat", no_spend):
            r = self.client.post("/api/run", json={"door_cm": 65, "live": True})
        self.assertEqual(r.status_code, 429)
        self.assertIn("budget", r.json()["detail"])

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

    Q6 = {"width_cm": 55, "length_cm": 83, "name": "Quantum Q6 Edge 3 Stretto",
          "axle_offset_cm": 0, "turning_diameter_cm": 107}
    S70 = {"kind": "s_route", "width_cm": 70, "legs": [["E", 300], ["S", 200], ["E", 300]]}

    def test_route_run_refuses_then_accepts(self):
        r = self.client.post("/api/run", json={"route": self.S70, "chair": self.Q6})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["verdict"]["refused_count"], 1)
        self.assertEqual(d["before"]["twin"]["kind"], "s_route")

    def test_exactly_one_of_door_or_route(self):
        self.assertEqual(self.client.post("/api/run", json={"chair": self.Q6}).status_code, 422)
        both = {"door_cm": 80, "route": self.S70, "chair": self.Q6}
        self.assertEqual(self.client.post("/api/run", json=both).status_code, 422)

    def test_invalid_routes_are_rejected_at_the_boundary(self):
        bad = [
            {"kind": "s_route", "width_cm": 90, "legs": [["E", 300], ["S", 200], ["W", 300]]},   # U-turn
            {"kind": "s_route", "width_cm": 90, "legs": [["E", 300], ["E", 200]]},               # no turn
            {"kind": "s_route", "width_cm": 90, "legs": [["E", 300]] * 2 + [["S", 100]] * 6},    # too many
            {"kind": "s_route", "width_cm": 90, "legs": [["X", 300]]},                           # bad dir
            {"kind": "hammerhead", "width_cm": 95, "bar_cm": 60},                                # bar < arms
        ]
        for route in bad:
            self.assertEqual(self.client.post("/api/run", json={"route": route}).status_code, 422, route)

    def test_driveway_run_and_its_boundaries(self):
        r = self.client.post("/api/run", json={"route": {"kind": "driveway", "width_cm": 350}, "chair": self.Q6})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["verdict"]["accepted_fix"][0]["params"], {"target_cm": 490})
        for route in ({"kind": "driveway", "width_cm": 300},                  # needs a multi-point turn
                      {"kind": "s_route", "width_cm": 300, "legs": [["E", 300]]}):   # hallways stay <= 200
            self.assertEqual(self.client.post("/api/run", json={"route": route}).status_code, 422, route)

    def test_routes_are_ada_only(self):
        r = self.client.post("/api/run", json={"route": self.S70, "standard": "EN17210"})
        self.assertEqual(r.status_code, 422)

    def test_brief_for_a_route_fix_and_kind_mismatch(self):
        ok = {"route": self.S70, "chair": self.Q6, "fix": [{"fix_id": "widen_corridor", "params": {"target_cm": 95}}]}
        r = self.client.post("/api/brief", json=ok)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("95 cm", r.json()["markdown"])
        wrong = dict(ok, fix=[{"fix_id": "widen_frame", "params": {"target_cm": 95}}])
        self.assertEqual(self.client.post("/api/brief", json=wrong).status_code, 409)

    def test_live_must_be_a_real_boolean(self):
        # lax coercion would turn "yes"/1 into True, which a proxy counting only `true` would miss
        for value in ("yes", 1, "true"):
            self.assertEqual(self.client.post("/api/run", json={"door_cm": 65, "live": value}).status_code, 422)
            self.assertEqual(self._brief(live=value).status_code, 422)

    def test_live_run_is_refused_unless_allowed(self):
        with mock.patch.dict(os.environ, {"CLEARWAY_ALLOW_LIVE": ""}):
            r = self.client.post("/api/run", json={"door_cm": 65, "live": True})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
