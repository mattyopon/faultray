"""DNS Resilience Simulator.

Simulates DNS failure scenarios and analyzes DNS infrastructure resilience.
Covers resolution failures, propagation delays, TTL strategies, cache
poisoning, provider outages, DNSSEC validation, and multi-provider failover.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DNSFailureType(str, Enum):
    """Types of DNS failure scenarios."""

    RESOLUTION_FAILURE = "resolution_failure"
    PROPAGATION_DELAY = "propagation_delay"
    TTL_EXPIRY = "ttl_expiry"
    CACHE_POISONING = "cache_poisoning"
    PROVIDER_OUTAGE = "provider_outage"
    ZONE_TRANSFER_FAILURE = "zone_transfer_failure"
    DNSSEC_VALIDATION_FAILURE = "dnssec_validation_failure"
    RECURSIVE_RESOLVER_FAILURE = "recursive_resolver_failure"
    AUTHORITATIVE_SERVER_FAILURE = "authoritative_server_failure"
    DDOS_AMPLIFICATION = "ddos_amplification"


class DNSRecordType(str, Enum):
    """Supported DNS record types."""

    A = "a"
    AAAA = "aaaa"
    CNAME = "cname"
    MX = "mx"
    TXT = "txt"
    SRV = "srv"
    NS = "ns"
    SOA = "soa"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class DNSConfig(BaseModel):
    """Configuration describing the DNS infrastructure."""

    provider: str = "default"
    ttl_seconds: int = Field(default=300, ge=1)
    records: list[str] = Field(default_factory=list)
    failover_provider: str = ""
    dnssec_enabled: bool = False
    health_check_enabled: bool = False
    multi_provider: bool = False


class DNSFailureImpact(BaseModel):
    """Impact assessment of a DNS failure scenario."""

    failure_type: DNSFailureType
    affected_services: list[str] = Field(default_factory=list)
    resolution_time_seconds: float = Field(default=0.0, ge=0.0)
    cache_protection_seconds: float = Field(default=0.0, ge=0.0)
    user_impact_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class DNSResilienceReport(BaseModel):
    """Full DNS resilience assessment report."""

    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    single_points_of_failure: list[str] = Field(default_factory=list)
    failure_impacts: list[DNSFailureImpact] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    timestamp: str = ""


class TTLAnalysis(BaseModel):
    """Analysis of DNS TTL strategy."""

    current_ttl: int = 0
    recommended_ttl: int = 300
    ttl_risk_level: str = "low"
    cache_effectiveness: float = Field(default=0.0, ge=0.0, le=100.0)
    propagation_delay_seconds: float = Field(default=0.0, ge=0.0)
    recommendations: list[str] = Field(default_factory=list)


class ProviderFailoverResult(BaseModel):
    """Result of simulating a DNS provider failover."""

    primary_provider: str = ""
    failover_provider: str = ""
    failover_time_seconds: float = Field(default=0.0, ge=0.0)
    records_affected: int = 0
    data_loss_possible: bool = False
    seamless: bool = False
    recommendations: list[str] = Field(default_factory=list)


class BlastRadiusResult(BaseModel):
    """Result of estimating DNS outage blast radius."""

    total_services: int = 0
    affected_services: list[str] = Field(default_factory=list)
    affected_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    critical_services_affected: list[str] = Field(default_factory=list)
    estimated_downtime_seconds: float = Field(default=0.0, ge=0.0)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FAILURE_BASE_IMPACT: dict[DNSFailureType, float] = {
    DNSFailureType.RESOLUTION_FAILURE: 90.0,
    DNSFailureType.PROPAGATION_DELAY: 30.0,
    DNSFailureType.TTL_EXPIRY: 40.0,
    DNSFailureType.CACHE_POISONING: 85.0,
    DNSFailureType.PROVIDER_OUTAGE: 95.0,
    DNSFailureType.ZONE_TRANSFER_FAILURE: 50.0,
    DNSFailureType.DNSSEC_VALIDATION_FAILURE: 70.0,
    DNSFailureType.RECURSIVE_RESOLVER_FAILURE: 75.0,
    DNSFailureType.AUTHORITATIVE_SERVER_FAILURE: 80.0,
    DNSFailureType.DDOS_AMPLIFICATION: 60.0,
}

# Typical resolution times per failure type (seconds)
_BASE_RESOLUTION_TIME: dict[DNSFailureType, float] = {
    DNSFailureType.RESOLUTION_FAILURE: 300.0,
    DNSFailureType.PROPAGATION_DELAY: 600.0,
    DNSFailureType.TTL_EXPIRY: 120.0,
    DNSFailureType.CACHE_POISONING: 1800.0,
    DNSFailureType.PROVIDER_OUTAGE: 3600.0,
    DNSFailureType.ZONE_TRANSFER_FAILURE: 900.0,
    DNSFailureType.DNSSEC_VALIDATION_FAILURE: 600.0,
    DNSFailureType.RECURSIVE_RESOLVER_FAILURE: 180.0,
    DNSFailureType.AUTHORITATIVE_SERVER_FAILURE: 1200.0,
    DNSFailureType.DDOS_AMPLIFICATION: 900.0,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp a value between lo and hi."""
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DNSResilienceEngine:
    """Stateless engine for DNS resilience analysis and failure simulation."""

    # -- full resilience assessment -----------------------------------------

    def assess_dns_resilience(
        self,
        graph: InfraGraph,
        dns_config: DNSConfig,
    ) -> DNSResilienceReport:
        """Perform a comprehensive DNS resilience assessment."""
        spofs = self.detect_dns_single_points(graph, dns_config)
        recommendations: list[str] = []
        impacts: list[DNSFailureImpact] = []

        # Simulate all failure types
        for ft in DNSFailureType:
            impact = self.simulate_dns_failure(graph, ft, dns_config)
            impacts.append(impact)

        # Score calculation
        score = 100.0

        # Penalise for single points of failure
        score -= len(spofs) * 15.0

        # Penalise for lack of DNSSEC
        if not dns_config.dnssec_enabled:
            score -= 10.0
            recommendations.append("Enable DNSSEC to protect against cache poisoning")

        # Penalise for lack of health checks
        if not dns_config.health_check_enabled:
            score -= 10.0
            recommendations.append(
                "Enable DNS health checks for automatic failover"
            )

        # Penalise for no failover provider
        if not dns_config.failover_provider:
            score -= 15.0
            recommendations.append(
                "Configure a failover DNS provider for redundancy"
            )

        # Penalise for no multi-provider
        if not dns_config.multi_provider:
            score -= 5.0
            recommendations.append(
                "Use multi-provider DNS for higher availability"
            )

        # TTL penalties
        if dns_config.ttl_seconds > 3600:
            score -= 5.0
            recommendations.append(
                "Reduce TTL to speed up failover propagation"
            )
        elif dns_config.ttl_seconds < 30:
            score -= 5.0
            recommendations.append(
                "TTL is very low; this increases DNS query load"
            )

        # High-impact failure bonus/penalty
        critical_impacts = [
            imp for imp in impacts if imp.user_impact_percent > 50.0
        ]
        score -= len(critical_impacts) * 3.0

        # SPOF recommendations
        for spof in spofs:
            recommendations.append(f"Eliminate single point of failure: {spof}")

        score = _clamp(score)

        return DNSResilienceReport(
            overall_score=round(score, 2),
            single_points_of_failure=spofs,
            failure_impacts=impacts,
            recommendations=recommendations,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # -- single failure simulation -----------------------------------------

    def simulate_dns_failure(
        self,
        graph: InfraGraph,
        failure_type: DNSFailureType,
        config: DNSConfig,
    ) -> DNSFailureImpact:
        """Simulate a single DNS failure scenario."""
        base_impact = _FAILURE_BASE_IMPACT[failure_type]
        base_resolution = _BASE_RESOLUTION_TIME[failure_type]
        component_ids = list(graph.components.keys())
        recommendations: list[str] = []

        user_impact = base_impact
        resolution_time = base_resolution
        cache_protection = float(config.ttl_seconds)

        if failure_type == DNSFailureType.RESOLUTION_FAILURE:
            if config.multi_provider:
                user_impact *= 0.3
                resolution_time *= 0.4
            if config.health_check_enabled:
                resolution_time *= 0.5
            recommendations.append("Configure multiple resolvers for redundancy")
            recommendations.append("Implement client-side DNS caching")

        elif failure_type == DNSFailureType.PROPAGATION_DELAY:
            # Impact scales with TTL
            if config.ttl_seconds <= 60:
                user_impact *= 0.5
                resolution_time *= 0.3
            elif config.ttl_seconds <= 300:
                user_impact *= 0.7
                resolution_time *= 0.6
            else:
                user_impact *= 1.0
                resolution_time = float(config.ttl_seconds)
            recommendations.append("Use lower TTL values during planned changes")
            recommendations.append("Pre-warm DNS caches before migrations")

        elif failure_type == DNSFailureType.TTL_EXPIRY:
            cache_protection = 0.0
            if config.health_check_enabled:
                user_impact *= 0.6
                resolution_time *= 0.5
            recommendations.append("Set appropriate TTL values for your use case")
            recommendations.append("Implement DNS cache with stale-if-error support")

        elif failure_type == DNSFailureType.CACHE_POISONING:
            if config.dnssec_enabled:
                user_impact *= 0.1
                resolution_time *= 0.2
            else:
                recommendations.append("Enable DNSSEC to prevent cache poisoning")
            recommendations.append("Use DNS-over-HTTPS or DNS-over-TLS")

        elif failure_type == DNSFailureType.PROVIDER_OUTAGE:
            if config.multi_provider:
                user_impact *= 0.2
                resolution_time *= 0.3
            elif config.failover_provider:
                user_impact *= 0.4
                resolution_time *= 0.5
            recommendations.append("Use multi-provider DNS architecture")
            if not config.failover_provider:
                recommendations.append("Configure a failover DNS provider")

        elif failure_type == DNSFailureType.ZONE_TRANSFER_FAILURE:
            if config.multi_provider:
                user_impact *= 0.5
                resolution_time *= 0.6
            recommendations.append("Monitor zone transfer status regularly")
            recommendations.append("Configure zone transfer alerts")

        elif failure_type == DNSFailureType.DNSSEC_VALIDATION_FAILURE:
            if not config.dnssec_enabled:
                user_impact *= 0.1  # not using DNSSEC, so no direct impact
            else:
                recommendations.append("Automate DNSSEC key rotation")
            recommendations.append("Monitor DNSSEC validation status")

        elif failure_type == DNSFailureType.RECURSIVE_RESOLVER_FAILURE:
            if config.multi_provider:
                user_impact *= 0.3
                resolution_time *= 0.4
            recommendations.append("Deploy multiple recursive resolvers")
            recommendations.append("Use anycast DNS for resolver redundancy")

        elif failure_type == DNSFailureType.AUTHORITATIVE_SERVER_FAILURE:
            if config.multi_provider:
                user_impact *= 0.3
                resolution_time *= 0.4
            elif config.failover_provider:
                user_impact *= 0.5
                resolution_time *= 0.6
            recommendations.append("Deploy authoritative servers in multiple regions")
            recommendations.append("Use secondary DNS zones for redundancy")

        elif failure_type == DNSFailureType.DDOS_AMPLIFICATION:
            if config.multi_provider:
                user_impact *= 0.4
                resolution_time *= 0.5
            recommendations.append("Implement DNS rate limiting")
            recommendations.append("Use anycast to distribute DDoS traffic")

        user_impact = _clamp(user_impact)
        resolution_time = max(0.0, resolution_time)
        cache_protection = max(0.0, cache_protection)

        # Determine affected services
        if user_impact > 50.0:
            affected = component_ids
        elif user_impact > 20.0:
            affected = component_ids[: max(1, len(component_ids) * 2 // 3)]
        else:
            affected = component_ids[: max(1, len(component_ids) // 3)]

        return DNSFailureImpact(
            failure_type=failure_type,
            affected_services=affected,
            resolution_time_seconds=round(resolution_time, 2),
            cache_protection_seconds=round(cache_protection, 2),
            user_impact_percent=round(user_impact, 2),
            recommendations=recommendations,
        )

    # -- TTL analysis -------------------------------------------------------

    def analyze_ttl_strategy(
        self,
        graph: InfraGraph,
        config: DNSConfig,
    ) -> TTLAnalysis:
        """Analyze the current TTL strategy and recommend improvements."""
        ttl = config.ttl_seconds
        recommendations: list[str] = []

        # Determine risk level based on TTL
        if ttl < 30:
            risk = "high"
            recommendations.append(
                "TTL is extremely low; DNS query volume will be very high"
            )
            recommendations.append(
                "Consider increasing TTL to at least 60 seconds"
            )
        elif ttl < 60:
            risk = "medium"
            recommendations.append(
                "Low TTL increases query volume; acceptable during migrations"
            )
        elif ttl <= 300:
            risk = "low"
        elif ttl <= 3600:
            risk = "low"
            recommendations.append(
                "Consider lowering TTL before planned DNS changes"
            )
        else:
            risk = "high"
            recommendations.append(
                "High TTL slows failover propagation; reduce to 300s or less"
            )
            recommendations.append(
                "Stale DNS cache entries may persist during outages"
            )

        # Cache effectiveness: higher TTL = better caching but slower failover
        if ttl < 30:
            cache_eff = 20.0
        elif ttl < 60:
            cache_eff = 40.0
        elif ttl < 300:
            cache_eff = 60.0
        elif ttl <= 3600:
            cache_eff = 80.0
        else:
            cache_eff = 95.0

        # Propagation delay: time for all caches to reflect changes
        # Worst case is the TTL itself (all caches expire at end of TTL)
        propagation_delay = float(ttl)

        # Graph-based adjustment: more services = more impactful
        total_services = len(graph.components)
        if total_services > 10:
            recommendations.append(
                "Large number of services; ensure TTL supports rapid failover"
            )

        return TTLAnalysis(
            current_ttl=ttl,
            recommended_ttl=300 if risk == "high" else ttl,
            ttl_risk_level=risk,
            cache_effectiveness=round(cache_eff, 2),
            propagation_delay_seconds=round(propagation_delay, 2),
            recommendations=recommendations,
        )

    # -- single point of failure detection ----------------------------------

    def detect_dns_single_points(
        self,
        graph: InfraGraph,
        config: DNSConfig,
    ) -> list[str]:
        """Identify DNS-related single points of failure."""
        spofs: list[str] = []

        if not config.failover_provider and not config.multi_provider:
            spofs.append(f"DNS provider '{config.provider}' has no failover")

        if not config.multi_provider:
            spofs.append("Single DNS provider; no multi-provider redundancy")

        if not config.dnssec_enabled:
            spofs.append("DNSSEC not enabled; vulnerable to cache poisoning")

        if not config.health_check_enabled:
            spofs.append("No DNS health checks; cannot auto-failover")

        # Check graph for DNS-type components without replicas
        for cid, comp in graph.components.items():
            if comp.type == ComponentType.DNS and comp.replicas <= 1:
                spofs.append(
                    f"DNS component '{comp.name}' has no replicas"
                )

        return spofs

    # -- provider failover simulation ---------------------------------------

    def simulate_provider_failover(
        self,
        graph: InfraGraph,
        config: DNSConfig,
    ) -> ProviderFailoverResult:
        """Simulate a DNS provider failover scenario."""
        recommendations: list[str] = []
        records_count = len(config.records) if config.records else 1
        seamless = False
        data_loss = False

        if not config.failover_provider:
            failover_time = float(config.ttl_seconds) * 3.0
            data_loss = True
            recommendations.append(
                "No failover provider configured; failover requires manual intervention"
            )
            recommendations.append(
                "Configure a secondary DNS provider for automated failover"
            )
        elif config.multi_provider:
            failover_time = float(config.ttl_seconds) * 0.1
            seamless = True
            recommendations.append(
                "Multi-provider setup allows near-seamless failover"
            )
        elif config.health_check_enabled:
            failover_time = float(config.ttl_seconds) * 0.5
            seamless = config.ttl_seconds <= 60
            recommendations.append(
                "Health check-based failover is configured"
            )
            if config.ttl_seconds > 300:
                recommendations.append(
                    "Reduce TTL for faster failover propagation"
                )
        else:
            failover_time = float(config.ttl_seconds) * 1.5
            recommendations.append(
                "Enable health checks for automated failover detection"
            )

        return ProviderFailoverResult(
            primary_provider=config.provider,
            failover_provider=config.failover_provider,
            failover_time_seconds=round(max(0.0, failover_time), 2),
            records_affected=records_count,
            data_loss_possible=data_loss,
            seamless=seamless,
            recommendations=recommendations,
        )

    # -- DNS config recommendation ------------------------------------------

    def recommend_dns_config(
        self,
        graph: InfraGraph,
    ) -> DNSConfig:
        """Recommend an optimal DNS configuration based on the graph."""
        total_services = len(graph.components)

        # Determine optimal TTL based on number of services
        if total_services <= 3:
            ttl = 300
        elif total_services <= 10:
            ttl = 180
        else:
            ttl = 60

        # Check for DNS components
        dns_components = [
            cid for cid, c in graph.components.items()
            if c.type == ComponentType.DNS
        ]

        # Check for critical components
        has_db = any(
            c.type == ComponentType.DATABASE for c in graph.components.values()
        )
        has_external = any(
            c.type == ComponentType.EXTERNAL_API for c in graph.components.values()
        )

        # Build recommended records
        records = [
            cid for cid in graph.components.keys()
        ]

        return DNSConfig(
            provider="recommended-primary",
            ttl_seconds=ttl,
            records=records,
            failover_provider="recommended-secondary",
            dnssec_enabled=True,
            health_check_enabled=True,
            multi_provider=total_services > 5 or has_db or has_external,
        )

    # -- blast radius estimation --------------------------------------------

    def estimate_dns_outage_blast_radius(
        self,
        graph: InfraGraph,
        config: DNSConfig,
    ) -> BlastRadiusResult:
        """Estimate the blast radius of a complete DNS outage."""
        total_services = len(graph.components)
        component_ids = list(graph.components.keys())
        recommendations: list[str] = []

        if total_services == 0:
            return BlastRadiusResult(
                total_services=0,
                affected_services=[],
                affected_percent=0.0,
                critical_services_affected=[],
                estimated_downtime_seconds=0.0,
                recommendations=["No services found in graph"],
            )

        # Determine affected services
        # DNS outage affects services that depend on DNS resolution
        # In most architectures, that's all services
        if config.multi_provider:
            affected_frac = 0.2
        elif config.failover_provider:
            affected_frac = 0.5
        else:
            affected_frac = 1.0

        affected_count = max(1, int(total_services * affected_frac))
        affected_services = component_ids[:affected_count]

        # Identify critical services
        critical = []
        for cid in affected_services:
            comp = graph.components.get(cid)
            if comp and comp.type in (
                ComponentType.DATABASE,
                ComponentType.LOAD_BALANCER,
                ComponentType.APP_SERVER,
            ):
                critical.append(cid)

        affected_pct = _clamp(
            (len(affected_services) / total_services) * 100.0
        )

        # Downtime estimation based on config
        if config.multi_provider:
            downtime = float(config.ttl_seconds) * 0.5
        elif config.failover_provider and config.health_check_enabled:
            downtime = float(config.ttl_seconds) * 1.0
        elif config.failover_provider:
            downtime = float(config.ttl_seconds) * 2.0
        else:
            downtime = float(config.ttl_seconds) * 5.0

        if not config.health_check_enabled:
            recommendations.append("Enable health checks for faster detection")
        if not config.multi_provider:
            recommendations.append("Use multi-provider DNS to reduce blast radius")
        if not config.failover_provider:
            recommendations.append("Configure failover provider to limit outage duration")
        if affected_pct > 50.0:
            recommendations.append(
                "High blast radius; implement service mesh for DNS independence"
            )
        if critical:
            recommendations.append(
                f"{len(critical)} critical services affected; prioritize DNS redundancy"
            )

        return BlastRadiusResult(
            total_services=total_services,
            affected_services=affected_services,
            affected_percent=round(affected_pct, 2),
            critical_services_affected=critical,
            estimated_downtime_seconds=round(max(0.0, downtime), 2),
            recommendations=recommendations,
        )
