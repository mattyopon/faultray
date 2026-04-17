# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""5-Layer Availability Limit Model — mathematical proof of availability ceiling.

Provides five mathematically distinct availability limits:

Layer 1 (Software Limit):
    The practical ceiling accounting for deployment downtime, human error,
    and configuration drift. Most organizations cannot exceed this.

Layer 2 (Hardware Limit):
    The physical ceiling from component MTBF, MTTR, redundancy factor,
    and failover promotion time. Even with perfect software, hardware
    constraints cap availability here.

Layer 3 (Theoretical Limit):
    The mathematical upper bound assuming perfect software AND accounting
    for irreducible physical noise: network packet loss, GC pauses, and
    kernel scheduling jitter. This is unreachable in practice.

Layer 4 (Operational Limit):
    Based on incident response time, team size, and on-call coverage.
    Captures the human factor: how quickly incidents are detected and
    resolved given the operational team's capabilities.

Layer 5 (External SLA Cascading):
    Product of all external dependency SLAs. If your system depends on
    third-party services, your availability is capped by their combined SLA.
"""

from __future__ import annotations

import math
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

# Default MTTR (hours)
_DEFAULT_MTTR: dict[str, float] = {
    "app_server": 0.083,
    "web_server": 0.083,
    "database": 0.5,
    "cache": 0.167,
    "load_balancer": 0.033,
    "queue": 0.25,
    "dns": 0.017,
    "storage": 0.083,
}


@dataclass
class AvailabilityLayer:
    """Result for a single availability layer."""

    availability: float  # 0.0 - 1.0
    nines: float  # -log10(1 - availability)
    annual_downtime_seconds: float
    description: str
    details: dict[str, float]  # per-component or per-factor breakdown


@dataclass
class ThreeLayerResult:
    """Complete 3-Layer Availability Limit Model result."""

    layer1_software: AvailabilityLayer
    layer2_hardware: AvailabilityLayer
    layer3_theoretical: AvailabilityLayer

    @property
    def summary(self) -> str:
        lines = [
            "3-Layer Availability Limit Model",
            "=" * 50,
            f"  Layer 1 (Software):    {self.layer1_software.nines:.2f} nines "
            f"({self.layer1_software.availability * 100:.6f}%) "
            f"— {self.layer1_software.annual_downtime_seconds:.0f}s/year",
            f"  Layer 2 (Hardware):    {self.layer2_hardware.nines:.2f} nines "
            f"({self.layer2_hardware.availability * 100:.6f}%) "
            f"— {self.layer2_hardware.annual_downtime_seconds:.0f}s/year",
            f"  Layer 3 (Theoretical): {self.layer3_theoretical.nines:.2f} nines "
            f"({self.layer3_theoretical.availability * 100:.6f}%) "
            f"— {self.layer3_theoretical.annual_downtime_seconds:.0f}s/year",
        ]
        return "\n".join(lines)


@dataclass
class FiveLayerResult:
    """Complete 5-Layer Availability Limit Model result."""

    layer1_software: AvailabilityLayer
    layer2_hardware: AvailabilityLayer
    layer3_theoretical: AvailabilityLayer
    layer4_operational: AvailabilityLayer
    layer5_external: AvailabilityLayer

    @property
    def summary(self) -> str:
        lines = [
            "5-Layer Availability Limit Model",
            "=" * 60,
            f"  Layer 1 (Software):     {self.layer1_software.nines:.2f} nines "
            f"({self.layer1_software.availability * 100:.6f}%) "
            f"— {self.layer1_software.annual_downtime_seconds:.0f}s/year",
            f"  Layer 2 (Hardware):     {self.layer2_hardware.nines:.2f} nines "
            f"({self.layer2_hardware.availability * 100:.6f}%) "
            f"— {self.layer2_hardware.annual_downtime_seconds:.0f}s/year",
            f"  Layer 3 (Theoretical):  {self.layer3_theoretical.nines:.2f} nines "
            f"({self.layer3_theoretical.availability * 100:.6f}%) "
            f"— {self.layer3_theoretical.annual_downtime_seconds:.0f}s/year",
            f"  Layer 4 (Operational):  {self.layer4_operational.nines:.2f} nines "
            f"({self.layer4_operational.availability * 100:.6f}%) "
            f"— {self.layer4_operational.annual_downtime_seconds:.0f}s/year",
            f"  Layer 5 (External SLA): {self.layer5_external.nines:.2f} nines "
            f"({self.layer5_external.availability * 100:.6f}%) "
            f"— {self.layer5_external.annual_downtime_seconds:.0f}s/year",
        ]
        return "\n".join(lines)


def _to_nines(availability: float) -> float:
    """Convert availability (0-1) to nines count."""
    if availability >= 1.0:
        return float("inf")
    if availability <= 0.0:
        return 0.0
    return -math.log10(1.0 - availability)


def _annual_downtime(availability: float) -> float:
    """Convert availability to annual downtime in seconds."""
    return (1.0 - availability) * 365.25 * 24 * 3600


def compute_three_layer_model(
    graph: InfraGraph,
    deploys_per_month: float = 8.0,
    human_error_rate: float = 0.001,
    config_drift_rate: float = 0.0005,
) -> ThreeLayerResult:
    """Compute the 3-Layer Availability Limit Model for an infrastructure graph.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyze.
    deploys_per_month:
        Average number of deployments per month (used for Layer 1).
    human_error_rate:
        Probability of a human-caused incident per month (Layer 1).
    config_drift_rate:
        Probability of configuration drift causing degradation per month (Layer 1).
    """
    if not graph.components:
        empty_layer = AvailabilityLayer(
            availability=0.0, nines=0.0, annual_downtime_seconds=365.25 * 24 * 3600,
            description="No components", details={},
        )
        return ThreeLayerResult(empty_layer, empty_layer, empty_layer)

    # =====================================================================
    # Layer 2: Hardware Availability Limit
    # Formula per component:
    #   A_single = MTBF / (MTBF + MTTR)
    #   A_tier = 1 - (1 - A_single)^replicas
    #   If failover: A_tier *= (1 - failover_unavail_fraction)
    # System = product of all tier availabilities
    # =====================================================================
    tier_availabilities: dict[str, float] = {}

    for comp in graph.components.values():
        comp_type = comp.type.value

        # Get MTBF/MTTR
        mtbf_hours = comp.operational_profile.mtbf_hours
        if mtbf_hours <= 0:
            mtbf_hours = _DEFAULT_MTBF.get(comp_type, 2160.0)

        mttr_hours = comp.operational_profile.mttr_minutes / 60.0
        if mttr_hours <= 0:
            mttr_hours = _DEFAULT_MTTR.get(comp_type, 0.5)

        # Single-instance availability
        a_single = mtbf_hours / (mtbf_hours + mttr_hours)

        # Redundancy: parallel reliability model
        # P(all fail) = (1 - A_single)^replicas
        replicas = max(comp.replicas, 1)
        a_tier = 1.0 - (1.0 - a_single) ** replicas

        # Failover penalty: during promotion, service is partially unavailable
        if comp.failover.enabled:
            promotion_s = comp.failover.promotion_time_seconds
            detection_s = (comp.failover.health_check_interval_seconds
                           * comp.failover.failover_threshold)
            total_fo_s = promotion_s + detection_s
            # Failover events per year ≈ 365*24 / MTBF_hours per instance * replicas
            fo_events_per_year = (365.25 * 24.0 / mtbf_hours) * replicas
            # Each event causes total_fo_s of partial unavailability
            fo_downtime_fraction = (fo_events_per_year * total_fo_s) / (365.25 * 24 * 3600)
            a_tier = a_tier * (1.0 - fo_downtime_fraction)

        tier_availabilities[comp.id] = max(0.0, min(1.0, a_tier))

    # System availability = product of all critical-path component availabilities
    # Use weighted product: `requires` deps are multiplicative, `optional` are not
    system_hw = 1.0
    for comp_id, a_tier in tier_availabilities.items():
        # Weight by number of `requires` dependents (more critical = more impact)
        comp_or_none = graph.get_component(comp_id)
        if comp_or_none is None:
            continue
        dependents = graph.get_dependents(comp_id)
        has_requires_dependent = any(
            (edge := graph.get_dependency_edge(d.id, comp_id)) and edge.dependency_type == "requires"
            for d in dependents
        )
        if has_requires_dependent or not dependents:
            # Critical path component or leaf: multiplicative
            system_hw *= a_tier

    system_hw = max(0.0, min(1.0, system_hw))

    layer2 = AvailabilityLayer(
        availability=system_hw,
        nines=_to_nines(system_hw),
        annual_downtime_seconds=_annual_downtime(system_hw),
        description="Hardware limit: MTBF × redundancy × failover",
        details=tier_availabilities,
    )

    # =====================================================================
    # Layer 1: Software Availability Limit
    # Adds deployment downtime, human error, and config drift on top of HW
    # =====================================================================
    seconds_per_month = 30.44 * 24 * 3600

    # Average deploy downtime per component
    total_deploy_downtime = 0.0
    deploy_count = 0
    for comp in graph.components.values():
        dt = comp.operational_profile.deploy_downtime_seconds
        if dt > 0:
            total_deploy_downtime += dt
            deploy_count += 1

    # Deploy unavailability fraction
    if deploy_count > 0:
        avg_deploy_downtime = total_deploy_downtime / deploy_count
    else:
        avg_deploy_downtime = 30.0  # default 30s

    deploy_unavail = (deploys_per_month * avg_deploy_downtime) / seconds_per_month

    # Combined software failure rate
    sw_unavail = deploy_unavail + human_error_rate + config_drift_rate
    sw_availability = max(0.0, 1.0 - sw_unavail)

    # Layer 1 = min(software, hardware) — can't exceed hardware limit
    system_sw = min(sw_availability, system_hw)
    # Clamp to [0, 1] (B3-1: all layer availabilities are clamped)
    system_sw = max(0.0, min(1.0, system_sw))

    layer1 = AvailabilityLayer(
        availability=system_sw,
        nines=_to_nines(system_sw),
        annual_downtime_seconds=_annual_downtime(system_sw),
        description="Software limit: deployment + human error + config drift",
        details={
            "deploy_unavail": deploy_unavail,
            "human_error_rate": human_error_rate,
            "config_drift_rate": config_drift_rate,
            "combined_sw_unavail": sw_unavail,
        },
    )

    # =====================================================================
    # Layer 3: Theoretical Limit
    # Perfect software (zero deploy downtime, zero human error) but
    # irreducible physical noise: packet loss + GC pauses + jitter
    # =====================================================================
    network_penalty = 0.0
    runtime_penalty = 0.0
    comp_count = len(graph.components)

    for comp in graph.components.values():
        network_penalty += comp.network.packet_loss_rate
        if comp.runtime_jitter.gc_pause_frequency > 0:
            gc_fraction = (
                comp.runtime_jitter.gc_pause_ms / 1000.0
                * comp.runtime_jitter.gc_pause_frequency
            )
            runtime_penalty += gc_fraction

    # Average across components
    if comp_count > 0:
        network_penalty /= comp_count
        runtime_penalty /= comp_count

    # Layer 3 (Runtime Noise Floor) is independent of Layer 2:
    # A_L3 = (1 - p_loss) * (1 - f_gc)
    # This models the irreducible runtime noise ceiling as a standalone bound,
    # not a further reduction of the hardware limit.  The previous formula
    # (system_hw * ...) made L3 ≤ L2 by construction, which caused min(L2, L3)
    # to always equal L3, rendering L2 redundant in the cross-layer min.
    system_theoretical = (1.0 - network_penalty) * (1.0 - runtime_penalty)
    # Clamp to [0, 1] (3-1: all layer availabilities are clamped)
    system_theoretical = max(0.0, min(1.0, system_theoretical))

    layer3 = AvailabilityLayer(
        availability=system_theoretical,
        nines=_to_nines(system_theoretical),
        annual_downtime_seconds=_annual_downtime(system_theoretical),
        description="Runtime noise floor: network packet loss + GC pauses (independent of hardware)",
        details={
            "avg_packet_loss_rate": network_penalty,
            "avg_gc_fraction": runtime_penalty,
        },
    )

    return ThreeLayerResult(
        layer1_software=layer1,
        layer2_hardware=layer2,
        layer3_theoretical=layer3,
    )


def compute_five_layer_model(
    graph: InfraGraph,
    deploys_per_month: float = 8.0,
    human_error_rate: float = 0.001,
    config_drift_rate: float = 0.0005,
    incidents_per_year: float = 12.0,
    mean_response_minutes: float = 30.0,
    oncall_coverage_percent: float = 100.0,
) -> FiveLayerResult:
    """Compute the 5-Layer Availability Limit Model for an infrastructure graph.

    Extends the 3-Layer model with:

    Layer 4 (Operational Limit):
        ``operational_avail = 1 - (incident_rate * mean_response_time / 8760_hours)``
        Adjusted by on-call coverage (24/7 = 100%, business hours only = 33%).

    Layer 5 (External SLA Cascading):
        ``external_avail = product(provider_sla[i])`` for each external-API
        component or any component with an ``external_sla`` config.

    Parameters
    ----------
    graph:
        The infrastructure graph to analyze.
    deploys_per_month:
        Average number of deployments per month (Layer 1).
    human_error_rate:
        Probability of a human-caused incident per month (Layer 1).
    config_drift_rate:
        Probability of configuration drift causing degradation per month (Layer 1).
    incidents_per_year:
        Expected number of incidents per year (Layer 4).
    mean_response_minutes:
        Mean time from incident detection to resolution in minutes (Layer 4).
    oncall_coverage_percent:
        Percentage of time an on-call engineer is available.
        100.0 = 24/7 coverage, 33.0 = business hours only (Layer 4).
    """
    # Reuse the 3-layer computation for layers 1-3
    three_layer = compute_three_layer_model(
        graph,
        deploys_per_month=deploys_per_month,
        human_error_rate=human_error_rate,
        config_drift_rate=config_drift_rate,
    )

    if not graph.components:
        empty_layer = AvailabilityLayer(
            availability=0.0, nines=0.0,
            annual_downtime_seconds=365.25 * 24 * 3600,
            description="No components", details={},
        )
        return FiveLayerResult(
            layer1_software=three_layer.layer1_software,
            layer2_hardware=three_layer.layer2_hardware,
            layer3_theoretical=three_layer.layer3_theoretical,
            layer4_operational=empty_layer,
            layer5_external=empty_layer,
        )

    # =====================================================================
    # Layer 4: Operational Limit
    # Formula: operational_avail = 1 - (incidents_per_year * mean_response_hours / 8760)
    # Adjusted by on-call coverage: lower coverage means longer effective
    # response time because incidents during uncovered hours wait until
    # an engineer is available.
    #
    # Per-component team configs (runbook_coverage_percent, automation_percent)
    # reduce the effective response time:
    #   - runbook_coverage reduces response time by up to 30%
    #   - automation reduces MTTR by up to 50%
    # =====================================================================
    hours_per_year = 8760.0
    mean_response_hours = mean_response_minutes / 60.0

    # Coverage adjustment: if only 33% coverage, effective response time
    # is inflated because incidents during uncovered periods accumulate.
    coverage_fraction = max(0.01, min(1.0, oncall_coverage_percent / 100.0))
    effective_response_hours = mean_response_hours / coverage_fraction

    # Apply team operational readiness from component configs.
    # Average runbook_coverage_percent and automation_percent across all
    # components to derive a system-wide operational efficiency factor.
    if graph.components:
        avg_runbook = sum(
            c.team.runbook_coverage_percent for c in graph.components.values()
        ) / len(graph.components)
        avg_automation = sum(
            c.team.automation_percent for c in graph.components.values()
        ) / len(graph.components)

        # Runbook coverage reduces effective response time by up to 30%.
        runbook_factor = 1.0 - 0.3 * (avg_runbook / 100.0)
        # Automation reduces MTTR by up to 50%.
        automation_factor = 1.0 - 0.5 * (avg_automation / 100.0)

        effective_response_hours *= runbook_factor * automation_factor

    # Total downtime fraction from incident response
    operational_unavail = (incidents_per_year * effective_response_hours) / hours_per_year
    operational_avail = max(0.0, min(1.0, 1.0 - operational_unavail))

    layer4 = AvailabilityLayer(
        availability=operational_avail,
        nines=_to_nines(operational_avail),
        annual_downtime_seconds=_annual_downtime(operational_avail),
        description="Operational limit: incident response + on-call coverage + team readiness",
        details={
            "incidents_per_year": incidents_per_year,
            "mean_response_minutes": mean_response_minutes,
            "oncall_coverage_percent": oncall_coverage_percent,
            "effective_response_hours": effective_response_hours,
            "operational_unavail_fraction": operational_unavail,
        },
    )

    # =====================================================================
    # Layer 5: External SLA Cascading
    # Product of all external dependency SLAs
    # =====================================================================
    external_sla_values: dict[str, float] = {}

    for comp in graph.components.values():
        # Include if component has explicit external_sla config
        if comp.external_sla is not None:
            sla_fraction = comp.external_sla.provider_sla / 100.0
            external_sla_values[comp.id] = max(0.0, min(1.0, sla_fraction))
        # Or if component type is external_api (default SLA = 99.9%)
        elif comp.type.value == "external_api":
            external_sla_values[comp.id] = 0.999  # default three nines

    if external_sla_values:
        external_avail = 1.0
        for sla_val in external_sla_values.values():
            external_avail *= sla_val
        external_avail = max(0.0, min(1.0, external_avail))
    else:
        # No external dependencies — external SLA is perfect (1.0)
        external_avail = 1.0

    layer5 = AvailabilityLayer(
        availability=external_avail,
        nines=_to_nines(external_avail),
        annual_downtime_seconds=_annual_downtime(external_avail),
        description="External SLA cascading: product of provider SLAs",
        details=external_sla_values if external_sla_values else {"no_external_deps": 1.0},
    )

    return FiveLayerResult(
        layer1_software=three_layer.layer1_software,
        layer2_hardware=three_layer.layer2_hardware,
        layer3_theoretical=three_layer.layer3_theoretical,
        layer4_operational=layer4,
        layer5_external=layer5,
    )
