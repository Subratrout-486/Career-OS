from __future__ import annotations

import asyncio
from pathlib import Path

from career_os.agent_runtime import AgentSpec, AgentRegistry, MultiAgentRuntime
from career_os.control_plane import ControlPlaneStore, TaskStatus


def test_continuation_reuses_same_child_task(tmp_path: Path):
    calls = {"n": 0}

    async def executor(*, objective, context, tools):
        calls["n"] += 1
        return {"objective": objective, "attempt": calls["n"], "continuation": context.get("continuation", False)}

    registry = AgentRegistry()
    registry.register(
        AgentSpec("resume-agent", "Resume Agent", "resume", ("resume",), ("filesystem",)),
        executor,
    )
    runtime = MultiAgentRuntime(ControlPlaneStore(tmp_path / "control-plane.json"), registry=registry)
    parent = runtime.store.create_task(
        __import__("career_os.control_plane", fromlist=["TaskRecord"]).TaskRecord(objective="parent", agent_id="career-os-runtime")
    )

    first = asyncio.run(
        runtime.execute_real_agent_async(
            parent_task_id=parent.id,
            agent_id="resume-agent",
            objective="draft resume",
            context={"version": 1},
        )
    )
    child_id = runtime.store.messages_for_task(parent.id)[-1].evidence[0]["task_id"] if isinstance(runtime.store.messages_for_task(parent.id)[-1].evidence[0], dict) and "task_id" in runtime.store.messages_for_task(parent.id)[-1].evidence[0] else None

    # The durable child is discoverable from the control-plane task records.
    children = [t for t in runtime.store.tasks() if t.parent_task_id == parent.id]
    assert len(children) == 1
    child_id = children[0].id
    assert children[0].status == TaskStatus.COMPLETED

    second = asyncio.run(
        runtime.execute_real_agent_async(
            parent_task_id=parent.id,
            agent_id="resume-agent",
            objective="correct resume after truth guard",
            context={"version": 2},
            existing_task_id=child_id,
        )
    )

    children_after = [t for t in runtime.store.tasks() if t.parent_task_id == parent.id]
    assert len(children_after) == 1
    assert children_after[0].id == child_id
    assert children_after[0].status == TaskStatus.COMPLETED
    assert second["continuation"] is True
    assert calls["n"] == 2
