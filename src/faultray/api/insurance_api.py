# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Cyber Insurance Scoring API - compute insurance risk scores for infrastructure.

Provides endpoints for evaluating infrastructure resilience from an insurance
underwriting perspective. Combines resilience, security, recovery, and
operational scores into a single overall risk grade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

insurance_router = APIRouter(prefix="/api/insurance", tags=["insurance"])


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class InsuranceScore:
    """Full insurance scoring result."""

    overall_score: int  # 0-100
    risk_grade: str  # A+/A/B+/B/C/D/F
    resilience_score: float
    security_score: float
    recovery_score: float
    operational_score: float
    annual_expected_loss: float
    max_single_incident_cost: float
    risk_factors: list[dict[str, Any]] = field(default_factory=list)
    mitigation_recommendations: list[dict[str, Any]] = field(default_factory=list)
    compliance_summary: dict[str, Any] = field(default_factory=dict)


class ScoreRequest(BaseModel):
    """Request body for the /score endpoint."""

    yaml_content: str


# ---------------------------------------------------------------------------
# Grade mapping
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [
    (90, "A+"),
    (80, "A"),
    (70, "B+"),
    (60, "B"),
    (50, "C"),
    (40, "D"),
]


def _score_to_grade(score: int) -> str:
    """Map a 0-100 score to a letter grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------


def compute_insurance_score(graph: InfraGraph) -> InsuranceScore:
    """Compute a comprehensive insurance risk score for the given infrastructure.

    The overall score is a weighted average:
    - Resilience:   25%
    - Security:     30%
    - Recovery:     25%
    - Operational:  20%

    Returns:
        InsuranceScore with all sub-scores and recommendations.
    """
    if not graph.components:
        return InsuranceScore(
            overall_score=0,
            risk_grade="F",
            resilience_score=0.0,
            security_score=0.0,
            recovery_score=0.0,
            operational_score=0.0,
            annual_expected_loss=0.0,
            max_single_incident_cost=0.0,
            risk_factors=[{"factor": "No components defined", "severity": "critical"}],
            mitigation_recommendations=[],
            compliance_summary={"status": "no_data"},
        )

    # --- 1. Resilience score (from v2) ---
    v2 = graph.resilience_score_v2()
    resilience_score = v2["score"]

    # --- 2. Security score (from SecurityProfile on each component) ---
    security_score = _compute_security_score(graph)

    # --- 3. Recovery score (from DR / failover / backup analysis) ---
    recovery_score = _compute_recovery_score(graph)

    # --- 4. Operational score (from operational profiles) ---
    operational_score = _compute_operational_score(graph)

    # --- Weighted average ---
    overall_float = (
        resilience_score * 0.25
        + security_score * 0.30
        + recovery_score * 0.25
        + operational_score * 0.20
    )
    overall = int(round(overall_float))
    overall = max(0, min(100, overall))

    risk_grade = _score_to_grade(overall)

    # --- Risk factors ---
    risk_factors = _identify_risk_factors(graph, resilience_score, security_score, recovery_score)

    # --- Mitigation recommendations ---
    mitigation_recs = _generate_mitigation_recommendations(
        graph, resilience_score, security_score, recovery_score, operational_score,
    )

    # --- Annual expected loss estimate ---
    annual_expected_loss = _estimate_annual_loss(graph, overall)

    # --- Max single incident cost ---
    max_single_incident = _estimate_max_incident_cost(graph)

    # --- Compliance summary ---
    compliance_summary = _compute_compliance_summary(graph)

    return InsuranceScore(
        overall_score=overall,
        risk_grade=risk_grade,
        resilience_score=round(resilience_score, 1),
        security_score=round(security_score, 1),
        recovery_score=round(recovery_score, 1),
        operational_score=round(operational_score, 1),
        annual_expected_loss=round(annual_expected_loss, 2),
        max_single_incident_cost=round(max_single_incident, 2),
        risk_factors=risk_factors,
        mitigation_recommendations=mitigation_recs,
        compliance_summary=compliance_summary,
    )


# ---------------------------------------------------------------------------
# Sub-score computation helpers
# ---------------------------------------------------------------------------


def _compute_security_score(graph: InfraGraph) -> float:
    """Compute security score (0-100) from SecurityProfile on each component."""
    if not graph.components:
        return 0.0

    component_scores: list[float] = []
    for comp in graph.components.values():
        sec = comp.security
        checks = [
            sec.encryption_at_rest,
            sec.encryption_in_transit,
            sec.waf_protected,
            sec.rate_limiting,
            sec.auth_required,
            sec.network_segmented,
            sec.backup_enabled,
            sec.log_enabled,
            sec.ids_monitored,
        ]
        passed = sum(1 for c in checks if c)
        total = len(checks)
        component_scores.append((passed / total) * 100.0 if total > 0 else 0.0)

    return sum(component_scores) / len(component_scores)


def _compute_recovery_score(graph: InfraGraph) -> float:
    """Compute recovery score (0-100) from failover/DR/backup settings."""
    if not graph.components:
        return 0.0

    scores: list[float] = []
    for comp in graph.components.values():
        comp_score = 0.0

        # Failover capability (40 points)
        if comp.failover.enabled:
            comp_score += 40.0

        # Backup enabled (30 points)
        if comp.security.backup_enabled:
            comp_score += 30.0
            # Bonus for frequent backups (< 4 hours)
            if comp.security.backup_frequency_hours <= 4.0:
                comp_score += 10.0

        # Multi-replica (20 points)
        if comp.replicas >= 2:
            comp_score += 20.0

        scores.append(min(100.0, comp_score))

    return sum(scores) / len(scores)


def _compute_operational_score(graph: InfraGraph) -> float:
    """Compute operational score (0-100) from operational profiles.

    Considers:
    - MTBF (higher is better)
    - MTTR (lower is better)
    - Autoscaling presence
    - Circuit breaker coverage
    """
    if not graph.components:
        return 0.0

    scores: list[float] = []
    for comp in graph.components.values():
        comp_score = 50.0  # baseline

        op = comp.operational_profile

        # MTBF bonus: > 720h (30 days) is excellent
        if op.mtbf_hours >= 720:
            comp_score += 20.0
        elif op.mtbf_hours >= 168:  # 1 week
            comp_score += 10.0
        elif op.mtbf_hours > 0:
            comp_score += 5.0

        # MTTR penalty: lower is better
        if op.mttr_minutes <= 5:
            comp_score += 15.0
        elif op.mttr_minutes <= 15:
            comp_score += 10.0
        elif op.mttr_minutes <= 30:
            comp_score += 5.0
        else:
            comp_score -= 5.0

        # Autoscaling bonus
        if comp.autoscaling.enabled:
            comp_score += 15.0

        scores.append(max(0.0, min(100.0, comp_score)))

    # Circuit breaker coverage bonus on edges
    all_edges = graph.all_dependency_edges()
    if all_edges:
        cb_count = sum(1 for e in all_edges if e.circuit_breaker.enabled)
        cb_ratio = cb_count / len(all_edges)
        cb_bonus = cb_ratio * 10.0  # up to 10 points
        avg = sum(scores) / len(scores)
        avg = min(100.0, avg + cb_bonus)
        return avg

    return sum(scores) / len(scores) if scores else 0.0


def _identify_risk_factors(
    graph: InfraGraph,
    resilience: float,
    security: float,
    recovery: float,
) -> list[dict[str, Any]]:
    """Identify key risk factors for the insurance report."""
    factors: list[dict[str, Any]] = []

    # SPOFs
    spof_count = 0
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0:
            spof_count += 1
    if spof_count > 0:
        factors.append({
            "factor": f"{spof_count} single point(s) of failure detected",
            "severity": "critical" if spof_count > 2 else "high",
            "category": "resilience",
        })

    # Low security
    if security < 50:
        factors.append({
            "factor": f"Security score below threshold ({security:.0f}/100)",
            "severity": "critical",
            "category": "security",
        })

    # Low recovery
    if recovery < 50:
        factors.append({
            "factor": f"Recovery capabilities insufficient ({recovery:.0f}/100)",
            "severity": "high",
            "category": "recovery",
        })

    # No circuit breakers
    edges = graph.all_dependency_edges()
    if edges:
        cb_count = sum(1 for e in edges if e.circuit_breaker.enabled)
        if cb_count == 0:
            factors.append({
                "factor": "No circuit breakers configured on any dependency",
                "severity": "high",
                "category": "resilience",
            })

    # No encryption
    no_encryption = sum(
        1 for c in graph.components.values()
        if not c.security.encryption_at_rest and not c.security.encryption_in_transit
    )
    if no_encryption > 0:
        factors.append({
            "factor": f"{no_encryption} component(s) without any encryption",
            "severity": "high",
            "category": "security",
        })

    return factors


def _generate_mitigation_recommendations(
    graph: InfraGraph,
    resilience: float,
    security: float,
    recovery: float,
    operational: float,
) -> list[dict[str, Any]]:
    """Generate actionable mitigation recommendations."""
    recs: list[dict[str, Any]] = []

    if resilience < 70:
        recs.append({
            "action": "Improve redundancy by adding replicas and failover for critical components",
            "impact": "high",
            "estimated_score_improvement": min(20, 70 - resilience),
        })

    if security < 70:
        recs.append({
            "action": "Enable encryption at rest and in transit for all components",
            "impact": "high",
            "estimated_score_improvement": min(25, 70 - security),
        })

    if recovery < 70:
        recs.append({
            "action": "Configure automated failover and regular backups",
            "impact": "high",
            "estimated_score_improvement": min(20, 70 - recovery),
        })

    if operational < 70:
        recs.append({
            "action": "Reduce MTTR through autoscaling and circuit breakers",
            "impact": "medium",
            "estimated_score_improvement": min(15, 70 - operational),
        })

    # Component-specific recommendations
    for comp in graph.components.values():
        if comp.replicas <= 1 and len(graph.get_dependents(comp.id)) > 0:
            recs.append({
                "action": f"Add replicas for '{comp.id}' (currently single instance with dependents)",
                "impact": "critical",
                "estimated_score_improvement": 5,
            })

    return recs


def _estimate_annual_loss(graph: InfraGraph, overall_score: int) -> float:
    """Estimate annual expected loss based on component costs and risk level.

    Uses a simplified model:
    - Base loss = sum of component hourly costs * risk factor * 8760 hours
    - Risk factor inversely proportional to overall score
    """
    total_hourly_cost = sum(
        c.cost_profile.hourly_infra_cost for c in graph.components.values()
    )
    total_revenue_per_minute = sum(
        c.cost_profile.revenue_per_minute for c in graph.components.values()
    )

    # Risk multiplier: perfect score = 0.001 (0.1%), worst = 0.1 (10%)
    max(0.001, (100 - overall_score) / 1000.0)

    # Expected annual downtime hours based on score
    # Score 100 -> 0.5h/year, Score 0 -> 500h/year
    expected_downtime_hours = 0.5 + (100 - overall_score) * 5.0

    infra_loss = total_hourly_cost * expected_downtime_hours
    revenue_loss = total_revenue_per_minute * expected_downtime_hours * 60.0

    return infra_loss + revenue_loss


def _estimate_max_incident_cost(graph: InfraGraph) -> float:
    """Estimate maximum single-incident cost (worst-case scenario).

    Assumes all components fail simultaneously for their MTTR duration.
    """
    total_cost = 0.0
    for comp in graph.components.values():
        mttr_hours = comp.operational_profile.mttr_minutes / 60.0
        hourly = comp.cost_profile.hourly_infra_cost
        revenue = comp.cost_profile.revenue_per_minute * 60.0  # per hour
        recovery = comp.cost_profile.recovery_engineer_cost
        total_cost += (hourly + revenue) * mttr_hours + recovery

    return total_cost


def _compute_compliance_summary(graph: InfraGraph) -> dict[str, Any]:
    """Compute a basic compliance summary for insurance purposes."""
    total = len(graph.components)
    if total == 0:
        return {"status": "no_data", "components_assessed": 0}

    encryption_rest = sum(1 for c in graph.components.values() if c.security.encryption_at_rest)
    encryption_transit = sum(1 for c in graph.components.values() if c.security.encryption_in_transit)
    backup = sum(1 for c in graph.components.values() if c.security.backup_enabled)
    logging_enabled = sum(1 for c in graph.components.values() if c.security.log_enabled)
    auth = sum(1 for c in graph.components.values() if c.security.auth_required)

    return {
        "components_assessed": total,
        "encryption_at_rest_coverage": round(encryption_rest / total * 100, 1),
        "encryption_in_transit_coverage": round(encryption_transit / total * 100, 1),
        "backup_coverage": round(backup / total * 100, 1),
        "logging_coverage": round(logging_enabled / total * 100, 1),
        "auth_coverage": round(auth / total * 100, 1),
    }


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@insurance_router.post("/score")
async def score_infrastructure(request: ScoreRequest) -> JSONResponse:
    """Compute insurance score from YAML infrastructure definition.

    Accepts a YAML string describing infrastructure components and
    dependencies, then returns a comprehensive insurance risk score.
    """
    import tempfile
    from pathlib import Path

    from faultray.model.loader import load_yaml

    try:
        # Write YAML to a temp file and load it
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(request.yaml_content)
            f.flush()
            tmp_path = Path(f.name)

        try:
            graph = load_yaml(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        score = compute_insurance_score(graph)

        return JSONResponse({
            "overall_score": score.overall_score,
            "risk_grade": score.risk_grade,
            "resilience_score": score.resilience_score,
            "security_score": score.security_score,
            "recovery_score": score.recovery_score,
            "operational_score": score.operational_score,
            "annual_expected_loss": score.annual_expected_loss,
            "max_single_incident_cost": score.max_single_incident_cost,
            "risk_factors": score.risk_factors,
            "mitigation_recommendations": score.mitigation_recommendations,
            "compliance_summary": score.compliance_summary,
        })
    except Exception as exc:
        logger.warning("Insurance scoring failed: %s", exc, exc_info=True)
        return JSONResponse(
            {"error": f"Failed to compute insurance score: {exc}"},
            status_code=400,
        )


@insurance_router.get("/benchmark")
async def get_benchmark() -> JSONResponse:
    """Return industry benchmark data for insurance scoring comparison.

    Provides reference scores for different infrastructure maturity levels
    so users can compare their scores against industry standards.
    """
    return JSONResponse({
        "benchmarks": {
            "startup_mvp": {
                "overall_score": 35,
                "risk_grade": "F",
                "description": "Minimal infrastructure, no redundancy or DR",
            },
            "small_business": {
                "overall_score": 55,
                "risk_grade": "C",
                "description": "Basic redundancy, limited security controls",
            },
            "mid_market": {
                "overall_score": 72,
                "risk_grade": "B+",
                "description": "Good redundancy, security baselines, basic DR",
            },
            "enterprise": {
                "overall_score": 85,
                "risk_grade": "A",
                "description": "Full redundancy, comprehensive security, multi-region DR",
            },
            "mission_critical": {
                "overall_score": 95,
                "risk_grade": "A+",
                "description": "Maximum resilience, zero-trust security, active-active multi-region",
            },
        },
        "scoring_methodology": {
            "resilience_weight": 0.25,
            "security_weight": 0.30,
            "recovery_weight": 0.25,
            "operational_weight": 0.20,
        },
        "grade_scale": {
            "A+": "90-100 (Excellent)",
            "A": "80-89 (Very Good)",
            "B+": "70-79 (Good)",
            "B": "60-69 (Acceptable)",
            "C": "50-59 (Below Average)",
            "D": "40-49 (Poor)",
            "F": "0-39 (Critical Risk)",
        },
    })
