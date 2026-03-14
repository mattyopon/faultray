"""Tests for the Multi-Region DR Engine."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.dr_engine import DREngine, DRScenarioResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_region_graph() -> InfraGraph:
    """Graph with components spread across 2 regions and 3 AZs."""
    graph = InfraGraph()

    # Primary region: us-east-1, AZs: us-east-1a, us-east-1b
    graph.add_component(Component(
        id="lb-primary",
        name="Load Balancer (Primary)",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        region=RegionConfig(
            region="us-east-1",
            availability_zone="us-east-1a",
            is_primary=True,
            dr_target_region="us-west-2",
            rpo_seconds=60,
            rto_seconds=300,
        ),
    ))
    graph.add_component(Component(
        id="app-primary",
        name="App Server (Primary)",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=3,
        region=RegionConfig(
            region="us-east-1",
            availability_zone="us-east-1b",
            is_primary=True,
            rpo_seconds=30,
            rto_seconds=120,
        ),
    ))
    graph.add_component(Component(
        id="db-primary",
        name="PostgreSQL (Primary)",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=15),
        region=RegionConfig(
            region="us-east-1",
            availability_zone="us-east-1a",
            is_primary=True,
            dr_target_region="us-west-2",
            rpo_seconds=10,
            rto_seconds=60,
        ),
    ))

    # DR region: us-west-2, AZ: us-west-2a
    graph.add_component(Component(
        id="lb-dr",
        name="Load Balancer (DR)",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        region=RegionConfig(
            region="us-west-2",
            availability_zone="us-west-2a",
            is_primary=False,
        ),
    ))
    graph.add_component(Component(
        id="app-dr",
        name="App Server (DR)",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=2,
        region=RegionConfig(
            region="us-west-2",
            availability_zone="us-west-2a",
            is_primary=False,
        ),
    ))
    graph.add_component(Component(
        id="db-dr",
        name="PostgreSQL (DR)",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=1,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=30),
        region=RegionConfig(
            region="us-west-2",
            availability_zone="us-west-2a",
            is_primary=False,
        ),
    ))

    # Dependencies
    graph.add_dependency(Dependency(source_id="lb-primary", target_id="app-primary", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app-primary", target_id="db-primary", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="lb-dr", target_id="app-dr", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app-dr", target_id="db-dr", dependency_type="requires"))
    # Cross-region replication
    graph.add_dependency(Dependency(source_id="db-primary", target_id="db-dr", dependency_type="async"))

    return graph


@pytest.fixture
def single_region_graph() -> InfraGraph:
    """Graph with all components in a single region."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=2,
        region=RegionConfig(region="us-east-1", availability_zone="us-east-1a"),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=1,
        region=RegionConfig(region="us-east-1", availability_zone="us-east-1a"),
    ))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    return graph


# ---------------------------------------------------------------------------
# DRScenarioResult dataclass
# ---------------------------------------------------------------------------


class TestDRScenarioResult:
    def test_default_values(self):
        result = DRScenarioResult(scenario="az_failure")
        assert result.scenario == "az_failure"
        assert result.affected_components == []
        assert result.surviving_components == []
        assert result.rpo_met is True
        assert result.rto_met is True
        assert result.availability_during_dr == 100.0

    def test_custom_values(self):
        result = DRScenarioResult(
            scenario="region_failure",
            affected_components=["a", "b"],
            surviving_components=["c"],
            rpo_met=False,
            rto_met=True,
            estimated_data_loss_seconds=120.0,
            estimated_recovery_seconds=300.0,
            availability_during_dr=33.33,
        )
        assert len(result.affected_components) == 2
        assert result.rpo_met is False
        assert result.estimated_data_loss_seconds == 120.0


# ---------------------------------------------------------------------------
# AZ Failure
# ---------------------------------------------------------------------------


class TestAZFailure:
    def test_az_failure_splits_components(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_az_failure("us-east-1a")
        # lb-primary and db-primary are in us-east-1a
        assert "lb-primary" in result.affected_components
        assert "db-primary" in result.affected_components
        # app-primary is in us-east-1b, should survive
        assert "app-primary" in result.surviving_components

    def test_az_failure_availability(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_az_failure("us-east-1a")
        # 2 affected out of 6 total = 66.67% surviving
        assert result.availability_during_dr < 100.0
        assert result.availability_during_dr > 0.0

    def test_az_failure_unknown_az(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_az_failure("eu-west-1a")
        # No components in this AZ
        assert len(result.affected_components) == 0
        assert result.availability_during_dr == 100.0

    def test_az_failure_recovery_with_failover(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_az_failure("us-east-1a")
        # db-primary has failover with 15s promotion time
        assert result.estimated_recovery_seconds > 0


# ---------------------------------------------------------------------------
# Region Failure
# ---------------------------------------------------------------------------


class TestRegionFailure:
    def test_region_failure_affects_all_in_region(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_region_failure("us-east-1")
        # All 3 primary components should be affected
        assert "lb-primary" in result.affected_components
        assert "app-primary" in result.affected_components
        assert "db-primary" in result.affected_components
        # DR components should survive
        assert "lb-dr" in result.surviving_components
        assert "app-dr" in result.surviving_components
        assert "db-dr" in result.surviving_components

    def test_region_failure_availability(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_region_failure("us-east-1")
        # 3 affected, 3 surviving = 50%
        assert result.availability_during_dr == 50.0

    def test_single_region_full_outage(self, single_region_graph):
        engine = DREngine(single_region_graph)
        result = engine.simulate_region_failure("us-east-1")
        assert len(result.affected_components) == 2
        assert len(result.surviving_components) == 0
        assert result.availability_during_dr == 0.0


# ---------------------------------------------------------------------------
# Network Partition
# ---------------------------------------------------------------------------


class TestNetworkPartition:
    def test_partition_breaks_cross_region_deps(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_network_partition("us-east-1", "us-west-2")
        # db-primary -> db-dr is cross-region async dependency
        # db-primary should be affected (source of cross-region dep)
        assert "db-primary" in result.affected_components

    def test_partition_no_overlap_regions(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_network_partition("eu-west-1", "ap-southeast-1")
        # No components in these regions, no cross-region deps
        assert len(result.affected_components) == 0
        assert result.availability_during_dr == 100.0


# ---------------------------------------------------------------------------
# simulate_all
# ---------------------------------------------------------------------------


class TestSimulateAll:
    def test_simulate_all_generates_scenarios(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        results = engine.simulate_all()
        # Should have: 3 AZ failures + 2 region failures + 1 network partition = 6
        assert len(results) >= 5  # at least AZ + region scenarios

    def test_simulate_all_scenario_types(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        results = engine.simulate_all()
        scenarios = {r.scenario for r in results}
        assert "az_failure" in scenarios
        assert "region_failure" in scenarios
        assert "network_partition" in scenarios

    def test_simulate_all_empty_graph(self):
        graph = InfraGraph()
        engine = DREngine(graph)
        results = engine.simulate_all()
        assert len(results) == 0

    def test_simulate_all_no_regions(self):
        """Graph with components but no region config."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App",
            type=ComponentType.APP_SERVER,
        ))
        engine = DREngine(graph)
        results = engine.simulate_all()
        assert len(results) == 0  # no regions discovered


# ---------------------------------------------------------------------------
# RPO/RTO validation
# ---------------------------------------------------------------------------


class TestRPORTO:
    def test_rpo_violated_when_no_failover(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_az_failure("us-east-1a")
        # lb-primary is in us-east-1a, has RPO=60s but no failover
        # -> estimated data loss = 3600s (no failover backup) > RPO=60s
        # So RPO should be violated
        assert result.rpo_met is False

    def test_rpo_met_failover_only_components(self):
        """When only components with failover are affected, RPO should be met."""
        graph = InfraGraph()
        graph.add_component(Component(
            id="db",
            name="Database",
            type=ComponentType.DATABASE,
            replicas=2,
            failover=FailoverConfig(enabled=True, promotion_time_seconds=10),
            region=RegionConfig(
                region="us-east-1",
                availability_zone="us-east-1a",
                rpo_seconds=30,
                rto_seconds=60,
            ),
        ))
        engine = DREngine(graph)
        result = engine.simulate_az_failure("us-east-1a")
        # Failover enabled -> estimated data loss = 5s, RPO = 30s -> met
        assert result.rpo_met is True
        assert result.rto_met is True

    def test_rto_check(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_az_failure("us-east-1a")
        # db-primary has failover promotion=15s, lb-primary has no failover (300s default)
        assert result.estimated_recovery_seconds > 0

    def test_region_failure_rpo_rto(self, multi_region_graph):
        engine = DREngine(multi_region_graph)
        result = engine.simulate_region_failure("us-east-1")
        # All primary components affected - recovery depends on failover config
        assert result.estimated_recovery_seconds > 0
        assert result.estimated_data_loss_seconds >= 0
