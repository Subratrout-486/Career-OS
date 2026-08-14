"""Safety contract for the browser-side application executor.

Career OS does not drive a browser in this package.  The authenticated browser
adapter supplies observations to this module and then passes the resulting
facts to :func:`career_os.application_mode.decide_application_mode`.

The contract deliberately accepts only the current ``resume_files`` emitted by
the same Career OS result.  It never searches for, substitutes, or promotes a
master/generic resume.  A browser adapter may retry the exact current artifact
through its file chooser/input, but it must prove that the expected filename is
selected and visible before continuing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


_ALLOWED_SUFFIXES = {".pdf", ".docx"}
_APPROVED_ANSWER_STATUSES = {"APPROVED", "USER_APPROVED", "VERIFIED"}


@dataclass(frozen=True)
class ResumeUploadPlan:
    """The exact current Career OS artifact and its permitted retry files."""

    primary: Path
    retries: tuple[Path, ...] = ()

    @property
    def permitted_paths(self) -> tuple[Path, ...]:
        return (self.primary, *self.retries)


def _validated_artifact(value: object) -> Path | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    if path.suffix.lower() not in _ALLOWED_SUFFIXES or not path.is_file():
        return None
    lowered = path.name.casefold()
    if any(marker in lowered for marker in ("master", "generic", "unrelated")):
        return None
    return path


def select_current_resume(resume_files: Mapping[str, object], *, preferred: str = "pdf") -> ResumeUploadPlan:
    """Select only the current Career OS PDF/DOCX from one pipeline result.

    ``preferred`` is normally ``pdf`` for LinkedIn and ATS portals.  If that
    artifact is unavailable, the current result's DOCX is the only permitted
    fallback.  No filesystem search is performed, which prevents accidental
    reuse of a master resume or another job's artifact.
    """

    order = [preferred, "pdf", "docx"]
    candidates: list[Path] = []
    for key in order:
        if key in {item.suffix.lstrip(".") for item in candidates}:
            continue
        artifact = _validated_artifact(resume_files.get(key))
        if artifact is not None and artifact not in candidates:
            candidates.append(artifact)
    if not candidates:
        raise ValueError("No verified current Career OS tailored PDF/DOCX is available")
    return ResumeUploadPlan(primary=candidates[0], retries=tuple(candidates[1:]))


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one exact local artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_resume_hash(plan: ResumeUploadPlan, expected_sha256: str | None) -> bool:
    """Require the selected primary artifact to equal the manifest digest."""
    expected = str(expected_sha256 or "").strip().lower()
    return bool(expected) and sha256_file(plan.primary) == expected


def verify_resume_attachment(
    plan: ResumeUploadPlan,
    *,
    selected_filename: str | None,
    form_text: str = "",
    attached: bool = False,
) -> bool:
    """Prove that the primary current artifact is actually attached.

    The browser adapter must report the selected filename and either an
    explicit attachment signal or visible form text containing that filename.
    A different filename, including a master or unrelated-job resume, fails.
    """

    if not selected_filename:
        return False
    expected = plan.primary.name.casefold()
    selected = Path(str(selected_filename)).name.casefold()
    if selected != expected:
        return False
    visible = expected in str(form_text or "").casefold()
    return bool(attached or visible) and visible


def build_verified_browser_context(
    *,
    application_type: str,
    application_url_verified: bool,
    resume_attachment_verified: bool,
    complete_form_verified: bool,
    resume_sha256_verified: bool = False,
    required_questions: Sequence[Mapping[str, Any]] = (),
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the conservative browser facts consumed by Application Mode.

    Every required question must have a non-empty answer with an explicitly
    approved status.  The caller remains responsible for setting review flags
    such as CAPTCHA, OTP, legal, sponsorship, compensation, or unknown fields
    in ``extra``; those flags remain human-controlled in Application Mode.
    """

    required = [item for item in required_questions if item.get("required") is True]
    answers_verified = all(
        str(item.get("user_answer") or "").strip()
        and str(item.get("status") or "").upper() in _APPROVED_ANSWER_STATUSES
        for item in required
    )
    context: dict[str, Any] = {
        "application_type": application_type,
        "application_url_verified": bool(application_url_verified),
        "resume_attachment_verified": bool(resume_attachment_verified),
        "complete_form_verified": bool(complete_form_verified),
        "resume_sha256_verified": bool(resume_sha256_verified),
        "required_answers_verified": bool(complete_form_verified and answers_verified),
    }
    if extra:
        context.update(dict(extra))
    return context
