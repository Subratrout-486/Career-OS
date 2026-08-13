import json
import os
import httpx
from .models import Job, FitReport, TailoredResume
from .structured_output import StructuredOutputError, extract_first_json_object

TRUTH_RULES = """
Use only evidence supplied in MASTER_PROFILE and the approved evidence pack. Never invent employers, dates, degree,
certifications, metrics, tools, responsibilities, production experience, or achievements.
Tailoring may reorder, emphasize, shorten, and rewrite supported facts. If evidence is missing, mark it as a gap.

CRITICAL EXPERIENCE-MAPPING RULE:
When a tool or skill is professionally confirmed for a specific employer, preserve that employer association in the
Experience section. Do not satisfy an ATS keyword by putting it only in Skills if the evidence supports placing it in
the relevant job's responsibilities.

Employer mapping must come from the approved evidence pack, not from historical resumes or hardcoded assumptions.
- FactSet professional evidence may be used only when the supplied item is Professional-Confirmed and Confirmed-by-User or Confirmed-by-Document.
- AWS/cloud application support, Python automation, ServiceNow, SQL/Oracle/PLSQL, Unix/Linux, Control-M, REST APIs/JSON/Postman,
  UAT/release validation, SOP/runbooks, and research/data operations must remain attributed to FactSet when the evidence pack maps them there.
- IGT group-reservations/backend-operations evidence is confirmed. Previously disputed IGT technical claims such as Python, SQL,
  Power Query, Power BI, REST API testing, and UAT remain Needs-Confirmation/Unconfirmed unless the current evidence pack explicitly
  marks them confirmed. Do not promote them because an old resume or target JD mentions them.
- Excel/Advanced Excel is unconfirmed unless the current evidence pack contains employer-specific confirmed evidence; do not add it
  as professional experience or attribute it to IGT.
- Concentrix technical troubleshooting, networking/connectivity, and CRM/ticketing may be used only when mapped by approved evidence.

Do not invent specific Salesforce objects, AWS services, modules, automations, reports, integrations, workflows or outcomes
that are not evidenced.
"""

FIT_PROMPT = """You are the Career OS JD & Fit Intelligence Agent.
{truth_rules}

Return ONLY valid JSON matching this exact shape:
{{
  \"fit_score\": 0,
  \"recommendation\": \"APPLY|APPLY-STRETCH|REVIEW|SKIP\",
  \"band\": \"A|B|C|D\",
  \"must_have_matches\": [],
  \"gaps\": [],
  \"blockers\": [],
  \"evidence\": [],
  \"keywords\": [],
  \"risks\": [],
  \"rationale\": \"\",
  \"requirement_matches\": [],
  \"confirmation_requests\": []
}}

Score the candidate against the job and identify hard blockers separately from trainable gaps.

IMPORTANT CONFIRMATION WORKFLOW:
- If the JD asks for a tool/skill that is NOT confirmed in MASTER_PROFILE/evidence, do not add it to the resume.
- If the candidate could plausibly have used it professionally but the source of truth does not confirm it, mark the requirement
  UNCONFIRMED and add a concise question to confirmation_requests, such as:
  \"JD requires Splunk. Did you use Splunk professionally at FactSet, IGT or another employer?\"
- Do not ask again for tools already explicitly confirmed in the source of truth. Those confirmations are reusable.
- A tool that is confirmed professionally must be mapped to its actual employer in requirement_matches.
- Unconfirmed tools must NOT be counted as confirmed must-have matches.
- Years-of-experience mismatch alone is not a reason to fabricate or automatically reject a defensible role.
- Excel/Advanced Excel is unconfirmed: surface as a gap/confirmation request, not a fabricated match, and do not auto-reject solely for Excel.

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
  \"title\": \"\",
  \"summary\": \"\",
  \"skills\": [],
  \"experience\": [{{\"title\":\"\",\"company\":\"\",\"dates\":\"\",\"bullets\":[]}}],
  \"education\": [],
  \"changes\": [],
  \"unsupported_claims\": [],
  \"evidence_trace\": []
}}

Create one JD-specific resume from MASTER_PROFILE for this job.

TAILORING REQUIREMENTS:
1. Preserve factual history, actual job titles and dates.
2. Build Experience from real responsibilities, not generic ATS keyword stuffing.
3. Put supported JD keywords in the responsibility bullet where the tool/skill was actually used.
4. Preserve employer-to-tool mapping. Python automation, AWS/ServiceNow belong to FactSet when relevant; Salesforce belongs to IGT when relevant.
5. Adapt wording, ordering and emphasis to the JD, but never copy unsupported target responsibilities into the candidate's history.
6. Do not invent specific actions for a tool merely because the JD mentions them.
7. Do not include any tool listed as UNCONFIRMED in the fit report unless it is separately confirmed in the approved evidence.
8. If confirmation_requests exist, keep the unconfirmed item out of the resume and list it in unsupported_claims/gaps.
9. Do not put Excel/Advanced Excel on the resume as professional experience until employer-specific confirmation exists.
10. Years-of-experience mismatch may be surfaced as a risk but never fabricated around.
11. evidence_trace should briefly map important tailored claims to the relevant employer/source evidence.

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
tools appear under the correct employer's Experience section when relevant. Verify that UNCONFIRMED tools (including Excel)
were not added. Do not rewrite the resume. Return concise plain text with sections: VERDICT, ISSUES, REQUIRED_FIXES.
"""


class AgentRuntime:
    def __init__(self):
        self.provider = os.getenv("AI_PROVIDER", "auto").lower()
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.github_model = os.getenv("GITHUB_MODEL", "openai/gpt-4.1-mini")
        self.github_endpoint = "https://models.github.ai/inference/chat/completions"
        self.gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.gemini_endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        )
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.deepseek_endpoint = "https://api.deepseek.com/chat/completions"
        self.xai_key = os.getenv("XAI_API_KEY")
        self.xai_model = os.getenv("XAI_MODEL") or os.getenv("GROK_MODEL") or "grok-4.6"
        self.xai_endpoint = "https://api.x.ai/v1/chat/completions"
        self.manus_key = os.getenv("OPENAI_API_KEY")
        self.manus_base = (os.getenv("OPENAI_API_BASE") or "").rstrip("/")
        self.manus_model = os.getenv("MANUS_MODEL", "gpt-5-mini")
        self.manus_endpoint = (
            f"{self.manus_base}/chat/completions" if self.manus_base else ""
        )
        self.last_provider_used: str | None = None

        if self.provider not in {"auto", "manus", "github", "gemini", "xai", "deepseek"}:
            raise RuntimeError(
                "AI_PROVIDER must be one of: auto, manus, github, gemini, xai, deepseek"
            )
        if self.provider == "github" and not self.github_token:
            raise RuntimeError(
                "GITHUB_TOKEN is required when AI_PROVIDER=github "
                "(note: GitHub Models retired 2026-07-30; prefer gemini/xai/deepseek)"
            )
        if self.provider == "gemini" and not self.gemini_key:
            raise RuntimeError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        if self.provider == "xai" and not self.xai_key:
            raise RuntimeError("XAI_API_KEY is required when AI_PROVIDER=xai")
        if self.provider == "deepseek" and not self.deepseek_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required when AI_PROVIDER=deepseek")
        if self.provider == "manus" and not (self.manus_key and self.manus_endpoint):
            raise RuntimeError(
                "OPENAI_API_KEY and OPENAI_API_BASE are required when AI_PROVIDER=manus"
            )
        if self.provider == "auto" and not any(
            [self.manus_key and self.manus_endpoint, self.github_token, self.gemini_key, self.xai_key, self.deepseek_key]
        ):
            raise RuntimeError(
                "At least one AI provider is required: Manus-managed OPENAI_API_KEY/OPENAI_API_BASE, "
                "GEMINI_API_KEY, XAI_API_KEY, DEEPSEEK_API_KEY, or GITHUB_TOKEN"
            )

    async def _chat_manus(self, system, user, *, json_mode, max_tokens):
        payload = {
            "model": self.manus_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.manus_model.startswith("gpt-"):
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.manus_key}",
            "Content-Type": "application/json",
        }
        request_timeout = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "45"))
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            response = await client.post(
                self.manus_endpoint, headers=headers, json=payload
            )
            response.raise_for_status()
            data = response.json()
        try:
            self.last_provider_used = f"manus:{self.manus_model}"
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Manus-managed model returned an unexpected response: {data}"
            ) from exc

    async def _chat_github(self, system, user, *, json_mode, max_tokens):
        payload = {
            "model": self.github_model,
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
            "Authorization": f"Bearer {self.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self.github_endpoint, headers=headers, json=payload
            )
            response.raise_for_status()
            data = response.json()
        try:
            self.last_provider_used = f"github:{self.github_model}"
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"GitHub Models returned an unexpected response: {data}"
            ) from exc

    async def _chat_gemini(self, system, user, *, json_mode, max_tokens):
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        headers = {
            "x-goog-api-key": self.gemini_key,
            "Content-Type": "application/json",
        }
        # Prefer configured model, then currently supported flash variants on
        # 503/429/404. Obsolete IDs (gemini-2.0-*, gemini-1.5-*) must not be
        # tried — they return 404 and waste cascade budget.
        candidates = [self.gemini_model]
        for alt in (
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash",
        ):
            if alt not in candidates:
                candidates.append(alt)
        last_exc: Exception | None = None
        data = None
        used_model = self.gemini_model
        async with httpx.AsyncClient(timeout=120) as client:
            for model in candidates:
                endpoint = self.gemini_endpoint.format(model=model)
                try:
                    response = await client.post(
                        endpoint, headers=headers, json=payload
                    )
                    if response.status_code in (429, 503, 500, 404):
                        last_exc = RuntimeError(
                            f"Gemini {response.status_code} for model {model}: "
                            f"{(response.text or '')[:200]}"
                        )
                        continue
                    response.raise_for_status()
                    data = response.json()
                    used_model = model
                    break
                except Exception as exc:
                    last_exc = exc
                    continue
        if data is None:
            raise RuntimeError(
                f"Gemini failed all model candidates {candidates}: {last_exc}"
            )
        try:
            self.last_provider_used = f"gemini:{used_model}"
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Gemini returned an unexpected response: {data}") from exc

    async def _chat_deepseek(self, system, user, *, json_mode, max_tokens):
        payload = {
            "model": self.deepseek_model,
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
            "Authorization": f"Bearer {self.deepseek_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self.deepseek_endpoint, headers=headers, json=payload
            )
            response.raise_for_status()
            data = response.json()
        try:
            self.last_provider_used = f"deepseek:{self.deepseek_model}"
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"DeepSeek returned an unexpected response: {data}"
            ) from exc

    async def _chat_xai(self, system, user, *, json_mode, max_tokens):
        """xAI Chat Completions (reserved for the independent challenger).

        HTTP 403 means the API key/team lacks endpoint or model permission in the
        xAI console — not a Career OS code defect. Never fall back to another
        provider from this method for the challenger path.
        """
        payload = {
            "model": self.xai_model,
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
            "Authorization": f"Bearer {self.xai_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self.xai_endpoint, headers=headers, json=payload
            )
            if response.status_code in (401, 403):
                body = (response.text or "")[:400]
                raise RuntimeError(
                    f"xAI {response.status_code}: API key or team lacks permission "
                    f"for model '{self.xai_model}' or the chat completions endpoint. "
                    "Fix in https://console.x.ai → API Keys: grant chat endpoint "
                    "and model access (or api-key:endpoint:* + api-key:model:*). "
                    f"Response snippet: {body}"
                )
            response.raise_for_status()
            data = response.json()
        try:
            self.last_provider_used = f"xai:{self.xai_model}"
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"xAI returned an unexpected response: {data}") from exc

    async def _chat(self, system, user, *, json_mode=False, max_tokens=4000):
        """Primary chat with resilient multi-provider fallback.

        Preferred provider is tried first when AI_PROVIDER is pinned, but any
        5xx / transport failure cascades to other configured providers so a
        single Gemini 503 cannot abort the whole pipeline.
        """
        errors: list[str] = []

        # GitHub Models retired 2026-07-30 (endpoint returns 410). Keep it last
        # for any residual tokens, but prefer live providers first.
        order: list[str] = []
        if self.provider == "manus":
            order = ["manus", "gemini", "deepseek", "github"]
        elif self.provider == "github":
            order = ["github", "manus", "gemini", "xai", "deepseek"]
        elif self.provider == "gemini":
            order = ["gemini", "manus", "xai", "deepseek", "github"]
        elif self.provider == "xai":
            order = ["xai", "manus", "gemini", "deepseek", "github"]
        elif self.provider == "deepseek":
            order = ["deepseek", "manus", "gemini", "xai", "github"]
        else:  # auto
            order = ["manus", "gemini", "xai", "deepseek", "github"]

        for name in order:
            try:
                if name == "manus" and self.manus_key and self.manus_endpoint:
                    return await self._chat_manus(
                        system, user, json_mode=json_mode, max_tokens=max_tokens
                    )
                if name == "github" and self.github_token:
                    return await self._chat_github(
                        system, user, json_mode=json_mode, max_tokens=max_tokens
                    )
                if name == "gemini" and self.gemini_key:
                    return await self._chat_gemini(
                        system, user, json_mode=json_mode, max_tokens=max_tokens
                    )
                if name == "xai" and self.xai_key:
                    return await self._chat_xai(
                        system, user, json_mode=json_mode, max_tokens=max_tokens
                    )
                if name == "deepseek" and self.deepseek_key:
                    return await self._chat_deepseek(
                        system, user, json_mode=json_mode, max_tokens=max_tokens
                    )
            except Exception as exc:
                errors.append(f"{name}: {exc}")
                continue

        raise RuntimeError(
            "All configured AI providers failed. " + " | ".join(errors)
        )

    async def _chat_prefer(
        self,
        preferred: str,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 4000,
    ) -> str:
        """Try a preferred specialty provider, then fall back to primary stack."""
        errors: list[str] = []
        if preferred == "deepseek" and self.deepseek_key:
            try:
                return await self._chat_deepseek(
                    system, user, json_mode=json_mode, max_tokens=max_tokens
                )
            except Exception as exc:
                errors.append(f"DeepSeek: {exc}")
        if preferred == "xai" and self.xai_key:
            try:
                return await self._chat_xai(
                    system, user, json_mode=json_mode, max_tokens=max_tokens
                )
            except Exception as exc:
                errors.append(f"xAI: {exc}")
        try:
            return await self._chat(
                system, user, json_mode=json_mode, max_tokens=max_tokens
            )
        except Exception as exc:
            if errors:
                raise RuntimeError(
                    "Preferred provider(s) failed, then primary failed. "
                    + " | ".join(errors)
                    + f" | Primary: {exc}"
                ) from exc
            raise

    @staticmethod
    def _clean_json(text: str) -> str:
        """Extract the first complete JSON object; ignore trailing extra data."""
        return extract_first_json_object(text)

    async def _structured_call(
        self,
        *,
        chat_fn,
        system: str,
        user: str,
        model_cls,
        json_mode: bool = True,
        max_tokens: int = 4000,
        max_attempts: int = 2,
    ):
        """Call the model and parse structured JSON with one retry on parse failure."""
        last_error: Exception | None = None
        prompt = user
        for attempt in range(1, max_attempts + 1):
            text = await chat_fn(
                system,
                prompt,
                json_mode=json_mode,
                max_tokens=max_tokens,
            )
            try:
                cleaned = self._clean_json(text)
                return model_cls.model_validate_json(cleaned)
            except (StructuredOutputError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                prompt = (
                    user
                    + "\n\nCRITICAL: Your previous response was not valid single-JSON. "
                    "Return ONLY one JSON object matching the required shape. "
                    "No markdown fences, no commentary, no second JSON object after the first."
                )
        raise RuntimeError(
            f"Structured output parse failed after {max_attempts} attempts: {last_error}"
        ) from last_error

    async def fit(self, profile, job, evidence_pack=None, jd_analysis=None):
        user = FIT_PROMPT.format(
            truth_rules=TRUTH_RULES,
            profile=profile,
            evidence_pack=json.dumps(evidence_pack or [], default=str, indent=2),
            jd_analysis=json.dumps(
                jd_analysis.model_dump()
                if hasattr(jd_analysis, "model_dump")
                else (jd_analysis or {}),
                indent=2,
            ),
            job=job.model_dump_json(indent=2),
        )
        return await self._structured_call(
            chat_fn=self._chat,
            system="You are a precise career fit analyst. Follow the supplied truth rules exactly.",
            user=user,
            model_cls=FitReport,
            json_mode=True,
            max_tokens=3000,
        )

    async def resume(self, profile, job, fit, evidence_pack=None, jd_analysis=None):
        user = RESUME_PROMPT.format(
            truth_rules=TRUTH_RULES,
            profile=profile,
            evidence_pack=json.dumps(evidence_pack or [], default=str, indent=2),
            fit=fit.model_dump_json(indent=2),
            jd_analysis=json.dumps(
                jd_analysis.model_dump()
                if hasattr(jd_analysis, "model_dump")
                else (jd_analysis or {}),
                indent=2,
            ),
            job=job.model_dump_json(indent=2),
        )
        async def _prefer(system, user, *, json_mode, max_tokens):
            return await self._chat_prefer(
                "deepseek", system, user, json_mode=json_mode, max_tokens=max_tokens
            )

        return await self._structured_call(
            chat_fn=_prefer,
            system="You are a meticulous ATS resume editor. Follow the supplied truth rules exactly.",
            user=user,
            model_cls=TailoredResume,
            json_mode=True,
            max_tokens=5000,
        )

    async def challenge(self, profile, job, fit, resume, evidence_pack=None):
        """Independent red-team review — MUST use xAI/Grok only.

        Never fall back to GitHub Models, Gemini, or DeepSeek for the challenger.
        A 403/401 is a user-side API key permission issue in console.x.ai.
        """
        if not self.xai_key:
            self.last_provider_used = None
            return (
                "INDEPENDENT CHALLENGER NOT RUN — XAI_API_KEY is not configured. "
                "Add secret XAI_API_KEY in GitHub Actions and grant the key chat + model "
                "permissions in https://console.x.ai. Do not treat any other model output "
                "as an independent review."
            )
        user = (
            CHALLENGE_PROMPT.format(truth_rules=TRUTH_RULES)
            + f"\n\nPROFILE:\n{profile}"
            + f"\n\nJOB:\n{job.model_dump_json(indent=2)}"
            + f"\n\nFIT:\n{fit.model_dump_json(indent=2)}"
            + f"\n\nRESUME:\n{resume.model_dump_json(indent=2)}"
            + f"\n\nEVIDENCE_PACK:\n{json.dumps(evidence_pack or [], default=str, indent=2)}"
        )
        try:
            return await self._chat_xai(
                "You are an independent red-team career reviewer. Do not invent facts.",
                user,
                json_mode=False,
                max_tokens=2500,
            )
        except Exception as exc:
            self.last_provider_used = None
            return (
                f"INDEPENDENT CHALLENGER NOT RUN — xAI request failed: {exc}. "
                "If this is HTTP 403/401, open https://console.x.ai → API Keys and grant "
                "endpoint (chat) + model permissions for this key (or wildcards "
                "api-key:endpoint:* and api-key:model:*). Do not treat any other model "
                "output as an independent review."
            )
