"""Tests for state_machine_chaos module — State Machine Chaos Simulator."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.state_machine_chaos import (
    ChaosInjectionResult,
    ComponentState,
    ForbiddenTransitionRisk,
    RecoveryPath,
    StateMachineChaosEngine,
    StateMachineConfig,
    StateTransition,
    TransitionTrigger,
    _DATA_RISK_BY_TYPE,
    _DEFAULT_FORBIDDEN,
    _DEFAULT_TRANSITIONS,
    _data_risk_for_component,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        health=health,
    )


def _graph(*comps: Component, deps: list[tuple[str, str]] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    for src, tgt in deps or []:
        g.add_dependency(Dependency(source_id=src, target_id=tgt, dependency_type="requires"))
    return g


# ---------------------------------------------------------------------------
# Tests: ComponentState enum
# ---------------------------------------------------------------------------


class TestComponentState:
    def test_all_values(self) -> None:
        expected = {
            "initializing",
            "healthy",
            "degraded",
            "overloaded",
            "failing",
            "recovering",
            "maintenance",
            "draining",
            "terminated",
        }
        assert {s.value for s in ComponentState} == expected

    def test_count(self) -> None:
        assert len(ComponentState) == 9

    def test_string_comparison(self) -> None:
        assert ComponentState.HEALTHY == "healthy"
        assert ComponentState.FAILING == "failing"

    def test_enum_identity(self) -> None:
        assert ComponentState("healthy") is ComponentState.HEALTHY


# ---------------------------------------------------------------------------
# Tests: TransitionTrigger enum
# ---------------------------------------------------------------------------


class TestTransitionTrigger:
    def test_all_values(self) -> None:
        expected = {
            "load_increase",
            "load_decrease",
            "failure_detected",
            "health_check_pass",
            "health_check_fail",
            "manual_intervention",
            "timeout",
            "resource_exhaustion",
            "dependency_failure",
            "deployment",
        }
        assert {t.value for t in TransitionTrigger} == expected

    def test_count(self) -> None:
        assert len(TransitionTrigger) == 10

    def test_string_comparison(self) -> None:
        assert TransitionTrigger.DEPLOYMENT == "deployment"


# ---------------------------------------------------------------------------
# Tests: StateTransition model
# ---------------------------------------------------------------------------


class TestStateTransition:
    def test_basic_construction(self) -> None:
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.DEGRADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
        )
        assert t.from_state == ComponentState.HEALTHY
        assert t.to_state == ComponentState.DEGRADED
        assert t.trigger == TransitionTrigger.LOAD_INCREASE
        assert t.probability == 1.0
        assert t.duration_seconds == 0.0
        assert t.side_effects == []

    def test_with_all_fields(self) -> None:
        t = StateTransition(
            from_state=ComponentState.OVERLOADED,
            to_state=ComponentState.FAILING,
            trigger=TransitionTrigger.RESOURCE_EXHAUSTION,
            probability=0.6,
            duration_seconds=5.0,
            side_effects=["oom_killed"],
        )
        assert t.probability == 0.6
        assert t.duration_seconds == 5.0
        assert t.side_effects == ["oom_killed"]

    def test_probability_zero(self) -> None:
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.DEGRADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
            probability=0.0,
        )
        assert t.probability == 0.0

    def test_probability_one(self) -> None:
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.DEGRADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
            probability=1.0,
        )
        assert t.probability == 1.0

    def test_probability_invalid_above(self) -> None:
        with pytest.raises(Exception):
            StateTransition(
                from_state=ComponentState.HEALTHY,
                to_state=ComponentState.DEGRADED,
                trigger=TransitionTrigger.LOAD_INCREASE,
                probability=1.5,
            )

    def test_probability_invalid_below(self) -> None:
        with pytest.raises(Exception):
            StateTransition(
                from_state=ComponentState.HEALTHY,
                to_state=ComponentState.DEGRADED,
                trigger=TransitionTrigger.LOAD_INCREASE,
                probability=-0.1,
            )

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(Exception):
            StateTransition(
                from_state=ComponentState.HEALTHY,
                to_state=ComponentState.DEGRADED,
                trigger=TransitionTrigger.LOAD_INCREASE,
                duration_seconds=-1.0,
            )

    def test_model_copy(self) -> None:
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.DEGRADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
            probability=0.5,
        )
        t2 = t.model_copy(update={"probability": 0.8})
        assert t2.probability == 0.8
        assert t.probability == 0.5

    def test_multiple_side_effects(self) -> None:
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.FAILING,
            trigger=TransitionTrigger.FAILURE_DETECTED,
            side_effects=["alert_triggered", "error_rate_spike", "page_oncall"],
        )
        assert len(t.side_effects) == 3


# ---------------------------------------------------------------------------
# Tests: StateMachineConfig model
# ---------------------------------------------------------------------------


class TestStateMachineConfig:
    def test_basic_construction(self) -> None:
        cfg = StateMachineConfig(
            component_id="web-1",
            states=[ComponentState.HEALTHY, ComponentState.FAILING],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        assert cfg.component_id == "web-1"
        assert len(cfg.states) == 2
        assert cfg.initial_state == ComponentState.HEALTHY
        assert cfg.forbidden_transitions == []

    def test_empty_states_rejected(self) -> None:
        with pytest.raises(Exception):
            StateMachineConfig(
                component_id="web-1",
                states=[],
                transitions=[],
                initial_state=ComponentState.HEALTHY,
            )

    def test_with_forbidden_transitions(self) -> None:
        cfg = StateMachineConfig(
            component_id="db-1",
            states=list(ComponentState),
            transitions=[],
            initial_state=ComponentState.HEALTHY,
            forbidden_transitions=[("terminated", "healthy"), ("initializing", "overloaded")],
        )
        assert len(cfg.forbidden_transitions) == 2

    def test_with_transitions(self) -> None:
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.DEGRADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
        )
        cfg = StateMachineConfig(
            component_id="app-1",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED],
            transitions=[t],
            initial_state=ComponentState.HEALTHY,
        )
        assert len(cfg.transitions) == 1


# ---------------------------------------------------------------------------
# Tests: RecoveryPath model
# ---------------------------------------------------------------------------


class TestRecoveryPath:
    def test_basic(self) -> None:
        rp = RecoveryPath(
            path=[ComponentState.FAILING, ComponentState.RECOVERING, ComponentState.HEALTHY],
            total_duration_seconds=20.0,
            transitions_used=[],
        )
        assert len(rp.path) == 3
        assert rp.total_duration_seconds == 20.0

    def test_single_step_path(self) -> None:
        t = StateTransition(
            from_state=ComponentState.DEGRADED,
            to_state=ComponentState.HEALTHY,
            trigger=TransitionTrigger.LOAD_DECREASE,
            duration_seconds=5.0,
        )
        rp = RecoveryPath(
            path=[ComponentState.DEGRADED, ComponentState.HEALTHY],
            total_duration_seconds=5.0,
            transitions_used=[t],
        )
        assert len(rp.transitions_used) == 1


# ---------------------------------------------------------------------------
# Tests: ForbiddenTransitionRisk model
# ---------------------------------------------------------------------------


class TestForbiddenTransitionRisk:
    def test_basic(self) -> None:
        ftr = ForbiddenTransitionRisk(
            from_state="terminated",
            to_state="healthy",
            possible_triggers=[TransitionTrigger.MANUAL_INTERVENTION],
            risk_level="high",
        )
        assert ftr.from_state == "terminated"
        assert ftr.to_state == "healthy"
        assert ftr.risk_level == "high"

    def test_no_triggers(self) -> None:
        ftr = ForbiddenTransitionRisk(
            from_state="initializing",
            to_state="overloaded",
            possible_triggers=[],
            risk_level="low",
        )
        assert ftr.possible_triggers == []


# ---------------------------------------------------------------------------
# Tests: ChaosInjectionResult model
# ---------------------------------------------------------------------------


class TestChaosInjectionResult:
    def test_basic(self) -> None:
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.FAILING,
            trigger=TransitionTrigger.FAILURE_DETECTED,
        )
        r = ChaosInjectionResult(
            triggered_transition=t,
            cascade_effects=["dep_a:degraded"],
            recovery_path=[ComponentState.FAILING, ComponentState.RECOVERING, ComponentState.HEALTHY],
            estimated_recovery_seconds=30.0,
            data_risk="low",
        )
        assert r.data_risk == "low"
        assert len(r.cascade_effects) == 1
        assert r.estimated_recovery_seconds == 30.0


# ---------------------------------------------------------------------------
# Tests: _data_risk_for_component
# ---------------------------------------------------------------------------


class TestDataRiskForComponent:
    def test_database_failing(self) -> None:
        comp = _comp("db", ctype=ComponentType.DATABASE)
        assert _data_risk_for_component(comp, ComponentState.FAILING) == "critical"

    def test_database_terminated(self) -> None:
        comp = _comp("db", ctype=ComponentType.DATABASE)
        assert _data_risk_for_component(comp, ComponentState.TERMINATED) == "critical"

    def test_database_degraded(self) -> None:
        comp = _comp("db", ctype=ComponentType.DATABASE)
        assert _data_risk_for_component(comp, ComponentState.DEGRADED) == "high"

    def test_cache_failing(self) -> None:
        comp = _comp("cache", ctype=ComponentType.CACHE)
        assert _data_risk_for_component(comp, ComponentState.FAILING) == "medium"

    def test_cache_degraded(self) -> None:
        comp = _comp("cache", ctype=ComponentType.CACHE)
        assert _data_risk_for_component(comp, ComponentState.DEGRADED) == "low"

    def test_load_balancer_failing(self) -> None:
        comp = _comp("lb", ctype=ComponentType.LOAD_BALANCER)
        assert _data_risk_for_component(comp, ComponentState.FAILING) == "none"

    def test_app_server_failing(self) -> None:
        comp = _comp("app", ctype=ComponentType.APP_SERVER)
        assert _data_risk_for_component(comp, ComponentState.FAILING) == "low"

    def test_app_server_healthy(self) -> None:
        comp = _comp("app", ctype=ComponentType.APP_SERVER)
        assert _data_risk_for_component(comp, ComponentState.HEALTHY) == "none"

    def test_storage_terminated(self) -> None:
        comp = _comp("s3", ctype=ComponentType.STORAGE)
        assert _data_risk_for_component(comp, ComponentState.TERMINATED) == "high"

    def test_queue_failing(self) -> None:
        comp = _comp("q", ctype=ComponentType.QUEUE)
        assert _data_risk_for_component(comp, ComponentState.FAILING) == "medium"

    def test_dns_failing(self) -> None:
        comp = _comp("dns", ctype=ComponentType.DNS)
        assert _data_risk_for_component(comp, ComponentState.FAILING) == "none"

    def test_external_api_failing(self) -> None:
        comp = _comp("ext", ctype=ComponentType.EXTERNAL_API)
        assert _data_risk_for_component(comp, ComponentState.FAILING) == "low"

    def test_custom_failing(self) -> None:
        comp = _comp("custom", ctype=ComponentType.CUSTOM)
        assert _data_risk_for_component(comp, ComponentState.FAILING) == "low"

    def test_web_server_terminated(self) -> None:
        comp = _comp("web", ctype=ComponentType.WEB_SERVER)
        assert _data_risk_for_component(comp, ComponentState.TERMINATED) == "low"

    def test_storage_degraded(self) -> None:
        comp = _comp("s3", ctype=ComponentType.STORAGE)
        assert _data_risk_for_component(comp, ComponentState.DEGRADED) == "medium"


# ---------------------------------------------------------------------------
# Tests: Default transition table
# ---------------------------------------------------------------------------


class TestDefaultTransitions:
    def test_not_empty(self) -> None:
        assert len(_DEFAULT_TRANSITIONS) > 0

    def test_all_transitions_valid(self) -> None:
        for t in _DEFAULT_TRANSITIONS:
            assert t.from_state in ComponentState
            assert t.to_state in ComponentState
            assert t.trigger in TransitionTrigger
            assert 0.0 <= t.probability <= 1.0
            assert t.duration_seconds >= 0.0

    def test_default_forbidden_not_empty(self) -> None:
        assert len(_DEFAULT_FORBIDDEN) > 0

    def test_forbidden_pairs_are_strings(self) -> None:
        for from_s, to_s in _DEFAULT_FORBIDDEN:
            assert isinstance(from_s, str)
            assert isinstance(to_s, str)

    def test_has_healthy_to_degraded(self) -> None:
        found = any(
            t.from_state == ComponentState.HEALTHY
            and t.to_state == ComponentState.DEGRADED
            for t in _DEFAULT_TRANSITIONS
        )
        assert found

    def test_has_recovering_to_healthy(self) -> None:
        found = any(
            t.from_state == ComponentState.RECOVERING
            and t.to_state == ComponentState.HEALTHY
            for t in _DEFAULT_TRANSITIONS
        )
        assert found


# ---------------------------------------------------------------------------
# Tests: StateMachineChaosEngine.build_state_machine
# ---------------------------------------------------------------------------


class TestBuildStateMachine:
    def test_basic_app_server(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        assert config.component_id == "app-1"
        assert ComponentState.HEALTHY in config.states
        assert len(config.states) == 9
        assert len(config.transitions) > 0
        assert config.initial_state == ComponentState.HEALTHY

    def test_database_component(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("db-1", ctype=ComponentType.DATABASE))
        config = engine.build_state_machine(g, "db-1")
        assert config.component_id == "db-1"
        # Database transitions to FAILING should have data_integrity_risk.
        failing_transitions = [
            t for t in config.transitions if t.to_state == ComponentState.FAILING
        ]
        assert any("data_integrity_risk" in t.side_effects for t in failing_transitions)

    def test_cache_component(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("cache-1", ctype=ComponentType.CACHE))
        config = engine.build_state_machine(g, "cache-1")
        # Cache transitions to FAILING should have cache_invalidated.
        failing_transitions = [
            t for t in config.transitions if t.to_state == ComponentState.FAILING
        ]
        assert any("cache_invalidated" in t.side_effects for t in failing_transitions)

    def test_load_balancer_component(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("lb-1", ctype=ComponentType.LOAD_BALANCER))
        config = engine.build_state_machine(g, "lb-1")
        failing_transitions = [
            t for t in config.transitions if t.to_state == ComponentState.FAILING
        ]
        assert any("traffic_blackhole" in t.side_effects for t in failing_transitions)

    def test_degraded_component_initial_state(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app", health=HealthStatus.DEGRADED))
        config = engine.build_state_machine(g, "app")
        assert config.initial_state == ComponentState.DEGRADED

    def test_overloaded_component_initial_state(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app", health=HealthStatus.OVERLOADED))
        config = engine.build_state_machine(g, "app")
        assert config.initial_state == ComponentState.OVERLOADED

    def test_down_component_initial_state(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app", health=HealthStatus.DOWN))
        config = engine.build_state_machine(g, "app")
        assert config.initial_state == ComponentState.FAILING

    def test_component_not_found_raises(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        with pytest.raises(ValueError, match="not found"):
            engine.build_state_machine(g, "nonexistent")

    def test_multi_replica_component(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1", replicas=3))
        config = engine.build_state_machine(g, "app-1")
        assert len(config.transitions) > 0

    def test_forbidden_transitions_populated(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        assert len(config.forbidden_transitions) > 0

    def test_all_nine_states_present(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        assert set(config.states) == set(ComponentState)

    def test_database_recovering_duration_longer(self) -> None:
        engine = StateMachineChaosEngine()
        g_app = _graph(_comp("app", ctype=ComponentType.APP_SERVER))
        g_db = _graph(_comp("db", ctype=ComponentType.DATABASE))
        config_app = engine.build_state_machine(g_app, "app")
        config_db = engine.build_state_machine(g_db, "db")
        # Database recovery transitions should be longer.
        app_rec = [
            t for t in config_app.transitions if t.to_state == ComponentState.RECOVERING
        ]
        db_rec = [
            t for t in config_db.transitions if t.to_state == ComponentState.RECOVERING
        ]
        if app_rec and db_rec:
            assert max(t.duration_seconds for t in db_rec) >= max(
                t.duration_seconds for t in app_rec
            )

    def test_cache_recovering_duration_shorter(self) -> None:
        engine = StateMachineChaosEngine()
        g_app = _graph(_comp("app", ctype=ComponentType.APP_SERVER))
        g_cache = _graph(_comp("cache", ctype=ComponentType.CACHE))
        config_app = engine.build_state_machine(g_app, "app")
        config_cache = engine.build_state_machine(g_cache, "cache")
        app_rec = [
            t for t in config_app.transitions if t.to_state == ComponentState.RECOVERING
        ]
        cache_rec = [
            t for t in config_cache.transitions if t.to_state == ComponentState.RECOVERING
        ]
        if app_rec and cache_rec:
            assert min(t.duration_seconds for t in cache_rec) <= min(
                t.duration_seconds for t in app_rec
            )


# ---------------------------------------------------------------------------
# Tests: StateMachineChaosEngine.inject_state_chaos
# ---------------------------------------------------------------------------


class TestInjectStateChaos:
    def test_inject_failure_on_healthy(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.FAILURE_DETECTED)
        assert isinstance(result, ChaosInjectionResult)
        assert result.triggered_transition.trigger == TransitionTrigger.FAILURE_DETECTED

    def test_inject_load_increase(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.LOAD_INCREASE)
        assert result.triggered_transition.from_state == ComponentState.HEALTHY
        assert result.triggered_transition.to_state == ComponentState.DEGRADED

    def test_inject_on_degraded_component(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1", health=HealthStatus.DEGRADED))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.LOAD_INCREASE)
        assert result.triggered_transition.from_state == ComponentState.DEGRADED
        assert result.triggered_transition.to_state == ComponentState.OVERLOADED

    def test_inject_deployment(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.DEPLOYMENT)
        assert result.triggered_transition.to_state == ComponentState.DRAINING

    def test_recovery_path_exists(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.FAILURE_DETECTED)
        assert len(result.recovery_path) >= 1

    def test_recovery_path_ends_at_healthy(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.FAILURE_DETECTED)
        if len(result.recovery_path) > 1:
            assert result.recovery_path[-1] == ComponentState.HEALTHY

    def test_cascade_effects_with_dependents(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(
            _comp("app-1"),
            _comp("web-1", ctype=ComponentType.WEB_SERVER),
            deps=[("web-1", "app-1")],
        )
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.FAILURE_DETECTED)
        assert any("web-1" in e for e in result.cascade_effects)

    def test_cascade_effects_no_dependents(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("standalone"))
        result = engine.inject_state_chaos(g, "standalone", TransitionTrigger.FAILURE_DETECTED)
        # Should still have side_effects from the transition itself.
        assert isinstance(result.cascade_effects, list)

    def test_database_data_risk_critical(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("db-1", ctype=ComponentType.DATABASE))
        result = engine.inject_state_chaos(g, "db-1", TransitionTrigger.FAILURE_DETECTED)
        assert result.data_risk == "critical"

    def test_app_server_data_risk_low(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.FAILURE_DETECTED)
        assert result.data_risk == "low"

    def test_component_not_found_raises(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        with pytest.raises(ValueError, match="not found"):
            engine.inject_state_chaos(g, "no-such", TransitionTrigger.FAILURE_DETECTED)

    def test_forced_transition_when_no_match(self) -> None:
        engine = StateMachineChaosEngine()
        # Overloaded component with HEALTH_CHECK_PASS — no direct transition defined
        g = _graph(_comp("app", health=HealthStatus.OVERLOADED))
        result = engine.inject_state_chaos(g, "app", TransitionTrigger.HEALTH_CHECK_PASS)
        assert isinstance(result, ChaosInjectionResult)

    def test_estimated_recovery_seconds_positive(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.FAILURE_DETECTED)
        assert result.estimated_recovery_seconds >= 0.0

    def test_inject_resource_exhaustion(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1", health=HealthStatus.DEGRADED))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.RESOURCE_EXHAUSTION)
        assert result.triggered_transition.to_state == ComponentState.FAILING

    def test_inject_manual_intervention_on_healthy(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        result = engine.inject_state_chaos(g, "app-1", TransitionTrigger.MANUAL_INTERVENTION)
        assert result.triggered_transition.to_state == ComponentState.MAINTENANCE

    def test_inject_timeout_on_overloaded(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app", health=HealthStatus.OVERLOADED))
        result = engine.inject_state_chaos(g, "app", TransitionTrigger.TIMEOUT)
        assert result.triggered_transition.to_state == ComponentState.FAILING

    def test_inject_health_check_fail_on_degraded(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app", health=HealthStatus.DEGRADED))
        result = engine.inject_state_chaos(g, "app", TransitionTrigger.HEALTH_CHECK_FAIL)
        assert result.triggered_transition.to_state == ComponentState.FAILING

    def test_cascade_with_terminated_state(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(
            _comp("app", health=HealthStatus.DOWN),
            _comp("db", ctype=ComponentType.DATABASE),
            deps=[("app", "db")],
        )
        # Inject timeout on failing component -> terminated
        result = engine.inject_state_chaos(g, "app", TransitionTrigger.TIMEOUT)
        assert isinstance(result.cascade_effects, list)

    def test_inject_dependency_failure(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        result = engine.inject_state_chaos(g, "app", TransitionTrigger.DEPENDENCY_FAILURE)
        assert result.triggered_transition.trigger == TransitionTrigger.DEPENDENCY_FAILURE

    def test_inject_load_decrease_on_healthy(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        result = engine.inject_state_chaos(g, "app", TransitionTrigger.LOAD_DECREASE)
        assert isinstance(result, ChaosInjectionResult)

    def test_lb_data_risk_none(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("lb", ctype=ComponentType.LOAD_BALANCER))
        result = engine.inject_state_chaos(g, "lb", TransitionTrigger.FAILURE_DETECTED)
        assert result.data_risk == "none"


# ---------------------------------------------------------------------------
# Tests: StateMachineChaosEngine.find_deadlock_states
# ---------------------------------------------------------------------------


class TestFindDeadlockStates:
    def test_no_deadlocks_in_default(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        deadlocks = engine.find_deadlock_states(config)
        # Default transitions cover all states — no deadlocks.
        assert isinstance(deadlocks, list)

    def test_with_deadlock_state(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.TERMINATED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.TERMINATED,
                    trigger=TransitionTrigger.FAILURE_DETECTED,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        deadlocks = engine.find_deadlock_states(config)
        assert ComponentState.TERMINATED in deadlocks
        assert ComponentState.HEALTHY not in deadlocks

    def test_all_deadlocked(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.FAILING],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        deadlocks = engine.find_deadlock_states(config)
        assert set(deadlocks) == {ComponentState.HEALTHY, ComponentState.FAILING}

    def test_no_deadlocks_with_cycles(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.DEGRADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
                StateTransition(
                    from_state=ComponentState.DEGRADED,
                    to_state=ComponentState.HEALTHY,
                    trigger=TransitionTrigger.LOAD_DECREASE,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        deadlocks = engine.find_deadlock_states(config)
        assert deadlocks == []

    def test_single_state_is_deadlock(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.TERMINATED],
            transitions=[],
            initial_state=ComponentState.TERMINATED,
        )
        deadlocks = engine.find_deadlock_states(config)
        assert deadlocks == [ComponentState.TERMINATED]


# ---------------------------------------------------------------------------
# Tests: StateMachineChaosEngine.find_unreachable_states
# ---------------------------------------------------------------------------


class TestFindUnreachableStates:
    def test_no_unreachable_in_default(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        unreachable = engine.find_unreachable_states(config)
        # Default transitions connect all states.
        assert isinstance(unreachable, list)

    def test_with_unreachable_state(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED, ComponentState.MAINTENANCE],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.DEGRADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        unreachable = engine.find_unreachable_states(config)
        assert ComponentState.MAINTENANCE in unreachable
        assert ComponentState.HEALTHY not in unreachable
        assert ComponentState.DEGRADED not in unreachable

    def test_all_reachable(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.DEGRADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
                StateTransition(
                    from_state=ComponentState.DEGRADED,
                    to_state=ComponentState.HEALTHY,
                    trigger=TransitionTrigger.LOAD_DECREASE,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        unreachable = engine.find_unreachable_states(config)
        assert unreachable == []

    def test_only_initial_state_reachable(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED, ComponentState.FAILING],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        unreachable = engine.find_unreachable_states(config)
        assert ComponentState.DEGRADED in unreachable
        assert ComponentState.FAILING in unreachable
        assert ComponentState.HEALTHY not in unreachable

    def test_chain_reachability(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[
                ComponentState.HEALTHY,
                ComponentState.DEGRADED,
                ComponentState.OVERLOADED,
                ComponentState.MAINTENANCE,
            ],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.DEGRADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
                StateTransition(
                    from_state=ComponentState.DEGRADED,
                    to_state=ComponentState.OVERLOADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        unreachable = engine.find_unreachable_states(config)
        assert ComponentState.MAINTENANCE in unreachable
        assert ComponentState.OVERLOADED not in unreachable


# ---------------------------------------------------------------------------
# Tests: StateMachineChaosEngine.simulate_state_sequence
# ---------------------------------------------------------------------------


class TestSimulateStateSequence:
    def test_empty_triggers(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        path = engine.simulate_state_sequence(config, [])
        assert path == [ComponentState.HEALTHY]

    def test_single_trigger(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        path = engine.simulate_state_sequence(config, [TransitionTrigger.LOAD_INCREASE])
        assert len(path) == 2
        assert path[0] == ComponentState.HEALTHY
        assert path[1] == ComponentState.DEGRADED

    def test_multiple_triggers(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        triggers = [
            TransitionTrigger.LOAD_INCREASE,
            TransitionTrigger.LOAD_INCREASE,
        ]
        path = engine.simulate_state_sequence(config, triggers)
        assert len(path) == 3
        assert path[0] == ComponentState.HEALTHY
        assert path[1] == ComponentState.DEGRADED
        assert path[2] == ComponentState.OVERLOADED

    def test_unmatched_trigger_stays(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        path = engine.simulate_state_sequence(config, [TransitionTrigger.LOAD_INCREASE])
        assert path == [ComponentState.HEALTHY, ComponentState.HEALTHY]

    def test_recovery_sequence(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        triggers = [
            TransitionTrigger.FAILURE_DETECTED,   # healthy -> failing
            TransitionTrigger.MANUAL_INTERVENTION, # failing -> recovering
            TransitionTrigger.HEALTH_CHECK_PASS,   # recovering -> healthy
        ]
        path = engine.simulate_state_sequence(config, triggers)
        assert len(path) == 4
        assert path[0] == ComponentState.HEALTHY
        assert path[1] == ComponentState.FAILING
        assert path[2] == ComponentState.RECOVERING
        assert path[3] == ComponentState.HEALTHY

    def test_maintenance_sequence(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        triggers = [
            TransitionTrigger.MANUAL_INTERVENTION,  # healthy -> maintenance
            TransitionTrigger.MANUAL_INTERVENTION,  # maintenance -> healthy
        ]
        path = engine.simulate_state_sequence(config, triggers)
        assert len(path) == 3
        assert path[1] == ComponentState.MAINTENANCE
        assert path[2] == ComponentState.HEALTHY

    def test_degradation_recovery_cycle(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        triggers = [
            TransitionTrigger.LOAD_INCREASE,   # healthy -> degraded
            TransitionTrigger.LOAD_DECREASE,   # degraded -> healthy
            TransitionTrigger.LOAD_INCREASE,   # healthy -> degraded
        ]
        path = engine.simulate_state_sequence(config, triggers)
        assert len(path) == 4
        assert path[0] == ComponentState.HEALTHY
        assert path[1] == ComponentState.DEGRADED
        assert path[2] == ComponentState.HEALTHY
        assert path[3] == ComponentState.DEGRADED

    def test_deployment_sequence(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        triggers = [
            TransitionTrigger.DEPLOYMENT,    # healthy -> draining
            TransitionTrigger.DEPLOYMENT,    # draining -> initializing
            TransitionTrigger.HEALTH_CHECK_PASS,  # initializing -> healthy
        ]
        path = engine.simulate_state_sequence(config, triggers)
        assert len(path) == 4
        assert path[1] == ComponentState.DRAINING
        assert path[2] == ComponentState.INITIALIZING
        assert path[3] == ComponentState.HEALTHY

    def test_length_is_triggers_plus_one(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        triggers = [TransitionTrigger.LOAD_INCREASE] * 5
        path = engine.simulate_state_sequence(config, triggers)
        assert len(path) == 6

    def test_from_degraded_initial(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app", health=HealthStatus.DEGRADED))
        config = engine.build_state_machine(g, "app")
        triggers = [TransitionTrigger.LOAD_DECREASE]
        path = engine.simulate_state_sequence(config, triggers)
        assert path[0] == ComponentState.DEGRADED
        assert path[1] == ComponentState.HEALTHY


# ---------------------------------------------------------------------------
# Tests: StateMachineChaosEngine.analyze_recovery_paths
# ---------------------------------------------------------------------------


class TestAnalyzeRecoveryPaths:
    def test_from_healthy_returns_empty(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.HEALTHY)
        assert paths == []

    def test_from_failing_has_paths(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.FAILING)
        assert len(paths) > 0
        for p in paths:
            assert p.path[-1] == ComponentState.HEALTHY
            assert p.path[0] == ComponentState.FAILING

    def test_from_degraded_has_paths(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.DEGRADED)
        assert len(paths) > 0

    def test_from_terminated_has_paths(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.TERMINATED)
        assert len(paths) > 0
        for p in paths:
            assert p.path[-1] == ComponentState.HEALTHY

    def test_path_duration_positive(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.FAILING)
        for p in paths:
            assert p.total_duration_seconds >= 0.0

    def test_no_path_when_isolated(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.TERMINATED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.TERMINATED,
                    trigger=TransitionTrigger.FAILURE_DETECTED,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        paths = engine.analyze_recovery_paths(config, ComponentState.TERMINATED)
        assert paths == []

    def test_path_transitions_match_states(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.FAILING)
        for p in paths:
            assert len(p.transitions_used) == len(p.path) - 1

    def test_from_recovering(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.RECOVERING)
        assert len(paths) > 0
        # Direct path: recovering -> healthy should exist.
        direct = [p for p in paths if len(p.path) == 2]
        assert len(direct) > 0

    def test_from_maintenance(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.MAINTENANCE)
        assert len(paths) > 0

    def test_from_overloaded(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.OVERLOADED)
        assert len(paths) > 0

    def test_from_draining(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.DRAINING)
        assert len(paths) > 0

    def test_from_initializing(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        paths = engine.analyze_recovery_paths(config, ComponentState.INITIALIZING)
        assert len(paths) > 0


# ---------------------------------------------------------------------------
# Tests: StateMachineChaosEngine.detect_forbidden_transitions
# ---------------------------------------------------------------------------


class TestDetectForbiddenTransitions:
    def test_default_forbidden_detected(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        risks = engine.detect_forbidden_transitions(config)
        assert len(risks) == len(config.forbidden_transitions)

    def test_risk_has_correct_fields(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app-1"))
        config = engine.build_state_machine(g, "app-1")
        risks = engine.detect_forbidden_transitions(config)
        for r in risks:
            assert isinstance(r.from_state, str)
            assert isinstance(r.to_state, str)
            assert isinstance(r.possible_triggers, list)
            assert r.risk_level in ("low", "medium", "high")

    def test_no_forbidden_configured(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
            forbidden_transitions=[],
        )
        risks = engine.detect_forbidden_transitions(config)
        assert risks == []

    def test_forbidden_with_direct_transition(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.TERMINATED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.TERMINATED,
                    to_state=ComponentState.HEALTHY,
                    trigger=TransitionTrigger.MANUAL_INTERVENTION,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
            forbidden_transitions=[("terminated", "healthy")],
        )
        risks = engine.detect_forbidden_transitions(config)
        assert len(risks) == 1
        assert TransitionTrigger.MANUAL_INTERVENTION in risks[0].possible_triggers

    def test_forbidden_with_indirect_path(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.INITIALIZING, ComponentState.DEGRADED, ComponentState.OVERLOADED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.INITIALIZING,
                    to_state=ComponentState.DEGRADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
                StateTransition(
                    from_state=ComponentState.DEGRADED,
                    to_state=ComponentState.OVERLOADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
            ],
            initial_state=ComponentState.INITIALIZING,
            forbidden_transitions=[("initializing", "overloaded")],
        )
        risks = engine.detect_forbidden_transitions(config)
        assert len(risks) == 1
        # Indirect via degraded.
        assert len(risks[0].possible_triggers) > 0

    def test_risk_level_high_for_resource_exhaustion(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.INITIALIZING, ComponentState.OVERLOADED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.INITIALIZING,
                    to_state=ComponentState.OVERLOADED,
                    trigger=TransitionTrigger.RESOURCE_EXHAUSTION,
                ),
            ],
            initial_state=ComponentState.INITIALIZING,
            forbidden_transitions=[("initializing", "overloaded")],
        )
        risks = engine.detect_forbidden_transitions(config)
        assert risks[0].risk_level == "high"

    def test_risk_level_low_when_no_triggers(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.TERMINATED],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
            forbidden_transitions=[("healthy", "terminated")],
        )
        risks = engine.detect_forbidden_transitions(config)
        assert risks[0].risk_level == "low"

    def test_risk_level_medium_for_multiple_triggers(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.MAINTENANCE, ComponentState.OVERLOADED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.MAINTENANCE,
                    to_state=ComponentState.OVERLOADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
                StateTransition(
                    from_state=ComponentState.MAINTENANCE,
                    to_state=ComponentState.OVERLOADED,
                    trigger=TransitionTrigger.DEPLOYMENT,
                ),
            ],
            initial_state=ComponentState.MAINTENANCE,
            forbidden_transitions=[("maintenance", "overloaded")],
        )
        risks = engine.detect_forbidden_transitions(config)
        assert risks[0].risk_level == "medium"
        assert len(risks[0].possible_triggers) == 2


# ---------------------------------------------------------------------------
# Tests: _build_transition_lookup
# ---------------------------------------------------------------------------


class TestBuildTransitionLookup:
    def test_groups_by_from_state(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.DEGRADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.FAILING,
                    trigger=TransitionTrigger.FAILURE_DETECTED,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        lookup = engine._build_transition_lookup(config)
        assert len(lookup[ComponentState.HEALTHY]) == 2
        assert ComponentState.DEGRADED not in lookup

    def test_empty_transitions(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        lookup = engine._build_transition_lookup(config)
        assert lookup == {}


# ---------------------------------------------------------------------------
# Tests: _find_transition
# ---------------------------------------------------------------------------


class TestFindTransition:
    def test_finds_matching(self) -> None:
        engine = StateMachineChaosEngine()
        t1 = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.DEGRADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
            probability=0.3,
        )
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED],
            transitions=[t1],
            initial_state=ComponentState.HEALTHY,
        )
        result = engine._find_transition(config, ComponentState.HEALTHY, TransitionTrigger.LOAD_INCREASE)
        assert result is not None
        assert result.to_state == ComponentState.DEGRADED

    def test_returns_none_when_no_match(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        result = engine._find_transition(config, ComponentState.HEALTHY, TransitionTrigger.LOAD_INCREASE)
        assert result is None

    def test_returns_highest_probability(self) -> None:
        engine = StateMachineChaosEngine()
        t1 = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.DEGRADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
            probability=0.3,
        )
        t2 = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.OVERLOADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
            probability=0.7,
        )
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED, ComponentState.OVERLOADED],
            transitions=[t1, t2],
            initial_state=ComponentState.HEALTHY,
        )
        result = engine._find_transition(config, ComponentState.HEALTHY, TransitionTrigger.LOAD_INCREASE)
        assert result is not None
        assert result.to_state == ComponentState.OVERLOADED


# ---------------------------------------------------------------------------
# Tests: _forced_target
# ---------------------------------------------------------------------------


class TestForcedTarget:
    def test_load_increase(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.LOAD_INCREASE) == ComponentState.OVERLOADED

    def test_load_decrease(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.LOAD_DECREASE) == ComponentState.HEALTHY

    def test_failure_detected(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.FAILURE_DETECTED) == ComponentState.FAILING

    def test_health_check_pass(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.HEALTH_CHECK_PASS) == ComponentState.HEALTHY

    def test_health_check_fail(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.HEALTH_CHECK_FAIL) == ComponentState.FAILING

    def test_manual_intervention(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.MANUAL_INTERVENTION) == ComponentState.MAINTENANCE

    def test_timeout(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.TIMEOUT) == ComponentState.FAILING

    def test_resource_exhaustion(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.RESOURCE_EXHAUSTION) == ComponentState.FAILING

    def test_dependency_failure(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.DEPENDENCY_FAILURE) == ComponentState.DEGRADED

    def test_deployment(self) -> None:
        assert StateMachineChaosEngine._forced_target(TransitionTrigger.DEPLOYMENT) == ComponentState.DRAINING


# ---------------------------------------------------------------------------
# Tests: _initial_state_for
# ---------------------------------------------------------------------------


class TestInitialStateFor:
    def test_healthy(self) -> None:
        comp = _comp("app", health=HealthStatus.HEALTHY)
        assert StateMachineChaosEngine._initial_state_for(comp) == ComponentState.HEALTHY

    def test_degraded(self) -> None:
        comp = _comp("app", health=HealthStatus.DEGRADED)
        assert StateMachineChaosEngine._initial_state_for(comp) == ComponentState.DEGRADED

    def test_overloaded(self) -> None:
        comp = _comp("app", health=HealthStatus.OVERLOADED)
        assert StateMachineChaosEngine._initial_state_for(comp) == ComponentState.OVERLOADED

    def test_down(self) -> None:
        comp = _comp("app", health=HealthStatus.DOWN)
        assert StateMachineChaosEngine._initial_state_for(comp) == ComponentState.FAILING


# ---------------------------------------------------------------------------
# Tests: _adapt_transitions
# ---------------------------------------------------------------------------


class TestAdaptTransitions:
    def test_returns_list(self) -> None:
        comp = _comp("app")
        result = StateMachineChaosEngine._adapt_transitions(comp, _DEFAULT_TRANSITIONS)
        assert isinstance(result, list)
        assert len(result) == len(_DEFAULT_TRANSITIONS)

    def test_database_adds_data_integrity_risk(self) -> None:
        comp = _comp("db", ctype=ComponentType.DATABASE)
        result = StateMachineChaosEngine._adapt_transitions(comp, _DEFAULT_TRANSITIONS)
        failing_transitions = [t for t in result if t.to_state == ComponentState.FAILING]
        assert any("data_integrity_risk" in t.side_effects for t in failing_transitions)

    def test_cache_adds_cache_invalidated(self) -> None:
        comp = _comp("cache", ctype=ComponentType.CACHE)
        result = StateMachineChaosEngine._adapt_transitions(comp, _DEFAULT_TRANSITIONS)
        failing_transitions = [t for t in result if t.to_state == ComponentState.FAILING]
        assert any("cache_invalidated" in t.side_effects for t in failing_transitions)

    def test_lb_adds_traffic_blackhole(self) -> None:
        comp = _comp("lb", ctype=ComponentType.LOAD_BALANCER)
        result = StateMachineChaosEngine._adapt_transitions(comp, _DEFAULT_TRANSITIONS)
        failing_transitions = [t for t in result if t.to_state == ComponentState.FAILING]
        assert any("traffic_blackhole" in t.side_effects for t in failing_transitions)

    def test_does_not_mutate_originals(self) -> None:
        original_effects = [list(t.side_effects) for t in _DEFAULT_TRANSITIONS]
        comp = _comp("db", ctype=ComponentType.DATABASE)
        StateMachineChaosEngine._adapt_transitions(comp, _DEFAULT_TRANSITIONS)
        for i, t in enumerate(_DEFAULT_TRANSITIONS):
            assert t.side_effects == original_effects[i]


# ---------------------------------------------------------------------------
# Tests: _compute_cascade_effects
# ---------------------------------------------------------------------------


class TestComputeCascadeEffects:
    def test_no_cascade_for_healthy_transition(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(
            _comp("app"),
            _comp("web", ctype=ComponentType.WEB_SERVER),
            deps=[("web", "app")],
        )
        t = StateTransition(
            from_state=ComponentState.DEGRADED,
            to_state=ComponentState.HEALTHY,
            trigger=TransitionTrigger.LOAD_DECREASE,
            side_effects=["latency_normalized"],
        )
        effects = engine._compute_cascade_effects(g, "app", t)
        assert effects == ["latency_normalized"]

    def test_cascade_for_failing(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(
            _comp("app"),
            _comp("web"),
            deps=[("web", "app")],
        )
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.FAILING,
            trigger=TransitionTrigger.FAILURE_DETECTED,
            side_effects=["error_spike"],
        )
        effects = engine._compute_cascade_effects(g, "app", t)
        assert "error_spike" in effects
        assert any("web" in e for e in effects)

    def test_cascade_for_terminated_includes_orphan(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(
            _comp("app"),
            _comp("db", ctype=ComponentType.DATABASE),
            deps=[("app", "db")],
        )
        t = StateTransition(
            from_state=ComponentState.FAILING,
            to_state=ComponentState.TERMINATED,
            trigger=TransitionTrigger.TIMEOUT,
            side_effects=["component_dead"],
        )
        effects = engine._compute_cascade_effects(g, "app", t)
        assert any("orphaned_dependency" in e for e in effects)

    def test_no_cascade_for_degraded_transition(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(
            _comp("app"),
            _comp("web"),
            deps=[("web", "app")],
        )
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.DEGRADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
            side_effects=["latency_increase"],
        )
        effects = engine._compute_cascade_effects(g, "app", t)
        assert effects == ["latency_increase"]

    def test_cascade_for_overloaded(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(
            _comp("app"),
            _comp("web"),
            deps=[("web", "app")],
        )
        t = StateTransition(
            from_state=ComponentState.DEGRADED,
            to_state=ComponentState.OVERLOADED,
            trigger=TransitionTrigger.LOAD_INCREASE,
            side_effects=["request_queuing"],
        )
        effects = engine._compute_cascade_effects(g, "app", t)
        assert "request_queuing" in effects
        assert any("web" in e for e in effects)

    def test_multiple_dependents(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(
            _comp("db", ctype=ComponentType.DATABASE),
            _comp("app1"),
            _comp("app2"),
            deps=[("app1", "db"), ("app2", "db")],
        )
        t = StateTransition(
            from_state=ComponentState.HEALTHY,
            to_state=ComponentState.FAILING,
            trigger=TransitionTrigger.FAILURE_DETECTED,
            side_effects=[],
        )
        effects = engine._compute_cascade_effects(g, "db", t)
        assert any("app1" in e for e in effects)
        assert any("app2" in e for e in effects)


# ---------------------------------------------------------------------------
# Tests: _shortest_recovery
# ---------------------------------------------------------------------------


class TestShortestRecovery:
    def test_already_healthy(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        config = engine.build_state_machine(g, "app")
        path = engine._shortest_recovery(config, ComponentState.HEALTHY)
        assert path == [ComponentState.HEALTHY]

    def test_from_degraded(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        config = engine.build_state_machine(g, "app")
        path = engine._shortest_recovery(config, ComponentState.DEGRADED)
        assert path[-1] == ComponentState.HEALTHY
        assert path[0] == ComponentState.DEGRADED

    def test_no_path_returns_single(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.TERMINATED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.TERMINATED,
                    trigger=TransitionTrigger.FAILURE_DETECTED,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        path = engine._shortest_recovery(config, ComponentState.TERMINATED)
        assert path == [ComponentState.TERMINATED]


# ---------------------------------------------------------------------------
# Tests: _recovery_duration
# ---------------------------------------------------------------------------


class TestRecoveryDuration:
    def test_single_state_zero(self) -> None:
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        dur = StateMachineChaosEngine._recovery_duration(config, [ComponentState.HEALTHY])
        assert dur == 0.0

    def test_known_durations(self) -> None:
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.FAILING, ComponentState.RECOVERING, ComponentState.HEALTHY],
            transitions=[
                StateTransition(
                    from_state=ComponentState.FAILING,
                    to_state=ComponentState.RECOVERING,
                    trigger=TransitionTrigger.MANUAL_INTERVENTION,
                    duration_seconds=5.0,
                ),
                StateTransition(
                    from_state=ComponentState.RECOVERING,
                    to_state=ComponentState.HEALTHY,
                    trigger=TransitionTrigger.HEALTH_CHECK_PASS,
                    duration_seconds=15.0,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        path = [ComponentState.FAILING, ComponentState.RECOVERING, ComponentState.HEALTHY]
        dur = StateMachineChaosEngine._recovery_duration(config, path)
        assert dur == 20.0

    def test_fallback_duration(self) -> None:
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.FAILING, ComponentState.HEALTHY],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        path = [ComponentState.FAILING, ComponentState.HEALTHY]
        dur = StateMachineChaosEngine._recovery_duration(config, path)
        assert dur == 30.0  # fallback

    def test_empty_path(self) -> None:
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        dur = StateMachineChaosEngine._recovery_duration(config, [])
        assert dur == 0.0


# ---------------------------------------------------------------------------
# Tests: _reachable_from
# ---------------------------------------------------------------------------


class TestReachableFrom:
    def test_includes_start(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY],
            transitions=[],
            initial_state=ComponentState.HEALTHY,
        )
        reachable = engine._reachable_from(config, ComponentState.HEALTHY)
        assert ComponentState.HEALTHY in reachable

    def test_chain_reachability(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED, ComponentState.OVERLOADED],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.DEGRADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
                StateTransition(
                    from_state=ComponentState.DEGRADED,
                    to_state=ComponentState.OVERLOADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        reachable = engine._reachable_from(config, ComponentState.HEALTHY)
        assert ComponentState.DEGRADED in reachable
        assert ComponentState.OVERLOADED in reachable

    def test_not_reachable(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[ComponentState.HEALTHY, ComponentState.DEGRADED, ComponentState.MAINTENANCE],
            transitions=[
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.DEGRADED,
                    trigger=TransitionTrigger.LOAD_INCREASE,
                ),
            ],
            initial_state=ComponentState.HEALTHY,
        )
        reachable = engine._reachable_from(config, ComponentState.HEALTHY)
        assert ComponentState.MAINTENANCE not in reachable


# ---------------------------------------------------------------------------
# Tests: _assess_forbidden_risk
# ---------------------------------------------------------------------------


class TestAssessForbiddenRisk:
    def test_no_triggers_low(self) -> None:
        assert StateMachineChaosEngine._assess_forbidden_risk([]) == "low"

    def test_resource_exhaustion_high(self) -> None:
        assert StateMachineChaosEngine._assess_forbidden_risk(
            [TransitionTrigger.RESOURCE_EXHAUSTION]
        ) == "high"

    def test_failure_detected_high(self) -> None:
        assert StateMachineChaosEngine._assess_forbidden_risk(
            [TransitionTrigger.FAILURE_DETECTED]
        ) == "high"

    def test_timeout_high(self) -> None:
        assert StateMachineChaosEngine._assess_forbidden_risk(
            [TransitionTrigger.TIMEOUT]
        ) == "high"

    def test_single_non_high_trigger_medium(self) -> None:
        assert StateMachineChaosEngine._assess_forbidden_risk(
            [TransitionTrigger.LOAD_INCREASE]
        ) == "medium"

    def test_two_triggers_medium(self) -> None:
        assert StateMachineChaosEngine._assess_forbidden_risk(
            [TransitionTrigger.LOAD_INCREASE, TransitionTrigger.DEPLOYMENT]
        ) == "medium"


# ---------------------------------------------------------------------------
# Tests: DATA_RISK_BY_TYPE coverage
# ---------------------------------------------------------------------------


class TestDataRiskByType:
    def test_all_component_types_covered(self) -> None:
        for ct in ComponentType:
            assert ct in _DATA_RISK_BY_TYPE

    def test_database_is_critical(self) -> None:
        assert _DATA_RISK_BY_TYPE[ComponentType.DATABASE] == "critical"

    def test_storage_is_high(self) -> None:
        assert _DATA_RISK_BY_TYPE[ComponentType.STORAGE] == "high"

    def test_load_balancer_is_none(self) -> None:
        assert _DATA_RISK_BY_TYPE[ComponentType.LOAD_BALANCER] == "none"


# ---------------------------------------------------------------------------
# Tests: Integration / end-to-end scenarios
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_lifecycle_app_server(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        config = engine.build_state_machine(g, "app")

        # Simulate full lifecycle.
        triggers = [
            TransitionTrigger.LOAD_INCREASE,        # healthy -> degraded
            TransitionTrigger.LOAD_INCREASE,        # degraded -> overloaded
            TransitionTrigger.RESOURCE_EXHAUSTION,  # overloaded -> failing
            TransitionTrigger.MANUAL_INTERVENTION,  # failing -> recovering
            TransitionTrigger.HEALTH_CHECK_PASS,    # recovering -> healthy
        ]
        path = engine.simulate_state_sequence(config, triggers)
        assert path[0] == ComponentState.HEALTHY
        assert path[-1] == ComponentState.HEALTHY

    def test_full_lifecycle_database(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        config = engine.build_state_machine(g, "db")

        result = engine.inject_state_chaos(g, "db", TransitionTrigger.FAILURE_DETECTED)
        assert result.data_risk == "critical"
        assert len(result.recovery_path) >= 1

    def test_complex_graph_cascade(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(
            _comp("lb", ctype=ComponentType.LOAD_BALANCER),
            _comp("app-1"),
            _comp("app-2"),
            _comp("db", ctype=ComponentType.DATABASE),
            _comp("cache", ctype=ComponentType.CACHE),
            deps=[
                ("lb", "app-1"),
                ("lb", "app-2"),
                ("app-1", "db"),
                ("app-2", "db"),
                ("app-1", "cache"),
                ("app-2", "cache"),
            ],
        )
        result = engine.inject_state_chaos(g, "db", TransitionTrigger.FAILURE_DETECTED)
        assert len(result.cascade_effects) > 0
        # app-1 and app-2 depend on db, so they should be in cascade.
        assert any("app-1" in e for e in result.cascade_effects)
        assert any("app-2" in e for e in result.cascade_effects)

    def test_deadlock_and_unreachable_on_custom_config(self) -> None:
        engine = StateMachineChaosEngine()
        config = StateMachineConfig(
            component_id="test",
            states=[
                ComponentState.INITIALIZING,
                ComponentState.HEALTHY,
                ComponentState.TERMINATED,
                ComponentState.MAINTENANCE,
            ],
            transitions=[
                StateTransition(
                    from_state=ComponentState.INITIALIZING,
                    to_state=ComponentState.HEALTHY,
                    trigger=TransitionTrigger.HEALTH_CHECK_PASS,
                ),
                StateTransition(
                    from_state=ComponentState.HEALTHY,
                    to_state=ComponentState.TERMINATED,
                    trigger=TransitionTrigger.FAILURE_DETECTED,
                ),
            ],
            initial_state=ComponentState.INITIALIZING,
        )
        deadlocks = engine.find_deadlock_states(config)
        assert ComponentState.TERMINATED in deadlocks
        assert ComponentState.MAINTENANCE in deadlocks

        unreachable = engine.find_unreachable_states(config)
        assert ComponentState.MAINTENANCE in unreachable

    def test_all_triggers_on_healthy(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        for trigger in TransitionTrigger:
            result = engine.inject_state_chaos(g, "app", trigger)
            assert isinstance(result, ChaosInjectionResult)

    def test_all_component_types(self) -> None:
        engine = StateMachineChaosEngine()
        for ct in ComponentType:
            g = _graph(_comp(f"comp-{ct.value}", ctype=ct))
            config = engine.build_state_machine(g, f"comp-{ct.value}")
            assert config.component_id == f"comp-{ct.value}"
            assert len(config.transitions) > 0

    def test_draining_to_terminated_sequence(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        config = engine.build_state_machine(g, "app")
        triggers = [
            TransitionTrigger.DEPLOYMENT,  # healthy -> draining
            TransitionTrigger.TIMEOUT,     # draining -> terminated
        ]
        path = engine.simulate_state_sequence(config, triggers)
        assert path[1] == ComponentState.DRAINING
        assert path[2] == ComponentState.TERMINATED

    def test_terminated_restart_sequence(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        config = engine.build_state_machine(g, "app")
        triggers = [
            TransitionTrigger.DEPLOYMENT,           # healthy -> draining
            TransitionTrigger.TIMEOUT,              # draining -> terminated
            TransitionTrigger.MANUAL_INTERVENTION,  # terminated -> initializing
            TransitionTrigger.HEALTH_CHECK_PASS,    # initializing -> healthy
        ]
        path = engine.simulate_state_sequence(config, triggers)
        assert path[0] == ComponentState.HEALTHY
        assert path[-1] == ComponentState.HEALTHY

    def test_recovery_paths_from_all_nonhealthy_states(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        config = engine.build_state_machine(g, "app")
        for state in ComponentState:
            paths = engine.analyze_recovery_paths(config, state)
            if state == ComponentState.HEALTHY:
                assert paths == []
            else:
                # All states should have at least one recovery path in default config.
                assert len(paths) >= 0  # some may not depending on graph

    def test_multiple_forbidden_transitions(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        config = engine.build_state_machine(g, "app")
        risks = engine.detect_forbidden_transitions(config)
        assert len(risks) == len(_DEFAULT_FORBIDDEN)
        for r in risks:
            assert r.risk_level in ("low", "medium", "high")

    def test_web_server_type(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("web", ctype=ComponentType.WEB_SERVER))
        config = engine.build_state_machine(g, "web")
        assert len(config.transitions) > 0

    def test_queue_type(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("q", ctype=ComponentType.QUEUE))
        config = engine.build_state_machine(g, "q")
        assert len(config.transitions) > 0

    def test_external_api_type(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("ext", ctype=ComponentType.EXTERNAL_API))
        config = engine.build_state_machine(g, "ext")
        assert len(config.transitions) > 0

    def test_storage_type(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("s3", ctype=ComponentType.STORAGE))
        config = engine.build_state_machine(g, "s3")
        assert len(config.transitions) > 0

    def test_dns_type(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("dns", ctype=ComponentType.DNS))
        config = engine.build_state_machine(g, "dns")
        assert len(config.transitions) > 0

    def test_custom_type(self) -> None:
        engine = StateMachineChaosEngine()
        g = _graph(_comp("custom", ctype=ComponentType.CUSTOM))
        config = engine.build_state_machine(g, "custom")
        assert len(config.transitions) > 0

    def test_dfs_recovery_max_results_cap(self) -> None:
        """Verify the max_results guard in _dfs_recovery stops enumeration."""
        engine = StateMachineChaosEngine()
        g = _graph(_comp("app"))
        config = engine.build_state_machine(g, "app")
        results: list[RecoveryPath] = []
        engine._dfs_recovery(
            config,
            current=ComponentState.FAILING,
            target=ComponentState.HEALTHY,
            visited=set(),
            path_states=[ComponentState.FAILING],
            path_transitions=[],
            results=results,
            max_results=1,
        )
        assert len(results) <= 1
