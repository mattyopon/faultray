# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Dependency Freshness Alerting for FaultRay.

Monitors how up-to-date infrastructure components and their dependencies are.
Identifies stale configurations, outdated software versions, expired certificates,
and aging infrastructure that increases failure risk. Generates alerts based on
freshness thresholds.

Usage:
    from faultray.simulator.freshness_alert import FreshnessAlertEngine
    engine = FreshnessAlertEngine()
    engine.add_record(record)
    report = engine.generate_report()
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FreshnessCategory(str, Enum):
    """Category of the item being tracked for freshness."""

    SOFTWARE_VERSION = "software_version"
    CERTIFICATE = "certificate"
    CONFIGURATION = "configuration"
    PATCH_LEVEL = "patch_level"
    DEPENDENCY_VERSION = "dependency_version"
    BACKUP = "backup"
    DOCUMENTATION = "documentation"
    RUNBOOK = "runbook"


class FreshnessLevel(str, Enum):
    """Freshness classification based on age relative to policy thresholds."""

    CURRENT = "current"
    AGING = "aging"
    STALE = "stale"
    CRITICAL = "critical"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class FreshnessRecord(BaseModel):
    """A single item whose freshness is being tracked."""

    component_id: str
    category: FreshnessCategory
    item_name: str
    current_version: str
    latest_version: str | None = None
    last_updated: datetime
    max_age_days: int
    freshness_level: FreshnessLevel | None = None


class FreshnessAlert(BaseModel):
    """An alert generated for a stale, critical, or expired record."""

    record: FreshnessRecord
    age_days: float
    overdue_days: float
    risk_score: float = Field(ge=0.0, le=1.0)
    recommendation: str


class FreshnessPolicy(BaseModel):
    """Policy defining freshness thresholds for a category."""

    category: FreshnessCategory
    max_age_days: int
    warning_at_percent: float = 75.0
    critical_at_percent: float = 90.0


class FreshnessReport(BaseModel):
    """Aggregated freshness report across all tracked records."""

    total_items: int
    current_count: int
    aging_count: int
    stale_count: int
    critical_count: int
    expired_count: int
    alerts: list[FreshnessAlert]
    overall_freshness_score: float = Field(ge=0.0, le=100.0)
    recommendations: list[str]


# ---------------------------------------------------------------------------
# Freshness score weights per level
# ---------------------------------------------------------------------------

_LEVEL_SCORES: dict[FreshnessLevel, float] = {
    FreshnessLevel.CURRENT: 100.0,
    FreshnessLevel.AGING: 75.0,
    FreshnessLevel.STALE: 50.0,
    FreshnessLevel.CRITICAL: 25.0,
    FreshnessLevel.EXPIRED: 0.0,
}

# Default max_age_days per category
_DEFAULT_MAX_AGE: dict[FreshnessCategory, int] = {
    FreshnessCategory.SOFTWARE_VERSION: 180,
    FreshnessCategory.CERTIFICATE: 365,
    FreshnessCategory.CONFIGURATION: 90,
    FreshnessCategory.PATCH_LEVEL: 30,
    FreshnessCategory.DEPENDENCY_VERSION: 120,
    FreshnessCategory.BACKUP: 7,
    FreshnessCategory.DOCUMENTATION: 180,
    FreshnessCategory.RUNBOOK: 90,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class FreshnessAlertEngine:
    """Engine that evaluates freshness records and generates alerts/reports.

    Comes with sensible default policies for all eight freshness categories.
    Policies can be customised via :meth:`set_policy`.
    """

    def __init__(self) -> None:
        self._records: list[FreshnessRecord] = []
        self._policies: dict[FreshnessCategory, FreshnessPolicy] = {}
        # Initialise default policies
        for cat, max_age in _DEFAULT_MAX_AGE.items():
            self._policies[cat] = FreshnessPolicy(
                category=cat, max_age_days=max_age
            )

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def add_record(self, record: FreshnessRecord) -> None:
        """Add a freshness record to the engine."""
        self._records.append(record)

    def set_policy(self, policy: FreshnessPolicy) -> None:
        """Set or override the policy for *policy.category*."""
        self._policies[policy.category] = policy

    def evaluate_freshness(self, record: FreshnessRecord) -> FreshnessLevel:
        """Determine the freshness level of *record* based on its age and policy.

        Freshness level thresholds (relative to ``max_age_days``):
        - ``CURRENT``:  age < warning_at_percent of max_age
        - ``AGING``:    age < critical_at_percent of max_age
        - ``STALE``:    age < max_age
        - ``CRITICAL``: age < max_age * 1.5
        - ``EXPIRED``:  age >= max_age * 1.5
        """
        policy = self._policies.get(record.category)
        max_age = record.max_age_days
        if policy is not None:
            max_age = policy.max_age_days

        age_days = self._compute_age_days(record)

        if policy is None:
            warning_pct = 75.0
            critical_pct = 90.0
        else:
            warning_pct = policy.warning_at_percent
            critical_pct = policy.critical_at_percent

        warning_threshold = max_age * (warning_pct / 100.0)
        critical_threshold = max_age * (critical_pct / 100.0)
        expired_threshold = max_age * 1.5

        if age_days < warning_threshold:
            return FreshnessLevel.CURRENT
        if age_days < critical_threshold:
            return FreshnessLevel.AGING
        if age_days < max_age:
            return FreshnessLevel.STALE
        if age_days < expired_threshold:
            return FreshnessLevel.CRITICAL
        return FreshnessLevel.EXPIRED

    def generate_alerts(self) -> list[FreshnessAlert]:
        """Generate alerts for all records that are STALE, CRITICAL, or EXPIRED."""
        alerts: list[FreshnessAlert] = []
        for record in self._records:
            level = self.evaluate_freshness(record)
            record.freshness_level = level
            if level in (
                FreshnessLevel.STALE,
                FreshnessLevel.CRITICAL,
                FreshnessLevel.EXPIRED,
            ):
                alert = self._build_alert(record, level)
                alerts.append(alert)
        # Sort by risk_score descending
        alerts.sort(key=lambda a: a.risk_score, reverse=True)
        return alerts

    def calculate_freshness_score(self) -> float:
        """Calculate the overall freshness score (0-100) across all records.

        Returns 100.0 when there are no records.
        """
        if not self._records:
            return 100.0

        total = 0.0
        for record in self._records:
            level = self.evaluate_freshness(record)
            total += _LEVEL_SCORES[level]

        return round(total / len(self._records), 1)

    def generate_report(self) -> FreshnessReport:
        """Generate a full freshness report covering all tracked records."""
        alerts = self.generate_alerts()

        counts: dict[FreshnessLevel, int] = {lvl: 0 for lvl in FreshnessLevel}
        for record in self._records:
            level = self.evaluate_freshness(record)
            record.freshness_level = level
            counts[level] += 1

        score = self.calculate_freshness_score()
        recommendations = self._generate_recommendations(counts, alerts)

        return FreshnessReport(
            total_items=len(self._records),
            current_count=counts[FreshnessLevel.CURRENT],
            aging_count=counts[FreshnessLevel.AGING],
            stale_count=counts[FreshnessLevel.STALE],
            critical_count=counts[FreshnessLevel.CRITICAL],
            expired_count=counts[FreshnessLevel.EXPIRED],
            alerts=alerts,
            overall_freshness_score=score,
            recommendations=recommendations,
        )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _compute_age_days(record: FreshnessRecord) -> float:
        """Compute the age of a record in days from ``last_updated`` to now."""
        now = datetime.now(timezone.utc)
        last = record.last_updated
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = now - last
        return max(0.0, delta.total_seconds() / 86400.0)

    def _build_alert(
        self, record: FreshnessRecord, level: FreshnessLevel
    ) -> FreshnessAlert:
        """Build a :class:`FreshnessAlert` for a record."""
        policy = self._policies.get(record.category)
        max_age = policy.max_age_days if policy else record.max_age_days
        age_days = self._compute_age_days(record)
        overdue = max(0.0, age_days - max_age)
        risk_score = min(1.0, age_days / (max_age * 1.5)) if max_age > 0 else 1.0
        recommendation = self._make_recommendation(record, level, age_days, max_age)

        return FreshnessAlert(
            record=record,
            age_days=round(age_days, 1),
            overdue_days=round(overdue, 1),
            risk_score=round(risk_score, 4),
            recommendation=recommendation,
        )

    @staticmethod
    def _make_recommendation(
        record: FreshnessRecord,
        level: FreshnessLevel,
        age_days: float,
        max_age: int,
    ) -> str:
        """Generate a human-readable recommendation string."""
        if level == FreshnessLevel.EXPIRED:
            return (
                f"URGENT: '{record.item_name}' on {record.component_id} is "
                f"{age_days:.0f} days old (limit: {max_age}). "
                f"Update immediately to reduce risk."
            )
        if level == FreshnessLevel.CRITICAL:
            return (
                f"CRITICAL: '{record.item_name}' on {record.component_id} is "
                f"{age_days:.0f} days old (limit: {max_age}). "
                f"Schedule update within this week."
            )
        return (
            f"WARNING: '{record.item_name}' on {record.component_id} is "
            f"{age_days:.0f} days old (limit: {max_age}). "
            f"Plan update in next maintenance window."
        )

    @staticmethod
    def _generate_recommendations(
        counts: dict[FreshnessLevel, int],
        alerts: list[FreshnessAlert],
    ) -> list[str]:
        """Generate report-level recommendations."""
        recs: list[str] = []
        expired = counts.get(FreshnessLevel.EXPIRED, 0)
        critical = counts.get(FreshnessLevel.CRITICAL, 0)
        stale = counts.get(FreshnessLevel.STALE, 0)

        if expired > 0:
            recs.append(
                f"URGENT: {expired} item(s) have expired and require immediate update."
            )
        if critical > 0:
            recs.append(
                f"CRITICAL: {critical} item(s) are critically outdated. "
                f"Schedule updates this week."
            )
        if stale > 0:
            recs.append(
                f"WARNING: {stale} item(s) are stale. "
                f"Plan updates in the next maintenance window."
            )
        if expired == 0 and critical == 0 and stale == 0:
            recs.append("All items are within acceptable freshness thresholds.")

        return recs
