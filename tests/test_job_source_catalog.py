import json

import pytest

from career_os.job_source_catalog import JobSourceCatalog


def test_catalog_validates_and_persists_source_health(tmp_path):
    config = tmp_path / "sources.json"
    state = tmp_path / "state.json"
    config.write_text(json.dumps({"sources": [
        {"id": "a", "company": "A", "url": "https://example.com/careers", "enabled": True}
    ]}))

    catalog = JobSourceCatalog(config_path=config, state_path=state)
    assert [s.id for s in catalog.enabled_sources()] == ["a"]

    catalog.record_failure("a", "timeout")
    catalog.record_failure("a", "503")
    assert catalog.sources["a"].consecutive_failures == 2

    reloaded = JobSourceCatalog(config_path=config, state_path=state)
    assert reloaded.sources["a"].last_error == "503"
    assert reloaded.sources["a"].consecutive_failures == 2

    reloaded.record_success("a", discovered_count=7)
    assert reloaded.sources["a"].consecutive_failures == 0
    assert reloaded.sources["a"].discovered_count == 7


def test_catalog_rejects_bad_source(tmp_path):
    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"sources": [
        {"id": "bad", "company": "Bad", "url": "not-a-url"}
    ]}))
    with pytest.raises(ValueError):
        JobSourceCatalog(config_path=config)
