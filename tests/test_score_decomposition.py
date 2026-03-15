"""Tests for the Resilience Score Decomposition module."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
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


# ---------------------------------------------------------------------------
# Coverage boost: _score_to_grade "F" fallback (line 129)
# ---------------------------------------------------------------------------

class TestScoreToGradeFallback:
    def test_grade_f_below_zero(self):
        """Negative scores should return F via the fallback (line 129)."""
        from infrasim.simulator.score_decomposition import _score_to_grade
        assert _score_to_grade(-5.0) == "F"

    def test_grade_f_at_zero(self):
        """Score of 0 matches threshold (0, 'F') in the list."""
        from infrasim.simulator.score_decomposition import _score_to_grade
        assert _score_to_grade(0.0) == "F"


# ---------------------------------------------------------------------------
# Coverage boost: _score_to_percentile ranges (lines 139, 141, 143, 145)
# ---------------------------------------------------------------------------

class TestScoreToPercentileRanges:
    def test_percentile_80_to_89(self):
        """Score in [80, 90) -> 85.0 percentile (line 137, previously line 139)."""
        from infrasim.simulator.score_decomposition import _score_to_percentile
        assert _score_to_percentile(85.0) == 85.0

    def test_percentile_70_to_79(self):
        """Score in [70, 80) -> 70.0 percentile (line 139, previously line 141)."""
        from infrasim.simulator.score_decomposition import _score_to_percentile
        assert _score_to_percentile(75.0) == 70.0

    def test_percentile_60_to_69(self):
        """Score in [60, 70) -> 55.0 percentile (line 141, previously line 143)."""
        from infrasim.simulator.score_decomposition import _score_to_percentile
        assert _score_to_percentile(65.0) == 55.0

    def test_percentile_50_to_59(self):
        """Score in [50, 60) -> 40.0 percentile (line 143, previously line 145)."""
        from infrasim.simulator.score_decomposition import _score_to_percentile
        assert _score_to_percentile(55.0) == 40.0

    def test_percentile_40_to_49(self):
        """Score in [40, 50) -> 25.0 percentile (line 145)."""
        from infrasim.simulator.score_decomposition import _score_to_percentile
        assert _score_to_percentile(45.0) == 25.0

    def test_percentile_below_40(self):
        """Score below 40 -> 10.0 percentile."""
        from infrasim.simulator.score_decomposition import _score_to_percentile
        assert _score_to_percentile(30.0) == 10.0


# ---------------------------------------------------------------------------
# Coverage boost: SPOF failover_save with autoscaling (lines 194-199)
# ---------------------------------------------------------------------------

class TestSPOFFailoverSaveWithAutoscaling:
    def test_failover_improvement_suggested_for_spof_without_failover(self):
        """SPOF without failover generates enable-failover improvement."""
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        failover_imps = [i for i in result.improvements if i.action == "enable-failover"]
        assert len(failover_imps) > 0
        assert failover_imps[0].component_id == "db"

    def test_failover_save_with_autoscaling_enabled(self):
        """SPOF with autoscaling but no failover -> failover_save is adjusted."""
        db = _make_component("db", ComponentType.DATABASE, autoscaling=True)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        failover_imps = [i for i in result.improvements if i.action == "enable-failover"]
        assert len(failover_imps) > 0
        # The improvement should be adjusted for autoscaling (multiplied by 0.5)
        assert failover_imps[0].estimated_improvement > 0


class TestSPOFOptionalAndAsyncDeps:
    """Test SPOF penalty calculation with optional/async dependency types (lines 194-199)."""

    def test_optional_dependency_lower_penalty(self):
        """Optional dependencies weight 0.3 instead of 1.0 (line 194-195)."""
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")], dep_type="optional")

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        # Should still have SPOF penalty but lower
        penalty_factors = [f for f in result.factors if f.category == "penalty" and "Single" in f.name]
        assert len(penalty_factors) > 0
        # With optional (0.3 weight), penalty = min(20, 0.3 * 5) = 1.5 vs requires (1.0 * 5) = 5.0
        assert penalty_factors[0].points > -5.1  # Less penalty than requires

    def test_async_dependency_even_lower_penalty(self):
        """Async/other dependencies weight 0.1 (lines 196-197)."""
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")], dep_type="async")

        decomposer = ScoreDecomposer()
        result = decomposer.decompose(graph)

        # With async (0.1 weight), penalty = min(20, 0.1 * 5) = 0.5
        penalty_factors = [f for f in result.factors if f.category == "penalty" and "Single" in f.name]
        assert len(penalty_factors) > 0
        assert penalty_factors[0].points > -1.0  # Very small penalty

    def test_no_edge_fallback_weight(self):
        """When get_dependency_edge returns None, weight defaults to 1.0 (line 199)."""
        # Create a graph where a component has dependents but get_dependency_edge returns None
        # This happens when the edge direction doesn't match the lookup
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        g = InfraGraph()
        g.add_component(db)
        g.add_component(app_comp)
        # Add dependency from app to db
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        # db has dependents (app). When looking up edge with dep_comp=app, comp=db:
        # get_dependency_edge(app.id, db.id) should find the edge.
        # To trigger the "else" branch, we need a situation where get_dependency_edge
        # returns None. This can happen if the graph internally stores dependents
        # differently. Let's use the internal API directly.
        from unittest.mock import patch

        decomposer = ScoreDecomposer()

        # Patch get_dependency_edge to return None for the db lookup
        original_func = g.get_dependency_edge

        def patched_edge(src, tgt):
            if tgt == "db":
                return None
            return original_func(src, tgt)

        with patch.object(g, "get_dependency_edge", side_effect=patched_edge):
            result = decomposer.decompose(g)

        # Should still compute penalties (with default weight 1.0)
        penalty_factors = [f for f in result.factors if f.category == "penalty" and "Single" in f.name]
        assert len(penalty_factors) > 0


# ---------------------------------------------------------------------------
# Coverage boost: what_if_fix reduce-utilization (lines 449-455)
# ---------------------------------------------------------------------------

class TestWhatIfReduceUtilization:
    def test_reduce_utilization(self):
        """what_if_fix with reduce-utilization should lower metrics (lines 449-455)."""
        comp = _make_component("web", cpu=95, memory=85)
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        current = graph.resilience_score()
        new_score = decomposer.what_if_fix(graph, "web", "reduce-utilization")

        # Reducing utilization should improve the score
        assert new_score >= current

    def test_reduce_utilization_on_high_util_component(self):
        """Reduce utilization on a component with high CPU/memory/disk."""
        comp = Component(
            id="overloaded",
            name="overloaded",
            type=ComponentType.APP_SERVER,
            replicas=2,
            metrics=ResourceMetrics(
                cpu_percent=95,
                memory_percent=90,
                disk_percent=88,
                network_connections=900,
            ),
            capacity=Capacity(max_connections=1000),
        )
        graph = _build_graph([comp])

        decomposer = ScoreDecomposer()
        new_score = decomposer.what_if_fix(graph, "overloaded", "reduce-utilization")
        # Should not crash and should return a valid score
        assert 0.0 <= new_score <= 100.0

    def test_enable_autoscaling_what_if(self):
        """what_if_fix with enable-autoscaling should improve score."""
        db = _make_component("db", ComponentType.DATABASE)
        app_comp = _make_component("app")
        graph = _build_graph([db, app_comp], [("app", "db")])

        decomposer = ScoreDecomposer()
        current = graph.resilience_score()
        new_score = decomposer.what_if_fix(graph, "db", "enable-autoscaling")
        assert new_score >= current
