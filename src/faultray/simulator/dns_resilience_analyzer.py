"""DNS Resilience Analyzer.

Analyzes DNS infrastructure resilience and failure scenarios across
distributed systems. Provides comprehensive assessment of:

- **Provider redundancy**: Multi-provider failover strategies, single-provider risk.
- **TTL analysis**: Cache behavior during failures, optimal TTL tuning.
- **Propagation delay modeling**: DNS change propagation timing estimates.
- **DNSSEC validation chain**: Signing chain integrity and expiry risk.
- **DNS-based load balancing**: GeoDNS, weighted, latency-based evaluation.
- **Failover timing**: Health check intervals, failover threshold analysis.
- **Amplification attack resistance**: Open resolver exposure, response-size risk.
- **Split-horizon DNS risk**: Internal/external view consistency assessment.
- **Dependency chain mapping**: NS delegation depth, CNAME chain analysis.
- **Resolver resilience**: Local cache, stub vs recursive, DoH/DoT readiness.
- **Zone transfer security**: AXFR/IXFR access control assessment.

Designed for commercial chaos engineering: helps teams understand how their
DNS topology behaves under failure conditions and quantify the risk of DNS
as a single point of failure.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DNSProviderType(str, Enum):
    """DNS hosting provider classification."""

    CLOUD_MANAGED = "cloud_managed"  # Route53, Cloud DNS, Azure DNS
    SELF_HOSTED = "self_hosted"  # BIND, PowerDNS, etc.
    THIRD_PARTY = "third_party"  # Cloudflare, NS1, Dyn
    HYBRID = "hybrid"  # Mix of providers


class LoadBalancingStrategy(str, Enum):
    """DNS-based load balancing strategy."""

    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"
    LATENCY_BASED = "latency_based"
    GEO_DNS = "geo_dns"
    FAILOVER = "failover"
    MULTI_VALUE = "multi_value"
    NONE = "none"


class DNSSECStatus(str, Enum):
    """DNSSEC validation chain status."""

    FULLY_SIGNED = "fully_signed"
    PARTIALLY_SIGNED = "partially_signed"
    UNSIGNED = "unsigned"
    EXPIRED = "expired"
    BROKEN_CHAIN = "broken_chain"


class ResolverType(str, Enum):
    """DNS resolver architecture type."""

    RECURSIVE = "recursive"
    STUB = "stub"
    FORWARDING = "forwarding"
    LOCAL_CACHE = "local_cache"
    DOH = "dns_over_https"
    DOT = "dns_over_tls"


class RiskLevel(str, Enum):
    """Qualitative risk level for DNS findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DNSProvider:
    """Configuration for a single DNS provider."""

    provider_id: str
    name: str
    provider_type: DNSProviderType = DNSProviderType.CLOUD_MANAGED
    is_primary: bool = True
    sla_percent: float = 99.99
    health_check_interval_seconds: float = 30.0
    failover_threshold: int = 3
    supports_dnssec: bool = True
    supports_geo_dns: bool = True
    anycast_enabled: bool = True
    max_qps: int = 100000


@dataclass
class DNSRecord:
    """Represents a DNS record for analysis."""

    name: str
    record_type: str = "A"  # A, AAAA, CNAME, NS, MX, SRV, TXT
    ttl_seconds: int = 300
    values: list[str] = field(default_factory=list)
    weight: float = 1.0
    health_check_enabled: bool = False
    failover_target: str = ""


@dataclass
class DNSZone:
    """A DNS zone configuration for analysis."""

    zone_id: str
    domain: str
    providers: list[DNSProvider] = field(default_factory=list)
    records: list[DNSRecord] = field(default_factory=list)
    dnssec_status: DNSSECStatus = DNSSECStatus.UNSIGNED
    dnssec_key_expiry_days: int = 365
    lb_strategy: LoadBalancingStrategy = LoadBalancingStrategy.NONE
    split_horizon_enabled: bool = False
    zone_transfer_restricted: bool = True
    ns_delegation_depth: int = 1


@dataclass
class TTLAssessment:
    """Assessment of TTL configuration impact during failures."""

    record_name: str
    current_ttl: int
    recommended_ttl: int
    failover_delay_seconds: float
    cache_staleness_risk: RiskLevel
    risk_description: str = ""


@dataclass
class PropagationEstimate:
    """Estimated DNS change propagation timing."""

    zone_id: str
    estimated_full_propagation_seconds: float
    estimated_partial_propagation_seconds: float
    ttl_bottleneck_record: str = ""
    bottleneck_ttl: int = 0
    risk_level: RiskLevel = RiskLevel.MEDIUM


@dataclass
class DNSSECAssessment:
    """DNSSEC validation chain analysis result."""

    zone_id: str
    status: DNSSECStatus
    chain_depth: int = 0
    key_expiry_days: int = 365
    risk_level: RiskLevel = RiskLevel.LOW
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FailoverTimingAssessment:
    """Assessment of DNS failover timing characteristics."""

    zone_id: str
    detection_time_seconds: float = 0.0
    propagation_time_seconds: float = 0.0
    total_failover_time_seconds: float = 0.0
    meets_rto: bool = True
    rto_target_seconds: float = 300.0
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class AmplificationRisk:
    """DNS amplification attack resistance assessment."""

    zone_id: str
    open_resolver_risk: bool = False
    max_response_amplification_factor: float = 1.0
    large_txt_records: int = 0
    large_any_responses: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SplitHorizonAssessment:
    """Split-horizon DNS risk analysis result."""

    zone_id: str
    is_enabled: bool = False
    consistency_risk: RiskLevel = RiskLevel.LOW
    internal_external_drift_risk: str = ""
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DependencyChainAssessment:
    """DNS dependency chain mapping result."""

    zone_id: str
    ns_delegation_depth: int = 0
    cname_chain_length: int = 0
    max_cname_depth: int = 0
    single_ns_risk: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ResolverAssessment:
    """DNS resolver resilience analysis."""

    resolver_type: ResolverType = ResolverType.RECURSIVE
    local_cache_enabled: bool = False
    encrypted_transport: bool = False
    redundant_resolvers: int = 1
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ZoneTransferAssessment:
    """Zone transfer security assessment."""

    zone_id: str
    transfer_restricted: bool = True
    tsig_enabled: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ProviderRedundancyAssessment:
    """DNS provider redundancy evaluation."""

    zone_id: str
    provider_count: int = 0
    has_failover: bool = False
    single_provider_risk: bool = True
    combined_sla_percent: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class LBEvaluation:
    """DNS-based load balancing evaluation result."""

    zone_id: str
    strategy: LoadBalancingStrategy = LoadBalancingStrategy.NONE
    health_check_coverage: float = 0.0
    failover_capable: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DNSResilienceReport:
    """Comprehensive DNS resilience analysis report."""

    timestamp: str = ""
    overall_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    provider_assessments: list[ProviderRedundancyAssessment] = field(
        default_factory=list
    )
    ttl_assessments: list[TTLAssessment] = field(default_factory=list)
    propagation_estimates: list[PropagationEstimate] = field(default_factory=list)
    dnssec_assessments: list[DNSSECAssessment] = field(default_factory=list)
    lb_evaluations: list[LBEvaluation] = field(default_factory=list)
    failover_assessments: list[FailoverTimingAssessment] = field(
        default_factory=list
    )
    amplification_risks: list[AmplificationRisk] = field(default_factory=list)
    split_horizon_assessments: list[SplitHorizonAssessment] = field(
        default_factory=list
    )
    dependency_chains: list[DependencyChainAssessment] = field(
        default_factory=list
    )
    resolver_assessments: list[ResolverAssessment] = field(default_factory=list)
    zone_transfer_assessments: list[ZoneTransferAssessment] = field(
        default_factory=list
    )
    recommendations: list[str] = field(default_factory=list)
    component_dns_risks: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DNSResilienceAnalyzer:
    """Analyze DNS infrastructure resilience across an ``InfraGraph``.

    The analyzer accepts an infrastructure graph and a list of DNS zone
    configurations, then evaluates each zone and the graph's DNS-type
    components to produce a comprehensive resilience report.

    Parameters
    ----------
    graph:
        The infrastructure dependency graph.
    zones:
        List of :class:`DNSZone` configurations to analyze.
    resolver:
        Optional :class:`ResolverAssessment` describing the resolver setup.
    rto_target_seconds:
        Target Recovery Time Objective for failover timing analysis.
    """

    def __init__(
        self,
        graph: InfraGraph,
        zones: Optional[list[DNSZone]] = None,
        resolver: Optional[ResolverAssessment] = None,
        rto_target_seconds: float = 300.0,
    ) -> None:
        self.graph = graph
        self.zones: list[DNSZone] = zones or []
        self.resolver = resolver
        self.rto_target_seconds = max(1.0, rto_target_seconds)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def analyze(self) -> DNSResilienceReport:
        """Run the full DNS resilience analysis and return a report."""
        now = datetime.now(timezone.utc).isoformat()

        provider_assessments: list[ProviderRedundancyAssessment] = []
        ttl_assessments: list[TTLAssessment] = []
        propagation_estimates: list[PropagationEstimate] = []
        dnssec_assessments: list[DNSSECAssessment] = []
        lb_evaluations: list[LBEvaluation] = []
        failover_assessments: list[FailoverTimingAssessment] = []
        amplification_risks: list[AmplificationRisk] = []
        split_horizon_assessments: list[SplitHorizonAssessment] = []
        dependency_chains: list[DependencyChainAssessment] = []
        zone_transfer_assessments: list[ZoneTransferAssessment] = []

        for zone in self.zones:
            provider_assessments.append(self._assess_provider_redundancy(zone))
            ttl_assessments.extend(self._assess_ttls(zone))
            propagation_estimates.append(self._estimate_propagation(zone))
            dnssec_assessments.append(self._assess_dnssec(zone))
            lb_evaluations.append(self._evaluate_load_balancing(zone))
            failover_assessments.append(self._assess_failover_timing(zone))
            amplification_risks.append(self._assess_amplification_risk(zone))
            split_horizon_assessments.append(self._assess_split_horizon(zone))
            dependency_chains.append(self._assess_dependency_chain(zone))
            zone_transfer_assessments.append(self._assess_zone_transfer(zone))

        resolver_assessments: list[ResolverAssessment] = []
        if self.resolver is not None:
            ra = self._assess_resolver(self.resolver)
            resolver_assessments.append(ra)

        component_dns_risks = self._assess_graph_dns_components()
        recommendations = self._compile_recommendations(
            provider_assessments,
            ttl_assessments,
            dnssec_assessments,
            failover_assessments,
            amplification_risks,
            split_horizon_assessments,
            dependency_chains,
            zone_transfer_assessments,
            resolver_assessments,
            component_dns_risks,
        )

        overall_score = self._calculate_overall_score(
            provider_assessments,
            ttl_assessments,
            dnssec_assessments,
            failover_assessments,
            amplification_risks,
            dependency_chains,
            zone_transfer_assessments,
            resolver_assessments,
            component_dns_risks,
        )
        overall_risk = self._score_to_risk(overall_score)

        return DNSResilienceReport(
            timestamp=now,
            overall_score=round(overall_score, 2),
            risk_level=overall_risk,
            provider_assessments=provider_assessments,
            ttl_assessments=ttl_assessments,
            propagation_estimates=propagation_estimates,
            dnssec_assessments=dnssec_assessments,
            lb_evaluations=lb_evaluations,
            failover_assessments=failover_assessments,
            amplification_risks=amplification_risks,
            split_horizon_assessments=split_horizon_assessments,
            dependency_chains=dependency_chains,
            resolver_assessments=resolver_assessments,
            zone_transfer_assessments=zone_transfer_assessments,
            recommendations=recommendations,
            component_dns_risks=component_dns_risks,
        )

    def analyze_zone(self, zone_id: str) -> DNSResilienceReport | None:
        """Analyze a single zone by its ID. Returns ``None`` if not found."""
        for z in self.zones:
            if z.zone_id == zone_id:
                temp = DNSResilienceAnalyzer(
                    graph=self.graph,
                    zones=[z],
                    resolver=self.resolver,
                    rto_target_seconds=self.rto_target_seconds,
                )
                return temp.analyze()
        return None

    def assess_failover_readiness(self, zone_id: str) -> FailoverTimingAssessment:
        """Assess failover readiness for a specific zone."""
        for z in self.zones:
            if z.zone_id == zone_id:
                return self._assess_failover_timing(z)
        return FailoverTimingAssessment(
            zone_id=zone_id,
            risk_level=RiskLevel.HIGH,
            recommendations=[f"Zone '{zone_id}' not found in configuration."],
        )

    def estimate_propagation_delay(self, zone_id: str) -> PropagationEstimate:
        """Estimate DNS propagation delay for a specific zone."""
        for z in self.zones:
            if z.zone_id == zone_id:
                return self._estimate_propagation(z)
        return PropagationEstimate(
            zone_id=zone_id,
            estimated_full_propagation_seconds=0.0,
            estimated_partial_propagation_seconds=0.0,
            risk_level=RiskLevel.HIGH,
        )

    # -----------------------------------------------------------------
    # Provider redundancy assessment
    # -----------------------------------------------------------------

    def _assess_provider_redundancy(
        self, zone: DNSZone
    ) -> ProviderRedundancyAssessment:
        """Evaluate DNS provider redundancy for a zone."""
        providers = zone.providers
        count = len(providers)
        if count == 0:
            return ProviderRedundancyAssessment(
                zone_id=zone.zone_id,
                provider_count=0,
                has_failover=False,
                single_provider_risk=True,
                combined_sla_percent=0.0,
                risk_level=RiskLevel.CRITICAL,
                recommendations=[
                    f"Zone '{zone.domain}' has no DNS providers configured. "
                    "Add at least one provider."
                ],
            )

        has_failover = any(not p.is_primary for p in providers)
        single_risk = count < 2

        # Combined SLA: 1 - product(1 - sla_i) for independent providers
        if count == 1:
            combined_sla = providers[0].sla_percent
        else:
            failure_prob = 1.0
            for p in providers:
                failure_prob *= 1.0 - (p.sla_percent / 100.0)
            combined_sla = (1.0 - failure_prob) * 100.0

        if single_risk:
            risk = RiskLevel.HIGH
            recs = [
                f"Zone '{zone.domain}' relies on a single DNS provider. "
                "Add a secondary provider for redundancy."
            ]
        elif not has_failover:
            risk = RiskLevel.MEDIUM
            recs = [
                f"Zone '{zone.domain}' has multiple providers but no "
                "failover configuration. Enable health-check failover."
            ]
        else:
            risk = RiskLevel.LOW
            recs = []

        return ProviderRedundancyAssessment(
            zone_id=zone.zone_id,
            provider_count=count,
            has_failover=has_failover,
            single_provider_risk=single_risk,
            combined_sla_percent=round(combined_sla, 6),
            risk_level=risk,
            recommendations=recs,
        )

    # -----------------------------------------------------------------
    # TTL analysis
    # -----------------------------------------------------------------

    def _assess_ttls(self, zone: DNSZone) -> list[TTLAssessment]:
        """Assess TTL configurations for all records in a zone."""
        assessments: list[TTLAssessment] = []
        for rec in zone.records:
            failover_delay = float(rec.ttl_seconds)
            if rec.ttl_seconds <= 30:
                recommended = rec.ttl_seconds
                risk = RiskLevel.LOW
                desc = "Low TTL allows rapid failover."
            elif rec.ttl_seconds <= 300:
                recommended = 60
                risk = RiskLevel.LOW
                desc = "Moderate TTL; failover within 5 minutes."
            elif rec.ttl_seconds <= 3600:
                recommended = 300
                risk = RiskLevel.MEDIUM
                desc = (
                    "High TTL may delay failover by up to "
                    f"{rec.ttl_seconds} seconds."
                )
            else:
                recommended = 300
                risk = RiskLevel.HIGH
                desc = (
                    f"Very high TTL ({rec.ttl_seconds}s) causes extended "
                    "cache staleness during failures."
                )
            assessments.append(
                TTLAssessment(
                    record_name=rec.name,
                    current_ttl=rec.ttl_seconds,
                    recommended_ttl=recommended,
                    failover_delay_seconds=failover_delay,
                    cache_staleness_risk=risk,
                    risk_description=desc,
                )
            )
        return assessments

    # -----------------------------------------------------------------
    # Propagation delay modeling
    # -----------------------------------------------------------------

    def _estimate_propagation(self, zone: DNSZone) -> PropagationEstimate:
        """Model DNS propagation delay based on TTLs and delegation depth."""
        if not zone.records:
            return PropagationEstimate(
                zone_id=zone.zone_id,
                estimated_full_propagation_seconds=0.0,
                estimated_partial_propagation_seconds=0.0,
                risk_level=RiskLevel.INFO,
            )

        max_ttl = max(r.ttl_seconds for r in zone.records)
        min_ttl = min(r.ttl_seconds for r in zone.records)
        bottleneck_rec = max(zone.records, key=lambda r: r.ttl_seconds)

        # Full propagation is limited by the longest TTL plus delegation
        # overhead (each delegation level adds ~10% overhead).
        delegation_factor = 1.0 + (zone.ns_delegation_depth - 1) * 0.1
        full_prop = float(max_ttl) * delegation_factor
        partial_prop = float(min_ttl) * delegation_factor

        if full_prop > 3600:
            risk = RiskLevel.HIGH
        elif full_prop > 600:
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        return PropagationEstimate(
            zone_id=zone.zone_id,
            estimated_full_propagation_seconds=round(full_prop, 2),
            estimated_partial_propagation_seconds=round(partial_prop, 2),
            ttl_bottleneck_record=bottleneck_rec.name,
            bottleneck_ttl=bottleneck_rec.ttl_seconds,
            risk_level=risk,
        )

    # -----------------------------------------------------------------
    # DNSSEC validation chain
    # -----------------------------------------------------------------

    def _assess_dnssec(self, zone: DNSZone) -> DNSSECAssessment:
        """Analyze DNSSEC signing chain and key expiry risk."""
        issues: list[str] = []
        recs: list[str] = []

        if zone.dnssec_status == DNSSECStatus.UNSIGNED:
            issues.append("Zone is not signed with DNSSEC.")
            recs.append(
                f"Enable DNSSEC for zone '{zone.domain}' to prevent "
                "cache poisoning and spoofing attacks."
            )
            risk = RiskLevel.MEDIUM
        elif zone.dnssec_status == DNSSECStatus.EXPIRED:
            issues.append("DNSSEC keys have expired.")
            recs.append("Rotate DNSSEC keys immediately to restore validation.")
            risk = RiskLevel.CRITICAL
        elif zone.dnssec_status == DNSSECStatus.BROKEN_CHAIN:
            issues.append("DNSSEC chain of trust is broken.")
            recs.append(
                "Fix the DS/DNSKEY chain. Broken DNSSEC causes resolution "
                "failures for validating resolvers."
            )
            risk = RiskLevel.CRITICAL
        elif zone.dnssec_status == DNSSECStatus.PARTIALLY_SIGNED:
            issues.append("Not all records are covered by DNSSEC signatures.")
            recs.append("Ensure all record types are signed to get full protection.")
            risk = RiskLevel.MEDIUM
        else:
            risk = RiskLevel.LOW

        # Key expiry check
        if zone.dnssec_key_expiry_days <= 7:
            issues.append(
                f"DNSSEC key expires in {zone.dnssec_key_expiry_days} day(s)."
            )
            recs.append("Rotate DNSSEC keys urgently; expiry imminent.")
            risk = RiskLevel.CRITICAL
        elif zone.dnssec_key_expiry_days <= 30:
            issues.append(
                f"DNSSEC key expires in {zone.dnssec_key_expiry_days} days."
            )
            recs.append("Schedule DNSSEC key rotation soon.")
            if risk not in (RiskLevel.CRITICAL,):
                risk = RiskLevel.HIGH

        chain_depth = zone.ns_delegation_depth + (
            1 if zone.dnssec_status == DNSSECStatus.FULLY_SIGNED else 0
        )

        return DNSSECAssessment(
            zone_id=zone.zone_id,
            status=zone.dnssec_status,
            chain_depth=chain_depth,
            key_expiry_days=zone.dnssec_key_expiry_days,
            risk_level=risk,
            issues=issues,
            recommendations=recs,
        )

    # -----------------------------------------------------------------
    # Load balancing evaluation
    # -----------------------------------------------------------------

    def _evaluate_load_balancing(self, zone: DNSZone) -> LBEvaluation:
        """Evaluate DNS-based load balancing configuration."""
        strategy = zone.lb_strategy
        records_with_health = sum(
            1 for r in zone.records if r.health_check_enabled
        )
        total = len(zone.records) or 1
        health_coverage = records_with_health / total

        failover_capable = (
            strategy == LoadBalancingStrategy.FAILOVER
            or health_coverage > 0.5
        )

        recs: list[str] = []
        if strategy == LoadBalancingStrategy.NONE:
            risk = RiskLevel.HIGH
            recs.append(
                f"Zone '{zone.domain}' has no DNS load balancing. Consider "
                "enabling weighted or failover routing."
            )
        elif health_coverage < 0.5:
            risk = RiskLevel.MEDIUM
            recs.append(
                "Less than 50% of records have health checks. Enable health "
                "checks for better failover reliability."
            )
        else:
            risk = RiskLevel.LOW

        return LBEvaluation(
            zone_id=zone.zone_id,
            strategy=strategy,
            health_check_coverage=round(health_coverage, 4),
            failover_capable=failover_capable,
            risk_level=risk,
            recommendations=recs,
        )

    # -----------------------------------------------------------------
    # Failover timing
    # -----------------------------------------------------------------

    def _assess_failover_timing(self, zone: DNSZone) -> FailoverTimingAssessment:
        """Analyze DNS failover timing against RTO targets."""
        recs: list[str] = []

        # Detection time: worst-case is health_check_interval * threshold
        if zone.providers:
            detection_times = []
            for p in zone.providers:
                dt = p.health_check_interval_seconds * p.failover_threshold
                detection_times.append(dt)
            detection = max(detection_times)
        else:
            detection = 0.0

        # Propagation time is dominated by the longest record TTL
        if zone.records:
            max_ttl = max(r.ttl_seconds for r in zone.records)
            propagation = float(max_ttl)
        else:
            propagation = 0.0

        total = detection + propagation
        meets_rto = total <= self.rto_target_seconds

        if not meets_rto:
            risk = RiskLevel.HIGH
            recs.append(
                f"Total failover time ({total:.0f}s) exceeds RTO target "
                f"({self.rto_target_seconds:.0f}s). Reduce TTLs or health "
                "check intervals."
            )
        elif total > self.rto_target_seconds * 0.8:
            risk = RiskLevel.MEDIUM
            recs.append(
                "Failover time is close to RTO target. Consider reducing "
                "TTLs for more headroom."
            )
        else:
            risk = RiskLevel.LOW

        if not zone.providers:
            risk = RiskLevel.HIGH
            recs.append("No providers configured; failover is impossible.")

        return FailoverTimingAssessment(
            zone_id=zone.zone_id,
            detection_time_seconds=round(detection, 2),
            propagation_time_seconds=round(propagation, 2),
            total_failover_time_seconds=round(total, 2),
            meets_rto=meets_rto,
            rto_target_seconds=self.rto_target_seconds,
            risk_level=risk,
            recommendations=recs,
        )

    # -----------------------------------------------------------------
    # Amplification attack resistance
    # -----------------------------------------------------------------

    def _assess_amplification_risk(self, zone: DNSZone) -> AmplificationRisk:
        """Assess DNS amplification attack resistance."""
        recs: list[str] = []

        # Check for open resolver risk (self-hosted without anycast are riskier)
        open_resolver = False
        for p in zone.providers:
            if p.provider_type == DNSProviderType.SELF_HOSTED and not p.anycast_enabled:
                open_resolver = True

        # Check for large TXT records that could amplify responses
        large_txt = sum(
            1
            for r in zone.records
            if r.record_type == "TXT" and len(",".join(r.values)) > 255
        )

        # Check ANY query response size risk
        total_records = len(zone.records)
        large_any = total_records > 20

        # Calculate amplification factor estimate
        avg_response_size = 0.0
        if zone.records:
            sizes = []
            for r in zone.records:
                val_len = sum(len(v) for v in r.values) if r.values else 40
                sizes.append(12 + val_len)  # 12 bytes overhead per record
            avg_response_size = sum(sizes) / len(sizes)
        query_size = 40.0  # typical DNS query size
        amplification = (
            avg_response_size / query_size if query_size > 0 else 1.0
        )

        if open_resolver:
            risk = RiskLevel.HIGH
            recs.append(
                "Self-hosted DNS without anycast is vulnerable to "
                "amplification attacks. Enable anycast or rate limiting."
            )
        elif large_txt > 0 or large_any:
            risk = RiskLevel.MEDIUM
            if large_txt > 0:
                recs.append(
                    f"{large_txt} large TXT record(s) detected. These increase "
                    "amplification factor."
                )
            if large_any:
                recs.append(
                    "Zone has many records; ANY query responses are large. "
                    "Consider disabling ANY query support."
                )
        else:
            risk = RiskLevel.LOW

        return AmplificationRisk(
            zone_id=zone.zone_id,
            open_resolver_risk=open_resolver,
            max_response_amplification_factor=round(amplification, 2),
            large_txt_records=large_txt,
            large_any_responses=large_any,
            risk_level=risk,
            recommendations=recs,
        )

    # -----------------------------------------------------------------
    # Split-horizon DNS risk
    # -----------------------------------------------------------------

    def _assess_split_horizon(self, zone: DNSZone) -> SplitHorizonAssessment:
        """Analyze split-horizon DNS configuration risks."""
        recs: list[str] = []
        if not zone.split_horizon_enabled:
            return SplitHorizonAssessment(
                zone_id=zone.zone_id,
                is_enabled=False,
                consistency_risk=RiskLevel.INFO,
                internal_external_drift_risk="Not applicable; split-horizon disabled.",
                recommendations=[],
            )

        # Split-horizon is enabled; assess risks
        drift_risk = (
            "Internal and external views may drift apart over time, "
            "causing inconsistent behavior for VPN users or hybrid clients."
        )
        recs.append(
            "Regularly audit internal/external views for consistency. "
            "Consider automated drift detection."
        )
        recs.append(
            "Document which records differ between views to aid "
            "incident response."
        )
        risk = RiskLevel.MEDIUM

        return SplitHorizonAssessment(
            zone_id=zone.zone_id,
            is_enabled=True,
            consistency_risk=risk,
            internal_external_drift_risk=drift_risk,
            recommendations=recs,
        )

    # -----------------------------------------------------------------
    # Dependency chain mapping
    # -----------------------------------------------------------------

    def _assess_dependency_chain(self, zone: DNSZone) -> DependencyChainAssessment:
        """Map NS delegation depth and CNAME chain length."""
        recs: list[str] = []

        # Count CNAME chains (CNAME pointing to CNAME)
        cname_records = [
            r for r in zone.records if r.record_type == "CNAME"
        ]
        cname_targets = {r.name: r.values[0] if r.values else "" for r in cname_records}
        max_chain = 0
        for start in cname_targets:
            chain_len = 0
            current = start
            visited: set[str] = set()
            while current in cname_targets and current not in visited:
                visited.add(current)
                current = cname_targets[current]
                chain_len += 1
            max_chain = max(max_chain, chain_len)

        ns_depth = zone.ns_delegation_depth
        single_ns = len(zone.providers) < 2

        if max_chain > 3:
            risk = RiskLevel.HIGH
            recs.append(
                f"CNAME chain depth of {max_chain} detected. Deep chains "
                "increase latency and failure probability."
            )
        elif ns_depth > 3:
            risk = RiskLevel.MEDIUM
            recs.append(
                f"NS delegation depth of {ns_depth} increases resolution "
                "latency and failure surface."
            )
        elif single_ns:
            risk = RiskLevel.MEDIUM
            recs.append(
                "Single NS provider is a single point of failure for "
                "DNS resolution."
            )
        else:
            risk = RiskLevel.LOW

        return DependencyChainAssessment(
            zone_id=zone.zone_id,
            ns_delegation_depth=ns_depth,
            cname_chain_length=len(cname_records),
            max_cname_depth=max_chain,
            single_ns_risk=single_ns,
            risk_level=risk,
            recommendations=recs,
        )

    # -----------------------------------------------------------------
    # Resolver resilience
    # -----------------------------------------------------------------

    def _assess_resolver(self, resolver: ResolverAssessment) -> ResolverAssessment:
        """Analyze resolver resilience and return an enriched assessment."""
        recs: list[str] = []
        risk = RiskLevel.LOW

        if not resolver.local_cache_enabled:
            recs.append(
                "Enable local DNS caching to survive upstream resolver "
                "outages."
            )
            risk = RiskLevel.MEDIUM

        if not resolver.encrypted_transport:
            recs.append(
                "DNS queries are unencrypted. Consider DoH or DoT for "
                "privacy and integrity."
            )
            if risk != RiskLevel.HIGH:
                risk = RiskLevel.MEDIUM

        if resolver.redundant_resolvers < 2:
            recs.append(
                "Only one resolver configured. Add redundant resolvers "
                "to avoid a DNS SPOF."
            )
            risk = RiskLevel.HIGH

        return ResolverAssessment(
            resolver_type=resolver.resolver_type,
            local_cache_enabled=resolver.local_cache_enabled,
            encrypted_transport=resolver.encrypted_transport,
            redundant_resolvers=resolver.redundant_resolvers,
            risk_level=risk,
            recommendations=recs,
        )

    # -----------------------------------------------------------------
    # Zone transfer security
    # -----------------------------------------------------------------

    def _assess_zone_transfer(self, zone: DNSZone) -> ZoneTransferAssessment:
        """Assess zone transfer (AXFR/IXFR) security."""
        recs: list[str] = []

        if not zone.zone_transfer_restricted:
            risk = RiskLevel.HIGH
            recs.append(
                f"Zone '{zone.domain}' allows unrestricted zone transfers. "
                "Restrict AXFR/IXFR to authorized secondary servers only."
            )
            recs.append(
                "Enable TSIG authentication for zone transfers."
            )
        else:
            risk = RiskLevel.LOW

        # Check for TSIG across providers
        tsig = any(
            p.provider_type == DNSProviderType.CLOUD_MANAGED
            for p in zone.providers
        )

        return ZoneTransferAssessment(
            zone_id=zone.zone_id,
            transfer_restricted=zone.zone_transfer_restricted,
            tsig_enabled=tsig,
            risk_level=risk,
            recommendations=recs,
        )

    # -----------------------------------------------------------------
    # Graph-level DNS component analysis
    # -----------------------------------------------------------------

    def _assess_graph_dns_components(self) -> list[dict]:
        """Check DNS-typed components in the infrastructure graph."""
        risks: list[dict] = []
        for cid, comp in self.graph.components.items():
            if comp.type == ComponentType.DNS:
                dependents = self.graph.get_dependents(cid)
                is_spof = comp.replicas <= 1 and len(dependents) > 0
                health_ok = comp.health == HealthStatus.HEALTHY

                risk_level = RiskLevel.LOW
                recs: list[str] = []
                if is_spof:
                    risk_level = RiskLevel.HIGH
                    recs.append(
                        f"DNS component '{comp.name}' is a single point of "
                        f"failure with {len(dependents)} dependent(s). "
                        "Add replicas or failover."
                    )
                if not health_ok:
                    risk_level = RiskLevel.CRITICAL
                    recs.append(
                        f"DNS component '{comp.name}' is not healthy "
                        f"(status={comp.health.value}). Investigate immediately."
                    )
                if not comp.failover.enabled and len(dependents) > 0:
                    if risk_level == RiskLevel.LOW:
                        risk_level = RiskLevel.MEDIUM
                    recs.append(
                        f"Enable failover for DNS component '{comp.name}'."
                    )

                risks.append(
                    {
                        "component_id": cid,
                        "component_name": comp.name,
                        "is_spof": is_spof,
                        "health": comp.health.value,
                        "dependents": len(dependents),
                        "replicas": comp.replicas,
                        "risk_level": risk_level.value,
                        "recommendations": recs,
                    }
                )
        return risks

    # -----------------------------------------------------------------
    # Scoring
    # -----------------------------------------------------------------

    def _calculate_overall_score(
        self,
        providers: list[ProviderRedundancyAssessment],
        ttls: list[TTLAssessment],
        dnssec: list[DNSSECAssessment],
        failovers: list[FailoverTimingAssessment],
        amplifications: list[AmplificationRisk],
        dep_chains: list[DependencyChainAssessment],
        zone_transfers: list[ZoneTransferAssessment],
        resolvers: list[ResolverAssessment],
        component_risks: list[dict],
    ) -> float:
        """Calculate overall DNS resilience score (0-100).

        Weighted categories:
        - Provider redundancy: 20%
        - TTL / failover timing: 15%
        - DNSSEC: 10%
        - Amplification resistance: 10%
        - Dependency chains: 10%
        - Zone transfer security: 10%
        - Resolver resilience: 10%
        - Component health: 15%
        """
        if not self.zones and not component_risks:
            return 0.0

        def _risk_to_score(risk: RiskLevel) -> float:
            return {
                RiskLevel.CRITICAL: 0.0,
                RiskLevel.HIGH: 25.0,
                RiskLevel.MEDIUM: 60.0,
                RiskLevel.LOW: 90.0,
                RiskLevel.INFO: 100.0,
            }.get(risk, 50.0)

        def _avg_risk_score(risks: list[RiskLevel]) -> float:
            if not risks:
                return 100.0
            return sum(_risk_to_score(r) for r in risks) / len(risks)

        provider_score = _avg_risk_score([p.risk_level for p in providers])
        ttl_score = _avg_risk_score([t.cache_staleness_risk for t in ttls])
        dnssec_score = _avg_risk_score([d.risk_level for d in dnssec])
        failover_score = _avg_risk_score([f.risk_level for f in failovers])
        amp_score = _avg_risk_score([a.risk_level for a in amplifications])
        chain_score = _avg_risk_score([c.risk_level for c in dep_chains])
        zt_score = _avg_risk_score([z.risk_level for z in zone_transfers])
        resolver_score = _avg_risk_score([r.risk_level for r in resolvers])
        comp_score = _avg_risk_score(
            [RiskLevel(cr["risk_level"]) for cr in component_risks]
        )

        total = (
            provider_score * 0.20
            + ttl_score * 0.10
            + failover_score * 0.10
            + dnssec_score * 0.10
            + amp_score * 0.10
            + chain_score * 0.10
            + zt_score * 0.10
            + resolver_score * 0.10
            + comp_score * 0.10
        )
        return min(100.0, max(0.0, total))

    @staticmethod
    def _score_to_risk(score: float) -> RiskLevel:
        """Map numeric score to qualitative risk level."""
        if score >= 80.0:
            return RiskLevel.LOW
        if score >= 60.0:
            return RiskLevel.MEDIUM
        if score >= 30.0:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    # -----------------------------------------------------------------
    # Recommendation compilation
    # -----------------------------------------------------------------

    def _compile_recommendations(
        self,
        providers: list[ProviderRedundancyAssessment],
        ttls: list[TTLAssessment],
        dnssec: list[DNSSECAssessment],
        failovers: list[FailoverTimingAssessment],
        amplifications: list[AmplificationRisk],
        split_horizons: list[SplitHorizonAssessment],
        dep_chains: list[DependencyChainAssessment],
        zone_transfers: list[ZoneTransferAssessment],
        resolvers: list[ResolverAssessment],
        component_risks: list[dict],
    ) -> list[str]:
        """Compile all unique recommendations across assessments."""
        all_recs: list[str] = []

        for p in providers:
            all_recs.extend(p.recommendations)
        for t in ttls:
            if t.cache_staleness_risk in (RiskLevel.HIGH, RiskLevel.MEDIUM):
                all_recs.append(
                    f"Record '{t.record_name}': reduce TTL from "
                    f"{t.current_ttl}s to {t.recommended_ttl}s for faster failover."
                )
        for d in dnssec:
            all_recs.extend(d.recommendations)
        for f in failovers:
            all_recs.extend(f.recommendations)
        for a in amplifications:
            all_recs.extend(a.recommendations)
        for s in split_horizons:
            all_recs.extend(s.recommendations)
        for c in dep_chains:
            all_recs.extend(c.recommendations)
        for z in zone_transfers:
            all_recs.extend(z.recommendations)
        for r in resolvers:
            all_recs.extend(r.recommendations)
        for cr in component_risks:
            all_recs.extend(cr.get("recommendations", []))

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for rec in all_recs:
            if rec not in seen:
                seen.add(rec)
                unique.append(rec)
        return unique
