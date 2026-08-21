"""Verified browser-execution manifest generation for Career OS.

A manifest is a short-lived execution package, not a source of truth.  It is
created only for a fully prepared ``AUTO_APPLY`` package and is revalidated by
the preserved dispatcher immediately before a browser task is created.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .application_mode import ApplicationMode, decide_application_mode
from .browser_executor import ResumeUploadPlan, select_current_resume, sha256_file


MANIFEST_SCHEMA_VERSION = "career_os_browser_execution_manifest/v1"
MANIFEST_GENERATOR_VERSION = "1.0.0"
_REQUIRED_GATE_KEYS = (
    "job_active",
    "ghost_job_risk_acceptable",
    "manus_recommendation_apply",
    "truth_guard_passed",
    "ats_passed",
    "recruiter_review_passed",
    "gemini_adversarial_passed",
    "gemini_adversarial_apply",
    "design_qa_passed",
    "complete_form_verified",
    "required_answers_verified",
    "resume_attachment_verified",
    "resume_sha256_verified",
)
_HUMAN_CONTROLLED_CONTEXT_FLAGS = {
    "captcha": "CAPTCHA detected",
    "otp": "OTP required",
    "mfa": "MFA required",
    "identity_verification": "identity verification required",
    "login_or_identity_challenge": "login or identity challenge detected",
    "assessment_or_test": "assessment or test detected",
    "unknown_required_question": "unknown mandatory question",
    "unusual_free_text": "unusual free-text question",
    "custom_cover_letter": "custom cover letter required",
    "sensitive_or_legal_question": "sensitive or legal question",
    "additional_personal_question": "additional personal question requires user input",
    "salary_judgment": "salary or compensation judgment required",
    "salary_or_ctc_question": "salary/CTC answer remains user-controlled",
    "salary_without_approved_answer": "salary/CTC has no approved answer",
    "notice_period_judgment": "notice-period judgment required",
    "ambiguous_work_authorization": "ambiguous work authorization question",
    "work_authorization_unknown": "work authorization requires user confirmation",
    "sponsorship_or_authorization_ambiguity": "sponsorship or authorization ambiguity",
    "unsupported_experience_question": "unsupported experience question",
    "relocation_judgment": "relocation judgment required",
    "on_site_availability_unknown": "on-site availability requires user confirmation",
    "shift_availability_unknown": "shift availability requires user confirmation",
    "unexpected_site_behavior": "unexpected site behavior",
    "contradictory_profile_data": "application data conflicts with verified profile",
    "unapproved_request": "application requests unapproved information",
    "suspicious_redirect": "application destination is suspicious",
}


class ManifestGenerationError(ValueError):
    """Raised when a prepared package cannot safely become an execution manifest."""


def _as_dict(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_nonempty_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _truth_guard_passed(result: Mapping[str, Any]) -> bool:
    errors = [str(item) for item in (result.get("errors") or [])]
    return not any(item.startswith("TRUTH_GUARD:") for item in errors)


def _human_controlled_blockers(
    result: Mapping[str, Any], browser_context: Mapping[str, Any]
) -> list[str]:
    blockers = _as_nonempty_list(browser_context.get("human_controlled_blockers"))
    for key, label in _HUMAN_CONTROLLED_CONTEXT_FLAGS.items():
        if browser_context.get(key):
            blockers.append(label)
    if str(result.get("application_mode") or "") != ApplicationMode.AUTO_APPLY.value:
        blockers.extend(_as_nonempty_list(result.get("application_mode_blockers")))
    return list(dict.fromkeys(blockers))


def _gate_results(
    result: Mapping[str, Any], browser_context: Mapping[str, Any], plan: ResumeUploadPlan
) -> dict[str, bool]:
    verification = _as_dict(result.get("job_verification"))
    ghost_risk = _as_dict(verification.get("ghost_job_risk"))
    ats = _as_dict(result.get("ats"))
    recruiter_review = _as_dict(result.get("recruiter_review"))
    design_qa = _as_dict(result.get("design_qa"))
    return {
        "job_active": verification.get("active") is True and verification.get("status") == "ACTIVE",
        "ghost_job_risk_acceptable": ghost_risk.get("acceptable") is True and ghost_risk.get("level") == "ACCEPTABLE",
        "manus_recommendation_apply": (
            str(result.get("primary_recommendation_provider") or "").lower().startswith("manus")
            and str(result.get("primary_recommendation") or "").upper() == "APPLY"
        ),
        "truth_guard_passed": _truth_guard_passed(result),
        "ats_passed": ats.get("passed") is True,
        "recruiter_review_passed": recruiter_review.get("status") == "PASS",
        # Legacy gate keys remain for dispatcher/schema compatibility; their
        # semantics now require the independent DeepSeek challenger.
        "gemini_adversarial_passed": (
            recruiter_review.get("status") == "PASS"
            and str(recruiter_review.get("provider") or "").lower().startswith("deepseek")
        ),
        "gemini_adversarial_apply": (
            str(recruiter_review.get("provider") or "").lower().startswith("deepseek")
            and str(recruiter_review.get("recommendation") or "").upper() == "APPLY"
        ),
        "design_qa_passed": design_qa.get("passed") is True,
        "complete_form_verified": browser_context.get("complete_form_verified") is True,
        "required_answers_verified": browser_context.get("required_answers_verified") is True,
        "resume_attachment_verified": browser_context.get("resume_attachment_verified") is True,
        "resume_sha256_verified": browser_context.get("resume_sha256_verified") is True and plan.primary.is_file(),
    }


def _resume_library_reference(result: Mapping[str, Any]) -> str:
    page_id = str(result.get("resume_library_page_id") or "").replace("-", "").strip()
    if not page_id:
        return ""
    return f"https://www.notion.so/{page_id}"


def _approved_answer_status(result: Mapping[str, Any], browser_context: Mapping[str, Any]) -> dict[str, Any]:
    questions = result.get("application_questions") or []
    required = [item for item in questions if isinstance(item, Mapping) and item.get("required") is True]
    return {
        "required_answers_verified": browser_context.get("required_answers_verified") is True,
        "required_question_count": len(required),
        "approved_question_count": len(required) if browser_context.get("required_answers_verified") is True else 0,
        "answers_serialized": False,
    }


def _application_id(result: Mapping[str, Any]) -> str:
    # Browser outcome reconciliation uses the durable Application record ID.  A
    # local job fingerprint is deliberately never substituted here.
    value = str(result.get("application_page_id") or result.get("application_id") or "").strip()
    if not value:
        raise ManifestGenerationError("MANIFEST_GENERATION_FAILED: durable application record ID is missing")
    return value


def build_browser_execution_record(
    result: Mapping[str, Any], *, browser_context: Mapping[str, Any]
) -> dict[str, Any]:
    """Create one dispatcher-compatible record after deterministic revalidation."""
    result_data = dict(result)
    context = dict(browser_context)
    mode = decide_application_mode(result_data, browser_context=context)
    if str(result_data.get("application_mode") or "") != ApplicationMode.AUTO_APPLY.value:
        raise ManifestGenerationError("MANIFEST_GENERATION_FAILED: application_mode must already be AUTO_APPLY")
    if mode.mode is not ApplicationMode.AUTO_APPLY:
        raise ManifestGenerationError(
            "MANIFEST_GENERATION_FAILED: readiness revalidation returned "
            f"{mode.mode.value}: {'; '.join(mode.blockers) or mode.reason}"
        )
    if str(result_data.get("review_status") or "") != "READY_FOR_REVIEW":
        raise ManifestGenerationError("MANIFEST_GENERATION_FAILED: review_status must be READY_FOR_REVIEW")
    if not _resume_library_reference(result_data):
        raise ManifestGenerationError("MANIFEST_GENERATION_FAILED: durable Resume Library record is missing")

    job = _as_dict(result_data.get("job"))
    company = str(job.get("company") or "").strip()
    title = str(job.get("title") or "").strip()
    job_url = str(_as_dict(result_data.get("job_verification")).get("application_url") or job.get("url") or "").strip()
    if not company or not title or not job_url:
        raise ManifestGenerationError("MANIFEST_GENERATION_FAILED: company, title, and verified application URL are required")

    plan = select_current_resume(_as_dict(result_data.get("resume_files")))
    digest = sha256_file(plan.primary)
    gates = _gate_results(result_data, context, plan)
    failed = [key for key in _REQUIRED_GATE_KEYS if gates.get(key) is not True]
    if failed:
        raise ManifestGenerationError(
            "MANIFEST_GENERATION_FAILED: required gates did not pass: " + ", ".join(failed)
        )
    blockers = _human_controlled_blockers(result_data, context)
    if blockers:
        raise ManifestGenerationError(
            "MANIFEST_GENERATION_FAILED: human-controlled blockers are present: " + "; ".join(blockers)
        )

    application_id = _application_id(result_data)
    application_method = str(
        context.get("application_method") or job.get("application_method") or context.get("application_type") or ""
    ).strip()
    if not application_method:
        raise ManifestGenerationError("MANIFEST_GENERATION_FAILED: application method is missing")

    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "application_id": application_id,
        "company": company,
        "title": title,
        "job_url": job_url,
        "application_method": application_method,
        "application_mode": ApplicationMode.AUTO_APPLY.value,
        "review_status": "READY_FOR_REVIEW",
        "resume_path": str(plan.primary),
        "resume_sha256": digest,
        "resume_artifact": {
            "runtime_path": str(plan.primary),
            "filename": plan.primary.name,
            "format": plan.primary.suffix.lower().lstrip("."),
            "sha256": digest,
            "resume_library_reference": _resume_library_reference(result_data),
        },
        "all_gate_results": gates,
        "approved_answer_status": _approved_answer_status(result_data, context),
        "human_controlled_blockers": [],
        "complete_form_verified": True,
        "resume_attachment_verified": True,
        "resume_sha256_verified": True,
        "gemini_adversarial_provider": str(_as_dict(result_data.get("recruiter_review")).get("provider") or ""),
        "execution": {
            "generated_at": generated_at,
            "generator_version": MANIFEST_GENERATOR_VERSION,
            "browser_context_version": str(context.get("browser_context_version") or "v1"),
            "source_job_id": str(job.get("source_job_id") or ""),
        },
        # The dispatcher consumes these flattened gate fields and recomputes the
        # artifact hash immediately before browser task creation.
        **gates,
    }


def validate_browser_execution_record(record: Mapping[str, Any]) -> None:
    """Validate one generated record without blocking sibling applications."""
    if str(record.get("manifest_schema_version") or "") != MANIFEST_SCHEMA_VERSION:
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: application record schema version is missing")
    for key in ("application_id", "company", "title", "job_url", "application_method", "resume_path", "resume_sha256"):
        if not str(record.get(key) or "").strip():
            raise ManifestGenerationError(f"MANIFEST_VALIDATION_FAILED: application record is missing {key}")
    if record.get("application_mode") != ApplicationMode.AUTO_APPLY.value:
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: manifest contains a non-AUTO_APPLY record")
    if record.get("review_status") != "READY_FOR_REVIEW":
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: manifest review status is not READY_FOR_REVIEW")
    gates = record.get("all_gate_results")
    if not isinstance(gates, Mapping):
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: all_gate_results is missing")
    missing = [key for key in _REQUIRED_GATE_KEYS if gates.get(key) is not True or record.get(key) is not True]
    if missing:
        raise ManifestGenerationError(
            "MANIFEST_VALIDATION_FAILED: required gates are not true: " + ", ".join(missing)
        )
    artifact = record.get("resume_artifact")
    if not isinstance(artifact, Mapping):
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: resume_artifact is missing")
    if artifact.get("runtime_path") != record.get("resume_path") or artifact.get("sha256") != record.get("resume_sha256"):
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: resume artifact does not match flattened values")
    if not str(artifact.get("resume_library_reference") or "").strip():
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: durable Resume Library reference is missing")
    if record.get("human_controlled_blockers"):
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: human-controlled blockers must be empty")


def validate_browser_execution_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate generator-specific schema before a manifest is persisted or dispatched."""
    if str(manifest.get("schema_version") or "") != MANIFEST_SCHEMA_VERSION:
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: unsupported manifest schema version")
    records = manifest.get("applications")
    if not isinstance(records, list) or not records:
        raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: applications must be a non-empty list")
    for record in records:
        if not isinstance(record, Mapping):
            raise ManifestGenerationError("MANIFEST_VALIDATION_FAILED: application record must be an object")
        validate_browser_execution_record(record)


def _merge_manifest(path: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generator_version": MANIFEST_GENERATOR_VERSION,
        "generated_at": generated_at,
        "applications": [],
    }
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, Mapping) or existing.get("schema_version") != MANIFEST_SCHEMA_VERSION:
                raise ManifestGenerationError("MANIFEST_GENERATION_FAILED: existing manifest has an incompatible schema")
            manifest.update(dict(existing))
            manifest["generated_at"] = generated_at
        except (OSError, json.JSONDecodeError):
            # A malformed existing file must never be silently extended.
            raise ManifestGenerationError("MANIFEST_GENERATION_FAILED: existing manifest is unreadable or invalid")
    applications = [item for item in manifest.get("applications") or [] if isinstance(item, Mapping)]
    application_id = str(record["application_id"])
    manifest["applications"] = [item for item in applications if str(item.get("application_id") or "") != application_id] + [dict(record)]
    return manifest


def generate_browser_execution_manifest(
    result: Mapping[str, Any],
    *,
    browser_context: Mapping[str, Any] | None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Generate and optionally persist a verified manifest for one application.

    ``REVIEW_REQUIRED`` and ``DO_NOT_APPLY`` packages raise a structured error
    rather than producing an empty or misleading execution artifact.
    """
    if not isinstance(browser_context, Mapping):
        raise ManifestGenerationError("MANIFEST_GENERATION_FAILED: verified browser context is required")
    record = build_browser_execution_record(result, browser_context=browser_context)
    path = Path(output_path or os.getenv("BROWSER_EXECUTION_MANIFEST_PATH", "browser_execution_manifest.json"))
    manifest = _merge_manifest(path, record)
    validate_browser_execution_manifest(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
    manifest["manifest_path"] = str(path)
    return manifest
