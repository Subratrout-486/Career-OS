from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_browser_queue_is_automatic_and_persists_cross_run_workspace():
    text = _workflow("application-execution-queue.yml")

    assert "workflow_run:" in text
    assert "Career OS — Job Discovery" in text
    assert "Career OS — Gmail Job Intake" in text
    assert "Career OS — Specialist Source Intake" in text
    assert "Career OS — Job Intake" in text
    assert "cron: '*/10 * * * *'" in text
    assert "career-os-browser-lifecycle-candidates" in text
    assert "run-id: ${{ github.event.workflow_run.id }}" in text
    assert "career-os-browser-lifecycle-state" in text
    assert "browser_execution_state.json" in text
    assert "merge-multiple: true" in text
    assert "python scripts/run_manus_browser_lifecycle.py --workspace browser_lifecycle" in text
    assert "workflow_dispatch:" in text  # an optional operational retry is retained
    assert "phase:" not in text  # no manual PRE-FLIGHT/DISPATCH/RECONCILE selector


def test_every_discovery_path_publishes_a_self_contained_lifecycle_bundle():
    for name in (
        "job-discovery.yml",
        "gmail-job-intake.yml",
        "specialist-source-intake.yml",
        "career-os-job-intake.yml",
    ):
        text = _workflow(name)
        assert "name: career-os-browser-lifecycle-candidates" in text
        assert "pipeline_results/" in text
        assert "generated_resumes/" in text


def test_automatic_queue_has_no_direct_dispatch_bypass():
    for name in ("job-discovery.yml", "gmail-job-intake.yml", "specialist-source-intake.yml"):
        text = _workflow(name)
        assert "dispatch_manus_browser_tasks.py" not in text
        assert "run_manus_browser_preflight.py" not in text
