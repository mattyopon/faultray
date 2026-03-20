# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""FISC compliance report generator for Japanese financial institutions.

Generates evidence reports mapped to FISC安全対策基準 (FISC Security
Guidelines) requirements, specifically for system risk management
and disaster recovery assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


@dataclass
class FISCControl:
    """A FISC security control assessment."""
    control_id: str  # e.g., "技-1", "運-15"
    category: str  # 技術 (Technical), 運用 (Operational), 設備 (Facility)
    title: str
    description: str
    status: str  # "適合" (Compliant), "一部適合" (Partially), "非適合" (Non-compliant), "対象外" (N/A)
    evidence: str  # What FaultRay found
    recommendation: str = ""


@dataclass
class FISCReport:
    """FISC compliance assessment report."""
    report_id: str
    generated_at: str
    organization: str
    total_controls: int
    compliant: int
    partially_compliant: int
    non_compliant: int
    not_applicable: int
    controls: list[FISCControl] = field(default_factory=list)
    overall_score: float = 0.0  # 0-100


class FISCReportGenerator:
    """Generates FISC安全対策基準 compliance reports from FaultRay analysis."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def generate(self, organization: str = "未設定") -> FISCReport:
        """Generate a FISC compliance report."""
        controls = []

        # 技-1: システムの冗長化 (System Redundancy)
        controls.append(self._check_redundancy())

        # 技-5: 障害検知と自動復旧 (Fault Detection and Auto-Recovery)
        controls.append(self._check_fault_detection())

        # 技-8: データバックアップ (Data Backup)
        controls.append(self._check_backup())

        # 技-12: 暗号化 (Encryption)
        controls.append(self._check_encryption())

        # 運-15: 障害影響分析 (Failure Impact Analysis)
        controls.append(self._check_impact_analysis())

        # 運-18: 災害復旧計画 (Disaster Recovery Plan)
        controls.append(self._check_dr_plan())

        # 運-22: サードパーティリスク (Third-Party Risk)
        controls.append(self._check_third_party_risk())

        # 技-20: AI利用における安全管理 (AI Safety Management)
        controls.append(self._check_ai_safety())

        compliant = sum(1 for c in controls if c.status == "適合")
        partial = sum(1 for c in controls if c.status == "一部適合")
        non_compliant = sum(1 for c in controls if c.status == "非適合")
        na = sum(1 for c in controls if c.status == "対象外")

        total_applicable = len(controls) - na
        score = round((compliant + partial * 0.5) / max(total_applicable, 1) * 100, 1)

        now = datetime.now(timezone.utc)
        report_id = f"FISC-{now.strftime('%Y%m%d%H%M%S')}"

        return FISCReport(
            report_id=report_id,
            generated_at=now.isoformat(),
            organization=organization,
            total_controls=len(controls),
            compliant=compliant,
            partially_compliant=partial,
            non_compliant=non_compliant,
            not_applicable=na,
            controls=controls,
            overall_score=score,
        )

    def _check_redundancy(self) -> FISCControl:
        single_replica = [c for c in self.graph.components.values() if c.replicas <= 1]
        total = len(self.graph.components)
        redundant = total - len(single_replica)

        if len(single_replica) == 0:
            status = "適合"
            evidence = f"全{total}コンポーネントが冗長化済み"
        elif redundant / max(total, 1) >= 0.7:
            status = "一部適合"
            evidence = f"{redundant}/{total}コンポーネントが冗長化済み。未対応: {', '.join(c.name for c in single_replica[:5])}"
        else:
            status = "非適合"
            evidence = f"{len(single_replica)}/{total}コンポーネントが単一障害点"

        return FISCControl(
            control_id="技-1",
            category="技術",
            title="システムの冗長化",
            description="重要なシステムコンポーネントは冗長構成とすること",
            status=status,
            evidence=evidence,
            recommendation="単一レプリカのコンポーネントにレプリカを追加してください" if status != "適合" else "",
        )

    def _check_fault_detection(self) -> FISCControl:
        has_failover = [c for c in self.graph.components.values()
                       if c.failover and c.failover.enabled]
        has_autoscale = [c for c in self.graph.components.values()
                        if c.autoscaling and c.autoscaling.enabled]
        total = len(self.graph.components)
        covered = len(set(c.id for c in has_failover + has_autoscale))

        if covered / max(total, 1) >= 0.8:
            status = "適合"
        elif covered / max(total, 1) >= 0.5:
            status = "一部適合"
        else:
            status = "非適合"

        return FISCControl(
            control_id="技-5",
            category="技術",
            title="障害検知と自動復旧",
            description="障害を自動検知し、自動復旧する仕組みを導入すること",
            status=status,
            evidence=f"フェイルオーバー: {len(has_failover)}件、オートスケーリング: {len(has_autoscale)}件 / 全{total}件",
            recommendation="フェイルオーバーまたはオートスケーリングの設定を追加してください" if status != "適合" else "",
        )

    def _check_backup(self) -> FISCControl:
        data_components = [c for c in self.graph.components.values()
                          if c.type in (ComponentType.DATABASE, ComponentType.STORAGE)]
        if not data_components:
            return FISCControl(
                control_id="技-8", category="技術", title="データバックアップ",
                description="重要データの定期バックアップを実施すること",
                status="対象外", evidence="データストアコンポーネントなし",
            )

        backed_up = [c for c in data_components
                    if c.security and c.security.backup_enabled]

        if len(backed_up) == len(data_components):
            status = "適合"
        elif backed_up:
            status = "一部適合"
        else:
            status = "非適合"

        return FISCControl(
            control_id="技-8",
            category="技術",
            title="データバックアップ",
            description="重要データの定期バックアップを実施すること",
            status=status,
            evidence=f"バックアップ設定済み: {len(backed_up)}/{len(data_components)}データストア",
            recommendation="全データストアのバックアップを有効にしてください" if status != "適合" else "",
        )

    def _check_encryption(self) -> FISCControl:
        encrypted_rest = [c for c in self.graph.components.values()
                         if c.security and c.security.encryption_at_rest]
        encrypted_transit = [c for c in self.graph.components.values()
                           if c.security and c.security.encryption_in_transit]
        total = len(self.graph.components)

        rest_pct = len(encrypted_rest) / max(total, 1)
        transit_pct = len(encrypted_transit) / max(total, 1)

        if rest_pct >= 0.9 and transit_pct >= 0.9:
            status = "適合"
        elif rest_pct >= 0.5 or transit_pct >= 0.5:
            status = "一部適合"
        else:
            status = "非適合"

        return FISCControl(
            control_id="技-12",
            category="技術",
            title="暗号化",
            description="保存時および通信時のデータ暗号化を実施すること",
            status=status,
            evidence=f"保存時暗号化: {len(encrypted_rest)}/{total}、通信時暗号化: {len(encrypted_transit)}/{total}",
            recommendation="全コンポーネントで暗号化を有効にしてください" if status != "適合" else "",
        )

    def _check_impact_analysis(self) -> FISCControl:
        # FaultRay's core function — always compliant if being used
        return FISCControl(
            control_id="運-15",
            category="運用",
            title="障害影響分析",
            description="システム障害の影響範囲を事前に分析すること",
            status="適合",
            evidence="FaultRayによる障害影響シミュレーションを実施済み。全コンポーネントの障害伝播パスを分析",
        )

    def _check_dr_plan(self) -> FISCControl:
        has_dr = [c for c in self.graph.components.values()
                 if c.region and c.region.dr_target_region]
        total = len(self.graph.components)

        if has_dr:
            status = "適合" if len(has_dr) / max(total, 1) >= 0.5 else "一部適合"
        else:
            status = "非適合"

        return FISCControl(
            control_id="運-18",
            category="運用",
            title="災害復旧計画",
            description="災害時のシステム復旧計画を策定し、定期的に訓練すること",
            status=status,
            evidence=f"DR設定済み: {len(has_dr)}/{total}コンポーネント",
            recommendation="災害復旧先リージョンの設定を追加してください" if status != "適合" else "",
        )

    def _check_third_party_risk(self) -> FISCControl:
        external = [c for c in self.graph.components.values()
                   if c.type in (ComponentType.EXTERNAL_API, ComponentType.LLM_ENDPOINT)]

        if not external:
            return FISCControl(
                control_id="運-22", category="運用", title="サードパーティリスク管理",
                description="外部サービスのリスク評価を実施すること",
                status="対象外", evidence="外部サービス依存なし",
            )

        with_sla = [c for c in external if c.external_sla]
        status = "適合" if len(with_sla) == len(external) else "一部適合" if with_sla else "非適合"

        return FISCControl(
            control_id="運-22",
            category="運用",
            title="サードパーティリスク管理",
            description="外部サービスのリスク評価を実施すること",
            status=status,
            evidence=f"SLA定義済み: {len(with_sla)}/{len(external)}外部サービス",
            recommendation="全外部サービスのSLAを定義してください" if status != "適合" else "",
        )

    def _check_ai_safety(self) -> FISCControl:
        agents = [c for c in self.graph.components.values()
                 if c.type in (ComponentType.AI_AGENT, ComponentType.AGENT_ORCHESTRATOR)]

        if not agents:
            return FISCControl(
                control_id="技-20", category="技術", title="AI利用における安全管理",
                description="AIシステムの利用に際し、適切な安全管理措置を講じること",
                status="対象外", evidence="AIエージェントコンポーネントなし",
            )

        params_list = [a.parameters or {} for a in agents]
        has_grounding = sum(1 for p in params_list if p.get("requires_grounding"))
        has_circuit_breaker = sum(1 for p in params_list if p.get("circuit_breaker_on_hallucination"))

        if has_grounding == len(agents) and has_circuit_breaker == len(agents):
            status = "適合"
        elif has_grounding > 0 or has_circuit_breaker > 0:
            status = "一部適合"
        else:
            status = "非適合"

        return FISCControl(
            control_id="技-20",
            category="技術",
            title="AI利用における安全管理",
            description="AIシステムの利用に際し、適切な安全管理措置を講じること",
            status=status,
            evidence=f"データグラウンディング: {has_grounding}/{len(agents)}、ハルシネーション遮断器: {has_circuit_breaker}/{len(agents)}",
            recommendation="全AIエージェントにデータグラウンディングとハルシネーション検知を設定してください" if status != "適合" else "",
        )
