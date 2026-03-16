"""Tests for PWA manifest, service worker, and SVG icons."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


STATIC_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "faultray"
    / "api"
    / "static"
)
TEMPLATE_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "faultray"
    / "api"
    / "templates"
)


# ---------------------------------------------------------------------------
# manifest.json
# ---------------------------------------------------------------------------


class TestManifest:
    @pytest.fixture
    def manifest(self) -> dict:
        manifest_path = STATIC_DIR / "manifest.json"
        assert manifest_path.exists(), f"manifest.json not found at {manifest_path}"
        return json.loads(manifest_path.read_text())

    def test_manifest_has_name(self, manifest):
        assert "name" in manifest
        assert len(manifest["name"]) > 0

    def test_manifest_has_short_name(self, manifest):
        assert "short_name" in manifest
        assert len(manifest["short_name"]) > 0

    def test_manifest_has_start_url(self, manifest):
        assert manifest["start_url"] == "/"

    def test_manifest_display_standalone(self, manifest):
        assert manifest["display"] == "standalone"

    def test_manifest_has_theme_color(self, manifest):
        assert "theme_color" in manifest
        assert manifest["theme_color"].startswith("#")

    def test_manifest_has_background_color(self, manifest):
        assert "background_color" in manifest
        assert manifest["background_color"].startswith("#")

    def test_manifest_has_icons(self, manifest):
        assert "icons" in manifest
        icons = manifest["icons"]
        assert len(icons) >= 2

        sizes = {icon["sizes"] for icon in icons}
        assert "192x192" in sizes
        assert "512x512" in sizes

    def test_manifest_icon_types(self, manifest):
        for icon in manifest["icons"]:
            assert "type" in icon
            assert icon["type"] in ("image/svg+xml", "image/png")

    def test_manifest_icon_sources(self, manifest):
        for icon in manifest["icons"]:
            assert "src" in icon
            assert icon["src"].startswith("/static/")

    def test_manifest_has_description(self, manifest):
        assert "description" in manifest
        assert len(manifest["description"]) > 0

    def test_manifest_valid_json(self):
        manifest_path = STATIC_DIR / "manifest.json"
        content = manifest_path.read_text()
        # Should not raise
        parsed = json.loads(content)
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# SVG Icons
# ---------------------------------------------------------------------------


class TestSVGIcons:
    def test_icon_192_exists(self):
        icon_path = STATIC_DIR / "icon-192.svg"
        assert icon_path.exists(), "icon-192.svg not found"

    def test_icon_512_exists(self):
        icon_path = STATIC_DIR / "icon-512.svg"
        assert icon_path.exists(), "icon-512.svg not found"

    def test_icon_192_valid_svg(self):
        icon_path = STATIC_DIR / "icon-192.svg"
        content = icon_path.read_text()
        assert content.strip().startswith("<svg")
        assert "</svg>" in content
        assert 'xmlns="http://www.w3.org/2000/svg"' in content

    def test_icon_512_valid_svg(self):
        icon_path = STATIC_DIR / "icon-512.svg"
        content = icon_path.read_text()
        assert content.strip().startswith("<svg")
        assert "</svg>" in content
        assert 'xmlns="http://www.w3.org/2000/svg"' in content

    def test_icon_192_dimensions(self):
        icon_path = STATIC_DIR / "icon-192.svg"
        content = icon_path.read_text()
        assert 'width="192"' in content
        assert 'height="192"' in content

    def test_icon_512_dimensions(self):
        icon_path = STATIC_DIR / "icon-512.svg"
        content = icon_path.read_text()
        assert 'width="512"' in content
        assert 'height="512"' in content


# ---------------------------------------------------------------------------
# Service Worker
# ---------------------------------------------------------------------------


class TestServiceWorker:
    @pytest.fixture
    def sw_content(self) -> str:
        sw_path = STATIC_DIR / "sw.js"
        assert sw_path.exists(), "sw.js not found"
        return sw_path.read_text()

    def test_cache_name_defined(self, sw_content):
        assert "CACHE_NAME" in sw_content
        assert "faultzero" in sw_content

    def test_install_event(self, sw_content):
        assert "addEventListener('install'" in sw_content or 'addEventListener("install"' in sw_content

    def test_activate_event(self, sw_content):
        assert "addEventListener('activate'" in sw_content or 'addEventListener("activate"' in sw_content

    def test_fetch_event(self, sw_content):
        assert "addEventListener('fetch'" in sw_content or 'addEventListener("fetch"' in sw_content

    def test_skip_waiting(self, sw_content):
        assert "skipWaiting()" in sw_content

    def test_clients_claim(self, sw_content):
        assert "clients.claim()" in sw_content

    def test_api_network_first(self, sw_content):
        assert "/api/" in sw_content

    def test_static_cache_first(self, sw_content):
        assert "/static/" in sw_content

    def test_caches_open(self, sw_content):
        assert "caches.open" in sw_content

    def test_static_assets_list(self, sw_content):
        assert "STATIC_ASSETS" in sw_content
        assert "manifest.json" in sw_content


# ---------------------------------------------------------------------------
# base.html integration
# ---------------------------------------------------------------------------


class TestBaseHTMLIntegration:
    @pytest.fixture
    def base_html(self) -> str:
        base_path = TEMPLATE_DIR / "base.html"
        assert base_path.exists(), "base.html not found"
        return base_path.read_text()

    def test_manifest_link(self, base_html):
        assert 'rel="manifest"' in base_html
        assert "manifest.json" in base_html

    def test_theme_color_meta(self, base_html):
        assert 'name="theme-color"' in base_html

    def test_apple_web_app_capable(self, base_html):
        assert 'name="apple-mobile-web-app-capable"' in base_html

    def test_apple_status_bar_style(self, base_html):
        assert 'name="apple-mobile-web-app-status-bar-style"' in base_html

    def test_apple_touch_icon(self, base_html):
        assert 'rel="apple-touch-icon"' in base_html
        assert "icon-192" in base_html

    def test_service_worker_registration(self, base_html):
        assert "serviceWorker" in base_html
        assert "sw.js" in base_html

    def test_doctype(self, base_html):
        assert "<!DOCTYPE html>" in base_html
