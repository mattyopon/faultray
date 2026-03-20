# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Time-stepped dynamic simulation engine for FaultRay v2.0.

Runs simulations over discrete time steps, applying time-varying traffic
patterns, auto-scaling decisions, failover logic, component recovery, and
latency cascade tracking to produce a detailed timeline of infrastructure
behaviour under stress.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect, CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType, generate_default_scenarios
from faultray.simulator.traffic import (
    TrafficPattern,
    TrafficPatternType,
    create_ddos_volumetric,
    create_flash_crowd,
    create_viral_event,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class ComponentSnapshot:
    """Point-in-time state of a single infrastructure component."""

    component_id: str
    health: HealthStatus
    utilization: float
    replicas: int
    is_failing_over: bool = False
    failover_elapsed_seconds: int = 0


@dataclass
class TimeStepSnapshot:
    """Full system state at a single point in simulated time."""

    time_seconds: int
    component_states: dict[str, ComponentSnapshot] = field(default_factory=dict)
    active_replicas: dict[str, int] = field(default_factory=dict)
    traffic_multiplier: float = 1.0
    cascade_effects: list[CascadeEffect] = field(default_factory=list)


class DynamicScenario(BaseModel):
    """A chaos scenario with optional time-varying traffic for dynamic simulation.

    Extends the concept of :class:`Scenario` with a :class:`TrafficPattern`,
    explicit duration, and configurable time-step granularity.
    """

    id: str
    name: str
    description: str
    faults: list[Fault] = Field(default_factory=list)
    traffic_pattern: TrafficPattern | None = None
    duration_seconds: int = 300
    time_step_seconds: int = 5

    @field_validator('duration_seconds', 'time_step_seconds')
    @classmethod
    def validate_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"Duration/step must be > 0, got {v}")
        return v


@dataclass
class DynamicScenarioResult:
    """Result of running a single :class:`DynamicScenario`.

    Provides the full timeline of snapshots together with aggregate metrics
    such as peak severity, recovery time, and human-readable event logs.
    """

    scenario: DynamicScenario
    snapshots: list[TimeStepSnapshot] = field(default_factory=list)
    peak_severity: float = 0.0
    peak_time_seconds: int = 0
    recovery_time_seconds: int | None = None
    autoscaling_events: list[str] = field(default_factory=list)
    failover_events: list[str] = field(default_factory=list)

    @property
    def is_critical(self) -> bool:
        """True when peak severity reaches or exceeds 7.0."""
        return self.peak_severity >= 7.0

    @property
    def is_warning(self) -> bool:
        """True when peak severity is in the warning band [4.0, 7.0)."""
        return 4.0 <= self.peak_severity < 7.0


@dataclass
class DynamicSimulationReport:
    """Aggregate report across all dynamic scenario results."""

    results: list[DynamicScenarioResult] = field(default_factory=list)
    resilience_score: float = 0.0

    @property
    def critical_findings(self) -> list[DynamicScenarioResult]:
        """Scenarios whose peak severity is critical (>= 7.0)."""
        return [r for r in self.results if r.is_critical]

    @property
    def warnings(self) -> list[DynamicScenarioResult]:
        """Scenarios whose peak severity is in the warning band."""
        return [r for r in self.results if r.is_warning]

    @property
    def passed(self) -> list[DynamicScenarioResult]:
        """Scenarios that neither reached critical nor warning levels."""
        return [r for r in self.results if not r.is_critical and not r.is_warning]


# ---------------------------------------------------------------------------
# Internal mutable state tracked per-component across time steps
# ---------------------------------------------------------------------------


class _CBState(str, Enum):
    """Circuit breaker state machine states."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class _CircuitBreakerDynamicState:
    """Mutable bookkeeping for a single circuit breaker (per dependency edge)."""

    source_id: str
    target_id: str
    state: _CBState = _CBState.CLOSED
    failure_count: int = 0
    open_since_seconds: int = 0  # time step when OPEN was entered
    recovery_timeout_seconds: float = 60.0
    failure_threshold: int = 5
    consecutive_opens: int = 0  # tracks repeated OPEN cycles for adaptive timeout


@dataclass
class _ComponentDynamicState:
    """Mutable bookkeeping for a single component during a simulation run."""

    component_id: str
    base_utilization: float
    current_utilization: float = 0.0
    current_health: HealthStatus = HealthStatus.HEALTHY
    current_replicas: int = 1
    base_replicas: int = 1

    # Auto-scaling trackers
    pending_scale_up_seconds: int = 0
    pending_scale_down_seconds: int = 0

    # Failover trackers
    consecutive_health_failures: int = 0
    is_failing_over: bool = False
    failover_elapsed_seconds: int = 0
    failover_total_seconds: int = 0
    post_failover_recovery_seconds: int = 0

    # Cache warming trackers
    is_warming: bool = False
    warming_started_at: int = 0  # time step when warming began
    warming_initial_hit_ratio: float = 0.0
    warming_duration_seconds: int = 300


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DynamicSimulationEngine:
    """Time-stepped simulation engine.

    For every time step the engine:
      1. Computes the traffic multiplier from the scenario's traffic pattern.
      2. Applies the multiplier to component utilization (with singleflight
         coalescing and cache-warming penalty).
      3. Evaluates auto-scaling decisions (scale up / scale down).
      4. Evaluates failover logic (detection, promotion, recovery) and
         triggers cache warming on failover recovery.
      5. Evaluates circuit breaker state machines on dependency edges.
      6. Runs the cascade engine for any faults active at the current step,
         skipping propagation through OPEN circuit breakers.
      7. Records a :class:`TimeStepSnapshot` of all component states.
      8. Tracks peak severity across the entire timeline.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self.cascade_engine = CascadeEngine(graph)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_dynamic_scenario(self, scenario: DynamicScenario) -> DynamicScenarioResult:
        """Run a single dynamic scenario across discrete time steps.

        Parameters
        ----------
        scenario:
            The dynamic scenario to simulate.

        Returns
        -------
        DynamicScenarioResult
            Full timeline plus aggregate metrics.
        """
        result = DynamicScenarioResult(scenario=scenario)

        # Initialise per-component mutable state
        comp_states = self._init_component_states()

        # Initialise per-dependency circuit breaker state
        cb_states = self._init_circuit_breaker_states()

        # Pre-compute the set of components affected by the traffic pattern
        affected_ids = self._resolve_affected_components(scenario.traffic_pattern)

        # Pre-compute which faults are active (keyed by target component id)
        faults_by_target: dict[str, list[Fault]] = {}
        for fault in scenario.faults:
            faults_by_target.setdefault(fault.target_component_id, []).append(fault)

        peak_severity: float = 0.0
        peak_time: int = 0
        first_critical_time: int | None = None
        recovery_time: int | None = None

        # Compute likelihood based on direct fault count vs total components.
        # Scenarios that directly fault a large percentage of components are
        # unlikely and receive a reduced likelihood factor.
        # Only apply to graphs with >= 10 components to avoid penalising
        # small test graphs where compound faults are realistic.
        total_components = len(self.graph.components)
        direct_fault_ratio = len(scenario.faults) / max(total_components, 1)
        if total_components >= 10 and direct_fault_ratio >= 0.9:
            scenario_likelihood = 0.05
        elif total_components >= 10 and direct_fault_ratio >= 0.5:
            scenario_likelihood = 0.3
        else:
            scenario_likelihood = 1.0

        total_steps = scenario.duration_seconds // scenario.time_step_seconds
        step_sec = scenario.time_step_seconds

        for step_idx in range(total_steps + 1):
            t = step_idx * step_sec

            # 1. Traffic multiplier
            multiplier = 1.0
            if scenario.traffic_pattern is not None:
                multiplier = scenario.traffic_pattern.multiplier_at(t)

            # 2. Apply traffic multiplier to utilization (singleflight + warming)
            self._apply_traffic(comp_states, multiplier, affected_ids, t)

            # 3. Auto-scaling
            scaling_msgs = self._evaluate_autoscaling(comp_states, step_sec, t)
            result.autoscaling_events.extend(scaling_msgs)

            # 4. Failover (also triggers cache warming on recovery)
            failover_msgs = self._evaluate_failover(comp_states, faults_by_target, step_sec, t)
            result.failover_events.extend(failover_msgs)

            # 5. Circuit breaker state machine
            cb_msgs = self._evaluate_circuit_breakers(cb_states, comp_states, step_sec, t)
            result.failover_events.extend(cb_msgs)

            # 6. Cascade engine for active faults (respects OPEN circuit breakers)
            step_effects = self._run_cascade_at_step(
                faults_by_target, comp_states, t, cb_states
            )

            # 7. Build snapshot
            snapshot = self._build_snapshot(comp_states, t, multiplier, step_effects)
            result.snapshots.append(snapshot)

            # 8. Calculate severity at this step
            step_severity = self._severity_for_step(comp_states, step_effects, scenario_likelihood)
            if step_severity > peak_severity:
                peak_severity = step_severity
                peak_time = t

            # Track recovery: first time after a critical event where all are HEALTHY
            all_healthy = all(
                s.current_health == HealthStatus.HEALTHY for s in comp_states.values()
            )
            if step_severity >= 4.0:
                first_critical_time = first_critical_time or t
                recovery_time = None  # reset; system is not recovered
            elif first_critical_time is not None and all_healthy and recovery_time is None:
                recovery_time = t

        result.peak_severity = round(peak_severity, 1)
        result.peak_time_seconds = peak_time
        result.recovery_time_seconds = recovery_time
        return result

    def run_all_dynamic_defaults(
        self,
        duration: int = 300,
        step: int = 5,
    ) -> DynamicSimulationReport:
        """Generate a suite of dynamic scenarios and run them all.

        The default suite combines existing static scenarios (converted to
        dynamic form) with purpose-built traffic-pattern scenarios such as
        DDoS, flash crowd, and viral events.

        Parameters
        ----------
        duration:
            Simulation duration in seconds for each scenario.
        step:
            Time step interval in seconds.

        Returns
        -------
        DynamicSimulationReport
            Aggregate report sorted by peak severity descending.
        """
        scenarios = self._generate_default_dynamic_scenarios(
            duration=duration, step=step,
        )
        results: list[DynamicScenarioResult] = []

        for scenario in scenarios:
            result = self.run_dynamic_scenario(scenario)
            results.append(result)

        results.sort(key=lambda r: r.peak_severity, reverse=True)

        return DynamicSimulationReport(
            results=results,
            resilience_score=self.graph.resilience_score(),
        )

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_component_states(self) -> dict[str, _ComponentDynamicState]:
        """Create mutable state entries for every component in the graph."""
        states: dict[str, _ComponentDynamicState] = {}
        for comp_id, comp in self.graph.components.items():
            base_util = comp.utilization()
            states[comp_id] = _ComponentDynamicState(
                component_id=comp_id,
                base_utilization=base_util,
                current_utilization=base_util,
                current_health=comp.health,
                current_replicas=comp.replicas,
                base_replicas=comp.replicas,
            )
        return states

    def _resolve_affected_components(
        self, pattern: TrafficPattern | None
    ) -> set[str] | None:
        """Determine which component IDs are affected by a traffic pattern.

        Returns ``None`` when *all* components are affected (either because no
        pattern is provided or because ``affected_components`` is empty).
        """
        if pattern is None:
            return None
        if not pattern.affected_components:
            return None  # empty list means all
        return set(pattern.affected_components)

    def _init_circuit_breaker_states(
        self,
    ) -> dict[tuple[str, str], _CircuitBreakerDynamicState]:
        """Create mutable CB state for every dependency with circuit_breaker enabled."""
        cb_states: dict[tuple[str, str], _CircuitBreakerDynamicState] = {}
        for dep in self.graph.all_dependency_edges():
            src, tgt = dep.source_id, dep.target_id
            cfg: CircuitBreakerConfig = dep.circuit_breaker
            if not cfg.enabled:
                continue
            cb_states[(src, tgt)] = _CircuitBreakerDynamicState(
                source_id=src,
                target_id=tgt,
                recovery_timeout_seconds=cfg.recovery_timeout_seconds,
                failure_threshold=cfg.failure_threshold,
            )
        return cb_states

    # ------------------------------------------------------------------
    # Step processors
    # ------------------------------------------------------------------

    def _apply_traffic(
        self,
        states: dict[str, _ComponentDynamicState],
        multiplier: float,
        affected_ids: set[str] | None,
        t: int = 0,
    ) -> None:
        """Apply the traffic multiplier to component utilization.

        When replicas have scaled from *base* to *current*, the effective
        utilization is reduced proportionally:
        ``effective = base_utilization * multiplier * (base_replicas / current_replicas)``

        Additional modifiers applied when configured:
        - **Singleflight**: reduces the effective multiplier by coalescing
          duplicate concurrent requests.
        - **Cache warming**: increases utilization during the warming period
          after failover recovery due to elevated cache-miss rate.

        Components whose health is DOWN are left untouched.
        """
        for comp_id, state in states.items():
            if state.current_health == HealthStatus.DOWN:
                continue

            comp = self.graph.get_component(comp_id)

            if affected_ids is not None and comp_id not in affected_ids:
                # Not targeted by the traffic pattern -- keep base utilization
                # but still respect replica scaling.
                replica_factor = (
                    state.base_replicas / state.current_replicas
                    if state.current_replicas > 0
                    else 1.0
                )
                state.current_utilization = state.base_utilization * replica_factor
                continue

            # --- Singleflight coalescing ---
            effective_multiplier = multiplier
            if comp is not None and comp.singleflight.enabled:
                effective_multiplier = multiplier * (
                    1.0 - comp.singleflight.coalesce_ratio
                )

            replica_factor = (
                state.base_replicas / state.current_replicas
                if state.current_replicas > 0
                else 1.0
            )
            state.current_utilization = (
                state.base_utilization * effective_multiplier * replica_factor
            )

            # --- Cache warming penalty ---
            if state.is_warming and comp is not None and comp.cache_warming.enabled:
                elapsed = t - state.warming_started_at
                warm_dur = state.warming_duration_seconds
                if elapsed >= warm_dur:
                    # Warming complete
                    state.is_warming = False
                else:
                    progress = min(1.0, elapsed / warm_dur) if warm_dur > 0 else 1.0
                    current_hit_ratio = (
                        state.warming_initial_hit_ratio
                        + (1.0 - state.warming_initial_hit_ratio) * progress
                    )
                    warming_penalty = 1.0 + (1.0 - current_hit_ratio) * 2.0
                    state.current_utilization *= warming_penalty

            # Derive health from utilization thresholds
            self._update_health_from_utilization(state)

    @staticmethod
    def _update_health_from_utilization(state: _ComponentDynamicState) -> None:
        """Set component health based on current utilization thresholds.

        Does not override DOWN or failing-over states.
        """
        if state.current_health == HealthStatus.DOWN or state.is_failing_over:
            return

        util = state.current_utilization
        if util > 100.0:
            state.current_health = HealthStatus.DOWN
        elif util > 90.0:
            state.current_health = HealthStatus.OVERLOADED
        elif util > 70.0:
            state.current_health = HealthStatus.DEGRADED
        else:
            state.current_health = HealthStatus.HEALTHY

    def _evaluate_autoscaling(
        self,
        states: dict[str, _ComponentDynamicState],
        step_sec: int,
        t: int,
    ) -> list[str]:
        """Evaluate auto-scaling for every component with scaling enabled.

        Scale-up logic:
            If utilization exceeds ``scale_up_threshold`` for longer than
            ``scale_up_delay_seconds``, add ``scale_up_step`` replicas (capped
            at ``max_replicas``).

        Scale-down logic:
            If utilization drops below ``scale_down_threshold`` for longer than
            ``scale_down_delay_seconds``, remove one replica (floored at
            ``min_replicas``).

        Returns a list of human-readable event descriptions.
        """
        events: list[str] = []

        for comp_id, state in states.items():
            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue
            cfg: AutoScalingConfig = comp.autoscaling
            if not cfg.enabled:
                continue

            util = state.current_utilization

            # --- Scale up ---
            if util > cfg.scale_up_threshold:
                state.pending_scale_up_seconds += step_sec
                state.pending_scale_down_seconds = 0  # reset cooldown

                # Emergency scale-up: bypass delay when utilization is critical
                # (>90%).  Real-world HPA implementations trigger immediate
                # scaling at extreme utilization to prevent outages.
                emergency = util > 90.0
                if emergency or state.pending_scale_up_seconds >= cfg.scale_up_delay_seconds:
                    # Emergency scaling uses a larger step to recover faster
                    step_size = cfg.scale_up_step * 2 if emergency else cfg.scale_up_step
                    new_replicas = min(
                        state.current_replicas + step_size,
                        cfg.max_replicas,
                    )
                    if new_replicas > state.current_replicas:
                        mode = "EMERGENCY" if emergency else "AUTO"
                        msg = (
                            f"[t={t}s] {mode}-SCALE UP {comp_id}: "
                            f"{state.current_replicas} -> {new_replicas} replicas "
                            f"(utilization {util:.1f}% > {cfg.scale_up_threshold}%)"
                        )
                        events.append(msg)
                        logger.info(msg)
                        state.current_replicas = new_replicas
                    state.pending_scale_up_seconds = 0  # reset after action
            else:
                state.pending_scale_up_seconds = 0

            # --- Scale down ---
            if util < cfg.scale_down_threshold:
                state.pending_scale_down_seconds += step_sec
                if state.pending_scale_down_seconds >= cfg.scale_down_delay_seconds:
                    new_replicas = max(
                        state.current_replicas - 1,
                        cfg.min_replicas,
                    )
                    if new_replicas < state.current_replicas:
                        msg = (
                            f"[t={t}s] AUTO-SCALE DOWN {comp_id}: "
                            f"{state.current_replicas} -> {new_replicas} replicas "
                            f"(utilization {util:.1f}% < {cfg.scale_down_threshold}%)"
                        )
                        events.append(msg)
                        logger.info(msg)
                        state.current_replicas = new_replicas
                    state.pending_scale_down_seconds = 0
            else:
                state.pending_scale_down_seconds = 0

        return events

    def _evaluate_failover(
        self,
        states: dict[str, _ComponentDynamicState],
        faults_by_target: dict[str, list[Fault]],
        step_sec: int,
        t: int,
    ) -> list[str]:
        """Evaluate failover progression for components with failover enabled.

        The failover state machine proceeds through three phases:

        1. **Detection**: The component is DOWN.  Once
           ``consecutive_health_failures`` reaches ``failover_threshold``,
           failover promotion begins.
        2. **Promotion**: The component stays DOWN for
           ``promotion_time_seconds`` while a replica is promoted.
        3. **Recovery**: After promotion completes the component enters a
           DEGRADED (recovering) state for an additional 50 % of the
           promotion time, then transitions to HEALTHY.

        Returns a list of human-readable event descriptions.
        """
        events: list[str] = []

        for comp_id, state in states.items():
            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue
            cfg: FailoverConfig = comp.failover
            if not cfg.enabled:
                continue

            # Determine whether this component is under a DOWN-inducing fault
            is_faulted_down = False
            for fault in faults_by_target.get(comp_id, []):
                if fault.fault_type in (
                    FaultType.COMPONENT_DOWN,
                    FaultType.NETWORK_PARTITION,
                    FaultType.MEMORY_EXHAUSTION,
                    FaultType.CONNECTION_POOL_EXHAUSTION,
                    FaultType.DISK_FULL,
                ):
                    is_faulted_down = True
                    break

            # Phase 3: Post-failover recovery
            if state.post_failover_recovery_seconds > 0:
                state.post_failover_recovery_seconds -= step_sec
                if state.post_failover_recovery_seconds <= 0:
                    state.current_health = HealthStatus.HEALTHY
                    state.post_failover_recovery_seconds = 0
                    msg = f"[t={t}s] FAILOVER RECOVERED {comp_id}: component is HEALTHY"
                    events.append(msg)
                    logger.info(msg)

                    # Trigger cache warming if configured
                    if comp.cache_warming.enabled and not state.is_warming:
                        state.is_warming = True
                        state.warming_started_at = t
                        state.warming_initial_hit_ratio = (
                            comp.cache_warming.initial_hit_ratio
                        )
                        state.warming_duration_seconds = (
                            comp.cache_warming.warm_duration_seconds
                        )
                        warm_msg = (
                            f"[t={t}s] CACHE WARMING STARTED {comp_id}: "
                            f"initial hit ratio {comp.cache_warming.initial_hit_ratio:.0%}, "
                            f"warming for {comp.cache_warming.warm_duration_seconds}s"
                        )
                        events.append(warm_msg)
                        logger.info(warm_msg)
                continue

            # Phase 2: Promotion in progress
            if state.is_failing_over:
                state.failover_elapsed_seconds += step_sec
                state.current_health = HealthStatus.DOWN
                if state.failover_elapsed_seconds >= state.failover_total_seconds:
                    # Promotion complete -- enter recovery (DEGRADED)
                    state.is_failing_over = False
                    state.current_health = HealthStatus.DEGRADED
                    recovery_period = max(step_sec, cfg.promotion_time_seconds // 2)
                    state.post_failover_recovery_seconds = recovery_period
                    state.consecutive_health_failures = 0
                    msg = (
                        f"[t={t}s] FAILOVER PROMOTED {comp_id}: "
                        f"replica promoted after {state.failover_elapsed_seconds}s, "
                        f"entering recovery (DEGRADED for ~{recovery_period}s)"
                    )
                    events.append(msg)
                    logger.info(msg)
                continue

            # Phase 1: Detection -- count consecutive health-check failures
            if state.current_health == HealthStatus.DOWN or is_faulted_down:
                state.current_health = HealthStatus.DOWN
                # Health checks fire every health_check_interval_seconds.
                # We accumulate step-seconds and count a failure each time
                # an interval boundary is crossed.
                checks_this_step = max(1, step_sec // max(1, cfg.health_check_interval_seconds))
                state.consecutive_health_failures += checks_this_step

                if state.consecutive_health_failures >= cfg.failover_threshold:
                    state.is_failing_over = True
                    state.failover_elapsed_seconds = 0
                    state.failover_total_seconds = cfg.promotion_time_seconds
                    msg = (
                        f"[t={t}s] FAILOVER STARTED {comp_id}: "
                        f"{state.consecutive_health_failures} consecutive failures "
                        f"(threshold {cfg.failover_threshold}), "
                        f"promoting replica ({cfg.promotion_time_seconds}s)"
                    )
                    events.append(msg)
                    logger.info(msg)
            else:
                # Component is not DOWN -- reset failure count
                state.consecutive_health_failures = 0

        return events

    def _evaluate_circuit_breakers(
        self,
        cb_states: dict[tuple[str, str], _CircuitBreakerDynamicState],
        comp_states: dict[str, _ComponentDynamicState],
        step_sec: int,
        t: int,
    ) -> list[str]:
        """Evaluate circuit breaker state machines on dependency edges.

        State transitions:
        - **CLOSED** (normal): If the target component is DOWN or OVERLOADED,
          increment ``failure_count``.  When ``failure_count`` reaches
          ``failure_threshold``, trip to OPEN.
        - **OPEN** (blocking): After ``recovery_timeout_seconds``, transition
          to HALF_OPEN.  While OPEN, cascade propagation through this
          dependency is suppressed.
        - **HALF_OPEN** (testing): If the target is HEALTHY, transition back
          to CLOSED.  Otherwise, trip back to OPEN.

        Returns a list of human-readable event descriptions.
        """
        events: list[str] = []

        for (src, tgt), cb in cb_states.items():
            target_state = comp_states.get(tgt)
            if target_state is None:
                continue

            target_unhealthy = target_state.current_health in (
                HealthStatus.DOWN,
                HealthStatus.OVERLOADED,
            )

            if cb.state == _CBState.CLOSED:
                if target_unhealthy:
                    cb.failure_count += 1
                    if cb.failure_count >= cb.failure_threshold:
                        cb.state = _CBState.OPEN
                        cb.open_since_seconds = t
                        msg = (
                            f"[t={t}s] CIRCUIT BREAKER OPEN {src}->{tgt}: "
                            f"{cb.failure_count} failures "
                            f"(threshold {cb.failure_threshold}), "
                            f"blocking cascade propagation"
                        )
                        events.append(msg)
                        logger.info(msg)
                else:
                    # Target is healthy -- reset failure count
                    cb.failure_count = 0

            elif cb.state == _CBState.OPEN:
                elapsed_open = t - cb.open_since_seconds
                # Adaptive recovery timeout: first attempt uses a shorter
                # timeout (1/3 of configured) to enable fast recovery from
                # transient failures.  Subsequent re-opens use exponentially
                # increasing timeouts (capped at the configured value).
                if cb.consecutive_opens == 0:
                    effective_timeout = max(
                        step_sec, cb.recovery_timeout_seconds / 3.0,
                    )
                else:
                    effective_timeout = min(
                        cb.recovery_timeout_seconds,
                        cb.recovery_timeout_seconds / 3.0 * (2 ** cb.consecutive_opens),
                    )
                if elapsed_open >= effective_timeout:
                    cb.state = _CBState.HALF_OPEN
                    msg = (
                        f"[t={t}s] CIRCUIT BREAKER HALF_OPEN {src}->{tgt}: "
                        f"adaptive timeout ({effective_timeout:.1f}s) "
                        f"elapsed, testing connectivity"
                    )
                    events.append(msg)
                    logger.info(msg)

            elif cb.state == _CBState.HALF_OPEN:
                if target_state.current_health == HealthStatus.HEALTHY:
                    cb.state = _CBState.CLOSED
                    cb.failure_count = 0
                    cb.consecutive_opens = 0  # reset on successful recovery
                    msg = (
                        f"[t={t}s] CIRCUIT BREAKER CLOSED {src}->{tgt}: "
                        f"target is HEALTHY, resuming normal traffic"
                    )
                    events.append(msg)
                    logger.info(msg)
                elif target_unhealthy:
                    # Still failing -- trip back to OPEN with increased backoff
                    cb.state = _CBState.OPEN
                    cb.open_since_seconds = t
                    cb.consecutive_opens += 1
                    msg = (
                        f"[t={t}s] CIRCUIT BREAKER RE-OPENED {src}->{tgt}: "
                        f"target still unhealthy in HALF_OPEN, "
                        f"blocking cascade propagation "
                        f"(backoff level {cb.consecutive_opens})"
                    )
                    events.append(msg)
                    logger.info(msg)

        return events

    def _run_cascade_at_step(
        self,
        faults_by_target: dict[str, list[Fault]],
        states: dict[str, _ComponentDynamicState],
        t: int,
        cb_states: dict[tuple[str, str], _CircuitBreakerDynamicState] | None = None,
    ) -> list[CascadeEffect]:
        """Run the cascade engine for faults active at time *t*.

        Also synthesises cascade effects from components that are currently in
        a non-healthy state (e.g. due to overload from traffic) so that the
        severity calculation considers the full system picture.

        When circuit breakers are in OPEN state, cascade effects that would
        propagate through the protected dependency edge are suppressed -- this
        models the circuit breaker blocking the cascade.

        Returns all :class:`CascadeEffect` instances produced for this step.
        """
        all_effects: list[CascadeEffect] = []

        # Build set of target component IDs that are blocked by OPEN CBs.
        # A CB on edge (src -> tgt) in OPEN state means the *source* will not
        # be affected by the *target*'s failure cascade.
        cb_blocked_targets: set[str] = set()
        if cb_states:
            for (src, tgt), cb in cb_states.items():
                if cb.state == _CBState.OPEN:
                    cb_blocked_targets.add(tgt)

        # Cascade effects from explicit faults
        for target_id, faults in faults_by_target.items():
            for fault in faults:
                chain = self.cascade_engine.simulate_fault(fault)
                for effect in chain.effects:
                    # Keep the effect on the faulted component itself, but
                    # suppress cascading effects if a CB blocks this target.
                    if (
                        effect.component_id != target_id
                        and target_id in cb_blocked_targets
                    ):
                        continue
                    all_effects.append(effect)

        # Synthesise effects from traffic-induced degradation
        for comp_id, state in states.items():
            if state.current_health in (HealthStatus.HEALTHY,):
                continue
            # Avoid duplicating effects that already came from an explicit fault
            if comp_id in faults_by_target:
                continue
            all_effects.append(
                CascadeEffect(
                    component_id=comp_id,
                    component_name=self._comp_name(comp_id),
                    health=state.current_health,
                    reason=self._health_reason(state),
                    metrics_impact={"utilization": state.current_utilization},
                )
            )

        return all_effects

    def _build_snapshot(
        self,
        states: dict[str, _ComponentDynamicState],
        t: int,
        multiplier: float,
        effects: list[CascadeEffect],
    ) -> TimeStepSnapshot:
        """Construct a :class:`TimeStepSnapshot` from the current state."""
        comp_snapshots: dict[str, ComponentSnapshot] = {}
        active_replicas: dict[str, int] = {}

        for comp_id, state in states.items():
            comp_snapshots[comp_id] = ComponentSnapshot(
                component_id=comp_id,
                health=state.current_health,
                utilization=round(state.current_utilization, 2),
                replicas=state.current_replicas,
                is_failing_over=state.is_failing_over,
                failover_elapsed_seconds=state.failover_elapsed_seconds,
            )
            active_replicas[comp_id] = state.current_replicas

        return TimeStepSnapshot(
            time_seconds=t,
            component_states=comp_snapshots,
            active_replicas=active_replicas,
            traffic_multiplier=round(multiplier, 4),
            cascade_effects=effects,
        )

    def _severity_for_step(
        self,
        states: dict[str, _ComponentDynamicState],
        effects: list[CascadeEffect],
        likelihood: float = 1.0,
    ) -> float:
        """Compute the severity score for a single time step.

        Uses :class:`CascadeChain`'s scoring logic by constructing a temporary
        chain that includes both explicit cascade effects and utilization-based
        component states.
        """
        total = len(self.graph.components)

        # Merge: prefer explicit effect health, supplement from state
        seen_ids: set[str] = set()
        merged_effects: list[CascadeEffect] = []
        for eff in effects:
            if eff.component_id not in seen_ids:
                merged_effects.append(eff)
                seen_ids.add(eff.component_id)

        for comp_id, state in states.items():
            if comp_id in seen_ids:
                continue
            if state.current_health != HealthStatus.HEALTHY:
                merged_effects.append(
                    CascadeEffect(
                        component_id=comp_id,
                        component_name=self._comp_name(comp_id),
                        health=state.current_health,
                        reason=self._health_reason(state),
                    )
                )

        chain = CascadeChain(
            trigger="time-step",
            effects=merged_effects,
            total_components=total,
            likelihood=likelihood,
        )
        return chain.severity

    # ------------------------------------------------------------------
    # Default scenario generation
    # ------------------------------------------------------------------

    def _generate_default_dynamic_scenarios(
        self,
        duration: int = 300,
        step: int = 5,
    ) -> list[DynamicScenario]:
        """Build the default suite of dynamic scenarios.

        This includes:
        - Conversion of every static default scenario into a dynamic form
          with configurable duration and step.
        - Purpose-built traffic-pattern scenarios (DDoS volumetric, flash
          crowd, viral event) both standalone and combined with component
          faults.
        """
        scenarios: list[DynamicScenario] = []
        component_ids = list(self.graph.components.keys())

        # --- Convert static scenarios ---
        static_scenarios = generate_default_scenarios(
            component_ids, components=self.graph.components
        )
        for static in static_scenarios:
            ds = DynamicScenario(
                id=f"dyn-{static.id}",
                name=f"[dynamic] {static.name}",
                description=static.description,
                faults=static.faults,
                traffic_pattern=None,
                duration_seconds=duration,
                time_step_seconds=step,
            )
            # Carry over static traffic_multiplier as a constant pattern
            if static.traffic_multiplier > 1.0:
                ds.traffic_pattern = TrafficPattern(
                    pattern_type=TrafficPatternType.CONSTANT,
                    peak_multiplier=static.traffic_multiplier,
                    duration_seconds=duration,
                    description=f"Constant {static.traffic_multiplier}x traffic",
                )
            scenarios.append(ds)

        # --- Traffic-pattern-only scenarios ---
        traffic_patterns: list[tuple[str, str, TrafficPattern]] = [
            (
                "ddos-volumetric-10x",
                "Volumetric DDoS (10x peak)",
                create_ddos_volumetric(peak=10.0, duration=duration),
            ),
            (
                "flash-crowd-8x",
                "Flash crowd (8x peak, 30s ramp)",
                create_flash_crowd(peak=8.0, ramp=30, duration=duration),
            ),
            (
                "viral-event-15x",
                "Viral event (15x peak, 60s ramp)",
                create_viral_event(peak=15.0, duration=duration),
            ),
        ]
        for pat_id, pat_name, pattern in traffic_patterns:
            scenarios.append(DynamicScenario(
                id=f"dyn-traffic-{pat_id}",
                name=f"[dynamic] {pat_name}",
                description=pattern.description,
                faults=[],
                traffic_pattern=pattern,
                duration_seconds=pattern.duration_seconds,
                time_step_seconds=step,
            ))

        # --- Combined: traffic pattern + single component fault ---
        for comp_id in component_ids:
            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue
            # DDoS + component down
            scenarios.append(DynamicScenario(
                id=f"dyn-ddos-down-{comp_id}",
                name=f"[dynamic] DDoS 10x + {comp_id} down",
                description=(
                    f"Volumetric DDoS at 10x while {comp_id} is down. "
                    f"Tests resilience under compound stress."
                ),
                faults=[Fault(
                    target_component_id=comp_id,
                    fault_type=FaultType.COMPONENT_DOWN,
                )],
                traffic_pattern=create_ddos_volumetric(peak=10.0, duration=duration),
                duration_seconds=duration,
                time_step_seconds=step,
            ))

        return scenarios

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _comp_name(self, comp_id: str) -> str:
        """Return the human-readable name for a component, falling back to id."""
        comp = self.graph.get_component(comp_id)
        return comp.name if comp is not None else comp_id

    @staticmethod
    def _health_reason(state: _ComponentDynamicState) -> str:
        """Derive a human-readable reason string from dynamic state."""
        warming_suffix = " (cache warming)" if state.is_warming else ""
        if state.is_failing_over:
            return (
                f"Failover in progress ({state.failover_elapsed_seconds}s / "
                f"{state.failover_total_seconds}s)"
            )
        if state.current_health == HealthStatus.DOWN:
            return f"Component down (utilization {state.current_utilization:.1f}%)"
        if state.current_health == HealthStatus.OVERLOADED:
            return (
                f"Overloaded at {state.current_utilization:.1f}% utilization"
                f"{warming_suffix}"
            )
        if state.current_health == HealthStatus.DEGRADED:
            return (
                f"Degraded at {state.current_utilization:.1f}% utilization"
                f"{warming_suffix}"
            )
        return "Healthy"
