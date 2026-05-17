# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.
"""Regression for #151 — insurance scoring endpoint must not leak raw
exception text to HTTP clients.

The bug was a single ``return JSONResponse({"error": f"...: {exc}"}, ...)``
inside the catch-all. Re-introducing that shape lets attackers map
parser internals / validation specifics by spraying malformed
payloads. The source-scan keeps a wider net than a single endpoint
integration test would.
"""
from __future__ import annotations

import re
from pathlib import Path

INSURANCE_API = Path(__file__).resolve().parent.parent / "src" / "faultray" / "api" / "insurance_api.py"


def _strip_comments(src: str) -> str:
    # Drop comment lines (``# ...``) so explanatory text mentioning
    # forbidden patterns doesn't trip the scan.
    return "\n".join(
        line for line in src.splitlines()
        if not line.lstrip().startswith("#")
    )


def test_no_raw_exception_message_returned() -> None:
    src = _strip_comments(INSURANCE_API.read_text())
    # ``"error": f"...: {exc}"`` and any close variant must not appear.
    forbidden = [
        r'"error":\s*f["\'][^"\']*\{exc\}',
        r'"error":\s*f["\'][^"\']*\{e\}',
        r'"error":\s*str\(exc\)',
        r'"error":\s*str\(e\)',
    ]
    for pat in forbidden:
        assert not re.search(pat, src), (
            f"#151 regression: raw exception text reachable via pattern {pat!r}"
        )


def test_endpoint_still_logs_failures() -> None:
    """The fix should preserve detailed logging for operators."""
    src = INSURANCE_API.read_text()
    # The fix path keeps ``logger.warning("Insurance scoring failed: %s", exc, exc_info=True)``.
    assert "logger.warning" in src
    assert "exc_info=True" in src
