"""No publication unless trusted hashes, tag, protections and uploaded bytes agree."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

import publish_release as publisher
import release_environment


class ProtectedReleaseTests(unittest.TestCase):
  def setUp(self):
    self.snapshot = {"files": [{"name": "example.zip", "bytes": 10, "sha256": "a" * 64},
                                {"name": "release-notes.md", "bytes": 20, "sha256": "b" * 64}]}
    self.release = {"draft": True, "tag_name": "v9.9.9", "assets": [
        {"name": "example.zip", "size": 10, "digest": "sha256:" + "a" * 64, "state": "uploaded"}]}

  def test_exact_remote_inventory_requires_hashes_sizes_and_uploaded_state(self):
    publisher.verify_remote_assets(self.release, self.snapshot)
    for field, value in (("name", "private.key"), ("size", 11), ("digest", None), ("state", "new")):
      with self.subTest(field=field):
        altered = copy.deepcopy(self.release)
        altered["assets"][0][field] = value
        with self.assertRaises(SystemExit):
          publisher.verify_remote_assets(altered, self.snapshot)
    self.release["assets"].append(self.release["assets"][0])
    with self.assertRaisesRegex(SystemExit, "duplicate"):
      publisher.verify_remote_assets(self.release, self.snapshot)

  def test_existing_release_and_remote_tag_mismatch_are_never_mutated(self):
    for remote in ({"type": "commit", "sha": "b" * 40}, {"type": "commit", "sha": "a" * 40}):
      with (mock.patch.object(publisher.release_snapshot, "verify", return_value=self.snapshot),
            mock.patch.object(publisher, "api", return_value={"object": remote}),
            mock.patch.object(publisher, "gh", return_value=json.dumps([[{"tag_name": "v9.9.9"}]])) as gh):
        with self.assertRaises(SystemExit):
          publisher.publish(Path("synthetic"), "9.9.9", "a" * 40, "c" * 64, "Akkitto/Tauridium")
        self.assertFalse(any(call.args[:2] == ("release", "create") for call in gh.call_args_list))

  def test_failed_uploaded_digest_never_promotes_the_draft(self):
    altered = copy.deepcopy(self.release)
    altered["assets"][0]["digest"] = "sha256:" + "b" * 64
    with (mock.patch.object(publisher.release_snapshot, "verify", return_value=self.snapshot),
          mock.patch.object(publisher, "api", return_value={"object": {"type": "commit", "sha": "a" * 40}}),
          mock.patch.object(publisher, "remote_release", return_value=altered),
          mock.patch.object(publisher, "gh", return_value="[]") as gh):
      with self.assertRaisesRegex(SystemExit, "digest"):
        publisher.publish(Path("synthetic"), "9.9.9", "a" * 40, "c" * 64, "Akkitto/Tauridium")
      self.assertTrue(any(call.args[:2] == ("release", "create") for call in gh.call_args_list))
      self.assertFalse(any(call.args[:2] == ("release", "edit") for call in gh.call_args_list))

  def test_release_environments_require_existing_review_and_custom_tag_restrictions(self):
    good = {"protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User"}]}],
            "deployment_branch_policy": {"custom_branch_policies": True, "protected_branches": False}}
    release_environment.validate(good, "synthetic")
    for field, value in (("protection_rules", []), ("deployment_branch_policy", None)):
      altered = {**good, field: value}
      with self.assertRaises(SystemExit):
        release_environment.validate(altered, "synthetic")


if __name__ == "__main__":
  unittest.main()
