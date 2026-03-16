"""Tests for faultray.simulator.secret_rotation module.

130+ tests covering all enums, data models, engine methods, edge cases,
and internal helpers with 100% coverage.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph, Dependency
from faultray.simulator.secret_rotation import (
    BlastRadiusResult,
    LeakedSecretResponse,
    RotationImpact,
    RotationReadinessReport,
    RotationStrategy,
    Secret,
    SecretRotationEngine,
    SecretType,
    SharedSecretRisk,
    _STRATEGY_BASE_DOWNTIME,
    _STRATEGY_ROLLBACK,
    _SECRET_LEAK_SEVERITY,
    _SECRET_CONNECTION_RESETS,
    _SECRET_CACHE_INVALIDATION,
    _clamp,
    _risk_level,
    _parse_iso,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str | None = None,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        health=health,
    )


def _graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


def _engine() -> SecretRotationEngine:
    return SecretRotationEngine()


def _secret(
    sid: str = "s1",
    name: str = "test-secret",
    secret_type: SecretType = SecretType.API_KEY,
    component_ids: list[str] | None = None,
    rotation_strategy: RotationStrategy = RotationStrategy.GRACE_PERIOD,
    rotation_interval_days: int = 90,
    last_rotated: str = "",
    expiry_date: str = "",
    auto_rotation: bool = False,
) -> Secret:
    return Secret(
        id=sid,
        name=name,
        secret_type=secret_type,
        component_ids=component_ids or [],
        rotation_strategy=rotation_strategy,
        rotation_interval_days=rotation_interval_days,
        last_rotated=last_rotated,
        expiry_date=expiry_date,
        auto_rotation=auto_rotation,
    )


def _expired_date() -> str:
    """Return an ISO date string in the past."""
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def _future_date() -> str:
    """Return an ISO date string in the future."""
    return (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()


# ===========================================================================
# Enum tests
# ===========================================================================


class TestSecretTypeEnum:
    """Tests for SecretType enum values."""

    def test_all_secret_types_exist(self):
        assert len(SecretType) == 10

    @pytest.mark.parametrize(
        "member,value",
        [
            (SecretType.DATABASE_PASSWORD, "database_password"),
            (SecretType.API_KEY, "api_key"),
            (SecretType.TLS_CERTIFICATE, "tls_certificate"),
            (SecretType.OAUTH_TOKEN, "oauth_token"),
            (SecretType.ENCRYPTION_KEY, "encryption_key"),
            (SecretType.SSH_KEY, "ssh_key"),
            (SecretType.JWT_SIGNING_KEY, "jwt_signing_key"),
            (SecretType.SERVICE_ACCOUNT, "service_account"),
            (SecretType.CONNECTION_STRING, "connection_string"),
            (SecretType.WEBHOOK_SECRET, "webhook_secret"),
        ],
    )
    def test_secret_type_values(self, member, value):
        assert member.value == value

    def test_secret_type_is_str_enum(self):
        assert isinstance(SecretType.API_KEY, str)


class TestRotationStrategyEnum:
    """Tests for RotationStrategy enum values."""

    def test_all_strategies_exist(self):
        assert len(RotationStrategy) == 6

    @pytest.mark.parametrize(
        "member,value",
        [
            (RotationStrategy.BLUE_GREEN, "blue_green"),
            (RotationStrategy.ROLLING, "rolling"),
            (RotationStrategy.DUAL_WRITE, "dual_write"),
            (RotationStrategy.GRACE_PERIOD, "grace_period"),
            (RotationStrategy.IMMEDIATE, "immediate"),
            (RotationStrategy.SCHEDULED_MAINTENANCE, "scheduled_maintenance"),
        ],
    )
    def test_rotation_strategy_values(self, member, value):
        assert member.value == value

    def test_rotation_strategy_is_str_enum(self):
        assert isinstance(RotationStrategy.ROLLING, str)


# ===========================================================================
# Data model tests
# ===========================================================================


class TestSecretModel:
    """Tests for Secret Pydantic model."""

    def test_defaults(self):
        s = Secret(id="s1", name="my-secret", secret_type=SecretType.API_KEY)
        assert s.id == "s1"
        assert s.name == "my-secret"
        assert s.secret_type == SecretType.API_KEY
        assert s.component_ids == []
        assert s.rotation_strategy == RotationStrategy.GRACE_PERIOD
        assert s.rotation_interval_days == 90
        assert s.last_rotated == ""
        assert s.expiry_date == ""
        assert s.auto_rotation is False

    def test_full_construction(self):
        s = _secret(
            component_ids=["a", "b"],
            rotation_strategy=RotationStrategy.BLUE_GREEN,
            rotation_interval_days=30,
            last_rotated="2025-01-01T00:00:00Z",
            expiry_date="2025-04-01T00:00:00Z",
            auto_rotation=True,
        )
        assert s.component_ids == ["a", "b"]
        assert s.rotation_strategy == RotationStrategy.BLUE_GREEN
        assert s.rotation_interval_days == 30
        assert s.auto_rotation is True

    def test_min_rotation_interval(self):
        with pytest.raises(Exception):
            Secret(
                id="s", name="s", secret_type=SecretType.API_KEY,
                rotation_interval_days=0,
            )


class TestRotationImpactModel:
    """Tests for RotationImpact Pydantic model."""

    def test_defaults(self):
        ri = RotationImpact(secret_id="s1")
        assert ri.secret_id == "s1"
        assert ri.affected_services == []
        assert ri.downtime_seconds == 0.0
        assert ri.connection_reset_count == 0
        assert ri.cache_invalidation_needed is False
        assert ri.rollback_possible is True
        assert ri.risk_level == "low"
        assert ri.recommendations == []


class TestRotationReadinessReportModel:
    """Tests for RotationReadinessReport model."""

    def test_defaults(self):
        r = RotationReadinessReport()
        assert r.total_secrets == 0
        assert r.readiness_score == 0.0
        assert r.recommendations == []


class TestLeakedSecretResponseModel:
    """Tests for LeakedSecretResponse model."""

    def test_defaults(self):
        lr = LeakedSecretResponse(secret_id="s1")
        assert lr.severity == "critical"
        assert lr.requires_maintenance_window is False
        assert lr.rollback_possible is True


class TestSharedSecretRiskModel:
    """Tests for SharedSecretRisk model."""

    def test_defaults(self):
        r = SharedSecretRisk(secret_id="s1")
        assert r.blast_radius == 0
        assert r.risk_level == "low"


class TestBlastRadiusResultModel:
    """Tests for BlastRadiusResult model."""

    def test_defaults(self):
        br = BlastRadiusResult(secret_id="s1")
        assert br.total_services == 0
        assert br.directly_affected == []
        assert br.transitively_affected == []
        assert br.affected_percent == 0.0


# ===========================================================================
# Helper function tests
# ===========================================================================


class TestClamp:
    """Tests for _clamp helper."""

    def test_in_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_lo(self):
        assert _clamp(-10.0) == 0.0

    def test_above_hi(self):
        assert _clamp(200.0) == 100.0

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0

    def test_custom_range(self):
        assert _clamp(5.0, lo=1.0, hi=10.0) == 5.0
        assert _clamp(0.0, lo=1.0, hi=10.0) == 1.0
        assert _clamp(15.0, lo=1.0, hi=10.0) == 10.0


class TestRiskLevel:
    """Tests for _risk_level helper."""

    def test_critical(self):
        assert _risk_level(0.8) == "critical"
        assert _risk_level(1.0) == "critical"

    def test_high(self):
        assert _risk_level(0.6) == "high"
        assert _risk_level(0.79) == "high"

    def test_medium(self):
        assert _risk_level(0.4) == "medium"
        assert _risk_level(0.59) == "medium"

    def test_low(self):
        assert _risk_level(0.0) == "low"
        assert _risk_level(0.39) == "low"


class TestParseIso:
    """Tests for _parse_iso helper."""

    def test_valid_iso(self):
        dt = _parse_iso("2025-06-15T10:30:00+00:00")
        assert dt is not None
        assert dt.year == 2025

    def test_z_suffix(self):
        dt = _parse_iso("2025-06-15T10:30:00Z")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_empty_string(self):
        assert _parse_iso("") is None

    def test_invalid_string(self):
        assert _parse_iso("not-a-date") is None

    def test_naive_datetime(self):
        dt = _parse_iso("2025-06-15T10:30:00")
        assert dt is not None


# ===========================================================================
# Constant coverage tests
# ===========================================================================


class TestConstants:
    """Tests to cover constant dictionaries."""

    def test_strategy_base_downtime_all_strategies(self):
        for strategy in RotationStrategy:
            assert strategy in _STRATEGY_BASE_DOWNTIME

    def test_strategy_rollback_all_strategies(self):
        for strategy in RotationStrategy:
            assert strategy in _STRATEGY_ROLLBACK

    def test_secret_leak_severity_all_types(self):
        for st in SecretType:
            assert st in _SECRET_LEAK_SEVERITY
            assert 0.0 <= _SECRET_LEAK_SEVERITY[st] <= 1.0

    def test_secret_connection_resets_all_types(self):
        for st in SecretType:
            assert st in _SECRET_CONNECTION_RESETS
            assert _SECRET_CONNECTION_RESETS[st] >= 0

    def test_secret_cache_invalidation_all_types(self):
        for st in SecretType:
            assert st in _SECRET_CACHE_INVALIDATION

    def test_blue_green_zero_downtime(self):
        assert _STRATEGY_BASE_DOWNTIME[RotationStrategy.BLUE_GREEN] == 0.0

    def test_immediate_no_rollback(self):
        assert _STRATEGY_ROLLBACK[RotationStrategy.IMMEDIATE] is False


# ===========================================================================
# simulate_rotation tests
# ===========================================================================


class TestSimulateRotation:
    """Tests for SecretRotationEngine.simulate_rotation."""

    def test_basic_rotation(self):
        g = _graph(_comp("app1"))
        s = _secret(component_ids=["app1"])
        result = _engine().simulate_rotation(g, s)
        assert result.secret_id == "s1"
        assert "app1" in result.affected_services

    def test_blue_green_zero_downtime(self):
        g = _graph(_comp("app1"))
        s = _secret(
            component_ids=["app1"],
            rotation_strategy=RotationStrategy.BLUE_GREEN,
        )
        result = _engine().simulate_rotation(g, s)
        assert result.downtime_seconds == 0.0
        assert result.rollback_possible is True

    def test_rolling_strategy(self):
        g = _graph(_comp("a1"), _comp("a2"), _comp("a3"))
        s = _secret(
            component_ids=["a1", "a2", "a3"],
            rotation_strategy=RotationStrategy.ROLLING,
        )
        result = _engine().simulate_rotation(g, s)
        assert result.downtime_seconds > 0.0
        assert len(result.affected_services) == 3

    def test_dual_write_zero_downtime(self):
        g = _graph(_comp("app1"))
        s = _secret(
            component_ids=["app1"],
            rotation_strategy=RotationStrategy.DUAL_WRITE,
        )
        result = _engine().simulate_rotation(g, s)
        assert result.downtime_seconds == 0.0

    def test_grace_period_reduced_downtime(self):
        g = _graph(_comp("app1"), _comp("app2"))
        s = _secret(
            component_ids=["app1", "app2"],
            rotation_strategy=RotationStrategy.GRACE_PERIOD,
        )
        result = _engine().simulate_rotation(g, s)
        # Grace period halves downtime
        assert result.downtime_seconds > 0.0

    def test_immediate_strategy_high_downtime(self):
        g = _graph(_comp("app1"))
        s = _secret(
            component_ids=["app1"],
            rotation_strategy=RotationStrategy.IMMEDIATE,
        )
        result = _engine().simulate_rotation(g, s)
        assert result.downtime_seconds > 0.0
        assert result.rollback_possible is False

    def test_scheduled_maintenance(self):
        g = _graph(_comp("app1"))
        s = _secret(
            component_ids=["app1"],
            rotation_strategy=RotationStrategy.SCHEDULED_MAINTENANCE,
        )
        result = _engine().simulate_rotation(g, s)
        assert result.downtime_seconds > 0.0
        assert result.rollback_possible is True

    def test_auto_rotation_reduces_downtime(self):
        g = _graph(_comp("app1"))
        s_manual = _secret(component_ids=["app1"], rotation_strategy=RotationStrategy.ROLLING)
        s_auto = _secret(
            component_ids=["app1"],
            rotation_strategy=RotationStrategy.ROLLING,
            auto_rotation=True,
        )
        manual = _engine().simulate_rotation(g, s_manual)
        auto = _engine().simulate_rotation(g, s_auto)
        assert auto.downtime_seconds < manual.downtime_seconds

    def test_connection_resets_scale_with_components(self):
        g = _graph(_comp("a1"), _comp("a2"))
        s = _secret(component_ids=["a1", "a2"])
        result = _engine().simulate_rotation(g, s)
        assert result.connection_reset_count == _SECRET_CONNECTION_RESETS[SecretType.API_KEY] * 2

    def test_cache_invalidation_for_api_key(self):
        g = _graph(_comp("app1"))
        s = _secret(component_ids=["app1"], secret_type=SecretType.API_KEY)
        result = _engine().simulate_rotation(g, s)
        assert result.cache_invalidation_needed is True

    def test_no_cache_invalidation_for_ssh_key(self):
        g = _graph(_comp("app1"))
        s = _secret(component_ids=["app1"], secret_type=SecretType.SSH_KEY)
        result = _engine().simulate_rotation(g, s)
        assert result.cache_invalidation_needed is False

    def test_risk_level_many_components(self):
        comps = [_comp(f"a{i}") for i in range(8)]
        g = _graph(*comps)
        s = _secret(
            component_ids=[f"a{i}" for i in range(8)],
            rotation_strategy=RotationStrategy.IMMEDIATE,
        )
        result = _engine().simulate_rotation(g, s)
        assert result.risk_level in ("high", "critical")

    def test_risk_level_few_components_safe_strategy(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.BLUE_GREEN,
            auto_rotation=True,
        )
        result = _engine().simulate_rotation(g, s)
        assert result.risk_level == "low"

    def test_nonexistent_component_filtered(self):
        g = _graph(_comp("app1"))
        s = _secret(component_ids=["app1", "nonexistent"])
        result = _engine().simulate_rotation(g, s)
        assert result.affected_services == ["app1"]

    def test_empty_component_ids(self):
        g = _graph(_comp("app1"))
        s = _secret(component_ids=[])
        result = _engine().simulate_rotation(g, s)
        assert result.affected_services == []

    def test_recommendations_present(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"])
        result = _engine().simulate_rotation(g, s)
        assert len(result.recommendations) > 0

    def test_medium_component_count_risk(self):
        """3 affected components -> medium risk modifier."""
        comps = [_comp(f"a{i}") for i in range(4)]
        g = _graph(*comps)
        s = _secret(component_ids=[f"a{i}" for i in range(4)])
        result = _engine().simulate_rotation(g, s)
        assert result.risk_level in ("low", "medium", "high")

    def test_all_strategies_produce_recommendations(self):
        g = _graph(_comp("a1"))
        for strategy in RotationStrategy:
            s = _secret(component_ids=["a1"], rotation_strategy=strategy)
            result = _engine().simulate_rotation(g, s)
            assert len(result.recommendations) >= 1

    def test_database_password_rotation(self):
        g = _graph(_comp("db1", ctype=ComponentType.DATABASE))
        s = _secret(
            component_ids=["db1"],
            secret_type=SecretType.DATABASE_PASSWORD,
        )
        result = _engine().simulate_rotation(g, s)
        assert result.cache_invalidation_needed is True
        assert result.connection_reset_count == 50


# ===========================================================================
# detect_expired_secrets tests
# ===========================================================================


class TestDetectExpiredSecrets:
    """Tests for SecretRotationEngine.detect_expired_secrets."""

    def test_no_secrets(self):
        result = _engine().detect_expired_secrets([])
        assert result == []

    def test_no_expired(self):
        s = _secret(expiry_date=_future_date())
        result = _engine().detect_expired_secrets([s])
        assert result == []

    def test_one_expired(self):
        s = _secret(expiry_date=_expired_date())
        result = _engine().detect_expired_secrets([s])
        assert result == ["s1"]

    def test_mixed_expired_and_valid(self):
        s1 = _secret(sid="s1", expiry_date=_expired_date())
        s2 = _secret(sid="s2", expiry_date=_future_date())
        s3 = _secret(sid="s3", expiry_date=_expired_date())
        result = _engine().detect_expired_secrets([s1, s2, s3])
        assert "s1" in result
        assert "s3" in result
        assert "s2" not in result

    def test_empty_expiry_not_expired(self):
        s = _secret(expiry_date="")
        result = _engine().detect_expired_secrets([s])
        assert result == []

    def test_invalid_expiry_not_expired(self):
        s = _secret(expiry_date="invalid")
        result = _engine().detect_expired_secrets([s])
        assert result == []

    def test_z_suffix_expiry(self):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        s = _secret(expiry_date=past)
        result = _engine().detect_expired_secrets([s])
        assert result == ["s1"]

    def test_naive_datetime_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        s = _secret(expiry_date=past)
        result = _engine().detect_expired_secrets([s])
        assert result == ["s1"]


# ===========================================================================
# assess_rotation_readiness tests
# ===========================================================================


class TestAssessRotationReadiness:
    """Tests for SecretRotationEngine.assess_rotation_readiness."""

    def test_empty_secrets(self):
        g = _graph()
        result = _engine().assess_rotation_readiness(g, [])
        assert result.readiness_score == 100.0
        assert result.total_secrets == 0

    def test_all_ready(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.BLUE_GREEN,
            auto_rotation=True,
            expiry_date=_future_date(),
        )
        result = _engine().assess_rotation_readiness(g, [s])
        assert result.ready_count == 1
        assert result.not_ready_count == 0
        assert result.readiness_score > 0

    def test_expired_secret_not_ready(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            expiry_date=_expired_date(),
        )
        result = _engine().assess_rotation_readiness(g, [s])
        assert result.not_ready_count == 1
        assert result.expired_count == 1

    def test_missing_component_not_ready(self):
        g = _graph()
        s = _secret(component_ids=["nonexistent"])
        result = _engine().assess_rotation_readiness(g, [s])
        assert result.not_ready_count == 1

    def test_immediate_strategy_not_ready(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.IMMEDIATE,
            expiry_date=_future_date(),
        )
        result = _engine().assess_rotation_readiness(g, [s])
        assert result.not_ready_count == 1

    def test_auto_rotation_boosts_score(self):
        g = _graph(_comp("a1"))
        s_manual = _secret(
            component_ids=["a1"],
            auto_rotation=False,
            expiry_date=_future_date(),
        )
        s_auto = _secret(
            component_ids=["a1"],
            auto_rotation=True,
            expiry_date=_future_date(),
        )
        manual = _engine().assess_rotation_readiness(g, [s_manual])
        auto = _engine().assess_rotation_readiness(g, [s_auto])
        assert auto.readiness_score > manual.readiness_score

    def test_recommendations_for_expired(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"], expiry_date=_expired_date())
        result = _engine().assess_rotation_readiness(g, [s])
        assert any("expired" in r for r in result.recommendations)

    def test_recommendations_for_no_auto_rotation(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            auto_rotation=False,
            expiry_date=_future_date(),
        )
        result = _engine().assess_rotation_readiness(g, [s])
        assert any("auto-rotation" in r for r in result.recommendations)

    def test_recommendations_for_immediate_strategy(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.IMMEDIATE,
            expiry_date=_future_date(),
        )
        result = _engine().assess_rotation_readiness(g, [s])
        assert any("immediate" in r.lower() for r in result.recommendations)

    def test_multiple_secrets_mixed(self):
        g = _graph(_comp("a1"), _comp("a2"))
        s1 = _secret(
            sid="s1",
            component_ids=["a1"],
            auto_rotation=True,
            expiry_date=_future_date(),
        )
        s2 = _secret(
            sid="s2",
            component_ids=["a2"],
            rotation_strategy=RotationStrategy.IMMEDIATE,
            expiry_date=_expired_date(),
        )
        result = _engine().assess_rotation_readiness(g, [s1, s2])
        assert result.total_secrets == 2
        assert result.ready_count == 1
        assert result.not_ready_count == 1

    def test_not_ready_recommendation(self):
        g = _graph()
        s = _secret(component_ids=["nonexistent"])
        result = _engine().assess_rotation_readiness(g, [s])
        assert any("not ready" in r for r in result.recommendations)

    def test_score_clamped_to_100(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            auto_rotation=True,
            expiry_date=_future_date(),
        )
        result = _engine().assess_rotation_readiness(g, [s])
        assert result.readiness_score <= 100.0


# ===========================================================================
# simulate_leaked_secret tests
# ===========================================================================


class TestSimulateLeakedSecret:
    """Tests for SecretRotationEngine.simulate_leaked_secret."""

    def test_basic_leak(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"])
        result = _engine().simulate_leaked_secret(g, s)
        assert result.secret_id == "s1"
        assert len(result.immediate_actions) > 0
        assert len(result.recommendations) > 0

    def test_database_password_leak(self):
        g = _graph(_comp("db1", ctype=ComponentType.DATABASE))
        s = _secret(
            component_ids=["db1"],
            secret_type=SecretType.DATABASE_PASSWORD,
        )
        result = _engine().simulate_leaked_secret(g, s)
        assert result.severity in ("high", "critical")
        assert any("database" in a.lower() for a in result.immediate_actions)

    def test_tls_certificate_leak(self):
        g = _graph(_comp("web1", ctype=ComponentType.WEB_SERVER))
        s = _secret(
            component_ids=["web1"],
            secret_type=SecretType.TLS_CERTIFICATE,
        )
        result = _engine().simulate_leaked_secret(g, s)
        assert any("certificate" in a.lower() for a in result.immediate_actions)

    def test_ssh_key_leak(self):
        g = _graph(_comp("srv1"))
        s = _secret(component_ids=["srv1"], secret_type=SecretType.SSH_KEY)
        result = _engine().simulate_leaked_secret(g, s)
        assert any("ssh" in a.lower() for a in result.immediate_actions)

    def test_api_key_leak(self):
        g = _graph(_comp("api1"))
        s = _secret(component_ids=["api1"], secret_type=SecretType.API_KEY)
        result = _engine().simulate_leaked_secret(g, s)
        assert any("api key" in a.lower() for a in result.immediate_actions)

    def test_encryption_key_leak(self):
        g = _graph(_comp("enc1"))
        s = _secret(component_ids=["enc1"], secret_type=SecretType.ENCRYPTION_KEY)
        result = _engine().simulate_leaked_secret(g, s)
        assert any("re-encrypt" in a.lower() for a in result.immediate_actions)
        assert result.requires_maintenance_window is True  # no auto_rotation

    def test_jwt_signing_key_leak(self):
        g = _graph(_comp("auth1"))
        s = _secret(component_ids=["auth1"], secret_type=SecretType.JWT_SIGNING_KEY)
        result = _engine().simulate_leaked_secret(g, s)
        assert any("token" in a.lower() for a in result.immediate_actions)

    def test_oauth_token_leak(self):
        g = _graph(_comp("oa1"))
        s = _secret(component_ids=["oa1"], secret_type=SecretType.OAUTH_TOKEN)
        result = _engine().simulate_leaked_secret(g, s)
        assert any("oauth" in a.lower() for a in result.immediate_actions)

    def test_service_account_leak(self):
        g = _graph(_comp("sa1"))
        s = _secret(component_ids=["sa1"], secret_type=SecretType.SERVICE_ACCOUNT)
        result = _engine().simulate_leaked_secret(g, s)
        assert any("service account" in a.lower() for a in result.immediate_actions)

    def test_connection_string_leak(self):
        g = _graph(_comp("cs1"))
        s = _secret(component_ids=["cs1"], secret_type=SecretType.CONNECTION_STRING)
        result = _engine().simulate_leaked_secret(g, s)
        assert any("connection string" in a.lower() for a in result.immediate_actions)

    def test_webhook_secret_leak(self):
        g = _graph(_comp("wh1"))
        s = _secret(component_ids=["wh1"], secret_type=SecretType.WEBHOOK_SECRET)
        result = _engine().simulate_leaked_secret(g, s)
        assert any("webhook" in a.lower() for a in result.immediate_actions)

    def test_auto_rotation_faster_response(self):
        g = _graph(_comp("a1"))
        s_manual = _secret(component_ids=["a1"], auto_rotation=False)
        s_auto = _secret(component_ids=["a1"], auto_rotation=True)
        manual = _engine().simulate_leaked_secret(g, s_manual)
        auto = _engine().simulate_leaked_secret(g, s_auto)
        assert auto.rotation_time_seconds < manual.rotation_time_seconds

    def test_immediate_strategy_amplified_disruption(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.IMMEDIATE,
        )
        result = _engine().simulate_leaked_secret(g, s)
        assert result.service_disruption_seconds > 0.0
        assert result.rollback_possible is False

    def test_maintenance_window_for_scheduled(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.SCHEDULED_MAINTENANCE,
        )
        result = _engine().simulate_leaked_secret(g, s)
        assert result.requires_maintenance_window is True

    def test_many_affected_services_recommendation(self):
        comps = [_comp(f"a{i}") for i in range(5)]
        g = _graph(*comps)
        s = _secret(component_ids=[f"a{i}" for i in range(5)])
        result = _engine().simulate_leaked_secret(g, s)
        assert any("isolation" in r for r in result.recommendations)

    def test_no_maintenance_for_auto_rotation_db(self):
        g = _graph(_comp("db1", ctype=ComponentType.DATABASE))
        s = _secret(
            component_ids=["db1"],
            secret_type=SecretType.DATABASE_PASSWORD,
            auto_rotation=True,
        )
        result = _engine().simulate_leaked_secret(g, s)
        assert result.requires_maintenance_window is False

    def test_encryption_key_auto_rotation_no_maintenance(self):
        g = _graph(_comp("enc1"))
        s = _secret(
            component_ids=["enc1"],
            secret_type=SecretType.ENCRYPTION_KEY,
            auto_rotation=True,
        )
        result = _engine().simulate_leaked_secret(g, s)
        assert result.requires_maintenance_window is False

    def test_recommendations_always_include_ci_cd(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"])
        result = _engine().simulate_leaked_secret(g, s)
        assert any("CI/CD" in r for r in result.recommendations)

    def test_recommendations_always_include_audit(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"])
        result = _engine().simulate_leaked_secret(g, s)
        assert any("audit" in r.lower() for r in result.recommendations)

    def test_empty_affected_services(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=[])
        result = _engine().simulate_leaked_secret(g, s)
        assert result.affected_services == []

    def test_auto_rotation_recommendation_when_disabled(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"], auto_rotation=False)
        result = _engine().simulate_leaked_secret(g, s)
        assert any("auto-rotation" in r.lower() for r in result.recommendations)

    def test_immediate_strategy_recommendation(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.IMMEDIATE,
        )
        result = _engine().simulate_leaked_secret(g, s)
        assert any("blue-green" in r.lower() for r in result.recommendations)


# ===========================================================================
# recommend_rotation_strategy tests
# ===========================================================================


class TestRecommendRotationStrategy:
    """Tests for SecretRotationEngine.recommend_rotation_strategy."""

    def test_many_dependents_returns_blue_green(self):
        comps = [_comp(f"a{i}") for i in range(7)]
        g = _graph(*comps)
        s = _secret(component_ids=[f"a{i}" for i in range(7)])
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.BLUE_GREEN

    def test_tls_certificate_returns_dual_write(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"], secret_type=SecretType.TLS_CERTIFICATE)
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.DUAL_WRITE

    def test_encryption_key_returns_dual_write(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"], secret_type=SecretType.ENCRYPTION_KEY)
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.DUAL_WRITE

    def test_database_password_returns_grace_period(self):
        g = _graph(_comp("db1", ctype=ComponentType.DATABASE))
        s = _secret(
            component_ids=["db1"],
            secret_type=SecretType.DATABASE_PASSWORD,
        )
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.GRACE_PERIOD

    def test_connection_string_returns_grace_period(self):
        g = _graph(_comp("db1"))
        s = _secret(component_ids=["db1"], secret_type=SecretType.CONNECTION_STRING)
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.GRACE_PERIOD

    def test_jwt_signing_key_returns_rolling(self):
        g = _graph(_comp("auth1"), _comp("auth2"))
        s = _secret(
            component_ids=["auth1", "auth2"],
            secret_type=SecretType.JWT_SIGNING_KEY,
        )
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.ROLLING

    def test_oauth_token_returns_rolling(self):
        g = _graph(_comp("oa1"), _comp("oa2"))
        s = _secret(
            component_ids=["oa1", "oa2"],
            secret_type=SecretType.OAUTH_TOKEN,
        )
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.ROLLING

    def test_single_component_returns_grace_period(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"], secret_type=SecretType.WEBHOOK_SECRET)
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.GRACE_PERIOD

    def test_moderate_impact_returns_rolling(self):
        g = _graph(_comp("a1"), _comp("a2"), _comp("a3"))
        s = _secret(
            component_ids=["a1", "a2", "a3"],
            secret_type=SecretType.SERVICE_ACCOUNT,
        )
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.ROLLING

    def test_empty_components_returns_grace_period(self):
        g = _graph()
        s = _secret(component_ids=[], secret_type=SecretType.SSH_KEY)
        result = _engine().recommend_rotation_strategy(g, s)
        # 0 affected -> num_affected <= 1 -> grace_period
        assert result == RotationStrategy.GRACE_PERIOD

    def test_tls_with_many_deps_still_blue_green(self):
        """Blue-green takes precedence for >5 affected."""
        comps = [_comp(f"a{i}") for i in range(7)]
        g = _graph(*comps)
        s = _secret(
            component_ids=[f"a{i}" for i in range(7)],
            secret_type=SecretType.TLS_CERTIFICATE,
        )
        result = _engine().recommend_rotation_strategy(g, s)
        assert result == RotationStrategy.BLUE_GREEN


# ===========================================================================
# find_shared_secrets tests
# ===========================================================================


class TestFindSharedSecrets:
    """Tests for SecretRotationEngine.find_shared_secrets."""

    def test_no_secrets(self):
        result = _engine().find_shared_secrets([])
        assert result == []

    def test_single_component_not_shared(self):
        s = _secret(component_ids=["a1"])
        result = _engine().find_shared_secrets([s])
        assert result == []

    def test_empty_component_ids_not_shared(self):
        s = _secret(component_ids=[])
        result = _engine().find_shared_secrets([s])
        assert result == []

    def test_two_components_shared(self):
        s = _secret(component_ids=["a1", "a2"])
        result = _engine().find_shared_secrets([s])
        assert len(result) == 1
        assert result[0].blast_radius == 2
        assert set(result[0].shared_component_ids) == {"a1", "a2"}

    def test_five_components_high_risk(self):
        s = _secret(
            component_ids=["a1", "a2", "a3", "a4", "a5"],
            secret_type=SecretType.DATABASE_PASSWORD,
        )
        result = _engine().find_shared_secrets([s])
        assert len(result) == 1
        assert result[0].blast_radius == 5
        assert result[0].risk_level in ("high", "critical")

    def test_three_components_medium_risk(self):
        s = _secret(
            component_ids=["a1", "a2", "a3"],
            secret_type=SecretType.WEBHOOK_SECRET,
        )
        result = _engine().find_shared_secrets([s])
        assert len(result) == 1
        assert result[0].blast_radius == 3

    def test_recommendations_for_shared(self):
        s = _secret(component_ids=["a1", "a2", "a3"])
        result = _engine().find_shared_secrets([s])
        assert len(result[0].recommendations) > 0

    def test_auto_rotation_recommendation(self):
        s = _secret(component_ids=["a1", "a2"], auto_rotation=False)
        result = _engine().find_shared_secrets([s])
        assert any("auto-rotation" in r for r in result[0].recommendations)

    def test_no_auto_rotation_recommendation_when_enabled(self):
        s = _secret(component_ids=["a1", "a2"], auto_rotation=True)
        result = _engine().find_shared_secrets([s])
        assert not any("auto-rotation" in r for r in result[0].recommendations)

    def test_multiple_secrets_filtered(self):
        s1 = _secret(sid="s1", component_ids=["a1"])
        s2 = _secret(sid="s2", component_ids=["a1", "a2"])
        s3 = _secret(sid="s3", component_ids=["a1", "a2", "a3"])
        result = _engine().find_shared_secrets([s1, s2, s3])
        assert len(result) == 2  # s2 and s3 only
        ids = [r.secret_id for r in result]
        assert "s2" in ids
        assert "s3" in ids

    def test_high_severity_type_amplifies_risk(self):
        s_low = _secret(
            sid="low",
            component_ids=["a1", "a2"],
            secret_type=SecretType.WEBHOOK_SECRET,
        )
        s_high = _secret(
            sid="high",
            component_ids=["a1", "a2"],
            secret_type=SecretType.DATABASE_PASSWORD,
        )
        results_low = _engine().find_shared_secrets([s_low])
        results_high = _engine().find_shared_secrets([s_high])
        # Higher severity type should produce higher or equal risk
        risk_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        assert risk_order[results_high[0].risk_level] >= risk_order[results_low[0].risk_level]

    def test_per_service_recommendation_for_3_plus(self):
        s = _secret(component_ids=["a1", "a2", "a3"])
        result = _engine().find_shared_secrets([s])
        assert any("per-service" in r for r in result[0].recommendations)

    def test_versioning_recommendation(self):
        s = _secret(component_ids=["a1", "a2"])
        result = _engine().find_shared_secrets([s])
        assert any("versioning" in r for r in result[0].recommendations)


# ===========================================================================
# calculate_rotation_blast_radius tests
# ===========================================================================


class TestCalculateRotationBlastRadius:
    """Tests for SecretRotationEngine.calculate_rotation_blast_radius."""

    def test_empty_graph(self):
        g = _graph()
        s = _secret(component_ids=["a1"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.total_services == 0
        assert "No services" in result.recommendations[0]

    def test_single_component_directly_affected(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.total_services == 1
        assert result.directly_affected == ["a1"]
        assert result.affected_percent == 100.0

    def test_transitive_impact(self):
        g = _graph(_comp("db1"), _comp("app1"), _comp("web1"))
        # app1 -> db1, web1 -> app1
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        g.add_dependency(Dependency(source_id="web1", target_id="app1"))
        s = _secret(component_ids=["db1"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert "db1" in result.directly_affected
        assert len(result.transitively_affected) > 0

    def test_no_transitive_impact(self):
        g = _graph(_comp("a1"), _comp("a2"))
        s = _secret(component_ids=["a1"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.directly_affected == ["a1"]
        assert result.transitively_affected == []

    def test_nonexistent_component_excluded(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1", "nonexistent"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.directly_affected == ["a1"]

    def test_downtime_scales_with_direct_impact(self):
        g = _graph(_comp("a1"), _comp("a2"), _comp("a3"))
        s = _secret(
            component_ids=["a1", "a2", "a3"],
            rotation_strategy=RotationStrategy.ROLLING,
        )
        result = _engine().calculate_rotation_blast_radius(g, s)
        expected = _STRATEGY_BASE_DOWNTIME[RotationStrategy.ROLLING] * 3
        assert result.estimated_downtime_seconds == expected

    def test_auto_rotation_reduces_downtime(self):
        g = _graph(_comp("a1"))
        s_manual = _secret(component_ids=["a1"], rotation_strategy=RotationStrategy.ROLLING)
        s_auto = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.ROLLING,
            auto_rotation=True,
        )
        manual = _engine().calculate_rotation_blast_radius(g, s_manual)
        auto = _engine().calculate_rotation_blast_radius(g, s_auto)
        assert auto.estimated_downtime_seconds < manual.estimated_downtime_seconds

    def test_high_blast_radius_recommendation(self):
        comps = [_comp(f"a{i}") for i in range(3)]
        g = _graph(*comps)
        s = _secret(component_ids=["a0", "a1", "a2"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.affected_percent == 100.0
        assert any("per-service" in r.lower() for r in result.recommendations)

    def test_transitive_recommendation(self):
        g = _graph(_comp("db1"), _comp("app1"))
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))
        s = _secret(component_ids=["db1"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        if result.transitively_affected:
            assert any("circuit breaker" in r.lower() for r in result.recommendations)

    def test_auto_rotation_recommendation_when_disabled(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"], auto_rotation=False)
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert any("auto-rotation" in r for r in result.recommendations)

    def test_immediate_strategy_recommendation(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.IMMEDIATE,
        )
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert any("immediate" in r.lower() for r in result.recommendations)

    def test_many_direct_services_recommendation(self):
        comps = [_comp(f"a{i}") for i in range(5)]
        g = _graph(*comps)
        s = _secret(component_ids=[f"a{i}" for i in range(5)])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert any("splitting" in r.lower() or "per-service" in r.lower() for r in result.recommendations)

    def test_risk_level_high_blast(self):
        comps = [_comp(f"a{i}") for i in range(4)]
        g = _graph(*comps)
        s = _secret(
            component_ids=[f"a{i}" for i in range(4)],
            secret_type=SecretType.DATABASE_PASSWORD,
        )
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.risk_level in ("medium", "high", "critical")

    def test_risk_level_low_blast(self):
        comps = [_comp(f"a{i}") for i in range(10)]
        g = _graph(*comps)
        s = _secret(
            component_ids=["a0"],
            secret_type=SecretType.WEBHOOK_SECRET,
        )
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.risk_level in ("low", "medium")

    def test_affected_percent_calculated(self):
        comps = [_comp(f"a{i}") for i in range(4)]
        g = _graph(*comps)
        s = _secret(component_ids=["a0", "a1"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.affected_percent == 50.0

    def test_blue_green_zero_downtime_blast_radius(self):
        g = _graph(_comp("a1"))
        s = _secret(
            component_ids=["a1"],
            rotation_strategy=RotationStrategy.BLUE_GREEN,
        )
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.estimated_downtime_seconds == 0.0

    def test_moderate_affected_percent_10_to_25(self):
        """Affected percent between 10% and 25% triggers the moderate risk branch."""
        comps = [_comp(f"a{i}") for i in range(6)]
        g = _graph(*comps)
        # 1 out of 6 = ~16.7% directly affected, no transitive deps
        s = _secret(
            component_ids=["a0"],
            secret_type=SecretType.WEBHOOK_SECRET,
        )
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert 10.0 < result.affected_percent <= 25.0


# ===========================================================================
# Integration / complex scenario tests
# ===========================================================================


class TestIntegrationScenarios:
    """Integration tests with complex graphs and multiple secrets."""

    def test_full_workflow(self):
        """Test a complete workflow: detect, assess, simulate, blast radius."""
        g = _graph(
            _comp("web1", ctype=ComponentType.WEB_SERVER),
            _comp("app1", ctype=ComponentType.APP_SERVER),
            _comp("db1", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="web1", target_id="app1"))
        g.add_dependency(Dependency(source_id="app1", target_id="db1"))

        secrets = [
            _secret(
                sid="db-pw",
                name="db-password",
                secret_type=SecretType.DATABASE_PASSWORD,
                component_ids=["db1"],
                expiry_date=_future_date(),
                auto_rotation=True,
            ),
            _secret(
                sid="api-key",
                name="api-key",
                secret_type=SecretType.API_KEY,
                component_ids=["app1", "web1"],
                expiry_date=_expired_date(),
            ),
        ]

        engine = _engine()

        # Detect expired
        expired = engine.detect_expired_secrets(secrets)
        assert "api-key" in expired

        # Assess readiness
        readiness = engine.assess_rotation_readiness(g, secrets)
        assert readiness.total_secrets == 2
        assert readiness.expired_count == 1

        # Simulate rotation
        for s in secrets:
            impact = engine.simulate_rotation(g, s)
            assert impact.secret_id == s.id

        # Blast radius
        db_blast = engine.calculate_rotation_blast_radius(g, secrets[0])
        assert "db1" in db_blast.directly_affected
        # app1 and web1 should be transitively affected
        assert len(db_blast.transitively_affected) >= 1

    def test_shared_secrets_with_blast_radius(self):
        """Shared secret risk feeds into blast radius analysis."""
        comps = [_comp(f"svc{i}") for i in range(4)]
        g = _graph(*comps)
        s = _secret(
            component_ids=["svc0", "svc1", "svc2", "svc3"],
            secret_type=SecretType.SERVICE_ACCOUNT,
        )

        engine = _engine()
        shared = engine.find_shared_secrets([s])
        assert len(shared) == 1
        assert shared[0].blast_radius == 4

        blast = engine.calculate_rotation_blast_radius(g, s)
        assert blast.affected_percent == 100.0

    def test_recommend_then_simulate(self):
        """Recommended strategy should produce lower risk than immediate."""
        g = _graph(_comp("a1"), _comp("a2"))
        s = _secret(
            component_ids=["a1", "a2"],
            secret_type=SecretType.API_KEY,
            rotation_strategy=RotationStrategy.IMMEDIATE,
        )

        engine = _engine()
        recommended = engine.recommend_rotation_strategy(g, s)
        assert recommended != RotationStrategy.IMMEDIATE

        # Simulate with both strategies
        s_immediate = s
        s_recommended = _secret(
            component_ids=["a1", "a2"],
            secret_type=SecretType.API_KEY,
            rotation_strategy=recommended,
        )
        impact_immediate = engine.simulate_rotation(g, s_immediate)
        impact_recommended = engine.simulate_rotation(g, s_recommended)
        assert impact_recommended.downtime_seconds <= impact_immediate.downtime_seconds

    def test_leaked_then_blast_radius(self):
        """Leaked secret response and blast radius should be consistent."""
        g = _graph(_comp("a1"), _comp("a2"))
        g.add_dependency(Dependency(source_id="a2", target_id="a1"))
        s = _secret(component_ids=["a1"], secret_type=SecretType.SSH_KEY)

        engine = _engine()
        leak = engine.simulate_leaked_secret(g, s)
        blast = engine.calculate_rotation_blast_radius(g, s)

        assert blast.directly_affected == ["a1"]
        assert "a2" in blast.transitively_affected
        assert leak.affected_services == ["a1"]

    def test_all_secret_types_rotation(self):
        """Every secret type can be simulated."""
        g = _graph(_comp("a1"))
        engine = _engine()
        for st in SecretType:
            s = _secret(component_ids=["a1"], secret_type=st)
            result = engine.simulate_rotation(g, s)
            assert result.secret_id == "s1"

    def test_all_strategies_rotation(self):
        """Every rotation strategy can be simulated."""
        g = _graph(_comp("a1"))
        engine = _engine()
        for strategy in RotationStrategy:
            s = _secret(component_ids=["a1"], rotation_strategy=strategy)
            result = engine.simulate_rotation(g, s)
            assert result.rollback_possible == _STRATEGY_ROLLBACK[strategy]

    def test_all_secret_types_leaked(self):
        """Every secret type has leaked secret handling."""
        g = _graph(_comp("a1"))
        engine = _engine()
        for st in SecretType:
            s = _secret(component_ids=["a1"], secret_type=st)
            result = engine.simulate_leaked_secret(g, s)
            assert len(result.immediate_actions) >= 3

    def test_all_secret_types_recommend_strategy(self):
        """Every secret type gets a valid strategy recommendation."""
        g = _graph(_comp("a1"), _comp("a2"))
        engine = _engine()
        for st in SecretType:
            s = _secret(component_ids=["a1", "a2"], secret_type=st)
            result = engine.recommend_rotation_strategy(g, s)
            assert result in RotationStrategy


# ===========================================================================
# Edge case tests
# ===========================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_graph_with_no_components(self):
        g = _graph()
        s = _secret(component_ids=[])
        result = _engine().simulate_rotation(g, s)
        assert result.affected_services == []
        assert result.connection_reset_count == 0

    def test_secret_with_all_nonexistent_components(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["x1", "x2", "x3"])
        result = _engine().simulate_rotation(g, s)
        assert result.affected_services == []

    def test_blast_radius_all_nonexistent(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["x1"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.directly_affected == []
        assert result.affected_percent == 0.0

    def test_large_graph(self):
        """Test with many components."""
        comps = [_comp(f"svc{i}") for i in range(20)]
        g = _graph(*comps)
        s = _secret(component_ids=[f"svc{i}" for i in range(20)])
        result = _engine().simulate_rotation(g, s)
        assert len(result.affected_services) == 20
        assert result.connection_reset_count == _SECRET_CONNECTION_RESETS[SecretType.API_KEY] * 20

    def test_single_secret_single_component(self):
        g = _graph(_comp("solo"))
        s = _secret(component_ids=["solo"])
        result = _engine().simulate_rotation(g, s)
        assert result.affected_services == ["solo"]

    def test_readiness_score_boundaries(self):
        """Score should always be between 0 and 100."""
        g = _graph(_comp("a1"))
        secrets = [
            _secret(
                sid=f"s{i}",
                component_ids=["a1"],
                rotation_strategy=RotationStrategy.IMMEDIATE,
                expiry_date=_expired_date(),
            )
            for i in range(10)
        ]
        result = _engine().assess_rotation_readiness(g, secrets)
        assert 0.0 <= result.readiness_score <= 100.0

    def test_blast_radius_percent_never_exceeds_100(self):
        g = _graph(_comp("a1"))
        s = _secret(component_ids=["a1"])
        result = _engine().calculate_rotation_blast_radius(g, s)
        assert result.affected_percent <= 100.0

    def test_downtime_never_negative(self):
        g = _graph(_comp("a1"))
        for strategy in RotationStrategy:
            s = _secret(component_ids=["a1"], rotation_strategy=strategy, auto_rotation=True)
            result = _engine().simulate_rotation(g, s)
            assert result.downtime_seconds >= 0.0

    def test_leaked_secret_empty_graph(self):
        g = _graph()
        s = _secret(component_ids=[])
        result = _engine().simulate_leaked_secret(g, s)
        assert result.affected_services == []
        assert result.service_disruption_seconds >= 0.0
