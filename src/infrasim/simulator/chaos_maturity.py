"""Chaos engineering maturity model.

Assesses an organization's chaos engineering practices across multiple
dimensions, providing a maturity level and actionable roadmap for
improving resilience testing practices. Based on the Chaos Engineering
Maturity Model (CEMM) framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from infrasim.model.components import ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph


class MaturityLevel(int, Enum):
    """Chaos engineering maturity levels (0-5)."""

    LEVEL_0_NONE = 0  # No chaos engineering
    LEVEL_1_INITIAL = 1  # Ad-hoc, manual testing
    LEVEL_2_DEFINED = 2  # Defined scenarios, some automation
    LEVEL_3_MANAGED = 3  # Regular game days, metrics-driven
    LEVEL_4_MEASURED = 4  # Continuous chaos, SLO-integrated
    LEVEL_5_OPTIMIZED = 5  # AI-driven, self-healing


class MaturityDimension(str, Enum):
    """Dimensions of chaos engineering maturity assessment."""

    FAULT_INJECTION = "fault_injection"
    OBSERVABILITY = "observability"
    AUTOMATION = "automation"
    BLAST_RADIUS_CONTROL = "blast_radius_control"
    GAME_DAYS = "game_days"
    STEADY_STATE_HYPOTHESIS = "steady_state_hypothesis"
    ROLLBACK_CAPABILITY = "rollback_capability"
    ORGANIZATIONAL_ADOPTION = "organizational_adoption"


@dataclass
class DimensionAssessment:
    """Assessment result for a single chaos maturity dimension."""

    dimension: MaturityDimension
    current_level: MaturityLevel
    max_level: MaturityLevel = MaturityLevel.LEVEL_5_OPTIMIZED
    score: float = 0.0  # 0-100
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    next_level_actions: list[str] = field(default_factory=list)


@dataclass
class MaturityRoadmap:
    """Improvement roadmap for advancing chaos engineering maturity."""

    current_overall_level: MaturityLevel = MaturityLevel.LEVEL_0_NONE
    target_level: MaturityLevel = MaturityLevel.LEVEL_1_INITIAL
    quick_wins: list[str] = field(default_factory=list)
    short_term: list[str] = field(default_factory=list)
    long_term: list[str] = field(default_factory=list)
    estimated_months_to_next_level: float = 0.0


@dataclass
class ChaosMaturityReport:
    """Complete chaos engineering maturity assessment report."""

    overall_level: MaturityLevel = MaturityLevel.LEVEL_0_NONE
    overall_score: float = 0.0  # 0-100
    dimensions: list[DimensionAssessment] = field(default_factory=list)
    roadmap: MaturityRoadmap = field(default_factory=MaturityRoadmap)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    peer_comparison: str = "below average"


class ChaosMaturityAssessor:
    """Assesses chaos engineering maturity from an infrastructure graph.

    Analyzes the infrastructure configuration across 8 dimensions to
    determine the organization's chaos engineering readiness, providing
    a maturity level (0-5), detailed per-dimension assessments, and an
    actionable roadmap for improvement.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    def assess(self) -> ChaosMaturityReport:
        """Run a full chaos engineering maturity assessment."""
        dimensions = [
            self._assess_fault_injection(),
            self._assess_observability(),
            self._assess_automation(),
            self._assess_blast_radius_control(),
            self._assess_game_days(),
            self._assess_steady_state(),
            self._assess_rollback(),
            self._assess_organizational(),
        ]

        overall_level, overall_score = self._calculate_overall(dimensions)
        roadmap = self._build_roadmap(dimensions, overall_level)
        peer_comparison = self._determine_peer_comparison(overall_score)

        # Determine strengths and weaknesses
        strengths: list[str] = []
        weaknesses: list[str] = []
        for dim in dimensions:
            label = dim.dimension.value.replace("_", " ").title()
            if dim.current_level.value >= 3:
                strengths.append(
                    f"{label}: Level {dim.current_level.value} ({dim.current_level.name})"
                )
            elif dim.current_level.value <= 1:
                weaknesses.append(
                    f"{label}: Level {dim.current_level.value} ({dim.current_level.name})"
                )

        return ChaosMaturityReport(
            overall_level=overall_level,
            overall_score=round(overall_score, 1),
            dimensions=dimensions,
            roadmap=roadmap,
            strengths=strengths,
            weaknesses=weaknesses,
            peer_comparison=peer_comparison,
        )

    # -------------------------------------------------------------------
    # Dimension assessors
    # -------------------------------------------------------------------

    def _assess_fault_injection(self) -> DimensionAssessment:
        """Assess fault injection maturity.

        Looks for circuit breakers, retry strategies, and fault tolerance
        patterns in the infrastructure graph.

        L0: No fault tolerance patterns
        L1: Some retry strategies
        L2: Circuit breakers on some edges
        L3: Circuit breakers + retries on most edges
        L4: Comprehensive fault tolerance + singleflight
        L5: Full coverage with advanced patterns
        """
        components = list(self._graph.components.values())
        edges = self._graph.all_dependency_edges()

        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.FAULT_INJECTION,
                current_level=MaturityLevel.LEVEL_0_NONE,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components to begin fault injection assessment"],
                next_level_actions=["Create an infrastructure model with dependency edges"],
            )

        total_edges = len(edges)
        if total_edges == 0:
            # No dependencies means limited fault injection scope
            has_failover = sum(1 for c in components if c.failover.enabled)
            fo_ratio = has_failover / len(components)
            if fo_ratio == 0:
                return DimensionAssessment(
                    dimension=MaturityDimension.FAULT_INJECTION,
                    current_level=MaturityLevel.LEVEL_0_NONE,
                    score=5.0,
                    evidence=["No dependency edges or failover configured"],
                    gaps=["No fault tolerance patterns found"],
                    next_level_actions=["Define dependencies and enable failover on critical components"],
                )
            level = MaturityLevel.LEVEL_1_INITIAL if fo_ratio < 0.5 else MaturityLevel.LEVEL_2_DEFINED
            return DimensionAssessment(
                dimension=MaturityDimension.FAULT_INJECTION,
                current_level=level,
                score=15.0 + fo_ratio * 25.0,
                evidence=[f"{has_failover}/{len(components)} components have failover"],
                gaps=["No dependency edges to apply circuit breakers or retries"],
                next_level_actions=["Define dependency edges with circuit breaker and retry configs"],
            )

        cb_count = sum(1 for e in edges if e.circuit_breaker.enabled)
        retry_count = sum(1 for e in edges if e.retry_strategy.enabled)
        sf_count = sum(1 for c in components if c.singleflight.enabled)

        cb_ratio = cb_count / total_edges
        retry_ratio = retry_count / total_edges
        sf_ratio = sf_count / len(components) if components else 0.0

        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if cb_ratio == 0 and retry_ratio == 0:
            level = MaturityLevel.LEVEL_0_NONE
            score = 5.0
            gaps.append("No circuit breakers or retry strategies configured")
            actions.append("Enable retry strategies on critical dependency edges")
            actions.append("Add circuit breakers to prevent cascade failures")
        elif cb_ratio < 0.25 and retry_ratio < 0.5:
            level = MaturityLevel.LEVEL_1_INITIAL
            score = 15.0 + (cb_ratio + retry_ratio) * 15.0
            evidence.append(f"CB: {cb_count}/{total_edges}, Retries: {retry_count}/{total_edges}")
            gaps.append("Limited fault tolerance coverage")
            actions.append("Increase circuit breaker coverage to >50% of edges")
        elif cb_ratio < 0.5:
            level = MaturityLevel.LEVEL_2_DEFINED
            score = 35.0 + cb_ratio * 30.0
            evidence.append(f"CB: {cb_ratio:.0%}, Retries: {retry_ratio:.0%}")
            gaps.append(f"{total_edges - cb_count} edges lack circuit breakers")
            actions.append("Enable circuit breakers on all dependency edges")
        elif cb_ratio < 0.75 or retry_ratio < 0.75:
            level = MaturityLevel.LEVEL_3_MANAGED
            score = 55.0 + (cb_ratio + retry_ratio) / 2 * 20.0
            evidence.append(f"CB: {cb_ratio:.0%}, Retries: {retry_ratio:.0%}")
            gaps.append("Not all edges have fault tolerance patterns")
            actions.append("Achieve >75% coverage for both circuit breakers and retries")
        elif sf_ratio < 0.5:
            level = MaturityLevel.LEVEL_4_MEASURED
            score = 75.0 + (cb_ratio + retry_ratio + sf_ratio) / 3 * 15.0
            evidence.append(f"CB: {cb_ratio:.0%}, Retries: {retry_ratio:.0%}, Singleflight: {sf_ratio:.0%}")
            gaps.append("Singleflight/request coalescing coverage is low")
            actions.append("Enable singleflight on components to deduplicate concurrent requests")
        else:
            level = MaturityLevel.LEVEL_5_OPTIMIZED
            score = 90.0 + min(10.0, (cb_ratio + retry_ratio + sf_ratio) / 3 * 10.0)
            evidence.append("Comprehensive fault injection patterns: CB, retries, singleflight")
            actions.append("Implement chaos experiments with automated fault injection schedules")

        return DimensionAssessment(
            dimension=MaturityDimension.FAULT_INJECTION,
            current_level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _assess_observability(self) -> DimensionAssessment:
        """Assess observability maturity.

        Checks log_enabled, monitoring setup, and health check configs.

        L0: No logging or monitoring
        L1: Some logging enabled
        L2: Majority of components have logging
        L3: Logging + IDS monitoring
        L4: Comprehensive monitoring (log + IDS + health checks)
        L5: Full observability with advanced metrics
        """
        components = list(self._graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.OBSERVABILITY,
                current_level=MaturityLevel.LEVEL_0_NONE,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                next_level_actions=["Create an infrastructure model to assess observability"],
            )

        total = len(components)
        log_count = sum(1 for c in components if c.security.log_enabled)
        ids_count = sum(1 for c in components if c.security.ids_monitored)
        hc_count = sum(
            1 for c in components
            if c.failover.enabled and c.failover.health_check_interval_seconds > 0
        )

        log_ratio = log_count / total
        ids_ratio = ids_count / total
        hc_ratio = hc_count / total

        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if log_ratio == 0:
            level = MaturityLevel.LEVEL_0_NONE
            score = 0.0
            gaps.append("No logging enabled on any component")
            actions.append("Enable log_enabled on all components")
        elif log_ratio < 0.5:
            level = MaturityLevel.LEVEL_1_INITIAL
            score = 10.0 + log_ratio * 30.0
            evidence.append(f"{log_count}/{total} components have logging enabled")
            gaps.append(f"{total - log_count} components lack logging")
            actions.append("Enable logging on all components")
        elif ids_ratio < 0.25:
            level = MaturityLevel.LEVEL_2_DEFINED
            score = 35.0 + log_ratio * 15.0
            evidence.append(f"Logging: {log_ratio:.0%}")
            gaps.append("IDS monitoring not widely deployed")
            actions.append("Enable IDS monitoring on critical components")
        elif hc_ratio < 0.5:
            level = MaturityLevel.LEVEL_3_MANAGED
            score = 55.0 + (ids_ratio + hc_ratio) / 2 * 20.0
            evidence.append(f"Logging: {log_ratio:.0%}, IDS: {ids_ratio:.0%}")
            gaps.append(f"Health checks configured on only {hc_count}/{total} components")
            actions.append("Enable health checks (failover with health_check_interval) on all components")
        elif hc_ratio < 0.75 or ids_ratio < 0.75:
            level = MaturityLevel.LEVEL_4_MEASURED
            score = 75.0 + (log_ratio + ids_ratio + hc_ratio) / 3 * 15.0
            evidence.append(f"Log: {log_ratio:.0%}, IDS: {ids_ratio:.0%}, HC: {hc_ratio:.0%}")
            gaps.append("Not all components have comprehensive monitoring")
            actions.append("Achieve >75% coverage for IDS and health checks")
        else:
            level = MaturityLevel.LEVEL_5_OPTIMIZED
            score = 90.0 + min(10.0, (log_ratio + ids_ratio + hc_ratio) / 3 * 10.0)
            evidence.append("Full observability: logging, IDS, health checks across all components")
            actions.append("Add distributed tracing and custom SLI metrics")

        return DimensionAssessment(
            dimension=MaturityDimension.OBSERVABILITY,
            current_level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _assess_automation(self) -> DimensionAssessment:
        """Assess automation maturity.

        Checks autoscaling and failover enabled ratios.

        L0: No automation
        L1: <25% autoscaling or failover
        L2: 25-50% coverage
        L3: 50-75% coverage
        L4: 75-90% coverage
        L5: >90% full automation
        """
        components = list(self._graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.AUTOMATION,
                current_level=MaturityLevel.LEVEL_0_NONE,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                next_level_actions=["Create an infrastructure model"],
            )

        total = len(components)
        as_count = sum(1 for c in components if c.autoscaling.enabled)
        fo_count = sum(1 for c in components if c.failover.enabled)

        as_ratio = as_count / total
        fo_ratio = fo_count / total
        combined = (as_ratio + fo_ratio) / 2.0

        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if combined == 0:
            level = MaturityLevel.LEVEL_0_NONE
            score = 0.0
            gaps.append("No autoscaling or failover enabled")
            actions.append("Enable autoscaling on stateless components")
            actions.append("Enable failover on stateful components (databases, queues)")
        elif combined < 0.25:
            level = MaturityLevel.LEVEL_1_INITIAL
            score = 10.0 + combined * 60.0
            evidence.append(f"Autoscaling: {as_count}/{total}, Failover: {fo_count}/{total}")
            gaps.append("Very limited automation coverage")
            actions.append("Expand autoscaling and failover to more components")
        elif combined < 0.5:
            level = MaturityLevel.LEVEL_2_DEFINED
            score = 30.0 + combined * 40.0
            evidence.append(f"AS: {as_ratio:.0%}, FO: {fo_ratio:.0%}")
            gaps.append("Automation covers less than half of components")
            actions.append("Enable autoscaling and failover on all critical path components")
        elif combined < 0.75:
            level = MaturityLevel.LEVEL_3_MANAGED
            score = 50.0 + combined * 30.0
            evidence.append(f"AS: {as_ratio:.0%}, FO: {fo_ratio:.0%}")
            gaps.append("Automation not yet comprehensive")
            actions.append("Achieve >75% combined autoscaling and failover coverage")
        elif combined < 0.9:
            level = MaturityLevel.LEVEL_4_MEASURED
            score = 75.0 + combined * 16.7
            evidence.append(f"AS: {as_ratio:.0%}, FO: {fo_ratio:.0%} (combined: {combined:.0%})")
            gaps.append("Near-complete automation but some gaps remain")
            actions.append("Enable automation on remaining components to reach >90%")
        else:
            level = MaturityLevel.LEVEL_5_OPTIMIZED
            score = 90.0 + min(10.0, combined * 10.0)
            evidence.append("Full automation: autoscaling and failover on all components")
            actions.append("Implement predictive autoscaling and ML-driven capacity management")

        return DimensionAssessment(
            dimension=MaturityDimension.AUTOMATION,
            current_level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _assess_blast_radius_control(self) -> DimensionAssessment:
        """Assess blast radius control maturity.

        Checks circuit breakers on dependencies, replica counts, and
        network segmentation.

        L0: No blast radius controls
        L1: Some replicas (>1)
        L2: Replicas + some circuit breakers
        L3: Good CB coverage + network segmentation
        L4: Comprehensive controls
        L5: Full isolation with advanced containment
        """
        components = list(self._graph.components.values())
        edges = self._graph.all_dependency_edges()

        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.BLAST_RADIUS_CONTROL,
                current_level=MaturityLevel.LEVEL_0_NONE,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                next_level_actions=["Create an infrastructure model"],
            )

        total = len(components)
        replica_count = sum(1 for c in components if c.replicas > 1)
        segmented_count = sum(1 for c in components if c.security.network_segmented)

        total_edges = len(edges)
        cb_count = sum(1 for e in edges if e.circuit_breaker.enabled) if total_edges > 0 else 0

        replica_ratio = replica_count / total
        seg_ratio = segmented_count / total
        cb_ratio = cb_count / total_edges if total_edges > 0 else 0.0

        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if replica_ratio == 0 and cb_ratio == 0:
            level = MaturityLevel.LEVEL_0_NONE
            score = 0.0
            gaps.append("No replicas or circuit breakers configured")
            actions.append("Add replicas to critical components for redundancy")
        elif replica_ratio < 0.5 and cb_ratio < 0.25:
            level = MaturityLevel.LEVEL_1_INITIAL
            score = 10.0 + (replica_ratio + cb_ratio) * 25.0
            evidence.append(f"Replicas: {replica_count}/{total}, CB: {cb_count}/{total_edges if total_edges else 0}")
            gaps.append("Limited blast radius containment")
            actions.append("Increase replica counts and add circuit breakers to dependencies")
        elif cb_ratio < 0.5 or seg_ratio < 0.25:
            level = MaturityLevel.LEVEL_2_DEFINED
            score = 30.0 + (replica_ratio + cb_ratio) / 2 * 30.0
            evidence.append(f"Replicas: {replica_ratio:.0%}, CB: {cb_ratio:.0%}")
            gaps.append("Circuit breaker and network segmentation coverage is low")
            actions.append("Enable circuit breakers on all edges and implement network segmentation")
        elif seg_ratio < 0.5 or cb_ratio < 0.75:
            level = MaturityLevel.LEVEL_3_MANAGED
            score = 55.0 + (cb_ratio + seg_ratio) / 2 * 20.0
            evidence.append(f"CB: {cb_ratio:.0%}, Segmentation: {seg_ratio:.0%}")
            gaps.append("Network segmentation not comprehensive")
            actions.append("Achieve >75% CB coverage and >50% network segmentation")
        elif seg_ratio < 0.75 or cb_ratio < 0.9:
            level = MaturityLevel.LEVEL_4_MEASURED
            score = 75.0 + (replica_ratio + cb_ratio + seg_ratio) / 3 * 15.0
            evidence.append(f"Replicas: {replica_ratio:.0%}, CB: {cb_ratio:.0%}, Seg: {seg_ratio:.0%}")
            gaps.append("Near-complete but gaps remain in segmentation or CB coverage")
            actions.append("Close remaining gaps in circuit breakers and segmentation")
        else:
            level = MaturityLevel.LEVEL_5_OPTIMIZED
            score = 90.0 + min(10.0, (replica_ratio + cb_ratio + seg_ratio) / 3 * 10.0)
            evidence.append("Full blast radius control: replicas, circuit breakers, segmentation")
            actions.append("Implement cell-based architecture for ultimate isolation")

        return DimensionAssessment(
            dimension=MaturityDimension.BLAST_RADIUS_CONTROL,
            current_level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _assess_game_days(self) -> DimensionAssessment:
        """Assess game day readiness.

        Infers game day readiness from evidence of fault tolerance testing
        in the infrastructure configuration: failover configs, circuit
        breakers, retry strategies, health checks, and autoscaling are
        all indicators that the organization tests failure scenarios.

        L0: No evidence of testing
        L1: Basic failover configured (testing implied)
        L2: Failover + circuit breakers (failure scenarios defined)
        L3: Comprehensive configs + team runbook coverage
        L4: All patterns + high team readiness
        L5: Full coverage with automation percentage > 60%
        """
        components = list(self._graph.components.values())
        edges = self._graph.all_dependency_edges()

        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.GAME_DAYS,
                current_level=MaturityLevel.LEVEL_0_NONE,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                next_level_actions=["Create an infrastructure model"],
            )

        total = len(components)
        total_edges = len(edges)

        fo_count = sum(1 for c in components if c.failover.enabled)
        as_count = sum(1 for c in components if c.autoscaling.enabled)
        cb_count = sum(1 for e in edges if e.circuit_breaker.enabled) if total_edges > 0 else 0
        retry_count = sum(1 for e in edges if e.retry_strategy.enabled) if total_edges > 0 else 0

        fo_ratio = fo_count / total
        as_ratio = as_count / total
        cb_ratio = cb_count / total_edges if total_edges > 0 else 0.0
        retry_ratio = retry_count / total_edges if total_edges > 0 else 0.0

        # Team readiness indicators
        runbook_scores = [c.team.runbook_coverage_percent for c in components]
        avg_runbook = sum(runbook_scores) / total
        automation_scores = [c.team.automation_percent for c in components]
        avg_automation = sum(automation_scores) / total

        # Combined readiness score from infrastructure patterns
        infra_readiness = (fo_ratio + as_ratio + cb_ratio + retry_ratio) / 4.0

        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if infra_readiness == 0:
            level = MaturityLevel.LEVEL_0_NONE
            score = 0.0
            gaps.append("No fault tolerance patterns suggest no game day exercises")
            actions.append("Start with basic failover testing on critical components")
        elif infra_readiness < 0.2:
            level = MaturityLevel.LEVEL_1_INITIAL
            score = 10.0 + infra_readiness * 100.0
            evidence.append(f"Infrastructure readiness: {infra_readiness:.0%}")
            gaps.append("Limited evidence of failure testing")
            actions.append("Define failure scenarios and conduct first game day exercise")
        elif infra_readiness < 0.4 or avg_runbook < 40:
            level = MaturityLevel.LEVEL_2_DEFINED
            score = 30.0 + infra_readiness * 50.0
            evidence.append(f"Infra readiness: {infra_readiness:.0%}, Avg runbook: {avg_runbook:.0f}%")
            gaps.append("Game days not yet regular or runbook coverage is low")
            actions.append("Schedule regular game days and improve runbook coverage to >50%")
        elif infra_readiness < 0.6 or avg_runbook < 60:
            level = MaturityLevel.LEVEL_3_MANAGED
            score = 55.0 + infra_readiness * 25.0
            evidence.append(f"Infra readiness: {infra_readiness:.0%}, Runbooks: {avg_runbook:.0f}%")
            gaps.append("Game days could be more comprehensive")
            actions.append("Expand game days to cover all critical paths and increase automation")
        elif avg_automation < 50:
            level = MaturityLevel.LEVEL_4_MEASURED
            score = 75.0 + infra_readiness * 12.5 + avg_automation / 100 * 5.0
            evidence.append(f"Infra readiness: {infra_readiness:.0%}, Automation: {avg_automation:.0f}%")
            gaps.append("Automation level could be higher for continuous chaos")
            actions.append("Increase automation to >60% for continuous chaos testing")
        else:
            level = MaturityLevel.LEVEL_5_OPTIMIZED
            score = 90.0 + min(10.0, infra_readiness * 10.0)
            evidence.append("High infrastructure readiness with strong automation and runbook coverage")
            actions.append("Implement automated game day scheduling with AI-driven scenario generation")

        return DimensionAssessment(
            dimension=MaturityDimension.GAME_DAYS,
            current_level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _assess_steady_state(self) -> DimensionAssessment:
        """Assess steady state hypothesis maturity.

        Checks SLA/SLO targets and health check configurations as indicators
        of defined steady state.

        L0: No SLO targets or health checks
        L1: Some health checks
        L2: Some SLO targets defined
        L3: SLO on most components + health checks
        L4: Comprehensive SLO + monitoring
        L5: Full SLO coverage with advanced observability
        """
        components = list(self._graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.STEADY_STATE_HYPOTHESIS,
                current_level=MaturityLevel.LEVEL_0_NONE,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                next_level_actions=["Create an infrastructure model"],
            )

        total = len(components)
        slo_count = sum(1 for c in components if len(c.slo_targets) > 0)
        hc_count = sum(
            1 for c in components
            if c.failover.enabled and c.failover.health_check_interval_seconds > 0
        )
        log_count = sum(1 for c in components if c.security.log_enabled)

        slo_ratio = slo_count / total
        hc_ratio = hc_count / total
        log_ratio = log_count / total

        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if slo_ratio == 0 and hc_ratio == 0:
            level = MaturityLevel.LEVEL_0_NONE
            score = 0.0
            gaps.append("No SLO targets or health checks defined")
            actions.append("Define SLO targets for critical services")
        elif hc_ratio < 0.25 and slo_ratio < 0.1:
            level = MaturityLevel.LEVEL_1_INITIAL
            score = 10.0 + (hc_ratio + slo_ratio) * 40.0
            evidence.append(f"HC: {hc_count}/{total}, SLO: {slo_count}/{total}")
            gaps.append("Minimal steady state definition")
            actions.append("Define SLO targets and enable health checks on critical components")
        elif slo_ratio < 0.5:
            level = MaturityLevel.LEVEL_2_DEFINED
            score = 30.0 + slo_ratio * 40.0
            evidence.append(f"SLO: {slo_ratio:.0%}, HC: {hc_ratio:.0%}")
            gaps.append(f"Only {slo_count}/{total} components have SLO targets")
            actions.append("Expand SLO coverage to >50% of components")
        elif slo_ratio < 0.75 or hc_ratio < 0.5:
            level = MaturityLevel.LEVEL_3_MANAGED
            score = 55.0 + (slo_ratio + hc_ratio) / 2 * 20.0
            evidence.append(f"SLO: {slo_ratio:.0%}, HC: {hc_ratio:.0%}")
            gaps.append("Not all components have comprehensive steady state definition")
            actions.append("Achieve >75% SLO and >50% health check coverage")
        elif log_ratio < 0.75:
            level = MaturityLevel.LEVEL_4_MEASURED
            score = 75.0 + (slo_ratio + hc_ratio + log_ratio) / 3 * 15.0
            evidence.append(f"SLO: {slo_ratio:.0%}, HC: {hc_ratio:.0%}, Log: {log_ratio:.0%}")
            gaps.append("Logging coverage needed for full steady state observability")
            actions.append("Enable logging on >75% of components for steady state monitoring")
        else:
            level = MaturityLevel.LEVEL_5_OPTIMIZED
            score = 90.0 + min(10.0, (slo_ratio + hc_ratio + log_ratio) / 3 * 10.0)
            evidence.append("Comprehensive steady state: SLO targets, health checks, logging")
            actions.append("Implement automated steady state validation with SLO burn-rate alerts")

        return DimensionAssessment(
            dimension=MaturityDimension.STEADY_STATE_HYPOTHESIS,
            current_level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _assess_rollback(self) -> DimensionAssessment:
        """Assess rollback capability maturity.

        Checks failover mechanisms, replica diversity, and backup configs.

        L0: No rollback capability
        L1: Some failover
        L2: Failover + replicas
        L3: Good failover + backup coverage
        L4: Comprehensive rollback + DR config
        L5: Full rollback with multi-region DR
        """
        components = list(self._graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.ROLLBACK_CAPABILITY,
                current_level=MaturityLevel.LEVEL_0_NONE,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                next_level_actions=["Create an infrastructure model"],
            )

        total = len(components)
        fo_count = sum(1 for c in components if c.failover.enabled)
        replica_count = sum(1 for c in components if c.replicas > 1)
        backup_count = sum(1 for c in components if c.security.backup_enabled)
        dr_count = sum(1 for c in components if c.region.dr_target_region != "")

        fo_ratio = fo_count / total
        rep_ratio = replica_count / total
        backup_ratio = backup_count / total
        dr_ratio = dr_count / total

        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if fo_ratio == 0 and rep_ratio == 0:
            level = MaturityLevel.LEVEL_0_NONE
            score = 0.0
            gaps.append("No failover or replicas configured")
            actions.append("Enable failover on critical components")
            actions.append("Add replicas for redundancy")
        elif fo_ratio < 0.25:
            level = MaturityLevel.LEVEL_1_INITIAL
            score = 10.0 + (fo_ratio + rep_ratio) * 25.0
            evidence.append(f"Failover: {fo_count}/{total}, Replicas>1: {replica_count}/{total}")
            gaps.append("Limited failover coverage")
            actions.append("Enable failover on all critical components")
        elif fo_ratio < 0.5 or backup_ratio < 0.25:
            level = MaturityLevel.LEVEL_2_DEFINED
            score = 30.0 + (fo_ratio + rep_ratio) / 2 * 30.0
            evidence.append(f"FO: {fo_ratio:.0%}, Replicas: {rep_ratio:.0%}")
            gaps.append("Backup coverage is low")
            actions.append("Enable backups and increase failover coverage to >50%")
        elif backup_ratio < 0.5 or fo_ratio < 0.75:
            level = MaturityLevel.LEVEL_3_MANAGED
            score = 55.0 + (fo_ratio + backup_ratio) / 2 * 20.0
            evidence.append(f"FO: {fo_ratio:.0%}, Backup: {backup_ratio:.0%}")
            gaps.append("Backup and failover not comprehensive")
            actions.append("Achieve >75% failover and >50% backup coverage")
        elif dr_ratio < 0.25:
            level = MaturityLevel.LEVEL_4_MEASURED
            score = 75.0 + (fo_ratio + backup_ratio) / 2 * 15.0
            evidence.append(f"FO: {fo_ratio:.0%}, Backup: {backup_ratio:.0%}, DR: {dr_ratio:.0%}")
            gaps.append("No multi-region DR configuration")
            actions.append("Configure DR target regions for critical services")
        else:
            level = MaturityLevel.LEVEL_5_OPTIMIZED
            score = 90.0 + min(10.0, (fo_ratio + backup_ratio + dr_ratio) / 3 * 10.0)
            evidence.append("Full rollback: failover, backups, multi-region DR")
            actions.append("Implement automated DR drills and rollback testing")

        return DimensionAssessment(
            dimension=MaturityDimension.ROLLBACK_CAPABILITY,
            current_level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _assess_organizational(self) -> DimensionAssessment:
        """Assess organizational adoption maturity.

        Checks team config presence: runbook_coverage, automation_percent,
        team_size, and oncall coverage.

        L0: Default team config (no customization)
        L1: Some team config present
        L2: Moderate runbook coverage
        L3: Good runbook + automation
        L4: High runbook + automation + oncall
        L5: Excellent across all organizational metrics
        """
        components = list(self._graph.components.values())
        if not components:
            return DimensionAssessment(
                dimension=MaturityDimension.ORGANIZATIONAL_ADOPTION,
                current_level=MaturityLevel.LEVEL_0_NONE,
                score=0.0,
                evidence=["No components defined"],
                gaps=["Define infrastructure components"],
                next_level_actions=["Create an infrastructure model"],
            )

        total = len(components)

        # Aggregate team metrics
        runbook_scores = [c.team.runbook_coverage_percent for c in components]
        automation_scores = [c.team.automation_percent for c in components]
        team_sizes = [c.team.team_size for c in components]
        oncall_hours = [c.team.oncall_coverage_hours for c in components]

        avg_runbook = sum(runbook_scores) / total
        avg_automation = sum(automation_scores) / total
        avg_team_size = sum(team_sizes) / total
        avg_oncall = sum(oncall_hours) / total

        # Check for non-default configurations (default runbook=50%, automation=20%)
        has_custom_team = sum(
            1 for c in components
            if c.team.runbook_coverage_percent != 50.0 or c.team.automation_percent != 20.0
        )
        custom_ratio = has_custom_team / total

        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if custom_ratio == 0:
            # All defaults - no organizational investment detected
            level = MaturityLevel.LEVEL_0_NONE
            score = 5.0
            gaps.append("All team configurations at default values")
            actions.append("Customize team config: set accurate runbook_coverage and automation_percent")
        elif avg_runbook < 40:
            level = MaturityLevel.LEVEL_1_INITIAL
            score = 10.0 + avg_runbook * 0.5
            evidence.append(f"Avg runbook coverage: {avg_runbook:.0f}%")
            gaps.append("Low runbook coverage across teams")
            actions.append("Increase runbook coverage to >50% for all components")
        elif avg_runbook < 60:
            level = MaturityLevel.LEVEL_2_DEFINED
            score = 30.0 + avg_runbook * 0.4
            evidence.append(f"Runbook: {avg_runbook:.0f}%, Automation: {avg_automation:.0f}%")
            gaps.append("Moderate runbook coverage but automation is limited")
            actions.append("Improve automation to >30% and runbook coverage to >60%")
        elif avg_automation < 40:
            level = MaturityLevel.LEVEL_3_MANAGED
            score = 55.0 + avg_automation * 0.4
            evidence.append(f"Runbook: {avg_runbook:.0f}%, Automation: {avg_automation:.0f}%")
            gaps.append("Automation percentage is below target")
            actions.append("Increase automation to >50%")
        elif avg_automation < 60 or avg_oncall < 20:
            level = MaturityLevel.LEVEL_4_MEASURED
            score = 75.0 + avg_automation * 0.25
            evidence.append(
                f"Runbook: {avg_runbook:.0f}%, Automation: {avg_automation:.0f}%, "
                f"Oncall: {avg_oncall:.0f}h"
            )
            gaps.append("Automation or oncall coverage needs improvement")
            actions.append("Achieve >60% automation and ensure 24h oncall coverage")
        else:
            level = MaturityLevel.LEVEL_5_OPTIMIZED
            score = 90.0 + min(10.0, avg_automation / 10.0)
            evidence.append("Excellent organizational adoption: runbooks, automation, oncall")
            actions.append("Establish chaos engineering center of excellence and internal training")

        return DimensionAssessment(
            dimension=MaturityDimension.ORGANIZATIONAL_ADOPTION,
            current_level=level,
            score=min(100.0, round(score, 1)),
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    # -------------------------------------------------------------------
    # Aggregation helpers
    # -------------------------------------------------------------------

    def _calculate_overall(
        self, dimensions: list[DimensionAssessment]
    ) -> tuple[MaturityLevel, float]:
        """Calculate overall maturity level and score from dimension assessments.

        Uses a weighted average of dimension scores. The overall level is
        derived from the average score mapped to the level thresholds.
        """
        if not dimensions:
            return MaturityLevel.LEVEL_0_NONE, 0.0

        total_score = sum(d.score for d in dimensions)
        avg_score = total_score / len(dimensions)

        # Map average score to level
        if avg_score >= 90:
            level = MaturityLevel.LEVEL_5_OPTIMIZED
        elif avg_score >= 75:
            level = MaturityLevel.LEVEL_4_MEASURED
        elif avg_score >= 55:
            level = MaturityLevel.LEVEL_3_MANAGED
        elif avg_score >= 30:
            level = MaturityLevel.LEVEL_2_DEFINED
        elif avg_score >= 10:
            level = MaturityLevel.LEVEL_1_INITIAL
        else:
            level = MaturityLevel.LEVEL_0_NONE

        return level, avg_score

    def _build_roadmap(
        self,
        dimensions: list[DimensionAssessment],
        current_level: MaturityLevel,
    ) -> MaturityRoadmap:
        """Build an improvement roadmap from dimension assessments."""
        target_level = MaturityLevel(min(current_level.value + 1, 5))

        quick_wins: list[str] = []
        short_term: list[str] = []
        long_term: list[str] = []

        # Sort dimensions by score ascending (weakest first)
        sorted_dims = sorted(dimensions, key=lambda d: d.score)

        for dim in sorted_dims:
            label = dim.dimension.value.replace("_", " ").title()
            if dim.current_level.value >= 5:
                continue  # Already optimized

            for action in dim.next_level_actions:
                action_text = f"[{label}] {action}"
                # Quick wins: low-hanging fruit from weakest dimensions
                if dim.current_level.value <= 1 and len(quick_wins) < 5:
                    quick_wins.append(action_text)
                # Short term: moderate improvements
                elif dim.current_level.value <= 3 and len(short_term) < 5:
                    short_term.append(action_text)
                # Long term: advanced improvements
                elif len(long_term) < 5:
                    long_term.append(action_text)

        # Estimate months to next level based on current state
        if current_level.value == 0:
            months = 1.0
        elif current_level.value == 1:
            months = 2.0
        elif current_level.value == 2:
            months = 3.0
        elif current_level.value == 3:
            months = 6.0
        elif current_level.value == 4:
            months = 12.0
        else:
            months = 0.0  # Already at max

        return MaturityRoadmap(
            current_overall_level=current_level,
            target_level=target_level,
            quick_wins=quick_wins,
            short_term=short_term,
            long_term=long_term,
            estimated_months_to_next_level=months,
        )

    def _determine_peer_comparison(self, score: float) -> str:
        """Determine peer comparison category based on overall score."""
        if score > 70:
            return "above average"
        elif score >= 40:
            return "average"
        else:
            return "below average"
