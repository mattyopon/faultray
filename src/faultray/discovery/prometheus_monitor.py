# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Continuous Prometheus metrics monitoring for real-time InfraGraph updates."""

from __future__ import annotations

import asyncio
import logging

from faultray.discovery.prometheus import PrometheusClient
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


class PrometheusMonitor:
    """Continuously fetches metrics from Prometheus and updates the InfraGraph.

    Usage::

        monitor = PrometheusMonitor("http://prometheus:9090", graph, interval_seconds=60)
        await monitor.start()   # starts background polling
        ...
        await monitor.stop()    # graceful shutdown
    """

    def __init__(
        self,
        prometheus_url: str,
        graph: InfraGraph,
        interval_seconds: int = 60,
    ) -> None:
        self.client = PrometheusClient(prometheus_url)
        self.graph = graph
        self.interval = interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        """Whether the background poll loop is active."""
        return self._running

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            logger.warning("PrometheusMonitor is already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Prometheus monitor started (url=%s, interval=%ds)",
            self.client.url,
            self.interval,
        )

    async def stop(self) -> None:
        """Stop the background polling loop gracefully."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Prometheus monitor stopped")

    async def _poll_loop(self) -> None:
        """Internal loop — polls Prometheus at ``self.interval`` seconds."""
        while self._running:
            try:
                await self.client.update_metrics(self.graph)
                logger.debug(
                    "Metrics updated for %d components",
                    len(self.graph.components),
                )
            except Exception as exc:
                logger.warning("Prometheus poll failed: %s", exc)
            await asyncio.sleep(self.interval)

    async def poll_once(self) -> None:
        """Execute a single poll cycle (useful for testing)."""
        await self.client.update_metrics(self.graph)
