# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Multi-Cloud Resilience Comparator.

Simulates the same architecture across AWS/GCP/Azure and quantifies
resilience differences between cloud providers.  Helps organisations make
data-driven decisions about cloud provider selection, multi-cloud
strategies, and cloud migration.
"""

from __future__ import annotations

import logging
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CloudProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    ON_PREMISE = "on_premise"


class ServiceCategory(str, Enum):
    COMPUTE = "compute"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    STORAGE = "storage"
    LOAD_BALANCER = "load_balancer"
    DNS = "dns"
    CDN = "cdn"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_COMPONENT_TO_CATEGORY: dict[ComponentType, ServiceCategory] = {
    ComponentType.APP_SERVER: ServiceCategory.COMPUTE,
    ComponentType.WEB_SERVER: ServiceCategory.COMPUTE,
    ComponentType.DATABASE: ServiceCategory.DATABASE,
    ComponentType.CACHE: ServiceCategory.CACHE,
    ComponentType.QUEUE: ServiceCategory.QUEUE,
    ComponentType.STORAGE: ServiceCategory.STORAGE,
    ComponentType.LOAD_BALANCER: ServiceCategory.LOAD_BALANCER,
    ComponentType.DNS: ServiceCategory.DNS,
}


class CloudServiceMapping(BaseModel):
    """Maps a service category to equivalent services across providers."""

    category: ServiceCategory
    aws_service: str
    gcp_service: str
    azure_service: str
    aws_sla: float = 99.9
    gcp_sla: float = 99.9
    azure_sla: float = 99.9


class ProviderResilienceScore(BaseModel):
    """Resilience score breakdown for a single cloud provider."""

    provider: CloudProvider
    overall_score: float = Field(default=0.0, ge=0, le=100)
    availability_score: float = Field(default=0.0, ge=0, le=100)
    recovery_score: float = Field(default=0.0, ge=0, le=100)
    redundancy_score: float = Field(default=0.0, ge=0, le=100)
    cost_normalized_score: float = Field(default=0.0, ge=0, le=100)


class ComparisonResult(BaseModel):
    """Per-category comparison across providers."""

    category: ServiceCategory
    scores_by_provider: dict[str, ProviderResilienceScore] = Field(
        default_factory=dict
    )
    winner: CloudProvider = CloudProvider.AWS
    margin: float = 0.0
    analysis: str = ""


class MigrationRisk(BaseModel):
    """Risk assessment for migrating between two cloud providers."""

    source_provider: CloudProvider
    target_provider: CloudProvider
    risk_score: float = Field(default=0.0, ge=0, le=1)
    data_transfer_risk: float = Field(default=0.0, ge=0, le=1)
    compatibility_issues: list[str] = Field(default_factory=list)
    estimated_downtime_hours: float = 0.0


class CloudComparisonReport(BaseModel):
    """Full multi-cloud resilience comparison report."""

    components_analyzed: int = 0
    provider_rankings: list[ProviderResilienceScore] = Field(
        default_factory=list
    )
    category_results: list[ComparisonResult] = Field(default_factory=list)
    migration_risks: list[MigrationRisk] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    best_multi_cloud_strategy: str = ""


# ---------------------------------------------------------------------------
# Built-in service mappings
# ---------------------------------------------------------------------------

_DEFAULT_MAPPINGS: list[CloudServiceMapping] = [
    CloudServiceMapping(
        category=ServiceCategory.COMPUTE,
        aws_service="EC2", gcp_service="Compute Engine",
        azure_service="Virtual Machines",
        aws_sla=99.99, gcp_sla=99.99, azure_sla=99.99,
    ),
    CloudServiceMapping(
        category=ServiceCategory.DATABASE,
        aws_service="RDS", gcp_service="Cloud SQL",
        azure_service="Azure SQL",
        aws_sla=99.95, gcp_sla=99.95, azure_sla=99.99,
    ),
    CloudServiceMapping(
        category=ServiceCategory.CACHE,
        aws_service="ElastiCache", gcp_service="Memorystore",
        azure_service="Azure Cache",
        aws_sla=99.9, gcp_sla=99.9, azure_sla=99.9,
    ),
    CloudServiceMapping(
        category=ServiceCategory.QUEUE,
        aws_service="SQS", gcp_service="Pub/Sub",
        azure_service="Service Bus",
        aws_sla=99.9, gcp_sla=99.95, azure_sla=99.9,
    ),
    CloudServiceMapping(
        category=ServiceCategory.STORAGE,
        aws_service="S3", gcp_service="Cloud Storage",
        azure_service="Blob Storage",
        aws_sla=99.99, gcp_sla=99.95, azure_sla=99.9,
    ),
    CloudServiceMapping(
        category=ServiceCategory.LOAD_BALANCER,
        aws_service="ALB", gcp_service="Cloud LB",
        azure_service="Azure LB",
        aws_sla=99.99, gcp_sla=99.99, azure_sla=99.99,
    ),
    CloudServiceMapping(
        category=ServiceCategory.DNS,
        aws_service="Route53", gcp_service="Cloud DNS",
        azure_service="Azure DNS",
        aws_sla=100.0, gcp_sla=100.0, azure_sla=100.0,
    ),
    CloudServiceMapping(
        category=ServiceCategory.CDN,
        aws_service="CloudFront", gcp_service="Cloud CDN",
        azure_service="Azure CDN",
        aws_sla=99.9, gcp_sla=99.9, azure_sla=99.9,
    ),
]


# ---------------------------------------------------------------------------
# CloudComparator
# ---------------------------------------------------------------------------


class CloudComparator:
    """Compare resilience of the same architecture across cloud providers."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._mappings: dict[ServiceCategory, CloudServiceMapping] = {
            m.category: m for m in _DEFAULT_MAPPINGS
        }

    # -- public API --

    def get_service_mapping(
        self, category: ServiceCategory
    ) -> CloudServiceMapping:
        """Return the service mapping for *category*."""
        return self._mappings[category]

    def score_provider(
        self, provider: CloudProvider
    ) -> ProviderResilienceScore:
        """Compute an overall resilience score for *provider* based on the graph."""
        if not self.graph.components:
            return ProviderResilienceScore(provider=provider)

        availability = self._availability_score(provider)
        recovery = self._recovery_score()
        redundancy = self._redundancy_score()
        cost_norm = self._cost_normalized_score(provider)
        overall = (
            availability * 0.35
            + recovery * 0.25
            + redundancy * 0.25
            + cost_norm * 0.15
        )
        return ProviderResilienceScore(
            provider=provider,
            overall_score=round(min(100.0, max(0.0, overall)), 2),
            availability_score=round(availability, 2),
            recovery_score=round(recovery, 2),
            redundancy_score=round(redundancy, 2),
            cost_normalized_score=round(cost_norm, 2),
        )

    def compare_category(
        self, category: ServiceCategory
    ) -> ComparisonResult:
        """Compare providers for a specific service *category*."""
        mapping = self._mappings[category]
        providers = [CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE]
        scores: dict[str, ProviderResilienceScore] = {}
        for p in providers:
            sla = self._sla_for_provider(mapping, p)
            avail = min(100.0, sla)
            recovery = self._recovery_score()
            redundancy = self._redundancy_score()
            cost_norm = self._cost_normalized_score(p)
            overall = (
                avail * 0.35
                + recovery * 0.25
                + redundancy * 0.25
                + cost_norm * 0.15
            )
            scores[p.value] = ProviderResilienceScore(
                provider=p,
                overall_score=round(min(100.0, max(0.0, overall)), 2),
                availability_score=round(avail, 2),
                recovery_score=round(recovery, 2),
                redundancy_score=round(redundancy, 2),
                cost_normalized_score=round(cost_norm, 2),
            )

        best = max(scores.values(), key=lambda s: s.overall_score)
        sorted_scores = sorted(
            scores.values(), key=lambda s: s.overall_score, reverse=True
        )
        margin = (
            sorted_scores[0].overall_score - sorted_scores[1].overall_score
            if len(sorted_scores) >= 2
            else 0.0
        )
        analysis = (
            f"{best.provider.value.upper()} leads in {category.value} "
            f"with score {best.overall_score:.1f} "
            f"(margin {margin:.2f})"
        )
        return ComparisonResult(
            category=category,
            scores_by_provider=scores,
            winner=best.provider,
            margin=round(margin, 2),
            analysis=analysis,
        )

    def assess_migration_risk(
        self,
        source: CloudProvider,
        target: CloudProvider,
    ) -> MigrationRisk:
        """Assess the risk of migrating from *source* to *target* provider."""
        if source == target:
            return MigrationRisk(
                source_provider=source,
                target_provider=target,
                risk_score=0.0,
                data_transfer_risk=0.0,
                compatibility_issues=[],
                estimated_downtime_hours=0.0,
            )

        issues: list[str] = []
        comp_count = len(self.graph.components)
        db_count = sum(
            1
            for c in self.graph.components.values()
            if c.type == ComponentType.DATABASE
        )
        has_queue = any(
            c.type == ComponentType.QUEUE
            for c in self.graph.components.values()
        )

        # Base risk increases with component count
        base_risk = min(1.0, comp_count * 0.05)

        # Data transfer risk based on databases
        data_risk = min(1.0, db_count * 0.2) if db_count > 0 else 0.1

        # Compatibility issues
        if source == CloudProvider.ON_PREMISE or target == CloudProvider.ON_PREMISE:
            issues.append(
                "On-premise migration requires network/VPN reconfiguration"
            )
            base_risk = min(1.0, base_risk + 0.2)

        if db_count > 0:
            issues.append(
                f"{db_count} database(s) require schema compatibility review"
            )

        if has_queue:
            issues.append("Message queue migration may cause message loss")

        # Unhealthy components add risk
        unhealthy = sum(
            1
            for c in self.graph.components.values()
            if c.health != HealthStatus.HEALTHY
        )
        if unhealthy > 0:
            issues.append(
                f"{unhealthy} component(s) are not healthy; "
                "migrate after stabilisation"
            )
            base_risk = min(1.0, base_risk + 0.1)

        downtime = max(1.0, comp_count * 0.5 + db_count * 2.0)

        return MigrationRisk(
            source_provider=source,
            target_provider=target,
            risk_score=round(min(1.0, base_risk), 2),
            data_transfer_risk=round(min(1.0, data_risk), 2),
            compatibility_issues=issues,
            estimated_downtime_hours=round(downtime, 1),
        )

    def recommend_multi_cloud_strategy(self) -> str:
        """Recommend a multi-cloud strategy based on the graph."""
        comp_count = len(self.graph.components)
        if comp_count == 0:
            return "No components to analyse; add infrastructure first."

        db_count = sum(
            1
            for c in self.graph.components.values()
            if c.type == ComponentType.DATABASE
        )
        has_cdn = any(
            c.type == ComponentType.DNS or "cdn" in c.id.lower()
            for c in self.graph.components.values()
        )

        if comp_count <= 3:
            return (
                "Single-cloud recommended for small architectures "
                "to minimise operational overhead."
            )

        if db_count >= 2 and has_cdn:
            return (
                "Active-Active multi-cloud recommended: "
                "use AWS for compute, GCP for data analytics, "
                "and Azure for enterprise integrations."
            )

        if db_count >= 1:
            return (
                "Primary-DR multi-cloud recommended: "
                "primary workload on one provider with "
                "warm standby on a second provider."
            )

        return (
            "Cloud-agnostic containerised strategy recommended: "
            "use Kubernetes to maintain portability across providers."
        )

    def generate_report(self) -> CloudComparisonReport:
        """Generate a full comparison report."""
        providers = [CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE]
        rankings = sorted(
            [self.score_provider(p) for p in providers],
            key=lambda s: s.overall_score,
            reverse=True,
        )

        category_results: list[ComparisonResult] = []
        used_categories: set[ServiceCategory] = set()
        for comp in self.graph.components.values():
            cat = _COMPONENT_TO_CATEGORY.get(comp.type)
            if cat and cat not in used_categories:
                used_categories.add(cat)
                category_results.append(self.compare_category(cat))

        migration_risks: list[MigrationRisk] = []
        for i, src in enumerate(providers):
            for tgt in providers[i + 1 :]:
                migration_risks.append(
                    self.assess_migration_risk(src, tgt)
                )

        recommendations = self._build_recommendations(
            rankings, category_results
        )
        strategy = self.recommend_multi_cloud_strategy()

        return CloudComparisonReport(
            components_analyzed=len(self.graph.components),
            provider_rankings=rankings,
            category_results=category_results,
            migration_risks=migration_risks,
            recommendations=recommendations,
            best_multi_cloud_strategy=strategy,
        )

    # -- private helpers --

    def _sla_for_provider(
        self, mapping: CloudServiceMapping, provider: CloudProvider
    ) -> float:
        if provider == CloudProvider.AWS:
            return mapping.aws_sla
        if provider == CloudProvider.GCP:
            return mapping.gcp_sla
        if provider == CloudProvider.AZURE:
            return mapping.azure_sla
        return 99.0  # ON_PREMISE default

    def _availability_score(self, provider: CloudProvider) -> float:
        """Average SLA across categories relevant to graph components."""
        slas: list[float] = []
        for comp in self.graph.components.values():
            cat = _COMPONENT_TO_CATEGORY.get(comp.type)
            if cat and cat in self._mappings:
                slas.append(
                    self._sla_for_provider(self._mappings[cat], provider)
                )
        if not slas:
            return 99.0
        return sum(slas) / len(slas)

    def _recovery_score(self) -> float:
        """Score (0-100) based on failover and autoscaling coverage."""
        if not self.graph.components:
            return 0.0
        scores: list[float] = []
        for comp in self.graph.components.values():
            s = 0.0
            if comp.failover.enabled:
                s += 50.0
            if comp.autoscaling.enabled:
                s += 30.0
            if comp.replicas >= 2:
                s += 20.0
            scores.append(min(100.0, s))
        return sum(scores) / len(scores)

    def _redundancy_score(self) -> float:
        """Score (0-100) based on replica counts and failover."""
        if not self.graph.components:
            return 0.0
        scores: list[float] = []
        for comp in self.graph.components.values():
            if comp.replicas >= 3 and comp.failover.enabled:
                scores.append(100.0)
            elif comp.replicas >= 2 and comp.failover.enabled:
                scores.append(80.0)
            elif comp.replicas >= 2 or comp.failover.enabled:
                scores.append(50.0)
            else:
                scores.append(20.0)
        return sum(scores) / len(scores)

    def _cost_normalized_score(self, provider: CloudProvider) -> float:
        """Cost normalisation score; lower SLA providers score lower."""
        slas: list[float] = []
        for cat, mapping in self._mappings.items():
            slas.append(self._sla_for_provider(mapping, provider))
        if not slas:
            return 50.0
        avg = sum(slas) / len(slas)
        # Map 99-100 -> 0-100
        return min(100.0, max(0.0, (avg - 99.0) * 100.0))

    def _build_recommendations(
        self,
        rankings: list[ProviderResilienceScore],
        category_results: list[ComparisonResult],
    ) -> list[str]:
        recs: list[str] = []
        if rankings:
            top = rankings[0]
            recs.append(
                f"{top.provider.value.upper()} ranks highest overall "
                f"with score {top.overall_score:.1f}."
            )
        for cr in category_results:
            if cr.margin > 1.0:
                recs.append(
                    f"For {cr.category.value}, consider "
                    f"{cr.winner.value.upper()} "
                    f"(leads by {cr.margin:.2f} points)."
                )
        if not self.graph.components:
            recs.append("Add components to get meaningful recommendations.")
        return recs
