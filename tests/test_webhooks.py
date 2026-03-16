"""Tests for webhook integrations (Slack, PagerDuty, generic)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from faultray.integrations.webhooks import (
    send_generic_webhook,
    send_pagerduty_event,
    send_slack_notification,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def report_summary_critical():
    """A report summary with critical findings."""
    return {
        "resilience_score": 42.5,
        "total_scenarios": 10,
        "critical_count": 3,
        "warning_count": 2,
        "passed_count": 5,
    }


@pytest.fixture
def report_summary_clean():
    """A report summary with no critical findings."""
    return {
        "resilience_score": 95.0,
        "total_scenarios": 10,
        "critical_count": 0,
        "warning_count": 1,
        "passed_count": 9,
    }


# ---------------------------------------------------------------------------
# Slack tests
# ---------------------------------------------------------------------------

class TestSlackNotification:
    @pytest.mark.asyncio
    async def test_slack_success(self, report_summary_critical):
        """Slack notification should return True on 200."""
        mock_response = httpx.Response(200)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_slack_notification(
                "https://hooks.slack.com/test", report_summary_critical,
            )
            assert result is True
            client_instance.post.assert_called_once()

            # Verify blocks structure
            call_kwargs = client_instance.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert "blocks" in payload
            # Should have header + section + critical warning = 3 blocks
            assert len(payload["blocks"]) == 3

    @pytest.mark.asyncio
    async def test_slack_no_critical_has_two_blocks(self, report_summary_clean):
        """Slack notification without critical findings should have 2 blocks."""
        mock_response = httpx.Response(200)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_slack_notification(
                "https://hooks.slack.com/test", report_summary_clean,
            )
            assert result is True

            call_kwargs = client_instance.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert len(payload["blocks"]) == 2

    @pytest.mark.asyncio
    async def test_slack_failure(self, report_summary_critical):
        """Slack notification should return False on non-200."""
        mock_response = httpx.Response(500)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_slack_notification(
                "https://hooks.slack.com/test", report_summary_critical,
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_slack_network_error(self, report_summary_critical):
        """Slack notification should return False on network error."""
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.side_effect = httpx.ConnectError("connection refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_slack_notification(
                "https://hooks.slack.com/test", report_summary_critical,
            )
            assert result is False


# ---------------------------------------------------------------------------
# PagerDuty tests
# ---------------------------------------------------------------------------

class TestPagerDutyEvent:
    @pytest.mark.asyncio
    async def test_pagerduty_critical_triggers(self, report_summary_critical):
        """PagerDuty should send event when there are critical findings."""
        mock_response = httpx.Response(202)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_pagerduty_event("test-routing-key", report_summary_critical)
            assert result is True

            call_kwargs = client_instance.post.call_args
            url = call_kwargs.args[0] if call_kwargs.args else call_kwargs[0][0]
            assert "pagerduty.com" in url

            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["routing_key"] == "test-routing-key"
            assert payload["event_action"] == "trigger"
            assert payload["payload"]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_pagerduty_no_critical_skips(self, report_summary_clean):
        """PagerDuty should skip when there are no critical findings."""
        result = await send_pagerduty_event("test-routing-key", report_summary_clean)
        assert result is False

    @pytest.mark.asyncio
    async def test_pagerduty_failure(self, report_summary_critical):
        """PagerDuty should return False on non-202."""
        mock_response = httpx.Response(500)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_pagerduty_event("test-routing-key", report_summary_critical)
            assert result is False


# ---------------------------------------------------------------------------
# Generic webhook tests
# ---------------------------------------------------------------------------

class TestGenericWebhook:
    @pytest.mark.asyncio
    async def test_generic_success(self, report_summary_critical):
        """Generic webhook should return True on success status codes."""
        mock_response = httpx.Response(200)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_generic_webhook(
                "https://example.com/webhook", report_summary_critical,
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_generic_failure(self, report_summary_critical):
        """Generic webhook should return False on 4xx/5xx."""
        mock_response = httpx.Response(400)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_generic_webhook(
                "https://example.com/webhook", report_summary_critical,
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_generic_network_error(self, report_summary_critical):
        """Generic webhook should return False on network error."""
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.side_effect = httpx.TimeoutException("timeout")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_generic_webhook(
                "https://example.com/webhook", report_summary_critical,
            )
            assert result is False
