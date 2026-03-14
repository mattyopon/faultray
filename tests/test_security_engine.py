"""Tests for the Security Resilience Engine."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.security_engine import (
    AttackSimulationResult,
    AttackType,
    SecurityReport,
    SecurityResilienceEngine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    port: int = 8080,
    **sec_kwargs,
) -> Component:
    """Create a component with optional security overrides."""
    sec = SecurityProfile(**sec_kwargs)
    return Component(id=cid, name=cid, type=ctype, port=port, security=sec)


def _simple_graph(
    components: list[Component],
    deps: list[tuple[str, str]] | None = None,
) -> InfraGraph:
    """Build an InfraGraph from a list of components and (source, target) edges."""
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in deps or []:
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


# ---------------------------------------------------------------------------
# 1. AttackType enumeration
# ---------------------------------------------------------------------------

class TestAttackTypeEnum:
    def test_all_attack_types_exist(self):
        expected = {
            "ddos_volumetric", "ddos_application", "credential_stuffing",
            "sql_injection", "ransomware", "supply_chain", "insider_threat",
            "zero_day", "api_abuse", "data_exfiltration",
        }
        assert {a.value for a in AttackType} == expected

    def test_attack_type_count(self):
        assert len(AttackType) == 10


# ---------------------------------------------------------------------------
# 2. Default SecurityProfile values
# ---------------------------------------------------------------------------

class TestSecurityProfileDefaults:
    def test_all_defaults_false_or_numeric(self):
        sp = SecurityProfile()
        assert sp.encryption_at_rest is False
        assert sp.encryption_in_transit is False
        assert sp.waf_protected is False
        assert sp.rate_limiting is False
        assert sp.auth_required is False
        assert sp.network_segmented is False
        assert sp.backup_enabled is False
        assert sp.backup_frequency_hours == 24.0
        assert sp.patch_sla_hours == 72.0
        assert sp.log_enabled is False
        assert sp.ids_monitored is False


# ---------------------------------------------------------------------------
# 3. WAF blocks SQL injection (high defense effectiveness)
# ---------------------------------------------------------------------------

class TestWafBlocksSQLInjection:
    def test_waf_provides_high_defense_against_sqli(self):
        comp = _make_component("web", port=443, waf_protected=True)
        g = _simple_graph([comp])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.SQL_INJECTION, "web")
        # WAF -> 90% mitigation for SQLi
        assert result.defense_effectiveness >= 0.85


# ---------------------------------------------------------------------------
# 4. No WAF allows SQL injection (low defense effectiveness)
# ---------------------------------------------------------------------------

class TestNoWafAllowsSQLInjection:
    def test_no_waf_zero_defense_against_sqli(self):
        comp = _make_component("web", port=443)
        g = _simple_graph([comp])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.SQL_INJECTION, "web")
        assert result.defense_effectiveness < 0.1


# ---------------------------------------------------------------------------
# 5. Network segmentation reduces blast radius
# ---------------------------------------------------------------------------

class TestNetworkSegmentationReducesBlastRadius:
    def test_segmented_neighbours_not_compromised(self):
        web = _make_component("web", port=443)
        db = _make_component("db", ctype=ComponentType.DATABASE, network_segmented=True)
        g = _simple_graph([web, db], deps=[("web", "db")])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.SUPPLY_CHAIN, "web")
        # db is segmented -> should NOT be in compromised list
        assert "db" not in result.compromised_components

    def test_unsegmented_neighbours_compromised(self):
        web = _make_component("web", port=443)
        db = _make_component("db", ctype=ComponentType.DATABASE)
        g = _simple_graph([web, db], deps=[("web", "db")])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.SUPPLY_CHAIN, "web")
        assert "db" in result.compromised_components


# ---------------------------------------------------------------------------
# 6. Encryption reduces data exfiltration impact
# ---------------------------------------------------------------------------

class TestEncryptionReducesExfiltration:
    def test_encryption_at_rest_high_defense(self):
        db = _make_component("db", ctype=ComponentType.DATABASE, encryption_at_rest=True)
        g = _simple_graph([db])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.DATA_EXFILTRATION, "db")
        assert result.defense_effectiveness >= 0.9

    def test_encryption_in_transit_defense(self):
        db = _make_component("db", ctype=ComponentType.DATABASE, encryption_in_transit=True)
        g = _simple_graph([db])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.DATA_EXFILTRATION, "db")
        assert result.defense_effectiveness >= 0.6

    def test_both_encryptions_combined(self):
        db = _make_component(
            "db", ctype=ComponentType.DATABASE,
            encryption_at_rest=True, encryption_in_transit=True,
        )
        g = _simple_graph([db])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.DATA_EXFILTRATION, "db")
        # Combined: 1 - (1-0.95)*(1-0.70) = 1 - 0.05*0.30 = 0.985
        assert result.defense_effectiveness >= 0.98


# ---------------------------------------------------------------------------
# 7. Rate limiting mitigates DDoS
# ---------------------------------------------------------------------------

class TestRateLimitingMitigatesDDoS:
    def test_rate_limiting_ddos_volumetric(self):
        lb = _make_component("lb", ctype=ComponentType.LOAD_BALANCER, port=443, rate_limiting=True)
        g = _simple_graph([lb])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.DDOS_VOLUMETRIC, "lb")
        assert result.defense_effectiveness >= 0.55

    def test_no_rate_limiting_ddos(self):
        lb = _make_component("lb", ctype=ComponentType.LOAD_BALANCER, port=443)
        g = _simple_graph([lb])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.DDOS_VOLUMETRIC, "lb")
        assert result.defense_effectiveness < 0.1


# ---------------------------------------------------------------------------
# 8. Full security = high score, no security = low score
# ---------------------------------------------------------------------------

class TestSecurityScore:
    def test_full_security_high_score(self):
        comp = _make_component(
            "app", port=443,
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=True, rate_limiting=True, auth_required=True,
            network_segmented=True, backup_enabled=True,
            backup_frequency_hours=1.0, patch_sla_hours=24.0,
            log_enabled=True, ids_monitored=True,
        )
        g = _simple_graph([comp])
        engine = SecurityResilienceEngine(g)
        score = engine.security_resilience_score()
        assert score >= 85.0, f"Expected high score, got {score}"

    def test_no_security_low_score(self):
        comp = _make_component("app", port=443)
        g = _simple_graph([comp])
        engine = SecurityResilienceEngine(g)
        score = engine.security_resilience_score()
        assert score <= 15.0, f"Expected low score, got {score}"


# ---------------------------------------------------------------------------
# 9. Blast radius calculation
# ---------------------------------------------------------------------------

class TestBlastRadius:
    def test_isolated_component_blast_radius_one(self):
        comp = _make_component("lone")
        g = _simple_graph([comp])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.RANSOMWARE, "lone")
        assert result.blast_radius == 1  # only itself

    def test_chain_blast_radius(self):
        # A -> B -> C, none segmented
        a = _make_component("a")
        b = _make_component("b")
        c = _make_component("c")
        g = _simple_graph([a, b, c], deps=[("a", "b"), ("b", "c")])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.SUPPLY_CHAIN, "a")
        assert result.blast_radius == 3


# ---------------------------------------------------------------------------
# 10. Lateral movement through dependency graph
# ---------------------------------------------------------------------------

class TestLateralMovement:
    def test_lateral_movement_follows_deps(self):
        web = _make_component("web")
        api = _make_component("api")
        db = _make_component("db", ctype=ComponentType.DATABASE)
        g = _simple_graph([web, api, db], deps=[("web", "api"), ("api", "db")])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.INSIDER_THREAT, "web")
        assert "api" in result.compromised_components
        assert "db" in result.compromised_components

    def test_segmentation_stops_lateral(self):
        web = _make_component("web")
        api = _make_component("api", network_segmented=True)
        db = _make_component("db", ctype=ComponentType.DATABASE)
        g = _simple_graph([web, api, db], deps=[("web", "api"), ("api", "db")])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.INSIDER_THREAT, "web")
        # api is segmented -> stops movement -> db also unreachable
        assert "api" not in result.compromised_components
        assert "db" not in result.compromised_components
        assert result.blast_radius == 1


# ---------------------------------------------------------------------------
# 11. Auto-generated scenarios cover all relevant attack types
# ---------------------------------------------------------------------------

class TestAutoGeneratedScenarios:
    def test_public_facing_generates_ddos_and_sqli(self):
        web = _make_component("web", port=443)
        g = _simple_graph([web])
        engine = SecurityResilienceEngine(g)
        scenarios = engine.generate_default_attack_scenarios()
        attack_types = {at for at, _ in scenarios}
        assert AttackType.DDOS_VOLUMETRIC in attack_types
        assert AttackType.DDOS_APPLICATION in attack_types
        assert AttackType.SQL_INJECTION in attack_types
        assert AttackType.API_ABUSE in attack_types

    def test_database_generates_exfiltration_and_ransomware(self):
        db = _make_component("db", ctype=ComponentType.DATABASE)
        g = _simple_graph([db])
        engine = SecurityResilienceEngine(g)
        scenarios = engine.generate_default_attack_scenarios()
        attack_types = {at for at, _ in scenarios}
        assert AttackType.DATA_EXFILTRATION in attack_types
        assert AttackType.RANSOMWARE in attack_types
        assert AttackType.SQL_INJECTION in attack_types

    def test_no_auth_generates_credential_stuffing(self):
        app = _make_component("app")
        g = _simple_graph([app])
        engine = SecurityResilienceEngine(g)
        scenarios = engine.generate_default_attack_scenarios()
        attack_types = {at for at, _ in scenarios}
        assert AttackType.CREDENTIAL_STUFFING in attack_types

    def test_no_segmentation_generates_supply_chain_insider(self):
        app = _make_component("app")
        g = _simple_graph([app])
        engine = SecurityResilienceEngine(g)
        scenarios = engine.generate_default_attack_scenarios()
        attack_types = {at for at, _ in scenarios}
        assert AttackType.SUPPLY_CHAIN in attack_types
        assert AttackType.INSIDER_THREAT in attack_types


# ---------------------------------------------------------------------------
# 12. Empty graph handling
# ---------------------------------------------------------------------------

class TestEmptyGraph:
    def test_empty_graph_score_zero(self):
        g = InfraGraph()
        engine = SecurityResilienceEngine(g)
        assert engine.security_resilience_score() == 0.0

    def test_empty_graph_simulate_all(self):
        g = InfraGraph()
        engine = SecurityResilienceEngine(g)
        report = engine.simulate_all_attacks()
        assert report.total_attacks_simulated == 0
        assert report.security_resilience_score == 0.0
        assert report.worst_case_blast_radius == 0

    def test_nonexistent_component(self):
        g = InfraGraph()
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.RANSOMWARE, "ghost")
        assert result.blast_radius == 0
        assert len(result.mitigation_recommendations) >= 1


# ---------------------------------------------------------------------------
# 13. Score breakdown contains all categories
# ---------------------------------------------------------------------------

class TestScoreBreakdown:
    def test_breakdown_has_all_categories(self):
        comp = _make_component("app")
        g = _simple_graph([comp])
        engine = SecurityResilienceEngine(g)
        report = engine.simulate_all_attacks()
        expected_keys = {"encryption", "access_control", "network", "monitoring", "recovery"}
        assert set(report.score_breakdown.keys()) == expected_keys

    def test_breakdown_values_in_range(self):
        comp = _make_component(
            "app",
            encryption_at_rest=True, encryption_in_transit=True,
            waf_protected=True, rate_limiting=True,
        )
        g = _simple_graph([comp])
        engine = SecurityResilienceEngine(g)
        report = engine.simulate_all_attacks()
        for cat, val in report.score_breakdown.items():
            assert 0.0 <= val <= 20.0, f"{cat} out of range: {val}"


# ---------------------------------------------------------------------------
# 14. Backup reduces ransomware recovery time
# ---------------------------------------------------------------------------

class TestBackupReducesRansomware:
    def test_backup_reduces_downtime(self):
        comp_no_backup = _make_component("db-no-bk", ctype=ComponentType.DATABASE)
        comp_with_backup = _make_component(
            "db-bk", ctype=ComponentType.DATABASE,
            backup_enabled=True, backup_frequency_hours=1.0,
        )

        g1 = _simple_graph([comp_no_backup])
        g2 = _simple_graph([comp_with_backup])

        e1 = SecurityResilienceEngine(g1)
        e2 = SecurityResilienceEngine(g2)

        r1 = e1.simulate_attack(AttackType.RANSOMWARE, "db-no-bk")
        r2 = e2.simulate_attack(AttackType.RANSOMWARE, "db-bk")

        assert r2.estimated_downtime_minutes < r1.estimated_downtime_minutes

    def test_frequent_backup_better_recovery(self):
        comp_hourly = _make_component(
            "db-1h", ctype=ComponentType.DATABASE,
            backup_enabled=True, backup_frequency_hours=1.0,
        )
        comp_daily = _make_component(
            "db-24h", ctype=ComponentType.DATABASE,
            backup_enabled=True, backup_frequency_hours=24.0,
        )

        g1 = _simple_graph([comp_hourly])
        g2 = _simple_graph([comp_daily])

        e1 = SecurityResilienceEngine(g1)
        e2 = SecurityResilienceEngine(g2)

        r1 = e1.simulate_attack(AttackType.RANSOMWARE, "db-1h")
        r2 = e2.simulate_attack(AttackType.RANSOMWARE, "db-24h")

        assert r1.estimated_downtime_minutes <= r2.estimated_downtime_minutes


# ---------------------------------------------------------------------------
# 15. Multiple attack types on same component
# ---------------------------------------------------------------------------

class TestMultipleAttacksOnSameComponent:
    def test_different_attacks_different_results(self):
        web = _make_component("web", port=443, waf_protected=True, rate_limiting=True)
        g = _simple_graph([web])
        engine = SecurityResilienceEngine(g)

        sqli = engine.simulate_attack(AttackType.SQL_INJECTION, "web")
        ddos = engine.simulate_attack(AttackType.DDOS_VOLUMETRIC, "web")
        ransom = engine.simulate_attack(AttackType.RANSOMWARE, "web")

        # WAF mitigates SQLi well, rate limiting mitigates DDoS, neither helps ransomware much
        assert sqli.defense_effectiveness > ransom.defense_effectiveness
        assert ddos.defense_effectiveness > ransom.defense_effectiveness

    def test_all_attacks_produce_results(self):
        web = _make_component("web", port=443)
        g = _simple_graph([web])
        engine = SecurityResilienceEngine(g)

        for attack in AttackType:
            result = engine.simulate_attack(attack, "web")
            assert isinstance(result, AttackSimulationResult)
            assert result.attack_type == attack
            assert result.blast_radius >= 1


# ---------------------------------------------------------------------------
# 16. SecurityReport structure
# ---------------------------------------------------------------------------

class TestSecurityReportStructure:
    def test_report_counts_are_consistent(self):
        web = _make_component("web", port=443)
        db = _make_component("db", ctype=ComponentType.DATABASE)
        g = _simple_graph([web, db], deps=[("web", "db")])
        engine = SecurityResilienceEngine(g)
        report = engine.simulate_all_attacks()

        assert isinstance(report, SecurityReport)
        total = (
            report.attacks_fully_mitigated
            + report.attacks_partially_mitigated
            + report.attacks_unmitigated
        )
        assert total == report.total_attacks_simulated
        assert len(report.results) == report.total_attacks_simulated
        assert 0.0 <= report.security_resilience_score <= 100.0


# ---------------------------------------------------------------------------
# 17. Data at risk flag
# ---------------------------------------------------------------------------

class TestDataAtRisk:
    def test_database_compromise_flags_data_risk(self):
        web = _make_component("web")
        db = _make_component("db", ctype=ComponentType.DATABASE)
        g = _simple_graph([web, db], deps=[("web", "db")])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.RANSOMWARE, "web")
        assert result.data_at_risk is True

    def test_no_database_no_data_risk(self):
        web = _make_component("web")
        cache = _make_component("cache", ctype=ComponentType.CACHE)
        g = _simple_graph([web, cache], deps=[("web", "cache")])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.RANSOMWARE, "web")
        assert result.data_at_risk is False


# ---------------------------------------------------------------------------
# 18. IDS monitoring and zero-day detection
# ---------------------------------------------------------------------------

class TestIDSMonitoring:
    def test_ids_provides_zero_day_defense(self):
        app = _make_component("app", ids_monitored=True)
        g = _simple_graph([app])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.ZERO_DAY, "app")
        assert result.defense_effectiveness >= 0.25

    def test_no_ids_no_zero_day_defense(self):
        app = _make_component("app")
        g = _simple_graph([app])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.ZERO_DAY, "app")
        assert result.defense_effectiveness < 0.1


# ---------------------------------------------------------------------------
# 19. Recommendations are generated
# ---------------------------------------------------------------------------

class TestRecommendations:
    def test_missing_waf_recommends_waf(self):
        web = _make_component("web", port=443)
        g = _simple_graph([web])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.SQL_INJECTION, "web")
        assert any("WAF" in r for r in result.mitigation_recommendations)

    def test_full_security_fewer_recommendations(self):
        web = _make_component(
            "web", port=443,
            waf_protected=True, rate_limiting=True, auth_required=True,
            encryption_at_rest=True, encryption_in_transit=True,
            network_segmented=True, ids_monitored=True, backup_enabled=True,
        )
        g = _simple_graph([web])
        engine = SecurityResilienceEngine(g)
        result = engine.simulate_attack(AttackType.SQL_INJECTION, "web")
        # Should have very few or no recommendations
        assert len(result.mitigation_recommendations) <= 1


# ---------------------------------------------------------------------------
# 20. SecurityProfile field on Component model
# ---------------------------------------------------------------------------

class TestSecurityProfileOnComponent:
    def test_component_has_default_security(self):
        comp = Component(id="x", name="x", type=ComponentType.APP_SERVER)
        assert isinstance(comp.security, SecurityProfile)
        assert comp.security.encryption_at_rest is False

    def test_component_with_custom_security(self):
        sec = SecurityProfile(
            encryption_at_rest=True,
            waf_protected=True,
            backup_enabled=True,
        )
        comp = Component(id="x", name="x", type=ComponentType.APP_SERVER, security=sec)
        assert comp.security.encryption_at_rest is True
        assert comp.security.waf_protected is True
        assert comp.security.backup_enabled is True
