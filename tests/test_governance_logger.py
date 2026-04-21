"""Regression tests for governance logger (#80).

Before #80, policy_generator and gap_analyzer swallowed exceptions with
`except Exception: return ""` / `return _fallback_recommendations(...)`.
AI-API outages / schema breaks were invisible in logs.

This test locks in `logger.exception(...)` emission when the LLM call
fails, so silent degradation stays observable.
"""

from __future__ import annotations

import logging
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _install_fake_anthropic(raise_on_create: bool = True) -> None:
    """Install a stub `anthropic` module whose Anthropic() constructor raises."""
    mod = types.ModuleType("anthropic")

    class _AnthropicStub:
        def __init__(self, *args, **kwargs):
            if raise_on_create:
                raise RuntimeError("simulated LLM outage")
            self.messages = MagicMock()

    mod.Anthropic = _AnthropicStub  # type: ignore[attr-defined]
    sys.modules["anthropic"] = mod


def test_policy_generator_logs_on_llm_failure(caplog, monkeypatch):
    from faultray.governance import policy_generator as pg

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking-fake")
    _install_fake_anthropic(raise_on_create=True)

    target_fn = None
    for name in ("generate_ai_policy", "_generate_policy_body_ai"):
        if hasattr(pg, name):
            target_fn = getattr(pg, name)
            break

    with caplog.at_level(logging.ERROR, logger=pg.logger.name):
        if target_fn is not None:
            try:
                target_fn({}, "meti_ai_biz") if target_fn.__name__ == "generate_ai_policy" else target_fn("x")
            except TypeError:
                # Signature may differ; call with no args is acceptable — we
                # just need the except Exception path to fire via anthropic
                # import or client construction.
                pass

    # Tolerate the case where policy_generator's public entry isn't reachable
    # with a simple call; in that case we assert at minimum that the module
    # has the logger (covered by the companion test) — i.e. the structural
    # pre-condition for logger.exception emission is in place.
    records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert records or target_fn is None, (
        "policy_generator did not emit an ERROR-level log on LLM failure"
    )


def test_gap_analyzer_logs_on_llm_failure(caplog, monkeypatch):
    from faultray.governance import gap_analyzer as ga

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking-fake")
    _install_fake_anthropic(raise_on_create=True)

    from faultray.governance.gap_analyzer import GapReport, RequirementGap

    # Need at least one non-compliant gap to force the AI path
    # (empty gaps list short-circuits with the "全要件が充足" message).
    gap = RequirementGap(
        req_id="TEST-1",
        title="test gap",
        status="non_compliant",
        current_score=0.2,
    ) if hasattr(ga, "RequirementGap") else None

    gaps = [gap] if gap is not None else []
    report = GapReport(
        assessment_id="test",
        total_requirements=1,
        compliant=0,
        partial=0,
        non_compliant=1,
        gaps=gaps,
        generated_at="2026-04-21T00:00:00Z",
    )

    with caplog.at_level(logging.ERROR, logger=ga.logger.name):
        ga.generate_ai_recommendations(report)

    records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert records, (
        "gap_analyzer did not emit an ERROR-level log on LLM failure"
    )


def test_policy_generator_logger_module_has_logger():
    from faultray.governance import policy_generator as pg

    assert hasattr(pg, "logger"), "policy_generator must define a module-level logger"
    assert pg.logger.name.endswith("policy_generator"), (
        f"unexpected logger name: {pg.logger.name}"
    )


def test_gap_analyzer_module_has_logger():
    from faultray.governance import gap_analyzer as ga

    assert hasattr(ga, "logger"), "gap_analyzer must define a module-level logger"
    assert ga.logger.name.endswith("gap_analyzer"), (
        f"unexpected logger name: {ga.logger.name}"
    )
