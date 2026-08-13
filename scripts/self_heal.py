#!/usr/bin/env python3
"""Bounded autonomous self-heal for Career OS CI failures.

Safety:
- Maximum one repair proposal per invocation (caller enforces one attempt per run).
- Never weakens Truth Guard, Evidence Vault rules, xAI-only challenger, or Ready-to-Apply.
- Never fabricates career evidence or modifies secrets / master profile claims.
- Only allowlisted paths may be patched.
- Caller must run the full test suite and refuse to commit on failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Paths the repair agent is allowed to touch (repo-relative).
ALLOWLIST_PREFIXES = (
    "src/career_os/",
    ".github/workflows/",
    "tests/",
    "scripts/",
    "pyproject.toml",
    "README.md",
    "docs/",
)

# Explicitly forbidden even if under an allowlisted prefix.
FORBIDDEN_EXACT = {
    "config/master_profile.md",
    ".env",
    ".env.example",
}
FORBIDDEN_SUBSTRINGS = (
    "secret",
    "credential",
    "master_profile",
    "evidence_vault_snapshot",
)

# Files whose core safety contracts must not be diluted.
PROTECTED_MODULES = {
    "src/career_os/truth_guard.py",
    "src/career_os/evidence.py",
    "src/career_os/evidence_loader.py",
}

GEMINI_CANDIDATES = (
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
)

SYSTEM_PROMPT = """You are the Career OS bounded self-heal engineer.

Return ONLY one JSON object with this exact shape:
{
  "diagnosable": true,
  "root_cause": "one paragraph",
  "safe_to_auto_repair": true,
  "reason_if_unsafe": "",
  "summary": "short commit-message style summary",
  "patches": [
    {
      "path": "relative/path.py",
      "action": "replace",
      "content": "full new file content"
    }
  ]
}

Rules:
1. Prefer the smallest change that fixes the observed CI/runtime failure.
2. safe_to_auto_repair must be false for: missing secrets, xAI credit/permission issues,
   Notion permission issues, user-side configuration, evidence fabrication requests,
   or any change that weakens Truth Guard / Evidence Vault / xAI-only challenger /
   Ready-to-Apply human gate / AI_CORRECTION_NOT_AVAILABLE non-fatal behavior.
3. Never invent career evidence, employers, tools, metrics, or dates.
4. Never modify secrets, .env, master_profile.md, or evidence vault snapshot claims.
5. Never remove or bypass validate_resume_truth, independent challenge xAI-only path,
   or Applications status "Ready to Apply".
6. Preserve Gemini cascade on 404/503 and non-fatal AI correction outage handling.
7. patches may only target: src/career_os/*.py, .github/workflows/*.yml, tests/*, scripts/*,
   pyproject.toml, README.md, docs/*.
8. For protected modules (truth_guard.py, evidence.py, evidence_loader.py) only fix clear
   bugs; do not relax validation.
9. If logs show only provider outage / 403 credits / missing secret, set
   safe_to_auto_repair=false and patches=[].
10. content must be the complete new file body for each patched path (action=replace only).
"""


def _gh_request(url: str, token: str, method: str = "GET", body: dict | None = None) -> Any:
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "career-os-self-heal",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"GitHub API {exc.code} for {url}: {detail}") from exc


def fetch_failed_logs(owner: str, repo: str, run_id: int, token: str, max_chars: int = 24000) -> str:
    jobs = _gh_request(
        f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
        token,
    )
    job_list = (jobs or {}).get("jobs") or []
    chunks: list[str] = []
    for job in job_list:
        if job.get("conclusion") not in {"failure", "cancelled", "timed_out"}:
            if job.get("conclusion") == "success":
                continue
        job_id = job.get("id")
        name = job.get("name")
        chunks.append(f"=== JOB {name} conclusion={job.get('conclusion')} ===")
        for step in job.get("steps") or []:
            if step.get("conclusion") in {"failure", "cancelled", "timed_out"}:
                chunks.append(
                    f"-- step: {step.get('name')} conclusion={step.get('conclusion')}"
                )
        if not job_id:
            continue
        log_url = f"https://api.github.com/repos/{owner}/{repo}/actions/jobs/{job_id}/logs"
        try:
            req = urllib.request.Request(
                log_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "career-os-self-heal",
                },
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                text = resp.read().decode("utf-8", errors="replace")
            tail = text[-max_chars:] if len(text) > max_chars else text
            chunks.append(tail)
        except Exception as exc:  # noqa: BLE001
            chunks.append(f"(log fetch failed for job {job_id}: {exc})")
    if not chunks:
        chunks.append(json.dumps(job_list, indent=2)[:max_chars])
    return "\n".join(chunks)[-max_chars:]


def call_gemini(system: str, user: str, api_key: str, preferred_model: str) -> str:
    candidates = [preferred_model]
    for alt in GEMINI_CANDIDATES:
        if alt not in candidates:
            candidates.append(alt)
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
    }
    last_err: Exception | None = None
    for model in candidates:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    raise RuntimeError(f"Gemini cascade failed: {last_err}")


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("No JSON object in model response")
    return json.loads(text[start : end + 1])


def path_allowed(rel: str) -> bool:
    rel = rel.replace("\\", "/").lstrip("./")
    if rel in FORBIDDEN_EXACT:
        return False
    lower = rel.lower()
    if any(s in lower for s in FORBIDDEN_SUBSTRINGS):
        return False
    if not any(rel == p or rel.startswith(p) for p in ALLOWLIST_PREFIXES):
        return False
    return True


def apply_patches(repo_root: Path, patches: list[dict]) -> list[str]:
    applied: list[str] = []
    for patch in patches:
        path = str(patch.get("path") or "").replace("\\", "/").lstrip("./")
        action = patch.get("action") or "replace"
        content = patch.get("content")
        if action != "replace" or content is None:
            raise RuntimeError(f"Unsupported patch action for {path}: {action}")
        if not path_allowed(path):
            raise RuntimeError(f"Refusing non-allowlisted path: {path}")
        if path in PROTECTED_MODULES:
            if "def validate_resume_truth" in Path(repo_root / path).read_text(
                encoding="utf-8", errors="replace"
            ):
                if "validate_resume_truth" not in content and path.endswith(
                    "truth_guard.py"
                ):
                    raise RuntimeError(
                        "Refusing patch that removes validate_resume_truth"
                    )
        target = repo_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        applied.append(path)
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Career OS bounded self-heal")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--workflow-name", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--out", default="self_heal_result.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    gemini_model = os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite"
    if not token:
        print("GITHUB_TOKEN required", file=sys.stderr)
        return 2
    if not gemini_key:
        print("GEMINI_API_KEY required", file=sys.stderr)
        return 2

    logs = fetch_failed_logs(args.owner, args.repo, args.run_id, token)
    user = (
        f"Failed workflow: {args.workflow_name}\n"
        f"Run ID: {args.run_id}\n"
        f"Head SHA: {args.head_sha}\n\n"
        f"=== FAILED JOB LOGS (tail) ===\n{logs}\n"
    )
    try:
        raw = call_gemini(SYSTEM_PROMPT, user, gemini_key, gemini_model)
        plan = extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        plan = {
            "diagnosable": False,
            "root_cause": f"Self-heal diagnosis failed: {exc}",
            "safe_to_auto_repair": False,
            "reason_if_unsafe": str(exc),
            "summary": "diagnosis-failed",
            "patches": [],
        }

    plan.setdefault("patches", [])
    plan.setdefault("safe_to_auto_repair", False)
    plan["applied_paths"] = []
    plan["apply_error"] = None

    if args.apply and plan.get("safe_to_auto_repair") and plan.get("patches"):
        try:
            plan["applied_paths"] = apply_patches(
                Path(args.repo_root).resolve(), plan["patches"]
            )
        except Exception as exc:  # noqa: BLE001
            plan["apply_error"] = str(exc)
            plan["safe_to_auto_repair"] = False
            plan["applied_paths"] = []

    out_path = Path(args.out)
    out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(json.dumps(plan, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
