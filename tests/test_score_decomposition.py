"""Tests for the Resilience Score Decomposition module.

Comprehensive tests covering:
- Dataclasses: ScoreFactor, ScoreImprovement, ScoreDecomposition (incl. to_dict)
- Helper functions: _score_to_grade(), _score_to_percentile()
- ScoreDecomposer.decompose() with various infrastructure configurations
- ScoreDecomposer.what_if_fix() for each fix type
- ScoreDecomposer.explain()
- ScoreDecomposer.to_waterfall_data()
- ScoreDecomposer._build_breakdown_text()
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.score_decomposition import (
    ScoreDecomposer,
    ScoreDecomposition,
    ScoreFactor,
    ScoreImprovement,
    _score_to_grade,
    _score_to_percentile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    *,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    cpu: float = 0.0,
    memory: float = 0.0,
    disk: float = 0.0,
    net_conns: int = 0,
    max_conns: int = 1000,
) -> Component:
    """Create a Component with concise kwargs."""
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        metrics=ResourceMetrics(
            cpu_percent=cpu,
            memory_percent=memory,
            disk_percent=disk,
            network_connections=net_conns,
        ),
        capacity=Capacity(max_connections=max_conns),
    )


def _chain_graph(
    length: int,
    *,
    replicas: int = 1,
    dep_type: str = "requires",
) -> InfraGraph:
    """Build a linear dependency chain: c0 -> c1 -> ... -> c{length-1}."""
    g = InfraGraph()
    for i in range(length):
        g.add_component(_comp(f"c{i}", replicas=replicas))
    for i in range(length - 1):
        g.add_dependency(
            Dependency(source_id=f"c{i}", target_id=f"c{i + 1}", dependency_type=dep_type)
        )
    return g


def _graph(
    components: list[Component],
    deps: list[tuple[str, str]] | None = None,
    *,
    dep_type: str = "requires",
    cb_enabled: bool = False,
) -> InfraGraph:
    """Build a graph from components and (source, target) dependency pairs."""
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in deps or []:
        g.add_dependency(
            Dependency(
                source_id=src,
                target_id=tgt,
                dependency_type=dep_type,
                circuit_breaker=CircuitBreakerConfig(enabled=cb_enabled),
            )
        )
    return g


# ---------------------------------------------------------------------------
# Test: ScoreFactor dataclass
# ---------------------------------------------------------------------------


class TestScoreFactor:
    def test_penalty_factor_fields(self):
        f = ScoreFactor(
            name="SPOF",
            category="penalty",
            points=-10.0,
            description="Single point of failure",
            affected_components=["db"],
            remediation="Add replicas",
        )
        assert f.name == "SPOF"
        assert f.category == "penalty"
        assert f.points == -10.0
        assert f.description == "Single point of failure"
        assert f.affected_components == ["db"]
        assert f.remediation == "Add replicas"

    def test_bonus_factor_defaults(self):
        f = ScoreFactor(
            name="Failover",
            category="bonus",
            points=0,
            description="Failover coverage",
        )
        assert f.category == "bonus"
        assert f.affected_components == []
        assert f.remediation is None

    def test_neutral_category(self):
        f = ScoreFactor(
            name="CB Coverage",
            category="neutral",
            points=0,
            description="Circuit breaker info",
        )
        assert f.category == "neutral"


# ---------------------------------------------------------------------------
# Test: ScoreImprovement dataclass
# ---------------------------------------------------------------------------


class TestScoreImprovement:
    def test_all_fields(self):
        imp = ScoreImprovement(
            action="add-replica",
            component_id="db",
            estimated_improvement=8.0,
            effort="medium",
            description="Add replicas to db",
        )
        assert imp.action == "add-replica"
        assert imp.component_id == "db"
        assert imp.estimated_improvement == 8.0
        assert imp.effort == "medium"
        assert imp.description == "Add replicas to db"

    def test_low_effort(self):
        imp = ScoreImprovement(
            action="enable-autoscaling",
            component_id="web",
            estimated_improvement=3.0,
            effort="low",
            description="Enable autoscaling",
        )
        assert imp.effort == "low"


# ---------------------------------------------------------------------------
# Test: ScoreDecomposition dataclass and to_dict()
# ---------------------------------------------------------------------------


class TestScoreDecomposition:
    def test_defaults(self):
        d = ScoreDecomposition(total_score=72.0)
        assert d.total_score == 72.0
        assert d.max_possible_score == 100.0
        assert d.base_score == 100.0
        assert d.penalties_total == 0.0
        assert d.bonuses_total == 0.0
        assert d.grade == "C"
        assert d.percentile_estimate == 50.0
        assert d.factors == []
        assert d.improvements == []
        assert d.score_breakdown_text == ""

    def test_to_dict_all_keys(self):
        d = ScoreDecomposition(
            total_score=85.0,
            max_possible_score=100.0,
            base_score=100.0,
            penalties_total=15.0,
            bonuses_total=0.0,
            grade="A-",
            percentile_estimate=85.0,
            score_breakdown_text="Test text",
            factors=[
                ScoreFactor(
                    name="SPOF",
                    category="penalty",
                    points=-15.0,
                    description="SPOF desc",
                    affected_components=["db"],
                    remediation="Fix it",
                )
            ],
            improvements=[
                ScoreImprovement(
                    action="add-replica",
                    component_id="db",
                    estimated_improvement=10.0,
                    effort="medium",
                    description="Add replicas",
                )
            ],
        )
        result = d.to_dict()

        assert result["total_score"] == 85.0
        assert result["max_possible_score"] == 100.0
        assert result["base_score"] == 100.0
        assert result["penalties_total"] == 15.0
        assert result["bonuses_total"] == 0.0
        assert result["grade"] == "A-"
        assert result["percentile_estimate"] == 85.0
        assert result["score_breakdown_text"] == "Test text"

        assert len(result["factors"]) == 1
        f = result["factors"][0]
        assert f["name"] == "SPOF"
        assert f["category"] == "penalty"
        assert f["points"] == -15.0
        assert f["description"] == "SPOF desc"
        assert f["affected_components"] == ["db"]
        assert f["remediation"] == "Fix it"

        assert len(result["improvements"]) == 1
        imp = result["improvements"][0]
        assert imp["action"] == "add-replica"
        assert imp["component_id"] == "db"
        assert imp["estimated_improvement"] == 10.0
        assert imp["effort"] == "medium"
        assert imp["description"] == "Add replicas"

    def test_to_dict_json_serializable(self):
        d = ScoreDecomposition(
            total_score=50.123456,
            factors=[
                ScoreFactor(name="P", category="penalty", points=-3.777, description="d"),
            ],
            improvements=[
                ScoreImprovement(
                    action="a", component_id="c", estimated_improvement=1.999,
                    effort="low", description="d",
                ),
            ],
        )
        result = d.to_dict()
        json_str = json.dumps(result)
        assert len(json_str) > 0
        # Values should be rounded
        assert result["total_score"] == 50.1
        assert result["factors"][0]["points"] == -3.8
        assert result["improvements"][0]["estimated_improvement"] == 2.0

    def test_to_dict_empty_factors_and_improvements(self):
        d = ScoreDecomposition(total_score=100.0)
        result = d.to_dict()
        assert result["factors"] == []
        assert result["improvements"] == []


# ---------------------------------------------------------------------------
# Test: _score_to_grade() helper
# ---------------------------------------------------------------------------


class TestScoreToGrade:
    @pytest.mark.parametrize(
        "score, expected_grade",
        [
            (100.0, "A+"),
            (95.0, "A+"),
            (94.9, "A"),
            (90.0, "A"),
            (89.9, "A-"),
            (85.0, "A-"),
            (84.9, "B+"),
            (80.0, "B+"),
            (79.9, "B"),
            (75.0, "B"),
            (74.9, "B-"),
            (70.0, "B-"),
            (69.9, "C+"),
            (65.0, "C+"),
            (64.9, "C"),
            (60.0, "C"),
            (59.9, "C-"),
            (55.0, "C-"),
            (54.9, "D+"),
            (50.0, "D+"),
            (49.9, "D"),
            (45.0, "D"),
            (44.9, "D-"),
            (40.0, "D-"),
            (39.9, "F"),
            (0.0, "F"),
        ],
    )
    def test_grade_thresholds(self, score, expected_grade):
        assert _score_to_grade(score) == expected_grade

    def test_negative_score_returns_f(self):
        """Negative scores fall through all thresholds to the fallback."""
        assert _score_to_grade(-5.0) == "F"
        assert _score_to_grade(-100.0) == "F"


# ---------------------------------------------------------------------------
# Test: _score_to_percentile() helper
# ---------------------------------------------------------------------------


class TestScoreToPercentile:
    @pytest.mark.parametrize(
        "score, expected",
        [
            (95.0, 95.0),
            (90.0, 95.0),
            (89.9, 85.0),
            (80.0, 85.0),
            (79.9, 70.0),
            (70.0, 70.0),
            (69.9, 55.0),
            (60.0, 55.0),
            (59.9, 40.0),
            (50.0, 40.0),
            (49.9, 25.0),
            (40.0, 25.0),
            (39.9, 10.0),
            (0.0, 10.0),
        ],
    )
    def test_percentile_ranges(self, score, expected):
        assert _score_to_percentile(score) == expected


# ---------------------------------------------------------------------------
# Test: ScoreDecomposer.decompose() — empty graph
# ---------------------------------------------------------------------------


class TestDecomposeEmptyGraph:
    def test_empty_graph_returns_zero(self):
        g = InfraGraph()
        result = ScoreDecomposer().decompose(g)
        assert result.total_score == 0.0
        assert result.grade == "F"
        assert result.percentile_estimate == 0.0
        assert result.score_breakdown_text == "No components loaded."
        assert result.factors == []
        assert result.improvements == []


# ---------------------------------------------------------------------------
# Test: ScoreDecomposer.decompose() — perfect graph (no penalties)
# ---------------------------------------------------------------------------


class TestDecomposePerfectGraph:
    def test_single_component_no_deps(self):
        """A lone component with replicas has no SPOF, no penalties."""
        g = _graph([_comp("web", replicas=3)])
        result = ScoreDecomposer().decompose(g)
        assert result.total_score == 100.0
        assert result.grade in ("A+", "A")
        assert result.percentile_estimate == 95.0
        assert result.penalties_total == 0.0

    def test_multi_component_all_replicated(self):
        """All components have replicas=2 -> no SPOF penalty."""
        app = _comp("app", replicas=2)
        db = _comp("db", ComponentType.DATABASE, replicas=2)
        g = _graph([app, db], [("app", "db")])
        result = ScoreDecomposer().decompose(g)
        assert result.total_score == 100.0

    def test_base_score_always_100(self):
        g = _graph([_comp("web")])
        result = ScoreDecomposer().decompose(g)
        assert result.base_score == 100.0
        assert result.max_possible_score == 100.0


# ---------------------------------------------------------------------------
# Test: SPOF penalty decomposition
# ---------------------------------------------------------------------------


class TestSPOFPenalty:
    def test_single_spof_with_requires_dep(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        penalty_factors = [f for f in result.factors if f.category == "penalty" and "Single" in f.name]
        assert len(penalty_factors) == 1
        assert penalty_factors[0].points < 0
        assert "db" in penalty_factors[0].affected_components
        assert penalty_factors[0].remediation is not None

    def test_spof_penalty_value_for_single_requires_dep(self):
        """With 1 'requires' dependent: weighted_deps=1.0, penalty=min(20, 1*5)=5."""
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        spof = [f for f in result.factors if "Single" in f.name][0]
        assert spof.points == -5.0

    def test_optional_dep_lower_weight(self):
        """Optional dependency weights 0.3 -> penalty = min(20, 0.3*5) = 1.5."""
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")], dep_type="optional")

        result = ScoreDecomposer().decompose(g)
        spof = [f for f in result.factors if "Single" in f.name][0]
        assert spof.points == -1.5

    def test_async_dep_lowest_weight(self):
        """Async dependency weights 0.1 -> penalty = min(20, 0.1*5) = 0.5."""
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")], dep_type="async")

        result = ScoreDecomposer().decompose(g)
        spof = [f for f in result.factors if "Single" in f.name][0]
        assert spof.points == -0.5

    def test_edge_not_found_defaults_to_weight_1(self):
        """When get_dependency_edge returns None, weight falls back to 1.0."""
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        decomposer = ScoreDecomposer()
        original_get_edge = g.get_dependency_edge

        def patched_edge(src, tgt):
            if tgt == "db":
                return None
            return original_get_edge(src, tgt)

        with patch.object(g, "get_dependency_edge", side_effect=patched_edge):
            result = decomposer.decompose(g)

        spof = [f for f in result.factors if "Single" in f.name][0]
        assert spof.points == -5.0  # 1.0 * 5 = 5

    def test_multiple_dependents_increase_penalty(self):
        """3 dependents with 'requires' -> weighted_deps=3.0, penalty=min(20,15)=15."""
        db = _comp("db", ComponentType.DATABASE)
        a1 = _comp("app1")
        a2 = _comp("app2")
        a3 = _comp("app3")
        g = _graph(
            [db, a1, a2, a3],
            [("app1", "db"), ("app2", "db"), ("app3", "db")],
        )

        result = ScoreDecomposer().decompose(g)
        spof = [f for f in result.factors if "Single" in f.name][0]
        assert spof.points == -15.0

    def test_penalty_capped_at_20(self):
        """Penalty is capped at min(20, weighted_deps * 5)."""
        db = _comp("db", ComponentType.DATABASE)
        apps = [_comp(f"a{i}") for i in range(10)]
        deps = [(f"a{i}", "db") for i in range(10)]
        g = _graph([db] + apps, deps)

        result = ScoreDecomposer().decompose(g)
        spof = [f for f in result.factors if "Single" in f.name][0]
        assert spof.points == -20.0  # capped

    def test_failover_reduces_penalty_by_70pct(self):
        """Failover reduces penalty to 30% of original."""
        db_no_fo = _comp("db", ComponentType.DATABASE)
        db_fo = _comp("db", ComponentType.DATABASE, failover=True)
        app1 = _comp("app")
        app2 = _comp("app")
        g1 = _graph([db_no_fo, app1], [("app", "db")])
        g2 = _graph([db_fo, app2], [("app", "db")])

        r1 = ScoreDecomposer().decompose(g1)
        r2 = ScoreDecomposer().decompose(g2)
        assert r2.total_score > r1.total_score
        # penalty without: 5.0, with failover: 5.0 * 0.3 = 1.5
        spof2 = [f for f in r2.factors if "Single" in f.name][0]
        assert spof2.points == -1.5

    def test_autoscaling_reduces_penalty_by_50pct(self):
        """Autoscaling reduces penalty to 50% of original."""
        db_as = _comp("db", ComponentType.DATABASE, autoscaling=True)
        app = _comp("app")
        g = _graph([db_as, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        spof = [f for f in result.factors if "Single" in f.name][0]
        assert spof.points == -2.5  # 5.0 * 0.5

    def test_failover_and_autoscaling_stack(self):
        """Both failover and autoscaling: penalty * 0.3 * 0.5 = 15%."""
        db = _comp("db", ComponentType.DATABASE, failover=True, autoscaling=True)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        spof = [f for f in result.factors if "Single" in f.name][0]
        # 5.0 * 0.3 * 0.5 = 0.75
        assert abs(spof.points - (-0.75)) < 0.01

    def test_replicas_gt_1_no_spof_penalty(self):
        """Component with replicas>1 is not a SPOF."""
        db = _comp("db", ComponentType.DATABASE, replicas=2)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        spof_factors = [f for f in result.factors if "Single" in f.name]
        assert len(spof_factors) == 0

    def test_no_dependents_no_spof_penalty(self):
        """A component with replicas=1 but no dependents is not penalized."""
        db = _comp("db", ComponentType.DATABASE)
        g = _graph([db])

        result = ScoreDecomposer().decompose(g)
        spof_factors = [f for f in result.factors if "Single" in f.name]
        assert len(spof_factors) == 0

    def test_score_matches_resilience_score(self):
        """Decomposed score must match InfraGraph.resilience_score()."""
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        assert abs(result.total_score - g.resilience_score()) < 0.01


# ---------------------------------------------------------------------------
# Test: Utilization penalty decomposition
# ---------------------------------------------------------------------------


class TestUtilizationPenalty:
    def test_cpu_above_90_penalty_15(self):
        web = _comp("web", cpu=95)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        util_factors = [f for f in result.factors if "Utilization" in f.name]
        assert len(util_factors) == 1
        assert util_factors[0].points == -15.0
        assert "web" in util_factors[0].affected_components

    def test_cpu_above_80_penalty_8(self):
        web = _comp("web", cpu=85)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        util_factors = [f for f in result.factors if "Utilization" in f.name]
        assert util_factors[0].points == -8.0

    def test_cpu_above_70_penalty_3(self):
        web = _comp("web", cpu=75)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        util_factors = [f for f in result.factors if "Utilization" in f.name]
        assert util_factors[0].points == -3.0

    def test_cpu_70_or_below_no_penalty(self):
        web = _comp("web", cpu=70)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        util_factors = [f for f in result.factors if "Utilization" in f.name]
        assert len(util_factors) == 0

    def test_multiple_high_util_components(self):
        """Penalties accumulate across components."""
        w1 = _comp("w1", cpu=95)  # -15
        w2 = _comp("w2", cpu=85)  # -8
        g = _graph([w1, w2])

        result = ScoreDecomposer().decompose(g)
        util_factors = [f for f in result.factors if "Utilization" in f.name]
        assert util_factors[0].points == -(15 + 8)
        assert len(util_factors[0].affected_components) == 2

    def test_autoscaling_suggestion_for_high_util(self):
        """High util without autoscaling -> enable-autoscaling improvement."""
        web = _comp("web", cpu=95)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        as_imps = [i for i in result.improvements if i.action == "enable-autoscaling"]
        assert len(as_imps) == 1
        assert as_imps[0].component_id == "web"
        assert as_imps[0].effort == "low"

    def test_no_autoscaling_suggestion_when_enabled(self):
        """High util with autoscaling -> no enable-autoscaling improvement."""
        web = _comp("web", cpu=95, autoscaling=True)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        as_imps = [i for i in result.improvements if i.action == "enable-autoscaling"]
        assert len(as_imps) == 0

    def test_utilization_score_matches(self):
        web = _comp("web", cpu=85)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        assert abs(result.total_score - g.resilience_score()) < 0.01

    def test_memory_utilization_triggers_penalty(self):
        """Memory utilization (via max()) also triggers penalties."""
        web = _comp("web", memory=92)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        util_factors = [f for f in result.factors if "Utilization" in f.name]
        assert len(util_factors) == 1
        assert util_factors[0].points == -15.0


# ---------------------------------------------------------------------------
# Test: Chain depth penalty decomposition
# ---------------------------------------------------------------------------


class TestChainDepthPenalty:
    def test_depth_6_penalty_5(self):
        """Chain of 6 -> max_depth=6, penalty = (6-5)*5 = 5."""
        g = _chain_graph(6, replicas=2)
        result = ScoreDecomposer().decompose(g)

        chain_factors = [f for f in result.factors if "Chain" in f.name or "Depth" in f.name]
        assert len(chain_factors) == 1
        assert chain_factors[0].points == -5.0

    def test_depth_7_penalty_10(self):
        """Chain of 7 -> max_depth=7, penalty = (7-5)*5 = 10."""
        g = _chain_graph(7, replicas=2)
        result = ScoreDecomposer().decompose(g)

        chain_factors = [f for f in result.factors if "Depth" in f.name]
        assert chain_factors[0].points == -10.0

    def test_depth_5_no_penalty(self):
        """Chain of 5 -> max_depth=5, no penalty (threshold is >5)."""
        g = _chain_graph(5, replicas=2)
        result = ScoreDecomposer().decompose(g)

        chain_factors = [f for f in result.factors if "Chain" in f.name or "Depth" in f.name]
        assert len(chain_factors) == 0

    def test_depth_3_no_penalty(self):
        """Short chains have no chain depth penalty."""
        g = _chain_graph(3, replicas=2)
        result = ScoreDecomposer().decompose(g)

        chain_factors = [f for f in result.factors if "Chain" in f.name or "Depth" in f.name]
        assert len(chain_factors) == 0

    def test_no_critical_paths_no_penalty(self):
        """Single component (no paths) -> no chain penalty."""
        g = _graph([_comp("solo", replicas=2)])
        result = ScoreDecomposer().decompose(g)

        chain_factors = [f for f in result.factors if "Chain" in f.name or "Depth" in f.name]
        assert len(chain_factors) == 0


# ---------------------------------------------------------------------------
# Test: Bonus factors (informational)
# ---------------------------------------------------------------------------


class TestBonusFactors:
    def test_failover_coverage_bonus(self):
        """Components with failover generate a Failover Coverage bonus factor."""
        web = _comp("web", failover=True, replicas=2)
        db = _comp("db", ComponentType.DATABASE, replicas=2)
        g = _graph([web, db])

        result = ScoreDecomposer().decompose(g)
        fo_factors = [f for f in result.factors if "Failover" in f.name]
        assert len(fo_factors) == 1
        assert fo_factors[0].category == "bonus"
        assert fo_factors[0].points == 0  # Informational
        assert "web" in fo_factors[0].affected_components

    def test_no_failover_no_bonus(self):
        web = _comp("web", replicas=2)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        fo_factors = [f for f in result.factors if "Failover Coverage" in f.name]
        assert len(fo_factors) == 0

    def test_autoscaling_coverage_bonus(self):
        web = _comp("web", autoscaling=True, replicas=2)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        as_factors = [f for f in result.factors if "Autoscaling" in f.name]
        assert len(as_factors) == 1
        assert as_factors[0].category == "bonus"

    def test_no_autoscaling_no_bonus(self):
        web = _comp("web", replicas=2)
        g = _graph([web])

        result = ScoreDecomposer().decompose(g)
        as_factors = [f for f in result.factors if "Autoscaling Coverage" in f.name]
        assert len(as_factors) == 0

    def test_circuit_breaker_coverage_bonus(self):
        """Edges with circuit breakers generate a CB Coverage bonus factor."""
        app = _comp("app", replicas=2)
        db = _comp("db", ComponentType.DATABASE, replicas=2)
        g = _graph([app, db], [("app", "db")], cb_enabled=True)

        result = ScoreDecomposer().decompose(g)
        cb_factors = [f for f in result.factors if "Circuit Breaker" in f.name]
        assert len(cb_factors) == 1
        assert cb_factors[0].category == "bonus"

    def test_circuit_breaker_neutral_when_none_enabled(self):
        """Edges without circuit breakers -> neutral category."""
        app = _comp("app", replicas=2)
        db = _comp("db", ComponentType.DATABASE, replicas=2)
        g = _graph([app, db], [("app", "db")], cb_enabled=False)

        result = ScoreDecomposer().decompose(g)
        cb_factors = [f for f in result.factors if "Circuit Breaker" in f.name]
        assert len(cb_factors) == 1
        assert cb_factors[0].category == "neutral"

    def test_no_edges_no_cb_factor(self):
        """No dependency edges -> no CB factor at all."""
        g = _graph([_comp("web", replicas=2)])
        result = ScoreDecomposer().decompose(g)

        cb_factors = [f for f in result.factors if "Circuit Breaker" in f.name]
        assert len(cb_factors) == 0

    def test_replica_redundancy_bonus(self):
        """Components with replicas>1 generate a Replica Redundancy factor."""
        web = _comp("web", replicas=3)
        db = _comp("db", ComponentType.DATABASE, replicas=2)
        g = _graph([web, db])

        result = ScoreDecomposer().decompose(g)
        rep_factors = [f for f in result.factors if "Replica" in f.name]
        assert len(rep_factors) == 1
        assert rep_factors[0].category == "bonus"
        assert "web" in rep_factors[0].affected_components
        assert "db" in rep_factors[0].affected_components
        # avg replicas: (3+2)/2 = 2.5
        assert "2.5" in rep_factors[0].description

    def test_no_multi_replica_no_bonus(self):
        """All components have replicas=1 -> no Replica Redundancy factor."""
        g = _graph([_comp("web")])
        result = ScoreDecomposer().decompose(g)

        rep_factors = [f for f in result.factors if "Replica" in f.name]
        assert len(rep_factors) == 0


# ---------------------------------------------------------------------------
# Test: Improvements generation
# ---------------------------------------------------------------------------


class TestImprovements:
    def test_spof_generates_add_replica_improvement(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        ar_imps = [i for i in result.improvements if i.action == "add-replica"]
        assert len(ar_imps) > 0
        assert ar_imps[0].component_id == "db"
        assert ar_imps[0].effort == "medium"
        assert ar_imps[0].estimated_improvement > 0

    def test_spof_without_failover_generates_failover_improvement(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        fo_imps = [i for i in result.improvements if i.action == "enable-failover"]
        assert len(fo_imps) > 0
        assert fo_imps[0].component_id == "db"
        assert fo_imps[0].effort == "medium"

    def test_spof_with_failover_no_failover_improvement(self):
        """No enable-failover suggestion when failover is already on."""
        db = _comp("db", ComponentType.DATABASE, failover=True)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        fo_imps = [i for i in result.improvements if i.action == "enable-failover"]
        assert len(fo_imps) == 0

    def test_failover_save_adjusted_for_autoscaling(self):
        """Failover save is halved when autoscaling is already enabled."""
        db_as = _comp("db", ComponentType.DATABASE, autoscaling=True)
        app = _comp("app")
        g = _graph([db_as, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        fo_imps = [i for i in result.improvements if i.action == "enable-failover"]
        assert len(fo_imps) > 0
        # original_penalty=5, failover_save = 5 - 5*0.3 = 3.5, * 0.5 (autoscaling) = 1.75
        # Rounded to 1 decimal in ScoreImprovement -> 1.8
        assert abs(fo_imps[0].estimated_improvement - 1.8) < 0.01

    def test_improvements_sorted_by_impact_descending(self):
        """Improvements should be sorted by estimated_improvement (descending)."""
        db = _comp("db", ComponentType.DATABASE)
        cache = _comp("cache", ComponentType.CACHE)
        a1, a2, a3 = _comp("a1"), _comp("a2"), _comp("a3")
        g = _graph(
            [db, cache, a1, a2, a3],
            [("a1", "db"), ("a2", "db"), ("a3", "db"), ("a1", "cache")],
        )

        result = ScoreDecomposer().decompose(g)
        for i in range(len(result.improvements) - 1):
            assert (
                result.improvements[i].estimated_improvement
                >= result.improvements[i + 1].estimated_improvement
            )


# ---------------------------------------------------------------------------
# Test: Final score clamping and totals
# ---------------------------------------------------------------------------


class TestFinalScoreComputation:
    def test_score_clamped_to_0(self):
        """Score should never go below 0."""
        # Create massive penalties
        comps = []
        deps = []
        db = _comp("db", ComponentType.DATABASE, cpu=95)
        comps.append(db)
        for i in range(10):
            svc = _comp(f"s{i}", cpu=95)
            comps.append(svc)
            deps.append((f"s{i}", "db"))
        g = _graph(comps, deps)

        result = ScoreDecomposer().decompose(g)
        assert result.total_score >= 0.0

    def test_score_clamped_to_100(self):
        """Score should never exceed 100."""
        g = _graph([_comp("web", replicas=10)])
        result = ScoreDecomposer().decompose(g)
        assert result.total_score <= 100.0

    def test_penalties_total_sum(self):
        """penalties_total = SPOF + util + chain penalties."""
        db = _comp("db", ComponentType.DATABASE, cpu=95)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        result = ScoreDecomposer().decompose(g)
        expected = abs(sum(f.points for f in result.factors if f.category == "penalty"))
        assert abs(result.penalties_total - expected) < 0.01

    def test_bonuses_total_is_zero_v1(self):
        """In v1, bonuses_total is always 0 (bonuses are implicit)."""
        db = _comp("db", ComponentType.DATABASE, failover=True, replicas=2)
        g = _graph([db])
        result = ScoreDecomposer().decompose(g)
        assert result.bonuses_total == 0.0


# ---------------------------------------------------------------------------
# Test: Score matches resilience_score() for complex graphs
# ---------------------------------------------------------------------------


class TestScoreMatchesComplex:
    def test_complex_multi_tier_graph(self):
        lb = _comp("lb", ComponentType.LOAD_BALANCER, replicas=2)
        web = _comp("web", ComponentType.WEB_SERVER, failover=True)
        app = _comp("app", cpu=82)
        db = _comp("db", ComponentType.DATABASE)
        cache = _comp("cache", ComponentType.CACHE, replicas=3)

        g = _graph(
            [lb, web, app, db, cache],
            [("lb", "web"), ("web", "app"), ("app", "db"), ("app", "cache")],
        )

        result = ScoreDecomposer().decompose(g)
        assert abs(result.total_score - g.resilience_score()) < 0.01

    def test_all_spof_with_mixed_utils(self):
        db = _comp("db", ComponentType.DATABASE, cpu=95)
        web = _comp("web", cpu=75)
        app = _comp("app", cpu=50)

        g = _graph(
            [db, web, app],
            [("web", "db"), ("app", "db")],
        )

        result = ScoreDecomposer().decompose(g)
        assert abs(result.total_score - g.resilience_score()) < 0.01

    def test_fully_optimized_graph(self):
        """All components redundant, low utilization, short chain."""
        lb = _comp("lb", ComponentType.LOAD_BALANCER, replicas=2, failover=True)
        web = _comp("web", ComponentType.WEB_SERVER, replicas=3, failover=True, autoscaling=True)
        db = _comp("db", ComponentType.DATABASE, replicas=2, failover=True)
        g = _graph(
            [lb, web, db],
            [("lb", "web"), ("web", "db")],
        )
        result = ScoreDecomposer().decompose(g)
        assert result.total_score == 100.0
        assert result.grade in ("A+", "A")


# ---------------------------------------------------------------------------
# Test: what_if_fix
# ---------------------------------------------------------------------------


class TestWhatIfFix:
    def test_add_replica_improves_score(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        current = g.resilience_score()
        new_score = ScoreDecomposer().what_if_fix(g, "db", "add-replica")
        assert new_score > current

    def test_enable_failover_improves_score(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        current = g.resilience_score()
        new_score = ScoreDecomposer().what_if_fix(g, "db", "enable-failover")
        assert new_score > current

    def test_enable_autoscaling_improves_score(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        current = g.resilience_score()
        new_score = ScoreDecomposer().what_if_fix(g, "db", "enable-autoscaling")
        assert new_score >= current

    def test_reduce_utilization_improves_score(self):
        web = _comp("web", cpu=95, memory=85)
        g = _graph([web])

        current = g.resilience_score()
        new_score = ScoreDecomposer().what_if_fix(g, "web", "reduce-utilization")
        assert new_score >= current

    def test_reduce_utilization_with_all_metrics(self):
        """reduce-utilization caps CPU, memory, disk and network_connections."""
        comp = Component(
            id="srv",
            name="srv",
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
        g = _graph([comp])

        new_score = ScoreDecomposer().what_if_fix(g, "srv", "reduce-utilization")
        assert 0.0 <= new_score <= 100.0

    def test_nonexistent_component_returns_current_score(self):
        web = _comp("web")
        g = _graph([web])

        score = ScoreDecomposer().what_if_fix(g, "nonexistent", "add-replica")
        assert score == g.resilience_score()

    def test_what_if_does_not_mutate_original(self):
        """The original graph must be unchanged after what_if_fix."""
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        original_score = g.resilience_score()
        ScoreDecomposer().what_if_fix(g, "db", "add-replica")

        assert g.resilience_score() == original_score
        assert g.get_component("db").replicas == 1

    def test_add_replica_already_has_replicas(self):
        """add-replica sets replicas to max(current, 2). If already 3, stays 3."""
        db = _comp("db", ComponentType.DATABASE, replicas=3)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        new_score = ScoreDecomposer().what_if_fix(g, "db", "add-replica")
        # Still valid score, already had replicas so likely same
        assert 0.0 <= new_score <= 100.0

    def test_dependencies_copied_correctly(self):
        """Dependencies should be preserved in the simulated graph."""
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        # After fix, the dependency should still exist
        new_score = ScoreDecomposer().what_if_fix(g, "db", "add-replica")
        # The add-replica fix removes SPOF penalty -> higher score
        assert new_score > g.resilience_score()


# ---------------------------------------------------------------------------
# Test: explain()
# ---------------------------------------------------------------------------


class TestExplain:
    def test_returns_string(self):
        g = _graph([_comp("web")])
        text = ScoreDecomposer().explain(g)
        assert isinstance(text, str)
        assert "Resilience Score" in text

    def test_includes_grade(self):
        g = _graph([_comp("web", replicas=2)])
        text = ScoreDecomposer().explain(g)
        assert "Grade" in text

    def test_includes_penalties_when_present(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        text = ScoreDecomposer().explain(g)
        assert "PENALTIES" in text
        assert "Single Points of Failure" in text

    def test_includes_improvements_when_present(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        text = ScoreDecomposer().explain(g)
        assert "TOP IMPROVEMENTS" in text

    def test_empty_graph_explain(self):
        g = InfraGraph()
        text = ScoreDecomposer().explain(g)
        assert text == "No components loaded."


# ---------------------------------------------------------------------------
# Test: to_waterfall_data()
# ---------------------------------------------------------------------------


class TestWaterfallData:
    def test_structure_base_and_final(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        decomp = ScoreDecomposer().decompose(g)
        wf = ScoreDecomposer().to_waterfall_data(decomp)

        assert len(wf) >= 2
        assert wf[0]["name"] == "Base Score"
        assert wf[0]["value"] == 100.0
        assert wf[0]["running_total"] == 100.0
        assert wf[0]["category"] == "base"
        assert wf[-1]["name"] == "Final Score"
        assert wf[-1]["category"] == "total"

    def test_running_total_matches_final_score(self):
        db = _comp("db", ComponentType.DATABASE)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        decomp = ScoreDecomposer().decompose(g)
        wf = ScoreDecomposer().to_waterfall_data(decomp)

        assert abs(wf[-1]["running_total"] - decomp.total_score) < 0.1

    def test_penalty_entries_have_correct_category(self):
        db = _comp("db", ComponentType.DATABASE, cpu=95)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        decomp = ScoreDecomposer().decompose(g)
        wf = ScoreDecomposer().to_waterfall_data(decomp)

        penalty_entries = [w for w in wf if w["category"] == "penalty"]
        assert len(penalty_entries) > 0
        for p in penalty_entries:
            assert p["value"] < 0

    def test_running_total_decreases_with_penalties(self):
        db = _comp("db", ComponentType.DATABASE, cpu=95)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        decomp = ScoreDecomposer().decompose(g)
        wf = ScoreDecomposer().to_waterfall_data(decomp)

        # running_total should decrease from base
        for i in range(1, len(wf) - 1):
            if wf[i]["category"] == "penalty":
                assert wf[i]["running_total"] < wf[0]["running_total"]

    def test_no_penalties_only_base_and_final(self):
        g = _graph([_comp("web", replicas=2)])
        decomp = ScoreDecomposer().decompose(g)
        wf = ScoreDecomposer().to_waterfall_data(decomp)

        assert len(wf) == 2
        assert wf[0]["name"] == "Base Score"
        assert wf[1]["name"] == "Final Score"

    def test_bonus_factors_not_in_waterfall(self):
        """Bonus factors (points=0) should not appear in waterfall."""
        web = _comp("web", failover=True, replicas=2)
        g = _graph([web])

        decomp = ScoreDecomposer().decompose(g)
        wf = ScoreDecomposer().to_waterfall_data(decomp)

        categories = {w["category"] for w in wf}
        assert "bonus" not in categories

    def test_multiple_penalties_in_waterfall(self):
        """Both SPOF and utilization penalties should appear."""
        db = _comp("db", ComponentType.DATABASE, cpu=95)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        decomp = ScoreDecomposer().decompose(g)
        wf = ScoreDecomposer().to_waterfall_data(decomp)

        penalty_names = [w["name"] for w in wf if w["category"] == "penalty"]
        assert len(penalty_names) >= 2  # SPOF + Utilization


# ---------------------------------------------------------------------------
# Test: _build_breakdown_text (static helper)
# ---------------------------------------------------------------------------


class TestBuildBreakdownText:
    def test_basic_structure(self):
        text = ScoreDecomposer._build_breakdown_text(
            base_score=100.0,
            final_score=80.0,
            factors=[],
            improvements=[],
        )
        assert "Resilience Score: 80/100" in text
        assert "Starting from base score: 100" in text
        assert "Grade: B+" in text

    def test_penalties_section(self):
        factors = [
            ScoreFactor(
                name="SPOF", category="penalty", points=-10.0,
                description="3 SPOFs", remediation="Fix them",
            ),
        ]
        text = ScoreDecomposer._build_breakdown_text(100, 90, factors, [])
        assert "PENALTIES:" in text
        assert "SPOF: -10.0 points" in text
        assert "3 SPOFs" in text
        assert "Fix: Fix them" in text

    def test_bonuses_section(self):
        factors = [
            ScoreFactor(
                name="Failover Coverage", category="bonus", points=0,
                description="2/3 have failover",
            ),
            ScoreFactor(
                name="CB Info", category="neutral", points=0,
                description="1/2 have CB",
            ),
        ]
        text = ScoreDecomposer._build_breakdown_text(100, 100, factors, [])
        assert "POSITIVE FACTORS:" in text
        assert "Failover Coverage: 2/3 have failover" in text
        assert "CB Info: 1/2 have CB" in text

    def test_improvements_section(self):
        improvements = [
            ScoreImprovement(
                action="add-replica", component_id="db",
                estimated_improvement=8.0, effort="medium",
                description="Add replicas to db",
            ),
        ]
        text = ScoreDecomposer._build_breakdown_text(100, 92, [], improvements)
        assert "TOP IMPROVEMENTS:" in text
        assert "add-replica on db" in text
        assert "+8.0 points" in text
        assert "medium effort" in text

    def test_improvements_limited_to_5(self):
        improvements = [
            ScoreImprovement(
                action=f"fix-{i}", component_id=f"c{i}",
                estimated_improvement=float(10 - i), effort="low",
                description=f"Fix c{i}",
            )
            for i in range(8)
        ]
        text = ScoreDecomposer._build_breakdown_text(100, 50, [], improvements)
        # Only first 5 should appear
        assert "fix-0" in text
        assert "fix-4" in text
        assert "fix-5" not in text

    def test_no_penalties_no_penalties_section(self):
        text = ScoreDecomposer._build_breakdown_text(100, 100, [], [])
        assert "PENALTIES:" not in text

    def test_no_bonuses_no_positive_factors_section(self):
        factors = [
            ScoreFactor(
                name="SPOF", category="penalty", points=-5.0, description="d",
            ),
        ]
        text = ScoreDecomposer._build_breakdown_text(100, 95, factors, [])
        assert "POSITIVE FACTORS:" not in text

    def test_penalty_without_remediation(self):
        factors = [
            ScoreFactor(
                name="High Util", category="penalty", points=-8.0,
                description="overloaded", remediation=None,
            ),
        ]
        text = ScoreDecomposer._build_breakdown_text(100, 92, factors, [])
        assert "Fix:" not in text


# ---------------------------------------------------------------------------
# Test: Grade and percentile in decompose result
# ---------------------------------------------------------------------------


class TestGradeAndPercentile:
    def test_perfect_score_a_plus(self):
        g = _graph([_comp("web", replicas=3)])
        result = ScoreDecomposer().decompose(g)
        assert result.grade == "A+"
        assert result.percentile_estimate == 95.0

    def test_mid_range_grade(self):
        """Score around 70 should give B-."""
        # Create a graph with penalty ~30 points
        db = _comp("db", ComponentType.DATABASE)
        apps = [_comp(f"a{i}") for i in range(4)]
        deps = [(f"a{i}", "db") for i in range(4)]
        g = _graph([db] + apps, deps)

        result = ScoreDecomposer().decompose(g)
        # Score should be 100 - 20 = 80 (capped at 20)
        assert result.grade in ("B+", "B", "B-", "A-")

    def test_low_score_gets_f(self):
        """Heavily penalized graph should get F."""
        comps = []
        deps = []
        for i in range(6):
            db = _comp(f"db{i}", ComponentType.DATABASE, cpu=95)
            comps.append(db)
        for i in range(6):
            for j in range(6):
                if i != j:
                    deps.append((f"db{i}", f"db{j}"))
        g = _graph(comps, deps)

        result = ScoreDecomposer().decompose(g)
        assert result.grade in ("F", "D-", "D", "D+", "C-", "C")


# ---------------------------------------------------------------------------
# Test: to_dict with a full decompose result
# ---------------------------------------------------------------------------


class TestToDictIntegration:
    def test_full_decompose_to_dict(self):
        db = _comp("db", ComponentType.DATABASE, cpu=85)
        app = _comp("app")
        g = _graph([db, app], [("app", "db")])

        decomp = ScoreDecomposer().decompose(g)
        d = decomp.to_dict()

        # Verify all top-level keys
        for key in [
            "total_score", "max_possible_score", "base_score",
            "penalties_total", "bonuses_total", "grade",
            "percentile_estimate", "score_breakdown_text",
            "factors", "improvements",
        ]:
            assert key in d

        # factors and improvements should be lists of dicts
        assert isinstance(d["factors"], list)
        assert isinstance(d["improvements"], list)
        if d["factors"]:
            assert "name" in d["factors"][0]
            assert "category" in d["factors"][0]
            assert "points" in d["factors"][0]
            assert "description" in d["factors"][0]
            assert "affected_components" in d["factors"][0]
            assert "remediation" in d["factors"][0]
        if d["improvements"]:
            assert "action" in d["improvements"][0]
            assert "component_id" in d["improvements"][0]
            assert "estimated_improvement" in d["improvements"][0]
            assert "effort" in d["improvements"][0]
            assert "description" in d["improvements"][0]

    def test_to_dict_is_json_serializable(self):
        db = _comp("db", ComponentType.DATABASE, failover=True)
        app = _comp("app", autoscaling=True)
        cache = _comp("cache", ComponentType.CACHE, replicas=3)
        g = _graph(
            [db, app, cache],
            [("app", "db"), ("app", "cache")],
            cb_enabled=True,
        )

        decomp = ScoreDecomposer().decompose(g)
        json_str = json.dumps(decomp.to_dict())
        assert len(json_str) > 0
        # Round-trip
        parsed = json.loads(json_str)
        assert parsed["total_score"] == decomp.to_dict()["total_score"]
