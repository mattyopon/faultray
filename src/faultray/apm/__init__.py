# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""FaultRay APM — Application Performance Monitoring agent and server components.

Submodules:
- ``models``: Pydantic data models for metrics, traces, and agent registration.
- ``metrics_db``: SQLite-based time-series metrics storage with retention.
- ``agent``: Lightweight daemon that collects host/process metrics via psutil.
- ``collector``: FastAPI endpoints receiving agent telemetry.
- ``anomaly``: Statistical anomaly detection engine.
- ``topology_updater``: Automatic InfraGraph updates from agent connection data.
- ``simulation_link``: Bidirectional bridge between APM data and simulations.
"""
