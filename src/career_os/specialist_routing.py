"""Specialist-provider routing for low-credit Manus orchestration.

Manus remains the execution/orchestration layer, while specialist providers
handle expensive reasoning tasks when their credentials are configured.

Provider routing is capability-aware: a configured specialist is preferred,
but a failed/unauthorized specialist must fall back to the resilient primary
stack so an available provider such as Gemini can continue the pipeline.
All specialist output is still validated by the existing Pydantic models and
Truth Guard.
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


async def _specialist_chat_prefer(
    runtime: AgentRuntime,
    preferred: str,
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    max_tokens: int = 4000,
    exclude_providers: set[str] | frozenset[str] | None = None,
) -> str:
    """Try a specialist once, then fall back without retrying that specialist.

    This intentionally does not call AgentRuntime._chat_prefer because the
    generic helper historically allowed the just-failed preferred provider to
    re-enter the primary cascade. Specialist routing must be bounded and
    should not spend another request on a provider already known to be down.
    """
    errors: list[str] = []
    excluded = {name.lower() for name in (exclude_providers or set())}
    preferred = preferred.lower()

    if preferred == "deepseek" and runtime.deepseek_key and preferred not in excluded:
        try:
            return await runtime._chat_deepseek(
                system, user, json_mode=json_mode, max_tokens=max_tokens
            )
        except Exception as exc:
            errors.append(f"DeepSeek: {exc}")
    elif preferred == "xai" and runtime.xai_key and preferred not in excluded:
        try:
            return await runtime._chat_xai(
                system, user, json_mode=json_mode, max_tokens=max_tokens
            )
        except Exception as exc:
            errors.append(f"xAI: {exc}")

    # The preferred provider has just been attempted and must not be retried
    # by the generic cascade. GitHub Models is retired and is also excluded
    # from specialist fallback so it cannot add a guaranteed 410 call.
    excluded.add(preferred)
    excluded.add("github")

    try:
        return await runtime._chat(
            system,
            user,
            json_mode=json_mode,
            max_tokens=max_tokens,
            exclude_providers=excluded,
        )
    except Exception as exc:
        if errors:
            raise RuntimeError(
                "Preferred specialist failed, then primary failed. "
                + " | ".join(errors)
                + f" | Primary: {exc}"
            ) from exc
        raise


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
    # DeepSeek is preferred for fit, but failure/403/402/transport errors must
    # flow into the normal provider cascade, where Gemini can be used. The
    # failed specialist is explicitly excluded from the second pass.
    text = await _specialist_chat_prefer(
        runtime,
        "deepseek",
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
    # xAI/Grok is preferred for the first draft, but the resilient primary stack
    # is the fallback. This prevents an xAI 403 from blocking resume generation.
    text = await _specialist_chat_prefer(
        runtime,
        "xai",
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
    # Keep Gemini out of the post-draft specialist review when it generated the
    # draft; the mandatory independent recruiter challenge remains separate.
    text = await _specialist_chat_prefer(
        runtime,
        "deepseek",
        "You are the Career OS independent resume quality reviewer. Return only the corrected JSON resume.",
        user,
        json_mode=True,
        max_tokens=5000,
        exclude_providers={"gemini"},
    )
    return TailoredResume.model_validate_json(runtime._clean_json(text))


def install_specialist_routing() -> bool:
    """Patch AgentRuntime so specialist work uses resilient provider fallback."""
    if getattr(AgentRuntime, "_specialist_routing_installed", False):
        return True

    original_fit = AgentRuntime.fit
    original_resume = AgentRuntime.resume

    async def routed_fit(self, profile, job, evidence_pack=None, jd_analysis=None):
        if self.deepseek_key:
            try:
                result = await _specialist_fit(self, profile, job, evidence_pack, jd_analysis)
                self.last_provider_used = self.last_provider_used or "deepseek:fit"
                return result
            except Exception:
                pass
        # Keep the existing path as a final safety net. The specialist path above
        # already permits Gemini through the resilient router.
        return await original_fit(self, profile, job, evidence_pack, jd_analysis)

    async def routed_resume(self, profile, job, fit, evidence_pack=None, jd_analysis=None):
        if self.xai_key:
            try:
                draft = await _specialist_resume_draft(
                    self, profile, job, fit, evidence_pack, jd_analysis
                )
                if self.deepseek_key and not str(self.last_provider_used or "").startswith("gemini:"):
                    try:
                        reviewed = await _specialist_resume_review(
                            self, profile, job, fit, draft, evidence_pack, jd_analysis
                        )
                        self.last_provider_used = f"{self.last_provider_used or 'xai:grok-draft'}+deepseek:review"
                        return reviewed
                    except Exception:
                        pass
                return draft
            except Exception:
                pass
        # When xAI is not configured, use the normal resilient resume path. Its
        # provider order can use Gemini and other live providers.
        return await original_resume(self, profile, job, fit, evidence_pack, jd_analysis)

    AgentRuntime.fit = routed_fit
    AgentRuntime.resume = routed_resume
    AgentRuntime._specialist_routing_installed = True
    return True
