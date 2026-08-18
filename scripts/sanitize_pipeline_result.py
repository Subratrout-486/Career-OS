#!/usr/bin/env python3
"""Create a bounded, secret-free artifact for Conductor reconciliation."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

SECRET_KEY = re.compile(r"(api[_-]?key|token|secret|password|cookie|authorization|credential|private[_-]?key|access[_-]?key|session)", re.I)
RAW_KEY = re.compile(r"(prompt|raw[_-]?(jd|job|description|html|payload)|browser[_-]?context|headers?)", re.I)
MAX_STRING = 8_000
MAX_LIST = 100
MAX_OBJECT = 200
MAX_OUTPUT_BYTES = 512 * 1024


def sanitize(value: Any, key: str = "") -> Any:
    if SECRET_KEY.search(key) or RAW_KEY.search(key):
        return None
    if isinstance(value, dict):
        result = {}
        for child_key, child_value in list(value.items())[:MAX_OBJECT]:
            if SECRET_KEY.search(str(child_key)) or RAW_KEY.search(str(child_key)):
                continue
            cleaned = sanitize(child_value, str(child_key))
            if cleaned is not None:
                result[str(child_key)] = cleaned
        return result
    if isinstance(value, list):
        return [cleaned for item in value[:MAX_LIST] if (cleaned := sanitize(item, key)) is not None]
    if isinstance(value, str):
        return value if len(value) <= MAX_STRING else value[:MAX_STRING] + "...[truncated]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_STRING]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: sanitize_pipeline_result.py INPUT OUTPUT", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    try:
        payload = json.loads(source.read_text(encoding="utf-8")) if source.exists() else {"quality_status": "FAILED", "error_code": "ORCHESTRATOR_NO_RESULT"}
    except Exception:
        payload = {"quality_status": "FAILED", "error_code": "ORCHESTRATOR_INVALID_RESULT"}
    cleaned = sanitize(payload)
    if not isinstance(cleaned, dict):
        cleaned = {"quality_status": "FAILED", "error_code": "ORCHESTRATOR_RESULT_NOT_OBJECT"}
    cleaned["artifact_protocol"] = "career-os-pipeline-result-v1"
    encoded = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_OUTPUT_BYTES:
        reduced = {key: cleaned[key] for key in ("artifact_protocol", "quality_status", "readiness_state", "status", "evidence", "provenance", "error_code") if key in cleaned}
        reduced["artifact_truncated"] = True
        encoded = json.dumps(reduced, ensure_ascii=False, separators=(",", ":"))
    target.write_text(encoded + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
