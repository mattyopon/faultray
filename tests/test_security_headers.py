"""Regression tests for security response headers and CDN SRI pinning."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from faultray.api.server import app

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "faultray" / "api" / "templates"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_security_headers_present(client: TestClient) -> None:
    r = client.get("/")
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    csp = r.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp


def test_csp_allowlists_used_cdns_only(client: TestClient) -> None:
    csp = client.get("/").headers.get("Content-Security-Policy", "")
    assert "https://unpkg.com" in csp
    assert "https://cdn.jsdelivr.net" in csp
    # d3 was moved to jsdelivr; d3js.org must no longer be trusted.
    assert "d3js.org" not in csp


def test_headers_on_api_responses(client: TestClient) -> None:
    # Headers must be applied to API/JSON responses too, not just HTML pages.
    r = client.get("/api/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Content-Security-Policy" in r.headers


@pytest.mark.parametrize("name", ["base.html", "graph.html", "blast_radius.html",
                                   "advisor.html", "topology_diff.html"])
def test_cdn_scripts_have_sri(name: str) -> None:
    """Every external CDN <script> must carry integrity + crossorigin (no
    un-pinned remote code)."""
    html = (TEMPLATES / name).read_text(encoding="utf-8")
    # Find external script tags (with a remote src).
    for tag in re.findall(r"<script\b[^>]*\bsrc=\"https?://[^>]*?>", html, flags=re.S):
        assert "integrity=\"sha384-" in tag, f"{name}: missing SRI integrity in {tag[:80]}"
        assert "crossorigin=" in tag, f"{name}: missing crossorigin in {tag[:80]}"


def test_no_unpinned_floating_cdn_versions() -> None:
    """Guard against mutable version ranges (e.g. mermaid@10) that would make
    SRI drift and break."""
    for name in ["base.html", "graph.html", "blast_radius.html", "advisor.html",
                 "topology_diff.html"]:
        html = (TEMPLATES / name).read_text(encoding="utf-8")
        # mermaid@10 / d3@7 (no patch) would be floating; require an exact x.y.z.
        assert "mermaid@10/" not in html, f"{name}: mermaid pinned to a floating major"
        assert "d3js.org/d3.v7" not in html, f"{name}: d3 served from a floating URL"
