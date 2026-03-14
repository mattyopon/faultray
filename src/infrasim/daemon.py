"""Monitoring daemon for continuous infrastructure scanning."""

from __future__ import annotations

import json
import logging
import signal
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class ChaosProofDaemon:
    """Continuously scan an infrastructure model on a fixed interval.

    On each tick the daemon:
    1. Loads the model from disk (picks up external changes).
    2. Runs the simulation engine.
    3. Compares against the previous run to detect regressions.
    4. Sends notifications when regressions are found.
    5. Persists the latest result for the next comparison.
    """

    def __init__(
        self,
        model_path: Path,
        interval_seconds: int = 3600,
        results_dir: Path | None = None,
        notification_config: dict | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.interval = interval_seconds
        self.results_dir = results_dir or (Path.home() / ".chaosproof" / "daemon")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.notification_config = notification_config or {}
        self._running = False
        self._previous_result: dict | None = None
        self._scan_count = 0

        # Load previous result if available
        latest = self._latest_result_path()
        if latest and latest.exists():
            try:
                self._previous_result = json.loads(latest.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not load previous daemon result from %s", latest)

    def start(self) -> None:
        """Run simulation on interval, notify on changes.

        Blocks until SIGINT/SIGTERM is received.
        """
        self._running = True
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info(
            "ChaosProof daemon started: model=%s interval=%ds",
            self.model_path,
            self.interval,
        )

        while self._running:
            try:
                result = self._run_scan()
                if result is not None:
                    if self._has_regression(result):
                        logger.warning("Regression detected in scan #%d", self._scan_count)
                        self._notify(result)
                    self._save_result(result)
                    self._previous_result = result
            except Exception:
                logger.error("Daemon scan failed", exc_info=True)

            # Sleep in small increments so we can respond to stop signals quickly
            self._interruptible_sleep(self.interval)

    def stop(self) -> None:
        """Signal the daemon to stop."""
        self._running = False
        logger.info("ChaosProof daemon stopping.")

    @property
    def running(self) -> bool:
        return self._running

    @property
    def scan_count(self) -> int:
        return self._scan_count

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _handle_signal(self, signum: int, frame) -> None:  # noqa: ANN001
        """Handle termination signals gracefully."""
        logger.info("Received signal %d, stopping daemon.", signum)
        self.stop()

    def _run_scan(self) -> dict | None:
        """Execute a single simulation scan and return the result dict."""
        if not self.model_path.exists():
            logger.error("Model file not found: %s", self.model_path)
            return None

        from infrasim.model.graph import InfraGraph
        from infrasim.reporter.export import _report_to_export_dict
        from infrasim.simulator.engine import SimulationEngine

        graph = InfraGraph.load(self.model_path)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        self._scan_count += 1
        result = _report_to_export_dict(report)
        result["scan_number"] = self._scan_count
        result["timestamp"] = time.time()
        return result

    def _has_regression(self, result: dict) -> bool:
        """Compare current result against previous to detect regression."""
        if self._previous_result is None:
            return False

        from infrasim.differ import SimulationDiffer

        differ = SimulationDiffer()
        diff = differ.diff(self._previous_result, result)
        return diff.regression_detected

    def _notify(self, result: dict) -> None:
        """Send notifications about the regression."""
        logger.info(
            "Sending regression notification: score=%.1f critical=%d",
            result.get("resilience_score", 0),
            result.get("critical_count", 0),
        )

        summary = {
            "resilience_score": result.get("resilience_score", 0),
            "critical_count": result.get("critical_count", 0),
            "warning_count": result.get("warning_count", 0),
            "passed_count": result.get("passed_count", 0),
            "total_scenarios": result.get("total_scenarios", 0),
        }

        # Try notification channels from config
        import asyncio

        async def _send():
            if "slack_webhook" in self.notification_config:
                try:
                    from infrasim.integrations.webhooks import send_slack_notification

                    await send_slack_notification(
                        self.notification_config["slack_webhook"], summary
                    )
                except Exception:
                    logger.warning("Slack notification failed", exc_info=True)

            if "pagerduty_key" in self.notification_config:
                try:
                    from infrasim.integrations.webhooks import send_pagerduty_event

                    await send_pagerduty_event(
                        self.notification_config["pagerduty_key"], summary
                    )
                except Exception:
                    logger.warning("PagerDuty notification failed", exc_info=True)

            if "teams_webhook" in self.notification_config:
                try:
                    from infrasim.integrations.webhooks import send_teams

                    await send_teams(
                        self.notification_config["teams_webhook"], summary
                    )
                except Exception:
                    logger.warning("Teams notification failed", exc_info=True)

        try:
            asyncio.run(_send())
        except Exception:
            logger.warning("Notification dispatch failed", exc_info=True)

    def _save_result(self, result: dict) -> None:
        """Persist the latest result to disk."""
        path = self._latest_result_path()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(result, indent=2, default=str),
                encoding="utf-8",
            )

    def _latest_result_path(self) -> Path | None:
        """Path to the latest daemon result file."""
        return self.results_dir / "latest.json"

    def _interruptible_sleep(self, seconds: int) -> None:
        """Sleep in 1-second increments to allow graceful shutdown."""
        for _ in range(seconds):
            if not self._running:
                break
            time.sleep(1)
