from datetime import datetime, timezone

from career_os.email_job_intake import EmailJobMessage, extract_job_urls, message_to_job
from career_os.job_intelligence import (
    JobRecord,
    detect_work_model,
    freshness_hours,
    normalize_job_url,
    parse_salary_range,
    rank_jobs,
    select_job_updates,
)
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
    assert "servicenow" in ranked[0].matched_terms


def test_remote_salary_and_freshness_are_detected_without_inventing_data():
    text = "Technical Support Specialist. Remote. $70K - $90K/yr."
    assert detect_work_model(text) == "REMOTE"
    assert parse_salary_range(text) == (70000.0, 90000.0, "USD")
    now = datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc)
    assert freshness_hours("2026-08-14T17:00:00+00:00", now) == 1.0


def test_remote_fresh_well_paid_role_gets_high_priority():
    now = datetime(2026, 8, 14, 18, 0, tzinfo=timezone.utc)
    job = JobRecord(
        "Acme",
        "Technical Support Specialist",
        "Remote",
        "https://acme/jobs/42",
        "email",
        description="ServiceNow SQL Remote $70K - $90K/yr",
        posted_at="2026-08-14T17:00:00+00:00",
    )
    matches = rank_jobs(job for job in [job], ["technical support", "servicenow", "sql"], minimum_salary=60000, now=now)
    assert matches[0].priority == "HIGH"
    assert "remote" in matches[0].reasons
    assert "salary_target_met" in matches[0].reasons
    assert matches[0].freshness_hours == 1.0
    assert select_job_updates(matches) == matches


def test_below_salary_target_is_not_selected_as_high_priority():
    job = JobRecord(
        "Acme",
        "Support Analyst",
        "Remote",
        "https://acme/jobs/43",
        "feed",
        description="Remote $40K - $50K/yr support role",
    )
    matches = rank_jobs([job], ["support"], minimum_salary=60000)
    assert "below_salary_target" in matches[0].blockers
    assert select_job_updates(matches) == []


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
