# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Japanese AI governance frameworks — data definitions.

Ported from JPGovAI. Three frameworks with cross-mapping:

1. METI AI事業者ガイドライン v1.1 — 10 principles, 28 requirements
2. ISO/IEC 42001:2023 AIMS — 7 clauses, 25 requirements
3. AI推進法 — 6 chapters, 15 requirements

Sources:
- https://www.meti.go.jp/shingikai/mono_info_service/ai_shakai_jisso/20240419_report.html
- https://www.soumu.go.jp/main_content/001002576.pdf (v1.1)
- ISO/IEC 42001:2023 Information technology — AI — Management system
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GovernanceFramework(str, Enum):
    """Supported AI governance frameworks."""

    METI_V1_1 = "meti-v1.1"
    ISO42001 = "iso42001"
    AI_PROMOTION = "ai-promotion"


# ---------------------------------------------------------------------------
# METI AI事業者ガイドライン v1.1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class METIRequirement:
    """Individual requirement from METI guidelines."""

    req_id: str
    category_id: str
    title: str
    description: str
    target_roles: list[str] = field(
        default_factory=lambda: ["developer", "provider", "user"]
    )
    risk_level: str = "all"  # all / high / limited


@dataclass(frozen=True)
class METICategory:
    """METI guideline principle category."""

    category_id: str
    title: str
    description: str
    requirements: list[METIRequirement] = field(default_factory=list)


METI_CATEGORIES: list[METICategory] = [
    METICategory(
        category_id="C01",
        title="人間中心（Human-Centric）",
        description="AIシステムの開発・提供・利用において、人間の尊厳と個人の自律を尊重し、人間が意思決定の主体であることを確保する。",
        requirements=[
            METIRequirement(
                req_id="C01-R01", category_id="C01",
                title="人間の尊厳・自律の尊重",
                description="AIの判断が人間の尊厳を損なわないよう、人間中心の原則を方針として定め、組織内に周知すること。",
            ),
            METIRequirement(
                req_id="C01-R02", category_id="C01",
                title="意思決定における人間の関与",
                description="AIの判断結果を最終的に人間が確認・判断できるプロセスを整備すること。特に高リスク領域では人間の介在を必須とすること。",
                risk_level="high",
            ),
            METIRequirement(
                req_id="C01-R03", category_id="C01",
                title="誤情報・偽情報への対処",
                description="AIが生成する情報の正確性を確認する仕組みを設け、誤情報・偽情報の拡散防止策を講じること。",
            ),
        ],
    ),
    METICategory(
        category_id="C02",
        title="安全性（Safety）",
        description="AIシステムが利害関係者の生命・身体・財産に危害を及ぼさないよう、適切な学習データの選定と安全な運用を確保する。",
        requirements=[
            METIRequirement(
                req_id="C02-R01", category_id="C02",
                title="リスクアセスメントの実施",
                description="AIシステムのリスクを特定・評価・軽減するためのリスクアセスメントを定期的に実施すること。",
            ),
            METIRequirement(
                req_id="C02-R02", category_id="C02",
                title="学習データの品質管理",
                description="学習データの品質（正確性・網羅性・偏りの有無）を管理し、不適切なデータによる危害を防止すること。",
                target_roles=["developer"],
            ),
            METIRequirement(
                req_id="C02-R03", category_id="C02",
                title="安全な運用・停止手順",
                description="AIシステムに異常が発生した場合の安全な停止手順、フォールバック手段を事前に定めること。",
            ),
        ],
    ),
    METICategory(
        category_id="C03",
        title="公平性（Fairness）",
        description="AIシステムが特定の集団に対して不当な差別を行わないよう配慮し、バイアスの評価と是正に努める。",
        requirements=[
            METIRequirement(
                req_id="C03-R01", category_id="C03",
                title="バイアス評価の実施",
                description="AIシステムの出力が特定の属性（性別・人種・年齢等）に基づく不当な差別を含まないか評価すること。",
            ),
            METIRequirement(
                req_id="C03-R02", category_id="C03",
                title="公平性基準の策定",
                description="利用文脈に応じた公平性の基準を定め、定期的にモニタリングすること。",
            ),
            METIRequirement(
                req_id="C03-R03", category_id="C03",
                title="差別的影響の是正措置",
                description="バイアスが検出された場合の是正手順を事前に定め、速やかに対応すること。",
            ),
        ],
    ),
    METICategory(
        category_id="C04",
        title="プライバシー保護（Privacy Protection）",
        description="AIシステムの開発・提供・利用において、個人情報・プライバシーの保護に努める。",
        requirements=[
            METIRequirement(
                req_id="C04-R01", category_id="C04",
                title="個人情報取扱方針の策定",
                description="AIに関する個人情報の取得・利用・提供・保管・削除に関する方針を策定し、公表すること。",
            ),
            METIRequirement(
                req_id="C04-R02", category_id="C04",
                title="プライバシー影響評価",
                description="AIシステムの導入前にプライバシー影響評価（PIA）を実施し、リスクを特定・軽減すること。",
            ),
            METIRequirement(
                req_id="C04-R03", category_id="C04",
                title="データ最小化・目的外利用禁止",
                description="必要最小限のデータのみを取り扱い、当初の目的以外での利用を行わないこと。",
            ),
        ],
    ),
    METICategory(
        category_id="C05",
        title="セキュリティ確保（Security）",
        description="AIシステムに対する不正な操作・アクセスによって意図しない動作変更や停止が生じないよう、セキュリティを確保する。",
        requirements=[
            METIRequirement(
                req_id="C05-R01", category_id="C05",
                title="セキュリティ対策の実施",
                description="AIシステムに対する攻撃（敵対的攻撃、データポイズニング等）への防御策を講じること。",
            ),
            METIRequirement(
                req_id="C05-R02", category_id="C05",
                title="脆弱性管理",
                description="AIシステムの脆弱性を定期的に評価し、発見された脆弱性に速やかに対処すること。",
            ),
            METIRequirement(
                req_id="C05-R03", category_id="C05",
                title="インシデント対応体制",
                description="セキュリティインシデント発生時の対応手順・連絡体制を事前に整備すること。",
            ),
        ],
    ),
    METICategory(
        category_id="C06",
        title="透明性（Transparency）",
        description="利害関係者に対して、技術的に可能な範囲で合理的な情報提供を行い、AIサービスの検証可能性を確保する。",
        requirements=[
            METIRequirement(
                req_id="C06-R01", category_id="C06",
                title="AI利用の明示",
                description="AIを利用していることを利害関係者に適切に開示すること。",
            ),
            METIRequirement(
                req_id="C06-R02", category_id="C06",
                title="判断根拠の説明",
                description="AIの判断結果について、技術的に可能な範囲で根拠を説明できるようにすること。",
            ),
            METIRequirement(
                req_id="C06-R03", category_id="C06",
                title="技術情報の文書化",
                description="AIシステムの技術仕様・学習データ・性能指標等を文書化し、必要に応じて開示できるようにすること。",
                target_roles=["developer", "provider"],
            ),
        ],
    ),
    METICategory(
        category_id="C07",
        title="アカウンタビリティ（Accountability）",
        description="AIシステムに関する責任の所在を明確にし、事実上・法律上の責任を果たす体制を整備する。",
        requirements=[
            METIRequirement(
                req_id="C07-R01", category_id="C07",
                title="責任者の指定",
                description="AIガバナンスに関する責任者を指定し、その権限と責任を明確にすること。",
            ),
            METIRequirement(
                req_id="C07-R02", category_id="C07",
                title="ガバナンス方針・体制の整備",
                description="AIの開発・提供・利用に関するガバナンス方針を策定し、実施体制を整備すること。",
            ),
            METIRequirement(
                req_id="C07-R03", category_id="C07",
                title="契約・SLAの整備",
                description="AI関連の取引において、責任分界・品質保証・免責等を契約やSLAで明確にすること。",
            ),
            METIRequirement(
                req_id="C07-R04", category_id="C07",
                title="ガバナンス記録の保持",
                description="ガバナンスに関する決定事項・実施記録を適切に保持し、監査可能な状態にすること。",
            ),
        ],
    ),
    METICategory(
        category_id="C08",
        title="教育・リテラシー（Education & Literacy）",
        description="AIシステムの正しい理解と適切な利用のために、必要な教育を提供する。",
        requirements=[
            METIRequirement(
                req_id="C08-R01", category_id="C08",
                title="従業員教育の実施",
                description="AIを扱う従業員に対して、AIの特性・限界・リスクに関する教育を定期的に実施すること。",
            ),
            METIRequirement(
                req_id="C08-R02", category_id="C08",
                title="利用者への情報提供",
                description="AIシステムの利用者に対して、適切な利用方法・注意事項を提供すること。",
                target_roles=["provider", "user"],
            ),
        ],
    ),
    METICategory(
        category_id="C09",
        title="公正競争の確保（Fair Competition）",
        description="AIを取り巻く公正な競争環境の維持に努める。",
        requirements=[
            METIRequirement(
                req_id="C09-R01", category_id="C09",
                title="公正競争への配慮",
                description="AIの開発・提供・利用において、不当な競争制限行為を行わないこと。",
            ),
            METIRequirement(
                req_id="C09-R02", category_id="C09",
                title="知的財産の尊重",
                description="AIの学習・利用において、他者の知的財産権を尊重すること。",
            ),
        ],
    ),
    METICategory(
        category_id="C10",
        title="イノベーション（Innovation）",
        description="社会全体のイノベーション促進に貢献するよう努める。",
        requirements=[
            METIRequirement(
                req_id="C10-R01", category_id="C10",
                title="イノベーション促進への貢献",
                description="AIの研究・開発・利用を通じて、社会課題の解決やイノベーション促進に貢献すること。",
            ),
            METIRequirement(
                req_id="C10-R02", category_id="C10",
                title="相互運用性・オープン性の確保",
                description="技術的な囲い込みを避け、相互運用性やオープン性の確保に努めること。",
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------
# METI Assessment Questions (25 questions)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class METIQuestion:
    """Self-assessment questionnaire question."""

    question_id: str
    category_id: str
    text: str
    options: list[str]
    scores: list[int]  # Score per option (0-4)
    requirement_ids: list[str]  # Related requirement IDs


METI_QUESTIONS: list[METIQuestion] = [
    METIQuestion("Q01", "C01", "AIの判断結果に対する最終的な人間の確認・承認プロセスはありますか？",
                 ["プロセスなし", "一部のAIシステムにのみ存在", "高リスク領域には存在", "全AIシステムに標準化されたプロセスがある", "定期的に見直し・改善されている"],
                 [0, 1, 2, 3, 4], ["C01-R01", "C01-R02"]),
    METIQuestion("Q02", "C01", "AIが生成する情報の正確性を検証する仕組みはありますか？",
                 ["仕組みなし", "担当者が個別に確認", "一部のシステムに自動検証あり", "全システムに検証プロセスあり", "継続的モニタリング＋改善サイクルあり"],
                 [0, 1, 2, 3, 4], ["C01-R03"]),
    METIQuestion("Q03", "C02", "AIシステムのリスクアセスメントを実施していますか？",
                 ["未実施", "導入時のみ実施", "年1回実施", "四半期ごとに実施", "継続的なリスクモニタリング体制あり"],
                 [0, 1, 2, 3, 4], ["C02-R01"]),
    METIQuestion("Q04", "C02", "学習データの品質管理プロセスはありますか？",
                 ["管理なし", "基本的なデータクレンジングのみ", "品質基準を策定済み", "定期的な品質評価を実施", "自動品質チェック＋人手レビュー体制あり"],
                 [0, 1, 2, 3, 4], ["C02-R02"]),
    METIQuestion("Q05", "C02", "AIシステムの異常時の安全停止手順は定められていますか？",
                 ["未策定", "口頭ベースの対応のみ", "手順書が存在する", "手順書＋定期訓練を実施", "自動フォールバック＋手動介入の二重体制"],
                 [0, 1, 2, 3, 4], ["C02-R03"]),
    METIQuestion("Q06", "C03", "AIシステムのバイアス評価を実施していますか？",
                 ["未実施", "問題指摘時のみ調査", "導入時に評価", "定期的な評価を実施", "継続的モニタリング＋自動アラートあり"],
                 [0, 1, 2, 3, 4], ["C03-R01", "C03-R02"]),
    METIQuestion("Q07", "C03", "バイアス検出時の是正手順は定められていますか？",
                 ["未策定", "個別対応", "基本方針がある", "詳細な是正手順＋責任者が明確", "是正＋再発防止＋報告の体制が確立"],
                 [0, 1, 2, 3, 4], ["C03-R03"]),
    METIQuestion("Q08", "C04", "AIに関する個人情報の取扱方針は策定・公表していますか？",
                 ["未策定", "一般的なプライバシーポリシーのみ", "AI固有の方針を策定中", "AI固有の方針を策定・社内周知済み", "策定・公表済み＋定期見直し"],
                 [0, 1, 2, 3, 4], ["C04-R01"]),
    METIQuestion("Q09", "C04", "AIシステム導入前にプライバシー影響評価（PIA）を実施していますか？",
                 ["未実施", "高リスクシステムのみ実施", "全システムで簡易評価", "全システムで詳細PIA実施", "PIA＋継続的プライバシーモニタリング"],
                 [0, 1, 2, 3, 4], ["C04-R02", "C04-R03"]),
    METIQuestion("Q10", "C05", "AIシステムに対するセキュリティ対策（敵対的攻撃対策等）を実施していますか？",
                 ["未実施", "一般的なIT対策のみ", "AI固有の脅威を考慮した対策あり", "敵対的攻撃テスト等を定期実施", "Red Team演習＋継続的脆弱性管理"],
                 [0, 1, 2, 3, 4], ["C05-R01", "C05-R02"]),
    METIQuestion("Q11", "C05", "AIセキュリティインシデント対応体制は整備されていますか？",
                 ["未整備", "一般的なインシデント対応のみ", "AI固有のインシデント対応手順あり", "手順＋定期訓練を実施", "24/7対応体制＋自動検知あり"],
                 [0, 1, 2, 3, 4], ["C05-R03"]),
    METIQuestion("Q12", "C06", "AIの利用を利害関係者に開示していますか？",
                 ["未開示", "問い合わせ時のみ回答", "利用規約等に記載", "積極的に開示し説明", "開示＋フィードバック受付体制あり"],
                 [0, 1, 2, 3, 4], ["C06-R01"]),
    METIQuestion("Q13", "C06", "AIの判断根拠を説明する仕組みはありますか？",
                 ["説明不可", "技術者が個別に説明可能", "一般利用者向けの説明ドキュメントあり", "システムが自動で根拠を提示", "説明可能AI（XAI）技術を導入済み"],
                 [0, 1, 2, 3, 4], ["C06-R02", "C06-R03"]),
    METIQuestion("Q14", "C07", "AIガバナンスの責任者は指定されていますか？",
                 ["未指定", "暗黙の担当者がいる", "正式に指定済み", "責任者＋専門チーム設置", "CAIO等のC-suite＋専門委員会あり"],
                 [0, 1, 2, 3, 4], ["C07-R01"]),
    METIQuestion("Q15", "C07", "AIガバナンス方針・体制は整備されていますか？",
                 ["未整備", "検討中", "基本方針を策定済み", "方針＋実施体制＋監査体制あり", "PDCA＋外部監査＋定期報告体制"],
                 [0, 1, 2, 3, 4], ["C07-R02", "C07-R03", "C07-R04"]),
    METIQuestion("Q16", "C08", "AI関連の従業員教育を実施していますか？",
                 ["未実施", "希望者のみ受講可", "AI関連部署のみ必須", "全従業員に年1回以上実施", "役割別教育＋効果測定＋継続改善"],
                 [0, 1, 2, 3, 4], ["C08-R01"]),
    METIQuestion("Q17", "C08", "AIシステムの利用者に適切な利用方法を提供していますか？",
                 ["未提供", "基本的なマニュアルのみ", "利用ガイドライン＋FAQ", "対話型サポート＋定期研修", "パーソナライズされたガイダンス＋フィードバック収集"],
                 [0, 1, 2, 3, 4], ["C08-R02"]),
    METIQuestion("Q18", "C09", "AI利用における公正競争への配慮は行っていますか？",
                 ["配慮なし", "法務部門が必要に応じ確認", "公正競争方針を策定", "方針＋定期レビュー", "競争法コンプライアンス体制＋外部監査"],
                 [0, 1, 2, 3, 4], ["C09-R01", "C09-R02"]),
    METIQuestion("Q19", "C10", "AIを通じたイノベーション促進への取り組みはありますか？",
                 ["取り組みなし", "個別プロジェクトのみ", "組織的なAI活用推進", "社外連携・オープンイノベーション", "エコシステム構築＋社会課題解決への貢献"],
                 [0, 1, 2, 3, 4], ["C10-R01", "C10-R02"]),
    METIQuestion("Q20", "C07", "AIに関するガバナンス記録（意思決定記録・実施記録等）を保持していますか？",
                 ["記録なし", "メールや議事録に散在", "統一的な記録管理を開始", "体系的な記録管理＋検索可能", "改竄防止＋監査証跡＋長期保存体制"],
                 [0, 1, 2, 3, 4], ["C07-R04"]),
    METIQuestion("Q21", "C02", "貴社のAIの主な用途は何ですか？（最もリスクの高いものを選択）",
                 ["社内業務効率化のみ", "コンテンツ生成・クリエイティブ支援", "顧客対応・サービス提供", "意思決定支援（審査・評価等）", "自律的意思決定（自動取引・自動判定等）"],
                 [0, 1, 2, 3, 4], ["C01-R02", "C02-R01"]),
    METIQuestion("Q22", "C04", "AIシステムが扱うデータの種類は？（最もセンシティブなものを選択）",
                 ["公開情報のみ", "社内業務データ", "顧客の非個人情報", "個人情報（氏名・連絡先等）", "要配慮個人情報（医療・信用情報等）"],
                 [0, 1, 2, 3, 4], ["C04-R01", "C04-R02", "C04-R03"]),
    METIQuestion("Q23", "C05", "外部AIサービス（API）のセキュリティ管理はどの程度実施していますか？",
                 ["管理なし", "サービス利用規約の確認のみ", "データ送信内容の制限ルールあり", "API利用のセキュリティガイドライン策定済み", "DLP＋モニタリング＋定期監査体制あり"],
                 [0, 1, 2, 3, 4], ["C05-R01", "C05-R02"]),
    METIQuestion("Q24", "C06", "AIシステムの技術仕様・性能指標の文書化はどの程度行っていますか？",
                 ["文書化なし", "開発メモレベル", "基本的な技術文書あり", "モデルカード等の標準フォーマットで管理", "バージョン管理＋変更履歴＋公開体制あり"],
                 [0, 1, 2, 3, 4], ["C06-R03"]),
    METIQuestion("Q25", "C07", "AIに関する契約・SLAの整備状況は？",
                 ["未整備", "一般的な業務委託契約のみ", "AI固有の条項を追加検討中", "AI固有の責任分界・品質保証条項あり", "標準テンプレート＋法務レビュー＋定期更新"],
                 [0, 1, 2, 3, 4], ["C07-R03"]),
]


# ---------------------------------------------------------------------------
# ISO/IEC 42001:2023 AIMS
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ISORequirement:
    """ISO 42001 individual requirement."""

    req_id: str
    clause: str
    title: str
    description: str
    meti_mapping: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ISOClause:
    """ISO 42001 clause."""

    clause_id: str
    title: str
    description: str
    requirements: list[ISORequirement] = field(default_factory=list)


ISO_CLAUSES: list[ISOClause] = [
    ISOClause(
        clause_id="4", title="組織の状況（Context of the Organization）",
        description="AIマネジメントシステムに関連する組織の状況を理解し、利害関係者のニーズと期待を特定する。",
        requirements=[
            ISORequirement("ISO-4.1", "4.1", "組織とその状況の理解",
                           "AIマネジメントシステムの目的に関連する外部・内部の課題を決定すること。", ["C07-R02"]),
            ISORequirement("ISO-4.2", "4.2", "利害関係者のニーズ及び期待の理解",
                           "AIマネジメントシステムに関連する利害関係者と、その要求事項を特定すること。", ["C01-R01", "C06-R01"]),
            ISORequirement("ISO-4.3", "4.3", "AIマネジメントシステムの適用範囲の決定",
                           "AIMSの適用範囲を決定し、文書化すること。", ["C07-R02"]),
            ISORequirement("ISO-4.4", "4.4", "AIマネジメントシステム",
                           "ISO 42001の要求事項に従い、AIMSを確立・実施・維持・継続的に改善すること。", ["C07-R02", "C07-R04"]),
        ],
    ),
    ISOClause(
        clause_id="5", title="リーダーシップ（Leadership）",
        description="トップマネジメントがAIMSに対するリーダーシップとコミットメントを示す。",
        requirements=[
            ISORequirement("ISO-5.1", "5.1", "リーダーシップ及びコミットメント",
                           "トップマネジメントがAIMSに対するリーダーシップ及びコミットメントを実証すること。", ["C07-R01", "C07-R02"]),
            ISORequirement("ISO-5.2", "5.2", "AI方針",
                           "AIに関する方針を確立し、伝達し、利用可能な状態にすること。", ["C01-R01", "C07-R02"]),
            ISORequirement("ISO-5.3", "5.3", "組織の役割、責任及び権限",
                           "AIMS関連の役割に対して責任及び権限を割り当て、伝達すること。", ["C07-R01"]),
        ],
    ),
    ISOClause(
        clause_id="6", title="計画（Planning）",
        description="AIMSのリスク及び機会への取組み、AI目的の設定とその達成計画。",
        requirements=[
            ISORequirement("ISO-6.1", "6.1", "リスク及び機会への取組み",
                           "AIに関連するリスク及び機会を特定し、それらに対処するための計画を策定すること。", ["C02-R01"]),
            ISORequirement("ISO-6.1.2", "6.1.2", "AIリスクアセスメント",
                           "AIシステムに関するリスクアセスメントのプロセスを定義し、実施すること。", ["C02-R01", "C02-R02"]),
            ISORequirement("ISO-6.1.3", "6.1.3", "AIリスク対応",
                           "リスクアセスメントの結果に基づき、リスク対応の選択肢を選び、実施すること。", ["C02-R01", "C02-R03"]),
            ISORequirement("ISO-6.2", "6.2", "AI目的及びそれを達成するための計画策定",
                           "AIに関する測定可能な目的を設定し、達成計画を策定すること。", ["C10-R01"]),
        ],
    ),
    ISOClause(
        clause_id="7", title="支援（Support）",
        description="AIMSの確立・実施・維持・改善に必要な資源、力量、認識、コミュニケーション、文書化。",
        requirements=[
            ISORequirement("ISO-7.1", "7.1", "資源",
                           "AIMSに必要な資源を決定し、提供すること。", ["C07-R02"]),
            ISORequirement("ISO-7.2", "7.2", "力量",
                           "AIMS関連の業務を行う人々に必要な力量を決定し、確保すること。", ["C08-R01"]),
            ISORequirement("ISO-7.3", "7.3", "認識",
                           "関連する人々がAI方針、自らの貢献、不適合の影響を認識すること。", ["C08-R01", "C08-R02"]),
            ISORequirement("ISO-7.4", "7.4", "コミュニケーション",
                           "AIMSに関する内部及び外部のコミュニケーションを計画すること。", ["C06-R01"]),
            ISORequirement("ISO-7.5", "7.5", "文書化した情報",
                           "AIMSで必要な文書化した情報を作成・更新・管理すること。", ["C06-R03", "C07-R04"]),
        ],
    ),
    ISOClause(
        clause_id="8", title="運用（Operation）",
        description="AIMSの要求事項を満たすために必要なプロセスの計画・実施・管理。",
        requirements=[
            ISORequirement("ISO-8.1", "8.1", "運用の計画及び管理",
                           "AIMSの要求事項を満たすために必要なプロセスを計画・実施・管理すること。", ["C07-R02"]),
            ISORequirement("ISO-8.2", "8.2", "AIリスクアセスメント（実施）",
                           "計画した間隔またはリスクの変化が生じた場合にAIリスクアセスメントを実施すること。", ["C02-R01"]),
            ISORequirement("ISO-8.3", "8.3", "AIリスク対応（実施）",
                           "AIリスク対応計画を実施すること。", ["C02-R03", "C05-R01"]),
            ISORequirement("ISO-8.4", "8.4", "AIシステム影響評価",
                           "AIシステムが個人、グループ、社会に与える影響を評価すること。", ["C01-R01", "C03-R01", "C04-R02"]),
        ],
    ),
    ISOClause(
        clause_id="9", title="パフォーマンス評価（Performance Evaluation）",
        description="AIMSのパフォーマンス及び有効性の監視・測定・分析・評価。",
        requirements=[
            ISORequirement("ISO-9.1", "9.1", "監視、測定、分析及び評価",
                           "AIMSのパフォーマンスを監視・測定・分析・評価すること。", ["C03-R02", "C07-R04"]),
            ISORequirement("ISO-9.2", "9.2", "内部監査",
                           "計画した間隔でAIMSの内部監査を実施すること。", ["C07-R04"]),
            ISORequirement("ISO-9.3", "9.3", "マネジメントレビュー",
                           "計画した間隔でAIMSのマネジメントレビューを実施すること。", ["C07-R02"]),
        ],
    ),
    ISOClause(
        clause_id="10", title="改善（Improvement）",
        description="不適合への対処と継続的改善。",
        requirements=[
            ISORequirement("ISO-10.1", "10.1", "不適合及び是正処置",
                           "不適合が発生した場合、是正処置を講じること。", ["C03-R03", "C05-R03"]),
            ISORequirement("ISO-10.2", "10.2", "継続的改善",
                           "AIMSの適切性、妥当性及び有効性を継続的に改善すること。", ["C10-R01"]),
        ],
    ),
]


# ---------------------------------------------------------------------------
# AI推進法 (AI Promotion Act)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActRequirement:
    """AI Promotion Act individual requirement."""

    req_id: str
    article: str
    title: str
    description: str
    obligation_type: str = "effort"  # "mandatory" / "effort"
    meti_mapping: list[str] = field(default_factory=list)
    iso_mapping: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ActChapter:
    """AI Promotion Act chapter."""

    chapter_id: str
    title: str
    description: str
    requirements: list[ActRequirement] = field(default_factory=list)


ACT_CHAPTERS: list[ActChapter] = [
    ActChapter(
        chapter_id="CH1", title="総則", description="法律の目的、基本理念、定義等。",
        requirements=[
            ActRequirement("APA-01", "第3条", "基本理念の遵守",
                           "AI関連技術の研究開発・活用にあたり、人間の尊厳の尊重、多様性の確保、持続可能な社会の実現等の基本理念を遵守すること。",
                           "mandatory", ["C01-R01"], ["ISO-5.2"]),
        ],
    ),
    ActChapter(
        chapter_id="CH2", title="AI推進基本方針", description="政府によるAI推進基本方針の策定。事業者の役割と責務。",
        requirements=[
            ActRequirement("APA-02", "第10条", "事業者の責務（安全性確保）",
                           "AI事業者は、AIシステムの安全性を確保するために必要な措置を講じるよう努めること。",
                           "effort", ["C02-R01", "C02-R03"], ["ISO-6.1", "ISO-8.3"]),
            ActRequirement("APA-03", "第10条", "事業者の責務（透明性確保）",
                           "AIの利用に関する透明性を確保し、利害関係者に対して適切な情報提供を行うよう努めること。",
                           "effort", ["C06-R01", "C06-R02"], ["ISO-7.4"]),
            ActRequirement("APA-04", "第10条", "事業者の責務（公平性確保）",
                           "AIの利用に際し、不当な差別が生じないよう配慮すること。",
                           "effort", ["C03-R01", "C03-R02"], ["ISO-8.4"]),
        ],
    ),
    ActChapter(
        chapter_id="CH3", title="安全・安心の確保", description="高リスクAIに対する安全性の確保措置。",
        requirements=[
            ActRequirement("APA-05", "第15条", "リスク管理体制の整備",
                           "特定AI（高リスクAI）を取り扱う事業者は、リスク管理体制を整備し、定期的にリスク評価を行うこと。",
                           "mandatory", ["C02-R01", "C02-R02"], ["ISO-6.1.2", "ISO-8.2"]),
            ActRequirement("APA-06", "第16条", "個人情報等の適正な取扱い",
                           "AI利用における個人情報の取扱いについて、個人情報保護法に加え、AI固有のリスクに対応する措置を講じること。",
                           "mandatory", ["C04-R01", "C04-R02", "C04-R03"], ["ISO-8.4"]),
            ActRequirement("APA-07", "第17条", "セキュリティ対策の実施",
                           "AIシステムに対するサイバーセキュリティ対策を実施し、脆弱性の管理とインシデント対応体制を整備すること。",
                           "mandatory", ["C05-R01", "C05-R02", "C05-R03"], ["ISO-8.3"]),
            ActRequirement("APA-08", "第18条", "インシデント報告義務",
                           "重大なAIインシデントが発生した場合、所管大臣に報告すること。",
                           "mandatory", ["C05-R03"], ["ISO-10.1"]),
        ],
    ),
    ActChapter(
        chapter_id="CH4", title="人材育成・リテラシー", description="AI人材の育成とAIリテラシーの向上。",
        requirements=[
            ActRequirement("APA-09", "第22条", "AI人材の育成",
                           "従業員に対してAIの適切な利用に関する教育・研修を実施すること。",
                           "effort", ["C08-R01"], ["ISO-7.2", "ISO-7.3"]),
            ActRequirement("APA-10", "第23条", "AIリテラシーの向上",
                           "AIサービスの利用者に対して、適切な利用方法等の情報提供を行うこと。",
                           "effort", ["C08-R02"], ["ISO-7.3"]),
        ],
    ),
    ActChapter(
        chapter_id="CH5", title="ガバナンス", description="AI利活用に関するガバナンス体制の整備。",
        requirements=[
            ActRequirement("APA-11", "第28条", "AIガバナンス体制の整備",
                           "AIの開発・提供・利用に関するガバナンス体制を整備し、内部統制を確保すること。",
                           "effort", ["C07-R01", "C07-R02"], ["ISO-5.1", "ISO-5.3"]),
            ActRequirement("APA-12", "第29条", "記録の保持・監査対応",
                           "AIシステムの運用記録を適切に保持し、監査に対応できる体制を整備すること。",
                           "effort", ["C07-R04"], ["ISO-7.5", "ISO-9.2"]),
        ],
    ),
    ActChapter(
        chapter_id="CH6", title="イノベーション推進", description="AI技術の研究開発及び活用の推進。",
        requirements=[
            ActRequirement("APA-13", "第32条", "知的財産権の保護",
                           "AI開発・利用における知的財産権の保護に配慮すること。",
                           "effort", ["C09-R02"], []),
            ActRequirement("APA-14", "第33条", "公正競争の確保",
                           "AI利活用における公正な競争環境の維持に努めること。",
                           "effort", ["C09-R01"], []),
            ActRequirement("APA-15", "第35条", "国際連携・相互運用性",
                           "国際的なAIガバナンスの枠組みとの整合性を確保し、相互運用性に配慮すること。",
                           "effort", ["C10-R02"], []),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Cross-mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrossMappingEntry:
    """Cross-framework mapping entry."""

    theme_id: str
    theme: str
    description: str
    meti_ids: list[str] = field(default_factory=list)
    iso_ids: list[str] = field(default_factory=list)
    act_ids: list[str] = field(default_factory=list)


CROSS_MAPPING: list[CrossMappingEntry] = [
    CrossMappingEntry("CM-01", "ガバナンス体制の整備", "AIガバナンスの方針・体制・責任者を確立する。",
                      ["C07-R01", "C07-R02"], ["ISO-5.1", "ISO-5.2", "ISO-5.3"], ["APA-11"]),
    CrossMappingEntry("CM-02", "リスク管理", "AIリスクの特定・評価・対応・モニタリングを行う。",
                      ["C02-R01", "C02-R03"], ["ISO-6.1", "ISO-6.1.2", "ISO-6.1.3", "ISO-8.2", "ISO-8.3"], ["APA-02", "APA-05"]),
    CrossMappingEntry("CM-03", "データ品質管理", "学習データの品質・代表性・バイアスを管理する。",
                      ["C02-R02"], ["ISO-6.1.2"], ["APA-05"]),
    CrossMappingEntry("CM-04", "公平性・バイアス対策", "AIによる不当な差別を防止し、公平性を確保する。",
                      ["C03-R01", "C03-R02", "C03-R03"], ["ISO-8.4"], ["APA-04"]),
    CrossMappingEntry("CM-05", "透明性・説明可能性", "AI利用の開示と判断根拠の説明を行う。",
                      ["C06-R01", "C06-R02", "C06-R03"], ["ISO-7.4", "ISO-7.5"], ["APA-03"]),
    CrossMappingEntry("CM-06", "プライバシー保護", "個人情報の適正な取扱いとプライバシー影響評価を行う。",
                      ["C04-R01", "C04-R02", "C04-R03"], ["ISO-8.4"], ["APA-06"]),
    CrossMappingEntry("CM-07", "セキュリティ対策", "AIシステムのサイバーセキュリティと堅牢性を確保する。",
                      ["C05-R01", "C05-R02"], ["ISO-8.3"], ["APA-07"]),
    CrossMappingEntry("CM-08", "インシデント対応", "AIインシデントの検出・対応・報告体制を整備する。",
                      ["C05-R03"], ["ISO-10.1"], ["APA-08"]),
    CrossMappingEntry("CM-09", "人間による監視", "AIの判断に対する人間の最終確認・介入を確保する。",
                      ["C01-R02"], ["ISO-8.4"], ["APA-01"]),
    CrossMappingEntry("CM-10", "文書化・記録管理", "技術文書、運用記録、監査証跡を適切に管理する。",
                      ["C06-R03", "C07-R04"], ["ISO-7.5", "ISO-9.2"], ["APA-12"]),
    CrossMappingEntry("CM-11", "教育・リテラシー", "AI関連の教育・訓練を実施し、リテラシーを向上させる。",
                      ["C08-R01", "C08-R02"], ["ISO-7.2", "ISO-7.3"], ["APA-09", "APA-10"]),
    CrossMappingEntry("CM-12", "影響評価", "AIシステムが個人・社会に与える影響を評価する。",
                      ["C01-R01", "C04-R02"], ["ISO-8.4"], ["APA-04"]),
    CrossMappingEntry("CM-13", "継続的改善・モニタリング", "AIガバナンスの継続的な改善とパフォーマンスモニタリングを行う。",
                      ["C10-R01"], ["ISO-9.1", "ISO-10.2"], []),
    CrossMappingEntry("CM-14", "サプライチェーン・ベンダー管理", "AIに関するサードパーティ・サプライチェーンのリスクを管理する。",
                      ["C07-R03"], ["ISO-8.1"], []),
    CrossMappingEntry("CM-15", "安全な運用・停止手順", "AIシステムの異常時の安全停止・フォールバック手順を整備する。",
                      ["C02-R03"], ["ISO-8.3"], ["APA-02"]),
]


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def all_meti_requirements() -> list[METIRequirement]:
    """Return all METI requirements as a flat list."""
    return [r for c in METI_CATEGORIES for r in c.requirements]


def all_iso_requirements() -> list[ISORequirement]:
    """Return all ISO 42001 requirements as a flat list."""
    return [r for c in ISO_CLAUSES for r in c.requirements]


def all_act_requirements() -> list[ActRequirement]:
    """Return all AI Promotion Act requirements as a flat list."""
    return [r for c in ACT_CHAPTERS for r in c.requirements]


def get_meti_to_iso_mapping() -> dict[str, list[str]]:
    """METI requirement ID -> ISO requirement IDs mapping."""
    mapping: dict[str, list[str]] = {}
    for req in all_iso_requirements():
        for meti_id in req.meti_mapping:
            mapping.setdefault(meti_id, []).append(req.req_id)
    return mapping


def get_meti_to_act_mapping() -> dict[str, list[str]]:
    """METI requirement ID -> AI Promotion Act requirement IDs mapping."""
    mapping: dict[str, list[str]] = {}
    for req in all_act_requirements():
        for meti_id in req.meti_mapping:
            mapping.setdefault(meti_id, []).append(req.req_id)
    return mapping


def get_frameworks_for_meti_requirement(meti_id: str) -> dict[str, list[str]]:
    """Return ISO and Act IDs that map to a given METI requirement."""
    result: dict[str, list[str]] = {"iso": [], "act": []}
    for entry in CROSS_MAPPING:
        if meti_id in entry.meti_ids:
            result["iso"].extend(entry.iso_ids)
            result["act"].extend(entry.act_ids)
    for key in result:
        result[key] = sorted(set(result[key]))
    return result


def get_coverage_matrix() -> dict[str, dict[str, list[str]]]:
    """Return the full cross-mapping coverage matrix.

    Returns:
        {theme_id: {"theme": [name], "meti": [...], "iso": [...], "act": [...]}}
    """
    matrix: dict[str, dict[str, list[str]]] = {}
    for entry in CROSS_MAPPING:
        matrix[entry.theme_id] = {
            "theme": [entry.theme],
            "meti": list(entry.meti_ids),
            "iso": list(entry.iso_ids),
            "act": list(entry.act_ids),
        }
    return matrix
