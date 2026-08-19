from career_os.control_plane import ControlPlaneStore, ModelRouter, RouteRequest
from career_os.department_registry import bootstrap_department_registry


def test_full_department_registry_is_truthful_and_idempotent(tmp_path):
    store = ControlPlaneStore(tmp_path / "control.json")
    bootstrap_department_registry(store)
    bootstrap_department_registry(store)

    ids = {agent.id for agent in store.agents()}
    assert "gmail-intake" in ids
    assert "jd-enrichment" in ids
    assert "fit-analysis" in ids
    assert "truth-guardian" in ids
    assert "browser-execution" in ids
    assert "observability" in ids
    assert "engineering-repair" in ids

    sentry = next(agent for agent in store.agents() if agent.id == "observability")
    assert sentry.provider == "sentry"
    assert sentry.availability in {"AVAILABLE", "DEGRADED"}


def test_builtin_departments_route_without_an_llm(tmp_path):
    store = ControlPlaneStore(tmp_path / "control.json")
    bootstrap_department_registry(store)
    decision = ModelRouter(store).route(RouteRequest(
        department="jd-enrichment",
        task_type="extract",
        required_capabilities=["extract"],
        max_cost_tier="FREE",
    ))
    assert decision.status == "ROUTED"
    assert decision.model_id == "jd-worker"
