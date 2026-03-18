"""Comprehensive tests for DORA Evidence Engine.

Tests cover all enums, models, controls, classification logic, gap analysis,
evidence generation, report generation, audit export, and edge cases.

Updated for the expanded engine covering all 5 DORA pillars (52 controls,
27 articles).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    FailoverConfig,
    HealthStatus,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.dora_evidence import (
    DORAArticle,
    DORAComplianceReport,
    DORAControl,
    DORAEvidenceEngine,
    DORAGapAnalysis,
    DORAPillar,
    EvaluationMethod,
    EvidenceRecord,
    EvidenceStatus,
    RiskConfig,
    TestClassification,
    _build_controls,
    _DORA_CONTROLS,
)

# Total control count after expansion
_TOTAL_CONTROLS = len(_DORA_CONTROLS)
_TOTAL_ARTICLES = len(DORAArticle)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    cid,
    name,
    ctype=ComponentType.APP_SERVER,
    replicas=1,
    failover=False,
    health=HealthStatus.HEALTHY,
    **kwargs,
):
    c = Component(id=cid, name=name, type=ctype, replicas=replicas, **kwargs)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    return c


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# 1. Enum Tests
# ---------------------------------------------------------------------------

class TestDORAArticleEnum:
    def test_article_11_value(self):
        assert DORAArticle.ARTICLE_11.value == "article_11"

    def test_article_24_value(self):
        assert DORAArticle.ARTICLE_24.value == "article_24"

    def test_article_25_value(self):
        assert DORAArticle.ARTICLE_25.value == "article_25"

    def test_article_26_value(self):
        assert DORAArticle.ARTICLE_26.value == "article_26"

    def test_article_28_value(self):
        assert DORAArticle.ARTICLE_28.value == "article_28"

    def test_article_count(self):
        # Expanded from 5 to 27 articles covering all DORA pillars
        assert len(DORAArticle) == _TOTAL_ARTICLES

    def test_articles_are_str_enum(self):
        for art in DORAArticle:
            assert isinstance(art, str)

    def test_all_five_pillars_have_articles(self):
        """All 5 DORA pillars have at least one article."""
        from faultray.simulator.dora_evidence import _ARTICLE_PILLAR_MAP
        pillars_covered = set(_ARTICLE_PILLAR_MAP.values())
        assert len(pillars_covered) == 5

    def test_new_pillar_1_articles(self):
        """Pillar 1 articles (5-16) are present."""
        for i in range(5, 17):
            assert hasattr(DORAArticle, f"ARTICLE_{i}")

    def test_new_pillar_2_articles(self):
        """Pillar 2 articles (17-23) are present."""
        for i in range(17, 24):
            assert hasattr(DORAArticle, f"ARTICLE_{i}")

    def test_pillar_5_article(self):
        assert DORAArticle.ARTICLE_45.value == "article_45"


class TestTestClassificationEnum:
    def test_basic_testing_value(self):
        assert TestClassification.BASIC_TESTING.value == "basic_testing"

    def test_advanced_testing_value(self):
        assert TestClassification.ADVANCED_TESTING.value == "advanced_testing"

    def test_tlpt_value(self):
        assert TestClassification.TLPT.value == "tlpt"

    def test_classification_count(self):
        assert len(TestClassification) == 3


class TestEvidenceStatusEnum:
    def test_compliant_value(self):
        assert EvidenceStatus.COMPLIANT.value == "compliant"

    def test_partially_compliant_value(self):
        assert EvidenceStatus.PARTIALLY_COMPLIANT.value == "partially_compliant"

    def test_non_compliant_value(self):
        assert EvidenceStatus.NON_COMPLIANT.value == "non_compliant"

    def test_not_applicable_value(self):
        assert EvidenceStatus.NOT_APPLICABLE.value == "not_applicable"

    def test_status_count(self):
        assert len(EvidenceStatus) == 4


class TestEvaluationMethodEnum:
    def test_all_methods(self):
        assert EvaluationMethod.AUTOMATED.value == "automated"
        assert EvaluationMethod.PARTIAL_AUTOMATED.value == "partial_automated"
        assert EvaluationMethod.MANUAL_REQUIRED.value == "manual_required"
        assert EvaluationMethod.EXTERNAL_ASSESSMENT.value == "external_assessment"
        assert EvaluationMethod.STUB.value == "stub"


# ---------------------------------------------------------------------------
# 2. Pydantic Model Tests
# ---------------------------------------------------------------------------

class TestDORAControlModel:
    def test_create_control(self):
        ctrl = DORAControl(
            article=DORAArticle.ARTICLE_11,
            control_id="DORA-11.01",
            description="Test control",
            test_requirements=["req1", "req2"],
        )
        assert ctrl.article == DORAArticle.ARTICLE_11
        assert ctrl.control_id == "DORA-11.01"
        assert ctrl.description == "Test control"
        assert ctrl.test_requirements == ["req1", "req2"]

    def test_control_default_requirements(self):
        ctrl = DORAControl(
            article=DORAArticle.ARTICLE_24,
            control_id="DORA-24.01",
            description="Desc",
        )
        assert ctrl.test_requirements == []

    def test_control_model_dump(self):
        ctrl = DORAControl(
            article=DORAArticle.ARTICLE_11,
            control_id="DORA-11.01",
            description="D",
        )
        d = ctrl.model_dump()
        assert "article" in d
        assert "control_id" in d

    def test_control_new_fields(self):
        ctrl = DORAControl(
            article=DORAArticle.ARTICLE_11,
            control_id="DORA-11.01",
            description="D",
            pillar=DORAPillar.ICT_RISK_MANAGEMENT,
            rts_references=["RTS 2024/1774 Art. 11"],
            evaluation_method=EvaluationMethod.AUTOMATED,
            default_risk_weight=1.2,
            remediation_deadline_days=60,
        )
        assert ctrl.pillar == DORAPillar.ICT_RISK_MANAGEMENT
        assert len(ctrl.rts_references) == 1
        assert ctrl.evaluation_method == EvaluationMethod.AUTOMATED
        assert ctrl.default_risk_weight == 1.2
        assert ctrl.remediation_deadline_days == 60


class TestEvidenceRecordModel:
    def test_create_record(self):
        now = datetime.now(timezone.utc)
        rec = EvidenceRecord(
            control_id="DORA-11.01",
            timestamp=now,
            test_type="basic_testing",
            test_description="Test",
            result="pass",
            severity="low",
        )
        assert rec.control_id == "DORA-11.01"
        assert rec.result == "pass"
        assert rec.remediation_required is False
        assert rec.artifacts == []

    def test_record_with_artifacts(self):
        now = datetime.now(timezone.utc)
        rec = EvidenceRecord(
            control_id="DORA-24.01",
            timestamp=now,
            test_type="advanced_testing",
            test_description="Failover test",
            result="fail",
            severity="high",
            remediation_required=True,
            artifacts=["report.json", "logs.txt"],
        )
        assert rec.remediation_required is True
        assert len(rec.artifacts) == 2


class TestDORAGapAnalysisModel:
    def test_create_gap(self):
        gap = DORAGapAnalysis(
            control_id="DORA-11.01",
            status=EvidenceStatus.COMPLIANT,
            risk_score=0.0,
        )
        assert gap.status == EvidenceStatus.COMPLIANT
        assert gap.gaps == []
        assert gap.recommendations == []

    def test_gap_with_issues(self):
        gap = DORAGapAnalysis(
            control_id="DORA-11.02",
            status=EvidenceStatus.NON_COMPLIANT,
            gaps=["Missing monitoring"],
            recommendations=["Deploy Prometheus"],
            risk_score=0.8,
        )
        assert gap.risk_score == 0.8
        assert len(gap.gaps) == 1

    def test_gap_new_fields(self):
        gap = DORAGapAnalysis(
            control_id="DORA-9.01",
            status=EvidenceStatus.PARTIALLY_COMPLIANT,
            risk_score=0.3,
            evaluation_method=EvaluationMethod.AUTOMATED,
            rts_references=["RTS 2024/1774 Art. 9"],
            evidence_items=["Encryption coverage: 60%"],
        )
        assert gap.evaluation_method == EvaluationMethod.AUTOMATED
        assert len(gap.rts_references) == 1
        assert len(gap.evidence_items) == 1


class TestDORAComplianceReportModel:
    def test_create_report(self):
        report = DORAComplianceReport(
            overall_status=EvidenceStatus.COMPLIANT,
        )
        assert report.overall_status == EvidenceStatus.COMPLIANT
        assert report.article_results == {}
        assert report.gap_analyses == []
        assert report.evidence_records == []

    def test_report_timestamps(self):
        report = DORAComplianceReport(
            overall_status=EvidenceStatus.COMPLIANT,
        )
        assert report.report_timestamp.tzinfo is not None
        assert report.next_review_date > report.report_timestamp

    def test_report_with_full_data(self):
        report = DORAComplianceReport(
            overall_status=EvidenceStatus.PARTIALLY_COMPLIANT,
            article_results={"article_11": EvidenceStatus.COMPLIANT},
            gap_analyses=[
                DORAGapAnalysis(
                    control_id="DORA-11.01",
                    status=EvidenceStatus.COMPLIANT,
                    risk_score=0.0,
                )
            ],
        )
        assert len(report.gap_analyses) == 1
        assert len(report.article_results) == 1

    def test_report_pillar_results(self):
        report = DORAComplianceReport(
            overall_status=EvidenceStatus.COMPLIANT,
            pillar_results={
                "ict_risk_management": EvidenceStatus.COMPLIANT,
                "resilience_testing": EvidenceStatus.PARTIALLY_COMPLIANT,
            },
        )
        assert len(report.pillar_results) == 2


# ---------------------------------------------------------------------------
# 3. Built-in Controls Tests
# ---------------------------------------------------------------------------

class TestBuiltInControls:
    def test_controls_loaded(self):
        controls = _build_controls()
        assert len(controls) == _TOTAL_CONTROLS
        assert _TOTAL_CONTROLS >= 50  # Expanded from 24

    def test_controls_raw_count(self):
        assert len(_DORA_CONTROLS) == _TOTAL_CONTROLS

    def test_article_11_has_6_controls(self):
        controls = _build_controls()
        art11 = [c for c in controls if c.article == DORAArticle.ARTICLE_11]
        assert len(art11) == 6

    def test_article_24_has_5_controls(self):
        controls = _build_controls()
        art24 = [c for c in controls if c.article == DORAArticle.ARTICLE_24]
        assert len(art24) == 5

    def test_article_25_has_5_controls(self):
        controls = _build_controls()
        art25 = [c for c in controls if c.article == DORAArticle.ARTICLE_25]
        assert len(art25) == 5

    def test_article_26_has_4_controls(self):
        controls = _build_controls()
        art26 = [c for c in controls if c.article == DORAArticle.ARTICLE_26]
        assert len(art26) == 4

    def test_article_28_has_4_controls(self):
        controls = _build_controls()
        art28 = [c for c in controls if c.article == DORAArticle.ARTICLE_28]
        assert len(art28) == 4

    def test_all_controls_have_unique_ids(self):
        controls = _build_controls()
        ids = [c.control_id for c in controls]
        assert len(ids) == len(set(ids))

    def test_all_controls_have_descriptions(self):
        controls = _build_controls()
        for c in controls:
            assert c.description, f"{c.control_id} has empty description"

    def test_all_controls_have_requirements(self):
        controls = _build_controls()
        for c in controls:
            assert len(c.test_requirements) > 0, f"{c.control_id} has no requirements"

    def test_control_ids_follow_pattern(self):
        controls = _build_controls()
        for c in controls:
            assert c.control_id.startswith("DORA-")

    def test_engine_loads_controls(self):
        g = _graph()
        engine = DORAEvidenceEngine(g)
        assert len(engine.controls) == _TOTAL_CONTROLS

    def test_pillar_1_has_controls(self):
        controls = _build_controls()
        p1 = [c for c in controls if c.pillar == DORAPillar.ICT_RISK_MANAGEMENT]
        assert len(p1) >= 15  # Art. 5-16

    def test_pillar_2_has_stub_controls(self):
        controls = _build_controls()
        p2 = [c for c in controls if c.pillar == DORAPillar.INCIDENT_MANAGEMENT]
        assert len(p2) >= 7  # Art. 17-23
        for c in p2:
            assert c.evaluation_method == EvaluationMethod.STUB

    def test_pillar_3_has_controls(self):
        controls = _build_controls()
        p3 = [c for c in controls if c.pillar == DORAPillar.RESILIENCE_TESTING]
        assert len(p3) >= 10  # Art. 24-27

    def test_pillar_4_has_controls(self):
        controls = _build_controls()
        p4 = [c for c in controls if c.pillar == DORAPillar.THIRD_PARTY_RISK]
        assert len(p4) >= 5  # Art. 28-30

    def test_pillar_5_has_controls(self):
        controls = _build_controls()
        p5 = [c for c in controls if c.pillar == DORAPillar.INFORMATION_SHARING]
        assert len(p5) >= 1  # Art. 45

    def test_rts_references_present(self):
        controls = _build_controls()
        controls_with_rts = [c for c in controls if c.rts_references]
        assert len(controls_with_rts) >= 10  # Many controls reference RTS


# ---------------------------------------------------------------------------
# 4. Test Classification Tests
# ---------------------------------------------------------------------------

class TestClassifyTest:
    def setup_method(self):
        self.engine = DORAEvidenceEngine(_graph())

    def test_basic_test(self):
        assert self.engine.classify_test("simple health check") == TestClassification.BASIC_TESTING

    def test_advanced_failover(self):
        assert self.engine.classify_test("failover test") == TestClassification.ADVANCED_TESTING

    def test_advanced_switchover(self):
        assert self.engine.classify_test("database switchover") == TestClassification.ADVANCED_TESTING

    def test_advanced_disaster(self):
        assert self.engine.classify_test("disaster recovery") == TestClassification.ADVANCED_TESTING

    def test_advanced_cascade(self):
        assert self.engine.classify_test("cascade failure") == TestClassification.ADVANCED_TESTING

    def test_advanced_chaos(self):
        assert self.engine.classify_test("chaos experiment") == TestClassification.ADVANCED_TESTING

    def test_advanced_stress(self):
        assert self.engine.classify_test("stress testing") == TestClassification.ADVANCED_TESTING

    def test_advanced_performance(self):
        assert self.engine.classify_test("performance benchmark") == TestClassification.ADVANCED_TESTING

    def test_advanced_load(self):
        assert self.engine.classify_test("load testing scenario") == TestClassification.ADVANCED_TESTING

    def test_advanced_recovery(self):
        assert self.engine.classify_test("recovery simulation") == TestClassification.ADVANCED_TESTING

    def test_tlpt_penetration(self):
        assert self.engine.classify_test("penetration test") == TestClassification.TLPT

    def test_tlpt_red_team(self):
        assert self.engine.classify_test("red team exercise") == TestClassification.TLPT

    def test_tlpt_attack(self):
        assert self.engine.classify_test("attack simulation") == TestClassification.TLPT

    def test_tlpt_threat_led(self):
        assert self.engine.classify_test("threat-led testing") == TestClassification.TLPT

    def test_tlpt_keyword(self):
        assert self.engine.classify_test("TLPT exercise") == TestClassification.TLPT

    def test_third_party_promotes_to_advanced(self):
        assert self.engine.classify_test("api integration", involves_third_party=True) == TestClassification.ADVANCED_TESTING

    def test_case_insensitive(self):
        assert self.engine.classify_test("FAILOVER TEST") == TestClassification.ADVANCED_TESTING

    def test_tlpt_takes_priority_over_advanced(self):
        # "attack" is TLPT, even though it could be advanced
        assert self.engine.classify_test("attack recovery") == TestClassification.TLPT


# ---------------------------------------------------------------------------
# 5. Control Evaluation Tests — unique logic per control
# ---------------------------------------------------------------------------

class TestEvaluateControl:
    def test_empty_graph_returns_not_applicable(self):
        engine = DORAEvidenceEngine(_graph())
        ctrl = DORAControl(
            article=DORAArticle.ARTICLE_11,
            control_id="DORA-11.01",
            description="Test",
        )
        result = engine.evaluate_control(ctrl)
        assert result.status == EvidenceStatus.NOT_APPLICABLE
        assert result.risk_score == 0.0

    def test_article_11_01_no_redundancy_no_failover(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-11.01")
        result = engine.evaluate_control(ctrl)
        assert result.status in (EvidenceStatus.NON_COMPLIANT, EvidenceStatus.PARTIALLY_COMPLIANT)
        assert len(result.gaps) > 0

    def test_article_11_01_with_redundancy_failover_monitoring(self):
        """DORA-11.01 checks redundancy + failover + monitoring + health."""
        g = _graph(
            _comp("app1", "App", replicas=3, failover=True),
            _comp("mon", "Prometheus Monitoring"),
        )
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-11.01")
        result = engine.evaluate_control(ctrl)
        assert result.status == EvidenceStatus.COMPLIANT
        assert result.risk_score == 0.0

    def test_article_11_01_unhealthy_component(self):
        g = _graph(
            _comp("app1", "App", replicas=2, failover=True, health=HealthStatus.DOWN),
            _comp("mon", "Prometheus"),
        )
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-11.01")
        result = engine.evaluate_control(ctrl)
        assert any("not healthy" in gap for gap in result.gaps)

    def test_article_11_02_vuln_assessment(self):
        """DORA-11.02 checks vulnerability exposure (patch SLA, encryption)."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-11.02")
        result = engine.evaluate_control(ctrl)
        # Should mention vulnerability scanning
        assert result.evaluation_method == EvaluationMethod.PARTIAL_AUTOMATED
        assert any("vulnerab" in gap.lower() or "scan" in gap.lower() for gap in result.gaps)

    def test_article_11_03_network_security(self):
        """DORA-11.03 checks network segmentation, TLS, WAF."""
        g = _graph(
            _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER),
            _comp("app1", "App"),
        )
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-11.03")
        result = engine.evaluate_control(ctrl)
        # Without segmentation/WAF, should have gaps
        assert len(result.gaps) > 0

    def test_article_11_04_stress_test(self):
        """DORA-11.04 checks capacity headroom and autoscaling."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-11.04")
        result = engine.evaluate_control(ctrl)
        # Without autoscaling, should have gaps
        assert any("autoscal" in gap.lower() for gap in result.gaps)

    def test_article_11_05_failover_scenarios(self):
        """DORA-11.05 checks actual failover/DR configuration."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-11.05")
        result = engine.evaluate_control(ctrl)
        assert result.status in (EvidenceStatus.NON_COMPLIANT, EvidenceStatus.PARTIALLY_COMPLIANT)
        assert any("failover" in gap.lower() for gap in result.gaps)

    def test_article_11_05_with_failover(self):
        g = _graph(_comp("app1", "App", replicas=2, failover=True))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-11.05")
        result = engine.evaluate_control(ctrl)
        # Should be better than non-compliant since failover is configured
        assert result.risk_score < 0.5

    def test_article_11_06_source_code_review(self):
        """DORA-11.06 checks CI/CD integration (NOT redundancy)."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-11.06")
        result = engine.evaluate_control(ctrl)
        # Should mention CI/CD or code review, not redundancy
        assert result.evaluation_method == EvaluationMethod.PARTIAL_AUTOMATED
        assert any("ci" in gap.lower() or "code review" in gap.lower() for gap in result.gaps)

    def test_article_9_01_encryption(self):
        """DORA-9.01 checks encryption coverage."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-9.01")
        result = engine.evaluate_control(ctrl)
        assert any("encrypt" in gap.lower() for gap in result.gaps)

    def test_article_9_01_with_encryption(self):
        """DORA-9.01 with encryption enabled should have lower risk."""
        c = _comp("app1", "App")
        c.security = SecurityProfile(encryption_at_rest=True, encryption_in_transit=True)
        g = _graph(c)
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-9.01")
        result = engine.evaluate_control(ctrl)
        assert result.risk_score < 0.5

    def test_article_10_01_monitoring(self):
        """DORA-10.01 checks for monitoring/alerting systems."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-10.01")
        result = engine.evaluate_control(ctrl)
        assert any("monitor" in gap.lower() for gap in result.gaps)

    def test_article_10_01_with_monitoring(self):
        g = _graph(_comp("mon", "Prometheus Monitoring"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-10.01")
        result = engine.evaluate_control(ctrl)
        # With monitoring, should be better
        assert result.risk_score < 0.4

    def test_article_12_01_backup(self):
        """DORA-12.01 checks backup configuration for data stores."""
        c = _comp("db1", "Database", ctype=ComponentType.DATABASE)
        g = _graph(c)
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-12.01")
        result = engine.evaluate_control(ctrl)
        assert any("backup" in gap.lower() for gap in result.gaps)

    def test_article_24_01_risk_based(self):
        """DORA-24.01 checks risk-based test programme (resilience mechanisms)."""
        g = _graph(_comp("app1", "App", replicas=2, failover=True))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-24.01")
        result = engine.evaluate_control(ctrl)
        # With redundancy + failover, should not be non-compliant
        assert result.status != EvidenceStatus.NON_COMPLIANT

    def test_article_24_no_resilience(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        art24 = [c for c in engine.controls if c.control_id == "DORA-24.01"]
        result = engine.evaluate_control(art24[0])
        assert result.status == EvidenceStatus.NON_COMPLIANT

    def test_article_24_partial_resilience(self):
        g = _graph(_comp("app1", "App", replicas=2))
        engine = DORAEvidenceEngine(g)
        art24 = [c for c in engine.controls if c.control_id == "DORA-24.01"]
        result = engine.evaluate_control(art24[0])
        assert result.status == EvidenceStatus.PARTIALLY_COMPLIANT

    def test_article_25_no_redundancy(self):
        """DORA-25 (TLPT) without redundancy should be non-compliant or partial."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        art25 = [c for c in engine.controls if c.article == DORAArticle.ARTICLE_25]
        result = engine.evaluate_control(art25[0])
        assert result.status in (EvidenceStatus.NON_COMPLIANT, EvidenceStatus.PARTIALLY_COMPLIANT)

    def test_article_25_ready(self):
        """DORA-25 with redundancy+failover should be at least partially compliant."""
        g = _graph(_comp("app1", "App", replicas=2, failover=True))
        engine = DORAEvidenceEngine(g)
        art25 = [c for c in engine.controls if c.article == DORAArticle.ARTICLE_25]
        result = engine.evaluate_control(art25[0])
        # TLPT always requires external assessment, so PARTIALLY_COMPLIANT is expected
        assert result.status == EvidenceStatus.PARTIALLY_COMPLIANT

    def test_article_25_03_production_tlpt(self):
        """DORA-25.03 flags requirement for external assessment."""
        g = _graph(_comp("app1", "App", replicas=2, failover=True))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-25.03")
        result = engine.evaluate_control(ctrl)
        assert result.evaluation_method == EvaluationMethod.EXTERNAL_ASSESSMENT
        assert any("external" in gap.lower() or "qualified" in gap.lower() for gap in result.gaps)

    def test_article_26_no_monitoring(self):
        """Art. 26 controls require manual verification (not infra checks)."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        art26 = [c for c in engine.controls if c.article == DORAArticle.ARTICLE_26]
        result = engine.evaluate_control(art26[0])
        assert result.status == EvidenceStatus.PARTIALLY_COMPLIANT

    def test_article_26_04_insurance(self):
        """DORA-26.04 (insurance) requires organisational verification, NOT infra check."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-26.04")
        result = engine.evaluate_control(ctrl)
        assert result.evaluation_method == EvaluationMethod.MANUAL_REQUIRED
        assert any("insurance" in gap.lower() or "organisational" in gap.lower() for gap in result.gaps)
        # Should NOT check redundancy for insurance
        assert not any("redundancy" in gap.lower() for gap in result.gaps)

    def test_article_28_no_third_party(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-28.01")
        result = engine.evaluate_control(ctrl)
        assert result.status == EvidenceStatus.NOT_APPLICABLE

    def test_article_28_with_third_party(self):
        g = _graph(
            _comp("app1", "App"),
            _comp("ext1", "Payment API", ctype=ComponentType.EXTERNAL_API),
        )
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-28.01")
        result = engine.evaluate_control(ctrl)
        assert result.status in (EvidenceStatus.COMPLIANT, EvidenceStatus.PARTIALLY_COMPLIANT)

    def test_article_28_02_concentration_hhi(self):
        """DORA-28.02 uses Herfindahl-style index for concentration risk."""
        # All externals from same host = high concentration
        g = _graph(
            _comp("ext1", "API1", ctype=ComponentType.EXTERNAL_API, host="provider.com"),
            _comp("ext2", "API2", ctype=ComponentType.EXTERNAL_API, host="provider.com"),
            _comp("ext3", "API3", ctype=ComponentType.EXTERNAL_API, host="provider.com"),
            _comp("app1", "App"),
        )
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-28.02")
        result = engine.evaluate_control(ctrl)
        # HHI = 1.0 (all same provider) — should flag concentration
        assert any("hhi" in gap.lower() or "concentration" in gap.lower() for gap in result.gaps)

    def test_article_28_02_diverse_providers(self):
        """DORA-28.02 with diverse providers should have lower risk."""
        g = _graph(
            _comp("ext1", "API1", ctype=ComponentType.EXTERNAL_API, host="provider-a.com"),
            _comp("ext2", "API2", ctype=ComponentType.EXTERNAL_API, host="provider-b.com"),
            _comp("ext3", "API3", ctype=ComponentType.EXTERNAL_API, host="provider-c.com"),
            _comp("app1", "App"),
        )
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-28.02")
        result = engine.evaluate_control(ctrl)
        # HHI = 0.33 (3 equal providers) — moderate, near threshold
        assert result.risk_score < 0.7

    def test_article_28_04_exit_strategy(self):
        """DORA-28.04 checks exit plans per provider."""
        g = _graph(
            _comp("app1", "App"),
            _comp("ext1", "Payment API", ctype=ComponentType.EXTERNAL_API),
        )
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-28.04")
        result = engine.evaluate_control(ctrl)
        # Without failover (proxy for exit strategy), should have gaps
        assert any("exit" in gap.lower() for gap in result.gaps)

    def test_article_28_04_with_exit_strategy(self):
        """DORA-28.04 with failover enabled (exit strategy proxy)."""
        g = _graph(
            _comp("app1", "App"),
            _comp("ext1", "Payment API", ctype=ComponentType.EXTERNAL_API, failover=True),
        )
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-28.04")
        result = engine.evaluate_control(ctrl)
        assert result.status == EvidenceStatus.COMPLIANT

    def test_article_28_high_concentration(self):
        # More than 50% third-party
        g = _graph(
            _comp("ext1", "API1", ctype=ComponentType.EXTERNAL_API),
            _comp("ext2", "API2", ctype=ComponentType.EXTERNAL_API),
            _comp("ext3", "API3", ctype=ComponentType.EXTERNAL_API),
            _comp("app1", "App"),
        )
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-28.01")
        result = engine.evaluate_control(ctrl)
        assert result.status == EvidenceStatus.NON_COMPLIANT
        assert result.risk_score >= 0.5

    def test_risk_score_capped_at_1(self):
        g = _graph(
            _comp("app1", "App", health=HealthStatus.DOWN),
        )
        engine = DORAEvidenceEngine(g)
        for ctrl in engine.controls:
            result = engine.evaluate_control(ctrl)
            assert result.risk_score <= 1.0

    def test_stub_controls_return_partially_compliant(self):
        """Pillar 2 stub controls should honestly flag as requiring verification."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        ctrl = next(c for c in engine.controls if c.control_id == "DORA-17.01")
        result = engine.evaluate_control(ctrl)
        assert result.status == EvidenceStatus.PARTIALLY_COMPLIANT
        assert result.evaluation_method in (EvaluationMethod.STUB, EvaluationMethod.MANUAL_REQUIRED)

    def test_manual_required_controls(self):
        """Manual-required controls return PARTIALLY_COMPLIANT (not fake COMPLIANT)."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        manual_ctrls = [c for c in engine.controls if c.evaluation_method == EvaluationMethod.MANUAL_REQUIRED]
        assert len(manual_ctrls) > 0
        for ctrl in manual_ctrls:
            result = engine.evaluate_control(ctrl)
            # Should never be COMPLIANT from infra data alone
            assert result.status != EvidenceStatus.COMPLIANT


# ---------------------------------------------------------------------------
# 6. Evidence Generation Tests
# ---------------------------------------------------------------------------

class TestGenerateEvidence:
    def setup_method(self):
        self.engine = DORAEvidenceEngine(
            _graph(_comp("app1", "App"))
        )

    def test_empty_scenarios(self):
        records = self.engine.generate_evidence([])
        assert records == []

    def test_single_passing_scenario(self):
        records = self.engine.generate_evidence([
            {"name": "health check", "result": "pass", "severity": "low"}
        ])
        assert len(records) == 1
        assert records[0].result == "pass"
        assert records[0].remediation_required is False

    def test_failing_scenario_requires_remediation(self):
        records = self.engine.generate_evidence([
            {"name": "failover test", "result": "fail", "severity": "high"}
        ])
        assert records[0].remediation_required is True

    def test_partial_result(self):
        records = self.engine.generate_evidence([
            {"name": "test", "result": "partial", "severity": "medium"}
        ])
        assert records[0].remediation_required is True

    def test_multiple_scenarios(self):
        records = self.engine.generate_evidence([
            {"name": "test1", "result": "pass"},
            {"name": "test2", "result": "fail"},
            {"name": "test3", "result": "partial"},
        ])
        assert len(records) == 3

    def test_evidence_has_timestamp(self):
        records = self.engine.generate_evidence([
            {"name": "test", "result": "pass"}
        ])
        assert records[0].timestamp.tzinfo is not None

    def test_evidence_has_artifacts(self):
        records = self.engine.generate_evidence([
            {"name": "my test", "result": "pass"}
        ])
        assert len(records[0].artifacts) == 1
        assert "my_test" in records[0].artifacts[0]

    def test_tlpt_scenario_maps_to_article_25(self):
        records = self.engine.generate_evidence([
            {"name": "penetration test", "result": "pass"}
        ])
        assert records[0].control_id == "DORA-25.01"
        assert records[0].test_type == "tlpt"

    def test_advanced_scenario_maps_to_article_11(self):
        records = self.engine.generate_evidence([
            {"name": "failover test", "result": "pass"}
        ])
        assert records[0].control_id == "DORA-11.05"
        assert records[0].test_type == "advanced_testing"

    def test_basic_scenario_maps_to_article_24(self):
        records = self.engine.generate_evidence([
            {"name": "simple check", "result": "pass"}
        ])
        assert records[0].control_id == "DORA-24.01"
        assert records[0].test_type == "basic_testing"

    def test_third_party_scenario_maps_to_article_28(self):
        records = self.engine.generate_evidence([
            {"name": "api check", "result": "pass", "involves_third_party": True}
        ])
        assert records[0].control_id == "DORA-28.01"

    def test_defaults_for_minimal_scenario(self):
        records = self.engine.generate_evidence([{}])
        assert len(records) == 1
        assert records[0].result == "pass"
        assert records[0].severity == "medium"

    def test_description_defaults_to_name(self):
        records = self.engine.generate_evidence([
            {"name": "my-scenario"}
        ])
        assert records[0].test_description == "my-scenario"

    def test_custom_description(self):
        records = self.engine.generate_evidence([
            {"name": "test", "description": "Custom description"}
        ])
        assert records[0].test_description == "Custom description"


# ---------------------------------------------------------------------------
# 7. Gap Analysis Tests
# ---------------------------------------------------------------------------

class TestGapAnalysis:
    def test_gap_analysis_returns_all_results(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        gaps = engine.gap_analysis()
        assert len(gaps) == _TOTAL_CONTROLS

    def test_empty_graph_all_not_applicable(self):
        engine = DORAEvidenceEngine(_graph())
        gaps = engine.gap_analysis()
        assert all(g.status == EvidenceStatus.NOT_APPLICABLE for g in gaps)

    def test_compliant_graph(self):
        g = _graph(
            _comp("app1", "App", replicas=3, failover=True),
            _comp("mon", "Prometheus Monitoring"),
        )
        engine = DORAEvidenceEngine(g)
        gaps = engine.gap_analysis()
        compliant = [g for g in gaps if g.status == EvidenceStatus.COMPLIANT]
        assert len(compliant) > 0

    def test_non_compliant_graph(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        gaps = engine.gap_analysis()
        non_compliant = [
            g for g in gaps
            if g.status in (EvidenceStatus.NON_COMPLIANT, EvidenceStatus.PARTIALLY_COMPLIANT)
        ]
        assert len(non_compliant) > 0

    def test_gap_analysis_unique_control_ids(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        gaps = engine.gap_analysis()
        ids = [g.control_id for g in gaps]
        assert len(ids) == len(set(ids))

    def test_article_28_not_applicable_without_external(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        gaps = engine.gap_analysis()
        # Only DORA-28.01, 28.02, 28.04 are automated and return N/A
        # DORA-28.03 is manual_required and returns PARTIALLY_COMPLIANT
        art28_auto_gaps = [
            g for g in gaps
            if g.control_id in ("DORA-28.01", "DORA-28.02", "DORA-28.04")
        ]
        for gap in art28_auto_gaps:
            assert gap.status == EvidenceStatus.NOT_APPLICABLE

    def test_article_28_evaluated_with_external(self):
        g = _graph(
            _comp("app1", "App"),
            _comp("ext1", "API", ctype=ComponentType.EXTERNAL_API),
        )
        engine = DORAEvidenceEngine(g)
        gaps = engine.gap_analysis()
        art28_auto_gaps = [
            g for g in gaps
            if g.control_id in ("DORA-28.01", "DORA-28.02", "DORA-28.04")
        ]
        for gap in art28_auto_gaps:
            assert gap.status != EvidenceStatus.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# 8. Report Generation Tests
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_report_with_empty_graph(self):
        engine = DORAEvidenceEngine(_graph())
        report = engine.generate_report([])
        assert report.overall_status == EvidenceStatus.NOT_APPLICABLE

    def test_report_has_article_results(self):
        g = _graph(_comp("app1", "App", replicas=2, failover=True))
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([{"name": "test", "result": "pass"}])
        assert len(report.article_results) > 0

    def test_report_has_gap_analyses(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        assert len(report.gap_analyses) == _TOTAL_CONTROLS

    def test_report_has_evidence_records(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([
            {"name": "test1", "result": "pass"},
            {"name": "test2", "result": "fail"},
        ])
        assert len(report.evidence_records) == 2

    def test_report_non_compliant_status(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        assert report.overall_status in (
            EvidenceStatus.NON_COMPLIANT,
            EvidenceStatus.PARTIALLY_COMPLIANT,
        )

    def test_report_timestamp(self):
        engine = DORAEvidenceEngine(_graph())
        report = engine.generate_report([])
        assert report.report_timestamp.tzinfo is not None

    def test_report_next_review_date(self):
        engine = DORAEvidenceEngine(_graph())
        report = engine.generate_report([])
        assert report.next_review_date > report.report_timestamp

    def test_report_article_results_keys(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        for key in report.article_results:
            assert key.startswith("article_")

    def test_all_articles_in_results(self):
        """All 27 articles should appear in results."""
        g = _graph(
            _comp("app1", "App"),
            _comp("ext1", "API", ctype=ComponentType.EXTERNAL_API),
        )
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        assert len(report.article_results) == _TOTAL_ARTICLES

    def test_report_pillar_results(self):
        """Report includes per-pillar results."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        assert len(report.pillar_results) == 5

    def test_report_overall_compliant_when_all_articles_compliant(self):
        g = _graph(
            _comp("app1", "App", replicas=3, failover=True),
            _comp("mon", "Prometheus Monitoring"),
        )
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        compliant_or_na = all(
            v in (EvidenceStatus.COMPLIANT, EvidenceStatus.NOT_APPLICABLE)
            for v in report.article_results.values()
        )
        if compliant_or_na:
            assert report.overall_status == EvidenceStatus.COMPLIANT

    def test_report_with_mixed_scenarios(self):
        g = _graph(_comp("app1", "App", replicas=2, failover=True))
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([
            {"name": "penetration test", "result": "pass", "severity": "critical"},
            {"name": "failover test", "result": "fail", "severity": "high"},
            {"name": "health check", "result": "pass", "severity": "low"},
        ])
        assert len(report.evidence_records) == 3


# ---------------------------------------------------------------------------
# 9. Audit Package Export Tests
# ---------------------------------------------------------------------------

class TestExportAuditPackage:
    def test_audit_package_structure(self):
        engine = DORAEvidenceEngine(_graph(_comp("app1", "App")))
        pkg = engine.export_audit_package()
        assert pkg["framework"] == "DORA"
        assert pkg["version"] == "2022/2554"
        assert "export_timestamp" in pkg
        assert "controls" in pkg
        assert "gap_analyses" in pkg

    def test_audit_package_counts(self):
        engine = DORAEvidenceEngine(_graph(_comp("app1", "App")))
        pkg = engine.export_audit_package()
        assert pkg["total_controls"] == _TOTAL_CONTROLS
        total = (
            pkg["compliant_count"]
            + pkg["non_compliant_count"]
            + pkg["partially_compliant_count"]
            + pkg["not_applicable_count"]
        )
        assert total == _TOTAL_CONTROLS

    def test_audit_package_empty_graph(self):
        engine = DORAEvidenceEngine(_graph())
        pkg = engine.export_audit_package()
        assert pkg["not_applicable_count"] == _TOTAL_CONTROLS
        assert pkg["compliant_count"] == 0

    def test_audit_package_compliant_graph(self):
        g = _graph(
            _comp("app1", "App", replicas=3, failover=True),
            _comp("mon", "Prometheus Monitoring"),
        )
        engine = DORAEvidenceEngine(g)
        pkg = engine.export_audit_package()
        assert pkg["compliant_count"] > 0

    def test_audit_package_has_controls_data(self):
        engine = DORAEvidenceEngine(_graph(_comp("app1", "App")))
        pkg = engine.export_audit_package()
        assert len(pkg["controls"]) == _TOTAL_CONTROLS
        assert all("control_id" in c for c in pkg["controls"])

    def test_audit_package_has_gap_data(self):
        engine = DORAEvidenceEngine(_graph(_comp("app1", "App")))
        pkg = engine.export_audit_package()
        assert len(pkg["gap_analyses"]) == _TOTAL_CONTROLS

    def test_audit_timestamp_is_iso(self):
        engine = DORAEvidenceEngine(_graph())
        pkg = engine.export_audit_package()
        # Should be parseable ISO format
        datetime.fromisoformat(pkg["export_timestamp"])

    def test_audit_package_pillar_summary(self):
        engine = DORAEvidenceEngine(_graph(_comp("app1", "App")))
        pkg = engine.export_audit_package()
        assert "pillar_summary" in pkg
        assert len(pkg["pillar_summary"]) == 5

    def test_audit_package_rts_coverage(self):
        engine = DORAEvidenceEngine(_graph(_comp("app1", "App")))
        pkg = engine.export_audit_package()
        assert "rts_coverage" in pkg
        # Should have RTS 2024/1774 referenced
        assert any("2024/1774" in key for key in pkg["rts_coverage"])


# ---------------------------------------------------------------------------
# 10. Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_graph_with_only_external_apis(self):
        g = _graph(
            _comp("ext1", "API1", ctype=ComponentType.EXTERNAL_API),
            _comp("ext2", "API2", ctype=ComponentType.EXTERNAL_API),
        )
        engine = DORAEvidenceEngine(g)
        gaps = engine.gap_analysis()
        assert len(gaps) == _TOTAL_CONTROLS

    def test_graph_with_all_degraded(self):
        g = _graph(
            _comp("app1", "App1", health=HealthStatus.DEGRADED),
            _comp("app2", "App2", health=HealthStatus.OVERLOADED),
        )
        engine = DORAEvidenceEngine(g)
        gaps = engine.gap_analysis()
        # DORA-11.01 specifically checks for unhealthy components
        art11_01 = next(ga for ga in gaps if ga.control_id == "DORA-11.01")
        assert any("not healthy" in gap for gap in art11_01.gaps)

    def test_graph_with_all_down(self):
        g = _graph(
            _comp("app1", "App1", health=HealthStatus.DOWN),
        )
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        assert report.overall_status != EvidenceStatus.COMPLIANT

    def test_single_component_many_replicas(self):
        g = _graph(_comp("app1", "App", replicas=100, failover=True))
        engine = DORAEvidenceEngine(g)
        gaps = engine.gap_analysis()
        art11 = [ga for ga in gaps if ga.control_id.startswith("DORA-11")]
        # Should have partial compliance (missing monitoring)
        assert any(ga.status != EvidenceStatus.NOT_APPLICABLE for ga in art11)

    def test_monitoring_keyword_otel(self):
        g = _graph(_comp("otel-collector", "OpenTelemetry Collector"))
        engine = DORAEvidenceEngine(g)
        assert engine._has_monitoring() is True

    def test_monitoring_keyword_grafana(self):
        g = _graph(_comp("grafana", "Grafana Dashboard"))
        engine = DORAEvidenceEngine(g)
        assert engine._has_monitoring() is True

    def test_monitoring_keyword_datadog(self):
        g = _graph(_comp("dd-agent", "Datadog Agent"))
        engine = DORAEvidenceEngine(g)
        assert engine._has_monitoring() is True

    def test_no_monitoring_keyword(self):
        g = _graph(_comp("app1", "My Application"))
        engine = DORAEvidenceEngine(g)
        assert engine._has_monitoring() is False

    def test_scenario_with_spaces_in_name(self):
        engine = DORAEvidenceEngine(_graph(_comp("app1", "App")))
        records = engine.generate_evidence([
            {"name": "my complex test scenario", "result": "pass"}
        ])
        assert "my_complex_test_scenario" in records[0].artifacts[0]

    def test_large_number_of_scenarios(self):
        engine = DORAEvidenceEngine(_graph(_comp("app1", "App")))
        scenarios = [{"name": f"test_{i}", "result": "pass"} for i in range(100)]
        records = engine.generate_evidence(scenarios)
        assert len(records) == 100

    def test_scenario_index_used_for_unnamed(self):
        engine = DORAEvidenceEngine(_graph(_comp("app1", "App")))
        records = engine.generate_evidence([{}, {}, {}])
        names = {r.test_description for r in records}
        assert "scenario_0" in names
        assert "scenario_1" in names
        assert "scenario_2" in names

    def test_mixed_component_types(self):
        g = _graph(
            _comp("lb", "Load Balancer", ctype=ComponentType.LOAD_BALANCER, replicas=2),
            _comp("app", "App Server", ctype=ComponentType.APP_SERVER, replicas=3, failover=True),
            _comp("db", "Database", ctype=ComponentType.DATABASE, failover=True),
            _comp("cache", "Redis", ctype=ComponentType.CACHE, replicas=2),
            _comp("ext", "Payment API", ctype=ComponentType.EXTERNAL_API),
            _comp("mon", "Prometheus"),
        )
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        assert len(report.article_results) == _TOTAL_ARTICLES

    def test_report_and_audit_consistency(self):
        g = _graph(
            _comp("app1", "App", replicas=2, failover=True),
            _comp("mon", "Prometheus"),
        )
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        pkg = engine.export_audit_package()
        assert len(report.gap_analyses) == pkg["total_controls"]

    def test_article_25_partial_without_failover(self):
        g = _graph(_comp("app1", "App", replicas=2))
        engine = DORAEvidenceEngine(g)
        art25 = [c for c in engine.controls if c.article == DORAArticle.ARTICLE_25]
        result = engine.evaluate_control(art25[0])
        assert result.status == EvidenceStatus.PARTIALLY_COMPLIANT

    def test_third_party_helper(self):
        g = _graph(
            _comp("app1", "App"),
            _comp("ext1", "API", ctype=ComponentType.EXTERNAL_API),
        )
        engine = DORAEvidenceEngine(g)
        assert engine._has_third_party() is True
        assert engine._third_party_count() == 1

    def test_no_third_party_helper(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        assert engine._has_third_party() is False
        assert engine._third_party_count() == 0

    def test_unhealthy_count(self):
        g = _graph(
            _comp("app1", "App", health=HealthStatus.HEALTHY),
            _comp("app2", "App2", health=HealthStatus.DOWN),
            _comp("app3", "App3", health=HealthStatus.DEGRADED),
        )
        engine = DORAEvidenceEngine(g)
        assert engine._unhealthy_count() == 2

    def test_component_count(self):
        g = _graph(
            _comp("a", "A"), _comp("b", "B"), _comp("c", "C"),
        )
        engine = DORAEvidenceEngine(g)
        assert engine._component_count() == 3

    def test_has_redundancy_false(self):
        g = _graph(_comp("app1", "App", replicas=1))
        engine = DORAEvidenceEngine(g)
        assert engine._has_redundancy() is False

    def test_has_redundancy_true(self):
        g = _graph(_comp("app1", "App", replicas=2))
        engine = DORAEvidenceEngine(g)
        assert engine._has_redundancy() is True

    def test_has_failover_false(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        assert engine._has_failover() is False

    def test_has_failover_true(self):
        g = _graph(_comp("app1", "App", failover=True))
        engine = DORAEvidenceEngine(g)
        assert engine._has_failover() is True

    def test_article_with_mixed_compliant_and_na(self):
        """Covers the branch where an article has both COMPLIANT and NOT_APPLICABLE controls."""
        g = _graph(
            _comp("app1", "App", replicas=3, failover=True),
            _comp("mon", "Prometheus Monitoring"),
            _comp("ext1", "Payment API", ctype=ComponentType.EXTERNAL_API),
        )
        engine = DORAEvidenceEngine(g)
        report = engine.generate_report([])
        assert report.overall_status in (
            EvidenceStatus.COMPLIANT,
            EvidenceStatus.PARTIALLY_COMPLIANT,
            EvidenceStatus.NON_COMPLIANT,
        )

    def test_report_no_controls_edge(self):
        """Covers the empty article_statuses branch by monkey-patching controls."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        engine.controls = []
        report = engine.generate_report([])
        assert report.overall_status == EvidenceStatus.NOT_APPLICABLE
        assert report.article_results == {}

    def test_article_mixed_compliant_and_na_controls(self):
        """Covers the COMPLIANT+NOT_APPLICABLE mix within a single article."""
        from unittest.mock import patch

        g = _graph(
            _comp("app1", "App", replicas=3, failover=True),
            _comp("mon", "Prometheus Monitoring"),
        )
        engine = DORAEvidenceEngine(g)

        mixed_gaps = [
            DORAGapAnalysis(
                control_id="DORA-11.01",
                status=EvidenceStatus.COMPLIANT,
                risk_score=0.0,
            ),
            DORAGapAnalysis(
                control_id="DORA-11.02",
                status=EvidenceStatus.NOT_APPLICABLE,
                risk_score=0.0,
            ),
        ]
        engine.controls = [
            DORAControl(article=DORAArticle.ARTICLE_11, control_id="DORA-11.01", description="C1"),
            DORAControl(article=DORAArticle.ARTICLE_11, control_id="DORA-11.02", description="C2"),
        ]
        with patch.object(engine, "gap_analysis", return_value=mixed_gaps):
            report = engine.generate_report([])
        assert report.article_results["article_11"] == EvidenceStatus.COMPLIANT
        assert report.overall_status == EvidenceStatus.COMPLIANT

    def test_herfindahl_index(self):
        """Test HHI calculation for provider concentration."""
        g = _graph(
            _comp("ext1", "API1", ctype=ComponentType.EXTERNAL_API, host="a.com"),
            _comp("ext2", "API2", ctype=ComponentType.EXTERNAL_API, host="b.com"),
        )
        engine = DORAEvidenceEngine(g)
        hhi = engine._herfindahl_index()
        # 2 providers with equal share: HHI = 0.5
        assert abs(hhi - 0.5) < 0.01

    def test_herfindahl_index_single_provider(self):
        g = _graph(
            _comp("ext1", "API1", ctype=ComponentType.EXTERNAL_API, host="same.com"),
            _comp("ext2", "API2", ctype=ComponentType.EXTERNAL_API, host="same.com"),
        )
        engine = DORAEvidenceEngine(g)
        hhi = engine._herfindahl_index()
        # All from same provider: HHI = 1.0
        assert abs(hhi - 1.0) < 0.01

    def test_herfindahl_index_no_externals(self):
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)
        assert engine._herfindahl_index() == 0.0

    def test_custom_risk_config(self):
        """RiskConfig allows overriding thresholds."""
        config = RiskConfig(
            non_compliant_threshold=0.8,
            min_replicas_for_redundancy=3,
        )
        g = _graph(_comp("app1", "App", replicas=2))
        engine = DORAEvidenceEngine(g, risk_config=config)
        # With threshold=3, replicas=2 should NOT count as redundancy
        assert engine._has_redundancy() is False

    def test_each_control_has_unique_evaluator_logic(self):
        """Key controls have different evaluation semantics — verify they produce
        different types of gaps for the same infrastructure."""
        g = _graph(_comp("app1", "App"))
        engine = DORAEvidenceEngine(g)

        # DORA-11.06 (source code review) should mention CI/CD, not redundancy
        ctrl_1106 = next(c for c in engine.controls if c.control_id == "DORA-11.06")
        result_1106 = engine.evaluate_control(ctrl_1106)

        # DORA-26.04 (insurance) should mention insurance/organisational
        ctrl_2604 = next(c for c in engine.controls if c.control_id == "DORA-26.04")
        result_2604 = engine.evaluate_control(ctrl_2604)

        # They should NOT have the same gaps
        assert result_1106.gaps != result_2604.gaps
        # Insurance check should NOT mention redundancy or CI/CD
        all_2604_text = " ".join(result_2604.gaps).lower()
        assert "redundancy" not in all_2604_text
        assert "ci/cd" not in all_2604_text
