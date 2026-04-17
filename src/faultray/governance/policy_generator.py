# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""AI Governance policy template generator.

Auto-generates comprehensive Japanese policy documents for 5 key areas.
Optionally integrates with Claude API for customized content.

Ported from JPGovAI's policy_generator service, adapted to FaultRay:
- dataclasses instead of Pydantic
- Markdown output (not PDF)
- File-based, no DB dependency
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PolicyDocument:
    """A generated policy document."""

    id: str = ""
    policy_type: str = ""
    title: str = ""
    content: str = ""  # markdown
    generated_at: str = ""
    org_name: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"POL-{uuid.uuid4().hex[:8].upper()}"
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Policy types
# ---------------------------------------------------------------------------

POLICY_TYPES: dict[str, dict[str, str]] = {
    "ai_usage": {
        "title": "AI利用ポリシー",
        "description": "組織におけるAIの利用に関する基本方針",
    },
    "risk_management": {
        "title": "AIリスク管理方針",
        "description": "AIシステムのリスクを特定・評価・軽減するための方針",
    },
    "ethics": {
        "title": "AI倫理方針",
        "description": "AI開発・利用における倫理的な指針",
    },
    "data_management": {
        "title": "データ管理方針",
        "description": "AI開発・運用に使用するデータの管理に関する方針",
    },
    "incident_response": {
        "title": "AIインシデント対応手順書",
        "description": "AIシステムに関するインシデント発生時の対応手順",
    },
}


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "ai_usage": [
        {
            "heading": "目的",
            "content": (
                "本ポリシーは、{org_name}（以下「当社」）におけるAI（人工知能）の"
                "利用に関する基本方針を定め、安全かつ責任あるAI活用を推進することを目的とする。"
            ),
        },
        {
            "heading": "適用範囲",
            "content": (
                "本ポリシーは、当社の全部門・全従業員が業務で利用するAIシステム・サービスに適用される。\n"
                "対象には以下を含む：\n"
                "- 社内開発のAIシステム\n"
                "- 外部から導入したAIサービス・API\n"
                "- 生成AI（ChatGPT、Claude等）の業務利用"
            ),
        },
        {
            "heading": "基本方針",
            "content": (
                "当社のAI利用は以下の原則に基づく：\n"
                "1. 人間中心: AIの判断に対する最終的な責任は人間が負う\n"
                "2. 安全性: AIシステムの安全な運用を確保する\n"
                "3. 公平性: 不当な差別を行わないよう配慮する\n"
                "4. 透明性: AI利用を利害関係者に適切に開示する\n"
                "5. プライバシー: 個人情報の保護を徹底する"
            ),
        },
        {
            "heading": "具体的措置",
            "content": (
                "1. 業務利用の承認: 新たなAIシステムの導入には所属長の承認を得ること\n"
                "2. データ入力制限: 機密情報・個人情報を外部AIサービスに入力しないこと\n"
                "3. 出力検証: AIの出力は必ず人間が確認・検証すること\n"
                "4. 記録保持: AI利用の記録を適切に保持すること\n\n"
                "以下のAI利用を禁止する：\n"
                "- 法令に違反する目的での利用\n"
                "- 他者の権利を侵害する利用\n"
                "- 承認されていないAIサービスの業務利用\n"
                "- AI出力を検証なしで最終成果物として使用すること"
            ),
        },
        {
            "heading": "責任体制",
            "content": (
                "1. AIガバナンス責任者: [役職名]がAI利用全般を統括する\n"
                "2. 各部門責任者: 部門内のAI利用の管理・監督を行う\n"
                "3. 全従業員: 本ポリシーを遵守し、問題を発見した場合は速やかに報告する"
            ),
        },
        {
            "heading": "見直し・改善",
            "content": "本ポリシーは年1回以上見直し、必要に応じて改定する。",
        },
    ],
    "risk_management": [
        {
            "heading": "目的",
            "content": (
                "本方針は、{org_name}が開発・提供・利用するAIシステムに関するリスクを"
                "体系的に管理し、安全性を確保することを目的とする。"
            ),
        },
        {
            "heading": "適用範囲",
            "content": (
                "当社が開発、導入、または利用する全てのAIシステムに適用する。\n"
                "サードパーティから提供されるAIサービス・APIも対象に含む。"
            ),
        },
        {
            "heading": "基本方針",
            "content": (
                "AIシステムのリスクを以下の4段階に分類する：\n"
                "- 許容不可リスク: 法令・倫理に違反するリスク → 使用禁止\n"
                "- 高リスク: 人の生命・安全・権利に影響 → 厳格な管理措置\n"
                "- 限定的リスク: 透明性の確保が必要 → 情報開示義務\n"
                "- 最小リスク: 特段の規制なし → 自主的対応"
            ),
        },
        {
            "heading": "具体的措置",
            "content": (
                "1. リスク特定: AIシステムの用途・データ・影響範囲からリスクを特定\n"
                "2. リスク評価: 影響度×発生確率でリスクレベルを評価\n"
                "3. リスク対応: 回避・軽減・移転・受容の選択肢から対応を決定\n"
                "4. モニタリング: 継続的なリスク監視と定期的な再評価\n"
                "5. リスク評価実施頻度: 四半期ごと、および重大変更時"
            ),
        },
        {
            "heading": "責任体制",
            "content": (
                "1. リスク管理責任者: [役職名]\n"
                "2. 報告: リスク評価結果は経営層に報告する\n"
                "3. リスクが顕在化した場合の対応は「インシデント対応手順書」に従う"
            ),
        },
        {
            "heading": "見直し・改善",
            "content": "本方針は年1回以上見直し、リスク環境の変化に応じて改定する。",
        },
    ],
    "ethics": [
        {
            "heading": "目的",
            "content": (
                "{org_name}は、AIが人類の福祉に貢献する技術であることを信じ、"
                "以下の倫理原則に基づきAIの開発・利用を行う。"
            ),
        },
        {
            "heading": "適用範囲",
            "content": "当社におけるAIの研究開発、導入、運用の全段階に適用する。",
        },
        {
            "heading": "基本方針",
            "content": (
                "1. 人間の尊厳の尊重: AIは人間の尊厳を損なう目的で使用しない\n"
                "2. 公平性・非差別: AIによる不当な差別を防止する\n"
                "3. 透明性・説明可能性: AIの判断根拠を可能な限り説明する\n"
                "4. プライバシーの尊重: 個人の情報とプライバシーを保護する\n"
                "5. 安全性・信頼性: AIシステムの安全な運用を確保する\n"
                "6. アカウンタビリティ: AIに関する説明責任を果たす"
            ),
        },
        {
            "heading": "具体的措置",
            "content": (
                "1. 高リスクAIシステムの導入・変更時には倫理審査を実施する\n"
                "2. 倫理審査委員会を設置し、定期的に審査を行う\n"
                "3. AIの利用に関して利害関係者との対話の機会を設ける\n"
                "4. 懸念や要望を把握し、方針に反映する"
            ),
        },
        {
            "heading": "責任体制",
            "content": (
                "1. AI倫理委員会: 多様なバックグラウンドの委員で構成\n"
                "2. 委員長: [役職名]\n"
                "3. 事務局: [担当部門]"
            ),
        },
        {
            "heading": "見直し・改善",
            "content": "本方針は社会の変化や技術の進歩に応じて随時見直す。",
        },
    ],
    "data_management": [
        {
            "heading": "目的",
            "content": (
                "本方針は、{org_name}がAI開発・運用に使用するデータの品質・安全性・"
                "プライバシーを確保するための管理基準を定める。"
            ),
        },
        {
            "heading": "適用範囲",
            "content": (
                "AI開発・運用に使用する全てのデータに適用する。\n"
                "学習データ、評価データ、運用データを含む。"
            ),
        },
        {
            "heading": "基本方針",
            "content": (
                "データを以下の4段階に分類し管理する：\n"
                "1. 公開データ: 一般公開されている情報\n"
                "2. 社内データ: 業務で生成された非公開情報\n"
                "3. 個人情報: 個人を特定できる情報\n"
                "4. 要配慮個人情報: 医療・信用情報等のセンシティブデータ"
            ),
        },
        {
            "heading": "具体的措置",
            "content": (
                "【品質管理】\n"
                "1. 学習データの品質基準を定め、定期的に評価する\n"
                "2. データの正確性・完全性・鮮度を維持する\n"
                "3. バイアスの検出と是正を継続的に行う\n\n"
                "【プライバシー保護】\n"
                "4. データ最小化の原則を遵守する\n"
                "5. 目的外利用を禁止する\n"
                "6. 適切な匿名化・仮名化措置を講じる\n"
                "7. プライバシー影響評価（PIA）を実施する\n\n"
                "【セキュリティ】\n"
                "8. データの暗号化（保存時・転送時）\n"
                "9. アクセス制御（最小権限の原則）\n"
                "10. 監査ログの記録\n"
                "11. データ廃棄手順の整備"
            ),
        },
        {
            "heading": "責任体制",
            "content": (
                "1. データ管理責任者: [役職名]\n"
                "2. 各データオーナー: データの品質と適切な利用を管理\n"
                "3. 情報セキュリティ部門: セキュリティ対策の実施"
            ),
        },
        {
            "heading": "見直し・改善",
            "content": "本方針は年1回以上見直し、法改正やインシデントに応じて改定する。",
        },
    ],
    "incident_response": [
        {
            "heading": "目的",
            "content": (
                "本手順書は、{org_name}が運用するAIシステムに関するインシデント発生時の"
                "対応手順を定め、被害の最小化と迅速な復旧を図ることを目的とする。"
            ),
        },
        {
            "heading": "適用範囲",
            "content": (
                "当社が運用する全てのAIシステムに関するインシデントに適用する。\n"
                "外部AIサービスに起因するインシデントも対象に含む。"
            ),
        },
        {
            "heading": "基本方針",
            "content": (
                "インシデントを以下の4種別に分類する：\n"
                "1. 重大インシデント: 人の生命・安全・権利に影響するもの\n"
                "2. セキュリティインシデント: データ漏洩、不正アクセス等\n"
                "3. 品質インシデント: AI出力の品質低下、バイアス検出等\n"
                "4. 運用インシデント: システム障害、性能劣化等"
            ),
        },
        {
            "heading": "具体的措置",
            "content": (
                "【対応フロー】\n"
                "1. 検知・報告: インシデントを検知した者は直ちに責任者に報告\n"
                "2. 初動対応: 被害拡大防止措置（AIシステムの停止を含む）\n"
                "3. 影響調査: 影響範囲と原因の調査\n"
                "4. 是正措置: 原因の除去と再発防止策の実施\n"
                "5. 報告: 経営層・関係者・当局への報告（必要に応じて）\n"
                "6. 記録: インシデント対応の全過程を記録・保存"
            ),
        },
        {
            "heading": "責任体制",
            "content": (
                "1. インシデント対応責任者: [役職名・連絡先]\n"
                "2. エスカレーションルール: [基準を記載]\n"
                "3. 外部連絡先: 監督官庁、セキュリティベンダー等"
            ),
        },
        {
            "heading": "見直し・改善",
            "content": (
                "1. 年1回以上のインシデント対応訓練を実施する\n"
                "2. 訓練結果を評価し、手順書の改善に反映する\n"
                "3. 実際のインシデント対応後は必ず振り返りを行い、手順を更新する"
            ),
        },
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_policy_types() -> list[dict]:
    """List available policy types with titles and descriptions.

    Returns:
        List of dicts with type, title, and description.
    """
    return [
        {"type": pt, "title": info["title"], "description": info["description"]}
        for pt, info in POLICY_TYPES.items()
    ]


def generate_policy(policy_type: str, org_name: str) -> PolicyDocument:
    """Generate a single policy document from template.

    Args:
        policy_type: One of ai_usage, risk_management, ethics,
                     data_management, incident_response.
        org_name: Organization name to embed in the template.

    Returns:
        PolicyDocument with markdown content.

    Raises:
        ValueError: If policy_type is unknown.
    """
    if policy_type not in POLICY_TYPES:
        valid = ", ".join(POLICY_TYPES.keys())
        raise ValueError(f"Unknown policy type: '{policy_type}'. Valid: {valid}")

    info = POLICY_TYPES[policy_type]
    sections = _TEMPLATES[policy_type]

    # Try Claude API for customization
    custom_content = _try_ai_customization(policy_type, org_name)
    if custom_content:
        return PolicyDocument(
            policy_type=policy_type,
            title=info["title"],
            content=custom_content,
            org_name=org_name,
        )

    # Fallback to template
    lines = [f"# {info['title']}", ""]
    lines.append(f"**組織名**: {org_name}")
    lines.append(f"**作成日**: {datetime.now(timezone.utc).strftime('%Y年%m月%d日')}")
    lines.append("")

    for section in sections:
        lines.append(f"## {section['heading']}")
        lines.append("")
        lines.append(section["content"].format(org_name=org_name))
        lines.append("")

    lines.append("---")
    lines.append(
        "*本文書はFaultRayにより自動生成されたテンプレートです。"
        "組織の実態に合わせて修正してください。*"
    )

    content = "\n".join(lines)

    return PolicyDocument(
        policy_type=policy_type,
        title=info["title"],
        content=content,
        org_name=org_name,
    )


def generate_all_policies(org_name: str) -> list[PolicyDocument]:
    """Generate all 5 policy documents.

    Args:
        org_name: Organization name.

    Returns:
        List of 5 PolicyDocument objects.
    """
    return [generate_policy(pt, org_name) for pt in POLICY_TYPES]


# ---------------------------------------------------------------------------
# AI customization (optional)
# ---------------------------------------------------------------------------


def _try_ai_customization(policy_type: str, org_name: str) -> str:
    """Try to use Claude API for customized policy generation.

    Returns empty string if API is unavailable.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-xxx"):
        return ""

    try:
        import anthropic  # type: ignore[import-untyped]

        client = anthropic.Anthropic(api_key=api_key)
        info = POLICY_TYPES[policy_type]

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"あなたはAIガバナンスの専門家です。\n"
                        f"「{org_name}」向けの「{info['title']}」を作成してください。\n\n"
                        f"以下のセクションを含めてください：\n"
                        f"1. 目的\n2. 適用範囲\n3. 基本方針\n"
                        f"4. 具体的措置\n5. 責任体制\n6. 見直し・改善\n\n"
                        f"Markdown形式で、日本語で作成してください。\n"
                        f"METI AI事業者ガイドライン v1.1 および ISO 42001 に準拠した内容としてください。"
                    ),
                }
            ],
        )
        return message.content[0].text  # type: ignore[union-attr]
    except Exception:
        return ""
