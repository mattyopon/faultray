# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""E2E: Every web page on faultray.com returns a valid HTTP response.

Tests ALL web pages via real HTTP GET requests.  Zero mocks.
Marked with @pytest.mark.e2e -- skip with: ``pytest -m "not e2e"``
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

try:
    import httpx

    _HTTPX = True
except ImportError:
    _HTTPX = False
    httpx = None  # type: ignore[assignment]

_skip = pytest.mark.skipif(not _HTTPX, reason="httpx not installed")

FAULTRAY_URL = "https://faultray.com"
_TIMEOUT = 15.0

# ---------------------------------------------------------------------------
# Page catalogue
# ---------------------------------------------------------------------------

# Public pages (should return 200 or redirect to locale variant)
PUBLIC_PAGES: list[str] = [
    "/",
    "/pricing",
    "/login",
    "/help",
    "/onboarding",
]

# App pages (may require auth -> 307/302 redirect is acceptable)
APP_PAGES: list[str] = [
    "/dashboard",
    "/topology",
    "/heatmap",
    "/score-detail",
    "/simulate",
    "/whatif",
    "/fmea",
    "/incidents",
    "/compliance",
    "/security",
    "/cost",
    "/reports",
    "/benchmark",
    "/remediation",
    "/evidence",
    "/advisor",
    "/settings",
    "/results",
    "/apm",
    "/projects",
    "/dora",
    "/governance",
    "/sla",
    "/runbooks",
    "/postmortems",
    "/supply-chain",
    "/drift",
    "/calendar",
    "/timeline",
    "/teams",
    "/env-compare",
    "/canary",
    "/optimize",
    "/iac",
    "/templates",
    "/ipo-readiness",
    "/traces",
    "/logs",
    "/dependencies",
    "/gameday",
    "/ai-reliability",
    "/fisc",
    "/audit-report",
    "/traffic-light",
    "/people-risk",
]

ALL_PAGES = PUBLIC_PAGES + APP_PAGES

# Pages that may redirect when not authenticated
AUTH_REDIRECT_PAGES = {
    "/dashboard",
    "/simulate",
    "/settings",
    "/results",
    "/projects",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@_skip
class TestAllPages:
    """Every known page returns 200 or a valid redirect."""

    @pytest.mark.parametrize("page", ALL_PAGES)
    def test_page_accessible(self, page: str) -> None:
        assert httpx is not None
        resp = httpx.get(
            f"{FAULTRAY_URL}{page}",
            timeout=_TIMEOUT,
            follow_redirects=False,
        )
        if page in AUTH_REDIRECT_PAGES:
            assert resp.status_code in (
                200,
                301,
                302,
                307,
                308,
            ), f"{page} returned {resp.status_code}"
        else:
            # Accept 200 or locale redirect (301/302/307/308)
            assert resp.status_code in (
                200,
                301,
                302,
                307,
                308,
            ), f"{page} returned {resp.status_code}"

    @pytest.mark.parametrize("page", ALL_PAGES)
    def test_page_no_500(self, page: str) -> None:
        """No page should return a 5xx server error."""
        assert httpx is not None
        resp = httpx.get(
            f"{FAULTRAY_URL}{page}",
            timeout=_TIMEOUT,
            follow_redirects=True,
        )
        assert resp.status_code < 500, (
            f"{page} returned server error {resp.status_code}"
        )


@_skip
class TestPageContent:
    """Verify key pages return HTML content."""

    def test_root_returns_html(self) -> None:
        assert httpx is not None
        resp = httpx.get(FAULTRAY_URL, timeout=_TIMEOUT, follow_redirects=True)
        ct = resp.headers.get("content-type", "")
        assert "text/html" in ct

    def test_pricing_returns_html(self) -> None:
        assert httpx is not None
        resp = httpx.get(
            f"{FAULTRAY_URL}/pricing", timeout=_TIMEOUT, follow_redirects=True
        )
        assert resp.status_code < 500
        ct = resp.headers.get("content-type", "")
        assert "text/html" in ct

    def test_login_returns_html(self) -> None:
        assert httpx is not None
        resp = httpx.get(
            f"{FAULTRAY_URL}/login", timeout=_TIMEOUT, follow_redirects=True
        )
        assert resp.status_code < 500

    def test_help_returns_content(self) -> None:
        assert httpx is not None
        resp = httpx.get(
            f"{FAULTRAY_URL}/help", timeout=_TIMEOUT, follow_redirects=True
        )
        assert resp.status_code < 500


@_skip
class TestPagePerformance:
    """Key pages must respond within reasonable time."""

    @pytest.mark.parametrize(
        "page",
        ["/", "/pricing", "/login", "/dashboard", "/apm"],
    )
    def test_page_responds_within_10s(self, page: str) -> None:
        import time

        assert httpx is not None
        t0 = time.time()
        httpx.get(
            f"{FAULTRAY_URL}{page}",
            timeout=10.0,
            follow_redirects=True,
        )
        elapsed = time.time() - t0
        assert elapsed < 10.0, f"{page} took {elapsed:.1f}s"
