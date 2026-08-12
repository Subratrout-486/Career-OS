import json
import os

import httpx

from .models import Job, FitReport, TailoredResume

TRUTH_RULES = """
Use only evidence supplied in MASTER_PROFILE. Never invent employers, dates, degree,
certifications, metrics, tools, responsibilities, production experience, or achievements.
Tailoring may reorder, emphasize, shorten, and rewrite supported facts. If evidence is
missing, mark it as a gap instead of creating it. A higher ATS score never justifies an
unsupported claim.
"""

FIT_PROMPT = f"""You are the Career OS JD & Fit Intelligence Agent.
{TRUTH_RULES}

Return ONLY valid JSON matching this exact shape:
{{
  "fit_score": 0,
  "recommendation": "APPLY|REVIEW|SKIP",
  "must_have_matches": [],
  "gaps": [],
  "blockers": [],
  "evidence": [],
  "keywords": [],
  "risks": [],
  "rationale": ""
}}
Score the candidate against the job, identify hard blockers separately from trainable gaps,
extract ATS keywords, and recommend APPLY only when the role is genuinely defensible.

MASTER_PROFILE:
{{profile}}

JOB:
{{job}}"""

RESUME_PROMPT = f"""You are the Career OS Resume Tailoring Agent.
{TRUTH_RULES}

Return ONLY valid JSON matching this exact shape:
{{
  "title": "",
  "summary": "",
  "skills": [],
  "experience": [{{"title":"","company":"","dates":"","bullets":[]}}],
  "education": [],
  "changes": [],
  "unsupported_claims": []
}}
Create one JD-specific resume from MASTER_PROFILE for this job. Preserve factual history and
actual job titles unless explicitly authorized. Optimize emphasis, ordering, wording and keyword
alignment. Keep unsupported_claims empty only when every claim is supported.

MASTER_PROFILE:
{{profile}}

FIT_REPORT:
{{fit}}

JOB:
{{job}}"""

CHALLENGE_PROMPT = f"""You are the Career OS Independent Challenge Agent.
{TRUTH_RULES}
Challenge the fit decision and tailored resume. Identify hidden blockers, overclaiming, weak
evidence, missing requirements, and reasons to skip or revise. Do not rewrite the resume.
Return concise plain text with sections: VERDICT, ISSUES, REQUIRED_FIXES.
"""


class AgentRuntime:
    """Multi-agent runtime backed by GitHub Models instead of paid provider API keys."""

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise RuntimeError("GITHUB_TOKEN is required for GitHub Models")
        self.model = os.getenv("GITHUB_MODEL", "openai/gpt-4.1-mini")
        self.endpoint = "https://models.github.ai/inference/chat/completions"

    async def _chat(self, system: str, user: str, *, json_mode: bool = False, max_tokens: int = 4000) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(self.endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"GitHub Models returned an unexpected response: {data}") from exc

    @staticmethod
    def _clean_json(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        json.loads(text)
        return text

    async def fit(self, profile: str, job: Job) -> FitReport:
        user = FIT_PROMPT.format(profile=profile, job=job.model_dump_json(indent=2))
        text = await self._chat(
            "You are a precise career fit analyst. Follow the supplied truth rules exactly.",
            user,
            json_mode=True,
            max_tokens=2500,
        )
        return FitReport.model_validate_json(self._clean_json(text))

    async def resume(self, profile: str, job: Job, fit: FitReport) -> TailoredResume:
        user = RESUME_PROMPT.format(
            profile=profile,
            fit=fit.model_dump_json(indent=2),
            job=job.model_dump_json(indent=2),
        )
        text = await self._chat(
            "You are a meticulous ATS resume editor. Follow the supplied truth rules exactly.",
            user,
            json_mode=True,
            max_tokens=5000,
        )
        return TailoredResume.model_validate_json(self._clean_json(text))

    async def challenge(self, profile: str, job: Job, fit: FitReport, resume: TailoredResume) -> str:
        user = (
            CHALLENGE_PROMPT
            + f"\n\nPROFILE:\n{profile}"
            + f"\n\nJOB:\n{job.model_dump_json(indent=2)}"
            + f"\n\nFIT:\n{fit.model_dump_json(indent=2)}"
            + f"\n\nRESUME:\n{resume.model_dump_json(indent=2)}"
        )
        return await self._chat(
            "You are an independent red-team career reviewer. Do not invent facts.",
            user,
            json_mode=False,
            max_tokens=2200,
        )
