# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Graceful Shutdown Simulator.

Simulates graceful shutdown behavior and validates drain/termination
sequences.  Evaluates how different shutdown configurations affect request
draining, data integrity, and service availability during planned or
unplanned terminations.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ShutdownPhase(str, Enum):
    """Phases of a graceful shutdown sequence."""

    SIGNAL_RECEIVED = "signal_received"
    NEW_CONNECTIONS_REFUSED = "new_connections_refused"
    IN_FLIGHT_DRAINING = "in_flight_draining"
    HEALTH_CHECK_FAILING = "health_check_failing"
    DEREGISTRATION = "deregistration"
    FINAL_CLEANUP = "final_cleanup"
    TERMINATED = "terminated"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ShutdownConfig(BaseModel):
    """Configuration for a graceful shutdown."""

    drain_timeout_seconds: float = Field(default=30.0, ge=0.0)
    grace_period_seconds: float = Field(default=15.0, ge=0.0)
    preStop_hook_seconds: float = Field(default=5.0, ge=0.0)
    sigterm_handler: bool = True
    connection_draining: bool = True
    deregister_from_lb: bool = True


class ShutdownPhaseResult(BaseModel):
    """Result of a single shutdown phase execution."""

    phase: ShutdownPhase
    duration_seconds: float = 0.0
    success: bool = True
    in_flight_requests: int = 0
    dropped_requests: int = 0
    detail: str = ""


class ShutdownSimulation(BaseModel):
    """Complete result of a graceful shutdown simulation."""

    phases: list[ShutdownPhaseResult] = Field(default_factory=list)
    total_duration_seconds: float = 0.0
    dropped_requests: int = 0
    in_flight_at_termination: int = 0
    data_loss_risk: str = "none"
    recommendations: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Result of validating a shutdown configuration."""

    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    score: float = Field(default=100.0, ge=0.0, le=100.0)


class ShutdownRisk(BaseModel):
    """A detected risk in a shutdown configuration."""

    risk_id: str = ""
    severity: str = "low"
    description: str = ""
    mitigation: str = ""


class ForcedKillResult(BaseModel):
    """Result of a forced kill (SIGKILL) simulation."""

    in_flight_lost: int = 0
    connections_dropped: int = 0
    data_loss_risk: str = "high"
    affected_components: list[str] = Field(default_factory=list)
    recovery_time_seconds: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class RollingRestartResult(BaseModel):
    """Result of a rolling restart simulation across multiple components."""

    total_duration_seconds: float = 0.0
    max_unavailable: int = 0
    min_available_percent: float = Field(default=100.0, ge=0.0, le=100.0)
    dropped_requests_total: int = 0
    per_component: list[ShutdownSimulation] = Field(default_factory=list)
    safe: bool = True
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _estimate_in_flight(component: Component | None) -> int:
    """Estimate typical in-flight requests based on component config."""
    if component is None:
        return 50  # sensible default

    rps = float(component.capacity.max_rps) * component.replicas
    avg_latency_s = component.capacity.timeout_seconds * 0.01  # ~1% of timeout
    in_flight = int(rps * avg_latency_s)
    return max(1, in_flight)


def _drain_rate(component: Component | None) -> float:
    """Requests drained per second during draining phase."""
    if component is None:
        return 100.0
    rps = float(component.capacity.max_rps) * component.replicas
    return max(1.0, rps * 0.8)  # 80% of capacity during drain


def _phase_duration(phase: ShutdownPhase, config: ShutdownConfig) -> float:
    """Compute nominal duration in seconds for each phase."""
    durations = {
        ShutdownPhase.SIGNAL_RECEIVED: 0.1,
        ShutdownPhase.NEW_CONNECTIONS_REFUSED: 0.5 if config.sigterm_handler else 0.0,
        ShutdownPhase.IN_FLIGHT_DRAINING: config.drain_timeout_seconds if config.connection_draining else 0.0,
        ShutdownPhase.HEALTH_CHECK_FAILING: 2.0,
        ShutdownPhase.DEREGISTRATION: 3.0 if config.deregister_from_lb else 0.0,
        ShutdownPhase.FINAL_CLEANUP: config.preStop_hook_seconds,
        ShutdownPhase.TERMINATED: 0.0,
    }
    return durations.get(phase, 0.0)


def _compute_data_loss_risk(
    dropped: int,
    in_flight_at_term: int,
    config: ShutdownConfig,
) -> str:
    """Classify data loss risk level."""
    if dropped == 0 and in_flight_at_term == 0:
        return "none"
    if not config.sigterm_handler:
        return "high"
    if in_flight_at_term > 0 and not config.connection_draining:
        return "high"
    if dropped > 50 or in_flight_at_term > 20:
        return "high"
    if dropped > 10 or in_flight_at_term > 5:
        return "medium"
    # At this point, at least one of dropped/in_flight_at_term > 0
    # (the both-zero case was handled at the top of the function)
    return "low"


def _generate_shutdown_recommendations(
    config: ShutdownConfig,
    dropped: int,
    in_flight_at_term: int,
    component: Component | None,
    total_duration: float,
) -> list[str]:
    """Generate actionable recommendations for shutdown configuration."""
    recs: list[str] = []

    if not config.sigterm_handler:
        recs.append(
            "Implement a SIGTERM handler to enable graceful shutdown; "
            "without it, processes are killed immediately"
        )

    if not config.connection_draining:
        recs.append(
            "Enable connection draining to allow in-flight requests "
            "to complete before termination"
        )

    if not config.deregister_from_lb:
        recs.append(
            "Enable load balancer deregistration to prevent new traffic "
            "from being routed to the terminating instance"
        )

    if config.drain_timeout_seconds < 5.0 and config.connection_draining:
        recs.append(
            "Drain timeout is very short; increase drain_timeout_seconds "
            "to at least 10s to allow slow requests to complete"
        )

    if config.preStop_hook_seconds < 2.0:
        recs.append(
            "preStop hook duration is very short; consider at least 2-3 seconds "
            "to allow load balancer health checks to propagate"
        )

    if config.grace_period_seconds < config.drain_timeout_seconds + config.preStop_hook_seconds:
        recs.append(
            "Grace period is shorter than drain_timeout + preStop_hook; "
            "the process may be killed before draining completes"
        )

    if dropped > 0:
        recs.append(
            f"{dropped} requests were dropped during shutdown; "
            "review drain timeout and connection draining settings"
        )

    if in_flight_at_term > 0:
        recs.append(
            f"{in_flight_at_term} requests were still in-flight at termination; "
            "increase drain timeout or implement request completion tracking"
        )

    if component is not None:
        if component.replicas <= 1:
            recs.append(
                f"Component '{component.id}' has a single replica; "
                "shutting down will cause complete unavailability"
            )
        if component.health == HealthStatus.DEGRADED:
            recs.append(
                f"Component '{component.id}' is already degraded; "
                "shutdown may take longer than expected"
            )

    if total_duration > 120.0:
        recs.append(
            "Total shutdown duration exceeds 2 minutes; consider optimizing "
            "the shutdown sequence for faster termination"
        )

    return recs


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class GracefulShutdownEngine:
    """Stateless engine for graceful shutdown simulations."""

    # -- core simulation ---------------------------------------------------

    def simulate_shutdown(
        self,
        graph: InfraGraph,
        component_id: str,
        config: ShutdownConfig,
    ) -> ShutdownSimulation:
        """Simulate a graceful shutdown sequence for *component_id*."""
        component = graph.get_component(component_id)
        estimated_in_flight = _estimate_in_flight(component)
        drain_per_second = _drain_rate(component)

        phases: list[ShutdownPhaseResult] = []
        remaining_in_flight = estimated_in_flight
        total_dropped = 0
        total_duration = 0.0

        for phase in ShutdownPhase:
            duration = _phase_duration(phase, config)
            dropped = 0
            success = True
            detail = ""

            if phase == ShutdownPhase.SIGNAL_RECEIVED:
                if not config.sigterm_handler:
                    detail = "No SIGTERM handler; process will be forcefully killed"
                    success = False
                else:
                    detail = "SIGTERM received and handled"

            elif phase == ShutdownPhase.NEW_CONNECTIONS_REFUSED:
                if config.sigterm_handler:
                    detail = "New connections are being refused"
                else:
                    detail = "No handler; connections not properly refused"
                    dropped = int(remaining_in_flight * 0.1)
                    total_dropped += dropped

            elif phase == ShutdownPhase.IN_FLIGHT_DRAINING:
                if config.connection_draining:
                    drained = int(drain_per_second * duration)
                    actual_drained = min(drained, remaining_in_flight)
                    remaining_in_flight = max(0, remaining_in_flight - actual_drained)
                    detail = f"Drained {actual_drained} requests"
                else:
                    dropped = remaining_in_flight
                    total_dropped += dropped
                    remaining_in_flight = 0
                    detail = "Connection draining disabled; all in-flight dropped"
                    success = False

            elif phase == ShutdownPhase.HEALTH_CHECK_FAILING:
                detail = "Health check returning unhealthy"

            elif phase == ShutdownPhase.DEREGISTRATION:
                if config.deregister_from_lb:
                    detail = "Deregistered from load balancer"
                else:
                    # Some requests may still arrive
                    new_arrivals = max(1, int(estimated_in_flight * 0.05))
                    dropped += new_arrivals
                    total_dropped += new_arrivals
                    detail = f"Not deregistered; {new_arrivals} new requests dropped"
                    success = False

            elif phase == ShutdownPhase.FINAL_CLEANUP:
                detail = "Running preStop hook and cleanup tasks"

            elif phase == ShutdownPhase.TERMINATED:
                if remaining_in_flight > 0:
                    total_dropped += remaining_in_flight
                    dropped = remaining_in_flight
                    detail = f"Terminated with {remaining_in_flight} in-flight"
                    success = False
                else:
                    detail = "Clean termination"

            total_duration += duration

            phases.append(
                ShutdownPhaseResult(
                    phase=phase,
                    duration_seconds=round(duration, 2),
                    success=success,
                    in_flight_requests=remaining_in_flight,
                    dropped_requests=dropped,
                    detail=detail,
                )
            )

        in_flight_at_term = remaining_in_flight
        data_loss = _compute_data_loss_risk(total_dropped, in_flight_at_term, config)
        recs = _generate_shutdown_recommendations(
            config, total_dropped, in_flight_at_term, component, total_duration,
        )

        return ShutdownSimulation(
            phases=phases,
            total_duration_seconds=round(total_duration, 2),
            dropped_requests=total_dropped,
            in_flight_at_termination=in_flight_at_term,
            data_loss_risk=data_loss,
            recommendations=recs,
        )

    # -- validate config ---------------------------------------------------

    def validate_shutdown_config(
        self,
        graph: InfraGraph,
        component_id: str,
        config: ShutdownConfig,
    ) -> ValidationResult:
        """Validate a shutdown configuration and return issues."""
        component = graph.get_component(component_id)
        errors: list[str] = []
        warnings: list[str] = []
        score = 100.0

        # Check SIGTERM handler
        if not config.sigterm_handler:
            errors.append("No SIGTERM handler configured; graceful shutdown impossible")
            score -= 30.0

        # Check connection draining
        if not config.connection_draining:
            errors.append("Connection draining is disabled; in-flight requests will be dropped")
            score -= 25.0

        # Check deregistration
        if not config.deregister_from_lb:
            warnings.append(
                "Load balancer deregistration is disabled; "
                "new requests may arrive during shutdown"
            )
            score -= 10.0

        # Check drain timeout
        if config.drain_timeout_seconds < 5.0:
            warnings.append("Drain timeout is very short (< 5s)")
            score -= 10.0
        elif config.drain_timeout_seconds > 120.0:
            warnings.append("Drain timeout is very long (> 120s); may delay deployments")
            score -= 5.0

        # Check grace period vs drain timeout
        total_needed = config.drain_timeout_seconds + config.preStop_hook_seconds
        if config.grace_period_seconds < total_needed:
            errors.append(
                f"Grace period ({config.grace_period_seconds}s) is shorter than "
                f"drain_timeout + preStop_hook ({total_needed}s)"
            )
            score -= 20.0

        # Check preStop hook
        if config.preStop_hook_seconds < 1.0:
            warnings.append("preStop hook is very short (< 1s)")
            score -= 5.0

        # Component-specific checks
        if component is not None:
            if component.type == ComponentType.DATABASE and config.drain_timeout_seconds < 30.0:
                warnings.append(
                    "Database components typically need longer drain timeouts (>= 30s)"
                )
                score -= 10.0

            if component.replicas <= 1 and not config.deregister_from_lb:
                errors.append(
                    "Single-replica component without LB deregistration will cause downtime"
                )
                score -= 15.0

            if component.health == HealthStatus.DOWN:
                warnings.append("Component is already DOWN; shutdown may behave unexpectedly")
                score -= 5.0

        score = max(0.0, score)
        valid = len(errors) == 0

        return ValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            score=round(score, 1),
        )

    # -- estimate drain time -----------------------------------------------

    def estimate_drain_time(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> float:
        """Estimate how long it takes to drain all in-flight requests."""
        component = graph.get_component(component_id)
        in_flight = _estimate_in_flight(component)
        rate = _drain_rate(component)

        if rate <= 0:
            return float('inf')

        drain_time = in_flight / rate

        # Account for long-running requests (tail latency)
        if component is not None:
            timeout = component.capacity.timeout_seconds
            drain_time = max(drain_time, timeout * 0.1)

        # Add a safety margin
        return round(drain_time * 1.2, 2)

    # -- detect shutdown risks ---------------------------------------------

    def detect_shutdown_risks(
        self,
        graph: InfraGraph,
        component_id: str,
        config: ShutdownConfig,
    ) -> list[ShutdownRisk]:
        """Detect risks in the shutdown configuration."""
        component = graph.get_component(component_id)
        risks: list[ShutdownRisk] = []

        if not config.sigterm_handler:
            risks.append(ShutdownRisk(
                risk_id="no_sigterm_handler",
                severity="critical",
                description="No SIGTERM handler; process will receive SIGKILL after grace period",
                mitigation="Implement a SIGTERM signal handler in the application",
            ))

        if not config.connection_draining:
            risks.append(ShutdownRisk(
                risk_id="no_connection_draining",
                severity="high",
                description="Connection draining disabled; in-flight requests will be terminated",
                mitigation="Enable connection draining and set appropriate drain timeout",
            ))

        if not config.deregister_from_lb:
            risks.append(ShutdownRisk(
                risk_id="no_lb_deregistration",
                severity="medium",
                description="Load balancer deregistration disabled; new traffic may arrive during shutdown",
                mitigation="Enable deregister_from_lb to stop new traffic during shutdown",
            ))

        total_needed = config.drain_timeout_seconds + config.preStop_hook_seconds
        if config.grace_period_seconds < total_needed:
            risks.append(ShutdownRisk(
                risk_id="insufficient_grace_period",
                severity="high",
                description=(
                    f"Grace period ({config.grace_period_seconds}s) < "
                    f"drain_timeout + preStop_hook ({total_needed}s); "
                    "forced kill before drain completes"
                ),
                mitigation="Increase grace_period_seconds to at least drain_timeout + preStop_hook",
            ))

        if config.drain_timeout_seconds < 5.0 and config.connection_draining:
            risks.append(ShutdownRisk(
                risk_id="short_drain_timeout",
                severity="medium",
                description="Drain timeout is very short; slow requests may not complete",
                mitigation="Increase drain_timeout_seconds to at least 10s",
            ))

        if config.preStop_hook_seconds < 2.0:
            risks.append(ShutdownRisk(
                risk_id="short_prestop_hook",
                severity="low",
                description="preStop hook is very short; LB health checks may not propagate",
                mitigation="Set preStop_hook_seconds to at least 2-3s",
            ))

        if component is not None:
            if component.replicas <= 1:
                risks.append(ShutdownRisk(
                    risk_id="single_replica",
                    severity="high",
                    description=f"Component '{component.id}' has only 1 replica; shutdown causes full outage",
                    mitigation="Add at least one additional replica before performing shutdown",
                ))

            if component.type == ComponentType.DATABASE:
                if config.drain_timeout_seconds < 30.0:
                    risks.append(ShutdownRisk(
                        risk_id="db_short_drain",
                        severity="high",
                        description="Database drain timeout < 30s; long-running transactions may be killed",
                        mitigation="Increase drain_timeout_seconds to >= 30s for database components",
                    ))

            deps = graph.get_dependents(component_id)
            if len(deps) > 3:
                risks.append(ShutdownRisk(
                    risk_id="many_dependents",
                    severity="medium",
                    description=f"Component has {len(deps)} dependents; shutdown may cascade",
                    mitigation="Ensure all dependents have retry logic and circuit breakers",
                ))

        return risks

    # -- simulate forced kill ----------------------------------------------

    def simulate_forced_kill(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> ForcedKillResult:
        """Simulate a forced kill (SIGKILL) of a component."""
        component = graph.get_component(component_id)
        in_flight = _estimate_in_flight(component)

        connections = 0
        if component is not None:
            connections = component.metrics.network_connections
            if connections == 0:
                connections = component.capacity.max_connections // 2

        affected = []
        if component_id in graph.components:
            dependents = graph.get_dependents(component_id)
            for dep in dependents:
                affected.append(dep.id)

        # Recovery time depends on component type and replicas
        recovery = 30.0  # baseline
        if component is not None:
            if component.type == ComponentType.DATABASE:
                recovery = 120.0
            elif component.type == ComponentType.QUEUE:
                recovery = 60.0
            elif component.type == ComponentType.CACHE:
                recovery = 45.0

            if component.replicas > 1:
                recovery *= 0.5
            if component.failover.enabled:
                recovery *= 0.3

        data_loss = "high"
        if component is not None:
            if component.type == ComponentType.CACHE:
                data_loss = "low"
            elif component.type == ComponentType.DATABASE:
                data_loss = "critical"
            elif component.replicas > 1:
                data_loss = "medium"

        recs: list[str] = []
        recs.append("Always prefer graceful shutdown (SIGTERM) over forced kill (SIGKILL)")
        if component is not None:
            if not component.failover.enabled:
                recs.append(f"Enable failover for '{component.id}' to reduce recovery time")
            if component.replicas <= 1:
                recs.append(f"Add replicas to '{component.id}' to maintain availability during kills")
            if component.type == ComponentType.DATABASE:
                recs.append("Database forced kill may cause data corruption; ensure WAL/journal is configured")
        if affected:
            recs.append(f"{len(affected)} dependent components will be impacted; ensure they have circuit breakers")

        return ForcedKillResult(
            in_flight_lost=in_flight,
            connections_dropped=connections,
            data_loss_risk=data_loss,
            affected_components=affected,
            recovery_time_seconds=round(recovery, 2),
            recommendations=recs,
        )

    # -- recommend config --------------------------------------------------

    def recommend_shutdown_config(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> ShutdownConfig:
        """Generate a recommended shutdown configuration for a component."""
        component = graph.get_component(component_id)

        drain_timeout = 30.0
        grace_period = 45.0
        preStop_hook = 5.0
        sigterm_handler = True
        connection_draining = True
        deregister_from_lb = True

        if component is not None:
            # Tailor by component type
            if component.type == ComponentType.DATABASE:
                drain_timeout = 60.0
                grace_period = 90.0
                preStop_hook = 10.0
            elif component.type == ComponentType.QUEUE:
                drain_timeout = 45.0
                grace_period = 60.0
                preStop_hook = 5.0
            elif component.type == ComponentType.CACHE:
                drain_timeout = 10.0
                grace_period = 20.0
                preStop_hook = 3.0
            elif component.type == ComponentType.LOAD_BALANCER:
                drain_timeout = 30.0
                grace_period = 45.0
                preStop_hook = 5.0
            elif component.type == ComponentType.APP_SERVER:
                drain_timeout = 30.0
                grace_period = 45.0
                preStop_hook = 5.0
            elif component.type == ComponentType.WEB_SERVER:
                drain_timeout = 20.0
                grace_period = 35.0
                preStop_hook = 5.0

            # Adjust for timeout - if long-running requests, extend drain
            if component.capacity.timeout_seconds > 30.0:
                drain_timeout = max(drain_timeout, component.capacity.timeout_seconds * 1.5)
                grace_period = drain_timeout + preStop_hook + 10.0

            # If many dependents, extend preStop hook for propagation
            deps = graph.get_dependents(component_id)
            if len(deps) > 3:
                preStop_hook = max(preStop_hook, 10.0)
                grace_period = drain_timeout + preStop_hook + 10.0

            # Ensure grace period is sufficient
            grace_period = max(grace_period, drain_timeout + preStop_hook + 5.0)

        return ShutdownConfig(
            drain_timeout_seconds=drain_timeout,
            grace_period_seconds=grace_period,
            preStop_hook_seconds=preStop_hook,
            sigterm_handler=sigterm_handler,
            connection_draining=connection_draining,
            deregister_from_lb=deregister_from_lb,
        )

    # -- analyze rolling restart -------------------------------------------

    def analyze_rolling_restart(
        self,
        graph: InfraGraph,
        component_ids: list[str],
        config: ShutdownConfig,
    ) -> RollingRestartResult:
        """Simulate a rolling restart across multiple components."""
        per_component: list[ShutdownSimulation] = []
        total_dropped = 0
        total_duration = 0.0
        max_unavailable = 0
        min_available_pct = 100.0

        total_replicas = 0
        for cid in component_ids:
            comp = graph.get_component(cid)
            if comp is not None:
                total_replicas += comp.replicas

        # Simulate each component shutdown sequentially
        unavailable_count = 0
        for i, cid in enumerate(component_ids):
            sim = self.simulate_shutdown(graph, cid, config)
            per_component.append(sim)
            total_dropped += sim.dropped_requests
            total_duration += sim.total_duration_seconds

            comp = graph.get_component(cid)
            if comp is not None:
                unavailable_count = 1  # one at a time in rolling restart
            else:
                unavailable_count = 1

            max_unavailable = max(max_unavailable, unavailable_count)

            if total_replicas > 0:
                available_pct = ((total_replicas - unavailable_count) / total_replicas) * 100.0
                min_available_pct = min(min_available_pct, available_pct)

        if total_replicas == 0 and len(component_ids) > 0:
            min_available_pct = 0.0

        safe = total_dropped == 0 and min_available_pct >= 50.0

        recs: list[str] = []
        if not safe:
            recs.append("Rolling restart is not safe under current configuration")

        if total_dropped > 0:
            recs.append(
                f"Total of {total_dropped} requests dropped across all restarts; "
                "review shutdown configuration"
            )

        if min_available_pct < 50.0:
            recs.append(
                "Available capacity drops below 50% during restart; "
                "add more replicas or use a slower rolling strategy"
            )

        if min_available_pct < 75.0 and min_available_pct >= 50.0:
            recs.append(
                "Available capacity drops below 75% during restart; "
                "consider adding more replicas"
            )

        if len(component_ids) > 5:
            recs.append(
                "Large number of components in rolling restart; "
                "consider batching with canary validation between batches"
            )

        if total_duration > 600.0:
            recs.append(
                "Total rolling restart duration exceeds 10 minutes; "
                "consider parallelizing non-dependent restarts"
            )

        return RollingRestartResult(
            total_duration_seconds=round(total_duration, 2),
            max_unavailable=max_unavailable,
            min_available_percent=round(_clamp(min_available_pct), 1),
            dropped_requests_total=total_dropped,
            per_component=per_component,
            safe=safe,
            recommendations=recs,
        )
