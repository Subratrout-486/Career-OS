"""Regression tests for robust structured JSON extraction.

Guards against the HighRadius RESUME_GENERATION_FAILED:
  Extra data: line 74 column 1
caused by find('{')/rfind('}') grabbing trailing content.
"""

from __future__ import annotations

import json

import pytest

from career_os.structured_output import (
    StructuredOutputError,
    extract_first_json_object,
    parse_structured_json,
)


def test_pure_json_object():
    raw = '{"title": "Support", "skills": ["SQL"]}'
    assert extract_first_json_object(raw) == raw
    assert parse_structured_json(raw)["title"] == "Support"


def test_json_with_trailing_prose():
    raw = '{"title": "A", "skills": []}\nHere is an explanation of the resume.'
    cleaned = extract_first_json_object(raw)
    assert json.loads(cleaned)["title"] == "A"


def test_json_followed_by_second_json_object():
    """The exact failure mode that produced Extra data: line 74 column 1."""
    first = {
        "title": "Product Support Engineer",
        "summary": "Support engineer",
        "skills": ["SQL", "ServiceNow"],
        "experience": [{"title": "PSE", "company": "FactSet", "dates": "2024-2026", "bullets": ["SQL"]}],
        "education": ["B.Com"],
        "changes": [],
        "unsupported_claims": [],
        "evidence_trace": [],
    }
    second = {"note": "extra object that used to break json.loads"}
    raw = json.dumps(first, indent=2) + "\n" + json.dumps(second, indent=2)
    cleaned = extract_first_json_object(raw)
    parsed = json.loads(cleaned)
    assert parsed["title"] == "Product Support Engineer"
    assert "note" not in parsed


def test_markdown_fenced_json():
    raw = '```json\n{"fit_score": 72, "recommendation": "APPLY"}\n```'
    cleaned = extract_first_json_object(raw)
    assert json.loads(cleaned)["fit_score"] == 72


def test_leading_prose_then_json():
    raw = 'Sure, here is the resume JSON:\n{"title": "Ops", "skills": ["Python"]}'
    assert json.loads(extract_first_json_object(raw))["title"] == "Ops"


def test_old_find_rfind_would_fail_but_raw_decode_succeeds():
    """Document that the old algorithm fails on this input while the new one works."""
    payload = '{"a": 1}\n{"b": 2}'
    start, end = payload.find("{"), payload.rfind("}")
    bad_slice = payload[start : end + 1]
    with pytest.raises(json.JSONDecodeError, match="Extra data"):
        json.loads(bad_slice)
    assert json.loads(extract_first_json_object(payload)) == {"a": 1}


def test_empty_raises():
    with pytest.raises(StructuredOutputError):
        extract_first_json_object("   ")


def test_no_json_raises():
    with pytest.raises(StructuredOutputError):
        extract_first_json_object("no braces here at all")
