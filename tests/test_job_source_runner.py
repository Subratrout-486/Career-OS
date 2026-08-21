import asyncio

from career_os.job_source_runner import JobSourceRunner


class FakeCatalog:
    def enabled_sources(self):
        return [
            {"id": "good", "url": "https://good.example/jobs", "company": "Good", "timeout_sec": 1},
            {"id": "bad", "url": "https://bad.example/jobs", "company": "Bad", "timeout_sec": 1},
        ]

    def record_success(self, source_id, count):
        self.success = (source_id, count)

    def record_failure(self, source_id, error):
        self.failure = (source_id, error)


class Candidate:
    def __init__(self, url):
        self.url = url


class FakeAdapter:
    async def discover(self, *, url, company):
        if "bad.example" in url:
            raise TimeoutError("source timed out")
        return [Candidate("https://good.example/job/1"), Candidate("https://good.example/job/1")]


def test_one_source_failure_does_not_abort_other_sources():
    result = asyncio.run(JobSourceRunner(catalog=FakeCatalog(), adapter=FakeAdapter()).run_once())
    assert result["successful_sources"] == ["good"]
    assert result["failed_sources"][0]["source_id"] == "bad"
    assert result["job_count"] == 1
