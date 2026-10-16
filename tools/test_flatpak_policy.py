"""Runtime metadata must satisfy the complete reviewed policy before custody."""
from pathlib import Path
import tempfile
import unittest

import flatpak_policy as policy

METADATA = '''[Application]
name=dev.brani.tauridium
runtime=org.gnome.Platform/x86_64/51
sdk=org.gnome.Sdk/x86_64/51
command=tauridium
[Context]
shared=ipc;network;
sockets=fallback-x11;pulseaudio;wayland;
devices=dri;
[Session Bus Policy]
org.kde.StatusNotifierWatcher=talk
org.freedesktop.secrets=talk
'''
DEBUG = '''[Extension dev.brani.tauridium.Debug]
directory=lib/debug
autodelete=true
no-autodownload=true
[Build]
built-extensions=dev.brani.tauridium.Debug;
'''


class FlatpakPolicyTests(unittest.TestCase):
  def check(self, text, *, rejected=False):
    with tempfile.TemporaryDirectory() as temporary:
      path = Path(temporary) / "metadata"
      path.write_text(text, encoding="utf-8")
      if rejected:
        with self.assertRaisesRegex(SystemExit, "permissions differ") as caught:
          policy.validate_permissions(path)
        self.assertNotIn("synthetic-private-value", str(caught.exception))
      else:
        policy.validate_permissions(path)

  def test_reviewed_architectures_empty_policy_groups_and_real_builder_metadata_pass(self):
    for architecture in ("x86_64", "aarch64"):
      for suffix in ("", DEBUG, DEBUG + "[System Bus Policy]\n[Environment]\n"):
        with self.subTest(architecture=architecture, suffix=suffix):
          self.check(METADATA.replace("x86_64", architecture) + suffix)
    self.check(METADATA.replace("shared=ipc;network;", "shared=network;ipc;"))

  def test_system_bus_permissions_are_not_silently_ignored(self):
    for permission in ("org.freedesktop.NetworkManager=talk", "org.freedesktop.*=own"):
      with self.subTest(permission=permission):
        self.check(METADATA + "[System Bus Policy]\n" + permission + "\n", rejected=True)

  def test_all_new_runtime_environment_requires_review(self):
    for name in ("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS", "LD_PRELOAD", "GTK_MODULES", "GIO_EXTRA_MODULES", "EXAMPLE"):
      with self.subTest(name=name):
        self.check(METADATA + f"[Environment]\n{name}=synthetic-private-value\n", rejected=True)

  def test_unknown_sections_and_application_fields_fail_closed(self):
    for section in ("Runtime", "Instance", "Policy org.example", "Extension org.example.Inject"):
      with self.subTest(section=section):
        self.check(METADATA + f"[{section}]\ndirectory=lib/inject\n", rejected=True)
    self.check(METADATA.replace("command=tauridium", "command=tauridium\nextra-args=synthetic-private-value"), rejected=True)

  def test_runtime_identity_architecture_branch_and_sdk_must_match_reviewed_contract(self):
    for original, replacement in (("name=dev.brani.tauridium", "name=org.example.Evil"),
                                  ("command=tauridium", "command=sh"),
                                  ("org.gnome.Platform/", "org.example.Platform/"),
                                  ("org.gnome.Sdk/x86_64/51", "org.gnome.Sdk/aarch64/51"),
                                  ("/51", "/50"), ("x86_64", "i386"),
                                  ("/51", "/51/extra")):
      with self.subTest(original=original, replacement=replacement):
        self.check(METADATA.replace(original, replacement), rejected=True)

  def test_context_and_session_bus_expansion_are_rejected(self):
    for original, replacement in (("devices=dri;", "devices=all;"),
                                  ("devices=dri;", "devices=dri;\nfilesystems=host;"),
                                  ("sockets=fallback-x11;", "sockets=system-bus;fallback-x11;"),
                                  ("org.freedesktop.secrets=talk", "org.freedesktop.secrets=own"),
                                  ("shared=ipc;network;", "shared=network;")):
      with self.subTest(replacement=replacement):
        self.check(METADATA.replace(original, replacement), rejected=True)

  def test_debug_extension_and_build_metadata_have_explicit_contracts(self):
    for original, replacement in (("directory=lib/debug", "directory=lib/debug\nadd-ld-path=lib"),
                                  ("autodelete=true", "autodelete=false"),
                                  ("built-extensions=dev.brani.tauridium.Debug;", "built-extensions=org.example.Inject;"),
                                  ("no-autodownload=true", "no-autodownload=true\nsubdirectories=true")):
      with self.subTest(replacement=replacement):
        self.check((METADATA + DEBUG).replace(original, replacement), rejected=True)

  def test_missing_sections_defaults_duplicates_and_parser_errors_do_not_pass(self):
    self.check(METADATA.replace("[Context]", "[Unknown]"), rejected=True)
    self.check("[DEFAULT]\nsynthetic-private-value=true\n" + METADATA, rejected=True)
    self.check(METADATA + "[Environment]\nEXAMPLE=one\nEXAMPLE=synthetic-private-value\n", rejected=True)
    self.check(METADATA + "[Environment]\n[Environment]\n", rejected=True)
    self.check(METADATA + "[broken-synthetic-private-value\n", rejected=True)

  def test_missing_oversized_and_invalid_utf8_metadata_fail_closed(self):
    with tempfile.TemporaryDirectory() as temporary:
      path = Path(temporary) / "metadata"
      with self.assertRaisesRegex(SystemExit, "permissions differ"):
        policy.validate_permissions(path)
      for data in (bytes(64 * 1024 + 1), b"\xffsynthetic-private-value"):
        path.write_bytes(data)
        with self.assertRaisesRegex(SystemExit, "permissions differ") as caught:
          policy.validate_permissions(path)
        self.assertNotIn("synthetic-private-value", str(caught.exception))

  def test_symlink_metadata_is_rejected(self):
    with tempfile.TemporaryDirectory() as temporary:
      target, link = Path(temporary) / "target", Path(temporary) / "metadata"
      target.write_text(METADATA, encoding="utf-8")
      try:
        link.symlink_to(target)
      except OSError:
        self.skipTest("Symlink privilege unavailable")
      with self.assertRaisesRegex(SystemExit, "permissions differ"):
        policy.validate_permissions(link)


if __name__ == "__main__":
  unittest.main()
