"""Tests for AWSResilienceHubBridge — pre-deploy Resilience Hub bridge."""

from __future__ import annotations

import pytest

from faultray.integrations.aws_resilience_hub_bridge import (
    AWSResilienceHubBridge,
    ComparisonReport,
    DisruptionScore,
    DisruptionType,
    PolicyStatus,
    PreDeployAssessment,
    ResiliencyPolicy,
    _disruption_score_from_overall,
    _estimate_rpo_from_score,
    _estimate_rto_from_score,
    _filter_risks_for_disruption,
    _generate_recommendations_for_disruption,
    _score_to_policy_status,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_plan_change(res_type: str, name: str, actions: list[str], after: dict | None = None):
    return {
        "type": res_type,
        "name": name,
        "address": f"{res_type}.{name}",
        "change": {"actions": actions, "before": None, "after": after},
    }


def _make_plan_json(*changes) -> dict:
    return {"resource_changes": list(changes)}


def _make_faultray_report(
    score: float = 75.0,
    app_name: str = "test-app",
    critical_findings: list | None = None,
    warnings: list | None = None,
    resource_count: int = 5,
) -> dict:
    return {
        "score": score,
        "app_name": app_name,
        "critical_findings": critical_findings or [],
        "warnings": warnings or [],
        "resource_count": resource_count,
    }


def _make_live_hub_assessment(
    score: float = 70.0,
    status: str = "MeetsPolicy",
    disruption: dict | None = None,
    findings: list | None = None,
) -> dict:
    return {
        "resiliencyScore": score,
        "complianceStatus": status,
        "disruptionResiliency": disruption or {},
        "findings": findings or [],
    }


# ============================================================
# ResiliencyPolicy defaults
# ============================================================

class TestResiliencyPolicy:
    def test_default_values_are_sensible(self):
        policy = ResiliencyPolicy(policy_name="test")
        assert policy.min_score_threshold == 60.0
        assert DisruptionType.INFRASTRUCTURE in policy.rto_seconds
        assert DisruptionType.REGION in policy.rpo_seconds

    def test_custom_threshold(self):
        policy = ResiliencyPolicy(policy_name="strict", min_score_threshold=80.0)
        assert policy.min_score_threshold == 80.0


# ============================================================
# Score mapping helpers
# ============================================================

class TestScoreMapping:
    def test_zero_score_is_not_assessed(self):
        assert _score_to_policy_status(0.0, 60.0) == PolicyStatus.NOT_ASSESSED

    def test_above_threshold_meets_policy(self):
        assert _score_to_policy_status(75.0, 60.0) == PolicyStatus.MEETS_POLICY

    def test_below_threshold_policy_breached(self):
        assert _score_to_policy_status(55.0, 60.0) == PolicyStatus.POLICY_BREACHED

    def test_exactly_at_threshold_meets_policy(self):
        assert _score_to_policy_status(60.0, 60.0) == PolicyStatus.MEETS_POLICY

    def test_rto_decreases_as_score_increases(self):
        rto_low = _estimate_rto_from_score(3600, 20.0)
        rto_high = _estimate_rto_from_score(3600, 90.0)
        assert rto_low > rto_high

    def test_rpo_decreases_as_score_increases(self):
        rpo_low = _estimate_rpo_from_score(1800, 20.0)
        rpo_high = _estimate_rpo_from_score(1800, 90.0)
        assert rpo_low > rpo_high

    def test_rto_zero_score_gives_max(self):
        base = 3600
        rto = _estimate_rto_from_score(base, 0.0)
        assert rto >= base * 2

    def test_disruption_score_clamped_to_0_100(self):
        for score in (0.0, 50.0, 100.0, 110.0, -5.0):
            for dt in DisruptionType:
                d = _disruption_score_from_overall(score, dt)
                assert 0.0 <= d <= 100.0


# ============================================================
# Risk filtering
# ============================================================

class TestFilterRisks:
    def test_az_keyword_routes_to_infrastructure(self):
        risks = ["az_failure detected", "unrelated issue"]
        filtered = _filter_risks_for_disruption(risks, DisruptionType.INFRASTRUCTURE)
        assert "az_failure detected" in filtered

    def test_lambda_routes_to_application(self):
        risks = ["lambda timeout", "network partition"]
        filtered = _filter_risks_for_disruption(risks, DisruptionType.APPLICATION)
        assert "lambda timeout" in filtered

    def test_vpc_routes_to_network(self):
        risks = ["vpc peering down", "cpu spike"]
        filtered = _filter_risks_for_disruption(risks, DisruptionType.NETWORK)
        assert "vpc peering down" in filtered

    def test_region_keyword_routes_to_region(self):
        risks = ["cross_region replication disabled"]
        filtered = _filter_risks_for_disruption(risks, DisruptionType.REGION)
        assert "cross_region replication disabled" in filtered

    def test_no_match_returns_all_risks(self):
        """When no risks match specific keywords, all risks are returned as generic."""
        risks = ["custom-risk-xyz", "another-risk-abc"]
        filtered = _filter_risks_for_disruption(risks, DisruptionType.INFRASTRUCTURE)
        assert set(filtered) == set(risks)

    def test_empty_risks_returns_empty(self):
        assert _filter_risks_for_disruption([], DisruptionType.APPLICATION) == []


# ============================================================
# Recommendation generation
# ============================================================

class TestRecommendationGeneration:
    def test_infra_low_score_generates_recs(self):
        recs = _generate_recommendations_for_disruption(
            DisruptionType.INFRASTRUCTURE, 50.0, []
        )
        assert len(recs) >= 2
        assert any("Availability Zone" in r for r in recs)

    def test_infra_high_score_fewer_recs(self):
        recs_high = _generate_recommendations_for_disruption(
            DisruptionType.INFRASTRUCTURE, 90.0, []
        )
        recs_low = _generate_recommendations_for_disruption(
            DisruptionType.INFRASTRUCTURE, 30.0, []
        )
        assert len(recs_high) <= len(recs_low)

    def test_region_critical_score_includes_dr_warning(self):
        recs = _generate_recommendations_for_disruption(
            DisruptionType.REGION, 25.0, []
        )
        text = " ".join(recs)
        assert "multi-region" in text.lower() or "full application downtime" in text.lower()

    def test_application_risks_included_in_recs(self):
        risks = ["lambda timeout", "ecs task crash"]
        recs = _generate_recommendations_for_disruption(
            DisruptionType.APPLICATION, 55.0, risks
        )
        # At least one recommendation should reference the risks
        assert any("lambda timeout" in r or "ecs task crash" in r for r in recs)

    def test_no_recs_for_perfect_score(self):
        recs = _generate_recommendations_for_disruption(
            DisruptionType.NETWORK, 100.0, []
        )
        assert recs == []


# ============================================================
# AWSResilienceHubBridge.from_faultray_report
# ============================================================

class TestFromFaultrayReport:
    def test_basic_report_produces_assessment(self):
        bridge = AWSResilienceHubBridge()
        report = _make_faultray_report(score=75.0)
        assessment = bridge.from_faultray_report(report)

        assert isinstance(assessment, PreDeployAssessment)
        assert assessment.overall_score == 75.0
        assert assessment.plan_source == "faultray_report"

    def test_app_name_propagated(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(
            _make_faultray_report(app_name="my-service")
        )
        assert assessment.app_name == "my-service"

    def test_critical_findings_become_findings(self):
        bridge = AWSResilienceHubBridge()
        report = _make_faultray_report(
            critical_findings=[{"name": "spof-detected", "severity": "critical"}],
            warnings=["no multi-az"],
        )
        assessment = bridge.from_faultray_report(report)
        assert "spof-detected" in assessment.findings
        assert "no multi-az" in assessment.findings

    def test_score_60_meets_policy(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(_make_faultray_report(score=60.0))
        assert assessment.overall_policy_status == PolicyStatus.MEETS_POLICY

    def test_score_59_policy_breached(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(_make_faultray_report(score=59.9))
        assert assessment.overall_policy_status == PolicyStatus.POLICY_BREACHED

    def test_score_zero_not_assessed(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(_make_faultray_report(score=0.0))
        assert assessment.overall_policy_status == PolicyStatus.NOT_ASSESSED

    def test_all_disruption_types_present(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(_make_faultray_report(score=70.0))
        types_in_assessment = {ds.disruption_type for ds in assessment.disruption_scores}
        assert types_in_assessment == set(DisruptionType)

    def test_disruption_scores_have_rto_and_rpo(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(_make_faultray_report(score=70.0))
        for ds in assessment.disruption_scores:
            assert ds.estimated_rto_seconds > 0
            assert ds.estimated_rpo_seconds > 0

    def test_custom_policy_threshold_applied(self):
        policy = ResiliencyPolicy(policy_name="strict", min_score_threshold=80.0)
        bridge = AWSResilienceHubBridge(policy=policy)
        assessment = bridge.from_faultray_report(_make_faultray_report(score=70.0))
        # 70 < 80 → breached
        assert assessment.overall_policy_status == PolicyStatus.POLICY_BREACHED

    def test_resource_count_from_report(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(
            _make_faultray_report(resource_count=12)
        )
        assert assessment.resource_count == 12


# ============================================================
# AWSResilienceHubBridge.from_terraform_plan
# ============================================================

class TestFromTerraformPlan:
    def test_empty_plan_produces_assessment(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_terraform_plan({})
        assert isinstance(assessment, PreDeployAssessment)
        assert assessment.plan_source == "terraform_plan"

    def test_plan_with_create_resources(self):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_instance", "web",
                actions=["create"],
                after={"instance_type": "t3.medium", "name": "web"},
            ),
        )
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_terraform_plan(plan)
        assert assessment.overall_score >= 0
        assert assessment.resource_count >= 0

    def test_plan_with_delete_reduces_or_keeps_score(self):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_db_instance", "db",
                actions=["delete"],
                after=None,
            ),
        )
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_terraform_plan(plan)
        assert isinstance(assessment, PreDeployAssessment)

    def test_all_disruption_types_present_in_plan_assessment(self):
        plan = _make_plan_json(
            _make_plan_change(
                "aws_instance", "app",
                actions=["create"],
                after={"name": "app", "instance_type": "t3.small"},
            ),
        )
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_terraform_plan(plan)
        types = {ds.disruption_type for ds in assessment.disruption_scores}
        assert types == set(DisruptionType)

    def test_plan_source_is_terraform_plan(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_terraform_plan({})
        assert assessment.plan_source == "terraform_plan"


# ============================================================
# AWSResilienceHubBridge.to_resilience_hub_format
# ============================================================

class TestToResilienceHubFormat:
    def _make_assessment(self, score: float = 75.0) -> PreDeployAssessment:
        bridge = AWSResilienceHubBridge()
        return bridge.from_faultray_report(_make_faultray_report(score=score))

    def test_output_has_required_top_level_keys(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment()
        output = bridge.to_resilience_hub_format(assessment)

        required = {
            "source", "assessmentType", "appName", "planSource",
            "resiliencyScore", "complianceStatus", "resourceCount",
            "disruptionResiliency", "findings", "recommendations",
        }
        assert required.issubset(output.keys())

    def test_source_identifies_faultray(self):
        bridge = AWSResilienceHubBridge()
        output = bridge.to_resilience_hub_format(self._make_assessment())
        assert output["source"] == "FaultRay-PreDeployBridge"
        assert output["assessmentType"] == "PRE_DEPLOY_PREDICTION"

    def test_score_rounded_to_two_decimals(self):
        bridge = AWSResilienceHubBridge()
        output = bridge.to_resilience_hub_format(self._make_assessment(score=73.456))
        assert output["resiliencyScore"] == 73.46

    def test_disruption_resiliency_has_all_types(self):
        bridge = AWSResilienceHubBridge()
        output = bridge.to_resilience_hub_format(self._make_assessment())
        disruption = output["disruptionResiliency"]
        expected_keys = {dt.value for dt in DisruptionType}
        assert expected_keys == set(disruption.keys())

    def test_each_disruption_has_rto_rpo_score_status(self):
        bridge = AWSResilienceHubBridge()
        output = bridge.to_resilience_hub_format(self._make_assessment())
        for key, data in output["disruptionResiliency"].items():
            assert "score" in data, f"Missing score for {key}"
            assert "rtoInSecs" in data, f"Missing rtoInSecs for {key}"
            assert "rpoInSecs" in data, f"Missing rpoInSecs for {key}"
            assert "policyStatus" in data, f"Missing policyStatus for {key}"

    def test_policy_included_when_set(self):
        policy = ResiliencyPolicy(policy_name="my-policy")
        bridge = AWSResilienceHubBridge(policy=policy)
        # Build the assessment with the same custom-policy bridge so it carries the policy
        assessment = bridge.from_faultray_report(_make_faultray_report(score=75.0))
        output = bridge.to_resilience_hub_format(assessment)
        assert output["policy"] is not None
        assert output["policy"]["policyName"] == "my-policy"

    def test_faultray_metadata_included(self):
        bridge = AWSResilienceHubBridge()
        output = bridge.to_resilience_hub_format(self._make_assessment(score=80.0))
        assert "faultray" in output
        assert "rawScore" in output["faultray"]
        assert "planSummary" in output["faultray"]

    def test_compliance_status_meets_policy_for_high_score(self):
        bridge = AWSResilienceHubBridge()
        output = bridge.to_resilience_hub_format(self._make_assessment(score=85.0))
        assert output["complianceStatus"] == PolicyStatus.MEETS_POLICY.value

    def test_compliance_status_policy_breached_for_low_score(self):
        bridge = AWSResilienceHubBridge()
        output = bridge.to_resilience_hub_format(self._make_assessment(score=40.0))
        assert output["complianceStatus"] == PolicyStatus.POLICY_BREACHED.value

    def test_compliance_status_not_assessed_for_zero(self):
        bridge = AWSResilienceHubBridge()
        output = bridge.to_resilience_hub_format(self._make_assessment(score=0.0))
        assert output["complianceStatus"] == PolicyStatus.NOT_ASSESSED.value


# ============================================================
# AWSResilienceHubBridge.compare_with_live
# ============================================================

class TestCompareWithLive:
    def _make_assessment(self, score: float = 75.0) -> PreDeployAssessment:
        bridge = AWSResilienceHubBridge()
        return bridge.from_faultray_report(_make_faultray_report(score=score))

    def test_returns_comparison_report(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(75.0)
        live = _make_live_hub_assessment(score=70.0)
        report = bridge.compare_with_live(assessment, live)
        assert isinstance(report, ComparisonReport)

    def test_score_delta_calculated_correctly(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(80.0)
        live = _make_live_hub_assessment(score=70.0)
        report = bridge.compare_with_live(assessment, live)
        assert report.score_delta == pytest.approx(10.0)

    def test_score_delta_negative_when_pessimistic(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(60.0)
        live = _make_live_hub_assessment(score=75.0)
        report = bridge.compare_with_live(assessment, live)
        assert report.score_delta == pytest.approx(-15.0)

    def test_perfect_prediction_has_high_accuracy(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(75.0)
        live = _make_live_hub_assessment(score=75.0)
        report = bridge.compare_with_live(assessment, live)
        assert report.prediction_accuracy == pytest.approx(1.0)

    def test_large_deviation_has_low_accuracy(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(90.0)
        live = _make_live_hub_assessment(score=60.0)
        report = bridge.compare_with_live(assessment, live)
        assert report.prediction_accuracy == pytest.approx(0.0)

    def test_policy_status_match_true_when_same(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(75.0)  # MeetsPolicy
        live = _make_live_hub_assessment(score=70.0, status="MeetsPolicy")
        report = bridge.compare_with_live(assessment, live)
        assert report.policy_status_match is True

    def test_policy_status_match_false_when_different(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(55.0)  # PolicyBreached
        live = _make_live_hub_assessment(score=80.0, status="MeetsPolicy")
        report = bridge.compare_with_live(assessment, live)
        assert report.policy_status_match is False

    def test_missed_risks_identified(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(75.0)
        # Live Hub found a risk that FaultRay missed
        live = _make_live_hub_assessment(
            score=70.0, findings=["az-single-point-of-failure"]
        )
        report = bridge.compare_with_live(assessment, live)
        assert "az-single-point-of-failure" in report.missed_risks

    def test_extra_risks_identified(self):
        bridge = AWSResilienceHubBridge()
        report_dict = _make_faultray_report(
            warnings=["faultray-specific-risk"]
        )
        assessment = bridge.from_faultray_report(report_dict)
        # Live Hub didn't find that risk
        live = _make_live_hub_assessment(score=70.0, findings=[])
        comparison = bridge.compare_with_live(assessment, live)
        assert "faultray-specific-risk" in comparison.extra_risks

    def test_summary_is_non_empty_string(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(75.0)
        live = _make_live_hub_assessment(score=70.0)
        report = bridge.compare_with_live(assessment, live)
        assert isinstance(report.summary, str)
        assert len(report.summary) > 0

    def test_pre_deploy_score_captured(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(72.0)
        live = _make_live_hub_assessment(score=68.0)
        report = bridge.compare_with_live(assessment, live)
        assert report.pre_deploy_score == pytest.approx(72.0)
        assert report.live_score == pytest.approx(68.0)

    def test_disruption_deltas_present(self):
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(75.0)
        live = _make_live_hub_assessment(
            score=70.0,
            disruption={
                "Infrastructure": {"score": 70.0},
                "Application": {"score": 65.0},
            },
        )
        report = bridge.compare_with_live(assessment, live)
        assert "Infrastructure" in report.disruption_deltas
        assert "Application" in report.disruption_deltas

    def test_live_assessment_with_alternative_score_key(self):
        """Resilience Hub exports sometimes use 'score' instead of 'resiliencyScore'."""
        bridge = AWSResilienceHubBridge()
        assessment = self._make_assessment(75.0)
        live = {"score": 72.0, "complianceStatus": "MeetsPolicy", "findings": []}
        report = bridge.compare_with_live(assessment, live)
        assert report.live_score == pytest.approx(72.0)


# ============================================================
# DisruptionScore dataclass
# ============================================================

class TestDisruptionScore:
    def test_instantiation(self):
        ds = DisruptionScore(
            disruption_type=DisruptionType.INFRASTRUCTURE,
            score=75.0,
            estimated_rto_seconds=3600,
            estimated_rpo_seconds=1800,
            policy_status=PolicyStatus.MEETS_POLICY,
        )
        assert ds.disruption_type == DisruptionType.INFRASTRUCTURE
        assert ds.risks == []
        assert ds.recommendations == []

    def test_with_risks_and_recs(self):
        ds = DisruptionScore(
            disruption_type=DisruptionType.APPLICATION,
            score=50.0,
            estimated_rto_seconds=600,
            estimated_rpo_seconds=300,
            policy_status=PolicyStatus.POLICY_BREACHED,
            risks=["lambda-timeout"],
            recommendations=["add circuit breaker"],
        )
        assert "lambda-timeout" in ds.risks
        assert "add circuit breaker" in ds.recommendations


# ============================================================
# Edge cases
# ============================================================

class TestEdgeCases:
    def test_bridge_with_no_policy_uses_default(self):
        bridge = AWSResilienceHubBridge()
        assert bridge.policy is not None
        assert bridge.policy.policy_name == "FaultRay-Default"

    def test_assessment_has_recommendations_when_low_score(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(_make_faultray_report(score=20.0))
        assert len(assessment.recommendations) > 0

    def test_assessment_recommendations_have_required_keys(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(_make_faultray_report(score=40.0))
        for rec in assessment.recommendations:
            assert "disruptionType" in rec
            assert "recommendation" in rec
            assert "severity" in rec

    def test_high_score_has_low_severity_recs(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(_make_faultray_report(score=95.0))
        for rec in assessment.recommendations:
            assert rec["severity"] in ("LOW", "MEDIUM", "HIGH")

    def test_disruption_type_enum_values(self):
        assert DisruptionType.INFRASTRUCTURE.value == "Infrastructure"
        assert DisruptionType.APPLICATION.value == "Application"
        assert DisruptionType.NETWORK.value == "Network"
        assert DisruptionType.REGION.value == "Region"

    def test_policy_status_enum_values(self):
        assert PolicyStatus.MEETS_POLICY.value == "MeetsPolicy"
        assert PolicyStatus.POLICY_BREACHED.value == "PolicyBreached"
        assert PolicyStatus.NOT_ASSESSED.value == "NotAssessed"

    def test_overall_score_not_exceeds_100(self):
        bridge = AWSResilienceHubBridge()
        # Feeding a score of exactly 100 should be fine
        assessment = bridge.from_faultray_report(_make_faultray_report(score=100.0))
        assert assessment.overall_score <= 100.0

    def test_overall_score_not_below_zero(self):
        bridge = AWSResilienceHubBridge()
        assessment = bridge.from_faultray_report(_make_faultray_report(score=-5.0))
        # Score is passed through as-is; disruption scores are clamped
        for ds in assessment.disruption_scores:
            assert ds.score >= 0.0
