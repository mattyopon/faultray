"""Tests for Resilience Badge Generator."""

from __future__ import annotations

import pytest

from infrasim.api.badge_generator import (
    BadgeGenerator,
    BadgeStyle,
    BadgeType,
    _estimate_text_width,
    _grade_to_color,
    _score_to_color,
    _score_to_grade,
    _spof_to_color,
)
from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _build_healthy_graph() -> InfraGraph:
    """Build a graph with good resilience (high score)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app1", name="App Server 1", type=ComponentType.APP_SERVER,
        replicas=3,
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app1", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app1", target_id="db", dependency_type="requires"))
    return graph


def _build_risky_graph() -> InfraGraph:
    """Build a graph with poor resilience (SPOFs, high utilization)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=95.0),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
        metrics=ResourceMetrics(cpu_percent=88.0),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


# ---------------------------------------------------------------------------
# Tests: Color helpers
# ---------------------------------------------------------------------------

class TestColorHelpers:
    def test_score_to_color_bright_green(self):
        assert _score_to_color(95) == "#4c1"

    def test_score_to_color_green(self):
        assert _score_to_color(85) == "#97ca00"

    def test_score_to_color_yellow(self):
        assert _score_to_color(75) == "#dfb317"

    def test_score_to_color_orange(self):
        assert _score_to_color(65) == "#fe7d37"

    def test_score_to_color_red(self):
        assert _score_to_color(40) == "#e05d44"

    def test_grade_to_color_a(self):
        assert _grade_to_color("A") == "#4c1"
        assert _grade_to_color("A-") == "#4c1"

    def test_grade_to_color_b(self):
        assert _grade_to_color("B+") == "#97ca00"

    def test_grade_to_color_c(self):
        assert _grade_to_color("C") == "#dfb317"

    def test_grade_to_color_d(self):
        assert _grade_to_color("D") == "#fe7d37"

    def test_grade_to_color_f(self):
        assert _grade_to_color("F") == "#e05d44"

    def test_spof_zero(self):
        assert _spof_to_color(0) == "#4c1"

    def test_spof_nonzero(self):
        assert _spof_to_color(3) == "#e05d44"


class TestScoreToGrade:
    def test_a_plus(self):
        assert _score_to_grade(98) == "A+"

    def test_a(self):
        assert _score_to_grade(94) == "A"

    def test_a_minus(self):
        assert _score_to_grade(91) == "A-"

    def test_b(self):
        assert _score_to_grade(84) == "B"

    def test_c(self):
        assert _score_to_grade(74) == "C"

    def test_f(self):
        assert _score_to_grade(50) == "F"


class TestTextWidth:
    def test_short_text(self):
        w = _estimate_text_width("OK")
        assert w > 10

    def test_long_text_wider(self):
        short = _estimate_text_width("A")
        long = _estimate_text_width("Resilience Score")
        assert long > short


# ---------------------------------------------------------------------------
# Tests: BadgeGenerator
# ---------------------------------------------------------------------------

class TestGenerateSVG:
    def test_returns_svg_string(self):
        gen = BadgeGenerator()
        svg = gen.generate_svg(BadgeType.RESILIENCE_SCORE, "85/100", "#4c1")
        assert "<svg" in svg
        assert "Resilience" in svg
        assert "85/100" in svg

    def test_flat_style(self):
        gen = BadgeGenerator()
        svg = gen.generate_svg(BadgeType.GRADE, "A", "#4c1", BadgeStyle.FLAT)
        assert "linearGradient" in svg

    def test_flat_square_style(self):
        gen = BadgeGenerator()
        svg = gen.generate_svg(BadgeType.GRADE, "B", "#97ca00", BadgeStyle.FLAT_SQUARE)
        assert "<svg" in svg
        assert "linearGradient" not in svg  # flat_square has no gradient

    def test_for_the_badge_style(self):
        gen = BadgeGenerator()
        svg = gen.generate_svg(BadgeType.GRADE, "A", "#4c1", BadgeStyle.FOR_THE_BADGE)
        assert 'height="28"' in svg

    def test_plastic_style(self):
        gen = BadgeGenerator()
        svg = gen.generate_svg(BadgeType.SPOF_COUNT, "0", "#4c1", BadgeStyle.PLASTIC)
        assert 'height="18"' in svg

    def test_color_is_embedded(self):
        gen = BadgeGenerator()
        svg = gen.generate_svg(BadgeType.RESILIENCE_SCORE, "50/100", "#e05d44")
        assert "#e05d44" in svg


class TestResilienceBadge:
    def test_healthy_graph(self):
        gen = BadgeGenerator()
        graph = _build_healthy_graph()
        svg = gen.generate_resilience_badge(graph)
        assert "<svg" in svg
        assert "Resilience" in svg

    def test_risky_graph_not_bright_green(self):
        gen = BadgeGenerator()
        graph = _build_risky_graph()
        svg = gen.generate_resilience_badge(graph)
        assert "<svg" in svg
        # Score should be lower than healthy -> not bright green
        assert "#4c1" not in svg


class TestSLABadge:
    def test_sla_badge_content(self):
        gen = BadgeGenerator()
        graph = _build_healthy_graph()
        svg = gen.generate_sla_badge(graph)
        assert "SLA" in svg
        assert "99" in svg  # should contain some 99.x%


class TestGradeBadge:
    def test_grade_badge_content(self):
        gen = BadgeGenerator()
        graph = _build_healthy_graph()
        svg = gen.generate_grade_badge(graph)
        assert "Grade" in svg


class TestSPOFBadge:
    def test_healthy_graph_zero_spof(self):
        gen = BadgeGenerator()
        graph = _build_healthy_graph()
        svg = gen.generate_spof_badge(graph)
        assert "SPOF" in svg
        # All have replicas >= 2 or no dependents -> SPOF = 0
        assert "#4c1" in svg

    def test_risky_graph_has_spof(self):
        gen = BadgeGenerator()
        graph = _build_risky_graph()
        svg = gen.generate_spof_badge(graph)
        assert "SPOF" in svg
        assert "#e05d44" in svg  # SPOF > 0 -> red


class TestAllBadges:
    def test_returns_dict(self):
        gen = BadgeGenerator()
        graph = _build_healthy_graph()
        badges = gen.generate_all_badges(graph)
        assert isinstance(badges, dict)
        assert BadgeType.RESILIENCE_SCORE.value in badges
        assert BadgeType.SLA_ESTIMATE.value in badges
        assert BadgeType.GRADE.value in badges
        assert BadgeType.SPOF_COUNT.value in badges
        assert BadgeType.COMPONENT_COUNT.value in badges

    def test_all_are_svg(self):
        gen = BadgeGenerator()
        graph = _build_healthy_graph()
        badges = gen.generate_all_badges(graph)
        for name, svg in badges.items():
            assert "<svg" in svg, f"Badge '{name}' is not valid SVG"


class TestMarkdownLinks:
    def test_contains_image_links(self):
        gen = BadgeGenerator()
        md = gen.get_markdown_links("http://localhost:8000")
        assert "![Resilience Score]" in md
        assert "![SLA Estimate]" in md
        assert "![Grade]" in md
        assert "![SPOF Count]" in md
        assert "http://localhost:8000/badge/" in md

    def test_strips_trailing_slash(self):
        gen = BadgeGenerator()
        md = gen.get_markdown_links("http://example.com/")
        assert "http://example.com/badge/" in md
        assert "http://example.com//badge/" not in md
