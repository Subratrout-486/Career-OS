from career_os.email_job_intake import EmailJobMessage, extract_job_urls, message_to_job
from career_os.job_intelligence import JobRecord, normalize_job_url, rank_jobs
from career_os.recruiter_outreach import RecruiterContact, OutreachStatus, approve_outreach, draft_referral_email


def test_tracking_parameters_do_not_change_job_identity():
    a = normalize_job_url("https://example.com/jobs/123?utm_source=x&rid=123")
    b = normalize_job_url("https://EXAMPLE.com/jobs/123?rid=123")
    assert a == b


def test_requisition_identity_deduplicates_tracking_variants():
    a = JobRecord("Acme", "Support Analyst", "Hyderabad", "https://x/jobs/1?utm_source=a", "linkedin", "REQ-42")
    b = JobRecord("Acme", "Support Analyst", "Hyderabad", "https://x/jobs/1?utm_source=b", "email", "REQ-42")
    assert a.identity == b.identity


def test_ranker_is_transparent_and_respects_blockers():
    jobs = [
        JobRecord("A", "Technical Support Analyst", "Hyderabad", "https://a", "feed", description="ServiceNow SQL Linux"),
        JobRecord("B", "Product Manager", "Hyderabad", "https://b", "feed", description="Product strategy"),
    ]
    ranked = rank_jobs(jobs, ["support", "ServiceNow", "SQL"], ["product manager"])
    assert ranked[0].job.company == "A"
    assert "ServiceNow" in ranked[0].matched_terms


def test_email_intake_extracts_first_job_url_and_requisition():
    message = EmailJobMessage("m1", "Hiring Team <jobs@example.com>", "Support Analyst", "Apply: https://example.com/jobs/42. Req ID: REQ-42")
    assert extract_job_urls(message.body) == ("https://example.com/jobs/42",)
    job = message_to_job(message, company="Example")
    assert job is not None
    assert job.requisition_id == "REQ-42"
    assert job.source == "email"


def test_referral_draft_requires_explicit_approval_before_transport():
    recruiter = RecruiterContact("Priya Sharma", "Example", email="priya@example.com")
    draft = draft_referral_email(recruiter, "Support Analyst", "https://example.com/jobs/42", "resume-42", "Candidate", "I have relevant product support experience.")
    assert draft.status is OutreachStatus.DRAFT
    approved = approve_outreach(draft)
    assert approved.status is OutreachStatus.APPROVED
