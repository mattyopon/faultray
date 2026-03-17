"""Tests for append-only audit chain."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultray.reporter.audit_chain import AuditChain, AuditEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def chain(tmp_path: Path) -> AuditChain:
    return AuditChain(log_path=tmp_path / "audit.jsonl")


@pytest.fixture
def populated_chain(chain: AuditChain) -> AuditChain:
    chain.append("topology_loaded", "user@test.com", "Loaded topology v1", data="topology_yaml")
    chain.append("simulation_run", "system", "Ran simulation #42", data='{"result": "ok"}')
    chain.append("report_generated", "api_key:abc", "Generated PDF report")
    return chain


# ---------------------------------------------------------------------------
# Append
# ---------------------------------------------------------------------------

class TestAuditChainAppend:
    """Tests for appending entries to the chain."""

    def test_append_returns_audit_entry(self, chain: AuditChain) -> None:
        entry = chain.append("test_action", "actor", "details")
        assert isinstance(entry, AuditEntry)

    def test_first_entry_sequence_zero(self, chain: AuditChain) -> None:
        entry = chain.append("action", "actor", "first entry")
        assert entry.sequence == 0

    def test_sequence_increments(self, populated_chain: AuditChain) -> None:
        entries = populated_chain.get_entries()
        for i, entry in enumerate(entries):
            assert entry.sequence == i

    def test_first_entry_uses_genesis_hash(self, chain: AuditChain) -> None:
        entry = chain.append("action", "actor", "first")
        assert entry.previous_hash == AuditChain.GENESIS_HASH

    def test_subsequent_entries_chain_hashes(self, populated_chain: AuditChain) -> None:
        entries = populated_chain.get_entries()
        assert entries[1].previous_hash == entries[0].entry_hash
        assert entries[2].previous_hash == entries[1].entry_hash

    def test_entry_hash_is_sha256(self, chain: AuditChain) -> None:
        entry = chain.append("action", "actor", "details")
        assert len(entry.entry_hash) == 64
        assert all(c in "0123456789abcdef" for c in entry.entry_hash)

    def test_data_hash_computed(self, chain: AuditChain) -> None:
        entry = chain.append("action", "actor", "details", data="some data")
        assert len(entry.data_hash) == 64
        # Different data should produce different hash
        entry2 = chain.append("action", "actor", "details", data="other data")
        assert entry.data_hash != entry2.data_hash

    def test_empty_data_hash(self, chain: AuditChain) -> None:
        entry = chain.append("action", "actor", "details", data="")
        assert len(entry.data_hash) == 64

    def test_length_property(self, populated_chain: AuditChain) -> None:
        assert populated_chain.length == 3

    def test_last_hash_property(self, populated_chain: AuditChain) -> None:
        entries = populated_chain.get_entries()
        assert populated_chain.last_hash == entries[-1].entry_hash

    def test_last_hash_empty_chain(self, chain: AuditChain) -> None:
        assert chain.last_hash == AuditChain.GENESIS_HASH


# ---------------------------------------------------------------------------
# Integrity Verification
# ---------------------------------------------------------------------------

class TestAuditChainIntegrity:
    """Tests for chain integrity verification."""

    def test_empty_chain_valid(self, chain: AuditChain) -> None:
        valid, msg = chain.verify_integrity()
        assert valid is True
        assert "Empty chain" in msg

    def test_valid_chain_passes(self, populated_chain: AuditChain) -> None:
        valid, msg = populated_chain.verify_integrity()
        assert valid is True
        assert "3 entries" in msg

    def test_tampered_entry_hash_detected(self, populated_chain: AuditChain) -> None:
        # Tamper with entry hash
        populated_chain._entries[1].entry_hash = "f" * 64
        valid, msg = populated_chain.verify_integrity()
        assert valid is False
        assert "previous_hash mismatch" in msg or "hash tampered" in msg

    def test_tampered_previous_hash_detected(self, populated_chain: AuditChain) -> None:
        populated_chain._entries[1].previous_hash = "e" * 64
        valid, msg = populated_chain.verify_integrity()
        assert valid is False
        assert "mismatch" in msg

    def test_tampered_sequence_detected(self, populated_chain: AuditChain) -> None:
        populated_chain._entries[1].sequence = 99
        valid, msg = populated_chain.verify_integrity()
        assert valid is False
        assert "Sequence mismatch" in msg

    def test_single_entry_valid(self, chain: AuditChain) -> None:
        chain.append("action", "actor", "single entry")
        valid, msg = chain.verify_integrity()
        assert valid is True


# ---------------------------------------------------------------------------
# Filtering and Retrieval
# ---------------------------------------------------------------------------

class TestAuditChainFiltering:
    """Tests for entry retrieval and filtering."""

    def test_get_all_entries(self, populated_chain: AuditChain) -> None:
        entries = populated_chain.get_entries()
        assert len(entries) == 3

    def test_filter_by_action(self, populated_chain: AuditChain) -> None:
        entries = populated_chain.get_entries(action="simulation_run")
        assert len(entries) == 1
        assert entries[0].action == "simulation_run"

    def test_filter_no_match(self, populated_chain: AuditChain) -> None:
        entries = populated_chain.get_entries(action="nonexistent")
        assert len(entries) == 0

    def test_limit_entries(self, populated_chain: AuditChain) -> None:
        entries = populated_chain.get_entries(limit=2)
        assert len(entries) == 2
        # Should return the last 2 entries
        assert entries[0].sequence == 1
        assert entries[1].sequence == 2


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestAuditChainPersistence:
    """Tests for loading and persisting the chain."""

    def test_persist_creates_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.jsonl"
        chain = AuditChain(log_path=log_path)
        chain.append("action", "actor", "details")
        assert log_path.exists()

    def test_load_from_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.jsonl"
        chain1 = AuditChain(log_path=log_path)
        chain1.append("action1", "actor1", "first")
        chain1.append("action2", "actor2", "second")

        chain2 = AuditChain(log_path=log_path)
        assert chain2.length == 2
        entries = chain2.get_entries()
        assert entries[0].action == "action1"
        assert entries[1].action == "action2"

    def test_loaded_chain_verifies(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.jsonl"
        chain1 = AuditChain(log_path=log_path)
        chain1.append("a", "b", "c")
        chain1.append("d", "e", "f")

        chain2 = AuditChain(log_path=log_path)
        valid, msg = chain2.verify_integrity()
        assert valid is True

    def test_append_after_reload(self, tmp_path: Path) -> None:
        log_path = tmp_path / "audit.jsonl"
        chain1 = AuditChain(log_path=log_path)
        chain1.append("first", "actor", "initial")

        chain2 = AuditChain(log_path=log_path)
        chain2.append("second", "actor", "continued")
        assert chain2.length == 2

        # Verify the chain is still valid after reload+append
        valid, msg = chain2.verify_integrity()
        assert valid is True

    def test_nonexistent_file_starts_empty(self, tmp_path: Path) -> None:
        chain = AuditChain(log_path=tmp_path / "nonexistent.jsonl")
        assert chain.length == 0

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        log_path = tmp_path / "deep" / "nested" / "audit.jsonl"
        chain = AuditChain(log_path=log_path)
        chain.append("action", "actor", "details")
        assert log_path.exists()


# ---------------------------------------------------------------------------
# Export for Audit
# ---------------------------------------------------------------------------

class TestAuditChainExport:
    """Tests for exporting the chain for auditors."""

    def test_export_creates_json(self, populated_chain: AuditChain, tmp_path: Path) -> None:
        output = tmp_path / "export.json"
        populated_chain.export_for_audit(output)
        assert output.exists()
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["chain_length"] == 3
        assert data["integrity_verified"] is True
        assert len(data["entries"]) == 3

    def test_export_includes_timestamps(self, populated_chain: AuditChain, tmp_path: Path) -> None:
        output = tmp_path / "export.json"
        populated_chain.export_for_audit(output)
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["first_entry"] is not None
        assert data["last_entry"] is not None

    def test_export_empty_chain(self, chain: AuditChain, tmp_path: Path) -> None:
        output = tmp_path / "export.json"
        chain.export_for_audit(output)
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["chain_length"] == 0
        assert data["integrity_verified"] is True
        assert data["first_entry"] is None
        assert data["last_entry"] is None
