# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Topology Intelligence Engine — discovers implicit/hidden dependencies."""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DependencySource(str, Enum):
    DECLARED = "declared"
    INFERRED_SHARED_INFRA = "inferred_shared_infra"
    INFERRED_PATTERN = "inferred_pattern"
    INFERRED_PROXIMITY = "inferred_proximity"
    INFERRED_COMMON_DEPENDENCY = "inferred_common_dependency"


class InferenceConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ImplicitDependency(BaseModel):
    source_component: str
    target_component: str
    dependency_type: str  # shared_dns, shared_auth, shared_storage, ntp_sync, common_lb, shared_network
    source: DependencySource
    confidence: InferenceConfidence
    reasoning: str


class TopologyAnomaly(BaseModel):
    anomaly_type: str  # missing_lb, single_path, circular_dependency, orphan_component, asymmetric_redundancy
    affected_components: list[str] = Field(default_factory=list)
    severity: float = 0.5  # 0-1
    description: str = ""
    recommendation: str = ""


class HiddenRiskScenario(BaseModel):
    scenario_id: str = ""
    name: str = ""
    description: str = ""
    target_dependency: ImplicitDependency | None = None
    impact_components: list[str] = Field(default_factory=list)
    estimated_blast_radius: float = 0.0  # 0-1
    recommended_test: str = ""


class TopologyIntelligenceReport(BaseModel):
    total_components: int = 0
    declared_dependencies: int = 0
    implicit_dependencies_found: int = 0
    anomalies: list[TopologyAnomaly] = Field(default_factory=list)
    hidden_risks: list[HiddenRiskScenario] = Field(default_factory=list)
    topology_health_score: float = 100.0  # 0-100
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class TopologyIntelligenceEngine:
    """Analyse an ``InfraGraph`` to discover hidden dependencies and risks."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # -- helpers -------------------------------------------------------------

    def _components_by_type(self, ctype: ComponentType) -> list[Component]:
        return [c for c in self._graph.components.values() if c.type == ctype]

    def _has_declared_dep(self, source_id: str, target_id: str) -> bool:
        return self._graph.get_dependency_edge(source_id, target_id) is not None

    def _all_component_ids(self) -> list[str]:
        return list(self._graph.components.keys())

    # -- public API ----------------------------------------------------------

    def discover_implicit_dependencies(self) -> list[ImplicitDependency]:
        """Discover hidden dependencies using heuristic rules."""
        results: list[ImplicitDependency] = []
        components = self._graph.components

        dns_nodes = self._components_by_type(ComponentType.DNS)
        lb_nodes = self._components_by_type(ComponentType.LOAD_BALANCER)
        cache_nodes = self._components_by_type(ComponentType.CACHE)
        db_nodes = self._components_by_type(ComponentType.DATABASE)
        self._components_by_type(ComponentType.STORAGE)

        # Rule 1: All components implicitly depend on DNS if one exists
        #   (External APIs are handled separately in Rule 4.)
        for dns in dns_nodes:
            for comp in components.values():
                if comp.id == dns.id:
                    continue
                if comp.type == ComponentType.EXTERNAL_API:
                    continue  # handled by Rule 4
                if not self._has_declared_dep(comp.id, dns.id):
                    results.append(ImplicitDependency(
                        source_component=comp.id,
                        target_component=dns.id,
                        dependency_type="shared_dns",
                        source=DependencySource.INFERRED_SHARED_INFRA,
                        confidence=InferenceConfidence.HIGH,
                        reasoning=f"Component '{comp.id}' implicitly depends on DNS '{dns.id}'",
                    ))

        # Rule 2: All web servers implicitly depend on load balancers
        for lb in lb_nodes:
            for ws in self._components_by_type(ComponentType.WEB_SERVER):
                if not self._has_declared_dep(ws.id, lb.id):
                    results.append(ImplicitDependency(
                        source_component=ws.id,
                        target_component=lb.id,
                        dependency_type="common_lb",
                        source=DependencySource.INFERRED_PATTERN,
                        confidence=InferenceConfidence.HIGH,
                        reasoning=f"Web server '{ws.id}' typically sits behind load balancer '{lb.id}'",
                    ))

        # Rule 3: Databases and caches in same region share network infra
        region_groups: dict[str, list[Component]] = {}
        for comp in list(db_nodes) + list(cache_nodes):
            region_key = comp.region.region or "__default__"
            region_groups.setdefault(region_key, []).append(comp)
        for _region, group in region_groups.items():
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if not self._has_declared_dep(a.id, b.id) and not self._has_declared_dep(b.id, a.id):
                        results.append(ImplicitDependency(
                            source_component=a.id,
                            target_component=b.id,
                            dependency_type="shared_network",
                            source=DependencySource.INFERRED_PROXIMITY,
                            confidence=InferenceConfidence.MEDIUM,
                            reasoning=f"'{a.id}' and '{b.id}' share network infrastructure in the same region",
                        ))

        # Rule 4: External APIs have implicit DNS and TLS dependencies
        for ext in self._components_by_type(ComponentType.EXTERNAL_API):
            for dns in dns_nodes:
                if not self._has_declared_dep(ext.id, dns.id):
                    results.append(ImplicitDependency(
                        source_component=ext.id,
                        target_component=dns.id,
                        dependency_type="shared_dns",
                        source=DependencySource.INFERRED_SHARED_INFRA,
                        confidence=InferenceConfidence.HIGH,
                        reasoning=f"External API '{ext.id}' requires DNS resolution",
                    ))

        # Rule 5: Components without declared deps but with same tags share infra
        tag_groups: dict[str, list[Component]] = {}
        for comp in components.values():
            declared_deps = self._graph.get_dependencies(comp.id)
            declared_dependents = self._graph.get_dependents(comp.id)
            if not declared_deps and not declared_dependents:
                for tag in comp.tags:
                    tag_groups.setdefault(tag, []).append(comp)
        for _tag, group in tag_groups.items():
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    already = any(
                        (d.source_component == a.id and d.target_component == b.id)
                        or (d.source_component == b.id and d.target_component == a.id)
                        for d in results
                    )
                    if not already:
                        results.append(ImplicitDependency(
                            source_component=a.id,
                            target_component=b.id,
                            dependency_type="shared_storage",
                            source=DependencySource.INFERRED_COMMON_DEPENDENCY,
                            confidence=InferenceConfidence.LOW,
                            reasoning=f"'{a.id}' and '{b.id}' share common tags and likely share infrastructure",
                        ))

        # Rule 6: App servers typically depend on cache if cache exists
        for cache in cache_nodes:
            for app in self._components_by_type(ComponentType.APP_SERVER):
                if not self._has_declared_dep(app.id, cache.id):
                    results.append(ImplicitDependency(
                        source_component=app.id,
                        target_component=cache.id,
                        dependency_type="shared_storage",
                        source=DependencySource.INFERRED_PATTERN,
                        confidence=InferenceConfidence.MEDIUM,
                        reasoning=f"App server '{app.id}' typically uses cache '{cache.id}'",
                    ))

        return results

    def detect_anomalies(self) -> list[TopologyAnomaly]:
        """Detect topology problems and anomalies."""
        anomalies: list[TopologyAnomaly] = []
        components = self._graph.components

        if not components:
            return anomalies

        web_servers = self._components_by_type(ComponentType.WEB_SERVER)
        lb_nodes = self._components_by_type(ComponentType.LOAD_BALANCER)

        # 1. missing_lb — web servers exist but no load balancer
        if web_servers and not lb_nodes:
            anomalies.append(TopologyAnomaly(
                anomaly_type="missing_lb",
                affected_components=[ws.id for ws in web_servers],
                severity=0.8,
                description="Web servers found without a load balancer",
                recommendation="Add a load balancer in front of web servers for redundancy",
            ))

        # 2. single_path — component has exactly one dependency and that target has replicas==1
        for comp in components.values():
            deps = self._graph.get_dependencies(comp.id)
            if len(deps) == 1 and deps[0].replicas == 1:
                anomalies.append(TopologyAnomaly(
                    anomaly_type="single_path",
                    affected_components=[comp.id, deps[0].id],
                    severity=0.7,
                    description=f"'{comp.id}' has a single dependency on '{deps[0].id}' with no redundancy",
                    recommendation=f"Add replicas or failover to '{deps[0].id}'",
                ))

        # 3. circular_dependency
        import networkx as nx
        cycles = list(nx.simple_cycles(self._graph._graph))
        for cycle in cycles:
            anomalies.append(TopologyAnomaly(
                anomaly_type="circular_dependency",
                affected_components=list(cycle),
                severity=0.9,
                description=f"Circular dependency detected: {' -> '.join(cycle)}",
                recommendation="Break the circular dependency to avoid deadlocks",
            ))

        # 4. orphan_component — no deps and no dependents
        for comp in components.values():
            deps = self._graph.get_dependencies(comp.id)
            dependents = self._graph.get_dependents(comp.id)
            if not deps and not dependents and len(components) > 1:
                anomalies.append(TopologyAnomaly(
                    anomaly_type="orphan_component",
                    affected_components=[comp.id],
                    severity=0.3,
                    description=f"Component '{comp.id}' has no declared dependencies or dependents",
                    recommendation=f"Verify if '{comp.id}' is correctly integrated into the topology",
                ))

        # 5. asymmetric_redundancy — components with dependents have fewer replicas than those they depend on
        for comp in components.values():
            deps = self._graph.get_dependencies(comp.id)
            for dep in deps:
                if comp.replicas > 1 and dep.replicas == 1:
                    anomalies.append(TopologyAnomaly(
                        anomaly_type="asymmetric_redundancy",
                        affected_components=[comp.id, dep.id],
                        severity=0.6,
                        description=f"'{comp.id}' has {comp.replicas} replicas but depends on '{dep.id}' with only 1 replica",
                        recommendation=f"Scale '{dep.id}' to match redundancy of '{comp.id}'",
                    ))

        return anomalies

    def generate_hidden_risk_scenarios(
        self, implicit_deps: list[ImplicitDependency]
    ) -> list[HiddenRiskScenario]:
        """Create test scenarios for hidden dependencies."""
        scenarios: list[HiddenRiskScenario] = []
        total = len(self._graph.components)

        for dep in implicit_deps:
            affected = self._graph.get_all_affected(dep.target_component)
            # Include the source component itself
            impact_ids = list(affected | {dep.source_component})
            blast = len(impact_ids) / total if total > 0 else 0.0
            blast = min(blast, 1.0)

            scenario = HiddenRiskScenario(
                scenario_id=f"hidden-{uuid.uuid4().hex[:8]}",
                name=f"Failure of hidden {dep.dependency_type} dependency",
                description=(
                    f"Simulates failure of the implicit {dep.dependency_type} link "
                    f"between '{dep.source_component}' and '{dep.target_component}'"
                ),
                target_dependency=dep,
                impact_components=impact_ids,
                estimated_blast_radius=round(blast, 2),
                recommended_test=(
                    f"Inject fault on '{dep.target_component}' and observe "
                    f"impact on {len(impact_ids)} component(s)"
                ),
            )
            scenarios.append(scenario)

        return scenarios

    def calculate_topology_health(self) -> float:
        """Return a topology health score from 0 to 100."""
        components = self._graph.components
        if not components:
            return 0.0

        score = 100.0
        total = len(components)

        # Penalty for orphan components
        for comp in components.values():
            deps = self._graph.get_dependencies(comp.id)
            dependents = self._graph.get_dependents(comp.id)
            if not deps and not dependents and total > 1:
                score -= 5.0

        # Penalty for single-replica components that have dependents
        for comp in components.values():
            dependents = self._graph.get_dependents(comp.id)
            if comp.replicas == 1 and dependents:
                score -= 8.0

        # Penalty for missing load balancer when web servers exist
        if self._components_by_type(ComponentType.WEB_SERVER) and not self._components_by_type(ComponentType.LOAD_BALANCER):
            score -= 10.0

        # Penalty for circular dependencies
        import networkx as nx
        cycles = list(nx.simple_cycles(self._graph._graph))
        score -= len(cycles) * 10.0

        # Bonus for failover-enabled components
        for comp in components.values():
            if comp.failover.enabled:
                score += 3.0

        return max(0.0, min(100.0, score))

    def generate_report(self) -> TopologyIntelligenceReport:
        """Generate the full topology intelligence report."""
        implicit_deps = self.discover_implicit_dependencies()
        anomalies = self.detect_anomalies()
        scenarios = self.generate_hidden_risk_scenarios(implicit_deps)
        health = self.calculate_topology_health()

        recommendations: list[str] = []
        for anomaly in anomalies:
            if anomaly.recommendation:
                recommendations.append(anomaly.recommendation)

        if implicit_deps:
            recommendations.append(
                f"Found {len(implicit_deps)} implicit dependencies — "
                "consider making them explicit in configuration"
            )

        high_blast = [s for s in scenarios if s.estimated_blast_radius > 0.5]
        if high_blast:
            recommendations.append(
                f"{len(high_blast)} hidden risk scenario(s) with blast radius > 50% — "
                "prioritise testing these"
            )

        return TopologyIntelligenceReport(
            total_components=len(self._graph.components),
            declared_dependencies=len(self._graph.all_dependency_edges()),
            implicit_dependencies_found=len(implicit_deps),
            anomalies=anomalies,
            hidden_risks=scenarios,
            topology_health_score=round(health, 1),
            recommendations=recommendations,
        )
