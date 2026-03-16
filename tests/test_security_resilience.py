"""Tests for the Security Resilience Engine.

Covers SecurityProfile, ThreatAssessment, SecurityScorecard,
assess_threat, and generate_scorecard with 50+ test cases.
"""
from __future__ import annotations

import pytest

from faultray.simulator.security_resilience import (
    RiskLevel,
    SecurityControl,
    SecurityProfile,
    SecurityResilienceEngine,
    SecurityScorecard,
    ThreatAssessment,
    ThreatCategory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_CONTROLS = list(SecurityControl)


def _engine_with_profiles(**profiles: SecurityProfile) -> SecurityResilienceEngine:
    """Create an engine and register one or more component profiles."""
    engine = SecurityResilienceEngine()
    for comp_id, profile in profiles.items():
        engine.set_component_profile(comp_id, profile)
    return engine


def _fully_secured_profile(public_facing: bool = False) -> SecurityProfile:
    """Profile with every SecurityControl enabled."""
    return SecurityProfile(
        controls=list(SecurityControl),
        public_facing=public_facing,
        stores_pii=False,
        stores_financial=False,
        authentication_required=True,
        network_zone="restricted",
    )


def _empty_profile(
    public_facing: bool = True,
    stores_pii: bool = False,
    stores_financial: bool = False,
) -> SecurityProfile:
    """Profile with no controls at all."""
    return SecurityProfile(
        controls=[],
        public_facing=public_facing,
        stores_pii=stores_pii,
        stores_financial=stores_financial,
    )


# ===========================================================================
# SecurityProfile — defaults and custom values
# ===========================================================================


class TestSecurityProfileDefaults:
    """SecurityProfile defaults and custom values."""

    def test_default_controls_empty(self):
        p = SecurityProfile()
        assert p.controls == []

    def test_default_public_facing_false(self):
        p = SecurityProfile()
        assert p.public_facing is False

    def test_default_stores_pii_false(self):
        p = SecurityProfile()
        assert p.stores_pii is False

    def test_default_stores_financial_false(self):
        p = SecurityProfile()
        assert p.stores_financial is False

    def test_default_authentication_required_true(self):
        p = SecurityProfile()
        assert p.authentication_required is True

    def test_default_network_zone_private(self):
        p = SecurityProfile()
        assert p.network_zone == "private"

    def test_custom_controls(self):
        p = SecurityProfile(controls=[SecurityControl.WAF, SecurityControl.MFA])
        assert SecurityControl.WAF in p.controls
        assert SecurityControl.MFA in p.controls

    def test_custom_network_zone(self):
        p = SecurityProfile(network_zone="dmz")
        assert p.network_zone == "dmz"

    def test_custom_all_fields(self):
        p = SecurityProfile(
            controls=[SecurityControl.DLP],
            public_facing=True,
            stores_pii=True,
            stores_financial=True,
            authentication_required=False,
            network_zone="public",
        )
        assert p.public_facing is True
        assert p.stores_pii is True
        assert p.stores_financial is True
        assert p.authentication_required is False
        assert p.network_zone == "public"


# ===========================================================================
# ThreatAssessment — dataclass fields
# ===========================================================================


class TestThreatAssessmentDataclass:
    """ThreatAssessment dataclass field validation."""

    def test_create_assessment(self):
        a = ThreatAssessment(
            threat=ThreatCategory.DDOS,
            risk_level=RiskLevel.HIGH,
            likelihood_score=7.0,
            impact_score=5.0,
            overall_score=35.0,
        )
        assert a.threat == ThreatCategory.DDOS
        assert a.risk_level == RiskLevel.HIGH
        assert a.likelihood_score == 7.0
        assert a.impact_score == 5.0
        assert a.overall_score == 35.0

    def test_default_vulnerable_components_empty(self):
        a = ThreatAssessment(
            threat=ThreatCategory.DDOS,
            risk_level=RiskLevel.LOW,
            likelihood_score=1.0,
            impact_score=1.0,
            overall_score=1.0,
        )
        assert a.vulnerable_components == []

    def test_default_missing_controls_empty(self):
        a = ThreatAssessment(
            threat=ThreatCategory.DDOS,
            risk_level=RiskLevel.LOW,
            likelihood_score=1.0,
            impact_score=1.0,
            overall_score=1.0,
        )
        assert a.missing_controls == []

    def test_default_mitigations_empty(self):
        a = ThreatAssessment(
            threat=ThreatCategory.DDOS,
            risk_level=RiskLevel.LOW,
            likelihood_score=1.0,
            impact_score=1.0,
            overall_score=1.0,
        )
        assert a.mitigations == []


# ===========================================================================
# Enums
# ===========================================================================


class TestEnums:
    """Enum membership and value checks."""

    def test_threat_category_count(self):
        assert len(ThreatCategory) == 8

    def test_security_control_count(self):
        assert len(SecurityControl) == 12

    def test_risk_level_count(self):
        assert len(RiskLevel) == 5

    @pytest.mark.parametrize("member,value", [
        (ThreatCategory.DDOS, "ddos"),
        (ThreatCategory.DATA_BREACH, "data_breach"),
        (ThreatCategory.RANSOMWARE, "ransomware"),
        (ThreatCategory.INSIDER_THREAT, "insider_threat"),
        (ThreatCategory.SUPPLY_CHAIN, "supply_chain"),
        (ThreatCategory.API_ABUSE, "api_abuse"),
        (ThreatCategory.CREDENTIAL_STUFFING, "credential_stuffing"),
        (ThreatCategory.LATERAL_MOVEMENT, "lateral_movement"),
    ])
    def test_threat_category_values(self, member, value):
        assert member.value == value

    @pytest.mark.parametrize("member,value", [
        (RiskLevel.CRITICAL, "critical"),
        (RiskLevel.HIGH, "high"),
        (RiskLevel.MEDIUM, "medium"),
        (RiskLevel.LOW, "low"),
        (RiskLevel.MINIMAL, "minimal"),
    ])
    def test_risk_level_values(self, member, value):
        assert member.value == value


# ===========================================================================
# SecurityResilienceEngine — basic operations
# ===========================================================================


class TestEngineBasics:
    """Engine initialization and component management."""

    def test_init_empty_profiles(self):
        engine = SecurityResilienceEngine()
        assert engine.component_profiles == {}

    def test_set_component_profile(self):
        engine = SecurityResilienceEngine()
        p = SecurityProfile(controls=[SecurityControl.WAF])
        engine.set_component_profile("web", p)
        assert "web" in engine.component_profiles
        assert engine.component_profiles["web"] is p

    def test_overwrite_component_profile(self):
        engine = SecurityResilienceEngine()
        p1 = SecurityProfile(controls=[SecurityControl.WAF])
        p2 = SecurityProfile(controls=[SecurityControl.MFA])
        engine.set_component_profile("web", p1)
        engine.set_component_profile("web", p2)
        assert engine.component_profiles["web"] is p2

    def test_multiple_components(self):
        engine = SecurityResilienceEngine()
        engine.set_component_profile("a", SecurityProfile())
        engine.set_component_profile("b", SecurityProfile())
        engine.set_component_profile("c", SecurityProfile())
        assert len(engine.component_profiles) == 3

    def test_threat_controls_mapping_has_all_threats(self):
        engine = SecurityResilienceEngine()
        for threat in ThreatCategory:
            assert threat in engine.THREAT_CONTROLS


# ===========================================================================
# assess_threat — various scenarios
# ===========================================================================


class TestAssessThreatFullControls:
    """assess_threat with full controls should result in minimal risk."""

    @pytest.mark.parametrize("threat", list(ThreatCategory))
    def test_full_controls_minimal_or_low_risk(self, threat):
        engine = _engine_with_profiles(server=_fully_secured_profile())
        assessment = engine.assess_threat(threat)
        assert assessment.risk_level in (RiskLevel.MINIMAL, RiskLevel.LOW)
        assert assessment.likelihood_score == 0.0
        assert assessment.missing_controls == []

    @pytest.mark.parametrize("threat", list(ThreatCategory))
    def test_full_controls_no_mitigations(self, threat):
        engine = _engine_with_profiles(server=_fully_secured_profile())
        assessment = engine.assess_threat(threat)
        assert assessment.mitigations == []


class TestAssessThreatNoControls:
    """assess_threat with no controls should result in high/critical risk."""

    def test_no_controls_public_facing_high_likelihood(self):
        engine = _engine_with_profiles(web=_empty_profile(public_facing=True))
        assessment = engine.assess_threat(ThreatCategory.DDOS)
        assert assessment.likelihood_score == 10.0

    def test_no_controls_financial_data_high_impact(self):
        engine = _engine_with_profiles(
            db=_empty_profile(stores_financial=True),
        )
        assessment = engine.assess_threat(ThreatCategory.DATA_BREACH)
        assert assessment.impact_score == 9

    def test_no_controls_pii_data_moderate_impact(self):
        engine = _engine_with_profiles(
            db=_empty_profile(stores_pii=True),
        )
        assessment = engine.assess_threat(ThreatCategory.DATA_BREACH)
        assert assessment.impact_score == 7

    def test_no_controls_ddos_critical_risk(self):
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        assessment = engine.assess_threat(ThreatCategory.DDOS)
        assert assessment.risk_level == RiskLevel.CRITICAL

    def test_no_controls_lists_all_missing(self):
        engine = _engine_with_profiles(web=_empty_profile())
        assessment = engine.assess_threat(ThreatCategory.DDOS)
        expected = SecurityResilienceEngine.THREAT_CONTROLS[ThreatCategory.DDOS]
        assert set(assessment.missing_controls) == set(expected)

    def test_no_controls_has_mitigations(self):
        engine = _engine_with_profiles(web=_empty_profile())
        assessment = engine.assess_threat(ThreatCategory.DDOS)
        assert len(assessment.mitigations) > 0
        for m in assessment.mitigations:
            assert "Implement" in m
            assert "ddos" in m

    def test_no_controls_vulnerable_components_public(self):
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True),
            db=SecurityProfile(controls=[], public_facing=False, stores_pii=False),
        )
        assessment = engine.assess_threat(ThreatCategory.DDOS)
        assert "web" in assessment.vulnerable_components
        # db is private and has no PII, so not vulnerable in this context
        assert "db" not in assessment.vulnerable_components

    def test_no_controls_vulnerable_components_pii(self):
        engine = _engine_with_profiles(
            db=SecurityProfile(controls=[], public_facing=False, stores_pii=True),
        )
        assessment = engine.assess_threat(ThreatCategory.DATA_BREACH)
        assert "db" in assessment.vulnerable_components


class TestAssessThreatPartialControls:
    """assess_threat with some controls present."""

    def test_partial_controls_ddos_waf_only(self):
        profile = SecurityProfile(
            controls=[SecurityControl.WAF],
            public_facing=True,
        )
        engine = _engine_with_profiles(web=profile)
        assessment = engine.assess_threat(ThreatCategory.DDOS)
        # WAF covers 1 of 2 DDOS controls -> 50% coverage
        assert assessment.likelihood_score == 5.0
        assert SecurityControl.RATE_LIMITING in assessment.missing_controls
        assert SecurityControl.WAF not in assessment.missing_controls

    def test_partial_controls_ransomware_backup_only(self):
        profile = SecurityProfile(
            controls=[SecurityControl.BACKUP_ENCRYPTION],
            public_facing=True,
        )
        engine = _engine_with_profiles(server=profile)
        assessment = engine.assess_threat(ThreatCategory.RANSOMWARE)
        # 1 of 3 ransomware controls
        assert 6.0 <= assessment.likelihood_score <= 7.0

    def test_partial_controls_reduces_risk(self):
        engine_none = _engine_with_profiles(web=_empty_profile(public_facing=True))
        engine_partial = _engine_with_profiles(
            web=SecurityProfile(
                controls=[SecurityControl.WAF],
                public_facing=True,
            ),
        )
        a_none = engine_none.assess_threat(ThreatCategory.DDOS)
        a_partial = engine_partial.assess_threat(ThreatCategory.DDOS)
        assert a_partial.overall_score <= a_none.overall_score
        # Likelihood should be lower with partial controls
        assert a_partial.likelihood_score < a_none.likelihood_score


class TestAssessThreatPublicVsPrivate:
    """Public-facing vs private components affect impact scoring."""

    def test_public_facing_higher_impact(self):
        engine_pub = _engine_with_profiles(
            web=SecurityProfile(controls=[], public_facing=True),
        )
        engine_priv = _engine_with_profiles(
            web=SecurityProfile(controls=[], public_facing=False),
        )
        a_pub = engine_pub.assess_threat(ThreatCategory.DDOS)
        a_priv = engine_priv.assess_threat(ThreatCategory.DDOS)
        assert a_pub.impact_score > a_priv.impact_score

    def test_private_component_not_listed_vulnerable(self):
        engine = _engine_with_profiles(
            internal=SecurityProfile(
                controls=[],
                public_facing=False,
                stores_pii=False,
            ),
        )
        assessment = engine.assess_threat(ThreatCategory.API_ABUSE)
        assert "internal" not in assessment.vulnerable_components


class TestAssessThreatPiiVsFinancial:
    """PII vs financial data impact scoring."""

    def test_financial_higher_impact_than_pii(self):
        engine_fin = _engine_with_profiles(
            db=SecurityProfile(controls=[], stores_financial=True),
        )
        engine_pii = _engine_with_profiles(
            db=SecurityProfile(controls=[], stores_pii=True),
        )
        a_fin = engine_fin.assess_threat(ThreatCategory.DATA_BREACH)
        a_pii = engine_pii.assess_threat(ThreatCategory.DATA_BREACH)
        assert a_fin.impact_score > a_pii.impact_score

    def test_financial_impact_is_9(self):
        engine = _engine_with_profiles(
            db=SecurityProfile(controls=[], stores_financial=True),
        )
        a = engine.assess_threat(ThreatCategory.DATA_BREACH)
        assert a.impact_score == 9

    def test_pii_impact_is_7(self):
        engine = _engine_with_profiles(
            db=SecurityProfile(controls=[], stores_pii=True),
        )
        a = engine.assess_threat(ThreatCategory.DATA_BREACH)
        assert a.impact_score == 7


# ===========================================================================
# assess_threat — risk level thresholds
# ===========================================================================


class TestRiskLevelThresholds:
    """Verify risk level assignment based on overall_score."""

    def test_critical_at_70(self):
        # Force score >= 70: no controls + financial data
        engine = _engine_with_profiles(
            db=_empty_profile(stores_financial=True),
        )
        a = engine.assess_threat(ThreatCategory.DATA_BREACH)
        # 10 * 9 / 10 * 100 = 90
        assert a.overall_score >= 70
        assert a.risk_level == RiskLevel.CRITICAL

    def test_minimal_at_0(self):
        engine = _engine_with_profiles(server=_fully_secured_profile())
        a = engine.assess_threat(ThreatCategory.DDOS)
        assert a.overall_score == 0.0
        assert a.risk_level == RiskLevel.MINIMAL


# ===========================================================================
# generate_scorecard — empty components
# ===========================================================================


class TestScorecardEmpty:
    """Scorecard with no components registered."""

    def test_empty_engine_scorecard_generates(self):
        engine = SecurityResilienceEngine()
        sc = engine.generate_scorecard()
        assert isinstance(sc, SecurityScorecard)

    def test_empty_engine_has_8_assessments(self):
        engine = SecurityResilienceEngine()
        sc = engine.generate_scorecard()
        assert len(sc.threat_assessments) == 8

    def test_empty_engine_overall_score_is_number(self):
        engine = SecurityResilienceEngine()
        sc = engine.generate_scorecard()
        assert isinstance(sc.overall_score, (int, float))
        assert 0 <= sc.overall_score <= 100

    def test_empty_engine_grade_is_string(self):
        engine = SecurityResilienceEngine()
        sc = engine.generate_scorecard()
        assert isinstance(sc.grade, str)

    def test_empty_engine_no_strengths(self):
        engine = SecurityResilienceEngine()
        sc = engine.generate_scorecard()
        assert sc.strengths == []

    def test_empty_engine_all_controls_missing(self):
        engine = SecurityResilienceEngine()
        sc = engine.generate_scorecard()
        for ctrl_val, present in sc.control_coverage.items():
            assert present is False


# ===========================================================================
# generate_scorecard — fully secured infrastructure
# ===========================================================================


class TestScorecardFullySecured:
    """Scorecard for an infrastructure with all controls enabled."""

    def test_fully_secured_high_score(self):
        engine = _engine_with_profiles(
            web=_fully_secured_profile(public_facing=True),
            db=SecurityProfile(
                controls=list(SecurityControl),
                stores_pii=True,
                stores_financial=True,
            ),
        )
        sc = engine.generate_scorecard()
        assert sc.overall_score >= 90

    def test_fully_secured_grade_a_or_better(self):
        engine = _engine_with_profiles(
            web=_fully_secured_profile(public_facing=True),
            db=SecurityProfile(
                controls=list(SecurityControl),
                stores_pii=True,
                stores_financial=True,
            ),
        )
        sc = engine.generate_scorecard()
        assert sc.grade in ("A+", "A", "A-")

    def test_fully_secured_all_controls_covered(self):
        engine = _engine_with_profiles(server=_fully_secured_profile())
        sc = engine.generate_scorecard()
        for ctrl_val, present in sc.control_coverage.items():
            assert present is True

    def test_fully_secured_no_weaknesses_in_top5(self):
        engine = _engine_with_profiles(server=_fully_secured_profile())
        sc = engine.generate_scorecard()
        # All controls present, so weaknesses list should be empty
        assert sc.weaknesses == []

    def test_fully_secured_strengths_populated(self):
        engine = _engine_with_profiles(server=_fully_secured_profile())
        sc = engine.generate_scorecard()
        assert len(sc.strengths) > 0


# ===========================================================================
# generate_scorecard — completely unsecured
# ===========================================================================


class TestScorecardUnsecured:
    """Scorecard for completely unsecured infrastructure."""

    def test_unsecured_low_score(self):
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        sc = engine.generate_scorecard()
        assert sc.overall_score < 30

    def test_unsecured_grade_f_or_d(self):
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        sc = engine.generate_scorecard()
        assert sc.grade in ("F", "D")

    def test_unsecured_has_recommendations(self):
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        sc = engine.generate_scorecard()
        assert len(sc.recommendations) > 0

    def test_unsecured_no_controls_covered(self):
        engine = _engine_with_profiles(
            web=_empty_profile(),
        )
        sc = engine.generate_scorecard()
        for ctrl_val, present in sc.control_coverage.items():
            assert present is False

    def test_unsecured_weaknesses_populated(self):
        engine = _engine_with_profiles(web=_empty_profile())
        sc = engine.generate_scorecard()
        assert len(sc.weaknesses) > 0


# ===========================================================================
# generate_scorecard — grade assignment
# ===========================================================================


class TestGradeAssignment:
    """Grade boundaries in generate_scorecard."""

    def _scorecard_with_score(self, target_score: float) -> SecurityScorecard:
        """Construct a scorecard via engine to hit approximately the target score.

        We can't directly set the score, but we can use fully-secured (high) vs
        unsecured (low) and verify the grade mapping logic by inspecting the
        grading code path.
        """
        # Instead, directly test the grading logic by creating a small engine
        # that is rigged so that the average threat score approximates (100 - target_score).
        # Since we can't trivially control the exact score, we just verify the engine
        # returns valid grades and boundaries work for known configurations.
        pass

    def test_fully_secured_gets_a_plus(self):
        engine = _engine_with_profiles(
            server=_fully_secured_profile(),
        )
        sc = engine.generate_scorecard()
        # Fully secured private server -> score 100 (all threats minimal)
        assert sc.grade == "A+"

    def test_grade_is_valid_string(self):
        engine = _engine_with_profiles(web=_empty_profile())
        sc = engine.generate_scorecard()
        valid_grades = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "D", "F"}
        assert sc.grade in valid_grades

    def test_unsecured_financial_gets_f(self):
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        sc = engine.generate_scorecard()
        assert sc.grade == "F"


# ===========================================================================
# generate_scorecard — control coverage map
# ===========================================================================


class TestControlCoverage:
    """Control coverage map in scorecard."""

    def test_coverage_has_all_controls(self):
        engine = _engine_with_profiles(web=_empty_profile())
        sc = engine.generate_scorecard()
        assert len(sc.control_coverage) == len(SecurityControl)

    def test_coverage_partial(self):
        profile = SecurityProfile(
            controls=[SecurityControl.WAF, SecurityControl.MFA],
            public_facing=True,
        )
        engine = _engine_with_profiles(web=profile)
        sc = engine.generate_scorecard()
        assert sc.control_coverage["waf"] is True
        assert sc.control_coverage["mfa"] is True
        assert sc.control_coverage["dlp"] is False

    def test_coverage_across_multiple_components(self):
        p1 = SecurityProfile(controls=[SecurityControl.WAF])
        p2 = SecurityProfile(controls=[SecurityControl.MFA])
        engine = _engine_with_profiles(web=p1, auth=p2)
        sc = engine.generate_scorecard()
        assert sc.control_coverage["waf"] is True
        assert sc.control_coverage["mfa"] is True


# ===========================================================================
# generate_scorecard — strengths and weaknesses
# ===========================================================================


class TestStrengthsAndWeaknesses:
    """Strengths and weaknesses population."""

    def test_strengths_are_present_controls(self):
        profile = SecurityProfile(controls=[SecurityControl.WAF, SecurityControl.DLP])
        engine = _engine_with_profiles(web=profile)
        sc = engine.generate_scorecard()
        assert "waf" in sc.strengths
        assert "dlp" in sc.strengths

    def test_weaknesses_are_missing_controls(self):
        profile = SecurityProfile(controls=[SecurityControl.WAF])
        engine = _engine_with_profiles(web=profile)
        sc = engine.generate_scorecard()
        # All controls except WAF should appear as weaknesses (capped at 5)
        for w in sc.weaknesses:
            assert w != "waf"
        assert len(sc.weaknesses) <= 5

    def test_strengths_capped_at_5(self):
        engine = _engine_with_profiles(server=_fully_secured_profile())
        sc = engine.generate_scorecard()
        assert len(sc.strengths) <= 5

    def test_weaknesses_capped_at_5(self):
        engine = _engine_with_profiles(web=_empty_profile())
        sc = engine.generate_scorecard()
        assert len(sc.weaknesses) <= 5


# ===========================================================================
# generate_scorecard — recommendations
# ===========================================================================


class TestRecommendations:
    """Recommendations generation from top threat assessments."""

    def test_unsecured_has_at_least_one_recommendation(self):
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        sc = engine.generate_scorecard()
        assert len(sc.recommendations) >= 1

    def test_recommendations_capped_at_5(self):
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        sc = engine.generate_scorecard()
        assert len(sc.recommendations) <= 5

    def test_recommendations_contain_implement_keyword(self):
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        sc = engine.generate_scorecard()
        for rec in sc.recommendations:
            assert "Implement" in rec

    def test_fully_secured_no_recommendations(self):
        engine = _engine_with_profiles(server=_fully_secured_profile())
        sc = engine.generate_scorecard()
        assert sc.recommendations == []


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_assess_all_threats_sequentially(self):
        engine = _engine_with_profiles(web=_empty_profile())
        for threat in ThreatCategory:
            a = engine.assess_threat(threat)
            assert a.threat == threat
            assert 0 <= a.overall_score <= 100

    def test_single_component_no_data(self):
        """A private component with no PII/financial and no controls."""
        profile = SecurityProfile(
            controls=[],
            public_facing=False,
            stores_pii=False,
            stores_financial=False,
        )
        engine = _engine_with_profiles(internal=profile)
        a = engine.assess_threat(ThreatCategory.DDOS)
        # Impact = 3 (private, no data), likelihood = 10 (no controls)
        assert a.impact_score == 3
        assert a.likelihood_score == 10.0
        # (10 * 3) / 10 * 100 = 300, capped at 100
        assert a.overall_score == 100
        assert a.risk_level == RiskLevel.CRITICAL

    def test_many_components_mixed_profiles(self):
        engine = SecurityResilienceEngine()
        engine.set_component_profile("web", SecurityProfile(
            controls=[SecurityControl.WAF, SecurityControl.RATE_LIMITING],
            public_facing=True,
        ))
        engine.set_component_profile("api", SecurityProfile(
            controls=[SecurityControl.RATE_LIMITING, SecurityControl.AUDIT_LOGGING],
        ))
        engine.set_component_profile("db", SecurityProfile(
            controls=[SecurityControl.ENCRYPTION_AT_REST, SecurityControl.BACKUP_ENCRYPTION],
            stores_financial=True,
        ))
        engine.set_component_profile("cache", SecurityProfile(
            controls=[SecurityControl.NETWORK_SEGMENTATION],
        ))
        sc = engine.generate_scorecard()
        assert 0 <= sc.overall_score <= 100
        assert len(sc.threat_assessments) == 8

    def test_overall_score_capped_at_100(self):
        """Even with extreme settings, overall_score should not exceed 100."""
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        for threat in ThreatCategory:
            a = engine.assess_threat(threat)
            assert a.overall_score <= 100

    def test_overall_score_minimum_0(self):
        """Security score should not go below 0."""
        engine = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        sc = engine.generate_scorecard()
        assert sc.overall_score >= 0

    def test_financial_overrides_pii_in_impact(self):
        """When both financial and PII are set, financial impact (9) should dominate."""
        engine = _engine_with_profiles(
            db=SecurityProfile(
                controls=[],
                stores_pii=True,
                stores_financial=True,
            ),
        )
        a = engine.assess_threat(ThreatCategory.DATA_BREACH)
        assert a.impact_score == 9

    def test_empty_engine_assess_threat_uses_default_impact(self):
        """With no components, impact defaults to 5."""
        engine = SecurityResilienceEngine()
        a = engine.assess_threat(ThreatCategory.DDOS)
        assert a.impact_score == 5

    def test_empty_engine_no_vulnerable_components(self):
        engine = SecurityResilienceEngine()
        a = engine.assess_threat(ThreatCategory.DDOS)
        assert a.vulnerable_components == []

    def test_scorecard_threat_assessments_match_all_categories(self):
        engine = _engine_with_profiles(web=_empty_profile())
        sc = engine.generate_scorecard()
        threats_in_scorecard = {a.threat for a in sc.threat_assessments}
        assert threats_in_scorecard == set(ThreatCategory)

    def test_assess_threat_mitigation_text_format(self):
        engine = _engine_with_profiles(web=_empty_profile())
        a = engine.assess_threat(ThreatCategory.CREDENTIAL_STUFFING)
        for m in a.mitigations:
            # Format: "Implement X to mitigate Y risk"
            assert "to mitigate" in m
            assert "credential_stuffing" in m

    def test_scorecard_score_inversely_related_to_risk(self):
        """Higher security score means lower average threat risk."""
        engine_good = _engine_with_profiles(server=_fully_secured_profile())
        engine_bad = _engine_with_profiles(
            web=_empty_profile(public_facing=True, stores_financial=True),
        )
        sc_good = engine_good.generate_scorecard()
        sc_bad = engine_bad.generate_scorecard()
        assert sc_good.overall_score > sc_bad.overall_score

    def test_adding_controls_improves_score(self):
        """Adding more controls should improve the scorecard score."""
        engine_none = _engine_with_profiles(web=_empty_profile())
        engine_some = _engine_with_profiles(
            web=SecurityProfile(
                controls=[SecurityControl.WAF, SecurityControl.MFA, SecurityControl.DLP],
                public_facing=True,
            ),
        )
        sc_none = engine_none.generate_scorecard()
        sc_some = engine_some.generate_scorecard()
        assert sc_some.overall_score >= sc_none.overall_score
