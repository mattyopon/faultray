"""Tests for shared theme constants."""

import pytest

from faultray.theme import (
    HEALTH_COLORS,
    SCORE_COLORS,
    SEVERITY_COLORS,
    score_to_color,
    severity_to_color,
)


class TestSeverityColors:
    """Verify severity color lookups."""

    def test_all_severity_levels_present(self):
        expected = {"critical", "high", "medium", "low", "info"}
        assert set(SEVERITY_COLORS.keys()) == expected

    def test_critical_is_red(self):
        assert SEVERITY_COLORS["critical"] == "#dc3545"

    def test_low_is_green(self):
        assert SEVERITY_COLORS["low"] == "#28a745"


class TestHealthColors:
    """Verify health color lookups."""

    def test_all_health_statuses_present(self):
        expected = {"healthy", "degraded", "overloaded", "down"}
        assert set(HEALTH_COLORS.keys()) == expected

    def test_healthy_is_green(self):
        assert HEALTH_COLORS["healthy"] == "#28a745"

    def test_down_is_red(self):
        assert HEALTH_COLORS["down"] == "#dc3545"


class TestScoreToColor:
    """Verify score_to_color returns correct color bands."""

    @pytest.mark.parametrize(
        "score,expected_key",
        [
            (100.0, "excellent"),
            (80.0, "excellent"),
            (79.9, "good"),
            (60.0, "good"),
            (59.9, "fair"),
            (40.0, "fair"),
            (39.9, "poor"),
            (20.0, "poor"),
            (19.9, "critical"),
            (0.0, "critical"),
        ],
    )
    def test_score_bands(self, score, expected_key):
        assert score_to_color(score) == SCORE_COLORS[expected_key]

    def test_negative_score(self):
        # Negative scores should map to critical
        assert score_to_color(-10.0) == SCORE_COLORS["critical"]

    def test_above_100_score(self):
        # Scores above 100 should map to excellent
        assert score_to_color(150.0) == SCORE_COLORS["excellent"]


class TestSeverityToColor:
    """Verify severity_to_color with case-insensitive lookup."""

    def test_lowercase(self):
        assert severity_to_color("critical") == "#dc3545"

    def test_uppercase(self):
        assert severity_to_color("CRITICAL") == "#dc3545"

    def test_mixed_case(self):
        assert severity_to_color("High") == "#fd7e14"

    def test_unknown_returns_default(self):
        assert severity_to_color("unknown") == "#8b949e"

    def test_empty_string_returns_default(self):
        assert severity_to_color("") == "#8b949e"
