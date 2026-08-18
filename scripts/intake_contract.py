#!/usr/bin/env python3
"""Validate and annotate Stage-1 Career OS intake records.

Stage 1 has exactly one responsibility: produce durable, validated intake
records. It must not invoke matching, resume generation, Notion processing,
or browser execution.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REQUIRED = ("title", "company", "location", "description")


def validate_job(job: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED:
        if not str(job.get(field, "")).strip():
            errors.append(f"missing:{field}")
    url = str(job.get("url", "")).strip()
    if not url:
        errors.append("missing:url")
    elif not (url.startswith("https://") or url.startswith("http://")):
        errors.append("invalid:url")
    return errors


def canonical_id(job: dict[str, Any]) -> str:
    url = str(job.get("url", "")).strip().lower()
    if url:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    raw = "|".join(str(job.get(k, "")).strip().lower() for k in ("company", "title", "location"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def contract_record(job: dict[str, Any]) -> dict[str, Any]:
    errors = validate_job(job)
    record = dict(job)
    record["job_id"] = canonical_id(job)
    record["pipeline_stage"] = "INTAKE"
    record["status"] = "INTAKED" if not errors else "INTAKE_FAILED"
    record["intake_errors"] = errors
    return record


def validate_paths(paths_file: str, report_file: str) -> int:
    paths = [p.strip() for p in Path(paths_file).read_text(encoding="utf-8").splitlines() if p.strip()]
    report: dict[str, Any] = {"stage": "INTAKE", "total": len(paths), "valid": 0, "invalid": 0, "records": []}
    for raw_path in paths:
        path = Path(raw_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("record_not_object")
            record = contract_record(data)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            ok = not record["intake_errors"]
            report["valid" if ok else "invalid"] += 1
            report["records"].append({"path": str(path), "job_id": record["job_id"], "status": record["status"], "errors": record["intake_errors"]})
        except Exception as exc:
            report["invalid"] += 1
            report["records"].append({"path": str(path), "status": "INTAKE_FAILED", "errors": [f"invalid_json:{exc}"]})
    Path(report_file).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["invalid"]:
        print(f"Stage 1 contract failed: {report['invalid']} invalid record(s)")
        return 1
    print(f"Stage 1 contract passed: {report['valid']} validated intake record(s)")
    return 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--paths", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    raise SystemExit(validate_paths(args.paths, args.report))
