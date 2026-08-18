from pathlib import Path


WORKFLOW = Path('.github/workflows/gmail-job-intake.yml').read_text(encoding='utf-8')


def test_gmail_stage1_persists_validated_records_to_canonical_store():
    assert 'contents: write' in WORKFLOW
    assert 'Persist validated Stage 1 records' in WORKFLOW
    assert 'mkdir -p jobs/email_runtime jobs/discovery_runtime' in WORKFLOW
    assert 'git add jobs/email_runtime jobs/discovery_runtime' in WORKFLOW
    assert "git commit -m 'chore: persist Stage 1 Gmail intake records'" in WORKFLOW
    assert 'git push' in WORKFLOW


def test_gmail_stage1_remains_isolated_from_downstream_departments():
    boundary = WORKFLOW.split('      - name: Stage 1 hard boundary', 1)[1]
    assert 'STAGE_1_GMAIL_INTAKE_COMPLETE' in boundary
    assert 'Downstream stages remain blocked by design.' in boundary
    assert 'matching' not in boundary.lower()
    assert 'resume' not in boundary.lower()
    assert 'notion' not in boundary.lower()
    assert 'browser' not in boundary.lower()
