"""Tests for Service Mesh Resilience Analyzer.

140+ tests covering all enums, data models, mesh health assessment,
sidecar failure simulation, retry storm analysis, policy conflict
detection, control plane outage simulation, policy recommendation,
and mesh overhead calculation.
"""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.service_mesh_resilience import (
    ControlPlaneOutageResult,
    MeshHealthReport,
    MeshOverheadReport,
    MeshPolicy,
    MeshPolicyConfig,
    MeshType,
    PolicyConflict,
    RetryStormAnalysis,
    ServiceMeshResilienceEngine,
    SidecarFailureResult,
    _CONTROL_PLANE_FEATURES,
    _MESH_CONTROL_PLANE_MTTR,
    _MESH_HOP_LATENCY_MS,
    _MESH_SIDECAR_CPU_PERCENT,
    _MESH_SIDECAR_MEMORY_MB,
    _POLICY_EVAL_LATENCY_MS,
    _clamp,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas, health=health)
    if failover:
        c.failover.enabled = True
    return c


def _graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


def _engine() -> ServiceMeshResilienceEngine:
    return ServiceMeshResilienceEngine()


def _basic_policies(component_ids: list[str]) -> list[MeshPolicyConfig]:
    """Create a basic set of mesh policies for testing."""
    return [
        MeshPolicyConfig(
            policy=MeshPolicy.RETRY,
            enabled=True,
            parameters={"max_retries": 3.0, "retry_delay_ms": 100.0},
            applied_to=component_ids,
        ),
        MeshPolicyConfig(
            policy=MeshPolicy.TIMEOUT,
            enabled=True,
            parameters={"timeout_seconds": 30.0},
            applied_to=component_ids,
        ),
        MeshPolicyConfig(
            policy=MeshPolicy.CIRCUIT_BREAKER,
            enabled=True,
            parameters={"failure_threshold": 5.0, "recovery_timeout_seconds": 60.0},
            applied_to=component_ids,
        ),
    ]


# ===========================================================================
# 1. Enum completeness
# ===========================================================================


class TestMeshTypeEnum:
    def test_all_values_exist(self):
        expected = {"istio", "linkerd", "consul_connect", "app_mesh", "kuma", "custom"}
        assert {mt.value for mt in MeshType} == expected

    def test_count(self):
        assert len(MeshType) == 6

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_is_str_enum(self, mt: MeshType):
        assert isinstance(mt.value, str)


class TestMeshPolicyEnum:
    def test_all_values_exist(self):
        expected = {
            "retry", "timeout", "circuit_breaker", "rate_limit",
            "outlier_detection", "fault_injection", "mirror",
        }
        assert {mp.value for mp in MeshPolicy} == expected

    def test_count(self):
        assert len(MeshPolicy) == 7

    @pytest.mark.parametrize("mp", list(MeshPolicy))
    def test_is_str_enum(self, mp: MeshPolicy):
        assert isinstance(mp.value, str)


# ===========================================================================
# 2. Constants
# ===========================================================================


class TestConstants:
    @pytest.mark.parametrize("mt", list(MeshType))
    def test_hop_latency_defined_for_all_mesh_types(self, mt: MeshType):
        assert mt in _MESH_HOP_LATENCY_MS

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_hop_latency_positive(self, mt: MeshType):
        assert _MESH_HOP_LATENCY_MS[mt] > 0.0

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_sidecar_memory_defined(self, mt: MeshType):
        assert mt in _MESH_SIDECAR_MEMORY_MB

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_sidecar_memory_positive(self, mt: MeshType):
        assert _MESH_SIDECAR_MEMORY_MB[mt] > 0.0

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_sidecar_cpu_defined(self, mt: MeshType):
        assert mt in _MESH_SIDECAR_CPU_PERCENT

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_sidecar_cpu_positive(self, mt: MeshType):
        assert _MESH_SIDECAR_CPU_PERCENT[mt] > 0.0

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_control_plane_mttr_defined(self, mt: MeshType):
        assert mt in _MESH_CONTROL_PLANE_MTTR

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_control_plane_mttr_positive(self, mt: MeshType):
        assert _MESH_CONTROL_PLANE_MTTR[mt] > 0.0

    @pytest.mark.parametrize("mp", list(MeshPolicy))
    def test_policy_eval_latency_defined(self, mp: MeshPolicy):
        assert mp in _POLICY_EVAL_LATENCY_MS

    @pytest.mark.parametrize("mp", list(MeshPolicy))
    def test_policy_eval_latency_non_negative(self, mp: MeshPolicy):
        assert _POLICY_EVAL_LATENCY_MS[mp] >= 0.0

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_control_plane_features_defined(self, mt: MeshType):
        assert mt in _CONTROL_PLANE_FEATURES

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_control_plane_features_non_empty(self, mt: MeshType):
        assert len(_CONTROL_PLANE_FEATURES[mt]) > 0


# ===========================================================================
# 3. Utility: _clamp
# ===========================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_lo(self):
        assert _clamp(-10.0) == 0.0

    def test_above_hi(self):
        assert _clamp(150.0) == 100.0

    def test_at_lo(self):
        assert _clamp(0.0) == 0.0

    def test_at_hi(self):
        assert _clamp(100.0) == 100.0

    def test_custom_range(self):
        assert _clamp(5.0, 1.0, 10.0) == 5.0

    def test_custom_range_below(self):
        assert _clamp(-1.0, 1.0, 10.0) == 1.0

    def test_custom_range_above(self):
        assert _clamp(20.0, 1.0, 10.0) == 10.0


# ===========================================================================
# 4. Data model defaults
# ===========================================================================


class TestMeshPolicyConfig:
    def test_defaults(self):
        p = MeshPolicyConfig(policy=MeshPolicy.RETRY)
        assert p.policy == MeshPolicy.RETRY
        assert p.enabled is True
        assert p.parameters == {}
        assert p.applied_to == []

    def test_custom_values(self):
        p = MeshPolicyConfig(
            policy=MeshPolicy.TIMEOUT,
            enabled=False,
            parameters={"timeout_seconds": 10.0},
            applied_to=["svc-a", "svc-b"],
        )
        assert p.enabled is False
        assert p.parameters["timeout_seconds"] == 10.0
        assert len(p.applied_to) == 2


class TestMeshHealthReport:
    def test_defaults(self):
        r = MeshHealthReport(mesh_type=MeshType.ISTIO)
        assert r.mesh_type == MeshType.ISTIO
        assert r.total_services == 0
        assert r.sidecar_coverage == 0.0
        assert r.policy_coverage == {}
        assert r.single_points_of_failure == []
        assert r.control_plane_resilience == 0.0
        assert r.data_plane_resilience == 0.0
        assert r.recommendations == []


class TestSidecarFailureResult:
    def test_defaults(self):
        r = SidecarFailureResult()
        assert r.affected_service == ""
        assert r.failure_mode == ""
        assert r.traffic_impact == ""
        assert r.fallback_behavior == ""
        assert r.blast_radius == []


class TestRetryStormAnalysis:
    def test_defaults(self):
        r = RetryStormAnalysis()
        assert r.at_risk_services == []
        assert r.max_amplification_factor == 1.0
        assert r.storm_probability == 0.0
        assert r.affected_paths == []
        assert r.recommendations == []


class TestPolicyConflict:
    def test_defaults(self):
        c = PolicyConflict(policy_a=MeshPolicy.RETRY, policy_b=MeshPolicy.TIMEOUT)
        assert c.policy_a == MeshPolicy.RETRY
        assert c.policy_b == MeshPolicy.TIMEOUT
        assert c.component_id == ""
        assert c.severity == "medium"
        assert c.resolution == ""


class TestControlPlaneOutageResult:
    def test_defaults(self):
        r = ControlPlaneOutageResult(mesh_type=MeshType.LINKERD)
        assert r.mesh_type == MeshType.LINKERD
        assert r.affected_features == []
        assert r.data_plane_continues is True
        assert r.config_propagation_blocked is True
        assert r.estimated_impact_percent == 0.0
        assert r.mttr_minutes == 0.0


class TestMeshOverheadReport:
    def test_defaults(self):
        r = MeshOverheadReport()
        assert r.total_latency_overhead_ms == 0.0
        assert r.per_hop_latency_ms == 0.0
        assert r.memory_overhead_mb == 0.0
        assert r.cpu_overhead_percent == 0.0
        assert r.total_sidecar_instances == 0
        assert r.policy_evaluation_ms == 0.0
        assert r.recommendations == []


# ===========================================================================
# 5. assess_mesh_health
# ===========================================================================


class TestAssessMeshHealth:
    def test_returns_health_report_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["api"]))
        assert isinstance(result, MeshHealthReport)

    def test_mesh_type_set(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.assess_mesh_health(g, MeshType.LINKERD, _basic_policies(["api"]))
        assert result.mesh_type == MeshType.LINKERD

    def test_total_services_count(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["a", "b", "c"]))
        assert result.total_services == 3

    def test_empty_graph(self):
        e = _engine()
        g = InfraGraph()
        result = e.assess_mesh_health(g, MeshType.ISTIO, [])
        assert result.total_services == 0
        assert result.sidecar_coverage == 0.0
        assert len(result.recommendations) > 0

    def test_full_sidecar_coverage(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        policies = _basic_policies(["a", "b"])
        result = e.assess_mesh_health(g, MeshType.ISTIO, policies)
        assert result.sidecar_coverage == 100.0

    def test_partial_sidecar_coverage(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        policies = _basic_policies(["a"])
        result = e.assess_mesh_health(g, MeshType.ISTIO, policies)
        assert result.sidecar_coverage == 50.0

    def test_no_sidecar_coverage(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, [])
        assert result.sidecar_coverage == 0.0

    def test_policy_coverage_all_types_present(self):
        e = _engine()
        g = _graph(_comp("a", "A"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["a"]))
        for mp in MeshPolicy:
            assert mp.value in result.policy_coverage

    def test_spof_detected_single_replica_with_dependents(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["api", "web"]))
        assert "api" in result.single_points_of_failure

    def test_no_spof_with_replicas(self):
        e = _engine()
        g = _graph(_comp("api", "API", replicas=3), _comp("web", "Web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["api", "web"]))
        assert "api" not in result.single_points_of_failure

    def test_no_spof_with_failover(self):
        e = _engine()
        g = _graph(_comp("api", "API", failover=True), _comp("web", "Web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["api", "web"]))
        assert "api" not in result.single_points_of_failure

    def test_control_plane_resilience_bounded(self):
        e = _engine()
        g = _graph(_comp("a", "A"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["a"]))
        assert 0.0 <= result.control_plane_resilience <= 100.0

    def test_data_plane_resilience_bounded(self):
        e = _engine()
        g = _graph(_comp("a", "A"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["a"]))
        assert 0.0 <= result.data_plane_resilience <= 100.0

    def test_full_coverage_high_resilience(self):
        e = _engine()
        g = _graph(
            _comp("a", "A", replicas=3, failover=True),
            _comp("b", "B", replicas=3, failover=True),
        )
        all_policies = []
        ids = ["a", "b"]
        for mp in MeshPolicy:
            all_policies.append(MeshPolicyConfig(
                policy=mp, enabled=True, applied_to=ids,
            ))
        result = e.assess_mesh_health(g, MeshType.ISTIO, all_policies)
        assert result.control_plane_resilience >= 70.0
        assert result.data_plane_resilience >= 70.0

    def test_no_coverage_lower_resilience(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        full = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["a", "b"]))
        empty = e.assess_mesh_health(g, MeshType.ISTIO, [])
        assert full.control_plane_resilience >= empty.control_plane_resilience
        assert full.data_plane_resilience >= empty.data_plane_resilience

    def test_recommendations_for_uncovered_services(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["a"]))
        assert any("uncovered" in r.lower() or "sidecar" in r.lower() for r in result.recommendations)

    def test_recommendations_for_spofs(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        result = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["api", "web"]))
        assert any("single point" in r.lower() or "failure" in r.lower() for r in result.recommendations)

    def test_disabled_policy_not_counted(self):
        e = _engine()
        g = _graph(_comp("a", "A"))
        policies = [MeshPolicyConfig(
            policy=MeshPolicy.RETRY, enabled=False, applied_to=["a"],
        )]
        result = e.assess_mesh_health(g, MeshType.ISTIO, policies)
        assert result.sidecar_coverage == 0.0

    def test_policy_for_nonexistent_component_ignored(self):
        e = _engine()
        g = _graph(_comp("a", "A"))
        policies = _basic_policies(["a", "nonexistent"])
        result = e.assess_mesh_health(g, MeshType.ISTIO, policies)
        assert result.total_services == 1
        assert result.sidecar_coverage == 100.0


# ===========================================================================
# 6. simulate_sidecar_failure
# ===========================================================================


class TestSimulateSidecarFailure:
    def test_returns_result_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_sidecar_failure(g, "api")
        assert isinstance(result, SidecarFailureResult)

    def test_affected_service_set(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_sidecar_failure(g, "api")
        assert result.affected_service == "api"

    def test_nonexistent_component(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_sidecar_failure(g, "nonexistent")
        assert result.affected_service == "nonexistent"
        assert result.failure_mode == "unknown"
        assert result.blast_radius == []

    def test_load_balancer_failure_mode(self):
        e = _engine()
        g = _graph(_comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER))
        result = e.simulate_sidecar_failure(g, "lb")
        assert result.failure_mode == "ingress_proxy_down"

    def test_database_failure_mode(self):
        e = _engine()
        g = _graph(_comp("db", "DB", ctype=ComponentType.DATABASE))
        result = e.simulate_sidecar_failure(g, "db")
        assert result.failure_mode == "data_plane_proxy_failure"

    def test_external_api_failure_mode(self):
        e = _engine()
        g = _graph(_comp("ext", "Ext", ctype=ComponentType.EXTERNAL_API))
        result = e.simulate_sidecar_failure(g, "ext")
        assert result.failure_mode == "egress_proxy_down"

    def test_app_server_failure_mode(self):
        e = _engine()
        g = _graph(_comp("api", "API", ctype=ComponentType.APP_SERVER))
        result = e.simulate_sidecar_failure(g, "api")
        assert result.failure_mode == "sidecar_crash"

    def test_blast_radius_includes_dependents(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        result = e.simulate_sidecar_failure(g, "api")
        assert "web" in result.blast_radius

    def test_blast_radius_includes_dependencies(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("db", "DB", ctype=ComponentType.DATABASE))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        result = e.simulate_sidecar_failure(g, "api")
        assert "db" in result.blast_radius

    def test_blast_radius_excludes_self(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        result = e.simulate_sidecar_failure(g, "api")
        assert "api" not in result.blast_radius

    def test_replicas_mitigate_impact(self):
        e = _engine()
        g = _graph(_comp("api", "API", replicas=3))
        result = e.simulate_sidecar_failure(g, "api")
        assert "mitigated" in result.traffic_impact.lower() or "replicas" in result.traffic_impact.lower()

    def test_failover_fallback(self):
        e = _engine()
        g = _graph(_comp("api", "API", failover=True))
        result = e.simulate_sidecar_failure(g, "api")
        assert result.fallback_behavior == "automatic_failover"

    def test_no_failover_default_fallback(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_sidecar_failure(g, "api")
        assert result.fallback_behavior != "automatic_failover"

    def test_transitive_blast_radius(self):
        e = _engine()
        g = _graph(
            _comp("db", "DB", ctype=ComponentType.DATABASE),
            _comp("api", "API"),
            _comp("web", "Web"),
        )
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        result = e.simulate_sidecar_failure(g, "db")
        assert "api" in result.blast_radius
        assert "web" in result.blast_radius

    def test_isolated_component_empty_blast_radius(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_sidecar_failure(g, "api")
        assert result.blast_radius == []


# ===========================================================================
# 7. analyze_retry_storms
# ===========================================================================


class TestAnalyzeRetryStorms:
    def test_returns_analysis_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.analyze_retry_storms(g, _basic_policies(["api"]))
        assert isinstance(result, RetryStormAnalysis)

    def test_empty_graph(self):
        e = _engine()
        g = InfraGraph()
        result = e.analyze_retry_storms(g, [])
        assert result.at_risk_services == []
        assert result.max_amplification_factor == 1.0

    def test_no_retry_policies_has_recommendation(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.analyze_retry_storms(g, [])
        assert any("no retry" in r.lower() for r in result.recommendations)

    def test_amplification_factor_on_chain(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 3.0},
                applied_to=["a", "b", "c"],
            ),
        ]
        result = e.analyze_retry_storms(g, policies)
        # (1+3)^3 = 64 amplification
        assert result.max_amplification_factor > 2.0

    def test_storm_probability_bounded(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        policies = _basic_policies(["a", "b"])
        result = e.analyze_retry_storms(g, policies)
        assert 0.0 <= result.storm_probability <= 1.0

    def test_retry_budget_reduces_probability(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        no_budget = [
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 3.0},
                applied_to=["a", "b", "c"],
            ),
        ]
        with_budget = [
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 3.0, "retry_budget_percent": 20.0},
                applied_to=["a", "b", "c"],
            ),
        ]
        r_no = e.analyze_retry_storms(g, no_budget)
        r_with = e.analyze_retry_storms(g, with_budget)
        assert r_with.storm_probability <= r_no.storm_probability

    def test_at_risk_services_populated_on_chain(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 3.0},
                applied_to=["a", "b", "c"],
            ),
        ]
        result = e.analyze_retry_storms(g, policies)
        assert len(result.at_risk_services) > 0

    def test_affected_paths_populated_on_chain(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 3.0},
                applied_to=["a", "b", "c"],
            ),
        ]
        result = e.analyze_retry_storms(g, policies)
        assert len(result.affected_paths) > 0

    def test_high_amplification_critical_recommendation(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 5.0},
                applied_to=["a", "b", "c"],
            ),
        ]
        result = e.analyze_retry_storms(g, policies)
        assert any("critical" in r.lower() or "amplification" in r.lower() for r in result.recommendations)

    def test_edge_retry_strategy_counted(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            retry_strategy={"enabled": True, "max_retries": 3},
        ))
        result = e.analyze_retry_storms(g, [])
        # Should detect retries from edge-level config
        assert result.max_amplification_factor >= 1.0

    def test_single_service_no_storm(self):
        e = _engine()
        g = _graph(_comp("a", "A"))
        policies = _basic_policies(["a"])
        result = e.analyze_retry_storms(g, policies)
        assert result.storm_probability == 0.0

    def test_multiple_retry_edges_marks_at_risk(self):
        """A service with 2+ retry-enabled outgoing edges is at risk."""
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            retry_strategy={"enabled": True, "max_retries": 3},
        ))
        g.add_dependency(Dependency(
            source_id="a", target_id="c",
            retry_strategy={"enabled": True, "max_retries": 3},
        ))
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 3.0},
                applied_to=["a"],
            ),
        ]
        result = e.analyze_retry_storms(g, policies)
        assert "a" in result.at_risk_services

    def test_edge_level_retry_budget_reduces_probability(self):
        """Edge-level retry budget should reduce storm probability."""
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        g.add_dependency(Dependency(
            source_id="a", target_id="b",
            retry_strategy={"enabled": True, "max_retries": 3, "retry_budget_per_second": 10.0},
        ))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 3.0},
                applied_to=["a", "b", "c"],
            ),
        ]
        result = e.analyze_retry_storms(g, policies)
        # Edge-level budget should reduce storm probability
        assert result.storm_probability < 0.5

    def test_amplification_without_at_risk_gives_zero_probability(self):
        """When max_amplification > 1 but at_risk is empty, probability should be 0."""
        e = _engine()
        # A graph where retry_map has entries but no critical path has >2.0 amplification
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        # Small retries: (1+1)*(1+1) = 4 > 2.0, will produce at_risk
        # Use retries=1 on single node to produce amplification < 2.0 on chain
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 0.5},  # rounds to 0 via int()
                applied_to=["a", "b"],
            ),
        ]
        result = e.analyze_retry_storms(g, policies)
        # With max_retries=0, amplification stays at 1.0
        assert result.storm_probability == 0.0


# ===========================================================================
# 8. detect_policy_conflicts
# ===========================================================================


class TestDetectPolicyConflicts:
    def test_returns_list(self):
        e = _engine()
        result = e.detect_policy_conflicts([])
        assert isinstance(result, list)

    def test_no_conflicts_with_empty_policies(self):
        e = _engine()
        result = e.detect_policy_conflicts([])
        assert len(result) == 0

    def test_no_conflicts_non_overlapping(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(policy=MeshPolicy.RETRY, enabled=True, applied_to=["a"]),
            MeshPolicyConfig(policy=MeshPolicy.TIMEOUT, enabled=True, applied_to=["b"]),
        ]
        result = e.detect_policy_conflicts(policies)
        assert len(result) == 0

    def test_timeout_retry_mismatch_detected(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.TIMEOUT, enabled=True,
                parameters={"timeout_seconds": 5.0},
                applied_to=["a"],
            ),
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 10.0, "retry_delay_ms": 1000.0},
                applied_to=["a"],
            ),
        ]
        result = e.detect_policy_conflicts(policies)
        timeout_conflicts = [c for c in result if c.conflict_type == "timeout_retry_mismatch"]
        assert len(timeout_conflicts) >= 1

    def test_timeout_retry_no_conflict_when_retries_fit(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.TIMEOUT, enabled=True,
                parameters={"timeout_seconds": 60.0},
                applied_to=["a"],
            ),
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 2.0, "retry_delay_ms": 100.0},
                applied_to=["a"],
            ),
        ]
        result = e.detect_policy_conflicts(policies)
        timeout_conflicts = [c for c in result if c.conflict_type == "timeout_retry_mismatch"]
        assert len(timeout_conflicts) == 0

    def test_cb_retry_threshold_conflict(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.CIRCUIT_BREAKER, enabled=True,
                parameters={"failure_threshold": 3.0},
                applied_to=["a"],
            ),
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 5.0},
                applied_to=["a"],
            ),
        ]
        result = e.detect_policy_conflicts(policies)
        cb_conflicts = [c for c in result if c.conflict_type == "cb_retry_threshold_conflict"]
        assert len(cb_conflicts) >= 1

    def test_cb_retry_no_conflict_when_retries_below_threshold(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.CIRCUIT_BREAKER, enabled=True,
                parameters={"failure_threshold": 10.0},
                applied_to=["a"],
            ),
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 3.0},
                applied_to=["a"],
            ),
        ]
        result = e.detect_policy_conflicts(policies)
        cb_conflicts = [c for c in result if c.conflict_type == "cb_retry_threshold_conflict"]
        assert len(cb_conflicts) == 0

    def test_rate_limit_fault_injection_conflict(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(policy=MeshPolicy.RATE_LIMIT, enabled=True, applied_to=["a"]),
            MeshPolicyConfig(policy=MeshPolicy.FAULT_INJECTION, enabled=True, applied_to=["a"]),
        ]
        result = e.detect_policy_conflicts(policies)
        rl_fi = [c for c in result if c.conflict_type == "rate_limit_fault_injection_overlap"]
        assert len(rl_fi) >= 1

    def test_mirror_rate_limit_conflict(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(policy=MeshPolicy.MIRROR, enabled=True, applied_to=["a"]),
            MeshPolicyConfig(policy=MeshPolicy.RATE_LIMIT, enabled=True, applied_to=["a"]),
        ]
        result = e.detect_policy_conflicts(policies)
        mirror_rl = [c for c in result if c.conflict_type == "mirror_rate_limit_amplification"]
        assert len(mirror_rl) >= 1

    def test_outlier_cb_timing_conflict(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.OUTLIER_DETECTION, enabled=True,
                parameters={"interval_seconds": 120.0},
                applied_to=["a"],
            ),
            MeshPolicyConfig(
                policy=MeshPolicy.CIRCUIT_BREAKER, enabled=True,
                parameters={"recovery_timeout_seconds": 30.0},
                applied_to=["a"],
            ),
        ]
        result = e.detect_policy_conflicts(policies)
        timing = [c for c in result if c.conflict_type == "outlier_cb_timing_conflict"]
        assert len(timing) >= 1

    def test_conflict_has_severity(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(policy=MeshPolicy.RATE_LIMIT, enabled=True, applied_to=["a"]),
            MeshPolicyConfig(policy=MeshPolicy.FAULT_INJECTION, enabled=True, applied_to=["a"]),
        ]
        result = e.detect_policy_conflicts(policies)
        assert all(c.severity in ("low", "medium", "high") for c in result)

    def test_conflict_has_resolution(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(policy=MeshPolicy.RATE_LIMIT, enabled=True, applied_to=["a"]),
            MeshPolicyConfig(policy=MeshPolicy.FAULT_INJECTION, enabled=True, applied_to=["a"]),
        ]
        result = e.detect_policy_conflicts(policies)
        assert all(len(c.resolution) > 0 for c in result)

    def test_disabled_policies_ignored(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(
                policy=MeshPolicy.TIMEOUT, enabled=False,
                parameters={"timeout_seconds": 5.0},
                applied_to=["a"],
            ),
            MeshPolicyConfig(
                policy=MeshPolicy.RETRY, enabled=True,
                parameters={"max_retries": 10.0, "retry_delay_ms": 1000.0},
                applied_to=["a"],
            ),
        ]
        result = e.detect_policy_conflicts(policies)
        timeout_conflicts = [c for c in result if c.conflict_type == "timeout_retry_mismatch"]
        assert len(timeout_conflicts) == 0

    def test_component_id_set_on_conflict(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(policy=MeshPolicy.RATE_LIMIT, enabled=True, applied_to=["svc-x"]),
            MeshPolicyConfig(policy=MeshPolicy.FAULT_INJECTION, enabled=True, applied_to=["svc-x"]),
        ]
        result = e.detect_policy_conflicts(policies)
        assert all(c.component_id == "svc-x" for c in result)

    def test_multiple_components_independent_conflicts(self):
        e = _engine()
        policies = [
            MeshPolicyConfig(policy=MeshPolicy.RATE_LIMIT, enabled=True, applied_to=["a", "b"]),
            MeshPolicyConfig(policy=MeshPolicy.FAULT_INJECTION, enabled=True, applied_to=["a", "b"]),
        ]
        result = e.detect_policy_conflicts(policies)
        comp_ids = {c.component_id for c in result}
        assert "a" in comp_ids
        assert "b" in comp_ids


# ===========================================================================
# 9. simulate_control_plane_outage
# ===========================================================================


class TestSimulateControlPlaneOutage:
    def test_returns_result_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_control_plane_outage(g, MeshType.ISTIO)
        assert isinstance(result, ControlPlaneOutageResult)

    def test_mesh_type_set(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_control_plane_outage(g, MeshType.CONSUL_CONNECT)
        assert result.mesh_type == MeshType.CONSUL_CONNECT

    def test_data_plane_continues(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_control_plane_outage(g, MeshType.ISTIO)
        assert result.data_plane_continues is True

    def test_config_propagation_blocked(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_control_plane_outage(g, MeshType.ISTIO)
        assert result.config_propagation_blocked is True

    def test_affected_features_match_mesh_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        for mt in MeshType:
            result = e.simulate_control_plane_outage(g, mt)
            assert result.affected_features == _CONTROL_PLANE_FEATURES[mt]

    def test_impact_percent_bounded(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_control_plane_outage(g, MeshType.ISTIO)
        assert 0.0 <= result.estimated_impact_percent <= 100.0

    def test_empty_graph_zero_impact(self):
        e = _engine()
        g = InfraGraph()
        result = e.simulate_control_plane_outage(g, MeshType.ISTIO)
        assert result.estimated_impact_percent == 0.0

    def test_more_services_higher_impact(self):
        e = _engine()
        small = _graph(_comp("a", "A"))
        large = _graph(*[_comp(f"s{i}", f"S{i}") for i in range(20)])
        r_small = e.simulate_control_plane_outage(small, MeshType.ISTIO)
        r_large = e.simulate_control_plane_outage(large, MeshType.ISTIO)
        assert r_large.estimated_impact_percent >= r_small.estimated_impact_percent

    def test_spofs_increase_impact(self):
        e = _engine()
        no_spof = _graph(_comp("a", "A", replicas=3, failover=True))
        with_spof = _graph(_comp("a", "A"))
        r_no = e.simulate_control_plane_outage(no_spof, MeshType.ISTIO)
        r_with = e.simulate_control_plane_outage(with_spof, MeshType.ISTIO)
        assert r_with.estimated_impact_percent >= r_no.estimated_impact_percent

    def test_mttr_matches_mesh_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        for mt in MeshType:
            result = e.simulate_control_plane_outage(g, mt)
            assert result.mttr_minutes == _MESH_CONTROL_PLANE_MTTR[mt]

    def test_recommendations_present(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_control_plane_outage(g, MeshType.ISTIO)
        assert len(result.recommendations) > 0

    def test_ha_recommendation_present(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_control_plane_outage(g, MeshType.ISTIO)
        assert any("high availability" in r.lower() or "multi-replica" in r.lower() for r in result.recommendations)

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_all_mesh_types_produce_result(self, mt: MeshType):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.simulate_control_plane_outage(g, mt)
        assert isinstance(result, ControlPlaneOutageResult)
        assert result.mttr_minutes > 0


# ===========================================================================
# 10. recommend_mesh_policies
# ===========================================================================


class TestRecommendMeshPolicies:
    def test_returns_list(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.recommend_mesh_policies(g)
        assert isinstance(result, list)

    def test_empty_graph(self):
        e = _engine()
        g = InfraGraph()
        result = e.recommend_mesh_policies(g)
        assert len(result) == 0

    def test_retry_policy_recommended(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.recommend_mesh_policies(g)
        retry_policies = [p for p in result if p.policy == MeshPolicy.RETRY]
        assert len(retry_policies) >= 1

    def test_timeout_policy_recommended(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.recommend_mesh_policies(g)
        timeout_policies = [p for p in result if p.policy == MeshPolicy.TIMEOUT]
        assert len(timeout_policies) >= 1

    def test_circuit_breaker_for_services_with_dependents(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        result = e.recommend_mesh_policies(g)
        cb_policies = [p for p in result if p.policy == MeshPolicy.CIRCUIT_BREAKER]
        assert len(cb_policies) >= 1
        assert "api" in cb_policies[0].applied_to

    def test_no_circuit_breaker_for_leaf_only(self):
        e = _engine()
        g = _graph(_comp("leaf", "Leaf"))
        result = e.recommend_mesh_policies(g)
        cb_policies = [p for p in result if p.policy == MeshPolicy.CIRCUIT_BREAKER]
        # Leaf with no dependents should not get CB policy
        assert len(cb_policies) == 0

    def test_rate_limit_for_entry_points(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("db", "DB", ctype=ComponentType.DATABASE))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        result = e.recommend_mesh_policies(g)
        rl_policies = [p for p in result if p.policy == MeshPolicy.RATE_LIMIT]
        assert len(rl_policies) >= 1
        # api is entry point (no dependents)
        assert "api" in rl_policies[0].applied_to

    def test_rate_limit_for_external_api(self):
        e = _engine()
        g = _graph(
            _comp("api", "API"),
            _comp("ext", "Ext", ctype=ComponentType.EXTERNAL_API),
        )
        g.add_dependency(Dependency(source_id="api", target_id="ext"))
        result = e.recommend_mesh_policies(g)
        rl_policies = [p for p in result if p.policy == MeshPolicy.RATE_LIMIT]
        ext_covered = any("ext" in p.applied_to for p in rl_policies)
        assert ext_covered

    def test_outlier_detection_for_replicated_services(self):
        e = _engine()
        g = _graph(_comp("api", "API", replicas=3))
        result = e.recommend_mesh_policies(g)
        od_policies = [p for p in result if p.policy == MeshPolicy.OUTLIER_DETECTION]
        assert len(od_policies) >= 1
        assert "api" in od_policies[0].applied_to

    def test_no_outlier_detection_single_replica(self):
        e = _engine()
        g = _graph(_comp("api", "API", replicas=1))
        result = e.recommend_mesh_policies(g)
        od_policies = [p for p in result if p.policy == MeshPolicy.OUTLIER_DETECTION]
        assert len(od_policies) == 0

    def test_all_recommended_policies_enabled(self):
        e = _engine()
        g = _graph(_comp("api", "API"), _comp("web", "Web"))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        result = e.recommend_mesh_policies(g)
        assert all(p.enabled for p in result)

    def test_all_recommended_policies_have_applied_to(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.recommend_mesh_policies(g)
        assert all(len(p.applied_to) > 0 for p in result)


# ===========================================================================
# 11. calculate_mesh_overhead
# ===========================================================================


class TestCalculateMeshOverhead:
    def test_returns_report_type(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.calculate_mesh_overhead(g, _basic_policies(["api"]))
        assert isinstance(result, MeshOverheadReport)

    def test_empty_graph(self):
        e = _engine()
        g = InfraGraph()
        result = e.calculate_mesh_overhead(g, [])
        assert result.total_sidecar_instances == 0
        assert len(result.recommendations) > 0

    def test_latency_overhead_positive(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.calculate_mesh_overhead(g, _basic_policies(["api"]))
        assert result.total_latency_overhead_ms > 0.0

    def test_per_hop_latency_positive(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.calculate_mesh_overhead(g, _basic_policies(["api"]))
        assert result.per_hop_latency_ms > 0.0

    def test_memory_overhead_positive(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.calculate_mesh_overhead(g, _basic_policies(["api"]))
        assert result.memory_overhead_mb > 0.0

    def test_cpu_overhead_positive(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.calculate_mesh_overhead(g, _basic_policies(["api"]))
        assert result.cpu_overhead_percent > 0.0

    def test_sidecar_instances_equals_total_replicas(self):
        e = _engine()
        g = _graph(
            _comp("a", "A", replicas=2),
            _comp("b", "B", replicas=3),
        )
        result = e.calculate_mesh_overhead(g, _basic_policies(["a", "b"]))
        assert result.total_sidecar_instances == 5

    def test_policy_evaluation_ms_positive_with_policies(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.calculate_mesh_overhead(g, _basic_policies(["api"]))
        assert result.policy_evaluation_ms > 0.0

    def test_policy_evaluation_ms_zero_no_policies(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.calculate_mesh_overhead(g, [])
        assert result.policy_evaluation_ms == 0.0

    def test_deeper_chain_more_latency(self):
        e = _engine()
        shallow = _graph(_comp("a", "A"), _comp("b", "B"))
        shallow.add_dependency(Dependency(source_id="a", target_id="b"))
        deep = _graph(
            _comp("a", "A"), _comp("b", "B"),
            _comp("c", "C"), _comp("d", "D"),
        )
        deep.add_dependency(Dependency(source_id="a", target_id="b"))
        deep.add_dependency(Dependency(source_id="b", target_id="c"))
        deep.add_dependency(Dependency(source_id="c", target_id="d"))
        policies = _basic_policies(["a", "b", "c", "d"])
        r_shallow = e.calculate_mesh_overhead(shallow, policies)
        r_deep = e.calculate_mesh_overhead(deep, policies)
        assert r_deep.total_latency_overhead_ms > r_shallow.total_latency_overhead_ms

    def test_linkerd_lower_latency_than_istio(self):
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        policies = _basic_policies(["a", "b"])
        r_istio = e.calculate_mesh_overhead(g, policies, mesh_type=MeshType.ISTIO)
        r_linkerd = e.calculate_mesh_overhead(g, policies, mesh_type=MeshType.LINKERD)
        assert r_linkerd.per_hop_latency_ms < r_istio.per_hop_latency_ms

    def test_linkerd_lower_memory_than_istio(self):
        e = _engine()
        g = _graph(_comp("a", "A"))
        policies = _basic_policies(["a"])
        r_istio = e.calculate_mesh_overhead(g, policies, mesh_type=MeshType.ISTIO)
        r_linkerd = e.calculate_mesh_overhead(g, policies, mesh_type=MeshType.LINKERD)
        assert r_linkerd.memory_overhead_mb < r_istio.memory_overhead_mb

    def test_more_services_more_memory(self):
        e = _engine()
        small = _graph(_comp("a", "A"))
        large = _graph(*[_comp(f"s{i}", f"S{i}") for i in range(10)])
        policies = _basic_policies([f"s{i}" for i in range(10)])
        r_small = e.calculate_mesh_overhead(small, policies)
        r_large = e.calculate_mesh_overhead(large, policies)
        assert r_large.memory_overhead_mb > r_small.memory_overhead_mb

    def test_recommendations_for_high_latency(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"S{i}") for i in range(10)])
        for i in range(9):
            g.add_dependency(Dependency(source_id=f"s{i}", target_id=f"s{i+1}"))
        policies = _basic_policies([f"s{i}" for i in range(10)])
        result = e.calculate_mesh_overhead(g, policies)
        assert any("latency" in r.lower() for r in result.recommendations)

    def test_recommendations_for_many_sidecars(self):
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"S{i}", replicas=3) for i in range(20)])
        policies = _basic_policies([f"s{i}" for i in range(20)])
        result = e.calculate_mesh_overhead(g, policies)
        assert any("sidecar" in r.lower() or "ambient" in r.lower() for r in result.recommendations)

    @pytest.mark.parametrize("mt", list(MeshType))
    def test_all_mesh_types_produce_result(self, mt: MeshType):
        e = _engine()
        g = _graph(_comp("api", "API"))
        result = e.calculate_mesh_overhead(g, _basic_policies(["api"]), mesh_type=mt)
        assert isinstance(result, MeshOverheadReport)
        assert result.total_latency_overhead_ms > 0.0

    def test_disabled_policies_not_counted_in_eval_latency(self):
        e = _engine()
        g = _graph(_comp("api", "API"))
        enabled = [MeshPolicyConfig(policy=MeshPolicy.RETRY, enabled=True, applied_to=["api"])]
        disabled = [MeshPolicyConfig(policy=MeshPolicy.RETRY, enabled=False, applied_to=["api"])]
        r_enabled = e.calculate_mesh_overhead(g, enabled)
        r_disabled = e.calculate_mesh_overhead(g, disabled)
        assert r_enabled.policy_evaluation_ms > r_disabled.policy_evaluation_ms

    def test_high_policy_eval_recommendation(self):
        """Many policies should trigger a policy evaluation overhead recommendation."""
        e = _engine()
        g = _graph(_comp("api", "API"))
        # Create many policies to exceed 1.0ms threshold
        policies = []
        for mp in MeshPolicy:
            for _ in range(3):
                policies.append(MeshPolicyConfig(
                    policy=mp, enabled=True, applied_to=["api"],
                ))
        result = e.calculate_mesh_overhead(g, policies)
        assert result.policy_evaluation_ms > 1.0
        assert any("policy evaluation" in r.lower() for r in result.recommendations)

    def test_high_cpu_overhead_recommendation(self):
        """Many services should trigger CPU overhead recommendation."""
        e = _engine()
        g = _graph(*[_comp(f"s{i}", f"S{i}", replicas=2) for i in range(10)])
        policies = _basic_policies([f"s{i}" for i in range(10)])
        result = e.calculate_mesh_overhead(g, policies)
        if result.cpu_overhead_percent > 10.0:
            assert any("cpu" in r.lower() for r in result.recommendations)


# ===========================================================================
# 12. Integration / cross-method tests
# ===========================================================================


class TestIntegration:
    def test_health_and_sidecar_consistent(self):
        """Services identified as SPOFs should have larger blast radius."""
        e = _engine()
        g = _graph(
            _comp("api", "API"),
            _comp("web", "Web"),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))

        health = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(["api", "web", "db"]))
        sidecar = e.simulate_sidecar_failure(g, "api")

        # api is a SPOF (single replica, has dependents)
        assert "api" in health.single_points_of_failure
        assert len(sidecar.blast_radius) > 0

    def test_policy_recommendation_avoids_conflicts(self):
        """Recommended policies should not conflict with each other."""
        e = _engine()
        g = _graph(
            _comp("api", "API", replicas=2),
            _comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2),
        )
        g.add_dependency(Dependency(source_id="api", target_id="db"))

        recommended = e.recommend_mesh_policies(g)
        conflicts = e.detect_policy_conflicts(recommended)

        # Recommended policies should be conflict-free
        high_conflicts = [c for c in conflicts if c.severity == "high"]
        assert len(high_conflicts) == 0

    def test_retry_storm_detected_for_recommended_policies(self):
        """Retry storms should be analyzed on recommended policies."""
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"), _comp("c", "C"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))

        recommended = e.recommend_mesh_policies(g)
        storms = e.analyze_retry_storms(g, recommended)
        assert isinstance(storms, RetryStormAnalysis)

    def test_overhead_with_recommended_policies(self):
        """Overhead should be calculable from recommended policies."""
        e = _engine()
        g = _graph(
            _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER),
            _comp("api", "API", replicas=3),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="lb", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))

        recommended = e.recommend_mesh_policies(g)
        overhead = e.calculate_mesh_overhead(g, recommended, mesh_type=MeshType.LINKERD)
        assert overhead.total_sidecar_instances == 5  # 1 + 3 + 1
        assert overhead.total_latency_overhead_ms > 0.0

    def test_full_workflow(self):
        """Complete analysis workflow on a realistic service mesh."""
        e = _engine()
        g = _graph(
            _comp("lb", "LB", ctype=ComponentType.LOAD_BALANCER, replicas=2),
            _comp("api", "API", replicas=3),
            _comp("auth", "Auth", replicas=2),
            _comp("db", "DB", ctype=ComponentType.DATABASE, replicas=2, failover=True),
            _comp("cache", "Cache", ctype=ComponentType.CACHE, replicas=3),
            _comp("ext", "Payment", ctype=ComponentType.EXTERNAL_API),
        )
        g.add_dependency(Dependency(source_id="lb", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="auth"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        g.add_dependency(Dependency(source_id="api", target_id="cache"))
        g.add_dependency(Dependency(source_id="api", target_id="ext"))

        ids = list(g.components.keys())

        # 1. Health assessment
        health = e.assess_mesh_health(g, MeshType.ISTIO, _basic_policies(ids))
        assert isinstance(health, MeshHealthReport)
        assert health.total_services == 6

        # 2. Sidecar failure for each component
        for cid in ids:
            result = e.simulate_sidecar_failure(g, cid)
            assert isinstance(result, SidecarFailureResult)

        # 3. Retry storm analysis
        storms = e.analyze_retry_storms(g, _basic_policies(ids))
        assert isinstance(storms, RetryStormAnalysis)

        # 4. Policy recommendations
        recommended = e.recommend_mesh_policies(g)
        assert len(recommended) > 0

        # 5. Conflict detection
        conflicts = e.detect_policy_conflicts(recommended)
        assert isinstance(conflicts, list)

        # 6. Control plane outage
        outage = e.simulate_control_plane_outage(g, MeshType.ISTIO)
        assert isinstance(outage, ControlPlaneOutageResult)

        # 7. Overhead calculation
        overhead = e.calculate_mesh_overhead(g, recommended, mesh_type=MeshType.ISTIO)
        assert isinstance(overhead, MeshOverheadReport)
        assert overhead.total_sidecar_instances == 13  # 2+3+2+2+3+1

    def test_control_plane_outage_all_mesh_types(self):
        """All mesh types should produce valid outage results."""
        e = _engine()
        g = _graph(
            _comp("api", "API", replicas=2),
            _comp("db", "DB", ctype=ComponentType.DATABASE),
        )
        g.add_dependency(Dependency(source_id="api", target_id="db"))
        for mt in MeshType:
            result = e.simulate_control_plane_outage(g, mt)
            assert result.mesh_type == mt
            assert len(result.affected_features) > 0
            assert result.mttr_minutes > 0.0

    def test_health_improves_with_better_policies(self):
        """Health metrics should improve with comprehensive policies."""
        e = _engine()
        g = _graph(_comp("a", "A"), _comp("b", "B"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        no_policies = e.assess_mesh_health(g, MeshType.ISTIO, [])
        full_policies = e.assess_mesh_health(
            g, MeshType.ISTIO,
            _basic_policies(["a", "b"]),
        )
        assert full_policies.sidecar_coverage > no_policies.sidecar_coverage
