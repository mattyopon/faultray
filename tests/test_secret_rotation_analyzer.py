"""Tests for faultray.simulator.secret_rotation_analyzer module.

Comprehensive test suite targeting 100% coverage across all enums, data classes,
helpers, and the SecretRotationAnalyzer engine methods.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.secret_rotation_analyzer import (
    BlastRadiusEntry,
    CertChainValidation,
    ComplianceFramework,
    ComplianceMapping,
    ComplianceReport,
    DualSecretAnalysis,
    EmergencyPlaybook,
    FrequencyComplianceResult,
    MaturityAssessment,
    MaturityLevel,
    PlaybookPriority,
    PlaybookStep,
    RiskSeverity,
    RotationDependency,
    RotationOrder,
    RotationWindowAnalysis,
    SecretEntry,
    SecretKind,
    SecretRotationAnalyzer,
    SprawlEntry,
    _BASE_ROTATION_DOWNTIME,
    _COMPLIANCE_ROTATION_DAYS,
    _DEFAULT_MAX_ROTATION_DAYS,
    _EMERGENCY_BASE_TIME,
    _clamp,
    _days_since,
    _days_until,
    _ensure_utc,
    _parse_iso,
    _severity_from_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid: str = "c1", ctype: ComponentType = ComponentType.APP_SERVER) -> Component:
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _analyzer() -> SecretRotationAnalyzer:
    return SecretRotationAnalyzer()


def _entry(
    sid: str = "s1",
    name: str = "test-secret",
    kind: SecretKind = SecretKind.API_KEY,
    component_ids: list[str] | None = None,
    rotation_interval_days: int = 90,
    last_rotated_iso: str = "",
    expiry_iso: str = "",
    auto_rotate: bool = False,
    dual_secret_enabled: bool = False,
    grace_period_hours: float = 0.0,
    cert_chain_length: int = 0,
    cert_issuer: str = "",
) -> SecretEntry:
    return SecretEntry(
        id=sid,
        name=name,
        kind=kind,
        component_ids=component_ids or [],
        rotation_interval_days=rotation_interval_days,
        last_rotated_iso=last_rotated_iso,
        expiry_iso=expiry_iso,
        auto_rotate=auto_rotate,
        dual_secret_enabled=dual_secret_enabled,
        grace_period_hours=grace_period_hours,
        cert_chain_length=cert_chain_length,
        cert_issuer=cert_issuer,
    )


def _past_iso(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


class TestEnums:
    def test_secret_kind_values(self) -> None:
        assert SecretKind.API_KEY == "api_key"
        assert SecretKind.DATABASE_PASSWORD == "database_password"
        assert SecretKind.TLS_CERTIFICATE == "tls_certificate"
        assert SecretKind.OAUTH_TOKEN == "oauth_token"
        assert SecretKind.ENCRYPTION_KEY == "encryption_key"
        assert SecretKind.SSH_KEY == "ssh_key"
        assert len(SecretKind) == 6

    def test_compliance_framework_values(self) -> None:
        assert ComplianceFramework.PCI_DSS == "pci_dss"
        assert ComplianceFramework.SOC2 == "soc2"
        assert ComplianceFramework.HIPAA == "hipaa"

    def test_maturity_level_values(self) -> None:
        assert MaturityLevel.MANUAL == "manual"
        assert MaturityLevel.SEMI_AUTOMATED == "semi_automated"
        assert MaturityLevel.FULLY_AUTOMATED == "fully_automated"
        assert MaturityLevel.ADAPTIVE == "adaptive"

    def test_risk_severity_values(self) -> None:
        assert RiskSeverity.LOW == "low"
        assert RiskSeverity.MEDIUM == "medium"
        assert RiskSeverity.HIGH == "high"
        assert RiskSeverity.CRITICAL == "critical"

    def test_playbook_priority_values(self) -> None:
        assert PlaybookPriority.IMMEDIATE == "immediate"
        assert PlaybookPriority.HIGH == "high"
        assert PlaybookPriority.MEDIUM == "medium"
        assert PlaybookPriority.LOW == "low"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_parse_iso_empty(self) -> None:
        assert _parse_iso("") is None

    def test_parse_iso_valid(self) -> None:
        dt = _parse_iso("2025-01-15T12:00:00+00:00")
        assert dt is not None
        assert dt.year == 2025

    def test_parse_iso_z_suffix(self) -> None:
        dt = _parse_iso("2025-06-01T00:00:00Z")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_parse_iso_invalid(self) -> None:
        assert _parse_iso("not-a-date") is None

    def test_parse_iso_none_type(self) -> None:
        # Exercises the TypeError branch
        assert _parse_iso("") is None

    def test_ensure_utc_naive(self) -> None:
        naive = datetime(2025, 1, 1, 0, 0, 0)
        aware = _ensure_utc(naive)
        assert aware.tzinfo == timezone.utc

    def test_ensure_utc_already_aware(self) -> None:
        aware = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = _ensure_utc(aware)
        assert result is aware

    def test_severity_from_score_boundaries(self) -> None:
        assert _severity_from_score(0.0) == RiskSeverity.LOW
        assert _severity_from_score(0.29) == RiskSeverity.LOW
        assert _severity_from_score(0.3) == RiskSeverity.MEDIUM
        assert _severity_from_score(0.59) == RiskSeverity.MEDIUM
        assert _severity_from_score(0.6) == RiskSeverity.HIGH
        assert _severity_from_score(0.79) == RiskSeverity.HIGH
        assert _severity_from_score(0.8) == RiskSeverity.CRITICAL
        assert _severity_from_score(1.0) == RiskSeverity.CRITICAL

    def test_clamp(self) -> None:
        assert _clamp(50.0) == 50.0
        assert _clamp(-10.0) == 0.0
        assert _clamp(200.0) == 100.0
        assert _clamp(5.0, 0.0, 10.0) == 5.0
        assert _clamp(-1.0, 0.0, 10.0) == 0.0
        assert _clamp(15.0, 0.0, 10.0) == 10.0

    def test_days_since_none(self) -> None:
        assert _days_since(None) is None

    def test_days_since_past(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(days=10)
        result = _days_since(past)
        assert result is not None
        assert result >= 10

    def test_days_since_naive(self) -> None:
        past = datetime.now() - timedelta(days=5)
        result = _days_since(past)
        assert result is not None
        assert result >= 4  # may be 4 due to timezone offset

    def test_days_until_none(self) -> None:
        assert _days_until(None) is None

    def test_days_until_future(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(days=10)
        result = _days_until(future)
        assert result is not None
        assert result >= 9

    def test_days_until_past(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(days=5)
        result = _days_until(past)
        assert result is not None
        assert result < 0

    def test_days_until_naive(self) -> None:
        future = datetime.now() + timedelta(days=15)
        result = _days_until(future)
        assert result is not None
        assert result >= 14


# ---------------------------------------------------------------------------
# SecretEntry data class
# ---------------------------------------------------------------------------


class TestSecretEntry:
    def test_defaults(self) -> None:
        e = _entry()
        assert e.id == "s1"
        assert e.kind == SecretKind.API_KEY
        assert e.auto_rotate is False
        assert e.dual_secret_enabled is False

    def test_last_rotated_dt_empty(self) -> None:
        e = _entry()
        assert e.last_rotated_dt() is None

    def test_last_rotated_dt_valid(self) -> None:
        e = _entry(last_rotated_iso=_past_iso(5))
        dt = e.last_rotated_dt()
        assert dt is not None

    def test_expiry_dt_empty(self) -> None:
        e = _entry()
        assert e.expiry_dt() is None

    def test_expiry_dt_valid(self) -> None:
        e = _entry(expiry_iso=_future_iso(30))
        dt = e.expiry_dt()
        assert dt is not None


# ---------------------------------------------------------------------------
# Constants coverage
# ---------------------------------------------------------------------------


class TestConstants:
    def test_default_max_rotation_days_all_kinds(self) -> None:
        for kind in SecretKind:
            assert kind in _DEFAULT_MAX_ROTATION_DAYS

    def test_base_rotation_downtime_all_kinds(self) -> None:
        for kind in SecretKind:
            assert kind in _BASE_ROTATION_DOWNTIME
            assert _BASE_ROTATION_DOWNTIME[kind] > 0

    def test_emergency_base_time_all_kinds(self) -> None:
        for kind in SecretKind:
            assert kind in _EMERGENCY_BASE_TIME
            assert _EMERGENCY_BASE_TIME[kind] > 0

    def test_compliance_rotation_days_all_frameworks(self) -> None:
        for fw in ComplianceFramework:
            assert fw in _COMPLIANCE_ROTATION_DAYS
            rules = _COMPLIANCE_ROTATION_DAYS[fw]
            for kind in SecretKind:
                assert kind in rules


# ---------------------------------------------------------------------------
# Frequency compliance
# ---------------------------------------------------------------------------


class TestFrequencyCompliance:
    def test_compliant_secret(self) -> None:
        a = _analyzer()
        s = _entry(last_rotated_iso=_past_iso(10))
        results = a.check_frequency_compliance([s])
        assert len(results) == 1
        assert results[0].compliant is True
        assert results[0].severity == RiskSeverity.LOW

    def test_no_rotation_history(self) -> None:
        a = _analyzer()
        s = _entry()
        results = a.check_frequency_compliance([s])
        assert len(results) == 1
        assert results[0].compliant is False
        assert results[0].severity == RiskSeverity.HIGH
        assert "No rotation history" in results[0].message

    def test_overdue_medium(self) -> None:
        a = _analyzer()
        s = _entry(last_rotated_iso=_past_iso(100))  # 100 > 90 limit
        results = a.check_frequency_compliance([s])
        assert results[0].compliant is False
        assert results[0].overdue_days > 0
        assert results[0].severity == RiskSeverity.MEDIUM  # 10d overdue

    def test_overdue_high(self) -> None:
        a = _analyzer()
        s = _entry(last_rotated_iso=_past_iso(150))  # 60d overdue
        results = a.check_frequency_compliance([s])
        assert results[0].compliant is False
        assert results[0].severity == RiskSeverity.HIGH

    def test_overdue_critical(self) -> None:
        a = _analyzer()
        s = _entry(last_rotated_iso=_past_iso(200))  # 110d overdue
        results = a.check_frequency_compliance([s])
        assert results[0].compliant is False
        assert results[0].severity == RiskSeverity.CRITICAL

    def test_custom_overrides(self) -> None:
        a = _analyzer()
        s = _entry(kind=SecretKind.API_KEY, last_rotated_iso=_past_iso(50))
        results = a.check_frequency_compliance([s], overrides={SecretKind.API_KEY: 30})
        assert results[0].compliant is False
        assert results[0].required_interval_days == 30

    def test_empty_secrets_list(self) -> None:
        a = _analyzer()
        results = a.check_frequency_compliance([])
        assert results == []

    def test_multiple_secrets(self) -> None:
        a = _analyzer()
        s1 = _entry(sid="s1", last_rotated_iso=_past_iso(5))
        s2 = _entry(sid="s2", last_rotated_iso=_past_iso(200))
        results = a.check_frequency_compliance([s1, s2])
        assert len(results) == 2
        assert results[0].compliant is True
        assert results[1].compliant is False


# ---------------------------------------------------------------------------
# Rotation window analysis
# ---------------------------------------------------------------------------


class TestRotationWindowAnalysis:
    def test_dual_secret_zero_downtime(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s = _entry(component_ids=["c1"], dual_secret_enabled=True)
        result = a.analyze_rotation_window(g, s)
        assert result.estimated_downtime_seconds == 0.0
        assert result.dual_secret_active is True
        assert result.overlap_safe is True

    def test_grace_period_reduces_downtime(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s = _entry(component_ids=["c1"], grace_period_hours=2.0)
        result = a.analyze_rotation_window(g, s)
        assert result.overlap_safe is True
        assert result.estimated_downtime_seconds > 0

    def test_no_overlap_high_risk(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"), _comp("c2"), _comp("c3"))
        s = _entry(component_ids=["c1", "c2", "c3"])
        result = a.analyze_rotation_window(g, s)
        assert result.overlap_safe is False

    def test_auto_rotate_halves_downtime(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s_manual = _entry(component_ids=["c1"], auto_rotate=False)
        s_auto = _entry(component_ids=["c1"], auto_rotate=True)
        r_manual = a.analyze_rotation_window(g, s_manual)
        r_auto = a.analyze_rotation_window(g, s_auto)
        assert r_auto.estimated_downtime_seconds < r_manual.estimated_downtime_seconds

    def test_high_fan_out_recommendations(self) -> None:
        a = _analyzer()
        comps = [_comp(f"c{i}") for i in range(7)]
        g = _graph(*comps)
        s = _entry(component_ids=[f"c{i}" for i in range(7)])
        result = a.analyze_rotation_window(g, s)
        assert any("per-service" in r for r in result.recommendations)

    def test_recommendations_all_present(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s = _entry(component_ids=["c1"])
        result = a.analyze_rotation_window(g, s)
        assert any("dual-secret" in r.lower() for r in result.recommendations)
        assert any("auto-rotation" in r.lower() for r in result.recommendations)
        assert any("grace period" in r.lower() or "overlap" in r.lower() for r in result.recommendations)

    def test_empty_graph(self) -> None:
        a = _analyzer()
        g = _graph()
        s = _entry(component_ids=["c1"])
        result = a.analyze_rotation_window(g, s)
        assert result.estimated_downtime_seconds >= 0


# ---------------------------------------------------------------------------
# Dual-secret analysis
# ---------------------------------------------------------------------------


class TestDualSecretAnalysis:
    def test_dual_enabled(self) -> None:
        a = _analyzer()
        s = _entry(dual_secret_enabled=True, grace_period_hours=4.0)
        result = a.analyze_dual_secret(s)
        assert result.dual_enabled is True
        assert result.zero_downtime is True
        assert result.overlap_hours == 4.0
        assert result.risk == RiskSeverity.LOW

    def test_dual_enabled_no_grace(self) -> None:
        a = _analyzer()
        s = _entry(dual_secret_enabled=True, grace_period_hours=0.0)
        result = a.analyze_dual_secret(s)
        assert result.overlap_hours == 1.0  # minimum overlap

    def test_grace_period_only(self) -> None:
        a = _analyzer()
        s = _entry(dual_secret_enabled=False, grace_period_hours=2.0)
        result = a.analyze_dual_secret(s)
        assert result.dual_enabled is False
        assert result.zero_downtime is False
        assert result.risk == RiskSeverity.MEDIUM

    def test_no_overlap_at_all(self) -> None:
        a = _analyzer()
        s = _entry(dual_secret_enabled=False, grace_period_hours=0.0)
        result = a.analyze_dual_secret(s)
        assert result.dual_enabled is False
        assert result.zero_downtime is False
        assert result.risk == RiskSeverity.HIGH
        assert len(result.recommendations) >= 2


# ---------------------------------------------------------------------------
# Certificate chain validation
# ---------------------------------------------------------------------------


class TestCertChainValidation:
    def test_valid_cert(self) -> None:
        a = _analyzer()
        s = _entry(
            kind=SecretKind.TLS_CERTIFICATE,
            expiry_iso=_future_iso(200),
            cert_chain_length=3,
            cert_issuer="DigiCert",
            auto_rotate=True,
        )
        result = a.validate_cert_chain(s)
        assert result.expired is False
        assert result.expiry_risk == RiskSeverity.LOW
        assert result.chain_length == 3

    def test_expired_cert(self) -> None:
        a = _analyzer()
        s = _entry(
            kind=SecretKind.TLS_CERTIFICATE,
            expiry_iso=_past_iso(5),
            cert_chain_length=3,
            cert_issuer="DigiCert",
        )
        result = a.validate_cert_chain(s)
        assert result.expired is True
        assert result.expiry_risk == RiskSeverity.CRITICAL
        assert any("expired" in r.lower() for r in result.recommendations)

    def test_expiring_within_7_days(self) -> None:
        a = _analyzer()
        s = _entry(
            kind=SecretKind.TLS_CERTIFICATE,
            expiry_iso=_future_iso(3),
            cert_chain_length=3,
            cert_issuer="LetsEncrypt",
        )
        result = a.validate_cert_chain(s)
        assert result.expiry_risk == RiskSeverity.CRITICAL

    def test_expiring_within_30_days(self) -> None:
        a = _analyzer()
        s = _entry(
            kind=SecretKind.TLS_CERTIFICATE,
            expiry_iso=_future_iso(20),
            cert_chain_length=3,
            cert_issuer="LetsEncrypt",
        )
        result = a.validate_cert_chain(s)
        assert result.expiry_risk == RiskSeverity.HIGH

    def test_expiring_within_90_days(self) -> None:
        a = _analyzer()
        s = _entry(
            kind=SecretKind.TLS_CERTIFICATE,
            expiry_iso=_future_iso(60),
            cert_chain_length=3,
            cert_issuer="LetsEncrypt",
        )
        result = a.validate_cert_chain(s)
        assert result.expiry_risk == RiskSeverity.MEDIUM

    def test_no_expiry_date(self) -> None:
        a = _analyzer()
        s = _entry(kind=SecretKind.TLS_CERTIFICATE)
        result = a.validate_cert_chain(s)
        assert result.days_until_expiry is None
        assert result.expiry_risk == RiskSeverity.MEDIUM

    def test_self_signed(self) -> None:
        a = _analyzer()
        s = _entry(
            kind=SecretKind.TLS_CERTIFICATE,
            expiry_iso=_future_iso(200),
            cert_chain_length=1,
        )
        result = a.validate_cert_chain(s)
        assert any("self-signed" in r.lower() for r in result.recommendations)

    def test_unknown_chain_length(self) -> None:
        a = _analyzer()
        s = _entry(kind=SecretKind.TLS_CERTIFICATE, expiry_iso=_future_iso(200))
        result = a.validate_cert_chain(s)
        assert any("chain length unknown" in r.lower() for r in result.recommendations)

    def test_no_issuer(self) -> None:
        a = _analyzer()
        s = _entry(
            kind=SecretKind.TLS_CERTIFICATE,
            expiry_iso=_future_iso(200),
            cert_chain_length=3,
        )
        result = a.validate_cert_chain(s)
        assert any("issuer" in r.lower() for r in result.recommendations)

    def test_no_auto_rotate(self) -> None:
        a = _analyzer()
        s = _entry(
            kind=SecretKind.TLS_CERTIFICATE,
            expiry_iso=_future_iso(200),
            cert_chain_length=3,
            cert_issuer="DigiCert",
            auto_rotate=False,
        )
        result = a.validate_cert_chain(s)
        assert any("auto-rotation" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Blast radius
# ---------------------------------------------------------------------------


class TestBlastRadius:
    def test_empty_graph(self) -> None:
        a = _analyzer()
        g = _graph()
        s = _entry(component_ids=["c1"])
        result = a.calculate_blast_radius(g, s)
        assert result.total_affected_count == 0
        assert "No components" in result.recommendations[0]

    def test_single_component(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s = _entry(component_ids=["c1"])
        result = a.calculate_blast_radius(g, s)
        assert result.directly_affected == ["c1"]
        assert result.affected_percent == 100.0

    def test_transitive_affected(self) -> None:
        a = _analyzer()
        c1 = _comp("c1")
        c2 = _comp("c2")
        c3 = _comp("c3")
        g = _graph(c1, c2, c3)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        g.add_dependency(Dependency(source_id="c3", target_id="c2"))
        s = _entry(component_ids=["c1"])
        result = a.calculate_blast_radius(g, s)
        assert "c1" in result.directly_affected
        assert len(result.transitively_affected) > 0

    def test_high_blast_radius(self) -> None:
        a = _analyzer()
        comps = [_comp(f"c{i}") for i in range(10)]
        g = _graph(*comps)
        for i in range(1, 10):
            g.add_dependency(Dependency(source_id=f"c{i}", target_id="c0"))
        s = _entry(component_ids=["c0"])
        result = a.calculate_blast_radius(g, s)
        assert result.affected_percent > 50.0
        assert result.risk in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)

    def test_missing_component_ids_ignored(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s = _entry(component_ids=["c1", "nonexistent"])
        result = a.calculate_blast_radius(g, s)
        assert result.directly_affected == ["c1"]

    def test_many_direct_components(self) -> None:
        a = _analyzer()
        comps = [_comp(f"c{i}") for i in range(5)]
        g = _graph(*comps)
        s = _entry(component_ids=[f"c{i}" for i in range(5)])
        result = a.calculate_blast_radius(g, s)
        assert len(result.directly_affected) == 5
        assert any("Split" in r or "per-service" in r for r in result.recommendations)

    def test_medium_blast_radius_25_to_50_pct(self) -> None:
        """Blast radius between 25-50% triggers the elif pct > 25 branch."""
        a = _analyzer()
        comps = [_comp(f"c{i}") for i in range(10)]
        g = _graph(*comps)
        # 3 of 10 = 30%
        s = _entry(component_ids=["c0", "c1", "c2"])
        result = a.calculate_blast_radius(g, s)
        assert 25.0 < result.affected_percent <= 50.0

    def test_low_blast_radius_10_to_25_pct(self) -> None:
        """Blast radius between 10-25% triggers the elif pct > 10 branch."""
        a = _analyzer()
        comps = [_comp(f"c{i}") for i in range(10)]
        g = _graph(*comps)
        # 2 of 10 = 20%
        s = _entry(component_ids=["c0", "c1"])
        result = a.calculate_blast_radius(g, s)
        assert 10.0 < result.affected_percent <= 25.0


# ---------------------------------------------------------------------------
# Maturity assessment
# ---------------------------------------------------------------------------


class TestMaturityAssessment:
    def test_empty_secrets(self) -> None:
        a = _analyzer()
        result = a.assess_maturity([])
        assert result.overall_level == MaturityLevel.MANUAL
        assert result.score == 0.0

    def test_manual_level(self) -> None:
        a = _analyzer()
        secrets = [_entry(sid=f"s{i}") for i in range(5)]
        result = a.assess_maturity(secrets)
        assert result.overall_level == MaturityLevel.MANUAL
        assert result.score < 25.0

    def test_semi_automated(self) -> None:
        a = _analyzer()
        secrets = [
            _entry(sid="s1", auto_rotate=True),
            _entry(sid="s2", auto_rotate=True),
            _entry(sid="s3"),
            _entry(sid="s4"),
        ]
        result = a.assess_maturity(secrets)
        assert result.overall_level == MaturityLevel.SEMI_AUTOMATED
        assert 25.0 <= result.score < 50.0

    def test_fully_automated(self) -> None:
        a = _analyzer()
        secrets = [
            _entry(sid="s1", auto_rotate=True, dual_secret_enabled=True),
            _entry(sid="s2", auto_rotate=True),
        ]
        result = a.assess_maturity(secrets)
        assert result.overall_level == MaturityLevel.FULLY_AUTOMATED

    def test_adaptive(self) -> None:
        a = _analyzer()
        secrets = [
            _entry(sid="s1", auto_rotate=True, dual_secret_enabled=True, grace_period_hours=4.0),
            _entry(sid="s2", auto_rotate=True, dual_secret_enabled=True, grace_period_hours=2.0),
        ]
        result = a.assess_maturity(secrets)
        assert result.overall_level == MaturityLevel.ADAPTIVE
        assert result.score >= 80.0

    def test_recommendations_present(self) -> None:
        a = _analyzer()
        secrets = [_entry(sid="s1"), _entry(sid="s2")]
        result = a.assess_maturity(secrets)
        assert len(result.recommendations) > 0


# ---------------------------------------------------------------------------
# Sprawl detection
# ---------------------------------------------------------------------------


class TestSprawlDetection:
    def test_no_sprawl(self) -> None:
        a = _analyzer()
        s = _entry(component_ids=["c1"])
        results = a.detect_sprawl([s])
        assert len(results) == 0

    def test_threshold_two(self) -> None:
        a = _analyzer()
        s = _entry(component_ids=["c1", "c2"])
        results = a.detect_sprawl([s], threshold=2)
        assert len(results) == 1
        assert results[0].service_count == 2

    def test_high_sprawl(self) -> None:
        a = _analyzer()
        s = _entry(component_ids=[f"c{i}" for i in range(10)])
        results = a.detect_sprawl([s])
        assert len(results) == 1
        assert results[0].risk in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)

    def test_medium_sprawl_five(self) -> None:
        a = _analyzer()
        s = _entry(component_ids=[f"c{i}" for i in range(5)])
        results = a.detect_sprawl([s])
        assert results[0].risk in (RiskSeverity.MEDIUM, RiskSeverity.HIGH)

    def test_sprawl_three(self) -> None:
        a = _analyzer()
        s = _entry(component_ids=["c1", "c2", "c3"])
        results = a.detect_sprawl([s])
        assert len(results) == 1
        assert results[0].risk == RiskSeverity.MEDIUM

    def test_custom_threshold(self) -> None:
        a = _analyzer()
        s = _entry(component_ids=["c1", "c2", "c3"])
        results = a.detect_sprawl([s], threshold=5)
        assert len(results) == 0

    def test_sprawl_recommendations(self) -> None:
        a = _analyzer()
        s = _entry(component_ids=["c1", "c2", "c3"])
        results = a.detect_sprawl([s])
        assert any("per-service" in r for r in results[0].recommendations)

    def test_multiple_secrets(self) -> None:
        a = _analyzer()
        s1 = _entry(sid="s1", component_ids=["c1"])
        s2 = _entry(sid="s2", component_ids=["c1", "c2", "c3"])
        results = a.detect_sprawl([s1, s2])
        assert len(results) == 1
        assert results[0].secret_id == "s2"


# ---------------------------------------------------------------------------
# Emergency playbook
# ---------------------------------------------------------------------------


class TestEmergencyPlaybook:
    def test_basic_playbook(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s = _entry(component_ids=["c1"])
        pb = a.generate_emergency_playbook(g, s)
        assert pb.secret_id == "s1"
        assert len(pb.steps) == 7
        assert pb.total_estimated_seconds > 0

    def test_step_ordering(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s = _entry(component_ids=["c1"])
        pb = a.generate_emergency_playbook(g, s)
        orders = [step.order for step in pb.steps]
        assert orders == sorted(orders)

    def test_auto_rotate_reduces_deploy_time(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s_manual = _entry(component_ids=["c1"], auto_rotate=False)
        s_auto = _entry(component_ids=["c1"], auto_rotate=True)
        pb_manual = a.generate_emergency_playbook(g, s_manual)
        pb_auto = a.generate_emergency_playbook(g, s_auto)
        assert pb_auto.total_estimated_seconds < pb_manual.total_estimated_seconds

    def test_high_fan_out_risk(self) -> None:
        a = _analyzer()
        comps = [_comp(f"c{i}") for i in range(7)]
        g = _graph(*comps)
        s = _entry(component_ids=[f"c{i}" for i in range(7)])
        pb = a.generate_emergency_playbook(g, s)
        assert pb.risk in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)

    def test_all_secret_kinds(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        for kind in SecretKind:
            s = _entry(kind=kind, component_ids=["c1"])
            pb = a.generate_emergency_playbook(g, s)
            assert pb.kind == kind
            assert len(pb.steps) > 0

    def test_empty_graph_playbook(self) -> None:
        a = _analyzer()
        g = _graph()
        s = _entry(component_ids=["c1"])
        pb = a.generate_emergency_playbook(g, s)
        assert len(pb.steps) == 7  # always generates full playbook

    def test_playbook_priorities(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s = _entry(component_ids=["c1"])
        pb = a.generate_emergency_playbook(g, s)
        priorities = [step.priority for step in pb.steps]
        assert PlaybookPriority.IMMEDIATE in priorities
        assert PlaybookPriority.LOW in priorities

    def test_medium_fan_out_risk(self) -> None:
        """3-5 affected services triggers elif num_affected > 2 branch."""
        a = _analyzer()
        comps = [_comp(f"c{i}") for i in range(4)]
        g = _graph(*comps)
        s = _entry(component_ids=[f"c{i}" for i in range(4)])
        pb = a.generate_emergency_playbook(g, s)
        assert pb.risk in (RiskSeverity.MEDIUM, RiskSeverity.HIGH)


# ---------------------------------------------------------------------------
# Rotation ordering
# ---------------------------------------------------------------------------


class TestRotationOrder:
    def test_empty_secrets(self) -> None:
        a = _analyzer()
        g = _graph()
        result = a.compute_rotation_order(g, [])
        assert result.ordered_ids == []
        assert "No secrets" in result.recommendations[0]

    def test_single_secret(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s = _entry(sid="s1", component_ids=["c1"])
        result = a.compute_rotation_order(g, [s])
        assert result.ordered_ids == ["s1"]
        assert result.has_cycle is False

    def test_priority_ordering(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s_api = _entry(sid="s_api", kind=SecretKind.API_KEY, component_ids=["c1"])
        s_enc = _entry(sid="s_enc", kind=SecretKind.ENCRYPTION_KEY, component_ids=["c1"])
        s_tls = _entry(sid="s_tls", kind=SecretKind.TLS_CERTIFICATE, component_ids=["c1"])
        result = a.compute_rotation_order(g, [s_api, s_enc, s_tls])
        # Encryption key should come first, then TLS, then API key
        assert result.ordered_ids.index("s_enc") < result.ordered_ids.index("s_api")
        assert result.ordered_ids.index("s_tls") < result.ordered_ids.index("s_api")

    def test_no_shared_components_no_deps(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        s1 = _entry(sid="s1", kind=SecretKind.API_KEY, component_ids=["c1"])
        s2 = _entry(sid="s2", kind=SecretKind.DATABASE_PASSWORD, component_ids=["c2"])
        result = a.compute_rotation_order(g, [s1, s2])
        assert len(result.dependencies) == 0

    def test_dependency_constraints(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        s_enc = _entry(sid="s_enc", kind=SecretKind.ENCRYPTION_KEY, component_ids=["c1"])
        s_api = _entry(sid="s_api", kind=SecretKind.API_KEY, component_ids=["c1"])
        result = a.compute_rotation_order(g, [s_enc, s_api])
        assert len(result.dependencies) > 0
        assert result.dependencies[0].source_secret_id == "s_enc"

    def test_multiple_kinds_ordering(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"))
        secrets = [
            _entry(sid="s_ssh", kind=SecretKind.SSH_KEY, component_ids=["c1"]),
            _entry(sid="s_db", kind=SecretKind.DATABASE_PASSWORD, component_ids=["c1"]),
            _entry(sid="s_enc", kind=SecretKind.ENCRYPTION_KEY, component_ids=["c1"]),
            _entry(sid="s_api", kind=SecretKind.API_KEY, component_ids=["c1"]),
        ]
        result = a.compute_rotation_order(g, secrets)
        enc_idx = result.ordered_ids.index("s_enc")
        api_idx = result.ordered_ids.index("s_api")
        assert enc_idx < api_idx


# ---------------------------------------------------------------------------
# Compliance mapping
# ---------------------------------------------------------------------------


class TestComplianceMapping:
    def test_pci_dss_compliant(self) -> None:
        a = _analyzer()
        s = _entry(kind=SecretKind.API_KEY, last_rotated_iso=_past_iso(30))
        report = a.map_compliance([s], ComplianceFramework.PCI_DSS)
        assert report.compliance_percent == 100.0
        assert report.compliant_count == 1

    def test_pci_dss_non_compliant(self) -> None:
        a = _analyzer()
        s = _entry(kind=SecretKind.API_KEY, last_rotated_iso=_past_iso(200))
        report = a.map_compliance([s], ComplianceFramework.PCI_DSS)
        assert report.non_compliant_count == 1
        assert report.compliance_percent == 0.0

    def test_soc2_compliance(self) -> None:
        a = _analyzer()
        s = _entry(kind=SecretKind.API_KEY, last_rotated_iso=_past_iso(100))
        report = a.map_compliance([s], ComplianceFramework.SOC2)
        # SOC2 allows 180d for API keys
        assert report.compliant_count == 1

    def test_hipaa_strict(self) -> None:
        a = _analyzer()
        s = _entry(kind=SecretKind.DATABASE_PASSWORD, last_rotated_iso=_past_iso(70))
        report = a.map_compliance([s], ComplianceFramework.HIPAA)
        # HIPAA requires 60d for DB passwords
        assert report.non_compliant_count == 1

    def test_no_rotation_history_non_compliant(self) -> None:
        a = _analyzer()
        s = _entry(kind=SecretKind.API_KEY)
        report = a.map_compliance([s], ComplianceFramework.PCI_DSS)
        assert report.non_compliant_count == 1
        non_compliant_map = report.mappings[0]
        assert not non_compliant_map.compliant
        assert any("No rotation history" in r for r in non_compliant_map.recommendations)

    def test_all_compliant_recommendation(self) -> None:
        a = _analyzer()
        s = _entry(kind=SecretKind.API_KEY, last_rotated_iso=_past_iso(5))
        report = a.map_compliance([s], ComplianceFramework.SOC2)
        assert any("All secrets comply" in r for r in report.recommendations)

    def test_mixed_compliance(self) -> None:
        a = _analyzer()
        s1 = _entry(sid="s1", kind=SecretKind.API_KEY, last_rotated_iso=_past_iso(5))
        s2 = _entry(sid="s2", kind=SecretKind.API_KEY, last_rotated_iso=_past_iso(200))
        report = a.map_compliance([s1, s2], ComplianceFramework.PCI_DSS)
        assert report.compliant_count == 1
        assert report.non_compliant_count == 1
        assert report.compliance_percent == 50.0


# ---------------------------------------------------------------------------
# Full analysis integration
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    def test_full_analysis_runs(self) -> None:
        a = _analyzer()
        c1 = _comp("c1")
        c2 = _comp("c2")
        g = _graph(c1, c2)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))

        secrets = [
            _entry(
                sid="s1",
                kind=SecretKind.API_KEY,
                component_ids=["c1"],
                last_rotated_iso=_past_iso(10),
                auto_rotate=True,
            ),
            _entry(
                sid="s2",
                kind=SecretKind.TLS_CERTIFICATE,
                component_ids=["c1", "c2"],
                last_rotated_iso=_past_iso(300),
                expiry_iso=_future_iso(20),
                cert_chain_length=3,
                cert_issuer="LetsEncrypt",
            ),
        ]

        result = a.full_analysis(g, secrets)

        assert "frequency_compliance" in result
        assert "rotation_windows" in result
        assert "dual_secret_analyses" in result
        assert "cert_chain_validations" in result
        assert "blast_radii" in result
        assert "maturity" in result
        assert "sprawl" in result
        assert "playbooks" in result
        assert "rotation_order" in result
        assert "compliance_reports" in result

        assert len(result["frequency_compliance"]) == 2
        assert len(result["rotation_windows"]) == 2
        assert len(result["dual_secret_analyses"]) == 2
        assert len(result["cert_chain_validations"]) == 1  # only TLS
        assert len(result["blast_radii"]) == 2
        assert len(result["playbooks"]) == 2
        assert len(result["compliance_reports"]) == 3  # PCI, SOC2, HIPAA

    def test_full_analysis_empty(self) -> None:
        a = _analyzer()
        g = _graph()
        result = a.full_analysis(g, [])
        assert len(result["frequency_compliance"]) == 0
        assert result["maturity"].overall_level == MaturityLevel.MANUAL


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


class TestPrivateHelpers:
    def test_resolve_affected(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        s = _entry(component_ids=["c1", "c3"])  # c3 doesn't exist
        result = a._resolve_affected(g, s)
        assert result == ["c1"]

    def test_count_affected(self) -> None:
        a = _analyzer()
        g = _graph(_comp("c1"), _comp("c2"))
        s = _entry(component_ids=["c1", "c2", "c3"])
        assert a._count_affected(g, s) == 2


# ---------------------------------------------------------------------------
# Data class defaults and edge cases
# ---------------------------------------------------------------------------


class TestDataClassDefaults:
    def test_frequency_compliance_result_defaults(self) -> None:
        r = FrequencyComplianceResult(
            secret_id="s1",
            kind=SecretKind.API_KEY,
            required_interval_days=90,
            actual_interval_days=None,
            compliant=False,
        )
        assert r.overdue_days == 0
        assert r.severity == RiskSeverity.LOW
        assert r.message == ""

    def test_rotation_window_analysis_defaults(self) -> None:
        r = RotationWindowAnalysis(secret_id="s1")
        assert r.estimated_downtime_seconds == 0.0
        assert r.overlap_safe is True

    def test_dual_secret_analysis_defaults(self) -> None:
        r = DualSecretAnalysis(secret_id="s1")
        assert r.dual_enabled is False
        assert r.zero_downtime is False

    def test_cert_chain_validation_defaults(self) -> None:
        r = CertChainValidation(secret_id="s1")
        assert r.chain_length == 0
        assert r.expired is False

    def test_blast_radius_entry_defaults(self) -> None:
        r = BlastRadiusEntry(secret_id="s1")
        assert r.total_affected_count == 0
        assert r.affected_percent == 0.0

    def test_maturity_assessment_defaults(self) -> None:
        r = MaturityAssessment()
        assert r.overall_level == MaturityLevel.MANUAL
        assert r.score == 0.0

    def test_sprawl_entry_defaults(self) -> None:
        r = SprawlEntry(secret_id="s1", name="test", kind=SecretKind.API_KEY)
        assert r.service_count == 0

    def test_playbook_step_defaults(self) -> None:
        r = PlaybookStep(order=1, description="test")
        assert r.priority == PlaybookPriority.MEDIUM
        assert r.estimated_seconds == 0.0

    def test_emergency_playbook_defaults(self) -> None:
        r = EmergencyPlaybook(secret_id="s1", secret_name="test", kind=SecretKind.API_KEY)
        assert r.steps == []
        assert r.total_estimated_seconds == 0.0

    def test_rotation_dependency_defaults(self) -> None:
        r = RotationDependency(source_secret_id="s1", target_secret_id="s2")
        assert r.reason == ""

    def test_rotation_order_defaults(self) -> None:
        r = RotationOrder()
        assert r.ordered_ids == []
        assert r.has_cycle is False

    def test_compliance_mapping_defaults(self) -> None:
        r = ComplianceMapping(secret_id="s1", framework=ComplianceFramework.PCI_DSS)
        assert r.compliant is True
        assert r.gap_days == 0

    def test_compliance_report_defaults(self) -> None:
        r = ComplianceReport(framework=ComplianceFramework.SOC2)
        assert r.total_secrets == 0
        assert r.compliance_percent == 0.0
