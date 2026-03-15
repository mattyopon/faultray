"""Datadog integration for FaultZero -- events and custom metrics."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)


class DatadogClient:
    """Client for Datadog Events and Metrics APIs."""

    def __init__(
        self,
        api_key: str,
        app_key: str = "",
        base_url: str = "https://api.datadoghq.com",
    ) -> None:
        self.api_key = api_key
        self.app_key = app_key
        self.base_url = base_url

    def _headers(self) -> dict[str, str]:
        headers = {
            "DD-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        if self.app_key:
            headers["DD-APPLICATION-KEY"] = self.app_key
        return headers

    async def send_event(
        self,
        title: str,
        text: str,
        alert_type: str = "info",
        tags: list[str] | None = None,
    ) -> dict:
        """Send a simulation event to Datadog (POST /api/v1/events)."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/events",
                headers=self._headers(),
                json={
                    "title": title,
                    "text": text,
                    "alert_type": alert_type,
                    "tags": tags or ["source:faultzero"],
                    "source_type_name": "faultzero",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def submit_metrics(
        self,
        resilience_score: float,
        security_score: float = 0.0,
        risk_exposure: float = 0.0,
        tags: list[str] | None = None,
    ) -> dict:
        """Submit custom metrics to Datadog (POST /api/v2/series)."""
        now = int(time.time())
        metric_tags = tags or ["source:faultzero"]

        series = [
            {
                "metric": "faultzero.resilience_score",
                "type": 3,  # gauge
                "points": [{"timestamp": now, "value": resilience_score}],
                "tags": metric_tags,
            },
            {
                "metric": "faultzero.security_score",
                "type": 3,
                "points": [{"timestamp": now, "value": security_score}],
                "tags": metric_tags,
            },
            {
                "metric": "faultzero.risk_exposure",
                "type": 3,
                "points": [{"timestamp": now, "value": risk_exposure}],
                "tags": metric_tags,
            },
        ]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/v2/series",
                headers=self._headers(),
                json={"series": series},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_metrics(
        self,
        query: str,
        from_ts: int = 0,
        to_ts: int = 0,
    ) -> dict:
        """Fetch metrics from Datadog (GET /api/v1/query)."""
        now = int(time.time())
        if not from_ts:
            from_ts = now - 3600
        if not to_ts:
            to_ts = now

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/v1/query",
                headers=self._headers(),
                params={"from": from_ts, "to": to_ts, "query": query},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
