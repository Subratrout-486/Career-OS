from __future__ import annotations

from scripts.gmail_job_intake import candidate_links, infer_company, infer_title, make_job


def test_candidate_links_prefers_job_detail_links():
    html = '''
    <a href="https://www.oracle.com/unsubscribe">Unsubscribe</a>
    <a href="https://www.oracle.com/careers/jobs/service-delivery-management-consultant-1-support">View job</a>
    <a href="https://www.oracle.com/careers">See all jobs</a>
    '''
    links = candidate_links(html)
    assert links
    assert links[0][1].endswith("service-delivery-management-consultant-1-support")


def test_infer_title_from_subject_and_body():
    assert infer_title("Oracle jobs — Service Delivery Management Consultant 1 - Support", "") == "Service Delivery Management Consultant 1 - Support"
    assert infer_title("Your latest Oracle jobs", "Service Delivery Management Consultant 1 - Support") == "Service Delivery Management Consultant 1 - Support"


def test_infer_company_from_sender():
    assert infer_company("Oracle Talent Acquisition <oracle@example.com>", "Your latest jobs", "") == "Oracle"


def test_make_job_preserves_source_message_id_and_role_url():
    job = make_job(
        "msg-123",
        "Oracle — Service Delivery Management Consultant 1 - Support",
        "Oracle Talent Acquisition <oracle@example.com>",
        '<a href="https://www.oracle.com/careers/jobs/service-delivery-management-consultant-1-support">View job</a>',
        "Hyderabad India",
        "1760000000000",
    )
    assert job["source_message_id"] == "msg-123"
    assert job["company"] == "Oracle"
    assert job["url"].endswith("service-delivery-management-consultant-1-support")
