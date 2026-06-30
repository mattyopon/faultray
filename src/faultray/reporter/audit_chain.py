# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Append-only audit chain for simulation evidence.

Implements a hash-chain audit log where each entry links to the previous
entry. Tamper-evidence is only genuine when a signing key is configured:
each link is then an HMAC-SHA256 keyed with ``FAULTRAY_SIGNING_KEY`` (or a
key passed to the constructor), so the chain cannot be silently rewritten
without the secret. Without a key the chain is merely *structurally*
consistent (plain SHA-256), which is detectable by anyone and therefore
NOT cryptographically tamper-evident — callers in regulated contexts should
construct the chain with ``require_signing=True`` to fail closed when no
key is present, mirroring the keyed-MAC pattern in ``dora_audit_report`` and
``licensing``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path

_ENV_SIGNING_KEY = "FAULTRAY_SIGNING_KEY"  # noqa: S105 - env var name, not a secret


@dataclass
class AuditEntry:
    """A single entry in the audit chain."""
    sequence: int
    timestamp: str  # ISO 8601 UTC
    action: str  # e.g., "simulation_run", "report_generated", "topology_loaded"
    actor: str  # e.g., "user@email.com", "api_key:xxx", "system"
    details: str  # Human-readable description
    data_hash: str  # MAC of the action's data
    previous_hash: str  # MAC of the previous entry (chain link)
    entry_hash: str  # MAC of this entry (including previous_hash)
    signed: bool = field(default=False)  # True when computed with a keyed HMAC


class AuditChain:
    """Append-only hash-chain audit log.

    When a signing key is configured the links are keyed HMAC-SHA256 and the
    chain is genuinely tamper-evident. Without a key the links fall back to
    plain SHA-256 and the chain is only structurally consistent; in that mode
    ``verify_integrity`` and ``export_for_audit`` explicitly report that the
    log is NOT cryptographically signed rather than overstating its guarantees.
    """

    GENESIS_HASH = "0" * 64  # Genesis block hash

    def __init__(
        self,
        log_path: Path | None = None,
        signing_key: str | None = None,
        *,
        require_signing: bool = False,
    ) -> None:
        self._entries: list[AuditEntry] = []
        self._log_path = log_path or Path.home() / ".faultray" / "audit_chain.jsonl"
        # Resolve the key from the environment when not supplied explicitly.
        self._signing_key = (
            signing_key if signing_key is not None else os.environ.get(_ENV_SIGNING_KEY)
        ) or None
        self._require_signing = require_signing
        if require_signing and not self._signing_key:
            raise RuntimeError(
                "Audit chain signing is required but no key is configured. "
                f"Set {_ENV_SIGNING_KEY} or pass signing_key= to the AuditChain."
            )
        self._load()
        # Whether new entries may be appended. The loaded prefix must be
        # consistent with how the NEXT entry will be written, or that append
        # would yield a chain no key can verify. Computed once at load (O(n))
        # rather than re-verifying on every append. Three refusal cases:
        #   1. signing active, prefix does not verify with the CURRENT key
        #      (unsigned legacy prefix, OR one signed under a rotated/old key);
        #   2. NO key configured, but the prefix already contains HMAC-signed
        #      entries — appending a new UNSIGNED entry would be rejected the
        #      moment the correct key is restored (an unsigned suffix in a signed
        #      chain), permanently breaking the log after one keyless event.
        self._appendable = True
        if self._entries:
            if self._signing_key or self._require_signing:
                self._appendable = self.verify_integrity()[0]
            elif any(e.signed for e in self._entries):
                # Signed entries present but no key to continue them: fail closed.
                self._appendable = False

    @property
    def tamper_evident(self) -> bool:
        """True only when a signing key is configured (keyed HMAC links)."""
        return bool(self._signing_key)

    def _mac(self, payload: str) -> tuple[str, bool]:
        """Return ``(hexdigest, signed)`` for *payload*.

        Uses keyed HMAC-SHA256 when a signing key is configured (the
        tamper-evident path); otherwise falls back to plain SHA-256 and
        reports ``signed=False`` so callers never mistake the unkeyed digest
        for a tamper-proof signature.
        """
        if self._signing_key:
            return (
                hmac.new(
                    self._signing_key.encode(), payload.encode(), hashlib.sha256
                ).hexdigest(),
                True,
            )
        return hashlib.sha256(payload.encode()).hexdigest(), False

    @staticmethod
    def _canonical_payload(
        sequence: int,
        timestamp: str,
        action: str,
        actor: str,
        data_hash: str,
        previous_hash: str,
        details: str,
    ) -> str:
        """Unambiguous serialization of an entry's fields for MAC-ing.

        Encoding the fields as a JSON array — rather than joining them with a
        ``|`` delimiter — means a ``|`` (or any byte) inside a field cannot shift
        a field boundary. ``action="deploy"`` / ``actor="alice|admin"`` and
        ``action="deploy|alice"`` / ``actor="admin"`` produce DIFFERENT bytes
        here, where the old pipe-joined form collided and let a signed entry's
        fields be re-partitioned without breaking ``verify_integrity``.
        json.dumps escapes embedded quotes/backslashes, so no value can forge the
        structure.
        """
        return json.dumps(
            [sequence, timestamp, action, actor, data_hash, previous_hash, details],
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def append(
        self,
        action: str,
        actor: str,
        details: str,
        data: str = "",
    ) -> AuditEntry:
        """Append a new entry to the audit chain."""
        # Fail closed when the loaded prefix is inconsistent with how the next
        # entry will be written (computed once in __init__): appending would
        # yield a chain that NO key can verify. This covers a current-key entry
        # onto an unsigned (legacy) prefix or a prefix signed under a different/
        # rotated key, AND a new UNSIGNED entry (no key configured) onto a prefix
        # that already has HMAC-signed entries. Require an explicit migration
        # (start a fresh signed chain, or load with the correct key). Brand-new
        # and already-all-signed chains are unaffected.
        if not self._appendable:
            raise RuntimeError(
                "Refusing to append to an audit chain whose existing entries are "
                "inconsistent with the current signing configuration: the loaded "
                "prefix has unsigned (legacy) entries, was signed under a "
                "different / rotated key, OR is HMAC-signed while no key is "
                "configured to continue it, so a new entry would make the whole "
                f"chain unverifiable. Set the correct {_ENV_SIGNING_KEY}, start a "
                "new signed chain, or load without a key only for an all-unsigned "
                "log."
            )
        sequence = len(self._entries)
        previous_hash = self._entries[-1].entry_hash if self._entries else self.GENESIS_HASH
        timestamp = datetime.now(timezone.utc).isoformat()
        data_hash, _ = self._mac(data)

        # Create the chain link (entry hash) from all fields including the
        # previous hash AND the human-readable details (otherwise details could
        # be altered on a signed entry without detection). Keyed with HMAC when
        # a signing key is configured so the chain cannot be rewritten.
        entry_payload = self._canonical_payload(
            sequence, timestamp, action, actor, data_hash, previous_hash, details
        )
        entry_hash, signed = self._mac(entry_payload)

        entry = AuditEntry(
            sequence=sequence,
            timestamp=timestamp,
            action=action,
            actor=actor,
            details=details,
            data_hash=data_hash,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
            signed=signed,
        )

        self._entries.append(entry)
        self._persist(entry)
        return entry

    def verify_integrity(self) -> tuple[bool, str]:
        """Verify the entire chain has not been tampered with."""
        if not self._entries:
            return True, "Empty chain"

        all_signed = True
        for i, entry in enumerate(self._entries):
            # Check sequence
            if entry.sequence != i:
                return False, f"Sequence mismatch at entry {i}: expected {i}, got {entry.sequence}"

            # Check previous hash linkage
            expected_prev = self._entries[i - 1].entry_hash if i > 0 else self.GENESIS_HASH
            if entry.previous_hash != expected_prev:
                return False, f"Chain broken at entry {i}: previous_hash mismatch"

            # A signed entry can only be verified with the key that produced
            # it: fail closed if it is signed but no key is configured.
            if entry.signed and not self._signing_key:
                return False, (
                    f"Entry {i} is HMAC-signed but no signing key is configured "
                    f"to verify it (set {_ENV_SIGNING_KEY})"
                )
            # In a signed deployment (key configured) every entry MUST be signed,
            # otherwise an attacker who can write the JSONL could append an
            # unsigned entry after a valid signed chain and recompute its plain
            # SHA-256 link. Reject unsigned entries whenever a key is configured.
            if (self._signing_key or self._require_signing) and not entry.signed:
                return False, (
                    f"Entry {i} is unsigned in a signed chain "
                    f"(a configured key requires every entry to be HMAC-signed)"
                )
            all_signed = all_signed and entry.signed

            canonical_payload = self._canonical_payload(
                entry.sequence, entry.timestamp, entry.action, entry.actor,
                entry.data_hash, entry.previous_hash, entry.details,
            )
            # Pre-canonicalization payload (fields joined with "|"). Retained as an
            # accepted form so a chain written by the previous release verifies
            # unchanged after an upgrade. This does NOT re-open the delimiter
            # ambiguity for entries written by THIS version: a new entry is MACed
            # over the JSON form, so its entry_hash is JSON-based, and a
            # pipe-joined string can never equal a JSON-array string — the pipe
            # form can only ever match an entry that was genuinely pipe-MACed
            # (i.e. a pre-upgrade one), whose ambiguity is an immutable property
            # of the already-written bytes and cannot be retrofixed regardless.
            pipe_payload = (
                f"{entry.sequence}|{entry.timestamp}|{entry.action}"
                f"|{entry.actor}|{entry.data_hash}|{entry.previous_hash}"
                f"|{entry.details}"
            )
            if entry.signed:
                key = self._signing_key.encode()
                if not any(
                    hmac.compare_digest(
                        entry.entry_hash,
                        hmac.new(key, p.encode(), hashlib.sha256).hexdigest(),
                    )
                    for p in (canonical_payload, pipe_payload)
                ):
                    return False, f"Entry hash tampered at entry {i}"
            else:
                # Unsigned (only reachable with no key configured). Accept the new
                # canonical JSON payload OR the two pre-upgrade pipe-joined payloads
                # (with and without details), so existing unsigned logs still
                # verify. Unsigned entries carry no cryptographic guarantee, so the
                # old delimiter ambiguity is irrelevant on this path.
                legacy_payload = (
                    f"{entry.sequence}|{entry.timestamp}|{entry.action}"
                    f"|{entry.actor}|{entry.data_hash}|{entry.previous_hash}"
                )
                if not any(
                    hmac.compare_digest(
                        entry.entry_hash, hashlib.sha256(p.encode()).hexdigest()
                    )
                    for p in (canonical_payload, pipe_payload, legacy_payload)
                ):
                    return False, f"Entry hash tampered at entry {i}"

        n = len(self._entries)
        if all_signed and self._signing_key:
            return True, f"Chain valid (HMAC-verified): {n} entries"
        return True, (
            f"Chain structurally valid: {n} entries "
            f"(WARNING: not cryptographically signed; set {_ENV_SIGNING_KEY} "
            "for tamper-evidence)"
        )

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
        # Tamper-evidence is only TRUE when a key is configured AND every loaded
        # entry was actually HMAC-signed. A key present over legacy unsigned
        # entries must not be advertised as tamper-evident.
        evident = (
            self.tamper_evident
            and bool(self._entries)
            and all(e.signed for e in self._entries)
        )
        export = {
            "chain_length": len(self._entries),
            "integrity_verified": valid,
            "integrity_message": message,
            "tamper_evident": evident,
            "signature_algorithm": "hmac-sha256" if evident else "sha256-unkeyed",
            "first_entry": self._entries[0].timestamp if self._entries else None,
            "last_entry": self._entries[-1].timestamp if self._entries else None,
            "entries": [asdict(e) for e in self._entries],
        }
        output_path.write_text(
            json.dumps(export, indent=2, default=str),
            encoding="utf-8",
        )
