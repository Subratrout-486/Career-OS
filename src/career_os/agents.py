import os
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from .models import Job, FitReport, TailoredResume
from .grok import challenge_with_grok

TRUTH_RULES = """
Use only evidence supplied in MASTER_PROFILE. Never invent employers, dates, degree, certifications, metrics, tools, responsibilities, production experience, or achievements. Tailoring may reorder, emphasize, shorten, and rewrite supported facts. If evidence is missing, mark it as a gap instead of creating it. A higher ATS score never justifies an unsupported claim.
"""
FIT_PROMPT = f"""You are the Career OS JD & Fit Intelligence Agent.\n{TRUTH_RULES}\n\nReturn JSON matching FitReport. Score the candidate against the job, identify hard blockers separately from trainable gaps, extract ATS keywords, and recommend APPLY only when the role is genuinely defensible.\n\nMASTER_PROFILE:\n{{profile}}\n\nJOB:\n{{job}}"""
RESUME_PROMPT = f"""You are the Career OS Resume Tailoring Agent.\n{TRUTH_RULES}\n\nCreate one JD-specific resume from the MASTER_PROFILE for this job. Preserve factual history and actual job titles unless the user explicitly authorizes a change. Optimize emphasis, ordering, wording and keyword alignment. Return JSON matching TailoredResume. Include unsupported_claims and keep it empty only when every claim is supported.\n\nMASTER_PROFILE:\n{{profile}}\n\nFIT_REPORT:\n{{fit}}\n\nJOB:\n{{job}}"""
CHALLENGE_PROMPT = f"""Act as an independent career reviewer. {TRUTH_RULES} Challenge the fit decision and tailored resume. Identify hidden blockers, overclaiming, weak evidence, or reasons to skip. Do not rewrite the resume."""

class AgentRuntime:
    def __init__(self):
        self.openai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.anthropic = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY")) if os.environ.get("ANTHROPIC_API_KEY") else None

    async def fit(self, profile: str, job: Job) -> FitReport:
        prompt = FIT_PROMPT.format(profile=profile, job=job.model_dump_json(indent=2))
        response = await self.openai.responses.create(
            model=os.getenv("OPENAI_MODEL") or "gpt-5.6", input=prompt,
            text={"format": {"type": "json_object"}},
        )
        return FitReport.model_validate_json(response.output_text)

    async def resume(self, profile: str, job: Job, fit: FitReport) -> TailoredResume:
        if not self.anthropic:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the Claude Resume Agent")
        prompt = RESUME_PROMPT.format(profile=profile, fit=fit.model_dump_json(indent=2), job=job.model_dump_json(indent=2))
        msg = await self.anthropic.messages.create(
            model=os.getenv("CLAUDE_MODEL") or "claude-sonnet-4-5", max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", None) == "text")
        return TailoredResume.model_validate_json(text)

    async def challenge(self, profile: str, job: Job, fit: FitReport, resume: TailoredResume) -> str:
        prompt = CHALLENGE_PROMPT + f"\n\nPROFILE:\n{profile}\n\nJOB:\n{job.model_dump_json()}\n\nFIT:\n{fit.model_dump_json()}\n\nRESUME:\n{resume.model_dump_json()}"
        return await challenge_with_grok(prompt)
