"""Tests for Infrastructure DNA Fingerprinting."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.dna import DNAEngine, InfraDNA, SimilarityResult
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(
    component_specs: list[tuple[str, str]],
    edges: list[tuple[str, str]] | None = None,
    failover: bool = False,
    autoscaling: bool = False,
    replicas: int = 1,
) -> InfraGraph:
    """Build a graph from (id, type_str) pairs and optional edge list."""
    g = InfraGraph()
    for cid, ctype in component_specs:
        g.add_component(
            Component(
                id=cid,
                name=cid,
                type=ComponentType(ctype),
                replicas=replicas,
                failover=FailoverConfig(enabled=failover),
                autoscaling=AutoScalingConfig(enabled=autoscaling),
            )
        )
    for src, tgt in (edges or []):
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


# ---------------------------------------------------------------------------
# DNAEngine.compute tests
# ---------------------------------------------------------------------------


class TestDNACompute:
    def test_fingerprint_is_64_hex_chars(self):
        g = _make_graph([("lb", "load_balancer"), ("app", "app_server")])
        dna = DNAEngine.compute(g)
        assert len(dna.fingerprint) == 64
        assert all(c in "0123456789abcdef" for c in dna.fingerprint)

    def test_topology_hash_16_chars(self):
        g = _make_graph(
            [("lb", "load_balancer"), ("app", "app_server")],
            edges=[("lb", "app")],
        )
        dna = DNAEngine.compute(g)
        assert len(dna.topology_hash) == 16

    def test_deterministic_fingerprint(self):
        specs = [("lb", "load_balancer"), ("app", "app_server"), ("db", "database")]
        edges = [("lb", "app"), ("app", "db")]
        g1 = _make_graph(specs, edges)
        g2 = _make_graph(specs, edges)
        assert DNAEngine.compute(g1).fingerprint == DNAEngine.compute(g2).fingerprint

    def test_different_topology_different_fingerprint(self):
        specs = [("lb", "load_balancer"), ("app", "app_server"), ("db", "database")]
        g1 = _make_graph(specs, edges=[("lb", "app"), ("app", "db")])
        g2 = _make_graph(specs, edges=[("lb", "db")])
        assert DNAEngine.compute(g1).fingerprint != DNAEngine.compute(g2).fingerprint

    def test_component_count_and_dependency_count(self):
        g = _make_graph(
            [("lb", "load_balancer"), ("app", "app_server"), ("db", "database")],
            edges=[("lb", "app"), ("app", "db")],
        )
        dna = DNAEngine.compute(g)
        assert dna.component_count == 3
        assert dna.dependency_count == 2

    def test_max_chain_depth(self):
        g = _make_graph(
            [("a", "app_server"), ("b", "app_server"), ("c", "database")],
            edges=[("a", "b"), ("b", "c")],
        )
        dna = DNAEngine.compute(g)
        assert dna.max_chain_depth == 3  # a -> b -> c

    def test_architecture_type_monolith(self):
        g = _make_graph([("app", "app_server"), ("db", "database")])
        dna = DNAEngine.compute(g)
        assert dna.architecture_type == "monolith"

    def test_architecture_type_microservices(self):
        g = _make_graph([
            ("lb", "load_balancer"),
            ("app1", "app_server"),
            ("app2", "app_server"),
            ("queue", "queue"),
        ])
        dna = DNAEngine.compute(g)
        assert dna.architecture_type == "microservices"

    def test_architecture_type_hybrid(self):
        g = _make_graph([
            ("lb", "load_balancer"),
            ("app1", "app_server"),
            ("app2", "app_server"),
            ("db", "database"),
        ])
        dna = DNAEngine.compute(g)
        assert dna.architecture_type == "hybrid"

    def test_architecture_type_serverless(self):
        g = _make_graph([
            ("fn1", "app_server"),
            ("fn2", "app_server"),
            ("fn3", "app_server"),
            ("s3", "storage"),
        ])
        dna = DNAEngine.compute(g)
        assert dna.architecture_type == "serverless"


# ---------------------------------------------------------------------------
# Redundancy classification tests
# ---------------------------------------------------------------------------


class TestRedundancyClassification:
    def test_single_no_redundancy(self):
        g = _make_graph([("app", "app_server")])
        dna = DNAEngine.compute(g)
        assert dna.redundancy_pattern == "single"

    def test_active_standby(self):
        g = _make_graph([("app", "app_server")], replicas=2)
        dna = DNAEngine.compute(g)
        assert dna.redundancy_pattern == "active-standby"

    def test_active_active(self):
        g = _make_graph([("app", "app_server")], replicas=2, failover=True)
        dna = DNAEngine.compute(g)
        assert dna.redundancy_pattern == "active-active"

    def test_empty_graph(self):
        g = InfraGraph()
        dna = DNAEngine.compute(g)
        assert dna.redundancy_pattern == "single"
        assert dna.component_count == 0


# ---------------------------------------------------------------------------
# DNAEngine.compare tests
# ---------------------------------------------------------------------------


class TestDNACompare:
    def test_identical_graphs_similarity_1(self):
        specs = [("lb", "load_balancer"), ("app", "app_server"), ("db", "database")]
        edges = [("lb", "app"), ("app", "db")]
        g1 = _make_graph(specs, edges)
        g2 = _make_graph(specs, edges)
        result = DNAEngine.compare(g1, g2)
        assert result.similarity == pytest.approx(1.0)
        assert result.architecture_match is True

    def test_completely_different_graphs(self):
        g1 = _make_graph([("app", "app_server")])
        g2 = _make_graph([
            ("lb", "load_balancer"),
            ("q", "queue"),
            ("db", "database"),
            ("ext", "external_api"),
        ])
        result = DNAEngine.compare(g1, g2)
        assert result.similarity < 0.5

    def test_partial_overlap(self):
        g1 = _make_graph(
            [("lb", "load_balancer"), ("app", "app_server"), ("db", "database")],
            edges=[("lb", "app"), ("app", "db")],
        )
        g2 = _make_graph(
            [("lb", "load_balancer"), ("app", "app_server"), ("cache", "cache")],
            edges=[("lb", "app"), ("app", "cache")],
        )
        result = DNAEngine.compare(g1, g2)
        assert 0.0 < result.similarity < 1.0
        assert result.matching_components >= 2

    def test_same_types_different_topology(self):
        specs = [("lb", "load_balancer"), ("app", "app_server"), ("db", "database")]
        g1 = _make_graph(specs, edges=[("lb", "app"), ("app", "db")])
        g2 = _make_graph(specs, edges=[("lb", "db")])
        result = DNAEngine.compare(g1, g2)
        assert result.matching_topology < 1.0

    def test_empty_graphs(self):
        g1 = InfraGraph()
        g2 = InfraGraph()
        result = DNAEngine.compare(g1, g2)
        assert result.similarity == pytest.approx(1.0)
        assert result.architecture_match is True
