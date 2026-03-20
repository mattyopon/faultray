# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Shared theme constants for FaultRay."""

SEVERITY_COLORS = {
    "critical": "#dc3545",
    "high": "#fd7e14",
    "medium": "#ffc107",
    "low": "#28a745",
    "info": "#17a2b8",
}

HEALTH_COLORS = {
    "healthy": "#28a745",
    "degraded": "#ffc107",
    "overloaded": "#fd7e14",
    "down": "#dc3545",
}

SCORE_COLORS = {
    "excellent": "#28a745",  # 80-100
    "good": "#17a2b8",       # 60-79
    "fair": "#ffc107",       # 40-59
    "poor": "#fd7e14",       # 20-39
    "critical": "#dc3545",   # 0-19
}


def score_to_color(score: float) -> str:
    """Return the theme color for a resilience score (0-100)."""
    if score >= 80:
        return SCORE_COLORS["excellent"]
    if score >= 60:
        return SCORE_COLORS["good"]
    if score >= 40:
        return SCORE_COLORS["fair"]
    if score >= 20:
        return SCORE_COLORS["poor"]
    return SCORE_COLORS["critical"]


def severity_to_color(severity: str) -> str:
    """Return the theme color for a severity level string."""
    return SEVERITY_COLORS.get(severity.lower(), "#8b949e")
