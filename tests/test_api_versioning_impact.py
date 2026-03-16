"""Tests for api_versioning_impact module — 100% coverage target."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.api_versioning_impact import (
    ApiVersion,
    ApiVersioningImpactEngine,
    BreakingChange,
    ChangeType,
    CompatibilityLevel,
    CompatibilityMatrix,
    MigrationPlan,
    MigrationRisk,
    MigrationRiskLevel,
    SkewSeverity,
    SunsetImpact,
    SunsetPhase,
    SunsetPlan,
    SunsetPlanEntry,
    SunsetPolicy,
    StrategyConsistencyReport,
    VersionHealthReport,
    VersionSkewRisk,
    VersioningStrategy,
    _BREAKING_TYPES,
    _CHANGE_TYPE_RISK,
    _COMPATIBILITY_SCORE,
    _EFFORT_PER_BREAKING_CHANGE,
    _EFFORT_PER_ENDPOINT,
    _MAX_RISK_SCORE,
    _PHASE_RISK_MULTIPLIER,
    _STRATEGY_COMPLEXITY,
    _aggregate_risk,
    _change_id,
    _compute_change_risk,
    _days_until,
    _estimate_downtime_minutes,
    _version_sort_key,
    classify_migration_risk_level,
    classify_skew_severity,
    compute_breaking_change_score,
    parse_version_number,
    version_distance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _api_ver(
    version="v1",
    component_id="c1",
    strategy=VersioningStrategy.URL_PATH,
    phase=SunsetPhase.ACTIVE,
    consumers=None,
    endpoints=None,
    release_date="",
    sunset_date="",
):
    return ApiVersion(
        version=version,
        component_id=component_id,
        strategy=strategy,
        phase=phase,
        consumers=consumers or [],
        endpoints=endpoints or [],
        release_date=release_date,
        sunset_date=sunset_date,
    )


def _change(
    source="v1",
    target="v2",
    component_id="c1",
    change_type=ChangeType.BREAKING,
    description="field removed",
    endpoints=None,
):
    return BreakingChange(
        source_version=source,
        target_version=target,
        component_id=component_id,
        change_type=change_type,
        description=description,
        affected_endpoints=endpoints or [],
    )


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_versioning_strategy_values(self):
        assert VersioningStrategy.URL_PATH.value == "url_path"
        assert VersioningStrategy.HEADER.value == "header"
        assert VersioningStrategy.QUERY_PARAM.value == "query_param"
        assert VersioningStrategy.CONTENT_TYPE.value == "content_type"
        assert VersioningStrategy.CONTENT_NEGOTIATION.value == "content_negotiation"
        assert VersioningStrategy.CUSTOM.value == "custom"

    def test_change_type_values(self):
        assert ChangeType.BREAKING.value == "breaking"
        assert ChangeType.NON_BREAKING.value == "non_breaking"
        assert ChangeType.DEPRECATION.value == "deprecation"
        assert ChangeType.REMOVAL.value == "removal"
        assert ChangeType.ADDITION.value == "addition"
        assert ChangeType.FIELD_TYPE_CHANGE.value == "field_type_change"
        assert ChangeType.ENDPOINT_RENAME.value == "endpoint_rename"
        assert ChangeType.AUTH_CHANGE.value == "auth_change"
        assert ChangeType.RATE_LIMIT_CHANGE.value == "rate_limit_change"
        assert ChangeType.PAGINATION_CHANGE.value == "pagination_change"

    def test_compatibility_level_values(self):
        assert CompatibilityLevel.FULL.value == "full"
        assert CompatibilityLevel.BACKWARD.value == "backward"
        assert CompatibilityLevel.FORWARD.value == "forward"
        assert CompatibilityLevel.NONE.value == "none"

    def test_sunset_phase_values(self):
        assert SunsetPhase.ACTIVE.value == "active"
        assert SunsetPhase.DEPRECATED.value == "deprecated"
        assert SunsetPhase.SUNSET.value == "sunset"
        assert SunsetPhase.REMOVED.value == "removed"

    def test_skew_severity_values(self):
        assert SkewSeverity.CRITICAL.value == "critical"
        assert SkewSeverity.HIGH.value == "high"
        assert SkewSeverity.MEDIUM.value == "medium"
        assert SkewSeverity.LOW.value == "low"
        assert SkewSeverity.NONE.value == "none"

    def test_migration_risk_level_values(self):
        assert MigrationRiskLevel.CRITICAL.value == "critical"
        assert MigrationRiskLevel.HIGH.value == "high"
        assert MigrationRiskLevel.MEDIUM.value == "medium"
        assert MigrationRiskLevel.LOW.value == "low"
        assert MigrationRiskLevel.NEGLIGIBLE.value == "negligible"


# ---------------------------------------------------------------------------
# Model creation tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_api_version_defaults(self):
        v = ApiVersion(version="v1", component_id="c1")
        assert v.strategy == VersioningStrategy.URL_PATH
        assert v.phase == SunsetPhase.ACTIVE
        assert v.consumers == []
        assert v.endpoints == []
        assert v.release_date == ""
        assert v.sunset_date == ""
        assert v.deprecation_date == ""
        assert v.fields_spec == {}
        assert v.supported_versions == []

    def test_api_version_with_all_fields(self):
        v = _api_ver(
            version="v2",
            component_id="api-gw",
            strategy=VersioningStrategy.HEADER,
            phase=SunsetPhase.DEPRECATED,
            consumers=["svc-a", "svc-b"],
            endpoints=["/users", "/orders"],
            release_date="2025-01-01",
            sunset_date="2025-06-01",
        )
        assert v.version == "v2"
        assert v.component_id == "api-gw"
        assert v.strategy == VersioningStrategy.HEADER
        assert v.phase == SunsetPhase.DEPRECATED
        assert len(v.consumers) == 2
        assert len(v.endpoints) == 2

    def test_breaking_change_defaults(self):
        c = BreakingChange(
            source_version="v1",
            target_version="v2",
            component_id="c1",
            change_type=ChangeType.BREAKING,
            description="test",
        )
        assert c.risk_score == 0.0
        assert c.affected_endpoints == []
        assert c.affected_field == ""
        assert c.rollback_safe is True
        assert c.migration_effort_hours == 1.0

    def test_compatibility_matrix_defaults(self):
        m = CompatibilityMatrix(component_id="c1")
        assert m.versions == []
        assert m.matrix == {}

    def test_version_skew_risk_defaults(self):
        r = VersionSkewRisk()
        assert r.component_ids == []
        assert r.versions_in_use == {}
        assert r.severity == SkewSeverity.NONE
        assert r.max_version_gap == 0
        assert r.description == ""
        assert r.affected_consumers == []

    def test_migration_risk_defaults(self):
        r = MigrationRisk(
            consumer_id="svc-a",
            source_version="v1",
            target_version="v2",
        )
        assert r.risk_score == 0.0
        assert r.breaking_changes_count == 0
        assert r.estimated_effort_hours == 0.0
        assert r.migration_steps == []
        assert r.risk_factors == []
        assert r.risk_level == MigrationRiskLevel.LOW
        assert r.affected_endpoints_count == 0

    def test_sunset_policy_defaults(self):
        p = SunsetPolicy(
            component_id="c1",
            version="v1",
            phase=SunsetPhase.DEPRECATED,
        )
        assert p.grace_period_days == 90
        assert p.active_consumers == 0
        assert p.migration_complete_percent == 0.0
        assert p.violations == []
        assert p.deprecation_date == ""
        assert p.removal_date == ""

    def test_sunset_impact_defaults(self):
        si = SunsetImpact(component_id="c1", version="v1")
        assert si.affected_consumers == []
        assert si.total_consumers == 0
        assert si.consumers_migrated == 0
        assert si.migration_percent == 0.0
        assert si.blocking_issues == []
        assert si.estimated_outage_risk == 0.0
        assert si.recommendations == []

    def test_sunset_plan_entry_defaults(self):
        e = SunsetPlanEntry(
            component_id="c1",
            version="v1",
            current_status=SunsetPhase.DEPRECATED,
            recommended_action="migrate",
        )
        assert e.deadline == ""
        assert e.consumers_affected == 0
        assert e.days_until_sunset is None

    def test_sunset_plan_defaults(self):
        sp = SunsetPlan()
        assert sp.entries == []
        assert sp.total_versions_to_sunset == 0
        assert sp.total_consumers_affected == 0

    def test_migration_plan_defaults(self):
        mp = MigrationPlan(
            component_id="c1",
            source_version="v1",
            target_version="v2",
        )
        assert mp.total_consumers == 0
        assert mp.migration_risks == []
        assert mp.overall_risk_score == 0.0
        assert mp.overall_risk_level == MigrationRiskLevel.LOW
        assert mp.estimated_total_effort_hours == 0.0
        assert mp.estimated_downtime_minutes == 0.0
        assert mp.parallel_possible is False
        assert mp.phases == []
        assert mp.recommendations == []

    def test_strategy_consistency_report_defaults(self):
        r = StrategyConsistencyReport()
        assert r.consistent is True
        assert r.strategy_counts == {}
        assert r.dominant_strategy is None
        assert r.outliers == []
        assert r.total_components == 0

    def test_version_health_report_defaults(self):
        r = VersionHealthReport()
        assert r.versions == []
        assert r.breaking_changes == []
        assert r.overall_versioning_health == 0.0
        assert r.total_breaking_changes == 0
        assert r.deprecated_versions_count == 0
        assert r.at_risk_consumers == 0
        assert r.recommendations == []
        assert r.skew_risks == []
        assert r.sunset_plan is None
        assert r.strategy_consistency is None
        assert r.backward_compatibility_score == 1.0
        assert r.component_version_map == {}


# ---------------------------------------------------------------------------
# Mapping table tests
# ---------------------------------------------------------------------------


class TestMappingTables:
    def test_change_type_risk_values(self):
        assert _CHANGE_TYPE_RISK[ChangeType.BREAKING] == 10.0
        assert _CHANGE_TYPE_RISK[ChangeType.REMOVAL] == 8.0
        assert _CHANGE_TYPE_RISK[ChangeType.DEPRECATION] == 4.0
        assert _CHANGE_TYPE_RISK[ChangeType.NON_BREAKING] == 1.0
        assert _CHANGE_TYPE_RISK[ChangeType.ADDITION] == 0.5
        assert _CHANGE_TYPE_RISK[ChangeType.FIELD_TYPE_CHANGE] == 7.0
        assert _CHANGE_TYPE_RISK[ChangeType.ENDPOINT_RENAME] == 6.0
        assert _CHANGE_TYPE_RISK[ChangeType.AUTH_CHANGE] == 9.0
        assert _CHANGE_TYPE_RISK[ChangeType.RATE_LIMIT_CHANGE] == 3.0
        assert _CHANGE_TYPE_RISK[ChangeType.PAGINATION_CHANGE] == 4.0

    def test_strategy_complexity_values(self):
        assert _STRATEGY_COMPLEXITY[VersioningStrategy.URL_PATH] == 1.0
        assert _STRATEGY_COMPLEXITY[VersioningStrategy.HEADER] == 1.5
        assert _STRATEGY_COMPLEXITY[VersioningStrategy.QUERY_PARAM] == 1.2
        assert _STRATEGY_COMPLEXITY[VersioningStrategy.CONTENT_TYPE] == 2.0
        assert _STRATEGY_COMPLEXITY[VersioningStrategy.CONTENT_NEGOTIATION] == 2.0
        assert _STRATEGY_COMPLEXITY[VersioningStrategy.CUSTOM] == 2.5

    def test_phase_risk_multiplier_values(self):
        assert _PHASE_RISK_MULTIPLIER[SunsetPhase.ACTIVE] == 0.0
        assert _PHASE_RISK_MULTIPLIER[SunsetPhase.DEPRECATED] == 1.0
        assert _PHASE_RISK_MULTIPLIER[SunsetPhase.SUNSET] == 2.0
        assert _PHASE_RISK_MULTIPLIER[SunsetPhase.REMOVED] == 5.0

    def test_compatibility_score_values(self):
        assert _COMPATIBILITY_SCORE[CompatibilityLevel.FULL] == 1.0
        assert _COMPATIBILITY_SCORE[CompatibilityLevel.BACKWARD] == 0.7
        assert _COMPATIBILITY_SCORE[CompatibilityLevel.FORWARD] == 0.5
        assert _COMPATIBILITY_SCORE[CompatibilityLevel.NONE] == 0.0

    def test_effort_constants(self):
        assert _EFFORT_PER_BREAKING_CHANGE == 4.0
        assert _EFFORT_PER_ENDPOINT == 1.0
        assert _MAX_RISK_SCORE == 100.0

    def test_breaking_types_frozenset(self):
        assert ChangeType.BREAKING in _BREAKING_TYPES
        assert ChangeType.REMOVAL in _BREAKING_TYPES
        assert ChangeType.FIELD_TYPE_CHANGE in _BREAKING_TYPES
        assert ChangeType.AUTH_CHANGE in _BREAKING_TYPES
        assert ChangeType.NON_BREAKING not in _BREAKING_TYPES
        assert ChangeType.ADDITION not in _BREAKING_TYPES


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_change_id_deterministic(self):
        c = _change()
        id1 = _change_id(c)
        id2 = _change_id(c)
        assert id1 == id2
        assert len(id1) == 12

    def test_change_id_different_inputs(self):
        c1 = _change(source="v1", target="v2")
        c2 = _change(source="v2", target="v3")
        assert _change_id(c1) != _change_id(c2)

    def test_compute_change_risk_breaking(self):
        risk = _compute_change_risk(ChangeType.BREAKING, 3, 5, VersioningStrategy.URL_PATH)
        assert risk > 0
        assert risk <= _MAX_RISK_SCORE

    def test_compute_change_risk_addition(self):
        risk = _compute_change_risk(ChangeType.ADDITION, 1, 1, VersioningStrategy.URL_PATH)
        assert risk < 10.0

    def test_compute_change_risk_caps_at_max(self):
        risk = _compute_change_risk(ChangeType.BREAKING, 100, 100, VersioningStrategy.CUSTOM)
        assert risk == _MAX_RISK_SCORE

    def test_compute_change_risk_with_header_strategy(self):
        risk_url = _compute_change_risk(ChangeType.BREAKING, 2, 2, VersioningStrategy.URL_PATH)
        risk_hdr = _compute_change_risk(ChangeType.BREAKING, 2, 2, VersioningStrategy.HEADER)
        assert risk_hdr > risk_url

    def test_compute_change_risk_zero_endpoints(self):
        risk = _compute_change_risk(ChangeType.NON_BREAKING, 0, 0, VersioningStrategy.URL_PATH)
        assert risk >= 0

    def test_days_until_empty(self):
        assert _days_until("") is None

    def test_days_until_invalid(self):
        assert _days_until("not-a-date") is None

    def test_days_until_future_date(self):
        result = _days_until("2099-01-01T00:00:00Z")
        assert result is not None
        assert result > 0

    def test_days_until_past_date(self):
        result = _days_until("2020-01-01T00:00:00Z")
        assert result is not None
        assert result < 0

    def test_days_until_without_timezone(self):
        result = _days_until("2099-06-15T12:00:00")
        assert result is not None
        assert result > 0

    def test_version_sort_key_basic(self):
        assert _version_sort_key("v1") < _version_sort_key("v2")
        assert _version_sort_key("v2") < _version_sort_key("v10")

    def test_version_sort_key_multi_digit(self):
        versions = ["v10", "v2", "v1", "v3"]
        sorted_v = sorted(versions, key=_version_sort_key)
        assert sorted_v == ["v1", "v2", "v3", "v10"]

    def test_version_sort_key_alpha(self):
        k = _version_sort_key("abc")
        assert isinstance(k, tuple)

    def test_version_sort_key_digit_then_alpha(self):
        """Covers the branch where digit segment is followed by non-digit."""
        k = _version_sort_key("1a2b")
        assert isinstance(k, tuple)


# ---------------------------------------------------------------------------
# parse_version_number
# ---------------------------------------------------------------------------


class TestParseVersionNumber:
    def test_simple_version(self):
        assert parse_version_number("v1") == (1,)

    def test_dotted_version(self):
        assert parse_version_number("v2.1") == (2, 1)

    def test_triple_version(self):
        assert parse_version_number("1.2.3") == (1, 2, 3)

    def test_uppercase_v(self):
        assert parse_version_number("V3") == (3,)

    def test_beta_suffix(self):
        assert parse_version_number("v1.0.0-beta") == (1, 0, 0)

    def test_plus_suffix(self):
        assert parse_version_number("v2.1.0+build42") == (2, 1, 0)

    def test_empty_string(self):
        assert parse_version_number("") == (0,)

    def test_no_digits(self):
        assert parse_version_number("abc") == (0,)

    def test_mixed_alpha_numeric_parts(self):
        result = parse_version_number("v1.2a.3b")
        assert result == (1, 2, 3)


# ---------------------------------------------------------------------------
# version_distance
# ---------------------------------------------------------------------------


class TestVersionDistance:
    def test_same_version(self):
        assert version_distance("v1", "v1") == 0

    def test_adjacent_major(self):
        d = version_distance("v1", "v2")
        assert d > 0

    def test_large_gap(self):
        d1 = version_distance("v1", "v2")
        d2 = version_distance("v1", "v5")
        assert d2 > d1

    def test_minor_distance(self):
        d = version_distance("v1.0", "v1.1")
        assert d > 0

    def test_major_weighs_more_than_minor(self):
        d_major = version_distance("v1.0", "v2.0")
        d_minor = version_distance("v1.0", "v1.1")
        assert d_major > d_minor

    def test_different_length_versions(self):
        d = version_distance("v1", "v1.2.3")
        assert d > 0


# ---------------------------------------------------------------------------
# classify_skew_severity
# ---------------------------------------------------------------------------


class TestClassifySkewSeverity:
    def test_zero_gap(self):
        assert classify_skew_severity(0) == SkewSeverity.NONE

    def test_negative_gap(self):
        assert classify_skew_severity(-1) == SkewSeverity.NONE

    def test_gap_one(self):
        assert classify_skew_severity(1) == SkewSeverity.LOW

    def test_gap_two(self):
        assert classify_skew_severity(2) == SkewSeverity.MEDIUM

    def test_gap_three(self):
        assert classify_skew_severity(3) == SkewSeverity.HIGH

    def test_gap_four_plus(self):
        assert classify_skew_severity(4) == SkewSeverity.CRITICAL
        assert classify_skew_severity(100) == SkewSeverity.CRITICAL


# ---------------------------------------------------------------------------
# classify_migration_risk_level
# ---------------------------------------------------------------------------


class TestClassifyMigrationRiskLevel:
    def test_negligible(self):
        assert classify_migration_risk_level(0, 1.0, True) == MigrationRiskLevel.NEGLIGIBLE

    def test_critical_not_rollback_safe_many_breaking(self):
        assert classify_migration_risk_level(3, 10.0, False) == MigrationRiskLevel.CRITICAL

    def test_high_not_rollback_safe(self):
        assert classify_migration_risk_level(1, 2.0, False) == MigrationRiskLevel.HIGH

    def test_high_many_breaking(self):
        assert classify_migration_risk_level(3, 2.0, True) == MigrationRiskLevel.HIGH

    def test_medium_some_breaking(self):
        assert classify_migration_risk_level(1, 2.0, True) == MigrationRiskLevel.MEDIUM

    def test_medium_high_effort(self):
        assert classify_migration_risk_level(0, 4.0, True) == MigrationRiskLevel.MEDIUM

    def test_low(self):
        assert classify_migration_risk_level(0, 2.5, True) == MigrationRiskLevel.LOW


# ---------------------------------------------------------------------------
# compute_breaking_change_score
# ---------------------------------------------------------------------------


class TestComputeBreakingChangeScore:
    def test_no_changes(self):
        assert compute_breaking_change_score([]) == 1.0

    def test_single_breaking(self):
        changes = [_change(change_type=ChangeType.BREAKING)]
        score = compute_breaking_change_score(changes)
        assert 0.0 <= score < 1.0

    def test_addition_minimal_penalty(self):
        changes = [_change(change_type=ChangeType.ADDITION)]
        score = compute_breaking_change_score(changes)
        assert score > 0.9

    def test_many_changes_floor_zero(self):
        changes = [
            _change(change_type=ChangeType.BREAKING, description=f"c{i}")
            for i in range(20)
        ]
        score = compute_breaking_change_score(changes)
        assert score == 0.0

    def test_removal_penalty(self):
        changes = [_change(change_type=ChangeType.REMOVAL)]
        score = compute_breaking_change_score(changes)
        assert 0.0 <= score < 1.0

    def test_field_type_change(self):
        changes = [_change(change_type=ChangeType.FIELD_TYPE_CHANGE)]
        score = compute_breaking_change_score(changes)
        assert 0.0 <= score < 1.0

    def test_auth_change(self):
        changes = [_change(change_type=ChangeType.AUTH_CHANGE)]
        score = compute_breaking_change_score(changes)
        assert 0.0 <= score < 1.0

    def test_rate_limit_change(self):
        changes = [_change(change_type=ChangeType.RATE_LIMIT_CHANGE)]
        score = compute_breaking_change_score(changes)
        assert score > 0.9

    def test_pagination_change(self):
        changes = [_change(change_type=ChangeType.PAGINATION_CHANGE)]
        score = compute_breaking_change_score(changes)
        assert 0.0 <= score < 1.0

    def test_endpoint_rename(self):
        changes = [_change(change_type=ChangeType.ENDPOINT_RENAME)]
        score = compute_breaking_change_score(changes)
        assert 0.0 <= score < 1.0


# ---------------------------------------------------------------------------
# _aggregate_risk
# ---------------------------------------------------------------------------


class TestAggregateRisk:
    def test_empty(self):
        assert _aggregate_risk([]) == MigrationRiskLevel.LOW

    def test_single_critical(self):
        assert _aggregate_risk([MigrationRiskLevel.CRITICAL]) == MigrationRiskLevel.CRITICAL

    def test_mixed_returns_highest(self):
        levels = [MigrationRiskLevel.LOW, MigrationRiskLevel.HIGH, MigrationRiskLevel.NEGLIGIBLE]
        assert _aggregate_risk(levels) == MigrationRiskLevel.HIGH

    def test_all_negligible(self):
        assert _aggregate_risk([MigrationRiskLevel.NEGLIGIBLE, MigrationRiskLevel.NEGLIGIBLE]) == MigrationRiskLevel.NEGLIGIBLE

    def test_medium_and_low(self):
        assert _aggregate_risk([MigrationRiskLevel.MEDIUM, MigrationRiskLevel.LOW]) == MigrationRiskLevel.MEDIUM


# ---------------------------------------------------------------------------
# _estimate_downtime_minutes
# ---------------------------------------------------------------------------


class TestEstimateDowntime:
    def test_empty(self):
        assert _estimate_downtime_minutes([]) == 0.0

    def test_single_low_risk(self):
        r = MigrationRisk(
            consumer_id="a",
            source_version="v1",
            target_version="v2",
            estimated_effort_hours=1.0,
            breaking_changes_count=0,
            risk_level=MigrationRiskLevel.LOW,
        )
        result = _estimate_downtime_minutes([r])
        assert result > 0

    def test_high_risk_multiplier(self):
        r_low = MigrationRisk(
            consumer_id="a",
            source_version="v1",
            target_version="v2",
            estimated_effort_hours=2.0,
            breaking_changes_count=1,
            risk_level=MigrationRiskLevel.LOW,
        )
        r_high = MigrationRisk(
            consumer_id="b",
            source_version="v1",
            target_version="v2",
            estimated_effort_hours=2.0,
            breaking_changes_count=1,
            risk_level=MigrationRiskLevel.HIGH,
        )
        dt_low = _estimate_downtime_minutes([r_low])
        dt_high = _estimate_downtime_minutes([r_high])
        assert dt_high > dt_low

    def test_critical_risk_multiplier(self):
        r = MigrationRisk(
            consumer_id="a",
            source_version="v1",
            target_version="v2",
            estimated_effort_hours=2.0,
            breaking_changes_count=3,
            risk_level=MigrationRiskLevel.CRITICAL,
        )
        result = _estimate_downtime_minutes([r])
        # base = 2.0 * 2.0 = 4.0, then * 3.0 = 12.0, plus 3*5=15, total 27
        assert result > 20

    def test_multiple_risks_additive(self):
        r1 = MigrationRisk(
            consumer_id="a",
            source_version="v1",
            target_version="v2",
            estimated_effort_hours=1.0,
            breaking_changes_count=0,
            risk_level=MigrationRiskLevel.LOW,
        )
        r2 = MigrationRisk(
            consumer_id="b",
            source_version="v1",
            target_version="v2",
            estimated_effort_hours=1.0,
            breaking_changes_count=0,
            risk_level=MigrationRiskLevel.LOW,
        )
        dt_one = _estimate_downtime_minutes([r1])
        dt_two = _estimate_downtime_minutes([r1, r2])
        assert dt_two > dt_one


# ---------------------------------------------------------------------------
# Engine: analyze_breaking_changes
# ---------------------------------------------------------------------------


class TestAnalyzeBreakingChanges:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_empty_changes(self):
        g = _graph(_comp())
        result = self.engine.analyze_breaking_changes(g, [], [])
        assert result == []

    def test_single_breaking_change_scored(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["svc-a", "svc-b"])]
        changes = [_change(endpoints=["/users"])]
        result = self.engine.analyze_breaking_changes(g, versions, changes)
        assert len(result) == 1
        assert result[0].risk_score > 0

    def test_multiple_changes_sorted_by_risk(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["svc-a"])]
        changes = [
            _change(change_type=ChangeType.ADDITION, endpoints=["/new"]),
            _change(change_type=ChangeType.BREAKING, endpoints=["/users", "/orders"]),
        ]
        result = self.engine.analyze_breaking_changes(g, versions, changes)
        assert len(result) == 2
        assert result[0].risk_score >= result[1].risk_score

    def test_change_without_matching_version(self):
        g = _graph(_comp())
        changes = [_change(component_id="unknown")]
        result = self.engine.analyze_breaking_changes(g, [], changes)
        assert len(result) == 1
        assert result[0].risk_score > 0

    def test_strategy_affects_risk(self):
        g = _graph(_comp())
        v_url = [_api_ver(strategy=VersioningStrategy.URL_PATH, consumers=["a"])]
        v_custom = [_api_ver(strategy=VersioningStrategy.CUSTOM, consumers=["a"])]
        c = [_change(endpoints=["/e1"])]
        r_url = self.engine.analyze_breaking_changes(g, v_url, c)
        r_custom = self.engine.analyze_breaking_changes(g, v_custom, c)
        assert r_custom[0].risk_score > r_url[0].risk_score


# ---------------------------------------------------------------------------
# Engine: compute_compatibility_matrix
# ---------------------------------------------------------------------------


class TestComputeCompatibilityMatrix:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_empty_versions(self):
        result = self.engine.compute_compatibility_matrix([], [])
        assert result == []

    def test_single_version_full_compat(self):
        versions = [_api_ver(version="v1")]
        result = self.engine.compute_compatibility_matrix(versions, [])
        assert len(result) == 1
        assert result[0].matrix["v1"]["v1"] == CompatibilityLevel.FULL

    def test_two_versions_no_changes(self):
        versions = [_api_ver(version="v1"), _api_ver(version="v2")]
        result = self.engine.compute_compatibility_matrix(versions, [])
        mat = result[0]
        assert mat.matrix["v1"]["v2"] == CompatibilityLevel.FULL
        assert mat.matrix["v2"]["v1"] == CompatibilityLevel.FULL

    def test_breaking_change_none_compat(self):
        versions = [_api_ver(version="v1"), _api_ver(version="v2")]
        changes = [_change(source="v1", target="v2", change_type=ChangeType.BREAKING)]
        result = self.engine.compute_compatibility_matrix(versions, changes)
        mat = result[0]
        assert mat.matrix["v1"]["v2"] == CompatibilityLevel.NONE

    def test_removal_change_none_compat(self):
        versions = [_api_ver(version="v1"), _api_ver(version="v2")]
        changes = [_change(source="v1", target="v2", change_type=ChangeType.REMOVAL)]
        result = self.engine.compute_compatibility_matrix(versions, changes)
        assert result[0].matrix["v1"]["v2"] == CompatibilityLevel.NONE

    def test_deprecation_backward_compat(self):
        versions = [_api_ver(version="v1"), _api_ver(version="v2")]
        changes = [_change(source="v1", target="v2", change_type=ChangeType.DEPRECATION)]
        result = self.engine.compute_compatibility_matrix(versions, changes)
        assert result[0].matrix["v1"]["v2"] == CompatibilityLevel.BACKWARD

    def test_addition_forward_compat(self):
        versions = [_api_ver(version="v1"), _api_ver(version="v2")]
        changes = [_change(source="v1", target="v2", change_type=ChangeType.ADDITION)]
        result = self.engine.compute_compatibility_matrix(versions, changes)
        assert result[0].matrix["v1"]["v2"] == CompatibilityLevel.FORWARD

    def test_multiple_components(self):
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v1", component_id="c2"),
        ]
        result = self.engine.compute_compatibility_matrix(versions, [])
        assert len(result) == 2

    def test_versions_sorted_in_matrix(self):
        versions = [
            _api_ver(version="v3"),
            _api_ver(version="v1"),
            _api_ver(version="v2"),
        ]
        result = self.engine.compute_compatibility_matrix(versions, [])
        assert result[0].versions == ["v1", "v2", "v3"]

    def test_field_type_change_none_compat(self):
        versions = [_api_ver(version="v1"), _api_ver(version="v2")]
        changes = [_change(source="v1", target="v2", change_type=ChangeType.FIELD_TYPE_CHANGE)]
        result = self.engine.compute_compatibility_matrix(versions, changes)
        assert result[0].matrix["v1"]["v2"] == CompatibilityLevel.NONE

    def test_auth_change_none_compat(self):
        versions = [_api_ver(version="v1"), _api_ver(version="v2")]
        changes = [_change(source="v1", target="v2", change_type=ChangeType.AUTH_CHANGE)]
        result = self.engine.compute_compatibility_matrix(versions, changes)
        assert result[0].matrix["v1"]["v2"] == CompatibilityLevel.NONE


# ---------------------------------------------------------------------------
# Engine: evaluate_sunset_policies
# ---------------------------------------------------------------------------


class TestEvaluateSunsetPolicies:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_no_deprecated_versions(self):
        versions = [_api_ver(phase=SunsetPhase.ACTIVE)]
        result = self.engine.evaluate_sunset_policies(versions)
        assert result == []

    def test_deprecated_with_consumers_violation(self):
        versions = [_api_ver(
            phase=SunsetPhase.DEPRECATED,
            consumers=["svc-a"],
        )]
        result = self.engine.evaluate_sunset_policies(versions)
        assert len(result) == 1
        assert any("consumer" in v.lower() for v in result[0].violations)

    def test_sunset_phase_with_consumers(self):
        versions = [_api_ver(
            phase=SunsetPhase.SUNSET,
            consumers=["svc-a", "svc-b"],
        )]
        result = self.engine.evaluate_sunset_policies(versions)
        assert len(result) == 1
        assert len(result[0].violations) > 0

    def test_removed_with_consumers(self):
        versions = [_api_ver(
            phase=SunsetPhase.REMOVED,
            consumers=["svc-a"],
        )]
        result = self.engine.evaluate_sunset_policies(versions)
        assert len(result) == 1
        assert any("REMOVED" in v for v in result[0].violations)

    def test_sunset_date_passed(self):
        versions = [_api_ver(
            phase=SunsetPhase.DEPRECATED,
            consumers=["svc-a"],
            sunset_date="2020-01-01T00:00:00Z",
        )]
        result = self.engine.evaluate_sunset_policies(versions)
        assert len(result) == 1
        violations = result[0].violations
        assert any("passed" in v.lower() for v in violations)

    def test_sunset_date_approaching_migration_incomplete(self):
        versions = [_api_ver(
            phase=SunsetPhase.DEPRECATED,
            consumers=["svc-a"],
            sunset_date="2099-01-01T00:00:00Z",
        )]
        policies = [SunsetPolicy(
            component_id="c1",
            version="v1",
            phase=SunsetPhase.DEPRECATED,
            sunset_date="2099-01-01T00:00:00Z",
            grace_period_days=999999,
            migration_complete_percent=50.0,
        )]
        result = self.engine.evaluate_sunset_policies(versions, policies)
        assert len(result) == 1

    def test_custom_policies(self):
        versions = [_api_ver(consumers=["svc-a"])]
        policies = [SunsetPolicy(
            component_id="c1",
            version="v1",
            phase=SunsetPhase.DEPRECATED,
            active_consumers=1,
        )]
        result = self.engine.evaluate_sunset_policies(versions, policies)
        assert len(result) == 1
        assert result[0].active_consumers == 1

    def test_migration_percent_updated(self):
        versions = [_api_ver(
            phase=SunsetPhase.DEPRECATED,
            consumers=["svc-a", "svc-b", "svc-c"],
        )]
        result = self.engine.evaluate_sunset_policies(versions)
        assert len(result) == 1
        assert result[0].active_consumers == 3

    def test_policy_without_matching_version(self):
        """Covers branch where api_ver is None — uses policy.active_consumers."""
        versions = [_api_ver(version="v1", component_id="c1")]
        policies = [SunsetPolicy(
            component_id="c999",
            version="v99",
            phase=SunsetPhase.DEPRECATED,
            active_consumers=5,
        )]
        result = self.engine.evaluate_sunset_policies(versions, policies)
        assert len(result) == 1
        assert result[0].active_consumers == 5

    def test_migration_percent_recalculated(self):
        """When api_ver exists, active_consumers = len(consumers), so migration_pct stays default."""
        versions = [_api_ver(
            phase=SunsetPhase.DEPRECATED,
            consumers=["svc-a", "svc-b", "svc-c", "svc-d"],
        )]
        policies = [SunsetPolicy(
            component_id="c1",
            version="v1",
            phase=SunsetPhase.DEPRECATED,
            active_consumers=2,
        )]
        result = self.engine.evaluate_sunset_policies(versions, policies)
        assert result[0].active_consumers == 4
        assert result[0].migration_complete_percent == 0.0


# ---------------------------------------------------------------------------
# Engine: simulate_sunset_impact
# ---------------------------------------------------------------------------


class TestSimulateSunsetImpact:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_no_consumers(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=[])]
        result = self.engine.simulate_sunset_impact(g, versions, "c1", "v1")
        assert result.total_consumers == 0
        assert result.migration_percent == 100.0

    def test_consumers_not_migrated(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["svc-a", "svc-b"])]
        result = self.engine.simulate_sunset_impact(g, versions, "c1", "v1")
        assert result.total_consumers == 2
        assert result.consumers_migrated == 0
        assert result.estimated_outage_risk > 0

    def test_consumers_partially_migrated(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1", consumers=["svc-a", "svc-b"]),
            _api_ver(version="v2", consumers=["svc-a"]),
        ]
        result = self.engine.simulate_sunset_impact(g, versions, "c1", "v1")
        assert result.consumers_migrated == 1
        assert result.migration_percent == 50.0

    def test_active_version_sunset_risk(self):
        g = _graph(_comp())
        versions = [_api_ver(phase=SunsetPhase.ACTIVE, consumers=["svc-a"])]
        result = self.engine.simulate_sunset_impact(g, versions, "c1", "v1")
        assert any("ACTIVE" in b for b in result.blocking_issues)
        assert result.estimated_outage_risk >= 0.3

    def test_graph_dependents_included(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        dep = Dependency(source_id="c2", target_id="c1")
        g.add_dependency(dep)
        versions = [_api_ver(consumers=[])]
        result = self.engine.simulate_sunset_impact(g, versions, "c1", "v1")
        assert "c2" in result.affected_consumers

    def test_component_not_in_graph(self):
        g = _graph()
        versions = [_api_ver(consumers=["svc-a"])]
        result = self.engine.simulate_sunset_impact(g, versions, "c1", "v1")
        assert result.total_consumers == 1

    def test_sunset_recommendations_generated(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["svc-a"])]
        result = self.engine.simulate_sunset_impact(g, versions, "c1", "v1")
        assert len(result.recommendations) > 0

    def test_all_migrated_recommendations(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1", consumers=["svc-a"]),
            _api_ver(version="v2", consumers=["svc-a"]),
        ]
        result = self.engine.simulate_sunset_impact(g, versions, "c1", "v1")
        assert result.migration_percent == 100.0
        assert any("safe" in r.lower() or "migrated" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Engine: detect_version_skew
# ---------------------------------------------------------------------------


class TestDetectVersionSkew:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_no_versions(self):
        g = _graph(_comp())
        result = self.engine.detect_version_skew(g, [])
        assert result == []

    def test_single_component_no_skew(self):
        g = _graph(_comp())
        versions = [_api_ver(version="v1", component_id="c1")]
        result = self.engine.detect_version_skew(g, versions)
        assert result == []

    def test_connected_same_version_no_skew(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v1", component_id="c2"),
        ]
        result = self.engine.detect_version_skew(g, versions)
        assert result == []

    def test_connected_different_versions_skew(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v3", component_id="c2"),
        ]
        result = self.engine.detect_version_skew(g, versions)
        assert len(result) >= 1
        assert result[0].max_version_gap > 0
        assert result[0].severity != SkewSeverity.NONE

    def test_unconnected_components_no_skew(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        # No dependency between them
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v5", component_id="c2"),
        ]
        result = self.engine.detect_version_skew(g, versions)
        # No cluster because not connected
        assert result == []

    def test_skew_only_active_versions(self):
        """Only ACTIVE versions are considered for skew detection."""
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1", phase=SunsetPhase.ACTIVE),
            _api_ver(version="v5", component_id="c2", phase=SunsetPhase.DEPRECATED),
        ]
        # c2 is deprecated, not in active_map, so no cluster
        result = self.engine.detect_version_skew(g, versions)
        assert result == []

    def test_three_component_cluster(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        c3 = _comp("c3")
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        g.add_dependency(Dependency(source_id="c2", target_id="c3"))
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v2", component_id="c2"),
            _api_ver(version="v3", component_id="c3"),
        ]
        result = self.engine.detect_version_skew(g, versions)
        assert len(result) >= 1
        assert len(result[0].component_ids) == 3

    def test_cluster_with_partial_active_versions(self):
        """Covers line 823: cluster where only one component has active version.

        Even though c1, c2, c3 form a cluster via dependencies, if only c1
        has an active version (and c2/c3 are not in active_map because they
        lack ACTIVE versions), the cluster has <2 versioned members and is
        skipped.
        """
        c1 = _comp("c1")
        c2 = _comp("c2")
        c3 = _comp("c3")
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        g.add_dependency(Dependency(source_id="c2", target_id="c3"))
        versions = [
            _api_ver(version="v1", component_id="c1", phase=SunsetPhase.ACTIVE),
            # c2 only has a deprecated version
            _api_ver(version="v1", component_id="c2", phase=SunsetPhase.DEPRECATED),
        ]
        result = self.engine.detect_version_skew(g, versions)
        # c1 is the only component in active_map, cluster has <2 versioned nodes
        assert result == []


# ---------------------------------------------------------------------------
# Engine: generate_migration_plan
# ---------------------------------------------------------------------------


class TestGenerateMigrationPlan:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_no_consumers(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=[])]
        result = self.engine.generate_migration_plan(
            g, versions, [], "c1", "v1", "v2",
        )
        assert result.total_consumers == 0
        assert result.overall_risk_score == 0.0

    def test_single_consumer_with_breaking_change(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["svc-a"])]
        changes = [_change(endpoints=["/users"])]
        result = self.engine.generate_migration_plan(
            g, versions, changes, "c1", "v1", "v2",
        )
        assert result.total_consumers == 1
        assert len(result.migration_risks) == 1
        assert result.migration_risks[0].breaking_changes_count == 1
        assert result.estimated_total_effort_hours > 0

    def test_external_api_consumer_higher_effort(self):
        c1 = _comp("c1")
        ext = _comp("ext", ComponentType.EXTERNAL_API)
        g = _graph(c1, ext)
        versions = [_api_ver(consumers=["ext"])]
        changes = [_change(endpoints=["/api"])]
        result = self.engine.generate_migration_plan(
            g, versions, changes, "c1", "v1", "v2",
        )
        assert len(result.migration_risks) == 1
        risk = result.migration_risks[0]
        assert any("external" in f.lower() for f in risk.risk_factors)

    def test_multiple_consumers_sorted_by_risk(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["svc-a", "svc-b", "svc-c"])]
        changes = [_change(endpoints=["/e1", "/e2"])]
        result = self.engine.generate_migration_plan(
            g, versions, changes, "c1", "v1", "v2",
        )
        assert len(result.migration_risks) == 3

    def test_no_source_version_found(self):
        g = _graph(_comp())
        result = self.engine.generate_migration_plan(
            g, [], [], "c1", "v1", "v2",
        )
        assert result.total_consumers == 0

    def test_phases_generated(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a", "b", "c", "d"])]
        changes = [_change()]
        result = self.engine.generate_migration_plan(
            g, versions, changes, "c1", "v1", "v2",
        )
        assert len(result.phases) > 0
        assert any("Phase 1" in p for p in result.phases)

    def test_phases_large_consumer_base(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a", "b", "c", "d"])]
        changes = [_change()]
        result = self.engine.generate_migration_plan(
            g, versions, changes, "c1", "v1", "v2",
        )
        assert any("canary" in p.lower() for p in result.phases)

    def test_phases_small_consumer_base(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a"])]
        result = self.engine.generate_migration_plan(
            g, versions, [], "c1", "v1", "v2",
        )
        assert not any("canary" in p.lower() for p in result.phases)

    def test_recommendations_high_risk(self):
        g = _graph(_comp())
        versions = [_api_ver(
            consumers=["a", "b", "c", "d", "e", "f"],
            strategy=VersioningStrategy.CUSTOM,
        )]
        changes = [
            _change(endpoints=[f"/e{i}" for i in range(10)]),
            _change(change_type=ChangeType.REMOVAL, endpoints=["/del1"]),
            _change(change_type=ChangeType.BREAKING, endpoints=["/brk1"]),
            _change(change_type=ChangeType.BREAKING, endpoints=["/brk2"]),
        ]
        result = self.engine.generate_migration_plan(
            g, versions, changes, "c1", "v1", "v2",
        )
        assert any("phased" in r.lower() or "support" in r.lower() for r in result.recommendations)

    def test_recommendations_low_risk(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a"])]
        result = self.engine.generate_migration_plan(
            g, versions, [], "c1", "v1", "v2",
        )
        assert any("low" in r.lower() for r in result.recommendations)

    def test_parallel_possible_no_breaking(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a", "b"])]
        result = self.engine.generate_migration_plan(
            g, versions, [], "c1", "v1", "v2",
        )
        assert result.parallel_possible is True

    def test_parallel_impossible_with_breaking(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a", "b"])]
        changes = [_change()]
        result = self.engine.generate_migration_plan(
            g, versions, changes, "c1", "v1", "v2",
        )
        assert result.parallel_possible is False

    def test_overall_risk_level_aggregated(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a"])]
        changes = [_change()]
        result = self.engine.generate_migration_plan(
            g, versions, changes, "c1", "v1", "v2",
        )
        assert isinstance(result.overall_risk_level, MigrationRiskLevel)

    def test_downtime_estimated(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a"])]
        changes = [_change(endpoints=["/e1"])]
        result = self.engine.generate_migration_plan(
            g, versions, changes, "c1", "v1", "v2",
        )
        assert result.estimated_downtime_minutes >= 0


# ---------------------------------------------------------------------------
# Engine: generate_sunset_plan
# ---------------------------------------------------------------------------


class TestGenerateSunsetPlan:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_no_deprecated_versions(self):
        versions = [_api_ver(phase=SunsetPhase.ACTIVE)]
        result = self.engine.generate_sunset_plan(versions)
        assert result.total_versions_to_sunset == 0
        assert result.entries == []

    def test_deprecated_version_entry(self):
        versions = [_api_ver(
            phase=SunsetPhase.DEPRECATED,
            consumers=["svc-a"],
            sunset_date="2099-01-01T00:00:00Z",
        )]
        result = self.engine.generate_sunset_plan(versions)
        assert result.total_versions_to_sunset == 1
        assert result.total_consumers_affected == 1
        entry = result.entries[0]
        assert entry.current_status == SunsetPhase.DEPRECATED
        assert "Migrate" in entry.recommended_action
        assert entry.days_until_sunset is not None
        assert entry.days_until_sunset > 0

    def test_sunset_version_entry(self):
        versions = [_api_ver(
            phase=SunsetPhase.SUNSET,
            consumers=["svc-a", "svc-b"],
        )]
        result = self.engine.generate_sunset_plan(versions)
        assert result.total_versions_to_sunset == 1
        entry = result.entries[0]
        assert entry.current_status == SunsetPhase.SUNSET
        assert "Urgently" in entry.recommended_action

    def test_removed_version_not_included(self):
        versions = [_api_ver(phase=SunsetPhase.REMOVED, consumers=["a"])]
        result = self.engine.generate_sunset_plan(versions)
        assert result.total_versions_to_sunset == 0

    def test_active_version_not_included(self):
        versions = [_api_ver(phase=SunsetPhase.ACTIVE)]
        result = self.engine.generate_sunset_plan(versions)
        assert result.total_versions_to_sunset == 0

    def test_entries_sorted_sunset_before_deprecated(self):
        versions = [
            _api_ver(version="v1", phase=SunsetPhase.DEPRECATED),
            _api_ver(version="v2", phase=SunsetPhase.SUNSET),
        ]
        result = self.engine.generate_sunset_plan(versions)
        assert result.entries[0].current_status == SunsetPhase.SUNSET
        assert result.entries[1].current_status == SunsetPhase.DEPRECATED

    def test_entries_sorted_by_days_until_sunset(self):
        versions = [
            _api_ver(
                version="v1",
                phase=SunsetPhase.DEPRECATED,
                sunset_date="2099-12-01T00:00:00Z",
            ),
            _api_ver(
                version="v2",
                phase=SunsetPhase.DEPRECATED,
                sunset_date="2099-01-01T00:00:00Z",
            ),
        ]
        result = self.engine.generate_sunset_plan(versions)
        # v2 has earlier sunset_date, should come first
        assert result.entries[0].version == "v2"
        assert result.entries[1].version == "v1"

    def test_no_sunset_date_entry(self):
        versions = [_api_ver(phase=SunsetPhase.DEPRECATED)]
        result = self.engine.generate_sunset_plan(versions)
        assert result.entries[0].days_until_sunset is None
        assert result.entries[0].deadline == ""

    def test_multiple_components(self):
        versions = [
            _api_ver(version="v1", component_id="c1", phase=SunsetPhase.DEPRECATED, consumers=["a"]),
            _api_ver(version="v1", component_id="c2", phase=SunsetPhase.SUNSET, consumers=["b", "c"]),
        ]
        result = self.engine.generate_sunset_plan(versions)
        assert result.total_versions_to_sunset == 2
        assert result.total_consumers_affected == 3


# ---------------------------------------------------------------------------
# Engine: analyze_strategy_consistency
# ---------------------------------------------------------------------------


class TestStrategyConsistency:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_empty_versions(self):
        result = self.engine.analyze_strategy_consistency([])
        assert result.consistent is True
        assert result.total_components == 0
        assert result.dominant_strategy is None

    def test_single_component_consistent(self):
        versions = [_api_ver(strategy=VersioningStrategy.URL_PATH)]
        result = self.engine.analyze_strategy_consistency(versions)
        assert result.consistent is True
        assert result.total_components == 1
        assert result.dominant_strategy == "url_path"
        assert result.outliers == []

    def test_same_strategy_consistent(self):
        versions = [
            _api_ver(version="v1", component_id="c1", strategy=VersioningStrategy.HEADER),
            _api_ver(version="v1", component_id="c2", strategy=VersioningStrategy.HEADER),
        ]
        result = self.engine.analyze_strategy_consistency(versions)
        assert result.consistent is True
        assert result.outliers == []

    def test_different_strategies_inconsistent(self):
        versions = [
            _api_ver(version="v1", component_id="c1", strategy=VersioningStrategy.URL_PATH),
            _api_ver(version="v1", component_id="c2", strategy=VersioningStrategy.HEADER),
            _api_ver(version="v1", component_id="c3", strategy=VersioningStrategy.URL_PATH),
        ]
        result = self.engine.analyze_strategy_consistency(versions)
        assert result.consistent is False
        assert result.dominant_strategy == "url_path"
        assert "c2" in result.outliers
        assert result.total_components == 3

    def test_strategy_counts(self):
        versions = [
            _api_ver(version="v1", component_id="c1", strategy=VersioningStrategy.URL_PATH),
            _api_ver(version="v1", component_id="c2", strategy=VersioningStrategy.URL_PATH),
            _api_ver(version="v1", component_id="c3", strategy=VersioningStrategy.CUSTOM),
        ]
        result = self.engine.analyze_strategy_consistency(versions)
        assert result.strategy_counts["url_path"] == 2
        assert result.strategy_counts["custom"] == 1

    def test_multiple_versions_per_component(self):
        """Latest version's strategy per component is used."""
        versions = [
            _api_ver(version="v1", component_id="c1", strategy=VersioningStrategy.URL_PATH),
            _api_ver(version="v2", component_id="c1", strategy=VersioningStrategy.HEADER),
        ]
        result = self.engine.analyze_strategy_consistency(versions)
        # Only 1 component, so consistent
        assert result.total_components == 1


# ---------------------------------------------------------------------------
# Engine: compute_backward_compatibility_score
# ---------------------------------------------------------------------------


class TestBackwardCompatibilityScore:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_no_edges(self):
        g = _graph(_comp())
        result = self.engine.compute_backward_compatibility_score(g, [], [])
        assert result == 1.0

    def test_same_version_full_score(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v1", component_id="c2"),
        ]
        result = self.engine.compute_backward_compatibility_score(g, versions, [])
        assert result == 1.0

    def test_different_versions_no_changes_scored(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v2", component_id="c2"),
        ]
        result = self.engine.compute_backward_compatibility_score(g, versions, [])
        assert 0.0 < result < 1.0

    def test_breaking_changes_lower_score(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v2", component_id="c2"),
        ]
        changes = [BreakingChange(
            source_version="v1",
            target_version="v2",
            component_id="c2",
            change_type=ChangeType.BREAKING,
            description="field removed",
        )]
        result = self.engine.compute_backward_compatibility_score(g, versions, changes)
        assert result < 1.0

    def test_no_active_versions_on_edges(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1", phase=SunsetPhase.DEPRECATED),
            _api_ver(version="v1", component_id="c2"),
        ]
        result = self.engine.compute_backward_compatibility_score(g, versions, [])
        # c1 is deprecated, no active version -> skipped
        assert result == 1.0

    def test_large_gap_low_score(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v10", component_id="c2"),
        ]
        result = self.engine.compute_backward_compatibility_score(g, versions, [])
        assert result <= 0.5

    def test_gap_one_score(self):
        """Covers gap <= 1 branch (line 1181)."""
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1.0", component_id="c1"),
            _api_ver(version="v1.1", component_id="c2"),
        ]
        result = self.engine.compute_backward_compatibility_score(g, versions, [])
        assert result == 0.9

    def test_gap_two_score(self):
        """Covers gap <= 2 branch (line 1183)."""
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1.0", component_id="c1"),
            _api_ver(version="v1.2", component_id="c2"),
        ]
        result = self.engine.compute_backward_compatibility_score(g, versions, [])
        assert result == 0.7

    def test_zero_gap_different_strings(self):
        """Covers gap == 0 branch (line 1179) when version strings differ
        but parse_version_number gives the same tuple (e.g. 'v1' vs 'v1.0')."""
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v1.0", component_id="c2"),
        ]
        result = self.engine.compute_backward_compatibility_score(g, versions, [])
        assert result == 1.0


# ---------------------------------------------------------------------------
# Engine: generate_health_report
# ---------------------------------------------------------------------------


class TestGenerateHealthReport:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_empty_infrastructure(self):
        g = _graph()
        result = self.engine.generate_health_report(g, [], [])
        assert result.overall_versioning_health == 100.0
        assert result.total_breaking_changes == 0

    def test_healthy_active_versions(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1", phase=SunsetPhase.ACTIVE),
            _api_ver(version="v2", phase=SunsetPhase.ACTIVE),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert result.overall_versioning_health > 50.0
        assert result.deprecated_versions_count == 0

    def test_deprecated_version_report(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1", phase=SunsetPhase.DEPRECATED, consumers=["svc-a"]),
            _api_ver(version="v2", phase=SunsetPhase.ACTIVE),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert result.deprecated_versions_count == 1
        assert len(result.sunset_impacts) == 1

    def test_breaking_changes_reduce_health(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a"])]
        changes = [
            _change(change_type=ChangeType.BREAKING),
            _change(change_type=ChangeType.BREAKING, description="another"),
        ]
        result = self.engine.generate_health_report(g, versions, changes)
        assert result.overall_versioning_health < 100.0
        assert result.total_breaking_changes == 2

    def test_removed_version_with_consumers_penalty(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1", phase=SunsetPhase.REMOVED, consumers=["svc-a"]),
            _api_ver(version="v2", phase=SunsetPhase.ACTIVE),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert result.overall_versioning_health < 100.0

    def test_sunset_with_consumers_penalty(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1", phase=SunsetPhase.SUNSET, consumers=["svc-a"]),
            _api_ver(version="v2", phase=SunsetPhase.ACTIVE),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert result.overall_versioning_health < 100.0

    def test_migration_plans_generated_for_deprecated(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1", phase=SunsetPhase.DEPRECATED, consumers=["svc-a"]),
            _api_ver(version="v2", phase=SunsetPhase.ACTIVE),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert len(result.migration_plans) >= 1

    def test_custom_policies_in_report(self):
        g = _graph(_comp())
        versions = [_api_ver(phase=SunsetPhase.DEPRECATED, consumers=["svc-a"])]
        policies = [SunsetPolicy(
            component_id="c1",
            version="v1",
            phase=SunsetPhase.DEPRECATED,
            active_consumers=1,
        )]
        result = self.engine.generate_health_report(g, versions, [], policies)
        assert len(result.sunset_policies) == 1

    def test_at_risk_consumers_counted(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1", phase=SunsetPhase.DEPRECATED, consumers=["a", "b"]),
            _api_ver(version="v2", phase=SunsetPhase.ACTIVE, consumers=["a"]),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert result.at_risk_consumers >= 1

    def test_recommendations_high_breaking_changes(self):
        g = _graph(_comp())
        versions = [_api_ver(consumers=["a"])]
        changes = [
            _change(change_type=ChangeType.BREAKING, description=f"break-{i}")
            for i in range(6)
        ]
        result = self.engine.generate_health_report(g, versions, changes)
        assert any("semantic" in r.lower() for r in result.recommendations)

    def test_recommendations_many_active_versions(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version=f"v{i}", phase=SunsetPhase.ACTIVE)
            for i in range(7)
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert any("consolidat" in r.lower() for r in result.recommendations)

    def test_recommendations_healthy(self):
        g = _graph(_comp())
        versions = [_api_ver()]
        result = self.engine.generate_health_report(g, versions, [])
        assert any("good" in r.lower() or "no action" in r.lower() for r in result.recommendations)

    def test_sunset_plan_in_report(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1", phase=SunsetPhase.DEPRECATED, consumers=["a"]),
            _api_ver(version="v2", phase=SunsetPhase.ACTIVE),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert result.sunset_plan is not None
        assert result.sunset_plan.total_versions_to_sunset >= 1

    def test_strategy_consistency_in_report(self):
        g = _graph(_comp())
        versions = [_api_ver()]
        result = self.engine.generate_health_report(g, versions, [])
        assert result.strategy_consistency is not None

    def test_backward_compatibility_score_in_report(self):
        g = _graph(_comp())
        versions = [_api_ver()]
        result = self.engine.generate_health_report(g, versions, [])
        assert 0.0 <= result.backward_compatibility_score <= 1.0

    def test_component_version_map_in_report(self):
        g = _graph(_comp())
        versions = [
            _api_ver(version="v1"),
            _api_ver(version="v2"),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert "c1" in result.component_version_map
        assert "v1" in result.component_version_map["c1"]
        assert "v2" in result.component_version_map["c1"]

    def test_skew_risks_in_report(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v5", component_id="c2"),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert result.skew_risks is not None

    def test_inconsistent_strategy_recommendation(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        versions = [
            _api_ver(version="v1", component_id="c1", strategy=VersioningStrategy.URL_PATH),
            _api_ver(version="v1", component_id="c2", strategy=VersioningStrategy.CUSTOM),
        ]
        result = self.engine.generate_health_report(g, versions, [])
        assert any("inconsistent" in r.lower() or "deviate" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Engine: private methods coverage
# ---------------------------------------------------------------------------


class TestPrivateMethods:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_build_version_map(self):
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v2", component_id="c1"),
        ]
        vmap = self.engine._build_version_map(versions)
        assert ("c1", "v1") in vmap
        assert ("c1", "v2") in vmap

    def test_determine_compatibility_no_changes(self):
        result = self.engine._determine_compatibility("v1", "v2", [])
        assert result == CompatibilityLevel.FULL

    def test_determine_compatibility_breaking(self):
        changes = [_change(source="v1", target="v2", change_type=ChangeType.BREAKING)]
        result = self.engine._determine_compatibility("v1", "v2", changes)
        assert result == CompatibilityLevel.NONE

    def test_determine_compatibility_reverse_direction(self):
        changes = [_change(source="v2", target="v1", change_type=ChangeType.BREAKING)]
        result = self.engine._determine_compatibility("v1", "v2", changes)
        assert result == CompatibilityLevel.NONE

    def test_determine_compatibility_deprecation(self):
        changes = [_change(source="v1", target="v2", change_type=ChangeType.DEPRECATION)]
        result = self.engine._determine_compatibility("v1", "v2", changes)
        assert result == CompatibilityLevel.BACKWARD

    def test_determine_compatibility_addition(self):
        changes = [_change(source="v1", target="v2", change_type=ChangeType.ADDITION)]
        result = self.engine._determine_compatibility("v1", "v2", changes)
        assert result == CompatibilityLevel.FORWARD

    def test_generate_default_policies_skip_active(self):
        versions = [
            _api_ver(phase=SunsetPhase.ACTIVE),
            _api_ver(version="v2", phase=SunsetPhase.DEPRECATED),
        ]
        policies = self.engine._generate_default_policies(versions)
        assert len(policies) == 1
        assert policies[0].version == "v2"

    def test_find_newer_versions(self):
        versions = [
            _api_ver(version="v1"),
            _api_ver(version="v2"),
            _api_ver(version="v3"),
        ]
        newer = self.engine._find_newer_versions(versions, "c1", "v1")
        assert len(newer) == 2

    def test_find_newer_versions_none_newer(self):
        versions = [_api_ver(version="v1")]
        newer = self.engine._find_newer_versions(versions, "c1", "v1")
        assert newer == []

    def test_find_newer_versions_different_component(self):
        versions = [
            _api_ver(version="v1", component_id="c1"),
            _api_ver(version="v2", component_id="c2"),
        ]
        newer = self.engine._find_newer_versions(versions, "c1", "v1")
        assert newer == []

    def test_find_version_clusters_empty(self):
        g = _graph()
        clusters = self.engine._find_version_clusters(g, {})
        assert clusters == []

    def test_find_version_clusters_single_component(self):
        g = _graph(_comp("c1"))
        clusters = self.engine._find_version_clusters(g, {"c1": "v1"})
        assert clusters == []  # need at least 2 in a cluster

    def test_find_version_clusters_connected(self):
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        clusters = self.engine._find_version_clusters(g, {"c1": "v1", "c2": "v2"})
        assert len(clusters) == 1
        assert {"c1", "c2"} == clusters[0]

    def test_find_version_clusters_not_in_graph(self):
        g = _graph(_comp("c1"))
        clusters = self.engine._find_version_clusters(g, {"c1": "v1", "c999": "v2"})
        # c999 not in graph, so get_component returns None, skipped
        assert clusters == []

    def test_find_version_clusters_bfs_revisit(self):
        """Covers the BFS 'continue' on already-visited node (line 1410)
        and dependent traversal (line 1419) by creating a cycle."""
        c1 = _comp("c1")
        c2 = _comp("c2")
        c3 = _comp("c3")
        g = _graph(c1, c2, c3)
        # Create cycle: c1->c2->c3->c1
        g.add_dependency(Dependency(source_id="c1", target_id="c2"))
        g.add_dependency(Dependency(source_id="c2", target_id="c3"))
        g.add_dependency(Dependency(source_id="c3", target_id="c1"))
        clusters = self.engine._find_version_clusters(
            g, {"c1": "v1", "c2": "v2", "c3": "v3"}
        )
        assert len(clusters) == 1
        assert clusters[0] == {"c1", "c2", "c3"}

    def test_migration_steps_with_breaking(self):
        steps = self.engine._migration_steps("v1", "v2", 3)
        assert any("breaking" in s.lower() for s in steps)
        assert any("staging" in s.lower() for s in steps)

    def test_migration_steps_no_breaking(self):
        steps = self.engine._migration_steps("v1", "v2", 0)
        assert not any("breaking" in s.lower() for s in steps)

    def test_migration_phases_large_group(self):
        phases = self.engine._migration_phases(5, 2)
        assert any("canary" in p.lower() for p in phases)

    def test_migration_phases_small_group(self):
        phases = self.engine._migration_phases(2, 0)
        assert not any("canary" in p.lower() for p in phases)

    def test_sunset_recommendations_not_migrated(self):
        recs = self.engine._sunset_recommendations(None, 3, 5, 40.0)
        assert any("remaining" in r.lower() for r in recs)
        assert any("extend" in r.lower() for r in recs)

    def test_sunset_recommendations_active_version(self):
        v = _api_ver(phase=SunsetPhase.ACTIVE)
        recs = self.engine._sunset_recommendations(v, 0, 1, 100.0)
        assert any("DEPRECATED" in r for r in recs)

    def test_sunset_recommendations_all_migrated(self):
        recs = self.engine._sunset_recommendations(None, 0, 5, 100.0)
        assert any("safe" in r.lower() for r in recs)

    def test_sunset_recommendations_no_consumers(self):
        recs = self.engine._sunset_recommendations(None, 0, 0, 100.0)
        assert any("safely removed" in r.lower() for r in recs)

    def test_compute_versioning_health_empty(self):
        score = self.engine._compute_versioning_health([], [], [])
        assert score == 100.0

    def test_compute_versioning_health_many_breaking(self):
        versions = [_api_ver()]
        changes = [
            _change(change_type=ChangeType.BREAKING, description=f"c{i}")
            for i in range(10)
        ]
        score = self.engine._compute_versioning_health(versions, changes, [])
        assert score < 100.0

    def test_compute_versioning_health_violations(self):
        versions = [_api_ver()]
        policies = [SunsetPolicy(
            component_id="c1",
            version="v1",
            phase=SunsetPhase.DEPRECATED,
            violations=["violation1", "violation2"],
        )]
        score = self.engine._compute_versioning_health(versions, [], policies)
        assert score < 100.0

    def test_compute_versioning_health_floor_zero(self):
        versions = [
            _api_ver(version=f"v{i}", phase=SunsetPhase.REMOVED, consumers=["a"])
            for i in range(5)
        ]
        changes = [
            _change(change_type=ChangeType.BREAKING, description=f"c{i}")
            for i in range(20)
        ]
        policies = [SunsetPolicy(
            component_id="c1",
            version="v1",
            phase=SunsetPhase.REMOVED,
            violations=[f"v{i}" for i in range(20)],
        )]
        score = self.engine._compute_versioning_health(versions, changes, policies)
        assert score == 0.0

    def test_health_recommendations_violations(self):
        policies = [SunsetPolicy(
            component_id="c1",
            version="v1",
            phase=SunsetPhase.DEPRECATED,
            violations=["a"],
        )]
        sr = StrategyConsistencyReport()
        recs = self.engine._health_recommendations([], [], policies, [], sr)
        assert any("violation" in r.lower() for r in recs)

    def test_health_recommendations_high_outage_risk(self):
        impacts = [SunsetImpact(
            component_id="c1",
            version="v1",
            estimated_outage_risk=0.8,
        )]
        sr = StrategyConsistencyReport()
        recs = self.engine._health_recommendations([], [], [], impacts, sr)
        assert any("outage" in r.lower() for r in recs)

    def test_health_recommendations_removed_with_consumers(self):
        versions = [_api_ver(phase=SunsetPhase.REMOVED, consumers=["a"])]
        sr = StrategyConsistencyReport()
        recs = self.engine._health_recommendations(versions, [], [], [], sr)
        assert any("immediate" in r.lower() for r in recs)

    def test_health_recommendations_inconsistent_strategy(self):
        sr = StrategyConsistencyReport(
            consistent=False,
            outliers=["c2"],
            dominant_strategy="url_path",
        )
        recs = self.engine._health_recommendations([], [], [], [], sr)
        assert any("inconsistent" in r.lower() or "deviate" in r.lower() for r in recs)

    def test_health_recommendations_no_issues(self):
        sr = StrategyConsistencyReport()
        recs = self.engine._health_recommendations([], [], [], [], sr)
        assert any("good" in r.lower() or "no action" in r.lower() for r in recs)

    def test_migration_recommendations_many_breaking(self):
        recs = self.engine._migration_recommendations([], 5, 1)
        assert any("shim" in r.lower() for r in recs)

    def test_migration_recommendations_large_consumer_base(self):
        recs = self.engine._migration_recommendations([], 0, 6)
        assert any("phased" in r.lower() for r in recs)

    def test_migration_recommendations_high_risk_consumers(self):
        risks = [MigrationRisk(
            consumer_id="a",
            source_version="v1",
            target_version="v2",
            risk_score=60.0,
        )]
        recs = self.engine._migration_recommendations(risks, 0, 1)
        assert any("support" in r.lower() for r in recs)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def setup_method(self):
        self.engine = ApiVersioningImpactEngine()

    def test_empty_everything(self):
        g = _graph()
        report = self.engine.generate_health_report(g, [], [])
        assert report.overall_versioning_health == 100.0
        assert report.total_breaking_changes == 0
        assert report.deprecated_versions_count == 0

    def test_version_with_no_component_in_graph(self):
        g = _graph()  # empty graph
        versions = [_api_ver(version="v1", component_id="nonexistent")]
        result = self.engine.analyze_breaking_changes(g, versions, [])
        assert result == []

    def test_change_for_nonexistent_version(self):
        g = _graph(_comp())
        changes = [_change(source="v99", target="v100", component_id="c1")]
        result = self.engine.analyze_breaking_changes(g, [], changes)
        assert len(result) == 1

    def test_sunset_impact_version_not_found(self):
        g = _graph(_comp())
        versions = [_api_ver(version="v2")]
        result = self.engine.simulate_sunset_impact(g, versions, "c1", "v999")
        assert result.total_consumers == 0

    def test_compatibility_matrix_with_all_change_types(self):
        versions = [_api_ver(version="v1"), _api_ver(version="v2")]
        for ct in ChangeType:
            changes = [_change(source="v1", target="v2", change_type=ct)]
            result = self.engine.compute_compatibility_matrix(versions, changes)
            assert len(result) == 1
            # Matrix should contain valid CompatibilityLevel
            level = result[0].matrix["v1"]["v2"]
            assert isinstance(level, CompatibilityLevel)

    def test_generate_default_policies_with_deprecation_date(self):
        versions = [_api_ver(
            version="v1",
            phase=SunsetPhase.DEPRECATED,
            release_date="2025-01-01",
        )]
        policies = self.engine._generate_default_policies(versions)
        assert len(policies) == 1
        # deprecation_date should fall back to release_date
        assert policies[0].deprecation_date == "2025-01-01"

    def test_many_versions_health_report(self):
        """Stress test with many versions, changes, and components."""
        comps = [_comp(f"c{i}") for i in range(5)]
        g = _graph(*comps)
        for i in range(4):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{i+1}"))

        versions = []
        for i in range(5):
            versions.append(_api_ver(
                version="v1",
                component_id=f"c{i}",
                consumers=[f"c{(i+1) % 5}"],
            ))
            versions.append(_api_ver(
                version="v2",
                component_id=f"c{i}",
                phase=SunsetPhase.DEPRECATED,
                consumers=[f"c{(i+2) % 5}"],
            ))

        changes = [
            _change(component_id=f"c{i}", source="v1", target="v2")
            for i in range(5)
        ]

        report = self.engine.generate_health_report(g, versions, changes)
        assert report.overall_versioning_health >= 0
        assert report.overall_versioning_health <= 100
        assert report.sunset_plan is not None
        assert report.strategy_consistency is not None
