"""Tests for the DNS Resilience Analyzer module.

Covers provider redundancy, TTL analysis, propagation delay modeling,
DNSSEC validation chain analysis, DNS-based load balancing evaluation,
failover timing, amplification attack resistance, split-horizon risk,
dependency chain mapping, resolver resilience, zone transfer security,
and graph-level DNS component analysis. Targets 100% branch coverage.
"""

from __future__ import annotations

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.dns_resilience_analyzer import (
    AmplificationRisk,
    DNSProviderType,
    DNSRecord,
    DNSResilienceAnalyzer,
    DNSResilienceReport,
    DNSSECAssessment,
    DNSSECStatus,
    DNSProvider,
    DNSZone,
    DependencyChainAssessment,
    FailoverTimingAssessment,
    LBEvaluation,
    LoadBalancingStrategy,
    PropagationEstimate,
    ProviderRedundancyAssessment,
    ResolverAssessment,
    ResolverType,
    RiskLevel,
    SplitHorizonAssessment,
    TTLAssessment,
    ZoneTransferAssessment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    from faultray.model.graph import InfraGraph

    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _dns_comp(cid="dns1", replicas=1, health=HealthStatus.HEALTHY, failover=False):
    return Component(
        id=cid,
        name=cid,
        type=ComponentType.DNS,
        replicas=replicas,
        health=health,
        failover=FailoverConfig(enabled=failover),
    )


def _provider(
    pid="p1",
    name="Provider1",
    ptype=DNSProviderType.CLOUD_MANAGED,
    primary=True,
    sla=99.99,
    hc_interval=30.0,
    failover_threshold=3,
    anycast=True,
):
    return DNSProvider(
        provider_id=pid,
        name=name,
        provider_type=ptype,
        is_primary=primary,
        sla_percent=sla,
        health_check_interval_seconds=hc_interval,
        failover_threshold=failover_threshold,
        anycast_enabled=anycast,
    )


def _record(
    name="www.example.com",
    rtype="A",
    ttl=300,
    values=None,
    health_check=False,
    failover_target="",
    weight=1.0,
):
    return DNSRecord(
        name=name,
        record_type=rtype,
        ttl_seconds=ttl,
        values=values or ["1.2.3.4"],
        health_check_enabled=health_check,
        failover_target=failover_target,
        weight=weight,
    )


def _zone(
    zone_id="z1",
    domain="example.com",
    providers=None,
    records=None,
    dnssec=DNSSECStatus.UNSIGNED,
    dnssec_expiry=365,
    lb_strategy=LoadBalancingStrategy.NONE,
    split_horizon=False,
    zone_transfer_restricted=True,
    ns_depth=1,
):
    return DNSZone(
        zone_id=zone_id,
        domain=domain,
        providers=providers or [],
        records=records or [],
        dnssec_status=dnssec,
        dnssec_key_expiry_days=dnssec_expiry,
        lb_strategy=lb_strategy,
        split_horizon_enabled=split_horizon,
        zone_transfer_restricted=zone_transfer_restricted,
        ns_delegation_depth=ns_depth,
    )


# ---------------------------------------------------------------------------
# Test: Empty / minimal graphs
# ---------------------------------------------------------------------------


class TestEmptyAndMinimal:
    def test_empty_graph_no_zones(self):
        """No zones, no components -> score 0."""
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g)
        report = analyzer.analyze()
        assert isinstance(report, DNSResilienceReport)
        assert report.overall_score == 0.0
        assert report.recommendations == []

    def test_single_non_dns_component(self):
        """Graph with only a non-DNS component, no zones."""
        g = _graph(_comp("app1"))
        analyzer = DNSResilienceAnalyzer(graph=g)
        report = analyzer.analyze()
        assert report.overall_score == 0.0
        assert report.component_dns_risks == []

    def test_analyze_zone_not_found(self):
        """analyze_zone returns None for unknown zone_id."""
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[_zone("z1")])
        result = analyzer.analyze_zone("nonexistent")
        assert result is None

    def test_analyze_zone_found(self):
        """analyze_zone returns report for existing zone."""
        z = _zone("z1", providers=[_provider()], records=[_record()])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        result = analyzer.analyze_zone("z1")
        assert result is not None
        assert isinstance(result, DNSResilienceReport)


# ---------------------------------------------------------------------------
# Test: Provider redundancy assessment
# ---------------------------------------------------------------------------


class TestProviderRedundancy:
    def test_no_providers(self):
        """Zone with no providers -> CRITICAL risk."""
        z = _zone("z1", providers=[])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        pa = report.provider_assessments[0]
        assert pa.provider_count == 0
        assert pa.risk_level == RiskLevel.CRITICAL
        assert pa.single_provider_risk is True
        assert len(pa.recommendations) > 0

    def test_single_provider(self):
        """Single provider -> HIGH risk."""
        z = _zone("z1", providers=[_provider("p1")])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        pa = report.provider_assessments[0]
        assert pa.provider_count == 1
        assert pa.risk_level == RiskLevel.HIGH
        assert pa.single_provider_risk is True

    def test_dual_provider_with_failover(self):
        """Two providers with primary/secondary -> LOW risk."""
        z = _zone(
            "z1",
            providers=[
                _provider("p1", primary=True, sla=99.99),
                _provider("p2", primary=False, sla=99.95),
            ],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        pa = report.provider_assessments[0]
        assert pa.provider_count == 2
        assert pa.has_failover is True
        assert pa.single_provider_risk is False
        assert pa.risk_level == RiskLevel.LOW
        # Combined SLA should be > each individual
        assert pa.combined_sla_percent > 99.99

    def test_dual_provider_both_primary_no_failover(self):
        """Two providers but both primary -> MEDIUM risk (no failover)."""
        z = _zone(
            "z1",
            providers=[
                _provider("p1", primary=True),
                _provider("p2", primary=True),
            ],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        pa = report.provider_assessments[0]
        # Both primary -> no secondary/failover provider
        assert pa.provider_count == 2
        assert pa.has_failover is False
        assert pa.single_provider_risk is False
        assert pa.risk_level == RiskLevel.MEDIUM
        assert len(pa.recommendations) > 0


# ---------------------------------------------------------------------------
# Test: TTL analysis
# ---------------------------------------------------------------------------


class TestTTLAnalysis:
    def test_very_low_ttl(self):
        """TTL <= 30 -> LOW risk."""
        z = _zone("z1", records=[_record(ttl=10)])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ttl = report.ttl_assessments[0]
        assert ttl.cache_staleness_risk == RiskLevel.LOW
        assert ttl.recommended_ttl == 10  # keep as-is

    def test_moderate_ttl(self):
        """TTL 60-300 -> LOW risk, recommend 60."""
        z = _zone("z1", records=[_record(ttl=300)])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ttl = report.ttl_assessments[0]
        assert ttl.cache_staleness_risk == RiskLevel.LOW
        assert ttl.recommended_ttl == 60

    def test_high_ttl(self):
        """TTL 301-3600 -> MEDIUM risk."""
        z = _zone("z1", records=[_record(ttl=1800)])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ttl = report.ttl_assessments[0]
        assert ttl.cache_staleness_risk == RiskLevel.MEDIUM
        assert ttl.recommended_ttl == 300

    def test_very_high_ttl(self):
        """TTL > 3600 -> HIGH risk."""
        z = _zone("z1", records=[_record(ttl=86400)])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ttl = report.ttl_assessments[0]
        assert ttl.cache_staleness_risk == RiskLevel.HIGH
        assert ttl.failover_delay_seconds == 86400.0

    def test_no_records(self):
        """Zone with no records -> no TTL assessments."""
        z = _zone("z1")
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        assert report.ttl_assessments == []


# ---------------------------------------------------------------------------
# Test: Propagation delay modeling
# ---------------------------------------------------------------------------


class TestPropagationDelay:
    def test_no_records_propagation(self):
        """No records -> zero propagation, INFO risk."""
        z = _zone("z1")
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        prop = report.propagation_estimates[0]
        assert prop.estimated_full_propagation_seconds == 0.0
        assert prop.risk_level == RiskLevel.INFO

    def test_low_ttl_propagation(self):
        """Low TTL records -> low propagation."""
        z = _zone("z1", records=[_record(ttl=60), _record(name="api", ttl=30)])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        prop = report.propagation_estimates[0]
        assert prop.estimated_full_propagation_seconds == 60.0
        assert prop.estimated_partial_propagation_seconds == 30.0
        assert prop.risk_level == RiskLevel.LOW

    def test_high_ttl_propagation(self):
        """Very high TTL -> HIGH risk propagation."""
        z = _zone("z1", records=[_record(ttl=7200)])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        prop = report.propagation_estimates[0]
        assert prop.estimated_full_propagation_seconds == 7200.0
        assert prop.risk_level == RiskLevel.HIGH

    def test_delegation_depth_multiplier(self):
        """NS delegation depth increases propagation estimate."""
        z = _zone("z1", records=[_record(ttl=600)], ns_depth=3)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        prop = report.propagation_estimates[0]
        # 600 * (1.0 + (3-1)*0.1) = 600 * 1.2 = 720
        assert prop.estimated_full_propagation_seconds == 720.0
        assert prop.risk_level == RiskLevel.MEDIUM

    def test_medium_propagation(self):
        """Propagation between 600 and 3600 -> MEDIUM risk."""
        z = _zone("z1", records=[_record(ttl=1000)])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        prop = report.propagation_estimates[0]
        assert prop.risk_level == RiskLevel.MEDIUM

    def test_estimate_propagation_delay_missing_zone(self):
        """estimate_propagation_delay for unknown zone."""
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g)
        result = analyzer.estimate_propagation_delay("unknown")
        assert result.risk_level == RiskLevel.HIGH
        assert result.estimated_full_propagation_seconds == 0.0

    def test_estimate_propagation_delay_found(self):
        """estimate_propagation_delay for known zone."""
        z = _zone("z1", records=[_record(ttl=120)])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        result = analyzer.estimate_propagation_delay("z1")
        assert result.estimated_full_propagation_seconds == 120.0


# ---------------------------------------------------------------------------
# Test: DNSSEC validation chain
# ---------------------------------------------------------------------------


class TestDNSSEC:
    def test_unsigned(self):
        """Unsigned zone -> MEDIUM risk."""
        z = _zone("z1", dnssec=DNSSECStatus.UNSIGNED)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ds = report.dnssec_assessments[0]
        assert ds.status == DNSSECStatus.UNSIGNED
        assert ds.risk_level == RiskLevel.MEDIUM
        assert len(ds.issues) > 0

    def test_expired_keys(self):
        """Expired DNSSEC -> CRITICAL risk."""
        z = _zone("z1", dnssec=DNSSECStatus.EXPIRED)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ds = report.dnssec_assessments[0]
        assert ds.risk_level == RiskLevel.CRITICAL

    def test_broken_chain(self):
        """Broken chain -> CRITICAL risk."""
        z = _zone("z1", dnssec=DNSSECStatus.BROKEN_CHAIN)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ds = report.dnssec_assessments[0]
        assert ds.risk_level == RiskLevel.CRITICAL

    def test_partially_signed(self):
        """Partially signed -> MEDIUM risk."""
        z = _zone("z1", dnssec=DNSSECStatus.PARTIALLY_SIGNED)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ds = report.dnssec_assessments[0]
        assert ds.risk_level == RiskLevel.MEDIUM

    def test_fully_signed(self):
        """Fully signed with good expiry -> LOW risk."""
        z = _zone("z1", dnssec=DNSSECStatus.FULLY_SIGNED, dnssec_expiry=365)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ds = report.dnssec_assessments[0]
        assert ds.risk_level == RiskLevel.LOW
        assert ds.chain_depth == 2  # ns_depth(1) + 1 for fully signed

    def test_key_expiry_imminent(self):
        """Key expiring in 5 days -> CRITICAL regardless of status."""
        z = _zone("z1", dnssec=DNSSECStatus.FULLY_SIGNED, dnssec_expiry=5)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ds = report.dnssec_assessments[0]
        assert ds.risk_level == RiskLevel.CRITICAL
        assert any("urgently" in r for r in ds.recommendations)

    def test_key_expiry_soon(self):
        """Key expiring in 20 days -> HIGH risk."""
        z = _zone("z1", dnssec=DNSSECStatus.FULLY_SIGNED, dnssec_expiry=20)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        ds = report.dnssec_assessments[0]
        assert ds.risk_level == RiskLevel.HIGH


# ---------------------------------------------------------------------------
# Test: Load balancing evaluation
# ---------------------------------------------------------------------------


class TestLoadBalancing:
    def test_no_lb_strategy(self):
        """No LB strategy -> HIGH risk."""
        z = _zone("z1", lb_strategy=LoadBalancingStrategy.NONE, records=[_record()])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        lb = report.lb_evaluations[0]
        assert lb.risk_level == RiskLevel.HIGH
        assert lb.strategy == LoadBalancingStrategy.NONE

    def test_failover_strategy(self):
        """Failover strategy with health checks -> LOW risk."""
        z = _zone(
            "z1",
            lb_strategy=LoadBalancingStrategy.FAILOVER,
            records=[_record(health_check=True)],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        lb = report.lb_evaluations[0]
        assert lb.failover_capable is True
        assert lb.risk_level == RiskLevel.LOW

    def test_weighted_low_health_coverage(self):
        """Weighted LB but <50% health checks -> MEDIUM risk."""
        z = _zone(
            "z1",
            lb_strategy=LoadBalancingStrategy.WEIGHTED,
            records=[
                _record(name="r1", health_check=False),
                _record(name="r2", health_check=False),
                _record(name="r3", health_check=True),
            ],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        lb = report.lb_evaluations[0]
        # 1/3 = 33% < 50%
        assert lb.risk_level == RiskLevel.MEDIUM

    def test_geo_dns_full_health(self):
        """GeoDNS with all health checks -> LOW risk."""
        z = _zone(
            "z1",
            lb_strategy=LoadBalancingStrategy.GEO_DNS,
            records=[_record(health_check=True), _record(name="api", health_check=True)],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        lb = report.lb_evaluations[0]
        assert lb.risk_level == RiskLevel.LOW
        assert lb.health_check_coverage == 1.0


# ---------------------------------------------------------------------------
# Test: Failover timing
# ---------------------------------------------------------------------------


class TestFailoverTiming:
    def test_no_providers_no_records(self):
        """No providers and no records -> HIGH risk."""
        z = _zone("z1")
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        fo = report.failover_assessments[0]
        assert fo.risk_level == RiskLevel.HIGH
        assert fo.total_failover_time_seconds == 0.0

    def test_fast_failover(self):
        """Short HC interval and low TTL -> LOW risk."""
        z = _zone(
            "z1",
            providers=[_provider(hc_interval=10, failover_threshold=2)],
            records=[_record(ttl=30)],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z], rto_target_seconds=300.0)
        report = analyzer.analyze()
        fo = report.failover_assessments[0]
        # detection: 10*2=20s, propagation: 30s, total: 50s
        assert fo.detection_time_seconds == 20.0
        assert fo.propagation_time_seconds == 30.0
        assert fo.total_failover_time_seconds == 50.0
        assert fo.meets_rto is True
        assert fo.risk_level == RiskLevel.LOW

    def test_slow_failover_exceeds_rto(self):
        """High TTL exceeds RTO -> HIGH risk."""
        z = _zone(
            "z1",
            providers=[_provider(hc_interval=30, failover_threshold=3)],
            records=[_record(ttl=600)],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z], rto_target_seconds=300.0)
        report = analyzer.analyze()
        fo = report.failover_assessments[0]
        # detection: 30*3=90s, propagation: 600s, total: 690s > 300
        assert fo.total_failover_time_seconds == 690.0
        assert fo.meets_rto is False
        assert fo.risk_level == RiskLevel.HIGH

    def test_close_to_rto_target(self):
        """Failover time 81-100% of RTO -> MEDIUM risk."""
        z = _zone(
            "z1",
            providers=[_provider(hc_interval=10, failover_threshold=2)],
            records=[_record(ttl=230)],
        )
        g = _graph()
        # detection=20 + propagation=230 = 250, target=300 -> 250/300=83% > 80%
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z], rto_target_seconds=300.0)
        report = analyzer.analyze()
        fo = report.failover_assessments[0]
        assert fo.meets_rto is True
        assert fo.risk_level == RiskLevel.MEDIUM

    def test_assess_failover_readiness_unknown(self):
        """Assess failover readiness for unknown zone."""
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g)
        result = analyzer.assess_failover_readiness("unknown")
        assert result.risk_level == RiskLevel.HIGH
        assert "not found" in result.recommendations[0]

    def test_assess_failover_readiness_known(self):
        """Assess failover readiness for known zone."""
        z = _zone(
            "z1",
            providers=[_provider(hc_interval=10, failover_threshold=2)],
            records=[_record(ttl=30)],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        result = analyzer.assess_failover_readiness("z1")
        assert result.zone_id == "z1"
        assert result.total_failover_time_seconds == 50.0

    def test_rto_target_clamped(self):
        """RTO target below 1.0 is clamped to 1.0."""
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, rto_target_seconds=0.5)
        assert analyzer.rto_target_seconds == 1.0


# ---------------------------------------------------------------------------
# Test: Amplification attack resistance
# ---------------------------------------------------------------------------


class TestAmplificationRisk:
    def test_cloud_managed_low_risk(self):
        """Cloud-managed provider with small records -> LOW risk."""
        z = _zone("z1", providers=[_provider()], records=[_record()])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        amp = report.amplification_risks[0]
        assert amp.risk_level == RiskLevel.LOW
        assert amp.open_resolver_risk is False

    def test_self_hosted_no_anycast(self):
        """Self-hosted without anycast -> HIGH risk."""
        z = _zone(
            "z1",
            providers=[_provider(ptype=DNSProviderType.SELF_HOSTED, anycast=False)],
            records=[_record()],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        amp = report.amplification_risks[0]
        assert amp.risk_level == RiskLevel.HIGH
        assert amp.open_resolver_risk is True

    def test_large_txt_records(self):
        """Large TXT records increase amplification risk."""
        big_txt = "v=spf1 " + "a " * 200  # > 255 chars
        z = _zone(
            "z1",
            providers=[_provider()],
            records=[_record(rtype="TXT", values=[big_txt])],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        amp = report.amplification_risks[0]
        assert amp.large_txt_records == 1
        assert amp.risk_level == RiskLevel.MEDIUM

    def test_many_records_large_any(self):
        """Zone with >20 records -> large_any_responses."""
        records = [_record(name=f"r{i}") for i in range(25)]
        z = _zone("z1", providers=[_provider()], records=records)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        amp = report.amplification_risks[0]
        assert amp.large_any_responses is True
        assert amp.risk_level == RiskLevel.MEDIUM

    def test_no_records_amplification(self):
        """No records -> amplification factor is 0.0 (no data to amplify)."""
        z = _zone("z1", providers=[_provider()])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        amp = report.amplification_risks[0]
        assert amp.max_response_amplification_factor == 0.0

    def test_record_with_empty_values(self):
        """Record with empty values list uses default size."""
        z = _zone(
            "z1",
            providers=[_provider()],
            records=[DNSRecord(name="empty", values=[])],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        amp = report.amplification_risks[0]
        assert amp.max_response_amplification_factor > 1.0


# ---------------------------------------------------------------------------
# Test: Split-horizon DNS risk
# ---------------------------------------------------------------------------


class TestSplitHorizon:
    def test_disabled(self):
        """Split-horizon disabled -> INFO risk."""
        z = _zone("z1", split_horizon=False)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        sh = report.split_horizon_assessments[0]
        assert sh.is_enabled is False
        assert sh.consistency_risk == RiskLevel.INFO
        assert sh.recommendations == []

    def test_enabled(self):
        """Split-horizon enabled -> MEDIUM risk with recommendations."""
        z = _zone("z1", split_horizon=True)
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        sh = report.split_horizon_assessments[0]
        assert sh.is_enabled is True
        assert sh.consistency_risk == RiskLevel.MEDIUM
        assert len(sh.recommendations) >= 2


# ---------------------------------------------------------------------------
# Test: Dependency chain mapping
# ---------------------------------------------------------------------------


class TestDependencyChain:
    def test_no_cnames_single_provider(self):
        """Single NS provider, no CNAMEs -> MEDIUM risk (single NS)."""
        z = _zone("z1", providers=[_provider()], records=[_record()])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        dc = report.dependency_chains[0]
        assert dc.single_ns_risk is True
        assert dc.risk_level == RiskLevel.MEDIUM

    def test_deep_cname_chain(self):
        """Deep CNAME chain -> HIGH risk."""
        records = [
            _record(name="a", rtype="CNAME", values=["b"]),
            _record(name="b", rtype="CNAME", values=["c"]),
            _record(name="c", rtype="CNAME", values=["d"]),
            _record(name="d", rtype="CNAME", values=["e"]),
        ]
        z = _zone(
            "z1",
            providers=[_provider("p1"), _provider("p2", primary=False)],
            records=records,
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        dc = report.dependency_chains[0]
        assert dc.max_cname_depth == 4
        assert dc.risk_level == RiskLevel.HIGH

    def test_deep_ns_delegation(self):
        """Deep NS delegation -> MEDIUM risk."""
        z = _zone(
            "z1",
            providers=[_provider("p1"), _provider("p2", primary=False)],
            records=[_record()],
            ns_depth=5,
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        dc = report.dependency_chains[0]
        assert dc.ns_delegation_depth == 5
        assert dc.risk_level == RiskLevel.MEDIUM

    def test_dual_provider_no_cnames(self):
        """Two providers, no CNAME chains, shallow delegation -> LOW risk."""
        z = _zone(
            "z1",
            providers=[_provider("p1"), _provider("p2", primary=False)],
            records=[_record()],
            ns_depth=1,
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        dc = report.dependency_chains[0]
        assert dc.risk_level == RiskLevel.LOW

    def test_cname_with_no_values(self):
        """CNAME record with empty values list."""
        records = [_record(name="alias", rtype="CNAME", values=[])]
        z = _zone(
            "z1",
            providers=[_provider("p1"), _provider("p2", primary=False)],
            records=records,
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        dc = report.dependency_chains[0]
        assert dc.cname_chain_length == 1
        assert dc.max_cname_depth == 1  # CNAME record exists even with empty target


# ---------------------------------------------------------------------------
# Test: Resolver resilience
# ---------------------------------------------------------------------------


class TestResolverResilience:
    def test_no_resolver_configured(self):
        """No resolver -> no resolver assessments."""
        z = _zone("z1")
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        assert report.resolver_assessments == []

    def test_single_resolver_no_cache_no_encryption(self):
        """Single resolver, no cache, no encryption -> HIGH risk."""
        resolver = ResolverAssessment(
            resolver_type=ResolverType.STUB,
            local_cache_enabled=False,
            encrypted_transport=False,
            redundant_resolvers=1,
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, resolver=resolver)
        report = analyzer.analyze()
        ra = report.resolver_assessments[0]
        assert ra.risk_level == RiskLevel.HIGH
        assert len(ra.recommendations) == 3

    def test_redundant_cached_encrypted_resolver(self):
        """Redundant, cached, encrypted resolver -> LOW risk."""
        resolver = ResolverAssessment(
            resolver_type=ResolverType.DOH,
            local_cache_enabled=True,
            encrypted_transport=True,
            redundant_resolvers=3,
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, resolver=resolver)
        report = analyzer.analyze()
        ra = report.resolver_assessments[0]
        assert ra.risk_level == RiskLevel.LOW
        assert ra.recommendations == []

    def test_no_cache_but_encrypted_redundant(self):
        """No cache, but encrypted and redundant -> MEDIUM risk."""
        resolver = ResolverAssessment(
            resolver_type=ResolverType.DOT,
            local_cache_enabled=False,
            encrypted_transport=True,
            redundant_resolvers=2,
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, resolver=resolver)
        report = analyzer.analyze()
        ra = report.resolver_assessments[0]
        assert ra.risk_level == RiskLevel.MEDIUM
        assert any("cach" in r.lower() for r in ra.recommendations)


# ---------------------------------------------------------------------------
# Test: Zone transfer security
# ---------------------------------------------------------------------------


class TestZoneTransfer:
    def test_restricted(self):
        """Restricted zone transfer -> LOW risk."""
        z = _zone("z1", zone_transfer_restricted=True, providers=[_provider()])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        zt = report.zone_transfer_assessments[0]
        assert zt.risk_level == RiskLevel.LOW
        assert zt.transfer_restricted is True

    def test_unrestricted(self):
        """Unrestricted zone transfer -> HIGH risk."""
        z = _zone("z1", zone_transfer_restricted=False, providers=[_provider()])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        zt = report.zone_transfer_assessments[0]
        assert zt.risk_level == RiskLevel.HIGH
        assert len(zt.recommendations) >= 2


# ---------------------------------------------------------------------------
# Test: Graph-level DNS component analysis
# ---------------------------------------------------------------------------


class TestGraphDNSComponents:
    def test_dns_spof(self):
        """DNS component with 1 replica and dependents -> HIGH risk."""
        dns = _dns_comp("dns1", replicas=1)
        app = _comp("app1")
        g = _graph(dns, app)
        g.add_dependency(Dependency(source_id="app1", target_id="dns1"))
        analyzer = DNSResilienceAnalyzer(graph=g)
        report = analyzer.analyze()
        assert len(report.component_dns_risks) == 1
        risk = report.component_dns_risks[0]
        assert risk["is_spof"] is True
        assert risk["risk_level"] == RiskLevel.HIGH.value

    def test_dns_unhealthy(self):
        """Unhealthy DNS component -> CRITICAL risk."""
        dns = _dns_comp("dns1", health=HealthStatus.DOWN)
        app = _comp("app1")
        g = _graph(dns, app)
        g.add_dependency(Dependency(source_id="app1", target_id="dns1"))
        analyzer = DNSResilienceAnalyzer(graph=g)
        report = analyzer.analyze()
        risk = report.component_dns_risks[0]
        assert risk["risk_level"] == RiskLevel.CRITICAL.value

    def test_dns_no_failover_with_dependents(self):
        """DNS without failover but not SPOF (replicas>1) -> MEDIUM risk."""
        dns = _dns_comp("dns1", replicas=3, failover=False)
        app = _comp("app1")
        g = _graph(dns, app)
        g.add_dependency(Dependency(source_id="app1", target_id="dns1"))
        analyzer = DNSResilienceAnalyzer(graph=g)
        report = analyzer.analyze()
        risk = report.component_dns_risks[0]
        assert risk["is_spof"] is False
        assert risk["risk_level"] == RiskLevel.MEDIUM.value
        assert any("failover" in r.lower() for r in risk["recommendations"])

    def test_dns_with_failover_and_replicas(self):
        """DNS with failover and multiple replicas -> LOW risk."""
        dns = _dns_comp("dns1", replicas=2, failover=True)
        g = _graph(dns)
        analyzer = DNSResilienceAnalyzer(graph=g)
        report = analyzer.analyze()
        assert len(report.component_dns_risks) == 1
        risk = report.component_dns_risks[0]
        assert risk["risk_level"] == RiskLevel.LOW.value

    def test_no_dns_components(self):
        """No DNS components in graph -> empty risks."""
        g = _graph(_comp("app1"), _comp("app2"))
        analyzer = DNSResilienceAnalyzer(graph=g)
        report = analyzer.analyze()
        assert report.component_dns_risks == []


# ---------------------------------------------------------------------------
# Test: Overall scoring and risk classification
# ---------------------------------------------------------------------------


class TestOverallScoring:
    def test_high_score_low_risk(self):
        """Well-configured zone -> high score, LOW risk."""
        z = _zone(
            "z1",
            providers=[
                _provider("p1", sla=99.99),
                _provider("p2", primary=False, sla=99.95),
            ],
            records=[_record(ttl=30, health_check=True)],
            dnssec=DNSSECStatus.FULLY_SIGNED,
            dnssec_expiry=365,
            lb_strategy=LoadBalancingStrategy.FAILOVER,
            zone_transfer_restricted=True,
        )
        resolver = ResolverAssessment(
            resolver_type=ResolverType.DOH,
            local_cache_enabled=True,
            encrypted_transport=True,
            redundant_resolvers=3,
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z], resolver=resolver)
        report = analyzer.analyze()
        assert report.overall_score >= 70.0
        assert report.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)

    def test_low_score_critical_risk(self):
        """Badly configured zone -> low score, HIGH or CRITICAL."""
        z = _zone(
            "z1",
            providers=[],
            records=[_record(ttl=86400)],
            dnssec=DNSSECStatus.BROKEN_CHAIN,
            lb_strategy=LoadBalancingStrategy.NONE,
            zone_transfer_restricted=False,
            split_horizon=True,
        )
        dns = _dns_comp("dns1", replicas=1, health=HealthStatus.DOWN)
        app = _comp("app1")
        g = _graph(dns, app)
        g.add_dependency(Dependency(source_id="app1", target_id="dns1"))
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        assert report.overall_score < 40.0
        assert report.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH)
        assert len(report.recommendations) > 0

    def test_score_to_risk_boundaries(self):
        """Test _score_to_risk static method boundaries."""
        assert DNSResilienceAnalyzer._score_to_risk(100.0) == RiskLevel.LOW
        assert DNSResilienceAnalyzer._score_to_risk(80.0) == RiskLevel.LOW
        assert DNSResilienceAnalyzer._score_to_risk(79.9) == RiskLevel.MEDIUM
        assert DNSResilienceAnalyzer._score_to_risk(60.0) == RiskLevel.MEDIUM
        assert DNSResilienceAnalyzer._score_to_risk(59.9) == RiskLevel.HIGH
        assert DNSResilienceAnalyzer._score_to_risk(30.0) == RiskLevel.HIGH
        assert DNSResilienceAnalyzer._score_to_risk(29.9) == RiskLevel.CRITICAL
        assert DNSResilienceAnalyzer._score_to_risk(0.0) == RiskLevel.CRITICAL

    def test_timestamp_present(self):
        """Report has a non-empty ISO timestamp."""
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[_zone("z1")])
        report = analyzer.analyze()
        assert report.timestamp != ""
        assert "T" in report.timestamp  # ISO format

    def test_multiple_zones(self):
        """Multiple zones produce per-zone assessments."""
        z1 = _zone("z1", providers=[_provider()], records=[_record(ttl=60)])
        z2 = _zone("z2", domain="other.com", providers=[_provider("p2")], records=[_record(ttl=3600)])
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z1, z2])
        report = analyzer.analyze()
        assert len(report.provider_assessments) == 2
        assert len(report.propagation_estimates) == 2
        assert len(report.ttl_assessments) == 2  # one record per zone


# ---------------------------------------------------------------------------
# Test: Recommendation compilation
# ---------------------------------------------------------------------------


class TestRecommendations:
    def test_recommendations_deduplicated(self):
        """Identical recommendations are not duplicated."""
        z = _zone(
            "z1",
            providers=[_provider()],
            records=[
                _record(name="r1", ttl=86400),
                _record(name="r2", ttl=86400),
            ],
            dnssec=DNSSECStatus.UNSIGNED,
            lb_strategy=LoadBalancingStrategy.NONE,
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        # Each recommendation should appear at most once
        assert len(report.recommendations) == len(set(report.recommendations))

    def test_ttl_medium_generates_recommendation(self):
        """MEDIUM TTL risk generates a reduce-TTL recommendation."""
        z = _zone(
            "z1",
            providers=[_provider()],
            records=[_record(name="slow", ttl=1800)],
        )
        g = _graph()
        analyzer = DNSResilienceAnalyzer(graph=g, zones=[z])
        report = analyzer.analyze()
        assert any("reduce TTL" in r for r in report.recommendations)


# ---------------------------------------------------------------------------
# Test: Dataclass defaults and enum values
# ---------------------------------------------------------------------------


class TestDataclassesAndEnums:
    def test_dns_provider_defaults(self):
        """DNSProvider dataclass defaults."""
        p = DNSProvider(provider_id="x", name="X")
        assert p.provider_type == DNSProviderType.CLOUD_MANAGED
        assert p.is_primary is True
        assert p.anycast_enabled is True

    def test_dns_record_defaults(self):
        """DNSRecord dataclass defaults."""
        r = DNSRecord(name="test")
        assert r.record_type == "A"
        assert r.ttl_seconds == 300
        assert r.values == []

    def test_dns_zone_defaults(self):
        """DNSZone dataclass defaults."""
        z = DNSZone(zone_id="z", domain="d.com")
        assert z.providers == []
        assert z.dnssec_status == DNSSECStatus.UNSIGNED
        assert z.zone_transfer_restricted is True

    def test_all_enums_have_values(self):
        """All enums have expected members."""
        assert len(DNSProviderType) == 4
        assert len(LoadBalancingStrategy) == 7
        assert len(DNSSECStatus) == 5
        assert len(ResolverType) == 6
        assert len(RiskLevel) == 5

    def test_report_default_fields(self):
        """DNSResilienceReport default values."""
        r = DNSResilienceReport()
        assert r.overall_score == 0.0
        assert r.risk_level == RiskLevel.LOW
        assert r.recommendations == []
        assert r.component_dns_risks == []
