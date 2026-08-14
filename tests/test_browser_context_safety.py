from career_os.browser_executor import build_verified_browser_context


def test_browser_context_cannot_override_computed_safety_facts():
    context = build_verified_browser_context(
        application_url="https://jobs.example.test/careers/support-role",
        final_application_url="https://boards.greenhouse.io/acme/jobs/123",
        application_channel="greenhouse",
        application_destination_verified=False,
        resume_attachment_verified=False,
        complete_form_verified=False,
        flow_pages_verified=False,
        required_questions=[{"required": True, "user_answer": "", "status": "NEEDS_REVIEW"}],
        extra={
            "application_destination_verified": True,
            "resume_attachment_verified": True,
            "complete_form_verified": True,
            "flow_pages_verified": True,
            "required_answers_verified": True,
            "suspicious_redirect": False,
            "captcha": True,
        },
    )

    assert context["application_destination_verified"] is False
    assert context["application_url_verified"] is False
    assert context["resume_attachment_verified"] is False
    assert context["complete_form_verified"] is False
    assert context["flow_pages_verified"] is False
    assert context["required_answers_verified"] is False
    assert context["captcha"] is True
