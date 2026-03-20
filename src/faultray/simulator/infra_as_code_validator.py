# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Infrastructure as Code Resilience Validator.

Validates IaC templates (Terraform, CloudFormation, CDK, Pulumi, Helm,
Kustomize, Ansible) for resilience best practices.  Detects missing
redundancy, monitoring gaps, encryption omissions and more, then generates
actionable remediation plans with effort estimates.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class IaCPlatform(str, Enum):
    """Supported Infrastructure-as-Code platforms."""

    TERRAFORM = "terraform"
    CLOUDFORMATION = "cloudformation"
    PULUMI = "pulumi"
    CDK = "cdk"
    HELM = "helm"
    KUSTOMIZE = "kustomize"
    ANSIBLE = "ansible"


class ResilienceRule(str, Enum):
    """Resilience best-practice rules checked by the validator."""

    MULTI_AZ = "multi_az"
    AUTO_SCALING = "auto_scaling"
    BACKUP_ENABLED = "backup_enabled"
    ENCRYPTION_ENABLED = "encryption_enabled"
    MONITORING_ENABLED = "monitoring_enabled"
    CIRCUIT_BREAKER = "circuit_breaker"
    RETRY_CONFIGURED = "retry_configured"
    HEALTH_CHECK = "health_check"
    DISASTER_RECOVERY = "disaster_recovery"
    COST_TAGGING = "cost_tagging"


class Severity(str, Enum):
    """Finding severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class IaCResource(BaseModel):
    """A single IaC-managed resource."""

    resource_type: str
    resource_id: str
    platform: IaCPlatform
    properties: dict[str, str] = Field(default_factory=dict)
    region: str = ""
    tags: dict[str, str] = Field(default_factory=dict)


class ValidationFinding(BaseModel):
    """A single validation finding against a resource."""

    rule: ResilienceRule
    resource_id: str
    severity: str = Severity.MEDIUM.value
    description: str = ""
    remediation: str = ""
    auto_fixable: bool = False


class IaCValidationReport(BaseModel):
    """Aggregated validation report."""

    platform: IaCPlatform
    total_resources: int = 0
    findings: list[ValidationFinding] = Field(default_factory=list)
    compliance_score: float = 0.0
    auto_fixable_count: int = 0
    recommendations: list[str] = Field(default_factory=list)


class RemediationStep(BaseModel):
    """A single step in a remediation plan."""

    order: int
    finding: ValidationFinding
    effort_hours: float = 0.0
    priority: int = 1
    description: str = ""


class RemediationPlan(BaseModel):
    """Plan to remediate all findings."""

    steps: list[RemediationStep] = Field(default_factory=list)
    total_effort_hours: float = 0.0
    auto_fixable_count: int = 0
    manual_count: int = 0
    priority_summary: dict[str, int] = Field(default_factory=dict)


class PlatformComplianceResult(BaseModel):
    """Compliance result for a single platform."""

    platform: IaCPlatform
    resource_count: int = 0
    finding_count: int = 0
    compliance_score: float = 0.0
    critical_count: int = 0
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class PlatformComparison(BaseModel):
    """Comparison of resilience posture across IaC platforms."""

    platforms: list[PlatformComplianceResult] = Field(default_factory=list)
    best_platform: str = ""
    worst_platform: str = ""
    overall_recommendations: list[str] = Field(default_factory=list)


class EffortEstimate(BaseModel):
    """Effort estimate to reach full compliance."""

    total_hours: float = 0.0
    critical_hours: float = 0.0
    high_hours: float = 0.0
    medium_hours: float = 0.0
    low_hours: float = 0.0
    info_hours: float = 0.0
    estimated_days: float = 0.0
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Severity weights for compliance score calculation
_SEVERITY_WEIGHTS: dict[str, float] = {
    Severity.CRITICAL.value: 10.0,
    Severity.HIGH.value: 7.0,
    Severity.MEDIUM.value: 4.0,
    Severity.LOW.value: 2.0,
    Severity.INFO.value: 0.5,
}

# Effort estimates in hours per rule
_RULE_EFFORT_HOURS: dict[ResilienceRule, float] = {
    ResilienceRule.MULTI_AZ: 8.0,
    ResilienceRule.AUTO_SCALING: 6.0,
    ResilienceRule.BACKUP_ENABLED: 4.0,
    ResilienceRule.ENCRYPTION_ENABLED: 3.0,
    ResilienceRule.MONITORING_ENABLED: 4.0,
    ResilienceRule.CIRCUIT_BREAKER: 6.0,
    ResilienceRule.RETRY_CONFIGURED: 3.0,
    ResilienceRule.HEALTH_CHECK: 2.0,
    ResilienceRule.DISASTER_RECOVERY: 12.0,
    ResilienceRule.COST_TAGGING: 1.0,
}

# Priority per severity (lower = higher priority)
_SEVERITY_PRIORITY: dict[str, int] = {
    Severity.CRITICAL.value: 1,
    Severity.HIGH.value: 2,
    Severity.MEDIUM.value: 3,
    Severity.LOW.value: 4,
    Severity.INFO.value: 5,
}

# Rule -> severity mapping
_RULE_SEVERITY: dict[ResilienceRule, str] = {
    ResilienceRule.MULTI_AZ: Severity.CRITICAL.value,
    ResilienceRule.AUTO_SCALING: Severity.HIGH.value,
    ResilienceRule.BACKUP_ENABLED: Severity.CRITICAL.value,
    ResilienceRule.ENCRYPTION_ENABLED: Severity.HIGH.value,
    ResilienceRule.MONITORING_ENABLED: Severity.MEDIUM.value,
    ResilienceRule.CIRCUIT_BREAKER: Severity.MEDIUM.value,
    ResilienceRule.RETRY_CONFIGURED: Severity.MEDIUM.value,
    ResilienceRule.HEALTH_CHECK: Severity.HIGH.value,
    ResilienceRule.DISASTER_RECOVERY: Severity.CRITICAL.value,
    ResilienceRule.COST_TAGGING: Severity.LOW.value,
}

# Rule -> auto-fixable mapping
_RULE_AUTO_FIXABLE: dict[ResilienceRule, bool] = {
    ResilienceRule.MULTI_AZ: False,
    ResilienceRule.AUTO_SCALING: False,
    ResilienceRule.BACKUP_ENABLED: True,
    ResilienceRule.ENCRYPTION_ENABLED: True,
    ResilienceRule.MONITORING_ENABLED: True,
    ResilienceRule.CIRCUIT_BREAKER: False,
    ResilienceRule.RETRY_CONFIGURED: True,
    ResilienceRule.HEALTH_CHECK: True,
    ResilienceRule.DISASTER_RECOVERY: False,
    ResilienceRule.COST_TAGGING: True,
}

# Resource types that should be checked for each rule
_RULE_APPLICABLE_RESOURCE_TYPES: dict[ResilienceRule, set[str]] = {
    ResilienceRule.MULTI_AZ: {
        "aws_instance", "aws_db_instance", "aws_rds_cluster",
        "aws_elasticache_cluster", "azurerm_virtual_machine",
        "google_compute_instance", "aws_elb", "aws_alb",
    },
    ResilienceRule.AUTO_SCALING: {
        "aws_instance", "aws_autoscaling_group", "aws_ecs_service",
        "azurerm_virtual_machine_scale_set", "google_compute_instance_group_manager",
        "kubernetes_deployment", "aws_lambda_function",
    },
    ResilienceRule.BACKUP_ENABLED: {
        "aws_db_instance", "aws_rds_cluster", "aws_dynamodb_table",
        "aws_s3_bucket", "azurerm_sql_database", "google_sql_database_instance",
        "aws_ebs_volume",
    },
    ResilienceRule.ENCRYPTION_ENABLED: {
        "aws_s3_bucket", "aws_db_instance", "aws_rds_cluster",
        "aws_ebs_volume", "aws_sqs_queue", "aws_sns_topic",
        "azurerm_storage_account", "google_storage_bucket",
    },
    ResilienceRule.MONITORING_ENABLED: {
        "aws_instance", "aws_db_instance", "aws_ecs_service",
        "aws_lambda_function", "azurerm_virtual_machine",
        "google_compute_instance", "kubernetes_deployment",
    },
    ResilienceRule.CIRCUIT_BREAKER: {
        "aws_ecs_service", "aws_lambda_function", "kubernetes_deployment",
        "aws_api_gateway_rest_api", "aws_appmesh_virtual_node",
    },
    ResilienceRule.RETRY_CONFIGURED: {
        "aws_lambda_function", "aws_sqs_queue", "aws_step_functions_state_machine",
        "aws_api_gateway_rest_api", "aws_ecs_service",
    },
    ResilienceRule.HEALTH_CHECK: {
        "aws_instance", "aws_ecs_service", "aws_elb", "aws_alb",
        "kubernetes_deployment", "aws_autoscaling_group",
        "azurerm_virtual_machine", "google_compute_instance",
    },
    ResilienceRule.DISASTER_RECOVERY: {
        "aws_db_instance", "aws_rds_cluster", "aws_s3_bucket",
        "aws_dynamodb_table", "azurerm_sql_database",
        "google_sql_database_instance",
    },
    ResilienceRule.COST_TAGGING: set(),  # applies to all resources
}

# Property keys that indicate a rule is satisfied
_RULE_PROPERTY_KEYS: dict[ResilienceRule, list[str]] = {
    ResilienceRule.MULTI_AZ: ["multi_az", "availability_zone_count", "az_count"],
    ResilienceRule.AUTO_SCALING: [
        "auto_scaling", "autoscaling", "min_capacity", "scaling_policy",
    ],
    ResilienceRule.BACKUP_ENABLED: [
        "backup", "backup_retention", "backup_enabled", "backup_policy",
    ],
    ResilienceRule.ENCRYPTION_ENABLED: [
        "encryption", "encrypted", "kms_key", "kms_key_id", "sse_algorithm",
    ],
    ResilienceRule.MONITORING_ENABLED: [
        "monitoring", "monitoring_enabled", "cloudwatch", "metrics",
        "logging", "log_group",
    ],
    ResilienceRule.CIRCUIT_BREAKER: [
        "circuit_breaker", "circuit_breaker_enabled", "outlier_detection",
    ],
    ResilienceRule.RETRY_CONFIGURED: [
        "retry", "retry_policy", "max_retries", "retry_count",
    ],
    ResilienceRule.HEALTH_CHECK: [
        "health_check", "health_check_path", "healthcheck", "liveness_probe",
    ],
    ResilienceRule.DISASTER_RECOVERY: [
        "dr", "disaster_recovery", "cross_region_replica", "geo_redundant",
        "read_replica",
    ],
    ResilienceRule.COST_TAGGING: [],  # checked via tags
}

# Remediation descriptions per rule
_RULE_REMEDIATION: dict[ResilienceRule, str] = {
    ResilienceRule.MULTI_AZ: (
        "Configure multi-AZ deployment to ensure high availability across "
        "availability zones."
    ),
    ResilienceRule.AUTO_SCALING: (
        "Enable auto-scaling with appropriate min/max capacity and scaling "
        "policies to handle load changes."
    ),
    ResilienceRule.BACKUP_ENABLED: (
        "Enable automated backups with appropriate retention period "
        "(minimum 7 days recommended)."
    ),
    ResilienceRule.ENCRYPTION_ENABLED: (
        "Enable encryption at rest and in transit using KMS or platform-managed keys."
    ),
    ResilienceRule.MONITORING_ENABLED: (
        "Enable monitoring and set up CloudWatch/Stackdriver/Azure Monitor "
        "alarms for critical metrics."
    ),
    ResilienceRule.CIRCUIT_BREAKER: (
        "Configure circuit breaker pattern to prevent cascading failures "
        "across dependent services."
    ),
    ResilienceRule.RETRY_CONFIGURED: (
        "Configure retry policies with exponential backoff and jitter "
        "to handle transient failures."
    ),
    ResilienceRule.HEALTH_CHECK: (
        "Configure health checks with appropriate interval, timeout, "
        "and threshold settings."
    ),
    ResilienceRule.DISASTER_RECOVERY: (
        "Set up cross-region replication or geo-redundant storage "
        "for disaster recovery."
    ),
    ResilienceRule.COST_TAGGING: (
        "Add cost allocation tags (environment, team, project, cost-center) "
        "for billing visibility."
    ),
}

# Finding descriptions per rule
_RULE_DESCRIPTION: dict[ResilienceRule, str] = {
    ResilienceRule.MULTI_AZ: "Resource is not configured for multi-AZ deployment.",
    ResilienceRule.AUTO_SCALING: "Auto-scaling is not configured for this resource.",
    ResilienceRule.BACKUP_ENABLED: "Automated backups are not enabled.",
    ResilienceRule.ENCRYPTION_ENABLED: "Encryption at rest is not enabled.",
    ResilienceRule.MONITORING_ENABLED: "Monitoring/alerting is not configured.",
    ResilienceRule.CIRCUIT_BREAKER: "Circuit breaker pattern is not configured.",
    ResilienceRule.RETRY_CONFIGURED: "Retry policy is not configured.",
    ResilienceRule.HEALTH_CHECK: "Health check is not configured.",
    ResilienceRule.DISASTER_RECOVERY: "Disaster recovery is not configured.",
    ResilienceRule.COST_TAGGING: "Cost allocation tags are missing.",
}

# Required cost tags
_REQUIRED_COST_TAGS: set[str] = {
    "environment", "team", "project", "cost-center",
}

# Effort multiplier per severity
_SEVERITY_EFFORT_HOURS: dict[str, float] = {
    Severity.CRITICAL.value: 1.5,
    Severity.HIGH.value: 1.2,
    Severity.MEDIUM.value: 1.0,
    Severity.LOW.value: 0.5,
    Severity.INFO.value: 0.25,
}

# Working hours per day for effort estimation
_WORKING_HOURS_PER_DAY = 8.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class IaCResilienceValidatorEngine:
    """Validates IaC resources for resilience best practices.

    Checks resources against a set of resilience rules, detects missing
    redundancy and monitoring, generates remediation plans, compares
    platform compliance, and estimates remediation effort.
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_resources(
        self,
        resources: list[IaCResource],
    ) -> IaCValidationReport:
        """Validate a list of IaC resources against all resilience rules.

        Parameters
        ----------
        resources:
            List of IaC resources to validate.

        Returns
        -------
        IaCValidationReport
            Aggregated validation report with findings, compliance score,
            and recommendations.
        """
        if not resources:
            return IaCValidationReport(
                platform=IaCPlatform.TERRAFORM,
                total_resources=0,
                findings=[],
                compliance_score=100.0,
                auto_fixable_count=0,
                recommendations=[],
            )

        platform = resources[0].platform
        findings: list[ValidationFinding] = []

        for resource in resources:
            for rule in ResilienceRule:
                finding = self.check_rule(resource, rule)
                if finding is not None:
                    findings.append(finding)

        # Add redundancy and monitoring findings
        redundancy_findings = self.detect_missing_redundancy(resources)
        monitoring_findings = self.detect_missing_monitoring(resources)

        # Deduplicate: only add if not already present for that resource+rule
        existing_keys = {(f.resource_id, f.rule) for f in findings}
        for f in redundancy_findings:
            if (f.resource_id, f.rule) not in existing_keys:
                findings.append(f)
                existing_keys.add((f.resource_id, f.rule))

        for f in monitoring_findings:
            if (f.resource_id, f.rule) not in existing_keys:
                findings.append(f)
                existing_keys.add((f.resource_id, f.rule))

        compliance_score = self._calculate_compliance_score(
            len(resources), findings,
        )
        auto_fixable_count = sum(1 for f in findings if f.auto_fixable)
        recommendations = self._generate_report_recommendations(findings, resources)

        return IaCValidationReport(
            platform=platform,
            total_resources=len(resources),
            findings=findings,
            compliance_score=compliance_score,
            auto_fixable_count=auto_fixable_count,
            recommendations=recommendations,
        )

    def check_rule(
        self,
        resource: IaCResource,
        rule: ResilienceRule,
    ) -> ValidationFinding | None:
        """Check a single resource against a single resilience rule.

        Parameters
        ----------
        resource:
            The IaC resource to check.
        rule:
            The resilience rule to evaluate.

        Returns
        -------
        ValidationFinding | None
            A finding if the rule is violated, or ``None`` if compliant.
        """
        # Check if the rule applies to this resource type
        if not self._is_rule_applicable(resource, rule):
            return None

        # Check if the rule is satisfied
        if self._is_rule_satisfied(resource, rule):
            return None

        # Rule is violated — create a finding
        return ValidationFinding(
            rule=rule,
            resource_id=resource.resource_id,
            severity=_RULE_SEVERITY.get(rule, Severity.MEDIUM.value),
            description=_RULE_DESCRIPTION.get(rule, f"Rule {rule.value} violated."),
            remediation=_RULE_REMEDIATION.get(rule, "Review and fix the configuration."),
            auto_fixable=_RULE_AUTO_FIXABLE.get(rule, False),
        )

    def detect_missing_redundancy(
        self,
        resources: list[IaCResource],
    ) -> list[ValidationFinding]:
        """Detect resources missing redundancy configurations.

        Checks for multi-AZ, auto-scaling, and disaster recovery gaps.

        Parameters
        ----------
        resources:
            List of IaC resources to check.

        Returns
        -------
        list[ValidationFinding]
            Findings related to missing redundancy.
        """
        findings: list[ValidationFinding] = []
        redundancy_rules = [
            ResilienceRule.MULTI_AZ,
            ResilienceRule.AUTO_SCALING,
            ResilienceRule.DISASTER_RECOVERY,
        ]

        for resource in resources:
            for rule in redundancy_rules:
                if self._is_rule_applicable(resource, rule):
                    if not self._is_rule_satisfied(resource, rule):
                        findings.append(
                            ValidationFinding(
                                rule=rule,
                                resource_id=resource.resource_id,
                                severity=_RULE_SEVERITY.get(
                                    rule, Severity.HIGH.value,
                                ),
                                description=_RULE_DESCRIPTION.get(
                                    rule, f"Missing {rule.value}.",
                                ),
                                remediation=_RULE_REMEDIATION.get(
                                    rule, "Add redundancy configuration.",
                                ),
                                auto_fixable=_RULE_AUTO_FIXABLE.get(rule, False),
                            )
                        )

        return findings

    def detect_missing_monitoring(
        self,
        resources: list[IaCResource],
    ) -> list[ValidationFinding]:
        """Detect resources missing monitoring configurations.

        Checks for monitoring, health checks, and circuit breaker gaps.

        Parameters
        ----------
        resources:
            List of IaC resources to check.

        Returns
        -------
        list[ValidationFinding]
            Findings related to missing monitoring.
        """
        findings: list[ValidationFinding] = []
        monitoring_rules = [
            ResilienceRule.MONITORING_ENABLED,
            ResilienceRule.HEALTH_CHECK,
            ResilienceRule.CIRCUIT_BREAKER,
        ]

        for resource in resources:
            for rule in monitoring_rules:
                if self._is_rule_applicable(resource, rule):
                    if not self._is_rule_satisfied(resource, rule):
                        findings.append(
                            ValidationFinding(
                                rule=rule,
                                resource_id=resource.resource_id,
                                severity=_RULE_SEVERITY.get(
                                    rule, Severity.MEDIUM.value,
                                ),
                                description=_RULE_DESCRIPTION.get(
                                    rule, f"Missing {rule.value}.",
                                ),
                                remediation=_RULE_REMEDIATION.get(
                                    rule, "Add monitoring configuration.",
                                ),
                                auto_fixable=_RULE_AUTO_FIXABLE.get(rule, False),
                            )
                        )

        return findings

    def generate_remediation_plan(
        self,
        findings: list[ValidationFinding],
    ) -> RemediationPlan:
        """Generate a prioritized remediation plan from findings.

        Parameters
        ----------
        findings:
            List of validation findings to remediate.

        Returns
        -------
        RemediationPlan
            Ordered remediation plan with effort estimates.
        """
        if not findings:
            return RemediationPlan(
                steps=[],
                total_effort_hours=0.0,
                auto_fixable_count=0,
                manual_count=0,
                priority_summary={},
            )

        # Sort by severity priority (critical first)
        sorted_findings = sorted(
            findings,
            key=lambda f: _SEVERITY_PRIORITY.get(f.severity, 5),
        )

        steps: list[RemediationStep] = []
        total_effort = 0.0
        auto_count = 0
        manual_count = 0
        priority_summary: dict[str, int] = {}

        for i, finding in enumerate(sorted_findings, start=1):
            effort = _RULE_EFFORT_HOURS.get(finding.rule, 4.0)
            # Adjust effort by severity multiplier
            sev_mult = _SEVERITY_EFFORT_HOURS.get(finding.severity, 1.0)
            effort *= sev_mult

            priority = _SEVERITY_PRIORITY.get(finding.severity, 5)

            step = RemediationStep(
                order=i,
                finding=finding,
                effort_hours=effort,
                priority=priority,
                description=(
                    f"Fix {finding.rule.value} for {finding.resource_id}: "
                    f"{finding.remediation}"
                ),
            )
            steps.append(step)
            total_effort += effort

            if finding.auto_fixable:
                auto_count += 1
            else:
                manual_count += 1

            sev_key = finding.severity
            priority_summary[sev_key] = priority_summary.get(sev_key, 0) + 1

        return RemediationPlan(
            steps=steps,
            total_effort_hours=total_effort,
            auto_fixable_count=auto_count,
            manual_count=manual_count,
            priority_summary=priority_summary,
        )

    def compare_platforms(
        self,
        resource_groups: dict[IaCPlatform, list[IaCResource]],
    ) -> PlatformComparison:
        """Compare resilience posture across IaC platforms.

        Parameters
        ----------
        resource_groups:
            Mapping of platform to its list of resources.

        Returns
        -------
        PlatformComparison
            Comparison result with per-platform scores and recommendations.
        """
        if not resource_groups:
            return PlatformComparison(
                platforms=[],
                best_platform="",
                worst_platform="",
                overall_recommendations=["No platforms to compare."],
            )

        platform_results: list[PlatformComplianceResult] = []

        for platform, resources in resource_groups.items():
            report = self.validate_resources(resources)

            critical_count = sum(
                1 for f in report.findings
                if f.severity == Severity.CRITICAL.value
            )

            # Determine strengths and weaknesses
            violated_rules = {f.rule for f in report.findings}
            all_rules = set(ResilienceRule)
            passed_rules = all_rules - violated_rules

            strengths = [
                f"{r.value} configured" for r in sorted(passed_rules, key=lambda x: x.value)
            ]
            weaknesses = [
                f"{r.value} missing" for r in sorted(violated_rules, key=lambda x: x.value)
            ]

            platform_results.append(
                PlatformComplianceResult(
                    platform=platform,
                    resource_count=len(resources),
                    finding_count=len(report.findings),
                    compliance_score=report.compliance_score,
                    critical_count=critical_count,
                    strengths=strengths,
                    weaknesses=weaknesses,
                )
            )

        # Sort by compliance score descending
        platform_results.sort(key=lambda p: p.compliance_score, reverse=True)

        best_platform = platform_results[0].platform.value if platform_results else ""
        worst_platform = platform_results[-1].platform.value if platform_results else ""

        overall_recs: list[str] = []
        if len(platform_results) > 1:
            score_diff = platform_results[0].compliance_score - platform_results[-1].compliance_score
            if score_diff > 20.0:
                overall_recs.append(
                    f"Significant compliance gap ({score_diff:.1f}%) between "
                    f"{best_platform} and {worst_platform}. "
                    f"Align {worst_platform} with {best_platform} best practices."
                )

        # Aggregate critical findings
        total_criticals = sum(p.critical_count for p in platform_results)
        if total_criticals > 0:
            overall_recs.append(
                f"{total_criticals} critical findings across all platforms. "
                "Address these before any other remediation."
            )

        if not overall_recs:
            overall_recs.append("All platforms show reasonable compliance posture.")

        return PlatformComparison(
            platforms=platform_results,
            best_platform=best_platform,
            worst_platform=worst_platform,
            overall_recommendations=overall_recs,
        )

    def estimate_compliance_effort(
        self,
        findings: list[ValidationFinding],
    ) -> EffortEstimate:
        """Estimate the effort to remediate all findings.

        Parameters
        ----------
        findings:
            List of validation findings.

        Returns
        -------
        EffortEstimate
            Effort breakdown by severity with total hours and days.
        """
        if not findings:
            return EffortEstimate(
                total_hours=0.0,
                critical_hours=0.0,
                high_hours=0.0,
                medium_hours=0.0,
                low_hours=0.0,
                info_hours=0.0,
                estimated_days=0.0,
                findings_by_severity={},
                recommendations=["No findings to remediate."],
            )

        severity_hours: dict[str, float] = {
            Severity.CRITICAL.value: 0.0,
            Severity.HIGH.value: 0.0,
            Severity.MEDIUM.value: 0.0,
            Severity.LOW.value: 0.0,
            Severity.INFO.value: 0.0,
        }
        findings_by_severity: dict[str, int] = {}

        for finding in findings:
            effort = _RULE_EFFORT_HOURS.get(finding.rule, 4.0)
            sev_mult = _SEVERITY_EFFORT_HOURS.get(finding.severity, 1.0)
            effort *= sev_mult

            sev = finding.severity
            severity_hours[sev] = severity_hours.get(sev, 0.0) + effort
            findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1

        total_hours = sum(severity_hours.values())
        estimated_days = total_hours / _WORKING_HOURS_PER_DAY if total_hours > 0 else 0.0

        recommendations: list[str] = []
        crit_count = findings_by_severity.get(Severity.CRITICAL.value, 0)
        high_count = findings_by_severity.get(Severity.HIGH.value, 0)

        if crit_count > 0:
            recommendations.append(
                f"Prioritize {crit_count} critical finding(s) — "
                f"estimated {severity_hours[Severity.CRITICAL.value]:.1f}h."
            )
        if high_count > 0:
            recommendations.append(
                f"Address {high_count} high-severity finding(s) next — "
                f"estimated {severity_hours[Severity.HIGH.value]:.1f}h."
            )
        auto_count = sum(1 for f in findings if f.auto_fixable)
        if auto_count > 0:
            recommendations.append(
                f"{auto_count} finding(s) can be auto-fixed to save time."
            )
        if not recommendations:
            recommendations.append("All findings are low priority.")

        return EffortEstimate(
            total_hours=total_hours,
            critical_hours=severity_hours[Severity.CRITICAL.value],
            high_hours=severity_hours[Severity.HIGH.value],
            medium_hours=severity_hours[Severity.MEDIUM.value],
            low_hours=severity_hours[Severity.LOW.value],
            info_hours=severity_hours[Severity.INFO.value],
            estimated_days=estimated_days,
            findings_by_severity=findings_by_severity,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_rule_applicable(
        self,
        resource: IaCResource,
        rule: ResilienceRule,
    ) -> bool:
        """Check whether a rule applies to a given resource type."""
        # Cost tagging applies to all resources
        if rule == ResilienceRule.COST_TAGGING:
            return True

        applicable_types = _RULE_APPLICABLE_RESOURCE_TYPES.get(rule, set())
        return resource.resource_type in applicable_types

    def _is_rule_satisfied(
        self,
        resource: IaCResource,
        rule: ResilienceRule,
    ) -> bool:
        """Check whether a resource satisfies a given rule."""
        # Cost tagging: check if required tags are present
        if rule == ResilienceRule.COST_TAGGING:
            return self._check_cost_tags(resource)

        # Check property keys
        property_keys = _RULE_PROPERTY_KEYS.get(rule, [])
        props_lower = {k.lower(): v.lower() for k, v in resource.properties.items()}

        for key in property_keys:
            if key.lower() in props_lower:
                val = props_lower[key.lower()]
                # "false", "0", "none", "" are not satisfied
                if val not in ("false", "0", "none", ""):
                    return True

        return False

    def _check_cost_tags(self, resource: IaCResource) -> bool:
        """Check whether required cost allocation tags are present."""
        resource_tags_lower = {k.lower() for k in resource.tags}
        required_lower = {t.lower() for t in _REQUIRED_COST_TAGS}
        return required_lower.issubset(resource_tags_lower)

    def _calculate_compliance_score(
        self,
        total_resources: int,
        findings: list[ValidationFinding],
    ) -> float:
        """Calculate a compliance score from 0 to 100.

        A perfect score (100) means no findings.  Each finding deducts
        points proportional to its severity weight, normalised by the
        total number of resources and rules.
        """
        if total_resources == 0:
            return 100.0

        max_possible = total_resources * len(ResilienceRule) * max(_SEVERITY_WEIGHTS.values())

        total_deductions = sum(
            _SEVERITY_WEIGHTS.get(f.severity, 1.0) for f in findings
        )

        score = max(0.0, 100.0 - (total_deductions / max_possible) * 100.0)
        return min(100.0, round(score, 2))

    def _generate_report_recommendations(
        self,
        findings: list[ValidationFinding],
        resources: list[IaCResource],
    ) -> list[str]:
        """Generate top-level recommendations for the validation report."""
        recs: list[str] = []

        if not findings:
            recs.append("All resources pass resilience validation. Well done!")
            return recs

        # Count by severity
        sev_counts: dict[str, int] = {}
        for f in findings:
            sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1

        crit = sev_counts.get(Severity.CRITICAL.value, 0)
        high = sev_counts.get(Severity.HIGH.value, 0)

        if crit > 0:
            recs.append(
                f"URGENT: {crit} critical finding(s) require immediate attention."
            )
        if high > 0:
            recs.append(
                f"{high} high-severity finding(s) should be addressed soon."
            )

        # Count auto-fixable
        auto_fixable = sum(1 for f in findings if f.auto_fixable)
        if auto_fixable > 0:
            recs.append(
                f"{auto_fixable} finding(s) can be automatically remediated."
            )

        # Rule-specific recommendations
        violated_rules = {f.rule for f in findings}
        if ResilienceRule.MULTI_AZ in violated_rules:
            recs.append(
                "Enable multi-AZ deployment for critical resources to "
                "improve availability."
            )
        if ResilienceRule.ENCRYPTION_ENABLED in violated_rules:
            recs.append(
                "Enable encryption at rest for data stores to meet "
                "compliance requirements."
            )
        if ResilienceRule.BACKUP_ENABLED in violated_rules:
            recs.append(
                "Enable automated backups for databases and storage "
                "to prevent data loss."
            )

        return recs
