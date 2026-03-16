"""Tests for the Data Replication Analyzer module.

Covers replication lag analysis, split-brain detection, conflict resolution
analysis, cross-region latency modeling, replication factor optimization,
RPO calculation, failover planning, replica health scoring, and comprehensive
report generation. Targets 100% branch coverage.
"""

from __future__ import annotations

import math

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    HealthStatus,
    ResourceMetrics,
    SecurityProfile,
    FailoverConfig,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.data_replication_analyzer import (
    ConflictResolution,
    ConsistencyModel,
    CrossRegionProfile,
    DataReplicationAnalyzer,
    FailoverPlan,
    FailoverStep,
    LagAssessment,
    ReplicaNode,
    ReplicaRole,
    ReplicationAnalysisReport,
    ReplicationCostProfile,
    ReplicationGroup,
    ReplicationStrategy,
    RiskLevel,
    SplitBrainAssessment,
    SplitBrainResolution,
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


def _db_comp(cid="db1", replicas=1, health=HealthStatus.HEALTHY):
    return Component(
        id=cid,
        name=cid,
        type=ComponentType.DATABASE,
        replicas=replicas,
        health=health,
    )


def _make_group(
    group_id="g1",
    strategy=ReplicationStrategy.ASYNCHRONOUS,
    consistency=ConsistencyModel.EVENTUAL,
    conflict=ConflictResolution.LAST_WRITE_WINS,
    split_brain=SplitBrainResolution.MANUAL,
    replication_factor=3,
    nodes=None,
    cross_region=False,
    quorum_read=0,
    quorum_write=0,
):
    return ReplicationGroup(
        group_id=group_id,
        strategy=strategy,
        consistency_model=consistency,
        conflict_resolution=conflict,
        split_brain_resolution=split_brain,
        replication_factor=replication_factor,
        quorum_read=quorum_read,
        quorum_write=quorum_write,
        nodes=nodes or [],
        cross_region=cross_region,
    )


def _make_nodes(count=3, lags=None, regions=None, healthy=None):
    """Create a list of ReplicaNodes. First node is PRIMARY, rest SECONDARY."""
    nodes = []
    for i in range(count):
        role = ReplicaRole.PRIMARY if i == 0 else ReplicaRole.SECONDARY
        lag = (lags[i] if lags and i < len(lags) else 0.0)
        region = (regions[i] if regions and i < len(regions) else "us-east-1")
        is_healthy = (healthy[i] if healthy and i < len(healthy) else True)
        nodes.append(ReplicaNode(
            node_id=f"n{i}",
            component_id=f"db{i}",
            role=role,
            region=region,
            replication_lag_ms=lag,
            is_healthy=is_healthy,
            health_score=100.0 if is_healthy else 40.0,
        ))
    return nodes


# ---------------------------------------------------------------------------
# Test: Replication Lag Analysis
# ---------------------------------------------------------------------------


def test_lag_analysis_empty_group():
    """Empty group should return low risk and a recommendation."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=[])

    result = analyzer.analyze_replication_lag(group)

    assert isinstance(result, LagAssessment)
    assert result.risk_level == RiskLevel.LOW
    assert len(result.recommendations) > 0


def test_lag_analysis_all_arbiters():
    """Group with only arbiters has no data-bearing nodes."""
    g = _graph(_db_comp())
    nodes = [
        ReplicaNode(node_id="a1", component_id="db1", role=ReplicaRole.ARBITER),
        ReplicaNode(node_id="w1", component_id="db1", role=ReplicaRole.WITNESS),
    ]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.analyze_replication_lag(group)
    assert result.risk_level == RiskLevel.LOW
    assert "No data-bearing nodes" in result.recommendations[0]


def test_lag_analysis_low_lag():
    """Low replication lag should yield LOW risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3, lags=[0.0, 5.0, 8.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.analyze_replication_lag(group)
    assert result.risk_level == RiskLevel.LOW
    assert result.max_lag_ms == 8.0
    assert result.avg_lag_ms > 0
    assert result.p99_lag_ms >= 5.0
    assert result.lagging_nodes == []


def test_lag_analysis_high_lag_async():
    """High lag with async replication should be CRITICAL."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    # One node with much higher lag than the others triggers lagging detection
    # (threshold is max(100, avg * 2)). Lags [0, 5, 50000] => avg ~16668, threshold ~33337
    # => n2 at 50000 > 33337 => flagged as lagging
    nodes = _make_nodes(3, lags=[0.0, 5.0, 50000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.ASYNCHRONOUS,
    )

    result = analyzer.analyze_replication_lag(group)
    assert result.risk_level == RiskLevel.CRITICAL
    assert result.max_lag_ms == 50000.0
    assert len(result.lagging_nodes) > 0
    assert result.estimated_data_loss_window_seconds > 0


def test_lag_analysis_sync_strategy_moderate_lag():
    """Synchronous replication with even small lag should flag higher risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 15.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.SYNCHRONOUS,
    )

    result = analyzer.analyze_replication_lag(group)
    assert result.risk_level == RiskLevel.HIGH
    assert result.estimated_data_loss_window_seconds == 0.0


def test_lag_analysis_semi_sync():
    """Semi-synchronous replication lag risk thresholds."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 2000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.SEMI_SYNCHRONOUS,
    )

    result = analyzer.analyze_replication_lag(group)
    assert result.risk_level == RiskLevel.HIGH
    # Semi-sync halves the data loss window
    assert result.estimated_data_loss_window_seconds > 0


def test_lag_analysis_cross_region_recommendation():
    """Cross-region with high lag should recommend read replicas."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(
        2, lags=[0.0, 8000.0], regions=["us-east-1", "eu-west-1"],
    )
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        cross_region=True,
        strategy=ReplicationStrategy.ASYNCHRONOUS,
    )

    result = analyzer.analyze_replication_lag(group)
    has_cross_region_rec = any("Cross-region" in r for r in result.recommendations)
    assert has_cross_region_rec


def test_lag_analysis_sync_high_avg():
    """Sync with high average lag should recommend network review."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[1500.0, 1800.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.SYNCHRONOUS,
    )

    result = analyzer.analyze_replication_lag(group)
    has_perf_rec = any("write performance" in r for r in result.recommendations)
    assert has_perf_rec


# ---------------------------------------------------------------------------
# Test: Split-Brain Detection
# ---------------------------------------------------------------------------


def test_split_brain_empty_group():
    """Empty group should report no susceptibility."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=[])

    result = analyzer.assess_split_brain_risk(group)
    assert not result.is_susceptible
    assert result.risk_level == RiskLevel.LOW


def test_split_brain_single_node():
    """Single node cannot have split-brain."""
    g = _graph(_db_comp("db0"))
    nodes = [ReplicaNode(
        node_id="n0", component_id="db0", role=ReplicaRole.PRIMARY,
    )]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.assess_split_brain_risk(group)
    assert not result.is_susceptible
    assert "Single node" in result.recommendations[0]


def test_split_brain_even_nodes_no_arbiter():
    """Even number of data nodes without arbiter increases risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.assess_split_brain_risk(group)
    assert any("arbiter" in s.lower() for s in result.partition_scenarios)
    has_arbiter_rec = any("arbiter" in r.lower() for r in result.recommendations)
    assert has_arbiter_rec


def test_split_brain_with_arbiter():
    """Adding an arbiter should reduce split-brain scenarios."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2)
    nodes.append(ReplicaNode(
        node_id="a0", component_id="db0", role=ReplicaRole.ARBITER,
    ))
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.assess_split_brain_risk(group)
    # Even with arbiter, 2 data nodes is still risky with async
    has_arbiter_scenario = any("arbiter" in s.lower() for s in result.partition_scenarios)
    # The even-node scenario should NOT appear because arbiter is present
    assert not has_arbiter_scenario


def test_split_brain_cross_region():
    """Cross-region deployment increases partition likelihood."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3, regions=["us-east-1", "eu-west-1", "ap-northeast-1"])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.assess_split_brain_risk(group)
    has_region_scenario = any("region" in s.lower() for s in result.partition_scenarios)
    assert has_region_scenario


def test_split_brain_quorum_low_write():
    """Quorum write below majority should flag risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.QUORUM,
        quorum_write=1,  # Below majority of 2
    )

    result = analyzer.assess_split_brain_risk(group)
    has_quorum_scenario = any("quorum" in s.lower() for s in result.partition_scenarios)
    assert has_quorum_scenario


def test_split_brain_quorum_well_configured():
    """Well-configured quorum should reduce risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.QUORUM,
        quorum_write=2,  # Majority
    )

    result = analyzer.assess_split_brain_risk(group)
    # Should have lower risk than misconfigured quorum
    assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)


def test_split_brain_unhealthy_nodes():
    """Unhealthy nodes amplify split-brain risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3, healthy=[True, False, False])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.assess_split_brain_risk(group)
    has_unhealthy_scenario = any("unhealthy" in s.lower() for s in result.partition_scenarios)
    assert has_unhealthy_scenario


def test_split_brain_manual_resolution_recommendation():
    """Manual resolution should recommend automatic alternatives."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        split_brain=SplitBrainResolution.MANUAL,
    )

    result = analyzer.assess_split_brain_risk(group)
    has_manual_rec = any("manual" in r.lower() for r in result.recommendations)
    assert has_manual_rec


def test_split_brain_lww_resolution_recommendation():
    """LWW should recommend better conflict resolution."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        conflict=ConflictResolution.LAST_WRITE_WINS,
    )

    result = analyzer.assess_split_brain_risk(group)
    has_lww_rec = any("last-write-wins" in r.lower() for r in result.recommendations)
    assert has_lww_rec


def test_split_brain_data_divergence_with_crdt():
    """CRDTs should yield low data divergence risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.SYNCHRONOUS,
        conflict=ConflictResolution.CRDT,
    )

    result = analyzer.assess_split_brain_risk(group)
    # CRDT effectiveness is 0.95, so divergence should be very low
    assert result.data_divergence_risk < 0.1


# ---------------------------------------------------------------------------
# Test: Conflict Resolution Analysis
# ---------------------------------------------------------------------------


def test_conflict_lww():
    """LWW should report low effectiveness and flag risks."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(conflict=ConflictResolution.LAST_WRITE_WINS)

    result = analyzer.analyze_conflict_resolution(group)
    assert result["effectiveness"] == 0.3
    assert len(result["risks"]) >= 2
    assert "vector_clocks" in result["recommended_alternatives"]


def test_conflict_vector_clocks():
    """Vector clocks should have moderate effectiveness."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(conflict=ConflictResolution.VECTOR_CLOCKS)

    result = analyzer.analyze_conflict_resolution(group)
    assert result["effectiveness"] == 0.8
    assert "crdt" in result["recommended_alternatives"]


def test_conflict_crdt():
    """CRDTs should have highest effectiveness."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(conflict=ConflictResolution.CRDT)

    result = analyzer.analyze_conflict_resolution(group)
    assert result["effectiveness"] == 0.95
    assert result["recommended_alternatives"] == []


def test_conflict_custom_merge():
    """Custom merge should flag maintenance risk."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(conflict=ConflictResolution.CUSTOM_MERGE)

    result = analyzer.analyze_conflict_resolution(group)
    assert result["effectiveness"] == 0.7
    assert any("maintained" in r for r in result["risks"])


def test_conflict_cross_region_amplification():
    """Cross-region should amplify conflict risk."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        conflict=ConflictResolution.LAST_WRITE_WINS,
        cross_region=True,
    )

    result = analyzer.analyze_conflict_resolution(group)
    assert result["conflict_amplification"] == 1.5
    assert any("cross-region" in r.lower() for r in result["risks"])


def test_consistency_conflict_compatibility_strong():
    """Strong consistency should be compatible with any resolution."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        consistency=ConsistencyModel.STRONG,
        conflict=ConflictResolution.LAST_WRITE_WINS,
    )

    result = analyzer.analyze_conflict_resolution(group)
    assert result["consistency_compatibility"] == 0.9


def test_consistency_conflict_compatibility_eventual_crdt():
    """Eventual + CRDT should have excellent compatibility."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        consistency=ConsistencyModel.EVENTUAL,
        conflict=ConflictResolution.CRDT,
    )

    result = analyzer.analyze_conflict_resolution(group)
    assert result["consistency_compatibility"] == 0.95


def test_consistency_conflict_compatibility_causal_vc():
    """Causal + vector clocks should be well-suited."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        consistency=ConsistencyModel.CAUSAL,
        conflict=ConflictResolution.VECTOR_CLOCKS,
    )

    result = analyzer.analyze_conflict_resolution(group)
    assert result["consistency_compatibility"] == 0.9


def test_consistency_conflict_compatibility_ryw():
    """Read-your-writes + LWW should have moderate compatibility."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        consistency=ConsistencyModel.READ_YOUR_WRITES,
        conflict=ConflictResolution.LAST_WRITE_WINS,
    )

    result = analyzer.analyze_conflict_resolution(group)
    assert result["consistency_compatibility"] == 0.6


# ---------------------------------------------------------------------------
# Test: Cross-Region Latency Modeling
# ---------------------------------------------------------------------------


def test_cross_region_not_enabled():
    """Non cross-region group should return empty profiles."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(cross_region=False)

    result = analyzer.model_cross_region_latency(group)
    assert result == []


def test_cross_region_two_known_regions():
    """Known region pair should use baseline latency."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, regions=["us-east-1", "eu-west-1"])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes, cross_region=True)

    profiles = analyzer.model_cross_region_latency(group)
    assert len(profiles) == 1
    assert profiles[0].estimated_latency_ms == 85.0
    assert profiles[0].regulatory_risk is True


def test_cross_region_unknown_regions():
    """Unknown region pair should default to 100ms."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, regions=["mars-1", "venus-2"])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes, cross_region=True)

    profiles = analyzer.model_cross_region_latency(group)
    assert len(profiles) == 1
    assert profiles[0].estimated_latency_ms == 100.0


def test_cross_region_same_region():
    """Same-region nodes should have minimal latency."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, regions=["us-east-1", "us-east-1"])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes, cross_region=True)

    profiles = analyzer.model_cross_region_latency(group)
    # Only one unique region, so no pairs
    assert len(profiles) == 0


def test_cross_region_three_regions():
    """Three regions should produce three profiles."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(
        3, regions=["us-east-1", "us-west-2", "eu-west-1"],
    )
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes, cross_region=True)

    profiles = analyzer.model_cross_region_latency(group)
    assert len(profiles) == 3


def test_cross_region_consistency_risk_sync():
    """Synchronous replication should show low consistency risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, regions=["us-east-1", "ap-northeast-1"])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        cross_region=True,
        strategy=ReplicationStrategy.SYNCHRONOUS,
    )

    profiles = analyzer.model_cross_region_latency(group)
    assert profiles[0].consistency_risk < 0.2


# ---------------------------------------------------------------------------
# Test: Replication Factor Optimization
# ---------------------------------------------------------------------------


def test_replication_factor_range():
    """Should produce profiles for factors 1 through max."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)

    profiles = analyzer.optimize_replication_factor(
        3, ReplicationStrategy.ASYNCHRONOUS, max_factor=5,
    )
    assert len(profiles) == 5
    assert profiles[0].replication_factor == 1
    assert profiles[-1].replication_factor == 5


def test_replication_factor_durability_increases():
    """Durability should increase with replication factor."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)

    profiles = analyzer.optimize_replication_factor(
        3, ReplicationStrategy.ASYNCHRONOUS, max_factor=5,
    )
    for i in range(1, len(profiles)):
        assert profiles[i].durability_nines > profiles[i - 1].durability_nines


def test_replication_factor_cost_increases():
    """Storage cost should increase linearly with factor."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)

    profiles = analyzer.optimize_replication_factor(
        3, ReplicationStrategy.SYNCHRONOUS, max_factor=4,
    )
    assert profiles[0].storage_cost_multiplier == 1.0
    assert profiles[2].storage_cost_multiplier == 3.0


def test_replication_factor_sync_write_latency():
    """Synchronous replication write latency should scale with factor."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)

    profiles = analyzer.optimize_replication_factor(
        3, ReplicationStrategy.SYNCHRONOUS, max_factor=4,
    )
    # RF=4 should have higher write latency than RF=1
    assert profiles[3].write_latency_multiplier > profiles[0].write_latency_multiplier


def test_replication_factor_max_factor_zero():
    """max_factor < 1 should be clamped to 1."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)

    profiles = analyzer.optimize_replication_factor(
        1, ReplicationStrategy.ASYNCHRONOUS, max_factor=0,
    )
    assert len(profiles) == 1


def test_replication_factor_quorum_latency():
    """Quorum strategy should have quorum-based write latency."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)

    profiles = analyzer.optimize_replication_factor(
        3, ReplicationStrategy.QUORUM, max_factor=5,
    )
    # Quorum latency for RF=5: quorum = 3
    assert profiles[4].write_latency_multiplier > profiles[0].write_latency_multiplier


def test_replication_factor_semi_sync_latency():
    """Semi-sync should have modest latency increase."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)

    profiles = analyzer.optimize_replication_factor(
        1, ReplicationStrategy.SEMI_SYNCHRONOUS, max_factor=3,
    )
    # RF=2 and RF=3 should have similar latency for semi-sync
    assert profiles[1].write_latency_multiplier == profiles[2].write_latency_multiplier


# ---------------------------------------------------------------------------
# Test: RPO Calculation
# ---------------------------------------------------------------------------


def test_rpo_empty_group():
    """Empty group should have zero RPO."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=[])

    assert analyzer.calculate_rpo(group) == 0.0


def test_rpo_sync():
    """Synchronous replication should have zero RPO."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 5.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.SYNCHRONOUS,
    )

    assert analyzer.calculate_rpo(group) == 0.0


def test_rpo_async():
    """Async replication RPO should be based on max lag."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 5000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.ASYNCHRONOUS,
        consistency=ConsistencyModel.EVENTUAL,
    )

    rpo = analyzer.calculate_rpo(group)
    assert rpo > 0.0
    # Should be max_lag/1000 * (1 + consistency_factor)
    expected = (5000.0 / 1000.0) * (1.0 + 0.6)
    assert abs(rpo - expected) < 0.01


def test_rpo_semi_sync():
    """Semi-sync RPO should be lower than async."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 5000.0])
    analyzer = DataReplicationAnalyzer(g)

    async_group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.ASYNCHRONOUS,
        consistency=ConsistencyModel.EVENTUAL,
    )
    semi_group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.SEMI_SYNCHRONOUS,
        consistency=ConsistencyModel.EVENTUAL,
    )

    rpo_async = analyzer.calculate_rpo(async_group)
    rpo_semi = analyzer.calculate_rpo(semi_group)
    assert rpo_semi < rpo_async


def test_rpo_quorum_with_write():
    """Quorum RPO should consider quorum coverage."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3, lags=[0.0, 2000.0, 3000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.QUORUM,
        quorum_write=2,
        consistency=ConsistencyModel.STRONG,
    )

    rpo = analyzer.calculate_rpo(group)
    assert rpo >= 0.0


def test_rpo_quorum_no_write_config():
    """Quorum with no write quorum should fall back to base RPO."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 1000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.QUORUM,
        quorum_write=0,
        consistency=ConsistencyModel.EVENTUAL,
    )

    rpo = analyzer.calculate_rpo(group)
    assert rpo > 0.0


# ---------------------------------------------------------------------------
# Test: Failover Planning
# ---------------------------------------------------------------------------


def test_failover_empty_group():
    """Empty group should produce CRITICAL risk plan."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=[])

    plan = analyzer.plan_failover(group)
    assert plan.risk_level == RiskLevel.CRITICAL
    assert plan.trigger == "no_nodes"


def test_failover_no_primary():
    """Group without primary should trigger emergency election."""
    g = _graph(_db_comp("db0"))
    nodes = [ReplicaNode(
        node_id="n0", component_id="db0", role=ReplicaRole.SECONDARY,
        is_healthy=True,
    )]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    plan = analyzer.plan_failover(group)
    assert plan.trigger == "no_primary"
    assert plan.steps[0].action == "emergency_election"


def test_failover_no_healthy_secondary():
    """No healthy secondaries should produce await_recovery plan."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = [
        ReplicaNode(
            node_id="n0", component_id="db0", role=ReplicaRole.PRIMARY,
            is_healthy=True,
        ),
        ReplicaNode(
            node_id="n1", component_id="db1", role=ReplicaRole.SECONDARY,
            is_healthy=False,
        ),
    ]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    plan = analyzer.plan_failover(group)
    assert plan.trigger == "no_healthy_secondary"
    assert plan.risk_level == RiskLevel.CRITICAL


def test_failover_normal():
    """Normal failover with healthy secondaries should produce full plan."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3, lags=[0.0, 50.0, 200.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    plan = analyzer.plan_failover(group)
    assert plan.trigger == "primary_failure"
    assert len(plan.steps) == 5
    assert plan.steps[0].action == "detect_primary_failure"
    assert plan.steps[1].action == "fence_old_primary"
    assert plan.steps[2].action == "promote_secondary"
    assert plan.steps[3].action == "redirect_clients"
    assert plan.steps[4].action == "verify_replication_health"
    assert plan.total_estimated_seconds > 0
    assert plan.rto_seconds == plan.total_estimated_seconds


def test_failover_prefers_low_lag_candidate():
    """Failover should prefer the secondary with lowest lag."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3, lags=[0.0, 50.0, 5000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    plan = analyzer.plan_failover(group)
    # Step 3 should promote the node with 50ms lag (n1)
    promote_step = plan.steps[2]
    assert promote_step.target_node_id == "n1"


def test_failover_cross_region_adds_time():
    """Cross-region failover should include additional DNS delay."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 100.0], regions=["us-east-1", "eu-west-1"])
    analyzer = DataReplicationAnalyzer(g)

    local_group = _make_group(nodes=nodes, cross_region=False)
    remote_group = _make_group(nodes=nodes, cross_region=True)

    local_plan = analyzer.plan_failover(local_group)
    remote_plan = analyzer.plan_failover(remote_group)

    assert remote_plan.total_estimated_seconds > local_plan.total_estimated_seconds


def test_failover_sync_low_risk():
    """Sync replication failover with low lag should be LOW risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 2.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.SYNCHRONOUS,
    )

    plan = analyzer.plan_failover(group)
    assert plan.risk_level == RiskLevel.LOW


def test_failover_high_lag_critical():
    """High lag candidate should be CRITICAL risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 15000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    plan = analyzer.plan_failover(group)
    assert plan.risk_level == RiskLevel.CRITICAL


# ---------------------------------------------------------------------------
# Test: Replica Health Scoring
# ---------------------------------------------------------------------------


def test_health_scoring_empty_group():
    """Empty group should have zero group health."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=[])

    result = analyzer.score_replica_health(group)
    assert result["group_health"] == 0.0
    assert result["node_scores"] == {}


def test_health_scoring_all_healthy():
    """All healthy nodes should have high health."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    assert result["group_health"] == 100.0
    assert len(result["degraded_nodes"]) == 0
    assert "healthy" in result["recommendations"][0].lower()


def test_health_scoring_unhealthy_node():
    """Unhealthy node should have degraded score."""
    g = _graph(_db_comp("db0"), _db_comp("db1", health=HealthStatus.DOWN))
    nodes = _make_nodes(2, healthy=[True, False])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    assert result["node_scores"]["n1"] < 70.0
    assert "n1" in result["degraded_nodes"]


def test_health_scoring_high_lag():
    """High replication lag should reduce node health."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 12000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    assert result["node_scores"]["n1"] < result["node_scores"]["n0"]


def test_health_scoring_overloaded_component():
    """Component with high utilization should reduce health."""
    comp = Component(
        id="db1", name="db1", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(cpu_percent=95.0),
        capacity=Capacity(max_connections=100),
    )
    g = _graph(_db_comp("db0"), comp)
    nodes = _make_nodes(2)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    assert result["node_scores"]["n1"] < 100.0


def test_health_scoring_degraded_component():
    """Degraded component status should reduce health."""
    comp = Component(
        id="db1", name="db1", type=ComponentType.DATABASE,
        health=HealthStatus.DEGRADED,
    )
    g = _graph(_db_comp("db0"), comp)
    nodes = _make_nodes(2)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    assert result["node_scores"]["n1"] < 100.0


def test_health_scoring_primary_weighted():
    """Primary should be weighted higher in group health."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = [
        ReplicaNode(
            node_id="n0", component_id="db0", role=ReplicaRole.PRIMARY,
            health_score=50.0,
        ),
        ReplicaNode(
            node_id="n1", component_id="db1", role=ReplicaRole.SECONDARY,
            health_score=100.0,
        ),
    ]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    # Group health should be weighted toward the primary's lower score
    # Primary weight=2, secondary weight=1 => (50*2 + 100*1) / 3 = 66.7
    assert result["group_health"] < 75.0


def test_health_scoring_low_group_health_recommendation():
    """Group health below 50 should generate critical recommendation."""
    g = _graph(_db_comp("db0", health=HealthStatus.DOWN))
    nodes = [
        ReplicaNode(
            node_id="n0", component_id="db0", role=ReplicaRole.PRIMARY,
            is_healthy=False, health_score=10.0,
        ),
    ]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    assert result["group_health"] < 50.0
    has_critical_rec = any("critically" in r.lower() for r in result["recommendations"])
    assert has_critical_rec


def test_health_scoring_arbiter_lag_ignored():
    """Arbiter nodes should not be penalized for lag."""
    g = _graph(_db_comp("db0"))
    nodes = [
        ReplicaNode(
            node_id="n0", component_id="db0", role=ReplicaRole.PRIMARY,
            replication_lag_ms=0.0,
        ),
        ReplicaNode(
            node_id="a0", component_id="db0", role=ReplicaRole.ARBITER,
            replication_lag_ms=999999.0,  # Should be ignored
        ),
    ]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    # Arbiter's lag should not drag down its health through lag penalty
    assert result["node_scores"]["a0"] >= 70.0


# ---------------------------------------------------------------------------
# Test: Comprehensive Report
# ---------------------------------------------------------------------------


def test_report_empty_groups():
    """Report with no groups should return minimal report."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)

    report = analyzer.generate_report([])
    assert isinstance(report, ReplicationAnalysisReport)
    assert report.groups_analyzed == 0
    assert report.overall_replication_health == 0.0


def test_report_single_group():
    """Report with a single group should include all analysis types."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"))
    nodes = _make_nodes(3, lags=[0.0, 100.0, 200.0])
    group = _make_group(nodes=nodes, cross_region=False)
    analyzer = DataReplicationAnalyzer(g)

    report = analyzer.generate_report([group])
    assert report.groups_analyzed == 1
    assert len(report.lag_assessments) == 1
    assert len(report.split_brain_assessments) == 1
    assert len(report.failover_plans) == 1
    assert len(report.cost_profiles) > 0
    assert report.overall_replication_health > 0
    assert report.analyzed_at != ""


def test_report_multiple_groups():
    """Report with multiple groups should aggregate correctly."""
    g = _graph(
        _db_comp("db0"), _db_comp("db1"),
        _db_comp("db2"), _db_comp("db3"),
    )
    nodes1 = _make_nodes(2, lags=[0.0, 100.0])
    nodes2 = [
        ReplicaNode(node_id="n2", component_id="db2", role=ReplicaRole.PRIMARY),
        ReplicaNode(node_id="n3", component_id="db3", role=ReplicaRole.SECONDARY,
                    replication_lag_ms=5000.0),
    ]
    group1 = _make_group(group_id="g1", nodes=nodes1)
    group2 = _make_group(group_id="g2", nodes=nodes2)
    analyzer = DataReplicationAnalyzer(g)

    report = analyzer.generate_report([group1, group2])
    assert report.groups_analyzed == 2
    assert len(report.lag_assessments) == 2
    assert len(report.split_brain_assessments) == 2
    assert len(report.failover_plans) == 2


def test_report_deduplicates_recommendations():
    """Report should not have duplicate recommendations."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2)
    group = _make_group(nodes=nodes)
    analyzer = DataReplicationAnalyzer(g)

    report = analyzer.generate_report([group])
    assert len(report.recommendations) == len(set(report.recommendations))


def test_report_risk_level_aggregation():
    """Report risk level should be the worst across all assessments."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 50000.0])
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.ASYNCHRONOUS,
    )
    analyzer = DataReplicationAnalyzer(g)

    report = analyzer.generate_report([group])
    assert report.risk_level == RiskLevel.CRITICAL


def test_report_cross_region_profiles():
    """Report should include cross-region profiles when applicable."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(
        2, regions=["us-east-1", "eu-west-1"],
    )
    group = _make_group(nodes=nodes, cross_region=True)
    analyzer = DataReplicationAnalyzer(g)

    report = analyzer.generate_report([group])
    assert len(report.cross_region_profiles) > 0


# ---------------------------------------------------------------------------
# Test: Utility / Edge Cases
# ---------------------------------------------------------------------------


def test_risk_from_score_boundaries():
    """risk_from_score should handle boundary values correctly."""
    assert DataReplicationAnalyzer._risk_from_score(0.0) == RiskLevel.LOW
    assert DataReplicationAnalyzer._risk_from_score(0.29) == RiskLevel.LOW
    assert DataReplicationAnalyzer._risk_from_score(0.3) == RiskLevel.MEDIUM
    assert DataReplicationAnalyzer._risk_from_score(0.49) == RiskLevel.MEDIUM
    assert DataReplicationAnalyzer._risk_from_score(0.5) == RiskLevel.HIGH
    assert DataReplicationAnalyzer._risk_from_score(0.69) == RiskLevel.HIGH
    assert DataReplicationAnalyzer._risk_from_score(0.7) == RiskLevel.CRITICAL
    assert DataReplicationAnalyzer._risk_from_score(1.0) == RiskLevel.CRITICAL


def test_enum_values():
    """All enum values should be accessible and have correct types."""
    assert ReplicationStrategy.SYNCHRONOUS.value == "synchronous"
    assert ConsistencyModel.STRONG.value == "strong"
    assert ConflictResolution.CRDT.value == "crdt"
    assert SplitBrainResolution.FENCING.value == "fencing"
    assert ReplicaRole.PRIMARY.value == "primary"
    assert RiskLevel.CRITICAL.value == "critical"


def test_dataclass_defaults():
    """Data classes should have sensible defaults."""
    node = ReplicaNode(node_id="x", component_id="y")
    assert node.role == ReplicaRole.SECONDARY
    assert node.is_healthy is True
    assert node.replication_lag_ms == 0.0

    group = ReplicationGroup(group_id="g")
    assert group.strategy == ReplicationStrategy.ASYNCHRONOUS
    assert group.replication_factor == 3
    assert group.nodes == []

    step = FailoverStep(step_number=1, action="test", target_node_id="x")
    assert step.data_loss_possible is False

    plan = FailoverPlan(group_id="g")
    assert plan.rpo_seconds == 0.0

    cost = ReplicationCostProfile()
    assert cost.replication_factor == 1

    profile = CrossRegionProfile()
    assert profile.estimated_latency_ms == 0.0
    assert profile.regulatory_risk is False


def test_component_not_in_graph():
    """Replica referencing a missing component should not crash health scoring."""
    g = _graph()  # Empty graph
    nodes = [
        ReplicaNode(node_id="n0", component_id="missing", role=ReplicaRole.PRIMARY),
    ]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    # Should still produce a valid result without crashing
    assert result["group_health"] >= 0.0


def test_lag_analysis_single_node():
    """Single node group should work without errors."""
    g = _graph(_db_comp("db0"))
    nodes = [ReplicaNode(
        node_id="n0", component_id="db0", role=ReplicaRole.PRIMARY,
        replication_lag_ms=0.0,
    )]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.analyze_replication_lag(group)
    assert result.max_lag_ms == 0.0
    assert result.avg_lag_ms == 0.0


def test_medium_lag_risk_levels():
    """Medium lag values should map to MEDIUM risk appropriately."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))

    # Async: 1000-10000ms = MEDIUM
    nodes = _make_nodes(2, lags=[0.0, 5000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.ASYNCHRONOUS,
    )
    result = analyzer.analyze_replication_lag(group)
    assert result.risk_level == RiskLevel.MEDIUM

    # Semi-sync: 200-1000ms = MEDIUM
    nodes_semi = _make_nodes(2, lags=[0.0, 500.0])
    group_semi = _make_group(
        nodes=nodes_semi,
        strategy=ReplicationStrategy.SEMI_SYNCHRONOUS,
    )
    result_semi = analyzer.analyze_replication_lag(group_semi)
    assert result_semi.risk_level == RiskLevel.MEDIUM

    # Sync: 1-10ms = MEDIUM
    nodes_sync = _make_nodes(2, lags=[0.0, 5.0])
    group_sync = _make_group(
        nodes=nodes_sync,
        strategy=ReplicationStrategy.SYNCHRONOUS,
    )
    result_sync = analyzer.analyze_replication_lag(group_sync)
    assert result_sync.risk_level == RiskLevel.MEDIUM


def test_high_lag_semi_sync():
    """Semi-sync CRITICAL threshold at > 5000ms."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 6000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.SEMI_SYNCHRONOUS,
    )
    result = analyzer.analyze_replication_lag(group)
    assert result.risk_level == RiskLevel.CRITICAL


def test_async_high_lag():
    """Async 10000-30000ms should be HIGH risk."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 15000.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.ASYNCHRONOUS,
    )
    result = analyzer.analyze_replication_lag(group)
    assert result.risk_level == RiskLevel.HIGH


def test_sync_critical_lag():
    """Sync > 50ms should be CRITICAL."""
    g = _graph(_db_comp("db0"), _db_comp("db1"))
    nodes = _make_nodes(2, lags=[0.0, 60.0])
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.SYNCHRONOUS,
    )
    result = analyzer.analyze_replication_lag(group)
    assert result.risk_level == RiskLevel.CRITICAL


def test_split_brain_high_risk_recommendation():
    """High risk score should recommend switching replication strategy."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"), _db_comp("db3"))
    nodes = _make_nodes(
        4,
        regions=["us-east-1", "eu-west-1", "ap-northeast-1", "us-west-2"],
        healthy=[True, False, False, False],
    )
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        nodes=nodes,
        strategy=ReplicationStrategy.ASYNCHRONOUS,
        conflict=ConflictResolution.LAST_WRITE_WINS,
        split_brain=SplitBrainResolution.MANUAL,
    )

    result = analyzer.assess_split_brain_risk(group)
    has_switch_rec = any("switching" in r.lower() or "quorum" in r.lower()
                        for r in result.recommendations)
    assert has_switch_rec


def test_overloaded_component_health():
    """Overloaded component should reduce node health."""
    comp = Component(
        id="db1", name="db1", type=ComponentType.DATABASE,
        health=HealthStatus.OVERLOADED,
    )
    g = _graph(_db_comp("db0"), comp)
    nodes = _make_nodes(2)
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    assert result["node_scores"]["n1"] < 100.0


def test_node_health_moderate_lag_levels():
    """Moderate lag levels should produce proportional health penalties."""
    g = _graph(_db_comp("db0"), _db_comp("db1"), _db_comp("db2"), _db_comp("db3"))
    nodes = [
        ReplicaNode(node_id="n0", component_id="db0", role=ReplicaRole.PRIMARY,
                    replication_lag_ms=0.0),
        ReplicaNode(node_id="n1", component_id="db1", role=ReplicaRole.SECONDARY,
                    replication_lag_ms=500.0),  # > 100 => -5
        ReplicaNode(node_id="n2", component_id="db2", role=ReplicaRole.SECONDARY,
                    replication_lag_ms=3000.0),  # > 1000 => -10
        ReplicaNode(node_id="n3", component_id="db3", role=ReplicaRole.SECONDARY,
                    replication_lag_ms=7000.0),  # > 5000 => -20
    ]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    assert result["node_scores"]["n0"] > result["node_scores"]["n1"]
    assert result["node_scores"]["n1"] > result["node_scores"]["n2"]
    assert result["node_scores"]["n2"] > result["node_scores"]["n3"]


def test_high_utilization_health_tiers():
    """Different utilization levels should produce different health penalties."""
    comp_70 = Component(
        id="db0", name="db0", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(cpu_percent=75.0),
    )
    comp_80 = Component(
        id="db1", name="db1", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(cpu_percent=85.0),
    )
    comp_90 = Component(
        id="db2", name="db2", type=ComponentType.DATABASE,
        metrics=ResourceMetrics(cpu_percent=95.0),
    )
    g = _graph(comp_70, comp_80, comp_90)
    nodes = [
        ReplicaNode(node_id="n0", component_id="db0", role=ReplicaRole.PRIMARY),
        ReplicaNode(node_id="n1", component_id="db1", role=ReplicaRole.SECONDARY),
        ReplicaNode(node_id="n2", component_id="db2", role=ReplicaRole.SECONDARY),
    ]
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(nodes=nodes)

    result = analyzer.score_replica_health(group)
    assert result["node_scores"]["n0"] > result["node_scores"]["n1"]
    assert result["node_scores"]["n1"] > result["node_scores"]["n2"]


def test_monotonic_reads_consistency():
    """Monotonic reads consistency should have moderate compatibility."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        consistency=ConsistencyModel.MONOTONIC_READS,
        conflict=ConflictResolution.LAST_WRITE_WINS,
    )

    result = analyzer.analyze_conflict_resolution(group)
    assert result["consistency_compatibility"] == 0.6


def test_eventual_lww_low_compatibility():
    """Eventual + LWW should have low compatibility score."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        consistency=ConsistencyModel.EVENTUAL,
        conflict=ConflictResolution.LAST_WRITE_WINS,
    )

    result = analyzer.analyze_conflict_resolution(group)
    assert result["consistency_compatibility"] == 0.3


def test_causal_lww_moderate_compatibility():
    """Causal + LWW should have moderate compatibility."""
    g = _graph(_db_comp())
    analyzer = DataReplicationAnalyzer(g)
    group = _make_group(
        consistency=ConsistencyModel.CAUSAL,
        conflict=ConflictResolution.LAST_WRITE_WINS,
    )

    result = analyzer.analyze_conflict_resolution(group)
    assert result["consistency_compatibility"] == 0.5
