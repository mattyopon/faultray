"""OpsGenie alert integration for FaultRay."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class OpsGenieClient:
    """Full-featured OpsGenie alert client."""

    def __init__(self, api_key: str, base_url: str = "https://api.opsgenie.com") -> None:
        self.api_key = api_key
        self.base_url = base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"GenieKey {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_alert(
        self,
        message: str,
        description: str = "",
        priority: str = "P3",
        tags: list[str] | None = None,
        details: dict | None = None,
    ) -> dict:
        """Create a new OpsGenie alert."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v2/alerts",
                headers=self._headers(),
                json={
                    "message": message,
                    "description": description,
                    "priority": priority,
                    "tags": tags or ["faultray"],
                    "details": details or {},
                    "source": "FaultRay",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()

    async def close_alert(self, alert_id: str, note: str = "") -> dict:
        """Close an existing OpsGenie alert."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v2/alerts/{alert_id}/close",
                headers=self._headers(),
                json={"note": note or "Closed by FaultRay"},
                timeout=10.0,
            )
            resp.raise_for_status()
            return resp.json()
