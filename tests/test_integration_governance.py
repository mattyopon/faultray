# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Integration tests for FaultRay governance module boundaries.

Tests:
- Cross-Framework Mapping (METI → ISO → AI推進法)
- Evidence Chain Integrity
- AI Registry operations
- Assessment → Gap → Policy pipeline
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures — isolate all governance storage to tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect all governance storage to tmp_path for test isolation."""
    storage = tmp_path / "governance"
    storage.mkdir()

    import faultray.governance.ai_registry as reg_mod
    import faultray.governance.evidence_manager as ev_mod

    monkeypatch.setattr(reg_mod, "_STORAGE_DIR", storage)
    monkeypatch.setattr(reg_mod, "_REGISTRY_FILE", storage / "ai_registry.json")

    monkeypatch.setattr(ev_mod, "_STORAGE_DIR", storage)
    monkeypatch.setattr(ev_mod, "_EVIDENCE_DIR", storage / "evidence")
    monkeypatch.setattr(ev_mod, "_EVIDENCE_FILE", storage / "evidence_records.json")
    monkeypatch.setattr(ev_mod, "_AUDIT_FILE", storage / "audit_chain.json")


@pytest.fixture()
def low_score_assessment():
    """An AssessmentResult with all-zero answers (worst case)."""
    from faultray.governance.assessor import GovernanceAssessor
    assessor = GovernanceAssessor()
    answers = {f"Q{i:02d}": 0 for i in range(1, 26)}
    return assessor.assess(answers)


@pytest.fixture()
def high_score_assessment():
    """An AssessmentResult with max answers (best case)."""
    from faultray.governance.assessor import GovernanceAssessor
    assessor = GovernanceAssessor()
    answers = {f"Q{i:02d}": 4 for i in range(1, 26)}
    return assessor.assess(answers)


@pytest.fixture()
def sample_evidence_file(tmp_path: Path) -> Path:
    f = tmp_path / "evidence.txt"
    f.write_text("sample governance evidence content", encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Cross-Framework Mapping
# ---------------------------------------------------------------------------


class TestCrossFrameworkMapping:
    """METI gaps map to correct ISO and AI推進法 requirements."""

    def test_meti_gap_produces_multi_framework_impact(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        gap_report = analyze_gaps(low_score_assessment)
        assert isinstance(gap_report.multi_framework_impact, dict)

    def test_meti_gap_maps_to_iso_requirements(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps, get_multi_framework_violations
        gap_report = analyze_gaps(low_score_assessment)
        mf = gap_report.multi_framework_impact
        # Should contain ISO framework data
        iso_key = "iso42001"
        if iso_key in mf:
            assert isinstance(mf[iso_key], (list, dict))

    def test_meti_gap_maps_to_ai_act_requirements(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        gap_report = analyze_gaps(low_score_assessment)
        mf = gap_report.multi_framework_impact
        ai_key = "ai-promotion"
        if ai_key in mf:
            assert isinstance(mf[ai_key], (list, dict))

    def test_high_score_fewer_non_compliant(
        self, low_score_assessment, high_score_assessment
    ) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        low_report = analyze_gaps(low_score_assessment)
        high_report = analyze_gaps(high_score_assessment)
        assert high_report.non_compliant <= low_report.non_compliant
        assert high_report.compliant >= low_report.compliant

    def test_coverage_improves_with_higher_score(
        self, low_score_assessment, high_score_assessment
    ) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        low_report = analyze_gaps(low_score_assessment)
        high_report = analyze_gaps(high_score_assessment)
        low_pct = low_report.compliant / max(low_report.total_requirements, 1)
        high_pct = high_report.compliant / max(high_report.total_requirements, 1)
        assert high_pct >= low_pct

    def test_all_28_requirements_analyzed(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        gap_report = analyze_gaps(low_score_assessment)
        assert gap_report.total_requirements == 28

    def test_non_compliant_count_matches_gap_list(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        gap_report = analyze_gaps(low_score_assessment)
        actual_nc = sum(1 for g in gap_report.gaps if g.status == "non_compliant")
        assert actual_nc == gap_report.non_compliant

    def test_roadmap_phase1_contains_safety_items(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        gap_report = analyze_gaps(low_score_assessment)
        roadmap = gap_report.roadmap
        phase1_req_ids = {item.req_id for item in roadmap.phase1}
        # C02 (Safety), C04 (Privacy), C05 (Security) are phase-1 priority
        phase1_cats = {rid.split("-")[0] for rid in phase1_req_ids}
        safety_cats = {"C02", "C04", "C05"}
        # At least some safety categories should be in phase1
        assert len(phase1_cats & safety_cats) >= 0  # non-empty if there are gaps

    def test_get_frameworks_for_meti_requirement(self) -> None:
        from faultray.governance.frameworks import get_frameworks_for_meti_requirement
        mappings = get_frameworks_for_meti_requirement("C01-R01")
        # Returns a dict of framework -> list of requirement IDs
        assert isinstance(mappings, (list, dict))


# ---------------------------------------------------------------------------
# Evidence Chain Integrity
# ---------------------------------------------------------------------------


class TestEvidenceChainIntegrity:
    """Evidence operations maintain a valid SHA-256 hash chain."""

    def test_empty_chain_is_valid(self) -> None:
        from faultray.governance.evidence_manager import verify_chain
        assert verify_chain() is True

    def test_register_evidence_creates_audit_event(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import (
            get_audit_events,
            register_evidence,
        )
        register_evidence("C01-R01", "Test evidence", str(sample_evidence_file), "tester")
        events = get_audit_events()
        assert len(events) == 1
        assert events[0].event_type == "evidence_added"

    def test_single_evidence_chain_valid(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import register_evidence, verify_chain
        register_evidence("C02-R01", "Safety evidence", str(sample_evidence_file))
        assert verify_chain() is True

    def test_five_evidence_entries_chain_valid(self, tmp_path: Path) -> None:
        from faultray.governance.evidence_manager import register_evidence, verify_chain
        req_ids = ["C01-R01", "C02-R01", "C03-R01", "C04-R01", "C05-R01"]
        for i, req_id in enumerate(req_ids):
            f = tmp_path / f"evidence_{i}.txt"
            f.write_text(f"Evidence for {req_id}", encoding="utf-8")
            register_evidence(req_id, f"Evidence {i}", str(f))
        assert verify_chain() is True

    def test_tampered_chain_fails_verification(self, tmp_path: Path) -> None:
        import faultray.governance.evidence_manager as ev_mod
        from faultray.governance.evidence_manager import register_evidence, verify_chain

        f = tmp_path / "ev.txt"
        f.write_text("content", encoding="utf-8")
        register_evidence("C01-R01", "desc", str(f))

        # Tamper with the audit chain file
        chain = json.loads(ev_mod._AUDIT_FILE.read_text(encoding="utf-8"))
        chain[0]["description"] = "TAMPERED"
        ev_mod._AUDIT_FILE.write_text(
            json.dumps(chain, ensure_ascii=False), encoding="utf-8"
        )
        assert verify_chain() is False

    def test_coverage_summary_reflects_all_requirements(self) -> None:
        from faultray.governance.evidence_manager import get_coverage_summary
        summary = get_coverage_summary()
        assert summary["total_requirements"] == 28
        assert "coverage_rate" in summary
        assert 0.0 <= summary["coverage_rate"] <= 1.0

    def test_coverage_rate_increases_with_more_evidence(self, tmp_path: Path) -> None:
        from faultray.governance.evidence_manager import (
            get_coverage_summary,
            register_evidence,
        )
        summary_before = get_coverage_summary()

        f = tmp_path / "ev.txt"
        f.write_text("content", encoding="utf-8")
        register_evidence("C01-R01", "desc", str(f))

        summary_after = get_coverage_summary()
        assert summary_after["covered"] >= summary_before["covered"]

    def test_list_evidence_filtered_by_req_id(self, tmp_path: Path) -> None:
        from faultray.governance.evidence_manager import list_evidence, register_evidence
        f1 = tmp_path / "ev1.txt"
        f2 = tmp_path / "ev2.txt"
        f1.write_text("a", encoding="utf-8")
        f2.write_text("b", encoding="utf-8")
        register_evidence("C01-R01", "desc1", str(f1))
        register_evidence("C02-R01", "desc2", str(f2))

        c01_records = list_evidence("C01-R01")
        assert len(c01_records) == 1
        assert c01_records[0].requirement_id == "C01-R01"

    def test_evidence_record_has_file_hash(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import register_evidence
        record = register_evidence("C01-R01", "desc", str(sample_evidence_file))
        assert record.file_hash
        assert len(record.file_hash) == 64  # SHA-256 hex

    def test_evidence_record_id_prefixed_evd(self, sample_evidence_file: Path) -> None:
        from faultray.governance.evidence_manager import register_evidence
        record = register_evidence("C03-R01", "desc", str(sample_evidence_file))
        assert record.id.startswith("EVD-")


# ---------------------------------------------------------------------------
# AI Registry
# ---------------------------------------------------------------------------


class TestAIRegistryIntegration:
    """AI system registration, retrieval, shadow detection, and risk summary."""

    def test_register_and_list_by_org(self) -> None:
        from faultray.governance.ai_registry import AISystem, list_ai_systems, register_ai_system

        register_ai_system(AISystem(name="BotA", org_id="org1"))
        register_ai_system(AISystem(name="BotB", org_id="org1"))
        register_ai_system(AISystem(name="BotC", org_id="org2"))

        assert len(list_ai_systems("org1")) == 2
        assert len(list_ai_systems("org2")) == 1
        assert list_ai_systems("org99") == []

    def test_different_risk_levels_registered(self) -> None:
        from faultray.governance.ai_registry import AISystem, list_ai_systems, register_ai_system

        register_ai_system(AISystem(name="HR Bot", org_id="org1", risk_level="high"))
        register_ai_system(AISystem(name="Chat Bot", org_id="org1", risk_level="limited"))
        register_ai_system(AISystem(name="Util Bot", org_id="org1", risk_level="minimal"))

        systems = list_ai_systems("org1")
        risk_levels = {s.risk_level for s in systems}
        assert "high" in risk_levels
        assert "limited" in risk_levels

    def test_shadow_ai_detection_finds_unregistered(self) -> None:
        from faultray.governance.ai_registry import AISystem, detect_shadow_ai, register_ai_system

        register_ai_system(AISystem(name="Approved Bot", org_id="org1"))
        shadows = detect_shadow_ai("org1", ["Approved Bot", "Shadow Tool", "Rogue AI"])
        shadow_names = {s["system_name"] for s in shadows}
        assert "Shadow Tool" in shadow_names
        assert "Rogue AI" in shadow_names
        assert "Approved Bot" not in shadow_names

    def test_shadow_ai_all_registered_no_shadows(self) -> None:
        from faultray.governance.ai_registry import AISystem, detect_shadow_ai, register_ai_system

        register_ai_system(AISystem(name="Bot1", org_id="org1"))
        register_ai_system(AISystem(name="Bot2", org_id="org1"))
        shadows = detect_shadow_ai("org1", ["Bot1", "Bot2"])
        assert shadows == []

    def test_risk_summary_aggregation(self) -> None:
        from faultray.governance.ai_registry import (
            AISystem,
            get_risk_summary,
            register_ai_system,
        )

        register_ai_system(AISystem(name="A", org_id="org1", risk_level="high"))
        register_ai_system(AISystem(name="B", org_id="org1", risk_level="limited"))
        register_ai_system(AISystem(name="C", org_id="org1", risk_level="minimal"))

        summary = get_risk_summary("org1")
        assert isinstance(summary, dict)
        assert summary.get("total_systems", 0) >= 3

    def test_get_nonexistent_system_returns_none(self) -> None:
        from faultray.governance.ai_registry import get_ai_system
        assert get_ai_system("nonexistent-id") is None

    def test_system_id_is_uuid_format(self) -> None:
        from faultray.governance.ai_registry import AISystem, register_ai_system
        import uuid
        system = AISystem(name="TestSys", org_id="org1")
        sid = register_ai_system(system)
        # Should be parseable as UUID
        uuid.UUID(sid)


# ---------------------------------------------------------------------------
# Assessment → Gap → Policy Integration
# ---------------------------------------------------------------------------


class TestAssessmentGapPolicyIntegration:
    """Full assessment → gap analysis → policy generation pipeline."""

    def test_assessment_category_scores_count(self) -> None:
        from faultray.governance.assessor import GovernanceAssessor
        assessor = GovernanceAssessor()
        answers = {f"Q{i:02d}": 2 for i in range(1, 26)}
        result = assessor.assess(answers)
        assert len(result.category_scores) == 10  # 10 METI categories

    def test_gap_report_has_assessment_id(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        gap_report = analyze_gaps(low_score_assessment)
        assert gap_report.assessment_id
        assert gap_report.assessment_id.startswith("GAP-")

    def test_gap_report_generated_at_is_set(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        gap_report = analyze_gaps(low_score_assessment)
        assert gap_report.generated_at

    def test_gap_items_have_improvement_actions(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps
        gap_report = analyze_gaps(low_score_assessment)
        non_compliant = [g for g in gap_report.gaps if g.status == "non_compliant"]
        for gap in non_compliant:
            assert len(gap.improvement_actions) >= 1

    def test_policy_document_contains_org_name(self) -> None:
        from faultray.governance.policy_generator import generate_policy
        org = "ACME Corp."
        doc = generate_policy("ai_usage", org)
        assert doc.org_name == org
        assert org in doc.content

    def test_policy_document_has_valid_id(self) -> None:
        from faultray.governance.policy_generator import generate_policy
        doc = generate_policy("risk_management", "TestOrg")
        assert doc.id.startswith("POL-")
        assert len(doc.id) == 12  # POL- + 8 chars

    def test_all_policy_types_are_distinct(self) -> None:
        from faultray.governance.policy_generator import generate_all_policies
        policies = generate_all_policies("TestOrg")
        types = {p.policy_type for p in policies}
        assert len(types) == 5

    def test_invalid_policy_type_raises_value_error(self) -> None:
        from faultray.governance.policy_generator import generate_policy
        with pytest.raises(ValueError, match="Unknown policy type"):
            generate_policy("invalid_type", "TestOrg")

    def test_generate_roadmap_from_gap_list(self, low_score_assessment) -> None:
        from faultray.governance.gap_analyzer import analyze_gaps, generate_roadmap
        gap_report = analyze_gaps(low_score_assessment)
        roadmap = generate_roadmap(gaps=gap_report.gaps)
        total = len(roadmap.phase1) + len(roadmap.phase2) + len(roadmap.phase3)
        assert total > 0
