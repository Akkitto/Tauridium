"""No publication unless trusted hashes, tag, protections and uploaded bytes agree."""
import copy
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest import mock

import publish_release as publisher
import release_environment


class DraftReleaseApi:
  """Model GitHub's draft-by-ID behavior; by-tag lookup cannot see drafts."""
  repository = "Akkitto/Tauridium"
  tag = "v9.9.9"
  identifier = 417

  def __init__(self, release):
    self.release = copy.deepcopy(release)
    self.final_release = None
    self.after_listings = None
    self.created = False
    self.promoted = False
    self.listing_reads = 0
    self.get_paths = []
    self.calls = []

  def current(self):
    if self.promoted:
      return self.final_release or {**self.release, "draft": False}
    return self.release

  def get(self, path):
    self.get_paths.append(path)
    if path == f"repos/{self.repository}/git/ref/tags/{self.tag}":
      return {"object": {"type": "commit", "sha": "a" * 40}}
    if "/releases/tags/" in path:
      raise SystemExit("404: draft is not a published release")
    if path == f"repos/{self.repository}/releases/{self.identifier}":
      return copy.deepcopy(self.current())
    raise AssertionError(f"Unexpected API read: {path}")

  def gh(self, *arguments):
    self.calls.append(arguments)
    if arguments == ("api", "--paginate", "--slurp", f"repos/{self.repository}/releases?per_page=100"):
      self.listing_reads += 1
      if not self.created:
        return "[]"
      return json.dumps(self.after_listings if self.after_listings is not None else
                        [[{"id": 3, "tag_name": "v1.0.0"}], [{"id": self.identifier, "tag_name": self.tag}]])
    if arguments[:3] == ("release", "create", self.tag):
      self.created = True
      return f"https://github.com/{self.repository}/releases/tag/{self.tag}"
    if arguments == ("api", "--paginate", "--slurp",
                     f"repos/{self.repository}/releases/{self.identifier}/assets?per_page=100"):
      assets = self.current()["assets"]
      return json.dumps([assets[:1], assets[1:]])
    if arguments == ("api", "--method", "PATCH", f"repos/{self.repository}/releases/{self.identifier}",
                     "-F", "draft=false", "-f", "make_latest=true"):
      self.promoted = True
      return json.dumps(self.current())
    raise AssertionError(f"Unexpected GitHub operation: {arguments}")


class ProtectedReleaseTests(unittest.TestCase):
  def setUp(self):
    self.snapshot = {"files": [{"name": "example.zip", "bytes": 10, "sha256": "a" * 64},
                                {"name": "release-notes.md", "bytes": 20, "sha256": "b" * 64}]}
    self.release = {"id": 417, "draft": True, "tag_name": "v9.9.9", "assets": [
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
      self.assertFalse(any(call.args[:3] == ("api", "--method", "PATCH") for call in gh.call_args_list))

  def run_publisher(self, github):
    with (mock.patch.object(publisher.release_snapshot, "verify", return_value=self.snapshot),
          mock.patch.object(publisher.policy, "public_names", return_value={"example.zip"}),
          mock.patch.object(publisher, "api", side_effect=github.get),
          mock.patch.object(publisher, "gh", side_effect=github.gh),
          contextlib.redirect_stdout(io.StringIO()) as output):
      publisher.publish(Path("synthetic"), "9.9.9", "a" * 40, "c" * 64, "Akkitto/Tauridium")
    return output.getvalue()

  def test_draft_discovery_and_promotion_use_same_numeric_identity(self):
    github = DraftReleaseApi(self.release)
    self.assertIn("Published verified Tauridium 9.9.9", self.run_publisher(github))
    self.assertTrue(github.created)
    self.assertTrue(github.promoted)
    self.assertEqual(github.listing_reads, 2)
    self.assertEqual(github.get_paths[1:], ["repos/Akkitto/Tauridium/releases/417"] * 2)
    creation = next(call for call in github.calls if call[:2] == ("release", "create"))
    self.assertEqual(creation[creation.index("--target") + 1], "a" * 40)

  def test_missing_or_duplicate_created_drafts_are_never_promoted(self):
    for listings in ([], [[{"id": 417, "tag_name": "v9.9.9"}, {"id": 418, "tag_name": "v9.9.9"}]]):
      with self.subTest(listings=listings):
        github = DraftReleaseApi(self.release)
        github.after_listings = listings
        with self.assertRaisesRegex(SystemExit, "exactly one"):
          self.run_publisher(github)
        self.assertTrue(github.created)
        self.assertFalse(github.promoted)

  def test_draft_identifiers_must_be_positive_integers(self):
    for identifier in (None, True, False, 0, -1, "417"):
      with self.subTest(identifier=identifier):
        github = DraftReleaseApi(self.release)
        github.after_listings = [[{"id": identifier, "tag_name": "v9.9.9"}]]
        with self.assertRaisesRegex(SystemExit, "numeric identity"):
          self.run_publisher(github)
        self.assertFalse(github.promoted)

  def test_release_id_and_tag_must_match_discovered_draft(self):
    for field, value in (("id", 418), ("id", True), ("tag_name", "v8.8.8")):
      with self.subTest(field=field, value=value):
        github = DraftReleaseApi(self.release)
        github.release[field] = value
        with self.assertRaises(SystemExit):
          self.run_publisher(github)
        self.assertFalse(github.promoted)

  def test_only_boolean_drafts_are_promoted(self):
    for draft in (False, None, 1, "true"):
      with self.subTest(draft=draft):
        github = DraftReleaseApi(self.release)
        github.release["draft"] = draft
        with self.assertRaisesRegex(SystemExit, "private draft"):
          self.run_publisher(github)
        self.assertFalse(github.promoted)

  def test_draft_inventory_and_hash_mismatches_never_promote(self):
    for field, value in (("name", "private.key"), ("size", 11), ("digest", None), ("state", "new")):
      with self.subTest(field=field):
        github = DraftReleaseApi(self.release)
        github.release["assets"][0][field] = value
        with self.assertRaises(SystemExit):
          self.run_publisher(github)
        self.assertFalse(github.promoted)

  def test_final_inventory_is_reverified_after_promotion(self):
    github = DraftReleaseApi(self.release)
    github.final_release = {**copy.deepcopy(self.release), "draft": False}
    github.final_release["assets"][0]["digest"] = "sha256:" + "b" * 64
    with self.assertRaisesRegex(SystemExit, "digest"):
      self.run_publisher(github)
    self.assertTrue(github.promoted)

  def test_final_release_must_be_explicitly_published(self):
    for draft in (True, None, 0):
      with self.subTest(draft=draft):
        github = DraftReleaseApi(self.release)
        github.final_release = {**self.release, "draft": draft}
        with self.assertRaisesRegex(SystemExit, "promotion did not complete"):
          self.run_publisher(github)

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
