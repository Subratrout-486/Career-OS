"""Career OS integrated pipeline orchestrator.

Flow:
  Job → active verification → JD analysis → live evidence vault → retrieve →
  fit → resume → deterministic truth guard → ATS → challenger → Notion review
  → Applications (Ready to Apply)

Production never silently falls back to the offline snapshot.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Sequence

from dotenv import load_dotenv

from .agents import AgentRuntime
from .ats_audit import audit_resume
from .evidence import EvidenceItem, retrieve_evidence
from .evidence_loader import VaultLoadError, load_evidence_vault
from .jd_analyzer import analyze_jd, requirements_for_retrieval
from .job_verify import verify_job_active
from .models import Job, JobVerificationModel, PipelineResult
from .notion import NotionReviewQueue
from .applications import ApplicationsTracker
from .application_mode import decide_application_mode
from .resume_files import generate_resume_files
from .truth_guard import validate_resume_truth
from .salary_intelligence import SalaryObservation, calculate_salary_intelligence

load_dotenv()


def collect_relevant_evidence(
    requirements: Sequence[str],
    vault: Sequence[EvidenceItem],
    *,
    include_all_usable: bool = True,
) -> list[EvidenceItem]:
    """Union of matched items across JD requirements, de-duplicated by claim+employer."""
    seen: set[tuple[str, str]] = set()
    ordered: list[EvidenceItem] = []
    for req in requirements:
        result = retrieve_evidence(req, vault, include_diagnostic=True)
        for match in result.matched:
            key = (match.item.claim, match.item.employer)
            if key not in seen:
                seen.add(key)
                ordered.append(match.item)
    if include_all_usable:
        for item in vault:
            if item.is_usable_professional:
                key = (item.claim, item.employer)
                if key not in seen:
                    seen.add(key)
                    ordered.append(item)
    return ordered


class CareerOS:
    def __init__(self, vault: Sequence[EvidenceItem] | None = None, write_to_notion: bool = True):
        self.runtime = AgentRuntime()
        self.notion = NotionReviewQueue()
        self.applications = ApplicationsTracker()
        self.write_to_notion = write_to_notion
        self._injected_vault = list(vault) if vault is not None else None

    def _load_vault(self) -> list[EvidenceItem]:
        if self._injected_vault is not None:
            return list(self._injected_vault)
        result = load_evidence_vault(use_cache=True)
        return result.items

    async def process(self, profile: str, job: Job) -> PipelineResult:
        errors: list[str] = []
        warnings: list[str] = []

        verification = verify_job_active(job)
        job_verification = JobVerificationModel(**verification.as_dict())

        if verification.status == "INACTIVE" or verification.active is False:
            return PipelineResult(
                job=job,
                job_verification=job_verification,
                fit=self._empty_fit("Job posting is inactive or unreachable"),
                application_mode="DO_NOT_APPLY",
                application_mode_reason="Application is blocked because the job is inactive or unreachable.",
                application_mode_blockers=["job is not verified ACTIVE"],
                review_status="INACTIVE_JOB",
                errors=list(verification.notes),
            )

        jd_analysis = analyze_jd(job)

        try:
            vault = self._load_vault()
        except VaultLoadError as exc:
            return PipelineResult(
                job=job,
                job_verification=job_verification,
                jd_analysis=jd_analysis,
                fit=self._empty_fit("Evidence vault unavailable"),
                review_status="EVIDENCE_VAULT_UNAVAILABLE",
                errors=[str(exc)],
            )

        usable = [e for e in vault if e.is_usable_professional]
        requirements = requirements_for_retrieval(jd_analysis)
        evidence_pack = collect_relevant_evidence(requirements, vault)
        fit_evidence_pack = collect_relevant_evidence(
            requirements, vault, include_all_usable=False
        )

        fit = await self.runtime.fit(profile, job, fit_evidence_pack, jd_analysis)
        if fit.recommendation == "SKIP" or fit.band == "D":
            return PipelineResult(
                job=job,
                job_verification=job_verification,
                jd_analysis=jd_analysis,
                fit=fit,
                application_mode="DO_NOT_APPLY",
                application_mode_reason="Career OS recommendation is SKIP.",
                application_mode_blockers=["Career OS recommendation is SKIP"],
                review_status="SKIPPED",
                evidence_count=len(vault),
                usable_evidence_count=len(usable),
            )

        try:
            resume = await self.runtime.resume(
                profile, job, fit, evidence_pack, jd_analysis
            )
        except Exception as exc:
            return PipelineResult(
                job=job,
                job_verification=job_verification,
                jd_analysis=jd_analysis,
                fit=fit,
                review_status="RESUME_GENERATION_FAILED",
                errors=[f"RESUME_GENERATION_FAILED: {exc}"],
                evidence_count=len(vault),
                usable_evidence_count=len(usable),
            )

        truth_issues = validate_resume_truth(
            resume=resume, profile=profile, fit=fit, evidence_pack=evidence_pack
        )
        # Optional AI rewrite when deterministic issues exist. Provider outage is
        # non-fatal: deterministic Truth Guard stays authoritative, original
        # resume is preserved, and status becomes AI_CORRECTION_NOT_AVAILABLE
        # instead of ERROR so Notion + Ready-to-Apply still proceed.
        ai_correction_unavailable = False
        if truth_issues:
            correction_profile = (
                profile
                + "\n\nHARD TRUTH-GUARD CORRECTION FEEDBACK. Revise the resume and remove/fix every item below. "
                "Do not invent replacements; if evidence is missing, omit the claim and record it in unsupported_claims.\n"
                + "\n".join(f"- {issue}" for issue in truth_issues)
            )
            try:
                revised = await self.runtime.resume(
                    correction_profile, job, fit, evidence_pack, jd_analysis
                )
                revised_issues = validate_resume_truth(
                    resume=revised, profile=profile, fit=fit, evidence_pack=evidence_pack
                )
                if not revised_issues:
                    resume = revised
                    truth_issues = []
                else:
                    truth_issues = revised_issues
            except Exception as exc:
                ai_correction_unavailable = True
                warnings.append(
                    f"AI_CORRECTION_NOT_AVAILABLE: correction providers unavailable — {exc}"
                )
                # Keep original resume; deterministic truth_issues remain for notes.

        if truth_issues:
            errors.extend(f"TRUTH_GUARD: {issue}" for issue in truth_issues)

        ats = None
        try:
            ats = audit_resume(jd=jd_analysis, resume=resume, vault=vault)
        except Exception as exc:
            errors.append(f"ATS_AUDIT_FAILED: {exc}")

        challenger = None
        try:
            challenger = await self.runtime.challenge(
                profile, job, fit, resume, evidence_pack
            )
            if challenger and challenger.startswith("INDEPENDENT CHALLENGER NOT RUN"):
                warnings.append(challenger)
        except Exception as exc:
            # Grok is an independent quality reviewer, not a prerequisite for
            # producing a truthful application package. Its failure is visible
            # but must not block a valid resume from reaching human review.
            challenger = f"INDEPENDENT CHALLENGER NOT RUN — {exc}"
            warnings.append(challenger)

        output_dir = os.getenv("RESUME_OUTPUT_DIR", "generated_resumes")
        resume_files = generate_resume_files(
            job.model_dump(), resume.model_dump(), output_dir
        )

        salary = calculate_salary_intelligence(
            [SalaryObservation(**item) for item in (job.salary_observations or []) if isinstance(item, dict)]
        )

        if ai_correction_unavailable:
            review_status = "AI_CORRECTION_NOT_AVAILABLE"
        elif errors:
            review_status = "ERROR"
        else:
            review_status = "READY_FOR_REVIEW"

        result = PipelineResult(
            job=job,
            job_verification=job_verification,
            jd_analysis=jd_analysis,
            fit=fit,
            resume=resume,
            ats=ats,
            salary=salary,
            challenger_notes=challenger,
            resume_files=resume_files,
            review_status=review_status,
            errors=errors,
            evidence_count=len(vault),
            usable_evidence_count=len(usable),
        )
        mode = decide_application_mode(result.model_dump())
        result.application_mode = mode.mode.value
        result.application_mode_reason = mode.reason
        result.application_mode_blockers = list(mode.blockers)
        if warnings:
            result.errors.extend([f"WARNING: {w}" for w in warnings])

        if self.write_to_notion:
            try:
                review_page_id, library_page_id = await self.notion.create_review_page(
                    result.model_dump()
                )
                result.review_page_id = review_page_id
                result.resume_library_page_id = library_page_id
            except Exception as exc:
                result.errors.append(f"NOTION_WRITE_FAILED: {exc}")
                result.review_status = "NOTION_WRITE_FAILED"

            try:
                app_id = await self.applications.create_review_record(result.model_dump())
                result.application_page_id = app_id
            except Exception as exc:
                result.errors.append(f"APPLICATIONS_TRACK_FAILED: {exc}")

        return result

    @staticmethod
    def _empty_fit(rationale: str):
        from .models import FitReport

        return FitReport(
            fit_score=0,
            recommendation="SKIP",
            band="D",
            rationale=rationale,
        )


def load_profile(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Career OS multi-agent pipeline")
    parser.add_argument("--profile", required=True)
    parser.add_argument(
        "--job-json",
        required=True,
        help="Path to a JSON file containing title/company/location/description",
    )
    parser.add_argument(
        "--no-notion-write",
        action="store_true",
        help="Pilot/test mode: run without writing Review, Resume Library, or Application records.",
    )
    parser.add_argument(
        "--offline-vault",
        action="store_true",
        help=(
            "TEST ONLY: use offline evidence snapshot instead of live Notion. "
            "Forbidden for production claims of complete evidence search."
        ),
    )
    args = parser.parse_args()
    profile = load_profile(args.profile)
    with open(args.job_json, "r", encoding="utf-8") as f:
        job = Job.model_validate(json.load(f))

    vault = None
    if args.offline_vault:
        from .evidence_vault_snapshot import VAULT_SNAPSHOT

        vault = VAULT_SNAPSHOT

    result = asyncio.run(
        CareerOS(vault=vault, write_to_notion=not args.no_notion_write).process(profile, job)
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
