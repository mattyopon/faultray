# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Canary Deployment & Automated Rollback Simulator.

Simulates canary deployments with progressive traffic shifting and automated
rollback decisions.  Analyzes blast radius, rollback impact, and compares
deployment strategies so operators can choose the safest promotion path.

Answers: "If my canary fails at X% traffic, what happens and how fast can I
roll back?"
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DeploymentStrategy(str, Enum):
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    ROLLING = "rolling"
    RECREATE = "recreate"
    SHADOW = "shadow"
    A_B_TEST = "a_b_test"


class RollbackTrigger(str, Enum):
    ERROR_RATE_SPIKE = "error_rate_spike"
    LATENCY_DEGRADATION = "latency_degradation"
    SATURATION_BREACH = "saturation_breach"
    SLO_VIOLATION = "slo_violation"
    HEALTH_CHECK_FAILURE = "health_check_failure"
    MANUAL = "manual"
    CRASH_LOOP = "crash_loop"
    MEMORY_LEAK = "memory_leak"
    CPU_SPIKE = "cpu_spike"
    CUSTOM_METRIC = "custom_metric"


class CanaryPhase(str, Enum):
    INITIAL_SPLIT = "initial_split"
    OBSERVATION = "observation"
    ANALYSIS = "analysis"
    PROMOTION = "promotion"
    ROLLBACK = "rollback"
    COMPLETED = "completed"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CanaryConfig(BaseModel):
    """Configuration for a canary deployment simulation."""

    strategy: DeploymentStrategy = DeploymentStrategy.CANARY
    initial_percentage: float = 5.0
    step_percentage: float = 10.0
    step_interval_seconds: int = 300
    max_error_rate: float = 1.0
    max_latency_p99_ms: float = 500.0
    min_observation_seconds: int = 60
    auto_rollback: bool = True
    rollback_on: list[RollbackTrigger] = Field(default_factory=list)


class CanaryStepResult(BaseModel):
    """Result of a single canary progression step."""

    step: int
    traffic_percentage: float
    duration_seconds: int
    error_rate: float
    latency_p99_ms: float
    phase: CanaryPhase
    decision: str  # proceed / hold / rollback
    metrics: dict[str, float] = Field(default_factory=dict)


class RollbackAnalysis(BaseModel):
    """Impact analysis of a rollback event."""

    trigger: RollbackTrigger
    detection_time_seconds: float
    rollback_time_seconds: float
    total_impact_seconds: float
    affected_requests_estimate: int
    blast_radius: list[str]
    data_consistency_risk: str  # none / low / medium / high
    recommendations: list[str] = Field(default_factory=list)


class FailedCanaryResult(BaseModel):
    """What happens when a canary fails at a given traffic percentage."""

    failure_percentage: float
    steps_before_failure: int
    detected_trigger: RollbackTrigger
    rollback_analysis: RollbackAnalysis
    total_duration_seconds: float
    steps: list[CanaryStepResult] = Field(default_factory=list)


class BlastRadiusEstimate(BaseModel):
    """Estimated blast radius at a given traffic split percentage."""

    percentage: float
    affected_components: list[str]
    affected_request_ratio: float
    estimated_error_impact: float
    risk_level: str  # low / medium / high / critical
    mitigation_suggestions: list[str] = Field(default_factory=list)


class StrategyComparison(BaseModel):
    """Comparison result for a single deployment strategy."""

    strategy: DeploymentStrategy
    risk_score: float
    rollback_time_seconds: float
    blast_radius_size: int
    recommended: bool
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class RollbackReadinessReport(BaseModel):
    """Pre-deploy rollback readiness assessment."""

    ready: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    score: float = 0.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CanaryRollbackEngine:
    """Stateless engine for canary deployment and rollback simulations."""

    # -- public API ---------------------------------------------------------

    def simulate_canary(
        self,
        graph: InfraGraph,
        component_id: str,
        config: CanaryConfig,
    ) -> list[CanaryStepResult]:
        """Run a full canary simulation, returning one result per step."""
        comp = graph.get_component(component_id)
        if comp is None:
            return []

        steps: list[CanaryStepResult] = []
        pct = config.initial_percentage
        step_num = 0

        # Initial split step
        step_num += 1
        error_rate = self._estimate_error_rate(graph, comp, pct)
        latency = self._estimate_latency(graph, comp, pct)
        decision, phase = self._evaluate_step(config, error_rate, latency, pct)
        steps.append(
            CanaryStepResult(
                step=step_num,
                traffic_percentage=pct,
                duration_seconds=config.min_observation_seconds,
                error_rate=error_rate,
                latency_p99_ms=latency,
                phase=CanaryPhase.INITIAL_SPLIT,
                decision=decision,
                metrics=self._build_metrics(graph, comp, pct),
            )
        )

        if decision == "rollback":
            return steps

        # Progressive steps
        while pct < 100.0:
            pct = min(pct + config.step_percentage, 100.0)
            step_num += 1
            error_rate = self._estimate_error_rate(graph, comp, pct)
            latency = self._estimate_latency(graph, comp, pct)
            decision, phase = self._evaluate_step(config, error_rate, latency, pct)

            if pct >= 100.0 and decision == "proceed":
                phase = CanaryPhase.COMPLETED
                decision = "proceed"

            steps.append(
                CanaryStepResult(
                    step=step_num,
                    traffic_percentage=pct,
                    duration_seconds=config.step_interval_seconds,
                    error_rate=error_rate,
                    latency_p99_ms=latency,
                    phase=phase,
                    decision=decision,
                    metrics=self._build_metrics(graph, comp, pct),
                )
            )

            if decision == "rollback":
                break

        return steps

    def analyze_rollback(
        self,
        graph: InfraGraph,
        component_id: str,
        trigger: RollbackTrigger,
    ) -> RollbackAnalysis:
        """Analyse the impact of rolling back a component."""
        comp = graph.get_component(component_id)
        affected = self._get_blast_radius_ids(graph, component_id)

        detection = self._detection_time(trigger, comp)
        rollback_time = self._rollback_time(comp)
        total_impact = detection + rollback_time

        rps = self._component_rps(comp) if comp else 100
        affected_reqs = int(total_impact * rps)

        consistency_risk = self._data_consistency_risk(graph, component_id)
        recs = self._rollback_recommendations(trigger, comp, affected)

        return RollbackAnalysis(
            trigger=trigger,
            detection_time_seconds=detection,
            rollback_time_seconds=rollback_time,
            total_impact_seconds=total_impact,
            affected_requests_estimate=affected_reqs,
            blast_radius=affected,
            data_consistency_risk=consistency_risk,
            recommendations=recs,
        )

    def recommend_strategy(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> CanaryConfig:
        """Recommend an optimal deployment strategy & config for *component_id*."""
        comp = graph.get_component(component_id)
        if comp is None:
            return CanaryConfig()

        strategy = self._pick_strategy(graph, comp)
        initial_pct = self._pick_initial_pct(graph, comp)
        step_pct = self._pick_step_pct(graph, comp)
        max_err = self._pick_max_error_rate(comp)
        max_lat = self._pick_max_latency(comp)
        triggers = self._pick_rollback_triggers(graph, comp)

        return CanaryConfig(
            strategy=strategy,
            initial_percentage=initial_pct,
            step_percentage=step_pct,
            step_interval_seconds=300,
            max_error_rate=max_err,
            max_latency_p99_ms=max_lat,
            min_observation_seconds=60,
            auto_rollback=True,
            rollback_on=triggers,
        )

    def simulate_failed_canary(
        self,
        graph: InfraGraph,
        component_id: str,
        failure_at_percentage: float,
    ) -> FailedCanaryResult:
        """Simulate what happens when a canary fails at *failure_at_percentage*."""
        comp = graph.get_component(component_id)
        if comp is None:
            return FailedCanaryResult(
                failure_percentage=failure_at_percentage,
                steps_before_failure=0,
                detected_trigger=RollbackTrigger.ERROR_RATE_SPIKE,
                rollback_analysis=self.analyze_rollback(
                    graph, component_id, RollbackTrigger.ERROR_RATE_SPIKE
                ),
                total_duration_seconds=0.0,
            )

        config = CanaryConfig(
            initial_percentage=5.0,
            step_percentage=10.0,
            max_error_rate=1.0,
            max_latency_p99_ms=500.0,
        )

        steps: list[CanaryStepResult] = []
        pct = config.initial_percentage
        step_num = 0
        total_dur = 0.0

        while pct < failure_at_percentage:
            step_num += 1
            error_rate = self._estimate_error_rate(graph, comp, pct)
            latency = self._estimate_latency(graph, comp, pct)
            dur = config.step_interval_seconds
            total_dur += dur
            steps.append(
                CanaryStepResult(
                    step=step_num,
                    traffic_percentage=pct,
                    duration_seconds=dur,
                    error_rate=error_rate,
                    latency_p99_ms=latency,
                    phase=CanaryPhase.OBSERVATION,
                    decision="proceed",
                    metrics=self._build_metrics(graph, comp, pct),
                )
            )
            pct = min(pct + config.step_percentage, 100.0)
            if pct >= failure_at_percentage:
                break

        # Failure step
        step_num += 1
        trigger = self._detect_trigger(comp, failure_at_percentage)
        total_dur += config.step_interval_seconds
        steps.append(
            CanaryStepResult(
                step=step_num,
                traffic_percentage=failure_at_percentage,
                duration_seconds=config.step_interval_seconds,
                error_rate=5.0,
                latency_p99_ms=1200.0,
                phase=CanaryPhase.ROLLBACK,
                decision="rollback",
                metrics=self._build_metrics(graph, comp, failure_at_percentage),
            )
        )

        rollback = self.analyze_rollback(graph, component_id, trigger)
        total_dur += rollback.total_impact_seconds

        return FailedCanaryResult(
            failure_percentage=failure_at_percentage,
            steps_before_failure=step_num - 1,
            detected_trigger=trigger,
            rollback_analysis=rollback,
            total_duration_seconds=total_dur,
            steps=steps,
        )

    def estimate_blast_radius(
        self,
        graph: InfraGraph,
        component_id: str,
        percentage: float,
    ) -> BlastRadiusEstimate:
        """Estimate the blast radius at a given traffic split *percentage*."""
        affected = self._get_blast_radius_ids(graph, component_id)
        ratio = percentage / 100.0
        error_impact = ratio * len(affected) * 0.1
        risk = self._risk_level(percentage, len(affected))
        mitigations = self._mitigation_suggestions(graph, component_id, percentage)

        return BlastRadiusEstimate(
            percentage=percentage,
            affected_components=affected,
            affected_request_ratio=ratio,
            estimated_error_impact=round(error_impact, 4),
            risk_level=risk,
            mitigation_suggestions=mitigations,
        )

    def compare_strategies(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> list[StrategyComparison]:
        """Compare all deployment strategies for *component_id*."""
        comp = graph.get_component(component_id)
        blast_ids = self._get_blast_radius_ids(graph, component_id)
        blast_size = len(blast_ids)

        results: list[StrategyComparison] = []
        best_strategy = self._pick_strategy(graph, comp) if comp else DeploymentStrategy.RECREATE

        for strategy in DeploymentStrategy:
            risk = self._strategy_risk(strategy, comp, blast_size)
            rb_time = self._strategy_rollback_time(strategy, comp)
            pros, cons = self._strategy_pros_cons(strategy)
            results.append(
                StrategyComparison(
                    strategy=strategy,
                    risk_score=risk,
                    rollback_time_seconds=rb_time,
                    blast_radius_size=blast_size,
                    recommended=(strategy == best_strategy),
                    pros=pros,
                    cons=cons,
                )
            )

        return results

    def validate_rollback_readiness(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> RollbackReadinessReport:
        """Pre-deploy check — is the component ready for safe rollback?"""
        comp = graph.get_component(component_id)
        if comp is None:
            return RollbackReadinessReport(
                ready=False,
                checks={},
                warnings=[],
                blockers=["Component not found"],
                score=0.0,
            )

        checks: dict[str, bool] = {}
        warnings: list[str] = []
        blockers: list[str] = []

        # Check health
        checks["healthy"] = comp.health == HealthStatus.HEALTHY
        if not checks["healthy"]:
            blockers.append("Component is not healthy")

        # Check replicas
        checks["multiple_replicas"] = comp.replicas > 1
        if not checks["multiple_replicas"]:
            warnings.append("Single replica — no redundancy during rollback")

        # Check failover
        checks["failover_enabled"] = comp.failover.enabled
        if not checks["failover_enabled"]:
            warnings.append("Failover is not enabled")

        # Check circuit breaker on incoming deps
        dependents = graph.get_dependents(component_id)
        has_cb = False
        for dep_comp in dependents:
            edge = graph.get_dependency_edge(dep_comp.id, component_id)
            if edge and edge.circuit_breaker.enabled:
                has_cb = True
                break
        checks["circuit_breaker_coverage"] = has_cb
        if not has_cb and len(dependents) > 0:
            warnings.append("No circuit breaker on upstream dependencies")

        # Check autoscaling
        checks["autoscaling_enabled"] = comp.autoscaling.enabled
        if not checks["autoscaling_enabled"]:
            warnings.append("Autoscaling is not enabled")

        # Check health check interval
        checks["health_check_configured"] = (
            comp.failover.health_check_interval_seconds > 0
        )

        # Check monitoring (SLO targets defined)
        checks["monitoring_configured"] = len(comp.slo_targets) > 0
        if not checks["monitoring_configured"]:
            warnings.append("No SLO targets defined — monitoring may be insufficient")

        # Check data tier dependencies
        deps = graph.get_dependencies(component_id)
        has_db = any(d.type == ComponentType.DATABASE for d in deps)
        if has_db:
            db_deps = [d for d in deps if d.type == ComponentType.DATABASE]
            db_replicated = all(d.replicas > 1 for d in db_deps)
            checks["database_replicated"] = db_replicated
            if not db_replicated:
                blockers.append("Database dependency has no replication")

        passed = sum(1 for v in checks.values() if v)
        total = len(checks) if checks else 1
        score = round((passed / total) * 100.0, 1)

        ready = len(blockers) == 0 and score >= 50.0

        return RollbackReadinessReport(
            ready=ready,
            checks=checks,
            warnings=warnings,
            blockers=blockers,
            score=score,
        )

    # -- private helpers ----------------------------------------------------

    def _estimate_error_rate(
        self, graph: InfraGraph, comp: Component, pct: float
    ) -> float:
        """Synthetic error rate based on component health & utilisation."""
        base = 0.01
        if comp.health == HealthStatus.DEGRADED:
            base = 0.5
        elif comp.health == HealthStatus.OVERLOADED:
            base = 2.0
        elif comp.health == HealthStatus.DOWN:
            base = 50.0

        util = comp.utilization()
        util_factor = 1.0 + (util / 100.0) * 0.5
        pct_factor = 1.0 + (pct / 100.0) * 0.3
        return round(base * util_factor * pct_factor, 4)

    def _estimate_latency(
        self, graph: InfraGraph, comp: Component, pct: float
    ) -> float:
        """Synthetic p99 latency based on component state."""
        base = 50.0
        if comp.health == HealthStatus.DEGRADED:
            base = 200.0
        elif comp.health == HealthStatus.OVERLOADED:
            base = 800.0
        elif comp.health == HealthStatus.DOWN:
            base = 5000.0

        deps = graph.get_dependencies(comp.id)
        dep_add = sum(
            d.network.rtt_ms for d in deps
        )
        pct_factor = 1.0 + (pct / 100.0) * 0.5
        return round((base + dep_add) * pct_factor, 2)

    def _evaluate_step(
        self,
        config: CanaryConfig,
        error_rate: float,
        latency: float,
        pct: float,
    ) -> tuple[str, CanaryPhase]:
        """Return (decision, phase) for a canary step."""
        if error_rate > config.max_error_rate and config.auto_rollback:
            return "rollback", CanaryPhase.ROLLBACK
        if latency > config.max_latency_p99_ms and config.auto_rollback:
            return "rollback", CanaryPhase.ROLLBACK
        if pct >= 100.0:
            return "proceed", CanaryPhase.PROMOTION
        if error_rate > config.max_error_rate * 0.8:
            return "hold", CanaryPhase.ANALYSIS
        return "proceed", CanaryPhase.OBSERVATION

    def _build_metrics(
        self, graph: InfraGraph, comp: Component, pct: float
    ) -> dict[str, float]:
        return {
            "cpu_percent": comp.metrics.cpu_percent,
            "memory_percent": comp.metrics.memory_percent,
            "traffic_percentage": pct,
            "replicas": float(comp.replicas),
        }

    def _get_blast_radius_ids(
        self, graph: InfraGraph, component_id: str
    ) -> list[str]:
        """Return sorted list of component IDs affected by *component_id* failure."""
        if graph.get_component(component_id) is None:
            return []
        affected = graph.get_all_affected(component_id)
        return sorted(affected - {component_id})

    def _detection_time(
        self, trigger: RollbackTrigger, comp: Component | None
    ) -> float:
        base_times: dict[RollbackTrigger, float] = {
            RollbackTrigger.ERROR_RATE_SPIKE: 10.0,
            RollbackTrigger.LATENCY_DEGRADATION: 15.0,
            RollbackTrigger.SATURATION_BREACH: 20.0,
            RollbackTrigger.SLO_VIOLATION: 30.0,
            RollbackTrigger.HEALTH_CHECK_FAILURE: 5.0,
            RollbackTrigger.MANUAL: 120.0,
            RollbackTrigger.CRASH_LOOP: 8.0,
            RollbackTrigger.MEMORY_LEAK: 60.0,
            RollbackTrigger.CPU_SPIKE: 12.0,
            RollbackTrigger.CUSTOM_METRIC: 25.0,
        }
        return base_times.get(trigger, 30.0)

    def _rollback_time(self, comp: Component | None) -> float:
        if comp is None:
            return 60.0
        base = comp.operational_profile.deploy_downtime_seconds
        if comp.failover.enabled:
            base = min(base, comp.failover.promotion_time_seconds)
        if comp.replicas > 1:
            base *= 0.7
        return round(max(base, 5.0), 2)

    def _component_rps(self, comp: Component) -> int:
        return max(comp.capacity.max_rps, 100)

    def _data_consistency_risk(
        self, graph: InfraGraph, component_id: str
    ) -> str:
        comp = graph.get_component(component_id)
        if comp is None:
            return "none"
        if comp.type == ComponentType.DATABASE:
            return "high"
        deps = graph.get_dependencies(component_id)
        has_db = any(d.type == ComponentType.DATABASE for d in deps)
        if not has_db:
            return "none"
        db_deps = [d for d in deps if d.type == ComponentType.DATABASE]
        if any(d.replicas <= 1 for d in db_deps):
            return "medium"
        return "low"

    def _rollback_recommendations(
        self,
        trigger: RollbackTrigger,
        comp: Component | None,
        affected: list[str],
    ) -> list[str]:
        recs: list[str] = []
        if comp and not comp.failover.enabled:
            recs.append("Enable failover for faster recovery")
        if comp and comp.replicas <= 1:
            recs.append("Increase replica count for redundancy")
        if len(affected) > 3:
            recs.append("Consider circuit breakers to limit blast radius")
        if trigger == RollbackTrigger.MEMORY_LEAK:
            recs.append("Investigate memory leak before re-deploying")
        if trigger == RollbackTrigger.CRASH_LOOP:
            recs.append("Check logs for crash root cause")
        if trigger == RollbackTrigger.LATENCY_DEGRADATION:
            recs.append("Profile latency bottleneck before retry")
        if not recs:
            recs.append("Review deployment logs before re-attempting")
        return recs

    def _pick_strategy(
        self, graph: InfraGraph, comp: Component
    ) -> DeploymentStrategy:
        deps = graph.get_dependencies(comp.id)
        dependents = graph.get_dependents(comp.id)
        has_db = any(d.type == ComponentType.DATABASE for d in deps)

        if comp.type == ComponentType.DATABASE:
            return DeploymentStrategy.BLUE_GREEN
        if comp.replicas >= 3 and not has_db:
            return DeploymentStrategy.ROLLING
        if len(dependents) > 5:
            return DeploymentStrategy.CANARY
        if comp.type == ComponentType.LOAD_BALANCER:
            return DeploymentStrategy.BLUE_GREEN
        if has_db and comp.replicas <= 1:
            return DeploymentStrategy.RECREATE
        return DeploymentStrategy.CANARY

    def _pick_initial_pct(self, graph: InfraGraph, comp: Component) -> float:
        dependents = graph.get_dependents(comp.id)
        if len(dependents) > 5:
            return 1.0
        if comp.replicas >= 3:
            return 10.0
        return 5.0

    def _pick_step_pct(self, graph: InfraGraph, comp: Component) -> float:
        dependents = graph.get_dependents(comp.id)
        if len(dependents) > 5:
            return 5.0
        return 10.0

    def _pick_max_error_rate(self, comp: Component) -> float:
        if comp.type == ComponentType.DATABASE:
            return 0.1
        if comp.type == ComponentType.LOAD_BALANCER:
            return 0.5
        return 1.0

    def _pick_max_latency(self, comp: Component) -> float:
        for slo in comp.slo_targets:
            if slo.metric == "latency_p99":
                return slo.target
        return 500.0

    def _pick_rollback_triggers(
        self, graph: InfraGraph, comp: Component
    ) -> list[RollbackTrigger]:
        triggers = [
            RollbackTrigger.ERROR_RATE_SPIKE,
            RollbackTrigger.LATENCY_DEGRADATION,
        ]
        deps = graph.get_dependencies(comp.id)
        if any(d.type == ComponentType.DATABASE for d in deps):
            triggers.append(RollbackTrigger.SLO_VIOLATION)
        if comp.metrics.memory_percent > 70:
            triggers.append(RollbackTrigger.MEMORY_LEAK)
        if comp.metrics.cpu_percent > 80:
            triggers.append(RollbackTrigger.CPU_SPIKE)
        triggers.append(RollbackTrigger.HEALTH_CHECK_FAILURE)
        return triggers

    def _detect_trigger(
        self, comp: Component, pct: float
    ) -> RollbackTrigger:
        if comp.health == HealthStatus.DOWN:
            return RollbackTrigger.CRASH_LOOP
        if comp.metrics.memory_percent > 80:
            return RollbackTrigger.MEMORY_LEAK
        if comp.metrics.cpu_percent > 80:
            return RollbackTrigger.CPU_SPIKE
        if pct > 50:
            return RollbackTrigger.LATENCY_DEGRADATION
        return RollbackTrigger.ERROR_RATE_SPIKE

    def _risk_level(self, percentage: float, affected_count: int) -> str:
        score = (percentage / 100.0) * 0.6 + (min(affected_count, 10) / 10.0) * 0.4
        if score >= 0.75:
            return "critical"
        if score >= 0.5:
            return "high"
        if score >= 0.25:
            return "medium"
        return "low"

    def _mitigation_suggestions(
        self, graph: InfraGraph, component_id: str, percentage: float
    ) -> list[str]:
        suggestions: list[str] = []
        comp = graph.get_component(component_id)
        if comp is None:
            return ["Verify component exists before deployment"]

        if percentage > 50:
            suggestions.append("Reduce canary percentage to limit blast radius")
        if comp.replicas <= 1:
            suggestions.append("Add replicas for redundancy")
        if not comp.autoscaling.enabled:
            suggestions.append("Enable autoscaling to absorb traffic spikes")

        dependents = graph.get_dependents(component_id)
        for dep in dependents:
            edge = graph.get_dependency_edge(dep.id, component_id)
            if edge and not edge.circuit_breaker.enabled:
                suggestions.append(
                    f"Enable circuit breaker on {dep.id} -> {component_id}"
                )
                break  # one suggestion is enough

        if not suggestions:
            suggestions.append("Current configuration appears adequate")
        return suggestions

    def _strategy_risk(
        self,
        strategy: DeploymentStrategy,
        comp: Component | None,
        blast_size: int,
    ) -> float:
        base: dict[DeploymentStrategy, float] = {
            DeploymentStrategy.CANARY: 20.0,
            DeploymentStrategy.BLUE_GREEN: 15.0,
            DeploymentStrategy.ROLLING: 30.0,
            DeploymentStrategy.RECREATE: 60.0,
            DeploymentStrategy.SHADOW: 10.0,
            DeploymentStrategy.A_B_TEST: 25.0,
        }
        risk = base.get(strategy, 50.0)
        risk += blast_size * 2.0
        if comp and comp.replicas <= 1:
            risk += 10.0
        return min(round(risk, 1), 100.0)

    def _strategy_rollback_time(
        self, strategy: DeploymentStrategy, comp: Component | None
    ) -> float:
        base_times: dict[DeploymentStrategy, float] = {
            DeploymentStrategy.CANARY: 30.0,
            DeploymentStrategy.BLUE_GREEN: 10.0,
            DeploymentStrategy.ROLLING: 120.0,
            DeploymentStrategy.RECREATE: 300.0,
            DeploymentStrategy.SHADOW: 5.0,
            DeploymentStrategy.A_B_TEST: 15.0,
        }
        t = base_times.get(strategy, 60.0)
        if comp and comp.failover.enabled:
            t *= 0.5
        return round(t, 1)

    def _strategy_pros_cons(
        self, strategy: DeploymentStrategy
    ) -> tuple[list[str], list[str]]:
        data: dict[DeploymentStrategy, tuple[list[str], list[str]]] = {
            DeploymentStrategy.CANARY: (
                ["Gradual traffic shift", "Early failure detection", "Low blast radius"],
                ["Slower rollout", "Requires traffic splitting"],
            ),
            DeploymentStrategy.BLUE_GREEN: (
                ["Instant rollback", "Zero-downtime", "Full environment validation"],
                ["Double resource cost", "State migration complexity"],
            ),
            DeploymentStrategy.ROLLING: (
                ["No extra resources", "Gradual update"],
                ["Slower rollback", "Mixed versions during deploy"],
            ),
            DeploymentStrategy.RECREATE: (
                ["Simple implementation", "Clean state"],
                ["Downtime required", "No gradual validation"],
            ),
            DeploymentStrategy.SHADOW: (
                ["Zero user impact", "Production traffic testing"],
                ["Double compute cost", "No real user validation"],
            ),
            DeploymentStrategy.A_B_TEST: (
                ["Data-driven decisions", "Controlled exposure"],
                ["Complex routing", "Requires feature flags"],
            ),
        }
        return data.get(strategy, (["Flexible"], ["Unknown trade-offs"]))
