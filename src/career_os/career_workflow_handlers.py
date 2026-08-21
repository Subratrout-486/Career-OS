"""Career OS workflow-node adapters.

Keeps AgentFlow's workflow engine generic while binding career-specific nodes
through the existing durable multi-agent runtime. Source discovery is injected
through the job-source registry; authenticated sources remain explicit tools.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .job_source_registry import JobSourceConfig, JobSourceRegistry
from .workflow_engine import WorkflowEngine, WorkflowNode


def _profile(context: dict[str, Any]) -> Any:
    return context.get("profile") or context.get("master_profile")


def _job(context: dict[str, Any]) -> Any:
    return context.get("job")


def _flatten_jobs(discovered: dict[str, list[Any]]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for source_id, candidates in discovered.items():
        for candidate in candidates:
            if hasattr(candidate, "__dict__"):
                item = dict(candidate.__dict__)
            else:
                item = dict(candidate)
            item["source_id"] = source_id
            jobs.append(item)
    return jobs


def _load_source_registry(context: dict[str, Any]) -> JobSourceRegistry:
    """Build the registry from configuration; allow a test/runtime override."""
    configured = context.get("job_sources")
    state_path = str(context.get("seen_jobs_path", "state/seen_jobs.json"))
    if configured is None:
        config_path = Path(str(context.get("job_sources_config", "config/job_sources.json")))
        if not config_path.exists():
            raise FileNotFoundError(f"Job source configuration not found: {config_path}")
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        configured = payload.get("sources", [])
    sources = [JobSourceConfig(**source) for source in configured]
    return JobSourceRegistry(sources, state_path=state_path)


def register_career_workflow_handlers(engine: WorkflowEngine, *, runtime: Any) -> None:
    """Register deterministic adapters for the canonical Career OS graph."""

    async def job_discovery(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        # Explicit jobs remain supported for deterministic fixtures/replays.
        if "jobs" in context:
            return {"jobs": context["jobs"], "source": context.get("job_source", "configured-input")}
        registry = _load_source_registry(context)
        discovered = await registry.discover_new()
        jobs = _flatten_jobs(discovered)
        return {"jobs": jobs, "source": "configured-job-sources", "sources": discovered, "new_job_count": len(jobs)}

    def deduplicate(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        source = inputs.get("job_discovery", {}).get("jobs", context.get("jobs", []))
        seen: set[str] = set()
        jobs: list[Any] = []
        for item in source:
            key = str(item.get("url") or item.get("id") or item.get("title")) if isinstance(item, dict) else str(item)
            if key not in seen:
                seen.add(key)
                jobs.append(item)
        return {"jobs": jobs, "count": len(jobs)}

    async def jd_enrichment(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        jobs = inputs.get("deduplicate", {}).get("jobs", [])
        return {"jobs": jobs, "jd": context.get("jd")}

    async def career_fit(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        job = _job(context)
        profile = _profile(context)
        if job is None or profile is None:
            raise ValueError("career_fit requires context.job and context.profile")
        return await runtime.execute_real_agent_async(
            parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "career-fit",
            objective="Score career fit using the canonical profile, job and evidence.",
            context={"profile": profile, "job": job, "evidence_pack": context.get("evidence_pack"), "jd_analysis": context.get("jd_analysis")},
        )

    async def resume_builder(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        return await runtime.execute_real_agent_async(
            parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "resume-builder",
            objective="Build a tailored resume using only verified career evidence.",
            context={"profile": _profile(context), "job": _job(context), "fit": inputs.get("career_fit"), "evidence_pack": context.get("evidence_pack"), "jd_analysis": context.get("jd_analysis")},
        )

    async def truth_guard(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        resume = inputs.get("resume_builder")
        if resume is None:
            raise ValueError("truth_guard requires resume_builder output")
        return await runtime.execute_real_agent_async(
            parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "truth-guard",
            objective="Verify every resume claim against the canonical Career Evidence Vault.",
            context={"profile": _profile(context), "job": _job(context), "resume": resume, "evidence_pack": context.get("evidence_pack")},
        )

    async def ats_review(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        return await runtime.execute_real_agent_async(
            parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "ats-scorer",
            objective="Evaluate ATS alignment without adding unsupported claims.",
            context={"job": _job(context), "resume": inputs.get("truth_guard") or inputs.get("resume_builder")},
        )

    async def independent_review(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        return await runtime.execute_real_agent_async(
            parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "challenger",
            objective="Independently challenge the fit, resume and ATS result for unsupported or weak reasoning.",
            context={"profile": _profile(context), "job": _job(context), "fit": inputs.get("career_fit"), "resume": inputs.get("truth_guard") or inputs.get("resume_builder"), "ats": inputs.get("ats_review")},
        )

    def application_approval(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        return {"status": "APPROVAL_REQUIRED", "job": _job(context), "review": inputs.get("independent_review")}

    def browser_application(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        return {"status": "READY_FOR_APPROVED_BROWSER_EXECUTION", "job": _job(context)}

    engine.register_handler("job_discovery", job_discovery)
    engine.register_handler("deduplicate", deduplicate)
    engine.register_handler("jd_enrichment", jd_enrichment)
    engine.register_handler("career_fit", career_fit)
    engine.register_handler("resume_builder", resume_builder)
    engine.register_handler("truth_guard", truth_guard)
    engine.register_handler("ats_review", ats_review)
    engine.register_handler("independent_review", independent_review)
    engine.register_handler("application_approval", application_approval)
    engine.register_handler("browser_application", browser_application)
