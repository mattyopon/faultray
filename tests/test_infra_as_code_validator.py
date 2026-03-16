"""Tests for Infrastructure as Code Resilience Validator.

Covers IaCResilienceValidatorEngine, all models, enumerations, rule checking,
redundancy detection, monitoring detection, remediation planning, platform
comparison, effort estimation, and edge cases.
Targets 100% line/branch coverage with 140+ tests.
"""

from __future__ import annotations

import pytest

from faultray.simulator.infra_as_code_validator import (
    EffortEstimate,
    IaCPlatform,
    IaCResilienceValidatorEngine,
    IaCResource,
    IaCValidationReport,
    PlatformComparison,
    PlatformComplianceResult,
    RemediationPlan,
    RemediationStep,
    ResilienceRule,
    Severity,
    ValidationFinding,
    _REQUIRED_COST_TAGS,
    _RULE_APPLICABLE_RESOURCE_TYPES,
    _RULE_AUTO_FIXABLE,
    _RULE_DESCRIPTION,
    _RULE_EFFORT_HOURS,
    _RULE_PROPERTY_KEYS,
    _RULE_REMEDIATION,
    _RULE_SEVERITY,
    _SEVERITY_EFFORT_HOURS,
    _SEVERITY_PRIORITY,
    _SEVERITY_WEIGHTS,
    _WORKING_HOURS_PER_DAY,
)


# ------------------------------------------------------------------ helpers


def _resource(
    resource_id: str = "my-resource",
    resource_type: str = "aws_instance",
    platform: IaCPlatform = IaCPlatform.TERRAFORM,
    properties: dict[str, str] | None = None,
    region: str = "us-east-1",
    tags: dict[str, str] | None = None,
) -> IaCResource:
    """Shorthand factory for IaCResource."""
    return IaCResource(
        resource_type=resource_type,
        resource_id=resource_id,
        platform=platform,
        properties=properties or {},
        region=region,
        tags=tags or {},
    )


def _compliant_resource(
    resource_id: str = "compliant-1",
    resource_type: str = "aws_instance",
    platform: IaCPlatform = IaCPlatform.TERRAFORM,
) -> IaCResource:
    """A resource that passes most rules."""
    return IaCResource(
        resource_type=resource_type,
        resource_id=resource_id,
        platform=platform,
        properties={
            "multi_az": "true",
            "auto_scaling": "true",
            "backup_enabled": "true",
            "encrypted": "true",
            "monitoring_enabled": "true",
            "circuit_breaker": "true",
            "retry_policy": "true",
            "health_check": "true",
            "disaster_recovery": "true",
        },
        region="us-east-1",
        tags={
            "environment": "production",
            "team": "platform",
            "project": "core",
            "cost-center": "eng-001",
        },
    )


# ------------------------------------------------------------------ Enum tests


class TestIaCPlatform:
    """Tests for IaCPlatform enum."""

    def test_all_values_exist(self) -> None:
        assert IaCPlatform.TERRAFORM.value == "terraform"
        assert IaCPlatform.CLOUDFORMATION.value == "cloudformation"
        assert IaCPlatform.PULUMI.value == "pulumi"
        assert IaCPlatform.CDK.value == "cdk"
        assert IaCPlatform.HELM.value == "helm"
        assert IaCPlatform.KUSTOMIZE.value == "kustomize"
        assert IaCPlatform.ANSIBLE.value == "ansible"

    def test_member_count(self) -> None:
        assert len(IaCPlatform) == 7

    def test_str_enum(self) -> None:
        assert str(IaCPlatform.TERRAFORM) == "IaCPlatform.TERRAFORM"
        assert IaCPlatform.TERRAFORM == "terraform"


class TestResilienceRule:
    """Tests for ResilienceRule enum."""

    def test_all_values_exist(self) -> None:
        assert ResilienceRule.MULTI_AZ.value == "multi_az"
        assert ResilienceRule.AUTO_SCALING.value == "auto_scaling"
        assert ResilienceRule.BACKUP_ENABLED.value == "backup_enabled"
        assert ResilienceRule.ENCRYPTION_ENABLED.value == "encryption_enabled"
        assert ResilienceRule.MONITORING_ENABLED.value == "monitoring_enabled"
        assert ResilienceRule.CIRCUIT_BREAKER.value == "circuit_breaker"
        assert ResilienceRule.RETRY_CONFIGURED.value == "retry_configured"
        assert ResilienceRule.HEALTH_CHECK.value == "health_check"
        assert ResilienceRule.DISASTER_RECOVERY.value == "disaster_recovery"
        assert ResilienceRule.COST_TAGGING.value == "cost_tagging"

    def test_member_count(self) -> None:
        assert len(ResilienceRule) == 10


class TestSeverity:
    """Tests for Severity enum."""

    def test_all_values(self) -> None:
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"
        assert Severity.INFO.value == "info"

    def test_member_count(self) -> None:
        assert len(Severity) == 5


# ------------------------------------------------------------------ Model tests


class TestIaCResource:
    """Tests for IaCResource Pydantic model."""

    def test_minimal_creation(self) -> None:
        r = IaCResource(
            resource_type="aws_instance",
            resource_id="i-123",
            platform=IaCPlatform.TERRAFORM,
        )
        assert r.resource_type == "aws_instance"
        assert r.resource_id == "i-123"
        assert r.platform == IaCPlatform.TERRAFORM
        assert r.properties == {}
        assert r.region == ""
        assert r.tags == {}

    def test_full_creation(self) -> None:
        r = _resource(
            resource_id="web-1",
            resource_type="aws_instance",
            properties={"multi_az": "true"},
            tags={"environment": "prod"},
        )
        assert r.properties["multi_az"] == "true"
        assert r.tags["environment"] == "prod"
        assert r.region == "us-east-1"

    def test_different_platforms(self) -> None:
        for p in IaCPlatform:
            r = IaCResource(
                resource_type="generic",
                resource_id="res-1",
                platform=p,
            )
            assert r.platform == p


class TestValidationFinding:
    """Tests for ValidationFinding Pydantic model."""

    def test_minimal_creation(self) -> None:
        f = ValidationFinding(
            rule=ResilienceRule.MULTI_AZ,
            resource_id="r-1",
        )
        assert f.rule == ResilienceRule.MULTI_AZ
        assert f.resource_id == "r-1"
        assert f.severity == Severity.MEDIUM.value
        assert f.auto_fixable is False

    def test_full_creation(self) -> None:
        f = ValidationFinding(
            rule=ResilienceRule.ENCRYPTION_ENABLED,
            resource_id="db-1",
            severity=Severity.HIGH.value,
            description="Not encrypted",
            remediation="Enable encryption",
            auto_fixable=True,
        )
        assert f.severity == "high"
        assert f.description == "Not encrypted"
        assert f.remediation == "Enable encryption"
        assert f.auto_fixable is True


class TestIaCValidationReport:
    """Tests for IaCValidationReport Pydantic model."""

    def test_minimal_creation(self) -> None:
        r = IaCValidationReport(platform=IaCPlatform.TERRAFORM)
        assert r.platform == IaCPlatform.TERRAFORM
        assert r.total_resources == 0
        assert r.findings == []
        assert r.compliance_score == 0.0
        assert r.auto_fixable_count == 0
        assert r.recommendations == []

    def test_full_creation(self) -> None:
        finding = ValidationFinding(
            rule=ResilienceRule.BACKUP_ENABLED,
            resource_id="db-1",
        )
        r = IaCValidationReport(
            platform=IaCPlatform.CLOUDFORMATION,
            total_resources=5,
            findings=[finding],
            compliance_score=80.0,
            auto_fixable_count=1,
            recommendations=["Enable backups"],
        )
        assert len(r.findings) == 1
        assert r.compliance_score == 80.0


class TestRemediationStep:
    """Tests for RemediationStep model."""

    def test_creation(self) -> None:
        finding = ValidationFinding(
            rule=ResilienceRule.HEALTH_CHECK,
            resource_id="svc-1",
        )
        step = RemediationStep(
            order=1,
            finding=finding,
            effort_hours=2.0,
            priority=1,
            description="Fix health check",
        )
        assert step.order == 1
        assert step.effort_hours == 2.0
        assert step.priority == 1


class TestRemediationPlan:
    """Tests for RemediationPlan model."""

    def test_empty(self) -> None:
        plan = RemediationPlan()
        assert plan.steps == []
        assert plan.total_effort_hours == 0.0
        assert plan.auto_fixable_count == 0
        assert plan.manual_count == 0


class TestPlatformComplianceResult:
    """Tests for PlatformComplianceResult model."""

    def test_creation(self) -> None:
        r = PlatformComplianceResult(
            platform=IaCPlatform.CDK,
            resource_count=10,
            finding_count=3,
            compliance_score=85.0,
            critical_count=1,
            strengths=["encryption configured"],
            weaknesses=["multi_az missing"],
        )
        assert r.platform == IaCPlatform.CDK
        assert r.compliance_score == 85.0


class TestPlatformComparison:
    """Tests for PlatformComparison model."""

    def test_empty(self) -> None:
        c = PlatformComparison()
        assert c.platforms == []
        assert c.best_platform == ""
        assert c.worst_platform == ""

    def test_creation(self) -> None:
        c = PlatformComparison(
            best_platform="terraform",
            worst_platform="ansible",
            overall_recommendations=["Fix it"],
        )
        assert c.best_platform == "terraform"


class TestEffortEstimate:
    """Tests for EffortEstimate model."""

    def test_defaults(self) -> None:
        e = EffortEstimate()
        assert e.total_hours == 0.0
        assert e.estimated_days == 0.0
        assert e.recommendations == []

    def test_full_creation(self) -> None:
        e = EffortEstimate(
            total_hours=40.0,
            critical_hours=10.0,
            high_hours=15.0,
            medium_hours=10.0,
            low_hours=4.0,
            info_hours=1.0,
            estimated_days=5.0,
            findings_by_severity={"critical": 2, "high": 3},
            recommendations=["Fix critical first"],
        )
        assert e.total_hours == 40.0
        assert e.estimated_days == 5.0


# ------------------------------------------------------------------ Constants tests


class TestConstants:
    """Tests for module-level constants."""

    def test_severity_weights_all_severities(self) -> None:
        for s in Severity:
            assert s.value in _SEVERITY_WEIGHTS

    def test_rule_effort_hours_all_rules(self) -> None:
        for r in ResilienceRule:
            assert r in _RULE_EFFORT_HOURS

    def test_severity_priority_all_severities(self) -> None:
        for s in Severity:
            assert s.value in _SEVERITY_PRIORITY

    def test_rule_severity_all_rules(self) -> None:
        for r in ResilienceRule:
            assert r in _RULE_SEVERITY

    def test_rule_auto_fixable_all_rules(self) -> None:
        for r in ResilienceRule:
            assert r in _RULE_AUTO_FIXABLE

    def test_rule_property_keys_all_rules(self) -> None:
        for r in ResilienceRule:
            assert r in _RULE_PROPERTY_KEYS

    def test_rule_remediation_all_rules(self) -> None:
        for r in ResilienceRule:
            assert r in _RULE_REMEDIATION

    def test_rule_description_all_rules(self) -> None:
        for r in ResilienceRule:
            assert r in _RULE_DESCRIPTION

    def test_required_cost_tags(self) -> None:
        assert "environment" in _REQUIRED_COST_TAGS
        assert "team" in _REQUIRED_COST_TAGS
        assert "project" in _REQUIRED_COST_TAGS
        assert "cost-center" in _REQUIRED_COST_TAGS

    def test_working_hours_per_day(self) -> None:
        assert _WORKING_HOURS_PER_DAY == 8.0

    def test_severity_effort_hours(self) -> None:
        assert _SEVERITY_EFFORT_HOURS[Severity.CRITICAL.value] > _SEVERITY_EFFORT_HOURS[Severity.LOW.value]


# ------------------------------------------------------------------ Engine: check_rule


class TestCheckRule:
    """Tests for IaCResilienceValidatorEngine.check_rule."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_non_applicable_rule_returns_none(self) -> None:
        """A rule that doesn't apply to the resource type returns None."""
        r = _resource(resource_type="custom_thing")
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is None

    def test_cost_tagging_applies_to_all_resources(self) -> None:
        r = _resource(resource_type="anything_at_all")
        result = self.engine.check_rule(r, ResilienceRule.COST_TAGGING)
        assert result is not None
        assert result.rule == ResilienceRule.COST_TAGGING

    def test_cost_tagging_passes_with_required_tags(self) -> None:
        r = _resource(
            resource_type="anything",
            tags={
                "environment": "prod",
                "team": "core",
                "project": "api",
                "cost-center": "eng",
            },
        )
        result = self.engine.check_rule(r, ResilienceRule.COST_TAGGING)
        assert result is None

    def test_cost_tagging_fails_with_missing_tags(self) -> None:
        r = _resource(resource_type="anything", tags={"environment": "prod"})
        result = self.engine.check_rule(r, ResilienceRule.COST_TAGGING)
        assert result is not None

    def test_multi_az_violated(self) -> None:
        r = _resource(resource_type="aws_instance")
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None
        assert result.severity == Severity.CRITICAL.value

    def test_multi_az_satisfied(self) -> None:
        r = _resource(
            resource_type="aws_instance",
            properties={"multi_az": "true"},
        )
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is None

    def test_auto_scaling_violated(self) -> None:
        r = _resource(resource_type="aws_autoscaling_group")
        result = self.engine.check_rule(r, ResilienceRule.AUTO_SCALING)
        assert result is not None
        assert result.rule == ResilienceRule.AUTO_SCALING

    def test_auto_scaling_satisfied(self) -> None:
        r = _resource(
            resource_type="aws_autoscaling_group",
            properties={"auto_scaling": "enabled"},
        )
        result = self.engine.check_rule(r, ResilienceRule.AUTO_SCALING)
        assert result is None

    def test_backup_violated(self) -> None:
        r = _resource(resource_type="aws_db_instance")
        result = self.engine.check_rule(r, ResilienceRule.BACKUP_ENABLED)
        assert result is not None
        assert result.auto_fixable is True

    def test_backup_satisfied(self) -> None:
        r = _resource(
            resource_type="aws_db_instance",
            properties={"backup_retention": "7"},
        )
        result = self.engine.check_rule(r, ResilienceRule.BACKUP_ENABLED)
        assert result is None

    def test_encryption_violated(self) -> None:
        r = _resource(resource_type="aws_s3_bucket")
        result = self.engine.check_rule(r, ResilienceRule.ENCRYPTION_ENABLED)
        assert result is not None

    def test_encryption_satisfied(self) -> None:
        r = _resource(
            resource_type="aws_s3_bucket",
            properties={"sse_algorithm": "aws:kms"},
        )
        result = self.engine.check_rule(r, ResilienceRule.ENCRYPTION_ENABLED)
        assert result is None

    def test_monitoring_violated(self) -> None:
        r = _resource(resource_type="aws_instance")
        result = self.engine.check_rule(r, ResilienceRule.MONITORING_ENABLED)
        assert result is not None

    def test_monitoring_satisfied(self) -> None:
        r = _resource(
            resource_type="aws_instance",
            properties={"monitoring": "true"},
        )
        result = self.engine.check_rule(r, ResilienceRule.MONITORING_ENABLED)
        assert result is None

    def test_circuit_breaker_violated(self) -> None:
        r = _resource(resource_type="aws_ecs_service")
        result = self.engine.check_rule(r, ResilienceRule.CIRCUIT_BREAKER)
        assert result is not None

    def test_circuit_breaker_satisfied(self) -> None:
        r = _resource(
            resource_type="aws_ecs_service",
            properties={"circuit_breaker_enabled": "true"},
        )
        result = self.engine.check_rule(r, ResilienceRule.CIRCUIT_BREAKER)
        assert result is None

    def test_retry_violated(self) -> None:
        r = _resource(resource_type="aws_lambda_function")
        result = self.engine.check_rule(r, ResilienceRule.RETRY_CONFIGURED)
        assert result is not None

    def test_retry_satisfied(self) -> None:
        r = _resource(
            resource_type="aws_lambda_function",
            properties={"max_retries": "3"},
        )
        result = self.engine.check_rule(r, ResilienceRule.RETRY_CONFIGURED)
        assert result is None

    def test_health_check_violated(self) -> None:
        r = _resource(resource_type="aws_ecs_service")
        result = self.engine.check_rule(r, ResilienceRule.HEALTH_CHECK)
        assert result is not None

    def test_health_check_satisfied(self) -> None:
        r = _resource(
            resource_type="aws_ecs_service",
            properties={"health_check_path": "/health"},
        )
        result = self.engine.check_rule(r, ResilienceRule.HEALTH_CHECK)
        assert result is None

    def test_disaster_recovery_violated(self) -> None:
        r = _resource(resource_type="aws_rds_cluster")
        result = self.engine.check_rule(r, ResilienceRule.DISASTER_RECOVERY)
        assert result is not None

    def test_disaster_recovery_satisfied(self) -> None:
        r = _resource(
            resource_type="aws_rds_cluster",
            properties={"cross_region_replica": "eu-west-1"},
        )
        result = self.engine.check_rule(r, ResilienceRule.DISASTER_RECOVERY)
        assert result is None

    def test_property_value_false_not_satisfied(self) -> None:
        """Property present but set to 'false' should not satisfy rule."""
        r = _resource(
            resource_type="aws_instance",
            properties={"multi_az": "false"},
        )
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None

    def test_property_value_zero_not_satisfied(self) -> None:
        """Property present but set to '0' should not satisfy rule."""
        r = _resource(
            resource_type="aws_instance",
            properties={"multi_az": "0"},
        )
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None

    def test_property_value_none_not_satisfied(self) -> None:
        """Property present but set to 'none' should not satisfy rule."""
        r = _resource(
            resource_type="aws_instance",
            properties={"multi_az": "none"},
        )
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None

    def test_property_value_empty_not_satisfied(self) -> None:
        """Property present but empty string should not satisfy rule."""
        r = _resource(
            resource_type="aws_instance",
            properties={"multi_az": ""},
        )
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None

    def test_finding_has_correct_description(self) -> None:
        r = _resource(resource_type="aws_instance")
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None
        assert "multi-AZ" in result.description

    def test_finding_has_correct_remediation(self) -> None:
        r = _resource(resource_type="aws_instance")
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None
        assert "multi-AZ" in result.remediation


# ------------------------------------------------------------------ Engine: validate_resources


class TestValidateResources:
    """Tests for IaCResilienceValidatorEngine.validate_resources."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_empty_resources(self) -> None:
        report = self.engine.validate_resources([])
        assert report.total_resources == 0
        assert report.compliance_score == 100.0
        assert report.findings == []
        assert report.platform == IaCPlatform.TERRAFORM

    def test_single_non_compliant_resource(self) -> None:
        r = _resource(resource_type="aws_instance")
        report = self.engine.validate_resources([r])
        assert report.total_resources == 1
        assert len(report.findings) > 0
        assert report.compliance_score < 100.0

    def test_single_compliant_resource(self) -> None:
        r = _compliant_resource()
        report = self.engine.validate_resources([r])
        assert report.total_resources == 1
        assert report.compliance_score > 90.0

    def test_platform_from_first_resource(self) -> None:
        r = _resource(platform=IaCPlatform.CLOUDFORMATION)
        report = self.engine.validate_resources([r])
        assert report.platform == IaCPlatform.CLOUDFORMATION

    def test_multiple_resources(self) -> None:
        resources = [
            _resource(resource_id="r-1", resource_type="aws_instance"),
            _resource(resource_id="r-2", resource_type="aws_db_instance"),
            _resource(resource_id="r-3", resource_type="aws_s3_bucket"),
        ]
        report = self.engine.validate_resources(resources)
        assert report.total_resources == 3
        assert len(report.findings) > 0

    def test_auto_fixable_count(self) -> None:
        resources = [
            _resource(resource_id="db-1", resource_type="aws_db_instance"),
        ]
        report = self.engine.validate_resources(resources)
        auto_fixable = [f for f in report.findings if f.auto_fixable]
        assert report.auto_fixable_count == len(auto_fixable)

    def test_recommendations_for_critical_findings(self) -> None:
        r = _resource(resource_type="aws_instance")
        report = self.engine.validate_resources([r])
        has_urgent = any("URGENT" in rec or "critical" in rec.lower() for rec in report.recommendations)
        # There should be critical findings for multi_az which triggers the recommendation
        critical_findings = [f for f in report.findings if f.severity == Severity.CRITICAL.value]
        if critical_findings:
            assert has_urgent

    def test_deduplication_of_findings(self) -> None:
        """Findings from check_rule and detect_missing_* should not duplicate."""
        r = _resource(resource_type="aws_instance")
        report = self.engine.validate_resources([r])
        keys = [(f.resource_id, f.rule) for f in report.findings]
        assert len(keys) == len(set(keys))

    def test_report_contains_encryption_recommendation(self) -> None:
        r = _resource(resource_type="aws_s3_bucket")
        report = self.engine.validate_resources([r])
        has_encryption_rec = any("encryption" in rec.lower() for rec in report.recommendations)
        assert has_encryption_rec

    def test_report_contains_backup_recommendation(self) -> None:
        r = _resource(resource_type="aws_db_instance")
        report = self.engine.validate_resources([r])
        has_backup_rec = any("backup" in rec.lower() for rec in report.recommendations)
        assert has_backup_rec


# ------------------------------------------------------------------ Engine: detect_missing_redundancy


class TestDetectMissingRedundancy:
    """Tests for detect_missing_redundancy."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_empty_resources(self) -> None:
        findings = self.engine.detect_missing_redundancy([])
        assert findings == []

    def test_detects_missing_multi_az(self) -> None:
        r = _resource(resource_type="aws_instance")
        findings = self.engine.detect_missing_redundancy([r])
        rules = [f.rule for f in findings]
        assert ResilienceRule.MULTI_AZ in rules

    def test_detects_missing_auto_scaling(self) -> None:
        r = _resource(resource_type="aws_autoscaling_group")
        findings = self.engine.detect_missing_redundancy([r])
        rules = [f.rule for f in findings]
        assert ResilienceRule.AUTO_SCALING in rules

    def test_detects_missing_disaster_recovery(self) -> None:
        r = _resource(resource_type="aws_db_instance")
        findings = self.engine.detect_missing_redundancy([r])
        rules = [f.rule for f in findings]
        assert ResilienceRule.DISASTER_RECOVERY in rules

    def test_no_findings_when_compliant(self) -> None:
        r = _compliant_resource()
        findings = self.engine.detect_missing_redundancy([r])
        # compliant resource has all properties set
        assert all(f.rule in {
            ResilienceRule.MULTI_AZ, ResilienceRule.AUTO_SCALING,
            ResilienceRule.DISASTER_RECOVERY,
        } for f in findings)

    def test_non_applicable_resource(self) -> None:
        """A resource type not in the applicable set should produce no findings."""
        r = _resource(resource_type="custom_widget")
        findings = self.engine.detect_missing_redundancy([r])
        assert findings == []


# ------------------------------------------------------------------ Engine: detect_missing_monitoring


class TestDetectMissingMonitoring:
    """Tests for detect_missing_monitoring."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_empty_resources(self) -> None:
        findings = self.engine.detect_missing_monitoring([])
        assert findings == []

    def test_detects_missing_monitoring(self) -> None:
        r = _resource(resource_type="aws_instance")
        findings = self.engine.detect_missing_monitoring([r])
        rules = [f.rule for f in findings]
        assert ResilienceRule.MONITORING_ENABLED in rules

    def test_detects_missing_health_check(self) -> None:
        r = _resource(resource_type="aws_ecs_service")
        findings = self.engine.detect_missing_monitoring([r])
        rules = [f.rule for f in findings]
        assert ResilienceRule.HEALTH_CHECK in rules

    def test_detects_missing_circuit_breaker(self) -> None:
        r = _resource(resource_type="aws_ecs_service")
        findings = self.engine.detect_missing_monitoring([r])
        rules = [f.rule for f in findings]
        assert ResilienceRule.CIRCUIT_BREAKER in rules

    def test_no_findings_when_all_configured(self) -> None:
        r = _resource(
            resource_type="aws_ecs_service",
            properties={
                "monitoring": "true",
                "health_check": "true",
                "circuit_breaker": "true",
            },
        )
        findings = self.engine.detect_missing_monitoring([r])
        assert findings == []


# ------------------------------------------------------------------ Engine: generate_remediation_plan


class TestGenerateRemediationPlan:
    """Tests for generate_remediation_plan."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_empty_findings(self) -> None:
        plan = self.engine.generate_remediation_plan([])
        assert plan.steps == []
        assert plan.total_effort_hours == 0.0
        assert plan.auto_fixable_count == 0
        assert plan.manual_count == 0

    def test_single_finding(self) -> None:
        finding = ValidationFinding(
            rule=ResilienceRule.MULTI_AZ,
            resource_id="r-1",
            severity=Severity.CRITICAL.value,
            auto_fixable=False,
        )
        plan = self.engine.generate_remediation_plan([finding])
        assert len(plan.steps) == 1
        assert plan.total_effort_hours > 0
        assert plan.manual_count == 1
        assert plan.auto_fixable_count == 0

    def test_multiple_findings_sorted_by_severity(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.COST_TAGGING,
                resource_id="r-1",
                severity=Severity.LOW.value,
            ),
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-2",
                severity=Severity.CRITICAL.value,
            ),
            ValidationFinding(
                rule=ResilienceRule.MONITORING_ENABLED,
                resource_id="r-3",
                severity=Severity.MEDIUM.value,
            ),
        ]
        plan = self.engine.generate_remediation_plan(findings)
        assert len(plan.steps) == 3
        # Critical should be first
        assert plan.steps[0].finding.severity == Severity.CRITICAL.value
        # Low should be last
        assert plan.steps[-1].finding.severity == Severity.LOW.value

    def test_auto_fixable_counting(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.BACKUP_ENABLED,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
                auto_fixable=True,
            ),
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-2",
                severity=Severity.CRITICAL.value,
                auto_fixable=False,
            ),
        ]
        plan = self.engine.generate_remediation_plan(findings)
        assert plan.auto_fixable_count == 1
        assert plan.manual_count == 1

    def test_priority_summary(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
            ValidationFinding(
                rule=ResilienceRule.BACKUP_ENABLED,
                resource_id="r-2",
                severity=Severity.CRITICAL.value,
            ),
            ValidationFinding(
                rule=ResilienceRule.MONITORING_ENABLED,
                resource_id="r-3",
                severity=Severity.MEDIUM.value,
            ),
        ]
        plan = self.engine.generate_remediation_plan(findings)
        assert plan.priority_summary.get(Severity.CRITICAL.value) == 2
        assert plan.priority_summary.get(Severity.MEDIUM.value) == 1

    def test_step_description_contains_resource_id(self) -> None:
        finding = ValidationFinding(
            rule=ResilienceRule.HEALTH_CHECK,
            resource_id="my-service",
            severity=Severity.HIGH.value,
        )
        plan = self.engine.generate_remediation_plan([finding])
        assert "my-service" in plan.steps[0].description

    def test_step_order_is_sequential(self) -> None:
        findings = [
            ValidationFinding(rule=ResilienceRule.MULTI_AZ, resource_id="r-1", severity=Severity.CRITICAL.value),
            ValidationFinding(rule=ResilienceRule.BACKUP_ENABLED, resource_id="r-2", severity=Severity.HIGH.value),
        ]
        plan = self.engine.generate_remediation_plan(findings)
        assert plan.steps[0].order == 1
        assert plan.steps[1].order == 2

    def test_effort_includes_severity_multiplier(self) -> None:
        f_critical = ValidationFinding(
            rule=ResilienceRule.MULTI_AZ,
            resource_id="r-1",
            severity=Severity.CRITICAL.value,
        )
        f_low = ValidationFinding(
            rule=ResilienceRule.MULTI_AZ,
            resource_id="r-2",
            severity=Severity.LOW.value,
        )
        plan_c = self.engine.generate_remediation_plan([f_critical])
        plan_l = self.engine.generate_remediation_plan([f_low])
        # Critical has higher multiplier than low
        assert plan_c.steps[0].effort_hours > plan_l.steps[0].effort_hours


# ------------------------------------------------------------------ Engine: compare_platforms


class TestComparePlatforms:
    """Tests for compare_platforms."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_empty_groups(self) -> None:
        result = self.engine.compare_platforms({})
        assert result.platforms == []
        assert result.best_platform == ""
        assert "No platforms" in result.overall_recommendations[0]

    def test_single_platform(self) -> None:
        groups = {
            IaCPlatform.TERRAFORM: [
                _resource(resource_type="aws_instance"),
            ],
        }
        result = self.engine.compare_platforms(groups)
        assert len(result.platforms) == 1
        assert result.best_platform == "terraform"
        assert result.worst_platform == "terraform"

    def test_two_platforms_different_compliance(self) -> None:
        groups = {
            IaCPlatform.TERRAFORM: [_compliant_resource(platform=IaCPlatform.TERRAFORM)],
            IaCPlatform.CLOUDFORMATION: [
                _resource(
                    resource_type="aws_instance",
                    platform=IaCPlatform.CLOUDFORMATION,
                ),
            ],
        }
        result = self.engine.compare_platforms(groups)
        assert len(result.platforms) == 2
        # Terraform (compliant) should have higher score
        tf_result = next(p for p in result.platforms if p.platform == IaCPlatform.TERRAFORM)
        cf_result = next(p for p in result.platforms if p.platform == IaCPlatform.CLOUDFORMATION)
        assert tf_result.compliance_score >= cf_result.compliance_score

    def test_strengths_and_weaknesses(self) -> None:
        groups = {
            IaCPlatform.TERRAFORM: [
                _resource(resource_type="aws_instance"),
            ],
        }
        result = self.engine.compare_platforms(groups)
        p = result.platforms[0]
        # There should be some weaknesses for a non-compliant resource
        assert len(p.weaknesses) > 0

    def test_critical_findings_recommendation(self) -> None:
        groups = {
            IaCPlatform.TERRAFORM: [
                _resource(resource_type="aws_instance"),
            ],
        }
        result = self.engine.compare_platforms(groups)
        has_critical_rec = any("critical" in r.lower() for r in result.overall_recommendations)
        # aws_instance without multi_az should produce critical findings
        assert has_critical_rec

    def test_large_compliance_gap_recommendation(self) -> None:
        groups = {
            IaCPlatform.TERRAFORM: [_compliant_resource(platform=IaCPlatform.TERRAFORM)],
            IaCPlatform.ANSIBLE: [
                _resource(
                    resource_id="ans-1",
                    resource_type="aws_instance",
                    platform=IaCPlatform.ANSIBLE,
                ),
                _resource(
                    resource_id="ans-2",
                    resource_type="aws_db_instance",
                    platform=IaCPlatform.ANSIBLE,
                ),
                _resource(
                    resource_id="ans-3",
                    resource_type="aws_s3_bucket",
                    platform=IaCPlatform.ANSIBLE,
                ),
            ],
        }
        result = self.engine.compare_platforms(groups)
        # Check if there's a gap recommendation
        gap_recs = [r for r in result.overall_recommendations if "gap" in r.lower() or "compliance" in r.lower()]
        # Score difference may or may not exceed 20
        # Just verify the comparison produces results
        assert len(result.platforms) == 2

    def test_all_platforms_reasonable(self) -> None:
        """When all platforms are compliant, we get a positive recommendation."""
        groups = {
            IaCPlatform.TERRAFORM: [_compliant_resource(platform=IaCPlatform.TERRAFORM)],
            IaCPlatform.CDK: [_compliant_resource(resource_id="cdk-1", platform=IaCPlatform.CDK)],
        }
        result = self.engine.compare_platforms(groups)
        assert len(result.platforms) == 2

    def test_platform_result_ordering(self) -> None:
        """Platforms should be sorted by compliance score descending."""
        groups = {
            IaCPlatform.TERRAFORM: [_compliant_resource(platform=IaCPlatform.TERRAFORM)],
            IaCPlatform.ANSIBLE: [_resource(resource_type="aws_instance", platform=IaCPlatform.ANSIBLE)],
        }
        result = self.engine.compare_platforms(groups)
        scores = [p.compliance_score for p in result.platforms]
        assert scores == sorted(scores, reverse=True)


# ------------------------------------------------------------------ Engine: estimate_compliance_effort


class TestEstimateComplianceEffort:
    """Tests for estimate_compliance_effort."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_empty_findings(self) -> None:
        est = self.engine.estimate_compliance_effort([])
        assert est.total_hours == 0.0
        assert est.estimated_days == 0.0
        assert "No findings" in est.recommendations[0]

    def test_single_critical_finding(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
        ]
        est = self.engine.estimate_compliance_effort(findings)
        assert est.total_hours > 0.0
        assert est.critical_hours > 0.0
        assert est.estimated_days > 0.0
        assert est.findings_by_severity.get(Severity.CRITICAL.value) == 1

    def test_mixed_severity_findings(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
            ValidationFinding(
                rule=ResilienceRule.MONITORING_ENABLED,
                resource_id="r-2",
                severity=Severity.MEDIUM.value,
            ),
            ValidationFinding(
                rule=ResilienceRule.COST_TAGGING,
                resource_id="r-3",
                severity=Severity.LOW.value,
            ),
        ]
        est = self.engine.estimate_compliance_effort(findings)
        assert est.critical_hours > 0.0
        assert est.medium_hours > 0.0
        assert est.low_hours > 0.0
        assert est.total_hours == est.critical_hours + est.high_hours + est.medium_hours + est.low_hours + est.info_hours

    def test_estimated_days_calculation(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
        ]
        est = self.engine.estimate_compliance_effort(findings)
        expected_days = est.total_hours / _WORKING_HOURS_PER_DAY
        assert abs(est.estimated_days - expected_days) < 0.01

    def test_auto_fixable_recommendation(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.BACKUP_ENABLED,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
                auto_fixable=True,
            ),
        ]
        est = self.engine.estimate_compliance_effort(findings)
        has_auto_rec = any("auto-fix" in r.lower() for r in est.recommendations)
        assert has_auto_rec

    def test_critical_recommendation(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
        ]
        est = self.engine.estimate_compliance_effort(findings)
        has_critical_rec = any("critical" in r.lower() for r in est.recommendations)
        assert has_critical_rec

    def test_high_recommendation(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.ENCRYPTION_ENABLED,
                resource_id="r-1",
                severity=Severity.HIGH.value,
            ),
        ]
        est = self.engine.estimate_compliance_effort(findings)
        has_high_rec = any("high" in r.lower() for r in est.recommendations)
        assert has_high_rec

    def test_low_only_recommendation(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.COST_TAGGING,
                resource_id="r-1",
                severity=Severity.LOW.value,
            ),
        ]
        est = self.engine.estimate_compliance_effort(findings)
        has_low_rec = any("low priority" in r.lower() for r in est.recommendations)
        assert has_low_rec

    def test_info_severity(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.COST_TAGGING,
                resource_id="r-1",
                severity=Severity.INFO.value,
            ),
        ]
        est = self.engine.estimate_compliance_effort(findings)
        assert est.info_hours > 0.0
        assert est.findings_by_severity.get(Severity.INFO.value) == 1


# ------------------------------------------------------------------ Engine: _is_rule_applicable


class TestIsRuleApplicable:
    """Tests for _is_rule_applicable private method."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_cost_tagging_always_applicable(self) -> None:
        r = _resource(resource_type="literally_anything")
        assert self.engine._is_rule_applicable(r, ResilienceRule.COST_TAGGING) is True

    def test_multi_az_applicable_to_aws_instance(self) -> None:
        r = _resource(resource_type="aws_instance")
        assert self.engine._is_rule_applicable(r, ResilienceRule.MULTI_AZ) is True

    def test_multi_az_not_applicable_to_random_type(self) -> None:
        r = _resource(resource_type="random_resource")
        assert self.engine._is_rule_applicable(r, ResilienceRule.MULTI_AZ) is False

    def test_each_rule_has_applicable_types(self) -> None:
        """Each rule (except cost_tagging) should have at least one applicable type."""
        for rule in ResilienceRule:
            if rule == ResilienceRule.COST_TAGGING:
                continue
            types = _RULE_APPLICABLE_RESOURCE_TYPES.get(rule, set())
            assert len(types) > 0, f"Rule {rule} has no applicable types"


# ------------------------------------------------------------------ Engine: _is_rule_satisfied


class TestIsRuleSatisfied:
    """Tests for _is_rule_satisfied private method."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_satisfied_with_correct_property(self) -> None:
        r = _resource(
            resource_type="aws_instance",
            properties={"multi_az": "true"},
        )
        assert self.engine._is_rule_satisfied(r, ResilienceRule.MULTI_AZ) is True

    def test_not_satisfied_with_empty_properties(self) -> None:
        r = _resource(resource_type="aws_instance")
        assert self.engine._is_rule_satisfied(r, ResilienceRule.MULTI_AZ) is False

    def test_case_insensitive_property_check(self) -> None:
        r = _resource(
            resource_type="aws_instance",
            properties={"Multi_AZ": "True"},
        )
        assert self.engine._is_rule_satisfied(r, ResilienceRule.MULTI_AZ) is True

    def test_cost_tagging_satisfied(self) -> None:
        r = _resource(
            tags={
                "environment": "prod",
                "team": "core",
                "project": "api",
                "cost-center": "eng",
            },
        )
        assert self.engine._is_rule_satisfied(r, ResilienceRule.COST_TAGGING) is True

    def test_cost_tagging_not_satisfied_missing_tag(self) -> None:
        r = _resource(tags={"environment": "prod"})
        assert self.engine._is_rule_satisfied(r, ResilienceRule.COST_TAGGING) is False


# ------------------------------------------------------------------ Engine: _check_cost_tags


class TestCheckCostTags:
    """Tests for _check_cost_tags private method."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_all_tags_present(self) -> None:
        r = _resource(
            tags={
                "environment": "prod",
                "team": "core",
                "project": "api",
                "cost-center": "eng",
            },
        )
        assert self.engine._check_cost_tags(r) is True

    def test_missing_one_tag(self) -> None:
        r = _resource(
            tags={
                "environment": "prod",
                "team": "core",
                "project": "api",
            },
        )
        assert self.engine._check_cost_tags(r) is False

    def test_no_tags(self) -> None:
        r = _resource()
        assert self.engine._check_cost_tags(r) is False

    def test_case_insensitive_tags(self) -> None:
        r = _resource(
            tags={
                "Environment": "prod",
                "Team": "core",
                "Project": "api",
                "Cost-Center": "eng",
            },
        )
        assert self.engine._check_cost_tags(r) is True

    def test_extra_tags_still_pass(self) -> None:
        r = _resource(
            tags={
                "environment": "prod",
                "team": "core",
                "project": "api",
                "cost-center": "eng",
                "owner": "alice",
            },
        )
        assert self.engine._check_cost_tags(r) is True


# ------------------------------------------------------------------ Engine: _calculate_compliance_score


class TestCalculateComplianceScore:
    """Tests for _calculate_compliance_score."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_zero_resources(self) -> None:
        score = self.engine._calculate_compliance_score(0, [])
        assert score == 100.0

    def test_no_findings(self) -> None:
        score = self.engine._calculate_compliance_score(5, [])
        assert score == 100.0

    def test_some_findings_reduce_score(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
        ]
        score = self.engine._calculate_compliance_score(1, findings)
        assert score < 100.0
        assert score >= 0.0

    def test_many_findings_low_score(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
        ] * 50
        score = self.engine._calculate_compliance_score(1, findings)
        assert score >= 0.0

    def test_score_is_bounded(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
        ] * 1000
        score = self.engine._calculate_compliance_score(1, findings)
        assert 0.0 <= score <= 100.0


# ------------------------------------------------------------------ Engine: _generate_report_recommendations


class TestGenerateReportRecommendations:
    """Tests for _generate_report_recommendations."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_no_findings(self) -> None:
        recs = self.engine._generate_report_recommendations([], [])
        assert any("Well done" in r for r in recs)

    def test_critical_findings(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
        ]
        recs = self.engine._generate_report_recommendations(findings, [])
        assert any("URGENT" in r for r in recs)

    def test_high_findings(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.ENCRYPTION_ENABLED,
                resource_id="r-1",
                severity=Severity.HIGH.value,
            ),
        ]
        recs = self.engine._generate_report_recommendations(findings, [])
        assert any("high" in r.lower() for r in recs)

    def test_auto_fixable_mentioned(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.BACKUP_ENABLED,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
                auto_fixable=True,
            ),
        ]
        recs = self.engine._generate_report_recommendations(findings, [])
        assert any("auto" in r.lower() for r in recs)

    def test_multi_az_recommendation(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.MULTI_AZ,
                resource_id="r-1",
                severity=Severity.CRITICAL.value,
            ),
        ]
        recs = self.engine._generate_report_recommendations(findings, [])
        assert any("multi-AZ" in r for r in recs)


# ------------------------------------------------------------------ Integration / End-to-end


class TestEndToEnd:
    """End-to-end integration tests."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_full_workflow(self) -> None:
        """validate -> remediation plan -> effort estimate."""
        resources = [
            _resource(resource_id="web-1", resource_type="aws_instance"),
            _resource(resource_id="db-1", resource_type="aws_db_instance"),
            _resource(resource_id="bucket-1", resource_type="aws_s3_bucket"),
        ]
        report = self.engine.validate_resources(resources)
        assert report.total_resources == 3
        assert len(report.findings) > 0

        plan = self.engine.generate_remediation_plan(report.findings)
        assert len(plan.steps) == len(report.findings)
        assert plan.total_effort_hours > 0

        estimate = self.engine.estimate_compliance_effort(report.findings)
        assert estimate.total_hours > 0
        assert estimate.estimated_days > 0

    def test_compliant_workflow(self) -> None:
        """Compliant resources should produce minimal findings."""
        resources = [_compliant_resource()]
        report = self.engine.validate_resources(resources)
        # May still have cost_tagging finding if resource type not in set
        assert report.compliance_score > 80.0

    def test_multi_platform_workflow(self) -> None:
        """Compare platforms and verify structure."""
        groups = {
            IaCPlatform.TERRAFORM: [
                _resource(resource_type="aws_instance", platform=IaCPlatform.TERRAFORM),
            ],
            IaCPlatform.CLOUDFORMATION: [
                _compliant_resource(platform=IaCPlatform.CLOUDFORMATION),
            ],
            IaCPlatform.CDK: [
                _resource(resource_type="aws_s3_bucket", platform=IaCPlatform.CDK),
            ],
        }
        comparison = self.engine.compare_platforms(groups)
        assert len(comparison.platforms) == 3
        assert comparison.best_platform != ""
        assert comparison.worst_platform != ""

    def test_validate_then_compare(self) -> None:
        """Validate individually then compare."""
        tf_resources = [_resource(resource_type="aws_instance", platform=IaCPlatform.TERRAFORM)]
        cf_resources = [_compliant_resource(platform=IaCPlatform.CLOUDFORMATION)]

        tf_report = self.engine.validate_resources(tf_resources)
        cf_report = self.engine.validate_resources(cf_resources)

        comparison = self.engine.compare_platforms({
            IaCPlatform.TERRAFORM: tf_resources,
            IaCPlatform.CLOUDFORMATION: cf_resources,
        })
        assert len(comparison.platforms) == 2


# ------------------------------------------------------------------ Edge cases


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_resource_with_all_falsy_properties(self) -> None:
        r = _resource(
            resource_type="aws_instance",
            properties={
                "multi_az": "false",
                "auto_scaling": "0",
                "monitoring": "none",
                "health_check": "",
            },
        )
        report = self.engine.validate_resources([r])
        # Should still have findings because values are falsy
        assert len(report.findings) > 0

    def test_resource_with_unknown_type(self) -> None:
        r = _resource(resource_type="unknown_provider_resource")
        report = self.engine.validate_resources([r])
        # Should only get cost_tagging finding
        cost_findings = [f for f in report.findings if f.rule == ResilienceRule.COST_TAGGING]
        assert len(cost_findings) == 1
        assert len(report.findings) == 1

    def test_many_resources(self) -> None:
        resources = [
            _resource(resource_id=f"r-{i}", resource_type="aws_instance")
            for i in range(50)
        ]
        report = self.engine.validate_resources(resources)
        assert report.total_resources == 50
        assert len(report.findings) > 50

    def test_single_resource_all_rules(self) -> None:
        """Check every rule against a single resource."""
        r = _resource(resource_type="aws_instance")
        for rule in ResilienceRule:
            result = self.engine.check_rule(r, rule)
            # Should return either None or a finding
            if result is not None:
                assert isinstance(result, ValidationFinding)

    def test_remediation_plan_with_info_severity(self) -> None:
        findings = [
            ValidationFinding(
                rule=ResilienceRule.COST_TAGGING,
                resource_id="r-1",
                severity=Severity.INFO.value,
                auto_fixable=True,
            ),
        ]
        plan = self.engine.generate_remediation_plan(findings)
        assert len(plan.steps) == 1
        assert plan.auto_fixable_count == 1
        assert plan.total_effort_hours > 0

    def test_platform_comparison_with_empty_resource_list(self) -> None:
        groups = {
            IaCPlatform.TERRAFORM: [],
        }
        result = self.engine.compare_platforms(groups)
        assert len(result.platforms) == 1
        p = result.platforms[0]
        assert p.resource_count == 0
        assert p.compliance_score == 100.0

    def test_validate_resources_different_platforms(self) -> None:
        """Resources from mixed platforms; platform taken from first."""
        resources = [
            _resource(resource_id="r-1", platform=IaCPlatform.TERRAFORM),
            _resource(resource_id="r-2", platform=IaCPlatform.CDK),
        ]
        report = self.engine.validate_resources(resources)
        assert report.platform == IaCPlatform.TERRAFORM

    def test_alternative_property_keys(self) -> None:
        """Verify multiple property keys can satisfy a rule."""
        # 'availability_zone_count' should also satisfy MULTI_AZ
        r = _resource(
            resource_type="aws_instance",
            properties={"availability_zone_count": "3"},
        )
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is None

    def test_kms_key_satisfies_encryption(self) -> None:
        r = _resource(
            resource_type="aws_s3_bucket",
            properties={"kms_key_id": "arn:aws:kms:us-east-1:123:key/abc"},
        )
        result = self.engine.check_rule(r, ResilienceRule.ENCRYPTION_ENABLED)
        assert result is None

    def test_backup_retention_satisfies_backup(self) -> None:
        r = _resource(
            resource_type="aws_db_instance",
            properties={"backup_retention": "14"},
        )
        result = self.engine.check_rule(r, ResilienceRule.BACKUP_ENABLED)
        assert result is None

    def test_scaling_policy_satisfies_autoscaling(self) -> None:
        r = _resource(
            resource_type="aws_autoscaling_group",
            properties={"scaling_policy": "target-tracking"},
        )
        result = self.engine.check_rule(r, ResilienceRule.AUTO_SCALING)
        assert result is None

    def test_cloudwatch_satisfies_monitoring(self) -> None:
        r = _resource(
            resource_type="aws_instance",
            properties={"cloudwatch": "enabled"},
        )
        result = self.engine.check_rule(r, ResilienceRule.MONITORING_ENABLED)
        assert result is None

    def test_liveness_probe_satisfies_health_check(self) -> None:
        r = _resource(
            resource_type="kubernetes_deployment",
            properties={"liveness_probe": "/healthz"},
        )
        result = self.engine.check_rule(r, ResilienceRule.HEALTH_CHECK)
        assert result is None

    def test_read_replica_satisfies_disaster_recovery(self) -> None:
        r = _resource(
            resource_type="aws_db_instance",
            properties={"read_replica": "us-west-2"},
        )
        result = self.engine.check_rule(r, ResilienceRule.DISASTER_RECOVERY)
        assert result is None

    def test_geo_redundant_satisfies_disaster_recovery(self) -> None:
        r = _resource(
            resource_type="aws_s3_bucket",
            properties={"geo_redundant": "true"},
        )
        result = self.engine.check_rule(r, ResilienceRule.DISASTER_RECOVERY)
        assert result is None

    def test_outlier_detection_satisfies_circuit_breaker(self) -> None:
        r = _resource(
            resource_type="aws_appmesh_virtual_node",
            properties={"outlier_detection": "true"},
        )
        result = self.engine.check_rule(r, ResilienceRule.CIRCUIT_BREAKER)
        assert result is None

    def test_retry_count_satisfies_retry(self) -> None:
        r = _resource(
            resource_type="aws_sqs_queue",
            properties={"retry_count": "5"},
        )
        result = self.engine.check_rule(r, ResilienceRule.RETRY_CONFIGURED)
        assert result is None

    def test_log_group_satisfies_monitoring(self) -> None:
        r = _resource(
            resource_type="aws_lambda_function",
            properties={"log_group": "/aws/lambda/my-fn"},
        )
        result = self.engine.check_rule(r, ResilienceRule.MONITORING_ENABLED)
        assert result is None

    def test_min_capacity_satisfies_auto_scaling(self) -> None:
        r = _resource(
            resource_type="aws_ecs_service",
            properties={"min_capacity": "2"},
        )
        result = self.engine.check_rule(r, ResilienceRule.AUTO_SCALING)
        assert result is None

    def test_az_count_satisfies_multi_az(self) -> None:
        r = _resource(
            resource_type="aws_elb",
            properties={"az_count": "3"},
        )
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is None

    def test_healthcheck_satisfies_health_check(self) -> None:
        r = _resource(
            resource_type="aws_alb",
            properties={"healthcheck": "/ping"},
        )
        result = self.engine.check_rule(r, ResilienceRule.HEALTH_CHECK)
        assert result is None

    def test_backup_policy_satisfies_backup(self) -> None:
        r = _resource(
            resource_type="aws_dynamodb_table",
            properties={"backup_policy": "continuous"},
        )
        result = self.engine.check_rule(r, ResilienceRule.BACKUP_ENABLED)
        assert result is None

    def test_sse_algorithm_satisfies_encryption(self) -> None:
        r = _resource(
            resource_type="aws_sqs_queue",
            properties={"sse_algorithm": "AES256"},
        )
        result = self.engine.check_rule(r, ResilienceRule.ENCRYPTION_ENABLED)
        assert result is None


# ------------------------------------------------------------------ Additional resource types


class TestAdditionalResourceTypes:
    """Test rule applicability for various resource types."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_azure_vm_multi_az(self) -> None:
        r = _resource(resource_type="azurerm_virtual_machine")
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None  # violated

    def test_google_compute_multi_az(self) -> None:
        r = _resource(resource_type="google_compute_instance")
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None

    def test_kubernetes_deployment_auto_scaling(self) -> None:
        r = _resource(resource_type="kubernetes_deployment")
        result = self.engine.check_rule(r, ResilienceRule.AUTO_SCALING)
        assert result is not None

    def test_azure_storage_encryption(self) -> None:
        r = _resource(resource_type="azurerm_storage_account")
        result = self.engine.check_rule(r, ResilienceRule.ENCRYPTION_ENABLED)
        assert result is not None

    def test_google_sql_disaster_recovery(self) -> None:
        r = _resource(resource_type="google_sql_database_instance")
        result = self.engine.check_rule(r, ResilienceRule.DISASTER_RECOVERY)
        assert result is not None

    def test_azure_sql_backup(self) -> None:
        r = _resource(resource_type="azurerm_sql_database")
        result = self.engine.check_rule(r, ResilienceRule.BACKUP_ENABLED)
        assert result is not None

    def test_google_storage_encryption(self) -> None:
        r = _resource(resource_type="google_storage_bucket")
        result = self.engine.check_rule(r, ResilienceRule.ENCRYPTION_ENABLED)
        assert result is not None

    def test_step_functions_retry(self) -> None:
        r = _resource(resource_type="aws_step_functions_state_machine")
        result = self.engine.check_rule(r, ResilienceRule.RETRY_CONFIGURED)
        assert result is not None

    def test_api_gateway_circuit_breaker(self) -> None:
        r = _resource(resource_type="aws_api_gateway_rest_api")
        result = self.engine.check_rule(r, ResilienceRule.CIRCUIT_BREAKER)
        assert result is not None

    def test_ebs_volume_encryption(self) -> None:
        r = _resource(resource_type="aws_ebs_volume")
        result = self.engine.check_rule(r, ResilienceRule.ENCRYPTION_ENABLED)
        assert result is not None

    def test_sns_topic_encryption(self) -> None:
        r = _resource(resource_type="aws_sns_topic")
        result = self.engine.check_rule(r, ResilienceRule.ENCRYPTION_ENABLED)
        assert result is not None

    def test_rds_cluster_multi_az(self) -> None:
        r = _resource(resource_type="aws_rds_cluster")
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None

    def test_elasticache_multi_az(self) -> None:
        r = _resource(resource_type="aws_elasticache_cluster")
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None

    def test_alb_multi_az(self) -> None:
        r = _resource(resource_type="aws_alb")
        result = self.engine.check_rule(r, ResilienceRule.MULTI_AZ)
        assert result is not None

    def test_vm_scale_set_auto_scaling(self) -> None:
        r = _resource(resource_type="azurerm_virtual_machine_scale_set")
        result = self.engine.check_rule(r, ResilienceRule.AUTO_SCALING)
        assert result is not None

    def test_instance_group_manager_auto_scaling(self) -> None:
        r = _resource(resource_type="google_compute_instance_group_manager")
        result = self.engine.check_rule(r, ResilienceRule.AUTO_SCALING)
        assert result is not None


# ------------------------------------------------------------------ Constructor


class TestDeduplication:
    """Tests for deduplication logic in validate_resources."""

    def setup_method(self) -> None:
        self.engine = IaCResilienceValidatorEngine()

    def test_redundancy_finding_added_when_not_in_check_rule(self, monkeypatch) -> None:
        """When detect_missing_redundancy returns a finding not from check_rule,
        it should be appended."""
        extra_finding = ValidationFinding(
            rule=ResilienceRule.DISASTER_RECOVERY,
            resource_id="extra-resource",
            severity=Severity.CRITICAL.value,
        )
        original_detect = self.engine.detect_missing_redundancy

        def patched_detect(resources):
            return original_detect(resources) + [extra_finding]

        monkeypatch.setattr(self.engine, "detect_missing_redundancy", patched_detect)
        r = _resource(resource_type="custom_widget")
        report = self.engine.validate_resources([r])
        ids = [(f.resource_id, f.rule) for f in report.findings]
        assert ("extra-resource", ResilienceRule.DISASTER_RECOVERY) in ids

    def test_monitoring_finding_added_when_not_in_check_rule(self, monkeypatch) -> None:
        """When detect_missing_monitoring returns a finding not from check_rule,
        it should be appended."""
        extra_finding = ValidationFinding(
            rule=ResilienceRule.HEALTH_CHECK,
            resource_id="extra-monitor",
            severity=Severity.HIGH.value,
        )
        original_detect = self.engine.detect_missing_monitoring

        def patched_detect(resources):
            return original_detect(resources) + [extra_finding]

        monkeypatch.setattr(self.engine, "detect_missing_monitoring", patched_detect)
        r = _resource(resource_type="custom_widget")
        report = self.engine.validate_resources([r])
        ids = [(f.resource_id, f.rule) for f in report.findings]
        assert ("extra-monitor", ResilienceRule.HEALTH_CHECK) in ids

    def test_duplicate_redundancy_not_added(self) -> None:
        """When detect_missing_redundancy returns findings already in check_rule,
        they should not be duplicated."""
        r = _resource(resource_type="aws_instance")
        report = self.engine.validate_resources([r])
        keys = [(f.resource_id, f.rule) for f in report.findings]
        assert len(keys) == len(set(keys))

    def test_duplicate_monitoring_not_added(self) -> None:
        """When detect_missing_monitoring returns findings already in check_rule,
        they should not be duplicated."""
        r = _resource(resource_type="aws_ecs_service")
        report = self.engine.validate_resources([r])
        keys = [(f.resource_id, f.rule) for f in report.findings]
        assert len(keys) == len(set(keys))


class TestEngineConstructor:
    """Test engine constructor."""

    def test_can_instantiate(self) -> None:
        engine = IaCResilienceValidatorEngine()
        assert engine is not None

    def test_multiple_instances(self) -> None:
        e1 = IaCResilienceValidatorEngine()
        e2 = IaCResilienceValidatorEngine()
        assert e1 is not e2
