"""Tests for Multi-Region Disaster Recovery Engine.

60+ test cases covering:
- DRConfig defaults and Region dataclass
- assess: all 4 strategies
- assess: RTO/RPO met/not met
- assess: replication modes (sync, async, semi-sync)
- assess: manual vs automated failover
- assess: DNS TTL impact
- assess: single region (no DR)
- assess: data loss risk levels
- assess: cost multipliers
- assess: availability nines
- simulate_failover: all triggers
- simulate_failover: timeline steps
- simulate_failover: data loss calculation
- simulate_failover: degraded period for reduced capacity
- compare_strategies: returns 4 results
- Edge cases
"""
from __future__ import annotations

import math

import pytest

from faultray.simulator.multi_region_dr import (
    DRAssessment,
    DRConfig,
    DRStrategy,
    FailoverSimulation,
    FailoverTrigger,
    MultiRegionDREngine,
    Region,
    ReplicationMode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _two_region_config(**overrides) -> DRConfig:
    """Create a standard two-region DRConfig with optional overrides."""
    defaults = dict(
        strategy=DRStrategy.ACTIVE_PASSIVE,
        regions=[
            Region(name="us-east-1", is_primary=True),
            Region(name="us-west-2", is_primary=False),
        ],
        replication_mode=ReplicationMode.ASYNCHRONOUS,
        replication_lag_seconds=1.0,
        failover_automation=True,
        dns_ttl_seconds=60.0,
        health_check_interval_seconds=30.0,
    )
    defaults.update(overrides)
    return DRConfig(**defaults)


# ===================================================================
# DRConfig defaults
# ===================================================================

class TestDRConfigDefaults:
    """Test that DRConfig has correct default values."""

    def test_default_strategy(self):
        cfg = DRConfig()
        assert cfg.strategy == DRStrategy.ACTIVE_PASSIVE

    def test_default_regions_empty(self):
        cfg = DRConfig()
        assert cfg.regions == []

    def test_default_replication_mode(self):
        cfg = DRConfig()
        assert cfg.replication_mode == ReplicationMode.ASYNCHRONOUS

    def test_default_replication_lag(self):
        cfg = DRConfig()
        assert cfg.replication_lag_seconds == 1.0

    def test_default_failover_automation(self):
        cfg = DRConfig()
        assert cfg.failover_automation is True

    def test_default_dns_ttl(self):
        cfg = DRConfig()
        assert cfg.dns_ttl_seconds == 60.0

    def test_default_health_check_interval(self):
        cfg = DRConfig()
        assert cfg.health_check_interval_seconds == 30.0


# ===================================================================
# Region dataclass
# ===================================================================

class TestRegion:
    """Test Region dataclass creation and defaults."""

    def test_region_name(self):
        r = Region(name="us-east-1")
        assert r.name == "us-east-1"

    def test_region_default_primary(self):
        r = Region(name="us-east-1")
        assert r.is_primary is True

    def test_region_default_latency(self):
        r = Region(name="us-east-1")
        assert r.latency_ms == 0.0

    def test_region_default_services(self):
        r = Region(name="us-east-1")
        assert r.services == []

    def test_region_default_capacity(self):
        r = Region(name="us-east-1")
        assert r.capacity_percent == 100.0

    def test_region_custom_values(self):
        r = Region(
            name="eu-west-1",
            is_primary=False,
            latency_ms=75.0,
            services=["api", "db"],
            capacity_percent=50.0,
        )
        assert r.name == "eu-west-1"
        assert r.is_primary is False
        assert r.latency_ms == 75.0
        assert r.services == ["api", "db"]
        assert r.capacity_percent == 50.0


# ===================================================================
# Enums
# ===================================================================

class TestEnums:
    """Test enum values."""

    def test_dr_strategy_values(self):
        assert DRStrategy.ACTIVE_ACTIVE.value == "active_active"
        assert DRStrategy.ACTIVE_PASSIVE.value == "active_passive"
        assert DRStrategy.PILOT_LIGHT.value == "pilot_light"
        assert DRStrategy.BACKUP_RESTORE.value == "backup_restore"

    def test_failover_trigger_values(self):
        assert FailoverTrigger.REGION_OUTAGE.value == "region_outage"
        assert FailoverTrigger.AZ_OUTAGE.value == "az_outage"
        assert FailoverTrigger.SERVICE_DEGRADATION.value == "service_degradation"
        assert FailoverTrigger.MANUAL.value == "manual"
        assert FailoverTrigger.DNS_HEALTH_CHECK.value == "dns_health_check"

    def test_replication_mode_values(self):
        assert ReplicationMode.SYNCHRONOUS.value == "synchronous"
        assert ReplicationMode.ASYNCHRONOUS.value == "asynchronous"
        assert ReplicationMode.SEMI_SYNCHRONOUS.value == "semi_synchronous"

    def test_dr_strategy_is_str_enum(self):
        assert isinstance(DRStrategy.ACTIVE_ACTIVE, str)

    def test_failover_trigger_is_str_enum(self):
        assert isinstance(FailoverTrigger.REGION_OUTAGE, str)

    def test_replication_mode_is_str_enum(self):
        assert isinstance(ReplicationMode.SYNCHRONOUS, str)


# ===================================================================
# Assess: strategy-specific tests
# ===================================================================

class TestAssessActiveActive:
    """Test assess() for active-active strategy."""

    def test_rto_active_active_is_lowest(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # active_active base=0, dns=0, detection=60
        assert result.rto_seconds == 60.0

    def test_dns_not_added_for_active_active(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE, dns_ttl_seconds=120)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # dns_time should be 0 for active_active
        assert result.rto_seconds == 60.0

    def test_cost_multiplier_active_active(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.cost_multiplier == 2.0

    def test_failover_steps_active_active(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert "Traffic already distributed - remove unhealthy region from pool" in result.failover_steps


class TestAssessActivePassive:
    """Test assess() for active-passive strategy."""

    def test_rto_active_passive(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_PASSIVE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # base=60, dns=60, detection=60
        assert result.rto_seconds == 180.0

    def test_cost_multiplier_active_passive(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_PASSIVE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.cost_multiplier == 1.6

    def test_failover_steps_active_passive(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_PASSIVE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert "Promote standby region to active" in result.failover_steps
        assert "Update DNS to point to secondary" in result.failover_steps


class TestAssessPilotLight:
    """Test assess() for pilot-light strategy."""

    def test_rto_pilot_light(self):
        cfg = _two_region_config(strategy=DRStrategy.PILOT_LIGHT)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # base=600, dns=60, detection=60
        assert result.rto_seconds == 720.0

    def test_cost_multiplier_pilot_light(self):
        cfg = _two_region_config(strategy=DRStrategy.PILOT_LIGHT)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.cost_multiplier == 1.2

    def test_failover_steps_pilot_light(self):
        cfg = _two_region_config(strategy=DRStrategy.PILOT_LIGHT)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert "Scale up pilot light infrastructure" in result.failover_steps
        assert "Restore recent data from replication" in result.failover_steps


class TestAssessBackupRestore:
    """Test assess() for backup-restore strategy."""

    def test_rto_backup_restore(self):
        cfg = _two_region_config(strategy=DRStrategy.BACKUP_RESTORE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # base=3600, dns=60, detection=60
        assert result.rto_seconds == 3720.0

    def test_cost_multiplier_backup_restore(self):
        cfg = _two_region_config(strategy=DRStrategy.BACKUP_RESTORE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.cost_multiplier == 1.05

    def test_failover_steps_backup_restore(self):
        cfg = _two_region_config(strategy=DRStrategy.BACKUP_RESTORE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert "Restore from latest backup" in result.failover_steps
        assert "Provision full infrastructure" in result.failover_steps
        assert "Validate data integrity" in result.failover_steps


# ===================================================================
# Assess: RTO/RPO met/not met
# ===================================================================

class TestAssessRTORPOMet:
    """Test RTO and RPO met/not-met conditions."""

    def test_rto_met_when_target_is_generous(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE)
        engine = MultiRegionDREngine(cfg, target_rto=600)
        result = engine.assess()
        assert result.rto_met is True

    def test_rto_not_met_when_target_is_tight(self):
        cfg = _two_region_config(strategy=DRStrategy.BACKUP_RESTORE)
        engine = MultiRegionDREngine(cfg, target_rto=300)
        result = engine.assess()
        assert result.rto_met is False

    def test_rpo_met_with_sync_replication(self):
        cfg = _two_region_config(replication_mode=ReplicationMode.SYNCHRONOUS)
        engine = MultiRegionDREngine(cfg, target_rpo=0)
        result = engine.assess()
        assert result.rpo_met is True

    def test_rpo_not_met_with_high_lag(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            replication_lag_seconds=60.0,
        )
        engine = MultiRegionDREngine(cfg, target_rpo=10)
        result = engine.assess()
        assert result.rpo_met is False

    def test_rto_exactly_equal_to_target_is_met(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_PASSIVE)
        engine = MultiRegionDREngine(cfg)
        rto = engine.assess().rto_seconds
        engine2 = MultiRegionDREngine(cfg, target_rto=rto)
        result = engine2.assess()
        assert result.rto_met is True

    def test_rpo_exactly_equal_to_target_is_met(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.SEMI_SYNCHRONOUS,
            replication_lag_seconds=5.0,
        )
        engine = MultiRegionDREngine(cfg, target_rpo=5.0)
        result = engine.assess()
        assert result.rpo_met is True


# ===================================================================
# Assess: Replication modes
# ===================================================================

class TestAssessReplicationModes:
    """Test RPO behavior for each replication mode."""

    def test_synchronous_rpo_is_zero(self):
        cfg = _two_region_config(replication_mode=ReplicationMode.SYNCHRONOUS)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.rpo_seconds == 0

    def test_asynchronous_rpo_is_double_lag(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            replication_lag_seconds=5.0,
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.rpo_seconds == 10.0

    def test_semi_synchronous_rpo_equals_lag(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.SEMI_SYNCHRONOUS,
            replication_lag_seconds=3.0,
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.rpo_seconds == 3.0


# ===================================================================
# Assess: Manual vs automated failover
# ===================================================================

class TestAssessFailoverAutomation:
    """Test impact of manual vs automated failover."""

    def test_automated_failover_lower_rto(self):
        auto_cfg = _two_region_config(failover_automation=True)
        manual_cfg = _two_region_config(failover_automation=False)
        auto_rto = MultiRegionDREngine(auto_cfg).assess().rto_seconds
        manual_rto = MultiRegionDREngine(manual_cfg).assess().rto_seconds
        assert auto_rto < manual_rto

    def test_manual_failover_detection_time(self):
        cfg = _two_region_config(failover_automation=False)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # Manual detection: 300s instead of health_check * 2
        # base=60, dns=60, detection=300
        assert result.rto_seconds == 420.0

    def test_manual_failover_risk_reported(self):
        cfg = _two_region_config(failover_automation=False)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert any("Manual failover" in r for r in result.risks)

    def test_manual_failover_recommendation(self):
        cfg = _two_region_config(failover_automation=False)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert any("automated failover" in r.lower() for r in result.recommendations)

    def test_automated_failover_no_manual_risk(self):
        cfg = _two_region_config(failover_automation=True)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert not any("Manual failover" in r for r in result.risks)


# ===================================================================
# Assess: DNS TTL impact
# ===================================================================

class TestAssessDNSTTL:
    """Test DNS TTL impact on assessment."""

    def test_high_dns_ttl_risk_reported(self):
        cfg = _two_region_config(dns_ttl_seconds=600.0)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert any("DNS TTL" in r for r in result.risks)

    def test_high_dns_ttl_recommendation(self):
        cfg = _two_region_config(dns_ttl_seconds=600.0)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert any("DNS TTL" in r.upper() or "dns ttl" in r.lower() for r in result.recommendations)

    def test_low_dns_ttl_no_risk(self):
        cfg = _two_region_config(dns_ttl_seconds=30.0)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert not any("DNS TTL" in r for r in result.risks)

    def test_dns_ttl_affects_rto(self):
        low_cfg = _two_region_config(dns_ttl_seconds=30.0)
        high_cfg = _two_region_config(dns_ttl_seconds=300.0)
        low_rto = MultiRegionDREngine(low_cfg).assess().rto_seconds
        high_rto = MultiRegionDREngine(high_cfg).assess().rto_seconds
        assert high_rto > low_rto


# ===================================================================
# Assess: Single region (no DR)
# ===================================================================

class TestAssessSingleRegion:
    """Test assessment with a single region."""

    def test_single_region_risk(self):
        cfg = DRConfig(regions=[Region(name="us-east-1")])
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert any("Single region" in r for r in result.risks)

    def test_single_region_recommendation(self):
        cfg = DRConfig(regions=[Region(name="us-east-1")])
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert any("secondary region" in r.lower() for r in result.recommendations)

    def test_no_regions_risk(self):
        cfg = DRConfig(regions=[])
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert any("Single region" in r for r in result.risks)


# ===================================================================
# Assess: Data loss risk levels
# ===================================================================

class TestAssessDataLossRisk:
    """Test data loss risk classification."""

    def test_data_loss_none_with_sync(self):
        cfg = _two_region_config(replication_mode=ReplicationMode.SYNCHRONOUS)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.data_loss_risk == "none"

    def test_data_loss_minimal_with_low_lag(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.SEMI_SYNCHRONOUS,
            replication_lag_seconds=2.0,
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.data_loss_risk == "minimal"

    def test_data_loss_moderate(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            replication_lag_seconds=10.0,
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # rpo = 10 * 2 = 20, 5 <= 20 < 60 => moderate
        assert result.data_loss_risk == "moderate"

    def test_data_loss_significant(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            replication_lag_seconds=60.0,
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # rpo = 60 * 2 = 120, >= 60 => significant
        assert result.data_loss_risk == "significant"


# ===================================================================
# Assess: Cost multipliers
# ===================================================================

class TestAssessCostMultipliers:
    """Test cost multiplier for each strategy."""

    @pytest.mark.parametrize("strategy,expected_cost", [
        (DRStrategy.ACTIVE_ACTIVE, 2.0),
        (DRStrategy.ACTIVE_PASSIVE, 1.6),
        (DRStrategy.PILOT_LIGHT, 1.2),
        (DRStrategy.BACKUP_RESTORE, 1.05),
    ])
    def test_cost_multiplier_per_strategy(self, strategy, expected_cost):
        cfg = _two_region_config(strategy=strategy)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.cost_multiplier == expected_cost


# ===================================================================
# Assess: Availability nines
# ===================================================================

class TestAssessAvailabilityNines:
    """Test availability nines calculation."""

    def test_active_active_high_nines(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.availability_nines > 3.0

    def test_backup_restore_lower_nines(self):
        cfg = _two_region_config(strategy=DRStrategy.BACKUP_RESTORE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.availability_nines > 0

    def test_active_active_higher_than_backup_restore(self):
        aa_cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE)
        br_cfg = _two_region_config(strategy=DRStrategy.BACKUP_RESTORE)
        aa_nines = MultiRegionDREngine(aa_cfg).assess().availability_nines
        br_nines = MultiRegionDREngine(br_cfg).assess().availability_nines
        assert aa_nines > br_nines

    def test_nines_capped_at_six(self):
        # Even with zero RTO, nines should not exceed 6
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.availability_nines <= 6.0


# ===================================================================
# Assess: Capacity check
# ===================================================================

class TestAssessCapacityCheck:
    """Test that reduced secondary capacity is flagged."""

    def test_reduced_capacity_risk(self):
        cfg = _two_region_config(
            regions=[
                Region(name="us-east-1", is_primary=True),
                Region(name="us-west-2", is_primary=False, capacity_percent=50.0),
            ]
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert any("reduced capacity" in r for r in result.risks)

    def test_full_capacity_no_risk(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert not any("reduced capacity" in r for r in result.risks)


# ===================================================================
# Assess: High replication lag
# ===================================================================

class TestAssessHighReplicationLag:
    """Test that high async replication lag is flagged."""

    def test_high_lag_risk(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            replication_lag_seconds=60.0,
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert any("replication lag" in r.lower() for r in result.risks)

    def test_low_lag_no_risk(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            replication_lag_seconds=1.0,
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert not any("replication lag" in r.lower() for r in result.risks)

    def test_sync_replication_no_lag_risk(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.SYNCHRONOUS,
            replication_lag_seconds=60.0,  # lag ignored for sync
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert not any("replication lag" in r.lower() for r in result.risks)


# ===================================================================
# Assess: Failover steps generation
# ===================================================================

class TestAssessFailoverSteps:
    """Test that failover steps include verification."""

    def test_all_strategies_end_with_verify(self):
        for strategy in DRStrategy:
            cfg = _two_region_config(strategy=strategy)
            engine = MultiRegionDREngine(cfg)
            result = engine.assess()
            assert result.failover_steps[-1] == "Verify application health in new region"

    def test_all_strategies_start_with_detect(self):
        for strategy in DRStrategy:
            cfg = _two_region_config(strategy=strategy)
            engine = MultiRegionDREngine(cfg)
            result = engine.assess()
            assert result.failover_steps[0] == "Detect failure via health checks"

    def test_automated_failover_step(self):
        cfg = _two_region_config(failover_automation=True)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert "Automated failover triggered" in result.failover_steps

    def test_manual_failover_step(self):
        cfg = _two_region_config(failover_automation=False)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert "Alert on-call engineer for manual failover" in result.failover_steps


# ===================================================================
# Simulate failover: all triggers
# ===================================================================

class TestSimulateFailoverTriggers:
    """Test simulate_failover with all trigger types."""

    @pytest.mark.parametrize("trigger", list(FailoverTrigger))
    def test_trigger_type_in_result(self, trigger):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover(trigger=trigger)
        assert sim.trigger == trigger

    @pytest.mark.parametrize("trigger", list(FailoverTrigger))
    def test_trigger_in_steps_log(self, trigger):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover(trigger=trigger)
        assert any(trigger.value in step for step in sim.steps_log)


# ===================================================================
# Simulate failover: timeline
# ===================================================================

class TestSimulateFailoverTimeline:
    """Test failover simulation timeline calculations."""

    def test_total_time_is_sum_of_parts(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_PASSIVE)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        expected = sim.detection_time_seconds + sim.decision_time_seconds + \
                   sim.execution_time_seconds + sim.dns_propagation_seconds
        assert sim.total_time_seconds == expected

    def test_automated_decision_time(self):
        cfg = _two_region_config(failover_automation=True)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.decision_time_seconds == 5

    def test_manual_decision_time(self):
        cfg = _two_region_config(failover_automation=False)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.decision_time_seconds == 120

    def test_detection_time_automated(self):
        cfg = _two_region_config(failover_automation=True, health_check_interval_seconds=15.0)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.detection_time_seconds == 30.0

    def test_detection_time_manual(self):
        cfg = _two_region_config(failover_automation=False)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.detection_time_seconds == 300

    def test_active_active_no_dns_propagation(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.dns_propagation_seconds == 0

    def test_active_passive_dns_propagation(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_PASSIVE, dns_ttl_seconds=120.0)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.dns_propagation_seconds == 120.0

    def test_execution_time_matches_strategy(self):
        for strategy in DRStrategy:
            cfg = _two_region_config(strategy=strategy)
            engine = MultiRegionDREngine(cfg)
            sim = engine.simulate_failover()
            assert sim.execution_time_seconds == MultiRegionDREngine.STRATEGY_BASE_RTO[strategy]


# ===================================================================
# Simulate failover: data loss
# ===================================================================

class TestSimulateFailoverDataLoss:
    """Test data loss calculation in failover simulation."""

    def test_sync_replication_zero_data_loss(self):
        cfg = _two_region_config(replication_mode=ReplicationMode.SYNCHRONOUS)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.data_loss_seconds == 0.0

    def test_async_replication_data_loss_equals_lag(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            replication_lag_seconds=5.0,
        )
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.data_loss_seconds == 5.0

    def test_semi_sync_data_loss_equals_lag(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.SEMI_SYNCHRONOUS,
            replication_lag_seconds=2.0,
        )
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.data_loss_seconds == 2.0


# ===================================================================
# Simulate failover: degraded period
# ===================================================================

class TestSimulateFailoverDegradedPeriod:
    """Test degraded period for reduced capacity secondary."""

    def test_full_capacity_no_degraded_period(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.degraded_period_seconds == 0.0

    def test_reduced_capacity_has_degraded_period(self):
        cfg = _two_region_config(
            regions=[
                Region(name="us-east-1", is_primary=True),
                Region(name="us-west-2", is_primary=False, capacity_percent=50.0),
            ]
        )
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.degraded_period_seconds == 300.0


# ===================================================================
# Simulate failover: success
# ===================================================================

class TestSimulateFailoverSuccess:
    """Test success condition for failover simulation."""

    def test_two_regions_success(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.success is True

    def test_single_region_failure(self):
        cfg = DRConfig(regions=[Region(name="us-east-1")])
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.success is False

    def test_no_regions_failure(self):
        cfg = DRConfig(regions=[])
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.success is False

    def test_three_regions_success(self):
        cfg = _two_region_config(
            regions=[
                Region(name="us-east-1", is_primary=True),
                Region(name="us-west-2", is_primary=False),
                Region(name="eu-west-1", is_primary=False),
            ]
        )
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.success is True


# ===================================================================
# Simulate failover: steps log
# ===================================================================

class TestSimulateFailoverStepsLog:
    """Test steps log content in failover simulation."""

    def test_steps_log_not_empty(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert len(sim.steps_log) > 0

    def test_steps_log_starts_with_detection(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.steps_log[0].startswith("T+0s:")

    def test_steps_log_ends_with_dns(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert "DNS propagation complete" in sim.steps_log[-1]

    def test_active_active_no_secondary_ready_step(self):
        cfg = _two_region_config(strategy=DRStrategy.ACTIVE_ACTIVE)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        # No "Secondary region ready" step since base_exec=0
        assert not any("Secondary region ready" in s for s in sim.steps_log)

    def test_backup_restore_has_secondary_ready_step(self):
        cfg = _two_region_config(strategy=DRStrategy.BACKUP_RESTORE)
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert any("Secondary region ready" in s for s in sim.steps_log)


# ===================================================================
# Compare strategies
# ===================================================================

class TestCompareStrategies:
    """Test compare_strategies method."""

    def test_returns_four_results(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        results = engine.compare_strategies()
        assert len(results) == 4

    def test_all_results_are_assessments(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        results = engine.compare_strategies()
        for r in results:
            assert isinstance(r, DRAssessment)

    def test_rto_ordering(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        results = engine.compare_strategies()
        rtos = [r.rto_seconds for r in results]
        # active_active < active_passive < pilot_light < backup_restore
        assert rtos[0] < rtos[1] < rtos[2] < rtos[3]

    def test_cost_ordering(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        results = engine.compare_strategies()
        costs = [r.cost_multiplier for r in results]
        # active_active > active_passive > pilot_light > backup_restore
        assert costs[0] > costs[1] > costs[2] > costs[3]

    def test_compare_uses_same_regions(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        results = engine.compare_strategies()
        # All should have same RPO since replication mode doesn't change
        rpos = set(r.rpo_seconds for r in results)
        assert len(rpos) == 1

    def test_compare_respects_target_rto(self):
        cfg = _two_region_config()
        # Very tight RTO target - only active_active might meet it
        engine = MultiRegionDREngine(cfg, target_rto=100)
        results = engine.compare_strategies()
        met_count = sum(1 for r in results if r.rto_met)
        assert met_count >= 1  # At least active_active should meet it


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_replication_lag(self):
        cfg = _two_region_config(replication_lag_seconds=0.0)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.rpo_seconds == 0.0

    def test_zero_dns_ttl(self):
        cfg = _two_region_config(dns_ttl_seconds=0.0)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # RTO = base(60) + dns(0) + detection(60) = 120
        assert result.rto_seconds == 120.0

    def test_zero_health_check_interval(self):
        cfg = _two_region_config(health_check_interval_seconds=0.0)
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        # detection = 0 * 2 = 0
        # RTO = base(60) + dns(60) + detection(0) = 120
        assert result.rto_seconds == 120.0

    def test_very_large_replication_lag(self):
        cfg = _two_region_config(
            replication_mode=ReplicationMode.ASYNCHRONOUS,
            replication_lag_seconds=3600.0,
        )
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert result.rpo_seconds == 7200.0
        assert result.data_loss_risk == "significant"

    def test_assessment_dataclass_fields(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        result = engine.assess()
        assert hasattr(result, "rto_seconds")
        assert hasattr(result, "rpo_seconds")
        assert hasattr(result, "rto_met")
        assert hasattr(result, "rpo_met")
        assert hasattr(result, "failover_steps")
        assert hasattr(result, "data_loss_risk")
        assert hasattr(result, "cost_multiplier")
        assert hasattr(result, "availability_nines")
        assert hasattr(result, "risks")
        assert hasattr(result, "recommendations")

    def test_failover_simulation_dataclass_fields(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert hasattr(sim, "trigger")
        assert hasattr(sim, "detection_time_seconds")
        assert hasattr(sim, "decision_time_seconds")
        assert hasattr(sim, "execution_time_seconds")
        assert hasattr(sim, "total_time_seconds")
        assert hasattr(sim, "dns_propagation_seconds")
        assert hasattr(sim, "data_loss_seconds")
        assert hasattr(sim, "success")
        assert hasattr(sim, "degraded_period_seconds")
        assert hasattr(sim, "steps_log")

    def test_default_trigger_is_region_outage(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        sim = engine.simulate_failover()
        assert sim.trigger == FailoverTrigger.REGION_OUTAGE

    def test_engine_default_targets(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        assert engine.target_rto == 300
        assert engine.target_rpo == 60

    def test_engine_custom_targets(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg, target_rto=600, target_rpo=120)
        assert engine.target_rto == 600
        assert engine.target_rpo == 120


# ===================================================================
# Internal method: _calculate_availability
# ===================================================================

class TestCalculateAvailability:
    """Test the internal _calculate_availability method."""

    def test_zero_rto_returns_six_nines(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        assert engine._calculate_availability(0) == 6.0

    def test_positive_rto_returns_positive_nines(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        nines = engine._calculate_availability(60)
        assert nines > 0

    def test_very_large_rto_returns_low_nines(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        nines = engine._calculate_availability(100000)
        assert nines < 2.0

    def test_nines_never_exceed_six(self):
        cfg = _two_region_config()
        engine = MultiRegionDREngine(cfg)
        for rto in [0, 1, 10, 60, 300]:
            assert engine._calculate_availability(rto) <= 6.0
