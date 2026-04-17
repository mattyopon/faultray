# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Timeout Budget Analyzer -- end-to-end timeout budget analysis across service chains.

Analyses and optimises timeout configurations across service dependency graphs.
Detects inconsistencies (caller timeout < callee timeout), models cascade
behaviour when timeouts fire in sequence, evaluates retry-timeout interactions,
propagates gRPC-style deadlines, suggests jitter strategies, and computes
optimal timeout values from p99 latency data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from faultray.model.components import (
    CircuitBreakerConfig,
    ComponentType,
    RetryStrategy,
)
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TimeoutKind(str, Enum):
    """Discriminates connection / read / write timeouts."""

    CONNECTION = "connection"
    READ = "read"
    WRITE = "write"


class Severity(str, Enum):
    """Issue severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class JitterStrategy(str, Enum):
    """Timeout jitter / randomisation strategies."""

    NONE = "none"
    UNIFORM = "uniform"
    DECORRELATED = "decorrelated"
    EQUAL = "equal"


class CircuitBreakerState(str, Enum):
    """Circuit breaker state model."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TimeoutConfig:
    """Per-hop timeout configuration (connection / read / write)."""

    component_id: str
    connection_timeout_ms: float = 1000.0
    read_timeout_ms: float = 5000.0
    write_timeout_ms: float = 3000.0

    @property
    def max_timeout_ms(self) -> float:
        return max(
            self.connection_timeout_ms,
            self.read_timeout_ms,
            self.write_timeout_ms,
        )


@dataclass
class TimeoutInconsistency:
    """A detected inconsistency between caller and callee timeout."""

    caller_id: str
    callee_id: str
    caller_timeout_ms: float
    callee_timeout_ms: float
    severity: Severity
    description: str


@dataclass
class RetryTimeoutInteraction:
    """Analysis of the interaction between retry budget and timeout window."""

    component_id: str
    target_id: str
    single_attempt_timeout_ms: float
    max_retries: int
    retry_delay_total_ms: float
    total_retry_budget_ms: float
    caller_timeout_ms: float
    fits_in_caller_window: bool
    description: str


@dataclass
class CascadeStep:
    """One step in a timeout cascade sequence."""

    component_id: str
    timeout_ms: float
    cumulative_ms: float
    is_blocking: bool


@dataclass
class TimeoutCascadeResult:
    """Result of modelling what happens when timeouts fire in sequence."""

    path: list[str]
    steps: list[CascadeStep]
    total_cascade_ms: float
    exceeds_end_to_end: bool
    end_to_end_budget_ms: float


@dataclass
class DeadlinePropagation:
    """gRPC-style deadline propagation along a path."""

    path: list[str]
    initial_deadline_ms: float
    hops: list[DeadlineHop]
    deadline_exceeded: bool
    remaining_at_end_ms: float


@dataclass
class DeadlineHop:
    """A single hop in deadline propagation."""

    component_id: str
    processing_time_ms: float
    remaining_before_ms: float
    remaining_after_ms: float
    exceeded: bool


@dataclass
class JitterRecommendation:
    """Jitter strategy recommendation for a component."""

    component_id: str
    current_strategy: JitterStrategy
    recommended_strategy: JitterStrategy
    base_timeout_ms: float
    jitter_range_ms: float
    reason: str


@dataclass
class CircuitBreakerTimeoutImpact:
    """How timeout patterns affect circuit breaker state transitions."""

    component_id: str
    target_id: str
    timeout_failure_rate: float
    will_trip_breaker: bool
    estimated_trips_per_hour: float
    recovery_timeout_seconds: float
    state_after_timeouts: CircuitBreakerState
    description: str


@dataclass
class OptimalTimeout:
    """Optimal timeout recommendation based on latency percentiles."""

    component_id: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    current_timeout_ms: float
    recommended_timeout_ms: float
    headroom_factor: float
    description: str


@dataclass
class SlowConsumerMismatch:
    """Mismatch between slow consumer and fast producer timeout configs."""

    producer_id: str
    consumer_id: str
    producer_rate_rps: float
    consumer_processing_ms: float
    consumer_timeout_ms: float
    queue_buildup_rate: float
    severity: Severity
    description: str


@dataclass
class PathBudgetVisualization:
    """Per-request-path timeout budget breakdown for visualization."""

    path: list[str]
    total_budget_ms: float
    hop_budgets: list[HopBudget]
    utilization_percent: float


@dataclass
class HopBudget:
    """Timeout budget allocated to a single hop."""

    component_id: str
    allocated_ms: float
    expected_latency_ms: float
    percent_of_total: float


@dataclass
class TimeoutBudgetReport:
    """Comprehensive timeout budget analysis report."""

    generated_at: datetime
    total_paths_analyzed: int
    inconsistencies: list[TimeoutInconsistency]
    retry_interactions: list[RetryTimeoutInteraction]
    cascade_results: list[TimeoutCascadeResult]
    deadline_propagations: list[DeadlinePropagation]
    jitter_recommendations: list[JitterRecommendation]
    circuit_breaker_impacts: list[CircuitBreakerTimeoutImpact]
    optimal_timeouts: list[OptimalTimeout]
    slow_consumer_mismatches: list[SlowConsumerMismatch]
    path_budgets: list[PathBudgetVisualization]
    overall_health: Severity
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class TimeoutBudgetAnalyzer:
    """Analyses and optimises timeout configurations across service chains."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._timeout_configs: dict[str, TimeoutConfig] = {}
        self._latency_data: dict[str, dict[str, float]] = {}
        # processing_time_ms per component for deadline propagation
        self._processing_times: dict[str, float] = {}
        # producer rates for slow-consumer analysis
        self._producer_rates: dict[str, float] = {}

    # -- configuration helpers ------------------------------------------------

    def set_timeout_config(self, config: TimeoutConfig) -> None:
        """Register a per-component timeout configuration."""
        self._timeout_configs[config.component_id] = config

    def get_timeout_config(self, component_id: str) -> TimeoutConfig:
        """Return timeout config for *component_id*, creating a default if absent."""
        if component_id not in self._timeout_configs:
            comp = self._graph.get_component(component_id)
            timeout_s = comp.capacity.timeout_seconds if comp else 30.0
            timeout_ms = timeout_s * 1000.0
            self._timeout_configs[component_id] = TimeoutConfig(
                component_id=component_id,
                connection_timeout_ms=min(timeout_ms, 5000.0),
                read_timeout_ms=timeout_ms,
                write_timeout_ms=timeout_ms * 0.6,
            )
        return self._timeout_configs[component_id]

    def set_latency_percentiles(
        self,
        component_id: str,
        p50_ms: float,
        p95_ms: float,
        p99_ms: float,
    ) -> None:
        """Provide observed latency percentiles for a component."""
        self._latency_data[component_id] = {
            "p50": p50_ms,
            "p95": p95_ms,
            "p99": p99_ms,
        }

    def set_processing_time(self, component_id: str, ms: float) -> None:
        """Set per-hop processing time used for deadline propagation."""
        self._processing_times[component_id] = ms

    def set_producer_rate(self, component_id: str, rps: float) -> None:
        """Set the production rate (requests per second) for a component."""
        self._producer_rates[component_id] = rps

    # -- path helpers ---------------------------------------------------------

    def _all_paths(self) -> list[list[str]]:
        """Return all entry-to-leaf paths in the graph."""
        paths = self._graph.get_critical_paths(max_paths=200)
        if not paths:
            # Fallback: every component as its own single-hop path
            return [[cid] for cid in self._graph.components]
        return paths

    # -- core analyses --------------------------------------------------------

    def detect_inconsistencies(self) -> list[TimeoutInconsistency]:
        """Detect caller timeout < callee timeout problems."""
        issues: list[TimeoutInconsistency] = []
        for dep in self._graph.all_dependency_edges():
            caller_cfg = self.get_timeout_config(dep.source_id)
            callee_cfg = self.get_timeout_config(dep.target_id)

            caller_to = caller_cfg.read_timeout_ms
            callee_to = callee_cfg.read_timeout_ms

            if caller_to < callee_to:
                ratio = callee_to / caller_to if caller_to > 0 else float("inf")
                sev = Severity.CRITICAL if ratio > 2.0 else Severity.WARNING
                issues.append(
                    TimeoutInconsistency(
                        caller_id=dep.source_id,
                        callee_id=dep.target_id,
                        caller_timeout_ms=caller_to,
                        callee_timeout_ms=callee_to,
                        severity=sev,
                        description=(
                            f"Caller {dep.source_id} timeout ({caller_to:.0f}ms) "
                            f"< callee {dep.target_id} timeout ({callee_to:.0f}ms). "
                            f"Caller may time out before callee responds."
                        ),
                    )
                )
        return issues

    def analyze_retry_timeout_interactions(self) -> list[RetryTimeoutInteraction]:
        """Check whether retry budget * timeout fits within caller's window."""
        results: list[RetryTimeoutInteraction] = []
        for dep in self._graph.all_dependency_edges():
            rs: RetryStrategy = dep.retry_strategy
            if not rs.enabled:
                continue

            caller_cfg = self.get_timeout_config(dep.source_id)
            callee_cfg = self.get_timeout_config(dep.target_id)

            single_timeout = callee_cfg.read_timeout_ms

            # Compute total retry delay (sum of exponential back-off delays)
            total_delay = 0.0
            delay = rs.initial_delay_ms
            for _ in range(rs.max_retries):
                total_delay += delay
                delay = min(delay * rs.multiplier, rs.max_delay_ms)

            total_budget = single_timeout * (rs.max_retries + 1) + total_delay
            caller_window = caller_cfg.read_timeout_ms
            fits = total_budget <= caller_window

            results.append(
                RetryTimeoutInteraction(
                    component_id=dep.source_id,
                    target_id=dep.target_id,
                    single_attempt_timeout_ms=single_timeout,
                    max_retries=rs.max_retries,
                    retry_delay_total_ms=round(total_delay, 2),
                    total_retry_budget_ms=round(total_budget, 2),
                    caller_timeout_ms=caller_window,
                    fits_in_caller_window=fits,
                    description=(
                        f"Retry budget {total_budget:.0f}ms "
                        f"{'fits' if fits else 'EXCEEDS'} "
                        f"caller window {caller_window:.0f}ms"
                    ),
                )
            )
        return results

    def model_timeout_cascade(
        self,
        path: list[str],
        end_to_end_budget_ms: float = 0.0,
    ) -> TimeoutCascadeResult:
        """Model what happens when timeouts fire in sequence along *path*."""
        steps: list[CascadeStep] = []
        cumulative = 0.0
        for cid in path:
            cfg = self.get_timeout_config(cid)
            timeout = cfg.read_timeout_ms
            cumulative += timeout

            dep_edges = self._graph.all_dependency_edges()
            is_blocking = any(
                d.source_id == cid and d.dependency_type == "requires"
                for d in dep_edges
            )

            steps.append(
                CascadeStep(
                    component_id=cid,
                    timeout_ms=timeout,
                    cumulative_ms=round(cumulative, 2),
                    is_blocking=is_blocking,
                )
            )

        budget = end_to_end_budget_ms if end_to_end_budget_ms > 0 else cumulative
        return TimeoutCascadeResult(
            path=list(path),
            steps=steps,
            total_cascade_ms=round(cumulative, 2),
            exceeds_end_to_end=cumulative > end_to_end_budget_ms
            if end_to_end_budget_ms > 0
            else False,
            end_to_end_budget_ms=budget,
        )

    def propagate_deadline(
        self,
        path: list[str],
        initial_deadline_ms: float,
    ) -> DeadlinePropagation:
        """Propagate a gRPC-style deadline context along *path*."""
        remaining = initial_deadline_ms
        hops: list[DeadlineHop] = []
        exceeded = False

        for cid in path:
            proc = self._processing_times.get(cid, 0.0)
            before = remaining
            remaining -= proc
            hop_exceeded = remaining < 0
            if hop_exceeded:
                exceeded = True
            hops.append(
                DeadlineHop(
                    component_id=cid,
                    processing_time_ms=proc,
                    remaining_before_ms=round(before, 2),
                    remaining_after_ms=round(remaining, 2),
                    exceeded=hop_exceeded,
                )
            )

        return DeadlinePropagation(
            path=list(path),
            initial_deadline_ms=initial_deadline_ms,
            hops=hops,
            deadline_exceeded=exceeded,
            remaining_at_end_ms=round(remaining, 2),
        )

    def recommend_jitter(self) -> list[JitterRecommendation]:
        """Suggest jitter / randomisation strategies per component."""
        recs: list[JitterRecommendation] = []
        for cid, comp in self._graph.components.items():
            cfg = self.get_timeout_config(cid)
            base = cfg.read_timeout_ms

            # Determine current strategy from retry config on edges
            current = JitterStrategy.NONE
            for dep in self._graph.all_dependency_edges():
                if dep.source_id == cid and dep.retry_strategy.enabled:
                    current = (
                        JitterStrategy.UNIFORM
                        if dep.retry_strategy.jitter
                        else JitterStrategy.NONE
                    )
                    break

            # Recommend decorrelated jitter for databases / high-fan-out
            dependents = self._graph.get_dependents(cid)
            if comp.type in (ComponentType.DATABASE, ComponentType.CACHE):
                recommended = JitterStrategy.DECORRELATED
                reason = (
                    f"{comp.type.value} components benefit from decorrelated jitter "
                    "to avoid thundering herd on reconnect."
                )
            elif len(dependents) > 3:
                recommended = JitterStrategy.DECORRELATED
                reason = (
                    f"High fan-in ({len(dependents)} dependents) makes "
                    "decorrelated jitter advisable."
                )
            elif current == JitterStrategy.NONE:
                recommended = JitterStrategy.UNIFORM
                reason = "Adding uniform jitter prevents synchronised retries."
            else:
                recommended = current
                reason = "Current jitter strategy is adequate."

            jitter_range = base * 0.2  # 20% of base timeout
            recs.append(
                JitterRecommendation(
                    component_id=cid,
                    current_strategy=current,
                    recommended_strategy=recommended,
                    base_timeout_ms=base,
                    jitter_range_ms=round(jitter_range, 2),
                    reason=reason,
                )
            )
        return recs

    def analyze_circuit_breaker_impact(self) -> list[CircuitBreakerTimeoutImpact]:
        """Evaluate how timeouts affect circuit breaker state transitions."""
        results: list[CircuitBreakerTimeoutImpact] = []
        for dep in self._graph.all_dependency_edges():
            cb: CircuitBreakerConfig = dep.circuit_breaker
            if not cb.enabled:
                continue

            callee_cfg = self.get_timeout_config(dep.target_id)
            callee_timeout = callee_cfg.read_timeout_ms

            # Estimate timeout-induced failure rate from latency data
            latency = self._latency_data.get(dep.target_id)
            if latency:
                p99 = latency["p99"]
                failure_rate = min(1.0, max(0.0, (p99 - callee_timeout) / callee_timeout)) if callee_timeout > 0 else 0.0
                # Rough heuristic: ~1% of requests beyond p99
                failure_rate = max(failure_rate, 0.01 if p99 > callee_timeout * 0.8 else 0.0)
            else:
                failure_rate = 0.05  # default assumption

            will_trip = failure_rate > 0 and (
                failure_rate * 100 >= cb.failure_threshold
            )

            # Estimate trips per hour (assuming constant request rate)
            comp = self._graph.get_component(dep.source_id)
            rps = comp.capacity.max_rps if comp else 100
            failures_per_sec = failure_rate * rps
            # Time to accumulate failure_threshold failures
            if failures_per_sec > 0:
                seconds_to_trip = cb.failure_threshold / failures_per_sec
                cycles_per_hour = 3600 / (seconds_to_trip + cb.recovery_timeout_seconds)
            else:
                cycles_per_hour = 0.0

            if will_trip:
                state = CircuitBreakerState.OPEN
            elif failure_rate > 0:
                state = CircuitBreakerState.HALF_OPEN
            else:
                state = CircuitBreakerState.CLOSED

            results.append(
                CircuitBreakerTimeoutImpact(
                    component_id=dep.source_id,
                    target_id=dep.target_id,
                    timeout_failure_rate=round(failure_rate, 4),
                    will_trip_breaker=will_trip,
                    estimated_trips_per_hour=round(cycles_per_hour, 2),
                    recovery_timeout_seconds=cb.recovery_timeout_seconds,
                    state_after_timeouts=state,
                    description=(
                        f"Timeout failure rate {failure_rate:.2%} on "
                        f"{dep.source_id}->{dep.target_id}. "
                        f"Breaker {'WILL' if will_trip else 'will NOT'} trip."
                    ),
                )
            )
        return results

    def compute_optimal_timeouts(
        self,
        headroom_factor: float = 1.5,
    ) -> list[OptimalTimeout]:
        """Compute optimal timeout values from p99 latency data."""
        results: list[OptimalTimeout] = []
        for cid, data in self._latency_data.items():
            cfg = self.get_timeout_config(cid)
            current = cfg.read_timeout_ms
            p99 = data["p99"]
            recommended = p99 * headroom_factor

            results.append(
                OptimalTimeout(
                    component_id=cid,
                    p50_ms=data["p50"],
                    p95_ms=data["p95"],
                    p99_ms=p99,
                    current_timeout_ms=current,
                    recommended_timeout_ms=round(recommended, 2),
                    headroom_factor=headroom_factor,
                    description=(
                        f"p99={p99:.0f}ms => recommended timeout "
                        f"{recommended:.0f}ms (current {current:.0f}ms)"
                    ),
                )
            )
        return results

    def detect_slow_consumer_mismatches(self) -> list[SlowConsumerMismatch]:
        """Detect slow-consumer vs fast-producer timeout mismatches."""
        results: list[SlowConsumerMismatch] = []
        for dep in self._graph.all_dependency_edges():
            if dep.dependency_type == "async":
                producer_rate = self._producer_rates.get(dep.source_id, 0.0)
                if producer_rate <= 0:
                    continue

                consumer_cfg = self.get_timeout_config(dep.target_id)
                consumer_processing = self._processing_times.get(
                    dep.target_id, consumer_cfg.read_timeout_ms
                )
                consumer_timeout = consumer_cfg.read_timeout_ms

                # Max consumer throughput
                consumer_rps = 1000.0 / consumer_processing if consumer_processing > 0 else float("inf")
                buildup = max(0.0, producer_rate - consumer_rps)

                if buildup > 0:
                    sev = Severity.CRITICAL if buildup > producer_rate * 0.5 else Severity.WARNING
                    results.append(
                        SlowConsumerMismatch(
                            producer_id=dep.source_id,
                            consumer_id=dep.target_id,
                            producer_rate_rps=producer_rate,
                            consumer_processing_ms=consumer_processing,
                            consumer_timeout_ms=consumer_timeout,
                            queue_buildup_rate=round(buildup, 2),
                            severity=sev,
                            description=(
                                f"Producer {dep.source_id} at {producer_rate:.0f} rps, "
                                f"consumer {dep.target_id} processes at "
                                f"{consumer_rps:.1f} rps. Queue builds at "
                                f"{buildup:.1f} msg/s."
                            ),
                        )
                    )
        return results

    def visualize_path_budgets(
        self,
        path: list[str] | None = None,
    ) -> list[PathBudgetVisualization]:
        """Generate per-request-path timeout budget breakdowns."""
        paths = [path] if path else self._all_paths()
        results: list[PathBudgetVisualization] = []

        for p in paths:
            if not p:
                continue
            hop_budgets: list[HopBudget] = []
            total = 0.0

            for cid in p:
                cfg = self.get_timeout_config(cid)
                allocated = cfg.read_timeout_ms
                expected = 0.0
                latency = self._latency_data.get(cid)
                if latency:
                    expected = latency["p50"]
                total += allocated
                hop_budgets.append(
                    HopBudget(
                        component_id=cid,
                        allocated_ms=allocated,
                        expected_latency_ms=expected,
                        percent_of_total=0.0,  # filled below
                    )
                )

            # Fill percentages
            for hb in hop_budgets:
                hb.percent_of_total = round(
                    (hb.allocated_ms / total * 100) if total > 0 else 0.0, 1
                )

            used = sum(hb.expected_latency_ms for hb in hop_budgets)
            utilization = (used / total * 100) if total > 0 else 0.0

            results.append(
                PathBudgetVisualization(
                    path=list(p),
                    total_budget_ms=round(total, 2),
                    hop_budgets=hop_budgets,
                    utilization_percent=round(utilization, 1),
                )
            )
        return results

    def analyze_timeout_kinds(
        self, component_id: str
    ) -> dict[TimeoutKind, float]:
        """Return connection / read / write timeout breakdown for a component."""
        cfg = self.get_timeout_config(component_id)
        return {
            TimeoutKind.CONNECTION: cfg.connection_timeout_ms,
            TimeoutKind.READ: cfg.read_timeout_ms,
            TimeoutKind.WRITE: cfg.write_timeout_ms,
        }

    # -- full report ----------------------------------------------------------

    def generate_report(
        self,
        end_to_end_budget_ms: float = 0.0,
        headroom_factor: float = 1.5,
    ) -> TimeoutBudgetReport:
        """Generate a comprehensive timeout budget analysis report."""
        inconsistencies = self.detect_inconsistencies()
        retry_interactions = self.analyze_retry_timeout_interactions()
        jitter_recs = self.recommend_jitter()
        cb_impacts = self.analyze_circuit_breaker_impact()
        optimal = self.compute_optimal_timeouts(headroom_factor)
        slow_consumers = self.detect_slow_consumer_mismatches()

        paths = self._all_paths()
        cascades = [
            self.model_timeout_cascade(p, end_to_end_budget_ms) for p in paths
        ]

        deadline_props: list[DeadlinePropagation] = []
        if end_to_end_budget_ms > 0:
            for p in paths:
                deadline_props.append(
                    self.propagate_deadline(p, end_to_end_budget_ms)
                )

        path_budgets = self.visualize_path_budgets()

        # Determine overall health
        recommendations: list[str] = []

        crit_count = sum(1 for i in inconsistencies if i.severity == Severity.CRITICAL)
        warn_count = sum(1 for i in inconsistencies if i.severity == Severity.WARNING)
        retry_overflow = sum(1 for r in retry_interactions if not r.fits_in_caller_window)
        cascade_overflow = sum(1 for c in cascades if c.exceeds_end_to_end)
        deadline_exceeded = sum(1 for d in deadline_props if d.deadline_exceeded)
        slow_crit = sum(1 for s in slow_consumers if s.severity == Severity.CRITICAL)

        if crit_count > 0:
            recommendations.append(
                f"{crit_count} critical timeout inconsistencies detected -- "
                "caller timeouts are significantly shorter than callee timeouts."
            )
        if warn_count > 0:
            recommendations.append(
                f"{warn_count} timeout inconsistencies at warning level."
            )
        if retry_overflow > 0:
            recommendations.append(
                f"{retry_overflow} retry budgets exceed caller timeout window."
            )
        if cascade_overflow > 0:
            recommendations.append(
                f"{cascade_overflow} paths exceed end-to-end budget when timeouts cascade."
            )
        if deadline_exceeded > 0:
            recommendations.append(
                f"{deadline_exceeded} paths exceed deadline during propagation."
            )
        if slow_crit > 0:
            recommendations.append(
                f"{slow_crit} critical slow-consumer mismatches detected."
            )

        # Optimal timeout recommendations
        for ot in optimal:
            if ot.recommended_timeout_ms < ot.current_timeout_ms * 0.5:
                recommendations.append(
                    f"{ot.component_id}: current timeout ({ot.current_timeout_ms:.0f}ms) "
                    f"is much higher than recommended ({ot.recommended_timeout_ms:.0f}ms)."
                )
            elif ot.recommended_timeout_ms > ot.current_timeout_ms:
                recommendations.append(
                    f"{ot.component_id}: current timeout ({ot.current_timeout_ms:.0f}ms) "
                    f"is lower than recommended ({ot.recommended_timeout_ms:.0f}ms), "
                    "risking spurious timeouts."
                )

        if crit_count > 0 or slow_crit > 0 or retry_overflow > 2:
            overall = Severity.CRITICAL
        elif warn_count > 0 or retry_overflow > 0 or cascade_overflow > 0:
            overall = Severity.WARNING
        else:
            overall = Severity.INFO

        return TimeoutBudgetReport(
            generated_at=datetime.now(timezone.utc),
            total_paths_analyzed=len(paths),
            inconsistencies=inconsistencies,
            retry_interactions=retry_interactions,
            cascade_results=cascades,
            deadline_propagations=deadline_props,
            jitter_recommendations=jitter_recs,
            circuit_breaker_impacts=cb_impacts,
            optimal_timeouts=optimal,
            slow_consumer_mismatches=slow_consumers,
            path_budgets=path_budgets,
            overall_health=overall,
            recommendations=recommendations,
        )
