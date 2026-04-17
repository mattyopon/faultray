# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""GraphQL-like API for FaultRay — zero external dependencies.

Provides a ``/graphql`` POST endpoint that accepts simplified GraphQL queries
and returns JSON responses.  No ``strawberry-graphql`` or other GraphQL library
is required; the query language is parsed with a lightweight recursive-descent
parser that supports the subset used by typical dashboard clients:

    { components { id name type replicas } }
    { simulationSummary { resilienceScore totalScenarios critical } }
    { availabilityLayers { name nines availabilityPercent annualDowntimeSeconds } }
    { resilienceScore }
    mutation { runSimulation { resilienceScore critical warning passed } }

Agent-specific queries (iteration 4)::

    { agentAssessment(topologyId: "default") { agentName riskScore riskLevel } }
    { agentMonitoringPlan(topologyId: "default") { rules { name metric threshold } } }
    { agentScenarios(topologyId: "default") { id name description } }
    { crossLayerRisk(topologyId: "default", componentId: "db-1") { agentId risk reason } }
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

graphql_router = APIRouter(tags=["graphql"])


# ---------------------------------------------------------------------------
# Lightweight GraphQL query parser
# ---------------------------------------------------------------------------

def _tokenize(query: str) -> list[str]:
    """Split a GraphQL-like query string into tokens.

    Supports identifiers, braces, parentheses, colons, commas, and
    quoted string literals (needed for field arguments).
    """
    return re.findall(r'"[^"]*"|[a-zA-Z_][a-zA-Z0-9_]*|[{}(),:!]', query)


def _parse_arguments(tokens: list[str], pos: int) -> tuple[dict[str, str], int]:
    """Parse ``(argName: "value", argName2: "value2")`` argument lists.

    Returns a dict of argument name → string value, and the new position.
    """
    if pos >= len(tokens) or tokens[pos] != '(':
        return {}, pos

    pos += 1  # skip '('
    args: dict[str, str] = {}

    while pos < len(tokens) and tokens[pos] != ')':
        arg_name = tokens[pos]
        pos += 1
        # skip ':'
        if pos < len(tokens) and tokens[pos] == ':':
            pos += 1
        # read value (may be quoted string or bare identifier)
        if pos < len(tokens):
            value = tokens[pos].strip('"')
            args[arg_name] = value
            pos += 1
        # skip optional ',' or '!'
        while pos < len(tokens) and tokens[pos] in (',', '!'):
            pos += 1

    if pos < len(tokens) and tokens[pos] == ')':
        pos += 1  # skip ')'

    return args, pos


def _parse_selection_set(tokens: list[str], pos: int) -> tuple[dict | list | None, int]:
    """Parse ``{ field1 field2 { subfield } }`` recursively.

    Returns a nested dict representing the selection set and the new position
    in the token stream.  Field values can be:

    - ``True`` for leaf fields
    - a nested dict for sub-selections
    - a ``("__args__", args_dict, sub_selection)`` tuple for fields with arguments
    """
    if pos >= len(tokens) or tokens[pos] != '{':
        return None, pos

    pos += 1  # skip '{'
    fields: dict[str, Any] = {}

    while pos < len(tokens) and tokens[pos] != '}':
        field_name = tokens[pos]
        pos += 1

        # Check for arguments: field(arg: "value")
        args: dict[str, str] = {}
        if pos < len(tokens) and tokens[pos] == '(':
            args, pos = _parse_arguments(tokens, pos)

        # Check for nested selection set
        if pos < len(tokens) and tokens[pos] == '{':
            sub, pos = _parse_selection_set(tokens, pos)
            if args:
                fields[field_name] = {"__args__": args, "__selection__": sub}
            else:
                fields[field_name] = sub
        else:
            if args:
                fields[field_name] = {"__args__": args, "__selection__": True}
            else:
                fields[field_name] = True  # leaf field

    if pos < len(tokens) and tokens[pos] == '}':
        pos += 1  # skip '}'

    return fields, pos


def _parse_query(query: str) -> tuple[str, dict]:
    """Parse a simplified GraphQL query.

    Returns ``(operation_type, selection_set)`` where *operation_type* is
    ``"query"`` or ``"mutation"``.
    """
    tokens = _tokenize(query)
    if not tokens:
        return "query", {}

    pos = 0
    operation = "query"

    if tokens[pos] in ("query", "mutation"):
        operation = tokens[pos]
        pos += 1

    selection, _ = _parse_selection_set(tokens, pos)
    return operation, selection or {}


# ---------------------------------------------------------------------------
# Field name conversion helpers
# ---------------------------------------------------------------------------

_CAMEL_RE = re.compile(r'([A-Z])')


def _camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    return _CAMEL_RE.sub(r'_\1', name).lower().lstrip('_')


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    parts = name.split('_')
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])


def _filter_dict(data: dict, selection: dict | bool) -> dict:
    """Filter *data* keys according to *selection*.

    If *selection* is ``True`` (leaf), return the value as-is.
    If *selection* is a dict, keep only keys that are present in the
    selection and recurse for nested selections.
    """
    if selection is True or selection is None:
        return data

    result: dict[str, Any] = {}
    for sel_key, sub_sel in selection.items():
        # Try both camelCase key and its snake_case equivalent
        snake_key = _camel_to_snake(sel_key)
        camel_key = _snake_to_camel(sel_key) if '_' in sel_key else sel_key

        value = None
        out_key = sel_key
        for candidate in (sel_key, snake_key, camel_key):
            if candidate in data:
                value = data[candidate]
                out_key = sel_key  # always return in the requested casing
                break

        if value is None:
            continue

        if isinstance(sub_sel, dict) and isinstance(value, dict):
            result[out_key] = _filter_dict(value, sub_sel)
        elif isinstance(sub_sel, dict) and isinstance(value, list):
            result[out_key] = [
                _filter_dict(item, sub_sel) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[out_key] = value

    return result


# ---------------------------------------------------------------------------
# Resolvers — each returns a plain dict / list
# ---------------------------------------------------------------------------

def _resolve_components() -> list[dict]:
    """Resolve the ``components`` field."""
    from faultray.api.server import get_graph

    graph = get_graph()
    result = []
    for comp in graph.components.values():
        result.append({
            "id": comp.id,
            "name": comp.name,
            "type": comp.type.value,
            "replicas": comp.replicas,
            "utilization": round(comp.utilization(), 2),
            "health": comp.health.value,
            "host": comp.host,
            "port": comp.port,
            "cpuPercent": comp.metrics.cpu_percent,
            "memoryPercent": comp.metrics.memory_percent,
        })
    return result


def _resolve_simulation_summary() -> dict | None:
    """Resolve the ``simulationSummary`` field."""
    from faultray.api.server import _last_report

    if _last_report is None:
        return None

    return {
        "resilienceScore": round(_last_report.resilience_score, 1),
        "totalScenarios": len(_last_report.results),
        "critical": len(_last_report.critical_findings),
        "warning": len(_last_report.warnings),
        "passed": len(_last_report.passed),
    }


def _resolve_availability_layers() -> list[dict]:
    """Resolve the ``availabilityLayers`` field."""
    from faultray.api.server import get_graph
    from faultray.simulator.availability_model import compute_five_layer_model

    graph = get_graph()
    if not graph.components:
        return []

    try:
        result = compute_five_layer_model(graph)
    except Exception:
        logger.debug("Could not compute availability layers", exc_info=True)
        return []

    def _safe_float(v: float) -> float:
        """Replace inf / nan with safe JSON-serialisable values."""
        if math.isinf(v):
            return 99.0 if v > 0 else -99.0
        if math.isnan(v):
            return 0.0
        return v

    layers = []
    for idx, (attr, label) in enumerate([
        ("layer1_software", "Software Limit"),
        ("layer2_hardware", "Hardware Limit"),
        ("layer3_theoretical", "Theoretical Limit"),
        ("layer4_operational", "Operational Limit"),
        ("layer5_external", "External SLA"),
    ], start=1):
        layer = getattr(result, attr, None)
        if layer is None:
            continue
        layers.append({
            "name": f"Layer {idx}: {label}",
            "nines": round(_safe_float(layer.nines), 2),
            "availabilityPercent": round(_safe_float(layer.availability * 100), 6),
            "annualDowntimeSeconds": round(_safe_float(layer.annual_downtime_seconds), 1),
        })
    return layers


def _resolve_resilience_score() -> float:
    """Resolve the ``resilienceScore`` scalar field."""
    from faultray.api.server import _last_report

    if _last_report is None:
        return 0.0
    return round(_last_report.resilience_score, 1)


def _resolve_resilience_score_v2() -> dict:
    """Resolve a v2 resilience score with breakdown."""
    from faultray.api.server import _last_report

    if _last_report is None:
        return {"score": 0.0, "breakdown": {}}

    total = len(_last_report.results)
    return {
        "score": round(_last_report.resilience_score, 1),
        "breakdown": {
            "totalScenarios": total,
            "critical": len(_last_report.critical_findings),
            "warning": len(_last_report.warnings),
            "passed": len(_last_report.passed),
            "criticalRatio": round(len(_last_report.critical_findings) / total, 3) if total else 0,
            "passedRatio": round(len(_last_report.passed) / total, 3) if total else 0,
        },
    }


def _mutation_run_simulation() -> dict:
    """Execute ``runSimulation`` mutation."""
    from faultray.api.server import get_graph
    from faultray.simulator.engine import SimulationEngine

    import faultray.api.server as _srv

    graph = get_graph()
    if not graph.components:
        return {
            "resilienceScore": 0.0,
            "totalScenarios": 0,
            "critical": 0,
            "warning": 0,
            "passed": 0,
        }

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults()
    _srv._last_report = report

    return {
        "resilienceScore": round(report.resilience_score, 1),
        "totalScenarios": len(report.results),
        "critical": len(report.critical_findings),
        "warning": len(report.warnings),
        "passed": len(report.passed),
    }


# ---------------------------------------------------------------------------
# Agent-specific resolvers (iteration 4)
# ---------------------------------------------------------------------------

def _resolve_agent_assessment(args: dict[str, str]) -> list[dict]:
    """Resolve ``agentAssessment(topologyId)`` — ADOPT risk assessment."""
    from faultray.api.server import get_graph
    from faultray.simulator.adoption_engine import AdoptionEngine

    graph = get_graph()
    engine = AdoptionEngine(graph)
    reports = engine.assess_all_agents()

    return [
        {
            "agentName": r.agent_name,
            "agentId": r.agent_id,
            "riskScore": r.risk_score,
            "riskLevel": r.risk_level.value,
            "maxBlastRadius": r.max_blast_radius,
            "hallucinationImpact": r.hallucination_impact,
            "safeToDeploy": r.safe_to_deploy,
            "failsafes": [
                {"name": f.name, "present": f.present, "description": f.description}
                for f in r.failsafes
            ],
            "recommendations": r.recommendations,
        }
        for r in reports
    ]


def _resolve_agent_monitoring_plan(args: dict[str, str]) -> dict:
    """Resolve ``agentMonitoringPlan(topologyId)`` — MANAGE monitoring plan."""
    from faultray.api.server import get_graph
    from faultray.simulator.agent_monitor import AgentMonitorEngine

    graph = get_graph()
    engine = AgentMonitorEngine(graph)
    plan = engine.generate_monitoring_plan()

    return {
        "totalComponentsMonitored": plan.total_components_monitored,
        "coveragePercent": plan.coverage_percent,
        "rules": [
            {
                "ruleId": r.rule_id,
                "name": r.name,
                "description": r.description,
                "componentId": r.component_id,
                "metric": r.metric,
                "threshold": r.threshold,
                "operator": r.operator,
                "predictedFault": r.predicted_fault.value,
                "severity": r.severity.value,
                "recommendedAction": r.recommended_action,
            }
            for r in plan.rules
        ],
    }


def _resolve_agent_scenarios(args: dict[str, str]) -> list[dict]:
    """Resolve ``agentScenarios(topologyId)`` — agent-specific scenarios."""
    from faultray.api.server import get_graph
    from faultray.simulator.agent_scenarios import generate_agent_scenarios

    graph = get_graph()
    scenarios = generate_agent_scenarios(graph)

    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "faults": [
                {"target": f.target_component_id, "type": f.fault_type.value}
                for f in s.faults
            ],
        }
        for s in scenarios
    ]


def _resolve_cross_layer_risk(args: dict[str, str]) -> list[dict]:
    """Resolve ``crossLayerRisk(topologyId, componentId)`` — hallucination risks."""
    from faultray.api.server import get_graph
    from faultray.simulator.agent_cascade import calculate_cross_layer_hallucination_risk

    component_id = args.get("componentId", "")
    if not component_id:
        return []

    graph = get_graph()
    risks = calculate_cross_layer_hallucination_risk(graph, component_id)

    return [
        {
            "agentId": agent_id,
            "risk": round(risk, 4),
            "reason": reason,
        }
        for agent_id, risk, reason in risks
    ]


# ---------------------------------------------------------------------------
# Root resolver dispatch
# ---------------------------------------------------------------------------

_QUERY_RESOLVERS: dict[str, Any] = {
    "components": _resolve_components,
    "simulationSummary": _resolve_simulation_summary,
    "simulation_summary": _resolve_simulation_summary,
    "availabilityLayers": _resolve_availability_layers,
    "availability_layers": _resolve_availability_layers,
    "resilienceScore": _resolve_resilience_score,
    "resilience_score": _resolve_resilience_score,
    "resilienceScoreV2": _resolve_resilience_score_v2,
    "resilience_score_v2": _resolve_resilience_score_v2,
    # Agent-specific resolvers (iteration 4) — accept args dict
    "agentAssessment": _resolve_agent_assessment,
    "agent_assessment": _resolve_agent_assessment,
    "agentMonitoringPlan": _resolve_agent_monitoring_plan,
    "agent_monitoring_plan": _resolve_agent_monitoring_plan,
    "agentScenarios": _resolve_agent_scenarios,
    "agent_scenarios": _resolve_agent_scenarios,
    "crossLayerRisk": _resolve_cross_layer_risk,
    "cross_layer_risk": _resolve_cross_layer_risk,
}

_MUTATION_RESOLVERS: dict[str, Any] = {
    "runSimulation": _mutation_run_simulation,
    "run_simulation": _mutation_run_simulation,
}


def _execute(operation: str, selection: dict) -> dict:
    """Execute a parsed query/mutation and return the data dict."""
    resolvers = _MUTATION_RESOLVERS if operation == "mutation" else _QUERY_RESOLVERS
    result: dict[str, Any] = {}

    for field_name, sub_selection in selection.items():
        resolver = resolvers.get(field_name)
        if resolver is None:
            # Try snake_case / camelCase variant
            alt = _camel_to_snake(field_name)
            resolver = resolvers.get(alt)
        if resolver is None:
            alt = _snake_to_camel(field_name)
            resolver = resolvers.get(alt)

        if resolver is None:
            result[field_name] = None
            continue

        # Extract arguments and actual selection from parsed field value
        args: dict[str, str] = {}
        actual_selection = sub_selection
        if isinstance(sub_selection, dict) and "__args__" in sub_selection:
            args = sub_selection["__args__"]
            actual_selection = sub_selection.get("__selection__", True)

        # Call resolver — with args if it accepts them, without otherwise
        try:
            value = resolver(args)
        except TypeError:
            value = resolver()

        # Apply sub-selection filtering
        if isinstance(actual_selection, dict):
            if isinstance(value, dict):
                value = _filter_dict(value, actual_selection)
            elif isinstance(value, list):
                value = [
                    _filter_dict(item, actual_selection) if isinstance(item, dict) else item
                    for item in value
                ]

        result[field_name] = value

    return result


# ---------------------------------------------------------------------------
# FastAPI endpoint
# ---------------------------------------------------------------------------

@graphql_router.post("/graphql")
async def graphql_endpoint(request: Request):
    """Handle a simplified GraphQL query.

    Expects a JSON body with a ``query`` string::

        { "query": "{ components { id name type } }" }
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"errors": [{"message": "Invalid JSON body"}]},
            status_code=400,
        )

    query_str = body.get("query", "")
    if not query_str:
        return JSONResponse(
            {"errors": [{"message": "Missing 'query' field"}]},
            status_code=400,
        )

    try:
        operation, selection = _parse_query(query_str)
        data = _execute(operation, selection)
        return JSONResponse({"data": data})
    except Exception as exc:
        logger.error("GraphQL execution error: %s", exc, exc_info=True)
        return JSONResponse(
            {"errors": [{"message": str(exc)}]},
            status_code=500,
        )
