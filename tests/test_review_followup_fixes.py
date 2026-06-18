# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Regression tests for the dual-model review follow-up fixes.

- ENG-MATH-1: compound-scenario merge must dedupe effects by component so a node
  faulted by multiple sub-scenarios is not double-counted in severity.
- ENG-MATH-2: SimulationReport.simulated_resilience_score must move with critical
  findings (the static resilience_score stays structural).
- ENG-MATH-3: ScoreDecomposition.penalties_total must include the host-colocation
  penalty so the breakdown reconciles with total_score.
- ENG-9: the embeddable widget must HTML-escape the reflected project_id.
"""
from __future__ import annotations

import asyncio

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect, dedupe_worst_effects
from faultray.simulator.engine import ScenarioResult, SimulationReport
from faultray.simulator.scenarios import Scenario
from faultray.simulator.score_decomposition import ScoreDecomposer


# --- ENG-MATH-1: dedupe_worst_effects -------------------------------------
def _eff(cid: str, health: HealthStatus) -> CascadeEffect:
    return CascadeEffect(component_id=cid, component_name=cid, health=health, reason="t")


def test_dedupe_keeps_one_worst_effect_per_component():
    effects = [
        _eff("a", HealthStatus.DEGRADED),
        _eff("a", HealthStatus.DOWN),       # same component, worse
        _eff("b", HealthStatus.OVERLOADED),
    ]
    out = dedupe_worst_effects(effects)
    by_id = {e.component_id: e.health for e in out}
    assert len(out) == 2  # 'a' collapsed to one
    assert by_id["a"] == HealthStatus.DOWN  # worst health kept
    assert by_id["b"] == HealthStatus.OVERLOADED


def test_duplicate_effect_does_not_inflate_severity():
    # A single DOWN component should hit the affected_count<=1 cap (3.0). A
    # double-counted duplicate would push affected_count to 2 and escape the cap.
    one = CascadeChain(trigger="t", total_components=2, likelihood=1.0)
    one.effects = [_eff("a", HealthStatus.DOWN)]
    dup = CascadeChain(trigger="t", total_components=2, likelihood=1.0)
    dup.effects = [_eff("a", HealthStatus.DOWN), _eff("a", HealthStatus.DOWN)]
    deduped = CascadeChain(trigger="t", total_components=2, likelihood=1.0)
    deduped.effects = dedupe_worst_effects(dup.effects)
    assert deduped.severity == one.severity
    assert deduped.severity <= 3.0


# --- ENG-MATH-2: simulated_resilience_score -------------------------------
def _result(risk: float) -> ScenarioResult:
    return ScenarioResult(
        scenario=Scenario(id="s", name="n", description="d", faults=[]),
        cascade=CascadeChain(trigger="t"),
        risk_score=risk,
    )


def test_simulated_score_drops_with_critical_findings():
    report = SimulationReport(
        results=[_result(9.0), _result(8.0)],  # both critical (>=7.0)
        resilience_score=80.0,
    )
    assert report.simulated_resilience_score < 80.0


def test_simulated_score_equals_static_when_no_critical():
    report = SimulationReport(
        results=[_result(1.0), _result(2.0)],  # none critical
        resilience_score=80.0,
    )
    assert report.simulated_resilience_score == 80.0
    # And with no scenarios at all.
    assert SimulationReport(resilience_score=77.0).simulated_resilience_score == 77.0


# --- ENG-MATH-3: penalties_total reconciles with total_score --------------
def test_penalties_total_includes_host_penalty():
    g = InfraGraph()
    # replicas>=2 + a host + a dependent triggers the host-colocation penalty.
    g.add_component(
        Component(
            id="db", name="db", type=ComponentType.DATABASE,
            replicas=2, host="host-1", failover=FailoverConfig(enabled=False),
        )
    )
    g.add_component(Component(id="web", name="web", type=ComponentType.APP_SERVER))
    g.add_dependency(Dependency(source_id="web", target_id="db", dependency_type="requires"))

    result = ScoreDecomposer().decompose(g)
    # The waterfall must reconcile: base_score - penalties_total == total_score.
    assert round(result.base_score - result.penalties_total, 1) == round(result.total_score, 1)


# --- ENG-9: widget reflected-XSS escaping ---------------------------------
def test_widget_escapes_project_id():
    from faultray.api.widget import scorecard_widget

    payload = "<script>alert(1)</script>"
    resp = asyncio.run(scorecard_widget(project_id=payload))
    body = resp.body.decode() if isinstance(resp.body, bytes) else resp.body
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
