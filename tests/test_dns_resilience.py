"""Tests for DNS Resilience Simulator.

130+ tests covering all enums, data models, failure simulation, TTL analysis,
single point of failure detection, provider failover, blast radius estimation,
recommended configuration, and full resilience assessment.
"""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.dns_resilience import (
    BlastRadiusResult,
    DNSConfig,
    DNSFailureImpact,
    DNSFailureType,
    DNSRecordType,
    DNSResilienceEngine,
    DNSResilienceReport,
    ProviderFailoverResult,
    TTLAnalysis,
    _BASE_RESOLUTION_TIME,
    _FAILURE_BASE_IMPACT,
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
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    return Component(id=cid, name=name, type=ctype, replicas=replicas, health=health)


def _graph(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


def _engine() -> DNSResilienceEngine:
    return DNSResilienceEngine()


def _default_config(**overrides) -> DNSConfig:
    defaults = dict(
        provider="route53",
        ttl_seconds=300,
        records=["app.example.com", "api.example.com"],
        failover_provider="cloudflare",
        dnssec_enabled=True,
        health_check_enabled=True,
        multi_provider=True,
    )
    defaults.update(overrides)
    return DNSConfig(**defaults)


def _weak_config(**overrides) -> DNSConfig:
    defaults = dict(
        provider="single-provider",
        ttl_seconds=7200,
        records=["app.example.com"],
        failover_provider="",
        dnssec_enabled=False,
        health_check_enabled=False,
        multi_provider=False,
    )
    defaults.update(overrides)
    return DNSConfig(**defaults)


def _sample_graph() -> InfraGraph:
    return _graph(
        _comp("lb", "Load Balancer", ComponentType.LOAD_BALANCER),
        _comp("app1", "App Server 1", ComponentType.APP_SERVER, replicas=2),
        _comp("app2", "App Server 2", ComponentType.APP_SERVER),
        _comp("db", "Database", ComponentType.DATABASE, replicas=2),
        _comp("cache", "Cache", ComponentType.CACHE),
    )


# ===========================================================================
# 1. Enum completeness
# ===========================================================================


class TestDNSFailureTypeEnum:
    def test_all_failure_types_exist(self):
        expected = {
            "resolution_failure",
            "propagation_delay",
            "ttl_expiry",
            "cache_poisoning",
            "provider_outage",
            "zone_transfer_failure",
            "dnssec_validation_failure",
            "recursive_resolver_failure",
            "authoritative_server_failure",
            "ddos_amplification",
        }
        assert {ft.value for ft in DNSFailureType} == expected

    @pytest.mark.parametrize("ft", list(DNSFailureType))
    def test_failure_type_is_str_enum(self, ft: DNSFailureType):
        assert isinstance(ft.value, str)

    def test_failure_type_count(self):
        assert len(DNSFailureType) == 10


class TestDNSRecordTypeEnum:
    def test_all_record_types_exist(self):
        expected = {"a", "aaaa", "cname", "mx", "txt", "srv", "ns", "soa"}
        assert {rt.value for rt in DNSRecordType} == expected

    @pytest.mark.parametrize("rt", list(DNSRecordType))
    def test_record_type_is_str_enum(self, rt: DNSRecordType):
        assert isinstance(rt.value, str)

    def test_record_type_count(self):
        assert len(DNSRecordType) == 8


# ===========================================================================
# 2. Pydantic model validation
# ===========================================================================


class TestDNSConfig:
    def test_defaults(self):
        cfg = DNSConfig()
        assert cfg.provider == "default"
        assert cfg.ttl_seconds == 300
        assert cfg.records == []
        assert cfg.failover_provider == ""
        assert cfg.dnssec_enabled is False
        assert cfg.health_check_enabled is False
        assert cfg.multi_provider is False

    def test_custom_values(self):
        cfg = DNSConfig(
            provider="route53",
            ttl_seconds=60,
            records=["a.example.com"],
            failover_provider="cloudflare",
            dnssec_enabled=True,
            health_check_enabled=True,
            multi_provider=True,
        )
        assert cfg.provider == "route53"
        assert cfg.ttl_seconds == 60
        assert cfg.multi_provider is True

    def test_ttl_min_validation(self):
        with pytest.raises(Exception):
            DNSConfig(ttl_seconds=0)


class TestDNSFailureImpact:
    def test_defaults(self):
        imp = DNSFailureImpact(failure_type=DNSFailureType.RESOLUTION_FAILURE)
        assert imp.affected_services == []
        assert imp.resolution_time_seconds == 0.0
        assert imp.cache_protection_seconds == 0.0
        assert imp.user_impact_percent == 0.0
        assert imp.recommendations == []

    def test_user_impact_bounds(self):
        with pytest.raises(Exception):
            DNSFailureImpact(
                failure_type=DNSFailureType.RESOLUTION_FAILURE,
                user_impact_percent=101.0,
            )
        with pytest.raises(Exception):
            DNSFailureImpact(
                failure_type=DNSFailureType.RESOLUTION_FAILURE,
                user_impact_percent=-1.0,
            )


class TestDNSResilienceReport:
    def test_defaults(self):
        r = DNSResilienceReport()
        assert r.overall_score == 0.0
        assert r.single_points_of_failure == []
        assert r.failure_impacts == []
        assert r.recommendations == []
        assert r.timestamp == ""


class TestTTLAnalysis:
    def test_defaults(self):
        t = TTLAnalysis()
        assert t.current_ttl == 0
        assert t.recommended_ttl == 300
        assert t.ttl_risk_level == "low"
        assert t.cache_effectiveness == 0.0
        assert t.propagation_delay_seconds == 0.0
        assert t.recommendations == []


class TestProviderFailoverResult:
    def test_defaults(self):
        r = ProviderFailoverResult()
        assert r.primary_provider == ""
        assert r.failover_provider == ""
        assert r.failover_time_seconds == 0.0
        assert r.records_affected == 0
        assert r.data_loss_possible is False
        assert r.seamless is False
        assert r.recommendations == []


class TestBlastRadiusResult:
    def test_defaults(self):
        r = BlastRadiusResult()
        assert r.total_services == 0
        assert r.affected_services == []
        assert r.affected_percent == 0.0
        assert r.critical_services_affected == []
        assert r.estimated_downtime_seconds == 0.0
        assert r.recommendations == []


# ===========================================================================
# 3. _clamp utility
# ===========================================================================


class TestClamp:
    def test_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_below_min(self):
        assert _clamp(-10.0) == 0.0

    def test_above_max(self):
        assert _clamp(150.0) == 100.0

    def test_at_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0

    def test_custom_range(self):
        assert _clamp(5.0, 10.0, 20.0) == 10.0
        assert _clamp(25.0, 10.0, 20.0) == 20.0
        assert _clamp(15.0, 10.0, 20.0) == 15.0


# ===========================================================================
# 4. Constants
# ===========================================================================


class TestConstants:
    @pytest.mark.parametrize("ft", list(DNSFailureType))
    def test_all_failure_types_have_base_impact(self, ft: DNSFailureType):
        assert ft in _FAILURE_BASE_IMPACT

    @pytest.mark.parametrize("ft", list(DNSFailureType))
    def test_all_failure_types_have_base_resolution_time(self, ft: DNSFailureType):
        assert ft in _BASE_RESOLUTION_TIME

    @pytest.mark.parametrize("ft", list(DNSFailureType))
    def test_base_impact_is_positive(self, ft: DNSFailureType):
        assert _FAILURE_BASE_IMPACT[ft] > 0

    @pytest.mark.parametrize("ft", list(DNSFailureType))
    def test_base_resolution_time_is_positive(self, ft: DNSFailureType):
        assert _BASE_RESOLUTION_TIME[ft] > 0


# ===========================================================================
# 5. simulate_dns_failure — per failure type
# ===========================================================================


class TestSimulateResolutionFailure:
    def test_basic(self):
        eng = _engine()
        g = _sample_graph()
        cfg = _weak_config()
        impact = eng.simulate_dns_failure(g, DNSFailureType.RESOLUTION_FAILURE, cfg)
        assert impact.failure_type == DNSFailureType.RESOLUTION_FAILURE
        assert impact.user_impact_percent > 0
        assert impact.resolution_time_seconds > 0
        assert len(impact.recommendations) >= 1

    def test_multi_provider_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        weak = eng.simulate_dns_failure(
            g, DNSFailureType.RESOLUTION_FAILURE, _weak_config()
        )
        strong = eng.simulate_dns_failure(
            g, DNSFailureType.RESOLUTION_FAILURE, _default_config()
        )
        assert strong.user_impact_percent < weak.user_impact_percent

    def test_health_check_reduces_resolution_time(self):
        eng = _engine()
        g = _sample_graph()
        no_hc = eng.simulate_dns_failure(
            g, DNSFailureType.RESOLUTION_FAILURE,
            _weak_config(),
        )
        with_hc = eng.simulate_dns_failure(
            g, DNSFailureType.RESOLUTION_FAILURE,
            _weak_config(health_check_enabled=True),
        )
        assert with_hc.resolution_time_seconds < no_hc.resolution_time_seconds


class TestSimulatePropagationDelay:
    def test_basic(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.PROPAGATION_DELAY, _default_config()
        )
        assert impact.failure_type == DNSFailureType.PROPAGATION_DELAY
        assert len(impact.recommendations) >= 1

    def test_low_ttl_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        high_ttl = eng.simulate_dns_failure(
            g, DNSFailureType.PROPAGATION_DELAY,
            _weak_config(ttl_seconds=3600),
        )
        low_ttl = eng.simulate_dns_failure(
            g, DNSFailureType.PROPAGATION_DELAY,
            _default_config(ttl_seconds=30),
        )
        assert low_ttl.user_impact_percent < high_ttl.user_impact_percent

    def test_medium_ttl(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.PROPAGATION_DELAY,
            _default_config(ttl_seconds=120),
        )
        assert impact.user_impact_percent > 0


class TestSimulateTTLExpiry:
    def test_cache_protection_is_zero(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.TTL_EXPIRY, _default_config()
        )
        assert impact.cache_protection_seconds == 0.0

    def test_health_check_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        no_hc = eng.simulate_dns_failure(
            g, DNSFailureType.TTL_EXPIRY,
            _weak_config(),
        )
        with_hc = eng.simulate_dns_failure(
            g, DNSFailureType.TTL_EXPIRY,
            _weak_config(health_check_enabled=True),
        )
        assert with_hc.user_impact_percent < no_hc.user_impact_percent


class TestSimulateCachePoisoning:
    def test_dnssec_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        no_dnssec = eng.simulate_dns_failure(
            g, DNSFailureType.CACHE_POISONING,
            _weak_config(),
        )
        with_dnssec = eng.simulate_dns_failure(
            g, DNSFailureType.CACHE_POISONING,
            _default_config(),
        )
        assert with_dnssec.user_impact_percent < no_dnssec.user_impact_percent

    def test_no_dnssec_recommends_enabling(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.CACHE_POISONING,
            _weak_config(),
        )
        joined = " ".join(impact.recommendations).lower()
        assert "dnssec" in joined


class TestSimulateProviderOutage:
    def test_multi_provider_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        single = eng.simulate_dns_failure(
            g, DNSFailureType.PROVIDER_OUTAGE,
            _weak_config(),
        )
        multi = eng.simulate_dns_failure(
            g, DNSFailureType.PROVIDER_OUTAGE,
            _default_config(),
        )
        assert multi.user_impact_percent < single.user_impact_percent

    def test_failover_provider_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        no_fo = eng.simulate_dns_failure(
            g, DNSFailureType.PROVIDER_OUTAGE,
            _weak_config(),
        )
        with_fo = eng.simulate_dns_failure(
            g, DNSFailureType.PROVIDER_OUTAGE,
            _weak_config(failover_provider="backup-dns"),
        )
        assert with_fo.user_impact_percent < no_fo.user_impact_percent

    def test_no_failover_recommends_configuring(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.PROVIDER_OUTAGE,
            _weak_config(),
        )
        joined = " ".join(impact.recommendations).lower()
        assert "failover" in joined


class TestSimulateZoneTransferFailure:
    def test_basic(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.ZONE_TRANSFER_FAILURE, _default_config()
        )
        assert impact.failure_type == DNSFailureType.ZONE_TRANSFER_FAILURE
        assert len(impact.recommendations) >= 1

    def test_multi_provider_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        single = eng.simulate_dns_failure(
            g, DNSFailureType.ZONE_TRANSFER_FAILURE,
            _weak_config(),
        )
        multi = eng.simulate_dns_failure(
            g, DNSFailureType.ZONE_TRANSFER_FAILURE,
            _default_config(),
        )
        assert multi.user_impact_percent < single.user_impact_percent


class TestSimulateDNSSECValidationFailure:
    def test_no_dnssec_low_impact(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.DNSSEC_VALIDATION_FAILURE,
            _weak_config(),
        )
        # No DNSSEC means validation failure has very low impact
        assert impact.user_impact_percent < 20.0

    def test_with_dnssec_higher_impact(self):
        eng = _engine()
        g = _sample_graph()
        no_sec = eng.simulate_dns_failure(
            g, DNSFailureType.DNSSEC_VALIDATION_FAILURE,
            _weak_config(),
        )
        with_sec = eng.simulate_dns_failure(
            g, DNSFailureType.DNSSEC_VALIDATION_FAILURE,
            _default_config(dnssec_enabled=True, multi_provider=False),
        )
        assert with_sec.user_impact_percent > no_sec.user_impact_percent


class TestSimulateRecursiveResolverFailure:
    def test_basic(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.RECURSIVE_RESOLVER_FAILURE, _default_config()
        )
        assert impact.failure_type == DNSFailureType.RECURSIVE_RESOLVER_FAILURE
        assert len(impact.recommendations) >= 1

    def test_multi_provider_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        single = eng.simulate_dns_failure(
            g, DNSFailureType.RECURSIVE_RESOLVER_FAILURE,
            _weak_config(),
        )
        multi = eng.simulate_dns_failure(
            g, DNSFailureType.RECURSIVE_RESOLVER_FAILURE,
            _default_config(),
        )
        assert multi.user_impact_percent < single.user_impact_percent


class TestSimulateAuthoritativeServerFailure:
    def test_basic(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.AUTHORITATIVE_SERVER_FAILURE, _default_config()
        )
        assert len(impact.recommendations) >= 1

    def test_multi_provider_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        single = eng.simulate_dns_failure(
            g, DNSFailureType.AUTHORITATIVE_SERVER_FAILURE,
            _weak_config(),
        )
        multi = eng.simulate_dns_failure(
            g, DNSFailureType.AUTHORITATIVE_SERVER_FAILURE,
            _default_config(),
        )
        assert multi.user_impact_percent < single.user_impact_percent

    def test_failover_provider_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        no_fo = eng.simulate_dns_failure(
            g, DNSFailureType.AUTHORITATIVE_SERVER_FAILURE,
            _weak_config(),
        )
        with_fo = eng.simulate_dns_failure(
            g, DNSFailureType.AUTHORITATIVE_SERVER_FAILURE,
            _weak_config(failover_provider="backup"),
        )
        assert with_fo.user_impact_percent < no_fo.user_impact_percent


class TestSimulateDDoSAmplification:
    def test_basic(self):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.DDOS_AMPLIFICATION, _default_config()
        )
        assert len(impact.recommendations) >= 1

    def test_multi_provider_reduces_impact(self):
        eng = _engine()
        g = _sample_graph()
        single = eng.simulate_dns_failure(
            g, DNSFailureType.DDOS_AMPLIFICATION,
            _weak_config(),
        )
        multi = eng.simulate_dns_failure(
            g, DNSFailureType.DDOS_AMPLIFICATION,
            _default_config(),
        )
        assert multi.user_impact_percent < single.user_impact_percent


# ===========================================================================
# 6. simulate_dns_failure — cross-cutting concerns
# ===========================================================================


class TestSimulateFailureCrossCutting:
    @pytest.mark.parametrize("ft", list(DNSFailureType))
    def test_all_types_return_impact(self, ft: DNSFailureType):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(g, ft, _default_config())
        assert isinstance(impact, DNSFailureImpact)
        assert impact.failure_type == ft
        assert impact.user_impact_percent >= 0.0
        assert impact.user_impact_percent <= 100.0
        assert impact.resolution_time_seconds >= 0.0
        assert impact.cache_protection_seconds >= 0.0
        assert len(impact.recommendations) >= 1

    @pytest.mark.parametrize("ft", list(DNSFailureType))
    def test_all_types_with_weak_config(self, ft: DNSFailureType):
        eng = _engine()
        g = _sample_graph()
        impact = eng.simulate_dns_failure(g, ft, _weak_config())
        assert isinstance(impact, DNSFailureImpact)
        assert impact.user_impact_percent >= 0.0

    @pytest.mark.parametrize("ft", list(DNSFailureType))
    def test_empty_graph(self, ft: DNSFailureType):
        eng = _engine()
        g = _graph()
        impact = eng.simulate_dns_failure(g, ft, _default_config())
        assert isinstance(impact, DNSFailureImpact)

    def test_affected_services_high_impact(self):
        eng = _engine()
        g = _sample_graph()
        # Provider outage with no redundancy = high impact = all services
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.PROVIDER_OUTAGE, _weak_config()
        )
        assert len(impact.affected_services) == len(g.components)

    def test_affected_services_low_impact(self):
        eng = _engine()
        g = _sample_graph()
        # DNSSEC validation without DNSSEC = very low impact
        impact = eng.simulate_dns_failure(
            g, DNSFailureType.DNSSEC_VALIDATION_FAILURE, _weak_config()
        )
        assert len(impact.affected_services) <= len(g.components)


# ===========================================================================
# 7. analyze_ttl_strategy
# ===========================================================================


class TestAnalyzeTTLStrategy:
    def test_normal_ttl(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=300))
        assert result.current_ttl == 300
        assert result.ttl_risk_level == "low"
        assert result.cache_effectiveness > 0.0

    def test_very_low_ttl(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=10))
        assert result.ttl_risk_level == "high"
        assert result.recommended_ttl == 300

    def test_low_ttl(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=45))
        assert result.ttl_risk_level == "medium"

    def test_high_ttl(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=7200))
        assert result.ttl_risk_level == "high"
        assert result.recommended_ttl == 300
        assert result.cache_effectiveness > 80.0

    def test_moderate_ttl(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=1800))
        assert result.ttl_risk_level == "low"

    def test_propagation_delay_equals_ttl(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=600))
        assert result.propagation_delay_seconds == 600.0

    def test_cache_effectiveness_increases_with_ttl(self):
        eng = _engine()
        g = _graph()
        low = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=10))
        mid = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=300))
        high = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=7200))
        assert low.cache_effectiveness < mid.cache_effectiveness
        assert mid.cache_effectiveness < high.cache_effectiveness

    def test_large_graph_recommendation(self):
        eng = _engine()
        components = [
            _comp(f"svc{i}", f"Service {i}") for i in range(15)
        ]
        g = _graph(*components)
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=300))
        joined = " ".join(result.recommendations).lower()
        assert "large" in joined or "failover" in joined

    def test_ttl_60_boundary(self):
        eng = _engine()
        g = _graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=60))
        assert result.ttl_risk_level == "low"

    def test_ttl_just_below_60(self):
        eng = _engine()
        g = _graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=59))
        assert result.ttl_risk_level == "medium"

    def test_ttl_3600_boundary(self):
        eng = _engine()
        g = _graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=3600))
        assert result.ttl_risk_level == "low"

    def test_ttl_above_3600(self):
        eng = _engine()
        g = _graph()
        result = eng.analyze_ttl_strategy(g, _default_config(ttl_seconds=3601))
        assert result.ttl_risk_level == "high"


# ===========================================================================
# 8. detect_dns_single_points
# ===========================================================================


class TestDetectDNSSinglePoints:
    def test_weak_config_has_many_spofs(self):
        eng = _engine()
        g = _sample_graph()
        spofs = eng.detect_dns_single_points(g, _weak_config())
        assert len(spofs) >= 3

    def test_strong_config_has_fewer_spofs(self):
        eng = _engine()
        g = _sample_graph()
        weak_spofs = eng.detect_dns_single_points(g, _weak_config())
        strong_spofs = eng.detect_dns_single_points(g, _default_config())
        assert len(strong_spofs) < len(weak_spofs)

    def test_no_failover_detected(self):
        eng = _engine()
        g = _graph()
        spofs = eng.detect_dns_single_points(g, _weak_config())
        assert any("failover" in s.lower() for s in spofs)

    def test_no_multi_provider_detected(self):
        eng = _engine()
        g = _graph()
        spofs = eng.detect_dns_single_points(
            g, _weak_config()
        )
        assert any("multi-provider" in s.lower() or "single" in s.lower() for s in spofs)

    def test_no_dnssec_detected(self):
        eng = _engine()
        g = _graph()
        spofs = eng.detect_dns_single_points(g, _weak_config())
        assert any("dnssec" in s.lower() for s in spofs)

    def test_no_health_check_detected(self):
        eng = _engine()
        g = _graph()
        spofs = eng.detect_dns_single_points(g, _weak_config())
        assert any("health" in s.lower() for s in spofs)

    def test_dns_component_without_replicas(self):
        eng = _engine()
        dns_comp = _comp("dns1", "Primary DNS", ComponentType.DNS, replicas=1)
        g = _graph(dns_comp)
        spofs = eng.detect_dns_single_points(g, _default_config())
        assert any("dns" in s.lower() and "replica" in s.lower() for s in spofs)

    def test_dns_component_with_replicas(self):
        eng = _engine()
        dns_comp = _comp("dns1", "Primary DNS", ComponentType.DNS, replicas=3)
        g = _graph(dns_comp)
        spofs = eng.detect_dns_single_points(g, _default_config())
        # Should NOT flag the DNS component
        assert not any(
            "Primary DNS" in s and "replica" in s.lower()
            for s in spofs
        )

    def test_empty_graph(self):
        eng = _engine()
        g = _graph()
        spofs = eng.detect_dns_single_points(g, _default_config())
        # Even with strong config, no DNS component SPOFs
        assert isinstance(spofs, list)


# ===========================================================================
# 9. simulate_provider_failover
# ===========================================================================


class TestSimulateProviderFailover:
    def test_no_failover_provider(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.simulate_provider_failover(g, _weak_config())
        assert result.data_loss_possible is True
        assert result.seamless is False
        assert result.failover_time_seconds > 0

    def test_multi_provider_is_seamless(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.simulate_provider_failover(g, _default_config())
        assert result.seamless is True
        assert result.data_loss_possible is False

    def test_health_check_failover(self):
        eng = _engine()
        g = _sample_graph()
        cfg = _default_config(multi_provider=False, ttl_seconds=60)
        result = eng.simulate_provider_failover(g, cfg)
        assert result.seamless is True  # low TTL + health check

    def test_health_check_failover_high_ttl(self):
        eng = _engine()
        g = _sample_graph()
        cfg = _default_config(multi_provider=False, ttl_seconds=600)
        result = eng.simulate_provider_failover(g, cfg)
        assert result.seamless is False  # high TTL

    def test_failover_without_health_check(self):
        eng = _engine()
        g = _sample_graph()
        cfg = DNSConfig(
            provider="main",
            failover_provider="backup",
            health_check_enabled=False,
            multi_provider=False,
        )
        result = eng.simulate_provider_failover(g, cfg)
        assert result.failover_time_seconds > 0
        joined = " ".join(result.recommendations).lower()
        assert "health check" in joined

    def test_primary_and_failover_providers(self):
        eng = _engine()
        g = _sample_graph()
        cfg = _default_config(provider="route53", failover_provider="cloudflare")
        result = eng.simulate_provider_failover(g, cfg)
        assert result.primary_provider == "route53"
        assert result.failover_provider == "cloudflare"

    def test_records_affected(self):
        eng = _engine()
        g = _sample_graph()
        cfg = _default_config(records=["a.com", "b.com", "c.com"])
        result = eng.simulate_provider_failover(g, cfg)
        assert result.records_affected == 3

    def test_no_records(self):
        eng = _engine()
        g = _sample_graph()
        cfg = _default_config(records=[])
        result = eng.simulate_provider_failover(g, cfg)
        assert result.records_affected == 1  # minimum 1

    def test_multi_provider_fastest_failover(self):
        eng = _engine()
        g = _sample_graph()
        multi = eng.simulate_provider_failover(g, _default_config())
        no_fo = eng.simulate_provider_failover(g, _weak_config())
        assert multi.failover_time_seconds < no_fo.failover_time_seconds


# ===========================================================================
# 10. recommend_dns_config
# ===========================================================================


class TestRecommendDNSConfig:
    def test_empty_graph(self):
        eng = _engine()
        g = _graph()
        cfg = eng.recommend_dns_config(g)
        assert cfg.dnssec_enabled is True
        assert cfg.health_check_enabled is True
        assert cfg.failover_provider != ""

    def test_small_graph_ttl(self):
        eng = _engine()
        g = _graph(
            _comp("a", "App1"),
            _comp("b", "App2"),
        )
        cfg = eng.recommend_dns_config(g)
        assert cfg.ttl_seconds == 300

    def test_medium_graph_ttl(self):
        eng = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(7)])
        cfg = eng.recommend_dns_config(g)
        assert cfg.ttl_seconds == 180

    def test_large_graph_ttl(self):
        eng = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(15)])
        cfg = eng.recommend_dns_config(g)
        assert cfg.ttl_seconds == 60

    def test_multi_provider_when_db_present(self):
        eng = _engine()
        g = _graph(
            _comp("app", "App", ComponentType.APP_SERVER),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        cfg = eng.recommend_dns_config(g)
        assert cfg.multi_provider is True

    def test_multi_provider_when_external_api_present(self):
        eng = _engine()
        g = _graph(
            _comp("app", "App", ComponentType.APP_SERVER),
            _comp("ext", "External", ComponentType.EXTERNAL_API),
        )
        cfg = eng.recommend_dns_config(g)
        assert cfg.multi_provider is True

    def test_multi_provider_when_many_services(self):
        eng = _engine()
        g = _graph(*[_comp(f"s{i}", f"Svc{i}") for i in range(8)])
        cfg = eng.recommend_dns_config(g)
        assert cfg.multi_provider is True

    def test_records_match_components(self):
        eng = _engine()
        g = _graph(
            _comp("web", "Web"),
            _comp("api", "API"),
        )
        cfg = eng.recommend_dns_config(g)
        assert set(cfg.records) == {"web", "api"}

    def test_recommended_config_scores_well(self):
        eng = _engine()
        g = _sample_graph()
        cfg = eng.recommend_dns_config(g)
        report = eng.assess_dns_resilience(g, cfg)
        assert report.overall_score >= 50.0


# ===========================================================================
# 11. estimate_dns_outage_blast_radius
# ===========================================================================


class TestBlastRadius:
    def test_empty_graph(self):
        eng = _engine()
        g = _graph()
        result = eng.estimate_dns_outage_blast_radius(g, _default_config())
        assert result.total_services == 0
        assert result.affected_percent == 0.0
        assert len(result.recommendations) >= 1

    def test_weak_config_full_blast(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        assert result.affected_percent == 100.0
        assert len(result.affected_services) == len(g.components)

    def test_multi_provider_reduces_blast(self):
        eng = _engine()
        g = _sample_graph()
        weak = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        strong = eng.estimate_dns_outage_blast_radius(g, _default_config())
        assert strong.affected_percent < weak.affected_percent

    def test_failover_provider_reduces_blast(self):
        eng = _engine()
        g = _sample_graph()
        no_fo = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        with_fo = eng.estimate_dns_outage_blast_radius(
            g, _weak_config(failover_provider="backup")
        )
        assert with_fo.affected_percent < no_fo.affected_percent

    def test_critical_services_identified(self):
        eng = _engine()
        g = _graph(
            _comp("lb", "LB", ComponentType.LOAD_BALANCER),
            _comp("db", "DB", ComponentType.DATABASE),
            _comp("cache", "Cache", ComponentType.CACHE),
        )
        result = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        # lb and db are critical types
        assert len(result.critical_services_affected) >= 1

    def test_downtime_multi_provider(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.estimate_dns_outage_blast_radius(g, _default_config())
        assert result.estimated_downtime_seconds > 0

    def test_downtime_no_redundancy(self):
        eng = _engine()
        g = _sample_graph()
        weak = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        strong = eng.estimate_dns_outage_blast_radius(g, _default_config())
        assert weak.estimated_downtime_seconds > strong.estimated_downtime_seconds

    def test_recommendations_no_health_check(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        joined = " ".join(result.recommendations).lower()
        assert "health check" in joined

    def test_recommendations_no_multi_provider(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        joined = " ".join(result.recommendations).lower()
        assert "multi-provider" in joined

    def test_recommendations_no_failover(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        joined = " ".join(result.recommendations).lower()
        assert "failover" in joined

    def test_high_blast_radius_recommendation(self):
        eng = _engine()
        g = _sample_graph()
        result = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        # 100% affected > 50%, should recommend service mesh
        joined = " ".join(result.recommendations).lower()
        assert "blast radius" in joined or "service mesh" in joined

    def test_critical_services_count_recommendation(self):
        eng = _engine()
        g = _graph(
            _comp("lb", "LB", ComponentType.LOAD_BALANCER),
            _comp("app", "App", ComponentType.APP_SERVER),
            _comp("db", "DB", ComponentType.DATABASE),
        )
        result = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        if result.critical_services_affected:
            joined = " ".join(result.recommendations).lower()
            assert "critical" in joined

    def test_downtime_with_failover_and_health_check(self):
        eng = _engine()
        g = _sample_graph()
        cfg = DNSConfig(
            failover_provider="backup",
            health_check_enabled=True,
            multi_provider=False,
        )
        result = eng.estimate_dns_outage_blast_radius(g, cfg)
        no_fo = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        assert result.estimated_downtime_seconds < no_fo.estimated_downtime_seconds

    def test_downtime_with_failover_no_health_check(self):
        eng = _engine()
        g = _sample_graph()
        cfg = DNSConfig(
            failover_provider="backup",
            health_check_enabled=False,
            multi_provider=False,
        )
        result = eng.estimate_dns_outage_blast_radius(g, cfg)
        assert result.estimated_downtime_seconds > 0


# ===========================================================================
# 12. assess_dns_resilience (full report)
# ===========================================================================


class TestAssessDNSResilience:
    def test_strong_config_high_score(self):
        eng = _engine()
        g = _sample_graph()
        report = eng.assess_dns_resilience(g, _default_config())
        assert report.overall_score > 50.0
        assert isinstance(report.timestamp, str)
        assert len(report.timestamp) > 0

    def test_weak_config_low_score(self):
        eng = _engine()
        g = _sample_graph()
        weak_report = eng.assess_dns_resilience(g, _weak_config())
        strong_report = eng.assess_dns_resilience(g, _default_config())
        assert weak_report.overall_score < strong_report.overall_score

    def test_all_failure_types_simulated(self):
        eng = _engine()
        g = _sample_graph()
        report = eng.assess_dns_resilience(g, _default_config())
        assert len(report.failure_impacts) == len(DNSFailureType)

    def test_spofs_populated(self):
        eng = _engine()
        g = _sample_graph()
        report = eng.assess_dns_resilience(g, _weak_config())
        assert len(report.single_points_of_failure) >= 1

    def test_recommendations_for_weak_config(self):
        eng = _engine()
        g = _sample_graph()
        report = eng.assess_dns_resilience(g, _weak_config())
        assert len(report.recommendations) >= 3

    def test_dnssec_recommendation(self):
        eng = _engine()
        g = _graph()
        report = eng.assess_dns_resilience(
            g, _default_config(dnssec_enabled=False)
        )
        joined = " ".join(report.recommendations).lower()
        assert "dnssec" in joined

    def test_health_check_recommendation(self):
        eng = _engine()
        g = _graph()
        report = eng.assess_dns_resilience(
            g, _default_config(health_check_enabled=False)
        )
        joined = " ".join(report.recommendations).lower()
        assert "health check" in joined

    def test_failover_recommendation(self):
        eng = _engine()
        g = _graph()
        report = eng.assess_dns_resilience(
            g, _default_config(failover_provider="")
        )
        joined = " ".join(report.recommendations).lower()
        assert "failover" in joined

    def test_multi_provider_recommendation(self):
        eng = _engine()
        g = _graph()
        report = eng.assess_dns_resilience(
            g, _default_config(multi_provider=False)
        )
        joined = " ".join(report.recommendations).lower()
        assert "multi-provider" in joined

    def test_high_ttl_recommendation(self):
        eng = _engine()
        g = _graph()
        report = eng.assess_dns_resilience(
            g, _default_config(ttl_seconds=7200)
        )
        joined = " ".join(report.recommendations).lower()
        assert "ttl" in joined

    def test_low_ttl_recommendation(self):
        eng = _engine()
        g = _graph()
        report = eng.assess_dns_resilience(
            g, _default_config(ttl_seconds=10)
        )
        joined = " ".join(report.recommendations).lower()
        assert "ttl" in joined

    def test_score_clamped_0_100(self):
        eng = _engine()
        g = _sample_graph()
        report = eng.assess_dns_resilience(g, _weak_config())
        assert 0.0 <= report.overall_score <= 100.0
        report2 = eng.assess_dns_resilience(g, _default_config())
        assert 0.0 <= report2.overall_score <= 100.0

    def test_empty_graph(self):
        eng = _engine()
        g = _graph()
        report = eng.assess_dns_resilience(g, _default_config())
        assert isinstance(report, DNSResilienceReport)
        assert 0.0 <= report.overall_score <= 100.0

    def test_spof_penalty(self):
        eng = _engine()
        g = _graph()
        # More SPOFs → lower score
        weak = eng.assess_dns_resilience(g, _weak_config())
        strong = eng.assess_dns_resilience(g, _default_config())
        assert weak.overall_score < strong.overall_score


# ===========================================================================
# 13. Edge cases and boundary values
# ===========================================================================


class TestEdgeCases:
    def test_minimal_config(self):
        eng = _engine()
        g = _graph()
        cfg = DNSConfig(ttl_seconds=1)
        report = eng.assess_dns_resilience(g, cfg)
        assert isinstance(report, DNSResilienceReport)

    def test_single_component_graph(self):
        eng = _engine()
        g = _graph(_comp("only", "Only Service"))
        cfg = _default_config()
        report = eng.assess_dns_resilience(g, cfg)
        assert report.overall_score > 0

    def test_dns_type_component_in_graph(self):
        eng = _engine()
        g = _graph(
            _comp("dns", "DNS Server", ComponentType.DNS, replicas=2),
            _comp("app", "App"),
        )
        cfg = _default_config()
        spofs = eng.detect_dns_single_points(g, cfg)
        # DNS with 2 replicas should not be flagged
        assert not any("DNS Server" in s and "replica" in s for s in spofs)

    def test_max_ttl(self):
        eng = _engine()
        g = _graph()
        cfg = DNSConfig(ttl_seconds=86400)
        analysis = eng.analyze_ttl_strategy(g, cfg)
        assert analysis.ttl_risk_level == "high"

    def test_min_ttl(self):
        eng = _engine()
        g = _graph()
        cfg = DNSConfig(ttl_seconds=1)
        analysis = eng.analyze_ttl_strategy(g, cfg)
        assert analysis.ttl_risk_level == "high"

    def test_all_failure_types_on_single_node_graph(self):
        eng = _engine()
        g = _graph(_comp("solo", "Solo"))
        for ft in DNSFailureType:
            impact = eng.simulate_dns_failure(g, ft, _default_config())
            assert isinstance(impact, DNSFailureImpact)

    def test_large_graph_blast_radius(self):
        eng = _engine()
        components = [_comp(f"s{i}", f"Svc{i}") for i in range(50)]
        g = _graph(*components)
        result = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        assert result.total_services == 50
        assert result.affected_percent == 100.0

    def test_failover_with_empty_records(self):
        eng = _engine()
        g = _graph()
        cfg = DNSConfig(records=[])
        result = eng.simulate_provider_failover(g, cfg)
        assert result.records_affected >= 1

    def test_recommend_then_assess(self):
        eng = _engine()
        g = _sample_graph()
        recommended = eng.recommend_dns_config(g)
        report = eng.assess_dns_resilience(g, recommended)
        assert report.overall_score >= 50.0

    def test_blast_radius_with_only_critical_services(self):
        eng = _engine()
        g = _graph(
            _comp("db1", "DB1", ComponentType.DATABASE),
            _comp("db2", "DB2", ComponentType.DATABASE),
            _comp("lb", "LB", ComponentType.LOAD_BALANCER),
        )
        result = eng.estimate_dns_outage_blast_radius(g, _weak_config())
        assert len(result.critical_services_affected) >= 2

    def test_all_record_types_in_config(self):
        cfg = DNSConfig(
            records=[rt.value for rt in DNSRecordType],
        )
        assert len(cfg.records) == 8

    def test_provider_failover_multi_provider_vs_health_check(self):
        eng = _engine()
        g = _graph()
        multi = eng.simulate_provider_failover(g, _default_config())
        hc_only = eng.simulate_provider_failover(
            g, _default_config(multi_provider=False)
        )
        assert multi.failover_time_seconds <= hc_only.failover_time_seconds

    def test_ttl_analysis_with_large_service_count(self):
        eng = _engine()
        g = _graph(*[_comp(f"s{i}", f"S{i}") for i in range(20)])
        result = eng.analyze_ttl_strategy(g, _default_config())
        joined = " ".join(result.recommendations).lower()
        assert "large" in joined or "failover" in joined

    def test_simulate_all_types_consistent_with_constants(self):
        eng = _engine()
        g = _sample_graph()
        for ft in DNSFailureType:
            impact = eng.simulate_dns_failure(g, ft, _weak_config())
            # Weak config should show higher impact
            assert impact.user_impact_percent > 0 or ft == DNSFailureType.DNSSEC_VALIDATION_FAILURE

    def test_blast_radius_affected_count_never_zero_with_services(self):
        eng = _engine()
        g = _graph(_comp("one", "One"))
        result = eng.estimate_dns_outage_blast_radius(g, _default_config())
        assert len(result.affected_services) >= 1

    def test_multiple_dns_components_some_without_replicas(self):
        eng = _engine()
        g = _graph(
            _comp("dns1", "DNS1", ComponentType.DNS, replicas=1),
            _comp("dns2", "DNS2", ComponentType.DNS, replicas=3),
        )
        spofs = eng.detect_dns_single_points(g, _default_config())
        assert any("DNS1" in s for s in spofs)
        assert not any("DNS2" in s and "replica" in s for s in spofs)
