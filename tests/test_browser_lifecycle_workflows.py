from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_browser_queue_is_explicitly_gated_until_upstream_stages_are_verified():
    text = _workflow("application-execution-queue.yml")

    assert "workflow_dispatch:" in text
    assert "STAGE_5_GATED" in text
    assert "No browser task is created from intake-only workflows." in text
    assert "actions: read" in text
    assert "contents: read" in text


def test_discovery_paths_publish_only_stage_one_evidence_and_stop_downstream_execution():
    for name in (
        "job-discovery.yml",
        "gmail-job-intake.yml",
        "specialist-source-intake.yml",
        "career-os-job-intake.yml",
    ):
        text = _workflow(name)
        assert "STAGE_1_" in text or "STAGE_2_GATED" in text
        assert ("BLOCKED:" in text or "Downstream stages remain blocked by design." in text or "No AI matching, resume generation, Notion sync, or browser execution is started." in text)
        assert "career-os-browser-lifecycle-candidates" not in text


def test_automatic_queue_has_no_direct_dispatch_bypass():
    for name in ("job-discovery.yml", "gmail-job-intake.yml", "specialist-source-intake.yml"):
        text = _workflow(name)
        assert "dispatch_manus_browser_tasks.py" not in text
        assert "run_manus_browser_preflight.py" not in text
