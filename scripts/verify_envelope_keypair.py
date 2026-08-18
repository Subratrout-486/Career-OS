#!/usr/bin/env python3
"""Verify a local owner-generated key pair without printing secrets or plaintext."""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import aead

VERSION = "career-os-envelope.v1"

def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--decryptor", type=Path, default=Path(__file__).with_name("decrypt_job_envelope.py"))
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    private_path = args.private_key.resolve()
    if private_path.is_relative_to(repo):
        raise SystemExit("private key must be outside the repository")
    private_text = private_path.read_text(encoding="utf-8")
    public_key = serialization.load_pem_public_key(args.public_key.read_bytes())
    run_id = "readiness-test-0001"
    issued_at = int(time.time() * 1000)
    expires_at = issued_at + 300_000
    payload = {"conductorRunId": run_id, "protocolVersion": "v1", "profile": "readiness-test", "job": {"controlled": True}, "sourceUrl": "https://example.invalid/readiness", "applicationUrl": None, "issuedAt": issued_at, "expiresAt": expires_at}
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    key = os.urandom(32)
    nonce = os.urandom(12)
    aad = f"{VERSION}:{run_id}:{expires_at}".encode("utf-8")
    encrypted = aead.AESGCM(key).encrypt(nonce, plaintext, aad)
    envelope = {"version": VERSION, "conductorRunId": run_id, "issuedAt": issued_at, "expiresAt": expires_at, "wrappedKey": b64(public_key.encrypt(key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))), "nonce": b64(nonce), "ciphertext": b64(encrypted[:-16]), "tag": b64(encrypted[-16:])}
    encoded = b64(json.dumps(envelope, separators=(",", ":")).encode("utf-8"))
    with tempfile.TemporaryDirectory(prefix="career-os-envelope-readiness-") as work:
        output = Path(work) / "decrypted.json"
        env = {"CONDUCTOR_RUN_ID": run_id, "CAREER_OS_ENVELOPE_PRIVATE_KEY": private_text}
        result = subprocess.run([sys.executable, str(args.decryptor), encoded, str(output)], env={**os.environ, **env}, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not output.exists():
            raise SystemExit("KEYPAIR_READINESS_FAILED")
        checked = json.loads(output.read_text(encoding="utf-8"))
        if checked.get("conductorRunId") != run_id or checked.get("profile") != "readiness-test" or checked.get("job") != {"controlled": True}:
            raise SystemExit("KEYPAIR_READINESS_FAILED")
    print("KEYPAIR_READINESS_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
