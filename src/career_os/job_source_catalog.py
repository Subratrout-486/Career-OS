"""Validated, local-first catalog for Career OS job sources.

The catalog keeps source configuration separate from source execution. This
mirrors declarative workflow systems: configuration selects tools, while the
source adapter performs the network operation. Credentials are intentionally
excluded from this file and must be supplied by an authenticated tool boundary.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass
class SourceRecord:
    id: str
    company: str
    url: str
    source_type: str = "company_careers"
    enabled: bool = True
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    discovered_count: int = 0


class JobSourceCatalog:
    """Loads and durably tracks configured job sources."""

    SUPPORTED_TYPES = {"company_careers"}

    def __init__(self, *, config_path: str | Path, state_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path)
        self.state_path = Path(state_path or self.config_path.with_name("job_source_state.json"))
        self.sources: dict[str, SourceRecord] = {}
        self._load()

    def enabled_sources(self) -> list[SourceRecord]:
        return [source for source in self.sources.values() if source.enabled]

    def record_success(self, source_id: str, *, discovered_count: int) -> None:
        source = self._get(source_id)
        now = time.time()
        source.last_success_at = now
        source.last_failure_at = None
        source.last_error = None
        source.consecutive_failures = 0
        source.discovered_count = discovered_count
        self._persist_state()

    def record_failure(self, source_id: str, error: str) -> None:
        source = self._get(source_id)
        source.last_failure_at = time.time()
        source.last_error = str(error)
        source.consecutive_failures += 1
        self._persist_state()

    def _load(self) -> None:
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        items = raw.get("sources", [])
        if not isinstance(items, list):
            raise ValueError("job source config 'sources' must be a list")
        for item in items:
            source = SourceRecord(**self._validate_item(item))
            if source.id in self.sources:
                raise ValueError(f"duplicate job source id: {source.id}")
            self.sources[source.id] = source

        if self.state_path.exists():
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            for source_id, values in state.get("sources", {}).items():
                if source_id in self.sources:
                    for key in (
                        "last_success_at", "last_failure_at", "last_error",
                        "consecutive_failures", "discovered_count",
                    ):
                        if key in values:
                            setattr(self.sources[source_id], key, values[key])

    def _validate_item(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("each job source must be an object")
        required = ("id", "company", "url")
        missing = [key for key in required if not item.get(key)]
        if missing:
            raise ValueError(f"job source missing required fields: {missing}")
        source_type = item.get("source_type", "company_careers")
        if source_type not in self.SUPPORTED_TYPES:
            raise ValueError(f"unsupported job source type: {source_type}")
        parsed = urlparse(str(item["url"]))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"job source URL must be absolute http(s): {item['url']}")
        return {
            "id": str(item["id"]),
            "company": str(item["company"]),
            "url": str(item["url"]),
            "source_type": source_type,
            "enabled": bool(item.get("enabled", True)),
        }

    def _get(self, source_id: str) -> SourceRecord:
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise KeyError(f"unknown job source: {source_id}") from exc

    def _persist_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"sources": {key: asdict(value) for key, value in self.sources.items()}}
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)
