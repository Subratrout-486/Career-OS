from career_os.recruiter_review import classify_recruiter_review


def test_explicit_pass_is_the_only_passing_recruiter_outcome():
    review = classify_recruiter_review(
        "VERDICT: PASS\nThe resume is evidence-grounded and role-aligned.",
        "deepseek:deepseek-chat",
    )
    assert review.status == "PASS"
    assert review.provider == "deepseek:deepseek-chat"


def test_unavailable_reviewer_is_not_treated_as_approval():
    review = classify_recruiter_review(
        "INDEPENDENT CHALLENGER NOT RUN — no configured independent reviewer was usable.",
        None,
    )
    assert review.status == "NOT_RUN"
    assert review.warnings


def test_ambiguous_reviewer_output_requires_revision():
    review = classify_recruiter_review("The draft needs clearer evidence citations.", "xai:grok")
    assert review.status == "REVISE"
    assert "omitted an explicit VERDICT" in review.warnings[0]
