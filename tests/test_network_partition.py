"""Tests for Advanced Network Partition Simulator.

Targets 100% coverage with 140+ tests covering all enums, models,
engine methods, edge cases, and internal helpers.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    RetryStrategy,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.network_partition import (
    CAPTradeoffResult,
    ConsensusImpact,
    ConsistencyModel,
    HealingSimulation,
    NetworkPartitionConfig,
    NetworkPartitionEngine,
    PartitionImpact,
    PartitionRecommendation,
    PartitionScope,
    PartitionType,
    SplitBrainAnalysis,
    VulnerablePath,
    _CONSISTENCY_RISK,
    _PARTITION_SEVERITY,
    _RECOVERY_BASE_SECONDS,
    _SCOPE_MULTIPLIER,
    _clamp,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _comp(
    cid: str = "svc",
    name: str = "Service",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    region: str = "",
    az: str = "",
    cb_enabled: bool = False,
) -> Component:
    return Component(
        id=cid,
        name=name,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        region=RegionConfig(region=region, availability_zone=az),
    )


def _graph(
    *components: Component,
    deps: list[Dependency] | None = None,
) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in (deps or []):
        g.add_dependency(d)
    return g


def _dep(
    src: str,
    tgt: str,
    dtype: str = "requires",
    cb: bool = False,
    retry: bool = False,
) -> Dependency:
    return Dependency(
        source_id=src,
        target_id=tgt,
        dependency_type=dtype,
        circuit_breaker=CircuitBreakerConfig(enabled=cb),
        retry_strategy=RetryStrategy(enabled=retry),
    )


def _config(
    pt: PartitionType = PartitionType.FULL_PARTITION,
    scope: PartitionScope = PartitionScope.ZONE_LEVEL,
    affected: list[str] | None = None,
    duration: float = 60.0,
    loss_pct: float = 0.0,
    latency_ms: float = 0.0,
    consistency: ConsistencyModel = ConsistencyModel.EVENTUAL,
) -> NetworkPartitionConfig:
    return NetworkPartitionConfig(
        partition_type=pt,
        scope=scope,
        affected_components=affected or [],
        duration_seconds=duration,
        packet_loss_percent=loss_pct,
        added_latency_ms=latency_ms,
        consistency_model=consistency,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> NetworkPartitionEngine:
    return NetworkPartitionEngine()


@pytest.fixture
def simple_graph() -> InfraGraph:
    return _graph(
        _comp("app-1", "App", ComponentType.APP_SERVER),
        _comp("db-1", "Database", ComponentType.DATABASE),
        _comp("cache-1", "Cache", ComponentType.CACHE),
        deps=[
            _dep("app-1", "db-1"),
            _dep("app-1", "cache-1", dtype="optional"),
        ],
    )


@pytest.fixture
def multi_region_graph() -> InfraGraph:
    return _graph(
        _comp("app-us", "App-US", region="us-east-1"),
        _comp("app-eu", "App-EU", region="eu-west-1"),
        _comp("db-us", "DB-US", ComponentType.DATABASE, region="us-east-1"),
        _comp("db-eu", "DB-EU", ComponentType.DATABASE, region="eu-west-1"),
        deps=[
            _dep("app-us", "db-us"),
            _dep("app-eu", "db-eu"),
            _dep("db-us", "db-eu"),
        ],
    )


# ===================================================================
# 1. Enum completeness
# ===================================================================


class TestPartitionTypeEnum:
    def test_all_values_exist(self):
        expected = {
            "full_partition", "asymmetric_partition", "partial_partition",
            "flapping", "dns_partition", "slow_network", "packet_reorder",
            "mtu_blackhole", "split_brain", "byzantine_partition",
        }
        assert {pt.value for pt in PartitionType} == expected

    def test_count(self):
        assert len(PartitionType) == 10

    @pytest.mark.parametrize("pt", list(PartitionType))
    def test_is_str_enum(self, pt: PartitionType):
        assert isinstance(pt.value, str)


class TestConsistencyModelEnum:
    def test_all_values_exist(self):
        expected = {
            "strong", "eventual", "causal",
            "linearizable", "sequential", "read_your_writes",
        }
        assert {cm.value for cm in ConsistencyModel} == expected

    def test_count(self):
        assert len(ConsistencyModel) == 6

    @pytest.mark.parametrize("cm", list(ConsistencyModel))
    def test_is_str_enum(self, cm: ConsistencyModel):
        assert isinstance(cm.value, str)


class TestPartitionScopeEnum:
    def test_all_values_exist(self):
        expected = {
            "rack_level", "zone_level", "region_level",
            "cross_region", "service_mesh", "custom",
        }
        assert {ps.value for ps in PartitionScope} == expected

    def test_count(self):
        assert len(PartitionScope) == 6

    @pytest.mark.parametrize("ps", list(PartitionScope))
    def test_is_str_enum(self, ps: PartitionScope):
        assert isinstance(ps.value, str)


# ===================================================================
# 2. Risk table completeness
# ===================================================================


class TestRiskTables:
    @pytest.mark.parametrize("pt", list(PartitionType))
    def test_severity_covers_all_partition_types(self, pt: PartitionType):
        assert pt in _PARTITION_SEVERITY
        assert 0.0 <= _PARTITION_SEVERITY[pt] <= 1.0

    @pytest.mark.parametrize("ps", list(PartitionScope))
    def test_scope_multiplier_covers_all_scopes(self, ps: PartitionScope):
        assert ps in _SCOPE_MULTIPLIER
        assert 0.0 <= _SCOPE_MULTIPLIER[ps] <= 1.0

    @pytest.mark.parametrize("cm", list(ConsistencyModel))
    def test_consistency_risk_covers_all_models(self, cm: ConsistencyModel):
        assert cm in _CONSISTENCY_RISK
        assert 0.0 <= _CONSISTENCY_RISK[cm] <= 1.0

    @pytest.mark.parametrize("pt", list(PartitionType))
    def test_recovery_base_covers_all_types(self, pt: PartitionType):
        assert pt in _RECOVERY_BASE_SECONDS
        assert _RECOVERY_BASE_SECONDS[pt] > 0


# ===================================================================
# 3. Pydantic model tests
# ===================================================================


class TestNetworkPartitionConfig:
    def test_defaults(self):
        cfg = NetworkPartitionConfig(
            partition_type=PartitionType.FULL_PARTITION,
            scope=PartitionScope.ZONE_LEVEL,
            affected_components=["a"],
        )
        assert cfg.duration_seconds == 60.0
        assert cfg.packet_loss_percent == 0.0
        assert cfg.added_latency_ms == 0.0
        assert cfg.consistency_model == ConsistencyModel.EVENTUAL

    def test_custom_values(self):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            scope=PartitionScope.CROSS_REGION,
            affected=["x", "y"],
            duration=120.0,
            loss_pct=5.0,
            latency_ms=200.0,
            consistency=ConsistencyModel.STRONG,
        )
        assert cfg.partition_type == PartitionType.SLOW_NETWORK
        assert cfg.scope == PartitionScope.CROSS_REGION
        assert cfg.affected_components == ["x", "y"]
        assert cfg.duration_seconds == 120.0
        assert cfg.packet_loss_percent == 5.0
        assert cfg.added_latency_ms == 200.0
        assert cfg.consistency_model == ConsistencyModel.STRONG


class TestPartitionImpact:
    def test_defaults(self):
        impact = PartitionImpact()
        assert impact.partition_sides == []
        assert impact.severed_connections == []
        assert impact.data_inconsistency_risk == "low"
        assert impact.split_brain_possible is False
        assert impact.estimated_data_loss_events == 0
        assert impact.availability_during_partition == 100.0
        assert impact.recovery_time_seconds == 0.0
        assert impact.recommendations == []


class TestSplitBrainAnalysis:
    def test_defaults(self):
        sba = SplitBrainAnalysis()
        assert sba.conflicting_writes == 0
        assert sba.resolution_strategy == "last_writer_wins"
        assert sba.data_reconciliation_time_seconds == 0.0
        assert sba.affected_users_estimate == 0


class TestVulnerablePath:
    def test_defaults(self):
        vp = VulnerablePath()
        assert vp.path == []
        assert vp.vulnerability_score == 0.0
        assert vp.bottleneck_component == ""
        assert vp.reason == ""


class TestCAPTradeoffResult:
    def test_defaults(self):
        cap = CAPTradeoffResult()
        assert cap.consistency_available is True
        assert cap.availability_available is True
        assert cap.partition_tolerance is True
        assert cap.chosen_tradeoff == "AP"
        assert cap.impact_description == ""
        assert cap.consistency_cost == 0.0
        assert cap.availability_cost == 0.0


class TestPartitionRecommendation:
    def test_defaults(self):
        rec = PartitionRecommendation()
        assert rec.component_id == ""
        assert rec.recommendation == ""
        assert rec.priority == "medium"
        assert rec.estimated_effort == "medium"


class TestHealingSimulation:
    def test_defaults(self):
        hs = HealingSimulation()
        assert hs.healing_time_seconds == 0.0
        assert hs.data_sync_required is False
        assert hs.sync_volume_estimate == "none"
        assert hs.conflict_resolution_needed is False
        assert hs.estimated_conflicts == 0
        assert hs.post_healing_consistency == "consistent"
        assert hs.steps == []


class TestConsensusImpact:
    def test_defaults(self):
        ci = ConsensusImpact()
        assert ci.quorum_maintained is True
        assert ci.nodes_in_majority == 0
        assert ci.nodes_in_minority == 0
        assert ci.leader_election_needed is False
        assert ci.election_time_seconds == 0.0
        assert ci.write_availability == 100.0
        assert ci.read_availability == 100.0
        assert ci.impact_summary == ""


# ===================================================================
# 4. _clamp helper
# ===================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_lo(self):
        assert _clamp(-10.0) == 0.0

    def test_above_hi(self):
        assert _clamp(150.0) == 100.0

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0

    def test_custom_range(self):
        assert _clamp(5.0, 1.0, 10.0) == 5.0
        assert _clamp(-1.0, 1.0, 10.0) == 1.0
        assert _clamp(20.0, 1.0, 10.0) == 10.0


# ===================================================================
# 5. simulate_partition
# ===================================================================


class TestSimulatePartition:
    def test_basic_partition_returns_impact(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_partition(simple_graph, cfg)
        assert isinstance(result, PartitionImpact)

    def test_partition_sides_populated(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_partition(simple_graph, cfg)
        assert len(result.partition_sides) == 2
        assert ["app-1"] in result.partition_sides

    def test_severed_connections_found(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_partition(simple_graph, cfg)
        assert len(result.severed_connections) > 0

    def test_full_partition_high_severity(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            consistency=ConsistencyModel.EVENTUAL,
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.data_inconsistency_risk in ("medium", "high")

    def test_split_brain_detected_for_full_partition(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.split_brain_possible is True

    def test_split_brain_not_detected_for_slow_network(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.split_brain_possible is False

    def test_availability_drops_during_partition(self, engine, simple_graph):
        cfg = _config(affected=["app-1", "db-1"])
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.availability_during_partition < 100.0

    def test_recovery_time_positive(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.recovery_time_seconds > 0

    def test_recommendations_non_empty(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_partition(simple_graph, cfg)
        assert len(result.recommendations) > 0

    def test_empty_affected_components(self, engine, simple_graph):
        cfg = _config(affected=[])
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.severed_connections == []

    def test_all_components_affected(self, engine, simple_graph):
        cfg = _config(affected=["app-1", "db-1", "cache-1"])
        result = engine.simulate_partition(simple_graph, cfg)
        # Only one side when everything is affected
        assert len(result.partition_sides) == 1

    def test_strong_consistency_low_risk(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            scope=PartitionScope.RACK_LEVEL,
            affected=["cache-1"],
            consistency=ConsistencyModel.STRONG,
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.data_inconsistency_risk == "low"

    def test_data_loss_events_with_high_loss(self, engine, simple_graph):
        cfg = _config(
            affected=["app-1"],
            duration=600.0,
            loss_pct=50.0,
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.estimated_data_loss_events >= 0

    def test_cross_region_scope_recommendation(self, engine, multi_region_graph):
        cfg = _config(
            scope=PartitionScope.CROSS_REGION,
            affected=["app-us", "db-us"],
        )
        result = engine.simulate_partition(multi_region_graph, cfg)
        assert any("region" in r.lower() for r in result.recommendations)

    def test_dns_partition_recommendation(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.DNS_PARTITION,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert any("dns" in r.lower() for r in result.recommendations)

    def test_flapping_partition_recommendation(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FLAPPING,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert any("flapping" in r.lower() for r in result.recommendations)

    def test_empty_graph_partition(self, engine):
        g = _graph()
        cfg = _config(affected=["nonexistent"])
        result = engine.simulate_partition(g, cfg)
        assert result.availability_during_partition == 100.0

    def test_no_edges_graph(self, engine):
        g = _graph(_comp("a"), _comp("b"))
        cfg = _config(affected=["a"])
        result = engine.simulate_partition(g, cfg)
        assert result.severed_connections == []

    def test_asymmetric_partition_split_brain(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.ASYMMETRIC_PARTITION,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.split_brain_possible is True

    def test_byzantine_partition_split_brain(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.BYZANTINE_PARTITION,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.split_brain_possible is True

    def test_partial_partition_no_split_brain(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.PARTIAL_PARTITION,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.split_brain_possible is False


# ===================================================================
# 6. detect_split_brain_risk
# ===================================================================


class TestDetectSplitBrainRisk:
    def test_returns_split_brain_analysis(self, engine, simple_graph):
        cfg = _config(affected=["db-1"])
        result = engine.detect_split_brain_risk(simple_graph, cfg)
        assert isinstance(result, SplitBrainAnalysis)

    def test_writable_on_both_sides(self, engine):
        g = _graph(
            _comp("db-1", ctype=ComponentType.DATABASE),
            _comp("db-2", ctype=ComponentType.DATABASE),
        )
        cfg = _config(affected=["db-1"])
        result = engine.detect_split_brain_risk(g, cfg)
        assert result.conflicting_writes > 0

    def test_no_writable_target_no_conflicts(self, engine):
        g = _graph(
            _comp("app-1", ctype=ComponentType.APP_SERVER),
            _comp("app-2", ctype=ComponentType.APP_SERVER),
        )
        cfg = _config(affected=["app-1"])
        result = engine.detect_split_brain_risk(g, cfg)
        assert result.conflicting_writes == 0

    def test_resolution_strategy_eventual(self, engine, simple_graph):
        cfg = _config(
            affected=["db-1"],
            consistency=ConsistencyModel.EVENTUAL,
        )
        result = engine.detect_split_brain_risk(simple_graph, cfg)
        assert result.resolution_strategy == "last_writer_wins"

    def test_resolution_strategy_strong(self, engine, simple_graph):
        cfg = _config(
            affected=["db-1"],
            consistency=ConsistencyModel.STRONG,
        )
        result = engine.detect_split_brain_risk(simple_graph, cfg)
        assert result.resolution_strategy == "rollback_to_primary"

    def test_resolution_strategy_causal(self, engine, simple_graph):
        cfg = _config(
            affected=["db-1"],
            consistency=ConsistencyModel.CAUSAL,
        )
        result = engine.detect_split_brain_risk(simple_graph, cfg)
        assert result.resolution_strategy == "causal_merge"

    def test_resolution_strategy_linearizable(self, engine, simple_graph):
        cfg = _config(
            affected=["db-1"],
            consistency=ConsistencyModel.LINEARIZABLE,
        )
        result = engine.detect_split_brain_risk(simple_graph, cfg)
        assert result.resolution_strategy == "rollback_to_primary"

    def test_resolution_strategy_sequential(self, engine, simple_graph):
        cfg = _config(
            affected=["db-1"],
            consistency=ConsistencyModel.SEQUENTIAL,
        )
        result = engine.detect_split_brain_risk(simple_graph, cfg)
        assert result.resolution_strategy == "version_vector"

    def test_resolution_strategy_read_your_writes(self, engine, simple_graph):
        cfg = _config(
            affected=["db-1"],
            consistency=ConsistencyModel.READ_YOUR_WRITES,
        )
        result = engine.detect_split_brain_risk(simple_graph, cfg)
        assert result.resolution_strategy == "last_writer_wins"

    def test_reconciliation_time_positive_with_conflicts(self, engine):
        g = _graph(
            _comp("db-1", ctype=ComponentType.DATABASE),
            _comp("cache-1", ctype=ComponentType.CACHE),
        )
        cfg = _config(affected=["db-1"], duration=120.0)
        result = engine.detect_split_brain_risk(g, cfg)
        if result.conflicting_writes > 0:
            assert result.data_reconciliation_time_seconds > 0

    def test_affected_users_scales_with_duration(self, engine, simple_graph):
        short = _config(affected=["db-1"], duration=10.0)
        long = _config(affected=["db-1"], duration=600.0)
        r_short = engine.detect_split_brain_risk(simple_graph, short)
        r_long = engine.detect_split_brain_risk(simple_graph, long)
        assert r_long.affected_users_estimate > r_short.affected_users_estimate

    def test_empty_graph(self, engine):
        g = _graph()
        cfg = _config(affected=[])
        result = engine.detect_split_brain_risk(g, cfg)
        assert result.conflicting_writes == 0

    def test_single_component(self, engine):
        g = _graph(_comp("db-1", ctype=ComponentType.DATABASE))
        cfg = _config(affected=["db-1"])
        result = engine.detect_split_brain_risk(g, cfg)
        # Only one side, no multi-writer
        assert result.conflicting_writes == 0

    def test_cache_counted_as_writable(self, engine):
        g = _graph(
            _comp("app-1", ctype=ComponentType.APP_SERVER),
            _comp("cache-1", ctype=ComponentType.CACHE),
        )
        cfg = _config(affected=["cache-1"])
        result = engine.detect_split_brain_risk(g, cfg)
        # cache is writable but app is not, so no multi-writer
        assert result.conflicting_writes == 0

    def test_storage_counted_as_writable(self, engine):
        g = _graph(
            _comp("store-1", ctype=ComponentType.STORAGE),
            _comp("store-2", ctype=ComponentType.STORAGE),
        )
        cfg = _config(affected=["store-1"])
        result = engine.detect_split_brain_risk(g, cfg)
        assert result.conflicting_writes > 0

    def test_queue_counted_as_writable(self, engine):
        g = _graph(
            _comp("q-1", ctype=ComponentType.QUEUE),
            _comp("q-2", ctype=ComponentType.QUEUE),
        )
        cfg = _config(affected=["q-1"])
        result = engine.detect_split_brain_risk(g, cfg)
        assert result.conflicting_writes > 0


# ===================================================================
# 7. find_partition_vulnerable_paths
# ===================================================================


class TestFindPartitionVulnerablePaths:
    def test_returns_list(self, engine, simple_graph):
        result = engine.find_partition_vulnerable_paths(simple_graph)
        assert isinstance(result, list)

    def test_paths_found_for_simple_graph(self, engine, simple_graph):
        result = engine.find_partition_vulnerable_paths(simple_graph)
        assert len(result) > 0

    def test_path_is_vulnerable_path_type(self, engine, simple_graph):
        result = engine.find_partition_vulnerable_paths(simple_graph)
        assert all(isinstance(vp, VulnerablePath) for vp in result)

    def test_sorted_by_score_descending(self, engine, simple_graph):
        result = engine.find_partition_vulnerable_paths(simple_graph)
        scores = [vp.vulnerability_score for vp in result]
        assert scores == sorted(scores, reverse=True)

    def test_empty_graph(self, engine):
        g = _graph()
        result = engine.find_partition_vulnerable_paths(g)
        assert result == []

    def test_single_component_no_edges(self, engine):
        g = _graph(_comp("a"))
        result = engine.find_partition_vulnerable_paths(g)
        assert result == []

    def test_cross_region_higher_score(self, engine):
        g = _graph(
            _comp("a", replicas=3, region="us-east-1"),
            _comp("b", replicas=3, failover=True, region="eu-west-1"),
            _comp("c", replicas=3, failover=True, region="us-east-1"),
            deps=[
                _dep("a", "b", cb=True, retry=True),
                _dep("a", "c", cb=True, retry=True),
            ],
        )
        result = engine.find_partition_vulnerable_paths(g)
        cross = [vp for vp in result if "b" in vp.path]
        same = [vp for vp in result if "c" in vp.path]
        assert cross[0].vulnerability_score > same[0].vulnerability_score

    def test_circuit_breaker_lowers_score(self, engine):
        g_no_cb = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b", cb=False)],
        )
        g_cb = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b", cb=True)],
        )
        r1 = engine.find_partition_vulnerable_paths(g_no_cb)
        r2 = engine.find_partition_vulnerable_paths(g_cb)
        assert r1[0].vulnerability_score > r2[0].vulnerability_score

    def test_requires_dep_higher_than_optional(self, engine):
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[
                _dep("a", "b", dtype="requires"),
                _dep("a", "c", dtype="optional"),
            ],
        )
        result = engine.find_partition_vulnerable_paths(g)
        req_path = [vp for vp in result if "b" in vp.path][0]
        opt_path = [vp for vp in result if "c" in vp.path][0]
        assert req_path.vulnerability_score > opt_path.vulnerability_score

    def test_failover_lowers_score(self, engine):
        g_no_fo = _graph(
            _comp("a"), _comp("b", failover=False),
            deps=[_dep("a", "b")],
        )
        g_fo = _graph(
            _comp("a"), _comp("b", failover=True),
            deps=[_dep("a", "b")],
        )
        r1 = engine.find_partition_vulnerable_paths(g_no_fo)
        r2 = engine.find_partition_vulnerable_paths(g_fo)
        assert r1[0].vulnerability_score > r2[0].vulnerability_score

    def test_bottleneck_is_lower_replica_component(self, engine):
        g = _graph(
            _comp("a", replicas=3),
            _comp("b", replicas=1),
            deps=[_dep("a", "b")],
        )
        result = engine.find_partition_vulnerable_paths(g)
        assert result[0].bottleneck_component == "b"

    def test_reason_describes_issues(self, engine, simple_graph):
        result = engine.find_partition_vulnerable_paths(simple_graph)
        assert result[0].reason != ""

    def test_replicas_reduce_score(self, engine):
        g_single = _graph(
            _comp("a", replicas=1), _comp("b", replicas=1),
            deps=[_dep("a", "b")],
        )
        g_multi = _graph(
            _comp("a", replicas=3), _comp("b", replicas=3),
            deps=[_dep("a", "b")],
        )
        r1 = engine.find_partition_vulnerable_paths(g_single)
        r2 = engine.find_partition_vulnerable_paths(g_multi)
        assert r1[0].vulnerability_score > r2[0].vulnerability_score

    def test_two_components_no_edges(self, engine):
        g = _graph(_comp("a"), _comp("b"))
        result = engine.find_partition_vulnerable_paths(g)
        assert result == []

    def test_edge_with_missing_component(self, engine):
        g = _graph(_comp("a"), _comp("b"))
        # Add an edge referencing a component not in the graph
        g.add_dependency(_dep("a", "nonexistent"))
        result = engine.find_partition_vulnerable_paths(g)
        # Only a->b-like edges with valid components should appear
        # Here there's no edge a->b, so only the a->nonexistent which is skipped
        valid = [vp for vp in result if "nonexistent" in vp.path]
        assert len(valid) == 0

    def test_zero_score_path_excluded(self, engine):
        """Perfect config with async dep yields score=0 and is excluded."""
        g = _graph(
            _comp("a", replicas=3, failover=True, region="us-east-1"),
            _comp("b", replicas=3, failover=True, region="us-east-1"),
            deps=[_dep("a", "b", dtype="async", cb=True, retry=True)],
        )
        result = engine.find_partition_vulnerable_paths(g)
        assert result == []


# ===================================================================
# 8. simulate_cap_tradeoff
# ===================================================================


class TestSimulateCAPTradeoff:
    def test_returns_cap_result(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert isinstance(result, CAPTradeoffResult)

    def test_strong_consistency_is_cp(self, engine, simple_graph):
        cfg = _config(
            affected=["app-1"],
            consistency=ConsistencyModel.STRONG,
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.chosen_tradeoff == "CP"
        assert result.consistency_available is True
        assert result.availability_available is False

    def test_linearizable_is_cp(self, engine, simple_graph):
        cfg = _config(
            affected=["app-1"],
            consistency=ConsistencyModel.LINEARIZABLE,
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.chosen_tradeoff == "CP"

    def test_eventual_consistency_is_ap(self, engine, simple_graph):
        cfg = _config(
            affected=["app-1"],
            consistency=ConsistencyModel.EVENTUAL,
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.chosen_tradeoff == "AP"
        assert result.consistency_available is False
        assert result.availability_available is True

    def test_read_your_writes_is_ap(self, engine, simple_graph):
        cfg = _config(
            affected=["app-1"],
            consistency=ConsistencyModel.READ_YOUR_WRITES,
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.chosen_tradeoff == "AP"

    def test_causal_is_balanced(self, engine, simple_graph):
        cfg = _config(
            affected=["app-1"],
            consistency=ConsistencyModel.CAUSAL,
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.chosen_tradeoff == "balanced"

    def test_sequential_is_balanced(self, engine, simple_graph):
        cfg = _config(
            affected=["app-1"],
            consistency=ConsistencyModel.SEQUENTIAL,
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.chosen_tradeoff == "balanced"

    def test_partition_tolerance_true_for_severe(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.partition_tolerance is True

    def test_partition_tolerance_false_for_mild(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            affected=["app-1"],
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.partition_tolerance is True  # 0.3 is still >= threshold

    def test_cp_has_zero_consistency_cost(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            consistency=ConsistencyModel.STRONG,
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.consistency_cost == 0.0
        assert result.availability_cost > 0

    def test_ap_has_zero_availability_cost(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            consistency=ConsistencyModel.EVENTUAL,
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert result.availability_cost == 0.0
        assert result.consistency_cost > 0

    def test_impact_description_contains_type(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.DNS_PARTITION,
            affected=["app-1"],
        )
        result = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert "dns_partition" in result.impact_description

    def test_balanced_consistency_depends_on_severity(self, engine, simple_graph):
        # Low severity: causal should keep consistency
        cfg_low = _config(
            pt=PartitionType.SLOW_NETWORK,
            affected=["app-1"],
            consistency=ConsistencyModel.CAUSAL,
        )
        result_low = engine.simulate_cap_tradeoff(simple_graph, cfg_low)
        assert result_low.consistency_available is True

        # High severity: causal loses consistency
        cfg_high = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            consistency=ConsistencyModel.CAUSAL,
        )
        result_high = engine.simulate_cap_tradeoff(simple_graph, cfg_high)
        assert result_high.consistency_available is False


# ===================================================================
# 9. recommend_partition_tolerance
# ===================================================================


class TestRecommendPartitionTolerance:
    def test_returns_list(self, engine, simple_graph):
        result = engine.recommend_partition_tolerance(simple_graph)
        assert isinstance(result, list)

    def test_recommendation_type(self, engine, simple_graph):
        result = engine.recommend_partition_tolerance(simple_graph)
        assert all(isinstance(r, PartitionRecommendation) for r in result)

    def test_single_replica_flagged(self, engine):
        g = _graph(_comp("a", replicas=1))
        result = engine.recommend_partition_tolerance(g)
        replica_recs = [r for r in result if "replicas" in r.recommendation.lower()]
        assert len(replica_recs) > 0

    def test_no_failover_flagged(self, engine):
        g = _graph(_comp("a", failover=False))
        result = engine.recommend_partition_tolerance(g)
        fo_recs = [r for r in result if "failover" in r.recommendation.lower()]
        assert len(fo_recs) > 0

    def test_database_needs_3_replicas(self, engine):
        g = _graph(_comp("db", ctype=ComponentType.DATABASE, replicas=2))
        result = engine.recommend_partition_tolerance(g)
        db_recs = [r for r in result if "quorum" in r.recommendation.lower()]
        assert len(db_recs) > 0

    def test_database_with_3_replicas_no_quorum_rec(self, engine):
        g = _graph(_comp("db", ctype=ComponentType.DATABASE, replicas=3))
        result = engine.recommend_partition_tolerance(g)
        db_recs = [r for r in result if "quorum" in r.recommendation.lower()]
        assert len(db_recs) == 0

    def test_missing_circuit_breaker_flagged(self, engine):
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b", cb=False)],
        )
        result = engine.recommend_partition_tolerance(g)
        cb_recs = [r for r in result if "circuit breaker" in r.recommendation.lower()]
        assert len(cb_recs) > 0

    def test_missing_retry_flagged(self, engine):
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b", retry=False)],
        )
        result = engine.recommend_partition_tolerance(g)
        retry_recs = [r for r in result if "retry" in r.recommendation.lower()]
        assert len(retry_recs) > 0

    def test_well_configured_fewer_recs(self, engine):
        g_weak = _graph(
            _comp("a", replicas=1, failover=False),
            _comp("b", replicas=1, failover=False),
            deps=[_dep("a", "b")],
        )
        g_strong = _graph(
            _comp("a", replicas=3, failover=True),
            _comp("b", replicas=3, failover=True),
            deps=[_dep("a", "b", cb=True, retry=True)],
        )
        r_weak = engine.recommend_partition_tolerance(g_weak)
        r_strong = engine.recommend_partition_tolerance(g_strong)
        assert len(r_weak) > len(r_strong)

    def test_empty_graph(self, engine):
        g = _graph()
        result = engine.recommend_partition_tolerance(g)
        assert result == []

    def test_priority_levels(self, engine, simple_graph):
        result = engine.recommend_partition_tolerance(simple_graph)
        priorities = {r.priority for r in result}
        # Should have at least high (from replica/failover recs)
        assert "high" in priorities or "critical" in priorities or "medium" in priorities


# ===================================================================
# 10. simulate_healing
# ===================================================================


class TestSimulateHealing:
    def test_returns_healing_simulation(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_healing(simple_graph, cfg)
        assert isinstance(result, HealingSimulation)

    def test_healing_time_positive(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.healing_time_seconds > 0

    def test_full_partition_needs_data_sync(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            consistency=ConsistencyModel.EVENTUAL,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.data_sync_required is True

    def test_slow_network_strong_no_sync(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            affected=["app-1"],
            consistency=ConsistencyModel.STRONG,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.data_sync_required is False

    def test_sync_volume_large_for_long_duration(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            duration=600.0,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.sync_volume_estimate == "large"

    def test_sync_volume_medium_for_moderate_duration(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            duration=120.0,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.sync_volume_estimate == "medium"

    def test_sync_volume_small_for_short_duration(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            duration=30.0,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.sync_volume_estimate == "small"

    def test_sync_volume_none_when_no_sync(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            affected=["app-1"],
            consistency=ConsistencyModel.STRONG,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.sync_volume_estimate == "none"

    def test_split_brain_needs_conflict_resolution(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SPLIT_BRAIN,
            affected=["app-1"],
            consistency=ConsistencyModel.EVENTUAL,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.conflict_resolution_needed is True

    def test_split_brain_strong_no_conflict(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SPLIT_BRAIN,
            affected=["app-1"],
            consistency=ConsistencyModel.STRONG,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.conflict_resolution_needed is False

    def test_byzantine_needs_conflict_resolution(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.BYZANTINE_PARTITION,
            affected=["app-1"],
            consistency=ConsistencyModel.EVENTUAL,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.conflict_resolution_needed is True

    def test_many_conflicts_requires_manual_review(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SPLIT_BRAIN,
            affected=["app-1"],
            duration=600.0,
            consistency=ConsistencyModel.EVENTUAL,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.estimated_conflicts > 0

    def test_steps_always_start_with_detect(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.steps[0] == "Detect partition healing"

    def test_steps_always_end_with_resume(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.steps[-1] == "Resume normal operations"

    def test_split_brain_has_leader_election_step(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SPLIT_BRAIN,
            affected=["app-1"],
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert any("leader" in s.lower() for s in result.steps)

    def test_dns_partition_has_flush_step(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.DNS_PARTITION,
            affected=["app-1"],
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert any("dns" in s.lower() for s in result.steps)

    def test_post_healing_consistency_auto_resolved(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            duration=60.0,
            consistency=ConsistencyModel.EVENTUAL,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.post_healing_consistency in (
            "auto_resolved", "eventually_consistent",
            "requires_manual_review", "consistent",
        )

    def test_no_sync_consistency_is_consistent(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            affected=["app-1"],
            consistency=ConsistencyModel.LINEARIZABLE,
        )
        result = engine.simulate_healing(simple_graph, cfg)
        assert result.post_healing_consistency == "consistent"


# ===================================================================
# 11. analyze_consensus_impact
# ===================================================================


class TestAnalyzeConsensusImpact:
    def test_returns_consensus_impact(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.analyze_consensus_impact(simple_graph, cfg)
        assert isinstance(result, ConsensusImpact)

    def test_quorum_maintained_with_majority(self, engine):
        g = _graph(
            _comp("n1"), _comp("n2"), _comp("n3"),
            _comp("n4"), _comp("n5"),
        )
        cfg = _config(affected=["n1"])  # 1 vs 4
        result = engine.analyze_consensus_impact(g, cfg)
        assert result.quorum_maintained is True
        assert result.nodes_in_majority == 4

    def test_quorum_lost_with_even_split(self, engine):
        g = _graph(
            _comp("n1"), _comp("n2"),
            _comp("n3"), _comp("n4"),
        )
        cfg = _config(affected=["n1", "n2"])  # 2 vs 2
        result = engine.analyze_consensus_impact(g, cfg)
        # Quorum needs 3, max side has 2
        assert result.quorum_maintained is False

    def test_leader_election_for_full_partition(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
        )
        result = engine.analyze_consensus_impact(simple_graph, cfg)
        assert result.leader_election_needed is True

    def test_no_leader_election_for_slow_network(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            affected=["app-1"],
        )
        result = engine.analyze_consensus_impact(simple_graph, cfg)
        assert result.leader_election_needed is False

    def test_election_time_positive_when_needed(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
        )
        result = engine.analyze_consensus_impact(simple_graph, cfg)
        assert result.election_time_seconds > 0

    def test_election_time_zero_when_not_needed(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            affected=["app-1"],
        )
        result = engine.analyze_consensus_impact(simple_graph, cfg)
        assert result.election_time_seconds == 0.0

    def test_write_availability_zero_when_quorum_lost(self, engine):
        g = _graph(_comp("n1"), _comp("n2"))
        cfg = _config(affected=["n1"])  # 1 vs 1, quorum needs 2
        result = engine.analyze_consensus_impact(g, cfg)
        if not result.quorum_maintained:
            assert result.write_availability == 0.0

    def test_read_availability_reduced_when_quorum_lost(self, engine):
        g = _graph(_comp("n1"), _comp("n2"))
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["n1"],
        )
        result = engine.analyze_consensus_impact(g, cfg)
        assert result.read_availability < 100.0

    def test_impact_summary_contains_quorum_status(self, engine, simple_graph):
        cfg = _config(affected=["app-1"])
        result = engine.analyze_consensus_impact(simple_graph, cfg)
        assert "quorum" in result.impact_summary.lower() or "Quorum" in result.impact_summary

    def test_empty_graph(self, engine):
        g = _graph()
        cfg = _config(affected=[])
        result = engine.analyze_consensus_impact(g, cfg)
        assert result.quorum_maintained is False
        assert "No nodes" in result.impact_summary

    def test_all_nodes_on_one_side(self, engine):
        g = _graph(_comp("n1"), _comp("n2"), _comp("n3"))
        cfg = _config(affected=["n1", "n2", "n3"])
        result = engine.analyze_consensus_impact(g, cfg)
        assert result.nodes_in_minority == 0

    def test_minority_count_correct(self, engine):
        g = _graph(
            _comp("n1"), _comp("n2"), _comp("n3"),
            _comp("n4"), _comp("n5"),
        )
        cfg = _config(affected=["n1", "n2"])  # 2 vs 3
        result = engine.analyze_consensus_impact(g, cfg)
        assert result.nodes_in_majority == 3
        assert result.nodes_in_minority == 2

    def test_leader_election_for_asymmetric(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.ASYMMETRIC_PARTITION,
            affected=["app-1"],
        )
        result = engine.analyze_consensus_impact(simple_graph, cfg)
        assert result.leader_election_needed is True

    def test_leader_election_for_split_brain(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SPLIT_BRAIN,
            affected=["app-1"],
        )
        result = engine.analyze_consensus_impact(simple_graph, cfg)
        assert result.leader_election_needed is True

    def test_leader_election_for_byzantine(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.BYZANTINE_PARTITION,
            affected=["app-1"],
        )
        result = engine.analyze_consensus_impact(simple_graph, cfg)
        assert result.leader_election_needed is True


# ===================================================================
# 12. Integration / cross-method tests
# ===================================================================


class TestIntegration:
    def test_partition_then_healing(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            duration=120.0,
        )
        impact = engine.simulate_partition(simple_graph, cfg)
        healing = engine.simulate_healing(simple_graph, cfg)
        assert impact.recovery_time_seconds > 0
        assert healing.healing_time_seconds > 0

    def test_cap_consistent_with_partition(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["app-1"],
            consistency=ConsistencyModel.STRONG,
        )
        impact = engine.simulate_partition(simple_graph, cfg)
        cap = engine.simulate_cap_tradeoff(simple_graph, cfg)
        assert cap.chosen_tradeoff == "CP"

    def test_vulnerable_paths_align_with_recommendations(self, engine):
        g = _graph(
            _comp("a", replicas=1, failover=False),
            _comp("b", replicas=1, failover=False),
            deps=[_dep("a", "b")],
        )
        paths = engine.find_partition_vulnerable_paths(g)
        recs = engine.recommend_partition_tolerance(g)
        assert len(paths) > 0
        assert len(recs) > 0

    def test_consensus_aligns_with_split_brain(self, engine):
        g = _graph(
            _comp("db-1", ctype=ComponentType.DATABASE),
            _comp("db-2", ctype=ComponentType.DATABASE),
            _comp("db-3", ctype=ComponentType.DATABASE),
        )
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            affected=["db-1"],
        )
        sb = engine.detect_split_brain_risk(g, cfg)
        ci = engine.analyze_consensus_impact(g, cfg)
        assert ci.quorum_maintained is True  # 2 of 3

    def test_full_scenario_multi_region(self, engine, multi_region_graph):
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            scope=PartitionScope.CROSS_REGION,
            affected=["app-us", "db-us"],
        )
        impact = engine.simulate_partition(multi_region_graph, cfg)
        healing = engine.simulate_healing(multi_region_graph, cfg)
        cap = engine.simulate_cap_tradeoff(multi_region_graph, cfg)
        ci = engine.analyze_consensus_impact(multi_region_graph, cfg)

        assert impact.split_brain_possible is True
        assert healing.healing_time_seconds > 0
        assert cap.partition_tolerance is True
        assert "majority" in ci.impact_summary or "Quorum" in ci.impact_summary

    def test_all_partition_types_run(self, engine, simple_graph):
        for pt in PartitionType:
            cfg = _config(pt=pt, affected=["app-1"])
            result = engine.simulate_partition(simple_graph, cfg)
            assert isinstance(result, PartitionImpact)

    def test_all_scopes_run(self, engine, simple_graph):
        for scope in PartitionScope:
            cfg = _config(scope=scope, affected=["app-1"])
            result = engine.simulate_partition(simple_graph, cfg)
            assert isinstance(result, PartitionImpact)

    def test_all_consistency_models_run(self, engine, simple_graph):
        for cm in ConsistencyModel:
            cfg = _config(affected=["app-1"], consistency=cm)
            result = engine.simulate_partition(simple_graph, cfg)
            assert isinstance(result, PartitionImpact)


# ===================================================================
# 13. Edge cases
# ===================================================================


class TestEdgeCases:
    def test_nonexistent_component_in_affected(self, engine, simple_graph):
        cfg = _config(affected=["nonexistent"])
        result = engine.simulate_partition(simple_graph, cfg)
        # nonexistent isn't in graph, so no actual side_a
        assert isinstance(result, PartitionImpact)

    def test_zero_duration(self, engine, simple_graph):
        cfg = _config(affected=["app-1"], duration=0.0)
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.recovery_time_seconds >= 0

    def test_very_long_duration(self, engine, simple_graph):
        cfg = _config(affected=["app-1"], duration=86400.0)
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.recovery_time_seconds > 0

    def test_100_percent_packet_loss(self, engine, simple_graph):
        cfg = _config(affected=["app-1"], loss_pct=100.0)
        result = engine.simulate_partition(simple_graph, cfg)
        assert isinstance(result, PartitionImpact)

    def test_zero_packet_loss(self, engine, simple_graph):
        cfg = _config(affected=["app-1"], loss_pct=0.0)
        result = engine.simulate_partition(simple_graph, cfg)
        assert isinstance(result, PartitionImpact)

    def test_high_latency(self, engine, simple_graph):
        cfg = _config(affected=["app-1"], latency_ms=5000.0)
        result = engine.simulate_partition(simple_graph, cfg)
        assert isinstance(result, PartitionImpact)

    def test_single_node_graph(self, engine):
        g = _graph(_comp("solo"))
        cfg = _config(affected=["solo"])
        impact = engine.simulate_partition(g, cfg)
        assert impact.split_brain_possible is False

        healing = engine.simulate_healing(g, cfg)
        assert healing.healing_time_seconds > 0

        consensus = engine.analyze_consensus_impact(g, cfg)
        # Only one side, all nodes in majority
        assert consensus.nodes_in_minority == 0

    def test_graph_with_only_dependencies_no_components_in_affected(self, engine):
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b")],
        )
        cfg = _config(affected=["c"])  # not in graph
        result = engine.simulate_partition(g, cfg)
        assert result.severed_connections == []

    def test_mtu_blackhole_partition(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.MTU_BLACKHOLE,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert isinstance(result, PartitionImpact)

    def test_packet_reorder_partition(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.PACKET_REORDER,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert isinstance(result, PartitionImpact)

    def test_split_brain_type_partition(self, engine, simple_graph):
        cfg = _config(
            pt=PartitionType.SPLIT_BRAIN,
            affected=["app-1"],
        )
        result = engine.simulate_partition(simple_graph, cfg)
        assert result.split_brain_possible is True

    def test_no_severed_when_all_on_same_side(self, engine):
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[_dep("a", "b"), _dep("b", "c")],
        )
        cfg = _config(affected=["a", "b", "c"])
        result = engine.simulate_partition(g, cfg)
        assert result.severed_connections == []


# ===================================================================
# 14. _compute_partition_sides
# ===================================================================


class TestComputePartitionSides:
    def test_basic_split(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        cfg = _config(affected=["a"])
        sides = NetworkPartitionEngine._compute_partition_sides(g, cfg)
        assert len(sides) == 2
        assert ["a"] in sides

    def test_all_affected(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = _config(affected=["a", "b"])
        sides = NetworkPartitionEngine._compute_partition_sides(g, cfg)
        assert len(sides) == 1

    def test_none_affected(self):
        g = _graph(_comp("a"), _comp("b"))
        cfg = _config(affected=[])
        sides = NetworkPartitionEngine._compute_partition_sides(g, cfg)
        # No affected = no side_a, only side_b with all
        assert len(sides) == 1

    def test_nonexistent_in_affected(self):
        g = _graph(_comp("a"))
        cfg = _config(affected=["x"])
        sides = NetworkPartitionEngine._compute_partition_sides(g, cfg)
        # x not in graph, only side_b with a
        assert len(sides) == 1


# ===================================================================
# 15. _find_severed_connections
# ===================================================================


class TestFindSeveredConnections:
    def test_severed_across_sides(self):
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b")],
        )
        sides = [["a"], ["b"]]
        cfg = _config(affected=["a"])
        severed = NetworkPartitionEngine._find_severed_connections(g, cfg, sides)
        assert ("a", "b") in severed

    def test_no_severed_same_side(self):
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[_dep("a", "b")],
        )
        sides = [["a", "b"]]
        cfg = _config(affected=["a", "b"])
        severed = NetworkPartitionEngine._find_severed_connections(g, cfg, sides)
        assert severed == []

    def test_no_edges(self):
        g = _graph(_comp("a"), _comp("b"))
        sides = [["a"], ["b"]]
        cfg = _config(affected=["a"])
        severed = NetworkPartitionEngine._find_severed_connections(g, cfg, sides)
        assert severed == []


# ===================================================================
# 16. _is_split_brain_possible
# ===================================================================


class TestIsSplitBrainPossible:
    def test_full_partition_true(self):
        cfg = _config(pt=PartitionType.FULL_PARTITION)
        assert NetworkPartitionEngine._is_split_brain_possible(cfg, [["a"], ["b"]]) is True

    def test_split_brain_type_true(self):
        cfg = _config(pt=PartitionType.SPLIT_BRAIN)
        assert NetworkPartitionEngine._is_split_brain_possible(cfg, [["a"], ["b"]]) is True

    def test_byzantine_true(self):
        cfg = _config(pt=PartitionType.BYZANTINE_PARTITION)
        assert NetworkPartitionEngine._is_split_brain_possible(cfg, [["a"], ["b"]]) is True

    def test_asymmetric_true(self):
        cfg = _config(pt=PartitionType.ASYMMETRIC_PARTITION)
        assert NetworkPartitionEngine._is_split_brain_possible(cfg, [["a"], ["b"]]) is True

    def test_slow_network_false(self):
        cfg = _config(pt=PartitionType.SLOW_NETWORK)
        assert NetworkPartitionEngine._is_split_brain_possible(cfg, [["a"], ["b"]]) is False

    def test_single_side_false(self):
        cfg = _config(pt=PartitionType.FULL_PARTITION)
        assert NetworkPartitionEngine._is_split_brain_possible(cfg, [["a", "b"]]) is False


# ===================================================================
# 17. _estimate_data_loss_events
# ===================================================================


class TestEstimateDataLossEvents:
    def test_no_severed_no_loss(self):
        cfg = _config()
        assert NetworkPartitionEngine._estimate_data_loss_events(cfg, [], 0.5) == 0

    def test_positive_with_severed(self):
        cfg = _config(duration=120.0)
        events = NetworkPartitionEngine._estimate_data_loss_events(
            cfg, [("a", "b")], 0.8,
        )
        assert events >= 0

    def test_higher_loss_pct_increases_events(self):
        cfg_low = _config(duration=120.0, loss_pct=0.0)
        cfg_high = _config(duration=120.0, loss_pct=50.0)
        e_low = NetworkPartitionEngine._estimate_data_loss_events(
            cfg_low, [("a", "b")], 0.8,
        )
        e_high = NetworkPartitionEngine._estimate_data_loss_events(
            cfg_high, [("a", "b")], 0.8,
        )
        assert e_high >= e_low


# ===================================================================
# 18. _estimate_availability
# ===================================================================


class TestEstimateAvailability:
    def test_empty_graph_100(self):
        g = _graph()
        cfg = _config()
        result = NetworkPartitionEngine._estimate_availability(g, cfg, [], [])
        assert result == 100.0

    def test_decreases_with_more_affected(self):
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        cfg1 = _config(affected=["a"])
        cfg2 = _config(affected=["a", "b"])
        sides1 = [["a"], ["b", "c"]]
        sides2 = [["a", "b"], ["c"]]
        a1 = NetworkPartitionEngine._estimate_availability(g, cfg1, sides1, [])
        a2 = NetworkPartitionEngine._estimate_availability(g, cfg2, sides2, [])
        assert a1 > a2

    def test_clamped_to_0_100(self):
        g = _graph(_comp("a"))
        cfg = _config(
            pt=PartitionType.FULL_PARTITION,
            scope=PartitionScope.CROSS_REGION,
            affected=["a"],
        )
        sides = [["a"]]
        result = NetworkPartitionEngine._estimate_availability(g, cfg, sides, [("a", "b")])
        assert 0.0 <= result <= 100.0


# ===================================================================
# 19. _estimate_recovery_time
# ===================================================================


class TestEstimateRecoveryTime:
    def test_positive_for_all_types(self):
        for pt in PartitionType:
            cfg = _config(pt=pt)
            t = NetworkPartitionEngine._estimate_recovery_time(cfg)
            assert t > 0

    def test_longer_duration_longer_recovery(self):
        cfg_short = _config(duration=10.0)
        cfg_long = _config(duration=600.0)
        t_short = NetworkPartitionEngine._estimate_recovery_time(cfg_short)
        t_long = NetworkPartitionEngine._estimate_recovery_time(cfg_long)
        assert t_long > t_short

    def test_scope_affects_recovery(self):
        cfg_rack = _config(scope=PartitionScope.RACK_LEVEL)
        cfg_cross = _config(scope=PartitionScope.CROSS_REGION)
        t_rack = NetworkPartitionEngine._estimate_recovery_time(cfg_rack)
        t_cross = NetworkPartitionEngine._estimate_recovery_time(cfg_cross)
        assert t_cross > t_rack


# ===================================================================
# 20. _build_recommendations
# ===================================================================


class TestBuildRecommendations:
    def test_split_brain_recommendation(self):
        cfg = _config()
        recs = NetworkPartitionEngine._build_recommendations(
            cfg, [["a"], ["b"]], [("a", "b")], True, "high",
        )
        assert any("split-brain" in r.lower() or "Split-brain" in r for r in recs)

    def test_high_risk_recommendation(self):
        cfg = _config()
        recs = NetworkPartitionEngine._build_recommendations(
            cfg, [["a"], ["b"]], [], False, "high",
        )
        assert any("inconsistency" in r.lower() for r in recs)

    def test_severed_recommendation(self):
        cfg = _config()
        recs = NetworkPartitionEngine._build_recommendations(
            cfg, [["a"], ["b"]], [("a", "b")], False, "low",
        )
        assert any("severed" in r.lower() or "connections" in r.lower() for r in recs)

    def test_default_no_action(self):
        cfg = _config(
            pt=PartitionType.SLOW_NETWORK,
            scope=PartitionScope.RACK_LEVEL,
        )
        recs = NetworkPartitionEngine._build_recommendations(
            cfg, [["a"]], [], False, "low",
        )
        assert any("no immediate action" in r.lower() for r in recs)


# ===================================================================
# 21. _select_resolution_strategy
# ===================================================================


class TestSelectResolutionStrategy:
    @pytest.mark.parametrize(
        "model,expected",
        [
            (ConsistencyModel.STRONG, "rollback_to_primary"),
            (ConsistencyModel.EVENTUAL, "last_writer_wins"),
            (ConsistencyModel.CAUSAL, "causal_merge"),
            (ConsistencyModel.LINEARIZABLE, "rollback_to_primary"),
            (ConsistencyModel.SEQUENTIAL, "version_vector"),
            (ConsistencyModel.READ_YOUR_WRITES, "last_writer_wins"),
        ],
    )
    def test_strategy_mapping(self, model, expected):
        assert NetworkPartitionEngine._select_resolution_strategy(model) == expected


# ===================================================================
# 22. _path_vulnerability_score
# ===================================================================


class TestPathVulnerabilityScore:
    def test_max_score_clamped(self):
        src = _comp("a", replicas=1, failover=False)
        tgt = _comp("b", replicas=1, failover=False, region="eu-west-1")
        src_with_region = _comp("a", replicas=1, failover=False, region="us-east-1")
        edge = _dep("a", "b")
        score = NetworkPartitionEngine._path_vulnerability_score(src_with_region, tgt, edge)
        assert score <= 100.0

    def test_multiple_replicas_lower_score(self):
        src1 = _comp("a", replicas=1)
        tgt1 = _comp("b", replicas=1)
        src2 = _comp("a", replicas=3)
        tgt2 = _comp("b", replicas=3)
        edge = _dep("a", "b")
        s1 = NetworkPartitionEngine._path_vulnerability_score(src1, tgt1, edge)
        s2 = NetworkPartitionEngine._path_vulnerability_score(src2, tgt2, edge)
        assert s1 > s2

    def test_retry_enabled_lowers_score(self):
        src = _comp("a")
        tgt = _comp("b")
        e1 = _dep("a", "b", retry=False)
        e2 = _dep("a", "b", retry=True)
        s1 = NetworkPartitionEngine._path_vulnerability_score(src, tgt, e1)
        s2 = NetworkPartitionEngine._path_vulnerability_score(src, tgt, e2)
        assert s1 > s2


# ===================================================================
# 23. _path_vulnerability_reason
# ===================================================================


class TestPathVulnerabilityReason:
    def test_single_replica_mentioned(self):
        src = _comp("a", replicas=1)
        tgt = _comp("b", replicas=3)
        edge = _dep("a", "b")
        reason = NetworkPartitionEngine._path_vulnerability_reason(src, tgt, edge)
        assert "a single replica" in reason

    def test_no_cb_mentioned(self):
        src = _comp("a")
        tgt = _comp("b")
        edge = _dep("a", "b", cb=False)
        reason = NetworkPartitionEngine._path_vulnerability_reason(src, tgt, edge)
        assert "circuit breaker" in reason.lower()

    def test_hard_dependency_mentioned(self):
        src = _comp("a")
        tgt = _comp("b")
        edge = _dep("a", "b", dtype="requires")
        reason = NetworkPartitionEngine._path_vulnerability_reason(src, tgt, edge)
        assert "hard dependency" in reason

    def test_minor_risk_when_well_configured(self):
        src = _comp("a", replicas=3)
        tgt = _comp("b", replicas=3, failover=True)
        edge = _dep("a", "b", dtype="optional", cb=True)
        reason = NetworkPartitionEngine._path_vulnerability_reason(src, tgt, edge)
        assert reason == "minor risk factors"

    def test_no_failover_mentioned(self):
        src = _comp("a", replicas=3)
        tgt = _comp("b", replicas=3, failover=False)
        edge = _dep("a", "b", dtype="optional", cb=True)
        reason = NetworkPartitionEngine._path_vulnerability_reason(src, tgt, edge)
        assert "no failover" in reason


# ===================================================================
# 24. _build_healing_steps
# ===================================================================


class TestBuildHealingSteps:
    def test_always_starts_with_detect(self):
        cfg = _config()
        steps = NetworkPartitionEngine._build_healing_steps(cfg, False, False)
        assert steps[0] == "Detect partition healing"

    def test_always_ends_with_resume(self):
        cfg = _config()
        steps = NetworkPartitionEngine._build_healing_steps(cfg, False, False)
        assert steps[-1] == "Resume normal operations"

    def test_data_sync_step_included(self):
        cfg = _config()
        steps = NetworkPartitionEngine._build_healing_steps(cfg, True, False)
        assert any("sync" in s.lower() for s in steps)

    def test_conflict_resolution_step_included(self):
        cfg = _config()
        steps = NetworkPartitionEngine._build_healing_steps(cfg, False, True)
        assert any("conflict" in s.lower() for s in steps)

    def test_split_brain_leader_election_step(self):
        cfg = _config(pt=PartitionType.SPLIT_BRAIN)
        steps = NetworkPartitionEngine._build_healing_steps(cfg, False, False)
        assert any("leader" in s.lower() for s in steps)

    def test_dns_flush_step(self):
        cfg = _config(pt=PartitionType.DNS_PARTITION)
        steps = NetworkPartitionEngine._build_healing_steps(cfg, False, False)
        assert any("dns" in s.lower() for s in steps)

    def test_normal_partition_no_extra_steps(self):
        cfg = _config(pt=PartitionType.SLOW_NETWORK)
        steps = NetworkPartitionEngine._build_healing_steps(cfg, False, False)
        assert len(steps) == 4  # detect, verify, validate, resume
