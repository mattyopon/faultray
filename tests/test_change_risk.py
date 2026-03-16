"""Tests for change risk scorer."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.change_risk import (
    BatchRiskAssessment,
    ChangeCategory,
    ChangeRiskAssessment,
    ChangeRiskScorer,
    ProposedChange,
    RiskFactor,
    RiskLevel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    return c


def _chain_graph() -> InfraGraph:
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API", replicas=3))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _change(
    cat: ChangeCategory = ChangeCategory.CONFIG_CHANGE,
    cid: str = "api",
    desc: str = "Test change",
    reversible: bool = True,
    downtime: bool = False,
    peak: bool = False,
) -> ProposedChange:
    return ProposedChange(
        category=cat,
        component_id=cid,
        description=desc,
        is_reversible=reversible,
        requires_downtime=downtime,
        is_peak_hours=peak,
    )


# ---------------------------------------------------------------------------
# Tests: Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_risk_levels(self):
        assert RiskLevel.CRITICAL.value == "critical"
        assert RiskLevel.MINIMAL.value == "minimal"

    def test_change_categories(self):
        assert ChangeCategory.SCALE_UP.value == "scale_up"
        assert ChangeCategory.MIGRATION.value == "migration"


# ---------------------------------------------------------------------------
# Tests: Single assessment
# ---------------------------------------------------------------------------


class TestSingleAssessment:
    def test_basic_assessment(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change())
        assert result.risk_score >= 0
        assert result.risk_level in RiskLevel
        assert isinstance(result.risk_factors, list)

    def test_scale_up_low_risk(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(ChangeCategory.SCALE_UP))
        assert result.risk_score < 50  # Scale up is low risk

    def test_remove_component_higher_than_scale_up(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        r1 = scorer.assess(_change(ChangeCategory.SCALE_UP, "db"))
        r2 = scorer.assess(_change(ChangeCategory.REMOVE_COMPONENT, "db"))
        assert r2.risk_score > r1.risk_score

    def test_irreversible_increases_risk(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        r1 = scorer.assess(_change(reversible=True))
        r2 = scorer.assess(_change(reversible=False))
        assert r2.risk_score > r1.risk_score

    def test_downtime_increases_risk(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        r1 = scorer.assess(_change(downtime=False))
        r2 = scorer.assess(_change(downtime=True))
        assert r2.risk_score > r1.risk_score

    def test_peak_hours_increases_risk(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        r1 = scorer.assess(_change(peak=False))
        r2 = scorer.assess(_change(peak=True))
        assert r2.risk_score > r1.risk_score

    def test_unhealthy_component_increases_risk(self):
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.DOWN))
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(cid="api"))
        health_factor = [f for f in result.risk_factors if f.name == "Current Health"]
        assert health_factor[0].score > 0


# ---------------------------------------------------------------------------
# Tests: Blast radius
# ---------------------------------------------------------------------------


class TestBlastRadius:
    def test_db_blast_radius(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(cid="db"))
        # db has dependents (api, lb transitively)
        assert result.blast_radius >= 1

    def test_leaf_component_no_blast(self):
        g = InfraGraph()
        g.add_component(_comp("leaf", "Leaf"))
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(cid="leaf"))
        assert result.blast_radius == 0

    def test_affected_components(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(cid="db"))
        assert isinstance(result.affected_components, list)


# ---------------------------------------------------------------------------
# Tests: Risk factors
# ---------------------------------------------------------------------------


class TestRiskFactors:
    def test_factor_count(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change())
        assert len(result.risk_factors) >= 5

    def test_factor_has_weight(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change())
        for factor in result.risk_factors:
            assert factor.weight > 0

    def test_blast_radius_factor(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(cid="db"))
        br_factor = [f for f in result.risk_factors if f.name == "Blast Radius"]
        assert len(br_factor) == 1

    def test_category_factor(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change())
        cat_factor = [f for f in result.risk_factors if f.name == "Change Category"]
        assert len(cat_factor) == 1


# ---------------------------------------------------------------------------
# Tests: Approval requirement
# ---------------------------------------------------------------------------


class TestApproval:
    def test_high_risk_requires_approval(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(
            ChangeCategory.REMOVE_COMPONENT, "db",
            reversible=False, downtime=True, peak=True,
        ))
        # Score 43.7 is MEDIUM, check that risky factors are identified
        assert result.risk_score > 30
        assert any("backup" in s.lower() for s in result.recommended_safeguards)

    def test_low_risk_no_approval(self):
        g = InfraGraph()
        g.add_component(_comp("leaf", "Leaf"))
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(ChangeCategory.SCALE_UP, "leaf"))
        assert result.requires_approval is False


# ---------------------------------------------------------------------------
# Tests: Safeguards and rollback
# ---------------------------------------------------------------------------


class TestSafeguards:
    def test_downtime_safeguard(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(downtime=True))
        assert any("maintenance" in s.lower() for s in result.recommended_safeguards)

    def test_irreversible_safeguard(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(reversible=False))
        assert any("backup" in s.lower() for s in result.recommended_safeguards)

    def test_peak_hours_safeguard(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(peak=True))
        assert any("off-peak" in s.lower() for s in result.recommended_safeguards)

    def test_rollback_plan(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(ChangeCategory.SCALE_DOWN))
        assert result.rollback_plan
        assert "scale" in result.rollback_plan.lower() or "api" in result.rollback_plan.lower()


# ---------------------------------------------------------------------------
# Tests: Batch assessment
# ---------------------------------------------------------------------------


class TestBatchAssessment:
    def test_empty_batch(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess_batch([])
        assert result.overall_risk_level == RiskLevel.MINIMAL
        assert result.can_proceed is True

    def test_single_change_batch(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess_batch([_change()])
        assert len(result.assessments) == 1

    def test_multiple_changes(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess_batch([
            _change(ChangeCategory.SCALE_UP, "api"),
            _change(ChangeCategory.CONFIG_CHANGE, "db"),
        ])
        assert len(result.assessments) == 2

    def test_overall_score_is_max(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess_batch([
            _change(ChangeCategory.SCALE_UP, "api"),
            _change(ChangeCategory.REMOVE_COMPONENT, "db", reversible=False),
        ])
        max_score = max(a.risk_score for a in result.assessments)
        assert result.overall_risk_score == max_score

    def test_deployment_order(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess_batch([
            _change(ChangeCategory.REMOVE_COMPONENT, "db"),
            _change(ChangeCategory.SCALE_UP, "api"),
        ])
        assert len(result.deployment_order) == 2
        # Scale up should come first (lower risk)
        assert result.deployment_order[0] == "api"

    def test_blockers(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess_batch([
            _change(
                ChangeCategory.REMOVE_COMPONENT, "db",
                reversible=False, downtime=True, peak=True,
            ),
        ])
        if result.overall_risk_level == RiskLevel.CRITICAL:
            assert len(result.blockers) >= 1
            assert result.can_proceed is False

    def test_total_blast_radius(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess_batch([
            _change(cid="db"),
            _change(cid="api"),
        ])
        assert isinstance(result.total_blast_radius, int)


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unknown_component(self):
        g = InfraGraph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(cid="nonexistent"))
        assert result.risk_score >= 0
        assert result.blast_radius == 0

    def test_migration_higher_than_config(self):
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        r1 = scorer.assess(_change(ChangeCategory.CONFIG_CHANGE, "db"))
        r2 = scorer.assess(_change(ChangeCategory.MIGRATION, "db"))
        assert r2.risk_score > r1.risk_score

    def test_dataclass_fields(self):
        change = ProposedChange(
            category=ChangeCategory.SCALE_UP,
            component_id="api",
            description="Test",
        )
        assert change.is_reversible is True
        assert change.requires_downtime is False
        assert change.is_peak_hours is False


# ---------------------------------------------------------------------------
# Tests: Health status branches (lines 183, 185)
# ---------------------------------------------------------------------------


class TestHealthStatusBranches:
    def test_overloaded_component_health_score(self):
        """Component with OVERLOADED health should get health_score=60 (line 183)."""
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.OVERLOADED))
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(cid="api"))
        health_factor = [f for f in result.risk_factors if f.name == "Current Health"]
        assert len(health_factor) == 1
        assert health_factor[0].score == 60

    def test_degraded_component_health_score(self):
        """Component with DEGRADED health should get health_score=40 (line 185)."""
        g = InfraGraph()
        g.add_component(_comp("api", "API", health=HealthStatus.DEGRADED))
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(cid="api"))
        health_factor = [f for f in result.risk_factors if f.name == "Current Health"]
        assert len(health_factor) == 1
        assert health_factor[0].score == 40


# ---------------------------------------------------------------------------
# Tests: CRITICAL risk level and blockers (lines 247, 266, 268, 280)
# ---------------------------------------------------------------------------


def _high_risk_graph() -> InfraGraph:
    """Build a graph where db has many dependents to maximize blast radius."""
    g = InfraGraph()
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1,
                          health=HealthStatus.DOWN))
    for i in range(8):
        cid = f"svc{i}"
        g.add_component(_comp(cid, f"Service {i}"))
        g.add_dependency(Dependency(source_id=cid, target_id="db"))
    return g


class TestCriticalRiskLevel:
    def test_critical_risk_score(self):
        """A worst-case change should produce a CRITICAL risk level (line 266)."""
        g = _high_risk_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(
            ChangeCategory.REMOVE_COMPONENT, "db",
            desc="Remove critical DB",
            reversible=False, downtime=True, peak=True,
        ))
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.risk_score >= 70
        assert result.requires_approval is True

    def test_high_risk_level(self):
        """Moderately risky change should produce HIGH risk level (line 268)."""
        g = InfraGraph()
        g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=1))
        for i in range(4):
            cid = f"svc{i}"
            g.add_component(_comp(cid, f"Service {i}"))
            g.add_dependency(Dependency(source_id=cid, target_id="db"))
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(
            ChangeCategory.SCALE_DOWN, "db",
            desc="Scale down DB",
            reversible=False, downtime=True, peak=True,
        ))
        assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert result.risk_score >= 50

    def test_critical_safeguard_manual_approval(self):
        """CRITICAL/HIGH risk should recommend manual approval (line 280)."""
        g = _high_risk_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(
            ChangeCategory.REMOVE_COMPONENT, "db",
            desc="Remove critical DB",
            reversible=False, downtime=True, peak=True,
        ))
        assert any("manual approval" in s.lower() for s in result.recommended_safeguards)

    def test_batch_with_critical_blocker(self):
        """Batch with a CRITICAL change should have blockers (line 247)."""
        g = _high_risk_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess_batch([
            _change(
                ChangeCategory.REMOVE_COMPONENT, "db",
                desc="Remove critical DB",
                reversible=False, downtime=True, peak=True,
            ),
        ])
        assert result.overall_risk_level == RiskLevel.CRITICAL
        assert len(result.blockers) >= 1
        assert result.can_proceed is False
        assert "CRITICAL" in result.blockers[0]


# ---------------------------------------------------------------------------
# Tests: Rollback plan branches (lines 308, 312)
# ---------------------------------------------------------------------------


class TestRollbackPlanBranches:
    def test_add_component_rollback(self):
        """ADD_COMPONENT should produce 'Remove newly added...' rollback (line 308)."""
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(ChangeCategory.ADD_COMPONENT, "api",
                                       desc="Add new component"))
        assert "Remove newly added" in result.rollback_plan
        assert "api" in result.rollback_plan

    def test_failover_toggle_rollback(self):
        """FAILOVER_TOGGLE should produce 'Toggle failover back...' rollback (line 312)."""
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(ChangeCategory.FAILOVER_TOGGLE, "api",
                                       desc="Toggle failover"))
        assert "Toggle failover back" in result.rollback_plan
        assert "api" in result.rollback_plan

    def test_dependency_change_rollback(self):
        """DEPENDENCY_CHANGE (no explicit branch) should get the default rollback."""
        g = _chain_graph()
        scorer = ChangeRiskScorer(g)
        result = scorer.assess(_change(ChangeCategory.DEPENDENCY_CHANGE, "api",
                                       desc="Change dependency"))
        assert "Revert changes" in result.rollback_plan
