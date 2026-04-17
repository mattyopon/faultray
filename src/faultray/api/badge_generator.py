# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Resilience Badge Generator.

Generate embeddable SVG badges showing resilience scores, similar to
CI/CD status badges or code coverage badges.

Formats:
- SVG badge (shields.io style)
- HTML widget (embeddable iframe)
- JSON endpoint (for custom integrations)
- Markdown badge link

Example badges:
  [Resilience: 85/100] (green)
  [SLA: 99.95%] (yellow)
  [SPOF: 0] (green)
  [Grade: A-] (green)
"""

from __future__ import annotations

import logging
from enum import Enum

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


class BadgeStyle(str, Enum):
    """Visual style for SVG badges."""

    FLAT = "flat"
    FLAT_SQUARE = "flat_square"
    FOR_THE_BADGE = "for_the_badge"
    PLASTIC = "plastic"


class BadgeType(str, Enum):
    """Type of metric shown on the badge."""

    RESILIENCE_SCORE = "resilience_score"
    SLA_ESTIMATE = "sla_estimate"
    SPOF_COUNT = "spof_count"
    GRADE = "grade"
    CRITICAL_COUNT = "critical_count"
    COMPONENT_COUNT = "component_count"


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _score_to_color(score: float) -> str:
    """Map a 0-100 resilience score to a badge color hex."""
    if score >= 90:
        return "#4c1"
    if score >= 80:
        return "#97ca00"
    if score >= 70:
        return "#dfb317"
    if score >= 60:
        return "#fe7d37"
    return "#e05d44"


def _grade_to_color(grade: str) -> str:
    """Map a letter grade to a badge color hex."""
    g = grade.upper().rstrip("+-")
    if g == "A":
        return "#4c1"
    if g == "B":
        return "#97ca00"
    if g == "C":
        return "#dfb317"
    if g == "D":
        return "#fe7d37"
    return "#e05d44"


def _spof_to_color(count: int) -> str:
    """Map SPOF count to a badge color hex."""
    return "#4c1" if count == 0 else "#e05d44"


def _score_to_grade(score: float) -> str:
    """Convert a 0-100 resilience score to a letter grade."""
    if score >= 97:
        return "A+"
    if score >= 93:
        return "A"
    if score >= 90:
        return "A-"
    if score >= 87:
        return "B+"
    if score >= 83:
        return "B"
    if score >= 80:
        return "B-"
    if score >= 77:
        return "C+"
    if score >= 73:
        return "C"
    if score >= 70:
        return "C-"
    if score >= 67:
        return "D+"
    if score >= 63:
        return "D"
    if score >= 60:
        return "D-"
    return "F"


def _estimate_text_width(text: str) -> int:
    """Rough estimate of text width in pixels for SVG rendering.

    Uses average character width of ~6.5px for 11px DejaVu Sans.
    """
    return int(len(text) * 6.5) + 10


# ---------------------------------------------------------------------------
# SVG templates
# ---------------------------------------------------------------------------

_SVG_FLAT = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20">
  <linearGradient id="smooth" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="round">
    <rect width="{width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#round)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{width}" height="20" fill="url(#smooth)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_x}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_x}" y="14">{label}</text>
    <text x="{value_x}" y="15" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{value_x}" y="14">{value}</text>
  </g>
</svg>"""

_SVG_FLAT_SQUARE = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20">
  <g>
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_x}" y="14">{label}</text>
    <text x="{value_x}" y="14">{value}</text>
  </g>
</svg>"""

_SVG_FOR_THE_BADGE = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="28">
  <g>
    <rect width="{label_width}" height="28" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="28" fill="{color}"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="10" font-weight="bold" text-transform="uppercase" letter-spacing="1">
    <text x="{label_x}" y="18">{label_upper}</text>
    <text x="{value_x}" y="18">{value_upper}</text>
  </g>
</svg>"""

_SVG_PLASTIC = """\
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="18">
  <linearGradient id="smooth" x2="0" y2="100%">
    <stop offset="0" stop-color="#fff" stop-opacity=".7"/>
    <stop offset=".1" stop-color="#aaa" stop-opacity=".1"/>
    <stop offset=".9" stop-color="#000" stop-opacity=".3"/>
    <stop offset="1" stop-color="#000" stop-opacity=".5"/>
  </linearGradient>
  <clipPath id="round">
    <rect width="{width}" height="18" rx="4" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#round)">
    <rect width="{label_width}" height="18" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="18" fill="{color}"/>
    <rect width="{width}" height="18" fill="url(#smooth)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_x}" y="13" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_x}" y="12">{label}</text>
    <text x="{value_x}" y="13" fill="#010101" fill-opacity=".3">{value}</text>
    <text x="{value_x}" y="12">{value}</text>
  </g>
</svg>"""


_STYLE_TEMPLATES = {
    BadgeStyle.FLAT: _SVG_FLAT,
    BadgeStyle.FLAT_SQUARE: _SVG_FLAT_SQUARE,
    BadgeStyle.FOR_THE_BADGE: _SVG_FOR_THE_BADGE,
    BadgeStyle.PLASTIC: _SVG_PLASTIC,
}


# ---------------------------------------------------------------------------
# BadgeGenerator
# ---------------------------------------------------------------------------

class BadgeGenerator:
    """Generate embeddable SVG badges for infrastructure resilience metrics."""

    def generate_svg(
        self,
        badge_type: BadgeType,
        value: str,
        color: str,
        style: BadgeStyle = BadgeStyle.FLAT,
    ) -> str:
        """Generate a shields.io-style SVG badge.

        Args:
            badge_type: The type of badge (used to derive the label).
            value: Display value on the right side of the badge.
            color: Hex color for the value section (e.g. "#4c1").
            style: Visual style of the badge.

        Returns:
            SVG string.
        """
        label = self._badge_label(badge_type)
        return self._render_svg(label, value, color, style)

    def generate_resilience_badge(
        self,
        graph: InfraGraph,
        style: BadgeStyle = BadgeStyle.FLAT,
    ) -> str:
        """Generate a resilience score badge from an InfraGraph."""
        score = round(graph.resilience_score(), 1)
        color = _score_to_color(score)
        return self._render_svg("Resilience", f"{score}/100", color, style)

    def generate_sla_badge(
        self,
        graph: InfraGraph,
        style: BadgeStyle = BadgeStyle.FLAT,
    ) -> str:
        """Generate an SLA estimate badge from an InfraGraph."""
        score = graph.resilience_score()
        # Map score to approximate SLA percentage
        if score >= 95:
            sla = "99.99%"
        elif score >= 90:
            sla = "99.95%"
        elif score >= 80:
            sla = "99.9%"
        elif score >= 70:
            sla = "99.5%"
        elif score >= 60:
            sla = "99%"
        else:
            sla = "<99%"
        color = _score_to_color(score)
        return self._render_svg("SLA", sla, color, style)

    def generate_grade_badge(
        self,
        graph: InfraGraph,
        style: BadgeStyle = BadgeStyle.FLAT,
    ) -> str:
        """Generate a letter-grade badge from an InfraGraph."""
        score = graph.resilience_score()
        grade = _score_to_grade(score)
        color = _grade_to_color(grade)
        return self._render_svg("Grade", grade, color, style)

    def generate_spof_badge(
        self,
        graph: InfraGraph,
        style: BadgeStyle = BadgeStyle.FLAT,
    ) -> str:
        """Generate a SPOF count badge from an InfraGraph."""
        spof_count = 0
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                spof_count += 1
        color = _spof_to_color(spof_count)
        return self._render_svg("SPOF", str(spof_count), color, style)

    def generate_all_badges(
        self,
        graph: InfraGraph,
        style: BadgeStyle = BadgeStyle.FLAT,
    ) -> dict[str, str]:
        """Generate all available badges for a graph.

        Returns:
            Dict mapping badge type name to SVG string.
        """
        return {
            BadgeType.RESILIENCE_SCORE.value: self.generate_resilience_badge(graph, style),
            BadgeType.SLA_ESTIMATE.value: self.generate_sla_badge(graph, style),
            BadgeType.GRADE.value: self.generate_grade_badge(graph, style),
            BadgeType.SPOF_COUNT.value: self.generate_spof_badge(graph, style),
            BadgeType.COMPONENT_COUNT.value: self._generate_component_count_badge(graph, style),
        }

    def get_markdown_links(self, base_url: str) -> str:
        """Return markdown snippet to embed all badges in a README.

        Args:
            base_url: The base URL of the FaultRay instance.

        Returns:
            Markdown string with badge image links.
        """
        base = base_url.rstrip("/")
        lines = [
            f"![Resilience Score]({base}/badge/resilience_score.svg)",
            f"![SLA Estimate]({base}/badge/sla_estimate.svg)",
            f"![Grade]({base}/badge/grade.svg)",
            f"![SPOF Count]({base}/badge/spof_count.svg)",
            f"![Components]({base}/badge/component_count.svg)",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_component_count_badge(
        self,
        graph: InfraGraph,
        style: BadgeStyle = BadgeStyle.FLAT,
    ) -> str:
        """Generate a component count badge."""
        count = len(graph.components)
        return self._render_svg("Components", str(count), "#007ec6", style)

    @staticmethod
    def _badge_label(badge_type: BadgeType) -> str:
        """Map badge type to a human-readable label."""
        labels = {
            BadgeType.RESILIENCE_SCORE: "Resilience",
            BadgeType.SLA_ESTIMATE: "SLA",
            BadgeType.SPOF_COUNT: "SPOF",
            BadgeType.GRADE: "Grade",
            BadgeType.CRITICAL_COUNT: "Critical",
            BadgeType.COMPONENT_COUNT: "Components",
        }
        return labels.get(badge_type, badge_type.value)

    @staticmethod
    def _render_svg(
        label: str,
        value: str,
        color: str,
        style: BadgeStyle = BadgeStyle.FLAT,
    ) -> str:
        """Render an SVG badge from label, value, color, and style."""
        label_width = _estimate_text_width(label)
        value_width = _estimate_text_width(value)
        width = label_width + value_width

        template = _STYLE_TEMPLATES.get(style, _SVG_FLAT)

        return template.format(
            width=width,
            label_width=label_width,
            value_width=value_width,
            label_x=label_width / 2,
            value_x=label_width + value_width / 2,
            label=label,
            value=value,
            color=color,
            label_upper=label.upper(),
            value_upper=value.upper(),
        )
