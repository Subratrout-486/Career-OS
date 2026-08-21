from career_os import agents


def test_truth_policy_reconciles_stale_igt_denylist():
    assert agents.TRUTH_POLICY_RECONCILED is True
    assert "HARD IGT RESUME PROHIBITION" not in agents.TRUTH_RULES
    assert "previously disputed IGT technical claims" not in agents.TRUTH_RULES
    assert "current canonical resume explicitly confirms Python, SQL, Power Query, Power BI, REST API testing, and UAT under IGT Solutions" in agents.TRUTH_RULES


def test_excel_is_scoped_by_evidence_instead_of_globally_denied():
    assert "Excel/Advanced Excel is unconfirmed" not in agents.FIT_PROMPT
    assert "Do not put Excel/Advanced Excel on the resume as professional experience until employer-specific confirmation exists." not in agents.RESUME_PROMPT
    assert "professionally confirmed Excel only at the employer(s) mapped in the approved evidence pack" in agents.RESUME_PROMPT


def test_challenger_uses_evidence_scope():
    assert "UNCONFIRMED tools (including Excel)" not in agents.CHALLENGE_PROMPT
    assert "safe wording/scope in the evidence pack" in agents.CHALLENGE_PROMPT
