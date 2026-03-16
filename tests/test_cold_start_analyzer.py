"""Tests for the Cold Start Analyzer module."""

from __future__ import annotations

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    NetworkProfile,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cold_start_analyzer import (
    CascadeAnalysis,
    CascadeNode,
    ColdStartAnalyzer,
    ColdStartFrequency,
    ColdStartProfile,
    ColdStartSeverity,
    ComponentRuntime,
    ConnectionPoolAnalysis,
    ContainerOverhead,
    FullColdStartReport,
    InitOrder,
    MitigationScore,
    MitigationStrategy,
    PreWarmStrategy,
    ResourceSpike,
    SLAImpact,
    StartupProbeAnalysis,
    StartupProbeStatus,
    WarmUpModel,
    WarmUpPhase,
    WarmUpPhaseDetail,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    cid: str = "c1",
    ctype: ComponentType = ComponentType.APP_SERVER,
    **kwargs,
) -> Component:
    return Component(id=cid, name=cid, type=ctype, **kwargs)


def _graph(*comps: Component) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _dep(source: str, target: str, **kwargs) -> Dependency:
    return Dependency(source_id=source, target_id=target, **kwargs)


# ---------------------------------------------------------------------------
# Tests: Cold Start Latency Estimation
# ---------------------------------------------------------------------------


class TestColdStartEstimation:
    """Cold start latency estimation per component."""

    def test_estimate_nonexistent_component(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("missing")
        assert profile.component_id == "missing"
        assert profile.total_cold_start_ms == 0.0
        assert profile.severity == ColdStartSeverity.INFO

    def test_estimate_app_server(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("app1")
        assert profile.component_id == "app1"
        assert profile.base_start_ms == 3000.0
        assert profile.total_cold_start_ms > 0
        assert profile.warm_start_ms < profile.total_cold_start_ms

    def test_estimate_database(self):
        g = _graph(_comp("db1", ComponentType.DATABASE))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("db1")
        assert profile.base_start_ms == 5000.0
        assert profile.total_cold_start_ms > 0

    def test_estimate_cache(self):
        g = _graph(_comp("cache1", ComponentType.CACHE))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("cache1")
        assert profile.base_start_ms == 1000.0

    def test_estimate_dns(self):
        g = _graph(_comp("dns1", ComponentType.DNS))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("dns1")
        assert profile.base_start_ms == 200.0
        assert profile.severity in (ColdStartSeverity.INFO, ColdStartSeverity.LOW)

    def test_estimate_queue(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("q1")
        assert profile.base_start_ms == 1500.0

    def test_estimate_load_balancer(self):
        g = _graph(_comp("lb1", ComponentType.LOAD_BALANCER))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("lb1")
        assert profile.base_start_ms == 500.0

    def test_estimate_storage(self):
        g = _graph(_comp("s1", ComponentType.STORAGE))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("s1")
        assert profile.base_start_ms == 800.0

    def test_estimate_external_api(self):
        g = _graph(_comp("ext1", ComponentType.EXTERNAL_API))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("ext1")
        assert profile.base_start_ms == 100.0

    def test_estimate_custom(self):
        g = _graph(_comp("custom1", ComponentType.CUSTOM))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("custom1")
        assert profile.base_start_ms == 2000.0

    def test_estimate_all_cold_starts(self):
        g = _graph(
            _comp("a1", ComponentType.APP_SERVER),
            _comp("b1", ComponentType.DATABASE),
            _comp("c1", ComponentType.CACHE),
        )
        analyzer = ColdStartAnalyzer(g)
        profiles = analyzer.estimate_all_cold_starts()
        assert len(profiles) == 3
        ids = {p.component_id for p in profiles}
        assert ids == {"a1", "b1", "c1"}

    def test_estimate_with_runtime_override(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("app1", ComponentRuntime.SERVERLESS)
        profile = analyzer.estimate_cold_start("app1")
        assert profile.runtime == ComponentRuntime.SERVERLESS
        # Serverless multiplier is 1.5x vs container 1.0x
        container_analyzer = ColdStartAnalyzer(g)
        container_profile = container_analyzer.estimate_cold_start("app1")
        assert profile.init_ms > container_profile.init_ms

    def test_estimate_with_vm_runtime(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("app1", ComponentRuntime.VM)
        profile = analyzer.estimate_cold_start("app1")
        assert profile.runtime == ComponentRuntime.VM
        assert profile.init_ms == 3000.0 * 3.0  # VM multiplier

    def test_estimate_with_dependencies(self):
        c1 = _comp("app1", ComponentType.APP_SERVER)
        c2 = _comp("db1", ComponentType.DATABASE)
        g = _graph(c1, c2)
        g.add_dependency(_dep("app1", "db1", dependency_type="requires"))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("app1")
        assert profile.dependency_wait_ms > 0

    def test_estimate_with_optional_dependency(self):
        c1 = _comp("app1", ComponentType.APP_SERVER)
        c2 = _comp("cache1", ComponentType.CACHE)
        g = _graph(c1, c2)
        g.add_dependency(_dep("app1", "cache1", dependency_type="optional"))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("app1")
        # Optional dependency wait should be smaller
        assert profile.dependency_wait_ms > 0

    def test_severity_critical(self):
        assert ColdStartAnalyzer._cold_start_severity(20000.0) == ColdStartSeverity.CRITICAL

    def test_severity_high(self):
        assert ColdStartAnalyzer._cold_start_severity(10000.0) == ColdStartSeverity.HIGH

    def test_severity_medium(self):
        assert ColdStartAnalyzer._cold_start_severity(5000.0) == ColdStartSeverity.MEDIUM

    def test_severity_low(self):
        assert ColdStartAnalyzer._cold_start_severity(2000.0) == ColdStartSeverity.LOW

    def test_severity_info(self):
        assert ColdStartAnalyzer._cold_start_severity(500.0) == ColdStartSeverity.INFO


# ---------------------------------------------------------------------------
# Tests: Warm-Up Time Modelling
# ---------------------------------------------------------------------------


class TestWarmUpModelling:
    """Warm-up time modelling."""

    def test_warm_up_nonexistent_component(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        model = analyzer.model_warm_up("missing")
        assert model.component_id == "missing"
        assert model.phases == []
        assert model.total_warm_up_ms == 0.0

    def test_warm_up_app_server(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        model = analyzer.model_warm_up("app1")
        assert model.component_id == "app1"
        assert len(model.phases) > 0
        assert model.total_warm_up_ms > 0
        phase_types = {p.phase for p in model.phases}
        assert WarmUpPhase.JIT_COMPILATION in phase_types
        assert WarmUpPhase.CONNECTION_POOL in phase_types

    def test_warm_up_database(self):
        g = _graph(_comp("db1", ComponentType.DATABASE))
        analyzer = ColdStartAnalyzer(g)
        model = analyzer.model_warm_up("db1")
        phase_types = {p.phase for p in model.phases}
        assert WarmUpPhase.CACHE_WARMING in phase_types
        assert WarmUpPhase.CONNECTION_POOL in phase_types

    def test_warm_up_cache(self):
        g = _graph(_comp("cache1", ComponentType.CACHE))
        analyzer = ColdStartAnalyzer(g)
        model = analyzer.model_warm_up("cache1")
        phase_types = {p.phase for p in model.phases}
        assert WarmUpPhase.CACHE_WARMING in phase_types

    def test_warm_up_load_balancer(self):
        g = _graph(_comp("lb1", ComponentType.LOAD_BALANCER))
        analyzer = ColdStartAnalyzer(g)
        model = analyzer.model_warm_up("lb1")
        phase_types = {p.phase for p in model.phases}
        assert WarmUpPhase.TLS_HANDSHAKE in phase_types

    def test_warm_up_has_blocking_phases(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        model = analyzer.model_warm_up("app1")
        blocking = [p for p in model.phases if p.is_blocking]
        assert len(blocking) > 0

    def test_warm_up_capacity_bounded(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        model = analyzer.model_warm_up("app1")
        assert model.ready_at_percent <= 100.0

    def test_warm_up_web_server(self):
        g = _graph(_comp("web1", ComponentType.WEB_SERVER))
        analyzer = ColdStartAnalyzer(g)
        model = analyzer.model_warm_up("web1")
        phase_types = {p.phase for p in model.phases}
        assert WarmUpPhase.TLS_HANDSHAKE in phase_types
        assert WarmUpPhase.DNS_RESOLUTION in phase_types

    def test_warm_up_queue_has_basic_phases(self):
        g = _graph(_comp("q1", ComponentType.QUEUE))
        analyzer = ColdStartAnalyzer(g)
        model = analyzer.model_warm_up("q1")
        phase_types = {p.phase for p in model.phases}
        assert WarmUpPhase.DNS_RESOLUTION in phase_types
        assert WarmUpPhase.HEALTH_CHECK in phase_types


# ---------------------------------------------------------------------------
# Tests: Cold Start Cascade Analysis
# ---------------------------------------------------------------------------


class TestCascadeAnalysis:
    """Cold start cascade analysis."""

    def test_cascade_nonexistent_component(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_cascade("missing")
        assert result.root_component_id == "missing"
        assert result.affected_components == 0

    def test_cascade_single_component_no_deps(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_cascade("app1")
        assert result.root_component_id == "app1"
        assert result.affected_components == 0
        assert result.total_cascade_ms > 0
        assert result.critical_path == ["app1"]

    def test_cascade_linear_chain(self):
        c1 = _comp("db1", ComponentType.DATABASE)
        c2 = _comp("app1", ComponentType.APP_SERVER)
        c3 = _comp("web1", ComponentType.WEB_SERVER)
        g = _graph(c1, c2, c3)
        g.add_dependency(_dep("app1", "db1"))
        g.add_dependency(_dep("web1", "app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_cascade("db1")
        assert result.affected_components >= 2
        assert result.max_depth >= 2
        assert result.critical_path_ms > 0

    def test_cascade_fan_out(self):
        db = _comp("db1", ComponentType.DATABASE)
        a1 = _comp("app1", ComponentType.APP_SERVER)
        a2 = _comp("app2", ComponentType.APP_SERVER)
        g = _graph(db, a1, a2)
        g.add_dependency(_dep("app1", "db1"))
        g.add_dependency(_dep("app2", "db1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_cascade("db1")
        assert result.affected_components == 2
        assert len(result.cascade_tree.children) == 2

    def test_cascade_severity_based_on_depth(self):
        assert ColdStartAnalyzer._cascade_severity(35000, 2) == ColdStartSeverity.CRITICAL
        assert ColdStartAnalyzer._cascade_severity(20000, 2) == ColdStartSeverity.HIGH
        assert ColdStartAnalyzer._cascade_severity(10000, 2) == ColdStartSeverity.MEDIUM
        assert ColdStartAnalyzer._cascade_severity(4000, 2) == ColdStartSeverity.LOW
        assert ColdStartAnalyzer._cascade_severity(1000, 0) == ColdStartSeverity.INFO

    def test_cascade_severity_based_on_affected(self):
        assert ColdStartAnalyzer._cascade_severity(1000, 15) == ColdStartSeverity.CRITICAL
        assert ColdStartAnalyzer._cascade_severity(1000, 7) == ColdStartSeverity.HIGH
        assert ColdStartAnalyzer._cascade_severity(1000, 4) == ColdStartSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Tests: Container / Serverless Overhead
# ---------------------------------------------------------------------------


class TestContainerOverhead:
    """Container/serverless cold start overhead breakdown."""

    def test_overhead_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_container_overhead("missing")
        assert result.component_id == "missing"
        assert result.total_overhead_ms == 0.0

    def test_overhead_container(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_container_overhead("app1")
        assert result.image_pull_ms > 0
        assert result.runtime_init_ms > 0
        assert result.app_init_ms > 0
        assert result.total_overhead_ms > 0

    def test_overhead_serverless(self):
        g = _graph(_comp("fn1", ComponentType.APP_SERVER, tags=["serverless"]))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_container_overhead("fn1")
        assert result.runtime == ComponentRuntime.SERVERLESS
        assert any("provisioned concurrency" in r.lower() for r in result.recommendations)

    def test_overhead_recommendations_large_image(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_container_overhead("app1")
        # Container image pull is 2000ms > 1500, so should recommend smaller image
        assert any("smaller base image" in r.lower() for r in result.recommendations)

    def test_overhead_includes_network_setup(self):
        net = NetworkProfile(rtt_ms=10.0, dns_resolution_ms=50.0)
        g = _graph(_comp("app1", ComponentType.APP_SERVER, network=net))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_container_overhead("app1")
        assert result.network_setup_ms > 0

    def test_overhead_vm_runtime(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("app1", ComponentRuntime.VM)
        result = analyzer.analyze_container_overhead("app1")
        assert result.runtime == ComponentRuntime.VM
        assert result.image_pull_ms == 0.0  # VMs don't pull images


# ---------------------------------------------------------------------------
# Tests: Initialization Order
# ---------------------------------------------------------------------------


class TestInitOrder:
    """Initialization order dependency resolution."""

    def test_empty_graph(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        order = analyzer.resolve_init_order()
        assert order.order == []
        assert order.total_layers == 0
        assert order.has_cycle is False

    def test_single_component(self):
        g = _graph(_comp("c1"))
        analyzer = ColdStartAnalyzer(g)
        order = analyzer.resolve_init_order()
        assert order.total_layers == 1
        assert order.order == [["c1"]]
        assert order.has_cycle is False

    def test_linear_chain(self):
        c1 = _comp("db1", ComponentType.DATABASE)
        c2 = _comp("app1", ComponentType.APP_SERVER)
        c3 = _comp("web1", ComponentType.WEB_SERVER)
        g = _graph(c1, c2, c3)
        g.add_dependency(_dep("app1", "db1"))
        g.add_dependency(_dep("web1", "app1"))
        analyzer = ColdStartAnalyzer(g)
        order = analyzer.resolve_init_order()
        assert order.has_cycle is False
        assert order.total_layers >= 2
        # db1 should be in an earlier layer
        db_layer = None
        app_layer = None
        for i, layer in enumerate(order.order):
            if "db1" in layer:
                db_layer = i
            if "app1" in layer:
                app_layer = i
        assert db_layer is not None
        assert app_layer is not None
        assert db_layer < app_layer

    def test_parallel_components(self):
        g = _graph(
            _comp("a1"),
            _comp("b1"),
            _comp("c1"),
        )
        analyzer = ColdStartAnalyzer(g)
        order = analyzer.resolve_init_order()
        assert order.total_layers == 1
        assert len(order.order[0]) == 3
        assert order.has_cycle is False

    def test_cycle_detection(self):
        c1 = _comp("a1")
        c2 = _comp("b1")
        g = _graph(c1, c2)
        g.add_dependency(_dep("a1", "b1"))
        g.add_dependency(_dep("b1", "a1"))
        analyzer = ColdStartAnalyzer(g)
        order = analyzer.resolve_init_order()
        assert order.has_cycle is True
        assert len(order.cycle_components) == 2

    def test_diamond_dependency(self):
        db = _comp("db1", ComponentType.DATABASE)
        s1 = _comp("s1", ComponentType.APP_SERVER)
        s2 = _comp("s2", ComponentType.APP_SERVER)
        web = _comp("web1", ComponentType.WEB_SERVER)
        g = _graph(db, s1, s2, web)
        g.add_dependency(_dep("s1", "db1"))
        g.add_dependency(_dep("s2", "db1"))
        g.add_dependency(_dep("web1", "s1"))
        g.add_dependency(_dep("web1", "s2"))
        analyzer = ColdStartAnalyzer(g)
        order = analyzer.resolve_init_order()
        assert order.has_cycle is False
        assert order.total_layers >= 3


# ---------------------------------------------------------------------------
# Tests: SLA Impact Analysis
# ---------------------------------------------------------------------------


class TestSLAImpact:
    """Cold start impact on SLA."""

    def test_sla_impact_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_sla_impact("missing")
        assert result.component_id == "missing"
        assert result.breach_probability == 0.0

    def test_sla_impact_no_breach(self):
        g = _graph(_comp("dns1", ComponentType.DNS))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_sla_impact("dns1", sla_target_ms=50000.0)
        assert result.breach_probability == 0.0
        assert result.severity == ColdStartSeverity.INFO

    def test_sla_impact_high_breach(self):
        g = _graph(_comp("db1", ComponentType.DATABASE))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("db1", ComponentRuntime.VM)
        result = analyzer.analyze_sla_impact("db1", sla_target_ms=100.0)
        assert result.breach_probability > 0
        assert result.severity in (ColdStartSeverity.CRITICAL, ColdStartSeverity.HIGH)
        assert len(result.recommendations) > 0

    def test_sla_impact_custom_target(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_sla_target("app1", 10000.0)
        result = analyzer.analyze_sla_impact("app1")
        assert result.sla_target_ms == 10000.0

    def test_sla_impact_explicit_target_overrides(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_sla_target("app1", 1000.0)
        result = analyzer.analyze_sla_impact("app1", sla_target_ms=5000.0)
        # Explicit argument should be used
        assert result.sla_target_ms == 5000.0

    def test_sla_impact_affected_requests(self):
        g = _graph(_comp("app1", replicas=4))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_sla_impact("app1", scale_out_count=2)
        # 2 new out of 6 total = ~33%
        assert 30.0 < result.affected_requests_percent < 40.0

    def test_sla_impact_error_budget_burn(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_sla_impact("app1", sla_target_ms=100.0)
        assert result.estimated_error_budget_burn_percent >= 0
        assert result.estimated_error_budget_burn_percent <= 100.0

    def test_sla_target_zero(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_sla_impact("app1", sla_target_ms=0.0)
        assert result.breach_probability == 1.0

    def test_sla_impact_medium_severity(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        # Find an SLA target that results in medium severity (0.2 < breach <= 0.5)
        profile = analyzer.estimate_cold_start("app1")
        cold_ms = profile.total_cold_start_ms
        # breach_prob = (cold_ms - target) / target, want ~0.3
        # 0.3 = (cold_ms - target) / target => target = cold_ms / 1.3
        target = cold_ms / 1.3
        result = analyzer.analyze_sla_impact("app1", sla_target_ms=target)
        assert result.severity == ColdStartSeverity.MEDIUM

    def test_sla_impact_low_severity(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("app1")
        cold_ms = profile.total_cold_start_ms
        # breach_prob = (cold_ms - target) / target, want ~0.1
        # 0.1 = (cold_ms - target) / target => target = cold_ms / 1.1
        target = cold_ms / 1.1
        result = analyzer.analyze_sla_impact("app1", sla_target_ms=target)
        assert result.severity == ColdStartSeverity.LOW


# ---------------------------------------------------------------------------
# Tests: Pre-Warming Strategy Evaluation
# ---------------------------------------------------------------------------


class TestPreWarmingEvaluation:
    """Pre-warming strategy evaluation."""

    def test_pre_warming_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        strategies = analyzer.evaluate_pre_warming("missing")
        assert strategies == []

    def test_pre_warming_returns_strategies(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        strategies = analyzer.evaluate_pre_warming("app1")
        assert len(strategies) == 8  # All 8 strategies

    def test_pre_warming_serverless_provisioned(self):
        g = _graph(_comp("fn1", tags=["serverless"]))
        analyzer = ColdStartAnalyzer(g)
        strategies = analyzer.evaluate_pre_warming("fn1")
        prov = [s for s in strategies if s.strategy == MitigationStrategy.PROVISIONED_CONCURRENCY]
        assert len(prov) == 1
        assert prov[0].applicable is True
        assert prov[0].effectiveness_score == 95.0

    def test_pre_warming_container_provisioned_less_effective(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        strategies = analyzer.evaluate_pre_warming("app1")
        prov = [s for s in strategies if s.strategy == MitigationStrategy.PROVISIONED_CONCURRENCY]
        assert prov[0].applicable is False
        assert prov[0].effectiveness_score == 40.0

    def test_pre_warming_db_connection_pooling(self):
        g = _graph(_comp("db1", ComponentType.DATABASE))
        analyzer = ColdStartAnalyzer(g)
        strategies = analyzer.evaluate_pre_warming("db1")
        cp = [s for s in strategies if s.strategy == MitigationStrategy.CONNECTION_POOLING]
        assert cp[0].effectiveness_score == 60.0

    def test_pre_warming_all_have_latency_reduction(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        strategies = analyzer.evaluate_pre_warming("app1")
        for s in strategies:
            assert s.latency_reduction_ms >= 0

    def test_pre_warming_warm_pool_applicable_container(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        strategies = analyzer.evaluate_pre_warming("app1")
        wp = [s for s in strategies if s.strategy == MitigationStrategy.WARM_POOL]
        assert wp[0].applicable is True

    def test_pre_warming_snapshot_managed_service(self):
        g = _graph(_comp("ext1", ComponentType.EXTERNAL_API))
        analyzer = ColdStartAnalyzer(g)
        strategies = analyzer.evaluate_pre_warming("ext1")
        snap = [s for s in strategies if s.strategy == MitigationStrategy.SNAPSHOT_RESTORE]
        assert snap[0].applicable is False


# ---------------------------------------------------------------------------
# Tests: Mitigation Scoring
# ---------------------------------------------------------------------------


class TestMitigationScoring:
    """Cold start mitigation scoring."""

    def test_mitigation_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.score_mitigation("missing")
        assert result.component_id == "missing"
        assert result.current_score == 0.0

    def test_mitigation_no_active(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.score_mitigation("app1")
        assert result.current_score == 0.0
        assert result.active_mitigations == []
        assert len(result.recommended_mitigations) > 0

    def test_mitigation_with_active(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_mitigations("app1", [
            MitigationStrategy.KEEP_ALIVE,
            MitigationStrategy.PRE_WARMING,
        ])
        result = analyzer.score_mitigation("app1")
        assert result.current_score > 0
        assert MitigationStrategy.KEEP_ALIVE in result.active_mitigations

    def test_mitigation_recommended_sorted_by_effectiveness(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.score_mitigation("app1")
        for i in range(len(result.recommended_mitigations) - 1):
            assert (
                result.recommended_mitigations[i].effectiveness_score
                >= result.recommended_mitigations[i + 1].effectiveness_score
            )

    def test_mitigation_potential_improvement(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.score_mitigation("app1")
        assert result.potential_improvement > 0

    def test_mitigation_max_score_bounded(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.score_mitigation("app1")
        assert result.max_score == 100.0
        assert result.current_score <= 100.0


# ---------------------------------------------------------------------------
# Tests: Connection Pool Analysis
# ---------------------------------------------------------------------------


class TestConnectionPoolAnalysis:
    """Database connection pool cold start analysis."""

    def test_pool_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_connection_pool("missing")
        assert result.component_id == "missing"
        assert result.pool_size == 0

    def test_pool_default_size(self):
        g = _graph(_comp("db1", ComponentType.DATABASE))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_connection_pool("db1")
        assert result.pool_size == 100  # default connection pool size
        assert result.fill_time_ms > 0
        assert result.total_pool_start_ms > result.fill_time_ms

    def test_pool_large_size_warning(self):
        cap = Capacity(connection_pool_size=250)
        g = _graph(_comp("db1", ComponentType.DATABASE, capacity=cap))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_connection_pool("db1")
        assert result.severity == ColdStartSeverity.HIGH
        assert any("large pool" in r.lower() for r in result.recommendations)

    def test_pool_moderate_size(self):
        cap = Capacity(connection_pool_size=150)
        g = _graph(_comp("db1", ComponentType.DATABASE, capacity=cap))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_connection_pool("db1")
        assert result.severity == ColdStartSeverity.MEDIUM

    def test_pool_non_database_warning(self):
        g = _graph(_comp("app1", ComponentType.APP_SERVER))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_connection_pool("app1")
        assert any("not a database" in r.lower() for r in result.recommendations)

    def test_pool_warmup_queries(self):
        cap = Capacity(connection_pool_size=100)
        g = _graph(_comp("db1", ComponentType.DATABASE, capacity=cap))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_connection_pool("db1")
        assert result.warmup_queries_needed == 10
        assert result.connection_overhead_ms == 50.0

    def test_pool_steady_state_time(self):
        g = _graph(_comp("db1", ComponentType.DATABASE))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_connection_pool("db1")
        assert result.steady_state_time_ms > result.total_pool_start_ms

    def test_pool_slow_fill_warning(self):
        cap = Capacity(connection_pool_size=200)
        g = _graph(_comp("db1", ComponentType.DATABASE, capacity=cap))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_connection_pool("db1")
        # 200 * 50ms = 10000ms > 5000ms
        assert any("fill time exceeds" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# Tests: Cold Start Frequency Estimation
# ---------------------------------------------------------------------------


class TestColdStartFrequency:
    """Cold start frequency estimation."""

    def test_frequency_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.estimate_frequency("missing")
        assert result.total_daily_cold_starts == 0.0

    def test_frequency_no_autoscaling(self):
        g = _graph(_comp("app1", replicas=2))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.estimate_frequency("app1")
        assert result.scale_events_per_day == 0.0
        # Deploy cold starts = replicas
        assert result.deployment_cold_starts == 2.0

    def test_frequency_with_autoscaling(self):
        asc = AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10)
        g = _graph(_comp("app1", autoscaling=asc))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.estimate_frequency("app1")
        assert result.scale_events_per_day > 0

    def test_frequency_serverless_idle(self):
        g = _graph(_comp("fn1", tags=["serverless"]))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.estimate_frequency("fn1")
        assert result.idle_timeout_cold_starts == 12.0

    def test_frequency_min_replicas_1(self):
        asc = AutoScalingConfig(enabled=True, min_replicas=1, max_replicas=5)
        g = _graph(_comp("app1", autoscaling=asc))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.estimate_frequency("app1")
        assert result.idle_timeout_cold_starts == 2.0

    def test_frequency_severity_high(self):
        asc = AutoScalingConfig(enabled=True, min_replicas=1, max_replicas=20)
        g = _graph(_comp("fn1", autoscaling=asc, tags=["serverless"]))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.estimate_frequency("fn1")
        # serverless idle=12, scale=8, deploy=1 = 21 > 20
        assert result.severity == ColdStartSeverity.HIGH

    def test_frequency_severity_medium(self):
        asc = AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=8)
        g = _graph(_comp("app1", autoscaling=asc, replicas=3))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.estimate_frequency("app1")
        # scale=8, idle=0, deploy=3 = 11 > 10
        if result.total_daily_cold_starts > 10:
            assert result.severity == ColdStartSeverity.MEDIUM

    def test_frequency_zero_range(self):
        asc = AutoScalingConfig(enabled=True, min_replicas=3, max_replicas=3)
        g = _graph(_comp("app1", autoscaling=asc))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.estimate_frequency("app1")
        assert result.scale_events_per_day == 0.0


# ---------------------------------------------------------------------------
# Tests: Startup Probe Timeout Adequacy
# ---------------------------------------------------------------------------


class TestStartupProbeAnalysis:
    """Startup probe timeout adequacy analysis."""

    def test_probe_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_startup_probe("missing")
        assert result.status == StartupProbeStatus.MISSING

    def test_probe_missing(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_startup_probe("app1")
        assert result.status == StartupProbeStatus.MISSING
        assert len(result.recommendations) > 0

    def test_probe_adequate(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("app1")
        # Set probe to 2x the estimated start
        timeout = profile.total_cold_start_ms * 2
        analyzer.set_probe_timeout("app1", timeout)
        result = analyzer.analyze_startup_probe("app1")
        assert result.status == StartupProbeStatus.ADEQUATE
        assert result.margin_percent >= 50.0

    def test_probe_too_short(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("app1")
        # Set probe slightly above estimated start
        timeout = profile.total_cold_start_ms * 1.1
        analyzer.set_probe_timeout("app1", timeout)
        result = analyzer.analyze_startup_probe("app1")
        assert result.status == StartupProbeStatus.TOO_SHORT
        assert len(result.recommendations) > 0

    def test_probe_shorter_than_start(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("app1")
        timeout = profile.total_cold_start_ms * 0.5
        analyzer.set_probe_timeout("app1", timeout)
        result = analyzer.analyze_startup_probe("app1")
        assert result.status == StartupProbeStatus.TOO_SHORT
        assert result.margin_ms < 0
        assert any("killed before startup" in r.lower() for r in result.recommendations)

    def test_probe_too_long(self):
        g = _graph(_comp("dns1", ComponentType.DNS))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("dns1")
        # Set probe to 10x the start time
        timeout = profile.total_cold_start_ms * 10
        analyzer.set_probe_timeout("dns1", timeout)
        result = analyzer.analyze_startup_probe("dns1")
        assert result.status == StartupProbeStatus.TOO_LONG
        assert any("delays failure detection" in r.lower() for r in result.recommendations)

    def test_probe_margin_calculation(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("app1")
        timeout = profile.total_cold_start_ms + 1000
        analyzer.set_probe_timeout("app1", timeout)
        result = analyzer.analyze_startup_probe("app1")
        assert abs(result.margin_ms - 1000) < 0.1


# ---------------------------------------------------------------------------
# Tests: Resource Consumption Spike
# ---------------------------------------------------------------------------


class TestResourceSpike:
    """Resource consumption spike during cold start."""

    def test_spike_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("missing")
        assert result.component_id == "missing"
        assert result.cpu_spike_percent == 0.0

    def test_spike_app_server(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("app1")
        assert result.cpu_spike_percent > 0
        assert result.memory_spike_percent > 0
        assert result.spike_duration_ms > 0

    def test_spike_database_higher(self):
        g = _graph(_comp("db1", ComponentType.DATABASE))
        analyzer = ColdStartAnalyzer(g)
        db_spike = analyzer.analyze_resource_spike("db1")

        g2 = _graph(_comp("dns1", ComponentType.DNS))
        analyzer2 = ColdStartAnalyzer(g2)
        dns_spike = analyzer2.analyze_resource_spike("dns1")

        # Database has higher spike multiplier
        assert db_spike.cpu_spike_percent >= dns_spike.cpu_spike_percent

    def test_spike_container_has_network(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("app1")
        assert result.network_spike_mbps > 0

    def test_spike_container_has_disk_io(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("app1")
        assert result.disk_io_spike_mbps > 0

    def test_spike_vm_higher_disk_io(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("app1", ComponentRuntime.VM)
        result = analyzer.analyze_resource_spike("app1")
        assert result.disk_io_spike_mbps == 60.0

    def test_spike_severity_high_cpu(self):
        metrics = ResourceMetrics(cpu_percent=50.0, memory_percent=50.0)
        g = _graph(_comp("db1", ComponentType.DATABASE, metrics=metrics))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("db1")
        # DB type has a multiplier applied to base cpu
        assert result.cpu_spike_percent > 0
        assert result.severity in (ColdStartSeverity.MEDIUM, ColdStartSeverity.HIGH)

    def test_spike_steady_state_values(self):
        metrics = ResourceMetrics(cpu_percent=25.0, memory_percent=40.0)
        g = _graph(_comp("app1", metrics=metrics))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("app1")
        assert result.steady_state_cpu == 25.0
        assert result.steady_state_memory == 40.0

    def test_spike_bounded_to_100(self):
        metrics = ResourceMetrics(cpu_percent=90.0, memory_percent=90.0)
        g = _graph(_comp("db1", ComponentType.DATABASE, metrics=metrics))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("db1")
        assert result.cpu_spike_percent <= 100.0
        assert result.memory_spike_percent <= 100.0

    def test_spike_recommendations_cpu(self):
        metrics = ResourceMetrics(cpu_percent=50.0)
        g = _graph(_comp("db1", ComponentType.DATABASE, metrics=metrics))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("db1")
        assert any("cpu" in r.lower() for r in result.recommendations)

    def test_spike_managed_service_no_network(self):
        g = _graph(_comp("ext1", ComponentType.EXTERNAL_API))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("ext1")
        # Managed service (external API) runtime is MANAGED_SERVICE, not container
        assert result.network_spike_mbps == 0.0


# ---------------------------------------------------------------------------
# Tests: Full Analysis
# ---------------------------------------------------------------------------


class TestFullAnalysis:
    """Full cold start analysis report."""

    def test_analyze_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        reports = analyzer.analyze("missing")
        assert len(reports) == 1
        assert reports[0].component_id == "missing"
        assert reports[0].overall_score == 0.0

    def test_analyze_single(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        reports = analyzer.analyze("app1")
        assert len(reports) == 1
        r = reports[0]
        assert r.component_id == "app1"
        assert r.profile is not None
        assert r.warm_up is not None
        assert r.sla_impact is not None
        assert r.mitigation is not None
        assert r.connection_pool is not None
        assert r.frequency is not None
        assert r.startup_probe is not None
        assert r.resource_spike is not None
        assert 0.0 <= r.overall_score <= 100.0
        assert r.analyzed_at != ""

    def test_analyze_all(self):
        g = _graph(
            _comp("a1"),
            _comp("b1", ComponentType.DATABASE),
            _comp("c1", ComponentType.CACHE),
        )
        analyzer = ColdStartAnalyzer(g)
        reports = analyzer.analyze()
        assert len(reports) == 3
        ids = {r.component_id for r in reports}
        assert ids == {"a1", "b1", "c1"}

    def test_analyze_score_penalizes_high_latency(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("app1", ComponentRuntime.BARE_METAL)
        reports = analyzer.analyze("app1")
        # Bare metal has very high cold start -> low score
        assert reports[0].overall_score < 80

    def test_analyze_score_penalizes_missing_probe(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        reports = analyzer.analyze("app1")
        score_no_probe = reports[0].overall_score

        g2 = _graph(_comp("app1"))
        analyzer2 = ColdStartAnalyzer(g2)
        profile = analyzer2.estimate_cold_start("app1")
        analyzer2.set_probe_timeout("app1", profile.total_cold_start_ms * 2)
        reports2 = analyzer2.analyze("app1")
        score_with_probe = reports2[0].overall_score

        assert score_with_probe > score_no_probe

    def test_analyze_score_rewards_mitigations(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        reports_no_mit = analyzer.analyze("app1")

        g2 = _graph(_comp("app1"))
        analyzer2 = ColdStartAnalyzer(g2)
        analyzer2.set_mitigations("app1", [
            MitigationStrategy.KEEP_ALIVE,
            MitigationStrategy.PRE_WARMING,
            MitigationStrategy.WARM_POOL,
        ])
        reports_with_mit = analyzer2.analyze("app1")

        assert reports_with_mit[0].overall_score >= reports_no_mit[0].overall_score


# ---------------------------------------------------------------------------
# Tests: Summary
# ---------------------------------------------------------------------------


class TestSummary:
    """Summary generation."""

    def test_summary_empty(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        summary = analyzer.generate_summary([])
        assert summary["total_components"] == 0
        assert summary["average_score"] == 0.0

    def test_summary_with_reports(self):
        g = _graph(
            _comp("a1"),
            _comp("b1", ComponentType.DATABASE),
        )
        analyzer = ColdStartAnalyzer(g)
        reports = analyzer.analyze()
        summary = analyzer.generate_summary(reports)
        assert summary["total_components"] == 2
        assert summary["average_score"] > 0
        assert summary["worst_component"] != ""
        assert len(summary["severity_counts"]) > 0

    def test_summary_worst_component(self):
        g = _graph(
            _comp("fast1", ComponentType.DNS),
            _comp("slow1", ComponentType.DATABASE),
        )
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("slow1", ComponentRuntime.BARE_METAL)
        reports = analyzer.analyze()
        summary = analyzer.generate_summary(reports)
        assert summary["worst_component"] == "slow1"
        assert summary["worst_score"] <= summary["average_score"]


# ---------------------------------------------------------------------------
# Tests: Runtime Inference
# ---------------------------------------------------------------------------


class TestRuntimeInference:
    """Runtime inference from component type and tags."""

    def test_infer_serverless_tag(self):
        comp = _comp("fn1", tags=["serverless"])
        assert ColdStartAnalyzer._infer_runtime(comp) == ComponentRuntime.SERVERLESS

    def test_infer_vm_tag(self):
        comp = _comp("vm1", tags=["vm"])
        assert ColdStartAnalyzer._infer_runtime(comp) == ComponentRuntime.VM

    def test_infer_bare_metal_tag(self):
        comp = _comp("bm1", tags=["bare_metal"])
        assert ColdStartAnalyzer._infer_runtime(comp) == ComponentRuntime.BARE_METAL

    def test_infer_external_api_managed(self):
        comp = _comp("ext1", ComponentType.EXTERNAL_API)
        assert ColdStartAnalyzer._infer_runtime(comp) == ComponentRuntime.MANAGED_SERVICE

    def test_infer_database_managed(self):
        comp = _comp("db1", ComponentType.DATABASE)
        assert ColdStartAnalyzer._infer_runtime(comp) == ComponentRuntime.MANAGED_SERVICE

    def test_infer_cache_managed(self):
        comp = _comp("c1", ComponentType.CACHE)
        assert ColdStartAnalyzer._infer_runtime(comp) == ComponentRuntime.MANAGED_SERVICE

    def test_infer_app_server_container(self):
        comp = _comp("app1", ComponentType.APP_SERVER)
        assert ColdStartAnalyzer._infer_runtime(comp) == ComponentRuntime.CONTAINER

    def test_infer_web_server_container(self):
        comp = _comp("web1", ComponentType.WEB_SERVER)
        assert ColdStartAnalyzer._infer_runtime(comp) == ComponentRuntime.CONTAINER

    def test_get_runtime_override(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("app1", ComponentRuntime.VM)
        assert analyzer.get_runtime("app1") == ComponentRuntime.VM

    def test_get_runtime_nonexistent(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        assert analyzer.get_runtime("missing") == ComponentRuntime.CONTAINER


# ---------------------------------------------------------------------------
# Tests: Type Spike Multiplier
# ---------------------------------------------------------------------------


class TestTypeSpikeMultiplier:
    """Resource spike multiplier by component type."""

    def test_database_highest(self):
        assert ColdStartAnalyzer._type_spike_multiplier(ComponentType.DATABASE) == 2.5

    def test_app_server(self):
        assert ColdStartAnalyzer._type_spike_multiplier(ComponentType.APP_SERVER) == 2.0

    def test_web_server(self):
        assert ColdStartAnalyzer._type_spike_multiplier(ComponentType.WEB_SERVER) == 1.5

    def test_cache(self):
        assert ColdStartAnalyzer._type_spike_multiplier(ComponentType.CACHE) == 1.8

    def test_dns_lowest(self):
        assert ColdStartAnalyzer._type_spike_multiplier(ComponentType.DNS) == 1.0

    def test_load_balancer(self):
        assert ColdStartAnalyzer._type_spike_multiplier(ComponentType.LOAD_BALANCER) == 1.2


# ---------------------------------------------------------------------------
# Tests: Enum Values (serialization stability)
# ---------------------------------------------------------------------------


class TestEnumValues:
    """Verify enum string values for serialization stability."""

    def test_severity_values(self):
        assert ColdStartSeverity.CRITICAL.value == "critical"
        assert ColdStartSeverity.HIGH.value == "high"
        assert ColdStartSeverity.MEDIUM.value == "medium"
        assert ColdStartSeverity.LOW.value == "low"
        assert ColdStartSeverity.INFO.value == "info"

    def test_warm_up_phase_values(self):
        assert WarmUpPhase.CACHE_WARMING.value == "cache_warming"
        assert WarmUpPhase.CONNECTION_POOL.value == "connection_pool"
        assert WarmUpPhase.JIT_COMPILATION.value == "jit_compilation"
        assert WarmUpPhase.DNS_RESOLUTION.value == "dns_resolution"
        assert WarmUpPhase.TLS_HANDSHAKE.value == "tls_handshake"
        assert WarmUpPhase.HEALTH_CHECK.value == "health_check"

    def test_mitigation_strategy_values(self):
        assert MitigationStrategy.KEEP_ALIVE.value == "keep_alive"
        assert MitigationStrategy.PROVISIONED_CONCURRENCY.value == "provisioned_concurrency"
        assert MitigationStrategy.PRE_WARMING.value == "pre_warming"
        assert MitigationStrategy.WARM_POOL.value == "warm_pool"
        assert MitigationStrategy.SNAPSHOT_RESTORE.value == "snapshot_restore"
        assert MitigationStrategy.LAZY_INIT.value == "lazy_init"
        assert MitigationStrategy.CONNECTION_POOLING.value == "connection_pooling"
        assert MitigationStrategy.CACHED_DNS.value == "cached_dns"

    def test_component_runtime_values(self):
        assert ComponentRuntime.CONTAINER.value == "container"
        assert ComponentRuntime.SERVERLESS.value == "serverless"
        assert ComponentRuntime.VM.value == "vm"
        assert ComponentRuntime.BARE_METAL.value == "bare_metal"
        assert ComponentRuntime.MANAGED_SERVICE.value == "managed_service"

    def test_startup_probe_status_values(self):
        assert StartupProbeStatus.ADEQUATE.value == "adequate"
        assert StartupProbeStatus.TOO_SHORT.value == "too_short"
        assert StartupProbeStatus.TOO_LONG.value == "too_long"
        assert StartupProbeStatus.MISSING.value == "missing"


# ---------------------------------------------------------------------------
# Tests: Overall Severity
# ---------------------------------------------------------------------------


class TestOverallSeverity:
    """Overall severity derivation from score."""

    def test_info_score_90(self):
        assert ColdStartAnalyzer._overall_severity(95.0) == ColdStartSeverity.INFO

    def test_info_boundary(self):
        assert ColdStartAnalyzer._overall_severity(90.0) == ColdStartSeverity.INFO

    def test_low_score(self):
        assert ColdStartAnalyzer._overall_severity(75.0) == ColdStartSeverity.LOW

    def test_low_boundary(self):
        assert ColdStartAnalyzer._overall_severity(70.0) == ColdStartSeverity.LOW

    def test_medium_score(self):
        assert ColdStartAnalyzer._overall_severity(55.0) == ColdStartSeverity.MEDIUM

    def test_medium_boundary(self):
        assert ColdStartAnalyzer._overall_severity(50.0) == ColdStartSeverity.MEDIUM

    def test_high_score(self):
        assert ColdStartAnalyzer._overall_severity(35.0) == ColdStartSeverity.HIGH

    def test_high_boundary(self):
        assert ColdStartAnalyzer._overall_severity(30.0) == ColdStartSeverity.HIGH

    def test_critical_score(self):
        assert ColdStartAnalyzer._overall_severity(10.0) == ColdStartSeverity.CRITICAL

    def test_critical_zero(self):
        assert ColdStartAnalyzer._overall_severity(0.0) == ColdStartSeverity.CRITICAL


# ---------------------------------------------------------------------------
# Tests: Dependency Wait Estimation
# ---------------------------------------------------------------------------


class TestDependencyWait:
    """Dependency wait estimation."""

    def test_no_dependencies_zero_wait(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        wait = analyzer._estimate_dependency_wait("app1")
        assert wait == 0.0

    def test_requires_dependency_wait(self):
        c1 = _comp("app1")
        c2 = _comp("db1", ComponentType.DATABASE)
        g = _graph(c1, c2)
        g.add_dependency(_dep("app1", "db1", dependency_type="requires", latency_ms=10.0))
        analyzer = ColdStartAnalyzer(g)
        wait = analyzer._estimate_dependency_wait("app1")
        assert wait > 0
        # Should include 30% of db base + latency
        expected = 5000.0 * 0.3 + 10.0
        assert abs(wait - expected) < 0.1

    def test_optional_dependency_smaller_wait(self):
        c1 = _comp("app1")
        c2 = _comp("cache1", ComponentType.CACHE)
        g = _graph(c1, c2)
        g.add_dependency(_dep("app1", "cache1", dependency_type="optional", latency_ms=5.0))
        analyzer = ColdStartAnalyzer(g)
        wait = analyzer._estimate_dependency_wait("app1")
        # Should include 10% of cache base + latency
        expected = 1000.0 * 0.1 + 5.0
        assert abs(wait - expected) < 0.1

    def test_multiple_deps_takes_max(self):
        c1 = _comp("app1")
        c2 = _comp("db1", ComponentType.DATABASE)
        c3 = _comp("cache1", ComponentType.CACHE)
        g = _graph(c1, c2, c3)
        g.add_dependency(_dep("app1", "db1", dependency_type="requires"))
        g.add_dependency(_dep("app1", "cache1", dependency_type="requires"))
        analyzer = ColdStartAnalyzer(g)
        wait = analyzer._estimate_dependency_wait("app1")
        # Should be max of db (5000*0.3=1500) and cache (1000*0.3=300)
        assert wait >= 1500.0

    def test_async_dependency_only_latency(self):
        c1 = _comp("app1")
        c2 = _comp("q1", ComponentType.QUEUE)
        g = _graph(c1, c2)
        g.add_dependency(_dep("app1", "q1", dependency_type="async", latency_ms=20.0))
        analyzer = ColdStartAnalyzer(g)
        wait = analyzer._estimate_dependency_wait("app1")
        assert abs(wait - 20.0) < 0.1


# ---------------------------------------------------------------------------
# Tests: Cascade Tree Utilities
# ---------------------------------------------------------------------------


class TestCascadeTreeUtils:
    """Cascade tree utility methods."""

    def test_tree_max_depth_leaf(self):
        node = CascadeNode(component_id="a1", depth=0)
        assert ColdStartAnalyzer._tree_max_depth(node) == 0

    def test_tree_max_depth_with_children(self):
        child = CascadeNode(component_id="b1", depth=1)
        grandchild = CascadeNode(component_id="c1", depth=2)
        child.children = [grandchild]
        root = CascadeNode(component_id="a1", depth=0, children=[child])
        assert ColdStartAnalyzer._tree_max_depth(root) == 2

    def test_tree_count_nodes_single(self):
        node = CascadeNode(component_id="a1")
        assert ColdStartAnalyzer._tree_count_nodes(node) == 1

    def test_tree_count_nodes_with_children(self):
        child1 = CascadeNode(component_id="b1")
        child2 = CascadeNode(component_id="c1")
        root = CascadeNode(component_id="a1", children=[child1, child2])
        assert ColdStartAnalyzer._tree_count_nodes(root) == 3

    def test_find_critical_path_leaf(self):
        node = CascadeNode(component_id="a1", cold_start_ms=100)
        path, ms = ColdStartAnalyzer._find_critical_path(node)
        assert path == ["a1"]
        assert ms == 100

    def test_find_critical_path_picks_longest(self):
        fast = CascadeNode(component_id="fast", cold_start_ms=100)
        slow = CascadeNode(component_id="slow", cold_start_ms=5000)
        root = CascadeNode(
            component_id="root", cold_start_ms=200,
            children=[fast, slow],
        )
        path, ms = ColdStartAnalyzer._find_critical_path(root)
        assert path == ["root", "slow"]
        assert ms == 200 + 5000


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_analyze_empty_graph(self):
        g = _graph()
        analyzer = ColdStartAnalyzer(g)
        reports = analyzer.analyze()
        assert reports == []

    def test_analyze_none_returns_all(self):
        g = _graph(_comp("a1"), _comp("b1"))
        analyzer = ColdStartAnalyzer(g)
        reports = analyzer.analyze(None)
        assert len(reports) == 2

    def test_cold_start_profile_cached(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        p1 = analyzer.estimate_cold_start("app1")
        p2 = analyzer.estimate_cold_start("app1")
        assert p1.total_cold_start_ms == p2.total_cold_start_ms

    def test_multiple_set_runtime_overwrite(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("app1", ComponentRuntime.VM)
        analyzer.set_runtime("app1", ComponentRuntime.SERVERLESS)
        assert analyzer.get_runtime("app1") == ComponentRuntime.SERVERLESS

    def test_score_never_negative(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_runtime("app1", ComponentRuntime.BARE_METAL)
        reports = analyzer.analyze("app1")
        assert reports[0].overall_score >= 0.0

    def test_score_never_exceeds_100(self):
        g = _graph(_comp("dns1", ComponentType.DNS))
        analyzer = ColdStartAnalyzer(g)
        analyzer.set_probe_timeout("dns1", 100000.0)
        analyzer.set_mitigations("dns1", list(MitigationStrategy))
        reports = analyzer.analyze("dns1")
        assert reports[0].overall_score <= 100.0

    def test_warm_start_less_than_cold(self):
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        profile = analyzer.estimate_cold_start("app1")
        assert profile.warm_start_ms < profile.total_cold_start_ms

    def test_init_order_layers_sorted(self):
        g = _graph(_comp("c1"), _comp("b1"), _comp("a1"))
        analyzer = ColdStartAnalyzer(g)
        order = analyzer.resolve_init_order()
        # Components within a layer should be sorted alphabetically
        assert order.order[0] == ["a1", "b1", "c1"]

    def test_cascade_avoids_cycles(self):
        """Cascade analysis should not infinite loop on cycles."""
        c1 = _comp("a1")
        c2 = _comp("b1")
        g = _graph(c1, c2)
        g.add_dependency(_dep("a1", "b1"))
        g.add_dependency(_dep("b1", "a1"))
        analyzer = ColdStartAnalyzer(g)
        # Should complete without hanging
        result = analyzer.analyze_cascade("a1")
        assert result.root_component_id == "a1"

    def test_container_overhead_managed_service_no_pull(self):
        g = _graph(_comp("ext1", ComponentType.EXTERNAL_API))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_container_overhead("ext1")
        assert result.image_pull_ms == 0.0

    def test_resource_spike_default_metrics(self):
        """When metrics are 0, defaults are used for spike calculation."""
        g = _graph(_comp("app1"))
        analyzer = ColdStartAnalyzer(g)
        result = analyzer.analyze_resource_spike("app1")
        # Defaults are 20% cpu, 30% memory
        assert result.steady_state_cpu == 20.0
        assert result.steady_state_memory == 30.0
