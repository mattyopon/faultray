"""Tests for the per-service DORA evidence pack renderer."""

from __future__ import annotations

import pytest

from faultray.model.demo import create_demo_graph
from faultray.reporter.dora_evidence_pack import (
    build_evidence_pack_markdown,
    evidence_pack_to_print_html,
)
from faultray.simulator.engine import SimulationEngine


def _build(service: str = "postgres", **kwargs) -> str:
    graph = create_demo_graph()
    report = SimulationEngine(graph).run_all_defaults()
    return build_evidence_pack_markdown(graph, report, service, **kwargs)


def test_evidence_pack_substitutes_all_tokens() -> None:
    markdown = _build(
        "postgres",
        institution="Acme Bank EU",
        rto_target="2h",
        rpo_target="15m",
    )
    # No unsubstituted placeholder tokens should remain.
    import re

    leftover = re.findall(r"\{[A-Z_]+\}", markdown)
    assert leftover == [], f"unsubstituted tokens: {leftover}"
    assert "Acme Bank EU" in markdown
    assert "2h" in markdown
    assert "15m" in markdown


def test_evidence_pack_covers_all_required_articles() -> None:
    markdown = _build("postgres")
    for article in ("Article 11", "Article 12", "Article 24", "Article 25", "Article 28", "Article 30"):
        assert article in markdown, f"missing {article}"
    # Honesty / scope language must be present.
    assert "not legal advice" in markdown.lower()
    assert "TLPT" in markdown


def test_evidence_pack_includes_grounded_appendix() -> None:
    markdown = _build("postgres")
    assert "Appendix A" in markdown
    assert "Blast-radius" in markdown
    assert "Fault-injection scenario results" in markdown


def test_evidence_pack_resolves_service_by_name() -> None:
    # Demo component "postgres" has name "PostgreSQL".
    graph = create_demo_graph()
    report = SimulationEngine(graph).run_all_defaults()
    by_name = build_evidence_pack_markdown(graph, report, "PostgreSQL")
    assert "DORA Pre-Audit Resilience Evidence Pack" in by_name


def test_evidence_pack_unknown_service_raises() -> None:
    graph = create_demo_graph()
    report = SimulationEngine(graph).run_all_defaults()
    with pytest.raises(ValueError, match="not found"):
        build_evidence_pack_markdown(graph, report, "does-not-exist-xyz")


def test_print_html_wraps_markdown_safely() -> None:
    html = evidence_pack_to_print_html("# Title\n<script>alert(1)</script>", title="T <x>")
    assert "<!DOCTYPE html>" in html
    # Raw markdown angle brackets must be escaped, not live HTML.
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
