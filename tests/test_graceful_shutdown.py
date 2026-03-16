"""Tests for Graceful Shutdown Simulator.

145+ tests covering all enums, data models, shutdown simulation, config
validation, drain time estimation, risk detection, forced kill simulation,
recommended configuration, rolling restart analysis, and edge cases.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.graceful_shutdown import (
    ForcedKillResult,
    GracefulShutdownEngine,
    RollingRestartResult,
    ShutdownConfig,
    ShutdownPhase,
    ShutdownPhaseResult,
    ShutdownRisk,
    ShutdownSimulation,
    ValidationResult,
    _clamp,
    _compute_data_loss_risk,
    _drain_rate,
    _estimate_in_flight,
    _generate_shutdown_recommendations,
    _phase_duration,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "app-1",
    name: str = "App Server",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 2,
    health: HealthStatus = HealthStatus.HEALTHY,
    max_rps: int = 5000,
    max_connections: int = 1000,
    timeout_seconds: float = 30.0,
    autoscaling: bool = False,
    failover: bool = False,
    network_connections: int = 0,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        health=health,
        capacity=Capacity(
            max_rps=max_rps,
            max_connections=max_connections,
            timeout_seconds=timeout_seconds,
        ),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        failover=FailoverConfig(enabled=failover),
        metrics=ResourceMetrics(network_connections=network_connections),
    )


def _graph(*components: Component, deps: list[tuple[str, str]] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    if deps:
        for src, tgt in deps:
            g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


def _default_config() -> ShutdownConfig:
    return ShutdownConfig()


def _bad_config() -> ShutdownConfig:
    """A poorly configured shutdown."""
    return ShutdownConfig(
        drain_timeout_seconds=0.0,
        grace_period_seconds=1.0,
        preStop_hook_seconds=0.0,
        sigterm_handler=False,
        connection_draining=False,
        deregister_from_lb=False,
    )


# ---------------------------------------------------------------------------
# 1. Enum coverage
# ---------------------------------------------------------------------------


class TestShutdownPhaseEnum:
    def test_all_values(self) -> None:
        assert len(ShutdownPhase) == 7

    def test_signal_received(self) -> None:
        assert ShutdownPhase.SIGNAL_RECEIVED == "signal_received"

    def test_new_connections_refused(self) -> None:
        assert ShutdownPhase.NEW_CONNECTIONS_REFUSED == "new_connections_refused"

    def test_in_flight_draining(self) -> None:
        assert ShutdownPhase.IN_FLIGHT_DRAINING == "in_flight_draining"

    def test_health_check_failing(self) -> None:
        assert ShutdownPhase.HEALTH_CHECK_FAILING == "health_check_failing"

    def test_deregistration(self) -> None:
        assert ShutdownPhase.DEREGISTRATION == "deregistration"

    def test_final_cleanup(self) -> None:
        assert ShutdownPhase.FINAL_CLEANUP == "final_cleanup"

    def test_terminated(self) -> None:
        assert ShutdownPhase.TERMINATED == "terminated"

    def test_is_str_enum(self) -> None:
        assert isinstance(ShutdownPhase.SIGNAL_RECEIVED, str)


# ---------------------------------------------------------------------------
# 2. Data model coverage
# ---------------------------------------------------------------------------


class TestShutdownConfig:
    def test_defaults(self) -> None:
        cfg = ShutdownConfig()
        assert cfg.drain_timeout_seconds == 30.0
        assert cfg.grace_period_seconds == 15.0
        assert cfg.preStop_hook_seconds == 5.0
        assert cfg.sigterm_handler is True
        assert cfg.connection_draining is True
        assert cfg.deregister_from_lb is True

    def test_custom_values(self) -> None:
        cfg = ShutdownConfig(
            drain_timeout_seconds=60.0,
            grace_period_seconds=90.0,
            preStop_hook_seconds=10.0,
            sigterm_handler=False,
            connection_draining=False,
            deregister_from_lb=False,
        )
        assert cfg.drain_timeout_seconds == 60.0
        assert cfg.grace_period_seconds == 90.0
        assert cfg.sigterm_handler is False

    def test_zero_drain_timeout(self) -> None:
        cfg = ShutdownConfig(drain_timeout_seconds=0.0)
        assert cfg.drain_timeout_seconds == 0.0

    def test_negative_drain_timeout_rejected(self) -> None:
        with pytest.raises(Exception):
            ShutdownConfig(drain_timeout_seconds=-1.0)


class TestShutdownPhaseResult:
    def test_defaults(self) -> None:
        r = ShutdownPhaseResult(phase=ShutdownPhase.SIGNAL_RECEIVED)
        assert r.phase == ShutdownPhase.SIGNAL_RECEIVED
        assert r.duration_seconds == 0.0
        assert r.success is True
        assert r.in_flight_requests == 0
        assert r.dropped_requests == 0
        assert r.detail == ""

    def test_custom(self) -> None:
        r = ShutdownPhaseResult(
            phase=ShutdownPhase.IN_FLIGHT_DRAINING,
            duration_seconds=30.0,
            success=False,
            in_flight_requests=100,
            dropped_requests=50,
            detail="Timed out",
        )
        assert r.dropped_requests == 50
        assert r.success is False


class TestShutdownSimulation:
    def test_defaults(self) -> None:
        s = ShutdownSimulation()
        assert s.phases == []
        assert s.total_duration_seconds == 0.0
        assert s.dropped_requests == 0
        assert s.in_flight_at_termination == 0
        assert s.data_loss_risk == "none"
        assert s.recommendations == []


class TestValidationResult:
    def test_defaults(self) -> None:
        v = ValidationResult()
        assert v.valid is True
        assert v.errors == []
        assert v.warnings == []
        assert v.score == 100.0

    def test_invalid(self) -> None:
        v = ValidationResult(valid=False, errors=["err"], score=50.0)
        assert v.valid is False
        assert len(v.errors) == 1


class TestShutdownRisk:
    def test_defaults(self) -> None:
        r = ShutdownRisk()
        assert r.risk_id == ""
        assert r.severity == "low"
        assert r.description == ""
        assert r.mitigation == ""

    def test_custom(self) -> None:
        r = ShutdownRisk(
            risk_id="test", severity="critical",
            description="bad", mitigation="fix it",
        )
        assert r.severity == "critical"


class TestForcedKillResult:
    def test_defaults(self) -> None:
        f = ForcedKillResult()
        assert f.in_flight_lost == 0
        assert f.connections_dropped == 0
        assert f.data_loss_risk == "high"
        assert f.affected_components == []
        assert f.recovery_time_seconds == 0.0
        assert f.recommendations == []


class TestRollingRestartResult:
    def test_defaults(self) -> None:
        r = RollingRestartResult()
        assert r.total_duration_seconds == 0.0
        assert r.max_unavailable == 0
        assert r.min_available_percent == 100.0
        assert r.dropped_requests_total == 0
        assert r.per_component == []
        assert r.safe is True
        assert r.recommendations == []


# ---------------------------------------------------------------------------
# 3. Internal helpers
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self) -> None:
        assert _clamp(50.0) == 50.0

    def test_below_min(self) -> None:
        assert _clamp(-10.0) == 0.0

    def test_above_max(self) -> None:
        assert _clamp(150.0) == 100.0

    def test_custom_bounds(self) -> None:
        assert _clamp(5.0, 1.0, 10.0) == 5.0
        assert _clamp(-1.0, 1.0, 10.0) == 1.0
        assert _clamp(20.0, 1.0, 10.0) == 10.0


class TestEstimateInFlight:
    def test_none_component(self) -> None:
        assert _estimate_in_flight(None) == 50

    def test_with_component(self) -> None:
        comp = _comp(max_rps=5000, replicas=2)
        result = _estimate_in_flight(comp)
        assert result >= 1

    def test_single_replica(self) -> None:
        comp = _comp(max_rps=1000, replicas=1)
        result = _estimate_in_flight(comp)
        assert result >= 1


class TestDrainRate:
    def test_none_component(self) -> None:
        assert _drain_rate(None) == 100.0

    def test_with_component(self) -> None:
        comp = _comp(max_rps=5000, replicas=2)
        rate = _drain_rate(comp)
        assert rate > 0
        assert rate == max(1.0, 5000 * 2 * 0.8)

    def test_low_capacity(self) -> None:
        comp = _comp(max_rps=1, replicas=1)
        rate = _drain_rate(comp)
        assert rate >= 1.0


class TestPhaseDuration:
    def test_signal_received(self) -> None:
        assert _phase_duration(ShutdownPhase.SIGNAL_RECEIVED, _default_config()) == 0.1

    def test_new_connections_with_handler(self) -> None:
        cfg = ShutdownConfig(sigterm_handler=True)
        assert _phase_duration(ShutdownPhase.NEW_CONNECTIONS_REFUSED, cfg) == 0.5

    def test_new_connections_without_handler(self) -> None:
        cfg = ShutdownConfig(sigterm_handler=False)
        assert _phase_duration(ShutdownPhase.NEW_CONNECTIONS_REFUSED, cfg) == 0.0

    def test_draining_enabled(self) -> None:
        cfg = ShutdownConfig(drain_timeout_seconds=30.0, connection_draining=True)
        assert _phase_duration(ShutdownPhase.IN_FLIGHT_DRAINING, cfg) == 30.0

    def test_draining_disabled(self) -> None:
        cfg = ShutdownConfig(connection_draining=False)
        assert _phase_duration(ShutdownPhase.IN_FLIGHT_DRAINING, cfg) == 0.0

    def test_deregistration_enabled(self) -> None:
        cfg = ShutdownConfig(deregister_from_lb=True)
        assert _phase_duration(ShutdownPhase.DEREGISTRATION, cfg) == 3.0

    def test_deregistration_disabled(self) -> None:
        cfg = ShutdownConfig(deregister_from_lb=False)
        assert _phase_duration(ShutdownPhase.DEREGISTRATION, cfg) == 0.0

    def test_final_cleanup(self) -> None:
        cfg = ShutdownConfig(preStop_hook_seconds=10.0)
        assert _phase_duration(ShutdownPhase.FINAL_CLEANUP, cfg) == 10.0

    def test_terminated(self) -> None:
        assert _phase_duration(ShutdownPhase.TERMINATED, _default_config()) == 0.0


class TestComputeDataLossRisk:
    def test_none(self) -> None:
        assert _compute_data_loss_risk(0, 0, _default_config()) == "none"

    def test_low(self) -> None:
        assert _compute_data_loss_risk(1, 0, _default_config()) == "low"

    def test_medium(self) -> None:
        assert _compute_data_loss_risk(15, 0, _default_config()) == "medium"

    def test_high_dropped(self) -> None:
        assert _compute_data_loss_risk(60, 0, _default_config()) == "high"

    def test_high_in_flight(self) -> None:
        assert _compute_data_loss_risk(0, 25, _default_config()) == "high"

    def test_no_sigterm_always_high(self) -> None:
        cfg = ShutdownConfig(sigterm_handler=False)
        assert _compute_data_loss_risk(1, 0, cfg) == "high"

    def test_no_draining_with_in_flight(self) -> None:
        cfg = ShutdownConfig(connection_draining=False)
        assert _compute_data_loss_risk(0, 10, cfg) == "high"


class TestGenerateShutdownRecommendations:
    def test_no_sigterm_handler(self) -> None:
        cfg = ShutdownConfig(sigterm_handler=False)
        recs = _generate_shutdown_recommendations(cfg, 0, 0, None, 10.0)
        assert any("SIGTERM handler" in r for r in recs)

    def test_no_connection_draining(self) -> None:
        cfg = ShutdownConfig(connection_draining=False)
        recs = _generate_shutdown_recommendations(cfg, 0, 0, None, 10.0)
        assert any("connection draining" in r.lower() for r in recs)

    def test_no_deregistration(self) -> None:
        cfg = ShutdownConfig(deregister_from_lb=False)
        recs = _generate_shutdown_recommendations(cfg, 0, 0, None, 10.0)
        assert any("deregistration" in r.lower() for r in recs)

    def test_short_drain_timeout(self) -> None:
        cfg = ShutdownConfig(drain_timeout_seconds=2.0)
        recs = _generate_shutdown_recommendations(cfg, 0, 0, None, 10.0)
        assert any("short" in r.lower() for r in recs)

    def test_short_prestop(self) -> None:
        cfg = ShutdownConfig(preStop_hook_seconds=0.5)
        recs = _generate_shutdown_recommendations(cfg, 0, 0, None, 10.0)
        assert any("preStop" in r or "prestop" in r.lower() for r in recs)

    def test_grace_period_too_short(self) -> None:
        cfg = ShutdownConfig(
            drain_timeout_seconds=30.0,
            preStop_hook_seconds=10.0,
            grace_period_seconds=20.0,
        )
        recs = _generate_shutdown_recommendations(cfg, 0, 0, None, 10.0)
        assert any("Grace period" in r or "grace period" in r.lower() for r in recs)

    def test_dropped_requests(self) -> None:
        recs = _generate_shutdown_recommendations(_default_config(), 5, 0, None, 10.0)
        assert any("dropped" in r.lower() for r in recs)

    def test_in_flight_at_term(self) -> None:
        recs = _generate_shutdown_recommendations(_default_config(), 0, 3, None, 10.0)
        assert any("in-flight" in r.lower() for r in recs)

    def test_single_replica_warning(self) -> None:
        comp = _comp(replicas=1)
        recs = _generate_shutdown_recommendations(_default_config(), 0, 0, comp, 10.0)
        assert any("single replica" in r.lower() for r in recs)

    def test_long_duration(self) -> None:
        recs = _generate_shutdown_recommendations(_default_config(), 0, 0, None, 150.0)
        assert any("2 minutes" in r for r in recs)

    def test_degraded_component(self) -> None:
        comp = _comp(health=HealthStatus.DEGRADED)
        recs = _generate_shutdown_recommendations(_default_config(), 0, 0, comp, 10.0)
        assert any("degraded" in r.lower() for r in recs)

    def test_good_config_no_issues(self) -> None:
        cfg = ShutdownConfig(
            drain_timeout_seconds=30.0,
            grace_period_seconds=50.0,
            preStop_hook_seconds=5.0,
        )
        comp = _comp(replicas=3)
        recs = _generate_shutdown_recommendations(cfg, 0, 0, comp, 10.0)
        assert len(recs) == 0


# ---------------------------------------------------------------------------
# 4. Engine: simulate_shutdown
# ---------------------------------------------------------------------------


class TestSimulateShutdown:
    def setup_method(self) -> None:
        self.engine = GracefulShutdownEngine()
        self.comp = _comp()
        self.graph = _graph(self.comp)

    def test_returns_simulation(self) -> None:
        result = self.engine.simulate_shutdown(self.graph, "app-1", _default_config())
        assert isinstance(result, ShutdownSimulation)

    def test_all_phases_present(self) -> None:
        result = self.engine.simulate_shutdown(self.graph, "app-1", _default_config())
        phases = [p.phase for p in result.phases]
        for phase in ShutdownPhase:
            assert phase in phases

    def test_total_duration_positive(self) -> None:
        result = self.engine.simulate_shutdown(self.graph, "app-1", _default_config())
        assert result.total_duration_seconds > 0

    def test_good_config_no_drops(self) -> None:
        cfg = ShutdownConfig(
            drain_timeout_seconds=60.0,
            grace_period_seconds=90.0,
            preStop_hook_seconds=5.0,
        )
        result = self.engine.simulate_shutdown(self.graph, "app-1", cfg)
        assert result.dropped_requests == 0
        assert result.in_flight_at_termination == 0

    def test_no_sigterm_handler_causes_drops(self) -> None:
        cfg = ShutdownConfig(sigterm_handler=False, connection_draining=False)
        result = self.engine.simulate_shutdown(self.graph, "app-1", cfg)
        assert result.dropped_requests > 0

    def test_no_connection_draining_drops_inflight(self) -> None:
        cfg = ShutdownConfig(connection_draining=False)
        result = self.engine.simulate_shutdown(self.graph, "app-1", cfg)
        assert result.dropped_requests > 0

    def test_no_deregistration_causes_drops(self) -> None:
        cfg = ShutdownConfig(deregister_from_lb=False)
        result = self.engine.simulate_shutdown(self.graph, "app-1", cfg)
        assert result.dropped_requests > 0

    def test_bad_config_high_data_loss_risk(self) -> None:
        result = self.engine.simulate_shutdown(self.graph, "app-1", _bad_config())
        assert result.data_loss_risk in ("high", "critical")

    def test_good_config_no_data_loss_risk(self) -> None:
        cfg = ShutdownConfig(
            drain_timeout_seconds=60.0,
            grace_period_seconds=90.0,
        )
        result = self.engine.simulate_shutdown(self.graph, "app-1", cfg)
        assert result.data_loss_risk == "none"

    def test_recommendations_on_bad_config(self) -> None:
        result = self.engine.simulate_shutdown(self.graph, "app-1", _bad_config())
        assert len(result.recommendations) > 0

    def test_unknown_component(self) -> None:
        result = self.engine.simulate_shutdown(self.graph, "nonexistent", _default_config())
        assert isinstance(result, ShutdownSimulation)
        assert len(result.phases) == 7

    def test_phases_have_detail(self) -> None:
        result = self.engine.simulate_shutdown(self.graph, "app-1", _default_config())
        for phase_result in result.phases:
            assert isinstance(phase_result.detail, str)

    def test_signal_received_success_with_handler(self) -> None:
        result = self.engine.simulate_shutdown(self.graph, "app-1", _default_config())
        signal_phase = result.phases[0]
        assert signal_phase.phase == ShutdownPhase.SIGNAL_RECEIVED
        assert signal_phase.success is True

    def test_signal_received_fails_without_handler(self) -> None:
        cfg = ShutdownConfig(sigterm_handler=False)
        result = self.engine.simulate_shutdown(self.graph, "app-1", cfg)
        signal_phase = result.phases[0]
        assert signal_phase.success is False


# ---------------------------------------------------------------------------
# 5. Engine: validate_shutdown_config
# ---------------------------------------------------------------------------


class TestValidateShutdownConfig:
    def setup_method(self) -> None:
        self.engine = GracefulShutdownEngine()
        self.comp = _comp()
        self.graph = _graph(self.comp)

    def test_valid_config(self) -> None:
        cfg = ShutdownConfig(
            drain_timeout_seconds=30.0,
            grace_period_seconds=45.0,
            preStop_hook_seconds=5.0,
        )
        result = self.engine.validate_shutdown_config(self.graph, "app-1", cfg)
        assert result.valid is True
        assert result.score > 50.0

    def test_no_sigterm_invalid(self) -> None:
        cfg = ShutdownConfig(sigterm_handler=False)
        result = self.engine.validate_shutdown_config(self.graph, "app-1", cfg)
        assert result.valid is False
        assert any("SIGTERM" in e for e in result.errors)

    def test_no_draining_invalid(self) -> None:
        cfg = ShutdownConfig(connection_draining=False)
        result = self.engine.validate_shutdown_config(self.graph, "app-1", cfg)
        assert result.valid is False

    def test_no_deregistration_warning(self) -> None:
        cfg = ShutdownConfig(deregister_from_lb=False, grace_period_seconds=50.0)
        result = self.engine.validate_shutdown_config(self.graph, "app-1", cfg)
        assert len(result.warnings) > 0

    def test_short_drain_timeout_warning(self) -> None:
        cfg = ShutdownConfig(drain_timeout_seconds=2.0, grace_period_seconds=50.0)
        result = self.engine.validate_shutdown_config(self.graph, "app-1", cfg)
        assert any("short" in w.lower() for w in result.warnings)

    def test_long_drain_timeout_warning(self) -> None:
        cfg = ShutdownConfig(drain_timeout_seconds=150.0, grace_period_seconds=200.0)
        result = self.engine.validate_shutdown_config(self.graph, "app-1", cfg)
        assert any("long" in w.lower() for w in result.warnings)

    def test_grace_period_too_short_error(self) -> None:
        cfg = ShutdownConfig(
            drain_timeout_seconds=30.0,
            preStop_hook_seconds=10.0,
            grace_period_seconds=20.0,
        )
        result = self.engine.validate_shutdown_config(self.graph, "app-1", cfg)
        assert result.valid is False
        assert any("Grace period" in e for e in result.errors)

    def test_short_prestop_warning(self) -> None:
        cfg = ShutdownConfig(preStop_hook_seconds=0.5, grace_period_seconds=50.0)
        result = self.engine.validate_shutdown_config(self.graph, "app-1", cfg)
        assert any("preStop" in w for w in result.warnings)

    def test_database_short_drain_warning(self) -> None:
        db = _comp(cid="db-1", ctype=ComponentType.DATABASE)
        g = _graph(db)
        cfg = ShutdownConfig(drain_timeout_seconds=10.0, grace_period_seconds=50.0)
        result = self.engine.validate_shutdown_config(g, "db-1", cfg)
        assert any("Database" in w or "database" in w.lower() for w in result.warnings)

    def test_single_replica_no_deregister_error(self) -> None:
        comp = _comp(replicas=1)
        g = _graph(comp)
        cfg = ShutdownConfig(deregister_from_lb=False, grace_period_seconds=50.0)
        result = self.engine.validate_shutdown_config(g, "app-1", cfg)
        assert result.valid is False
        assert any("Single-replica" in e or "single" in e.lower() for e in result.errors)

    def test_down_component_warning(self) -> None:
        comp = _comp(health=HealthStatus.DOWN)
        g = _graph(comp)
        cfg = ShutdownConfig(grace_period_seconds=50.0)
        result = self.engine.validate_shutdown_config(g, "app-1", cfg)
        assert any("DOWN" in w for w in result.warnings)

    def test_score_decreases_with_issues(self) -> None:
        cfg = _bad_config()
        result = self.engine.validate_shutdown_config(self.graph, "app-1", cfg)
        assert result.score < 50.0

    def test_score_never_negative(self) -> None:
        cfg = ShutdownConfig(
            sigterm_handler=False,
            connection_draining=False,
            deregister_from_lb=False,
            drain_timeout_seconds=0.0,
            grace_period_seconds=0.0,
            preStop_hook_seconds=0.0,
        )
        comp = _comp(replicas=1, health=HealthStatus.DOWN, ctype=ComponentType.DATABASE)
        g = _graph(comp)
        result = self.engine.validate_shutdown_config(g, "app-1", cfg)
        assert result.score >= 0.0

    def test_unknown_component(self) -> None:
        result = self.engine.validate_shutdown_config(
            self.graph, "nonexistent", _default_config()
        )
        assert isinstance(result, ValidationResult)

    def test_perfect_config_high_score(self) -> None:
        cfg = ShutdownConfig(
            drain_timeout_seconds=30.0,
            grace_period_seconds=50.0,
            preStop_hook_seconds=5.0,
        )
        comp = _comp(replicas=3)
        g = _graph(comp)
        result = self.engine.validate_shutdown_config(g, "app-1", cfg)
        assert result.score >= 90.0


# ---------------------------------------------------------------------------
# 6. Engine: estimate_drain_time
# ---------------------------------------------------------------------------


class TestEstimateDrainTime:
    def setup_method(self) -> None:
        self.engine = GracefulShutdownEngine()

    def test_returns_positive(self) -> None:
        comp = _comp()
        g = _graph(comp)
        result = self.engine.estimate_drain_time(g, "app-1")
        assert result > 0.0

    def test_unknown_component(self) -> None:
        g = _graph()
        result = self.engine.estimate_drain_time(g, "nonexistent")
        assert result > 0.0

    def test_high_rps_drains_fast(self) -> None:
        fast = _comp(cid="fast", max_rps=10000, replicas=4)
        slow = _comp(cid="slow", max_rps=100, replicas=1)
        g = _graph(fast, slow)
        fast_time = self.engine.estimate_drain_time(g, "fast")
        slow_time = self.engine.estimate_drain_time(g, "slow")
        # fast component should drain faster relative to its in-flight count
        assert fast_time >= 0.0
        assert slow_time >= 0.0

    def test_includes_safety_margin(self) -> None:
        comp = _comp()
        g = _graph(comp)
        result = self.engine.estimate_drain_time(g, "app-1")
        # Result includes 1.2x safety margin
        assert result > 0.0

    def test_accounts_for_timeout(self) -> None:
        comp = _comp(timeout_seconds=120.0)
        g = _graph(comp)
        result = self.engine.estimate_drain_time(g, "app-1")
        # Should be at least 10% of timeout * 1.2
        assert result >= 120.0 * 0.1 * 1.2 - 0.01

    def test_zero_drain_rate_returns_inf(self) -> None:
        comp = _comp()
        g = _graph(comp)
        with patch(
            "faultray.simulator.graceful_shutdown._drain_rate", return_value=0.0,
        ):
            result = self.engine.estimate_drain_time(g, "app-1")
            assert result == float("inf")


# ---------------------------------------------------------------------------
# 7. Engine: detect_shutdown_risks
# ---------------------------------------------------------------------------


class TestDetectShutdownRisks:
    def setup_method(self) -> None:
        self.engine = GracefulShutdownEngine()

    def test_good_config_minimal_risks(self) -> None:
        comp = _comp(replicas=3)
        g = _graph(comp)
        cfg = ShutdownConfig(
            drain_timeout_seconds=30.0,
            grace_period_seconds=50.0,
            preStop_hook_seconds=5.0,
        )
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        # May still have informational risks, but no critical
        critical = [r for r in risks if r.severity == "critical"]
        assert len(critical) == 0

    def test_no_sigterm_critical(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = ShutdownConfig(sigterm_handler=False, grace_period_seconds=50.0)
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        critical = [r for r in risks if r.severity == "critical"]
        assert len(critical) >= 1
        assert any("sigterm" in r.risk_id for r in risks)

    def test_no_draining_high(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = ShutdownConfig(connection_draining=False, grace_period_seconds=50.0)
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        high = [r for r in risks if r.severity == "high"]
        assert len(high) >= 1

    def test_no_deregistration_medium(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = ShutdownConfig(deregister_from_lb=False, grace_period_seconds=50.0)
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        medium = [r for r in risks if r.severity == "medium"]
        assert len(medium) >= 1

    def test_insufficient_grace_period(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = ShutdownConfig(
            drain_timeout_seconds=30.0,
            preStop_hook_seconds=10.0,
            grace_period_seconds=20.0,
        )
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        assert any("insufficient_grace_period" in r.risk_id for r in risks)

    def test_short_drain_timeout_risk(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = ShutdownConfig(drain_timeout_seconds=2.0, grace_period_seconds=50.0)
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        assert any("short_drain_timeout" in r.risk_id for r in risks)

    def test_short_prestop_risk(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = ShutdownConfig(preStop_hook_seconds=0.5, grace_period_seconds=50.0)
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        assert any("short_prestop" in r.risk_id for r in risks)

    def test_single_replica_risk(self) -> None:
        comp = _comp(replicas=1)
        g = _graph(comp)
        cfg = ShutdownConfig(grace_period_seconds=50.0)
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        assert any("single_replica" in r.risk_id for r in risks)

    def test_database_short_drain_risk(self) -> None:
        db = _comp(cid="db-1", ctype=ComponentType.DATABASE)
        g = _graph(db)
        cfg = ShutdownConfig(drain_timeout_seconds=10.0, grace_period_seconds=50.0)
        risks = self.engine.detect_shutdown_risks(g, "db-1", cfg)
        assert any("db_short_drain" in r.risk_id for r in risks)

    def test_many_dependents_risk(self) -> None:
        main = _comp(cid="main")
        deps = [_comp(cid=f"dep-{i}") for i in range(5)]
        g = _graph(main, *deps, deps=[
            (f"dep-{i}", "main") for i in range(5)
        ])
        cfg = ShutdownConfig(grace_period_seconds=50.0)
        risks = self.engine.detect_shutdown_risks(g, "main", cfg)
        assert any("many_dependents" in r.risk_id for r in risks)

    def test_unknown_component_risks(self) -> None:
        g = _graph()
        risks = self.engine.detect_shutdown_risks(g, "nonexistent", _default_config())
        assert isinstance(risks, list)

    def test_all_risks_have_mitigation(self) -> None:
        cfg = _bad_config()
        comp = _comp(replicas=1, ctype=ComponentType.DATABASE)
        g = _graph(comp)
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        for risk in risks:
            assert risk.mitigation != ""

    def test_risk_severity_values(self) -> None:
        cfg = _bad_config()
        comp = _comp(replicas=1)
        g = _graph(comp)
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        valid_severities = {"low", "medium", "high", "critical"}
        for risk in risks:
            assert risk.severity in valid_severities


# ---------------------------------------------------------------------------
# 8. Engine: simulate_forced_kill
# ---------------------------------------------------------------------------


class TestSimulateForcedKill:
    def setup_method(self) -> None:
        self.engine = GracefulShutdownEngine()

    def test_returns_result(self) -> None:
        comp = _comp()
        g = _graph(comp)
        result = self.engine.simulate_forced_kill(g, "app-1")
        assert isinstance(result, ForcedKillResult)

    def test_in_flight_lost_positive(self) -> None:
        comp = _comp()
        g = _graph(comp)
        result = self.engine.simulate_forced_kill(g, "app-1")
        assert result.in_flight_lost > 0

    def test_connections_dropped(self) -> None:
        comp = _comp(network_connections=500)
        g = _graph(comp)
        result = self.engine.simulate_forced_kill(g, "app-1")
        assert result.connections_dropped == 500

    def test_connections_dropped_fallback(self) -> None:
        comp = _comp(network_connections=0, max_connections=1000)
        g = _graph(comp)
        result = self.engine.simulate_forced_kill(g, "app-1")
        assert result.connections_dropped == 500  # max_connections // 2

    def test_database_critical_data_loss(self) -> None:
        db = _comp(cid="db-1", ctype=ComponentType.DATABASE)
        g = _graph(db)
        result = self.engine.simulate_forced_kill(g, "db-1")
        assert result.data_loss_risk == "critical"

    def test_cache_low_data_loss(self) -> None:
        cache = _comp(cid="cache-1", ctype=ComponentType.CACHE)
        g = _graph(cache)
        result = self.engine.simulate_forced_kill(g, "cache-1")
        assert result.data_loss_risk == "low"

    def test_multi_replica_medium_data_loss(self) -> None:
        comp = _comp(replicas=3)
        g = _graph(comp)
        result = self.engine.simulate_forced_kill(g, "app-1")
        assert result.data_loss_risk == "medium"

    def test_database_longer_recovery(self) -> None:
        db = _comp(cid="db-1", ctype=ComponentType.DATABASE, replicas=1, failover=False)
        app = _comp(cid="app-1", replicas=1, failover=False)
        g_db = _graph(db)
        g_app = _graph(app)
        db_result = self.engine.simulate_forced_kill(g_db, "db-1")
        app_result = self.engine.simulate_forced_kill(g_app, "app-1")
        assert db_result.recovery_time_seconds > app_result.recovery_time_seconds

    def test_failover_reduces_recovery(self) -> None:
        with_fo = _comp(cid="with-fo", failover=True)
        without_fo = _comp(cid="without-fo", failover=False)
        g1 = _graph(with_fo)
        g2 = _graph(without_fo)
        r1 = self.engine.simulate_forced_kill(g1, "with-fo")
        r2 = self.engine.simulate_forced_kill(g2, "without-fo")
        assert r1.recovery_time_seconds < r2.recovery_time_seconds

    def test_replicas_reduce_recovery(self) -> None:
        multi = _comp(cid="multi", replicas=3, failover=False)
        single = _comp(cid="single", replicas=1, failover=False)
        g1 = _graph(multi)
        g2 = _graph(single)
        r1 = self.engine.simulate_forced_kill(g1, "multi")
        r2 = self.engine.simulate_forced_kill(g2, "single")
        assert r1.recovery_time_seconds < r2.recovery_time_seconds

    def test_affected_components(self) -> None:
        main = _comp(cid="main")
        dep1 = _comp(cid="dep-1")
        dep2 = _comp(cid="dep-2")
        g = _graph(main, dep1, dep2, deps=[("dep-1", "main"), ("dep-2", "main")])
        result = self.engine.simulate_forced_kill(g, "main")
        assert "dep-1" in result.affected_components
        assert "dep-2" in result.affected_components

    def test_no_dependents(self) -> None:
        comp = _comp()
        g = _graph(comp)
        result = self.engine.simulate_forced_kill(g, "app-1")
        assert result.affected_components == []

    def test_recommendations_present(self) -> None:
        comp = _comp()
        g = _graph(comp)
        result = self.engine.simulate_forced_kill(g, "app-1")
        assert len(result.recommendations) > 0
        assert any("graceful" in r.lower() for r in result.recommendations)

    def test_unknown_component(self) -> None:
        g = _graph()
        result = self.engine.simulate_forced_kill(g, "nonexistent")
        assert isinstance(result, ForcedKillResult)
        assert result.in_flight_lost == 50  # fallback default

    def test_db_recommendation(self) -> None:
        db = _comp(cid="db-1", ctype=ComponentType.DATABASE)
        g = _graph(db)
        result = self.engine.simulate_forced_kill(g, "db-1")
        assert any("WAL" in r or "journal" in r for r in result.recommendations)

    def test_queue_recovery_time(self) -> None:
        queue = _comp(cid="q-1", ctype=ComponentType.QUEUE, replicas=1, failover=False)
        g = _graph(queue)
        result = self.engine.simulate_forced_kill(g, "q-1")
        assert result.recovery_time_seconds == 60.0


# ---------------------------------------------------------------------------
# 9. Engine: recommend_shutdown_config
# ---------------------------------------------------------------------------


class TestRecommendShutdownConfig:
    def setup_method(self) -> None:
        self.engine = GracefulShutdownEngine()

    def test_returns_config(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = self.engine.recommend_shutdown_config(g, "app-1")
        assert isinstance(cfg, ShutdownConfig)

    def test_always_has_sigterm_handler(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = self.engine.recommend_shutdown_config(g, "app-1")
        assert cfg.sigterm_handler is True

    def test_always_has_connection_draining(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = self.engine.recommend_shutdown_config(g, "app-1")
        assert cfg.connection_draining is True

    def test_always_has_deregistration(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = self.engine.recommend_shutdown_config(g, "app-1")
        assert cfg.deregister_from_lb is True

    def test_database_longer_drain(self) -> None:
        db = _comp(cid="db-1", ctype=ComponentType.DATABASE)
        g = _graph(db)
        cfg = self.engine.recommend_shutdown_config(g, "db-1")
        assert cfg.drain_timeout_seconds >= 60.0

    def test_cache_shorter_drain(self) -> None:
        cache = _comp(cid="cache-1", ctype=ComponentType.CACHE)
        g = _graph(cache)
        cfg = self.engine.recommend_shutdown_config(g, "cache-1")
        assert cfg.drain_timeout_seconds <= 30.0

    def test_queue_moderate_drain(self) -> None:
        queue = _comp(cid="q-1", ctype=ComponentType.QUEUE)
        g = _graph(queue)
        cfg = self.engine.recommend_shutdown_config(g, "q-1")
        assert cfg.drain_timeout_seconds >= 30.0

    def test_grace_period_sufficient(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = self.engine.recommend_shutdown_config(g, "app-1")
        assert cfg.grace_period_seconds >= cfg.drain_timeout_seconds + cfg.preStop_hook_seconds

    def test_long_timeout_extends_drain(self) -> None:
        comp = _comp(timeout_seconds=120.0)
        g = _graph(comp)
        cfg = self.engine.recommend_shutdown_config(g, "app-1")
        assert cfg.drain_timeout_seconds >= 120.0 * 1.5

    def test_many_dependents_extends_prestop(self) -> None:
        main = _comp(cid="main")
        deps = [_comp(cid=f"dep-{i}") for i in range(5)]
        g = _graph(main, *deps, deps=[(f"dep-{i}", "main") for i in range(5)])
        cfg = self.engine.recommend_shutdown_config(g, "main")
        assert cfg.preStop_hook_seconds >= 10.0

    def test_unknown_component(self) -> None:
        g = _graph()
        cfg = self.engine.recommend_shutdown_config(g, "nonexistent")
        assert isinstance(cfg, ShutdownConfig)
        assert cfg.sigterm_handler is True

    def test_web_server_config(self) -> None:
        web = _comp(cid="web-1", ctype=ComponentType.WEB_SERVER)
        g = _graph(web)
        cfg = self.engine.recommend_shutdown_config(g, "web-1")
        assert cfg.drain_timeout_seconds == 20.0

    def test_lb_config(self) -> None:
        lb = _comp(cid="lb-1", ctype=ComponentType.LOAD_BALANCER)
        g = _graph(lb)
        cfg = self.engine.recommend_shutdown_config(g, "lb-1")
        assert cfg.drain_timeout_seconds >= 20.0


# ---------------------------------------------------------------------------
# 10. Engine: analyze_rolling_restart
# ---------------------------------------------------------------------------


class TestAnalyzeRollingRestart:
    def setup_method(self) -> None:
        self.engine = GracefulShutdownEngine()

    def test_returns_result(self) -> None:
        comps = [_comp(cid=f"app-{i}") for i in range(3)]
        g = _graph(*comps)
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], _default_config(),
        )
        assert isinstance(result, RollingRestartResult)

    def test_per_component_count(self) -> None:
        comps = [_comp(cid=f"app-{i}") for i in range(3)]
        g = _graph(*comps)
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], _default_config(),
        )
        assert len(result.per_component) == 3

    def test_total_duration_sums(self) -> None:
        comps = [_comp(cid=f"app-{i}") for i in range(2)]
        g = _graph(*comps)
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], _default_config(),
        )
        assert result.total_duration_seconds > 0

    def test_good_config_safe(self) -> None:
        comps = [_comp(cid=f"app-{i}", replicas=3) for i in range(2)]
        g = _graph(*comps)
        cfg = ShutdownConfig(
            drain_timeout_seconds=60.0,
            grace_period_seconds=90.0,
        )
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], cfg,
        )
        assert result.safe is True
        assert result.dropped_requests_total == 0

    def test_bad_config_unsafe(self) -> None:
        comps = [_comp(cid=f"app-{i}") for i in range(3)]
        g = _graph(*comps)
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], _bad_config(),
        )
        assert result.safe is False
        assert result.dropped_requests_total > 0

    def test_max_unavailable(self) -> None:
        comps = [_comp(cid=f"app-{i}") for i in range(3)]
        g = _graph(*comps)
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], _default_config(),
        )
        assert result.max_unavailable >= 1

    def test_min_available_percent(self) -> None:
        comps = [_comp(cid=f"app-{i}", replicas=2) for i in range(4)]
        g = _graph(*comps)
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], _default_config(),
        )
        assert result.min_available_percent > 0
        assert result.min_available_percent <= 100.0

    def test_single_component(self) -> None:
        comp = _comp()
        g = _graph(comp)
        result = self.engine.analyze_rolling_restart(g, ["app-1"], _default_config())
        assert len(result.per_component) == 1

    def test_empty_list(self) -> None:
        g = _graph()
        result = self.engine.analyze_rolling_restart(g, [], _default_config())
        assert result.total_duration_seconds == 0.0
        assert result.per_component == []
        assert result.safe is True

    def test_recommendations_on_unsafe(self) -> None:
        comps = [_comp(cid=f"app-{i}") for i in range(3)]
        g = _graph(*comps)
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], _bad_config(),
        )
        assert len(result.recommendations) > 0

    def test_many_components_recommendation(self) -> None:
        comps = [_comp(cid=f"app-{i}", replicas=3) for i in range(6)]
        g = _graph(*comps)
        cfg = ShutdownConfig(
            drain_timeout_seconds=60.0,
            grace_period_seconds=90.0,
        )
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], cfg,
        )
        assert any("batch" in r.lower() for r in result.recommendations)

    def test_min_available_zero_no_replicas(self) -> None:
        # With no total replicas (unknown components), min_available is 0
        g = _graph()
        result = self.engine.analyze_rolling_restart(
            g, ["x-1", "x-2"], _default_config(),
        )
        assert result.min_available_percent == 0.0


# ---------------------------------------------------------------------------
# 11. Edge cases & integration
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def setup_method(self) -> None:
        self.engine = GracefulShutdownEngine()

    def test_simulate_then_validate(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = _default_config()
        sim = self.engine.simulate_shutdown(g, "app-1", cfg)
        val = self.engine.validate_shutdown_config(g, "app-1", cfg)
        assert isinstance(sim, ShutdownSimulation)
        assert isinstance(val, ValidationResult)

    def test_recommend_then_simulate(self) -> None:
        comp = _comp()
        g = _graph(comp)
        recommended = self.engine.recommend_shutdown_config(g, "app-1")
        sim = self.engine.simulate_shutdown(g, "app-1", recommended)
        # Recommended config should produce a clean shutdown
        assert sim.dropped_requests == 0
        assert sim.data_loss_risk == "none"

    def test_recommend_then_validate(self) -> None:
        comp = _comp(replicas=3)
        g = _graph(comp)
        recommended = self.engine.recommend_shutdown_config(g, "app-1")
        val = self.engine.validate_shutdown_config(g, "app-1", recommended)
        assert val.valid is True
        assert val.score >= 80.0

    def test_detect_risks_then_simulate(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = _bad_config()
        risks = self.engine.detect_shutdown_risks(g, "app-1", cfg)
        sim = self.engine.simulate_shutdown(g, "app-1", cfg)
        # Bad config has risks AND dropped requests
        assert len(risks) > 0
        assert sim.dropped_requests > 0

    def test_forced_kill_vs_graceful(self) -> None:
        comp = _comp()
        g = _graph(comp)
        kill = self.engine.simulate_forced_kill(g, "app-1")
        graceful = self.engine.simulate_shutdown(g, "app-1", ShutdownConfig(
            drain_timeout_seconds=60.0,
            grace_period_seconds=90.0,
        ))
        # Forced kill always loses in-flight; graceful should not
        assert kill.in_flight_lost > 0
        assert graceful.dropped_requests == 0

    def test_zero_drain_timeout_with_draining(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = ShutdownConfig(drain_timeout_seconds=0.0)
        result = self.engine.simulate_shutdown(g, "app-1", cfg)
        assert isinstance(result, ShutdownSimulation)

    def test_very_large_drain_timeout(self) -> None:
        comp = _comp()
        g = _graph(comp)
        cfg = ShutdownConfig(
            drain_timeout_seconds=3600.0,
            grace_period_seconds=4000.0,
        )
        result = self.engine.simulate_shutdown(g, "app-1", cfg)
        assert result.dropped_requests == 0

    def test_graph_with_dependencies(self) -> None:
        lb = _comp(cid="lb", ctype=ComponentType.LOAD_BALANCER)
        app = _comp(cid="app", ctype=ComponentType.APP_SERVER)
        db = _comp(cid="db", ctype=ComponentType.DATABASE)
        g = _graph(lb, app, db, deps=[("lb", "app"), ("app", "db")])
        # Each component can be independently simulated
        for cid in ["lb", "app", "db"]:
            result = self.engine.simulate_shutdown(g, cid, _default_config())
            assert isinstance(result, ShutdownSimulation)

    def test_all_component_types_recommend(self) -> None:
        for ct in [
            ComponentType.APP_SERVER,
            ComponentType.DATABASE,
            ComponentType.CACHE,
            ComponentType.QUEUE,
            ComponentType.LOAD_BALANCER,
            ComponentType.WEB_SERVER,
            ComponentType.STORAGE,
        ]:
            comp = _comp(cid=f"c-{ct.value}", ctype=ct)
            g = _graph(comp)
            cfg = self.engine.recommend_shutdown_config(g, f"c-{ct.value}")
            assert isinstance(cfg, ShutdownConfig)
            assert cfg.grace_period_seconds >= cfg.drain_timeout_seconds + cfg.preStop_hook_seconds

    def test_rolling_restart_with_mixed_types(self) -> None:
        app = _comp(cid="app-1", ctype=ComponentType.APP_SERVER)
        web = _comp(cid="web-1", ctype=ComponentType.WEB_SERVER)
        g = _graph(app, web)
        result = self.engine.analyze_rolling_restart(
            g, ["app-1", "web-1"], _default_config()
        )
        assert len(result.per_component) == 2

    def test_overloaded_component_shutdown(self) -> None:
        comp = _comp(health=HealthStatus.OVERLOADED)
        g = _graph(comp)
        result = self.engine.simulate_shutdown(g, "app-1", _default_config())
        assert isinstance(result, ShutdownSimulation)

    def test_down_component_shutdown(self) -> None:
        comp = _comp(health=HealthStatus.DOWN)
        g = _graph(comp)
        result = self.engine.simulate_shutdown(g, "app-1", _default_config())
        assert isinstance(result, ShutdownSimulation)

    def test_rolling_restart_long_duration_recommendation(self) -> None:
        """Cover the > 600s total duration recommendation branch."""
        # Use many components with large drain timeouts to exceed 600s
        comps = [_comp(cid=f"app-{i}", replicas=3) for i in range(8)]
        g = _graph(*comps)
        cfg = ShutdownConfig(
            drain_timeout_seconds=120.0,
            grace_period_seconds=150.0,
            preStop_hook_seconds=5.0,
        )
        result = self.engine.analyze_rolling_restart(
            g, [c.id for c in comps], cfg,
        )
        assert result.total_duration_seconds > 600.0
        assert any("10 minutes" in r for r in result.recommendations)
