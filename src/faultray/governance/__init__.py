# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""AI Governance module for FaultRay.

Provides Japanese AI governance framework assessment based on:
- METI AI事業者ガイドライン v1.1 (10 principles, 28 requirements)
- ISO/IEC 42001:2023 AIMS (7 clauses, 25 requirements)
- AI推進法 (6 chapters, 15 requirements)

Ported from JPGovAI project with cross-framework mapping support.

Extended with:
- AI System Registry (ai_registry)
- Evidence Management with audit trail (evidence_manager)
- Policy Template Generator (policy_generator)
- Enhanced Gap Analysis with roadmap (gap_analyzer)
"""

from faultray.governance.assessor import (
    AssessmentResult,
    CategoryScore,
    GovernanceAssessor,
)
from faultray.governance.frameworks import (
    METI_CATEGORIES,
    METI_QUESTIONS,
    ISO_CLAUSES,
    ACT_CHAPTERS,
    CROSS_MAPPING,
    GovernanceFramework,
)
from faultray.governance.reporter import GovernanceReporter

__all__ = [
    "AssessmentResult",
    "CategoryScore",
    "GovernanceAssessor",
    "GovernanceReporter",
    "GovernanceFramework",
    "METI_CATEGORIES",
    "METI_QUESTIONS",
    "ISO_CLAUSES",
    "ACT_CHAPTERS",
    "CROSS_MAPPING",
]
