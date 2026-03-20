# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Operational simulation engine for FaultRay v3.0.

Models real-world operational scenarios over days/weeks: deployments,
maintenance windows, gradual degradation (memory leaks, disk fill,
connection leaks), random failures based on MTBF, SLO tracking with
error budgets, and composite traffic patterns (diurnal-weekly + growth).
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from faultray.model.components import (
    Component,
    HealthStatus,
    SLOTarget,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.scenarios import Fault, FaultType
from faultray.simulator.traffic import (
    TrafficPattern,
    create_diurnal_weekly,
    create_growth_trend,
)

logger = logging.getLogger(__name__)

# Seeded RNG for reproducible operational simulation results.
_ops_rng = random.Random(2024)

# Maximum fraction of a component tier to maintain simultaneously.
# Ensures no single tier loses more than ~34% capacity during maintenance.
MAX_MAINT_FRACTION = 0.34
# Absolute cap: never maintain more than this many instances of any tier at once.
# Prevents large tiers (33 app_servers) from having oversized maintenance groups.
MAX_MAINT_GROUP_CAP = 3
# Proactive graceful restart threshold: restart when degradation accumulator
# exceeds this fraction of capacity, preventing hard failures (OOM/disk full).
GRACEFUL_RESTART_THRESHOLD = 0.80
# Downtime for a proactive graceful restart (seconds).
GRACEFUL_RESTART_DOWNTIME = 5

# Type-based default maintenance durations (seconds).
# Stateless services restart quickly; stateful services need longer windows.
_DEFAULT_MAINT_SECONDS: dict[str, int] = {
    "app_server": 60,       # Quick restart
    "web_server": 60,       # Quick restart
    "proxy": 120,           # Config reload + health check
    "load_balancer": 120,   # Config reload
    "cache": 300,           # Restart + cache warm-up
    "database": 1800,       # Patch + vacuum (30 min)
    "queue": 600,           # Drain + restart (10 min)
}

# Type-based default MTBF (hours). Stateless services are more reliable
# (easy restart) while stateful services have longer but still reasonable MTBF.
_DEFAULT_MTBF_HOURS: dict[str, float] = {
    "app_server": 2160.0,       # 90 days — stateless, auto-restart
    "web_server": 2160.0,       # 90 days
    "database": 4320.0,         # 180 days — enterprise-grade
    "cache": 1440.0,            # 60 days — volatile
    "load_balancer": 8760.0,    # 365 days — very stable
    "queue": 2160.0,            # 90 days
    "proxy": 4320.0,            # 180 days
}

# Type-based default MTTR (minutes). Stateless components auto-recover quickly.
_DEFAULT_MTTR_MINUTES: dict[str, float] = {
    "app_server": 5.0,          # Auto-restart, stateless
    "web_server": 5.0,          # Auto-restart
    "database": 30.0,           # May need manual intervention
    "cache": 10.0,              # Restart + warm-up
    "load_balancer": 2.0,       # Automatic failover
    "queue": 15.0,              # Drain + restart
    "proxy": 5.0,               # Config reload
}


# Default degradation rates by component type (when not explicitly configured).
# Rates are moderate — designed to trigger 1-3 events per component per 30 days.
_DEFAULT_DEGRADATION: dict[str, dict[str, float]] = {
    "app_server": {"memory_leak_mb_per_hour": 2.0, "connection_leak_per_hour": 0.3},
    "web_server": {"memory_leak_mb_per_hour": 1.5},
    "database": {"connection_leak_per_hour": 0.5, "disk_fill_gb_per_hour": 0.2},
    "cache": {"memory_leak_mb_per_hour": 3.0},
    "load_balancer": {"connection_leak_per_hour": 0.2},
    "queue": {"disk_fill_gb_per_hour": 0.1, "memory_leak_mb_per_hour": 1.0},
    "proxy": {"connection_leak_per_hour": 0.3},
}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TimeUnit(str, Enum):
    """Granularity for the operational simulation time steps."""

    MINUTE = "1min"
    FIVE_MINUTES = "5min"
    HOUR = "1hour"


class OpsEventType(str, Enum):
    """Types of operational events that can occur during simulation."""

    DEPLOY = "deploy"
    MAINTENANCE = "maintenance"
    CERT_RENEWAL = "cert_renewal"
    RANDOM_FAILURE = "random_failure"
    MEMORY_LEAK_OOM = "memory_leak_oom"
    DISK_FULL = "disk_full"
    CONN_POOL_EXHAUSTION = "conn_pool_exhaustion"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class OpsEvent:
    """A single operational event occurring at a specific time."""

    time_seconds: int
    event_type: OpsEventType
    target_component_id: str
    duration_seconds: int = 0
    description: str = ""


class OpsScenario(BaseModel):
    """Configuration for an operational simulation run."""

    id: str
    name: str
    description: str = ""
    duration_days: int = 7
    time_unit: TimeUnit = TimeUnit.FIVE_MINUTES
    traffic_patterns: list[TrafficPattern] = Field(default_factory=list)
    scheduled_deploys: list[dict[str, Any]] = Field(default_factory=list)
    # scheduled_deploys: list of dicts like:
    #   {"component_id": "app-1", "day_of_week": 1, "hour": 14,
    #    "downtime_seconds": 30}
    enable_random_failures: bool = False
    enable_degradation: bool = False
    enable_maintenance: bool = False
    maintenance_day_of_week: int = 6  # 0=Mon, 6=Sun
    maintenance_hour: int = 2  # 2 AM
    maintenance_duration_factor: float = 1.0  # Multiplier for maintenance durations
    random_seed: int = 2024


@dataclass
class SLIDataPoint:
    """A single SLI measurement at a point in time."""

    time_seconds: int
    total_components: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    overloaded_count: int = 0
    down_count: int = 0
    availability_percent: float = 100.0
    estimated_latency_p99_ms: float = 0.0
    error_rate: float = 0.0
    max_utilization: float = 0.0


@dataclass
class ErrorBudgetStatus:
    """Error budget status for a single SLO target."""

    slo: SLOTarget
    component_id: str
    budget_total_minutes: float = 0.0
    budget_consumed_minutes: float = 0.0
    budget_remaining_minutes: float = 0.0
    budget_remaining_percent: float = 100.0
    burn_rate_1h: float = 0.0
    burn_rate_6h: float = 0.0
    is_budget_exhausted: bool = False


@dataclass
class OpsSimulationResult:
    """Result of running an operational simulation."""

    scenario: OpsScenario
    events: list[OpsEvent] = field(default_factory=list)
    sli_timeline: list[SLIDataPoint] = field(default_factory=list)
    error_budget_statuses: list[ErrorBudgetStatus] = field(default_factory=list)
    total_downtime_seconds: float = 0.0
    total_component_down_seconds: float = 0.0
    total_deploys: int = 0
    total_failures: int = 0
    total_degradation_events: int = 0
    peak_utilization: float = 0.0
    min_availability: float = 100.0
    summary: str = ""


# ---------------------------------------------------------------------------
# Internal mutable state tracked per-component
# ---------------------------------------------------------------------------


@dataclass
class _OpsComponentState:
    """Mutable bookkeeping for a single component during ops simulation."""

    component_id: str
    base_utilization: float
    current_utilization: float = 0.0
    current_health: HealthStatus = HealthStatus.HEALTHY
    current_replicas: int = 1
    base_replicas: int = 1

    # Instance-level failure tracking: how many replicas are currently down.
    # A random failure on a multi-replica component only downs 1 instance.
    instances_down: int = 0

    # Degradation accumulators
    leaked_memory_mb: float = 0.0
    filled_disk_gb: float = 0.0
    leaked_connections: float = 0.0

    # Degradation jitter factor (0.7-1.3) — prevents thundering herd
    degradation_jitter: float = 1.0

    # Autoscaling cooldown tracking
    last_scale_up_time: int = -999999
    last_scale_down_time: int = -999999


# ---------------------------------------------------------------------------
# SLO Tracker
# ---------------------------------------------------------------------------


class SLOTracker:
    """Tracks SLI measurements and computes error budget status."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._measurements: list[SLIDataPoint] = []
        # Per-component, per-metric violation tracking
        # Key: (component_id, metric), Value: list of (time_seconds, violated)
        self._violations: dict[tuple[str, str], list[tuple[int, bool]]] = {}
        self._last_effective_health: dict[str, HealthStatus] = {}

    def _propagate_dependencies(
        self, comp_states: dict[str, _OpsComponentState]
    ) -> dict[str, HealthStatus]:
        """Compute effective health after dependency propagation.

        Returns dict[str, HealthStatus] mapping component_id to effective health.
        Does NOT modify actual component states.
        """
        effective = {
            cid: state.current_health for cid, state in comp_states.items()
        }

        # Get all dependency edges
        dep_edges = self.graph.all_dependency_edges()

        # Fixed-point iteration
        for _ in range(len(comp_states) + 1):
            changed = False
            for comp_id in comp_states:
                if effective[comp_id] == HealthStatus.DOWN:
                    continue

                # Collect requires targets for this component
                requires_targets: list[HealthStatus] = []
                has_optional_down = False

                for dep in dep_edges:
                    if dep.source_id != comp_id:
                        continue
                    target_health = effective.get(dep.target_id)
                    if target_health is None:
                        continue

                    if dep.dependency_type == "requires":
                        requires_targets.append(target_health)
                    elif dep.dependency_type == "optional":
                        if target_health == HealthStatus.DOWN:
                            has_optional_down = True
                    # async: no propagation

                # Apply rules
                if requires_targets:
                    all_down = all(
                        h == HealthStatus.DOWN for h in requires_targets
                    )
                    any_down = any(
                        h == HealthStatus.DOWN for h in requires_targets
                    )
                    any_overloaded = any(
                        h == HealthStatus.OVERLOADED
                        for h in requires_targets
                    )

                    if all_down:
                        if effective[comp_id] != HealthStatus.DOWN:
                            effective[comp_id] = HealthStatus.DOWN
                            changed = True
                    elif any_down or any_overloaded:
                        if effective[comp_id] == HealthStatus.HEALTHY:
                            effective[comp_id] = HealthStatus.DEGRADED
                            changed = True

                if has_optional_down:
                    if effective[comp_id] in (
                        HealthStatus.HEALTHY,
                    ):
                        effective[comp_id] = HealthStatus.DEGRADED
                        changed = True

            if not changed:
                break

        return effective

    def record(
        self,
        time_seconds: int,
        comp_states: dict[str, _OpsComponentState],
    ) -> SLIDataPoint:
        """Record SLI measurements at a point in time.

        Parameters
        ----------
        time_seconds:
            Current simulation time.
        comp_states:
            Current state of all components.

        Returns
        -------
        SLIDataPoint
            The measurement recorded.
        """
        # Use dependency-propagated effective health for counting
        effective_health = self._propagate_dependencies(comp_states)
        self._last_effective_health = effective_health

        # --- Service-tier aware availability ---
        # Group components into tiers by name prefix (e.g. hono-api-*).
        # A tier is available if ANY member is healthy/degraded.
        # Only when ALL members of a tier are DOWN is the tier unavailable.
        import re
        tiers: dict[str, list[str]] = {}
        standalone: list[str] = []
        for comp_id in effective_health:
            # Extract tier prefix: "hono-api-1" → "hono-api"
            match = re.match(r'^(.*?)-?\d+$', comp_id)
            prefix = match.group(1) if match else None
            # Only tier if there are multiple members with same prefix
            if prefix:
                tiers.setdefault(prefix, []).append(comp_id)
            else:
                standalone.append(comp_id)

        # Separate real tiers (2+ members) from standalone
        real_tiers = {k: v for k, v in tiers.items() if len(v) >= 2}
        for k, v in tiers.items():
            if len(v) < 2:
                standalone.extend(v)

        # Count tier-level health
        tier_count = len(real_tiers) + len(standalone)
        tier_down = 0
        tier_fractional_down = 0.0

        # For each tier: DOWN only if ALL members are DOWN
        for tier_prefix, members in real_tiers.items():
            member_health = [effective_health[m] for m in members]
            all_down = all(h == HealthStatus.DOWN for h in member_health)
            if all_down:
                # Check if failover-enabled
                comp = self.graph.get_component(members[0])
                if comp and comp.failover.enabled:
                    promotion = comp.failover.promotion_time_seconds
                    detection = comp.failover.health_check_interval_seconds * comp.failover.failover_threshold
                    tier_fractional_down += min(0.5, (promotion + detection) / 300.0)
                else:
                    tier_down += 1
            # If not all down → tier is available (no impact)

        # Standalone components: individual health
        for comp_id in standalone:
            h = effective_health[comp_id]
            if h == HealthStatus.DOWN:
                comp = self.graph.get_component(comp_id)
                if comp and comp.replicas >= 2:
                    # Multi-replica component: internal redundancy absorbs
                    # individual instance failures. Only a fractional impact
                    # during replica recovery.
                    if comp.failover.enabled:
                        promotion = comp.failover.promotion_time_seconds
                        detection = comp.failover.health_check_interval_seconds * comp.failover.failover_threshold
                        tier_fractional_down += min(0.3, (promotion + detection) / 300.0)
                    # else: replicas handle it, negligible impact
                elif comp and comp.failover.enabled:
                    # Single replica with failover: fractional impact
                    promotion = comp.failover.promotion_time_seconds
                    detection = comp.failover.health_check_interval_seconds * comp.failover.failover_threshold
                    tier_fractional_down += min(0.5, (promotion + detection) / 300.0)
                else:
                    tier_down += 1

        # Also count individual states for SLIDataPoint fields
        healthy = degraded = overloaded = down = 0
        for h in effective_health.values():
            if h == HealthStatus.HEALTHY:
                healthy += 1
            elif h == HealthStatus.DEGRADED:
                degraded += 1
            elif h == HealthStatus.OVERLOADED:
                overloaded += 1
            elif h == HealthStatus.DOWN:
                down += 1
        total = len(comp_states)

        # Service-tier availability (macro level)
        effective_up = tier_count - tier_down - tier_fractional_down
        macro_avail = (effective_up / tier_count * 100.0) if tier_count > 0 else 100.0

        # Request-level micro-availability: even when tiers are "up",
        # failover transitions cause brief request failures.
        # Model: each DOWN instance causes (failover_time / step_window)
        # fraction of requests to fail on that instance's share of traffic.
        micro_penalty = 0.0
        for comp_id, h in effective_health.items():
            if h != HealthStatus.DOWN:
                continue
            comp = self.graph.get_component(comp_id)
            if comp is None or comp.replicas < 1:
                continue
            if comp.failover.enabled:
                fo_time = (comp.failover.promotion_time_seconds
                           + comp.failover.health_check_interval_seconds
                           * comp.failover.failover_threshold)
                # This instance handles 1/replicas of traffic
                instance_share = 1.0 / max(comp.replicas, 1)
                # Fraction of the timestep where requests fail
                # Estimate step window from measurement history
                if len(self._measurements) >= 2:
                    step_window = time_seconds - self._measurements[-1].time_seconds
                else:
                    step_window = 300
                time_fraction = min(1.0, fo_time / step_window)
                micro_penalty += instance_share * time_fraction / total * 100.0

        # Network + runtime jitter: baseline request failure probability.
        # Even healthy components drop a tiny fraction of requests due to
        # packet loss, DNS timeouts, GC pauses, kernel scheduling delays.
        network_penalty = 0.0
        for comp_id in effective_health:
            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue
            # Packet loss contributes to request failures
            pkt_loss = comp.network.packet_loss_rate
            # GC pauses: fraction of time spent in GC
            gc_fraction = 0.0
            if comp.runtime_jitter.gc_pause_frequency > 0:
                gc_fraction = (
                    comp.runtime_jitter.gc_pause_ms / 1000.0
                    * comp.runtime_jitter.gc_pause_frequency
                )
            # Combined per-component failure probability
            comp_fail_prob = pkt_loss + gc_fraction
            # Weight by component's share of total
            network_penalty += comp_fail_prob / total * 100.0

        availability = max(0.0, macro_avail - micro_penalty - network_penalty)

        # Max utilization across all components
        max_util = max(
            (s.current_utilization for s in comp_states.values()), default=0.0
        )

        # Estimated p99 latency based on max utilization (hockey stick curve)
        latency_p99 = self._estimate_latency(max_util)

        # Error rate: fraction of components that are DOWN or OVERLOADED
        error_rate = ((down + overloaded) / total) if total > 0 else 0.0

        point = SLIDataPoint(
            time_seconds=time_seconds,
            total_components=total,
            healthy_count=healthy,
            degraded_count=degraded,
            overloaded_count=overloaded,
            down_count=down,
            availability_percent=round(availability, 10),
            estimated_latency_p99_ms=round(latency_p99, 2),
            error_rate=round(error_rate, 6),
            max_utilization=round(max_util, 2),
        )
        self._measurements.append(point)

        # Track per-component violations for error budget computation
        for comp_id, state in comp_states.items():
            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue
            for slo in comp.slo_targets:
                key = (comp_id, slo.metric)
                if key not in self._violations:
                    self._violations[key] = []

                violated = False
                if slo.metric == "availability":
                    # Component-level: DOWN = violated
                    violated = state.current_health == HealthStatus.DOWN
                elif slo.metric == "latency_p99":
                    # Estimate latency for this component
                    comp_latency = self._estimate_latency(
                        state.current_utilization
                    )
                    violated = comp_latency > slo.target
                elif slo.metric == "error_rate":
                    # Component contributing errors if DOWN or OVERLOADED
                    comp_error = (
                        1.0
                        if state.current_health
                        in (HealthStatus.DOWN, HealthStatus.OVERLOADED)
                        else 0.0
                    )
                    violated = comp_error > slo.target

                self._violations[key].append((time_seconds, violated))

        return point

    def error_budget_status(self) -> list[ErrorBudgetStatus]:
        """Compute error budget status for all SLO targets.

        Returns
        -------
        list[ErrorBudgetStatus]
            One entry per (component, SLO) pair.
        """
        statuses: list[ErrorBudgetStatus] = []

        for comp_id, comp in self.graph.components.items():
            for slo in comp.slo_targets:
                total = self._budget_total(slo)
                consumed = self._budget_consumed(slo, comp_id)
                remaining = max(0.0, total - consumed)
                remaining_pct = (
                    (remaining / total * 100.0) if total > 0 else 100.0
                )

                # Burn rates
                burn_1h = self._burn_rate(slo, comp_id, 3600)
                burn_6h = self._burn_rate(slo, comp_id, 21600)

                statuses.append(
                    ErrorBudgetStatus(
                        slo=slo,
                        component_id=comp_id,
                        budget_total_minutes=round(total, 2),
                        budget_consumed_minutes=round(consumed, 2),
                        budget_remaining_minutes=round(remaining, 2),
                        budget_remaining_percent=round(remaining_pct, 2),
                        burn_rate_1h=round(burn_1h, 4),
                        burn_rate_6h=round(burn_6h, 4),
                        is_budget_exhausted=remaining <= 0,
                    )
                )

        return statuses

    @staticmethod
    def _estimate_latency(max_utilization: float) -> float:
        """Estimate p99 latency using a hockey-stick curve.

        At low utilization, latency is ~5ms.  As utilization approaches
        100%, latency rises exponentially, modelling queue build-up.

        Parameters
        ----------
        max_utilization:
            Peak utilization percentage (0-100+).

        Returns
        -------
        float
            Estimated p99 latency in milliseconds.
        """
        base_ms = 5.0
        if max_utilization <= 0:
            return base_ms

        # Normalise to 0-1 range (allow > 1.0 for overloaded)
        u = max_utilization / 100.0

        if u < 0.5:
            # Low utilization: linear, roughly base to 2*base
            return base_ms * (1.0 + u)
        elif u < 0.8:
            # Medium: gentle curve
            return base_ms * (1.0 + u + (u - 0.5) ** 2 * 10)
        else:
            # High utilization: hockey stick
            # At u=1.0 -> ~50ms, at u=1.2 -> ~200ms
            overshoot = max(0.0, u - 0.8)
            return base_ms * (1.0 + u + overshoot ** 2 * 500)

    def _budget_total(self, slo: SLOTarget) -> float:
        """Calculate total error budget in minutes for an SLO.

        For availability SLOs:
            budget = window_days * 24 * 60 * (1 - target/100)
        For latency/error_rate: use window duration directly.
        """
        window_minutes = slo.window_days * 24.0 * 60.0

        if slo.metric == "availability":
            # e.g. 99.9% over 30 days -> 43.2 minutes of allowed downtime
            return window_minutes * (1.0 - slo.target / 100.0)
        else:
            # For latency and error_rate, budget is a fraction of the window
            # where violations are allowed.  We define budget as 0.1% of
            # window.
            return window_minutes * 0.001

    def _budget_consumed(self, slo: SLOTarget, comp_id: str) -> float:
        """Calculate consumed error budget in minutes."""
        key = (comp_id, slo.metric)
        violations = self._violations.get(key, [])
        if not violations:
            return 0.0

        violated_count = sum(1 for _, v in violations if v)
        total_count = len(violations)
        if total_count == 0:
            return 0.0

        # Determine the time span covered by measurements
        if total_count >= 2:
            time_span_seconds = violations[-1][0] - violations[0][0]
        else:
            time_span_seconds = 300  # default 5-minute window

        # Consumed = fraction of time in violation * time span in minutes
        violation_ratio = violated_count / total_count
        return violation_ratio * (time_span_seconds / 60.0)

    def _burn_rate(
        self, slo: SLOTarget, comp_id: str, window_seconds: int
    ) -> float:
        """Calculate burn rate over a recent window.

        Burn rate = (violation ratio in window) / (allowed violation ratio).
        A burn rate of 1.0 means budget is being consumed at exactly the
        expected rate.  > 1.0 means faster than sustainable.
        """
        key = (comp_id, slo.metric)
        violations = self._violations.get(key, [])
        if not violations:
            return 0.0

        latest_time = violations[-1][0]
        window_start = latest_time - window_seconds

        # Filter to recent window
        recent = [(t, v) for t, v in violations if t >= window_start]
        if not recent:
            return 0.0

        violated_count = sum(1 for _, v in recent if v)
        total_count = len(recent)
        if total_count == 0:
            return 0.0

        violation_ratio = violated_count / total_count

        # Expected violation ratio based on SLO
        if slo.metric == "availability":
            allowed_ratio = 1.0 - slo.target / 100.0
        else:
            allowed_ratio = 0.001  # 0.1%

        if allowed_ratio <= 0:
            return float("inf") if violation_ratio > 0 else 0.0

        return violation_ratio / allowed_ratio


# ---------------------------------------------------------------------------
# Operational Simulation Engine
# ---------------------------------------------------------------------------


class OpsSimulationEngine:
    """Operational simulation engine for multi-day infrastructure scenarios.

    Simulates realistic operational conditions including deployments,
    maintenance, gradual degradation, random failures (MTBF-based),
    and tracks SLO compliance with error budgets.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_ops_scenario(self, scenario: OpsScenario) -> OpsSimulationResult:
        """Run a single operational scenario.

        This is the main simulation method.  It steps through time at
        the configured granularity, applying traffic patterns,
        degradation models, scheduled events, and random failures,
        while tracking SLI measurements and error budgets.

        Parameters
        ----------
        scenario:
            The operational scenario configuration.

        Returns
        -------
        OpsSimulationResult
            Full simulation results including events, SLI timeline,
            and error budget status.
        """
        if scenario.duration_days <= 0:
            raise ValueError(
                f"duration_days must be positive, got {scenario.duration_days}"
            )

        rng = random.Random(scenario.random_seed)
        total_seconds = scenario.duration_days * 86400
        step_seconds = self._time_unit_to_seconds(scenario.time_unit)

        # Initialise component states
        ops_states = self._init_ops_states(scenario)

        # Schedule all events up front
        events = self._schedule_events(scenario, total_seconds, rng)

        # Sort events by time for efficient lookup
        events.sort(key=lambda e: e.time_seconds)

        # Create SLO tracker
        tracker = SLOTracker(self.graph)

        result = OpsSimulationResult(scenario=scenario)
        result.events = list(events)

        all_events = list(events)  # mutable combined list

        # Pre-count event types
        result.total_deploys = sum(
            1 for e in events if e.event_type == OpsEventType.DEPLOY
        )
        result.total_failures = sum(
            1
            for e in events
            if e.event_type
            in (
                OpsEventType.RANDOM_FAILURE,
                OpsEventType.MEMORY_LEAK_OOM,
                OpsEventType.DISK_FULL,
                OpsEventType.CONN_POOL_EXHAUSTION,
            )
        )

        total_down_seconds = 0.0
        total_component_down_seconds = 0.0
        peak_util = 0.0
        min_avail = 100.0

        # Accumulate degradation events generated during simulation
        degradation_events: list[OpsEvent] = []

        # Build component→events index for efficient downtime lookup
        _comp_events: dict[str, list] = {}
        for ev in all_events:
            _comp_events.setdefault(ev.target_component_id, []).append(ev)

        # Main simulation loop
        num_steps = total_seconds // step_seconds
        for step_idx in range(num_steps + 1):
            t = step_idx * step_seconds

            # 1. Compute composite traffic multiplier
            traffic_mult = self._composite_traffic(t, scenario)

            # 2. Apply degradation models
            new_deg_events = self._apply_degradation(
                ops_states, t, step_seconds, scenario
            )
            degradation_events.extend(new_deg_events)
            all_events.extend(new_deg_events)
            for ev in new_deg_events:
                _comp_events.setdefault(ev.target_component_id, []).append(ev)
            result.total_degradation_events += len(new_deg_events)

            # 3. Get active faults from scheduled events + degradation
            # events at this time
            active_faults = self._get_active_faults(all_events, t)

            # 4. Update component health and utilization
            for comp_id, state in ops_states.items():
                comp = self.graph.get_component(comp_id)
                if comp is None:
                    continue

                # Check if this component is targeted by an active fault
                is_faulted = any(
                    f.target_component_id == comp_id for f in active_faults
                )

                if is_faulted:
                    # Classify active faults for this component
                    all(
                        ev.event_type in (OpsEventType.MAINTENANCE, OpsEventType.DEPLOY, OpsEventType.CERT_RENEWAL)
                        for ev in all_events
                        if ev.target_component_id == comp_id
                        and ev.time_seconds <= t < ev.time_seconds + ev.duration_seconds
                    )
                    has_unplanned = any(
                        ev.event_type in (OpsEventType.RANDOM_FAILURE, OpsEventType.MEMORY_LEAK_OOM,
                                          OpsEventType.DISK_FULL, OpsEventType.CONN_POOL_EXHAUSTION)
                        for ev in all_events
                        if ev.target_component_id == comp_id
                        and ev.time_seconds <= t < ev.time_seconds + ev.duration_seconds
                    )

                    if comp.replicas > 1:
                        # Instance-level failure: unplanned faults down
                        # 1 instance, not the whole component.
                        if has_unplanned:
                            state.instances_down = min(
                                state.instances_down + 1, comp.replicas
                            )
                        if state.instances_down >= comp.replicas:
                            # All instances down → component DOWN
                            state.current_health = HealthStatus.DOWN
                            state.current_utilization = 0.0
                        else:
                            # Partial failure → DEGRADED with load redistribution
                            surviving = comp.replicas - state.instances_down
                            load_factor = comp.replicas / surviving
                            state.current_health = HealthStatus.DEGRADED
                            state.current_utilization = (
                                state.base_utilization * load_factor
                            )
                    else:
                        # Single replica: any fault = full DOWN
                        state.current_health = HealthStatus.DOWN
                        state.current_utilization = 0.0
                else:
                    # No active fault: recover instances
                    if state.instances_down > 0:
                        state.instances_down = max(0, state.instances_down - 1)

                    # Calculate effective utilization.
                    # base_utilization is already per-replica, so we
                    # scale by traffic and adjust only for *changes*
                    # in replica count from the baseline.
                    base_util = state.base_utilization
                    replica_ratio = state.base_replicas / max(
                        state.current_replicas, 1
                    )
                    effective_util = (
                        base_util * traffic_mult * replica_ratio
                    )

                    # Add degradation-induced utilization pressure
                    if (
                        comp.capacity.max_memory_mb > 0
                        and state.leaked_memory_mb > 0
                    ):
                        mem_pressure = (
                            state.leaked_memory_mb
                            / comp.capacity.max_memory_mb
                            * 100.0
                        )
                        effective_util += mem_pressure * 0.5

                    if (
                        comp.capacity.max_disk_gb > 0
                        and state.filled_disk_gb > 0
                    ):
                        disk_pressure = (
                            state.filled_disk_gb
                            / comp.capacity.max_disk_gb
                            * 100.0
                        )
                        effective_util += disk_pressure * 0.3

                    if (
                        comp.capacity.connection_pool_size > 0
                        and state.leaked_connections > 0
                    ):
                        conn_pressure = (
                            state.leaked_connections
                            / comp.capacity.connection_pool_size
                            * 100.0
                        )
                        effective_util += conn_pressure * 0.4

                    # Cap at 120% (allows overload detection)
                    effective_util = min(effective_util, 120.0)
                    state.current_utilization = effective_util

                    # Traffic/degradation-induced health changes.
                    # Utilization thresholds: >95% triggers OVERLOADED,
                    # >110% triggers DOWN.  At baseline traffic
                    # (traffic_mult=1.0) most components run at 30-65%
                    # utilization, so they remain HEALTHY.  Overload
                    # kicks in only when traffic spikes or degradation
                    # push utilization well above normal operating range.
                    if effective_util > 110.0:
                        state.current_health = HealthStatus.DOWN
                    elif effective_util > 95.0:
                        state.current_health = HealthStatus.OVERLOADED
                    elif effective_util > 85.0:
                        state.current_health = HealthStatus.DEGRADED
                    else:
                        state.current_health = HealthStatus.HEALTHY

                # 5. Simplified autoscaling
                if comp.autoscaling.enabled and not is_faulted:
                    cfg = comp.autoscaling
                    util = state.current_utilization

                    # Scale up
                    if util > cfg.scale_up_threshold:
                        cooldown_elapsed = t - state.last_scale_up_time
                        if cooldown_elapsed >= cfg.scale_up_delay_seconds:
                            new_replicas = min(
                                state.current_replicas + cfg.scale_up_step,
                                cfg.max_replicas,
                            )
                            if new_replicas > state.current_replicas:
                                logger.debug(
                                    "[t=%ds] OPS AUTO-SCALE UP %s: %d -> %d",
                                    t,
                                    comp_id,
                                    state.current_replicas,
                                    new_replicas,
                                )
                                state.current_replicas = new_replicas
                                state.last_scale_up_time = t

                    # Scale down
                    elif util < cfg.scale_down_threshold:
                        cooldown_elapsed = t - state.last_scale_down_time
                        if cooldown_elapsed >= cfg.scale_down_delay_seconds:
                            new_replicas = max(
                                state.current_replicas - 1,
                                cfg.min_replicas,
                            )
                            if new_replicas < state.current_replicas:
                                logger.debug(
                                    "[t=%ds] OPS AUTO-SCALE DOWN %s: %d -> %d",
                                    t,
                                    comp_id,
                                    state.current_replicas,
                                    new_replicas,
                                )
                                state.current_replicas = new_replicas
                                state.last_scale_down_time = t

            # 6. Record SLI measurements
            sli_point = tracker.record(t, ops_states)
            result.sli_timeline.append(sli_point)

            # Track aggregate metrics
            if sli_point.max_utilization > peak_util:
                peak_util = sli_point.max_utilization

            if sli_point.availability_percent < min_avail:
                min_avail = sli_point.availability_percent

            # Count downtime using effective health (dependency-propagated)
            # and fault-overlap with this timestep to avoid overestimating
            # short faults (e.g. a 30-second deploy fault within a
            # 300-second timestep).
            eff_health = tracker._last_effective_health
            down_count = 0
            component_overlap_total = 0.0
            for comp_id, state in ops_states.items():
                if eff_health[comp_id] == HealthStatus.DOWN:
                    down_count += 1
                    # Find the maximum overlap of any active event
                    # targeting this component with the current timestep.
                    max_overlap = 0.0
                    for ev in _comp_events.get(comp_id, []):
                        ev_start = ev.time_seconds
                        ev_end = ev_start + ev.duration_seconds
                        overlap = min(ev_end, t + step_seconds) - max(ev_start, t)
                        if overlap > max_overlap:
                            max_overlap = overlap
                    # Use the fault overlap, falling back to the full
                    # step if no matching event was found (defensive).
                    component_overlap_total += max_overlap if max_overlap > 0 else step_seconds

            total_components = len(ops_states)
            if down_count > 0 and total_components > 0:
                total_down_seconds += component_overlap_total / total_components
                total_component_down_seconds += component_overlap_total

        # Include degradation-generated events in the result
        result.events.extend(degradation_events)
        result.events.sort(key=lambda e: e.time_seconds)

        # Compute final error budget statuses
        result.error_budget_statuses = tracker.error_budget_status()
        result.total_downtime_seconds = total_down_seconds
        result.total_component_down_seconds = total_component_down_seconds
        result.peak_utilization = round(peak_util, 2)
        result.min_availability = round(min_avail, 4)

        # Generate summary
        result.summary = self._build_summary(result)

        return result

    def run_default_ops_scenarios(self, time_unit_override: TimeUnit | None = None) -> list[OpsSimulationResult]:
        """Run a suite of default operational scenarios.

        Generates 5 standard scenarios covering baseline operations,
        deployments, full operations with degradation, growth trends,
        and extended stress testing.

        Returns
        -------
        list[OpsSimulationResult]
            Results for all 5 default scenarios.
        """
        component_ids = list(self.graph.components.keys())

        # Identify app-server-like components for deploy targets
        deploy_targets: list[str] = []
        for comp_id, comp in self.graph.components.items():
            if comp.type.value in ("app_server", "web_server"):
                deploy_targets.append(comp_id)
        if not deploy_targets:
            deploy_targets = (
                component_ids[:2]
                if len(component_ids) >= 2
                else list(component_ids)
            )

        scenarios: list[OpsScenario] = []

        # --- Shared deploy schedules ---
        tuesday_deploys = [
            {
                "component_id": comp_id,
                "day_of_week": 1,  # Tuesday (0=Mon)
                "hour": 14,
                "downtime_seconds": 30,
            }
            for comp_id in deploy_targets
        ]
        thursday_deploys = [
            {
                "component_id": comp_id,
                "day_of_week": 3,  # Thursday
                "hour": 14,
                "downtime_seconds": 30,
            }
            for comp_id in deploy_targets
        ]

        # 1. ops-7d-baseline: 7 days, normal traffic, no events
        scenarios.append(
            OpsScenario(
                id="ops-7d-baseline",
                name="7-day baseline (no events)",
                description=(
                    "Baseline operational simulation for 7 days with "
                    "diurnal-weekly traffic pattern but no deployments, "
                    "failures, or degradation.  Establishes normal "
                    "operating SLI baselines."
                ),
                duration_days=7,
                time_unit=TimeUnit.FIVE_MINUTES,
                traffic_patterns=[
                    create_diurnal_weekly(
                        peak=2.0, duration=604800, weekend_factor=0.6
                    ),
                ],
                enable_random_failures=False,
                enable_degradation=False,
                enable_maintenance=False,
            )
        )

        # 2. ops-7d-with-deploys: 7 days with Tue/Thu deploys
        scenarios.append(
            OpsScenario(
                id="ops-7d-with-deploys",
                name="7-day with Tue/Thu deploys",
                description=(
                    "7-day simulation with diurnal-weekly traffic and "
                    "scheduled deployments on Tuesday and Thursday at "
                    "14:00.  Tests the impact of routine deployments "
                    "on SLO compliance."
                ),
                duration_days=7,
                time_unit=TimeUnit.FIVE_MINUTES,
                traffic_patterns=[
                    create_diurnal_weekly(
                        peak=2.0, duration=604800, weekend_factor=0.6
                    ),
                ],
                scheduled_deploys=tuesday_deploys + thursday_deploys,
                enable_random_failures=False,
                enable_degradation=False,
                enable_maintenance=False,
            )
        )

        # 3. ops-7d-full: 7 days with deploys + random failures +
        #    degradation
        scenarios.append(
            OpsScenario(
                id="ops-7d-full",
                name="7-day full operations",
                description=(
                    "Full operational simulation for 7 days including "
                    "diurnal-weekly traffic, scheduled deployments "
                    "(Tue/Thu), random MTBF-based failures, gradual "
                    "degradation (memory leaks, disk fill), and "
                    "weekly maintenance windows."
                ),
                duration_days=7,
                time_unit=TimeUnit.FIVE_MINUTES,
                traffic_patterns=[
                    create_diurnal_weekly(
                        peak=2.5, duration=604800, weekend_factor=0.6
                    ),
                ],
                scheduled_deploys=tuesday_deploys + thursday_deploys,
                enable_random_failures=True,
                enable_degradation=True,
                enable_maintenance=True,
                maintenance_day_of_week=6,  # Sunday
                maintenance_hour=2,
            )
        )

        # 4. ops-14d-growth: 14 days with 10% monthly growth
        scenarios.append(
            OpsScenario(
                id="ops-14d-growth",
                name="14-day with 10% monthly growth",
                description=(
                    "14-day simulation combining diurnal-weekly traffic "
                    "with a 10% monthly growth trend.  Tests whether "
                    "autoscaling and capacity planning keep up with "
                    "increasing demand."
                ),
                duration_days=14,
                time_unit=TimeUnit.FIVE_MINUTES,
                traffic_patterns=[
                    create_diurnal_weekly(
                        peak=2.0, duration=1209600, weekend_factor=0.6
                    ),
                    create_growth_trend(
                        monthly_rate=0.1, duration=1209600
                    ),
                ],
                scheduled_deploys=tuesday_deploys + thursday_deploys,
                enable_random_failures=True,
                enable_degradation=True,
                enable_maintenance=True,
                maintenance_day_of_week=6,
                maintenance_hour=2,
            )
        )

        # 5. ops-30d-stress: 30 days full stress test
        scenarios.append(
            OpsScenario(
                id="ops-30d-stress",
                name="30-day stress test",
                description=(
                    "Extended 30-day stress test with elevated "
                    "diurnal-weekly traffic (3.5x peak), aggressive "
                    "growth (15% monthly), full degradation models, "
                    "frequent random failures, and bi-weekly "
                    "deployments.  Validates long-term operational "
                    "resilience and error budget consumption."
                ),
                duration_days=30,
                time_unit=TimeUnit.FIVE_MINUTES,  # 5-min for accurate short-event tracking
                traffic_patterns=[
                    create_diurnal_weekly(
                        peak=3.5, duration=2592000, weekend_factor=0.5
                    ),
                    create_growth_trend(
                        monthly_rate=0.15, duration=2592000
                    ),
                ],
                scheduled_deploys=tuesday_deploys + thursday_deploys,
                enable_random_failures=True,
                enable_degradation=True,
                enable_maintenance=True,
                maintenance_day_of_week=6,
                maintenance_hour=2,
                random_seed=42,
            )
        )

        # Apply time_unit override if requested
        if time_unit_override is not None:
            for scenario in scenarios:
                scenario.time_unit = time_unit_override

        # Run all scenarios
        results: list[OpsSimulationResult] = []
        for scenario in scenarios:
            result = self.run_ops_scenario(scenario)
            results.append(result)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _time_unit_to_seconds(unit: TimeUnit) -> int:
        """Convert a TimeUnit enum value to seconds."""
        if unit == TimeUnit.MINUTE:
            return 60
        elif unit == TimeUnit.FIVE_MINUTES:
            return 300
        elif unit == TimeUnit.HOUR:
            return 3600
        return 300  # default fallback

    @staticmethod
    def _composite_traffic(t: int, scenario: OpsScenario) -> float:
        """Compute the composite traffic multiplier at time *t*.

        When multiple traffic patterns are configured, their multipliers
        are combined multiplicatively.  For example, a diurnal pattern
        producing 2.0x and a growth trend producing 1.05x yields 2.1x.

        Parameters
        ----------
        t:
            Current time in seconds from simulation start.
        scenario:
            The scenario containing traffic patterns.

        Returns
        -------
        float
            Combined traffic multiplier (>= 0.1).
        """
        if not scenario.traffic_patterns:
            return 1.0

        composite = 1.0
        for pattern in scenario.traffic_patterns:
            mult = pattern.multiplier_at(t)
            composite *= mult

        # Floor at 0.1 to allow below-baseline traffic while preventing near-zero values
        return max(0.1, composite)

    def _schedule_events(
        self,
        scenario: OpsScenario,
        total_seconds: int,
        rng: random.Random,
    ) -> list[OpsEvent]:
        """Pre-schedule all operational events for the simulation.

        Generates:
        - Deployment events from ``scheduled_deploys``
        - Random failures based on component MTBF
        - Maintenance windows

        Parameters
        ----------
        scenario:
            The scenario configuration.
        total_seconds:
            Total simulation duration in seconds.
        rng:
            Seeded random number generator.

        Returns
        -------
        list[OpsEvent]
            All scheduled events sorted by time.
        """
        events: list[OpsEvent] = []

        # --- Scheduled deployments ---
        # First pass: resolve downtime for each deploy config
        resolved_deploys: list[dict[str, Any]] = []
        for deploy_cfg in scenario.scheduled_deploys:
            comp_id = deploy_cfg.get("component_id", "")
            day_of_week = deploy_cfg.get("day_of_week", 1)  # 0=Mon
            hour = deploy_cfg.get("hour", 14)
            downtime = deploy_cfg.get("downtime_seconds", 30)

            comp = self.graph.get_component(comp_id)
            if comp is not None:
                # Use the component's operational profile downtime if
                # available and non-zero
                profile_downtime = (
                    comp.operational_profile.deploy_downtime_seconds
                )
                if profile_downtime > 0:
                    downtime = int(profile_downtime)

            resolved_deploys.append(
                {
                    "component_id": comp_id,
                    "day_of_week": day_of_week,
                    "hour": hour,
                    "downtime": downtime,
                }
            )

        # Second pass: group by (day, hour) and stagger for rolling deploy
        for day in range(scenario.duration_days):
            # Collect deploy configs that fire on this day
            batch: list[dict[str, Any]] = []
            for rd in resolved_deploys:
                if day % 7 == rd["day_of_week"]:
                    batch.append(rd)

            if not batch:
                continue

            # Sort for deterministic ordering
            batch.sort(key=lambda d: d["component_id"])
            total_in_batch = len(batch)

            for idx, rd in enumerate(batch):
                comp_id = rd["component_id"]
                hour = rd["hour"]
                downtime = rd["downtime"]
                stagger_offset = idx * (downtime + 30)
                deploy_time = (
                    day * 86400 + hour * 3600 + stagger_offset
                )
                if deploy_time < total_seconds:
                    events.append(
                        OpsEvent(
                            time_seconds=deploy_time,
                            event_type=OpsEventType.DEPLOY,
                            target_component_id=comp_id,
                            duration_seconds=downtime,
                            description=(
                                f"Scheduled deploy to {comp_id} "
                                f"(day {day}, {hour}:00, "
                                f"{downtime}s downtime) "
                                f"(rolling {idx + 1}/{total_in_batch})"
                            ),
                        )
                    )

        # --- Random failures based on MTBF ---
        if scenario.enable_random_failures:
            for comp_id, comp in self.graph.components.items():
                comp_type = comp.type.value

                # Use local variables instead of mutating the component's
                # operational profile so the input graph stays unchanged.
                mtbf_hours = comp.operational_profile.mtbf_hours
                if mtbf_hours <= 0:
                    mtbf_hours = _DEFAULT_MTBF_HOURS.get(comp_type, 2160.0)

                mttr_minutes = comp.operational_profile.mttr_minutes
                if mttr_minutes <= 0:
                    mttr_minutes = _DEFAULT_MTTR_MINUTES.get(comp_type, 30.0)

                # Add mean acknowledge time from the operational team config.
                # Total recovery = acknowledge time + repair time.
                ack_minutes = comp.team.mean_acknowledge_time_minutes
                total_recovery_minutes = mttr_minutes + ack_minutes

                mtbf_seconds = mtbf_hours * 3600.0
                mttr_seconds = total_recovery_minutes * 60.0

                # Generate failures using exponential distribution
                t_cursor = rng.expovariate(1.0 / mtbf_seconds)
                while t_cursor < total_seconds:
                    events.append(
                        OpsEvent(
                            time_seconds=int(t_cursor),
                            event_type=OpsEventType.RANDOM_FAILURE,
                            target_component_id=comp_id,
                            duration_seconds=int(mttr_seconds),
                            description=(
                                f"Random failure of {comp_id} at "
                                f"t={int(t_cursor)}s "
                                f"(MTBF={mtbf_hours}h, "
                                f"MTTR={mttr_minutes}min, "
                                f"ack={ack_minutes}min)"
                            ),
                        )
                    )
                    # Next failure: skip MTTR + exponential wait
                    t_cursor += mttr_seconds + rng.expovariate(
                        1.0 / mtbf_seconds
                    )

        # --- Correlated failures (AZ / zone outage simulation) ---
        # Once per 30-day window, simulate an AZ event that simultaneously
        # affects ~33% of components of the same type for a short duration.
        if scenario.enable_random_failures and scenario.duration_days >= 14:
            az_time = int(total_seconds * 0.6)  # occurs at ~60% of sim
            az_duration = 120  # 2-minute AZ blip
            comp_by_type: dict[str, list[str]] = {}
            for cid, comp in self.graph.components.items():
                comp_by_type.setdefault(comp.type.value, []).append(cid)

            for ctype, cids in comp_by_type.items():
                if len(cids) < 2:
                    continue
                # Affect ~33% of components in this type (at least 1)
                affected_count = max(1, len(cids) // 3)
                affected = rng.sample(cids, min(affected_count, len(cids)))
                for cid in affected:
                    events.append(
                        OpsEvent(
                            time_seconds=az_time,
                            event_type=OpsEventType.RANDOM_FAILURE,
                            target_component_id=cid,
                            duration_seconds=az_duration,
                            description=(
                                f"AZ correlated failure: {cid} "
                                f"(zone outage affecting {len(affected)}/{len(cids)} "
                                f"{ctype} components, {az_duration}s)"
                            ),
                        )
                    )

        # --- Maintenance windows (tier-aware staged) ---
        if scenario.enable_maintenance:
            for day in range(scenario.duration_days):
                if day % 7 == scenario.maintenance_day_of_week:
                    maint_time = (
                        day * 86400 + scenario.maintenance_hour * 3600
                    )

                    if maint_time < total_seconds:
                        # Group components by type for tier-aware staging
                        maint_factor = scenario.maintenance_duration_factor
                        tiers: dict[str, list[tuple[str, int]]] = {}
                        for comp_id, comp in self.graph.components.items():
                            comp_type = comp.type.value
                            base_duration = _DEFAULT_MAINT_SECONDS.get(
                                comp_type, 3600
                            )
                            maint_duration = int(base_duration * maint_factor)

                            tier_key = comp.type.value
                            tiers.setdefault(tier_key, []).append(
                                (comp_id, maint_duration)
                            )

                        # For each tier, create groups that maintain
                        # at most MAX_MAINT_FRACTION of the tier at once
                        global_offset = 0
                        global_group_idx = 0
                        # Sort tier keys for deterministic ordering
                        for tier_key in sorted(tiers.keys()):
                            tier_comps = tiers[tier_key]
                            tier_comps.sort(key=lambda x: x[0])
                            tier_count = len(tier_comps)
                            group_size = max(
                                1,
                                min(
                                    int(
                                        math.ceil(
                                            tier_count
                                            * MAX_MAINT_FRACTION
                                        )
                                    ),
                                    MAX_MAINT_GROUP_CAP,
                                ),
                            )

                            tier_groups = [
                                tier_comps[i : i + group_size]
                                for i in range(
                                    0, tier_count, group_size
                                )
                            ]

                            for tg_idx, tg in enumerate(tier_groups):
                                max_dur = max(d for _, d in tg)
                                for comp_id, dur in tg:
                                    maint_start = (
                                        maint_time + global_offset
                                    )
                                    if maint_start < total_seconds:
                                        global_group_idx += 1
                                        events.append(
                                            OpsEvent(
                                                time_seconds=maint_start,
                                                event_type=(
                                                    OpsEventType
                                                    .MAINTENANCE
                                                ),
                                                target_component_id=(
                                                    comp_id
                                                ),
                                                duration_seconds=dur,
                                                description=(
                                                    f"Maintenance "
                                                    f"{comp_id} "
                                                    f"(day {day}, "
                                                    f"tier={tier_key},"
                                                    f" {dur}s) "
                                                    f"(group "
                                                    f"{tg_idx + 1}/"
                                                    f"{len(tier_groups)}"
                                                    f")"
                                                ),
                                            )
                                        )
                                global_offset += max_dur

        events.sort(key=lambda e: e.time_seconds)
        return events

    @staticmethod
    def _ops_utilization(comp: Component) -> float:
        """Compute a representative utilization for ops simulation.

        Uses ``max()`` of all resource metrics, matching the
        ``Component.utilization()`` method — the bottleneck resource
        determines component health (limiting-factor principle).
        """
        factors: list[float] = []
        if comp.metrics.cpu_percent > 0:
            factors.append(comp.metrics.cpu_percent)
        if comp.metrics.memory_percent > 0:
            factors.append(comp.metrics.memory_percent)
        if comp.metrics.disk_percent > 0:
            factors.append(comp.metrics.disk_percent)
        if (
            comp.capacity.max_connections > 0
            and comp.metrics.network_connections > 0
        ):
            conn_pct = (
                comp.metrics.network_connections
                / comp.capacity.max_connections
                * 100.0
            )
            factors.append(conn_pct)
        return max(factors) if factors else 0.0

    def _init_ops_states(self, scenario: OpsScenario) -> dict[str, _OpsComponentState]:
        """Create initial mutable state for every component."""
        # Use a per-scenario RNG (+1 to differentiate from the event RNG)
        jitter_rng = random.Random(scenario.random_seed + 1)
        states: dict[str, _OpsComponentState] = {}
        for comp_id, comp in self.graph.components.items():
            base_util = self._ops_utilization(comp)
            # Assign jitter factor (0.7-1.3) per component to prevent
            # thundering herd when multiple instances share the same
            # degradation rate — they'll hit thresholds at different times.
            jitter = 0.7 + jitter_rng.random() * 0.6
            states[comp_id] = _OpsComponentState(
                component_id=comp_id,
                base_utilization=base_util,
                current_utilization=base_util,
                current_health=comp.health,
                current_replicas=comp.replicas,
                base_replicas=comp.replicas,
                degradation_jitter=jitter,
            )
        return states

    def _apply_degradation(
        self,
        ops_states: dict[str, _OpsComponentState],
        t: int,
        step_seconds: int,
        scenario: OpsScenario,
    ) -> list[OpsEvent]:
        """Apply gradual degradation models to all components.

        Updates the degradation accumulators in ``ops_states`` based on
        each component's ``DegradationConfig``.  When a threshold is
        breached (e.g. leaked memory > max memory), generates an
        operational event (OOM, disk full, or connection pool
        exhaustion).

        Parameters
        ----------
        ops_states:
            Current mutable component states.
        t:
            Current simulation time in seconds.
        step_seconds:
            Duration of the current time step.
        scenario:
            Scenario configuration (checked for
            ``enable_degradation``).

        Returns
        -------
        list[OpsEvent]
            Any new degradation-triggered events.
        """
        events: list[OpsEvent] = []

        if not scenario.enable_degradation:
            return events

        step_hours = step_seconds / 3600.0

        for comp_id, state in ops_states.items():
            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue

            # Skip components that are already DOWN
            if state.current_health == HealthStatus.DOWN:
                continue

            degradation = comp.operational_profile.degradation

            # If all degradation rates are zero, apply type-based defaults
            if (
                degradation.memory_leak_mb_per_hour == 0.0
                and degradation.disk_fill_gb_per_hour == 0.0
                and degradation.connection_leak_per_hour == 0.0
            ):
                type_defaults = _DEFAULT_DEGRADATION.get(
                    comp.type.value, {}
                )
                if type_defaults:
                    eff_mem = type_defaults.get(
                        "memory_leak_mb_per_hour", 0.0
                    )
                    eff_disk = type_defaults.get(
                        "disk_fill_gb_per_hour", 0.0
                    )
                    eff_conn = type_defaults.get(
                        "connection_leak_per_hour", 0.0
                    )
                else:
                    eff_mem = 0.0
                    eff_disk = 0.0
                    eff_conn = 0.0
            else:
                eff_mem = degradation.memory_leak_mb_per_hour
                eff_disk = degradation.disk_fill_gb_per_hour
                eff_conn = degradation.connection_leak_per_hour

            # Apply per-component jitter to prevent thundering herd
            jitter = state.degradation_jitter
            jeff_mem = eff_mem * jitter
            jeff_disk = eff_disk * jitter
            jeff_conn = eff_conn * jitter

            # Memory leak
            if jeff_mem > 0:
                state.leaked_memory_mb += (
                    jeff_mem * step_hours
                )
                max_mem = comp.capacity.max_memory_mb
                if max_mem > 0 and state.leaked_memory_mb > 0:
                    mem_ratio = state.leaked_memory_mb / max_mem
                    if mem_ratio >= 1.0:
                        # Hard failure — OOM
                        events.append(
                            OpsEvent(
                                time_seconds=t,
                                event_type=OpsEventType.MEMORY_LEAK_OOM,
                                target_component_id=comp_id,
                                duration_seconds=int(
                                    comp.operational_profile.mttr_minutes
                                    * 60
                                ),
                                description=(
                                    f"OOM: {comp_id} leaked "
                                    f"{state.leaked_memory_mb:.0f}MB "
                                    f"(max {max_mem:.0f}MB)"
                                ),
                            )
                        )
                        state.leaked_memory_mb = 0.0
                    elif mem_ratio >= GRACEFUL_RESTART_THRESHOLD:
                        # Proactive graceful restart
                        events.append(
                            OpsEvent(
                                time_seconds=t,
                                event_type=OpsEventType.MAINTENANCE,
                                target_component_id=comp_id,
                                duration_seconds=GRACEFUL_RESTART_DOWNTIME,
                                description=(
                                    f"Graceful restart: {comp_id} "
                                    f"memory {mem_ratio:.0%} "
                                    f"(threshold "
                                    f"{GRACEFUL_RESTART_THRESHOLD:.0%})"
                                ),
                            )
                        )
                        state.leaked_memory_mb = 0.0

            # Disk fill
            if jeff_disk > 0:
                state.filled_disk_gb += (
                    jeff_disk * step_hours
                )
                max_disk = comp.capacity.max_disk_gb
                if max_disk > 0 and state.filled_disk_gb > 0:
                    disk_ratio = state.filled_disk_gb / max_disk
                    if disk_ratio >= 1.0:
                        # Hard failure — disk full
                        events.append(
                            OpsEvent(
                                time_seconds=t,
                                event_type=OpsEventType.DISK_FULL,
                                target_component_id=comp_id,
                                duration_seconds=int(
                                    comp.operational_profile
                                    .mttr_minutes * 60
                                ),
                                description=(
                                    f"Disk full: {comp_id} "
                                    f"{state.filled_disk_gb:.1f}GB "
                                    f"(max {max_disk:.0f}GB)"
                                ),
                            )
                        )
                        state.filled_disk_gb = 0.0
                    elif disk_ratio >= GRACEFUL_RESTART_THRESHOLD:
                        # Proactive log rotation / cleanup
                        events.append(
                            OpsEvent(
                                time_seconds=t,
                                event_type=OpsEventType.MAINTENANCE,
                                target_component_id=comp_id,
                                duration_seconds=GRACEFUL_RESTART_DOWNTIME,
                                description=(
                                    f"Disk cleanup: {comp_id} "
                                    f"disk {disk_ratio:.0%} "
                                    f"(threshold "
                                    f"{GRACEFUL_RESTART_THRESHOLD:.0%})"
                                ),
                            )
                        )
                        state.filled_disk_gb = 0.0

            # Connection leak
            if jeff_conn > 0:
                state.leaked_connections += (
                    jeff_conn * step_hours
                )
                max_conn = comp.capacity.connection_pool_size
                if max_conn > 0 and state.leaked_connections > 0:
                    conn_ratio = state.leaked_connections / max_conn
                    if conn_ratio >= 1.0:
                        # Hard failure — pool exhaustion
                        events.append(
                            OpsEvent(
                                time_seconds=t,
                                event_type=(
                                    OpsEventType.CONN_POOL_EXHAUSTION
                                ),
                                target_component_id=comp_id,
                                duration_seconds=int(
                                    comp.operational_profile.mttr_minutes
                                    * 60
                                ),
                                description=(
                                    f"Connection pool exhausted: "
                                    f"{comp_id} leaked "
                                    f"{state.leaked_connections:.0f} "
                                    f"connections (pool "
                                    f"{max_conn})"
                                ),
                            )
                        )
                        state.leaked_connections = 0.0
                    elif conn_ratio >= GRACEFUL_RESTART_THRESHOLD:
                        # Proactive connection drain + restart
                        events.append(
                            OpsEvent(
                                time_seconds=t,
                                event_type=OpsEventType.MAINTENANCE,
                                target_component_id=comp_id,
                                duration_seconds=GRACEFUL_RESTART_DOWNTIME,
                                description=(
                                    f"Graceful restart: {comp_id} "
                                    f"connections {conn_ratio:.0%} "
                                    f"(threshold "
                                    f"{GRACEFUL_RESTART_THRESHOLD:.0%})"
                                ),
                            )
                        )
                        state.leaked_connections = 0.0

        return events

    @staticmethod
    def _get_active_faults(
        events: list[OpsEvent], t: int
    ) -> list[Fault]:
        """Determine which faults are active at time *t*.

        An event is active if ``t`` falls within
        ``[event.time_seconds,
         event.time_seconds + event.duration_seconds)``.

        Parameters
        ----------
        events:
            All scheduled and generated events.
        t:
            Current simulation time in seconds.

        Returns
        -------
        list[Fault]
            Active faults converted to the Fault model.
        """
        faults: list[Fault] = []
        for event in events:
            start = event.time_seconds
            end = start + event.duration_seconds
            if start <= t < end:
                # Map event type to fault type
                fault_type_map = {
                    OpsEventType.DEPLOY: FaultType.COMPONENT_DOWN,
                    OpsEventType.MAINTENANCE: FaultType.COMPONENT_DOWN,
                    OpsEventType.CERT_RENEWAL: FaultType.COMPONENT_DOWN,
                    OpsEventType.RANDOM_FAILURE: FaultType.COMPONENT_DOWN,
                    OpsEventType.MEMORY_LEAK_OOM: (
                        FaultType.MEMORY_EXHAUSTION
                    ),
                    OpsEventType.DISK_FULL: FaultType.DISK_FULL,
                    OpsEventType.CONN_POOL_EXHAUSTION: (
                        FaultType.CONNECTION_POOL_EXHAUSTION
                    ),
                }
                mapped_type = fault_type_map.get(
                    event.event_type, FaultType.COMPONENT_DOWN
                )
                faults.append(
                    Fault(
                        target_component_id=event.target_component_id,
                        fault_type=mapped_type,
                        duration_seconds=event.duration_seconds,
                    )
                )

        return faults

    @staticmethod
    def _build_summary(result: OpsSimulationResult) -> str:
        """Build a human-readable summary of the simulation results."""
        lines = [
            f"Scenario: {result.scenario.name}",
            f"Duration: {result.scenario.duration_days} days",
            f"Total events: {len(result.events)}",
            f"  Deployments: {result.total_deploys}",
            f"  Failures: {result.total_failures}",
            f"  Degradation events: {result.total_degradation_events}",
            (
                f"Weighted downtime: {result.total_downtime_seconds:.1f}s "
                f"({result.total_downtime_seconds / 60:.1f} min)"
            ),
            (
                f"Component downtime: {result.total_component_down_seconds:.1f}s "
                f"({result.total_component_down_seconds / 60:.1f} min)"
            ),
            f"Peak utilization: {result.peak_utilization}%",
            f"Min availability: {result.min_availability}%",
        ]

        if result.error_budget_statuses:
            lines.append("Error budgets:")
            for ebs in result.error_budget_statuses:
                status = (
                    "EXHAUSTED" if ebs.is_budget_exhausted else "OK"
                )
                lines.append(
                    f"  {ebs.component_id}/{ebs.slo.metric}: "
                    f"{ebs.budget_remaining_percent:.1f}% remaining "
                    f"(burn 1h={ebs.burn_rate_1h:.2f}x, "
                    f"6h={ebs.burn_rate_6h:.2f}x) [{status}]"
                )

        return "\n".join(lines)
