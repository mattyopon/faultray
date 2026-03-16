"""Tests for the Incident Learning Engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.simulator.incident_learning import (
    ChaosScenarioTemplate,
    IncidentCategory,
    IncidentLearningEngine,
    IncidentLearningReport,
    IncidentRecord,
    IncidentSeverity,
    LearningInsight,
    _CATEGORY_FAILURE_STEPS,
    _SEVERITY_WEIGHT,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _ts(year: int = 2025, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _make_incident(
    incident_id: str = "INC-001",
    title: str = "Test incident",
    severity: IncidentSeverity = IncidentSeverity.SEV2,
    category: IncidentCategory = IncidentCategory.CASCADE_FAILURE,
    root_cause_component: str = "api-gateway",
    affected_components: list[str] | None = None,
    duration_minutes: float = 60.0,
    detection_time_minutes: float = 10.0,
    mitigation_steps: list[str] | None = None,
    timestamp: datetime | None = None,
    lessons_learned: list[str] | None = None,
) -> IncidentRecord:
    return IncidentRecord(
        incident_id=incident_id,
        title=title,
        severity=severity,
        category=category,
        root_cause_component=root_cause_component,
        affected_components=affected_components or ["service-a"],
        duration_minutes=duration_minutes,
        detection_time_minutes=detection_time_minutes,
        mitigation_steps=mitigation_steps or ["restart pods"],
        timestamp=timestamp or _ts(),
        lessons_learned=lessons_learned or ["add monitoring"],
    )


@pytest.fixture
def engine() -> IncidentLearningEngine:
    return IncidentLearningEngine()


@pytest.fixture
def populated_engine() -> IncidentLearningEngine:
    eng = IncidentLearningEngine()
    eng.add_incident(_make_incident("INC-001", category=IncidentCategory.CASCADE_FAILURE))
    eng.add_incident(_make_incident("INC-002", category=IncidentCategory.CASCADE_FAILURE, severity=IncidentSeverity.SEV1))
    eng.add_incident(_make_incident("INC-003", category=IncidentCategory.CAPACITY_EXHAUSTION, root_cause_component="db-primary"))
    return eng


# ===================================================================
# IncidentSeverity enum
# ===================================================================

class TestIncidentSeverity:
    def test_sev1_value(self):
        assert IncidentSeverity.SEV1 == "SEV1"

    def test_sev2_value(self):
        assert IncidentSeverity.SEV2 == "SEV2"

    def test_sev3_value(self):
        assert IncidentSeverity.SEV3 == "SEV3"

    def test_sev4_value(self):
        assert IncidentSeverity.SEV4 == "SEV4"

    def test_all_members_count(self):
        assert len(IncidentSeverity) == 4

    def test_from_string(self):
        assert IncidentSeverity("SEV1") is IncidentSeverity.SEV1


# ===================================================================
# IncidentCategory enum
# ===================================================================

class TestIncidentCategory:
    def test_cascade_failure(self):
        assert IncidentCategory.CASCADE_FAILURE == "CASCADE_FAILURE"

    def test_capacity_exhaustion(self):
        assert IncidentCategory.CAPACITY_EXHAUSTION == "CAPACITY_EXHAUSTION"

    def test_dependency_failure(self):
        assert IncidentCategory.DEPENDENCY_FAILURE == "DEPENDENCY_FAILURE"

    def test_config_error(self):
        assert IncidentCategory.CONFIG_ERROR == "CONFIG_ERROR"

    def test_deployment_failure(self):
        assert IncidentCategory.DEPLOYMENT_FAILURE == "DEPLOYMENT_FAILURE"

    def test_security_breach(self):
        assert IncidentCategory.SECURITY_BREACH == "SECURITY_BREACH"

    def test_data_corruption(self):
        assert IncidentCategory.DATA_CORRUPTION == "DATA_CORRUPTION"

    def test_network_partition(self):
        assert IncidentCategory.NETWORK_PARTITION == "NETWORK_PARTITION"

    def test_all_members_count(self):
        assert len(IncidentCategory) == 8

    def test_all_categories_have_failure_steps(self):
        for cat in IncidentCategory:
            assert cat in _CATEGORY_FAILURE_STEPS


# ===================================================================
# IncidentRecord model
# ===================================================================

class TestIncidentRecord:
    def test_basic_creation(self):
        rec = _make_incident()
        assert rec.incident_id == "INC-001"
        assert rec.title == "Test incident"

    def test_severity_field(self):
        rec = _make_incident(severity=IncidentSeverity.SEV1)
        assert rec.severity is IncidentSeverity.SEV1

    def test_category_field(self):
        rec = _make_incident(category=IncidentCategory.CONFIG_ERROR)
        assert rec.category is IncidentCategory.CONFIG_ERROR

    def test_root_cause_component(self):
        rec = _make_incident(root_cause_component="redis-cluster")
        assert rec.root_cause_component == "redis-cluster"

    def test_affected_components_default(self):
        rec = IncidentRecord(
            incident_id="x", title="t", severity=IncidentSeverity.SEV4,
            category=IncidentCategory.CONFIG_ERROR, root_cause_component="c",
        )
        assert rec.affected_components == []

    def test_affected_components_list(self):
        rec = _make_incident(affected_components=["a", "b", "c"])
        assert rec.affected_components == ["a", "b", "c"]

    def test_duration_minutes(self):
        rec = _make_incident(duration_minutes=120.5)
        assert rec.duration_minutes == 120.5

    def test_detection_time_minutes(self):
        rec = _make_incident(detection_time_minutes=5.0)
        assert rec.detection_time_minutes == 5.0

    def test_mitigation_steps(self):
        rec = _make_incident(mitigation_steps=["step1", "step2"])
        assert rec.mitigation_steps == ["step1", "step2"]

    def test_timestamp_default_is_utc(self):
        rec = IncidentRecord(
            incident_id="x", title="t", severity=IncidentSeverity.SEV4,
            category=IncidentCategory.CONFIG_ERROR, root_cause_component="c",
        )
        assert rec.timestamp.tzinfo is not None

    def test_timestamp_explicit(self):
        ts = _ts(2024, 6, 15)
        rec = _make_incident(timestamp=ts)
        assert rec.timestamp == ts

    def test_lessons_learned(self):
        rec = _make_incident(lessons_learned=["lesson1", "lesson2"])
        assert rec.lessons_learned == ["lesson1", "lesson2"]

    def test_lessons_learned_default(self):
        rec = IncidentRecord(
            incident_id="x", title="t", severity=IncidentSeverity.SEV4,
            category=IncidentCategory.CONFIG_ERROR, root_cause_component="c",
        )
        assert rec.lessons_learned == []


# ===================================================================
# ChaosScenarioTemplate model
# ===================================================================

class TestChaosScenarioTemplate:
    def test_basic_creation(self):
        t = ChaosScenarioTemplate(
            scenario_id="s1", name="n", description="d", source_incident_id="i1",
        )
        assert t.scenario_id == "s1"
        assert t.source_incident_id == "i1"

    def test_default_lists(self):
        t = ChaosScenarioTemplate(
            scenario_id="s1", name="n", description="d", source_incident_id="i1",
        )
        assert t.target_components == []
        assert t.failure_sequence == []
        assert t.validation_criteria == []

    def test_default_times(self):
        t = ChaosScenarioTemplate(
            scenario_id="s1", name="n", description="d", source_incident_id="i1",
        )
        assert t.expected_detection_time_minutes == 0.0
        assert t.expected_recovery_time_minutes == 0.0

    def test_with_all_fields(self):
        t = ChaosScenarioTemplate(
            scenario_id="s1", name="n", description="d", source_incident_id="i1",
            target_components=["a", "b"],
            failure_sequence=[{"action": "kill"}],
            expected_detection_time_minutes=5.0,
            expected_recovery_time_minutes=10.0,
            validation_criteria=["detect fast"],
        )
        assert len(t.target_components) == 2
        assert len(t.failure_sequence) == 1
        assert t.expected_detection_time_minutes == 5.0


# ===================================================================
# LearningInsight model
# ===================================================================

class TestLearningInsight:
    def test_basic(self):
        li = LearningInsight(pattern="test")
        assert li.pattern == "test"
        assert li.frequency == 0
        assert li.risk_score == 0.0

    def test_full(self):
        li = LearningInsight(
            pattern="p", frequency=3,
            affected_categories=[IncidentCategory.CASCADE_FAILURE],
            risk_score=0.8, recommendation="fix it",
        )
        assert li.frequency == 3
        assert li.risk_score == 0.8
        assert li.recommendation == "fix it"


# ===================================================================
# IncidentLearningReport model
# ===================================================================

class TestIncidentLearningReport:
    def test_defaults(self):
        r = IncidentLearningReport()
        assert r.total_incidents == 0
        assert r.scenarios_generated == 0
        assert r.templates == []
        assert r.insights == []
        assert r.repeat_risk_score == 0.0
        assert r.coverage_by_category == {}

    def test_with_values(self):
        r = IncidentLearningReport(
            total_incidents=5, scenarios_generated=5,
            repeat_risk_score=0.6,
            coverage_by_category={"CASCADE_FAILURE": 1.0},
        )
        assert r.total_incidents == 5
        assert r.coverage_by_category["CASCADE_FAILURE"] == 1.0


# ===================================================================
# Severity weight constants
# ===================================================================

class TestSeverityWeight:
    def test_sev1_weight(self):
        assert _SEVERITY_WEIGHT[IncidentSeverity.SEV1] == 1.0

    def test_sev2_weight(self):
        assert _SEVERITY_WEIGHT[IncidentSeverity.SEV2] == 0.7

    def test_sev3_weight(self):
        assert _SEVERITY_WEIGHT[IncidentSeverity.SEV3] == 0.4

    def test_sev4_weight(self):
        assert _SEVERITY_WEIGHT[IncidentSeverity.SEV4] == 0.2

    def test_all_severities_have_weight(self):
        for sev in IncidentSeverity:
            assert sev in _SEVERITY_WEIGHT


# ===================================================================
# Engine: __init__
# ===================================================================

class TestEngineInit:
    def test_empty_incidents(self, engine: IncidentLearningEngine):
        assert engine._incidents == []

    def test_empty_scenarios(self, engine: IncidentLearningEngine):
        assert engine._scenarios == []


# ===================================================================
# Engine: add_incident
# ===================================================================

class TestAddIncident:
    def test_add_one(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident())
        assert len(engine._incidents) == 1

    def test_add_multiple(self, engine: IncidentLearningEngine):
        for i in range(5):
            engine.add_incident(_make_incident(incident_id=f"INC-{i}"))
        assert len(engine._incidents) == 5

    def test_preserves_order(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A"))
        engine.add_incident(_make_incident("B"))
        assert engine._incidents[0].incident_id == "A"
        assert engine._incidents[1].incident_id == "B"

    def test_duplicate_ids_allowed(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("X"))
        engine.add_incident(_make_incident("X"))
        assert len(engine._incidents) == 2


# ===================================================================
# Engine: extract_patterns
# ===================================================================

class TestExtractPatterns:
    def test_empty_engine(self, engine: IncidentLearningEngine):
        assert engine.extract_patterns() == []

    def test_single_incident_no_category_repeat(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident())
        patterns = engine.extract_patterns()
        # No repeated categories, but may have slow detection pattern
        cat_patterns = [p for p in patterns if "Recurring" in p.pattern]
        assert len(cat_patterns) == 0

    def test_repeated_category_detected(self, populated_engine: IncidentLearningEngine):
        patterns = populated_engine.extract_patterns()
        cat_patterns = [p for p in patterns if "CASCADE_FAILURE" in p.pattern and "Recurring" in p.pattern]
        assert len(cat_patterns) == 1
        assert cat_patterns[0].frequency == 2

    def test_repeated_component_detected(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A", root_cause_component="redis"))
        engine.add_incident(_make_incident("B", root_cause_component="redis"))
        patterns = engine.extract_patterns()
        comp_patterns = [p for p in patterns if "redis" in p.pattern]
        assert len(comp_patterns) >= 1
        assert comp_patterns[0].frequency == 2

    def test_slow_detection_pattern(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A", detection_time_minutes=30.0))
        patterns = engine.extract_patterns()
        slow = [p for p in patterns if "Slow detection" in p.pattern]
        assert len(slow) == 1

    def test_no_slow_detection_if_fast(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A", detection_time_minutes=5.0))
        engine.add_incident(_make_incident("B", detection_time_minutes=10.0, category=IncidentCategory.CONFIG_ERROR))
        patterns = engine.extract_patterns()
        slow = [p for p in patterns if "Slow detection" in p.pattern]
        assert len(slow) == 0

    def test_risk_score_bounded(self, populated_engine: IncidentLearningEngine):
        patterns = populated_engine.extract_patterns()
        for p in patterns:
            assert 0.0 <= p.risk_score <= 1.0

    def test_recommendation_non_empty(self, populated_engine: IncidentLearningEngine):
        patterns = populated_engine.extract_patterns()
        for p in patterns:
            assert len(p.recommendation) > 0

    def test_affected_categories_populated(self, populated_engine: IncidentLearningEngine):
        patterns = populated_engine.extract_patterns()
        cat_patterns = [p for p in patterns if "Recurring" in p.pattern]
        for p in cat_patterns:
            assert len(p.affected_categories) >= 1

    def test_component_pattern_categories_sorted(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A", root_cause_component="x", category=IncidentCategory.NETWORK_PARTITION))
        engine.add_incident(_make_incident("B", root_cause_component="x", category=IncidentCategory.CASCADE_FAILURE))
        patterns = engine.extract_patterns()
        comp_patterns = [p for p in patterns if "'x'" in p.pattern]
        assert len(comp_patterns) == 1
        cats = comp_patterns[0].affected_categories
        assert cats == sorted(cats, key=lambda c: c.value)

    def test_many_incidents_all_patterns(self, engine: IncidentLearningEngine):
        for i in range(10):
            engine.add_incident(_make_incident(
                f"INC-{i}", root_cause_component="svc",
                category=IncidentCategory.CASCADE_FAILURE,
                detection_time_minutes=20.0,
            ))
        patterns = engine.extract_patterns()
        assert len(patterns) >= 3  # category, component, slow detection

    def test_risk_score_capped_at_one(self, engine: IncidentLearningEngine):
        for i in range(50):
            engine.add_incident(_make_incident(
                f"INC-{i}", severity=IncidentSeverity.SEV1,
                category=IncidentCategory.CASCADE_FAILURE,
            ))
        patterns = engine.extract_patterns()
        for p in patterns:
            assert p.risk_score <= 1.0


# ===================================================================
# Engine: generate_scenario
# ===================================================================

class TestGenerateScenario:
    def test_scenario_id_format(self, engine: IncidentLearningEngine):
        inc = _make_incident()
        sc = engine.generate_scenario(inc)
        assert sc.scenario_id.startswith("chaos-")
        assert len(sc.scenario_id) > 6

    def test_name_contains_title(self, engine: IncidentLearningEngine):
        inc = _make_incident(title="DB crashed")
        sc = engine.generate_scenario(inc)
        assert "DB crashed" in sc.name

    def test_description_contains_category(self, engine: IncidentLearningEngine):
        inc = _make_incident(category=IncidentCategory.NETWORK_PARTITION)
        sc = engine.generate_scenario(inc)
        assert "NETWORK_PARTITION" in sc.description

    def test_description_contains_root_cause(self, engine: IncidentLearningEngine):
        inc = _make_incident(root_cause_component="my-service")
        sc = engine.generate_scenario(inc)
        assert "my-service" in sc.description

    def test_source_incident_id(self, engine: IncidentLearningEngine):
        inc = _make_incident(incident_id="INC-42")
        sc = engine.generate_scenario(inc)
        assert sc.source_incident_id == "INC-42"

    def test_target_components_includes_root_cause(self, engine: IncidentLearningEngine):
        inc = _make_incident(root_cause_component="root", affected_components=["dep-a"])
        sc = engine.generate_scenario(inc)
        assert "root" in sc.target_components

    def test_target_components_includes_affected(self, engine: IncidentLearningEngine):
        inc = _make_incident(root_cause_component="root", affected_components=["dep-a", "dep-b"])
        sc = engine.generate_scenario(inc)
        assert "dep-a" in sc.target_components
        assert "dep-b" in sc.target_components

    def test_target_components_no_duplicates(self, engine: IncidentLearningEngine):
        inc = _make_incident(root_cause_component="svc", affected_components=["svc", "other"])
        sc = engine.generate_scenario(inc)
        assert sc.target_components.count("svc") == 1

    def test_failure_sequence_for_cascade(self, engine: IncidentLearningEngine):
        inc = _make_incident(category=IncidentCategory.CASCADE_FAILURE)
        sc = engine.generate_scenario(inc)
        assert len(sc.failure_sequence) == 2
        assert sc.failure_sequence[0]["action"] == "inject_latency"

    def test_failure_sequence_for_capacity(self, engine: IncidentLearningEngine):
        inc = _make_incident(category=IncidentCategory.CAPACITY_EXHAUSTION)
        sc = engine.generate_scenario(inc)
        assert len(sc.failure_sequence) == 1
        assert sc.failure_sequence[0]["action"] == "exhaust_resource"

    def test_failure_sequence_for_dependency(self, engine: IncidentLearningEngine):
        inc = _make_incident(category=IncidentCategory.DEPENDENCY_FAILURE)
        sc = engine.generate_scenario(inc)
        assert sc.failure_sequence[0]["action"] == "kill_dependency"

    def test_failure_sequence_for_config(self, engine: IncidentLearningEngine):
        inc = _make_incident(category=IncidentCategory.CONFIG_ERROR)
        sc = engine.generate_scenario(inc)
        assert sc.failure_sequence[0]["action"] == "inject_bad_config"

    def test_failure_sequence_for_deployment(self, engine: IncidentLearningEngine):
        inc = _make_incident(category=IncidentCategory.DEPLOYMENT_FAILURE)
        sc = engine.generate_scenario(inc)
        assert sc.failure_sequence[0]["action"] == "simulate_bad_deploy"

    def test_failure_sequence_for_security(self, engine: IncidentLearningEngine):
        inc = _make_incident(category=IncidentCategory.SECURITY_BREACH)
        sc = engine.generate_scenario(inc)
        assert sc.failure_sequence[0]["action"] == "simulate_breach_attempt"

    def test_failure_sequence_for_data_corruption(self, engine: IncidentLearningEngine):
        inc = _make_incident(category=IncidentCategory.DATA_CORRUPTION)
        sc = engine.generate_scenario(inc)
        assert sc.failure_sequence[0]["action"] == "corrupt_data_store"

    def test_failure_sequence_for_network_partition(self, engine: IncidentLearningEngine):
        inc = _make_incident(category=IncidentCategory.NETWORK_PARTITION)
        sc = engine.generate_scenario(inc)
        assert sc.failure_sequence[0]["action"] == "partition_network"

    def test_failure_sequence_target_substituted(self, engine: IncidentLearningEngine):
        inc = _make_incident(root_cause_component="my-db", category=IncidentCategory.CASCADE_FAILURE)
        sc = engine.generate_scenario(inc)
        assert sc.failure_sequence[0]["target"] == "my-db"

    def test_expected_detection_time(self, engine: IncidentLearningEngine):
        inc = _make_incident(detection_time_minutes=20.0)
        sc = engine.generate_scenario(inc)
        assert sc.expected_detection_time_minutes == 10.0

    def test_expected_recovery_time(self, engine: IncidentLearningEngine):
        inc = _make_incident(duration_minutes=100.0)
        sc = engine.generate_scenario(inc)
        assert sc.expected_recovery_time_minutes == 50.0

    def test_detection_time_min_clamp(self, engine: IncidentLearningEngine):
        inc = _make_incident(detection_time_minutes=0.0)
        sc = engine.generate_scenario(inc)
        assert sc.expected_detection_time_minutes == 1.0

    def test_recovery_time_min_clamp(self, engine: IncidentLearningEngine):
        inc = _make_incident(duration_minutes=0.0)
        sc = engine.generate_scenario(inc)
        assert sc.expected_recovery_time_minutes == 1.0

    def test_validation_criteria_contains_detection(self, engine: IncidentLearningEngine):
        inc = _make_incident()
        sc = engine.generate_scenario(inc)
        assert any("Detection" in c for c in sc.validation_criteria)

    def test_validation_criteria_contains_recovery(self, engine: IncidentLearningEngine):
        inc = _make_incident()
        sc = engine.generate_scenario(inc)
        assert any("Recovery" in c for c in sc.validation_criteria)

    def test_validation_criteria_contains_mitigation(self, engine: IncidentLearningEngine):
        inc = _make_incident(mitigation_steps=["rollback deployment"])
        sc = engine.generate_scenario(inc)
        assert any("rollback deployment" in c for c in sc.validation_criteria)

    def test_deterministic_scenario_id(self, engine: IncidentLearningEngine):
        inc = _make_incident(incident_id="INC-99")
        s1 = engine.generate_scenario(inc)
        s2 = engine.generate_scenario(inc)
        assert s1.scenario_id == s2.scenario_id

    def test_different_ids_produce_different_scenario_ids(self, engine: IncidentLearningEngine):
        s1 = engine.generate_scenario(_make_incident(incident_id="A"))
        s2 = engine.generate_scenario(_make_incident(incident_id="B"))
        assert s1.scenario_id != s2.scenario_id

    def test_multiple_mitigation_steps_in_criteria(self, engine: IncidentLearningEngine):
        inc = _make_incident(mitigation_steps=["step1", "step2", "step3"])
        sc = engine.generate_scenario(inc)
        mitigation_criteria = [c for c in sc.validation_criteria if "Mitigation" in c]
        assert len(mitigation_criteria) == 3

    def test_empty_affected_components(self, engine: IncidentLearningEngine):
        inc = IncidentRecord(
            incident_id="X", title="t", severity=IncidentSeverity.SEV3,
            category=IncidentCategory.CONFIG_ERROR,
            root_cause_component="svc", affected_components=[],
        )
        sc = engine.generate_scenario(inc)
        assert sc.target_components == ["svc"]

    def test_empty_mitigation_steps(self, engine: IncidentLearningEngine):
        inc = IncidentRecord(
            incident_id="X", title="t", severity=IncidentSeverity.SEV3,
            category=IncidentCategory.CONFIG_ERROR,
            root_cause_component="svc", mitigation_steps=[],
        )
        sc = engine.generate_scenario(inc)
        # Only detection + recovery criteria
        assert len(sc.validation_criteria) == 2


# ===================================================================
# Engine: generate_all_scenarios
# ===================================================================

class TestGenerateAllScenarios:
    def test_empty_engine(self, engine: IncidentLearningEngine):
        result = engine.generate_all_scenarios()
        assert result == []

    def test_generates_one_per_incident(self, populated_engine: IncidentLearningEngine):
        result = populated_engine.generate_all_scenarios()
        assert len(result) == 3

    def test_stores_internally(self, populated_engine: IncidentLearningEngine):
        populated_engine.generate_all_scenarios()
        assert len(populated_engine._scenarios) == 3

    def test_replaces_previous(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A"))
        engine.generate_all_scenarios()
        assert len(engine._scenarios) == 1
        engine.add_incident(_make_incident("B"))
        engine.generate_all_scenarios()
        assert len(engine._scenarios) == 2

    def test_each_scenario_unique_id(self, populated_engine: IncidentLearningEngine):
        result = populated_engine.generate_all_scenarios()
        ids = [s.scenario_id for s in result]
        assert len(ids) == len(set(ids))

    def test_source_ids_match_incidents(self, populated_engine: IncidentLearningEngine):
        result = populated_engine.generate_all_scenarios()
        source_ids = {s.source_incident_id for s in result}
        incident_ids = {i.incident_id for i in populated_engine._incidents}
        assert source_ids == incident_ids


# ===================================================================
# Engine: assess_repeat_risk
# ===================================================================

class TestAssessRepeatRisk:
    def test_empty_engine(self, engine: IncidentLearningEngine):
        assert engine.assess_repeat_risk() == 0.0

    def test_single_incident(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident())
        risk = engine.assess_repeat_risk()
        assert 0.0 <= risk <= 1.0

    def test_repeated_categories_higher_risk(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A", category=IncidentCategory.CASCADE_FAILURE))
        single_risk = engine.assess_repeat_risk()
        engine.add_incident(_make_incident("B", category=IncidentCategory.CASCADE_FAILURE))
        repeated_risk = engine.assess_repeat_risk()
        assert repeated_risk >= single_risk

    def test_sev1_higher_risk_than_sev4(self):
        eng1 = IncidentLearningEngine()
        eng1.add_incident(_make_incident("A", severity=IncidentSeverity.SEV1))
        risk1 = eng1.assess_repeat_risk()

        eng2 = IncidentLearningEngine()
        eng2.add_incident(_make_incident("A", severity=IncidentSeverity.SEV4))
        risk2 = eng2.assess_repeat_risk()
        assert risk1 > risk2

    def test_risk_bounded_above(self, engine: IncidentLearningEngine):
        for i in range(100):
            engine.add_incident(_make_incident(
                f"INC-{i}", severity=IncidentSeverity.SEV1,
                category=IncidentCategory.CASCADE_FAILURE,
            ))
        assert engine.assess_repeat_risk() <= 1.0

    def test_no_repeats_lower_risk(self, engine: IncidentLearningEngine):
        cats = list(IncidentCategory)
        for i, cat in enumerate(cats):
            engine.add_incident(_make_incident(f"INC-{i}", category=cat))
        risk = engine.assess_repeat_risk()
        # No repeated categories => ratio == 0
        assert risk < 1.0

    def test_all_repeats_higher_risk(self, engine: IncidentLearningEngine):
        for i in range(10):
            engine.add_incident(_make_incident(
                f"INC-{i}", category=IncidentCategory.CASCADE_FAILURE,
                severity=IncidentSeverity.SEV1,
            ))
        risk = engine.assess_repeat_risk()
        assert risk >= 0.5

    def test_returns_rounded(self, populated_engine: IncidentLearningEngine):
        risk = populated_engine.assess_repeat_risk()
        assert risk == round(risk, 4)


# ===================================================================
# Engine: coverage_analysis
# ===================================================================

class TestCoverageAnalysis:
    def test_empty_engine(self, engine: IncidentLearningEngine):
        assert engine.coverage_analysis() == {}

    def test_no_scenarios_zero_coverage(self, populated_engine: IncidentLearningEngine):
        # Don't generate scenarios first
        cov = populated_engine.coverage_analysis()
        for val in cov.values():
            assert val == 0.0

    def test_full_coverage_after_generate(self, populated_engine: IncidentLearningEngine):
        populated_engine.generate_all_scenarios()
        cov = populated_engine.coverage_analysis()
        for val in cov.values():
            assert val == 1.0

    def test_partial_coverage(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A", category=IncidentCategory.CASCADE_FAILURE))
        engine.add_incident(_make_incident("B", category=IncidentCategory.CASCADE_FAILURE))
        # Generate scenario only for incident A
        sc = engine.generate_scenario(engine._incidents[0])
        engine._scenarios = [sc]
        cov = engine.coverage_analysis()
        assert cov["CASCADE_FAILURE"] == 0.5

    def test_categories_present(self, populated_engine: IncidentLearningEngine):
        cov = populated_engine.coverage_analysis()
        assert "CASCADE_FAILURE" in cov
        assert "CAPACITY_EXHAUSTION" in cov

    def test_coverage_bounded(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A"))
        engine.generate_all_scenarios()
        cov = engine.coverage_analysis()
        for val in cov.values():
            assert 0.0 <= val <= 1.0

    def test_coverage_rounded(self, engine: IncidentLearningEngine):
        for i in range(3):
            engine.add_incident(_make_incident(f"INC-{i}", category=IncidentCategory.CASCADE_FAILURE))
        sc = engine.generate_scenario(engine._incidents[0])
        engine._scenarios = [sc]
        cov = engine.coverage_analysis()
        val = cov["CASCADE_FAILURE"]
        assert val == round(val, 4)


# ===================================================================
# Engine: generate_report
# ===================================================================

class TestGenerateReport:
    def test_empty_report(self, engine: IncidentLearningEngine):
        report = engine.generate_report()
        assert isinstance(report, IncidentLearningReport)
        assert report.total_incidents == 0
        assert report.scenarios_generated == 0

    def test_report_total_incidents(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        assert report.total_incidents == 3

    def test_report_scenarios_generated(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        assert report.scenarios_generated == 3

    def test_report_has_templates(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        assert len(report.templates) == 3

    def test_report_has_insights(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        assert len(report.insights) > 0

    def test_report_repeat_risk_score(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        assert 0.0 <= report.repeat_risk_score <= 1.0

    def test_report_coverage(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        assert len(report.coverage_by_category) > 0

    def test_report_coverage_values(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        for val in report.coverage_by_category.values():
            assert 0.0 <= val <= 1.0

    def test_report_templates_are_chaos_scenarios(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        for t in report.templates:
            assert isinstance(t, ChaosScenarioTemplate)

    def test_report_insights_are_learning_insights(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        for i in report.insights:
            assert isinstance(i, LearningInsight)

    def test_report_stores_scenarios_internally(self, populated_engine: IncidentLearningEngine):
        populated_engine.generate_report()
        assert len(populated_engine._scenarios) == 3

    def test_single_incident_report(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident())
        report = engine.generate_report()
        assert report.total_incidents == 1
        assert report.scenarios_generated == 1

    def test_report_coverage_full_after_generate(self, populated_engine: IncidentLearningEngine):
        report = populated_engine.generate_report()
        # After generate_report, all incidents have scenarios
        for val in report.coverage_by_category.values():
            assert val == 1.0


# ===================================================================
# Integration / edge-case tests
# ===================================================================

class TestIntegration:
    def test_full_workflow(self):
        eng = IncidentLearningEngine()
        eng.add_incident(_make_incident("A", category=IncidentCategory.CASCADE_FAILURE, severity=IncidentSeverity.SEV1))
        eng.add_incident(_make_incident("B", category=IncidentCategory.CASCADE_FAILURE, severity=IncidentSeverity.SEV2))
        eng.add_incident(_make_incident("C", category=IncidentCategory.DEPENDENCY_FAILURE, root_cause_component="db"))
        eng.add_incident(_make_incident("D", category=IncidentCategory.DEPENDENCY_FAILURE, root_cause_component="db", detection_time_minutes=30))

        patterns = eng.extract_patterns()
        assert len(patterns) >= 3  # category repeat * 2 + component repeat + slow detection

        scenarios = eng.generate_all_scenarios()
        assert len(scenarios) == 4

        risk = eng.assess_repeat_risk()
        assert risk > 0

        coverage = eng.coverage_analysis()
        assert len(coverage) == 2

        report = eng.generate_report()
        assert report.total_incidents == 4

    def test_all_categories_scenario_generation(self, engine: IncidentLearningEngine):
        for i, cat in enumerate(IncidentCategory):
            engine.add_incident(_make_incident(f"INC-{i}", category=cat))
        scenarios = engine.generate_all_scenarios()
        assert len(scenarios) == len(IncidentCategory)

    def test_all_severities(self, engine: IncidentLearningEngine):
        for i, sev in enumerate(IncidentSeverity):
            engine.add_incident(_make_incident(f"INC-{i}", severity=sev, category=IncidentCategory.CONFIG_ERROR))
        report = engine.generate_report()
        assert report.total_incidents == 4

    def test_large_scale(self, engine: IncidentLearningEngine):
        for i in range(200):
            cat = list(IncidentCategory)[i % len(IncidentCategory)]
            sev = list(IncidentSeverity)[i % len(IncidentSeverity)]
            engine.add_incident(_make_incident(f"INC-{i}", category=cat, severity=sev))
        report = engine.generate_report()
        assert report.total_incidents == 200
        assert report.scenarios_generated == 200
        assert len(report.coverage_by_category) == len(IncidentCategory)

    def test_report_idempotent(self, populated_engine: IncidentLearningEngine):
        r1 = populated_engine.generate_report()
        r2 = populated_engine.generate_report()
        assert r1.total_incidents == r2.total_incidents
        assert r1.scenarios_generated == r2.scenarios_generated
        assert r1.repeat_risk_score == r2.repeat_risk_score

    def test_scenario_failure_sequence_component_substitution_all_categories(self, engine: IncidentLearningEngine):
        for cat in IncidentCategory:
            inc = _make_incident(root_cause_component="target-svc", category=cat)
            sc = engine.generate_scenario(inc)
            for step in sc.failure_sequence:
                if "target" in step:
                    assert step["target"] == "target-svc"

    def test_zero_duration_and_detection(self, engine: IncidentLearningEngine):
        inc = _make_incident(duration_minutes=0.0, detection_time_minutes=0.0)
        sc = engine.generate_scenario(inc)
        assert sc.expected_detection_time_minutes >= 1.0
        assert sc.expected_recovery_time_minutes >= 1.0

    def test_very_large_duration(self, engine: IncidentLearningEngine):
        inc = _make_incident(duration_minutes=10000.0, detection_time_minutes=5000.0)
        sc = engine.generate_scenario(inc)
        assert sc.expected_detection_time_minutes == 2500.0
        assert sc.expected_recovery_time_minutes == 5000.0

    def test_coverage_with_mixed_categories(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A", category=IncidentCategory.CASCADE_FAILURE))
        engine.add_incident(_make_incident("B", category=IncidentCategory.CONFIG_ERROR))
        engine.add_incident(_make_incident("C", category=IncidentCategory.CONFIG_ERROR))
        # Generate scenario for only the first incident
        sc = engine.generate_scenario(engine._incidents[0])
        engine._scenarios = [sc]
        cov = engine.coverage_analysis()
        assert cov["CASCADE_FAILURE"] == 1.0
        assert cov["CONFIG_ERROR"] == 0.0

    def test_pattern_with_single_slow_detection(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A", detection_time_minutes=16.0))
        patterns = engine.extract_patterns()
        slow = [p for p in patterns if "Slow detection" in p.pattern]
        assert len(slow) == 1
        assert slow[0].frequency == 1

    def test_multiple_slow_detection_incidents(self, engine: IncidentLearningEngine):
        engine.add_incident(_make_incident("A", detection_time_minutes=20.0, category=IncidentCategory.CASCADE_FAILURE))
        engine.add_incident(_make_incident("B", detection_time_minutes=30.0, category=IncidentCategory.CONFIG_ERROR))
        patterns = engine.extract_patterns()
        slow = [p for p in patterns if "Slow detection" in p.pattern]
        assert len(slow) == 1
        assert slow[0].frequency == 2
        assert len(slow[0].affected_categories) == 2
