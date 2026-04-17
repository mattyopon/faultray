# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for AI Governance module (METI / ISO42001 / AI推進法)."""

from __future__ import annotations

import json

import pytest

from faultray.governance.frameworks import (
    METI_CATEGORIES,
    METI_QUESTIONS,
    ISO_CLAUSES,
    ACT_CHAPTERS,
    CROSS_MAPPING,
    GovernanceFramework,
    METIRequirement,
    ISORequirement,
    ActRequirement,
    all_meti_requirements,
    all_iso_requirements,
    all_act_requirements,
    get_meti_to_iso_mapping,
    get_meti_to_act_mapping,
    get_coverage_matrix,
    get_frameworks_for_meti_requirement,
)
from faultray.governance.assessor import (
    GovernanceAssessor,
    AssessmentResult,
    CategoryScore,
    MATURITY_LABELS,
    _score_to_maturity,
    _raw_to_percent,
)
from faultray.governance.reporter import GovernanceReporter


# ---------------------------------------------------------------------------
# Framework data integrity tests
# ---------------------------------------------------------------------------


class TestMETIFramework:
    """METI AI事業者ガイドライン v1.1 data integrity."""

    def test_has_10_principles(self) -> None:
        assert len(METI_CATEGORIES) == 10

    def test_has_28_requirements(self) -> None:
        assert len(all_meti_requirements()) == 28

    def test_categories_have_ids(self) -> None:
        ids = [c.category_id for c in METI_CATEGORIES]
        expected = [f"C{i:02d}" for i in range(1, 11)]
        assert ids == expected

    def test_requirements_have_correct_category_refs(self) -> None:
        for cat in METI_CATEGORIES:
            for req in cat.requirements:
                assert req.category_id == cat.category_id

    def test_requirement_ids_unique(self) -> None:
        ids = [r.req_id for r in all_meti_requirements()]
        assert len(ids) == len(set(ids))

    def test_25_questions(self) -> None:
        assert len(METI_QUESTIONS) == 25

    def test_questions_have_5_options(self) -> None:
        for q in METI_QUESTIONS:
            assert len(q.options) == 5
            assert len(q.scores) == 5

    def test_questions_reference_valid_requirements(self) -> None:
        valid_ids = {r.req_id for r in all_meti_requirements()}
        for q in METI_QUESTIONS:
            for req_id in q.requirement_ids:
                assert req_id in valid_ids, f"Q {q.question_id} references unknown req {req_id}"

    def test_questions_cover_all_categories(self) -> None:
        cat_ids = {q.category_id for q in METI_QUESTIONS}
        expected = {f"C{i:02d}" for i in range(1, 11)}
        assert cat_ids == expected


class TestISO42001Framework:
    """ISO/IEC 42001:2023 AIMS data integrity."""

    def test_has_7_clauses(self) -> None:
        assert len(ISO_CLAUSES) == 7

    def test_has_25_requirements(self) -> None:
        assert len(all_iso_requirements()) == 25

    def test_clause_ids(self) -> None:
        ids = [c.clause_id for c in ISO_CLAUSES]
        expected = ["4", "5", "6", "7", "8", "9", "10"]
        assert ids == expected

    def test_requirement_ids_unique(self) -> None:
        ids = [r.req_id for r in all_iso_requirements()]
        assert len(ids) == len(set(ids))

    def test_all_requirements_have_meti_mapping(self) -> None:
        for req in all_iso_requirements():
            assert len(req.meti_mapping) > 0, f"{req.req_id} has no METI mapping"

    def test_meti_mapping_references_valid_ids(self) -> None:
        valid_ids = {r.req_id for r in all_meti_requirements()}
        for req in all_iso_requirements():
            for meti_id in req.meti_mapping:
                assert meti_id in valid_ids, f"ISO {req.req_id} maps to unknown METI {meti_id}"


class TestAIPromotionAct:
    """AI推進法 data integrity."""

    def test_has_6_chapters(self) -> None:
        assert len(ACT_CHAPTERS) == 6

    def test_has_15_requirements(self) -> None:
        assert len(all_act_requirements()) == 15

    def test_chapter_ids(self) -> None:
        ids = [c.chapter_id for c in ACT_CHAPTERS]
        expected = [f"CH{i}" for i in range(1, 7)]
        assert ids == expected

    def test_requirement_ids_unique(self) -> None:
        ids = [r.req_id for r in all_act_requirements()]
        assert len(ids) == len(set(ids))

    def test_has_mandatory_requirements(self) -> None:
        mandatory = [r for r in all_act_requirements() if r.obligation_type == "mandatory"]
        assert len(mandatory) >= 5  # CH1 and CH3 have mandatory requirements

    def test_meti_mapping_references_valid_ids(self) -> None:
        valid_ids = {r.req_id for r in all_meti_requirements()}
        for req in all_act_requirements():
            for meti_id in req.meti_mapping:
                assert meti_id in valid_ids, f"APA {req.req_id} maps to unknown METI {meti_id}"

    def test_iso_mapping_references_valid_ids(self) -> None:
        valid_ids = {r.req_id for r in all_iso_requirements()}
        for req in all_act_requirements():
            for iso_id in req.iso_mapping:
                assert iso_id in valid_ids, f"APA {req.req_id} maps to unknown ISO {iso_id}"


# ---------------------------------------------------------------------------
# Cross-mapping tests
# ---------------------------------------------------------------------------


class TestCrossMapping:
    """Cross-framework mapping integrity."""

    def test_has_15_themes(self) -> None:
        assert len(CROSS_MAPPING) == 15

    def test_theme_ids_unique(self) -> None:
        ids = [e.theme_id for e in CROSS_MAPPING]
        assert len(ids) == len(set(ids))

    def test_all_themes_have_meti_ids(self) -> None:
        for entry in CROSS_MAPPING:
            assert len(entry.meti_ids) > 0, f"Theme {entry.theme_id} has no METI IDs"

    def test_meti_to_iso_mapping(self) -> None:
        mapping = get_meti_to_iso_mapping()
        assert isinstance(mapping, dict)
        assert len(mapping) > 0
        # Check that mapped ISO IDs are valid
        valid_iso = {r.req_id for r in all_iso_requirements()}
        for meti_id, iso_ids in mapping.items():
            for iso_id in iso_ids:
                assert iso_id in valid_iso

    def test_meti_to_act_mapping(self) -> None:
        mapping = get_meti_to_act_mapping()
        assert isinstance(mapping, dict)
        assert len(mapping) > 0

    def test_coverage_matrix(self) -> None:
        matrix = get_coverage_matrix()
        assert len(matrix) == 15
        for theme_id, data in matrix.items():
            assert "theme" in data
            assert "meti" in data
            assert "iso" in data
            assert "act" in data

    def test_frameworks_for_meti_requirement(self) -> None:
        result = get_frameworks_for_meti_requirement("C07-R01")
        assert "iso" in result
        assert "act" in result
        assert len(result["iso"]) > 0  # C07-R01 maps to ISO-5.1, ISO-5.3


# ---------------------------------------------------------------------------
# Assessment scoring tests
# ---------------------------------------------------------------------------


class TestAssessmentScoring:
    """Governance assessment scoring logic."""

    def test_maturity_level_boundaries(self) -> None:
        assert _score_to_maturity(0.0) == 1
        assert _score_to_maturity(0.7) == 1
        assert _score_to_maturity(0.8) == 2
        assert _score_to_maturity(1.5) == 2
        assert _score_to_maturity(1.6) == 3
        assert _score_to_maturity(2.3) == 3
        assert _score_to_maturity(2.4) == 4
        assert _score_to_maturity(3.1) == 4
        assert _score_to_maturity(3.2) == 5
        assert _score_to_maturity(4.0) == 5

    def test_raw_to_percent(self) -> None:
        assert _raw_to_percent(0.0) == 0.0
        assert _raw_to_percent(2.0) == 50.0
        assert _raw_to_percent(4.0) == 100.0

    def test_maturity_labels_complete(self) -> None:
        for level in range(1, 6):
            assert level in MATURITY_LABELS

    def test_all_zeros_assessment(self) -> None:
        assessor = GovernanceAssessor()
        result = assessor.assess({})
        assert result.overall_score == 0.0
        assert result.maturity_level == 1
        assert len(result.category_scores) == 10
        assert all(cs.score == 0.0 for cs in result.category_scores)

    def test_all_max_assessment(self) -> None:
        assessor = GovernanceAssessor()
        answers = {q.question_id: 4 for q in METI_QUESTIONS}
        result = assessor.assess(answers)
        assert result.overall_score == 100.0
        assert result.maturity_level == 5
        assert all(cs.maturity_level == 5 for cs in result.category_scores)

    def test_partial_assessment(self) -> None:
        assessor = GovernanceAssessor()
        answers = {q.question_id: 2 for q in METI_QUESTIONS}
        result = assessor.assess(answers)
        assert 40.0 <= result.overall_score <= 60.0
        assert result.maturity_level == 3

    def test_framework_coverage_computed(self) -> None:
        assessor = GovernanceAssessor()
        answers = {q.question_id: 3 for q in METI_QUESTIONS}
        result = assessor.assess(answers)
        assert GovernanceFramework.METI_V1_1.value in result.framework_coverage
        assert GovernanceFramework.ISO42001.value in result.framework_coverage
        assert GovernanceFramework.AI_PROMOTION.value in result.framework_coverage

    def test_gaps_generated_for_low_scores(self) -> None:
        assessor = GovernanceAssessor()
        result = assessor.assess({})
        assert len(result.top_gaps) > 0

    def test_recommendations_generated_for_low_scores(self) -> None:
        assessor = GovernanceAssessor()
        result = assessor.assess({})
        assert len(result.top_recommendations) > 0

    def test_no_gaps_for_max_scores(self) -> None:
        assessor = GovernanceAssessor()
        answers = {q.question_id: 4 for q in METI_QUESTIONS}
        result = assessor.assess(answers)
        assert len(result.top_gaps) == 0

    def test_auto_assess(self) -> None:
        assessor = GovernanceAssessor()
        result = assessor.assess_auto(
            has_monitoring=True,
            has_auth=True,
            has_encryption=True,
        )
        assert result.overall_score > 0.0
        assert result.maturity_level >= 1

    def test_requirement_scores_computed(self) -> None:
        assessor = GovernanceAssessor()
        answers = {q.question_id: 2 for q in METI_QUESTIONS}
        result = assessor.assess(answers)
        assert len(result.requirement_scores) > 0
        for rs in result.requirement_scores:
            assert rs.framework == GovernanceFramework.METI_V1_1

    def test_invalid_answer_index_clamped(self) -> None:
        assessor = GovernanceAssessor()
        answers = {"Q01": 99, "Q02": -5}
        result = assessor.assess(answers)
        # Should not crash; out-of-range indices are clamped
        assert result.overall_score >= 0.0


# ---------------------------------------------------------------------------
# Reporter tests
# ---------------------------------------------------------------------------


class TestReporter:
    """Governance report generation tests."""

    def test_json_export(self) -> None:
        assessor = GovernanceAssessor()
        result = assessor.assess({q.question_id: 2 for q in METI_QUESTIONS})
        reporter = GovernanceReporter(result)
        json_str = reporter.to_json()
        data = json.loads(json_str)

        assert "assessment" in data
        assert "frameworks" in data
        assert "cross_mapping" in data

        assert data["frameworks"]["meti_v1_1"]["principles"] == 10
        assert data["frameworks"]["meti_v1_1"]["requirements"] == 28
        assert data["frameworks"]["iso42001"]["clauses"] == 7
        assert data["frameworks"]["iso42001"]["requirements"] == 25
        assert data["frameworks"]["ai_promotion"]["chapters"] == 6
        assert data["frameworks"]["ai_promotion"]["requirements"] == 15

    def test_json_export_without_assessment(self) -> None:
        reporter = GovernanceReporter()
        json_str = reporter.to_json()
        data = json.loads(json_str)
        assert "assessment" not in data
        assert "frameworks" in data

    def test_json_export_to_file(self, tmp_path: "Path") -> None:
        reporter = GovernanceReporter()
        outfile = tmp_path / "report.json"
        reporter.to_json(outfile)
        assert outfile.exists()
        data = json.loads(outfile.read_text())
        assert "frameworks" in data

    def test_cross_mapping_count(self) -> None:
        reporter = GovernanceReporter()
        json_str = reporter.to_json()
        data = json.loads(json_str)
        assert len(data["cross_mapping"]) == 15


# ---------------------------------------------------------------------------
# CLI command existence tests
# ---------------------------------------------------------------------------


class TestCLICommands:
    """Verify governance CLI commands are registered."""

    def test_governance_app_exists(self) -> None:
        from faultray.cli.governance_cmd import governance_app
        assert governance_app is not None

    def test_governance_assess_command_exists(self) -> None:
        from faultray.cli.governance_cmd import governance_assess
        assert governance_assess is not None

    def test_governance_report_command_exists(self) -> None:
        from faultray.cli.governance_cmd import governance_report
        assert governance_report is not None

    def test_governance_cross_map_command_exists(self) -> None:
        from faultray.cli.governance_cmd import governance_cross_map
        assert governance_cross_map is not None


# ---------------------------------------------------------------------------
# Compliance frameworks integration tests
# ---------------------------------------------------------------------------


class TestComplianceFrameworksIntegration:
    """Verify Japanese frameworks are registered in existing compliance systems."""

    def test_compliance_frameworks_enum_has_meti(self) -> None:
        from faultray.simulator.compliance_frameworks import ComplianceFramework
        assert ComplianceFramework.METI_V1_1 == "meti-v1.1"

    def test_compliance_frameworks_enum_has_iso42001(self) -> None:
        from faultray.simulator.compliance_frameworks import ComplianceFramework
        assert ComplianceFramework.ISO42001 == "iso42001"

    def test_compliance_frameworks_enum_has_ai_promotion(self) -> None:
        from faultray.simulator.compliance_frameworks import ComplianceFramework
        assert ComplianceFramework.AI_PROMOTION == "ai-promotion"

    def test_compliance_monitor_enum_has_meti(self) -> None:
        from faultray.simulator.compliance_monitor import ComplianceFramework
        assert ComplianceFramework.METI_V1_1 == "meti-v1.1"

    def test_compliance_monitor_enum_has_iso42001(self) -> None:
        from faultray.simulator.compliance_monitor import ComplianceFramework
        assert ComplianceFramework.ISO42001 == "iso42001"

    def test_compliance_monitor_enum_has_ai_promotion(self) -> None:
        from faultray.simulator.compliance_monitor import ComplianceFramework
        assert ComplianceFramework.AI_PROMOTION == "ai-promotion"

    def test_frameworks_engine_supports_meti(self) -> None:
        from faultray.simulator.compliance_frameworks import (
            ComplianceFramework,
            ComplianceFrameworksEngine,
        )
        engine = ComplianceFrameworksEngine()
        report = engine.assess(ComplianceFramework.METI_V1_1)
        assert report.framework == ComplianceFramework.METI_V1_1
        assert len(report.controls) == 10

    def test_frameworks_engine_supports_iso42001(self) -> None:
        from faultray.simulator.compliance_frameworks import (
            ComplianceFramework,
            ComplianceFrameworksEngine,
        )
        engine = ComplianceFrameworksEngine()
        report = engine.assess(ComplianceFramework.ISO42001)
        assert report.framework == ComplianceFramework.ISO42001
        assert len(report.controls) == 7

    def test_frameworks_engine_supports_ai_promotion(self) -> None:
        from faultray.simulator.compliance_frameworks import (
            ComplianceFramework,
            ComplianceFrameworksEngine,
        )
        engine = ComplianceFrameworksEngine()
        report = engine.assess(ComplianceFramework.AI_PROMOTION)
        assert report.framework == ComplianceFramework.AI_PROMOTION
        assert len(report.controls) == 6
