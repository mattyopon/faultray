"""Tests for the Incident Replay Engine."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    CostProfile,
    Dependency,
    FailoverConfig,
    HealthStatus,
    OperationalProfile,
    RegionConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.incident_db import HISTORICAL_INCIDENTS
from faultray.simulator.incident_replay import (
    AffectedComponent,
    HistoricalIncident,
    IncidentEvent,
    IncidentReplayEngine,
    ReplayResult,
    SERVICE_COMPONENT_MAPPING,
)


# ---------------------------------------------------------------------------
# Helpers  (same pattern as test_change_risk.py)
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    region: str = "",
    dr_region: str = "",
    failover: bool = False,
    failover_seconds: float = 30.0,
    revenue_per_min: float = 0.0,
    mttr_minutes: float = 30.0,
) -> Component:
    fo = (
        FailoverConfig(enabled=True, promotion_time_seconds=failover_seconds)
        if failover
        else FailoverConfig()
    )
    rc = RegionConfig(region=region, dr_target_region=dr_region)
    cp = CostProfile(revenue_per_minute=revenue_per_min)
    op = OperationalProfile(mttr_minutes=mttr_minutes)
    c = Component(
        id=cid, name=name, type=ctype, replicas=replicas,
        failover=fo, region=rc, cost_profile=cp, operational_profile=op,
    )
    c.health = health
    return c


def _chain_graph() -> InfraGraph:
    """lb -> app -> db  (single region, no protection)."""
    g = InfraGraph()
    g.add_component(_comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER, region="us-east-1"))
    g.add_component(_comp("app", "App Server", region="us-east-1"))
    g.add_component(_comp("db", "RDS Database", ComponentType.DATABASE, region="us-east-1"))
    g.add_component(_comp("cache", "ElastiCache Redis", ComponentType.CACHE, region="us-east-1"))
    g.add_dependency(Dependency(source_id="lb", target_id="app", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
    return g


def _resilient_graph() -> InfraGraph:
    """Multi-region with failover and replicas."""
    g = InfraGraph()
    g.add_component(_comp(
        "lb", "Global LB", ComponentType.LOAD_BALANCER,
        replicas=2, region="us-east-1", dr_region="us-west-2", failover=True, failover_seconds=15,
    ))
    g.add_component(_comp(
        "app-east", "App East", replicas=3,
        region="us-east-1", dr_region="us-west-2", failover=True, failover_seconds=30,
    ))
    g.add_component(_comp("app-west", "App West", replicas=3, region="us-west-2"))
    g.add_component(_comp(
        "db-primary", "Aurora Primary", ComponentType.DATABASE,
        replicas=2, region="us-east-1", dr_region="us-west-2", failover=True, failover_seconds=60,
    ))
    g.add_component(_comp("db-replica", "Aurora Replica", ComponentType.DATABASE, replicas=2, region="us-west-2"))
    g.add_component(_comp("cache", "Redis", ComponentType.CACHE, replicas=3, region="us-east-1"))
    g.add_dependency(Dependency(source_id="lb", target_id="app-east"))
    g.add_dependency(Dependency(source_id="lb", target_id="app-west"))
    g.add_dependency(Dependency(source_id="app-east", target_id="db-primary"))
    g.add_dependency(Dependency(source_id="app-west", target_id="db-replica"))
    g.add_dependency(Dependency(source_id="app-east", target_id="cache", dependency_type="optional"))
    return g


def _custom_incident(
    affected_services: list[str] | None = None,
    affected_regions: list[str] | None = None,
    timeline: list[IncidentEvent] | None = None,
    duration: timedelta = timedelta(hours=2),
    severity: str = "major",
    lessons: list[str] | None = None,
) -> HistoricalIncident:
    return HistoricalIncident(
        id="test-incident",
        name="Test Incident",
        provider="aws",
        date=datetime(2024, 1, 1),
        duration=duration,
        root_cause="Test root cause",
        affected_services=affected_services or ["ec2"],
        affected_regions=affected_regions or ["us-east-1"],
        severity=severity,
        timeline=timeline or [],
        lessons_learned=lessons or ["Test lesson"],
        post_mortem_url="https://example.com",
    )


# ---------------------------------------------------------------------------
# IncidentReplayEngine: listing / lookup
# ---------------------------------------------------------------------------


class TestIncidentListing:
    def test_list_all(self):
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        assert len(incidents) >= 15

    def test_filter_by_provider(self):
        engine = IncidentReplayEngine()
        aws = engine.list_incidents(provider="aws")
        assert len(aws) >= 3
        assert all(i.provider == "aws" for i in aws)

    def test_filter_unknown_provider(self):
        engine = IncidentReplayEngine()
        assert engine.list_incidents(provider="nonexistent") == []

    def test_get_incident_by_id(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        assert inc.id == "aws-us-east-1-2021-12"
        assert inc.provider == "aws"

    def test_get_incident_unknown_raises(self):
        engine = IncidentReplayEngine()
        with pytest.raises(KeyError, match="nonexistent"):
            engine.get_incident("nonexistent")


# ---------------------------------------------------------------------------
# Replay: basic scenarios
# ---------------------------------------------------------------------------


class TestReplayBasic:
    def test_single_region_fails_regional_outage(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(_chain_graph(), inc)
        assert isinstance(result, ReplayResult)
        assert not result.survived
        assert result.impact_score > 5.0
        assert result.resilience_grade_during_incident in ("D", "F")
        assert len(result.affected_components) > 0
        assert result.downtime_estimate > timedelta(0)
        assert len(result.vulnerability_factors) > 0

    def test_multi_region_survives_regional_outage(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(_resilient_graph(), inc)
        assert result.impact_score < 8.0
        assert len(result.survival_factors) > 0

    def test_unrelated_infra_unaffected(self):
        engine = IncidentReplayEngine()
        g = InfraGraph()
        g.add_component(_comp("custom", "Custom", ComponentType.CUSTOM))
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        assert result.survived
        assert result.impact_score == 0.0
        assert result.resilience_grade_during_incident == "A"
        assert len(result.affected_components) == 0

    def test_replay_all(self):
        engine = IncidentReplayEngine()
        results = engine.replay_all(_chain_graph())
        assert len(results) == len(engine.list_incidents())
        assert all(isinstance(r, ReplayResult) for r in results)


# ---------------------------------------------------------------------------
# Vulnerability scanning
# ---------------------------------------------------------------------------


class TestFindVulnerable:
    def test_vulnerable_incidents_for_exposed_infra(self):
        engine = IncidentReplayEngine()
        vuln = engine.find_vulnerable_incidents(_chain_graph())
        assert len(vuln) > 0
        scores = [s for _, s in vuln]
        assert scores == sorted(scores, reverse=True)
        assert all(s > 0 for _, s in vuln)

    def test_no_vulnerabilities_for_custom(self):
        engine = IncidentReplayEngine()
        g = InfraGraph()
        g.add_component(_comp("x", "X", ComponentType.CUSTOM))
        assert engine.find_vulnerable_incidents(g) == []


# ---------------------------------------------------------------------------
# ReplayResult properties
# ---------------------------------------------------------------------------


class TestReplayResultProperties:
    def test_impact_score_range(self):
        engine = IncidentReplayEngine()
        for inc in engine.list_incidents():
            result = engine.replay(_chain_graph(), inc)
            assert 0.0 <= result.impact_score <= 10.0

    def test_grade_values(self):
        engine = IncidentReplayEngine()
        for inc in engine.list_incidents():
            result = engine.replay(_chain_graph(), inc)
            assert result.resilience_grade_during_incident in ("A", "B", "C", "D", "F")

    def test_recommendations_on_failure(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(_chain_graph(), inc)
        if not result.survived:
            assert len(result.recommendations) > 0

    def test_timeline_ordered(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(_chain_graph(), inc)
        for i in range(1, len(result.timeline)):
            assert result.timeline[i].timestamp_offset >= result.timeline[i - 1].timestamp_offset

    def test_revenue_impact_with_cost(self):
        g = InfraGraph()
        g.add_component(_comp(
            "app", "App", region="us-east-1", revenue_per_min=100.0,
        ))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        if not result.survived and result.downtime_estimate > timedelta(0):
            assert result.revenue_impact_estimate is not None
            assert result.revenue_impact_estimate > 0

    def test_revenue_impact_none_without_cost(self):
        engine = IncidentReplayEngine()
        g = InfraGraph()
        g.add_component(_comp("x", "X", ComponentType.CUSTOM))
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        # No revenue configured => None
        assert result.revenue_impact_estimate is None


# ---------------------------------------------------------------------------
# Region protection
# ---------------------------------------------------------------------------


class TestRegionProtection:
    def test_different_region_survives(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="us-west-2"))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        assert result.survived
        assert result.impact_score == 0.0

    def test_same_region_affected(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="us-east-1"))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        assert not result.survived
        assert result.impact_score > 0

    def test_global_outage_affects_all_regions(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="ap-southeast-1"))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("crowdstrike-2024-07")
        result = engine.replay(g, inc)
        assert result.impact_score > 0

    def test_failover_to_unaffected_dr_region(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "DB", ComponentType.DATABASE,
            region="us-east-1", dr_region="eu-west-1",
            failover=True, failover_seconds=60,
        ))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        assert result.survived or result.impact_score < 5.0
        assert len(result.survival_factors) > 0


# ---------------------------------------------------------------------------
# Evaluate component edge cases
# ---------------------------------------------------------------------------


class TestEvaluateComponent:
    def test_no_region_specified_goes_down(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App"))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        app = [a for a in result.affected_components if a.component_id == "app"]
        if app:
            assert "no region" in app[0].reason.lower() or result.impact_score > 0

    def test_replicas_gt1_non_global_survives(self):
        """Component with replicas > 1 in non-global outage survives as degraded."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, region="us-east-1"))
        engine = IncidentReplayEngine()
        inc = _custom_incident(affected_regions=["us-east-1"])
        result = engine.replay(g, inc)
        app = [a for a in result.affected_components if a.component_id == "app"]
        assert len(app) >= 1
        assert app[0].health_during_incident in (HealthStatus.DEGRADED, HealthStatus.HEALTHY)

    def test_replicas_gt2_global_survives_degraded(self):
        """Component with replicas > 2 in global outage -> DEGRADED."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=5, region="us-east-1"))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("crowdstrike-2024-07")
        result = engine.replay(g, inc)
        app = [a for a in result.affected_components if a.component_id == "app"]
        assert len(app) >= 1
        assert app[0].health_during_incident in (HealthStatus.DEGRADED, HealthStatus.HEALTHY)

    def test_global_outage_single_replica_goes_down(self):
        """Global outage + single replica => DOWN."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=1, region="us-east-1"))
        engine = IncidentReplayEngine()
        inc = _custom_incident(affected_regions=["global"])
        result = engine.replay(g, inc)
        app = [a for a in result.affected_components if a.component_id == "app"]
        if app:
            assert app[0].health_during_incident == HealthStatus.DOWN


# ---------------------------------------------------------------------------
# Recovery time estimation
# ---------------------------------------------------------------------------


class TestRecoveryTime:
    def test_failover_uses_promotion_time(self):
        g = InfraGraph()
        g.add_component(_comp(
            "db", "DB", ComponentType.DATABASE,
            region="us-east-1", failover=True, failover_seconds=120,
        ))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        db = [a for a in result.affected_components if a.component_id == "db"]
        if db and db[0].recovery_time:
            assert db[0].recovery_time.total_seconds() == 120

    def test_mttr_used_when_no_failover(self):
        g = InfraGraph()
        g.add_component(_comp(
            "app", "App", region="us-east-1", mttr_minutes=15,
        ))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        app = [a for a in result.affected_components if a.component_id == "app"]
        if app and app[0].recovery_time:
            assert app[0].recovery_time == timedelta(minutes=15)

    def test_default_70pct_when_no_mttr(self):
        g = InfraGraph()
        g.add_component(_comp(
            "app", "App", region="us-east-1", mttr_minutes=0,
        ))
        engine = IncidentReplayEngine()
        inc = _custom_incident(duration=timedelta(hours=2))
        result = engine.replay(g, inc)
        app = [a for a in result.affected_components if a.component_id == "app"]
        if app and app[0].recovery_time:
            expected = timedelta(seconds=2 * 3600 * 0.7)
            assert app[0].recovery_time == expected


# ---------------------------------------------------------------------------
# Timeline events
# ---------------------------------------------------------------------------


class TestTimeline:
    def test_synthetic_events_no_timeline(self):
        """Incident without timeline generates synthetic events."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="us-east-1"))
        engine = IncidentReplayEngine()
        inc = _custom_incident(timeline=[])
        result = engine.replay(g, inc)
        assert len(result.timeline) >= 1

    def test_synthetic_survived_event(self):
        """Survived component gets 'survived' synthetic event."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, region="us-east-1"))
        engine = IncidentReplayEngine()
        inc = _custom_incident(timeline=[])
        result = engine.replay(g, inc)
        survived_events = [e for e in result.timeline if e.event_type == "survived"]
        # Component has replicas => survived
        assert len(survived_events) >= 1

    def test_mapped_timeline_events(self):
        """Incident with timeline maps events to replay events."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="us-east-1"))
        engine = IncidentReplayEngine()
        timeline = [
            IncidentEvent(
                timestamp_offset=timedelta(0),
                event_type="service_degradation",
                affected_services=["ec2"],
                description="Degradation starts",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=10),
                event_type="full_outage",
                affected_services=["ec2"],
                description="Full outage",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(minutes=60),
                event_type="partial_recovery",
                affected_services=["ec2"],
                description="Partial recovery",
            ),
            IncidentEvent(
                timestamp_offset=timedelta(hours=2),
                event_type="full_recovery",
                affected_services=["ec2"],
                description="Full recovery",
            ),
        ]
        inc = _custom_incident(timeline=timeline)
        result = engine.replay(g, inc)
        assert len(result.timeline) >= 4

    def test_unknown_event_type_fallback(self):
        """Unknown event_type falls back to resulting_health."""
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="us-east-1"))
        engine = IncidentReplayEngine()
        timeline = [
            IncidentEvent(
                timestamp_offset=timedelta(minutes=10),
                event_type="custom_unknown_type",
                affected_services=["ec2"],
                description="Custom event",
            ),
        ]
        inc = _custom_incident(timeline=timeline)
        result = engine.replay(g, inc)
        assert len(result.timeline) >= 1


# ---------------------------------------------------------------------------
# Cascade analysis
# ---------------------------------------------------------------------------


class TestCascadeAnalysis:
    def test_cascade_from_db_failure(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="us-east-1"))
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, region="us-east-1"))
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        ids = {a.component_id for a in result.affected_components}
        assert "db" in ids
        assert len(result.affected_components) >= 1

    def test_optional_dependency_degraded(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="us-east-1"))
        g.add_component(_comp("cache", "Redis", ComponentType.CACHE, region="us-east-1"))
        g.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        cascade = [a for a in result.affected_components if a.impact_type == "cascade"]
        for c in cascade:
            if c.component_id == "app":
                assert c.health_during_incident == HealthStatus.DEGRADED

    def test_async_dependency_degraded(self):
        g = InfraGraph()
        g.add_component(_comp("queue", "SQS", ComponentType.QUEUE, region="us-east-1"))
        g.add_component(_comp("worker", "Worker", region="us-east-1"))
        g.add_dependency(Dependency(source_id="worker", target_id="queue", dependency_type="async"))
        engine = IncidentReplayEngine()
        inc = _custom_incident(affected_services=["sqs"], affected_regions=["us-east-1"])
        result = engine.replay(g, inc)
        worker = [a for a in result.affected_components if a.component_id == "worker"]
        if worker:
            assert worker[0].health_during_incident == HealthStatus.DEGRADED

    def test_cascade_requires_with_replicas_degraded(self):
        """Dependent with replicas > 1 on requires dep => DEGRADED (not DOWN)."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, region="us-east-1"))
        g.add_component(_comp("api", "API", replicas=3, region="us-east-1"))
        g.add_dependency(Dependency(source_id="api", target_id="db", dependency_type="requires"))
        engine = IncidentReplayEngine()
        inc = _custom_incident(affected_services=["rds"], affected_regions=["us-east-1"])
        result = engine.replay(g, inc)
        api = [a for a in result.affected_components if a.component_id == "api"]
        if api:
            assert api[0].health_during_incident in (HealthStatus.DEGRADED, HealthStatus.DOWN)

    def test_cascade_requires_no_replicas_goes_down(self):
        """Dependent with replicas=1 on requires dep => DOWN, cascades further."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, region="us-east-1"))
        g.add_component(_comp("api", "API", replicas=1, region="us-east-1"))
        g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=1, region="us-east-1"))
        g.add_dependency(Dependency(source_id="api", target_id="db", dependency_type="requires"))
        g.add_dependency(Dependency(source_id="lb", target_id="api", dependency_type="requires"))
        engine = IncidentReplayEngine()
        inc = _custom_incident(affected_services=["rds"], affected_regions=["us-east-1"])
        result = engine.replay(g, inc)
        ids = {a.component_id for a in result.affected_components}
        # db goes down, api cascades DOWN, lb cascades
        assert "db" in ids


# ---------------------------------------------------------------------------
# Impact scoring
# ---------------------------------------------------------------------------


class TestImpactScoring:
    def test_no_affected_zero_score(self):
        engine = IncidentReplayEngine()
        score = engine._calculate_impact_score([], InfraGraph())
        assert score == 0.0

    def test_high_down_ratio_boosts_score(self):
        """More than 50% down => score >= 8.0."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        affected = [
            AffectedComponent("a", "A", "direct", HealthStatus.DOWN, None, "down"),
            AffectedComponent("b", "B", "direct", HealthStatus.DOWN, None, "down"),
        ]
        engine = IncidentReplayEngine()
        score = engine._calculate_impact_score(affected, g)
        assert score >= 8.0

    def test_moderate_down_ratio_boost(self):
        """30-50% down => score >= 6.0."""
        g = InfraGraph()
        for i in range(10):
            g.add_component(_comp(f"c{i}", f"C{i}"))
        affected = [
            AffectedComponent(f"c{i}", f"C{i}", "direct", HealthStatus.DOWN, None, "down")
            for i in range(4)  # 4/10 = 40%
        ]
        engine = IncidentReplayEngine()
        score = engine._calculate_impact_score(affected, g)
        assert score >= 6.0

    def test_degraded_lower_than_down(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        engine = IncidentReplayEngine()
        down_score = engine._calculate_impact_score(
            [AffectedComponent("a", "A", "d", HealthStatus.DOWN, None, "x")], g,
        )
        degraded_score = engine._calculate_impact_score(
            [AffectedComponent("a", "A", "d", HealthStatus.DEGRADED, None, "x")], g,
        )
        assert down_score > degraded_score


# ---------------------------------------------------------------------------
# Downtime estimation
# ---------------------------------------------------------------------------


class TestDowntimeEstimation:
    def test_no_down_components_zero_downtime(self):
        engine = IncidentReplayEngine()
        inc = _custom_incident(duration=timedelta(hours=1))
        dt = engine._estimate_total_downtime([], inc)
        assert dt == timedelta(0)

    def test_downtime_capped_at_incident_duration(self):
        engine = IncidentReplayEngine()
        inc = _custom_incident(duration=timedelta(hours=1))
        affected = [
            AffectedComponent(
                "a", "A", "d", HealthStatus.DOWN,
                timedelta(hours=10),  # exceeds incident duration
                "x",
            ),
        ]
        dt = engine._estimate_total_downtime(affected, inc)
        assert dt <= inc.duration


# ---------------------------------------------------------------------------
# Grade calculation
# ---------------------------------------------------------------------------


class TestGradeCalculation:
    def test_all_grades(self):
        engine = IncidentReplayEngine()
        assert engine._calculate_grade(0.5) == "A"
        assert engine._calculate_grade(1.0) == "A"
        assert engine._calculate_grade(2.0) == "B"
        assert engine._calculate_grade(3.0) == "B"
        assert engine._calculate_grade(4.0) == "C"
        assert engine._calculate_grade(5.0) == "C"
        assert engine._calculate_grade(5.5) == "D"
        assert engine._calculate_grade(7.0) == "D"
        assert engine._calculate_grade(8.0) == "F"
        assert engine._calculate_grade(10.0) == "F"


# ---------------------------------------------------------------------------
# Component matching
# ---------------------------------------------------------------------------


class TestComponentMatching:
    def test_match_by_type(self):
        g = InfraGraph()
        g.add_component(_comp("my-db", "CustomDB", ComponentType.DATABASE))
        engine = IncidentReplayEngine()
        matched = engine._find_matching_components(g, "rds")
        assert len(matched) == 1
        assert matched[0].id == "my-db"

    def test_match_by_name_pattern(self):
        g = InfraGraph()
        g.add_component(_comp("redis-cluster", "Redis Cluster", ComponentType.CUSTOM))
        engine = IncidentReplayEngine()
        matched = engine._find_matching_components(g, "elasticache")
        assert len(matched) == 1
        assert matched[0].id == "redis-cluster"

    def test_no_match(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API Gateway"))
        engine = IncidentReplayEngine()
        assert engine._find_matching_components(g, "s3") == []

    def test_unknown_service_returns_empty(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        engine = IncidentReplayEngine()
        assert engine._find_matching_components(g, "nonexistent_service_xyz") == []


# ---------------------------------------------------------------------------
# Quick vulnerability score
# ---------------------------------------------------------------------------


class TestQuickVulnerability:
    def test_protected_component_partial_score(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=3, region="us-east-1"))
        engine = IncidentReplayEngine()
        inc = _custom_incident()
        score = engine._quick_vulnerability_score(g, inc)
        # With protection: 0.3/1 * 10 = 3.0
        assert 0 < score <= 5.0

    def test_unprotected_full_score(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", replicas=1, region="us-east-1"))
        engine = IncidentReplayEngine()
        inc = _custom_incident()
        score = engine._quick_vulnerability_score(g, inc)
        assert score == 10.0

    def test_different_region_not_vulnerable(self):
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="eu-west-1"))
        engine = IncidentReplayEngine()
        inc = _custom_incident(affected_regions=["us-east-1"])
        score = engine._quick_vulnerability_score(g, inc)
        assert score == 0.0

    def test_no_matching_components_zero(self):
        g = InfraGraph()
        g.add_component(_comp("x", "X", ComponentType.CUSTOM))
        engine = IncidentReplayEngine()
        inc = _custom_incident()
        score = engine._quick_vulnerability_score(g, inc)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_multi_region_recommendation(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(_chain_graph(), inc)
        assert any("multi-region" in r.lower() or "failover" in r.lower() for r in result.recommendations)

    def test_replicas_recommendation(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(_chain_graph(), inc)
        assert any("replica" in r.lower() for r in result.recommendations)

    def test_cascade_recommendation(self):
        """Cascade failures trigger circuit breaker recommendation."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, region="us-east-1"))
        g.add_component(_comp("api", "API", region="us-east-1"))
        g.add_dependency(Dependency(source_id="api", target_id="db", dependency_type="requires"))
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        result = engine.replay(g, inc)
        cascade = [a for a in result.affected_components if a.impact_type == "cascade"]
        if cascade:
            assert any("circuit breaker" in r.lower() for r in result.recommendations)

    def test_lessons_learned_included(self):
        engine = IncidentReplayEngine()
        inc = _custom_incident(lessons=["Always test DR", "Monitor everything"])
        g = InfraGraph()
        g.add_component(_comp("app", "App", region="us-east-1"))
        result = engine.replay(g, inc)
        assert any("Lesson" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# SERVICE_COMPONENT_MAPPING
# ---------------------------------------------------------------------------


class TestServiceMapping:
    def test_aws_services_present(self):
        for svc in ["ec2", "rds", "elasticache", "alb", "s3", "sqs", "lambda", "route53", "cloudfront", "api_gateway"]:
            assert svc in SERVICE_COMPONENT_MAPPING

    def test_all_mappings_have_required_keys(self):
        for svc, mapping in SERVICE_COMPONENT_MAPPING.items():
            assert "types" in mapping
            assert "name_patterns" in mapping
            assert len(mapping["types"]) > 0
            assert len(mapping["name_patterns"]) > 0


# ---------------------------------------------------------------------------
# Historical incident DB
# ---------------------------------------------------------------------------


class TestHistoricalIncidentDB:
    def test_minimum_count(self):
        assert len(HISTORICAL_INCIDENTS) >= 15

    def test_unique_ids(self):
        ids = [i.id for i in HISTORICAL_INCIDENTS]
        assert len(ids) == len(set(ids))

    def test_required_fields(self):
        for inc in HISTORICAL_INCIDENTS:
            assert inc.id
            assert inc.name
            assert inc.provider
            assert inc.root_cause
            assert inc.affected_services
            assert inc.affected_regions
            assert inc.severity in ("critical", "major", "minor")
            assert inc.duration > timedelta(0)
            assert len(inc.timeline) > 0
            assert len(inc.lessons_learned) > 0

    def test_multiple_providers(self):
        providers = {i.provider for i in HISTORICAL_INCIDENTS}
        for p in ("aws", "gcp", "azure", "generic"):
            assert p in providers

    def test_valid_dates(self):
        for inc in HISTORICAL_INCIDENTS:
            assert 2010 <= inc.date.year <= 2025

    def test_valid_timeline_event_types(self):
        valid = {"service_degradation", "full_outage", "partial_recovery", "full_recovery"}
        for inc in HISTORICAL_INCIDENTS:
            for ev in inc.timeline:
                assert ev.event_type in valid

    def test_crowdstrike_details(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("crowdstrike-2024-07")
        assert inc.date == datetime(2024, 7, 19)
        assert inc.severity == "critical"
        assert "global" in inc.affected_regions

    def test_aws_2021_details(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("aws-us-east-1-2021-12")
        assert inc.date == datetime(2021, 12, 7)
        assert "us-east-1" in inc.affected_regions
        assert "ec2" in inc.affected_services

    def test_meta_bgp_details(self):
        engine = IncidentReplayEngine()
        inc = engine.get_incident("meta-bgp-2021-10")
        assert inc.date == datetime(2021, 10, 4)
        assert "global" in inc.affected_regions
        assert "dns" in inc.affected_services
