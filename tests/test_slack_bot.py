"""Tests for Slack bot integration (slack_bot.py)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrasim.integrations.slack_bot import (
    FaultZeroSlackBot,
    SlackCommand,
    SlackResponse,
    parse_slack_command,
)
from infrasim.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph() -> InfraGraph:
    """Create a simple InfraGraph for testing."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        port=443,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="api",
        name="API Server",
        type=ComponentType.APP_SERVER,
        port=8080,
        replicas=3,
        autoscaling=AutoScalingConfig(enabled=True),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        port=5432,
        replicas=2,
        failover=FailoverConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="api"))
    graph.add_dependency(Dependency(source_id="api", target_id="db"))
    return graph


def _save_model(tmp_path: Path) -> Path:
    """Save a test model to disk and return the path."""
    graph = _make_graph()
    model_path = tmp_path / "test-model.json"
    graph.save(model_path)
    return model_path


# ---------------------------------------------------------------------------
# 1. Command parsing
# ---------------------------------------------------------------------------

class TestParseSlackCommand:
    def test_empty_input(self):
        cmd = parse_slack_command("")
        assert cmd.command == "help"

    def test_simulate_command(self):
        cmd = parse_slack_command("simulate")
        assert cmd.command == "simulate"

    def test_score_command(self):
        cmd = parse_slack_command("score")
        assert cmd.command == "score"

    def test_trend_command(self):
        cmd = parse_slack_command("trend")
        assert cmd.command == "trend"

    def test_trend_with_days(self):
        cmd = parse_slack_command("trend --days 60")
        assert cmd.command == "trend"
        assert cmd.args["days"] == "60"

    def test_help_command(self):
        cmd = parse_slack_command("help")
        assert cmd.command == "help"

    def test_user_and_channel(self):
        cmd = parse_slack_command("score", user_id="U123", channel_id="C456")
        assert cmd.user_id == "U123"
        assert cmd.channel_id == "C456"

    def test_case_insensitive(self):
        cmd = parse_slack_command("SIMULATE")
        assert cmd.command == "simulate"


# ---------------------------------------------------------------------------
# 2. SlackResponse
# ---------------------------------------------------------------------------

class TestSlackResponse:
    def test_to_dict_basic(self):
        resp = SlackResponse(text="Hello")
        d = resp.to_dict()
        assert d["text"] == "Hello"
        assert d["response_type"] == "in_channel"

    def test_to_dict_ephemeral(self):
        resp = SlackResponse(text="Private", ephemeral=True)
        d = resp.to_dict()
        assert d["response_type"] == "ephemeral"

    def test_to_dict_with_blocks(self):
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}]
        resp = SlackResponse(text="Hello", blocks=blocks)
        d = resp.to_dict()
        assert len(d["blocks"]) == 1


# ---------------------------------------------------------------------------
# 3. Help command
# ---------------------------------------------------------------------------

class TestHelpCommand:
    def test_help_response(self):
        bot = FaultZeroSlackBot()
        cmd = SlackCommand(command="help")
        resp = bot.handle_command(cmd)

        assert resp.ephemeral is True
        assert "Commands" in resp.text or "commands" in resp.text.lower()
        assert len(resp.blocks) >= 1


# ---------------------------------------------------------------------------
# 4. Unknown command
# ---------------------------------------------------------------------------

class TestUnknownCommand:
    def test_unknown_response(self):
        bot = FaultZeroSlackBot()
        cmd = SlackCommand(command="foobar")
        resp = bot.handle_command(cmd)

        assert resp.ephemeral is True
        assert "unknown" in resp.text.lower() or "Unknown" in resp.text


# ---------------------------------------------------------------------------
# 5. Score command
# ---------------------------------------------------------------------------

class TestScoreCommand:
    def test_score_with_model(self, tmp_path):
        model_path = _save_model(tmp_path)
        bot = FaultZeroSlackBot(model_path=model_path)
        cmd = SlackCommand(command="score")
        resp = bot.handle_command(cmd)

        assert "Score" in resp.text or "score" in resp.text.lower()
        assert len(resp.blocks) >= 2  # Header + score section
        assert resp.ephemeral is False

    def test_score_no_model(self, tmp_path):
        bot = FaultZeroSlackBot(model_path=tmp_path / "nonexistent.json")
        cmd = SlackCommand(command="score")
        resp = bot.handle_command(cmd)

        assert resp.ephemeral is True
        assert "not found" in resp.text.lower() or "no model" in resp.text.lower()


# ---------------------------------------------------------------------------
# 6. Simulate command
# ---------------------------------------------------------------------------

class TestSimulateCommand:
    def test_simulate_with_model(self, tmp_path):
        model_path = _save_model(tmp_path)
        bot = FaultZeroSlackBot(model_path=model_path)
        cmd = SlackCommand(command="simulate")
        resp = bot.handle_command(cmd)

        assert "complete" in resp.text.lower() or "score" in resp.text.lower()
        assert len(resp.blocks) >= 2
        assert resp.ephemeral is False

    def test_simulate_no_model(self, tmp_path):
        bot = FaultZeroSlackBot(model_path=tmp_path / "nonexistent.json")
        cmd = SlackCommand(command="simulate")
        resp = bot.handle_command(cmd)

        assert resp.ephemeral is True


# ---------------------------------------------------------------------------
# 7. Trend command
# ---------------------------------------------------------------------------

class TestTrendCommand:
    def test_trend_no_history(self, tmp_path):
        bot = FaultZeroSlackBot(model_path=tmp_path / "nonexistent.json")
        cmd = SlackCommand(command="trend")
        # This should handle gracefully when no history exists
        resp = bot.handle_command(cmd)
        # Either ephemeral error or a valid response about no data
        assert isinstance(resp, SlackResponse)

    def test_trend_with_history(self, tmp_path):
        # Set up history first
        from infrasim.history import HistoryTracker

        db_path = Path.home() / ".faultzero" / "history.db"
        tracker = HistoryTracker(db_path=db_path)
        graph = _make_graph()
        tracker.record(graph)

        bot = FaultZeroSlackBot()
        cmd = SlackCommand(command="trend", args={"days": "30"})
        resp = bot.handle_command(cmd)

        assert isinstance(resp, SlackResponse)


# ---------------------------------------------------------------------------
# 8. Format blocks
# ---------------------------------------------------------------------------

class TestFormatBlocks:
    def test_format_score_blocks_high(self):
        bot = FaultZeroSlackBot()
        blocks = bot._format_score_blocks(90.0, 0, 1, 10, 11)

        assert len(blocks) >= 2
        # Check header exists
        assert blocks[0]["type"] == "header"

        # Find the block with score text
        found_green = False
        for b in blocks:
            text_content = json.dumps(b)
            if "green" in text_content or "90" in text_content:
                found_green = True
        assert found_green

    def test_format_score_blocks_low(self):
        bot = FaultZeroSlackBot()
        blocks = bot._format_score_blocks(40.0, 5, 3, 2, 10)

        assert len(blocks) >= 2
        found_red = False
        for b in blocks:
            text_content = json.dumps(b)
            if "red" in text_content:
                found_red = True
        assert found_red

    def test_format_error_blocks(self):
        bot = FaultZeroSlackBot()
        blocks = bot._format_error_blocks("test_cmd", ValueError("test error"))

        assert len(blocks) >= 1
        text_content = json.dumps(blocks)
        assert "test error" in text_content

    def test_error_handling_in_command(self):
        """Commands that raise exceptions should return error blocks."""
        bot = FaultZeroSlackBot()

        # Patch _cmd_simulate to raise
        with patch.object(bot, "_cmd_simulate", side_effect=RuntimeError("boom")):
            cmd = SlackCommand(command="simulate")
            resp = bot.handle_command(cmd)

            assert "Error" in resp.text or "boom" in resp.text
            assert len(resp.blocks) >= 1
