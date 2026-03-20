# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Certificate Expiry Analyzer.

Analyzes TLS/SSL certificate configurations and expiry risks across
infrastructure components.  Provides certificate expiry timeline and risk
scoring, certificate chain validation (root -> intermediate -> leaf),
auto-renewal capability assessment, certificate pinning risk analysis,
wildcard vs SAN certificate coverage gaps, mTLS certificate rotation impact,
certificate authority (CA) dependency risk, OCSP/CRL availability assessment,
certificate transparency monitoring gaps, cross-datacenter certificate
consistency, certificate rotation downtime estimation, and expiry cascade
analysis (shared CA/intermediate expiry).

Designed for commercial chaos engineering: helps teams proactively identify
TLS/SSL certificate weaknesses before they cause outages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CertificateType(str, Enum):
    """Type of TLS/SSL certificate."""

    SINGLE_DOMAIN = "single_domain"
    WILDCARD = "wildcard"
    SAN = "san"
    SELF_SIGNED = "self_signed"
    MTLS_CLIENT = "mtls_client"
    MTLS_SERVER = "mtls_server"
    CODE_SIGNING = "code_signing"
    EV = "extended_validation"


class ChainRole(str, Enum):
    """Role of a certificate within the chain."""

    ROOT = "root"
    INTERMEDIATE = "intermediate"
    LEAF = "leaf"


class RenewalMethod(str, Enum):
    """How the certificate is renewed."""

    MANUAL = "manual"
    ACME = "acme"
    CLOUD_MANAGED = "cloud_managed"
    INTERNAL_CA = "internal_ca"
    VENDOR_API = "vendor_api"


class RiskSeverity(str, Enum):
    """Risk severity classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PinningStrategy(str, Enum):
    """Certificate pinning strategy."""

    NONE = "none"
    PUBLIC_KEY = "public_key"
    CERTIFICATE = "certificate"
    CA = "ca"


class OCSPMode(str, Enum):
    """OCSP stapling / checking mode."""

    DISABLED = "disabled"
    STAPLING = "stapling"
    RESPONDER = "responder"
    MUST_STAPLE = "must_staple"


class CRLMode(str, Enum):
    """CRL distribution mode."""

    DISABLED = "disabled"
    PERIODIC = "periodic"
    REAL_TIME = "real_time"


class TransparencyStatus(str, Enum):
    """Certificate Transparency (CT) log status."""

    NOT_LOGGED = "not_logged"
    LOGGED = "logged"
    MONITORED = "monitored"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CertificateEntry:
    """A single TLS/SSL certificate to be analyzed."""

    id: str
    name: str
    cert_type: CertificateType
    component_ids: list[str] = field(default_factory=list)
    issued_iso: str = ""
    expiry_iso: str = ""
    chain_role: ChainRole = ChainRole.LEAF
    issuer_ca: str = ""
    subject: str = ""
    san_domains: list[str] = field(default_factory=list)
    renewal_method: RenewalMethod = RenewalMethod.MANUAL
    auto_renew: bool = False
    renewal_days_before_expiry: int = 30
    pinning_strategy: PinningStrategy = PinningStrategy.NONE
    pinned_hash: str = ""
    ocsp_mode: OCSPMode = OCSPMode.DISABLED
    crl_mode: CRLMode = CRLMode.DISABLED
    ct_status: TransparencyStatus = TransparencyStatus.NOT_LOGGED
    datacenter: str = ""
    chain_certificates: list[str] = field(default_factory=list)
    key_size_bits: int = 2048
    signature_algorithm: str = "sha256"
    is_mtls: bool = False
    rotation_downtime_seconds: float = 0.0

    def issued_dt(self) -> datetime | None:
        return _parse_iso(self.issued_iso)

    def expiry_dt(self) -> datetime | None:
        return _parse_iso(self.expiry_iso)


@dataclass
class ExpiryTimelineEntry:
    """Timeline entry for a certificate approaching or past expiry."""

    cert_id: str
    name: str
    days_until_expiry: int | None = None
    expired: bool = False
    risk_score: float = 0.0
    severity: RiskSeverity = RiskSeverity.LOW
    expiry_iso: str = ""
    message: str = ""


@dataclass
class ExpiryTimeline:
    """Aggregated expiry timeline for all certificates."""

    entries: list[ExpiryTimelineEntry] = field(default_factory=list)
    nearest_expiry_days: int | None = None
    expired_count: int = 0
    critical_count: int = 0
    overall_risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ChainLink:
    """A single link in the certificate chain."""

    cert_id: str
    role: ChainRole
    issuer_ca: str = ""
    days_until_expiry: int | None = None
    valid: bool = True
    message: str = ""


@dataclass
class ChainValidationResult:
    """Result of certificate chain validation."""

    cert_id: str
    chain_length: int = 0
    links: list[ChainLink] = field(default_factory=list)
    complete: bool = True
    valid: bool = True
    severity: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RenewalAssessment:
    """Auto-renewal capability assessment for a certificate."""

    cert_id: str
    renewal_method: RenewalMethod = RenewalMethod.MANUAL
    auto_renew: bool = False
    renewal_days_before: int = 30
    renewal_reliable: bool = False
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PinningRiskResult:
    """Certificate pinning risk analysis result."""

    cert_id: str
    pinning_strategy: PinningStrategy = PinningStrategy.NONE
    rotation_blocked: bool = False
    risk: RiskSeverity = RiskSeverity.LOW
    affected_clients: int = 0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CoverageGap:
    """A single coverage gap in wildcard/SAN domains."""

    domain: str
    covered: bool = False
    cert_id: str = ""
    gap_type: str = ""


@dataclass
class CoverageAnalysis:
    """Wildcard vs SAN certificate coverage analysis."""

    total_domains: int = 0
    covered_domains: int = 0
    uncovered_domains: int = 0
    gaps: list[CoverageGap] = field(default_factory=list)
    coverage_percent: float = 0.0
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class MTLSRotationImpact:
    """mTLS certificate rotation impact analysis."""

    cert_id: str
    affected_services: list[str] = field(default_factory=list)
    mutual_dependencies: list[str] = field(default_factory=list)
    estimated_downtime_seconds: float = 0.0
    coordinated_rotation_needed: bool = False
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CADependencyRisk:
    """Certificate Authority dependency risk result."""

    ca_name: str
    cert_count: int = 0
    cert_ids: list[str] = field(default_factory=list)
    single_ca_dependency: bool = False
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class OCSPCRLAssessment:
    """OCSP/CRL availability assessment for a certificate."""

    cert_id: str
    ocsp_mode: OCSPMode = OCSPMode.DISABLED
    crl_mode: CRLMode = CRLMode.DISABLED
    revocation_checkable: bool = False
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class TransparencyAssessment:
    """Certificate Transparency monitoring gap assessment."""

    cert_id: str
    ct_status: TransparencyStatus = TransparencyStatus.NOT_LOGGED
    monitored: bool = False
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DatacenterConsistency:
    """Cross-datacenter certificate consistency result."""

    cert_name: str
    datacenters: list[str] = field(default_factory=list)
    consistent: bool = True
    mismatched_certs: list[str] = field(default_factory=list)
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RotationDowntimeEstimate:
    """Certificate rotation downtime estimation."""

    cert_id: str
    estimated_downtime_seconds: float = 0.0
    affected_component_count: int = 0
    zero_downtime_possible: bool = False
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CascadeEntry:
    """An entry in the expiry cascade analysis."""

    source_cert_id: str
    affected_cert_ids: list[str] = field(default_factory=list)
    affected_count: int = 0
    cascade_type: str = ""
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ExpiryCascadeAnalysis:
    """Full expiry cascade analysis (shared CA/intermediate)."""

    cascades: list[CascadeEntry] = field(default_factory=list)
    max_cascade_size: int = 0
    overall_risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FullCertificateReport:
    """Consolidated report from all certificate analyses."""

    expiry_timeline: ExpiryTimeline | None = None
    chain_validations: list[ChainValidationResult] = field(default_factory=list)
    renewal_assessments: list[RenewalAssessment] = field(default_factory=list)
    pinning_risks: list[PinningRiskResult] = field(default_factory=list)
    coverage_analysis: CoverageAnalysis | None = None
    mtls_impacts: list[MTLSRotationImpact] = field(default_factory=list)
    ca_risks: list[CADependencyRisk] = field(default_factory=list)
    ocsp_crl_assessments: list[OCSPCRLAssessment] = field(default_factory=list)
    transparency_assessments: list[TransparencyAssessment] = field(default_factory=list)
    datacenter_consistency: list[DatacenterConsistency] = field(default_factory=list)
    rotation_downtimes: list[RotationDowntimeEstimate] = field(default_factory=list)
    cascade_analysis: ExpiryCascadeAnalysis | None = None
    overall_risk: RiskSeverity = RiskSeverity.LOW
    total_certificates: int = 0
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Risk thresholds for days-until-expiry
_EXPIRY_CRITICAL_DAYS: int = 7
_EXPIRY_HIGH_DAYS: int = 30
_EXPIRY_MEDIUM_DAYS: int = 90

# Base rotation downtime per cert type (seconds)
_BASE_ROTATION_DOWNTIME: dict[CertificateType, float] = {
    CertificateType.SINGLE_DOMAIN: 5.0,
    CertificateType.WILDCARD: 8.0,
    CertificateType.SAN: 10.0,
    CertificateType.SELF_SIGNED: 3.0,
    CertificateType.MTLS_CLIENT: 15.0,
    CertificateType.MTLS_SERVER: 15.0,
    CertificateType.CODE_SIGNING: 2.0,
    CertificateType.EV: 12.0,
}

# Minimum acceptable key sizes
_MIN_KEY_SIZE: int = 2048
_RECOMMENDED_KEY_SIZE: int = 4096

# CA concentration threshold
_CA_CONCENTRATION_THRESHOLD: int = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(date_str: str) -> datetime | None:
    """Best-effort ISO-8601 date parsing (stdlib only)."""
    if not date_str:
        return None
    try:
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure *dt* is timezone-aware (UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _severity_from_score(score: float) -> RiskSeverity:
    """Map a 0-1 risk score to :class:`RiskSeverity`."""
    if score >= 0.8:
        return RiskSeverity.CRITICAL
    if score >= 0.6:
        return RiskSeverity.HIGH
    if score >= 0.3:
        return RiskSeverity.MEDIUM
    return RiskSeverity.LOW


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def _days_until(dt: datetime | None) -> int | None:
    """Return the number of days until *dt*, or *None* if unknown."""
    if dt is None:
        return None
    dt = _ensure_utc(dt)
    now = datetime.now(timezone.utc)
    delta = dt - now
    return delta.days  # can be negative if past


def _days_since(dt: datetime | None) -> int | None:
    """Return the number of days since *dt*, or *None* if unknown."""
    if dt is None:
        return None
    dt = _ensure_utc(dt)
    now = datetime.now(timezone.utc)
    delta = now - dt
    return max(0, delta.days)


def _max_severity(*severities: RiskSeverity) -> RiskSeverity:
    """Return the highest severity from the given values."""
    order = {
        RiskSeverity.LOW: 0,
        RiskSeverity.MEDIUM: 1,
        RiskSeverity.HIGH: 2,
        RiskSeverity.CRITICAL: 3,
    }
    if not severities:
        return RiskSeverity.LOW
    return max(severities, key=lambda s: order[s])


def _severity_for_expiry_days(days: int | None) -> RiskSeverity:
    """Determine severity based on days until expiry."""
    if days is None:
        return RiskSeverity.MEDIUM
    if days < 0:
        return RiskSeverity.CRITICAL
    if days <= _EXPIRY_CRITICAL_DAYS:
        return RiskSeverity.CRITICAL
    if days <= _EXPIRY_HIGH_DAYS:
        return RiskSeverity.HIGH
    if days <= _EXPIRY_MEDIUM_DAYS:
        return RiskSeverity.MEDIUM
    return RiskSeverity.LOW


def _risk_score_for_expiry_days(days: int | None) -> float:
    """Convert days-until-expiry to a 0-1 risk score."""
    if days is None:
        return 0.5
    if days < 0:
        return 1.0
    if days <= _EXPIRY_CRITICAL_DAYS:
        return 0.9
    if days <= _EXPIRY_HIGH_DAYS:
        return 0.7
    if days <= _EXPIRY_MEDIUM_DAYS:
        return 0.4
    return 0.1


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class CertificateExpiryAnalyzer:
    """Comprehensive TLS/SSL certificate lifecycle analysis engine.

    All methods are stateless and take an :class:`InfraGraph` plus one or more
    :class:`CertificateEntry` instances as input.
    """

    # -- 1. Expiry timeline and risk scoring ---------------------------------

    def build_expiry_timeline(
        self,
        certs: Sequence[CertificateEntry],
    ) -> ExpiryTimeline:
        """Build a timeline of certificates ordered by expiry urgency.

        Parameters
        ----------
        certs:
            Certificates to analyze.
        """
        if not certs:
            return ExpiryTimeline(
                recommendations=["No certificates to analyze"],
            )

        entries: list[ExpiryTimelineEntry] = []
        expired_count = 0
        critical_count = 0
        nearest: int | None = None

        for cert in certs:
            days = _days_until(cert.expiry_dt())
            expired = days is not None and days < 0
            severity = _severity_for_expiry_days(days)
            risk_score = _risk_score_for_expiry_days(days)

            if expired:
                expired_count += 1
                msg = f"Certificate '{cert.name}' has EXPIRED ({abs(days)} days ago)"
            elif days is not None:
                msg = f"Certificate '{cert.name}' expires in {days} days"
            else:
                msg = f"Certificate '{cert.name}' has no expiry date recorded"

            if severity in (RiskSeverity.CRITICAL,):
                critical_count += 1

            if days is not None:
                if nearest is None or days < nearest:
                    nearest = days

            entries.append(
                ExpiryTimelineEntry(
                    cert_id=cert.id,
                    name=cert.name,
                    days_until_expiry=days,
                    expired=expired,
                    risk_score=round(risk_score, 2),
                    severity=severity,
                    expiry_iso=cert.expiry_iso,
                    message=msg,
                )
            )

        # Sort by urgency: expired first, then soonest expiry
        entries.sort(key=lambda e: (not e.expired, e.days_until_expiry if e.days_until_expiry is not None else 99999))

        recs: list[str] = []
        if expired_count > 0:
            recs.append(f"{expired_count} certificate(s) have expired; rotate immediately")
        if critical_count > 0:
            recs.append(f"{critical_count} certificate(s) at critical risk")
        if nearest is not None and 0 <= nearest <= _EXPIRY_HIGH_DAYS:
            recs.append(f"Nearest expiry is in {nearest} days; schedule rotation")

        overall = RiskSeverity.LOW
        if expired_count > 0:
            overall = RiskSeverity.CRITICAL
        elif critical_count > 0:
            overall = RiskSeverity.CRITICAL
        elif nearest is not None and nearest <= _EXPIRY_HIGH_DAYS:
            overall = RiskSeverity.HIGH
        elif nearest is not None and nearest <= _EXPIRY_MEDIUM_DAYS:
            overall = RiskSeverity.MEDIUM

        return ExpiryTimeline(
            entries=entries,
            nearest_expiry_days=nearest,
            expired_count=expired_count,
            critical_count=critical_count,
            overall_risk=overall,
            recommendations=recs,
        )

    # -- 2. Certificate chain validation (root -> intermediate -> leaf) ------

    def validate_chain(
        self,
        cert: CertificateEntry,
        all_certs: Sequence[CertificateEntry],
    ) -> ChainValidationResult:
        """Validate the certificate chain from leaf to root."""
        links: list[ChainLink] = []
        recs: list[str] = []
        valid = True
        complete = True

        # Build the chain from the cert's chain_certificates list
        chain_ids = cert.chain_certificates if cert.chain_certificates else []
        cert_map = {c.id: c for c in all_certs}

        # Add the leaf certificate itself
        leaf_days = _days_until(cert.expiry_dt())
        leaf_valid = leaf_days is None or leaf_days >= 0
        if not leaf_valid:
            valid = False
        links.append(
            ChainLink(
                cert_id=cert.id,
                role=cert.chain_role,
                issuer_ca=cert.issuer_ca,
                days_until_expiry=leaf_days,
                valid=leaf_valid,
                message=f"Leaf certificate '{cert.name}'"
                if leaf_valid
                else f"Leaf certificate '{cert.name}' has expired",
            )
        )

        # Walk the chain
        for chain_cert_id in chain_ids:
            if chain_cert_id not in cert_map:
                complete = False
                valid = False
                links.append(
                    ChainLink(
                        cert_id=chain_cert_id,
                        role=ChainRole.INTERMEDIATE,
                        valid=False,
                        message=f"Chain certificate '{chain_cert_id}' not found",
                    )
                )
                recs.append(f"Missing chain certificate '{chain_cert_id}'")
                continue

            chain_cert = cert_map[chain_cert_id]
            chain_days = _days_until(chain_cert.expiry_dt())
            chain_valid = chain_days is None or chain_days >= 0
            if not chain_valid:
                valid = False
            links.append(
                ChainLink(
                    cert_id=chain_cert_id,
                    role=chain_cert.chain_role,
                    issuer_ca=chain_cert.issuer_ca,
                    days_until_expiry=chain_days,
                    valid=chain_valid,
                    message=f"Chain certificate '{chain_cert.name}'"
                    if chain_valid
                    else f"Chain certificate '{chain_cert.name}' has expired",
                )
            )

        chain_length = len(links)

        if chain_length < 2 and cert.cert_type != CertificateType.SELF_SIGNED:
            recs.append("Certificate chain has fewer than 2 links; verify intermediate certificates")
            complete = False

        if not valid:
            recs.append("One or more certificates in the chain are expired or invalid")

        if cert.cert_type == CertificateType.SELF_SIGNED:
            recs.append("Self-signed certificate detected; use a trusted CA for production")

        if cert.key_size_bits < _MIN_KEY_SIZE:
            recs.append(f"Key size {cert.key_size_bits} bits is below minimum {_MIN_KEY_SIZE}; upgrade key")
            valid = False

        severity = RiskSeverity.LOW
        if not valid:
            severity = RiskSeverity.CRITICAL
        elif not complete:
            severity = RiskSeverity.HIGH
        elif chain_length < 2 and cert.cert_type != CertificateType.SELF_SIGNED:
            severity = RiskSeverity.MEDIUM

        return ChainValidationResult(
            cert_id=cert.id,
            chain_length=chain_length,
            links=links,
            complete=complete,
            valid=valid,
            severity=severity,
            recommendations=recs,
        )

    # -- 3. Auto-renewal capability assessment --------------------------------

    def assess_renewal(
        self,
        cert: CertificateEntry,
    ) -> RenewalAssessment:
        """Assess the auto-renewal capability of a certificate."""
        recs: list[str] = []
        reliable = False

        if cert.auto_renew:
            if cert.renewal_method in (RenewalMethod.ACME, RenewalMethod.CLOUD_MANAGED):
                reliable = True
                risk = RiskSeverity.LOW
            elif cert.renewal_method == RenewalMethod.VENDOR_API:
                reliable = True
                risk = RiskSeverity.LOW
                recs.append("Vendor API renewal depends on external service availability")
            elif cert.renewal_method == RenewalMethod.INTERNAL_CA:
                reliable = True
                risk = RiskSeverity.LOW
                recs.append("Internal CA renewal; ensure CA infrastructure is resilient")
            else:
                # MANUAL with auto_renew is contradictory
                reliable = False
                risk = RiskSeverity.MEDIUM
                recs.append("Auto-renew enabled but renewal method is manual; verify configuration")
        else:
            risk = RiskSeverity.HIGH if cert.renewal_method == RenewalMethod.MANUAL else RiskSeverity.MEDIUM
            recs.append("Auto-renewal is disabled; enable to reduce expiry risk")
            if cert.renewal_method == RenewalMethod.MANUAL:
                recs.append("Manual renewal increases risk of missed rotation deadlines")

        if cert.renewal_days_before_expiry < 14:
            recs.append(
                f"Renewal window of {cert.renewal_days_before_expiry} days is narrow; "
                "consider renewing at least 14 days before expiry"
            )
            if reliable:
                risk = _max_severity(risk, RiskSeverity.MEDIUM)

        days = _days_until(cert.expiry_dt())
        if days is not None and days <= cert.renewal_days_before_expiry and not cert.auto_renew:
            recs.append(
                f"Certificate expires in {days} days and renewal window is "
                f"{cert.renewal_days_before_expiry} days; immediate action needed"
            )
            risk = _max_severity(risk, RiskSeverity.HIGH)

        return RenewalAssessment(
            cert_id=cert.id,
            renewal_method=cert.renewal_method,
            auto_renew=cert.auto_renew,
            renewal_days_before=cert.renewal_days_before_expiry,
            renewal_reliable=reliable,
            risk=risk,
            recommendations=recs,
        )

    # -- 4. Certificate pinning risk analysis ---------------------------------

    def analyze_pinning_risk(
        self,
        cert: CertificateEntry,
        graph: InfraGraph,
    ) -> PinningRiskResult:
        """Analyze the risk associated with certificate pinning configuration."""
        recs: list[str] = []
        rotation_blocked = False
        risk = RiskSeverity.LOW

        affected = self._count_affected(graph, cert)

        if cert.pinning_strategy == PinningStrategy.CERTIFICATE:
            rotation_blocked = True
            risk = RiskSeverity.CRITICAL
            recs.append(
                "Certificate-level pinning blocks rotation; "
                "switch to public key or CA pinning"
            )
        elif cert.pinning_strategy == PinningStrategy.PUBLIC_KEY:
            rotation_blocked = False
            risk = RiskSeverity.MEDIUM
            recs.append(
                "Public key pinning allows key reuse but requires "
                "coordinated client updates on key change"
            )
        elif cert.pinning_strategy == PinningStrategy.CA:
            rotation_blocked = False
            risk = RiskSeverity.LOW
            recs.append("CA pinning provides flexibility for certificate rotation")
        else:
            risk = RiskSeverity.LOW
            recs.append("No pinning configured; consider adding pinning for high-security services")

        if rotation_blocked and affected > 3:
            risk = RiskSeverity.CRITICAL
            recs.append(
                f"Pinning blocks rotation across {affected} services; "
                "high blast radius on rotation"
            )

        return PinningRiskResult(
            cert_id=cert.id,
            pinning_strategy=cert.pinning_strategy,
            rotation_blocked=rotation_blocked,
            risk=risk,
            affected_clients=affected,
            recommendations=recs,
        )

    # -- 5. Wildcard vs SAN certificate coverage gaps -------------------------

    def analyze_coverage(
        self,
        certs: Sequence[CertificateEntry],
        required_domains: Sequence[str],
    ) -> CoverageAnalysis:
        """Analyze coverage gaps between certificates and required domains."""
        if not required_domains:
            return CoverageAnalysis(
                recommendations=["No required domains specified"],
            )

        # Build a coverage map
        covered_set: set[str] = set()
        domain_cert_map: dict[str, str] = {}

        for cert in certs:
            if cert.cert_type == CertificateType.WILDCARD:
                # Wildcard covers *.base_domain
                for domain in required_domains:
                    parts = domain.split(".")
                    if len(parts) >= 2:
                        base = ".".join(parts[-2:])
                        wildcard_base = ".".join(cert.subject.split(".")[-2:]) if cert.subject else ""
                        if base == wildcard_base or f"*.{base}" == cert.subject:
                            covered_set.add(domain)
                            domain_cert_map[domain] = cert.id
                # Also check SAN domains on the wildcard cert
                for san in cert.san_domains:
                    if san in required_domains:
                        covered_set.add(san)
                        domain_cert_map[san] = cert.id
                    elif san.startswith("*."):
                        san_base = san[2:]
                        for domain in required_domains:
                            if domain.endswith(f".{san_base}") or domain == san_base:
                                covered_set.add(domain)
                                domain_cert_map[domain] = cert.id
            elif cert.cert_type == CertificateType.SAN:
                for san in cert.san_domains:
                    if san in required_domains:
                        covered_set.add(san)
                        domain_cert_map[san] = cert.id
            else:
                # Single domain or other types
                if cert.subject in required_domains:
                    covered_set.add(cert.subject)
                    domain_cert_map[cert.subject] = cert.id
                for san in cert.san_domains:
                    if san in required_domains:
                        covered_set.add(san)
                        domain_cert_map[san] = cert.id

        total = len(required_domains)
        covered = len(covered_set)
        uncovered = total - covered

        gaps: list[CoverageGap] = []
        for domain in required_domains:
            if domain in covered_set:
                gaps.append(
                    CoverageGap(
                        domain=domain,
                        covered=True,
                        cert_id=domain_cert_map.get(domain, ""),
                    )
                )
            else:
                gaps.append(
                    CoverageGap(
                        domain=domain,
                        covered=False,
                        gap_type="uncovered",
                    )
                )

        pct = _clamp((covered / total) * 100.0) if total > 0 else 0.0

        recs: list[str] = []
        if uncovered > 0:
            recs.append(f"{uncovered} domain(s) lack TLS certificate coverage")
        if pct < 100.0:
            recs.append("Consider using a SAN or wildcard certificate to close coverage gaps")

        risk_score = 0.1
        if uncovered > 0:
            risk_score += min(0.6, uncovered / total * 0.8)
        risk = _severity_from_score(risk_score)

        return CoverageAnalysis(
            total_domains=total,
            covered_domains=covered,
            uncovered_domains=uncovered,
            gaps=gaps,
            coverage_percent=round(pct, 2),
            risk=risk,
            recommendations=recs,
        )

    # -- 6. mTLS certificate rotation impact ----------------------------------

    def analyze_mtls_impact(
        self,
        cert: CertificateEntry,
        graph: InfraGraph,
        all_certs: Sequence[CertificateEntry],
    ) -> MTLSRotationImpact:
        """Analyze the impact of rotating an mTLS certificate."""
        recs: list[str] = []

        affected_services = self._resolve_affected(graph, cert)
        # Find mutual mTLS dependencies: certs that share components
        mutual: list[str] = []
        for other in all_certs:
            if other.id == cert.id:
                continue
            if not other.is_mtls:
                continue
            shared = set(cert.component_ids) & set(other.component_ids)
            if shared:
                mutual.append(other.id)

        coordinated = len(mutual) > 0

        base_dt = _BASE_ROTATION_DOWNTIME.get(cert.cert_type, 15.0)
        downtime = base_dt * max(1, len(affected_services))
        if cert.auto_renew:
            downtime *= 0.3
        if coordinated:
            downtime *= 1.5  # coordination overhead

        risk_score = 0.1
        if len(affected_services) > 5:
            risk_score += 0.4
        elif len(affected_services) > 2:
            risk_score += 0.2
        if coordinated:
            risk_score += 0.2
        if not cert.auto_renew:
            risk_score += 0.1
        risk = _severity_from_score(min(1.0, risk_score))

        if coordinated:
            recs.append(
                f"Coordinated rotation needed with {len(mutual)} mutual mTLS certificate(s)"
            )
        if not cert.auto_renew:
            recs.append("Enable auto-renewal for mTLS certificates to reduce rotation risk")
        if len(affected_services) > 3:
            recs.append("High number of affected services; consider rolling rotation strategy")

        return MTLSRotationImpact(
            cert_id=cert.id,
            affected_services=affected_services,
            mutual_dependencies=mutual,
            estimated_downtime_seconds=round(max(0.0, downtime), 2),
            coordinated_rotation_needed=coordinated,
            risk=risk,
            recommendations=recs,
        )

    # -- 7. Certificate Authority (CA) dependency risk ------------------------

    def analyze_ca_dependency(
        self,
        certs: Sequence[CertificateEntry],
    ) -> list[CADependencyRisk]:
        """Analyze concentration risk across Certificate Authorities."""
        if not certs:
            return []

        ca_map: dict[str, list[str]] = {}
        for cert in certs:
            ca = cert.issuer_ca or "unknown"
            ca_map.setdefault(ca, []).append(cert.id)

        results: list[CADependencyRisk] = []
        total_certs = len(certs)

        for ca_name, cert_ids in sorted(ca_map.items()):
            count = len(cert_ids)
            single_dep = count >= _CA_CONCENTRATION_THRESHOLD or (
                count == total_certs and total_certs > 1
            )

            recs: list[str] = []
            if single_dep:
                recs.append(
                    f"CA '{ca_name}' serves {count} certificate(s); "
                    "diversify across multiple CAs to reduce single-CA risk"
                )

            risk_score = 0.1
            if total_certs > 0:
                concentration = count / total_certs
                if concentration >= 0.8:
                    risk_score += 0.5
                elif concentration >= 0.5:
                    risk_score += 0.3
                elif concentration >= 0.3:
                    risk_score += 0.15
            if ca_name == "unknown":
                risk_score += 0.2
                recs.append("CA issuer is unknown; verify certificate provenance")

            risk = _severity_from_score(min(1.0, risk_score))

            results.append(
                CADependencyRisk(
                    ca_name=ca_name,
                    cert_count=count,
                    cert_ids=cert_ids,
                    single_ca_dependency=single_dep,
                    risk=risk,
                    recommendations=recs,
                )
            )

        return results

    # -- 8. OCSP/CRL availability assessment ----------------------------------

    def assess_ocsp_crl(
        self,
        cert: CertificateEntry,
    ) -> OCSPCRLAssessment:
        """Assess OCSP and CRL availability for revocation checking."""
        recs: list[str] = []
        revocation_checkable = False

        if cert.ocsp_mode in (OCSPMode.STAPLING, OCSPMode.MUST_STAPLE):
            revocation_checkable = True
        elif cert.ocsp_mode == OCSPMode.RESPONDER:
            revocation_checkable = True
            recs.append("OCSP responder mode may add latency to TLS handshake")

        if cert.crl_mode in (CRLMode.PERIODIC, CRLMode.REAL_TIME):
            revocation_checkable = True
        elif cert.crl_mode == CRLMode.DISABLED and cert.ocsp_mode == OCSPMode.DISABLED:
            recs.append("Both OCSP and CRL are disabled; revocation checking is unavailable")

        risk_score = 0.1
        if not revocation_checkable:
            risk_score += 0.4
            recs.append("Enable OCSP stapling or CRL distribution for revocation support")
        if cert.ocsp_mode == OCSPMode.DISABLED:
            risk_score += 0.15
        if cert.crl_mode == CRLMode.DISABLED:
            risk_score += 0.1

        if cert.ocsp_mode == OCSPMode.MUST_STAPLE:
            recs.append("OCSP Must-Staple provides strongest revocation checking")

        risk = _severity_from_score(min(1.0, risk_score))

        return OCSPCRLAssessment(
            cert_id=cert.id,
            ocsp_mode=cert.ocsp_mode,
            crl_mode=cert.crl_mode,
            revocation_checkable=revocation_checkable,
            risk=risk,
            recommendations=recs,
        )

    # -- 9. Certificate transparency monitoring gaps --------------------------

    def assess_transparency(
        self,
        cert: CertificateEntry,
    ) -> TransparencyAssessment:
        """Assess Certificate Transparency (CT) monitoring status."""
        recs: list[str] = []
        monitored = cert.ct_status == TransparencyStatus.MONITORED

        risk_score = 0.1
        if cert.ct_status == TransparencyStatus.NOT_LOGGED:
            risk_score += 0.4
            recs.append("Certificate is not logged in CT logs; submit to public CT logs")
        elif cert.ct_status == TransparencyStatus.LOGGED:
            risk_score += 0.15
            recs.append("Certificate is logged but not actively monitored; enable CT monitoring")
        else:
            recs.append("Certificate Transparency monitoring is active")

        if cert.cert_type == CertificateType.EV and not monitored:
            risk_score += 0.2
            recs.append("Extended Validation certificates should always be CT-monitored")

        risk = _severity_from_score(min(1.0, risk_score))

        return TransparencyAssessment(
            cert_id=cert.id,
            ct_status=cert.ct_status,
            monitored=monitored,
            risk=risk,
            recommendations=recs,
        )

    # -- 10. Cross-datacenter certificate consistency -------------------------

    def check_datacenter_consistency(
        self,
        certs: Sequence[CertificateEntry],
    ) -> list[DatacenterConsistency]:
        """Check whether certificates are consistent across datacenters."""
        if not certs:
            return []

        # Group by name (same logical cert should be consistent across DCs)
        name_map: dict[str, list[CertificateEntry]] = {}
        for cert in certs:
            name_map.setdefault(cert.name, []).append(cert)

        results: list[DatacenterConsistency] = []

        for name, cert_group in sorted(name_map.items()):
            if len(cert_group) < 2:
                continue  # only check certs that appear in multiple DCs

            datacenters = [c.datacenter for c in cert_group if c.datacenter]
            if len(datacenters) < 2:
                continue

            # Check consistency: same expiry, same issuer, same key size
            reference = cert_group[0]
            mismatched: list[str] = []
            consistent = True

            for other in cert_group[1:]:
                reasons: list[str] = []
                if other.expiry_iso != reference.expiry_iso:
                    reasons.append("expiry_mismatch")
                if other.issuer_ca != reference.issuer_ca:
                    reasons.append("issuer_mismatch")
                if other.key_size_bits != reference.key_size_bits:
                    reasons.append("key_size_mismatch")
                if reasons:
                    consistent = False
                    mismatched.append(f"{other.id}:{','.join(reasons)}")

            recs: list[str] = []
            if not consistent:
                recs.append(
                    f"Certificate '{name}' is inconsistent across datacenters; "
                    "synchronize certificates"
                )
            risk = RiskSeverity.HIGH if not consistent else RiskSeverity.LOW

            results.append(
                DatacenterConsistency(
                    cert_name=name,
                    datacenters=datacenters,
                    consistent=consistent,
                    mismatched_certs=mismatched,
                    risk=risk,
                    recommendations=recs,
                )
            )

        return results

    # -- 11. Certificate rotation downtime estimation -------------------------

    def estimate_rotation_downtime(
        self,
        cert: CertificateEntry,
        graph: InfraGraph,
    ) -> RotationDowntimeEstimate:
        """Estimate the downtime associated with rotating a certificate."""
        affected = self._resolve_affected(graph, cert)
        num_affected = len(affected)

        base_dt = _BASE_ROTATION_DOWNTIME.get(cert.cert_type, 10.0)
        downtime = base_dt * max(1, num_affected)

        zero_downtime = False
        if cert.auto_renew and cert.renewal_method in (
            RenewalMethod.ACME,
            RenewalMethod.CLOUD_MANAGED,
        ):
            downtime *= 0.1
            zero_downtime = True

        if cert.rotation_downtime_seconds > 0:
            downtime = cert.rotation_downtime_seconds * max(1, num_affected)
            if cert.auto_renew:
                downtime *= 0.3
                zero_downtime = True

        recs: list[str] = []
        if not zero_downtime:
            recs.append("Consider ACME or cloud-managed renewal for near-zero downtime")
        if num_affected > 5:
            recs.append(f"Rotation affects {num_affected} services; use rolling rotation")
        if not cert.auto_renew:
            recs.append("Enable auto-renewal to reduce rotation downtime")

        risk_score = 0.1
        if downtime > 300:
            risk_score += 0.5
        elif downtime > 60:
            risk_score += 0.3
        elif downtime > 10:
            risk_score += 0.15
        if not zero_downtime:
            risk_score += 0.1
        risk = _severity_from_score(min(1.0, risk_score))

        return RotationDowntimeEstimate(
            cert_id=cert.id,
            estimated_downtime_seconds=round(max(0.0, downtime), 2),
            affected_component_count=num_affected,
            zero_downtime_possible=zero_downtime,
            risk=risk,
            recommendations=recs,
        )

    # -- 12. Expiry cascade analysis (shared CA/intermediate expiry) ----------

    def analyze_expiry_cascade(
        self,
        certs: Sequence[CertificateEntry],
    ) -> ExpiryCascadeAnalysis:
        """Analyze cascade effects when a shared CA or intermediate expires.

        If a root or intermediate certificate expires, all leaf certificates
        signed by it become invalid.
        """
        if not certs:
            return ExpiryCascadeAnalysis(
                recommendations=["No certificates to analyze"],
            )

        {c.id: c for c in certs}
        cascades: list[CascadeEntry] = []

        # Find root and intermediate certs
        non_leaf = [c for c in certs if c.chain_role in (ChainRole.ROOT, ChainRole.INTERMEDIATE)]

        for parent in non_leaf:
            # Find certs that reference this parent in their chain
            affected_ids: list[str] = []
            for cert in certs:
                if cert.id == parent.id:
                    continue
                if parent.id in cert.chain_certificates:
                    affected_ids.append(cert.id)
                # Also check by issuer_ca matching
                elif cert.issuer_ca and cert.issuer_ca == parent.issuer_ca and cert.chain_role == ChainRole.LEAF:
                    if parent.chain_role == ChainRole.INTERMEDIATE:
                        affected_ids.append(cert.id)

            if not affected_ids:
                continue

            days = _days_until(parent.expiry_dt())
            severity = _severity_for_expiry_days(days)

            recs: list[str] = []
            cascade_type = (
                "root_expiry" if parent.chain_role == ChainRole.ROOT else "intermediate_expiry"
            )

            if days is not None and days < 0:
                recs.append(
                    f"{parent.chain_role.value.capitalize()} certificate '{parent.name}' "
                    f"has expired; {len(affected_ids)} dependent cert(s) are invalid"
                )
            elif days is not None and days <= _EXPIRY_HIGH_DAYS:
                recs.append(
                    f"{parent.chain_role.value.capitalize()} certificate '{parent.name}' "
                    f"expires in {days} days; {len(affected_ids)} cert(s) will cascade"
                )

            cascades.append(
                CascadeEntry(
                    source_cert_id=parent.id,
                    affected_cert_ids=affected_ids,
                    affected_count=len(affected_ids),
                    cascade_type=cascade_type,
                    risk=severity,
                    recommendations=recs,
                )
            )

        max_size = max((c.affected_count for c in cascades), default=0)

        overall_recs: list[str] = []
        if max_size > 5:
            overall_recs.append(
                f"Largest cascade affects {max_size} certificates; "
                "diversify intermediate CAs"
            )
        if any(c.risk == RiskSeverity.CRITICAL for c in cascades):
            overall_recs.append("Critical cascade risk detected; rotate parent certificates first")

        overall = RiskSeverity.LOW
        if cascades:
            overall = _max_severity(*(c.risk for c in cascades))

        return ExpiryCascadeAnalysis(
            cascades=cascades,
            max_cascade_size=max_size,
            overall_risk=overall,
            recommendations=overall_recs,
        )

    # -- Full analysis -------------------------------------------------------

    def full_analysis(
        self,
        graph: InfraGraph,
        certs: Sequence[CertificateEntry],
        required_domains: Sequence[str] | None = None,
    ) -> FullCertificateReport:
        """Run all analyses and return a consolidated report."""
        if not certs:
            return FullCertificateReport(
                recommendations=["No certificates to analyze"],
            )

        timeline = self.build_expiry_timeline(certs)

        chains = [self.validate_chain(c, certs) for c in certs]
        renewals = [self.assess_renewal(c) for c in certs]
        pinning = [self.analyze_pinning_risk(c, graph) for c in certs]

        coverage = (
            self.analyze_coverage(certs, required_domains)
            if required_domains
            else None
        )

        mtls_certs = [c for c in certs if c.is_mtls]
        mtls_impacts = [self.analyze_mtls_impact(c, graph, certs) for c in mtls_certs]

        ca_risks = self.analyze_ca_dependency(certs)
        ocsp_crl = [self.assess_ocsp_crl(c) for c in certs]
        transparency = [self.assess_transparency(c) for c in certs]
        dc_consistency = self.check_datacenter_consistency(certs)
        downtimes = [self.estimate_rotation_downtime(c, graph) for c in certs]
        cascade = self.analyze_expiry_cascade(certs)

        # Determine overall risk
        all_severities = [timeline.overall_risk, cascade.overall_risk]
        for chain in chains:
            all_severities.append(chain.severity)
        for r in renewals:
            all_severities.append(r.risk)
        for p in pinning:
            all_severities.append(p.risk)
        for o in ocsp_crl:
            all_severities.append(o.risk)
        for d in downtimes:
            all_severities.append(d.risk)
        if coverage:
            all_severities.append(coverage.risk)
        for ca in ca_risks:
            all_severities.append(ca.risk)

        overall = _max_severity(*all_severities) if all_severities else RiskSeverity.LOW

        top_recs: list[str] = []
        if timeline.expired_count > 0:
            top_recs.append(f"{timeline.expired_count} expired certificate(s) require immediate rotation")
        auto_renew_count = sum(1 for c in certs if c.auto_renew)
        if auto_renew_count < len(certs):
            top_recs.append(
                f"{len(certs) - auto_renew_count} certificate(s) lack auto-renewal"
            )
        if cascade.max_cascade_size > 0:
            top_recs.append(
                f"Expiry cascade risk detected; max cascade size is {cascade.max_cascade_size}"
            )

        return FullCertificateReport(
            expiry_timeline=timeline,
            chain_validations=chains,
            renewal_assessments=renewals,
            pinning_risks=pinning,
            coverage_analysis=coverage,
            mtls_impacts=mtls_impacts,
            ca_risks=ca_risks,
            ocsp_crl_assessments=ocsp_crl,
            transparency_assessments=transparency,
            datacenter_consistency=dc_consistency,
            rotation_downtimes=downtimes,
            cascade_analysis=cascade,
            overall_risk=overall,
            total_certificates=len(certs),
            recommendations=top_recs,
        )

    # -- Private helpers -----------------------------------------------------

    def _resolve_affected(
        self,
        graph: InfraGraph,
        cert: CertificateEntry,
    ) -> list[str]:
        """Return component IDs in *cert* that exist in *graph*."""
        return [cid for cid in cert.component_ids if graph.get_component(cid) is not None]

    def _count_affected(
        self,
        graph: InfraGraph,
        cert: CertificateEntry,
    ) -> int:
        """Return count of valid affected components."""
        return len(self._resolve_affected(graph, cert))
