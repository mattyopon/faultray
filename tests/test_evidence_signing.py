"""Tests for tamper-proof evidence signing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultray.reporter.evidence_signing import EvidenceSigner, SignedEvidence


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_REPORT = "FaultRay Simulation Report: All components healthy."
SAMPLE_TOPOLOGY = "components:\n  - id: web\n    type: web_server\n"
SAMPLE_RESULTS = {"availability": 99.95, "spof_count": 0, "components_analyzed": 5}


@pytest.fixture
def signer() -> EvidenceSigner:
    return EvidenceSigner(signing_key="test-secret-key")


@pytest.fixture
def evidence(signer: EvidenceSigner) -> SignedEvidence:
    return signer.sign_report(
        report_content=SAMPLE_REPORT,
        topology_yaml=SAMPLE_TOPOLOGY,
        simulation_results=SAMPLE_RESULTS,
        metadata={"env": "staging", "triggered_by": "ci"},
    )


# ---------------------------------------------------------------------------
# Sign & Verify
# ---------------------------------------------------------------------------

class TestEvidenceSignerSign:
    """Tests for signing simulation reports."""

    def test_sign_report_returns_signed_evidence(self, evidence: SignedEvidence) -> None:
        assert isinstance(evidence, SignedEvidence)

    def test_evidence_id_format(self, evidence: SignedEvidence) -> None:
        assert evidence.evidence_id.startswith("FR-")
        parts = evidence.evidence_id.split("-")
        assert len(parts) == 3
        # Timestamp part should be 14 digits (YYYYMMDDHHmmSS)
        assert len(parts[1]) == 14
        # Short hash part should be 8 hex chars
        assert len(parts[2]) == 8

    def test_timestamp_is_iso8601_utc(self, evidence: SignedEvidence) -> None:
        assert "T" in evidence.timestamp
        assert "+00:00" in evidence.timestamp or evidence.timestamp.endswith("Z")

    def test_faultray_version_populated(self, evidence: SignedEvidence) -> None:
        import faultray
        assert evidence.faultray_version == faultray.__version__

    def test_hashes_are_sha256_hex(self, evidence: SignedEvidence) -> None:
        for h in (evidence.topology_hash, evidence.simulation_hash, evidence.report_hash):
            assert len(h) == 64
            assert all(c in "0123456789abcdef" for c in h)

    def test_signature_is_sha256_hex(self, evidence: SignedEvidence) -> None:
        assert len(evidence.signature) == 64

    def test_metadata_preserved(self, evidence: SignedEvidence) -> None:
        assert evidence.metadata == {"env": "staging", "triggered_by": "ci"}

    def test_default_metadata_empty(self, signer: EvidenceSigner) -> None:
        ev = signer.sign_report(SAMPLE_REPORT, SAMPLE_TOPOLOGY, SAMPLE_RESULTS)
        assert ev.metadata == {}


class TestEvidenceSignerVerify:
    """Tests for verifying report integrity."""

    def test_verify_valid_report(self, signer: EvidenceSigner, evidence: SignedEvidence) -> None:
        assert signer.verify_report(evidence, SAMPLE_REPORT) is True

    def test_tampered_content_detected(self, signer: EvidenceSigner, evidence: SignedEvidence) -> None:
        assert signer.verify_report(evidence, "TAMPERED CONTENT") is False

    def test_tampered_signature_detected(self, signer: EvidenceSigner, evidence: SignedEvidence) -> None:
        evidence.signature = "a" * 64
        assert signer.verify_report(evidence, SAMPLE_REPORT) is False

    def test_tampered_report_hash_detected(self, signer: EvidenceSigner, evidence: SignedEvidence) -> None:
        evidence.report_hash = "b" * 64
        assert signer.verify_report(evidence, SAMPLE_REPORT) is False

    def test_wrong_key_fails_verification(self, evidence: SignedEvidence) -> None:
        other_signer = EvidenceSigner(signing_key="wrong-key")
        assert other_signer.verify_report(evidence, SAMPLE_REPORT) is False

    def test_default_key_works(self) -> None:
        signer = EvidenceSigner()  # default key
        ev = signer.sign_report(SAMPLE_REPORT, SAMPLE_TOPOLOGY, SAMPLE_RESULTS)
        assert signer.verify_report(ev, SAMPLE_REPORT) is True


# ---------------------------------------------------------------------------
# Export / Load
# ---------------------------------------------------------------------------

class TestEvidenceExportLoad:
    """Tests for exporting and loading signed evidence."""

    def test_export_creates_json_file(
        self, signer: EvidenceSigner, evidence: SignedEvidence, tmp_path: Path
    ) -> None:
        output = tmp_path / "evidence.json"
        signer.export_evidence(evidence, output)
        assert output.exists()
        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["evidence_id"] == evidence.evidence_id
        assert data["signature"] == evidence.signature

    def test_load_roundtrip(
        self, signer: EvidenceSigner, evidence: SignedEvidence, tmp_path: Path
    ) -> None:
        output = tmp_path / "evidence.json"
        signer.export_evidence(evidence, output)
        loaded = EvidenceSigner.load_evidence(output)
        assert loaded.evidence_id == evidence.evidence_id
        assert loaded.signature == evidence.signature
        assert loaded.metadata == evidence.metadata

    def test_loaded_evidence_verifies(
        self, signer: EvidenceSigner, evidence: SignedEvidence, tmp_path: Path
    ) -> None:
        output = tmp_path / "evidence.json"
        signer.export_evidence(evidence, output)
        loaded = EvidenceSigner.load_evidence(output)
        assert signer.verify_report(loaded, SAMPLE_REPORT) is True

    def test_loaded_evidence_detects_tampering(
        self, signer: EvidenceSigner, evidence: SignedEvidence, tmp_path: Path
    ) -> None:
        output = tmp_path / "evidence.json"
        signer.export_evidence(evidence, output)
        # Tamper with the file
        data = json.loads(output.read_text(encoding="utf-8"))
        data["report_hash"] = "c" * 64
        output.write_text(json.dumps(data), encoding="utf-8")
        loaded = EvidenceSigner.load_evidence(output)
        assert signer.verify_report(loaded, SAMPLE_REPORT) is False
