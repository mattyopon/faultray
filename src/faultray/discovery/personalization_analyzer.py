# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Personalization (属人化) risk analyzer.

Combines GAS scan + infrastructure scan to identify
single-person dependencies across the entire organization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from faultray.discovery.gas_scanner import GASScanResult, GASScript

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class PersonDependency:
    """Single person's system dependencies and associated risk."""

    person_name: str
    person_email: str
    person_status: str  # "active" | "departed" | "on_leave"
    systems: list[dict[str, Any]] = field(default_factory=list)
    # [{name, type, role, risk_level}]
    risk_score: float = 0.0
    bus_factor: int = 1  # How many people need to leave for this to break

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "person_name": self.person_name,
            "person_email": self.person_email,
            "person_status": self.person_status,
            "systems": self.systems,
            "risk_score": self.risk_score,
            "bus_factor": self.bus_factor,
        }


@dataclass
class PersonalizationReport:
    """Organization-wide personalization (属人化) risk report."""

    organization: str
    total_people: int
    total_systems: int
    critical_dependencies: list[PersonDependency] = field(default_factory=list)
    bus_factor_1: int = 0  # Systems where 1 person leaving = broken
    bus_factor_2: int = 0  # Systems where 2 people leaving = broken
    improvement_actions: list[dict[str, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "organization": self.organization,
            "total_people": self.total_people,
            "total_systems": self.total_systems,
            "critical_dependencies": [d.to_dict() for d in self.critical_dependencies],
            "bus_factor_1": self.bus_factor_1,
            "bus_factor_2": self.bus_factor_2,
            "improvement_actions": self.improvement_actions,
            "generated_at": self.generated_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class PersonalizationAnalyzer:
    """Analyze personalization risk across GAS scripts and infrastructure."""

    def analyze_gas(self, gas_result: GASScanResult) -> PersonalizationReport:
        """Build a PersonalizationReport from a GASScanResult.

        Args:
            gas_result: The result of a GAS organization scan.

        Returns:
            PersonalizationReport with dependency analysis and improvement actions.
        """
        # Build a per-owner view
        owner_map: dict[str, list[GASScript]] = {}
        for script in gas_result.scripts:
            owner_map.setdefault(script.owner_email, []).append(script)

        # Build PersonDependency per person
        person_deps: list[PersonDependency] = []
        bus_factor_1 = 0
        bus_factor_2 = 0

        for email, scripts in owner_map.items():
            sample = scripts[0]
            person_status = sample.owner_status

            systems: list[dict[str, Any]] = []
            max_risk = 0.0
            for s in scripts:
                # Find risk level for this script from gas_result.risks
                risk_entry = next(
                    (r for r in gas_result.risks if r.script_id == s.id), None
                )
                risk_level = risk_entry.risk_level if risk_entry else "ok"
                risk_score = risk_entry.risk_score if risk_entry else 0.0

                shared_count = len(s.shared_with)
                if shared_count <= 1:
                    bus_factor_1 += 1
                elif shared_count == 2:
                    bus_factor_2 += 1

                systems.append(
                    {
                        "name": s.name,
                        "type": "GAS",
                        "role": "owner",
                        "risk_level": risk_level,
                        "linked_services": s.linked_services,
                        "shared_with_count": shared_count,
                    }
                )
                if risk_score > max_risk:
                    max_risk = risk_score

            dep = PersonDependency(
                person_name=sample.owner_name,
                person_email=email,
                person_status=person_status,
                systems=systems,
                risk_score=max_risk,
                bus_factor=1 if all(len(s.shared_with) <= 1 for s in scripts) else 2,
            )
            person_deps.append(dep)

        # Sort by risk score descending, only expose "critical" or "warning" level
        person_deps.sort(key=lambda d: d.risk_score, reverse=True)
        critical_deps = [
            d for d in person_deps if d.risk_score >= 4 or d.person_status == "departed"
        ]

        improvement_actions = self._generate_improvement_actions(gas_result, critical_deps)

        return PersonalizationReport(
            organization=gas_result.organization,
            total_people=len(owner_map),
            total_systems=gas_result.total_scripts,
            critical_dependencies=critical_deps,
            bus_factor_1=bus_factor_1,
            bus_factor_2=bus_factor_2,
            improvement_actions=improvement_actions,
        )

    def _generate_improvement_actions(
        self,
        gas_result: GASScanResult,
        critical_deps: list[PersonDependency],
    ) -> list[dict[str, Any]]:
        """Generate prioritized improvement actions for reducing personalization risk."""
        actions: list[dict[str, Any]] = []

        departed_owners = [
            d for d in critical_deps if d.person_status == "departed"
        ]
        if departed_owners:
            names = ", ".join(d.person_name for d in departed_owners[:3])
            actions.append(
                {
                    "priority": "critical",
                    "action": "departed_owner_transfer",
                    "title": "退職者所有スクリプトのオーナー移転",
                    "description": (
                        f"{names} など {len(departed_owners)} 名の退職者が"
                        "オーナーのスクリプトを即座に別の担当者に移転してください。"
                    ),
                    "affected_scripts": sum(len(d.systems) for d in departed_owners),
                }
            )

        no_backup_count = sum(
            1
            for r in gas_result.risks
            if r.risk_level in ("critical", "warning") and not r.has_backup_owner
        )
        if no_backup_count:
            actions.append(
                {
                    "priority": "high",
                    "action": "add_backup_owner",
                    "title": "バックアップオーナーの追加",
                    "description": (
                        f"{no_backup_count} 件のスクリプトに"
                        "バックアップオーナーを追加し、単一障害点を排除してください。"
                    ),
                    "affected_scripts": no_backup_count,
                }
            )

        stale_count = sum(
            1
            for s in gas_result.scripts
            if (
                hasattr(s, "updated_at")
                and (
                    __import__("datetime").datetime.now(
                        tz=__import__("datetime").timezone.utc
                    )
                    - s.updated_at
                ).days
                > 365
            )
        )
        if stale_count:
            actions.append(
                {
                    "priority": "medium",
                    "action": "review_stale_scripts",
                    "title": "長期未更新スクリプトのレビュー",
                    "description": (
                        f"{stale_count} 件のスクリプトが 1 年以上更新されていません。"
                        "現在も必要かどうか確認し、不要なら削除してください。"
                    ),
                    "affected_scripts": stale_count,
                }
            )

        actions.append(
            {
                "priority": "low",
                "action": "document_all_scripts",
                "title": "全スクリプトのドキュメント整備",
                "description": (
                    "スクリプトの目的・担当者・依存サービスを"
                    "スプレッドシートまたは Notion に記録し、"
                    "属人化を構造的に防止する台帳を作成してください。"
                ),
                "affected_scripts": gas_result.total_scripts,
            }
        )

        return actions
