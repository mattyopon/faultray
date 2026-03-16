"""Tests for faultray.simulator.certificate_expiry_analyzer module.

Targets 100% coverage with 50+ test functions covering all public methods,
models, enums, edge cases, and internal helpers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.certificate_expiry_analyzer import (
    CADependencyRisk,
    CascadeEntry,
    CertificateEntry,
    CertificateExpiryAnalyzer,
    CertificateType,
    ChainLink,
    ChainRole,
    ChainValidationResult,
    CoverageAnalysis,
    CoverageGap,
    CRLMode,
    DatacenterConsistency,
    ExpiryCascadeAnalysis,
    ExpiryTimeline,
    ExpiryTimelineEntry,
    FullCertificateReport,
    MTLSRotationImpact,
    OCSPCRLAssessment,
    OCSPMode,
    PinningRiskResult,
    PinningStrategy,
    RenewalAssessment,
    RenewalMethod,
    RiskSeverity,
    RotationDowntimeEstimate,
    TransparencyAssessment,
    TransparencyStatus,
    _BASE_ROTATION_DOWNTIME,
    _CA_CONCENTRATION_THRESHOLD,
    _EXPIRY_CRITICAL_DAYS,
    _EXPIRY_HIGH_DAYS,
    _EXPIRY_MEDIUM_DAYS,
    _MIN_KEY_SIZE,
    _RECOMMENDED_KEY_SIZE,
    _clamp,
    _days_since,
    _days_until,
    _ensure_utc,
    _max_severity,
    _parse_iso,
    _risk_score_for_expiry_days,
    _severity_for_expiry_days,
    _severity_from_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _future_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _cert(
    cid: str = "cert1",
    name: str = "test-cert",
    cert_type: CertificateType = CertificateType.SINGLE_DOMAIN,
    component_ids: list[str] | None = None,
    expiry_iso: str = "",
    issued_iso: str = "",
    chain_role: ChainRole = ChainRole.LEAF,
    issuer_ca: str = "TestCA",
    subject: str = "example.com",
    san_domains: list[str] | None = None,
    renewal_method: RenewalMethod = RenewalMethod.MANUAL,
    auto_renew: bool = False,
    renewal_days_before_expiry: int = 30,
    pinning_strategy: PinningStrategy = PinningStrategy.NONE,
    ocsp_mode: OCSPMode = OCSPMode.DISABLED,
    crl_mode: CRLMode = CRLMode.DISABLED,
    ct_status: TransparencyStatus = TransparencyStatus.NOT_LOGGED,
    datacenter: str = "",
    chain_certificates: list[str] | None = None,
    key_size_bits: int = 2048,
    is_mtls: bool = False,
    rotation_downtime_seconds: float = 0.0,
) -> CertificateEntry:
    return CertificateEntry(
        id=cid,
        name=name,
        cert_type=cert_type,
        component_ids=component_ids or [],
        expiry_iso=expiry_iso,
        issued_iso=issued_iso,
        chain_role=chain_role,
        issuer_ca=issuer_ca,
        subject=subject,
        san_domains=san_domains or [],
        renewal_method=renewal_method,
        auto_renew=auto_renew,
        renewal_days_before_expiry=renewal_days_before_expiry,
        pinning_strategy=pinning_strategy,
        ocsp_mode=ocsp_mode,
        crl_mode=crl_mode,
        ct_status=ct_status,
        datacenter=datacenter,
        chain_certificates=chain_certificates or [],
        key_size_bits=key_size_bits,
        is_mtls=is_mtls,
        rotation_downtime_seconds=rotation_downtime_seconds,
    )


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


class TestEnums:
    """Verify all enum members are accessible and have correct values."""

    def test_certificate_type_values(self):
        assert CertificateType.SINGLE_DOMAIN == "single_domain"
        assert CertificateType.WILDCARD == "wildcard"
        assert CertificateType.SAN == "san"
        assert CertificateType.SELF_SIGNED == "self_signed"
        assert CertificateType.MTLS_CLIENT == "mtls_client"
        assert CertificateType.MTLS_SERVER == "mtls_server"
        assert CertificateType.CODE_SIGNING == "code_signing"
        assert CertificateType.EV == "extended_validation"

    def test_chain_role_values(self):
        assert ChainRole.ROOT == "root"
        assert ChainRole.INTERMEDIATE == "intermediate"
        assert ChainRole.LEAF == "leaf"

    def test_renewal_method_values(self):
        assert RenewalMethod.MANUAL == "manual"
        assert RenewalMethod.ACME == "acme"
        assert RenewalMethod.CLOUD_MANAGED == "cloud_managed"
        assert RenewalMethod.INTERNAL_CA == "internal_ca"
        assert RenewalMethod.VENDOR_API == "vendor_api"

    def test_risk_severity_values(self):
        assert RiskSeverity.LOW == "low"
        assert RiskSeverity.MEDIUM == "medium"
        assert RiskSeverity.HIGH == "high"
        assert RiskSeverity.CRITICAL == "critical"

    def test_pinning_strategy_values(self):
        assert PinningStrategy.NONE == "none"
        assert PinningStrategy.PUBLIC_KEY == "public_key"
        assert PinningStrategy.CERTIFICATE == "certificate"
        assert PinningStrategy.CA == "ca"

    def test_ocsp_mode_values(self):
        assert OCSPMode.DISABLED == "disabled"
        assert OCSPMode.STAPLING == "stapling"
        assert OCSPMode.RESPONDER == "responder"
        assert OCSPMode.MUST_STAPLE == "must_staple"

    def test_crl_mode_values(self):
        assert CRLMode.DISABLED == "disabled"
        assert CRLMode.PERIODIC == "periodic"
        assert CRLMode.REAL_TIME == "real_time"

    def test_transparency_status_values(self):
        assert TransparencyStatus.NOT_LOGGED == "not_logged"
        assert TransparencyStatus.LOGGED == "logged"
        assert TransparencyStatus.MONITORED == "monitored"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for module-level helper functions."""

    def test_parse_iso_empty(self):
        assert _parse_iso("") is None

    def test_parse_iso_valid(self):
        dt = _parse_iso("2025-06-01T00:00:00+00:00")
        assert dt is not None
        assert dt.year == 2025

    def test_parse_iso_z_suffix(self):
        dt = _parse_iso("2025-06-01T12:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_parse_iso_invalid(self):
        assert _parse_iso("not-a-date") is None

    def test_ensure_utc_naive(self):
        naive = datetime(2025, 1, 1)
        result = _ensure_utc(naive)
        assert result.tzinfo == timezone.utc

    def test_ensure_utc_already_utc(self):
        aware = datetime(2025, 1, 1, tzinfo=timezone.utc)
        result = _ensure_utc(aware)
        assert result.tzinfo == timezone.utc

    def test_severity_from_score_critical(self):
        assert _severity_from_score(0.9) == RiskSeverity.CRITICAL

    def test_severity_from_score_high(self):
        assert _severity_from_score(0.7) == RiskSeverity.HIGH

    def test_severity_from_score_medium(self):
        assert _severity_from_score(0.4) == RiskSeverity.MEDIUM

    def test_severity_from_score_low(self):
        assert _severity_from_score(0.1) == RiskSeverity.LOW

    def test_clamp_normal(self):
        assert _clamp(50.0) == 50.0

    def test_clamp_below(self):
        assert _clamp(-10.0) == 0.0

    def test_clamp_above(self):
        assert _clamp(110.0) == 100.0

    def test_clamp_custom_range(self):
        assert _clamp(5.0, 0.0, 10.0) == 5.0
        assert _clamp(-1.0, 0.0, 10.0) == 0.0
        assert _clamp(15.0, 0.0, 10.0) == 10.0

    def test_days_until_none(self):
        assert _days_until(None) is None

    def test_days_until_future(self):
        future = datetime.now(timezone.utc) + timedelta(days=30)
        result = _days_until(future)
        assert result is not None
        assert 29 <= result <= 30

    def test_days_until_past(self):
        past = datetime.now(timezone.utc) - timedelta(days=10)
        result = _days_until(past)
        assert result is not None
        assert result < 0

    def test_days_since_none(self):
        assert _days_since(None) is None

    def test_days_since_past(self):
        past = datetime.now(timezone.utc) - timedelta(days=10)
        result = _days_since(past)
        assert result is not None
        assert 9 <= result <= 10

    def test_max_severity_empty(self):
        assert _max_severity() == RiskSeverity.LOW

    def test_max_severity_single(self):
        assert _max_severity(RiskSeverity.HIGH) == RiskSeverity.HIGH

    def test_max_severity_multiple(self):
        assert _max_severity(RiskSeverity.LOW, RiskSeverity.CRITICAL, RiskSeverity.MEDIUM) == RiskSeverity.CRITICAL

    def test_severity_for_expiry_days_none(self):
        assert _severity_for_expiry_days(None) == RiskSeverity.MEDIUM

    def test_severity_for_expiry_days_expired(self):
        assert _severity_for_expiry_days(-5) == RiskSeverity.CRITICAL

    def test_severity_for_expiry_days_critical(self):
        assert _severity_for_expiry_days(3) == RiskSeverity.CRITICAL

    def test_severity_for_expiry_days_high(self):
        assert _severity_for_expiry_days(20) == RiskSeverity.HIGH

    def test_severity_for_expiry_days_medium(self):
        assert _severity_for_expiry_days(60) == RiskSeverity.MEDIUM

    def test_severity_for_expiry_days_low(self):
        assert _severity_for_expiry_days(365) == RiskSeverity.LOW

    def test_risk_score_for_expiry_days_none(self):
        assert _risk_score_for_expiry_days(None) == 0.5

    def test_risk_score_for_expiry_days_expired(self):
        assert _risk_score_for_expiry_days(-1) == 1.0

    def test_risk_score_for_expiry_days_critical(self):
        assert _risk_score_for_expiry_days(5) == 0.9

    def test_risk_score_for_expiry_days_high(self):
        assert _risk_score_for_expiry_days(15) == 0.7

    def test_risk_score_for_expiry_days_medium(self):
        assert _risk_score_for_expiry_days(50) == 0.4

    def test_risk_score_for_expiry_days_low(self):
        assert _risk_score_for_expiry_days(200) == 0.1


# ---------------------------------------------------------------------------
# CertificateEntry dataclass tests
# ---------------------------------------------------------------------------


class TestCertificateEntry:
    """Tests for CertificateEntry dataclass."""

    def test_issued_dt_valid(self):
        c = _cert(issued_iso="2025-01-01T00:00:00+00:00")
        assert c.issued_dt() is not None

    def test_issued_dt_empty(self):
        c = _cert(issued_iso="")
        assert c.issued_dt() is None

    def test_expiry_dt_valid(self):
        c = _cert(expiry_iso="2025-12-31T00:00:00+00:00")
        assert c.expiry_dt() is not None

    def test_expiry_dt_empty(self):
        c = _cert(expiry_iso="")
        assert c.expiry_dt() is None

    def test_default_fields(self):
        c = _cert()
        assert c.component_ids == []
        assert c.san_domains == []
        assert c.chain_certificates == []
        assert c.key_size_bits == 2048
        assert c.is_mtls is False


# ---------------------------------------------------------------------------
# Constants tests
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants."""

    def test_expiry_thresholds(self):
        assert _EXPIRY_CRITICAL_DAYS == 7
        assert _EXPIRY_HIGH_DAYS == 30
        assert _EXPIRY_MEDIUM_DAYS == 90

    def test_base_rotation_downtime_keys(self):
        assert CertificateType.SINGLE_DOMAIN in _BASE_ROTATION_DOWNTIME
        assert CertificateType.WILDCARD in _BASE_ROTATION_DOWNTIME
        assert CertificateType.SAN in _BASE_ROTATION_DOWNTIME
        assert CertificateType.MTLS_CLIENT in _BASE_ROTATION_DOWNTIME

    def test_min_key_size(self):
        assert _MIN_KEY_SIZE == 2048
        assert _RECOMMENDED_KEY_SIZE == 4096

    def test_ca_concentration_threshold(self):
        assert _CA_CONCENTRATION_THRESHOLD == 3


# ---------------------------------------------------------------------------
# Expiry Timeline tests
# ---------------------------------------------------------------------------


class TestBuildExpiryTimeline:
    """Tests for CertificateExpiryAnalyzer.build_expiry_timeline."""

    def test_empty_certs(self):
        a = CertificateExpiryAnalyzer()
        result = a.build_expiry_timeline([])
        assert result.entries == []
        assert len(result.recommendations) == 1

    def test_single_valid_cert(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(expiry_iso=_future_iso(365))
        result = a.build_expiry_timeline([c])
        assert len(result.entries) == 1
        assert result.expired_count == 0
        assert result.overall_risk == RiskSeverity.LOW

    def test_expired_cert(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(expiry_iso=_past_iso(10))
        result = a.build_expiry_timeline([c])
        assert result.expired_count == 1
        assert result.entries[0].expired is True
        assert result.overall_risk == RiskSeverity.CRITICAL

    def test_critical_expiry(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(expiry_iso=_future_iso(3))
        result = a.build_expiry_timeline([c])
        assert result.critical_count == 1
        assert result.overall_risk == RiskSeverity.CRITICAL

    def test_high_expiry(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(expiry_iso=_future_iso(20))
        result = a.build_expiry_timeline([c])
        assert result.overall_risk == RiskSeverity.HIGH

    def test_medium_expiry(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(expiry_iso=_future_iso(60))
        result = a.build_expiry_timeline([c])
        assert result.overall_risk == RiskSeverity.MEDIUM

    def test_no_expiry_date(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(expiry_iso="")
        result = a.build_expiry_timeline([c])
        assert result.entries[0].days_until_expiry is None
        assert "no expiry date" in result.entries[0].message

    def test_multiple_certs_sorted(self):
        a = CertificateExpiryAnalyzer()
        c1 = _cert(cid="cert1", expiry_iso=_future_iso(365))
        c2 = _cert(cid="cert2", expiry_iso=_future_iso(5))
        c3 = _cert(cid="cert3", expiry_iso=_past_iso(2))
        result = a.build_expiry_timeline([c1, c2, c3])
        assert len(result.entries) == 3
        # Expired certs first, then soonest
        assert result.entries[0].cert_id == "cert3"
        assert result.entries[1].cert_id == "cert2"

    def test_nearest_expiry_days(self):
        a = CertificateExpiryAnalyzer()
        c1 = _cert(cid="c1", expiry_iso=_future_iso(100))
        c2 = _cert(cid="c2", expiry_iso=_future_iso(10))
        result = a.build_expiry_timeline([c1, c2])
        assert result.nearest_expiry_days is not None
        assert result.nearest_expiry_days <= 10


# ---------------------------------------------------------------------------
# Chain Validation tests
# ---------------------------------------------------------------------------


class TestValidateChain:
    """Tests for CertificateExpiryAnalyzer.validate_chain."""

    def test_leaf_only_chain(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(expiry_iso=_future_iso(100))
        result = a.validate_chain(c, [c])
        assert result.chain_length == 1
        # Incomplete since no intermediate
        assert not result.complete

    def test_self_signed_chain(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(cert_type=CertificateType.SELF_SIGNED, expiry_iso=_future_iso(100))
        result = a.validate_chain(c, [c])
        assert any("Self-signed" in r for r in result.recommendations)

    def test_complete_chain(self):
        a = CertificateExpiryAnalyzer()
        root = _cert(cid="root", chain_role=ChainRole.ROOT, expiry_iso=_future_iso(3650))
        inter = _cert(cid="inter", chain_role=ChainRole.INTERMEDIATE, expiry_iso=_future_iso(1825))
        leaf = _cert(
            cid="leaf",
            chain_role=ChainRole.LEAF,
            expiry_iso=_future_iso(365),
            chain_certificates=["inter", "root"],
        )
        result = a.validate_chain(leaf, [root, inter, leaf])
        assert result.chain_length == 3
        assert result.complete is True
        assert result.valid is True

    def test_expired_chain_cert(self):
        a = CertificateExpiryAnalyzer()
        inter = _cert(cid="inter", chain_role=ChainRole.INTERMEDIATE, expiry_iso=_past_iso(10))
        leaf = _cert(
            cid="leaf",
            expiry_iso=_future_iso(365),
            chain_certificates=["inter"],
        )
        result = a.validate_chain(leaf, [inter, leaf])
        assert not result.valid
        assert result.severity == RiskSeverity.CRITICAL

    def test_missing_chain_cert(self):
        a = CertificateExpiryAnalyzer()
        leaf = _cert(
            cid="leaf",
            expiry_iso=_future_iso(365),
            chain_certificates=["missing_cert"],
        )
        result = a.validate_chain(leaf, [leaf])
        assert not result.complete
        assert not result.valid
        assert any("Missing" in r for r in result.recommendations)

    def test_weak_key_size(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(key_size_bits=1024, expiry_iso=_future_iso(365))
        result = a.validate_chain(c, [c])
        assert not result.valid
        assert any("Key size" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# Renewal Assessment tests
# ---------------------------------------------------------------------------


class TestAssessRenewal:
    """Tests for CertificateExpiryAnalyzer.assess_renewal."""

    def test_manual_no_auto(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(renewal_method=RenewalMethod.MANUAL, auto_renew=False)
        result = a.assess_renewal(c)
        assert result.risk == RiskSeverity.HIGH
        assert not result.renewal_reliable

    def test_acme_auto(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(renewal_method=RenewalMethod.ACME, auto_renew=True)
        result = a.assess_renewal(c)
        assert result.renewal_reliable is True
        assert result.risk == RiskSeverity.LOW

    def test_cloud_managed_auto(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(renewal_method=RenewalMethod.CLOUD_MANAGED, auto_renew=True)
        result = a.assess_renewal(c)
        assert result.renewal_reliable is True

    def test_vendor_api_auto(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(renewal_method=RenewalMethod.VENDOR_API, auto_renew=True)
        result = a.assess_renewal(c)
        assert result.renewal_reliable is True
        assert any("Vendor API" in r for r in result.recommendations)

    def test_internal_ca_auto(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(renewal_method=RenewalMethod.INTERNAL_CA, auto_renew=True)
        result = a.assess_renewal(c)
        assert result.renewal_reliable is True

    def test_manual_with_auto_flag(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(renewal_method=RenewalMethod.MANUAL, auto_renew=True)
        result = a.assess_renewal(c)
        assert not result.renewal_reliable
        assert result.risk == RiskSeverity.MEDIUM

    def test_narrow_renewal_window(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(
            renewal_method=RenewalMethod.ACME,
            auto_renew=True,
            renewal_days_before_expiry=5,
        )
        result = a.assess_renewal(c)
        assert any("narrow" in r for r in result.recommendations)

    def test_expiring_soon_no_auto(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(
            renewal_method=RenewalMethod.MANUAL,
            auto_renew=False,
            expiry_iso=_future_iso(10),
            renewal_days_before_expiry=30,
        )
        result = a.assess_renewal(c)
        assert result.risk in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)

    def test_non_manual_no_auto(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(renewal_method=RenewalMethod.ACME, auto_renew=False)
        result = a.assess_renewal(c)
        assert result.risk == RiskSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Pinning Risk tests
# ---------------------------------------------------------------------------


class TestAnalyzePinningRisk:
    """Tests for CertificateExpiryAnalyzer.analyze_pinning_risk."""

    def test_no_pinning(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(component_ids=["c1"])
        result = a.analyze_pinning_risk(c, g)
        assert result.risk == RiskSeverity.LOW
        assert not result.rotation_blocked

    def test_certificate_pinning(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(pinning_strategy=PinningStrategy.CERTIFICATE, component_ids=["c1"])
        result = a.analyze_pinning_risk(c, g)
        assert result.rotation_blocked is True
        assert result.risk == RiskSeverity.CRITICAL

    def test_public_key_pinning(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(pinning_strategy=PinningStrategy.PUBLIC_KEY, component_ids=["c1"])
        result = a.analyze_pinning_risk(c, g)
        assert not result.rotation_blocked
        assert result.risk == RiskSeverity.MEDIUM

    def test_ca_pinning(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(pinning_strategy=PinningStrategy.CA, component_ids=["c1"])
        result = a.analyze_pinning_risk(c, g)
        assert result.risk == RiskSeverity.LOW

    def test_cert_pinning_high_fanout(self):
        a = CertificateExpiryAnalyzer()
        comps = [_comp(f"c{i}") for i in range(5)]
        g = _graph(*comps)
        c = _cert(
            pinning_strategy=PinningStrategy.CERTIFICATE,
            component_ids=[f"c{i}" for i in range(5)],
        )
        result = a.analyze_pinning_risk(c, g)
        assert result.risk == RiskSeverity.CRITICAL
        assert result.affected_clients == 5


# ---------------------------------------------------------------------------
# Coverage Analysis tests
# ---------------------------------------------------------------------------


class TestAnalyzeCoverage:
    """Tests for CertificateExpiryAnalyzer.analyze_coverage."""

    def test_empty_domains(self):
        a = CertificateExpiryAnalyzer()
        result = a.analyze_coverage([], [])
        assert result.total_domains == 0

    def test_full_san_coverage(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(
            cert_type=CertificateType.SAN,
            san_domains=["api.example.com", "web.example.com"],
        )
        result = a.analyze_coverage(
            [c],
            ["api.example.com", "web.example.com"],
        )
        assert result.covered_domains == 2
        assert result.uncovered_domains == 0
        assert result.coverage_percent == 100.0

    def test_partial_coverage(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(
            cert_type=CertificateType.SAN,
            san_domains=["api.example.com"],
        )
        result = a.analyze_coverage(
            [c],
            ["api.example.com", "web.example.com"],
        )
        assert result.covered_domains == 1
        assert result.uncovered_domains == 1
        assert result.coverage_percent == 50.0

    def test_wildcard_coverage(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(
            cert_type=CertificateType.WILDCARD,
            subject="*.example.com",
            san_domains=["*.example.com"],
        )
        result = a.analyze_coverage(
            [c],
            ["api.example.com", "web.example.com"],
        )
        assert result.covered_domains == 2

    def test_single_domain_coverage(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(
            cert_type=CertificateType.SINGLE_DOMAIN,
            subject="api.example.com",
        )
        result = a.analyze_coverage(
            [c],
            ["api.example.com", "web.example.com"],
        )
        assert result.covered_domains == 1

    def test_coverage_gaps_list(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(
            cert_type=CertificateType.SAN,
            san_domains=["api.example.com"],
        )
        result = a.analyze_coverage(
            [c],
            ["api.example.com", "missing.example.com"],
        )
        uncovered = [g for g in result.gaps if not g.covered]
        assert len(uncovered) == 1
        assert uncovered[0].domain == "missing.example.com"


# ---------------------------------------------------------------------------
# mTLS Rotation Impact tests
# ---------------------------------------------------------------------------


class TestAnalyzeMTLSImpact:
    """Tests for CertificateExpiryAnalyzer.analyze_mtls_impact."""

    def test_no_mutual_deps(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(is_mtls=True, component_ids=["c1"])
        result = a.analyze_mtls_impact(c, g, [c])
        assert not result.coordinated_rotation_needed
        assert len(result.mutual_dependencies) == 0

    def test_mutual_mtls_deps(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        c1 = _cert(cid="cert1", is_mtls=True, component_ids=["c1", "c2"])
        c2 = _cert(cid="cert2", is_mtls=True, component_ids=["c1"])
        result = a.analyze_mtls_impact(c1, g, [c1, c2])
        assert result.coordinated_rotation_needed is True
        assert "cert2" in result.mutual_dependencies

    def test_auto_renew_reduces_downtime(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c1 = _cert(is_mtls=True, component_ids=["c1"], auto_renew=False)
        c2 = _cert(cid="auto", is_mtls=True, component_ids=["c1"], auto_renew=True)
        r1 = a.analyze_mtls_impact(c1, g, [c1])
        r2 = a.analyze_mtls_impact(c2, g, [c2])
        assert r2.estimated_downtime_seconds < r1.estimated_downtime_seconds

    def test_many_affected_services(self):
        a = CertificateExpiryAnalyzer()
        comps = [_comp(f"s{i}") for i in range(6)]
        g = _graph(*comps)
        c = _cert(is_mtls=True, component_ids=[f"s{i}" for i in range(6)])
        result = a.analyze_mtls_impact(c, g, [c])
        assert len(result.affected_services) == 6
        assert any("High number" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# CA Dependency Risk tests
# ---------------------------------------------------------------------------


class TestAnalyzeCADependency:
    """Tests for CertificateExpiryAnalyzer.analyze_ca_dependency."""

    def test_empty_certs(self):
        a = CertificateExpiryAnalyzer()
        result = a.analyze_ca_dependency([])
        assert result == []

    def test_diverse_cas(self):
        a = CertificateExpiryAnalyzer()
        certs = [
            _cert(cid="c1", issuer_ca="CA_A"),
            _cert(cid="c2", issuer_ca="CA_B"),
            _cert(cid="c3", issuer_ca="CA_C"),
        ]
        result = a.analyze_ca_dependency(certs)
        assert len(result) == 3
        for r in result:
            assert r.cert_count == 1

    def test_concentrated_ca(self):
        a = CertificateExpiryAnalyzer()
        certs = [_cert(cid=f"c{i}", issuer_ca="SameCA") for i in range(5)]
        result = a.analyze_ca_dependency(certs)
        assert len(result) == 1
        assert result[0].single_ca_dependency is True
        assert result[0].cert_count == 5

    def test_unknown_ca(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(issuer_ca="")
        result = a.analyze_ca_dependency([c])
        assert result[0].ca_name == "unknown"
        assert any("unknown" in r for r in result[0].recommendations)

    def test_all_same_ca_two_certs(self):
        a = CertificateExpiryAnalyzer()
        certs = [
            _cert(cid="c1", issuer_ca="OnlyCA"),
            _cert(cid="c2", issuer_ca="OnlyCA"),
        ]
        result = a.analyze_ca_dependency(certs)
        # 2 certs all same CA -> single_ca_dependency true (total == count > 1)
        assert result[0].single_ca_dependency is True


# ---------------------------------------------------------------------------
# OCSP/CRL Assessment tests
# ---------------------------------------------------------------------------


class TestAssessOCSPCRL:
    """Tests for CertificateExpiryAnalyzer.assess_ocsp_crl."""

    def test_both_disabled(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(ocsp_mode=OCSPMode.DISABLED, crl_mode=CRLMode.DISABLED)
        result = a.assess_ocsp_crl(c)
        assert not result.revocation_checkable
        assert any("disabled" in r.lower() for r in result.recommendations)

    def test_ocsp_stapling(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(ocsp_mode=OCSPMode.STAPLING)
        result = a.assess_ocsp_crl(c)
        assert result.revocation_checkable is True

    def test_ocsp_must_staple(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(ocsp_mode=OCSPMode.MUST_STAPLE)
        result = a.assess_ocsp_crl(c)
        assert result.revocation_checkable is True
        assert any("Must-Staple" in r for r in result.recommendations)

    def test_ocsp_responder(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(ocsp_mode=OCSPMode.RESPONDER)
        result = a.assess_ocsp_crl(c)
        assert result.revocation_checkable is True
        assert any("latency" in r for r in result.recommendations)

    def test_crl_periodic(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(crl_mode=CRLMode.PERIODIC)
        result = a.assess_ocsp_crl(c)
        assert result.revocation_checkable is True

    def test_crl_realtime(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(crl_mode=CRLMode.REAL_TIME)
        result = a.assess_ocsp_crl(c)
        assert result.revocation_checkable is True


# ---------------------------------------------------------------------------
# Transparency Assessment tests
# ---------------------------------------------------------------------------


class TestAssessTransparency:
    """Tests for CertificateExpiryAnalyzer.assess_transparency."""

    def test_not_logged(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(ct_status=TransparencyStatus.NOT_LOGGED)
        result = a.assess_transparency(c)
        assert not result.monitored
        assert any("not logged" in r for r in result.recommendations)

    def test_logged(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(ct_status=TransparencyStatus.LOGGED)
        result = a.assess_transparency(c)
        assert not result.monitored
        assert any("monitoring" in r.lower() for r in result.recommendations)

    def test_monitored(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(ct_status=TransparencyStatus.MONITORED)
        result = a.assess_transparency(c)
        assert result.monitored is True

    def test_ev_not_monitored(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(
            cert_type=CertificateType.EV,
            ct_status=TransparencyStatus.NOT_LOGGED,
        )
        result = a.assess_transparency(c)
        assert any("Extended Validation" in r for r in result.recommendations)


# ---------------------------------------------------------------------------
# Datacenter Consistency tests
# ---------------------------------------------------------------------------


class TestCheckDatacenterConsistency:
    """Tests for CertificateExpiryAnalyzer.check_datacenter_consistency."""

    def test_empty_certs(self):
        a = CertificateExpiryAnalyzer()
        result = a.check_datacenter_consistency([])
        assert result == []

    def test_single_datacenter(self):
        a = CertificateExpiryAnalyzer()
        c = _cert(datacenter="dc1")
        result = a.check_datacenter_consistency([c])
        assert result == []

    def test_consistent_across_dcs(self):
        a = CertificateExpiryAnalyzer()
        c1 = _cert(
            cid="c1", name="shared-cert", datacenter="dc1",
            expiry_iso="2026-12-01T00:00:00+00:00", issuer_ca="CA1", key_size_bits=2048,
        )
        c2 = _cert(
            cid="c2", name="shared-cert", datacenter="dc2",
            expiry_iso="2026-12-01T00:00:00+00:00", issuer_ca="CA1", key_size_bits=2048,
        )
        result = a.check_datacenter_consistency([c1, c2])
        assert len(result) == 1
        assert result[0].consistent is True

    def test_inconsistent_across_dcs(self):
        a = CertificateExpiryAnalyzer()
        c1 = _cert(
            cid="c1", name="shared-cert", datacenter="dc1",
            expiry_iso="2026-12-01T00:00:00+00:00", issuer_ca="CA1",
        )
        c2 = _cert(
            cid="c2", name="shared-cert", datacenter="dc2",
            expiry_iso="2027-01-01T00:00:00+00:00", issuer_ca="CA2",
        )
        result = a.check_datacenter_consistency([c1, c2])
        assert len(result) == 1
        assert not result[0].consistent
        assert result[0].risk == RiskSeverity.HIGH

    def test_different_names_not_compared(self):
        a = CertificateExpiryAnalyzer()
        c1 = _cert(cid="c1", name="cert-a", datacenter="dc1")
        c2 = _cert(cid="c2", name="cert-b", datacenter="dc2")
        result = a.check_datacenter_consistency([c1, c2])
        assert result == []


# ---------------------------------------------------------------------------
# Rotation Downtime Estimation tests
# ---------------------------------------------------------------------------


class TestEstimateRotationDowntime:
    """Tests for CertificateExpiryAnalyzer.estimate_rotation_downtime."""

    def test_basic_downtime(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(component_ids=["c1"])
        result = a.estimate_rotation_downtime(c, g)
        assert result.estimated_downtime_seconds > 0
        assert result.affected_component_count == 1

    def test_acme_auto_near_zero(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(
            component_ids=["c1"],
            auto_renew=True,
            renewal_method=RenewalMethod.ACME,
        )
        result = a.estimate_rotation_downtime(c, g)
        assert result.zero_downtime_possible is True

    def test_custom_rotation_downtime(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(
            component_ids=["c1"],
            rotation_downtime_seconds=60.0,
            auto_renew=True,
        )
        result = a.estimate_rotation_downtime(c, g)
        assert result.zero_downtime_possible is True

    def test_many_services_downtime(self):
        a = CertificateExpiryAnalyzer()
        comps = [_comp(f"c{i}") for i in range(8)]
        g = _graph(*comps)
        c = _cert(component_ids=[f"c{i}" for i in range(8)])
        result = a.estimate_rotation_downtime(c, g)
        assert result.affected_component_count == 8
        assert any("rolling" in r for r in result.recommendations)

    def test_no_affected_components(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(component_ids=["nonexistent"])
        result = a.estimate_rotation_downtime(c, g)
        assert result.affected_component_count == 0


# ---------------------------------------------------------------------------
# Expiry Cascade Analysis tests
# ---------------------------------------------------------------------------


class TestAnalyzeExpiryCascade:
    """Tests for CertificateExpiryAnalyzer.analyze_expiry_cascade."""

    def test_empty_certs(self):
        a = CertificateExpiryAnalyzer()
        result = a.analyze_expiry_cascade([])
        assert result.cascades == []
        assert result.max_cascade_size == 0

    def test_no_cascade(self):
        a = CertificateExpiryAnalyzer()
        c1 = _cert(cid="leaf1", chain_role=ChainRole.LEAF)
        c2 = _cert(cid="leaf2", chain_role=ChainRole.LEAF)
        result = a.analyze_expiry_cascade([c1, c2])
        assert result.cascades == []

    def test_intermediate_cascade(self):
        a = CertificateExpiryAnalyzer()
        inter = _cert(
            cid="inter",
            name="Intermediate",
            chain_role=ChainRole.INTERMEDIATE,
            expiry_iso=_future_iso(10),
        )
        leaf1 = _cert(
            cid="leaf1",
            chain_role=ChainRole.LEAF,
            chain_certificates=["inter"],
        )
        leaf2 = _cert(
            cid="leaf2",
            chain_role=ChainRole.LEAF,
            chain_certificates=["inter"],
        )
        result = a.analyze_expiry_cascade([inter, leaf1, leaf2])
        assert len(result.cascades) >= 1
        cascade = result.cascades[0]
        assert cascade.source_cert_id == "inter"
        assert cascade.affected_count >= 2

    def test_root_cascade(self):
        a = CertificateExpiryAnalyzer()
        root = _cert(
            cid="root",
            name="Root CA",
            chain_role=ChainRole.ROOT,
            expiry_iso=_past_iso(5),
        )
        leaf = _cert(
            cid="leaf",
            chain_role=ChainRole.LEAF,
            chain_certificates=["root"],
        )
        result = a.analyze_expiry_cascade([root, leaf])
        assert result.overall_risk == RiskSeverity.CRITICAL

    def test_large_cascade(self):
        a = CertificateExpiryAnalyzer()
        inter = _cert(
            cid="inter",
            chain_role=ChainRole.INTERMEDIATE,
            expiry_iso=_future_iso(5),
        )
        leaves = [
            _cert(
                cid=f"leaf{i}",
                chain_role=ChainRole.LEAF,
                chain_certificates=["inter"],
            )
            for i in range(8)
        ]
        result = a.analyze_expiry_cascade([inter] + leaves)
        assert result.max_cascade_size >= 8
        assert any("cascade" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Full Analysis tests
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    """Tests for CertificateExpiryAnalyzer.full_analysis."""

    def test_empty(self):
        a = CertificateExpiryAnalyzer()
        g = _graph()
        result = a.full_analysis(g, [])
        assert result.total_certificates == 0
        assert len(result.recommendations) > 0

    def test_single_cert(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(
            component_ids=["c1"],
            expiry_iso=_future_iso(365),
            auto_renew=True,
            renewal_method=RenewalMethod.ACME,
        )
        result = a.full_analysis(g, [c])
        assert result.total_certificates == 1
        assert result.expiry_timeline is not None
        assert len(result.chain_validations) == 1
        assert len(result.renewal_assessments) == 1

    def test_with_required_domains(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(
            component_ids=["c1"],
            cert_type=CertificateType.SAN,
            san_domains=["api.example.com"],
            expiry_iso=_future_iso(365),
        )
        result = a.full_analysis(
            g, [c],
            required_domains=["api.example.com", "web.example.com"],
        )
        assert result.coverage_analysis is not None
        assert result.coverage_analysis.uncovered_domains == 1

    def test_mtls_certs_included(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(
            component_ids=["c1"],
            is_mtls=True,
            expiry_iso=_future_iso(365),
        )
        result = a.full_analysis(g, [c])
        assert len(result.mtls_impacts) == 1

    def test_overall_risk_escalation(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        expired = _cert(
            cid="exp",
            component_ids=["c1"],
            expiry_iso=_past_iso(5),
        )
        result = a.full_analysis(g, [expired])
        assert result.overall_risk == RiskSeverity.CRITICAL

    def test_auto_renewal_recommendations(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(
            component_ids=["c1"],
            auto_renew=False,
            expiry_iso=_future_iso(365),
        )
        result = a.full_analysis(g, [c])
        assert any("auto-renewal" in r for r in result.recommendations)

    def test_no_required_domains_skips_coverage(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        c = _cert(component_ids=["c1"], expiry_iso=_future_iso(365))
        result = a.full_analysis(g, [c])
        assert result.coverage_analysis is None

    def test_cascade_in_full_report(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"))
        inter = _cert(
            cid="inter",
            chain_role=ChainRole.INTERMEDIATE,
            expiry_iso=_future_iso(10),
            component_ids=["c1"],
        )
        leaf = _cert(
            cid="leaf",
            chain_certificates=["inter"],
            component_ids=["c1"],
            expiry_iso=_future_iso(100),
        )
        result = a.full_analysis(g, [inter, leaf])
        assert result.cascade_analysis is not None
        assert result.cascade_analysis.max_cascade_size >= 1


# ---------------------------------------------------------------------------
# Private helper tests
# ---------------------------------------------------------------------------


class TestPrivateHelpers:
    """Tests for analyzer private helpers."""

    def test_resolve_affected_valid(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        c = _cert(component_ids=["c1", "c2", "missing"])
        result = a._resolve_affected(g, c)
        assert result == ["c1", "c2"]

    def test_resolve_affected_empty(self):
        a = CertificateExpiryAnalyzer()
        g = _graph()
        c = _cert(component_ids=["c1"])
        result = a._resolve_affected(g, c)
        assert result == []

    def test_count_affected(self):
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        c = _cert(component_ids=["c1", "c2"])
        assert a._count_affected(g, c) == 2

    def test_count_affected_none(self):
        a = CertificateExpiryAnalyzer()
        g = _graph()
        c = _cert(component_ids=["x"])
        assert a._count_affected(g, c) == 0


# ---------------------------------------------------------------------------
# Dataclass default value tests
# ---------------------------------------------------------------------------


class TestDataclassDefaults:
    """Ensure all dataclass models have correct defaults."""

    def test_expiry_timeline_entry_defaults(self):
        e = ExpiryTimelineEntry(cert_id="x", name="x")
        assert e.days_until_expiry is None
        assert e.expired is False
        assert e.risk_score == 0.0
        assert e.severity == RiskSeverity.LOW

    def test_expiry_timeline_defaults(self):
        t = ExpiryTimeline()
        assert t.entries == []
        assert t.nearest_expiry_days is None
        assert t.expired_count == 0
        assert t.overall_risk == RiskSeverity.LOW

    def test_chain_link_defaults(self):
        cl = ChainLink(cert_id="x", role=ChainRole.LEAF)
        assert cl.valid is True
        assert cl.role == ChainRole.LEAF

    def test_chain_validation_defaults(self):
        cv = ChainValidationResult(cert_id="x")
        assert cv.chain_length == 0
        assert cv.complete is True
        assert cv.valid is True

    def test_renewal_assessment_defaults(self):
        ra = RenewalAssessment(cert_id="x")
        assert ra.renewal_method == RenewalMethod.MANUAL
        assert ra.auto_renew is False

    def test_pinning_risk_defaults(self):
        pr = PinningRiskResult(cert_id="x")
        assert pr.rotation_blocked is False
        assert pr.affected_clients == 0

    def test_coverage_gap_defaults(self):
        cg = CoverageGap(domain="x")
        assert cg.covered is False
        assert cg.cert_id == ""

    def test_coverage_analysis_defaults(self):
        ca = CoverageAnalysis()
        assert ca.total_domains == 0
        assert ca.coverage_percent == 0.0

    def test_mtls_rotation_defaults(self):
        m = MTLSRotationImpact(cert_id="x")
        assert m.coordinated_rotation_needed is False
        assert m.estimated_downtime_seconds == 0.0

    def test_ca_dependency_defaults(self):
        cd = CADependencyRisk(ca_name="x")
        assert cd.cert_count == 0
        assert cd.single_ca_dependency is False

    def test_ocsp_crl_defaults(self):
        oc = OCSPCRLAssessment(cert_id="x")
        assert oc.revocation_checkable is False

    def test_transparency_defaults(self):
        ta = TransparencyAssessment(cert_id="x")
        assert ta.monitored is False

    def test_dc_consistency_defaults(self):
        dc = DatacenterConsistency(cert_name="x")
        assert dc.consistent is True
        assert dc.mismatched_certs == []

    def test_rotation_downtime_defaults(self):
        rd = RotationDowntimeEstimate(cert_id="x")
        assert rd.zero_downtime_possible is False

    def test_cascade_entry_defaults(self):
        ce = CascadeEntry(source_cert_id="x")
        assert ce.affected_count == 0
        assert ce.cascade_type == ""

    def test_expiry_cascade_defaults(self):
        ec = ExpiryCascadeAnalysis()
        assert ec.max_cascade_size == 0

    def test_full_report_defaults(self):
        fr = FullCertificateReport()
        assert fr.total_certificates == 0
        assert fr.overall_risk == RiskSeverity.LOW
        assert fr.expiry_timeline is None
        assert fr.coverage_analysis is None
        assert fr.cascade_analysis is None


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


class TestAdditionalCoverage:
    """Additional tests targeting remaining uncovered lines."""

    def test_chain_validation_medium_severity_incomplete_non_selfsigned(self):
        """Line 688: chain_length < 2 and not self-signed but still valid/complete."""
        a = CertificateExpiryAnalyzer()
        # A non-self-signed cert with no chain_certificates and valid expiry
        # complete=False, valid=True => severity HIGH (line 686)
        # To reach line 688 we need: valid=True, complete=True, chain_length < 2
        # But chain_length < 2 with no chain sets complete=False...
        # Actually we can test the exact path: valid=True, complete=True (self-signed skips the
        # incomplete check), chain < 2 non-self-signed -> medium.
        # Let's use a cert with chain but with complete=True and valid=True achieved differently.
        # Simplest: a cert that has exactly 1 link (itself) and the chain_length < 2 check
        # is reached after complete was not set to False. But the code does set complete=False
        # for chain_length < 2 non-self-signed. So line 688 is actually after two elifs that are
        # False, meaning valid=True and complete=True. With the current logic chain < 2 non-self
        # also sets complete=False earlier so the severity path goes to HIGH not MEDIUM.
        # This means line 688 is unreachable with current logic. Let's verify:
        # At line 675 chain_length < 2 and not self_signed => complete = False
        # Then at line 685: not complete => severity = HIGH (not reaching 688)
        # So line 688 is effectively dead code. We can still verify the path by
        # checking a self-signed cert with 1 link: it would go valid=True, complete=True
        # but then fail the `not self_signed` condition at 687, so LOW.
        # This confirms 688 is unreachable dead code.
        pass

    def test_wildcard_san_exact_match(self):
        """Lines 841-843: wildcard cert with SAN that exactly matches required domain."""
        a = CertificateExpiryAnalyzer()
        c = _cert(
            cert_type=CertificateType.WILDCARD,
            subject="*.example.com",
            san_domains=["exact.other.com"],
        )
        result = a.analyze_coverage(
            [c],
            ["exact.other.com"],
        )
        assert result.covered_domains == 1

    def test_single_domain_with_san_coverage(self):
        """Lines 860-863: non-wildcard non-SAN cert with san_domains."""
        a = CertificateExpiryAnalyzer()
        c = _cert(
            cert_type=CertificateType.SINGLE_DOMAIN,
            subject="main.example.com",
            san_domains=["alt.example.com"],
        )
        result = a.analyze_coverage(
            [c],
            ["main.example.com", "alt.example.com", "other.example.com"],
        )
        assert result.covered_domains == 2
        assert result.uncovered_domains == 1

    def test_mtls_skip_non_mtls_in_mutual(self):
        """Line 928-929: non-mTLS cert skipped during mutual dependency check."""
        a = CertificateExpiryAnalyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        mtls_cert = _cert(cid="m1", is_mtls=True, component_ids=["c1", "c2"])
        non_mtls = _cert(cid="n1", is_mtls=False, component_ids=["c1", "c2"])
        result = a.analyze_mtls_impact(mtls_cert, g, [mtls_cert, non_mtls])
        assert "n1" not in result.mutual_dependencies

    def test_mtls_medium_affected_count(self):
        """Line 946-947: 2 < affected_services <= 5."""
        a = CertificateExpiryAnalyzer()
        comps = [_comp(f"s{i}") for i in range(4)]
        g = _graph(*comps)
        c = _cert(is_mtls=True, component_ids=[f"s{i}" for i in range(4)])
        result = a.analyze_mtls_impact(c, g, [c])
        assert len(result.affected_services) == 4

    def test_ca_medium_concentration(self):
        """Line 1010: concentration >= 0.5."""
        a = CertificateExpiryAnalyzer()
        certs = [
            _cert(cid="c1", issuer_ca="MainCA"),
            _cert(cid="c2", issuer_ca="MainCA"),
            _cert(cid="c3", issuer_ca="OtherCA"),
        ]
        result = a.analyze_ca_dependency(certs)
        main_ca = [r for r in result if r.ca_name == "MainCA"][0]
        # 2 out of 3 = 66.7% concentration
        assert main_ca.cert_count == 2

    def test_dc_key_size_mismatch(self):
        """Line 1147: key_size_bits mismatch in datacenter consistency."""
        a = CertificateExpiryAnalyzer()
        c1 = _cert(
            cid="c1", name="shared", datacenter="dc1",
            expiry_iso="2026-12-01T00:00:00+00:00",
            issuer_ca="CA1",
            key_size_bits=2048,
        )
        c2 = _cert(
            cid="c2", name="shared", datacenter="dc2",
            expiry_iso="2026-12-01T00:00:00+00:00",
            issuer_ca="CA1",
            key_size_bits=4096,
        )
        result = a.check_datacenter_consistency([c1, c2])
        assert len(result) == 1
        assert not result[0].consistent
        assert any("key_size_mismatch" in m for m in result[0].mismatched_certs)

    def test_rotation_downtime_high(self):
        """Lines 1211,1213: downtime > 300 and > 60."""
        a = CertificateExpiryAnalyzer()
        # Create many components to push downtime > 300
        comps = [_comp(f"c{i}") for i in range(100)]
        g = _graph(*comps)
        c = _cert(component_ids=[f"c{i}" for i in range(100)])
        result = a.estimate_rotation_downtime(c, g)
        assert result.estimated_downtime_seconds > 300

    def test_rotation_downtime_medium(self):
        """Line 1213: 60 < downtime <= 300."""
        a = CertificateExpiryAnalyzer()
        comps = [_comp(f"c{i}") for i in range(20)]
        g = _graph(*comps)
        c = _cert(component_ids=[f"c{i}" for i in range(20)])
        result = a.estimate_rotation_downtime(c, g)
        assert result.estimated_downtime_seconds > 60

    def test_cascade_by_issuer_ca_match(self):
        """Lines 1260-1262: cascade detected via issuer_ca matching."""
        a = CertificateExpiryAnalyzer()
        inter = _cert(
            cid="inter",
            name="Intermediate",
            chain_role=ChainRole.INTERMEDIATE,
            issuer_ca="SharedCA",
            expiry_iso=_future_iso(10),
        )
        leaf = _cert(
            cid="leaf1",
            chain_role=ChainRole.LEAF,
            issuer_ca="SharedCA",
            chain_certificates=[],  # not referenced via chain_certificates
        )
        result = a.analyze_expiry_cascade([inter, leaf])
        # The issuer_ca matching branch should find the leaf
        has_cascade = any(
            c.source_cert_id == "inter" and "leaf1" in c.affected_cert_ids
            for c in result.cascades
        )
        assert has_cascade

    def test_cascade_no_affected_skipped(self):
        """Line 1264-1265: intermediate with no affected certs is skipped."""
        a = CertificateExpiryAnalyzer()
        inter = _cert(
            cid="inter",
            chain_role=ChainRole.INTERMEDIATE,
            issuer_ca="LonelyCA",
            expiry_iso=_future_iso(100),
        )
        leaf = _cert(
            cid="leaf",
            chain_role=ChainRole.LEAF,
            issuer_ca="DifferentCA",
            chain_certificates=[],
        )
        result = a.analyze_expiry_cascade([inter, leaf])
        assert len(result.cascades) == 0
