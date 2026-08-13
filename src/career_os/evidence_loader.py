"""Live Notion Career Evidence Vault loader.

Production source of truth is the live Notion data source.
The offline snapshot in evidence_vault_snapshot.py is test-only.

Fail-safe: if the live vault cannot be loaded, raise VaultLoadError.
Do NOT silently fall back to the static snapshot in production.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

import httpx

from .evidence import EvidenceItem

DEFAULT_VAULT_DATA_SOURCE_ID = "eb8a5be7-990e-47d3-9b36-c922ff0bb3aa"

# Short-lived in-memory cache (seconds). Not a second source of truth.
_CACHE_TTL_SECONDS = 60.0
_cache_items: list[EvidenceItem] | None = None
_cache_loaded_at: float = 0.0
_cache_key: str = ""


class VaultLoadError(RuntimeError):
    """Raised when the live Career Evidence Vault cannot be loaded.

    Callers must treat this as: retrieval unavailable — do not pretend
    the complete evidence base was searched.
    """


@dataclass
class ParseIssue:
    page_id: str
    reason: str
    raw_claim: str = ""


@dataclass
class VaultLoadResult:
    items: list[EvidenceItem]
    issues: list[ParseIssue] = field(default_factory=list)
    source: str = "notion"
    data_source_id: str = ""

    @property
    def ok(self) -> bool:
        return True  # successful HTTP load even if some rows had issues

    def __len__(self) -> int:
        return len(self.items)


# ---------------------------------------------------------------------------
# Notion property parsers (no invented defaults for required fields)
# ---------------------------------------------------------------------------

def _rich_text_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, list):
        return str(value).strip()
    parts: list[str] = []
    for block in value:
        if not isinstance(block, dict):
            continue
        if "plain_text" in block:
            parts.append(str(block.get("plain_text") or ""))
        elif block.get("type") == "text":
            parts.append(str((block.get("text") or {}).get("content") or ""))
        else:
            text = block.get("text") or block.get("mention") or {}
            if isinstance(text, dict) and "content" in text:
                parts.append(str(text.get("content") or ""))
    return "".join(parts).strip()


def _select_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        name = value.get("name")
        return str(name).strip() if name is not None else ""
    return str(value).strip()


def _extract_property(prop: Any) -> str:
    """Extract a plain string from a Notion property object or bare value."""
    if prop is None:
        return ""
    if isinstance(prop, str):
        return prop.strip()
    if not isinstance(prop, dict):
        return str(prop).strip()

    if "name" in prop and "type" not in prop and "title" not in prop and "rich_text" not in prop:
        return _select_to_str(prop)

    ptype = prop.get("type")
    if ptype == "title":
        return _rich_text_to_str(prop.get("title"))
    if ptype == "rich_text":
        return _rich_text_to_str(prop.get("rich_text"))
    if ptype == "select":
        return _select_to_str(prop.get("select"))
    if ptype == "multi_select":
        items = prop.get("multi_select") or []
        return ", ".join(_select_to_str(x) for x in items if x)
    if ptype == "url":
        return str(prop.get("url") or "").strip()
    if ptype == "number":
        num = prop.get("number")
        return "" if num is None else str(num)
    if ptype == "checkbox":
        return "true" if prop.get("checkbox") else "false"
    if ptype == "status":
        return _select_to_str(prop.get("status"))

    for key in ("title", "rich_text", "select", "status", "name", "plain_text"):
        if key in prop:
            if key in ("title", "rich_text"):
                return _rich_text_to_str(prop.get(key))
            if key in ("select", "status", "name"):
                return _select_to_str(prop.get(key))
            return str(prop.get(key) or "").strip()
    return ""


def _get_prop(properties: dict[str, Any], *names: str) -> str:
    for name in names:
        if name in properties:
            return _extract_property(properties[name])
    lower_map = {k.lower(): k for k in properties}
    for name in names:
        key = lower_map.get(name.lower())
        if key is not None:
            return _extract_property(properties[key])
    return ""


def parse_notion_page(page: dict[str, Any]) -> tuple[EvidenceItem | None, ParseIssue | None]:
    """Parse a single Notion page/row into an EvidenceItem.

    Required: Claim (title). Missing claim → issue, no invented item.
    Optional fields may be empty strings without inventing content.
    """
    page_id = str(page.get("id") or page.get("page_id") or "")
    properties = page.get("properties") or {}
    if not isinstance(properties, dict):
        return None, ParseIssue(page_id=page_id, reason="properties is not a dict")

    claim = _get_prop(properties, "Claim", "Name", "title")
    if not claim:
        return None, ParseIssue(
            page_id=page_id,
            reason="missing required title/Claim property",
            raw_claim="",
        )

    try:
        item = EvidenceItem(
            claim=claim,
            category=_get_prop(properties, "Category"),
            employer=_get_prop(properties, "Employer"),
            role=_get_prop(properties, "Role"),
            employment_period=_get_prop(properties, "Employment Period", "EmploymentPeriod"),
            professional_status=_get_prop(properties, "Professional Status", "ProfessionalStatus"),
            usage_level=_get_prop(properties, "Usage Level", "UsageLevel"),
            context=_get_prop(properties, "Context"),
            evidence_source=_get_prop(properties, "Evidence Source", "EvidenceSource"),
            confirmation_status=_get_prop(properties, "Confirmation Status", "ConfirmationStatus"),
            safe_wording=_get_prop(properties, "Safe Wording", "SafeWording"),
            unsafe_wording=_get_prop(properties, "Unsafe Wording", "UnsafeWording"),
            notes=_get_prop(properties, "Notes"),
        )
    except Exception as exc:  # noqa: BLE001 — report, do not invent
        return None, ParseIssue(
            page_id=page_id,
            reason=f"failed to construct EvidenceItem: {exc}",
            raw_claim=claim,
        )

    return item, None


def parse_notion_pages(
    pages: Sequence[dict[str, Any]],
) -> tuple[list[EvidenceItem], list[ParseIssue]]:
    items: list[EvidenceItem] = []
    issues: list[ParseIssue] = []
    for page in pages:
        item, issue = parse_notion_page(page)
        if item is not None:
            items.append(item)
        if issue is not None:
            issues.append(issue)
    return items, issues


# ---------------------------------------------------------------------------
# HTTP loader
# ---------------------------------------------------------------------------

def _normalize_data_source_id(raw: str | None) -> str:
    value = (raw or DEFAULT_VAULT_DATA_SOURCE_ID).strip()
    return value.replace("collection://", "")


def _notion_headers(token: str, version: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": version,
        "Content-Type": "application/json",
    }


def _query_data_source(
    *,
    token: str,
    version: str,
    data_source_id: str,
    client: httpx.Client,
) -> list[dict[str, Any]]:
    """Query all rows from the Career Evidence Vault data source.

    Tries the data_sources query endpoint first, then falls back to the
    classic databases query endpoint with the same ID.
    """
    headers = _notion_headers(token, version)
    endpoints = [
        f"https://api.notion.com/v1/data_sources/{data_source_id}/query",
        f"https://api.notion.com/v1/databases/{data_source_id}/query",
    ]
    last_error: Exception | None = None
    for url in endpoints:
        pages: list[dict[str, Any]] = []
        cursor: str | None = None
        try:
            while True:
                body: dict[str, Any] = {"page_size": 100}
                if cursor:
                    body["start_cursor"] = cursor
                response = client.post(url, headers=headers, json=body, timeout=60.0)
                if response.status_code == 404:
                    last_error = RuntimeError(f"404 from {url}")
                    break
                if response.is_error:
                    raise VaultLoadError(
                        f"LIVE VAULT LOAD FAILED — Notion query error "
                        f"({response.status_code}): {response.text[:500]}"
                    )
                data = response.json()
                results = data.get("results") or []
                if not isinstance(results, list):
                    raise VaultLoadError(
                        "LIVE VAULT LOAD FAILED — unexpected Notion response shape"
                    )
                pages.extend(results)
                if not data.get("has_more"):
                    return pages
                cursor = data.get("next_cursor")
                if not cursor:
                    return pages
            continue
        except VaultLoadError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise VaultLoadError(
        f"LIVE VAULT LOAD FAILED — could not query data source "
        f"{data_source_id}: {last_error}"
    )


def load_evidence_vault(
    *,
    token: str | None = None,
    data_source_id: str | None = None,
    version: str | None = None,
    use_cache: bool = True,
    client: httpx.Client | None = None,
) -> VaultLoadResult:
    """Load the live Career Evidence Vault from Notion.

    Raises VaultLoadError when credentials are missing or Notion is unreachable.
    Never falls back to the offline snapshot.
    """
    global _cache_items, _cache_loaded_at, _cache_key

    resolved_token = token if token is not None else os.getenv("NOTION_TOKEN")
    resolved_version = version or os.getenv("NOTION_VERSION", "2026-03-11")
    resolved_ds = _normalize_data_source_id(
        data_source_id
        or os.getenv("NOTION_EVIDENCE_VAULT_DATA_SOURCE_ID")
        or DEFAULT_VAULT_DATA_SOURCE_ID
    )

    if not resolved_token:
        raise VaultLoadError(
            "LIVE VAULT LOAD FAILED — NOTION_TOKEN is not configured. "
            "Retrieval is unavailable; the offline snapshot must not be used "
            "as production truth."
        )

    cache_key = f"{resolved_ds}:{resolved_version}"
    now = time.monotonic()
    if (
        use_cache
        and _cache_items is not None
        and _cache_key == cache_key
        and (now - _cache_loaded_at) < _CACHE_TTL_SECONDS
    ):
        return VaultLoadResult(
            items=list(_cache_items),
            issues=[],
            source="notion-cache",
            data_source_id=resolved_ds,
        )

    owns_client = client is None
    http_client = client or httpx.Client(timeout=60.0)
    try:
        pages = _query_data_source(
            token=resolved_token,
            version=resolved_version,
            data_source_id=resolved_ds,
            client=http_client,
        )
    finally:
        if owns_client:
            http_client.close()

    items, issues = parse_notion_pages(pages)

    if use_cache:
        _cache_items = list(items)
        _cache_loaded_at = time.monotonic()
        _cache_key = cache_key

    return VaultLoadResult(
        items=items,
        issues=issues,
        source="notion",
        data_source_id=resolved_ds,
    )


def clear_vault_cache() -> None:
    """Clear the short-lived in-memory cache (tests / explicit refresh)."""
    global _cache_items, _cache_loaded_at, _cache_key
    _cache_items = None
    _cache_loaded_at = 0.0
    _cache_key = ""


def load_evidence_vault_or_raise() -> list[EvidenceItem]:
    """Convenience wrapper for production callers.

    Returns items only. Raises VaultLoadError on any load failure.
    """
    result = load_evidence_vault()
    return result.items
