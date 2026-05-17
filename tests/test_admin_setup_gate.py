# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.
"""Regression tests for #140 — /setup must be gated.

Before #140 a fresh deployment exposed POST /setup on the public
internet, so whichever caller reached it first claimed permanent admin
access. ``_check_setup_allowed`` now refuses every non-loopback caller
unless they present a matching ``FAULTRAY_BOOTSTRAP_TOKEN``.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from faultray.api.server import app


@pytest.fixture
def client(monkeypatch):
    """TestClient simulates client.host = 'testclient' (non-loopback)."""
    monkeypatch.delenv("FAULTRAY_BOOTSTRAP_TOKEN", raising=False)
    return TestClient(app, raise_server_exceptions=False)


def test_get_setup_rejected_without_token_and_not_loopback(client):
    resp = client.get("/setup")
    assert resp.status_code == 403


def test_post_setup_rejected_without_token_and_not_loopback(client):
    resp = client.post(
        "/setup",
        data={"name": "X", "email": "x@example.com"},
    )
    assert resp.status_code == 403


def test_get_setup_rejected_with_wrong_token(monkeypatch):
    monkeypatch.setenv("FAULTRAY_BOOTSTRAP_TOKEN", "correct-token-value")
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.get("/setup", headers={"X-Setup-Token": "wrong-token"})
    assert resp.status_code == 403


def test_get_setup_rejected_with_empty_token_header(monkeypatch):
    monkeypatch.setenv("FAULTRAY_BOOTSTRAP_TOKEN", "correct-token-value")
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.get("/setup", headers={"X-Setup-Token": ""})
    assert resp.status_code == 403


def test_get_setup_accepted_with_correct_header_token(monkeypatch):
    monkeypatch.setenv("FAULTRAY_BOOTSTRAP_TOKEN", "correct-token-value")
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.get("/setup", headers={"X-Setup-Token": "correct-token-value"})
    # 200 (no users) or 302 (users exist) are both fine — the gate let us in.
    assert resp.status_code in {200, 302}


def test_get_setup_accepted_with_correct_query_token(monkeypatch):
    monkeypatch.setenv("FAULTRAY_BOOTSTRAP_TOKEN", "correct-token-value")
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.get("/setup?token=correct-token-value")
    assert resp.status_code in {200, 302}


def test_post_setup_rejected_with_wrong_token(monkeypatch):
    monkeypatch.setenv("FAULTRAY_BOOTSTRAP_TOKEN", "correct-token-value")
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.post(
        "/setup",
        data={"name": "X", "email": "x@example.com"},
        headers={"X-Setup-Token": "guess"},
    )
    assert resp.status_code == 403


def test_whitespace_only_env_treated_as_unset(monkeypatch):
    """FAULTRAY_BOOTSTRAP_TOKEN='   ' must not act as a valid secret."""
    monkeypatch.setenv("FAULTRAY_BOOTSTRAP_TOKEN", "   ")
    c = TestClient(app, raise_server_exceptions=False)
    # Stripped env -> no token configured, non-loopback client -> 403.
    resp = c.get("/setup")
    assert resp.status_code == 403
