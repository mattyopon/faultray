# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Spreadsheet formula-injection neutralizer for CSV exports.

User-supplied topology data (component names, scenario descriptions, reasons,
owners) flows verbatim into CSV exports. A spreadsheet (Excel / Google Sheets /
LibreOffice) treats any cell beginning with ``=``, ``+``, ``-``, ``@`` — or a
leading TAB/CR before one of those — as a *formula*, so an attacker-controlled
value like ``=HYPERLINK("http://evil","click")`` or ``=cmd|'/c calc'!A1``
executes on open (CSV injection, CWE-1236).

This mirrors the neutralizer the TypeScript exporters already apply
(``remediation``/``audit-log`` pages in faultray-app): prefix the offending
cell with a single quote so the spreadsheet renders it as literal text. The
``csv`` module already handles delimiter/quote escaping, so we only add the
formula-defusing prefix here.

Use :func:`neutralize_rows` / :func:`neutralize_row` right before handing rows
to ``csv.DictWriter``/``csv.writer``.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

# Leading whitespace (which spreadsheets trim) followed by a formula trigger.
_FORMULA_LEAD = re.compile(r"^[\s]*[=+\-@]")


def neutralize(value: Any) -> Any:
    """Return *value* with spreadsheet formula triggers defused.

    Only ``str`` values are transformed; numbers/bools pass through unchanged
    so legitimate negative numbers (e.g. ``-1.5``) are never mangled into text.
    """
    if not isinstance(value, str):
        return value
    if _FORMULA_LEAD.match(value) or value[:1] in ("\t", "\r"):
        return "'" + value
    return value


def neutralize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of *row* (a dict) with every value neutralized."""
    return {key: neutralize(val) for key, val in row.items()}


def neutralize_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return a list of dict rows with every value neutralized."""
    return [neutralize_row(row) for row in rows]


def neutralize_cells(cells: Iterable[Any]) -> list[Any]:
    """Return a list (one positional CSV record) with every cell neutralized."""
    return [neutralize(cell) for cell in cells]
