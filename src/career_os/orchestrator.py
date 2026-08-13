from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .agents import AgentRuntime
from .applications import ApplicationsTracker
from .ats_audit import audit_resume
from .evidence import load_evidence_pack
from .evidence_loader import load_vault_evidence
from .jd_analyzer import analyze_jd
from .job_verify import verify_job
from .models import Job, PipelineResult
from .notion import NotionClient
from .resume_files import generate_resume_files
from .truth_guard import validate_resume_truth


class Orchestrator:
    def __init__(self):
        self.runtime = AgentRuntime()
        self.notion = NotionClient()
        self.applications = ApplicationsTracker()

    async def run(self, profile: str, job: Job) -> PipelineResult:
        errors: list[str] = []
        warnings: list[str] = []

        job_verification = verify_job(job)
        if not job_verification.active:
            return PipelineResult(
                job=job,
                job_verification=job_verification,
                review_status="INACTIVE_JOB",
                errors=[f"Job is not active: {job_verification.status}"],
            )

        try:
            vault = load_vault_evidence()
        except Exception as exc:
            return PipelineResult(
                job=job,
                job_verification=job_verification,
                review_status="EVIDENCE_VAULT_UNAVAILABLE",
                errors=[f"Evidence vault unavailable: {exc}"],
            )

        usable = [item for item in vault if getattr(item, "usable_for_resume", True)]
        evidence_pack = load_evidence_pack(vault)

        jd_analysis = analyze_jd(job)

        try:
            fit = await self.runtime.fit(profile, job, evidence_pack, jd_analysis)
        except Exception as exc:
            return PipelineResult(
                job=job,
                job_verification=job_verification,
                jd_analysis=jd_analysis,
                review_status="SKIPPED",
                errors=[f"FIT_FAILED: {exc}"],
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
            challenger_notes=challenger,
            resume_files=resume_files,
            review_status=review_status,
            errors=errors,
            evidence_count=len(vault),
            usable_evidence_count=len(usable),
        )
        if warnings:
            result.errors.extend([f"WARNING: {w}" for w in warnings])

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


def _load_profile(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _load_job(path: str) -> Job:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Job.model_validate(data)


async def _amain() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Career OS pipeline")
    parser.add_argument("--profile", required=True, help="Path to master profile markdown")
    parser.add_argument("--job-json", required=True, help="Path to job JSON")
    args = parser.parse_args()
    profile = _load_profile(args.profile)
    job = _load_job(args.job_json)
    orchestrator = Orchestrator()
    result = await orchestrator.run(profile, job)
    print(json.dumps(result.model_dump(), indent=2, default=str))


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
