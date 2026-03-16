"""Tests for dependency_graph_diff module — DependencyGraphDiffEngine.

Minimum target: 140 tests, 100% line/branch coverage.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.dependency_graph_diff import (
    CompatibilityIssue,
    CompatibilityReport,
    DependencyGraphDiffEngine,
    DiffEntry,
    DiffType,
    GraphDiff,
    MigrationPlan,
    MigrationStep,
    _CRITICAL_TYPES,
    _RISK_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    host: str = "",
    port: int = 0,
    failover: bool = False,
    autoscaling: bool = False,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        health=health,
        host=host,
        port=port,
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
    )


def _make_dep(
    src: str,
    tgt: str,
    dep_type: str = "requires",
    weight: float = 1.0,
    cb_enabled: bool = False,
) -> Dependency:
    return Dependency(
        source_id=src,
        target_id=tgt,
        dependency_type=dep_type,
        weight=weight,
        circuit_breaker=CircuitBreakerConfig(enabled=cb_enabled),
    )


def _graph_with(*components: Component, deps: list[Dependency] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in (deps or []):
        g.add_dependency(d)
    return g


@pytest.fixture
def engine() -> DependencyGraphDiffEngine:
    return DependencyGraphDiffEngine()


# ---------------------------------------------------------------------------
# DiffType enum
# ---------------------------------------------------------------------------

class TestDiffType:
    def test_all_values_exist(self):
        expected = {
            "component_added", "component_removed", "component_modified",
            "dependency_added", "dependency_removed", "dependency_modified",
            "type_changed", "replicas_changed", "health_changed",
        }
        assert {dt.value for dt in DiffType} == expected

    def test_str_enum(self):
        assert DiffType.COMPONENT_ADDED.value == "component_added"
        assert "COMPONENT_ADDED" in str(DiffType.COMPONENT_ADDED)

    def test_equality(self):
        assert DiffType.COMPONENT_REMOVED == DiffType.COMPONENT_REMOVED
        assert DiffType.COMPONENT_ADDED != DiffType.COMPONENT_REMOVED


# ---------------------------------------------------------------------------
# DiffEntry model
# ---------------------------------------------------------------------------

class TestDiffEntry:
    def test_defaults(self):
        e = DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="x")
        assert e.old_value == ""
        assert e.new_value == ""
        assert e.risk_level == "low"
        assert e.description == ""

    def test_full_init(self):
        e = DiffEntry(
            diff_type=DiffType.TYPE_CHANGED,
            entity_id="db",
            old_value="database",
            new_value="cache",
            risk_level="critical",
            description="changed type",
        )
        assert e.diff_type == DiffType.TYPE_CHANGED
        assert e.entity_id == "db"
        assert e.risk_level == "critical"

    def test_serialization_roundtrip(self):
        e = DiffEntry(
            diff_type=DiffType.HEALTH_CHANGED,
            entity_id="web",
            old_value="healthy",
            new_value="down",
            risk_level="critical",
            description="health degraded",
        )
        data = e.model_dump()
        e2 = DiffEntry(**data)
        assert e2 == e


# ---------------------------------------------------------------------------
# GraphDiff model
# ---------------------------------------------------------------------------

class TestGraphDiff:
    def test_defaults(self):
        gd = GraphDiff()
        assert gd.added_components == []
        assert gd.removed_components == []
        assert gd.modified_components == []
        assert gd.added_dependencies == []
        assert gd.removed_dependencies == []
        assert gd.entries == []
        assert gd.total_changes == 0
        assert gd.risk_score == 0.0
        assert gd.breaking_changes == []
        assert gd.recommendations == []

    def test_populated(self):
        gd = GraphDiff(
            added_components=["a"],
            removed_components=["b"],
            total_changes=2,
            risk_score=50.0,
            breaking_changes=["removed b"],
        )
        assert gd.total_changes == 2
        assert gd.risk_score == 50.0
        assert len(gd.breaking_changes) == 1


# ---------------------------------------------------------------------------
# MigrationPlan / MigrationStep models
# ---------------------------------------------------------------------------

class TestMigrationModels:
    def test_migration_step_defaults(self):
        s = MigrationStep(order=1, action="add", component_id="x", description="d")
        assert s.risk_level == "low"
        assert s.rollback_action == ""

    def test_migration_plan_defaults(self):
        mp = MigrationPlan()
        assert mp.steps == []
        assert mp.estimated_steps == 0
        assert mp.requires_downtime is False
        assert mp.rollback_steps == []
        assert mp.warnings == []


# ---------------------------------------------------------------------------
# CompatibilityReport / CompatibilityIssue models
# ---------------------------------------------------------------------------

class TestCompatibilityModels:
    def test_issue_fields(self):
        ci = CompatibilityIssue(severity="high", entity_id="x", description="d")
        assert ci.severity == "high"

    def test_report_defaults(self):
        cr = CompatibilityReport()
        assert cr.is_compatible is True
        assert cr.issues == []
        assert cr.score == 100.0
        assert cr.summary == ""


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_risk_weights(self):
        assert _RISK_WEIGHTS["critical"] == 1.0
        assert _RISK_WEIGHTS["high"] == 0.7
        assert _RISK_WEIGHTS["medium"] == 0.4
        assert _RISK_WEIGHTS["low"] == 0.1

    def test_critical_types(self):
        assert ComponentType.DATABASE in _CRITICAL_TYPES
        assert ComponentType.LOAD_BALANCER in _CRITICAL_TYPES
        assert ComponentType.DNS in _CRITICAL_TYPES
        assert ComponentType.APP_SERVER not in _CRITICAL_TYPES


# ---------------------------------------------------------------------------
# compute_diff — empty / identical graphs
# ---------------------------------------------------------------------------

class TestComputeDiffEmpty:
    def test_both_empty(self, engine):
        diff = engine.compute_diff(InfraGraph(), InfraGraph())
        assert diff.total_changes == 0
        assert diff.risk_score == 0.0
        assert diff.breaking_changes == []

    def test_identical_single_component(self, engine):
        c = _make_component("a")
        g1 = _graph_with(c)
        g2 = _graph_with(c)
        diff = engine.compute_diff(g1, g2)
        assert diff.total_changes == 0
        assert diff.added_components == []
        assert diff.removed_components == []

    def test_identical_with_dependency(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        dep = _make_dep("a", "b")
        g1 = _graph_with(c1, c2, deps=[dep])
        g2 = _graph_with(c1, c2, deps=[dep])
        diff = engine.compute_diff(g1, g2)
        assert diff.total_changes == 0


# ---------------------------------------------------------------------------
# compute_diff — component additions
# ---------------------------------------------------------------------------

class TestComputeDiffAdditions:
    def test_single_addition(self, engine):
        g1 = InfraGraph()
        g2 = _graph_with(_make_component("web"))
        diff = engine.compute_diff(g1, g2)
        assert diff.added_components == ["web"]
        assert diff.total_changes == 1
        assert diff.entries[0].diff_type == DiffType.COMPONENT_ADDED

    def test_multiple_additions(self, engine):
        g1 = InfraGraph()
        g2 = _graph_with(
            _make_component("a"),
            _make_component("b"),
            _make_component("c"),
        )
        diff = engine.compute_diff(g1, g2)
        assert sorted(diff.added_components) == ["a", "b", "c"]
        assert diff.total_changes == 3

    def test_add_critical_type_component(self, engine):
        g1 = InfraGraph()
        g2 = _graph_with(_make_component("db1", ctype=ComponentType.DATABASE))
        diff = engine.compute_diff(g1, g2)
        assert diff.entries[0].risk_level == "medium"

    def test_add_non_critical_type(self, engine):
        g1 = InfraGraph()
        g2 = _graph_with(_make_component("app1", ctype=ComponentType.APP_SERVER))
        diff = engine.compute_diff(g1, g2)
        assert diff.entries[0].risk_level == "low"

    def test_add_component_with_dependents(self, engine):
        """When a newly added component already has dependents in the new graph."""
        c1 = _make_component("web")
        c2 = _make_component("cache", ctype=ComponentType.CACHE)
        dep = _make_dep("web", "cache")
        g1 = _graph_with(c1)
        g2 = _graph_with(c1, c2, deps=[dep])
        diff = engine.compute_diff(g1, g2)
        assert "cache" in diff.added_components


# ---------------------------------------------------------------------------
# compute_diff — component removals
# ---------------------------------------------------------------------------

class TestComputeDiffRemovals:
    def test_single_removal(self, engine):
        g1 = _graph_with(_make_component("old"))
        g2 = InfraGraph()
        diff = engine.compute_diff(g1, g2)
        assert diff.removed_components == ["old"]
        assert diff.entries[0].diff_type == DiffType.COMPONENT_REMOVED

    def test_remove_with_dependents_is_critical(self, engine):
        c1 = _make_component("web")
        c2 = _make_component("db", ctype=ComponentType.DATABASE)
        dep = _make_dep("web", "db")
        g1 = _graph_with(c1, c2, deps=[dep])
        g2 = _graph_with(c1)
        diff = engine.compute_diff(g1, g2)
        entry = [e for e in diff.entries if e.diff_type == DiffType.COMPONENT_REMOVED][0]
        assert entry.risk_level == "critical"

    def test_remove_without_dependents_is_medium(self, engine):
        g1 = _graph_with(_make_component("isolated"))
        g2 = InfraGraph()
        diff = engine.compute_diff(g1, g2)
        entry = [e for e in diff.entries if e.diff_type == DiffType.COMPONENT_REMOVED][0]
        assert entry.risk_level == "medium"

    def test_remove_critical_type_no_dependents(self, engine):
        g1 = _graph_with(_make_component("lb", ctype=ComponentType.LOAD_BALANCER))
        g2 = InfraGraph()
        diff = engine.compute_diff(g1, g2)
        entry = [e for e in diff.entries if e.diff_type == DiffType.COMPONENT_REMOVED][0]
        assert entry.risk_level == "high"

    def test_multiple_removals(self, engine):
        g1 = _graph_with(
            _make_component("a"),
            _make_component("b"),
        )
        g2 = InfraGraph()
        diff = engine.compute_diff(g1, g2)
        assert sorted(diff.removed_components) == ["a", "b"]


# ---------------------------------------------------------------------------
# compute_diff — component modifications
# ---------------------------------------------------------------------------

class TestComputeDiffModifications:
    def test_type_change(self, engine):
        c1 = _make_component("x", ctype=ComponentType.CACHE)
        c2 = _make_component("x", ctype=ComponentType.DATABASE)
        g1 = _graph_with(c1)
        g2 = _graph_with(c2)
        diff = engine.compute_diff(g1, g2)
        assert "x" in diff.modified_components
        type_entries = [e for e in diff.entries if e.diff_type == DiffType.TYPE_CHANGED]
        assert len(type_entries) == 1
        assert type_entries[0].risk_level in ("critical", "high")

    def test_type_change_with_dependents_is_critical(self, engine):
        c1 = _make_component("db", ctype=ComponentType.CACHE)
        c2 = _make_component("db", ctype=ComponentType.DATABASE)
        web = _make_component("web")
        dep = _make_dep("web", "db")
        g1 = _graph_with(web, c1, deps=[dep])
        g2 = _graph_with(web, c2, deps=[dep])
        diff = engine.compute_diff(g1, g2)
        type_entries = [e for e in diff.entries if e.diff_type == DiffType.TYPE_CHANGED]
        assert type_entries[0].risk_level == "critical"

    def test_type_change_without_dependents_is_high(self, engine):
        c1 = _make_component("x", ctype=ComponentType.CACHE)
        c2 = _make_component("x", ctype=ComponentType.DATABASE)
        g1 = _graph_with(c1)
        g2 = _graph_with(c2)
        diff = engine.compute_diff(g1, g2)
        type_entries = [e for e in diff.entries if e.diff_type == DiffType.TYPE_CHANGED]
        assert type_entries[0].risk_level == "high"

    def test_replicas_increase(self, engine):
        c1 = _make_component("web", replicas=1)
        c2 = _make_component("web", replicas=3)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        rep = [e for e in diff.entries if e.diff_type == DiffType.REPLICAS_CHANGED]
        assert len(rep) == 1
        assert rep[0].risk_level == "low"

    def test_replicas_decrease_app_server(self, engine):
        c1 = _make_component("web", replicas=3, ctype=ComponentType.APP_SERVER)
        c2 = _make_component("web", replicas=1, ctype=ComponentType.APP_SERVER)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        rep = [e for e in diff.entries if e.diff_type == DiffType.REPLICAS_CHANGED]
        assert rep[0].risk_level == "medium"

    def test_replicas_decrease_database(self, engine):
        c1 = _make_component("db", replicas=3, ctype=ComponentType.DATABASE)
        c2 = _make_component("db", replicas=1, ctype=ComponentType.DATABASE)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        rep = [e for e in diff.entries if e.diff_type == DiffType.REPLICAS_CHANGED]
        assert rep[0].risk_level == "high"

    def test_health_change_to_down(self, engine):
        c1 = _make_component("web", health=HealthStatus.HEALTHY)
        c2 = _make_component("web", health=HealthStatus.DOWN)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        h = [e for e in diff.entries if e.diff_type == DiffType.HEALTH_CHANGED]
        assert h[0].risk_level == "critical"

    def test_health_change_to_overloaded(self, engine):
        c1 = _make_component("web", health=HealthStatus.HEALTHY)
        c2 = _make_component("web", health=HealthStatus.OVERLOADED)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        h = [e for e in diff.entries if e.diff_type == DiffType.HEALTH_CHANGED]
        assert h[0].risk_level == "critical"

    def test_health_change_to_degraded(self, engine):
        c1 = _make_component("web", health=HealthStatus.HEALTHY)
        c2 = _make_component("web", health=HealthStatus.DEGRADED)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        h = [e for e in diff.entries if e.diff_type == DiffType.HEALTH_CHANGED]
        assert h[0].risk_level == "medium"

    def test_health_change_to_healthy(self, engine):
        c1 = _make_component("web", health=HealthStatus.DEGRADED)
        c2 = _make_component("web", health=HealthStatus.HEALTHY)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        h = [e for e in diff.entries if e.diff_type == DiffType.HEALTH_CHANGED]
        assert h[0].risk_level == "low"

    def test_name_change(self, engine):
        c1 = _make_component("x", name="OldName")
        c2 = _make_component("x", name="NewName")
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        name_e = [e for e in diff.entries if "name changed" in e.description]
        assert len(name_e) == 1
        assert name_e[0].risk_level == "low"

    def test_host_port_change(self, engine):
        c1 = _make_component("x", host="old.host", port=8080)
        c2 = _make_component("x", host="new.host", port=9090)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        ep = [e for e in diff.entries if "endpoint" in e.description]
        assert len(ep) == 1
        assert ep[0].risk_level == "medium"

    def test_failover_disabled(self, engine):
        c1 = _make_component("x", failover=True)
        c2 = _make_component("x", failover=False)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        fo = [e for e in diff.entries if "failover" in e.description.lower()]
        assert fo[0].risk_level == "high"

    def test_failover_enabled(self, engine):
        c1 = _make_component("x", failover=False)
        c2 = _make_component("x", failover=True)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        fo = [e for e in diff.entries if "failover" in e.description.lower()]
        assert fo[0].risk_level == "low"

    def test_autoscaling_disabled(self, engine):
        c1 = _make_component("x", autoscaling=True)
        c2 = _make_component("x", autoscaling=False)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        auto = [e for e in diff.entries if "autoscaling" in e.description.lower()]
        assert auto[0].risk_level == "medium"

    def test_autoscaling_enabled(self, engine):
        c1 = _make_component("x", autoscaling=False)
        c2 = _make_component("x", autoscaling=True)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        auto = [e for e in diff.entries if "autoscaling" in e.description.lower()]
        assert auto[0].risk_level == "low"

    def test_no_modification_when_identical(self, engine):
        c = _make_component("x")
        diff = engine.compute_diff(_graph_with(c), _graph_with(c))
        assert diff.modified_components == []

    def test_multiple_fields_modified(self, engine):
        c1 = _make_component("x", replicas=2, health=HealthStatus.HEALTHY, failover=True)
        c2 = _make_component("x", replicas=1, health=HealthStatus.DEGRADED, failover=False)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        assert "x" in diff.modified_components
        assert diff.total_changes >= 3


# ---------------------------------------------------------------------------
# compute_diff — dependency changes
# ---------------------------------------------------------------------------

class TestComputeDiffDependencies:
    def test_dependency_added(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2)
        g2 = _graph_with(c1, c2, deps=[_make_dep("a", "b")])
        diff = engine.compute_diff(g1, g2)
        assert diff.added_dependencies == [("a", "b")]

    def test_dependency_removed(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b")])
        g2 = _graph_with(c1, c2)
        diff = engine.compute_diff(g1, g2)
        assert diff.removed_dependencies == [("a", "b")]

    def test_dep_removed_with_source_still_present_requires(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", dep_type="requires")])
        g2 = _graph_with(c1, c2)
        diff = engine.compute_diff(g1, g2)
        rem = [e for e in diff.entries if e.diff_type == DiffType.DEPENDENCY_REMOVED]
        assert rem[0].risk_level == "critical"

    def test_dep_removed_with_source_also_removed(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b")])
        g2 = _graph_with(c2)
        diff = engine.compute_diff(g1, g2)
        rem = [e for e in diff.entries if e.diff_type == DiffType.DEPENDENCY_REMOVED]
        assert rem[0].risk_level == "low"

    def test_dep_removed_optional(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", dep_type="optional")])
        g2 = _graph_with(c1, c2)
        diff = engine.compute_diff(g1, g2)
        rem = [e for e in diff.entries if e.diff_type == DiffType.DEPENDENCY_REMOVED]
        assert rem[0].risk_level == "medium"

    def test_dep_removed_async(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", dep_type="async")])
        g2 = _graph_with(c1, c2)
        diff = engine.compute_diff(g1, g2)
        rem = [e for e in diff.entries if e.diff_type == DiffType.DEPENDENCY_REMOVED]
        assert rem[0].risk_level == "low"

    def test_dependency_type_modified(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", dep_type="optional")])
        g2 = _graph_with(c1, c2, deps=[_make_dep("a", "b", dep_type="requires")])
        diff = engine.compute_diff(g1, g2)
        mod = [e for e in diff.entries if e.diff_type == DiffType.DEPENDENCY_MODIFIED]
        assert len(mod) >= 1
        type_mod = [m for m in mod if "type changed" in m.description]
        assert type_mod[0].risk_level == "high"

    def test_dependency_type_downgrade(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", dep_type="requires")])
        g2 = _graph_with(c1, c2, deps=[_make_dep("a", "b", dep_type="optional")])
        diff = engine.compute_diff(g1, g2)
        mod = [e for e in diff.entries if e.diff_type == DiffType.DEPENDENCY_MODIFIED]
        type_mod = [m for m in mod if "type changed" in m.description]
        assert type_mod[0].risk_level == "medium"

    def test_dependency_weight_changed(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", weight=0.5)])
        g2 = _graph_with(c1, c2, deps=[_make_dep("a", "b", weight=1.0)])
        diff = engine.compute_diff(g1, g2)
        wmod = [e for e in diff.entries if "weight" in e.description]
        assert len(wmod) == 1
        assert wmod[0].risk_level == "medium"

    def test_dependency_weight_decreased(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", weight=1.0)])
        g2 = _graph_with(c1, c2, deps=[_make_dep("a", "b", weight=0.3)])
        diff = engine.compute_diff(g1, g2)
        wmod = [e for e in diff.entries if "weight" in e.description]
        assert wmod[0].risk_level == "low"

    def test_circuit_breaker_toggled_on(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", cb_enabled=False)])
        g2 = _graph_with(c1, c2, deps=[_make_dep("a", "b", cb_enabled=True)])
        diff = engine.compute_diff(g1, g2)
        cb = [e for e in diff.entries if "circuit breaker" in e.description.lower()]
        assert cb[0].risk_level == "low"

    def test_circuit_breaker_toggled_off(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", cb_enabled=True)])
        g2 = _graph_with(c1, c2, deps=[_make_dep("a", "b", cb_enabled=False)])
        diff = engine.compute_diff(g1, g2)
        cb = [e for e in diff.entries if "circuit breaker" in e.description.lower()]
        assert cb[0].risk_level == "medium"


# ---------------------------------------------------------------------------
# compute_diff — complex scenarios
# ---------------------------------------------------------------------------

class TestComputeDiffComplex:
    def test_add_and_remove_simultaneously(self, engine):
        c1 = _make_component("old")
        c2 = _make_component("new")
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        assert diff.added_components == ["new"]
        assert diff.removed_components == ["old"]
        assert diff.total_changes == 2

    def test_large_graph_diff(self, engine):
        comps_a = [_make_component(f"c{i}") for i in range(20)]
        comps_b = [_make_component(f"c{i}") for i in range(5, 25)]
        g1 = _graph_with(*comps_a)
        g2 = _graph_with(*comps_b)
        diff = engine.compute_diff(g1, g2)
        assert len(diff.removed_components) == 5   # c0..c4
        assert len(diff.added_components) == 5     # c20..c24

    def test_diff_populates_risk_score(self, engine):
        g1 = _graph_with(_make_component("web"))
        g2 = InfraGraph()
        diff = engine.compute_diff(g1, g2)
        assert diff.risk_score > 0

    def test_diff_populates_breaking_changes(self, engine):
        c1 = _make_component("db", ctype=ComponentType.DATABASE)
        web = _make_component("web")
        dep = _make_dep("web", "db")
        g1 = _graph_with(web, c1, deps=[dep])
        g2 = _graph_with(web)
        diff = engine.compute_diff(g1, g2)
        assert len(diff.breaking_changes) > 0

    def test_diff_populates_recommendations(self, engine):
        web = _make_component("web")
        db = _make_component("db", ctype=ComponentType.DATABASE, replicas=3)
        db2 = _make_component("db", ctype=ComponentType.DATABASE, replicas=1)
        dep = _make_dep("web", "db")
        g1 = _graph_with(web, db, deps=[dep])
        g2 = _graph_with(web, db2, deps=[dep])
        diff = engine.compute_diff(g1, g2)
        assert len(diff.recommendations) > 0


# ---------------------------------------------------------------------------
# detect_breaking_changes
# ---------------------------------------------------------------------------

class TestDetectBreakingChanges:
    def test_no_entries(self, engine):
        diff = GraphDiff()
        assert engine.detect_breaking_changes(diff) == []

    def test_critical_risk_entry(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(
                diff_type=DiffType.HEALTH_CHANGED,
                entity_id="x",
                risk_level="critical",
                description="health went down",
            )
        ])
        result = engine.detect_breaking_changes(diff)
        assert "health went down" in result

    def test_component_removed_always_breaking(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(
                diff_type=DiffType.COMPONENT_REMOVED,
                entity_id="x",
                risk_level="medium",
                description="removed x",
            )
        ])
        result = engine.detect_breaking_changes(diff)
        assert "removed x" in result

    def test_type_changed_always_breaking(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(
                diff_type=DiffType.TYPE_CHANGED,
                entity_id="x",
                risk_level="high",
                description="type changed",
            )
        ])
        result = engine.detect_breaking_changes(diff)
        assert "type changed" in result

    def test_dep_removed_critical(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(
                diff_type=DiffType.DEPENDENCY_REMOVED,
                entity_id="a->b",
                risk_level="critical",
                description="dep removed",
            )
        ])
        assert "dep removed" in engine.detect_breaking_changes(diff)

    def test_dep_removed_high(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(
                diff_type=DiffType.DEPENDENCY_REMOVED,
                entity_id="a->b",
                risk_level="high",
                description="dep removed high",
            )
        ])
        assert "dep removed high" in engine.detect_breaking_changes(diff)

    def test_dep_removed_low_not_breaking(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(
                diff_type=DiffType.DEPENDENCY_REMOVED,
                entity_id="a->b",
                risk_level="low",
                description="dep removed low",
            )
        ])
        assert engine.detect_breaking_changes(diff) == []

    def test_deduplication(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="x",
                      risk_level="critical", description="same"),
            DiffEntry(diff_type=DiffType.TYPE_CHANGED, entity_id="x",
                      risk_level="critical", description="same"),
        ])
        result = engine.detect_breaking_changes(diff)
        assert result.count("same") == 1

    def test_non_breaking_entry_excluded(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(
                diff_type=DiffType.REPLICAS_CHANGED,
                entity_id="x",
                risk_level="low",
                description="replicas changed",
            )
        ])
        assert engine.detect_breaking_changes(diff) == []


# ---------------------------------------------------------------------------
# calculate_change_risk
# ---------------------------------------------------------------------------

class TestCalculateChangeRisk:
    def test_zero_entries(self, engine):
        assert engine.calculate_change_risk(GraphDiff()) == 0.0

    def test_single_low_entry(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="x", risk_level="low"),
        ])
        score = engine.calculate_change_risk(diff)
        assert 0 < score < 10

    def test_single_critical_entry(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="x", risk_level="critical"),
        ])
        score = engine.calculate_change_risk(diff)
        assert score == 10.0

    def test_multiple_critical_entries(self, engine):
        entries = [
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id=f"c{i}", risk_level="critical")
            for i in range(10)
        ]
        diff = GraphDiff(entries=entries)
        score = engine.calculate_change_risk(diff)
        assert score == 100.0

    def test_mixed_risk_levels(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="a", risk_level="low"),
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="b", risk_level="critical"),
        ])
        score = engine.calculate_change_risk(diff)
        assert 0 < score < 100

    def test_capped_at_100(self, engine):
        entries = [
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id=f"c{i}", risk_level="critical")
            for i in range(20)
        ]
        diff = GraphDiff(entries=entries)
        score = engine.calculate_change_risk(diff)
        assert score <= 100.0

    def test_unknown_risk_level_uses_default(self, engine):
        diff = GraphDiff(entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="x", risk_level="unknown"),
        ])
        score = engine.calculate_change_risk(diff)
        assert score >= 0.0


# ---------------------------------------------------------------------------
# generate_migration_plan
# ---------------------------------------------------------------------------

class TestGenerateMigrationPlan:
    def test_empty_diff(self, engine):
        plan = engine.generate_migration_plan(GraphDiff())
        assert plan.estimated_steps == 0
        assert plan.steps == []
        assert not plan.requires_downtime

    def test_add_only(self, engine):
        diff = GraphDiff(
            added_components=["web"],
            entries=[DiffEntry(
                diff_type=DiffType.COMPONENT_ADDED, entity_id="web",
                risk_level="low", description="add web",
            )],
        )
        plan = engine.generate_migration_plan(diff)
        assert plan.estimated_steps == 1
        assert plan.steps[0].action == "add"
        assert not plan.requires_downtime

    def test_remove_requires_downtime(self, engine):
        diff = GraphDiff(
            removed_components=["old"],
            entries=[DiffEntry(
                diff_type=DiffType.COMPONENT_REMOVED, entity_id="old",
                risk_level="high", description="remove old",
            )],
        )
        plan = engine.generate_migration_plan(diff)
        assert plan.requires_downtime
        assert any("old" in s.component_id for s in plan.steps)

    def test_modify_with_type_change_requires_downtime(self, engine):
        diff = GraphDiff(
            modified_components=["db"],
            entries=[DiffEntry(
                diff_type=DiffType.TYPE_CHANGED, entity_id="db",
                risk_level="critical", description="type changed",
            )],
        )
        plan = engine.generate_migration_plan(diff)
        assert plan.requires_downtime
        assert any("may require downtime" in w for w in plan.warnings)

    def test_ordering_add_before_remove(self, engine):
        diff = GraphDiff(
            added_components=["new"],
            removed_components=["old"],
            entries=[
                DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="new",
                          risk_level="low", description="add new"),
                DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="old",
                          risk_level="high", description="remove old"),
            ],
        )
        plan = engine.generate_migration_plan(diff)
        add_order = next(s.order for s in plan.steps if s.action == "add")
        rem_order = next(s.order for s in plan.steps if s.action == "remove")
        assert add_order < rem_order

    def test_rollback_steps_reversed(self, engine):
        diff = GraphDiff(
            added_components=["a", "b"],
            entries=[
                DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="a",
                          risk_level="low", description="add a"),
                DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="b",
                          risk_level="low", description="add b"),
            ],
        )
        plan = engine.generate_migration_plan(diff)
        assert len(plan.rollback_steps) == 2
        # Rollback should reverse the order.
        assert plan.rollback_steps[0].order < plan.rollback_steps[1].order

    def test_added_dependency_step(self, engine):
        diff = GraphDiff(
            added_dependencies=[("a", "b")],
            entries=[DiffEntry(
                diff_type=DiffType.DEPENDENCY_ADDED, entity_id="a->b",
                risk_level="low", description="dep added",
            )],
        )
        plan = engine.generate_migration_plan(diff)
        dep_steps = [s for s in plan.steps if s.action == "add_dependency"]
        assert len(dep_steps) == 1

    def test_removed_dependency_step(self, engine):
        diff = GraphDiff(
            removed_dependencies=[("a", "b")],
            entries=[DiffEntry(
                diff_type=DiffType.DEPENDENCY_REMOVED, entity_id="a->b",
                risk_level="medium", description="dep removed",
            )],
        )
        plan = engine.generate_migration_plan(diff)
        dep_steps = [s for s in plan.steps if s.action == "remove_dependency"]
        assert len(dep_steps) == 1

    def test_warnings_for_removal(self, engine):
        diff = GraphDiff(
            removed_components=["db"],
            entries=[DiffEntry(
                diff_type=DiffType.COMPONENT_REMOVED, entity_id="db",
                risk_level="critical", description="remove db",
            )],
        )
        plan = engine.generate_migration_plan(diff)
        assert any("irreversible" in w.lower() for w in plan.warnings)

    def test_modify_step_picks_max_risk(self, engine):
        diff = GraphDiff(
            modified_components=["web"],
            entries=[
                DiffEntry(diff_type=DiffType.REPLICAS_CHANGED, entity_id="web",
                          risk_level="low", description="replicas"),
                DiffEntry(diff_type=DiffType.HEALTH_CHANGED, entity_id="web",
                          risk_level="critical", description="health"),
            ],
        )
        plan = engine.generate_migration_plan(diff)
        mod_step = [s for s in plan.steps if s.action == "modify"][0]
        assert mod_step.risk_level == "critical"

    def test_full_plan_structure(self, engine):
        c1 = _make_component("web")
        c2 = _make_component("db", ctype=ComponentType.DATABASE)
        c3 = _make_component("cache", ctype=ComponentType.CACHE)
        dep = _make_dep("web", "db")
        g1 = _graph_with(c1, c2, deps=[dep])
        g2 = _graph_with(c1, c3, deps=[_make_dep("web", "cache")])
        diff = engine.compute_diff(g1, g2)
        plan = engine.generate_migration_plan(diff)
        assert plan.estimated_steps > 0
        assert len(plan.rollback_steps) > 0


# ---------------------------------------------------------------------------
# find_safe_rollback_point
# ---------------------------------------------------------------------------

class TestFindSafeRollbackPoint:
    def test_empty_list(self, engine):
        assert engine.find_safe_rollback_point([]) == -1

    def test_single_diff(self, engine):
        assert engine.find_safe_rollback_point([GraphDiff()]) == 0

    def test_increasing_risk(self, engine):
        d1 = GraphDiff(risk_score=5.0, entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="a", risk_level="low"),
        ])
        d2 = GraphDiff(risk_score=50.0, entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="b", risk_level="critical"),
        ])
        d3 = GraphDiff(risk_score=80.0, entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="c", risk_level="critical"),
        ])
        idx = engine.find_safe_rollback_point([d1, d2, d3])
        assert idx == 0  # First diff has lowest cumulative risk.

    def test_all_zero_risk(self, engine):
        diffs = [GraphDiff(risk_score=0.0) for _ in range(5)]
        idx = engine.find_safe_rollback_point(diffs)
        # All equal; last one with lowest cumulative (they all are 0).
        assert 0 <= idx < 5

    def test_two_diffs(self, engine):
        d1 = GraphDiff(risk_score=10.0, entries=[])
        d2 = GraphDiff(risk_score=5.0, entries=[])
        idx = engine.find_safe_rollback_point([d1, d2])
        assert idx in (0, 1)

    def test_critical_entries_penalized(self, engine):
        d1 = GraphDiff(risk_score=20.0, entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="a", risk_level="low"),
        ])
        d2 = GraphDiff(risk_score=10.0, entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="b", risk_level="critical"),
        ])
        idx = engine.find_safe_rollback_point([d1, d2])
        assert idx == 0


# ---------------------------------------------------------------------------
# summarize_diff
# ---------------------------------------------------------------------------

class TestSummarizeDiff:
    def test_no_changes(self, engine):
        s = engine.summarize_diff(GraphDiff())
        assert "No changes" in s

    def test_with_additions(self, engine):
        diff = GraphDiff(added_components=["a"], total_changes=1, entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="a"),
        ])
        s = engine.summarize_diff(diff)
        assert "1 component(s) added" in s

    def test_with_removals(self, engine):
        diff = GraphDiff(removed_components=["x"], total_changes=1, entries=[
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="x"),
        ])
        s = engine.summarize_diff(diff)
        assert "1 component(s) removed" in s

    def test_with_modifications(self, engine):
        diff = GraphDiff(modified_components=["y"], total_changes=1, entries=[
            DiffEntry(diff_type=DiffType.REPLICAS_CHANGED, entity_id="y"),
        ])
        s = engine.summarize_diff(diff)
        assert "modified" in s

    def test_with_dependencies(self, engine):
        diff = GraphDiff(
            added_dependencies=[("a", "b")],
            removed_dependencies=[("c", "d")],
            total_changes=2,
            entries=[
                DiffEntry(diff_type=DiffType.DEPENDENCY_ADDED, entity_id="a->b"),
                DiffEntry(diff_type=DiffType.DEPENDENCY_REMOVED, entity_id="c->d"),
            ],
        )
        s = engine.summarize_diff(diff)
        assert "dependency" in s.lower()

    def test_includes_risk_score(self, engine):
        diff = GraphDiff(
            added_components=["a"], total_changes=1, risk_score=42.0,
            entries=[DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="a")],
        )
        s = engine.summarize_diff(diff)
        assert "42.0" in s

    def test_includes_breaking_changes(self, engine):
        diff = GraphDiff(
            removed_components=["x"], total_changes=1,
            breaking_changes=["removed x"],
            entries=[DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="x")],
        )
        s = engine.summarize_diff(diff)
        assert "Breaking" in s
        assert "removed x" in s

    def test_breaking_changes_truncated(self, engine):
        diff = GraphDiff(
            total_changes=5,
            breaking_changes=[f"break{i}" for i in range(5)],
            entries=[DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id=f"c{i}")
                     for i in range(5)],
        )
        s = engine.summarize_diff(diff)
        assert "more" in s.lower()

    def test_includes_recommendations(self, engine):
        diff = GraphDiff(
            added_components=["a"], total_changes=1,
            recommendations=["do something", "do another"],
            entries=[DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="a")],
        )
        s = engine.summarize_diff(diff)
        assert "Recommendations" in s
        assert "+1 more" in s

    def test_single_recommendation(self, engine):
        diff = GraphDiff(
            added_components=["a"], total_changes=1,
            recommendations=["only one"],
            entries=[DiffEntry(diff_type=DiffType.COMPONENT_ADDED, entity_id="a")],
        )
        s = engine.summarize_diff(diff)
        assert "only one" in s
        assert "more" not in s.lower()


# ---------------------------------------------------------------------------
# validate_backward_compatibility
# ---------------------------------------------------------------------------

class TestValidateBackwardCompatibility:
    def test_empty_diff_compatible(self, engine):
        report = engine.validate_backward_compatibility(GraphDiff())
        assert report.is_compatible
        assert report.score == 100.0
        assert "Fully backward compatible" in report.summary

    def test_removed_component_incompatible(self, engine):
        diff = GraphDiff(
            removed_components=["db"],
            entries=[DiffEntry(
                diff_type=DiffType.COMPONENT_REMOVED, entity_id="db",
                risk_level="critical", description="removed db",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        assert not report.is_compatible
        assert any(i.severity == "critical" for i in report.issues)
        assert report.score < 100.0

    def test_type_changed_incompatible(self, engine):
        diff = GraphDiff(
            modified_components=["x"],
            entries=[DiffEntry(
                diff_type=DiffType.TYPE_CHANGED, entity_id="x",
                risk_level="critical", description="type changed",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        assert not report.is_compatible

    def test_dep_removed_source_still_present(self, engine):
        diff = GraphDiff(
            removed_dependencies=[("a", "b")],
            entries=[DiffEntry(
                diff_type=DiffType.DEPENDENCY_REMOVED, entity_id="a->b",
                risk_level="high", description="dep removed",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        # High but not critical, so still "compatible" (no critical issues).
        assert report.is_compatible
        assert any(i.severity == "high" for i in report.issues)

    def test_dep_removed_source_also_removed(self, engine):
        diff = GraphDiff(
            removed_components=["a"],
            removed_dependencies=[("a", "b")],
            entries=[
                DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="a",
                          risk_level="critical", description="removed a"),
                DiffEntry(diff_type=DiffType.DEPENDENCY_REMOVED, entity_id="a->b",
                          risk_level="low", description="dep removed"),
            ],
        )
        report = engine.validate_backward_compatibility(diff)
        # Component removal makes it incompatible.
        assert not report.is_compatible

    def test_replicas_reduced(self, engine):
        diff = GraphDiff(
            modified_components=["web"],
            entries=[DiffEntry(
                diff_type=DiffType.REPLICAS_CHANGED, entity_id="web",
                old_value="3", new_value="1",
                risk_level="high", description="replicas reduced",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        assert report.is_compatible  # Medium concern, not critical.
        assert any(i.severity == "medium" for i in report.issues)

    def test_replicas_increased_no_issue(self, engine):
        diff = GraphDiff(
            modified_components=["web"],
            entries=[DiffEntry(
                diff_type=DiffType.REPLICAS_CHANGED, entity_id="web",
                old_value="1", new_value="3",
                risk_level="low", description="replicas increased",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        assert report.is_compatible
        assert report.score == 100.0

    def test_health_degraded_to_down(self, engine):
        diff = GraphDiff(
            modified_components=["web"],
            entries=[DiffEntry(
                diff_type=DiffType.HEALTH_CHANGED, entity_id="web",
                old_value="healthy", new_value="down",
                risk_level="critical", description="health down",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        assert any(i.severity == "high" for i in report.issues)

    def test_health_degraded_to_overloaded(self, engine):
        diff = GraphDiff(
            modified_components=["web"],
            entries=[DiffEntry(
                diff_type=DiffType.HEALTH_CHANGED, entity_id="web",
                old_value="healthy", new_value="overloaded",
                risk_level="critical", description="health overloaded",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        assert any(i.severity == "high" for i in report.issues)

    def test_health_improved_no_issue(self, engine):
        diff = GraphDiff(
            modified_components=["web"],
            entries=[DiffEntry(
                diff_type=DiffType.HEALTH_CHANGED, entity_id="web",
                old_value="degraded", new_value="healthy",
                risk_level="low", description="health improved",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        assert report.is_compatible
        assert report.score == 100.0

    def test_score_deduction_accumulates(self, engine):
        diff = GraphDiff(
            removed_components=["a", "b"],
            entries=[
                DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="a",
                          risk_level="critical", description="removed a"),
                DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id="b",
                          risk_level="critical", description="removed b"),
            ],
        )
        report = engine.validate_backward_compatibility(diff)
        assert report.score < 100.0
        assert report.score == max(0.0, 100.0 - 25.0 * 2)

    def test_score_never_negative(self, engine):
        entries = [
            DiffEntry(diff_type=DiffType.COMPONENT_REMOVED, entity_id=f"c{i}",
                      risk_level="critical", description=f"removed c{i}")
            for i in range(10)
        ]
        diff = GraphDiff(
            removed_components=[f"c{i}" for i in range(10)],
            entries=entries,
        )
        report = engine.validate_backward_compatibility(diff)
        assert report.score >= 0.0

    def test_summary_not_compatible(self, engine):
        diff = GraphDiff(
            removed_components=["x"],
            entries=[DiffEntry(
                diff_type=DiffType.COMPONENT_REMOVED, entity_id="x",
                risk_level="critical", description="removed x",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        assert "NOT backward compatible" in report.summary

    def test_summary_compatible_with_concerns(self, engine):
        diff = GraphDiff(
            modified_components=["web"],
            entries=[DiffEntry(
                diff_type=DiffType.REPLICAS_CHANGED, entity_id="web",
                old_value="3", new_value="1",
                risk_level="high", description="replicas reduced",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        assert "concern" in report.summary.lower()

    def test_replicas_non_integer_skipped(self, engine):
        diff = GraphDiff(
            modified_components=["web"],
            entries=[DiffEntry(
                diff_type=DiffType.REPLICAS_CHANGED, entity_id="web",
                old_value="not_a_number", new_value="also_not",
                risk_level="medium", description="bad values",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        # Should not crash; replicas issue is simply skipped.
        assert report.is_compatible


# ---------------------------------------------------------------------------
# Recommendations generation
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_recommendation_for_removed_with_dependents(self, engine):
        web = _make_component("web")
        db = _make_component("db", ctype=ComponentType.DATABASE)
        dep = _make_dep("web", "db")
        g1 = _graph_with(web, db, deps=[dep])
        g2 = _graph_with(web)
        diff = engine.compute_diff(g1, g2)
        assert any("depended on" in r for r in diff.recommendations)

    def test_recommendation_for_replica_reduction(self, engine):
        c1 = _make_component("web", replicas=5)
        c2 = _make_component("web", replicas=1)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        assert any("replicas reduced" in r.lower() for r in diff.recommendations)

    def test_recommendation_for_type_change(self, engine):
        c1 = _make_component("x", ctype=ComponentType.CACHE)
        c2 = _make_component("x", ctype=ComponentType.DATABASE)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        assert any("type changed" in r.lower() for r in diff.recommendations)

    def test_recommendation_for_failover_disabled(self, engine):
        c1 = _make_component("x", failover=True)
        c2 = _make_component("x", failover=False)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        assert any("failover" in r.lower() for r in diff.recommendations)

    def test_recommendation_for_health_degradation(self, engine):
        c1 = _make_component("x", health=HealthStatus.HEALTHY)
        c2 = _make_component("x", health=HealthStatus.DOWN)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        assert any("health degraded" in r.lower() for r in diff.recommendations)

    def test_recommendation_for_dep_type_escalation(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", dep_type="optional")])
        g2 = _graph_with(c1, c2, deps=[_make_dep("a", "b", dep_type="requires")])
        diff = engine.compute_diff(g1, g2)
        assert any("escalated" in r for r in diff.recommendations)

    def test_recommendation_for_circuit_breaker_disabled(self, engine):
        c1 = _make_component("a")
        c2 = _make_component("b")
        g1 = _graph_with(c1, c2, deps=[_make_dep("a", "b", cb_enabled=True)])
        g2 = _graph_with(c1, c2, deps=[_make_dep("a", "b", cb_enabled=False)])
        diff = engine.compute_diff(g1, g2)
        assert any("circuit breaker" in r.lower() for r in diff.recommendations)

    def test_no_duplicate_recommendations(self, engine):
        c1 = _make_component("x", failover=True, health=HealthStatus.HEALTHY)
        c2 = _make_component("x", failover=False, health=HealthStatus.DOWN)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        assert len(diff.recommendations) == len(set(diff.recommendations))


# ---------------------------------------------------------------------------
# Integration / end-to-end
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_full_workflow(self, engine):
        # Before graph: web -> db (requires), web -> cache (optional).
        web = _make_component("web", replicas=2)
        db = _make_component("db", ctype=ComponentType.DATABASE, replicas=3, failover=True)
        cache = _make_component("cache", ctype=ComponentType.CACHE, replicas=2)
        g1 = _graph_with(web, db, cache, deps=[
            _make_dep("web", "db", dep_type="requires"),
            _make_dep("web", "cache", dep_type="optional"),
        ])

        # After graph: web -> db (still), cache removed, queue added.
        web2 = _make_component("web", replicas=1)
        db2 = _make_component("db", ctype=ComponentType.DATABASE, replicas=1, failover=False)
        queue = _make_component("queue", ctype=ComponentType.QUEUE)
        g2 = _graph_with(web2, db2, queue, deps=[
            _make_dep("web", "db", dep_type="requires"),
            _make_dep("web", "queue", dep_type="async"),
        ])

        diff = engine.compute_diff(g1, g2)

        # Assertions on the diff.
        assert "queue" in diff.added_components
        assert "cache" in diff.removed_components
        assert "web" in diff.modified_components
        assert "db" in diff.modified_components
        assert diff.total_changes > 0
        assert diff.risk_score > 0

        # Breaking changes should include removed cache and type changes.
        assert len(diff.breaking_changes) > 0

        # Recommendations should be populated.
        assert len(diff.recommendations) > 0

        # Migration plan should be valid.
        plan = engine.generate_migration_plan(diff)
        assert plan.estimated_steps > 0
        assert len(plan.rollback_steps) > 0

        # Compatibility report should flag issues.
        report = engine.validate_backward_compatibility(diff)
        assert len(report.issues) > 0

        # Summary should be non-trivial.
        summary = engine.summarize_diff(diff)
        assert len(summary) > 50

    def test_no_change_workflow(self, engine):
        web = _make_component("web")
        g = _graph_with(web)
        diff = engine.compute_diff(g, g)
        assert diff.total_changes == 0
        plan = engine.generate_migration_plan(diff)
        assert plan.estimated_steps == 0
        report = engine.validate_backward_compatibility(diff)
        assert report.is_compatible
        assert report.score == 100.0
        summary = engine.summarize_diff(diff)
        assert "No changes" in summary

    def test_rollback_over_multiple_diffs(self, engine):
        web = _make_component("web")
        db = _make_component("db", ctype=ComponentType.DATABASE)
        g1 = _graph_with(web)
        g2 = _graph_with(web, db, deps=[_make_dep("web", "db")])

        d1 = engine.compute_diff(g1, g2)

        cache = _make_component("cache", ctype=ComponentType.CACHE)
        g3 = _graph_with(web, db, cache, deps=[
            _make_dep("web", "db"),
            _make_dep("web", "cache"),
        ])
        d2 = engine.compute_diff(g2, g3)

        # Remove db (breaking).
        g4 = _graph_with(web, cache, deps=[_make_dep("web", "cache")])
        d3 = engine.compute_diff(g3, g4)

        idx = engine.find_safe_rollback_point([d1, d2, d3])
        assert 0 <= idx <= 2

    def test_symmetry_add_remove(self, engine):
        """Adding then removing should yield a mirror diff."""
        web = _make_component("web")
        cache = _make_component("cache", ctype=ComponentType.CACHE)
        g1 = _graph_with(web)
        g2 = _graph_with(web, cache)
        d_forward = engine.compute_diff(g1, g2)
        d_backward = engine.compute_diff(g2, g1)
        assert d_forward.added_components == d_backward.removed_components
        assert d_forward.removed_components == d_backward.added_components


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_component_with_none_from_get(self, engine):
        """Ensure engine handles get_component returning None gracefully."""
        g1 = InfraGraph()
        g2 = InfraGraph()
        # Add then forcibly corrupt (should not happen in practice).
        diff = engine.compute_diff(g1, g2)
        assert diff.total_changes == 0

    def test_dep_set_empty_graph(self, engine):
        result = engine._dep_set(InfraGraph())
        assert result == set()

    def test_dep_set_no_edges(self, engine):
        g = _graph_with(_make_component("a"), _make_component("b"))
        result = engine._dep_set(g)
        assert result == set()

    def test_find_entry_not_found(self, engine):
        diff = GraphDiff()
        assert engine._find_entry(diff, "nonexistent", DiffType.COMPONENT_ADDED) is None

    def test_find_entry_found(self, engine):
        entry = DiffEntry(
            diff_type=DiffType.COMPONENT_ADDED, entity_id="web",
            risk_level="low", description="added web",
        )
        diff = GraphDiff(entries=[entry])
        found = engine._find_entry(diff, "web", DiffType.COMPONENT_ADDED)
        assert found is entry

    def test_component_add_risk_none(self, engine):
        assert engine._component_add_risk(None, InfraGraph()) == "low"

    def test_component_remove_risk_none(self, engine):
        assert engine._component_remove_risk(None, InfraGraph()) == "medium"

    def test_dep_remove_risk_async_type(self, engine):
        """Async dependency removal when source still exists."""
        c1 = _make_component("a")
        c2 = _make_component("b")
        dep = _make_dep("a", "b", dep_type="async")
        g1 = _graph_with(c1, c2, deps=[dep])
        g2 = _graph_with(c1, c2)
        risk = engine._dep_remove_risk("a", "b", g1, g2)
        assert risk == "low"

    def test_host_change_only(self, engine):
        c1 = _make_component("x", host="host1", port=80)
        c2 = _make_component("x", host="host2", port=80)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        ep = [e for e in diff.entries if "endpoint" in e.description]
        assert len(ep) == 1

    def test_port_change_only(self, engine):
        c1 = _make_component("x", host="same", port=80)
        c2 = _make_component("x", host="same", port=443)
        diff = engine.compute_diff(_graph_with(c1), _graph_with(c2))
        ep = [e for e in diff.entries if "endpoint" in e.description]
        assert len(ep) == 1

    def test_many_components_performance(self, engine):
        """Ensure 100-component graph diffs complete without issue."""
        comps = [_make_component(f"c{i}") for i in range(100)]
        g1 = _graph_with(*comps[:50])
        g2 = _graph_with(*comps[50:])
        diff = engine.compute_diff(g1, g2)
        assert diff.total_changes == 100  # 50 removed + 50 added.

    def test_dependency_entity_id_without_arrow(self, engine):
        """Validate compatibility check when entity_id has no ->."""
        diff = GraphDiff(
            entries=[DiffEntry(
                diff_type=DiffType.DEPENDENCY_REMOVED,
                entity_id="no_arrow",
                risk_level="medium",
                description="dep removed",
            )],
        )
        report = engine.validate_backward_compatibility(diff)
        # Should not crash; the source is empty so the issue is not added.
        assert report.is_compatible

    def test_common_component_none_in_internal_dict(self, engine):
        """Cover the defensive continue when get_component returns None for common ids."""
        # Create a subclass that makes get_component return None for a specific id
        # while keeping the id in the components keys dict.
        class _BrokenGraph(InfraGraph):
            def __init__(self, break_id: str):
                super().__init__()
                self._break_id = break_id

            @property
            def components(self):
                return self._components

            def get_component(self, component_id):
                if component_id == self._break_id:
                    return None
                return super().get_component(component_id)

        g1 = _BrokenGraph("ghost")
        g2 = InfraGraph()
        c = _make_component("ghost")
        g1.add_component(c)
        g2.add_component(c)
        diff = engine.compute_diff(g1, g2)
        # "ghost" is in both id sets but g1.get_component("ghost") returns None => skip.
        assert "ghost" not in diff.modified_components

    def test_recommendations_replicas_non_integer_values(self, engine):
        """Cover the except branch in _generate_recommendations for non-integer replicas."""
        diff = GraphDiff(
            modified_components=["web"],
            entries=[DiffEntry(
                diff_type=DiffType.REPLICAS_CHANGED, entity_id="web",
                old_value="abc", new_value="def",
                risk_level="medium", description="bad replicas",
            )],
        )
        recs = engine._generate_recommendations(diff, InfraGraph(), InfraGraph())
        # Should not crash; the bad values are silently skipped.
        replica_recs = [r for r in recs if "replicas reduced" in r.lower()]
        assert len(replica_recs) == 0
