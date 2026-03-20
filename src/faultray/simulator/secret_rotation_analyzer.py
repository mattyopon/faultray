# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Secret Rotation Analyzer.

Analyzes secrets/credential rotation practices and their impact on system
availability.  Goes beyond the basic :class:`SecretRotationEngine` by providing
rotation-frequency compliance checking, rotation-window analysis, dual-secret
strategy evaluation, certificate chain validation, blast-radius mapping for
expired credentials, rotation automation maturity assessment, secret-sprawl
detection, emergency rotation playbook generation, rotation dependency ordering,
and compliance framework mapping (PCI-DSS, SOC2, HIPAA).

Designed for commercial chaos engineering: helps teams proactively identify
credential management weaknesses before they cause outages.
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


class SecretKind(str, Enum):
    """Types of secrets / credentials managed by an organisation."""

    API_KEY = "api_key"
    DATABASE_PASSWORD = "database_password"
    TLS_CERTIFICATE = "tls_certificate"
    OAUTH_TOKEN = "oauth_token"
    ENCRYPTION_KEY = "encryption_key"
    SSH_KEY = "ssh_key"


class ComplianceFramework(str, Enum):
    """Compliance frameworks with secret-rotation requirements."""

    PCI_DSS = "pci_dss"
    SOC2 = "soc2"
    HIPAA = "hipaa"


class MaturityLevel(str, Enum):
    """Rotation automation maturity levels."""

    MANUAL = "manual"
    SEMI_AUTOMATED = "semi_automated"
    FULLY_AUTOMATED = "fully_automated"
    ADAPTIVE = "adaptive"


class RiskSeverity(str, Enum):
    """Risk severity classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PlaybookPriority(str, Enum):
    """Emergency playbook step priority."""

    IMMEDIATE = "immediate"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SecretEntry:
    """A single secret that requires rotation management."""

    id: str
    name: str
    kind: SecretKind
    component_ids: list[str] = field(default_factory=list)
    rotation_interval_days: int = 90
    last_rotated_iso: str = ""
    expiry_iso: str = ""
    auto_rotate: bool = False
    dual_secret_enabled: bool = False
    grace_period_hours: float = 0.0
    # For TLS certificates
    cert_chain_length: int = 0
    cert_issuer: str = ""

    def last_rotated_dt(self) -> datetime | None:
        return _parse_iso(self.last_rotated_iso)

    def expiry_dt(self) -> datetime | None:
        return _parse_iso(self.expiry_iso)


@dataclass
class FrequencyComplianceResult:
    """Result of checking a secret's rotation frequency against policy."""

    secret_id: str
    kind: SecretKind
    required_interval_days: int
    actual_interval_days: int | None
    compliant: bool
    overdue_days: int = 0
    severity: RiskSeverity = RiskSeverity.LOW
    message: str = ""


@dataclass
class RotationWindowAnalysis:
    """Analysis of the rotation window for a secret."""

    secret_id: str
    estimated_downtime_seconds: float = 0.0
    grace_period_hours: float = 0.0
    overlap_safe: bool = True
    dual_secret_active: bool = False
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DualSecretAnalysis:
    """Analysis of dual-secret (old+new coexist) strategy."""

    secret_id: str
    dual_enabled: bool = False
    overlap_hours: float = 0.0
    zero_downtime: bool = False
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CertChainValidation:
    """TLS certificate chain validation result."""

    secret_id: str
    chain_length: int = 0
    issuer: str = ""
    days_until_expiry: int | None = None
    expired: bool = False
    expiry_risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class BlastRadiusEntry:
    """Blast radius of an expired or rotated credential."""

    secret_id: str
    directly_affected: list[str] = field(default_factory=list)
    transitively_affected: list[str] = field(default_factory=list)
    total_affected_count: int = 0
    affected_percent: float = 0.0
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class MaturityAssessment:
    """Rotation automation maturity assessment."""

    overall_level: MaturityLevel = MaturityLevel.MANUAL
    score: float = 0.0  # 0-100
    auto_rotate_ratio: float = 0.0
    dual_secret_ratio: float = 0.0
    grace_period_ratio: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SprawlEntry:
    """A secret found across multiple services (secret sprawl)."""

    secret_id: str
    name: str
    kind: SecretKind
    service_count: int = 0
    component_ids: list[str] = field(default_factory=list)
    risk: RiskSeverity = RiskSeverity.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PlaybookStep:
    """A single step in an emergency rotation playbook."""

    order: int
    description: str
    priority: PlaybookPriority = PlaybookPriority.MEDIUM
    estimated_seconds: float = 0.0
    responsible: str = ""


@dataclass
class EmergencyPlaybook:
    """Emergency rotation playbook for a secret."""

    secret_id: str
    secret_name: str
    kind: SecretKind
    steps: list[PlaybookStep] = field(default_factory=list)
    total_estimated_seconds: float = 0.0
    risk: RiskSeverity = RiskSeverity.LOW


@dataclass
class RotationDependency:
    """A dependency ordering constraint: rotate source before target."""

    source_secret_id: str
    target_secret_id: str
    reason: str = ""


@dataclass
class RotationOrder:
    """Ordered list of secrets for rotation with dependency constraints."""

    ordered_ids: list[str] = field(default_factory=list)
    dependencies: list[RotationDependency] = field(default_factory=list)
    has_cycle: bool = False
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ComplianceMapping:
    """Mapping of a secret against a compliance framework's rotation rules."""

    secret_id: str
    framework: ComplianceFramework
    required_interval_days: int = 0
    current_interval_days: int | None = None
    compliant: bool = True
    gap_days: int = 0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ComplianceReport:
    """Full compliance report across all frameworks and secrets."""

    framework: ComplianceFramework
    total_secrets: int = 0
    compliant_count: int = 0
    non_compliant_count: int = 0
    compliance_percent: float = 0.0
    mappings: list[ComplianceMapping] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Recommended max rotation intervals per secret kind (days)
_DEFAULT_MAX_ROTATION_DAYS: dict[SecretKind, int] = {
    SecretKind.API_KEY: 90,
    SecretKind.DATABASE_PASSWORD: 90,
    SecretKind.TLS_CERTIFICATE: 365,
    SecretKind.OAUTH_TOKEN: 30,
    SecretKind.ENCRYPTION_KEY: 365,
    SecretKind.SSH_KEY: 180,
}

# Base downtime seconds when rotating without dual-secret
_BASE_ROTATION_DOWNTIME: dict[SecretKind, float] = {
    SecretKind.API_KEY: 5.0,
    SecretKind.DATABASE_PASSWORD: 15.0,
    SecretKind.TLS_CERTIFICATE: 10.0,
    SecretKind.OAUTH_TOKEN: 3.0,
    SecretKind.ENCRYPTION_KEY: 20.0,
    SecretKind.SSH_KEY: 8.0,
}

# Emergency rotation base time (seconds)
_EMERGENCY_BASE_TIME: dict[SecretKind, float] = {
    SecretKind.API_KEY: 30.0,
    SecretKind.DATABASE_PASSWORD: 120.0,
    SecretKind.TLS_CERTIFICATE: 180.0,
    SecretKind.OAUTH_TOKEN: 15.0,
    SecretKind.ENCRYPTION_KEY: 300.0,
    SecretKind.SSH_KEY: 60.0,
}

# Compliance framework rotation requirements (max days)
_COMPLIANCE_ROTATION_DAYS: dict[ComplianceFramework, dict[SecretKind, int]] = {
    ComplianceFramework.PCI_DSS: {
        SecretKind.API_KEY: 90,
        SecretKind.DATABASE_PASSWORD: 90,
        SecretKind.TLS_CERTIFICATE: 365,
        SecretKind.OAUTH_TOKEN: 30,
        SecretKind.ENCRYPTION_KEY: 365,
        SecretKind.SSH_KEY: 90,
    },
    ComplianceFramework.SOC2: {
        SecretKind.API_KEY: 180,
        SecretKind.DATABASE_PASSWORD: 90,
        SecretKind.TLS_CERTIFICATE: 365,
        SecretKind.OAUTH_TOKEN: 60,
        SecretKind.ENCRYPTION_KEY: 365,
        SecretKind.SSH_KEY: 180,
    },
    ComplianceFramework.HIPAA: {
        SecretKind.API_KEY: 90,
        SecretKind.DATABASE_PASSWORD: 60,
        SecretKind.TLS_CERTIFICATE: 365,
        SecretKind.OAUTH_TOKEN: 30,
        SecretKind.ENCRYPTION_KEY: 180,
        SecretKind.SSH_KEY: 90,
    },
}


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


def _days_since(dt: datetime | None) -> int | None:
    """Return the number of days since *dt*, or *None* if unknown."""
    if dt is None:
        return None
    dt = _ensure_utc(dt)
    now = datetime.now(timezone.utc)
    delta = now - dt
    return max(0, delta.days)


def _days_until(dt: datetime | None) -> int | None:
    """Return the number of days until *dt*, or *None* if unknown."""
    if dt is None:
        return None
    dt = _ensure_utc(dt)
    now = datetime.now(timezone.utc)
    delta = dt - now
    return delta.days  # can be negative if past


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class SecretRotationAnalyzer:
    """Comprehensive secret rotation analysis engine.

    All methods are stateless and take an :class:`InfraGraph` plus one or more
    :class:`SecretEntry` instances as input.
    """

    # -- 1. Rotation frequency compliance -----------------------------------

    def check_frequency_compliance(
        self,
        secrets: Sequence[SecretEntry],
        overrides: dict[SecretKind, int] | None = None,
    ) -> list[FrequencyComplianceResult]:
        """Check each secret against its recommended rotation frequency.

        Parameters
        ----------
        secrets:
            Secrets to check.
        overrides:
            Optional per-kind overrides for the maximum rotation interval (days).
        """
        max_days = dict(_DEFAULT_MAX_ROTATION_DAYS)
        if overrides:
            max_days.update(overrides)

        results: list[FrequencyComplianceResult] = []
        for s in secrets:
            required = max_days.get(s.kind, 90)
            last_dt = s.last_rotated_dt()
            actual_days = _days_since(last_dt)

            if actual_days is None:
                results.append(
                    FrequencyComplianceResult(
                        secret_id=s.id,
                        kind=s.kind,
                        required_interval_days=required,
                        actual_interval_days=None,
                        compliant=False,
                        overdue_days=0,
                        severity=RiskSeverity.HIGH,
                        message="No rotation history recorded",
                    )
                )
                continue

            compliant = actual_days <= required
            overdue = max(0, actual_days - required)

            if overdue == 0:
                severity = RiskSeverity.LOW
            elif overdue <= 30:
                severity = RiskSeverity.MEDIUM
            elif overdue <= 90:
                severity = RiskSeverity.HIGH
            else:
                severity = RiskSeverity.CRITICAL

            msg = (
                f"Rotated {actual_days}d ago (limit {required}d)"
                if compliant
                else f"Overdue by {overdue}d (limit {required}d)"
            )

            results.append(
                FrequencyComplianceResult(
                    secret_id=s.id,
                    kind=s.kind,
                    required_interval_days=required,
                    actual_interval_days=actual_days,
                    compliant=compliant,
                    overdue_days=overdue,
                    severity=severity,
                    message=msg,
                )
            )
        return results

    # -- 2. Rotation window analysis ----------------------------------------

    def analyze_rotation_window(
        self,
        graph: InfraGraph,
        secret: SecretEntry,
    ) -> RotationWindowAnalysis:
        """Analyze expected downtime and overlap safety during rotation."""
        num_affected = self._count_affected(graph, secret)
        base_dt = _BASE_ROTATION_DOWNTIME.get(secret.kind, 10.0)

        if secret.dual_secret_enabled:
            downtime = 0.0
            overlap_safe = True
        elif secret.grace_period_hours > 0:
            downtime = base_dt * 0.5 * max(1, num_affected)
            overlap_safe = True
        else:
            downtime = base_dt * max(1, num_affected)
            overlap_safe = False

        if secret.auto_rotate:
            downtime *= 0.5

        risk_score = 0.1
        if not overlap_safe:
            risk_score += 0.3
        if num_affected > 5:
            risk_score += 0.3
        elif num_affected > 2:
            risk_score += 0.15
        if not secret.auto_rotate:
            risk_score += 0.1
        risk = _severity_from_score(min(1.0, risk_score))

        recs: list[str] = []
        if not secret.dual_secret_enabled:
            recs.append("Enable dual-secret strategy for zero-downtime rotation")
        if not secret.auto_rotate:
            recs.append("Enable auto-rotation to reduce rotation window")
        if not overlap_safe:
            recs.append("Add grace period to allow old+new overlap during rotation")
        if num_affected > 5:
            recs.append("High fan-out; consider per-service credentials")

        return RotationWindowAnalysis(
            secret_id=secret.id,
            estimated_downtime_seconds=round(max(0.0, downtime), 2),
            grace_period_hours=secret.grace_period_hours,
            overlap_safe=overlap_safe,
            dual_secret_active=secret.dual_secret_enabled,
            risk=risk,
            recommendations=recs,
        )

    # -- 3. Dual-secret strategy analysis -----------------------------------

    def analyze_dual_secret(
        self,
        secret: SecretEntry,
    ) -> DualSecretAnalysis:
        """Evaluate the dual-secret (old+new coexist) strategy."""
        if secret.dual_secret_enabled:
            overlap = max(secret.grace_period_hours, 1.0)
            return DualSecretAnalysis(
                secret_id=secret.id,
                dual_enabled=True,
                overlap_hours=overlap,
                zero_downtime=True,
                risk=RiskSeverity.LOW,
                recommendations=["Dual-secret is active; ensure old secret is revoked after overlap"],
            )

        recs: list[str] = ["Enable dual-secret to achieve zero-downtime rotation"]
        if secret.grace_period_hours > 0:
            risk = RiskSeverity.MEDIUM
            recs.append("Grace period provides partial overlap but is not as robust as dual-secret")
            return DualSecretAnalysis(
                secret_id=secret.id,
                dual_enabled=False,
                overlap_hours=secret.grace_period_hours,
                zero_downtime=False,
                risk=risk,
                recommendations=recs,
            )

        return DualSecretAnalysis(
            secret_id=secret.id,
            dual_enabled=False,
            overlap_hours=0.0,
            zero_downtime=False,
            risk=RiskSeverity.HIGH,
            recommendations=recs + ["No grace period configured; rotation will cause downtime"],
        )

    # -- 4. Certificate chain validation ------------------------------------

    def validate_cert_chain(
        self,
        secret: SecretEntry,
    ) -> CertChainValidation:
        """Validate TLS certificate chain and expiry for a cert-type secret."""
        recs: list[str] = []

        chain_len = secret.cert_chain_length
        issuer = secret.cert_issuer

        expiry_dt = secret.expiry_dt()
        days_left = _days_until(expiry_dt)
        expired = False
        expiry_risk = RiskSeverity.LOW

        if days_left is not None:
            if days_left < 0:
                expired = True
                expiry_risk = RiskSeverity.CRITICAL
                recs.append("Certificate has expired; rotate immediately")
            elif days_left <= 7:
                expiry_risk = RiskSeverity.CRITICAL
                recs.append("Certificate expires within 7 days; schedule urgent rotation")
            elif days_left <= 30:
                expiry_risk = RiskSeverity.HIGH
                recs.append("Certificate expires within 30 days; plan rotation")
            elif days_left <= 90:
                expiry_risk = RiskSeverity.MEDIUM
                recs.append("Certificate expires within 90 days; add to rotation queue")
        else:
            expiry_risk = RiskSeverity.MEDIUM
            recs.append("No expiry date recorded; verify certificate expiry")

        if chain_len == 0:
            recs.append("Certificate chain length unknown; verify chain completeness")
        elif chain_len < 2:
            recs.append("Self-signed certificate detected; use a trusted CA")

        if not issuer:
            recs.append("No issuer recorded; verify certificate authority")

        if not secret.auto_rotate:
            recs.append("Enable auto-rotation for TLS certificates")

        return CertChainValidation(
            secret_id=secret.id,
            chain_length=chain_len,
            issuer=issuer,
            days_until_expiry=days_left,
            expired=expired,
            expiry_risk=expiry_risk,
            recommendations=recs,
        )

    # -- 5. Blast radius of expired/rotated credentials ---------------------

    def calculate_blast_radius(
        self,
        graph: InfraGraph,
        secret: SecretEntry,
    ) -> BlastRadiusEntry:
        """Calculate the blast radius if *secret* expires or is rotated."""
        total = len(graph.components)
        if total == 0:
            return BlastRadiusEntry(
                secret_id=secret.id,
                recommendations=["No components in graph"],
            )

        directly: list[str] = [
            cid for cid in secret.component_ids if graph.get_component(cid) is not None
        ]

        trans_set: set[str] = set()
        for cid in directly:
            for dep_id in graph.get_all_affected(cid):
                if dep_id not in directly:
                    trans_set.add(dep_id)

        transitively = sorted(trans_set)
        all_count = len(set(directly) | trans_set)
        pct = _clamp((all_count / total) * 100.0)

        risk_score = 0.1
        if pct > 50.0:
            risk_score += 0.5
        elif pct > 25.0:
            risk_score += 0.3
        elif pct > 10.0:
            risk_score += 0.15
        if len(directly) > 3:
            risk_score += 0.2
        risk = _severity_from_score(min(1.0, risk_score))

        recs: list[str] = []
        if pct > 50.0:
            recs.append("Over 50% of services affected; isolate credentials per service")
        if trans_set:
            recs.append(f"{len(trans_set)} service(s) transitively affected; add circuit breakers")
        if len(directly) > 3:
            recs.append("Split this secret into per-service credentials")

        return BlastRadiusEntry(
            secret_id=secret.id,
            directly_affected=directly,
            transitively_affected=transitively,
            total_affected_count=all_count,
            affected_percent=round(pct, 2),
            risk=risk,
            recommendations=recs,
        )

    # -- 6. Rotation automation maturity ------------------------------------

    def assess_maturity(
        self,
        secrets: Sequence[SecretEntry],
    ) -> MaturityAssessment:
        """Assess the rotation automation maturity across all secrets."""
        if not secrets:
            return MaturityAssessment(
                overall_level=MaturityLevel.MANUAL,
                score=0.0,
                recommendations=["No secrets to assess"],
            )

        total = len(secrets)
        auto_count = sum(1 for s in secrets if s.auto_rotate)
        dual_count = sum(1 for s in secrets if s.dual_secret_enabled)
        grace_count = sum(1 for s in secrets if s.grace_period_hours > 0)

        auto_ratio = auto_count / total
        dual_ratio = dual_count / total
        grace_ratio = grace_count / total

        # Weighted score
        score = (auto_ratio * 50.0) + (dual_ratio * 30.0) + (grace_ratio * 20.0)
        score = _clamp(score)

        if score >= 80.0:
            level = MaturityLevel.ADAPTIVE
        elif score >= 50.0:
            level = MaturityLevel.FULLY_AUTOMATED
        elif score >= 25.0:
            level = MaturityLevel.SEMI_AUTOMATED
        else:
            level = MaturityLevel.MANUAL

        recs: list[str] = []
        if auto_ratio < 1.0:
            recs.append(f"{total - auto_count} secret(s) lack auto-rotation")
        if dual_ratio < 0.5:
            recs.append("Less than 50% of secrets use dual-secret strategy")
        if grace_ratio < 0.5:
            recs.append("Less than 50% of secrets have a grace period configured")
        if level == MaturityLevel.MANUAL:
            recs.append("Overall maturity is MANUAL; prioritise auto-rotation enablement")

        return MaturityAssessment(
            overall_level=level,
            score=round(score, 2),
            auto_rotate_ratio=round(auto_ratio, 4),
            dual_secret_ratio=round(dual_ratio, 4),
            grace_period_ratio=round(grace_ratio, 4),
            recommendations=recs,
        )

    # -- 7. Secret sprawl detection -----------------------------------------

    def detect_sprawl(
        self,
        secrets: Sequence[SecretEntry],
        threshold: int = 2,
    ) -> list[SprawlEntry]:
        """Detect secrets that are used across multiple services (sprawl).

        Parameters
        ----------
        threshold:
            Minimum number of components for a secret to be flagged.
        """
        results: list[SprawlEntry] = []
        for s in secrets:
            count = len(s.component_ids)
            if count < threshold:
                continue

            risk_score = 0.1
            if count >= 10:
                risk_score += 0.6
            elif count >= 5:
                risk_score += 0.4
            elif count >= 3:
                risk_score += 0.2
            else:
                risk_score += 0.1
            risk = _severity_from_score(min(1.0, risk_score))

            recs: list[str] = []
            recs.append(
                f"Secret '{s.name}' is used in {count} services; "
                "consider per-service credentials"
            )
            if not s.auto_rotate:
                recs.append("Enable auto-rotation to reduce sprawl risk")
            if not s.dual_secret_enabled:
                recs.append("Enable dual-secret for safe rotation across services")

            results.append(
                SprawlEntry(
                    secret_id=s.id,
                    name=s.name,
                    kind=s.kind,
                    service_count=count,
                    component_ids=list(s.component_ids),
                    risk=risk,
                    recommendations=recs,
                )
            )
        return results

    # -- 8. Emergency rotation playbook -------------------------------------

    def generate_emergency_playbook(
        self,
        graph: InfraGraph,
        secret: SecretEntry,
    ) -> EmergencyPlaybook:
        """Generate an emergency rotation playbook for a compromised secret."""
        base_time = _EMERGENCY_BASE_TIME.get(secret.kind, 60.0)
        steps: list[PlaybookStep] = []
        order = 0

        # Step 1: Revoke compromised secret
        order += 1
        steps.append(
            PlaybookStep(
                order=order,
                description=f"Revoke compromised secret '{secret.name}' immediately",
                priority=PlaybookPriority.IMMEDIATE,
                estimated_seconds=base_time * 0.1,
                responsible="security",
            )
        )

        # Step 2: Notify security team
        order += 1
        steps.append(
            PlaybookStep(
                order=order,
                description="Notify security team and initiate incident response",
                priority=PlaybookPriority.IMMEDIATE,
                estimated_seconds=30.0,
                responsible="security",
            )
        )

        # Step 3: Generate new secret
        order += 1
        steps.append(
            PlaybookStep(
                order=order,
                description=f"Generate new {secret.kind.value} credential",
                priority=PlaybookPriority.HIGH,
                estimated_seconds=base_time * 0.2,
                responsible="platform",
            )
        )

        # Step 4: Deploy new secret to affected services
        affected = self._resolve_affected(graph, secret)
        deploy_time = base_time * 0.3 * max(1, len(affected))
        if secret.auto_rotate:
            deploy_time *= 0.3
        order += 1
        steps.append(
            PlaybookStep(
                order=order,
                description=f"Deploy new secret to {len(affected)} affected service(s)",
                priority=PlaybookPriority.HIGH,
                estimated_seconds=round(deploy_time, 2),
                responsible="platform",
            )
        )

        # Step 5: Verify services
        order += 1
        steps.append(
            PlaybookStep(
                order=order,
                description="Verify all affected services are operational with new secret",
                priority=PlaybookPriority.HIGH,
                estimated_seconds=base_time * 0.2,
                responsible="sre",
            )
        )

        # Step 6: Audit logs
        order += 1
        steps.append(
            PlaybookStep(
                order=order,
                description="Audit access logs for unauthorised usage of compromised secret",
                priority=PlaybookPriority.MEDIUM,
                estimated_seconds=base_time * 0.5,
                responsible="security",
            )
        )

        # Step 7: Post-incident review
        order += 1
        steps.append(
            PlaybookStep(
                order=order,
                description="Conduct post-incident review and update rotation policies",
                priority=PlaybookPriority.LOW,
                estimated_seconds=base_time * 0.5,
                responsible="security",
            )
        )

        total_time = sum(s.estimated_seconds for s in steps)

        num_affected = len(affected)
        risk_score = 0.2
        if num_affected > 5:
            risk_score += 0.4
        elif num_affected > 2:
            risk_score += 0.2
        if not secret.auto_rotate:
            risk_score += 0.2
        risk = _severity_from_score(min(1.0, risk_score))

        return EmergencyPlaybook(
            secret_id=secret.id,
            secret_name=secret.name,
            kind=secret.kind,
            steps=steps,
            total_estimated_seconds=round(total_time, 2),
            risk=risk,
        )

    # -- 9. Rotation dependency ordering ------------------------------------

    def compute_rotation_order(
        self,
        graph: InfraGraph,
        secrets: Sequence[SecretEntry],
    ) -> RotationOrder:
        """Determine the order to rotate secrets based on dependency constraints.

        Encryption keys and TLS certificates should be rotated before API keys
        and database passwords that depend on the same components.
        """
        if not secrets:
            return RotationOrder(recommendations=["No secrets to order"])

        # Build a priority map: lower = rotate first
        _priority: dict[SecretKind, int] = {
            SecretKind.ENCRYPTION_KEY: 0,
            SecretKind.TLS_CERTIFICATE: 1,
            SecretKind.SSH_KEY: 2,
            SecretKind.DATABASE_PASSWORD: 3,
            SecretKind.OAUTH_TOKEN: 4,
            SecretKind.API_KEY: 5,
        }

        # Discover dependencies between secrets via shared component_ids
        secret_by_id: dict[str, SecretEntry] = {s.id: s for s in secrets}
        deps: list[RotationDependency] = []
        ids = list(secret_by_id.keys())

        for i, sid_a in enumerate(ids):
            for sid_b in ids[i + 1 :]:
                sa = secret_by_id[sid_a]
                sb = secret_by_id[sid_b]
                shared = set(sa.component_ids) & set(sb.component_ids)
                if not shared:
                    continue
                pa = _priority.get(sa.kind, 99)
                pb = _priority.get(sb.kind, 99)
                if pa < pb:
                    deps.append(
                        RotationDependency(
                            source_secret_id=sid_a,
                            target_secret_id=sid_b,
                            reason=f"{sa.kind.value} should be rotated before {sb.kind.value} (shared components: {sorted(shared)})",
                        )
                    )
                elif pb < pa:
                    deps.append(
                        RotationDependency(
                            source_secret_id=sid_b,
                            target_secret_id=sid_a,
                            reason=f"{sb.kind.value} should be rotated before {sa.kind.value} (shared components: {sorted(shared)})",
                        )
                    )

        # Topological sort with cycle detection
        adj: dict[str, list[str]] = {s.id: [] for s in secrets}
        in_deg: dict[str, int] = {s.id: 0 for s in secrets}
        for d in deps:
            adj[d.source_secret_id].append(d.target_secret_id)
            in_deg[d.target_secret_id] += 1

        queue: list[str] = []
        for sid in ids:
            if in_deg[sid] == 0:
                queue.append(sid)

        # Stable sort: within the same topological level, sort by kind priority
        queue.sort(key=lambda sid: _priority.get(secret_by_id[sid].kind, 99))
        ordered: list[str] = []
        while queue:
            sid = queue.pop(0)
            ordered.append(sid)
            for nxt in sorted(
                adj[sid],
                key=lambda s: _priority.get(secret_by_id[s].kind, 99),
            ):
                in_deg[nxt] -= 1
                if in_deg[nxt] == 0:
                    queue.append(nxt)
            queue.sort(key=lambda sid: _priority.get(secret_by_id[sid].kind, 99))

        has_cycle = len(ordered) < len(secrets)

        recs: list[str] = []
        if has_cycle:
            recs.append("Circular dependency detected in rotation order; review secret relationships")
            # Add remaining secrets in priority order
            remaining = [s.id for s in secrets if s.id not in ordered]
            remaining.sort(key=lambda sid: _priority.get(secret_by_id[sid].kind, 99))
            ordered.extend(remaining)
        if deps:
            recs.append(f"{len(deps)} rotation dependency constraint(s) identified")

        return RotationOrder(
            ordered_ids=ordered,
            dependencies=deps,
            has_cycle=has_cycle,
            recommendations=recs,
        )

    # -- 10. Compliance framework mapping -----------------------------------

    def map_compliance(
        self,
        secrets: Sequence[SecretEntry],
        framework: ComplianceFramework,
    ) -> ComplianceReport:
        """Map secrets against a compliance framework's rotation requirements."""
        fw_rules = _COMPLIANCE_ROTATION_DAYS.get(framework, {})
        mappings: list[ComplianceMapping] = []
        compliant_count = 0

        for s in secrets:
            required = fw_rules.get(s.kind, 90)
            last_dt = s.last_rotated_dt()
            actual = _days_since(last_dt)

            if actual is None:
                gap = 0
                is_compliant = False
            else:
                gap = max(0, actual - required)
                is_compliant = actual <= required

            recs: list[str] = []
            if not is_compliant:
                recs.append(
                    f"Non-compliant with {framework.value}: "
                    f"secret '{s.name}' requires rotation every {required}d"
                )
                if actual is not None:
                    recs.append(f"Last rotated {actual}d ago; overdue by {gap}d")
                else:
                    recs.append("No rotation history; rotate immediately")
            else:
                compliant_count += 1

            mappings.append(
                ComplianceMapping(
                    secret_id=s.id,
                    framework=framework,
                    required_interval_days=required,
                    current_interval_days=actual,
                    compliant=is_compliant,
                    gap_days=gap,
                    recommendations=recs,
                )
            )

        total = len(secrets)
        non_compliant = total - compliant_count
        pct = _clamp((compliant_count / total) * 100.0) if total > 0 else 0.0

        report_recs: list[str] = []
        if non_compliant > 0:
            report_recs.append(
                f"{non_compliant} of {total} secrets are non-compliant with {framework.value}"
            )
        if pct == 100.0:
            report_recs.append(f"All secrets comply with {framework.value} requirements")

        return ComplianceReport(
            framework=framework,
            total_secrets=total,
            compliant_count=compliant_count,
            non_compliant_count=non_compliant,
            compliance_percent=round(pct, 2),
            mappings=mappings,
            recommendations=report_recs,
        )

    # -- 11. Full analysis --------------------------------------------------

    def full_analysis(
        self,
        graph: InfraGraph,
        secrets: Sequence[SecretEntry],
    ) -> dict:
        """Run all analyses and return a consolidated report dictionary."""
        freq = self.check_frequency_compliance(secrets)
        windows = [self.analyze_rotation_window(graph, s) for s in secrets]
        duals = [self.analyze_dual_secret(s) for s in secrets]
        certs = [
            self.validate_cert_chain(s)
            for s in secrets
            if s.kind == SecretKind.TLS_CERTIFICATE
        ]
        blasts = [self.calculate_blast_radius(graph, s) for s in secrets]
        maturity = self.assess_maturity(secrets)
        sprawl = self.detect_sprawl(secrets)
        playbooks = [self.generate_emergency_playbook(graph, s) for s in secrets]
        order = self.compute_rotation_order(graph, secrets)

        compliance_reports = [
            self.map_compliance(secrets, fw)
            for fw in ComplianceFramework
        ]

        return {
            "frequency_compliance": freq,
            "rotation_windows": windows,
            "dual_secret_analyses": duals,
            "cert_chain_validations": certs,
            "blast_radii": blasts,
            "maturity": maturity,
            "sprawl": sprawl,
            "playbooks": playbooks,
            "rotation_order": order,
            "compliance_reports": compliance_reports,
        }

    # -- private helpers ----------------------------------------------------

    def _resolve_affected(
        self,
        graph: InfraGraph,
        secret: SecretEntry,
    ) -> list[str]:
        """Return component IDs in *secret* that exist in *graph*."""
        return [cid for cid in secret.component_ids if graph.get_component(cid) is not None]

    def _count_affected(
        self,
        graph: InfraGraph,
        secret: SecretEntry,
    ) -> int:
        """Return count of valid affected components."""
        return len(self._resolve_affected(graph, secret))
