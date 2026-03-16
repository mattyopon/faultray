"""Comprehensive tests for ImpactAnalyzer and the Dependency Impact Matrix."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.impact_matrix import (
    ComponentImpactProfile,
    ImpactAnalyzer,
    ImpactCell,
    ImpactLevel,
    ImpactMatrix,
    _score_to_level,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _comp(cid: str, name: str, ctype: ComponentType = ComponentType.APP_SERVER, replicas: int = 1) -> Component:
    return Component(id=cid, name=name, type=ctype, replicas=replicas)


def _linear_graph() -> InfraGraph:
    """A -> B -> C  (A depends on B, B depends on C).

    Failure of C cascades to B then A.
    """
    g = InfraGraph()
    g.add_component(_comp("a", "A"))
    g.add_component(_comp("b", "B"))
    g.add_component(_comp("c", "C"))
    g.add_dependency(Dependency(source_id="a", target_id="b"))
    g.add_dependency(Dependency(source_id="b", target_id="c"))
    return g


def _diamond_graph() -> InfraGraph:
    """Diamond topology:

       A
      / \\
     B   C
      \\ /
       D

    A depends on B and C; B and C both depend on D.
    """
    g = InfraGraph()
    g.add_component(_comp("a", "A"))
    g.add_component(_comp("b", "B"))
    g.add_component(_comp("c", "C"))
    g.add_component(_comp("d", "D"))
    g.add_dependency(Dependency(source_id="a", target_id="b"))
    g.add_dependency(Dependency(source_id="a", target_id="c"))
    g.add_dependency(Dependency(source_id="b", target_id="d"))
    g.add_dependency(Dependency(source_id="c", target_id="d"))
    return g


def _star_graph() -> InfraGraph:
    """Star topology: B, C, D all depend on central A.

    Failure of A affects B, C, D.
    """
    g = InfraGraph()
    g.add_component(_comp("a", "A"))
    g.add_component(_comp("b", "B"))
    g.add_component(_comp("c", "C"))
    g.add_component(_comp("d", "D"))
    g.add_dependency(Dependency(source_id="b", target_id="a"))
    g.add_dependency(Dependency(source_id="c", target_id="a"))
    g.add_dependency(Dependency(source_id="d", target_id="a"))
    return g


# ===================================================================
# ImpactLevel classification
# ===================================================================

class TestImpactLevelClassification:
    """Tests for _score_to_level and ImpactLevel enum."""

    def test_critical_at_100(self):
        assert _score_to_level(100) == ImpactLevel.CRITICAL

    def test_critical_at_80(self):
        assert _score_to_level(80) == ImpactLevel.CRITICAL

    def test_high_at_79(self):
        assert _score_to_level(79) == ImpactLevel.HIGH

    def test_high_at_60(self):
        assert _score_to_level(60) == ImpactLevel.HIGH

    def test_medium_at_59(self):
        assert _score_to_level(59) == ImpactLevel.MEDIUM

    def test_medium_at_40(self):
        assert _score_to_level(40) == ImpactLevel.MEDIUM

    def test_low_at_39(self):
        assert _score_to_level(39) == ImpactLevel.LOW

    def test_low_at_20(self):
        assert _score_to_level(20) == ImpactLevel.LOW

    def test_none_at_19(self):
        assert _score_to_level(19) == ImpactLevel.NONE

    def test_none_at_zero(self):
        assert _score_to_level(0) == ImpactLevel.NONE

    def test_impact_level_values(self):
        assert ImpactLevel.NONE.value == "none"
        assert ImpactLevel.LOW.value == "low"
        assert ImpactLevel.MEDIUM.value == "medium"
        assert ImpactLevel.HIGH.value == "high"
        assert ImpactLevel.CRITICAL.value == "critical"


# ===================================================================
# Empty graph
# ===================================================================

class TestEmptyGraph:
    def test_build_matrix_empty(self):
        g = InfraGraph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.matrix_size == 0
        assert matrix.cells == []
        assert matrix.component_profiles == []
        assert matrix.most_critical_component == ""
        assert matrix.most_vulnerable_component == ""
        assert matrix.avg_blast_radius == 0.0
        assert matrix.max_blast_radius == 0

    def test_get_impact_empty(self):
        g = InfraGraph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_impact("x", "y") is None

    def test_get_blast_radius_empty(self):
        g = InfraGraph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_blast_radius("x") == []

    def test_get_critical_path_empty(self):
        g = InfraGraph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_critical_path("x", "y") == []

    def test_find_most_vulnerable_empty(self):
        g = InfraGraph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.find_most_vulnerable() == ""

    def test_format_matrix_empty(self):
        g = InfraGraph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        text = analyzer.format_matrix(matrix)
        assert "Empty matrix" in text


# ===================================================================
# Single component
# ===================================================================

class TestSingleComponent:
    def test_build_matrix_single(self):
        g = InfraGraph()
        g.add_component(_comp("only", "Only"))
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.matrix_size == 1
        assert matrix.cells == []
        assert len(matrix.component_profiles) == 1
        assert matrix.component_profiles[0].blast_radius == 0

    def test_get_impact_self(self):
        g = InfraGraph()
        g.add_component(_comp("only", "Only"))
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_impact("only", "only") is None

    def test_blast_radius_single(self):
        g = InfraGraph()
        g.add_component(_comp("only", "Only"))
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_blast_radius("only") == []


# ===================================================================
# Linear chain: A -> B -> C
# ===================================================================

class TestLinearChain:
    """A depends on B, B depends on C. Failure propagates upstream."""

    def test_blast_radius_c(self):
        """C failure affects B and A."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        br = analyzer.get_blast_radius("c")
        assert set(br) == {"a", "b"}

    def test_blast_radius_b(self):
        """B failure affects only A."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        br = analyzer.get_blast_radius("b")
        assert set(br) == {"a"}

    def test_blast_radius_a(self):
        """A failure affects nobody (leaf)."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_blast_radius("a") == []

    def test_get_impact_direct(self):
        """C -> B is direct (1 hop)."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        cell = analyzer.get_impact("c", "b")
        assert cell is not None
        assert cell.is_direct is True
        assert cell.path_length == 1
        assert cell.impact_score == pytest.approx(100.0)
        assert cell.impact_level == ImpactLevel.CRITICAL

    def test_get_impact_transitive(self):
        """C -> A is transitive (2 hops)."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        cell = analyzer.get_impact("c", "a")
        assert cell is not None
        assert cell.is_direct is False
        assert cell.path_length == 2
        assert cell.impact_score == pytest.approx(50.0)
        assert cell.impact_level == ImpactLevel.MEDIUM

    def test_get_impact_no_path(self):
        """A -> C has no impact (A is upstream of C)."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_impact("a", "c") is None

    def test_critical_path_c_to_a(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        path = analyzer.get_critical_path("c", "a")
        assert path == ["c", "b", "a"]

    def test_critical_path_c_to_b(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        path = analyzer.get_critical_path("c", "b")
        assert path == ["c", "b"]

    def test_critical_path_same_node(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        path = analyzer.get_critical_path("b", "b")
        assert path == ["b"]

    def test_most_critical_is_c(self):
        """C has the largest blast radius (2)."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.most_critical_component == "c"

    def test_most_vulnerable(self):
        """A appears in blast radii of both B and C -> most vulnerable."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.find_most_vulnerable() == "a"


# ===================================================================
# Diamond topology
# ===================================================================

class TestDiamondTopology:
    """A depends on B,C; B,C depend on D."""

    def test_blast_radius_d(self):
        """D failure affects B, C, and A."""
        g = _diamond_graph()
        analyzer = ImpactAnalyzer(g)
        br = analyzer.get_blast_radius("d")
        assert set(br) == {"a", "b", "c"}

    def test_blast_radius_b(self):
        """B failure only affects A."""
        g = _diamond_graph()
        analyzer = ImpactAnalyzer(g)
        br = analyzer.get_blast_radius("b")
        assert set(br) == {"a"}

    def test_most_critical_is_d(self):
        g = _diamond_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.most_critical_component == "d"

    def test_most_vulnerable_is_a(self):
        """A is affected by D, B, and C failures."""
        g = _diamond_graph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.find_most_vulnerable() == "a"

    def test_path_d_to_a_via_b_or_c(self):
        """Shortest path from D to A is 2 hops (via B or C)."""
        g = _diamond_graph()
        analyzer = ImpactAnalyzer(g)
        path = analyzer.get_critical_path("d", "a")
        assert len(path) == 3
        assert path[0] == "d"
        assert path[-1] == "a"
        assert path[1] in ("b", "c")

    def test_matrix_size(self):
        g = _diamond_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.matrix_size == 4


# ===================================================================
# Star topology
# ===================================================================

class TestStarTopology:
    """B,C,D all depend on central A."""

    def test_blast_radius_a(self):
        g = _star_graph()
        analyzer = ImpactAnalyzer(g)
        br = analyzer.get_blast_radius("a")
        assert set(br) == {"b", "c", "d"}

    def test_blast_radius_leaf(self):
        g = _star_graph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_blast_radius("b") == []

    def test_most_critical_is_a(self):
        g = _star_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.most_critical_component == "a"

    def test_max_blast_radius(self):
        g = _star_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.max_blast_radius == 3

    def test_avg_blast_radius(self):
        """Only A has radius 3; B,C,D have 0. Avg = 3/4 = 0.75."""
        g = _star_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.avg_blast_radius == pytest.approx(0.75)


# ===================================================================
# Isolated components (no dependencies)
# ===================================================================

class TestIsolatedComponents:
    def test_no_impact(self):
        g = InfraGraph()
        g.add_component(_comp("x", "X"))
        g.add_component(_comp("y", "Y"))
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_impact("x", "y") is None
        assert analyzer.get_impact("y", "x") is None

    def test_all_blast_radii_zero(self):
        g = InfraGraph()
        g.add_component(_comp("x", "X"))
        g.add_component(_comp("y", "Y"))
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.max_blast_radius == 0
        assert matrix.avg_blast_radius == 0.0

    def test_all_profiles_zero(self):
        g = InfraGraph()
        g.add_component(_comp("x", "X"))
        g.add_component(_comp("y", "Y"))
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        for p in matrix.component_profiles:
            assert p.blast_radius == 0
            assert p.direct_dependents == 0
            assert p.transitive_dependents == 0

    def test_matrix_size_two_isolated(self):
        g = InfraGraph()
        g.add_component(_comp("x", "X"))
        g.add_component(_comp("y", "Y"))
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        assert matrix.matrix_size == 2
        assert matrix.cells == []


# ===================================================================
# build_matrix aggregate statistics
# ===================================================================

class TestBuildMatrixStats:
    def test_linear_matrix_cells_count(self):
        """In a 3-node linear chain, only C->B, C->A, B->A produce cells."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        # C impacts B (direct) and A (transitive) = 2 cells
        # B impacts A (direct) = 1 cell
        # A impacts nobody = 0 cells
        assert len(matrix.cells) == 3

    def test_profiles_have_correct_ranks(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        profiles = analyzer.rank_by_criticality()
        rank_map = {p.component_id: p.criticality_rank for p in profiles}
        # C has blast radius 2 (rank 1), B has 1 (rank 2), A has 0 (rank 3)
        assert rank_map["c"] == 1
        assert rank_map["b"] == 2
        assert rank_map["a"] == 3

    def test_component_profile_fields(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        profiles = analyzer.rank_by_criticality()
        c_prof = next(p for p in profiles if p.component_id == "c")
        assert c_prof.component_name == "C"
        assert c_prof.blast_radius == 2
        assert c_prof.direct_dependents == 1  # B
        assert c_prof.transitive_dependents == 1  # A
        assert c_prof.max_impact_score == pytest.approx(100.0)
        assert c_prof.avg_impact_score == pytest.approx(75.0)  # (100 + 50) / 2


# ===================================================================
# get_impact edge cases
# ===================================================================

class TestGetImpact:
    def test_returns_none_for_same_id(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_impact("a", "a") is None

    def test_returns_none_no_connection(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        # A is upstream of everything, cannot impact C
        assert analyzer.get_impact("a", "c") is None

    def test_description_direct(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        cell = analyzer.get_impact("c", "b")
        assert cell is not None
        assert "Direct dependency" in cell.description

    def test_description_transitive(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        cell = analyzer.get_impact("c", "a")
        assert cell is not None
        assert "Transitive impact" in cell.description
        assert "2 hops" in cell.description

    def test_impact_score_3_hops(self):
        """Score for 3 hops = 100 / 3 ~ 33.33 -> LOW (20-39 range)."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        g.add_component(_comp("d", "D"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        g.add_dependency(Dependency(source_id="c", target_id="d"))
        analyzer = ImpactAnalyzer(g)
        cell = analyzer.get_impact("d", "a")
        assert cell is not None
        assert cell.path_length == 3
        assert cell.impact_score == pytest.approx(100.0 / 3)
        assert cell.impact_level == ImpactLevel.LOW


# ===================================================================
# format_matrix output
# ===================================================================

class TestFormatMatrix:
    def test_format_contains_component_ids(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        text = analyzer.format_matrix(matrix)
        for cid in ("a", "b", "c"):
            assert cid in text

    def test_format_contains_stats(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        text = analyzer.format_matrix(matrix)
        assert "Most Critical" in text
        assert "Most Vulnerable" in text
        assert "Avg Blast Radius" in text
        assert "Max Blast Radius" in text

    def test_format_diagonal_dashes(self):
        """Diagonal cells (self-impact) should show '---'."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        text = analyzer.format_matrix(matrix)
        assert "---" in text

    def test_format_shows_critical_label(self):
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        matrix = analyzer.build_matrix()
        text = analyzer.format_matrix(matrix)
        assert "CRITICAL" in text


# ===================================================================
# Complex / mixed topologies
# ===================================================================

class TestComplexTopology:
    def test_multiple_paths_shortest_used(self):
        """When multiple paths exist, BFS returns the shortest."""
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        g.add_component(_comp("c", "C"))
        # a -> b -> c (A depends on B depends on C)
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        # Also a -> c (A also depends on C directly)
        g.add_dependency(Dependency(source_id="a", target_id="c"))
        analyzer = ImpactAnalyzer(g)
        # c -> a: shortest should be 1 hop (direct), not 2 (via b)
        cell = analyzer.get_impact("c", "a")
        assert cell is not None
        assert cell.path_length == 1
        assert cell.is_direct is True

    def test_long_chain_score(self):
        """5-hop chain: score = 100 / 5 = 20 -> LOW."""
        g = InfraGraph()
        nodes = ["n0", "n1", "n2", "n3", "n4", "n5"]
        for n in nodes:
            g.add_component(_comp(n, n.upper()))
        for i in range(len(nodes) - 1):
            g.add_dependency(Dependency(source_id=nodes[i], target_id=nodes[i + 1]))
        analyzer = ImpactAnalyzer(g)
        cell = analyzer.get_impact("n5", "n0")
        assert cell is not None
        assert cell.path_length == 5
        assert cell.impact_score == pytest.approx(20.0)
        assert cell.impact_level == ImpactLevel.LOW

    def test_component_types_preserved(self):
        """Component types from the graph are correctly reflected."""
        g = InfraGraph()
        g.add_component(_comp("lb", "LoadBalancer", ComponentType.LOAD_BALANCER))
        g.add_component(_comp("db", "Database", ComponentType.DATABASE))
        g.add_dependency(Dependency(source_id="lb", target_id="db"))
        analyzer = ImpactAnalyzer(g)
        profiles = analyzer.rank_by_criticality()
        db_prof = next(p for p in profiles if p.component_id == "db")
        assert db_prof.component_name == "Database"
        assert db_prof.blast_radius == 1

    def test_rank_stability(self):
        """Calling rank_by_criticality twice gives same result."""
        g = _diamond_graph()
        analyzer = ImpactAnalyzer(g)
        r1 = [(p.component_id, p.criticality_rank) for p in analyzer.rank_by_criticality()]
        r2 = [(p.component_id, p.criticality_rank) for p in analyzer.rank_by_criticality()]
        assert r1 == r2

    def test_blast_radius_returns_sorted(self):
        g = _star_graph()
        analyzer = ImpactAnalyzer(g)
        br = analyzer.get_blast_radius("a")
        assert br == sorted(br)

    def test_critical_path_source_exists_target_missing(self):
        """get_critical_path returns [] when source exists but target does not."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_critical_path("a", "nonexistent") == []

    def test_get_impact_source_missing(self):
        """get_impact returns None when source component does not exist."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_impact("nonexistent", "a") is None

    def test_get_impact_target_missing(self):
        """get_impact returns None when target component does not exist."""
        g = _linear_graph()
        analyzer = ImpactAnalyzer(g)
        assert analyzer.get_impact("a", "nonexistent") is None
