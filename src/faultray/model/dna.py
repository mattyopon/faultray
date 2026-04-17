# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Infrastructure DNA Fingerprinting — compute and compare infrastructure fingerprints.

Uses only hashlib (stdlib) to produce a deterministic 256-bit fingerprint of an
infrastructure graph based on its topology, component characteristics, and
configuration.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph


@dataclass
class InfraDNA:
    """The fingerprint of an infrastructure graph."""

    fingerprint: str  # 64-char hex (SHA-256)
    topology_hash: str  # 16-char hex
    component_hash: str  # 16-char hex
    config_hash: str  # 16-char hex

    component_count: int
    dependency_count: int
    max_chain_depth: int
    redundancy_pattern: str  # "active-active", "active-standby", "single"
    architecture_type: str  # "monolith", "microservices", "serverless", "hybrid"


@dataclass
class SimilarityResult:
    """Result of comparing two infrastructure graphs."""

    similarity: float  # 0-1
    matching_components: int
    matching_topology: float
    architecture_match: bool


class DNAEngine:
    """Compute and compare Infrastructure DNA fingerprints."""

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------

    @staticmethod
    def compute(graph: InfraGraph) -> InfraDNA:
        """Compute a 256-bit fingerprint of an infrastructure graph.

        The fingerprint is built from three independent hashes:

        * **topology_hash** — edge structure (source/target pairs)
        * **component_hash** — component characteristics (type, replicas, failover)
        * **config_hash** — capacity and autoscaling configuration

        These are combined into a final SHA-256 ``fingerprint``.
        """
        # --- Topology hash (edge structure) ---
        edges = sorted(
            (e.source_id, e.target_id) for e in graph.all_dependency_edges()
        )
        topology_hash = hashlib.sha256(str(edges).encode()).hexdigest()[:16]

        # --- Component characteristics hash ---
        comps = sorted(
            f"{c.type.value}:{c.replicas}:{c.failover.enabled}"
            for c in graph.components.values()
        )
        component_hash = hashlib.sha256(str(comps).encode()).hexdigest()[:16]

        # --- Configuration hash ---
        configs = sorted(
            f"{c.id}:{c.capacity.max_connections}:{c.autoscaling.enabled}"
            for c in graph.components.values()
        )
        config_hash = hashlib.sha256(str(configs).encode()).hexdigest()[:16]

        # --- Combined fingerprint ---
        fingerprint = hashlib.sha256(
            f"{topology_hash}{component_hash}{config_hash}".encode()
        ).hexdigest()

        # --- Classify architecture ---
        architecture_type = DNAEngine._classify_architecture(graph)

        # --- Redundancy pattern ---
        redundancy_pattern = DNAEngine._classify_redundancy(graph)

        # --- Max chain depth ---
        critical_paths = graph.get_critical_paths()
        max_chain_depth = max(len(p) for p in critical_paths) if critical_paths else 0

        return InfraDNA(
            fingerprint=fingerprint,
            topology_hash=topology_hash,
            component_hash=component_hash,
            config_hash=config_hash,
            component_count=len(graph.components),
            dependency_count=len(graph.all_dependency_edges()),
            max_chain_depth=max_chain_depth,
            redundancy_pattern=redundancy_pattern,
            architecture_type=architecture_type,
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    @staticmethod
    def compare(graph1: InfraGraph, graph2: InfraGraph) -> SimilarityResult:
        """Compare two infrastructure graphs for architectural similarity.

        Similarity is computed as a weighted combination of:

        * component type overlap (40 %)
        * topology similarity (40 %)
        * architecture type match (20 %)
        """
        dna1 = DNAEngine.compute(graph1)
        dna2 = DNAEngine.compute(graph2)

        # --- Component type overlap ---
        types1 = _component_type_multiset(graph1)
        types2 = _component_type_multiset(graph2)
        all_types = set(types1.keys()) | set(types2.keys())
        if all_types:
            type_overlap = sum(
                min(types1.get(t, 0), types2.get(t, 0)) for t in all_types
            ) / max(
                sum(max(types1.get(t, 0), types2.get(t, 0)) for t in all_types), 1
            )
        else:
            type_overlap = 1.0

        matching_components = sum(
            min(types1.get(t, 0), types2.get(t, 0)) for t in all_types
        )

        # --- Topology similarity (Jaccard on edge type-pairs) ---
        edges1 = _edge_type_pairs(graph1)
        edges2 = _edge_type_pairs(graph2)
        all_edges = edges1 | edges2
        if all_edges:
            matching_topology = len(edges1 & edges2) / len(all_edges)
        else:
            matching_topology = 1.0

        # --- Architecture match ---
        architecture_match = dna1.architecture_type == dna2.architecture_type

        similarity = (
            0.4 * type_overlap
            + 0.4 * matching_topology
            + 0.2 * (1.0 if architecture_match else 0.0)
        )

        return SimilarityResult(
            similarity=round(similarity, 4),
            matching_components=matching_components,
            matching_topology=round(matching_topology, 4),
            architecture_match=architecture_match,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_architecture(graph: InfraGraph) -> str:
        """Classify the architecture type of a graph."""
        types = [c.type.value for c in graph.components.values()]
        if len(graph.components) <= 3:
            return "monolith"
        if "queue" in types or "external_api" in types:
            return "microservices"
        if all(c.type.value in ("app_server", "storage") for c in graph.components.values()):
            return "serverless"
        return "hybrid"

    @staticmethod
    def _classify_redundancy(graph: InfraGraph) -> str:
        """Classify the overall redundancy pattern of a graph."""
        if not graph.components:
            return "single"

        has_multi_replica_failover = False
        has_any_redundancy = False

        for c in graph.components.values():
            if c.replicas >= 2 and c.failover.enabled:
                has_multi_replica_failover = True
                has_any_redundancy = True
            elif c.replicas >= 2 or c.failover.enabled:
                has_any_redundancy = True

        if has_multi_replica_failover:
            return "active-active"
        if has_any_redundancy:
            return "active-standby"
        return "single"


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _component_type_multiset(graph: InfraGraph) -> dict[str, int]:
    """Return a multiset (type -> count) for the graph's components."""
    counts: dict[str, int] = {}
    for c in graph.components.values():
        counts[c.type.value] = counts.get(c.type.value, 0) + 1
    return counts


def _edge_type_pairs(graph: InfraGraph) -> set[tuple[str, str]]:
    """Return a set of (source_type, target_type) pairs for topology comparison."""
    pairs: set[tuple[str, str]] = set()
    for edge in graph.all_dependency_edges():
        src = graph.get_component(edge.source_id)
        tgt = graph.get_component(edge.target_id)
        if src and tgt:
            pairs.add((src.type.value, tgt.type.value))
    return pairs
