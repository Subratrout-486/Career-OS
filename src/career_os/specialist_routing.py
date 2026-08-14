"""Specialist-provider routing for low-credit Manus orchestration.

Manus remains the execution/orchestration layer, while specialist providers
handle expensive reasoning tasks when their credentials are configured:

- DeepSeek: fit/JD analysis and resume review.
- xAI/Grok: first-pass JD-tailored resume drafting.

All specialist output is still validated by the existing Pydantic models and
Truth Guard. If a specialist is unavailable, Career OS falls back to the
existing AgentRuntime implementation rather than blocking the pipeline.
"""

from __future__ import annotations

import json
from typing import Any

from .agents import FIT_PROMPT, RESUME_PROMPT, TRUTH_RULES, AgentRuntime
from .models import FitReport, TailoredResume


REVIEW_PROMPT = """You are the Career OS DeepSeek Resume Review Agent.
{truth_rules}

Review the proposed JD-tailored resume below against the supplied fit report,
JD analysis, evidence pack, and master profile. Return ONLY one JSON object
matching the exact TailoredResume schema:
{{
  \"title\": \"\",
  \"summary\": \"\",
  \"skills\": [],
  \"experience\": [{{\"title\":\"\",\"company\":\"\",\"dates\":\"\",\"bullets\":[]}}],
  \"education\": [],
  \"changes\": [],
  \"unsupported_claims\": [],
  \"evidence_trace\": []
}}

Rules:
1. Keep every employer, title, and date factual.
2. Remove or rewrite any unsupported claim; never invent a replacement.
3. Preserve correct employer-to-tool mapping from the evidence pack.
4. Do not add JD keywords merely because the JD contains them.
5. Keep professionally confirmed tools under the employer where they were actually used.
6. Keep unconfirmed tools out of the resume and list them in unsupported_claims when relevant.
7. Keep the resume concise and one-page oriented; prioritize JD-relevant evidence.
8. Preserve strong supported content from the draft instead of rewriting it unnecessarily.
9. Do not fabricate metrics, certifications, projects, technologies, or responsibilities.
10. evidence_trace must map important tailored claims to source evidence.

MASTER_PROFILE:
{profile}

EVIDENCE_PACK:
{evidence_pack}

FIT_REPORT:
{fit}

JD_ANALYSIS:
{jd_analysis}

JOB:
{job}

DRAFT_RESUME:
{draft}
"""


async def _specialist_fit(runtime: AgentRuntime, profile: str, job: Any, evidence_pack: Any, jd_analysis: Any) -> FitReport:
    user = FIT_PROMPT.format(
        truth_rules=TRUTH_RULES,
        profile=profile,
        evidence_pack=json.dumps(evidence_pack or [], default=str, indent=2),
        jd_analysis=json.dumps(
            jd_analysis.model_dump() if hasattr(jd_analysis, "model_dump") else (jd_analysis or {}),
            indent=2,
        ),
        job=job.model_dump_json(indent=2),
    )
    text = await runtime._chat_deepseek(
        "You are a precise Career OS fit analyst. Follow the supplied truth rules exactly.",
        user,
        json_mode=True,
        max_tokens=3000,
    )
    return FitReport.model_validate_json(runtime._clean_json(text))


async def _specialist_resume_draft(runtime: AgentRuntime, profile: str, job: Any, fit: FitReport, evidence_pack: Any, jd_analysis: Any) -> TailoredResume:
    user = RESUME_PROMPT.format(
        truth_rules=TRUTH_RULES,
        profile=profile,
        evidence_pack=json.dumps(evidence_pack or [], default=str, indent=2),
        fit=fit.model_dump_json(indent=2),
        jd_analysis=json.dumps(
            jd_analysis.model_dump() if hasattr(jd_analysis, "model_dump") else (jd_analysis or {}),
            indent=2,
        ),
        job=job.model_dump_json(indent=2),
    )
    text = await runtime._chat_xai(
        "You are the Career OS JD-tailored resume drafting agent. Follow the supplied truth rules exactly.",
        user,
        json_mode=True,
        max_tokens=5000,
    )
    return TailoredResume.model_validate_json(runtime._clean_json(text))


async def _specialist_resume_review(runtime: AgentRuntime, profile: str, job: Any, fit: FitReport, resume: TailoredResume, evidence_pack: Any, jd_analysis: Any) -> TailoredResume:
    user = REVIEW_PROMPT.format(
        truth_rules=TRUTH_RULES,
        profile=profile,
        evidence_pack=json.dumps(evidence_pack or [], default=str, indent=2),
        fit=fit.model_dump_json(indent=2),
        jd_analysis=json.dumps(
            jd_analysis.model_dump() if hasattr(jd_analysis, "model_dump") else (jd_analysis or {}),
            indent=2,
        ),
        job=job.model_dump_json(indent=2),
        draft=resume.model_dump_json(indent=2),
    )
    text = await runtime._chat_deepseek(
        "You are the Career OS independent resume quality reviewer. Return only the corrected JSON resume.",
        user,
        json_mode=True,
        max_tokens=5000,
    )
    return TailoredResume.model_validate_json(runtime._clean_json(text))


def install_specialist_routing() -> bool:
    """Patch AgentRuntime once so specialist work bypasses Manus when possible.

    The patch is deliberately fail-open: provider outages or missing keys call
    the original implementation. This keeps existing production behavior and
    Truth Guard/Application Mode safeguards intact.
    """
    if getattr(AgentRuntime, "_specialist_routing_installed", False):
        return True

    original_fit = AgentRuntime.fit
    original_resume = AgentRuntime.resume

    async def routed_fit(self, profile, job, evidence_pack=None, jd_analysis=None):
        if self.deepseek_key:
            try:
                result = await _specialist_fit(self, profile, job, evidence_pack, jd_analysis)
                self.last_provider_used = "deepseek:fit"
                return result
            except Exception:
                pass
        return await original_fit(self, profile, job, evidence_pack, jd_analysis)

    async def routed_resume(self, profile, job, fit, evidence_pack=None, jd_analysis=None):
        # Grok drafts first; DeepSeek reviews and corrects the draft. If either
        # specialist is unavailable, fall back to the existing Career OS resume
        # path so the pipeline never loses availability.
        if self.xai_key:
            try:
                draft = await _specialist_resume_draft(
                    self, profile, job, fit, evidence_pack, jd_analysis
                )
                if self.deepseek_key:
                    try:
                        reviewed = await _specialist_resume_review(
                            self, profile, job, fit, draft, evidence_pack, jd_analysis
                        )
                        self.last_provider_used = "xai:grok-draft+deepseek:review"
                        return reviewed
                    except Exception:
                        pass
                self.last_provider_used = "xai:grok-draft"
                return draft
            except Exception:
                pass
        return await original_resume(self, profile, job, fit, evidence_pack, jd_analysis)

    AgentRuntime.fit = routed_fit
    AgentRuntime.resume = routed_resume
    AgentRuntime._specialist_routing_installed = True
    return True
