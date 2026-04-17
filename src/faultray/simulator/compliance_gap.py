# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Compliance Gap Analyzer — identify gaps between infrastructure state and compliance requirements.

Supports SOC2, HIPAA, PCI-DSS, GDPR, and ISO27001 frameworks.
Inspects :class:`InfraGraph` component configuration (security profiles,
replication, failover, monitoring, etc.) to detect non-compliant areas and
produce actionable remediation plans.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ComplianceFramework(str, Enum):
    SOC2 = "soc2"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    GDPR = "gdpr"
    ISO27001 = "iso27001"


class ComplianceStatus(str, Enum):
    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"


class RemediationPriority(str, Enum):
    IMMEDIATE = "immediate"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ComplianceRequirement:
    """A single compliance requirement within a framework."""

    framework: ComplianceFramework
    requirement_id: str
    description: str
    category: str


@dataclass
class ComplianceGap:
    """A detected compliance gap for a specific component."""

    requirement: ComplianceRequirement
    status: ComplianceStatus
    component_id: str
    component_name: str
    finding: str
    remediation: str
    priority: RemediationPriority


@dataclass
class ComplianceGapReport:
    """Aggregated gap-analysis report for a single framework."""

    framework: ComplianceFramework
    total_requirements: int = 0
    compliant_count: int = 0
    partial_count: int = 0
    non_compliant_count: int = 0
    compliance_score: float = 0.0  # 0-100
    gaps: list[ComplianceGap] = field(default_factory=list)
    critical_gaps: list[ComplianceGap] = field(default_factory=list)
    remediation_plan: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Framework requirement definitions
# ---------------------------------------------------------------------------

_SOC2_REQUIREMENTS: list[ComplianceRequirement] = [
    ComplianceRequirement(ComplianceFramework.SOC2, "SOC2-CC6.1", "Encryption at rest for data stores", "Security"),
    ComplianceRequirement(ComplianceFramework.SOC2, "SOC2-CC6.7", "Encryption in transit", "Security"),
    ComplianceRequirement(ComplianceFramework.SOC2, "SOC2-CC7.2", "Monitoring and log collection", "Monitoring"),
    ComplianceRequirement(ComplianceFramework.SOC2, "SOC2-A1.2", "Redundancy (replicas > 1)", "Availability"),
    ComplianceRequirement(ComplianceFramework.SOC2, "SOC2-A1.3", "Backup enabled for data stores", "Availability"),
    ComplianceRequirement(ComplianceFramework.SOC2, "SOC2-CC6.3", "Access control enforcement", "Access Control"),
    ComplianceRequirement(ComplianceFramework.SOC2, "SOC2-CC8.1", "Failover capability", "Availability"),
]

_HIPAA_REQUIREMENTS: list[ComplianceRequirement] = [
    ComplianceRequirement(ComplianceFramework.HIPAA, "HIPAA-164.312a", "Access control for PHI systems", "Access Control"),
    ComplianceRequirement(ComplianceFramework.HIPAA, "HIPAA-164.312e", "Encryption in transit for PHI", "Security"),
    ComplianceRequirement(ComplianceFramework.HIPAA, "HIPAA-164.312d", "Encryption at rest for PHI", "Security"),
    ComplianceRequirement(ComplianceFramework.HIPAA, "HIPAA-164.312b", "Audit logging for PHI access", "Monitoring"),
    ComplianceRequirement(ComplianceFramework.HIPAA, "HIPAA-164.308a7", "Backup and disaster recovery for PHI", "Availability"),
    ComplianceRequirement(ComplianceFramework.HIPAA, "HIPAA-164.310d", "Data integrity controls", "Security"),
    ComplianceRequirement(ComplianceFramework.HIPAA, "HIPAA-164.312c", "Network segmentation for PHI", "Security"),
]

_PCI_DSS_REQUIREMENTS: list[ComplianceRequirement] = [
    ComplianceRequirement(ComplianceFramework.PCI_DSS, "PCI-3.4", "Encryption at rest for cardholder data", "Security"),
    ComplianceRequirement(ComplianceFramework.PCI_DSS, "PCI-4.1", "Encryption in transit", "Security"),
    ComplianceRequirement(ComplianceFramework.PCI_DSS, "PCI-10.1", "Audit trail / logging", "Monitoring"),
    ComplianceRequirement(ComplianceFramework.PCI_DSS, "PCI-1.3", "Network segmentation", "Security"),
    ComplianceRequirement(ComplianceFramework.PCI_DSS, "PCI-6.6", "WAF protection for web-facing apps", "Security"),
    ComplianceRequirement(ComplianceFramework.PCI_DSS, "PCI-9.5", "Backup for cardholder data", "Availability"),
    ComplianceRequirement(ComplianceFramework.PCI_DSS, "PCI-7.1", "Access control / auth required", "Access Control"),
    ComplianceRequirement(ComplianceFramework.PCI_DSS, "PCI-11.4", "IDS/IPS monitoring", "Monitoring"),
]

_GDPR_REQUIREMENTS: list[ComplianceRequirement] = [
    ComplianceRequirement(ComplianceFramework.GDPR, "GDPR-Art32a", "Encryption at rest for personal data", "Security"),
    ComplianceRequirement(ComplianceFramework.GDPR, "GDPR-Art32b", "Encryption in transit for personal data", "Security"),
    ComplianceRequirement(ComplianceFramework.GDPR, "GDPR-Art30", "Audit logging of processing activities", "Monitoring"),
    ComplianceRequirement(ComplianceFramework.GDPR, "GDPR-Art32c", "Availability and resilience (replicas)", "Availability"),
    ComplianceRequirement(ComplianceFramework.GDPR, "GDPR-Art32d", "Backup and restore capability", "Availability"),
    ComplianceRequirement(ComplianceFramework.GDPR, "GDPR-Art25", "Data protection by design (access control)", "Access Control"),
]

_ISO27001_REQUIREMENTS: list[ComplianceRequirement] = [
    ComplianceRequirement(ComplianceFramework.ISO27001, "ISO-A10.1", "Encryption at rest", "Security"),
    ComplianceRequirement(ComplianceFramework.ISO27001, "ISO-A13.1", "Encryption in transit", "Security"),
    ComplianceRequirement(ComplianceFramework.ISO27001, "ISO-A12.4", "Logging and monitoring", "Monitoring"),
    ComplianceRequirement(ComplianceFramework.ISO27001, "ISO-A17.1", "Redundancy and availability", "Availability"),
    ComplianceRequirement(ComplianceFramework.ISO27001, "ISO-A12.3", "Backup procedures", "Availability"),
    ComplianceRequirement(ComplianceFramework.ISO27001, "ISO-A9.1", "Access control policy", "Access Control"),
    ComplianceRequirement(ComplianceFramework.ISO27001, "ISO-A17.2", "Failover and disaster recovery", "Availability"),
    ComplianceRequirement(ComplianceFramework.ISO27001, "ISO-A13.2", "Network segmentation", "Security"),
]

_FRAMEWORK_REQUIREMENTS: dict[ComplianceFramework, list[ComplianceRequirement]] = {
    ComplianceFramework.SOC2: _SOC2_REQUIREMENTS,
    ComplianceFramework.HIPAA: _HIPAA_REQUIREMENTS,
    ComplianceFramework.PCI_DSS: _PCI_DSS_REQUIREMENTS,
    ComplianceFramework.GDPR: _GDPR_REQUIREMENTS,
    ComplianceFramework.ISO27001: _ISO27001_REQUIREMENTS,
}

# Data-store component types that require encryption at rest / backup
_DATA_STORE_TYPES = {ComponentType.DATABASE, ComponentType.STORAGE, ComponentType.CACHE}


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class ComplianceGapAnalyzer:
    """Analyze an :class:`InfraGraph` for compliance gaps across frameworks."""

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, graph: InfraGraph, framework: ComplianceFramework) -> ComplianceGapReport:
        """Analyze *graph* against a single *framework* and return a gap report."""
        requirements = _FRAMEWORK_REQUIREMENTS[framework]
        gaps: list[ComplianceGap] = []

        components = list(graph.components.values())
        if not components:
            # Empty graph: all requirements are non-compliant (no infra to check)
            for req in requirements:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id="N/A",
                    component_name="(no components)",
                    finding="No infrastructure components defined",
                    remediation="Define infrastructure components to evaluate compliance",
                    priority=RemediationPriority.IMMEDIATE,
                ))
            return self._build_report(framework, requirements, gaps)

        for req in requirements:
            gaps.extend(self._check_requirement(req, components, graph))

        return self._build_report(framework, requirements, gaps)

    def analyze_all(self, graph: InfraGraph) -> dict[ComplianceFramework, ComplianceGapReport]:
        """Analyze *graph* against every supported framework."""
        return {fw: self.analyze(graph, fw) for fw in ComplianceFramework}

    # ------------------------------------------------------------------
    # Requirement checking dispatcher
    # ------------------------------------------------------------------

    def _check_requirement(
        self,
        req: ComplianceRequirement,
        components: list[Component],
        graph: InfraGraph,
    ) -> list[ComplianceGap]:
        """Dispatch a requirement to the appropriate checker and return gaps."""
        cat = req.category.lower()
        req.requirement_id.lower()
        desc = req.description.lower()

        # Encryption at rest
        if "encryption at rest" in desc:
            return self._check_encryption_at_rest(req, components)

        # Encryption in transit
        if "encryption in transit" in desc:
            return self._check_encryption_in_transit(req, components)

        # IDS/IPS (check before generic monitoring to avoid mis-dispatch)
        if "ids" in desc or "ips" in desc:
            return self._check_ids(req, components)

        # WAF protection
        if "waf" in desc:
            return self._check_waf(req, components)

        # Monitoring / logging / audit
        if cat == "monitoring" or "logging" in desc or "audit" in desc:
            return self._check_monitoring(req, components)

        # Redundancy / replicas
        if "redundancy" in desc or "replicas" in desc:
            return self._check_redundancy(req, components)

        # Backup
        if "backup" in desc:
            return self._check_backup(req, components)

        # Access control
        if cat == "access control" or "access control" in desc:
            return self._check_access_control(req, components)

        # Failover / disaster recovery
        if "failover" in desc or "disaster recovery" in desc:
            return self._check_failover(req, components)

        # Network segmentation
        if "network segmentation" in desc or "segmentation" in desc:
            return self._check_network_segmentation(req, components)

        # Data integrity
        if "data integrity" in desc:
            return self._check_data_integrity(req, components)

        return []

    # ------------------------------------------------------------------
    # Individual checkers
    # ------------------------------------------------------------------

    def _check_encryption_at_rest(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        data_stores = [c for c in components if c.type in _DATA_STORE_TYPES]
        if not data_stores:
            # No data stores — check is not applicable
            return []
        for comp in data_stores:
            if not comp.security.encryption_at_rest:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"Encryption at rest is not enabled on {comp.name}",
                    remediation=f"Enable encryption at rest on {comp.name} ({comp.id})",
                    priority=RemediationPriority.IMMEDIATE,
                ))
        return gaps

    def _check_encryption_in_transit(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        for comp in components:
            if not comp.security.encryption_in_transit:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"Encryption in transit is not enabled on {comp.name}",
                    remediation=f"Enable TLS/encryption in transit on {comp.name} ({comp.id})",
                    priority=RemediationPriority.HIGH,
                ))
        return gaps

    def _check_monitoring(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        for comp in components:
            if not comp.security.log_enabled:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"Logging/monitoring is not enabled on {comp.name}",
                    remediation=f"Enable log collection and monitoring on {comp.name} ({comp.id})",
                    priority=RemediationPriority.HIGH,
                ))
        return gaps

    def _check_redundancy(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        for comp in components:
            if comp.replicas <= 1:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"{comp.name} has only {comp.replicas} replica(s)",
                    remediation=f"Increase replicas to >= 2 on {comp.name} ({comp.id})",
                    priority=RemediationPriority.HIGH,
                ))
        return gaps

    def _check_backup(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        data_stores = [c for c in components if c.type in _DATA_STORE_TYPES]
        if not data_stores:
            return []
        for comp in data_stores:
            if not comp.security.backup_enabled:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"Backup is not enabled on {comp.name}",
                    remediation=f"Enable automated backups on {comp.name} ({comp.id})",
                    priority=RemediationPriority.IMMEDIATE,
                ))
        return gaps

    def _check_access_control(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        for comp in components:
            if not comp.security.auth_required:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"Authentication/access control not enforced on {comp.name}",
                    remediation=f"Enable auth_required on {comp.name} ({comp.id})",
                    priority=RemediationPriority.HIGH,
                ))
        return gaps

    def _check_failover(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        # Failover is most critical for data stores and app servers
        critical_types = _DATA_STORE_TYPES | {ComponentType.APP_SERVER}
        for comp in components:
            if comp.type in critical_types and not comp.failover.enabled:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"Failover is not enabled on {comp.name}",
                    remediation=f"Enable failover on {comp.name} ({comp.id})",
                    priority=RemediationPriority.MEDIUM,
                ))
        return gaps

    def _check_network_segmentation(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        for comp in components:
            if not comp.security.network_segmented:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"Network segmentation not configured on {comp.name}",
                    remediation=f"Enable network segmentation for {comp.name} ({comp.id})",
                    priority=RemediationPriority.MEDIUM,
                ))
        return gaps

    def _check_waf(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        web_types = {ComponentType.WEB_SERVER, ComponentType.APP_SERVER, ComponentType.LOAD_BALANCER}
        for comp in components:
            if comp.type in web_types and not comp.security.waf_protected:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"WAF protection not enabled on web-facing {comp.name}",
                    remediation=f"Enable WAF protection on {comp.name} ({comp.id})",
                    priority=RemediationPriority.HIGH,
                ))
        return gaps

    def _check_ids(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        for comp in components:
            if not comp.security.ids_monitored:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"IDS/IPS monitoring not enabled on {comp.name}",
                    remediation=f"Enable IDS monitoring on {comp.name} ({comp.id})",
                    priority=RemediationPriority.MEDIUM,
                ))
        return gaps

    def _check_data_integrity(
        self, req: ComplianceRequirement, components: list[Component],
    ) -> list[ComplianceGap]:
        gaps: list[ComplianceGap] = []
        data_stores = [c for c in components if c.type in _DATA_STORE_TYPES]
        for comp in data_stores:
            # Data integrity = encryption at rest + backup + replicas > 1
            issues: list[str] = []
            if not comp.security.encryption_at_rest:
                issues.append("no encryption at rest")
            if not comp.security.backup_enabled:
                issues.append("no backup")
            if comp.replicas <= 1:
                issues.append("no redundancy (replicas=1)")
            if issues:
                gaps.append(ComplianceGap(
                    requirement=req,
                    status=ComplianceStatus.PARTIAL if len(issues) < 3 else ComplianceStatus.NON_COMPLIANT,
                    component_id=comp.id,
                    component_name=comp.name,
                    finding=f"Data integrity gaps on {comp.name}: {', '.join(issues)}",
                    remediation=f"Fix data integrity on {comp.name}: {'; '.join(issues)}",
                    priority=RemediationPriority.HIGH,
                ))
        return gaps

    # ------------------------------------------------------------------
    # Report builder
    # ------------------------------------------------------------------

    def _build_report(
        self,
        framework: ComplianceFramework,
        requirements: list[ComplianceRequirement],
        gaps: list[ComplianceGap],
    ) -> ComplianceGapReport:
        total_requirements = len(requirements)

        # Group gaps by requirement to determine per-requirement status
        req_statuses: dict[str, ComplianceStatus] = {}
        for gap in gaps:
            rid = gap.requirement.requirement_id
            current = req_statuses.get(rid, ComplianceStatus.COMPLIANT)
            # Escalate: NON_COMPLIANT > PARTIAL > COMPLIANT
            if gap.status == ComplianceStatus.NON_COMPLIANT:
                req_statuses[rid] = ComplianceStatus.NON_COMPLIANT
            elif gap.status == ComplianceStatus.PARTIAL and current != ComplianceStatus.NON_COMPLIANT:
                req_statuses[rid] = ComplianceStatus.PARTIAL

        non_compliant_count = sum(1 for s in req_statuses.values() if s == ComplianceStatus.NON_COMPLIANT)
        partial_count = sum(1 for s in req_statuses.values() if s == ComplianceStatus.PARTIAL)
        compliant_count = total_requirements - non_compliant_count - partial_count

        # Score: compliant=100%, partial=50%, non-compliant=0%
        if total_requirements > 0:
            score = (compliant_count * 100.0 + partial_count * 50.0) / total_requirements
        else:
            score = 0.0

        # Critical gaps = IMMEDIATE or HIGH priority
        critical_gaps = [
            g for g in gaps
            if g.priority in (RemediationPriority.IMMEDIATE, RemediationPriority.HIGH)
        ]

        # Remediation plan: ordered by priority
        priority_order = {
            RemediationPriority.IMMEDIATE: 0,
            RemediationPriority.HIGH: 1,
            RemediationPriority.MEDIUM: 2,
            RemediationPriority.LOW: 3,
        }
        sorted_gaps = sorted(gaps, key=lambda g: priority_order[g.priority])
        seen_remediations: set[str] = set()
        remediation_plan: list[str] = []
        for g in sorted_gaps:
            if g.remediation not in seen_remediations:
                seen_remediations.add(g.remediation)
                remediation_plan.append(f"[{g.priority.value.upper()}] {g.remediation}")

        return ComplianceGapReport(
            framework=framework,
            total_requirements=total_requirements,
            compliant_count=compliant_count,
            partial_count=partial_count,
            non_compliant_count=non_compliant_count,
            compliance_score=round(score, 1),
            gaps=gaps,
            critical_gaps=critical_gaps,
            remediation_plan=remediation_plan,
        )
