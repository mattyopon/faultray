"""Tests for the enhanced FaultZero Python SDK."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from faultray.sdk import FaultZero


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def demo_fz():
    """Create a FaultZero instance from the built-in demo graph."""
    return FaultZero.demo()


@pytest.fixture
def yaml_path(tmp_path: Path) -> Path:
    """Write a minimal YAML infrastructure file and return its path."""
    content = """\
schema_version: "3.0"
components:
  - id: lb
    name: Load Balancer
    type: load_balancer
    replicas: 2
  - id: app
    name: App Server
    type: app_server
    replicas: 2
  - id: db
    name: Database
    type: database
    replicas: 1

dependencies:
  - source: lb
    target: app
    type: requires
  - source: app
    target: db
    type: requires
"""
    p = tmp_path / "test-infra.yaml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------

class TestFaultZeroConstruction:
    def test_from_demo(self):
        fz = FaultZero.demo()
        assert fz.component_count > 0
        assert fz.resilience_score >= 0

    def test_from_yaml(self, yaml_path: Path):
        fz = FaultZero(yaml_path)
        assert fz.component_count == 3

    def test_from_yaml_str(self, yaml_path: Path):
        fz = FaultZero(str(yaml_path))
        assert fz.component_count == 3

    def test_from_dict(self):
        data = {
            "components": [
                {"id": "a", "name": "A", "type": "app_server"},
                {"id": "b", "name": "B", "type": "database"},
            ],
            "dependencies": [
                {"source_id": "a", "target_id": "b", "dependency_type": "requires"},
            ],
        }
        fz = FaultZero.from_dict(data)
        assert fz.component_count == 2

    def test_from_graph(self):
        from faultray.model.demo import create_demo_graph

        graph = create_demo_graph()
        fz = FaultZero(graph=graph)
        assert fz.component_count == len(graph.components)

    def test_from_text(self):
        fz = FaultZero.from_text("2 web servers behind a load balancer with a database")
        assert fz.component_count > 0

    def test_no_args_raises(self):
        with pytest.raises(ValueError, match="requires either"):
            FaultZero()


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

class TestFaultZeroProperties:
    def test_resilience_score(self, demo_fz: FaultZero):
        score = demo_fz.resilience_score
        assert 0 <= score <= 100
        assert isinstance(score, float)

    def test_component_count(self, demo_fz: FaultZero):
        assert demo_fz.component_count == 9  # demo has 9 components

    def test_spof_count(self, demo_fz: FaultZero):
        assert demo_fz.spof_count >= 0

    def test_components_list(self, demo_fz: FaultZero):
        comps = demo_fz.components
        assert isinstance(comps, list)
        assert len(comps) == demo_fz.component_count

    def test_graph_property(self, demo_fz: FaultZero):
        from faultray.model.graph import InfraGraph

        assert isinstance(demo_fz.graph, InfraGraph)


# ---------------------------------------------------------------------------
# Analysis tests
# ---------------------------------------------------------------------------

class TestFaultZeroAnalysis:
    def test_simulate(self, demo_fz: FaultZero):
        report = demo_fz.simulate(include_feed=False)
        assert hasattr(report, "results")
        assert hasattr(report, "critical_findings")
        assert hasattr(report, "resilience_score")
        assert len(report.results) > 0

    def test_validate_sla(self, demo_fz: FaultZero):
        result = demo_fz.validate_sla(target_nines=3.0)
        assert hasattr(result, "achievable")
        assert hasattr(result, "calculated_availability")
        assert isinstance(result.achievable, bool)
        assert 0 <= result.calculated_availability <= 1.0

    def test_validate_sla_high_target(self, demo_fz: FaultZero):
        result = demo_fz.validate_sla(target_nines=5.0)
        assert hasattr(result, "achievable")

    def test_genome(self, demo_fz: FaultZero):
        genome = demo_fz.genome()
        assert hasattr(genome, "resilience_grade")
        assert hasattr(genome, "traits")
        assert hasattr(genome, "weakness_genes")
        assert genome.resilience_grade in ("A+", "A", "A-", "B+", "B", "B-",
                                            "C+", "C", "C-", "D+", "D", "D-", "F")

    def test_benchmark(self, demo_fz: FaultZero):
        result = demo_fz.benchmark(industry="saas")
        assert hasattr(result, "your_score")
        assert hasattr(result, "percentile")
        assert hasattr(result, "rank_description")
        assert 0 <= result.percentile <= 100

    def test_risk_heatmap(self, demo_fz: FaultZero):
        heatmap = demo_fz.risk_heatmap()
        assert hasattr(heatmap, "components")
        assert hasattr(heatmap, "hotspots")
        assert len(heatmap.components) == demo_fz.component_count


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------

class TestFaultZeroExports:
    def test_to_yaml(self, demo_fz: FaultZero):
        yaml_str = demo_fz.to_yaml()
        assert isinstance(yaml_str, str)
        assert "components" in yaml_str

    def test_to_json(self, demo_fz: FaultZero):
        json_str = demo_fz.to_json()
        data = json.loads(json_str)
        assert "components" in data
        assert "dependencies" in data

    def test_to_mermaid(self, demo_fz: FaultZero):
        mermaid = demo_fz.to_mermaid()
        assert isinstance(mermaid, str)
        assert "graph" in mermaid.lower() or "flowchart" in mermaid.lower() or "-->" in mermaid

    def test_to_terraform(self, demo_fz: FaultZero):
        tf_files = demo_fz.to_terraform()
        assert isinstance(tf_files, dict)
        # May be empty if no remediations needed, but must be a dict


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------

class TestFaultZeroUtilities:
    def test_find_spofs(self, demo_fz: FaultZero):
        spofs = demo_fz.find_spofs()
        assert isinstance(spofs, list)
        # Demo graph has single-replica components with required deps
        assert len(spofs) > 0

    def test_quick_wins(self, demo_fz: FaultZero):
        wins = demo_fz.quick_wins()
        assert isinstance(wins, list)

    def test_replay_all_incidents(self, demo_fz: FaultZero):
        results = demo_fz.replay_all_incidents()
        assert isinstance(results, list)
        # Should have at least some known incidents
        assert len(results) > 0
        for r in results:
            assert hasattr(r, "survived")
            assert hasattr(r, "impact_score")

    def test_chat(self, demo_fz: FaultZero):
        answer = demo_fz.chat("How resilient is the system?")
        assert isinstance(answer, str)
        assert len(answer) > 0


# ---------------------------------------------------------------------------
# Representation tests
# ---------------------------------------------------------------------------

class TestFaultZeroRepr:
    def test_repr(self, demo_fz: FaultZero):
        r = repr(demo_fz)
        assert "FaultZero" in r
        assert "components=" in r
        assert "score=" in r

    def test_str(self, demo_fz: FaultZero):
        s = str(demo_fz)
        assert "FaultZero" in s
        assert "Components:" in s
        assert "Resilience Score:" in s


# ---------------------------------------------------------------------------
# Import test (from faultray import FaultZero)
# ---------------------------------------------------------------------------

class TestFaultZeroImport:
    def test_import_from_package(self):
        from faultray import FaultZero as FZ

        assert FZ is FaultZero

    def test_in_all(self):
        import faultray

        assert "FaultZero" in faultray.__all__
