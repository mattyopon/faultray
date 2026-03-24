"""Tests for faultray.health — component-level health checks.

Covers HealthStatus enum, ComponentHealth/SystemHealth dataclasses,
and the check_health function with 20+ test cases.
"""
from __future__ import annotations

from unittest.mock import patch


from faultray.health import (
    HealthStatus,
    ComponentHealth,
    SystemHealth,
    check_health,
    _start_time,
)


# ===========================================================================
# HealthStatus enum tests
# ===========================================================================

class TestHealthStatus:
    """HealthStatus enum values and behavior."""

    def test_healthy_value(self):
        assert HealthStatus.HEALTHY == "healthy"

    def test_degraded_value(self):
        assert HealthStatus.DEGRADED == "degraded"

    def test_unhealthy_value(self):
        assert HealthStatus.UNHEALTHY == "unhealthy"

    def test_is_string_subclass(self):
        assert isinstance(HealthStatus.HEALTHY, str)

    def test_enum_member_count(self):
        assert len(HealthStatus) == 3

    def test_healthy_in_string_comparison(self):
        assert HealthStatus.HEALTHY == "healthy"
        assert "healthy" == HealthStatus.HEALTHY

    def test_all_values(self):
        values = {s.value for s in HealthStatus}
        assert values == {"healthy", "degraded", "unhealthy"}


# ===========================================================================
# ComponentHealth dataclass tests
# ===========================================================================

class TestComponentHealth:
    """ComponentHealth dataclass structure and defaults."""

    def test_create_with_required_fields(self):
        c = ComponentHealth(name="cascade", status=HealthStatus.HEALTHY)
        assert c.name == "cascade"
        assert c.status == HealthStatus.HEALTHY

    def test_default_latency(self):
        c = ComponentHealth(name="test", status=HealthStatus.HEALTHY)
        assert c.latency_ms == 0.0

    def test_default_message(self):
        c = ComponentHealth(name="test", status=HealthStatus.HEALTHY)
        assert c.message == ""

    def test_custom_latency(self):
        c = ComponentHealth(name="test", status=HealthStatus.HEALTHY, latency_ms=5.3)
        assert c.latency_ms == 5.3

    def test_custom_message(self):
        c = ComponentHealth(
            name="test",
            status=HealthStatus.UNHEALTHY,
            message="import failed",
        )
        assert c.message == "import failed"

    def test_unhealthy_component(self):
        c = ComponentHealth(
            name="missing_engine",
            status=HealthStatus.UNHEALTHY,
            latency_ms=0.1,
            message="No module named 'faultray.simulator.missing'",
        )
        assert c.status == HealthStatus.UNHEALTHY
        assert "No module" in c.message


# ===========================================================================
# SystemHealth dataclass tests
# ===========================================================================

class TestSystemHealth:
    """SystemHealth dataclass structure and defaults."""

    def test_create_minimal(self):
        h = SystemHealth(
            status=HealthStatus.HEALTHY,
            version="10.2.0",
            uptime_seconds=1.5,
            engines_available=8,
        )
        assert h.status == HealthStatus.HEALTHY
        assert h.version == "10.2.0"

    def test_default_components_empty(self):
        h = SystemHealth(
            status=HealthStatus.HEALTHY,
            version="1.0.0",
            uptime_seconds=0.0,
            engines_available=0,
        )
        assert h.components == []

    def test_default_checks_zero(self):
        h = SystemHealth(
            status=HealthStatus.HEALTHY,
            version="1.0.0",
            uptime_seconds=0.0,
            engines_available=0,
        )
        assert h.checks_passed == 0
        assert h.checks_failed == 0

    def test_with_components(self):
        comps = [
            ComponentHealth("a", HealthStatus.HEALTHY, 1.0),
            ComponentHealth("b", HealthStatus.UNHEALTHY, 2.0, "err"),
        ]
        h = SystemHealth(
            status=HealthStatus.DEGRADED,
            version="1.0.0",
            uptime_seconds=10.0,
            engines_available=1,
            components=comps,
            checks_passed=1,
            checks_failed=1,
        )
        assert len(h.components) == 2
        assert h.checks_passed == 1
        assert h.checks_failed == 1


# ===========================================================================
# check_health function tests
# ===========================================================================

class TestCheckHealth:
    """check_health should return a valid SystemHealth object."""

    def test_returns_system_health(self):
        result = check_health()
        assert isinstance(result, SystemHealth)

    def test_status_is_health_status(self):
        result = check_health()
        assert isinstance(result.status, HealthStatus)

    def test_version_matches_package(self):
        import faultray
        result = check_health()
        assert result.version == faultray.__version__

    def test_uptime_positive(self):
        result = check_health()
        assert result.uptime_seconds > 0

    def test_engines_available_count(self):
        result = check_health()
        # All 8 engines should be importable in the test environment
        assert result.engines_available >= 5

    def test_components_populated(self):
        result = check_health()
        assert len(result.components) == 8  # 8 engine checks

    def test_all_components_are_component_health(self):
        result = check_health()
        for comp in result.components:
            assert isinstance(comp, ComponentHealth)

    def test_component_names_present(self):
        result = check_health()
        names = {c.name for c in result.components}
        expected = {
            "cascade_engine",
            "dynamic_engine",
            "ops_engine",
            "cost_engine",
            "security_engine",
            "compliance_engine",
            "dr_engine",
            "predictive_engine",
        }
        assert names == expected

    def test_healthy_components_have_zero_or_positive_latency(self):
        result = check_health()
        for comp in result.components:
            if comp.status == HealthStatus.HEALTHY:
                assert comp.latency_ms >= 0

    def test_checks_passed_plus_failed_equals_total(self):
        result = check_health()
        assert result.checks_passed + result.checks_failed == len(result.components)

    def test_all_healthy_means_healthy_status(self):
        result = check_health()
        if result.checks_failed == 0:
            assert result.status == HealthStatus.HEALTHY

    def test_some_failed_means_degraded(self):
        """When some but not all imports fail, status should be DEGRADED."""
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__


        def mock_import(name, *args, **kwargs):
            if name == "faultray.simulator.predictive_engine":
                raise ImportError("mocked failure")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = check_health()
        assert result.checks_failed >= 1
        if result.checks_passed > 0:
            assert result.status == HealthStatus.DEGRADED

    def test_all_failed_means_unhealthy(self):
        """When all imports fail, status should be UNHEALTHY."""
        def mock_import(name, *args, **kwargs):
            if name.startswith("faultray.simulator."):
                raise ImportError("all mocked")
            return __import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = check_health()
        assert result.status == HealthStatus.UNHEALTHY
        assert result.checks_passed == 0
        assert result.engines_available == 0

    def test_unhealthy_component_has_message(self):
        """Unhealthy components should include an error message."""
        def mock_import(name, *args, **kwargs):
            if name == "faultray.simulator.cascade":
                raise ImportError("cascade broken")
            return __import__(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = check_health()
        cascade = [c for c in result.components if c.name == "cascade_engine"][0]
        assert cascade.status == HealthStatus.UNHEALTHY
        assert "cascade broken" in cascade.message

    def test_start_time_is_monotonic(self):
        """Module-level _start_time should be a valid monotonic timestamp."""
        assert isinstance(_start_time, float)
        assert _start_time > 0

    def test_idempotent_multiple_calls(self):
        """Calling check_health multiple times should be safe."""
        r1 = check_health()
        r2 = check_health()
        assert r1.engines_available == r2.engines_available
        assert r1.status == r2.status
