"""Optional live smoke test against the real Notion Career Evidence Vault.

Skips cleanly when NOTION_TOKEN is not set.
Never prints the token.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from career_os.evidence import retrieve_evidence, format_retrieval  # noqa: E402
from career_os.evidence_loader import (  # noqa: E402
    VaultLoadError,
    clear_vault_cache,
    load_evidence_vault,
)


def test_live_vault_smoke():
    token = os.getenv("NOTION_TOKEN")
    if not token:
        print("SKIP  test_live_vault_smoke — NOTION_TOKEN not set")
        return

    clear_vault_cache()
    result = load_evidence_vault(use_cache=False)
    assert result.source in {"notion", "notion-cache"}
    assert len(result.items) > 0, "live vault returned zero items"
    assert result.data_source_id

    if result.issues:
        print(f"WARN  {len(result.issues)} parse issue(s)")
        for issue in result.issues[:5]:
            print(f"  - {issue.page_id}: {issue.reason}")

    employers = {i.employer for i in result.items}
    assert employers, "employers should be present"

    aws = retrieve_evidence("AWS cloud application support", result.items)
    assert aws.has_usable_evidence, "expected FactSet AWS professional evidence"
    assert all(
        m.item.professional_status == "Professional-Confirmed" for m in aws.matched
    )

    snow = retrieve_evidence("ServiceNow and incident management", result.items)
    assert snow.has_usable_evidence

    sql = retrieve_evidence("SQL troubleshooting and Oracle", result.items)
    assert sql.has_usable_evidence

    support = retrieve_evidence("Customer-facing technical support", result.items)
    assert support.has_usable_evidence

    power = retrieve_evidence(
        "Power BI dashboard development", result.items, include_diagnostic=True
    )
    assert not power.has_usable_evidence, "Power BI must not be usable professional evidence"
    if power.has_related_unconfirmed:
        assert any("Power BI" in e.item.claim or "Power" in e.item.claim for e in power.excluded)

    print("LIVE SMOKE OK")
    print(f"  items loaded: {len(result.items)}")
    print(f"  parse issues: {len(result.issues)}")
    print(f"  employers: {sorted(employers)}")
    print("---")
    print(format_retrieval(aws, show_excluded=False))
    print("---")
    print(format_retrieval(power, show_excluded=True))


def test_live_fail_safe_without_token_message():
    """Even without token, error message must be explicit."""
    clear_vault_cache()
    old = os.environ.pop("NOTION_TOKEN", None)
    try:
        try:
            load_evidence_vault(token="", use_cache=False)
            raise AssertionError("expected VaultLoadError")
        except VaultLoadError as exc:
            msg = str(exc)
            assert "LIVE VAULT LOAD FAILED" in msg
            assert "snapshot" in msg.lower() or "NOTION_TOKEN" in msg
    finally:
        if old is not None:
            os.environ["NOTION_TOKEN"] = old


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
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
