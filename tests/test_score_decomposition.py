"""Tests for the Resilience Score Decomposition module."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.score_decomposition import (
    ScoreDecomposer,
    ScoreDecomposition,
    ScoreFactor,
    ScoreImprovement,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    cpu: float = 0.0,
    memory: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        metrics=ResourceMetrics(cpu_percent=cpu, memory_percent=memory),
    )


def _build_graph(
    components: list[Component],
    deps: list[tuple[str, str]] | None = None,
    dep_type: str = "requires",
) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in deps or []:
        g.add_dependency(Dependency(source_id=src, target_id=tgt, dependency_type=dep_type))
    return g


# ---------------------------------------------------------------------------
# Test: ScoreFactor dataclass
# ---------------------------------------------------------------------------

class TestScoreFactor:
    def test_penalty_factor(self):
        f = ScoreFactor(
            name="SPOF",
            category="penalty",
            points=-10.0,
            description="Single point of failure",
            affected_components=["db"],
            remediation="Add replicas",
        )
        assert f.points == -10.0
        assert f.category == "penalty"

    def test_bonus_factor(self):
        f = ScoreFactor(
            name="Failover",
            category="bonus",
            points=0,
            description="Failover coverage",
        )
        assert f.category == "bonus"


# ---------------------------------------------------------------------------
# Test: ScoreImprovement dataclass
# ---------------------------------------------------------------------------

class TestScoreImprovement:
    def test_fields(self):
        imp = ScoreImprovement(
            action="add-replica",
            component_id="db",
            estimated_improvement=8.0,
            effort="medium",
            description="Add replicas to db",
        )
        assert imp.estimated_improvement == 8.0
        assert imp.effort == "medium"


# ---------------------------------------------------------------------------
# Test: ScoreDecomposer.decompose — basic
# ---------------------------------------------------------------------------

class TestDecomposeBasic:
    def test_empty_graph(self):
        graph = InfraGraph()
        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        assert result.total_score == 0.0
        assert result.grade == "F"

    def test_perfect_score(self):
        """A single component with replicas and no dependencies -> score 100."""
        comp = _make_component("web", replicas=3)
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        assert result.total_score == 100.0
        assert result.grade in ("A+", "A")

    def test_decompose_returns_decomposition(self):
        comp = _make_component("web")
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        assert isinstance(result, ScoreDecomposition)
        assert result.base_score == 100.0
        assert result.max_possible_score == 100.0


# ---------------------------------------------------------------------------
# Test: SPOF penalty decomposition
# ---------------------------------------------------------------------------

class TestSPOFDecomposition:
    def test_single_spof_penalized(self):
        """A SPOF component (replicas=1) with a dependent should be penalized."""
        db = _make_component("db", ComponentType.DATABASE)
        app = _make_component("app")
        graph = _build_graph([db, app], [("app", "db")])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        # Should have a SPOF penalty factor
        penalty_factors = [f for f in result.factors if f.category == "penalty" and "Single" in f.name]
        assert len(penalty_factors) > 0
        assert penalty_factors[0].points < 0
        assert "db" in penalty_factors[0].affected_components

    def test_spof_penalty_matches_resilience_score(self):
        """Decomposed score must match graph.resilience_score()."""
        db = _make_component("db", ComponentType.DATABASE)
        app = _make_component("app")
        graph = _build_graph([db, app], [("app", "db")])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        actual_score = graph.resilience_score()
        assert abs(result.total_score - actual_score) < 0.01, (
            f"Decomposed score {result.total_score} != actual {actual_score}"
        )

    def test_failover_reduces_spof_penalty(self):
        """Failover should reduce the SPOF penalty."""
        db_no_fo = _make_component("db", ComponentType.DATABASE)
        app1 = _make_component("app")
        graph1 = _build_graph([db_no_fo, app1], [("app", "db")])

        db_with_fo = _make_component("db", ComponentType.DATABASE, failover=True)
        app2 = _make_component("app")
        graph2 = _build_graph([db_with_fo, app2], [("app", "db")])

        decomposer = ScoreDecomposer()
        result1 = decomposer.decompose(graph1)
        result2 = decomposer.decompose(graph2)

        # With failover should have higher score (less penalty)
        assert result2.total_score > result1.total_score

    def test_autoscaling_reduces_spof_penalty(self):
        """Autoscaling should reduce the SPOF penalty."""
        db_no_as = _make_component("db", ComponentType.DATABASE)
        app1 = _make_component("app")
        graph1 = _build_graph([db_no_as, app1], [("app", "db")])

        db_with_as = _make_component("db", ComponentType.DATABASE, autoscaling=True)
        app2 = _make_component("app")
        graph2 = _build_graph([db_with_as, app2], [("app", "db")])

        decomposer = ScoreDecomposer()
        result1 = decomposer.decompose(graph1)
        result2 = decomposer.decompose(graph2)

        assert result2.total_score > result1.total_score

    def test_multiple_dependents_increase_penalty(self):
        """More dependents on a SPOF should increase the penalty."""
        db = _make_component("db", ComponentType.DATABASE)
        app1 = _make_component("app1")
        graph1 = _build_graph([db, app1], [("app1", "db")])

        db2 = _make_component("db", ComponentType.DATABASE)
        app2a = _make_component("app1")
        app2b = _make_component("app2")
        graph2 = _build_graph([db2, app2a, app2b], [("app1", "db"), ("app2", "db")])

        decomposer = ScoreDecomposer()
        result1 = decomposer.decompose(graph1)
        result2 = decomposer.decompose(graph2)

        # More dependents -> lower score
        assert result2.total_score <= result1.total_score


# ---------------------------------------------------------------------------
# Test: Utilization penalty decomposition
# ---------------------------------------------------------------------------

class TestUtilizationDecomposition:
    def test_high_cpu_penalized(self):
        comp = _make_component("web", cpu=95)
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        util_factors = [f for f in result.factors if "Utilization" in f.name]
        assert len(util_factors) > 0
        assert util_factors[0].points < 0

    def test_utilization_matches_resilience_score(self):
        comp = _make_component("web", cpu=85)
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        actual = graph.resilience_score()
        assert abs(result.total_score - actual) < 0.01

    def test_moderate_utilization_smaller_penalty(self):
        high = _make_component("high", cpu=95)
        graph1 = _build_graph([high])

        moderate = _make_component("mod", cpu=75)
        graph2 = _build_graph([moderate])

        decomposer = ScoreDecomposer()
        r1 = decomposer.decompose(graph1)
        r2 = decomposer.decompose(graph2)

        # 75% should be less penalized than 95%
        assert r2.total_score > r1.total_score


# ---------------------------------------------------------------------------
# Test: Chain depth penalty decomposition
# ---------------------------------------------------------------------------

class TestChainDepthDecomposition:
    def test_deep_chain_penalized(self):
        # Create a chain of depth 7 (7 > 5 threshold)
        comps = [_make_component(f"c{i}", replicas=2) for i in range(7)]
        deps = [(f"c{i}", f"c{i+1}") for i in range(6)]
        graph = _build_graph(comps, deps)

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        chain_factors = [f for f in result.factors if "Chain" in f.name or "Depth" in f.name]
        assert len(chain_factors) > 0
        assert chain_factors[0].points < 0

    def test_shallow_chain_no_penalty(self):
        # Chain of depth 3 (below threshold of 5)
        comps = [_make_component(f"c{i}", replicas=2) for i in range(3)]
        deps = [(f"c{i}", f"c{i+1}") for i in range(2)]
        graph = _build_graph(comps, deps)

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        chain_factors = [f for f in result.factors if "Chain" in f.name or "Depth" in f.name]
        assert len(chain_factors) == 0  # No chain penalty


# ---------------------------------------------------------------------------
# Test: Score matches resilience_score for complex graphs
# ---------------------------------------------------------------------------

class TestScoreMatches:
    def test_complex_graph_score_match(self):
        """The decomposed score must exactly match resilience_score()."""
        lb = _make_component("lb", ComponentType.LOAD_BALANCER, replicas=2)
        web = _make_component("web", ComponentType.WEB_SERVER, failover=True)
        app_comp = _make_component("app", ComponentType.APP_SERVER, cpu=82)
        db = _make_component("db", ComponentType.DATABASE)
        cache = _make_component("cache", ComponentType.CACHE, replicas=3)

        graph = _build_graph(
            [lb, web, app_comp, db, cache],
            [("lb", "web"), ("web", "app"), ("app", "db"), ("app", "cache")],
        )

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)
        actual = graph.resilience_score()

        assert abs(result.total_score - actual) < 0.01, (
            f"Decomposed {result.total_score} != actual {actual}"
        )


# ---------------------------------------------------------------------------
# Test: Improvements
# ---------------------------------------------------------------------------

class TestImprovements:
    def test_spof_generates_improvement(self):
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        add_replica_imps = [i for i in result.improvements if i.action == "add-replica"]
        assert len(add_replica_imps) > 0
        assert add_replica_imps[0].component_id == "db"
        assert add_replica_imps[0].estimated_improvement > 0

    def test_improvements_sorted_by_impact(self):
        db = _make_component("db", ComponentType.DATABASE)
        cache = _make_component("cache", ComponentType.CACHE)
        app1 = _make_component("app1")
        app2 = _make_component("app2")
        app3 = _make_component("app3")
        graph = _build_graph(
            [db, cache, app1, app2, app3],
            [("app1", "db"), ("app2", "db"), ("app3", "db"), ("app1", "cache")],
        )

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        if len(result.improvements) >= 2:
            for i in range(len(result.improvements) - 1):
                assert result.improvements[i].estimated_improvement >= result.improvements[i + 1].estimated_improvement


# ---------------------------------------------------------------------------
# Test: what_if_fix
# ---------------------------------------------------------------------------

class TestWhatIfFix:
    def test_add_replica_improves(self):
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        decomposer = ScoreDecomposer()
        current = graph.resilience_score()
        new_score = decomposer.what_if_fix(graph, "db", "add-replica")

        assert new_score > current

    def test_enable_failover_improves(self):
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        decomposer = ScoreDecomposer()
        current = graph.resilience_score()
        new_score = decomposer.what_if_fix(graph, "db", "enable-failover")

        assert new_score > current

    def test_nonexistent_component(self):
        comp = _make_component("web")
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        score = decomposer.what_if_fix(graph, "nonexistent", "add-replica")
        assert score == graph.resilience_score()

    def test_what_if_does_not_mutate_original(self):
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        original_score = graph.resilience_score()
        decomposer = ScoreDecomposer()
        decomposer.what_if_fix(graph, "db", "add-replica")

        # Original graph should be unchanged
        assert graph.resilience_score() == original_score
        assert graph.get_component("db").replicas == 1


# ---------------------------------------------------------------------------
# Test: explain
# ---------------------------------------------------------------------------

class TestExplain:
    def test_returns_string(self):
        comp = _make_component("web")
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        text = decomposer.explain(graph)

        assert isinstance(text, str)
        assert "Resilience Score" in text

    def test_includes_grade(self):
        comp = _make_component("web", replicas=2)
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        text = decomposer.explain(graph)
        assert "Grade" in text


# ---------------------------------------------------------------------------
# Test: to_waterfall_data
# ---------------------------------------------------------------------------

class TestWaterfallData:
    def test_waterfall_structure(self):
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        decomposer = ScoreDecomposer()
        decomposition = decomposer.decompose(graph)
        waterfall = decomposer.to_waterfall_data(decomposition)

        assert len(waterfall) >= 2  # at least base and final
        assert waterfall[0]["name"] == "Base Score"
        assert waterfall[0]["category"] == "base"
        assert waterfall[-1]["name"] == "Final Score"
        assert waterfall[-1]["category"] == "total"

    def test_waterfall_running_total(self):
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        decomposer = ScoreDecomposer()
        decomposition = decomposer.decompose(graph)
        waterfall = decomposer.to_waterfall_data(decomposition)

        # Final running total should match total score
        assert abs(waterfall[-1]["running_total"] - decomposition.total_score) < 0.1


# ---------------------------------------------------------------------------
# Test: to_dict serialization
# ---------------------------------------------------------------------------

class TestToDict:
    def test_to_dict_keys(self):
        comp = _make_component("web")
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)
        d = result.to_dict()

        assert "total_score" in d
        assert "grade" in d
        assert "factors" in d
        assert "improvements" in d
        assert "penalties_total" in d
        assert "base_score" in d

    def test_to_dict_serializable(self):
        import json

        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)
        d = result.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(d)
        assert len(json_str) > 0


# ---------------------------------------------------------------------------
# Test: Grade assignment
# ---------------------------------------------------------------------------

class TestGrades:
    def test_perfect_score_a_plus(self):
        comp = _make_component("web", replicas=3)
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)
        assert result.grade in ("A+", "A")

    def test_low_score_f(self):
        # Create many SPOFs with high utilization
        comps = []
        deps = []
        for i in range(5):
            svc = _make_component(f"svc{i}", cpu=95)
            comps.append(svc)
        # All depend on each other to create max penalty
        db = _make_component("db", ComponentType.DATABASE, cpu=95)
        comps.append(db)
        for i in range(5):
            deps.append((f"svc{i}", "db"))

        graph = _build_graph(comps, deps)
        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        # Should have a low grade
        assert result.grade in ("F", "D-", "D", "D+", "C-")
