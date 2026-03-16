"""Tests for K8s Pod Disruption Analyzer."""

from __future__ import annotations

import math

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.k8s_pod_disruption_analyzer import (
    AnalysisReport,
    ConflictCategory,
    CrossNamespaceInteraction,
    DisruptionSeverity,
    DrainOutcome,
    DrainSimulationResult,
    EvictionBudget,
    MaintenanceStrategy,
    MaintenanceWindow,
    PDBConflict,
    PDBPolicyType,
    PDBRecommendation,
    PDBSpec,
    PodDisruptionAnalyzer,
    RecommendationPriority,
    RiskLevel,
    RollingUpdateImpact,
    ViolationRisk,
    WorkloadPDBDifference,
    WorkloadType,
    _calculate_max_unavailable,
    _calculate_min_available,
    _clamp,
    _labels_overlap,
    _risk_level_from_score,
    _severity_rank,
    _workload_duration_multiplier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _make_pdb(
    pdb_id: str = "pdb1",
    component_ids: list[str] | None = None,
    **kwargs,
) -> PDBSpec:
    """Convenience factory for PDBSpec with sensible defaults."""
    defaults: dict = dict(
        pdb_id=pdb_id,
        namespace="default",
        policy_type=PDBPolicyType.MAX_UNAVAILABLE,
        value=1,
        total_replicas=3,
        ready_replicas=3,
        component_ids=component_ids or ["c1"],
    )
    defaults.update(kwargs)
    return PDBSpec(**defaults)


# ============================================================================
# Tests for helper functions
# ============================================================================


class TestCalculateMinAvailable:
    """Tests for _calculate_min_available."""

    def test_max_unavailable_absolute(self):
        spec = _make_pdb(policy_type=PDBPolicyType.MAX_UNAVAILABLE, value=1, total_replicas=5)
        assert _calculate_min_available(spec) == 4

    def test_max_unavailable_percentage(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MAX_UNAVAILABLE, value=50,
            percentage=True, total_replicas=6,
        )
        # floor(6*50/100) = 3 -> min_avail = 6-3 = 3
        assert _calculate_min_available(spec) == 3

    def test_min_available_absolute(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=2, total_replicas=5,
        )
        assert _calculate_min_available(spec) == 2

    def test_min_available_percentage(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=60,
            percentage=True, total_replicas=5,
        )
        # ceil(5*60/100) = ceil(3.0) = 3
        assert _calculate_min_available(spec) == 3

    def test_min_available_capped_by_replicas(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=10, total_replicas=3,
        )
        assert _calculate_min_available(spec) == 3

    def test_max_unavailable_percentage_floor_at_one(self):
        """Even a tiny percentage must floor to at least 1 unavailable."""
        spec = _make_pdb(
            policy_type=PDBPolicyType.MAX_UNAVAILABLE, value=1,
            percentage=True, total_replicas=3,
        )
        # floor(3*1/100) = 0 -> max(1, 0) = 1 -> min_avail = 3 - 1 = 2
        assert _calculate_min_available(spec) == 2


class TestCalculateMaxUnavailable:
    """Tests for _calculate_max_unavailable."""

    def test_max_unavailable_absolute(self):
        spec = _make_pdb(policy_type=PDBPolicyType.MAX_UNAVAILABLE, value=2, total_replicas=5)
        assert _calculate_max_unavailable(spec) == 2

    def test_max_unavailable_capped_by_replicas(self):
        spec = _make_pdb(policy_type=PDBPolicyType.MAX_UNAVAILABLE, value=10, total_replicas=3)
        assert _calculate_max_unavailable(spec) == 3

    def test_max_unavailable_percentage(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MAX_UNAVAILABLE, value=50,
            percentage=True, total_replicas=6,
        )
        assert _calculate_max_unavailable(spec) == 3

    def test_min_available_derives_max_unavailable(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=2, total_replicas=5,
        )
        assert _calculate_max_unavailable(spec) == 3

    def test_min_available_percentage_derives_max(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=50,
            percentage=True, total_replicas=6,
        )
        # ceil(6*50/100) = 3 -> max_unav = 6 - 3 = 3
        assert _calculate_max_unavailable(spec) == 3

    def test_max_unavailable_percentage_floor(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MAX_UNAVAILABLE, value=10,
            percentage=True, total_replicas=5,
        )
        # floor(5*10/100) = 0 -> max(1, 0) = 1
        assert _calculate_max_unavailable(spec) == 1


class TestLabelsOverlap:
    """Tests for _labels_overlap."""

    def test_no_overlap(self):
        assert _labels_overlap({"a": "1"}, {"b": "2"}) is False

    def test_overlap(self):
        assert _labels_overlap({"a": "1"}, {"a": "1", "b": "2"}) is True

    def test_empty_a(self):
        assert _labels_overlap({}, {"a": "1"}) is False

    def test_empty_b(self):
        assert _labels_overlap({"a": "1"}, {}) is False

    def test_both_empty(self):
        assert _labels_overlap({}, {}) is False

    def test_same_key_different_value(self):
        assert _labels_overlap({"a": "1"}, {"a": "2"}) is False


class TestSeverityRank:
    """Tests for _severity_rank."""

    def test_all_levels(self):
        assert _severity_rank(DisruptionSeverity.INFO) == 0
        assert _severity_rank(DisruptionSeverity.LOW) == 1
        assert _severity_rank(DisruptionSeverity.MEDIUM) == 2
        assert _severity_rank(DisruptionSeverity.HIGH) == 3
        assert _severity_rank(DisruptionSeverity.CRITICAL) == 4


class TestRiskLevelFromScore:
    """Tests for _risk_level_from_score."""

    def test_minimal(self):
        assert _risk_level_from_score(0.0) == RiskLevel.MINIMAL
        assert _risk_level_from_score(19.9) == RiskLevel.MINIMAL

    def test_low(self):
        assert _risk_level_from_score(20.0) == RiskLevel.LOW
        assert _risk_level_from_score(39.9) == RiskLevel.LOW

    def test_moderate(self):
        assert _risk_level_from_score(40.0) == RiskLevel.MODERATE
        assert _risk_level_from_score(59.9) == RiskLevel.MODERATE

    def test_high(self):
        assert _risk_level_from_score(60.0) == RiskLevel.HIGH
        assert _risk_level_from_score(79.9) == RiskLevel.HIGH

    def test_critical(self):
        assert _risk_level_from_score(80.0) == RiskLevel.CRITICAL
        assert _risk_level_from_score(100.0) == RiskLevel.CRITICAL


class TestClamp:
    """Tests for _clamp."""

    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_lo(self):
        assert _clamp(-10.0) == 0.0

    def test_above_hi(self):
        assert _clamp(150.0) == 100.0

    def test_custom_range(self):
        assert _clamp(0.5, 0.0, 1.0) == 0.5
        assert _clamp(2.0, 0.0, 1.0) == 1.0
        assert _clamp(-1.0, 0.0, 1.0) == 0.0


class TestWorkloadDurationMultiplier:
    """Tests for _workload_duration_multiplier."""

    def test_deployment(self):
        assert _workload_duration_multiplier(WorkloadType.DEPLOYMENT) == 1.0

    def test_stateful_set(self):
        assert _workload_duration_multiplier(WorkloadType.STATEFUL_SET) == 1.5

    def test_daemon_set(self):
        assert _workload_duration_multiplier(WorkloadType.DAEMON_SET) == 1.2

    def test_replica_set(self):
        assert _workload_duration_multiplier(WorkloadType.REPLICA_SET) == 1.0


# ============================================================================
# Tests for PodDisruptionAnalyzer
# ============================================================================


class TestAnalyzerInit:
    """Test analyzer construction and configuration API."""

    def test_init_empty_graph(self):
        g = _graph()
        analyzer = PodDisruptionAnalyzer(g)
        assert analyzer.pdbs == {}
        assert analyzer.node_assignments == {}

    def test_add_and_remove_pdb(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        pdb = _make_pdb("p1")
        analyzer.add_pdb(pdb)
        assert "p1" in analyzer.pdbs
        assert analyzer.remove_pdb("p1") is True
        assert "p1" not in analyzer.pdbs

    def test_remove_nonexistent_pdb(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        assert analyzer.remove_pdb("nonexistent") is False

    def test_set_node_assignment(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1", "c2"])
        assert analyzer.node_assignments == {"node1": ["c1", "c2"]}

    def test_set_traffic_weight(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_traffic_weight("c1", 0.9)
        # Verify indirectly via violation risk
        pdb = _make_pdb("p1", component_ids=["c1"], total_replicas=5, ready_replicas=5)
        analyzer.add_pdb(pdb)
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("traffic" in f.lower() for f in risk.contributing_factors)

    def test_set_drain_timeout(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_drain_timeout(120.0)
        # Negative clamped to 0
        analyzer.set_drain_timeout(-5.0)

    def test_set_traffic_weight_clamped(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_traffic_weight("c1", 1.5)  # clamped to 1.0
        analyzer.set_traffic_weight("c2", -0.5)  # clamped to 0.0


# ============================================================================
# PDB Policy Evaluation
# ============================================================================


class TestEvaluatePDBPolicy:
    """Tests for evaluate_pdb_policy."""

    def test_nonexistent_pdb(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        assert analyzer.evaluate_pdb_policy("no-such") is None

    def test_basic_max_unavailable(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", total_replicas=5, ready_replicas=5, value=2))
        budget = analyzer.evaluate_pdb_policy("p1")
        assert budget is not None
        assert budget.allowed_disruptions == 2
        assert budget.is_blocked is False
        assert budget.headroom == 2  # 5 - 3

    def test_blocked_when_not_enough_ready(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=3, ready_replicas=2, value=1,
            policy_type=PDBPolicyType.MAX_UNAVAILABLE,
        ))
        budget = analyzer.evaluate_pdb_policy("p1")
        assert budget is not None
        # current_unavailable=1, max_unavailable=1, allowed=0
        assert budget.allowed_disruptions == 0
        assert budget.is_blocked is True

    def test_min_available_policy(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=2, total_replicas=5, ready_replicas=5,
        ))
        budget = analyzer.evaluate_pdb_policy("p1")
        assert budget is not None
        assert budget.min_available_effective == 2
        assert budget.max_unavailable_effective == 3
        assert budget.allowed_disruptions == 3

    def test_evaluate_all_pdbs(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["c1"]))
        analyzer.add_pdb(_make_pdb("p2", component_ids=["c2"]))
        budgets = analyzer.evaluate_all_pdbs()
        assert len(budgets) == 2

    def test_empty_component_ids(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(PDBSpec(pdb_id="p1", component_ids=[], total_replicas=3, ready_replicas=3))
        budget = analyzer.evaluate_pdb_policy("p1")
        assert budget is not None
        assert budget.component_id == ""

    def test_percentage_based_budget(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MAX_UNAVAILABLE,
            value=50, percentage=True, total_replicas=10, ready_replicas=10,
        ))
        budget = analyzer.evaluate_pdb_policy("p1")
        assert budget is not None
        assert budget.max_unavailable_effective == 5
        assert budget.allowed_disruptions == 5


# ============================================================================
# Rolling Update Impact
# ============================================================================


class TestRollingUpdateImpact:
    """Tests for analyze_rolling_update."""

    def test_nonexistent_pdb(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        assert analyzer.analyze_rolling_update("nope") is None

    def test_basic_rolling_update(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", total_replicas=6, value=2, max_surge=1))
        impact = analyzer.analyze_rolling_update("p1")
        assert impact is not None
        assert impact.can_proceed is True
        assert impact.pod_transitions == 6
        assert impact.effective_parallelism == 2
        assert impact.severity == DisruptionSeverity.INFO

    def test_blocked_rolling_update(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=5, total_replicas=5,
        ))
        impact = analyzer.analyze_rolling_update("p1")
        assert impact is not None
        assert impact.can_proceed is False
        assert impact.severity == DisruptionSeverity.CRITICAL
        assert "blocked" in impact.blocking_reason.lower()

    def test_parallelism_limited_to_one(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=10, value=1, max_surge=0,
        ))
        impact = analyzer.analyze_rolling_update("p1")
        assert impact is not None
        assert impact.effective_parallelism == 1
        assert impact.severity == DisruptionSeverity.MEDIUM

    def test_statefulset_slower(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=3, value=1,
            workload_type=WorkloadType.STATEFUL_SET,
        ))
        impact_ss = analyzer.analyze_rolling_update("p1")
        assert impact_ss is not None
        # StatefulSet multiplier 1.5x
        assert impact_ss.estimated_duration_seconds > 90.0
        assert impact_ss.severity != DisruptionSeverity.INFO  # at least LOW

    def test_analyze_all_rolling_updates(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["c1"]))
        analyzer.add_pdb(_make_pdb("p2", component_ids=["c2"]))
        impacts = analyzer.analyze_all_rolling_updates()
        assert len(impacts) == 2

    def test_low_parallelism_severity(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=12, value=1, max_surge=1,
        ))
        impact = analyzer.analyze_rolling_update("p1")
        assert impact is not None
        # effective_parallelism=1, which is < 12//3=4
        assert impact.severity == DisruptionSeverity.MEDIUM

    def test_daemon_set_multiplier(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=3, value=1,
            workload_type=WorkloadType.DAEMON_SET,
        ))
        impact = analyzer.analyze_rolling_update("p1")
        assert impact is not None
        # DaemonSet 1.2x multiplier
        base_duration = math.ceil(3 / 1) * 30.0  # parallelism=1
        assert impact.estimated_duration_seconds == pytest.approx(base_duration * 1.2)


# ============================================================================
# Node Drain Simulation
# ============================================================================


class TestNodeDrainSimulation:
    """Tests for simulate_node_drain."""

    def test_empty_node(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        result = analyzer.simulate_node_drain("node-empty")
        assert result.outcome == DrainOutcome.SUCCESS
        assert result.total_pods == 0

    def test_all_evictable(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1", "c2"])
        # No PDBs -> all evictable
        result = analyzer.simulate_node_drain("node1")
        assert result.outcome == DrainOutcome.SUCCESS
        assert result.pods_evicted == 2
        assert result.pods_blocked == 0

    def test_all_blocked(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1"])
        # PDB that blocks all
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        result = analyzer.simulate_node_drain("node1")
        assert result.outcome == DrainOutcome.BLOCKED
        assert result.pods_blocked == 1
        assert result.pods_evicted == 0
        assert result.severity == DisruptionSeverity.CRITICAL
        assert "p1" in result.blocking_pdbs

    def test_partial_drain(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1", "c2"])
        # c1 is blocked, c2 has no PDB
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        result = analyzer.simulate_node_drain("node1")
        assert result.outcome == DrainOutcome.PARTIAL
        assert result.pods_evicted == 1
        assert result.pods_blocked == 1
        assert result.severity == DisruptionSeverity.HIGH

    def test_cascade_affected(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1"])
        result = analyzer.simulate_node_drain("node1")
        assert "c2" in result.cascade_affected

    def test_drain_timeout_affects_duration(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_drain_timeout(60.0)
        analyzer.set_node_assignment("node1", ["c1"])
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        result = analyzer.simulate_node_drain("node1")
        assert result.connection_drain_seconds == 60.0
        assert result.estimated_duration_seconds >= 60.0

    def test_multi_node_drain(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("n1", ["c1"])
        analyzer.set_node_assignment("n2", ["c2"])
        results = analyzer.simulate_multi_node_drain(["n1", "n2"])
        assert len(results) == 2
        assert all(r.outcome == DrainOutcome.SUCCESS for r in results)


# ============================================================================
# Conflict Detection
# ============================================================================


class TestConflictDetection:
    """Tests for detect_conflicts."""

    def test_no_conflicts_with_single_pdb(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1"))
        assert analyzer.detect_conflicts() == []

    def test_overlapping_selector(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            selector_labels={"app": "web"},
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"],
            selector_labels={"app": "web"},
        ))
        conflicts = analyzer.detect_conflicts()
        cat = [c.conflict_category for c in conflicts]
        assert ConflictCategory.OVERLAPPING_SELECTOR in cat

    def test_contradictory_budget(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MAX_UNAVAILABLE,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=2,
        ))
        conflicts = analyzer.detect_conflicts()
        cat = [c.conflict_category for c in conflicts]
        assert ConflictCategory.CONTRADICTORY_BUDGET in cat

    def test_over_constrained(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=2,
            total_replicas=3,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=2,
            total_replicas=3,
        ))
        conflicts = analyzer.detect_conflicts()
        cat = [c.conflict_category for c in conflicts]
        # combined min_available=4 > replicas=1 (from graph component)
        assert ConflictCategory.OVER_CONSTRAINED in cat

    def test_cross_namespace_clash(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], namespace="ns-a",
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c1"], namespace="ns-b",
        ))
        conflicts = analyzer.detect_conflicts()
        cat = [c.conflict_category for c in conflicts]
        assert ConflictCategory.CROSS_NAMESPACE_CLASH in cat

    def test_stale_selector(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            selector_labels={"app": "web"},
            ready_replicas=0, total_replicas=3,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"],
            selector_labels={"app": "web"},
            ready_replicas=3, total_replicas=3,
        ))
        conflicts = analyzer.detect_conflicts()
        cat = [c.conflict_category for c in conflicts]
        assert ConflictCategory.STALE_SELECTOR in cat

    def test_no_conflict_disjoint(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["c1"]))
        analyzer.add_pdb(_make_pdb("p2", component_ids=["c2"]))
        assert analyzer.detect_conflicts() == []

    def test_over_constrained_uses_graph_replicas(self):
        """When component exists in graph, use its replicas for constraint check."""
        c = _comp("c1")
        g = _graph(c)
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=1, total_replicas=3,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=1, total_replicas=3,
        ))
        conflicts = analyzer.detect_conflicts()
        # combined min=2, graph replicas=1 -> over-constrained
        over = [c for c in conflicts if c.conflict_category == ConflictCategory.OVER_CONSTRAINED]
        assert len(over) == 1


# ============================================================================
# Eviction Budget Calculation
# ============================================================================


class TestEvictionBudget:
    """Tests for calculate_eviction_budget."""

    def test_no_pdb_for_component(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        budget = analyzer.calculate_eviction_budget("c1")
        assert budget is not None
        assert budget.pdb_id == ""
        assert budget.allowed_disruptions == 1  # replicas=1

    def test_component_not_in_graph(self):
        g = _graph()
        analyzer = PodDisruptionAnalyzer(g)
        assert analyzer.calculate_eviction_budget("no-such") is None

    def test_most_restrictive_pdb_wins(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], value=2,
            total_replicas=5, ready_replicas=5,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c1"], value=1,
            total_replicas=5, ready_replicas=5,
        ))
        budget = analyzer.calculate_eviction_budget("c1")
        assert budget is not None
        assert budget.allowed_disruptions == 1


# ============================================================================
# Maintenance Window Optimization
# ============================================================================


class TestMaintenanceWindows:
    """Tests for optimize_maintenance_windows."""

    def test_default_windows(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=10, ready_replicas=10, value=5,
        ))
        windows = analyzer.optimize_maintenance_windows()
        assert len(windows) == 2
        assert all(isinstance(w, MaintenanceWindow) for w in windows)

    def test_custom_hours(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", total_replicas=4, value=2))
        windows = analyzer.optimize_maintenance_windows(
            available_hours=[(10, 14)],
        )
        assert len(windows) == 1
        assert windows[0].start_hour == 10
        assert windows[0].end_hour == 14
        assert windows[0].estimated_duration_minutes == 240.0

    def test_no_pdbs_no_replicas(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        # No PDBs -> no windows since total_replicas = 0
        windows = analyzer.optimize_maintenance_windows()
        assert windows == []

    def test_zero_disruption_budget(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        windows = analyzer.optimize_maintenance_windows()
        assert all(w.strategy == MaintenanceStrategy.BIG_BANG for w in windows)
        assert all(w.risk_score == 100.0 for w in windows)

    def test_high_disruption_ratio(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=10, ready_replicas=10, value=8,
        ))
        windows = analyzer.optimize_maintenance_windows()
        # ratio=8/10=0.8 > 0.5 -> ROLLING
        assert all(w.strategy == MaintenanceStrategy.ROLLING for w in windows)

    def test_canary_strategy(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=10, ready_replicas=10, value=3,
        ))
        windows = analyzer.optimize_maintenance_windows()
        # ratio=3/10=0.3 > 0.2 -> CANARY
        assert all(w.strategy == MaintenanceStrategy.CANARY for w in windows)

    def test_blue_green_strategy(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=10, ready_replicas=10, value=1,
        ))
        windows = analyzer.optimize_maintenance_windows()
        # ratio=1/10=0.1 -> BLUE_GREEN
        assert all(w.strategy == MaintenanceStrategy.BLUE_GREEN for w in windows)

    def test_wrap_around_hours(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", total_replicas=4, value=2))
        windows = analyzer.optimize_maintenance_windows(
            available_hours=[(22, 2)],
        )
        assert len(windows) == 1
        assert windows[0].estimated_duration_minutes == 240.0

    def test_sorted_by_risk(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", total_replicas=4, value=2))
        windows = analyzer.optimize_maintenance_windows(
            available_hours=[(2, 6), (10, 14), (22, 2)],
        )
        risk_scores = [w.risk_score for w in windows]
        assert risk_scores == sorted(risk_scores)


# ============================================================================
# Workload Differences
# ============================================================================


class TestWorkloadDifferences:
    """Tests for analyze_workload_differences."""

    def test_returns_all_types(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        diffs = analyzer.analyze_workload_differences()
        types = {d.workload_type for d in diffs}
        assert types == {
            WorkloadType.DEPLOYMENT,
            WorkloadType.STATEFUL_SET,
            WorkloadType.DAEMON_SET,
            WorkloadType.REPLICA_SET,
        }

    def test_statefulset_properties(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        diffs = analyzer.analyze_workload_differences()
        ss = [d for d in diffs if d.workload_type == WorkloadType.STATEFUL_SET][0]
        assert ss.ordered_pod_management is True
        assert ss.supports_parallel_scaling is False
        assert ss.volume_affinity is True
        assert ss.identity_stability is True
        assert ss.pdb_effectiveness_score == 75.0

    def test_deployment_properties(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        diffs = analyzer.analyze_workload_differences()
        dep = [d for d in diffs if d.workload_type == WorkloadType.DEPLOYMENT][0]
        assert dep.ordered_pod_management is False
        assert dep.supports_parallel_scaling is True
        assert dep.pdb_effectiveness_score == 90.0

    def test_daemonset_properties(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        diffs = analyzer.analyze_workload_differences()
        ds = [d for d in diffs if d.workload_type == WorkloadType.DAEMON_SET][0]
        assert ds.pdb_effectiveness_score == 60.0
        assert len(ds.notes) >= 1


# ============================================================================
# Violation Risk Scoring
# ============================================================================


class TestViolationRisk:
    """Tests for assess_violation_risk."""

    def test_nonexistent_pdb(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        assert analyzer.assess_violation_risk("nope") is None

    def test_low_risk_healthy_pdb(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=10, ready_replicas=10, value=2,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert risk.risk_score < 40.0
        assert risk.risk_level in (RiskLevel.MINIMAL, RiskLevel.LOW)

    def test_high_risk_blocked_pdb(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=2, total_replicas=2, ready_replicas=2,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert risk.risk_score >= 40.0

    def test_statefulset_adds_risk(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=5, ready_replicas=5, value=1,
            workload_type=WorkloadType.STATEFUL_SET,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("StatefulSet" in f for f in risk.contributing_factors)

    def test_daemonset_adds_risk(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=5, ready_replicas=5, value=1,
            workload_type=WorkloadType.DAEMON_SET,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("DaemonSet" in f for f in risk.contributing_factors)

    def test_low_replica_count_increases_risk(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", total_replicas=2, ready_replicas=2, value=1))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("Low replica" in f for f in risk.contributing_factors)

    def test_moderate_replica_count(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", total_replicas=4, ready_replicas=4, value=1))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("Moderate replica" in f for f in risk.contributing_factors)

    def test_percentage_small_set(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=3, ready_replicas=3,
            value=50, percentage=True,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("Percentage" in f for f in risk.contributing_factors)

    def test_single_node_concentration(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1"])
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=3, ready_replicas=3, value=1,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("single node" in f.lower() for f in risk.contributing_factors)

    def test_partial_node_concentration(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1"])
        analyzer.set_node_assignment("node2", ["c1"])
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=5, ready_replicas=5, value=1,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("concentration" in f.lower() for f in risk.contributing_factors)

    def test_high_traffic_weight(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_traffic_weight("c1", 0.9)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=5, ready_replicas=5, value=1,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("High traffic" in f for f in risk.contributing_factors)

    def test_moderate_traffic_weight(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_traffic_weight("c1", 0.6)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=5, ready_replicas=5, value=1,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("Moderate traffic" in f for f in risk.contributing_factors)

    def test_assess_all(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["c1"]))
        analyzer.add_pdb(_make_pdb("p2", component_ids=["c2"]))
        risks = analyzer.assess_all_violation_risks()
        assert len(risks) == 2

    def test_blocked_pdb_has_mitigation(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert len(risk.mitigations) > 0

    def test_very_low_headroom(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        # headroom = 20 - 19 = 1, ratio = 1/20 = 0.05 < 0.1
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=19, total_replicas=20, ready_replicas=20,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("Very low headroom" in f for f in risk.contributing_factors)

    def test_moderate_headroom(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=6, total_replicas=10, ready_replicas=10,
        ))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert any("Moderate headroom" in f for f in risk.contributing_factors)

    def test_violation_probability_range(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", total_replicas=5, ready_replicas=5, value=1))
        risk = analyzer.assess_violation_risk("p1")
        assert risk is not None
        assert 0.0 <= risk.violation_probability <= 1.0


# ============================================================================
# Cross-Namespace Interaction
# ============================================================================


class TestCrossNamespace:
    """Tests for analyze_cross_namespace."""

    def test_same_namespace_no_interaction(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["c1"], namespace="default"))
        analyzer.add_pdb(_make_pdb("p2", component_ids=["c2"], namespace="default"))
        assert analyzer.analyze_cross_namespace() == []

    def test_different_namespace_shared_node(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1", "c2"])
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], namespace="ns-a",
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=2,
            total_replicas=3, ready_replicas=3,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"], namespace="ns-b",
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=2,
            total_replicas=3, ready_replicas=3,
        ))
        interactions = analyzer.analyze_cross_namespace()
        assert len(interactions) >= 1
        assert interactions[0].shared_node_pool is True

    def test_no_shared_nodes_no_interaction(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1"])
        analyzer.set_node_assignment("node2", ["c2"])
        # High max_unavailable -> no resource contention
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], namespace="ns-a",
            value=5, total_replicas=5, ready_replicas=5,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"], namespace="ns-b",
            value=5, total_replicas=5, ready_replicas=5,
        ))
        interactions = analyzer.analyze_cross_namespace()
        assert interactions == []

    def test_resource_contention(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1", "c2"])
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], namespace="ns-a",
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=4,
            total_replicas=5, ready_replicas=5,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"], namespace="ns-b",
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=4,
            total_replicas=5, ready_replicas=5,
        ))
        interactions = analyzer.analyze_cross_namespace()
        assert len(interactions) >= 1
        assert any(i.resource_contention for i in interactions)

    def test_eviction_priority_conflict(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1", "c2"])
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], namespace="ns-a",
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=2,
            total_replicas=3, ready_replicas=3,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"], namespace="ns-b",
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=2,
            total_replicas=3, ready_replicas=3,
        ))
        interactions = analyzer.analyze_cross_namespace()
        assert len(interactions) >= 1
        assert any(i.eviction_priority_conflict for i in interactions)

    def test_severity_high_when_shared_and_contention(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1", "c2"])
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], namespace="ns-a",
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=4,
            total_replicas=5, ready_replicas=5,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"], namespace="ns-b",
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=4,
            total_replicas=5, ready_replicas=5,
        ))
        interactions = analyzer.analyze_cross_namespace()
        high_sev = [i for i in interactions if i.severity == DisruptionSeverity.HIGH]
        assert len(high_sev) >= 1


# ============================================================================
# Recommendations
# ============================================================================


class TestRecommendations:
    """Tests for generate_recommendations."""

    def test_blocked_eviction_recommendation(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        recs = analyzer.generate_recommendations()
        blocked = [r for r in recs if r.category == "blocked_eviction"]
        assert len(blocked) >= 1
        assert blocked[0].priority == RecommendationPriority.MUST

    def test_percentage_small_set_recommendation(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=3, ready_replicas=3,
            value=50, percentage=True,
        ))
        recs = analyzer.generate_recommendations()
        pct_recs = [r for r in recs if r.category == "percentage_small_set"]
        assert len(pct_recs) >= 1

    def test_zero_tolerance_recommendation(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=5, total_replicas=5, ready_replicas=5,
        ))
        recs = analyzer.generate_recommendations()
        zt = [r for r in recs if r.category == "zero_tolerance"]
        assert len(zt) >= 1

    def test_statefulset_awareness_recommendation(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=5, ready_replicas=5, value=1,
            workload_type=WorkloadType.STATEFUL_SET,
        ))
        recs = analyzer.generate_recommendations()
        ss = [r for r in recs if r.category == "statefulset_awareness"]
        assert len(ss) >= 1
        assert ss[0].priority == RecommendationPriority.NICE_TO_HAVE

    def test_single_replica_recommendation(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=1, ready_replicas=1, value=1,
        ))
        recs = analyzer.generate_recommendations()
        sr = [r for r in recs if r.category == "single_replica"]
        assert len(sr) >= 1
        assert sr[0].priority == RecommendationPriority.MUST

    def test_high_max_unavailable_recommendation(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=6, ready_replicas=6, value=4,
        ))
        recs = analyzer.generate_recommendations()
        hmu = [r for r in recs if r.category == "high_max_unavailable"]
        assert len(hmu) >= 1

    def test_daemonset_restrictive_recommendation(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=3, ready_replicas=3,
            workload_type=WorkloadType.DAEMON_SET,
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=3,
        ))
        recs = analyzer.generate_recommendations()
        ds = [r for r in recs if r.category == "daemonset_restrictive"]
        assert len(ds) >= 1

    def test_empty_component_ids_in_recommendation(self):
        g = _graph()
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(PDBSpec(
            pdb_id="p1", component_ids=[], total_replicas=1,
            ready_replicas=1, value=1,
        ))
        recs = analyzer.generate_recommendations()
        assert all(r.component_id == "" for r in recs)


# ============================================================================
# Full Analysis
# ============================================================================


class TestFullAnalysis:
    """Tests for analyze() method."""

    def test_basic_analysis(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))

        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], total_replicas=5, value=1,
        ))
        analyzer.set_node_assignment("node1", ["c1", "c2"])

        report = analyzer.analyze()

        assert isinstance(report, AnalysisReport)
        assert report.total_pdbs == 1
        assert report.total_components == 2
        assert len(report.eviction_budgets) == 1
        assert len(report.rolling_update_impacts) == 1
        assert len(report.drain_results) == 1
        assert len(report.workload_differences) == 4
        assert report.overall_risk_score >= 0.0
        assert report.timestamp != ""

    def test_analysis_with_no_pdbs(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        report = analyzer.analyze()
        assert report.total_pdbs == 0
        assert len(report.eviction_budgets) == 0
        assert report.overall_risk_score == 0.0
        assert report.overall_risk_level == RiskLevel.MINIMAL

    def test_analysis_with_conflicts(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MAX_UNAVAILABLE, value=1,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE, value=2,
        ))
        report = analyzer.analyze()
        assert len(report.conflicts) > 0
        assert report.overall_risk_score > 0.0

    def test_analysis_with_blocked_drain(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1"])
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        report = analyzer.analyze()
        assert report.drain_results[0].outcome == DrainOutcome.BLOCKED
        assert report.overall_risk_score > 0.0

    def test_analysis_risk_level_escalation(self):
        """Multiple conflicts and blocked drains should escalate risk."""
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1"])
        analyzer.set_node_assignment("node2", ["c2"])

        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        report = analyzer.analyze()
        assert report.overall_risk_level != RiskLevel.MINIMAL


# ============================================================================
# Utility Methods
# ============================================================================


class TestUtilityMethods:
    """Tests for utility query methods."""

    def test_get_blocked_components(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"], value=1,
            total_replicas=3, ready_replicas=3,
        ))
        blocked = analyzer.get_blocked_components()
        assert "c1" in blocked
        assert "c2" not in blocked

    def test_get_blocked_components_empty(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        assert analyzer.get_blocked_components() == []

    def test_safest_drain_order(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1"])
        analyzer.set_node_assignment("node2", ["c2"])
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        order = analyzer.get_safest_drain_order()
        assert len(order) == 2
        # node2 (no blocking) should come before node1 (blocked)
        assert order[0] == "node2"

    def test_safest_drain_order_empty(self):
        g = _graph()
        analyzer = PodDisruptionAnalyzer(g)
        assert analyzer.get_safest_drain_order() == []

    def test_pdb_coverage_ratio(self):
        g = _graph(_comp("c1"), _comp("c2"), _comp("c3"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["c1"]))
        assert analyzer.pdb_coverage_ratio() == pytest.approx(1 / 3)

    def test_pdb_coverage_ratio_full(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["c1", "c2"]))
        assert analyzer.pdb_coverage_ratio() == pytest.approx(1.0)

    def test_pdb_coverage_ratio_empty_graph(self):
        g = _graph()
        analyzer = PodDisruptionAnalyzer(g)
        assert analyzer.pdb_coverage_ratio() == 0.0

    def test_find_unprotected_components(self):
        g = _graph(_comp("c1"), _comp("c2"), _comp("c3"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["c1"]))
        unprotected = analyzer.find_unprotected_components()
        assert "c2" in unprotected
        assert "c3" in unprotected
        assert "c1" not in unprotected

    def test_count_by_workload_type(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"],
            workload_type=WorkloadType.DEPLOYMENT,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"],
            workload_type=WorkloadType.STATEFUL_SET,
        ))
        counts = analyzer.count_by_workload_type()
        assert counts["deployment"] == 1
        assert counts["stateful_set"] == 1

    def test_max_disruption_capacity(self):
        g = _graph(_comp("c1"), _comp("c2"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], total_replicas=5, value=2,
            ready_replicas=5,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c2"], total_replicas=3, value=1,
            ready_replicas=3,
        ))
        assert analyzer.max_disruption_capacity() == 3

    def test_summary(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["c1"]))
        s = analyzer.summary()
        assert s["total_pdbs"] == 1
        assert s["total_components"] == 1
        assert "blocked_pdbs" in s
        assert "total_allowed_disruptions" in s
        assert "conflicts" in s
        assert "average_risk_score" in s
        assert "coverage_ratio" in s

    def test_summary_empty(self):
        g = _graph()
        analyzer = PodDisruptionAnalyzer(g)
        s = analyzer.summary()
        assert s["total_pdbs"] == 0
        assert s["average_risk_score"] == 0.0


# ============================================================================
# Enum value tests
# ============================================================================


class TestEnums:
    """Test enum values are accessible and correct."""

    def test_pdb_policy_types(self):
        assert PDBPolicyType.MIN_AVAILABLE.value == "min_available"
        assert PDBPolicyType.MAX_UNAVAILABLE.value == "max_unavailable"

    def test_workload_types(self):
        assert WorkloadType.DEPLOYMENT.value == "deployment"
        assert WorkloadType.STATEFUL_SET.value == "stateful_set"
        assert WorkloadType.DAEMON_SET.value == "daemon_set"
        assert WorkloadType.REPLICA_SET.value == "replica_set"

    def test_disruption_severity(self):
        assert DisruptionSeverity.CRITICAL.value == "critical"
        assert DisruptionSeverity.INFO.value == "info"

    def test_conflict_categories(self):
        assert ConflictCategory.OVERLAPPING_SELECTOR.value == "overlapping_selector"
        assert ConflictCategory.STALE_SELECTOR.value == "stale_selector"

    def test_drain_outcomes(self):
        assert DrainOutcome.SUCCESS.value == "success"
        assert DrainOutcome.TIMEOUT.value == "timeout"

    def test_maintenance_strategies(self):
        assert MaintenanceStrategy.ROLLING.value == "rolling"
        assert MaintenanceStrategy.BIG_BANG.value == "big_bang"

    def test_risk_levels(self):
        assert RiskLevel.MINIMAL.value == "minimal"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_recommendation_priorities(self):
        assert RecommendationPriority.MUST.value == "must"
        assert RecommendationPriority.NICE_TO_HAVE.value == "nice_to_have"


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_zero_total_replicas(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=0, ready_replicas=0, value=0,
        ))
        budget = analyzer.evaluate_pdb_policy("p1")
        assert budget is not None
        assert budget.is_blocked is True

    def test_ready_greater_than_total(self):
        """Shouldn't happen in practice but should not crash."""
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=3, ready_replicas=5, value=1,
        ))
        budget = analyzer.evaluate_pdb_policy("p1")
        assert budget is not None

    def test_very_large_replica_count(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb(
            "p1", total_replicas=10000, ready_replicas=10000, value=100,
        ))
        budget = analyzer.evaluate_pdb_policy("p1")
        assert budget is not None
        assert budget.allowed_disruptions == 100

    def test_multiple_pdbs_same_component(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        for i in range(5):
            analyzer.add_pdb(_make_pdb(
                f"p{i}", component_ids=["c1"],
                total_replicas=10, ready_replicas=10, value=i + 1,
            ))
        budget = analyzer.calculate_eviction_budget("c1")
        assert budget is not None
        # Most restrictive: value=1 -> allowed=1
        assert budget.allowed_disruptions == 1

    def test_pdb_with_no_matching_graph_component(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.add_pdb(_make_pdb("p1", component_ids=["nonexistent"]))
        budget = analyzer.evaluate_pdb_policy("p1")
        assert budget is not None
        # The PDB still evaluates even if component is not in graph

    def test_percentage_100(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MAX_UNAVAILABLE,
            value=100, percentage=True, total_replicas=5,
        )
        assert _calculate_max_unavailable(spec) == 5

    def test_percentage_0_floors_to_1(self):
        spec = _make_pdb(
            policy_type=PDBPolicyType.MAX_UNAVAILABLE,
            value=0, percentage=True, total_replicas=5,
        )
        # floor(0) = 0 -> max(1, 0) = 1
        assert _calculate_max_unavailable(spec) == 1

    def test_drain_with_multiple_pdbs_on_same_pod(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        analyzer.set_node_assignment("node1", ["c1"])
        # One PDB allows, another blocks
        analyzer.add_pdb(_make_pdb(
            "p1", component_ids=["c1"], value=1,
            total_replicas=3, ready_replicas=3,
        ))
        analyzer.add_pdb(_make_pdb(
            "p2", component_ids=["c1"],
            policy_type=PDBPolicyType.MIN_AVAILABLE,
            value=3, total_replicas=3, ready_replicas=3,
        ))
        result = analyzer.simulate_node_drain("node1")
        # One PDB blocks => pod is blocked
        assert result.pods_blocked == 1

    def test_maintenance_recommendation_strings(self):
        g = _graph(_comp("c1"))
        analyzer = PodDisruptionAnalyzer(g)
        # Test all strategy paths
        assert "Rolling" in analyzer._maintenance_recommendation(
            MaintenanceStrategy.ROLLING, 0.8, 10,
        )
        assert "blue-green" in analyzer._maintenance_recommendation(
            MaintenanceStrategy.BLUE_GREEN, 0.1, 2,
        )
        assert "Canary" in analyzer._maintenance_recommendation(
            MaintenanceStrategy.CANARY, 0.3, 5,
        )
        assert "No disruptions" in analyzer._maintenance_recommendation(
            MaintenanceStrategy.BIG_BANG, 0.0, 0,
        )
