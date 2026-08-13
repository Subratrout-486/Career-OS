import json
import os
import httpx
from .models import Job, FitReport, TailoredResume

TRUTH_RULES = """
Use only evidence supplied in MASTER_PROFILE and the approved evidence pack. Never invent employers, dates, degree,
certifications, metrics, tools, responsibilities, production experience, or achievements.
Tailoring may reorder, emphasize, shorten, and rewrite supported facts. If evidence is missing, mark it as a gap.

CRITICAL EXPERIENCE-MAPPING RULE:
When a tool or skill is professionally confirmed for a specific employer, preserve that employer association in the
Experience section. Do not satisfy an ATS keyword by putting it only in Skills if the evidence supports placing it in
the relevant job's responsibilities.

Confirmed mappings that must be preserved:
- FactSet: AWS/cloud application support, ServiceNow, SQL/Oracle/PLSQL, Unix/Linux, Control-M, REST APIs/JSON/Postman,
  UAT/release validation, SOP/runbooks and research/data operations.
- IGT: Technical Operations Analyst / Associate (contract), Python, SQL, Power Query, Power BI, REST API testing, UAT,
  operational reporting/data validation, SOPs, and Salesforce professional use.
- Concentrix: technical troubleshooting, networking/connectivity areas and CRM/ticketing.

Do not invent specific Salesforce objects, AWS services, modules, automations, reports, integrations, workflows or outcomes
that are not evidenced.
"""

FIT_PROMPT = """You are the Career OS JD & Fit Intelligence Agent.
{truth_rules}

Return ONLY valid JSON matching this exact shape:
{{
  "fit_score": 0,
  "recommendation": "APPLY|APPLY-STRETCH|REVIEW|SKIP",
  "band": "A|B|C|D",
  "must_have_matches": [],
  "gaps": [],
  "blockers": [],
  "evidence": [],
  "keywords": [],
  "risks": [],
  "rationale": "",
  "requirement_matches": [],
  "confirmation_requests": []
}}

Score the candidate against the job and identify hard blockers separately from trainable gaps.

IMPORTANT CONFIRMATION WORKFLOW:
- If the JD asks for a tool/skill that is NOT confirmed in MASTER_PROFILE/evidence, do not add it to the resume.
- If the candidate could plausibly have used it professionally but the source of truth does not confirm it, mark the requirement
  UNCONFIRMED and add a concise question to confirmation_requests, such as:
  "JD requires Splunk. Did you use Splunk professionally at FactSet, IGT or another employer?"
- Do not ask again for tools already explicitly confirmed in the source of truth. Those confirmations are reusable.
- A tool that is confirmed professionally must be mapped to its actual employer in requirement_matches.
- Years-of-experience mismatch alone is not a reason to fabricate or automatically reject a defensible role.

MASTER_PROFILE:
{profile}

EVIDENCE_PACK:
{evidence_pack}

JD_ANALYSIS:
{jd_analysis}

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
  "unsupported_claims": [],
  "evidence_trace": []
}}

Create one JD-specific resume from MASTER_PROFILE for this job.

TAILORING REQUIREMENTS:
1. Preserve factual history, actual job titles and dates.
2. Build Experience from real responsibilities, not generic ATS keyword stuffing.
3. Put supported JD keywords in the responsibility bullet where the tool/skill was actually used.
4. Preserve employer-to-tool mapping. AWS/ServiceNow belong to FactSet when relevant; Salesforce belongs to IGT when relevant.
5. Adapt wording, ordering and emphasis to the JD, but never copy unsupported target responsibilities into the candidate's history.
6. Do not invent specific actions for a tool merely because the JD mentions them.
7. Do not include any tool listed as UNCONFIRMED in the fit report unless it is separately confirmed in the approved evidence.
8. If confirmation_requests exist, keep the unconfirmed item out of the resume and list it in unsupported_claims/gaps.
9. Years-of-experience mismatch may be surfaced as a risk but never fabricated around.
10. evidence_trace should briefly map important tailored claims to the relevant employer/source evidence.

MASTER_PROFILE:
{profile}

EVIDENCE_PACK:
{evidence_pack}

FIT_REPORT:
{fit}

JD_ANALYSIS:
{jd_analysis}

JOB:
{job}"""

CHALLENGE_PROMPT = """You are the Career OS Independent Challenge Agent.
{truth_rules}
Challenge the fit decision and tailored resume. Identify hidden blockers, overclaiming, weak evidence, missing requirements,
incorrect employer-to-tool mapping, keyword-only stuffing, and reasons to skip or revise. Verify that professionally confirmed
tools appear under the correct employer's Experience section when relevant. Verify that UNCONFIRMED tools were not added.
Do not rewrite the resume. Return concise plain text with sections: VERDICT, ISSUES, REQUIRED_FIXES.
"""

class AgentRuntime:
    def __init__(self):
        self.provider=os.getenv("AI_PROVIDER","auto").lower()
        self.github_token=os.getenv("GITHUB_TOKEN")
        self.github_model=os.getenv("GITHUB_MODEL","openai/gpt-4.1-mini")
        self.github_endpoint="https://models.github.ai/inference/chat/completions"
        self.gemini_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model=os.getenv("GEMINI_MODEL","gemini-3.1-flash-lite")
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
        payload={"systemInstruction":{"parts":[{"text":system}]},"contents":[{"role":"user","parts":[{"text":user}]}],"generationConfig":{"maxOutputTokens":max_tokens}}
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

    async def fit(self,profile,job,evidence_pack=None,jd_analysis=None):
        user=FIT_PROMPT.format(
            truth_rules=TRUTH_RULES, profile=profile,
            evidence_pack=json.dumps(evidence_pack or [], default=str, indent=2),
            jd_analysis=json.dumps(jd_analysis.model_dump() if hasattr(jd_analysis,"model_dump") else (jd_analysis or {}), indent=2),
            job=job.model_dump_json(indent=2),
        )
        text=await self._chat("You are a precise career fit analyst. Follow the supplied truth rules exactly.",user,json_mode=True,max_tokens=3000)
        return FitReport.model_validate_json(self._clean_json(text))

    async def resume(self,profile,job,fit,evidence_pack=None,jd_analysis=None):
        user=RESUME_PROMPT.format(
            truth_rules=TRUTH_RULES, profile=profile,
            evidence_pack=json.dumps(evidence_pack or [], default=str, indent=2),
            fit=fit.model_dump_json(indent=2),
            jd_analysis=json.dumps(jd_analysis.model_dump() if hasattr(jd_analysis,"model_dump") else (jd_analysis or {}), indent=2),
            job=job.model_dump_json(indent=2),
        )
        text=await self._chat("You are a meticulous ATS resume editor. Follow the supplied truth rules exactly.",user,json_mode=True,max_tokens=5000)
        return TailoredResume.model_validate_json(self._clean_json(text))

    async def challenge(self,profile,job,fit,resume,evidence_pack=None):
        user=CHALLENGE_PROMPT.format(truth_rules=TRUTH_RULES)+f"\n\nPROFILE:\n{profile}"+f"\n\nJOB:\n{job.model_dump_json(indent=2)}"+f"\n\nFIT:\n{fit.model_dump_json(indent=2)}"+f"\n\nRESUME:\n{resume.model_dump_json(indent=2)}"+f"\n\nEVIDENCE_PACK:\n{json.dumps(evidence_pack or [], default=str, indent=2)}"
        return await self._chat("You are an independent red-team career reviewer. Do not invent facts.",user,json_mode=False,max_tokens=2500)
