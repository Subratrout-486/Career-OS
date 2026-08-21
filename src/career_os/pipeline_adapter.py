"""Bridge the proven CareerOS pipeline into the durable control plane."""

from __future__ import annotations

from typing import Any

from .control_plane import (
    AgentRecord,
    ApprovalStatus,
    ControlPlaneStore,
    PlatformOrchestrator,
    TaskStatus,
    UsageEvent,
    bootstrap_registry,
)
from .models import Job, PipelineResult
from .orchestrator import CareerOS
from .agents import AgentRuntime
from .agent_runtime import MultiAgentRuntime


class ControlledCareerPipeline:
    """Run ``CareerOS.process`` while preserving task, audit, and approval state."""

    def __init__(self, pipeline: CareerOS | None = None, store: ControlPlaneStore | None = None):
        self.store = store or ControlPlaneStore()
        bootstrap_registry(self.store)
        self.provider_runtime = getattr(pipeline, "runtime", None)
        self.harness = MultiAgentRuntime(self.store, provider_runtime=self.provider_runtime)
        self.store.register_agent(AgentRecord(
            id="career-os-runtime",
            name="Career OS Proven Pipeline",
            department="orchestrator",
            provider="career-os",
            capabilities=["pipeline", "truth-guard", "ats", "notion"],
            availability="AVAILABLE",
        ))
        self.platform = PlatformOrchestrator(self.store)
        self.pipeline = pipeline
        if isinstance(self.pipeline, CareerOS):
            self.pipeline.harness_runtime = self.harness

    async def process(
        self,
        profile: str,
        job: Job,
        *,
        browser_context: dict[str, object] | None = None,
        existing_application_page_id: str | None = None,
    ) -> PipelineResult:
        if self.pipeline is None:
            self.provider_runtime = AgentRuntime()
            self.harness = MultiAgentRuntime(self.store, provider_runtime=self.provider_runtime)
            self.pipeline = CareerOS(runtime=self.provider_runtime, harness_runtime=self.harness)

        task = self.platform.submit_objective(
            f"Process application pipeline for {job.company} — {job.title}",
            department="orchestrator",
            payload={"job": job.model_dump(mode="json"), "browser_context_present": bool(browser_context)},
        )
        self.platform.delegate(
            task.id,
            to_agent="career-os-runtime",
            objective="Run the existing verified Career OS pipeline",
            input_data={"company": job.company, "title": job.title},
            evidence=["CareerOS.process"],
        )
        try:
            result = await self.pipeline.process(
                profile,
                job,
                browser_context=browser_context,
                existing_application_page_id=existing_application_page_id,
                harness_parent_task_id=task.id,
            )
        except Exception as exc:
            self.platform.record_result(
                task.id,
                status=TaskStatus.FAILED,
                failure_reason=str(exc),
                human_escalation="Inspect the pipeline exception and rerun only after the failure is understood.",
            )
            raise

        result_payload: dict[str, Any] = {
            "review_status": result.review_status,
            "application_mode": result.application_mode,
            "errors": list(result.errors),
            "resume_files": [item.model_dump(mode="json") if hasattr(item, "model_dump") else str(item) for item in (result.resume_files or [])],
        }
        if result.application_mode == "AUTO_APPLY":
            approval = self.platform.request_approval(
                action="execute_application",
                resource_type="job",
                resource_id=str(getattr(job, "source_job_id", None) or f"{job.company}:{job.title}"),
                summary="The existing pipeline passed its application gates; human approval is still required before browser execution.",
                evidence=["application_mode=AUTO_APPLY", "truth-guard and browser gates are recorded by the pipeline"],
                task_id=task.id,
            )
            result_payload["approval_id"] = approval.id
        else:
            self.platform.record_result(
                task.id,
                status=TaskStatus.COMPLETED,
                result=result_payload,
                model=self.pipeline.runtime.last_provider_used or None,
            )

        if self.pipeline.runtime.last_provider_used:
            self.platform.record_usage(UsageEvent(
                provider=self.pipeline.runtime.last_provider_used,
                model=self.pipeline.runtime.last_provider_used,
                task_id=task.id,
                operation="career_os_pipeline",
                success=True,
            ))
        return result
