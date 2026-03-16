"""Tests for Architecture Fitness Functions."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
    RetryStrategy,
    SecurityProfile,
    ComplianceTags,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.fitness_functions import (
    FitnessCategory,
    FitnessEvaluator,
    FitnessGrade,
    FitnessReport,
    FitnessResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
    encryption_at_rest: bool = False,
    encryption_in_transit: bool = False,
    log_enabled: bool = False,
    backup_enabled: bool = False,
    pci_scope: bool = False,
    contains_pii: bool = False,
    autoscaling: bool = False,
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
) -> Component:
    """Helper to construct a Component with common overrides."""
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover.enabled = True
    c.security.encryption_at_rest = encryption_at_rest
    c.security.encryption_in_transit = encryption_in_transit
    c.security.log_enabled = log_enabled
    c.security.backup_enabled = backup_enabled
    c.compliance_tags.pci_scope = pci_scope
    c.compliance_tags.contains_pii = contains_pii
    if autoscaling:
        c.autoscaling.enabled = True
    c.metrics.cpu_percent = cpu_percent
    c.metrics.memory_percent = memory_percent
    return c


def _empty_graph() -> InfraGraph:
    return InfraGraph()


def _well_configured_graph() -> InfraGraph:
    """Graph where everything is well-configured -- should score all A's."""
    graph = InfraGraph()
    for cid in ["lb", "app", "db"]:
        ctype = {
            "lb": ComponentType.LOAD_BALANCER,
            "app": ComponentType.APP_SERVER,
            "db": ComponentType.DATABASE,
        }[cid]
        c = _comp(
            cid, cid.upper(), ctype=ctype, replicas=3, failover=True,
            health=HealthStatus.HEALTHY,
            encryption_at_rest=True, encryption_in_transit=True,
            log_enabled=True, backup_enabled=True,
            pci_scope=True, contains_pii=True,
            autoscaling=True,
            cpu_percent=50.0,
        )
        graph.add_component(c)
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(max_retries=3),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
        retry_strategy=RetryStrategy(max_retries=3),
    ))
    return graph


def _poorly_configured_graph() -> InfraGraph:
    """Graph where everything is poorly configured -- should score F's."""
    graph = InfraGraph()
    for cid in ["lb", "app", "db"]:
        ctype = {
            "lb": ComponentType.LOAD_BALANCER,
            "app": ComponentType.APP_SERVER,
            "db": ComponentType.DATABASE,
        }[cid]
        c = _comp(
            cid, cid.upper(), ctype=ctype, replicas=1, failover=False,
            health=HealthStatus.DOWN,
            encryption_at_rest=False, encryption_in_transit=False,
            log_enabled=False, backup_enabled=False,
            pci_scope=False, contains_pii=False,
            autoscaling=False,
            cpu_percent=95.0,
        )
        graph.add_component(c)
    graph.add_dependency(Dependency(source_id="lb", target_id="app"))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    return graph


# ---------------------------------------------------------------------------
# Tests: Grade conversion
# ---------------------------------------------------------------------------


class TestGradeConversion:
    def test_grade_a_at_100(self):
        ev = FitnessEvaluator()
        assert ev.grade(100.0) == FitnessGrade.A

    def test_grade_a_at_90(self):
        ev = FitnessEvaluator()
        assert ev.grade(90.0) == FitnessGrade.A

    def test_grade_b_at_89(self):
        ev = FitnessEvaluator()
        assert ev.grade(89.9) == FitnessGrade.B

    def test_grade_b_at_75(self):
        ev = FitnessEvaluator()
        assert ev.grade(75.0) == FitnessGrade.B

    def test_grade_c_at_74(self):
        ev = FitnessEvaluator()
        assert ev.grade(74.9) == FitnessGrade.C

    def test_grade_c_at_60(self):
        ev = FitnessEvaluator()
        assert ev.grade(60.0) == FitnessGrade.C

    def test_grade_d_at_59(self):
        ev = FitnessEvaluator()
        assert ev.grade(59.9) == FitnessGrade.D

    def test_grade_d_at_40(self):
        ev = FitnessEvaluator()
        assert ev.grade(40.0) == FitnessGrade.D

    def test_grade_f_at_39(self):
        ev = FitnessEvaluator()
        assert ev.grade(39.9) == FitnessGrade.F

    def test_grade_f_at_0(self):
        ev = FitnessEvaluator()
        assert ev.grade(0.0) == FitnessGrade.F


# ---------------------------------------------------------------------------
# Tests: FitnessReport dataclass defaults
# ---------------------------------------------------------------------------


class TestFitnessReportDefaults:
    def test_default_values(self):
        report = FitnessReport()
        assert report.results == []
        assert report.overall_score == 0.0
        assert report.overall_grade == FitnessGrade.F
        assert report.category_scores == {}
        assert report.passed_count == 0
        assert report.failed_count == 0
        assert report.critical_failures == []
        assert report.trends == []


# ---------------------------------------------------------------------------
# Tests: FitnessResult dataclass
# ---------------------------------------------------------------------------


class TestFitnessResult:
    def test_fields(self):
        r = FitnessResult(
            function_id="test",
            function_name="Test",
            category=FitnessCategory.RESILIENCE,
            score=85.0,
            grade=FitnessGrade.B,
            weight=1.5,
            details="Some details.",
            passed=True,
            threshold=60.0,
        )
        assert r.function_id == "test"
        assert r.function_name == "Test"
        assert r.category == FitnessCategory.RESILIENCE
        assert r.score == 85.0
        assert r.grade == FitnessGrade.B
        assert r.weight == 1.5
        assert r.details == "Some details."
        assert r.passed is True
        assert r.threshold == 60.0


# ---------------------------------------------------------------------------
# Tests: Empty graph
# ---------------------------------------------------------------------------


class TestEmptyGraph:
    def test_empty_graph_perfect_score(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_empty_graph())
        assert report.overall_score == 100.0
        assert report.overall_grade == FitnessGrade.A

    def test_empty_graph_no_failures(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_empty_graph())
        assert report.failed_count == 0
        assert report.critical_failures == []

    def test_empty_graph_all_passed(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_empty_graph())
        assert report.passed_count == len(report.results)


# ---------------------------------------------------------------------------
# Tests: Well-configured graph (all A's)
# ---------------------------------------------------------------------------


class TestWellConfiguredGraph:
    def test_high_overall_score(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        assert report.overall_score >= 75.0

    def test_grade_a_or_b(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        assert report.overall_grade in (FitnessGrade.A, FitnessGrade.B)

    def test_no_critical_failures(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        assert report.critical_failures == []

    def test_most_functions_pass(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        assert report.passed_count >= report.failed_count


# ---------------------------------------------------------------------------
# Tests: Poorly configured graph (all F's)
# ---------------------------------------------------------------------------


class TestPoorlyConfiguredGraph:
    def test_low_overall_score(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        assert report.overall_score < 60.0

    def test_has_failures(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        assert report.failed_count > 0

    def test_has_critical_failures(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        assert len(report.critical_failures) > 0

    def test_grade_d_or_f(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        assert report.overall_grade in (FitnessGrade.D, FitnessGrade.F)


# ---------------------------------------------------------------------------
# Tests: Individual fitness functions — RESILIENCE
# ---------------------------------------------------------------------------


class TestRedundancyFitness:
    def test_all_redundant(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", replicas=3))
        graph.add_component(_comp("b", "B", replicas=2))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        redundancy = [r for r in results if r.function_id == "redundancy"][0]
        assert redundancy.score == 100.0

    def test_none_redundant(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", replicas=1))
        graph.add_component(_comp("b", "B", replicas=1))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        redundancy = [r for r in results if r.function_id == "redundancy"][0]
        assert redundancy.score == 0.0

    def test_half_redundant(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", replicas=2))
        graph.add_component(_comp("b", "B", replicas=1))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        redundancy = [r for r in results if r.function_id == "redundancy"][0]
        assert redundancy.score == 50.0


class TestFailoverFitness:
    def test_all_critical_with_failover(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("app", "App", failover=True))
        graph.add_component(_comp("client", "Client"))
        graph.add_dependency(Dependency(source_id="client", target_id="app"))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        failover = [r for r in results if r.function_id == "failover"][0]
        assert failover.score == 100.0

    def test_no_critical_components(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        failover = [r for r in results if r.function_id == "failover"][0]
        assert failover.score == 100.0

    def test_critical_without_failover(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("app", "App", failover=False))
        graph.add_component(_comp("client", "Client"))
        graph.add_dependency(Dependency(source_id="client", target_id="app"))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        failover = [r for r in results if r.function_id == "failover"][0]
        assert failover.score == 0.0


class TestSpofFitness:
    def test_no_spofs(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("app", "App", replicas=2))
        graph.add_component(_comp("client", "Client"))
        graph.add_dependency(Dependency(source_id="client", target_id="app"))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        spof = [r for r in results if r.function_id == "spof"][0]
        assert spof.score == 100.0

    def test_all_spofs(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("app", "App", replicas=1))
        graph.add_component(_comp("db", "DB", replicas=1))
        graph.add_dependency(Dependency(source_id="app", target_id="db"))
        # app has no dependents but db does (app depends on db)
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        spof = [r for r in results if r.function_id == "spof"][0]
        assert spof.score < 100.0


class TestCircuitBreakerFitness:
    def test_all_with_cb(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        graph.add_component(_comp("b", "B"))
        graph.add_dependency(Dependency(
            source_id="a", target_id="b",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        ))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        cb = [r for r in results if r.function_id == "circuit_breaker"][0]
        assert cb.score == 100.0

    def test_no_cb(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        graph.add_component(_comp("b", "B"))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        cb = [r for r in results if r.function_id == "circuit_breaker"][0]
        assert cb.score == 0.0

    def test_no_edges(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        cb = [r for r in results if r.function_id == "circuit_breaker"][0]
        assert cb.score == 100.0


# ---------------------------------------------------------------------------
# Tests: Individual fitness functions — SECURITY
# ---------------------------------------------------------------------------


class TestEncryptionFitness:
    def test_all_encrypted(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", encryption_at_rest=True))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        enc = [r for r in results if r.function_id == "encryption"][0]
        assert enc.score == 100.0

    def test_none_encrypted(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        enc = [r for r in results if r.function_id == "encryption"][0]
        assert enc.score == 0.0

    def test_partial_encryption(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", encryption_in_transit=True))
        graph.add_component(_comp("b", "B"))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        enc = [r for r in results if r.function_id == "encryption"][0]
        assert enc.score == 50.0


class TestMonitoringFitness:
    def test_all_monitored(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", log_enabled=True))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        mon = [r for r in results if r.function_id == "monitoring"][0]
        assert mon.score == 100.0

    def test_none_monitored(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", log_enabled=False))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        mon = [r for r in results if r.function_id == "monitoring"][0]
        assert mon.score == 0.0


class TestBackupFitness:
    def test_all_data_stores_backed(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("db", "DB", ctype=ComponentType.DATABASE, backup_enabled=True))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        backup = [r for r in results if r.function_id == "backup"][0]
        assert backup.score == 100.0

    def test_no_data_stores(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("app", "App"))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        backup = [r for r in results if r.function_id == "backup"][0]
        assert backup.score == 100.0

    def test_no_backups(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("db", "DB", ctype=ComponentType.DATABASE, backup_enabled=False))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        backup = [r for r in results if r.function_id == "backup"][0]
        assert backup.score == 0.0


class TestComplianceFitness:
    def test_all_tagged(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", pci_scope=True))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        comp = [r for r in results if r.function_id == "compliance"][0]
        assert comp.score == 100.0

    def test_none_tagged(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        results = ev.evaluate_category(graph, FitnessCategory.SECURITY)
        comp = [r for r in results if r.function_id == "compliance"][0]
        assert comp.score == 0.0


# ---------------------------------------------------------------------------
# Tests: Individual fitness functions — PERFORMANCE
# ---------------------------------------------------------------------------


class TestUtilizationFitness:
    def test_zero_utilization_is_perfect(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", cpu_percent=0.0))
        results = ev.evaluate_category(graph, FitnessCategory.PERFORMANCE)
        util = [r for r in results if r.function_id == "utilization"][0]
        assert util.score == 100.0

    def test_high_utilization_lowers_score(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", cpu_percent=90.0))
        results = ev.evaluate_category(graph, FitnessCategory.PERFORMANCE)
        util = [r for r in results if r.function_id == "utilization"][0]
        assert util.score < 20.0


class TestDependencyDepthFitness:
    def test_no_dependencies(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        results = ev.evaluate_category(graph, FitnessCategory.PERFORMANCE)
        depth = [r for r in results if r.function_id == "dependency_depth"][0]
        assert depth.score == 100.0

    def test_shallow_chain(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        graph.add_component(_comp("b", "B"))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        results = ev.evaluate_category(graph, FitnessCategory.PERFORMANCE)
        depth = [r for r in results if r.function_id == "dependency_depth"][0]
        assert depth.score == 100.0

    def test_deep_chain_penalized(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        for i in range(8):
            graph.add_component(_comp(f"c{i}", f"C{i}"))
        for i in range(7):
            graph.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{i+1}"))
        results = ev.evaluate_category(graph, FitnessCategory.PERFORMANCE)
        depth = [r for r in results if r.function_id == "dependency_depth"][0]
        assert depth.score < 100.0

    def test_very_deep_chain_zero(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        for i in range(12):
            graph.add_component(_comp(f"c{i}", f"C{i}"))
        for i in range(11):
            graph.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{i+1}"))
        results = ev.evaluate_category(graph, FitnessCategory.PERFORMANCE)
        depth = [r for r in results if r.function_id == "dependency_depth"][0]
        assert depth.score == 0.0


# ---------------------------------------------------------------------------
# Tests: Individual fitness functions — OPERABILITY
# ---------------------------------------------------------------------------


class TestHealthFitness:
    def test_all_healthy(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", health=HealthStatus.HEALTHY))
        graph.add_component(_comp("b", "B", health=HealthStatus.HEALTHY))
        results = ev.evaluate_category(graph, FitnessCategory.OPERABILITY)
        health = [r for r in results if r.function_id == "health"][0]
        assert health.score == 100.0

    def test_all_down(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", health=HealthStatus.DOWN))
        graph.add_component(_comp("b", "B", health=HealthStatus.DOWN))
        results = ev.evaluate_category(graph, FitnessCategory.OPERABILITY)
        health = [r for r in results if r.function_id == "health"][0]
        assert health.score == 0.0

    def test_partial_health(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", health=HealthStatus.HEALTHY))
        graph.add_component(_comp("b", "B", health=HealthStatus.DOWN))
        results = ev.evaluate_category(graph, FitnessCategory.OPERABILITY)
        health = [r for r in results if r.function_id == "health"][0]
        assert health.score == 50.0


class TestRetryFitness:
    def test_all_with_retry(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        graph.add_component(_comp("b", "B"))
        graph.add_dependency(Dependency(
            source_id="a", target_id="b",
            retry_strategy=RetryStrategy(max_retries=3),
        ))
        results = ev.evaluate_category(graph, FitnessCategory.OPERABILITY)
        retry = [r for r in results if r.function_id == "retry"][0]
        assert retry.score == 100.0

    def test_no_retry(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        graph.add_component(_comp("b", "B"))
        graph.add_dependency(Dependency(
            source_id="a", target_id="b",
            retry_strategy=RetryStrategy(max_retries=0),
        ))
        results = ev.evaluate_category(graph, FitnessCategory.OPERABILITY)
        retry = [r for r in results if r.function_id == "retry"][0]
        assert retry.score == 0.0


# ---------------------------------------------------------------------------
# Tests: Individual fitness functions — SCALABILITY
# ---------------------------------------------------------------------------


class TestAutoscaleReadiness:
    def test_all_autoscaled(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", autoscaling=True))
        results = ev.evaluate_category(graph, FitnessCategory.SCALABILITY)
        auto = [r for r in results if r.function_id == "autoscale_readiness"][0]
        assert auto.score == 100.0

    def test_none_autoscaled(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", autoscaling=False))
        results = ev.evaluate_category(graph, FitnessCategory.SCALABILITY)
        auto = [r for r in results if r.function_id == "autoscale_readiness"][0]
        assert auto.score == 0.0


class TestLoadDistribution:
    def test_even_load(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", cpu_percent=50.0))
        graph.add_component(_comp("b", "B", cpu_percent=50.0))
        results = ev.evaluate_category(graph, FitnessCategory.SCALABILITY)
        ld = [r for r in results if r.function_id == "load_distribution"][0]
        assert ld.score == 100.0

    def test_uneven_load(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", cpu_percent=95.0))
        graph.add_component(_comp("b", "B", cpu_percent=5.0))
        results = ev.evaluate_category(graph, FitnessCategory.SCALABILITY)
        ld = [r for r in results if r.function_id == "load_distribution"][0]
        assert ld.score < 50.0

    def test_single_component(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", cpu_percent=80.0))
        results = ev.evaluate_category(graph, FitnessCategory.SCALABILITY)
        ld = [r for r in results if r.function_id == "load_distribution"][0]
        assert ld.score == 100.0


# ---------------------------------------------------------------------------
# Tests: Individual fitness functions — COST_EFFICIENCY
# ---------------------------------------------------------------------------


class TestRightSizing:
    def test_well_sized(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", cpu_percent=50.0))
        results = ev.evaluate_category(graph, FitnessCategory.COST_EFFICIENCY)
        rs = [r for r in results if r.function_id == "right_sizing"][0]
        assert rs.score == 100.0

    def test_over_provisioned(self):
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", cpu_percent=5.0))
        graph.add_component(_comp("b", "B", cpu_percent=5.0))
        results = ev.evaluate_category(graph, FitnessCategory.COST_EFFICIENCY)
        rs = [r for r in results if r.function_id == "right_sizing"][0]
        assert rs.score < 100.0

    def test_zero_utilization_is_fine(self):
        """Zero utilization (no data) is treated as well-sized."""
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", cpu_percent=0.0))
        results = ev.evaluate_category(graph, FitnessCategory.COST_EFFICIENCY)
        rs = [r for r in results if r.function_id == "right_sizing"][0]
        assert rs.score == 100.0


# ---------------------------------------------------------------------------
# Tests: evaluate() full report
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_results_count(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        assert len(report.results) == 15  # 15 built-in functions

    def test_passed_plus_failed_equals_total(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        assert report.passed_count + report.failed_count == len(report.results)

    def test_overall_score_in_range(self):
        ev = FitnessEvaluator()
        for graph_fn in [_empty_graph, _well_configured_graph, _poorly_configured_graph]:
            report = ev.evaluate(graph_fn())
            assert 0.0 <= report.overall_score <= 100.0

    def test_all_result_scores_in_range(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        for r in report.results:
            assert 0.0 <= r.score <= 100.0

    def test_weighted_average(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        total_weight = sum(r.weight for r in report.results)
        expected = sum(r.score * r.weight for r in report.results) / total_weight
        assert abs(report.overall_score - round(expected, 2)) < 0.1


# ---------------------------------------------------------------------------
# Tests: evaluate_category()
# ---------------------------------------------------------------------------


class TestEvaluateCategory:
    def test_resilience_returns_4_functions(self):
        ev = FitnessEvaluator()
        results = ev.evaluate_category(_well_configured_graph(), FitnessCategory.RESILIENCE)
        assert len(results) == 4
        ids = {r.function_id for r in results}
        assert ids == {"redundancy", "failover", "spof", "circuit_breaker"}

    def test_security_returns_4_functions(self):
        ev = FitnessEvaluator()
        results = ev.evaluate_category(_well_configured_graph(), FitnessCategory.SECURITY)
        assert len(results) == 4
        ids = {r.function_id for r in results}
        assert ids == {"encryption", "monitoring", "backup", "compliance"}

    def test_performance_returns_2_functions(self):
        ev = FitnessEvaluator()
        results = ev.evaluate_category(_well_configured_graph(), FitnessCategory.PERFORMANCE)
        assert len(results) == 2

    def test_operability_returns_2_functions(self):
        ev = FitnessEvaluator()
        results = ev.evaluate_category(_well_configured_graph(), FitnessCategory.OPERABILITY)
        assert len(results) == 2

    def test_scalability_returns_2_functions(self):
        ev = FitnessEvaluator()
        results = ev.evaluate_category(_well_configured_graph(), FitnessCategory.SCALABILITY)
        assert len(results) == 2

    def test_cost_efficiency_returns_1_function(self):
        ev = FitnessEvaluator()
        results = ev.evaluate_category(_well_configured_graph(), FitnessCategory.COST_EFFICIENCY)
        assert len(results) == 1

    def test_category_results_have_correct_category(self):
        ev = FitnessEvaluator()
        results = ev.evaluate_category(_well_configured_graph(), FitnessCategory.SECURITY)
        for r in results:
            assert r.category == FitnessCategory.SECURITY


# ---------------------------------------------------------------------------
# Tests: Custom thresholds
# ---------------------------------------------------------------------------


class TestCustomThresholds:
    def test_higher_threshold_causes_failure(self):
        ev = FitnessEvaluator(custom_thresholds={"redundancy": 100.0})
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", replicas=2))
        graph.add_component(_comp("b", "B", replicas=1))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        redundancy = [r for r in results if r.function_id == "redundancy"][0]
        assert redundancy.score == 50.0
        assert redundancy.passed is False
        assert redundancy.threshold == 100.0

    def test_lower_threshold_causes_pass(self):
        ev = FitnessEvaluator(custom_thresholds={"redundancy": 10.0})
        graph = InfraGraph()
        graph.add_component(_comp("a", "A", replicas=2))
        graph.add_component(_comp("b", "B", replicas=1))
        results = ev.evaluate_category(graph, FitnessCategory.RESILIENCE)
        redundancy = [r for r in results if r.function_id == "redundancy"][0]
        assert redundancy.score == 50.0
        assert redundancy.passed is True
        assert redundancy.threshold == 10.0

    def test_default_threshold_is_60(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        for r in report.results:
            assert r.threshold == 60.0


# ---------------------------------------------------------------------------
# Tests: category_scores in report
# ---------------------------------------------------------------------------


class TestCategoryScores:
    def test_all_categories_present(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        expected = {
            FitnessCategory.RESILIENCE.value,
            FitnessCategory.SECURITY.value,
            FitnessCategory.PERFORMANCE.value,
            FitnessCategory.OPERABILITY.value,
            FitnessCategory.SCALABILITY.value,
            FitnessCategory.COST_EFFICIENCY.value,
        }
        assert set(report.category_scores.keys()) == expected

    def test_category_scores_in_range(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        for score in report.category_scores.values():
            assert 0.0 <= score <= 100.0

    def test_category_score_is_average_of_functions(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        # Manually verify resilience category average
        resilience_scores = [
            r.score for r in report.results if r.category == FitnessCategory.RESILIENCE
        ]
        expected_avg = sum(resilience_scores) / len(resilience_scores)
        assert abs(report.category_scores["resilience"] - round(expected_avg, 2)) < 0.1


# ---------------------------------------------------------------------------
# Tests: critical_failures
# ---------------------------------------------------------------------------


class TestCriticalFailures:
    def test_no_critical_on_good_graph(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        assert report.critical_failures == []

    def test_critical_on_bad_graph(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        # Should have functions scoring below 30
        assert len(report.critical_failures) > 0

    def test_critical_threshold_is_30(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        for crit_id in report.critical_failures:
            result = [r for r in report.results if r.function_id == crit_id][0]
            assert result.score < 30.0


# ---------------------------------------------------------------------------
# Tests: trends (improvement suggestions)
# ---------------------------------------------------------------------------


class TestTrends:
    def test_no_trends_on_perfect_graph(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_empty_graph())
        assert report.trends == []

    def test_trends_on_bad_graph(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        assert len(report.trends) > 0

    def test_trends_are_strings(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_poorly_configured_graph())
        for trend in report.trends:
            assert isinstance(trend, str)


# ---------------------------------------------------------------------------
# Tests: Enum values
# ---------------------------------------------------------------------------


class TestEnumValues:
    def test_category_values(self):
        assert FitnessCategory.RESILIENCE.value == "resilience"
        assert FitnessCategory.SECURITY.value == "security"
        assert FitnessCategory.PERFORMANCE.value == "performance"
        assert FitnessCategory.OPERABILITY.value == "operability"
        assert FitnessCategory.SCALABILITY.value == "scalability"
        assert FitnessCategory.COST_EFFICIENCY.value == "cost_efficiency"

    def test_grade_values(self):
        assert FitnessGrade.A.value == "A"
        assert FitnessGrade.B.value == "B"
        assert FitnessGrade.C.value == "C"
        assert FitnessGrade.D.value == "D"
        assert FitnessGrade.F.value == "F"


# ---------------------------------------------------------------------------
# Tests: Weight correctness
# ---------------------------------------------------------------------------


class TestWeights:
    def test_resilience_weight_is_1_5(self):
        ev = FitnessEvaluator()
        results = ev.evaluate_category(_well_configured_graph(), FitnessCategory.RESILIENCE)
        for r in results:
            assert r.weight == 1.5

    def test_security_weight_is_1_3(self):
        ev = FitnessEvaluator()
        results = ev.evaluate_category(_well_configured_graph(), FitnessCategory.SECURITY)
        for r in results:
            assert r.weight == 1.3

    def test_other_weights_are_1_0(self):
        ev = FitnessEvaluator()
        report = ev.evaluate(_well_configured_graph())
        for r in report.results:
            if r.category not in (FitnessCategory.RESILIENCE, FitnessCategory.SECURITY):
                assert r.weight == 1.0


# ---------------------------------------------------------------------------
# Tests: Edge cases for 100% coverage
# ---------------------------------------------------------------------------


class TestBuildReportEdgeCases:
    def test_empty_results_returns_default_report(self):
        """_build_report with empty list returns default FitnessReport."""
        ev = FitnessEvaluator()
        report = ev._build_report([])
        assert report.overall_score == 0.0
        assert report.overall_grade == FitnessGrade.F
        assert report.results == []
        assert report.passed_count == 0
        assert report.failed_count == 0

    def test_zero_weight_results_score_is_zero(self):
        """_build_report with all zero-weight results yields 0.0 overall."""
        ev = FitnessEvaluator()
        result = FitnessResult(
            function_id="test",
            function_name="Test",
            category=FitnessCategory.RESILIENCE,
            score=80.0,
            grade=FitnessGrade.B,
            weight=0.0,
            details="zero weight",
            passed=True,
            threshold=60.0,
        )
        report = ev._build_report([result])
        assert report.overall_score == 0.0


class TestDependencyDepthEdgeCases:
    def test_components_exist_but_no_paths(self):
        """Components with no dependencies -> get_critical_paths returns []."""
        ev = FitnessEvaluator()
        graph = InfraGraph()
        graph.add_component(_comp("a", "A"))
        graph.add_component(_comp("b", "B"))
        # No dependencies, so get_critical_paths should return []
        results = ev.evaluate_category(graph, FitnessCategory.PERFORMANCE)
        depth = [r for r in results if r.function_id == "dependency_depth"][0]
        assert depth.score == 100.0


class TestLoadDistributionEdgeCases:
    def test_extreme_variance_yields_zero(self):
        """stddev >= 50 should yield score 0."""
        ev = FitnessEvaluator()
        graph = InfraGraph()
        # cpu=100 -> utilization ~100, cpu=0 -> utilization 0
        # stddev of [100, 0] = 50 -> score should be 0
        graph.add_component(_comp("a", "A", cpu_percent=100.0))
        graph.add_component(_comp("b", "B", cpu_percent=0.0))
        results = ev.evaluate_category(graph, FitnessCategory.SCALABILITY)
        ld = [r for r in results if r.function_id == "load_distribution"][0]
        assert ld.score == 0.0
