"""Multi-Cloud Topology Mapper.

Model infrastructure spanning multiple cloud providers and regions,
enabling cross-cloud resilience analysis.

Answers:
- "What happens if an entire cloud provider goes down?"
- "Is our infrastructure too concentrated in one region?"
- "What is the vendor lock-in risk?"
- "How does cross-cloud latency affect resilience?"
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data classes
# ---------------------------------------------------------------------------

class CloudProvider(str, Enum):
    """Supported cloud providers."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    ON_PREMISE = "on_premise"
    HYBRID = "hybrid"


@dataclass
class CloudRegion:
    """A cloud provider region with geographic metadata."""

    provider: CloudProvider
    region_name: str
    display_name: str
    latitude: float
    longitude: float


@dataclass
class CloudMapping:
    """Maps a component to a specific cloud provider / region / AZ."""

    component_id: str
    provider: CloudProvider
    region: str
    availability_zone: str | None = None
    service_name: str | None = None


@dataclass
class CrossCloudLink:
    """Network link between two cloud providers."""

    source_provider: CloudProvider
    target_provider: CloudProvider
    estimated_latency_ms: float
    bandwidth_gbps: float
    is_private_link: bool = False


@dataclass
class MultiCloudRisk:
    """Risk assessment for a multi-cloud topology."""

    provider_concentration_risk: str  # "Low" / "Medium" / "High"
    region_concentration_risk: str
    cross_cloud_latency_risk: str
    vendor_lock_in_score: float  # 0-100
    geographic_distribution_score: float  # 0-100
    recommendations: list[str] = field(default_factory=list)


@dataclass
class MultiCloudTopology:
    """Complete multi-cloud topology description."""

    mappings: dict[str, CloudMapping] = field(default_factory=dict)
    links: list[CrossCloudLink] = field(default_factory=list)
    regions_used: list[CloudRegion] = field(default_factory=list)
    provider_distribution: dict[str, int] = field(default_factory=dict)
    risk_assessment: MultiCloudRisk = field(
        default_factory=lambda: MultiCloudRisk(
            provider_concentration_risk="Low",
            region_concentration_risk="Low",
            cross_cloud_latency_risk="Low",
            vendor_lock_in_score=0.0,
            geographic_distribution_score=0.0,
        )
    )


# ---------------------------------------------------------------------------
# Known cloud regions
# ---------------------------------------------------------------------------

_KNOWN_REGIONS: list[CloudRegion] = [
    # AWS regions
    CloudRegion(CloudProvider.AWS, "us-east-1", "US East (N. Virginia)", 39.0438, -77.4874),
    CloudRegion(CloudProvider.AWS, "us-west-2", "US West (Oregon)", 45.5231, -122.6765),
    CloudRegion(CloudProvider.AWS, "eu-west-1", "EU (Ireland)", 53.3498, -6.2603),
    CloudRegion(CloudProvider.AWS, "ap-northeast-1", "Asia Pacific (Tokyo)", 35.6762, 139.6503),
    CloudRegion(CloudProvider.AWS, "ap-southeast-1", "Asia Pacific (Singapore)", 1.3521, 103.8198),
    # GCP regions
    CloudRegion(CloudProvider.GCP, "us-central1", "US Central (Iowa)", 41.2619, -95.8608),
    CloudRegion(CloudProvider.GCP, "us-east1", "US East (South Carolina)", 33.8361, -81.1637),
    CloudRegion(CloudProvider.GCP, "europe-west1", "Europe West (Belgium)", 50.4473, 3.8196),
    CloudRegion(CloudProvider.GCP, "asia-northeast1", "Asia Northeast (Tokyo)", 35.6762, 139.6503),
    CloudRegion(CloudProvider.GCP, "asia-southeast1", "Asia Southeast (Singapore)", 1.3521, 103.8198),
    # Azure regions
    CloudRegion(CloudProvider.AZURE, "eastus", "East US (Virginia)", 37.4316, -78.6569),
    CloudRegion(CloudProvider.AZURE, "westus2", "West US 2 (Washington)", 47.2331, -119.8527),
    CloudRegion(CloudProvider.AZURE, "westeurope", "West Europe (Netherlands)", 52.3676, 4.9041),
    CloudRegion(CloudProvider.AZURE, "japaneast", "Japan East (Tokyo)", 35.6762, 139.6503),
    CloudRegion(CloudProvider.AZURE, "southeastasia", "Southeast Asia (Singapore)", 1.3521, 103.8198),
]


# ---------------------------------------------------------------------------
# Auto-detection heuristic patterns
# ---------------------------------------------------------------------------

_AWS_PATTERNS: list[str] = [
    "rds", "dynamodb", "s3", "lambda", "ec2", "elb",
    "cloudfront", "sqs", "sns", "elasticache",
]

_GCP_PATTERNS: list[str] = [
    "cloud-sql", "bigquery", "gcs", "cloud-run", "gke",
    "cloud-cdn", "pub-sub", "memorystore",
]

_AZURE_PATTERNS: list[str] = [
    "cosmos", "blob", "aks", "app-service",
    "azure-cdn", "service-bus", "azure-cache",
]

# Provider-specific service names for vendor lock-in scoring
_PROVIDER_SPECIFIC_SERVICES: dict[CloudProvider, set[str]] = {
    CloudProvider.AWS: {
        "rds", "dynamodb", "s3", "lambda", "ec2", "elb",
        "cloudfront", "sqs", "sns", "elasticache", "aurora",
        "kinesis", "redshift", "ecs", "fargate",
    },
    CloudProvider.GCP: {
        "cloud-sql", "bigquery", "gcs", "cloud-run", "gke",
        "cloud-cdn", "pub-sub", "memorystore", "spanner",
        "dataflow", "cloud-functions", "bigtable",
    },
    CloudProvider.AZURE: {
        "cosmos", "blob", "aks", "app-service", "azure-cdn",
        "service-bus", "azure-cache", "azure-functions",
        "cosmos-db", "azure-sql", "event-hub",
    },
}


# ---------------------------------------------------------------------------
# MultiCloudMapper
# ---------------------------------------------------------------------------

class MultiCloudMapper:
    """Maps infrastructure graphs to multi-cloud topologies and analyses risks."""

    def __init__(self) -> None:
        self._known_regions: list[CloudRegion] = list(_KNOWN_REGIONS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map_topology(
        self,
        graph: InfraGraph,
        mappings: list[CloudMapping],
    ) -> MultiCloudTopology:
        """Build a MultiCloudTopology from explicit component-to-cloud mappings.

        Args:
            graph: The infrastructure graph.
            mappings: Explicit cloud mappings for each component.

        Returns:
            A fully populated MultiCloudTopology.
        """
        mapping_dict: dict[str, CloudMapping] = {}
        for m in mappings:
            if m.component_id in graph.components:
                mapping_dict[m.component_id] = m

        # Determine regions used
        regions_used = self._resolve_regions(mapping_dict)

        # Provider distribution
        provider_dist = self._calc_provider_distribution(mapping_dict)

        # Generate cross-cloud links from dependency edges
        links = self._generate_cross_cloud_links(graph, mapping_dict)

        topology = MultiCloudTopology(
            mappings=mapping_dict,
            links=links,
            regions_used=regions_used,
            provider_distribution=provider_dist,
        )

        # Risk assessment
        topology.risk_assessment = self.analyze_cross_cloud_risks(topology)

        return topology

    def auto_detect_providers(
        self,
        graph: InfraGraph,
    ) -> list[CloudMapping]:
        """Heuristically detect cloud provider from component names/ids.

        Detection rules (checked in order):
        - AWS patterns: rds, dynamodb, s3, lambda, ec2, elb, cloudfront, sqs, sns, elasticache
        - GCP patterns: cloud-sql, bigquery, gcs, cloud-run, gke, cloud-cdn, pub-sub, memorystore
        - Azure patterns: cosmos, blob, aks, app-service, azure-cdn, service-bus, azure-cache
        - Fallback: ON_PREMISE

        Args:
            graph: The infrastructure graph.

        Returns:
            List of auto-detected CloudMappings.
        """
        mappings: list[CloudMapping] = []

        for comp_id, comp in graph.components.items():
            name_lower = comp.name.lower()
            id_lower = comp.id.lower()
            search_text = f"{name_lower} {id_lower}"

            provider = self._detect_provider(search_text)
            region = self._default_region_for_provider(provider)
            service_name = self._detect_service_name(search_text, provider)

            mappings.append(CloudMapping(
                component_id=comp_id,
                provider=provider,
                region=region,
                service_name=service_name,
            ))

        return mappings

    def analyze_cross_cloud_risks(
        self,
        topology: MultiCloudTopology,
    ) -> MultiCloudRisk:
        """Analyze risks in a multi-cloud topology.

        Evaluates:
        - Provider concentration risk (>80% in one provider = High)
        - Region concentration risk (>60% in one region = High)
        - Cross-cloud latency risk
        - Vendor lock-in score (0-100)
        - Geographic distribution score (0-100)

        Args:
            topology: The multi-cloud topology to analyze.

        Returns:
            MultiCloudRisk assessment.
        """
        total = sum(topology.provider_distribution.values())
        if total == 0:
            return MultiCloudRisk(
                provider_concentration_risk="Low",
                region_concentration_risk="Low",
                cross_cloud_latency_risk="Low",
                vendor_lock_in_score=0.0,
                geographic_distribution_score=0.0,
                recommendations=["No components mapped to cloud providers."],
            )

        # --- Provider concentration ---
        provider_concentration = self._assess_provider_concentration(
            topology.provider_distribution, total,
        )

        # --- Region concentration ---
        region_concentration = self._assess_region_concentration(
            topology.mappings, total,
        )

        # --- Cross-cloud latency risk ---
        latency_risk = self._assess_latency_risk(topology.links)

        # --- Vendor lock-in score ---
        lock_in = self._calc_vendor_lock_in(topology.mappings)

        # --- Geographic distribution score ---
        geo_score = self._calc_geographic_distribution(topology.regions_used)

        # --- Recommendations ---
        recommendations = self._generate_risk_recommendations(
            provider_concentration, region_concentration,
            latency_risk, lock_in, geo_score, topology,
        )

        return MultiCloudRisk(
            provider_concentration_risk=provider_concentration,
            region_concentration_risk=region_concentration,
            cross_cloud_latency_risk=latency_risk,
            vendor_lock_in_score=round(lock_in, 1),
            geographic_distribution_score=round(geo_score, 1),
            recommendations=recommendations,
        )

    def suggest_multi_cloud_strategy(
        self,
        graph: InfraGraph,
        topology: MultiCloudTopology,
    ) -> list[str]:
        """Suggest improvements to the multi-cloud strategy.

        Args:
            graph: The infrastructure graph.
            topology: Current multi-cloud topology.

        Returns:
            List of strategy suggestions.
        """
        suggestions: list[str] = []
        total = sum(topology.provider_distribution.values())
        if total == 0:
            suggestions.append(
                "No components are mapped. Map components to cloud providers "
                "to enable multi-cloud analysis."
            )
            return suggestions

        # Count distinct providers (excluding ON_PREMISE)
        cloud_providers = {
            p for p, c in topology.provider_distribution.items()
            if c > 0 and p not in (CloudProvider.ON_PREMISE.value, CloudProvider.HYBRID.value)
        }

        if len(cloud_providers) <= 1:
            suggestions.append(
                "Consider distributing workloads across at least 2 cloud providers "
                "to reduce vendor dependency and improve resilience."
            )

        # Check for single-region deployments
        regions = set()
        for m in topology.mappings.values():
            regions.add(m.region)
        if len(regions) <= 1:
            suggestions.append(
                "All components are in a single region. Deploy across multiple "
                "regions for geographic redundancy and disaster recovery."
            )

        # Check for databases without multi-region setup
        for comp_id, comp in graph.components.items():
            if comp.type in (ComponentType.DATABASE, ComponentType.CACHE):
                mapping = topology.mappings.get(comp_id)
                if mapping:
                    same_region_dbs = [
                        m for m in topology.mappings.values()
                        if m.component_id != comp_id
                        and m.region == mapping.region
                        and graph.components.get(m.component_id)
                        and graph.components[m.component_id].type == comp.type
                    ]
                    if not same_region_dbs and comp.replicas <= 1:
                        suggestions.append(
                            f"Component '{comp_id}' ({comp.type.value}) has no "
                            f"cross-region replica. Consider multi-region replication "
                            f"for disaster recovery."
                        )

        # Check for high cross-cloud latency links
        for link in topology.links:
            if link.estimated_latency_ms > 100:
                suggestions.append(
                    f"High latency ({link.estimated_latency_ms:.0f}ms) detected between "
                    f"{link.source_provider.value} and {link.target_provider.value}. "
                    f"Consider co-locating tightly coupled components or using "
                    f"private interconnects."
                )

        # Check vendor lock-in
        risk = topology.risk_assessment
        if risk.vendor_lock_in_score > 70:
            suggestions.append(
                f"Vendor lock-in score is high ({risk.vendor_lock_in_score:.0f}/100). "
                f"Consider using provider-agnostic services (e.g., Kubernetes, "
                f"PostgreSQL) to reduce dependency on proprietary services."
            )

        # Deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique.append(s)

        return unique

    def calculate_provider_blast_radius(
        self,
        graph: InfraGraph,
        topology: MultiCloudTopology,
        provider: CloudProvider,
    ) -> dict:
        """Calculate the blast radius of an entire cloud provider outage.

        Args:
            graph: The infrastructure graph.
            topology: The multi-cloud topology.
            provider: The cloud provider that goes down.

        Returns:
            Dict with affected_components, affected_percentage,
            cascade_affected, total_affected, and surviving_components.
        """
        total_components = len(graph.components)
        if total_components == 0:
            return {
                "provider": provider.value,
                "directly_affected": [],
                "directly_affected_count": 0,
                "cascade_affected": [],
                "cascade_affected_count": 0,
                "total_affected_count": 0,
                "total_affected_percentage": 0.0,
                "surviving_components": [],
                "surviving_count": 0,
            }

        # Directly affected: components on this provider
        directly_affected: list[str] = []
        for comp_id, mapping in topology.mappings.items():
            if mapping.provider == provider:
                directly_affected.append(comp_id)

        # Cascade: components that depend on directly affected (transitively)
        cascade_affected: set[str] = set()
        for comp_id in directly_affected:
            affected = graph.get_all_affected(comp_id)
            cascade_affected.update(affected)

        # Remove directly affected from cascade set
        cascade_affected -= set(directly_affected)

        total_affected = set(directly_affected) | cascade_affected
        surviving = [
            cid for cid in graph.components if cid not in total_affected
        ]

        return {
            "provider": provider.value,
            "directly_affected": sorted(directly_affected),
            "directly_affected_count": len(directly_affected),
            "cascade_affected": sorted(cascade_affected),
            "cascade_affected_count": len(cascade_affected),
            "total_affected_count": len(total_affected),
            "total_affected_percentage": round(
                len(total_affected) / total_components * 100, 1,
            ),
            "surviving_components": sorted(surviving),
            "surviving_count": len(surviving),
        }

    def calculate_region_blast_radius(
        self,
        graph: InfraGraph,
        topology: MultiCloudTopology,
        region: str,
    ) -> dict:
        """Calculate the blast radius of a regional outage.

        Args:
            graph: The infrastructure graph.
            topology: The multi-cloud topology.
            region: The region that goes down.

        Returns:
            Dict with affected_components, cascade_affected, etc.
        """
        total_components = len(graph.components)
        if total_components == 0:
            return {
                "region": region,
                "directly_affected": [],
                "directly_affected_count": 0,
                "cascade_affected": [],
                "cascade_affected_count": 0,
                "total_affected_count": 0,
                "total_affected_percentage": 0.0,
                "surviving_components": [],
                "surviving_count": 0,
            }

        directly_affected: list[str] = []
        for comp_id, mapping in topology.mappings.items():
            if mapping.region == region:
                directly_affected.append(comp_id)

        cascade_affected: set[str] = set()
        for comp_id in directly_affected:
            affected = graph.get_all_affected(comp_id)
            cascade_affected.update(affected)

        cascade_affected -= set(directly_affected)

        total_affected = set(directly_affected) | cascade_affected
        surviving = [
            cid for cid in graph.components if cid not in total_affected
        ]

        return {
            "region": region,
            "directly_affected": sorted(directly_affected),
            "directly_affected_count": len(directly_affected),
            "cascade_affected": sorted(cascade_affected),
            "cascade_affected_count": len(cascade_affected),
            "total_affected_count": len(total_affected),
            "total_affected_percentage": round(
                len(total_affected) / total_components * 100, 1,
            ),
            "surviving_components": sorted(surviving),
            "surviving_count": len(surviving),
        }

    def generate_topology_summary(
        self,
        topology: MultiCloudTopology,
    ) -> str:
        """Generate a human-readable text summary of the topology.

        Args:
            topology: The multi-cloud topology.

        Returns:
            Multi-line text summary string.
        """
        lines: list[str] = []
        lines.append("=== Multi-Cloud Topology Summary ===")
        lines.append("")

        # Provider distribution
        total = sum(topology.provider_distribution.values())
        lines.append(f"Total mapped components: {total}")
        lines.append("Provider distribution:")
        for provider, count in sorted(topology.provider_distribution.items()):
            pct = (count / total * 100) if total > 0 else 0.0
            lines.append(f"  {provider}: {count} ({pct:.1f}%)")

        # Regions
        lines.append("")
        lines.append(f"Regions used: {len(topology.regions_used)}")
        for region in topology.regions_used:
            lines.append(
                f"  {region.provider.value}/{region.region_name} "
                f"({region.display_name})"
            )

        # Cross-cloud links
        if topology.links:
            lines.append("")
            lines.append(f"Cross-cloud links: {len(topology.links)}")
            for link in topology.links:
                priv = " [private]" if link.is_private_link else ""
                lines.append(
                    f"  {link.source_provider.value} <-> "
                    f"{link.target_provider.value}: "
                    f"{link.estimated_latency_ms:.1f}ms, "
                    f"{link.bandwidth_gbps:.1f} Gbps{priv}"
                )

        # Risk assessment
        risk = topology.risk_assessment
        lines.append("")
        lines.append("Risk Assessment:")
        lines.append(f"  Provider concentration: {risk.provider_concentration_risk}")
        lines.append(f"  Region concentration: {risk.region_concentration_risk}")
        lines.append(f"  Cross-cloud latency: {risk.cross_cloud_latency_risk}")
        lines.append(f"  Vendor lock-in score: {risk.vendor_lock_in_score:.1f}/100")
        lines.append(
            f"  Geographic distribution: {risk.geographic_distribution_score:.1f}/100"
        )

        if risk.recommendations:
            lines.append("")
            lines.append("Recommendations:")
            for rec in risk.recommendations:
                lines.append(f"  - {rec}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_provider(self, text: str) -> CloudProvider:
        """Detect cloud provider from text using pattern matching."""
        # Check Azure first (patterns like "azure-" are more specific)
        for pattern in _AZURE_PATTERNS:
            if pattern in text:
                return CloudProvider.AZURE

        # Check GCP (patterns like "cloud-" are fairly specific)
        for pattern in _GCP_PATTERNS:
            if pattern in text:
                return CloudProvider.GCP

        # Check AWS
        for pattern in _AWS_PATTERNS:
            if pattern in text:
                return CloudProvider.AWS

        return CloudProvider.ON_PREMISE

    def _detect_service_name(
        self, text: str, provider: CloudProvider,
    ) -> str | None:
        """Detect specific service name from text."""
        patterns_map = {
            CloudProvider.AWS: _AWS_PATTERNS,
            CloudProvider.GCP: _GCP_PATTERNS,
            CloudProvider.AZURE: _AZURE_PATTERNS,
        }
        patterns = patterns_map.get(provider, [])
        for pattern in patterns:
            if pattern in text:
                return pattern
        return None

    def _default_region_for_provider(self, provider: CloudProvider) -> str:
        """Return the default region for a provider."""
        defaults = {
            CloudProvider.AWS: "us-east-1",
            CloudProvider.GCP: "us-central1",
            CloudProvider.AZURE: "eastus",
            CloudProvider.ON_PREMISE: "on-premise",
            CloudProvider.HYBRID: "hybrid",
        }
        return defaults.get(provider, "unknown")

    def _resolve_regions(
        self, mappings: dict[str, CloudMapping],
    ) -> list[CloudRegion]:
        """Resolve CloudRegion objects from mappings."""
        seen: set[tuple[str, str]] = set()
        regions: list[CloudRegion] = []

        for mapping in mappings.values():
            key = (mapping.provider.value, mapping.region)
            if key in seen:
                continue
            seen.add(key)

            # Look up in known regions
            found = False
            for kr in self._known_regions:
                if kr.provider == mapping.provider and kr.region_name == mapping.region:
                    regions.append(kr)
                    found = True
                    break
            if not found:
                # Create a placeholder region
                regions.append(CloudRegion(
                    provider=mapping.provider,
                    region_name=mapping.region,
                    display_name=mapping.region,
                    latitude=0.0,
                    longitude=0.0,
                ))

        return regions

    def _calc_provider_distribution(
        self, mappings: dict[str, CloudMapping],
    ) -> dict[str, int]:
        """Count components per provider."""
        dist: dict[str, int] = {}
        for mapping in mappings.values():
            pval = mapping.provider.value
            dist[pval] = dist.get(pval, 0) + 1
        return dist

    def _generate_cross_cloud_links(
        self,
        graph: InfraGraph,
        mappings: dict[str, CloudMapping],
    ) -> list[CrossCloudLink]:
        """Generate cross-cloud links from dependency edges."""
        links: list[CrossCloudLink] = []
        seen: set[tuple[str, str]] = set()

        for edge in graph.all_dependency_edges():
            src_mapping = mappings.get(edge.source_id)
            tgt_mapping = mappings.get(edge.target_id)

            if not src_mapping or not tgt_mapping:
                continue

            # Only create links for cross-provider or cross-region dependencies
            if src_mapping.provider == tgt_mapping.provider and src_mapping.region == tgt_mapping.region:
                continue

            link_key = tuple(sorted([
                f"{src_mapping.provider.value}:{src_mapping.region}",
                f"{tgt_mapping.provider.value}:{tgt_mapping.region}",
            ]))
            if link_key in seen:
                continue
            seen.add(link_key)

            latency = self._estimate_latency(src_mapping, tgt_mapping)
            bandwidth = self._estimate_bandwidth(src_mapping, tgt_mapping)

            links.append(CrossCloudLink(
                source_provider=src_mapping.provider,
                target_provider=tgt_mapping.provider,
                estimated_latency_ms=latency,
                bandwidth_gbps=bandwidth,
                is_private_link=False,
            ))

        return links

    def _estimate_latency(
        self, src: CloudMapping, tgt: CloudMapping,
    ) -> float:
        """Estimate network latency between two cloud mappings.

        Rules:
        - Same provider, same region: 1.5ms
        - Same provider, cross-region: 100ms
        - Cross-provider, same geography: 12.5ms
        - Cross-provider, cross-geography: 200ms
        """
        if src.provider == tgt.provider:
            if src.region == tgt.region:
                return 1.5
            return 100.0

        # Cross-provider: check geography
        src_region_obj = self._find_region(src.provider, src.region)
        tgt_region_obj = self._find_region(tgt.provider, tgt.region)

        if src_region_obj and tgt_region_obj:
            distance = self._haversine_distance(
                src_region_obj.latitude, src_region_obj.longitude,
                tgt_region_obj.latitude, tgt_region_obj.longitude,
            )
            # Roughly: < 2000 km = same geography
            if distance < 2000:
                return 12.5
            return 200.0

        # Fallback: cross-provider, unknown geography
        return 200.0

    def _estimate_bandwidth(
        self, src: CloudMapping, tgt: CloudMapping,
    ) -> float:
        """Estimate bandwidth in Gbps between two mappings."""
        if src.provider == tgt.provider:
            if src.region == tgt.region:
                return 25.0
            return 10.0
        return 5.0

    def _find_region(
        self, provider: CloudProvider, region_name: str,
    ) -> CloudRegion | None:
        """Find a known cloud region."""
        for kr in self._known_regions:
            if kr.provider == provider and kr.region_name == region_name:
                return kr
        return None

    @staticmethod
    def _haversine_distance(
        lat1: float, lon1: float, lat2: float, lon2: float,
    ) -> float:
        """Calculate distance in km between two lat/lon points."""
        r = 6371.0  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c

    def _assess_provider_concentration(
        self,
        provider_dist: dict[str, int],
        total: int,
    ) -> str:
        """Assess provider concentration risk."""
        if total == 0:
            return "Low"
        max_count = max(provider_dist.values())
        ratio = max_count / total
        if ratio > 0.8:
            return "High"
        elif ratio > 0.6:
            return "Medium"
        return "Low"

    def _assess_region_concentration(
        self,
        mappings: dict[str, CloudMapping],
        total: int,
    ) -> str:
        """Assess region concentration risk."""
        if total == 0:
            return "Low"
        region_counts: dict[str, int] = {}
        for m in mappings.values():
            region_counts[m.region] = region_counts.get(m.region, 0) + 1
        max_count = max(region_counts.values()) if region_counts else 0
        ratio = max_count / total
        if ratio > 0.6:
            return "High"
        elif ratio > 0.4:
            return "Medium"
        return "Low"

    def _assess_latency_risk(self, links: list[CrossCloudLink]) -> str:
        """Assess cross-cloud latency risk."""
        if not links:
            return "Low"
        max_latency = max(link.estimated_latency_ms for link in links)
        if max_latency > 150:
            return "High"
        elif max_latency > 50:
            return "Medium"
        return "Low"

    def _calc_vendor_lock_in(
        self,
        mappings: dict[str, CloudMapping],
    ) -> float:
        """Calculate vendor lock-in score (0-100).

        Higher score = more lock-in.
        Based on how many provider-specific services are used.
        """
        if not mappings:
            return 0.0

        total = len(mappings)
        locked_count = 0

        for m in mappings.values():
            if m.service_name:
                specific_services = _PROVIDER_SPECIFIC_SERVICES.get(
                    m.provider, set(),
                )
                if m.service_name in specific_services:
                    locked_count += 1

        return (locked_count / total) * 100.0

    def _calc_geographic_distribution(
        self,
        regions: list[CloudRegion],
    ) -> float:
        """Calculate geographic distribution score (0-100).

        Higher score = better geographic spread.
        Based on number of unique geographic areas covered.
        """
        if not regions:
            return 0.0

        if len(regions) == 1:
            return 20.0

        # Calculate average pairwise distance between regions
        distances: list[float] = []
        for i in range(len(regions)):
            for j in range(i + 1, len(regions)):
                d = self._haversine_distance(
                    regions[i].latitude, regions[i].longitude,
                    regions[j].latitude, regions[j].longitude,
                )
                distances.append(d)

        if not distances:
            return 20.0

        avg_distance = sum(distances) / len(distances)

        # Score based on:
        # - Number of regions (up to 50 points)
        # - Average distance spread (up to 50 points)
        region_score = min(50.0, len(regions) * 10.0)

        # Max distance on Earth is ~20000 km; normalize to 0-50
        distance_score = min(50.0, (avg_distance / 20000.0) * 100.0)

        return round(region_score + distance_score, 1)

    def _generate_risk_recommendations(
        self,
        provider_conc: str,
        region_conc: str,
        latency_risk: str,
        lock_in: float,
        geo_score: float,
        topology: MultiCloudTopology,
    ) -> list[str]:
        """Generate recommendations based on risk analysis."""
        recs: list[str] = []

        if provider_conc == "High":
            # Find the dominant provider
            dominant = max(
                topology.provider_distribution,
                key=topology.provider_distribution.get,  # type: ignore[arg-type]
            )
            recs.append(
                f"Provider concentration is high: >80% of components are on "
                f"{dominant}. Distribute workloads across multiple providers "
                f"to reduce single-provider risk."
            )
        elif provider_conc == "Medium":
            recs.append(
                "Provider concentration is moderate. Consider further "
                "distributing workloads for improved resilience."
            )

        if region_conc == "High":
            recs.append(
                "Region concentration is high: >60% of components are in a "
                "single region. Deploy across multiple regions for disaster "
                "recovery."
            )
        elif region_conc == "Medium":
            recs.append(
                "Region concentration is moderate. Consider spreading "
                "components across more regions."
            )

        if latency_risk == "High":
            recs.append(
                "Cross-cloud latency is high (>150ms). Co-locate tightly "
                "coupled services or use private interconnects to reduce "
                "latency."
            )
        elif latency_risk == "Medium":
            recs.append(
                "Cross-cloud latency is moderate. Monitor for latency-"
                "sensitive workloads."
            )

        if lock_in > 70:
            recs.append(
                f"Vendor lock-in score is {lock_in:.0f}/100 (high). Adopt "
                f"provider-agnostic alternatives where possible."
            )
        elif lock_in > 40:
            recs.append(
                f"Vendor lock-in score is {lock_in:.0f}/100 (moderate). "
                f"Review proprietary service usage."
            )

        if geo_score < 30:
            recs.append(
                "Geographic distribution is limited. Consider deploying "
                "to additional regions for better availability and "
                "latency characteristics."
            )

        return recs
