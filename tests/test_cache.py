"""Tests for ResultCache (SQLite-based simulation result caching)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from faultray.cache import ResultCache


@pytest.fixture
def tmp_cache(tmp_path: Path) -> ResultCache:
    """Create a ResultCache in a temporary directory."""
    return ResultCache(cache_dir=tmp_path)


@pytest.fixture
def sample_result() -> dict:
    return {
        "resilience_score": 85.0,
        "total_scenarios": 10,
        "critical_count": 1,
        "warning_count": 2,
        "passed_count": 7,
    }


# ---------------------------------------------------------------------------
# Basic CRUD operations
# ---------------------------------------------------------------------------


class TestResultCacheBasic:
    def test_put_and_get(self, tmp_cache: ResultCache, sample_result: dict):
        """put() then get() should return the cached result."""
        tmp_cache.put("abc123", "scenario-1", sample_result)
        cached = tmp_cache.get("abc123", "scenario-1")
        assert cached is not None
        assert cached["resilience_score"] == 85.0
        assert cached["critical_count"] == 1

    def test_get_missing_returns_none(self, tmp_cache: ResultCache):
        """get() for a nonexistent key should return None."""
        assert tmp_cache.get("nonexistent", "scenario-1") is None

    def test_put_overwrites(self, tmp_cache: ResultCache, sample_result: dict):
        """put() with the same key should overwrite the previous value."""
        tmp_cache.put("abc123", "scenario-1", sample_result)
        updated = {**sample_result, "resilience_score": 90.0}
        tmp_cache.put("abc123", "scenario-1", updated)
        cached = tmp_cache.get("abc123", "scenario-1")
        assert cached["resilience_score"] == 90.0

    def test_different_scenarios_independent(self, tmp_cache: ResultCache, sample_result: dict):
        """Different scenario_ids under the same graph_hash are independent."""
        tmp_cache.put("abc123", "scenario-1", sample_result)
        tmp_cache.put("abc123", "scenario-2", {**sample_result, "critical_count": 5})

        r1 = tmp_cache.get("abc123", "scenario-1")
        r2 = tmp_cache.get("abc123", "scenario-2")
        assert r1["critical_count"] == 1
        assert r2["critical_count"] == 5


# ---------------------------------------------------------------------------
# TTL / Expiry
# ---------------------------------------------------------------------------


class TestResultCacheTTL:
    def test_expired_entry_returns_none(self, tmp_cache: ResultCache, sample_result: dict):
        """Expired entries should return None and be auto-deleted."""
        # Insert with a very short TTL
        tmp_cache.put("abc123", "scenario-1", sample_result, ttl_hours=0)

        # Force expiry by inserting with created_at in the past
        import sqlite3

        with sqlite3.connect(str(tmp_cache.db_path)) as conn:
            conn.execute(
                "UPDATE result_cache SET created_at = ? WHERE graph_hash = ? AND scenario_id = ?",
                (time.time() - 7200, "abc123", "scenario-1"),
            )

        result = tmp_cache.get("abc123", "scenario-1")
        assert result is None

    def test_non_expired_entry_returned(self, tmp_cache: ResultCache, sample_result: dict):
        """Non-expired entries should be returned normally."""
        tmp_cache.put("abc123", "scenario-1", sample_result, ttl_hours=24)
        result = tmp_cache.get("abc123", "scenario-1")
        assert result is not None


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


class TestResultCacheInvalidation:
    def test_invalidate_all(self, tmp_cache: ResultCache, sample_result: dict):
        """invalidate() without args should clear all entries."""
        tmp_cache.put("abc123", "s1", sample_result)
        tmp_cache.put("def456", "s2", sample_result)

        deleted = tmp_cache.invalidate()
        assert deleted == 2
        assert tmp_cache.get("abc123", "s1") is None
        assert tmp_cache.get("def456", "s2") is None

    def test_invalidate_by_graph_hash(self, tmp_cache: ResultCache, sample_result: dict):
        """invalidate(graph_hash) should only remove matching entries."""
        tmp_cache.put("abc123", "s1", sample_result)
        tmp_cache.put("abc123", "s2", sample_result)
        tmp_cache.put("def456", "s3", sample_result)

        deleted = tmp_cache.invalidate("abc123")
        assert deleted == 2
        assert tmp_cache.get("abc123", "s1") is None
        assert tmp_cache.get("def456", "s3") is not None

    def test_invalidate_single_entry(self, tmp_cache: ResultCache, sample_result: dict):
        """invalidate_entry() should remove exactly one entry."""
        tmp_cache.put("abc123", "s1", sample_result)
        tmp_cache.put("abc123", "s2", sample_result)

        deleted = tmp_cache.invalidate_entry("abc123", "s1")
        assert deleted == 1
        assert tmp_cache.get("abc123", "s1") is None
        assert tmp_cache.get("abc123", "s2") is not None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestResultCacheStats:
    def test_stats_empty(self, tmp_cache: ResultCache):
        """stats() on empty cache should show 0 entries."""
        stats = tmp_cache.stats()
        assert stats["entries"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["size_bytes"] >= 0

    def test_stats_after_operations(self, tmp_cache: ResultCache, sample_result: dict):
        """stats() should reflect put/get operations."""
        tmp_cache.put("abc123", "s1", sample_result)
        tmp_cache.put("abc123", "s2", sample_result)

        # Hit
        tmp_cache.get("abc123", "s1")
        # Miss
        tmp_cache.get("nonexistent", "s1")

        stats = tmp_cache.stats()
        assert stats["entries"] == 2
        assert stats["hit_rate"] == 0.5  # 1 hit / 2 total
        assert stats["size_bytes"] > 0

    def test_stats_hit_rate_all_hits(self, tmp_cache: ResultCache, sample_result: dict):
        """hit_rate should be 1.0 when all gets are hits."""
        tmp_cache.put("abc123", "s1", sample_result)
        tmp_cache.get("abc123", "s1")
        tmp_cache.get("abc123", "s1")

        stats = tmp_cache.stats()
        assert stats["hit_rate"] == 1.0


# ---------------------------------------------------------------------------
# hash_graph
# ---------------------------------------------------------------------------


class TestHashGraph:
    def test_hash_graph_deterministic(self):
        """hash_graph() should produce consistent hashes."""
        mock_graph = MagicMock()
        mock_graph.to_dict.return_value = {
            "components": [{"id": "web", "name": "Web"}],
            "dependencies": [],
        }

        h1 = ResultCache.hash_graph(mock_graph)
        h2 = ResultCache.hash_graph(mock_graph)
        assert h1 == h2
        assert len(h1) == 16

    def test_hash_graph_different_for_different_graphs(self):
        """Different graphs should produce different hashes."""
        graph1 = MagicMock()
        graph1.to_dict.return_value = {"components": [{"id": "web"}], "dependencies": []}

        graph2 = MagicMock()
        graph2.to_dict.return_value = {"components": [{"id": "api"}], "dependencies": []}

        assert ResultCache.hash_graph(graph1) != ResultCache.hash_graph(graph2)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestResultCacheCleanup:
    def test_cleanup_expired(self, tmp_cache: ResultCache, sample_result: dict):
        """cleanup_expired() should remove only expired entries."""
        import sqlite3

        tmp_cache.put("abc123", "s1", sample_result, ttl_hours=1)
        tmp_cache.put("abc123", "s2", sample_result, ttl_hours=1)

        # Make s1 expired
        with sqlite3.connect(str(tmp_cache.db_path)) as conn:
            conn.execute(
                "UPDATE result_cache SET created_at = ? WHERE scenario_id = ?",
                (time.time() - 7200, "s1"),
            )

        deleted = tmp_cache.cleanup_expired()
        assert deleted == 1
        assert tmp_cache.get("abc123", "s1") is None
        # s2 is still valid -- get() should not fail
        # (we reset _misses counter effect from s1 deletion)

    def test_db_path_created(self, tmp_path: Path):
        """Cache directory should be created automatically."""
        cache_dir = tmp_path / "nested" / "cache"
        cache = ResultCache(cache_dir=cache_dir)
        assert cache.db_path.parent.exists()
