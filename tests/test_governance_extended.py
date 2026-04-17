# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for extended governance features:
- AI Registry
- Evidence Manager (with hash chain)
- Policy Generator
- Gap Analyzer
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect all governance storage to tmp_path for test isolation."""
    storage = tmp_path / "governance"
    storage.mkdir()

    # ai_registry
    import faultray.governance.ai_registry as reg_mod

    monkeypatch.setattr(reg_mod, "_STORAGE_DIR", storage)
    monkeypatch.setattr(reg_mod, "_REGISTRY_FILE", storage / "ai_registry.json")

    # evidence_manager
    import faultray.governance.evidence_manager as ev_mod

    monkeypatch.setattr(ev_mod, "_STORAGE_DIR", storage)
    monkeypatch.setattr(ev_mod, "_EVIDENCE_DIR", storage / "evidence")
    monkeypatch.setattr(ev_mod, "_EVIDENCE_FILE", storage / "evidence_records.json")
    monkeypatch.setattr(ev_mod, "_AUDIT_FILE", storage / "audit_chain.json")


@pytest.fixture()
def sample_evidence_file(tmp_path: Path) -> Path:
    """Create a sample file for evidence registration."""
    f = tmp_path / "evidence_sample.txt"
    f.write_text("This is governance evidence.", encoding="utf-8")
    return f


# ===========================================================================
# AI Registry Tests (10 tests)
# ===========================================================================


class TestAIRegistry:
    """Tests for ai_registry module."""

    def test_register_and_get(self) -> None:
        from faultray.governance.ai_registry import AISystem, get_ai_system, register_ai_system

        system = AISystem(name="Test Bot", org_id="org1", ai_type="generative")
        sid = register_ai_system(system)
        assert sid
        fetched = get_ai_system(sid)
        assert fetched is not None
        assert fetched.name == "Test Bot"

    def test_list_by_org(self) -> None:
        from faultray.governance.ai_registry import AISystem, list_ai_systems, register_ai_system

        register_ai_system(AISystem(name="A", org_id="org1"))
        register_ai_system(AISystem(name="B", org_id="org1"))
        register_ai_system(AISystem(name="C", org_id="org2"))

        org1 = list_ai_systems("org1")
        assert len(org1) == 2
        org2 = list_ai_systems("org2")
        assert len(org2) == 1

    def test_list_empty_org(self) -> None:
        from faultray.governance.ai_registry import list_ai_systems

        assert list_ai_systems("nonexistent") == []

    def test_detect_shadow_ai_finds_unregistered(self) -> None:
        from faultray.governance.ai_registry import AISystem, detect_shadow_ai, register_ai_system

        register_ai_system(AISystem(name="Approved Bot", org_id="org1"))
        shadows = detect_shadow_ai("org1", ["Approved Bot", "Shadow Tool"])
        assert len(shadows) == 1
        assert shadows[0]["system_name"] == "Shadow Tool"
        assert shadows[0]["status"] == "unregistered"

    def test_detect_shadow_ai_no_shadows(self) -> None:
        from faultray.governance.ai_registry import AISystem, detect_shadow_ai, register_ai_system

        register_ai_system(AISystem(name="Bot A", org_id="org1"))
        shadows = detect_shadow_ai("org1", ["Bot A"])
        assert len(shadows) == 0

    def test_risk_summary(self) -> None:
        from faultray.governance.ai_registry import AISystem, get_risk_summary, register_ai_system

        register_ai_system(AISystem(name="A", org_id="org1", risk_level="high", has_pia=True))
        register_ai_system(AISystem(name="B", org_id="org1", risk_level="minimal", has_ria=True))

        summary = get_risk_summary("org1")
        assert summary["total_systems"] == 2
        assert summary["by_risk_level"]["high"] == 1
        assert summary["by_risk_level"]["minimal"] == 1
        assert summary["high_risk_count"] == 1
        assert summary["pia_coverage"] == 0.5

    def test_risk_summary_empty(self) -> None:
        from faultray.governance.ai_registry import get_risk_summary

        summary = get_risk_summary("empty_org")
        assert summary["total_systems"] == 0

    def test_auto_risk_classification_high(self) -> None:
        from faultray.governance.ai_registry import AISystem, classify_risk_level

        system = AISystem(name="Medical diagnosis AI", purpose="患者の診断支援")
        assert classify_risk_level(system) == "high"

    def test_auto_risk_classification_limited(self) -> None:
        from faultray.governance.ai_registry import AISystem, classify_risk_level

        system = AISystem(name="Office chatbot", ai_type="generative")
        assert classify_risk_level(system) == "limited"

    def test_auto_risk_classification_minimal(self) -> None:
        from faultray.governance.ai_registry import AISystem, classify_risk_level

        system = AISystem(name="Internal tool", ai_type="other", purpose="internal sorting")
        assert classify_risk_level(system) == "minimal"


# ===========================================================================
# Evidence Manager Tests (10 tests)
# ===========================================================================


class TestEvidenceManager:
    """Tests for evidence_manager module."""

    def test_register_evidence(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import register_evidence

        record = register_evidence("C01-R01", "AI policy doc", str(sample_evidence_file))
        assert record.id.startswith("EVD-")
        assert record.requirement_id == "C01-R01"
        assert record.file_hash  # non-empty SHA-256

    def test_list_evidence_all(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import list_evidence, register_evidence

        register_evidence("C01-R01", "Doc A", str(sample_evidence_file))
        register_evidence("C02-R01", "Doc B", str(sample_evidence_file))

        all_evidence = list_evidence()
        assert len(all_evidence) == 2

    def test_list_evidence_filtered(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import list_evidence, register_evidence

        register_evidence("C01-R01", "Doc A", str(sample_evidence_file))
        register_evidence("C02-R01", "Doc B", str(sample_evidence_file))

        filtered = list_evidence("C01-R01")
        assert len(filtered) == 1
        assert filtered[0].requirement_id == "C01-R01"

    def test_list_evidence_empty(self) -> None:
        from faultray.governance.evidence_manager import list_evidence

        assert list_evidence() == []

    def test_coverage_summary(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import get_coverage_summary, register_evidence

        register_evidence("C01-R01", "Doc", str(sample_evidence_file))
        register_evidence("C01-R02", "Doc", str(sample_evidence_file))

        summary = get_coverage_summary()
        assert summary["total_requirements"] == 28
        assert summary["covered"] == 2
        assert summary["coverage_rate"] == pytest.approx(2 / 28, rel=1e-2)
        assert "C01-R03" in summary["uncovered_ids"]

    def test_coverage_summary_empty(self) -> None:
        from faultray.governance.evidence_manager import get_coverage_summary

        summary = get_coverage_summary()
        assert summary["covered"] == 0
        assert summary["coverage_rate"] == 0.0

    def test_verify_chain_empty(self) -> None:
        from faultray.governance.evidence_manager import verify_chain

        assert verify_chain() is True

    def test_verify_chain_valid(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import register_evidence, verify_chain

        register_evidence("C01-R01", "Doc A", str(sample_evidence_file))
        register_evidence("C02-R01", "Doc B", str(sample_evidence_file))

        assert verify_chain() is True

    def test_verify_chain_tampered(self, sample_evidence_file: Path, tmp_path: Path) -> None:
        from faultray.governance.evidence_manager import register_evidence, verify_chain

        register_evidence("C01-R01", "Doc", str(sample_evidence_file))

        # Tamper with the audit chain
        import faultray.governance.evidence_manager as ev_mod

        chain_file = ev_mod._AUDIT_FILE
        chain = json.loads(chain_file.read_text(encoding="utf-8"))
        chain[0]["hash"] = "tampered_hash"
        chain_file.write_text(json.dumps(chain), encoding="utf-8")

        assert verify_chain() is False

    def test_audit_events_recorded(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import get_audit_events, register_evidence

        register_evidence("C01-R01", "Doc", str(sample_evidence_file))
        events = get_audit_events()
        assert len(events) == 1
        assert events[0].event_type == "evidence_added"
        assert "C01-R01" in events[0].description


# ===========================================================================
# Policy Generator Tests (8 tests)
# ===========================================================================


class TestPolicyGenerator:
    """Tests for policy_generator module."""

    def test_list_policy_types(self) -> None:
        from faultray.governance.policy_generator import list_policy_types

        types = list_policy_types()
        assert len(types) == 5
        names = {t["type"] for t in types}
        assert names == {"ai_usage", "risk_management", "ethics", "data_management", "incident_response"}

    def test_generate_single_policy(self) -> None:
        from faultray.governance.policy_generator import generate_policy

        doc = generate_policy("ai_usage", "テスト株式会社")
        assert doc.policy_type == "ai_usage"
        assert doc.title == "AI利用ポリシー"
        assert "テスト株式会社" in doc.content
        assert doc.org_name == "テスト株式会社"
        assert doc.id.startswith("POL-")

    def test_generate_policy_has_sections(self) -> None:
        from faultray.governance.policy_generator import generate_policy

        doc = generate_policy("risk_management", "Test Corp")
        assert "## 目的" in doc.content
        assert "## 基本方針" in doc.content
        assert "## 具体的措置" in doc.content
        assert "## 責任体制" in doc.content
        assert "## 見直し・改善" in doc.content

    def test_generate_all_policies(self) -> None:
        from faultray.governance.policy_generator import generate_all_policies

        docs = generate_all_policies("テスト株式会社")
        assert len(docs) == 5
        types = {d.policy_type for d in docs}
        assert types == {"ai_usage", "risk_management", "ethics", "data_management", "incident_response"}

    def test_generate_invalid_type(self) -> None:
        from faultray.governance.policy_generator import generate_policy

        with pytest.raises(ValueError, match="Unknown policy type"):
            generate_policy("nonexistent", "Test")

    def test_policy_content_markdown(self) -> None:
        from faultray.governance.policy_generator import generate_policy

        doc = generate_policy("ethics", "倫理テスト株式会社")
        assert doc.content.startswith("# AI倫理方針")
        assert "倫理テスト株式会社" in doc.content

    def test_policy_incident_response(self) -> None:
        from faultray.governance.policy_generator import generate_policy

        doc = generate_policy("incident_response", "Test Corp")
        assert "インシデント" in doc.content
        assert "対応フロー" in doc.content

    def test_policy_data_management(self) -> None:
        from faultray.governance.policy_generator import generate_policy

        doc = generate_policy("data_management", "Data Corp")
        assert "データ" in doc.content
        assert "プライバシー" in doc.content


# ===========================================================================
# Gap Analyzer Tests (10 tests)
# ===========================================================================


class TestGapAnalyzer:
    """Tests for gap_analyzer module."""

    def _make_assessment(self, score: int = 0) -> "AssessmentResult":
        """Create a test assessment with uniform scores."""
        from faultray.governance.assessor import GovernanceAssessor

        assessor = GovernanceAssessor()
        answers = {f"Q{i:02d}": score for i in range(1, 26)}
        return assessor.assess(answers)

    def test_analyze_gaps_all_zero(self) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps

        result = self._make_assessment(0)
        report = analyze_gaps(result)

        assert report.total_requirements == 28
        assert report.non_compliant > 0
        assert report.compliant == 0

    def test_analyze_gaps_all_max(self) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps

        result = self._make_assessment(4)
        report = analyze_gaps(result)

        assert report.total_requirements == 28
        assert report.compliant == 28
        assert report.non_compliant == 0

    def test_analyze_gaps_partial(self) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps

        result = self._make_assessment(2)
        report = analyze_gaps(result)

        # score=2 -> 50% -> partial
        assert report.partial > 0

    def test_gap_report_has_roadmap(self) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps

        result = self._make_assessment(0)
        report = analyze_gaps(result)

        rm = report.roadmap
        total_items = len(rm.phase1) + len(rm.phase2) + len(rm.phase3)
        assert total_items > 0

    def test_roadmap_phase1_is_safety_security(self) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps

        result = self._make_assessment(0)
        report = analyze_gaps(result)

        phase1_cats = {item.req_id[:3] for item in report.roadmap.phase1}
        # Phase 1 should contain C02, C04, C05
        assert phase1_cats & {"C02", "C04", "C05"}

    def test_multi_framework_violations(self) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps

        result = self._make_assessment(0)
        report = analyze_gaps(result)

        mf = report.multi_framework_impact
        assert "violations" in mf
        assert "summary" in mf
        assert mf["summary"]["total_meti_gaps"] > 0
        assert mf["summary"]["iso_requirements_impacted"] > 0

    def test_multi_framework_violations_compliant(self) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps

        result = self._make_assessment(4)
        report = analyze_gaps(result)

        mf = report.multi_framework_impact
        assert mf["summary"]["total_meti_gaps"] == 0

    def test_generate_roadmap_directly(self) -> None:
        from faultray.governance.gap_analyzer import RequirementGap, generate_roadmap

        gaps = [
            RequirementGap(req_id="C02-R01", category_id="C02", title="Test", status="non_compliant"),
            RequirementGap(req_id="C08-R01", category_id="C08", title="Test2", status="partial"),
        ]
        rm = generate_roadmap(gaps)
        assert len(rm.phase1) == 1  # C02 non-compliant -> phase1
        assert len(rm.phase3) == 1  # C08 partial -> phase3

    def test_gap_report_has_assessment_id(self) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps

        result = self._make_assessment(0)
        report = analyze_gaps(result)
        assert report.assessment_id.startswith("GAP-")

    def test_fallback_recommendations(self) -> None:
        from faultray.governance.gap_analyzer import _fallback_recommendations, analyze_gaps

        result = self._make_assessment(0)
        report = analyze_gaps(result)

        recs = _fallback_recommendations(report)
        assert "改善提案" in recs
        assert "Phase 1" in recs


# ===========================================================================
# Integration: Cross-module (2 tests)
# ===========================================================================


class TestIntegration:
    """Cross-module integration tests."""

    def test_evidence_then_coverage(self, sample_evidence_file: Path) -> None:
        """Register evidence for some requirements, check coverage improved."""
        from faultray.governance.evidence_manager import get_coverage_summary, register_evidence

        # Register for 5 different requirements
        for i, req in enumerate(["C01-R01", "C02-R01", "C03-R01", "C04-R01", "C05-R01"]):
            register_evidence(req, f"Evidence {i}", str(sample_evidence_file))

        summary = get_coverage_summary()
        assert summary["covered"] == 5
        assert summary["coverage_rate"] == pytest.approx(5 / 28, rel=1e-2)

    def test_registry_and_shadow_detection(self) -> None:
        """Register some systems, detect shadow AI for unregistered ones."""
        from faultray.governance.ai_registry import AISystem, detect_shadow_ai, get_risk_summary, register_ai_system

        register_ai_system(AISystem(name="ChatBot", org_id="org1", ai_type="generative"))
        register_ai_system(AISystem(name="Risk Model", org_id="org1", ai_type="predictive", risk_level="high"))

        shadows = detect_shadow_ai("org1", ["ChatBot", "Risk Model", "Unknown Tool"])
        assert len(shadows) == 1

        summary = get_risk_summary("org1")
        assert summary["total_systems"] == 2
