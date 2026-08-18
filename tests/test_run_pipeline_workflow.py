from pathlib import Path


WORKFLOW = Path('.github/workflows/run-pipeline.yml').read_text(encoding='utf-8')


def test_envelope_failure_is_redacted_and_orchestrator_is_gated():
    assert 'id: envelope' in WORKFLOW
    assert 'continue-on-error: true' in WORKFLOW
    assert 'ENVELOPE_DECRYPTION_FAILED' in WORKFLOW
    assert "if: steps.envelope.outcome == 'success'" in WORKFLOW
    assert 'pipeline-result.json' in WORKFLOW


def test_workflow_does_not_use_plaintext_job_inputs():
    assert 'job_path:' not in WORKFLOW
    assert 'browser_context_path:' not in WORKFLOW
    assert 'encrypted_job_envelope:' in WORKFLOW
    assert 'conductor_run_id:' in WORKFLOW
