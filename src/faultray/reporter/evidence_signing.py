"""Tamper-proof evidence signing for compliance audit reports.

Provides cryptographic signatures on simulation results to ensure
report integrity for SOC 2, ISO 27001, FISC, and DORA compliance.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SignedEvidence:
    """A signed piece of evidence from a FaultRay simulation."""
    evidence_id: str
    timestamp: str  # ISO 8601 UTC
    faultray_version: str
    topology_hash: str  # SHA-256 of input topology
    simulation_hash: str  # SHA-256 of simulation results
    report_hash: str  # SHA-256 of the full report content
    signature: str  # HMAC-SHA256 of all above fields combined
    metadata: dict = field(default_factory=dict)


class EvidenceSigner:
    """Signs simulation reports for audit trail integrity."""

    def __init__(self, signing_key: str = "faultray-default-key") -> None:
        self._key = signing_key.encode()

    def sign_report(
        self,
        report_content: str,
        topology_yaml: str,
        simulation_results: dict,
        metadata: dict | None = None,
    ) -> SignedEvidence:
        """Create a signed evidence record for a simulation report."""
        import faultray

        now = datetime.now(timezone.utc)
        evidence_id = f"FR-{now.strftime('%Y%m%d%H%M%S')}-{hashlib.sha256(report_content.encode()).hexdigest()[:8]}"

        topology_hash = hashlib.sha256(topology_yaml.encode()).hexdigest()
        simulation_hash = hashlib.sha256(
            json.dumps(simulation_results, sort_keys=True, default=str).encode()
        ).hexdigest()
        report_hash = hashlib.sha256(report_content.encode()).hexdigest()

        # Create signature from all fields
        sign_payload = f"{evidence_id}|{now.isoformat()}|{faultray.__version__}|{topology_hash}|{simulation_hash}|{report_hash}"
        import hmac
        signature = hmac.new(self._key, sign_payload.encode(), hashlib.sha256).hexdigest()

        return SignedEvidence(
            evidence_id=evidence_id,
            timestamp=now.isoformat(),
            faultray_version=faultray.__version__,
            topology_hash=topology_hash,
            simulation_hash=simulation_hash,
            report_hash=report_hash,
            signature=signature,
            metadata=metadata or {},
        )

    def verify_report(self, evidence: SignedEvidence, report_content: str) -> bool:
        """Verify that a report has not been tampered with."""
        report_hash = hashlib.sha256(report_content.encode()).hexdigest()
        if report_hash != evidence.report_hash:
            return False

        sign_payload = (
            f"{evidence.evidence_id}|{evidence.timestamp}|{evidence.faultray_version}"
            f"|{evidence.topology_hash}|{evidence.simulation_hash}|{evidence.report_hash}"
        )
        import hmac
        expected = hmac.new(self._key, sign_payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(evidence.signature, expected)

    def export_evidence(self, evidence: SignedEvidence, output_path: Path) -> None:
        """Export signed evidence to a JSON file."""
        output_path.write_text(
            json.dumps(asdict(evidence), indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def load_evidence(path: Path) -> SignedEvidence:
        """Load signed evidence from a JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return SignedEvidence(**data)
