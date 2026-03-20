# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Backup & Recovery Planner for FaultRay.

Plans and evaluates backup and disaster recovery strategies.  Features include
backup strategy selection, RTO/RPO estimation, 3-2-1 rule compliance,
cross-region distribution, backup window analysis, restore testing simulation,
data corruption detection, tiered storage optimisation, incremental chain
dependency analysis, and retention policy evaluation.

All public data models use Pydantic v2 ``BaseModel``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BackupStrategy(str, Enum):
    """Supported backup strategies."""

    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"
    CONTINUOUS = "continuous"
    SNAPSHOT = "snapshot"


class StorageTier(str, Enum):
    """Storage tier classification based on access frequency / SLA."""

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    ARCHIVE = "archive"


class IntegrityStatus(str, Enum):
    """Result of a data-integrity / checksum verification."""

    VALID = "valid"
    CORRUPTED = "corrupted"
    MISSING = "missing"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Cost constants  (USD / GB / month)
# ---------------------------------------------------------------------------

_TIER_COST_PER_GB: dict[StorageTier, float] = {
    StorageTier.HOT: 0.023,
    StorageTier.WARM: 0.0125,
    StorageTier.COLD: 0.004,
    StorageTier.ARCHIVE: 0.00099,
}

_TIER_RETRIEVAL_COST_PER_GB: dict[StorageTier, float] = {
    StorageTier.HOT: 0.0,
    StorageTier.WARM: 0.01,
    StorageTier.COLD: 0.02,
    StorageTier.ARCHIVE: 0.05,
}

# Restore speed in GB/min per tier (approximation).
_TIER_RESTORE_SPEED_GB_MIN: dict[StorageTier, float] = {
    StorageTier.HOT: 10.0,
    StorageTier.WARM: 5.0,
    StorageTier.COLD: 1.0,
    StorageTier.ARCHIVE: 0.1,
}

# Strategy-specific overhead multiplier on backup size.
_STRATEGY_SIZE_FACTOR: dict[BackupStrategy, float] = {
    BackupStrategy.FULL: 1.0,
    BackupStrategy.INCREMENTAL: 0.1,
    BackupStrategy.DIFFERENTIAL: 0.3,
    BackupStrategy.CONTINUOUS: 0.05,
    BackupStrategy.SNAPSHOT: 0.2,
}

# RPO guarantees in seconds per strategy (best-case).
_STRATEGY_RPO_SECONDS: dict[BackupStrategy, int] = {
    BackupStrategy.FULL: 86400,         # 24 h
    BackupStrategy.INCREMENTAL: 3600,   # 1 h
    BackupStrategy.DIFFERENTIAL: 3600,  # 1 h
    BackupStrategy.CONTINUOUS: 5,       # near-zero
    BackupStrategy.SNAPSHOT: 900,       # 15 min
}

# Maximum recommended incremental chain length before a full backup.
_MAX_SAFE_CHAIN_LENGTH = 14

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class BackupConfig(BaseModel):
    """Configuration describing a backup job for a single component."""

    component_id: str
    strategy: BackupStrategy = BackupStrategy.FULL
    frequency_hours: float = 24.0
    retention_days: int = 30
    storage_tier: StorageTier = StorageTier.WARM
    data_size_gb: float = 0.0
    daily_change_rate: float = 0.05  # 5 % of data changes per day
    backup_window_minutes: int = 240  # 4-hour window
    network_bandwidth_mbps: float = 1000.0  # 1 Gbps
    copies: int = 1
    media_types: int = 1
    offsite_copies: int = 0
    regions: list[str] = Field(default_factory=list)
    encryption_enabled: bool = False
    compression_ratio: float = 0.5  # effective size = data * ratio


class RTOEstimate(BaseModel):
    """Estimated Recovery Time Objective for a component."""

    component_id: str
    strategy: BackupStrategy
    estimated_rto_seconds: float = 0.0
    restore_data_gb: float = 0.0
    network_transfer_seconds: float = 0.0
    processing_overhead_seconds: float = 0.0
    tier_retrieval_seconds: float = 0.0
    bottleneck: str = ""


class RPOAnalysis(BaseModel):
    """Recovery Point Objective analysis for a backup configuration."""

    component_id: str
    strategy: BackupStrategy
    guaranteed_rpo_seconds: int = 0
    worst_case_data_loss_gb: float = 0.0
    meets_target: bool = True
    target_rpo_seconds: int = 0
    explanation: str = ""


class ThreeTwoOneResult(BaseModel):
    """Result of the 3-2-1 backup rule compliance check."""

    component_id: str
    compliant: bool = False
    copies: int = 0
    media_types: int = 0
    offsite_copies: int = 0
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class BackupWindowAnalysis(BaseModel):
    """Analysis of whether a backup fits within its maintenance window."""

    component_id: str
    estimated_backup_minutes: float = 0.0
    window_minutes: int = 0
    fits_in_window: bool = True
    utilisation_percent: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class RestoreTestResult(BaseModel):
    """Simulated restore test from a specific backup point."""

    component_id: str
    backup_age_hours: float = 0.0
    restore_time_seconds: float = 0.0
    data_loss_gb: float = 0.0
    integrity_status: IntegrityStatus = IntegrityStatus.VALID
    success: bool = True
    notes: list[str] = Field(default_factory=list)


class ChecksumVerification(BaseModel):
    """Result of a checksum / integrity-chain verification."""

    component_id: str
    status: IntegrityStatus = IntegrityStatus.UNKNOWN
    chain_length: int = 0
    verified_blocks: int = 0
    corrupted_blocks: int = 0
    checksum_algorithm: str = "sha256"
    issues: list[str] = Field(default_factory=list)


class TieredStorageRecommendation(BaseModel):
    """Recommendation for optimal storage tier per component."""

    component_id: str
    current_tier: StorageTier
    recommended_tier: StorageTier
    current_monthly_cost: float = 0.0
    recommended_monthly_cost: float = 0.0
    savings_monthly: float = 0.0
    recovery_sla_seconds: int = 0
    explanation: str = ""


class ChainDependencyAnalysis(BaseModel):
    """Analysis of incremental backup chain dependencies."""

    component_id: str
    chain_length: int = 0
    max_safe_length: int = _MAX_SAFE_CHAIN_LENGTH
    risk_level: str = "low"  # low / medium / high / critical
    full_backup_needed: bool = False
    estimated_restore_time_multiplier: float = 1.0
    recommendations: list[str] = Field(default_factory=list)


class RetentionEvaluation(BaseModel):
    """Evaluation of a retention policy: compliance vs cost."""

    component_id: str
    retention_days: int = 0
    required_retention_days: int = 0
    compliant: bool = True
    monthly_storage_cost: float = 0.0
    annual_storage_cost: float = 0.0
    cost_if_minimal: float = 0.0
    potential_savings: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class CrossRegionDistribution(BaseModel):
    """Cross-region backup distribution analysis."""

    component_id: str
    regions: list[str] = Field(default_factory=list)
    region_count: int = 0
    monthly_transfer_cost: float = 0.0
    monthly_storage_cost: float = 0.0
    total_monthly_cost: float = 0.0
    meets_geo_redundancy: bool = False
    recommendations: list[str] = Field(default_factory=list)


class BackupPlanReport(BaseModel):
    """Comprehensive backup plan evaluation report."""

    timestamp: str = ""
    total_components: int = 0
    rto_estimates: list[RTOEstimate] = Field(default_factory=list)
    rpo_analyses: list[RPOAnalysis] = Field(default_factory=list)
    three_two_one_results: list[ThreeTwoOneResult] = Field(default_factory=list)
    window_analyses: list[BackupWindowAnalysis] = Field(default_factory=list)
    chain_analyses: list[ChainDependencyAnalysis] = Field(default_factory=list)
    tier_recommendations: list[TieredStorageRecommendation] = Field(
        default_factory=list,
    )
    retention_evaluations: list[RetentionEvaluation] = Field(default_factory=list)
    cross_region: list[CrossRegionDistribution] = Field(default_factory=list)
    overall_compliant: bool = True
    total_monthly_cost: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BackupRecoveryPlanner:
    """Plans and evaluates backup and disaster recovery strategies.

    Operates on an :class:`InfraGraph` and a mapping of
    :class:`BackupConfig` keyed by component ID.
    """

    def __init__(
        self,
        graph: InfraGraph | None = None,
        configs: dict[str, BackupConfig] | None = None,
    ) -> None:
        self.graph = graph or InfraGraph()
        self.configs: dict[str, BackupConfig] = configs or {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _effective_data_size(cfg: BackupConfig) -> float:
        """Return the effective (compressed) data size for a backup."""
        raw = cfg.data_size_gb
        factor = _STRATEGY_SIZE_FACTOR.get(cfg.strategy, 1.0)
        if cfg.strategy in (BackupStrategy.INCREMENTAL, BackupStrategy.DIFFERENTIAL,
                            BackupStrategy.CONTINUOUS, BackupStrategy.SNAPSHOT):
            raw = cfg.data_size_gb * cfg.daily_change_rate
        effective = raw * factor * cfg.compression_ratio
        return max(effective, 0.0)

    @staticmethod
    def _transfer_seconds(data_gb: float, bandwidth_mbps: float) -> float:
        """Estimate network transfer time in seconds."""
        if bandwidth_mbps <= 0:
            return float("inf")
        data_mb = data_gb * 1024.0
        return (data_mb * 8.0) / bandwidth_mbps  # bits / bps

    @staticmethod
    def _tier_for_sla(recovery_sla_seconds: int) -> StorageTier:
        """Choose the cheapest tier that satisfies the recovery SLA."""
        if recovery_sla_seconds <= 60:
            return StorageTier.HOT
        if recovery_sla_seconds <= 600:
            return StorageTier.WARM
        if recovery_sla_seconds <= 3600:
            return StorageTier.COLD
        return StorageTier.ARCHIVE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_rto(self, component_id: str) -> RTOEstimate:
        """Estimate Recovery Time Objective for *component_id*.

        RTO = tier retrieval latency + network transfer + processing overhead.
        """
        cfg = self.configs.get(component_id)
        if cfg is None:
            return RTOEstimate(
                component_id=component_id,
                strategy=BackupStrategy.FULL,
                bottleneck="no_config",
            )

        data_gb = cfg.data_size_gb * cfg.compression_ratio
        tier = cfg.storage_tier
        _TIER_RESTORE_SPEED_GB_MIN.get(tier, 1.0)

        # Tier retrieval latency: time for the storage to make data available.
        if tier == StorageTier.ARCHIVE:
            tier_retrieval_s = 3600.0 * 3  # 3 hours for deep-archive
        elif tier == StorageTier.COLD:
            tier_retrieval_s = 3600.0  # 1 hour
        elif tier == StorageTier.WARM:
            tier_retrieval_s = 300.0  # 5 min
        else:
            tier_retrieval_s = 0.0

        network_s = self._transfer_seconds(data_gb, cfg.network_bandwidth_mbps)

        # Processing overhead: decompression + integrity check.
        processing_s = data_gb * 6.0  # ~6 s/GB for decompress + verify

        # Incremental strategy needs to replay chain.
        if cfg.strategy == BackupStrategy.INCREMENTAL:
            chain_len = cfg.retention_days  # worst-case chain from last full
            if chain_len > _MAX_SAFE_CHAIN_LENGTH:
                chain_len = _MAX_SAFE_CHAIN_LENGTH
            processing_s *= 1.0 + 0.1 * chain_len

        total_s = tier_retrieval_s + network_s + processing_s

        # Identify bottleneck.
        parts = {
            "tier_retrieval": tier_retrieval_s,
            "network_transfer": network_s,
            "processing": processing_s,
        }
        bottleneck = max(parts, key=parts.get)  # type: ignore[arg-type]

        return RTOEstimate(
            component_id=component_id,
            strategy=cfg.strategy,
            estimated_rto_seconds=round(total_s, 2),
            restore_data_gb=round(data_gb, 3),
            network_transfer_seconds=round(network_s, 2),
            processing_overhead_seconds=round(processing_s, 2),
            tier_retrieval_seconds=round(tier_retrieval_s, 2),
            bottleneck=bottleneck,
        )

    def analyse_rpo(
        self,
        component_id: str,
        target_rpo_seconds: int = 3600,
    ) -> RPOAnalysis:
        """Analyse RPO guarantees for *component_id*.

        Parameters
        ----------
        component_id:
            Component to analyse.
        target_rpo_seconds:
            The desired RPO target in seconds.
        """
        cfg = self.configs.get(component_id)
        if cfg is None:
            return RPOAnalysis(
                component_id=component_id,
                strategy=BackupStrategy.FULL,
                guaranteed_rpo_seconds=0,
                meets_target=False,
                target_rpo_seconds=target_rpo_seconds,
                explanation="No backup configuration found.",
            )

        strategy = cfg.strategy
        base_rpo = _STRATEGY_RPO_SECONDS.get(strategy, 86400)

        # If custom frequency is tighter than strategy default, use it.
        freq_rpo = int(cfg.frequency_hours * 3600)
        guaranteed_rpo = min(base_rpo, freq_rpo)

        # Worst-case data loss.
        change_per_second = (cfg.data_size_gb * cfg.daily_change_rate) / 86400.0
        worst_loss_gb = change_per_second * guaranteed_rpo

        meets = guaranteed_rpo <= target_rpo_seconds

        explanation_parts: list[str] = []
        if meets:
            explanation_parts.append(
                f"Strategy '{strategy.value}' guarantees RPO of {guaranteed_rpo}s "
                f"which meets the target of {target_rpo_seconds}s."
            )
        else:
            explanation_parts.append(
                f"Strategy '{strategy.value}' guarantees RPO of {guaranteed_rpo}s "
                f"which EXCEEDS the target of {target_rpo_seconds}s."
            )
            if strategy == BackupStrategy.FULL:
                explanation_parts.append(
                    "Consider switching to incremental, differential, or continuous backups."
                )
            elif strategy in (BackupStrategy.INCREMENTAL, BackupStrategy.DIFFERENTIAL):
                explanation_parts.append(
                    "Consider increasing backup frequency or switching to continuous (CDC)."
                )

        return RPOAnalysis(
            component_id=component_id,
            strategy=strategy,
            guaranteed_rpo_seconds=guaranteed_rpo,
            worst_case_data_loss_gb=round(worst_loss_gb, 6),
            meets_target=meets,
            target_rpo_seconds=target_rpo_seconds,
            explanation=" ".join(explanation_parts),
        )

    def check_three_two_one(self, component_id: str) -> ThreeTwoOneResult:
        """Verify 3-2-1 rule compliance for *component_id*.

        The 3-2-1 rule: 3 copies, 2 different media types, 1 offsite.
        """
        cfg = self.configs.get(component_id)
        if cfg is None:
            return ThreeTwoOneResult(
                component_id=component_id,
                compliant=False,
                issues=["No backup configuration found."],
                recommendations=["Create a backup configuration for this component."],
            )

        issues: list[str] = []
        recs: list[str] = []

        copies = cfg.copies
        media = cfg.media_types
        offsite = cfg.offsite_copies

        if copies < 3:
            issues.append(f"Only {copies} copies; need at least 3.")
            recs.append("Add additional backup copies to reach a minimum of 3.")
        if media < 2:
            issues.append(f"Only {media} media type(s); need at least 2.")
            recs.append(
                "Use a second media type (e.g. tape, cloud, or different disk system)."
            )
        if offsite < 1:
            issues.append("No offsite copies; need at least 1.")
            recs.append("Store at least one backup copy in an offsite / remote location.")

        compliant = len(issues) == 0

        return ThreeTwoOneResult(
            component_id=component_id,
            compliant=compliant,
            copies=copies,
            media_types=media,
            offsite_copies=offsite,
            issues=issues,
            recommendations=recs,
        )

    def analyse_backup_window(self, component_id: str) -> BackupWindowAnalysis:
        """Determine whether the backup will complete within its maintenance window."""
        cfg = self.configs.get(component_id)
        if cfg is None:
            return BackupWindowAnalysis(
                component_id=component_id,
                fits_in_window=False,
                recommendations=["No backup configuration found."],
            )

        effective_gb = self._effective_data_size(cfg)
        transfer_s = self._transfer_seconds(effective_gb, cfg.network_bandwidth_mbps)
        processing_s = effective_gb * 6.0  # compress + checksum
        total_min = (transfer_s + processing_s) / 60.0

        window_min = cfg.backup_window_minutes
        fits = total_min <= window_min if window_min > 0 else False

        utilisation = (total_min / window_min * 100.0) if window_min > 0 else 100.0
        utilisation = min(utilisation, 100.0)

        recs: list[str] = []
        if not fits:
            recs.append(
                "Backup exceeds the maintenance window. Consider increasing "
                "bandwidth, using a more incremental strategy, or extending the window."
            )
        if utilisation > 80.0 and fits:
            recs.append(
                "Backup utilises >80% of the window. Consider adding headroom."
            )

        return BackupWindowAnalysis(
            component_id=component_id,
            estimated_backup_minutes=round(total_min, 2),
            window_minutes=window_min,
            fits_in_window=fits,
            utilisation_percent=round(utilisation, 2),
            recommendations=recs,
        )

    def simulate_restore(
        self,
        component_id: str,
        backup_age_hours: float = 0.0,
        simulate_corruption: bool = False,
    ) -> RestoreTestResult:
        """Simulate restoring from a backup point.

        Parameters
        ----------
        component_id:
            Component to restore.
        backup_age_hours:
            How old the backup is (hours since last backup).
        simulate_corruption:
            If ``True``, pretend a corruption is detected mid-restore.
        """
        cfg = self.configs.get(component_id)
        if cfg is None:
            return RestoreTestResult(
                component_id=component_id,
                success=False,
                integrity_status=IntegrityStatus.UNKNOWN,
                notes=["No backup configuration found."],
            )

        rto = self.estimate_rto(component_id)
        restore_s = rto.estimated_rto_seconds

        # Additional penalty for old backups (incremental chain replay).
        if cfg.strategy == BackupStrategy.INCREMENTAL and backup_age_hours > 0:
            chain_extra = backup_age_hours / cfg.frequency_hours
            restore_s *= 1.0 + 0.05 * chain_extra

        # Data loss is the change accumulated since the backup was taken.
        change_per_hour = (cfg.data_size_gb * cfg.daily_change_rate) / 24.0
        data_loss_gb = change_per_hour * backup_age_hours

        notes: list[str] = []
        integrity = IntegrityStatus.VALID
        success = True

        if simulate_corruption:
            integrity = IntegrityStatus.CORRUPTED
            success = False
            notes.append("Corruption detected during restore verification.")
            notes.append("Restore from an earlier clean backup is recommended.")

        if backup_age_hours > 24.0:
            notes.append(
                f"Backup is {backup_age_hours:.1f}h old; data loss may be significant."
            )

        return RestoreTestResult(
            component_id=component_id,
            backup_age_hours=backup_age_hours,
            restore_time_seconds=round(restore_s, 2),
            data_loss_gb=round(data_loss_gb, 6),
            integrity_status=integrity,
            success=success,
            notes=notes,
        )

    def verify_integrity(
        self,
        component_id: str,
        chain_length: int = 1,
        corrupted_blocks: int = 0,
        total_blocks: int = 100,
    ) -> ChecksumVerification:
        """Simulate checksum / integrity-chain verification.

        Parameters
        ----------
        component_id:
            Component whose backup integrity to verify.
        chain_length:
            Number of incremental links in the chain.
        corrupted_blocks:
            Simulated number of corrupted data blocks.
        total_blocks:
            Total data blocks checked.
        """
        issues: list[str] = []

        if corrupted_blocks > 0:
            status = IntegrityStatus.CORRUPTED
            issues.append(
                f"{corrupted_blocks} of {total_blocks} blocks failed checksum."
            )
        elif total_blocks == 0:
            status = IntegrityStatus.MISSING
            issues.append("No data blocks available for verification.")
        else:
            status = IntegrityStatus.VALID

        if chain_length > _MAX_SAFE_CHAIN_LENGTH:
            issues.append(
                f"Chain length {chain_length} exceeds safe limit of "
                f"{_MAX_SAFE_CHAIN_LENGTH}. Schedule a full backup."
            )

        verified = total_blocks - corrupted_blocks

        return ChecksumVerification(
            component_id=component_id,
            status=status,
            chain_length=chain_length,
            verified_blocks=verified,
            corrupted_blocks=corrupted_blocks,
            checksum_algorithm="sha256",
            issues=issues,
        )

    def recommend_storage_tier(
        self,
        component_id: str,
        recovery_sla_seconds: int = 3600,
    ) -> TieredStorageRecommendation:
        """Recommend optimal storage tier for *component_id*.

        The recommendation balances cost against the required recovery SLA.
        """
        cfg = self.configs.get(component_id)
        if cfg is None:
            recommended = self._tier_for_sla(recovery_sla_seconds)
            return TieredStorageRecommendation(
                component_id=component_id,
                current_tier=StorageTier.HOT,
                recommended_tier=recommended,
                recovery_sla_seconds=recovery_sla_seconds,
                explanation="No backup config; recommendation based on SLA only.",
            )

        current_tier = cfg.storage_tier
        recommended = self._tier_for_sla(recovery_sla_seconds)

        data_gb = cfg.data_size_gb * cfg.compression_ratio * cfg.retention_days
        current_cost = data_gb * _TIER_COST_PER_GB.get(current_tier, 0.023)
        recommended_cost = data_gb * _TIER_COST_PER_GB.get(recommended, 0.023)
        savings = current_cost - recommended_cost

        explanation_parts: list[str] = []
        if recommended == current_tier:
            explanation_parts.append(
                f"Current tier '{current_tier.value}' is optimal for the "
                f"{recovery_sla_seconds}s recovery SLA."
            )
        elif savings > 0:
            explanation_parts.append(
                f"Moving from '{current_tier.value}' to '{recommended.value}' "
                f"saves ${savings:.2f}/month while meeting the SLA."
            )
        else:
            explanation_parts.append(
                f"Moving from '{current_tier.value}' to '{recommended.value}' "
                f"is needed to meet the {recovery_sla_seconds}s recovery SLA "
                f"(additional ${abs(savings):.2f}/month)."
            )

        return TieredStorageRecommendation(
            component_id=component_id,
            current_tier=current_tier,
            recommended_tier=recommended,
            current_monthly_cost=round(current_cost, 2),
            recommended_monthly_cost=round(recommended_cost, 2),
            savings_monthly=round(savings, 2),
            recovery_sla_seconds=recovery_sla_seconds,
            explanation=" ".join(explanation_parts),
        )

    def analyse_chain_dependency(
        self,
        component_id: str,
        chain_length: int | None = None,
    ) -> ChainDependencyAnalysis:
        """Analyse incremental backup chain dependency risks.

        Longer chains increase restore time and fragility.
        """
        cfg = self.configs.get(component_id)

        if chain_length is None:
            if cfg is not None and cfg.strategy == BackupStrategy.INCREMENTAL:
                # Estimate chain length from retention / frequency.
                if cfg.frequency_hours > 0:
                    chain_length = int(
                        (cfg.retention_days * 24) / cfg.frequency_hours
                    )
                else:
                    chain_length = cfg.retention_days
            else:
                chain_length = 0

        max_safe = _MAX_SAFE_CHAIN_LENGTH
        recs: list[str] = []

        if chain_length <= max_safe // 2:
            risk = "low"
        elif chain_length <= max_safe:
            risk = "medium"
            recs.append("Consider scheduling a full backup soon.")
        elif chain_length <= max_safe * 2:
            risk = "high"
            recs.append("Chain is long; schedule a full backup immediately.")
        else:
            risk = "critical"
            recs.append(
                "Chain far exceeds safe limit. Restore reliability is at risk."
            )

        full_needed = chain_length > max_safe
        restore_mult = 1.0 + 0.1 * min(chain_length, 100)

        return ChainDependencyAnalysis(
            component_id=component_id,
            chain_length=chain_length,
            max_safe_length=max_safe,
            risk_level=risk,
            full_backup_needed=full_needed,
            estimated_restore_time_multiplier=round(restore_mult, 2),
            recommendations=recs,
        )

    def evaluate_retention(
        self,
        component_id: str,
        required_retention_days: int = 90,
    ) -> RetentionEvaluation:
        """Evaluate retention policy: compliance vs. cost trade-off.

        Parameters
        ----------
        component_id:
            Component to evaluate.
        required_retention_days:
            Minimum retention required for compliance.
        """
        cfg = self.configs.get(component_id)
        if cfg is None:
            return RetentionEvaluation(
                component_id=component_id,
                retention_days=0,
                required_retention_days=required_retention_days,
                compliant=False,
                recommendations=["No backup configuration found."],
            )

        ret = cfg.retention_days
        compliant = ret >= required_retention_days

        data_per_day = self._effective_data_size(cfg)
        tier_cost = _TIER_COST_PER_GB.get(cfg.storage_tier, 0.023)

        monthly_cost = data_per_day * ret * tier_cost
        annual_cost = monthly_cost * 12.0
        minimal_cost = data_per_day * required_retention_days * tier_cost
        potential_savings = max(0.0, monthly_cost - minimal_cost)

        recs: list[str] = []
        if not compliant:
            recs.append(
                f"Retention of {ret} days is below the required "
                f"{required_retention_days} days. Increase retention to comply."
            )
        if ret > required_retention_days * 2:
            recs.append(
                f"Retention of {ret} days is more than double the requirement. "
                f"Consider reducing to save ${potential_savings:.2f}/month."
            )

        return RetentionEvaluation(
            component_id=component_id,
            retention_days=ret,
            required_retention_days=required_retention_days,
            compliant=compliant,
            monthly_storage_cost=round(monthly_cost, 2),
            annual_storage_cost=round(annual_cost, 2),
            cost_if_minimal=round(minimal_cost, 2),
            potential_savings=round(potential_savings, 2),
            recommendations=recs,
        )

    def analyse_cross_region(self, component_id: str) -> CrossRegionDistribution:
        """Analyse cross-region backup distribution and cost."""
        cfg = self.configs.get(component_id)
        if cfg is None:
            return CrossRegionDistribution(
                component_id=component_id,
                meets_geo_redundancy=False,
                recommendations=["No backup configuration found."],
            )

        regions = list(cfg.regions)
        region_count = len(regions)

        data_gb = cfg.data_size_gb * cfg.compression_ratio
        # Cross-region transfer: ~$0.02/GB
        transfer_cost = data_gb * 0.02 * max(0, region_count - 1) * 30  # monthly
        storage_cost = (
            data_gb
            * cfg.retention_days
            * _TIER_COST_PER_GB.get(cfg.storage_tier, 0.023)
            * region_count
        )
        total = transfer_cost + storage_cost

        meets_geo = region_count >= 2
        recs: list[str] = []
        if not meets_geo:
            recs.append(
                "Backups are stored in fewer than 2 regions. "
                "Add at least one remote region for geo-redundancy."
            )
        if region_count > 3:
            recs.append(
                "More than 3 regions may incur unnecessary transfer costs."
            )

        return CrossRegionDistribution(
            component_id=component_id,
            regions=regions,
            region_count=region_count,
            monthly_transfer_cost=round(transfer_cost, 2),
            monthly_storage_cost=round(storage_cost, 2),
            total_monthly_cost=round(total, 2),
            meets_geo_redundancy=meets_geo,
            recommendations=recs,
        )

    # ------------------------------------------------------------------
    # Comprehensive report
    # ------------------------------------------------------------------

    def generate_report(
        self,
        target_rpo_seconds: int = 3600,
        required_retention_days: int = 90,
        recovery_sla_seconds: int = 3600,
    ) -> BackupPlanReport:
        """Generate a comprehensive backup plan report for all configured components.

        Parameters
        ----------
        target_rpo_seconds:
            Desired RPO target applied to every component.
        required_retention_days:
            Minimum retention required for compliance.
        recovery_sla_seconds:
            Recovery SLA for tiered-storage recommendation.
        """
        rto_estimates: list[RTOEstimate] = []
        rpo_analyses: list[RPOAnalysis] = []
        three_two_one: list[ThreeTwoOneResult] = []
        windows: list[BackupWindowAnalysis] = []
        chains: list[ChainDependencyAnalysis] = []
        tiers: list[TieredStorageRecommendation] = []
        retentions: list[RetentionEvaluation] = []
        cross_regions: list[CrossRegionDistribution] = []

        all_recs: list[str] = []
        overall_compliant = True
        total_cost = 0.0

        for cid in sorted(self.configs.keys()):
            rto = self.estimate_rto(cid)
            rto_estimates.append(rto)

            rpo = self.analyse_rpo(cid, target_rpo_seconds)
            rpo_analyses.append(rpo)
            if not rpo.meets_target:
                overall_compliant = False
                all_recs.append(
                    f"[{cid}] RPO target not met. {rpo.explanation}"
                )

            t321 = self.check_three_two_one(cid)
            three_two_one.append(t321)
            if not t321.compliant:
                overall_compliant = False
                all_recs.extend(f"[{cid}] {r}" for r in t321.recommendations)

            win = self.analyse_backup_window(cid)
            windows.append(win)
            if not win.fits_in_window:
                all_recs.extend(f"[{cid}] {r}" for r in win.recommendations)

            chain = self.analyse_chain_dependency(cid)
            chains.append(chain)
            if chain.full_backup_needed:
                all_recs.extend(f"[{cid}] {r}" for r in chain.recommendations)

            tier = self.recommend_storage_tier(cid, recovery_sla_seconds)
            tiers.append(tier)
            total_cost += tier.recommended_monthly_cost

            ret = self.evaluate_retention(cid, required_retention_days)
            retentions.append(ret)
            if not ret.compliant:
                overall_compliant = False
                all_recs.extend(f"[{cid}] {r}" for r in ret.recommendations)

            cr = self.analyse_cross_region(cid)
            cross_regions.append(cr)
            if not cr.meets_geo_redundancy:
                all_recs.extend(f"[{cid}] {r}" for r in cr.recommendations)

        # Deduplicate recommendations.
        seen: set[str] = set()
        unique_recs: list[str] = []
        for r in all_recs:
            if r not in seen:
                seen.add(r)
                unique_recs.append(r)

        now = datetime.now(timezone.utc).isoformat()

        return BackupPlanReport(
            timestamp=now,
            total_components=len(self.configs),
            rto_estimates=rto_estimates,
            rpo_analyses=rpo_analyses,
            three_two_one_results=three_two_one,
            window_analyses=windows,
            chain_analyses=chains,
            tier_recommendations=tiers,
            retention_evaluations=retentions,
            cross_region=cross_regions,
            overall_compliant=overall_compliant,
            total_monthly_cost=round(total_cost, 2),
            recommendations=unique_recs,
        )
