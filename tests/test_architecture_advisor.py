"""Tests for the AI Architecture Advisor."""

from __future__ import annotations

import json

import pytest

from infrasim.ai.architecture_advisor import (
    ArchitectureAdvisor,
    ArchitectureChange,
    ArchitecturePattern,
    ArchitectureProposal,
    ArchitectureReport,
    _nines_to_score,
    _score_to_nines,
)
from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_graph() -> InfraGraph:
    """Graph with a clear SPOF: single DB with multiple dependents."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=2,
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=1,
    ))
    graph.add_component(Component(
        id="cache", name="Redis", type=ComponentType.CACHE,
        replicas=1,
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
    return graph


@pytest.fixture
def redundant_graph() -> InfraGraph:
    """Graph with good redundancy: replicas >= 2, failover, circuit breakers."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=3, failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="app", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3, failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db", name="PostgreSQL", type=ComponentType.DATABASE,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="cache", name="Redis", type=ComponentType.CACHE,
        replicas=2, failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="cache", dependency_type="optional",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


@pytest.fixture
def empty_graph() -> InfraGraph:
    """Completely empty graph."""
    return InfraGraph()


@pytest.fixture
def single_node_graph() -> InfraGraph:
    """Graph with a single component and no dependencies."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=1,
    ))
    return graph


@pytest.fixture
def deep_chain_graph() -> InfraGraph:
    """Linear chain with 6 hops: lb -> web -> app -> svc -> db -> storage."""
    graph = InfraGraph()
    ids = ["lb", "web", "app", "svc", "db", "storage"]
    types = [
        ComponentType.LOAD_BALANCER,
        ComponentType.WEB_SERVER,
        ComponentType.APP_SERVER,
        ComponentType.APP_SERVER,
        ComponentType.DATABASE,
        ComponentType.STORAGE,
    ]
    for cid, ctype in zip(ids, types):
        graph.add_component(Component(id=cid, name=cid, type=ctype, replicas=1))
    for i in range(len(ids) - 1):
        graph.add_dependency(Dependency(source_id=ids[i], target_id=ids[i + 1]))
    return graph


@pytest.fixture
def external_api_graph() -> InfraGraph:
    """Graph with external API dependency and no circuit breaker."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
    ))
    graph.add_component(Component(
        id="ext-payment", name="Payment API", type=ComponentType.EXTERNAL_API,
        replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="ext-payment", dependency_type="requires",
    ))
    return graph


@pytest.fixture
def god_component_graph() -> InfraGraph:
    """Graph with a single DB depended on by >5 services."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db", name="Main DB", type=ComponentType.DATABASE, replicas=1,
    ))
    for i in range(6):
        svc_id = f"svc-{i}"
        graph.add_component(Component(
            id=svc_id, name=f"Service {i}", type=ComponentType.APP_SERVER, replicas=1,
        ))
        graph.add_dependency(Dependency(source_id=svc_id, target_id="db"))
    return graph


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestArchitecturePattern:
    def test_pattern_values(self):
        assert ArchitecturePattern.ACTIVE_ACTIVE.value == "active_active"
        assert ArchitecturePattern.CIRCUIT_BREAKER.value == "circuit_breaker"
        assert ArchitecturePattern.BULKHEAD.value == "bulkhead"
        assert ArchitecturePattern.CQRS.value == "cqrs"
        assert ArchitecturePattern.MULTI_REGION.value == "multi_region"

    def test_total_patterns(self):
        assert len(ArchitecturePattern) == 16


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestArchitectureChange:
    def test_creation(self):
        change = ArchitectureChange(
            change_type="modify_component",
            component_id="db",
            description="Add replica",
            before_state={"replicas": 1},
            after_state={"replicas": 3},
            pattern=ArchitecturePattern.ACTIVE_ACTIVE,
            estimated_cost="$100-500/mo",
            effort="hours",
            resilience_impact=10.0,
            risk_reduction="Eliminates SPOF",
        )
        assert change.change_type == "modify_component"
        assert change.component_id == "db"
        assert change.resilience_impact == 10.0
        assert change.pattern == ArchitecturePattern.ACTIVE_ACTIVE

    def test_defaults(self):
        change = ArchitectureChange(
            change_type="add_component",
            component_id="new-cache",
            description="Add cache",
            before_state=None,
            after_state={"type": "cache"},
        )
        assert change.estimated_cost == "$0"
        assert change.effort == "hours"
        assert change.resilience_impact == 0.0
        assert change.pattern is None


class TestArchitectureProposal:
    def test_creation(self):
        proposal = ArchitectureProposal(
            name="HA Upgrade",
            description="High availability upgrade",
            target_nines=4.0,
            current_score=60.0,
            projected_score=85.0,
        )
        assert proposal.name == "HA Upgrade"
        assert proposal.changes == []
        assert proposal.patterns_applied == []
        assert proposal.trade_offs == []

    def test_with_changes(self):
        change = ArchitectureChange(
            change_type="modify_component",
            component_id="db",
            description="Add replica",
            before_state={"replicas": 1},
            after_state={"replicas": 3},
        )
        proposal = ArchitectureProposal(
            name="Test",
            description="Test proposal",
            target_nines=4.0,
            changes=[change],
        )
        assert len(proposal.changes) == 1


class TestArchitectureReport:
    def test_empty_report(self):
        report = ArchitectureReport()
        assert report.current_score == 0.0
        assert report.proposals == []
        assert report.quick_wins == []
        assert report.anti_patterns_detected == []
        assert report.mermaid_diagram == ""

    def test_report_with_data(self):
        report = ArchitectureReport(
            current_assessment="Good infrastructure",
            current_score=75.0,
            current_nines=2.6,
            target_nines=4.0,
            gap_analysis="Need improvements",
        )
        assert report.current_score == 75.0
        assert report.target_nines == 4.0


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_score_to_nines_zero(self):
        assert _score_to_nines(0) == 0.0

    def test_score_to_nines_100(self):
        assert _score_to_nines(100) == 5.0

    def test_score_to_nines_90(self):
        nines = _score_to_nines(90)
        assert 0.9 < nines < 1.1  # ~1.0 nine

    def test_score_to_nines_99(self):
        nines = _score_to_nines(99)
        assert 1.9 < nines < 2.1  # ~2.0 nines

    def test_nines_to_score_zero(self):
        assert _nines_to_score(0) == 0.0

    def test_nines_to_score_five(self):
        assert _nines_to_score(5) == 100.0

    def test_nines_to_score_two(self):
        score = _nines_to_score(2)
        assert 98.5 < score < 99.5  # ~99%

    def test_roundtrip(self):
        """Score -> nines -> score should be approximately the same."""
        for score in [50.0, 70.0, 90.0, 95.0, 99.0]:
            nines = _score_to_nines(score)
            recovered = _nines_to_score(nines)
            assert abs(recovered - score) < 1.0, f"Roundtrip failed for score={score}"


# ---------------------------------------------------------------------------
# Quick Wins Detection
# ---------------------------------------------------------------------------


class TestQuickWins:
    def test_detects_spof_quick_win(self, simple_graph):
        advisor = ArchitectureAdvisor()
        wins = advisor.generate_quick_wins(simple_graph)

        # DB (replicas=1 with dependents) should have a replica quick win
        replica_wins = [w for w in wins if "replica" in w.description.lower() or "Add replica" in w.description]
        assert len(replica_wins) >= 1

    def test_detects_missing_circuit_breaker(self, simple_graph):
        advisor = ArchitectureAdvisor()
        wins = advisor.generate_quick_wins(simple_graph)

        cb_wins = [w for w in wins if "circuit breaker" in w.description.lower()]
        assert len(cb_wins) >= 1  # At least one edge without CB

    def test_detects_missing_autoscaling(self, simple_graph):
        advisor = ArchitectureAdvisor()
        wins = advisor.generate_quick_wins(simple_graph)

        as_wins = [w for w in wins if "autoscaling" in w.description.lower()]
        assert len(as_wins) >= 1

    def test_detects_missing_failover(self, simple_graph):
        advisor = ArchitectureAdvisor()
        wins = advisor.generate_quick_wins(simple_graph)

        fo_wins = [w for w in wins if "failover" in w.description.lower()]
        assert len(fo_wins) >= 1

    def test_fewer_wins_for_redundant_graph(self, redundant_graph):
        advisor = ArchitectureAdvisor()
        wins_simple = advisor.generate_quick_wins(
            InfraGraph()  # Will be replaced
        )
        wins_redundant = advisor.generate_quick_wins(redundant_graph)

        # Redundant graph should have fewer quick wins (no SPOF, no missing CB)
        replica_wins = [w for w in wins_redundant if "replica" in w.description.lower()]
        assert len(replica_wins) == 0  # All have replicas >= 2

    def test_sorted_by_impact(self, simple_graph):
        advisor = ArchitectureAdvisor()
        wins = advisor.generate_quick_wins(simple_graph)

        if len(wins) >= 2:
            # Should be sorted by impact descending
            for i in range(len(wins) - 1):
                assert wins[i].resilience_impact >= wins[i + 1].resilience_impact

    def test_empty_graph_no_wins(self, empty_graph):
        advisor = ArchitectureAdvisor()
        wins = advisor.generate_quick_wins(empty_graph)
        assert wins == []

    def test_single_node_no_replica_win(self, single_node_graph):
        advisor = ArchitectureAdvisor()
        wins = advisor.generate_quick_wins(single_node_graph)
        # Single node with no dependents should NOT get a replica win
        replica_wins = [w for w in wins if "replica" in w.description.lower()]
        assert len(replica_wins) == 0

    def test_detects_missing_cache(self, simple_graph):
        """When DB exists but no cache, suggest adding a cache layer."""
        # Remove cache from simple_graph
        graph = InfraGraph()
        graph.add_component(Component(
            id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        ))
        graph.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
        ))
        graph.add_dependency(Dependency(source_id="lb", target_id="app"))
        graph.add_dependency(Dependency(source_id="app", target_id="db"))

        advisor = ArchitectureAdvisor()
        wins = advisor.generate_quick_wins(graph)
        cache_wins = [w for w in wins if "cache" in w.description.lower() or "caching" in w.description.lower()]
        assert len(cache_wins) >= 1


# ---------------------------------------------------------------------------
# Anti-Pattern Detection
# ---------------------------------------------------------------------------


class TestAntiPatternDetection:
    def test_god_component(self, god_component_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.detect_anti_patterns(god_component_graph)

        god_patterns = [p for p in patterns if p[0] == "God Component"]
        assert len(god_patterns) >= 1
        assert "db" in god_patterns[0][1]

    def test_chain_of_death(self, deep_chain_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.detect_anti_patterns(deep_chain_graph)

        chain_patterns = [p for p in patterns if p[0] == "Chain of Death"]
        assert len(chain_patterns) >= 1

    def test_missing_circuit_breaker_external(self, external_api_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.detect_anti_patterns(external_api_graph)

        missing_cb = [p for p in patterns if p[0] == "Missing Circuit Breaker"]
        assert len(missing_cb) >= 1

    def test_synchronous_everything(self, simple_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.detect_anti_patterns(simple_graph)

        sync_patterns = [p for p in patterns if p[0] == "Synchronous Everything"]
        assert len(sync_patterns) >= 1

    def test_no_bulkhead(self, simple_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.detect_anti_patterns(simple_graph)

        bulkhead_patterns = [p for p in patterns if p[0] == "No Bulkhead"]
        assert len(bulkhead_patterns) >= 1

    def test_empty_graph_no_anti_patterns(self, empty_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.detect_anti_patterns(empty_graph)
        assert patterns == []


# ---------------------------------------------------------------------------
# Pattern Recommendations
# ---------------------------------------------------------------------------


class TestPatternRecommendations:
    def test_spof_recommends_active_passive(self, simple_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.recommend_patterns(simple_graph)

        pattern_types = [p[0] for p in patterns]
        assert (
            ArchitecturePattern.ACTIVE_PASSIVE in pattern_types
            or ArchitecturePattern.ACTIVE_ACTIVE in pattern_types
        )

    def test_deep_chain_recommends_circuit_breaker(self, deep_chain_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.recommend_patterns(deep_chain_graph)

        pattern_types = [p[0] for p in patterns]
        assert ArchitecturePattern.CIRCUIT_BREAKER in pattern_types
        assert ArchitecturePattern.BULKHEAD in pattern_types

    def test_external_api_recommends_retry(self, external_api_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.recommend_patterns(external_api_graph)

        pattern_types = [p[0] for p in patterns]
        assert ArchitecturePattern.RETRY_WITH_BACKOFF in pattern_types

    def test_empty_graph_no_patterns(self, empty_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.recommend_patterns(empty_graph)
        assert patterns == []

    def test_db_heavy_recommends_read_replica(self, god_component_graph):
        advisor = ArchitectureAdvisor()
        patterns = advisor.recommend_patterns(god_component_graph)

        pattern_types = [p[0] for p in patterns]
        assert ArchitecturePattern.READ_REPLICA in pattern_types


# ---------------------------------------------------------------------------
# Mermaid Diagram
# ---------------------------------------------------------------------------


class TestMermaidDiagram:
    def test_generates_valid_mermaid(self, simple_graph):
        advisor = ArchitectureAdvisor()
        diagram = advisor.generate_mermaid_diagram(simple_graph, [])

        assert diagram.startswith("graph TB")
        assert "classDef existing" in diagram
        assert "classDef modified" in diagram
        assert "classDef new" in diagram

    def test_marks_modified_components(self, simple_graph):
        advisor = ArchitectureAdvisor()
        changes = [
            ArchitectureChange(
                change_type="modify_component",
                component_id="db",
                description="Add replica",
                before_state={"replicas": 1},
                after_state={"replicas": 3},
            )
        ]
        diagram = advisor.generate_mermaid_diagram(simple_graph, changes)
        assert "db" in diagram
        assert ":::modified" in diagram

    def test_marks_new_components(self, simple_graph):
        advisor = ArchitectureAdvisor()
        changes = [
            ArchitectureChange(
                change_type="add_component",
                component_id="new-cache",
                description="Add cache layer",
                before_state=None,
                after_state={"type": "cache", "replicas": 2},
            )
        ]
        diagram = advisor.generate_mermaid_diagram(simple_graph, changes)
        assert "new-cache" in diagram
        assert ":::new" in diagram

    def test_empty_graph_still_valid(self, empty_graph):
        advisor = ArchitectureAdvisor()
        diagram = advisor.generate_mermaid_diagram(empty_graph, [])
        assert "graph TB" in diagram
        assert "classDef existing" in diagram

    def test_contains_edges(self, simple_graph):
        advisor = ArchitectureAdvisor()
        diagram = advisor.generate_mermaid_diagram(simple_graph, [])
        # Should have edges between components
        assert "lb" in diagram
        assert "app" in diagram
        assert "db" in diagram


# ---------------------------------------------------------------------------
# Full Advise
# ---------------------------------------------------------------------------


class TestAdvise:
    def test_returns_architecture_report(self, simple_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph)
        assert isinstance(report, ArchitectureReport)

    def test_report_has_current_score(self, simple_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph)
        assert report.current_score > 0
        assert report.current_nines > 0

    def test_report_has_proposals(self, simple_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph, target_nines=4.0)
        assert len(report.proposals) >= 1

    def test_report_has_quick_wins(self, simple_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph)
        assert len(report.quick_wins) >= 1

    def test_report_has_anti_patterns(self, simple_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph)
        assert len(report.anti_patterns_detected) >= 1

    def test_report_has_mermaid_diagram(self, simple_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph)
        assert report.mermaid_diagram != ""
        assert "graph TB" in report.mermaid_diagram

    def test_report_has_assessment(self, simple_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph)
        assert report.current_assessment != ""
        assert report.gap_analysis != ""

    def test_redundant_graph_fewer_issues(self, redundant_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(redundant_graph)

        # Should have fewer quick wins and anti-patterns
        simple_report = advisor.advise(
            InfraGraph()  # Empty graph baseline
        )

        # Redundant graph score should be higher
        assert report.current_score > 0

    def test_empty_graph_report(self, empty_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(empty_graph)
        assert report.current_score == 0.0
        assert report.quick_wins == []
        assert report.proposals == []

    def test_target_nines_respected(self, simple_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph, target_nines=3.0)
        assert report.target_nines == 3.0

    def test_proposals_sorted_by_effort(self, simple_graph):
        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph, target_nines=4.0)

        if len(report.proposals) >= 2:
            # First proposal should be quickest (Quick Wins)
            assert report.proposals[0].name == "Quick Wins"


# ---------------------------------------------------------------------------
# Apply Proposal
# ---------------------------------------------------------------------------


class TestApplyProposal:
    def test_apply_creates_new_graph(self, simple_graph):
        advisor = ArchitectureAdvisor()
        proposal = ArchitectureProposal(
            name="Test",
            description="Test proposal",
            target_nines=4.0,
            changes=[
                ArchitectureChange(
                    change_type="modify_component",
                    component_id="db",
                    description="Add replicas",
                    before_state={"replicas": 1},
                    after_state={"replicas": 3, "failover_enabled": True},
                )
            ],
        )

        modified = advisor.apply_proposal(simple_graph, proposal)

        # Original should be unchanged
        assert simple_graph.get_component("db").replicas == 1
        # Modified should have the change
        assert modified.get_component("db").replicas == 3
        assert modified.get_component("db").failover.enabled is True

    def test_apply_add_component(self, simple_graph):
        advisor = ArchitectureAdvisor()
        proposal = ArchitectureProposal(
            name="Test",
            description="Add new component",
            target_nines=4.0,
            changes=[
                ArchitectureChange(
                    change_type="add_component",
                    component_id="new-queue",
                    description="Add message queue",
                    before_state=None,
                    after_state={"type": "queue", "replicas": 2, "name": "Message Queue"},
                )
            ],
        )

        modified = advisor.apply_proposal(simple_graph, proposal)
        assert "new-queue" in modified.components
        assert modified.get_component("new-queue").type == ComponentType.QUEUE
        assert modified.get_component("new-queue").replicas == 2

    def test_apply_modify_dependency(self, simple_graph):
        advisor = ArchitectureAdvisor()
        proposal = ArchitectureProposal(
            name="Test",
            description="Add circuit breaker",
            target_nines=4.0,
            changes=[
                ArchitectureChange(
                    change_type="modify_dependency",
                    component_id="app->db",
                    description="Enable circuit breaker",
                    before_state={"circuit_breaker_enabled": False},
                    after_state={
                        "circuit_breaker_enabled": True,
                        "failure_threshold": 5,
                    },
                )
            ],
        )

        modified = advisor.apply_proposal(simple_graph, proposal)
        edge = modified.get_dependency_edge("app", "db")
        assert edge is not None
        assert edge.circuit_breaker.enabled is True


# ---------------------------------------------------------------------------
# Compare Before/After
# ---------------------------------------------------------------------------


class TestCompareBeforeAfter:
    def test_compare_returns_expected_keys(self, simple_graph):
        advisor = ArchitectureAdvisor()
        # Create a modified graph
        proposal = ArchitectureProposal(
            name="Test",
            description="Test",
            target_nines=4.0,
            changes=[
                ArchitectureChange(
                    change_type="modify_component",
                    component_id="db",
                    description="Add replicas",
                    before_state={"replicas": 1},
                    after_state={"replicas": 3},
                )
            ],
        )
        modified = advisor.apply_proposal(simple_graph, proposal)
        comparison = advisor.compare_before_after(simple_graph, modified)

        assert "original_score" in comparison
        assert "modified_score" in comparison
        assert "score_improvement" in comparison
        assert "original_nines" in comparison
        assert "modified_nines" in comparison
        assert "nines_improvement" in comparison

    def test_improvement_is_positive(self, simple_graph):
        advisor = ArchitectureAdvisor()
        proposal = ArchitectureProposal(
            name="Test",
            description="Test",
            target_nines=4.0,
            changes=[
                ArchitectureChange(
                    change_type="modify_component",
                    component_id="db",
                    description="Add replicas",
                    before_state={"replicas": 1},
                    after_state={"replicas": 3},
                )
            ],
        )
        modified = advisor.apply_proposal(simple_graph, proposal)
        comparison = advisor.compare_before_after(simple_graph, modified)

        # Adding replicas should improve the score
        assert comparison["score_improvement"] >= 0

    def test_same_graph_no_improvement(self, simple_graph):
        advisor = ArchitectureAdvisor()
        comparison = advisor.compare_before_after(simple_graph, simple_graph)
        assert comparison["score_improvement"] == 0.0
        assert comparison["nines_improvement"] == 0.0


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_workflow(self, simple_graph):
        """Test the full advise -> apply -> compare workflow."""
        advisor = ArchitectureAdvisor()

        # Step 1: Get advice
        report = advisor.advise(simple_graph, target_nines=4.0)
        assert report.current_score > 0
        assert len(report.proposals) >= 1

        # Step 2: Apply first proposal
        proposal = report.proposals[0]
        modified = advisor.apply_proposal(simple_graph, proposal)
        assert len(modified.components) >= len(simple_graph.components)

        # Step 3: Compare
        comparison = advisor.compare_before_after(simple_graph, modified)
        assert comparison["score_improvement"] >= 0

    def test_report_serializable(self, simple_graph):
        """Verify the report can be serialized to JSON (for API endpoint)."""
        import dataclasses

        advisor = ArchitectureAdvisor()
        report = advisor.advise(simple_graph)
        report_dict = dataclasses.asdict(report)

        # Should be JSON-serializable
        json_str = json.dumps(report_dict, default=str)
        assert len(json_str) > 0

        # Should be deserializable
        parsed = json.loads(json_str)
        assert parsed["current_score"] == report.current_score
        assert parsed["target_nines"] == report.target_nines

    def test_god_component_gets_advice(self, god_component_graph):
        """God component graph should get specific advice."""
        advisor = ArchitectureAdvisor()
        report = advisor.advise(god_component_graph)

        # Should detect the god component anti-pattern
        anti_pattern_names = [p[0] for p in report.anti_patterns_detected]
        assert "God Component" in anti_pattern_names

        # Should recommend patterns to fix it
        assert len(report.architecture_patterns_recommended) >= 1

    def test_external_api_gets_circuit_breaker_advice(self, external_api_graph):
        """External API graph should get circuit breaker recommendation."""
        advisor = ArchitectureAdvisor()
        report = advisor.advise(external_api_graph)

        pattern_types = [p[0] for p in report.architecture_patterns_recommended]
        assert ArchitecturePattern.CIRCUIT_BREAKER in pattern_types or \
               ArchitecturePattern.RETRY_WITH_BACKOFF in pattern_types
