# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Append-only audit chain for simulation evidence.

Implements a hash-chain audit log where each entry includes the hash
of the previous entry, creating a tamper-evident sequence similar to
a blockchain but without consensus overhead.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class AuditEntry:
    """A single entry in the audit chain."""
    sequence: int
    timestamp: str  # ISO 8601 UTC
    action: str  # e.g., "simulation_run", "report_generated", "topology_loaded"
    actor: str  # e.g., "user@email.com", "api_key:xxx", "system"
    details: str  # Human-readable description
    data_hash: str  # SHA-256 of the action's data
    previous_hash: str  # Hash of the previous entry (chain link)
    entry_hash: str  # Hash of this entry (including previous_hash)


class AuditChain:
    """Append-only hash-chain audit log."""

    GENESIS_HASH = "0" * 64  # Genesis block hash

    def __init__(self, log_path: Path | None = None) -> None:
        self._entries: list[AuditEntry] = []
        self._log_path = log_path or Path.home() / ".faultray" / "audit_chain.jsonl"
        self._load()

    def append(
        self,
        action: str,
        actor: str,
        details: str,
        data: str = "",
    ) -> AuditEntry:
        """Append a new entry to the audit chain."""
        sequence = len(self._entries)
        previous_hash = self._entries[-1].entry_hash if self._entries else self.GENESIS_HASH
        timestamp = datetime.now(timezone.utc).isoformat()
        data_hash = hashlib.sha256(data.encode()).hexdigest()

        # Create entry hash from all fields including previous hash
        entry_payload = f"{sequence}|{timestamp}|{action}|{actor}|{data_hash}|{previous_hash}"
        entry_hash = hashlib.sha256(entry_payload.encode()).hexdigest()

        entry = AuditEntry(
            sequence=sequence,
            timestamp=timestamp,
            action=action,
            actor=actor,
            details=details,
            data_hash=data_hash,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
        )

        self._entries.append(entry)
        self._persist(entry)
        return entry

    def verify_integrity(self) -> tuple[bool, str]:
        """Verify the entire chain has not been tampered with."""
        if not self._entries:
            return True, "Empty chain"

        for i, entry in enumerate(self._entries):
            # Check sequence
            if entry.sequence != i:
                return False, f"Sequence mismatch at entry {i}: expected {i}, got {entry.sequence}"

            # Check previous hash linkage
            expected_prev = self._entries[i - 1].entry_hash if i > 0 else self.GENESIS_HASH
            if entry.previous_hash != expected_prev:
                return False, f"Chain broken at entry {i}: previous_hash mismatch"

            # Verify entry hash
            entry_payload = (
                f"{entry.sequence}|{entry.timestamp}|{entry.action}"
                f"|{entry.actor}|{entry.data_hash}|{entry.previous_hash}"
            )
            expected_hash = hashlib.sha256(entry_payload.encode()).hexdigest()
            if entry.entry_hash != expected_hash:
                return False, f"Entry hash tampered at entry {i}"

        return True, f"Chain valid: {len(self._entries)} entries"

    def get_entries(self, action: str | None = None, limit: int = 100) -> list[AuditEntry]:
        """Retrieve audit entries, optionally filtered by action."""
        entries = self._entries
        if action:
            entries = [e for e in entries if e.action == action]
        return entries[-limit:]

    @property
    def length(self) -> int:
        return len(self._entries)

    @property
    def last_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else self.GENESIS_HASH

    def _persist(self, entry: AuditEntry) -> None:
        """Append entry to the log file."""
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), default=str) + "\n")

    def _load(self) -> None:
        """Load existing entries from the log file."""
        if not self._log_path.exists():
            return
        for line in self._log_path.read_text(encoding="utf-8").strip().split("\n"):
            if line:
                data = json.loads(line)
                self._entries.append(AuditEntry(**data))

    def export_for_audit(self, output_path: Path) -> None:
        """Export the full chain as a JSON file for auditors."""
        valid, message = self.verify_integrity()
        export = {
            "chain_length": len(self._entries),
            "integrity_verified": valid,
            "integrity_message": message,
            "first_entry": self._entries[0].timestamp if self._entries else None,
            "last_entry": self._entries[-1].timestamp if self._entries else None,
            "entries": [asdict(e) for e in self._entries],
        }
        output_path.write_text(
            json.dumps(export, indent=2, default=str),
            encoding="utf-8",
        )
