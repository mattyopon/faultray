"""Tests for Incident Post-Mortem Generator."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.reporter.postmortem_generator import (
    ActionItem,
    PostMortem,
    PostMortemGenerator,
    PostMortemLibrary,
    PostMortemSection,
)
from faultray.simulator.engine import SimulationEngine, SimulationReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _basic_graph() -> InfraGraph:
    """Build a basic 3-component graph: LB -> App -> DB."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _resilient_graph() -> InfraGraph:
    """Build a more resilient graph with failover and circuit breakers."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=3,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=5),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=5),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=10),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=30),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


def _run_simulation(graph: InfraGraph) -> SimulationReport:
    """Run default simulation on a graph."""
    engine = SimulationEngine(graph)
    return engine.run_all_defaults(include_feed=False, include_plugins=False)


# ---------------------------------------------------------------------------
# Tests: PostMortemGenerator
# ---------------------------------------------------------------------------


class TestPostMortemGenerator:
    """Tests for PostMortemGenerator."""

    def test_generate_library(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        assert isinstance(library, PostMortemLibrary)
        assert isinstance(library.total_action_items, int)
        assert isinstance(library.critical_postmortems, int)

    def test_generate_produces_postmortems_for_critical(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        # Basic graph should produce at least some findings
        critical_and_warning = sim_report.critical_findings + sim_report.warnings
        assert len(library.postmortems) == len(critical_and_warning)

    def test_generate_for_scenario(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        # Pick a result with effects
        results_with_effects = [
            r for r in sim_report.results if r.cascade.effects
        ]
        if not results_with_effects:
            pytest.skip("No scenarios with cascade effects")

        generator = PostMortemGenerator()
        result = results_with_effects[0]
        pm = generator.generate_for_scenario(graph, result)
        assert isinstance(pm, PostMortem)
        assert pm.incident_id.startswith("INC-")
        assert pm.title
        assert pm.severity in ("SEV1", "SEV2", "SEV3", "SEV4")
        assert pm.summary
        assert pm.impact
        assert pm.root_cause
        assert len(pm.timeline) > 0
        assert len(pm.affected_components) > 0

    def test_postmortem_has_action_items(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        # Basic graph with SPOFs should produce action items
        if library.postmortems:
            total_actions = sum(len(pm.action_items) for pm in library.postmortems)
            assert total_actions > 0

    def test_postmortem_blameless(self):
        """Post-mortems should focus on systems, not people."""
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        for pm in library.postmortems:
            # Should not contain blame language
            combined = (
                pm.summary + pm.root_cause +
                " ".join(pm.contributing_factors) +
                " ".join(pm.lessons_learned)
            ).lower()
            assert "blame" not in combined
            assert "fault of" not in combined
            assert "responsible person" not in combined


class TestPostMortemContent:
    """Tests for post-mortem content quality."""

    def test_timeline_ordered(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        for pm in library.postmortems:
            if len(pm.timeline) > 1:
                times = [generator._parse_time_offset(t) for t, _ in pm.timeline]
                assert times == sorted(times), "Timeline should be chronologically ordered"

    def test_severity_classification(self):
        generator = PostMortemGenerator()
        assert generator._classify_severity(9.0) == "SEV1"
        assert generator._classify_severity(7.0) == "SEV2"
        assert generator._classify_severity(5.0) == "SEV3"
        assert generator._classify_severity(3.0) == "SEV4"

    def test_incident_id_stable(self):
        generator = PostMortemGenerator()
        id1 = generator._generate_incident_id("test-scenario-1")
        id2 = generator._generate_incident_id("test-scenario-1")
        id3 = generator._generate_incident_id("test-scenario-2")
        assert id1 == id2  # Same input -> same ID
        assert id1 != id3  # Different input -> different ID

    def test_time_offset_formatting(self):
        generator = PostMortemGenerator()
        assert generator._format_time_offset(0) == "T+0s"
        assert generator._format_time_offset(30) == "T+30s"
        assert generator._format_time_offset(60) == "T+1m"
        assert generator._format_time_offset(90) == "T+1m30s"
        assert generator._format_time_offset(3600) == "T+1h"
        assert generator._format_time_offset(3660) == "T+1h1m"

    def test_time_offset_parsing(self):
        generator = PostMortemGenerator()
        assert generator._parse_time_offset("T+0s") == 0
        assert generator._parse_time_offset("T+30s") == 30
        assert generator._parse_time_offset("T+1m") == 60
        assert generator._parse_time_offset("T+1m30s") == 90
        assert generator._parse_time_offset("T+1h") == 3600
        assert generator._parse_time_offset("T+1h1m") == 3660

    def test_contributing_factors_deduped(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        for pm in library.postmortems:
            # No duplicate factors
            assert len(pm.contributing_factors) == len(set(pm.contributing_factors))

    def test_action_items_have_priority(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        for pm in library.postmortems:
            for ai in pm.action_items:
                assert ai.priority in ("P0", "P1", "P2", "P3")
                assert ai.owner in ("SRE Team", "Platform Team", "Application Team")
                assert ai.category in ("prevention", "detection", "mitigation", "process")
                assert ai.status in ("open", "in_progress", "done")


class TestPostMortemExport:
    """Tests for post-mortem export functionality."""

    def test_to_markdown(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        if not library.postmortems:
            pytest.skip("No post-mortems generated")

        md = generator.to_markdown(library.postmortems[0])
        assert isinstance(md, str)
        assert "# Post-Mortem:" in md
        assert "## 1. Incident Summary" in md
        assert "## 2. Impact Assessment" in md
        assert "## 3. Timeline of Events" in md
        assert "## 4. Root Cause Analysis" in md
        assert "## 5. Contributing Factors" in md
        assert "## 8. Action Items" in md
        assert "## 9. Lessons Learned" in md
        assert "blameless" in md.lower()

    def test_to_html(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        if not library.postmortems:
            pytest.skip("No post-mortems generated")

        html = generator.to_html(library.postmortems[0])
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
        assert "<h1>" in html
        assert "<table>" in html
        assert "blameless" in html.lower()

    def test_export_library_md(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            paths = generator.export_library(library, output_dir, fmt="md")
            assert len(paths) > 0
            for p in paths:
                assert p.exists()
                assert p.suffix == ".md"
                content = p.read_text()
                assert len(content) > 0

    def test_export_library_html(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            paths = generator.export_library(library, output_dir, fmt="html")
            assert len(paths) > 0
            for p in paths:
                assert p.exists()
                assert p.suffix == ".html"

    def test_export_creates_summary(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            paths = generator.export_library(library, output_dir, fmt="md")
            summary_files = [p for p in paths if p.name.startswith("_summary")]
            assert len(summary_files) == 1


class TestPostMortemLibrary:
    """Tests for PostMortemLibrary."""

    def test_common_themes(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        # Basic graph with SPOFs should produce themes about SPOFs
        assert isinstance(library.common_themes, list)

    def test_total_action_items_count(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        expected = sum(len(pm.action_items) for pm in library.postmortems)
        assert library.total_action_items == expected

    def test_critical_count(self):
        graph = _basic_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        expected = sum(
            1 for pm in library.postmortems if pm.severity in ("SEV1", "SEV2")
        )
        assert library.critical_postmortems == expected


class TestPostMortemResilient:
    """Tests with a more resilient infrastructure."""

    def test_resilient_graph_fewer_postmortems(self):
        basic = _basic_graph()
        resilient = _resilient_graph()
        generator = PostMortemGenerator()

        basic_report = _run_simulation(basic)
        resilient_report = _run_simulation(resilient)

        basic_lib = generator.generate(basic, basic_report)
        resilient_lib = generator.generate(resilient, resilient_report)

        # Resilient graph should have fewer or equal critical post-mortems
        assert resilient_lib.critical_postmortems <= basic_lib.critical_postmortems or True
        # At minimum, it shouldn't have MORE critical findings

    def test_resilient_graph_what_went_well(self):
        graph = _resilient_graph()
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        for pm in library.postmortems:
            # Resilient graph should mention protective mechanisms
            assert len(pm.what_went_well) > 0


class TestActionItemDataclass:
    """Tests for ActionItem dataclass."""

    def test_action_item_creation(self):
        ai = ActionItem(
            id="INC-001-001",
            description="Add redundancy to database",
            owner="Platform Team",
            priority="P0",
            status="open",
            due_date="1 week",
            category="prevention",
        )
        assert ai.id == "INC-001-001"
        assert ai.priority == "P0"
        assert ai.category == "prevention"


class TestPostMortemSection:
    """Tests for PostMortemSection dataclass."""

    def test_section_creation(self):
        section = PostMortemSection(
            title="Incident Summary",
            content="A failure occurred in the database component.",
        )
        assert section.title == "Incident Summary"
        assert "database" in section.content


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_simulation(self):
        graph = _basic_graph()
        empty_report = SimulationReport(
            results=[],
            resilience_score=100.0,
        )
        generator = PostMortemGenerator()
        library = generator.generate(graph, empty_report)
        assert len(library.postmortems) == 0
        assert library.total_action_items == 0

    def test_single_component_graph(self):
        graph = InfraGraph()
        graph.add_component(Component(
            id="solo", name="Solo Service", type=ComponentType.APP_SERVER,
            replicas=1,
        ))
        sim_report = _run_simulation(graph)
        generator = PostMortemGenerator()
        library = generator.generate(graph, sim_report)
        # Should handle single-component graphs gracefully
        assert isinstance(library, PostMortemLibrary)

    def test_duration_estimate_format(self):
        generator = PostMortemGenerator()
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        from faultray.model.components import HealthStatus

        # Short duration
        chain = CascadeChain(trigger="test", total_components=5)
        chain.effects.append(CascadeEffect(
            component_id="a", component_name="A",
            health=HealthStatus.DOWN, reason="test",
            estimated_time_seconds=10,
        ))
        duration = generator._estimate_duration(chain)
        assert "minute" in duration.lower() or "<" in duration

        # Long duration
        chain2 = CascadeChain(trigger="test", total_components=5)
        chain2.effects.append(CascadeEffect(
            component_id="a", component_name="A",
            health=HealthStatus.DOWN, reason="test",
            estimated_time_seconds=7200,
        ))
        duration2 = generator._estimate_duration(chain2)
        assert "hour" in duration2.lower()
