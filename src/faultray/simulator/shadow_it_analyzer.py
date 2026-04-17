# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Shadow IT / Orphaned System Analyzer.

Detects components that are unmanaged, undocumented, or otherwise likely to
represent "shadow IT" — systems that operate outside normal governance.

Risk categories:
- orphaned      : owner is empty
- stale         : last_modified more than 365 days ago
- possibly_dead : last_executed empty or more than 30 days ago
- undocumented  : documentation_url empty
- high_risk_orphan : automation/serverless/scheduled_job with no owner
- creator_left  : created_by differs from owner and owner is empty
- unknown_status: lifecycle_status == "unknown"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

# Component types that carry elevated risk when unmanaged
_HIGH_RISK_TYPES: frozenset[ComponentType] = frozenset(
    {
        ComponentType.AUTOMATION,
        ComponentType.SERVERLESS,
        ComponentType.SCHEDULED_JOB,
    }
)

_STALE_DAYS = 365          # days since last_modified to flag as stale
_DEAD_DAYS = 30            # days since last_executed to flag as possibly_dead


def _parse_date(value: str) -> date | None:
    """Parse an ISO 8601 date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS...).

    Returns ``None`` when the string is empty or unparseable.
    """
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            continue
    return None


def _days_since(value: str) -> int | None:
    """Return the number of calendar days between *value* and today.

    Returns ``None`` when *value* is empty or cannot be parsed.
    """
    parsed = _parse_date(value)
    if parsed is None:
        return None
    today = datetime.now(tz=timezone.utc).date()
    return (today - parsed).days


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ShadowITFinding:
    """A single finding about a potentially unmanaged component."""

    component_id: str
    component_name: str
    component_type: str
    risk_level: str        # critical / high / medium / low
    category: str          # orphaned / stale / undocumented / dead / unknown_owner / high_risk_orphan / creator_left / unknown_status
    detail: str
    recommendation: str


@dataclass
class ShadowITReport:
    """Aggregated shadow IT analysis result."""

    findings: list[ShadowITFinding] = field(default_factory=list)
    total_components: int = 0
    orphaned_count: int = 0
    stale_count: int = 0
    undocumented_count: int = 0
    risk_score: float = 0.0   # 0-100, higher = more shadow IT risk
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "total_components": self.total_components,
            "orphaned_count": self.orphaned_count,
            "stale_count": self.stale_count,
            "undocumented_count": self.undocumented_count,
            "risk_score": round(self.risk_score, 1),
            "summary": self.summary,
            "findings": [
                {
                    "component_id": f.component_id,
                    "component_name": f.component_name,
                    "component_type": f.component_type,
                    "risk_level": f.risk_level,
                    "category": f.category,
                    "detail": f.detail,
                    "recommendation": f.recommendation,
                }
                for f in self.findings
            ],
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class ShadowITAnalyzer:
    """Detect and assess orphaned / unmanaged components in an InfraGraph."""

    def analyze(self, graph: InfraGraph) -> ShadowITReport:
        """Analyze all components for ownership and lifecycle issues.

        Args:
            graph: The infrastructure graph to inspect.

        Returns:
            A :class:`ShadowITReport` with all findings and aggregate metrics.
        """
        findings: list[ShadowITFinding] = []
        orphaned_ids: set[str] = set()
        stale_ids: set[str] = set()
        undocumented_ids: set[str] = set()

        for comp in graph.components.values():
            comp_type_str = comp.type.value if hasattr(comp.type, "value") else str(comp.type)

            # 1. owner empty → orphaned
            if not comp.owner:
                orphaned_ids.add(comp.id)
                findings.append(
                    ShadowITFinding(
                        component_id=comp.id,
                        component_name=comp.name,
                        component_type=comp_type_str,
                        risk_level="high",
                        category="orphaned",
                        detail="No owner assigned to this component.",
                        recommendation="Assign an owner who is responsible for maintenance and incident response.",
                    )
                )

            # 2. last_modified more than _STALE_DAYS ago → stale
            modified_age = _days_since(comp.last_modified)
            if modified_age is not None and modified_age > _STALE_DAYS:
                stale_ids.add(comp.id)
                findings.append(
                    ShadowITFinding(
                        component_id=comp.id,
                        component_name=comp.name,
                        component_type=comp_type_str,
                        risk_level="medium",
                        category="stale",
                        detail=f"Last modified {modified_age} days ago (threshold: {_STALE_DAYS} days).",
                        recommendation="Review whether this component is still required and update or decommission it.",
                    )
                )

            # 3. last_executed empty or more than _DEAD_DAYS ago → possibly_dead
            executed_age = _days_since(comp.last_executed)
            if comp.last_executed == "" or (executed_age is not None and executed_age > _DEAD_DAYS):
                # Only flag execution-oriented types or components with explicit last_executed field
                if comp.type in _HIGH_RISK_TYPES or comp.last_executed:
                    findings.append(
                        ShadowITFinding(
                            component_id=comp.id,
                            component_name=comp.name,
                            component_type=comp_type_str,
                            risk_level="medium",
                            category="possibly_dead",
                            detail=(
                                "Last execution date is unknown."
                                if not comp.last_executed
                                else f"Last executed {executed_age} days ago (threshold: {_DEAD_DAYS} days)."
                            ),
                            recommendation="Confirm this component is still actively running; decommission if unused.",
                        )
                    )

            # 4. documentation_url empty → undocumented
            if not comp.documentation_url:
                undocumented_ids.add(comp.id)
                findings.append(
                    ShadowITFinding(
                        component_id=comp.id,
                        component_name=comp.name,
                        component_type=comp_type_str,
                        risk_level="low",
                        category="undocumented",
                        detail="No documentation URL provided.",
                        recommendation="Add a link to runbook, wiki, or README that describes this component.",
                    )
                )

            # 5. High-risk type with no owner → high_risk_orphan (critical)
            if comp.type in _HIGH_RISK_TYPES and not comp.owner:
                findings.append(
                    ShadowITFinding(
                        component_id=comp.id,
                        component_name=comp.name,
                        component_type=comp_type_str,
                        risk_level="critical",
                        category="high_risk_orphan",
                        detail=(
                            f"Component of type '{comp_type_str}' (automation/serverless/scheduled job) "
                            "has no owner. Silent failures may go unnoticed."
                        ),
                        recommendation=(
                            "Immediately assign an owner. Add alerting for failures and document the trigger/schedule."
                        ),
                    )
                )

            # 6. created_by differs from owner AND owner is empty → creator_left
            if comp.created_by and comp.created_by != comp.owner and not comp.owner:
                findings.append(
                    ShadowITFinding(
                        component_id=comp.id,
                        component_name=comp.name,
                        component_type=comp_type_str,
                        risk_level="high",
                        category="creator_left",
                        detail=(
                            f"Original creator '{comp.created_by}' is no longer the owner, "
                            "and no replacement owner has been assigned."
                        ),
                        recommendation=(
                            "Determine if the creator has left or changed roles, "
                            "then assign a new owner before institutional knowledge is lost."
                        ),
                    )
                )

            # 7. lifecycle_status == "unknown" → unknown_status risk
            if comp.lifecycle_status == "unknown":
                findings.append(
                    ShadowITFinding(
                        component_id=comp.id,
                        component_name=comp.name,
                        component_type=comp_type_str,
                        risk_level="medium",
                        category="unknown_status",
                        detail="Lifecycle status is 'unknown'. It is unclear whether this component is active or decommissioned.",
                        recommendation="Set lifecycle_status to 'active', 'deprecated', or 'orphaned' and notify the team.",
                    )
                )

        # --- Aggregate metrics ------------------------------------------------
        total = len(graph.components)

        # Risk score: weighted sum normalised to 0-100
        # critical=10, high=5, medium=2, low=1
        _weights = {"critical": 10, "high": 5, "medium": 2, "low": 1}
        raw_score = sum(_weights.get(f.risk_level, 1) for f in findings)
        max_possible = total * sum(_weights.values()) if total > 0 else 1
        risk_score = min(100.0, (raw_score / max_possible) * 100) if max_possible > 0 else 0.0

        # Build summary line
        critical_count = sum(1 for f in findings if f.risk_level == "critical")
        high_count = sum(1 for f in findings if f.risk_level == "high")
        summary = (
            f"{total} component(s) analysed. "
            f"{len(orphaned_ids)} orphaned, "
            f"{len(stale_ids)} stale, "
            f"{len(undocumented_ids)} undocumented. "
            f"Risk score: {risk_score:.1f}/100"
            + (f" — {critical_count} critical finding(s)." if critical_count else ".")
            + (f" {high_count} high finding(s)." if high_count else "")
        )

        return ShadowITReport(
            findings=findings,
            total_components=total,
            orphaned_count=len(orphaned_ids),
            stale_count=len(stale_ids),
            undocumented_count=len(undocumented_ids),
            risk_score=risk_score,
            summary=summary,
        )
