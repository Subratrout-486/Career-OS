"""Career OS integrated pipeline orchestrator.

Flow:
  Job → active verification → JD analysis → live evidence vault → retrieve →
  fit → resume → deterministic truth guard → ATS → challenger → Notion review
  → browser safety decision → Applications tracking.

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
from .design_qa import audit_resume_design
from .recruiter_review import classify_recruiter_review
from .resume_files import generate_resume_files
from .truth_guard import validate_resume_truth
from .salary_intelligence import SalaryObservation, calculate_salary_intelligence
from .browser_execution_manifest import ManifestGenerationError, generate_browser_execution_manifest

load_dotenv()


def collect_relevant_evidence(requirements: Sequence[str], vault: Sequence[EvidenceItem], *, include_all_usable: bool = True) -> list[EvidenceItem]:
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

    async def process(self, profile: str, job: Job, *, browser_context: dict[str, object] | None = None) -> PipelineResult:
        """Run the pipeline and classify the result for browser execution.

        Browser facts are optional during discovery. A later authenticated
        browser operator (e.g. Manus) can rerun this same pipeline with a
        verified browser-context JSON file. Only then can AUTO_APPLY be issued.
        """
        errors: list[str] = []
        warnings: list[str] = []
        browser_evidence = None
        if isinstance(browser_context, dict):
            candidate_evidence = browser_context.get("job_page_evidence") or browser_context.get("active_job_evidence")
            if isinstance(candidate_evidence, dict):
                browser_evidence = candidate_evidence
            elif browser_context.get("page_loaded") is not None:
                browser_evidence = browser_context
        verification = verify_job_active(job, browser_evidence=browser_evidence)
        job_verification = JobVerificationModel(**verification.as_dict())

        if verification.status == "INACTIVE" or verification.active is False:
            return PipelineResult(job=job, job_verification=job_verification, fit=self._empty_fit("Job posting is inactive or unreachable"), application_mode="DO_NOT_APPLY", application_mode_reason="Application is blocked because the job is inactive or unreachable.", application_mode_blockers=["job is not verified ACTIVE"], review_status="INACTIVE_JOB", errors=list(verification.notes))

        jd_analysis = analyze_jd(job)
        try:
            vault = self._load_vault()
        except VaultLoadError as exc:
            return PipelineResult(job=job, job_verification=job_verification, jd_analysis=jd_analysis, fit=self._empty_fit("Evidence vault unavailable"), review_status="EVIDENCE_VAULT_UNAVAILABLE", errors=[str(exc)])

        usable = [e for e in vault if e.is_usable_professional]
        requirements = requirements_for_retrieval(jd_analysis)
        evidence_pack = collect_relevant_evidence(requirements, vault)
        fit_evidence_pack = collect_relevant_evidence(requirements, vault, include_all_usable=False)
        fit = await self.runtime.fit(profile, job, fit_evidence_pack, jd_analysis)
        primary_recommendation_provider = self.runtime.last_provider_used or ""
        primary_recommendation = (
            "APPLY"
            if primary_recommendation_provider.lower().startswith("manus")
            and str(fit.recommendation or "").upper() == "APPLY"
            else ("SKIP" if str(fit.recommendation or "").upper() == "SKIP" else "NOT_RUN")
        )
        if fit.recommendation == "SKIP" or fit.band == "D":
            return PipelineResult(job=job, job_verification=job_verification, jd_analysis=jd_analysis, fit=fit, application_mode="DO_NOT_APPLY", application_mode_reason="Career OS recommendation is SKIP.", application_mode_blockers=["Career OS recommendation is SKIP"], review_status="SKIPPED", evidence_count=len(vault), usable_evidence_count=len(usable))

        try:
            resume = await self.runtime.resume(profile, job, fit, evidence_pack, jd_analysis)
        except Exception as exc:
            return PipelineResult(job=job, job_verification=job_verification, jd_analysis=jd_analysis, fit=fit, review_status="RESUME_GENERATION_FAILED", errors=[f"RESUME_GENERATION_FAILED: {exc}"], evidence_count=len(vault), usable_evidence_count=len(usable))

        truth_issues = validate_resume_truth(resume=resume, profile=profile, fit=fit, evidence_pack=evidence_pack)
        ai_correction_unavailable = False
        if truth_issues:
            correction_profile = profile + "\n\nHARD TRUTH-GUARD CORRECTION FEEDBACK. Revise the resume and remove/fix every item below. Do not invent replacements; if evidence is missing, omit the claim and record it in unsupported_claims.\n" + "\n".join(f"- {issue}" for issue in truth_issues)
            try:
                revised = await self.runtime.resume(correction_profile, job, fit, evidence_pack, jd_analysis)
                revised_issues = validate_resume_truth(resume=revised, profile=profile, fit=fit, evidence_pack=evidence_pack)
                if not revised_issues:
                    resume = revised
                    truth_issues = []
                else:
                    truth_issues = revised_issues
            except Exception as exc:
                ai_correction_unavailable = True
                warnings.append(f"AI_CORRECTION_NOT_AVAILABLE: correction providers unavailable — {exc}")

        if truth_issues:
            errors.extend(f"TRUTH_GUARD: {issue}" for issue in truth_issues)

        ats = None
        try:
            ats = audit_resume(jd=jd_analysis, resume=resume, vault=vault)
        except Exception as exc:
            errors.append(f"ATS_AUDIT_FAILED: {exc}")

        output_dir = os.getenv("RESUME_OUTPUT_DIR", "generated_resumes")
        resume_files = generate_resume_files(job.model_dump(), resume.model_dump(), output_dir)
        design_qa = audit_resume_design(resume_files)
        if not design_qa.get("passed"):
            warnings.append("DESIGN_QA_NOT_PASSED: " + "; ".join(design_qa.get("issues") or ["unknown design QA failure"]))

        challenger = None
        try:
            challenger = await self.runtime.challenge(profile, job, fit, resume, evidence_pack)
        except Exception as exc:
            challenger = f"INDEPENDENT CHALLENGER NOT RUN — {exc}"
        recruiter_review = classify_recruiter_review(challenger, self.runtime.last_provider_used)
        if recruiter_review.status != "PASS":
            warnings.extend(recruiter_review.warnings or ["Independent recruiter review did not pass."])

        salary = calculate_salary_intelligence([SalaryObservation(**item) for item in (job.salary_observations or []) if isinstance(item, dict)])
        review_status = "AI_CORRECTION_NOT_AVAILABLE" if ai_correction_unavailable else ("ERROR" if errors else "READY_FOR_REVIEW")

        observed_channel = str((browser_context or {}).get("application_channel") or (browser_context or {}).get("application_type") or "").strip() or None
        observed_application_url = str((browser_context or {}).get("application_url") or "").strip() or None
        observed_final_url = str((browser_context or {}).get("final_application_url") or "").strip() or None
        result = PipelineResult(
            job=job,
            job_verification=job_verification,
            jd_analysis=jd_analysis,
            fit=fit,
            resume=resume,
            ats=ats,
            recruiter_review=recruiter_review,
            gemini_diagnostic=dict(self.runtime.gemini_diagnostic),
            primary_recommendation_provider=primary_recommendation_provider,
            primary_recommendation=primary_recommendation,
            design_qa=design_qa,
            salary=salary,
            challenger_notes=challenger,
            resume_files=resume_files,
            review_status=review_status,
            errors=errors,
            evidence_count=len(vault),
            usable_evidence_count=len(usable),
            application_channel=observed_channel,
            application_url=observed_application_url,
            final_application_url=observed_final_url,
            application_destination_verified=bool((browser_context or {}).get("application_destination_verified") or (browser_context or {}).get("application_url_verified")),
        )
        mode = decide_application_mode(result.model_dump(), browser_context=browser_context)
        result.application_mode = mode.mode.value
        result.application_mode_reason = mode.reason
        result.application_mode_blockers = list(mode.blockers)
        if warnings:
            result.errors.extend([f"WARNING: {w}" for w in warnings])

        if self.write_to_notion:
            try:
                review_page_id, library_page_id = await self.notion.create_review_page(result.model_dump())
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
        return FitReport(fit_score=0, recommendation="SKIP", band="D", rationale=rationale)


def load_profile(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Career OS multi-agent pipeline")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--job-json", required=True, help="Path to a JSON file containing title/company/location/description")
    parser.add_argument("--browser-context-json", help="Optional verified browser observations produced by the authenticated browser executor")
    parser.add_argument("--no-notion-write", action="store_true", help="Pilot/test mode: run without writing Review, Resume Library, or Application records.")
    parser.add_argument("--offline-vault", action="store_true", help="TEST ONLY: use offline evidence snapshot instead of live Notion.")
    parser.add_argument("--result-output", help="Optional path for the full pipeline result JSON.")
    parser.add_argument("--manifest-output", help="Generate a verified browser-execution manifest at this path; requires a verified browser context and all AUTO_APPLY gates.")
    args = parser.parse_args()
    profile = load_profile(args.profile)
    with open(args.job_json, "r", encoding="utf-8") as f:
        job = Job.model_validate(json.load(f))
    browser_context = None
    if args.browser_context_json:
        with open(args.browser_context_json, "r", encoding="utf-8") as f:
            browser_context = json.load(f)
        if not isinstance(browser_context, dict):
            raise SystemExit("--browser-context-json must contain a JSON object")
    vault = None
    if args.offline_vault:
        from .evidence_vault_snapshot import VAULT_SNAPSHOT
        vault = VAULT_SNAPSHOT
    result = asyncio.run(CareerOS(vault=vault, write_to_notion=not args.no_notion_write).process(profile, job, browser_context=browser_context))
    result_data = result.model_dump()
    if args.manifest_output:
        try:
            manifest = generate_browser_execution_manifest(
                result_data,
                browser_context=browser_context,
                output_path=args.manifest_output,
            )
            result_data["browser_execution_manifest"] = manifest["manifest_path"]
        except ManifestGenerationError as exc:
            result_data.setdefault("errors", []).append(str(exc))
            result_data["review_status"] = "MANIFEST_GENERATION_FAILED"
    if args.result_output:
        with open(args.result_output, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2)
            f.write("\n")
    print(json.dumps(result_data, indent=2))


if __name__ == "__main__":
    main()
