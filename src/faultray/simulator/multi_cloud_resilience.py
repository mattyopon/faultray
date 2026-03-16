"""Multi-Cloud Resilience Analyzer.

Analyzes resilience of multi-cloud and hybrid cloud deployments by
evaluating cross-cloud dependencies, provider-level failure impact,
data sovereignty compliance, vendor lock-in risk, egress costs,
portable workload identification, and disaster recovery posture.

Answers:
- "How resilient is our multi-cloud deployment?"
- "What is our vendor lock-in risk per component?"
- "Which workloads can be migrated between clouds?"
- "What are the egress costs for cross-cloud communication?"
- "Does our deployment comply with data sovereignty requirements?"
- "What is our DR posture across clouds (active-active vs active-passive)?"
- "Which cloud-specific failure modes affect us (AZ outage, region outage)?"
- "How do we map equivalent services across providers (S3/GCS/Blob)?"
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CloudProvider(str, Enum):
    """Supported cloud providers."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    ON_PREMISE = "on_premise"
    EDGE = "edge"


class DRMode(str, Enum):
    """Disaster recovery modes across clouds."""

    ACTIVE_ACTIVE = "active_active"
    ACTIVE_PASSIVE = "active_passive"
    PILOT_LIGHT = "pilot_light"
    BACKUP_RESTORE = "backup_restore"
    NONE = "none"


class FailureMode(str, Enum):
    """Cloud-specific failure modes."""

    AZ_OUTAGE = "az_outage"
    REGION_OUTAGE = "region_outage"
    PROVIDER_OUTAGE = "provider_outage"
    NETWORK_PARTITION = "network_partition"
    SERVICE_DEGRADATION = "service_degradation"
    DNS_FAILURE = "dns_failure"
    CONTROL_PLANE_FAILURE = "control_plane_failure"


class DataSovereigntyRegion(str, Enum):
    """Data sovereignty compliance regions."""

    EU = "eu"
    US = "us"
    APAC = "apac"
    CHINA = "china"
    BRAZIL = "brazil"
    INDIA = "india"
    RUSSIA = "russia"
    GLOBAL = "global"


class PortabilityLevel(str, Enum):
    """Workload portability level."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    LOCKED = "locked"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CloudComponentMapping:
    """Maps a component to a cloud provider, region, and service."""

    component_id: str
    provider: CloudProvider
    region: str
    availability_zone: str = ""
    service_name: str = ""
    data_sovereignty: DataSovereigntyRegion = DataSovereigntyRegion.GLOBAL
    is_stateful: bool = False
    data_volume_gb: float = 0.0


@dataclass
class CrossCloudDependency:
    """A dependency that crosses cloud provider boundaries."""

    source_id: str
    target_id: str
    source_provider: CloudProvider
    target_provider: CloudProvider
    source_region: str
    target_region: str
    estimated_latency_ms: float = 0.0
    monthly_data_transfer_gb: float = 0.0
    is_critical: bool = True


@dataclass
class ServiceEquivalent:
    """Maps equivalent services across cloud providers."""

    service_category: str
    aws_service: str
    gcp_service: str
    azure_service: str
    migration_complexity: PortabilityLevel = PortabilityLevel.MEDIUM


@dataclass
class VendorLockInAssessment:
    """Per-component vendor lock-in risk assessment."""

    component_id: str
    provider: CloudProvider
    service_name: str
    lock_in_score: float  # 0-100, higher = more locked in
    portability: PortabilityLevel
    migration_effort_hours: float
    alternatives: list[str] = field(default_factory=list)
    lock_in_reasons: list[str] = field(default_factory=list)


@dataclass
class EgressCostEstimate:
    """Egress cost modeling for cross-cloud communication."""

    source_provider: CloudProvider
    target_provider: CloudProvider
    source_region: str
    target_region: str
    monthly_data_gb: float
    cost_per_gb: float
    monthly_cost: float
    annual_cost: float


@dataclass
class FailureModeImpact:
    """Impact analysis for a specific failure mode."""

    failure_mode: FailureMode
    affected_provider: CloudProvider
    affected_region: str
    directly_affected_components: list[str] = field(default_factory=list)
    cascade_affected_components: list[str] = field(default_factory=list)
    total_affected_count: int = 0
    total_component_count: int = 0
    impact_percentage: float = 0.0
    estimated_recovery_minutes: float = 0.0
    surviving_components: list[str] = field(default_factory=list)


@dataclass
class DRPosture:
    """Disaster recovery posture across clouds."""

    mode: DRMode
    primary_provider: CloudProvider
    primary_region: str
    dr_provider: CloudProvider | None = None
    dr_region: str = ""
    rpo_seconds: int = 0
    rto_seconds: int = 0
    failover_automated: bool = False
    data_replication_lag_seconds: int = 0
    last_tested: str = ""
    readiness_score: float = 0.0


@dataclass
class ResilienceAnalysisResult:
    """Complete multi-cloud resilience analysis result."""

    timestamp: str
    overall_score: float  # 0-100
    provider_diversity_score: float
    geographic_distribution_score: float
    vendor_lock_in_score: float
    dr_readiness_score: float
    data_sovereignty_compliant: bool
    cross_cloud_dependency_count: int
    total_monthly_egress_cost: float
    failure_mode_impacts: list[FailureModeImpact] = field(default_factory=list)
    vendor_assessments: list[VendorLockInAssessment] = field(default_factory=list)
    egress_costs: list[EgressCostEstimate] = field(default_factory=list)
    portable_workloads: list[str] = field(default_factory=list)
    locked_workloads: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service equivalence mapping
# ---------------------------------------------------------------------------

_SERVICE_EQUIVALENTS: list[ServiceEquivalent] = [
    ServiceEquivalent("object_storage", "s3", "gcs", "blob", PortabilityLevel.HIGH),
    ServiceEquivalent("block_storage", "ebs", "persistent-disk", "managed-disk", PortabilityLevel.HIGH),
    ServiceEquivalent("relational_db", "rds", "cloud-sql", "azure-sql", PortabilityLevel.MEDIUM),
    ServiceEquivalent("nosql_db", "dynamodb", "firestore", "cosmos", PortabilityLevel.LOW),
    ServiceEquivalent("container_orchestration", "ecs", "gke", "aks", PortabilityLevel.MEDIUM),
    ServiceEquivalent("serverless_compute", "lambda", "cloud-functions", "azure-functions", PortabilityLevel.LOW),
    ServiceEquivalent("message_queue", "sqs", "pub-sub", "service-bus", PortabilityLevel.MEDIUM),
    ServiceEquivalent("cdn", "cloudfront", "cloud-cdn", "azure-cdn", PortabilityLevel.HIGH),
    ServiceEquivalent("load_balancer", "elb", "cloud-lb", "azure-lb", PortabilityLevel.HIGH),
    ServiceEquivalent("cache", "elasticache", "memorystore", "azure-cache", PortabilityLevel.MEDIUM),
    ServiceEquivalent("dns", "route53", "cloud-dns", "azure-dns", PortabilityLevel.HIGH),
    ServiceEquivalent("kubernetes", "eks", "gke", "aks", PortabilityLevel.HIGH),
]

# Provider-specific (proprietary) services that increase lock-in
_PROPRIETARY_SERVICES: dict[CloudProvider, set[str]] = {
    CloudProvider.AWS: {
        "dynamodb", "aurora", "kinesis", "redshift", "step-functions",
        "fargate", "app-mesh", "eventbridge", "lake-formation",
    },
    CloudProvider.GCP: {
        "bigquery", "spanner", "bigtable", "dataflow", "vertex-ai",
        "cloud-composer", "alloydb", "firestore",
    },
    CloudProvider.AZURE: {
        "cosmos", "synapse", "event-hub", "logic-apps",
        "power-automate", "azure-arc", "cosmos-db",
    },
}

# Egress cost per GB (USD) for cross-cloud / cross-region data transfer
_EGRESS_COSTS: dict[CloudProvider, float] = {
    CloudProvider.AWS: 0.09,
    CloudProvider.GCP: 0.08,
    CloudProvider.AZURE: 0.087,
    CloudProvider.ON_PREMISE: 0.0,
    CloudProvider.EDGE: 0.12,
}

# Typical cross-cloud latency estimates (ms)
_CROSS_CLOUD_LATENCY: dict[tuple[str, str], float] = {
    ("same_provider_same_region", ""): 1.5,
    ("same_provider_cross_region", ""): 80.0,
    ("cross_provider_same_geo", ""): 15.0,
    ("cross_provider_cross_geo", ""): 200.0,
}

# Estimated recovery time per failure mode (minutes)
_RECOVERY_ESTIMATES: dict[FailureMode, float] = {
    FailureMode.AZ_OUTAGE: 30.0,
    FailureMode.REGION_OUTAGE: 120.0,
    FailureMode.PROVIDER_OUTAGE: 480.0,
    FailureMode.NETWORK_PARTITION: 15.0,
    FailureMode.SERVICE_DEGRADATION: 45.0,
    FailureMode.DNS_FAILURE: 20.0,
    FailureMode.CONTROL_PLANE_FAILURE: 60.0,
}

# Data sovereignty region to geographic region mapping
_SOVEREIGNTY_GEO_MAP: dict[DataSovereigntyRegion, set[str]] = {
    DataSovereigntyRegion.EU: {
        "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1",
        "europe-west1", "europe-west2", "europe-west3", "europe-west4",
        "europe-north1", "westeurope", "northeurope", "germanywestcentral",
        "francecentral", "swedencentral",
    },
    DataSovereigntyRegion.US: {
        "us-east-1", "us-east-2", "us-west-1", "us-west-2",
        "us-central1", "us-east1", "us-west1", "us-west2",
        "eastus", "eastus2", "westus", "westus2", "centralus",
    },
    DataSovereigntyRegion.APAC: {
        "ap-northeast-1", "ap-southeast-1", "ap-southeast-2", "ap-south-1",
        "asia-northeast1", "asia-southeast1", "asia-east1",
        "japaneast", "japanwest", "southeastasia", "eastasia",
    },
    DataSovereigntyRegion.CHINA: {
        "cn-north-1", "cn-northwest-1",
        "asia-east2",
        "chinaeast", "chinanorth",
    },
    DataSovereigntyRegion.BRAZIL: {
        "sa-east-1",
        "southamerica-east1",
        "brazilsouth",
    },
    DataSovereigntyRegion.INDIA: {
        "ap-south-1",
        "asia-south1",
        "centralindia", "southindia",
    },
}


# ---------------------------------------------------------------------------
# MultiCloudResilienceAnalyzer
# ---------------------------------------------------------------------------

class MultiCloudResilienceAnalyzer:
    """Analyzes resilience of multi-cloud and hybrid cloud deployments."""

    def __init__(self) -> None:
        self._service_equivalents = list(_SERVICE_EQUIVALENTS)
        self._proprietary_services = dict(_PROPRIETARY_SERVICES)
        self._egress_costs = dict(_EGRESS_COSTS)

    # ------------------------------------------------------------------
    # Main analysis entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        graph: InfraGraph,
        mappings: list[CloudComponentMapping],
        dr_posture: DRPosture | None = None,
    ) -> ResilienceAnalysisResult:
        """Run a full multi-cloud resilience analysis.

        Args:
            graph: The infrastructure graph.
            mappings: Cloud component mappings.
            dr_posture: Optional DR posture configuration.

        Returns:
            Complete ResilienceAnalysisResult.
        """
        mapping_dict = {m.component_id: m for m in mappings if m.component_id in graph.components}

        cross_deps = self.identify_cross_cloud_dependencies(graph, mapping_dict)
        vendor_assessments = self.assess_vendor_lock_in(graph, mapping_dict)
        egress_costs = self.estimate_egress_costs(cross_deps)
        failure_impacts = self.analyze_all_failure_modes(graph, mapping_dict)
        portable, locked = self.identify_portable_workloads(mapping_dict)
        sovereignty_ok = self.check_data_sovereignty(mapping_dict)

        provider_diversity = self._calc_provider_diversity(mapping_dict)
        geo_distribution = self._calc_geographic_distribution(mapping_dict)
        avg_lock_in = self._calc_average_lock_in(vendor_assessments)
        dr_score = self._calc_dr_readiness(dr_posture)

        overall = self._calc_overall_score(
            provider_diversity, geo_distribution, avg_lock_in, dr_score,
        )

        total_egress = sum(e.monthly_cost for e in egress_costs)

        recommendations = self._generate_recommendations(
            provider_diversity, geo_distribution, avg_lock_in, dr_score,
            cross_deps, failure_impacts, sovereignty_ok, total_egress,
        )

        now = datetime.now(timezone.utc).isoformat()

        return ResilienceAnalysisResult(
            timestamp=now,
            overall_score=round(overall, 1),
            provider_diversity_score=round(provider_diversity, 1),
            geographic_distribution_score=round(geo_distribution, 1),
            vendor_lock_in_score=round(avg_lock_in, 1),
            dr_readiness_score=round(dr_score, 1),
            data_sovereignty_compliant=sovereignty_ok,
            cross_cloud_dependency_count=len(cross_deps),
            total_monthly_egress_cost=round(total_egress, 2),
            failure_mode_impacts=failure_impacts,
            vendor_assessments=vendor_assessments,
            egress_costs=egress_costs,
            portable_workloads=portable,
            locked_workloads=locked,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Cross-cloud dependency identification
    # ------------------------------------------------------------------

    def identify_cross_cloud_dependencies(
        self,
        graph: InfraGraph,
        mappings: dict[str, CloudComponentMapping],
    ) -> list[CrossCloudDependency]:
        """Identify dependencies that cross cloud provider boundaries.

        Args:
            graph: Infrastructure graph.
            mappings: Component-to-cloud mappings.

        Returns:
            List of cross-cloud dependencies.
        """
        cross_deps: list[CrossCloudDependency] = []

        for edge in graph.all_dependency_edges():
            src_map = mappings.get(edge.source_id)
            tgt_map = mappings.get(edge.target_id)

            if not src_map or not tgt_map:
                continue

            if src_map.provider == tgt_map.provider and src_map.region == tgt_map.region:
                continue

            latency = self._estimate_latency(src_map, tgt_map)
            data_transfer = max(src_map.data_volume_gb, tgt_map.data_volume_gb) * 0.1

            cross_deps.append(CrossCloudDependency(
                source_id=edge.source_id,
                target_id=edge.target_id,
                source_provider=src_map.provider,
                target_provider=tgt_map.provider,
                source_region=src_map.region,
                target_region=tgt_map.region,
                estimated_latency_ms=round(latency, 1),
                monthly_data_transfer_gb=round(data_transfer, 2),
                is_critical=(edge.dependency_type == "requires"),
            ))

        return cross_deps

    # ------------------------------------------------------------------
    # Vendor lock-in assessment
    # ------------------------------------------------------------------

    def assess_vendor_lock_in(
        self,
        graph: InfraGraph,
        mappings: dict[str, CloudComponentMapping],
    ) -> list[VendorLockInAssessment]:
        """Assess vendor lock-in risk per component.

        Args:
            graph: Infrastructure graph.
            mappings: Component-to-cloud mappings.

        Returns:
            List of VendorLockInAssessment.
        """
        assessments: list[VendorLockInAssessment] = []

        for comp_id, mapping in mappings.items():
            comp = graph.get_component(comp_id)
            if not comp:
                continue

            service = mapping.service_name.lower() if mapping.service_name else ""
            provider = mapping.provider

            lock_in_score = 0.0
            reasons: list[str] = []
            alternatives: list[str] = []

            # Check if service is proprietary
            proprietary = self._proprietary_services.get(provider, set())
            if service in proprietary:
                lock_in_score += 40.0
                reasons.append(f"Uses proprietary service: {service}")

            # Check for service equivalent availability
            equiv = self._find_service_equivalent(service, provider)
            if equiv:
                alternatives = self._get_alternatives(equiv, provider)
                if equiv.migration_complexity == PortabilityLevel.LOW:
                    lock_in_score += 20.0
                    reasons.append("Low portability: significant migration effort")
                elif equiv.migration_complexity == PortabilityLevel.LOCKED:
                    lock_in_score += 35.0
                    reasons.append("Locked: no direct equivalent on other providers")
            else:
                if service and provider not in (CloudProvider.ON_PREMISE, CloudProvider.EDGE):
                    lock_in_score += 15.0
                    reasons.append("No known cross-cloud equivalent mapping")

            # Stateful components are harder to migrate
            if mapping.is_stateful:
                lock_in_score += 15.0
                reasons.append("Stateful workload: data migration required")

            # Large data volumes increase migration difficulty
            if mapping.data_volume_gb > 1000:
                lock_in_score += 10.0
                reasons.append(f"Large data volume: {mapping.data_volume_gb:.0f} GB")
            elif mapping.data_volume_gb > 100:
                lock_in_score += 5.0
                reasons.append(f"Moderate data volume: {mapping.data_volume_gb:.0f} GB")

            lock_in_score = min(100.0, lock_in_score)
            portability = self._score_to_portability(lock_in_score)
            migration_hours = self._estimate_migration_hours(lock_in_score, mapping.data_volume_gb)

            assessments.append(VendorLockInAssessment(
                component_id=comp_id,
                provider=provider,
                service_name=service,
                lock_in_score=round(lock_in_score, 1),
                portability=portability,
                migration_effort_hours=round(migration_hours, 1),
                alternatives=alternatives,
                lock_in_reasons=reasons,
            ))

        return assessments

    # ------------------------------------------------------------------
    # Egress cost estimation
    # ------------------------------------------------------------------

    def estimate_egress_costs(
        self,
        cross_deps: list[CrossCloudDependency],
    ) -> list[EgressCostEstimate]:
        """Estimate egress costs for cross-cloud communication.

        Args:
            cross_deps: List of cross-cloud dependencies.

        Returns:
            List of EgressCostEstimate.
        """
        estimates: list[EgressCostEstimate] = []

        for dep in cross_deps:
            cost_per_gb = self._egress_costs.get(dep.source_provider, 0.09)
            monthly = dep.monthly_data_transfer_gb * cost_per_gb
            annual = monthly * 12

            estimates.append(EgressCostEstimate(
                source_provider=dep.source_provider,
                target_provider=dep.target_provider,
                source_region=dep.source_region,
                target_region=dep.target_region,
                monthly_data_gb=dep.monthly_data_transfer_gb,
                cost_per_gb=cost_per_gb,
                monthly_cost=round(monthly, 2),
                annual_cost=round(annual, 2),
            ))

        return estimates

    # ------------------------------------------------------------------
    # Failure mode analysis
    # ------------------------------------------------------------------

    def analyze_failure_mode(
        self,
        graph: InfraGraph,
        mappings: dict[str, CloudComponentMapping],
        failure_mode: FailureMode,
        target_provider: CloudProvider,
        target_region: str = "",
    ) -> FailureModeImpact:
        """Analyze impact of a specific failure mode.

        Args:
            graph: Infrastructure graph.
            mappings: Component-to-cloud mappings.
            failure_mode: Type of failure.
            target_provider: Affected provider.
            target_region: Affected region (for AZ/region outages).

        Returns:
            FailureModeImpact describing the blast radius.
        """
        total = len(graph.components)
        directly_affected: list[str] = []

        for comp_id, mapping in mappings.items():
            if self._is_affected_by_failure(mapping, failure_mode, target_provider, target_region):
                directly_affected.append(comp_id)

        # Cascade analysis
        cascade_affected: set[str] = set()
        for comp_id in directly_affected:
            affected = graph.get_all_affected(comp_id)
            cascade_affected.update(affected)
        cascade_affected -= set(directly_affected)

        all_affected = set(directly_affected) | cascade_affected
        surviving = [cid for cid in graph.components if cid not in all_affected]

        recovery_minutes = _RECOVERY_ESTIMATES.get(failure_mode, 60.0)

        impact_pct = (len(all_affected) / total * 100) if total > 0 else 0.0

        return FailureModeImpact(
            failure_mode=failure_mode,
            affected_provider=target_provider,
            affected_region=target_region,
            directly_affected_components=sorted(directly_affected),
            cascade_affected_components=sorted(cascade_affected),
            total_affected_count=len(all_affected),
            total_component_count=total,
            impact_percentage=round(impact_pct, 1),
            estimated_recovery_minutes=recovery_minutes,
            surviving_components=sorted(surviving),
        )

    def analyze_all_failure_modes(
        self,
        graph: InfraGraph,
        mappings: dict[str, CloudComponentMapping],
    ) -> list[FailureModeImpact]:
        """Analyze all relevant failure modes for the current topology.

        Args:
            graph: Infrastructure graph.
            mappings: Component-to-cloud mappings.

        Returns:
            List of FailureModeImpact for each relevant failure mode.
        """
        impacts: list[FailureModeImpact] = []

        # Collect unique providers and regions
        providers: set[CloudProvider] = set()
        regions: dict[CloudProvider, set[str]] = {}
        for m in mappings.values():
            providers.add(m.provider)
            regions.setdefault(m.provider, set()).add(m.region)

        # Provider-level outage for each provider
        for provider in providers:
            impact = self.analyze_failure_mode(
                graph, mappings, FailureMode.PROVIDER_OUTAGE, provider,
            )
            if impact.total_affected_count > 0:
                impacts.append(impact)

        # Region-level outage for each provider/region
        for provider, region_set in regions.items():
            for region in region_set:
                impact = self.analyze_failure_mode(
                    graph, mappings, FailureMode.REGION_OUTAGE, provider, region,
                )
                if impact.total_affected_count > 0:
                    impacts.append(impact)

        return impacts

    # ------------------------------------------------------------------
    # Portable workload identification
    # ------------------------------------------------------------------

    def identify_portable_workloads(
        self,
        mappings: dict[str, CloudComponentMapping],
    ) -> tuple[list[str], list[str]]:
        """Identify which workloads can be migrated between clouds.

        Args:
            mappings: Component-to-cloud mappings.

        Returns:
            Tuple of (portable_workload_ids, locked_workload_ids).
        """
        portable: list[str] = []
        locked: list[str] = []

        for comp_id, mapping in mappings.items():
            service = mapping.service_name.lower() if mapping.service_name else ""
            provider = mapping.provider

            # On-premise and edge are inherently portable (or not cloud-locked)
            if provider in (CloudProvider.ON_PREMISE, CloudProvider.EDGE):
                portable.append(comp_id)
                continue

            is_proprietary = service in self._proprietary_services.get(provider, set())
            has_equivalent = self._find_service_equivalent(service, provider) is not None

            if is_proprietary and not has_equivalent:
                locked.append(comp_id)
            elif mapping.is_stateful and mapping.data_volume_gb > 500:
                locked.append(comp_id)
            else:
                portable.append(comp_id)

        return sorted(portable), sorted(locked)

    # ------------------------------------------------------------------
    # Cross-cloud service mapping
    # ------------------------------------------------------------------

    def get_service_equivalents(
        self,
        service_name: str,
        source_provider: CloudProvider,
    ) -> dict[str, str]:
        """Get equivalent services across other cloud providers.

        Args:
            service_name: The source service name.
            source_provider: The source cloud provider.

        Returns:
            Dict mapping provider name to equivalent service name.
        """
        equiv = self._find_service_equivalent(service_name.lower(), source_provider)
        if not equiv:
            return {}

        result: dict[str, str] = {}
        provider_service_map = {
            CloudProvider.AWS: equiv.aws_service,
            CloudProvider.GCP: equiv.gcp_service,
            CloudProvider.AZURE: equiv.azure_service,
        }
        for provider, svc in provider_service_map.items():
            if provider != source_provider:
                result[provider.value] = svc

        return result

    # ------------------------------------------------------------------
    # Data sovereignty compliance
    # ------------------------------------------------------------------

    def check_data_sovereignty(
        self,
        mappings: dict[str, CloudComponentMapping],
    ) -> bool:
        """Check if all components comply with data sovereignty requirements.

        Args:
            mappings: Component-to-cloud mappings.

        Returns:
            True if all components comply, False otherwise.
        """
        for mapping in mappings.values():
            if mapping.data_sovereignty == DataSovereigntyRegion.GLOBAL:
                continue

            allowed_regions = _SOVEREIGNTY_GEO_MAP.get(mapping.data_sovereignty, set())
            if not allowed_regions:
                continue

            if mapping.region not in allowed_regions:
                logger.warning(
                    "Component %s in region %s violates %s data sovereignty",
                    mapping.component_id, mapping.region, mapping.data_sovereignty.value,
                )
                return False

        return True

    def get_sovereignty_violations(
        self,
        mappings: dict[str, CloudComponentMapping],
    ) -> list[dict[str, str]]:
        """Get detailed data sovereignty violations.

        Args:
            mappings: Component-to-cloud mappings.

        Returns:
            List of violation dicts with component_id, region,
            required_sovereignty, and message.
        """
        violations: list[dict[str, str]] = []

        for mapping in mappings.values():
            if mapping.data_sovereignty == DataSovereigntyRegion.GLOBAL:
                continue

            allowed_regions = _SOVEREIGNTY_GEO_MAP.get(mapping.data_sovereignty, set())
            if not allowed_regions:
                continue

            if mapping.region not in allowed_regions:
                violations.append({
                    "component_id": mapping.component_id,
                    "region": mapping.region,
                    "required_sovereignty": mapping.data_sovereignty.value,
                    "message": (
                        f"Component '{mapping.component_id}' is in region "
                        f"'{mapping.region}' but requires {mapping.data_sovereignty.value} "
                        f"data sovereignty."
                    ),
                })

        return violations

    # ------------------------------------------------------------------
    # DR posture analysis
    # ------------------------------------------------------------------

    def analyze_dr_posture(
        self,
        dr_posture: DRPosture,
        graph: InfraGraph,
        mappings: dict[str, CloudComponentMapping],
    ) -> dict:
        """Analyze disaster recovery posture across clouds.

        Args:
            dr_posture: Current DR configuration.
            graph: Infrastructure graph.
            mappings: Component-to-cloud mappings.

        Returns:
            Dict with readiness_score, gaps, and recommendations.
        """
        score = 0.0
        gaps: list[str] = []
        recs: list[str] = []

        # Mode scoring
        mode_scores: dict[DRMode, float] = {
            DRMode.ACTIVE_ACTIVE: 30.0,
            DRMode.ACTIVE_PASSIVE: 22.0,
            DRMode.PILOT_LIGHT: 15.0,
            DRMode.BACKUP_RESTORE: 8.0,
            DRMode.NONE: 0.0,
        }
        score += mode_scores.get(dr_posture.mode, 0.0)

        if dr_posture.mode == DRMode.NONE:
            gaps.append("No disaster recovery strategy configured")
            recs.append("Implement at least active-passive DR across clouds")

        # Cross-provider DR
        if dr_posture.dr_provider and dr_posture.dr_provider != dr_posture.primary_provider:
            score += 20.0
        elif dr_posture.dr_provider:
            score += 10.0
            recs.append(
                "DR is on the same provider as primary. Consider cross-provider DR "
                "for provider-level outage protection."
            )
        else:
            gaps.append("No DR provider configured")

        # Cross-region DR
        if dr_posture.dr_region and dr_posture.dr_region != dr_posture.primary_region:
            score += 15.0
        elif dr_posture.dr_region:
            score += 5.0
            recs.append("DR region is the same as primary. Use a different region.")
        else:
            if dr_posture.mode != DRMode.NONE:
                gaps.append("No DR region configured")

        # Automated failover
        if dr_posture.failover_automated:
            score += 15.0
        else:
            if dr_posture.mode in (DRMode.ACTIVE_ACTIVE, DRMode.ACTIVE_PASSIVE):
                recs.append("Enable automated failover to reduce RTO")

        # RPO/RTO targets
        if dr_posture.rpo_seconds > 0 and dr_posture.rto_seconds > 0:
            if dr_posture.rpo_seconds <= 60:
                score += 10.0
            elif dr_posture.rpo_seconds <= 300:
                score += 5.0
            else:
                recs.append(
                    f"RPO is {dr_posture.rpo_seconds}s. Consider reducing to < 60s "
                    f"for critical workloads."
                )

            if dr_posture.rto_seconds <= 300:
                score += 10.0
            elif dr_posture.rto_seconds <= 1800:
                score += 5.0
            else:
                recs.append(
                    f"RTO is {dr_posture.rto_seconds}s. Consider reducing to < 300s "
                    f"for critical workloads."
                )

        # Testing recency
        if dr_posture.last_tested:
            score = min(100.0, score)
        else:
            gaps.append("DR plan has never been tested")
            recs.append("Test your DR plan regularly (at least quarterly)")

        score = max(0.0, min(100.0, score))

        return {
            "readiness_score": round(score, 1),
            "mode": dr_posture.mode.value,
            "gaps": gaps,
            "recommendations": recs,
        }

    # ------------------------------------------------------------------
    # Cost vs resilience tradeoff
    # ------------------------------------------------------------------

    def analyze_cost_resilience_tradeoff(
        self,
        graph: InfraGraph,
        mappings: dict[str, CloudComponentMapping],
        dr_posture: DRPosture | None = None,
    ) -> dict:
        """Analyze the cost vs resilience tradeoff for multi-cloud.

        Args:
            graph: Infrastructure graph.
            mappings: Component-to-cloud mappings.
            dr_posture: Optional DR posture.

        Returns:
            Dict with current costs, resilience score, and improvement options.
        """
        cross_deps = self.identify_cross_cloud_dependencies(graph, mappings)
        egress_costs = self.estimate_egress_costs(cross_deps)
        total_egress = sum(e.monthly_cost for e in egress_costs)

        assessments = self.assess_vendor_lock_in(graph, mappings)
        avg_lock_in = self._calc_average_lock_in(assessments)

        provider_diversity = self._calc_provider_diversity(mappings)
        dr_score = self._calc_dr_readiness(dr_posture)

        improvements: list[dict] = []

        # Suggestion: add another provider
        if provider_diversity < 50.0:
            improvements.append({
                "action": "Add secondary cloud provider",
                "estimated_monthly_cost_increase": total_egress * 0.3,
                "resilience_improvement": 20.0,
                "description": (
                    "Distribute workloads across 2+ providers to reduce "
                    "single-provider risk."
                ),
            })

        # Suggestion: implement DR
        if dr_score < 50.0:
            improvements.append({
                "action": "Implement cross-cloud DR",
                "estimated_monthly_cost_increase": total_egress + 200.0,
                "resilience_improvement": 25.0,
                "description": (
                    "Set up active-passive DR across cloud providers."
                ),
            })

        # Suggestion: reduce lock-in
        if avg_lock_in > 50.0:
            improvements.append({
                "action": "Reduce vendor lock-in",
                "estimated_monthly_cost_increase": 0.0,
                "resilience_improvement": 15.0,
                "description": (
                    "Replace proprietary services with provider-agnostic "
                    "alternatives (Kubernetes, PostgreSQL, etc.)."
                ),
            })

        return {
            "current_monthly_egress_cost": round(total_egress, 2),
            "current_resilience_score": round(
                self._calc_overall_score(
                    provider_diversity,
                    self._calc_geographic_distribution(mappings),
                    avg_lock_in,
                    dr_score,
                ), 1,
            ),
            "vendor_lock_in_score": round(avg_lock_in, 1),
            "provider_diversity_score": round(provider_diversity, 1),
            "improvements": improvements,
        }

    # ------------------------------------------------------------------
    # Network latency modeling
    # ------------------------------------------------------------------

    def model_cross_cloud_latency(
        self,
        mappings: dict[str, CloudComponentMapping],
        source_id: str,
        target_id: str,
    ) -> dict:
        """Model network latency between two components.

        Args:
            mappings: Component-to-cloud mappings.
            source_id: Source component ID.
            target_id: Target component ID.

        Returns:
            Dict with estimated latency, classification, and recommendation.
        """
        src = mappings.get(source_id)
        tgt = mappings.get(target_id)

        if not src or not tgt:
            return {
                "source_id": source_id,
                "target_id": target_id,
                "estimated_latency_ms": 0.0,
                "classification": "unknown",
                "recommendation": "Component mapping not found.",
            }

        latency = self._estimate_latency(src, tgt)

        if latency <= 2.0:
            classification = "same_region"
            rec = "Low latency. No action needed."
        elif latency <= 20.0:
            classification = "cross_provider_same_geo"
            rec = "Acceptable latency for most workloads."
        elif latency <= 100.0:
            classification = "cross_region"
            rec = "Consider caching or async communication for latency-sensitive paths."
        else:
            classification = "cross_geography"
            rec = (
                "High latency. Use CDN, edge caching, or co-locate "
                "tightly coupled services."
            )

        return {
            "source_id": source_id,
            "target_id": target_id,
            "estimated_latency_ms": round(latency, 1),
            "classification": classification,
            "recommendation": rec,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _estimate_latency(
        self,
        src: CloudComponentMapping,
        tgt: CloudComponentMapping,
    ) -> float:
        """Estimate network latency between two cloud mappings."""
        if src.provider == tgt.provider:
            if src.region == tgt.region:
                return 1.5
            return 80.0

        # Cross-provider: rough geographic estimate
        src_geo = self._region_to_geography(src.region)
        tgt_geo = self._region_to_geography(tgt.region)

        if src_geo == tgt_geo and src_geo != "unknown":
            return 15.0
        return 200.0

    def _region_to_geography(self, region: str) -> str:
        """Map a region name to a geographic area."""
        region_lower = region.lower()
        us_patterns = ["us-", "us_", "central", "east", "west"]
        eu_patterns = ["eu-", "europe", "north", "germany", "france", "sweden"]
        apac_patterns = ["ap-", "asia", "japan", "singapore", "australia", "india"]

        # Check US
        if any(p in region_lower for p in ["us-", "us_", "eastus", "westus", "centralus"]):
            return "us"
        if "us-central" in region_lower or "us-east" in region_lower or "us-west" in region_lower:
            return "us"

        # Check EU
        if any(p in region_lower for p in ["eu-", "europe", "westeurope", "northeurope"]):
            return "eu"

        # Check APAC
        if any(p in region_lower for p in ["ap-", "asia", "japan", "southeast"]):
            return "apac"

        return "unknown"

    def _is_affected_by_failure(
        self,
        mapping: CloudComponentMapping,
        failure_mode: FailureMode,
        target_provider: CloudProvider,
        target_region: str,
    ) -> bool:
        """Determine if a component is directly affected by a failure mode."""
        if failure_mode == FailureMode.PROVIDER_OUTAGE:
            return mapping.provider == target_provider

        if failure_mode == FailureMode.REGION_OUTAGE:
            return mapping.provider == target_provider and mapping.region == target_region

        if failure_mode == FailureMode.AZ_OUTAGE:
            return (
                mapping.provider == target_provider
                and mapping.region == target_region
                and mapping.availability_zone == target_region
            )

        if failure_mode == FailureMode.NETWORK_PARTITION:
            return mapping.provider == target_provider

        if failure_mode == FailureMode.SERVICE_DEGRADATION:
            return mapping.provider == target_provider and mapping.region == target_region

        if failure_mode == FailureMode.DNS_FAILURE:
            return mapping.provider == target_provider

        if failure_mode == FailureMode.CONTROL_PLANE_FAILURE:
            return mapping.provider == target_provider

        return False

    def _find_service_equivalent(
        self,
        service_name: str,
        provider: CloudProvider,
    ) -> ServiceEquivalent | None:
        """Find a service equivalent entry for a given service."""
        for equiv in self._service_equivalents:
            svc_map = {
                CloudProvider.AWS: equiv.aws_service,
                CloudProvider.GCP: equiv.gcp_service,
                CloudProvider.AZURE: equiv.azure_service,
            }
            svc = svc_map.get(provider, "")
            if svc and svc == service_name:
                return equiv
        return None

    def _get_alternatives(
        self,
        equiv: ServiceEquivalent,
        source_provider: CloudProvider,
    ) -> list[str]:
        """Get alternative services from other providers."""
        alts: list[str] = []
        provider_map = {
            CloudProvider.AWS: equiv.aws_service,
            CloudProvider.GCP: equiv.gcp_service,
            CloudProvider.AZURE: equiv.azure_service,
        }
        for provider, svc in provider_map.items():
            if provider != source_provider and svc:
                alts.append(f"{provider.value}:{svc}")
        return alts

    def _score_to_portability(self, lock_in_score: float) -> PortabilityLevel:
        """Convert a lock-in score to a portability level."""
        if lock_in_score <= 20.0:
            return PortabilityLevel.HIGH
        if lock_in_score <= 45.0:
            return PortabilityLevel.MEDIUM
        if lock_in_score <= 70.0:
            return PortabilityLevel.LOW
        return PortabilityLevel.LOCKED

    def _estimate_migration_hours(self, lock_in_score: float, data_gb: float) -> float:
        """Estimate migration effort in hours."""
        base_hours = lock_in_score * 0.5
        data_hours = math.log2(max(1.0, data_gb)) * 2.0
        return base_hours + data_hours

    def _calc_provider_diversity(
        self,
        mappings: dict[str, CloudComponentMapping],
    ) -> float:
        """Calculate provider diversity score (0-100)."""
        if not mappings:
            return 0.0

        providers: dict[str, int] = {}
        for m in mappings.values():
            pv = m.provider.value
            providers[pv] = providers.get(pv, 0) + 1

        total = sum(providers.values())
        if total == 0:
            return 0.0

        # Single provider = low score
        num_providers = len(providers)
        if num_providers == 1:
            return 20.0

        # Shannon diversity index (normalized)
        h = 0.0
        for count in providers.values():
            p = count / total
            if p > 0:
                h -= p * math.log2(p)

        max_h = math.log2(num_providers) if num_providers > 1 else 1.0
        evenness = h / max_h if max_h > 0 else 0.0

        # Score: base from provider count + evenness bonus
        base_score = min(50.0, num_providers * 15.0)
        evenness_score = evenness * 50.0

        return min(100.0, base_score + evenness_score)

    def _calc_geographic_distribution(
        self,
        mappings: dict[str, CloudComponentMapping],
    ) -> float:
        """Calculate geographic distribution score (0-100)."""
        if not mappings:
            return 0.0

        geos: set[str] = set()
        regions: set[str] = set()
        for m in mappings.values():
            geos.add(self._region_to_geography(m.region))
            regions.add(f"{m.provider.value}:{m.region}")

        geos.discard("unknown")

        if len(geos) == 0:
            return 10.0
        if len(geos) == 1:
            region_score = min(30.0, len(regions) * 10.0)
            return 20.0 + region_score

        # Multiple geographies
        geo_score = min(50.0, len(geos) * 20.0)
        region_score = min(50.0, len(regions) * 8.0)
        return min(100.0, geo_score + region_score)

    def _calc_average_lock_in(
        self,
        assessments: list[VendorLockInAssessment],
    ) -> float:
        """Calculate average vendor lock-in score."""
        if not assessments:
            return 0.0
        return sum(a.lock_in_score for a in assessments) / len(assessments)

    def _calc_dr_readiness(self, dr_posture: DRPosture | None) -> float:
        """Calculate DR readiness score (0-100)."""
        if not dr_posture:
            return 0.0

        mode_scores: dict[DRMode, float] = {
            DRMode.ACTIVE_ACTIVE: 40.0,
            DRMode.ACTIVE_PASSIVE: 30.0,
            DRMode.PILOT_LIGHT: 20.0,
            DRMode.BACKUP_RESTORE: 10.0,
            DRMode.NONE: 0.0,
        }

        score = mode_scores.get(dr_posture.mode, 0.0)

        if dr_posture.failover_automated:
            score += 20.0
        if dr_posture.dr_provider and dr_posture.dr_provider != dr_posture.primary_provider:
            score += 20.0
        elif dr_posture.dr_provider:
            score += 10.0
        if dr_posture.rpo_seconds > 0 and dr_posture.rpo_seconds <= 60:
            score += 10.0
        elif dr_posture.rpo_seconds > 0 and dr_posture.rpo_seconds <= 300:
            score += 5.0
        if dr_posture.last_tested:
            score += 10.0

        return min(100.0, score)

    def _calc_overall_score(
        self,
        provider_diversity: float,
        geo_distribution: float,
        avg_lock_in: float,
        dr_readiness: float,
    ) -> float:
        """Calculate overall multi-cloud resilience score (0-100).

        Weighted formula:
        - Provider diversity:     25%
        - Geographic distribution: 25%
        - Lock-in (inverted):     25%
        - DR readiness:           25%
        """
        lock_in_inverted = 100.0 - avg_lock_in

        score = (
            provider_diversity * 0.25
            + geo_distribution * 0.25
            + lock_in_inverted * 0.25
            + dr_readiness * 0.25
        )

        return max(0.0, min(100.0, score))

    def _generate_recommendations(
        self,
        provider_diversity: float,
        geo_distribution: float,
        avg_lock_in: float,
        dr_readiness: float,
        cross_deps: list[CrossCloudDependency],
        failure_impacts: list[FailureModeImpact],
        sovereignty_ok: bool,
        total_egress: float,
    ) -> list[str]:
        """Generate recommendations based on analysis results."""
        recs: list[str] = []

        if provider_diversity < 30.0:
            recs.append(
                "Low provider diversity. Distribute workloads across at least "
                "2 cloud providers to reduce single-provider failure risk."
            )

        if geo_distribution < 30.0:
            recs.append(
                "Limited geographic distribution. Deploy across multiple "
                "geographic regions for better disaster recovery."
            )

        if avg_lock_in > 60.0:
            recs.append(
                "High vendor lock-in. Replace proprietary services with "
                "cloud-agnostic alternatives (Kubernetes, PostgreSQL, etc.)."
            )

        if dr_readiness < 30.0:
            recs.append(
                "DR readiness is low. Implement cross-cloud disaster recovery "
                "with automated failover."
            )

        # Check for critical cross-cloud dependencies
        critical_cross = [d for d in cross_deps if d.is_critical]
        if critical_cross:
            recs.append(
                f"{len(critical_cross)} critical dependencies cross cloud "
                f"boundaries. Ensure redundancy and fallback paths."
            )

        # Check for high-impact failure modes
        for impact in failure_impacts:
            if impact.impact_percentage > 80.0:
                recs.append(
                    f"{impact.failure_mode.value} on {impact.affected_provider.value} "
                    f"would affect {impact.impact_percentage:.0f}% of components. "
                    f"Add redundancy across providers."
                )

        if not sovereignty_ok:
            recs.append(
                "Data sovereignty violations detected. Move affected components "
                "to compliant regions."
            )

        if total_egress > 1000.0:
            recs.append(
                f"High monthly egress costs (${total_egress:.0f}). Consider "
                f"using private interconnects or reducing cross-cloud data transfer."
            )

        return recs

    def generate_summary_report(
        self,
        result: ResilienceAnalysisResult,
    ) -> str:
        """Generate a human-readable summary report.

        Args:
            result: The analysis result.

        Returns:
            Multi-line text summary.
        """
        lines: list[str] = [
            "=== Multi-Cloud Resilience Analysis Report ===",
            "",
            f"Timestamp: {result.timestamp}",
            f"Overall Resilience Score: {result.overall_score}/100",
            "",
            "--- Score Breakdown ---",
            f"  Provider Diversity:       {result.provider_diversity_score}/100",
            f"  Geographic Distribution:  {result.geographic_distribution_score}/100",
            f"  Vendor Lock-in (lower=better): {result.vendor_lock_in_score}/100",
            f"  DR Readiness:             {result.dr_readiness_score}/100",
            "",
            f"Data Sovereignty Compliant: {'Yes' if result.data_sovereignty_compliant else 'No'}",
            f"Cross-Cloud Dependencies:   {result.cross_cloud_dependency_count}",
            f"Monthly Egress Cost:        ${result.total_monthly_egress_cost:.2f}",
            "",
            f"Portable Workloads:  {len(result.portable_workloads)}",
            f"Locked Workloads:    {len(result.locked_workloads)}",
        ]

        if result.failure_mode_impacts:
            lines.append("")
            lines.append("--- Failure Mode Impacts ---")
            for impact in result.failure_mode_impacts:
                lines.append(
                    f"  {impact.failure_mode.value} ({impact.affected_provider.value}): "
                    f"{impact.impact_percentage:.0f}% affected "
                    f"({impact.total_affected_count}/{impact.total_component_count})"
                )

        if result.recommendations:
            lines.append("")
            lines.append("--- Recommendations ---")
            for i, rec in enumerate(result.recommendations, 1):
                lines.append(f"  {i}. {rec}")

        return "\n".join(lines)
