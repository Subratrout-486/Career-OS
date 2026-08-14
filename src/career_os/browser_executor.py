"""Safety contract for the authenticated browser-side application executor.

Career OS does not drive a browser in this package. The browser adapter supplies
observations from the verified application destination and passes the resulting
facts to :func:`career_os.application_mode.decide_application_mode`.

The contract is deliberately channel-agnostic. ``application_channel`` is a
description discovered from the live destination (for example ``linkedin_easy_apply``,
``greenhouse``, ``lever``, ``workday``, or ``employer_hosted_form``); it is never
used as an allow-list. The adapter must inspect the actual flow and fail closed
for suspicious redirects, human-controlled steps, or incomplete pages.

Only the current ``resume_files`` emitted by the same Career OS result may be
used. A browser adapter may retry the exact current PDF/DOCX through its file
chooser/input, but it must prove the selected filename and submitted-file hash.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


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

    @property
    def permitted_filenames(self) -> tuple[str, ...]:
        return tuple(path.name for path in self.permitted_paths)


@dataclass(frozen=True)
class ApplicationDestination:
    """A destination observed by the browser, independent of application channel."""

    requested_url: str
    final_url: str
    application_channel: str
    expected_url: str | None = None
    redirect_chain: tuple[str, ...] = ()
    suspicious_redirect: bool = False

    @property
    def verified(self) -> bool:
        return verify_application_destination(
            expected_application_url=self.expected_url,
            requested_url=self.requested_url,
            final_url=self.final_url,
            application_channel=self.application_channel,
            redirect_chain=self.redirect_chain,
            suspicious_redirect=self.suspicious_redirect,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected_url": self.expected_url,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "application_channel": self.application_channel,
            "redirect_chain": list(self.redirect_chain),
            "suspicious_redirect": self.suspicious_redirect,
            "verified": self.verified,
        }


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


def _is_http_url(value: object) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def verify_application_destination(
    *,
    expected_application_url: str | None = None,
    requested_url: str | None,
    final_url: str | None,
    application_channel: str | None,
    redirect_chain: Sequence[str] = (),
    suspicious_redirect: bool = False,
) -> bool:
    """Verify that the browser reached a concrete, non-suspicious destination.

    A channel is descriptive metadata discovered by the browser, not a policy
    allow-list. Direct employer pages, ATS pages, LinkedIn flows, and other
    legitimate forms are all valid when the live URL and redirect chain are
    verified. The caller must set ``suspicious_redirect`` when the observed
    destination is unexpected, impersonating an employer, or otherwise unsafe.
    """

    if suspicious_redirect or not str(application_channel or "").strip():
        return False
    if expected_application_url and str(expected_application_url).strip() != str(requested_url or "").strip():
        return False
    if not _is_http_url(requested_url) or not _is_http_url(final_url):
        return False
    chain = tuple(str(item).strip() for item in redirect_chain if str(item).strip())
    if chain and (not all(_is_http_url(item) for item in chain) or chain[-1] != str(final_url).strip()):
        return False
    return True


def select_current_resume(resume_files: Mapping[str, object], *, preferred: str = "pdf") -> ResumeUploadPlan:
    """Select only the current Career OS PDF/DOCX from one pipeline result.

    ``preferred`` is normally ``pdf`` for LinkedIn and ATS portals. If that
    artifact is unavailable, the current result's DOCX is the only permitted
    fallback. No filesystem search is performed, which prevents accidental
    reuse of a master resume or another job's artifact.
    """

    order = [preferred, "pdf", "docx"]
    candidates: list[Path] = []
    for key in order:
        artifact = _validated_artifact(resume_files.get(key))
        if artifact is not None and artifact not in candidates:
            candidates.append(artifact)
    if not candidates:
        raise ValueError("No verified current Career OS tailored PDF/DOCX is available")
    return ResumeUploadPlan(primary=candidates[0], retries=tuple(candidates[1:]))


def sha256_file(path: Path | str) -> str:
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
    """Prove that an exact current Career OS artifact is attached.

    The primary PDF is preferred, but a current DOCX in ``plan.retries`` is a
    valid controlled fallback when the portal requires it or the PDF upload
    interaction fails. A master or another-job filename always fails.
    """

    if not selected_filename:
        return False
    selected = Path(str(selected_filename)).name.casefold()
    permitted = {name.casefold() for name in plan.permitted_filenames}
    if selected not in permitted:
        return False
    visible = selected in str(form_text or "").casefold()
    return bool(attached or visible) and visible


def verify_submitted_resume_hash(
    plan: ResumeUploadPlan,
    *,
    submitted_filename: str | None,
    submitted_sha256: str | None,
) -> bool:
    """Verify that the submitted file is one of this run's exact artifacts."""

    if not submitted_filename or not submitted_sha256:
        return False
    submitted = Path(str(submitted_filename)).name.casefold()
    for path in plan.permitted_paths:
        if path.name.casefold() == submitted and sha256_file(path).casefold() == str(submitted_sha256).casefold():
            return True
    return False


def verify_submission_confirmation(
    plan: ResumeUploadPlan,
    *,
    confirmation_verified: bool,
    submitted_filename: str | None,
    submitted_sha256: str | None,
) -> bool:
    """Require authoritative confirmation and exact tailored-resume identity.

    Reaching a form, uploading a file, or pressing a button is not enough. The
    browser adapter must independently verify the employer/LinkedIn confirmation
    and report the submitted file hash before an application may be marked Applied.
    """

    return bool(
        confirmation_verified
        and verify_submitted_resume_hash(
            plan,
            submitted_filename=submitted_filename,
            submitted_sha256=submitted_sha256,
        )
    )


def build_verified_browser_context(
    *,
    application_url_verified: bool | None = None,
    application_destination_verified: bool | None = None,
    application_url: str | None = None,
    expected_application_url: str | None = None,
    final_application_url: str | None = None,
    application_channel: str | None = None,
    application_type: str | None = None,
    resume_attachment_verified: bool,
    complete_form_verified: bool,
    resume_sha256_verified: bool = False,
    required_questions: Sequence[Mapping[str, Any]] = (),
    flow_pages_verified: bool | None = None,
    application_destination: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build conservative browser facts consumed by Application Mode.

    ``application_channel`` is discovered after following the verified
    ``application_url`` and inspecting the live form. It is intentionally open
    ended. Every required question must have a non-empty answer with an
    explicitly approved status. The caller remains responsible for setting
    review flags such as CAPTCHA, OTP, legal, sponsorship, compensation,
    suspicious redirects, assessments, or unknown fields in ``extra``.
    """

    required = [item for item in required_questions if item.get("required") is True]
    answers_verified = all(
        str(item.get("user_answer") or "").strip()
        and str(item.get("status") or "").upper() in _APPROVED_ANSWER_STATUSES
        for item in required
    )

    channel = str(application_channel or application_type or "").strip()
    destination_verified = application_destination_verified
    if destination_verified is None:
        destination_verified = application_url_verified
    if application_destination is not None:
        destination = dict(application_destination)
        destination_verified = verify_application_destination(
            expected_application_url=str(destination.get("expected_url") or expected_application_url or application_url or ""),
            requested_url=str(destination.get("requested_url") or application_url or ""),
            final_url=str(destination.get("final_url") or final_application_url or application_url or ""),
            application_channel=str(destination.get("application_channel") or channel),
            redirect_chain=destination.get("redirect_chain") or (),
            suspicious_redirect=bool(destination.get("suspicious_redirect")),
        )
        channel = str(destination.get("application_channel") or channel).strip()
    elif application_url or final_application_url:
        destination_verified = bool(
            destination_verified
            and verify_application_destination(
                expected_application_url=expected_application_url,
                requested_url=application_url,
                final_url=final_application_url or application_url,
                application_channel=channel,
            )
        )

    complete = bool(complete_form_verified and flow_pages_verified is not False)
    context: dict[str, Any] = {
        "application_url": application_url,
        "expected_application_url": expected_application_url or application_url,
        "final_application_url": final_application_url or application_url,
        "application_channel": channel,
        # Retain the descriptive legacy key for downstream records and callers.
        "application_type": channel,
        "application_url_verified": bool(destination_verified),
        "application_destination_verified": bool(destination_verified),
        "resume_attachment_verified": bool(resume_attachment_verified),
        "complete_form_verified": complete,
        "flow_pages_verified": flow_pages_verified is not False,
        "resume_sha256_verified": bool(resume_sha256_verified),
        "required_answers_verified": bool(complete and answers_verified),
    }
    if application_destination is not None:
        context["application_redirect_chain"] = list(application_destination.get("redirect_chain") or [])
        context["suspicious_redirect"] = bool(application_destination.get("suspicious_redirect"))
    if extra:
        protected = {
            "application_url_verified",
            "application_destination_verified",
            "resume_attachment_verified",
            "complete_form_verified",
            "flow_pages_verified",
            "required_answers_verified",
            "suspicious_redirect",
        }
        context.update({key: value for key, value in dict(extra).items() if key not in protected})
    return context
