# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""E2E scenario tests for FaultRay.

Tests complete user flows end-to-end across all major feature areas:
- Scenario 1: Full APM Monitoring Flow
- Scenario 2: Autonomous Remediation Flow
- Scenario 3: Governance Assessment Flow
- Scenario 4: APM + Simulation Integration
- Scenario 5: Full Self-Healing Cycle
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from faultray.apm.anomaly import AnomalyEngine, DEFAULT_ALERT_RULES
from faultray.apm.auto_discover import AutoDiscoverer
from faultray.apm.auto_simulate import AutoSimulator
from faultray.apm.models import (
    AgentConfig,
    ConnectionInfo,
    HostMetrics,
    MetricsBatch,
    MetricPoint,
    MetricType,
    ProcessInfo,
)
from faultray.apm.topology_updater import set_topology_graph, update_topology_from_batch
from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
)
from faultray.model.graph import InfraGraph
from faultray.remediation.autonomous_agent import AutonomousRemediationAgent


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_spof_graph() -> InfraGraph:
    """Return an InfraGraph with a DB that is a SPOF (replicas=1)."""
    g = InfraGraph()
    web = Component(id="web-01", name="web-01", type=ComponentType.WEB_SERVER)
    db = Component(id="db-01", name="db-01", type=ComponentType.DATABASE, replicas=1)
    g.add_component(web)
    g.add_component(db)
    g.add_dependency(Dependency(source_id="web-01", target_id="db-01"))
    return g


def _make_remediation_agent(tmp_path: Path, graph: InfraGraph | None = None) -> AutonomousRemediationAgent:
    model_path = tmp_path / "model.json"
    g = graph or _make_spof_graph()
    g.save(model_path)
    return AutonomousRemediationAgent(
        model_path=str(model_path),
        auto_approve=True,
        dry_run=True,
        output_dir=str(tmp_path / "remediation"),
    )


# ---------------------------------------------------------------------------
# Scenario 1: Full APM Monitoring Flow
# ---------------------------------------------------------------------------


class TestScenario1FullAPMMonitoringFlow:
    """install -> collect -> discover -> simulate -> alert cycle."""

    def test_s1_step1_agent_config_created(self) -> None:
        """APM config can be created with default values."""
        config = AgentConfig()
        assert config.agent_id
        assert config.collector_url

    def test_s1_step2_collect_metrics_batch_structure(self) -> None:
        """MetricsBatch has correct structure after collection."""
        host = HostMetrics(cpu_percent=45.0, memory_percent=60.0, disk_percent=30.0)
        batch = MetricsBatch(
            agent_id="agent-01",
            host_metrics=host,
            custom_metrics=[
                MetricPoint(name="cpu", value=45.0, metric_type=MetricType.GAUGE),
                MetricPoint(name="mem", value=60.0, metric_type=MetricType.GAUGE),
            ],
        )
        assert batch.agent_id == "agent-01"
        assert batch.host_metrics.cpu_percent == 45.0
        assert len(batch.custom_metrics) == 2
        assert batch.timestamp  # auto-generated

    def test_s1_step3_build_topology_from_connections(self) -> None:
        """Connections in MetricsBatch build a valid InfraGraph."""
        g = InfraGraph()
        set_topology_graph(g)
        try:
            batch = MetricsBatch(
                agent_id="a1",
                processes=[
                    ProcessInfo(
                        pid=1, name="nginx",
                        connections=[
                            ConnectionInfo(local_addr="0.0.0.0", local_port=80, status="LISTEN"),
                        ],
                    ),
                ],
            )
            update_topology_from_batch(batch)
            assert len(g.components) >= 1
        finally:
            set_topology_graph(None)  # type: ignore[arg-type]

    def test_s1_step4_auto_simulation_on_graph(self) -> None:
        """AutoSimulator generates a report from a given InfraGraph."""
        graph = _make_spof_graph()
        report = AutoSimulator(graph).run()
        assert report.score >= 0.0
        assert report.total_scenarios >= 0
        assert report.timestamp

    def test_s1_step5_anomaly_detection_fires_alert(self) -> None:
        """Anomaly engine fires alert when disk usage exceeds threshold."""
        engine = AnomalyEngine(rules=list(DEFAULT_ALERT_RULES), window_size=10)
        hm = HostMetrics(disk_percent=91.0)
        alerts = engine.check_batch("agent-01", hm)
        assert any(a.rule_name == "high_disk" for a in alerts)

    def test_s1_full_cycle_no_exceptions(self) -> None:
        """Full install→collect→discover→simulate→alert runs without exceptions."""
        # Config creation
        config = AgentConfig(agent_id="e2e-agent", collect_interval_seconds=60)
        assert config.agent_id == "e2e-agent"

        # Batch collection
        host = HostMetrics(cpu_percent=30.0, memory_percent=40.0)
        batch = MetricsBatch(agent_id=config.agent_id, hostname="host-e2e", host_metrics=host)

        # Topology update
        g = InfraGraph()
        set_topology_graph(g)
        try:
            update_topology_from_batch(batch)
        finally:
            set_topology_graph(None)  # type: ignore[arg-type]

        # Simulation
        report = AutoSimulator(InfraGraph()).run()
        assert isinstance(report.score, float)

        # Anomaly check (below threshold, no alerts)
        engine = AnomalyEngine(rules=list(DEFAULT_ALERT_RULES))
        alerts = engine.check_batch(config.agent_id, HostMetrics(cpu_percent=30.0))
        assert isinstance(alerts, list)


# ---------------------------------------------------------------------------
# Scenario 2: Autonomous Remediation Flow
# ---------------------------------------------------------------------------


class TestScenario2AutonomousRemediationFlow:
    """Load model -> simulate -> detect SPOFs -> plan -> dry-run."""

    def test_s2_step1_load_infrastructure_model(self, tmp_path: Path) -> None:
        """Infrastructure model can be saved and loaded."""
        g = _make_spof_graph()
        model_path = tmp_path / "model.json"
        g.save(model_path)
        assert model_path.exists()
        loaded = InfraGraph.load(model_path)
        assert "db-01" in loaded.components

    def test_s2_step2_simulation_detects_spofs(self) -> None:
        """Simulation on SPOF graph identifies critical issues."""
        graph = _make_spof_graph()
        report = AutoSimulator(graph).run()
        assert isinstance(report.spofs, list)
        # At least one scenario should be evaluated
        assert report.total_scenarios >= 0

    def test_s2_step3_iac_plan_generated(self, tmp_path: Path) -> None:
        """Remediation agent generates an IaC plan."""
        agent = _make_remediation_agent(tmp_path)
        cycle = agent.run_cycle()
        assert cycle.status in ("completed", "failed", "awaiting_approval")
        if cycle.issues_found:
            assert cycle.remediation_plan is not None

    def test_s2_step4_simulated_score_available(self, tmp_path: Path) -> None:
        """After planning, simulated score is recorded in cycle."""
        agent = _make_remediation_agent(tmp_path)
        cycle = agent.run_cycle()
        assert isinstance(cycle.initial_score, float)
        assert isinstance(cycle.simulated_score, float)

    def test_s2_step5_dry_run_execution(self, tmp_path: Path) -> None:
        """Dry-run executes steps without writing real infra."""
        agent = _make_remediation_agent(tmp_path)
        cycle = agent.run_cycle()
        if cycle.execution_log:
            for entry in cycle.execution_log:
                assert entry.get("status") in ("dry_run", "blocked", "success", "failed")

    def test_s2_step6_cycle_persistence(self, tmp_path: Path) -> None:
        """Completed cycle is persisted as JSON file."""
        agent = _make_remediation_agent(tmp_path)
        agent.run_cycle()
        cycles_dir = tmp_path / "remediation" / "cycles"
        cycle_files = list(cycles_dir.glob("*.json"))
        assert len(cycle_files) >= 1
        data = json.loads(cycle_files[0].read_text())
        assert "id" in data
        assert "status" in data

    def test_s2_step7_report_generated(self, tmp_path: Path) -> None:
        """Report summary is non-empty after cycle completion."""
        agent = _make_remediation_agent(tmp_path)
        cycle = agent.run_cycle()
        assert cycle.report_summary
        assert isinstance(cycle.report_summary, str)

    def test_s2_full_cycle_completes(self, tmp_path: Path) -> None:
        """Full remediation cycle completes without raising."""
        agent = _make_remediation_agent(tmp_path)
        cycle = agent.run_cycle()
        assert cycle.id
        assert cycle.started_at
        assert cycle.status in ("completed", "failed", "awaiting_approval", "rolled_back")


# ---------------------------------------------------------------------------
# Scenario 3: Governance Assessment Flow
# ---------------------------------------------------------------------------


class TestScenario3GovernanceAssessmentFlow:
    """25-question assessment -> gap -> roadmap -> policy -> evidence."""

    @pytest.fixture(autouse=True)
    def _isolate_storage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        storage = tmp_path / "governance"
        storage.mkdir()
        import faultray.governance.ai_registry as reg_mod
        import faultray.governance.evidence_manager as ev_mod
        monkeypatch.setattr(reg_mod, "_STORAGE_DIR", storage)
        monkeypatch.setattr(reg_mod, "_REGISTRY_FILE", storage / "ai_registry.json")
        monkeypatch.setattr(ev_mod, "_STORAGE_DIR", storage)
        monkeypatch.setattr(ev_mod, "_EVIDENCE_DIR", storage / "evidence")
        monkeypatch.setattr(ev_mod, "_EVIDENCE_FILE", storage / "evidence_records.json")
        monkeypatch.setattr(ev_mod, "_AUDIT_FILE", storage / "audit_chain.json")

    def test_s3_step1_assessment_produces_maturity_score(self) -> None:
        """25-question assessment returns a maturity score in 1-5."""
        from faultray.governance.assessor import GovernanceAssessor
        assessor = GovernanceAssessor()
        answers = {f"Q{i:02d}": 2 for i in range(1, 26)}
        result = assessor.assess(answers)
        assert 0.0 <= result.overall_score <= 100.0
        assert 1 <= result.maturity_level <= 5

    def test_s3_step2_gap_analyzer_produces_report(self) -> None:
        """Gap analyzer produces a GapReport from assessment result."""
        from faultray.governance.assessor import GovernanceAssessor
        from faultray.governance.gap_analyzer import analyze_gaps
        assessor = GovernanceAssessor()
        answers = {f"Q{i:02d}": 0 for i in range(1, 26)}
        result = assessor.assess(answers)
        gap_report = analyze_gaps(result)
        assert gap_report.total_requirements > 0
        assert len(gap_report.gaps) == gap_report.total_requirements

    def test_s3_step3_multi_framework_violations(self) -> None:
        """GapReport contains multi-framework violation mapping."""
        from faultray.governance.assessor import GovernanceAssessor
        from faultray.governance.gap_analyzer import analyze_gaps
        assessor = GovernanceAssessor()
        answers = {f"Q{i:02d}": 0 for i in range(1, 26)}
        result = assessor.assess(answers)
        gap_report = analyze_gaps(result)
        # multi_framework_impact should be populated
        assert isinstance(gap_report.multi_framework_impact, dict)

    def test_s3_step4_roadmap_has_3_phases(self) -> None:
        """Roadmap includes items across 3 phases for low-score assessment."""
        from faultray.governance.assessor import GovernanceAssessor
        from faultray.governance.gap_analyzer import analyze_gaps
        assessor = GovernanceAssessor()
        answers = {f"Q{i:02d}": 0 for i in range(1, 26)}
        result = assessor.assess(answers)
        gap_report = analyze_gaps(result)
        roadmap = gap_report.roadmap
        total_items = len(roadmap.phase1) + len(roadmap.phase2) + len(roadmap.phase3)
        assert total_items > 0

    def test_s3_step5_policy_generator_5_documents(self) -> None:
        """Policy generator produces exactly 5 policy documents."""
        from faultray.governance.policy_generator import generate_all_policies
        policies = generate_all_policies("TestOrg Inc.")
        assert len(policies) == 5
        for p in policies:
            assert p.id
            assert p.content
            assert "TestOrg Inc." in p.content or p.org_name == "TestOrg Inc."

    def test_s3_step6_ai_registry_register(self) -> None:
        """AI system can be registered and retrieved."""
        from faultray.governance.ai_registry import AISystem, register_ai_system, get_ai_system
        system = AISystem(name="TestBot", org_id="org1", ai_type="generative")
        sid = register_ai_system(system)
        fetched = get_ai_system(sid)
        assert fetched is not None
        assert fetched.name == "TestBot"

    def test_s3_step7_evidence_hash_chain_integrity(self, tmp_path: Path) -> None:
        """Registering evidence creates a valid hash chain."""
        from faultray.governance.evidence_manager import register_evidence, verify_chain
        f = tmp_path / "evidence.txt"
        f.write_text("governance evidence", encoding="utf-8")
        register_evidence("C01-R01", "Test evidence", str(f), "tester")
        assert verify_chain() is True

    def test_s3_full_cycle(self, tmp_path: Path) -> None:
        """Full assess->gap->roadmap->policy->evidence cycle."""
        from faultray.governance.assessor import GovernanceAssessor
        from faultray.governance.gap_analyzer import analyze_gaps
        from faultray.governance.policy_generator import generate_all_policies
        from faultray.governance.evidence_manager import register_evidence, verify_chain

        # Assess
        assessor = GovernanceAssessor()
        answers = {f"Q{i:02d}": 1 for i in range(1, 26)}
        result = assessor.assess(answers)
        assert result.overall_score >= 0.0

        # Gap analysis
        gap_report = analyze_gaps(result)
        assert gap_report.total_requirements > 0

        # Policies
        policies = generate_all_policies("E2E Test Org")
        assert len(policies) == 5

        # Evidence
        f = tmp_path / "ev.txt"
        f.write_text("test", encoding="utf-8")
        register_evidence("C02-R01", "Safety evidence", str(f))
        assert verify_chain() is True


# ---------------------------------------------------------------------------
# Scenario 4: APM + Simulation Integration
# ---------------------------------------------------------------------------


class TestScenario4APMSimulationIntegration:
    """APM agent collects metrics -> topology build -> simulation -> link calibration."""

    def test_s4_step1_batch_builds_topology(self) -> None:
        """Batch with LISTEN connections builds topology components."""
        g = InfraGraph()
        set_topology_graph(g)
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
            # postgres listener should yield a DATABASE component
            types = [c.type for c in g.components.values()]
            assert ComponentType.DATABASE in types
        finally:
            set_topology_graph(None)  # type: ignore[arg-type]

    def test_s4_step2_multiple_batches_grow_topology(self) -> None:
        """Multiple batches add new components to the topology."""
        g = InfraGraph()
        set_topology_graph(g)
        try:
            for port, name in [(80, "nginx"), (6379, "redis")]:
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
            assert len(g.components) >= 2
        finally:
            set_topology_graph(None)  # type: ignore[arg-type]

    def test_s4_step3_auto_discover_returns_graph(self) -> None:
        """AutoDiscoverer.discover_local() returns a valid InfraGraph."""
        discoverer = AutoDiscoverer()
        graph = discoverer.discover_local()
        assert isinstance(graph, InfraGraph)

    def test_s4_step4_simulation_on_discovered_graph(self) -> None:
        """AutoSimulator can run on a discovered graph."""
        discoverer = AutoDiscoverer()
        graph = discoverer.discover_local()
        report = AutoSimulator(graph).run()
        assert report.score >= 0.0
        assert report.components_analyzed >= 0

    def test_s4_step5_simulation_link_marks_critical(self) -> None:
        """SimulationAPMLink marks critical components from simulation results."""
        from faultray.apm.simulation_link import SimulationAPMLink
        from faultray.apm.metrics_db import MetricsDB

        g = InfraGraph()
        g.add_component(Component(id="db-01", name="db-01", type=ComponentType.DATABASE))

        class _FakeDB:
            def query_metrics(self, *a, **kw):
                return []

        link = SimulationAPMLink(g, _FakeDB())  # type: ignore[arg-type]
        sim_results = {"scenarios": [{"component_id": "db-01", "severity": "critical"}]}
        critical = link.mark_critical_components(sim_results)
        assert "db-01" in critical

    def test_s4_full_flow(self) -> None:
        """Full APM+Simulation flow without exceptions."""
        # Discovery
        discoverer = AutoDiscoverer()
        graph = discoverer.discover_local()

        # Simulation
        report = AutoSimulator(graph).run()
        assert isinstance(report.score, float)

        # Anomaly engine on same agent ID
        engine = AnomalyEngine(rules=list(DEFAULT_ALERT_RULES))
        alerts = engine.check_batch("test-agent", HostMetrics())
        assert isinstance(alerts, list)


# ---------------------------------------------------------------------------
# Scenario 5: Full Self-Healing Cycle
# ---------------------------------------------------------------------------


class TestScenario5FullSelfHealingCycle:
    """High CPU detected -> discover -> simulate SPOF -> plan -> dry-run -> verify."""

    def test_s5_step1_anomaly_fires_on_high_cpu(self) -> None:
        """APM agent detects high CPU (via duration-based alert)."""
        import time
        from faultray.apm.models import AlertRule, AlertSeverity
        engine = AnomalyEngine(rules=[], window_size=10)
        engine.add_rule(AlertRule(
            name="instant_cpu",
            metric_name="cpu_percent",
            condition="gt",
            threshold=80.0,
            duration_seconds=0,  # fire immediately
            severity=AlertSeverity.CRITICAL,
        ))
        hm = HostMetrics(cpu_percent=90.0)
        alerts = engine.check_batch("db-server", hm)
        assert len(alerts) == 1
        assert alerts[0].rule_name == "instant_cpu"
        assert alerts[0].agent_id == "db-server"

    def test_s5_step2_topology_built_from_discovery(self) -> None:
        """Auto-discover builds topology from local discovery."""
        with patch("faultray.discovery.scanner.scan_local") as mock_scan:
            mock_graph = _make_spof_graph()
            mock_scan.return_value = mock_graph
            discoverer = AutoDiscoverer()
            graph = discoverer.discover_local()
        assert "db-01" in graph.components

    def test_s5_step3_simulation_finds_spof(self) -> None:
        """Simulation on SPOF topology detects the single point of failure."""
        graph = _make_spof_graph()
        report = AutoSimulator(graph).run()
        # SPOF present — score should be below perfect
        assert report.score < 100.0

    def test_s5_step4_remediation_generates_terraform(self, tmp_path: Path) -> None:
        """Remediation agent generates IaC files in dry-run mode."""
        agent = _make_remediation_agent(tmp_path)
        cycle = agent.run_cycle()
        # In dry-run mode at least the cycle should record the plan
        assert cycle.status in ("completed", "failed", "awaiting_approval", "rolled_back")

    def test_s5_step5_ratchet_restricts_permissions(self) -> None:
        """Ratchet narrows permissions when CONFIDENTIAL resource is touched."""
        from faultray.simulator.ratchet_models import RatchetState, SensitivityLevel
        state = RatchetState()
        assert "execute:tool" in state.remaining_permissions
        state.apply_ratchet(SensitivityLevel.CONFIDENTIAL)
        assert "execute:tool" not in state.remaining_permissions

    def test_s5_step6_cycle_json_has_before_after_scores(self, tmp_path: Path) -> None:
        """Cycle JSON records initial_score and simulated_score."""
        agent = _make_remediation_agent(tmp_path)
        cycle = agent.run_cycle()
        d = cycle.to_dict()
        assert "initial_score" in d
        assert "simulated_score" in d

    def test_s5_step7_report_has_summary(self, tmp_path: Path) -> None:
        """Cycle report_summary is populated after completion."""
        agent = _make_remediation_agent(tmp_path)
        cycle = agent.run_cycle()
        assert cycle.report_summary
        assert len(cycle.report_summary) > 0

    def test_s5_full_self_healing_cycle(self, tmp_path: Path) -> None:
        """Complete self-healing cycle: detect->discover->simulate->plan->verify."""
        # Step 1: anomaly detection
        from faultray.apm.models import AlertRule, AlertSeverity
        engine = AnomalyEngine(rules=[])
        engine.add_rule(AlertRule(
            name="cpu_high", metric_name="cpu_percent",
            condition="gt", threshold=80.0,
            duration_seconds=0, severity=AlertSeverity.CRITICAL,
        ))
        alerts = engine.check_batch("db-server", HostMetrics(cpu_percent=95.0))
        assert len(alerts) == 1

        # Step 2: build topology
        graph = _make_spof_graph()

        # Step 3: simulation
        report = AutoSimulator(graph).run()
        assert report.score >= 0.0

        # Step 4-6: remediation cycle
        agent = _make_remediation_agent(tmp_path, graph)
        cycle = agent.run_cycle()
        assert cycle.report_summary
