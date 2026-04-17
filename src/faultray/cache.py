# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""SQLite-based cache for simulation results."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class ResultCache:
    """SQLite-based cache for simulation results.

    Stores simulation results keyed by (graph_hash, scenario_id) so that
    identical simulations can be served from cache without re-computation.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.db_path = (cache_dir or Path.home() / ".faultray") / "cache.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0
        self._init_db()

    def _init_db(self) -> None:
        """Create the cache table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS result_cache (
                    graph_hash TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    ttl_hours INTEGER NOT NULL DEFAULT 24,
                    PRIMARY KEY (graph_hash, scenario_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cache_graph
                ON result_cache (graph_hash)
                """
            )

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to the cache database."""
        return sqlite3.connect(str(self.db_path))

    def get(self, graph_hash: str, scenario_id: str) -> dict | None:
        """Retrieve a cached result, or None if not found / expired."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT result_json, created_at, ttl_hours
                FROM result_cache
                WHERE graph_hash = ? AND scenario_id = ?
                """,
                (graph_hash, scenario_id),
            ).fetchone()

        if row is None:
            self._misses += 1
            return None

        result_json, created_at, ttl_hours = row
        age_hours = (time.time() - created_at) / 3600.0
        if age_hours > ttl_hours:
            # Expired -- remove and return None
            self.invalidate_entry(graph_hash, scenario_id)
            self._misses += 1
            return None

        self._hits += 1
        result: dict[str, object] = json.loads(result_json)
        return result

    def put(
        self,
        graph_hash: str,
        scenario_id: str,
        result: dict,
        ttl_hours: int = 24,
    ) -> None:
        """Store a result in the cache (upsert)."""
        result_json = json.dumps(result, sort_keys=True, default=str)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO result_cache
                    (graph_hash, scenario_id, result_json, created_at, ttl_hours)
                VALUES (?, ?, ?, ?, ?)
                """,
                (graph_hash, scenario_id, result_json, time.time(), ttl_hours),
            )

    def invalidate(self, graph_hash: str | None = None) -> int:
        """Delete cached entries.

        If *graph_hash* is given, only entries for that graph are removed.
        Otherwise, all entries are deleted.

        Returns:
            Number of deleted rows.
        """
        with self._connect() as conn:
            if graph_hash is not None:
                cursor = conn.execute(
                    "DELETE FROM result_cache WHERE graph_hash = ?",
                    (graph_hash,),
                )
            else:
                cursor = conn.execute("DELETE FROM result_cache")
            return cursor.rowcount

    def invalidate_entry(self, graph_hash: str, scenario_id: str) -> int:
        """Delete a single cached entry."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM result_cache WHERE graph_hash = ? AND scenario_id = ?",
                (graph_hash, scenario_id),
            )
            return cursor.rowcount

    def stats(self) -> dict:
        """Return cache statistics.

        Returns:
            Dict with ``entries``, ``size_bytes``, and ``hit_rate``.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM result_cache").fetchone()
            entries = row[0] if row else 0

        size_bytes = 0
        if self.db_path.exists():
            size_bytes = self.db_path.stat().st_size

        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "entries": entries,
            "size_bytes": size_bytes,
            "hit_rate": round(hit_rate, 4),
        }

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of deleted rows.
        """
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM result_cache
                WHERE (? - created_at) / 3600.0 > ttl_hours
                """,
                (now,),
            )
            return cursor.rowcount

    @staticmethod
    def hash_graph(graph: object) -> str:
        """Content-addressed hash of an InfraGraph.

        Uses the FULL SHA-256 hex digest (64 chars = 256 bits) over the
        JSON-serialized graph data with sorted keys.  The previous 16-char
        truncation (64 bits) had a birthday-paradox collision risk at
        around 4 billion entries — benign at present scale but unsafe for
        a content-addressed cache that silently returns the matching
        entry (a collision would serve the wrong result).
        """
        data = json.dumps(graph.to_dict(), sort_keys=True, default=str)  # type: ignore[attr-defined]
        return hashlib.sha256(data.encode()).hexdigest()
