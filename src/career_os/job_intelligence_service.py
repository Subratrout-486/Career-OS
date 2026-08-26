"""Bridge job-intelligence records into the existing Career OS pipeline."""
from __future__ import annotations

from .job_intelligence import JobRecord
from .models import Job, PipelineResult
from .orchestrator import CareerOS


def to_pipeline_job(record: JobRecord) -> Job:
    """Convert an intake record to the canonical Career OS Job model."""
    return Job(
        title=record.title,
        company=record.company,
        location=record.location,
        url=record.canonical_url,
        source=record.source,
        description=record.description,
        captured_at=record.metadata.get("captured_at"),
        source_job_id=record.requisition_id,
        source_url=record.url,
        discovery_channel=record.source,
        published_at=record.posted_at,
        source_capture_evidence=record.metadata.get("source_capture_evidence"),
    )


async def process_intake_record(
    career_os: CareerOS,
    profile: str,
    record: JobRecord,
    *,
    browser_context: dict[str, object] | None = None,
    existing_application_page_id: str | None = None,
) -> PipelineResult:
    """Send a normalized job through the single existing application pipeline."""
    if not record.active:
        raise ValueError("Inactive job records cannot enter application processing")
    return await career_os.process(
        profile,
        to_pipeline_job(record),
        browser_context=browser_context,
        existing_application_page_id=existing_application_page_id,
    )
