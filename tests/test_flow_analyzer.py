"""Tests for FlowLogAnalyzer -- VPC Flow Log dependency discovery."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrasim.discovery.flow_analyzer import (
    CommunicationPattern,
    FlowAnalysisResult,
    FlowLogAnalyzer,
)
from infrasim.model.components import Component, ComponentType, Dependency
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(cid: str, ctype: ComponentType, host: str) -> Component:
    return Component(
        id=cid,
        name=cid.replace("_", " ").title(),
        type=ctype,
        host=host,
    )


def _make_graph(components: list[Component], deps: list[Dependency] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in deps or []:
        g.add_dependency(d)
    return g


SAMPLE_FLOW_LOG = textwrap.dedent("""\
    2 123456789012 eni-abc 10.0.1.10 10.0.2.20 49152 5432 6 10 5000 1620000000 1620000060 ACCEPT OK
    2 123456789012 eni-abc 10.0.1.10 10.0.2.20 49153 5432 6 5 2500 1620000060 1620000120 ACCEPT OK
    2 123456789012 eni-abc 10.0.1.10 10.0.3.30 49154 6379 6 3 1000 1620000000 1620000060 ACCEPT OK
    2 123456789012 eni-xyz 10.0.1.10 10.0.4.40 49155 443 6 20 10000 1620000000 1620000060 ACCEPT OK
    2 123456789012 eni-xyz 10.0.1.10 192.168.1.1 49156 8080 6 2 500 1620000000 1620000060 ACCEPT OK
    2 123456789012 eni-xyz 10.0.1.10 10.0.2.20 49157 5432 6 1 100 1620000000 1620000060 REJECT OK
""")


# ---------------------------------------------------------------------------
# Tests: File-based analysis
# ---------------------------------------------------------------------------


class TestAnalyzeFromFile:
    def test_parse_flow_log_file(self, tmp_path: Path):
        log_file = tmp_path / "flow.log"
        log_file.write_text(SAMPLE_FLOW_LOG)

        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.10")
        db = _make_component("db", ComponentType.DATABASE, "10.0.2.20")
        cache = _make_component("cache", ComponentType.CACHE, "10.0.3.30")
        ext = _make_component("ext_api", ComponentType.EXTERNAL_API, "10.0.4.40")

        graph = _make_graph([web, db, cache, ext])
        analyzer = FlowLogAnalyzer(graph)
        result = analyzer.analyze_from_file(log_file)

        assert isinstance(result, FlowAnalysisResult)
        # Should have patterns for accepted flows
        assert len(result.patterns) >= 3

    def test_discovers_database_dependency(self, tmp_path: Path):
        log_file = tmp_path / "flow.log"
        log_file.write_text(SAMPLE_FLOW_LOG)

        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.10")
        db = _make_component("db", ComponentType.DATABASE, "10.0.2.20")

        graph = _make_graph([web, db])
        analyzer = FlowLogAnalyzer(graph)
        result = analyzer.analyze_from_file(log_file)

        db_deps = [d for d in result.discovered_dependencies if d.target_id == "db"]
        assert len(db_deps) >= 1
        assert db_deps[0].source_id == "web"
        assert db_deps[0].dependency_type == "requires"
        assert db_deps[0].port == 5432

    def test_discovers_cache_dependency(self, tmp_path: Path):
        log_file = tmp_path / "flow.log"
        log_file.write_text(SAMPLE_FLOW_LOG)

        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.10")
        cache = _make_component("cache", ComponentType.CACHE, "10.0.3.30")

        graph = _make_graph([web, cache])
        analyzer = FlowLogAnalyzer(graph)
        result = analyzer.analyze_from_file(log_file)

        cache_deps = [d for d in result.discovered_dependencies if d.target_id == "cache"]
        assert len(cache_deps) >= 1
        assert cache_deps[0].dependency_type == "optional"
        assert cache_deps[0].port == 6379

    def test_unmapped_flows_tracked(self, tmp_path: Path):
        log_file = tmp_path / "flow.log"
        log_file.write_text(SAMPLE_FLOW_LOG)

        # Only register web -- 192.168.1.1 is not mapped
        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.10")

        graph = _make_graph([web])
        analyzer = FlowLogAnalyzer(graph)
        result = analyzer.analyze_from_file(log_file)

        # Flows to unregistered IPs should be in unmapped
        assert len(result.unmapped_flows) >= 1
        unmapped_dests = {f.dest_ip for f in result.unmapped_flows}
        # At least 10.0.2.20, 10.0.3.30, 10.0.4.40, or 192.168.1.1
        assert len(unmapped_dests) >= 1

    def test_rejected_flows_excluded(self, tmp_path: Path):
        log_file = tmp_path / "flow.log"
        log_file.write_text(SAMPLE_FLOW_LOG)

        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.10")
        db = _make_component("db", ComponentType.DATABASE, "10.0.2.20")

        graph = _make_graph([web, db])
        analyzer = FlowLogAnalyzer(graph)
        result = analyzer.analyze_from_file(log_file)

        # The REJECT line should not produce any patterns
        for p in result.patterns:
            if p.source_ip == "10.0.1.10" and p.dest_ip == "10.0.2.20" and p.dest_port == 5432:
                # Should aggregate bytes from accepted flows only (5000+2500=7500)
                assert p.bytes_transferred == 7500
                assert p.request_count == 2

    def test_header_line_skipped(self, tmp_path: Path):
        log = "version account-id interface-id srcaddr dstaddr srcport dstport protocol packets bytes start end action log-status\n"
        log += "2 123456789012 eni-a 10.0.1.1 10.0.2.2 49152 5432 6 1 100 1620000000 1620000060 ACCEPT OK\n"
        log_file = tmp_path / "flow_with_header.log"
        log_file.write_text(log)

        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.1")
        db = _make_component("db", ComponentType.DATABASE, "10.0.2.2")

        graph = _make_graph([web, db])
        analyzer = FlowLogAnalyzer(graph)
        result = analyzer.analyze_from_file(log_file)

        assert len(result.patterns) >= 1

    def test_bytes_aggregated(self, tmp_path: Path):
        log_file = tmp_path / "flow.log"
        log_file.write_text(SAMPLE_FLOW_LOG)

        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.10")
        db = _make_component("db", ComponentType.DATABASE, "10.0.2.20")

        graph = _make_graph([web, db])
        analyzer = FlowLogAnalyzer(graph)
        result = analyzer.analyze_from_file(log_file)

        db_pattern = [p for p in result.patterns if p.dest_port == 5432 and p.dest_ip == "10.0.2.20"]
        assert len(db_pattern) == 1
        assert db_pattern[0].bytes_transferred == 7500  # 5000 + 2500
        assert db_pattern[0].request_count == 2


# ---------------------------------------------------------------------------
# Tests: Port-to-dependency-type inference
# ---------------------------------------------------------------------------


class TestPortInference:
    @pytest.mark.parametrize(
        "port,expected_type",
        [
            (5432, "requires"),
            (3306, "requires"),
            (6379, "optional"),
            (11211, "optional"),
            (443, "requires"),
            (80, "requires"),
            (8080, "optional"),
            (9999, "optional"),
        ],
    )
    def test_infer_dep_type(self, port, expected_type):
        assert FlowLogAnalyzer._infer_dep_type(port) == expected_type


# ---------------------------------------------------------------------------
# Tests: merge_dependencies
# ---------------------------------------------------------------------------


class TestMergeDependencies:
    def test_merge_adds_new_dependencies(self, tmp_path: Path):
        log_file = tmp_path / "flow.log"
        log_file.write_text(SAMPLE_FLOW_LOG)

        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.10")
        db = _make_component("db", ComponentType.DATABASE, "10.0.2.20")
        cache = _make_component("cache", ComponentType.CACHE, "10.0.3.30")

        graph = _make_graph([web, db, cache])
        analyzer = FlowLogAnalyzer(graph)

        result = analyzer.analyze_from_file(log_file)
        count = analyzer.merge_dependencies(result)

        assert count >= 2  # web->db and web->cache
        edges = graph.all_dependency_edges()
        edge_pairs = {(e.source_id, e.target_id) for e in edges}
        assert ("web", "db") in edge_pairs
        assert ("web", "cache") in edge_pairs

    def test_merge_skips_existing_edges(self, tmp_path: Path):
        log_file = tmp_path / "flow.log"
        log_file.write_text(SAMPLE_FLOW_LOG)

        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.10")
        db = _make_component("db", ComponentType.DATABASE, "10.0.2.20")

        # Pre-add the edge
        existing = Dependency(source_id="web", target_id="db", dependency_type="requires")
        graph = _make_graph([web, db], deps=[existing])

        analyzer = FlowLogAnalyzer(graph)
        result = analyzer.analyze_from_file(log_file)
        count = analyzer.merge_dependencies(result)

        # web->db already exists, should not be duplicated
        edges = graph.all_dependency_edges()
        db_edges = [e for e in edges if e.source_id == "web" and e.target_id == "db"]
        assert len(db_edges) == 1
        # count should be 0 for that edge (already existed)
        assert count == 0


# ---------------------------------------------------------------------------
# Tests: CloudWatch Logs (mocked)
# ---------------------------------------------------------------------------


class TestVPCFlowLogsFromCloudWatch:
    def test_analyze_vpc_flow_logs_mocked(self):
        web = _make_component("web", ComponentType.WEB_SERVER, "10.0.1.10")
        db = _make_component("db", ComponentType.DATABASE, "10.0.2.20")
        graph = _make_graph([web, db])

        mock_logs = MagicMock()
        mock_logs.start_query.return_value = {"queryId": "test-query-123"}
        mock_logs.get_query_results.return_value = {
            "status": "Complete",
            "results": [
                [{"field": "@message", "value": "2 123456789012 eni-a 10.0.1.10 10.0.2.20 49152 5432 6 10 5000 1620000000 1620000060 ACCEPT OK"}],
                [{"field": "@message", "value": "2 123456789012 eni-a 10.0.1.10 10.0.2.20 49153 5432 6 5 2500 1620000060 1620000120 ACCEPT OK"}],
            ],
        }

        analyzer = FlowLogAnalyzer(graph)
        result = analyzer.analyze_vpc_flow_logs("test-log-group", hours=1, _logs_client=mock_logs)

        assert len(result.patterns) >= 1
        assert len(result.discovered_dependencies) >= 1
        assert result.discovered_dependencies[0].target_id == "db"
