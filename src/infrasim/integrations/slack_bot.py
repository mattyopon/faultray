"""Slack bot for interactive FaultZero commands.

Provides a Slack bot that responds to slash commands for running
simulations, checking scores, and viewing trends. Does NOT require
slack_sdk -- it builds JSON payloads (Slack Block Kit) directly.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SlackCommand:
    """Parsed Slack slash command."""

    command: str  # "simulate", "score", "trend", "help"
    args: dict = field(default_factory=dict)
    user_id: str = ""
    channel_id: str = ""


@dataclass
class SlackResponse:
    """Response to send back to Slack."""

    text: str
    blocks: list[dict] = field(default_factory=list)
    ephemeral: bool = False

    def to_dict(self) -> dict:
        """Convert to a JSON-serialisable dict for Slack API."""
        result: dict[str, Any] = {"text": self.text}
        if self.blocks:
            result["blocks"] = self.blocks
        if self.ephemeral:
            result["response_type"] = "ephemeral"
        else:
            result["response_type"] = "in_channel"
        return result


def parse_slack_command(text: str, user_id: str = "", channel_id: str = "") -> SlackCommand:
    """Parse raw Slack command text into a SlackCommand.

    Expected formats:
        /faultzero simulate
        /faultzero score
        /faultzero trend --days 30
        /faultzero help
    """
    parts = text.strip().split()
    if not parts:
        return SlackCommand(command="help", user_id=user_id, channel_id=channel_id)

    cmd = parts[0].lower()
    args: dict = {}

    # Parse --key value pairs
    i = 1
    while i < len(parts):
        if parts[i].startswith("--") and i + 1 < len(parts):
            key = parts[i][2:]
            args[key] = parts[i + 1]
            i += 2
        else:
            args.setdefault("positional", []).append(parts[i])
            i += 1

    return SlackCommand(command=cmd, args=args, user_id=user_id, channel_id=channel_id)


class FaultZeroSlackBot:
    """Slack bot for interactive FaultZero commands.

    Does not depend on slack_sdk. Builds Slack Block Kit JSON payloads
    that can be sent via webhook or returned as HTTP responses.
    """

    def __init__(self, model_path: Path | None = None) -> None:
        self.model_path = model_path

    def handle_command(self, command: SlackCommand) -> SlackResponse:
        """Route a SlackCommand to the appropriate handler.

        Args:
            command: Parsed Slack command.

        Returns:
            A SlackResponse with text and optional Block Kit blocks.
        """
        handlers = {
            "simulate": self._cmd_simulate,
            "score": self._cmd_score,
            "trend": self._cmd_trend,
            "help": self._cmd_help,
        }

        handler = handlers.get(command.command, self._cmd_unknown)
        try:
            return handler(command.args)
        except Exception as exc:
            return SlackResponse(
                text=f"Error running '{command.command}': {exc}",
                blocks=self._format_error_blocks(command.command, exc),
            )

    def _cmd_simulate(self, args: dict) -> SlackResponse:
        """Run simulation and return summary."""
        graph = self._load_graph()
        if graph is None:
            return SlackResponse(
                text="No model file found. Set model_path or use default faultzero-model.json.",
                ephemeral=True,
            )

        from infrasim.simulator.engine import SimulationEngine

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()

        score = report.resilience_score
        critical = len(report.critical_findings)
        warning = len(report.warnings)
        passed = len(report.passed)
        total = len(report.results)

        text = (
            f"Simulation complete: score {score:.0f}/100, "
            f"{critical} critical, {warning} warnings, {passed} passed"
        )
        blocks = self._format_score_blocks(score, critical, warning, passed, total)

        # Record to history
        self._record_history(graph, report)

        return SlackResponse(text=text, blocks=blocks)

    def _cmd_score(self, args: dict) -> SlackResponse:
        """Show current resilience score."""
        graph = self._load_graph()
        if graph is None:
            return SlackResponse(
                text="No model file found.",
                ephemeral=True,
            )

        score_v1 = graph.resilience_score()
        v2_data = graph.resilience_score_v2()
        score_v2 = v2_data.get("score", 0.0)
        breakdown = v2_data.get("breakdown", {})
        component_count = len(graph.components)
        dep_count = len(graph.all_dependency_edges())

        text = f"Resilience Score: {score_v1:.0f}/100 (v2: {score_v2:.0f}/100)"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "FaultZero Resilience Score"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Score (v1):* {score_v1:.0f}/100"},
                    {"type": "mrkdwn", "text": f"*Score (v2):* {score_v2:.0f}/100"},
                    {"type": "mrkdwn", "text": f"*Components:* {component_count}"},
                    {"type": "mrkdwn", "text": f"*Dependencies:* {dep_count}"},
                ],
            },
        ]

        # Add v2 breakdown
        if breakdown:
            breakdown_lines = []
            for key, val in breakdown.items():
                label = key.replace("_", " ").title()
                bar_len = int(val / 20.0 * 10)
                bar = "\u2588" * bar_len + "\u2591" * (10 - bar_len)
                breakdown_lines.append(f"`{bar}` {label}: {val:.1f}/20")

            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Score Breakdown (v2):*\n" + "\n".join(breakdown_lines),
                },
            })

        return SlackResponse(text=text, blocks=blocks)

    def _cmd_trend(self, args: dict) -> SlackResponse:
        """Show score trend over time."""
        days = int(args.get("days", "30"))

        try:
            from infrasim.history import HistoryTracker

            tracker = HistoryTracker()
            trend = tracker.analyze_trend(days=days)
        except Exception as exc:
            return SlackResponse(
                text=f"Could not load history: {exc}",
                ephemeral=True,
            )

        if not trend.entries:
            return SlackResponse(
                text="No history data available. Run evaluations first.",
                ephemeral=True,
            )

        trend_emoji = {
            "improving": ":arrow_up:",
            "stable": ":left_right_arrow:",
            "degrading": ":arrow_down:",
        }
        emoji = trend_emoji.get(trend.score_trend, ":question:")

        latest = trend.entries[-1]
        text = (
            f"Trend ({days}d): {trend.score_trend} {emoji} | "
            f"Current: {latest.resilience_score:.0f}/100 | "
            f"Change: {trend.score_change_30d:+.1f}"
        )

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"FaultZero Trend ({days} days)"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Trend:* {trend.score_trend} {emoji}"},
                    {"type": "mrkdwn", "text": f"*30-day Change:* {trend.score_change_30d:+.1f}"},
                    {"type": "mrkdwn", "text": f"*Best Score:* {trend.best_score:.0f}"},
                    {"type": "mrkdwn", "text": f"*Worst Score:* {trend.worst_score:.0f}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Latest:* {latest.resilience_score:.0f}/100 "
                    f"({latest.critical_count} critical, {latest.warning_count} warnings)\n"
                    f"*Regressions:* {len(trend.regression_dates)}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Recommendation:* {trend.recommendation}",
                },
            },
        ]

        return SlackResponse(text=text, blocks=blocks)

    def _cmd_help(self, args: dict) -> SlackResponse:
        """Show available commands."""
        text = "FaultZero Slack Bot Commands"
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "FaultZero Slack Commands"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Available Commands:*\n\n"
                        "`/faultzero simulate` - Run chaos simulation and show results\n"
                        "`/faultzero score` - Show current resilience score\n"
                        "`/faultzero trend` - Show 30-day score trend\n"
                        "`/faultzero trend --days 90` - Show 90-day score trend\n"
                        "`/faultzero help` - Show this help message"
                    ),
                },
            },
        ]
        return SlackResponse(text=text, blocks=blocks, ephemeral=True)

    def _cmd_unknown(self, args: dict) -> SlackResponse:
        """Handle unknown commands."""
        return SlackResponse(
            text="Unknown command. Use `/faultzero help` for available commands.",
            ephemeral=True,
        )

    def _format_score_blocks(
        self,
        score: float,
        critical: int,
        warning: int,
        passed: int,
        total: int,
    ) -> list[dict]:
        """Format simulation results as Slack Block Kit blocks."""
        if score >= 80:
            color = ":large_green_circle:"
        elif score >= 60:
            color = ":large_yellow_circle:"
        else:
            color = ":red_circle:"

        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "FaultZero Simulation Results",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{color} *Resilience Score: {score:.0f}/100*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total Scenarios:* {total}"},
                    {"type": "mrkdwn", "text": f"*Critical:* {critical}"},
                    {"type": "mrkdwn", "text": f"*Warnings:* {warning}"},
                    {"type": "mrkdwn", "text": f"*Passed:* {passed}"},
                ],
            },
        ]

    def _format_error_blocks(self, command: str, error: Exception) -> list[dict]:
        """Format an error as Slack Block Kit blocks."""
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":x: *Error running `{command}`:*\n```{error}```",
                },
            },
        ]

    def _load_graph(self) -> Any:
        """Load the InfraGraph from the configured model path."""
        from infrasim.model.graph import InfraGraph

        path = self.model_path
        if path is None:
            path = Path("faultzero-model.json")

        if not path.exists():
            return None

        if str(path).endswith((".yaml", ".yml")):
            from infrasim.model.loader import load_yaml
            return load_yaml(path)

        return InfraGraph.load(path)

    def _record_history(self, graph: Any, report: Any) -> None:
        """Try to record simulation results to history tracker."""
        try:
            from infrasim.history import HistoryTracker

            tracker = HistoryTracker()
            tracker.record(graph, report=report)
        except Exception:
            pass  # History recording is best-effort
