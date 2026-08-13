"""Unit tests for the live Notion Career Evidence Vault loader.

Uses mocked Notion responses — no credentials required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.evidence import retrieve_evidence  # noqa: E402
from career_os.evidence_loader import (  # noqa: E402
    VaultLoadError,
    clear_vault_cache,
    load_evidence_vault,
    parse_notion_page,
    parse_notion_pages,
)


def _title(text: str) -> dict:
    return {
        "type": "title",
        "title": [{"type": "text", "text": {"content": text}, "plain_text": text}],
    }


def _rich(text: str) -> dict:
    return {
        "type": "rich_text",
        "rich_text": [{"type": "text", "text": {"content": text}, "plain_text": text}],
    }


def _select(name: str | None) -> dict:
    if name is None:
        return {"type": "select", "select": None}
    return {"type": "select", "select": {"name": name}}


def _page(page_id: str, props: dict) -> dict:
    return {"id": page_id, "properties": props}


def _full_props(**overrides) -> dict:
    base = {
        "Claim": _title("AWS / cloud application support at FactSet"),
        "Category": _select("Tool"),
        "Employer": _select("FactSet Systems India Pvt. Ltd."),
        "Role": _rich("Product Support Engineer / Research Analyst"),
        "Employment Period": _rich("Nov 2024 – Jan 2026"),
        "Professional Status": _select("Professional-Confirmed"),
        "Usage Level": _select("Frequent"),
        "Context": _rich("Cloud application support context"),
        "Evidence Source": _rich("User confirmation"),
        "Confirmation Status": _select("Confirmed-by-User"),
        "Safe Wording": _rich("Supported cloud-hosted applications at FactSet."),
        "Unsafe Wording": _rich("Owned AWS architecture"),
        "Notes": _rich("Conservative scope"),
    }
    base.update(overrides)
    return base


def test_valid_record():
    page = _page("p1", _full_props())
    item, issue = parse_notion_page(page)
    assert issue is None
    assert item is not None
    assert item.claim.startswith("AWS")
    assert item.employer == "FactSet Systems India Pvt. Ltd."
    assert item.professional_status == "Professional-Confirmed"
    assert item.confirmation_status == "Confirmed-by-User"
    assert "FactSet" in item.safe_wording
    assert item.is_usable_professional


def test_missing_optional_property():
    props = _full_props()
    del props["Notes"]
    del props["Unsafe Wording"]
    item, issue = parse_notion_page(_page("p2", props))
    assert issue is None
    assert item is not None
    assert item.notes == ""
    assert item.unsafe_wording == ""


def test_malformed_properties_not_dict():
    item, issue = parse_notion_page({"id": "bad", "properties": "not-a-dict"})
    assert item is None
    assert issue is not None
    assert "properties" in issue.reason


def test_select_property():
    item, issue = parse_notion_page(_page("p3", _full_props(
        Category=_select("Responsibility"),
        Employer=_select("IGT Solutions"),
    )))
    assert issue is None
    assert item.category == "Responsibility"
    assert item.employer == "IGT Solutions"


def test_title_property():
    item, issue = parse_notion_page(_page("p4", _full_props(
        Claim=_title("ServiceNow / ITSM ticket and incident management"),
    )))
    assert issue is None
    assert "ServiceNow" in item.claim


def test_rich_text_property():
    item, issue = parse_notion_page(_page("p5", _full_props(
        SafeWording=_rich("Managed support tickets in ServiceNow."),
    )))
    assert issue is None
    item2, _ = parse_notion_page(_page("p5b", _full_props(
        **{"Safe Wording": _rich("Managed support tickets in ServiceNow.")}
    )))
    assert "ServiceNow" in item2.safe_wording


def test_empty_vault():
    items, issues = parse_notion_pages([])
    assert items == []
    assert issues == []


def test_multiple_employers():
    pages = [
        _page("a", _full_props(
            Claim=_title("ServiceNow at FactSet"),
            Employer=_select("FactSet Systems India Pvt. Ltd."),
        )),
        _page("b", _full_props(
            Claim=_title("Comcast troubleshooting"),
            Employer=_select("Concentrix (Comcast process)"),
            **{"Professional Status": _select("Professional-Confirmed"),
               "Confirmation Status": _select("Confirmed-by-User")},
        )),
    ]
    items, issues = parse_notion_pages(pages)
    assert len(items) == 2
    employers = {i.employer for i in items}
    assert "FactSet Systems India Pvt. Ltd." in employers
    assert "Concentrix (Comcast process)" in employers


def test_needs_confirmation_item():
    item, issue = parse_notion_page(_page("p6", _full_props(
        Claim=_title("Power BI dashboards for reservation accuracy at IGT"),
        Employer=_select("IGT Solutions"),
        **{
            "Professional Status": _select("Unconfirmed"),
            "Confirmation Status": _select("Needs-Confirmation"),
            "Safe Wording": _rich("(Do not use on resume until confirmed)"),
        },
    )))
    assert issue is None
    assert item is not None
    assert not item.is_usable_professional
    assert item.confirmation_status == "Needs-Confirmation"


def test_self_directed_item():
    item, issue = parse_notion_page(_page("p7", _full_props(
        Claim=_title("AWS specific services EC2 IAM S3 — personal labs"),
        Employer=_select("Self-Directed / Personal"),
        **{
            "Professional Status": _select("Self-Directed"),
            "Confirmation Status": _select("Confirmed-by-User"),
        },
    )))
    assert issue is None
    assert item is not None
    assert not item.is_usable_professional
    assert item.professional_status == "Self-Directed"


def test_missing_claim_reported():
    props = _full_props()
    props["Claim"] = _title("")
    item, issue = parse_notion_page(_page("p8", props))
    assert item is None
    assert issue is not None
    assert "missing required" in issue.reason


def test_load_evidence_vault_mocked_success():
    clear_vault_cache()
    pages = [
        _page("live1", _full_props()),
        _page("live2", _full_props(
            Claim=_title("Power BI dashboards at IGT"),
            Employer=_select("IGT Solutions"),
            **{
                "Professional Status": _select("Unconfirmed"),
                "Confirmation Status": _select("Needs-Confirmation"),
            },
        )),
    ]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.json.return_value = {"results": pages, "has_more": False}

    client = MagicMock()
    client.post.return_value = mock_response

    result = load_evidence_vault(
        token="test-token-not-real",
        data_source_id="eb8a5be7-990e-47d3-9b36-c922ff0bb3aa",
        use_cache=False,
        client=client,
    )
    assert len(result.items) == 2
    assert result.source == "notion"
    aws = next(i for i in result.items if "AWS / cloud" in i.claim)
    assert aws.is_usable_professional
    power = next(i for i in result.items if "Power BI" in i.claim)
    assert not power.is_usable_professional


def test_load_fails_without_token():
    clear_vault_cache()
    try:
        load_evidence_vault(token="", use_cache=False)
        assert False, "expected VaultLoadError"
    except VaultLoadError as exc:
        assert "LIVE VAULT LOAD FAILED" in str(exc)
        assert "NOTION_TOKEN" in str(exc)


def test_load_fails_on_http_error():
    clear_vault_cache()
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.is_error = True
    mock_response.text = "unauthorized"

    client = MagicMock()
    client.post.return_value = mock_response

    try:
        load_evidence_vault(
            token="bad-token",
            use_cache=False,
            client=client,
        )
        assert False, "expected VaultLoadError"
    except VaultLoadError as exc:
        assert "LIVE VAULT LOAD FAILED" in str(exc)


def test_no_silent_snapshot_fallback():
    """Production loader must never return snapshot data when Notion fails."""
    clear_vault_cache()
    try:
        load_evidence_vault(token=None, use_cache=False)
    except VaultLoadError:
        pass
    else:
        raise AssertionError("must raise, not return snapshot")


def test_retrieval_from_loaded_items_power_bi_excluded():
    pages = [
        _page("a", _full_props()),
        _page("b", _full_props(
            Claim=_title("Power BI dashboards for reservation accuracy and SLA compliance at IGT"),
            Employer=_select("IGT Solutions"),
            Category=_select("Tool"),
            Context=_rich("Power BI dashboards at IGT — unconfirmed"),
            **{
                "Professional Status": _select("Unconfirmed"),
                "Confirmation Status": _select("Needs-Confirmation"),
                "Safe Wording": _rich("(Do not use on resume until confirmed)"),
            },
        )),
        _page("c", _full_props(
            Claim=_title("ServiceNow / ITSM ticket and incident management"),
            Employer=_select("FactSet Systems India Pvt. Ltd."),
            Context=_rich("ServiceNow ticket workflow"),
            **{
                "Professional Status": _select("Professional-Confirmed"),
                "Confirmation Status": _select("Confirmed-by-User"),
                "Safe Wording": _rich("Managed support tickets in ServiceNow."),
            },
        )),
        _page("d", _full_props(
            Claim=_title("Oracle / PL/SQL for application and data investigation"),
            Employer=_select("FactSet Systems India Pvt. Ltd."),
            Context=_rich("Oracle SQL investigation"),
            **{
                "Professional Status": _select("Professional-Confirmed"),
                "Confirmation Status": _select("Confirmed-by-User"),
                "Safe Wording": _rich("Used Oracle SQL and PL/SQL during support work."),
            },
        )),
        _page("e", _full_props(
            Claim=_title("Comcast / Xfinity technical troubleshooting"),
            Employer=_select("Concentrix (Comcast process)"),
            Category=_select("Responsibility"),
            Context=_rich("Comcast connectivity troubleshooting"),
            **{
                "Professional Status": _select("Professional-Confirmed"),
                "Confirmation Status": _select("Confirmed-by-User"),
                "Safe Wording": _rich("First-line Comcast technical troubleshooting."),
            },
        )),
    ]
    items, issues = parse_notion_pages(pages)
    assert not issues

    aws = retrieve_evidence("AWS cloud application support", items)
    assert aws.has_usable_evidence
    assert any("AWS" in m.item.claim for m in aws.matched)
    for m in aws.matched:
        if "AWS" in m.item.claim:
            assert m.item.employer == "FactSet Systems India Pvt. Ltd."
            assert m.item.professional_status == "Professional-Confirmed"

    snow = retrieve_evidence("ServiceNow and incident management", items)
    assert snow.has_usable_evidence
    assert any("ServiceNow" in m.item.claim for m in snow.matched)

    sql = retrieve_evidence("SQL troubleshooting and Oracle database support", items)
    assert sql.has_usable_evidence
    assert any("Oracle" in m.item.claim or "SQL" in m.item.claim for m in sql.matched)

    support = retrieve_evidence("Customer-facing technical support", items)
    assert support.has_usable_evidence

    power = retrieve_evidence(
        "Power BI dashboard development", items, include_diagnostic=True
    )
    assert not power.has_usable_evidence
    assert power.has_related_unconfirmed
    assert any("Power BI" in e.item.claim for e in power.excluded)


def test_parse_continues_after_bad_row():
    pages = [
        _page("good", _full_props()),
        {"id": "bad", "properties": "broken"},
        _page("good2", _full_props(Claim=_title("Excel / Advanced Excel"))),
    ]
    items, issues = parse_notion_pages(pages)
    assert len(items) == 2
    assert len(issues) == 1
    assert issues[0].page_id == "bad"


if __name__ == "__main__":
    import traceback

    tests = [n for n in dir() if n.startswith("test_")]
    passed = failed = 0
    for name in tests:
        try:
            globals()[name]()
            print(f"PASS  {name}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {name}: {exc}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    raise SystemExit(1 if failed else 0)
