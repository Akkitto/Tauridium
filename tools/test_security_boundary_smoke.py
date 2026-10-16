"""A missing heartbeat or argument error cannot masquerade as authorization."""
import unittest
import security_boundary_smoke as smoke


class BoundarySmokeTests(unittest.TestCase):
  def test_missing_duplicate_wrong_origin_and_recipe_leak_reports_fail(self):
    first, second = "http://127.0.0.1:10000", "http://127.0.0.1:10001"
    reports = [{"case": case, "origin": second if case == "cross-origin" else first,
                "url": (second if case == "cross-origin" else first) + "/fixture", "recipe": case != "cross-origin",
                "commands": {name: "authorization-denied" for name in smoke.COMMANDS}}
               for case in ["initial", "cross-origin"] + [f"navigation-{i}" for i in range(len(smoke.NAVIGATIONS))]]
    smoke.validate_reports(reports, first, second)
    for changed in (reports[:-1], reports + [reports[0]], [{**reports[0], "origin": "tauri://localhost"}] + reports[1:],
                    [reports[0], {**reports[1], "recipe": True}] + reports[2:],
                    [{**reports[0], "commands": {name: "WRONG-FAILURE" for name in smoke.COMMANDS}}] + reports[1:]):
      with self.assertRaises(RuntimeError):
        smoke.validate_reports(changed, first, second)
