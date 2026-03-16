"""Dependency Drift Detector for FaultRay.

Detects when infrastructure dependencies have drifted from their intended
configuration over time — version skew, capacity imbalances, security policy
inconsistencies, topology changes, and more.

Usage:
    from faultray.simulator.dependency_drift import DependencyDriftEngine
    engine = DependencyDriftEngine()
    report = engine.detect_drifts(graph)
    plan = engine.generate_remediation_plan(report.drifts)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph


class DriftType(str, Enum):
    """Types of dependency drift that can be detected."""

    VERSION_SKEW = "version_skew"
    CONFIG_DRIFT = "config_drift"
    SCHEMA_MISMATCH = "schema_mismatch"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    CAPACITY_IMBALANCE = "capacity_imbalance"
    SECURITY_POLICY_DRIFT = "security_policy_drift"
    TLS_EXPIRY = "tls_expiry"
    API_VERSION_MISMATCH = "api_version_mismatch"
    TOPOLOGY_DRIFT = "topology_drift"
    COMPLIANCE_DRIFT = "compliance_drift"


class DriftSeverity(str, Enum):
    """Severity levels for drift detections."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class DriftDetection(BaseModel):
    """A single detected drift between expected and actual state."""

    component_id: str
    drift_type: DriftType
    severity: DriftSeverity
    expected_value: str
    actual_value: str
    detected_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    remediation: str
    auto_fixable: bool = False
    blast_radius: list[str] = Field(default_factory=list)


class DriftReport(BaseModel):
    """Full report of all detected drifts."""

    total_drifts: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    drifts: list[DriftDetection] = Field(default_factory=list)
    drift_score: float = 100.0
    recommendations: list[str] = Field(default_factory=list)
    auto_fixable_count: int = 0


class RemediationStep(BaseModel):
    """A single step in a remediation plan."""

    priority: int
    component_id: str
    drift_type: DriftType
    severity: DriftSeverity
    action: str
    auto_fixable: bool = False
    estimated_impact: str = ""


class RemediationPlan(BaseModel):
    """Prioritized plan for fixing detected drifts."""

    steps: list[RemediationStep] = Field(default_factory=list)
    total_steps: int = 0
    auto_fixable_steps: int = 0
    manual_steps: int = 0
    estimated_risk_reduction: float = 0.0


# ---------------------------------------------------------------------------
# Version extraction helpers
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _extract_version(name: str) -> str | None:
    """Extract a version string from a component name or tag."""
    m = _VERSION_RE.search(name)
    if m:
        parts = [m.group(1)]
        if m.group(2) is not None:
            parts.append(m.group(2))
        if m.group(3) is not None:
            parts.append(m.group(3))
        return ".".join(parts)
    return None


def _version_major(ver: str) -> int | None:
    """Return the major version number, or None."""
    m = _VERSION_RE.match(ver)
    if m:
        return int(m.group(1))
    return None


def _version_tuple(ver: str) -> tuple[int, ...]:
    """Convert a version string to a comparable tuple."""
    m = _VERSION_RE.match(ver)
    if not m:
        return (0,)
    parts = [int(m.group(1))]
    if m.group(2) is not None:
        parts.append(int(m.group(2)))
    if m.group(3) is not None:
        parts.append(int(m.group(3)))
    return tuple(parts)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DependencyDriftEngine:
    """Stateless engine that detects dependency drift across an infrastructure graph.

    Each public method takes an InfraGraph (and optionally a baseline graph)
    and returns drift detections without mutating any state.
    """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def detect_drifts(self, graph: InfraGraph) -> DriftReport:
        """Run a full drift scan across the graph.

        Aggregates results from all specialised detectors and produces a
        consolidated DriftReport with a drift score (0-100, 100=no drift).
        """
        all_drifts: list[DriftDetection] = []
        all_drifts.extend(self.detect_version_skew(graph))
        all_drifts.extend(self.detect_capacity_imbalance(graph))
        all_drifts.extend(self.detect_security_drift(graph))
        all_drifts.extend(self._detect_config_drift(graph))
        all_drifts.extend(self._detect_protocol_mismatch(graph))
        all_drifts.extend(self._detect_tls_expiry(graph))
        all_drifts.extend(self._detect_compliance_drift(graph))

        return self._build_report(all_drifts, graph)

    def detect_version_skew(self, graph: InfraGraph) -> list[DriftDetection]:
        """Detect version mismatches among connected components of the same type."""
        drifts: list[DriftDetection] = []
        components = list(graph.components.values())

        # Group components by type
        by_type: dict[ComponentType, list[Component]] = {}
        for c in components:
            by_type.setdefault(c.type, []).append(c)

        for ctype, comps in by_type.items():
            if len(comps) < 2:
                continue

            versions: dict[str, str] = {}
            for c in comps:
                ver = self._component_version(c)
                if ver:
                    versions[c.id] = ver

            if len(versions) < 2:
                continue

            unique_versions = set(versions.values())
            if len(unique_versions) <= 1:
                continue

            # Find the most common version as expected
            version_counts: dict[str, int] = {}
            for v in versions.values():
                version_counts[v] = version_counts.get(v, 0) + 1
            expected_ver = max(version_counts, key=lambda v: (version_counts[v], _version_tuple(v)))

            for comp_id, ver in versions.items():
                if ver == expected_ver:
                    continue

                comp = graph.get_component(comp_id)
                if comp is None:
                    continue  # pragma: no cover

                severity = self._version_skew_severity(expected_ver, ver)
                blast = self._compute_blast_radius(graph, comp_id)

                drifts.append(
                    DriftDetection(
                        component_id=comp_id,
                        drift_type=DriftType.VERSION_SKEW,
                        severity=severity,
                        expected_value=expected_ver,
                        actual_value=ver,
                        remediation=f"Upgrade {comp.name} from {ver} to {expected_ver}",
                        auto_fixable=severity in (DriftSeverity.LOW, DriftSeverity.INFO),
                        blast_radius=blast,
                    )
                )

        # Also detect version skew among directly connected components
        # that share the same technology tag
        drifts.extend(self._detect_connected_version_skew(graph))

        return drifts

    def detect_capacity_imbalance(self, graph: InfraGraph) -> list[DriftDetection]:
        """Detect capacity mismatches between connected components."""
        drifts: list[DriftDetection] = []

        for comp in graph.components.values():
            deps = graph.get_dependencies(comp.id)
            for dep_comp in deps:
                edge = graph.get_dependency_edge(comp.id, dep_comp.id)
                if not edge or edge.dependency_type != "requires":
                    continue

                # Check RPS capacity imbalance
                source_rps = comp.capacity.max_rps * comp.replicas
                target_rps = dep_comp.capacity.max_rps * dep_comp.replicas

                if target_rps > 0 and source_rps > target_rps * 2:
                    severity = DriftSeverity.HIGH if source_rps > target_rps * 4 else DriftSeverity.MEDIUM
                    blast = self._compute_blast_radius(graph, dep_comp.id)
                    drifts.append(
                        DriftDetection(
                            component_id=dep_comp.id,
                            drift_type=DriftType.CAPACITY_IMBALANCE,
                            severity=severity,
                            expected_value=f"rps>={source_rps}",
                            actual_value=f"rps={target_rps}",
                            remediation=(
                                f"Scale {dep_comp.name} to handle upstream capacity "
                                f"({source_rps} rps from {comp.name})"
                            ),
                            auto_fixable=dep_comp.autoscaling.enabled,
                            blast_radius=blast,
                        )
                    )

                # Check connection capacity imbalance
                source_conns = comp.capacity.max_connections * comp.replicas
                target_conns = dep_comp.capacity.max_connections * dep_comp.replicas

                if target_conns > 0 and source_conns > target_conns * 2:
                    severity = DriftSeverity.HIGH if source_conns > target_conns * 4 else DriftSeverity.MEDIUM
                    blast = self._compute_blast_radius(graph, dep_comp.id)
                    drifts.append(
                        DriftDetection(
                            component_id=dep_comp.id,
                            drift_type=DriftType.CAPACITY_IMBALANCE,
                            severity=severity,
                            expected_value=f"conns>={source_conns}",
                            actual_value=f"conns={target_conns}",
                            remediation=(
                                f"Increase max_connections on {dep_comp.name} "
                                f"to handle {source_conns} from {comp.name}"
                            ),
                            auto_fixable=False,
                            blast_radius=blast,
                        )
                    )

                # Check utilization imbalance
                source_util = comp.utilization()
                target_util = dep_comp.utilization()
                if target_util > 85 and source_util < 40:
                    blast = self._compute_blast_radius(graph, dep_comp.id)
                    drifts.append(
                        DriftDetection(
                            component_id=dep_comp.id,
                            drift_type=DriftType.CAPACITY_IMBALANCE,
                            severity=DriftSeverity.HIGH,
                            expected_value=f"util<70%",
                            actual_value=f"util={target_util:.0f}%",
                            remediation=(
                                f"{dep_comp.name} is at {target_util:.0f}% utilization "
                                f"while {comp.name} is at {source_util:.0f}%. Scale up the dependency."
                            ),
                            auto_fixable=dep_comp.autoscaling.enabled,
                            blast_radius=blast,
                        )
                    )

        return drifts

    def detect_security_drift(self, graph: InfraGraph) -> list[DriftDetection]:
        """Detect security policy inconsistencies across the graph."""
        drifts: list[DriftDetection] = []

        for comp in graph.components.values():
            sec = comp.security

            # Components with dependents that lack encryption in transit
            dependents = graph.get_dependents(comp.id)
            if dependents and not sec.encryption_in_transit:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.SECURITY_POLICY_DRIFT,
                        severity=DriftSeverity.HIGH,
                        expected_value="encryption_in_transit=true",
                        actual_value="encryption_in_transit=false",
                        remediation=f"Enable encryption in transit for {comp.name}",
                        auto_fixable=False,
                        blast_radius=blast,
                    )
                )

            # PCI scope without encryption at rest
            if comp.compliance_tags.pci_scope and not sec.encryption_at_rest:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.SECURITY_POLICY_DRIFT,
                        severity=DriftSeverity.CRITICAL,
                        expected_value="encryption_at_rest=true",
                        actual_value="encryption_at_rest=false",
                        remediation=(
                            f"Enable encryption at rest for PCI-scoped component {comp.name}"
                        ),
                        auto_fixable=False,
                        blast_radius=blast,
                    )
                )

            # PII without encryption at rest
            if comp.compliance_tags.contains_pii and not sec.encryption_at_rest:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.SECURITY_POLICY_DRIFT,
                        severity=DriftSeverity.HIGH,
                        expected_value="encryption_at_rest=true",
                        actual_value="encryption_at_rest=false",
                        remediation=(
                            f"Enable encryption at rest for PII-containing component {comp.name}"
                        ),
                        auto_fixable=False,
                        blast_radius=blast,
                    )
                )

            # External-facing without WAF
            if comp.type == ComponentType.LOAD_BALANCER and not sec.waf_protected:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.SECURITY_POLICY_DRIFT,
                        severity=DriftSeverity.MEDIUM,
                        expected_value="waf_protected=true",
                        actual_value="waf_protected=false",
                        remediation=f"Enable WAF protection on {comp.name}",
                        auto_fixable=False,
                        blast_radius=blast,
                    )
                )

            # No auth on app servers
            if comp.type == ComponentType.APP_SERVER and not sec.auth_required:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.SECURITY_POLICY_DRIFT,
                        severity=DriftSeverity.MEDIUM,
                        expected_value="auth_required=true",
                        actual_value="auth_required=false",
                        remediation=f"Enable authentication on {comp.name}",
                        auto_fixable=False,
                        blast_radius=blast,
                    )
                )

            # Database without backup
            if comp.type == ComponentType.DATABASE and not sec.backup_enabled:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.SECURITY_POLICY_DRIFT,
                        severity=DriftSeverity.HIGH,
                        expected_value="backup_enabled=true",
                        actual_value="backup_enabled=false",
                        remediation=f"Enable backups for database {comp.name}",
                        auto_fixable=True,
                        blast_radius=blast,
                    )
                )

            # Rate limiting for external APIs
            if comp.type == ComponentType.EXTERNAL_API and not sec.rate_limiting:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.SECURITY_POLICY_DRIFT,
                        severity=DriftSeverity.MEDIUM,
                        expected_value="rate_limiting=true",
                        actual_value="rate_limiting=false",
                        remediation=f"Enable rate limiting for external API {comp.name}",
                        auto_fixable=True,
                        blast_radius=blast,
                    )
                )

        # Check for mixed encryption policies among connected components
        drifts.extend(self._detect_encryption_inconsistency(graph))

        return drifts

    def detect_topology_drift(
        self, graph: InfraGraph, baseline_graph: InfraGraph
    ) -> list[DriftDetection]:
        """Detect topology changes from a baseline graph."""
        drifts: list[DriftDetection] = []

        current_ids = set(graph.components.keys())
        baseline_ids = set(baseline_graph.components.keys())

        # Components removed from baseline
        for cid in baseline_ids - current_ids:
            bcomp = baseline_graph.get_component(cid)
            name = bcomp.name if bcomp else cid
            blast = list(baseline_graph.get_all_affected(cid))
            drifts.append(
                DriftDetection(
                    component_id=cid,
                    drift_type=DriftType.TOPOLOGY_DRIFT,
                    severity=DriftSeverity.HIGH if blast else DriftSeverity.MEDIUM,
                    expected_value="present",
                    actual_value="absent",
                    remediation=f"Component {name} was removed; verify this was intentional",
                    auto_fixable=False,
                    blast_radius=blast,
                )
            )

        # Components added not in baseline
        for cid in current_ids - baseline_ids:
            comp = graph.get_component(cid)
            name = comp.name if comp else cid
            drifts.append(
                DriftDetection(
                    component_id=cid,
                    drift_type=DriftType.TOPOLOGY_DRIFT,
                    severity=DriftSeverity.INFO,
                    expected_value="absent",
                    actual_value="present",
                    remediation=f"New component {name} added; ensure it has proper configuration",
                    auto_fixable=False,
                    blast_radius=[],
                )
            )

        # Edge changes — compare dependency edges
        baseline_edges = {
            (d.source_id, d.target_id) for d in baseline_graph.all_dependency_edges()
        }
        current_edges = {
            (d.source_id, d.target_id) for d in graph.all_dependency_edges()
        }

        for src, tgt in baseline_edges - current_edges:
            # Only report if both components still exist
            if src in current_ids and tgt in current_ids:
                drifts.append(
                    DriftDetection(
                        component_id=src,
                        drift_type=DriftType.TOPOLOGY_DRIFT,
                        severity=DriftSeverity.MEDIUM,
                        expected_value=f"edge:{src}->{tgt}",
                        actual_value="absent",
                        remediation=f"Dependency {src}->{tgt} was removed; verify intent",
                        auto_fixable=False,
                        blast_radius=[],
                    )
                )

        for src, tgt in current_edges - baseline_edges:
            # Only report if both components existed in baseline
            if src in baseline_ids and tgt in baseline_ids:
                drifts.append(
                    DriftDetection(
                        component_id=src,
                        drift_type=DriftType.TOPOLOGY_DRIFT,
                        severity=DriftSeverity.LOW,
                        expected_value="absent",
                        actual_value=f"edge:{src}->{tgt}",
                        remediation=f"New dependency {src}->{tgt} added; verify it has proper config",
                        auto_fixable=False,
                        blast_radius=[],
                    )
                )

        # Replica count changes for existing components
        for cid in current_ids & baseline_ids:
            curr_comp = graph.get_component(cid)
            base_comp = baseline_graph.get_component(cid)
            if curr_comp and base_comp and curr_comp.replicas != base_comp.replicas:
                if curr_comp.replicas < base_comp.replicas:
                    severity = DriftSeverity.HIGH if curr_comp.replicas == 1 else DriftSeverity.MEDIUM
                    blast = self._compute_blast_radius(graph, cid)
                    drifts.append(
                        DriftDetection(
                            component_id=cid,
                            drift_type=DriftType.TOPOLOGY_DRIFT,
                            severity=severity,
                            expected_value=f"replicas={base_comp.replicas}",
                            actual_value=f"replicas={curr_comp.replicas}",
                            remediation=(
                                f"Restore replicas of {curr_comp.name} from "
                                f"{curr_comp.replicas} to {base_comp.replicas}"
                            ),
                            auto_fixable=curr_comp.autoscaling.enabled,
                            blast_radius=blast,
                        )
                    )
                else:
                    drifts.append(
                        DriftDetection(
                            component_id=cid,
                            drift_type=DriftType.TOPOLOGY_DRIFT,
                            severity=DriftSeverity.INFO,
                            expected_value=f"replicas={base_comp.replicas}",
                            actual_value=f"replicas={curr_comp.replicas}",
                            remediation="Replica increase detected; update baseline if intentional",
                            auto_fixable=False,
                            blast_radius=[],
                        )
                    )

        return drifts

    def calculate_drift_score(self, graph: InfraGraph) -> float:
        """Calculate an overall drift score (0-100, 100=no drift).

        The score is calculated from all detected drifts, where each drift
        applies a penalty based on its severity.
        """
        report = self.detect_drifts(graph)
        return report.drift_score

    def generate_remediation_plan(
        self, drifts: list[DriftDetection]
    ) -> RemediationPlan:
        """Generate a prioritized remediation plan from a list of drifts.

        Steps are ordered by severity (critical first) and within the same
        severity by drift type.
        """
        severity_priority = {
            DriftSeverity.CRITICAL: 1,
            DriftSeverity.HIGH: 2,
            DriftSeverity.MEDIUM: 3,
            DriftSeverity.LOW: 4,
            DriftSeverity.INFO: 5,
        }

        sorted_drifts = sorted(
            drifts,
            key=lambda d: (severity_priority.get(d.severity, 5), d.drift_type.value),
        )

        steps: list[RemediationStep] = []
        for i, drift in enumerate(sorted_drifts, start=1):
            steps.append(
                RemediationStep(
                    priority=i,
                    component_id=drift.component_id,
                    drift_type=drift.drift_type,
                    severity=drift.severity,
                    action=drift.remediation,
                    auto_fixable=drift.auto_fixable,
                    estimated_impact=self._estimate_impact(drift),
                )
            )

        auto_count = sum(1 for s in steps if s.auto_fixable)
        manual_count = len(steps) - auto_count

        risk_reduction = 0.0
        for drift in drifts:
            risk_reduction += self._severity_penalty(drift.severity)

        return RemediationPlan(
            steps=steps,
            total_steps=len(steps),
            auto_fixable_steps=auto_count,
            manual_steps=manual_count,
            estimated_risk_reduction=min(100.0, risk_reduction),
        )

    # ------------------------------------------------------------------ #
    # Internal detection methods
    # ------------------------------------------------------------------ #

    def _detect_config_drift(self, graph: InfraGraph) -> list[DriftDetection]:
        """Detect configuration drift within the graph.

        Looks for inconsistencies like autoscaling disabled on components
        with high utilization, or circuit breakers disabled on critical edges.
        """
        drifts: list[DriftDetection] = []

        for comp in graph.components.values():
            # High utilization without autoscaling
            util = comp.utilization()
            if util > 80 and not comp.autoscaling.enabled:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.CONFIG_DRIFT,
                        severity=DriftSeverity.HIGH if util > 90 else DriftSeverity.MEDIUM,
                        expected_value="autoscaling=enabled",
                        actual_value=f"autoscaling=disabled,util={util:.0f}%",
                        remediation=(
                            f"Enable autoscaling on {comp.name} (utilization: {util:.0f}%)"
                        ),
                        auto_fixable=True,
                        blast_radius=blast,
                    )
                )

            # Failover disabled on critical components (databases, caches)
            if comp.type in (ComponentType.DATABASE, ComponentType.CACHE):
                dependents = graph.get_dependents(comp.id)
                if dependents and not comp.failover.enabled:
                    blast = self._compute_blast_radius(graph, comp.id)
                    drifts.append(
                        DriftDetection(
                            component_id=comp.id,
                            drift_type=DriftType.CONFIG_DRIFT,
                            severity=DriftSeverity.HIGH,
                            expected_value="failover=enabled",
                            actual_value="failover=disabled",
                            remediation=f"Enable failover for {comp.name}",
                            auto_fixable=False,
                            blast_radius=blast,
                        )
                    )

        # Check circuit breakers on critical dependency edges
        for dep in graph.all_dependency_edges():
            if dep.dependency_type == "requires" and not dep.circuit_breaker.enabled:
                target = graph.get_component(dep.target_id)
                source = graph.get_component(dep.source_id)
                if target and source:
                    blast = self._compute_blast_radius(graph, dep.target_id)
                    drifts.append(
                        DriftDetection(
                            component_id=dep.source_id,
                            drift_type=DriftType.CONFIG_DRIFT,
                            severity=DriftSeverity.MEDIUM,
                            expected_value="circuit_breaker=enabled",
                            actual_value="circuit_breaker=disabled",
                            remediation=(
                                f"Enable circuit breaker on {source.name}->{target.name}"
                            ),
                            auto_fixable=True,
                            blast_radius=blast,
                        )
                    )

        return drifts

    def _detect_protocol_mismatch(self, graph: InfraGraph) -> list[DriftDetection]:
        """Detect protocol mismatches on dependency edges."""
        drifts: list[DriftDetection] = []

        edges = graph.all_dependency_edges()
        if not edges:
            return drifts

        # Group edges by target to find protocol inconsistency
        target_protocols: dict[str, list[tuple[str, str]]] = {}
        for dep in edges:
            if dep.protocol:
                target_protocols.setdefault(dep.target_id, []).append(
                    (dep.source_id, dep.protocol)
                )

        for target_id, sources in target_protocols.items():
            protocols = {proto for _, proto in sources}
            if len(protocols) > 1:
                target = graph.get_component(target_id)
                if not target:
                    continue  # pragma: no cover
                proto_list = ", ".join(sorted(protocols))
                blast = self._compute_blast_radius(graph, target_id)
                for source_id, proto in sources:
                    drifts.append(
                        DriftDetection(
                            component_id=source_id,
                            drift_type=DriftType.PROTOCOL_MISMATCH,
                            severity=DriftSeverity.MEDIUM,
                            expected_value=f"consistent_protocol",
                            actual_value=f"protocol={proto} (target has: {proto_list})",
                            remediation=(
                                f"Standardise protocol for connections to {target.name}"
                            ),
                            auto_fixable=False,
                            blast_radius=blast,
                        )
                    )

        return drifts

    def _detect_tls_expiry(self, graph: InfraGraph) -> list[DriftDetection]:
        """Detect TLS-related issues based on component configuration."""
        drifts: list[DriftDetection] = []

        for comp in graph.components.values():
            # Flag components that handle traffic but lack encryption in transit
            if comp.type in (
                ComponentType.LOAD_BALANCER,
                ComponentType.WEB_SERVER,
                ComponentType.EXTERNAL_API,
            ):
                if not comp.security.encryption_in_transit:
                    blast = self._compute_blast_radius(graph, comp.id)
                    drifts.append(
                        DriftDetection(
                            component_id=comp.id,
                            drift_type=DriftType.TLS_EXPIRY,
                            severity=DriftSeverity.CRITICAL,
                            expected_value="tls=enabled",
                            actual_value="tls=disabled",
                            remediation=f"Enable TLS on {comp.name}",
                            auto_fixable=False,
                            blast_radius=blast,
                        )
                    )

        return drifts

    def _detect_compliance_drift(self, graph: InfraGraph) -> list[DriftDetection]:
        """Detect compliance policy drifts."""
        drifts: list[DriftDetection] = []

        for comp in graph.components.values():
            ct = comp.compliance_tags

            # PCI scope without audit logging
            if ct.pci_scope and not ct.audit_logging:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.COMPLIANCE_DRIFT,
                        severity=DriftSeverity.CRITICAL,
                        expected_value="audit_logging=true",
                        actual_value="audit_logging=false",
                        remediation=f"Enable audit logging for PCI-scoped {comp.name}",
                        auto_fixable=True,
                        blast_radius=blast,
                    )
                )

            # PCI scope without change management
            if ct.pci_scope and not ct.change_management:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.COMPLIANCE_DRIFT,
                        severity=DriftSeverity.HIGH,
                        expected_value="change_management=true",
                        actual_value="change_management=false",
                        remediation=f"Enable change management for PCI-scoped {comp.name}",
                        auto_fixable=False,
                        blast_radius=blast,
                    )
                )

            # PHI without encryption at rest
            if ct.contains_phi and not comp.security.encryption_at_rest:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.COMPLIANCE_DRIFT,
                        severity=DriftSeverity.CRITICAL,
                        expected_value="encryption_at_rest=true",
                        actual_value="encryption_at_rest=false",
                        remediation=(
                            f"Enable encryption at rest for PHI-containing {comp.name}"
                        ),
                        auto_fixable=False,
                        blast_radius=blast,
                    )
                )

            # Restricted data classification without network segmentation
            if ct.data_classification == "restricted" and not comp.security.network_segmented:
                blast = self._compute_blast_radius(graph, comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=comp.id,
                        drift_type=DriftType.COMPLIANCE_DRIFT,
                        severity=DriftSeverity.HIGH,
                        expected_value="network_segmented=true",
                        actual_value="network_segmented=false",
                        remediation=(
                            f"Enable network segmentation for restricted data on {comp.name}"
                        ),
                        auto_fixable=False,
                        blast_radius=blast,
                    )
                )

        return drifts

    def _detect_connected_version_skew(
        self, graph: InfraGraph
    ) -> list[DriftDetection]:
        """Detect version skew between directly connected components sharing tags."""
        drifts: list[DriftDetection] = []

        # Look for API version mismatches via tags like "api-v1", "api-v2"
        for comp in graph.components.values():
            api_ver = self._extract_api_version(comp)
            if not api_ver:
                continue

            deps = graph.get_dependencies(comp.id)
            for dep_comp in deps:
                dep_api_ver = self._extract_api_version(dep_comp)
                if dep_api_ver and dep_api_ver != api_ver:
                    blast = self._compute_blast_radius(graph, comp.id)
                    drifts.append(
                        DriftDetection(
                            component_id=comp.id,
                            drift_type=DriftType.API_VERSION_MISMATCH,
                            severity=DriftSeverity.HIGH,
                            expected_value=f"api_version={dep_api_ver}",
                            actual_value=f"api_version={api_ver}",
                            remediation=(
                                f"Align API version between {comp.name} ({api_ver}) "
                                f"and {dep_comp.name} ({dep_api_ver})"
                            ),
                            auto_fixable=False,
                            blast_radius=blast,
                        )
                    )

        return drifts

    def _detect_encryption_inconsistency(
        self, graph: InfraGraph
    ) -> list[DriftDetection]:
        """Detect encryption inconsistencies between connected components."""
        drifts: list[DriftDetection] = []
        seen: set[str] = set()

        for comp in graph.components.values():
            if not comp.security.encryption_in_transit:
                continue

            deps = graph.get_dependencies(comp.id)
            for dep_comp in deps:
                if dep_comp.security.encryption_in_transit:
                    continue
                key = f"{comp.id}->{dep_comp.id}"
                if key in seen:
                    continue  # pragma: no cover – defensive dedup
                seen.add(key)

                blast = self._compute_blast_radius(graph, dep_comp.id)
                drifts.append(
                    DriftDetection(
                        component_id=dep_comp.id,
                        drift_type=DriftType.SECURITY_POLICY_DRIFT,
                        severity=DriftSeverity.MEDIUM,
                        expected_value="encryption_in_transit=true",
                        actual_value="encryption_in_transit=false",
                        remediation=(
                            f"Enable encryption in transit on {dep_comp.name} "
                            f"(connected from encrypted {comp.name})"
                        ),
                        auto_fixable=False,
                        blast_radius=blast,
                    )
                )

        return drifts

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _component_version(comp: Component) -> str | None:
        """Extract a version from a component's name or tags."""
        # Try tags first (e.g. "v14.2", "redis-7.0")
        for tag in comp.tags:
            ver = _extract_version(tag)
            if ver:
                return ver
        # Try the component name
        return _extract_version(comp.name)

    @staticmethod
    def _extract_api_version(comp: Component) -> str | None:
        """Extract an API version string from component tags."""
        for tag in comp.tags:
            tag_lower = tag.lower()
            if tag_lower.startswith("api-v") or tag_lower.startswith("api_v"):
                return tag_lower
            if tag_lower.startswith("v") and tag_lower[1:].isdigit():
                return tag_lower
        return None

    @staticmethod
    def _version_skew_severity(expected: str, actual: str) -> DriftSeverity:
        """Determine severity of a version skew."""
        exp_major = _version_major(expected)
        act_major = _version_major(actual)
        if exp_major is not None and act_major is not None:
            diff = abs(exp_major - act_major)
            if diff >= 2:
                return DriftSeverity.CRITICAL
            if diff == 1:
                return DriftSeverity.HIGH
        # Minor/patch only
        exp_tuple = _version_tuple(expected)
        act_tuple = _version_tuple(actual)
        if exp_tuple != act_tuple:
            return DriftSeverity.MEDIUM
        return DriftSeverity.LOW

    @staticmethod
    def _compute_blast_radius(graph: InfraGraph, component_id: str) -> list[str]:
        """Return IDs of all transitively affected components."""
        return sorted(graph.get_all_affected(component_id))

    @staticmethod
    def _severity_penalty(severity: DriftSeverity) -> float:
        """Return the drift-score penalty for a given severity level."""
        return {
            DriftSeverity.CRITICAL: 15.0,
            DriftSeverity.HIGH: 8.0,
            DriftSeverity.MEDIUM: 4.0,
            DriftSeverity.LOW: 2.0,
            DriftSeverity.INFO: 0.5,
        }.get(severity, 1.0)

    @staticmethod
    def _estimate_impact(drift: DriftDetection) -> str:
        """Produce a human-readable impact estimate for a drift."""
        n = len(drift.blast_radius)
        if n == 0:
            return "Localised impact"
        if n <= 2:
            return f"Low blast radius ({n} component{'s' if n > 1 else ''})"
        if n <= 5:
            return f"Moderate blast radius ({n} components)"
        return f"High blast radius ({n} components)"

    def _build_report(
        self, drifts: list[DriftDetection], graph: InfraGraph
    ) -> DriftReport:
        """Build a DriftReport from a list of detections."""
        critical = sum(1 for d in drifts if d.severity == DriftSeverity.CRITICAL)
        high = sum(1 for d in drifts if d.severity == DriftSeverity.HIGH)
        medium = sum(1 for d in drifts if d.severity == DriftSeverity.MEDIUM)
        low = sum(1 for d in drifts if d.severity == DriftSeverity.LOW)
        auto_fixable = sum(1 for d in drifts if d.auto_fixable)

        # Calculate score: start at 100, subtract penalties
        score = 100.0
        for d in drifts:
            score -= self._severity_penalty(d.severity)
        score = max(0.0, min(100.0, score))

        recommendations = self._generate_recommendations(drifts, graph)

        return DriftReport(
            total_drifts=len(drifts),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            drifts=drifts,
            drift_score=round(score, 1),
            recommendations=recommendations,
            auto_fixable_count=auto_fixable,
        )

    @staticmethod
    def _generate_recommendations(
        drifts: list[DriftDetection], graph: InfraGraph
    ) -> list[str]:
        """Generate deduplicated recommendations from drift detections."""
        recs: list[str] = []
        seen_types: set[DriftType] = set()

        for d in drifts:
            if d.drift_type in seen_types:
                continue
            seen_types.add(d.drift_type)

            if d.drift_type == DriftType.VERSION_SKEW:
                recs.append(
                    "Standardise component versions across the fleet to prevent "
                    "compatibility issues."
                )
            elif d.drift_type == DriftType.CAPACITY_IMBALANCE:
                recs.append(
                    "Review capacity allocation between connected services to "
                    "prevent bottlenecks."
                )
            elif d.drift_type == DriftType.SECURITY_POLICY_DRIFT:
                recs.append(
                    "Enforce consistent security policies (encryption, auth, WAF) "
                    "across all components."
                )
            elif d.drift_type == DriftType.CONFIG_DRIFT:
                recs.append(
                    "Enable autoscaling and circuit breakers on high-utilisation "
                    "or critical components."
                )
            elif d.drift_type == DriftType.PROTOCOL_MISMATCH:
                recs.append(
                    "Standardise communication protocols for each target service."
                )
            elif d.drift_type == DriftType.TLS_EXPIRY:
                recs.append(
                    "Ensure TLS is enabled on all traffic-handling components."
                )
            elif d.drift_type == DriftType.COMPLIANCE_DRIFT:
                recs.append(
                    "Review compliance controls (audit logging, encryption, change "
                    "management) for regulated components."
                )
            elif d.drift_type == DriftType.API_VERSION_MISMATCH:
                recs.append(
                    "Align API versions between consumers and providers to prevent "
                    "integration failures."
                )
            elif d.drift_type == DriftType.TOPOLOGY_DRIFT:
                recs.append(
                    "Review topology changes and update the baseline if changes "
                    "are intentional."
                )

        return recs
