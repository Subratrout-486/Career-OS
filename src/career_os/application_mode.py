"""Deterministic browser-execution mode decisions for Career OS.

Career OS remains the decision and truth engine. This module never invents
profile data and never submits an application. It classifies a prepared package
for a later browser operator, defaulting to human review whenever browser
conditions or required answers are unknown.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ApplicationMode(StrEnum):
    AUTO_APPLY = "AUTO_APPLY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DO_NOT_APPLY = "DO_NOT_APPLY"


@dataclass(frozen=True)
class ApplicationModeDecision:
    mode: ApplicationMode
    reason: str
    blockers: tuple[str, ...] = field(default_factory=tuple)


def _truth_guard_failed(result: dict[str, Any]) -> bool:
    errors = [str(item) for item in result.get("errors") or []]
    # ``resume.unsupported_claims`` is an audit trail for omitted or rejected
    # JD requirements. Truth Guard itself emits the hard signal only when an
    # unsupported claim actually appears in the generated resume.
    return any(item.startswith("TRUTH_GUARD:") for item in errors)


def decide_application_mode(
    result: dict[str, Any],
    *,
    browser_context: dict[str, Any] | None = None,
) -> ApplicationModeDecision:
    """Classify a Career OS package for browser execution.

    ``browser_context`` is intentionally optional and absent during normal
    pipeline processing. Without explicit, verified browser facts the result
    is REVIEW_REQUIRED rather than AUTO_APPLY.
    """
    job_verification = result.get("job_verification") or {}
    fit = result.get("fit") or {}
    resume = result.get("resume") or {}
    ats = result.get("ats") or {}
    errors = [str(item) for item in result.get("errors") or []]
    blockers: list[str] = []

    if result.get("review_status") in {"INACTIVE_JOB", "SKIPPED", "EVIDENCE_VAULT_UNAVAILABLE", "RESUME_GENERATION_FAILED", "NOTION_WRITE_FAILED"}:
        return ApplicationModeDecision(ApplicationMode.DO_NOT_APPLY, "Career OS did not produce an eligible application package.", (result.get("review_status", "invalid_pipeline"),))
    if not job_verification.get("active") or job_verification.get("status") != "ACTIVE":
        blockers.append("job is not verified ACTIVE")
    if str(fit.get("recommendation", "")).upper() == "SKIP" or str(fit.get("band", "")).upper() == "D":
        blockers.append("Career OS recommendation is SKIP")
    if _truth_guard_failed(result):
        blockers.append("Truth Guard failed or unsupported claims remain")
    if not resume:
        blockers.append("tailored resume is missing")
    if not ats:
        blockers.append("ATS output is missing")
    if any(item.startswith(("NOTION_WRITE_FAILED:", "APPLICATIONS_TRACK_FAILED:")) for item in errors):
        blockers.append("required tracking persistence failed")

    if blockers:
        return ApplicationModeDecision(ApplicationMode.DO_NOT_APPLY, "Application is blocked by Career OS safeguards.", tuple(dict.fromkeys(blockers)))

    context = browser_context or {}
    if not browser_context:
        return ApplicationModeDecision(ApplicationMode.REVIEW_REQUIRED, "Browser conditions and required-answer safety are not yet verified; human review is required.", ("browser context not supplied",))

    review_conditions = {
        "custom_cover_letter": "custom cover letter required",
        "unusual_free_text": "unusual free-text question",
        "salary_judgment": "salary or compensation judgment required",
        "notice_period_judgment": "notice-period judgment required",
        "ambiguous_work_authorization": "ambiguous work authorization question",
        "work_authorization_unknown": "work authorization requires user confirmation",
        "relocation_judgment": "relocation judgment required",
        "on_site_availability_unknown": "on-site availability requires user confirmation",
        "shift_availability_unknown": "shift availability requires user confirmation",
        "assessment_or_test": "assessment or test detected",
        "additional_personal_question": "additional personal question requires user input",
        "captcha": "CAPTCHA detected",
        "login_or_identity_challenge": "login or identity challenge detected",
        "unexpected_site_behavior": "unexpected site behavior",
        "contradictory_profile_data": "application data conflicts with verified profile",
        "unapproved_request": "application requests unapproved information",
        "suspicious_redirect": "application destination is suspicious",
        "salary_or_ctc_question": "salary/CTC answer remains user-controlled",
    }
    review_blockers = [label for key, label in review_conditions.items() if context.get(key)]
    if context.get("required_answers_verified") is not True:
        review_blockers.append("not all required answers are verified profile data")
    if context.get("complete_form_verified") is not True:
        review_blockers.append("complete application form is not verified")
    if context.get("resume_attachment_verified") is not True:
        review_blockers.append("current Career OS tailored resume attachment is not verified")
    if context.get("application_type") not in {"easy_apply", "straightforward_form"}:
        review_blockers.append("application form type is not explicitly straightforward")
    if context.get("application_url_verified") is not True:
        review_blockers.append("application URL is not explicitly verified")

    if review_blockers:
        return ApplicationModeDecision(ApplicationMode.REVIEW_REQUIRED, "The package is eligible for review, but browser execution requires human input or confirmation.", tuple(dict.fromkeys(review_blockers)))

    return ApplicationModeDecision(ApplicationMode.AUTO_APPLY, "All Career OS and explicitly verified browser safety conditions passed.", ())
