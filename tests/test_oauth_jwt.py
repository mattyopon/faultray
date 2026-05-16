# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.
"""Regression tests for the JWT signing hardening (#137).

Before #137 the JWT layer fell open in two independent ways: a publicly
known default secret, and an ``ImportError`` branch that issued and
accepted unsigned base64 JSON tokens whenever python-jose was missing.
These tests pin the new fail-closed contract.
"""
from __future__ import annotations

import pytest

from faultray.api import oauth


@pytest.fixture(autouse=True)
def _clear_jwt_env(monkeypatch):
    monkeypatch.delenv("FAULTRAY_JWT_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)


def test_require_jwt_secret_raises_when_unset() -> None:
    with pytest.raises(RuntimeError, match="JWT signing secret is not configured"):
        oauth._require_jwt_secret()


@pytest.mark.parametrize(
    "sentinel",
    [
        "faultray-dev-secret-change-me",
        "change-me",
        "REPLACE_ME",
        "secret",
        "",
    ],
)
def test_require_jwt_secret_rejects_known_insecure_values(monkeypatch, sentinel: str) -> None:
    monkeypatch.setenv("FAULTRAY_JWT_SECRET", sentinel)
    with pytest.raises(RuntimeError, match="not configured"):
        oauth._require_jwt_secret()


def test_require_jwt_secret_rejects_short_value(monkeypatch) -> None:
    monkeypatch.setenv("FAULTRAY_JWT_SECRET", "x" * 31)
    with pytest.raises(RuntimeError, match="too short"):
        oauth._require_jwt_secret()


def test_require_jwt_secret_accepts_strong_value(monkeypatch) -> None:
    secret = "x" * 64
    monkeypatch.setenv("FAULTRAY_JWT_SECRET", secret)
    assert oauth._require_jwt_secret() == secret


def test_create_jwt_refuses_without_secret() -> None:
    with pytest.raises(RuntimeError):
        oauth.create_jwt({"sub": "u1"})


def test_decode_jwt_refuses_without_secret() -> None:
    with pytest.raises(RuntimeError):
        oauth.decode_jwt("not-a-token")


def test_signed_token_roundtrip(monkeypatch) -> None:
    monkeypatch.setenv("FAULTRAY_JWT_SECRET", "z" * 64)
    token = oauth.create_jwt({"sub": "user-123"})
    # Real JWT shape: three base64url segments separated by dots.
    assert token.count(".") == 2
    decoded = oauth.decode_jwt(token)
    assert decoded is not None
    assert decoded["sub"] == "user-123"


def test_decode_jwt_rejects_forgery_with_different_secret(monkeypatch) -> None:
    monkeypatch.setenv("FAULTRAY_JWT_SECRET", "a" * 64)
    token = oauth.create_jwt({"sub": "victim"})

    monkeypatch.setenv("FAULTRAY_JWT_SECRET", "b" * 64)
    # Same token, different signing key — must fail verification.
    assert oauth.decode_jwt(token) is None


def test_decode_jwt_rejects_base64_only_payload(monkeypatch) -> None:
    """#137: a bare base64-encoded JSON blob must NOT validate as a JWT.

    The old ImportError path treated such blobs as valid sessions if the
    payload had an unexpired ``exp``. Now even a perfectly-shaped fake
    must be rejected.
    """
    import base64
    import json
    import time

    monkeypatch.setenv("FAULTRAY_JWT_SECRET", "c" * 64)
    forged = base64.urlsafe_b64encode(
        json.dumps({"sub": "admin", "exp": int(time.time()) + 3600}).encode()
    ).decode()
    assert oauth.decode_jwt(forged) is None
