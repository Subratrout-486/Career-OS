#!/usr/bin/env python3
"""Decrypt a Candor Career OS envelope only inside the GitHub runner."""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import aead

VERSION = "career-os-envelope.v1"
MAX_PLAINTEXT_BYTES = 512 * 1024
MAX_ENVELOPE_BYTES = 1024 * 1024


def decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    if len(sys.argv) != 3:
        fail("usage: decrypt_job_envelope.py ENVELOPE OUTPUT_JSON")
    encoded, output_path = sys.argv[1], Path(sys.argv[2])
    run_id = os.environ.get("CONDUCTOR_RUN_ID", "")
    private_key_text = os.environ.get("CAREER_OS_ENVELOPE_PRIVATE_KEY", "")
    if not run_id or not run_id.replace("_", "").replace("-", "").isalnum() or len(run_id) < 8:
        fail("invalid opaque run identifier")
    if not private_key_text:
        fail("missing envelope decryption credential")
    if len(encoded) > MAX_ENVELOPE_BYTES * 2:
        fail("encrypted envelope too large")
    try:
        envelope = json.loads(decode(encoded).decode("utf-8"))
        if envelope.get("version") != VERSION or envelope.get("conductorRunId") != run_id:
            fail("encrypted envelope identity mismatch")
        issued_at = int(envelope["issuedAt"])
        expires_at = int(envelope["expiresAt"])
        now = int(time.time() * 1000)
        if issued_at > now + 60_000 or expires_at <= now or expires_at - issued_at > 60 * 60 * 1000:
            fail("encrypted envelope expired or invalid")
        private_key = serialization.load_pem_private_key(private_key_text.encode("utf-8"), password=None)
        wrapped_key = private_key.decrypt(decode(envelope["wrappedKey"]), padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        aad = f"{VERSION}:{run_id}:{expires_at}".encode("utf-8")
        plaintext = aead.AESGCM(wrapped_key).decrypt(decode(envelope["nonce"]), decode(envelope["ciphertext"]) + decode(envelope["tag"]), aad)
        if len(plaintext) > MAX_PLAINTEXT_BYTES:
            fail("decrypted envelope too large")
        payload = json.loads(plaintext.decode("utf-8"))
        if payload.get("conductorRunId") != run_id or payload.get("expiresAt") != expires_at:
            fail("decrypted envelope identity mismatch")
        if not isinstance(payload.get("job"), dict) or not isinstance(payload.get("profile"), str) or not isinstance(payload.get("sourceUrl"), str):
            fail("decrypted envelope missing required fields")
        output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - runner failure is intentionally generic
        fail(f"encrypted envelope rejected: {type(exc).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
