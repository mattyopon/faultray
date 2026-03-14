"""Grafana integration for ChaosProof -- annotations and dashboards."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)


class GrafanaClient:
    """Client for Grafana HTTP API (annotations and dashboards)."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        username: str = "",
        password: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.username = username
        self.password = password

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _auth(self) -> tuple[str, str] | None:
        if self.username and self.password:
            return (self.username, self.password)
        return None

    async def create_annotation(
        self,
        text: str,
        tags: list[str] | None = None,
        dashboard_uid: str = "",
        panel_id: int = 0,
    ) -> dict:
        """Create a Grafana annotation (POST /api/annotations)."""
        now_ms = int(time.time() * 1000)
        payload: dict = {
            "text": text,
            "tags": tags or ["chaosproof", "simulation"],
            "time": now_ms,
        }
        if dashboard_uid:
            payload["dashboardUID"] = dashboard_uid
        if panel_id:
            payload["panelId"] = panel_id

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/annotations",
                headers=self._headers(),
                auth=self._auth(),
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def import_dashboard(self, dashboard_json: dict) -> dict:
        """Import a dashboard into Grafana (POST /api/dashboards/db)."""
        payload = {
            "dashboard": dashboard_json,
            "overwrite": True,
            "folderId": 0,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/api/dashboards/db",
                headers=self._headers(),
                auth=self._auth(),
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
