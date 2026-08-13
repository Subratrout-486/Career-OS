import json
import os
import httpx
from .models import Job, FitReport, TailoredResume
from .structured_output import StructuredOutputError, extract_first_json_object

TRUTH_RULES = """
Use only evidence supplied in MASTER_PROFILE and the approved evidence pack. Never invent employers, dates, degrees, titles, metrics, tools, or responsibilities.
If a claim is not supported by evidence, omit it or mark it as needing confirmation.
Prefer precise, verifiable language over marketing hype.
"""

FIT_PROMPT = """
You are a rigorous career fit analyst. Follow the truth rules exactly.

{truth_rules}

Return a single JSON object matching this schema:
{{
  "fit_score": 0-100 integer,
  "recommendation": "APPLY" | "MAYBE" | "SKIP",
  "band": "A" | "B" | "C" | "D",
  "rationale": string,
  "must_have_matches": [string],
  "gaps": [string],
  "blockers": [string],
  "risks": [string],
  "confirmation_requests": [string]
}}
"""

RESUME_PROMPT = """
You are a meticulous ATS resume editor. Follow the truth rules exactly.

{truth_rules}

Produce a tailored resume as a single JSON object matching this schema:
{{
  "title": string,
  "summary": string,
  "skills": [string],
  "experience": [
    {{
      "employer": string,
      "title": string,
      "location": string,
      "start": string,
      "end": string,
      "bullets": [string]
    }}
  ],
  "changes": [string],
  "unsupported_claims": [string],
  "evidence_trace": [string]
}}

Every bullet and skill must be grounded in the supplied profile and evidence pack.
Do not invent metrics or tools.
"""

CHALLENGE_PROMPT = """
You are an independent red-team career reviewer. Do not invent facts.

{truth_rules}

Challenge the fit report and tailored resume. Call out:
- unsupported claims
- weak or missing evidence
- hard blockers for the role
- reasons to skip or revise

Return plain text notes (not JSON).
"""


class AgentRuntime:
    def __init__(self):
        self.provider = (os.getenv("AI_PROVIDER") or "auto").strip().lower()
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
        self.last_provider_used: str | None = None

        if self.provider not in {"auto", "github", "gemini"}:
            raise RuntimeError("AI_PROVIDER must be one of: auto, github, gemini")
        if self.provider == "github" and not self.github_token:
            raise RuntimeError("GITHUB_TOKEN is required when AI_PROVIDER=github")
        if self.provider == "gemini" and not self.gemini_key:
            raise RuntimeError("GEMINI_API_KEY is required when AI_PROVIDER=gemini")
        if self.provider == "auto" and not self.github_token and not self.gemini_key:
            # Still allow construction if only xAI/deepseek exist; _chat will surface errors.
            pass

    async def _chat_github(self, system, user, *, json_mode, max_tokens):
        payload = {
            "model": self.github_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.github_token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
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
            raise RuntimeError(f"GitHub Models returned an unexpected response: {data}") from exc

    async def _chat_gemini(self, system, user, *, json_mode, max_tokens):
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_tokens,
            },
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        headers = {
            "x-goog-api-key": self.gemini_key,
            "Content-Type": "application/json",
        }
        endpoint = self.gemini_endpoint.format(model=self.gemini_model)
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(endpoint, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        try:
            self.last_provider_used = f"gemini:{self.gemini_model}"
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
            "max_tokens": max_tokens,
            "temperature": 0.2,
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
            raise RuntimeError(f"DeepSeek returned an unexpected response: {data}") from exc

    async def _chat_xai(self, system, user, *, json_mode, max_tokens):
        """xAI Chat Completions (used by independent challenger and optional primary).

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
            "max_tokens": max_tokens,
            "temperature": 0.2,
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

        order: list[str] = []
        if self.provider == "github":
            order = ["github", "gemini", "xai", "deepseek"]
        elif self.provider == "gemini":
            order = ["gemini", "github", "xai", "deepseek"]
        else:  # auto
            order = ["github", "gemini", "xai", "deepseek"]

        for name in order:
            try:
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
            "All configured AI providers failed. " + " | ".join(errors) if errors else
            "No AI providers configured (need GITHUB_TOKEN, GEMINI_API_KEY, XAI_API_KEY, or DEEPSEEK_API_KEY)."
        )

    async def _structured_call(self, chat_fn, system, user, model_cls, *, json_mode, max_tokens):
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                raw = await chat_fn(system, user, json_mode=json_mode, max_tokens=max_tokens)
                cleaned = extract_first_json_object(raw)
                return model_cls.model_validate_json(cleaned)
            except (StructuredOutputError, Exception) as exc:
                last_err = exc
                # Retry once with a stricter instruction
                user = (
                    user
                    + "\n\nIMPORTANT: Reply with ONLY a single valid JSON object. "
                    "No markdown fences, no trailing commentary."
                )
        raise RuntimeError(f"Structured output failed after retries: {last_err}") from last_err

    async def analyze_fit(self, profile, job, evidence_pack=None):
        user = (
            FIT_PROMPT.format(truth_rules=TRUTH_RULES)
            + f"\n\nPROFILE:\n{profile}"
            + f"\n\nJOB:\n{job.model_dump_json(indent=2)}"
            + f"\n\nEVIDENCE_PACK:\n{json.dumps(evidence_pack or [], default=str, indent=2)}"
        )

        async def _prefer(system, user, *, json_mode, max_tokens):
            return await self._chat(system, user, json_mode=json_mode, max_tokens=max_tokens)

        return await self._structured_call(
            chat_fn=_prefer,
            system="You are a rigorous career fit analyst. Follow the supplied truth rules exactly.",
            user=user,
            model_cls=FitReport,
            json_mode=True,
            max_tokens=4000,
        )

    async def tailor_resume(self, profile, job, fit, evidence_pack=None):
        user = (
            RESUME_PROMPT.format(truth_rules=TRUTH_RULES)
            + f"\n\nPROFILE:\n{profile}"
            + f"\n\nJOB:\n{job.model_dump_json(indent=2)}"
            + f"\n\nFIT:\n{fit.model_dump_json(indent=2)}"
            + f"\n\nEVIDENCE_PACK:\n{json.dumps(evidence_pack or [], default=str, indent=2)}"
        )

        async def _prefer(system, user, *, json_mode, max_tokens):
            return await self._chat(system, user, json_mode=json_mode, max_tokens=max_tokens)

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
