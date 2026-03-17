"""Tests for FISC compliance report generator."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    ExternalSLAConfig,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.reporter.fisc_report import FISCControl, FISCReport, FISCReportGenerator


# ---------------------------------------------------------------------------
# Graph builders
# ---------------------------------------------------------------------------

def _build_fully_compliant_graph() -> InfraGraph:
    """Build a graph that should pass all FISC controls."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="web", name="Web Server", type=ComponentType.WEB_SERVER,
        replicas=3,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True, backup_enabled=True,
        ),
        region=RegionConfig(region="ap-northeast-1", dr_target_region="ap-northeast-3"),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(
            encryption_at_rest=True, encryption_in_transit=True, backup_enabled=True,
        ),
        region=RegionConfig(region="ap-northeast-1", dr_target_region="ap-northeast-3"),
    ))
    return graph


def _build_minimal_graph() -> InfraGraph:
    """Build a graph with minimal configuration (many controls will fail)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="web", name="Web Server", type=ComponentType.WEB_SERVER,
        replicas=1,
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE,
        replicas=1,
    ))
    return graph


def _build_graph_with_agents() -> InfraGraph:
    """Build a graph containing AI agent components."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="agent1", name="AI Agent 1", type=ComponentType.AI_AGENT,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(encryption_at_rest=True, encryption_in_transit=True),
        parameters={
            "requires_grounding": 1,
            "circuit_breaker_on_hallucination": 1,
        },
    ))
    graph.add_component(Component(
        id="orch", name="Agent Orchestrator", type=ComponentType.AGENT_ORCHESTRATOR,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        security=SecurityProfile(encryption_at_rest=True, encryption_in_transit=True),
        parameters={
            "requires_grounding": 1,
            "circuit_breaker_on_hallucination": 1,
        },
    ))
    return graph


def _build_graph_with_external_apis() -> InfraGraph:
    """Build a graph with external API dependencies."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="ext1", name="Payment API", type=ComponentType.EXTERNAL_API,
        replicas=1,
        external_sla=ExternalSLAConfig(provider_sla=99.9),
    ))
    graph.add_component(Component(
        id="ext2", name="Notification API", type=ComponentType.EXTERNAL_API,
        replicas=1,
        # No SLA defined
    ))
    return graph


def _find_control(report: FISCReport, control_id: str) -> FISCControl:
    """Find a control by ID in the report."""
    for c in report.controls:
        if c.control_id == control_id:
            return c
    raise ValueError(f"Control {control_id} not found")


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

class TestFISCReportGeneration:
    """Tests for overall report generation."""

    def test_report_has_8_controls(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        assert report.total_controls == 8

    def test_report_id_format(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        assert report.report_id.startswith("FISC-")

    def test_organization_default(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        assert report.organization == "未設定"

    def test_organization_custom(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate(organization="テスト銀行")
        assert report.organization == "テスト銀行"

    def test_generated_at_is_iso8601(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        assert "T" in report.generated_at

    def test_status_counts_sum(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        total = report.compliant + report.partially_compliant + report.non_compliant + report.not_applicable
        assert total == report.total_controls


# ---------------------------------------------------------------------------
# Score Calculation
# ---------------------------------------------------------------------------

class TestFISCScoring:
    """Tests for compliance score calculation."""

    def test_fully_compliant_high_score(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        # Should have a high score (some controls may be N/A)
        assert report.overall_score >= 80.0

    def test_minimal_graph_low_score(self) -> None:
        graph = _build_minimal_graph()
        report = FISCReportGenerator(graph).generate()
        assert report.overall_score < 50.0

    def test_score_range(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        assert 0.0 <= report.overall_score <= 100.0


# ---------------------------------------------------------------------------
# Individual Controls
# ---------------------------------------------------------------------------

class TestFISCRedundancy:
    """Tests for 技-1: システムの冗長化."""

    def test_all_redundant_compliant(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-1")
        assert control.status == "適合"

    def test_no_redundancy_non_compliant(self) -> None:
        graph = _build_minimal_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-1")
        assert control.status == "非適合"

    def test_partial_redundancy(self) -> None:
        graph = InfraGraph()
        # 3 out of 4 components have replicas > 1 (75% >= 70% threshold)
        for i in range(3):
            graph.add_component(Component(
                id=f"svc{i}", name=f"Service {i}", type=ComponentType.APP_SERVER,
                replicas=2,
            ))
        graph.add_component(Component(
            id="single", name="Single", type=ComponentType.APP_SERVER, replicas=1,
        ))
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-1")
        assert control.status == "一部適合"


class TestFISCFaultDetection:
    """Tests for 技-5: 障害検知と自動復旧."""

    def test_failover_and_autoscale_compliant(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-5")
        assert control.status == "適合"

    def test_no_fault_detection_non_compliant(self) -> None:
        graph = _build_minimal_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-5")
        assert control.status == "非適合"


class TestFISCBackup:
    """Tests for 技-8: データバックアップ."""

    def test_all_backed_up_compliant(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-8")
        assert control.status == "適合"

    def test_no_backup_non_compliant(self) -> None:
        graph = _build_minimal_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-8")
        assert control.status == "非適合"

    def test_no_data_components_na(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="web", name="Web", type=ComponentType.WEB_SERVER, replicas=1,
        ))
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-8")
        assert control.status == "対象外"

    def test_partial_backup(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="db1", name="DB1", type=ComponentType.DATABASE,
            security=SecurityProfile(backup_enabled=True),
        ))
        graph.add_component(Component(
            id="db2", name="DB2", type=ComponentType.DATABASE,
            security=SecurityProfile(backup_enabled=False),
        ))
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-8")
        assert control.status == "一部適合"


class TestFISCEncryption:
    """Tests for 技-12: 暗号化."""

    def test_fully_encrypted_compliant(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-12")
        assert control.status == "適合"

    def test_no_encryption_non_compliant(self) -> None:
        graph = _build_minimal_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-12")
        assert control.status == "非適合"


class TestFISCImpactAnalysis:
    """Tests for 運-15: 障害影響分析."""

    def test_always_compliant(self) -> None:
        """FaultRay usage itself satisfies this control."""
        graph = _build_minimal_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "運-15")
        assert control.status == "適合"


class TestFISCDRPlan:
    """Tests for 運-18: 災害復旧計画."""

    def test_dr_configured_compliant(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "運-18")
        assert control.status == "適合"

    def test_no_dr_non_compliant(self) -> None:
        graph = _build_minimal_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "運-18")
        assert control.status == "非適合"


class TestFISCThirdPartyRisk:
    """Tests for 運-22: サードパーティリスク管理."""

    def test_no_external_na(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "運-22")
        assert control.status == "対象外"

    def test_partial_sla_coverage(self) -> None:
        graph = _build_graph_with_external_apis()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "運-22")
        assert control.status == "一部適合"

    def test_all_sla_compliant(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="ext", name="API", type=ComponentType.EXTERNAL_API,
            external_sla=ExternalSLAConfig(provider_sla=99.9),
        ))
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "運-22")
        assert control.status == "適合"

    def test_no_sla_non_compliant(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="ext", name="API", type=ComponentType.EXTERNAL_API,
        ))
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "運-22")
        assert control.status == "非適合"


class TestFISCAISafety:
    """Tests for 技-20: AI利用における安全管理."""

    def test_no_agents_na(self) -> None:
        graph = _build_fully_compliant_graph()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-20")
        assert control.status == "対象外"

    def test_fully_configured_agents_compliant(self) -> None:
        graph = _build_graph_with_agents()
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-20")
        assert control.status == "適合"

    def test_unconfigured_agents_non_compliant(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="agent", name="Agent", type=ComponentType.AI_AGENT,
            parameters={},
        ))
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-20")
        assert control.status == "非適合"

    def test_partial_agent_config(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="agent1", name="Agent 1", type=ComponentType.AI_AGENT,
            parameters={"requires_grounding": 1},
        ))
        graph.add_component(Component(
            id="agent2", name="Agent 2", type=ComponentType.AI_AGENT,
            parameters={},
        ))
        report = FISCReportGenerator(graph).generate()
        control = _find_control(report, "技-20")
        assert control.status == "一部適合"
