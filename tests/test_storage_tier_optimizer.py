"""Tests for the Storage Tier Optimizer module.

Covers storage tier recommendation, cost modeling (including IOPS costs),
lifecycle rule generation, deduplication/compression analysis, cross-region
replication cost estimation, capacity projection, data classification,
compliance retention checks, latency impact, transition cost, SLA constraint
handling, and full report generation.  Targets 100% branch coverage.
"""

from __future__ import annotations

import math
from unittest.mock import patch

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.storage_tier_optimizer import (
    AccessPattern,
    CapacityProjection,
    ComplianceCheck,
    ComplianceFramework,
    CrossRegionCost,
    CROSS_REGION_REPLICATION_COST_PER_GB,
    DataAccessProfile,
    DataClassification,
    DeduplicationOpportunity,
    LifecycleRule,
    READ_IOPS_COST,
    RETRIEVAL_LATENCY_MS,
    RiskLevel,
    STORAGE_COST_PER_GB,
    StorageTier,
    StorageTierOptimizer,
    StorageTierReport,
    TierRecommendation,
    TRANSITION_COST_PER_GB,
    WRITE_IOPS_COST,
    _classify_temperature,
    _determine_risk,
    _monthly_iops_cost,
    _monthly_storage_cost,
    _recommend_tier,
    _total_monthly_cost,
    _total_monthly_cost_on_tier,
    _transition_cost,
    COMPLIANCE_RETENTION_DAYS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _storage_comp(cid="s1", disk_gb=500.0):
    return Component(
        id=cid,
        name=cid,
        type=ComponentType.STORAGE,
    )


def _db_comp(cid="db1", disk_gb=200.0):
    return Component(
        id=cid,
        name=cid,
        type=ComponentType.DATABASE,
    )


def _hot_profile(cid="s1", size_gb=100.0, **kwargs):
    """Create a high-frequency hot profile."""
    defaults = dict(
        component_id=cid,
        data_size_gb=size_gb,
        current_tier=StorageTier.HOT,
        read_iops=2000.0,
        write_iops=500.0,
        read_frequency_per_day=50000.0,
        write_frequency_per_day=10000.0,
        last_access_days_ago=0,
        data_age_days=10,
    )
    defaults.update(kwargs)
    return DataAccessProfile(**defaults)


def _cold_profile(cid="s1", size_gb=500.0, **kwargs):
    """Create a low-frequency cold-eligible profile."""
    defaults = dict(
        component_id=cid,
        data_size_gb=size_gb,
        current_tier=StorageTier.HOT,
        read_iops=0.0,
        write_iops=0.0,
        read_frequency_per_day=2.0,
        write_frequency_per_day=0.0,
        last_access_days_ago=200,
        data_age_days=365,
    )
    defaults.update(kwargs)
    return DataAccessProfile(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStorageTierEnums:
    """Verify enum values for tiers, patterns, and frameworks."""

    def test_storage_tier_values(self):
        assert StorageTier.HOT.value == "hot"
        assert StorageTier.WARM.value == "warm"
        assert StorageTier.COLD.value == "cold"
        assert StorageTier.ARCHIVE.value == "archive"

    def test_access_pattern_values(self):
        assert AccessPattern.SEQUENTIAL_READ.value == "sequential_read"
        assert AccessPattern.RANDOM_WRITE.value == "random_write"
        assert AccessPattern.MIXED.value == "mixed"

    def test_compliance_framework_values(self):
        assert ComplianceFramework.GDPR.value == "gdpr"
        assert ComplianceFramework.HIPAA.value == "hipaa"
        assert ComplianceFramework.SOX.value == "sox"
        assert ComplianceFramework.PCI_DSS.value == "pci_dss"
        assert ComplianceFramework.CUSTOM.value == "custom"

    def test_risk_level_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"


class TestCostHelpers:
    """Test low-level cost computation helpers."""

    def test_monthly_storage_cost(self):
        cost = _monthly_storage_cost(StorageTier.HOT, 100.0)
        assert cost == STORAGE_COST_PER_GB[StorageTier.HOT] * 100.0

    def test_monthly_storage_cost_archive(self):
        cost = _monthly_storage_cost(StorageTier.ARCHIVE, 1000.0)
        assert cost == STORAGE_COST_PER_GB[StorageTier.ARCHIVE] * 1000.0

    def test_monthly_iops_cost_hot(self):
        cost = _monthly_iops_cost(StorageTier.HOT, 100.0, 50.0)
        secs = 30.0 * 24.0 * 3600.0
        expected_read = (100.0 * secs / 1000.0) * READ_IOPS_COST[StorageTier.HOT]
        expected_write = (50.0 * secs / 1000.0) * WRITE_IOPS_COST[StorageTier.HOT]
        assert abs(cost - (expected_read + expected_write)) < 0.01

    def test_monthly_iops_cost_archive(self):
        cost = _monthly_iops_cost(StorageTier.ARCHIVE, 0.0, 0.0)
        assert cost == 0.0

    def test_total_monthly_cost(self):
        profile = _hot_profile()
        cost = _total_monthly_cost(profile)
        storage = _monthly_storage_cost(StorageTier.HOT, profile.data_size_gb)
        iops = _monthly_iops_cost(StorageTier.HOT, profile.read_iops, profile.write_iops)
        assert abs(cost - (storage + iops)) < 0.01

    def test_total_monthly_cost_on_tier(self):
        profile = _hot_profile()
        cost_warm = _total_monthly_cost_on_tier(profile, StorageTier.WARM)
        storage = _monthly_storage_cost(StorageTier.WARM, profile.data_size_gb)
        iops = _monthly_iops_cost(StorageTier.WARM, profile.read_iops, profile.write_iops)
        assert abs(cost_warm - (storage + iops)) < 0.01

    def test_transition_cost_known_pair(self):
        cost = _transition_cost(StorageTier.HOT, StorageTier.WARM, 100.0)
        expected = TRANSITION_COST_PER_GB[(StorageTier.HOT, StorageTier.WARM)] * 100.0
        assert abs(cost - expected) < 0.001

    def test_transition_cost_same_tier(self):
        cost = _transition_cost(StorageTier.HOT, StorageTier.HOT, 100.0)
        assert cost == 0.0

    def test_transition_cost_promotion_is_higher(self):
        demote = _transition_cost(StorageTier.HOT, StorageTier.ARCHIVE, 100.0)
        promote = _transition_cost(StorageTier.ARCHIVE, StorageTier.HOT, 100.0)
        assert promote > demote


class TestDataClassification:
    """Test temperature-based data classification."""

    def test_hot_data_classification(self):
        profile = _hot_profile(read_frequency_per_day=50000.0, write_frequency_per_day=10000.0)
        cls = _classify_temperature(profile)
        assert cls.component_id == profile.component_id
        assert cls.hot_ratio > 0.5
        # Ratios sum to 1.0
        total = cls.hot_ratio + cls.warm_ratio + cls.cold_ratio + cls.archive_ratio
        assert abs(total - 1.0) < 0.01

    def test_cold_data_classification(self):
        profile = _cold_profile(
            read_frequency_per_day=0.0,
            write_frequency_per_day=0.0,
            last_access_days_ago=200,
        )
        cls = _classify_temperature(profile)
        assert cls.archive_ratio > 0.5

    def test_warm_data_classification(self):
        profile = DataAccessProfile(
            component_id="w1",
            data_size_gb=100.0,
            current_tier=StorageTier.WARM,
            read_frequency_per_day=500.0,
            write_frequency_per_day=100.0,
            last_access_days_ago=5,
            data_age_days=60,
        )
        cls = _classify_temperature(profile)
        # Warm data should have meaningful warm+hot ratios
        assert cls.warm_ratio + cls.hot_ratio > 0.3

    def test_zero_frequency_recent_access(self):
        profile = DataAccessProfile(
            component_id="z1",
            read_frequency_per_day=0.0,
            write_frequency_per_day=0.0,
            last_access_days_ago=10,
        )
        cls = _classify_temperature(profile)
        # Low frequency but recent => warm/cold, not archive
        assert cls.cold_ratio > cls.archive_ratio

    def test_medium_frequency_classification(self):
        """Test classification with moderate frequency (100-1000 range)."""
        profile = DataAccessProfile(
            component_id="m1",
            read_frequency_per_day=800.0,
            write_frequency_per_day=100.0,
            last_access_days_ago=0,
        )
        cls = _classify_temperature(profile)
        assert cls.hot_ratio + cls.warm_ratio > 0.5

    def test_low_frequency_classification(self):
        """Test classification with very low frequency (< 10)."""
        profile = DataAccessProfile(
            component_id="l1",
            read_frequency_per_day=5.0,
            write_frequency_per_day=1.0,
            last_access_days_ago=0,
        )
        cls = _classify_temperature(profile)
        assert cls.cold_ratio + cls.warm_ratio > 0.5

    def test_moderate_last_access_shifts_cold(self):
        """Test that last_access > 30 shifts hot ratio down."""
        profile = DataAccessProfile(
            component_id="ma1",
            read_frequency_per_day=5000.0,
            write_frequency_per_day=1000.0,
            last_access_days_ago=50,
        )
        fresh = DataAccessProfile(
            component_id="ma2",
            read_frequency_per_day=5000.0,
            write_frequency_per_day=1000.0,
            last_access_days_ago=0,
        )
        cls_old = _classify_temperature(profile)
        cls_fresh = _classify_temperature(fresh)
        assert cls_old.hot_ratio <= cls_fresh.hot_ratio

    def test_zero_freq_moderate_last_access(self):
        """Zero frequency + last_access between 31-180 hits the elif branch."""
        profile = DataAccessProfile(
            component_id="zm1",
            read_frequency_per_day=0.0,
            write_frequency_per_day=0.0,
            last_access_days_ago=60,
        )
        cls = _classify_temperature(profile)
        # Should hit: total_freq <= 0 and last_access > 30 (but <= 180)
        assert cls.cold_ratio > cls.archive_ratio
        assert cls.hot_ratio == 0.0

    def test_freq_11_to_100_classification(self):
        """Total frequency 11-100 hits the elif total_freq <= 100 branch."""
        profile = DataAccessProfile(
            component_id="f100",
            read_frequency_per_day=40.0,
            write_frequency_per_day=10.0,
            last_access_days_ago=0,
        )
        cls = _classify_temperature(profile)
        # Should hit: total_freq <= 100 branch
        assert cls.warm_ratio > cls.hot_ratio


class TestRecommendTier:
    """Test the _recommend_tier heuristic."""

    def test_hot_data_stays_hot(self):
        profile = _hot_profile()
        tier = _recommend_tier(profile)
        assert tier == StorageTier.HOT

    def test_cold_data_recommended_archive(self):
        profile = _cold_profile(
            read_frequency_per_day=0.0,
            write_frequency_per_day=0.0,
            last_access_days_ago=200,
        )
        tier = _recommend_tier(profile)
        assert tier in (StorageTier.COLD, StorageTier.ARCHIVE)

    def test_sla_constrains_tier(self):
        """If SLA requires low latency, tier cannot go to archive."""
        profile = _cold_profile(sla_max_retrieval_ms=100.0)
        tier = _recommend_tier(profile)
        # Archive has 3_600_000 ms latency, cold has 50 ms
        assert RETRIEVAL_LATENCY_MS[tier] <= 100.0

    def test_sla_constrains_to_hot(self):
        """Very tight SLA forces hot tier."""
        profile = _cold_profile(sla_max_retrieval_ms=1.0)
        tier = _recommend_tier(profile)
        assert tier == StorageTier.HOT

    def test_sla_impossible_still_returns_hot(self):
        """SLA tighter than any tier's latency still returns hot (break at order==0)."""
        profile = _cold_profile(sla_max_retrieval_ms=0.01)
        tier = _recommend_tier(profile)
        # HOT latency is 0.5ms which exceeds 0.01ms, but we break at order==0
        assert tier == StorageTier.HOT


class TestDetermineRisk:
    """Test risk assessment for tier transitions."""

    def test_same_tier_is_low(self):
        assert _determine_risk(StorageTier.HOT, StorageTier.HOT, _hot_profile()) == RiskLevel.LOW

    def test_one_step_colder_is_low(self):
        p = _hot_profile()
        assert _determine_risk(StorageTier.HOT, StorageTier.WARM, p) == RiskLevel.LOW

    def test_two_steps_colder_is_medium(self):
        p = _hot_profile()
        assert _determine_risk(StorageTier.HOT, StorageTier.COLD, p) == RiskLevel.MEDIUM

    def test_three_steps_colder_is_high(self):
        p = _hot_profile()
        assert _determine_risk(StorageTier.HOT, StorageTier.ARCHIVE, p) == RiskLevel.HIGH

    def test_one_step_promotion_is_low(self):
        p = _cold_profile(current_tier=StorageTier.WARM)
        assert _determine_risk(StorageTier.WARM, StorageTier.HOT, p) == RiskLevel.LOW

    def test_multi_step_promotion_is_medium(self):
        p = _cold_profile(current_tier=StorageTier.ARCHIVE)
        assert _determine_risk(StorageTier.ARCHIVE, StorageTier.HOT, p) == RiskLevel.MEDIUM


class TestLifecycleRules:
    """Test lifecycle rule generation."""

    def test_hot_tier_generates_age_rules(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile()
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        rules = optimizer._generate_lifecycle_rules(profile)
        # Should produce hot->warm, warm->cold, cold->archive age rules
        age_rules = [r for r in rules if r.condition_type == "age"]
        assert len(age_rules) == 3
        assert age_rules[0].target_tier == StorageTier.WARM
        assert age_rules[1].target_tier == StorageTier.COLD
        assert age_rules[2].target_tier == StorageTier.ARCHIVE

    def test_low_frequency_generates_freq_rule(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _cold_profile(read_frequency_per_day=2.0, write_frequency_per_day=0.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        rules = optimizer._generate_lifecycle_rules(profile)
        freq_rules = [r for r in rules if r.condition_type == "access_frequency"]
        assert len(freq_rules) >= 1

    def test_old_data_generates_last_access_rule(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _cold_profile(last_access_days_ago=120)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        rules = optimizer._generate_lifecycle_rules(profile)
        la_rules = [r for r in rules if r.condition_type == "last_access"]
        assert len(la_rules) >= 1
        assert la_rules[0].target_tier == StorageTier.ARCHIVE


class TestDeduplicationAnalysis:
    """Test deduplication and compression opportunity analysis."""

    def test_no_dedup_no_compression(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(dedup_eligible_ratio=0.0, compression_ratio=1.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        opp = optimizer._analyze_dedup(profile)
        assert opp.dedup_savings_gb == 0.0
        assert opp.compression_savings_gb == 0.0
        assert opp.total_savings_gb == 0.0
        assert opp.effective_size_gb == profile.data_size_gb

    def test_dedup_only(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(
            size_gb=200.0,
            dedup_eligible_ratio=0.3,
            compression_ratio=1.0,
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        opp = optimizer._analyze_dedup(profile)
        assert opp.dedup_savings_gb == 60.0
        assert opp.compression_savings_gb == 0.0
        assert abs(opp.effective_size_gb - 140.0) < 0.01

    def test_compression_only(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(
            size_gb=200.0,
            dedup_eligible_ratio=0.0,
            compression_ratio=0.5,
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        opp = optimizer._analyze_dedup(profile)
        assert opp.dedup_savings_gb == 0.0
        assert abs(opp.compression_savings_gb - 100.0) < 0.01
        assert abs(opp.effective_size_gb - 100.0) < 0.01

    def test_dedup_and_compression(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(
            size_gb=400.0,
            dedup_eligible_ratio=0.25,
            compression_ratio=0.5,
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        opp = optimizer._analyze_dedup(profile)
        # 400 * 0.25 = 100 GB dedup -> 300 GB after dedup
        # 300 * 0.5 = 150 GB after compression
        assert abs(opp.dedup_savings_gb - 100.0) < 0.01
        assert abs(opp.compression_savings_gb - 150.0) < 0.01
        assert abs(opp.effective_size_gb - 150.0) < 0.01
        assert opp.monthly_cost_savings > 0

    def test_dedup_cost_savings_reflect_tier(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(
            size_gb=1000.0,
            dedup_eligible_ratio=0.5,
            compression_ratio=1.0,
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        opp = optimizer._analyze_dedup(profile)
        expected_saving = _monthly_storage_cost(StorageTier.HOT, 500.0)
        assert abs(opp.monthly_cost_savings - expected_saving) < 0.01


class TestCrossRegionCost:
    """Test cross-region replication cost estimation."""

    def test_no_replicas(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(cross_region_replicas=0)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        # No cross-region entry produced in report
        report = optimizer.analyze()
        assert len(report.cross_region_costs) == 0

    def test_with_replicas(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(size_gb=200.0, cross_region_replicas=2)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        cr = optimizer._calculate_cross_region_cost(profile)
        assert cr.replica_count == 2
        assert cr.monthly_transfer_cost == round(
            200.0 * 2 * CROSS_REGION_REPLICATION_COST_PER_GB, 2,
        )
        assert cr.total_monthly_cost > cr.monthly_transfer_cost


class TestCapacityProjection:
    """Test storage capacity forecasting."""

    def test_basic_projection(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(size_gb=100.0, growth_rate_gb_per_month=10.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        proj = optimizer._project_capacity(profile)
        assert proj.current_size_gb == 100.0
        assert proj.projected_size_30d_gb == 110.0
        assert proj.projected_size_90d_gb == 130.0
        assert proj.projected_size_365d_gb == 220.0

    def test_threshold_reached(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(
            size_gb=900.0,
            growth_rate_gb_per_month=50.0,
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile], capacity_threshold_gb=1000.0)
        proj = optimizer._project_capacity(profile)
        assert proj.months_until_threshold_gb == 2.0  # (1000-900)/50

    def test_no_growth(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(size_gb=100.0, growth_rate_gb_per_month=0.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile], capacity_threshold_gb=1000.0)
        proj = optimizer._project_capacity(profile)
        assert proj.months_until_threshold_gb == float("inf")

    def test_already_exceeded(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(size_gb=1500.0, growth_rate_gb_per_month=0.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile], capacity_threshold_gb=1000.0)
        proj = optimizer._project_capacity(profile)
        assert proj.months_until_threshold_gb == 0.0


class TestComplianceCheck:
    """Test compliance retention validation."""

    def test_gdpr_meets_requirement(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = DataAccessProfile(
            component_id="s1",
            data_age_days=400,
            compliance_frameworks=[ComplianceFramework.GDPR],
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        check = optimizer._check_compliance(profile, ComplianceFramework.GDPR)
        assert check.meets_requirement is True

    def test_hipaa_long_retention_suggests_cold(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = DataAccessProfile(
            component_id="s1",
            data_age_days=10,
            current_tier=StorageTier.HOT,
            compliance_frameworks=[ComplianceFramework.HIPAA],
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        check = optimizer._check_compliance(profile, ComplianceFramework.HIPAA)
        assert check.meets_requirement is True
        assert "cold/archive" in check.recommendation

    def test_archive_violates_sla(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = DataAccessProfile(
            component_id="s1",
            data_age_days=100,
            current_tier=StorageTier.ARCHIVE,
            sla_max_retrieval_ms=100.0,
            compliance_frameworks=[ComplianceFramework.PCI_DSS],
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        check = optimizer._check_compliance(profile, ComplianceFramework.PCI_DSS)
        assert check.meets_requirement is False
        assert "violates SLA" in check.recommendation

    def test_custom_retention(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = DataAccessProfile(
            component_id="s1",
            data_age_days=50,
            custom_retention_days=90,
            compliance_frameworks=[ComplianceFramework.CUSTOM],
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        check = optimizer._check_compliance(profile, ComplianceFramework.CUSTOM)
        assert check.required_retention_days == 90
        assert check.meets_requirement is True

    def test_sox_retention_value(self):
        assert COMPLIANCE_RETENTION_DAYS[ComplianceFramework.SOX] == 2555


class TestStorageTierOptimizer:
    """Integration-level tests on the optimizer."""

    def test_default_profile_generation(self):
        """Graph with storage/db components auto-generates profiles."""
        s1 = _storage_comp("s1")
        db1 = _db_comp("db1")
        app = _comp("a1", ComponentType.APP_SERVER)
        g = _graph(s1, db1, app)
        optimizer = StorageTierOptimizer(g)
        # Should only create profiles for storage + database types
        assert len(optimizer.profiles) == 2
        ids = {p.component_id for p in optimizer.profiles}
        assert ids == {"s1", "db1"}

    def test_analyze_returns_report(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile()
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert isinstance(report, StorageTierReport)
        assert report.total_profiles_analyzed == 1
        assert report.generated_at is not None

    def test_analyze_with_multiple_profiles(self):
        g = _graph(
            _comp("s1", ComponentType.STORAGE),
            _comp("s2", ComponentType.STORAGE),
        )
        profiles = [
            _hot_profile("s1"),
            _cold_profile("s2"),
        ]
        optimizer = StorageTierOptimizer(g, profiles=profiles)
        report = optimizer.analyze()
        assert report.total_profiles_analyzed == 2
        assert len(report.recommendations) == 2
        assert len(report.data_classifications) == 2

    def test_savings_are_nonnegative(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _cold_profile()
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert report.total_savings_monthly >= 0

    def test_optimized_cost_leq_current(self):
        """Optimized cost should be less than or equal to current cost."""
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _cold_profile(size_gb=1000.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert report.optimized_monthly_cost <= report.current_monthly_cost

    def test_capacity_warning_emitted(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(size_gb=2000.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile], capacity_threshold_gb=1000.0)
        report = optimizer.analyze()
        assert any("exceeds threshold" in w for w in report.warnings)

    def test_sla_violation_warning(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = DataAccessProfile(
            component_id="s1",
            current_tier=StorageTier.ARCHIVE,
            sla_max_retrieval_ms=100.0,
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert any("exceeds SLA" in w for w in report.warnings)

    def test_cross_region_costs_in_report(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(size_gb=100.0, cross_region_replicas=3)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert len(report.cross_region_costs) == 1
        assert report.cross_region_costs[0].replica_count == 3

    def test_compliance_checks_in_report(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = DataAccessProfile(
            component_id="s1",
            compliance_frameworks=[
                ComplianceFramework.GDPR,
                ComplianceFramework.HIPAA,
            ],
            data_age_days=100,
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert len(report.compliance_checks) == 2

    def test_recommend_tier_for_profile_method(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile()
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        rec = optimizer.recommend_tier_for_profile(profile)
        assert isinstance(rec, TierRecommendation)
        assert rec.component_id == "s1"

    def test_compare_all_tiers(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile()
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        comparison = optimizer.compare_all_tiers(profile)
        assert set(comparison.keys()) == set(StorageTier)
        # Hot tier should be most expensive for storage, but archive IOPS
        # are expensive, so just check all values are non-negative
        for cost in comparison.values():
            assert cost >= 0.0

    def test_estimate_transition_costs(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(size_gb=100.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        costs = optimizer.estimate_transition_costs(profile)
        assert costs[StorageTier.HOT] == 0.0  # same tier
        assert costs[StorageTier.WARM] > 0.0
        assert costs[StorageTier.ARCHIVE] > 0.0

    def test_break_even_days_positive(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _cold_profile(size_gb=500.0, current_tier=StorageTier.HOT)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        for rec in report.recommendations:
            if rec.savings_monthly > 0:
                assert rec.break_even_days > 0

    def test_empty_graph_no_profiles(self):
        g = _graph(_comp("a1", ComponentType.APP_SERVER))
        optimizer = StorageTierOptimizer(g)
        assert len(optimizer.profiles) == 0
        report = optimizer.analyze()
        assert report.total_profiles_analyzed == 0
        assert report.current_monthly_cost == 0.0

    def test_savings_percent_correct(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _cold_profile(size_gb=1000.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        if report.current_monthly_cost > 0:
            expected_pct = (
                report.total_savings_monthly / report.current_monthly_cost * 100.0
            )
            assert abs(report.savings_percent - round(expected_pct, 1)) < 0.2

    def test_lifecycle_rules_populated(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile()
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert len(report.lifecycle_rules) >= 3  # age rules for hot tier

    def test_graph_with_dependency(self):
        """Ensure optimizer works with graphs that have dependencies."""
        s1 = _comp("s1", ComponentType.STORAGE)
        a1 = _comp("a1", ComponentType.APP_SERVER)
        g = _graph(s1, a1)
        g.add_dependency(Dependency(source_id="a1", target_id="s1"))
        profile = _hot_profile("s1")
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert report.total_profiles_analyzed == 1

    def test_recommendation_for_already_optimal(self):
        """When current tier is already optimal, savings should be 0."""
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile()
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        rec = optimizer.recommend_tier_for_profile(profile)
        if rec.recommended_tier == rec.current_tier:
            assert rec.savings_monthly == 0.0
            assert "optimal" in rec.reason.lower()

    def test_dedup_opportunities_in_report(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(dedup_eligible_ratio=0.2, compression_ratio=0.7)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert len(report.dedup_opportunities) == 1
        assert report.dedup_opportunities[0].total_savings_gb > 0

    def test_capacity_projections_in_report(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = _hot_profile(size_gb=100.0, growth_rate_gb_per_month=20.0)
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        report = optimizer.analyze()
        assert len(report.capacity_projections) == 1
        proj = report.capacity_projections[0]
        assert proj.projected_size_365d_gb > proj.current_size_gb

    def test_warm_tier_no_age_lifecycle_rules(self):
        """Warm tier should not generate the hot->warm age rule."""
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = DataAccessProfile(
            component_id="s1",
            current_tier=StorageTier.WARM,
            read_frequency_per_day=50.0,
            write_frequency_per_day=10.0,
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        rules = optimizer._generate_lifecycle_rules(profile)
        age_rules = [r for r in rules if r.condition_type == "age"]
        assert len(age_rules) == 0

    def test_retrieval_latency_ordering(self):
        """Verify latency constants are ordered hot < warm < cold < archive."""
        assert RETRIEVAL_LATENCY_MS[StorageTier.HOT] < RETRIEVAL_LATENCY_MS[StorageTier.WARM]
        assert RETRIEVAL_LATENCY_MS[StorageTier.WARM] < RETRIEVAL_LATENCY_MS[StorageTier.COLD]
        assert RETRIEVAL_LATENCY_MS[StorageTier.COLD] < RETRIEVAL_LATENCY_MS[StorageTier.ARCHIVE]

    def test_storage_cost_ordering(self):
        """Hot storage costs more per GB than colder tiers."""
        assert STORAGE_COST_PER_GB[StorageTier.HOT] > STORAGE_COST_PER_GB[StorageTier.WARM]
        assert STORAGE_COST_PER_GB[StorageTier.WARM] > STORAGE_COST_PER_GB[StorageTier.COLD]
        assert STORAGE_COST_PER_GB[StorageTier.COLD] > STORAGE_COST_PER_GB[StorageTier.ARCHIVE]

    def test_compliance_short_remaining_retention(self):
        """Short remaining retention with hot tier passes without cold suggestion."""
        g = _graph(_comp("s1", ComponentType.STORAGE))
        profile = DataAccessProfile(
            component_id="s1",
            data_age_days=360,
            current_tier=StorageTier.HOT,
            compliance_frameworks=[ComplianceFramework.GDPR],
        )
        optimizer = StorageTierOptimizer(g, profiles=[profile])
        check = optimizer._check_compliance(profile, ComplianceFramework.GDPR)
        assert check.meets_requirement is True
        # Remaining is only 5 days, no cold suggestion
        assert "cold/archive" not in check.recommendation
