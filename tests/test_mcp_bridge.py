"""Tests for MCP Bridge — 130+ tests targeting 100% coverage."""

import time
import uuid

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.mcp_bridge import (
    MCPBridge,
    MCPRequest,
    MCPResponse,
    MCPToolName,
    MCPToolRegistry,
    MCPToolSchema,
    _TOOL_DEFS,
    _TOOL_MAP,
    _elapsed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    *,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
    cpu: float = 0.0,
    memory: float = 0.0,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        health=health,
        metrics=ResourceMetrics(cpu_percent=cpu, memory_percent=memory),
    )


def _graph(
    *components: Component,
    deps: list[tuple[str, str]] | None = None,
) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in deps or []:
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


def _simple_graph() -> InfraGraph:
    """A minimal graph: lb -> app -> db."""
    return _graph(
        _comp("lb", ComponentType.LOAD_BALANCER),
        _comp("app", ComponentType.APP_SERVER),
        _comp("db", ComponentType.DATABASE),
        deps=[("lb", "app"), ("app", "db")],
    )


def _redundant_graph() -> InfraGraph:
    """All components have replicas >= 2 and failover enabled."""
    return _graph(
        _comp("lb", ComponentType.LOAD_BALANCER, replicas=3, failover=True),
        _comp("app", ComponentType.APP_SERVER, replicas=3, failover=True),
        _comp("db", ComponentType.DATABASE, replicas=2, failover=True),
        deps=[("lb", "app"), ("app", "db")],
    )


def _empty_graph() -> InfraGraph:
    return InfraGraph()


def _single_component_graph() -> InfraGraph:
    return _graph(_comp("solo"))


# ===========================================================================
# MCPToolName enum
# ===========================================================================


class TestMCPToolName:
    def test_all_values(self):
        assert len(MCPToolName) == 10

    def test_simulate_value(self):
        assert MCPToolName.SIMULATE == "simulate"

    def test_analyze_resilience_value(self):
        assert MCPToolName.ANALYZE_RESILIENCE == "analyze_resilience"

    def test_what_if_value(self):
        assert MCPToolName.WHAT_IF == "what_if"

    def test_find_spof_value(self):
        assert MCPToolName.FIND_SPOF == "find_spof"

    def test_recommend_chaos_value(self):
        assert MCPToolName.RECOMMEND_CHAOS == "recommend_chaos"

    def test_check_compliance_value(self):
        assert MCPToolName.CHECK_COMPLIANCE == "check_compliance"

    def test_compare_clouds_value(self):
        assert MCPToolName.COMPARE_CLOUDS == "compare_clouds"

    def test_predict_change_risk_value(self):
        assert MCPToolName.PREDICT_CHANGE_RISK == "predict_change_risk"

    def test_forecast_resilience_value(self):
        assert MCPToolName.FORECAST_RESILIENCE == "forecast_resilience"

    def test_generate_report_value(self):
        assert MCPToolName.GENERATE_REPORT == "generate_report"

    def test_str_enum(self):
        assert isinstance(MCPToolName.SIMULATE, str)


# ===========================================================================
# Pydantic models
# ===========================================================================


class TestMCPToolSchema:
    def test_create_minimal(self):
        schema = MCPToolSchema(name=MCPToolName.SIMULATE, description="test")
        assert schema.name == MCPToolName.SIMULATE
        assert schema.description == "test"
        assert schema.parameters == {}
        assert schema.required_params == []

    def test_create_full(self):
        schema = MCPToolSchema(
            name=MCPToolName.WHAT_IF,
            description="what-if",
            parameters={"x": {"type": "string"}},
            required_params=["x"],
        )
        assert schema.required_params == ["x"]
        assert "x" in schema.parameters


class TestMCPRequest:
    def test_defaults(self):
        req = MCPRequest(tool_name=MCPToolName.FIND_SPOF)
        assert req.tool_name == MCPToolName.FIND_SPOF
        assert req.parameters == {}
        assert len(req.request_id) == 12

    def test_custom_request_id(self):
        req = MCPRequest(tool_name=MCPToolName.SIMULATE, request_id="abc123")
        assert req.request_id == "abc123"

    def test_with_parameters(self):
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "web"},
        )
        assert req.parameters["component_id"] == "web"


class TestMCPResponse:
    def test_success_response(self):
        resp = MCPResponse(request_id="r1", success=True, result={"ok": 1})
        assert resp.success
        assert resp.result == {"ok": 1}
        assert resp.error is None

    def test_error_response(self):
        resp = MCPResponse(request_id="r1", success=False, error="boom")
        assert not resp.success
        assert resp.error == "boom"
        assert resp.result is None

    def test_execution_time(self):
        resp = MCPResponse(request_id="r1", success=True, execution_time_ms=42.5)
        assert resp.execution_time_ms == 42.5

    def test_defaults(self):
        resp = MCPResponse(request_id="x", success=True)
        assert resp.execution_time_ms == 0.0
        assert resp.result is None


class TestMCPToolRegistry:
    def test_defaults(self):
        reg = MCPToolRegistry()
        assert reg.tools == []
        assert reg.version == "1.0.0"
        assert reg.server_name == "faultray"

    def test_custom(self):
        reg = MCPToolRegistry(version="2.0", server_name="custom")
        assert reg.version == "2.0"
        assert reg.server_name == "custom"


# ===========================================================================
# Module-level constants
# ===========================================================================


class TestToolDefinitions:
    def test_tool_defs_count(self):
        assert len(_TOOL_DEFS) == 10

    def test_tool_map_count(self):
        assert len(_TOOL_MAP) == 10

    def test_all_names_covered(self):
        for name in MCPToolName:
            assert name in _TOOL_MAP

    def test_each_def_has_description(self):
        for td in _TOOL_DEFS:
            assert td.description

    def test_simulate_required_params(self):
        schema = _TOOL_MAP[MCPToolName.SIMULATE]
        assert "component_id" in schema.required_params

    def test_compliance_required_params(self):
        schema = _TOOL_MAP[MCPToolName.CHECK_COMPLIANCE]
        assert "framework" in schema.required_params

    def test_predict_risk_required_params(self):
        schema = _TOOL_MAP[MCPToolName.PREDICT_CHANGE_RISK]
        assert "component_id" in schema.required_params
        assert "change_type" in schema.required_params

    def test_whatif_required_params(self):
        schema = _TOOL_MAP[MCPToolName.WHAT_IF]
        assert "component_id" in schema.required_params
        assert "change" in schema.required_params


# ===========================================================================
# _elapsed helper
# ===========================================================================


class TestElapsed:
    def test_positive(self):
        t0 = time.monotonic()
        val = _elapsed(t0)
        assert val >= 0.0

    def test_is_float(self):
        assert isinstance(_elapsed(time.monotonic()), float)


# ===========================================================================
# MCPBridge — construction & registry
# ===========================================================================


class TestMCPBridgeInit:
    def test_init_stores_graph(self):
        g = _empty_graph()
        bridge = MCPBridge(g)
        assert bridge._graph is g

    def test_handlers_registered(self):
        bridge = MCPBridge(_empty_graph())
        assert len(bridge._handlers) == 10

    def test_all_tool_names_have_handlers(self):
        bridge = MCPBridge(_empty_graph())
        for name in MCPToolName:
            assert name in bridge._handlers


class TestGetRegistry:
    def test_returns_registry(self):
        bridge = MCPBridge(_empty_graph())
        reg = bridge.get_registry()
        assert isinstance(reg, MCPToolRegistry)

    def test_registry_has_all_tools(self):
        bridge = MCPBridge(_empty_graph())
        reg = bridge.get_registry()
        assert len(reg.tools) == 10

    def test_registry_version(self):
        reg = MCPBridge(_empty_graph()).get_registry()
        assert reg.version == "1.0.0"

    def test_registry_server_name(self):
        reg = MCPBridge(_empty_graph()).get_registry()
        assert reg.server_name == "faultray"


class TestGetToolSchema:
    def test_known_tool(self):
        bridge = MCPBridge(_empty_graph())
        schema = bridge.get_tool_schema(MCPToolName.SIMULATE)
        assert schema.name == MCPToolName.SIMULATE

    def test_all_tools_retrievable(self):
        bridge = MCPBridge(_empty_graph())
        for name in MCPToolName:
            schema = bridge.get_tool_schema(name)
            assert schema.name == name

    def test_unknown_tool_raises_key_error(self):
        """Covers the KeyError branch when _TOOL_MAP lacks the name."""
        import faultray.simulator.mcp_bridge as mod

        bridge = MCPBridge(_empty_graph())
        original = mod._TOOL_MAP.copy()
        # Temporarily remove one entry
        removed_key = MCPToolName.SIMULATE
        del mod._TOOL_MAP[removed_key]
        try:
            with pytest.raises(KeyError, match="Unknown tool"):
                bridge.get_tool_schema(removed_key)
        finally:
            mod._TOOL_MAP.update(original)


# ===========================================================================
# MCPBridge.execute — general
# ===========================================================================


class TestExecuteGeneral:
    def test_returns_mcp_response(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(tool_name=MCPToolName.FIND_SPOF)
        resp = bridge.execute(req)
        assert isinstance(resp, MCPResponse)

    def test_preserves_request_id(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(tool_name=MCPToolName.FIND_SPOF, request_id="myid")
        resp = bridge.execute(req)
        assert resp.request_id == "myid"

    def test_execution_time_is_positive(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(tool_name=MCPToolName.FIND_SPOF)
        resp = bridge.execute(req)
        assert resp.execution_time_ms >= 0.0

    def test_success_on_valid_request(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE)
        resp = bridge.execute(req)
        assert resp.success

    def test_unknown_handler_returns_error(self):
        """Covers the branch when _handlers lacks the tool_name."""
        bridge = MCPBridge(_simple_graph())
        # Temporarily remove a handler
        removed_key = MCPToolName.SIMULATE
        handler = bridge._handlers.pop(removed_key)
        try:
            req = MCPRequest(tool_name=removed_key, request_id="unk")
            resp = bridge.execute(req)
            assert not resp.success
            assert "Unknown tool" in resp.error
            assert resp.request_id == "unk"
            assert resp.execution_time_ms >= 0.0
        finally:
            bridge._handlers[removed_key] = handler


# ===========================================================================
# _handle_simulate
# ===========================================================================


class TestHandleSimulate:
    def test_success(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "db"},
        )
        resp = bridge.execute(req)
        assert resp.success
        assert resp.result["component_id"] == "db"

    def test_failure_type_default(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "db"},
        )
        resp = bridge.execute(req)
        assert resp.result["failure_type"] == "down"

    def test_failure_type_custom(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "db", "failure_type": "degraded"},
        )
        resp = bridge.execute(req)
        assert resp.result["failure_type"] == "degraded"

    def test_affected_components(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "db"},
        )
        resp = bridge.execute(req)
        # app depends on db, lb depends on app
        assert resp.result["total_affected"] >= 1

    def test_cascade_paths(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "db"},
        )
        resp = bridge.execute(req)
        assert isinstance(resp.result["cascade_paths"], list)

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "app"},
        )
        resp = bridge.execute(req)
        assert "timestamp" in resp.result

    def test_missing_component_id(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(tool_name=MCPToolName.SIMULATE, parameters={})
        resp = bridge.execute(req)
        assert not resp.success
        assert "component_id" in resp.error

    def test_unknown_component(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "nonexistent"},
        )
        resp = bridge.execute(req)
        assert not resp.success
        assert "not found" in resp.error.lower()

    def test_component_name_in_result(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "lb"},
        )
        resp = bridge.execute(req)
        assert resp.result["component_name"] == "lb"

    def test_affected_sorted(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.SIMULATE,
            parameters={"component_id": "db"},
        )
        resp = bridge.execute(req)
        affected = resp.result["affected_components"]
        assert affected == sorted(affected)


# ===========================================================================
# _handle_analyze
# ===========================================================================


class TestHandleAnalyze:
    def test_success(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE)
        resp = bridge.execute(req)
        assert resp.success

    def test_has_summary(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE))
        assert "summary" in resp.result

    def test_has_resilience_score(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE))
        assert "resilience_score" in resp.result
        assert isinstance(resp.result["resilience_score"], float)

    def test_has_breakdown(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE))
        assert "breakdown" in resp.result

    def test_has_recommendations(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE))
        assert "recommendations" in resp.result

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE))
        assert "timestamp" in resp.result

    def test_empty_graph(self):
        bridge = MCPBridge(_empty_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE))
        assert resp.success
        assert resp.result["resilience_score"] == 0.0

    def test_redundant_graph_higher_score(self):
        simple_bridge = MCPBridge(_simple_graph())
        redundant_bridge = MCPBridge(_redundant_graph())
        s_resp = simple_bridge.execute(MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE))
        r_resp = redundant_bridge.execute(MCPRequest(tool_name=MCPToolName.ANALYZE_RESILIENCE))
        assert r_resp.result["resilience_score"] >= s_resp.result["resilience_score"]


# ===========================================================================
# _handle_whatif
# ===========================================================================


class TestHandleWhatIf:
    def test_success(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "app", "change": "add_replicas", "value": 3},
        )
        resp = bridge.execute(req)
        assert resp.success
        assert resp.result["component_id"] == "app"

    def test_add_replicas_description(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "app", "change": "add_replicas", "value": 5},
        )
        resp = bridge.execute(req)
        assert "replicas" in resp.result["description"].lower()
        assert "5" in resp.result["description"]

    def test_enable_failover_description(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "db", "change": "enable_failover"},
        )
        resp = bridge.execute(req)
        assert "failover" in resp.result["description"].lower()

    def test_enable_autoscaling_description(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "app", "change": "enable_autoscaling"},
        )
        resp = bridge.execute(req)
        assert "autoscaling" in resp.result["description"].lower()

    def test_generic_change_description(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "app", "change": "custom_change"},
        )
        resp = bridge.execute(req)
        assert "custom_change" in resp.result["description"]

    def test_default_value(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "app", "change": "add_replicas"},
        )
        resp = bridge.execute(req)
        assert resp.result["value"] == 2

    def test_missing_component_id(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"change": "add_replicas"},
        )
        resp = bridge.execute(req)
        assert not resp.success
        assert "component_id" in resp.error

    def test_missing_change(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "app"},
        )
        resp = bridge.execute(req)
        assert not resp.success
        assert "change" in resp.error

    def test_unknown_component(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "nope", "change": "x"},
        )
        resp = bridge.execute(req)
        assert not resp.success
        assert "not found" in resp.error.lower()

    def test_has_current_score(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "app", "change": "add_replicas"},
        )
        resp = bridge.execute(req)
        assert "current_score" in resp.result

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.WHAT_IF,
            parameters={"component_id": "app", "change": "add_replicas"},
        )
        resp = bridge.execute(req)
        assert "timestamp" in resp.result


# ===========================================================================
# _handle_find_spof
# ===========================================================================


class TestHandleFindSpof:
    def test_finds_spofs(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FIND_SPOF))
        assert resp.success
        assert resp.result["total_spofs"] >= 1

    def test_no_spofs_in_redundant_graph(self):
        bridge = MCPBridge(_redundant_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FIND_SPOF))
        assert resp.success
        assert resp.result["total_spofs"] == 0

    def test_empty_graph(self):
        bridge = MCPBridge(_empty_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FIND_SPOF))
        assert resp.success
        assert resp.result["total_spofs"] == 0

    def test_spof_fields(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FIND_SPOF))
        if resp.result["total_spofs"] > 0:
            spof = resp.result["spofs"][0]
            assert "component_id" in spof
            assert "component_name" in spof
            assert "type" in spof
            assert "dependent_count" in spof
            assert "dependents" in spof

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FIND_SPOF))
        assert "timestamp" in resp.result

    def test_single_component_no_deps(self):
        bridge = MCPBridge(_single_component_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FIND_SPOF))
        assert resp.result["total_spofs"] == 0

    def test_spof_dependent_list(self):
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"),
            deps=[("b", "a"), ("c", "a")],
        )
        bridge = MCPBridge(g)
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FIND_SPOF))
        spofs = resp.result["spofs"]
        # 'a' has 2 dependents and replicas=1
        a_spof = [s for s in spofs if s["component_id"] == "a"]
        assert len(a_spof) == 1
        assert a_spof[0]["dependent_count"] == 2


# ===========================================================================
# _handle_recommend
# ===========================================================================


class TestHandleRecommend:
    def test_success(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.RECOMMEND_CHAOS))
        assert resp.success
        assert resp.result["total"] > 0

    def test_max_experiments_default(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.RECOMMEND_CHAOS))
        assert resp.result["total"] <= 5

    def test_max_experiments_custom(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.RECOMMEND_CHAOS,
            parameters={"max_experiments": 2},
        )
        resp = bridge.execute(req)
        assert resp.result["total"] <= 2

    def test_experiment_fields(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.RECOMMEND_CHAOS))
        exp = resp.result["experiments"][0]
        assert "target" in exp
        assert "experiment" in exp
        assert "priority" in exp
        assert "rationale" in exp

    def test_empty_graph(self):
        bridge = MCPBridge(_empty_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.RECOMMEND_CHAOS))
        assert resp.success
        assert resp.result["total"] == 0

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.RECOMMEND_CHAOS))
        assert "timestamp" in resp.result

    def test_priority_is_high_for_spof(self):
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[("b", "a")],
        )
        bridge = MCPBridge(g)
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.RECOMMEND_CHAOS))
        # 'a' has dependents and replicas=1 => priority=high
        a_exp = [e for e in resp.result["experiments"] if e["target"] == "a"]
        assert len(a_exp) == 1
        assert a_exp[0]["priority"] == "high"

    def test_priority_is_medium_for_no_deps(self):
        bridge = MCPBridge(_single_component_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.RECOMMEND_CHAOS))
        assert resp.result["experiments"][0]["priority"] == "medium"


# ===========================================================================
# _handle_compliance
# ===========================================================================


class TestHandleCompliance:
    def test_soc2(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        assert resp.success
        assert resp.result["framework"] == "soc2"

    def test_iso27001(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "iso27001"},
        )
        resp = bridge.execute(req)
        assert resp.success

    def test_pci_dss(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "pci_dss"},
        )
        resp = bridge.execute(req)
        assert resp.success

    def test_nist_csf(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "nist_csf"},
        )
        resp = bridge.execute(req)
        assert resp.success

    def test_missing_framework(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={},
        )
        resp = bridge.execute(req)
        assert not resp.success
        assert "framework" in resp.error

    def test_unknown_framework(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "hipaa"},
        )
        resp = bridge.execute(req)
        assert not resp.success
        assert "hipaa" in resp.error.lower()

    def test_checks_returned(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        assert len(resp.result["checks"]) == 2

    def test_compliance_percent(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        assert 0.0 <= resp.result["compliance_percent"] <= 100.0

    def test_redundant_graph_passes_redundancy(self):
        bridge = MCPBridge(_redundant_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        redundancy_check = [c for c in resp.result["checks"] if c["control"] == "redundancy"]
        assert redundancy_check[0]["status"] == "pass"

    def test_simple_graph_fails_redundancy(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        redundancy_check = [c for c in resp.result["checks"] if c["control"] == "redundancy"]
        assert redundancy_check[0]["status"] == "fail"

    def test_redundant_graph_passes_failover(self):
        bridge = MCPBridge(_redundant_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        fo_check = [c for c in resp.result["checks"] if c["control"] == "failover"]
        assert fo_check[0]["status"] == "pass"

    def test_simple_graph_fails_failover(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        fo_check = [c for c in resp.result["checks"] if c["control"] == "failover"]
        assert fo_check[0]["status"] == "fail"

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        assert "timestamp" in resp.result

    def test_empty_graph_compliance(self):
        bridge = MCPBridge(_empty_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        assert resp.success
        # Empty graph has no components -> both checks fail (False)
        assert resp.result["compliance_percent"] == 0.0

    def test_passed_count(self):
        bridge = MCPBridge(_redundant_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        assert resp.result["passed"] == 2
        assert resp.result["total"] == 2

    def test_evidence_strings(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.CHECK_COMPLIANCE,
            parameters={"framework": "soc2"},
        )
        resp = bridge.execute(req)
        for check in resp.result["checks"]:
            assert "evidence" in check
            assert isinstance(check["evidence"], str)


# ===========================================================================
# _handle_compare_clouds
# ===========================================================================


class TestHandleCompareClouds:
    def test_default_providers(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.COMPARE_CLOUDS))
        assert resp.success
        assert resp.result["total_providers"] == 3

    def test_custom_providers(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.COMPARE_CLOUDS,
            parameters={"providers": ["aws", "gcp"]},
        )
        resp = bridge.execute(req)
        assert resp.result["total_providers"] == 2

    def test_comparison_fields(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.COMPARE_CLOUDS))
        comp = resp.result["comparisons"][0]
        assert "provider" in comp
        assert "component_count" in comp
        assert "resilience_score" in comp
        assert "note" in comp

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.COMPARE_CLOUDS))
        assert "timestamp" in resp.result

    def test_empty_graph(self):
        bridge = MCPBridge(_empty_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.COMPARE_CLOUDS))
        assert resp.success
        assert resp.result["comparisons"][0]["component_count"] == 0

    def test_single_provider(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.COMPARE_CLOUDS,
            parameters={"providers": ["azure"]},
        )
        resp = bridge.execute(req)
        assert resp.result["total_providers"] == 1
        assert resp.result["comparisons"][0]["provider"] == "azure"


# ===========================================================================
# _handle_predict_risk
# ===========================================================================


class TestHandlePredictRisk:
    def test_success(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"component_id": "app", "change_type": "upgrade"},
        )
        resp = bridge.execute(req)
        assert resp.success

    def test_risk_level_high(self):
        g = _graph(
            _comp("a"), _comp("b"), _comp("c"), _comp("d"),
            deps=[("b", "a"), ("c", "a"), ("d", "a")],
        )
        bridge = MCPBridge(g)
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"component_id": "a", "change_type": "upgrade"},
        )
        resp = bridge.execute(req)
        assert resp.result["risk_level"] == "high"

    def test_risk_level_medium(self):
        g = _graph(
            _comp("a"), _comp("b"),
            deps=[("b", "a")],
        )
        bridge = MCPBridge(g)
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"component_id": "a", "change_type": "config_change"},
        )
        resp = bridge.execute(req)
        assert resp.result["risk_level"] == "medium"

    def test_risk_level_low(self):
        bridge = MCPBridge(_single_component_graph())
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"component_id": "solo", "change_type": "patch"},
        )
        resp = bridge.execute(req)
        assert resp.result["risk_level"] == "low"

    def test_missing_component_id(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"change_type": "upgrade"},
        )
        resp = bridge.execute(req)
        assert not resp.success
        assert "component_id" in resp.error

    def test_missing_change_type(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"component_id": "app"},
        )
        resp = bridge.execute(req)
        assert not resp.success
        assert "change_type" in resp.error

    def test_unknown_component(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"component_id": "ghost", "change_type": "x"},
        )
        resp = bridge.execute(req)
        assert not resp.success
        assert "not found" in resp.error.lower()

    def test_description_passed_through(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={
                "component_id": "app",
                "change_type": "upgrade",
                "description": "Upgrade to v2",
            },
        )
        resp = bridge.execute(req)
        assert resp.result["description"] == "Upgrade to v2"

    def test_description_default_empty(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"component_id": "app", "change_type": "patch"},
        )
        resp = bridge.execute(req)
        assert resp.result["description"] == ""

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"component_id": "app", "change_type": "x"},
        )
        resp = bridge.execute(req)
        assert "timestamp" in resp.result

    def test_dependent_count(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.PREDICT_CHANGE_RISK,
            parameters={"component_id": "app", "change_type": "upgrade"},
        )
        resp = bridge.execute(req)
        assert isinstance(resp.result["dependent_count"], int)


# ===========================================================================
# _handle_forecast
# ===========================================================================


class TestHandleForecast:
    def test_success(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FORECAST_RESILIENCE))
        assert resp.success

    def test_default_horizon(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FORECAST_RESILIENCE))
        assert resp.result["horizon_days"] == 30

    def test_custom_horizon(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.FORECAST_RESILIENCE,
            parameters={"horizon_days": 90},
        )
        resp = bridge.execute(req)
        assert resp.result["horizon_days"] == 90

    def test_has_current_score(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FORECAST_RESILIENCE))
        assert "current_score" in resp.result

    def test_has_forecast_score(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FORECAST_RESILIENCE))
        assert "forecast_score" in resp.result

    def test_has_trend(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FORECAST_RESILIENCE))
        assert resp.result["trend"] == "stable"

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FORECAST_RESILIENCE))
        assert "timestamp" in resp.result

    def test_empty_graph(self):
        bridge = MCPBridge(_empty_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.FORECAST_RESILIENCE))
        assert resp.success
        assert resp.result["current_score"] == 0.0


# ===========================================================================
# _handle_report
# ===========================================================================


class TestHandleReport:
    def test_summary_format(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.GENERATE_REPORT))
        assert resp.success
        assert resp.result["format"] == "summary"

    def test_detailed_format(self):
        bridge = MCPBridge(_simple_graph())
        req = MCPRequest(
            tool_name=MCPToolName.GENERATE_REPORT,
            parameters={"format": "detailed"},
        )
        resp = bridge.execute(req)
        assert resp.result["format"] == "detailed"
        assert "breakdown" in resp.result
        assert "recommendations" in resp.result

    def test_summary_has_no_breakdown(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.GENERATE_REPORT))
        assert "breakdown" not in resp.result

    def test_has_summary(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.GENERATE_REPORT))
        assert "summary" in resp.result

    def test_has_resilience_score(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.GENERATE_REPORT))
        assert "resilience_score" in resp.result

    def test_has_timestamp(self):
        bridge = MCPBridge(_simple_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.GENERATE_REPORT))
        assert "timestamp" in resp.result

    def test_empty_graph(self):
        bridge = MCPBridge(_empty_graph())
        resp = bridge.execute(MCPRequest(tool_name=MCPToolName.GENERATE_REPORT))
        assert resp.success

    def test_detailed_empty_graph(self):
        bridge = MCPBridge(_empty_graph())
        req = MCPRequest(
            tool_name=MCPToolName.GENERATE_REPORT,
            parameters={"format": "detailed"},
        )
        resp = bridge.execute(req)
        assert resp.success
        assert "breakdown" in resp.result
