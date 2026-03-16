"""Tests for the Autoscaling Policy Evaluator module."""

from __future__ import annotations

import math

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.autoscaling_policy_evaluator import (
    AutoscalingPolicyEvaluator,
    BlastRadiusResult,
    ConflictType,
    CostAnalysis,
    CostStrategy,
    EvaluationResult,
    MetricDataPoint,
    MetricType,
    OscillationWindow,
    PolicyConflict,
    PolicySeverity,
    RegionalScalingState,
    ScalingDirection,
    ScalingEvent,
    ScalingLagAnalysis,
    ScalingPolicy,
    ScalingStrategy,
    WarmPoolState,
)


# ---------------------------------------------------------------------------
# Helpers (as mandated by the project conventions)
# ---------------------------------------------------------------------------

def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _make_policy(
    policy_id: str = "pol1",
    component_id: str = "c1",
    **kwargs,
) -> ScalingPolicy:
    """Convenience factory for ScalingPolicy with sensible defaults."""
    defaults = dict(
        policy_id=policy_id,
        component_id=component_id,
        strategy=ScalingStrategy.REACTIVE,
        metric_type=MetricType.CPU,
        scale_up_threshold=70.0,
        scale_down_threshold=30.0,
        min_instances=1,
        max_instances=10,
        cooldown_up_seconds=60,
        cooldown_down_seconds=300,
    )
    defaults.update(kwargs)
    return ScalingPolicy(**defaults)


def _make_series(
    values: list[float],
    start: float = 0.0,
    interval: float = 10.0,
    metric_type: MetricType = MetricType.CPU,
) -> list[MetricDataPoint]:
    """Build a metric time series from a list of values."""
    return [
        MetricDataPoint(timestamp=start + i * interval, value=v, metric_type=metric_type)
        for i, v in enumerate(values)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPolicyManagement:
    """Policy registration and retrieval."""

    def test_add_and_get_policies(self):
        g = _graph(_comp("a1"))
        ev = AutoscalingPolicyEvaluator(g)
        p1 = _make_policy("p1", "a1")
        p2 = _make_policy("p2", "a1")
        ev.add_policy(p1)
        ev.add_policy(p2)
        assert len(ev.get_policies()) == 2
        assert len(ev.get_policies("a1")) == 2
        assert len(ev.get_policies("nonexistent")) == 0

    def test_add_policies_bulk(self):
        g = _graph(_comp("a1"), _comp("b1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policies([
            _make_policy("p1", "a1"),
            _make_policy("p2", "b1"),
        ])
        assert len(ev.get_policies()) == 2
        assert len(ev.get_policies("a1")) == 1
        assert len(ev.get_policies("b1")) == 1

    def test_clear_policies(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy())
        ev.clear_policies()
        assert ev.get_policies() == []


class TestMetricHistory:
    """Metric history recording and retrieval."""

    def test_add_and_get_metric_data(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        pts = _make_series([10, 20, 30])
        ev.add_metric_data("c1", pts)
        assert len(ev.get_metric_history("c1")) == 3

    def test_get_empty_metric_history(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        assert ev.get_metric_history("c1") == []


class TestSimulateScaling:
    """Scaling simulation logic."""

    def test_no_policies_returns_empty(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        series = _make_series([80, 90, 95])
        assert ev.simulate_scaling("c1", series) == []

    def test_no_metric_series_returns_empty(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy())
        assert ev.simulate_scaling("c1", []) == []

    def test_scale_up_on_high_cpu(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", cooldown_up_seconds=0, cooldown_down_seconds=9999))
        series = _make_series([50, 55, 75, 85])
        events = ev.simulate_scaling("c1", series, initial_instances=2)
        up_events = [e for e in events if e.direction == ScalingDirection.UP and not e.was_blocked_by_cooldown]
        assert len(up_events) >= 1
        assert up_events[0].from_count == 2
        assert up_events[0].to_count > 2

    def test_scale_down_on_low_cpu(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", cooldown_down_seconds=0, min_instances=1))
        series = _make_series([20, 15, 10])
        events = ev.simulate_scaling("c1", series, initial_instances=5)
        down_events = [e for e in events if e.direction == ScalingDirection.DOWN and not e.was_blocked_by_cooldown]
        assert len(down_events) >= 1
        assert down_events[0].to_count < down_events[0].from_count

    def test_cooldown_blocks_rapid_scaling(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", cooldown_up_seconds=100))
        # All high values within 100s, only first should proceed
        series = _make_series([80, 85, 90], interval=10.0)
        events = ev.simulate_scaling("c1", series, initial_instances=1)
        # At least one should be blocked
        non_blocked = [e for e in events if not e.was_blocked_by_cooldown and e.direction == ScalingDirection.UP]
        blocked = [e for e in events if e.was_blocked_by_cooldown and e.direction == ScalingDirection.UP]
        assert len(non_blocked) >= 1
        assert len(blocked) >= 1

    def test_min_max_constraints(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", min_instances=2, max_instances=3, cooldown_up_seconds=0))
        series = _make_series([95, 95, 95, 95, 95])
        events = ev.simulate_scaling("c1", series, initial_instances=2)
        # Should never exceed max_instances=3
        for e in events:
            if not e.was_blocked_by_cooldown:
                assert e.to_count <= 3

    def test_duration_filter(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", cooldown_up_seconds=0))
        series = _make_series([80, 85, 90, 95, 99], interval=100.0)
        events = ev.simulate_scaling("c1", series, initial_instances=1, duration_seconds=250.0)
        # Only points within 250s of start should be processed (0, 100, 200)
        timestamps = [e.timestamp for e in events]
        for ts in timestamps:
            assert ts <= 250.0

    def test_warm_pool_reduces_lag(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", cooldown_up_seconds=0, warm_pool_size=5))
        series = _make_series([85])
        events = ev.simulate_scaling("c1", series, initial_instances=1)
        up_events = [e for e in events if e.direction == ScalingDirection.UP and not e.was_blocked_by_cooldown]
        assert len(up_events) >= 1
        assert up_events[0].warm_pool_used > 0
        # Lag should be lower with warm pool
        assert up_events[0].lag_seconds <= 10.0  # warm start is ~5s per instance

    def test_step_scaling_strategy(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        steps = [
            {"threshold": 70, "adjustment": 1, "direction": "up"},
            {"threshold": 90, "adjustment": 3, "direction": "up"},
        ]
        ev.add_policy(_make_policy(
            "p1", "c1",
            strategy=ScalingStrategy.STEP,
            step_adjustments=steps,
            cooldown_up_seconds=0,
        ))
        series = _make_series([95])
        events = ev.simulate_scaling("c1", series, initial_instances=2)
        up_events = [e for e in events if e.direction == ScalingDirection.UP and not e.was_blocked_by_cooldown]
        assert len(up_events) == 1
        # Step adjustment of 3 at 90+
        assert up_events[0].to_count == 5  # 2 + 3

    def test_metric_type_mismatch_ignored(self):
        """A CPU policy should not react to memory metric data."""
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", metric_type=MetricType.CPU))
        series = _make_series([90, 95], metric_type=MetricType.MEMORY)
        events = ev.simulate_scaling("c1", series, initial_instances=1)
        assert events == []

    def test_combined_metric_matches_any(self):
        """A COMBINED policy should react to any metric type."""
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", metric_type=MetricType.COMBINED, cooldown_up_seconds=0))
        series = _make_series([90], metric_type=MetricType.MEMORY)
        events = ev.simulate_scaling("c1", series, initial_instances=1)
        up = [e for e in events if e.direction == ScalingDirection.UP and not e.was_blocked_by_cooldown]
        assert len(up) >= 1


class TestOscillationDetection:
    """Oscillation / thrashing detection."""

    def test_no_events_no_oscillation(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        assert ev.detect_oscillations([]) == []

    def test_few_events_no_oscillation(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        events = [
            ScalingEvent(timestamp=0, component_id="c1", direction=ScalingDirection.UP,
                         from_count=1, to_count=2, trigger_metric=MetricType.CPU, trigger_value=80),
            ScalingEvent(timestamp=10, component_id="c1", direction=ScalingDirection.DOWN,
                         from_count=2, to_count=1, trigger_metric=MetricType.CPU, trigger_value=20),
        ]
        assert ev.detect_oscillations(events, min_direction_changes=3) == []

    def test_detects_oscillation(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        events = [
            ScalingEvent(timestamp=0, component_id="c1", direction=ScalingDirection.UP,
                         from_count=1, to_count=2, trigger_metric=MetricType.CPU, trigger_value=80),
            ScalingEvent(timestamp=30, component_id="c1", direction=ScalingDirection.DOWN,
                         from_count=2, to_count=1, trigger_metric=MetricType.CPU, trigger_value=20),
            ScalingEvent(timestamp=60, component_id="c1", direction=ScalingDirection.UP,
                         from_count=1, to_count=2, trigger_metric=MetricType.CPU, trigger_value=80),
            ScalingEvent(timestamp=90, component_id="c1", direction=ScalingDirection.DOWN,
                         from_count=2, to_count=1, trigger_metric=MetricType.CPU, trigger_value=20),
        ]
        oscillations = ev.detect_oscillations(events, window_seconds=200, min_direction_changes=3)
        assert len(oscillations) >= 1
        assert oscillations[0].direction_changes >= 3

    def test_blocked_events_excluded(self):
        """Blocked events (by cooldown) should not count as direction changes."""
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        events = [
            ScalingEvent(timestamp=0, component_id="c1", direction=ScalingDirection.UP,
                         from_count=1, to_count=2, trigger_metric=MetricType.CPU, trigger_value=80),
            ScalingEvent(timestamp=30, component_id="c1", direction=ScalingDirection.DOWN,
                         from_count=2, to_count=1, trigger_metric=MetricType.CPU, trigger_value=20,
                         was_blocked_by_cooldown=True),
            ScalingEvent(timestamp=60, component_id="c1", direction=ScalingDirection.UP,
                         from_count=1, to_count=2, trigger_metric=MetricType.CPU, trigger_value=80,
                         was_blocked_by_cooldown=True),
            ScalingEvent(timestamp=90, component_id="c1", direction=ScalingDirection.DOWN,
                         from_count=2, to_count=1, trigger_metric=MetricType.CPU, trigger_value=20,
                         was_blocked_by_cooldown=True),
        ]
        oscillations = ev.detect_oscillations(events, min_direction_changes=3)
        # Only 1 effective event, so no oscillation detected
        assert oscillations == []


class TestAsymmetryAnalysis:
    """Scale-up vs scale-down asymmetry."""

    def test_healthy_asymmetry(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        policy = _make_policy(
            "p1", "c1",
            scale_up_threshold=70.0,
            scale_down_threshold=30.0,
            cooldown_up_seconds=60,
            cooldown_down_seconds=300,
        )
        result = ev.analyse_asymmetry([policy])
        assert "c1" in result
        assert result["c1"]["is_healthy"] is True
        assert result["c1"]["threshold_gap"] == 40.0
        assert result["c1"]["cooldown_ratio"] == 5.0
        assert result["c1"]["recommendations"] == []

    def test_unhealthy_narrow_gap(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        policy = _make_policy(
            "p1", "c1",
            scale_up_threshold=55.0,
            scale_down_threshold=45.0,
            cooldown_up_seconds=60,
            cooldown_down_seconds=120,
        )
        result = ev.analyse_asymmetry([policy])
        assert result["c1"]["is_healthy"] is False
        assert len(result["c1"]["recommendations"]) >= 1

    def test_low_down_threshold_warning(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        policy = _make_policy(
            "p1", "c1",
            scale_up_threshold=70.0,
            scale_down_threshold=5.0,
            cooldown_up_seconds=30,
            cooldown_down_seconds=300,
        )
        result = ev.analyse_asymmetry([policy])
        recs = result["c1"]["recommendations"]
        assert any("very low" in r.lower() for r in recs)

    def test_zero_cooldown_up(self):
        """Zero cooldown_up_seconds should not cause division by zero."""
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        policy = _make_policy("p1", "c1", cooldown_up_seconds=0)
        result = ev.analyse_asymmetry([policy])
        assert result["c1"]["cooldown_ratio"] == 0.0


class TestConflictDetection:
    """Policy conflict detection."""

    def test_no_conflicts_single_policy(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1"))
        assert ev.detect_conflicts() == []

    def test_contradictory_thresholds(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policies([
            _make_policy("p1", "c1", scale_up_threshold=40.0, scale_down_threshold=20.0),
            _make_policy("p2", "c1", scale_up_threshold=80.0, scale_down_threshold=50.0),
        ])
        conflicts = ev.detect_conflicts()
        critical = [c for c in conflicts if c.conflict_type == ConflictType.CONTRADICTORY_THRESHOLDS]
        assert len(critical) >= 1
        assert critical[0].severity == PolicySeverity.CRITICAL

    def test_cooldown_conflict(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policies([
            _make_policy("p1", "c1", cooldown_up_seconds=10),
            _make_policy("p2", "c1", cooldown_up_seconds=600),
        ])
        conflicts = ev.detect_conflicts()
        cooldown = [c for c in conflicts if c.conflict_type == ConflictType.COOLDOWN_CONFLICT]
        assert len(cooldown) >= 1

    def test_direction_conflict_min_max(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policies([
            _make_policy("p1", "c1", min_instances=5, max_instances=10),
            _make_policy("p2", "c1", min_instances=1, max_instances=3),
        ])
        conflicts = ev.detect_conflicts()
        dir_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.DIRECTION_CONFLICT]
        assert len(dir_conflicts) >= 1
        assert dir_conflicts[0].severity == PolicySeverity.HIGH

    def test_no_conflict_different_components(self):
        g = _graph(_comp("a1"), _comp("b1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policies([
            _make_policy("p1", "a1", scale_up_threshold=40.0, scale_down_threshold=20.0),
            _make_policy("p2", "b1", scale_up_threshold=80.0, scale_down_threshold=50.0),
        ])
        conflicts = ev.detect_conflicts()
        # These are on different components, so the contradictory thresholds
        # check should not fire between them.
        cross = [
            c for c in conflicts
            if c.conflict_type == ConflictType.CONTRADICTORY_THRESHOLDS
        ]
        assert cross == []

    def test_metric_conflict_shadowing(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policies([
            _make_policy("p1", "c1", scale_up_threshold=50.0, scale_down_threshold=30.0, metric_type=MetricType.CPU),
            _make_policy("p2", "c1", scale_up_threshold=80.0, scale_down_threshold=20.0, metric_type=MetricType.CPU),
        ])
        conflicts = ev.detect_conflicts()
        metric = [c for c in conflicts if c.conflict_type == ConflictType.METRIC_CONFLICT]
        assert len(metric) >= 1


class TestCostAnalysis:
    """Cost optimisation analysis."""

    def test_basic_cost(self):
        g = _graph(Component(id="c1", name="c1", type=ComponentType.APP_SERVER, replicas=4))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", min_instances=2))
        result = ev.analyse_cost("c1", hourly_instance_cost=1.0)
        assert result.current_monthly_cost > 0
        assert result.optimized_monthly_cost < result.current_monthly_cost
        assert result.savings_percent > 0

    def test_cost_nonexistent_component(self):
        g = _graph()
        ev = AutoscalingPolicyEvaluator(g)
        result = ev.analyse_cost("missing")
        assert result.current_monthly_cost == 0.0
        assert result.savings_percent == 0.0
        assert "not found" in result.recommendation.lower()

    def test_cost_no_burst(self):
        """When avg_instances equals min, all reserved."""
        g = _graph(Component(id="c1", name="c1", type=ComponentType.APP_SERVER, replicas=2))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", min_instances=2))
        result = ev.analyse_cost("c1", hourly_instance_cost=0.50, avg_instances=2.0)
        assert result.spot_ratio == 0.0
        assert result.reserved_ratio == 1.0
        assert result.strategy == CostStrategy.RESERVED_CAPACITY


class TestScalingLagAnalysis:
    """Scaling lag analysis."""

    def test_empty_events(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        result = ev.analyse_scaling_lag([])
        assert result.avg_lag_seconds == 0.0
        assert result.meets_sla is True

    def test_lag_within_sla(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        events = [
            ScalingEvent(timestamp=0, component_id="c1", direction=ScalingDirection.UP,
                         from_count=1, to_count=2, trigger_metric=MetricType.CPU,
                         trigger_value=80, lag_seconds=30),
            ScalingEvent(timestamp=100, component_id="c1", direction=ScalingDirection.UP,
                         from_count=2, to_count=3, trigger_metric=MetricType.CPU,
                         trigger_value=85, lag_seconds=45),
        ]
        result = ev.analyse_scaling_lag(events, sla_target_seconds=120.0)
        assert result.meets_sla is True
        assert result.avg_lag_seconds > 0
        assert result.p95_lag_seconds <= 120.0

    def test_lag_exceeds_sla(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        events = [
            ScalingEvent(timestamp=0, component_id="c1", direction=ScalingDirection.UP,
                         from_count=1, to_count=2, trigger_metric=MetricType.CPU,
                         trigger_value=80, lag_seconds=200),
        ]
        result = ev.analyse_scaling_lag(events, sla_target_seconds=60.0)
        assert result.meets_sla is False
        assert result.p95_lag_seconds > 60.0

    def test_lag_breakdown_directions(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        events = [
            ScalingEvent(timestamp=0, component_id="c1", direction=ScalingDirection.UP,
                         from_count=1, to_count=2, trigger_metric=MetricType.CPU,
                         trigger_value=80, lag_seconds=40),
            ScalingEvent(timestamp=100, component_id="c1", direction=ScalingDirection.DOWN,
                         from_count=3, to_count=2, trigger_metric=MetricType.CPU,
                         trigger_value=20, lag_seconds=10),
        ]
        result = ev.analyse_scaling_lag(events)
        assert "scale_up_avg" in result.breakdown
        assert "scale_down_avg" in result.breakdown
        assert result.breakdown["scale_up_avg"] == 40.0
        assert result.breakdown["scale_down_avg"] == 10.0

    def test_lag_zero_lag_events(self):
        """Events with lag_seconds=0 should be skipped in calculation."""
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        events = [
            ScalingEvent(timestamp=0, component_id="c1", direction=ScalingDirection.UP,
                         from_count=1, to_count=2, trigger_metric=MetricType.CPU,
                         trigger_value=80, lag_seconds=0),
        ]
        result = ev.analyse_scaling_lag(events)
        assert result.avg_lag_seconds == 0.0
        assert result.meets_sla is True


class TestBlastRadius:
    """Blast radius analysis during scale-in."""

    def test_blast_radius_missing_component(self):
        g = _graph()
        ev = AutoscalingPolicyEvaluator(g)
        result = ev.analyse_blast_radius("missing")
        assert result.active_connections_affected == 0
        assert result.risk_level == PolicySeverity.INFO

    def test_blast_radius_critical_when_all_removed(self):
        g = _graph(Component(id="c1", name="c1", type=ComponentType.APP_SERVER, replicas=2))
        ev = AutoscalingPolicyEvaluator(g)
        result = ev.analyse_blast_radius("c1", instances_to_remove=2)
        assert result.risk_level == PolicySeverity.CRITICAL

    def test_blast_radius_high_single_remaining(self):
        g = _graph(Component(id="c1", name="c1", type=ComponentType.APP_SERVER, replicas=2))
        ev = AutoscalingPolicyEvaluator(g)
        result = ev.analyse_blast_radius("c1", instances_to_remove=1)
        assert result.risk_level == PolicySeverity.HIGH

    def test_blast_radius_low_many_remaining(self):
        g = _graph(Component(id="c1", name="c1", type=ComponentType.APP_SERVER, replicas=10))
        ev = AutoscalingPolicyEvaluator(g)
        result = ev.analyse_blast_radius("c1", instances_to_remove=1)
        assert result.risk_level == PolicySeverity.LOW

    def test_blast_radius_includes_dependents(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        ev = AutoscalingPolicyEvaluator(g)
        result = ev.analyse_blast_radius("c1", instances_to_remove=1)
        assert "c2" in result.dependent_components

    def test_blast_radius_drain_time_from_policy(self):
        g = _graph(Component(id="c1", name="c1", type=ComponentType.APP_SERVER, replicas=4))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", connection_drain_seconds=120))
        result = ev.analyse_blast_radius("c1", instances_to_remove=1)
        assert result.drain_time_seconds == 120.0


class TestWarmPool:
    """Warm pool evaluation."""

    def test_no_policies_empty_pool(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        state = ev.evaluate_warm_pool("c1")
        assert state.pool_size == 0
        assert state.available == 0

    def test_warm_pool_with_policy(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", warm_pool_size=10, warm_pool_reuse=True))
        state = ev.evaluate_warm_pool("c1")
        assert state.pool_size == 10
        assert state.available == 8  # 80% of 10
        assert state.initializing == 2
        assert state.reuse_enabled is True


class TestRegionalScaling:
    """Regional scaling coordination."""

    def test_empty_regions(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        assert ev.coordinate_regional_scaling("c1", []) == []

    def test_primary_gets_minimum_2(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        regions = [
            {"region": "us-east-1", "current_instances": 1, "target_instances": 1, "is_primary": True},
        ]
        states = ev.coordinate_regional_scaling("c1", regions)
        assert len(states) == 1
        assert states[0].target_instances >= 2
        assert states[0].is_primary is True

    def test_multi_region_proportional(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        regions = [
            {"region": "us-east-1", "current_instances": 6, "target_instances": 8, "is_primary": True, "latency_ms": 5},
            {"region": "eu-west-1", "current_instances": 4, "target_instances": 4, "is_primary": False, "latency_ms": 80},
        ]
        states = ev.coordinate_regional_scaling("c1", regions)
        assert len(states) == 2
        total_target = sum(s.target_instances for s in states)
        assert total_target >= 12  # total of original targets
        # Primary region should have more
        primary = [s for s in states if s.is_primary][0]
        secondary = [s for s in states if not s.is_primary][0]
        assert primary.target_instances >= secondary.target_instances


class TestMultiMetric:
    """Multi-dimensional scaling evaluation."""

    def test_scale_up_if_any_exceeds(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", metric_type=MetricType.CPU, scale_up_threshold=70))
        ev.add_policy(_make_policy("p2", "c1", metric_type=MetricType.MEMORY, scale_up_threshold=80))
        direction = ev.evaluate_multi_metric("c1", {
            MetricType.CPU: 75,  # above threshold
            MetricType.MEMORY: 50,  # below threshold
        })
        assert direction == ScalingDirection.UP

    def test_scale_down_if_all_below(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", metric_type=MetricType.CPU, scale_down_threshold=30))
        ev.add_policy(_make_policy("p2", "c1", metric_type=MetricType.MEMORY, scale_down_threshold=30))
        direction = ev.evaluate_multi_metric("c1", {
            MetricType.CPU: 10,
            MetricType.MEMORY: 15,
        })
        assert direction == ScalingDirection.DOWN

    def test_none_when_between_thresholds(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", metric_type=MetricType.CPU,
                                   scale_up_threshold=70, scale_down_threshold=30))
        direction = ev.evaluate_multi_metric("c1", {MetricType.CPU: 50})
        assert direction == ScalingDirection.NONE

    def test_no_policies_returns_none(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        direction = ev.evaluate_multi_metric("c1", {MetricType.CPU: 80})
        assert direction == ScalingDirection.NONE


class TestForecast:
    """Metric forecasting."""

    def test_forecast_too_few_points(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        result = ev.forecast_metric([MetricDataPoint(timestamp=0, value=50)])
        assert result == []

    def test_forecast_linear_trend(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        points = _make_series([10, 20, 30, 40, 50], interval=60.0)
        forecasts = ev.forecast_metric(points, horizon_seconds=180.0)
        assert len(forecasts) >= 1
        # Values should continue the upward trend
        assert forecasts[-1].value > 50

    def test_forecast_flat_trend(self):
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        points = _make_series([50, 50, 50, 50], interval=60.0)
        forecasts = ev.forecast_metric(points, horizon_seconds=120.0)
        for f in forecasts:
            assert abs(f.value - 50.0) < 1.0  # should stay flat

    def test_forecast_values_non_negative(self):
        """Forecasted values should be clamped to non-negative."""
        g = _graph(_comp())
        ev = AutoscalingPolicyEvaluator(g)
        # Steep downward trend
        points = _make_series([100, 80, 60, 40, 20], interval=60.0)
        forecasts = ev.forecast_metric(points, horizon_seconds=600.0)
        for f in forecasts:
            assert f.value >= 0.0


class TestFullEvaluation:
    """Full evaluate() method integration tests."""

    def test_evaluate_empty_graph(self):
        g = _graph()
        ev = AutoscalingPolicyEvaluator(g)
        assert ev.evaluate() == []

    def test_evaluate_single_component_no_policy(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        results = ev.evaluate("c1")
        assert len(results) == 1
        r = results[0]
        assert r.component_id == "c1"
        assert r.policies_evaluated == 0
        assert r.score == 50.0  # no policies = score 50

    def test_evaluate_with_policy_and_data(self):
        g = _graph(Component(id="c1", name="c1", type=ComponentType.APP_SERVER, replicas=2))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policy(_make_policy("p1", "c1", cooldown_up_seconds=0))
        ev.add_metric_data("c1", _make_series([20, 40, 75, 85, 90]))
        results = ev.evaluate("c1")
        assert len(results) == 1
        r = results[0]
        assert r.policies_evaluated == 1
        assert len(r.scaling_events) >= 1
        assert r.evaluated_at != ""

    def test_evaluate_all_components(self):
        g = _graph(_comp("a1"), _comp("b1"), _comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        results = ev.evaluate()
        assert len(results) == 3
        ids = {r.component_id for r in results}
        assert ids == {"a1", "b1", "c1"}

    def test_evaluate_score_degrades_with_conflicts(self):
        g = _graph(_comp("c1"))
        ev = AutoscalingPolicyEvaluator(g)
        ev.add_policies([
            _make_policy("p1", "c1", scale_up_threshold=40.0, scale_down_threshold=20.0),
            _make_policy("p2", "c1", scale_up_threshold=80.0, scale_down_threshold=50.0),
        ])
        results = ev.evaluate("c1")
        assert results[0].score < 100.0

    def test_evaluate_generates_recommendations(self):
        c1 = Component(id="c1", name="c1", type=ComponentType.APP_SERVER, replicas=2)
        c2 = Component(id="c2", name="c2", type=ComponentType.APP_SERVER, replicas=1)
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        ev = AutoscalingPolicyEvaluator(g)
        # Add conflicting policies
        ev.add_policies([
            _make_policy("p1", "c1", scale_up_threshold=30.0, scale_down_threshold=10.0),
            _make_policy("p2", "c1", scale_up_threshold=90.0, scale_down_threshold=50.0),
        ])
        results = ev.evaluate("c1")
        assert len(results[0].recommendations) > 0


class TestSeverityMapping:
    """Score to severity mapping."""

    def test_info_severity(self):
        assert AutoscalingPolicyEvaluator._derive_severity(95.0) == PolicySeverity.INFO

    def test_low_severity(self):
        assert AutoscalingPolicyEvaluator._derive_severity(75.0) == PolicySeverity.LOW

    def test_medium_severity(self):
        assert AutoscalingPolicyEvaluator._derive_severity(55.0) == PolicySeverity.MEDIUM

    def test_high_severity(self):
        assert AutoscalingPolicyEvaluator._derive_severity(35.0) == PolicySeverity.HIGH

    def test_critical_severity(self):
        assert AutoscalingPolicyEvaluator._derive_severity(10.0) == PolicySeverity.CRITICAL

    def test_boundary_90(self):
        assert AutoscalingPolicyEvaluator._derive_severity(90.0) == PolicySeverity.INFO

    def test_boundary_70(self):
        assert AutoscalingPolicyEvaluator._derive_severity(70.0) == PolicySeverity.LOW

    def test_boundary_50(self):
        assert AutoscalingPolicyEvaluator._derive_severity(50.0) == PolicySeverity.MEDIUM

    def test_boundary_30(self):
        assert AutoscalingPolicyEvaluator._derive_severity(30.0) == PolicySeverity.HIGH

    def test_boundary_0(self):
        assert AutoscalingPolicyEvaluator._derive_severity(0.0) == PolicySeverity.CRITICAL


class TestScalingLagEstimation:
    """Internal lag estimation logic."""

    def test_scale_up_cold_start_lag(self):
        lag = AutoscalingPolicyEvaluator._estimate_lag(
            ScalingDirection.UP, count_change=2, warm_pool_used=0, drain_seconds=30,
        )
        assert lag == 90.0  # 2 * 45s

    def test_scale_up_warm_pool_lag(self):
        lag = AutoscalingPolicyEvaluator._estimate_lag(
            ScalingDirection.UP, count_change=2, warm_pool_used=2, drain_seconds=30,
        )
        assert lag == 10.0  # 2 * 5s

    def test_scale_up_mixed_lag(self):
        lag = AutoscalingPolicyEvaluator._estimate_lag(
            ScalingDirection.UP, count_change=3, warm_pool_used=1, drain_seconds=30,
        )
        # cold = 2, warm = 1 -> max(2*45, 1*5) = 90
        assert lag == 90.0

    def test_scale_down_lag_equals_drain(self):
        lag = AutoscalingPolicyEvaluator._estimate_lag(
            ScalingDirection.DOWN, count_change=1, warm_pool_used=0, drain_seconds=60,
        )
        assert lag == 60.0


class TestThresholdEvaluation:
    """Internal threshold evaluation."""

    def test_reactive_scale_up(self):
        d = AutoscalingPolicyEvaluator._evaluate_threshold(
            80.0, 70.0, 30.0, ScalingStrategy.REACTIVE, [],
        )
        assert d == ScalingDirection.UP

    def test_reactive_scale_down(self):
        d = AutoscalingPolicyEvaluator._evaluate_threshold(
            20.0, 70.0, 30.0, ScalingStrategy.REACTIVE, [],
        )
        assert d == ScalingDirection.DOWN

    def test_reactive_none(self):
        d = AutoscalingPolicyEvaluator._evaluate_threshold(
            50.0, 70.0, 30.0, ScalingStrategy.REACTIVE, [],
        )
        assert d == ScalingDirection.NONE

    def test_step_up(self):
        steps = [{"threshold": 60, "direction": "up"}]
        d = AutoscalingPolicyEvaluator._evaluate_threshold(
            65.0, 70.0, 30.0, ScalingStrategy.STEP, steps,
        )
        assert d == ScalingDirection.UP

    def test_step_down(self):
        steps = [{"threshold": 20, "direction": "down"}]
        d = AutoscalingPolicyEvaluator._evaluate_threshold(
            15.0, 70.0, 30.0, ScalingStrategy.STEP, steps,
        )
        assert d == ScalingDirection.DOWN

    def test_step_no_match(self):
        steps = [{"threshold": 90, "direction": "up"}]
        d = AutoscalingPolicyEvaluator._evaluate_threshold(
            50.0, 70.0, 30.0, ScalingStrategy.STEP, steps,
        )
        assert d == ScalingDirection.NONE


class TestEnumValues:
    """Verify enum string values for serialisation stability."""

    def test_scaling_strategy_values(self):
        assert ScalingStrategy.REACTIVE.value == "reactive"
        assert ScalingStrategy.PREDICTIVE.value == "predictive"
        assert ScalingStrategy.SCHEDULED.value == "scheduled"
        assert ScalingStrategy.STEP.value == "step"

    def test_metric_type_values(self):
        assert MetricType.CPU.value == "cpu"
        assert MetricType.MEMORY.value == "memory"
        assert MetricType.REQUEST_RATE.value == "request_rate"
        assert MetricType.QUEUE_DEPTH.value == "queue_depth"
        assert MetricType.CUSTOM.value == "custom"
        assert MetricType.COMBINED.value == "combined"

    def test_scaling_direction_values(self):
        assert ScalingDirection.UP.value == "scale_up"
        assert ScalingDirection.DOWN.value == "scale_down"
        assert ScalingDirection.NONE.value == "none"

    def test_policy_severity_values(self):
        assert PolicySeverity.CRITICAL.value == "critical"
        assert PolicySeverity.HIGH.value == "high"
        assert PolicySeverity.MEDIUM.value == "medium"
        assert PolicySeverity.LOW.value == "low"
        assert PolicySeverity.INFO.value == "info"

    def test_conflict_type_values(self):
        assert ConflictType.CONTRADICTORY_THRESHOLDS.value == "contradictory_thresholds"
        assert ConflictType.OVERLAPPING_SCHEDULES.value == "overlapping_schedules"

    def test_cost_strategy_values(self):
        assert CostStrategy.RIGHT_SIZING.value == "right_sizing"
        assert CostStrategy.SPOT_MIX.value == "spot_mix"
        assert CostStrategy.RESERVED_CAPACITY.value == "reserved_capacity"
        assert CostStrategy.SCHEDULED_SCALING.value == "scheduled_scaling"
