import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


VERSION = "career-os-envelope.v1"


def enc(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class DecryptEnvelopeTests(unittest.TestCase):
    def make_envelope(self, run_id="run_ABC-123_456", expires_at=None):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = private.public_key()
        issued_at = int(time.time() * 1000)
        expires_at = expires_at or issued_at + 60_000
        payload = {"conductorRunId": run_id, "profile": "private profile", "job": {"title": "Secret JD", "company": "Private Co"}, "sourceUrl": "https://example.com/job", "issuedAt": issued_at, "expiresAt": expires_at}
        plaintext = json.dumps(payload).encode()
        key = os.urandom(32)
        nonce = os.urandom(12)
        aad = f"{VERSION}:{run_id}:{expires_at}".encode()
        sealed = AESGCM(key).encrypt(nonce, plaintext, aad)
        wrapped = public.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
        envelope = {"version": VERSION, "conductorRunId": run_id, "issuedAt": issued_at, "expiresAt": expires_at, "wrappedKey": enc(wrapped), "nonce": enc(nonce), "ciphertext": enc(sealed[:-16]), "tag": enc(sealed[-16:])}
        private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        return enc(json.dumps(envelope).encode()), private_pem

    def run_decrypt(self, encoded, private_pem, run_id="run_ABC-123_456"):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "job-envelope.json"
            env = {**os.environ, "CONDUCTOR_RUN_ID": run_id, "CAREER_OS_ENVELOPE_PRIVATE_KEY": private_pem}
            completed = subprocess.run([sys.executable, "scripts/decrypt_job_envelope.py", encoded, str(target)], env=env, capture_output=True, text=True)
            output = target.read_text() if target.exists() else None
            return completed, output

    def test_round_trip_and_no_plaintext_output(self):
        encoded, private_pem = self.make_envelope()
        completed, output = self.run_decrypt(encoded, private_pem)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("Secret JD", completed.stdout + completed.stderr)
        self.assertEqual(json.loads(output)["job"]["title"], "Secret JD")

    def test_tamper_and_replay_identity_are_rejected(self):
        encoded, private_pem = self.make_envelope()
        raw = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        decoded_ciphertext = bytearray(base64.urlsafe_b64decode(raw["ciphertext"] + "=" * (-len(raw["ciphertext"]) % 4)))
        decoded_ciphertext[0] ^= 1
        raw["ciphertext"] = enc(bytes(decoded_ciphertext))
        tampered = enc(json.dumps(raw).encode())
        completed, _ = self.run_decrypt(tampered, private_pem)
        self.assertNotEqual(completed.returncode, 0)
        replayed, _ = self.run_decrypt(encoded, private_pem, run_id="run_OTHER-123")
        self.assertNotEqual(replayed.returncode, 0)

    def test_expired_envelope_is_rejected(self):
        encoded, private_pem = self.make_envelope(expires_at=int(time.time() * 1000) - 1)
        completed, _ = self.run_decrypt(encoded, private_pem)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("expired", completed.stderr.lower())


if __name__ == "__main__":
    unittest.main()
