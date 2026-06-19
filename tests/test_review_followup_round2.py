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


def test_existing_plain_chain_still_verifies_after_key_enabled(isolated_storage, monkeypatch):
    # Migration: enabling a key must NOT make an existing plain chain report
    # TAMPERED. Legacy plain events are checked with their recorded algorithm.
    monkeypatch.delenv("FAULTRAY_SIGNING_KEY", raising=False)
    _register_two(isolated_storage)  # plain events
    monkeypatch.setenv("FAULTRAY_SIGNING_KEY", "key-enabled-late")
    assert ev.verify_chain() is True  # legacy plain entries still verify
    # New appends are keyed; the mixed plain→hmac chain still verifies.
    ev.register_evidence("C03-R01", "Doc C", str(isolated_storage))
    assert ev.verify_chain() is True


def test_forward_lock_rejects_plain_after_hmac(isolated_storage, monkeypatch):
    import uuid as _uuid

    monkeypatch.setenv("FAULTRAY_SIGNING_KEY", "key-forward-lock")
    _register_two(isolated_storage)  # hmac events
    assert ev.verify_chain() is True
    # Append a downgrade: a plain (sha256) event with an internally-consistent
    # hash, after the HMAC chain. Forward-lock must reject it.
    chain = json.loads(ev._AUDIT_FILE.read_text(encoding="utf-8"))
    prev = chain[-1]["hash"]
    eid = f"AUD-{_uuid.uuid4().hex[:12]}"
    ts = "2026-01-01T00:00:00+00:00"
    event_data = json.dumps(
        {"event_type": "evidence_added", "description": "downgrade",
         "timestamp": ts, "id": eid},
        sort_keys=True, ensure_ascii=False,
    )
    chain.append({
        "id": eid, "event_type": "evidence_added", "description": "downgrade",
        "timestamp": ts, "hash": ev._compute_event_hash(prev, event_data, None),
        "previous_hash": prev, "hash_alg": "sha256",
    })
    ev._AUDIT_FILE.write_text(json.dumps(chain), encoding="utf-8")
    assert ev.verify_chain() is False


def test_key_file_convention_enables_keyed_chain(isolated_storage, tmp_path, monkeypatch):
    # codex #4: honor FAULTRAY_SIGNING_KEY_FILE (shared with evidence_signing),
    # not only the inline env var.
    keyfile = tmp_path / "signing.key"
    keyfile.write_text("file-key-xyz", encoding="utf-8")
    monkeypatch.delenv("FAULTRAY_SIGNING_KEY", raising=False)
    monkeypatch.setenv("FAULTRAY_SIGNING_KEY_FILE", str(keyfile))
    _register_two(isolated_storage)
    chain = json.loads(ev._AUDIT_FILE.read_text(encoding="utf-8"))
    assert chain and all(e.get("hash_alg") == "hmac-sha256" for e in chain)
    assert ev.verify_chain() is True
    # Without the key file the keyed chain can't be verified.
    monkeypatch.delenv("FAULTRAY_SIGNING_KEY_FILE", raising=False)
    assert ev.verify_chain() is False


# --- availability_model: opt-in layer composition (U10) -------------------
def _lossy_graph(n: int, packet_loss: float):
    from faultray.model.components import Component, ComponentType
    from faultray.model.graph import InfraGraph

    g = InfraGraph()
    for i in range(n):
        c = Component(id=f"c{i}", name=f"c{i}", type=ComponentType.APP_SERVER)
        c.network.packet_loss_rate = packet_loss
        g.add_component(c)
    return g


def test_compose_layers_is_opt_in_and_lowers_runtime_floor(monkeypatch):
    from faultray.simulator.availability_model import compute_three_layer_model

    monkeypatch.delenv("FAULTRAY_COMPOSE_AVAILABILITY_LAYERS", raising=False)
    g = _lossy_graph(3, 0.02)

    default = compute_three_layer_model(g)
    composed = compute_three_layer_model(g, compose_layers=True)

    # Composing independent per-component packet loss (product) penalizes more
    # than averaging, so the runtime floor (layer 3) is strictly lower.
    assert composed.layer3_theoretical.availability < default.layer3_theoretical.availability


def test_compose_layers_env_opt_in(monkeypatch):
    from faultray.simulator.availability_model import compute_three_layer_model

    g = _lossy_graph(3, 0.02)
    monkeypatch.delenv("FAULTRAY_COMPOSE_AVAILABILITY_LAYERS", raising=False)
    default = compute_three_layer_model(g)
    monkeypatch.setenv("FAULTRAY_COMPOSE_AVAILABILITY_LAYERS", "1")
    env_on = compute_three_layer_model(g)
    # The env var alone enables the corrected composition.
    assert env_on.layer3_theoretical.availability < default.layer3_theoretical.availability
