# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Enhanced gap analysis with multi-framework support and roadmap generation.

Extends the existing assessor with:
- Multi-framework gap analysis (METI -> ISO -> AI推進法 in one report)
- Priority-based improvement roadmap (Phase 1-3)
- Default improvement actions for all 28 requirements
- Optional AI-powered recommendations (Claude API fallback)

Ported from JPGovAI's gap_analysis service, adapted to FaultRay patterns.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from faultray.governance.assessor import AssessmentResult
from faultray.governance.frameworks import (
    all_meti_requirements,
    get_frameworks_for_meti_requirement,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RequirementGap:
    """Gap information for a single requirement."""

    req_id: str = ""
    category_id: str = ""
    title: str = ""
    status: str = "non_compliant"  # compliant / partial / non_compliant
    current_score: float = 0.0
    gap_description: str = ""
    improvement_actions: list[str] = field(default_factory=list)
    priority: str = "medium"  # high / medium / low


@dataclass
class RoadmapItem:
    """A single improvement action in the roadmap."""

    phase: int = 1  # 1, 2, or 3
    phase_label: str = ""
    req_id: str = ""
    title: str = ""
    actions: list[str] = field(default_factory=list)
    priority: str = "medium"


@dataclass
class Roadmap:
    """Phased improvement roadmap."""

    phase1: list[RoadmapItem] = field(default_factory=list)  # 1-3 months
    phase2: list[RoadmapItem] = field(default_factory=list)  # 3-6 months
    phase3: list[RoadmapItem] = field(default_factory=list)  # 6-12 months


@dataclass
class GapReport:
    """Complete gap analysis report."""

    assessment_id: str = ""
    total_requirements: int = 0
    compliant: int = 0
    partial: int = 0
    non_compliant: int = 0
    gaps: list[RequirementGap] = field(default_factory=list)
    roadmap: Roadmap = field(default_factory=Roadmap)
    multi_framework_impact: dict = field(default_factory=dict)
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not self.assessment_id:
            self.assessment_id = f"GAP-{uuid.uuid4().hex[:8]}"
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Status determination
# ---------------------------------------------------------------------------


def _score_to_status(score_pct: float) -> str:
    """Convert score percentage to compliance status."""
    if score_pct >= 75.0:
        return "compliant"
    elif score_pct >= 37.5:
        return "partial"
    return "non_compliant"


def _determine_priority(status: str, category_id: str) -> str:
    """Determine improvement priority based on status and category."""
    high_priority_cats = {"C02", "C04", "C05"}  # Safety, Privacy, Security
    if status == "non_compliant":
        return "high"
    elif status == "partial":
        return "high" if category_id in high_priority_cats else "medium"
    return "low"


# ---------------------------------------------------------------------------
# Default improvement actions for all 28 METI requirements
# ---------------------------------------------------------------------------

_DEFAULT_ACTIONS: dict[str, list[str]] = {
    "C01-R01": [
        "AIガバナンス基本方針に人間中心の原則を明記する",
        "全従業員への方針周知・研修を実施する",
    ],
    "C01-R02": [
        "高リスクAIシステムの判断に人間の最終承認プロセスを導入する",
        "Human-in-the-Loopの仕組みを設計・実装する",
    ],
    "C01-R03": [
        "AI生成コンテンツのファクトチェックプロセスを整備する",
        "誤情報検出・フィルタリングの仕組みを導入する",
    ],
    "C02-R01": [
        "AI固有のリスクアセスメントフレームワークを策定する",
        "定期的なリスク評価スケジュールを確立する",
    ],
    "C02-R02": [
        "学習データの品質基準を定義する",
        "データ品質の定期監査プロセスを導入する",
    ],
    "C02-R03": [
        "AIシステムの異常検知・安全停止手順書を作成する",
        "フォールバック手段の設計と定期的な訓練を実施する",
    ],
    "C03-R01": [
        "バイアス評価のための定量的指標を定義する",
        "定期的なバイアスオーディットを実施する",
    ],
    "C03-R02": [
        "利用文脈に応じた公平性基準を策定する",
        "公平性モニタリングダッシュボードを構築する",
    ],
    "C03-R03": [
        "バイアス検出時の是正手順と責任者を明確にする",
        "是正実施後の効果検証プロセスを整備する",
    ],
    "C04-R01": [
        "AI固有の個人情報取扱方針を策定・公表する",
        "方針の定期見直しスケジュールを設定する",
    ],
    "C04-R02": [
        "AI導入前のPIA（プライバシー影響評価）テンプレートを作成する",
        "全AIシステムでPIAを実施する",
    ],
    "C04-R03": [
        "データ最小化の原則をAIデータ設計に組み込む",
        "目的外利用を防止する技術的・組織的措置を講じる",
    ],
    "C05-R01": [
        "AI固有の脅威（敵対的攻撃等）に対するセキュリティ対策を実装する",
        "定期的なペネトレーションテストを実施する",
    ],
    "C05-R02": [
        "AIシステムの脆弱性管理プロセスを確立する",
        "脆弱性スキャンの自動化と修正追跡を行う",
    ],
    "C05-R03": [
        "AIセキュリティインシデント対応計画を策定する",
        "対応手順の定期訓練を実施する",
    ],
    "C06-R01": [
        "AIの利用を利害関係者に明示するポリシーを策定する",
        "サービス画面・ドキュメントでのAI利用表示を実装する",
    ],
    "C06-R02": [
        "AI判断の説明生成機能を設計・実装する",
        "利用者向けの判断根拠説明テンプレートを作成する",
    ],
    "C06-R03": [
        "モデルカード等の標準フォーマットで技術文書を整備する",
        "バージョン管理と変更履歴の体制を構築する",
    ],
    "C07-R01": [
        "AIガバナンス責任者を正式に任命する",
        "責任者の権限・責任を組織内文書で明確にする",
    ],
    "C07-R02": [
        "AIガバナンス方針を策定し、実施体制を整備する",
        "定期的な方針レビューと改善サイクルを確立する",
    ],
    "C07-R03": [
        "AI関連契約の標準テンプレートを作成する",
        "責任分界・品質保証条項を明確にする",
    ],
    "C07-R04": [
        "ガバナンス記録の統一管理システムを導入する",
        "改竄防止付きの監査証跡を実装する",
    ],
    "C08-R01": [
        "役割別のAI教育プログラムを設計・実施する",
        "教育効果の測定と改善サイクルを確立する",
    ],
    "C08-R02": [
        "AIシステム利用者向けガイドラインを作成する",
        "FAQとサポート体制を整備する",
    ],
    "C09-R01": [
        "AI利用における公正競争方針を策定する",
        "競争法コンプライアンスのレビュー体制を構築する",
    ],
    "C09-R02": [
        "AI学習・利用における知的財産権チェックリストを作成する",
        "知的財産権侵害リスクの評価プロセスを導入する",
    ],
    "C10-R01": [
        "AIイノベーション推進のロードマップを策定する",
        "社外連携・オープンイノベーションの機会を探索する",
    ],
    "C10-R02": [
        "相互運用性を考慮したAI技術選定基準を策定する",
        "オープン標準への準拠方針を定める",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_gaps(assessment_result: AssessmentResult) -> GapReport:
    """Run gap analysis on an assessment result.

    Produces a GapReport with per-requirement gaps, multi-framework impact,
    and a phased improvement roadmap.

    Args:
        assessment_result: The assessment result from GovernanceAssessor.

    Returns:
        GapReport with gaps, roadmap, and multi-framework impact.
    """
    # Build requirement score map from assessment
    req_score_map: dict[str, float] = {}
    for rs in assessment_result.requirement_scores:
        req_score_map[rs.req_id] = rs.score

    gaps: list[RequirementGap] = []

    for req in all_meti_requirements():
        score = req_score_map.get(req.req_id, 0.0)
        status = _score_to_status(score)
        priority = _determine_priority(status, req.category_id)

        if status == "compliant":
            actions = ["現状維持＋定期的な見直しを継続する"]
        else:
            actions = _DEFAULT_ACTIONS.get(req.req_id, [
                "当該要件の現状を詳細に調査する",
                "改善計画を策定し、責任者と期限を設定する",
            ])

        gap_desc = ""
        if status == "non_compliant":
            gap_desc = f"要件「{req.title}」が未充足です。{req.description}"
        elif status == "partial":
            gap_desc = f"要件「{req.title}」が部分的に充足されています。さらなる改善が必要です。"

        gaps.append(RequirementGap(
            req_id=req.req_id,
            category_id=req.category_id,
            title=req.title,
            status=status,
            current_score=round(score, 1),
            gap_description=gap_desc,
            improvement_actions=actions,
            priority=priority,
        ))

    compliant = sum(1 for g in gaps if g.status == "compliant")
    partial_count = sum(1 for g in gaps if g.status == "partial")
    non_compliant = sum(1 for g in gaps if g.status == "non_compliant")

    # Multi-framework impact
    multi_fw = get_multi_framework_violations(gaps)

    # Roadmap
    roadmap = generate_roadmap(gaps)

    return GapReport(
        total_requirements=len(gaps),
        compliant=compliant,
        partial=partial_count,
        non_compliant=non_compliant,
        gaps=gaps,
        roadmap=roadmap,
        multi_framework_impact=multi_fw,
    )


def generate_roadmap(gaps: list[RequirementGap] | None = None, gap_report: GapReport | None = None) -> Roadmap:
    """Generate a phased improvement roadmap.

    Phase 1 (1-3 months): Safety, Security, Privacy (C02, C04, C05) non-compliant
    Phase 2 (3-6 months): Governance, Accountability (C07, C01, C03) + remaining high priority
    Phase 3 (6-12 months): Education, Innovation, Fair Competition + partial items

    Args:
        gaps: List of RequirementGap (direct) or from gap_report.
        gap_report: GapReport to extract gaps from.

    Returns:
        Roadmap with phase1, phase2, phase3 items.
    """
    if gap_report is not None:
        gaps = gap_report.gaps
    if gaps is None:
        return Roadmap()

    phase1_cats = {"C02", "C04", "C05"}
    phase2_cats = {"C01", "C03", "C06", "C07"}
    # phase3: everything else

    roadmap = Roadmap()

    for gap in gaps:
        if gap.status == "compliant":
            continue

        item = RoadmapItem(
            req_id=gap.req_id,
            title=gap.title,
            actions=gap.improvement_actions,
            priority=gap.priority,
        )

        if gap.status == "non_compliant" and gap.category_id in phase1_cats:
            item.phase = 1
            item.phase_label = "Phase 1 (1-3ヶ月): 安全性・セキュリティ・プライバシー"
            roadmap.phase1.append(item)
        elif gap.status == "non_compliant" and gap.category_id in phase2_cats:
            item.phase = 2
            item.phase_label = "Phase 2 (3-6ヶ月): ガバナンス体制・アカウンタビリティ"
            roadmap.phase2.append(item)
        elif gap.status == "non_compliant":
            item.phase = 2
            item.phase_label = "Phase 2 (3-6ヶ月): その他未充足要件"
            roadmap.phase2.append(item)
        else:  # partial
            if gap.category_id in phase1_cats:
                item.phase = 2
                item.phase_label = "Phase 2 (3-6ヶ月): 安全性・セキュリティ強化"
                roadmap.phase2.append(item)
            else:
                item.phase = 3
                item.phase_label = "Phase 3 (6-12ヶ月): 全要件充足と継続的改善"
                roadmap.phase3.append(item)

    return roadmap


def get_multi_framework_violations(
    gaps: list[RequirementGap] | None = None,
    gap_report: GapReport | None = None,
) -> dict:
    """Get violations across multiple frameworks for non-compliant requirements.

    For each non-compliant/partial METI requirement, shows which ISO 42001
    and AI推進法 requirements are also impacted.

    Args:
        gaps: List of RequirementGap (direct) or from gap_report.
        gap_report: GapReport to extract gaps from.

    Returns:
        Dict with per-requirement framework violations and summary.
    """
    if gap_report is not None:
        gaps = gap_report.gaps
    if gaps is None:
        return {"violations": [], "summary": {}}

    violations: list[dict] = []
    iso_impacted: set[str] = set()
    act_impacted: set[str] = set()

    for gap in gaps:
        if gap.status == "compliant":
            continue

        fw_map = get_frameworks_for_meti_requirement(gap.req_id)

        violation = {
            "req_id": gap.req_id,
            "title": gap.title,
            "status": gap.status,
            "score": gap.current_score,
            "meti": gap.req_id,
            "iso_impacts": fw_map.get("iso", []),
            "act_impacts": fw_map.get("act", []),
        }
        violations.append(violation)

        iso_impacted.update(fw_map.get("iso", []))
        act_impacted.update(fw_map.get("act", []))

    return {
        "violations": violations,
        "summary": {
            "total_meti_gaps": len(violations),
            "iso_requirements_impacted": len(iso_impacted),
            "act_requirements_impacted": len(act_impacted),
            "iso_impacted_ids": sorted(iso_impacted),
            "act_impacted_ids": sorted(act_impacted),
        },
    }


def generate_ai_recommendations(gap_report: GapReport) -> str:
    """Generate AI-powered recommendations using Claude API.

    Falls back to template-based recommendations if API is unavailable.

    Args:
        gap_report: The gap analysis report.

    Returns:
        Markdown string with recommendations.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-xxx"):
        return _fallback_recommendations(gap_report)

    try:
        import anthropic  # type: ignore[import-untyped]

        client = anthropic.Anthropic(api_key=api_key)

        non_compliant = [g for g in gap_report.gaps if g.status != "compliant"]
        if not non_compliant:
            return "全要件が充足しています。現状のガバナンス体制を維持してください。"

        gap_summary = "\n".join(
            f"- [{g.req_id}] {g.title}: {g.status} (スコア: {g.current_score})"
            for g in non_compliant[:15]
        )

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "あなたはAIガバナンスの専門家です。\n"
                        "以下はMETI AI事業者ガイドライン準拠状況のギャップ分析結果です。\n\n"
                        f"## 未充足・部分充足の要件:\n{gap_summary}\n\n"
                        "## タスク:\n"
                        "1. 最も優先度の高い改善アクションを5つ挙げてください\n"
                        "2. 各アクションの具体的な実施手順を簡潔に記述してください\n"
                        "3. 想定される期間と必要リソースの目安を示してください\n\n"
                        "日本語で回答してください。"
                    ),
                }
            ],
        )
        return message.content[0].text  # type: ignore[union-attr]
    except Exception:
        return _fallback_recommendations(gap_report)


def _fallback_recommendations(gap_report: GapReport) -> str:
    """Template-based recommendations when AI API is unavailable."""
    non_compliant = [g for g in gap_report.gaps if g.status == "non_compliant"]
    partial = [g for g in gap_report.gaps if g.status == "partial"]

    lines = ["## 改善提案\n"]

    if non_compliant:
        lines.append("### 優先度: 高（未充足）")
        for g in non_compliant[:5]:
            lines.append(f"\n**{g.req_id}: {g.title}**")
            for action in g.improvement_actions:
                lines.append(f"  - {action}")

    if partial:
        lines.append("\n### 優先度: 中（部分充足）")
        for g in partial[:5]:
            lines.append(f"\n**{g.req_id}: {g.title}**")
            for action in g.improvement_actions:
                lines.append(f"  - {action}")

    lines.append("\n### 推奨ロードマップ")
    lines.append("1. **Phase 1 (1-3ヶ月)**: 高リスク要件（安全性・セキュリティ・プライバシー）の対応")
    lines.append("2. **Phase 2 (3-6ヶ月)**: ガバナンス体制・アカウンタビリティの整備")
    lines.append("3. **Phase 3 (6-12ヶ月)**: 全要件の充足と継続的改善体制の構築")

    return "\n".join(lines)
