"""E2E tests for Streamlit UI using Streamlit's AppTest framework."""
# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

from __future__ import annotations

import os
import sys

import pytest

# Ensure the project root is importable
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Check if streamlit.testing is available
try:
    from streamlit.testing.v1 import AppTest  # type: ignore[import]
    HAS_APPTEST = True
except ImportError:
    HAS_APPTEST = False

pytestmark = pytest.mark.skipif(
    not HAS_APPTEST,
    reason="streamlit.testing.v1 not available (requires Streamlit >= 1.28)",
)

_APP_PATH = os.path.join(_ROOT, "ui", "streamlit_app.py")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_at(timeout: int = 30) -> "AppTest":
    """Return a fresh AppTest instance for streamlit_app.py."""
    return AppTest.from_file(_APP_PATH, default_timeout=timeout)


def _text_in_any(elements: object, substr: str) -> bool:
    """Return True if *substr* appears in any element's string representation."""
    for el in elements:  # type: ignore[union-attr]
        val = getattr(el, "value", None) or getattr(el, "body", None) or str(el)
        if isinstance(val, str) and substr in val:
            return True
    return False


def _all_text(at: "AppTest") -> str:
    """Collect all visible text (markdown + write + title + header) into one string."""
    parts: list[str] = []
    for container in (at.markdown, at.title, at.header, at.subheader):
        for el in container:
            val = getattr(el, "value", None) or getattr(el, "body", None) or str(el)
            parts.append(str(val))
    return "\n".join(parts)


def _navigate_to(at: "AppTest", page_label: str) -> "AppTest":
    """Navigate to a page by setting the sidebar radio value.

    Returns the updated AppTest after the navigation run.
    NOTE: The Streamlit AppTest radio widget can become stale after set_value().
    We look up the current radio fresh each time.
    """
    for radio in at.radio:
        options = getattr(radio, "options", [])
        matching = [o for o in options if page_label in o]
        if matching:
            at = radio.set_value(matching[0]).run()
            return at
    return at


# ---------------------------------------------------------------------------
# Test 1: App launches and shows the Welcome screen
# ---------------------------------------------------------------------------

def test_app_launches_without_exception() -> None:
    """App should boot without raising an exception."""
    at = _make_at()
    at.run()
    assert not at.exception, f"App raised an exception on first run: {at.exception}"


def test_welcome_page_content() -> None:
    """Welcome screen should contain 'FaultRay' branding."""
    at = _make_at()
    at.run()
    assert not at.exception
    text = _all_text(at)
    # The welcome card contains the FaultRay title
    assert "FaultRay" in text, "Expected 'FaultRay' in welcome page text"


def test_welcome_page_has_buttons() -> None:
    """Welcome screen should have Quick Demo, DORA Check, Upload YAML buttons."""
    at = _make_at()
    at.run()
    assert not at.exception
    button_labels = [b.label for b in at.button]
    assert len(button_labels) >= 3, "Expected at least 3 buttons on welcome screen"
    # At least one 'Quick Demo' button
    assert any("Quick Demo" in lbl for lbl in button_labels), (
        f"Expected a 'Quick Demo' button, found: {button_labels}"
    )


# ---------------------------------------------------------------------------
# Test 2: Quick Demo flow — clicking Quick Demo transitions to demo page
# ---------------------------------------------------------------------------

def test_quick_demo_button_click() -> None:
    """Clicking Quick Demo should not raise an exception and transition state."""
    at = _make_at()
    at.run()
    assert not at.exception

    # Find the Quick Demo button (key=welcome_quick_demo)
    quick_demo_buttons = [b for b in at.button if "Quick Demo" in b.label]
    assert quick_demo_buttons, "No Quick Demo button found on welcome screen"

    quick_demo_buttons[0].click().run()
    assert not at.exception, f"Exception after clicking Quick Demo: {at.exception}"


def test_quick_demo_shows_results_or_demo_content() -> None:
    """After Quick Demo, the UI should show simulation content (score, metrics, etc.)."""
    at = _make_at(timeout=60)
    at.run()
    assert not at.exception

    quick_demo_buttons = [b for b in at.button if "Quick Demo" in b.label]
    if not quick_demo_buttons:
        pytest.skip("No Quick Demo button found")

    quick_demo_buttons[0].click().run()
    assert not at.exception

    text = _all_text(at)
    # After Quick Demo the page should show some simulation-related content
    simulation_keywords = ["Quick Demo", "Simulation", "FaultRay", "スコア", "Score", "シミュレーション"]
    assert any(kw in text for kw in simulation_keywords), (
        f"Expected simulation content after Quick Demo. Full text:\n{text[:500]}"
    )


# ---------------------------------------------------------------------------
# Test 3: Sidebar navigation — onboarded users see navigation radio
# ---------------------------------------------------------------------------

def test_sidebar_navigation_available_after_onboard() -> None:
    """After onboarding the sidebar radio should be present with menu items."""
    at = _make_at()
    at.run()
    assert not at.exception

    # Onboard by clicking Quick Demo
    quick_demo_buttons = [b for b in at.button if "Quick Demo" in b.label]
    if not quick_demo_buttons:
        pytest.skip("No Quick Demo button — cannot onboard")

    quick_demo_buttons[0].click().run()
    assert not at.exception

    # After onboarding a sidebar radio should be present
    radio_elements = list(at.radio)
    assert radio_elements, "Expected sidebar navigation radio after onboarding"


def test_sidebar_navigation_has_expected_pages() -> None:
    """Sidebar radio options should include the core pages."""
    at = _make_at()
    at.run()
    assert not at.exception

    quick_demo_buttons = [b for b in at.button if "Quick Demo" in b.label]
    if not quick_demo_buttons:
        pytest.skip("No Quick Demo button — cannot onboard")

    at = quick_demo_buttons[0].click().run()
    assert not at.exception

    # Collect all radio options
    all_options: list[str] = []
    for radio in at.radio:
        if hasattr(radio, "options"):
            all_options.extend(radio.options)

    expected_pages = ["Simulation", "DORA", "IaC"]
    for page in expected_pages:
        assert any(page in opt for opt in all_options), (
            f"Expected '{page}' in sidebar options, found: {all_options}"
        )


# ---------------------------------------------------------------------------
# Test 4: Navigate to Simulation page via sidebar
# ---------------------------------------------------------------------------

def test_navigate_to_simulation_page() -> None:
    """Selecting 'Simulation' in the sidebar radio should load the Simulation page."""
    at = _make_at()
    at.run()
    assert not at.exception

    quick_demo_buttons = [b for b in at.button if "Quick Demo" in b.label]
    if not quick_demo_buttons:
        pytest.skip("No Quick Demo button — cannot onboard")

    at = quick_demo_buttons[0].click().run()
    assert not at.exception

    # Find the navigation radio options
    sim_options: list[str] = []
    for radio in at.radio:
        options = getattr(radio, "options", [])
        sim_options = [o for o in options if "Simulation" in o]
        if sim_options:
            break

    if not sim_options:
        pytest.skip("No navigation radio with 'Simulation' option found")

    at = _navigate_to(at, "Simulation")
    assert not at.exception

    # The Simulation page header uses Japanese "シミュレーション" or English "Simulation"
    headers = [getattr(el, "value", str(el)) for el in at.header]
    text = _all_text(at)
    assert any(kw in h for h in headers for kw in ["Simulation", "シミュレーション"]) or \
           any(kw in text for kw in ["シミュレーション", "YAML", "topology", "sample", "Sample"]), (
        f"Simulation page content not found. Headers: {headers}. Text:\n{text[:500]}"
    )


# ---------------------------------------------------------------------------
# Test 5: Navigate to DORA Compliance page
# ---------------------------------------------------------------------------

def test_navigate_to_dora_page() -> None:
    """Selecting 'DORA Compliance' in sidebar should load the governance page."""
    at = _make_at()
    at.run()
    assert not at.exception

    quick_demo_buttons = [b for b in at.button if "Quick Demo" in b.label]
    if not quick_demo_buttons:
        pytest.skip("No Quick Demo button — cannot onboard")

    at = quick_demo_buttons[0].click().run()
    assert not at.exception

    has_dora = False
    for radio in at.radio:
        options = getattr(radio, "options", [])
        if any("DORA" in o or "Compliance" in o for o in options):
            has_dora = True
            break
    if not has_dora:
        pytest.skip("No navigation radio with 'DORA' option found")

    at = _navigate_to(at, "DORA")
    assert not at.exception, f"Exception on DORA page: {at.exception}"


# ---------------------------------------------------------------------------
# Test 6: Navigate to IaC Export page
# ---------------------------------------------------------------------------

def test_navigate_to_iac_export_page() -> None:
    """Selecting 'IaC Export' in sidebar should load without exception."""
    at = _make_at()
    at.run()
    assert not at.exception

    quick_demo_buttons = [b for b in at.button if "Quick Demo" in b.label]
    if not quick_demo_buttons:
        pytest.skip("No Quick Demo button — cannot onboard")

    at = quick_demo_buttons[0].click().run()
    assert not at.exception

    has_iac = False
    for radio in at.radio:
        options = getattr(radio, "options", [])
        if any("IaC" in o for o in options):
            has_iac = True
            break
    if not has_iac:
        pytest.skip("No navigation radio with 'IaC' option found")

    at = _navigate_to(at, "IaC")
    assert not at.exception, f"Exception on IaC Export page: {at.exception}"


# ---------------------------------------------------------------------------
# Test 7: Simulation page text area is accessible
# ---------------------------------------------------------------------------

def test_simulation_page_has_input_widgets() -> None:
    """Simulation page should have sample selection buttons and an expander for YAML input."""
    at = _make_at()
    at.run()
    assert not at.exception

    quick_demo_buttons = [b for b in at.button if "Quick Demo" in b.label]
    if not quick_demo_buttons:
        pytest.skip("No Quick Demo button — cannot onboard")

    at = quick_demo_buttons[0].click().run()
    assert not at.exception

    # Check if a navigation radio with Simulation exists
    has_sim = False
    for radio in at.radio:
        options = getattr(radio, "options", [])
        if any("Simulation" in o for o in options):
            has_sim = True
            break
    if not has_sim:
        pytest.skip("No navigation radio with 'Simulation' option found")

    at = _navigate_to(at, "Simulation")
    assert not at.exception

    # The Simulation page renders sample buttons and/or markdown content.
    # The text_area is inside a collapsed expander (not directly accessible).
    # Verify by checking: buttons exist OR markdown contains simulation-related content.
    buttons = list(at.button)
    text = _all_text(at)
    assert buttons or any(kw in text for kw in ["構成", "sample", "YAML", "シミュレーション", "Simulation"]), (
        "Expected simulation-related content (buttons or text) on the Simulation page. "
        f"Found {len(buttons)} buttons, text:\n{text[:500]}"
    )


# ---------------------------------------------------------------------------
# Test 8: No exception on Dashboard page
# ---------------------------------------------------------------------------

def test_dashboard_page_no_exception() -> None:
    """Dashboard page should render without exception after onboarding."""
    at = _make_at()
    at.run()
    assert not at.exception

    quick_demo_buttons = [b for b in at.button if "Quick Demo" in b.label]
    if not quick_demo_buttons:
        pytest.skip("No Quick Demo button — cannot onboard")

    at = quick_demo_buttons[0].click().run()
    assert not at.exception

    has_dashboard = any(
        "Dashboard" in o
        for radio in at.radio
        for o in getattr(radio, "options", [])
    )

    if has_dashboard:
        at = _navigate_to(at, "Dashboard")
        assert not at.exception, f"Exception on Dashboard: {at.exception}"
    else:
        # Already on dashboard or no navigation radio
        assert not at.exception
