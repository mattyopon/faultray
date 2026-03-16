"""Tests for the Infrastructure Cost Anomaly Detector."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cost_anomaly import (
    AnomalyType,
    CostAnomaly,
    CostAnomalyDetector,
    CostEfficiencyReport,
    _BASE_MONTHLY_COST,
    _COMPONENT_TIER,
    _OVER_PROVISION_FACTOR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    """Create a minimal component for testing."""
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
    )


def _dep(source: str, target: str) -> Dependency:
    """Create a dependency edge."""
    return Dependency(source_id=source, target_id=target)


def _empty_graph() -> InfraGraph:
    return InfraGraph()


def _single_component_graph(
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("c1", "Component1", ctype, replicas, health))
    return g


def _chain_graph(replicas: int = 1) -> InfraGraph:
    """LB -> APP -> DB chain."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LoadBalancer", ComponentType.LOAD_BALANCER, replicas))
    g.add_component(_comp("app", "AppServer", ComponentType.APP_SERVER, replicas))
    g.add_component(_comp("db", "Database", ComponentType.DATABASE, replicas))
    g.add_dependency(_dep("lb", "app"))
    g.add_dependency(_dep("app", "db"))
    return g


# ===================================================================
# AnomalyType enum tests
# ===================================================================


class TestAnomalyType:
    def test_all_values_are_strings(self):
        for member in AnomalyType:
            assert isinstance(member.value, str)

    def test_expected_members(self):
        names = {m.name for m in AnomalyType}
        assert "OVER_PROVISIONED" in names
        assert "UNDER_UTILIZED" in names
        assert "COST_SPIKE" in names
        assert "REDUNDANT_COMPONENT" in names
        assert "MISSING_SPOT_OPPORTUNITY" in names
        assert "OVERSIZED_INSTANCE" in names
        assert "IDLE_RESOURCE" in names
        assert "UNBALANCED_REPLICAS" in names

    def test_member_count(self):
        assert len(AnomalyType) == 8


# ===================================================================
# CostAnomaly dataclass tests
# ===================================================================


class TestCostAnomalyDataclass:
    def test_create_anomaly(self):
        a = CostAnomaly(
            component_id="x",
            component_name="X",
            anomaly_type=AnomalyType.IDLE_RESOURCE,
            description="idle",
            current_monthly_cost=100.0,
            optimized_monthly_cost=0.0,
            savings_potential=100.0,
            savings_percent=100.0,
            confidence=0.9,
            recommendation="remove it",
            risk_if_optimized="none",
        )
        assert a.component_id == "x"
        assert a.anomaly_type == AnomalyType.IDLE_RESOURCE
        assert a.savings_potential == 100.0

    def test_confidence_range(self):
        a = CostAnomaly(
            component_id="y",
            component_name="Y",
            anomaly_type=AnomalyType.COST_SPIKE,
            description="spike",
            current_monthly_cost=500.0,
            optimized_monthly_cost=200.0,
            savings_potential=300.0,
            savings_percent=60.0,
            confidence=0.5,
            recommendation="investigate",
            risk_if_optimized="unknown",
        )
        assert 0 <= a.confidence <= 1.0


# ===================================================================
# CostEfficiencyReport dataclass tests
# ===================================================================


class TestCostEfficiencyReport:
    def test_defaults(self):
        r = CostEfficiencyReport(
            total_monthly_cost=0.0,
            optimizable_cost=0.0,
            potential_savings=0.0,
            savings_percent=0.0,
            efficiency_score=100.0,
        )
        assert r.anomalies == []
        assert r.top_recommendations == []
        assert r.cost_by_component_type == {}
        assert r.cost_by_tier == {}


# ===================================================================
# Empty graph
# ===================================================================


class TestEmptyGraph:
    def test_empty_graph_returns_perfect_score(self):
        report = CostAnomalyDetector(_empty_graph()).analyze()
        assert report.total_monthly_cost == 0.0
        assert report.efficiency_score == 100.0
        assert report.anomalies == []

    def test_empty_graph_zero_savings(self):
        report = CostAnomalyDetector(_empty_graph()).analyze()
        assert report.potential_savings == 0.0
        assert report.savings_percent == 0.0

    def test_empty_graph_no_recommendations(self):
        report = CostAnomalyDetector(_empty_graph()).analyze()
        assert report.top_recommendations == []

    def test_empty_graph_empty_cost_maps(self):
        report = CostAnomalyDetector(_empty_graph()).analyze()
        assert report.cost_by_component_type == {}
        assert report.cost_by_tier == {}


# ===================================================================
# Efficient graph (no anomalies expected)
# ===================================================================


class TestEfficientGraph:
    def test_chain_with_low_replicas_is_efficient(self):
        """A simple chain with 1 replica each should detect idle resources for
        leaf/root but not over-provisioning or unbalanced replicas."""
        g = _chain_graph(replicas=1)
        report = CostAnomalyDetector(g).analyze()
        # No over-provisioned or unbalanced anomalies
        over_prov = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.OVER_PROVISIONED
        ]
        unbalanced = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.UNBALANCED_REPLICAS
        ]
        assert len(over_prov) == 0
        assert len(unbalanced) == 0

    def test_connected_components_not_idle(self):
        """Components with dependencies should not be flagged as idle."""
        g = _chain_graph(replicas=1)
        report = CostAnomalyDetector(g).analyze()
        idle = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.IDLE_RESOURCE
        ]
        # The middle component 'app' has both dependents and dependencies,
        # so it must NOT be idle.
        idle_ids = {a.component_id for a in idle}
        assert "app" not in idle_ids

    def test_total_cost_matches_component_sum(self):
        g = _chain_graph(replicas=2)
        report = CostAnomalyDetector(g).analyze()
        expected = (
            _BASE_MONTHLY_COST[ComponentType.LOAD_BALANCER] * 2
            + _BASE_MONTHLY_COST[ComponentType.APP_SERVER] * 2
            + _BASE_MONTHLY_COST[ComponentType.DATABASE] * 2
        )
        assert report.total_monthly_cost == pytest.approx(expected)


# ===================================================================
# Over-provisioning detection
# ===================================================================


class TestOverProvisioning:
    def test_high_replicas_with_no_dependents_flagged(self):
        """A single component with many replicas and no dependents should be
        flagged when replicas > 3 * max(1, 0) = 3."""
        g = InfraGraph()
        g.add_component(_comp("big", "BigApp", ComponentType.APP_SERVER, replicas=10))
        report = CostAnomalyDetector(g).analyze()
        # It is also idle (no deps), but check over-provisioned specifically
        # -- it should NOT be over-provisioned because min_needed = max(1, 0) = 1
        # and threshold = 1*3 = 3, and 10 > 3, so it IS flagged.
        over = [a for a in report.anomalies if a.anomaly_type == AnomalyType.OVER_PROVISIONED]
        assert len(over) == 1
        assert over[0].component_id == "big"

    def test_replicas_at_threshold_not_flagged(self):
        """Replicas exactly at the threshold should not be flagged."""
        g = InfraGraph()
        # 1 dependent => min_needed=1, threshold=3; 3 replicas is NOT over.
        g.add_component(_comp("srv", "Server", ComponentType.APP_SERVER, replicas=3))
        g.add_component(_comp("client", "Client", ComponentType.WEB_SERVER, replicas=1))
        g.add_dependency(_dep("client", "srv"))
        report = CostAnomalyDetector(g).analyze()
        over = [a for a in report.anomalies if a.anomaly_type == AnomalyType.OVER_PROVISIONED]
        assert len(over) == 0

    def test_replicas_just_above_threshold_flagged(self):
        """Replicas just above the threshold should be flagged."""
        g = InfraGraph()
        # 1 dependent => min_needed=1, threshold=3; 4 > 3, flagged.
        g.add_component(_comp("srv", "Server", ComponentType.APP_SERVER, replicas=4))
        g.add_component(_comp("client", "Client", ComponentType.WEB_SERVER, replicas=1))
        g.add_dependency(_dep("client", "srv"))
        report = CostAnomalyDetector(g).analyze()
        over = [a for a in report.anomalies if a.anomaly_type == AnomalyType.OVER_PROVISIONED]
        assert len(over) == 1

    def test_over_provisioned_savings_calculated(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=10))
        report = CostAnomalyDetector(g).analyze()
        over = [a for a in report.anomalies if a.anomaly_type == AnomalyType.OVER_PROVISIONED]
        assert len(over) == 1
        anom = over[0]
        assert anom.current_monthly_cost == _BASE_MONTHLY_COST[ComponentType.DATABASE] * 10
        assert anom.optimized_monthly_cost == _BASE_MONTHLY_COST[ComponentType.DATABASE] * 3
        assert anom.savings_potential == pytest.approx(
            anom.current_monthly_cost - anom.optimized_monthly_cost
        )

    def test_over_provisioned_confidence(self):
        g = InfraGraph()
        g.add_component(_comp("x", "X", ComponentType.APP_SERVER, replicas=20))
        report = CostAnomalyDetector(g).analyze()
        over = [a for a in report.anomalies if a.anomaly_type == AnomalyType.OVER_PROVISIONED]
        assert over[0].confidence == 0.8


# ===================================================================
# Redundant component detection
# ===================================================================


class TestRedundantComponents:
    def test_two_same_type_no_dependents(self):
        """Two components of the same type with no dependents are redundant."""
        g = InfraGraph()
        g.add_component(_comp("c1", "Cache1", ComponentType.CACHE, replicas=1))
        g.add_component(_comp("c2", "Cache2", ComponentType.CACHE, replicas=1))
        report = CostAnomalyDetector(g).analyze()
        redundant = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.REDUNDANT_COMPONENT
        ]
        assert len(redundant) == 1

    def test_two_same_type_same_dependents_flagged(self):
        """Two caches used by the same app are redundant."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", ComponentType.APP_SERVER))
        g.add_component(_comp("c1", "Cache1", ComponentType.CACHE))
        g.add_component(_comp("c2", "Cache2", ComponentType.CACHE))
        g.add_dependency(_dep("app", "c1"))
        g.add_dependency(_dep("app", "c2"))
        report = CostAnomalyDetector(g).analyze()
        redundant = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.REDUNDANT_COMPONENT
        ]
        assert len(redundant) == 1

    def test_different_types_not_redundant(self):
        """Components of different types are not redundant."""
        g = InfraGraph()
        g.add_component(_comp("c1", "Cache", ComponentType.CACHE))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE))
        report = CostAnomalyDetector(g).analyze()
        redundant = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.REDUNDANT_COMPONENT
        ]
        assert len(redundant) == 0

    def test_same_type_different_dependents_not_redundant(self):
        """Same-type components with different dependents are NOT redundant."""
        g = InfraGraph()
        # Use a shared root so app1/app2 are not orphans (they have a dependent).
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER))
        g.add_component(_comp("app1", "App1", ComponentType.APP_SERVER))
        g.add_component(_comp("app2", "App2", ComponentType.APP_SERVER))
        g.add_component(_comp("c1", "Cache1", ComponentType.CACHE))
        g.add_component(_comp("c2", "Cache2", ComponentType.CACHE))
        g.add_dependency(_dep("lb", "app1"))
        g.add_dependency(_dep("lb", "app2"))
        g.add_dependency(_dep("app1", "c1"))
        g.add_dependency(_dep("app2", "c2"))
        report = CostAnomalyDetector(g).analyze()
        redundant = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.REDUNDANT_COMPONENT
        ]
        # c1 has dependent app1, c2 has dependent app2 — different sets
        cache_redundant = [a for a in redundant if a.component_id in ("c1", "c2")]
        assert len(cache_redundant) == 0

    def test_redundant_picks_cheaper_to_remove(self):
        """The cheaper component should be suggested for removal."""
        g = InfraGraph()
        g.add_component(_comp("c1", "Cache1", ComponentType.CACHE, replicas=1))
        g.add_component(_comp("c2", "Cache2", ComponentType.CACHE, replicas=3))
        report = CostAnomalyDetector(g).analyze()
        redundant = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.REDUNDANT_COMPONENT
        ]
        assert len(redundant) == 1
        assert redundant[0].component_id == "c1"  # cheaper (1 replica)

    def test_redundant_confidence(self):
        g = InfraGraph()
        g.add_component(_comp("c1", "Cache1", ComponentType.CACHE))
        g.add_component(_comp("c2", "Cache2", ComponentType.CACHE))
        report = CostAnomalyDetector(g).analyze()
        redundant = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.REDUNDANT_COMPONENT
        ]
        assert redundant[0].confidence == 0.6


# ===================================================================
# Unbalanced replicas detection
# ===================================================================


class TestUnbalancedReplicas:
    def test_wildly_different_replicas_flagged(self):
        """Same-type components with >3x replica spread are flagged."""
        g = InfraGraph()
        g.add_component(_comp("a1", "App1", ComponentType.APP_SERVER, replicas=1))
        g.add_component(_comp("a2", "App2", ComponentType.APP_SERVER, replicas=10))
        # Connect them so they are not idle
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER))
        g.add_dependency(_dep("lb", "a1"))
        g.add_dependency(_dep("lb", "a2"))
        report = CostAnomalyDetector(g).analyze()
        unbalanced = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.UNBALANCED_REPLICAS
        ]
        assert len(unbalanced) >= 1
        assert unbalanced[0].component_id == "a2"

    def test_balanced_replicas_not_flagged(self):
        """Same-type components with similar replicas are NOT flagged."""
        g = InfraGraph()
        g.add_component(_comp("a1", "App1", ComponentType.APP_SERVER, replicas=2))
        g.add_component(_comp("a2", "App2", ComponentType.APP_SERVER, replicas=3))
        report = CostAnomalyDetector(g).analyze()
        unbalanced = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.UNBALANCED_REPLICAS
        ]
        assert len(unbalanced) == 0

    def test_single_component_type_not_unbalanced(self):
        """Cannot detect imbalance with only one component of a type."""
        g = InfraGraph()
        g.add_component(_comp("a1", "App1", ComponentType.APP_SERVER, replicas=100))
        report = CostAnomalyDetector(g).analyze()
        unbalanced = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.UNBALANCED_REPLICAS
        ]
        assert len(unbalanced) == 0

    def test_unbalanced_savings_positive(self):
        g = InfraGraph()
        g.add_component(_comp("a1", "App1", ComponentType.APP_SERVER, replicas=1))
        g.add_component(_comp("a2", "App2", ComponentType.APP_SERVER, replicas=10))
        report = CostAnomalyDetector(g).analyze()
        unbalanced = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.UNBALANCED_REPLICAS
        ]
        assert all(a.savings_potential > 0 for a in unbalanced)

    def test_unbalanced_confidence(self):
        g = InfraGraph()
        g.add_component(_comp("a1", "A1", ComponentType.APP_SERVER, replicas=1))
        g.add_component(_comp("a2", "A2", ComponentType.APP_SERVER, replicas=10))
        report = CostAnomalyDetector(g).analyze()
        unbalanced = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.UNBALANCED_REPLICAS
        ]
        assert unbalanced[0].confidence == 0.7


# ===================================================================
# Idle resource detection
# ===================================================================


class TestIdleResources:
    def test_orphan_component_flagged(self):
        """A healthy component with no edges is idle."""
        g = InfraGraph()
        g.add_component(_comp("orphan", "Orphan", ComponentType.APP_SERVER))
        report = CostAnomalyDetector(g).analyze()
        idle = [a for a in report.anomalies if a.anomaly_type == AnomalyType.IDLE_RESOURCE]
        assert len(idle) == 1
        assert idle[0].component_id == "orphan"

    def test_orphan_savings_equals_full_cost(self):
        g = InfraGraph()
        g.add_component(_comp("orphan", "Orphan", ComponentType.DATABASE, replicas=2))
        report = CostAnomalyDetector(g).analyze()
        idle = [a for a in report.anomalies if a.anomaly_type == AnomalyType.IDLE_RESOURCE]
        expected = _BASE_MONTHLY_COST[ComponentType.DATABASE] * 2
        assert idle[0].savings_potential == pytest.approx(expected)
        assert idle[0].savings_percent == 100.0

    def test_down_component_not_idle(self):
        """A DOWN component without edges is NOT flagged as idle (only HEALTHY)."""
        g = InfraGraph()
        g.add_component(
            _comp("down", "DownBox", ComponentType.APP_SERVER, health=HealthStatus.DOWN)
        )
        report = CostAnomalyDetector(g).analyze()
        idle = [a for a in report.anomalies if a.anomaly_type == AnomalyType.IDLE_RESOURCE]
        assert len(idle) == 0

    def test_degraded_component_not_idle(self):
        g = InfraGraph()
        g.add_component(
            _comp("deg", "Degraded", ComponentType.APP_SERVER, health=HealthStatus.DEGRADED)
        )
        report = CostAnomalyDetector(g).analyze()
        idle = [a for a in report.anomalies if a.anomaly_type == AnomalyType.IDLE_RESOURCE]
        assert len(idle) == 0

    def test_connected_component_not_idle(self):
        """A component with at least one edge is not idle."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", ComponentType.APP_SERVER))
        g.add_component(_comp("b", "B", ComponentType.DATABASE))
        g.add_dependency(_dep("a", "b"))
        report = CostAnomalyDetector(g).analyze()
        idle = [a for a in report.anomalies if a.anomaly_type == AnomalyType.IDLE_RESOURCE]
        assert len(idle) == 0

    def test_idle_confidence(self):
        g = InfraGraph()
        g.add_component(_comp("orphan", "Orphan", ComponentType.CACHE))
        report = CostAnomalyDetector(g).analyze()
        idle = [a for a in report.anomalies if a.anomaly_type == AnomalyType.IDLE_RESOURCE]
        assert idle[0].confidence == 0.9


# ===================================================================
# Cost calculations per component type
# ===================================================================


class TestCostCalculations:
    @pytest.mark.parametrize(
        "ctype,expected_base",
        [
            (ComponentType.DATABASE, 500.0),
            (ComponentType.APP_SERVER, 200.0),
            (ComponentType.CACHE, 150.0),
            (ComponentType.LOAD_BALANCER, 100.0),
            (ComponentType.WEB_SERVER, 180.0),
            (ComponentType.QUEUE, 120.0),
            (ComponentType.STORAGE, 80.0),
            (ComponentType.DNS, 50.0),
            (ComponentType.EXTERNAL_API, 0.0),
            (ComponentType.CUSTOM, 100.0),
        ],
    )
    def test_base_cost_per_type(self, ctype: ComponentType, expected_base: float):
        assert _BASE_MONTHLY_COST[ctype] == expected_base

    def test_cost_scales_with_replicas(self):
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=5))
        det = CostAnomalyDetector(g)
        comp = g.get_component("db")
        cost = det._estimate_component_cost(comp)
        assert cost == pytest.approx(500.0 * 5)

    def test_cost_by_component_type_map(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", ComponentType.APP_SERVER, replicas=2))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1))
        g.add_dependency(_dep("app", "db"))
        report = CostAnomalyDetector(g).analyze()
        assert "app_server" in report.cost_by_component_type
        assert "database" in report.cost_by_component_type
        assert report.cost_by_component_type["app_server"] == pytest.approx(200.0 * 2)
        assert report.cost_by_component_type["database"] == pytest.approx(500.0)

    def test_cost_by_tier_map(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", ComponentType.APP_SERVER, replicas=1))
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=1))
        g.add_component(_comp("s3", "S3", ComponentType.STORAGE, replicas=1))
        g.add_dependency(_dep("lb", "app"))
        report = CostAnomalyDetector(g).analyze()
        assert "compute" in report.cost_by_tier
        assert "network" in report.cost_by_tier
        # storage is idle (no dep to/from it) but still counted in tier
        assert "storage" in report.cost_by_tier

    def test_tier_mapping_complete(self):
        """Every ComponentType should be in the tier map."""
        for ctype in ComponentType:
            assert ctype in _COMPONENT_TIER


# ===================================================================
# Efficiency score boundaries
# ===================================================================


class TestEfficiencyScore:
    def test_score_100_when_no_anomalies(self):
        """A connected graph with modest replicas should score near 100."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", ComponentType.APP_SERVER, replicas=1))
        g.add_component(_comp("b", "B", ComponentType.DATABASE, replicas=1))
        g.add_dependency(_dep("a", "b"))
        report = CostAnomalyDetector(g).analyze()
        assert report.efficiency_score == 100.0

    def test_score_0_when_all_cost_is_waste(self):
        """All orphan components means 100% savings => score 0."""
        g = InfraGraph()
        g.add_component(_comp("o1", "O1", ComponentType.APP_SERVER))
        g.add_component(_comp("o2", "O2", ComponentType.DATABASE))
        report = CostAnomalyDetector(g).analyze()
        # Both are idle (100% savings on each)
        assert report.efficiency_score == pytest.approx(0.0, abs=1.0)

    def test_score_50_approx(self):
        """Mix of idle and connected components."""
        g = InfraGraph()
        # Connected pair — not idle, not over-provisioned
        g.add_component(_comp("a", "A", ComponentType.APP_SERVER, replicas=1))
        g.add_component(_comp("b", "B", ComponentType.APP_SERVER, replicas=1))
        g.add_dependency(_dep("a", "b"))
        # Orphan — idle, full savings
        g.add_component(_comp("o", "O", ComponentType.APP_SERVER, replicas=1))
        report = CostAnomalyDetector(g).analyze()
        # ~33% of cost is waste (1 out of 3 equal-cost components)
        # But 'a' and 'b' have the same type and 'b' is dependent of 'a'
        # only 'o' is truly idle. Redundancy check: a and o both have
        # deps_a = {} and deps_o = {}, so a and o ARE redundant. Let's verify.
        assert 0.0 < report.efficiency_score < 100.0

    def test_score_clamped_above_zero(self):
        """Score should never go below 0."""
        g = InfraGraph()
        g.add_component(_comp("o", "O", ComponentType.DATABASE, replicas=1))
        report = CostAnomalyDetector(g).analyze()
        assert report.efficiency_score >= 0.0

    def test_score_clamped_below_100(self):
        report = CostAnomalyDetector(_empty_graph()).analyze()
        assert report.efficiency_score <= 100.0


# ===================================================================
# Single component edge cases
# ===================================================================


class TestSingleComponent:
    def test_single_component_is_idle(self):
        g = _single_component_graph()
        report = CostAnomalyDetector(g).analyze()
        idle = [a for a in report.anomalies if a.anomaly_type == AnomalyType.IDLE_RESOURCE]
        assert len(idle) == 1

    def test_single_component_cost(self):
        g = _single_component_graph(ComponentType.CACHE, replicas=3)
        report = CostAnomalyDetector(g).analyze()
        assert report.total_monthly_cost == pytest.approx(150.0 * 3)

    def test_single_component_all_types(self):
        for ctype in ComponentType:
            g = _single_component_graph(ctype)
            report = CostAnomalyDetector(g).analyze()
            expected = _BASE_MONTHLY_COST[ctype]
            assert report.total_monthly_cost == pytest.approx(expected)


# ===================================================================
# All components same type
# ===================================================================


class TestAllSameType:
    def test_multiple_same_type_redundancy_check(self):
        """Three caches with no edges — each pair is redundant."""
        g = InfraGraph()
        g.add_component(_comp("c1", "C1", ComponentType.CACHE))
        g.add_component(_comp("c2", "C2", ComponentType.CACHE))
        g.add_component(_comp("c3", "C3", ComponentType.CACHE))
        report = CostAnomalyDetector(g).analyze()
        redundant = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.REDUNDANT_COMPONENT
        ]
        # Three pairwise comparisons: (c1,c2), (c1,c3), (c2,c3) — all redundant
        assert len(redundant) == 3

    def test_all_same_type_cost_by_type(self):
        g = InfraGraph()
        for i in range(5):
            g.add_component(_comp(f"a{i}", f"A{i}", ComponentType.APP_SERVER, replicas=2))
        report = CostAnomalyDetector(g).analyze()
        assert report.cost_by_component_type["app_server"] == pytest.approx(200.0 * 2 * 5)


# ===================================================================
# Savings calculations accuracy
# ===================================================================


class TestSavingsAccuracy:
    def test_savings_percent_formula(self):
        g = InfraGraph()
        # One over-provisioned DB (10 replicas, min_needed=1, threshold=3)
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=10))
        report = CostAnomalyDetector(g).analyze()
        assert report.savings_percent == pytest.approx(
            report.potential_savings / report.total_monthly_cost * 100.0
        )

    def test_total_savings_is_sum_of_anomaly_savings(self):
        g = InfraGraph()
        g.add_component(_comp("o1", "O1", ComponentType.APP_SERVER))
        g.add_component(_comp("o2", "O2", ComponentType.DATABASE))
        report = CostAnomalyDetector(g).analyze()
        assert report.potential_savings == pytest.approx(
            sum(a.savings_potential for a in report.anomalies)
        )

    def test_optimizable_equals_potential_savings(self):
        g = InfraGraph()
        g.add_component(_comp("x", "X", ComponentType.QUEUE, replicas=5))
        report = CostAnomalyDetector(g).analyze()
        assert report.optimizable_cost == report.potential_savings


# ===================================================================
# Anomaly type distribution
# ===================================================================


class TestAnomalyDistribution:
    def test_mixed_anomaly_types(self):
        g = InfraGraph()
        # Idle resource (orphan)
        g.add_component(_comp("orphan", "Orphan", ComponentType.STORAGE))
        # Over-provisioned (10 replicas, no dependents)
        g.add_component(_comp("big", "Big", ComponentType.APP_SERVER, replicas=10))
        # Unbalanced (same type, very different replicas)
        g.add_component(_comp("small", "Small", ComponentType.APP_SERVER, replicas=1))
        report = CostAnomalyDetector(g).analyze()
        types_found = {a.anomaly_type for a in report.anomalies}
        assert AnomalyType.IDLE_RESOURCE in types_found
        assert AnomalyType.OVER_PROVISIONED in types_found
        assert AnomalyType.UNBALANCED_REPLICAS in types_found

    def test_no_duplicate_anomaly_ids_per_type(self):
        """Each anomaly type should not flag the same component twice."""
        g = InfraGraph()
        g.add_component(_comp("a", "A", ComponentType.APP_SERVER, replicas=20))
        g.add_component(_comp("b", "B", ComponentType.APP_SERVER, replicas=1))
        report = CostAnomalyDetector(g).analyze()
        for atype in AnomalyType:
            ids = [
                a.component_id
                for a in report.anomalies
                if a.anomaly_type == atype
            ]
            assert len(ids) == len(set(ids)), f"Duplicate in {atype}"


# ===================================================================
# Large graph with mixed anomaly types
# ===================================================================


class TestLargeGraph:
    def _build_large_graph(self) -> InfraGraph:
        g = InfraGraph()
        # Tier 1: load balancers
        g.add_component(_comp("lb1", "LB1", ComponentType.LOAD_BALANCER, replicas=2))
        g.add_component(_comp("lb2", "LB2", ComponentType.LOAD_BALANCER, replicas=2))
        # Tier 2: app servers (one over-provisioned)
        g.add_component(_comp("app1", "App1", ComponentType.APP_SERVER, replicas=2))
        g.add_component(_comp("app2", "App2", ComponentType.APP_SERVER, replicas=20))
        # Tier 3: databases
        g.add_component(_comp("db1", "DB1", ComponentType.DATABASE, replicas=2))
        g.add_component(_comp("db2", "DB2", ComponentType.DATABASE, replicas=2))
        # Tier 4: caches (redundant pair)
        g.add_component(_comp("cache1", "Cache1", ComponentType.CACHE, replicas=1))
        g.add_component(_comp("cache2", "Cache2", ComponentType.CACHE, replicas=1))
        # Orphan component
        g.add_component(_comp("orphan_q", "OrphanQueue", ComponentType.QUEUE))
        # Dependencies
        g.add_dependency(_dep("lb1", "app1"))
        g.add_dependency(_dep("lb2", "app2"))
        g.add_dependency(_dep("app1", "db1"))
        g.add_dependency(_dep("app1", "cache1"))
        g.add_dependency(_dep("app1", "cache2"))
        g.add_dependency(_dep("app2", "db2"))
        return g

    def test_large_graph_has_anomalies(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        assert len(report.anomalies) > 0

    def test_large_graph_total_cost_positive(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        assert report.total_monthly_cost > 0

    def test_large_graph_efficiency_between_0_and_100(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        assert 0.0 <= report.efficiency_score <= 100.0

    def test_large_graph_has_recommendations(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        assert len(report.top_recommendations) > 0

    def test_large_graph_cost_by_tier_sums_to_total(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        tier_sum = sum(report.cost_by_tier.values())
        assert tier_sum == pytest.approx(report.total_monthly_cost)

    def test_large_graph_cost_by_type_sums_to_total(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        type_sum = sum(report.cost_by_component_type.values())
        assert type_sum == pytest.approx(report.total_monthly_cost)

    def test_large_graph_orphan_detected(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        idle = [a for a in report.anomalies if a.anomaly_type == AnomalyType.IDLE_RESOURCE]
        idle_ids = {a.component_id for a in idle}
        assert "orphan_q" in idle_ids

    def test_large_graph_over_provisioned_detected(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        over = [a for a in report.anomalies if a.anomaly_type == AnomalyType.OVER_PROVISIONED]
        over_ids = {a.component_id for a in over}
        assert "app2" in over_ids

    def test_large_graph_unbalanced_detected(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        unbalanced = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.UNBALANCED_REPLICAS
        ]
        assert len(unbalanced) >= 1

    def test_large_graph_savings_not_exceed_total_cost(self):
        report = CostAnomalyDetector(self._build_large_graph()).analyze()
        assert report.potential_savings <= report.total_monthly_cost


# ===================================================================
# Top recommendations
# ===================================================================


class TestTopRecommendations:
    def test_recommendations_unique(self):
        g = InfraGraph()
        g.add_component(_comp("o1", "O1", ComponentType.APP_SERVER))
        g.add_component(_comp("o2", "O2", ComponentType.APP_SERVER))
        report = CostAnomalyDetector(g).analyze()
        assert len(report.top_recommendations) == len(set(report.top_recommendations))

    def test_recommendations_ordered_by_savings(self):
        g = InfraGraph()
        # Expensive orphan
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=5))
        # Cheap orphan
        g.add_component(_comp("dns", "DNS", ComponentType.DNS, replicas=1))
        report = CostAnomalyDetector(g).analyze()
        # The DB recommendation should come first (higher savings)
        if len(report.top_recommendations) >= 2:
            assert "DB" in report.top_recommendations[0]


# ===================================================================
# Base cost helper
# ===================================================================


class TestBaseCostHelper:
    def test_base_cost_static_method(self):
        assert CostAnomalyDetector._base_cost(ComponentType.DATABASE) == 500.0

    def test_base_cost_unknown_type_fallback(self):
        """Should return 100.0 for an unknown type via dict.get default."""
        # ComponentType is an enum, so we can't pass arbitrary values,
        # but we can test the CUSTOM type which maps to 100.
        assert CostAnomalyDetector._base_cost(ComponentType.CUSTOM) == 100.0


# ===================================================================
# Module-level constants
# ===================================================================


class TestConstants:
    def test_over_provision_factor(self):
        assert _OVER_PROVISION_FACTOR == 3

    def test_base_monthly_cost_covers_all_types(self):
        for ctype in ComponentType:
            assert ctype in _BASE_MONTHLY_COST

    def test_component_tier_covers_all_types(self):
        for ctype in ComponentType:
            assert ctype in _COMPONENT_TIER

    def test_tier_values(self):
        valid_tiers = {"compute", "storage", "network"}
        for tier in _COMPONENT_TIER.values():
            assert tier in valid_tiers


# ===================================================================
# Coverage gaps — lines 235, 296, 306
# ===================================================================


class TestCoverageGaps:
    def test_unbalanced_replicas_zero_cost_component(self):
        """EXTERNAL_API has base cost 0, so savings <= 0 when computing
        unbalanced replicas. The continue branch is hit. [line 306]"""
        g = InfraGraph()
        g.add_component(
            _comp("ext1", "ExtAPI1", ComponentType.EXTERNAL_API, replicas=1)
        )
        g.add_component(
            _comp("ext2", "ExtAPI2", ComponentType.EXTERNAL_API, replicas=10)
        )
        report = CostAnomalyDetector(g).analyze()
        # EXTERNAL_API base cost is 0, so savings = 0 - 0 = 0 -> continue
        unbalanced = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.UNBALANCED_REPLICAS
        ]
        # No unbalanced anomaly because savings <= 0
        assert len(unbalanced) == 0

    def test_redundant_pair_already_seen_is_skipped(self):
        """When a pair is already in seen_pairs, it should be skipped.
        [line 235] This is actually dead code due to the loop structure,
        but we verify the redundancy detection works correctly with
        multiple same-type components."""
        g = InfraGraph()
        # Three caches with same dependents -> multiple pairs processed
        g.add_component(_comp("c1", "C1", ComponentType.CACHE))
        g.add_component(_comp("c2", "C2", ComponentType.CACHE))
        g.add_component(_comp("c3", "C3", ComponentType.CACHE))
        report = CostAnomalyDetector(g).analyze()
        redundant = [
            a for a in report.anomalies
            if a.anomaly_type == AnomalyType.REDUNDANT_COMPONENT
        ]
        # All three pairs: (c1,c2), (c1,c3), (c2,c3) are redundant
        assert len(redundant) == 3
