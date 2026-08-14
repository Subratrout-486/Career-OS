"""Regression tests for ApplicationsTracker._resume_used_reference.

Root cause: the Applications 'Resume Used' field used to embed raw local
filesystem paths (e.g. "generated_resumes/foo.pdf") whenever resume files
existed, regardless of whether they were ever uploaded to Notion. Those
paths live only on the ephemeral GitHub Actions runner and are never
openable from Notion — a local path existing is not evidence the file is
actually visible in Notion. These tests lock in the fix: the Applications
record must reference the real Notion Resume Library page when it exists,
and must say so explicitly (never hint at a phantom local path) when it
doesn't.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.applications import ApplicationsTracker  # noqa: E402


def test_resume_used_links_to_resume_library_page_when_present():
    ref = ApplicationsTracker._resume_used_reference(
        resume_library_page_id="3bb8bc1d-ce0e-8130-a237-da7583ff2db1",
        resume_files={
            "pdf": "generated_resumes/example.pdf",
            "docx": "generated_resumes/example.docx",
        },
    )
    assert ref == "Resume Library: https://www.notion.so/3bb8bc1dce0e8130a237da7583ff2db1"
    # Must never leak the ephemeral local runner path into the Notion record.
    assert "generated_resumes" not in ref
    assert ".pdf" not in ref
    assert ".docx" not in ref


def test_resume_used_never_exposes_local_path_when_library_page_missing():
    """This is the exact bug scenario: resume files exist locally (the
    pipeline generated them) but the Notion Resume Library page was never
    created (e.g. the file_upload call failed). The old code silently
    surfaced the local path as if it were a working reference."""
    ref = ApplicationsTracker._resume_used_reference(
        resume_library_page_id=None,
        resume_files={
            "pdf": "generated_resumes/example.pdf",
            "docx": "generated_resumes/example.docx",
        },
    )
    assert "generated_resumes" not in ref
    assert ".pdf" not in ref
    assert ".docx" not in ref
    assert "NOT attached to Notion Resume Library" in ref


def test_resume_used_states_no_file_when_nothing_generated():
    ref = ApplicationsTracker._resume_used_reference(
        resume_library_page_id=None,
        resume_files={},
    )
    assert ref == "No resume file generated for this run."


def test_resume_used_prefers_library_link_even_if_local_paths_also_present():
    """When both exist, the Resume Library link is authoritative — local
    paths must never appear alongside it either."""
    ref = ApplicationsTracker._resume_used_reference(
        resume_library_page_id="abc123",
        resume_files={"pdf": "generated_resumes/x.pdf"},
    )
    assert ref.startswith("Resume Library: https://www.notion.so/abc123")
    assert "generated_resumes" not in ref
