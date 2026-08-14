"""Verified Manus browser-preflight evaluation for Career OS.

This module does not drive a browser or infer answers.  It accepts structured
observations returned by an authenticated Manus browser task, proves that the
currently generated JD-tailored artifact was used, and feeds conservative facts
back through :func:`decide_application_mode`.  A preflight can only make a
package *more* restrictive; missing, malformed, or unapproved facts remain a
human-review condition.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .application_mode import ApplicationMode, ApplicationModeDecision, decide_application_mode
from .browser_executor import (
    ResumeUploadPlan,
    build_verified_browser_context,
    select_current_resume,
    sha256_file,
    verify_resume_attachment,
)

PREFLIGHT_SCHEMA_VERSION = "career_os_manus_browser_preflight/v1"
_APPROVED_ANSWER_STATUSES = {"APPROVED", "USER_APPROVED", "VERIFIED", "NOT_APPLICABLE"}
_SAFETY_FLAGS = (
    "captcha",
    "otp",
    "mfa",
    "identity_verification",
    "login_or_identity_challenge",
    "assessment_or_test",
    "unknown_required_question",
    "unusual_free_text",
    "custom_cover_letter",
    "sensitive_or_legal_question",
    "additional_personal_question",
    "salary_judgment",
    "salary_or_ctc_question",
    "notice_period_judgment",
    "ambiguous_work_authorization",
    "work_authorization_unknown",
    "sponsorship_or_authorization_ambiguity",
    "unsupported_experience_question",
    "relocation_judgment",
    "on_site_availability_unknown",
    "shift_availability_unknown",
    "unexpected_site_behavior",
    "contradictory_profile_data",
    "unapproved_request",
    "suspicious_redirect",
)


class BrowserPreflightError(ValueError):
    """Raised when a package cannot safely enter Manus browser preflight."""


@dataclass(frozen=True)
class BrowserPreflightEvaluation:
    """The only supported transition from browser observation to execution mode."""

    status: str
    browser_context: dict[str, Any]
    decision: ApplicationModeDecision
    prepared_result: dict[str, Any]
    resume_plan: ResumeUploadPlan
    required_question_payload: dict[str, Any]


def _as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _normalise_question(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _normalise_answer(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _application_id(result: Mapping[str, Any]) -> str:
    application_id = str(result.get("application_page_id") or result.get("application_id") or "").strip()
    if not application_id:
        raise BrowserPreflightError("PREFLIGHT_BLOCKED: durable Application record ID is required")
    return application_id


def _application_identity(result: Mapping[str, Any]) -> dict[str, str]:
    job = _as_dict(result.get("job"))
    verification = _as_dict(result.get("job_verification"))
    identity = {
        "company": str(job.get("company") or "").strip(),
        "title": str(job.get("title") or "").strip(),
        "job_url": str(verification.get("application_url") or job.get("url") or "").strip(),
        "application_id": _application_id(result),
    }
    missing = [key for key, value in identity.items() if not value]
    if missing:
        raise BrowserPreflightError("PREFLIGHT_BLOCKED: application identity is incomplete: " + ", ".join(missing))
    return identity


def _approved_questions(
    result: Mapping[str, Any], explicit_questions: Sequence[Mapping[str, Any]] | None = None
) -> dict[str, dict[str, Any]]:
    """Return the user-approved answer contract keyed by normalized question text.

    The explicit set is intended for a Notion Application Questions export.  It
    is merged with the pipeline result but must never replace a conflicting
    answer.  This prevents a browser observer from changing an approved answer
    by merely returning a different value.
    """

    candidates: list[Mapping[str, Any]] = []
    candidates.extend(item for item in _as_list(result.get("application_questions")) if isinstance(item, Mapping))
    if explicit_questions:
        candidates.extend(item for item in explicit_questions if isinstance(item, Mapping))

    approved: dict[str, dict[str, Any]] = {}
    for item in candidates:
        text = str(item.get("question") or item.get("text") or "").strip()
        key = _normalise_question(text)
        answer = str(item.get("user_answer") or item.get("approved_answer") or item.get("answer") or "").strip()
        status = str(item.get("status") or item.get("approval_status") or "").upper().strip()
        required = item.get("required") is True
        if not key or not required or not answer or status not in _APPROVED_ANSWER_STATUSES:
            continue
        candidate = {"question": text, "answer": answer, "status": status, "required": True}
        existing = approved.get(key)
        if existing and _normalise_answer(existing["answer"]) != _normalise_answer(answer):
            raise BrowserPreflightError(f"PREFLIGHT_BLOCKED: conflicting approved answers for required question: {text}")
        approved[key] = candidate
    return approved


def build_preflight_request(
    result: Mapping[str, Any], *, approved_questions: Sequence[Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    """Build the immutable inputs for one browser inspection task.

    A package may be in ``REVIEW_REQUIRED`` solely because browser facts are not
    known yet.  This function permits that case, but rejects all hard pipeline
    failures before an external browser task is created.
    """

    result_data = dict(result)
    initial = decide_application_mode(result_data, browser_context={})
    if initial.mode is ApplicationMode.DO_NOT_APPLY:
        raise BrowserPreflightError("PREFLIGHT_BLOCKED: " + "; ".join(initial.blockers or (initial.reason,)))
    plan = select_current_resume(_as_dict(result_data.get("resume_files")))
    identity = _application_identity(result_data)
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "application": identity,
        "resume_path": str(plan.primary),
        "resume_filename": plan.primary.name,
        "resume_sha256": sha256_file(plan.primary),
        "resume_retry_filenames": [path.name for path in plan.retries],
        "approved_questions": list(_approved_questions(result_data, approved_questions).values()),
    }


def _safe_flags(observation: Mapping[str, Any]) -> dict[str, bool]:
    raw = _as_dict(observation.get("safety_flags"))
    flags = {name: raw.get(name) is True or observation.get(name) is True for name in _SAFETY_FLAGS}
    return flags


def _required_question_evidence(
    observation: Mapping[str, Any], approved: Mapping[str, Mapping[str, Any]]
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Verify that every observed mandatory question exactly matches approval.

    In particular, a support role must not be promoted to engineering experience:
    a question asking for engineering years passes only when the exact approved
    engineering answer is returned (for the TCS fixture, ``0``).
    """

    blockers: list[str] = []
    feedback: list[dict[str, Any]] = []
    required = [item for item in _as_list(observation.get("required_questions")) if isinstance(item, Mapping) and item.get("required") is True]
    for item in required:
        text = str(item.get("question") or item.get("text") or "").strip()
        key = _normalise_question(text)
        observed_answer = str(item.get("approved_answer") or item.get("answer") or "").strip()
        observed_status = str(item.get("approval_status") or item.get("status") or "").upper().strip()
        expected = approved.get(key)
        if not text or expected is None:
            blockers.append("unknown mandatory question" + (f": {text}" if text else ""))
            feedback.append({"question": text or "[unnamed required question]", "required": True, "type": "Other"})
            continue
        if observed_status not in _APPROVED_ANSWER_STATUSES:
            blockers.append(f"required question lacks approved status: {text}")
            feedback.append({"question": text, "required": True, "type": "Other"})
            continue
        if _normalise_answer(observed_answer) != _normalise_answer(expected["answer"]):
            blockers.append(f"required answer does not match approved answer: {text}")
            feedback.append({"question": text, "required": True, "type": "Other"})
    return not blockers, blockers, feedback


def evaluate_preflight_observation(
    result: Mapping[str, Any],
    observation: Mapping[str, Any],
    *,
    approved_questions: Sequence[Mapping[str, Any]] | None = None,
) -> BrowserPreflightEvaluation:
    """Validate a completed Manus preflight observation against Career OS facts."""

    result_data = dict(result)
    observation_data = dict(observation)
    request = build_preflight_request(result_data, approved_questions=approved_questions)
    plan = select_current_resume(_as_dict(result_data.get("resume_files")))
    approved = _approved_questions(result_data, approved_questions)
    flags = _safe_flags(observation_data)
    raw_blockers = [str(item).strip() for item in _as_list(observation_data.get("blockers")) if str(item).strip()]

    observation_status = str(observation_data.get("status") or "ERROR").upper().strip()
    if observation_status != "PREFLIGHT_READY":
        raw_blockers.append(f"Manus preflight status={observation_status}")
    observed_url = str(observation_data.get("observed_application_url") or "").strip()
    url_verified = observation_data.get("application_url_verified") is True and observed_url == request["application"]["job_url"]
    if not url_verified:
        raw_blockers.append("verified application URL was not observed")

    answers_verified, question_blockers, feedback_questions = _required_question_evidence(observation_data, approved)
    raw_blockers.extend(question_blockers)
    if question_blockers:
        flags["unknown_required_question"] = True

    selected_filename = str(observation_data.get("selected_resume_filename") or "")
    attachment_visible = observation_data.get("resume_attachment_visible") is True
    attachment_verified = verify_resume_attachment(
        plan,
        selected_filename=selected_filename,
        form_text=plan.primary.name if attachment_visible else "",
        attached=attachment_visible,
    )
    expected_hash = request["resume_sha256"]
    hash_verified = (
        observation_data.get("selected_resume_sha256") == expected_hash
        and sha256_file(plan.primary) == expected_hash
        and selected_filename == plan.primary.name
    )
    normal_upload_attempted = observation_data.get("normal_upload_attempted") is True
    fallback_attempted = (
        observation_data.get("file_chooser_retry_attempted") is True
        or observation_data.get("input_retry_attempted") is True
    )
    fallback_succeeded = (
        observation_data.get("file_chooser_retry_succeeded") is True
        or observation_data.get("input_retry_succeeded") is True
    )
    if not normal_upload_attempted:
        raw_blockers.append("normal tailored-resume upload was not attempted")
    if not attachment_verified:
        raw_blockers.append("exact tailored-resume attachment is not visibly verified")
    if not hash_verified:
        raw_blockers.append("exact tailored-resume SHA-256 is not verified")
    if normal_upload_attempted and observation_data.get("normal_upload_succeeded") is not True:
        if not fallback_attempted:
            raw_blockers.append("force-resume-upload fallback was not attempted after normal upload failure")
        elif not fallback_succeeded:
            raw_blockers.append("force-resume-upload fallback did not confirm a successful exact tailored-resume upload")

    context_extra: dict[str, Any] = {
        "application_method": str(observation_data.get("application_method") or "").strip(),
        "browser_context_version": PREFLIGHT_SCHEMA_VERSION,
        "human_controlled_blockers": list(dict.fromkeys(raw_blockers)),
        "resume_upload_fallback_used": fallback_attempted and fallback_succeeded,
        **flags,
    }
    context = build_verified_browser_context(
        application_type=str(observation_data.get("application_type") or "").strip(),
        application_url_verified=url_verified,
        complete_form_verified=observation_data.get("complete_form_verified") is True,
        required_questions=[
            {
                "required": True,
                "user_answer": item.get("approved_answer") or item.get("answer"),
                "status": item.get("approval_status") or item.get("status"),
            }
            for item in _as_list(observation_data.get("required_questions"))
            if isinstance(item, Mapping) and item.get("required") is True
        ],
        resume_attachment_verified=attachment_verified,
        resume_sha256_verified=hash_verified,
        extra=context_extra,
    )
    # The browser response must itself agree with the deterministically checked
    # required-question evidence; neither signal is trusted alone.
    context["required_answers_verified"] = bool(
        answers_verified
        and observation_data.get("required_answers_verified") is True
        and context.get("required_answers_verified") is True
    )

    decision = decide_application_mode(result_data, browser_context=context)
    prepared = dict(result_data)
    prepared["application_mode"] = decision.mode.value
    prepared["application_mode_reason"] = decision.reason
    prepared["application_mode_blockers"] = list(decision.blockers)

    status = "AUTO_APPLY_READY" if decision.mode is ApplicationMode.AUTO_APPLY else "REVIEW_REQUIRED"
    question_payload = {
        "application_id": request["application"]["application_id"],
        "company": request["application"]["company"],
        "job_title": request["application"]["title"],
        "application_url": request["application"]["job_url"],
        "questions": feedback_questions,
    }
    return BrowserPreflightEvaluation(
        status=status,
        browser_context=context,
        decision=decision,
        prepared_result=prepared,
        resume_plan=plan,
        required_question_payload=question_payload,
    )
