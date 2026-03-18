"""Tests for the embeddable widget endpoints."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from tests.conftest import TEST_API_KEY, _setup_test_user


@pytest.fixture
def client():
    """Create a test client for the FaultRay API."""
    from faultray.api.server import app
    _setup_test_user()
    return TestClient(app, raise_server_exceptions=False, headers={"Authorization": f"Bearer {TEST_API_KEY}"})


class TestScorecardWidget:
    """Test the scorecard widget endpoint."""

    def test_scorecard_returns_html(self, client):
        resp = client.get("/widget/scorecard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "FaultRay" in resp.text

    def test_scorecard_contains_score(self, client):
        resp = client.get("/widget/scorecard")
        assert "/100" in resp.text

    def test_scorecard_accepts_project_id(self, client):
        resp = client.get("/widget/scorecard?project_id=myproject")
        assert resp.status_code == 200
        assert "myproject" in resp.text

    def test_scorecard_default_project_id(self, client):
        resp = client.get("/widget/scorecard")
        assert "default" in resp.text


class TestEmbedScript:
    """Test the JavaScript embed script endpoint."""

    def test_embed_js_returns_javascript(self, client):
        resp = client.get("/widget/embed.js")
        assert resp.status_code == 200
        assert "javascript" in resp.headers["content-type"]
        assert "FaultRay" in resp.text
        assert "renderCard" in resp.text

    def test_embed_js_creates_iframe(self, client):
        resp = client.get("/widget/embed.js")
        assert "iframe" in resp.text


class TestBadgeEndpoint:
    """Test the shields.io badge endpoint."""

    def test_badge_returns_json(self, client):
        resp = client.get("/widget/badge")
        assert resp.status_code == 200
        data = resp.json()
        assert data["schemaVersion"] == 1
        assert data["label"] == "FaultRay"
        assert "/100" in data["message"]
        assert data["color"] in ("brightgreen", "yellow", "red")

    def test_badge_accepts_project_id(self, client):
        resp = client.get("/widget/badge?project_id=test")
        assert resp.status_code == 200


class TestGetScoreAndStatus:
    """Test the internal score/status helper."""

    def test_no_infrastructure_returns_zero(self):
        from faultray.api.widget import _get_score_and_status

        with patch("faultray.api.server._graph", None), \
             patch("faultray.api.server._last_report", None):
            score, status, color = _get_score_and_status()
            assert score == 0.0
            assert status == "No infrastructure loaded"
