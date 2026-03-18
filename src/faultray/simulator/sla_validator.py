"""SLA Validator - Mathematically prove SLA achievability.

Given an infrastructure topology and SLA target (e.g., 99.99% uptime),
this engine mathematically proves whether the SLA is achievable or not,
using availability theory, reliability engineering math, and Monte Carlo validation.

Key insight: Many organizations commit to SLAs without mathematical basis.
This engine provides proof that an SLA is or isn't achievable.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import timedelta

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Default component availability assumptions
# ---------------------------------------------------------------------------

COMPONENT_AVAILABILITY: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 0.9999,   # 99.99%
    ComponentType.WEB_SERVER: 0.999,       # 99.9%
    ComponentType.APP_SERVER: 0.999,       # 99.9%
    ComponentType.DATABASE: 0.9995,        # 99.95%
    ComponentType.CACHE: 0.999,            # 99.9%
    ComponentType.QUEUE: 0.9999,           # 99.99%
    ComponentType.DNS: 0.99999,            # 99.999%
    ComponentType.STORAGE: 0.99999,        # 99.999%
    ComponentType.EXTERNAL_API: 0.999,     # 99.9%
    ComponentType.CUSTOM: 0.999,           # 99.9%
    ComponentType.AI_AGENT: 0.999,         # 99.9%
    ComponentType.LLM_ENDPOINT: 0.999,     # 99.9%
    ComponentType.TOOL_SERVICE: 0.999,     # 99.9%
    ComponentType.AGENT_ORCHESTRATOR: 0.999, # 99.9%
}

# Default MTBF/MTTR for Monte Carlo (hours)
_DEFAULT_MTBF: dict[str, float] = {
    "load_balancer": 8760.0,
    "web_server": 2160.0,
    "app_server": 2160.0,
    "database": 4320.0,
    "cache": 1440.0,
    "queue": 4320.0,
    "dns": 43800.0,
    "storage": 8760.0,
    "external_api": 2160.0,
    "custom": 2160.0,
    "ai_agent": 2160.0,
    "llm_endpoint": 2160.0,
    "tool_service": 2160.0,
    "agent_orchestrator": 2160.0,
}

_DEFAULT_MTTR: dict[str, float] = {
    "load_balancer": 0.033,
    "web_server": 0.083,
    "app_server": 0.083,
    "database": 0.5,
    "cache": 0.167,
    "queue": 0.25,
    "dns": 0.017,
    "storage": 0.083,
    "external_api": 0.5,
    "custom": 0.5,
    "ai_agent": 0.25,
    "llm_endpoint": 0.167,
    "tool_service": 0.167,
    "agent_orchestrator": 0.25,
}

# Measurement window durations
_WINDOW_SECONDS: dict[str, float] = {
    "monthly": 30.44 * 24 * 3600,
    "quarterly": 91.31 * 24 * 3600,
    "annual": 365.25 * 24 * 3600,
}

SECONDS_PER_YEAR = 365.25 * 24 * 3600


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PenaltyTier:
    """SLA breach penalty tier."""

    threshold: float  # e.g., 99.9 -> if availability below this, penalty applies
    penalty_percent: float  # e.g., 10.0 -> 10% credit
    description: str = ""


@dataclass
class SLATarget:
    """Service Level Agreement target definition."""

    name: str  # e.g., "API Availability"
    target_nines: float  # e.g., 4.0 for 99.99%
    measurement_window: str = "monthly"  # monthly, quarterly, annual
    penalty_tiers: list[PenaltyTier] = field(default_factory=list)

    @property
    def target_availability(self) -> float:
        """Convert nines to availability fraction (e.g., 4.0 -> 0.9999)."""
        return 1.0 - 10.0 ** (-self.target_nines)

    @property
    def target_percent(self) -> float:
        """Target as a percentage (e.g., 99.99)."""
        return self.target_availability * 100.0

    @property
    def allowed_downtime(self) -> timedelta:
        """Maximum allowed downtime within the measurement window."""
        window_seconds = _WINDOW_SECONDS.get(self.measurement_window, _WINDOW_SECONDS["monthly"])
        downtime_seconds = (1.0 - self.target_availability) * window_seconds
        return timedelta(seconds=downtime_seconds)


@dataclass
class SLAImprovement:
    """A suggested improvement to meet an SLA target."""

    component: str
    current_availability: float
    needed_availability: float
    suggestion: str
    cost_estimate: str = "medium"  # low, medium, high


@dataclass
class SLAValidationResult:
    """Complete result of SLA validation."""

    target: SLATarget
    achievable: bool
    calculated_availability: float  # actual estimated availability (fraction)
    confidence_level: float  # 0-1, confidence in this estimate
    gap_nines: float  # difference between target and actual nines
    allowed_downtime: timedelta
    estimated_downtime: timedelta
    bottleneck_components: list[str]
    improvement_needed: list[SLAImprovement]
    proof_method: str  # "analytical", "monte_carlo", "combined"
    mathematical_proof: str  # human-readable explanation
    risk_of_breach: float  # probability of breaching SLA in next period
    expected_penalty_cost: float  # expected $ cost if breach occurs

    @property
    def calculated_nines(self) -> float:
        """Calculated availability expressed as nines."""
        return _to_nines(self.calculated_availability)

    @property
    def calculated_percent(self) -> float:
        """Calculated availability as percentage."""
        return self.calculated_availability * 100.0


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _to_nines(availability: float) -> float:
    """Convert availability (0-1) to nines count."""
    if availability >= 1.0:
        return float("inf")
    if availability <= 0.0:
        return 0.0
    return -math.log10(1.0 - availability)


def _nines_to_availability(nines: float) -> float:
    """Convert nines count to availability fraction."""
    if nines == float("inf"):
        return 1.0
    if nines <= 0.0:
        return 0.0
    return 1.0 - 10.0 ** (-nines)


def _component_base_availability(comp) -> float:
    """Get base availability for a single instance of a component.

    Uses MTBF/MTTR if available, otherwise falls back to type defaults.
    """
    mtbf_hours = comp.operational_profile.mtbf_hours
    mttr_hours = comp.operational_profile.mttr_minutes / 60.0

    if mtbf_hours > 0 and mttr_hours > 0:
        return mtbf_hours / (mtbf_hours + mttr_hours)

    # Fall back to component type defaults
    return COMPONENT_AVAILABILITY.get(comp.type, 0.999)


def _component_effective_availability(comp) -> float:
    """Calculate effective availability considering replicas and failover.

    A_component = 1 - (1 - A_single)^n where n = replicas
    With failover penalty factored in.
    """
    a_single = _component_base_availability(comp)
    replicas = max(comp.replicas, 1)

    # Parallel system availability: A = 1 - (1 - A_single)^n
    a_effective = 1.0 - (1.0 - a_single) ** replicas

    # Failover penalty: during promotion, partial unavailability
    if comp.failover.enabled and replicas > 1:
        mtbf_hours = comp.operational_profile.mtbf_hours
        if mtbf_hours <= 0:
            mtbf_hours = _DEFAULT_MTBF.get(comp.type.value, 2160.0)

        promotion_s = comp.failover.promotion_time_seconds
        detection_s = (
            comp.failover.health_check_interval_seconds
            * comp.failover.failover_threshold
        )
        total_fo_s = promotion_s + detection_s
        fo_events_per_year = (SECONDS_PER_YEAR / 3600.0 / mtbf_hours) * replicas
        fo_downtime_fraction = (fo_events_per_year * total_fo_s) / SECONDS_PER_YEAR
        a_effective *= (1.0 - fo_downtime_fraction)

    return max(0.0, min(1.0, a_effective))


# ---------------------------------------------------------------------------
# SLA Validator Engine
# ---------------------------------------------------------------------------

class SLAValidatorEngine:
    """Engine for mathematically validating SLA achievability."""

    def validate(
        self,
        graph: InfraGraph,
        targets: list[SLATarget],
    ) -> list[SLAValidationResult]:
        """Validate multiple SLA targets against the infrastructure topology.

        Parameters
        ----------
        graph:
            The infrastructure graph to analyze.
        targets:
            List of SLA targets to validate.

        Returns
        -------
        list[SLAValidationResult]
            Validation results for each target.
        """
        return [self.prove_achievability(graph, t.target_nines, t) for t in targets]

    def prove_achievability(
        self,
        graph: InfraGraph,
        target_nines: float,
        target: SLATarget | None = None,
    ) -> SLAValidationResult:
        """Prove whether a target SLA is achievable for the given infrastructure.

        Uses a combined approach:
        1. Analytical calculation of critical path availability
        2. Monte Carlo simulation for confidence interval
        3. Bottleneck identification and improvement suggestions

        Parameters
        ----------
        graph:
            The infrastructure graph.
        target_nines:
            Target availability in nines (e.g., 4.0 for 99.99%).
        target:
            Optional SLATarget with full configuration. If None, a default is created.

        Returns
        -------
        SLAValidationResult
            Complete validation result with proof.
        """
        if target is None:
            target = SLATarget(
                name="System Availability",
                target_nines=target_nines,
            )

        target_avail = _nines_to_availability(target_nines)

        # Step 1: Analytical calculation
        analytical_avail = self.calculate_critical_path_availability(graph)

        # Step 2: Monte Carlo validation
        mc_breach_prob = self.estimate_breach_probability(graph, target)

        # Step 3: Determine confidence level
        # Higher trial count and narrower CI -> higher confidence
        confidence = max(0.0, min(1.0, 1.0 - mc_breach_prob * 0.5))

        # Use analytical result as primary
        calculated_avail = analytical_avail
        calculated_nines = _to_nines(calculated_avail)
        gap = target_nines - calculated_nines

        # Step 4: Identify bottlenecks
        bottlenecks = self._find_bottleneck_components(graph)

        # Step 5: Calculate improvements needed
        improvements = self.find_minimum_changes(graph, target_nines)

        # Step 6: Calculate downtime estimates
        window_seconds = _WINDOW_SECONDS.get(target.measurement_window, _WINDOW_SECONDS["monthly"])
        allowed_dt = timedelta(seconds=(1.0 - target_avail) * window_seconds)
        estimated_dt = timedelta(seconds=(1.0 - calculated_avail) * window_seconds)

        # Step 7: Calculate expected penalty cost
        expected_penalty = self._calculate_expected_penalty(target, mc_breach_prob, graph)

        # Step 8: Build mathematical proof
        proof = self._build_mathematical_proof(
            graph, target, calculated_avail, calculated_nines, gap, bottlenecks,
        )

        achievable = calculated_nines >= target_nines

        return SLAValidationResult(
            target=target,
            achievable=achievable,
            calculated_availability=calculated_avail,
            confidence_level=confidence,
            gap_nines=gap,
            allowed_downtime=allowed_dt,
            estimated_downtime=estimated_dt,
            bottleneck_components=bottlenecks,
            improvement_needed=improvements,
            proof_method="combined",
            mathematical_proof=proof,
            risk_of_breach=mc_breach_prob,
            expected_penalty_cost=expected_penalty,
        )

    def calculate_critical_path_availability(self, graph: InfraGraph) -> float:
        """Calculate system availability based on critical path analysis.

        Algorithm:
        1. For each component, compute effective availability
           (considering replicas and failover).
        2. Find all critical path components (those with 'requires' dependents
           or standalone/leaf nodes).
        3. System availability = product of critical path component availabilities
           (series system model).

        Parameters
        ----------
        graph:
            The infrastructure graph.

        Returns
        -------
        float
            System-level availability as a fraction (0.0-1.0).
        """
        if not graph.components:
            return 0.0

        system_avail = 1.0

        for comp_id, comp in graph.components.items():
            a_comp = _component_effective_availability(comp)

            # Determine if this component is on the critical path
            dependents = graph.get_dependents(comp_id)
            has_requires_dependent = any(
                (edge := graph.get_dependency_edge(d.id, comp_id))
                and edge.dependency_type == "requires"
                for d in dependents
            )

            # Component is critical if it has required dependents or is standalone
            if has_requires_dependent or not dependents:
                system_avail *= a_comp

        return max(0.0, min(1.0, system_avail))

    def estimate_breach_probability(
        self,
        graph: InfraGraph,
        target: SLATarget,
        simulations: int = 10000,
        seed: int = 42,
    ) -> float:
        """Estimate the probability of breaching the SLA via Monte Carlo simulation.

        Runs N simulations with random component failures based on MTBF/MTTR
        distributions and counts how many times the system availability
        falls below the SLA target.

        Parameters
        ----------
        graph:
            The infrastructure graph.
        target:
            The SLA target to check against.
        simulations:
            Number of Monte Carlo trials (default 10,000).
        seed:
            Random seed for reproducibility.

        Returns
        -------
        float
            Probability of SLA breach (0.0-1.0).
        """
        if not graph.components:
            return 1.0

        rng = random.Random(seed)
        target_avail = target.target_availability

        # Pre-compute per-component info
        comp_info = []
        for comp_id, comp in graph.components.items():
            comp_type = comp.type.value
            mtbf_hours = comp.operational_profile.mtbf_hours
            if mtbf_hours <= 0:
                mtbf_hours = _DEFAULT_MTBF.get(comp_type, 2160.0)

            mttr_hours = comp.operational_profile.mttr_minutes / 60.0
            if mttr_hours <= 0:
                mttr_hours = _DEFAULT_MTTR.get(comp_type, 0.5)

            replicas = max(comp.replicas, 1)

            # Critical path check
            dependents = graph.get_dependents(comp_id)
            has_requires = any(
                (edge := graph.get_dependency_edge(d.id, comp_id))
                and edge.dependency_type == "requires"
                for d in dependents
            )
            is_critical = has_requires or not dependents

            comp_info.append({
                "id": comp_id,
                "mtbf_hours": mtbf_hours,
                "mttr_hours": mttr_hours,
                "replicas": replicas,
                "is_critical": is_critical,
            })

        breach_count = 0

        for _ in range(simulations):
            system_avail = 1.0

            for info in comp_info:
                # Sample MTBF from exponential distribution
                sampled_mtbf = rng.expovariate(1.0 / info["mtbf_hours"]) if info["mtbf_hours"] > 0 else 0.0
                sampled_mtbf = max(sampled_mtbf, 1e-6)

                # Sample MTTR from log-normal distribution
                if info["mttr_hours"] > 0:
                    mu = math.log(info["mttr_hours"])
                    sampled_mttr = rng.lognormvariate(mu, 0.5)
                else:
                    sampled_mttr = 1e-9
                sampled_mttr = max(sampled_mttr, 1e-9)

                # Single-instance availability
                a_single = sampled_mtbf / (sampled_mtbf + sampled_mttr)

                # Apply redundancy
                a_tier = 1.0 - (1.0 - a_single) ** info["replicas"]

                # Multiply into system if critical
                if info["is_critical"]:
                    system_avail *= a_tier

            system_avail = max(0.0, min(1.0, system_avail))

            if system_avail < target_avail:
                breach_count += 1

        return breach_count / simulations

    def find_minimum_changes(
        self,
        graph: InfraGraph,
        target_nines: float,
    ) -> list[SLAImprovement]:
        """Determine the minimum changes needed to achieve the target SLA.

        Strategy:
        1. Identify the weakest components (lowest availability)
        2. For each, calculate what availability is needed
        3. Suggest concrete improvements (more replicas, failover, etc.)

        Parameters
        ----------
        graph:
            The infrastructure graph.
        target_nines:
            Target availability in nines.

        Returns
        -------
        list[SLAImprovement]
            List of suggested improvements, ordered by impact.
        """
        if not graph.components:
            return []

        target_avail = _nines_to_availability(target_nines)
        current_avail = self.calculate_critical_path_availability(graph)

        if current_avail >= target_avail:
            return []  # Already meeting the target

        improvements: list[SLAImprovement] = []

        # Get critical path components sorted by availability (weakest first)
        comp_avails = []
        for comp_id, comp in graph.components.items():
            dependents = graph.get_dependents(comp_id)
            has_requires = any(
                (edge := graph.get_dependency_edge(d.id, comp_id))
                and edge.dependency_type == "requires"
                for d in dependents
            )
            is_critical = has_requires or not dependents

            if is_critical:
                a_comp = _component_effective_availability(comp)
                comp_avails.append((comp_id, comp, a_comp))

        # Sort by availability ascending (weakest first)
        comp_avails.sort(key=lambda x: x[2])

        # Calculate how much each component needs to improve
        # system_avail = product(a_i) for all critical components
        # To reach target, we need to increase the weakest components
        remaining_gap = target_avail / current_avail if current_avail > 0 else float("inf")

        for comp_id, comp, a_current in comp_avails:
            if remaining_gap <= 1.0:
                break

            _component_base_availability(comp)

            # Calculate what availability is needed from this component
            # to close the gap
            a_needed = min(a_current * remaining_gap, 0.99999)

            if a_needed <= a_current:
                continue

            # Determine suggestion based on current state
            suggestion, cost = self._suggest_improvement(comp, a_current, a_needed)

            improvements.append(SLAImprovement(
                component=comp_id,
                current_availability=a_current,
                needed_availability=a_needed,
                suggestion=suggestion,
                cost_estimate=cost,
            ))

            # Update remaining gap
            improvement_factor = a_needed / a_current if a_current > 0 else 1.0
            remaining_gap /= improvement_factor

        return improvements

    def _find_bottleneck_components(self, graph: InfraGraph) -> list[str]:
        """Find components that limit system availability the most.

        Returns component IDs sorted by impact on system availability
        (most limiting first).
        """
        if not graph.components:
            return []

        comp_impact: list[tuple[str, float]] = []

        for comp_id, comp in graph.components.items():
            dependents = graph.get_dependents(comp_id)
            has_requires = any(
                (edge := graph.get_dependency_edge(d.id, comp_id))
                and edge.dependency_type == "requires"
                for d in dependents
            )
            is_critical = has_requires or not dependents

            if is_critical:
                a_comp = _component_effective_availability(comp)
                # Impact = how much unavailability this component contributes
                # Lower availability = higher impact
                impact = 1.0 - a_comp
                comp_impact.append((comp_id, impact))

        # Sort by impact descending (most impactful first)
        comp_impact.sort(key=lambda x: x[1], reverse=True)

        return [comp_id for comp_id, _ in comp_impact]

    def _suggest_improvement(
        self, comp, a_current: float, a_needed: float,
    ) -> tuple[str, str]:
        """Generate a concrete improvement suggestion for a component."""
        a_base = _component_base_availability(comp)
        replicas = comp.replicas
        has_failover = comp.failover.enabled

        # Calculate replicas needed to achieve target
        # A_parallel = 1 - (1 - A_base)^n
        # n = log(1 - A_needed) / log(1 - A_base)
        if a_base < 1.0 and a_needed < 1.0:
            needed_replicas = math.ceil(
                math.log(1.0 - a_needed) / math.log(1.0 - a_base)
            )
        else:
            needed_replicas = replicas

        suggestions = []
        cost = "medium"

        if replicas == 1:
            suggestions.append(
                f"Increase replicas from {replicas} to at least {max(needed_replicas, 2)}"
            )
            cost = "medium" if needed_replicas <= 3 else "high"

        elif needed_replicas > replicas:
            suggestions.append(
                f"Increase replicas from {replicas} to {needed_replicas}"
            )
            cost = "medium" if needed_replicas - replicas <= 2 else "high"

        if not has_failover and replicas >= 2:
            suggestions.append("Enable failover for automatic recovery")
            cost = "low"

        if not comp.autoscaling.enabled:
            suggestions.append("Enable autoscaling for dynamic capacity")

        if not suggestions:
            suggestions.append(
                f"Improve single-instance reliability (current: {a_base * 100:.3f}%, "
                f"needed: {a_needed * 100:.4f}%)"
            )
            cost = "high"

        return "; ".join(suggestions), cost

    def _calculate_expected_penalty(
        self,
        target: SLATarget,
        breach_probability: float,
        graph: InfraGraph,
    ) -> float:
        """Calculate expected penalty cost from SLA breaches.

        Expected cost = P(breach) * weighted_average_penalty * monthly_revenue
        """
        if not target.penalty_tiers or breach_probability <= 0:
            return 0.0

        # Use cost profiles to estimate monthly revenue
        monthly_revenue = 0.0
        for comp in graph.components.values():
            if comp.cost_profile.revenue_per_minute > 0:
                monthly_revenue += comp.cost_profile.revenue_per_minute * 60 * 24 * 30.44
            if comp.cost_profile.monthly_contract_value > 0:
                monthly_revenue += comp.cost_profile.monthly_contract_value

        if monthly_revenue <= 0:
            # Default estimate if no cost profile
            return 0.0

        # Calculate weighted penalty (probability of each tier being triggered)
        max_penalty_pct = max(t.penalty_percent for t in target.penalty_tiers)
        expected_cost = breach_probability * (max_penalty_pct / 100.0) * monthly_revenue

        return round(expected_cost, 2)

    def _build_mathematical_proof(
        self,
        graph: InfraGraph,
        target: SLATarget,
        calculated_avail: float,
        calculated_nines: float,
        gap: float,
        bottlenecks: list[str],
    ) -> str:
        """Build a human-readable mathematical proof of SLA achievability."""
        lines = []
        lines.append("=" * 60)
        lines.append(f"SLA VALIDATION PROOF: {target.name}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Target: {target.target_nines:.2f} nines ({target.target_percent:.4f}%)")
        lines.append(f"Window: {target.measurement_window}")
        lines.append(f"Allowed downtime: {target.allowed_downtime}")
        lines.append("")

        # Component analysis
        lines.append("--- Component Availability Analysis ---")
        lines.append("")

        for comp_id, comp in graph.components.items():
            a_base = _component_base_availability(comp)
            a_effective = _component_effective_availability(comp)
            replicas = comp.replicas

            lines.append(f"  {comp_id} ({comp.type.value}):")
            lines.append(f"    Single-instance availability: {a_base * 100:.4f}%")

            if replicas > 1:
                lines.append(f"    Replicas: {replicas}")
                lines.append(f"    Formula: A = 1 - (1 - {a_base:.6f})^{replicas}")
                lines.append(f"           = 1 - ({1.0 - a_base:.6f})^{replicas}")
                lines.append(f"           = {a_effective * 100:.6f}%")
            else:
                lines.append("    Replicas: 1 (no redundancy)")
                lines.append(f"    Effective availability: {a_effective * 100:.4f}%")

            if comp.failover.enabled:
                lines.append(f"    Failover: enabled (promotion: {comp.failover.promotion_time_seconds}s)")

            lines.append(f"    Nines: {_to_nines(a_effective):.2f}")
            lines.append("")

        # System calculation
        lines.append("--- System Availability (Series Model) ---")
        lines.append("")
        lines.append("  A_system = A_1 x A_2 x ... x A_n (critical path components)")

        critical_avails = []
        for comp_id, comp in graph.components.items():
            dependents = graph.get_dependents(comp_id)
            has_requires = any(
                (edge := graph.get_dependency_edge(d.id, comp_id))
                and edge.dependency_type == "requires"
                for d in dependents
            )
            is_critical = has_requires or not dependents
            if is_critical:
                a_eff = _component_effective_availability(comp)
                critical_avails.append((comp_id, a_eff))

        if critical_avails:
            formula_parts = " x ".join(f"{a:.6f}" for _, a in critical_avails)
            lines.append(f"  A_system = {formula_parts}")
            lines.append(f"           = {calculated_avail:.8f}")
            lines.append(f"           = {calculated_avail * 100:.6f}%")
            lines.append(f"           = {calculated_nines:.2f} nines")
        else:
            lines.append("  No critical path components found.")

        lines.append("")

        # Verdict
        lines.append("--- Verdict ---")
        lines.append("")
        if calculated_nines >= target.target_nines:
            lines.append(f"  ACHIEVABLE: {calculated_nines:.2f} nines >= {target.target_nines:.2f} nines (target)")
            margin = calculated_nines - target.target_nines
            lines.append(f"  Safety margin: {margin:.2f} nines")
        else:
            lines.append(f"  NOT ACHIEVABLE: {calculated_nines:.2f} nines < {target.target_nines:.2f} nines (target)")
            lines.append(f"  Gap: {gap:.2f} nines")
            window_s = _WINDOW_SECONDS.get(target.measurement_window, _WINDOW_SECONDS["monthly"])
            target_dt = (1.0 - _nines_to_availability(target.target_nines)) * window_s
            actual_dt = (1.0 - calculated_avail) * window_s
            lines.append(f"  Allowed downtime ({target.measurement_window}): {timedelta(seconds=target_dt)}")
            lines.append(f"  Estimated downtime ({target.measurement_window}): {timedelta(seconds=actual_dt)}")

        lines.append("")

        if bottlenecks:
            lines.append("--- Bottleneck Components ---")
            lines.append("")
            for i, bn in enumerate(bottlenecks[:5], 1):
                comp = graph.get_component(bn)
                if comp:
                    a_eff = _component_effective_availability(comp)
                    lines.append(f"  {i}. {bn}: {a_eff * 100:.4f}% ({_to_nines(a_eff):.2f} nines)")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
