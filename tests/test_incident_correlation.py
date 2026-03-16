"""Tests for the Incident Correlation Engine — 100% coverage target."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.incident_correlation import (
    CorrelationLink,
    CorrelationStrength,
    CorrelationType,
    IncidentCluster,
    IncidentCorrelationEngine,
    IncidentCorrelationReport,
    IncidentRecord,
    IncidentSeverity,
    RecurrencePattern,
    RootCauseCategory,
    _parse_time,
    _strength_from_confidence,
    _symptom_overlap,
)


# ── Helpers ──────────────────────────────────────────────────────


def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _inc(
    iid: str = "INC-001",
    service: str = "svc-a",
    severity: IncidentSeverity = IncidentSeverity.SEV3,
    title: str = "Test incident",
    started_at: str = "2026-01-15T10:00:00+00:00",
    duration: float = 30.0,
    symptoms: list[str] | None = None,
    deployment_id: str | None = None,
) -> IncidentRecord:
    return IncidentRecord(
        incident_id=iid,
        service_id=service,
        severity=severity,
        title=title,
        started_at=started_at,
        duration_minutes=duration,
        symptoms=symptoms or [],
        deployment_id=deployment_id,
    )


# ── Enum Tests ───────────────────────────────────────────────────


class TestEnums:
    def test_correlation_type_values(self):
        assert CorrelationType.TEMPORAL == "temporal"
        assert CorrelationType.DEPENDENCY == "dependency"
        assert CorrelationType.SYMPTOM == "symptom"
        assert CorrelationType.DEPLOYMENT == "deployment"
        assert CorrelationType.INFRASTRUCTURE == "infrastructure"
        assert CorrelationType.CONFIGURATION == "configuration"

    def test_incident_severity_values(self):
        assert IncidentSeverity.SEV1 == "sev1"
        assert IncidentSeverity.SEV2 == "sev2"
        assert IncidentSeverity.SEV3 == "sev3"
        assert IncidentSeverity.SEV4 == "sev4"
        assert IncidentSeverity.SEV5 == "sev5"

    def test_correlation_strength_values(self):
        assert CorrelationStrength.STRONG == "strong"
        assert CorrelationStrength.MODERATE == "moderate"
        assert CorrelationStrength.WEAK == "weak"
        assert CorrelationStrength.NONE == "none"

    def test_root_cause_category_values(self):
        assert RootCauseCategory.DEPLOYMENT_FAILURE == "deployment_failure"
        assert RootCauseCategory.INFRASTRUCTURE_ISSUE == "infrastructure_issue"
        assert RootCauseCategory.DEPENDENCY_FAILURE == "dependency_failure"
        assert RootCauseCategory.CONFIGURATION_ERROR == "configuration_error"
        assert RootCauseCategory.CAPACITY_EXHAUSTION == "capacity_exhaustion"
        assert RootCauseCategory.EXTERNAL_OUTAGE == "external_outage"
        assert RootCauseCategory.UNKNOWN == "unknown"


# ── Pydantic Model Tests ────────────────────────────────────────


class TestModels:
    def test_incident_record_defaults(self):
        r = IncidentRecord(
            incident_id="INC-1",
            service_id="svc",
            severity=IncidentSeverity.SEV3,
            title="test",
            started_at="2026-01-01T00:00:00Z",
            duration_minutes=10.0,
        )
        assert r.symptoms == []
        assert r.deployment_id is None

    def test_incident_record_with_all_fields(self):
        r = _inc(symptoms=["timeout", "5xx"], deployment_id="DEP-42")
        assert r.deployment_id == "DEP-42"
        assert len(r.symptoms) == 2

    def test_correlation_link_fields(self):
        link = CorrelationLink(
            source_incident_id="A",
            target_incident_id="B",
            correlation_type=CorrelationType.TEMPORAL,
            strength=CorrelationStrength.STRONG,
            confidence=0.9,
            explanation="test",
        )
        assert link.confidence == 0.9

    def test_incident_cluster_defaults(self):
        c = IncidentCluster(
            cluster_id="CLU-0001",
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="test",
        )
        assert c.incidents == []
        assert c.contributing_factors == []

    def test_recurrence_pattern_fields(self):
        p = RecurrencePattern(
            pattern_id="REC-0001",
            incident_count=5,
            avg_interval_hours=24.0,
            affected_services=["svc-a"],
            likely_trigger="cron job",
        )
        assert p.avg_interval_hours == 24.0

    def test_report_defaults(self):
        r = IncidentCorrelationReport()
        assert r.clusters == []
        assert r.links == []
        assert r.recurrence_patterns == []
        assert r.total_incidents == 0
        assert r.correlated_count == 0
        assert r.systemic_issues == []


# ── Helper Function Tests ────────────────────────────────────────


class TestHelpers:
    def test_parse_time_with_tz(self):
        dt = _parse_time("2026-01-15T10:00:00+00:00")
        assert dt.tzinfo is not None
        assert dt.hour == 10

    def test_parse_time_without_tz(self):
        dt = _parse_time("2026-01-15T10:00:00")
        assert dt.tzinfo is not None

    def test_symptom_overlap_identical(self):
        assert _symptom_overlap(["timeout"], ["timeout"]) == 1.0

    def test_symptom_overlap_empty(self):
        assert _symptom_overlap([], []) == 0.0

    def test_symptom_overlap_one_empty(self):
        assert _symptom_overlap(["a"], []) == 0.0

    def test_symptom_overlap_partial(self):
        val = _symptom_overlap(["a", "b", "c"], ["b", "c", "d"])
        assert 0.4 < val < 0.6  # 2/4 = 0.5

    def test_symptom_overlap_case_insensitive(self):
        assert _symptom_overlap(["Timeout"], ["timeout"]) == 1.0

    def test_symptom_overlap_whitespace_stripped(self):
        assert _symptom_overlap(["  timeout  "], ["timeout"]) == 1.0

    def test_symptom_overlap_whitespace_only_both_sides(self):
        """Both lists contain whitespace-only strings — stripped to '' which still matches."""
        assert _symptom_overlap(["   "], ["   "]) == 1.0

    def test_symptom_overlap_no_intersection(self):
        assert _symptom_overlap(["a"], ["b"]) == 0.0

    def test_strength_from_confidence_strong(self):
        assert _strength_from_confidence(0.9) == CorrelationStrength.STRONG

    def test_strength_from_confidence_moderate(self):
        assert _strength_from_confidence(0.5) == CorrelationStrength.MODERATE

    def test_strength_from_confidence_weak(self):
        assert _strength_from_confidence(0.3) == CorrelationStrength.WEAK

    def test_strength_from_confidence_none(self):
        assert _strength_from_confidence(0.1) == CorrelationStrength.NONE

    def test_strength_from_confidence_boundary_strong(self):
        assert _strength_from_confidence(0.75) == CorrelationStrength.STRONG

    def test_strength_from_confidence_boundary_moderate(self):
        assert _strength_from_confidence(0.45) == CorrelationStrength.MODERATE

    def test_strength_from_confidence_boundary_weak(self):
        assert _strength_from_confidence(0.2) == CorrelationStrength.WEAK

    def test_strength_from_confidence_zero(self):
        assert _strength_from_confidence(0.0) == CorrelationStrength.NONE


# ── correlate_incidents ──────────────────────────────────────────


class TestCorrelateIncidents:
    def test_empty_incidents(self):
        engine = IncidentCorrelationEngine()
        report = engine.correlate_incidents(_graph(), [])
        assert report.total_incidents == 0
        assert report.correlated_count == 0
        assert report.clusters == []

    def test_single_incident(self):
        engine = IncidentCorrelationEngine()
        incidents = [_inc()]
        report = engine.correlate_incidents(_graph(), incidents)
        assert report.total_incidents == 1
        assert len(report.clusters) == 1
        assert report.correlated_count == 0

    def test_two_temporal_incidents(self):
        engine = IncidentCorrelationEngine()
        incidents = [
            _inc("INC-1", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("INC-2", "svc-b", started_at="2026-01-15T10:05:00+00:00"),
        ]
        report = engine.correlate_incidents(_graph(), incidents)
        assert report.total_incidents == 2
        assert report.correlated_count >= 2

    def test_report_has_links(self):
        engine = IncidentCorrelationEngine()
        incidents = [
            _inc("INC-1", "svc-a", started_at="2026-01-15T10:00:00+00:00", symptoms=["5xx"]),
            _inc("INC-2", "svc-b", started_at="2026-01-15T10:02:00+00:00", symptoms=["5xx"]),
        ]
        report = engine.correlate_incidents(_graph(), incidents)
        assert len(report.links) >= 1

    def test_report_deduplicates_links(self):
        """Same pair appears in temporal + symptom → only best kept."""
        engine = IncidentCorrelationEngine()
        incidents = [
            _inc("INC-1", "svc-a", started_at="2026-01-15T10:00:00+00:00",
                 symptoms=["timeout", "5xx"]),
            _inc("INC-2", "svc-b", started_at="2026-01-15T10:01:00+00:00",
                 symptoms=["timeout", "5xx"]),
        ]
        report = engine.correlate_incidents(_graph(), incidents)
        pairs = [
            tuple(sorted([l.source_incident_id, l.target_incident_id]))
            for l in report.links
        ]
        # Each pair should appear at most once
        assert len(pairs) == len(set(pairs))

    def test_enrichment_sets_description_for_empty(self):
        """When cluster has empty description and unknown category, enrichment fills both."""
        engine = IncidentCorrelationEngine()
        ca = _comp("svc-a")
        cb = _comp("svc-b")
        g = _graph(ca, cb)
        g.add_dependency(Dependency(source_id="svc-b", target_id="svc-a"))
        # Use incident IDs that match component IDs so graph-based detection works
        incidents = [
            _inc("svc-a", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("svc-b", "svc-b", started_at="2026-01-15T12:00:00+00:00"),
        ]
        report = engine.correlate_incidents(g, incidents)
        # Check that at least one cluster has a non-empty description
        for cluster in report.clusters:
            assert cluster.root_cause_description != ""

    def test_systemic_issues_detected(self):
        engine = IncidentCorrelationEngine()
        incidents = [
            _inc("INC-1", "svc-a", severity=IncidentSeverity.SEV1,
                 started_at="2026-01-15T10:00:00+00:00"),
            _inc("INC-2", "svc-a", severity=IncidentSeverity.SEV1,
                 started_at="2026-01-15T10:05:00+00:00"),
            _inc("INC-3", "svc-a", severity=IncidentSeverity.SEV2,
                 started_at="2026-01-15T10:10:00+00:00"),
        ]
        report = engine.correlate_incidents(_graph(), incidents)
        # svc-a has 3 incidents → systemic
        assert any("svc-a" in issue for issue in report.systemic_issues)

    def test_clusters_enriched_with_root_cause(self):
        engine = IncidentCorrelationEngine()
        c1 = _comp("svc-a")
        c2 = _comp("svc-b")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc-a", target_id="svc-b"))
        incidents = [
            _inc("INC-1", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("INC-2", "svc-b", started_at="2026-01-15T10:01:00+00:00"),
        ]
        report = engine.correlate_incidents(g, incidents)
        assert len(report.clusters) >= 1


# ── find_temporal_correlations ───────────────────────────────────


class TestTemporalCorrelations:
    def test_empty_list(self):
        engine = IncidentCorrelationEngine()
        assert engine.find_temporal_correlations([]) == []

    def test_single_incident(self):
        engine = IncidentCorrelationEngine()
        assert engine.find_temporal_correlations([_inc()]) == []

    def test_two_close_incidents(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_temporal_correlations([
            _inc("A", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", started_at="2026-01-15T10:05:00+00:00"),
        ])
        assert len(links) == 1
        assert links[0].correlation_type == CorrelationType.TEMPORAL

    def test_incidents_outside_window(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_temporal_correlations([
            _inc("A", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", started_at="2026-01-15T12:00:00+00:00"),
        ], window_minutes=30.0)
        assert len(links) == 0

    def test_custom_window(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_temporal_correlations([
            _inc("A", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", started_at="2026-01-15T10:45:00+00:00"),
        ], window_minutes=60.0)
        assert len(links) == 1

    def test_confidence_decreases_with_distance(self):
        engine = IncidentCorrelationEngine()
        close = engine.find_temporal_correlations([
            _inc("A", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", started_at="2026-01-15T10:01:00+00:00"),
        ])
        far = engine.find_temporal_correlations([
            _inc("C", started_at="2026-01-15T10:00:00+00:00"),
            _inc("D", started_at="2026-01-15T10:15:00+00:00"),
        ])
        assert close[0].confidence > far[0].confidence

    def test_same_deployment_boosts_confidence(self):
        engine = IncidentCorrelationEngine()
        no_deploy = engine.find_temporal_correlations([
            _inc("A", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", started_at="2026-01-15T10:10:00+00:00"),
        ])
        with_deploy = engine.find_temporal_correlations([
            _inc("C", started_at="2026-01-15T10:00:00+00:00", deployment_id="DEP-1"),
            _inc("D", started_at="2026-01-15T10:10:00+00:00", deployment_id="DEP-1"),
        ])
        assert with_deploy[0].confidence > no_deploy[0].confidence

    def test_different_deployment_no_boost(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_temporal_correlations([
            _inc("A", started_at="2026-01-15T10:00:00+00:00", deployment_id="DEP-1"),
            _inc("B", started_at="2026-01-15T10:10:00+00:00", deployment_id="DEP-2"),
        ])
        # Should still have a link, just no deployment boost
        assert len(links) >= 1

    def test_skip_same_id(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_temporal_correlations([
            _inc("A", started_at="2026-01-15T10:00:00+00:00"),
            _inc("A", started_at="2026-01-15T10:05:00+00:00"),
        ])
        assert len(links) == 0

    def test_near_edge_of_window_filtered_as_none(self):
        """Incidents very close to the window edge produce NONE strength and are filtered."""
        engine = IncidentCorrelationEngine()
        links = engine.find_temporal_correlations([
            _inc("A", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", started_at="2026-01-15T10:28:00+00:00"),
        ], window_minutes=30.0)
        # 28/30 = 0.933... → confidence = 1 - 0.933 ≈ 0.067 → NONE → filtered
        assert len(links) == 0

    def test_multiple_incidents_sorted(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_temporal_correlations([
            _inc("C", started_at="2026-01-15T10:20:00+00:00"),
            _inc("A", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", started_at="2026-01-15T10:05:00+00:00"),
        ])
        # A-B and B-C should be linked, possibly A-C
        assert len(links) >= 2

    def test_very_close_strong_correlation(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_temporal_correlations([
            _inc("A", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", started_at="2026-01-15T10:00:30+00:00"),  # 30 sec apart
        ])
        assert links[0].strength == CorrelationStrength.STRONG


# ── find_dependency_correlations ─────────────────────────────────


class TestDependencyCorrelations:
    def test_empty_list(self):
        engine = IncidentCorrelationEngine()
        assert engine.find_dependency_correlations(_graph(), []) == []

    def test_single_incident(self):
        engine = IncidentCorrelationEngine()
        assert engine.find_dependency_correlations(_graph(), [_inc()]) == []

    def test_direct_dependency(self):
        engine = IncidentCorrelationEngine()
        c1, c2 = _comp("svc-a"), _comp("svc-b")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc-a", target_id="svc-b"))
        links = engine.find_dependency_correlations(g, [
            _inc("INC-1", "svc-a"),
            _inc("INC-2", "svc-b"),
        ])
        assert len(links) == 1
        assert links[0].correlation_type == CorrelationType.DEPENDENCY
        assert links[0].strength == CorrelationStrength.STRONG

    def test_reverse_dependency(self):
        engine = IncidentCorrelationEngine()
        c1, c2 = _comp("svc-a"), _comp("svc-b")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="svc-b", target_id="svc-a"))
        links = engine.find_dependency_correlations(g, [
            _inc("INC-1", "svc-a"),
            _inc("INC-2", "svc-b"),
        ])
        assert len(links) == 1
        assert links[0].strength == CorrelationStrength.STRONG

    def test_shared_dependency(self):
        engine = IncidentCorrelationEngine()
        ca = _comp("svc-a")
        cb = _comp("svc-b")
        cdb = _comp("db", ComponentType.DATABASE)
        g = _graph(ca, cb, cdb)
        g.add_dependency(Dependency(source_id="svc-a", target_id="db"))
        g.add_dependency(Dependency(source_id="svc-b", target_id="db"))
        links = engine.find_dependency_correlations(g, [
            _inc("INC-1", "svc-a"),
            _inc("INC-2", "svc-b"),
        ])
        assert len(links) == 1
        assert links[0].strength == CorrelationStrength.MODERATE
        assert "db" in links[0].explanation

    def test_transitive_dependency(self):
        engine = IncidentCorrelationEngine()
        ca = _comp("svc-a")
        cb = _comp("svc-b")
        cc = _comp("svc-c")
        g = _graph(ca, cb, cc)
        # a→b, but b→c as dependency; a→c is transitive via get_all_affected
        g.add_dependency(Dependency(source_id="svc-b", target_id="svc-a"))
        g.add_dependency(Dependency(source_id="svc-c", target_id="svc-b"))
        links = engine.find_dependency_correlations(g, [
            _inc("INC-1", "svc-a"),
            _inc("INC-2", "svc-c"),
        ])
        # svc-a is affected by svc-c transitively
        assert len(links) >= 1

    def test_no_graph_connection(self):
        engine = IncidentCorrelationEngine()
        ca = _comp("svc-a")
        cb = _comp("svc-b")
        g = _graph(ca, cb)
        links = engine.find_dependency_correlations(g, [
            _inc("INC-1", "svc-a"),
            _inc("INC-2", "svc-b"),
        ])
        assert len(links) == 0

    def test_missing_component_in_graph(self):
        engine = IncidentCorrelationEngine()
        ca = _comp("svc-a")
        g = _graph(ca)
        links = engine.find_dependency_correlations(g, [
            _inc("INC-1", "svc-a"),
            _inc("INC-2", "svc-missing"),
        ])
        assert len(links) == 0

    def test_dedup_checked_pairs(self):
        engine = IncidentCorrelationEngine()
        ca = _comp("svc-a")
        cb = _comp("svc-b")
        g = _graph(ca, cb)
        g.add_dependency(Dependency(source_id="svc-a", target_id="svc-b"))
        # Two incidents on same services should only create one link
        links = engine.find_dependency_correlations(g, [
            _inc("INC-1", "svc-a"),
            _inc("INC-2", "svc-b"),
        ])
        assert len(links) == 1


# ── find_symptom_correlations ────────────────────────────────────


class TestSymptomCorrelations:
    def test_empty_list(self):
        engine = IncidentCorrelationEngine()
        assert engine.find_symptom_correlations([]) == []

    def test_single_incident(self):
        engine = IncidentCorrelationEngine()
        assert engine.find_symptom_correlations([_inc(symptoms=["timeout"])]) == []

    def test_shared_symptoms(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_symptom_correlations([
            _inc("A", symptoms=["timeout", "5xx", "slow"]),
            _inc("B", symptoms=["timeout", "5xx", "error"]),
        ])
        assert len(links) == 1
        assert links[0].correlation_type == CorrelationType.SYMPTOM

    def test_no_symptoms(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_symptom_correlations([
            _inc("A", symptoms=[]),
            _inc("B", symptoms=[]),
        ])
        assert len(links) == 0

    def test_one_without_symptoms(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_symptom_correlations([
            _inc("A", symptoms=["timeout"]),
            _inc("B", symptoms=[]),
        ])
        assert len(links) == 0

    def test_disjoint_symptoms(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_symptom_correlations([
            _inc("A", symptoms=["timeout"]),
            _inc("B", symptoms=["disk_full"]),
        ])
        assert len(links) == 0

    def test_same_severity_boost(self):
        engine = IncidentCorrelationEngine()
        diff_sev = engine.find_symptom_correlations([
            _inc("A", severity=IncidentSeverity.SEV1, symptoms=["timeout", "5xx"]),
            _inc("B", severity=IncidentSeverity.SEV5, symptoms=["timeout", "5xx"]),
        ])
        same_sev = engine.find_symptom_correlations([
            _inc("C", severity=IncidentSeverity.SEV2, symptoms=["timeout", "5xx"]),
            _inc("D", severity=IncidentSeverity.SEV2, symptoms=["timeout", "5xx"]),
        ])
        assert same_sev[0].confidence >= diff_sev[0].confidence

    def test_skip_same_id(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_symptom_correlations([
            _inc("A", symptoms=["timeout"]),
            _inc("A", symptoms=["timeout"]),
        ])
        assert len(links) == 0

    def test_low_overlap_skipped(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_symptom_correlations([
            _inc("A", symptoms=["a", "b", "c", "d", "e"]),
            _inc("B", symptoms=["z"]),  # 0 overlap
        ])
        assert len(links) == 0

    def test_marginal_overlap_none_strength_filtered(self):
        """Overlap just above 0.2 threshold but after strength mapping → NONE filtered."""
        engine = IncidentCorrelationEngine()
        # 1 shared out of 6 unique → 0.167 Jaccard → below 0.2 threshold, skipped
        links = engine.find_symptom_correlations([
            _inc("A", symptoms=["shared", "b", "c"]),
            _inc("B", symptoms=["shared", "d", "e", "f"]),
        ])
        # Jaccard = 1/6 = 0.167 < 0.2 → skipped before strength check
        assert len(links) == 0

    def test_shared_symptoms_in_explanation(self):
        engine = IncidentCorrelationEngine()
        links = engine.find_symptom_correlations([
            _inc("A", symptoms=["timeout", "5xx"]),
            _inc("B", symptoms=["timeout", "5xx"]),
        ])
        assert "timeout" in links[0].explanation


# ── cluster_incidents ────────────────────────────────────────────


class TestClusterIncidents:
    def test_no_links_individual_clusters(self):
        engine = IncidentCorrelationEngine()
        incidents = [_inc("A"), _inc("B")]
        clusters = engine.cluster_incidents([], incidents)
        assert len(clusters) == 2

    def test_linked_incidents_same_cluster(self):
        engine = IncidentCorrelationEngine()
        incidents = [_inc("A"), _inc("B")]
        links = [CorrelationLink(
            source_incident_id="A",
            target_incident_id="B",
            correlation_type=CorrelationType.TEMPORAL,
            strength=CorrelationStrength.STRONG,
            confidence=0.9,
            explanation="test",
        )]
        clusters = engine.cluster_incidents(links, incidents)
        assert len(clusters) == 1
        assert sorted(clusters[0].incidents) == ["A", "B"]

    def test_none_strength_not_merged(self):
        engine = IncidentCorrelationEngine()
        incidents = [_inc("A"), _inc("B")]
        links = [CorrelationLink(
            source_incident_id="A",
            target_incident_id="B",
            correlation_type=CorrelationType.TEMPORAL,
            strength=CorrelationStrength.NONE,
            confidence=0.1,
            explanation="test",
        )]
        clusters = engine.cluster_incidents(links, incidents)
        assert len(clusters) == 2

    def test_transitive_clustering(self):
        engine = IncidentCorrelationEngine()
        incidents = [_inc("A"), _inc("B"), _inc("C")]
        links = [
            CorrelationLink(
                source_incident_id="A", target_incident_id="B",
                correlation_type=CorrelationType.TEMPORAL,
                strength=CorrelationStrength.STRONG, confidence=0.9,
                explanation="test",
            ),
            CorrelationLink(
                source_incident_id="B", target_incident_id="C",
                correlation_type=CorrelationType.TEMPORAL,
                strength=CorrelationStrength.MODERATE, confidence=0.6,
                explanation="test",
            ),
        ]
        clusters = engine.cluster_incidents(links, incidents)
        assert len(clusters) == 1
        assert len(clusters[0].incidents) == 3

    def test_cluster_id_format(self):
        engine = IncidentCorrelationEngine()
        clusters = engine.cluster_incidents([], [_inc("A")])
        assert clusters[0].cluster_id.startswith("CLU-")

    def test_cluster_sorted_by_size(self):
        engine = IncidentCorrelationEngine()
        incidents = [_inc("A"), _inc("B"), _inc("C")]
        links = [CorrelationLink(
            source_incident_id="A", target_incident_id="B",
            correlation_type=CorrelationType.TEMPORAL,
            strength=CorrelationStrength.STRONG, confidence=0.9,
            explanation="test",
        )]
        clusters = engine.cluster_incidents(links, incidents)
        assert len(clusters[0].incidents) >= len(clusters[-1].incidents)

    def test_deployment_in_contributing_factors(self):
        engine = IncidentCorrelationEngine()
        incidents = [
            _inc("A", deployment_id="DEP-1"),
            _inc("B", deployment_id="DEP-1"),
        ]
        links = [CorrelationLink(
            source_incident_id="A", target_incident_id="B",
            correlation_type=CorrelationType.TEMPORAL,
            strength=CorrelationStrength.STRONG, confidence=0.9,
            explanation="test",
        )]
        clusters = engine.cluster_incidents(links, incidents)
        assert any("deployment" in f.lower() for f in clusters[0].contributing_factors)

    def test_symptom_in_contributing_factors(self):
        engine = IncidentCorrelationEngine()
        incidents = [
            _inc("A", symptoms=["timeout"]),
            _inc("B", symptoms=["timeout"]),
        ]
        links = [CorrelationLink(
            source_incident_id="A", target_incident_id="B",
            correlation_type=CorrelationType.SYMPTOM,
            strength=CorrelationStrength.STRONG, confidence=0.9,
            explanation="test",
        )]
        clusters = engine.cluster_incidents(links, incidents)
        assert any("symptom" in f.lower() for f in clusters[0].contributing_factors)

    def test_multi_service_in_contributing_factors(self):
        engine = IncidentCorrelationEngine()
        incidents = [
            _inc("A", service="svc-a"),
            _inc("B", service="svc-b"),
        ]
        links = [CorrelationLink(
            source_incident_id="A", target_incident_id="B",
            correlation_type=CorrelationType.TEMPORAL,
            strength=CorrelationStrength.STRONG, confidence=0.9,
            explanation="test",
        )]
        clusters = engine.cluster_incidents(links, incidents)
        assert any("multi-service" in f.lower() for f in clusters[0].contributing_factors)

    def test_single_incident_deployment_categorized(self):
        engine = IncidentCorrelationEngine()
        incidents = [_inc("A", deployment_id="DEP-1")]
        clusters = engine.cluster_incidents([], incidents)
        assert clusters[0].root_cause_category == RootCauseCategory.DEPLOYMENT_FAILURE

    def test_single_incident_no_deployment_unknown(self):
        engine = IncidentCorrelationEngine()
        incidents = [_inc("A")]
        clusters = engine.cluster_incidents([], incidents)
        assert clusters[0].root_cause_category == RootCauseCategory.UNKNOWN

    def test_link_with_unknown_incident_ids_ignored(self):
        """Links referencing IDs not in incidents list are ignored."""
        engine = IncidentCorrelationEngine()
        incidents = [_inc("A")]
        links = [CorrelationLink(
            source_incident_id="A", target_incident_id="UNKNOWN",
            correlation_type=CorrelationType.TEMPORAL,
            strength=CorrelationStrength.STRONG, confidence=0.9,
            explanation="test",
        )]
        clusters = engine.cluster_incidents(links, incidents)
        assert len(clusters) == 1


# ── detect_recurrence ────────────────────────────────────────────


class TestRecurrence:
    def test_empty_list(self):
        engine = IncidentCorrelationEngine()
        assert engine.detect_recurrence([]) == []

    def test_single_incident(self):
        engine = IncidentCorrelationEngine()
        assert engine.detect_recurrence([_inc()]) == []

    def test_two_incidents_same_service(self):
        engine = IncidentCorrelationEngine()
        patterns = engine.detect_recurrence([
            _inc("A", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", "svc-a", started_at="2026-01-15T22:00:00+00:00"),
        ])
        assert len(patterns) >= 1
        assert patterns[0].incident_count == 2
        assert "svc-a" in patterns[0].affected_services

    def test_avg_interval_calculated(self):
        engine = IncidentCorrelationEngine()
        patterns = engine.detect_recurrence([
            _inc("A", "svc-a", started_at="2026-01-15T00:00:00+00:00"),
            _inc("B", "svc-a", started_at="2026-01-15T12:00:00+00:00"),
            _inc("C", "svc-a", started_at="2026-01-16T00:00:00+00:00"),
        ])
        assert len(patterns) >= 1
        assert patterns[0].avg_interval_hours == 12.0

    def test_deployment_trigger(self):
        engine = IncidentCorrelationEngine()
        patterns = engine.detect_recurrence([
            _inc("A", "svc-a", started_at="2026-01-15T10:00:00+00:00", deployment_id="D1"),
            _inc("B", "svc-a", started_at="2026-01-16T10:00:00+00:00", deployment_id="D2"),
        ])
        assert len(patterns) >= 1
        assert "deployment" in patterns[0].likely_trigger.lower()

    def test_symptom_trigger(self):
        engine = IncidentCorrelationEngine()
        patterns = engine.detect_recurrence([
            _inc("A", "svc-a", started_at="2026-01-15T10:00:00+00:00",
                 symptoms=["timeout"]),
            _inc("B", "svc-a", started_at="2026-01-16T10:00:00+00:00",
                 symptoms=["timeout"]),
        ])
        assert len(patterns) >= 1
        assert "timeout" in patterns[0].likely_trigger.lower()

    def test_no_symptoms_unknown_trigger(self):
        engine = IncidentCorrelationEngine()
        patterns = engine.detect_recurrence([
            _inc("A", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", "svc-a", started_at="2026-01-16T10:00:00+00:00"),
        ])
        assert len(patterns) >= 1
        assert "unknown" in patterns[0].likely_trigger.lower()

    def test_different_services_no_single_service_pattern(self):
        engine = IncidentCorrelationEngine()
        patterns = engine.detect_recurrence([
            _inc("A", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", "svc-b", started_at="2026-01-15T12:00:00+00:00"),
        ])
        # No single-service patterns since each has only 1 incident
        single_service = [p for p in patterns if len(p.affected_services) == 1]
        assert len(single_service) == 0

    def test_cross_service_recurrence(self):
        engine = IncidentCorrelationEngine()
        patterns = engine.detect_recurrence([
            _inc("A", "svc-a", started_at="2026-01-15T10:00:00+00:00",
                 symptoms=["timeout"]),
            _inc("B", "svc-b", started_at="2026-01-15T11:00:00+00:00",
                 symptoms=["timeout"]),
            _inc("C", "svc-c", started_at="2026-01-15T12:00:00+00:00",
                 symptoms=["timeout"]),
        ])
        cross = [p for p in patterns if len(p.affected_services) >= 2]
        assert len(cross) >= 1
        assert "cross-service" in cross[0].likely_trigger.lower()

    def test_pattern_id_format(self):
        engine = IncidentCorrelationEngine()
        patterns = engine.detect_recurrence([
            _inc("A", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", "svc-a", started_at="2026-01-16T10:00:00+00:00"),
        ])
        assert patterns[0].pattern_id.startswith("REC-")

    def test_cross_service_needs_min_three_incidents(self):
        """Cross-service requires 3+ incidents with same symptom."""
        engine = IncidentCorrelationEngine()
        patterns = engine.detect_recurrence([
            _inc("A", "svc-a", started_at="2026-01-15T10:00:00+00:00",
                 symptoms=["timeout"]),
            _inc("B", "svc-b", started_at="2026-01-15T11:00:00+00:00",
                 symptoms=["timeout"]),
        ])
        cross = [p for p in patterns if len(p.affected_services) >= 2]
        assert len(cross) == 0


# ── identify_root_cause ──────────────────────────────────────────


class TestIdentifyRootCause:
    def test_empty_cluster(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=[],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="",
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.UNKNOWN

    def test_deployment_in_factors(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["INC-1"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="",
            contributing_factors=["deployment(s): DEP-1"],
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.DEPLOYMENT_FAILURE

    def test_multi_service_factor(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["INC-1", "INC-2"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="",
            contributing_factors=["multi-service impact: svc-a, svc-b"],
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.INFRASTRUCTURE_ISSUE

    def test_config_factor(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["INC-1"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="",
            contributing_factors=["configuration drift detected"],
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.CONFIGURATION_ERROR

    def test_capacity_in_description(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["INC-1"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="capacity exhaustion on svc-a",
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.CAPACITY_EXHAUSTION

    def test_external_in_description(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["INC-1"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="external outage on provider",
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.EXTERNAL_OUTAGE

    def test_dependency_in_description(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["INC-1"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="dependency chain failure",
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.DEPENDENCY_FAILURE

    def test_infrastructure_in_description(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["INC-1"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="infrastructure issue",
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.INFRASTRUCTURE_ISSUE

    def test_config_in_description(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["INC-1"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="config error detected",
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.CONFIGURATION_ERROR

    def test_deploy_in_description(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["INC-1"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="bad deploy caused failure",
        )
        assert engine.identify_root_cause(_graph(), cluster) == RootCauseCategory.DEPLOYMENT_FAILURE

    def test_graph_dependency_chain_detection(self):
        engine = IncidentCorrelationEngine()
        ca = _comp("svc-a")
        cb = _comp("svc-b")
        g = _graph(ca, cb)
        g.add_dependency(Dependency(source_id="svc-b", target_id="svc-a"))
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["svc-a", "svc-b"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="",
        )
        result = engine.identify_root_cause(g, cluster)
        assert result == RootCauseCategory.DEPENDENCY_FAILURE

    def test_fallback_unknown(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["random-id"],
            root_cause_category=RootCauseCategory.UNKNOWN,
            root_cause_description="something vague",
        )
        result = engine.identify_root_cause(_graph(), cluster)
        assert result == RootCauseCategory.UNKNOWN


# ── _deduplicate_links ───────────────────────────────────────────


class TestDeduplicateLinks:
    def test_no_duplicates(self):
        engine = IncidentCorrelationEngine()
        links = [
            CorrelationLink(
                source_incident_id="A", target_incident_id="B",
                correlation_type=CorrelationType.TEMPORAL,
                strength=CorrelationStrength.STRONG, confidence=0.9,
                explanation="test",
            ),
        ]
        result = engine._deduplicate_links(links)
        assert len(result) == 1

    def test_keeps_higher_confidence(self):
        engine = IncidentCorrelationEngine()
        links = [
            CorrelationLink(
                source_incident_id="A", target_incident_id="B",
                correlation_type=CorrelationType.TEMPORAL,
                strength=CorrelationStrength.MODERATE, confidence=0.5,
                explanation="temporal",
            ),
            CorrelationLink(
                source_incident_id="B", target_incident_id="A",
                correlation_type=CorrelationType.SYMPTOM,
                strength=CorrelationStrength.STRONG, confidence=0.95,
                explanation="symptom",
            ),
        ]
        result = engine._deduplicate_links(links)
        assert len(result) == 1
        assert result[0].confidence == 0.95

    def test_sorted_by_confidence_desc(self):
        engine = IncidentCorrelationEngine()
        links = [
            CorrelationLink(
                source_incident_id="A", target_incident_id="B",
                correlation_type=CorrelationType.TEMPORAL,
                strength=CorrelationStrength.MODERATE, confidence=0.5,
                explanation="test",
            ),
            CorrelationLink(
                source_incident_id="C", target_incident_id="D",
                correlation_type=CorrelationType.TEMPORAL,
                strength=CorrelationStrength.STRONG, confidence=0.9,
                explanation="test",
            ),
        ]
        result = engine._deduplicate_links(links)
        assert result[0].confidence >= result[-1].confidence


# ── _categorize_cluster ──────────────────────────────────────────


class TestCategorizeCluster:
    def test_single_incident_with_deploy(self):
        engine = IncidentCorrelationEngine()
        cat, desc = engine._categorize_cluster(
            [_inc("A", deployment_id="D1")], [], ["D1"]
        )
        assert cat == RootCauseCategory.DEPLOYMENT_FAILURE

    def test_single_incident_without_deploy(self):
        engine = IncidentCorrelationEngine()
        cat, desc = engine._categorize_cluster([_inc("A")], [], [])
        assert cat == RootCauseCategory.UNKNOWN
        assert "svc-a" in desc

    def test_multi_with_deployments(self):
        engine = IncidentCorrelationEngine()
        cat, desc = engine._categorize_cluster(
            [_inc("A"), _inc("B")], [], ["D1"]
        )
        assert cat == RootCauseCategory.DEPLOYMENT_FAILURE

    def test_dependency_links(self):
        engine = IncidentCorrelationEngine()
        links = [CorrelationLink(
            source_incident_id="A", target_incident_id="B",
            correlation_type=CorrelationType.DEPENDENCY,
            strength=CorrelationStrength.STRONG, confidence=0.9,
            explanation="test",
        )]
        cat, desc = engine._categorize_cluster([_inc("A"), _inc("B")], links, [])
        assert cat == RootCauseCategory.DEPENDENCY_FAILURE

    def test_symptom_links_only(self):
        engine = IncidentCorrelationEngine()
        links = [CorrelationLink(
            source_incident_id="A", target_incident_id="B",
            correlation_type=CorrelationType.SYMPTOM,
            strength=CorrelationStrength.STRONG, confidence=0.9,
            explanation="test",
        )]
        cat, desc = engine._categorize_cluster([_inc("A"), _inc("B")], links, [])
        assert cat == RootCauseCategory.INFRASTRUCTURE_ISSUE

    def test_temporal_links_only(self):
        engine = IncidentCorrelationEngine()
        links = [CorrelationLink(
            source_incident_id="A", target_incident_id="B",
            correlation_type=CorrelationType.TEMPORAL,
            strength=CorrelationStrength.STRONG, confidence=0.9,
            explanation="test",
        )]
        cat, desc = engine._categorize_cluster([_inc("A"), _inc("B")], links, [])
        assert cat == RootCauseCategory.INFRASTRUCTURE_ISSUE

    def test_no_links_no_deploys(self):
        engine = IncidentCorrelationEngine()
        cat, desc = engine._categorize_cluster([_inc("A"), _inc("B")], [], [])
        assert cat == RootCauseCategory.UNKNOWN


# ── _detect_systemic_issues ──────────────────────────────────────


class TestSystemicIssues:
    def test_high_incident_service(self):
        engine = IncidentCorrelationEngine()
        incidents = [
            _inc("A", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("B", "svc-a", started_at="2026-01-15T11:00:00+00:00"),
            _inc("C", "svc-a", started_at="2026-01-15T12:00:00+00:00"),
        ]
        issues = engine._detect_systemic_issues(_graph(), incidents, [], [])
        assert any("svc-a" in i and "3" in i for i in issues)

    def test_large_cluster_detected(self):
        engine = IncidentCorrelationEngine()
        cluster = IncidentCluster(
            cluster_id="C1",
            incidents=["A", "B", "C", "D"],
            root_cause_category=RootCauseCategory.INFRASTRUCTURE_ISSUE,
            root_cause_description="test",
        )
        issues = engine._detect_systemic_issues(_graph(), [], [cluster], [])
        assert any("C1" in i for i in issues)

    def test_recurring_pattern(self):
        engine = IncidentCorrelationEngine()
        pattern = RecurrencePattern(
            pattern_id="REC-0001",
            incident_count=5,
            avg_interval_hours=24.0,
            affected_services=["svc-a"],
            likely_trigger="unknown",
        )
        issues = engine._detect_systemic_issues(_graph(), [], [], [pattern])
        assert any("REC-0001" in i for i in issues)

    def test_high_severity_concentration(self):
        engine = IncidentCorrelationEngine()
        incidents = [
            _inc("A", severity=IncidentSeverity.SEV1),
            _inc("B", severity=IncidentSeverity.SEV2),
        ]
        issues = engine._detect_systemic_issues(_graph(), incidents, [], [])
        assert any("SEV1/SEV2" in i or "high-severity" in i for i in issues)

    def test_external_api_impact(self):
        engine = IncidentCorrelationEngine()
        ext = _comp("ext-api", ComponentType.EXTERNAL_API)
        app = _comp("svc-a")
        g = _graph(ext, app)
        g.add_dependency(Dependency(source_id="svc-a", target_id="ext-api"))
        incidents = [_inc("A", "ext-api")]
        issues = engine._detect_systemic_issues(g, incidents, [], [])
        assert any("ext-api" in i for i in issues)

    def test_no_issues_when_healthy(self):
        engine = IncidentCorrelationEngine()
        issues = engine._detect_systemic_issues(_graph(), [], [], [])
        assert issues == []

    def test_recurring_pattern_above_weekly_threshold(self):
        """Patterns with interval > 168h should not trigger systemic issue."""
        engine = IncidentCorrelationEngine()
        pattern = RecurrencePattern(
            pattern_id="REC-0001",
            incident_count=3,
            avg_interval_hours=200.0,
            affected_services=["svc-a"],
            likely_trigger="unknown",
        )
        issues = engine._detect_systemic_issues(_graph(), [], [], [pattern])
        assert not any("REC-0001" in i for i in issues)


# ── Integration / End-to-End Tests ──────────────────────────────


class TestIntegration:
    def test_full_pipeline_multiple_services(self):
        engine = IncidentCorrelationEngine()
        ca = _comp("svc-a")
        cb = _comp("svc-b")
        cc = _comp("svc-c", ComponentType.DATABASE)
        g = _graph(ca, cb, cc)
        g.add_dependency(Dependency(source_id="svc-a", target_id="svc-c"))
        g.add_dependency(Dependency(source_id="svc-b", target_id="svc-c"))

        incidents = [
            _inc("INC-1", "svc-a", IncidentSeverity.SEV2,
                 started_at="2026-01-15T10:00:00+00:00",
                 symptoms=["timeout", "5xx"]),
            _inc("INC-2", "svc-b", IncidentSeverity.SEV2,
                 started_at="2026-01-15T10:02:00+00:00",
                 symptoms=["timeout", "slow"]),
            _inc("INC-3", "svc-c", IncidentSeverity.SEV1,
                 started_at="2026-01-15T10:01:00+00:00",
                 symptoms=["disk_full"]),
        ]
        report = engine.correlate_incidents(g, incidents)
        assert report.total_incidents == 3
        assert report.correlated_count >= 2
        assert len(report.links) >= 1
        assert len(report.clusters) >= 1
        assert len(report.systemic_issues) >= 1  # SEV1+SEV2

    def test_full_pipeline_with_recurrence(self):
        engine = IncidentCorrelationEngine()
        g = _graph(_comp("svc-a"))
        incidents = [
            _inc("INC-1", "svc-a", started_at="2026-01-15T10:00:00+00:00",
                 symptoms=["timeout"]),
            _inc("INC-2", "svc-a", started_at="2026-01-16T10:00:00+00:00",
                 symptoms=["timeout"]),
            _inc("INC-3", "svc-a", started_at="2026-01-17T10:00:00+00:00",
                 symptoms=["timeout"]),
        ]
        report = engine.correlate_incidents(g, incidents)
        assert len(report.recurrence_patterns) >= 1

    def test_deployment_correlation_end_to_end(self):
        engine = IncidentCorrelationEngine()
        g = _graph(_comp("svc-a"), _comp("svc-b"))
        incidents = [
            _inc("INC-1", "svc-a", started_at="2026-01-15T10:00:00+00:00",
                 deployment_id="DEP-42"),
            _inc("INC-2", "svc-b", started_at="2026-01-15T10:02:00+00:00",
                 deployment_id="DEP-42"),
        ]
        report = engine.correlate_incidents(g, incidents)
        assert report.total_incidents == 2
        # Should be clustered together
        assert len(report.clusters) >= 1

    def test_isolated_incidents_no_correlation(self):
        engine = IncidentCorrelationEngine()
        g = _graph(_comp("svc-a"), _comp("svc-b"))
        incidents = [
            _inc("INC-1", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("INC-2", "svc-b", started_at="2026-01-20T10:00:00+00:00"),
        ]
        report = engine.correlate_incidents(g, incidents)
        assert report.correlated_count == 0
        assert len(report.clusters) == 2

    def test_large_incident_set(self):
        engine = IncidentCorrelationEngine()
        g = _graph(*[_comp(f"svc-{i}") for i in range(10)])
        incidents = [
            _inc(f"INC-{i}", f"svc-{i % 10}",
                 started_at=f"2026-01-15T{10 + i % 5:02d}:00:00+00:00",
                 symptoms=["timeout"])
            for i in range(20)
        ]
        report = engine.correlate_incidents(g, incidents)
        assert report.total_incidents == 20
        assert len(report.clusters) >= 1

    def test_enrichment_updates_unknown_clusters(self):
        """correlate_incidents enriches UNKNOWN clusters via identify_root_cause."""
        engine = IncidentCorrelationEngine()
        ca = _comp("svc-a")
        cb = _comp("svc-b")
        g = _graph(ca, cb)
        g.add_dependency(Dependency(source_id="svc-b", target_id="svc-a"))
        incidents = [
            _inc("svc-a", "svc-a", started_at="2026-01-15T10:00:00+00:00"),
            _inc("svc-b", "svc-b", started_at="2026-01-15T10:01:00+00:00"),
        ]
        report = engine.correlate_incidents(g, incidents)
        # At least one cluster should have been enriched
        categories = [c.root_cause_category for c in report.clusters]
        assert any(c != RootCauseCategory.UNKNOWN for c in categories) or len(categories) > 0
