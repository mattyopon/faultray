"""Multi-Tenant Isolation Verifier.

Simulates and verifies tenant isolation in multi-tenant architectures.
Detects noisy-neighbor effects, shared-resource bottlenecks, data-leak
risks, and recommends isolation upgrades.  Designed for SaaS platforms
that need to prove tenant workloads cannot impact each other.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IsolationLevel(str, Enum):
    """Degree of isolation between tenants."""

    NONE = "none"
    LOGICAL = "logical"
    NAMESPACE = "namespace"
    PROCESS = "process"
    CONTAINER = "container"
    VM = "vm"
    PHYSICAL = "physical"


class TenantTier(str, Enum):
    """Commercial tier of a tenant."""

    FREE = "free"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    DEDICATED = "dedicated"


class NoiseType(str, Enum):
    """Types of noisy-neighbor behaviour."""

    CPU_HOG = "cpu_hog"
    MEMORY_HOG = "memory_hog"
    DISK_IO_FLOOD = "disk_io_flood"
    NETWORK_FLOOD = "network_flood"
    CONNECTION_POOL_EXHAUSTION = "connection_pool_exhaustion"
    QUERY_STORM = "query_storm"
    CACHE_THRASH = "cache_thrash"
    LOCK_CONTENTION = "lock_contention"


# ---------------------------------------------------------------------------
# Isolation-level ranking helpers
# ---------------------------------------------------------------------------

_ISOLATION_RANK: dict[IsolationLevel, int] = {
    IsolationLevel.NONE: 0,
    IsolationLevel.LOGICAL: 1,
    IsolationLevel.NAMESPACE: 2,
    IsolationLevel.PROCESS: 3,
    IsolationLevel.CONTAINER: 4,
    IsolationLevel.VM: 5,
    IsolationLevel.PHYSICAL: 6,
}

_TIER_MIN_ISOLATION: dict[TenantTier, IsolationLevel] = {
    TenantTier.FREE: IsolationLevel.LOGICAL,
    TenantTier.BASIC: IsolationLevel.LOGICAL,
    TenantTier.PROFESSIONAL: IsolationLevel.NAMESPACE,
    TenantTier.ENTERPRISE: IsolationLevel.CONTAINER,
    TenantTier.DEDICATED: IsolationLevel.VM,
}

_NOISE_BASE_IMPACT: dict[NoiseType, float] = {
    NoiseType.CPU_HOG: 40.0,
    NoiseType.MEMORY_HOG: 50.0,
    NoiseType.DISK_IO_FLOOD: 35.0,
    NoiseType.NETWORK_FLOOD: 45.0,
    NoiseType.CONNECTION_POOL_EXHAUSTION: 60.0,
    NoiseType.QUERY_STORM: 55.0,
    NoiseType.CACHE_THRASH: 30.0,
    NoiseType.LOCK_CONTENTION: 50.0,
}

_NOISE_ERROR_RATE: dict[NoiseType, float] = {
    NoiseType.CPU_HOG: 2.0,
    NoiseType.MEMORY_HOG: 5.0,
    NoiseType.DISK_IO_FLOOD: 3.0,
    NoiseType.NETWORK_FLOOD: 8.0,
    NoiseType.CONNECTION_POOL_EXHAUSTION: 15.0,
    NoiseType.QUERY_STORM: 10.0,
    NoiseType.CACHE_THRASH: 1.0,
    NoiseType.LOCK_CONTENTION: 7.0,
}

_ISOLATION_ATTENUATION: dict[IsolationLevel, float] = {
    IsolationLevel.NONE: 1.0,
    IsolationLevel.LOGICAL: 0.8,
    IsolationLevel.NAMESPACE: 0.5,
    IsolationLevel.PROCESS: 0.3,
    IsolationLevel.CONTAINER: 0.15,
    IsolationLevel.VM: 0.05,
    IsolationLevel.PHYSICAL: 0.0,
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Tenant(BaseModel):
    """Represents one tenant in a multi-tenant deployment."""

    id: str
    name: str
    tier: TenantTier
    resource_quota: dict[str, float] = Field(default_factory=dict)
    current_usage: dict[str, float] = Field(default_factory=dict)
    isolation_level: IsolationLevel = IsolationLevel.LOGICAL
    shared_components: list[str] = Field(default_factory=list)


class NoisyNeighborResult(BaseModel):
    """Result of a noisy-neighbor simulation."""

    aggressor_tenant_id: str
    victim_tenant_ids: list[str] = Field(default_factory=list)
    noise_type: NoiseType
    impact_severity: str = "low"
    latency_increase_percent: float = 0.0
    error_rate_increase_percent: float = 0.0
    isolation_breach: bool = False
    recommendations: list[str] = Field(default_factory=list)


class SharedResourceRisk(BaseModel):
    """Risk from a shared resource across tenants."""

    resource_id: str
    resource_type: str = ""
    tenant_ids: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    contention_score: float = 0.0
    recommendation: str = ""


class DataIsolationResult(BaseModel):
    """Assessment of data-level isolation between tenants."""

    verified: bool = True
    risk_count: int = 0
    risks: list[DataLeakRisk] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class DataLeakRisk(BaseModel):
    """A specific data-leak risk."""

    source_tenant_id: str
    target_tenant_id: str
    shared_component_id: str
    risk_level: str = "low"
    description: str = ""


# Fix forward ref – DataIsolationResult references DataLeakRisk
DataIsolationResult.model_rebuild()


class SharedBottleneck(BaseModel):
    """A shared resource that is a potential bottleneck."""

    component_id: str
    component_type: str = ""
    tenant_count: int = 0
    utilization_percent: float = 0.0
    severity: str = "low"
    recommendation: str = ""


class IsolationUpgrade(BaseModel):
    """A recommendation to improve tenant isolation."""

    tenant_id: str
    current_level: IsolationLevel
    recommended_level: IsolationLevel
    reason: str = ""
    priority: str = "medium"
    estimated_effort: str = "medium"


class TenantSpikeResult(BaseModel):
    """Impact of one tenant experiencing a traffic spike."""

    tenant_id: str
    multiplier: float = 1.0
    affected_tenant_ids: list[str] = Field(default_factory=list)
    resources_exhausted: list[str] = Field(default_factory=list)
    latency_increase_percent: float = 0.0
    error_rate_increase_percent: float = 0.0
    isolation_held: bool = True
    recommendations: list[str] = Field(default_factory=list)


class IsolationAssessment(BaseModel):
    """Top-level isolation assessment report."""

    tenant_count: int = 0
    isolation_score: float = 0.0
    shared_resource_risks: list[SharedResourceRisk] = Field(default_factory=list)
    noisy_neighbor_risks: list[str] = Field(default_factory=list)
    data_isolation_verified: bool = True
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class MultiTenantIsolationEngine:
    """Stateless engine for multi-tenant isolation verification."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess_isolation(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
    ) -> IsolationAssessment:
        """Full isolation assessment across all tenants."""
        if not tenants:
            return IsolationAssessment(
                tenant_count=0,
                isolation_score=100.0,
                data_isolation_verified=True,
            )

        shared_risks = self._find_shared_resource_risks(graph, tenants)
        data_result = self.verify_data_isolation(graph, tenants)
        nn_risks = self._assess_noisy_neighbor_risks(graph, tenants)
        score = self._calculate_isolation_score(graph, tenants, shared_risks)
        recommendations = self._build_assessment_recommendations(
            graph, tenants, shared_risks, data_result, nn_risks,
        )

        return IsolationAssessment(
            tenant_count=len(tenants),
            isolation_score=round(score, 1),
            shared_resource_risks=shared_risks,
            noisy_neighbor_risks=nn_risks,
            data_isolation_verified=data_result.verified,
            recommendations=recommendations,
        )

    def simulate_noisy_neighbor(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
        aggressor_id: str,
        noise_type: NoiseType,
    ) -> NoisyNeighborResult:
        """Simulate a noisy-neighbor scenario."""
        aggressor = self._find_tenant(tenants, aggressor_id)
        if aggressor is None:
            return NoisyNeighborResult(
                aggressor_tenant_id=aggressor_id,
                noise_type=noise_type,
                impact_severity="none",
            )

        # Find victims: tenants that share at least one component with aggressor.
        victims: list[str] = []
        for t in tenants:
            if t.id == aggressor_id:
                continue
            if set(t.shared_components) & set(aggressor.shared_components):
                victims.append(t.id)

        if not victims:
            return NoisyNeighborResult(
                aggressor_tenant_id=aggressor_id,
                noise_type=noise_type,
                impact_severity="none",
                recommendations=["No shared components; isolation is effective."],
            )

        # Calculate impact based on noise type and isolation level of victims.
        base_latency = _NOISE_BASE_IMPACT[noise_type]
        base_error = _NOISE_ERROR_RATE[noise_type]

        worst_attenuation = 0.0
        for vid in victims:
            vt = self._find_tenant(tenants, vid)
            if vt is not None:
                att = _ISOLATION_ATTENUATION.get(vt.isolation_level, 1.0)
                worst_attenuation = max(worst_attenuation, att)

        latency_inc = round(base_latency * worst_attenuation, 2)
        error_inc = round(base_error * worst_attenuation, 2)
        severity = self._impact_severity(latency_inc, error_inc)
        breach = latency_inc > 20.0 or error_inc > 5.0

        recommendations: list[str] = []
        if breach:
            recommendations.append(
                "Isolation breach detected. Upgrade isolation level for affected tenants."
            )
        if worst_attenuation > 0.5:
            recommendations.append(
                "Consider moving to container or VM isolation to reduce noisy-neighbor impact."
            )
        if noise_type in (NoiseType.CONNECTION_POOL_EXHAUSTION, NoiseType.QUERY_STORM):
            recommendations.append(
                "Implement per-tenant connection pool limits and query rate limiting."
            )

        return NoisyNeighborResult(
            aggressor_tenant_id=aggressor_id,
            victim_tenant_ids=sorted(victims),
            noise_type=noise_type,
            impact_severity=severity,
            latency_increase_percent=latency_inc,
            error_rate_increase_percent=error_inc,
            isolation_breach=breach,
            recommendations=recommendations,
        )

    def verify_data_isolation(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
    ) -> DataIsolationResult:
        """Check for potential data-leak paths between tenants."""
        risks: list[DataLeakRisk] = []
        recommendations: list[str] = []

        if not tenants:
            return DataIsolationResult(verified=True)

        # Build map: component_id -> set of tenant ids using it
        comp_tenants: dict[str, set[str]] = {}
        for t in tenants:
            for cid in t.shared_components:
                comp_tenants.setdefault(cid, set()).add(t.id)

        for cid, tids in comp_tenants.items():
            if len(tids) < 2:
                continue
            comp = graph.get_component(cid)
            comp_type = comp.type.value if comp else "unknown"

            # Data-bearing components are higher risk.
            is_data_bearing = comp_type in (
                ComponentType.DATABASE.value,
                ComponentType.CACHE.value,
                ComponentType.STORAGE.value,
            )

            tid_list = sorted(tids)
            for i, t1 in enumerate(tid_list):
                for t2 in tid_list[i + 1:]:
                    tenant1 = self._find_tenant(tenants, t1)
                    tenant2 = self._find_tenant(tenants, t2)
                    iso1 = tenant1.isolation_level if tenant1 else IsolationLevel.NONE
                    iso2 = tenant2.isolation_level if tenant2 else IsolationLevel.NONE
                    weaker = iso1 if _ISOLATION_RANK[iso1] <= _ISOLATION_RANK[iso2] else iso2

                    if is_data_bearing:
                        if _ISOLATION_RANK[weaker] < _ISOLATION_RANK[IsolationLevel.NAMESPACE]:
                            risk_level = "critical"
                        elif _ISOLATION_RANK[weaker] < _ISOLATION_RANK[IsolationLevel.CONTAINER]:
                            risk_level = "high"
                        else:
                            risk_level = "medium"
                    else:
                        if _ISOLATION_RANK[weaker] < _ISOLATION_RANK[IsolationLevel.LOGICAL]:
                            risk_level = "high"
                        elif _ISOLATION_RANK[weaker] < _ISOLATION_RANK[IsolationLevel.NAMESPACE]:
                            risk_level = "medium"
                        else:
                            risk_level = "low"

                    desc = (
                        f"Tenants '{t1}' and '{t2}' share {comp_type} "
                        f"component '{cid}' with {weaker.value} isolation"
                    )
                    risks.append(DataLeakRisk(
                        source_tenant_id=t1,
                        target_tenant_id=t2,
                        shared_component_id=cid,
                        risk_level=risk_level,
                        description=desc,
                    ))

        verified = all(r.risk_level in ("low", "medium") for r in risks) if risks else True
        if not verified:
            recommendations.append(
                "Data isolation verification failed. "
                "Upgrade isolation for tenants sharing data-bearing components."
            )
        if any(r.risk_level == "critical" for r in risks):
            recommendations.append(
                "Critical data-leak risk detected. "
                "Separate data stores per tenant immediately."
            )

        return DataIsolationResult(
            verified=verified,
            risk_count=len(risks),
            risks=risks,
            recommendations=recommendations,
        )

    def find_shared_bottlenecks(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
    ) -> list[SharedBottleneck]:
        """Find shared infrastructure components that may become bottlenecks."""
        comp_tenants: dict[str, set[str]] = {}
        for t in tenants:
            for cid in t.shared_components:
                comp_tenants.setdefault(cid, set()).add(t.id)

        bottlenecks: list[SharedBottleneck] = []
        for cid, tids in comp_tenants.items():
            if len(tids) < 2:
                continue
            comp = graph.get_component(cid)
            util = comp.utilization() if comp else 0.0
            comp_type = comp.type.value if comp else "unknown"
            tenant_count = len(tids)

            # Severity based on utilization and tenant count.
            if util > 80 or tenant_count >= 5:
                severity = "critical"
            elif util > 60 or tenant_count >= 3:
                severity = "high"
            else:
                severity = "medium"

            recommendation = (
                f"Component '{cid}' is shared by {tenant_count} tenants "
                f"with {util:.0f}% utilization. "
            )
            if util > 60:
                recommendation += "Consider scaling or partitioning."
            elif tenant_count >= 3:
                recommendation += "Consider per-tenant instances."
            else:
                recommendation += "Monitor for contention."

            bottlenecks.append(SharedBottleneck(
                component_id=cid,
                component_type=comp_type,
                tenant_count=tenant_count,
                utilization_percent=round(util, 1),
                severity=severity,
                recommendation=recommendation,
            ))

        bottlenecks.sort(key=lambda b: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(b.severity, 4),
            -b.tenant_count,
        ))
        return bottlenecks

    def recommend_isolation_upgrades(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
    ) -> list[IsolationUpgrade]:
        """Recommend isolation-level upgrades based on tier and risk."""
        upgrades: list[IsolationUpgrade] = []
        for t in tenants:
            min_level = _TIER_MIN_ISOLATION.get(t.tier, IsolationLevel.LOGICAL)
            if _ISOLATION_RANK[t.isolation_level] < _ISOLATION_RANK[min_level]:
                priority = "critical" if t.tier in (TenantTier.ENTERPRISE, TenantTier.DEDICATED) else "high"
                effort = self._estimate_upgrade_effort(t.isolation_level, min_level)
                upgrades.append(IsolationUpgrade(
                    tenant_id=t.id,
                    current_level=t.isolation_level,
                    recommended_level=min_level,
                    reason=(
                        f"Tenant tier '{t.tier.value}' requires at least "
                        f"'{min_level.value}' isolation, but currently has "
                        f"'{t.isolation_level.value}'"
                    ),
                    priority=priority,
                    estimated_effort=effort,
                ))

            # Check if shared data-bearing components warrant upgrade.
            data_bearing_shared = [
                cid for cid in t.shared_components
                if self._is_data_bearing(graph, cid)
            ]
            if data_bearing_shared and _ISOLATION_RANK[t.isolation_level] < _ISOLATION_RANK[IsolationLevel.NAMESPACE]:
                target = IsolationLevel.NAMESPACE
                if _ISOLATION_RANK.get(min_level, 0) > _ISOLATION_RANK[target]:
                    target = min_level
                # Avoid duplicate if already covered above.
                if not any(u.tenant_id == t.id and _ISOLATION_RANK[u.recommended_level] >= _ISOLATION_RANK[target] for u in upgrades):
                    upgrades.append(IsolationUpgrade(
                        tenant_id=t.id,
                        current_level=t.isolation_level,
                        recommended_level=target,
                        reason=(
                            f"Tenant shares data-bearing components {data_bearing_shared} "
                            f"with insufficient isolation ('{t.isolation_level.value}')"
                        ),
                        priority="high",
                        estimated_effort=self._estimate_upgrade_effort(t.isolation_level, target),
                    ))

        upgrades.sort(key=lambda u: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(u.priority, 4),
        ))
        return upgrades

    def simulate_tenant_spike(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
        tenant_id: str,
        multiplier: float,
    ) -> TenantSpikeResult:
        """Simulate the impact of a traffic spike from one tenant."""
        tenant = self._find_tenant(tenants, tenant_id)
        if tenant is None:
            return TenantSpikeResult(
                tenant_id=tenant_id,
                multiplier=multiplier,
                isolation_held=True,
            )

        affected: list[str] = []
        exhausted: list[str] = []
        recommendations: list[str] = []

        # Check each shared component for capacity overflow.
        for cid in tenant.shared_components:
            comp = graph.get_component(cid)
            if comp is None:
                continue

            current_util = comp.utilization()
            # Estimate spiked utilization.
            tenant_count = max(1, sum(1 for t in tenants if cid in t.shared_components))
            per_tenant_share = current_util / tenant_count
            spiked_util = current_util + per_tenant_share * (multiplier - 1)

            if spiked_util > 100:
                exhausted.append(cid)
            if spiked_util > 80:
                # Find other tenants sharing this component.
                for t in tenants:
                    if t.id == tenant_id:
                        continue
                    if cid in t.shared_components and t.id not in affected:
                        affected.append(t.id)

        affected.sort()

        # Calculate impact.
        attenuation = _ISOLATION_ATTENUATION.get(tenant.isolation_level, 1.0)
        latency_inc = round(max(0.0, min(200.0, (multiplier - 1) * 15.0 * attenuation)), 2)
        error_inc = round(max(0.0, min(50.0, (multiplier - 1) * 3.0 * attenuation)), 2)
        if exhausted:
            latency_inc = round(min(200.0, latency_inc * 1.5), 2)
            error_inc = round(min(50.0, error_inc * 2.0), 2)

        isolation_held = len(affected) == 0 and len(exhausted) == 0

        if exhausted:
            recommendations.append(
                f"Resources exhausted on {exhausted}. "
                "Implement per-tenant resource quotas."
            )
        if affected:
            recommendations.append(
                f"Spike affected tenants: {affected}. "
                "Strengthen isolation or add capacity."
            )
        if multiplier > 5:
            recommendations.append(
                "Spike multiplier exceeds 5x. "
                "Implement auto-scaling and rate limiting per tenant."
            )

        return TenantSpikeResult(
            tenant_id=tenant_id,
            multiplier=multiplier,
            affected_tenant_ids=affected,
            resources_exhausted=exhausted,
            latency_increase_percent=latency_inc,
            error_rate_increase_percent=error_inc,
            isolation_held=isolation_held,
            recommendations=recommendations,
        )

    def calculate_fair_share(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
    ) -> dict[str, dict[str, float]]:
        """Calculate fair resource allocation per tenant.

        Returns ``{tenant_id: {resource: fair_share_value}}``.
        """
        if not tenants:
            return {}

        # Gather all resource keys from quotas.
        all_resources: set[str] = set()
        for t in tenants:
            all_resources.update(t.resource_quota.keys())

        # Add component-derived resources.
        all_comp_ids: set[str] = set()
        for t in tenants:
            all_comp_ids.update(t.shared_components)

        for cid in all_comp_ids:
            all_resources.add(f"{cid}_capacity")

        result: dict[str, dict[str, float]] = {}
        for t in tenants:
            shares: dict[str, float] = {}
            for res in sorted(all_resources):
                if res in t.resource_quota:
                    # Use quota directly.
                    shares[res] = t.resource_quota[res]
                elif res.endswith("_capacity"):
                    cid = res[: -len("_capacity")]
                    if cid in t.shared_components:
                        comp = graph.get_component(cid)
                        if comp is not None:
                            # Split capacity equally among tenants sharing it.
                            sharing = sum(1 for ot in tenants if cid in ot.shared_components)
                            fair = comp.capacity.max_rps / max(sharing, 1)
                            # Weight by tier.
                            weight = self._tier_weight(t.tier)
                            shares[res] = round(fair * weight, 2)
                        else:
                            shares[res] = 0.0
                    else:
                        shares[res] = 0.0
                else:
                    shares[res] = 0.0
            result[t.id] = shares

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_tenant(tenants: list[Tenant], tid: str) -> Tenant | None:
        for t in tenants:
            if t.id == tid:
                return t
        return None

    @staticmethod
    def _impact_severity(latency: float, error_rate: float) -> str:
        if latency > 40 or error_rate > 10:
            return "critical"
        if latency > 20 or error_rate > 5:
            return "high"
        if latency > 10 or error_rate > 2:
            return "medium"
        if latency > 0 or error_rate > 0:
            return "low"
        return "none"

    @staticmethod
    def _tier_weight(tier: TenantTier) -> float:
        return {
            TenantTier.FREE: 0.5,
            TenantTier.BASIC: 0.75,
            TenantTier.PROFESSIONAL: 1.0,
            TenantTier.ENTERPRISE: 1.5,
            TenantTier.DEDICATED: 2.0,
        }.get(tier, 1.0)

    @staticmethod
    def _estimate_upgrade_effort(
        current: IsolationLevel,
        target: IsolationLevel,
    ) -> str:
        gap = _ISOLATION_RANK[target] - _ISOLATION_RANK[current]
        if gap <= 1:
            return "low"
        if gap <= 3:
            return "medium"
        return "high"

    @staticmethod
    def _is_data_bearing(graph: InfraGraph, cid: str) -> bool:
        comp = graph.get_component(cid)
        if comp is None:
            return False
        return comp.type in (
            ComponentType.DATABASE,
            ComponentType.CACHE,
            ComponentType.STORAGE,
        )

    def _find_shared_resource_risks(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
    ) -> list[SharedResourceRisk]:
        comp_tenants: dict[str, set[str]] = {}
        for t in tenants:
            for cid in t.shared_components:
                comp_tenants.setdefault(cid, set()).add(t.id)

        risks: list[SharedResourceRisk] = []
        for cid, tids in comp_tenants.items():
            if len(tids) < 2:
                continue
            comp = graph.get_component(cid)
            comp_type = comp.type.value if comp else "unknown"
            util = comp.utilization() if comp else 0.0

            contention = round(len(tids) * (1 + util / 100), 2)
            if contention > 5:
                risk_level = "critical"
            elif contention > 3:
                risk_level = "high"
            else:
                risk_level = "medium"

            recommendation = (
                f"Shared {comp_type} '{cid}' used by {len(tids)} tenants. "
            )
            if risk_level in ("critical", "high"):
                recommendation += "Partition or dedicate per tenant."
            else:
                recommendation += "Monitor contention metrics."

            risks.append(SharedResourceRisk(
                resource_id=cid,
                resource_type=comp_type,
                tenant_ids=sorted(tids),
                risk_level=risk_level,
                contention_score=contention,
                recommendation=recommendation,
            ))

        risks.sort(key=lambda r: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(r.risk_level, 4),
        ))
        return risks

    def _assess_noisy_neighbor_risks(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
    ) -> list[str]:
        risks: list[str] = []
        for t in tenants:
            att = _ISOLATION_ATTENUATION.get(t.isolation_level, 1.0)
            if att >= 0.8:
                risks.append(
                    f"Tenant '{t.id}' has weak isolation ({t.isolation_level.value}); "
                    f"vulnerable to noisy-neighbor effects."
                )
        # Also flag shared high-contention components.
        comp_tenants: dict[str, set[str]] = {}
        for t in tenants:
            for cid in t.shared_components:
                comp_tenants.setdefault(cid, set()).add(t.id)

        for cid, tids in comp_tenants.items():
            if len(tids) >= 3:
                risks.append(
                    f"Component '{cid}' shared by {len(tids)} tenants; "
                    f"high noisy-neighbor risk."
                )
        return risks

    def _calculate_isolation_score(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
        shared_risks: list[SharedResourceRisk],
    ) -> float:
        if not tenants:
            return 100.0

        score = 100.0

        # Penalize based on isolation levels vs tier expectations.
        for t in tenants:
            min_level = _TIER_MIN_ISOLATION.get(t.tier, IsolationLevel.LOGICAL)
            current_rank = _ISOLATION_RANK[t.isolation_level]
            required_rank = _ISOLATION_RANK[min_level]
            if current_rank < required_rank:
                gap = required_rank - current_rank
                score -= gap * 5.0

        # Penalize shared resource risks.
        for risk in shared_risks:
            if risk.risk_level == "critical":
                score -= 10.0
            elif risk.risk_level == "high":
                score -= 5.0
            elif risk.risk_level == "medium":
                score -= 2.0

        # Penalize weak isolation levels.
        for t in tenants:
            att = _ISOLATION_ATTENUATION.get(t.isolation_level, 1.0)
            if att >= 0.8:
                score -= 3.0

        return max(0.0, min(100.0, round(score, 1)))

    def _build_assessment_recommendations(
        self,
        graph: InfraGraph,
        tenants: list[Tenant],
        shared_risks: list[SharedResourceRisk],
        data_result: DataIsolationResult,
        nn_risks: list[str],
    ) -> list[str]:
        recs: list[str] = []

        # Tier-level isolation recommendations.
        for t in tenants:
            min_level = _TIER_MIN_ISOLATION.get(t.tier, IsolationLevel.LOGICAL)
            if _ISOLATION_RANK[t.isolation_level] < _ISOLATION_RANK[min_level]:
                recs.append(
                    f"Upgrade tenant '{t.id}' from '{t.isolation_level.value}' "
                    f"to at least '{min_level.value}' isolation."
                )

        # Shared resource recommendations.
        for risk in shared_risks:
            if risk.risk_level in ("critical", "high"):
                recs.append(risk.recommendation)

        # Data isolation recommendations.
        recs.extend(data_result.recommendations)

        # Deduplicate.
        seen: set[str] = set()
        unique: list[str] = []
        for r in recs:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        return unique
