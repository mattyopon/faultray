# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""AI System Registry for governance tracking.

Allows organizations to register and track their AI systems,
detect shadow AI (unregistered usage), and aggregate risk summaries.

Ported from JPGovAI's ai_registry service, adapted to FaultRay patterns:
- dataclasses instead of Pydantic
- JSON file-based storage (~/.faultray/governance/)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Storage path
# ---------------------------------------------------------------------------

_STORAGE_DIR = Path.home() / ".faultray" / "governance"
_REGISTRY_FILE = _STORAGE_DIR / "ai_registry.json"


# ---------------------------------------------------------------------------
# Risk classification keywords (EU AI Act)
# ---------------------------------------------------------------------------

_HIGH_RISK_KEYWORDS = [
    "biometric", "生体", "顔認証", "face recognition",
    "critical infrastructure", "重要インフラ", "インフラ",
    "education", "教育", "入試", "entrance exam",
    "employment", "雇用", "採用", "recruitment", "hr",
    "credit scoring", "信用スコア", "融資審査", "loan",
    "law enforcement", "法執行", "犯罪", "crime",
    "healthcare", "医療", "診断", "diagnosis",
    "safety", "安全", "自動運転", "autonomous",
]

_LIMITED_RISK_KEYWORDS = [
    "chatbot", "チャットボット", "chat",
    "content generation", "コンテンツ生成", "生成AI",
    "deepfake", "ディープフェイク",
    "emotion recognition", "感情認識",
    "generative", "生成",
]

# Valid enum-like values
AI_TYPES = ("generative", "predictive", "classification", "recommendation", "other")
RISK_LEVELS = ("unacceptable", "high", "limited", "minimal")
DEPLOYMENT_STATUSES = ("planning", "development", "testing", "production", "retired")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AISystem:
    """Registered AI system record."""

    id: str = ""
    name: str = ""
    description: str = ""
    department: str = ""
    purpose: str = ""
    ai_type: str = "other"  # generative/predictive/classification/recommendation/other
    risk_level: str = "minimal"  # unacceptable/high/limited/minimal (EU AI Act)
    data_types: list[str] = field(default_factory=list)  # personal/financial/health/...
    vendor: str = ""
    model_name: str = ""  # e.g. GPT-4, Claude, in-house
    deployment_status: str = "planning"  # planning/development/testing/production/retired
    registered_at: str = ""
    last_reviewed: str = ""
    owner: str = ""
    has_pia: bool = False  # Privacy Impact Assessment
    has_ria: bool = False  # Risk Impact Assessment
    org_id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.registered_at:
            self.registered_at = now
        if not self.last_reviewed:
            self.last_reviewed = now


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _load_registry() -> list[dict]:
    """Load registry from JSON file."""
    if not _REGISTRY_FILE.exists():
        return []
    try:
        data = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_registry(records: list[dict]) -> None:
    """Save registry to JSON file."""
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    _REGISTRY_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _dict_to_system(d: dict) -> AISystem:
    """Convert a dict to an AISystem, ignoring unknown keys."""
    known_fields = {f.name for f in AISystem.__dataclass_fields__.values()}
    filtered = {k: v for k, v in d.items() if k in known_fields}
    sys = AISystem.__new__(AISystem)
    for fname in known_fields:
        setattr(sys, fname, filtered.get(fname, AISystem.__dataclass_fields__[fname].default
                                         if AISystem.__dataclass_fields__[fname].default is not
                                         AISystem.__dataclass_fields__[fname].default_factory
                                         else AISystem.__dataclass_fields__[fname].default_factory()))
    return sys


def _dict_to_system_safe(d: dict) -> AISystem:
    """Safely convert dict -> AISystem."""
    return AISystem(
        id=d.get("id", ""),
        name=d.get("name", ""),
        description=d.get("description", ""),
        department=d.get("department", ""),
        purpose=d.get("purpose", ""),
        ai_type=d.get("ai_type", "other"),
        risk_level=d.get("risk_level", "minimal"),
        data_types=d.get("data_types", []),
        vendor=d.get("vendor", ""),
        model_name=d.get("model_name", ""),
        deployment_status=d.get("deployment_status", "planning"),
        registered_at=d.get("registered_at", ""),
        last_reviewed=d.get("last_reviewed", ""),
        owner=d.get("owner", ""),
        has_pia=d.get("has_pia", False),
        has_ria=d.get("has_ria", False),
        org_id=d.get("org_id", ""),
    )


# ---------------------------------------------------------------------------
# Risk auto-classification (EU AI Act)
# ---------------------------------------------------------------------------


def classify_risk_level(system: AISystem) -> str:
    """Auto-classify risk level based on EU AI Act criteria.

    Examines name, description, purpose, data_types, and ai_type.

    Returns:
        Risk level string: "high", "limited", or "minimal".
    """
    text = f"{system.name} {system.description} {system.purpose}".lower()
    has_personal = "personal" in system.data_types

    for kw in _HIGH_RISK_KEYWORDS:
        if kw.lower() in text:
            return "high"

    if has_personal and system.ai_type in ("classification", "predictive"):
        return "high"

    for kw in _LIMITED_RISK_KEYWORDS:
        if kw.lower() in text:
            return "limited"

    if system.ai_type == "generative":
        return "limited"

    return "minimal"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_ai_system(system: AISystem) -> str:
    """Register an AI system and return its ID.

    If ``system.risk_level`` is ``"minimal"`` and the system has keywords
    suggesting higher risk, auto-classification is applied.

    Args:
        system: AISystem to register.

    Returns:
        The system's UUID string.
    """
    if not system.id:
        system.id = str(uuid.uuid4())

    # Auto-classify risk if not explicitly set
    if system.risk_level == "minimal":
        auto = classify_risk_level(system)
        if auto != "minimal":
            system.risk_level = auto

    records = _load_registry()
    records.append(asdict(system))
    _save_registry(records)
    return system.id


def list_ai_systems(org_id: str) -> list[AISystem]:
    """List all AI systems for an organization.

    Args:
        org_id: Organization identifier.

    Returns:
        List of AISystem records.
    """
    records = _load_registry()
    return [
        _dict_to_system_safe(r)
        for r in records
        if r.get("org_id") == org_id
    ]


def get_ai_system(system_id: str) -> AISystem | None:
    """Get a single AI system by ID."""
    records = _load_registry()
    for r in records:
        if r.get("id") == system_id:
            return _dict_to_system_safe(r)
    return None


def detect_shadow_ai(
    org_id: str, known_systems: list[str],
) -> list[dict]:
    """Detect shadow AI by comparing registered systems against known ones.

    Args:
        org_id: Organization identifier.
        known_systems: List of known/approved AI system names or identifiers.

    Returns:
        List of dicts describing unregistered AI usage detected.
    """
    registered = list_ai_systems(org_id)
    registered_names = {s.name.lower() for s in registered}
    registered_ids = {s.id for s in registered}

    shadows: list[dict] = []
    for known in known_systems:
        known_lower = known.lower()
        if known_lower not in registered_names and known not in registered_ids:
            shadows.append({
                "system_name": known,
                "status": "unregistered",
                "recommendation": f"AIシステム「{known}」が台帳に未登録です。登録してください。",
            })

    return shadows


def get_risk_summary(org_id: str) -> dict:
    """Get aggregated risk summary for an organization.

    Args:
        org_id: Organization identifier.

    Returns:
        Dict with total, by_risk_level, by_department, by_status counts,
        and avg completeness metrics.
    """
    systems = list_ai_systems(org_id)

    by_risk: dict[str, int] = {}
    by_dept: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    pia_count = 0
    ria_count = 0

    for s in systems:
        by_risk[s.risk_level] = by_risk.get(s.risk_level, 0) + 1
        if s.department:
            by_dept[s.department] = by_dept.get(s.department, 0) + 1
        by_status[s.deployment_status] = by_status.get(s.deployment_status, 0) + 1
        by_type[s.ai_type] = by_type.get(s.ai_type, 0) + 1
        if s.has_pia:
            pia_count += 1
        if s.has_ria:
            ria_count += 1

    total = len(systems)
    return {
        "total_systems": total,
        "by_risk_level": by_risk,
        "by_department": by_dept,
        "by_deployment_status": by_status,
        "by_ai_type": by_type,
        "pia_coverage": pia_count / total if total > 0 else 0.0,
        "ria_coverage": ria_count / total if total > 0 else 0.0,
        "high_risk_count": by_risk.get("high", 0) + by_risk.get("unacceptable", 0),
    }


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------


def reset_registry() -> None:
    """Reset the registry file (for testing)."""
    if _REGISTRY_FILE.exists():
        _REGISTRY_FILE.unlink()
