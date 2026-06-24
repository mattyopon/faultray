"""Tests for the CSV formula-injection neutralizer."""

from __future__ import annotations

import csv
import io

import pytest

from faultray.reporter.csv_safe import (
    neutralize,
    neutralize_cells,
    neutralize_row,
    neutralize_rows,
)


@pytest.mark.parametrize("payload", [
    "=HYPERLINK(\"http://evil\",\"x\")",
    "+1+1",
    "-2+3",
    "@SUM(A1:A9)",
    "=cmd|'/c calc'!A1",
    "  =1+1",          # leading whitespace then formula (sheets trims it)
    "\t=1+1",          # leading tab then formula
    "\r=1+1",          # leading CR then formula
])
def test_formula_payloads_are_prefixed(payload: str) -> None:
    out = neutralize(payload)
    assert out.startswith("'"), out


@pytest.mark.parametrize("benign", [
    "Web Frontend 1",
    "PostgreSQL (User Data)",
    "Auth & Billing",
    "O'Brien's DB",
    "normal text",
    "",
])
def test_benign_strings_untouched(benign: str) -> None:
    assert neutralize(benign) == benign


@pytest.mark.parametrize("value", [0, 1, -1, -1.5, 3.14, True, False, None])
def test_non_strings_pass_through(value: object) -> None:
    # Numbers/bools/None must not be mangled (e.g. -1.5 stays numeric).
    assert neutralize(value) == value


def test_neutralize_row_only_touches_string_values() -> None:
    row = {"name": "=evil", "score": -1.5, "count": 3, "note": "ok"}
    out = neutralize_row(row)
    assert out["name"] == "'=evil"
    assert out["score"] == -1.5  # negative number preserved
    assert out["count"] == 3
    assert out["note"] == "ok"


def test_neutralize_rows_roundtrips_through_csv() -> None:
    rows = [{"name": "=cmd", "v": -2}, {"name": "safe", "v": 5}]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["name", "v"])
    writer.writeheader()
    writer.writerows(neutralize_rows(rows))
    text = buf.getvalue()
    # Read back: the formula cell is now literal text starting with '.
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert parsed[0]["name"] == "'=cmd"
    assert parsed[0]["v"] == "-2"      # negative number survived as-is
    assert parsed[1]["name"] == "safe"


def test_neutralize_cells_positional() -> None:
    assert neutralize_cells(["=x", 1, "ok"]) == ["'=x", 1, "ok"]
