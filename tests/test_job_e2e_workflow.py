import pytest

from career_os.job_e2e_workflow import JobStage, JobWorkflowError, validate_stage_transition, workflow_plan


def test_workflow_contains_submission_safe_terminal_state():
    plan = workflow_plan()
    stages = [item["stage"] for item in plan]
    assert stages[-1] == JobStage.REVIEW_REQUIRED.value
    assert "submit_application" not in [item["command"] for item in plan]
    assert any(item["approval_required"] for item in plan)


def test_stage_transition_fails_closed_on_missing_prerequisite():
    with pytest.raises(JobWorkflowError):
        validate_stage_transition(set(), JobStage.ANALYZE_JD)


def test_stage_transition_accepts_completed_prerequisites():
    completed = {
        JobStage.DISCOVER,
        JobStage.VERIFY,
        JobStage.ANALYZE_JD,
    }
    validate_stage_transition(completed, JobStage.RETRIEVE_EVIDENCE)
