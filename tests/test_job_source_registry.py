import asyncio
import json

from career_os.job_source_registry import JobSourceConfig, JobSourceRegistry, SeenJobStore, job_fingerprint
from career_os.job_sources import JobCandidate


def candidate(url: str, title: str = "Analyst"):
    return JobCandidate(title=title, company="Example", url=url)


def test_seen_store_only_emits_new_jobs(tmp_path):
    store = SeenJobStore(tmp_path / "seen.json")
    first, known = store.classify([candidate("https://example.com/jobs/1"), candidate("https://example.com/jobs/2")])
    assert len(first) == 2 and not known
    second, known = store.classify([candidate("https://example.com/jobs/1"), candidate("https://example.com/jobs/3")])
    assert [item.url for item in second] == ["https://example.com/jobs/3"]
    assert [item.url for item in known] == ["https://example.com/jobs/1"]
    assert store.count() == 3


def test_fingerprint_is_stable():
    assert job_fingerprint(candidate("https://example.com/jobs/1")) == job_fingerprint(candidate("https://example.com/jobs/1"))


def test_registry_uses_configured_sources(tmp_path):
    class FakeSource:
        async def discover(self, *, url, company):
            return [candidate(url + "/1")]

    registry = JobSourceRegistry(
        [JobSourceConfig(id="example", company="Example", url="https://example.com/careers")],
        state_path=str(tmp_path / "seen.json"),
        source_adapter=FakeSource(),
    )
    result = asyncio.run(registry.discover_new())
    assert list(result) == ["example"]
    assert result["example"][0].url.endswith("/1")
