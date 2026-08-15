from pathlib import Path

import pytest

from career_os.control_plane import (
    AgentRecord,
    ApprovalStatus,
    ControlPlaneStore,
    MemoryItem,
    MemoryType,
    ModelRecord,
    ModelRouter,
    PlatformOrchestrator,
    RouteRequest,
    TaskStatus,
    UsageEvent,
)
from career_os.master_profile import CareerFact, MasterCareerProfile


def test_control_plane_persists_tasks_messages_and_audit(tmp_path: Path):
    path = tmp_path / "control-plane.json"
    store = ControlPlaneStore(path)
    platform = PlatformOrchestrator(store)
    store.register_agent(AgentRecord(id="jd-analyzer", name="JD Analyzer", department="jd-analysis", capabilities=["extract"]))

    root, children = platform.create_execution_plan(
        "Prepare a truthful application package",
        [
            {"objective": "Analyze the job description", "department": "jd-analysis"},
            {"objective": "Draft the resume", "department": "resume"},
        ],
    )
    message = platform.delegate(children[0].id, to_agent="jd-analyzer", objective="Extract structured requirements", input_data={"job_id": "job-1"})
    platform.record_result(children[0].id, status=TaskStatus.COMPLETED, result={"requirements": ["SQL"]}, model="deterministic")

    reloaded = ControlPlaneStore(path)
    assert reloaded.get_task(root.id).objective == root.objective
    assert reloaded.messages(children[0].id)[0].to_agent == message.to_agent
    assert reloaded.get_task(children[0].id).status == TaskStatus.COMPLETED
    assert {event.event_type for event in reloaded.audit_events(children[0].id)} == {"TASK_DELEGATED", "TASK_RESULT_RECORDED"}


def test_controlled_delegation_rejects_unknown_or_terminal_agents(tmp_path: Path):
    store = ControlPlaneStore(tmp_path / "state.json")
    platform = PlatformOrchestrator(store)
    task = platform.submit_objective("Analyze a job")

    with pytest.raises(ValueError, match="not registered"):
        platform.delegate(task.id, to_agent="missing", objective="Do work")

    platform.record_result(task.id, status=TaskStatus.COMPLETED, result={"ok": True})
    with pytest.raises(ValueError, match="terminal task"):
        platform.delegate(task.id, to_agent="missing", objective="Do work")


def test_router_prefers_lowest_cost_capable_available_model(tmp_path: Path):
    store = ControlPlaneStore(tmp_path / "state.json")
    store.register_model(ModelRecord(id="cheap", provider="local", model="extractor", departments=["jd-analysis"], capabilities=["extract"], cost_tier="FREE", quality_score=0.70))
    store.register_model(ModelRecord(id="strong", provider="cloud", model="reasoner", departments=["jd-analysis"], capabilities=["extract"], cost_tier="HIGH", quality_score=0.98))

    decision = ModelRouter(store).route(RouteRequest(department="jd-analysis", task_type="keyword extraction", required_capabilities=["extract"]))
    assert decision.status == "ROUTED"
    assert decision.model_id == "cheap"


def test_router_waits_when_all_models_are_unavailable(tmp_path: Path):
    store = ControlPlaneStore(tmp_path / "state.json")
    store.register_model(ModelRecord(id="offline", provider="cloud", model="x", capabilities=["extract"], availability="UNAVAILABLE"))

    decision = ModelRouter(store).route(RouteRequest(department="jd-analysis", task_type="keyword extraction", required_capabilities=["extract"]))
    assert decision.status == "WAITING"
    assert "No registered available model" in decision.reason


def test_approval_and_usage_are_audited(tmp_path: Path):
    store = ControlPlaneStore(tmp_path / "state.json")
    platform = PlatformOrchestrator(store)
    task = platform.submit_objective("Submit application only after review")
    approval = platform.request_approval(action="submit_application", resource_type="job", resource_id="job-1", summary="Submit the approved tailored resume", evidence=["truth-guard:pass"], task_id=task.id)

    assert store.get_task(task.id).status == TaskStatus.AWAITING_APPROVAL
    platform.decide_approval(approval.id, ApprovalStatus.REJECTED, decided_by="user", note="Need to review compensation first")
    platform.record_usage(UsageEvent(provider="deterministic", operation="truth_guard", task_id=task.id, success=True))

    assert store.approvals(pending_only=True) == []
    assert store.usage_events()[0].operation == "truth_guard"
    assert {event.event_type for event in store.audit_events()} >= {"APPROVAL_REQUESTED", "APPROVAL_DECIDED", "USAGE_RECORDED"}


def test_unverified_memory_cannot_be_authoritative(tmp_path: Path):
    store = ControlPlaneStore(tmp_path / "state.json")
    platform = PlatformOrchestrator(store)
    with pytest.raises(ValueError, match="verified memory"):
        platform.add_memory(MemoryItem(memory_type=MemoryType.CAREER, key="employment", content="unknown", source="agent", authoritative=True))

    memory = platform.add_memory(MemoryItem(memory_type=MemoryType.TASK, key="job-1:jd", content={"status": "analyzed"}, source="jd-analyzer", status="VERIFIED", confidence=0.9))
    assert memory.id.startswith("mem_")


def test_master_profile_proposals_are_immutable_and_resume_safe():
    original = MasterCareerProfile(facts=(CareerFact(id="fact-1", category="employment", subject="title", value="Support Engineer", source="verified-document", status="VERIFIED"),))
    proposed = original.propose_fact(CareerFact(id="fact-2", category="achievement", subject="metric", value="Doubled productivity", source="agent-output"))

    assert original.version == 1
    assert len(original.facts) == 1
    assert proposed.version == 2
    assert proposed.facts[-1].status == "UNVERIFIED"
    assert [fact.id for fact in proposed.facts_for_resume()] == ["fact-1"]

    approved = proposed.approve_fact("fact-2", approver="user")
    assert proposed.facts[-1].status == "UNVERIFIED"
    assert approved.facts[-1].status == "VERIFIED"
    assert "approved-by:user" in approved.facts[-1].provenance
    assert {fact.id for fact in approved.facts_for_resume()} == {"fact-1", "fact-2"}
