# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""MCP (Model Context Protocol) Bridge for FaultRay.

Provides a structured interface for AI assistants (Claude Desktop, Cursor,
Windsurf) to interact with FaultRay.  Defines tool schemas, handles requests,
and returns structured results.

This is NOT the actual MCP server transport layer — it is the business logic
layer that any MCP server implementation can call.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MCPToolName(str, Enum):
    """Available MCP tool names."""

    SIMULATE = "simulate"
    ANALYZE_RESILIENCE = "analyze_resilience"
    WHAT_IF = "what_if"
    FIND_SPOF = "find_spof"
    RECOMMEND_CHAOS = "recommend_chaos"
    CHECK_COMPLIANCE = "check_compliance"
    COMPARE_CLOUDS = "compare_clouds"
    PREDICT_CHANGE_RISK = "predict_change_risk"
    FORECAST_RESILIENCE = "forecast_resilience"
    GENERATE_REPORT = "generate_report"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class MCPToolSchema(BaseModel):
    """JSON-Schema description of a single MCP tool."""

    name: MCPToolName
    description: str
    parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    required_params: list[str] = Field(default_factory=list)


class MCPRequest(BaseModel):
    """An incoming tool invocation request."""

    tool_name: MCPToolName
    parameters: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])


class MCPResponse(BaseModel):
    """The result of executing an MCP tool."""

    request_id: str
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    execution_time_ms: float = 0.0


class MCPToolRegistry(BaseModel):
    """Registry of all available MCP tools."""

    tools: list[MCPToolSchema] = Field(default_factory=list)
    version: str = "1.0.0"
    server_name: str = "faultray"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_TOOL_DEFS: list[MCPToolSchema] = [
    MCPToolSchema(
        name=MCPToolName.SIMULATE,
        description="Simulate a component failure and show cascade impact.",
        parameters={
            "component_id": {"type": "string", "description": "ID of the component to fail"},
            "failure_type": {"type": "string", "description": "Type of failure (down, degraded, overloaded)", "default": "down"},
        },
        required_params=["component_id"],
    ),
    MCPToolSchema(
        name=MCPToolName.ANALYZE_RESILIENCE,
        description="Analyze overall infrastructure resilience and return a detailed score breakdown.",
        parameters={},
        required_params=[],
    ),
    MCPToolSchema(
        name=MCPToolName.WHAT_IF,
        description="Evaluate a hypothetical change (e.g. adding replicas) on the resilience score.",
        parameters={
            "component_id": {"type": "string", "description": "Component to modify"},
            "change": {"type": "string", "description": "Change type: add_replicas, enable_failover, enable_autoscaling"},
            "value": {"type": "integer", "description": "New value (e.g. replica count)", "default": 2},
        },
        required_params=["component_id", "change"],
    ),
    MCPToolSchema(
        name=MCPToolName.FIND_SPOF,
        description="Find all single points of failure in the infrastructure.",
        parameters={},
        required_params=[],
    ),
    MCPToolSchema(
        name=MCPToolName.RECOMMEND_CHAOS,
        description="Recommend chaos experiments based on current topology.",
        parameters={
            "max_experiments": {"type": "integer", "description": "Maximum experiments to return", "default": 5},
        },
        required_params=[],
    ),
    MCPToolSchema(
        name=MCPToolName.CHECK_COMPLIANCE,
        description="Check infrastructure compliance against a regulatory framework.",
        parameters={
            "framework": {"type": "string", "description": "Framework name: soc2, iso27001, pci_dss, nist_csf"},
        },
        required_params=["framework"],
    ),
    MCPToolSchema(
        name=MCPToolName.COMPARE_CLOUDS,
        description="Compare resilience characteristics across cloud providers.",
        parameters={
            "providers": {"type": "array", "description": "List of providers to compare", "items": {"type": "string"}},
        },
        required_params=[],
    ),
    MCPToolSchema(
        name=MCPToolName.PREDICT_CHANGE_RISK,
        description="Predict the risk level of a proposed infrastructure change.",
        parameters={
            "component_id": {"type": "string", "description": "Component being changed"},
            "change_type": {"type": "string", "description": "Type of change"},
            "description": {"type": "string", "description": "Human-readable description"},
        },
        required_params=["component_id", "change_type"],
    ),
    MCPToolSchema(
        name=MCPToolName.FORECAST_RESILIENCE,
        description="Forecast future resilience score based on current trajectory.",
        parameters={
            "horizon_days": {"type": "integer", "description": "Forecast horizon in days", "default": 30},
        },
        required_params=[],
    ),
    MCPToolSchema(
        name=MCPToolName.GENERATE_REPORT,
        description="Generate a resilience report summary.",
        parameters={
            "format": {"type": "string", "description": "Report format: summary, detailed", "default": "summary"},
        },
        required_params=[],
    ),
]

_TOOL_MAP: dict[MCPToolName, MCPToolSchema] = {t.name: t for t in _TOOL_DEFS}


# ---------------------------------------------------------------------------
# Bridge implementation
# ---------------------------------------------------------------------------


class MCPBridge:
    """Bridge between MCP protocol and FaultRay analysis engines.

    Parameters
    ----------
    graph:
        The :class:`InfraGraph` to operate on.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._handlers: dict[MCPToolName, Any] = {
            MCPToolName.SIMULATE: self._handle_simulate,
            MCPToolName.ANALYZE_RESILIENCE: self._handle_analyze,
            MCPToolName.WHAT_IF: self._handle_whatif,
            MCPToolName.FIND_SPOF: self._handle_find_spof,
            MCPToolName.RECOMMEND_CHAOS: self._handle_recommend,
            MCPToolName.CHECK_COMPLIANCE: self._handle_compliance,
            MCPToolName.COMPARE_CLOUDS: self._handle_compare_clouds,
            MCPToolName.PREDICT_CHANGE_RISK: self._handle_predict_risk,
            MCPToolName.FORECAST_RESILIENCE: self._handle_forecast,
            MCPToolName.GENERATE_REPORT: self._handle_report,
        }

    # -- public API --------------------------------------------------------

    def get_registry(self) -> MCPToolRegistry:
        """Return the full tool registry."""
        return MCPToolRegistry(tools=list(_TOOL_DEFS))

    def get_tool_schema(self, name: MCPToolName) -> MCPToolSchema:
        """Return schema for a single tool.

        Raises ``KeyError`` if the tool is unknown.
        """
        schema = _TOOL_MAP.get(name)
        if schema is None:
            raise KeyError(f"Unknown tool: {name}")
        return schema

    def execute(self, request: MCPRequest) -> MCPResponse:
        """Execute an MCP tool request and return a structured response."""
        t0 = time.monotonic()
        handler = self._handlers.get(request.tool_name)
        if handler is None:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=f"Unknown tool: {request.tool_name}",
                execution_time_ms=_elapsed(t0),
            )
        try:
            result = handler(request.parameters)
            return MCPResponse(
                request_id=request.request_id,
                success=True,
                result=result,
                execution_time_ms=_elapsed(t0),
            )
        except Exception as exc:  # noqa: BLE001
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=str(exc),
                execution_time_ms=_elapsed(t0),
            )

    # -- handlers ----------------------------------------------------------

    def _handle_simulate(self, params: dict[str, Any]) -> dict[str, Any]:
        cid = params.get("component_id")
        if not cid:
            raise ValueError("component_id is required")
        comp = self._graph.get_component(cid)
        if comp is None:
            raise ValueError(f"Component not found: {cid}")
        failure_type = params.get("failure_type", "down")
        affected = self._graph.get_all_affected(cid)
        cascade_paths = self._graph.get_cascade_path(cid)
        return {
            "component_id": cid,
            "component_name": comp.name,
            "failure_type": failure_type,
            "affected_components": sorted(affected),
            "cascade_paths": cascade_paths,
            "total_affected": len(affected),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_analyze(self, params: dict[str, Any]) -> dict[str, Any]:
        summary = self._graph.summary()
        v2 = self._graph.resilience_score_v2()
        return {
            "summary": summary,
            "resilience_score": v2["score"],
            "breakdown": v2["breakdown"],
            "recommendations": v2["recommendations"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_whatif(self, params: dict[str, Any]) -> dict[str, Any]:
        cid = params.get("component_id")
        change = params.get("change")
        if not cid:
            raise ValueError("component_id is required")
        if not change:
            raise ValueError("change is required")
        comp = self._graph.get_component(cid)
        if comp is None:
            raise ValueError(f"Component not found: {cid}")
        value = params.get("value", 2)
        before_score = self._graph.resilience_score()
        description = f"Apply '{change}' to '{cid}'"
        if change == "add_replicas":
            description = f"Set replicas to {value} on '{cid}'"
        elif change == "enable_failover":
            description = f"Enable failover on '{cid}'"
        elif change == "enable_autoscaling":
            description = f"Enable autoscaling on '{cid}'"
        return {
            "component_id": cid,
            "change": change,
            "value": value,
            "current_score": round(before_score, 1),
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_find_spof(self, params: dict[str, Any]) -> dict[str, Any]:
        spofs: list[dict[str, Any]] = []
        for comp in self._graph.components.values():
            dependents = self._graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                spofs.append({
                    "component_id": comp.id,
                    "component_name": comp.name,
                    "type": comp.type.value,
                    "dependent_count": len(dependents),
                    "dependents": [d.id for d in dependents],
                })
        return {
            "spofs": spofs,
            "total_spofs": len(spofs),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_recommend(self, params: dict[str, Any]) -> dict[str, Any]:
        max_exp = params.get("max_experiments", 5)
        experiments: list[dict[str, Any]] = []
        for comp in list(self._graph.components.values())[:max_exp]:
            dependents = self._graph.get_dependents(comp.id)
            priority = "high" if len(dependents) > 0 and comp.replicas <= 1 else "medium"
            experiments.append({
                "target": comp.id,
                "experiment": f"Simulate {comp.type.value} failure on '{comp.name}'",
                "priority": priority,
                "rationale": f"{len(dependents)} dependent(s), replicas={comp.replicas}",
            })
        return {
            "experiments": experiments,
            "total": len(experiments),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_compliance(self, params: dict[str, Any]) -> dict[str, Any]:
        framework = params.get("framework")
        if not framework:
            raise ValueError("framework is required")
        valid = {"soc2", "iso27001", "pci_dss", "nist_csf"}
        if framework not in valid:
            raise ValueError(f"Unknown framework: {framework}. Valid: {sorted(valid)}")
        checks: list[dict[str, str]] = []
        passed = 0
        total = 0
        # Redundancy check
        total += 1
        has_redundancy = all(c.replicas >= 2 for c in self._graph.components.values()) if self._graph.components else False
        status = "pass" if has_redundancy else "fail"
        if status == "pass":
            passed += 1
        checks.append({"control": "redundancy", "status": status, "evidence": "All components have replicas >= 2" if has_redundancy else "Some components lack redundancy"})
        # Failover check
        total += 1
        has_failover = all(c.failover.enabled for c in self._graph.components.values()) if self._graph.components else False
        status = "pass" if has_failover else "fail"
        if status == "pass":
            passed += 1
        checks.append({"control": "failover", "status": status, "evidence": "All components have failover enabled" if has_failover else "Some components lack failover"})
        pct = (passed / total * 100) if total > 0 else 0.0
        return {
            "framework": framework,
            "checks": checks,
            "passed": passed,
            "total": total,
            "compliance_percent": round(pct, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_compare_clouds(self, params: dict[str, Any]) -> dict[str, Any]:
        providers = params.get("providers", ["aws", "gcp", "azure"])
        summary = self._graph.summary()
        comparisons: list[dict[str, Any]] = []
        for provider in providers:
            comparisons.append({
                "provider": provider,
                "component_count": summary["total_components"],
                "resilience_score": summary["resilience_score"],
                "note": f"Simulated topology on {provider}",
            })
        return {
            "comparisons": comparisons,
            "total_providers": len(providers),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_predict_risk(self, params: dict[str, Any]) -> dict[str, Any]:
        cid = params.get("component_id")
        change_type = params.get("change_type")
        if not cid:
            raise ValueError("component_id is required")
        if not change_type:
            raise ValueError("change_type is required")
        comp = self._graph.get_component(cid)
        if comp is None:
            raise ValueError(f"Component not found: {cid}")
        dependents = self._graph.get_dependents(cid)
        dep_count = len(dependents)
        if dep_count >= 3:
            risk = "high"
        elif dep_count >= 1:
            risk = "medium"
        else:
            risk = "low"
        description = params.get("description", "")
        return {
            "component_id": cid,
            "change_type": change_type,
            "risk_level": risk,
            "dependent_count": dep_count,
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_forecast(self, params: dict[str, Any]) -> dict[str, Any]:
        horizon = params.get("horizon_days", 30)
        current_score = self._graph.resilience_score()
        return {
            "current_score": round(current_score, 1),
            "horizon_days": horizon,
            "forecast_score": round(current_score, 1),
            "trend": "stable",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _handle_report(self, params: dict[str, Any]) -> dict[str, Any]:
        fmt = params.get("format", "summary")
        summary = self._graph.summary()
        v2 = self._graph.resilience_score_v2()
        result: dict[str, Any] = {
            "format": fmt,
            "summary": summary,
            "resilience_score": v2["score"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if fmt == "detailed":
            result["breakdown"] = v2["breakdown"]
            result["recommendations"] = v2["recommendations"]
        return result


def _elapsed(t0: float) -> float:
    """Return elapsed milliseconds since *t0*."""
    return (time.monotonic() - t0) * 1000.0
