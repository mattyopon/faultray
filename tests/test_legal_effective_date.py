"""Regression tests for legal policy headers (#94).

Guards docs/legal/*.md and rendered docs/legal/**/index.html from
regressing to '[To be determined]' placeholder for Effective Date, and
ensures both files carry a Version field for audit trail.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_LEGAL = _ROOT / "docs" / "legal"

_POLICY_FILES = [
    _LEGAL / "privacy-policy.md",
    _LEGAL / "terms-of-service.md",
    _LEGAL / "privacy-policy" / "index.html",
    _LEGAL / "terms-of-service" / "index.html",
]

_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


@pytest.mark.parametrize("path", _POLICY_FILES)
def test_no_placeholder_effective_date(path: Path):
    assert path.exists(), f"expected legal file missing: {path}"
    text = path.read_text(encoding="utf-8")
    assert "[To be determined]" not in text, (
        f"{path.name} still contains '[To be determined]' placeholder "
        f"for a dated field — set a real ISO date (#94)"
    )


@pytest.mark.parametrize("path", _POLICY_FILES)
def test_effective_date_is_iso_format(path: Path):
    text = path.read_text(encoding="utf-8")
    # Markdown: **Effective Date:** 2026-04-22
    # HTML:     <strong>Effective Date:</strong> 2026-04-22
    m = re.search(r"Effective Date:\s*(?:</strong>)?\s*\**\s*(\d{4}-\d{2}-\d{2})", text)
    assert m, f"{path.name}: could not find 'Effective Date: YYYY-MM-DD'"
    assert _ISO_DATE.fullmatch(m.group(1)), (
        f"{path.name}: Effective Date must be ISO yyyy-mm-dd, got {m.group(1)!r}"
    )


@pytest.mark.parametrize("path", _POLICY_FILES)
def test_version_field_present(path: Path):
    text = path.read_text(encoding="utf-8")
    # Markdown: **Version:** 1.0
    # HTML:     <strong>Version:</strong> 1.0
    assert re.search(r"Version:\s*(?:</strong>)?\s*\**\s*\d+(?:\.\d+)*", text), (
        f"{path.name}: expected a 'Version: X.Y' line for audit trail (#94)"
    )
