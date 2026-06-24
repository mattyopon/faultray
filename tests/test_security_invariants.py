"""Lightweight CI guards that lock in the security quick-win fixes.

These run as part of the normal pytest suite (no separate workflow) and are
designed to PASS on the current tree while failing if a fix is reverted —
e.g. a sensitive integrity file dropping back to an unkeyed hash, or a CSV
exporter bypassing the formula-injection neutralizer. They are intentionally
file-scoped (not a blanket ban) so they do not break on unrelated existing code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from faultray.model.components import Component, ComponentType

SRC = Path(__file__).resolve().parents[1] / "src" / "faultray"


# ---------------------------------------------------------------------------
# Component model-boundary validator (XSS / report-injection)
# ---------------------------------------------------------------------------

def _component(**kw) -> Component:
    base = dict(id="svc-1", name="Web", type=ComponentType.WEB_SERVER)
    base.update(kw)
    return Component(**base)


@pytest.mark.parametrize("field", ["id", "name", "host", "owner"])
@pytest.mark.parametrize("payload", [
    "<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "a>b",
    "x<svg/onload=1>", "line1\r\nline2", "tab\tinject", "nul\x00byte",
])
def test_component_rejects_injection_chars(field: str, payload: str) -> None:
    with pytest.raises(ValidationError):
        _component(**{field: payload})


@pytest.mark.parametrize("name", [
    "CloudFront CDN", "PostgreSQL (User Data)", "Auth & Billing",
    "O'Brien's DB", 'say "hi" svc', "db-primary_01",
])
def test_component_accepts_legitimate_names(name: str) -> None:
    assert _component(name=name).name == name


# ---------------------------------------------------------------------------
# Integrity primitives must be keyed in sensitive files
# ---------------------------------------------------------------------------

def test_sensitive_integrity_files_using_sha256_also_use_hmac() -> None:
    """Audit/seal/license files that hash with sha256 must also use hmac, so a
    tamper-evidence / signing primitive is never shipped unkeyed."""
    offenders = []
    for path in SRC.rglob("*.py"):
        if not re.search(r"audit|seal|licens|coupon", path.name, re.I):
            continue
        text = path.read_text(encoding="utf-8")
        if "hashlib.sha256" in text and "hmac" not in text:
            offenders.append(str(path.relative_to(SRC)))
    assert not offenders, f"unkeyed sha256 in sensitive file(s): {offenders}"


def test_audit_chain_links_are_hmac_keyed() -> None:
    text = (SRC / "reporter" / "audit_chain.py").read_text(encoding="utf-8")
    assert "hmac.new(" in text
    assert "compare_digest" in text


# ---------------------------------------------------------------------------
# CSV exporters must route through the formula-injection neutralizer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rel", ["reporter/export.py", "cli/fmea_cmd.py"])
def test_csv_exporters_use_neutralizer(rel: str) -> None:
    text = (SRC / rel).read_text(encoding="utf-8")
    assert "csv_safe" in text, f"{rel} writes CSV without the csv_safe neutralizer"
