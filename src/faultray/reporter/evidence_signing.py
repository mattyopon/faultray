# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tamper-proof evidence signing for compliance audit reports.

Provides cryptographic signatures on simulation results to ensure
report integrity for SOC 2, ISO 27001, FISC, and DORA compliance.

Key management hierarchy (in order of precedence):
  1. Direct ``signing_key`` parameter passed to the constructor.
  2. Environment variable ``FAULTRAY_SIGNING_KEY``.
  3. File path in ``FAULTRAY_SIGNING_KEY_FILE`` environment variable.

A missing key does NOT fall back to a hardcoded default; instead a
``SigningKeyError`` is raised at signing time to prevent accidental use
of a weak or shared secret in production environments.

Key rotation is supported: sign with the current key, verify by trying
the current key first, then any configured old keys.

X.509 certificate-based signing is supported when the ``cryptography``
library is available.  When it is not installed the implementation falls
back transparently to HMAC-SHA256.

Blockchain-style chain hashing links every evidence record to the one
before it, enabling tamper detection across the entire audit trail.
Counter-signatures allow a second approver to attest that the primary
evidence record has been reviewed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

_SIGNING_KEY_ERROR_MSG = (
    "No signing key configured.  Provide one of:\n"
    "  • EvidenceSigner(signing_key='...')\n"
    "  • Environment variable FAULTRAY_SIGNING_KEY\n"
    "  • File path in FAULTRAY_SIGNING_KEY_FILE environment variable\n"
    "Using a default key is not permitted in a financial compliance context."
)

_LEGACY_DEFAULT_KEY = "faultray-default-key"


class SigningKeyError(RuntimeError):
    """Raised when no signing key is configured and signing is requested."""


# ---------------------------------------------------------------------------
# Key resolution helpers
# ---------------------------------------------------------------------------


def _load_key_from_env() -> bytes | None:
    """Try to load signing key bytes from environment variables."""
    # Direct value
    raw = os.environ.get("FAULTRAY_SIGNING_KEY")
    if raw:
        return raw.encode()

    # Path to a file containing the key
    key_file = os.environ.get("FAULTRAY_SIGNING_KEY_FILE")
    if key_file:
        key_path = Path(key_file)
        if key_path.is_file():
            return key_path.read_bytes().strip()
        logger.warning(
            "FAULTRAY_SIGNING_KEY_FILE points to a non-existent file: %s", key_file
        )

    return None


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class CounterSignature:
    """A second approver's attestation on an evidence record."""

    signer_id: str          # Identifier of the approving party (e.g. user e-mail, role)
    key_id: str             # Key ID used for the counter-signature
    timestamp: str          # ISO 8601 UTC
    signature: str          # HMAC-SHA256 of the primary evidence's signature + signer_id
    signing_algorithm: str = "HMAC-SHA256"


@dataclass
class SignedEvidence:
    """A signed piece of evidence from a FaultRay simulation.

    Extended from the original model to carry algorithm metadata,
    key-rotation identifiers, X.509 certificate thumbprints, and
    chain-linking hashes for tamper-evident sequencing.
    """

    # --- Original fields (preserved for backward compatibility) ---
    evidence_id: str
    timestamp: str              # ISO 8601 UTC
    faultray_version: str
    topology_hash: str          # SHA-256 of input topology
    simulation_hash: str        # SHA-256 of simulation results
    report_hash: str            # SHA-256 of the full report content
    signature: str              # HMAC-SHA256 (or RSA-SHA256) of all above fields
    metadata: dict = field(default_factory=dict)

    # --- New compliance fields ---
    signing_algorithm: str = "HMAC-SHA256"
    key_id: str = ""            # Identifies which key was used (for rotation tracking)
    certificate_thumbprint: str = ""   # SHA-256 of X.509 cert (if using cert-based signing)
    chain_hash: str = ""        # SHA-256 of the *previous* evidence record (blockchain link)
    counter_signatures: list[CounterSignature] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Chain verification report
# ---------------------------------------------------------------------------


@dataclass
class ChainVerificationReport:
    """Result of verifying an entire sequence of evidence records."""

    total_records: int
    valid_count: int
    invalid_records: list[dict]   # [{index, evidence_id, reason}]
    chain_intact: bool
    summary: str


# ---------------------------------------------------------------------------
# EvidenceSigner
# ---------------------------------------------------------------------------


class EvidenceSigner:
    """Signs simulation reports for audit trail integrity.

    Key management
    --------------
    Keys are resolved in this order:

    1. ``signing_key`` constructor parameter (explicit, highest priority).
    2. ``FAULTRAY_SIGNING_KEY`` environment variable.
    3. File at path given by ``FAULTRAY_SIGNING_KEY_FILE`` env var.

    If none of the above is configured, calling :meth:`sign_report` raises
    :exc:`SigningKeyError`.  Verification (:meth:`verify_report`) never
    requires a key: it uses the key already stored in the signer.

    Key rotation
    ------------
    Pass ``old_signing_keys`` to accept evidence that was signed with a
    previous key.  Verification tries the current key first, then each
    old key in order.

    X.509 certificate-based signing
    --------------------------------
    Pass ``certificate_path`` and ``private_key_path`` (PEM files) to
    enable RSA-SHA256 signatures.  Requires the ``cryptography`` package.
    Falls back to HMAC-SHA256 when the package is unavailable.

    Backward compatibility
    ----------------------
    The ``sign_report`` and ``verify_report`` method signatures are fully
    preserved.  Old callers that passed ``signing_key="faultray-default-key"``
    will receive a ``DeprecationWarning`` but the call will still succeed.
    """

    def __init__(
        self,
        signing_key: str | None = None,
        key_id: str = "",
        old_signing_keys: list[str] | None = None,
        certificate_path: Path | None = None,
        private_key_path: Path | None = None,
    ) -> None:
        """
        Args:
            signing_key: HMAC secret key as a plain string.  ``None`` means
                the constructor will attempt environment-variable resolution.
                Pass the sentinel value explicitly as the empty string ``""``
                to create a verify-only signer (no signing capability).
            key_id: Human-readable identifier for this key version
                (e.g. ``"2024-Q1"``).  Stored in every :class:`SignedEvidence`
                record to aid rotation tracking.
            old_signing_keys: List of previously-used keys accepted during
                verification (allows cross-key verification after rotation).
            certificate_path: Path to a PEM-encoded X.509 certificate.
                If provided together with ``private_key_path``, RSA-SHA256
                signing is used.
            private_key_path: Path to a PEM-encoded RSA private key.
        """
        # Detect legacy default-key usage and emit a deprecation warning
        if signing_key == _LEGACY_DEFAULT_KEY:
            warnings.warn(
                "EvidenceSigner: the default key 'faultray-default-key' is deprecated "
                "and must not be used in production compliance contexts.  "
                "Configure a real key via the signing_key parameter or the "
                "FAULTRAY_SIGNING_KEY environment variable.",
                DeprecationWarning,
                stacklevel=2,
            )

        # Resolve key: explicit parameter wins, then env, then None (deferred error)
        if signing_key is not None:
            self._key: bytes | None = signing_key.encode() if signing_key else None
        else:
            self._key = _load_key_from_env()

        self._key_id = key_id
        self._old_keys: list[bytes] = [k.encode() for k in (old_signing_keys or [])]

        # X.509 certificate-based signing setup
        self._cert_thumbprint = ""
        self._private_key: Any = None
        self._use_cert = False

        if certificate_path is not None and private_key_path is not None:
            self._setup_cert_signing(certificate_path, private_key_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sign_report(
        self,
        report_content: str,
        topology_yaml: str,
        simulation_results: dict,
        metadata: dict | None = None,
        previous_evidence: SignedEvidence | None = None,
    ) -> SignedEvidence:
        """Create a signed evidence record for a simulation report.

        Args:
            report_content: Full text of the rendered report.
            topology_yaml: YAML representation of the topology that was simulated.
            simulation_results: Raw simulation output (must be JSON-serialisable).
            metadata: Arbitrary key/value annotations (environment, CI run ID, etc.).
            previous_evidence: The immediately preceding evidence record.  When
                provided, its hash is included as ``chain_hash`` to create a
                blockchain-style link between records.

        Returns:
            A :class:`SignedEvidence` instance ready for storage or export.

        Raises:
            SigningKeyError: If no key has been configured.
        """
        self._require_key()

        import faultray

        now = datetime.now(timezone.utc)
        report_hash = hashlib.sha256(report_content.encode()).hexdigest()
        evidence_id = f"FR-{now.strftime('%Y%m%d%H%M%S')}-{report_hash[:8]}"

        topology_hash = hashlib.sha256(topology_yaml.encode()).hexdigest()
        simulation_hash = hashlib.sha256(
            json.dumps(simulation_results, sort_keys=True, default=str).encode()
        ).hexdigest()

        # Compute chain link to previous record
        chain_hash = ""
        if previous_evidence is not None:
            chain_hash = self._hash_evidence(previous_evidence)

        # Build the sign payload — order is stable and documented
        sign_payload = self._build_sign_payload(
            evidence_id=evidence_id,
            timestamp=now.isoformat(),
            version=faultray.__version__,
            topology_hash=topology_hash,
            simulation_hash=simulation_hash,
            report_hash=report_hash,
            chain_hash=chain_hash,
        )

        if self._use_cert:
            signature, algorithm = self._sign_with_cert(sign_payload)
        else:
            signature = hmac.new(
                self._key,  # type: ignore[arg-type]
                sign_payload.encode(),
                hashlib.sha256,
            ).hexdigest()
            algorithm = "HMAC-SHA256"

        return SignedEvidence(
            evidence_id=evidence_id,
            timestamp=now.isoformat(),
            faultray_version=faultray.__version__,
            topology_hash=topology_hash,
            simulation_hash=simulation_hash,
            report_hash=report_hash,
            signature=signature,
            metadata=metadata or {},
            signing_algorithm=algorithm,
            key_id=self._key_id,
            certificate_thumbprint=self._cert_thumbprint,
            chain_hash=chain_hash,
            counter_signatures=[],
        )

    def verify_report(
        self,
        evidence: SignedEvidence,
        report_content: str,
    ) -> bool:
        """Verify that a report has not been tampered with.

        Tries the current key first, then each ``old_signing_keys`` entry in
        order.  Returns ``True`` only if the report content matches the stored
        hash *and* the signature is valid under at least one configured key.

        Args:
            evidence: The :class:`SignedEvidence` record to verify.
            report_content: The report text that should match ``evidence.report_hash``.

        Returns:
            ``True`` if the evidence record is authentic and unmodified.
        """
        # Content integrity check first
        report_hash = hashlib.sha256(report_content.encode()).hexdigest()
        if report_hash != evidence.report_hash:
            return False

        sign_payload = self._build_sign_payload(
            evidence_id=evidence.evidence_id,
            timestamp=evidence.timestamp,
            version=evidence.faultray_version,
            topology_hash=evidence.topology_hash,
            simulation_hash=evidence.simulation_hash,
            report_hash=evidence.report_hash,
            chain_hash=evidence.chain_hash,
        )

        # Try current key
        if self._key is not None:
            if self._verify_hmac(self._key, sign_payload, evidence.signature):
                return True

        # Try old keys (rotation support)
        for old_key in self._old_keys:
            if self._verify_hmac(old_key, sign_payload, evidence.signature):
                return True

        # Certificate-based verification: fall through to HMAC keys only;
        # cert-based verification requires the caller to have cert context
        return False

    def add_counter_signature(
        self,
        evidence: SignedEvidence,
        signer_id: str,
        counter_key: str | None = None,
    ) -> SignedEvidence:
        """Add a counter-signature to an existing evidence record.

        Counter-signatures allow a second approver (e.g. a compliance officer)
        to attest that they have reviewed the primary evidence record.  Multiple
        counter-signers are supported; each appends to the list.

        Args:
            evidence: The evidence record to counter-sign.
            signer_id: Identity string for the counter-signer (e-mail, role, etc.).
            counter_key: HMAC key for the counter-signature.  Falls back to the
                signer's own key if not provided.

        Returns:
            The same ``evidence`` instance (mutated in place) with the new
            counter-signature appended.  Returning it enables chaining.

        Raises:
            SigningKeyError: If no key is available for counter-signing.
        """
        key = counter_key.encode() if counter_key else self._key
        if key is None:
            raise SigningKeyError(_SIGNING_KEY_ERROR_MSG)

        now = datetime.now(timezone.utc)
        counter_payload = f"{evidence.signature}|{signer_id}|{now.isoformat()}"
        counter_sig = hmac.new(key, counter_payload.encode(), hashlib.sha256).hexdigest()

        cs = CounterSignature(
            signer_id=signer_id,
            key_id=self._key_id,
            timestamp=now.isoformat(),
            signature=counter_sig,
            signing_algorithm="HMAC-SHA256",
        )
        evidence.counter_signatures.append(cs)
        return evidence

    def verify_chain(
        self,
        evidence_chain: list[SignedEvidence],
        report_contents: list[str] | None = None,
    ) -> ChainVerificationReport:
        """Verify the integrity of an entire sequence of evidence records.

        Checks that:
        - Each record's ``chain_hash`` matches the hash of the previous record.
        - Each record's signature is valid (if ``report_contents`` are supplied).

        Args:
            evidence_chain: Ordered list of :class:`SignedEvidence` records,
                oldest first.
            report_contents: Optional list of report text strings (same order and
                length as ``evidence_chain``).  When provided, full signature
                verification is performed on each record.

        Returns:
            A :class:`ChainVerificationReport` summarising the result.
        """
        invalid: list[dict] = []
        report_contents = report_contents or []

        for i, ev in enumerate(evidence_chain):
            reasons: list[str] = []

            # Chain link verification
            if i == 0:
                if ev.chain_hash not in ("", "0" * 64):
                    reasons.append(
                        f"First record has unexpected chain_hash: {ev.chain_hash!r}"
                    )
            else:
                expected_prev_hash = self._hash_evidence(evidence_chain[i - 1])
                if ev.chain_hash != expected_prev_hash:
                    reasons.append(
                        f"chain_hash mismatch: expected {expected_prev_hash[:16]}…, "
                        f"got {ev.chain_hash[:16] if ev.chain_hash else 'empty'}…"
                    )

            # Signature verification (only when report content is available)
            if i < len(report_contents):
                if not self.verify_report(ev, report_contents[i]):
                    reasons.append("Signature verification failed")

            if reasons:
                invalid.append({
                    "index": i,
                    "evidence_id": ev.evidence_id,
                    "reasons": reasons,
                })

        valid_count = len(evidence_chain) - len(invalid)
        chain_intact = len(invalid) == 0

        if chain_intact:
            summary = (
                f"Chain intact: {len(evidence_chain)} record(s) verified, "
                "no tampering detected."
            )
        else:
            summary = (
                f"Chain INVALID: {len(invalid)} of {len(evidence_chain)} record(s) "
                "failed verification."
            )

        return ChainVerificationReport(
            total_records=len(evidence_chain),
            valid_count=valid_count,
            invalid_records=invalid,
            chain_intact=chain_intact,
            summary=summary,
        )

    def export_evidence(self, evidence: SignedEvidence, output_path: Path) -> None:
        """Export signed evidence to a JSON file."""
        output_path.write_text(
            json.dumps(self._evidence_to_dict(evidence), indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def load_evidence(path: Path) -> SignedEvidence:
        """Load signed evidence from a JSON file exported by :meth:`export_evidence`."""
        data = json.loads(path.read_text(encoding="utf-8"))

        # Reconstruct nested counter_signatures list
        raw_cs = data.pop("counter_signatures", [])
        counter_sigs = [CounterSignature(**cs) for cs in raw_cs]

        ev = SignedEvidence(**data)
        ev.counter_signatures = counter_sigs
        return ev

    # ------------------------------------------------------------------
    # Certificate-based signing helpers
    # ------------------------------------------------------------------

    def _setup_cert_signing(
        self, certificate_path: Path, private_key_path: Path
    ) -> None:
        """Load X.509 certificate and private key for RSA-SHA256 signing."""
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from cryptography.x509 import load_pem_x509_certificate
            from cryptography.hazmat.backends import default_backend

            cert_pem = certificate_path.read_bytes()
            key_pem = private_key_path.read_bytes()

            cert = load_pem_x509_certificate(cert_pem, default_backend())
            self._private_key = load_pem_private_key(key_pem, password=None, backend=default_backend())

            # Compute certificate thumbprint (SHA-256 of DER-encoded cert)
            der_bytes = cert.public_bytes(
                __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.DER
            )
            self._cert_thumbprint = hashlib.sha256(der_bytes).hexdigest()
            self._use_cert = True

            logger.info("Certificate-based signing enabled (thumbprint: %s…)", self._cert_thumbprint[:16])

        except ImportError:
            logger.warning(
                "The 'cryptography' package is not installed; "
                "falling back to HMAC-SHA256 for signing."
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to load certificate/key pair (%s); "
                "falling back to HMAC-SHA256.",
                exc,
            )

    def _sign_with_cert(self, payload: str) -> tuple[str, str]:
        """Sign ``payload`` with the loaded RSA private key.  Returns (hex_sig, algo)."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        raw_sig = self._private_key.sign(
            payload.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return raw_sig.hex(), "RSA-SHA256"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_key(self) -> None:
        """Raise :exc:`SigningKeyError` if no key is configured."""
        if self._key is None and not self._use_cert:
            raise SigningKeyError(_SIGNING_KEY_ERROR_MSG)

    @staticmethod
    def _build_sign_payload(
        *,
        evidence_id: str,
        timestamp: str,
        version: str,
        topology_hash: str,
        simulation_hash: str,
        report_hash: str,
        chain_hash: str,
    ) -> str:
        """Build the canonical string that is fed to the signing algorithm.

        The format is stable and documented so that third-party tools can
        independently reproduce and verify signatures.

        Format:  ``<evidence_id>|<timestamp>|<version>|<topology_hash>|
                    <simulation_hash>|<report_hash>|<chain_hash>``
        """
        return (
            f"{evidence_id}|{timestamp}|{version}"
            f"|{topology_hash}|{simulation_hash}|{report_hash}"
            f"|{chain_hash}"
        )

    @staticmethod
    def _verify_hmac(key: bytes, payload: str, expected_hex: str) -> bool:
        """Constant-time HMAC comparison."""
        try:
            actual = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(actual, expected_hex)
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _hash_evidence(evidence: SignedEvidence) -> str:
        """Compute a canonical SHA-256 hash of a :class:`SignedEvidence` record.

        Only the immutable fields are included (not ``counter_signatures``).
        """
        stable = {
            "evidence_id": evidence.evidence_id,
            "timestamp": evidence.timestamp,
            "faultray_version": evidence.faultray_version,
            "topology_hash": evidence.topology_hash,
            "simulation_hash": evidence.simulation_hash,
            "report_hash": evidence.report_hash,
            "signature": evidence.signature,
            "signing_algorithm": evidence.signing_algorithm,
            "key_id": evidence.key_id,
            "certificate_thumbprint": evidence.certificate_thumbprint,
            "chain_hash": evidence.chain_hash,
        }
        payload = json.dumps(stable, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _evidence_to_dict(evidence: SignedEvidence) -> dict:
        """Serialise a :class:`SignedEvidence` to a plain dict, handling nested types."""
        d = asdict(evidence)
        return d
