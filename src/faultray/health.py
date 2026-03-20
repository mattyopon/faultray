# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Health check module for FaultRay.

Provides detailed component-level health information
for monitoring and orchestration systems.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

import faultray


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str = ""


@dataclass
class SystemHealth:
    status: HealthStatus
    version: str
    uptime_seconds: float
    engines_available: int
    components: list[ComponentHealth] = field(default_factory=list)
    checks_passed: int = 0
    checks_failed: int = 0


_start_time = time.monotonic()


def check_health() -> SystemHealth:
    """Run all health checks and return system health."""
    components = []

    # Check core imports
    checks = [
        ("cascade_engine", "faultray.simulator.cascade"),
        ("dynamic_engine", "faultray.simulator.dynamic_engine"),
        ("ops_engine", "faultray.simulator.ops_engine"),
        ("cost_engine", "faultray.simulator.cost_impact"),
        ("security_engine", "faultray.simulator.security_resilience"),
        ("compliance_engine", "faultray.simulator.compliance_frameworks"),
        ("dr_engine", "faultray.simulator.multi_region_dr"),
        ("predictive_engine", "faultray.simulator.predictive_engine"),
    ]

    passed = 0
    failed = 0
    for name, module_path in checks:
        start = time.monotonic()
        try:
            __import__(module_path)
            latency = (time.monotonic() - start) * 1000
            components.append(ComponentHealth(name, HealthStatus.HEALTHY, latency))
            passed += 1
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            components.append(ComponentHealth(name, HealthStatus.UNHEALTHY, latency, str(e)))
            failed += 1

    overall = HealthStatus.HEALTHY
    if failed > 0 and passed > 0:
        overall = HealthStatus.DEGRADED
    elif failed > 0 and passed == 0:
        overall = HealthStatus.UNHEALTHY

    return SystemHealth(
        status=overall,
        version=faultray.__version__,
        uptime_seconds=round(time.monotonic() - _start_time, 2),
        engines_available=passed,
        components=components,
        checks_passed=passed,
        checks_failed=failed,
    )
