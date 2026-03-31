"""Tests for FaultRay APM auto-discovery and auto-simulation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from faultray.apm.auto_discover import AutoDiscoverer
from faultray.apm.auto_simulate import AutoSimulator, AutoSimulationReport, _score_to_availability
from faultray.apm.models import AgentConfig
from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph_with_spof() -> InfraGraph:
    """Return a minimal InfraGraph that has one SPOF."""
    g = InfraGraph()
    web = Component(id="web-01", name="web-01", type=ComponentType.WEB_SERVER)
    db = Component(id="db-01", name="db-01", type=ComponentType.DATABASE, replicas=1)
    g.add_component(web)
    g.add_component(db)
    g.add_dependency(
        Dependency(source_id="web-01", target_id="db-01", dependency_type="requires")
    )
    return g


def _make_empty_graph() -> InfraGraph:
    return InfraGraph()


# ---------------------------------------------------------------------------
# AutoDiscoverer.discover_local
# ---------------------------------------------------------------------------


class TestDiscoverLocal:
    def test_returns_infra_graph(self) -> None:
        """discover_local() must return a valid InfraGraph even if no services run."""
        discoverer = AutoDiscoverer()
        graph = discoverer.discover_local()
        assert isinstance(graph, InfraGraph)

    def test_returns_empty_graph_on_error(self) -> None:
        """If scan_local raises, discover_local() returns an empty graph."""
        discoverer = AutoDiscoverer()
        with patch("faultray.discovery.scanner.scan_local", side_effect=OSError("boom")):
            graph = discoverer.discover_local()
        assert isinstance(graph, InfraGraph)
        assert len(graph.components) == 0

    def test_components_are_valid(self) -> None:
        """Components in the returned graph must have non-empty IDs."""
        discoverer = AutoDiscoverer()
        graph = discoverer.discover_local()
        for comp_id, comp in graph.components.items():
            assert comp_id  # non-empty
            assert isinstance(comp, Component)


# ---------------------------------------------------------------------------
# AutoDiscoverer.discover_cloud
# ---------------------------------------------------------------------------


class TestDiscoverCloud:
    def test_returns_none_when_no_provider(self) -> None:
        discoverer = AutoDiscoverer(cloud_provider=None)
        assert discoverer.discover_cloud() is None

    def test_returns_none_on_import_error(self) -> None:
        """If boto3 is not installed the method must return None (not raise)."""
        discoverer = AutoDiscoverer(cloud_provider="aws", cloud_config={"region": "us-east-1"})
        with patch(
            "faultray.apm.auto_discover.AutoDiscoverer._discover_aws",
            side_effect=ImportError("no boto3"),
        ):
            result = discoverer.discover_cloud()
        assert result is None

    def test_returns_none_on_unknown_provider(self) -> None:
        discoverer = AutoDiscoverer(cloud_provider="unknown-cloud")
        result = discoverer.discover_cloud()
        assert result is None

    def test_returns_none_on_exception(self) -> None:
        """Any non-import exception from a scanner must be caught."""
        discoverer = AutoDiscoverer(cloud_provider="gcp", cloud_config={"project_id": "x"})
        with patch(
            "faultray.apm.auto_discover.AutoDiscoverer._discover_gcp",
            side_effect=RuntimeError("credentials missing"),
        ):
            result = discoverer.discover_cloud()
        assert result is None


# ---------------------------------------------------------------------------
# AutoDiscoverer.merge_graphs
# ---------------------------------------------------------------------------


class TestMergeGraphs:
    def test_merge_empty_graphs(self) -> None:
        discoverer = AutoDiscoverer()
        merged = discoverer.merge_graphs(InfraGraph(), InfraGraph())
        assert len(merged.components) == 0

    def test_merge_non_overlapping(self) -> None:
        local = InfraGraph()
        local.add_component(Component(id="web-01", name="web", type=ComponentType.WEB_SERVER))

        cloud = InfraGraph()
        cloud.add_component(Component(id="db-cloud", name="rds", type=ComponentType.DATABASE))

        discoverer = AutoDiscoverer()
        merged = discoverer.merge_graphs(local, cloud)
        assert len(merged.components) == 2
        assert "web-01" in merged.components
        assert "db-cloud" in merged.components

    def test_merge_deduplicates_by_id(self) -> None:
        """Local component takes priority on ID collision."""
        local = InfraGraph()
        local.add_component(
            Component(id="shared-01", name="local-version", type=ComponentType.APP_SERVER)
        )

        cloud = InfraGraph()
        cloud.add_component(
            Component(id="shared-01", name="cloud-version", type=ComponentType.APP_SERVER)
        )

        discoverer = AutoDiscoverer()
        merged = discoverer.merge_graphs(local, cloud)
        assert len(merged.components) == 1
        assert merged.components["shared-01"].name == "local-version"

    def test_merge_preserves_dependencies(self) -> None:
        local = InfraGraph()
        local.add_component(Component(id="web", name="web", type=ComponentType.WEB_SERVER))
        local.add_component(Component(id="db", name="db", type=ComponentType.DATABASE))
        local.add_dependency(
            Dependency(source_id="web", target_id="db", dependency_type="requires")
        )

        cloud = InfraGraph()
        discoverer = AutoDiscoverer()
        merged = discoverer.merge_graphs(local, cloud)
        assert merged.get_dependency_edge("web", "db") is not None


# ---------------------------------------------------------------------------
# AutoDiscoverer.discover_all (integration-style, mocked scanners)
# ---------------------------------------------------------------------------


class TestDiscoverAll:
    def test_discover_all_local_only(self, tmp_path: Path) -> None:
        """discover_all() without cloud config returns a valid graph."""
        discoverer = AutoDiscoverer(
            cloud_provider=None,
            model_output_path=str(tmp_path / "auto-model.json"),
        )
        graph = discoverer.discover_all()
        assert isinstance(graph, InfraGraph)
        # Model file must be saved
        assert (tmp_path / "auto-model.json").exists()

    def test_discover_all_saves_model(self, tmp_path: Path) -> None:
        discoverer = AutoDiscoverer(
            cloud_provider=None,
            model_output_path=str(tmp_path / "model.json"),
        )
        discoverer.discover_all()
        model_file = tmp_path / "model.json"
        assert model_file.exists()
        import json
        data = json.loads(model_file.read_text())
        assert "components" in data
        assert "dependencies" in data


# ---------------------------------------------------------------------------
# AutoSimulator
# ---------------------------------------------------------------------------


class TestAutoSimulator:
    def test_run_returns_report(self) -> None:
        graph = _make_graph_with_spof()
        sim = AutoSimulator(graph)
        report = sim.run()
        assert isinstance(report, AutoSimulationReport)
        assert isinstance(report.score, float)
        assert 0.0 <= report.score <= 100.0

    def test_run_empty_graph(self) -> None:
        """Running on an empty graph must not raise."""
        sim = AutoSimulator(_make_empty_graph())
        report = sim.run()
        assert isinstance(report, AutoSimulationReport)
        assert report.availability_estimate == "unknown"

    def test_run_has_timestamp(self) -> None:
        sim = AutoSimulator(_make_graph_with_spof())
        report = sim.run()
        assert report.timestamp  # non-empty ISO string

    def test_run_counts_components(self) -> None:
        graph = _make_graph_with_spof()
        sim = AutoSimulator(graph)
        report = sim.run()
        assert report.components_analyzed == 2
        assert report.dependencies_analyzed == 1

    def test_run_on_engine_error_returns_zero_score(self) -> None:
        """If SimulationEngine raises, report must still be returned."""
        graph = _make_graph_with_spof()
        sim = AutoSimulator(graph)
        with patch(
            "faultray.simulator.engine.SimulationEngine.run_all_defaults",
            side_effect=RuntimeError("engine boom"),
        ):
            report = sim.run()
        assert isinstance(report, AutoSimulationReport)
        assert report.score == 0.0


# ---------------------------------------------------------------------------
# AutoSimulator.get_spofs
# ---------------------------------------------------------------------------


class TestGetSpofs:
    def test_detects_spof(self) -> None:
        graph = _make_graph_with_spof()
        sim = AutoSimulator(graph)
        spofs = sim.get_spofs()
        spof_ids = [s["id"] for s in spofs]
        assert "db-01" in spof_ids

    def test_no_spof_when_replicated(self) -> None:
        g = InfraGraph()
        web = Component(id="web", name="web", type=ComponentType.WEB_SERVER)
        db = Component(id="db", name="db", type=ComponentType.DATABASE, replicas=2)
        g.add_component(web)
        g.add_component(db)
        g.add_dependency(Dependency(source_id="web", target_id="db", dependency_type="requires"))
        sim = AutoSimulator(g)
        spofs = sim.get_spofs()
        spof_ids = [s["id"] for s in spofs]
        assert "db" not in spof_ids

    def test_no_spof_when_no_dependents(self) -> None:
        g = InfraGraph()
        g.add_component(Component(id="isolated", name="iso", type=ComponentType.APP_SERVER))
        sim = AutoSimulator(g)
        assert sim.get_spofs() == []


# ---------------------------------------------------------------------------
# get_availability_ceiling
# ---------------------------------------------------------------------------


class TestGetAvailabilityCeiling:
    def test_returns_dict_with_expected_keys(self) -> None:
        sim = AutoSimulator(_make_graph_with_spof())
        result = sim.get_availability_ceiling()
        assert "availability_string" in result
        assert "score" in result
        assert "limiting_components" in result

    def test_score_is_float(self) -> None:
        sim = AutoSimulator(_make_graph_with_spof())
        result = sim.get_availability_ceiling()
        assert isinstance(result["score"], float)


# ---------------------------------------------------------------------------
# _score_to_availability helper
# ---------------------------------------------------------------------------


class TestScoreToAvailability:
    @pytest.mark.parametrize(
        "score, expected",
        [
            (99.5, "99.999%"),
            (97.0, "99.99%"),
            (90.0, "99.9%"),
            (75.0, "99.5%"),
            (60.0, "99.0%"),
            (40.0, "95.0%"),
            (10.0, "< 95.0%"),
            (0.0,  "< 95.0%"),
        ],
    )
    def test_mapping(self, score: float, expected: str) -> None:
        assert _score_to_availability(score) == expected


# ---------------------------------------------------------------------------
# AgentConfig new fields
# ---------------------------------------------------------------------------


class TestAgentConfigNewFields:
    def test_defaults(self) -> None:
        cfg = AgentConfig()
        assert cfg.cloud_provider is None
        assert cfg.cloud_config == {}
        assert cfg.discovery_interval_seconds == 3600
        assert cfg.auto_simulate is True
        assert cfg.model_output_path == ""

    def test_cloud_provider_set(self) -> None:
        cfg = AgentConfig(cloud_provider="aws", cloud_config={"region": "us-east-1"})
        assert cfg.cloud_provider == "aws"
        assert cfg.cloud_config["region"] == "us-east-1"

    def test_custom_discovery_interval(self) -> None:
        cfg = AgentConfig(discovery_interval_seconds=300)
        assert cfg.discovery_interval_seconds == 300

    def test_disable_auto_simulate(self) -> None:
        cfg = AgentConfig(auto_simulate=False)
        assert cfg.auto_simulate is False
