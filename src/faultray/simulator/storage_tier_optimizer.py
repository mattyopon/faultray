"""Storage Tier Optimizer for FaultRay.

Optimizes data storage placement across tiers based on access patterns,
SLA requirements, and cost constraints.  Provides data lifecycle policy
recommendations, storage cost modeling (including IOPS costs), latency
impact analysis of tier transitions, retrieval time modeling, compliance
retention validation, deduplication / compression opportunity analysis,
cross-region replication cost estimation, capacity forecasting, and
automatic data classification by temperature (hot / warm / cold / archive).

Usage:
    from faultray.simulator.storage_tier_optimizer import StorageTierOptimizer
    optimizer = StorageTierOptimizer(graph)
    report = optimizer.analyze()
    print(f"Current cost: ${report.current_monthly_cost:.2f}/mo")
    print(f"Optimized cost: ${report.optimized_monthly_cost:.2f}/mo")

CLI:
    faultray storage-tier-optimize model.yaml --json
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StorageTier(str, Enum):
    """Available storage tiers ordered from hottest to coldest."""

    HOT = "hot"          # SSD / NVMe – lowest latency
    WARM = "warm"        # HDD – balanced
    COLD = "cold"        # S3 Standard-IA – infrequent access
    ARCHIVE = "archive"  # Glacier / tape – long-term retention


class AccessPattern(str, Enum):
    """I/O access pattern classification."""

    SEQUENTIAL_READ = "sequential_read"
    RANDOM_READ = "random_read"
    SEQUENTIAL_WRITE = "sequential_write"
    RANDOM_WRITE = "random_write"
    MIXED = "mixed"


class ComplianceFramework(str, Enum):
    """Data retention compliance frameworks."""

    GDPR = "gdpr"
    HIPAA = "hipaa"
    SOX = "sox"
    PCI_DSS = "pci_dss"
    CUSTOM = "custom"


class RiskLevel(str, Enum):
    """Risk assessment level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Constants – cost model per tier
# ---------------------------------------------------------------------------

# $/GB/month (storage only)
STORAGE_COST_PER_GB: dict[StorageTier, float] = {
    StorageTier.HOT: 0.23,
    StorageTier.WARM: 0.045,
    StorageTier.COLD: 0.0125,
    StorageTier.ARCHIVE: 0.004,
}

# $/1000 IOPS/month (read)
READ_IOPS_COST: dict[StorageTier, float] = {
    StorageTier.HOT: 0.005,
    StorageTier.WARM: 0.01,
    StorageTier.COLD: 0.10,
    StorageTier.ARCHIVE: 5.0,
}

# $/1000 IOPS/month (write)
WRITE_IOPS_COST: dict[StorageTier, float] = {
    StorageTier.HOT: 0.01,
    StorageTier.WARM: 0.02,
    StorageTier.COLD: 0.15,
    StorageTier.ARCHIVE: 10.0,
}

# Retrieval latency per tier (milliseconds for first-byte)
RETRIEVAL_LATENCY_MS: dict[StorageTier, float] = {
    StorageTier.HOT: 0.5,
    StorageTier.WARM: 8.0,
    StorageTier.COLD: 50.0,
    StorageTier.ARCHIVE: 3_600_000.0,  # 1 hour for Glacier standard
}

# Transition cost $/GB when moving between tiers
TRANSITION_COST_PER_GB: dict[tuple[StorageTier, StorageTier], float] = {
    (StorageTier.HOT, StorageTier.WARM): 0.01,
    (StorageTier.HOT, StorageTier.COLD): 0.02,
    (StorageTier.HOT, StorageTier.ARCHIVE): 0.03,
    (StorageTier.WARM, StorageTier.COLD): 0.01,
    (StorageTier.WARM, StorageTier.ARCHIVE): 0.02,
    (StorageTier.COLD, StorageTier.ARCHIVE): 0.01,
    # Retrieval (promotion) costs are higher
    (StorageTier.ARCHIVE, StorageTier.COLD): 0.05,
    (StorageTier.ARCHIVE, StorageTier.WARM): 0.08,
    (StorageTier.ARCHIVE, StorageTier.HOT): 0.12,
    (StorageTier.COLD, StorageTier.WARM): 0.03,
    (StorageTier.COLD, StorageTier.HOT): 0.05,
    (StorageTier.WARM, StorageTier.HOT): 0.02,
}

# Minimum retention days per compliance framework
COMPLIANCE_RETENTION_DAYS: dict[ComplianceFramework, int] = {
    ComplianceFramework.GDPR: 365,
    ComplianceFramework.HIPAA: 2190,        # 6 years
    ComplianceFramework.SOX: 2555,          # 7 years
    ComplianceFramework.PCI_DSS: 365,
    ComplianceFramework.CUSTOM: 0,
}

# Cross-region replication cost $/GB
CROSS_REGION_REPLICATION_COST_PER_GB = 0.02

# Tier ordering for comparison
_TIER_ORDER: dict[StorageTier, int] = {
    StorageTier.HOT: 0,
    StorageTier.WARM: 1,
    StorageTier.COLD: 2,
    StorageTier.ARCHIVE: 3,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DataAccessProfile:
    """Describes the access behaviour of a data set on a component."""

    component_id: str
    data_size_gb: float = 100.0
    current_tier: StorageTier = StorageTier.HOT
    read_iops: float = 1000.0       # average reads/second
    write_iops: float = 200.0       # average writes/second
    access_pattern: AccessPattern = AccessPattern.MIXED
    read_frequency_per_day: float = 10000.0
    write_frequency_per_day: float = 2000.0
    last_access_days_ago: int = 0
    data_age_days: int = 30
    growth_rate_gb_per_month: float = 5.0
    dedup_eligible_ratio: float = 0.0   # 0.0 – 1.0
    compression_ratio: float = 1.0      # e.g. 0.5 means 50% of original size
    cross_region_replicas: int = 0
    compliance_frameworks: list[ComplianceFramework] = field(default_factory=list)
    custom_retention_days: int = 0
    sla_max_retrieval_ms: float = 0.0   # 0 = no constraint


@dataclass
class TierRecommendation:
    """Recommendation to move data to a different tier."""

    component_id: str
    current_tier: StorageTier
    recommended_tier: StorageTier
    current_cost_monthly: float
    recommended_cost_monthly: float
    savings_monthly: float
    transition_cost: float
    break_even_days: float
    latency_impact_ms: float
    retrieval_time_ms: float
    risk_level: RiskLevel
    reason: str


@dataclass
class LifecycleRule:
    """An auto-tiering lifecycle rule."""

    rule_id: str
    component_id: str
    condition_type: str        # "age", "access_frequency", "last_access"
    condition_threshold: float  # days or ops/day
    source_tier: StorageTier
    target_tier: StorageTier
    description: str


@dataclass
class DeduplicationOpportunity:
    """Deduplication / compression savings for a component."""

    component_id: str
    current_size_gb: float
    effective_size_gb: float
    dedup_savings_gb: float
    compression_savings_gb: float
    total_savings_gb: float
    monthly_cost_savings: float


@dataclass
class CrossRegionCost:
    """Cost of replicating data across regions."""

    component_id: str
    data_size_gb: float
    replica_count: int
    monthly_transfer_cost: float
    monthly_storage_cost: float
    total_monthly_cost: float


@dataclass
class CapacityProjection:
    """Storage capacity forecast for a component."""

    component_id: str
    current_size_gb: float
    growth_rate_gb_per_month: float
    projected_size_30d_gb: float
    projected_size_90d_gb: float
    projected_size_365d_gb: float
    months_until_threshold_gb: float  # months until breaching a threshold
    threshold_gb: float


@dataclass
class DataClassification:
    """Breakdown of data by temperature classification."""

    component_id: str
    total_size_gb: float
    hot_ratio: float
    warm_ratio: float
    cold_ratio: float
    archive_ratio: float


@dataclass
class ComplianceCheck:
    """Result of a compliance retention validation."""

    component_id: str
    framework: ComplianceFramework
    required_retention_days: int
    current_tier: StorageTier
    current_data_age_days: int
    meets_requirement: bool
    recommendation: str


@dataclass
class StorageTierReport:
    """Complete storage tier optimization report."""

    generated_at: datetime
    total_profiles_analyzed: int
    current_monthly_cost: float
    optimized_monthly_cost: float
    total_savings_monthly: float
    savings_percent: float
    recommendations: list[TierRecommendation] = field(default_factory=list)
    lifecycle_rules: list[LifecycleRule] = field(default_factory=list)
    dedup_opportunities: list[DeduplicationOpportunity] = field(default_factory=list)
    cross_region_costs: list[CrossRegionCost] = field(default_factory=list)
    capacity_projections: list[CapacityProjection] = field(default_factory=list)
    data_classifications: list[DataClassification] = field(default_factory=list)
    compliance_checks: list[ComplianceCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _monthly_storage_cost(tier: StorageTier, size_gb: float) -> float:
    """Calculate monthly storage cost for a tier and data size."""
    return STORAGE_COST_PER_GB[tier] * size_gb


def _monthly_iops_cost(
    tier: StorageTier,
    read_iops: float,
    write_iops: float,
) -> float:
    """Estimate monthly IOPS cost for given read/write rates.

    Converts IOPS (per-second) to a monthly operation count then applies
    the per-1000-ops cost rate.
    """
    seconds_per_month = 30.0 * 24.0 * 3600.0
    total_read_ops = read_iops * seconds_per_month
    total_write_ops = write_iops * seconds_per_month
    read_cost = (total_read_ops / 1000.0) * READ_IOPS_COST[tier]
    write_cost = (total_write_ops / 1000.0) * WRITE_IOPS_COST[tier]
    return read_cost + write_cost


def _total_monthly_cost(profile: DataAccessProfile) -> float:
    """Total monthly cost for a profile on its current tier."""
    storage = _monthly_storage_cost(profile.current_tier, profile.data_size_gb)
    iops = _monthly_iops_cost(profile.current_tier, profile.read_iops, profile.write_iops)
    return storage + iops


def _total_monthly_cost_on_tier(
    profile: DataAccessProfile,
    tier: StorageTier,
) -> float:
    """Total monthly cost if the profile's data lived on *tier*."""
    storage = _monthly_storage_cost(tier, profile.data_size_gb)
    iops = _monthly_iops_cost(tier, profile.read_iops, profile.write_iops)
    return storage + iops


def _transition_cost(
    source: StorageTier,
    target: StorageTier,
    size_gb: float,
) -> float:
    """One-time cost to move data between tiers."""
    per_gb = TRANSITION_COST_PER_GB.get((source, target), 0.0)
    return per_gb * size_gb


def _classify_temperature(profile: DataAccessProfile) -> DataClassification:
    """Classify data into temperature buckets based on access patterns."""
    # Heuristic: the more recent and frequent the access, the hotter the data
    read_freq = profile.read_frequency_per_day
    write_freq = profile.write_frequency_per_day
    total_freq = read_freq + write_freq
    last_access = profile.last_access_days_ago
    max(1, profile.data_age_days)

    # Score: higher = hotter
    if total_freq <= 0 and last_access > 180:
        hot, warm, cold, archive = 0.0, 0.0, 0.1, 0.9
    elif total_freq <= 0 and last_access > 30:
        hot, warm, cold, archive = 0.0, 0.1, 0.7, 0.2
    elif total_freq <= 10:
        hot, warm, cold, archive = 0.0, 0.2, 0.6, 0.2
    elif total_freq <= 100:
        hot, warm, cold, archive = 0.1, 0.5, 0.3, 0.1
    elif total_freq <= 1000:
        hot, warm, cold, archive = 0.3, 0.5, 0.15, 0.05
    elif total_freq <= 10000:
        hot, warm, cold, archive = 0.6, 0.3, 0.08, 0.02
    else:
        hot, warm, cold, archive = 0.8, 0.15, 0.04, 0.01

    # Adjust by recency: very old data shifts colder
    if last_access > 90:
        shift = min(0.3, last_access / 1000.0)
        hot = max(0.0, hot - shift)
        archive = min(1.0, archive + shift)
    elif last_access > 30:
        shift = min(0.15, last_access / 1000.0)
        hot = max(0.0, hot - shift)
        cold = min(1.0, cold + shift)

    # Normalise
    total = hot + warm + cold + archive
    if total > 0:
        hot /= total
        warm /= total
        cold /= total
        archive /= total
    else:
        hot, warm, cold, archive = 0.0, 0.0, 0.0, 1.0

    return DataClassification(
        component_id=profile.component_id,
        total_size_gb=profile.data_size_gb,
        hot_ratio=round(hot, 4),
        warm_ratio=round(warm, 4),
        cold_ratio=round(cold, 4),
        archive_ratio=round(archive, 4),
    )


def _recommend_tier(profile: DataAccessProfile) -> StorageTier:
    """Determine the optimal tier for a data access profile.

    Considers access frequency, recency, SLA retrieval constraints, and
    compliance requirements.
    """
    classification = _classify_temperature(profile)

    # Pick tier by dominant ratio
    ratios = {
        StorageTier.HOT: classification.hot_ratio,
        StorageTier.WARM: classification.warm_ratio,
        StorageTier.COLD: classification.cold_ratio,
        StorageTier.ARCHIVE: classification.archive_ratio,
    }
    best_tier = max(ratios, key=lambda t: ratios[t])

    # SLA constraint: if max retrieval time is specified, clamp tier
    if profile.sla_max_retrieval_ms > 0:
        while RETRIEVAL_LATENCY_MS[best_tier] > profile.sla_max_retrieval_ms:
            order = _TIER_ORDER[best_tier]
            if order == 0:
                break
            # Move one tier hotter
            for t, o in _TIER_ORDER.items():
                if o == order - 1:
                    best_tier = t
                    break

    return best_tier


def _determine_risk(
    current_tier: StorageTier,
    recommended_tier: StorageTier,
    profile: DataAccessProfile,
) -> RiskLevel:
    """Assess risk of a tier transition."""
    current_order = _TIER_ORDER[current_tier]
    rec_order = _TIER_ORDER[recommended_tier]
    step = abs(rec_order - current_order)

    if step == 0:
        return RiskLevel.LOW

    # Moving to colder storage is safer than promoting
    moving_colder = rec_order > current_order

    if moving_colder:
        if step == 1:
            return RiskLevel.LOW
        elif step == 2:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.HIGH
    else:
        # Promotion – typically done for performance, less risky
        if step == 1:
            return RiskLevel.LOW
        else:
            return RiskLevel.MEDIUM


# ---------------------------------------------------------------------------
# Main optimizer class
# ---------------------------------------------------------------------------


class StorageTierOptimizer:
    """Optimizes data placement across storage tiers.

    Parameters
    ----------
    graph:
        Infrastructure graph providing component context.
    profiles:
        Per-component data access profiles.  If not supplied the optimizer
        will generate synthetic profiles from the graph's storage/database
        components.
    capacity_threshold_gb:
        Threshold used for capacity projection warnings.
    """

    def __init__(
        self,
        graph: InfraGraph,
        profiles: list[DataAccessProfile] | None = None,
        capacity_threshold_gb: float = 1000.0,
    ) -> None:
        self.graph = graph
        self.profiles = profiles or self._build_default_profiles()
        self.capacity_threshold_gb = capacity_threshold_gb

    # ------------------------------------------------------------------
    # Profile generation
    # ------------------------------------------------------------------

    def _build_default_profiles(self) -> list[DataAccessProfile]:
        """Create synthetic profiles for storage-relevant components."""
        profiles: list[DataAccessProfile] = []
        storage_types = {ComponentType.STORAGE, ComponentType.DATABASE}
        for comp in self.graph.components.values():
            if comp.type in storage_types:
                profiles.append(DataAccessProfile(
                    component_id=comp.id,
                    data_size_gb=comp.capacity.max_disk_gb,
                    current_tier=StorageTier.HOT,
                    read_iops=500.0,
                    write_iops=100.0,
                ))
        return profiles

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyze(self) -> StorageTierReport:
        """Run full storage tier optimization analysis.

        Returns a comprehensive :class:`StorageTierReport` containing tier
        recommendations, lifecycle rules, dedup opportunities, cross-region
        costs, capacity projections, data classifications, and compliance
        checks.
        """
        recommendations: list[TierRecommendation] = []
        lifecycle_rules: list[LifecycleRule] = []
        dedup_opps: list[DeduplicationOpportunity] = []
        cross_region: list[CrossRegionCost] = []
        projections: list[CapacityProjection] = []
        classifications: list[DataClassification] = []
        compliance: list[ComplianceCheck] = []
        warnings: list[str] = []

        current_total_cost = 0.0
        optimized_total_cost = 0.0

        for profile in self.profiles:
            # ------ cost on current tier ------
            cur_cost = _total_monthly_cost(profile)
            current_total_cost += cur_cost

            # ------ optimal tier recommendation ------
            rec_tier = _recommend_tier(profile)
            rec_cost = _total_monthly_cost_on_tier(profile, rec_tier)
            optimized_total_cost += rec_cost

            savings = cur_cost - rec_cost
            trans_cost = _transition_cost(
                profile.current_tier, rec_tier, profile.data_size_gb,
            )
            break_even = (
                trans_cost / savings * 30.0 if savings > 0 else 0.0
            )
            latency_impact = (
                RETRIEVAL_LATENCY_MS[rec_tier]
                - RETRIEVAL_LATENCY_MS[profile.current_tier]
            )
            retrieval = RETRIEVAL_LATENCY_MS[rec_tier]

            risk = _determine_risk(profile.current_tier, rec_tier, profile)

            if rec_tier != profile.current_tier:
                reason = (
                    f"Access pattern suggests {rec_tier.value} tier; "
                    f"saves ${savings:.2f}/mo with {break_even:.0f}-day break-even"
                )
            else:
                reason = "Current tier is optimal for this workload"

            recommendations.append(TierRecommendation(
                component_id=profile.component_id,
                current_tier=profile.current_tier,
                recommended_tier=rec_tier,
                current_cost_monthly=round(cur_cost, 2),
                recommended_cost_monthly=round(rec_cost, 2),
                savings_monthly=round(savings, 2),
                transition_cost=round(trans_cost, 2),
                break_even_days=round(break_even, 1),
                latency_impact_ms=round(latency_impact, 2),
                retrieval_time_ms=round(retrieval, 2),
                risk_level=risk,
                reason=reason,
            ))

            # ------ lifecycle rules ------
            lifecycle_rules.extend(self._generate_lifecycle_rules(profile))

            # ------ dedup / compression ------
            dedup_opps.append(self._analyze_dedup(profile))

            # ------ cross-region replication cost ------
            if profile.cross_region_replicas > 0:
                cross_region.append(self._calculate_cross_region_cost(profile))

            # ------ capacity projection ------
            projections.append(self._project_capacity(profile))

            # ------ data classification ------
            classifications.append(_classify_temperature(profile))

            # ------ compliance checks ------
            for fw in profile.compliance_frameworks:
                compliance.append(self._check_compliance(profile, fw))

            # ------ warnings ------
            if profile.data_size_gb > self.capacity_threshold_gb:
                warnings.append(
                    f"{profile.component_id}: data size "
                    f"({profile.data_size_gb:.0f} GB) exceeds threshold "
                    f"({self.capacity_threshold_gb:.0f} GB)"
                )
            if profile.sla_max_retrieval_ms > 0:
                current_latency = RETRIEVAL_LATENCY_MS[profile.current_tier]
                if current_latency > profile.sla_max_retrieval_ms:
                    warnings.append(
                        f"{profile.component_id}: current tier "
                        f"{profile.current_tier.value} retrieval latency "
                        f"({current_latency:.0f} ms) exceeds SLA "
                        f"({profile.sla_max_retrieval_ms:.0f} ms)"
                    )

        total_savings = current_total_cost - optimized_total_cost
        pct = (
            (total_savings / current_total_cost * 100.0)
            if current_total_cost > 0
            else 0.0
        )

        return StorageTierReport(
            generated_at=datetime.now(timezone.utc),
            total_profiles_analyzed=len(self.profiles),
            current_monthly_cost=round(current_total_cost, 2),
            optimized_monthly_cost=round(optimized_total_cost, 2),
            total_savings_monthly=round(total_savings, 2),
            savings_percent=round(pct, 1),
            recommendations=recommendations,
            lifecycle_rules=lifecycle_rules,
            dedup_opportunities=dedup_opps,
            cross_region_costs=cross_region,
            capacity_projections=projections,
            data_classifications=classifications,
            compliance_checks=compliance,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Tier recommendation helpers
    # ------------------------------------------------------------------

    def recommend_tier_for_profile(
        self, profile: DataAccessProfile,
    ) -> TierRecommendation:
        """Return a single tier recommendation for a given profile."""
        cur_cost = _total_monthly_cost(profile)
        rec_tier = _recommend_tier(profile)
        rec_cost = _total_monthly_cost_on_tier(profile, rec_tier)
        savings = cur_cost - rec_cost
        trans_cost = _transition_cost(
            profile.current_tier, rec_tier, profile.data_size_gb,
        )
        break_even = trans_cost / savings * 30.0 if savings > 0 else 0.0
        latency_impact = (
            RETRIEVAL_LATENCY_MS[rec_tier]
            - RETRIEVAL_LATENCY_MS[profile.current_tier]
        )
        retrieval = RETRIEVAL_LATENCY_MS[rec_tier]
        risk = _determine_risk(profile.current_tier, rec_tier, profile)
        reason = (
            f"Recommended {rec_tier.value} based on access profile"
            if rec_tier != profile.current_tier
            else "Current tier is optimal"
        )
        return TierRecommendation(
            component_id=profile.component_id,
            current_tier=profile.current_tier,
            recommended_tier=rec_tier,
            current_cost_monthly=round(cur_cost, 2),
            recommended_cost_monthly=round(rec_cost, 2),
            savings_monthly=round(savings, 2),
            transition_cost=round(trans_cost, 2),
            break_even_days=round(break_even, 1),
            latency_impact_ms=round(latency_impact, 2),
            retrieval_time_ms=round(retrieval, 2),
            risk_level=risk,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Lifecycle rule generation
    # ------------------------------------------------------------------

    def _generate_lifecycle_rules(
        self, profile: DataAccessProfile,
    ) -> list[LifecycleRule]:
        """Generate auto-tiering lifecycle rules for a profile."""
        rules: list[LifecycleRule] = []
        cid = profile.component_id

        # Rule: age-based transition to warm after 30 days
        if profile.current_tier == StorageTier.HOT:
            rules.append(LifecycleRule(
                rule_id=f"{cid}-age-warm",
                component_id=cid,
                condition_type="age",
                condition_threshold=30.0,
                source_tier=StorageTier.HOT,
                target_tier=StorageTier.WARM,
                description=(
                    f"Move {cid} data older than 30 days from hot to warm"
                ),
            ))
            rules.append(LifecycleRule(
                rule_id=f"{cid}-age-cold",
                component_id=cid,
                condition_type="age",
                condition_threshold=90.0,
                source_tier=StorageTier.WARM,
                target_tier=StorageTier.COLD,
                description=(
                    f"Move {cid} data older than 90 days from warm to cold"
                ),
            ))
            rules.append(LifecycleRule(
                rule_id=f"{cid}-age-archive",
                component_id=cid,
                condition_type="age",
                condition_threshold=365.0,
                source_tier=StorageTier.COLD,
                target_tier=StorageTier.ARCHIVE,
                description=(
                    f"Move {cid} data older than 365 days from cold to archive"
                ),
            ))

        # Rule: access-frequency-based transition
        if profile.read_frequency_per_day + profile.write_frequency_per_day < 10:
            rules.append(LifecycleRule(
                rule_id=f"{cid}-freq-cold",
                component_id=cid,
                condition_type="access_frequency",
                condition_threshold=10.0,
                source_tier=profile.current_tier,
                target_tier=StorageTier.COLD,
                description=(
                    f"Move {cid} to cold when daily access < 10 ops"
                ),
            ))

        # Rule: last-access-based archival
        if profile.last_access_days_ago > 90:
            rules.append(LifecycleRule(
                rule_id=f"{cid}-lastaccess-archive",
                component_id=cid,
                condition_type="last_access",
                condition_threshold=90.0,
                source_tier=profile.current_tier,
                target_tier=StorageTier.ARCHIVE,
                description=(
                    f"Archive {cid} data not accessed for 90+ days"
                ),
            ))

        return rules

    # ------------------------------------------------------------------
    # Deduplication / compression analysis
    # ------------------------------------------------------------------

    def _analyze_dedup(
        self, profile: DataAccessProfile,
    ) -> DeduplicationOpportunity:
        """Estimate dedup / compression savings."""
        original = profile.data_size_gb
        dedup_savings = original * profile.dedup_eligible_ratio
        after_dedup = original - dedup_savings

        # Compression applies to post-dedup size
        if profile.compression_ratio < 1.0:
            compressed = after_dedup * profile.compression_ratio
            compression_savings = after_dedup - compressed
        else:
            compressed = after_dedup
            compression_savings = 0.0

        effective = compressed
        total_saved = dedup_savings + compression_savings

        cost_saving = _monthly_storage_cost(
            profile.current_tier, total_saved,
        )

        return DeduplicationOpportunity(
            component_id=profile.component_id,
            current_size_gb=round(original, 2),
            effective_size_gb=round(effective, 2),
            dedup_savings_gb=round(dedup_savings, 2),
            compression_savings_gb=round(compression_savings, 2),
            total_savings_gb=round(total_saved, 2),
            monthly_cost_savings=round(cost_saving, 2),
        )

    # ------------------------------------------------------------------
    # Cross-region replication cost
    # ------------------------------------------------------------------

    def _calculate_cross_region_cost(
        self, profile: DataAccessProfile,
    ) -> CrossRegionCost:
        """Estimate cost of cross-region replication."""
        replicas = profile.cross_region_replicas
        transfer = profile.data_size_gb * replicas * CROSS_REGION_REPLICATION_COST_PER_GB
        storage = _monthly_storage_cost(
            profile.current_tier, profile.data_size_gb,
        ) * replicas
        return CrossRegionCost(
            component_id=profile.component_id,
            data_size_gb=profile.data_size_gb,
            replica_count=replicas,
            monthly_transfer_cost=round(transfer, 2),
            monthly_storage_cost=round(storage, 2),
            total_monthly_cost=round(transfer + storage, 2),
        )

    # ------------------------------------------------------------------
    # Capacity projection
    # ------------------------------------------------------------------

    def _project_capacity(
        self, profile: DataAccessProfile,
    ) -> CapacityProjection:
        """Forecast storage growth over 30, 90, and 365 days."""
        current = profile.data_size_gb
        rate = profile.growth_rate_gb_per_month

        proj_30 = current + rate * 1
        proj_90 = current + rate * 3
        proj_365 = current + rate * 12

        threshold = self.capacity_threshold_gb
        if rate > 0:
            remaining_gb = max(0.0, threshold - current)
            months_until = remaining_gb / rate
        elif current >= threshold:
            months_until = 0.0
        else:
            months_until = float("inf")

        return CapacityProjection(
            component_id=profile.component_id,
            current_size_gb=round(current, 2),
            growth_rate_gb_per_month=round(rate, 2),
            projected_size_30d_gb=round(proj_30, 2),
            projected_size_90d_gb=round(proj_90, 2),
            projected_size_365d_gb=round(proj_365, 2),
            months_until_threshold_gb=round(months_until, 2) if math.isfinite(months_until) else float("inf"),
            threshold_gb=threshold,
        )

    # ------------------------------------------------------------------
    # Compliance checking
    # ------------------------------------------------------------------

    def _check_compliance(
        self, profile: DataAccessProfile,
        framework: ComplianceFramework,
    ) -> ComplianceCheck:
        """Validate data retention against compliance requirements."""
        if framework == ComplianceFramework.CUSTOM:
            required = profile.custom_retention_days
        else:
            required = COMPLIANCE_RETENTION_DAYS[framework]

        age = profile.data_age_days

        # Tiers that support long-term retention
        long_term_tiers = {StorageTier.COLD, StorageTier.ARCHIVE}

        meets = True
        recommendation = "Data retention meets compliance requirements"

        if required > 0 and age < required:
            # Data hasn't reached the required retention yet – that's okay,
            # but it must be *stored* (not deleted) for the full period.
            # We flag a warning if the current tier is too expensive for
            # the remaining retention period.
            remaining = required - age
            if remaining > 365 and profile.current_tier not in long_term_tiers:
                meets = True  # still compliant but suboptimal
                recommendation = (
                    f"Data needs {remaining} more days of retention; "
                    f"consider moving to cold/archive to reduce cost"
                )
            else:
                recommendation = (
                    f"Data will be retained for the required "
                    f"{required} days ({remaining} days remaining)"
                )

        # If tier is archive, check Glacier retrieval constraint vs SLA
        if (
            profile.current_tier == StorageTier.ARCHIVE
            and profile.sla_max_retrieval_ms > 0
            and RETRIEVAL_LATENCY_MS[StorageTier.ARCHIVE] > profile.sla_max_retrieval_ms
        ):
            recommendation = (
                "Archive tier violates SLA retrieval constraint; "
                "consider cold tier with lifecycle policy"
            )
            meets = False

        return ComplianceCheck(
            component_id=profile.component_id,
            framework=framework,
            required_retention_days=required,
            current_tier=profile.current_tier,
            current_data_age_days=age,
            meets_requirement=meets,
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # Convenience: cost comparisons across all tiers
    # ------------------------------------------------------------------

    def compare_all_tiers(
        self, profile: DataAccessProfile,
    ) -> dict[StorageTier, float]:
        """Return monthly cost for a profile on every tier."""
        return {
            tier: round(_total_monthly_cost_on_tier(profile, tier), 2)
            for tier in StorageTier
        }

    def estimate_transition_costs(
        self, profile: DataAccessProfile,
    ) -> dict[StorageTier, float]:
        """Return one-time transition cost to each tier from current."""
        return {
            tier: round(
                _transition_cost(profile.current_tier, tier, profile.data_size_gb),
                2,
            )
            for tier in StorageTier
        }
