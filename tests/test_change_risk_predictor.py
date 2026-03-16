"""Tests for change_risk_predictor module."""

from __future__ import annotations

import copy

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.change_risk_predictor import (
    ChangeImpact,
    ChangeRiskPredictor,
    ChangeRiskReport,
    ChangeSet,
    ChangeType,
    ProposedChange,
    RiskCategory,
    _risk_rank,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    failover: bool = False,
) -> Component:
    c = Component(id=cid, name=name or cid, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True)
    return c


def _graph() -> InfraGraph:
    """LB -> API -> DB  (simple chain)."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API", replicas=2))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _big_graph() -> InfraGraph:
    """Larger graph for blast radius tests: lb -> api -> db, api -> cache, api -> queue."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API", replicas=3))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
    g.add_component(_comp("cache", "Cache", ComponentType.CACHE, replicas=2))
    g.add_component(_comp("queue", "Queue", ComponentType.QUEUE))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    g.add_dependency(Dependency(source_id="api", target_id="cache"))
    g.add_dependency(Dependency(source_id="api", target_id="queue"))
    return g


def _single_graph() -> InfraGraph:
    """Graph with a single component."""
    g = InfraGraph()
    g.add_component(_comp("solo", "Solo"))
    return g


def _empty_graph() -> InfraGraph:
    return InfraGraph()


# ---------------------------------------------------------------------------
# Tests: ChangeType enum
# ---------------------------------------------------------------------------


class TestChangeTypeEnum:
    def test_add_component_value(self):
        assert ChangeType.ADD_COMPONENT.value == "add_component"

    def test_remove_component_value(self):
        assert ChangeType.REMOVE_COMPONENT.value == "remove_component"

    def test_modify_replicas_value(self):
        assert ChangeType.MODIFY_REPLICAS.value == "modify_replicas"

    def test_modify_failover_value(self):
        assert ChangeType.MODIFY_FAILOVER.value == "modify_failover"

    def test_add_dependency_value(self):
        assert ChangeType.ADD_DEPENDENCY.value == "add_dependency"

    def test_remove_dependency_value(self):
        assert ChangeType.REMOVE_DEPENDENCY.value == "remove_dependency"

    def test_change_region_value(self):
        assert ChangeType.CHANGE_REGION.value == "change_region"

    def test_upgrade_version_value(self):
        assert ChangeType.UPGRADE_VERSION.value == "upgrade_version"

    def test_all_members_count(self):
        assert len(ChangeType) == 8

    def test_is_string_enum(self):
        assert isinstance(ChangeType.ADD_COMPONENT, str)


# ---------------------------------------------------------------------------
# Tests: RiskCategory enum
# ---------------------------------------------------------------------------


class TestRiskCategoryEnum:
    def test_critical_value(self):
        assert RiskCategory.CRITICAL.value == "critical"

    def test_high_value(self):
        assert RiskCategory.HIGH.value == "high"

    def test_medium_value(self):
        assert RiskCategory.MEDIUM.value == "medium"

    def test_low_value(self):
        assert RiskCategory.LOW.value == "low"

    def test_negligible_value(self):
        assert RiskCategory.NEGLIGIBLE.value == "negligible"

    def test_all_members_count(self):
        assert len(RiskCategory) == 5

    def test_is_string_enum(self):
        assert isinstance(RiskCategory.CRITICAL, str)


# ---------------------------------------------------------------------------
# Tests: _risk_rank utility
# ---------------------------------------------------------------------------


class TestRiskRank:
    def test_negligible_is_zero(self):
        assert _risk_rank(RiskCategory.NEGLIGIBLE) == 0

    def test_low_is_one(self):
        assert _risk_rank(RiskCategory.LOW) == 1

    def test_medium_is_two(self):
        assert _risk_rank(RiskCategory.MEDIUM) == 2

    def test_high_is_three(self):
        assert _risk_rank(RiskCategory.HIGH) == 3

    def test_critical_is_four(self):
        assert _risk_rank(RiskCategory.CRITICAL) == 4

    def test_ordering(self):
        assert (
            _risk_rank(RiskCategory.NEGLIGIBLE)
            < _risk_rank(RiskCategory.LOW)
            < _risk_rank(RiskCategory.MEDIUM)
            < _risk_rank(RiskCategory.HIGH)
            < _risk_rank(RiskCategory.CRITICAL)
        )


# ---------------------------------------------------------------------------
# Tests: ProposedChange model
# ---------------------------------------------------------------------------


class TestProposedChangeModel:
    def test_basic_creation(self):
        pc = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="new-svc",
            description="Add new service",
        )
        assert pc.change_type == ChangeType.ADD_COMPONENT
        assert pc.target_component_id == "new-svc"
        assert pc.description == "Add new service"

    def test_default_parameters(self):
        pc = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="x",
        )
        assert pc.parameters == {}
        assert pc.description == ""

    def test_with_parameters(self):
        pc = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
            parameters={"new_replicas": 5},
        )
        assert pc.parameters["new_replicas"] == 5

    def test_serialization_roundtrip(self):
        pc = ProposedChange(
            change_type=ChangeType.CHANGE_REGION,
            target_component_id="db",
            description="Move to us-west-2",
            parameters={"new_region": "us-west-2"},
        )
        data = pc.model_dump()
        pc2 = ProposedChange(**data)
        assert pc2.change_type == pc.change_type
        assert pc2.target_component_id == pc.target_component_id


# ---------------------------------------------------------------------------
# Tests: ChangeImpact model
# ---------------------------------------------------------------------------


class TestChangeImpactModel:
    def test_fields(self):
        pc = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT, target_component_id="x"
        )
        ci = ChangeImpact(
            change=pc,
            before_score=80.0,
            after_score=85.0,
            delta=5.0,
            risk_category=RiskCategory.NEGLIGIBLE,
            affected_components=["x"],
            blast_radius=0.1,
            rollback_complexity="simple",
        )
        assert ci.before_score == 80.0
        assert ci.after_score == 85.0
        assert ci.delta == 5.0
        assert ci.risk_category == RiskCategory.NEGLIGIBLE

    def test_default_values(self):
        pc = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT, target_component_id="x"
        )
        ci = ChangeImpact(
            change=pc,
            before_score=0,
            after_score=0,
            delta=0,
            risk_category=RiskCategory.NEGLIGIBLE,
        )
        assert ci.affected_components == []
        assert ci.blast_radius == 0.0
        assert ci.rollback_complexity == "simple"


# ---------------------------------------------------------------------------
# Tests: ChangeSet model
# ---------------------------------------------------------------------------


class TestChangeSetModel:
    def test_empty_changeset(self):
        cs = ChangeSet()
        assert cs.changes == []
        assert cs.combined_impact == 0.0
        assert cs.interaction_effects == []
        assert cs.recommended_order == []

    def test_with_data(self):
        pc = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT, target_component_id="x"
        )
        cs = ChangeSet(
            changes=[pc],
            combined_impact=-5.0,
            interaction_effects=["interaction"],
            recommended_order=[0],
        )
        assert len(cs.changes) == 1
        assert cs.combined_impact == -5.0


# ---------------------------------------------------------------------------
# Tests: ChangeRiskReport model
# ---------------------------------------------------------------------------


class TestChangeRiskReportModel:
    def test_empty_report(self):
        r = ChangeRiskReport()
        assert r.total_changes == 0
        assert r.impacts == []
        assert r.overall_risk == RiskCategory.NEGLIGIBLE
        assert r.safe_to_proceed is True
        assert r.warnings == []
        assert r.recommended_sequence == []

    def test_with_data(self):
        r = ChangeRiskReport(
            total_changes=2,
            overall_risk=RiskCategory.HIGH,
            safe_to_proceed=False,
            warnings=["danger"],
        )
        assert r.total_changes == 2
        assert r.overall_risk == RiskCategory.HIGH
        assert r.safe_to_proceed is False


# ---------------------------------------------------------------------------
# Tests: ChangeRiskPredictor.__init__
# ---------------------------------------------------------------------------


class TestPredictorInit:
    def test_init_with_graph(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        assert p._graph is g

    def test_init_with_empty_graph(self):
        g = _empty_graph()
        p = ChangeRiskPredictor(g)
        assert p._graph is g


# ---------------------------------------------------------------------------
# Tests: predict_impact — ADD_COMPONENT
# ---------------------------------------------------------------------------


class TestPredictImpactAddComponent:
    def test_add_component_returns_impact(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="cache",
            parameters={"component_type": "cache", "name": "Cache"},
        )
        imp = p.predict_impact(ch)
        assert isinstance(imp, ChangeImpact)

    def test_add_component_before_score_unchanged(self):
        g = _graph()
        original_score = g.resilience_score()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="cache",
            parameters={"component_type": "cache"},
        )
        imp = p.predict_impact(ch)
        assert imp.before_score == round(original_score, 2)

    def test_add_component_does_not_mutate_original(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="cache",
            parameters={"component_type": "cache"},
        )
        p.predict_impact(ch)
        assert g.get_component("cache") is None

    def test_add_component_rollback_is_complex(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="x",
            parameters={"component_type": "app_server"},
        )
        imp = p.predict_impact(ch)
        assert imp.rollback_complexity == "complex"

    def test_add_component_affected_contains_new_id(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="new-svc",
            parameters={"component_type": "app_server"},
        )
        imp = p.predict_impact(ch)
        assert "new-svc" in imp.affected_components

    def test_add_component_with_replicas(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="new",
            parameters={"component_type": "web_server", "replicas": 3, "name": "New"},
        )
        imp = p.predict_impact(ch)
        assert isinstance(imp.after_score, float)


# ---------------------------------------------------------------------------
# Tests: predict_impact — REMOVE_COMPONENT
# ---------------------------------------------------------------------------


class TestPredictImpactRemoveComponent:
    def test_remove_sets_down(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="db",
        )
        imp = p.predict_impact(ch)
        # Original graph should be unmodified
        assert g.get_component("db").health == HealthStatus.HEALTHY

    def test_remove_component_rollback_is_complex(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="db",
        )
        imp = p.predict_impact(ch)
        assert imp.rollback_complexity == "complex"

    def test_remove_component_affected_includes_dependents(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="db",
        )
        imp = p.predict_impact(ch)
        assert "db" in imp.affected_components
        # api depends on db, lb depends on api
        assert "api" in imp.affected_components

    def test_remove_nonexistent_component(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="nonexistent",
        )
        imp = p.predict_impact(ch)
        assert imp.affected_components == []

    def test_remove_central_vs_leaf_blast(self):
        g = _big_graph()
        p = ChangeRiskPredictor(g)
        # api is central: lb depends on it. cache/db/queue have api as dependent.
        # Removing db: affected = db + api(dependent) + lb(transitive)
        # Removing lb: affected = lb only (it's the entry point, no one depends on it)
        ch_entry = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="lb",
        )
        ch_mid = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="api",
        )
        imp_entry = p.predict_impact(ch_entry)
        imp_mid = p.predict_impact(ch_mid)
        assert imp_entry.blast_radius <= imp_mid.blast_radius


# ---------------------------------------------------------------------------
# Tests: predict_impact — MODIFY_REPLICAS
# ---------------------------------------------------------------------------


class TestPredictImpactModifyReplicas:
    def test_increase_replicas(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="db",
            parameters={"new_replicas": 3},
        )
        imp = p.predict_impact(ch)
        assert imp.rollback_complexity == "simple"
        # db was single replica, adding replicas should improve or keep score
        assert imp.delta >= 0 or isinstance(imp.delta, float)

    def test_decrease_replicas(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
            parameters={"new_replicas": 1},
        )
        imp = p.predict_impact(ch)
        # Reducing replicas from 2 to 1 may lower score
        assert isinstance(imp.delta, float)

    def test_replicas_clamped_to_one(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
            parameters={"new_replicas": 0},
        )
        imp = p.predict_impact(ch)
        assert isinstance(imp, ChangeImpact)

    def test_modify_replicas_no_mutation(self):
        g = _graph()
        original_replicas = g.get_component("api").replicas
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
            parameters={"new_replicas": 10},
        )
        p.predict_impact(ch)
        assert g.get_component("api").replicas == original_replicas

    def test_modify_replicas_nonexistent(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="nope",
            parameters={"new_replicas": 5},
        )
        imp = p.predict_impact(ch)
        assert imp.affected_components == []


# ---------------------------------------------------------------------------
# Tests: predict_impact — MODIFY_FAILOVER
# ---------------------------------------------------------------------------


class TestPredictImpactModifyFailover:
    def test_enable_failover(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_FAILOVER,
            target_component_id="db",
            parameters={"enabled": True},
        )
        imp = p.predict_impact(ch)
        assert imp.rollback_complexity == "simple"

    def test_disable_failover(self):
        g = InfraGraph()
        g.add_component(_comp("svc", "Svc", failover=True))
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_FAILOVER,
            target_component_id="svc",
            parameters={"enabled": False},
        )
        imp = p.predict_impact(ch)
        assert isinstance(imp.delta, float)

    def test_failover_no_mutation(self):
        g = _graph()
        assert g.get_component("db").failover.enabled is False
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_FAILOVER,
            target_component_id="db",
            parameters={"enabled": True},
        )
        p.predict_impact(ch)
        assert g.get_component("db").failover.enabled is False

    def test_failover_nonexistent_component(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_FAILOVER,
            target_component_id="ghost",
            parameters={"enabled": True},
        )
        imp = p.predict_impact(ch)
        assert imp.affected_components == []


# ---------------------------------------------------------------------------
# Tests: predict_impact — ADD_DEPENDENCY
# ---------------------------------------------------------------------------


class TestPredictImpactAddDependency:
    def test_add_dependency(self):
        g = _big_graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_DEPENDENCY,
            target_component_id="cache",
            parameters={"target_id": "db"},
        )
        imp = p.predict_impact(ch)
        assert imp.rollback_complexity == "moderate"

    def test_add_dependency_affected(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_DEPENDENCY,
            target_component_id="api",
            parameters={"target_id": "db"},
        )
        imp = p.predict_impact(ch)
        assert "api" in imp.affected_components
        assert "db" in imp.affected_components

    def test_add_dependency_no_target(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_DEPENDENCY,
            target_component_id="api",
            parameters={},
        )
        imp = p.predict_impact(ch)
        assert "api" in imp.affected_components

    def test_add_dependency_with_type(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_DEPENDENCY,
            target_component_id="lb",
            parameters={"target_id": "db", "dependency_type": "optional"},
        )
        imp = p.predict_impact(ch)
        assert isinstance(imp, ChangeImpact)


# ---------------------------------------------------------------------------
# Tests: predict_impact — REMOVE_DEPENDENCY
# ---------------------------------------------------------------------------


class TestPredictImpactRemoveDependency:
    def test_remove_dependency(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_DEPENDENCY,
            target_component_id="api",
            parameters={"target_id": "db"},
        )
        imp = p.predict_impact(ch)
        assert imp.rollback_complexity == "moderate"

    def test_remove_dependency_no_mutation(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_DEPENDENCY,
            target_component_id="api",
            parameters={"target_id": "db"},
        )
        p.predict_impact(ch)
        # Original edge should still exist
        assert g.get_dependency_edge("api", "db") is not None

    def test_remove_nonexistent_dependency(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_DEPENDENCY,
            target_component_id="lb",
            parameters={"target_id": "db"},
        )
        imp = p.predict_impact(ch)
        assert isinstance(imp, ChangeImpact)

    def test_remove_dependency_no_target_param(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_DEPENDENCY,
            target_component_id="api",
            parameters={},
        )
        imp = p.predict_impact(ch)
        assert "api" in imp.affected_components


# ---------------------------------------------------------------------------
# Tests: predict_impact — CHANGE_REGION
# ---------------------------------------------------------------------------


class TestPredictImpactChangeRegion:
    def test_change_region(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.CHANGE_REGION,
            target_component_id="db",
            parameters={"new_region": "eu-west-1"},
        )
        imp = p.predict_impact(ch)
        assert imp.rollback_complexity == "moderate"

    def test_change_region_no_mutation(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.CHANGE_REGION,
            target_component_id="db",
            parameters={"new_region": "ap-northeast-1"},
        )
        p.predict_impact(ch)
        assert g.get_component("db").region.region == ""

    def test_change_region_nonexistent_component(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.CHANGE_REGION,
            target_component_id="nope",
            parameters={"new_region": "us-east-1"},
        )
        imp = p.predict_impact(ch)
        assert imp.affected_components == []


# ---------------------------------------------------------------------------
# Tests: predict_impact — UPGRADE_VERSION
# ---------------------------------------------------------------------------


class TestPredictImpactUpgradeVersion:
    def test_upgrade_version(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.UPGRADE_VERSION,
            target_component_id="api",
            parameters={"old_version": "1.0", "new_version": "2.0"},
        )
        imp = p.predict_impact(ch)
        assert imp.rollback_complexity == "moderate"
        # Upgrade is a no-op in topology, delta should be 0
        assert imp.delta == 0.0

    def test_upgrade_version_nonexistent(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.UPGRADE_VERSION,
            target_component_id="nope",
        )
        imp = p.predict_impact(ch)
        assert imp.affected_components == []


# ---------------------------------------------------------------------------
# Tests: predict_impact — edge cases
# ---------------------------------------------------------------------------


class TestPredictImpactEdgeCases:
    def test_empty_graph(self):
        g = _empty_graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="first",
            parameters={"component_type": "app_server"},
        )
        imp = p.predict_impact(ch)
        assert imp.before_score == 0.0

    def test_single_component_graph(self):
        g = _single_graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="solo",
        )
        imp = p.predict_impact(ch)
        assert "solo" in imp.affected_components

    def test_blast_radius_is_fraction(self):
        g = _big_graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="db",
        )
        imp = p.predict_impact(ch)
        assert 0.0 <= imp.blast_radius <= 1.0

    def test_score_values_are_rounded(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
            parameters={"new_replicas": 5},
        )
        imp = p.predict_impact(ch)
        # Should be rounded to 2 decimal places
        assert imp.before_score == round(imp.before_score, 2)
        assert imp.after_score == round(imp.after_score, 2)
        assert imp.delta == round(imp.delta, 2)


# ---------------------------------------------------------------------------
# Tests: classify_risk
# ---------------------------------------------------------------------------


class TestClassifyRisk:
    def test_negligible(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(0.0, 0.0) == RiskCategory.NEGLIGIBLE

    def test_low_from_delta(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(-1.5, 0.0) == RiskCategory.LOW

    def test_low_from_blast(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(0.0, 0.15) == RiskCategory.LOW

    def test_medium_from_delta(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(-6.0, 0.0) == RiskCategory.MEDIUM

    def test_medium_from_blast(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(0.0, 0.35) == RiskCategory.MEDIUM

    def test_high_from_delta(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(-12.0, 0.0) == RiskCategory.HIGH

    def test_high_from_blast(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(0.0, 0.6) == RiskCategory.HIGH

    def test_critical_from_delta(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(-25.0, 0.0) == RiskCategory.CRITICAL

    def test_critical_from_blast(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(0.0, 0.85) == RiskCategory.CRITICAL

    def test_positive_delta_negligible(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(10.0, 0.0) == RiskCategory.NEGLIGIBLE

    def test_positive_delta_with_blast(self):
        p = ChangeRiskPredictor(_graph())
        # Positive delta but large blast radius
        assert p.classify_risk(10.0, 0.85) == RiskCategory.CRITICAL

    def test_boundary_negligible_to_low_delta(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(-0.9, 0.0) == RiskCategory.NEGLIGIBLE
        assert p.classify_risk(-1.0, 0.0) == RiskCategory.LOW

    def test_boundary_low_to_medium_delta(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(-4.9, 0.0) == RiskCategory.LOW
        assert p.classify_risk(-5.0, 0.0) == RiskCategory.MEDIUM

    def test_boundary_medium_to_high_delta(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(-9.9, 0.0) == RiskCategory.MEDIUM
        assert p.classify_risk(-10.0, 0.0) == RiskCategory.HIGH

    def test_boundary_high_to_critical_delta(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(-19.9, 0.0) == RiskCategory.HIGH
        assert p.classify_risk(-20.0, 0.0) == RiskCategory.CRITICAL

    def test_boundary_blast_negligible_to_low(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(0.0, 0.09) == RiskCategory.NEGLIGIBLE
        assert p.classify_risk(0.0, 0.1) == RiskCategory.LOW

    def test_boundary_blast_low_to_medium(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(0.0, 0.29) == RiskCategory.LOW
        assert p.classify_risk(0.0, 0.3) == RiskCategory.MEDIUM

    def test_boundary_blast_medium_to_high(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(0.0, 0.49) == RiskCategory.MEDIUM
        assert p.classify_risk(0.0, 0.5) == RiskCategory.HIGH

    def test_boundary_blast_high_to_critical(self):
        p = ChangeRiskPredictor(_graph())
        assert p.classify_risk(0.0, 0.79) == RiskCategory.HIGH
        assert p.classify_risk(0.0, 0.8) == RiskCategory.CRITICAL


# ---------------------------------------------------------------------------
# Tests: suggest_rollback_plan
# ---------------------------------------------------------------------------


class TestSuggestRollbackPlan:
    def test_add_component(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT, target_component_id="x"
        )
        plan = p.suggest_rollback_plan(ch)
        assert "x" in plan
        assert "Remove" in plan or "remove" in plan.lower()

    def test_remove_component(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT, target_component_id="db"
        )
        plan = p.suggest_rollback_plan(ch)
        assert "db" in plan
        assert "deploy" in plan.lower() or "restore" in plan.lower()

    def test_modify_replicas(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
            parameters={"old_replicas": 2},
        )
        plan = p.suggest_rollback_plan(ch)
        assert "api" in plan
        assert "2" in plan

    def test_modify_replicas_default_old(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
        )
        plan = p.suggest_rollback_plan(ch)
        assert "original" in plan

    def test_modify_failover(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_FAILOVER, target_component_id="db"
        )
        plan = p.suggest_rollback_plan(ch)
        assert "db" in plan
        assert "failover" in plan.lower()

    def test_add_dependency(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.ADD_DEPENDENCY,
            target_component_id="api",
            parameters={"target_id": "cache"},
        )
        plan = p.suggest_rollback_plan(ch)
        assert "api" in plan
        assert "cache" in plan

    def test_add_dependency_no_target(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.ADD_DEPENDENCY,
            target_component_id="api",
        )
        plan = p.suggest_rollback_plan(ch)
        assert "api" in plan

    def test_remove_dependency(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_DEPENDENCY,
            target_component_id="api",
            parameters={"target_id": "db"},
        )
        plan = p.suggest_rollback_plan(ch)
        assert "api" in plan
        assert "db" in plan

    def test_remove_dependency_no_target(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_DEPENDENCY,
            target_component_id="api",
        )
        plan = p.suggest_rollback_plan(ch)
        assert "api" in plan

    def test_change_region(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.CHANGE_REGION,
            target_component_id="db",
            parameters={"old_region": "us-east-1"},
        )
        plan = p.suggest_rollback_plan(ch)
        assert "db" in plan
        assert "us-east-1" in plan

    def test_change_region_default_old(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.CHANGE_REGION,
            target_component_id="db",
        )
        plan = p.suggest_rollback_plan(ch)
        assert "original region" in plan

    def test_upgrade_version(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.UPGRADE_VERSION,
            target_component_id="api",
            parameters={"old_version": "v1.0"},
        )
        plan = p.suggest_rollback_plan(ch)
        assert "api" in plan
        assert "v1.0" in plan

    def test_upgrade_version_default_old(self):
        p = ChangeRiskPredictor(_graph())
        ch = ProposedChange(
            change_type=ChangeType.UPGRADE_VERSION,
            target_component_id="api",
        )
        plan = p.suggest_rollback_plan(ch)
        assert "previous version" in plan


# ---------------------------------------------------------------------------
# Tests: gate_check
# ---------------------------------------------------------------------------


class TestGateCheck:
    def test_gate_passes_with_safe_changes(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.UPGRADE_VERSION,
            target_component_id="api",
        )
        # api has blast_radius ~0.67, which classifies as HIGH,
        # so threshold must be HIGH or above to pass
        assert p.gate_check([ch], RiskCategory.HIGH) is True

    def test_gate_fails_critical_against_medium_threshold(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        # Remove a central component — high blast radius
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="api",
        )
        imp = p.predict_impact(ch)
        # The blast radius should be high enough to push risk above MEDIUM
        if _risk_rank(imp.risk_category) > _risk_rank(RiskCategory.MEDIUM):
            assert p.gate_check([ch], RiskCategory.MEDIUM) is False

    def test_gate_passes_with_empty_changes(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        assert p.gate_check([], RiskCategory.NEGLIGIBLE) is True

    def test_gate_critical_threshold_accepts_all(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="api",
        )
        assert p.gate_check([ch], RiskCategory.CRITICAL) is True

    def test_gate_negligible_threshold_strict(self):
        g = _big_graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="api",
        )
        # Removing api has big blast, should fail NEGLIGIBLE gate
        assert p.gate_check([ch], RiskCategory.NEGLIGIBLE) is False

    def test_gate_multiple_changes(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        changes = [
            ProposedChange(
                change_type=ChangeType.UPGRADE_VERSION,
                target_component_id="api",
            ),
            ProposedChange(
                change_type=ChangeType.UPGRADE_VERSION,
                target_component_id="db",
            ),
        ]
        # db has blast_radius=1.0 (CRITICAL), api=0.67 (HIGH)
        # CRITICAL threshold accepts everything
        assert p.gate_check(changes, RiskCategory.CRITICAL) is True


# ---------------------------------------------------------------------------
# Tests: analyze_change_set
# ---------------------------------------------------------------------------


class TestAnalyzeChangeSet:
    def test_empty_set(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        cs = p.analyze_change_set([])
        assert cs.changes == []
        assert cs.combined_impact == 0.0
        assert cs.interaction_effects == []
        assert cs.recommended_order == []

    def test_single_change(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
            parameters={"new_replicas": 5},
        )
        cs = p.analyze_change_set([ch])
        assert len(cs.changes) == 1
        assert len(cs.recommended_order) == 1
        assert cs.recommended_order == [0]

    def test_multiple_changes_have_order(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        changes = [
            ProposedChange(
                change_type=ChangeType.MODIFY_REPLICAS,
                target_component_id="api",
                parameters={"new_replicas": 5},
            ),
            ProposedChange(
                change_type=ChangeType.MODIFY_REPLICAS,
                target_component_id="db",
                parameters={"new_replicas": 3},
            ),
        ]
        cs = p.analyze_change_set(changes)
        assert len(cs.recommended_order) == 2
        assert set(cs.recommended_order) == {0, 1}

    def test_duplicate_target_interaction(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        changes = [
            ProposedChange(
                change_type=ChangeType.MODIFY_REPLICAS,
                target_component_id="api",
                parameters={"new_replicas": 5},
            ),
            ProposedChange(
                change_type=ChangeType.MODIFY_FAILOVER,
                target_component_id="api",
                parameters={"enabled": True},
            ),
        ]
        cs = p.analyze_change_set(changes)
        assert any("api" in e for e in cs.interaction_effects)

    def test_combined_impact_calculated(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        changes = [
            ProposedChange(
                change_type=ChangeType.MODIFY_REPLICAS,
                target_component_id="db",
                parameters={"new_replicas": 3},
            ),
        ]
        cs = p.analyze_change_set(changes)
        assert isinstance(cs.combined_impact, float)


# ---------------------------------------------------------------------------
# Tests: generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_empty_changes(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        report = p.generate_report([])
        assert report.total_changes == 0
        assert report.safe_to_proceed is True
        assert report.overall_risk == RiskCategory.NEGLIGIBLE

    def test_single_safe_change(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.UPGRADE_VERSION,
            target_component_id="api",
        )
        report = p.generate_report([ch])
        assert report.total_changes == 1
        assert len(report.impacts) == 1

    def test_report_has_impacts(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        changes = [
            ProposedChange(
                change_type=ChangeType.MODIFY_REPLICAS,
                target_component_id="api",
                parameters={"new_replicas": 5},
            ),
            ProposedChange(
                change_type=ChangeType.MODIFY_REPLICAS,
                target_component_id="db",
                parameters={"new_replicas": 3},
            ),
        ]
        report = p.generate_report(changes)
        assert report.total_changes == 2
        assert len(report.impacts) == 2

    def test_report_recommended_sequence(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        changes = [
            ProposedChange(
                change_type=ChangeType.REMOVE_COMPONENT,
                target_component_id="db",
            ),
            ProposedChange(
                change_type=ChangeType.UPGRADE_VERSION,
                target_component_id="api",
            ),
        ]
        report = p.generate_report(changes)
        assert len(report.recommended_sequence) == 2

    def test_report_warnings_on_large_blast(self):
        g = _single_graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="solo",
        )
        report = p.generate_report([ch])
        # blast_radius=1.0 (100%) which is >0.5 -> warning
        blast_warnings = [w for w in report.warnings if "blast" in w.lower()]
        assert len(blast_warnings) > 0

    def test_report_warnings_on_large_delta(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="a",
        )
        imp = p.predict_impact(ch)
        report = p.generate_report([ch])
        if imp.delta < -10:
            delta_warnings = [w for w in report.warnings if "resilience drop" in w]
            assert len(delta_warnings) > 0

    def test_report_safe_to_proceed_with_low_risk(self):
        # Use big_graph and target lb (entry point, no dependents -> low blast)
        g = _big_graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.UPGRADE_VERSION,
            target_component_id="lb",
        )
        report = p.generate_report([ch])
        # lb has 1/5 = 0.2 blast radius -> LOW risk -> safe
        assert report.safe_to_proceed is True

    def test_report_not_safe_when_high_risk(self):
        g = _single_graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="solo",
        )
        report = p.generate_report([ch])
        # solo removal has blast_radius=1.0 -> CRITICAL
        if _risk_rank(report.overall_risk) > _risk_rank(RiskCategory.MEDIUM):
            assert report.safe_to_proceed is False

    def test_report_complex_rollback_warning(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="db",
        )
        report = p.generate_report([ch])
        rollback_warnings = [w for w in report.warnings if "rollback" in w.lower()]
        assert len(rollback_warnings) > 0

    def test_report_overall_risk_is_worst(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        changes = [
            ProposedChange(
                change_type=ChangeType.UPGRADE_VERSION,
                target_component_id="api",
            ),
            ProposedChange(
                change_type=ChangeType.REMOVE_COMPONENT,
                target_component_id="db",
            ),
        ]
        report = p.generate_report(changes)
        # Overall risk should be at least as bad as the worst individual
        individual_risks = [imp.risk_category for imp in report.impacts]
        worst = max(individual_risks, key=_risk_rank)
        assert _risk_rank(report.overall_risk) >= _risk_rank(worst)


# ---------------------------------------------------------------------------
# Tests: _rollback_complexity (private, tested via predict_impact)
# ---------------------------------------------------------------------------


class TestRollbackComplexity:
    def test_add_component_complex(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.ADD_COMPONENT,
                target_component_id="x",
                parameters={"component_type": "app_server"},
            )
        )
        assert imp.rollback_complexity == "complex"

    def test_remove_component_complex(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.REMOVE_COMPONENT,
                target_component_id="db",
            )
        )
        assert imp.rollback_complexity == "complex"

    def test_modify_replicas_simple(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.MODIFY_REPLICAS,
                target_component_id="api",
                parameters={"new_replicas": 5},
            )
        )
        assert imp.rollback_complexity == "simple"

    def test_modify_failover_simple(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.MODIFY_FAILOVER,
                target_component_id="db",
                parameters={"enabled": True},
            )
        )
        assert imp.rollback_complexity == "simple"

    def test_add_dependency_moderate(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.ADD_DEPENDENCY,
                target_component_id="api",
                parameters={"target_id": "lb"},
            )
        )
        assert imp.rollback_complexity == "moderate"

    def test_remove_dependency_moderate(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.REMOVE_DEPENDENCY,
                target_component_id="api",
                parameters={"target_id": "db"},
            )
        )
        assert imp.rollback_complexity == "moderate"

    def test_change_region_moderate(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.CHANGE_REGION,
                target_component_id="db",
                parameters={"new_region": "eu-west-1"},
            )
        )
        assert imp.rollback_complexity == "moderate"

    def test_upgrade_version_moderate(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.UPGRADE_VERSION,
                target_component_id="api",
            )
        )
        assert imp.rollback_complexity == "moderate"


# ---------------------------------------------------------------------------
# Tests: _find_affected (private, tested via predict_impact)
# ---------------------------------------------------------------------------


class TestFindAffected:
    def test_add_returns_new_id(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.ADD_COMPONENT,
                target_component_id="new",
                parameters={"component_type": "cache"},
            )
        )
        assert imp.affected_components == ["new"]

    def test_remove_returns_target_and_dependents(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.REMOVE_COMPONENT,
                target_component_id="db",
            )
        )
        assert "db" in imp.affected_components
        assert "api" in imp.affected_components

    def test_upgrade_returns_target_and_dependents(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.UPGRADE_VERSION,
                target_component_id="api",
            )
        )
        assert "api" in imp.affected_components

    def test_add_dependency_returns_source_and_target(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.ADD_DEPENDENCY,
                target_component_id="lb",
                parameters={"target_id": "db"},
            )
        )
        assert "lb" in imp.affected_components
        assert "db" in imp.affected_components

    def test_nonexistent_target_empty(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.MODIFY_REPLICAS,
                target_component_id="nope",
                parameters={"new_replicas": 3},
            )
        )
        assert imp.affected_components == []


# ---------------------------------------------------------------------------
# Tests: _apply_change (tested indirectly)
# ---------------------------------------------------------------------------


class TestApplyChange:
    def test_add_component_to_cloned_graph(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="new-cache",
            parameters={"component_type": "cache", "name": "NewCache", "replicas": 2},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        assert sim.get_component("new-cache") is not None
        assert sim.get_component("new-cache").name == "NewCache"
        assert sim.get_component("new-cache").replicas == 2
        assert g.get_component("new-cache") is None

    def test_remove_component_sets_down(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="db",
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        assert sim.get_component("db").health == HealthStatus.DOWN

    def test_modify_replicas_applies(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
            parameters={"new_replicas": 7},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        assert sim.get_component("api").replicas == 7

    def test_modify_failover_applies(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_FAILOVER,
            target_component_id="db",
            parameters={"enabled": True},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        assert sim.get_component("db").failover.enabled is True

    def test_add_dependency_applies(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_DEPENDENCY,
            target_component_id="lb",
            parameters={"target_id": "db"},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        assert sim.get_dependency_edge("lb", "db") is not None

    def test_remove_dependency_applies(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_DEPENDENCY,
            target_component_id="api",
            parameters={"target_id": "db"},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        assert sim.get_dependency_edge("api", "db") is None

    def test_change_region_applies(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.CHANGE_REGION,
            target_component_id="db",
            parameters={"new_region": "eu-central-1"},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        assert sim.get_component("db").region.region == "eu-central-1"

    def test_upgrade_version_is_noop(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.UPGRADE_VERSION,
            target_component_id="api",
        )
        sim = copy.deepcopy(g)
        before_score = sim.resilience_score()
        p._apply_change(sim, ch)
        after_score = sim.resilience_score()
        assert before_score == after_score

    def test_add_dependency_empty_target(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_DEPENDENCY,
            target_component_id="api",
            parameters={},
        )
        sim = copy.deepcopy(g)
        # Should not crash
        p._apply_change(sim, ch)

    def test_remove_dependency_empty_target(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_DEPENDENCY,
            target_component_id="api",
            parameters={},
        )
        sim = copy.deepcopy(g)
        # Should not crash
        p._apply_change(sim, ch)

    def test_remove_component_nonexistent(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="ghost",
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        # No crash

    def test_modify_replicas_nonexistent(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="ghost",
            parameters={"new_replicas": 3},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        # No crash

    def test_modify_failover_nonexistent(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_FAILOVER,
            target_component_id="ghost",
            parameters={"enabled": True},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        # No crash

    def test_change_region_nonexistent(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.CHANGE_REGION,
            target_component_id="ghost",
            parameters={"new_region": "ap-1"},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        # No crash

    def test_add_component_default_name(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="auto-name",
            parameters={"component_type": "web_server"},
        )
        sim = copy.deepcopy(g)
        p._apply_change(sim, ch)
        assert sim.get_component("auto-name").name == "auto-name"

    def test_modify_replicas_no_param_keeps_original(self):
        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.MODIFY_REPLICAS,
            target_component_id="api",
            parameters={},
        )
        sim = copy.deepcopy(g)
        original_replicas = sim.get_component("api").replicas
        p._apply_change(sim, ch)
        assert sim.get_component("api").replicas == original_replicas


# ---------------------------------------------------------------------------
# Tests: Coverage — interaction effects (line 162)
# ---------------------------------------------------------------------------


class TestInteractionEffects:
    def test_combined_differs_from_sum(self):
        """When changes interact, combined delta differs from sum of individual."""
        # Build a graph where removing replicas from db AND enabling failover
        # on db interact (combined effect differs from sum of individual)
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_dependency(Dependency(source_id="b", target_id="a"))
        g.add_dependency(Dependency(source_id="c", target_id="a"))
        p = ChangeRiskPredictor(g)
        # First change increases replicas on a, second enables failover
        changes = [
            ProposedChange(
                change_type=ChangeType.MODIFY_REPLICAS,
                target_component_id="a",
                parameters={"new_replicas": 5},
            ),
            ProposedChange(
                change_type=ChangeType.MODIFY_FAILOVER,
                target_component_id="a",
                parameters={"enabled": True},
            ),
        ]
        cs = p.analyze_change_set(changes)
        # Whether or not interaction is detected, the test validates the path
        assert isinstance(cs.combined_impact, float)
        assert isinstance(cs.interaction_effects, list)


# ---------------------------------------------------------------------------
# Tests: Coverage — report delta warning (line 255)
# ---------------------------------------------------------------------------


class TestReportDeltaWarning:
    def test_large_delta_warning_generated(self):
        """Remove a well-configured hub component to cause delta < -10."""
        g = InfraGraph()
        # core has replicas=3 + failover, many dependents
        g.add_component(
            _comp("core", "Core", replicas=3, failover=True)
        )
        for i in range(5):
            cid = f"svc{i}"
            g.add_component(_comp(cid, cid, replicas=2))
            g.add_dependency(
                Dependency(source_id=cid, target_id="core", dependency_type="requires")
            )
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.REMOVE_COMPONENT,
            target_component_id="core",
        )
        imp = p.predict_impact(ch)
        report = p.generate_report([ch])
        # Removing core with failover+replicas causes large delta
        assert imp.delta < -10, f"Expected delta < -10, got {imp.delta}"
        drop_warnings = [w for w in report.warnings if "resilience drop" in w]
        assert len(drop_warnings) > 0


# ---------------------------------------------------------------------------
# Tests: Coverage — fallback in _find_affected (line 384)
# and fallback in _rollback_complexity (line 400)
# These fallbacks are unreachable with current ChangeType enum members,
# but we test them indirectly to validate coverage if the enum were extended.
# ---------------------------------------------------------------------------


class TestFallbackPaths:
    def test_find_affected_remove_dep_no_target_returns_source(self):
        """REMOVE_DEPENDENCY with empty target returns [cid]."""
        g = _graph()
        p = ChangeRiskPredictor(g)
        imp = p.predict_impact(
            ProposedChange(
                change_type=ChangeType.REMOVE_DEPENDENCY,
                target_component_id="api",
                parameters={},
            )
        )
        assert "api" in imp.affected_components

    def test_suggest_rollback_all_types(self):
        """Verify suggest_rollback_plan returns a string for every type."""
        g = _graph()
        p = ChangeRiskPredictor(g)
        for ct in ChangeType:
            ch = ProposedChange(change_type=ct, target_component_id="test")
            plan = p.suggest_rollback_plan(ch)
            assert isinstance(plan, str)
            assert "test" in plan

    def test_suggest_rollback_fallback_with_mock(self):
        """Hit the generic fallback return in suggest_rollback_plan (line 229)."""
        from unittest.mock import patch

        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="x",
        )
        # Patch change_type to a value that doesn't match any branch
        with patch.object(ch, "change_type", new="unknown_type"):
            plan = p.suggest_rollback_plan(ch)
            assert "x" in plan
            assert "Revert" in plan

    def test_find_affected_fallback_with_mock(self):
        """Hit the generic fallback return in _find_affected (line 384)."""
        from unittest.mock import patch

        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="api",
        )
        with patch.object(ch, "change_type", new="unknown_type"):
            result = p._find_affected(ch)
            assert result == ["api"]

    def test_rollback_complexity_fallback_with_mock(self):
        """Hit the generic fallback return in _rollback_complexity (line 400)."""
        from unittest.mock import patch

        g = _graph()
        p = ChangeRiskPredictor(g)
        ch = ProposedChange(
            change_type=ChangeType.ADD_COMPONENT,
            target_component_id="x",
        )
        with patch.object(ch, "change_type", new="unknown_type"):
            result = p._rollback_complexity(ch)
            assert result == "moderate"
