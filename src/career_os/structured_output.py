"""Robust extraction of a single JSON object from model text.

AI providers sometimes return a valid JSON object followed by commentary
or a second JSON blob. Using text.find("{") + text.rfind("}") then
json.loads() produces "Extra data: line N column 1". This module extracts
only the first complete JSON value via JSONDecoder.raw_decode.
"""

from __future__ import annotations

import json
import re
from typing import Any


class StructuredOutputError(ValueError):
    """Raised when no valid JSON object can be extracted from model text."""


def strip_code_fences(text: str) -> str:
    """Remove surrounding markdown code fences if present."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_first_json_object(text: str) -> str:
    """Return the JSON string of the first complete object/array in text.

    Handles:
    - pure JSON
    - JSON inside ```json fences
    - leading/trailing prose
    - a second JSON object after the first (ignores the rest)
    """
    cleaned = strip_code_fences(text)
    if not cleaned:
        raise StructuredOutputError("Empty model output; no JSON to parse")

    # Fast path: whole string is valid JSON
    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    # Search from each '{' or '[' so nested structures are handled correctly
    for match in re.finditer(r"[{\[]", cleaned):
        start = match.start()
        try:
            _obj, end = decoder.raw_decode(cleaned, start)
            candidate = cleaned[start:end].strip()
            # Prefer objects over arrays for resume/fit payloads
            if candidate.startswith("{"):
                return candidate
            # Keep first array only if no object found later — continue search
        except json.JSONDecodeError:
            continue

    # Second pass: accept first array if no object was found
    for match in re.finditer(r"[{\[]", cleaned):
        start = match.start()
        try:
            _obj, end = decoder.raw_decode(cleaned, start)
            return cleaned[start:end].strip()
        except json.JSONDecodeError:
            continue

    raise StructuredOutputError(
        "Could not extract a complete JSON value from model output"
    )


def parse_structured_json(text: str) -> Any:
    """Extract and parse the first JSON value from model text."""
    return json.loads(extract_first_json_object(text))
