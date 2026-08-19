"""Truthful department/agent registry for the Career OS control plane.

The registry is intentionally separate from the legacy bootstrap list so the
platform can add departments without rewriting the storage/router contracts.
Availability is derived only from explicit runtime configuration; a connector
shown in the UI is never treated as an executable provider automatically.
"""

from __future__ import annotations

import os

from .control_plane import AgentRecord, ControlPlaneStore, ModelRecord, utc_now


DEPARTMENTS = [
    ("job-discovery", "Job Discovery / Intake", "discovery", ["discover", "deduplicate"]),
    ("gmail-intake", "Gmail Intake", "gmail", ["ingest", "classify", "deduplicate"]),
    ("linkedin-intake", "LinkedIn / Browser Capture", "browser", ["capture", "verify"]),
    ("jd-enrichment", "JD Enrichment", "jd", ["fetch", "extract", "validate"]),
    ("company-research", "Company Research", "research", ["research", "summarize"]),
    ("evidence-retrieval", "Evidence Retrieval", "notion", ["retrieve", "provenance"]),
    ("fit-analysis", "Fit Analysis", "fit", ["match", "score", "gap-analysis"]),
    ("resume", "Resume Generation", "resume", ["generation", "tailoring"]),
    ("truth-guardian", "Truth Guard", "quality", ["validate", "provenance"]),
    ("ats", "ATS Validation", "ats", ["score", "parse", "validate"]),
    ("independent-review", "Independent Reviewer", "review", ["challenge", "validate"]),
    ("recruiter-outreach", "Recruiter Outreach", "outreach", ["draft"]),
    ("application-tracking", "Application Tracking", "notion", ["track", "sync"]),
    ("browser-execution", "Browser / Manus Execution", "browser", ["execute", "verify"]),
    ("observability", "Observability", "sentry", ["diagnose", "correlate"]),
    ("engineering-repair", "Engineering Repair", "engineering", ["inspect", "modify", "test"]),
    ("product-ui", "Product / UI", "ui", ["present", "inspect"]),
]


def _available(provider: str) -> str:
    env_map = {
        "gmail": ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"),
        "notion": ("NOTION_TOKEN", "NOTION_API_KEY"),
        "browser": ("MANUS_API_KEY",),
        "sentry": ("SENTRY_DSN", "SENTRY_AUTH_TOKEN"),
        "research": ("OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY"),
        "fit": ("OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY"),
        "resume": ("OPENAI_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "DEEPSEEK_API_KEY"),
        "review": ("GEMINI_API_KEY", "XAI_API_KEY"),
    }
    keys = env_map.get(provider, ())
    if not keys:
        return "AVAILABLE"
    return "AVAILABLE" if any(os.getenv(key) for key in keys) else "DEGRADED"


def bootstrap_department_registry(store: ControlPlaneStore) -> None:
    """Register the full operating model without inventing connectivity."""
    now = utc_now()
    for agent_id, name, provider, capabilities in DEPARTMENTS:
        availability = _available(provider)
        store.register_agent(AgentRecord(
            id=agent_id,
            name=name,
            department=agent_id,
            provider=provider,
            capabilities=capabilities,
            availability=availability,
            last_seen=now,
            metadata={
                "fallback_policy": "route_to_next_available_capable_worker",
                "human_boundary": "required_for_application_submission" if agent_id == "browser-execution" else None,
            },
        ))

    providers = [
        ("openai", "openai", os.getenv("OPENAI_MODEL", "configured"), os.getenv("OPENAI_API_KEY")),
        ("gemini", "google", os.getenv("GEMINI_MODEL", "configured"), os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        ("deepseek", "deepseek", os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), os.getenv("DEEPSEEK_API_KEY")),
        ("xai", "xai", os.getenv("XAI_MODEL") or os.getenv("GROK_MODEL") or "configured", os.getenv("XAI_API_KEY")),
        ("manus", "manus", os.getenv("MANUS_MODEL", "configured"), os.getenv("MANUS_API_KEY")),
    ]
    for model_id, provider, model_name, credential in providers:
        if credential:
            store.register_model(ModelRecord(
                id=model_id,
                provider=provider,
                model=model_name,
                departments=[item[0] for item in DEPARTMENTS if item[2] not in {"gmail", "notion", "sentry", "ui"}],
                capabilities=["reasoning", "research", "extract", "match", "generation", "tailoring", "validate", "challenge", "coding"],
                cost_tier="UNKNOWN",
                free_tier_status="CONFIGURED",
                availability="AVAILABLE",
                quality_score=0.8,
                connector_method=provider,
            ))

    # Built-in routing targets for non-LLM departments. These never require a
    # provider key and keep the pipeline alive when all LLMs are unavailable.
    for model_id, department, capability in (
        ("gmail-worker", "gmail-intake", "ingest"),
        ("discovery-worker", "job-discovery", "discover"),
        ("jd-worker", "jd-enrichment", "extract"),
        ("truth-worker", "truth-guardian", "validate"),
        ("ats-worker", "ats", "score"),
        ("engineering-worker", "engineering-repair", "test"),
    ):
        store.register_model(ModelRecord(
            id=model_id,
            provider="builtin",
            model=model_id,
            departments=[department],
            capabilities=[capability, "validate"],
            cost_tier="FREE",
            free_tier_status="BUILT_IN",
            availability="AVAILABLE",
            quality_score=0.75,
            connector_method="local-workflow",
        ))
