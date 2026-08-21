from career_os.job_sources import JobCandidate
from career_os.seen_jobs import SeenJobStore


def test_new_only_persists_between_instances(tmp_path):
    path = tmp_path / "seen.json"
    job = JobCandidate(title="Analyst", company="Acme", url="https://acme.example/jobs/1")

    first = SeenJobStore(path)
    assert first.new_only([job]) == [job]

    second = SeenJobStore(path)
    assert second.new_only([job]) == []
    assert second.count() == 1
