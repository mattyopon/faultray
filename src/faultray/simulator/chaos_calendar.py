"""Chaos Calendar - schedule chaos experiments with learning from results.

Provides scheduled chaos windows, experiment suggestion, result recording,
risk forecasting (Poisson process), and Bayesian MTBF adjustments.

Stores persistent data in SQLite at ``~/.faultray/calendar.db``.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

_DEFAULT_DB_DIR = Path.home() / ".faultray"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "calendar.db"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ChaosWindow:
    """A recurring time window during which chaos experiments may run."""

    name: str
    cron_expression: str  # e.g. "0 2 * * THU"
    max_blast_radius: float = 0.5  # 0-1
    allowed_categories: list[str] = field(default_factory=lambda: ["all"])
    max_duration_minutes: int = 60


@dataclass
class ExperimentRecord:
    """Record of a single experiment execution."""

    experiment_id: str
    scenario_id: str
    scheduled_at: str
    executed_at: str | None = None
    result: str = "pass"  # "pass", "fail", "skipped"
    observed_blast_radius: float = 0.0
    learned_mtbf_adjustment: float = 0.0  # Bayesian MTBF update factor
    notes: str = ""


@dataclass
class RiskForecast:
    """Risk forecast over a given horizon."""

    horizon_days: int
    critical_incident_probability: float
    component_risks: dict[str, float]  # comp_id -> failure probability
    recommendation: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_db(db_path: Path) -> sqlite3.Connection:
    """Open (and optionally create) the calendar database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chaos_windows (
            name TEXT PRIMARY KEY,
            cron_expression TEXT NOT NULL,
            max_blast_radius REAL DEFAULT 0.5,
            allowed_categories TEXT DEFAULT '["all"]',
            max_duration_minutes INTEGER DEFAULT 60
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS experiment_records (
            experiment_id TEXT PRIMARY KEY,
            scenario_id TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            executed_at TEXT,
            result TEXT DEFAULT 'pass',
            observed_blast_radius REAL DEFAULT 0.0,
            learned_mtbf_adjustment REAL DEFAULT 0.0,
            notes TEXT DEFAULT ''
        )
    """)
    conn.commit()
    return conn


def _poisson_failure_probability(mtbf_hours: float, horizon_hours: float) -> float:
    """P(at least one failure) = 1 - exp(-t / MTBF)."""
    if mtbf_hours <= 0:
        return 1.0
    return 1.0 - math.exp(-horizon_hours / mtbf_hours)


def _bayesian_mtbf_update(
    prior_mtbf: float,
    experiment_passed: bool,
    experiment_duration_hours: float = 1.0,
) -> float:
    """Simple Bayesian update of MTBF based on an experiment outcome.

    If the experiment passed (no failure), we increase confidence in the
    current MTBF.  If it failed, we lower it.

    Returns the adjustment factor (positive = increase, negative = decrease).
    """
    if experiment_passed:
        # Survival evidence: nudge MTBF upward
        return experiment_duration_hours * 0.1  # +10 % of experiment duration
    else:
        # Failure evidence: nudge MTBF downward
        return -experiment_duration_hours * 0.2  # -20 % of experiment duration


# ---------------------------------------------------------------------------
# ChaosCalendar
# ---------------------------------------------------------------------------

class ChaosCalendar:
    """Schedule and track chaos experiments with feedback learning.

    Args:
        graph: The infrastructure graph to reason about.
        store_path: Optional path to the SQLite database.
                    Defaults to ``~/.faultray/calendar.db``.
    """

    def __init__(
        self,
        graph: InfraGraph,
        store_path: Path | None = None,
    ) -> None:
        self.graph = graph
        self._db_path = store_path or _DEFAULT_DB_PATH
        self._conn = _init_db(self._db_path)

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------

    def add_window(self, window: ChaosWindow) -> None:
        """Register a chaos experiment window."""
        self._conn.execute(
            "INSERT OR REPLACE INTO chaos_windows "
            "(name, cron_expression, max_blast_radius, allowed_categories, max_duration_minutes) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                window.name,
                window.cron_expression,
                window.max_blast_radius,
                json.dumps(window.allowed_categories),
                window.max_duration_minutes,
            ),
        )
        self._conn.commit()

    def get_schedule(self) -> list[dict]:
        """Return all registered chaos windows."""
        cur = self._conn.execute(
            "SELECT name, cron_expression, max_blast_radius, "
            "allowed_categories, max_duration_minutes FROM chaos_windows"
        )
        results = []
        for row in cur.fetchall():
            results.append({
                "name": row[0],
                "cron_expression": row[1],
                "max_blast_radius": row[2],
                "allowed_categories": json.loads(row[3]),
                "max_duration_minutes": row[4],
            })
        return results

    # ------------------------------------------------------------------
    # Experiments
    # ------------------------------------------------------------------

    def suggest_experiments(self) -> list[dict]:
        """Suggest chaos experiments based on the infrastructure graph.

        Prioritises components that are single-points-of-failure,
        have high utilisation, or have not been tested recently.
        """
        suggestions: list[dict] = []

        tested_scenarios: set[str] = set()
        cur = self._conn.execute("SELECT DISTINCT scenario_id FROM experiment_records")
        for row in cur.fetchall():
            tested_scenarios.add(row[0])

        for comp_id, comp in self.graph.components.items():
            dependents = self.graph.get_dependents(comp_id)
            is_spof = comp.replicas <= 1 and len(dependents) > 0
            util = comp.utilization()

            # Priority score
            priority = 0.0
            reasons: list[str] = []

            if is_spof:
                priority += 5.0
                reasons.append("single point of failure")
            if util > 70:
                priority += 3.0
                reasons.append(f"high utilization ({util:.0f}%)")
            if comp_id not in tested_scenarios:
                priority += 2.0
                reasons.append("never tested")
            if comp.operational_profile.mtbf_hours > 0:
                if comp.operational_profile.mtbf_hours < 720:
                    priority += 1.0
                    reasons.append("low MTBF")

            if priority > 0:
                suggestions.append({
                    "component_id": comp_id,
                    "component_name": comp.name,
                    "priority": priority,
                    "reasons": reasons,
                    "suggested_scenario": f"Kill {comp.name} ({comp.type.value})",
                })

        suggestions.sort(key=lambda s: s["priority"], reverse=True)
        return suggestions

    def record_result(self, record: ExperimentRecord) -> None:
        """Persist an experiment result and apply Bayesian MTBF update."""
        # Apply MTBF adjustment if we have a graph component
        comp = self.graph.get_component(record.scenario_id)
        if comp and comp.operational_profile.mtbf_hours > 0:
            passed = record.result == "pass"
            adj = _bayesian_mtbf_update(
                comp.operational_profile.mtbf_hours,
                passed,
            )
            record.learned_mtbf_adjustment = adj

        self._conn.execute(
            "INSERT OR REPLACE INTO experiment_records "
            "(experiment_id, scenario_id, scheduled_at, executed_at, result, "
            "observed_blast_radius, learned_mtbf_adjustment, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.experiment_id,
                record.scenario_id,
                record.scheduled_at,
                record.executed_at,
                record.result,
                record.observed_blast_radius,
                record.learned_mtbf_adjustment,
                record.notes,
            ),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Risk forecast
    # ------------------------------------------------------------------

    def risk_forecast(self, horizon_days: int = 30) -> RiskForecast:
        """Forecast failure probability over *horizon_days* using Poisson model.

        Adjusts MTBF values based on recorded experiment results.
        """
        horizon_hours = horizon_days * 24.0
        component_risks: dict[str, float] = {}
        max_prob = 0.0

        for comp_id, comp in self.graph.components.items():
            mtbf = comp.operational_profile.mtbf_hours
            if mtbf <= 0:
                # No MTBF data — assume moderate risk
                component_risks[comp_id] = 0.5
                max_prob = max(max_prob, 0.5)
                continue

            # Apply learned adjustments from experiment history
            adjusted_mtbf = mtbf + self._total_mtbf_adjustment(comp_id)
            adjusted_mtbf = max(1.0, adjusted_mtbf)  # floor at 1 hour

            prob = _poisson_failure_probability(adjusted_mtbf, horizon_hours)
            component_risks[comp_id] = round(prob, 4)
            max_prob = max(max_prob, prob)

        # Critical incident probability: P(any component fails)
        # P(none fail) = product of (1-p_i)
        p_none_fail = 1.0
        for p in component_risks.values():
            p_none_fail *= (1.0 - p)
        critical_prob = round(1.0 - p_none_fail, 4)

        # Recommendation
        if critical_prob > 0.9:
            rec = "High risk of incident. Increase redundancy and conduct chaos experiments immediately."
        elif critical_prob > 0.5:
            rec = "Moderate risk. Schedule proactive chaos experiments this week."
        else:
            rec = "Risk is within acceptable levels. Continue regular testing cadence."

        return RiskForecast(
            horizon_days=horizon_days,
            critical_incident_probability=critical_prob,
            component_risks=component_risks,
            recommendation=rec,
        )

    # ------------------------------------------------------------------
    # Learning summary
    # ------------------------------------------------------------------

    def learning_summary(self) -> dict:
        """Summarise what has been learned from past experiments."""
        cur = self._conn.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN result='pass' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN result='fail' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN result='skipped' THEN 1 ELSE 0 END), "
            "AVG(observed_blast_radius), "
            "SUM(learned_mtbf_adjustment) "
            "FROM experiment_records"
        )
        row = cur.fetchone()
        total = row[0] or 0
        return {
            "total_experiments": total,
            "passed": row[1] or 0,
            "failed": row[2] or 0,
            "skipped": row[3] or 0,
            "avg_blast_radius": round(row[4] or 0.0, 4),
            "total_mtbf_adjustment_hours": round(row[5] or 0.0, 2),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _total_mtbf_adjustment(self, comp_id: str) -> float:
        """Sum of all MTBF adjustments for a given component from experiments."""
        cur = self._conn.execute(
            "SELECT SUM(learned_mtbf_adjustment) "
            "FROM experiment_records WHERE scenario_id = ?",
            (comp_id,),
        )
        row = cur.fetchone()
        return row[0] if row and row[0] else 0.0

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
