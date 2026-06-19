# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Regression tests for the second review follow-up round.

- governance evidence chain: when FAULTRAY_SIGNING_KEY is set the chain hashes
  are a keyed HMAC (a filesystem attacker can't recompute them without the key);
  without a key the plain hash chain is preserved (backward compatible).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import faultray.governance.evidence_manager as ev


@pytest.fixture
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    storage = tmp_path / "governance"
    monkeypatch.setattr(ev, "_STORAGE_DIR", storage)
    monkeypatch.setattr(ev, "_EVIDENCE_DIR", storage / "evidence")
    monkeypatch.setattr(ev, "_EVIDENCE_FILE", storage / "evidence_records.json")
    monkeypatch.setattr(ev, "_AUDIT_FILE", storage / "audit_chain.json")
    f = tmp_path / "doc.txt"
    f.write_text("evidence body", encoding="utf-8")
    return f


def _register_two(doc: Path) -> None:
    ev.register_evidence("C01-R01", "Doc A", str(doc))
    ev.register_evidence("C02-R01", "Doc B", str(doc))


def test_chain_is_keyed_when_signing_key_set(isolated_storage, monkeypatch):
    monkeypatch.setenv("FAULTRAY_SIGNING_KEY", "secret-key-1")
    _register_two(isolated_storage)
    # Consistent key → chain verifies.
    assert ev.verify_chain() is True
    # Remove the key: recomputation now uses the plain hash, which must NOT match
    # the stored HMAC — proving the chain hashes were keyed (not forgeable
    # without the key).
    monkeypatch.delenv("FAULTRAY_SIGNING_KEY", raising=False)
    assert ev.verify_chain() is False


def test_chain_tamper_detected_with_key(isolated_storage, monkeypatch):
    monkeypatch.setenv("FAULTRAY_SIGNING_KEY", "secret-key-2")
    _register_two(isolated_storage)
    assert ev.verify_chain() is True
    # Tamper with a stored audit-chain event's content; the keyed chain (verified
    # against _AUDIT_FILE) must reject it because the recomputed HMAC won't match.
    chain = json.loads(ev._AUDIT_FILE.read_text(encoding="utf-8"))
    chain[0]["description"] = "TAMPERED"
    ev._AUDIT_FILE.write_text(json.dumps(chain), encoding="utf-8")
    assert ev.verify_chain() is False


def test_chain_plain_without_key_still_verifies(isolated_storage, monkeypatch):
    monkeypatch.delenv("FAULTRAY_SIGNING_KEY", raising=False)
    _register_two(isolated_storage)
    # Backward compatible: no key → plain SHA-256 chain still verifies.
    assert ev.verify_chain() is True
