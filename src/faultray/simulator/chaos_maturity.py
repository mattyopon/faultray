"""Chaos engineering maturity model.

Assesses an organization's chaos engineering practices across multiple
dimensions, providing a maturity level and actionable roadmap for
improving resilience testing practices.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MaturityLevel(str, Enum):
    """Chaos engineering maturity levels."""

    level_0_initial = "level_0_initial"
    level_1_planned = "level_1_planned"
    level_2_practiced = "level_2_practiced"
    level_3_managed = "level_3_managed"
    level_4_optimized = "level_4_optimized"


class MaturityDimension(str, Enum):
    """Dimensions of chaos engineering maturity assessment."""

    culture = "culture"
    process = "process"
    tooling = "tooling"
    automation = "automation"
    observability = "observability"
    blast_radius_control = "blast_radius_control"
    hypothesis_driven = "hypothesis_driven"
    gameday_practice = "gameday_practice"


# ---------------------------------------------------------------------------
# Score thresholds
# ---------------------------------------------------------------------------

_LEVEL_THRESHOLDS: list[tuple[float, MaturityLevel]] = [
    (80.0, MaturityLevel.level_4_optimized),
    (60.0, MaturityLevel.level_3_managed),
    (40.0, MaturityLevel.level_2_practiced),
    (20.0, MaturityLevel.level_1_planned),
    (0.0, MaturityLevel.level_0_initial),
]


def _score_to_level(score: float) -> MaturityLevel:
    """Map a 0-100 score to a maturity level."""
    for threshold, level in _LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return MaturityLevel.level_0_initial


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


class ChaosConfig(BaseModel):
    """Organisational chaos engineering configuration input."""

    has_gameday_practice: bool = False
    gameday_frequency_per_quarter: int = 0
    has_hypothesis_driven_experiments: bool = False
    has_automated_chaos: bool = False
    chaos_in_ci_cd: bool = False
    blast_radius_controls: bool = False
    observability_coverage_percent: float = 0.0
    runbook_coverage_percent: float = 0.0
    incident_learning_process: bool = False
    team_training_hours_per_quarter: float = 0.0


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class DimensionScore(BaseModel):
    """Assessment result for a single chaos maturity dimension."""

    dimension: MaturityDimension
    score: float = 0.0
    level: MaturityLevel = MaturityLevel.level_0_initial
    evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next_level_actions: list[str] = Field(default_factory=list)


class RoadmapItem(BaseModel):
    """A single improvement action in the maturity roadmap."""

    phase: int = 1
    title: str = ""
    description: str = ""
    dimension: MaturityDimension = MaturityDimension.culture
    effort: str = "medium"  # low / medium / high
    impact: str = "medium"  # low / medium / high
    prerequisites: list[str] = Field(default_factory=list)


class MaturityAssessment(BaseModel):
    """Full chaos engineering maturity assessment result."""

    overall_level: MaturityLevel = MaturityLevel.level_0_initial
    overall_score: float = 0.0
    dimensions: list[DimensionScore] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    roadmap: list[RoadmapItem] = Field(default_factory=list)
    industry_percentile: float = 0.0
    estimated_improvement_months: int = 0


class IndustryComparison(BaseModel):
    """Benchmark comparison against industry peers."""

    industry: str = ""
    your_score: float = 0.0
    industry_average: float = 50.0
    percentile: float = 0.0
    above_average_dimensions: list[str] = Field(default_factory=list)
    below_average_dimensions: list[str] = Field(default_factory=list)


class ROIEstimate(BaseModel):
    """Estimated ROI of reaching a target maturity level."""

    current_level: MaturityLevel = MaturityLevel.level_0_initial
    target_level: MaturityLevel = MaturityLevel.level_1_planned
    estimated_months: int = 0
    estimated_cost_hours: int = 0
    incident_reduction_percent: float = 0.0
    mttr_improvement_percent: float = 0.0
    availability_gain_nines: float = 0.0


class ExecutiveSummary(BaseModel):
    """C-level executive summary of the maturity assessment."""

    overall_level: MaturityLevel = MaturityLevel.level_0_initial
    overall_score: float = 0.0
    headline: str = ""
    key_findings: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    recommended_investments: list[str] = Field(default_factory=list)
    estimated_improvement_months: int = 0


class ProgressReport(BaseModel):
    """Track improvement over time between two assessments."""

    score_delta: float = 0.0
    level_changed: bool = False
    previous_level: MaturityLevel = MaturityLevel.level_0_initial
    current_level: MaturityLevel = MaturityLevel.level_0_initial
    improved_dimensions: list[str] = Field(default_factory=list)
    regressed_dimensions: list[str] = Field(default_factory=list)
    unchanged_dimensions: list[str] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Industry averages (static lookup)
# ---------------------------------------------------------------------------

_INDUSTRY_AVERAGES: dict[str, float] = {
    "finance": 62.0,
    "healthcare": 48.0,
    "ecommerce": 55.0,
    "saas": 58.0,
    "gaming": 45.0,
    "media": 42.0,
    "telecom": 50.0,
    "government": 35.0,
    "default": 50.0,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ChaosMaturityEngine:
    """Stateless engine that assesses chaos engineering maturity.

    All methods are pure functions that take explicit inputs and return
    deterministic results (except timestamps).
    """

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def assess_maturity(
        self,
        graph: InfraGraph,
        chaos_config: ChaosConfig,
    ) -> MaturityAssessment:
        """Run a full maturity assessment across all dimensions."""
        dimensions = [
            self.score_dimension(graph, dim, chaos_config)
            for dim in MaturityDimension
        ]

        overall_score = self._average_score(dimensions)
        overall_level = _score_to_level(overall_score)

        strengths = self._find_strengths(dimensions)
        weaknesses = self._find_weaknesses(dimensions)

        roadmap = self.generate_roadmap(
            MaturityAssessment(
                overall_level=overall_level,
                overall_score=overall_score,
                dimensions=dimensions,
                strengths=strengths,
                weaknesses=weaknesses,
            )
        )

        percentile = self._estimate_percentile(overall_score)
        months = self._estimate_months(overall_level)

        return MaturityAssessment(
            overall_level=overall_level,
            overall_score=round(overall_score, 1),
            dimensions=dimensions,
            strengths=strengths,
            weaknesses=weaknesses,
            roadmap=roadmap,
            industry_percentile=round(percentile, 1),
            estimated_improvement_months=months,
        )

    def score_dimension(
        self,
        graph: InfraGraph,
        dimension: MaturityDimension,
        config: ChaosConfig,
    ) -> DimensionScore:
        """Score a single maturity dimension."""
        scorers = {
            MaturityDimension.culture: self._score_culture,
            MaturityDimension.process: self._score_process,
            MaturityDimension.tooling: self._score_tooling,
            MaturityDimension.automation: self._score_automation,
            MaturityDimension.observability: self._score_observability,
            MaturityDimension.blast_radius_control: self._score_blast_radius,
            MaturityDimension.hypothesis_driven: self._score_hypothesis,
            MaturityDimension.gameday_practice: self._score_gameday,
        }
        scorer = scorers[dimension]
        return scorer(graph, config)

    def generate_roadmap(
        self,
        assessment: MaturityAssessment,
    ) -> list[RoadmapItem]:
        """Generate an improvement roadmap from an assessment."""
        items: list[RoadmapItem] = []

        sorted_dims = sorted(assessment.dimensions, key=lambda d: d.score)

        phase = 1
        for ds in sorted_dims:
            if ds.level == MaturityLevel.level_4_optimized:
                continue
            for action in ds.next_level_actions:
                effort = "low" if ds.score < 30 else ("medium" if ds.score < 60 else "high")
                impact = "high" if ds.score < 30 else ("medium" if ds.score < 60 else "low")
                prereqs: list[str] = []
                if phase > 1:
                    prereqs.append(f"Complete phase {phase - 1}")
                items.append(RoadmapItem(
                    phase=phase,
                    title=action,
                    description=f"Improve {ds.dimension.value}: {action}",
                    dimension=ds.dimension,
                    effort=effort,
                    impact=impact,
                    prerequisites=prereqs,
                ))
                phase += 1

        return items

    def compare_to_industry(
        self,
        assessment: MaturityAssessment,
        industry: str,
    ) -> IndustryComparison:
        """Compare assessment to industry benchmark."""
        avg = _INDUSTRY_AVERAGES.get(industry.lower(), _INDUSTRY_AVERAGES["default"])
        your_score = assessment.overall_score

        if avg > 0:
            percentile = min(99.0, max(1.0, (your_score / avg) * 50.0))
        else:
            percentile = 50.0

        above: list[str] = []
        below: list[str] = []
        for ds in assessment.dimensions:
            if ds.score >= avg:
                above.append(ds.dimension.value)
            else:
                below.append(ds.dimension.value)

        return IndustryComparison(
            industry=industry,
            your_score=round(your_score, 1),
            industry_average=avg,
            percentile=round(percentile, 1),
            above_average_dimensions=above,
            below_average_dimensions=below,
        )

    def estimate_roi(
        self,
        assessment: MaturityAssessment,
        target_level: MaturityLevel,
    ) -> ROIEstimate:
        """Estimate ROI of reaching a target maturity level."""
        level_order = list(MaturityLevel)
        current_idx = level_order.index(assessment.overall_level)
        target_idx = level_order.index(target_level)

        gap = max(0, target_idx - current_idx)
        months = gap * 3
        cost_hours = gap * 160
        incident_reduction = min(80.0, gap * 20.0)
        mttr_improvement = min(70.0, gap * 15.0)
        availability_gain = gap * 0.2

        return ROIEstimate(
            current_level=assessment.overall_level,
            target_level=target_level,
            estimated_months=months,
            estimated_cost_hours=cost_hours,
            incident_reduction_percent=round(incident_reduction, 1),
            mttr_improvement_percent=round(mttr_improvement, 1),
            availability_gain_nines=round(availability_gain, 2),
        )

    def generate_executive_summary(
        self,
        assessment: MaturityAssessment,
    ) -> ExecutiveSummary:
        """Generate a C-level executive summary."""
        level_labels = {
            MaturityLevel.level_0_initial: "Initial",
            MaturityLevel.level_1_planned: "Planned",
            MaturityLevel.level_2_practiced: "Practiced",
            MaturityLevel.level_3_managed: "Managed",
            MaturityLevel.level_4_optimized: "Optimized",
        }
        label = level_labels.get(assessment.overall_level, "Unknown")
        headline = (
            f"Chaos Engineering Maturity: {label} "
            f"(Score: {assessment.overall_score}/100)"
        )

        findings: list[str] = []
        if assessment.strengths:
            findings.append(f"Strengths: {', '.join(assessment.strengths[:3])}")
        if assessment.weaknesses:
            findings.append(f"Areas for improvement: {', '.join(assessment.weaknesses[:3])}")
        findings.append(
            f"Overall maturity at {assessment.overall_score:.0f}% "
            f"({label} level)"
        )

        risks: list[str] = []
        for ds in sorted(assessment.dimensions, key=lambda d: d.score):
            if ds.score < 30:
                risks.append(f"Low maturity in {ds.dimension.value} ({ds.score:.0f}%)")

        investments: list[str] = []
        for item in assessment.roadmap[:3]:
            investments.append(f"[{item.effort} effort] {item.title}")

        return ExecutiveSummary(
            overall_level=assessment.overall_level,
            overall_score=assessment.overall_score,
            headline=headline,
            key_findings=findings,
            top_risks=risks,
            recommended_investments=investments,
            estimated_improvement_months=assessment.estimated_improvement_months,
        )

    def track_progress(
        self,
        current: MaturityAssessment,
        previous: MaturityAssessment,
    ) -> ProgressReport:
        """Track improvement over time between two assessments."""
        delta = current.overall_score - previous.overall_score
        level_changed = current.overall_level != previous.overall_level

        prev_map = {ds.dimension: ds.score for ds in previous.dimensions}
        improved: list[str] = []
        regressed: list[str] = []
        unchanged: list[str] = []

        for ds in current.dimensions:
            prev_score = prev_map.get(ds.dimension, 0.0)
            if ds.score > prev_score + 0.5:
                improved.append(ds.dimension.value)
            elif ds.score < prev_score - 0.5:
                regressed.append(ds.dimension.value)
            else:
                unchanged.append(ds.dimension.value)

        return ProgressReport(
            score_delta=round(delta, 1),
            level_changed=level_changed,
            previous_level=previous.overall_level,
            current_level=current.overall_level,
            improved_dimensions=improved,
            regressed_dimensions=regressed,
            unchanged_dimensions=unchanged,
        )

    # -----------------------------------------------------------------------
    # Dimension scorers (private)
    # -----------------------------------------------------------------------

    def _score_culture(
        self, graph: InfraGraph, config: ChaosConfig
    ) -> DimensionScore:
        """Score the 'culture' dimension.

        Factors: incident_learning_process, team_training_hours,
        gameday_practice, team config on graph components.
        """
        score = 0.0
        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if config.incident_learning_process:
            score += 25.0
            evidence.append("Incident learning process in place")
        else:
            gaps.append("No incident learning process")
            actions.append("Establish a blameless post-incident review process")

        training = min(config.team_training_hours_per_quarter, 20.0)
        training_score = (training / 20.0) * 25.0
        score += training_score
        if training >= 10:
            evidence.append(f"Team training: {config.team_training_hours_per_quarter}h/quarter")
        else:
            gaps.append(f"Low training hours ({config.team_training_hours_per_quarter}h/quarter)")
            actions.append("Increase chaos engineering training to 10+ hours/quarter")

        if config.has_gameday_practice:
            score += 15.0
            evidence.append("Gameday practice established")
        else:
            gaps.append("No gameday practice")
            actions.append("Start regular gameday exercises")

        components = list(graph.components.values())
        if components:
            avg_runbook = sum(c.team.runbook_coverage_percent for c in components) / len(components)
            runbook_score = min(35.0, (avg_runbook / 100.0) * 35.0)
            score += runbook_score
            if avg_runbook >= 60:
                evidence.append(f"Average runbook coverage: {avg_runbook:.0f}%")
            else:
                gaps.append(f"Low runbook coverage ({avg_runbook:.0f}%)")
                actions.append("Improve runbook coverage to 60%+")
        else:
            gaps.append("No components defined for team analysis")
            actions.append("Define infrastructure components")

        score = min(100.0, max(0.0, score))
        level = _score_to_level(score)
        return DimensionScore(
            dimension=MaturityDimension.culture,
            score=round(score, 1),
            level=level,
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _score_process(
        self, graph: InfraGraph, config: ChaosConfig
    ) -> DimensionScore:
        """Score the 'process' dimension.

        Factors: hypothesis_driven, incident_learning, runbook coverage,
        gameday frequency.
        """
        score = 0.0
        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if config.has_hypothesis_driven_experiments:
            score += 30.0
            evidence.append("Hypothesis-driven experiments in use")
        else:
            gaps.append("No hypothesis-driven experiments")
            actions.append("Adopt hypothesis-driven chaos experiment methodology")

        if config.incident_learning_process:
            score += 20.0
            evidence.append("Incident learning process defined")
        else:
            gaps.append("No incident learning process")
            actions.append("Implement post-incident review workflow")

        freq = min(config.gameday_frequency_per_quarter, 4)
        freq_score = (freq / 4.0) * 25.0
        score += freq_score
        if freq >= 2:
            evidence.append(f"Gameday frequency: {config.gameday_frequency_per_quarter}/quarter")
        else:
            gaps.append(f"Low gameday frequency ({config.gameday_frequency_per_quarter}/quarter)")
            actions.append("Increase gameday frequency to at least 2 per quarter")

        runbook_score = min(25.0, (config.runbook_coverage_percent / 100.0) * 25.0)
        score += runbook_score
        if config.runbook_coverage_percent >= 60:
            evidence.append(f"Runbook coverage: {config.runbook_coverage_percent}%")
        else:
            gaps.append(f"Low runbook coverage ({config.runbook_coverage_percent}%)")
            actions.append("Expand runbook coverage to 60%+")

        score = min(100.0, max(0.0, score))
        level = _score_to_level(score)
        return DimensionScore(
            dimension=MaturityDimension.process,
            score=round(score, 1),
            level=level,
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _score_tooling(
        self, graph: InfraGraph, config: ChaosConfig
    ) -> DimensionScore:
        """Score the 'tooling' dimension.

        Factors: has_automated_chaos, chaos_in_ci_cd, blast_radius_controls,
        circuit breakers & retry strategies on edges.
        """
        score = 0.0
        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if config.has_automated_chaos:
            score += 25.0
            evidence.append("Automated chaos tooling deployed")
        else:
            gaps.append("No automated chaos tooling")
            actions.append("Deploy chaos engineering tooling (e.g. Litmus, Gremlin)")

        if config.chaos_in_ci_cd:
            score += 25.0
            evidence.append("Chaos tests integrated in CI/CD")
        else:
            gaps.append("Chaos not integrated in CI/CD")
            actions.append("Integrate chaos experiments into CI/CD pipeline")

        if config.blast_radius_controls:
            score += 15.0
            evidence.append("Blast radius controls configured")
        else:
            gaps.append("No blast radius controls in tooling")
            actions.append("Add blast radius controls to chaos experiments")

        edges = graph.all_dependency_edges()
        if edges:
            cb_count = sum(1 for e in edges if e.circuit_breaker.enabled)
            retry_count = sum(1 for e in edges if e.retry_strategy.enabled)
            total = len(edges)
            ratio = (cb_count + retry_count) / (total * 2)
            infra_score = ratio * 35.0
            score += infra_score
            if ratio >= 0.5:
                evidence.append(f"CB: {cb_count}/{total}, Retry: {retry_count}/{total}")
            else:
                gaps.append(f"Low CB/retry coverage ({cb_count}/{total} CB, {retry_count}/{total} retry)")
                actions.append("Enable circuit breakers and retry strategies on dependency edges")
        else:
            gaps.append("No dependency edges to assess tooling coverage")
            actions.append("Define dependency edges with resilience patterns")

        score = min(100.0, max(0.0, score))
        level = _score_to_level(score)
        return DimensionScore(
            dimension=MaturityDimension.tooling,
            score=round(score, 1),
            level=level,
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _score_automation(
        self, graph: InfraGraph, config: ChaosConfig
    ) -> DimensionScore:
        """Score the 'automation' dimension.

        Factors: has_automated_chaos, chaos_in_ci_cd, autoscaling/failover
        on components, team automation_percent.
        """
        score = 0.0
        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if config.has_automated_chaos:
            score += 20.0
            evidence.append("Automated chaos experiments")
        else:
            gaps.append("No automated chaos")
            actions.append("Automate chaos experiment execution")

        if config.chaos_in_ci_cd:
            score += 20.0
            evidence.append("Chaos in CI/CD pipeline")
        else:
            gaps.append("No chaos in CI/CD")
            actions.append("Add chaos experiments to CI/CD")

        components = list(graph.components.values())
        if components:
            total = len(components)
            as_count = sum(1 for c in components if c.autoscaling.enabled)
            fo_count = sum(1 for c in components if c.failover.enabled)
            combined = (as_count + fo_count) / (total * 2)
            infra_score = combined * 30.0
            score += infra_score
            if combined >= 0.5:
                evidence.append(f"Autoscaling: {as_count}/{total}, Failover: {fo_count}/{total}")
            else:
                gaps.append(f"Low autoscaling/failover coverage")
                actions.append("Enable autoscaling and failover on more components")

            avg_auto = sum(c.team.automation_percent for c in components) / total
            team_score = min(30.0, (avg_auto / 100.0) * 30.0)
            score += team_score
            if avg_auto >= 50:
                evidence.append(f"Average automation: {avg_auto:.0f}%")
            else:
                gaps.append(f"Low team automation ({avg_auto:.0f}%)")
                actions.append("Increase team automation to 50%+")
        else:
            gaps.append("No components to assess automation")
            actions.append("Define infrastructure components")

        score = min(100.0, max(0.0, score))
        level = _score_to_level(score)
        return DimensionScore(
            dimension=MaturityDimension.automation,
            score=round(score, 1),
            level=level,
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _score_observability(
        self, graph: InfraGraph, config: ChaosConfig
    ) -> DimensionScore:
        """Score the 'observability' dimension.

        Factors: observability_coverage_percent from config, log/IDS/healthcheck
        on graph components.
        """
        score = 0.0
        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        obs_pct = min(config.observability_coverage_percent, 100.0)
        config_score = (obs_pct / 100.0) * 40.0
        score += config_score
        if obs_pct >= 70:
            evidence.append(f"Observability coverage: {obs_pct}%")
        else:
            gaps.append(f"Low observability coverage ({obs_pct}%)")
            actions.append("Increase observability coverage to 70%+")

        components = list(graph.components.values())
        if components:
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

            log_score = log_ratio * 20.0
            ids_score = ids_ratio * 20.0
            hc_score = hc_ratio * 20.0
            score += log_score + ids_score + hc_score

            if log_ratio >= 0.7:
                evidence.append(f"Logging: {log_count}/{total}")
            else:
                gaps.append(f"Low logging coverage ({log_count}/{total})")
                actions.append("Enable logging on all components")
            if ids_ratio >= 0.5:
                evidence.append(f"IDS monitoring: {ids_count}/{total}")
            else:
                gaps.append(f"Low IDS coverage ({ids_count}/{total})")
                actions.append("Enable IDS monitoring on critical components")
            if hc_ratio >= 0.5:
                evidence.append(f"Health checks: {hc_count}/{total}")
            else:
                gaps.append(f"Low health check coverage ({hc_count}/{total})")
                actions.append("Configure health checks on all components")
        else:
            gaps.append("No components to assess observability")
            actions.append("Define infrastructure components")

        score = min(100.0, max(0.0, score))
        level = _score_to_level(score)
        return DimensionScore(
            dimension=MaturityDimension.observability,
            score=round(score, 1),
            level=level,
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _score_blast_radius(
        self, graph: InfraGraph, config: ChaosConfig
    ) -> DimensionScore:
        """Score the 'blast_radius_control' dimension.

        Factors: blast_radius_controls config, circuit breakers on edges,
        replicas, network segmentation.
        """
        score = 0.0
        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if config.blast_radius_controls:
            score += 25.0
            evidence.append("Blast radius controls in chaos config")
        else:
            gaps.append("No blast radius controls configured")
            actions.append("Configure blast radius controls for chaos experiments")

        components = list(graph.components.values())
        edges = graph.all_dependency_edges()

        if components:
            total = len(components)
            replica_count = sum(1 for c in components if c.replicas > 1)
            seg_count = sum(1 for c in components if c.security.network_segmented)
            rep_ratio = replica_count / total
            seg_ratio = seg_count / total

            rep_score = rep_ratio * 25.0
            seg_score = seg_ratio * 25.0
            score += rep_score + seg_score

            if rep_ratio >= 0.5:
                evidence.append(f"Replicas > 1: {replica_count}/{total}")
            else:
                gaps.append(f"Low replica coverage ({replica_count}/{total})")
                actions.append("Add replicas to critical components")
            if seg_ratio >= 0.5:
                evidence.append(f"Network segmented: {seg_count}/{total}")
            else:
                gaps.append(f"Low network segmentation ({seg_count}/{total})")
                actions.append("Implement network segmentation")
        else:
            gaps.append("No components to assess blast radius")
            actions.append("Define infrastructure components")

        if edges:
            cb_count = sum(1 for e in edges if e.circuit_breaker.enabled)
            cb_ratio = cb_count / len(edges)
            cb_score = cb_ratio * 25.0
            score += cb_score
            if cb_ratio >= 0.5:
                evidence.append(f"Circuit breakers: {cb_count}/{len(edges)}")
            else:
                gaps.append(f"Low circuit breaker coverage ({cb_count}/{len(edges)})")
                actions.append("Enable circuit breakers on all dependency edges")
        else:
            if components:
                gaps.append("No dependency edges for circuit breaker analysis")
                actions.append("Define dependency edges with circuit breakers")

        score = min(100.0, max(0.0, score))
        level = _score_to_level(score)
        return DimensionScore(
            dimension=MaturityDimension.blast_radius_control,
            score=round(score, 1),
            level=level,
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _score_hypothesis(
        self, graph: InfraGraph, config: ChaosConfig
    ) -> DimensionScore:
        """Score the 'hypothesis_driven' dimension.

        Factors: has_hypothesis_driven_experiments, SLO targets on components,
        incident_learning_process, observability_coverage.
        """
        score = 0.0
        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if config.has_hypothesis_driven_experiments:
            score += 35.0
            evidence.append("Hypothesis-driven experiments adopted")
        else:
            gaps.append("No hypothesis-driven experiments")
            actions.append("Define hypotheses before running chaos experiments")

        if config.incident_learning_process:
            score += 15.0
            evidence.append("Incident learning feeds experiment design")
        else:
            gaps.append("No incident learning process for hypothesis refinement")
            actions.append("Use incident data to inform chaos hypotheses")

        obs_contrib = min(15.0, (config.observability_coverage_percent / 100.0) * 15.0)
        score += obs_contrib
        if config.observability_coverage_percent >= 60:
            evidence.append(f"Observability supports hypothesis validation ({config.observability_coverage_percent}%)")
        else:
            gaps.append("Insufficient observability for hypothesis validation")
            actions.append("Improve observability to validate experiment hypotheses")

        components = list(graph.components.values())
        if components:
            total = len(components)
            slo_count = sum(1 for c in components if len(c.slo_targets) > 0)
            slo_ratio = slo_count / total
            slo_score = slo_ratio * 35.0
            score += slo_score
            if slo_ratio >= 0.5:
                evidence.append(f"SLO targets defined: {slo_count}/{total}")
            else:
                gaps.append(f"Low SLO coverage ({slo_count}/{total})")
                actions.append("Define SLO targets for steady-state hypothesis validation")
        else:
            gaps.append("No components with SLO targets")
            actions.append("Define components and SLO targets")

        score = min(100.0, max(0.0, score))
        level = _score_to_level(score)
        return DimensionScore(
            dimension=MaturityDimension.hypothesis_driven,
            score=round(score, 1),
            level=level,
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    def _score_gameday(
        self, graph: InfraGraph, config: ChaosConfig
    ) -> DimensionScore:
        """Score the 'gameday_practice' dimension.

        Factors: has_gameday_practice, gameday_frequency, team training,
        runbook coverage, failover/autoscaling infrastructure readiness.
        """
        score = 0.0
        evidence: list[str] = []
        gaps: list[str] = []
        actions: list[str] = []

        if config.has_gameday_practice:
            score += 25.0
            evidence.append("Gameday practice established")
        else:
            gaps.append("No gameday practice")
            actions.append("Establish regular gameday exercises")

        freq = min(config.gameday_frequency_per_quarter, 4)
        freq_score = (freq / 4.0) * 25.0
        score += freq_score
        if freq >= 2:
            evidence.append(f"Gameday frequency: {config.gameday_frequency_per_quarter}/quarter")
        else:
            gaps.append(f"Low gameday frequency ({config.gameday_frequency_per_quarter}/quarter)")
            actions.append("Schedule at least 2 gamedays per quarter")

        training = min(config.team_training_hours_per_quarter, 20.0)
        training_score = (training / 20.0) * 15.0
        score += training_score
        if training >= 8:
            evidence.append(f"Training: {config.team_training_hours_per_quarter}h/quarter")
        else:
            gaps.append(f"Low training hours ({config.team_training_hours_per_quarter}h)")
            actions.append("Increase team training to 8+ hours/quarter")

        runbook_score = min(15.0, (config.runbook_coverage_percent / 100.0) * 15.0)
        score += runbook_score
        if config.runbook_coverage_percent >= 60:
            evidence.append(f"Runbook coverage: {config.runbook_coverage_percent}%")
        else:
            gaps.append(f"Low runbook coverage ({config.runbook_coverage_percent}%)")
            actions.append("Improve runbook coverage for gameday scenarios")

        components = list(graph.components.values())
        if components:
            total = len(components)
            fo_count = sum(1 for c in components if c.failover.enabled)
            as_count = sum(1 for c in components if c.autoscaling.enabled)
            readiness = (fo_count + as_count) / (total * 2)
            infra_score = readiness * 20.0
            score += infra_score
            if readiness >= 0.5:
                evidence.append(f"Infrastructure readiness: {readiness:.0%}")
            else:
                gaps.append(f"Low infrastructure readiness ({readiness:.0%})")
                actions.append("Improve failover/autoscaling coverage for gamedays")
        else:
            gaps.append("No components to assess gameday readiness")
            actions.append("Define infrastructure components")

        score = min(100.0, max(0.0, score))
        level = _score_to_level(score)
        return DimensionScore(
            dimension=MaturityDimension.gameday_practice,
            score=round(score, 1),
            level=level,
            evidence=evidence,
            gaps=gaps,
            next_level_actions=actions,
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _average_score(dimensions: list[DimensionScore]) -> float:
        if not dimensions:
            return 0.0
        return sum(d.score for d in dimensions) / len(dimensions)

    @staticmethod
    def _find_strengths(dimensions: list[DimensionScore]) -> list[str]:
        return [
            ds.dimension.value
            for ds in dimensions
            if ds.score >= 60.0
        ]

    @staticmethod
    def _find_weaknesses(dimensions: list[DimensionScore]) -> list[str]:
        return [
            ds.dimension.value
            for ds in dimensions
            if ds.score < 30.0
        ]

    @staticmethod
    def _estimate_percentile(score: float) -> float:
        """Rough percentile estimate: linear mapping 0-100 -> 1-99."""
        return min(99.0, max(1.0, score * 0.98 + 1.0))

    @staticmethod
    def _estimate_months(level: MaturityLevel) -> int:
        """Estimate months to reach the next maturity level."""
        months_map = {
            MaturityLevel.level_0_initial: 3,
            MaturityLevel.level_1_planned: 4,
            MaturityLevel.level_2_practiced: 6,
            MaturityLevel.level_3_managed: 9,
            MaturityLevel.level_4_optimized: 0,
        }
        return months_map.get(level, 6)
