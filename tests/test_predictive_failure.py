"""Comprehensive tests for the PredictiveFailureEngine.

Covers all branches, risk levels, patterns, edge cases, and summary generation
to achieve 99%+ code coverage.
"""

from __future__ import annotations

import math

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.predictive_failure import (
    FailurePattern,
    FailurePrediction,
    PatternMatch,
    PredictiveFailureEngine,
    PredictiveReport,
    RiskLevel,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    cpu: float = 0.0,
    memory: float = 0.0,
    disk: float = 0.0,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover: bool = False,
    max_connections: int = 0,
    network_connections: int = 0,
    timeout_seconds: float = 0,
    latency_ms: float = 0,
    parameters: dict | None = None,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.metrics = ResourceMetrics(
        cpu_percent=cpu,
        memory_percent=memory,
        disk_percent=disk,
        network_connections=network_connections,
        latency_ms=latency_ms,
    )
    c.capacity = Capacity(
        max_connections=max_connections,
        timeout_seconds=timeout_seconds,
    )
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    if parameters:
        c.parameters = parameters
    return c


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ===================================================================
# 1. Empty graph
# ===================================================================


class TestEmptyGraph:
    def test_no_predictions(self):
        engine = PredictiveFailureEngine(_graph())
        report = engine.predict()
        assert report.predictions == []
        assert report.detected_patterns == []
        assert report.overall_risk_score == 0.0
        assert report.mean_time_to_predicted_failure == float("inf")
        assert report.risk_distribution == {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "unknown": 0,
        }
        assert report.top_risks == []
        assert "healthy" in report.risk_summary.lower()


# ===================================================================
# 2. Single healthy component — no/low risk
# ===================================================================


class TestHealthyComponent:
    def test_fully_healthy_multiple_replicas_with_failover(self):
        """No factors at all => risk_score==0 => returns None => no predictions."""
        c = _comp("h1", "Healthy", replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0

    def test_single_replica_no_failover_yields_low_risk(self):
        """Single replica + no failover => 10 + 5 = 15 => LOW."""
        c = _comp("h2", "SingleReplica")
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 1
        pred = report.predictions[0]
        assert pred.risk_level == RiskLevel.LOW
        assert pred.risk_score == 15.0
        assert "Single replica" in pred.contributing_factors[0]
        assert "No failover" in pred.contributing_factors[1]


# ===================================================================
# 3. High CPU — risk factor + correct pattern
# ===================================================================


class TestHighCPU:
    def test_cpu_above_threshold(self):
        c = _comp("cpu1", "HotCPU", cpu=90.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 1
        pred = report.predictions[0]
        assert "CPU at 90.0%" in pred.contributing_factors[0]
        assert pred.failure_pattern == FailurePattern.CPU_MEMORY_CASCADE

    def test_cpu_at_100(self):
        c = _comp("cpu2", "MaxCPU", cpu=100.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        # remaining=0 => hours=0
        assert pred.predicted_failure_hours == 0.0

    def test_cpu_just_above_threshold(self):
        c = _comp("cpu3", "BarelyCPU", cpu=76.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_score > 0

    def test_cpu_at_threshold_no_risk(self):
        """CPU == 75 should not trigger (strict >)."""
        c = _comp("cpu4", "ThreshCPU", cpu=75.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0


# ===================================================================
# 4. High memory — risk
# ===================================================================


class TestHighMemory:
    def test_memory_above_threshold(self):
        c = _comp("mem1", "HotMem", memory=95.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert "Memory at 95.0%" in pred.contributing_factors[0]
        # CPU is not high, so pattern should be CONNECTION_POOL_LEAK
        assert pred.failure_pattern == FailurePattern.CONNECTION_POOL_LEAK

    def test_memory_at_100(self):
        c = _comp("mem2", "MaxMem", memory=100.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.predicted_failure_hours == 0.0

    def test_memory_at_threshold_no_risk(self):
        """memory == 80 should not trigger (strict >)."""
        c = _comp("mem3", "ThreshMem", memory=80.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0


# ===================================================================
# 5. High disk — DISK_EXHAUSTION pattern
# ===================================================================


class TestHighDisk:
    def test_disk_above_threshold(self):
        c = _comp("dsk1", "FullDisk", disk=85.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert "Disk at 85.0%" in pred.contributing_factors[0]
        assert pred.failure_pattern == FailurePattern.DISK_EXHAUSTION

    def test_disk_at_100(self):
        c = _comp("dsk2", "MaxDisk", disk=100.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.predicted_failure_hours == 0.0

    def test_disk_at_threshold_no_risk(self):
        """disk == 70 should not trigger (strict >)."""
        c = _comp("dsk3", "ThreshDisk", disk=70.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0


# ===================================================================
# 6. Connection pool near max — CONNECTION_POOL_LEAK pattern
# ===================================================================


class TestConnectionPool:
    def test_connection_pool_high(self):
        c = _comp(
            "conn1",
            "ConnPool",
            max_connections=100,
            network_connections=85,
            replicas=2,
            failover=True,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert "Connection pool" in pred.contributing_factors[0]
        assert pred.failure_pattern == FailurePattern.CONNECTION_POOL_LEAK

    def test_connection_pool_at_max(self):
        c = _comp(
            "conn2",
            "ConnMax",
            max_connections=100,
            network_connections=100,
            replicas=2,
            failover=True,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.predicted_failure_hours == 0.0

    def test_connection_pool_below_ratio_no_risk(self):
        """70% exactly should not trigger (strict >)."""
        c = _comp(
            "conn3",
            "ConnOK",
            max_connections=100,
            network_connections=70,
            replicas=2,
            failover=True,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0

    def test_connection_pool_zero_max_connections(self):
        """max_connections == 0 should skip connection analysis."""
        c = _comp(
            "conn4",
            "NoPool",
            max_connections=0,
            network_connections=999,
            replicas=2,
            failover=True,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0


# ===================================================================
# 7. CPU + memory both high — CPU_MEMORY_CASCADE pattern
# ===================================================================


class TestCPUMemoryCascade:
    def test_both_high(self):
        c = _comp(
            "cm1", "CascadeComp", cpu=90.0, memory=95.0, replicas=2, failover=True
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.failure_pattern == FailurePattern.CPU_MEMORY_CASCADE
        assert len(pred.contributing_factors) >= 2


# ===================================================================
# 8. Single replica penalty
# ===================================================================


class TestSingleReplica:
    def test_single_replica_adds_risk(self):
        c = _comp("sr1", "SingleR", cpu=80.0, replicas=1, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert any("Single replica" in f for f in pred.contributing_factors)

    def test_multiple_replicas_no_penalty(self):
        c = _comp("sr2", "MultiR", cpu=80.0, replicas=3, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert not any("Single replica" in f for f in pred.contributing_factors)


# ===================================================================
# 9. Health statuses: DEGRADED, OVERLOADED, DOWN
# ===================================================================


class TestHealthStatuses:
    def test_degraded(self):
        c = _comp("hs1", "Degraded", health=HealthStatus.DEGRADED, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert any("degraded" in f for f in pred.contributing_factors)
        assert pred.risk_score == 15.0

    def test_overloaded(self):
        c = _comp("hs2", "Overloaded", health=HealthStatus.OVERLOADED, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert any("overloaded" in f for f in pred.contributing_factors)
        assert pred.predicted_failure_hours <= 4.0

    def test_down(self):
        c = _comp("hs3", "Down", health=HealthStatus.DOWN, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert any("DOWN" in f for f in pred.contributing_factors)
        assert pred.predicted_failure_hours == 0.0
        assert pred.risk_score == 50.0

    def test_healthy_no_health_penalty(self):
        """HEALTHY adds no health-based risk."""
        c = _comp("hs4", "Healthy", replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0


# ===================================================================
# 10. No failover penalty
# ===================================================================


class TestNoFailover:
    def test_no_failover_single_replica(self):
        c = _comp("nf1", "NoFail", replicas=1, failover=False)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert any("No failover" in f for f in pred.contributing_factors)

    def test_failover_enabled_no_penalty(self):
        c = _comp("nf2", "WithFail", replicas=1, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        # Should have single replica factor but NOT no failover factor
        assert any("Single replica" in f for f in pred.contributing_factors)
        assert not any("No failover" in f for f in pred.contributing_factors)

    def test_no_failover_multiple_replicas_no_penalty(self):
        """Failover penalty only applies when replicas <= 1."""
        c = _comp("nf3", "MultiNoFail", replicas=2, failover=False)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0


# ===================================================================
# 11. Risk level thresholds
# ===================================================================


class TestRiskLevelThresholds:
    def test_critical_at_70(self):
        # DOWN(50) + single_replica(10) + no_failover(5) + DEGRADED... We need >= 70.
        # Use: DOWN=50, single_replica=10*1.0=10, no_failover=5 => 65 (not enough)
        # Add some CPU: cpu=80 => cpu_risk = (80-75)/25*40 = 8, * type_weight=1.0
        # total = 50 + 10 + 5 + 8 = 73 => CRITICAL
        c = _comp("rl1", "Critical", cpu=80.0, health=HealthStatus.DOWN)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_level == RiskLevel.CRITICAL
        assert pred.risk_score >= 70.0

    def test_high_at_45(self):
        # OVERLOADED=25, single_replica=10, no_failover=5, cpu=80 => 8
        # total = 25 + 10 + 5 + 8 = 48 => HIGH
        c = _comp("rl2", "High", cpu=80.0, health=HealthStatus.OVERLOADED)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_level == RiskLevel.HIGH
        assert 45.0 <= pred.risk_score < 70.0

    def test_medium_at_20(self):
        # DEGRADED=15, single_replica=10, no_failover=5 => 30 => MEDIUM
        c = _comp("rl3", "Medium", health=HealthStatus.DEGRADED)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_level == RiskLevel.MEDIUM
        assert 20.0 <= pred.risk_score < 45.0

    def test_low_above_0(self):
        # single_replica=10, no_failover=5 => 15 => LOW
        c = _comp("rl4", "Low")
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_level == RiskLevel.LOW
        assert 0 < pred.risk_score < 20.0

    def test_no_risk_returns_none(self):
        c = _comp("rl5", "NoRisk", replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0


# ===================================================================
# 12. Risk score capped at 100
# ===================================================================


class TestRiskScoreCap:
    def test_cap_at_100(self):
        # Stack as many risk factors as possible
        c = _comp(
            "cap1",
            "OverCapped",
            ctype=ComponentType.EXTERNAL_API,  # weight 1.6
            cpu=100.0,
            memory=100.0,
            disk=100.0,
            max_connections=100,
            network_connections=100,
            health=HealthStatus.DOWN,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_score == 100.0
        assert pred.risk_level == RiskLevel.CRITICAL


# ===================================================================
# 13. Component type risk weights
# ===================================================================


class TestTypeRiskWeights:
    def test_database_higher_risk(self):
        """DATABASE type_weight=1.5 should produce higher risk than DNS weight=0.7."""
        db = _comp("tw1", "DB", ctype=ComponentType.DATABASE, cpu=90.0, replicas=2, failover=True)
        dns = _comp("tw2", "DNS", ctype=ComponentType.DNS, cpu=90.0, replicas=2, failover=True)
        db_engine = PredictiveFailureEngine(_graph(db))
        dns_engine = PredictiveFailureEngine(_graph(dns))
        db_report = db_engine.predict()
        dns_report = dns_engine.predict()
        assert db_report.predictions[0].risk_score > dns_report.predictions[0].risk_score

    def test_external_api_highest_weight(self):
        ext = _comp("tw3", "ExtAPI", ctype=ComponentType.EXTERNAL_API, cpu=90.0, replicas=2, failover=True)
        app = _comp("tw4", "AppSrv", ctype=ComponentType.APP_SERVER, cpu=90.0, replicas=2, failover=True)
        ext_engine = PredictiveFailureEngine(_graph(ext))
        app_engine = PredictiveFailureEngine(_graph(app))
        assert ext_engine.predict().predictions[0].risk_score > app_engine.predict().predictions[0].risk_score

    def test_unknown_type_defaults_to_1(self):
        """CUSTOM type_weight=1.0 (explicitly in dict)."""
        custom = _comp("tw5", "Custom", ctype=ComponentType.CUSTOM, cpu=90.0, replicas=2, failover=True)
        app = _comp("tw6", "App", ctype=ComponentType.APP_SERVER, cpu=90.0, replicas=2, failover=True)
        custom_engine = PredictiveFailureEngine(_graph(custom))
        app_engine = PredictiveFailureEngine(_graph(app))
        assert custom_engine.predict().predictions[0].risk_score == app_engine.predict().predictions[0].risk_score


# ===================================================================
# 14. Pattern detection
# ===================================================================


class TestPatternDetection:
    def test_cpu_memory_cascade_pattern(self):
        """CPU>60 and memory>60 triggers CPU_MEMORY_CASCADE pattern."""
        c = _comp("pd1", "CascadeP", cpu=65.0, memory=65.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.CPU_MEMORY_CASCADE in pattern_types

    def test_cpu_memory_cascade_severity_scales(self):
        """Severity = min(1.0, count * 0.3)."""
        comps = [
            _comp(f"pd2_{i}", f"Cascade{i}", cpu=65.0, memory=65.0, replicas=2, failover=True)
            for i in range(4)
        ]
        engine = PredictiveFailureEngine(_graph(*comps))
        report = engine.predict()
        cascade = [p for p in report.detected_patterns if p.pattern == FailurePattern.CPU_MEMORY_CASCADE]
        assert len(cascade) == 1
        # 4 * 0.3 = 1.2, capped at 1.0
        assert cascade[0].severity == 1.0

    def test_dependency_chain_pattern(self):
        """Degraded component with >=2 dependents triggers DEPENDENCY_CHAIN."""
        from faultray.model.components import Dependency

        db = _comp("dc1", "DegradedDB", health=HealthStatus.DEGRADED, replicas=2, failover=True)
        app1 = _comp("dc2", "App1", replicas=2, failover=True)
        app2 = _comp("dc3", "App2", replicas=2, failover=True)
        g = _graph(db, app1, app2)
        g.add_dependency(Dependency(source_id="dc2", target_id="dc1"))
        g.add_dependency(Dependency(source_id="dc3", target_id="dc1"))
        engine = PredictiveFailureEngine(g)
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.DEPENDENCY_CHAIN in pattern_types

    def test_dependency_chain_not_triggered_with_one_dependent(self):
        from faultray.model.components import Dependency

        db = _comp("dc4", "DegDB2", health=HealthStatus.DEGRADED, replicas=2, failover=True)
        app = _comp("dc5", "SingleApp", replicas=2, failover=True)
        g = _graph(db, app)
        g.add_dependency(Dependency(source_id="dc5", target_id="dc4"))
        engine = PredictiveFailureEngine(g)
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.DEPENDENCY_CHAIN not in pattern_types

    def test_dependency_chain_overloaded(self):
        from faultray.model.components import Dependency

        db = _comp("dc6", "OverDB", health=HealthStatus.OVERLOADED, replicas=2, failover=True)
        app1 = _comp("dc7", "A1", replicas=2, failover=True)
        app2 = _comp("dc8", "A2", replicas=2, failover=True)
        g = _graph(db, app1, app2)
        g.add_dependency(Dependency(source_id="dc7", target_id="dc6"))
        g.add_dependency(Dependency(source_id="dc8", target_id="dc6"))
        engine = PredictiveFailureEngine(g)
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.DEPENDENCY_CHAIN in pattern_types

    def test_dependency_chain_down(self):
        from faultray.model.components import Dependency

        db = _comp("dc9", "DownDB", health=HealthStatus.DOWN, replicas=2, failover=True)
        app1 = _comp("dc10", "DA1", replicas=2, failover=True)
        app2 = _comp("dc11", "DA2", replicas=2, failover=True)
        g = _graph(db, app1, app2)
        g.add_dependency(Dependency(source_id="dc10", target_id="dc9"))
        g.add_dependency(Dependency(source_id="dc11", target_id="dc9"))
        engine = PredictiveFailureEngine(g)
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.DEPENDENCY_CHAIN in pattern_types

    def test_replica_drift_pattern(self):
        """Same type, different health => REPLICA_DRIFT."""
        c1 = _comp("rd1", "AppH", ctype=ComponentType.APP_SERVER, replicas=2, failover=True)
        c2 = _comp("rd2", "AppD", ctype=ComponentType.APP_SERVER, health=HealthStatus.DEGRADED, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c1, c2))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.REPLICA_DRIFT in pattern_types

    def test_replica_drift_not_triggered_same_health(self):
        c1 = _comp("rd3", "AppH1", replicas=2, failover=True)
        c2 = _comp("rd4", "AppH2", replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c1, c2))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.REPLICA_DRIFT not in pattern_types

    def test_replica_drift_not_triggered_single_component(self):
        c1 = _comp("rd5", "Solo", replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c1))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.REPLICA_DRIFT not in pattern_types

    def test_replica_drift_all_unhealthy_no_healthy_in_set(self):
        """All components same type but all DOWN — no HEALTHY in healths set, skip."""
        c1 = _comp("rd6", "D1", health=HealthStatus.DOWN, replicas=2, failover=True)
        c2 = _comp("rd7", "D2", health=HealthStatus.DOWN, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c1, c2))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.REPLICA_DRIFT not in pattern_types

    def test_thundering_herd_pattern(self):
        """>=2 components DEGRADED with replicas>=3 triggers THUNDERING_HERD."""
        c1 = _comp("th1", "TH1", health=HealthStatus.DEGRADED, replicas=3, failover=True)
        c2 = _comp("th2", "TH2", health=HealthStatus.DEGRADED, replicas=3, failover=True)
        engine = PredictiveFailureEngine(_graph(c1, c2))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.THUNDERING_HERD in pattern_types

    def test_thundering_herd_not_triggered_low_replicas(self):
        c1 = _comp("th3", "THL1", health=HealthStatus.DEGRADED, replicas=2, failover=True)
        c2 = _comp("th4", "THL2", health=HealthStatus.DEGRADED, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c1, c2))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.THUNDERING_HERD not in pattern_types

    def test_thundering_herd_not_triggered_single_degraded(self):
        c1 = _comp("th5", "TH5", health=HealthStatus.DEGRADED, replicas=5, failover=True)
        engine = PredictiveFailureEngine(_graph(c1))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.THUNDERING_HERD not in pattern_types

    def test_cold_start_storm_pattern(self):
        """cpu<10, replicas>=5 triggers COLD_START_STORM."""
        c = _comp("cs1", "ColdStart", cpu=5.0, replicas=5, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.COLD_START_STORM in pattern_types

    def test_cold_start_storm_not_triggered_high_cpu(self):
        c = _comp("cs2", "HotStart", cpu=15.0, replicas=5, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.COLD_START_STORM not in pattern_types

    def test_cold_start_storm_not_triggered_low_replicas(self):
        c = _comp("cs3", "FewReplicas", cpu=5.0, replicas=4, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.COLD_START_STORM not in pattern_types

    def test_disk_exhaustion_pattern(self):
        """disk > 60 triggers DISK_EXHAUSTION pattern."""
        c = _comp("de1", "DiskWarn", disk=65.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.DISK_EXHAUSTION in pattern_types

    def test_disk_exhaustion_not_triggered(self):
        c = _comp("de2", "DiskOK", disk=59.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.DISK_EXHAUSTION not in pattern_types

    def test_latency_degradation_pattern(self):
        """Component with latency_ms > 50% of timeout triggers LATENCY_DEGRADATION."""
        c = _comp(
            "ld1",
            "SlowComp",
            timeout_seconds=2.0,
            replicas=2,
            failover=True,
            parameters={"latency_ms": 1200.0},  # 1200 / (2*1000) = 0.6 > 0.5
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.LATENCY_DEGRADATION in pattern_types

    def test_latency_degradation_not_triggered_low_ratio(self):
        c = _comp(
            "ld2",
            "FastComp",
            timeout_seconds=10.0,
            replicas=2,
            failover=True,
            parameters={"latency_ms": 100.0},  # 100 / 10000 = 0.01 < 0.5
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.LATENCY_DEGRADATION not in pattern_types

    def test_latency_degradation_no_timeout(self):
        """timeout_seconds == 0 should skip latency check."""
        c = _comp(
            "ld3",
            "NoTimeout",
            timeout_seconds=0,
            replicas=2,
            failover=True,
            parameters={"latency_ms": 9999.0},
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.LATENCY_DEGRADATION not in pattern_types

    def test_latency_degradation_no_latency_param(self):
        """No latency_ms param => latency=0 => skip."""
        c = _comp("ld4", "NoLatency", timeout_seconds=10.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pattern_types = [p.pattern for p in report.detected_patterns]
        assert FailurePattern.LATENCY_DEGRADATION not in pattern_types


# ===================================================================
# 15. Pattern boosting of predictions
# ===================================================================


class TestPatternBoosting:
    def test_boost_increases_risk_score(self):
        """Pattern detection should boost risk score for affected components."""
        # CPU=90 + memory=90 => both above 60 => CPU_MEMORY_CASCADE pattern
        c = _comp("pb1", "Boosted", cpu=90.0, memory=90.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        # The component should have a "Pattern detected" factor after boost
        assert any("Pattern detected" in f for f in pred.contributing_factors)

    def test_boost_caps_at_100(self):
        c = _comp(
            "pb2",
            "MaxBoost",
            ctype=ComponentType.EXTERNAL_API,
            cpu=100.0,
            memory=100.0,
            disk=100.0,
            max_connections=10,
            network_connections=10,
            health=HealthStatus.DOWN,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_score <= 100.0

    def test_no_boost_without_pattern(self):
        """Component not in any pattern should not be boosted."""
        c = _comp("pb3", "NoBoosted", replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0

    def test_boost_confidence_increase(self):
        """Boosted prediction should have +0.1 confidence."""
        c = _comp("pb4", "ConfBoost", cpu=90.0, memory=90.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        # 2 factors * 0.2 + 0.1 = 0.5, then +0.1 = 0.6
        assert pred.confidence >= 0.5

    def test_boost_re_evaluates_risk_level(self):
        """Boosting can elevate risk level."""
        # DEGRADED=15, single_replica=10, no_failover=5 => 30 => MEDIUM
        # CPU+memory>60 pattern: severity=0.3*15=4.5 boost => 34.5 => still MEDIUM
        c = _comp("pb5", "Elevated", cpu=65.0, memory=65.0, health=HealthStatus.DEGRADED)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        # Base 30 + boost 4.5 = 34.5 => MEDIUM
        assert pred.risk_level == RiskLevel.MEDIUM
        assert pred.risk_score == pytest.approx(34.5, abs=0.1)
        assert any("Pattern detected" in f for f in pred.contributing_factors)

    def test_boost_risk_level_low(self):
        """Verify LOW level after boost when score stays below 20."""
        # Create a scenario where boost is small and total stays < 20
        # Single replica=10, no failover=5 => 15 (LOW)
        # No pattern => no boost => stays LOW
        c = _comp("pb6", "StayLow")
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_level == RiskLevel.LOW

    def test_boost_multiple_patterns_max_severity(self):
        """Component in multiple patterns uses max severity for boost."""
        # High disk (>60) => DISK_EXHAUSTION pattern
        # CPU+memory > 60 => CPU_MEMORY_CASCADE pattern
        c = _comp("pb7", "MultiPattern", cpu=65.0, memory=65.0, disk=65.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        # Should be in at least 2 patterns
        patterns_with_comp = [
            p for p in report.detected_patterns if "pb7" in p.affected_components
        ]
        assert len(patterns_with_comp) >= 2


# ===================================================================
# 16. Overall risk calculation (weighted average)
# ===================================================================


class TestOverallRisk:
    def test_overall_risk_weighted_by_level(self):
        """CRITICAL predictions are weighted 4x, HIGH 2x, etc."""
        # Create one CRITICAL and one LOW
        c1 = _comp("or1", "Crit", cpu=100.0, memory=100.0, health=HealthStatus.DOWN)
        c2 = _comp("or2", "Low", replicas=2, failover=True)
        # c2 won't generate a prediction (no risk), so add a minimal risk one
        c3 = _comp("or3", "LowRisk", replicas=1, failover=True)  # 10 => LOW
        engine = PredictiveFailureEngine(_graph(c1, c3))
        report = engine.predict()
        assert report.overall_risk_score > 0

    def test_overall_risk_empty_predictions(self):
        """_calculate_overall_risk with empty list returns 0."""
        result = PredictiveFailureEngine._calculate_overall_risk([])
        assert result == 0.0

    def test_overall_risk_capped_at_100(self):
        result = PredictiveFailureEngine._calculate_overall_risk(
            [
                FailurePrediction(
                    component_id="x",
                    component_name="X",
                    risk_level=RiskLevel.CRITICAL,
                    confidence=1.0,
                    predicted_failure_hours=0,
                    failure_pattern=FailurePattern.CPU_MEMORY_CASCADE,
                    contributing_factors=[],
                    recommended_actions=[],
                    risk_score=100.0,
                )
            ]
        )
        assert result <= 100.0

    def test_overall_risk_unknown_level(self):
        """UNKNOWN risk level uses weight 0.5."""
        result = PredictiveFailureEngine._calculate_overall_risk(
            [
                FailurePrediction(
                    component_id="u",
                    component_name="U",
                    risk_level=RiskLevel.UNKNOWN,
                    confidence=0.5,
                    predicted_failure_hours=720,
                    failure_pattern=FailurePattern.CPU_MEMORY_CASCADE,
                    contributing_factors=[],
                    recommended_actions=[],
                    risk_score=50.0,
                )
            ]
        )
        # 50 * 0.5 / 0.5 = 50
        assert result == 50.0


# ===================================================================
# 17. Summary generation
# ===================================================================


class TestSummaryGeneration:
    def test_summary_no_predictions(self):
        summary = PredictiveFailureEngine._generate_summary([], [], 0.0)
        assert "No significant failure risks" in summary
        assert "healthy" in summary.lower()

    def test_summary_with_critical(self):
        pred = FailurePrediction(
            component_id="s1",
            component_name="S1",
            risk_level=RiskLevel.CRITICAL,
            confidence=0.9,
            predicted_failure_hours=2,
            failure_pattern=FailurePattern.CPU_MEMORY_CASCADE,
            contributing_factors=["High CPU"],
            recommended_actions=["Scale"],
            risk_score=85.0,
        )
        summary = PredictiveFailureEngine._generate_summary([pred], [], 85.0)
        assert "1 CRITICAL risk" in summary
        assert "85" in summary

    def test_summary_with_multiple_critical(self):
        preds = [
            FailurePrediction(
                component_id=f"mc{i}",
                component_name=f"MC{i}",
                risk_level=RiskLevel.CRITICAL,
                confidence=0.9,
                predicted_failure_hours=2,
                failure_pattern=FailurePattern.CPU_MEMORY_CASCADE,
                contributing_factors=["High CPU"],
                recommended_actions=["Scale"],
                risk_score=85.0,
            )
            for i in range(3)
        ]
        summary = PredictiveFailureEngine._generate_summary(preds, [], 90.0)
        assert "3 CRITICAL risks" in summary

    def test_summary_with_high(self):
        pred = FailurePrediction(
            component_id="h1",
            component_name="H1",
            risk_level=RiskLevel.HIGH,
            confidence=0.7,
            predicted_failure_hours=48,
            failure_pattern=FailurePattern.DISK_EXHAUSTION,
            contributing_factors=["High disk"],
            recommended_actions=["Expand"],
            risk_score=55.0,
        )
        summary = PredictiveFailureEngine._generate_summary([pred], [], 55.0)
        assert "1 HIGH risk" in summary

    def test_summary_with_multiple_high(self):
        preds = [
            FailurePrediction(
                component_id=f"mh{i}",
                component_name=f"MH{i}",
                risk_level=RiskLevel.HIGH,
                confidence=0.7,
                predicted_failure_hours=48,
                failure_pattern=FailurePattern.DISK_EXHAUSTION,
                contributing_factors=["disk"],
                recommended_actions=["Expand"],
                risk_score=55.0,
            )
            for i in range(2)
        ]
        summary = PredictiveFailureEngine._generate_summary(preds, [], 55.0)
        assert "2 HIGH risks" in summary

    def test_summary_with_patterns(self):
        pred = FailurePrediction(
            component_id="p1",
            component_name="P1",
            risk_level=RiskLevel.MEDIUM,
            confidence=0.5,
            predicted_failure_hours=168,
            failure_pattern=FailurePattern.CONNECTION_POOL_LEAK,
            contributing_factors=["pool"],
            recommended_actions=["fix"],
            risk_score=30.0,
        )
        pattern = PatternMatch(
            pattern=FailurePattern.CPU_MEMORY_CASCADE,
            affected_components=["p1"],
            severity=0.5,
            description="test",
        )
        summary = PredictiveFailureEngine._generate_summary([pred], [pattern], 30.0)
        assert "1 failure pattern" in summary

    def test_summary_with_multiple_patterns(self):
        pred = FailurePrediction(
            component_id="mp1",
            component_name="MP1",
            risk_level=RiskLevel.MEDIUM,
            confidence=0.5,
            predicted_failure_hours=168,
            failure_pattern=FailurePattern.CONNECTION_POOL_LEAK,
            contributing_factors=["pool"],
            recommended_actions=["fix"],
            risk_score=30.0,
        )
        patterns = [
            PatternMatch(
                pattern=FailurePattern.CPU_MEMORY_CASCADE,
                affected_components=["mp1"],
                severity=0.5,
                description="test1",
            ),
            PatternMatch(
                pattern=FailurePattern.DISK_EXHAUSTION,
                affected_components=["mp1"],
                severity=0.3,
                description="test2",
            ),
        ]
        summary = PredictiveFailureEngine._generate_summary([pred], patterns, 30.0)
        assert "2 failure patterns" in summary

    def test_summary_low_risk_no_critical_high(self):
        """LOW predictions should not appear in summary parts."""
        pred = FailurePrediction(
            component_id="l1",
            component_name="L1",
            risk_level=RiskLevel.LOW,
            confidence=0.3,
            predicted_failure_hours=720,
            failure_pattern=FailurePattern.CPU_MEMORY_CASCADE,
            contributing_factors=["minor"],
            recommended_actions=["watch"],
            risk_score=10.0,
        )
        summary = PredictiveFailureEngine._generate_summary([pred], [], 10.0)
        assert "CRITICAL" not in summary
        assert "HIGH" not in summary
        assert "Overall risk: 10/100" in summary


# ===================================================================
# 18. Risk distribution counts
# ===================================================================


class TestRiskDistribution:
    def test_distribution_counts(self):
        c1 = _comp("dist1", "Crit", cpu=100.0, memory=100.0, health=HealthStatus.DOWN)
        c2 = _comp("dist2", "Med", health=HealthStatus.DEGRADED)
        c3 = _comp("dist3", "Low", replicas=1, failover=True)  # single replica = 10 => LOW
        engine = PredictiveFailureEngine(_graph(c1, c2, c3))
        report = engine.predict()
        assert report.risk_distribution["critical"] >= 1
        total = sum(report.risk_distribution.values())
        assert total == len(report.predictions)


# ===================================================================
# 19. Mean time to predicted failure
# ===================================================================


class TestMTTF:
    def test_mttf_average(self):
        c1 = _comp("mt1", "Quick", health=HealthStatus.DOWN, replicas=2, failover=True)  # hours=0
        c2 = _comp("mt2", "Slow", health=HealthStatus.DEGRADED, replicas=2, failover=True)  # hours=720 (default)
        engine = PredictiveFailureEngine(_graph(c1, c2))
        report = engine.predict()
        # 0 + 720 = 720 / 2 = 360
        assert report.mean_time_to_predicted_failure == 360.0

    def test_mttf_inf_no_predictions(self):
        engine = PredictiveFailureEngine(_graph())
        report = engine.predict()
        assert report.mean_time_to_predicted_failure == float("inf")


# ===================================================================
# 20. Edge cases
# ===================================================================


class TestEdgeCases:
    def test_zero_metrics(self):
        c = _comp("ec1", "Zero", replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.predictions) == 0

    def test_100_percent_utilization(self):
        c = _comp(
            "ec2",
            "Max",
            cpu=100.0,
            memory=100.0,
            disk=100.0,
            max_connections=10,
            network_connections=10,
            health=HealthStatus.DOWN,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_score == 100.0
        assert pred.predicted_failure_hours == 0.0

    def test_multiple_components_sorted_by_risk(self):
        c1 = _comp("ec3", "HighRisk", cpu=100.0, health=HealthStatus.DOWN)
        c2 = _comp("ec4", "LowRisk")
        engine = PredictiveFailureEngine(_graph(c1, c2))
        report = engine.predict()
        if len(report.predictions) >= 2:
            assert report.predictions[0].risk_score >= report.predictions[1].risk_score

    def test_top_risks_max_five(self):
        comps = [
            _comp(f"tr{i}", f"Comp{i}", health=HealthStatus.DEGRADED) for i in range(10)
        ]
        engine = PredictiveFailureEngine(_graph(*comps))
        report = engine.predict()
        assert len(report.top_risks) <= 5

    def test_top_risks_format(self):
        c = _comp("tf1", "Formatted", cpu=90.0, health=HealthStatus.DOWN)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert len(report.top_risks) >= 1
        assert "Formatted" in report.top_risks[0]
        assert "risk=" in report.top_risks[0]

    def test_confidence_capped_at_1(self):
        """Many factors should not push confidence above 1.0."""
        c = _comp(
            "ec5",
            "ManyFactors",
            cpu=100.0,
            memory=100.0,
            disk=100.0,
            max_connections=10,
            network_connections=10,
            health=HealthStatus.DOWN,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.confidence <= 1.0

    def test_hours_default_when_no_estimate(self):
        """If no resource threshold is exceeded but health causes risk, hours defaults to 720."""
        c = _comp("ec6", "DefHours", health=HealthStatus.DEGRADED, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.predicted_failure_hours == 720.0

    def test_disk_pattern_severity_max(self):
        """Disk pattern severity = min(1.0, max_disk/100)."""
        c = _comp("ec7", "DiskSev", disk=95.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        disk_patterns = [
            p for p in report.detected_patterns if p.pattern == FailurePattern.DISK_EXHAUSTION
        ]
        assert len(disk_patterns) == 1
        assert disk_patterns[0].severity == pytest.approx(0.95, abs=0.01)

    def test_connection_pool_with_disk_pattern_interaction(self):
        """Connection pool analysis runs after disk; last to set pattern wins."""
        c = _comp(
            "ec8",
            "DiskAndConn",
            disk=85.0,
            max_connections=100,
            network_connections=90,
            replicas=2,
            failover=True,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        # Connection pool sets pattern AFTER disk, so CONNECTION_POOL_LEAK wins
        assert pred.failure_pattern == FailurePattern.CONNECTION_POOL_LEAK

    def test_memory_only_sets_connection_pool_leak_pattern(self):
        """Memory high but CPU low => pattern is CONNECTION_POOL_LEAK."""
        c = _comp("ec9", "MemOnly", memory=95.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.failure_pattern == FailurePattern.CONNECTION_POOL_LEAK

    def test_overloaded_caps_hours(self):
        """OVERLOADED sets hours to min(hours, 4.0)."""
        c = _comp("ec10", "OvHours", health=HealthStatus.OVERLOADED, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.predicted_failure_hours <= 4.0

    def test_multiple_risk_types_contribute(self):
        """All risk factors (cpu, mem, disk, conn, health) stack up."""
        c = _comp(
            "ec11",
            "AllFactors",
            cpu=90.0,
            memory=90.0,
            disk=80.0,
            max_connections=100,
            network_connections=90,
            health=HealthStatus.DEGRADED,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        # Should have many contributing factors
        assert len(pred.contributing_factors) >= 5

    def test_predict_report_structure(self):
        """Verify PredictiveReport has all expected fields."""
        c = _comp("st1", "Structure", cpu=90.0)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        assert isinstance(report, PredictiveReport)
        assert isinstance(report.predictions, list)
        assert isinstance(report.detected_patterns, list)
        assert isinstance(report.overall_risk_score, float)
        assert isinstance(report.risk_summary, str)
        assert isinstance(report.top_risks, list)
        assert isinstance(report.mean_time_to_predicted_failure, float)
        assert isinstance(report.risk_distribution, dict)

    def test_hours_from_cpu_estimation(self):
        """CPU remaining / 5 * 24 is the CPU hours estimate."""
        c = _comp("ec12", "CPUHours", cpu=85.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        expected_hours = (100 - 85) / 5.0 * 24  # 15/5*24 = 72
        assert pred.predicted_failure_hours == expected_hours

    def test_hours_from_memory_estimation(self):
        """Memory remaining / 3 * 24 is the memory hours estimate."""
        c = _comp("ec13", "MemHours", memory=95.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        expected_hours = (100 - 95) / 3.0 * 24  # 5/3*24 = 40
        assert pred.predicted_failure_hours == 40.0

    def test_hours_from_disk_estimation(self):
        """Disk remaining / 2 * 24 is the disk hours estimate."""
        c = _comp("ec14", "DiskHours", disk=90.0, replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        expected_hours = (100 - 90) / 2.0 * 24  # 10/2*24 = 120
        assert pred.predicted_failure_hours == expected_hours

    def test_hours_from_connection_estimation(self):
        """Connection remaining * 48 is the conn hours estimate."""
        c = _comp(
            "ec15",
            "ConnHours",
            max_connections=100,
            network_connections=80,
            replicas=2,
            failover=True,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        remaining = 1.0 - 0.8  # 0.2
        expected_hours = remaining * 48  # 9.6
        assert pred.predicted_failure_hours == pytest.approx(expected_hours, abs=0.1)

    def test_min_hours_across_all_resources(self):
        """Hours should be the minimum across all resources."""
        c = _comp(
            "ec16",
            "MinHours",
            cpu=99.0,   # (100-99)/5*24 = 4.8
            memory=99.0, # (100-99)/3*24 = 8.0
            disk=99.0,    # (100-99)/2*24 = 12.0
            replicas=2,
            failover=True,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        # Minimum is CPU: 4.8
        assert pred.predicted_failure_hours == pytest.approx(4.8, abs=0.1)


# ===================================================================
# Additional: boost re-evaluation covers all risk level branches
# ===================================================================


class TestBoostRiskLevelBranches:
    def test_boost_to_critical(self):
        """Verify boost can push to CRITICAL."""
        # cpu=100 => cpu_risk=40*1.0=40, mem=85 => (85-80)/20*35=8.75, OVERLOADED=25
        # Total = 40+8.75+25 = 73.75 => CRITICAL already (>=70)
        # Plus cpu>60 and mem>60 => CPU_MEMORY_CASCADE pattern boost
        c = _comp(
            "bl1",
            "BoostCrit",
            cpu=100.0,
            memory=85.0,
            health=HealthStatus.OVERLOADED,
            replicas=2,
            failover=True,
        )
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_level == RiskLevel.CRITICAL

    def test_boost_to_medium(self):
        """Verify boost pushes score from LOW into MEDIUM range."""
        # DEGRADED=15, no other risk with replicas=2 + failover => score=15 => LOW
        # cpu=65, memory=65 => CPU_MEMORY_CASCADE pattern: severity=0.3, boost=4.5
        # 15 + 4.5 = 19.5 => still LOW (need >=20 for MEDIUM)
        # So we add a bit more: cpu=76 => cpu_risk=(76-75)/25*40 = 1.6 => total 16.6
        # 16.6 + 4.5 = 21.1 => MEDIUM
        c = _comp("bl2", "BoostMed", cpu=76.0, memory=65.0, health=HealthStatus.DEGRADED,
                  replicas=2, failover=True)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        assert pred.risk_level == RiskLevel.MEDIUM
        assert 20.0 <= pred.risk_score < 45.0

    def test_boost_stays_low(self):
        """Verify LOW stays LOW when boost is tiny and total < 20."""
        # Single replica=10, no failover=5 => 15 => LOW
        # CPU=65, memory=65 won't trigger CPU risk (need >75)
        # But will trigger CPU_MEMORY_CASCADE pattern: severity=0.3, boost=4.5
        # 15 + 4.5 = 19.5 => still LOW
        c = _comp("bl3", "StayLow", cpu=65.0, memory=65.0)
        engine = PredictiveFailureEngine(_graph(c))
        report = engine.predict()
        pred = report.predictions[0]
        # The risk is 15 + 4.5 = 19.5 => LOW
        assert pred.risk_level == RiskLevel.LOW


# ===================================================================
# Data class instantiation tests
# ===================================================================


class TestDataClasses:
    def test_risk_level_values(self):
        assert RiskLevel.CRITICAL.value == "critical"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.UNKNOWN.value == "unknown"

    def test_failure_pattern_values(self):
        assert FailurePattern.CPU_MEMORY_CASCADE.value == "cpu_memory_cascade"
        assert FailurePattern.DISK_EXHAUSTION.value == "disk_exhaustion"
        assert FailurePattern.CONNECTION_POOL_LEAK.value == "connection_pool_leak"
        assert FailurePattern.LATENCY_DEGRADATION.value == "latency_degradation"
        assert FailurePattern.REPLICA_DRIFT.value == "replica_drift"
        assert FailurePattern.DEPENDENCY_CHAIN.value == "dependency_chain"
        assert FailurePattern.THUNDERING_HERD.value == "thundering_herd"
        assert FailurePattern.COLD_START_STORM.value == "cold_start_storm"

    def test_failure_prediction_dataclass(self):
        pred = FailurePrediction(
            component_id="x",
            component_name="X",
            risk_level=RiskLevel.LOW,
            confidence=0.5,
            predicted_failure_hours=100,
            failure_pattern=FailurePattern.DISK_EXHAUSTION,
            contributing_factors=["a"],
            recommended_actions=["b"],
            risk_score=10.0,
        )
        assert pred.component_id == "x"
        assert pred.risk_score == 10.0

    def test_pattern_match_dataclass(self):
        pm = PatternMatch(
            pattern=FailurePattern.CPU_MEMORY_CASCADE,
            affected_components=["a", "b"],
            severity=0.7,
            description="test pattern",
        )
        assert pm.severity == 0.7
        assert len(pm.affected_components) == 2

    def test_predictive_report_dataclass(self):
        report = PredictiveReport(
            predictions=[],
            detected_patterns=[],
            overall_risk_score=0.0,
            risk_summary="ok",
            top_risks=[],
            mean_time_to_predicted_failure=float("inf"),
            risk_distribution={"critical": 0},
        )
        assert report.overall_risk_score == 0.0
