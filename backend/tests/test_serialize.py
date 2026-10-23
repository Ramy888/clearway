"""T10b: what the UI receives is exact and JSON-safe."""
import json
import unittest

from clearway.twin import two_room_template
from clearway.planner import Chair
from clearway.rules import DoorSpec, RouteSpec
from clearway.presets import Q6
from clearway.orchestrator import run
from clearway.serialize import twin_to_dict, run_to_dict


class TestSerialize(unittest.TestCase):
    def test_wall_rects_cover_exactly_the_blocked_cells(self):
        t = two_room_template(door_cm=65, threshold_mm=20)
        d = twin_to_dict(t)
        cells = {(x + i, y) for x, y, w in d["walls"] for i in range(w)}
        self.assertEqual(cells, set(t.blocked))
        steps = {(x + i, y) for x, y, w in d["thresholds"] for i in range(w)}
        self.assertEqual(steps, set(t.thresholds))
        self.assertEqual((d["W"], d["H"], d["cell_cm"]), (t.W, t.H, t.cell_cm))

    def test_run_payload_is_json_and_has_before_and_after(self):
        r = run(DoorSpec(clear_width_cm=65), Chair(70, 110, name="power"))
        d = json.loads(json.dumps(run_to_dict(r, Chair(70, 110, name="power"))))
        self.assertFalse(d["before"]["plan"]["reached"])
        self.assertTrue(d["after"]["plan"]["reached"])
        self.assertEqual(d["after"]["twin"]["door_cm"], 82)
        self.assertEqual(d["verdict"]["refused_count"], 1)
        self.assertEqual([e["action"] for e in d["ledger"]].count("refuse"), 1)

    def test_escalated_run_has_no_after(self):
        r = run(DoorSpec(clear_width_cm=65), Chair(70, 110), max_rounds=1)
        d = run_to_dict(r, Chair(70, 110))
        self.assertIsNone(d["after"])
        self.assertTrue(d["verdict"]["escalated"])

    def test_driveway_scene_carries_the_van_and_its_ramp(self):
        d = json.loads(json.dumps(run_to_dict(run(RouteSpec("driveway", 350), Q6), Q6)))
        before, after = d["before"], d["after"]
        self.assertEqual(before["vehicle"]["length_cm"], 517)
        self.assertEqual(before["vehicle"]["ramp_length_cm"], 132)
        self.assertFalse(before["ramp"]["clear"])
        self.assertTrue(after["ramp"]["clear"])
        self.assertEqual(len(after["ramp"]["strip"]), 4)
        self.assertNotIn("vehicle", run_to_dict(run(DoorSpec(clear_width_cm=65), Q6), Q6)["before"])


if __name__ == "__main__":
    unittest.main()
