# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""AI Governance self-assessment engine.

Provides 25-question maturity assessment, scoring, gap analysis,
and improvement recommendations based on METI AI事業者ガイドライン v1.1.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from faultray.governance.frameworks import (
    METI_CATEGORIES,
    METI_QUESTIONS,
    GovernanceFramework,
    METIQuestion,
    all_iso_requirements,
    all_act_requirements,
    all_meti_requirements,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CategoryScore:
    """Score for a single governance category."""

    category_id: str
    category_title: str
    score: float  # 0.0 - 4.0 (raw average)
    score_percent: float  # 0 - 100
    maturity_level: int  # 1-5
    question_count: int
    gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RequirementScore:
    """Score for a single requirement (0-100)."""

    req_id: str
    title: str
    score: float  # 0-100
    framework: GovernanceFramework
    gaps: list[str] = field(default_factory=list)


@dataclass
class AssessmentResult:
    """Complete governance assessment result."""

    overall_score: float  # 0-100
    maturity_level: int  # 1-5
    category_scores: list[CategoryScore] = field(default_factory=list)
    requirement_scores: list[RequirementScore] = field(default_factory=list)
    top_gaps: list[str] = field(default_factory=list)
    top_recommendations: list[str] = field(default_factory=list)
    framework_coverage: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Maturity level helpers
# ---------------------------------------------------------------------------

MATURITY_LABELS: dict[int, str] = {
    1: "初期段階 (Ad-hoc)",
    2: "基礎段階 (Basic)",
    3: "定義段階 (Defined)",
    4: "管理段階 (Managed)",
    5: "最適化段階 (Optimized)",
}


def _score_to_maturity(score: float) -> int:
    """Convert raw score (0-4) to maturity level (1-5)."""
    if score < 0.8:
        return 1
    elif score < 1.6:
        return 2
    elif score < 2.4:
        return 3
    elif score < 3.2:
        return 4
    else:
        return 5


def _raw_to_percent(score: float) -> float:
    """Convert raw score (0-4) to percentage (0-100)."""
    return round(score / 4.0 * 100.0, 1)


# ---------------------------------------------------------------------------
# Recommendation database
# ---------------------------------------------------------------------------

_CATEGORY_RECOMMENDATIONS: dict[str, dict[int, str]] = {
    "C01": {
        1: "人間中心の原則について組織方針を策定し、全AIシステムに適用する体制を構築してください。",
        2: "高リスクAI領域での人間の介在プロセスを明確化してください。",
        3: "AIが生成する情報の検証プロセスを体系化し、全システムに展開してください。",
    },
    "C02": {
        1: "AIリスクアセスメントの基本フレームワークを導入してください。",
        2: "学習データ品質管理プロセスを確立し、定期的な品質評価を開始してください。",
        3: "安全停止手順の文書化と定期訓練を実施してください。",
    },
    "C03": {
        1: "バイアス評価の基本プロセスを導入してください。",
        2: "公平性基準を策定し、定期的なモニタリングを開始してください。",
        3: "バイアス是正手順を文書化し、責任者を明確にしてください。",
    },
    "C04": {
        1: "AI固有の個人情報取扱方針を策定してください。",
        2: "全AIシステムにプライバシー影響評価（PIA）を実施してください。",
        3: "データ最小化の原則を全システムに適用してください。",
    },
    "C05": {
        1: "AI固有のセキュリティ対策（敵対的攻撃対策等）を導入してください。",
        2: "脆弱性管理プロセスを確立し、定期的な評価を開始してください。",
        3: "AIインシデント対応体制を整備し、定期訓練を実施してください。",
    },
    "C06": {
        1: "AI利用の開示方針を策定し、利害関係者に情報提供を開始してください。",
        2: "AI判断根拠の説明機能を実装してください。",
        3: "技術文書の標準化とバージョン管理体制を構築してください。",
    },
    "C07": {
        1: "AIガバナンス責任者を正式に指定し、権限と責任を明確にしてください。",
        2: "ガバナンス方針を策定し、実施体制を整備してください。",
        3: "ガバナンス記録の保持と監査対応体制を確立してください。",
    },
    "C08": {
        1: "AI関連の従業員教育プログラムを導入してください。",
        2: "利用者向けのAI利用ガイドラインを整備してください。",
    },
    "C09": {
        1: "AI利用における公正競争方針を策定してください。",
        2: "知的財産権に関するレビュープロセスを導入してください。",
    },
    "C10": {
        1: "組織的なAI活用推進体制を構築してください。",
        2: "相互運用性とオープン性を考慮したAI戦略を策定してください。",
    },
}


# ---------------------------------------------------------------------------
# Assessor
# ---------------------------------------------------------------------------


class GovernanceAssessor:
    """AI governance maturity assessor.

    Accepts questionnaire answers and produces a comprehensive
    assessment result with scores, gap analysis, and recommendations.
    """

    def __init__(self) -> None:
        self._question_map: dict[str, METIQuestion] = {
            q.question_id: q for q in METI_QUESTIONS
        }
        self._cat_title_map: dict[str, str] = {
            c.category_id: c.title for c in METI_CATEGORIES
        }

    def assess(self, answers: dict[str, int]) -> AssessmentResult:
        """Run the full governance assessment.

        Args:
            answers: mapping of question_id -> selected_index (0-4).
                     Missing questions are scored as 0.

        Returns:
            AssessmentResult with scores, gaps, and recommendations.
        """
        # Collect per-category raw scores
        cat_raw: dict[str, list[int]] = defaultdict(list)

        for q in METI_QUESTIONS:
            idx = answers.get(q.question_id, 0)
            idx = max(0, min(idx, len(q.scores) - 1))
            score = q.scores[idx]
            cat_raw[q.category_id].append(score)

        # Build category scores
        category_scores: list[CategoryScore] = []
        all_avgs: list[float] = []

        for cat_id in sorted(cat_raw.keys()):
            scores = cat_raw[cat_id]
            avg = sum(scores) / len(scores) if scores else 0.0
            all_avgs.append(avg)
            maturity = _score_to_maturity(avg)
            pct = _raw_to_percent(avg)

            # Gaps and recommendations
            gaps: list[str] = []
            recs: list[str] = []
            if maturity < 3:
                cat_title = self._cat_title_map.get(cat_id, cat_id)
                gaps.append(f"{cat_title}: 成熟度レベル{maturity} — 改善が必要")
            cat_recs = _CATEGORY_RECOMMENDATIONS.get(cat_id, {})
            for level, rec in sorted(cat_recs.items()):
                if maturity < level + 1:
                    recs.append(rec)

            category_scores.append(CategoryScore(
                category_id=cat_id,
                category_title=self._cat_title_map.get(cat_id, cat_id),
                score=round(avg, 2),
                score_percent=pct,
                maturity_level=maturity,
                question_count=len(scores),
                gaps=gaps,
                recommendations=recs,
            ))

        overall_raw = sum(all_avgs) / len(all_avgs) if all_avgs else 0.0
        overall_pct = _raw_to_percent(overall_raw)
        overall_maturity = _score_to_maturity(overall_raw)

        # Requirement-level scores (METI)
        req_scores = self._compute_requirement_scores(answers)

        # Derive ISO/Act coverage from METI scores
        framework_coverage = self._compute_framework_coverage(req_scores)

        # Top gaps and recommendations
        top_gaps: list[str] = []
        top_recs: list[str] = []
        for cs in sorted(category_scores, key=lambda c: c.score):
            top_gaps.extend(cs.gaps)
            top_recs.extend(cs.recommendations)

        return AssessmentResult(
            overall_score=overall_pct,
            maturity_level=overall_maturity,
            category_scores=category_scores,
            requirement_scores=req_scores,
            top_gaps=top_gaps[:10],
            top_recommendations=top_recs[:10],
            framework_coverage=framework_coverage,
        )

    def assess_auto(self, has_monitoring: bool = False, has_auth: bool = False,
                    has_encryption: bool = False, has_dr: bool = False,
                    has_logging: bool = False) -> AssessmentResult:
        """Auto-assess governance posture from infrastructure signals.

        Maps infrastructure capabilities to approximate questionnaire answers.
        """
        answers: dict[str, int] = {}

        # Security (C05) - Q10, Q11, Q23
        sec_level = sum([has_auth, has_encryption, has_monitoring])
        answers["Q10"] = min(sec_level, 4)
        answers["Q11"] = 2 if has_monitoring else 0
        answers["Q23"] = 2 if has_encryption else 0

        # Safety (C02) - Q03, Q05
        answers["Q03"] = 2 if has_monitoring else 0
        answers["Q05"] = 2 if has_dr else 0

        # Transparency (C06) - Q12, Q13, Q24
        answers["Q12"] = 1  # Minimal by default
        answers["Q13"] = 1 if has_logging else 0
        answers["Q24"] = 1 if has_logging else 0

        # Accountability (C07) - Q14, Q15, Q20, Q25
        answers["Q14"] = 1  # Assume minimal
        answers["Q15"] = 1
        answers["Q20"] = 2 if has_logging else 0
        answers["Q25"] = 1

        return self.assess(answers)

    def _compute_requirement_scores(
        self, answers: dict[str, int],
    ) -> list[RequirementScore]:
        """Compute per-requirement scores from questionnaire answers."""
        # Map requirement_id -> list of raw scores from related questions
        req_raw: dict[str, list[int]] = defaultdict(list)

        for q in METI_QUESTIONS:
            idx = answers.get(q.question_id, 0)
            idx = max(0, min(idx, len(q.scores) - 1))
            score = q.scores[idx]
            for req_id in q.requirement_ids:
                req_raw[req_id].append(score)

        req_title_map = {r.req_id: r.title for r in all_meti_requirements()}

        result: list[RequirementScore] = []
        for req_id in sorted(req_raw.keys()):
            scores = req_raw[req_id]
            avg = sum(scores) / len(scores) if scores else 0.0
            pct = _raw_to_percent(avg)
            gaps: list[str] = []
            if pct < 50.0:
                gaps.append(f"{req_id} ({req_title_map.get(req_id, '')}): スコア{pct}% — 要改善")
            result.append(RequirementScore(
                req_id=req_id,
                title=req_title_map.get(req_id, req_id),
                score=pct,
                framework=GovernanceFramework.METI_V1_1,
                gaps=gaps,
            ))

        return result

    def _compute_framework_coverage(
        self, meti_scores: list[RequirementScore],
    ) -> dict[str, float]:
        """Derive ISO/Act coverage percentage from METI requirement scores."""
        meti_score_map = {rs.req_id: rs.score for rs in meti_scores}

        # ISO coverage
        iso_scores: list[float] = []
        for iso_req in all_iso_requirements():
            mapped_scores = [meti_score_map.get(mid, 0.0) for mid in iso_req.meti_mapping]
            if mapped_scores:
                iso_scores.append(sum(mapped_scores) / len(mapped_scores))

        # Act coverage
        act_scores: list[float] = []
        for act_req in all_act_requirements():
            mapped_scores = [meti_score_map.get(mid, 0.0) for mid in act_req.meti_mapping]
            if mapped_scores:
                act_scores.append(sum(mapped_scores) / len(mapped_scores))

        # METI overall
        meti_avg = sum(rs.score for rs in meti_scores) / len(meti_scores) if meti_scores else 0.0

        return {
            GovernanceFramework.METI_V1_1.value: round(meti_avg, 1),
            GovernanceFramework.ISO42001.value: round(
                sum(iso_scores) / len(iso_scores) if iso_scores else 0.0, 1
            ),
            GovernanceFramework.AI_PROMOTION.value: round(
                sum(act_scores) / len(act_scores) if act_scores else 0.0, 1
            ),
        }
