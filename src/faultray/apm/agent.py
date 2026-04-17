# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""FaultRay APM Agent — lightweight daemon for host/process metrics collection.

The agent runs as a background process on monitored servers, periodically
collecting system metrics via ``psutil`` and sending batches to the
FaultRay Collector API.

Usage::

    agent = APMAgent(config)
    agent.start()       # blocks until SIGINT/SIGTERM
    # or
    await agent.run()   # async entry-point
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import signal
import socket
import time
from pathlib import Path

import httpx
import psutil

from faultray.apm.models import (
    AgentConfig,
    ConnectionInfo,
    HostMetrics,
    MetricsBatch,
    ProcessInfo,
)

logger = logging.getLogger(__name__)

_VERSION = "1.0.0"


class APMAgent:
    """APM agent daemon that collects and ships metrics."""

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        self._running = False
        self._start_time: float = 0.0
        self._metrics_buffer: list[MetricsBatch] = []
        self._send_lock = asyncio.Lock()
        self._hostname = socket.gethostname()
        self._ip_address = _get_local_ip()
        self._os_info = f"{platform.system()} {platform.release()}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Synchronous entry-point — blocks until stopped."""
        asyncio.run(self.run())

    async def run(self) -> None:
        """Async entry-point — register, collect, send loop."""
        self._running = True
        self._start_time = time.monotonic()

        # Install signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._request_stop)

        logger.info(
            "FaultRay APM Agent starting (id=%s, collector=%s, interval=%ds)",
            self.config.agent_id,
            self.config.collector_url,
            self.config.collect_interval_seconds,
        )

        # Write PID file
        self._write_pid_file()

        # Register with collector
        await self._register()

        # Main loop
        collect_task = asyncio.create_task(self._collect_loop())
        send_task = asyncio.create_task(self._send_loop())
        discovery_task = asyncio.create_task(self._discovery_loop())

        try:
            await asyncio.gather(collect_task, send_task, discovery_task)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            await self._deregister()
            self._remove_pid_file()
            logger.info("FaultRay APM Agent stopped (id=%s)", self.config.agent_id)

    def stop(self) -> None:
        """Request graceful shutdown."""
        self._request_stop()

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def collect_host_metrics(self) -> HostMetrics:
        """Collect system-wide host metrics using psutil."""
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        try:
            load = os.getloadavg()
        except (OSError, AttributeError):
            load = (0.0, 0.0, 0.0)

        return HostMetrics(
            cpu_percent=psutil.cpu_percent(interval=0),
            cpu_count=psutil.cpu_count() or 1,
            memory_percent=vm.percent,
            memory_used_mb=vm.used / (1024 * 1024),
            memory_total_mb=vm.total / (1024 * 1024),
            disk_percent=disk.percent,
            disk_used_gb=disk.used / (1024**3),
            disk_total_gb=disk.total / (1024**3),
            network_bytes_sent=net.bytes_sent,
            network_bytes_recv=net.bytes_recv,
            network_connections=len(psutil.net_connections(kind="inet")),
            load_avg_1m=load[0],
            load_avg_5m=load[1],
            load_avg_15m=load[2],
        )

    def collect_processes(self) -> list[ProcessInfo]:
        """Collect process information. Filters by config patterns if set."""
        procs: list[ProcessInfo] = []
        filters = self.config.process_filter

        for proc in psutil.process_iter(
            ["pid", "name", "cmdline", "cpu_percent", "memory_percent",
             "memory_info", "status", "create_time", "num_threads"]
        ):
            try:
                info = proc.info
                name = info.get("name", "") or ""

                # Apply filter
                if filters and not any(f.lower() in name.lower() for f in filters):
                    continue

                cmdline_parts = info.get("cmdline") or []
                cmdline = " ".join(cmdline_parts) if cmdline_parts else ""
                mem_info = info.get("memory_info")
                rss_mb = (mem_info.rss / (1024 * 1024)) if mem_info else 0.0

                proc_conns: list[ConnectionInfo] = []
                if self.config.collect_connections:
                    try:
                        for c in proc.net_connections(kind="inet"):
                            proc_conns.append(ConnectionInfo(
                                local_addr=c.laddr.ip if c.laddr else "",
                                local_port=c.laddr.port if c.laddr else 0,
                                remote_addr=c.raddr.ip if c.raddr else "",
                                remote_port=c.raddr.port if c.raddr else 0,
                                status=c.status if c.status else "",
                                pid=info.get("pid"),
                            ))
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        pass

                procs.append(ProcessInfo(
                    pid=info.get("pid", 0),
                    name=name,
                    cmdline=cmdline[:500],  # truncate long cmdlines
                    cpu_percent=info.get("cpu_percent", 0.0) or 0.0,
                    memory_percent=info.get("memory_percent", 0.0) or 0.0,
                    memory_rss_mb=rss_mb,
                    status=info.get("status", ""),
                    create_time=info.get("create_time", 0.0) or 0.0,
                    num_threads=info.get("num_threads", 0) or 0,
                    connections=proc_conns,
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return procs

    def collect_connections(self) -> list[ConnectionInfo]:
        """Collect system-wide network connections."""
        conns: list[ConnectionInfo] = []
        try:
            for c in psutil.net_connections(kind="inet"):
                conns.append(ConnectionInfo(
                    local_addr=c.laddr.ip if c.laddr else "",
                    local_port=c.laddr.port if c.laddr else 0,
                    remote_addr=c.raddr.ip if c.raddr else "",
                    remote_port=c.raddr.port if c.raddr else 0,
                    status=c.status if c.status else "",
                    pid=c.pid,
                ))
        except (psutil.AccessDenied, OSError):
            logger.debug("Cannot collect system-wide connections (access denied)")
        return conns

    # ------------------------------------------------------------------
    # Internal loops
    # ------------------------------------------------------------------

    async def _collect_loop(self) -> None:
        """Periodically collect metrics and buffer them."""
        while self._running:
            try:
                batch = self._collect_batch()
                self._metrics_buffer.append(batch)
                logger.debug(
                    "Collected batch: host_cpu=%.1f%%, procs=%d, conns=%d",
                    batch.host_metrics.cpu_percent if batch.host_metrics else 0,
                    len(batch.processes),
                    len(batch.connections),
                )
            except Exception:
                logger.error("Collection failed", exc_info=True)

            await self._interruptible_sleep(self.config.collect_interval_seconds)

    async def _send_loop(self) -> None:
        """Periodically flush buffered metrics to the collector."""
        while self._running:
            await self._interruptible_sleep(self.config.send_interval_seconds)
            await self._flush_buffer()

    async def _discovery_loop(self) -> None:
        """Periodic auto-discovery + simulation loop.

        Waits for the first two collection cycles to complete so that there is
        live data available before the topology scan begins, then runs
        discovery and (optionally) chaos simulation on the discovered graph.
        The loop repeats every ``config.discovery_interval_seconds`` (default
        3600 s / 1 h).
        """
        if not self.config.auto_simulate:
            logger.debug("Auto-simulate disabled — discovery loop not started")
            return

        # Give the collection loop a head-start
        await self._interruptible_sleep(self.config.collect_interval_seconds * 2)

        while self._running:
            try:
                logger.info("Running auto-discovery...")
                from faultray.apm.auto_discover import AutoDiscoverer

                discoverer = AutoDiscoverer(
                    cloud_provider=self.config.cloud_provider,
                    cloud_config=self.config.cloud_config,
                    model_output_path=self.config.model_output_path,
                )
                graph = discoverer.discover_all()

                logger.info(
                    "Running auto-simulation (%d components)...",
                    len(graph.components),
                )
                from faultray.apm.auto_simulate import AutoSimulator
                from dataclasses import asdict as _asdict

                simulator = AutoSimulator(graph)
                report = simulator.run()

                # Log key findings
                logger.info(
                    "Simulation complete: score=%d/100, SPOFs=%d, critical=%d",
                    int(report.score),
                    len(report.spofs),
                    report.critical_count,
                )
                for spof in report.spofs:
                    logger.warning(
                        "SPOF detected: %s (%s)", spof["id"], spof["type"]
                    )

                # Save report to disk
                report_path = (
                    Path(self.config.pid_file).parent / "auto-report.json"
                )
                import json as _json

                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    _json.dumps(_asdict(report), indent=2), encoding="utf-8"
                )
                logger.debug("Auto-simulation report written to %s", report_path)

                # Send report to collector (best-effort)
                await self._send_report(report)

            except Exception as exc:
                logger.error(
                    "Auto-discovery/simulation failed: %s", exc, exc_info=True
                )

            # Wait for next cycle
            await self._interruptible_sleep(self.config.discovery_interval_seconds)

    async def _send_report(self, report: object) -> None:
        """Ship the auto-simulation report to the collector (best-effort).

        Failures here are logged at DEBUG level and never propagate.
        """
        import json as _json
        from dataclasses import asdict as _asdict

        try:
            payload = _asdict(report)  # type: ignore[arg-type]
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {"Content-Type": "application/json"}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                await client.post(
                    f"{self.config.collector_url}/api/apm/simulation-report",
                    content=_json.dumps(payload),
                    headers=headers,
                )
        except Exception as exc:
            logger.debug("Could not send simulation report to collector: %s", exc)

    async def _flush_buffer(self) -> None:
        """Send all buffered batches to the collector API."""
        if not self._metrics_buffer:
            return

        async with self._send_lock:
            batches = self._metrics_buffer[:]
            self._metrics_buffer.clear()

        # Merge into a single batch for efficiency
        merged = self._merge_batches(batches)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {"Content-Type": "application/json"}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"

                resp = await client.post(
                    f"{self.config.collector_url}/api/apm/metrics",
                    content=merged.model_dump_json(),
                    headers=headers,
                )
                if resp.status_code == 200:
                    logger.debug("Sent metrics batch (status=200)")
                else:
                    logger.warning(
                        "Collector responded with status %d: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
        except httpx.ConnectError:
            logger.warning(
                "Cannot connect to collector at %s — buffering",
                self.config.collector_url,
            )
            # Re-add to buffer for retry
            async with self._send_lock:
                self._metrics_buffer.extend(batches)
        except Exception:
            logger.error("Failed to send metrics", exc_info=True)

    def _collect_batch(self) -> MetricsBatch:
        """Collect a complete metrics batch."""
        host = self.collect_host_metrics()
        procs = self.collect_processes() if self.config.collect_processes else []
        conns = self.collect_connections() if self.config.collect_connections else []

        return MetricsBatch(
            agent_id=self.config.agent_id,
            host_metrics=host,
            processes=procs,
            connections=conns,
        )

    def _merge_batches(self, batches: list[MetricsBatch]) -> MetricsBatch:
        """Merge multiple batches — keep latest host metrics, accumulate rest."""
        if len(batches) == 1:
            return batches[0]

        latest_host = batches[-1].host_metrics
        all_procs: list[ProcessInfo] = []
        all_conns: list[ConnectionInfo] = []
        all_traces = []
        all_custom = []

        for b in batches:
            all_procs.extend(b.processes)
            all_conns.extend(b.connections)
            all_traces.extend(b.traces)
            all_custom.extend(b.custom_metrics)

        # Deduplicate processes — keep latest by PID
        seen_pids: dict[int, ProcessInfo] = {}
        for p in all_procs:
            seen_pids[p.pid] = p

        return MetricsBatch(
            agent_id=self.config.agent_id,
            host_metrics=latest_host,
            processes=list(seen_pids.values()),
            connections=all_conns,
            traces=all_traces,
            custom_metrics=all_custom,
        )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def _register(self) -> None:
        """Register this agent with the collector."""
        payload = {
            "agent_id": self.config.agent_id,
            "hostname": self._hostname,
            "ip_address": self._ip_address,
            "os_info": self._os_info,
            "agent_version": _VERSION,
            "labels": self.config.labels,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {"Content-Type": "application/json"}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                await client.post(
                    f"{self.config.collector_url}/api/apm/agents/register",
                    json=payload,
                    headers=headers,
                )
                logger.info("Agent registered with collector")
        except Exception:
            logger.warning("Could not register with collector — will retry on next send")

    async def _deregister(self) -> None:
        """Notify collector that agent is stopping."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                headers = {"Content-Type": "application/json"}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                await client.post(
                    f"{self.config.collector_url}/api/apm/agents/{self.config.agent_id}/heartbeat",
                    json={"agent_id": self.config.agent_id, "status": "stopped"},
                    headers=headers,
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _request_stop(self, *_args: object) -> None:
        self._running = False

    async def _interruptible_sleep(self, seconds: float) -> None:
        """Sleep in small increments so stop signals are handled quickly."""
        step = min(1.0, seconds)
        elapsed = 0.0
        while elapsed < seconds and self._running:
            await asyncio.sleep(step)
            elapsed += step

    def _write_pid_file(self) -> None:
        try:
            pid_path = Path(self.config.pid_file)
            pid_path.parent.mkdir(parents=True, exist_ok=True)
            pid_path.write_text(str(os.getpid()))
        except OSError:
            logger.debug("Could not write PID file at %s", self.config.pid_file)

    def _remove_pid_file(self) -> None:
        try:
            Path(self.config.pid_file).unlink(missing_ok=True)
        except OSError:
            pass

    @property
    def uptime_seconds(self) -> float:
        if self._start_time == 0:
            return 0.0
        return time.monotonic() - self._start_time


def _get_local_ip() -> str:
    """Get the local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def load_agent_config(path: Path | str | None = None) -> AgentConfig:
    """Load agent configuration from a YAML file."""
    import yaml

    if path is None:
        candidates = [
            Path("/etc/faultray/agent.yaml"),
            Path.home() / ".faultray" / "agent.yaml",
            Path("faultray-agent.yaml"),
        ]
        for c in candidates:
            if c.exists():
                path = c
                break

    if path is None:
        return AgentConfig()

    path = Path(path)
    if not path.exists():
        logger.warning("Agent config file not found: %s — using defaults", path)
        return AgentConfig()

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    return AgentConfig(**data)
