"""Regression: RateLimiter periodic expired-sweep (#103).

Before #103, `_cleanup()` only fired when `len(self.requests) > MAX_KEYS`
(10,000). With fewer keys, expired entries accumulated forever in the
defaultdict — a slow-but-real memory leak on long-running servers with
moderate unique-IP traffic.

Fix: add a `CLEANUP_INTERVAL_SECONDS` bound so the sweep runs on a
time-based schedule regardless of total key count.
"""

from __future__ import annotations

import time

import pytest

from faultray.api.server import RateLimiter


def test_expired_keys_are_swept_below_max_keys_after_interval(monkeypatch):
    """Stale keys get evicted once CLEANUP_INTERVAL_SECONDS elapses, even
    when the total key count is far below MAX_KEYS."""
    # Shrink interval and window so the test runs quickly.
    rl = RateLimiter(max_requests=10, window_seconds=1)
    rl.CLEANUP_INTERVAL_SECONDS = 0  # cleanup every call for determinism

    # Seed 100 unique "clients" — well below MAX_KEYS=10,000.
    for i in range(100):
        assert rl.is_allowed(f"client-{i}") is True

    assert len(rl.requests) == 100

    # Wait past the window so every entry is expired.
    time.sleep(1.1)

    # A single call from one new client should trigger _cleanup() because
    # CLEANUP_INTERVAL_SECONDS=0 → always run. All 100 stale keys must be
    # evicted; only the new caller's one key remains.
    rl.is_allowed("fresh-client")

    assert "fresh-client" in rl.requests
    assert len(rl.requests) == 1, (
        f"expected only 1 live key after expired sweep, saw {len(rl.requests)}: "
        f"{list(rl.requests)[:10]}..."
    )


def test_interval_default_bounded_to_reasonable_value():
    """CLEANUP_INTERVAL_SECONDS must be set to a positive finite number
    so the sweep runs at least occasionally; guards against accidental
    regressions that would disable the soft cap."""
    assert 1 <= RateLimiter.CLEANUP_INTERVAL_SECONDS <= 300


def test_cleanup_preserves_active_client_requests(monkeypatch):
    """A client who just made requests must not be swept out by the
    periodic sweep."""
    rl = RateLimiter(max_requests=10, window_seconds=60)
    rl.CLEANUP_INTERVAL_SECONDS = 0  # always cleanup

    # Active client — all timestamps are fresh.
    for _ in range(3):
        rl.is_allowed("active")

    # Stale client — fabricate an expired timestamp directly.
    rl.requests["stale"].append(time.time() - 9999)

    # Trigger cleanup via a new call from any client.
    rl.is_allowed("active")

    assert "active" in rl.requests
    assert "stale" not in rl.requests


def test_hard_cap_still_enforced_when_over_max_keys(monkeypatch):
    """The MAX_KEYS hard-cap path must still evict down to MAX_KEYS even
    when nothing is expired yet."""
    rl = RateLimiter(max_requests=10, window_seconds=60)
    rl.MAX_KEYS = 5
    rl.CLEANUP_INTERVAL_SECONDS = 9999  # disable time-based path

    for i in range(10):
        rl.is_allowed(f"k{i}")

    # After the 10th call, _cleanup() should have run (over MAX_KEYS).
    assert len(rl.requests) <= rl.MAX_KEYS, (
        f"hard cap failed: len={len(rl.requests)} but MAX_KEYS={rl.MAX_KEYS}"
    )
