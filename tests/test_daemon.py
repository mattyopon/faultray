"""Tests for ChaosProofDaemon (continuous monitoring)."""

from __future__ import annotations

import json
import signal
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrasim.daemon import ChaosProofDaemon


@pytest.fixture
def model_file(tmp_path: Path) -> Path:
    """Create a minimal model JSON file for the daemon."""
    from infrasim.model.components import Component, ComponentType
    from infrasim.model.graph import InfraGraph

    graph = InfraGraph()
    graph.add_component(
        Component(id="web", name="Web Server", type=ComponentType.WEB_SERVER)
    )
    model_path = tmp_path / "test-model.json"
    graph.save(model_path)
    return model_path


@pytest.fixture
def daemon(model_file: Path, tmp_path: Path) -> ChaosProofDaemon:
    """Create a daemon instance with short interval for testing."""
    return ChaosProofDaemon(
        model_path=model_file,
        interval_seconds=1,
        results_dir=tmp_path / "results",
    )


class TestChaosProofDaemon:
    def test_init(self, daemon: ChaosProofDaemon, model_file: Path):
        """Daemon should initialize with correct attributes."""
        assert daemon.model_path == model_file
        assert daemon.interval == 1
        assert daemon.running is False
        assert daemon.scan_count == 0

    def test_run_scan(self, daemon: ChaosProofDaemon):
        """_run_scan() should execute simulation and return a result dict."""
        result = daemon._run_scan()
        assert result is not None
        assert "resilience_score" in result
        assert "total_scenarios" in result
        assert result["scan_number"] == 1
        assert "timestamp" in result

    def test_run_scan_missing_model(self, tmp_path: Path):
        """_run_scan() should return None if model file is missing."""
        daemon = ChaosProofDaemon(
            model_path=tmp_path / "nonexistent.json",
            interval_seconds=1,
            results_dir=tmp_path / "results",
        )
        result = daemon._run_scan()
        assert result is None

    def test_save_and_load_result(self, daemon: ChaosProofDaemon):
        """_save_result() should persist results that can be loaded later."""
        result = {"resilience_score": 85.0, "critical_count": 1}
        daemon._save_result(result)

        latest_path = daemon._latest_result_path()
        assert latest_path.exists()

        loaded = json.loads(latest_path.read_text())
        assert loaded["resilience_score"] == 85.0

    def test_has_regression_no_previous(self, daemon: ChaosProofDaemon):
        """_has_regression() should return False when there's no previous result."""
        result = daemon._run_scan()
        assert daemon._has_regression(result) is False

    def test_has_regression_detected(self, daemon: ChaosProofDaemon):
        """_has_regression() should detect score drops."""
        daemon._previous_result = {
            "resilience_score": 90.0,
            "results": [],
        }
        # Run a scan that likely produces a different score
        result = {
            "resilience_score": 50.0,
            "results": [
                {"scenario_name": "new-critical", "risk_score": 9.0, "is_critical": True, "is_warning": False, "cascade": {"effects": []}},
            ],
        }
        assert daemon._has_regression(result) is True

    def test_stop(self, daemon: ChaosProofDaemon):
        """stop() should set running to False."""
        daemon._running = True
        daemon.stop()
        assert daemon.running is False

    def test_handle_signal(self, daemon: ChaosProofDaemon):
        """Signal handler should stop the daemon."""
        daemon._running = True
        daemon._handle_signal(signal.SIGINT, None)
        assert daemon.running is False

    def test_start_runs_and_stops(self, daemon: ChaosProofDaemon):
        """start() should run scans and respond to stop."""
        scan_count = 0

        original_sleep = daemon._interruptible_sleep

        def mock_sleep(seconds):
            nonlocal scan_count
            scan_count += 1
            if scan_count >= 2:
                daemon.stop()

        daemon._interruptible_sleep = mock_sleep
        daemon.start()

        assert daemon.scan_count >= 1
        assert daemon.running is False

    def test_notify_called_on_regression(self, daemon: ChaosProofDaemon):
        """Notification should be triggered when regression is detected."""
        with patch.object(daemon, "_notify") as mock_notify:
            daemon._previous_result = {
                "resilience_score": 95.0,
                "results": [],
            }

            result = {
                "resilience_score": 40.0,
                "results": [
                    {"scenario_name": "bad", "risk_score": 9.0, "is_critical": True, "is_warning": False, "cascade": {"effects": []}},
                ],
                "scan_number": 1,
                "timestamp": time.time(),
            }

            with patch.object(daemon, "_run_scan", return_value=result):
                scan_count = 0

                def mock_sleep(seconds):
                    nonlocal scan_count
                    scan_count += 1
                    daemon.stop()

                daemon._interruptible_sleep = mock_sleep
                daemon.start()

            mock_notify.assert_called()

    def test_load_previous_result_on_init(self, model_file: Path, tmp_path: Path):
        """Daemon should load the latest result on init if available."""
        results_dir = tmp_path / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        latest = results_dir / "latest.json"
        latest.write_text(json.dumps({"resilience_score": 88.0, "results": []}))

        daemon = ChaosProofDaemon(
            model_path=model_file,
            interval_seconds=1,
            results_dir=results_dir,
        )
        assert daemon._previous_result is not None
        assert daemon._previous_result["resilience_score"] == 88.0
