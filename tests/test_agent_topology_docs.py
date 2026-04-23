"""Regression: agent_config / llm_config / tool_config / orchestrator_config
are documented with working examples (#83)."""

from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent


def test_agent_topology_guide_exists():
    p = _ROOT / "docs" / "guides" / "agent-topology.md"
    assert p.exists(), "docs/guides/agent-topology.md missing (#83)"
    text = p.read_text(encoding="utf-8")
    for key in ("agent_config", "llm_config", "tool_config", "orchestrator_config"):
        assert key in text, f"guide must document '{key}' (#83)"


def test_minimal_example_valid_yaml_and_has_agent_config():
    p = _ROOT / "examples" / "agent-topology-minimal.yaml"
    assert p.exists()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["schema_version"] == "4.0"
    agent = next(c for c in data["components"] if c["type"] == "ai_agent")
    assert "agent_config" in agent
    assert "llm_config" in agent


def test_advanced_example_exercises_orchestrator_config():
    p = _ROOT / "examples" / "agent-topology-advanced.yaml"
    assert p.exists()
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    supervisor = next(c for c in data["components"] if c["id"] == "supervisor")
    assert "orchestrator_config" in supervisor
    assert supervisor["orchestrator_config"]["strategy"] == "majority_vote"
    assert len(supervisor["orchestrator_config"]["workers"]) == 3


def test_examples_load_via_faultray_loader():
    """End-to-end: loader flattens configs into parameters without error."""
    from faultray.model.loader import load_yaml

    for fname in ("agent-topology-minimal.yaml", "agent-topology-advanced.yaml"):
        p = _ROOT / "examples" / fname
        graph = load_yaml(p)
        assert graph.components, f"{fname} produced an empty graph"
