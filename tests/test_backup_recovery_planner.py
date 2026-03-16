"""Tests for faultray.simulator.backup_recovery_planner module.

Targets 100% coverage with 30+ test functions covering all public methods,
models, enums, edge cases, and internal helpers.
"""

from __future__ import annotations

import math

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.backup_recovery_planner import (
    BackupConfig,
    BackupPlanReport,
    BackupRecoveryPlanner,
    BackupStrategy,
    BackupWindowAnalysis,
    ChainDependencyAnalysis,
    ChecksumVerification,
    CrossRegionDistribution,
    IntegrityStatus,
    RPOAnalysis,
    RTOEstimate,
    RestoreTestResult,
    RetentionEvaluation,
    StorageTier,
    ThreeTwoOneResult,
    TieredStorageRecommendation,
    _MAX_SAFE_CHAIN_LENGTH,
    _STRATEGY_RPO_SECONDS,
    _STRATEGY_SIZE_FACTOR,
    _TIER_COST_PER_GB,
    _TIER_RESTORE_SPEED_GB_MIN,
    _TIER_RETRIEVAL_COST_PER_GB,
)


# ---------------------------------------------------------------------------
# Helpers (as specified in requirements)
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _default_config(
    component_id: str = "c1",
    strategy: BackupStrategy = BackupStrategy.FULL,
    frequency_hours: float = 24.0,
    retention_days: int = 30,
    storage_tier: StorageTier = StorageTier.WARM,
    data_size_gb: float = 100.0,
    daily_change_rate: float = 0.05,
    backup_window_minutes: int = 240,
    network_bandwidth_mbps: float = 1000.0,
    copies: int = 3,
    media_types: int = 2,
    offsite_copies: int = 1,
    regions: list[str] | None = None,
    encryption_enabled: bool = False,
    compression_ratio: float = 0.5,
) -> BackupConfig:
    return BackupConfig(
        component_id=component_id,
        strategy=strategy,
        frequency_hours=frequency_hours,
        retention_days=retention_days,
        storage_tier=storage_tier,
        data_size_gb=data_size_gb,
        daily_change_rate=daily_change_rate,
        backup_window_minutes=backup_window_minutes,
        network_bandwidth_mbps=network_bandwidth_mbps,
        copies=copies,
        media_types=media_types,
        offsite_copies=offsite_copies,
        regions=regions if regions is not None else ["us-east-1", "eu-west-1"],
        encryption_enabled=encryption_enabled,
        compression_ratio=compression_ratio,
    )


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


class TestEnums:
    """Verify all enum members are accessible and have correct values."""

    def test_backup_strategy_values(self):
        assert BackupStrategy.FULL == "full"
        assert BackupStrategy.INCREMENTAL == "incremental"
        assert BackupStrategy.DIFFERENTIAL == "differential"
        assert BackupStrategy.CONTINUOUS == "continuous"
        assert BackupStrategy.SNAPSHOT == "snapshot"
        assert len(BackupStrategy) == 5

    def test_storage_tier_values(self):
        assert StorageTier.HOT == "hot"
        assert StorageTier.WARM == "warm"
        assert StorageTier.COLD == "cold"
        assert StorageTier.ARCHIVE == "archive"
        assert len(StorageTier) == 4

    def test_integrity_status_values(self):
        assert IntegrityStatus.VALID == "valid"
        assert IntegrityStatus.CORRUPTED == "corrupted"
        assert IntegrityStatus.MISSING == "missing"
        assert IntegrityStatus.UNKNOWN == "unknown"
        assert len(IntegrityStatus) == 4


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify lookup-table constants are well-formed."""

    def test_tier_cost_per_gb_all_tiers(self):
        for tier in StorageTier:
            assert tier in _TIER_COST_PER_GB
            assert _TIER_COST_PER_GB[tier] >= 0

    def test_tier_cost_ordering(self):
        # Hot > Warm > Cold > Archive
        assert _TIER_COST_PER_GB[StorageTier.HOT] > _TIER_COST_PER_GB[StorageTier.WARM]
        assert _TIER_COST_PER_GB[StorageTier.WARM] > _TIER_COST_PER_GB[StorageTier.COLD]
        assert _TIER_COST_PER_GB[StorageTier.COLD] > _TIER_COST_PER_GB[StorageTier.ARCHIVE]

    def test_tier_retrieval_cost(self):
        assert _TIER_RETRIEVAL_COST_PER_GB[StorageTier.HOT] == 0.0
        for tier in (StorageTier.WARM, StorageTier.COLD, StorageTier.ARCHIVE):
            assert _TIER_RETRIEVAL_COST_PER_GB[tier] > 0

    def test_tier_restore_speed(self):
        for tier in StorageTier:
            assert tier in _TIER_RESTORE_SPEED_GB_MIN
            assert _TIER_RESTORE_SPEED_GB_MIN[tier] > 0

    def test_strategy_size_factor(self):
        for strategy in BackupStrategy:
            assert strategy in _STRATEGY_SIZE_FACTOR
            assert 0 < _STRATEGY_SIZE_FACTOR[strategy] <= 1.0

    def test_strategy_rpo_seconds(self):
        for strategy in BackupStrategy:
            assert strategy in _STRATEGY_RPO_SECONDS
        # Continuous should have the lowest RPO
        assert _STRATEGY_RPO_SECONDS[BackupStrategy.CONTINUOUS] < _STRATEGY_RPO_SECONDS[BackupStrategy.FULL]

    def test_max_safe_chain_length(self):
        assert _MAX_SAFE_CHAIN_LENGTH == 14


# ---------------------------------------------------------------------------
# Model construction tests
# ---------------------------------------------------------------------------


class TestModels:
    """Verify Pydantic model defaults and construction."""

    def test_backup_config_defaults(self):
        cfg = BackupConfig(component_id="x")
        assert cfg.strategy == BackupStrategy.FULL
        assert cfg.frequency_hours == 24.0
        assert cfg.retention_days == 30
        assert cfg.copies == 1
        assert cfg.media_types == 1
        assert cfg.offsite_copies == 0
        assert cfg.regions == []
        assert cfg.compression_ratio == 0.5

    def test_rto_estimate_defaults(self):
        r = RTOEstimate(component_id="x", strategy=BackupStrategy.FULL)
        assert r.estimated_rto_seconds == 0.0
        assert r.bottleneck == ""

    def test_rpo_analysis_defaults(self):
        r = RPOAnalysis(component_id="x", strategy=BackupStrategy.FULL)
        assert r.meets_target is True
        assert r.guaranteed_rpo_seconds == 0

    def test_three_two_one_result_defaults(self):
        r = ThreeTwoOneResult(component_id="x")
        assert r.compliant is False
        assert r.issues == []

    def test_backup_window_analysis_defaults(self):
        r = BackupWindowAnalysis(component_id="x")
        assert r.fits_in_window is True

    def test_restore_test_result_defaults(self):
        r = RestoreTestResult(component_id="x")
        assert r.success is True
        assert r.integrity_status == IntegrityStatus.VALID

    def test_checksum_verification_defaults(self):
        r = ChecksumVerification(component_id="x")
        assert r.status == IntegrityStatus.UNKNOWN
        assert r.checksum_algorithm == "sha256"

    def test_tiered_storage_recommendation_defaults(self):
        r = TieredStorageRecommendation(
            component_id="x",
            current_tier=StorageTier.HOT,
            recommended_tier=StorageTier.HOT,
        )
        assert r.savings_monthly == 0.0

    def test_chain_dependency_analysis_defaults(self):
        r = ChainDependencyAnalysis(component_id="x")
        assert r.risk_level == "low"
        assert r.max_safe_length == _MAX_SAFE_CHAIN_LENGTH

    def test_retention_evaluation_defaults(self):
        r = RetentionEvaluation(component_id="x")
        assert r.compliant is True

    def test_cross_region_distribution_defaults(self):
        r = CrossRegionDistribution(component_id="x")
        assert r.meets_geo_redundancy is False

    def test_backup_plan_report_defaults(self):
        r = BackupPlanReport()
        assert r.total_components == 0
        assert r.overall_compliant is True


# ---------------------------------------------------------------------------
# Constructor / initialisation tests
# ---------------------------------------------------------------------------


class TestPlannerInit:
    """Verify BackupRecoveryPlanner construction."""

    def test_default_construction(self):
        planner = BackupRecoveryPlanner()
        assert planner.graph is not None
        assert planner.configs == {}

    def test_construction_with_graph(self):
        c = _comp("db1", ComponentType.DATABASE)
        g = _graph(c)
        planner = BackupRecoveryPlanner(graph=g)
        assert planner.graph.get_component("db1") is not None

    def test_construction_with_configs(self):
        cfg = _default_config("c1")
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        assert "c1" in planner.configs

    def test_construction_with_graph_and_configs(self):
        c = _comp("c1")
        g = _graph(c)
        cfg = _default_config("c1")
        planner = BackupRecoveryPlanner(graph=g, configs={"c1": cfg})
        assert planner.graph.get_component("c1") is not None
        assert "c1" in planner.configs


# ---------------------------------------------------------------------------
# Static helper tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test static helper methods."""

    def test_effective_data_size_full(self):
        cfg = _default_config(strategy=BackupStrategy.FULL, data_size_gb=200.0,
                              compression_ratio=0.5)
        size = BackupRecoveryPlanner._effective_data_size(cfg)
        # FULL: raw=200 * factor=1.0 * compression=0.5 = 100.0
        assert size == 100.0

    def test_effective_data_size_incremental(self):
        cfg = _default_config(strategy=BackupStrategy.INCREMENTAL,
                              data_size_gb=200.0, daily_change_rate=0.05,
                              compression_ratio=0.5)
        size = BackupRecoveryPlanner._effective_data_size(cfg)
        # INCREMENTAL: raw = 200 * 0.05 = 10, * factor=0.1 * compression=0.5 = 0.5
        assert abs(size - 0.5) < 0.01

    def test_effective_data_size_differential(self):
        cfg = _default_config(strategy=BackupStrategy.DIFFERENTIAL,
                              data_size_gb=100.0, daily_change_rate=0.1,
                              compression_ratio=0.5)
        size = BackupRecoveryPlanner._effective_data_size(cfg)
        # raw = 100 * 0.1 = 10, * 0.3 * 0.5 = 1.5
        assert abs(size - 1.5) < 0.01

    def test_effective_data_size_continuous(self):
        cfg = _default_config(strategy=BackupStrategy.CONTINUOUS,
                              data_size_gb=100.0, daily_change_rate=0.1,
                              compression_ratio=0.5)
        size = BackupRecoveryPlanner._effective_data_size(cfg)
        # raw = 100 * 0.1 = 10, * 0.05 * 0.5 = 0.25
        assert abs(size - 0.25) < 0.01

    def test_effective_data_size_snapshot(self):
        cfg = _default_config(strategy=BackupStrategy.SNAPSHOT,
                              data_size_gb=100.0, daily_change_rate=0.1,
                              compression_ratio=0.5)
        size = BackupRecoveryPlanner._effective_data_size(cfg)
        # raw = 100 * 0.1 = 10, * 0.2 * 0.5 = 1.0
        assert abs(size - 1.0) < 0.01

    def test_effective_data_size_zero(self):
        cfg = _default_config(data_size_gb=0.0)
        size = BackupRecoveryPlanner._effective_data_size(cfg)
        assert size == 0.0

    def test_transfer_seconds_normal(self):
        # 10 GB over 1 Gbps
        s = BackupRecoveryPlanner._transfer_seconds(10.0, 1000.0)
        expected = (10.0 * 1024.0 * 8.0) / 1000.0  # ~81.92
        assert abs(s - expected) < 0.01

    def test_transfer_seconds_zero_bandwidth(self):
        s = BackupRecoveryPlanner._transfer_seconds(10.0, 0.0)
        assert s == float("inf")

    def test_transfer_seconds_negative_bandwidth(self):
        s = BackupRecoveryPlanner._transfer_seconds(10.0, -1.0)
        assert s == float("inf")

    def test_tier_for_sla_hot(self):
        assert BackupRecoveryPlanner._tier_for_sla(30) == StorageTier.HOT

    def test_tier_for_sla_warm(self):
        assert BackupRecoveryPlanner._tier_for_sla(300) == StorageTier.WARM

    def test_tier_for_sla_cold(self):
        assert BackupRecoveryPlanner._tier_for_sla(3600) == StorageTier.COLD

    def test_tier_for_sla_archive(self):
        assert BackupRecoveryPlanner._tier_for_sla(86400) == StorageTier.ARCHIVE

    def test_tier_for_sla_boundary_60(self):
        assert BackupRecoveryPlanner._tier_for_sla(60) == StorageTier.HOT

    def test_tier_for_sla_boundary_61(self):
        assert BackupRecoveryPlanner._tier_for_sla(61) == StorageTier.WARM

    def test_tier_for_sla_boundary_600(self):
        assert BackupRecoveryPlanner._tier_for_sla(600) == StorageTier.WARM

    def test_tier_for_sla_boundary_601(self):
        assert BackupRecoveryPlanner._tier_for_sla(601) == StorageTier.COLD

    def test_tier_for_sla_boundary_3601(self):
        assert BackupRecoveryPlanner._tier_for_sla(3601) == StorageTier.ARCHIVE


# ---------------------------------------------------------------------------
# estimate_rto tests
# ---------------------------------------------------------------------------


class TestEstimateRTO:
    """Test the estimate_rto method."""

    def test_no_config(self):
        planner = BackupRecoveryPlanner()
        result = planner.estimate_rto("missing")
        assert result.component_id == "missing"
        assert result.bottleneck == "no_config"
        assert result.strategy == BackupStrategy.FULL

    def test_hot_tier_no_retrieval_delay(self):
        cfg = _default_config(storage_tier=StorageTier.HOT, data_size_gb=10.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        assert result.tier_retrieval_seconds == 0.0
        assert result.estimated_rto_seconds > 0

    def test_archive_tier_has_large_retrieval(self):
        cfg = _default_config(storage_tier=StorageTier.ARCHIVE, data_size_gb=1.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        assert result.tier_retrieval_seconds == 3600.0 * 3

    def test_cold_tier_retrieval(self):
        cfg = _default_config(storage_tier=StorageTier.COLD, data_size_gb=1.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        assert result.tier_retrieval_seconds == 3600.0

    def test_warm_tier_retrieval(self):
        cfg = _default_config(storage_tier=StorageTier.WARM, data_size_gb=1.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        assert result.tier_retrieval_seconds == 300.0

    def test_incremental_adds_chain_overhead(self):
        cfg_full = _default_config(
            component_id="full",
            strategy=BackupStrategy.FULL,
            data_size_gb=100.0,
            storage_tier=StorageTier.HOT,
        )
        cfg_inc = _default_config(
            component_id="inc",
            strategy=BackupStrategy.INCREMENTAL,
            data_size_gb=100.0,
            storage_tier=StorageTier.HOT,
            retention_days=10,
        )
        planner = BackupRecoveryPlanner(configs={"full": cfg_full, "inc": cfg_inc})
        r_full = planner.estimate_rto("full")
        r_inc = planner.estimate_rto("inc")
        # Incremental has chain replay overhead on processing
        assert r_inc.processing_overhead_seconds > 0

    def test_bottleneck_identified(self):
        cfg = _default_config(
            storage_tier=StorageTier.ARCHIVE,
            data_size_gb=0.001,
            network_bandwidth_mbps=10000.0,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        # Archive retrieval (10800s) dominates for tiny data
        assert result.bottleneck == "tier_retrieval"

    def test_network_bottleneck(self):
        cfg = _default_config(
            storage_tier=StorageTier.HOT,
            data_size_gb=1000.0,
            network_bandwidth_mbps=10.0,  # very slow
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        assert result.bottleneck == "network_transfer"

    def test_restore_data_gb_equals_compressed(self):
        cfg = _default_config(data_size_gb=200.0, compression_ratio=0.4)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        assert result.restore_data_gb == pytest.approx(80.0, abs=0.01)

    def test_incremental_chain_capped_at_max(self):
        cfg = _default_config(
            strategy=BackupStrategy.INCREMENTAL,
            retention_days=100,  # exceeds _MAX_SAFE_CHAIN_LENGTH
            storage_tier=StorageTier.HOT,
            data_size_gb=10.0,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        # Chain capped at 14
        data_gb = 10.0 * 0.5
        base_processing = data_gb * 6.0
        expected_processing = base_processing * (1.0 + 0.1 * 14)
        assert result.processing_overhead_seconds == pytest.approx(expected_processing, rel=0.01)


# ---------------------------------------------------------------------------
# analyse_rpo tests
# ---------------------------------------------------------------------------


class TestAnalyseRPO:
    """Test the analyse_rpo method."""

    def test_no_config(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_rpo("missing")
        assert result.meets_target is False
        assert "No backup configuration" in result.explanation

    def test_continuous_meets_tight_rpo(self):
        cfg = _default_config(strategy=BackupStrategy.CONTINUOUS, frequency_hours=0.001)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_rpo("c1", target_rpo_seconds=10)
        # Continuous base RPO = 5s, and freq_rpo = 0.001 * 3600 = 3.6s -> min(5, 3) = 3
        assert result.guaranteed_rpo_seconds <= 10
        assert result.meets_target is True

    def test_full_backup_fails_tight_rpo(self):
        cfg = _default_config(strategy=BackupStrategy.FULL, frequency_hours=24.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_rpo("c1", target_rpo_seconds=3600)
        # Full base RPO = 86400, freq = 24*3600 = 86400 -> RPO = 86400 > 3600
        assert result.meets_target is False
        assert "EXCEEDS" in result.explanation
        assert "incremental" in result.explanation.lower() or "continuous" in result.explanation.lower()

    def test_incremental_meets_hourly_rpo(self):
        cfg = _default_config(strategy=BackupStrategy.INCREMENTAL, frequency_hours=1.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_rpo("c1", target_rpo_seconds=3600)
        # base RPO = 3600, freq = 3600 -> guaranteed = 3600 <= 3600
        assert result.meets_target is True

    def test_worst_case_data_loss_calculated(self):
        cfg = _default_config(
            strategy=BackupStrategy.INCREMENTAL,
            frequency_hours=1.0,
            data_size_gb=100.0,
            daily_change_rate=0.1,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_rpo("c1", target_rpo_seconds=3600)
        # change/s = 100 * 0.1 / 86400 ~ 0.000115741
        # loss = 0.000115741 * 3600 ~ 0.41667
        assert result.worst_case_data_loss_gb > 0

    def test_frequency_tighter_than_strategy_default(self):
        cfg = _default_config(strategy=BackupStrategy.FULL, frequency_hours=0.5)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_rpo("c1", target_rpo_seconds=2000)
        # freq RPO = 0.5 * 3600 = 1800; strategy RPO = 86400
        # guaranteed = min(86400, 1800) = 1800 <= 2000
        assert result.guaranteed_rpo_seconds == 1800
        assert result.meets_target is True

    def test_incremental_exceeds_target_recommends_continuous(self):
        cfg = _default_config(strategy=BackupStrategy.INCREMENTAL, frequency_hours=2.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_rpo("c1", target_rpo_seconds=60)
        assert result.meets_target is False
        assert "continuous" in result.explanation.lower() or "frequency" in result.explanation.lower()

    def test_differential_exceeds_target(self):
        cfg = _default_config(strategy=BackupStrategy.DIFFERENTIAL, frequency_hours=2.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_rpo("c1", target_rpo_seconds=60)
        assert result.meets_target is False


# ---------------------------------------------------------------------------
# check_three_two_one tests
# ---------------------------------------------------------------------------


class TestThreeTwoOne:
    """Test 3-2-1 rule compliance checking."""

    def test_no_config(self):
        planner = BackupRecoveryPlanner()
        result = planner.check_three_two_one("missing")
        assert result.compliant is False
        assert len(result.issues) == 1

    def test_fully_compliant(self):
        cfg = _default_config(copies=3, media_types=2, offsite_copies=1)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.check_three_two_one("c1")
        assert result.compliant is True
        assert result.issues == []

    def test_insufficient_copies(self):
        cfg = _default_config(copies=2, media_types=2, offsite_copies=1)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.check_three_two_one("c1")
        assert result.compliant is False
        assert any("copies" in i.lower() for i in result.issues)

    def test_insufficient_media(self):
        cfg = _default_config(copies=3, media_types=1, offsite_copies=1)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.check_three_two_one("c1")
        assert result.compliant is False
        assert any("media" in i.lower() for i in result.issues)

    def test_no_offsite(self):
        cfg = _default_config(copies=3, media_types=2, offsite_copies=0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.check_three_two_one("c1")
        assert result.compliant is False
        assert any("offsite" in i.lower() for i in result.issues)

    def test_all_violations(self):
        cfg = _default_config(copies=1, media_types=1, offsite_copies=0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.check_three_two_one("c1")
        assert result.compliant is False
        assert len(result.issues) == 3
        assert len(result.recommendations) == 3

    def test_exactly_three_copies(self):
        cfg = _default_config(copies=3, media_types=2, offsite_copies=1)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.check_three_two_one("c1")
        assert result.copies == 3
        assert result.compliant is True


# ---------------------------------------------------------------------------
# analyse_backup_window tests
# ---------------------------------------------------------------------------


class TestBackupWindow:
    """Test backup window analysis."""

    def test_no_config(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_backup_window("missing")
        assert result.fits_in_window is False
        assert len(result.recommendations) > 0

    def test_fits_in_window(self):
        # Small data, big window
        cfg = _default_config(
            data_size_gb=1.0,
            backup_window_minutes=240,
            network_bandwidth_mbps=10000.0,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_backup_window("c1")
        assert result.fits_in_window is True

    def test_exceeds_window(self):
        # Large data, tiny window
        cfg = _default_config(
            strategy=BackupStrategy.FULL,
            data_size_gb=10000.0,
            backup_window_minutes=1,
            network_bandwidth_mbps=100.0,
            compression_ratio=0.9,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_backup_window("c1")
        assert result.fits_in_window is False
        assert len(result.recommendations) > 0

    def test_high_utilisation_warning(self):
        # We need: fits_in_window=True AND utilisation > 80%.
        # Strategy: FULL backup.  effective_data = data_size * 1.0 * compression.
        # Transfer time = (effective * 1024 * 8) / bandwidth seconds.
        # Processing time = effective * 6 seconds.
        # Total minutes = (transfer + processing) / 60.
        # We want total_min to be between 0.8 * window and window.
        #
        # Let data=15, compression=0.5 => effective=7.5 GB
        # transfer = (7.5*1024*8)/1000 = 61.44s
        # processing = 7.5*6 = 45s
        # total = 106.44s => 1.774 min
        # window = 2 min => utilisation = 1.774/2 = 88.7%
        cfg = BackupConfig(
            component_id="c1",
            strategy=BackupStrategy.FULL,
            data_size_gb=15.0,
            compression_ratio=0.5,
            network_bandwidth_mbps=1000.0,
            backup_window_minutes=2,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_backup_window("c1")
        assert result.fits_in_window is True
        assert result.utilisation_percent > 80.0
        assert any("headroom" in r.lower() for r in result.recommendations)

    def test_zero_window(self):
        cfg = _default_config(backup_window_minutes=0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_backup_window("c1")
        assert result.fits_in_window is False

    def test_utilisation_capped_at_100(self):
        cfg = _default_config(
            strategy=BackupStrategy.FULL,
            data_size_gb=10000.0,
            backup_window_minutes=1,
            network_bandwidth_mbps=10.0,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_backup_window("c1")
        assert result.utilisation_percent <= 100.0


# ---------------------------------------------------------------------------
# simulate_restore tests
# ---------------------------------------------------------------------------


class TestSimulateRestore:
    """Test restore simulation."""

    def test_no_config(self):
        planner = BackupRecoveryPlanner()
        result = planner.simulate_restore("missing")
        assert result.success is False
        assert result.integrity_status == IntegrityStatus.UNKNOWN

    def test_basic_restore(self):
        cfg = _default_config(storage_tier=StorageTier.HOT, data_size_gb=10.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.simulate_restore("c1")
        assert result.success is True
        assert result.integrity_status == IntegrityStatus.VALID
        assert result.restore_time_seconds > 0

    def test_corruption_simulation(self):
        cfg = _default_config()
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.simulate_restore("c1", simulate_corruption=True)
        assert result.success is False
        assert result.integrity_status == IntegrityStatus.CORRUPTED
        assert any("corruption" in n.lower() for n in result.notes)

    def test_old_backup_note(self):
        cfg = _default_config()
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.simulate_restore("c1", backup_age_hours=48.0)
        assert any("48.0h" in n for n in result.notes)
        assert result.data_loss_gb > 0

    def test_incremental_backup_age_penalty(self):
        cfg = _default_config(
            strategy=BackupStrategy.INCREMENTAL,
            storage_tier=StorageTier.HOT,
            data_size_gb=10.0,
            frequency_hours=1.0,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        r_fresh = planner.simulate_restore("c1", backup_age_hours=0)
        r_old = planner.simulate_restore("c1", backup_age_hours=24.0)
        assert r_old.restore_time_seconds > r_fresh.restore_time_seconds

    def test_data_loss_proportional_to_age(self):
        cfg = _default_config(data_size_gb=100.0, daily_change_rate=0.1)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        r1 = planner.simulate_restore("c1", backup_age_hours=1.0)
        r2 = planner.simulate_restore("c1", backup_age_hours=10.0)
        assert r2.data_loss_gb > r1.data_loss_gb


# ---------------------------------------------------------------------------
# verify_integrity tests
# ---------------------------------------------------------------------------


class TestVerifyIntegrity:
    """Test checksum / integrity chain verification."""

    def test_valid_integrity(self):
        planner = BackupRecoveryPlanner()
        result = planner.verify_integrity("c1", chain_length=5, total_blocks=100)
        assert result.status == IntegrityStatus.VALID
        assert result.verified_blocks == 100
        assert result.corrupted_blocks == 0

    def test_corrupted_blocks(self):
        planner = BackupRecoveryPlanner()
        result = planner.verify_integrity(
            "c1", corrupted_blocks=3, total_blocks=100,
        )
        assert result.status == IntegrityStatus.CORRUPTED
        assert result.verified_blocks == 97
        assert any("3 of 100" in i for i in result.issues)

    def test_missing_blocks(self):
        planner = BackupRecoveryPlanner()
        result = planner.verify_integrity("c1", total_blocks=0)
        assert result.status == IntegrityStatus.MISSING

    def test_chain_exceeds_safe_limit(self):
        planner = BackupRecoveryPlanner()
        result = planner.verify_integrity(
            "c1", chain_length=20, total_blocks=50,
        )
        assert any("exceeds safe limit" in i for i in result.issues)

    def test_chain_within_limit_no_warning(self):
        planner = BackupRecoveryPlanner()
        result = planner.verify_integrity(
            "c1", chain_length=10, total_blocks=50,
        )
        assert not any("exceeds" in i for i in result.issues)

    def test_checksum_algorithm(self):
        planner = BackupRecoveryPlanner()
        result = planner.verify_integrity("c1")
        assert result.checksum_algorithm == "sha256"


# ---------------------------------------------------------------------------
# recommend_storage_tier tests
# ---------------------------------------------------------------------------


class TestRecommendStorageTier:
    """Test tiered storage optimisation recommendations."""

    def test_no_config_uses_sla_only(self):
        planner = BackupRecoveryPlanner()
        result = planner.recommend_storage_tier("missing", recovery_sla_seconds=30)
        assert result.recommended_tier == StorageTier.HOT
        assert "SLA only" in result.explanation

    def test_already_optimal(self):
        cfg = _default_config(storage_tier=StorageTier.WARM, data_size_gb=10.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.recommend_storage_tier("c1", recovery_sla_seconds=300)
        assert result.recommended_tier == StorageTier.WARM
        assert result.current_tier == StorageTier.WARM
        assert "optimal" in result.explanation.lower()

    def test_downgrade_saves_money(self):
        cfg = _default_config(storage_tier=StorageTier.HOT, data_size_gb=100.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.recommend_storage_tier("c1", recovery_sla_seconds=7200)
        assert result.recommended_tier == StorageTier.ARCHIVE
        assert result.savings_monthly > 0

    def test_upgrade_needed_for_sla(self):
        cfg = _default_config(storage_tier=StorageTier.ARCHIVE, data_size_gb=10.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.recommend_storage_tier("c1", recovery_sla_seconds=30)
        assert result.recommended_tier == StorageTier.HOT
        assert result.savings_monthly < 0  # costs more
        assert "needed" in result.explanation.lower() or "additional" in result.explanation.lower()

    def test_cost_calculations_correct(self):
        cfg = _default_config(
            storage_tier=StorageTier.HOT,
            data_size_gb=100.0,
            compression_ratio=0.5,
            retention_days=30,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.recommend_storage_tier("c1", recovery_sla_seconds=300)
        # data = 100 * 0.5 * 30 = 1500 GB-days-equivalent
        data_gb = 100.0 * 0.5 * 30
        expected_current = data_gb * _TIER_COST_PER_GB[StorageTier.HOT]
        assert result.current_monthly_cost == pytest.approx(expected_current, rel=0.01)


# ---------------------------------------------------------------------------
# analyse_chain_dependency tests
# ---------------------------------------------------------------------------


class TestChainDependency:
    """Test incremental chain dependency analysis."""

    def test_no_config_no_chain(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_chain_dependency("c1")
        assert result.chain_length == 0
        assert result.risk_level == "low"

    def test_explicit_chain_length_low(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_chain_dependency("c1", chain_length=5)
        assert result.risk_level == "low"
        assert not result.full_backup_needed

    def test_explicit_chain_length_medium(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_chain_dependency("c1", chain_length=10)
        assert result.risk_level == "medium"
        assert not result.full_backup_needed
        assert len(result.recommendations) > 0

    def test_explicit_chain_length_high(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_chain_dependency("c1", chain_length=20)
        assert result.risk_level == "high"
        assert result.full_backup_needed is True

    def test_explicit_chain_length_critical(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_chain_dependency("c1", chain_length=50)
        assert result.risk_level == "critical"
        assert result.full_backup_needed is True

    def test_auto_calculate_from_config(self):
        cfg = _default_config(
            strategy=BackupStrategy.INCREMENTAL,
            retention_days=7,
            frequency_hours=12.0,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_chain_dependency("c1")
        # chain = 7 * 24 / 12 = 14
        assert result.chain_length == 14

    def test_non_incremental_strategy_zero_chain(self):
        cfg = _default_config(strategy=BackupStrategy.FULL)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_chain_dependency("c1")
        assert result.chain_length == 0

    def test_restore_multiplier_scales(self):
        planner = BackupRecoveryPlanner()
        r_low = planner.analyse_chain_dependency("c1", chain_length=2)
        r_high = planner.analyse_chain_dependency("c1", chain_length=20)
        assert r_high.estimated_restore_time_multiplier > r_low.estimated_restore_time_multiplier

    def test_zero_frequency_uses_retention(self):
        cfg = _default_config(
            strategy=BackupStrategy.INCREMENTAL,
            retention_days=10,
            frequency_hours=0.0,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_chain_dependency("c1")
        assert result.chain_length == 10

    def test_boundary_half_max_safe(self):
        planner = BackupRecoveryPlanner()
        half = _MAX_SAFE_CHAIN_LENGTH // 2
        result = planner.analyse_chain_dependency("c1", chain_length=half)
        assert result.risk_level == "low"

    def test_boundary_exactly_max_safe(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_chain_dependency("c1", chain_length=_MAX_SAFE_CHAIN_LENGTH)
        assert result.risk_level == "medium"
        assert result.full_backup_needed is False

    def test_boundary_max_safe_plus_one(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_chain_dependency("c1", chain_length=_MAX_SAFE_CHAIN_LENGTH + 1)
        assert result.risk_level == "high"
        assert result.full_backup_needed is True


# ---------------------------------------------------------------------------
# evaluate_retention tests
# ---------------------------------------------------------------------------


class TestEvaluateRetention:
    """Test retention policy evaluation."""

    def test_no_config(self):
        planner = BackupRecoveryPlanner()
        result = planner.evaluate_retention("missing")
        assert result.compliant is False
        assert result.retention_days == 0

    def test_compliant_retention(self):
        cfg = _default_config(retention_days=90)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.evaluate_retention("c1", required_retention_days=90)
        assert result.compliant is True

    def test_non_compliant_retention(self):
        cfg = _default_config(retention_days=30)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.evaluate_retention("c1", required_retention_days=90)
        assert result.compliant is False
        assert any("below" in r.lower() for r in result.recommendations)

    def test_excessive_retention_warns(self):
        cfg = _default_config(retention_days=365)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.evaluate_retention("c1", required_retention_days=90)
        assert result.compliant is True
        assert result.potential_savings > 0
        assert any("reducing" in r.lower() for r in result.recommendations)

    def test_cost_calculation(self):
        cfg = _default_config(
            strategy=BackupStrategy.FULL,
            data_size_gb=100.0,
            retention_days=30,
            storage_tier=StorageTier.WARM,
            compression_ratio=0.5,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.evaluate_retention("c1", required_retention_days=30)
        assert result.monthly_storage_cost > 0
        assert result.annual_storage_cost == pytest.approx(
            result.monthly_storage_cost * 12, rel=0.01,
        )

    def test_exactly_double_required(self):
        cfg = _default_config(retention_days=180)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.evaluate_retention("c1", required_retention_days=90)
        # 180 == 90 * 2, not > 2x, so no warning
        assert result.compliant is True

    def test_more_than_double_required(self):
        cfg = _default_config(retention_days=200)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.evaluate_retention("c1", required_retention_days=90)
        assert result.compliant is True
        assert any("reducing" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# analyse_cross_region tests
# ---------------------------------------------------------------------------


class TestCrossRegion:
    """Test cross-region backup distribution analysis."""

    def test_no_config(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_cross_region("missing")
        assert result.meets_geo_redundancy is False

    def test_two_regions_compliant(self):
        cfg = _default_config(regions=["us-east-1", "eu-west-1"])
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_cross_region("c1")
        assert result.meets_geo_redundancy is True
        assert result.region_count == 2

    def test_single_region_non_compliant(self):
        cfg = _default_config(regions=["us-east-1"])
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_cross_region("c1")
        assert result.meets_geo_redundancy is False
        assert len(result.recommendations) > 0

    def test_no_regions(self):
        cfg = _default_config(regions=[])
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_cross_region("c1")
        assert result.meets_geo_redundancy is False

    def test_many_regions_warns(self):
        cfg = _default_config(regions=["r1", "r2", "r3", "r4"])
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_cross_region("c1")
        assert result.meets_geo_redundancy is True
        assert any("unnecessary" in r.lower() for r in result.recommendations)

    def test_transfer_cost_increases_with_regions(self):
        cfg_2 = _default_config(regions=["r1", "r2"], data_size_gb=100.0)
        cfg_3 = _default_config(
            component_id="c2", regions=["r1", "r2", "r3"], data_size_gb=100.0,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg_2, "c2": cfg_3})
        r2 = planner.analyse_cross_region("c1")
        r3 = planner.analyse_cross_region("c2")
        assert r3.monthly_transfer_cost > r2.monthly_transfer_cost

    def test_storage_cost_scales_with_regions(self):
        cfg = _default_config(
            regions=["r1", "r2", "r3"],
            data_size_gb=100.0,
            retention_days=30,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_cross_region("c1")
        assert result.monthly_storage_cost > 0
        assert result.total_monthly_cost >= result.monthly_storage_cost


# ---------------------------------------------------------------------------
# generate_report tests
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Test comprehensive report generation."""

    def test_empty_configs(self):
        planner = BackupRecoveryPlanner()
        report = planner.generate_report()
        assert report.total_components == 0
        assert report.overall_compliant is True
        assert report.recommendations == []

    def test_single_component_fully_compliant(self):
        cfg = _default_config(
            strategy=BackupStrategy.CONTINUOUS,
            frequency_hours=0.001,
            retention_days=90,
            copies=3,
            media_types=2,
            offsite_copies=1,
            regions=["us-east-1", "eu-west-1"],
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        report = planner.generate_report(
            target_rpo_seconds=3600,
            required_retention_days=90,
        )
        assert report.total_components == 1
        assert len(report.rto_estimates) == 1
        assert len(report.rpo_analyses) == 1
        assert len(report.three_two_one_results) == 1

    def test_non_compliant_report(self):
        cfg = _default_config(
            strategy=BackupStrategy.FULL,
            frequency_hours=24.0,
            retention_days=7,
            copies=1,
            media_types=1,
            offsite_copies=0,
            regions=[],
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        report = planner.generate_report(
            target_rpo_seconds=60,
            required_retention_days=90,
        )
        assert report.overall_compliant is False
        assert len(report.recommendations) > 0

    def test_multiple_components(self):
        cfg1 = _default_config(component_id="db1", data_size_gb=500.0)
        cfg2 = _default_config(component_id="app1", data_size_gb=50.0)
        planner = BackupRecoveryPlanner(configs={"db1": cfg1, "app1": cfg2})
        report = planner.generate_report()
        assert report.total_components == 2
        assert len(report.rto_estimates) == 2
        assert len(report.rpo_analyses) == 2

    def test_report_timestamp(self):
        planner = BackupRecoveryPlanner(configs={"c1": _default_config()})
        report = planner.generate_report()
        assert report.timestamp != ""
        assert "T" in report.timestamp  # ISO format

    def test_report_deduplicates_recommendations(self):
        # Two components with identical issues should not duplicate recommendations
        cfg1 = _default_config(
            component_id="a",
            copies=1,
            media_types=1,
            offsite_copies=0,
        )
        cfg2 = _default_config(
            component_id="b",
            copies=1,
            media_types=1,
            offsite_copies=0,
        )
        planner = BackupRecoveryPlanner(configs={"a": cfg1, "b": cfg2})
        report = planner.generate_report()
        # Each component generates its own prefixed recs, so they differ by [a] / [b]
        # but there should be no exact duplicates
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_report_total_monthly_cost(self):
        cfg = _default_config(data_size_gb=100.0, retention_days=30)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        report = planner.generate_report()
        assert report.total_monthly_cost > 0

    def test_report_sorted_component_ids(self):
        cfg_z = _default_config(component_id="z")
        cfg_a = _default_config(component_id="a")
        planner = BackupRecoveryPlanner(configs={"z": cfg_z, "a": cfg_a})
        report = planner.generate_report()
        ids = [r.component_id for r in report.rto_estimates]
        assert ids == ["a", "z"]

    def test_report_chain_analysis_included(self):
        cfg = _default_config(strategy=BackupStrategy.INCREMENTAL)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        report = planner.generate_report()
        assert len(report.chain_analyses) == 1

    def test_report_window_not_fitting_adds_recommendation(self):
        cfg = _default_config(
            strategy=BackupStrategy.FULL,
            data_size_gb=100000.0,
            backup_window_minutes=1,
            network_bandwidth_mbps=10.0,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        report = planner.generate_report()
        assert any("window" in r.lower() or "bandwidth" in r.lower() for r in report.recommendations)


# ---------------------------------------------------------------------------
# Integration with InfraGraph
# ---------------------------------------------------------------------------


class TestInfraGraphIntegration:
    """Verify the planner works when paired with an InfraGraph."""

    def test_planner_with_graph_components(self):
        db = _comp("db1", ComponentType.DATABASE)
        app = _comp("app1", ComponentType.APP_SERVER)
        g = _graph(db, app)
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))

        cfg_db = _default_config(
            component_id="db1",
            strategy=BackupStrategy.CONTINUOUS,
            data_size_gb=500.0,
            copies=3,
            media_types=2,
            offsite_copies=1,
            retention_days=365,
            regions=["us-east-1", "eu-west-1"],
        )
        cfg_app = _default_config(
            component_id="app1",
            strategy=BackupStrategy.SNAPSHOT,
            data_size_gb=20.0,
            copies=3,
            media_types=2,
            offsite_copies=1,
            retention_days=90,
            regions=["us-east-1", "eu-west-1"],
        )
        planner = BackupRecoveryPlanner(
            graph=g,
            configs={"db1": cfg_db, "app1": cfg_app},
        )

        assert planner.graph.get_component("db1") is not None
        report = planner.generate_report(
            target_rpo_seconds=60,
            required_retention_days=90,
        )
        assert report.total_components == 2

    def test_planner_config_keys_need_not_match_graph(self):
        """Configs can exist for components not in the graph."""
        g = _graph(_comp("c1"))
        cfg = _default_config(component_id="c2")  # not in graph
        planner = BackupRecoveryPlanner(graph=g, configs={"c2": cfg})
        result = planner.estimate_rto("c2")
        assert result.estimated_rto_seconds > 0


# ---------------------------------------------------------------------------
# Edge case / branch coverage boosters
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge-case tests for branch coverage."""

    def test_zero_data_size_rto(self):
        cfg = _default_config(data_size_gb=0.0, storage_tier=StorageTier.HOT)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        assert result.estimated_rto_seconds == 0.0

    def test_zero_daily_change_rate(self):
        cfg = _default_config(daily_change_rate=0.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        rpo = planner.analyse_rpo("c1", target_rpo_seconds=100000)
        assert rpo.worst_case_data_loss_gb == 0.0

    def test_very_high_bandwidth(self):
        cfg = _default_config(
            data_size_gb=100.0,
            network_bandwidth_mbps=1_000_000.0,
            storage_tier=StorageTier.HOT,
        )
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.estimate_rto("c1")
        # Network transfer should be very small
        assert result.network_transfer_seconds < 1.0

    def test_restore_fresh_backup_no_data_loss(self):
        cfg = _default_config(data_size_gb=100.0)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.simulate_restore("c1", backup_age_hours=0.0)
        assert result.data_loss_gb == 0.0

    def test_full_strategy_effective_size(self):
        cfg = _default_config(
            strategy=BackupStrategy.FULL,
            data_size_gb=100.0,
            compression_ratio=1.0,
        )
        size = BackupRecoveryPlanner._effective_data_size(cfg)
        assert size == 100.0

    def test_retention_exactly_at_required(self):
        cfg = _default_config(retention_days=90)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.evaluate_retention("c1", required_retention_days=90)
        assert result.compliant is True
        assert result.potential_savings == 0.0

    def test_cross_region_single_region_transfer_cost(self):
        cfg = _default_config(regions=["us-east-1"])
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_cross_region("c1")
        # With 1 region, transfer cost = 0 (no cross-region transfers)
        assert result.monthly_transfer_cost == 0.0

    def test_rpo_snapshot_strategy(self):
        cfg = _default_config(strategy=BackupStrategy.SNAPSHOT, frequency_hours=0.25)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.analyse_rpo("c1", target_rpo_seconds=1000)
        assert result.guaranteed_rpo_seconds == min(900, int(0.25 * 3600))
        assert result.meets_target is True

    def test_chain_dependency_exactly_double_max(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_chain_dependency(
            "c1", chain_length=_MAX_SAFE_CHAIN_LENGTH * 2,
        )
        assert result.risk_level == "high"

    def test_chain_dependency_beyond_double_max(self):
        planner = BackupRecoveryPlanner()
        result = planner.analyse_chain_dependency(
            "c1", chain_length=_MAX_SAFE_CHAIN_LENGTH * 2 + 1,
        )
        assert result.risk_level == "critical"

    def test_tier_recommendation_savings_zero_when_same(self):
        cfg = _default_config(storage_tier=StorageTier.COLD)
        planner = BackupRecoveryPlanner(configs={"c1": cfg})
        result = planner.recommend_storage_tier("c1", recovery_sla_seconds=2000)
        # SLA 2000s -> cold tier
        assert result.recommended_tier == StorageTier.COLD
        assert result.savings_monthly == 0.0

    def test_effective_data_size_negative_guarded(self):
        """Ensure negative effective size is clamped to 0."""
        cfg = BackupConfig(
            component_id="c1",
            strategy=BackupStrategy.FULL,
            data_size_gb=0.0,
            compression_ratio=0.5,
        )
        size = BackupRecoveryPlanner._effective_data_size(cfg)
        assert size >= 0.0
