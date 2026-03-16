"""Multi-Environment Resilience Comparison.

Compare resilience metrics across multiple infrastructure environments
(dev, staging, production) or across multiple microservices/teams.

Answers:
- "Is staging as resilient as production?"
- "Which service has the weakest resilience?"
- "Are all environments meeting the same standards?"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EnvironmentProfile:
    """Resilience profile for a single environment."""

    name: str  # e.g., "production", "staging", "dev"
    yaml_path: str
    graph: InfraGraph
    resilience_score: float
    component_count: int
    spof_count: int
    critical_findings: int
    availability_estimate: float
    genome_hash: str | None


@dataclass
class EnvironmentDelta:
    """Difference in a single metric between two environments."""

    metric: str
    env_a_name: str
    env_a_value: float
    env_b_name: str
    env_b_value: float
    delta: float
    concern: bool  # True if delta is significant


@dataclass
class ComparisonMatrix:
    """Complete comparison result across all environments."""

    environments: list[EnvironmentProfile] = field(default_factory=list)
    deltas: list[EnvironmentDelta] = field(default_factory=list)
    weakest_environment: str = ""
    strongest_environment: str = ""
    parity_score: float = 0.0  # 0-100, how similar environments are
    recommendations: list[str] = field(default_factory=list)
    matrix_data: dict[str, dict[str, float]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Metric extraction helpers
# ---------------------------------------------------------------------------

def _count_spofs(graph: InfraGraph) -> int:
    """Count single points of failure (replicas == 1 with dependents)."""
    count = 0
    for comp in graph.components.values():
        if comp.replicas <= 1:
            dependents = graph.get_dependents(comp.id)
            if len(dependents) > 0:
                count += 1
    return count


def _average_replicas(graph: InfraGraph) -> float:
    """Average replica count across all components."""
    if not graph.components:
        return 0.0
    total = sum(c.replicas for c in graph.components.values())
    return total / len(graph.components)


def _failover_coverage(graph: InfraGraph) -> float:
    """Percentage of components with failover enabled."""
    if not graph.components:
        return 0.0
    count = sum(1 for c in graph.components.values() if c.failover.enabled)
    return (count / len(graph.components)) * 100.0


def _autoscaling_coverage(graph: InfraGraph) -> float:
    """Percentage of components with autoscaling enabled."""
    if not graph.components:
        return 0.0
    count = sum(1 for c in graph.components.values() if c.autoscaling.enabled)
    return (count / len(graph.components)) * 100.0


def _circuit_breaker_coverage(graph: InfraGraph) -> float:
    """Percentage of dependency edges with circuit breakers enabled."""
    edges = graph.all_dependency_edges()
    if not edges:
        return 100.0  # No dependencies means no risk
    count = sum(1 for e in edges if e.circuit_breaker.enabled)
    return (count / len(edges)) * 100.0


def _max_dependency_depth(graph: InfraGraph) -> int:
    """Maximum depth of the dependency chain."""
    paths = graph.get_critical_paths()
    if not paths:
        return 0
    return len(paths[0])


def _average_blast_radius(graph: InfraGraph) -> float:
    """Average blast radius as percentage of total components."""
    if not graph.components:
        return 0.0
    total = len(graph.components)
    radii: list[float] = []
    for comp_id in graph.components:
        affected = graph.get_all_affected(comp_id)
        radii.append(len(affected) / total * 100.0)
    return sum(radii) / len(radii) if radii else 0.0


def _estimate_availability(graph: InfraGraph) -> float:
    """Rough availability estimate based on resilience score mapping.

    Maps resilience score (0-100) to availability percentage.
    Conservative: score 100 -> 99.99%, score 50 -> 99.5%, score 0 -> 95%.
    """
    score = graph.resilience_score()
    if score >= 95:
        return 99.99
    elif score >= 80:
        # Linear from 99.9 to 99.99
        return 99.9 + (score - 80) * 0.009 / 15.0
    elif score >= 50:
        # Linear from 99.5 to 99.9
        return 99.5 + (score - 50) * 0.4 / 30.0
    else:
        # Linear from 95.0 to 99.5
        return 95.0 + score * 4.5 / 50.0


def _extract_metrics(graph: InfraGraph) -> dict[str, float]:
    """Extract all comparison metrics from a graph."""
    return {
        "resilience_score": graph.resilience_score(),
        "component_count": float(len(graph.components)),
        "spof_count": float(_count_spofs(graph)),
        "average_replicas": _average_replicas(graph),
        "failover_coverage": _failover_coverage(graph),
        "autoscaling_coverage": _autoscaling_coverage(graph),
        "circuit_breaker_coverage": _circuit_breaker_coverage(graph),
        "dependency_depth": float(_max_dependency_depth(graph)),
        "blast_radius_avg": _average_blast_radius(graph),
    }


# ---------------------------------------------------------------------------
# Threshold for concern (percentage difference that triggers a flag)
# ---------------------------------------------------------------------------
_CONCERN_THRESHOLDS: dict[str, float] = {
    "resilience_score": 10.0,
    "component_count": 20.0,
    "spof_count": 1.0,       # absolute difference
    "average_replicas": 0.5,  # absolute difference
    "failover_coverage": 15.0,
    "autoscaling_coverage": 15.0,
    "circuit_breaker_coverage": 15.0,
    "dependency_depth": 2.0,  # absolute difference
    "blast_radius_avg": 10.0,
}

# Metrics where higher is worse (delta sign is inverted for concern)
_HIGHER_IS_WORSE = {"spof_count", "dependency_depth", "blast_radius_avg"}


# ---------------------------------------------------------------------------
# MultiEnvAnalyzer
# ---------------------------------------------------------------------------

class MultiEnvAnalyzer:
    """Compare resilience across multiple infrastructure environments."""

    def compare(self, env_configs: dict[str, Path]) -> ComparisonMatrix:
        """Compare environments from YAML config paths.

        Args:
            env_configs: Mapping of environment name to YAML file path.

        Returns:
            ComparisonMatrix with full comparison results.
        """
        from faultray.model.loader import load_yaml

        envs: dict[str, InfraGraph] = {}
        yaml_paths: dict[str, str] = {}
        for name, path in env_configs.items():
            envs[name] = load_yaml(path)
            yaml_paths[name] = str(path)

        return self._do_compare(envs, yaml_paths)

    def compare_graphs(self, envs: dict[str, InfraGraph]) -> ComparisonMatrix:
        """Compare pre-loaded InfraGraph instances.

        Args:
            envs: Mapping of environment name to InfraGraph.

        Returns:
            ComparisonMatrix with full comparison results.
        """
        yaml_paths = {name: "" for name in envs}
        return self._do_compare(envs, yaml_paths)

    def check_parity(
        self, env_configs: dict[str, Path], tolerance: float = 10.0,
    ) -> bool:
        """Check whether all environments meet the same resilience standards.

        Args:
            env_configs: Mapping of environment name to YAML file path.
            tolerance: Maximum acceptable parity deviation (0-100).

        Returns:
            True if parity_score >= (100 - tolerance).
        """
        matrix = self.compare(env_configs)
        return matrix.parity_score >= (100.0 - tolerance)

    def find_drift_between_envs(
        self, prod: InfraGraph, staging: InfraGraph,
    ) -> list[str]:
        """Find configuration drift between two environments.

        Args:
            prod: Production environment graph.
            staging: Staging environment graph.

        Returns:
            List of human-readable drift descriptions.
        """
        drift: list[str] = []
        prod_ids = set(prod.components.keys())
        staging_ids = set(staging.components.keys())

        # Components in prod but not in staging
        only_prod = prod_ids - staging_ids
        if only_prod:
            drift.append(
                f"Components in prod but missing from staging: "
                f"{', '.join(sorted(only_prod))}"
            )

        # Components in staging but not in prod
        only_staging = staging_ids - prod_ids
        if only_staging:
            drift.append(
                f"Components in staging but missing from prod: "
                f"{', '.join(sorted(only_staging))}"
            )

        # Shared components with different configurations
        shared = prod_ids & staging_ids
        for comp_id in sorted(shared):
            pc = prod.components[comp_id]
            sc = staging.components[comp_id]

            if pc.replicas != sc.replicas:
                drift.append(
                    f"{comp_id}: replica count differs "
                    f"(prod={pc.replicas}, staging={sc.replicas})"
                )

            if pc.failover.enabled != sc.failover.enabled:
                drift.append(
                    f"{comp_id}: failover differs "
                    f"(prod={'enabled' if pc.failover.enabled else 'disabled'}, "
                    f"staging={'enabled' if sc.failover.enabled else 'disabled'})"
                )

            if pc.autoscaling.enabled != sc.autoscaling.enabled:
                drift.append(
                    f"{comp_id}: autoscaling differs "
                    f"(prod={'enabled' if pc.autoscaling.enabled else 'disabled'}, "
                    f"staging={'enabled' if sc.autoscaling.enabled else 'disabled'})"
                )

            if pc.type != sc.type:
                drift.append(
                    f"{comp_id}: component type differs "
                    f"(prod={pc.type.value}, staging={sc.type.value})"
                )

        # Dependency edge differences
        prod_edges = {(e.source_id, e.target_id) for e in prod.all_dependency_edges()}
        staging_edges = {(e.source_id, e.target_id) for e in staging.all_dependency_edges()}

        only_prod_edges = prod_edges - staging_edges
        if only_prod_edges:
            for src, tgt in sorted(only_prod_edges):
                drift.append(f"Dependency {src} -> {tgt} exists in prod but not staging")

        only_staging_edges = staging_edges - prod_edges
        if only_staging_edges:
            for src, tgt in sorted(only_staging_edges):
                drift.append(f"Dependency {src} -> {tgt} exists in staging but not prod")

        return drift

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_compare(
        self,
        envs: dict[str, InfraGraph],
        yaml_paths: dict[str, str],
    ) -> ComparisonMatrix:
        """Core comparison logic."""
        if len(envs) < 2:
            logger.warning("Need at least 2 environments to compare")
            return ComparisonMatrix()

        # Build profiles
        profiles: list[EnvironmentProfile] = []
        all_metrics: dict[str, dict[str, float]] = {}

        for name, graph in envs.items():
            metrics = _extract_metrics(graph)
            all_metrics[name] = metrics

            # Try to get genome hash
            genome_hash = None
            try:
                from faultray.simulator.chaos_genome import ChaosGenomeAnalyzer
                analyzer = ChaosGenomeAnalyzer()
                genome = analyzer.analyze(graph)
                genome_hash = genome.genome_hash
            except Exception:
                pass

            # Count critical findings from simulation
            critical_findings = 0
            try:
                from faultray.simulator.engine import SimulationEngine
                engine = SimulationEngine(graph)
                report = engine.run_all_defaults(
                    include_feed=False, include_plugins=False,
                )
                critical_findings = len(report.critical_findings)
            except Exception:
                logger.debug(
                    "Could not run simulation for %s, using 0 critical findings",
                    name,
                )

            profiles.append(EnvironmentProfile(
                name=name,
                yaml_path=yaml_paths.get(name, ""),
                graph=graph,
                resilience_score=metrics["resilience_score"],
                component_count=int(metrics["component_count"]),
                spof_count=int(metrics["spof_count"]),
                critical_findings=critical_findings,
                availability_estimate=_estimate_availability(graph),
                genome_hash=genome_hash,
            ))

        # Build pairwise deltas
        deltas: list[EnvironmentDelta] = []
        env_names = list(envs.keys())
        for i in range(len(env_names)):
            for j in range(i + 1, len(env_names)):
                a_name = env_names[i]
                b_name = env_names[j]
                for metric_name in all_metrics[a_name]:
                    a_val = all_metrics[a_name][metric_name]
                    b_val = all_metrics[b_name][metric_name]
                    delta_val = b_val - a_val

                    threshold = _CONCERN_THRESHOLDS.get(metric_name, 10.0)
                    concern = abs(delta_val) >= threshold

                    deltas.append(EnvironmentDelta(
                        metric=metric_name,
                        env_a_name=a_name,
                        env_a_value=round(a_val, 2),
                        env_b_name=b_name,
                        env_b_value=round(b_val, 2),
                        delta=round(delta_val, 2),
                        concern=concern,
                    ))

        # Determine weakest/strongest by resilience score
        sorted_profiles = sorted(profiles, key=lambda p: p.resilience_score)
        weakest = sorted_profiles[0].name if sorted_profiles else ""
        strongest = sorted_profiles[-1].name if sorted_profiles else ""

        # Calculate parity score (0-100)
        # Based on how similar the resilience scores are across environments
        parity_score = self._calculate_parity(profiles)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            profiles, deltas, all_metrics,
        )

        return ComparisonMatrix(
            environments=profiles,
            deltas=deltas,
            weakest_environment=weakest,
            strongest_environment=strongest,
            parity_score=round(parity_score, 1),
            recommendations=recommendations,
            matrix_data=all_metrics,
        )

    def _calculate_parity(self, profiles: list[EnvironmentProfile]) -> float:
        """Calculate how similar environments are (0-100).

        100 = identical resilience profiles, 0 = completely different.
        """
        if len(profiles) < 2:
            return 100.0

        scores = [p.resilience_score for p in profiles]
        max_score = max(scores)
        min_score = min(scores)

        if max_score == 0:
            return 100.0  # All zero is technically identical

        # Range as percentage of max
        spread = (max_score - min_score) / max(max_score, 1.0) * 100.0
        return max(0.0, 100.0 - spread)

    def _generate_recommendations(
        self,
        profiles: list[EnvironmentProfile],
        deltas: list[EnvironmentDelta],
        all_metrics: dict[str, dict[str, float]],
    ) -> list[str]:
        """Generate actionable recommendations from the comparison."""
        recs: list[str] = []

        # Find the weakest environment
        sorted_profiles = sorted(profiles, key=lambda p: p.resilience_score)
        weakest = sorted_profiles[0]
        strongest = sorted_profiles[-1]

        if weakest.resilience_score < strongest.resilience_score - 15:
            recs.append(
                f"'{weakest.name}' resilience score ({weakest.resilience_score:.1f}) "
                f"is significantly lower than '{strongest.name}' "
                f"({strongest.resilience_score:.1f}). "
                f"Review infrastructure parity."
            )

        # Check for environments with high SPOF count
        for profile in profiles:
            if profile.spof_count > 0:
                recs.append(
                    f"'{profile.name}' has {profile.spof_count} single point(s) "
                    f"of failure. Add replicas or failover to critical components."
                )

        # Check deltas with concerns
        for delta in deltas:
            if not delta.concern:
                continue
            if delta.metric == "failover_coverage":
                lower_env = delta.env_a_name if delta.env_a_value < delta.env_b_value else delta.env_b_name
                recs.append(
                    f"Failover coverage gap: '{lower_env}' has lower failover "
                    f"coverage. Align failover settings across environments."
                )
            elif delta.metric == "autoscaling_coverage":
                lower_env = delta.env_a_name if delta.env_a_value < delta.env_b_value else delta.env_b_name
                recs.append(
                    f"Autoscaling coverage gap: '{lower_env}' has lower "
                    f"autoscaling coverage. Enable autoscaling to match other environments."
                )
            elif delta.metric == "circuit_breaker_coverage":
                lower_env = delta.env_a_name if delta.env_a_value < delta.env_b_value else delta.env_b_name
                recs.append(
                    f"Circuit breaker gap: '{lower_env}' has fewer circuit "
                    f"breakers. Add circuit breakers to prevent cascade failures."
                )

        # Deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for r in recs:
            if r not in seen:
                seen.add(r)
                unique.append(r)

        return unique
