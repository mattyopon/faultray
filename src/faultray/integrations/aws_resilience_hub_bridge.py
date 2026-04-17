# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""AWS Resilience Hub Pre-Deploy Bridge — FaultRay as "AWS Resilience Hub for Terraform Plan".

AWS Resilience Hub scores infrastructure resilience but only works AFTER deployment
(against live AWS resources). This bridge positions FaultRay to do the same analysis
BEFORE deployment by analyzing Terraform plans.

Usage:
    bridge = AWSResilienceHubBridge()
    assessment = bridge.from_terraform_plan(plan_json)
    output = bridge.to_resilience_hub_format(assessment)

    # Or compare a pre-deploy prediction against the actual post-deploy Hub assessment
    report = bridge.compare_with_live(assessment, hub_assessment_dict)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DisruptionType(str, Enum):
    """Maps to AWS Resilience Hub disruption categories."""

    INFRASTRUCTURE = "Infrastructure"   # AZ outage / hardware failure
    APPLICATION = "Application"         # Software failure / process crash
    NETWORK = "Network"                 # Connectivity loss / DNS failure
    REGION = "Region"                   # Full region failure


class PolicyStatus(str, Enum):
    """AWS Resilience Hub policy compliance states."""

    MEETS_POLICY = "MeetsPolicy"
    POLICY_BREACHED = "PolicyBreached"
    NOT_ASSESSED = "NotAssessed"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ResiliencyPolicy:
    """Defines the RTO/RPO targets that the application must meet.

    Mirrors the structure of an AWS Resilience Hub ResiliencyPolicy object.
    """

    policy_name: str
    description: str = ""

    # Targets per disruption type (seconds)
    rto_seconds: dict[DisruptionType, int] = field(default_factory=lambda: {
        DisruptionType.INFRASTRUCTURE: 3600,    # 1 hour
        DisruptionType.APPLICATION: 900,        # 15 minutes
        DisruptionType.NETWORK: 1800,           # 30 minutes
        DisruptionType.REGION: 86400,           # 24 hours
    })
    rpo_seconds: dict[DisruptionType, int] = field(default_factory=lambda: {
        DisruptionType.INFRASTRUCTURE: 1800,    # 30 minutes
        DisruptionType.APPLICATION: 300,        # 5 minutes
        DisruptionType.NETWORK: 900,            # 15 minutes
        DisruptionType.REGION: 43200,           # 12 hours
    })

    # FaultRay score threshold that maps to "MeetsPolicy"
    min_score_threshold: float = 60.0


@dataclass
class DisruptionScore:
    """Resilience score for a single disruption type.

    Mirrors AWS Resilience Hub's per-disruption scoring output.
    """

    disruption_type: DisruptionType
    score: float                    # 0.0–100.0 (FaultRay scale)
    estimated_rto_seconds: int      # Estimated Recovery Time Objective
    estimated_rpo_seconds: int      # Estimated Recovery Point Objective
    policy_status: PolicyStatus
    risks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PreDeployAssessment:
    """Pre-deployment resilience assessment — the main output of the bridge.

    This mirrors the structure of an AWS Resilience Hub AppAssessment so that
    it can be consumed by the same tooling / dashboards.
    """

    app_name: str
    plan_source: str                # e.g. "terraform_plan" or "faultray_report"
    overall_score: float            # 0.0–100.0
    overall_policy_status: PolicyStatus
    disruption_scores: list[DisruptionScore] = field(default_factory=list)
    policy: ResiliencyPolicy | None = None
    resource_count: int = 0
    findings: list[str] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    # Raw FaultRay data retained for debugging / comparison
    raw_faultray_score: float = 0.0
    raw_plan_summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComparisonReport:
    """Comparison between a pre-deploy prediction and an actual Resilience Hub result.

    Produced by AWSResilienceHubBridge.compare_with_live().
    """

    pre_deploy_assessment: PreDeployAssessment
    live_hub_assessment: dict[str, Any]

    # Score delta: positive means FaultRay was optimistic, negative means pessimistic
    score_delta: float = 0.0
    live_score: float = 0.0
    pre_deploy_score: float = 0.0

    disruption_deltas: dict[str, float] = field(default_factory=dict)
    prediction_accuracy: float = 0.0    # 0.0–1.0
    policy_status_match: bool = False
    missed_risks: list[str] = field(default_factory=list)
    extra_risks: list[str] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Score mapping helpers
# ---------------------------------------------------------------------------

_SCORE_THRESHOLDS = {
    "meets_policy": 60.0,
    "not_assessed": 0.0,
}

# Per-disruption score weights for FaultRay's overall resilience score
_DISRUPTION_WEIGHTS: dict[DisruptionType, float] = {
    DisruptionType.INFRASTRUCTURE: 0.35,
    DisruptionType.APPLICATION: 0.30,
    DisruptionType.NETWORK: 0.20,
    DisruptionType.REGION: 0.15,
}

# Heuristic modifiers — some disruption types have inherent score penalties
# relative to the overall score when specific risk signals are absent.
_DISRUPTION_PENALTIES: dict[DisruptionType, float] = {
    DisruptionType.INFRASTRUCTURE: 0.0,
    DisruptionType.APPLICATION: -5.0,   # Software failures are often under-engineered
    DisruptionType.NETWORK: -3.0,
    DisruptionType.REGION: -10.0,       # Multi-region is rarely fully configured
}

# Estimated base RTO/RPO constants (seconds) indexed by disruption type
_BASE_RTO: dict[DisruptionType, int] = {
    DisruptionType.INFRASTRUCTURE: 3600,
    DisruptionType.APPLICATION: 600,
    DisruptionType.NETWORK: 1800,
    DisruptionType.REGION: 14400,
}
_BASE_RPO: dict[DisruptionType, int] = {
    DisruptionType.INFRASTRUCTURE: 1800,
    DisruptionType.APPLICATION: 300,
    DisruptionType.NETWORK: 900,
    DisruptionType.REGION: 7200,
}


def _score_to_policy_status(score: float, threshold: float) -> PolicyStatus:
    """Map a FaultRay 0-100 score to a Resilience Hub policy status."""
    if score <= 0.0:
        return PolicyStatus.NOT_ASSESSED
    if score >= threshold:
        return PolicyStatus.MEETS_POLICY
    return PolicyStatus.POLICY_BREACHED


def _estimate_rto_from_score(base_rto: int, score: float) -> int:
    """Estimate RTO in seconds from a resilience score.

    Higher score → faster recovery → lower RTO.
    Uses an inverse linear relationship capped at [base_rto * 0.1, base_rto * 3].
    """
    if score <= 0.0:
        return base_rto * 3
    factor = max(0.1, 2.0 - (score / 100.0) * 1.9)
    return int(base_rto * factor)


def _estimate_rpo_from_score(base_rpo: int, score: float) -> int:
    """Estimate RPO in seconds from a resilience score."""
    if score <= 0.0:
        return base_rpo * 3
    factor = max(0.1, 2.0 - (score / 100.0) * 1.9)
    return int(base_rpo * factor)


def _disruption_score_from_overall(
    overall: float, disruption: DisruptionType
) -> float:
    """Derive a per-disruption score from the overall FaultRay score."""
    base = overall + _DISRUPTION_PENALTIES[disruption]
    return max(0.0, min(100.0, base))


# ---------------------------------------------------------------------------
# Main bridge class
# ---------------------------------------------------------------------------

class AWSResilienceHubBridge:
    """Bridge between FaultRay's analysis and AWS Resilience Hub's output format.

    The bridge provides three conversion paths:

    1. ``from_terraform_plan`` — full analysis pipeline from a raw Terraform plan JSON
    2. ``from_faultray_report`` — convert an already-computed FaultRay report dict
    3. ``to_resilience_hub_format`` — serialize a PreDeployAssessment into the
       Resilience Hub JSON schema
    4. ``compare_with_live`` — diff a pre-deploy prediction against an actual
       Resilience Hub assessment exported from the AWS console
    """

    def __init__(self, policy: ResiliencyPolicy | None = None) -> None:
        self.policy = policy or ResiliencyPolicy(
            policy_name="FaultRay-Default",
            description="Default FaultRay resilience policy",
        )

    # ------------------------------------------------------------------
    # Primary entry points
    # ------------------------------------------------------------------

    def from_terraform_plan(self, plan_json: dict) -> PreDeployAssessment:
        """Analyze a Terraform plan JSON and produce a pre-deploy assessment.

        Internally this uses FaultRay's TerraformFaultRayProvider to parse the
        plan, build before/after InfraGraphs, and run the resilience simulation.
        The resulting score and risk list are then mapped to Resilience Hub format.

        Args:
            plan_json: Parsed Terraform plan JSON dict (from ``terraform show -json``).

        Returns:
            PreDeployAssessment with per-disruption scores and recommendations.
        """
        from faultray.integrations.terraform_provider import TerraformFaultRayProvider

        provider = TerraformFaultRayProvider()
        try:
            analysis = provider.analyze_plan_json(plan_json)
        except Exception as exc:
            logger.warning("Terraform plan analysis failed: %s", exc)
            # Return a not-assessed result rather than crashing
            return self._not_assessed_assessment(
                plan_source="terraform_plan",
                reason=str(exc),
            )

        overall_score = analysis.score_after
        risks = analysis.new_risks + [
            r for r in analysis.changes
            if isinstance(r, dict) and r.get("risk_level", 0) >= 6
        ]
        risk_strings = [
            r if isinstance(r, str) else str(r.get("address", r))
            for r in risks
        ]

        # Build resource count from plan
        resource_count = (
            analysis.resources_added
            + analysis.resources_changed
            + analysis.resources_destroyed
        )

        plan_summary = {
            "resources_added": analysis.resources_added,
            "resources_changed": analysis.resources_changed,
            "resources_destroyed": analysis.resources_destroyed,
            "score_before": analysis.score_before,
            "score_after": analysis.score_after,
            "score_delta": analysis.score_delta,
            "recommendation": analysis.recommendation,
        }

        return self._build_assessment(
            app_name="terraform-app",
            plan_source="terraform_plan",
            overall_score=overall_score,
            risks=risk_strings,
            resource_count=resource_count,
            raw_plan_summary=plan_summary,
        )

    def from_faultray_report(self, report: dict) -> PreDeployAssessment:
        """Convert a FaultRay simulation report dict into a pre-deploy assessment.

        The ``report`` dict is expected to have keys such as:
          - ``score`` (float 0–100)
          - ``critical_findings`` (list of finding dicts with ``name`` and ``severity``)
          - ``warnings`` (list of warning strings)
          - ``app_name`` (str, optional)
          - ``resource_count`` (int, optional)

        Args:
            report: FaultRay simulation report as a plain dict.

        Returns:
            PreDeployAssessment mapped from the report contents.
        """
        overall_score = float(report.get("score", 0.0))
        app_name = str(report.get("app_name", "faultray-app"))
        resource_count = int(report.get("resource_count", 0))

        # Collect risk strings from critical findings + warnings
        risks: list[str] = []
        for finding in report.get("critical_findings", []):
            if isinstance(finding, dict):
                risks.append(finding.get("name", str(finding)))
            else:
                risks.append(str(finding))
        for warning in report.get("warnings", []):
            risks.append(str(warning))

        plan_summary = {k: v for k, v in report.items() if k not in ("critical_findings",)}

        return self._build_assessment(
            app_name=app_name,
            plan_source="faultray_report",
            overall_score=overall_score,
            risks=risks,
            resource_count=resource_count,
            raw_plan_summary=plan_summary,
        )

    def to_resilience_hub_format(self, assessment: PreDeployAssessment) -> dict:
        """Serialize a PreDeployAssessment into an AWS Resilience Hub-compatible dict.

        The output schema mirrors the structure of an ``AppAssessment`` object
        from the AWS Resilience Hub API, enriched with FaultRay-specific metadata
        to make it clear this is a pre-deploy prediction.

        Args:
            assessment: The pre-deploy assessment to serialize.

        Returns:
            Dictionary following Resilience Hub AppAssessment schema conventions.
        """
        disruption_resiliency: dict[str, Any] = {}
        disruption_recommendations: dict[str, list[dict]] = {}

        for ds in assessment.disruption_scores:
            key = ds.disruption_type.value
            disruption_resiliency[key] = {
                "score": round(ds.score, 2),
                "rtoInSecs": ds.estimated_rto_seconds,
                "rpoInSecs": ds.estimated_rpo_seconds,
                "policyStatus": ds.policy_status.value,
                "risks": ds.risks,
            }
            if ds.recommendations:
                disruption_recommendations[key] = [
                    {"recommendation": r, "type": "ALARM"} for r in ds.recommendations
                ]

        policy_dict: dict[str, Any] | None = None
        if assessment.policy:
            p = assessment.policy
            policy_dict = {
                "policyName": p.policy_name,
                "description": p.description,
                "targets": {
                    dt.value: {
                        "rtoInSecs": p.rto_seconds.get(dt, 3600),
                        "rpoInSecs": p.rpo_seconds.get(dt, 1800),
                    }
                    for dt in DisruptionType
                },
            }

        return {
            # Identifies this as a FaultRay pre-deploy prediction
            "source": "FaultRay-PreDeployBridge",
            "assessmentType": "PRE_DEPLOY_PREDICTION",
            "appName": assessment.app_name,
            "planSource": assessment.plan_source,
            # Top-level score mirrors Hub's resiliencyScore field
            "resiliencyScore": round(assessment.overall_score, 2),
            "complianceStatus": assessment.overall_policy_status.value,
            "resourceCount": assessment.resource_count,
            # Per-disruption breakdown — key field for Hub compatibility
            "disruptionResiliency": disruption_resiliency,
            "disruptionRecommendations": disruption_recommendations,
            "findings": assessment.findings,
            "recommendations": assessment.recommendations,
            "policy": policy_dict,
            # FaultRay-specific metadata (not in Hub schema, clearly namespaced)
            "faultray": {
                "rawScore": assessment.raw_faultray_score,
                "planSummary": assessment.raw_plan_summary,
            },
        }

    def compare_with_live(
        self, assessment: PreDeployAssessment, hub_assessment: dict
    ) -> ComparisonReport:
        """Compare a pre-deploy prediction against an actual Resilience Hub assessment.

        Use this after deploying infrastructure to measure the accuracy of FaultRay's
        pre-deploy prediction versus what Resilience Hub actually scores.

        Args:
            assessment: The FaultRay pre-deploy assessment to validate.
            hub_assessment: The actual Resilience Hub AppAssessment export (dict).

        Returns:
            ComparisonReport with accuracy metrics and divergence details.
        """
        # Extract the live score — handle both Hub API format and FaultRay format
        live_score = float(
            hub_assessment.get("resiliencyScore")
            or hub_assessment.get("score")
            or 0.0
        )
        pre_score = assessment.overall_score
        score_delta = pre_score - live_score

        # Per-disruption deltas
        disruption_deltas: dict[str, float] = {}
        live_disruption = hub_assessment.get("disruptionResiliency", {})
        for ds in assessment.disruption_scores:
            key = ds.disruption_type.value
            live_ds_score = float(
                live_disruption.get(key, {}).get("score", 0.0)
            )
            disruption_deltas[key] = round(ds.score - live_ds_score, 2)

        # Policy status match
        live_status = hub_assessment.get(
            "complianceStatus", hub_assessment.get("policyStatus", "")
        )
        policy_status_match = (
            assessment.overall_policy_status.value == live_status
        )

        # Risk comparison
        live_risks: set[str] = set(hub_assessment.get("findings", []))
        pre_risks: set[str] = set(assessment.findings)
        missed_risks = sorted(live_risks - pre_risks)
        extra_risks = sorted(pre_risks - live_risks)

        # Prediction accuracy — based on score proximity (max 10-point deviation = 0%)
        max_deviation = 10.0
        accuracy = max(0.0, 1.0 - abs(score_delta) / max_deviation)

        summary = (
            f"FaultRay predicted {pre_score:.1f}, "
            f"Resilience Hub scored {live_score:.1f} "
            f"(delta {score_delta:+.1f}). "
            f"Accuracy: {accuracy * 100:.0f}%. "
            f"Policy status match: {policy_status_match}."
        )

        return ComparisonReport(
            pre_deploy_assessment=assessment,
            live_hub_assessment=hub_assessment,
            score_delta=round(score_delta, 2),
            live_score=live_score,
            pre_deploy_score=pre_score,
            disruption_deltas=disruption_deltas,
            prediction_accuracy=round(accuracy, 4),
            policy_status_match=policy_status_match,
            missed_risks=missed_risks,
            extra_risks=extra_risks,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_assessment(
        self,
        app_name: str,
        plan_source: str,
        overall_score: float,
        risks: list[str],
        resource_count: int,
        raw_plan_summary: dict[str, Any],
    ) -> PreDeployAssessment:
        """Core factory that constructs a PreDeployAssessment from computed values."""
        policy = self.policy
        threshold = policy.min_score_threshold if policy else _SCORE_THRESHOLDS["meets_policy"]

        overall_status = _score_to_policy_status(overall_score, threshold)

        disruption_scores: list[DisruptionScore] = []
        for disruption in DisruptionType:
            d_score = _disruption_score_from_overall(overall_score, disruption)
            base_rto = _BASE_RTO[disruption]
            base_rpo = _BASE_RPO[disruption]
            rto = (
                policy.rto_seconds.get(disruption, base_rto)
                if policy else base_rto
            )
            rpo = (
                policy.rpo_seconds.get(disruption, base_rpo)
                if policy else base_rpo
            )
            est_rto = _estimate_rto_from_score(rto, d_score)
            est_rpo = _estimate_rpo_from_score(rpo, d_score)
            d_status = _score_to_policy_status(d_score, threshold)

            # Filter risks relevant to this disruption type
            d_risks = _filter_risks_for_disruption(risks, disruption)
            d_recs = _generate_recommendations_for_disruption(disruption, d_score, d_risks)

            disruption_scores.append(DisruptionScore(
                disruption_type=disruption,
                score=round(d_score, 2),
                estimated_rto_seconds=est_rto,
                estimated_rpo_seconds=est_rpo,
                policy_status=d_status,
                risks=d_risks,
                recommendations=d_recs,
            ))

        # Top-level recommendations aggregate across disruptions
        top_recommendations = _build_top_recommendations(disruption_scores, overall_score)

        return PreDeployAssessment(
            app_name=app_name,
            plan_source=plan_source,
            overall_score=round(overall_score, 2),
            overall_policy_status=overall_status,
            disruption_scores=disruption_scores,
            policy=policy,
            resource_count=resource_count,
            findings=risks,
            recommendations=top_recommendations,
            raw_faultray_score=overall_score,
            raw_plan_summary=raw_plan_summary,
        )

    def _not_assessed_assessment(
        self, plan_source: str, reason: str = ""
    ) -> PreDeployAssessment:
        """Return a not-assessed assessment when analysis fails."""
        disruption_scores = [
            DisruptionScore(
                disruption_type=dt,
                score=0.0,
                estimated_rto_seconds=_BASE_RTO[dt] * 3,
                estimated_rpo_seconds=_BASE_RPO[dt] * 3,
                policy_status=PolicyStatus.NOT_ASSESSED,
            )
            for dt in DisruptionType
        ]
        return PreDeployAssessment(
            app_name="unknown",
            plan_source=plan_source,
            overall_score=0.0,
            overall_policy_status=PolicyStatus.NOT_ASSESSED,
            disruption_scores=disruption_scores,
            policy=self.policy,
            findings=[reason] if reason else [],
        )


# ---------------------------------------------------------------------------
# Risk / recommendation helpers (module-level, pure functions)
# ---------------------------------------------------------------------------

_INFRA_RISK_KEYWORDS = frozenset({
    "az", "availability_zone", "subnet", "instance", "ec2", "asg",
    "autoscaling", "elb", "alb", "nlb", "rds", "database", "disk",
    "hardware", "host",
})
_APP_RISK_KEYWORDS = frozenset({
    "lambda", "ecs", "fargate", "container", "service", "process",
    "application", "deploy", "cpu", "memory", "oom", "crash", "timeout",
})
_NETWORK_RISK_KEYWORDS = frozenset({
    "network", "vpc", "security_group", "nacl", "route", "internet_gateway",
    "nat", "dns", "connectivity", "peering", "transit_gateway",
})
_REGION_RISK_KEYWORDS = frozenset({
    "region", "cross_region", "global", "multi_region", "dr", "disaster",
    "recovery", "replication", "backup",
})

_DISRUPTION_KEYWORDS: dict[DisruptionType, frozenset[str]] = {
    DisruptionType.INFRASTRUCTURE: _INFRA_RISK_KEYWORDS,
    DisruptionType.APPLICATION: _APP_RISK_KEYWORDS,
    DisruptionType.NETWORK: _NETWORK_RISK_KEYWORDS,
    DisruptionType.REGION: _REGION_RISK_KEYWORDS,
}


def _filter_risks_for_disruption(
    risks: list[str], disruption: DisruptionType
) -> list[str]:
    """Return risks that are relevant to a given disruption type via keyword match."""
    keywords = _DISRUPTION_KEYWORDS[disruption]
    result = []
    for risk in risks:
        lower = risk.lower()
        if any(kw in lower for kw in keywords):
            result.append(risk)
    # If no keyword-matched risks, all risks are generic enough to include for every type
    if not result and risks:
        return list(risks)
    return result


def _generate_recommendations_for_disruption(
    disruption: DisruptionType,
    score: float,
    risks: list[str],
) -> list[str]:
    """Generate actionable recommendations for a disruption type based on the score."""
    recs: list[str] = []

    if disruption == DisruptionType.INFRASTRUCTURE:
        if score < 80:
            recs.append(
                "Deploy resources across multiple Availability Zones to reduce AZ-level blast radius."
            )
        if score < 60:
            recs.append(
                "Enable Multi-AZ for RDS instances and configure Auto Scaling Groups "
                "with a minimum of 2 instances."
            )
        if any("single" in r.lower() or "no_redundancy" in r.lower() for r in risks):
            recs.append(
                "Eliminate single points of failure identified in the plan."
            )

    elif disruption == DisruptionType.APPLICATION:
        if score < 80:
            recs.append(
                "Configure health checks and automatic instance replacement for all services."
            )
        if score < 60:
            recs.append(
                "Implement circuit breakers and retry logic to handle transient application failures."
            )
        if risks:
            recs.append(
                "Review application-level failure scenarios: "
                + ", ".join(risks[:3])
                + ("..." if len(risks) > 3 else "")
                + "."
            )

    elif disruption == DisruptionType.NETWORK:
        if score < 80:
            recs.append(
                "Configure redundant NAT Gateways per AZ and review security group egress rules."
            )
        if score < 60:
            recs.append(
                "Implement VPC endpoints for AWS services to reduce public internet dependency."
            )

    elif disruption == DisruptionType.REGION:
        if score < 80:
            recs.append(
                "Consider cross-region replication for critical data stores (S3, RDS)."
            )
        if score < 60:
            recs.append(
                "Implement a Disaster Recovery strategy (Pilot Light or Warm Standby) "
                "in a secondary AWS region."
            )
        if score < 40:
            recs.append(
                "Current infrastructure has no detectable multi-region resilience. "
                "A region-level failure would result in full application downtime."
            )

    return recs


def _build_top_recommendations(
    disruption_scores: list[DisruptionScore],
    overall_score: float,
) -> list[dict[str, Any]]:
    """Build a top-level list of prioritised recommendations across all disruption types."""
    recs: list[dict[str, Any]] = []

    # Sort by score ascending — lowest-scoring disruptions get highest priority
    sorted_ds = sorted(disruption_scores, key=lambda ds: ds.score)

    for ds in sorted_ds:
        for rec_text in ds.recommendations:
            severity = "HIGH" if ds.score < 60 else ("MEDIUM" if ds.score < 80 else "LOW")
            recs.append({
                "disruptionType": ds.disruption_type.value,
                "recommendation": rec_text,
                "severity": severity,
                "estimatedRtoImprovementSecs": max(0, ds.estimated_rto_seconds // 2),
            })

    if not recs and overall_score < 100:
        recs.append({
            "disruptionType": "General",
            "recommendation": (
                "Run FaultRay chaos simulations to identify specific resilience gaps "
                "before deploying to production."
            ),
            "severity": "LOW",
            "estimatedRtoImprovementSecs": 0,
        })

    return recs
