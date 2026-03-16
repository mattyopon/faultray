"""Tests for faultray.simulator.multi_tenant_isolation module.

Targets 100 % coverage with 140+ tests covering all enums, models,
engine methods, edge cases, and internal helpers.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.multi_tenant_isolation import (
    DataIsolationResult,
    DataLeakRisk,
    IsolationAssessment,
    IsolationLevel,
    IsolationUpgrade,
    MultiTenantIsolationEngine,
    NoisyNeighborResult,
    NoiseType,
    SharedBottleneck,
    SharedResourceRisk,
    Tenant,
    TenantSpikeResult,
    TenantTier,
    _ISOLATION_ATTENUATION,
    _ISOLATION_RANK,
    _NOISE_BASE_IMPACT,
    _NOISE_ERROR_RATE,
    _TIER_MIN_ISOLATION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    cpu: float = 0.0,
    max_rps: int = 5000,
    network_connections: int = 0,
    max_connections: int = 1000,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        capacity=Capacity(max_rps=max_rps, max_connections=max_connections),
        metrics=ResourceMetrics(
            cpu_percent=cpu,
            network_connections=network_connections,
        ),
    )


def _graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


def _tenant(
    tid: str,
    name: str | None = None,
    tier: TenantTier = TenantTier.PROFESSIONAL,
    isolation: IsolationLevel = IsolationLevel.LOGICAL,
    shared: list[str] | None = None,
    quota: dict[str, float] | None = None,
    usage: dict[str, float] | None = None,
) -> Tenant:
    return Tenant(
        id=tid,
        name=name or tid,
        tier=tier,
        isolation_level=isolation,
        shared_components=shared or [],
        resource_quota=quota or {},
        current_usage=usage or {},
    )


# ---------------------------------------------------------------------------
# IsolationLevel enum
# ---------------------------------------------------------------------------


class TestIsolationLevelEnum:
    def test_values(self):
        assert IsolationLevel.NONE == "none"
        assert IsolationLevel.LOGICAL == "logical"
        assert IsolationLevel.NAMESPACE == "namespace"
        assert IsolationLevel.PROCESS == "process"
        assert IsolationLevel.CONTAINER == "container"
        assert IsolationLevel.VM == "vm"
        assert IsolationLevel.PHYSICAL == "physical"

    def test_member_count(self):
        assert len(IsolationLevel) == 7

    def test_is_str_enum(self):
        assert isinstance(IsolationLevel.NONE, str)


# ---------------------------------------------------------------------------
# TenantTier enum
# ---------------------------------------------------------------------------


class TestTenantTierEnum:
    def test_values(self):
        assert TenantTier.FREE == "free"
        assert TenantTier.BASIC == "basic"
        assert TenantTier.PROFESSIONAL == "professional"
        assert TenantTier.ENTERPRISE == "enterprise"
        assert TenantTier.DEDICATED == "dedicated"

    def test_member_count(self):
        assert len(TenantTier) == 5


# ---------------------------------------------------------------------------
# NoiseType enum
# ---------------------------------------------------------------------------


class TestNoiseTypeEnum:
    def test_values(self):
        assert NoiseType.CPU_HOG == "cpu_hog"
        assert NoiseType.MEMORY_HOG == "memory_hog"
        assert NoiseType.DISK_IO_FLOOD == "disk_io_flood"
        assert NoiseType.NETWORK_FLOOD == "network_flood"
        assert NoiseType.CONNECTION_POOL_EXHAUSTION == "connection_pool_exhaustion"
        assert NoiseType.QUERY_STORM == "query_storm"
        assert NoiseType.CACHE_THRASH == "cache_thrash"
        assert NoiseType.LOCK_CONTENTION == "lock_contention"

    def test_member_count(self):
        assert len(NoiseType) == 8


# ---------------------------------------------------------------------------
# Lookup-table sanity
# ---------------------------------------------------------------------------


class TestLookupTables:
    def test_isolation_rank_covers_all(self):
        for lvl in IsolationLevel:
            assert lvl in _ISOLATION_RANK

    def test_isolation_rank_ascending(self):
        prev = -1
        for lvl in IsolationLevel:
            assert _ISOLATION_RANK[lvl] > prev
            prev = _ISOLATION_RANK[lvl]

    def test_tier_min_isolation_covers_all(self):
        for tier in TenantTier:
            assert tier in _TIER_MIN_ISOLATION

    def test_noise_base_impact_covers_all(self):
        for nt in NoiseType:
            assert nt in _NOISE_BASE_IMPACT

    def test_noise_error_rate_covers_all(self):
        for nt in NoiseType:
            assert nt in _NOISE_ERROR_RATE

    def test_isolation_attenuation_covers_all(self):
        for lvl in IsolationLevel:
            assert lvl in _ISOLATION_ATTENUATION

    def test_attenuation_physical_zero(self):
        assert _ISOLATION_ATTENUATION[IsolationLevel.PHYSICAL] == 0.0

    def test_attenuation_none_one(self):
        assert _ISOLATION_ATTENUATION[IsolationLevel.NONE] == 1.0


# ---------------------------------------------------------------------------
# Tenant model
# ---------------------------------------------------------------------------


class TestTenantModel:
    def test_minimal(self):
        t = Tenant(id="t1", name="T1", tier=TenantTier.FREE)
        assert t.id == "t1"
        assert t.tier == TenantTier.FREE
        assert t.shared_components == []
        assert t.resource_quota == {}
        assert t.current_usage == {}
        assert t.isolation_level == IsolationLevel.LOGICAL

    def test_full(self):
        t = _tenant(
            "t2", tier=TenantTier.ENTERPRISE,
            isolation=IsolationLevel.CONTAINER,
            shared=["db-1"], quota={"cpu": 4.0}, usage={"cpu": 2.0},
        )
        assert t.shared_components == ["db-1"]
        assert t.resource_quota == {"cpu": 4.0}
        assert t.current_usage == {"cpu": 2.0}


# ---------------------------------------------------------------------------
# NoisyNeighborResult model
# ---------------------------------------------------------------------------


class TestNoisyNeighborResultModel:
    def test_defaults(self):
        r = NoisyNeighborResult(
            aggressor_tenant_id="a",
            noise_type=NoiseType.CPU_HOG,
        )
        assert r.victim_tenant_ids == []
        assert r.impact_severity == "low"
        assert r.latency_increase_percent == 0.0
        assert r.error_rate_increase_percent == 0.0
        assert r.isolation_breach is False
        assert r.recommendations == []


# ---------------------------------------------------------------------------
# SharedResourceRisk model
# ---------------------------------------------------------------------------


class TestSharedResourceRiskModel:
    def test_defaults(self):
        r = SharedResourceRisk(resource_id="db-1")
        assert r.tenant_ids == []
        assert r.risk_level == "low"
        assert r.contention_score == 0.0


# ---------------------------------------------------------------------------
# DataLeakRisk / DataIsolationResult model
# ---------------------------------------------------------------------------


class TestDataLeakRiskModel:
    def test_creation(self):
        r = DataLeakRisk(
            source_tenant_id="a",
            target_tenant_id="b",
            shared_component_id="db-1",
        )
        assert r.risk_level == "low"


class TestDataIsolationResultModel:
    def test_defaults(self):
        r = DataIsolationResult()
        assert r.verified is True
        assert r.risks == []


# ---------------------------------------------------------------------------
# SharedBottleneck model
# ---------------------------------------------------------------------------


class TestSharedBottleneckModel:
    def test_defaults(self):
        b = SharedBottleneck(component_id="c1")
        assert b.tenant_count == 0
        assert b.severity == "low"


# ---------------------------------------------------------------------------
# IsolationUpgrade model
# ---------------------------------------------------------------------------


class TestIsolationUpgradeModel:
    def test_defaults(self):
        u = IsolationUpgrade(
            tenant_id="t1",
            current_level=IsolationLevel.NONE,
            recommended_level=IsolationLevel.CONTAINER,
        )
        assert u.priority == "medium"
        assert u.estimated_effort == "medium"


# ---------------------------------------------------------------------------
# TenantSpikeResult model
# ---------------------------------------------------------------------------


class TestTenantSpikeResultModel:
    def test_defaults(self):
        r = TenantSpikeResult(tenant_id="t1")
        assert r.multiplier == 1.0
        assert r.isolation_held is True


# ---------------------------------------------------------------------------
# IsolationAssessment model
# ---------------------------------------------------------------------------


class TestIsolationAssessmentModel:
    def test_defaults(self):
        a = IsolationAssessment()
        assert a.tenant_count == 0
        assert a.isolation_score == 0.0
        assert a.data_isolation_verified is True


# ---------------------------------------------------------------------------
# Engine: _find_tenant
# ---------------------------------------------------------------------------


class TestFindTenant:
    def test_found(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1")
        assert e._find_tenant([t], "t1") is t

    def test_not_found(self):
        e = MultiTenantIsolationEngine()
        assert e._find_tenant([], "nope") is None


# ---------------------------------------------------------------------------
# Engine: _impact_severity
# ---------------------------------------------------------------------------


class TestImpactSeverity:
    def test_none(self):
        assert MultiTenantIsolationEngine._impact_severity(0, 0) == "none"

    def test_low(self):
        assert MultiTenantIsolationEngine._impact_severity(5, 1) == "low"

    def test_medium(self):
        assert MultiTenantIsolationEngine._impact_severity(15, 0) == "medium"

    def test_medium_by_error(self):
        assert MultiTenantIsolationEngine._impact_severity(0, 3) == "medium"

    def test_high(self):
        assert MultiTenantIsolationEngine._impact_severity(25, 0) == "high"

    def test_high_by_error(self):
        assert MultiTenantIsolationEngine._impact_severity(0, 6) == "high"

    def test_critical(self):
        assert MultiTenantIsolationEngine._impact_severity(50, 0) == "critical"

    def test_critical_by_error(self):
        assert MultiTenantIsolationEngine._impact_severity(0, 15) == "critical"


# ---------------------------------------------------------------------------
# Engine: _tier_weight
# ---------------------------------------------------------------------------


class TestTierWeight:
    def test_free(self):
        assert MultiTenantIsolationEngine._tier_weight(TenantTier.FREE) == 0.5

    def test_basic(self):
        assert MultiTenantIsolationEngine._tier_weight(TenantTier.BASIC) == 0.75

    def test_professional(self):
        assert MultiTenantIsolationEngine._tier_weight(TenantTier.PROFESSIONAL) == 1.0

    def test_enterprise(self):
        assert MultiTenantIsolationEngine._tier_weight(TenantTier.ENTERPRISE) == 1.5

    def test_dedicated(self):
        assert MultiTenantIsolationEngine._tier_weight(TenantTier.DEDICATED) == 2.0


# ---------------------------------------------------------------------------
# Engine: _estimate_upgrade_effort
# ---------------------------------------------------------------------------


class TestEstimateUpgradeEffort:
    def test_low(self):
        assert MultiTenantIsolationEngine._estimate_upgrade_effort(
            IsolationLevel.LOGICAL, IsolationLevel.NAMESPACE,
        ) == "low"

    def test_medium(self):
        assert MultiTenantIsolationEngine._estimate_upgrade_effort(
            IsolationLevel.LOGICAL, IsolationLevel.CONTAINER,
        ) == "medium"

    def test_high(self):
        assert MultiTenantIsolationEngine._estimate_upgrade_effort(
            IsolationLevel.NONE, IsolationLevel.VM,
        ) == "high"


# ---------------------------------------------------------------------------
# Engine: _is_data_bearing
# ---------------------------------------------------------------------------


class TestIsDataBearing:
    def test_database(self):
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        assert MultiTenantIsolationEngine._is_data_bearing(g, "db") is True

    def test_cache(self):
        g = _graph(_comp("c", ctype=ComponentType.CACHE))
        assert MultiTenantIsolationEngine._is_data_bearing(g, "c") is True

    def test_storage(self):
        g = _graph(_comp("s", ctype=ComponentType.STORAGE))
        assert MultiTenantIsolationEngine._is_data_bearing(g, "s") is True

    def test_app_server(self):
        g = _graph(_comp("a", ctype=ComponentType.APP_SERVER))
        assert MultiTenantIsolationEngine._is_data_bearing(g, "a") is False

    def test_missing_component(self):
        g = _graph()
        assert MultiTenantIsolationEngine._is_data_bearing(g, "x") is False


# ---------------------------------------------------------------------------
# Engine: assess_isolation
# ---------------------------------------------------------------------------


class TestAssessIsolation:
    def test_empty_tenants(self):
        e = MultiTenantIsolationEngine()
        result = e.assess_isolation(_graph(), [])
        assert result.tenant_count == 0
        assert result.isolation_score == 100.0

    def test_single_tenant_no_sharing(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("app"))
        result = e.assess_isolation(g, [_tenant("t1", shared=["app"])])
        assert result.tenant_count == 1
        assert result.isolation_score > 0

    def test_two_tenants_shared_db(self):
        e = MultiTenantIsolationEngine()
        db = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph(db)
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.LOGICAL)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.LOGICAL)
        result = e.assess_isolation(g, [t1, t2])
        assert result.tenant_count == 2
        assert len(result.shared_resource_risks) > 0

    def test_high_isolation_score(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("app"))
        t = _tenant("t1", tier=TenantTier.PROFESSIONAL,
                     isolation=IsolationLevel.CONTAINER, shared=["app"])
        result = e.assess_isolation(g, [t])
        assert result.isolation_score >= 80

    def test_low_isolation_causes_penalty(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t = _tenant("t1", tier=TenantTier.ENTERPRISE,
                     isolation=IsolationLevel.NONE, shared=["db"])
        result = e.assess_isolation(g, [t])
        assert result.isolation_score < 100

    def test_recommendations_for_under_isolated(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t = _tenant("t1", tier=TenantTier.ENTERPRISE,
                     isolation=IsolationLevel.LOGICAL, shared=["db"])
        result = e.assess_isolation(g, [t])
        assert len(result.recommendations) > 0

    def test_data_isolation_verified_flag(self):
        e = MultiTenantIsolationEngine()
        db = _comp("db", ctype=ComponentType.DATABASE)
        g = _graph(db)
        t1 = _tenant("t1", isolation=IsolationLevel.NONE, shared=["db"])
        t2 = _tenant("t2", isolation=IsolationLevel.NONE, shared=["db"])
        result = e.assess_isolation(g, [t1, t2])
        # NONE isolation on a shared DB => data isolation not verified
        assert result.data_isolation_verified is False

    def test_noisy_neighbor_risks_populated(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("app"))
        t1 = _tenant("t1", isolation=IsolationLevel.NONE, shared=["app"])
        t2 = _tenant("t2", isolation=IsolationLevel.NONE, shared=["app"])
        result = e.assess_isolation(g, [t1, t2])
        assert len(result.noisy_neighbor_risks) > 0


# ---------------------------------------------------------------------------
# Engine: simulate_noisy_neighbor
# ---------------------------------------------------------------------------


class TestSimulateNoisyNeighbor:
    def test_unknown_aggressor(self):
        e = MultiTenantIsolationEngine()
        result = e.simulate_noisy_neighbor(
            _graph(), [], "unknown", NoiseType.CPU_HOG,
        )
        assert result.impact_severity == "none"

    def test_no_shared_components(self):
        e = MultiTenantIsolationEngine()
        t1 = _tenant("t1", shared=["a"])
        t2 = _tenant("t2", shared=["b"])
        result = e.simulate_noisy_neighbor(
            _graph(_comp("a"), _comp("b")), [t1, t2], "t1", NoiseType.CPU_HOG,
        )
        assert result.victim_tenant_ids == []
        assert result.impact_severity == "none"

    def test_shared_components_logical(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.LOGICAL)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.LOGICAL)
        result = e.simulate_noisy_neighbor(g, [t1, t2], "t1", NoiseType.CPU_HOG)
        assert "t2" in result.victim_tenant_ids
        assert result.latency_increase_percent > 0

    def test_physical_isolation_zero_impact(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.PHYSICAL)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.PHYSICAL)
        result = e.simulate_noisy_neighbor(g, [t1, t2], "t1", NoiseType.CPU_HOG)
        assert result.latency_increase_percent == 0.0
        assert result.error_rate_increase_percent == 0.0

    def test_isolation_breach_flag(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_noisy_neighbor(
            g, [t1, t2], "t1", NoiseType.CONNECTION_POOL_EXHAUSTION,
        )
        assert result.isolation_breach is True

    def test_connection_pool_recommendation(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_noisy_neighbor(
            g, [t1, t2], "t1", NoiseType.CONNECTION_POOL_EXHAUSTION,
        )
        assert any("connection pool" in r.lower() for r in result.recommendations)

    def test_query_storm_recommendation(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_noisy_neighbor(
            g, [t1, t2], "t1", NoiseType.QUERY_STORM,
        )
        assert any("rate limiting" in r.lower() for r in result.recommendations)

    def test_multiple_victims(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        t1 = _tenant("t1", shared=["db"])
        t2 = _tenant("t2", shared=["db"])
        t3 = _tenant("t3", shared=["db"])
        result = e.simulate_noisy_neighbor(
            g, [t1, t2, t3], "t1", NoiseType.MEMORY_HOG,
        )
        assert sorted(result.victim_tenant_ids) == ["t2", "t3"]

    def test_container_isolation_reduces_impact(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.CONTAINER)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.CONTAINER)
        result = e.simulate_noisy_neighbor(g, [t1, t2], "t1", NoiseType.CPU_HOG)
        base = _NOISE_BASE_IMPACT[NoiseType.CPU_HOG]
        att = _ISOLATION_ATTENUATION[IsolationLevel.CONTAINER]
        assert result.latency_increase_percent == pytest.approx(base * att, abs=0.01)

    def test_vm_isolation_very_low_impact(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.VM)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.VM)
        result = e.simulate_noisy_neighbor(g, [t1, t2], "t1", NoiseType.CPU_HOG)
        assert result.latency_increase_percent < 5.0

    def test_all_noise_types_produce_positive_latency_with_none_isolation(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        for nt in NoiseType:
            t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
            t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
            result = e.simulate_noisy_neighbor(g, [t1, t2], "t1", nt)
            assert result.latency_increase_percent > 0, f"Expected latency for {nt}"

    def test_weak_isolation_recommendation(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_noisy_neighbor(
            g, [t1, t2], "t1", NoiseType.MEMORY_HOG,
        )
        assert any("isolation" in r.lower() for r in result.recommendations)

    def test_no_shared_gives_effective_message(self):
        e = MultiTenantIsolationEngine()
        t1 = _tenant("t1", shared=["a"])
        t2 = _tenant("t2", shared=["b"])
        result = e.simulate_noisy_neighbor(
            _graph(_comp("a"), _comp("b")), [t1, t2], "t1", NoiseType.CPU_HOG,
        )
        assert any("effective" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Engine: verify_data_isolation
# ---------------------------------------------------------------------------


class TestVerifyDataIsolation:
    def test_empty_tenants(self):
        e = MultiTenantIsolationEngine()
        result = e.verify_data_isolation(_graph(), [])
        assert result.verified is True
        assert result.risk_count == 0

    def test_no_shared(self):
        e = MultiTenantIsolationEngine()
        t1 = _tenant("t1", shared=["a"])
        t2 = _tenant("t2", shared=["b"])
        result = e.verify_data_isolation(
            _graph(_comp("a"), _comp("b")), [t1, t2],
        )
        assert result.verified is True

    def test_shared_non_data_bearing_low_risk(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("lb", ctype=ComponentType.LOAD_BALANCER))
        t1 = _tenant("t1", shared=["lb"], isolation=IsolationLevel.NAMESPACE)
        t2 = _tenant("t2", shared=["lb"], isolation=IsolationLevel.NAMESPACE)
        result = e.verify_data_isolation(g, [t1, t2])
        assert result.verified is True
        assert result.risk_count == 1
        assert result.risks[0].risk_level == "low"

    def test_shared_database_none_isolation_critical(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.verify_data_isolation(g, [t1, t2])
        assert result.verified is False
        assert any(r.risk_level == "critical" for r in result.risks)

    def test_shared_database_logical_critical(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.LOGICAL)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.LOGICAL)
        result = e.verify_data_isolation(g, [t1, t2])
        assert result.verified is False

    def test_shared_database_namespace_high(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NAMESPACE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NAMESPACE)
        result = e.verify_data_isolation(g, [t1, t2])
        assert any(r.risk_level == "high" for r in result.risks)
        assert result.verified is False

    def test_shared_database_container_medium(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.CONTAINER)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.CONTAINER)
        result = e.verify_data_isolation(g, [t1, t2])
        assert any(r.risk_level == "medium" for r in result.risks)
        assert result.verified is True

    def test_critical_recommendation(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.verify_data_isolation(g, [t1, t2])
        assert any("critical" in r.lower() for r in result.recommendations)

    def test_three_tenants_shared_db(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        ts = [
            _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE),
            _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE),
            _tenant("t3", shared=["db"], isolation=IsolationLevel.NONE),
        ]
        result = e.verify_data_isolation(g, ts)
        # 3 tenants = C(3,2) = 3 risk pairs
        assert result.risk_count == 3

    def test_mixed_isolation_uses_weaker(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.CONTAINER)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.verify_data_isolation(g, [t1, t2])
        assert result.risks[0].risk_level == "critical"

    def test_unknown_component_still_evaluated(self):
        e = MultiTenantIsolationEngine()
        g = _graph()  # component not in graph
        t1 = _tenant("t1", shared=["missing"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["missing"], isolation=IsolationLevel.NONE)
        result = e.verify_data_isolation(g, [t1, t2])
        assert result.risk_count == 1

    def test_non_data_bearing_none_isolation_high(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("app", ctype=ComponentType.APP_SERVER))
        t1 = _tenant("t1", shared=["app"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["app"], isolation=IsolationLevel.NONE)
        result = e.verify_data_isolation(g, [t1, t2])
        assert result.risks[0].risk_level == "high"

    def test_non_data_bearing_logical_medium(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("app", ctype=ComponentType.APP_SERVER))
        t1 = _tenant("t1", shared=["app"], isolation=IsolationLevel.LOGICAL)
        t2 = _tenant("t2", shared=["app"], isolation=IsolationLevel.LOGICAL)
        result = e.verify_data_isolation(g, [t1, t2])
        assert result.risks[0].risk_level == "medium"

    def test_cache_is_data_bearing(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("c", ctype=ComponentType.CACHE))
        t1 = _tenant("t1", shared=["c"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["c"], isolation=IsolationLevel.NONE)
        result = e.verify_data_isolation(g, [t1, t2])
        assert result.risks[0].risk_level == "critical"

    def test_storage_is_data_bearing(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("s", ctype=ComponentType.STORAGE))
        t1 = _tenant("t1", shared=["s"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["s"], isolation=IsolationLevel.NONE)
        result = e.verify_data_isolation(g, [t1, t2])
        assert result.risks[0].risk_level == "critical"


# ---------------------------------------------------------------------------
# Engine: find_shared_bottlenecks
# ---------------------------------------------------------------------------


class TestFindSharedBottlenecks:
    def test_empty(self):
        e = MultiTenantIsolationEngine()
        assert e.find_shared_bottlenecks(_graph(), []) == []

    def test_no_sharing(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("a"), _comp("b"))
        ts = [_tenant("t1", shared=["a"]), _tenant("t2", shared=["b"])]
        assert e.find_shared_bottlenecks(g, ts) == []

    def test_two_tenants_sharing(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        ts = [_tenant("t1", shared=["db"]), _tenant("t2", shared=["db"])]
        bns = e.find_shared_bottlenecks(g, ts)
        assert len(bns) == 1
        assert bns[0].component_id == "db"
        assert bns[0].tenant_count == 2

    def test_high_utilization_critical(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=90.0)
        g = _graph(c)
        ts = [_tenant("t1", shared=["db"]), _tenant("t2", shared=["db"])]
        bns = e.find_shared_bottlenecks(g, ts)
        assert bns[0].severity == "critical"

    def test_many_tenants_critical(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        ts = [_tenant(f"t{i}", shared=["db"]) for i in range(5)]
        bns = e.find_shared_bottlenecks(g, ts)
        assert bns[0].severity == "critical"
        assert bns[0].tenant_count == 5

    def test_three_tenants_high(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        ts = [_tenant(f"t{i}", shared=["db"]) for i in range(3)]
        bns = e.find_shared_bottlenecks(g, ts)
        assert bns[0].severity == "high"

    def test_moderate_utilization_high(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=65.0)
        g = _graph(c)
        ts = [_tenant("t1", shared=["db"]), _tenant("t2", shared=["db"])]
        bns = e.find_shared_bottlenecks(g, ts)
        assert bns[0].severity == "high"

    def test_sorted_by_severity(self):
        e = MultiTenantIsolationEngine()
        g = _graph(
            _comp("db", cpu=90.0),
            _comp("cache"),
        )
        ts = [
            _tenant("t1", shared=["db", "cache"]),
            _tenant("t2", shared=["db", "cache"]),
        ]
        bns = e.find_shared_bottlenecks(g, ts)
        # db should come first (critical due to 90% cpu)
        assert bns[0].component_id == "db"

    def test_missing_component(self):
        e = MultiTenantIsolationEngine()
        g = _graph()
        ts = [_tenant("t1", shared=["x"]), _tenant("t2", shared=["x"])]
        bns = e.find_shared_bottlenecks(g, ts)
        assert len(bns) == 1
        assert bns[0].component_type == "unknown"

    def test_recommendation_scaling(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=70.0)
        g = _graph(c)
        ts = [_tenant("t1", shared=["db"]), _tenant("t2", shared=["db"])]
        bns = e.find_shared_bottlenecks(g, ts)
        assert "scaling" in bns[0].recommendation.lower() or "partition" in bns[0].recommendation.lower()

    def test_recommendation_monitor_low_util(self):
        e = MultiTenantIsolationEngine()
        c = _comp("app", cpu=10.0)
        g = _graph(c)
        ts = [_tenant("t1", shared=["app"]), _tenant("t2", shared=["app"])]
        bns = e.find_shared_bottlenecks(g, ts)
        assert "monitor" in bns[0].recommendation.lower()


# ---------------------------------------------------------------------------
# Engine: recommend_isolation_upgrades
# ---------------------------------------------------------------------------


class TestRecommendIsolationUpgrades:
    def test_empty(self):
        e = MultiTenantIsolationEngine()
        assert e.recommend_isolation_upgrades(_graph(), []) == []

    def test_no_upgrade_needed(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.FREE, isolation=IsolationLevel.LOGICAL)
        assert e.recommend_isolation_upgrades(_graph(), [t]) == []

    def test_enterprise_needs_container(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.ENTERPRISE,
                     isolation=IsolationLevel.LOGICAL)
        upgrades = e.recommend_isolation_upgrades(_graph(), [t])
        assert len(upgrades) >= 1
        assert upgrades[0].recommended_level == IsolationLevel.CONTAINER
        assert upgrades[0].priority == "critical"

    def test_dedicated_needs_vm(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.DEDICATED,
                     isolation=IsolationLevel.NAMESPACE)
        upgrades = e.recommend_isolation_upgrades(_graph(), [t])
        assert any(u.recommended_level == IsolationLevel.VM for u in upgrades)

    def test_professional_needs_namespace(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.PROFESSIONAL,
                     isolation=IsolationLevel.LOGICAL)
        upgrades = e.recommend_isolation_upgrades(_graph(), [t])
        assert any(u.recommended_level == IsolationLevel.NAMESPACE for u in upgrades)

    def test_data_bearing_shared_low_isolation(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t = _tenant("t1", tier=TenantTier.FREE,
                     isolation=IsolationLevel.NONE, shared=["db"])
        upgrades = e.recommend_isolation_upgrades(g, [t])
        # Should recommend at least namespace for data-bearing
        assert any(
            _ISOLATION_RANK[u.recommended_level] >= _ISOLATION_RANK[IsolationLevel.NAMESPACE]
            for u in upgrades
        )

    def test_sorted_by_priority(self):
        e = MultiTenantIsolationEngine()
        t1 = _tenant("t1", tier=TenantTier.FREE,
                      isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", tier=TenantTier.ENTERPRISE,
                      isolation=IsolationLevel.NONE)
        upgrades = e.recommend_isolation_upgrades(_graph(), [t1, t2])
        # Enterprise (critical) should be first
        assert upgrades[0].tenant_id == "t2"

    def test_no_duplicate_for_same_tenant(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        # Enterprise + data-bearing: tier already demands container >= namespace
        t = _tenant("t1", tier=TenantTier.ENTERPRISE,
                     isolation=IsolationLevel.LOGICAL, shared=["db"])
        upgrades = e.recommend_isolation_upgrades(g, [t])
        tenant_ids = [u.tenant_id for u in upgrades]
        # Should not have duplicate when tier upgrade covers data-bearing upgrade
        assert tenant_ids.count("t1") == 1

    def test_effort_estimation(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.DEDICATED,
                     isolation=IsolationLevel.NONE)
        upgrades = e.recommend_isolation_upgrades(_graph(), [t])
        assert upgrades[0].estimated_effort == "high"

    def test_reason_contains_tier(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.ENTERPRISE,
                     isolation=IsolationLevel.NONE)
        upgrades = e.recommend_isolation_upgrades(_graph(), [t])
        assert "enterprise" in upgrades[0].reason.lower()

    def test_already_sufficient_isolation(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.ENTERPRISE,
                     isolation=IsolationLevel.VM)
        assert e.recommend_isolation_upgrades(_graph(), [t]) == []


# ---------------------------------------------------------------------------
# Engine: simulate_tenant_spike
# ---------------------------------------------------------------------------


class TestSimulateTenantSpike:
    def test_unknown_tenant(self):
        e = MultiTenantIsolationEngine()
        result = e.simulate_tenant_spike(_graph(), [], "x", 5.0)
        assert result.isolation_held is True

    def test_no_shared_components(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", shared=[])
        result = e.simulate_tenant_spike(_graph(), [t], "t1", 5.0)
        assert result.isolation_held is True
        assert result.affected_tenant_ids == []

    def test_spike_affects_cotenants(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=50.0)
        g = _graph(c)
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_tenant_spike(g, [t1, t2], "t1", 3.0)
        assert "t2" in result.affected_tenant_ids
        assert result.isolation_held is False

    def test_high_multiplier_recommendation(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=50.0)
        g = _graph(c)
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_tenant_spike(g, [t1], "t1", 10.0)
        assert any("auto-scaling" in r.lower() for r in result.recommendations)

    def test_resource_exhaustion(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=60.0)
        g = _graph(c)
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_tenant_spike(g, [t1, t2], "t1", 5.0)
        assert len(result.resources_exhausted) > 0

    def test_exhaustion_increases_error_rate(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=60.0)
        g = _graph(c)
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_tenant_spike(g, [t1, t2], "t1", 5.0)
        assert result.error_rate_increase_percent > 0

    def test_isolation_reduces_spike_impact(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=50.0)
        g = _graph(c)
        t1_none = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2_none = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        r_none = e.simulate_tenant_spike(g, [t1_none, t2_none], "t1", 3.0)

        t1_vm = _tenant("t1", shared=["db"], isolation=IsolationLevel.VM)
        t2_vm = _tenant("t2", shared=["db"], isolation=IsolationLevel.VM)
        r_vm = e.simulate_tenant_spike(g, [t1_vm, t2_vm], "t1", 3.0)

        assert r_vm.latency_increase_percent < r_none.latency_increase_percent

    def test_latency_capped_at_200(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=80.0)
        g = _graph(c)
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_tenant_spike(g, [t1, t2], "t1", 100.0)
        assert result.latency_increase_percent <= 200.0

    def test_error_rate_capped_at_50(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=80.0)
        g = _graph(c)
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_tenant_spike(g, [t1, t2], "t1", 100.0)
        assert result.error_rate_increase_percent <= 50.0

    def test_spike_multiplier_recorded(self):
        e = MultiTenantIsolationEngine()
        t1 = _tenant("t1")
        result = e.simulate_tenant_spike(_graph(), [t1], "t1", 7.5)
        assert result.multiplier == 7.5

    def test_missing_component_skipped(self):
        e = MultiTenantIsolationEngine()
        g = _graph()  # no components
        t1 = _tenant("t1", shared=["missing"])
        result = e.simulate_tenant_spike(g, [t1], "t1", 3.0)
        assert result.isolation_held is True


# ---------------------------------------------------------------------------
# Engine: calculate_fair_share
# ---------------------------------------------------------------------------


class TestCalculateFairShare:
    def test_empty(self):
        e = MultiTenantIsolationEngine()
        assert e.calculate_fair_share(_graph(), []) == {}

    def test_single_tenant_with_quota(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", quota={"cpu": 4.0})
        result = e.calculate_fair_share(_graph(), [t])
        assert result["t1"]["cpu"] == 4.0

    def test_two_tenants_sharing_component(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", max_rps=1000)
        g = _graph(c)
        t1 = _tenant("t1", tier=TenantTier.PROFESSIONAL, shared=["db"])
        t2 = _tenant("t2", tier=TenantTier.PROFESSIONAL, shared=["db"])
        result = e.calculate_fair_share(g, [t1, t2])
        # Each gets 500 rps * weight 1.0
        assert result["t1"]["db_capacity"] == 500.0
        assert result["t2"]["db_capacity"] == 500.0

    def test_tier_weighting(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", max_rps=1000)
        g = _graph(c)
        t1 = _tenant("t1", tier=TenantTier.FREE, shared=["db"])
        t2 = _tenant("t2", tier=TenantTier.ENTERPRISE, shared=["db"])
        result = e.calculate_fair_share(g, [t1, t2])
        assert result["t1"]["db_capacity"] < result["t2"]["db_capacity"]

    def test_unshared_resource_zero(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", max_rps=1000)
        g = _graph(c)
        t1 = _tenant("t1", shared=["db"])
        t2 = _tenant("t2", shared=[])
        result = e.calculate_fair_share(g, [t1, t2])
        assert result["t2"]["db_capacity"] == 0.0

    def test_quota_overrides_capacity(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", max_rps=1000)
        g = _graph(c)
        t = _tenant("t1", shared=["db"], quota={"cpu": 8.0})
        result = e.calculate_fair_share(g, [t])
        assert result["t1"]["cpu"] == 8.0

    def test_resource_not_in_quota_zero(self):
        e = MultiTenantIsolationEngine()
        t1 = _tenant("t1", quota={"cpu": 4.0})
        t2 = _tenant("t2", quota={})
        result = e.calculate_fair_share(_graph(), [t1, t2])
        assert result["t2"]["cpu"] == 0.0

    def test_missing_component_zero(self):
        e = MultiTenantIsolationEngine()
        g = _graph()  # no components
        t = _tenant("t1", shared=["missing"])
        result = e.calculate_fair_share(g, [t])
        assert result["t1"]["missing_capacity"] == 0.0

    def test_dedicated_higher_weight(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", max_rps=1000)
        g = _graph(c)
        t1 = _tenant("t1", tier=TenantTier.FREE, shared=["db"])
        t2 = _tenant("t2", tier=TenantTier.DEDICATED, shared=["db"])
        result = e.calculate_fair_share(g, [t1, t2])
        ratio = result["t2"]["db_capacity"] / result["t1"]["db_capacity"]
        assert ratio == pytest.approx(4.0, abs=0.01)  # 2.0/0.5

    def test_three_tenants_fair_split(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", max_rps=3000)
        g = _graph(c)
        ts = [
            _tenant(f"t{i}", tier=TenantTier.PROFESSIONAL, shared=["db"])
            for i in range(3)
        ]
        result = e.calculate_fair_share(g, ts)
        for t in ts:
            assert result[t.id]["db_capacity"] == 1000.0


# ---------------------------------------------------------------------------
# Engine: _find_shared_resource_risks
# ---------------------------------------------------------------------------


class TestFindSharedResourceRisks:
    def test_no_shared(self):
        e = MultiTenantIsolationEngine()
        risks = e._find_shared_resource_risks(
            _graph(_comp("a"), _comp("b")),
            [_tenant("t1", shared=["a"]), _tenant("t2", shared=["b"])],
        )
        assert risks == []

    def test_shared_produces_risk(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        risks = e._find_shared_resource_risks(
            g, [_tenant("t1", shared=["db"]), _tenant("t2", shared=["db"])],
        )
        assert len(risks) == 1
        assert sorted(risks[0].tenant_ids) == ["t1", "t2"]

    def test_contention_score(self):
        e = MultiTenantIsolationEngine()
        c = _comp("db", cpu=50.0)
        g = _graph(c)
        risks = e._find_shared_resource_risks(
            g, [_tenant("t1", shared=["db"]), _tenant("t2", shared=["db"])],
        )
        assert risks[0].contention_score > 0


# ---------------------------------------------------------------------------
# Engine: _assess_noisy_neighbor_risks
# ---------------------------------------------------------------------------


class TestAssessNoisyNeighborRisks:
    def test_weak_isolation_flagged(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", isolation=IsolationLevel.NONE)
        risks = e._assess_noisy_neighbor_risks(_graph(), [t])
        assert len(risks) >= 1
        assert "weak isolation" in risks[0].lower()

    def test_strong_isolation_not_flagged(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", isolation=IsolationLevel.CONTAINER)
        risks = e._assess_noisy_neighbor_risks(_graph(), [t])
        assert all("weak isolation" not in r.lower() for r in risks)

    def test_many_tenants_sharing(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db"))
        ts = [_tenant(f"t{i}", isolation=IsolationLevel.VM, shared=["db"])
              for i in range(3)]
        risks = e._assess_noisy_neighbor_risks(g, ts)
        assert any("shared by 3" in r for r in risks)


# ---------------------------------------------------------------------------
# Engine: _calculate_isolation_score
# ---------------------------------------------------------------------------


class TestCalculateIsolationScore:
    def test_empty(self):
        e = MultiTenantIsolationEngine()
        assert e._calculate_isolation_score(_graph(), [], []) == 100.0

    def test_perfect_isolation(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.FREE, isolation=IsolationLevel.VM)
        score = e._calculate_isolation_score(_graph(), [t], [])
        assert score > 90

    def test_poor_isolation_lower_score(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.ENTERPRISE,
                     isolation=IsolationLevel.NONE)
        score = e._calculate_isolation_score(_graph(), [t], [])
        assert score < 90

    def test_shared_risks_reduce_score(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", tier=TenantTier.FREE, isolation=IsolationLevel.VM)
        risk = SharedResourceRisk(
            resource_id="db", risk_level="critical",
            tenant_ids=["t1", "t2"], contention_score=5.0,
        )
        score = e._calculate_isolation_score(_graph(), [t], [risk])
        assert score < 100.0

    def test_clamped_to_zero(self):
        e = MultiTenantIsolationEngine()
        ts = [
            _tenant(f"t{i}", tier=TenantTier.DEDICATED,
                    isolation=IsolationLevel.NONE)
            for i in range(30)
        ]
        risks = [
            SharedResourceRisk(resource_id=f"r{i}", risk_level="critical",
                               contention_score=10.0)
            for i in range(20)
        ]
        score = e._calculate_isolation_score(_graph(), ts, risks)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Integration: full scenario
# ---------------------------------------------------------------------------


class TestIntegrationFullScenario:
    def test_saas_scenario(self):
        """Multi-tier SaaS with free, pro, and enterprise tenants."""
        e = MultiTenantIsolationEngine()
        db = _comp("db", ctype=ComponentType.DATABASE, cpu=40.0, max_rps=10000)
        cache = _comp("cache", ctype=ComponentType.CACHE, cpu=20.0)
        app = _comp("app", ctype=ComponentType.APP_SERVER, cpu=30.0)
        g = _graph(db, cache, app)

        tenants = [
            _tenant("free-1", tier=TenantTier.FREE,
                    isolation=IsolationLevel.LOGICAL,
                    shared=["db", "cache", "app"]),
            _tenant("pro-1", tier=TenantTier.PROFESSIONAL,
                    isolation=IsolationLevel.NAMESPACE,
                    shared=["db", "cache"]),
            _tenant("ent-1", tier=TenantTier.ENTERPRISE,
                    isolation=IsolationLevel.CONTAINER,
                    shared=["db"]),
        ]

        assessment = e.assess_isolation(g, tenants)
        assert assessment.tenant_count == 3
        assert 0 <= assessment.isolation_score <= 100
        assert isinstance(assessment.shared_resource_risks, list)
        assert isinstance(assessment.recommendations, list)

        # Noisy neighbor simulation
        nn = e.simulate_noisy_neighbor(g, tenants, "free-1", NoiseType.CPU_HOG)
        assert len(nn.victim_tenant_ids) >= 1

        # Data isolation
        data = e.verify_data_isolation(g, tenants)
        assert data.risk_count > 0

        # Bottlenecks
        bottlenecks = e.find_shared_bottlenecks(g, tenants)
        assert len(bottlenecks) > 0

        # Upgrades
        upgrades = e.recommend_isolation_upgrades(g, tenants)
        # pro-1 has namespace but professional needs namespace -> no upgrade
        # free-1 has logical which is fine for free
        # ent-1 has container which is fine for enterprise
        # But free-1 shares data-bearing with low isolation
        assert isinstance(upgrades, list)

        # Fair share
        shares = e.calculate_fair_share(g, tenants)
        assert len(shares) == 3
        for tid in ["free-1", "pro-1", "ent-1"]:
            assert tid in shares

        # Spike
        spike = e.simulate_tenant_spike(g, tenants, "free-1", 5.0)
        assert isinstance(spike.affected_tenant_ids, list)

    def test_single_tenant_dedicated(self):
        """Dedicated tenant should have perfect isolation."""
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        t = _tenant("ent", tier=TenantTier.DEDICATED,
                     isolation=IsolationLevel.VM, shared=["db"])
        assessment = e.assess_isolation(g, [t])
        assert assessment.isolation_score >= 80
        assert assessment.data_isolation_verified is True

    def test_all_none_isolation_worst_case(self):
        """All tenants with no isolation is the worst case."""
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE, cpu=80.0))
        ts = [
            _tenant(f"t{i}", tier=TenantTier.ENTERPRISE,
                    isolation=IsolationLevel.NONE, shared=["db"])
            for i in range(5)
        ]
        assessment = e.assess_isolation(g, ts)
        assert assessment.isolation_score < 30
        assert assessment.data_isolation_verified is False
        assert len(assessment.recommendations) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_tenant_no_shared_components(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", shared=[])
        result = e.assess_isolation(_graph(), [t])
        assert result.tenant_count == 1

    def test_spike_multiplier_one(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", cpu=50.0))
        t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
        result = e.simulate_tenant_spike(g, [t1], "t1", 1.0)
        assert result.latency_increase_percent == 0.0

    def test_spike_multiplier_less_than_one(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", cpu=50.0))
        t1 = _tenant("t1", shared=["db"])
        result = e.simulate_tenant_spike(g, [t1], "t1", 0.5)
        # Multiplier < 1 means no increase
        assert result.latency_increase_percent == 0.0

    def test_noisy_neighbor_severity_values(self):
        """Verify all severity strings are valid."""
        e = MultiTenantIsolationEngine()
        valid = {"none", "low", "medium", "high", "critical"}
        g = _graph(_comp("db"))
        for nt in NoiseType:
            t1 = _tenant("t1", shared=["db"], isolation=IsolationLevel.NONE)
            t2 = _tenant("t2", shared=["db"], isolation=IsolationLevel.NONE)
            result = e.simulate_noisy_neighbor(g, [t1, t2], "t1", nt)
            assert result.impact_severity in valid

    def test_fair_share_with_only_quotas(self):
        e = MultiTenantIsolationEngine()
        t = _tenant("t1", quota={"cpu": 4.0, "mem": 16.0})
        result = e.calculate_fair_share(_graph(), [t])
        assert result["t1"]["cpu"] == 4.0
        assert result["t1"]["mem"] == 16.0

    def test_assess_deduplicates_recommendations(self):
        e = MultiTenantIsolationEngine()
        g = _graph(_comp("db", ctype=ComponentType.DATABASE))
        # Same tenant twice in the list - should not duplicate recommendations
        t1 = _tenant("t1", tier=TenantTier.ENTERPRISE,
                     isolation=IsolationLevel.NONE, shared=["db"])
        result = e.assess_isolation(g, [t1])
        # Check no exact duplicates
        assert len(result.recommendations) == len(set(result.recommendations))
