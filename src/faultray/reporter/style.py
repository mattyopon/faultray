# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Shared severity thresholds and cascade-time helpers for report formats.

Console (Rich), HTML, PDF/Markdown and diff reports each render scores and
cascades in their own style, but the *cutoffs* and the running time-delta
logic must agree across formats. They live here so the formats cannot drift.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from faultray.model.components import HealthStatus

# Resilience score cutoffs (0-100 scale).
SCORE_GOOD = 80.0
SCORE_FAIR = 60.0

# Risk score cutoffs (0-10 scale).
RISK_CRITICAL = 7.0
RISK_WARNING = 4.0

# Utilization cutoffs (percent).
UTIL_HIGH = 80.0
UTIL_ELEVATED = 60.0


def score_bucket(score: float) -> str:
    """Bucket a 0-100 resilience score into ``good`` / ``fair`` / ``poor``."""
    if score >= SCORE_GOOD:
        return "good"
    if score >= SCORE_FAIR:
        return "fair"
    return "poor"


def risk_bucket(score: float) -> str:
    """Bucket a 0-10 risk score into ``critical`` / ``warning`` / ``low``."""
    if score >= RISK_CRITICAL:
        return "critical"
    if score >= RISK_WARNING:
        return "warning"
    return "low"


def util_bucket(util: float) -> str:
    """Bucket a utilization percentage into ``high`` / ``elevated`` / ``normal``."""
    if util > UTIL_HIGH:
        return "high"
    if util > UTIL_ELEVATED:
        return "elevated"
    return "normal"


# Canonical short status labels. Formats that need different casing or
# styling wrap these rather than maintaining their own tables.
HEALTH_LABELS: dict[HealthStatus, str] = {
    HealthStatus.HEALTHY: "OK",
    HealthStatus.DEGRADED: "WARN",
    HealthStatus.OVERLOADED: "OVERLOAD",
    HealthStatus.DOWN: "DOWN",
}


def health_label(health: HealthStatus, default: str = "?") -> str:
    return HEALTH_LABELS.get(health, default)


def iter_effects_with_delta(
    effects: Iterable[Any],
) -> Iterator[tuple[Any, int | None]]:
    """Yield ``(effect, delta_seconds)`` for a cascade effect sequence.

    ``delta_seconds`` is the time elapsed since the previous timed effect, or
    ``None`` for effects that carry no timing. Every report format used to
    reimplement this running-delta loop.
    """
    prev_time = 0
    for eff in effects:
        if eff.estimated_time_seconds > 0:
            delta = eff.estimated_time_seconds - prev_time
            prev_time = eff.estimated_time_seconds
            yield eff, delta
        else:
            yield eff, None
