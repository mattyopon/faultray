"""API Versioning and Rate Limiting.

Provides:
- API version prefix management (/api/v1/, /api/v2/)
- Rate limiting per API key
- Usage tracking
- API health endpoint
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# API Version registry
# ---------------------------------------------------------------------------

@dataclass
class APIVersion:
    """Describes a single API version and its lifecycle status."""

    version: str  # e.g. "v1", "v2"
    status: str  # "stable", "beta", "deprecated"
    release_date: str  # ISO-8601 date string
    deprecation_date: str | None = None
    changelog: list[str] = field(default_factory=list)


# Pre-defined versions shipped with the product
API_VERSIONS: dict[str, APIVersion] = {
    "v1": APIVersion(
        version="v1",
        status="stable",
        release_date="2025-01-15",
        deprecation_date=None,
        changelog=[
            "Initial public API release",
            "Topology, simulation, compliance endpoints",
            "Badge generation and calendar support",
        ],
    ),
    "v2": APIVersion(
        version="v2",
        status="beta",
        release_date="2026-03-01",
        deprecation_date=None,
        changelog=[
            "Enhanced dashboard summary endpoint",
            "API health check endpoint",
            "Improved rate limiting with tiered access",
            "Usage tracking per API key",
        ],
    ),
}


def list_versions() -> list[dict]:
    """Return all registered API versions as serialisable dicts."""
    return [
        {
            "version": v.version,
            "status": v.status,
            "release_date": v.release_date,
            "deprecation_date": v.deprecation_date,
            "changelog": v.changelog,
        }
        for v in API_VERSIONS.values()
    ]


# ---------------------------------------------------------------------------
# Tiered rate limiter
# ---------------------------------------------------------------------------

# Default limits per tier (requests per minute)
TIER_LIMITS: dict[str, int] = {
    "free": 30,
    "basic": 120,
    "pro": 600,
    "enterprise": 3000,
    "internal": 10_000,
}


class RateLimiter:
    """In-memory sliding-window rate limiter with tier support.

    Each ``api_key`` is mapped to a tier via :meth:`set_tier`.  Unknown keys
    default to the *free* tier.
    """

    def __init__(self, window_seconds: int = 60):
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._tiers: dict[str, str] = {}  # api_key -> tier name
        self._usage: dict[str, int] = defaultdict(int)  # total lifetime calls

    # -- tier management -----------------------------------------------------

    def set_tier(self, api_key: str, tier: str) -> None:
        """Assign *api_key* to a rate-limit tier."""
        if tier not in TIER_LIMITS:
            raise ValueError(f"Unknown tier '{tier}'. Choose from {sorted(TIER_LIMITS)}")
        self._tiers[api_key] = tier

    def _limit_for(self, api_key: str) -> int:
        tier = self._tiers.get(api_key, "free")
        return TIER_LIMITS.get(tier, TIER_LIMITS["free"])

    # -- core API ------------------------------------------------------------

    def check_limit(self, api_key: str, endpoint: str = "") -> bool:
        """Return ``True`` if the request is allowed, ``False`` if rate-limited.

        A side-effect is that an allowed request is recorded in the sliding
        window so that subsequent calls see updated counts.
        """
        now = time.time()
        key = api_key  # could combine with endpoint for per-endpoint limits
        window_start = now - self.window

        # Prune old entries
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        if len(self._requests[key]) >= self._limit_for(api_key):
            return False

        self._requests[key].append(now)
        self._usage[api_key] += 1
        return True

    def get_remaining(self, api_key: str) -> int:
        """Return how many requests remain in the current window."""
        now = time.time()
        window_start = now - self.window
        self._requests[api_key] = [
            t for t in self._requests[api_key] if t > window_start
        ]
        limit = self._limit_for(api_key)
        return max(0, limit - len(self._requests[api_key]))

    def reset_time(self, api_key: str) -> datetime:
        """Return the UTC datetime when the oldest request in the window expires."""
        now = time.time()
        window_start = now - self.window
        timestamps = [t for t in self._requests.get(api_key, []) if t > window_start]
        if not timestamps:
            return datetime.now(timezone.utc)
        oldest = min(timestamps)
        reset_epoch = oldest + self.window
        return datetime.fromtimestamp(reset_epoch, tz=timezone.utc)

    def get_usage(self, api_key: str) -> int:
        """Return the total number of requests ever recorded for *api_key*."""
        return self._usage.get(api_key, 0)


# Module-level singleton used by the server
rate_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# API Health Check
# ---------------------------------------------------------------------------

_start_time = time.time()


class APIHealthCheck:
    """Lightweight health probe for the FaultRay API."""

    def __init__(self, version: str = "2.1.0"):
        self.version = version

    def check(self, component_count: int = 0) -> dict:
        """Return a health status dict suitable for JSON serialisation."""
        uptime_seconds = time.time() - _start_time
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)

        return {
            "status": "healthy",
            "version": self.version,
            "uptime": f"{hours}h {minutes}m {seconds}s",
            "uptime_seconds": round(uptime_seconds, 1),
            "components_loaded": component_count,
            "api_versions": list_versions(),
            "rate_limit_tiers": TIER_LIMITS,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


health_checker = APIHealthCheck()
