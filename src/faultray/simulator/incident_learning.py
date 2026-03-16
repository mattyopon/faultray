"""Incident Learning Engine.

Converts post-mortem/incident reports into reproducible chaos simulations.
Extracts failure patterns from past incidents and creates automated test
scenarios to verify that fixes actually work. Transforms organizational
knowledge from "we learned from this incident" into "we continuously verify
we won't repeat this incident."
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class IncidentSeverity(str, Enum):
    """Incident severity levels."""

    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


class IncidentCategory(str, Enum):
    """Incident failure category."""

    CASCADE_FAILURE = "CASCADE_FAILURE"
    CAPACITY_EXHAUSTION = "CAPACITY_EXHAUSTION"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    CONFIG_ERROR = "CONFIG_ERROR"
    DEPLOYMENT_FAILURE = "DEPLOYMENT_FAILURE"
    SECURITY_BREACH = "SECURITY_BREACH"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    NETWORK_PARTITION = "NETWORK_PARTITION"


class IncidentRecord(BaseModel):
    """A past incident report."""

    incident_id: str
    title: str
    severity: IncidentSeverity
    category: IncidentCategory
    root_cause_component: str
    affected_components: list[str] = Field(default_factory=list)
    duration_minutes: float = 0.0
    detection_time_minutes: float = 0.0
    mitigation_steps: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    lessons_learned: list[str] = Field(default_factory=list)


class ChaosScenarioTemplate(BaseModel):
    """A chaos scenario derived from an incident."""

    scenario_id: str
    name: str
    description: str
    source_incident_id: str
    target_components: list[str] = Field(default_factory=list)
    failure_sequence: list[dict] = Field(default_factory=list)
    expected_detection_time_minutes: float = 0.0
    expected_recovery_time_minutes: float = 0.0
    validation_criteria: list[str] = Field(default_factory=list)


class LearningInsight(BaseModel):
    """A pattern extracted from multiple incidents."""

    pattern: str
    frequency: int = 0
    affected_categories: list[IncidentCategory] = Field(default_factory=list)
    risk_score: float = 0.0
    recommendation: str = ""


class IncidentLearningReport(BaseModel):
    """Full incident learning analysis report."""

    total_incidents: int = 0
    scenarios_generated: int = 0
    templates: list[ChaosScenarioTemplate] = Field(default_factory=list)
    insights: list[LearningInsight] = Field(default_factory=list)
    repeat_risk_score: float = 0.0
    coverage_by_category: dict[str, float] = Field(default_factory=dict)


# Severity weights used for risk scoring
_SEVERITY_WEIGHT: dict[IncidentSeverity, float] = {
    IncidentSeverity.SEV1: 1.0,
    IncidentSeverity.SEV2: 0.7,
    IncidentSeverity.SEV3: 0.4,
    IncidentSeverity.SEV4: 0.2,
}

# Category-specific failure sequence templates
_CATEGORY_FAILURE_STEPS: dict[IncidentCategory, list[dict]] = {
    IncidentCategory.CASCADE_FAILURE: [
        {"action": "inject_latency", "target": "{component}", "params": {"ms": 5000}},
        {"action": "observe_cascade", "target": "{component}", "params": {}},
    ],
    IncidentCategory.CAPACITY_EXHAUSTION: [
        {"action": "exhaust_resource", "target": "{component}", "params": {"cpu_percent": 95}},
    ],
    IncidentCategory.DEPENDENCY_FAILURE: [
        {"action": "kill_dependency", "target": "{component}", "params": {}},
    ],
    IncidentCategory.CONFIG_ERROR: [
        {"action": "inject_bad_config", "target": "{component}", "params": {}},
    ],
    IncidentCategory.DEPLOYMENT_FAILURE: [
        {"action": "simulate_bad_deploy", "target": "{component}", "params": {}},
    ],
    IncidentCategory.SECURITY_BREACH: [
        {"action": "simulate_breach_attempt", "target": "{component}", "params": {}},
    ],
    IncidentCategory.DATA_CORRUPTION: [
        {"action": "corrupt_data_store", "target": "{component}", "params": {}},
    ],
    IncidentCategory.NETWORK_PARTITION: [
        {"action": "partition_network", "target": "{component}", "params": {}},
    ],
}


class IncidentLearningEngine:
    """Converts incident history into chaos engineering scenarios.

    Analyses past incidents, extracts failure patterns, and generates
    reproducible chaos simulation templates so organisations can continuously
    verify they will not repeat the same failures.
    """

    def __init__(self) -> None:
        self._incidents: list[IncidentRecord] = []
        self._scenarios: list[ChaosScenarioTemplate] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_incident(self, record: IncidentRecord) -> None:
        """Register a past incident."""
        self._incidents.append(record)

    def extract_patterns(self) -> list[LearningInsight]:
        """Find recurring patterns across all registered incidents."""
        if not self._incidents:
            return []

        insights: list[LearningInsight] = []

        # Pattern 1: repeated categories
        cat_counter: Counter[IncidentCategory] = Counter(i.category for i in self._incidents)
        for cat, freq in cat_counter.most_common():
            if freq >= 2:
                severity_scores = [
                    _SEVERITY_WEIGHT[i.severity]
                    for i in self._incidents
                    if i.category == cat
                ]
                risk = min(1.0, sum(severity_scores) / max(len(severity_scores), 1) * (freq / len(self._incidents)))
                insights.append(LearningInsight(
                    pattern=f"Recurring {cat.value} incidents ({freq} occurrences)",
                    frequency=freq,
                    affected_categories=[cat],
                    risk_score=round(risk, 4),
                    recommendation=f"Implement automated chaos tests for {cat.value} scenarios",
                ))

        # Pattern 2: repeated root cause components
        comp_counter: Counter[str] = Counter(i.root_cause_component for i in self._incidents)
        for comp, freq in comp_counter.most_common():
            if freq >= 2:
                cats = list({i.category for i in self._incidents if i.root_cause_component == comp})
                risk = min(1.0, freq / len(self._incidents))
                insights.append(LearningInsight(
                    pattern=f"Component '{comp}' is a repeated root cause ({freq} incidents)",
                    frequency=freq,
                    affected_categories=sorted(cats, key=lambda c: c.value),
                    risk_score=round(risk, 4),
                    recommendation=f"Prioritise resilience hardening for '{comp}'",
                ))

        # Pattern 3: slow detection
        slow = [i for i in self._incidents if i.detection_time_minutes > 15]
        if len(slow) >= 1:
            cats = list({i.category for i in slow})
            risk = min(1.0, len(slow) / len(self._incidents))
            insights.append(LearningInsight(
                pattern=f"Slow detection (>15 min) in {len(slow)} incident(s)",
                frequency=len(slow),
                affected_categories=sorted(cats, key=lambda c: c.value),
                risk_score=round(risk, 4),
                recommendation="Improve monitoring and alerting to reduce detection time",
            ))

        return insights

    def generate_scenario(self, incident: IncidentRecord) -> ChaosScenarioTemplate:
        """Create a chaos scenario template from a single incident."""
        sid = hashlib.sha256(incident.incident_id.encode()).hexdigest()[:12]

        steps = []
        for step_template in _CATEGORY_FAILURE_STEPS.get(incident.category, []):
            step = {
                k: (v.replace("{component}", incident.root_cause_component) if isinstance(v, str) else v)
                for k, v in step_template.items()
            }
            steps.append(step)

        targets = list(dict.fromkeys(
            [incident.root_cause_component] + incident.affected_components
        ))

        detection = max(1.0, incident.detection_time_minutes * 0.5)
        recovery = max(1.0, incident.duration_minutes * 0.5)

        criteria: list[str] = [
            f"Detection within {detection:.1f} minutes",
            f"Recovery within {recovery:.1f} minutes",
        ]
        for step in incident.mitigation_steps:
            criteria.append(f"Mitigation applied: {step}")

        scenario = ChaosScenarioTemplate(
            scenario_id=f"chaos-{sid}",
            name=f"Replay: {incident.title}",
            description=(
                f"Chaos scenario derived from incident {incident.incident_id} "
                f"({incident.category.value}). Root cause: {incident.root_cause_component}."
            ),
            source_incident_id=incident.incident_id,
            target_components=targets,
            failure_sequence=steps,
            expected_detection_time_minutes=round(detection, 1),
            expected_recovery_time_minutes=round(recovery, 1),
            validation_criteria=criteria,
        )
        return scenario

    def generate_all_scenarios(self) -> list[ChaosScenarioTemplate]:
        """Generate chaos scenarios for every registered incident."""
        self._scenarios = [self.generate_scenario(inc) for inc in self._incidents]
        return list(self._scenarios)

    def assess_repeat_risk(self) -> float:
        """Estimate the probability of similar incidents recurring.

        Returns a float between 0 and 1.  Higher means greater repeat risk.
        """
        if not self._incidents:
            return 0.0

        cat_counter: Counter[IncidentCategory] = Counter(i.category for i in self._incidents)
        repeat_cats = sum(1 for f in cat_counter.values() if f >= 2)

        severity_factor = sum(
            _SEVERITY_WEIGHT[i.severity] for i in self._incidents
        ) / len(self._incidents)

        ratio = repeat_cats / max(len(cat_counter), 1)
        risk = min(1.0, (ratio * 0.6 + severity_factor * 0.4))
        return round(risk, 4)

    def coverage_analysis(self) -> dict[str, float]:
        """Compute how well past incident categories are covered by scenarios.

        Returns a dict mapping category name to a coverage ratio (0.0 – 1.0).
        """
        cat_counts: Counter[IncidentCategory] = Counter(i.category for i in self._incidents)
        if not cat_counts:
            return {}

        covered_cats: Counter[IncidentCategory] = Counter()
        for s in self._scenarios:
            for inc in self._incidents:
                if inc.incident_id == s.source_incident_id:
                    covered_cats[inc.category] += 1

        result: dict[str, float] = {}
        for cat, total in cat_counts.items():
            covered = covered_cats.get(cat, 0)
            result[cat.value] = round(min(1.0, covered / total), 4)
        return result

    def generate_report(self) -> IncidentLearningReport:
        """Produce a full incident learning report."""
        templates = self.generate_all_scenarios()
        insights = self.extract_patterns()
        risk = self.assess_repeat_risk()
        coverage = self.coverage_analysis()

        return IncidentLearningReport(
            total_incidents=len(self._incidents),
            scenarios_generated=len(templates),
            templates=templates,
            insights=insights,
            repeat_risk_score=risk,
            coverage_by_category=coverage,
        )
