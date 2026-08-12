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

FIT_PROMPT = """You are the Career OS JD & Fit Intelligence Agent.
{truth_rules}

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
{profile}

JOB:
{job}"""

RESUME_PROMPT = """You are the Career OS Resume Tailoring Agent.
{truth_rules}

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
{profile}

FIT_REPORT:
{fit}

JOB:
{job}"""

CHALLENGE_PROMPT = """You are the Career OS Independent Challenge Agent.
{truth_rules}
Challenge the fit decision and tailored resume. Identify hidden blockers, overclaiming, weak
evidence, missing requirements, and reasons to skip or revise. Do not rewrite the resume.
Return concise plain text with sections: VERDICT, ISSUES, REQUIRED_FIXES.
"""

class AgentRuntime:
    def __init__(self):
        self.provider=os.getenv("AI_PROVIDER","auto").lower()
        self.github_token=os.getenv("GITHUB_TOKEN")
        self.github_model=os.getenv("GITHUB_MODEL","openai/gpt-4.1-mini")
        self.github_endpoint="https://models.github.ai/inference/chat/completions"
        self.gemini_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
        self.gemini_endpoint="https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        if self.provider not in {"auto","github","gemini"}: raise RuntimeError("AI_PROVIDER must be one of: auto, github, gemini")
        if self.provider=="github" and not self.github_token: raise RuntimeError("GITHUB_TOKEN is required when AI_PROVIDER=github")
        if self.provider=="gemini" and not self.gemini_key: raise RuntimeError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        if self.provider=="auto" and not self.github_token and not self.gemini_key: raise RuntimeError("At least one AI provider is required: GITHUB_TOKEN or GEMINI_API_KEY")

    async def _chat_github(self,system,user,*,json_mode,max_tokens):
        payload={"model":self.github_model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"temperature":0.1,"max_tokens":max_tokens}
        if json_mode: payload["response_format"]={"type":"json_object"}
        headers={"Accept":"application/vnd.github+json","Authorization":f"Bearer {self.github_token}","X-GitHub-Api-Version":"2022-11-28","Content-Type":"application/json"}
        async with httpx.AsyncClient(timeout=120) as client:
            response=await client.post(self.github_endpoint,headers=headers,json=payload); response.raise_for_status(); data=response.json()
        try: return data["choices"][0]["message"]["content"].strip()
        except (KeyError,IndexError,TypeError) as exc: raise RuntimeError(f"GitHub Models returned an unexpected response: {data}") from exc

    async def _chat_gemini(self,system,user,*,json_mode,max_tokens):
        payload={"systemInstruction":{"parts":[{"text":system}]},"contents":[{"role":"user","parts":[{"text":user}]}],"generationConfig":{"temperature":0.1,"maxOutputTokens":max_tokens}}
        if json_mode: payload["generationConfig"]["responseMimeType"]="application/json"
        headers={"x-goog-api-key":self.gemini_key,"Content-Type":"application/json"}
        endpoint=self.gemini_endpoint.format(model=self.gemini_model)
        async with httpx.AsyncClient(timeout=120) as client:
            response=await client.post(endpoint,headers=headers,json=payload); response.raise_for_status(); data=response.json()
        try: return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError,IndexError,TypeError) as exc: raise RuntimeError(f"Gemini returned an unexpected response: {data}") from exc

    async def _chat(self,system,user,*,json_mode=False,max_tokens=4000):
        errors=[]
        if self.provider in {"auto","github"} and self.github_token:
            try: return await self._chat_github(system,user,json_mode=json_mode,max_tokens=max_tokens)
            except Exception as exc:
                errors.append(f"GitHub Models: {exc}")
                if self.provider=="github": raise RuntimeError("GitHub Models request failed: "+str(exc)) from exc
        if self.provider in {"auto","gemini"} and self.gemini_key:
            try: return await self._chat_gemini(system,user,json_mode=json_mode,max_tokens=max_tokens)
            except Exception as exc: errors.append(f"Gemini: {exc}")
        raise RuntimeError("All configured AI providers failed. "+" | ".join(errors))

    @staticmethod
    def _clean_json(text):
        text=text.strip()
        if text.startswith("```"):
            lines=text.splitlines()
            if lines and lines[0].startswith("```"): lines=lines[1:]
            if lines and lines[-1].strip()=="```": lines=lines[:-1]
            text="\n".join(lines).strip()
        start,end=text.find("{"),text.rfind("}")
        if start>=0 and end>start: text=text[start:end+1]
        json.loads(text); return text

    async def fit(self,profile,job):
        user=FIT_PROMPT.format(truth_rules=TRUTH_RULES,profile=profile,job=job.model_dump_json(indent=2))
        text=await self._chat("You are a precise career fit analyst. Follow the supplied truth rules exactly.",user,json_mode=True,max_tokens=2500)
        return FitReport.model_validate_json(self._clean_json(text))

    async def resume(self,profile,job,fit):
        user=RESUME_PROMPT.format(truth_rules=TRUTH_RULES,profile=profile,fit=fit.model_dump_json(indent=2),job=job.model_dump_json(indent=2))
        text=await self._chat("You are a meticulous ATS resume editor. Follow the supplied truth rules exactly.",user,json_mode=True,max_tokens=5000)
        return TailoredResume.model_validate_json(self._clean_json(text))

    async def challenge(self,profile,job,fit,resume):
        user=CHALLENGE_PROMPT.format(truth_rules=TRUTH_RULES)+f"\n\nPROFILE:\n{profile}"+f"\n\nJOB:\n{job.model_dump_json(indent=2)}"+f"\n\nFIT:\n{fit.model_dump_json(indent=2)}"+f"\n\nRESUME:\n{resume.model_dump_json(indent=2)}"
        return await self._chat("You are an independent red-team career reviewer. Do not invent facts.",user,json_mode=False,max_tokens=2200)
