# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Bayesian network model for conditional failure probability.

Computes prior and posterior failure probabilities using the infrastructure
dependency graph.  Uses Bayes' theorem with dependency-type-based impact
factors — no external ML dependencies required.
"""

from __future__ import annotations

from dataclasses import dataclass

from faultray.model.graph import InfraGraph

# Default MTBF (hours) when component has no explicit profile
_DEFAULT_MTBF: dict[str, float] = {
    "app_server": 2160.0,
    "web_server": 2160.0,
    "database": 4320.0,
    "cache": 1440.0,
    "load_balancer": 8760.0,
    "queue": 2160.0,
    "dns": 43800.0,
    "storage": 8760.0,
}

# Impact factors by dependency type
_IMPACT_FACTORS: dict[str, float] = {
    "requires": 0.9,
    "optional": 0.3,
    "async": 0.1,
}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BayesianResult:
    """Bayesian analysis result for a single component."""

    component_id: str
    prior_failure_prob: float  # P(fail) from MTBF/MTTR
    posterior_given_deps: float  # P(fail | dependencies status)
    conditional_impacts: dict[str, float]  # {dep_id: P(this fails | dep fails)}
    most_critical_dependency: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prior_failure_prob(mtbf_hours: float, mttr_minutes: float) -> float:
    """Compute prior failure probability: P(fail) = MTTR / (MTBF + MTTR).

    This represents the steady-state unavailability for a single instance.
    """
    mttr_hours = mttr_minutes / 60.0
    if mtbf_hours <= 0 and mttr_hours <= 0:
        return 0.5
    if mtbf_hours <= 0:
        return 1.0
    if mttr_hours <= 0:
        return 0.0
    return mttr_hours / (mtbf_hours + mttr_hours)


def _impact_factor(dependency_type: str) -> float:
    """Return the impact factor for a given dependency type."""
    return _IMPACT_FACTORS.get(dependency_type, 0.5)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BayesianEngine:
    """Bayesian network for conditional failure probability analysis.

    Computes how the failure of one component affects the probability of
    failure of its dependents, using dependency-type-based impact factors.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._priors: dict[str, float] = {}
        self._compute_priors()

    # Default MTTR (minutes) when component has no explicit profile
    _DEFAULT_MTTR: dict[str, float] = {
        "app_server": 15.0,
        "web_server": 10.0,
        "database": 30.0,
        "cache": 5.0,
        "load_balancer": 10.0,
        "queue": 15.0,
        "dns": 5.0,
        "storage": 30.0,
    }

    def _compute_priors(self) -> None:
        """Compute prior failure probability for each component."""
        for comp in self._graph.components.values():
            mtbf = comp.operational_profile.mtbf_hours
            if mtbf <= 0:
                mtbf = _DEFAULT_MTBF.get(comp.type.value, 2160.0)
            mttr = comp.operational_profile.mttr_minutes
            if mttr <= 0:
                mttr = self._DEFAULT_MTTR.get(comp.type.value, 15.0)

            # Account for replicas: P(all fail) = P(single fail)^replicas
            p_single = _prior_failure_prob(mtbf, mttr)
            replicas = max(comp.replicas, 1)
            self._priors[comp.id] = p_single ** replicas

    def analyze(self) -> list[BayesianResult]:
        """Analyze all components and return Bayesian results.

        For each component, computes:
        - Prior failure probability
        - Conditional impact from each dependency
        - Posterior probability given current dependency status
        - Most critical dependency
        """
        results: list[BayesianResult] = []

        for comp in self._graph.components.values():
            # Get dependencies (things this component depends ON)
            deps = self._graph.get_dependencies(comp.id)
            p_fail = self._priors[comp.id]

            conditional_impacts: dict[str, float] = {}
            # Noisy-OR aggregation: independent dependency effects compose as
            # 1 - ∏(1 - f_i), so N simultaneously-failing dependencies drive
            # the posterior towards 1.0 instead of plateauing at the largest
            # single factor (the previous ``max`` collapse was a known bug
            # that caped posteriors around 0.9 even when every upstream was
            # down).
            non_failure_product = 1.0

            for dep_comp in deps:
                edge = self._graph.get_dependency_edge(comp.id, dep_comp.id)
                if edge is None:
                    continue

                dep_type = edge.dependency_type
                factor = _impact_factor(dep_type)
                p_dep_fail = self._priors.get(dep_comp.id, 0.0)

                # P(this fails | dep fails) = P(this fails) + factor * (1 - P(this fails))
                p_this_given_dep_fail = min(1.0, p_fail + factor * (1.0 - p_fail))
                conditional_impacts[dep_comp.id] = round(p_this_given_dep_fail, 6)

                # Marginal contribution of this dependency to the combined
                # failure effect.  For a DOWN dep the contribution is the
                # full impact factor; otherwise it is attenuated by the
                # dep's own prior failure probability.
                dep_health = self._graph.get_component(dep_comp.id)
                if dep_health and dep_health.health.value == "down":
                    contribution = factor
                else:
                    contribution = factor * p_dep_fail

                # Clamp to [0,1] before the noisy-OR product to stay numerically
                # safe when impact tables are customised.
                contribution = max(0.0, min(1.0, contribution))
                non_failure_product *= (1.0 - contribution)

            combined_dep_effect = 1.0 - non_failure_product

            # Posterior: P(fail | deps) = P(fail) + combined_effect * (1 - P(fail))
            posterior = min(1.0, p_fail + combined_dep_effect * (1.0 - p_fail))

            # Most critical dependency
            if conditional_impacts:
                most_critical = max(
                    conditional_impacts,
                    key=conditional_impacts.get,  # type: ignore[arg-type]
                )
            else:
                most_critical = ""

            results.append(BayesianResult(
                component_id=comp.id,
                prior_failure_prob=p_fail,
                posterior_given_deps=posterior,
                conditional_impacts=conditional_impacts,
                most_critical_dependency=most_critical,
            ))

        # Sort by posterior probability (highest risk first)
        results.sort(key=lambda r: r.posterior_given_deps, reverse=True)
        return results

    def query(
        self,
        evidence: dict[str, str],
    ) -> dict[str, float]:
        """Query posterior failure probabilities given evidence.

        Parameters
        ----------
        evidence:
            Dict mapping component_id -> status ("healthy", "degraded", "down").
            Components not in evidence use their prior probability.

        Returns
        -------
        dict[str, float]
            Updated failure probabilities for all components.
        """
        posteriors: dict[str, float] = {}

        for comp in self._graph.components.values():
            # If this component has direct evidence, use it
            if comp.id in evidence:
                status = evidence[comp.id]
                if status == "down":
                    posteriors[comp.id] = 1.0
                elif status == "degraded":
                    posteriors[comp.id] = min(1.0, self._priors[comp.id] * 5.0)
                else:
                    posteriors[comp.id] = self._priors[comp.id] * 0.1
                continue

            # Compute posterior based on dependency evidence using the same
            # noisy-OR aggregation as analyze() so multiple failing
            # dependencies compound correctly.
            p_fail = self._priors[comp.id]
            deps = self._graph.get_dependencies(comp.id)
            non_failure_product = 1.0

            for dep_comp in deps:
                edge = self._graph.get_dependency_edge(comp.id, dep_comp.id)
                if edge is None:
                    continue

                factor = _impact_factor(edge.dependency_type)

                if dep_comp.id in evidence:
                    dep_status = evidence[dep_comp.id]
                    if dep_status == "down":
                        contribution = factor
                    elif dep_status == "degraded":
                        contribution = factor * 0.5
                    else:
                        contribution = 0.0
                else:
                    p_dep = self._priors.get(dep_comp.id, 0.0)
                    contribution = factor * p_dep

                contribution = max(0.0, min(1.0, contribution))
                non_failure_product *= (1.0 - contribution)

            combined_effect = 1.0 - non_failure_product

            posteriors[comp.id] = round(
                min(1.0, p_fail + combined_effect * (1.0 - p_fail)),
                6,
            )

        return posteriors
