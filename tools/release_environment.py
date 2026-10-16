"""Read-only preflight: refuse privileged jobs unless owner protections already exist."""
import json
import os
import subprocess


def validate(document: dict, name: str) -> None:
  rules = document.get("protection_rules", [])
  if not any(row.get("type") == "required_reviewers" and row.get("reviewers") for row in rules):
    raise SystemExit(f"error: {name} requires an owner-configured reviewer before release activation")
  # GitHub's read API does not expose the UI administrator-bypass setting.
  # Its owner review is documented; never pretend an absent field proves it.
  branch = document.get("deployment_branch_policy") or {}
  if not branch.get("custom_branch_policies") or branch.get("protected_branches"):
    raise SystemExit(f"error: {name} requires explicit version-tag deployment restrictions")


def main() -> None:
  repository = os.environ.get("GITHUB_REPOSITORY")
  if repository != "Akkitto/Tauridium":
    raise SystemExit("error: protected release workflow only supports the reviewed upstream repository")
  if os.environ.get("RELEASE_KEY_SCOPE_CONFIRMED") != "true":
    raise SystemExit("error: owner must confirm updater keys exist only in release-signing environment secrets")
  for name in ("release-signing", "release-publishing"):
    result = subprocess.run(["gh", "api", f"repos/{repository}/environments/{name}"],
                            capture_output=True, text=True, check=False, timeout=30)
    if result.returncode:
      raise SystemExit(f"error: owner must pre-create protected {name}; refusing implicit environment creation")
    validate(json.loads(result.stdout), name)
    result = subprocess.run(["gh", "api", f"repos/{repository}/environments/{name}/deployment-branch-policies"],
                            capture_output=True, text=True, check=False, timeout=30)
    if result.returncode:
      raise SystemExit("error: unable to verify protected release tag policies")
    policies = json.loads(result.stdout)["branch_policies"]
    if not policies or any(row.get("type") != "tag" or row.get("name") != "v*" for row in policies):
      raise SystemExit(f"error: restrict {name} to the reviewed v* tag policy only")
  print("Existing reviewed release environments verified; no remote settings were changed")


if __name__ == "__main__":
  main()
