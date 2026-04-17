# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Chaos Genome - Infrastructure Resilience DNA Fingerprinting.

Every infrastructure topology has a unique 'resilience genome' - a multi-dimensional
fingerprint that captures its structural properties, failure characteristics, and
evolutionary trajectory. Like DNA for infrastructure.

The genome enables:
- Benchmarking against industry peers (anonymized)
- Tracking resilience evolution over time
- Identifying 'genetic' weaknesses inherited from architecture decisions
- Predicting failure patterns based on structural similarity to known-bad patterns
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

import networkx as nx

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Industry benchmark reference data (normalized 0-1 trait values)
# ---------------------------------------------------------------------------

INDUSTRY_BENCHMARKS: dict[str, dict[str, float]] = {
    "fintech": {
        "graph_density": 0.45,
        "avg_path_length": 0.50,
        "max_depth": 0.55,
        "clustering_coefficient": 0.40,
        "component_diversity": 0.65,
        "avg_replicas": 0.85,
        "min_replicas": 0.80,
        "failover_coverage": 0.90,
        "multi_az_coverage": 0.85,
        "provider_diversity": 0.40,
        "type_diversity": 0.60,
        "version_spread": 0.35,
        "circuit_breaker_coverage": 0.85,
        "blast_radius_avg": 0.30,
        "isolation_score": 0.80,
        "autoscaling_coverage": 0.80,
        "avg_recovery_time": 0.75,
        "health_check_coverage": 0.90,
    },
    "ecommerce": {
        "graph_density": 0.40,
        "avg_path_length": 0.45,
        "max_depth": 0.50,
        "clustering_coefficient": 0.35,
        "component_diversity": 0.70,
        "avg_replicas": 0.70,
        "min_replicas": 0.60,
        "failover_coverage": 0.75,
        "multi_az_coverage": 0.70,
        "provider_diversity": 0.35,
        "type_diversity": 0.65,
        "version_spread": 0.40,
        "circuit_breaker_coverage": 0.70,
        "blast_radius_avg": 0.35,
        "isolation_score": 0.65,
        "autoscaling_coverage": 0.75,
        "avg_recovery_time": 0.65,
        "health_check_coverage": 0.80,
    },
    "healthcare": {
        "graph_density": 0.35,
        "avg_path_length": 0.55,
        "max_depth": 0.50,
        "clustering_coefficient": 0.30,
        "component_diversity": 0.55,
        "avg_replicas": 0.90,
        "min_replicas": 0.85,
        "failover_coverage": 0.95,
        "multi_az_coverage": 0.90,
        "provider_diversity": 0.30,
        "type_diversity": 0.50,
        "version_spread": 0.25,
        "circuit_breaker_coverage": 0.80,
        "blast_radius_avg": 0.25,
        "isolation_score": 0.85,
        "autoscaling_coverage": 0.70,
        "avg_recovery_time": 0.80,
        "health_check_coverage": 0.95,
    },
    "saas": {
        "graph_density": 0.42,
        "avg_path_length": 0.48,
        "max_depth": 0.52,
        "clustering_coefficient": 0.38,
        "component_diversity": 0.68,
        "avg_replicas": 0.75,
        "min_replicas": 0.65,
        "failover_coverage": 0.78,
        "multi_az_coverage": 0.72,
        "provider_diversity": 0.45,
        "type_diversity": 0.70,
        "version_spread": 0.50,
        "circuit_breaker_coverage": 0.72,
        "blast_radius_avg": 0.35,
        "isolation_score": 0.70,
        "autoscaling_coverage": 0.80,
        "avg_recovery_time": 0.68,
        "health_check_coverage": 0.82,
    },
    "media": {
        "graph_density": 0.38,
        "avg_path_length": 0.42,
        "max_depth": 0.45,
        "clustering_coefficient": 0.32,
        "component_diversity": 0.60,
        "avg_replicas": 0.60,
        "min_replicas": 0.50,
        "failover_coverage": 0.60,
        "multi_az_coverage": 0.55,
        "provider_diversity": 0.50,
        "type_diversity": 0.65,
        "version_spread": 0.45,
        "circuit_breaker_coverage": 0.55,
        "blast_radius_avg": 0.40,
        "isolation_score": 0.55,
        "autoscaling_coverage": 0.70,
        "avg_recovery_time": 0.55,
        "health_check_coverage": 0.65,
    },
    "gaming": {
        "graph_density": 0.40,
        "avg_path_length": 0.40,
        "max_depth": 0.48,
        "clustering_coefficient": 0.35,
        "component_diversity": 0.62,
        "avg_replicas": 0.65,
        "min_replicas": 0.55,
        "failover_coverage": 0.65,
        "multi_az_coverage": 0.60,
        "provider_diversity": 0.35,
        "type_diversity": 0.60,
        "version_spread": 0.40,
        "circuit_breaker_coverage": 0.60,
        "blast_radius_avg": 0.38,
        "isolation_score": 0.58,
        "autoscaling_coverage": 0.85,
        "avg_recovery_time": 0.60,
        "health_check_coverage": 0.70,
    },
}

# Known weakness gene patterns
_WEAKNESS_CATALOG: list[dict] = [
    {
        "name": "single_database_gene",
        "check": "single_db",
        "severity": "critical",
        "description": "Single database instance with no replicas or failover - a classic SPOF inherited from monolithic designs.",
        "remediation": "Add read replicas, enable failover, or adopt a multi-primary architecture.",
        "prevalence": 0.35,
    },
    {
        "name": "no_circuit_breaker_gene",
        "check": "no_cb",
        "severity": "high",
        "description": "Dependencies lack circuit breakers, allowing cascading failures to propagate unchecked.",
        "remediation": "Enable circuit breakers on all 'requires' dependency edges.",
        "prevalence": 0.45,
    },
    {
        "name": "single_load_balancer_gene",
        "check": "single_lb",
        "severity": "high",
        "description": "Single load balancer with no redundancy - the front door is a single point of failure.",
        "remediation": "Deploy redundant load balancers or use a managed LB service with built-in HA.",
        "prevalence": 0.30,
    },
    {
        "name": "no_autoscaling_gene",
        "check": "no_autoscale",
        "severity": "medium",
        "description": "Components lack autoscaling, making the infrastructure brittle under load spikes.",
        "remediation": "Enable HPA/KEDA autoscaling for stateless components.",
        "prevalence": 0.40,
    },
    {
        "name": "deep_dependency_chain_gene",
        "check": "deep_chain",
        "severity": "high",
        "description": "Dependency chains exceed 5 hops, amplifying latency and failure probability.",
        "remediation": "Flatten the architecture by reducing intermediary services or introducing caching layers.",
        "prevalence": 0.25,
    },
    {
        "name": "no_health_check_gene",
        "check": "no_health",
        "severity": "medium",
        "description": "Components without health checks cannot be auto-recovered or removed from rotation.",
        "remediation": "Configure health check endpoints and enable liveness/readiness probes.",
        "prevalence": 0.30,
    },
    {
        "name": "single_az_gene",
        "check": "single_az",
        "severity": "high",
        "description": "Infrastructure concentrated in a single availability zone - vulnerable to zone-level outages.",
        "remediation": "Distribute components across multiple availability zones.",
        "prevalence": 0.35,
    },
    {
        "name": "no_failover_gene",
        "check": "no_failover",
        "severity": "high",
        "description": "Critical components lack failover configuration, increasing recovery time.",
        "remediation": "Enable failover for databases, caches, and other stateful components.",
        "prevalence": 0.40,
    },
]

# Failure affinity patterns - maps genome characteristics to failure types
_FAILURE_AFFINITY_PATTERNS: list[dict] = [
    {
        "failure_type": "cascade_failure",
        "contributing_traits": ["blast_radius_avg", "circuit_breaker_coverage", "isolation_score"],
        "trait_weights": [0.4, -0.35, -0.25],
        "contributing_genes": ["no_circuit_breaker_gene", "deep_dependency_chain_gene"],
        "explanation": "High blast radius and low circuit breaker coverage make cascading failures likely.",
    },
    {
        "failure_type": "capacity_exhaustion",
        "contributing_traits": ["autoscaling_coverage", "avg_replicas", "min_replicas"],
        "trait_weights": [-0.4, -0.3, -0.3],
        "contributing_genes": ["no_autoscaling_gene"],
        "explanation": "Lack of autoscaling and low replica counts leave no headroom for traffic spikes.",
    },
    {
        "failure_type": "single_point_of_failure",
        "contributing_traits": ["min_replicas", "failover_coverage", "isolation_score"],
        "trait_weights": [-0.4, -0.35, -0.25],
        "contributing_genes": ["single_database_gene", "single_load_balancer_gene", "no_failover_gene"],
        "explanation": "Components with single replicas and no failover are classical SPOFs.",
    },
    {
        "failure_type": "zone_outage",
        "contributing_traits": ["multi_az_coverage", "provider_diversity", "failover_coverage"],
        "trait_weights": [-0.5, -0.25, -0.25],
        "contributing_genes": ["single_az_gene"],
        "explanation": "Concentration in a single AZ makes the entire stack vulnerable to zone-level outages.",
    },
    {
        "failure_type": "slow_recovery",
        "contributing_traits": ["avg_recovery_time", "health_check_coverage", "autoscaling_coverage"],
        "trait_weights": [-0.4, -0.3, -0.3],
        "contributing_genes": ["no_health_check_gene", "no_autoscaling_gene", "no_failover_gene"],
        "explanation": "Missing health checks and auto-recovery mechanisms prolong incident recovery.",
    },
    {
        "failure_type": "latency_degradation",
        "contributing_traits": ["avg_path_length", "max_depth", "clustering_coefficient"],
        "trait_weights": [0.4, 0.35, -0.25],
        "contributing_genes": ["deep_dependency_chain_gene"],
        "explanation": "Deep dependency chains and long average paths amplify latency under load.",
    },
]


# ---------------------------------------------------------------------------
# Grading thresholds
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (95.0, "A+"),
    (90.0, "A"),
    (85.0, "A-"),
    (80.0, "B+"),
    (75.0, "B"),
    (70.0, "B-"),
    (65.0, "C+"),
    (60.0, "C"),
    (55.0, "C-"),
    (45.0, "D"),
    (0.0, "F"),
]


def _score_to_grade(score: float) -> str:
    """Convert a 0-100 score to a letter grade."""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


TRAIT_CATEGORIES = ("structure", "redundancy", "diversity", "isolation", "recovery")


@dataclass
class GenomeTrait:
    """A single measurable trait of the infrastructure."""

    name: str
    value: float  # normalized 0-1
    category: str  # one of TRAIT_CATEGORIES
    percentile: float | None = None  # vs industry benchmark

    def __post_init__(self) -> None:
        if self.category not in TRAIT_CATEGORIES:
            raise ValueError(
                f"Invalid trait category '{self.category}'. "
                f"Must be one of {TRAIT_CATEGORIES}"
            )
        self.value = max(0.0, min(1.0, self.value))


@dataclass
class WeaknessGene:
    """An architectural anti-pattern ('gene') that creates inherited weakness."""

    name: str
    severity: str  # critical, high, medium, low
    description: str
    affected_components: list[str]
    remediation: str
    prevalence: float  # how common this weakness is in industry (0-1)


@dataclass
class FailureAffinity:
    """Prediction of how susceptible the genome is to a specific failure type."""

    failure_type: str
    affinity_score: float  # 0-1, how susceptible
    contributing_genes: list[str]
    explanation: str


@dataclass
class GenomeProfile:
    """Complete resilience genome of an infrastructure."""

    infrastructure_id: str  # hash of topology
    traits: list[GenomeTrait]
    genome_hash: str  # SHA256 of sorted trait values
    resilience_grade: str  # A+ through F
    structural_age: str  # archetype: monolith, microservices, serverless, hybrid
    weakness_genes: list[str]
    evolution_vector: dict[str, float]  # direction of change over time
    benchmark_percentile: float  # overall percentile vs industry (0-100)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def trait_vector(self) -> list[float]:
        """Return trait values as a sorted, deterministic vector."""
        return [t.value for t in sorted(self.traits, key=lambda t: t.name)]

    def trait_by_name(self, name: str) -> GenomeTrait | None:
        """Look up a trait by name."""
        for t in self.traits:
            if t.name == name:
                return t
        return None

    def category_score(self, category: str) -> float:
        """Average trait value for a given category (0-1)."""
        cat_traits = [t for t in self.traits if t.category == category]
        if not cat_traits:
            return 0.0
        return sum(t.value for t in cat_traits) / len(cat_traits)


@dataclass
class GenomeComparison:
    """Result of comparing two infrastructure genomes."""

    similarity_score: float  # 0-1 cosine similarity
    divergent_traits: list[tuple[str, float, float]]  # (trait, val_a, val_b)
    strengths_a: list[str]
    strengths_b: list[str]


@dataclass
class BenchmarkResult:
    """Result of benchmarking a genome against an industry."""

    industry: str
    overall_percentile: float  # 0-100
    trait_percentiles: dict[str, float]  # trait_name -> percentile
    above_average: list[str]
    below_average: list[str]
    recommendations: list[str]


@dataclass
class EvolutionReport:
    """Report on how a genome has changed over time."""

    snapshots: int
    time_span_days: float
    overall_trend: str  # improving, stable, degrading
    trait_trends: dict[str, str]  # trait_name -> improving/stable/degrading
    evolution_vector: dict[str, float]  # trait_name -> delta
    grade_history: list[str]


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class ChaosGenomeEngine:
    """Engine for extracting, comparing, and benchmarking infrastructure genomes."""

    def __init__(self) -> None:
        self._benchmarks = INDUSTRY_BENCHMARKS

    # === Public API ========================================================

    def analyze(self, graph: InfraGraph) -> GenomeProfile:
        """Extract all traits and compute the full genome profile."""
        traits = self._extract_all_traits(graph)

        # Compute infrastructure ID from topology structure
        infra_id = self._compute_infrastructure_id(graph)

        # Compute genome hash from sorted trait values
        genome_hash = self._compute_genome_hash(traits)

        # Compute overall score (0-100) from trait values
        overall_score = self._compute_overall_score(traits)

        # Grade
        grade = _score_to_grade(overall_score)

        # Determine structural archetype
        archetype = self._determine_archetype(graph, traits)

        # Weakness genes
        weakness_genes = self.find_weakness_genes(graph)
        weakness_names = [w.name for w in weakness_genes]

        return GenomeProfile(
            infrastructure_id=infra_id,
            traits=traits,
            genome_hash=genome_hash,
            resilience_grade=grade,
            structural_age=archetype,
            weakness_genes=weakness_names,
            evolution_vector={},
            benchmark_percentile=overall_score,
        )

    def compare(
        self, genome_a: GenomeProfile, genome_b: GenomeProfile
    ) -> GenomeComparison:
        """Compare two genomes using cosine similarity."""
        vec_a = genome_a.trait_vector()
        vec_b = genome_b.trait_vector()

        similarity = self._cosine_similarity(vec_a, vec_b)

        # Build trait map for each genome
        map_a = {t.name: t.value for t in genome_a.traits}
        map_b = {t.name: t.value for t in genome_b.traits}

        all_names = sorted(set(map_a.keys()) | set(map_b.keys()))

        divergent: list[tuple[str, float, float]] = []
        strengths_a: list[str] = []
        strengths_b: list[str] = []
        threshold = 0.1  # minimum difference to be considered divergent

        for name in all_names:
            val_a = map_a.get(name, 0.0)
            val_b = map_b.get(name, 0.0)
            diff = abs(val_a - val_b)
            if diff >= threshold:
                divergent.append((name, val_a, val_b))
                if val_a > val_b:
                    strengths_a.append(name)
                else:
                    strengths_b.append(name)

        return GenomeComparison(
            similarity_score=similarity,
            divergent_traits=divergent,
            strengths_a=strengths_a,
            strengths_b=strengths_b,
        )

    def benchmark(
        self, genome: GenomeProfile, industry: str = "saas"
    ) -> BenchmarkResult:
        """Benchmark a genome against industry averages."""
        if industry not in self._benchmarks:
            available = ", ".join(sorted(self._benchmarks.keys()))
            raise ValueError(
                f"Unknown industry '{industry}'. Available: {available}"
            )

        bench = self._benchmarks[industry]
        trait_map = {t.name: t.value for t in genome.traits}

        trait_percentiles: dict[str, float] = {}
        above: list[str] = []
        below: list[str] = []
        recommendations: list[str] = []

        for trait_name, bench_val in bench.items():
            actual = trait_map.get(trait_name, 0.0)
            # Compute a simple percentile relative to the benchmark
            # If actual >= bench, percentile > 50; if actual < bench, percentile < 50
            if bench_val > 0:
                ratio = actual / bench_val
                percentile = min(100.0, ratio * 50.0)
            else:
                percentile = 50.0 if actual == 0 else 100.0

            trait_percentiles[trait_name] = round(percentile, 1)

            if actual >= bench_val:
                above.append(trait_name)
            else:
                below.append(trait_name)
                gap = bench_val - actual
                if gap > 0.15:
                    recommendations.append(
                        f"Improve '{trait_name}' — currently {actual:.2f} "
                        f"vs {industry} average {bench_val:.2f} (gap: {gap:.2f})"
                    )

        overall_percentile = (
            sum(trait_percentiles.values()) / len(trait_percentiles)
            if trait_percentiles
            else 50.0
        )

        return BenchmarkResult(
            industry=industry,
            overall_percentile=round(overall_percentile, 1),
            trait_percentiles=trait_percentiles,
            above_average=above,
            below_average=below,
            recommendations=recommendations,
        )

    def track_evolution(self, history: list[GenomeProfile]) -> EvolutionReport:
        """Track how the genome has changed over a series of snapshots."""
        if not history:
            return EvolutionReport(
                snapshots=0,
                time_span_days=0.0,
                overall_trend="stable",
                trait_trends={},
                evolution_vector={},
                grade_history=[],
            )

        # Sort by timestamp
        sorted_history = sorted(history, key=lambda g: g.timestamp)
        first = sorted_history[0]
        last = sorted_history[-1]

        time_span = (last.timestamp - first.timestamp).total_seconds() / 86400.0

        # Compute per-trait evolution vector (last - first)
        first_map = {t.name: t.value for t in first.traits}
        last_map = {t.name: t.value for t in last.traits}
        all_names = sorted(set(first_map.keys()) | set(last_map.keys()))

        evolution_vector: dict[str, float] = {}
        trait_trends: dict[str, str] = {}
        improving_count = 0
        degrading_count = 0

        for name in all_names:
            delta = last_map.get(name, 0.0) - first_map.get(name, 0.0)
            evolution_vector[name] = round(delta, 4)
            if delta > 0.05:
                trait_trends[name] = "improving"
                improving_count += 1
            elif delta < -0.05:
                trait_trends[name] = "degrading"
                degrading_count += 1
            else:
                trait_trends[name] = "stable"

        if improving_count > degrading_count:
            overall_trend = "improving"
        elif degrading_count > improving_count:
            overall_trend = "degrading"
        else:
            overall_trend = "stable"

        grade_history = [g.resilience_grade for g in sorted_history]

        return EvolutionReport(
            snapshots=len(sorted_history),
            time_span_days=round(time_span, 1),
            overall_trend=overall_trend,
            trait_trends=trait_trends,
            evolution_vector=evolution_vector,
            grade_history=grade_history,
        )

    def find_weakness_genes(self, graph: InfraGraph) -> list[WeaknessGene]:
        """Identify architectural anti-patterns ('weakness genes') in the topology."""
        weaknesses: list[WeaknessGene] = []
        components = graph.components
        if not components:
            return weaknesses

        for pattern in _WEAKNESS_CATALOG:
            affected = self._check_weakness(graph, pattern["check"])
            if affected:
                weaknesses.append(
                    WeaknessGene(
                        name=pattern["name"],
                        severity=pattern["severity"],
                        description=pattern["description"],
                        affected_components=affected,
                        remediation=pattern["remediation"],
                        prevalence=pattern["prevalence"],
                    )
                )

        return weaknesses

    def predict_failure_affinity(
        self, genome: GenomeProfile
    ) -> list[FailureAffinity]:
        """Predict which failure types this genome is most susceptible to."""
        trait_map = {t.name: t.value for t in genome.traits}
        weakness_set = set(genome.weakness_genes)
        affinities: list[FailureAffinity] = []

        for pattern in _FAILURE_AFFINITY_PATTERNS:
            # Compute affinity score from weighted trait values
            score = 0.0
            for trait_name, weight in zip(
                pattern["contributing_traits"], pattern["trait_weights"]
            ):
                val = trait_map.get(trait_name, 0.5)
                # For negative weights, invert the contribution:
                # low value + negative weight = high affinity
                score += weight * val

            # Normalize to 0-1 range: raw score is in roughly [-1, 1]
            affinity = max(0.0, min(1.0, 0.5 + score))

            # Boost if matching weakness genes are present
            matching_genes = [
                g for g in pattern["contributing_genes"] if g in weakness_set
            ]
            if matching_genes:
                affinity = min(1.0, affinity + 0.15 * len(matching_genes))

            affinities.append(
                FailureAffinity(
                    failure_type=pattern["failure_type"],
                    affinity_score=round(affinity, 3),
                    contributing_genes=matching_genes,
                    explanation=pattern["explanation"],
                )
            )

        # Sort by affinity descending
        affinities.sort(key=lambda a: a.affinity_score, reverse=True)
        return affinities

    # === Trait Extraction Methods ==========================================

    def _extract_all_traits(self, graph: InfraGraph) -> list[GenomeTrait]:
        """Extract all measurable traits from the infrastructure graph."""
        traits: list[GenomeTrait] = []

        # Structure traits
        traits.append(self._trait_graph_density(graph))
        traits.append(self._trait_avg_path_length(graph))
        traits.append(self._trait_max_depth(graph))
        traits.append(self._trait_clustering_coefficient(graph))
        traits.append(self._trait_component_diversity(graph))

        # Redundancy traits
        traits.append(self._trait_avg_replicas(graph))
        traits.append(self._trait_min_replicas(graph))
        traits.append(self._trait_failover_coverage(graph))
        traits.append(self._trait_multi_az_coverage(graph))

        # Diversity traits
        traits.append(self._trait_provider_diversity(graph))
        traits.append(self._trait_type_diversity(graph))
        traits.append(self._trait_version_spread(graph))

        # Isolation traits
        traits.append(self._trait_circuit_breaker_coverage(graph))
        traits.append(self._trait_blast_radius_avg(graph))
        traits.append(self._trait_isolation_score(graph))

        # Recovery traits
        traits.append(self._trait_autoscaling_coverage(graph))
        traits.append(self._trait_avg_recovery_time(graph))
        traits.append(self._trait_health_check_coverage(graph))

        return traits

    # -- Structure traits ---------------------------------------------------

    def _trait_graph_density(self, graph: InfraGraph) -> GenomeTrait:
        """Edge density of the dependency graph."""
        g = graph._graph
        n = g.number_of_nodes()
        if n <= 1:
            density = 0.0
        else:
            max_edges = n * (n - 1)  # directed graph
            density = g.number_of_edges() / max_edges if max_edges > 0 else 0.0
        return GenomeTrait(name="graph_density", value=density, category="structure")

    def _trait_avg_path_length(self, graph: InfraGraph) -> GenomeTrait:
        """Average shortest path between components (normalized)."""
        g = graph._graph
        if g.number_of_nodes() <= 1:
            return GenomeTrait(name="avg_path_length", value=0.0, category="structure")

        try:
            if nx.is_weakly_connected(g):
                # Use the undirected version for average path length
                avg = nx.average_shortest_path_length(g.to_undirected())
            else:
                # For disconnected graphs, compute per component
                undirected = g.to_undirected()
                lengths = []
                for cc in nx.connected_components(undirected):
                    if len(cc) > 1:
                        subgraph = undirected.subgraph(cc)
                        lengths.append(nx.average_shortest_path_length(subgraph))
                avg = sum(lengths) / len(lengths) if lengths else 0.0
        except Exception:
            avg = 0.0

        # Normalize: path length of 1 -> 1.0, 10+ -> ~0.1
        # Shorter paths = better connectivity = higher value
        normalized = 1.0 / (1.0 + avg) if avg > 0 else 0.0
        return GenomeTrait(name="avg_path_length", value=normalized, category="structure")

    def _trait_max_depth(self, graph: InfraGraph) -> GenomeTrait:
        """Maximum dependency chain depth (normalized)."""
        g = graph._graph
        if g.number_of_nodes() == 0:
            return GenomeTrait(name="max_depth", value=0.0, category="structure")

        max_depth = 0
        try:
            max_depth = nx.dag_longest_path_length(g)
        except nx.NetworkXUnfeasible:
            # Graph has cycles; use longest shortest path as proxy
            try:
                for node in g.nodes:
                    lengths = nx.single_source_shortest_path_length(g, node)
                    if lengths:
                        max_depth = max(max_depth, max(lengths.values()))
            except Exception:
                max_depth = 0

        # Normalize: depth 1 -> 0.9, depth 5 -> 0.5, depth 10+ -> ~0.1
        # Shallower = better = higher value
        normalized = 1.0 / (1.0 + max_depth * 0.2) if max_depth > 0 else 1.0
        return GenomeTrait(name="max_depth", value=normalized, category="structure")

    def _trait_clustering_coefficient(self, graph: InfraGraph) -> GenomeTrait:
        """Graph clustering coefficient (using undirected version)."""
        g = graph._graph
        if g.number_of_nodes() <= 2:
            return GenomeTrait(
                name="clustering_coefficient", value=0.0, category="structure"
            )

        undirected = g.to_undirected()
        cc = nx.average_clustering(undirected)
        return GenomeTrait(
            name="clustering_coefficient", value=cc, category="structure"
        )

    def _trait_component_diversity(self, graph: InfraGraph) -> GenomeTrait:
        """Shannon entropy of component type distribution (normalized)."""
        components = graph.components
        if not components:
            return GenomeTrait(
                name="component_diversity", value=0.0, category="structure"
            )

        type_counts = Counter(c.type.value for c in components.values())
        total = sum(type_counts.values())
        if total == 0:
            return GenomeTrait(
                name="component_diversity", value=0.0, category="structure"
            )

        # Shannon entropy
        entropy = 0.0
        for count in type_counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        # Normalize by max possible entropy (log2 of number of types)
        num_types = len(type_counts)
        max_entropy = math.log2(num_types) if num_types > 1 else 1.0
        normalized = entropy / max_entropy if max_entropy > 0 else 0.0

        return GenomeTrait(
            name="component_diversity", value=normalized, category="structure"
        )

    # -- Redundancy traits --------------------------------------------------

    def _trait_avg_replicas(self, graph: InfraGraph) -> GenomeTrait:
        """Average replica count across components (normalized)."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(name="avg_replicas", value=0.0, category="redundancy")

        avg = sum(c.replicas for c in components) / len(components)
        # Normalize: 1 replica -> 0.2, 2 -> 0.5, 3 -> 0.7, 5+ -> ~1.0
        normalized = 1.0 - 1.0 / (1.0 + (avg - 1) * 0.5) if avg > 1 else 0.2
        return GenomeTrait(name="avg_replicas", value=normalized, category="redundancy")

    def _trait_min_replicas(self, graph: InfraGraph) -> GenomeTrait:
        """Minimum replica count (weakest link, normalized)."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(name="min_replicas", value=0.0, category="redundancy")

        min_rep = min(c.replicas for c in components)
        # 1 replica = 0.1 (weak), 2 = 0.5, 3+ = 0.8+
        if min_rep <= 1:
            normalized = 0.1
        elif min_rep == 2:
            normalized = 0.5
        else:
            normalized = min(1.0, 0.5 + (min_rep - 2) * 0.15)
        return GenomeTrait(name="min_replicas", value=normalized, category="redundancy")

    def _trait_failover_coverage(self, graph: InfraGraph) -> GenomeTrait:
        """Percentage of components with failover enabled."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(
                name="failover_coverage", value=0.0, category="redundancy"
            )

        enabled = sum(1 for c in components if c.failover.enabled)
        ratio = enabled / len(components)
        return GenomeTrait(
            name="failover_coverage", value=ratio, category="redundancy"
        )

    def _trait_multi_az_coverage(self, graph: InfraGraph) -> GenomeTrait:
        """Percentage of components spanning multiple AZs."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(
                name="multi_az_coverage", value=0.0, category="redundancy"
            )

        # Collect all unique AZs
        azs = set()
        for c in components:
            if c.region.availability_zone:
                azs.add(c.region.availability_zone)

        # If there's more than one AZ, check coverage
        if len(azs) <= 1:
            # All in same AZ (or no AZ info)
            return GenomeTrait(
                name="multi_az_coverage", value=0.0, category="redundancy"
            )

        # Count how many components have AZ info (i.e. participate in multi-AZ)
        has_az = sum(1 for c in components if c.region.availability_zone)
        ratio = has_az / len(components) if has_az > 0 else 0.0
        return GenomeTrait(
            name="multi_az_coverage", value=ratio, category="redundancy"
        )

    # -- Diversity traits ---------------------------------------------------

    def _trait_provider_diversity(self, graph: InfraGraph) -> GenomeTrait:
        """How many cloud providers / tech stacks (from tags/host patterns)."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(
                name="provider_diversity", value=0.0, category="diversity"
            )

        # Infer providers from tags, host names, etc.
        providers: set[str] = set()
        for c in components:
            for tag in c.tags:
                tag_lower = tag.lower()
                if any(
                    p in tag_lower
                    for p in ("aws", "gcp", "azure", "onprem", "do", "heroku")
                ):
                    providers.add(tag_lower)
            # Also check host patterns
            host_lower = c.host.lower()
            if "aws" in host_lower or "ec2" in host_lower or "amazonaws" in host_lower:
                providers.add("aws")
            elif "gcp" in host_lower or "gke" in host_lower:
                providers.add("gcp")
            elif "azure" in host_lower:
                providers.add("azure")

        # Normalize: 1 provider -> 0.2, 2 -> 0.6, 3+ -> 0.9+
        n = len(providers)
        if n == 0:
            # No provider info available; assume single provider
            normalized = 0.2
        elif n == 1:
            normalized = 0.2
        elif n == 2:
            normalized = 0.6
        else:
            normalized = min(1.0, 0.6 + (n - 2) * 0.15)

        return GenomeTrait(
            name="provider_diversity", value=normalized, category="diversity"
        )

    def _trait_type_diversity(self, graph: InfraGraph) -> GenomeTrait:
        """Variety of component types used (ratio of used types to available)."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(name="type_diversity", value=0.0, category="diversity")

        used_types = len(set(c.type for c in components))
        total_types = len(ComponentType)
        ratio = used_types / total_types
        return GenomeTrait(name="type_diversity", value=ratio, category="diversity")

    def _trait_version_spread(self, graph: InfraGraph) -> GenomeTrait:
        """How varied the technology versions are (from parameters/tags)."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(name="version_spread", value=0.0, category="diversity")

        # Infer version info from parameters
        versions: set[str] = set()
        for c in components:
            ver = c.parameters.get("version", "")
            if ver:
                versions.add(str(ver))
            for tag in c.tags:
                # Look for version-like patterns
                if any(c_char.isdigit() for c_char in tag) and "." in tag:
                    versions.add(tag)

        # Normalize: 0 versions known -> 0.5 (neutral), more = higher diversity
        n = len(versions)
        if n == 0:
            normalized = 0.5  # No version info = neutral
        else:
            normalized = min(1.0, n / (len(components) * 0.5))

        return GenomeTrait(
            name="version_spread", value=normalized, category="diversity"
        )

    # -- Isolation traits ---------------------------------------------------

    def _trait_circuit_breaker_coverage(self, graph: InfraGraph) -> GenomeTrait:
        """Percentage of dependency edges with circuit breakers enabled."""
        edges = graph.all_dependency_edges()
        if not edges:
            return GenomeTrait(
                name="circuit_breaker_coverage", value=1.0, category="isolation"
            )

        enabled = sum(1 for e in edges if e.circuit_breaker.enabled)
        ratio = enabled / len(edges)
        return GenomeTrait(
            name="circuit_breaker_coverage", value=ratio, category="isolation"
        )

    def _trait_blast_radius_avg(self, graph: InfraGraph) -> GenomeTrait:
        """Average cascade impact per component failure (normalized, inverted)."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(
                name="blast_radius_avg", value=1.0, category="isolation"
            )

        total_affected = 0
        for comp in components:
            affected = graph.get_all_affected(comp.id)
            total_affected += len(affected)

        avg_affected = total_affected / len(components)
        # Normalize: 0 affected = 1.0 (best), many = near 0.0
        # Inverted because lower blast radius is better
        max_possible = len(components) - 1
        if max_possible > 0:
            normalized = 1.0 - (avg_affected / max_possible)
        else:
            normalized = 1.0

        return GenomeTrait(
            name="blast_radius_avg", value=max(0.0, normalized), category="isolation"
        )

    def _trait_isolation_score(self, graph: InfraGraph) -> GenomeTrait:
        """Composite score of how well failures are contained."""
        # Combine circuit breaker coverage, blast radius, and graph structure
        cb = self._trait_circuit_breaker_coverage(graph).value
        blast = self._trait_blast_radius_avg(graph).value

        # Weight circuit breakers higher since they directly contain failures
        isolation = cb * 0.6 + blast * 0.4
        return GenomeTrait(
            name="isolation_score", value=isolation, category="isolation"
        )

    # -- Recovery traits ----------------------------------------------------

    def _trait_autoscaling_coverage(self, graph: InfraGraph) -> GenomeTrait:
        """Percentage of components with autoscaling enabled."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(
                name="autoscaling_coverage", value=0.0, category="recovery"
            )

        enabled = sum(1 for c in components if c.autoscaling.enabled)
        ratio = enabled / len(components)
        return GenomeTrait(
            name="autoscaling_coverage", value=ratio, category="recovery"
        )

    def _trait_avg_recovery_time(self, graph: InfraGraph) -> GenomeTrait:
        """Average estimated recovery time (normalized, inverted)."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(
                name="avg_recovery_time", value=0.0, category="recovery"
            )

        recovery_times: list[float] = []
        for c in components:
            # Estimate recovery time from operational profile and failover config
            base_mttr = c.operational_profile.mttr_minutes
            if c.failover.enabled:
                # Failover reduces recovery time
                recovery_time = min(
                    base_mttr,
                    c.failover.promotion_time_seconds / 60.0,
                )
            elif c.autoscaling.enabled:
                recovery_time = min(
                    base_mttr,
                    c.autoscaling.scale_up_delay_seconds / 60.0,
                )
            else:
                recovery_time = base_mttr
            recovery_times.append(recovery_time)

        avg_recovery = sum(recovery_times) / len(recovery_times) if recovery_times else 30.0

        # Normalize: 0 min = 1.0 (instant), 60 min = ~0.0
        # Inverted because faster recovery is better
        normalized = 1.0 / (1.0 + avg_recovery / 10.0)
        return GenomeTrait(
            name="avg_recovery_time", value=normalized, category="recovery"
        )

    def _trait_health_check_coverage(self, graph: InfraGraph) -> GenomeTrait:
        """Percentage of components with health checks configured."""
        components = list(graph.components.values())
        if not components:
            return GenomeTrait(
                name="health_check_coverage", value=0.0, category="recovery"
            )

        # Consider a component to have health checks if:
        # - failover is enabled (implies health checking), or
        # - health_check_interval_seconds is set in failover config (even if failover disabled)
        has_health_check = 0
        for c in components:
            if c.failover.enabled:
                has_health_check += 1
            elif c.failover.health_check_interval_seconds < 30.0:
                # Custom health check interval configured (default is 10, but we check <30
                # to identify intentional configuration)
                has_health_check += 1
            elif c.autoscaling.enabled:
                # Autoscaling implies some form of health monitoring
                has_health_check += 1

        ratio = has_health_check / len(components)
        return GenomeTrait(
            name="health_check_coverage", value=ratio, category="recovery"
        )

    # === Internal Helpers ==================================================

    def _compute_infrastructure_id(self, graph: InfraGraph) -> str:
        """Compute a deterministic hash of the topology structure."""
        # Hash component IDs and types + edge structure
        parts: list[str] = []
        for comp_id in sorted(graph.components.keys()):
            comp = graph.components[comp_id]
            parts.append(f"{comp_id}:{comp.type.value}:{comp.replicas}")

        for edge in sorted(
            graph.all_dependency_edges(),
            key=lambda e: (e.source_id, e.target_id),
        ):
            parts.append(f"{edge.source_id}->{edge.target_id}:{edge.dependency_type}")

        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _compute_genome_hash(self, traits: list[GenomeTrait]) -> str:
        """Compute SHA256 hash of sorted trait values for fingerprinting."""
        sorted_traits = sorted(traits, key=lambda t: t.name)
        # Use 4 decimal places for deterministic hashing
        values_str = ",".join(
            f"{t.name}={t.value:.4f}" for t in sorted_traits
        )
        return hashlib.sha256(values_str.encode()).hexdigest()

    def _compute_overall_score(self, traits: list[GenomeTrait]) -> float:
        """Compute overall resilience score (0-100) from trait values.

        Weighted by category importance:
        - redundancy:  30%
        - isolation:   25%
        - recovery:    25%
        - structure:   10%
        - diversity:   10%
        """
        category_weights = {
            "redundancy": 0.30,
            "isolation": 0.25,
            "recovery": 0.25,
            "structure": 0.10,
            "diversity": 0.10,
        }

        category_scores: dict[str, list[float]] = {cat: [] for cat in TRAIT_CATEGORIES}
        for t in traits:
            category_scores[t.category].append(t.value)

        weighted_sum = 0.0
        for cat, scores in category_scores.items():
            if scores:
                avg = sum(scores) / len(scores)
                weighted_sum += avg * category_weights.get(cat, 0.1)

        return round(weighted_sum * 100, 1)

    def _determine_archetype(
        self, graph: InfraGraph, traits: list[GenomeTrait]
    ) -> str:
        """Determine the structural archetype of the infrastructure."""
        components = graph.components
        n_components = len(components)

        if n_components == 0:
            return "unknown"

        # Check for serverless indicators
        has_serverless_tags = any(
            "serverless" in tag.lower() or "lambda" in tag.lower() or "function" in tag.lower()
            for c in components.values()
            for tag in c.tags
        )
        if has_serverless_tags:
            return "serverless"

        # Microservices: many components, moderate density
        trait_map = {t.name: t.value for t in traits}
        trait_map.get("graph_density", 0.5)
        diversity = trait_map.get("component_diversity", 0.5)

        if n_components >= 8 and diversity > 0.5:
            return "microservices"

        if n_components <= 3:
            return "monolith"

        # Hybrid is the default for medium complexity
        return "hybrid"

    def _check_weakness(self, graph: InfraGraph, check_type: str) -> list[str]:
        """Check for a specific weakness pattern and return affected component IDs."""
        components = graph.components
        affected: list[str] = []

        if check_type == "single_db":
            for comp in components.values():
                if comp.type == ComponentType.DATABASE and comp.replicas <= 1 and not comp.failover.enabled:
                    affected.append(comp.id)

        elif check_type == "no_cb":
            edges = graph.all_dependency_edges()
            for edge in edges:
                if edge.dependency_type == "requires" and not edge.circuit_breaker.enabled:
                    affected.append(f"{edge.source_id}->{edge.target_id}")

        elif check_type == "single_lb":
            for comp in components.values():
                if comp.type == ComponentType.LOAD_BALANCER and comp.replicas <= 1 and not comp.failover.enabled:
                    affected.append(comp.id)

        elif check_type == "no_autoscale":
            for comp in components.values():
                if not comp.autoscaling.enabled:
                    affected.append(comp.id)

        elif check_type == "deep_chain":
            g = graph._graph
            try:
                max_depth = nx.dag_longest_path_length(g)
            except nx.NetworkXUnfeasible:
                max_depth = 0
            if max_depth > 5:
                # Report the longest path
                try:
                    longest = nx.dag_longest_path(g)
                    affected = longest
                except Exception:
                    affected = ["deep_chain_detected"]

        elif check_type == "no_health":
            for comp in components.values():
                if not comp.failover.enabled and not comp.autoscaling.enabled:
                    affected.append(comp.id)

        elif check_type == "single_az":
            azs = set()
            for comp in components.values():
                if comp.region.availability_zone:
                    azs.add(comp.region.availability_zone)
            if len(azs) <= 1:
                affected = [c.id for c in components.values()]

        elif check_type == "no_failover":
            for comp in components.values():
                # Only flag stateful or critical components without failover
                if comp.type in (
                    ComponentType.DATABASE,
                    ComponentType.CACHE,
                    ComponentType.QUEUE,
                    ComponentType.STORAGE,
                ) and not comp.failover.enabled:
                    affected.append(comp.id)

        return affected

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(vec_a) != len(vec_b):
            # Pad shorter vector with zeros
            max_len = max(len(vec_a), len(vec_b))
            vec_a = vec_a + [0.0] * (max_len - len(vec_a))
            vec_b = vec_b + [0.0] * (max_len - len(vec_b))

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot / (norm_a * norm_b)
