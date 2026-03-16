"""Tests for the Prometheus continuous monitoring module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from faultray.discovery.prometheus_monitor import PrometheusMonitor
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_graph():
    return InfraGraph()


@pytest.fixture
def monitor(empty_graph):
    return PrometheusMonitor(
        prometheus_url="http://prometheus:9090",
        graph=empty_graph,
        interval_seconds=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPrometheusMonitorInit:
    def test_basic_init(self, empty_graph):
        mon = PrometheusMonitor("http://prom:9090", empty_graph, interval_seconds=30)
        assert mon.client.url == "http://prom:9090"
        assert mon.interval == 30
        assert mon.running is False
        assert mon.graph is empty_graph


class TestPrometheusMonitorStartStop:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, monitor):
        with patch.object(monitor.client, "update_metrics", new_callable=AsyncMock) as mock_update:
            await monitor.start()
            assert monitor.running is True
            assert monitor._task is not None

            # Give the poll loop a moment to run at least once
            await asyncio.sleep(0.1)

            await monitor.stop()
            assert monitor.running is False
            assert monitor._task is None

            # update_metrics should have been called at least once
            assert mock_update.call_count >= 1

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, monitor):
        """Stopping a monitor that never started should not raise."""
        await monitor.stop()
        assert monitor.running is False

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self, monitor):
        with patch.object(monitor.client, "update_metrics", new_callable=AsyncMock):
            await monitor.start()
            first_task = monitor._task
            await monitor.start()  # should warn but not crash
            assert monitor._task is first_task  # same task
            await monitor.stop()


class TestPrometheusMonitorPollOnce:
    @pytest.mark.asyncio
    async def test_poll_once_calls_update(self, monitor):
        with patch.object(monitor.client, "update_metrics", new_callable=AsyncMock) as mock_update:
            await monitor.poll_once()
            mock_update.assert_awaited_once_with(monitor.graph)

    @pytest.mark.asyncio
    async def test_poll_once_propagates_errors(self, monitor):
        with patch.object(
            monitor.client,
            "update_metrics",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ):
            with pytest.raises(RuntimeError, match="connection refused"):
                await monitor.poll_once()


class TestPrometheusMonitorPollLoop:
    @pytest.mark.asyncio
    async def test_poll_loop_tolerates_errors(self, empty_graph):
        """The background loop should log warnings but keep running on errors."""
        monitor = PrometheusMonitor("http://prom:9090", empty_graph, interval_seconds=0)

        call_count = 0

        async def flaky_update(graph):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")
            # Succeed on subsequent calls

        with patch.object(monitor.client, "update_metrics", side_effect=flaky_update):
            await monitor.start()
            await asyncio.sleep(0.15)  # Give time for a couple of iterations
            await monitor.stop()

        # Should have been called at least twice (one fail, one success)
        assert call_count >= 2
