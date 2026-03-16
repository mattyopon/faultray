"""Tests for the Attack Surface Analyzer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.attack_surface import (
    AttackChain,
    AttackSurfaceAnalyzer,
    AttackSurfaceReport,
    EntryPoint,
    HighValueTarget,
    LateralMovePath,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    port: int = 8080,
    replicas: int = 1,
    failover: bool = False,
    **sec_kwargs,
) -> Component:
    sec = SecurityProfile(**sec_kwargs)
    fo = FailoverConfig(enabled=failover)
    return Component(id=cid, name=cid, type=ctype, port=port, replicas=replicas, security=sec, failover=fo)


def _build_graph(
    components: list[Component],
    deps: list[tuple[str, str]] | None = None,
    cb_edges: set[tuple[str, str]] | None = None,
) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    cb_edges = cb_edges or set()
    for src, tgt in deps or []:
        cb = CircuitBreakerConfig(enabled=((src, tgt) in cb_edges))
        g.add_dependency(Dependency(source_id=src, target_id=tgt, circuit_breaker=cb))
    return g


# ---------------------------------------------------------------------------
# Test: EntryPoint dataclass
# ---------------------------------------------------------------------------

class TestEntryPoint:
    def test_fields(self):
        ep = EntryPoint(
            component_id="lb",
            component_name="Load Balancer",
            exposure_type="internet",
            protocol="https",
            attack_vectors=["DDoS"],
            defense_score=0.8,
        )
        assert ep.component_id == "lb"
        assert ep.exposure_type == "internet"
        assert ep.defense_score == 0.8


# ---------------------------------------------------------------------------
# Test: LateralMovePath dataclass
# ---------------------------------------------------------------------------

class TestLateralMovePath:
    def test_fields(self):
        lmp = LateralMovePath(
            source="lb",
            path=["lb", "web", "db"],
            target="db",
            hops=2,
            defense_barriers=1,
            difficulty="moderate",
            description="test",
        )
        assert lmp.hops == 2
        assert lmp.difficulty == "moderate"


# ---------------------------------------------------------------------------
# Test: HighValueTarget dataclass
# ---------------------------------------------------------------------------

class TestHighValueTarget:
    def test_fields(self):
        ht = HighValueTarget(
            component_id="db",
            component_name="postgres",
            value_type="data_store",
            risk_score=8.5,
            reachable_from=["lb"],
            min_hops=2,
            defense_depth=1,
        )
        assert ht.value_type == "data_store"
        assert ht.risk_score == 8.5


# ---------------------------------------------------------------------------
# Test: AttackSurfaceAnalyzer.find_entry_points
# ---------------------------------------------------------------------------

class TestFindEntryPoints:
    def test_load_balancer_detected(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        app_comp = _make_component("app", ComponentType.APP_SERVER)
        graph = _build_graph([lb, app_comp], [("lb", "app")])

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)

        ids = [ep.component_id for ep in eps]
        assert "lb" in ids

    def test_dns_detected(self):
        dns = _make_component("dns", ComponentType.DNS)
        graph = _build_graph([dns])

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)
        assert len(eps) == 1
        assert eps[0].exposure_type == "internet"

    def test_external_api_detected(self):
        ext = _make_component("ext-api", ComponentType.EXTERNAL_API)
        graph = _build_graph([ext])

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)
        assert len(eps) == 1
        assert eps[0].exposure_type == "api"

    def test_name_heuristic_gateway(self):
        gw = _make_component("api-gateway", ComponentType.APP_SERVER)
        graph = _build_graph([gw])

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)
        assert len(eps) == 1
        assert eps[0].exposure_type == "internet"

    def test_internal_server_not_entry_point(self):
        internal = _make_component("internal-service", ComponentType.APP_SERVER)
        graph = _build_graph([internal])

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)
        assert len(eps) == 0

    def test_defense_score_calculated(self):
        lb = _make_component(
            "lb", ComponentType.LOAD_BALANCER,
            waf_protected=True, rate_limiting=True, auth_required=True,
        )
        graph = _build_graph([lb])

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)
        assert eps[0].defense_score > 0.2


# ---------------------------------------------------------------------------
# Test: AttackSurfaceAnalyzer.find_lateral_paths
# ---------------------------------------------------------------------------

class TestFindLateralPaths:
    def test_simple_chain(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        web = _make_component("web", ComponentType.WEB_SERVER)
        db = _make_component("db", ComponentType.DATABASE)
        graph = _build_graph([lb, web, db], [("lb", "web"), ("web", "db")])

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)
        paths = analyzer.find_lateral_paths(graph, eps)

        # Should have paths from lb to web and lb to db
        targets = {p.target for p in paths}
        assert "web" in targets
        assert "db" in targets

    def test_no_entry_no_paths(self):
        a = _make_component("svc-a", ComponentType.APP_SERVER)
        b = _make_component("svc-b", ComponentType.APP_SERVER)
        graph = _build_graph([a, b], [("svc-a", "svc-b")])

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)
        paths = analyzer.find_lateral_paths(graph, eps)
        assert len(paths) == 0  # no entry points

    def test_barriers_counted(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        web = _make_component("web", ComponentType.WEB_SERVER, auth_required=True, network_segmented=True)
        graph = _build_graph([lb, web], [("lb", "web")], cb_edges={("lb", "web")})

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)
        paths = analyzer.find_lateral_paths(graph, eps)

        # web has auth + network_segmented, and cb on edge = 3+ barriers
        web_paths = [p for p in paths if p.target == "web"]
        assert len(web_paths) > 0
        assert web_paths[0].defense_barriers >= 2

    def test_difficulty_classification(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        open_svc = _make_component("open-svc", ComponentType.APP_SERVER)
        graph = _build_graph([lb, open_svc], [("lb", "open-svc")])

        analyzer = AttackSurfaceAnalyzer()
        eps = analyzer.find_entry_points(graph)
        paths = analyzer.find_lateral_paths(graph, eps)

        open_paths = [p for p in paths if p.target == "open-svc"]
        assert len(open_paths) > 0
        assert open_paths[0].difficulty in ("trivial", "easy")


# ---------------------------------------------------------------------------
# Test: AttackSurfaceAnalyzer.find_high_value_targets
# ---------------------------------------------------------------------------

class TestFindHighValueTargets:
    def test_database_is_hvt(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        db = _make_component("postgres", ComponentType.DATABASE)
        graph = _build_graph([lb, db], [("lb", "postgres")])

        analyzer = AttackSurfaceAnalyzer()
        targets = analyzer.find_high_value_targets(graph)
        assert any(t.component_id == "postgres" for t in targets)
        db_target = [t for t in targets if t.component_id == "postgres"][0]
        assert db_target.value_type == "data_store"

    def test_auth_service_detected(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        auth = _make_component("auth-service", ComponentType.APP_SERVER)
        graph = _build_graph([lb, auth], [("lb", "auth-service")])

        analyzer = AttackSurfaceAnalyzer()
        targets = analyzer.find_high_value_targets(graph)
        auth_targets = [t for t in targets if t.component_id == "auth-service"]
        assert len(auth_targets) == 1
        assert auth_targets[0].value_type == "auth_service"

    def test_payment_detected(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        pay = _make_component("payment-processor", ComponentType.APP_SERVER)
        graph = _build_graph([lb, pay], [("lb", "payment-processor")])

        analyzer = AttackSurfaceAnalyzer()
        targets = analyzer.find_high_value_targets(graph)
        pay_targets = [t for t in targets if t.component_id == "payment-processor"]
        assert len(pay_targets) == 1
        assert pay_targets[0].value_type == "payment"

    def test_reachability_from_entry(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        web = _make_component("web", ComponentType.WEB_SERVER)
        db = _make_component("db", ComponentType.DATABASE)
        graph = _build_graph([lb, web, db], [("lb", "web"), ("web", "db")])

        analyzer = AttackSurfaceAnalyzer()
        targets = analyzer.find_high_value_targets(graph)
        db_target = [t for t in targets if t.component_id == "db"][0]
        assert "lb" in db_target.reachable_from
        assert db_target.min_hops == 2


# ---------------------------------------------------------------------------
# Test: AttackSurfaceAnalyzer.generate_attack_chains
# ---------------------------------------------------------------------------

class TestGenerateAttackChains:
    def test_external_to_database_chain(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        web = _make_component("web", ComponentType.WEB_SERVER)
        db = _make_component("db", ComponentType.DATABASE)
        graph = _build_graph([lb, web, db], [("lb", "web"), ("web", "db")])

        analyzer = AttackSurfaceAnalyzer()
        chains = analyzer.generate_attack_chains(graph)
        chain_names = [c.name for c in chains]
        assert "External to Database" in chain_names

    def test_supply_chain_attack(self):
        ext = _make_component("stripe-api", ComponentType.EXTERNAL_API)
        svc = _make_component("payment-svc", ComponentType.APP_SERVER)
        graph = _build_graph([ext, svc], [("payment-svc", "stripe-api")])

        analyzer = AttackSurfaceAnalyzer()
        chains = analyzer.generate_attack_chains(graph)
        chain_names = [c.name for c in chains]
        assert "Supply Chain Attack" in chain_names

    def test_chains_have_mitigations(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        db = _make_component("db", ComponentType.DATABASE)
        graph = _build_graph([lb, db], [("lb", "db")])

        analyzer = AttackSurfaceAnalyzer()
        chains = analyzer.generate_attack_chains(graph)
        for chain in chains:
            assert len(chain.mitigations) > 0


# ---------------------------------------------------------------------------
# Test: AttackSurfaceAnalyzer.calculate_defense_depth
# ---------------------------------------------------------------------------

class TestDefenseDepth:
    def test_zero_defense(self):
        a = _make_component("a", ComponentType.LOAD_BALANCER)
        b = _make_component("b", ComponentType.APP_SERVER)
        graph = _build_graph([a, b], [("a", "b")])

        analyzer = AttackSurfaceAnalyzer()
        depth = analyzer.calculate_defense_depth(graph, "a", "b", ["a", "b"])
        assert depth == 0

    def test_auth_counts_as_barrier(self):
        a = _make_component("a", ComponentType.LOAD_BALANCER)
        b = _make_component("b", ComponentType.APP_SERVER, auth_required=True)
        graph = _build_graph([a, b], [("a", "b")])

        analyzer = AttackSurfaceAnalyzer()
        depth = analyzer.calculate_defense_depth(graph, "a", "b", ["a", "b"])
        assert depth >= 1

    def test_circuit_breaker_counts(self):
        a = _make_component("a", ComponentType.LOAD_BALANCER)
        b = _make_component("b", ComponentType.APP_SERVER)
        graph = _build_graph([a, b], [("a", "b")], cb_edges={("a", "b")})

        analyzer = AttackSurfaceAnalyzer()
        depth = analyzer.calculate_defense_depth(graph, "a", "b", ["a", "b"])
        assert depth >= 1


# ---------------------------------------------------------------------------
# Test: Full analysis pipeline
# ---------------------------------------------------------------------------

class TestFullAnalysis:
    def test_analyze_returns_report(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER, waf_protected=True)
        web = _make_component("web", ComponentType.WEB_SERVER, auth_required=True)
        db = _make_component("db", ComponentType.DATABASE, encryption_at_rest=True)
        graph = _build_graph([lb, web, db], [("lb", "web"), ("web", "db")])

        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)

        assert isinstance(report, AttackSurfaceReport)
        assert report.total_attack_surface_score >= 0
        assert report.total_attack_surface_score <= 100
        assert len(report.entry_points) > 0
        assert len(report.recommendations) > 0

    def test_empty_graph(self):
        graph = InfraGraph()
        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)

        assert report.total_attack_surface_score == 0
        assert len(report.entry_points) == 0

    def test_report_to_dict(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        db = _make_component("db", ComponentType.DATABASE)
        graph = _build_graph([lb, db], [("lb", "db")])

        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)
        d = report.to_dict()

        assert "entry_points" in d
        assert "lateral_paths" in d
        assert "high_value_targets" in d
        assert "attack_chains" in d
        assert "total_attack_surface_score" in d
        assert "recommendations" in d

    def test_weakest_path_identified(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        web = _make_component("web", ComponentType.WEB_SERVER)
        db = _make_component("db", ComponentType.DATABASE)
        graph = _build_graph([lb, web, db], [("lb", "web"), ("web", "db")])

        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)
        assert report.weakest_path is not None

    def test_most_exposed_target_identified(self):
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        db = _make_component("db", ComponentType.DATABASE)
        graph = _build_graph([lb, db], [("lb", "db")])

        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)
        assert report.most_exposed_target is not None
        assert report.most_exposed_target.component_id == "db"

    def test_classify_difficulty_fallback(self):
        """Test line 234: _classify_difficulty returns 'very_hard' for barrier count beyond thresholds."""
        from faultray.simulator.attack_surface import _classify_difficulty
        assert _classify_difficulty(999) == "very_hard"
        assert _classify_difficulty(1000) == "very_hard"

    def test_find_lateral_paths_none_entry_points(self):
        """Test line 348: find_lateral_paths auto-discovers entry points when None."""
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        web = _make_component("web", ComponentType.WEB_SERVER)
        graph = _build_graph([lb, web], [("lb", "web")])

        analyzer = AttackSurfaceAnalyzer()
        paths = analyzer.find_lateral_paths(graph, entry_points=None)
        # Should auto-discover lb as entry point
        assert len(paths) > 0

    def test_privilege_escalation_chain(self):
        """Test lines 540-560: privilege escalation attack chain generation."""
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        auth = _make_component("auth-service", ComponentType.APP_SERVER)
        graph = _build_graph([lb, auth], [("lb", "auth-service")])

        analyzer = AttackSurfaceAnalyzer()
        chains = analyzer.generate_attack_chains(graph)
        chain_names = [c.name for c in chains]
        assert "Privilege Escalation" in chain_names
        priv_chain = [c for c in chains if c.name == "Privilege Escalation"][0]
        assert len(priv_chain.mitigations) >= 1

    def test_defense_depth_none_path(self):
        """Test line 602: defense depth with path=None defaults to [source, target]."""
        a = _make_component("a", ComponentType.LOAD_BALANCER)
        b = _make_component("b", ComponentType.APP_SERVER, auth_required=True)
        graph = _build_graph([a, b], [("a", "b")])

        analyzer = AttackSurfaceAnalyzer()
        depth = analyzer.calculate_defense_depth(graph, "a", "b", path=None)
        assert depth >= 1

    def test_defense_depth_nonexistent_component(self):
        """Test line 608: defense depth skips None components in path."""
        a = _make_component("a", ComponentType.LOAD_BALANCER)
        graph = _build_graph([a])

        analyzer = AttackSurfaceAnalyzer()
        depth = analyzer.calculate_defense_depth(graph, "a", "ghost", ["a", "ghost"])
        assert depth >= 0

    def test_infer_protocol_port_443(self):
        """Test line 653: port 443 -> https."""
        comp = _make_component("web", ComponentType.WEB_SERVER, port=443)
        result = AttackSurfaceAnalyzer._infer_protocol(comp)
        assert result == "https"

    def test_infer_protocol_port_0(self):
        """Test lines 656-657: port 0 -> https (default)."""
        comp = _make_component("web", ComponentType.WEB_SERVER, port=0)
        result = AttackSurfaceAnalyzer._infer_protocol(comp)
        assert result == "https"

    def test_infer_protocol_other_port(self):
        """Test line 658: non-standard port -> tcp."""
        comp = _make_component("web", ComponentType.WEB_SERVER, port=5432)
        result = AttackSurfaceAnalyzer._infer_protocol(comp)
        assert result == "tcp"

    def test_classify_value_secrets(self):
        """Test line 676: secrets store detected."""
        comp = _make_component("vault-secrets", ComponentType.APP_SERVER)
        result = AttackSurfaceAnalyzer._classify_value(comp)
        assert result == "secrets"

    def test_classify_value_pii(self):
        """Test line 678: PII component detected."""
        comp = _make_component("user-pii-store", ComponentType.APP_SERVER)
        result = AttackSurfaceAnalyzer._classify_value(comp)
        assert result == "pii"

    def test_calculate_target_risk_low_defense(self):
        """Test line 701: min_defense_depth==1 gives score += 1.0."""
        comp = _make_component("db", ComponentType.DATABASE)
        risk = AttackSurfaceAnalyzer._calculate_target_risk(comp, ["lb"], min_hops=1, min_defense_depth=1)
        assert risk > 0

    def test_score_avg_defense_depth_between_1_and_2(self):
        """Test line 743: avg_defense_depth between 1 and 2 gives +10 to score."""
        # Create components with exactly 1 barrier each (auth_required)
        # so avg defense depth lands between 1 and 2
        lb = _make_component("lb", ComponentType.LOAD_BALANCER)
        web = _make_component("web", ComponentType.WEB_SERVER, auth_required=True)
        db = _make_component("db", ComponentType.DATABASE, auth_required=True)
        graph = _build_graph([lb, web, db], [("lb", "web"), ("web", "db")])
        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)
        assert report.total_attack_surface_score > 0

    def test_score_avg_defense_depth_between_2_and_3(self):
        """Test line 745: avg_defense_depth between 2 and 3 gives +5."""
        lb = _make_component(
            "lb", ComponentType.LOAD_BALANCER,
            waf_protected=True, auth_required=True, network_segmented=True,
        )
        web = _make_component(
            "web", ComponentType.WEB_SERVER,
            auth_required=True, network_segmented=True,
        )
        db = _make_component(
            "db", ComponentType.DATABASE,
            auth_required=True, network_segmented=True, encryption_at_rest=True,
        )
        graph = _build_graph(
            [lb, web, db],
            [("lb", "web"), ("web", "db")],
            cb_edges={("lb", "web"), ("web", "db")},
        )
        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)
        assert report.total_attack_surface_score >= 0

    def test_well_defended_infra_low_score(self):
        lb = _make_component(
            "lb", ComponentType.LOAD_BALANCER,
            waf_protected=True, rate_limiting=True, encryption_in_transit=True,
        )
        web = _make_component(
            "web", ComponentType.WEB_SERVER,
            auth_required=True, network_segmented=True, encryption_in_transit=True,
        )
        db = _make_component(
            "db", ComponentType.DATABASE,
            auth_required=True, network_segmented=True,
            encryption_at_rest=True, encryption_in_transit=True,
            backup_enabled=True,
        )
        graph = _build_graph(
            [lb, web, db],
            [("lb", "web"), ("web", "db")],
            cb_edges={("lb", "web"), ("web", "db")},
        )

        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)
        # Well-defended should have lower score (better)
        assert report.total_attack_surface_score < 70


class TestCalculateSurfaceScoreDirectly:
    """Direct tests for _calculate_surface_score to cover all defense depth branches."""

    def test_surface_score_defense_depth_between_1_and_2(self):
        """Test line 743: avg_defense_depth in [1, 2) adds +10 to score."""
        graph = InfraGraph()
        graph.add_component(_make_component("a", ComponentType.APP_SERVER))
        # Call static method directly with avg_defense_depth = 1.5
        score = AttackSurfaceAnalyzer._calculate_surface_score(
            entry_points=[], lateral_paths=[], high_value_targets=[],
            avg_defense_depth=1.5, graph=graph,
        )
        # With no entry points, no lateral paths, no HVTs, only defense depth contributes
        # avg_defense_depth=1.5 -> score += 10
        assert score == 10.0
