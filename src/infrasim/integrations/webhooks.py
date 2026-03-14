"""Webhook integrations for notifications."""
from __future__ import annotations

import json
import logging
import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    url: str
    type: str  # "slack", "pagerduty", "generic"


async def send_slack_notification(webhook_url: str, report_summary: dict) -> bool:
    """Send simulation results to Slack."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "ChaosProof Simulation Report"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Resilience Score:* {report_summary.get('resilience_score', 'N/A')}/100\n"
                    f"*Critical:* {report_summary.get('critical_count', 0)} | "
                    f"*Warning:* {report_summary.get('warning_count', 0)} | "
                    f"*Passed:* {report_summary.get('passed_count', 0)}"
                ),
            },
        },
    ]
    if report_summary.get("critical_count", 0) > 0:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        ":rotating_light: *Critical findings detected!* "
                        "Run `chaosproof analyze` for recommendations."
                    ),
                },
            }
        )

    payload = {"blocks": blocks}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=10)
            return resp.status_code == 200
    except Exception:
        logger.warning("Slack notification failed.", exc_info=True)
        return False


async def send_pagerduty_event(routing_key: str, report_summary: dict) -> bool:
    """Send PagerDuty event for critical findings."""
    if report_summary.get("critical_count", 0) == 0:
        return False  # Only alert on critical

    payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "payload": {
            "summary": (
                f"ChaosProof: {report_summary['critical_count']} "
                "critical infrastructure risks detected"
            ),
            "severity": "critical",
            "source": "chaosproof",
            "custom_details": report_summary,
        },
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=10,
            )
            return resp.status_code == 202
    except Exception:
        logger.warning("PagerDuty event failed.", exc_info=True)
        return False


async def send_generic_webhook(url: str, report_summary: dict) -> bool:
    """Send results to any webhook URL."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=report_summary, timeout=10)
            return resp.status_code < 400
    except Exception:
        logger.warning("Generic webhook failed.", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Microsoft Teams — Adaptive Card
# ---------------------------------------------------------------------------

async def send_teams(webhook_url: str, report_summary: dict) -> bool:
    """Send simulation results to Microsoft Teams via Adaptive Card webhook."""
    score = report_summary.get("resilience_score", "N/A")
    critical = report_summary.get("critical_count", 0)
    warning = report_summary.get("warning_count", 0)
    passed = report_summary.get("passed_count", 0)

    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Large",
                            "weight": "Bolder",
                            "text": "ChaosProof Simulation Report",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Resilience Score", "value": f"{score}/100"},
                                {"title": "Critical", "value": str(critical)},
                                {"title": "Warning", "value": str(warning)},
                                {"title": "Passed", "value": str(passed)},
                            ],
                        },
                    ],
                },
            }
        ],
    }

    if critical > 0:
        card["attachments"][0]["content"]["body"].append(
            {
                "type": "TextBlock",
                "text": "Critical findings detected! Run `chaosproof analyze` for recommendations.",
                "color": "Attention",
                "weight": "Bolder",
            }
        )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=card, timeout=10)
            return resp.status_code < 400
    except Exception:
        logger.warning("Teams notification failed.", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# SMTP Email
# ---------------------------------------------------------------------------

@dataclass
class SmtpConfig:
    """SMTP server configuration."""

    host: str = "localhost"
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    from_address: str = "chaosproof@localhost"


def send_email(
    smtp_config: SmtpConfig | dict,
    recipients: list[str],
    subject: str,
    body: str,
) -> bool:
    """Send an email via SMTP.

    Args:
        smtp_config: SMTP configuration (SmtpConfig or dict).
        recipients: List of email addresses.
        subject: Email subject line.
        body: Email body (plain text).

    Returns:
        True if the email was sent successfully.
    """
    if isinstance(smtp_config, dict):
        smtp_config = SmtpConfig(**smtp_config)

    if not recipients:
        logger.warning("No email recipients specified.")
        return False

    msg = MIMEMultipart()
    msg["From"] = smtp_config.from_address
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        if smtp_config.use_tls:
            server = smtplib.SMTP(smtp_config.host, smtp_config.port)
            server.ehlo()
            server.starttls()
        else:
            server = smtplib.SMTP(smtp_config.host, smtp_config.port)

        if smtp_config.username and smtp_config.password:
            server.login(smtp_config.username, smtp_config.password)

        server.sendmail(smtp_config.from_address, recipients, msg.as_string())
        server.quit()
        return True
    except Exception:
        logger.warning("Email notification failed.", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# OpsGenie
# ---------------------------------------------------------------------------

async def send_opsgenie(api_key: str, message: str, priority: str = "P3") -> bool:
    """Send an alert to OpsGenie.

    Args:
        api_key: OpsGenie API key.
        message: Alert message text.
        priority: Alert priority (P1-P5).

    Returns:
        True if the alert was created successfully.
    """
    valid_priorities = {"P1", "P2", "P3", "P4", "P5"}
    if priority not in valid_priorities:
        priority = "P3"

    payload = {
        "message": message,
        "priority": priority,
        "source": "ChaosProof",
        "tags": ["chaosproof", "infrastructure", "simulation"],
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.opsgenie.com/v2/alerts",
                json=payload,
                headers={
                    "Authorization": f"GenieKey {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            return resp.status_code in (200, 201, 202)
    except Exception:
        logger.warning("OpsGenie alert failed.", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Smart routing by severity
# ---------------------------------------------------------------------------

@dataclass
class NotificationConfig:
    """Configuration for severity-based notification routing."""

    pagerduty_key: str = ""
    slack_webhook: str = ""
    teams_webhook: str = ""
    opsgenie_key: str = ""
    smtp: SmtpConfig | dict = field(default_factory=SmtpConfig)
    recipients: list[str] = field(default_factory=list)


async def notify_by_severity(results: dict, config: NotificationConfig | dict) -> dict:
    """Route notifications based on severity.

    - Critical findings -> PagerDuty + OpsGenie
    - Warning findings  -> Slack + Teams
    - Always            -> Email (if configured)

    Args:
        results: Simulation report summary dict.
        config: NotificationConfig or dict.

    Returns:
        Dict with channel names as keys and success booleans as values.
    """
    if isinstance(config, dict):
        smtp_val = config.get("smtp", {})
        if isinstance(smtp_val, dict):
            config["smtp"] = SmtpConfig(**smtp_val)
        config = NotificationConfig(**config)

    statuses: dict[str, bool] = {}
    has_critical = results.get("critical_count", 0) > 0
    has_warning = results.get("warning_count", 0) > 0

    if has_critical:
        if config.pagerduty_key:
            statuses["pagerduty"] = await send_pagerduty_event(
                config.pagerduty_key, results
            )
        if config.opsgenie_key:
            message = (
                f"ChaosProof: {results.get('critical_count', 0)} "
                "critical infrastructure risks detected"
            )
            statuses["opsgenie"] = await send_opsgenie(
                config.opsgenie_key, message, priority="P1"
            )

    if has_warning or has_critical:
        if config.slack_webhook:
            statuses["slack"] = await send_slack_notification(
                config.slack_webhook, results
            )
        if config.teams_webhook:
            statuses["teams"] = await send_teams(
                config.teams_webhook, results
            )

    # Email is always sent if configured
    if config.recipients:
        score = results.get("resilience_score", "N/A")
        critical_count = results.get("critical_count", 0)
        warning_count = results.get("warning_count", 0)
        passed_count = results.get("passed_count", 0)
        subject = f"ChaosProof Report - Score: {score}/100"
        body = (
            f"ChaosProof Simulation Report\n"
            f"============================\n\n"
            f"Resilience Score: {score}/100\n"
            f"Critical: {critical_count}\n"
            f"Warning: {warning_count}\n"
            f"Passed: {passed_count}\n"
        )
        smtp_cfg = config.smtp
        statuses["email"] = send_email(smtp_cfg, config.recipients, subject, body)

    return statuses


# ---------------------------------------------------------------------------
# NotificationManager — unified multi-channel notification dispatch
# ---------------------------------------------------------------------------


class _SlackChannel:
    """Slack notification channel for NotificationManager."""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def send(self, title: str, summary: dict, severity: str = "info") -> bool:
        return await send_slack_notification(self.webhook_url, summary)


class _PagerDutyChannel:
    """PagerDuty notification channel for NotificationManager."""

    def __init__(self, routing_key: str) -> None:
        self.routing_key = routing_key

    async def send(self, title: str, summary: dict, severity: str = "info") -> bool:
        return await send_pagerduty_event(self.routing_key, summary)


class _OpsGenieChannel:
    """OpsGenie notification channel for NotificationManager."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def send(self, title: str, summary: dict, severity: str = "info") -> bool:
        priority_map = {"critical": "P1", "high": "P2", "warning": "P3", "info": "P4"}
        priority = priority_map.get(severity, "P3")
        return await send_opsgenie(self.api_key, title, priority=priority)


class _DatadogChannel:
    """Datadog notification channel for NotificationManager."""

    def __init__(self, api_key: str, app_key: str = "") -> None:
        self.api_key = api_key
        self.app_key = app_key

    async def send(self, title: str, summary: dict, severity: str = "info") -> bool:
        try:
            from infrasim.integrations.datadog import DatadogClient

            client = DatadogClient(self.api_key, self.app_key)
            await client.send_event(title, str(summary), alert_type=severity)
            return True
        except Exception:
            logger.warning("Datadog notification failed.", exc_info=True)
            return False


class NotificationManager:
    """Unified notification manager dispatching to all registered channels."""

    def __init__(self) -> None:
        self.channels: list = []

    def add_slack(self, webhook_url: str) -> None:
        self.channels.append(_SlackChannel(webhook_url))

    def add_pagerduty(self, routing_key: str) -> None:
        self.channels.append(_PagerDutyChannel(routing_key))

    def add_opsgenie(self, api_key: str) -> None:
        self.channels.append(_OpsGenieChannel(api_key))

    def add_datadog(self, api_key: str, app_key: str = "") -> None:
        self.channels.append(_DatadogChannel(api_key, app_key))

    async def notify_all(
        self, title: str, summary: dict, severity: str = "info",
    ) -> list:
        """Send notifications to all registered channels concurrently."""
        import asyncio

        if not self.channels:
            return []

        tasks = [ch.send(title, summary, severity) for ch in self.channels]
        return await asyncio.gather(*tasks, return_exceptions=True)
