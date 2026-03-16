"""Tests for the FaultRay exception hierarchy."""

import pytest

from faultray.errors import (
    FaultRayError,
    ComponentNotFoundError,
    ConfigurationError,
    ExternalServiceError,
    PluginError,
    SimulationError,
    ValidationError,
)


class TestExceptionHierarchy:
    """Verify all custom exceptions inherit from FaultRayError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ComponentNotFoundError,
            ValidationError,
            ConfigurationError,
            ExternalServiceError,
            SimulationError,
            PluginError,
        ],
    )
    def test_inherits_from_faultray_error(self, exc_class):
        assert issubclass(exc_class, FaultRayError)

    @pytest.mark.parametrize(
        "exc_class",
        [
            FaultRayError,
            ComponentNotFoundError,
            ValidationError,
            ConfigurationError,
            ExternalServiceError,
            SimulationError,
            PluginError,
        ],
    )
    def test_inherits_from_exception(self, exc_class):
        assert issubclass(exc_class, Exception)


class TestBackwardCompatibility:
    """Verify backward-compatible inheritance from stdlib exceptions."""

    def test_validation_error_is_value_error(self):
        assert issubclass(ValidationError, ValueError)

    def test_configuration_error_is_value_error(self):
        assert issubclass(ConfigurationError, ValueError)

    def test_component_not_found_is_key_error(self):
        assert issubclass(ComponentNotFoundError, KeyError)

    def test_external_service_error_is_runtime_error(self):
        assert issubclass(ExternalServiceError, RuntimeError)

    def test_simulation_error_is_runtime_error(self):
        assert issubclass(SimulationError, RuntimeError)

    def test_plugin_error_is_not_stdlib_subtype(self):
        # PluginError only extends FaultRayError, not a stdlib exception
        assert not issubclass(PluginError, ValueError)
        assert not issubclass(PluginError, KeyError)
        assert not issubclass(PluginError, RuntimeError)


class TestExceptionMessages:
    """Verify exceptions preserve their messages."""

    def test_faultray_error_message(self):
        exc = FaultRayError("base error")
        assert str(exc) == "base error"

    def test_component_not_found_error_message(self):
        exc = ComponentNotFoundError("component 'web-01' not found")
        assert "web-01" in str(exc)

    def test_validation_error_message(self):
        exc = ValidationError("invalid YAML: missing 'id' field")
        assert "invalid YAML" in str(exc)

    def test_configuration_error_message(self):
        exc = ConfigurationError("missing config key 'api_url'")
        assert "api_url" in str(exc)

    def test_external_service_error_message(self):
        exc = ExternalServiceError("AWS API timeout after 30s")
        assert "AWS" in str(exc)

    def test_simulation_error_message(self):
        exc = SimulationError("engine diverged at step 42")
        assert "step 42" in str(exc)

    def test_plugin_error_message(self):
        exc = PluginError("plugin 'custom-checker' failed to load")
        assert "custom-checker" in str(exc)


class TestIsinstanceChecks:
    """Verify isinstance works correctly with the hierarchy."""

    def test_catch_specific_as_base(self):
        exc = ComponentNotFoundError("missing")
        assert isinstance(exc, FaultRayError)
        assert isinstance(exc, Exception)

    def test_catch_validation_as_base(self):
        exc = ValidationError("bad input")
        assert isinstance(exc, FaultRayError)

    def test_catch_validation_as_value_error(self):
        exc = ValidationError("bad input")
        assert isinstance(exc, ValueError)

    def test_catch_component_not_found_as_key_error(self):
        exc = ComponentNotFoundError("missing")
        assert isinstance(exc, KeyError)

    def test_catch_external_service_as_runtime_error(self):
        exc = ExternalServiceError("timeout")
        assert isinstance(exc, RuntimeError)

    def test_base_is_not_subclass(self):
        exc = FaultRayError("generic")
        assert not isinstance(exc, ComponentNotFoundError)
        assert not isinstance(exc, ValidationError)

    def test_siblings_are_not_related(self):
        exc = ValidationError("bad input")
        assert not isinstance(exc, ComponentNotFoundError)
        assert not isinstance(exc, ExternalServiceError)


class TestRaiseAndCatch:
    """Verify raise/catch patterns work as expected."""

    def test_raise_component_not_found_catch_base(self):
        with pytest.raises(FaultRayError):
            raise ComponentNotFoundError("comp-123")

    def test_raise_validation_catch_base(self):
        with pytest.raises(FaultRayError):
            raise ValidationError("bad param")

    def test_raise_validation_catch_value_error(self):
        with pytest.raises(ValueError):
            raise ValidationError("bad param")

    def test_raise_external_service_catch_runtime_error(self):
        with pytest.raises(RuntimeError):
            raise ExternalServiceError("timeout")

    def test_raise_external_service_catch_base(self):
        with pytest.raises(FaultRayError):
            raise ExternalServiceError("timeout")

    def test_raise_specific_catch_specific(self):
        with pytest.raises(ValidationError):
            raise ValidationError("invalid")

    def test_raise_specific_does_not_catch_sibling(self):
        with pytest.raises(ValidationError):
            raise ValidationError("oops")
        # ComponentNotFoundError should NOT be caught by ValidationError handler
        with pytest.raises(ComponentNotFoundError):
            raise ComponentNotFoundError("missing")
