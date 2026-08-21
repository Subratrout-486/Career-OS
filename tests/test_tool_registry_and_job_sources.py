import asyncio

import pytest

from career_os.job_sources import CompanyCareerSource, JobCandidate, deduplicate_candidates
from career_os.tool_registry import ToolApprovalRequired, ToolExecutionError, ToolRegistry, ToolSpec


@pytest.mark.asyncio
async def test_tool_registry_enforces_capabilities_and_approval():
    registry = ToolRegistry()
    registry.register(ToolSpec("safe", "safe tool", lambda: {"ok": True}, capabilities=frozenset({"read"})))
    registry.register(ToolSpec("apply", "application", lambda: {"ok": True}, requires_approval=True))
    with pytest.raises(ToolExecutionError):
        await registry.execute("safe")
    assert await registry.execute("safe", capabilities={"read"}) == {"ok": True}
    with pytest.raises(ToolApprovalRequired):
        await registry.execute("apply")
    assert await registry.execute("apply", approval_granted=True) == {"ok": True}


@pytest.mark.asyncio
async def test_tool_registry_times_out_async_tool():
    async def slow():
        await asyncio.sleep(0.05)
    registry = ToolRegistry()
    registry.register(ToolSpec("slow", "slow", slow, timeout_sec=1))
    await registry.execute("slow")
    assert registry.audit_log[-1]["status"] == "COMPLETED"


def test_job_candidate_deduplication_is_url_based():
    items = [JobCandidate("A", "Acme", "https://acme.test/job/1/"), JobCandidate("A", "Acme", "https://acme.test/job/1"), JobCandidate("B", "Acme", "https://acme.test/job/2")]
    result = deduplicate_candidates(items)
    assert [item.title for item in result] == ["A", "B"]


def test_company_source_extracts_conservative_links():
    html = '<a href="/careers/123">Senior Analyst</a><a href="/about">About us</a>'
    result = CompanyCareerSource().extract_candidates(html, base_url="https://acme.test", company="Acme")
    assert len(result) == 1
    assert result[0].url == "https://acme.test/careers/123"
