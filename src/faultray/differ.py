# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Compare two simulation runs and detect regressions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Thresholds for severity classification (matches engine.py)
CRITICAL_THRESHOLD = 7.0
WARNING_THRESHOLD = 4.0


@dataclass
class DiffResult:
    """Result of comparing two simulation runs."""

    score_before: float
    score_after: float
    score_delta: float
    new_critical: list[str] = field(default_factory=list)
    resolved_critical: list[str] = field(default_factory=list)
    new_warnings: list[str] = field(default_factory=list)
    resolved_warnings: list[str] = field(default_factory=list)
    component_changes: list[str] = field(default_factory=list)
    regression_detected: bool = False


class SimulationDiffer:
    """Compares two simulation result sets and produces a DiffResult."""

    def diff(self, before: dict, after: dict) -> DiffResult:
        """Compare two simulation result dicts.

        Both *before* and *after* are expected to follow the JSON export
        format produced by ``export_json`` / ``_report_to_export_dict`` with
        keys like ``resilience_score``, ``results`` (list of scenario dicts),
        etc.
        """
        score_before = before.get("resilience_score", 0.0)
        score_after = after.get("resilience_score", 0.0)
        score_delta = round(score_after - score_before, 4)

        # Extract scenario-level severity info
        before_scenarios = self._scenario_map(before)
        after_scenarios = self._scenario_map(after)

        before_critical = {
            name for name, info in before_scenarios.items()
            if info.get("is_critical") or info.get("risk_score", 0) >= CRITICAL_THRESHOLD
        }
        after_critical = {
            name for name, info in after_scenarios.items()
            if info.get("is_critical") or info.get("risk_score", 0) >= CRITICAL_THRESHOLD
        }
        before_warning = {
            name for name, info in before_scenarios.items()
            if (info.get("is_warning") or WARNING_THRESHOLD <= info.get("risk_score", 0) < CRITICAL_THRESHOLD)
            and name not in before_critical
        }
        after_warning = {
            name for name, info in after_scenarios.items()
            if (info.get("is_warning") or WARNING_THRESHOLD <= info.get("risk_score", 0) < CRITICAL_THRESHOLD)
            and name not in after_critical
        }

        new_critical = sorted(after_critical - before_critical)
        resolved_critical = sorted(before_critical - after_critical)
        new_warnings = sorted(after_warning - before_warning)
        resolved_warnings = sorted(before_warning - after_warning)

        # Component-level changes (if available)
        component_changes = self._detect_component_changes(before, after)

        # Regression: score dropped OR new critical findings appeared
        regression_detected = score_delta < 0 or len(new_critical) > 0

        return DiffResult(
            score_before=score_before,
            score_after=score_after,
            score_delta=score_delta,
            new_critical=new_critical,
            resolved_critical=resolved_critical,
            new_warnings=new_warnings,
            resolved_warnings=resolved_warnings,
            component_changes=component_changes,
            regression_detected=regression_detected,
        )

    def diff_files(self, before_path: Path, after_path: Path) -> DiffResult:
        """Load two JSON result files and compare them."""
        before_path = Path(before_path)
        after_path = Path(after_path)

        with open(before_path, encoding="utf-8") as f:
            before = json.load(f)
        with open(after_path, encoding="utf-8") as f:
            after = json.load(f)

        return self.diff(before, after)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scenario_map(data: dict) -> dict[str, dict]:
        """Build a mapping of scenario_name -> scenario info dict."""
        scenarios: dict[str, dict] = {}
        for r in data.get("results", []):
            name = r.get("scenario_name", r.get("name", "unknown"))
            scenarios[name] = r
        return scenarios

    @staticmethod
    def _detect_component_changes(before: dict, after: dict) -> list[str]:
        """Detect added/removed components between two runs."""
        changes: list[str] = []

        # Try to extract component lists from results cascade effects
        before_components = set()
        after_components = set()

        for r in before.get("results", []):
            cascade = r.get("cascade", {})
            for effect in cascade.get("effects", []):
                cid = effect.get("component_id", "")
                if cid:
                    before_components.add(cid)

        for r in after.get("results", []):
            cascade = r.get("cascade", {})
            for effect in cascade.get("effects", []):
                cid = effect.get("component_id", "")
                if cid:
                    after_components.add(cid)

        added = sorted(after_components - before_components)
        removed = sorted(before_components - after_components)

        for cid in added:
            changes.append(f"added: {cid}")
        for cid in removed:
            changes.append(f"removed: {cid}")

        return changes
