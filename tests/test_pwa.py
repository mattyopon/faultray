"""Tests for PWA support, responsive design, and accessibility.

Verifies that the manifest.json, service worker, and viewport meta tag exist,
and that templates include proper ARIA attributes for accessibility.
"""

from __future__ import annotations

import json
from pathlib import Path


# Base paths
STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "infrasim" / "api" / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "infrasim" / "api" / "templates"


class TestPWASupport:
    """Verify PWA assets exist and are properly configured."""

    def test_manifest_exists_and_valid(self):
        """manifest.json should exist with required PWA fields."""
        manifest_path = STATIC_DIR / "manifest.json"
        assert manifest_path.exists(), f"manifest.json not found at {manifest_path}"

        data = json.loads(manifest_path.read_text())
        assert "name" in data
        assert "short_name" in data
        assert data["start_url"] == "/"
        assert data["display"] == "standalone"
        assert "background_color" in data
        assert "theme_color" in data
        assert "icons" in data
        assert len(data["icons"]) >= 2
        # Verify icon entries have required fields
        for icon in data["icons"]:
            assert "src" in icon
            assert "sizes" in icon
            assert "type" in icon

    def test_service_worker_exists(self):
        """sw.js should exist with fetch event listener."""
        sw_path = STATIC_DIR / "sw.js"
        assert sw_path.exists(), f"Service worker not found at {sw_path}"

        content = sw_path.read_text()
        assert "CACHE_NAME" in content, "Service worker should define CACHE_NAME"
        assert "addEventListener" in content, "Service worker should have event listeners"
        assert "'fetch'" in content, "Service worker should handle fetch events"
        assert "'install'" in content, "Service worker should handle install events"
        assert "'activate'" in content, "Service worker should handle activate events"

    def test_viewport_meta_tag_in_base_template(self):
        """base.html should contain viewport meta tag for responsive design."""
        base_path = TEMPLATES_DIR / "base.html"
        assert base_path.exists(), f"base.html not found at {base_path}"

        content = base_path.read_text()
        assert 'name="viewport"' in content, "base.html should have viewport meta tag"
        assert "width=device-width" in content, "Viewport should include width=device-width"
        assert "initial-scale=1.0" in content, "Viewport should include initial-scale=1.0"


class TestResponsiveDesign:
    """Verify responsive CSS rules exist."""

    def test_mobile_breakpoint_css(self):
        """style.css should have 768px and 480px breakpoints."""
        css_path = STATIC_DIR / "style.css"
        assert css_path.exists(), f"style.css not found at {css_path}"

        content = css_path.read_text()
        assert "@media (max-width: 768px)" in content, "Should have 768px breakpoint"
        assert "@media (max-width: 480px)" in content, "Should have 480px breakpoint"

    def test_manifest_linked_in_base(self):
        """base.html should link to manifest.json."""
        base_path = TEMPLATES_DIR / "base.html"
        content = base_path.read_text()
        assert 'rel="manifest"' in content, "base.html should link manifest.json"
        assert "manifest.json" in content

    def test_service_worker_registered_in_base(self):
        """base.html should register the service worker."""
        base_path = TEMPLATES_DIR / "base.html"
        content = base_path.read_text()
        assert "serviceWorker" in content, "base.html should register service worker"
        assert "sw.js" in content, "Should reference sw.js"


class TestAccessibility:
    """Verify ARIA attributes and accessibility compliance."""

    def test_base_template_has_lang_attribute(self):
        """HTML tag should have lang='en'."""
        base_path = TEMPLATES_DIR / "base.html"
        content = base_path.read_text()
        assert 'lang="en"' in content, "HTML tag should have lang='en'"

    def test_navigation_has_role(self):
        """Sidebar nav should have role='navigation'."""
        base_path = TEMPLATES_DIR / "base.html"
        content = base_path.read_text()
        assert 'role="navigation"' in content, "Nav element should have role='navigation'"

    def test_main_has_role(self):
        """Main content area should have role='main'."""
        base_path = TEMPLATES_DIR / "base.html"
        content = base_path.read_text()
        assert 'role="main"' in content, "Main element should have role='main'"

    def test_components_table_has_role(self):
        """Data table in components.html should have role='table'."""
        comp_path = TEMPLATES_DIR / "components.html"
        content = comp_path.read_text()
        assert 'role="table"' in content, "Table should have role='table'"

    def test_interactive_elements_have_aria_labels(self):
        """Buttons and interactive elements should have aria-label attributes."""
        templates = ["base.html", "dashboard.html", "simulation.html", "analyze.html", "graph.html"]
        for template_name in templates:
            path = TEMPLATES_DIR / template_name
            content = path.read_text()
            assert "aria-label" in content, (
                f"{template_name} should have aria-label on interactive elements"
            )

    def test_table_headers_have_scope(self):
        """Table headers in components.html should have scope='col'."""
        comp_path = TEMPLATES_DIR / "components.html"
        content = comp_path.read_text()
        assert 'scope="col"' in content, "Table headers should have scope='col'"

    def test_color_contrast_css_variables(self):
        """CSS should define high-contrast color variables for WCAG AA compliance.

        The dark theme uses light text on dark backgrounds.
        Verifies that key color variables are defined.
        """
        css_path = STATIC_DIR / "style.css"
        content = css_path.read_text()
        # Primary text (#e2e8f0) on dark bg (#0b0e17) has >15:1 ratio (passes AAA)
        assert "--text-primary: #e2e8f0" in content, "Should define primary text color"
        assert "--bg-dark: #0b0e17" in content, "Should define dark background"
        # Secondary text (#94a3b8) on dark bg has >7:1 ratio (passes AA)
        assert "--text-secondary: #94a3b8" in content, "Should define secondary text color"
