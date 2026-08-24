"""Career OS workflow-node adapters.

Keeps AgentFlow generic while giving Career OS an Activepieces-style
loop-on-items boundary: every discovered job travels independently through
the specialist stages, with bounded concurrency and per-item failures.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from .job_source_registry import JobSourceConfig, JobSourceRegistry
from .workflow_engine import WorkflowEngine, WorkflowNode
from .responsibility_fit import _CAPABILITY_FAMILIES


def _profile(context: dict[str, Any]) -> Any:
    return context.get("profile") or context.get("master_profile")


def _load_source_registry(context: dict[str, Any]) -> JobSourceRegistry:
    configured = context.get("job_sources")
    state_path = str(context.get("seen_jobs_path", "state/seen_jobs.json"))
    if configured is None:
        config_path = Path(str(context.get("job_sources_config", "config/job_sources.json")))
        if not config_path.exists():
            raise FileNotFoundError(f"Job source configuration not found: {config_path}")
        configured = json.loads(config_path.read_text(encoding="utf-8")).get("sources", [])
    return JobSourceRegistry([JobSourceConfig(**source) for source in configured], state_path=state_path)


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("items", value.get("jobs", []))
    return [dict(item) for item in (value or [])]


def _responsibility_fit_policy() -> str:
    """Return the canonical transferable-skill policy used by the fit worker."""
    families = ", ".join(sorted(_CAPABILITY_FAMILIES))
    return f"""
CAREER OS RESPONSIBILITY-FIRST FIT POLICY (mandatory):
1. Evaluate the JD itself before relying on the job title. A target designation is a positive signal, not a requirement.
2. If the designation is outside the target families, still qualify the job when the JD's actual responsibilities and required
   skills make the candidate reasonably eligible to apply.
3. Responsibilities and required skills are the primary evidence. Do not reject a job merely because the implementation/tool
   differs from the candidate's prior employer when the underlying capability is reasonably transferable.
4. Examples of reasonable transferability: Oracle/SQL -> other relational SQL environments; Unix -> Linux; ServiceNow/ITSM ->
   comparable ticketing/workflow systems; REST/JSON -> comparable API tooling; Python -> scripting/automation/AI workflow work.
5. Transferability is NOT permission to claim hands-on experience with the target tool. Record the target tool as transferable or
   a learnable gap and preserve the actual employer/tool evidence in the resume.
6. A SQL requirement should be treated as a real skill match when the evidence shows the candidate can write/use SQL queries;
   do not require the exact database vendor unless the JD requires deep vendor-specific administration/performance expertise.
7. Recent Career OS v2 project work may be used as PROJECT evidence for AI automation, agents, prompting, workflow automation,
   JD analysis and related skills. It must never be converted into years of professional employment experience.
8. Do not automatically reject for a years-of-experience mismatch alone. Treat years as a fit factor unless the JD's seniority or
   specialist scope makes the gap materially incompatible.
9. Mandatory education, location, explicit specialist-domain requirements, and deep seniority/ownership requirements remain hard
   blockers when the source of truth does not satisfy them.
10. Distinguish MATCH, TRANSFERABLE, LEARNABLE/UNCONFIRMED and BLOCKER in requirement_matches. Do not inflate a transferable
    capability into direct target-tool experience.
11. Score actual work/responsibilities higher than title keywords. Consider support/operations workflow, troubleshooting,
    incident ownership, RCA, SQL/data work, APIs, Linux/Unix, ticketing/ITSM, scripting, process improvement, research/data
    operations, stakeholder work and AI/automation project evidence where present in the JD and profile.
12. The capability families currently recognized for transferability are: {families}.
"""


async def _map_jobs(
    jobs: list[dict[str, Any]],
    worker: Callable[[dict[str, Any]], Awaitable[Any]],
    *,
    concurrency: int = 4,
) -> list[dict[str, Any]]:
    """Bounded loop-on-items execution with per-item failure isolation."""
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_one(job: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            try:
                return {"job": job, "status": "COMPLETED", "result": await worker(job)}
            except Exception as exc:
                return {"job": job, "status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}

    return list(await asyncio.gather(*(run_one(job) for job in jobs)))


def register_career_workflow_handlers(engine: WorkflowEngine, *, runtime: Any) -> None:
    async def job_discovery(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        if "jobs" in context:
            return {"jobs": context["jobs"], "source": context.get("job_source", "configured-input")}
        jobs, failures = await _load_source_registry(context).discover_new()
        normalized = [dict(job.__dict__) for job in jobs]
        return {
            "jobs": normalized,
            "source": "configured-job-sources",
            "failures": [failure.__dict__ for failure in failures],
            "new_job_count": len(normalized),
        }

    def deduplicate(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        source = _items(inputs.get("job_discovery")) or _items(context.get("jobs"))
        seen: set[str] = set()
        jobs: list[dict[str, Any]] = []
        for item in source:
            key = str(item.get("url") or item.get("id") or item.get("title", "")).rstrip("/").lower()
            if key and key not in seen:
                seen.add(key)
                jobs.append(item)
        return {"jobs": jobs, "count": len(jobs)}

    async def jd_enrichment(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        return {"jobs": _items(inputs.get("deduplicate")), "jd": context.get("jd")}

    async def career_fit(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        profile = _profile(context)
        if profile is None:
            raise ValueError("career_fit requires profile/master_profile")
        jobs = _items(inputs.get("jd_enrichment"))
        policy = _responsibility_fit_policy()
        async def worker(job: dict[str, Any]) -> Any:
            return await runtime.execute_real_agent_async(
                parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "career-fit",
                objective=(
                    "Score career fit using the canonical profile, complete JD and evidence. "
                    "Do not use designation-only matching. Read and compare the actual responsibilities and required skills, "
                    "allow reasonable capability transfer across implementations, and treat recent Career OS work as project "
                    "evidence where relevant. Return direct matches, transferable capabilities, learnable/unconfirmed gaps and "
                    "hard blockers separately.\n\n" + policy
                ),
                context={
                    "profile": profile,
                    "job": job,
                    "evidence_pack": context.get("evidence_pack"),
                    "responsibility_fit_policy": policy,
                    "jd_responsibilities_first": True,
                    "allow_transferable_skills": True,
                    "designation_is_secondary_signal": True,
                },
            )
        return {"items": await _map_jobs(jobs, worker), "count": len(jobs)}

    async def resume_builder(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        profile = _profile(context)
        fit_items = inputs.get("career_fit", {}).get("items", [])
        async def worker(item: dict[str, Any]) -> Any:
            return await runtime.execute_real_agent_async(
                parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "resume-builder",
                objective=(
                    "Build a tailored resume using only verified career evidence. Preserve actual employer/tool mapping. "
                    "Use the responsibility-first fit report to emphasize transferable capabilities without claiming the target "
                    "tool was used when it was not evidenced. Project evidence such as recent Career OS AI/automation work may "
                    "be included only as project evidence, never as fabricated employment history."
                ),
                context={
                    "profile": profile,
                    "job": item["job"],
                    "fit": item.get("result"),
                    "evidence_pack": context.get("evidence_pack"),
                    "responsibility_fit_policy": _responsibility_fit_policy(),
                },
            )
        return {"items": await _map_jobs(fit_items, worker), "count": len(fit_items)}

    async def truth_guard(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        profile = _profile(context)
        items = inputs.get("resume_builder", {}).get("items", [])
        async def worker(item: dict[str, Any]) -> Any:
            return await runtime.execute_real_agent_async(
                parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "truth-guard",
                objective="Verify every resume claim against the canonical Career Evidence Vault, including transferable-vs-direct-tool wording.",
                context={"profile": profile, "job": item["job"], "resume": item.get("result"), "evidence_pack": context.get("evidence_pack")},
            )
        return {"items": await _map_jobs(items, worker), "count": len(items)}

    async def ats_review(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        items = inputs.get("truth_guard", {}).get("items", [])
        async def worker(item: dict[str, Any]) -> Any:
            return await runtime.execute_real_agent_async(
                parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "ats-scorer",
                objective="Evaluate ATS alignment without adding unsupported claims and without penalizing truthful transferable skills solely because the vendor/tool differs.",
                context={"job": item["job"], "resume": item.get("result")},
            )
        return {"items": await _map_jobs(items, worker), "count": len(items)}

    async def independent_review(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        items = inputs.get("ats_review", {}).get("items", [])
        async def worker(item: dict[str, Any]) -> Any:
            return await runtime.execute_real_agent_async(
                parent_task_id=context["parent_task_id"], agent_id=node.agent_id or "challenger",
                objective="Independently challenge the responsibility-first fit, transferable-skill reasoning, resume and ATS result for unsupported claims, hidden blockers or overly conservative rejection.",
                context={"profile": _profile(context), "job": item["job"], "ats": item.get("result"), "responsibility_fit_policy": _responsibility_fit_policy()},
            )
        return {"items": await _map_jobs(items, worker), "count": len(items)}

    def application_approval(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        return {"status": "APPROVAL_REQUIRED", "items": inputs.get("independent_review", {}).get("items", [])}

    def browser_application(*, node: WorkflowNode, inputs: dict[str, Any], context: dict[str, Any], run: Any) -> Any:
        return {"status": "READY_FOR_APPROVED_BROWSER_EXECUTION", "items": inputs.get("application_approval", {}).get("items", [])}

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
