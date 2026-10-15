#!/usr/bin/env python3
"""Verify Tauri's encoded Minisign envelope, exact bytes, key and signed version."""
from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAX_ENVELOPE_BYTES = 16 * 1024


def find_minisign() -> str | None:
    executable = shutil.which("minisign")
    if executable:
        return executable
    # A parent Windows terminal may not yet have refreshed its PATH after init.
    if os.name == "nt":
        for variable, suffix in (("USERPROFILE", "scoop/shims/minisign.exe"),
                                 ("LOCALAPPDATA", "Microsoft/WinGet/Links/minisign.exe")):
            base = os.environ.get(variable)
            if base and (candidate := Path(base) / suffix).is_file():
                return str(candidate)
    return None


def require_regular(path: Path) -> None:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
        raise ValueError("Updater inputs must be regular files, never links or reparse points")


def read_small(path: Path) -> bytes:
    require_regular(path)
    with path.open("rb") as stream:
        data = stream.read(MAX_ENVELOPE_BYTES + 1)
    if len(data) > MAX_ENVELOPE_BYTES:
        raise ValueError("Updater signature envelope exceeds its size limit")
    return data


def configured_public_key() -> str:
    config = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    return config["plugins"]["updater"]["pubkey"]


def decode_envelope(encoded: str | bytes) -> bytes:
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise ValueError("Updater signature envelope exceeds its size limit")
    return base64.b64decode(encoded.strip(), validate=True)


def verify(artifact: Path, signature: Path, release_version: str, *, public_key: str | None = None) -> str:
    try:
        require_regular(artifact)
        encoded = read_small(signature).strip()
        decoded = decode_envelope(encoded)
        lines = decoded.splitlines()
        if len(lines) != 4 or not lines[0].startswith(b"untrusted comment: ") or not lines[2].startswith(b"trusted comment: "):
            raise ValueError("Invalid Minisign signature envelope")
        packet = base64.b64decode(lines[1], validate=True)
        global_signature = base64.b64decode(lines[3], validate=True)
        if len(packet) != 74 or packet[:2] != b"ED" or len(global_signature) != 64:
            raise ValueError("A prehashed Minisign signature is required")
        fields = lines[2][len(b"trusted comment: "):].split(b"\t")
        versions = [field[len(b"version:"):] for field in fields if field.startswith(b"version:")]
        if versions != [release_version.encode("utf-8")]:
            raise ValueError("Signature must bind the exact release version in its trusted comment")
        key = decode_envelope(public_key if public_key is not None else configured_public_key())
        key_lines = key.splitlines()
        if len(key_lines) != 2 or not key_lines[0].startswith(b"untrusted comment: "):
            raise ValueError("Invalid configured updater public key")
        key_packet = base64.b64decode(key_lines[1], validate=True)
        if len(key_packet) != 42 or key_packet[:2] != b"Ed" or packet[2:10] != key_packet[2:10]:
            raise ValueError("Signature does not match the configured updater public key")
        executable = find_minisign()
        if executable is None:
            raise ValueError("Minisign is required for signature verification; run just init (on macOS: brew install minisign)")
        # Use the maintained verifier, including the global/trusted-comment signature;
        # do not invent a Python cryptographic implementation or trust a .pub sidecar.
        with tempfile.TemporaryDirectory(prefix="tauridium-signature-") as directory:
            root = Path(directory)
            key_path, signature_path = root / "key.pub", root / "signature.minisig"
            key_path.write_bytes(key)
            signature_path.write_bytes(decoded)
            result = subprocess.run([executable, "-V", "-H", "-p", str(key_path), "-x", str(signature_path), "-m", str(artifact.resolve())],
                                    check=False, capture_output=True, timeout=60)
            if result.returncode:
                raise ValueError("Cryptographic artifact/trusted-comment signature verification failed")
        return encoded.decode("ascii")
    except (OSError, ValueError, KeyError, TypeError, binascii.Error, subprocess.SubprocessError) as error:
        raise SystemExit(f"error: updater signature rejected for {artifact.name}: {error}") from error
