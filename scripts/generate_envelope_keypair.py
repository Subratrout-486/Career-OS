#!/usr/bin/env python3
"""Generate the Career OS envelope RSA key pair without uploading or printing secrets.

The private output must be outside the repository and is intended for manual entry
into the GitHub Actions secret named CAREER_OS_ENVELOPE_PRIVATE_KEY.
"""
from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def secure_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    public_path = args.public_output.resolve()
    private_path = args.private_output.resolve()
    repo_path = Path.cwd().resolve()
    if public_path == private_path:
        raise SystemExit("public and private output paths must differ")
    if private_path.is_relative_to(repo_path):
        raise SystemExit("private output must be outside the repository working directory")
    if public_path.exists() or private_path.exists():
        raise SystemExit("refusing to overwrite an existing key file")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_bytes = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    secure_write(private_path, private_bytes, stat.S_IRUSR | stat.S_IWUSR)
    try:
        secure_write(public_path, public_bytes, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    except Exception:
        private_path.unlink(missing_ok=True)
        raise
    os.chmod(private_path, stat.S_IRUSR | stat.S_IWUSR)
    os.chmod(public_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    print("KEYPAIR_GENERATED")
    print(f"PUBLIC_KEY_PATH={public_path}")
    print("PRIVATE_KEY_PATH=created; keep outside the repository and never print or commit it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
