from __future__ import annotations

import asyncio
from pathlib import Path

from career_os.control_plane import ControlPlaneStore, TaskStatus
from career_os.pipeline_harness import PipelineHarness


class ProviderUnavailableResult:
    def model_dump(self):
        return {
            "review_status": "AI_PROVIDER_UNAVAILABLE",
            "errors": ["AI provider unavailable"],
        }


def test_provider_outage_becomes_waiting_for_conductor(tmp_path: Path):
    store = ControlPlaneStore(tmp_path / "control-plane.json")
    harness = PipelineHarness(store)

    task, result = asyncio.run(
        harness.run(
            objective="test conductor handoff",
            context={"job_id": "job-1"},
            operation=lambda: ProviderUnavailableResult(),
        )
    )

    assert task.status == TaskStatus.WAITING
    assert result.model_dump()["review_status"] == "AI_PROVIDER_UNAVAILABLE"
    assert task.payload["handoff"]["status"] == "READY_FOR_CONDUCTOR"
