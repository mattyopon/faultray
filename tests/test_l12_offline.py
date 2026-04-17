# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""L12 Offline Capability Tests — Infrastructure Limits layer.

Validates that FaultRay core functionality works without network:
- All core simulation features operate offline
- No external API dependencies for core operations
- Model loading and simulation are fully local
"""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from faultray.model.demo import create_demo_graph
from faultray.model.loader import load_yaml
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.monte_carlo import run_monte_carlo


# ---------------------------------------------------------------------------
# L12-OFFLINE-001: Core features work without network
# ---------------------------------------------------------------------------


class TestOfflineCoreFeatures:
    """Verify that core features do not require network connectivity."""

    def _block_network(self):
        """Context manager that blocks all socket connections."""
        _original_connect = socket.socket.connect

        def blocked_connect(*args, **kwargs):
            raise OSError("Network blocked by test")

        return patch.object(socket.socket, "connect", blocked_connect)

    def test_demo_graph_creation_offline(self) -> None:
        """Demo graph creation should work without network."""
        with self._block_network():
            graph = create_demo_graph()
            assert len(graph.components) > 0

    def test_yaml_loading_offline(self, tmp_path: Path) -> None:
        """YAML loading should work without network."""
        yaml_content = {
            "components": [
                {"id": "web", "name": "Web", "type": "web_server"},
                {"id": "db", "name": "DB", "type": "database"},
            ],
            "dependencies": [
                {"source": "web", "target": "db", "type": "requires"},
            ],
        }
        yaml_file = tmp_path / "offline.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))

        with self._block_network():
            graph = load_yaml(yaml_file)
            assert len(graph.components) == 2

    def test_simulation_offline(self) -> None:
        """Full simulation should work without network."""
        with self._block_network():
            graph = create_demo_graph()
            engine = SimulationEngine(graph)
            report = engine.run_all_defaults(
                include_feed=False, include_plugins=False,
            )
            assert len(report.results) > 0
            assert report.resilience_score >= 0

    def test_monte_carlo_offline(self) -> None:
        """Monte Carlo simulation should work without network."""
        with self._block_network():
            graph = create_demo_graph()
            result = run_monte_carlo(graph, n_trials=100, seed=42)
            assert result.availability_mean > 0.0


# ---------------------------------------------------------------------------
# L12-OFFLINE-002: No external API dependencies for core
# ---------------------------------------------------------------------------


class TestNoExternalAPIDependency:
    """Verify that core operations don't call external services."""

    def test_sdk_faultzero_demo_no_network(self) -> None:
        """FaultZero.demo() should not make network calls."""
        from faultray.sdk import FaultZero

        with patch.object(socket.socket, "connect", side_effect=OSError("blocked")):
            fz = FaultZero.demo()
            score = fz.resilience_score
            assert score >= 0

    def test_config_load_no_network(self) -> None:
        """Config loading should not require network."""
        from faultray.config import FaultRayConfig

        with patch.object(socket.socket, "connect", side_effect=OSError("blocked")):
            config = FaultRayConfig()
            assert config.simulation is not None

    def test_error_classes_no_network(self) -> None:
        """Error classes should be usable without network."""
        from faultray.errors import (
            FaultRayError,
            ValidationError,
            ComponentNotFoundError,
        )

        with patch.object(socket.socket, "connect", side_effect=OSError("blocked")):
            err = ValidationError("test error")
            assert str(err) == "test error"
