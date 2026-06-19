# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Evidence management with SHA-256 hash chain audit trail.

Manages governance evidence files and maintains an append-only
hash chain ledger for tamper-proof audit tracking.

Ported from JPGovAI's evidence + audit_trail services, adapted to FaultRay:
- dataclasses instead of Pydantic
- File-based storage (~/.faultray/governance/evidence/)
- SHA-256 hash chain (no DB dependency)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from faultray.governance.frameworks import all_meti_requirements


# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

_STORAGE_DIR = Path.home() / ".faultray" / "governance"
_EVIDENCE_DIR = _STORAGE_DIR / "evidence"
_EVIDENCE_FILE = _STORAGE_DIR / "evidence_records.json"
_AUDIT_FILE = _STORAGE_DIR / "audit_chain.json"

GENESIS_HASH = hashlib.sha256(b"FAULTRAY-GOVERNANCE-GENESIS").hexdigest()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EvidenceRecord:
    """A single evidence record tied to a governance requirement."""

    id: str = ""
    requirement_id: str = ""  # e.g. "C01-R01"
    description: str = ""
    file_path: str = ""
    file_hash: str = ""  # SHA-256
    registered_at: str = ""
    registered_by: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"EVD-{uuid.uuid4().hex[:12]}"
        if not self.registered_at:
            self.registered_at = datetime.now(timezone.utc).isoformat()


@dataclass
class AuditEvent:
    """A single audit event in the hash chain."""

    id: str = ""
    event_type: str = ""  # evidence_added, assessment_run, policy_generated, etc.
    description: str = ""
    timestamp: str = ""
    hash: str = ""  # SHA-256 or keyed HMAC-SHA256 of (prev_hash + event_data)
    previous_hash: str = ""
    # Which algorithm produced ``hash``. Legacy chains (written before keyed
    # signing) have no field → treated as "sha256", so they keep verifying.
    hash_alg: str = "sha256"

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"AUD-{uuid.uuid4().hex[:12]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    p = Path(file_path)
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_signing_key() -> bytes | None:
    """Signing key from FAULTRAY_SIGNING_KEY or FAULTRAY_SIGNING_KEY_FILE.

    Shared with reporter.evidence_signing so the governance audit chain honors
    the same key-file convention (not only the inline env var).
    """
    try:
        from faultray.reporter.evidence_signing import _load_key_from_env

        return _load_key_from_env()
    except Exception:
        raw = os.environ.get("FAULTRAY_SIGNING_KEY")
        return raw.encode("utf-8") if raw else None


def _compute_event_hash(
    previous_hash: str, event_data: str, key: bytes | None
) -> str:
    """Compute the chain hash linking this event to the previous one.

    With a key, use keyed HMAC-SHA256 (tamper-PROOF — a filesystem attacker can't
    recompute it without the key). Without a key, plain SHA-256 (tamper-EVIDENT).
    The algorithm is recorded per event (AuditEvent.hash_alg) so an existing
    plain chain keeps verifying after a key is configured (each event is checked
    with the algorithm it was written with), and verify_chain forward-locks: once
    an HMAC event appears no later event may downgrade to plain. (A determined
    attacker who can rewrite the whole file from before the first HMAC event
    still needs out-of-band anchoring of chain heads for full assurance.)
    """
    payload = previous_hash + event_data
    if key:
        return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return _sha256(payload)


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _load_evidence() -> list[dict]:
    if not _EVIDENCE_FILE.exists():
        return []
    try:
        data = json.loads(_EVIDENCE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_evidence(records: list[dict]) -> None:
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    _EVIDENCE_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_audit_chain() -> list[dict]:
    if not _AUDIT_FILE.exists():
        return []
    try:
        data = json.loads(_AUDIT_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_audit_chain(events: list[dict]) -> None:
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    _AUDIT_FILE.write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Audit chain operations
# ---------------------------------------------------------------------------


def _append_audit_event(event_type: str, description: str) -> AuditEvent:
    """Append an audit event to the hash chain."""
    chain = _load_audit_chain()
    previous_hash = chain[-1]["hash"] if chain else GENESIS_HASH

    event = AuditEvent(
        event_type=event_type,
        description=description,
    )

    event_data = json.dumps(
        {"event_type": event.event_type, "description": event.description,
         "timestamp": event.timestamp, "id": event.id},
        sort_keys=True, ensure_ascii=False,
    )
    event.previous_hash = previous_hash
    key = _resolve_signing_key()
    event.hash_alg = "hmac-sha256" if key else "sha256"
    event.hash = _compute_event_hash(previous_hash, event_data, key)

    chain.append(asdict(event))
    _save_audit_chain(chain)
    return event


# ---------------------------------------------------------------------------
# Public API — Evidence
# ---------------------------------------------------------------------------


def register_evidence(
    req_id: str,
    description: str,
    file_path: str,
    registered_by: str = "",
) -> EvidenceRecord:
    """Register an evidence file for a governance requirement.

    Args:
        req_id: Requirement ID (e.g. "C01-R01").
        description: Human-readable description.
        file_path: Path to the evidence file.
        registered_by: Name/ID of the person registering.

    Returns:
        The created EvidenceRecord.
    """
    file_hash = _compute_file_hash(file_path)

    record = EvidenceRecord(
        requirement_id=req_id,
        description=description,
        file_path=file_path,
        file_hash=file_hash,
        registered_by=registered_by,
    )

    records = _load_evidence()
    records.append(asdict(record))
    _save_evidence(records)

    _append_audit_event(
        "evidence_added",
        f"Evidence {record.id} registered for {req_id}: {description}",
    )

    return record


def list_evidence(req_id: str | None = None) -> list[EvidenceRecord]:
    """List evidence records, optionally filtered by requirement ID.

    Args:
        req_id: If provided, filter to this requirement.

    Returns:
        List of EvidenceRecord.
    """
    records = _load_evidence()
    result = []
    for r in records:
        if req_id is not None and r.get("requirement_id") != req_id:
            continue
        result.append(EvidenceRecord(
            id=r.get("id", ""),
            requirement_id=r.get("requirement_id", ""),
            description=r.get("description", ""),
            file_path=r.get("file_path", ""),
            file_hash=r.get("file_hash", ""),
            registered_at=r.get("registered_at", ""),
            registered_by=r.get("registered_by", ""),
        ))
    return result


def get_coverage_summary() -> dict:
    """Get evidence coverage summary across all 28 METI requirements.

    Returns:
        Dict with total_requirements, covered, uncovered list, and coverage_rate.
    """
    all_reqs = all_meti_requirements()
    all_req_ids = {r.req_id for r in all_reqs}

    records = _load_evidence()
    covered_ids = {r["requirement_id"] for r in records if "requirement_id" in r}

    covered = all_req_ids & covered_ids
    uncovered = sorted(all_req_ids - covered_ids)

    total = len(all_req_ids)
    return {
        "total_requirements": total,
        "covered": len(covered),
        "uncovered_ids": uncovered,
        "coverage_rate": len(covered) / total if total > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Public API — Audit chain
# ---------------------------------------------------------------------------


def verify_chain() -> bool:
    """Verify the integrity of the audit hash chain.

    Returns:
        True if the chain is valid, False if tampered.
    """
    chain = _load_audit_chain()
    if not chain:
        return True

    # Check genesis link
    if chain[0].get("previous_hash") != GENESIS_HASH:
        return False

    key = _resolve_signing_key()
    seen_hmac = False

    for i, event in enumerate(chain):
        alg = event.get("hash_alg", "sha256")
        if alg == "hmac-sha256":
            # A keyed event can only be verified with the key.
            if key is None:
                return False
            seen_hmac = True
            event_key: bytes | None = key
        else:
            # Forward-lock: once the chain switched to HMAC, a later plain event
            # is a downgrade attempt, not a legitimate legacy entry.
            if seen_hmac:
                return False
            event_key = None

        # Recompute the hash with the algorithm this event was written with.
        event_data = json.dumps(
            {"event_type": event["event_type"], "description": event["description"],
             "timestamp": event["timestamp"], "id": event["id"]},
            sort_keys=True, ensure_ascii=False,
        )
        expected_hash = _compute_event_hash(event["previous_hash"], event_data, event_key)
        if event["hash"] != expected_hash:
            return False

        # Check chain link (except first)
        if i > 0 and event["previous_hash"] != chain[i - 1]["hash"]:
            return False

    return True


def get_audit_events() -> list[AuditEvent]:
    """Get all audit events from the chain.

    Returns:
        List of AuditEvent.
    """
    chain = _load_audit_chain()
    return [
        AuditEvent(
            id=e.get("id", ""),
            event_type=e.get("event_type", ""),
            description=e.get("description", ""),
            timestamp=e.get("timestamp", ""),
            hash=e.get("hash", ""),
            previous_hash=e.get("previous_hash", ""),
            hash_alg=e.get("hash_alg", "sha256"),
        )
        for e in chain
    ]


def record_audit_event(event_type: str, description: str) -> AuditEvent:
    """Public API to record a custom audit event.

    Args:
        event_type: Event type string.
        description: Human-readable description.

    Returns:
        The created AuditEvent.
    """
    return _append_audit_event(event_type, description)


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------


def reset_evidence_store() -> None:
    """Reset all evidence and audit data (for testing)."""
    if _EVIDENCE_FILE.exists():
        _EVIDENCE_FILE.unlink()
    if _AUDIT_FILE.exists():
        _AUDIT_FILE.unlink()
