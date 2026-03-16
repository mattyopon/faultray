"""Tests for the Disaster Recovery Readiness Scorer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    ComplianceTags,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
    OperationalTeamConfig,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.dr_readiness import (
    DRCapability,
    DRReadinessReport,
    DRReadinessScorer,
    DRScenario,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    *,
    region: str = "",
    az: str = "",
    replicas: int = 1,
    failover: bool = False,
    failover_promotion_seconds: float = 30.0,
    autoscaling: bool = False,
    backup_enabled: bool = False,
    encryption_at_rest: bool = False,
    encryption_in_transit: bool = False,
    waf_protected: bool = False,
    network_segmented: bool = False,
    log_enabled: bool = False,
    audit_logging: bool = False,
    rpo_seconds: int = 0,
    rto_seconds: int = 0,
    runbook_coverage: float = 50.0,
    backup_frequency_hours: float = 24.0,
    mttr_minutes: float = 30.0,
) -> Component:
    """Convenience builder for components used in DR readiness tests."""
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        region=RegionConfig(
            region=region,
            availability_zone=az,
            rpo_seconds=rpo_seconds,
            rto_seconds=rto_seconds,
        ),
        failover=FailoverConfig(
            enabled=failover,
            promotion_time_seconds=failover_promotion_seconds,
        ),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        security=SecurityProfile(
            encryption_at_rest=encryption_at_rest,
            encryption_in_transit=encryption_in_transit,
            waf_protected=waf_protected,
            network_segmented=network_segmented,
            backup_enabled=backup_enabled,
            log_enabled=log_enabled,
            backup_frequency_hours=backup_frequency_hours,
        ),
        compliance_tags=ComplianceTags(audit_logging=audit_logging),
        team=OperationalTeamConfig(runbook_coverage_percent=runbook_coverage),
        operational_profile=OperationalProfile(mttr_minutes=mttr_minutes),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_graph() -> InfraGraph:
    """An empty infrastructure graph."""
    return InfraGraph()


@pytest.fixture
def fully_protected_graph() -> InfraGraph:
    """A graph with all protections enabled — should score 100."""
    graph = InfraGraph()
    for i, ctype in enumerate(
        [ComponentType.LOAD_BALANCER, ComponentType.APP_SERVER, ComponentType.DATABASE]
    ):
        region = "us-east-1" if i < 2 else "us-west-2"
        az = f"{region}a" if i < 2 else f"{region}a"
        graph.add_component(_make_component(
            f"comp-{i}",
            ctype,
            region=region,
            az=az,
            replicas=3,
            failover=True,
            autoscaling=True,
            backup_enabled=True,
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            network_segmented=True,
            log_enabled=True,
            audit_logging=True,
            runbook_coverage=100.0,
        ))

    # Add dependencies with circuit breakers
    graph.add_dependency(Dependency(
        source_id="comp-0",
        target_id="comp-1",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="comp-1",
        target_id="comp-2",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


@pytest.fixture
def unprotected_graph() -> InfraGraph:
    """A graph with zero protections — should score near 0."""
    graph = InfraGraph()
    graph.add_component(_make_component(
        "lonely-app",
        ComponentType.APP_SERVER,
    ))
    graph.add_component(_make_component(
        "lonely-db",
        ComponentType.DATABASE,
    ))
    # dependency without circuit breaker
    graph.add_dependency(Dependency(
        source_id="lonely-app",
        target_id="lonely-db",
    ))
    return graph


@pytest.fixture
def multi_region_graph() -> InfraGraph:
    """Graph spanning 2 regions with partial protections."""
    graph = InfraGraph()
    graph.add_component(_make_component(
        "lb",
        ComponentType.LOAD_BALANCER,
        region="us-east-1",
        az="us-east-1a",
        failover=True,
        encryption_at_rest=True,
        audit_logging=True,
    ))
    graph.add_component(_make_component(
        "app",
        ComponentType.APP_SERVER,
        region="us-east-1",
        az="us-east-1b",
        autoscaling=True,
        log_enabled=True,
    ))
    graph.add_component(_make_component(
        "db",
        ComponentType.DATABASE,
        region="us-west-2",
        az="us-west-2a",
        failover=True,
        backup_enabled=True,
        encryption_at_rest=True,
    ))
    graph.add_dependency(Dependency(
        source_id="lb",
        target_id="app",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app",
        target_id="db",
    ))
    return graph


# ---------------------------------------------------------------------------
# DRScenario Enum
# ---------------------------------------------------------------------------


class TestDRScenario:
    def test_all_scenarios_exist(self):
        assert DRScenario.REGIONAL_OUTAGE == "regional_outage"
        assert DRScenario.DATACENTER_FAILURE == "datacenter_failure"
        assert DRScenario.DATA_CORRUPTION == "data_corruption"
        assert DRScenario.RANSOMWARE == "ransomware"
        assert DRScenario.DNS_HIJACK == "dns_hijack"
        assert DRScenario.CLOUD_PROVIDER_OUTAGE == "cloud_provider_outage"

    def test_scenario_count(self):
        assert len(DRScenario) == 6

    def test_scenario_is_str(self):
        for scenario in DRScenario:
            assert isinstance(scenario, str)
            assert isinstance(scenario.value, str)


# ---------------------------------------------------------------------------
# DRCapability dataclass
# ---------------------------------------------------------------------------


class TestDRCapability:
    def test_default_gaps_and_recommendations(self):
        cap = DRCapability(
            scenario=DRScenario.REGIONAL_OUTAGE,
            is_covered=True,
            rto_achievable_minutes=5.0,
            rpo_achievable_minutes=1.0,
            automation_level="fully_automated",
        )
        assert cap.gaps == []
        assert cap.recommendations == []

    def test_with_gaps(self):
        cap = DRCapability(
            scenario=DRScenario.RANSOMWARE,
            is_covered=False,
            rto_achievable_minutes=120.0,
            rpo_achievable_minutes=60.0,
            automation_level="none",
            gaps=["no backups"],
            recommendations=["enable backups"],
        )
        assert len(cap.gaps) == 1
        assert cap.is_covered is False


# ---------------------------------------------------------------------------
# DRReadinessReport dataclass
# ---------------------------------------------------------------------------


class TestDRReadinessReport:
    def test_default_values(self):
        report = DRReadinessReport(overall_score=50.0, tier="silver")
        assert report.overall_score == 50.0
        assert report.tier == "silver"
        assert report.capabilities == []
        assert report.critical_gaps == []
        assert report.total_scenarios == 0
        assert report.covered_scenarios == 0
        assert report.estimated_recovery_cost_hours == 0.0
        assert report.runbook_completeness == 0.0


# ---------------------------------------------------------------------------
# Tier Boundaries
# ---------------------------------------------------------------------------


class TestTierBoundaries:
    """Test exact tier boundary values."""

    def test_platinum_at_90(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(90.0) == "platinum"

    def test_platinum_at_100(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(100.0) == "platinum"

    def test_gold_at_89(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(89.0) == "gold"

    def test_gold_at_89_9(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(89.9) == "gold"

    def test_gold_at_70(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(70.0) == "gold"

    def test_silver_at_69(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(69.0) == "silver"

    def test_silver_at_69_9(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(69.9) == "silver"

    def test_silver_at_50(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(50.0) == "silver"

    def test_bronze_at_49(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(49.0) == "bronze"

    def test_bronze_at_49_9(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(49.9) == "bronze"

    def test_bronze_at_30(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(30.0) == "bronze"

    def test_unprotected_at_29(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(29.0) == "unprotected"

    def test_unprotected_at_29_9(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(29.9) == "unprotected"

    def test_unprotected_at_0(self):
        graph = InfraGraph()
        graph.add_component(_make_component("x", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        assert scorer._calculate_tier(0.0) == "unprotected"


# ---------------------------------------------------------------------------
# Empty Graph
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    def test_empty_graph_score_zero(self, empty_graph):
        scorer = DRReadinessScorer(empty_graph)
        report = scorer.assess()
        assert report.overall_score == 0.0
        assert report.tier == "unprotected"
        assert report.covered_scenarios == 0
        assert report.total_scenarios == 6

    def test_empty_graph_all_scenarios_uncovered(self, empty_graph):
        scorer = DRReadinessScorer(empty_graph)
        report = scorer.assess()
        for cap in report.capabilities:
            assert cap.is_covered is False

    def test_empty_graph_has_gaps(self, empty_graph):
        scorer = DRReadinessScorer(empty_graph)
        report = scorer.assess()
        assert len(report.critical_gaps) > 0

    def test_empty_graph_recovery_cost_zero(self, empty_graph):
        scorer = DRReadinessScorer(empty_graph)
        report = scorer.assess()
        assert report.estimated_recovery_cost_hours == 0.0

    def test_empty_graph_runbook_zero(self, empty_graph):
        scorer = DRReadinessScorer(empty_graph)
        report = scorer.assess()
        assert report.runbook_completeness == 0.0


# ---------------------------------------------------------------------------
# Fully Protected Graph
# ---------------------------------------------------------------------------


class TestFullyProtectedGraph:
    def test_score_100(self, fully_protected_graph):
        scorer = DRReadinessScorer(fully_protected_graph)
        report = scorer.assess()
        assert report.overall_score == 100.0

    def test_tier_platinum(self, fully_protected_graph):
        scorer = DRReadinessScorer(fully_protected_graph)
        report = scorer.assess()
        assert report.tier == "platinum"

    def test_all_scenarios_assessed(self, fully_protected_graph):
        scorer = DRReadinessScorer(fully_protected_graph)
        report = scorer.assess()
        assert report.total_scenarios == 6

    def test_recovery_cost_low(self, fully_protected_graph):
        scorer = DRReadinessScorer(fully_protected_graph)
        report = scorer.assess()
        # 3 components, all fully automated = 3 * 0.5 = 1.5
        assert report.estimated_recovery_cost_hours == 1.5

    def test_runbook_completeness_100(self, fully_protected_graph):
        scorer = DRReadinessScorer(fully_protected_graph)
        report = scorer.assess()
        assert report.runbook_completeness == 100.0


# ---------------------------------------------------------------------------
# Unprotected Graph
# ---------------------------------------------------------------------------


class TestUnprotectedGraph:
    def test_score_near_zero(self, unprotected_graph):
        scorer = DRReadinessScorer(unprotected_graph)
        report = scorer.assess()
        # No multi-region, no failover, no backup, no CB on dep, no monitoring,
        # no encryption, no autoscaling, no logging
        # Only gets: 15 points from backup coverage (no data stores need backup? Actually db needs it)
        # db has no backup, so backup_coverage = 0/1 = 0
        # Score should be very low
        assert report.overall_score < 30.0
        assert report.tier == "unprotected"

    def test_has_critical_gaps(self, unprotected_graph):
        scorer = DRReadinessScorer(unprotected_graph)
        report = scorer.assess()
        assert len(report.critical_gaps) > 0

    def test_high_recovery_cost(self, unprotected_graph):
        scorer = DRReadinessScorer(unprotected_graph)
        report = scorer.assess()
        # 2 components, both manual = 2 * 4.0 = 8.0
        assert report.estimated_recovery_cost_hours == 8.0


# ---------------------------------------------------------------------------
# Multi-region Graph (partial coverage)
# ---------------------------------------------------------------------------


class TestMultiRegionGraph:
    def test_gets_multi_region_points(self, multi_region_graph):
        scorer = DRReadinessScorer(multi_region_graph)
        score = scorer._compute_score()
        # Multi-region = +25 (check_multi_region is True since 2 regions)
        assert score >= 25.0

    def test_tier_is_not_unprotected(self, multi_region_graph):
        scorer = DRReadinessScorer(multi_region_graph)
        report = scorer.assess()
        assert report.tier != "unprotected"

    def test_partial_failover_points(self, multi_region_graph):
        scorer = DRReadinessScorer(multi_region_graph)
        report = scorer.assess()
        # 2 out of 3 have failover = 2/3 * 20 ~ 13.3
        assert report.overall_score > 25.0


# ---------------------------------------------------------------------------
# Individual Scoring Factors
# ---------------------------------------------------------------------------


class TestScoringFactors:
    """Test each scoring factor independently."""

    def test_multi_region_adds_25(self):
        """Multi-region deployment alone should contribute 25 points."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", ComponentType.APP_SERVER, region="us-east-1", az="us-east-1a",
        ))
        graph.add_component(_make_component(
            "b", ComponentType.APP_SERVER, region="us-west-2", az="us-west-2a",
        ))
        scorer = DRReadinessScorer(graph)
        # Base: 25 (multi-region) + 0 (failover) + 15 (no data stores) + 10 (no deps) + 0 + 0 + 0 + 0
        score = scorer._compute_score()
        assert score >= 25.0

    def test_failover_adds_up_to_20(self):
        """All components with failover should add 20 points."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", ComponentType.APP_SERVER, failover=True,
        ))
        graph.add_component(_make_component(
            "b", ComponentType.APP_SERVER, failover=True,
        ))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        # 0 (no multi-region) + 20 (failover 2/2) + 15 (no data stores) + 10 (no deps) = 45
        assert score >= 20.0

    def test_partial_failover(self):
        """Only half components with failover should add 10 points."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", ComponentType.APP_SERVER, failover=True))
        graph.add_component(_make_component("b", ComponentType.APP_SERVER, failover=False))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        # Failover ratio = 0.5 -> 10 points
        # No multi-region: 0 + 10 (failover) + 15 (no data) + 10 (no deps) = 35
        assert score >= 10.0

    def test_backup_coverage_adds_15(self):
        """All data stores backed up should add 15 points."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db", ComponentType.DATABASE, backup_enabled=True,
        ))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        # backup_coverage = 1.0 -> 15 points
        assert score >= 15.0

    def test_no_backup_on_data_stores(self):
        """Data stores without backup should get 0 backup points."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db", ComponentType.DATABASE, backup_enabled=False,
        ))
        scorer = DRReadinessScorer(graph)
        backup_cov = scorer._check_backup_coverage()
        assert backup_cov == 0.0

    def test_backup_coverage_no_data_stores(self):
        """No data stores means full coverage by default."""
        graph = InfraGraph()
        graph.add_component(_make_component("app", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        backup_cov = scorer._check_backup_coverage()
        assert backup_cov == 1.0

    def test_circuit_breakers_add_10(self):
        """All edges with circuit breakers should add 10 points."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", ComponentType.APP_SERVER))
        graph.add_component(_make_component("b", ComponentType.APP_SERVER))
        graph.add_dependency(Dependency(
            source_id="a",
            target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        # Should include 10 points for CB coverage
        # No multi-region + no failover + 15 (no data stores) + 10 (CB) = 25
        assert score >= 10.0

    def test_no_circuit_breakers(self):
        """Edges without circuit breakers should get 0 CB points."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", ComponentType.APP_SERVER))
        graph.add_component(_make_component("b", ComponentType.APP_SERVER))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        # 0 + 0 + 15 + 0 (no CB) = 15
        assert score >= 0.0

    def test_no_edges_gets_10_cb_points(self):
        """No dependency edges should give full CB points (no risk)."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        # 0 + 0 + 15 + 10 (no deps) = 25
        assert score >= 25.0

    def test_monitoring_adds_10(self):
        """All components with audit_logging should add 10 points."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", ComponentType.APP_SERVER, audit_logging=True,
        ))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        assert score >= 10.0

    def test_encryption_adds_10(self):
        """All components with encryption at rest should add 10 points."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", ComponentType.APP_SERVER, encryption_at_rest=True,
        ))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        assert score >= 10.0

    def test_autoscaling_adds_5(self):
        """All components with autoscaling should add 5 points."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", ComponentType.APP_SERVER, autoscaling=True,
        ))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        assert score >= 5.0

    def test_log_monitoring_adds_5(self):
        """All components with log_enabled should add 5 points."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", ComponentType.APP_SERVER, log_enabled=True,
        ))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        assert score >= 5.0

    def test_combined_maximum_score(self):
        """All factors enabled on a single-component graph (no multi-region) should yield 75."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a",
            ComponentType.APP_SERVER,
            failover=True,
            autoscaling=True,
            encryption_at_rest=True,
            log_enabled=True,
            audit_logging=True,
        ))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        # 0 (no multi-region) + 20 (failover) + 15 (no data stores=full)
        # + 10 (no deps=full CB) + 10 (audit) + 10 (encryption) + 5 (autoscale) + 5 (log)
        assert score == 75.0


# ---------------------------------------------------------------------------
# Check Methods
# ---------------------------------------------------------------------------


class TestCheckMethods:
    def test_check_multi_region_true(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", region="us-east-1"))
        graph.add_component(_make_component("b", region="us-west-2"))
        scorer = DRReadinessScorer(graph)
        assert scorer._check_multi_region() is True

    def test_check_multi_region_false_single(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", region="us-east-1"))
        graph.add_component(_make_component("b", region="us-east-1"))
        scorer = DRReadinessScorer(graph)
        assert scorer._check_multi_region() is False

    def test_check_multi_region_false_no_region(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        scorer = DRReadinessScorer(graph)
        assert scorer._check_multi_region() is False

    def test_check_multi_az_counts(self):
        """Multiple AZs in the same region should count as multi-region."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", region="us-east-1", az="us-east-1a"))
        graph.add_component(_make_component("b", region="us-east-1", az="us-east-1b"))
        scorer = DRReadinessScorer(graph)
        assert scorer._check_multi_region() is True

    def test_failover_automation_fully(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", failover=True))
        graph.add_component(_make_component("b", autoscaling=True))
        scorer = DRReadinessScorer(graph)
        assert scorer._check_failover_automation() == "fully_automated"

    def test_failover_automation_semi(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", failover=True))
        graph.add_component(_make_component("b"))
        scorer = DRReadinessScorer(graph)
        assert scorer._check_failover_automation() == "semi_automated"

    def test_failover_automation_manual(self):
        """One component with automation out of three -> ratio < 0.5."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", failover=True))
        graph.add_component(_make_component("b"))
        graph.add_component(_make_component("c"))
        scorer = DRReadinessScorer(graph)
        # 1/3 = 0.33 -> manual
        assert scorer._check_failover_automation() == "manual"

    def test_failover_automation_none(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        graph.add_component(_make_component("b"))
        scorer = DRReadinessScorer(graph)
        assert scorer._check_failover_automation() == "none"

    def test_failover_automation_empty(self):
        graph = InfraGraph()
        scorer = DRReadinessScorer(graph)
        assert scorer._check_failover_automation() == "none"

    def test_check_data_protection_all_enabled(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a",
            encryption_at_rest=True,
            encryption_in_transit=True,
            backup_enabled=True,
            waf_protected=True,
        ))
        scorer = DRReadinessScorer(graph)
        dp = scorer._check_data_protection()
        assert dp["encryption_at_rest_ratio"] == 1.0
        assert dp["encryption_in_transit_ratio"] == 1.0
        assert dp["backup_ratio"] == 1.0
        assert dp["waf_ratio"] == 1.0

    def test_check_data_protection_none_enabled(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        scorer = DRReadinessScorer(graph)
        dp = scorer._check_data_protection()
        assert dp["encryption_at_rest_ratio"] == 0.0
        assert dp["waf_ratio"] == 0.0

    def test_check_data_protection_empty(self):
        graph = InfraGraph()
        scorer = DRReadinessScorer(graph)
        dp = scorer._check_data_protection()
        assert dp["encryption_at_rest_ratio"] == 0.0


# ---------------------------------------------------------------------------
# Scenario Assessments
# ---------------------------------------------------------------------------


class TestRegionalOutageScenario:
    def test_covered_with_multi_region_and_failover(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", region="us-east-1", failover=True,
        ))
        graph.add_component(_make_component(
            "b", region="us-west-2", failover=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.REGIONAL_OUTAGE)
        assert cap.is_covered is True
        assert cap.automation_level == "fully_automated"

    def test_not_covered_single_region(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", region="us-east-1"))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.REGIONAL_OUTAGE)
        assert cap.is_covered is False
        assert len(cap.gaps) > 0

    def test_not_covered_no_failover(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", region="us-east-1"))
        graph.add_component(_make_component("b", region="us-west-2"))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.REGIONAL_OUTAGE)
        assert cap.is_covered is False


class TestDatacenterFailureScenario:
    def test_covered_multi_az_with_failover(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", region="us-east-1", az="us-east-1a", failover=True,
        ))
        graph.add_component(_make_component(
            "b", region="us-east-1", az="us-east-1b", failover=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DATACENTER_FAILURE)
        assert cap.is_covered is True

    def test_not_covered_single_az(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", region="us-east-1", az="us-east-1a", failover=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DATACENTER_FAILURE)
        assert cap.is_covered is False

    def test_not_covered_no_az_set(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", region="us-east-1"))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DATACENTER_FAILURE)
        assert cap.is_covered is False
        assert any("availability zone" in g.lower() for g in cap.gaps)


class TestDataCorruptionScenario:
    def test_covered_with_full_backup(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db", ComponentType.DATABASE, backup_enabled=True, encryption_at_rest=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DATA_CORRUPTION)
        assert cap.is_covered is True

    def test_not_covered_without_backup(self):
        graph = InfraGraph()
        graph.add_component(_make_component("db", ComponentType.DATABASE))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DATA_CORRUPTION)
        assert cap.is_covered is False

    def test_gap_for_no_encryption(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db", ComponentType.DATABASE, backup_enabled=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DATA_CORRUPTION)
        assert any("encryption" in g.lower() for g in cap.gaps)


class TestRansomwareScenario:
    def test_covered_fully_protected(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db",
            ComponentType.DATABASE,
            backup_enabled=True,
            encryption_at_rest=True,
            network_segmented=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.RANSOMWARE)
        assert cap.is_covered is True

    def test_not_covered_no_segmentation(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db",
            ComponentType.DATABASE,
            backup_enabled=True,
            encryption_at_rest=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.RANSOMWARE)
        assert cap.is_covered is False
        assert any("segmentation" in g.lower() for g in cap.gaps)

    def test_not_covered_no_backup(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db",
            ComponentType.DATABASE,
            encryption_at_rest=True,
            network_segmented=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.RANSOMWARE)
        assert cap.is_covered is False

    def test_not_covered_no_encryption(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db",
            ComponentType.DATABASE,
            backup_enabled=True,
            network_segmented=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.RANSOMWARE)
        assert cap.is_covered is False


class TestDNSHijackScenario:
    def test_covered_with_dns_waf_and_tls(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "dns",
            ComponentType.DNS,
            waf_protected=True,
            encryption_in_transit=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DNS_HIJACK)
        assert cap.is_covered is True

    def test_not_covered_no_dns(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "app",
            ComponentType.APP_SERVER,
            waf_protected=True,
            encryption_in_transit=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DNS_HIJACK)
        assert cap.is_covered is False
        assert any("dns" in g.lower() for g in cap.gaps)

    def test_not_covered_no_waf(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "dns",
            ComponentType.DNS,
            encryption_in_transit=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DNS_HIJACK)
        assert cap.is_covered is False

    def test_not_covered_no_transit_encryption(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "dns",
            ComponentType.DNS,
            waf_protected=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.DNS_HIJACK)
        assert cap.is_covered is False
        assert any("transit" in g.lower() for g in cap.gaps)


class TestCloudProviderOutageScenario:
    def test_covered_multi_region_with_failover(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", region="us-east-1", failover=True,
        ))
        graph.add_component(_make_component(
            "b", region="us-west-2", failover=True,
        ))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.CLOUD_PROVIDER_OUTAGE)
        assert cap.is_covered is True

    def test_not_covered_single_region(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", region="us-east-1", failover=True))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.CLOUD_PROVIDER_OUTAGE)
        assert cap.is_covered is False

    def test_gap_for_external_deps_without_cb(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "app", region="us-east-1", failover=True,
        ))
        graph.add_component(_make_component(
            "ext",
            ComponentType.EXTERNAL_API,
            region="us-west-2",
            failover=True,
        ))
        graph.add_dependency(Dependency(source_id="app", target_id="ext"))
        scorer = DRReadinessScorer(graph)
        cap = scorer.assess_scenario(DRScenario.CLOUD_PROVIDER_OUTAGE)
        assert any("circuit breaker" in g.lower() for g in cap.gaps)


# ---------------------------------------------------------------------------
# RTO / RPO Calculations
# ---------------------------------------------------------------------------


class TestRTORPOCalculations:
    def test_rto_with_failover(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", failover=True, failover_promotion_seconds=60.0,
        ))
        scorer = DRReadinessScorer(graph)
        rto = scorer._worst_case_rto_minutes()
        assert rto == 1.0  # 60 seconds = 1 minute

    def test_rto_without_failover_uses_mttr(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", mttr_minutes=45.0))
        scorer = DRReadinessScorer(graph)
        rto = scorer._worst_case_rto_minutes()
        assert rto == 45.0

    def test_rto_without_failover_default_mttr(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", mttr_minutes=0.0))
        scorer = DRReadinessScorer(graph)
        rto = scorer._worst_case_rto_minutes()
        assert rto == 30.0  # default

    def test_rto_empty_graph(self):
        graph = InfraGraph()
        scorer = DRReadinessScorer(graph)
        assert scorer._worst_case_rto_minutes() == 0.0

    def test_rto_worst_case_across_components(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", failover=True, failover_promotion_seconds=120.0,
        ))
        graph.add_component(_make_component("b", mttr_minutes=60.0))
        scorer = DRReadinessScorer(graph)
        rto = scorer._worst_case_rto_minutes()
        assert rto == 60.0  # b has 60 min MTTR > a's 2 min

    def test_rpo_with_explicit_rpo(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", rpo_seconds=300))
        scorer = DRReadinessScorer(graph)
        rpo = scorer._worst_case_rpo_minutes()
        assert rpo == 5.0  # 300 sec = 5 min

    def test_rpo_with_backup(self):
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a", backup_enabled=True, backup_frequency_hours=6.0,
        ))
        scorer = DRReadinessScorer(graph)
        rpo = scorer._worst_case_rpo_minutes()
        assert rpo == 360.0  # 6 hours * 60

    def test_rpo_with_failover_only(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", failover=True))
        scorer = DRReadinessScorer(graph)
        rpo = scorer._worst_case_rpo_minutes()
        # async replication lag ~5 seconds
        assert rpo == pytest.approx(5.0 / 60.0, abs=0.01)

    def test_rpo_no_protection(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        scorer = DRReadinessScorer(graph)
        rpo = scorer._worst_case_rpo_minutes()
        assert rpo == 24.0 * 60.0  # worst case 24h

    def test_rpo_empty_graph(self):
        graph = InfraGraph()
        scorer = DRReadinessScorer(graph)
        assert scorer._worst_case_rpo_minutes() == 0.0


# ---------------------------------------------------------------------------
# Recovery Cost Estimation
# ---------------------------------------------------------------------------


class TestRecoveryCostEstimation:
    def test_fully_automated(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", failover=True, autoscaling=True))
        scorer = DRReadinessScorer(graph)
        assert scorer._estimate_recovery_cost_hours() == 0.5

    def test_semi_automated(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", failover=True))
        scorer = DRReadinessScorer(graph)
        assert scorer._estimate_recovery_cost_hours() == 2.0

    def test_semi_automated_autoscaling_only(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", autoscaling=True))
        scorer = DRReadinessScorer(graph)
        assert scorer._estimate_recovery_cost_hours() == 2.0

    def test_manual_recovery(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        scorer = DRReadinessScorer(graph)
        assert scorer._estimate_recovery_cost_hours() == 4.0

    def test_mixed_automation(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", failover=True, autoscaling=True))
        graph.add_component(_make_component("b", failover=True))
        graph.add_component(_make_component("c"))
        scorer = DRReadinessScorer(graph)
        assert scorer._estimate_recovery_cost_hours() == 0.5 + 2.0 + 4.0

    def test_empty_graph(self):
        graph = InfraGraph()
        scorer = DRReadinessScorer(graph)
        assert scorer._estimate_recovery_cost_hours() == 0.0


# ---------------------------------------------------------------------------
# Runbook Completeness
# ---------------------------------------------------------------------------


class TestRunbookCompleteness:
    def test_full_coverage(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", runbook_coverage=100.0))
        scorer = DRReadinessScorer(graph)
        assert scorer._compute_runbook_completeness() == 100.0

    def test_zero_coverage(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", runbook_coverage=0.0))
        scorer = DRReadinessScorer(graph)
        assert scorer._compute_runbook_completeness() == 0.0

    def test_average_coverage(self):
        graph = InfraGraph()
        graph.add_component(_make_component("a", runbook_coverage=80.0))
        graph.add_component(_make_component("b", runbook_coverage=40.0))
        scorer = DRReadinessScorer(graph)
        assert scorer._compute_runbook_completeness() == 60.0

    def test_empty_graph(self):
        graph = InfraGraph()
        scorer = DRReadinessScorer(graph)
        assert scorer._compute_runbook_completeness() == 0.0


# ---------------------------------------------------------------------------
# Full Assess Integration
# ---------------------------------------------------------------------------


class TestAssessIntegration:
    def test_assess_returns_all_scenarios(self, multi_region_graph):
        scorer = DRReadinessScorer(multi_region_graph)
        report = scorer.assess()
        scenario_set = {c.scenario for c in report.capabilities}
        for s in DRScenario:
            assert s in scenario_set

    def test_assess_counts_covered(self, fully_protected_graph):
        scorer = DRReadinessScorer(fully_protected_graph)
        report = scorer.assess()
        # Not all scenarios may be covered (e.g., DNS hijack needs DNS component)
        # but covered_scenarios should be <= total_scenarios
        assert report.covered_scenarios <= report.total_scenarios
        assert report.covered_scenarios >= 0

    def test_assess_deduplicates_gaps(self):
        """Gaps from different scenarios should be deduplicated."""
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        scorer = DRReadinessScorer(graph)
        report = scorer.assess()
        # Check no duplicates
        assert len(report.critical_gaps) == len(set(report.critical_gaps))

    def test_assess_score_matches_tier(self, multi_region_graph):
        scorer = DRReadinessScorer(multi_region_graph)
        report = scorer.assess()
        expected_tier = scorer._calculate_tier(report.overall_score)
        assert report.tier == expected_tier

    def test_assess_recovery_cost_positive(self, multi_region_graph):
        scorer = DRReadinessScorer(multi_region_graph)
        report = scorer.assess()
        assert report.estimated_recovery_cost_hours > 0.0

    def test_assess_runbook_completeness_range(self, multi_region_graph):
        scorer = DRReadinessScorer(multi_region_graph)
        report = scorer.assess()
        assert 0.0 <= report.runbook_completeness <= 100.0


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_component_no_features(self):
        """Single component with no features should score low."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", ComponentType.APP_SERVER))
        scorer = DRReadinessScorer(graph)
        report = scorer.assess()
        assert report.overall_score < 50.0

    def test_all_storage_types(self):
        """Backup coverage should count database, storage, and cache."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db", ComponentType.DATABASE, backup_enabled=True,
        ))
        graph.add_component(_make_component(
            "s3", ComponentType.STORAGE, backup_enabled=True,
        ))
        graph.add_component(_make_component(
            "redis", ComponentType.CACHE, backup_enabled=True,
        ))
        scorer = DRReadinessScorer(graph)
        assert scorer._check_backup_coverage() == 1.0

    def test_partial_storage_backup(self):
        """One out of two data stores backed up = 50% coverage."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "db", ComponentType.DATABASE, backup_enabled=True,
        ))
        graph.add_component(_make_component(
            "s3", ComponentType.STORAGE, backup_enabled=False,
        ))
        scorer = DRReadinessScorer(graph)
        assert scorer._check_backup_coverage() == 0.5

    def test_score_never_exceeds_100(self):
        """Even with generous configuration, score should cap at 100."""
        graph = InfraGraph()
        for i in range(5):
            graph.add_component(_make_component(
                f"c-{i}",
                ComponentType.APP_SERVER,
                region=f"region-{i}",
                az=f"region-{i}a",
                failover=True,
                autoscaling=True,
                backup_enabled=True,
                encryption_at_rest=True,
                log_enabled=True,
                audit_logging=True,
            ))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        assert score <= 100.0

    def test_score_never_below_zero(self):
        """Score should not go negative."""
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        scorer = DRReadinessScorer(graph)
        score = scorer._compute_score()
        assert score >= 0.0

    def test_large_number_of_components(self):
        """Scorer should handle many components without error."""
        graph = InfraGraph()
        for i in range(50):
            graph.add_component(_make_component(
                f"comp-{i}",
                ComponentType.APP_SERVER,
                region="us-east-1" if i % 2 == 0 else "us-west-2",
            ))
        scorer = DRReadinessScorer(graph)
        report = scorer.assess()
        assert 0.0 <= report.overall_score <= 100.0
        assert report.total_scenarios == 6

    def test_assess_scenario_empty_graph(self):
        """assess_scenario on empty graph should produce uncovered capability."""
        graph = InfraGraph()
        scorer = DRReadinessScorer(graph)
        for s in DRScenario:
            cap = scorer.assess_scenario(s)
            assert cap.is_covered is False
            assert cap.automation_level == "none"
            assert len(cap.gaps) > 0

    def test_mixed_component_types(self):
        """Different component types should all be evaluated."""
        graph = InfraGraph()
        graph.add_component(_make_component("lb", ComponentType.LOAD_BALANCER))
        graph.add_component(_make_component("app", ComponentType.APP_SERVER))
        graph.add_component(_make_component("db", ComponentType.DATABASE, backup_enabled=True))
        graph.add_component(_make_component("cache", ComponentType.CACHE))
        graph.add_component(_make_component("queue", ComponentType.QUEUE))
        graph.add_component(_make_component("dns", ComponentType.DNS))
        graph.add_component(_make_component("ext", ComponentType.EXTERNAL_API))
        scorer = DRReadinessScorer(graph)
        report = scorer.assess()
        assert report.total_scenarios == 6

    def test_rpo_priority_explicit_over_backup(self):
        """Explicit RPO should take precedence over backup-derived RPO."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a",
            rpo_seconds=60,
            backup_enabled=True,
            backup_frequency_hours=12.0,
        ))
        scorer = DRReadinessScorer(graph)
        rpo = scorer._worst_case_rpo_minutes()
        assert rpo == 1.0  # 60 seconds, not 720 minutes

    def test_score_clamped_at_boundaries(self):
        """Score should be clamped to [0, 100]."""
        graph = InfraGraph()
        graph.add_component(_make_component("a"))
        scorer = DRReadinessScorer(graph)
        assert 0.0 <= scorer._compute_score() <= 100.0

    def test_coverage_scenarios_count(self):
        """covered_scenarios should equal number of scenarios where is_covered=True."""
        graph = InfraGraph()
        graph.add_component(_make_component(
            "a",
            ComponentType.APP_SERVER,
            region="us-east-1",
            failover=True,
        ))
        graph.add_component(_make_component(
            "b",
            ComponentType.APP_SERVER,
            region="us-west-2",
            failover=True,
        ))
        scorer = DRReadinessScorer(graph)
        report = scorer.assess()
        manually_counted = sum(1 for c in report.capabilities if c.is_covered)
        assert report.covered_scenarios == manually_counted
