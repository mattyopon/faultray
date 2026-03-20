# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Team Resilience Tracker.

Track and compare resilience metrics across teams/services over time.
Enables data-driven SRE performance management.

Features:
- Per-team resilience scoring
- Historical tracking
- Cross-team comparison
- Improvement velocity metrics
- Team resilience leaderboard
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# Default storage path
_HISTORY_DIR = Path.home() / ".faultzero"
_HISTORY_FILE = _HISTORY_DIR / "team_history.jsonl"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TeamMetrics:
    """Resilience metrics for a single team."""

    team_name: str
    components_owned: list[str]
    resilience_score: float
    spof_count: int
    critical_findings: int
    failover_coverage: float
    circuit_breaker_coverage: float
    sre_maturity_level: int
    annual_risk_estimate: float


@dataclass
class TeamSnapshot:
    """A timestamped snapshot of team metrics."""

    timestamp: str  # ISO format string for serialization
    team_name: str
    metrics: TeamMetrics


@dataclass
class TeamComparison:
    """Comparison of resilience across multiple teams."""

    teams: list[TeamMetrics]
    leader: str
    laggard: str
    avg_score: float
    score_spread: float
    improvement_areas: dict[str, list[str]]


@dataclass
class TeamLeaderboard:
    """Ranked list of teams by resilience score."""

    rankings: list[tuple[int, str, float]]
    most_improved: str | None
    needs_attention: list[str]


# ---------------------------------------------------------------------------
# Auto team assignment
# ---------------------------------------------------------------------------


def auto_assign_teams(graph: InfraGraph) -> dict[str, list[str]]:
    """Automatically assign components to teams based on naming conventions.

    Components are categorized by keywords in their name and type:
    - backend: api, web, app, server
    - data: db, postgres, mysql, redis, cache, aurora, dynamodb
    - platform: lb, nginx, cdn, dns, gateway, waf
    - messaging: kafka, sqs, queue, rabbit, mqtt
    - other: anything not matching above

    Args:
        graph: The infrastructure graph.

    Returns:
        Dict mapping team name to list of component IDs.
    """
    mapping: dict[str, list[str]] = {}
    for comp in graph.components.values():
        name_lower = comp.name.lower()
        comp_type = comp.type.value.lower()

        if any(p in name_lower for p in ["lb", "nginx", "cdn", "dns", "gateway", "waf"]) or comp_type in ("load_balancer", "dns"):
            team = "platform"
        elif any(p in name_lower for p in ["kafka", "sqs", "queue", "rabbit", "mqtt"]) or comp_type == "queue":
            team = "messaging"
        elif any(p in name_lower for p in ["db", "postgres", "mysql", "redis", "cache", "aurora", "dynamodb"]) or comp_type in ("database", "cache"):
            team = "data"
        elif any(p in name_lower for p in ["api", "web", "app", "server", "lambda", "service", "worker"]) or comp_type in ("app_server", "web_server"):
            team = "backend"
        else:
            team = "other"

        mapping.setdefault(team, []).append(comp.id)

    return mapping


# ---------------------------------------------------------------------------
# TeamTracker
# ---------------------------------------------------------------------------


class TeamTracker:
    """Track and compare team resilience metrics over time."""

    def __init__(self, history_path: Path | None = None) -> None:
        self._history_path = history_path or _HISTORY_FILE

    def analyze_teams(
        self, graph: InfraGraph, team_mapping: dict[str, list[str]]
    ) -> list[TeamMetrics]:
        """Analyze resilience metrics for each team.

        Args:
            graph: The infrastructure graph.
            team_mapping: Dict mapping team name to list of component IDs.

        Returns:
            List of TeamMetrics, one per team.
        """
        results: list[TeamMetrics] = []

        for team_name, comp_ids in sorted(team_mapping.items()):
            # Filter to components that exist in the graph
            owned = [cid for cid in comp_ids if cid in graph.components]
            if not owned:
                continue

            # SPOF count: components with replicas <= 1 and dependents
            spof_count = 0
            for cid in owned:
                comp = graph.components[cid]
                dependents = graph.get_dependents(cid)
                if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
                    spof_count += 1

            # Failover coverage: fraction of owned components with failover enabled
            failover_count = sum(
                1 for cid in owned if graph.components[cid].failover.enabled
            )
            failover_coverage = failover_count / len(owned) if owned else 0.0

            # Circuit breaker coverage: fraction of edges from owned components with CB
            team_edges_total = 0
            team_edges_cb = 0
            for cid in owned:
                for dep in graph.get_dependencies(cid):
                    edge = graph.get_dependency_edge(cid, dep.id)
                    if edge:
                        team_edges_total += 1
                        if edge.circuit_breaker.enabled:
                            team_edges_cb += 1
            cb_coverage = team_edges_cb / team_edges_total if team_edges_total > 0 else 0.0

            # SRE maturity level (1-5)
            maturity = 1
            if failover_coverage >= 0.3:
                maturity += 1
            if cb_coverage >= 0.3:
                maturity += 1
            if spof_count == 0:
                maturity += 1
            has_autoscaling = any(
                graph.components[cid].autoscaling.enabled for cid in owned
            )
            if has_autoscaling:
                maturity += 1
            maturity = min(5, maturity)

            # Build sub-graph for team-specific resilience score
            team_score = self._calculate_team_score(graph, owned)

            # Critical findings count based on SPOFs and missing CB
            critical = spof_count + (team_edges_total - team_edges_cb)

            # Annual risk estimate (simplified)
            # Higher SPOFs and lower scores -> higher risk
            base_risk = 50000.0  # base annual risk per SPOF
            risk = spof_count * base_risk * (1.0 - team_score / 100.0)

            results.append(
                TeamMetrics(
                    team_name=team_name,
                    components_owned=owned,
                    resilience_score=round(team_score, 1),
                    spof_count=spof_count,
                    critical_findings=critical,
                    failover_coverage=round(failover_coverage * 100, 1),
                    circuit_breaker_coverage=round(cb_coverage * 100, 1),
                    sre_maturity_level=maturity,
                    annual_risk_estimate=round(risk, 2),
                )
            )

        return results

    def compare_teams(
        self, graph: InfraGraph, team_mapping: dict[str, list[str]]
    ) -> TeamComparison:
        """Compare resilience metrics across teams.

        Args:
            graph: The infrastructure graph.
            team_mapping: Dict mapping team name to list of component IDs.

        Returns:
            TeamComparison with leader, laggard, and improvement areas.
        """
        teams = self.analyze_teams(graph, team_mapping)
        if not teams:
            return TeamComparison(
                teams=[],
                leader="",
                laggard="",
                avg_score=0.0,
                score_spread=0.0,
                improvement_areas={},
            )

        scores = [(t.team_name, t.resilience_score) for t in teams]
        scores.sort(key=lambda x: x[1], reverse=True)

        leader = scores[0][0]
        laggard = scores[-1][0]
        avg_score = sum(s for _, s in scores) / len(scores)
        score_spread = scores[0][1] - scores[-1][1]

        # Identify improvement areas per team
        improvement_areas: dict[str, list[str]] = {}
        for t in teams:
            areas: list[str] = []
            if t.spof_count > 0:
                areas.append(f"Eliminate {t.spof_count} single point(s) of failure")
            if t.failover_coverage < 50.0:
                areas.append(f"Increase failover coverage (currently {t.failover_coverage:.0f}%)")
            if t.circuit_breaker_coverage < 50.0:
                areas.append(f"Add circuit breakers (currently {t.circuit_breaker_coverage:.0f}%)")
            if t.sre_maturity_level < 3:
                areas.append(f"Improve SRE maturity (currently level {t.sre_maturity_level})")
            if areas:
                improvement_areas[t.team_name] = areas

        return TeamComparison(
            teams=teams,
            leader=leader,
            laggard=laggard,
            avg_score=round(avg_score, 1),
            score_spread=round(score_spread, 1),
            improvement_areas=improvement_areas,
        )

    def record_snapshot(
        self, graph: InfraGraph, team_mapping: dict[str, list[str]]
    ) -> None:
        """Record a timestamped snapshot of team metrics.

        Appends to JSON Lines file at ~/.faultzero/team_history.jsonl.
        """
        teams = self.analyze_teams(graph, team_mapping)
        timestamp = datetime.now().isoformat()

        self._history_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self._history_path, "a", encoding="utf-8") as f:
            for tm in teams:
                snapshot = TeamSnapshot(
                    timestamp=timestamp,
                    team_name=tm.team_name,
                    metrics=tm,
                )
                f.write(json.dumps(asdict(snapshot), default=str) + "\n")

        logger.info(
            "Recorded snapshot for %d teams at %s", len(teams), timestamp
        )

    def get_leaderboard(
        self, graph: InfraGraph, team_mapping: dict[str, list[str]]
    ) -> TeamLeaderboard:
        """Get team rankings by resilience score.

        Args:
            graph: The infrastructure graph.
            team_mapping: Dict mapping team name to list of component IDs.

        Returns:
            TeamLeaderboard with rankings, most improved, and attention list.
        """
        teams = self.analyze_teams(graph, team_mapping)
        if not teams:
            return TeamLeaderboard(rankings=[], most_improved=None, needs_attention=[])

        # Sort by score descending
        sorted_teams = sorted(teams, key=lambda t: t.resilience_score, reverse=True)
        rankings = [
            (rank + 1, t.team_name, t.resilience_score)
            for rank, t in enumerate(sorted_teams)
        ]

        # Determine most improved by comparing with last snapshot
        most_improved: str | None = None
        history = self._load_history()
        if history:
            improvements: dict[str, float] = {}
            current_scores = {t.team_name: t.resilience_score for t in teams}
            for team_name, current_score in current_scores.items():
                past = [
                    s for s in history if s["team_name"] == team_name
                ]
                if past:
                    last_score = past[-1]["metrics"]["resilience_score"]
                    improvements[team_name] = current_score - last_score
            if improvements:
                best_team = max(improvements, key=improvements.get)  # type: ignore[arg-type]
                if improvements[best_team] > 0:
                    most_improved = best_team

        # Teams needing attention: low score or high SPOFs
        needs_attention = [
            t.team_name for t in teams
            if t.resilience_score < 50.0 or t.spof_count > 2
        ]

        return TeamLeaderboard(
            rankings=rankings,
            most_improved=most_improved,
            needs_attention=needs_attention,
        )

    def get_team_history(
        self, team_name: str, days: int = 90
    ) -> list[TeamSnapshot]:
        """Get historical snapshots for a specific team.

        Args:
            team_name: Name of the team.
            days: Number of days to look back.

        Returns:
            List of TeamSnapshot in chronological order.
        """
        history = self._load_history()
        cutoff = datetime.now().timestamp() - (days * 86400)

        snapshots: list[TeamSnapshot] = []
        for entry in history:
            if entry["team_name"] != team_name:
                continue
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
                if ts.timestamp() >= cutoff:
                    metrics = TeamMetrics(**entry["metrics"])
                    snapshots.append(
                        TeamSnapshot(
                            timestamp=entry["timestamp"],
                            team_name=team_name,
                            metrics=metrics,
                        )
                    )
            except (ValueError, KeyError):
                continue

        return snapshots

    def auto_assign_teams(self, graph: InfraGraph) -> dict[str, list[str]]:
        """Auto-assign components to teams based on naming conventions.

        Convenience wrapper around the module-level function.
        """
        return auto_assign_teams(graph)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_team_score(
        self, graph: InfraGraph, component_ids: list[str]
    ) -> float:
        """Calculate a resilience score for a subset of components."""
        if not component_ids:
            return 0.0

        score = 100.0

        for cid in component_ids:
            comp = graph.components[cid]
            dependents = graph.get_dependents(cid)

            # SPOF penalty
            if comp.replicas <= 1 and len(dependents) > 0:
                penalty = min(20.0, len(dependents) * 5.0)
                if comp.failover.enabled:
                    penalty *= 0.3
                if comp.autoscaling.enabled:
                    penalty *= 0.5
                score -= penalty

            # High utilization penalty
            util = comp.utilization()
            if util > 90:
                score -= 10
            elif util > 80:
                score -= 5

        # Circuit breaker coverage bonus/penalty
        cb_total = 0
        cb_enabled = 0
        for cid in component_ids:
            for dep in graph.get_dependencies(cid):
                edge = graph.get_dependency_edge(cid, dep.id)
                if edge:
                    cb_total += 1
                    if edge.circuit_breaker.enabled:
                        cb_enabled += 1
        if cb_total > 0:
            cb_ratio = cb_enabled / cb_total
            if cb_ratio < 0.5:
                score -= 10

        return max(0.0, min(100.0, score))

    def _load_history(self) -> list[dict]:
        """Load all history entries from the JSONL file."""
        if not self._history_path.exists():
            return []

        entries: list[dict] = []
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            logger.warning("Could not read team history from %s", self._history_path)

        return entries
