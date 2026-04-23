"""Regression: CLI deprecation warning mechanism (#86)."""

from __future__ import annotations

import warnings

import pytest

from faultray.cli.deprecation import (
    FaultRayDeprecationWarning,
    deprecated_command,
    warn_deprecated_option,
)


def test_deprecated_command_emits_warning_on_call(capsys):
    @deprecated_command(reason="Use `foo` instead", removed_in="12.0.0")
    def _cmd(x):
        return x * 2

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", FaultRayDeprecationWarning)
        result = _cmd(3)

    assert result == 6
    err = capsys.readouterr().err
    assert "[DEPRECATION]" in err
    assert "v12.0.0" in err
    assert "Use `foo` instead" in err

    assert any(issubclass(rec.category, FaultRayDeprecationWarning) for rec in w)


def test_deprecation_metadata_attached():
    @deprecated_command(reason="Use `new` instead", removed_in="12.0.0")
    def _cmd():
        pass

    meta = getattr(_cmd, "__faultray_deprecated__", None)
    assert meta is not None
    assert meta["removed_in"] == "12.0.0"
    assert meta["reason"].startswith("Use")


def test_suppress_env_silences_warning(capsys, monkeypatch):
    monkeypatch.setenv("FAULTRAY_SUPPRESS_DEPRECATION", "1")

    @deprecated_command(reason="gone", removed_in="12.0.0")
    def _cmd():
        return 7

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", FaultRayDeprecationWarning)
        _cmd()

    err = capsys.readouterr().err
    assert "[DEPRECATION]" not in err
    assert not any(issubclass(rec.category, FaultRayDeprecationWarning) for rec in w)


def test_warn_deprecated_option_imperative(capsys, monkeypatch):
    monkeypatch.delenv("FAULTRAY_SUPPRESS_DEPRECATION", raising=False)
    warn_deprecated_option(
        "--old-flag", reason="Use --new-flag", removed_in="12.0.0"
    )
    err = capsys.readouterr().err
    assert "[DEPRECATION]" in err
    assert "--old-flag" in err


def test_custom_name_override(capsys):
    @deprecated_command(reason="gone", removed_in="12.0.0", name="legacy-foo")
    def some_internal_function():
        pass

    some_internal_function()
    err = capsys.readouterr().err
    assert "legacy-foo" in err
