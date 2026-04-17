# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Resilience Leaderboard API.

Provides a competitive scoring system where teams can submit their
infrastructure resilience scores, earn badges, and track improvements
over time.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ScoreSubmission(BaseModel):
    """Request body for submitting a resilience score."""

    team_name: str = Field(..., min_length=1, max_length=100)
    score: float = Field(..., ge=0.0, le=100.0)
    components: int = Field(0, ge=0)
    security_score: float = Field(0.0, ge=0.0, le=100.0)


@dataclass
class LeaderboardEntry:
    """A single entry on the leaderboard."""

    team_name: str
    score: float
    rank: int = 0
    score_delta: float = 0.0  # change from last submission
    badges: list[str] = field(default_factory=list)
    submitted_at: float = 0.0  # unix timestamp
    components: int = 0


# ---------------------------------------------------------------------------
# Badge system
# ---------------------------------------------------------------------------


def _check_slo_champion(score: float, **_kwargs) -> bool:
    """Score >= 95 earns the SLO Champion badge."""
    return score >= 95.0


def _check_spof_slayer(graph: InfraGraph | None = None, **_kwargs) -> bool:
    """All components have replicas >= 2."""
    if graph is None:
        return False
    return all(c.replicas >= 2 for c in graph.components.values())


def _check_security_ace(security_score: float = 0.0, **_kwargs) -> bool:
    """Security score >= 90 earns the Security Ace badge."""
    return security_score >= 90.0


def _check_rising_star(delta: float = 0.0, **_kwargs) -> bool:
    """Score improvement >= 10 points earns Rising Star."""
    return delta >= 10.0


def _check_iron_fortress(score: float = 0.0, **_kwargs) -> bool:
    """Perfect score of 100 earns Iron Fortress."""
    return score >= 100.0


def _check_first_steps(score: float = 0.0, **_kwargs) -> bool:
    """Any score > 0 earns First Steps (participation badge)."""
    return score > 0.0


BADGE_CRITERIA: dict[str, dict] = {
    "slo_champion": {
        "check": _check_slo_champion,
        "description": "Achieved a resilience score of 95+",
        "icon": "trophy",
    },
    "spof_slayer": {
        "check": _check_spof_slayer,
        "description": "Eliminated all single points of failure (all replicas >= 2)",
        "icon": "shield",
    },
    "security_ace": {
        "check": _check_security_ace,
        "description": "Security score of 90+",
        "icon": "lock",
    },
    "rising_star": {
        "check": _check_rising_star,
        "description": "Improved score by 10+ points",
        "icon": "star",
    },
    "iron_fortress": {
        "check": _check_iron_fortress,
        "description": "Achieved a perfect score of 100",
        "icon": "castle",
    },
    "first_steps": {
        "check": _check_first_steps,
        "description": "Submitted first resilience score",
        "icon": "footprints",
    },
}


def evaluate_badges(
    score: float,
    delta: float = 0.0,
    security_score: float = 0.0,
    graph: InfraGraph | None = None,
) -> list[str]:
    """Evaluate which badges a team has earned.

    Parameters
    ----------
    score:
        Current resilience score (0-100).
    delta:
        Change from previous score.
    security_score:
        Security assessment score (0-100).
    graph:
        Optional infrastructure graph for SPOF analysis.

    Returns
    -------
    list[str]
        List of earned badge identifiers.
    """
    earned: list[str] = []
    for badge_id, badge_info in BADGE_CRITERIA.items():
        check_fn = badge_info["check"]
        try:
            if check_fn(
                score=score,
                delta=delta,
                security_score=security_score,
                graph=graph,
            ):
                earned.append(badge_id)
        except Exception:
            logger.debug("Badge check failed for %s", badge_id, exc_info=True)
    return earned


# ---------------------------------------------------------------------------
# In-memory leaderboard store
# ---------------------------------------------------------------------------


class LeaderboardStore:
    """In-memory leaderboard storage.

    Thread-safety note: this is a simple in-memory store suitable for
    single-process deployments.  For production use, replace with a
    database-backed store.
    """

    def __init__(self) -> None:
        self._entries: dict[str, LeaderboardEntry] = {}
        self._history: dict[str, list[float]] = {}  # team -> list of scores

    def submit(
        self,
        team_name: str,
        score: float,
        components: int = 0,
        security_score: float = 0.0,
        graph: InfraGraph | None = None,
    ) -> LeaderboardEntry:
        """Submit or update a team's score.

        Returns the updated :class:`LeaderboardEntry` with rank and badges.
        """
        # Calculate delta
        previous_scores = self._history.get(team_name, [])
        if previous_scores:
            delta = score - previous_scores[-1]
        else:
            delta = 0.0

        # Record in history
        if team_name not in self._history:
            self._history[team_name] = []
        self._history[team_name].append(score)

        # Evaluate badges
        badges = evaluate_badges(
            score=score,
            delta=delta,
            security_score=security_score,
            graph=graph,
        )

        entry = LeaderboardEntry(
            team_name=team_name,
            score=score,
            score_delta=delta,
            badges=badges,
            submitted_at=time.time(),
            components=components,
        )
        self._entries[team_name] = entry

        # Recalculate ranks
        self._recalculate_ranks()

        return entry

    def get_leaderboard(self, limit: int = 50) -> list[LeaderboardEntry]:
        """Get the leaderboard sorted by score descending.

        Parameters
        ----------
        limit:
            Maximum number of entries to return.
        """
        self._recalculate_ranks()
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: e.score,
            reverse=True,
        )
        return sorted_entries[:limit]

    def get_team(self, team_name: str) -> LeaderboardEntry | None:
        """Get a specific team's entry."""
        return self._entries.get(team_name)

    def get_team_history(self, team_name: str) -> list[float]:
        """Get the score history for a team."""
        return list(self._history.get(team_name, []))

    def clear(self) -> None:
        """Clear all leaderboard data."""
        self._entries.clear()
        self._history.clear()

    def _recalculate_ranks(self) -> None:
        """Recalculate ranks for all entries."""
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: e.score,
            reverse=True,
        )
        for i, entry in enumerate(sorted_entries, 1):
            entry.rank = i


# Global leaderboard instance
_leaderboard = LeaderboardStore()


def get_leaderboard_store() -> LeaderboardStore:
    """Get the global leaderboard store instance."""
    return _leaderboard


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

leaderboard_router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])


@leaderboard_router.get("/")
async def get_leaderboard(limit: int = 50):
    """Get the resilience leaderboard.

    Returns teams ranked by their resilience score with badges.
    """
    store = get_leaderboard_store()
    entries = store.get_leaderboard(limit=limit)

    return {
        "leaderboard": [
            {
                "rank": e.rank,
                "team_name": e.team_name,
                "score": round(e.score, 1),
                "score_delta": round(e.score_delta, 1),
                "badges": e.badges,
                "components": e.components,
                "submitted_at": e.submitted_at,
            }
            for e in entries
        ],
        "total_teams": len(entries),
    }


@leaderboard_router.post("/submit")
async def submit_score(submission: ScoreSubmission):
    """Submit a team's resilience score.

    Evaluates badges and updates the leaderboard ranking.
    """
    store = get_leaderboard_store()
    entry = store.submit(
        team_name=submission.team_name,
        score=submission.score,
        components=submission.components,
        security_score=submission.security_score,
    )

    return {
        "team_name": entry.team_name,
        "score": round(entry.score, 1),
        "rank": entry.rank,
        "score_delta": round(entry.score_delta, 1),
        "badges": entry.badges,
    }


@leaderboard_router.get("/team/{team_name}")
async def get_team(team_name: str):
    """Get a specific team's leaderboard entry and history."""
    store = get_leaderboard_store()
    entry = store.get_team(team_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_name}' not found")

    history = store.get_team_history(team_name)

    return {
        "team_name": entry.team_name,
        "score": round(entry.score, 1),
        "rank": entry.rank,
        "score_delta": round(entry.score_delta, 1),
        "badges": entry.badges,
        "history": history,
        "components": entry.components,
    }


@leaderboard_router.get("/badges")
async def list_badges():
    """List all available badges and their criteria."""
    return {
        "badges": [
            {
                "id": badge_id,
                "description": info["description"],
                "icon": info["icon"],
            }
            for badge_id, info in BADGE_CRITERIA.items()
        ],
    }
