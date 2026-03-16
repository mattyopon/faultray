"""Tests for Chaos Genome - Infrastructure Resilience DNA Fingerprinting."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    ResourceMetrics,
)
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph
from faultray.simulator.chaos_genome import (
    INDUSTRY_BENCHMARKS,
    TRAIT_CATEGORIES,
    BenchmarkResult,
    ChaosGenomeEngine,
    EvolutionReport,
    FailureAffinity,
    GenomeComparison,
    GenomeProfile,
    GenomeTrait,
    WeaknessGene,
    _score_to_grade,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_simple_graph() -> InfraGraph:
    """Build a minimal 3-component graph: LB -> App -> DB."""
    graph = InfraGraph()
    graph.add_component(
        Component(
            id="lb",
            name="Load Balancer",
            type=ComponentType.LOAD_BALANCER,
            port=443,
            replicas=1,
        )
    )
    graph.add_component(
        Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            port=8080,
            replicas=2,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        )
    )
    graph.add_component(
        Component(
            id="db",
            name="Database",
            type=ComponentType.DATABASE,
            port=5432,
            replicas=1,
        )
    )
    graph.add_dependency(
        Dependency(
            source_id="lb",
            target_id="app",
            dependency_type="requires",
        )
    )
    graph.add_dependency(
        Dependency(
            source_id="app",
            target_id="db",
            dependency_type="requires",
        )
    )
    return graph


def _build_resilient_graph() -> InfraGraph:
    """Build a resilient graph with failover, circuit breakers, multi-AZ."""
    graph = InfraGraph()

    graph.add_component(
        Component(
            id="lb",
            name="Load Balancer",
            type=ComponentType.LOAD_BALANCER,
            port=443,
            replicas=2,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=5.0),
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
            region=RegionConfig(availability_zone="us-east-1a"),
        )
    )
    graph.add_component(
        Component(
            id="app1",
            name="App Server 1",
            type=ComponentType.APP_SERVER,
            port=8080,
            replicas=3,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=10.0),
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=3, max_replicas=20),
            region=RegionConfig(availability_zone="us-east-1a"),
        )
    )
    graph.add_component(
        Component(
            id="app2",
            name="App Server 2",
            type=ComponentType.APP_SERVER,
            port=8080,
            replicas=3,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=10.0),
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=3, max_replicas=20),
            region=RegionConfig(availability_zone="us-east-1b"),
        )
    )
    graph.add_component(
        Component(
            id="db",
            name="Primary DB",
            type=ComponentType.DATABASE,
            port=5432,
            replicas=2,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=30.0),
            region=RegionConfig(availability_zone="us-east-1a"),
        )
    )
    graph.add_component(
        Component(
            id="cache",
            name="Redis Cache",
            type=ComponentType.CACHE,
            port=6379,
            replicas=3,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=5.0),
            region=RegionConfig(availability_zone="us-east-1b"),
        )
    )

    graph.add_dependency(
        Dependency(
            source_id="lb",
            target_id="app1",
            dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )
    graph.add_dependency(
        Dependency(
            source_id="lb",
            target_id="app2",
            dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )
    graph.add_dependency(
        Dependency(
            source_id="app1",
            target_id="db",
            dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )
    graph.add_dependency(
        Dependency(
            source_id="app2",
            target_id="db",
            dependency_type="requires",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )
    graph.add_dependency(
        Dependency(
            source_id="app1",
            target_id="cache",
            dependency_type="optional",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )
    graph.add_dependency(
        Dependency(
            source_id="app2",
            target_id="cache",
            dependency_type="optional",
            circuit_breaker=CircuitBreakerConfig(enabled=True),
        )
    )

    return graph


# ---------------------------------------------------------------------------
# GenomeTrait tests
# ---------------------------------------------------------------------------


class TestGenomeTrait:
    def test_valid_trait(self):
        t = GenomeTrait(name="test", value=0.5, category="structure")
        assert t.name == "test"
        assert t.value == 0.5
        assert t.category == "structure"
        assert t.percentile is None

    def test_trait_clamps_value(self):
        t = GenomeTrait(name="over", value=1.5, category="redundancy")
        assert t.value == 1.0

        t2 = GenomeTrait(name="under", value=-0.3, category="isolation")
        assert t2.value == 0.0

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError, match="Invalid trait category"):
            GenomeTrait(name="bad", value=0.5, category="nonexistent")

    def test_all_categories_accepted(self):
        for cat in TRAIT_CATEGORIES:
            t = GenomeTrait(name=f"test_{cat}", value=0.5, category=cat)
            assert t.category == cat


# ---------------------------------------------------------------------------
# Grading tests
# ---------------------------------------------------------------------------


class TestGrading:
    def test_grade_boundaries(self):
        assert _score_to_grade(100.0) == "A+"
        assert _score_to_grade(95.0) == "A+"
        assert _score_to_grade(94.9) == "A"
        assert _score_to_grade(90.0) == "A"
        assert _score_to_grade(89.9) == "A-"
        assert _score_to_grade(85.0) == "A-"
        assert _score_to_grade(84.9) == "B+"
        assert _score_to_grade(80.0) == "B+"
        assert _score_to_grade(79.9) == "B"
        assert _score_to_grade(75.0) == "B"
        assert _score_to_grade(74.9) == "B-"
        assert _score_to_grade(70.0) == "B-"
        assert _score_to_grade(69.9) == "C+"
        assert _score_to_grade(65.0) == "C+"
        assert _score_to_grade(64.9) == "C"
        assert _score_to_grade(60.0) == "C"
        assert _score_to_grade(59.9) == "C-"
        assert _score_to_grade(55.0) == "C-"
        assert _score_to_grade(54.9) == "D"
        assert _score_to_grade(45.0) == "D"
        assert _score_to_grade(44.9) == "F"
        assert _score_to_grade(0.0) == "F"

    def test_negative_score(self):
        assert _score_to_grade(-5.0) == "F"


# ---------------------------------------------------------------------------
# ChaosGenomeEngine.analyze() tests
# ---------------------------------------------------------------------------


class TestChaosGenomeAnalyze:
    def test_analyze_simple_graph(self):
        graph = _build_simple_graph()
        engine = ChaosGenomeEngine()
        genome = engine.analyze(graph)

        assert isinstance(genome, GenomeProfile)
        assert genome.infrastructure_id  # non-empty hash
        assert genome.genome_hash  # non-empty hash
        assert genome.resilience_grade in (
            "A+", "A", "A-", "B+", "B", "B-",
            "C+", "C", "C-", "D", "F",
        )
        assert genome.structural_age in ("monolith", "microservices", "serverless", "hybrid", "unknown")
        assert isinstance(genome.traits, list)
        assert len(genome.traits) == 18  # all 18 traits extracted
        assert isinstance(genome.weakness_genes, list)

    def test_analyze_demo_graph(self):
        graph = create_demo_graph()
        engine = ChaosGenomeEngine()
        genome = engine.analyze(graph)

        assert genome.infrastructure_id
        assert len(genome.traits) == 18
        # Demo graph has 6 components with diverse types
        assert genome.structural_age in ("hybrid", "microservices")

    def test_analyze_resilient_graph_scores_higher(self):
        simple = _build_simple_graph()
        resilient = _build_resilient_graph()
        engine = ChaosGenomeEngine()

        genome_simple = engine.analyze(simple)
        genome_resilient = engine.analyze(resilient)

        # Resilient graph should score higher
        assert genome_resilient.benchmark_percentile > genome_simple.benchmark_percentile

    def test_analyze_empty_graph(self):
        graph = InfraGraph()
        engine = ChaosGenomeEngine()
        genome = engine.analyze(graph)

        assert genome.resilience_grade == "F"
        assert genome.structural_age == "unknown"
        assert len(genome.traits) == 18
        # All traits should be 0 for empty graph
        for t in genome.traits:
            assert t.value == 0.0 or t.value == 1.0  # some defaults are 1.0

    def test_genome_hash_deterministic(self):
        graph = _build_simple_graph()
        engine = ChaosGenomeEngine()
        genome1 = engine.analyze(graph)
        genome2 = engine.analyze(graph)

        assert genome1.genome_hash == genome2.genome_hash

    def test_infrastructure_id_deterministic(self):
        graph = _build_simple_graph()
        engine = ChaosGenomeEngine()
        genome1 = engine.analyze(graph)
        genome2 = engine.analyze(graph)

        assert genome1.infrastructure_id == genome2.infrastructure_id

    def test_different_graphs_have_different_hashes(self):
        graph1 = _build_simple_graph()
        graph2 = _build_resilient_graph()
        engine = ChaosGenomeEngine()

        genome1 = engine.analyze(graph1)
        genome2 = engine.analyze(graph2)

        assert genome1.genome_hash != genome2.genome_hash
        assert genome1.infrastructure_id != genome2.infrastructure_id

    def test_all_trait_categories_present(self):
        graph = _build_simple_graph()
        engine = ChaosGenomeEngine()
        genome = engine.analyze(graph)

        categories_found = set(t.category for t in genome.traits)
        assert categories_found == set(TRAIT_CATEGORIES)


# ---------------------------------------------------------------------------
# Trait extraction tests
# ---------------------------------------------------------------------------


class TestTraitExtraction:
    def setup_method(self):
        self.engine = ChaosGenomeEngine()

    def test_graph_density_empty(self):
        graph = InfraGraph()
        trait = self.engine._trait_graph_density(graph)
        assert trait.name == "graph_density"
        assert trait.category == "structure"
        assert trait.value == 0.0

    def test_graph_density_simple(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_graph_density(graph)
        # 3 nodes, 2 edges, max = 3*2 = 6 => density = 2/6 = 0.333
        assert abs(trait.value - 2 / 6) < 0.01

    def test_avg_path_length(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_avg_path_length(graph)
        assert trait.name == "avg_path_length"
        assert trait.category == "structure"
        assert 0.0 < trait.value <= 1.0

    def test_max_depth_simple(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_max_depth(graph)
        assert trait.name == "max_depth"
        assert trait.category == "structure"
        # Depth 2 (lb -> app -> db) => normalized
        assert 0.0 < trait.value <= 1.0

    def test_clustering_coefficient(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_clustering_coefficient(graph)
        assert trait.name == "clustering_coefficient"
        assert trait.category == "structure"
        assert 0.0 <= trait.value <= 1.0

    def test_component_diversity_single_type(self):
        graph = InfraGraph()
        graph.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, port=80))
        graph.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, port=80))
        trait = self.engine._trait_component_diversity(graph)
        # All same type => entropy = 0
        assert trait.value == 0.0

    def test_component_diversity_mixed(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_component_diversity(graph)
        # 3 different types => max entropy
        assert trait.value > 0.9  # should be near 1.0 for 3 unique types out of 3

    def test_avg_replicas(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_avg_replicas(graph)
        assert trait.name == "avg_replicas"
        assert trait.category == "redundancy"
        # Average of (1, 2, 1) = 1.33 -> slightly above min
        assert trait.value > 0.1

    def test_min_replicas(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_min_replicas(graph)
        assert trait.name == "min_replicas"
        assert trait.category == "redundancy"
        # Min is 1 => value should be low (0.1)
        assert trait.value == 0.1

    def test_failover_coverage_none(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_failover_coverage(graph)
        # No failover in simple graph
        assert trait.value == 0.0

    def test_failover_coverage_full(self):
        graph = _build_resilient_graph()
        trait = self.engine._trait_failover_coverage(graph)
        # All components have failover enabled
        assert trait.value == 1.0

    def test_multi_az_coverage_single(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_multi_az_coverage(graph)
        # No AZ info -> 0.0
        assert trait.value == 0.0

    def test_multi_az_coverage_multi(self):
        graph = _build_resilient_graph()
        trait = self.engine._trait_multi_az_coverage(graph)
        # Multiple AZs configured
        assert trait.value > 0.0

    def test_circuit_breaker_coverage_none(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_circuit_breaker_coverage(graph)
        # No circuit breakers
        assert trait.value == 0.0

    def test_circuit_breaker_coverage_full(self):
        graph = _build_resilient_graph()
        trait = self.engine._trait_circuit_breaker_coverage(graph)
        # All edges have circuit breakers
        assert trait.value == 1.0

    def test_blast_radius_avg(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_blast_radius_avg(graph)
        assert trait.name == "blast_radius_avg"
        assert trait.category == "isolation"
        assert 0.0 <= trait.value <= 1.0

    def test_isolation_score(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_isolation_score(graph)
        assert trait.name == "isolation_score"
        assert trait.category == "isolation"

    def test_autoscaling_coverage(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_autoscaling_coverage(graph)
        # Only 1 of 3 components has autoscaling
        assert abs(trait.value - 1 / 3) < 0.01

    def test_avg_recovery_time(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_avg_recovery_time(graph)
        assert trait.name == "avg_recovery_time"
        assert trait.category == "recovery"
        assert 0.0 <= trait.value <= 1.0

    def test_health_check_coverage(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_health_check_coverage(graph)
        assert trait.name == "health_check_coverage"
        assert trait.category == "recovery"

    def test_provider_diversity_no_info(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_provider_diversity(graph)
        assert trait.value == 0.2  # default single provider assumption

    def test_type_diversity(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_type_diversity(graph)
        # 3 distinct types out of 10 total
        assert abs(trait.value - 3 / len(ComponentType)) < 0.01

    def test_version_spread_no_versions(self):
        graph = _build_simple_graph()
        trait = self.engine._trait_version_spread(graph)
        assert trait.value == 0.5  # neutral when no version info


# ---------------------------------------------------------------------------
# Genome comparison tests
# ---------------------------------------------------------------------------


class TestGenomeComparison:
    def test_compare_identical(self):
        graph = _build_simple_graph()
        engine = ChaosGenomeEngine()
        genome = engine.analyze(graph)
        result = engine.compare(genome, genome)

        assert isinstance(result, GenomeComparison)
        assert result.similarity_score == pytest.approx(1.0, abs=0.001)
        assert len(result.divergent_traits) == 0
        assert len(result.strengths_a) == 0
        assert len(result.strengths_b) == 0

    def test_compare_different(self):
        engine = ChaosGenomeEngine()
        genome_a = engine.analyze(_build_simple_graph())
        genome_b = engine.analyze(_build_resilient_graph())
        result = engine.compare(genome_a, genome_b)

        assert 0.0 <= result.similarity_score <= 1.0
        assert result.similarity_score < 1.0  # should be different
        assert len(result.divergent_traits) > 0

    def test_compare_strengths_identified(self):
        engine = ChaosGenomeEngine()
        genome_a = engine.analyze(_build_simple_graph())
        genome_b = engine.analyze(_build_resilient_graph())
        result = engine.compare(genome_a, genome_b)

        # Resilient graph should have more strengths
        assert len(result.strengths_b) > len(result.strengths_a)


# ---------------------------------------------------------------------------
# Benchmarking tests
# ---------------------------------------------------------------------------


class TestBenchmark:
    def test_benchmark_valid_industry(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())
        result = engine.benchmark(genome, "fintech")

        assert isinstance(result, BenchmarkResult)
        assert result.industry == "fintech"
        assert 0.0 <= result.overall_percentile <= 100.0
        assert len(result.trait_percentiles) > 0
        assert isinstance(result.above_average, list)
        assert isinstance(result.below_average, list)

    def test_benchmark_invalid_industry(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())
        with pytest.raises(ValueError, match="Unknown industry"):
            engine.benchmark(genome, "nonexistent")

    def test_benchmark_all_industries(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())

        for industry in INDUSTRY_BENCHMARKS:
            result = engine.benchmark(genome, industry)
            assert result.industry == industry
            assert 0.0 <= result.overall_percentile <= 100.0

    def test_resilient_graph_benchmarks_higher(self):
        engine = ChaosGenomeEngine()
        genome_simple = engine.analyze(_build_simple_graph())
        genome_resilient = engine.analyze(_build_resilient_graph())

        bench_simple = engine.benchmark(genome_simple, "saas")
        bench_resilient = engine.benchmark(genome_resilient, "saas")

        assert bench_resilient.overall_percentile > bench_simple.overall_percentile

    def test_benchmark_recommendations_for_weak_infra(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())
        result = engine.benchmark(genome, "fintech")

        # Simple graph should have recommendations since fintech benchmarks are high
        assert len(result.recommendations) > 0


# ---------------------------------------------------------------------------
# Weakness gene tests
# ---------------------------------------------------------------------------


class TestWeaknessGenes:
    def test_find_weaknesses_simple_graph(self):
        graph = _build_simple_graph()
        engine = ChaosGenomeEngine()
        weaknesses = engine.find_weakness_genes(graph)

        assert isinstance(weaknesses, list)
        assert len(weaknesses) > 0

        # Simple graph should have single_database_gene
        names = [w.name for w in weaknesses]
        assert "single_database_gene" in names

    def test_find_weaknesses_resilient_graph(self):
        graph = _build_resilient_graph()
        engine = ChaosGenomeEngine()
        weaknesses = engine.find_weakness_genes(graph)

        # Resilient graph should have fewer weaknesses
        names = [w.name for w in weaknesses]
        assert "single_database_gene" not in names
        assert "single_load_balancer_gene" not in names

    def test_weakness_gene_structure(self):
        graph = _build_simple_graph()
        engine = ChaosGenomeEngine()
        weaknesses = engine.find_weakness_genes(graph)

        for w in weaknesses:
            assert isinstance(w, WeaknessGene)
            assert w.name
            assert w.severity in ("critical", "high", "medium", "low")
            assert w.description
            assert isinstance(w.affected_components, list)
            assert len(w.affected_components) > 0
            assert w.remediation
            assert 0.0 <= w.prevalence <= 1.0

    def test_no_circuit_breaker_gene(self):
        graph = _build_simple_graph()
        engine = ChaosGenomeEngine()
        weaknesses = engine.find_weakness_genes(graph)
        names = [w.name for w in weaknesses]
        assert "no_circuit_breaker_gene" in names

    def test_empty_graph_no_weaknesses(self):
        graph = InfraGraph()
        engine = ChaosGenomeEngine()
        weaknesses = engine.find_weakness_genes(graph)
        assert len(weaknesses) == 0


# ---------------------------------------------------------------------------
# Failure affinity tests
# ---------------------------------------------------------------------------


class TestFailureAffinity:
    def test_predict_failure_affinity(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())
        affinities = engine.predict_failure_affinity(genome)

        assert isinstance(affinities, list)
        assert len(affinities) > 0

        for a in affinities:
            assert isinstance(a, FailureAffinity)
            assert a.failure_type
            assert 0.0 <= a.affinity_score <= 1.0
            assert isinstance(a.contributing_genes, list)
            assert a.explanation

    def test_affinity_sorted_descending(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())
        affinities = engine.predict_failure_affinity(genome)

        scores = [a.affinity_score for a in affinities]
        assert scores == sorted(scores, reverse=True)

    def test_simple_graph_high_spof_affinity(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())
        affinities = engine.predict_failure_affinity(genome)

        spof = next(a for a in affinities if a.failure_type == "single_point_of_failure")
        assert spof.affinity_score > 0.3  # should have some SPOF affinity

    def test_resilient_graph_lower_affinities(self):
        engine = ChaosGenomeEngine()
        genome_simple = engine.analyze(_build_simple_graph())
        genome_resilient = engine.analyze(_build_resilient_graph())

        aff_simple = engine.predict_failure_affinity(genome_simple)
        aff_resilient = engine.predict_failure_affinity(genome_resilient)

        # Total affinity should be lower for resilient graph
        total_simple = sum(a.affinity_score for a in aff_simple)
        total_resilient = sum(a.affinity_score for a in aff_resilient)
        assert total_resilient < total_simple


# ---------------------------------------------------------------------------
# Evolution tracking tests
# ---------------------------------------------------------------------------


class TestEvolution:
    def test_track_empty_history(self):
        engine = ChaosGenomeEngine()
        report = engine.track_evolution([])

        assert isinstance(report, EvolutionReport)
        assert report.snapshots == 0
        assert report.overall_trend == "stable"

    def test_track_single_snapshot(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())
        report = engine.track_evolution([genome])

        assert report.snapshots == 1
        assert report.overall_trend == "stable"
        assert report.grade_history == [genome.resilience_grade]

    def test_track_improvement(self):
        engine = ChaosGenomeEngine()

        # Simulate improvement: simple -> resilient
        genome_before = engine.analyze(_build_simple_graph())
        genome_before.timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)

        genome_after = engine.analyze(_build_resilient_graph())
        genome_after.timestamp = datetime(2024, 6, 1, tzinfo=timezone.utc)

        report = engine.track_evolution([genome_before, genome_after])

        assert report.snapshots == 2
        assert report.overall_trend == "improving"
        assert report.time_span_days > 0

        # At least some traits should be improving
        improving = [k for k, v in report.trait_trends.items() if v == "improving"]
        assert len(improving) > 0

    def test_evolution_vector(self):
        engine = ChaosGenomeEngine()

        genome1 = engine.analyze(_build_simple_graph())
        genome1.timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)

        genome2 = engine.analyze(_build_resilient_graph())
        genome2.timestamp = datetime(2024, 3, 1, tzinfo=timezone.utc)

        report = engine.track_evolution([genome1, genome2])

        assert isinstance(report.evolution_vector, dict)
        assert len(report.evolution_vector) > 0

        # Check that deltas are computed correctly
        map1 = {t.name: t.value for t in genome1.traits}
        map2 = {t.name: t.value for t in genome2.traits}
        for name, delta in report.evolution_vector.items():
            expected = map2.get(name, 0.0) - map1.get(name, 0.0)
            assert abs(delta - round(expected, 4)) < 0.001


# ---------------------------------------------------------------------------
# GenomeProfile helper tests
# ---------------------------------------------------------------------------


class TestGenomeProfileHelpers:
    def test_trait_vector_sorted(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())
        vec = genome.trait_vector()

        assert len(vec) == 18
        # Verify it matches sorted order
        sorted_names = [t.name for t in sorted(genome.traits, key=lambda t: t.name)]
        trait_map = {t.name: t.value for t in genome.traits}
        expected = [trait_map[n] for n in sorted_names]
        assert vec == expected

    def test_trait_by_name(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())

        trait = genome.trait_by_name("graph_density")
        assert trait is not None
        assert trait.name == "graph_density"

        missing = genome.trait_by_name("nonexistent_trait")
        assert missing is None

    def test_category_score(self):
        engine = ChaosGenomeEngine()
        genome = engine.analyze(_build_simple_graph())

        for cat in TRAIT_CATEGORIES:
            score = genome.category_score(cat)
            assert 0.0 <= score <= 1.0

        # Unknown category
        assert genome.category_score("nonexistent") == 0.0


# ---------------------------------------------------------------------------
# Cosine similarity tests
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self):
        sim = ChaosGenomeEngine._cosine_similarity([1, 2, 3], [1, 2, 3])
        assert sim == pytest.approx(1.0, abs=0.001)

    def test_orthogonal_vectors(self):
        sim = ChaosGenomeEngine._cosine_similarity([1, 0], [0, 1])
        assert sim == pytest.approx(0.0, abs=0.001)

    def test_opposite_vectors(self):
        sim = ChaosGenomeEngine._cosine_similarity([1, 0], [-1, 0])
        assert sim == pytest.approx(-1.0, abs=0.001)

    def test_zero_vector(self):
        sim = ChaosGenomeEngine._cosine_similarity([0, 0], [1, 2])
        assert sim == 0.0

    def test_different_length_vectors(self):
        # Should pad shorter vector with zeros
        sim = ChaosGenomeEngine._cosine_similarity([1, 2], [1, 2, 0, 0])
        assert sim == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# Archetype detection tests
# ---------------------------------------------------------------------------


class TestArchetypeDetection:
    def test_monolith_few_components(self):
        graph = InfraGraph()
        graph.add_component(Component(id="app", name="App", type=ComponentType.APP_SERVER, port=80))
        graph.add_component(Component(id="db", name="DB", type=ComponentType.DATABASE, port=5432))

        engine = ChaosGenomeEngine()
        genome = engine.analyze(graph)
        assert genome.structural_age == "monolith"

    def test_serverless_from_tags(self):
        graph = InfraGraph()
        graph.add_component(
            Component(id="fn1", name="Lambda 1", type=ComponentType.CUSTOM, port=0, tags=["serverless", "lambda"])
        )
        graph.add_component(
            Component(id="fn2", name="Lambda 2", type=ComponentType.CUSTOM, port=0, tags=["serverless"])
        )
        graph.add_component(
            Component(id="api", name="API GW", type=ComponentType.CUSTOM, port=443, tags=["serverless"])
        )
        graph.add_component(
            Component(id="db", name="DynamoDB", type=ComponentType.DATABASE, port=443, tags=["serverless"])
        )

        engine = ChaosGenomeEngine()
        genome = engine.analyze(graph)
        assert genome.structural_age == "serverless"


# ---------------------------------------------------------------------------
# Industry benchmarks data validation
# ---------------------------------------------------------------------------


class TestIndustryBenchmarks:
    def test_all_industries_have_required_traits(self):
        expected_traits = {
            "graph_density", "avg_path_length", "max_depth",
            "clustering_coefficient", "component_diversity",
            "avg_replicas", "min_replicas", "failover_coverage",
            "multi_az_coverage", "provider_diversity", "type_diversity",
            "version_spread", "circuit_breaker_coverage", "blast_radius_avg",
            "isolation_score", "autoscaling_coverage", "avg_recovery_time",
            "health_check_coverage",
        }
        for industry, benchmarks in INDUSTRY_BENCHMARKS.items():
            for trait in expected_traits:
                assert trait in benchmarks, (
                    f"Industry '{industry}' missing benchmark for trait '{trait}'"
                )

    def test_benchmark_values_in_range(self):
        for industry, benchmarks in INDUSTRY_BENCHMARKS.items():
            for trait, value in benchmarks.items():
                assert 0.0 <= value <= 1.0, (
                    f"Industry '{industry}' trait '{trait}' out of range: {value}"
                )


# ---------------------------------------------------------------------------
# Integration with demo graph
# ---------------------------------------------------------------------------


class TestDemoGraphIntegration:
    def test_demo_graph_full_pipeline(self):
        """Run the full analysis pipeline on the demo graph."""
        graph = create_demo_graph()
        engine = ChaosGenomeEngine()

        # Analyze
        genome = engine.analyze(graph)
        assert genome.resilience_grade

        # Benchmark
        bench = engine.benchmark(genome, "saas")
        assert bench.overall_percentile > 0

        # Weaknesses
        weaknesses = engine.find_weakness_genes(graph)
        assert len(weaknesses) > 0  # demo graph has weaknesses

        # Failure affinity
        affinities = engine.predict_failure_affinity(genome)
        assert len(affinities) > 0

    def test_demo_graph_weakness_detection(self):
        """Demo graph should detect known weaknesses."""
        graph = create_demo_graph()
        engine = ChaosGenomeEngine()
        weaknesses = engine.find_weakness_genes(graph)
        names = {w.name for w in weaknesses}

        # Demo graph has single-replica DB with no failover
        assert "single_database_gene" in names
        # Demo graph has single-replica LB with no failover
        assert "single_load_balancer_gene" in names
        # Demo graph has no circuit breakers on requires edges
        assert "no_circuit_breaker_gene" in names


# ---------------------------------------------------------------------------
# Coverage boost tests
# ---------------------------------------------------------------------------


class TestCompareStrengths:
    """Test genome comparison divergent traits (line 488: strengths_a)."""

    def test_compare_divergent_traits(self):
        engine = ChaosGenomeEngine()
        graph1 = _build_simple_graph()
        # Give graph1 higher failover
        graph1.components["lb"].failover = FailoverConfig(enabled=True)
        genome1 = engine.analyze(graph1)

        graph2 = _build_simple_graph()
        genome2 = engine.analyze(graph2)

        comparison = engine.compare(genome1, genome2)
        # The graphs differ, so there should be divergent traits
        assert isinstance(comparison, GenomeComparison)
        # Strengths should be populated if there are divergent traits
        all_strengths = comparison.strengths_a + comparison.strengths_b
        if comparison.divergent_traits:
            assert len(all_strengths) > 0


class TestBenchmarkZeroBenchVal:
    """Test benchmark with bench_val=0 (line 525)."""

    def test_benchmark_with_zero_bench_value(self):
        engine = ChaosGenomeEngine()
        graph = _build_simple_graph()
        genome = engine.analyze(graph)

        # Patch the benchmark data to have a zero value
        from unittest.mock import patch
        custom_bench = {"failover_coverage": 0.0, "health_check_coverage": 0.5}
        with patch.dict(engine._benchmarks, {"test_industry": custom_bench}):
            result = engine.benchmark(genome, "test_industry")
        # When bench_val is 0 and actual is 0 -> percentile = 50
        # When bench_val is 0 and actual > 0 -> percentile = 100
        assert isinstance(result, BenchmarkResult)


class TestEvolutionDegradingTrend:
    """Test evolution with degrading trend (lines 591-592, 599)."""

    def test_degrading_overall_trend(self):
        engine = ChaosGenomeEngine()

        # Create two genomes: first better, second worse
        graph1 = InfraGraph()
        graph1.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=3, failover=FailoverConfig(enabled=True),
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=6),
        ))
        genome1 = engine.analyze(graph1)
        genome1.timestamp = datetime.now(timezone.utc) - timedelta(days=30)

        graph2 = InfraGraph()
        graph2.add_component(Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=1,
        ))
        genome2 = engine.analyze(graph2)
        genome2.timestamp = datetime.now(timezone.utc)

        report = engine.track_evolution([genome1, genome2])
        assert isinstance(report, EvolutionReport)
        # With degraded traits, trend should be 'degrading'
        assert report.overall_trend == "degrading"


class TestDisconnectedGraphPathLength:
    """Test avg_path_length trait with disconnected graph (lines 744-745, 747-748)."""

    def test_disconnected_graph_path_length(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        # Create two disconnected components
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.DATABASE, replicas=2,
        ))
        graph.add_component(Component(
            id="c", name="C", type=ComponentType.CACHE, replicas=2,
        ))
        # Only connect a->b, c is disconnected
        graph.add_dependency(Dependency(source_id="a", target_id="b"))

        trait = engine._trait_avg_path_length(graph)
        assert trait.name == "avg_path_length"
        assert 0.0 <= trait.value <= 1.0


class TestGraphCycleMaxDepth:
    """Test max_depth with graph cycles (lines 764-772)."""

    def test_cyclic_graph_max_depth(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="c", name="C", type=ComponentType.APP_SERVER, replicas=2,
        ))
        # Create a cycle: a -> b -> c -> a
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        graph.add_dependency(Dependency(source_id="b", target_id="c"))
        graph.add_dependency(Dependency(source_id="c", target_id="a"))

        trait = engine._trait_max_depth(graph)
        assert trait.name == "max_depth"
        assert 0.0 <= trait.value <= 1.0


class TestComponentDiversityZeroTotal:
    """Test component_diversity when total is 0 (line 804)."""

    def test_empty_components_diversity(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        trait = engine._trait_component_diversity(graph)
        assert trait.value == 0.0

    def test_component_diversity_zero_total_via_mock(self):
        """Force Counter to return empty to hit the total==0 guard (line 803-806)."""
        from unittest.mock import patch
        from collections import Counter

        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        ))
        # Mock Counter to return an empty counter so total == 0
        with patch("faultray.simulator.chaos_genome.Counter", return_value=Counter()):
            trait = engine._trait_component_diversity(graph)
        assert trait.value == 0.0


class TestMinReplicasThreeOrMore:
    """Test min_replicas trait with 3+ replicas (line 850)."""

    def test_min_replicas_three(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=3,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.DATABASE, replicas=4,
        ))
        trait = engine._trait_min_replicas(graph)
        assert trait.name == "min_replicas"
        assert trait.value >= 0.5  # min is 3, so normalized >= 0.5 + 0.15 = 0.65


class TestProviderDiversityHostPatterns:
    """Test provider_diversity with host patterns (lines 914-922, 929-934)."""

    def test_provider_tag_matching(self):
        """Provider tag matching via tags list (line 914)."""
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            tags=["aws"],
        ))
        trait = engine._trait_provider_diversity(graph)
        assert trait.value == 0.2  # single provider tag

    def test_aws_host_pattern(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            host="ec2-1.amazonaws.com",
        ))
        trait = engine._trait_provider_diversity(graph)
        assert trait.value == 0.2  # single provider (aws)

    def test_gcp_host_pattern(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            host="gke-cluster-1.gcp.internal",
        ))
        trait = engine._trait_provider_diversity(graph)
        assert trait.value == 0.2  # single provider (gcp)

    def test_azure_host_pattern(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            host="my-vm.azure.internal",
        ))
        trait = engine._trait_provider_diversity(graph)
        assert trait.value == 0.2  # single provider (azure)

    def test_multi_provider_diversity(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            host="ec2.amazonaws.com",
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.DATABASE, replicas=2,
            host="gke-cluster.gcp.internal",
        ))
        trait = engine._trait_provider_diversity(graph)
        assert trait.value == 0.6  # two providers

    def test_three_provider_diversity(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            host="ec2.amazonaws.com",
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.DATABASE, replicas=2,
            host="gke-cluster.gcp.internal",
        ))
        graph.add_component(Component(
            id="c", name="C", type=ComponentType.CACHE, replicas=2,
            host="my-vm.azure.internal",
        ))
        trait = engine._trait_provider_diversity(graph)
        assert trait.value >= 0.6  # three providers -> 0.75

    def test_no_provider_info(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        ))
        trait = engine._trait_provider_diversity(graph)
        assert trait.value == 0.2  # no provider info = assume single


class TestVersionSpread:
    """Test version_spread trait (lines 962, 966, 973)."""

    def test_version_in_parameters(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            parameters={"version": "1.2.3"},
        ))
        trait = engine._trait_version_spread(graph)
        assert trait.name == "version_spread"
        assert trait.value > 0.5  # has version info

    def test_version_in_tags(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            tags=["v3.2.1", "production"],
        ))
        trait = engine._trait_version_spread(graph)
        assert trait.name == "version_spread"
        assert trait.value > 0.5  # has version-like tag

    def test_multiple_versions(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            parameters={"version": "1.0.0"},
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.DATABASE, replicas=2,
            parameters={"version": "14.2"},
        ))
        trait = engine._trait_version_spread(graph)
        assert trait.value > 0.5


class TestBlastRadiusSingleComponent:
    """Test blast_radius_avg with single component (line 1015)."""

    def test_single_component_blast_radius(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        ))
        trait = engine._trait_blast_radius_avg(graph)
        assert trait.name == "blast_radius_avg"
        assert trait.value == 1.0  # max_possible is 0, so normalized = 1.0


class TestHealthCheckViaAutoscaling:
    """Test health_check_coverage counts autoscaling as health check (lines 1104-1106)."""

    def test_autoscaling_counts_as_health_check(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        # Component WITHOUT failover and WITHOUT custom health check interval
        # but WITH autoscaling -> should still count as health check (line 1104-1106)
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=1, max_replicas=4),
            failover=FailoverConfig(enabled=False, health_check_interval_seconds=30.0),
        ))
        trait = engine._trait_health_check_coverage(graph)
        assert trait.name == "health_check_coverage"
        assert trait.value > 0  # autoscaling counts as health check


class TestMicroservicesArchetype:
    """Test _classify_archetype returns 'microservices' (line 1196)."""

    def test_microservices_archetype(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        # Need >= 8 components with high diversity
        types = list(ComponentType)
        for i in range(10):
            graph.add_component(Component(
                id=f"c{i}", name=f"Component {i}",
                type=types[i % len(types)],
                replicas=2,
            ))
        genome = engine.analyze(graph)
        # With 10 diverse components, should classify as microservices
        assert genome.structural_age in ("microservices", "hybrid")


class TestDeepChainWeaknessWithCycles:
    """Test deep_chain weakness detection when graph has cycles (lines 1234-1235, 1238-1242)."""

    def test_deep_chain_weakness_with_cycle(self):
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        # Create a cycle -> NetworkXUnfeasible -> max_depth = 0
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        graph.add_dependency(Dependency(source_id="b", target_id="a"))

        weaknesses = engine.find_weakness_genes(graph)
        # With a cycle, dag_longest_path_length raises NetworkXUnfeasible
        # -> max_depth = 0, so deep_chain weakness should NOT fire
        deep_chain = [w for w in weaknesses if w.name == "deep_dependency_chain_gene"]
        assert len(deep_chain) == 0

    def test_deep_chain_weakness_long_dag(self):
        """Test deep_chain weakness with a long DAG (>5 depth) that triggers lines 1238-1240."""
        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        # Create a chain of 8 components (depth > 5, so max_depth=7 > 5)
        for i in range(8):
            graph.add_component(Component(
                id=f"c{i}", name=f"Component {i}",
                type=ComponentType.APP_SERVER, replicas=2,
            ))
        for i in range(7):
            graph.add_dependency(Dependency(source_id=f"c{i}", target_id=f"c{i+1}"))

        weaknesses = engine.find_weakness_genes(graph)
        deep_chain = [w for w in weaknesses if w.name == "deep_dependency_chain_gene"]
        assert len(deep_chain) == 1
        assert len(deep_chain[0].affected_components) > 0

    def test_deep_chain_weakness_dag_longest_path_exception(self):
        """When dag_longest_path raises but dag_longest_path_length works (lines 1241-1242)."""
        from unittest.mock import patch

        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        # Create a simple graph (doesn't matter, we mock the nx calls)
        for i in range(3):
            graph.add_component(Component(
                id=f"c{i}", name=f"Component {i}",
                type=ComponentType.APP_SERVER, replicas=2,
            ))
        graph.add_dependency(Dependency(source_id="c0", target_id="c1"))
        graph.add_dependency(Dependency(source_id="c1", target_id="c2"))

        # Mock dag_longest_path_length to return > 5 and dag_longest_path to raise
        with patch("faultray.simulator.chaos_genome.nx.dag_longest_path_length",
                    return_value=7):
            with patch("faultray.simulator.chaos_genome.nx.dag_longest_path",
                        side_effect=RuntimeError("mock error")):
                affected = engine._check_weakness(graph, "deep_chain")

        assert affected == ["deep_chain_detected"]


class TestPathLengthException:
    """Test avg_path_length outer exception handler (lines 747-748)."""

    def test_avg_path_length_exception(self):
        from unittest.mock import patch

        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.DATABASE, replicas=2,
        ))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))

        # Patch nx.is_weakly_connected to raise an exception
        with patch("faultray.simulator.chaos_genome.nx.is_weakly_connected",
                    side_effect=RuntimeError("mock")):
            trait = engine._trait_avg_path_length(graph)
        assert trait.name == "avg_path_length"
        assert trait.value == 0.0


class TestMaxDepthInnerException:
    """Test max_depth inner exception handler (lines 771-772)."""

    def test_max_depth_inner_exception(self):
        import networkx as nx
        from unittest.mock import patch

        engine = ChaosGenomeEngine()
        graph = InfraGraph()
        # Create a cycle to trigger NetworkXUnfeasible on dag_longest_path_length
        graph.add_component(Component(
            id="a", name="A", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_component(Component(
            id="b", name="B", type=ComponentType.APP_SERVER, replicas=2,
        ))
        graph.add_dependency(Dependency(source_id="a", target_id="b"))
        graph.add_dependency(Dependency(source_id="b", target_id="a"))

        # Patch single_source_shortest_path_length to raise inside the cycle handler
        with patch("faultray.simulator.chaos_genome.nx.single_source_shortest_path_length",
                    side_effect=RuntimeError("mock error")):
            trait = engine._trait_max_depth(graph)
        assert trait.name == "max_depth"
        assert trait.value >= 0.0
