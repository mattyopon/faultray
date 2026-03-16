"""Multi-Region DR Engine - simulate disaster recovery scenarios.

Supports AZ failure, region failure, and network partition scenarios.
Uses RegionConfig on components to determine geographic distribution
and RPO/RTO compliance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


@dataclass
class DRScenarioResult:
    """Result of a single DR scenario simulation."""

    scenario: str  # "az_failure", "region_failure", "network_partition"
    affected_components: list[str] = field(default_factory=list)
    surviving_components: list[str] = field(default_factory=list)
    rpo_met: bool = True
    rto_met: bool = True
    estimated_data_loss_seconds: float = 0.0
    estimated_recovery_seconds: float = 0.0
    availability_during_dr: float = 100.0


class DREngine:
    """Simulate disaster recovery scenarios against an InfraGraph.

    Components are grouped by their ``region`` configuration. When a region
    or AZ fails, the engine determines which components are affected,
    which survive, and whether RPO/RTO targets are met.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_region(self, comp) -> str:
        """Get region string from a component."""
        region_cfg = getattr(comp, "region", None)
        if region_cfg is not None and region_cfg.region:
            return region_cfg.region
        return ""

    def _get_az(self, comp) -> str:
        """Get availability zone from a component."""
        region_cfg = getattr(comp, "region", None)
        if region_cfg is not None and region_cfg.availability_zone:
            return region_cfg.availability_zone
        return ""

    def _get_rpo(self, comp) -> int:
        """Get RPO in seconds from a component."""
        region_cfg = getattr(comp, "region", None)
        if region_cfg is not None and region_cfg.rpo_seconds > 0:
            return region_cfg.rpo_seconds
        return 0

    def _get_rto(self, comp) -> int:
        """Get RTO in seconds from a component."""
        region_cfg = getattr(comp, "region", None)
        if region_cfg is not None and region_cfg.rto_seconds > 0:
            return region_cfg.rto_seconds
        return 0

    def _is_primary(self, comp) -> bool:
        """Check if a component is in the primary region."""
        region_cfg = getattr(comp, "region", None)
        if region_cfg is not None:
            return region_cfg.is_primary
        return True

    def _all_regions(self) -> set[str]:
        """Get all unique regions."""
        regions = set()
        for comp in self.graph.components.values():
            r = self._get_region(comp)
            if r:
                regions.add(r)
        return regions

    def _all_azs(self) -> set[str]:
        """Get all unique availability zones."""
        azs = set()
        for comp in self.graph.components.values():
            az = self._get_az(comp)
            if az:
                azs.add(az)
        return azs

    def _estimate_recovery_seconds(self, affected_comps: list) -> float:
        """Estimate recovery time based on affected components.

        Uses failover promotion time if available, otherwise defaults
        to a base recovery time plus per-component overhead.
        """
        if not affected_comps:
            return 0.0

        max_recovery = 0.0
        for comp in affected_comps:
            # If the component has failover configured, use promotion time
            if comp.failover.enabled:
                recovery = comp.failover.promotion_time_seconds
            else:
                # Base recovery: MTTR or default
                mttr = comp.operational_profile.mttr_minutes
                if mttr > 0:
                    recovery = mttr * 60.0
                else:
                    recovery = 300.0  # 5 min default
            max_recovery = max(max_recovery, recovery)

        return max_recovery

    def _estimate_data_loss_seconds(self, affected_comps: list) -> float:
        """Estimate potential data loss based on RPO and replication lag.

        For components without explicit RPO, estimate based on sync type:
        - With failover: assume async replication lag (~5s)
        - Without failover: last backup window (~3600s)
        """
        if not affected_comps:
            return 0.0

        max_data_loss = 0.0
        for comp in affected_comps:
            rpo = self._get_rpo(comp)
            if rpo > 0:
                data_loss = float(rpo)
            elif comp.failover.enabled:
                # Async replication lag estimate
                data_loss = 5.0
            else:
                # Last backup window estimate
                data_loss = 3600.0
            max_data_loss = max(max_data_loss, data_loss)

        return max_data_loss

    # ------------------------------------------------------------------
    # Scenario simulations
    # ------------------------------------------------------------------

    def simulate_az_failure(self, az: str) -> DRScenarioResult:
        """Simulate a single availability zone failure.

        All components in the specified AZ are considered affected.
        Components in other AZs (same or different region) survive.
        """
        affected = []
        surviving = []

        for comp in self.graph.components.values():
            comp_az = self._get_az(comp)
            if comp_az == az:
                affected.append(comp)
            else:
                surviving.append(comp)

        affected_ids = [c.id for c in affected]
        surviving_ids = [c.id for c in surviving]

        total = len(self.graph.components)
        if total == 0:
            availability = 100.0
        else:
            availability = len(surviving) / total * 100.0

        recovery_seconds = self._estimate_recovery_seconds(affected)
        data_loss_seconds = self._estimate_data_loss_seconds(affected)

        # Check RPO/RTO against targets
        rpo_met = True
        rto_met = True
        for comp in affected:
            rpo = self._get_rpo(comp)
            rto = self._get_rto(comp)
            if rpo > 0 and data_loss_seconds > rpo:
                rpo_met = False
            if rto > 0 and recovery_seconds > rto:
                rto_met = False

        return DRScenarioResult(
            scenario="az_failure",
            affected_components=affected_ids,
            surviving_components=surviving_ids,
            rpo_met=rpo_met,
            rto_met=rto_met,
            estimated_data_loss_seconds=data_loss_seconds,
            estimated_recovery_seconds=recovery_seconds,
            availability_during_dr=round(availability, 2),
        )

    def simulate_region_failure(self, region: str) -> DRScenarioResult:
        """Simulate a full region failure.

        All components in the specified region are considered affected.
        Components in other regions survive.
        """
        affected = []
        surviving = []

        for comp in self.graph.components.values():
            comp_region = self._get_region(comp)
            if comp_region == region:
                affected.append(comp)
            else:
                surviving.append(comp)

        affected_ids = [c.id for c in affected]
        surviving_ids = [c.id for c in surviving]

        total = len(self.graph.components)
        if total == 0:
            availability = 100.0
        else:
            availability = len(surviving) / total * 100.0

        recovery_seconds = self._estimate_recovery_seconds(affected)
        data_loss_seconds = self._estimate_data_loss_seconds(affected)

        # Check RPO/RTO
        rpo_met = True
        rto_met = True
        for comp in affected:
            rpo = self._get_rpo(comp)
            rto = self._get_rto(comp)
            if rpo > 0 and data_loss_seconds > rpo:
                rpo_met = False
            if rto > 0 and recovery_seconds > rto:
                rto_met = False

        return DRScenarioResult(
            scenario="region_failure",
            affected_components=affected_ids,
            surviving_components=surviving_ids,
            rpo_met=rpo_met,
            rto_met=rto_met,
            estimated_data_loss_seconds=data_loss_seconds,
            estimated_recovery_seconds=recovery_seconds,
            availability_during_dr=round(availability, 2),
        )

    def simulate_network_partition(self, region_a: str, region_b: str) -> DRScenarioResult:
        """Simulate a network partition between two regions.

        Components in both regions survive individually, but cross-region
        dependencies are broken. Affected components are those that depend
        on components in the other partition.
        """
        region_a_comps = set()
        region_b_comps = set()

        for comp in self.graph.components.values():
            r = self._get_region(comp)
            if r == region_a:
                region_a_comps.add(comp.id)
            elif r == region_b:
                region_b_comps.add(comp.id)

        # Find cross-region dependencies that are broken
        affected_ids = set()
        for edge in self.graph.all_dependency_edges():
            src_in_a = edge.source_id in region_a_comps
            tgt_in_b = edge.target_id in region_b_comps
            src_in_b = edge.source_id in region_b_comps
            tgt_in_a = edge.target_id in region_a_comps

            if (src_in_a and tgt_in_b) or (src_in_b and tgt_in_a):
                # Cross-region dependency broken - source is affected
                affected_ids.add(edge.source_id)

        all_ids = set(self.graph.components.keys())
        surviving_ids = list(all_ids - affected_ids)
        affected_list = list(affected_ids)

        affected_comps = [
            self.graph.get_component(cid)
            for cid in affected_list
            if self.graph.get_component(cid) is not None
        ]

        total = len(self.graph.components)
        if total == 0:
            availability = 100.0
        else:
            availability = len(surviving_ids) / total * 100.0

        recovery_seconds = self._estimate_recovery_seconds(affected_comps)
        data_loss_seconds = self._estimate_data_loss_seconds(affected_comps)

        # Check RPO/RTO
        rpo_met = True
        rto_met = True
        for comp in affected_comps:
            rpo = self._get_rpo(comp)
            rto = self._get_rto(comp)
            if rpo > 0 and data_loss_seconds > rpo:
                rpo_met = False
            if rto > 0 and recovery_seconds > rto:
                rto_met = False

        return DRScenarioResult(
            scenario="network_partition",
            affected_components=affected_list,
            surviving_components=surviving_ids,
            rpo_met=rpo_met,
            rto_met=rto_met,
            estimated_data_loss_seconds=data_loss_seconds,
            estimated_recovery_seconds=recovery_seconds,
            availability_during_dr=round(availability, 2),
        )

    def simulate_all(self) -> list[DRScenarioResult]:
        """Run all possible DR scenarios based on discovered regions and AZs.

        Generates:
        - One az_failure per unique AZ
        - One region_failure per unique region
        - Network partition between each pair of regions
        """
        results: list[DRScenarioResult] = []

        # AZ failures
        for az in sorted(self._all_azs()):
            results.append(self.simulate_az_failure(az))

        # Region failures
        regions = sorted(self._all_regions())
        for region in regions:
            results.append(self.simulate_region_failure(region))

        # Network partitions between region pairs
        for i, r_a in enumerate(regions):
            for r_b in regions[i + 1:]:
                results.append(self.simulate_network_partition(r_a, r_b))

        return results
