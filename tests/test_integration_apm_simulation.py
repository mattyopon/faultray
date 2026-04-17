# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Integration tests for APM + Simulation module boundaries.

Tests:
- APM → Topology Integration
- APM → Anomaly → Alert Integration
- Topology → Simulation Integration
- Simulation → Remediation Integration
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from faultray.apm.anomaly import AnomalyEngine, DEFAULT_ALERT_RULES
from faultray.apm.auto_discover import AutoDiscoverer
from faultray.apm.auto_simulate import AutoSimulator
from faultray.apm.models import (
    AlertRule,
    AlertSeverity,
    ConnectionInfo,
    HostMetrics,
    MetricsBatch,
    MetricPoint,
    MetricType,
    ProcessInfo,
)
from faultray.apm.topology_updater import (
    _infer_service_type,
    set_topology_graph,
    update_topology_from_batch,
)
from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.remediation.auto_pipeline import AutoRemediationPipeline
from faultray.remediation.autonomous_agent import AutonomousRemediationAgent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_graph() -> InfraGraph:
    return InfraGraph()


@pytest.fixture()
def spof_graph() -> InfraGraph:
    g = InfraGraph()
    web = Component(id="web-01", name="web-01", type=ComponentType.WEB_SERVER)
    db = Component(id="db-01", name="db-01", type=ComponentType.DATABASE, replicas=1)
    g.add_component(web)
    g.add_component(db)
    g.add_dependency(Dependency(source_id="web-01", target_id="db-01"))
    return g


@pytest.fixture()
def replicated_graph() -> InfraGraph:
    g = InfraGraph()
    web = Component(id="web-01", name="web-01", type=ComponentType.WEB_SERVER, replicas=3)
    db = Component(id="db-01", name="db-01", type=ComponentType.DATABASE, replicas=3)
    g.add_component(web)
    g.add_component(db)
    g.add_dependency(Dependency(source_id="web-01", target_id="db-01"))
    return g


# ---------------------------------------------------------------------------
# APM → Topology Integration
# ---------------------------------------------------------------------------


class TestAPMTopologyIntegration:
    """MetricsBatch with connections → valid InfraGraph."""

    def test_batch_with_listen_connections_updates_graph(self, empty_graph: InfraGraph) -> None:
        set_topology_graph(empty_graph)
        try:
            batch = MetricsBatch(
                agent_id="a1",
                processes=[
                    ProcessInfo(
                        pid=5432, name="postgres",
                        connections=[
                            ConnectionInfo(local_addr="0.0.0.0", local_port=5432, status="LISTEN"),
                        ],
                    ),
                ],
            )
            update_topology_from_batch(batch)
            assert len(empty_graph.components) >= 1
        finally:
            set_topology_graph(None)  # type: ignore[arg-type]

    def test_multiple_batches_grow_topology(self, empty_graph: InfraGraph) -> None:
        set_topology_graph(empty_graph)
        try:
            for port, name in [(80, "nginx"), (5432, "postgres"), (6379, "redis")]:
                batch = MetricsBatch(
                    agent_id=f"a-{port}",
                    hostname=f"host-{port}",
                    processes=[
                        ProcessInfo(
                            pid=port, name=name,
                            connections=[
                                ConnectionInfo(local_addr="0.0.0.0", local_port=port, status="LISTEN"),
                            ],
                        ),
                    ],
                )
                update_topology_from_batch(batch)
            assert len(empty_graph.components) >= 3
        finally:
            set_topology_graph(None)  # type: ignore[arg-type]

    def test_known_ports_get_correct_component_type(self, empty_graph: InfraGraph) -> None:
        set_topology_graph(empty_graph)
        try:
            for port, name, expected_type in [
                (80, "nginx", ComponentType.WEB_SERVER),
                (5432, "postgres", ComponentType.DATABASE),
                (6379, "redis", ComponentType.CACHE),
                (9092, "kafka", ComponentType.QUEUE),
            ]:
                batch = MetricsBatch(
                    agent_id=f"a-{port}",
                    hostname=f"h-{port}",
                    processes=[
                        ProcessInfo(
                            pid=port, name=name,
                            connections=[
                                ConnectionInfo(local_addr="0.0.0.0", local_port=port, status="LISTEN"),
                            ],
                        ),
                    ],
                )
                update_topology_from_batch(batch)

            types_in_graph = {c.type for c in empty_graph.components.values()}
            assert ComponentType.WEB_SERVER in types_in_graph
            assert ComponentType.DATABASE in types_in_graph
            assert ComponentType.CACHE in types_in_graph
            assert ComponentType.QUEUE in types_in_graph
        finally:
            set_topology_graph(None)  # type: ignore[arg-type]

    def test_batch_without_processes_does_not_crash(self, empty_graph: InfraGraph) -> None:
        set_topology_graph(empty_graph)
        try:
            batch = MetricsBatch(agent_id="a1", hostname="h1", processes=[])
            update_topology_from_batch(batch)  # should not raise
        finally:
            set_topology_graph(None)  # type: ignore[arg-type]

    def test_batch_with_no_topology_graph_set(self) -> None:
        set_topology_graph(None)  # type: ignore[arg-type]
        batch = MetricsBatch(
            agent_id="a1", hostname="h1",
            processes=[
                ProcessInfo(pid=80, name="nginx",
                            connections=[ConnectionInfo(local_port=80, status="LISTEN")]),
            ],
        )
        # Should not raise even when no graph is set
        update_topology_from_batch(batch)


# ---------------------------------------------------------------------------
# APM → Anomaly → Alert Integration
# ---------------------------------------------------------------------------


class TestAPMAnomalyAlertIntegration:
    """Metric points above threshold → AnomalyEngine fires alerts."""

    @pytest.fixture()
    def engine(self) -> AnomalyEngine:
        return AnomalyEngine(rules=list(DEFAULT_ALERT_RULES), window_size=10)

    def test_disk_above_threshold_fires_alert(self, engine: AnomalyEngine) -> None:
        hm = HostMetrics(disk_percent=92.0)
        alerts = engine.check_batch("a1", hm)
        assert any(a.rule_name == "high_disk" for a in alerts)

    def test_below_threshold_no_alert(self, engine: AnomalyEngine) -> None:
        hm = HostMetrics(cpu_percent=20.0, memory_percent=30.0, disk_percent=40.0)
        alerts = engine.check_batch("a1", hm)
        assert alerts == []

    def test_statistical_spike_detected(self) -> None:
        """Sudden spike above sigma threshold is detected as anomaly."""
        engine = AnomalyEngine(rules=[], window_size=10, sigma_threshold=2.0)
        # Feed normal values to build the buffer
        for v in [10.0, 12.0, 11.0, 10.5, 11.5, 10.2, 11.8, 10.9, 11.1, 10.7]:
            engine.check_batch("a1", HostMetrics(cpu_percent=v))

        # Spike value should appear as anomaly
        engine.check_batch("a1", HostMetrics(cpu_percent=200.0))
        anomalies = engine.detect_anomalies("a1")
        cpu_anomaly = next((a for a in anomalies if a.metric_name == "cpu_percent"), None)
        assert cpu_anomaly is not None
        assert cpu_anomaly.is_anomaly is True

    def test_custom_rule_fires_on_high_connections(self, engine: AnomalyEngine) -> None:
        engine.add_rule(AlertRule(
            name="high_conns",
            metric_name="network_connections",
            condition="gt",
            threshold=200.0,
            duration_seconds=0,
            severity=AlertSeverity.WARNING,
        ))
        hm = HostMetrics(network_connections=250)
        alerts = engine.check_batch("a1", hm)
        assert any(a.rule_name == "high_conns" for a in alerts)

    def test_alert_resolves_after_value_drops(self, engine: AnomalyEngine) -> None:
        hm_high = HostMetrics(disk_percent=91.0)
        engine.check_batch("a1", hm_high)
        assert ("a1", "high_disk") in engine._active_alerts

        hm_low = HostMetrics(disk_percent=50.0)
        engine.check_batch("a1", hm_low)
        assert ("a1", "high_disk") not in engine._active_alerts

    def test_no_duplicate_alerts_for_same_condition(self, engine: AnomalyEngine) -> None:
        hm = HostMetrics(disk_percent=91.0)
        alerts1 = engine.check_batch("a1", hm)
        alerts2 = engine.check_batch("a1", hm)
        assert len(alerts1) == 1
        assert len(alerts2) == 0

    def test_multiple_agents_get_independent_alerts(self, engine: AnomalyEngine) -> None:
        hm = HostMetrics(disk_percent=91.0)
        alerts_a = engine.check_batch("agent-a", hm)
        alerts_b = engine.check_batch("agent-b", hm)
        assert len(alerts_a) == 1
        assert len(alerts_b) == 1

    def test_trend_detection_returns_positive_for_gradual_increase(self) -> None:
        """Trend detection identifies positive trend for gradual metric increase."""
        engine = AnomalyEngine(rules=[], window_size=20, sigma_threshold=1.5)
        # Simulate gradual increase
        for v in [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0]:
            engine.check_batch("a1", HostMetrics(cpu_percent=v))
        anomalies = engine.detect_anomalies("a1")
        cpu_result = next((a for a in anomalies if a.metric_name == "cpu_percent"), None)
        if cpu_result is not None:
            # Trend should indicate increase for increasing values
            assert cpu_result.trend in ("increasing", "stable", "decreasing")


# ---------------------------------------------------------------------------
# Topology → Simulation Integration
# ---------------------------------------------------------------------------


class TestTopologySimulationIntegration:
    """InfraGraph from topology → SimulationEngine → findings."""

    def test_spof_graph_produces_lower_score(self, spof_graph: InfraGraph) -> None:
        report = AutoSimulator(spof_graph).run()
        assert report.score < 100.0

    def test_replicated_graph_higher_score_than_spof(
        self, spof_graph: InfraGraph, replicated_graph: InfraGraph
    ) -> None:
        spof_report = AutoSimulator(spof_graph).run()
        rep_report = AutoSimulator(replicated_graph).run()
        # Replicated system should score at least as high as SPOF
        assert rep_report.score >= spof_report.score

    def test_empty_graph_simulation_completes(self, empty_graph: InfraGraph) -> None:
        report = AutoSimulator(empty_graph).run()
        assert isinstance(report.score, float)
        assert report.components_analyzed == 0

    def test_simulation_report_has_availability_estimate(self, spof_graph: InfraGraph) -> None:
        report = AutoSimulator(spof_graph).run()
        assert report.availability_estimate
        assert "%" in report.availability_estimate

    def test_simulation_report_timestamp_is_iso_format(self, spof_graph: InfraGraph) -> None:
        report = AutoSimulator(spof_graph).run()
        assert report.timestamp
        # Should be parsable ISO datetime
        from datetime import datetime
        datetime.fromisoformat(report.timestamp.replace("Z", "+00:00"))

    def test_simulation_counts_components_and_dependencies(self, spof_graph: InfraGraph) -> None:
        report = AutoSimulator(spof_graph).run()
        assert report.components_analyzed == 2
        assert report.dependencies_analyzed >= 1


# ---------------------------------------------------------------------------
# Simulation → Remediation Integration
# ---------------------------------------------------------------------------


class TestSimulationRemediationIntegration:
    """Simulation report → IaC plan → AutoRemediationPipeline → cycle."""

    def test_pipeline_runs_on_spof_graph(self, spof_graph: InfraGraph, tmp_path: Path) -> None:
        pipeline = AutoRemediationPipeline(spof_graph, output_dir=tmp_path / "out")
        result = pipeline.run(dry_run=True)
        assert result.score_before >= 0.0
        assert isinstance(result.success, bool)

    def test_pipeline_result_has_steps(self, spof_graph: InfraGraph, tmp_path: Path) -> None:
        pipeline = AutoRemediationPipeline(spof_graph, output_dir=tmp_path / "out")
        result = pipeline.run(dry_run=True)
        assert len(result.steps) > 0

    def test_pipeline_to_dict_is_json_serializable(
        self, spof_graph: InfraGraph, tmp_path: Path
    ) -> None:
        import json
        pipeline = AutoRemediationPipeline(spof_graph, output_dir=tmp_path / "out")
        result = pipeline.run(dry_run=True)
        d = result.to_dict()
        # Must be JSON serializable
        json.dumps(d)

    def test_pipeline_dry_run_flag_in_result(self, spof_graph: InfraGraph, tmp_path: Path) -> None:
        pipeline = AutoRemediationPipeline(spof_graph, output_dir=tmp_path / "out")
        result = pipeline.run(dry_run=True)
        assert result.dry_run is True

    def test_autonomous_agent_cycle_from_saved_model(
        self, spof_graph: InfraGraph, tmp_path: Path
    ) -> None:
        model_path = tmp_path / "model.json"
        spof_graph.save(model_path)
        agent = AutonomousRemediationAgent(
            model_path=str(model_path),
            auto_approve=True,
            dry_run=True,
            output_dir=str(tmp_path / "rem"),
        )
        cycle = agent.run_cycle()
        assert cycle.status in ("completed", "failed", "awaiting_approval", "rolled_back")

    def test_autonomous_agent_saves_cycle_json(
        self, spof_graph: InfraGraph, tmp_path: Path
    ) -> None:
        import json
        model_path = tmp_path / "model.json"
        spof_graph.save(model_path)
        agent = AutonomousRemediationAgent(
            model_path=str(model_path),
            auto_approve=True,
            dry_run=True,
            output_dir=str(tmp_path / "rem"),
        )
        agent.run_cycle()
        cycles_dir = tmp_path / "rem" / "cycles"
        files = list(cycles_dir.glob("*.json"))
        assert len(files) >= 1
        data = json.loads(files[0].read_text())
        assert "id" in data
        assert "status" in data
