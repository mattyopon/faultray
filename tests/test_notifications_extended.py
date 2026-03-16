"""Tests for extended notification integrations (Teams, Email, OpsGenie, smart routing)."""

from __future__ import annotations

import smtplib
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from faultray.integrations.webhooks import (
    NotificationConfig,
    SmtpConfig,
    notify_by_severity,
    send_email,
    send_opsgenie,
    send_teams,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def report_summary_critical():
    return {
        "resilience_score": 42.5,
        "total_scenarios": 10,
        "critical_count": 3,
        "warning_count": 2,
        "passed_count": 5,
    }


@pytest.fixture
def report_summary_warning():
    return {
        "resilience_score": 75.0,
        "total_scenarios": 10,
        "critical_count": 0,
        "warning_count": 3,
        "passed_count": 7,
    }


@pytest.fixture
def report_summary_clean():
    return {
        "resilience_score": 95.0,
        "total_scenarios": 10,
        "critical_count": 0,
        "warning_count": 0,
        "passed_count": 10,
    }


# ---------------------------------------------------------------------------
# Microsoft Teams tests
# ---------------------------------------------------------------------------


class TestTeamsNotification:
    @pytest.mark.asyncio
    async def test_teams_success(self, report_summary_critical):
        """Teams notification should return True on success."""
        mock_response = httpx.Response(200)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_teams(
                "https://outlook.office.com/webhook/test",
                report_summary_critical,
            )
            assert result is True
            client_instance.post.assert_called_once()

            # Verify Adaptive Card structure
            call_kwargs = client_instance.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["type"] == "message"
            assert len(payload["attachments"]) == 1
            card = payload["attachments"][0]["content"]
            assert card["type"] == "AdaptiveCard"
            # Should have critical warning block since critical_count > 0
            assert len(card["body"]) == 3  # title + facts + critical warning

    @pytest.mark.asyncio
    async def test_teams_no_critical(self, report_summary_clean):
        """Teams card without critical findings should have 2 body blocks."""
        mock_response = httpx.Response(200)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_teams(
                "https://outlook.office.com/webhook/test",
                report_summary_clean,
            )
            assert result is True
            call_kwargs = client_instance.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            card = payload["attachments"][0]["content"]
            assert len(card["body"]) == 2  # title + facts only

    @pytest.mark.asyncio
    async def test_teams_failure(self, report_summary_critical):
        """Teams notification should return False on error."""
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.side_effect = httpx.ConnectError("refused")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_teams(
                "https://outlook.office.com/webhook/test",
                report_summary_critical,
            )
            assert result is False


# ---------------------------------------------------------------------------
# Email tests
# ---------------------------------------------------------------------------


class TestEmailNotification:
    def test_email_success(self):
        """send_email should return True when SMTP succeeds."""
        config = SmtpConfig(
            host="smtp.test.com",
            port=587,
            username="user",
            password="pass",
            use_tls=True,
            from_address="test@test.com",
        )

        with patch("faultray.integrations.webhooks.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value = mock_server

            result = send_email(
                config,
                ["recipient@test.com"],
                "Test Subject",
                "Test body",
            )
            assert result is True
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("user", "pass")
            mock_server.sendmail.assert_called_once()
            mock_server.quit.assert_called_once()

    def test_email_no_tls(self):
        """send_email with use_tls=False should skip starttls."""
        config = SmtpConfig(host="smtp.test.com", port=25, use_tls=False)

        with patch("faultray.integrations.webhooks.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value = mock_server

            result = send_email(
                config,
                ["recipient@test.com"],
                "Test",
                "Body",
            )
            assert result is True
            mock_server.starttls.assert_not_called()

    def test_email_no_recipients(self):
        """send_email with empty recipients should return False."""
        config = SmtpConfig()
        result = send_email(config, [], "Test", "Body")
        assert result is False

    def test_email_connection_error(self):
        """send_email should return False on SMTP error."""
        config = SmtpConfig(host="nonexistent.invalid")

        with patch("faultray.integrations.webhooks.smtplib.SMTP") as MockSMTP:
            MockSMTP.side_effect = smtplib.SMTPConnectError(421, "Connection refused")

            result = send_email(config, ["test@test.com"], "Test", "Body")
            assert result is False

    def test_email_from_dict(self):
        """send_email should accept config as dict."""
        config_dict = {
            "host": "smtp.test.com",
            "port": 587,
            "username": "user",
            "password": "pass",
        }

        with patch("faultray.integrations.webhooks.smtplib.SMTP") as MockSMTP:
            mock_server = MagicMock()
            MockSMTP.return_value = mock_server

            result = send_email(config_dict, ["test@test.com"], "Test", "Body")
            assert result is True


# ---------------------------------------------------------------------------
# OpsGenie tests
# ---------------------------------------------------------------------------


class TestOpsGenieNotification:
    @pytest.mark.asyncio
    async def test_opsgenie_success(self):
        """OpsGenie alert should return True on 202."""
        mock_response = httpx.Response(202)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_opsgenie(
                "test-api-key",
                "Critical infrastructure risk",
                priority="P1",
            )
            assert result is True

            call_kwargs = client_instance.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["priority"] == "P1"
            assert "FaultRay" in payload["source"]

            # Verify auth header
            headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
            assert "GenieKey test-api-key" in headers["Authorization"]

    @pytest.mark.asyncio
    async def test_opsgenie_invalid_priority_defaults(self):
        """Invalid priority should default to P3."""
        mock_response = httpx.Response(202)
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.return_value = mock_response
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_opsgenie("key", "msg", priority="INVALID")
            assert result is True

            call_kwargs = client_instance.post.call_args
            payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
            assert payload["priority"] == "P3"

    @pytest.mark.asyncio
    async def test_opsgenie_failure(self):
        """OpsGenie alert should return False on error."""
        with patch("faultray.integrations.webhooks.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            client_instance.post.side_effect = httpx.TimeoutException("timeout")
            MockClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await send_opsgenie("key", "msg")
            assert result is False


# ---------------------------------------------------------------------------
# Smart routing tests
# ---------------------------------------------------------------------------


class TestNotifyBySeverity:
    @pytest.mark.asyncio
    async def test_critical_routes_to_pagerduty(self, report_summary_critical):
        """Critical findings should route to PagerDuty."""
        config = NotificationConfig(
            pagerduty_key="test-key",
            slack_webhook="https://slack.test/webhook",
        )

        with patch("faultray.integrations.webhooks.send_pagerduty_event", new_callable=AsyncMock) as mock_pd, \
             patch("faultray.integrations.webhooks.send_slack_notification", new_callable=AsyncMock) as mock_slack:
            mock_pd.return_value = True
            mock_slack.return_value = True

            statuses = await notify_by_severity(report_summary_critical, config)

            assert statuses["pagerduty"] is True
            assert statuses["slack"] is True
            mock_pd.assert_called_once()
            mock_slack.assert_called_once()

    @pytest.mark.asyncio
    async def test_warning_skips_pagerduty(self, report_summary_warning):
        """Warning-only findings should not trigger PagerDuty."""
        config = NotificationConfig(
            pagerduty_key="test-key",
            slack_webhook="https://slack.test/webhook",
        )

        with patch("faultray.integrations.webhooks.send_pagerduty_event", new_callable=AsyncMock) as mock_pd, \
             patch("faultray.integrations.webhooks.send_slack_notification", new_callable=AsyncMock) as mock_slack:
            mock_slack.return_value = True

            statuses = await notify_by_severity(report_summary_warning, config)

            assert "pagerduty" not in statuses
            assert statuses["slack"] is True
            mock_pd.assert_not_called()

    @pytest.mark.asyncio
    async def test_email_always_sent(self, report_summary_clean):
        """Email should always be sent if recipients are configured."""
        config = NotificationConfig(
            recipients=["admin@test.com"],
            smtp=SmtpConfig(host="smtp.test.com"),
        )

        with patch("faultray.integrations.webhooks.send_email") as mock_email:
            mock_email.return_value = True

            statuses = await notify_by_severity(report_summary_clean, config)

            assert statuses["email"] is True
            mock_email.assert_called_once()
