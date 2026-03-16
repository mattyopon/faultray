"""Tests for model/components.py — all model classes, defaults, validators, methods."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from faultray.model.components import (
    AutoScalingConfig,
    CacheWarmingConfig,
    Capacity,
    CircuitBreakerConfig,
    ComplianceTags,
    Component,
    ComponentType,
    CostProfile,
    DegradationConfig,
    Dependency,
    ExternalSLAConfig,
    FailoverConfig,
    HealthStatus,
    NetworkProfile,
    OperationalProfile,
    OperationalTeamConfig,
    RegionConfig,
    ResourceMetrics,
    RetryStrategy,
    RuntimeJitter,
    SCHEMA_VERSION,
    SecurityProfile,
    SLOTarget,
    SingleflightConfig,
)


# ===========================================================================
# Schema version
# ===========================================================================


class TestSchemaVersion:
    def test_schema_version_exists(self):
        assert SCHEMA_VERSION == "3.0"


# ===========================================================================
# SecurityProfile
# ===========================================================================


class TestSecurityProfile:
    def test_defaults(self):
        sp = SecurityProfile()
        assert sp.encryption_at_rest is False
        assert sp.encryption_in_transit is False
        assert sp.waf_protected is False
        assert sp.rate_limiting is False
        assert sp.auth_required is False
        assert sp.network_segmented is False
        assert sp.backup_enabled is False
        assert sp.backup_frequency_hours == 24.0
        assert sp.patch_sla_hours == 72.0
        assert sp.log_enabled is False
        assert sp.ids_monitored is False

    def test_custom_values(self):
        sp = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            network_segmented=True,
            backup_enabled=True,
            backup_frequency_hours=6.0,
            patch_sla_hours=24.0,
            log_enabled=True,
            ids_monitored=True,
        )
        assert sp.encryption_at_rest is True
        assert sp.encryption_in_transit is True
        assert sp.waf_protected is True
        assert sp.rate_limiting is True
        assert sp.auth_required is True
        assert sp.network_segmented is True
        assert sp.backup_enabled is True
        assert sp.backup_frequency_hours == 6.0
        assert sp.patch_sla_hours == 24.0
        assert sp.log_enabled is True
        assert sp.ids_monitored is True


# ===========================================================================
# CostProfile
# ===========================================================================


class TestCostProfile:
    def test_defaults(self):
        cp = CostProfile()
        assert cp.hourly_infra_cost == 0.0
        assert cp.revenue_per_minute == 0.0
        assert cp.sla_credit_percent == 0.0
        assert cp.recovery_engineer_cost == 100.0
        assert cp.monthly_contract_value == 0.0
        assert cp.customer_ltv == 0.0
        assert cp.churn_rate_per_hour_outage == 0.001
        assert cp.recovery_team_size == 0
        assert cp.data_loss_cost_per_gb == 0.0

    def test_custom_values(self):
        cp = CostProfile(
            hourly_infra_cost=50.0,
            revenue_per_minute=200.0,
            sla_credit_percent=10.0,
            recovery_engineer_cost=150.0,
            monthly_contract_value=10000.0,
            customer_ltv=50000.0,
            churn_rate_per_hour_outage=0.01,
            recovery_team_size=5,
            data_loss_cost_per_gb=1000.0,
        )
        assert cp.hourly_infra_cost == 50.0
        assert cp.revenue_per_minute == 200.0
        assert cp.sla_credit_percent == 10.0
        assert cp.recovery_engineer_cost == 150.0
        assert cp.monthly_contract_value == 10000.0
        assert cp.customer_ltv == 50000.0
        assert cp.churn_rate_per_hour_outage == 0.01
        assert cp.recovery_team_size == 5
        assert cp.data_loss_cost_per_gb == 1000.0


# ===========================================================================
# ComplianceTags
# ===========================================================================


class TestComplianceTags:
    def test_defaults(self):
        ct = ComplianceTags()
        assert ct.data_classification == "internal"
        assert ct.pci_scope is False
        assert ct.contains_pii is False
        assert ct.contains_phi is False
        assert ct.audit_logging is False
        assert ct.change_management is False

    def test_custom_values(self):
        ct = ComplianceTags(
            data_classification="restricted",
            pci_scope=True,
            contains_pii=True,
            contains_phi=True,
            audit_logging=True,
            change_management=True,
        )
        assert ct.data_classification == "restricted"
        assert ct.pci_scope is True
        assert ct.contains_pii is True
        assert ct.contains_phi is True
        assert ct.audit_logging is True
        assert ct.change_management is True


# ===========================================================================
# OperationalTeamConfig
# ===========================================================================


class TestOperationalTeamConfig:
    def test_defaults(self):
        otc = OperationalTeamConfig()
        assert otc.team_size == 3
        assert otc.oncall_coverage_hours == 24.0
        assert otc.timezone_coverage == 1
        assert otc.mean_acknowledge_time_minutes == 5.0
        assert otc.mean_diagnosis_time_minutes == 15.0
        assert otc.runbook_coverage_percent == 50.0
        assert otc.automation_percent == 20.0

    def test_custom_values(self):
        otc = OperationalTeamConfig(
            team_size=10,
            oncall_coverage_hours=12.0,
            timezone_coverage=3,
            mean_acknowledge_time_minutes=2.0,
            mean_diagnosis_time_minutes=5.0,
            runbook_coverage_percent=90.0,
            automation_percent=80.0,
        )
        assert otc.team_size == 10
        assert otc.oncall_coverage_hours == 12.0
        assert otc.timezone_coverage == 3
        assert otc.mean_acknowledge_time_minutes == 2.0
        assert otc.mean_diagnosis_time_minutes == 5.0
        assert otc.runbook_coverage_percent == 90.0
        assert otc.automation_percent == 80.0


# ===========================================================================
# RegionConfig
# ===========================================================================


class TestRegionConfig:
    def test_defaults(self):
        rc = RegionConfig()
        assert rc.region == ""
        assert rc.availability_zone == ""
        assert rc.is_primary is True
        assert rc.dr_target_region == ""
        assert rc.rpo_seconds == 0
        assert rc.rto_seconds == 0

    def test_custom_values(self):
        rc = RegionConfig(
            region="us-east-1",
            availability_zone="us-east-1a",
            is_primary=False,
            dr_target_region="us-west-2",
            rpo_seconds=300,
            rto_seconds=600,
        )
        assert rc.region == "us-east-1"
        assert rc.availability_zone == "us-east-1a"
        assert rc.is_primary is False
        assert rc.dr_target_region == "us-west-2"
        assert rc.rpo_seconds == 300
        assert rc.rto_seconds == 600


# ===========================================================================
# ExternalSLAConfig
# ===========================================================================


class TestExternalSLAConfig:
    def test_defaults(self):
        sla = ExternalSLAConfig()
        assert sla.provider_sla == 99.9

    def test_custom(self):
        sla = ExternalSLAConfig(provider_sla=99.99)
        assert sla.provider_sla == 99.99


# ===========================================================================
# NetworkProfile
# ===========================================================================


class TestNetworkProfile:
    def test_defaults(self):
        np = NetworkProfile()
        assert np.rtt_ms == 1.0
        assert np.packet_loss_rate == 0.0001
        assert np.jitter_ms == 0.5
        assert np.dns_resolution_ms == 5.0
        assert np.tls_handshake_ms == 10.0

    def test_custom_values(self):
        np = NetworkProfile(
            rtt_ms=10.0,
            packet_loss_rate=0.01,
            jitter_ms=2.0,
            dns_resolution_ms=50.0,
            tls_handshake_ms=25.0,
        )
        assert np.rtt_ms == 10.0
        assert np.packet_loss_rate == 0.01
        assert np.jitter_ms == 2.0
        assert np.dns_resolution_ms == 50.0
        assert np.tls_handshake_ms == 25.0


# ===========================================================================
# RuntimeJitter
# ===========================================================================


class TestRuntimeJitter:
    def test_defaults(self):
        rj = RuntimeJitter()
        assert rj.gc_pause_ms == 0.0
        assert rj.gc_pause_frequency == 0.0
        assert rj.scheduling_jitter_ms == 0.1

    def test_custom_values(self):
        rj = RuntimeJitter(
            gc_pause_ms=5.0,
            gc_pause_frequency=2.0,
            scheduling_jitter_ms=0.5,
        )
        assert rj.gc_pause_ms == 5.0
        assert rj.gc_pause_frequency == 2.0
        assert rj.scheduling_jitter_ms == 0.5


# ===========================================================================
# Other model classes: Capacity, AutoScalingConfig, FailoverConfig, etc.
# ===========================================================================


class TestCapacity:
    def test_defaults(self):
        c = Capacity()
        assert c.max_connections == 1000
        assert c.max_rps == 5000
        assert c.connection_pool_size == 100
        assert c.max_memory_mb == 8192
        assert c.max_disk_gb == 100
        assert c.timeout_seconds == 30.0
        assert c.retry_multiplier == 3.0

    def test_custom(self):
        c = Capacity(max_connections=500, timeout_seconds=60.0)
        assert c.max_connections == 500
        assert c.timeout_seconds == 60.0


class TestAutoScalingConfig:
    def test_defaults(self):
        asc = AutoScalingConfig()
        assert asc.enabled is False
        assert asc.min_replicas == 1
        assert asc.max_replicas == 1
        assert asc.scale_up_threshold == 70.0
        assert asc.scale_down_threshold == 30.0
        assert asc.scale_up_delay_seconds == 15
        assert asc.scale_down_delay_seconds == 300
        assert asc.scale_up_step == 2


class TestFailoverConfig:
    def test_defaults(self):
        fc = FailoverConfig()
        assert fc.enabled is False
        assert fc.promotion_time_seconds == 30.0
        assert fc.health_check_interval_seconds == 10.0
        assert fc.failover_threshold == 3


class TestCircuitBreakerConfig:
    def test_defaults(self):
        cbc = CircuitBreakerConfig()
        assert cbc.enabled is False
        assert cbc.failure_threshold == 5
        assert cbc.recovery_timeout_seconds == 60.0
        assert cbc.half_open_max_requests == 3
        assert cbc.success_threshold == 2


class TestRetryStrategy:
    def test_defaults(self):
        rs = RetryStrategy()
        assert rs.enabled is False
        assert rs.max_retries == 3
        assert rs.initial_delay_ms == 100.0
        assert rs.max_delay_ms == 30000.0
        assert rs.multiplier == 2.0
        assert rs.jitter is True
        assert rs.retry_budget_per_second == 0.0


class TestCacheWarmingConfig:
    def test_defaults(self):
        cwc = CacheWarmingConfig()
        assert cwc.enabled is False
        assert cwc.initial_hit_ratio == 0.0
        assert cwc.warm_duration_seconds == 300
        assert cwc.warming_curve == "linear"


class TestSingleflightConfig:
    def test_defaults(self):
        sf = SingleflightConfig()
        assert sf.enabled is False
        assert sf.coalesce_ratio == 0.8


class TestSLOTarget:
    def test_defaults(self):
        slo = SLOTarget()
        assert slo.name == ""
        assert slo.metric == "availability"
        assert slo.target == 99.9
        assert slo.unit == "percent"
        assert slo.window_days == 30

    def test_custom(self):
        slo = SLOTarget(
            name="API latency", metric="latency_p99",
            target=500.0, unit="ms", window_days=7,
        )
        assert slo.name == "API latency"
        assert slo.metric == "latency_p99"
        assert slo.target == 500.0
        assert slo.unit == "ms"
        assert slo.window_days == 7


class TestDegradationConfig:
    def test_defaults(self):
        dc = DegradationConfig()
        assert dc.memory_leak_mb_per_hour == 0.0
        assert dc.disk_fill_gb_per_hour == 0.0
        assert dc.connection_leak_per_hour == 0.0


class TestOperationalProfile:
    def test_defaults(self):
        op = OperationalProfile()
        assert op.mtbf_hours == 0.0
        assert op.mttr_minutes == 30.0
        assert op.deploy_downtime_seconds == 30.0
        assert op.maintenance_downtime_minutes == 60.0
        assert isinstance(op.degradation, DegradationConfig)


class TestResourceMetrics:
    def test_defaults(self):
        rm = ResourceMetrics()
        assert rm.cpu_percent == 0.0
        assert rm.memory_percent == 0.0
        assert rm.disk_percent == 0.0
        assert rm.network_connections == 0
        assert rm.open_files == 0
        assert rm.memory_used_mb == 0.0
        assert rm.memory_total_mb == 0.0
        assert rm.disk_used_gb == 0.0
        assert rm.disk_total_gb == 0.0


# ===========================================================================
# ComponentType enum
# ===========================================================================


class TestComponentType:
    def test_all_values(self):
        expected = {
            "load_balancer", "web_server", "app_server", "database",
            "cache", "queue", "storage", "dns", "external_api", "custom",
        }
        actual = {ct.value for ct in ComponentType}
        assert actual == expected


# ===========================================================================
# HealthStatus enum
# ===========================================================================


class TestHealthStatus:
    def test_all_values(self):
        expected = {"healthy", "degraded", "overloaded", "down"}
        actual = {hs.value for hs in HealthStatus}
        assert actual == expected


# ===========================================================================
# Component model
# ===========================================================================


class TestComponent:
    def test_minimal(self):
        c = Component(id="app", name="App", type=ComponentType.APP_SERVER)
        assert c.id == "app"
        assert c.name == "App"
        assert c.type == ComponentType.APP_SERVER
        assert c.replicas == 1
        assert c.health == HealthStatus.HEALTHY
        assert c.host == ""
        assert c.port == 0
        assert c.tags == []
        assert c.parameters == {}
        assert c.external_sla is None

    def test_replicas_validator_rejects_zero(self):
        with pytest.raises(ValidationError, match="replicas must be >= 1"):
            Component(id="x", name="x", type=ComponentType.APP_SERVER, replicas=0)

    def test_replicas_validator_rejects_negative(self):
        with pytest.raises(ValidationError, match="replicas must be >= 1"):
            Component(id="x", name="x", type=ComponentType.APP_SERVER, replicas=-1)

    def test_utilization_cpu_only(self):
        c = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(cpu_percent=65.0),
        )
        assert c.utilization() == 65.0

    def test_utilization_connections(self):
        c = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(network_connections=500),
            capacity=Capacity(max_connections=1000),
        )
        assert c.utilization() == 50.0

    def test_utilization_max_of_factors(self):
        c = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            metrics=ResourceMetrics(
                cpu_percent=40.0, memory_percent=60.0, disk_percent=80.0,
            ),
        )
        assert c.utilization() == 80.0

    def test_utilization_no_metrics(self):
        c = Component(id="app", name="App", type=ComponentType.APP_SERVER)
        assert c.utilization() == 0.0

    def test_effective_capacity_at_replicas(self):
        c = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            replicas=2,
        )
        assert c.effective_capacity_at_replicas(4) == 2.0
        assert c.effective_capacity_at_replicas(2) == 1.0
        assert c.effective_capacity_at_replicas(1) == 0.5

    def test_all_nested_configs_present(self):
        """All nested model configs should be instantiated with defaults."""
        c = Component(id="app", name="App", type=ComponentType.APP_SERVER)
        assert isinstance(c.metrics, ResourceMetrics)
        assert isinstance(c.capacity, Capacity)
        assert isinstance(c.autoscaling, AutoScalingConfig)
        assert isinstance(c.failover, FailoverConfig)
        assert isinstance(c.cache_warming, CacheWarmingConfig)
        assert isinstance(c.singleflight, SingleflightConfig)
        assert isinstance(c.slo_targets, list)
        assert isinstance(c.cost_profile, CostProfile)
        assert isinstance(c.operational_profile, OperationalProfile)
        assert isinstance(c.region, RegionConfig)
        assert isinstance(c.network, NetworkProfile)
        assert isinstance(c.runtime_jitter, RuntimeJitter)
        assert isinstance(c.security, SecurityProfile)
        assert isinstance(c.compliance_tags, ComplianceTags)
        assert isinstance(c.team, OperationalTeamConfig)

    def test_component_with_slo_targets(self):
        c = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            slo_targets=[
                SLOTarget(name="avail", metric="availability", target=99.95),
                SLOTarget(name="latency", metric="latency_p99", target=200.0, unit="ms"),
            ],
        )
        assert len(c.slo_targets) == 2
        assert c.slo_targets[0].name == "avail"

    def test_component_with_external_sla(self):
        c = Component(
            id="api", name="External API", type=ComponentType.EXTERNAL_API,
            external_sla=ExternalSLAConfig(provider_sla=99.95),
        )
        assert c.external_sla is not None
        assert c.external_sla.provider_sla == 99.95

    def test_component_with_tags_and_parameters(self):
        c = Component(
            id="app", name="App", type=ComponentType.APP_SERVER,
            tags=["production", "tier-1"],
            parameters={"timeout": 30, "version": "2.0"},
        )
        assert "production" in c.tags
        assert c.parameters["timeout"] == 30


# ===========================================================================
# Dependency model
# ===========================================================================


class TestDependency:
    def test_defaults(self):
        d = Dependency(source_id="app", target_id="db")
        assert d.source_id == "app"
        assert d.target_id == "db"
        assert d.dependency_type == "requires"
        assert d.protocol == ""
        assert d.port == 0
        assert d.latency_ms == 0.0
        assert d.weight == 1.0
        assert isinstance(d.circuit_breaker, CircuitBreakerConfig)
        assert isinstance(d.retry_strategy, RetryStrategy)

    def test_custom(self):
        d = Dependency(
            source_id="app", target_id="db",
            dependency_type="optional",
            protocol="grpc",
            port=5432,
            latency_ms=5.0,
            weight=0.8,
            circuit_breaker=CircuitBreakerConfig(enabled=True, failure_threshold=3),
            retry_strategy=RetryStrategy(enabled=True, max_retries=5),
        )
        assert d.dependency_type == "optional"
        assert d.protocol == "grpc"
        assert d.port == 5432
        assert d.latency_ms == 5.0
        assert d.weight == 0.8
        assert d.circuit_breaker.enabled is True
        assert d.circuit_breaker.failure_threshold == 3
        assert d.retry_strategy.enabled is True
        assert d.retry_strategy.max_retries == 5
