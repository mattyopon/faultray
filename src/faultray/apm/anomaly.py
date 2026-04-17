# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Anomaly detection engine for APM metrics.

Provides:
- Static threshold alerts (configurable via AlertRule).
- Statistical anomaly detection (moving average + standard deviation).
- Trend detection (degradation early warning).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import math
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from faultray.apm.models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AnomalyResult,
    HostMetrics,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default alert rules
# ---------------------------------------------------------------------------

DEFAULT_ALERT_RULES: list[AlertRule] = [
    AlertRule(
        name="high_cpu",
        metric_name="cpu_percent",
        condition="gt",
        threshold=90.0,
        duration_seconds=60,
        severity=AlertSeverity.CRITICAL,
    ),
    AlertRule(
        name="high_memory",
        metric_name="memory_percent",
        condition="gt",
        threshold=90.0,
        duration_seconds=60,
        severity=AlertSeverity.CRITICAL,
    ),
    AlertRule(
        name="high_disk",
        metric_name="disk_percent",
        condition="gt",
        threshold=85.0,
        duration_seconds=0,
        severity=AlertSeverity.WARNING,
    ),
    AlertRule(
        name="high_load",
        metric_name="load_avg_1m",
        condition="gt",
        threshold=10.0,
        duration_seconds=120,
        severity=AlertSeverity.WARNING,
    ),
]


class AnomalyEngine:
    """Statistical anomaly detection and threshold alerting engine.

    Maintains a rolling window of metric values per agent for computing
    moving averages and standard deviations.
    """

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        window_size: int = 60,
        sigma_threshold: float = 3.0,
    ) -> None:
        self.rules = rules if rules is not None else list(DEFAULT_ALERT_RULES)
        self.window_size = window_size
        self.sigma_threshold = sigma_threshold

        # Rolling buffers: {agent_id -> {metric_name -> list[float]}}
        self._buffers: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # Duration tracking: {(agent_id, rule_name) -> first_breach_time}
        self._breach_start: dict[tuple[str, str], _dt.datetime] = {}
        # Fired alerts (to avoid duplicates): {(agent_id, rule_name)}
        self._active_alerts: set[tuple[str, str]] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_batch(
        self,
        agent_id: str,
        host_metrics: HostMetrics,
        db: Any | None = None,
    ) -> list[Alert]:
        """Check a host metrics snapshot for anomalies and threshold breaches.

        Returns list of newly fired alerts.
        """
        metrics_map = {
            "cpu_percent": host_metrics.cpu_percent,
            "memory_percent": host_metrics.memory_percent,
            "disk_percent": host_metrics.disk_percent,
            "load_avg_1m": host_metrics.load_avg_1m,
            "network_connections": float(host_metrics.network_connections),
        }

        fired: list[Alert] = []

        # Update rolling buffers
        for name, value in metrics_map.items():
            buf = self._buffers[agent_id][name]
            buf.append(value)
            if len(buf) > self.window_size:
                buf.pop(0)

        # Check threshold rules
        for rule in self.rules:
            if not rule.enabled:
                continue
            metric_value: float | None = metrics_map.get(rule.metric_name)
            if metric_value is None:
                continue

            breached = self._check_condition(metric_value, rule.condition, rule.threshold)
            key = (agent_id, rule.name)

            if breached:
                if rule.duration_seconds > 0:
                    now = _dt.datetime.now(_dt.timezone.utc)
                    if key not in self._breach_start:
                        self._breach_start[key] = now
                    elapsed = (now - self._breach_start[key]).total_seconds()
                    if elapsed < rule.duration_seconds:
                        continue  # Duration not yet met

                if key not in self._active_alerts:
                    alert = Alert(
                        alert_id=uuid.uuid4().hex[:12],
                        rule_name=rule.name,
                        agent_id=agent_id,
                        metric_name=rule.metric_name,
                        metric_value=value,
                        threshold=rule.threshold,
                        severity=rule.severity,
                        message=(
                            f"{rule.metric_name} = {value:.1f} "
                            f"{rule.condition} {rule.threshold} on {agent_id}"
                        ),
                    )
                    fired.append(alert)
                    self._active_alerts.add(key)

                    # Persist alert
                    if db is not None:
                        try:
                            db.insert_alert(alert.model_dump(mode="json"))
                        except Exception:
                            logger.debug("Could not persist alert", exc_info=True)

                    # Send notification
                    self._notify(alert)
            else:
                # Condition resolved
                self._breach_start.pop(key, None)
                if key in self._active_alerts:
                    self._active_alerts.discard(key)

        return fired

    def detect_anomalies(self, agent_id: str) -> list[AnomalyResult]:
        """Run statistical anomaly detection on buffered metrics."""
        results: list[AnomalyResult] = []
        agent_bufs = self._buffers.get(agent_id, {})

        for metric_name, values in agent_bufs.items():
            if len(values) < 5:
                continue

            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std = math.sqrt(variance) if variance > 0 else 0.0

            current = values[-1]
            deviation = abs(current - mean) / std if std > 0 else 0.0

            # Trend detection
            trend = self._detect_trend(values)

            is_anomaly = deviation >= self.sigma_threshold

            results.append(AnomalyResult(
                metric_name=metric_name,
                agent_id=agent_id,
                current_value=current,
                expected_value=mean,
                deviation_sigma=deviation,
                is_anomaly=is_anomaly,
                trend=trend,
            ))

        return results

    def add_rule(self, rule: AlertRule) -> None:
        """Add a new alert rule."""
        self.rules.append(rule)

    def remove_rule(self, name: str) -> bool:
        """Remove an alert rule by name."""
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.name != name]
        return len(self.rules) < before

    def load_rules_from_file(self, path: Path | str) -> int:
        """Load alert rules from a YAML/JSON file."""
        import yaml

        path = Path(path)
        if not path.exists():
            return 0

        with open(path) as f:
            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(f) or {}
            else:
                data = json.loads(f.read())

        rules_data = data.get("rules", data if isinstance(data, list) else [])
        count = 0
        for rd in rules_data:
            try:
                rule = AlertRule(**rd)
                self.rules.append(rule)
                count += 1
            except Exception:
                logger.warning("Invalid alert rule: %s", rd)
        return count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _check_condition(value: float, condition: str, threshold: float) -> bool:
        ops = {
            "gt": lambda v, t: v > t,
            "lt": lambda v, t: v < t,
            "gte": lambda v, t: v >= t,
            "lte": lambda v, t: v <= t,
            "eq": lambda v, t: abs(v - t) < 0.001,
        }
        fn = ops.get(condition)
        if fn is None:
            return False
        return bool(fn(value, threshold))

    @staticmethod
    def _detect_trend(values: list[float]) -> str:
        """Simple trend detection using linear regression slope."""
        n = len(values)
        if n < 3:
            return "stable"

        # Use last N points (max 30)
        window = values[-min(n, 30):]
        n = len(window)
        x_mean = (n - 1) / 2.0
        y_mean = sum(window) / n

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(window))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return "stable"

        slope = numerator / denominator

        # Normalize slope relative to mean
        if y_mean == 0:
            return "stable"

        relative_slope = slope / abs(y_mean)

        if relative_slope > 0.05:
            return "increasing"
        elif relative_slope < -0.05:
            return "decreasing"

        # Check for spike (current much higher than recent average)
        recent_avg = sum(window[-3:]) / 3
        overall_avg = sum(window[:-3]) / max(len(window) - 3, 1)
        if overall_avg > 0 and recent_avg / overall_avg > 1.5:
            return "spike"

        return "stable"

    def _notify(self, alert: Alert) -> None:
        """Send alert notification via configured channels."""
        logger.warning(
            "ALERT [%s] %s: %s (value=%.1f, threshold=%.1f)",
            alert.severity.value.upper(),
            alert.rule_name,
            alert.message,
            alert.metric_value,
            alert.threshold,
        )
        # Async notifications (Slack, PagerDuty, etc.) would be triggered here
        # via the existing faultray.integrations.webhooks module.


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_engine: AnomalyEngine | None = None


def get_anomaly_engine() -> AnomalyEngine:
    global _engine
    if _engine is None:
        _engine = AnomalyEngine()
    return _engine


def set_anomaly_engine(engine: AnomalyEngine) -> None:
    global _engine
    _engine = engine
