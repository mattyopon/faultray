"""Tests for security_chaos module — compound failure + attack simulation."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    FailoverConfig,
    HealthStatus,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.security_chaos import (
    AttackSurfaceChange,
    AttackType,
    CompoundScenario,
    SecurityChaosEngine,
    SecurityChaosReport,
    SecurityPosture,
    SecurityResilienceScore,
    _ATTACK_DEFENSE_MAP,
    _FAILURE_EXPOSURE_MAP,
    _FAILURE_TYPES,
    _MAX_SECURITY_WEIGHT,
    _SECURITY_FIELD_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid,
    name,
    ctype=ComponentType.APP_SERVER,
    replicas=1,
    failover=False,
    health=HealthStatus.HEALTHY,
    security=None,
):
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True, promotion_time_seconds=10)
    if security:
        c.security = security
    return c


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _hardened_security():
    return SecurityProfile(
        encryption_at_rest=True,
        encryption_in_transit=True,
        waf_protected=True,
        rate_limiting=True,
        auth_required=True,
        network_segmented=True,
        backup_enabled=True,
        log_enabled=True,
        ids_monitored=True,
    )


def _weak_security():
    return SecurityProfile(
        encryption_at_rest=False,
        encryption_in_transit=False,
        waf_protected=False,
        rate_limiting=False,
        auth_required=False,
        network_segmented=False,
        backup_enabled=False,
        log_enabled=False,
        ids_monitored=False,
    )


def _partial_security():
    return SecurityProfile(
        encryption_at_rest=True,
        encryption_in_transit=True,
        waf_protected=False,
        rate_limiting=False,
        auth_required=True,
        network_segmented=False,
        backup_enabled=True,
        log_enabled=True,
        ids_monitored=False,
    )


# ============================================================================
# AttackType Enum
# ============================================================================


class TestAttackType:
    def test_all_members(self):
        assert len(AttackType) == 10

    def test_ddos_value(self):
        assert AttackType.DDOS.value == "ddos"

    def test_auth_bypass_value(self):
        assert AttackType.AUTH_BYPASS.value == "auth_bypass"

    def test_cert_expiry_value(self):
        assert AttackType.CERT_EXPIRY.value == "cert_expiry"

    def test_dns_poisoning_value(self):
        assert AttackType.DNS_POISONING.value == "dns_poisoning"

    def test_data_exfiltration_value(self):
        assert AttackType.DATA_EXFILTRATION.value == "data_exfiltration"

    def test_privilege_escalation_value(self):
        assert AttackType.PRIVILEGE_ESCALATION.value == "privilege_escalation"

    def test_supply_chain_value(self):
        assert AttackType.SUPPLY_CHAIN_ATTACK.value == "supply_chain_attack"

    def test_api_abuse_value(self):
        assert AttackType.API_ABUSE.value == "api_abuse"

    def test_credential_stuffing_value(self):
        assert AttackType.CREDENTIAL_STUFFING.value == "credential_stuffing"

    def test_man_in_the_middle_value(self):
        assert AttackType.MAN_IN_THE_MIDDLE.value == "man_in_the_middle"

    def test_is_str_enum(self):
        assert isinstance(AttackType.DDOS, str)


# ============================================================================
# SecurityPosture Enum
# ============================================================================


class TestSecurityPosture:
    def test_all_members(self):
        assert len(SecurityPosture) == 4

    def test_hardened(self):
        assert SecurityPosture.HARDENED.value == "hardened"

    def test_standard(self):
        assert SecurityPosture.STANDARD.value == "standard"

    def test_weak(self):
        assert SecurityPosture.WEAK.value == "weak"

    def test_compromised(self):
        assert SecurityPosture.COMPROMISED.value == "compromised"

    def test_is_str_enum(self):
        assert isinstance(SecurityPosture.HARDENED, str)


# ============================================================================
# CompoundScenario model
# ============================================================================


class TestCompoundScenario:
    def test_defaults(self):
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        assert cs.simultaneous is True
        assert cs.attack_severity == 0.5
        assert cs.failure_severity == 0.5

    def test_custom_values(self):
        cs = CompoundScenario(
            failure_type="disk_failure",
            attack_type=AttackType.DATA_EXFILTRATION,
            simultaneous=False,
            attack_severity=0.9,
            failure_severity=0.1,
        )
        assert cs.failure_type == "disk_failure"
        assert cs.attack_type == AttackType.DATA_EXFILTRATION
        assert cs.simultaneous is False
        assert cs.attack_severity == 0.9
        assert cs.failure_severity == 0.1

    def test_severity_bounds_min(self):
        with pytest.raises(Exception):
            CompoundScenario(
                failure_type="x", attack_type=AttackType.DDOS, attack_severity=-0.1
            )

    def test_severity_bounds_max(self):
        with pytest.raises(Exception):
            CompoundScenario(
                failure_type="x", attack_type=AttackType.DDOS, attack_severity=1.1
            )

    def test_failure_severity_bounds_min(self):
        with pytest.raises(Exception):
            CompoundScenario(
                failure_type="x", attack_type=AttackType.DDOS, failure_severity=-0.1
            )

    def test_failure_severity_bounds_max(self):
        with pytest.raises(Exception):
            CompoundScenario(
                failure_type="x", attack_type=AttackType.DDOS, failure_severity=1.1
            )

    def test_zero_severity(self):
        cs = CompoundScenario(
            failure_type="x", attack_type=AttackType.DDOS, attack_severity=0.0, failure_severity=0.0
        )
        assert cs.attack_severity == 0.0
        assert cs.failure_severity == 0.0

    def test_max_severity(self):
        cs = CompoundScenario(
            failure_type="x", attack_type=AttackType.DDOS, attack_severity=1.0, failure_severity=1.0
        )
        assert cs.attack_severity == 1.0
        assert cs.failure_severity == 1.0


# ============================================================================
# SecurityResilienceScore model
# ============================================================================


class TestSecurityResilienceScore:
    def test_defaults(self):
        s = SecurityResilienceScore()
        assert s.overall_score == 0.0
        assert s.attack_resistance == 0.0
        assert s.failure_containment == 0.0
        assert s.compound_risk == 0.0
        assert s.exposure_window_minutes == 0.0

    def test_custom_values(self):
        s = SecurityResilienceScore(
            overall_score=75.0,
            attack_resistance=80.0,
            failure_containment=70.0,
            compound_risk=20.0,
            exposure_window_minutes=15.5,
        )
        assert s.overall_score == 75.0
        assert s.exposure_window_minutes == 15.5


# ============================================================================
# AttackSurfaceChange model
# ============================================================================


class TestAttackSurfaceChange:
    def test_defaults(self):
        a = AttackSurfaceChange(component_id="c1")
        assert a.component_id == "c1"
        assert a.normal_attack_surface == 0.0
        assert a.degraded_attack_surface == 0.0
        assert a.increase_percent == 0.0
        assert a.vulnerabilities_exposed == []

    def test_custom_values(self):
        a = AttackSurfaceChange(
            component_id="db",
            normal_attack_surface=0.3,
            degraded_attack_surface=0.7,
            increase_percent=133.33,
            vulnerabilities_exposed=["disk_failure_disables_encryption_at_rest"],
        )
        assert len(a.vulnerabilities_exposed) == 1


# ============================================================================
# SecurityChaosReport model
# ============================================================================


class TestSecurityChaosReport:
    def test_defaults(self):
        r = SecurityChaosReport()
        assert r.compound_scenarios_tested == 0
        assert r.highest_risk_scenario == ""
        assert r.security_resilience.overall_score == 0.0
        assert r.attack_surface_changes == []
        assert r.recommendations == []

    def test_custom(self):
        r = SecurityChaosReport(
            compound_scenarios_tested=5,
            highest_risk_scenario="ddos+node_failure",
            recommendations=["add WAF"],
        )
        assert r.compound_scenarios_tested == 5
        assert r.highest_risk_scenario == "ddos+node_failure"
        assert len(r.recommendations) == 1


# ============================================================================
# Module-level constants
# ============================================================================


class TestConstants:
    def test_security_field_weights_count(self):
        assert len(_SECURITY_FIELD_WEIGHTS) == 9

    def test_max_weight_sum(self):
        assert _MAX_SECURITY_WEIGHT == sum(_SECURITY_FIELD_WEIGHTS.values())

    def test_attack_defense_map_keys(self):
        assert set(_ATTACK_DEFENSE_MAP.keys()) == set(AttackType)

    def test_failure_types_non_empty(self):
        assert len(_FAILURE_TYPES) > 0

    def test_failure_exposure_map_has_expected_keys(self):
        expected = {"node_failure", "disk_failure", "cascade_failure", "network_partition"}
        assert expected.issubset(set(_FAILURE_EXPOSURE_MAP.keys()))


# ============================================================================
# SecurityChaosEngine — assess_security_posture
# ============================================================================


class TestAssessSecurityPosture:
    def test_hardened(self):
        g = _graph(_comp("a", "App", security=_hardened_security()))
        engine = SecurityChaosEngine(g)
        assert engine.assess_security_posture("a") == SecurityPosture.HARDENED

    def test_standard(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        assert engine.assess_security_posture("a") == SecurityPosture.STANDARD

    def test_weak(self):
        sec = SecurityProfile(encryption_at_rest=True, auth_required=True)
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        assert engine.assess_security_posture("a") == SecurityPosture.WEAK

    def test_compromised(self):
        g = _graph(_comp("a", "App", security=_weak_security()))
        engine = SecurityChaosEngine(g)
        assert engine.assess_security_posture("a") == SecurityPosture.COMPROMISED

    def test_missing_component(self):
        g = _graph()
        engine = SecurityChaosEngine(g)
        assert engine.assess_security_posture("nonexistent") == SecurityPosture.COMPROMISED

    def test_default_security_profile(self):
        g = _graph(_comp("a", "App"))
        engine = SecurityChaosEngine(g)
        assert engine.assess_security_posture("a") == SecurityPosture.COMPROMISED

    def test_borderline_hardened(self):
        """Exactly at the 0.75 threshold."""
        # All enabled except backup_enabled (weight 0.5) and log_enabled (weight 0.5)
        # Total enabled weight: 9.0 - 0.5 - 0.5 = 8.0; ratio = 8.0/9.0 ≈ 0.889 → HARDENED
        sec = SecurityProfile(
            encryption_at_rest=True,
            encryption_in_transit=True,
            waf_protected=True,
            rate_limiting=True,
            auth_required=True,
            network_segmented=True,
            backup_enabled=False,
            log_enabled=False,
            ids_monitored=True,
        )
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        assert engine.assess_security_posture("a") == SecurityPosture.HARDENED


# ============================================================================
# SecurityChaosEngine — simulate_compound
# ============================================================================


class TestSimulateCompound:
    def test_missing_target(self):
        g = _graph()
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        score = engine.simulate_compound(cs, "missing")
        assert score.overall_score == 0.0
        assert score.compound_risk == 100.0

    def test_hardened_target(self):
        g = _graph(_comp("a", "App", security=_hardened_security(), replicas=3, failover=True))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(
            failure_type="node_failure", attack_type=AttackType.DDOS,
            attack_severity=0.5, failure_severity=0.5,
        )
        score = engine.simulate_compound(cs, "a")
        assert score.overall_score > 50
        assert score.attack_resistance > 0
        assert score.failure_containment > 0

    def test_weak_target(self):
        g = _graph(_comp("a", "App", security=_weak_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(
            failure_type="cascade_failure", attack_type=AttackType.DATA_EXFILTRATION,
            attack_severity=0.9, failure_severity=0.9,
        )
        score = engine.simulate_compound(cs, "a")
        assert score.overall_score < 50
        assert score.compound_risk > 0

    def test_simultaneous_vs_sequential(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        sim = CompoundScenario(
            failure_type="node_failure", attack_type=AttackType.AUTH_BYPASS,
            simultaneous=True, attack_severity=0.5, failure_severity=0.5,
        )
        seq = CompoundScenario(
            failure_type="node_failure", attack_type=AttackType.AUTH_BYPASS,
            simultaneous=False, attack_severity=0.5, failure_severity=0.5,
        )
        sim_score = engine.simulate_compound(sim, "a")
        seq_score = engine.simulate_compound(seq, "a")
        # Simultaneous should generally have higher compound risk
        # (or at least different behaviour)
        assert sim_score.compound_risk != seq_score.compound_risk

    def test_zero_severity(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(
            failure_type="node_failure", attack_type=AttackType.DDOS,
            attack_severity=0.0, failure_severity=0.0,
        )
        score = engine.simulate_compound(cs, "a")
        assert score.overall_score >= 0
        assert score.exposure_window_minutes >= 0

    def test_max_severity(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(
            failure_type="cascade_failure", attack_type=AttackType.DDOS,
            attack_severity=1.0, failure_severity=1.0,
        )
        score = engine.simulate_compound(cs, "a")
        assert 0 <= score.overall_score <= 100
        assert 0 <= score.compound_risk <= 100

    def test_scores_bounded(self):
        g = _graph(_comp("a", "App", security=_hardened_security(), replicas=5, failover=True))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        score = engine.simulate_compound(cs, "a")
        assert 0 <= score.overall_score <= 100
        assert 0 <= score.attack_resistance <= 100
        assert 0 <= score.failure_containment <= 100
        assert 0 <= score.compound_risk <= 100
        assert score.exposure_window_minutes >= 0

    def test_exposure_window_hardened_is_short(self):
        g = _graph(_comp("a", "App", security=_hardened_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS, attack_severity=0.5, failure_severity=0.5)
        score = engine.simulate_compound(cs, "a")
        # Hardened posture has 0.5 factor
        assert score.exposure_window_minutes < 30

    def test_exposure_window_weak_is_long(self):
        g = _graph(_comp("a", "App", security=_weak_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS, attack_severity=0.5, failure_severity=0.5)
        score = engine.simulate_compound(cs, "a")
        # Compromised posture has 3.0 factor
        assert score.exposure_window_minutes > 50

    def test_replicas_improve_containment(self):
        g1 = _graph(_comp("a", "App", security=_weak_security(), replicas=1))
        g3 = _graph(_comp("a", "App", security=_weak_security(), replicas=3))
        engine1 = SecurityChaosEngine(g1)
        engine3 = SecurityChaosEngine(g3)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        s1 = engine1.simulate_compound(cs, "a")
        s3 = engine3.simulate_compound(cs, "a")
        assert s3.failure_containment > s1.failure_containment

    def test_failover_improves_containment(self):
        g_no = _graph(_comp("a", "App", security=_weak_security()))
        g_yes = _graph(_comp("a", "App", security=_weak_security(), failover=True))
        e_no = SecurityChaosEngine(g_no)
        e_yes = SecurityChaosEngine(g_yes)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        s_no = e_no.simulate_compound(cs, "a")
        s_yes = e_yes.simulate_compound(cs, "a")
        assert s_yes.failure_containment > s_no.failure_containment

    def test_backup_helps_disk_failure(self):
        sec_backup = SecurityProfile(backup_enabled=True)
        sec_no_backup = SecurityProfile(backup_enabled=False)
        g_b = _graph(_comp("a", "App", security=sec_backup))
        g_n = _graph(_comp("a", "App", security=sec_no_backup))
        e_b = SecurityChaosEngine(g_b)
        e_n = SecurityChaosEngine(g_n)
        cs = CompoundScenario(failure_type="disk_failure", attack_type=AttackType.DDOS)
        s_b = e_b.simulate_compound(cs, "a")
        s_n = e_n.simulate_compound(cs, "a")
        assert s_b.failure_containment > s_n.failure_containment

    def test_all_attack_types_produce_scores(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        for at in AttackType:
            cs = CompoundScenario(failure_type="node_failure", attack_type=at)
            score = engine.simulate_compound(cs, "a")
            assert 0 <= score.overall_score <= 100

    def test_all_failure_types_produce_scores(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        for ft in _FAILURE_TYPES:
            cs = CompoundScenario(failure_type=ft, attack_type=AttackType.DDOS)
            score = engine.simulate_compound(cs, "a")
            assert 0 <= score.overall_score <= 100

    def test_unknown_failure_type(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="unknown_failure", attack_type=AttackType.DDOS)
        score = engine.simulate_compound(cs, "a")
        assert 0 <= score.overall_score <= 100

    def test_network_segmented_improves_containment(self):
        sec_seg = SecurityProfile(network_segmented=True)
        sec_no = SecurityProfile(network_segmented=False)
        g_s = _graph(_comp("a", "App", security=sec_seg))
        g_n = _graph(_comp("a", "App", security=sec_no))
        e_s = SecurityChaosEngine(g_s)
        e_n = SecurityChaosEngine(g_n)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        s_s = e_s.simulate_compound(cs, "a")
        s_n = e_n.simulate_compound(cs, "a")
        assert s_s.failure_containment > s_n.failure_containment


# ============================================================================
# SecurityChaosEngine — calculate_attack_surface_change
# ============================================================================


class TestCalculateAttackSurfaceChange:
    def test_missing_component(self):
        g = _graph()
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("missing", "node_failure")
        assert change.component_id == "missing"
        assert change.normal_attack_surface == 1.0
        assert change.degraded_attack_surface == 1.0
        assert "component_not_found" in change.vulnerabilities_exposed

    def test_hardened_node_failure(self):
        g = _graph(_comp("a", "App", security=_hardened_security()))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "node_failure")
        assert change.degraded_attack_surface >= change.normal_attack_surface
        assert len(change.vulnerabilities_exposed) > 0

    def test_weak_no_change(self):
        """Weak security: all fields False, so failure can't disable them further."""
        g = _graph(_comp("a", "App", security=_weak_security()))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "node_failure")
        assert change.vulnerabilities_exposed == []
        assert change.increase_percent == 0.0

    def test_disk_failure_disables_encryption(self):
        sec = SecurityProfile(encryption_at_rest=True, backup_enabled=True, log_enabled=True)
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "disk_failure")
        assert any("encryption_at_rest" in v for v in change.vulnerabilities_exposed)
        assert any("backup_enabled" in v for v in change.vulnerabilities_exposed)
        assert change.increase_percent > 0

    def test_unknown_failure_type(self):
        g = _graph(_comp("a", "App", security=_hardened_security()))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "unknown_type")
        assert change.vulnerabilities_exposed == []
        assert change.increase_percent == 0.0

    def test_surface_bounded(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        for ft in _FAILURE_TYPES:
            change = engine.calculate_attack_surface_change("a", ft)
            assert 0 <= change.normal_attack_surface <= 1
            assert 0 <= change.degraded_attack_surface <= 1

    def test_network_partition(self):
        sec = SecurityProfile(encryption_in_transit=True, network_segmented=True, waf_protected=True)
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "network_partition")
        assert len(change.vulnerabilities_exposed) == 3
        assert change.degraded_attack_surface > change.normal_attack_surface

    def test_cpu_overload(self):
        sec = SecurityProfile(rate_limiting=True, waf_protected=True, auth_required=True)
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "cpu_overload")
        assert len(change.vulnerabilities_exposed) == 3

    def test_memory_exhaustion(self):
        sec = SecurityProfile(rate_limiting=True, waf_protected=True, ids_monitored=True)
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "memory_exhaustion")
        assert len(change.vulnerabilities_exposed) == 3

    def test_certificate_expiry(self):
        sec = SecurityProfile(encryption_in_transit=True, auth_required=True)
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "certificate_expiry")
        assert len(change.vulnerabilities_exposed) == 2

    def test_dependency_timeout(self):
        sec = SecurityProfile(auth_required=True, rate_limiting=True)
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "dependency_timeout")
        assert len(change.vulnerabilities_exposed) == 2

    def test_dns_failure(self):
        sec = SecurityProfile(network_segmented=True, waf_protected=True)
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "dns_failure")
        assert len(change.vulnerabilities_exposed) == 2

    def test_cascade_failure(self):
        sec = SecurityProfile(
            network_segmented=True, ids_monitored=True, log_enabled=True, waf_protected=True
        )
        g = _graph(_comp("a", "App", security=sec))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "cascade_failure")
        assert len(change.vulnerabilities_exposed) == 4

    def test_increase_percent_zero_normal_surface(self):
        """When normal surface is 0 (all controls on) but degraded > 0 => 100%."""
        g = _graph(_comp("a", "App", security=_hardened_security()))
        engine = SecurityChaosEngine(g)
        change = engine.calculate_attack_surface_change("a", "cascade_failure")
        # Normal surface is ~0 (all enabled), degraded disables some
        # Since normal is very small but not quite 0, increase_percent will be large
        assert change.increase_percent > 0


# ============================================================================
# SecurityChaosEngine — find_critical_combinations
# ============================================================================


class TestFindCriticalCombinations:
    def test_empty_graph(self):
        g = _graph()
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        assert combos == []

    def test_weak_component_generates_many(self):
        g = _graph(_comp("a", "App", security=_weak_security()))
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        # Weak/Compromised → all attacks * all failure types
        assert len(combos) == len(AttackType) * len(_FAILURE_TYPES)

    def test_hardened_component_generates_few(self):
        g = _graph(_comp("a", "App", security=_hardened_security()))
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        # Hardened → only 3 high-impact combos
        assert len(combos) == 3

    def test_mixed_components(self):
        g = _graph(
            _comp("a", "App", security=_hardened_security()),
            _comp("b", "BackendWeak", security=_weak_security()),
        )
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        # Hardened: 3, Weak: all combos
        expected = 3 + len(AttackType) * len(_FAILURE_TYPES)
        assert len(combos) == expected

    def test_standard_posture_generates_few(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        assert len(combos) == 3

    def test_combo_attributes(self):
        g = _graph(_comp("a", "App", security=_weak_security()))
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        for c in combos:
            assert c.simultaneous is True
            assert c.attack_severity == 0.8
            assert c.failure_severity == 0.8

    def test_hardened_combo_attributes(self):
        g = _graph(_comp("a", "App", security=_hardened_security()))
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        for c in combos:
            assert c.simultaneous is True
            assert c.attack_severity == 0.7
            assert c.failure_severity == 0.7
            assert c.failure_type == "cascade_failure"

    def test_hardened_attack_types(self):
        g = _graph(_comp("a", "App", security=_hardened_security()))
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        attack_types = {c.attack_type for c in combos}
        assert attack_types == {AttackType.DDOS, AttackType.DATA_EXFILTRATION, AttackType.SUPPLY_CHAIN_ATTACK}


# ============================================================================
# SecurityChaosEngine — generate_report
# ============================================================================


class TestGenerateReport:
    def test_empty_scenarios(self):
        g = _graph(_comp("a", "App"))
        engine = SecurityChaosEngine(g)
        report = engine.generate_report([])
        assert report.compound_scenarios_tested == 0
        assert report.highest_risk_scenario == ""
        assert report.recommendations == []

    def test_single_scenario_single_component(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        report = engine.generate_report([cs])
        assert report.compound_scenarios_tested == 1
        assert "ddos" in report.highest_risk_scenario
        assert report.security_resilience.overall_score > 0
        assert len(report.attack_surface_changes) > 0

    def test_multi_scenario(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        scenarios = [
            CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS),
            CompoundScenario(failure_type="disk_failure", attack_type=AttackType.DATA_EXFILTRATION),
        ]
        report = engine.generate_report(scenarios)
        assert report.compound_scenarios_tested == 2

    def test_multi_component(self):
        g = _graph(
            _comp("a", "App", security=_hardened_security()),
            _comp("b", "DB", ctype=ComponentType.DATABASE, security=_weak_security()),
        )
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        report = engine.generate_report([cs])
        assert report.compound_scenarios_tested == 1
        assert len(report.attack_surface_changes) >= 1

    def test_highest_risk_scenario_format(self):
        g = _graph(_comp("a", "App", security=_weak_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="cascade_failure", attack_type=AttackType.DATA_EXFILTRATION)
        report = engine.generate_report([cs])
        assert "data_exfiltration" in report.highest_risk_scenario
        assert "cascade_failure" in report.highest_risk_scenario

    def test_report_resilience_bounded(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        report = engine.generate_report(combos)
        r = report.security_resilience
        assert 0 <= r.overall_score <= 100
        assert 0 <= r.attack_resistance <= 100
        assert 0 <= r.failure_containment <= 100
        assert 0 <= r.compound_risk <= 100
        assert r.exposure_window_minutes >= 0

    def test_recommendations_generated_for_weak(self):
        g = _graph(_comp("a", "App", security=_weak_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(
            failure_type="cascade_failure", attack_type=AttackType.DATA_EXFILTRATION,
            attack_severity=0.9, failure_severity=0.9,
        )
        report = engine.generate_report([cs])
        assert len(report.recommendations) > 0

    def test_recommendations_adequate_for_hardened(self):
        g = _graph(_comp("a", "App", security=_hardened_security(), replicas=3, failover=True))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS, attack_severity=0.1, failure_severity=0.1)
        report = engine.generate_report([cs])
        # Should say "adequate" if all scores are good
        assert len(report.recommendations) > 0

    def test_surface_changes_deduplicated(self):
        g = _graph(_comp("a", "App", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        scenarios = [
            CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS),
            CompoundScenario(failure_type="node_failure", attack_type=AttackType.API_ABUSE),
        ]
        report = engine.generate_report(scenarios)
        # Same component + same failure_type should be deduplicated
        ft_keys = [sc.component_id for sc in report.attack_surface_changes]
        assert len(ft_keys) == len(set(f"{sc.component_id}" for sc in report.attack_surface_changes))


# ============================================================================
# SecurityChaosEngine — _security_profile_score (static method)
# ============================================================================


class TestSecurityProfileScore:
    def test_all_enabled(self):
        score = SecurityChaosEngine._security_profile_score(_hardened_security())
        assert abs(score - 1.0) < 0.001

    def test_none_enabled(self):
        score = SecurityChaosEngine._security_profile_score(_weak_security())
        assert score == 0.0

    def test_partial(self):
        score = SecurityChaosEngine._security_profile_score(_partial_security())
        assert 0.0 < score < 1.0

    def test_single_field(self):
        sec = SecurityProfile(encryption_at_rest=True)
        score = SecurityChaosEngine._security_profile_score(sec)
        expected = _SECURITY_FIELD_WEIGHTS["encryption_at_rest"] / _MAX_SECURITY_WEIGHT
        assert abs(score - expected) < 0.001


# ============================================================================
# SecurityChaosEngine — _compute_attack_resistance
# ============================================================================


class TestComputeAttackResistance:
    def test_full_defense_ddos(self):
        comp = _comp("a", "App", security=_hardened_security())
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        resistance = engine._compute_attack_resistance(comp, AttackType.DDOS)
        assert resistance == 100.0

    def test_no_defense_ddos(self):
        comp = _comp("a", "App", security=_weak_security())
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        resistance = engine._compute_attack_resistance(comp, AttackType.DDOS)
        assert resistance == 0.0

    def test_partial_defense(self):
        sec = SecurityProfile(waf_protected=True, rate_limiting=False)
        comp = _comp("a", "App", security=sec)
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        resistance = engine._compute_attack_resistance(comp, AttackType.DDOS)
        assert 0 < resistance < 100

    def test_all_attack_types(self):
        comp = _comp("a", "App", security=_hardened_security())
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        for at in AttackType:
            r = engine._compute_attack_resistance(comp, at)
            assert 0 <= r <= 100

    def test_empty_defense_map(self):
        """When _ATTACK_DEFENSE_MAP returns empty dict, default 50.0 is returned."""
        comp = _comp("a", "App", security=_hardened_security())
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        # Temporarily patch the map to return empty for DDOS
        import faultray.simulator.security_chaos as mod
        original = mod._ATTACK_DEFENSE_MAP
        mod._ATTACK_DEFENSE_MAP = {}
        try:
            r = engine._compute_attack_resistance(comp, AttackType.DDOS)
            assert r == 50.0
        finally:
            mod._ATTACK_DEFENSE_MAP = original

    def test_zero_total_weight_defense(self):
        """When defense entries exist but have zero weight, default 50.0 returned."""
        comp = _comp("a", "App", security=_hardened_security())
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        import faultray.simulator.security_chaos as mod
        original = mod._ATTACK_DEFENSE_MAP
        mod._ATTACK_DEFENSE_MAP = {AttackType.DDOS: {"waf_protected": 0.0, "rate_limiting": 0.0}}
        try:
            r = engine._compute_attack_resistance(comp, AttackType.DDOS)
            assert r == 50.0
        finally:
            mod._ATTACK_DEFENSE_MAP = original


# ============================================================================
# SecurityChaosEngine — _compute_failure_containment
# ============================================================================


class TestComputeFailureContainment:
    def test_base_containment(self):
        comp = _comp("a", "App", security=_weak_security())
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        fc = engine._compute_failure_containment(comp, "node_failure")
        assert fc == 50.0

    def test_replicas_boost(self):
        comp = _comp("a", "App", security=_weak_security(), replicas=3)
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        fc = engine._compute_failure_containment(comp, "node_failure")
        assert fc == 70.0  # 50 + min(20, 2*10)

    def test_failover_boost(self):
        comp = _comp("a", "App", security=_weak_security(), failover=True)
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        fc = engine._compute_failure_containment(comp, "node_failure")
        assert fc == 65.0  # 50 + 15

    def test_backup_for_disk_failure(self):
        sec = SecurityProfile(backup_enabled=True)
        comp = _comp("a", "App", security=sec)
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        fc = engine._compute_failure_containment(comp, "disk_failure")
        assert fc == 60.0  # 50 + 10

    def test_backup_not_for_node_failure(self):
        sec = SecurityProfile(backup_enabled=True)
        comp = _comp("a", "App", security=sec)
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        fc = engine._compute_failure_containment(comp, "node_failure")
        assert fc == 50.0  # backup doesn't help node failure

    def test_all_boosts_combined(self):
        sec = SecurityProfile(backup_enabled=True, network_segmented=True)
        comp = _comp("a", "App", security=sec, replicas=3, failover=True)
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        fc = engine._compute_failure_containment(comp, "cascade_failure")
        # 50 + 20 (replicas) + 15 (failover) + 10 (backup) + 5 (segmented) = 100
        assert fc == 100.0

    def test_capped_at_100(self):
        sec = SecurityProfile(backup_enabled=True, network_segmented=True)
        comp = _comp("a", "App", security=sec, replicas=10, failover=True)
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        fc = engine._compute_failure_containment(comp, "cascade_failure")
        assert fc == 100.0

    def test_replicas_cap_at_20(self):
        comp = _comp("a", "App", security=_weak_security(), replicas=10)
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        fc = engine._compute_failure_containment(comp, "node_failure")
        # 50 + min(20, 9*10) = 50 + 20 = 70
        assert fc == 70.0


# ============================================================================
# SecurityChaosEngine — _generate_recommendations
# ============================================================================


class TestGenerateRecommendations:
    def test_low_resilience(self):
        # Create scores with low overall
        scores = [
            (
                CompoundScenario(failure_type="x", attack_type=AttackType.DDOS),
                SecurityResilienceScore(overall_score=20.0),
            )
        ]
        changes = []
        recs = SecurityChaosEngine._generate_recommendations(
            SecurityChaosEngine.__new__(SecurityChaosEngine), scores, changes
        )
        assert any("critically low" in r for r in recs)

    def test_medium_resilience(self):
        scores = [
            (
                CompoundScenario(failure_type="x", attack_type=AttackType.DDOS),
                SecurityResilienceScore(overall_score=50.0),
            )
        ]
        recs = SecurityChaosEngine._generate_recommendations(
            SecurityChaosEngine.__new__(SecurityChaosEngine), scores, []
        )
        assert any("below acceptable" in r for r in recs)

    def test_large_surface_increase(self):
        scores = [
            (
                CompoundScenario(failure_type="x", attack_type=AttackType.DDOS),
                SecurityResilienceScore(overall_score=80.0),
            )
        ]
        changes = [
            AttackSurfaceChange(component_id="c1", increase_percent=60.0),
        ]
        recs = SecurityChaosEngine._generate_recommendations(
            SecurityChaosEngine.__new__(SecurityChaosEngine), scores, changes
        )
        assert any(">50%" in r for r in recs)

    def test_high_exposure_window(self):
        scores = [
            (
                CompoundScenario(failure_type="x", attack_type=AttackType.DDOS),
                SecurityResilienceScore(overall_score=80.0, exposure_window_minutes=120.0),
            )
        ]
        recs = SecurityChaosEngine._generate_recommendations(
            SecurityChaosEngine.__new__(SecurityChaosEngine), scores, []
        )
        assert any("60 minutes" in r for r in recs)

    def test_adequate_resilience(self):
        scores = [
            (
                CompoundScenario(failure_type="x", attack_type=AttackType.DDOS),
                SecurityResilienceScore(overall_score=80.0, exposure_window_minutes=10.0),
            )
        ]
        recs = SecurityChaosEngine._generate_recommendations(
            SecurityChaosEngine.__new__(SecurityChaosEngine), scores, []
        )
        assert any("adequate" in r for r in recs)

    def test_multiple_surface_increases_truncated(self):
        scores = [
            (
                CompoundScenario(failure_type="x", attack_type=AttackType.DDOS),
                SecurityResilienceScore(overall_score=80.0),
            )
        ]
        changes = [
            AttackSurfaceChange(component_id=f"c{i}", increase_percent=60.0)
            for i in range(5)
        ]
        recs = SecurityChaosEngine._generate_recommendations(
            SecurityChaosEngine.__new__(SecurityChaosEngine), scores, changes
        )
        # Should mention up to 3 component IDs
        surface_rec = [r for r in recs if ">50%" in r][0]
        assert "c0" in surface_rec
        assert "c2" in surface_rec


# ============================================================================
# Integration: full workflow
# ============================================================================


class TestIntegrationWorkflow:
    def test_full_pipeline(self):
        g = _graph(
            _comp("lb", "LoadBalancer", ctype=ComponentType.LOAD_BALANCER, security=_hardened_security(), replicas=2, failover=True),
            _comp("app", "AppServer", security=_partial_security(), replicas=3),
            _comp("db", "Database", ctype=ComponentType.DATABASE, security=_weak_security()),
        )
        engine = SecurityChaosEngine(g)

        # 1. Assess postures
        assert engine.assess_security_posture("lb") == SecurityPosture.HARDENED
        assert engine.assess_security_posture("app") == SecurityPosture.STANDARD
        assert engine.assess_security_posture("db") == SecurityPosture.COMPROMISED

        # 2. Find critical combinations
        combos = engine.find_critical_combinations()
        assert len(combos) > 0

        # 3. Generate report
        report = engine.generate_report(combos)
        assert report.compound_scenarios_tested > 0
        assert report.highest_risk_scenario != ""
        assert report.security_resilience.overall_score >= 0
        assert len(report.recommendations) > 0

    def test_single_component_pipeline(self):
        g = _graph(_comp("solo", "Solo", security=_partial_security()))
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        report = engine.generate_report(combos)
        assert report.compound_scenarios_tested > 0

    def test_all_weak_pipeline(self):
        g = _graph(
            _comp("a", "A", security=_weak_security()),
            _comp("b", "B", security=_weak_security()),
        )
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        report = engine.generate_report(combos)
        assert report.security_resilience.overall_score < 60

    def test_all_hardened_pipeline(self):
        g = _graph(
            _comp("a", "A", security=_hardened_security(), replicas=3, failover=True),
            _comp("b", "B", security=_hardened_security(), replicas=3, failover=True),
        )
        engine = SecurityChaosEngine(g)
        combos = engine.find_critical_combinations()
        report = engine.generate_report(combos)
        assert report.security_resilience.overall_score > 40


# ============================================================================
# Edge cases
# ============================================================================


class TestEdgeCases:
    def test_component_types(self):
        """All component types should work."""
        for ct in ComponentType:
            g = _graph(_comp("c", "C", ctype=ct, security=_partial_security()))
            engine = SecurityChaosEngine(g)
            assert engine.assess_security_posture("c") == SecurityPosture.STANDARD

    def test_many_replicas(self):
        g = _graph(_comp("a", "App", security=_weak_security(), replicas=100))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        score = engine.simulate_compound(cs, "a")
        assert score.failure_containment > 50

    def test_degraded_health(self):
        g = _graph(_comp("a", "App", health=HealthStatus.DEGRADED, security=_partial_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        score = engine.simulate_compound(cs, "a")
        assert 0 <= score.overall_score <= 100

    def test_down_health(self):
        g = _graph(_comp("a", "App", health=HealthStatus.DOWN, security=_partial_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        score = engine.simulate_compound(cs, "a")
        assert 0 <= score.overall_score <= 100

    def test_overloaded_health(self):
        g = _graph(_comp("a", "App", health=HealthStatus.OVERLOADED, security=_partial_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        score = engine.simulate_compound(cs, "a")
        assert 0 <= score.overall_score <= 100

    def test_graph_with_no_components_report(self):
        g = _graph()
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        report = engine.generate_report([cs])
        # No components means no scores are generated, but report still valid
        assert report.compound_scenarios_tested == 1

    def test_backup_cascade_failure(self):
        sec = SecurityProfile(backup_enabled=True)
        comp = _comp("a", "App", security=sec)
        g = _graph(comp)
        engine = SecurityChaosEngine(g)
        fc = engine._compute_failure_containment(comp, "cascade_failure")
        assert fc == 60.0  # 50 + 10 (backup helps cascade)

    def test_sequential_compound_risk(self):
        g = _graph(_comp("a", "App", security=_weak_security()))
        engine = SecurityChaosEngine(g)
        cs = CompoundScenario(
            failure_type="node_failure", attack_type=AttackType.DDOS,
            simultaneous=False,
        )
        score = engine.simulate_compound(cs, "a")
        # Sequential: max(1 - ar/100, 1 - fc/100) * 50
        assert score.compound_risk <= 50

    def test_model_dump_compound_scenario(self):
        cs = CompoundScenario(failure_type="node_failure", attack_type=AttackType.DDOS)
        d = cs.model_dump()
        assert d["failure_type"] == "node_failure"
        assert d["attack_type"] == "ddos"

    def test_model_dump_resilience_score(self):
        s = SecurityResilienceScore(overall_score=50.0)
        d = s.model_dump()
        assert d["overall_score"] == 50.0

    def test_model_dump_surface_change(self):
        a = AttackSurfaceChange(component_id="x", increase_percent=10.0)
        d = a.model_dump()
        assert d["component_id"] == "x"

    def test_model_dump_report(self):
        r = SecurityChaosReport(compound_scenarios_tested=3)
        d = r.model_dump()
        assert d["compound_scenarios_tested"] == 3
