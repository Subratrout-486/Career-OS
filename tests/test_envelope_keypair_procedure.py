from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_envelope_keypair.py"
READINESS = ROOT / "scripts" / "verify_envelope_keypair.py"


class EnvelopeKeyPairProcedureTests(unittest.TestCase):
    def test_generate_and_readiness_check_without_printing_key_material(self) -> None:
        with tempfile.TemporaryDirectory(prefix="career-os-keypair-test-") as work:
            work_path = Path(work)
            private_path = work_path / "private.pem"
            public_path = work_path / "public.pem"
            generated = subprocess.run(
                [sys.executable, str(GENERATOR), "--public-output", str(public_path), "--private-output", str(private_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertIn("KEYPAIR_GENERATED", generated.stdout)
            self.assertNotIn("BEGIN PRIVATE KEY", generated.stdout)
            self.assertEqual(stat.S_IMODE(private_path.stat().st_mode), 0o600)
            readiness = subprocess.run(
                [sys.executable, str(READINESS), "--public-key", str(public_path), "--private-key", str(private_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(readiness.returncode, 0, readiness.stderr)
            self.assertEqual(readiness.stdout.strip(), "KEYPAIR_READINESS_PASSED")
            self.assertNotIn("BEGIN PRIVATE KEY", readiness.stdout)
            self.assertNotIn('"controlled"', readiness.stdout)

    def test_generator_refuses_private_output_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory(prefix="career-os-keypair-test-") as work:
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "--public-output", str(Path(work) / "public.pem"), "--private-output", str(ROOT / "private.pem")],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside the repository", result.stderr + result.stdout)
            self.assertFalse((ROOT / "private.pem").exists())


if __name__ == "__main__":
    unittest.main()
