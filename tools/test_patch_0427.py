#!/usr/bin/env python3
"""Regression coverage for Tauridium 0.4.27 service-view workspace API tests."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = (ROOT / "src/lib/api.ts").read_text(encoding="utf-8")
API_TEST = (ROOT / "src/lib/api.test.ts").read_text(encoding="utf-8")


class Patch0427Tests(unittest.TestCase):
  def test_service_view_request_keeps_workspace_context_in_typed_payload(self) -> None:
    self.assertIn("function serviceViewRequest(s: Service, workspaceId: string | null = null)", API)
    self.assertIn("workspaceId,", API)
    self.assertIn("serviceViewRequest(s, workspaceId)", API)
    self.assertIn("serviceViewRequest(s, null)", API)

  def test_default_service_view_expectations_include_null_workspace_context(self) -> None:
    service_tests = API_TEST.split('describe("service view commands"', 1)[1].split('describe("local recipe commands"', 1)[0]
    self.assertIn("workspaceId: null,", service_tests)
    self.assertIn('["show_service", showService]', service_tests)
    self.assertIn('["preload_service", preloadService]', service_tests)

  def test_show_service_test_covers_explicit_workspace_context(self) -> None:
    self.assertIn('await showService(service, "workspace-123");', API_TEST)
    self.assertIn('workspaceId: "workspace-123",', API_TEST)
    self.assertIn('toHaveBeenCalledWith("show_service"', API_TEST)


if __name__ == "__main__":
  unittest.main()
