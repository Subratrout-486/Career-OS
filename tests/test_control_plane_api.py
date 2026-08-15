from fastapi.testclient import TestClient

from career_os.api import create_app
from career_os.control_plane import AgentRecord, ApprovalStatus, ControlPlaneStore, ModelRecord


def test_api_exposes_ai_optional_dashboard_and_objective_submission(tmp_path):
    store = ControlPlaneStore(tmp_path / "state.json")
    store.register_model(ModelRecord(id="deterministic", provider="builtin", model="rules", capabilities=["extract"], cost_tier="FREE"))
    client = TestClient(create_app(store))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ai_optional"] is True

    created = client.post("/api/objectives", json={"objective": "Analyze a job description", "department": "jd-analysis"})
    assert created.status_code == 201
    task_id = created.json()["id"]

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["tasks"][0]["id"] == task_id

    routed = client.post("/api/route", json={"department": "jd-analysis", "task_type": "JD extraction", "required_capabilities": ["extract"]})
    assert routed.status_code == 200
    assert routed.json()["model_id"] in {"deterministic", "deterministic-rules-v1"}


def test_api_approval_decision_and_unverified_memory_guard(tmp_path):
    store = ControlPlaneStore(tmp_path / "state.json")
    store.register_agent(AgentRecord(id="reviewer", name="Reviewer", department="quality"))
    client = TestClient(create_app(store))
    task = client.post("/api/objectives", json={"objective": "Prepare review package"}).json()

    # Create the approval through the platform facade so the API remains read/write
    # compatible with the durable control-plane records.
    from career_os.control_plane import PlatformOrchestrator
    approval = PlatformOrchestrator(store).request_approval(
        action="publish_resume",
        resource_type="resume",
        resource_id="resume-1",
        summary="Publish the reviewed resume",
        task_id=task["id"],
    )
    decision = client.post(
        f"/api/approvals/{approval.id}/decision",
        json={"status": ApprovalStatus.REJECTED.value, "decided_by": "user", "note": "Not yet"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == ApprovalStatus.REJECTED.value

    blocked = client.post(
        "/api/memory",
        json={
            "memory_type": "CAREER",
            "key": "employment",
            "content": "unverified",
            "source": "agent",
            "status": "UNVERIFIED",
            "authoritative": True,
        },
    )
    assert blocked.status_code == 400
