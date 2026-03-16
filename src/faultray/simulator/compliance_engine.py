"""Compliance Engine - auto-check infrastructure against regulatory frameworks.

Supports SOC 2 Type II, ISO 27001, PCI DSS, and NIST CSF frameworks.
Derives compliance status from InfraGraph topology and component configuration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


@dataclass
class ComplianceCheck:
    """Result of a single compliance control check."""

    framework: str  # "soc2", "iso27001", "pci_dss", "nist_csf"
    control_id: str  # e.g. "CC6.1", "A.17.1", "Req-6.1"
    description: str
    status: str  # "pass", "fail", "partial", "not_applicable"
    evidence: str  # what was checked
    recommendation: str  # how to fix if failed


@dataclass
class ComplianceReport:
    """Aggregated compliance report for a single framework."""

    framework: str
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    partial: int = 0
    compliance_percent: float = 0.0
    checks: list[ComplianceCheck] = field(default_factory=list)


class ComplianceEngine:
    """Check infrastructure compliance against regulatory frameworks.

    Derives compliance status from :class:`InfraGraph` topology by inspecting
    component configuration (replicas, failover, ports, tags, etc.) and
    dependency edges (circuit breakers, retry strategies).
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _has_redundancy(self, comp_types: list[ComponentType] | None = None) -> bool:
        """Check if critical components have replicas >= 2."""
        for comp in self.graph.components.values():
            if comp_types and comp.type not in comp_types:
                continue
            if comp.replicas >= 2:
                return True
        return False

    def _get_components_without_redundancy(self) -> list[str]:
        """Return IDs of components with replicas < 2 that have dependents."""
        result = []
        for comp in self.graph.components.values():
            dependents = self.graph.get_dependents(comp.id)
            if comp.replicas < 2 and len(dependents) > 0:
                result.append(comp.id)
        return result

    def _has_failover(self) -> bool:
        """Check if any database/cache has failover enabled."""
        for comp in self.graph.components.values():
            if comp.type in (ComponentType.DATABASE, ComponentType.CACHE):
                if comp.failover.enabled:
                    return True
        return False

    def _has_encryption(self) -> bool:
        """Check if components use TLS/encryption (port 443 or not port 80)."""
        for comp in self.graph.components.values():
            if comp.port == 443:
                return True
        return False

    def _has_non_encrypted(self) -> list[str]:
        """Return IDs of components using port 80 (non-TLS)."""
        return [
            comp.id
            for comp in self.graph.components.values()
            if comp.port == 80
        ]

    def _has_monitoring(self) -> bool:
        """Check if monitoring component exists (otel-collector, monitoring, prometheus)."""
        monitoring_keywords = {"otel", "monitoring", "prometheus", "grafana", "datadog", "newrelic"}
        for comp in self.graph.components.values():
            comp_lower = comp.id.lower() + " " + comp.name.lower()
            if any(kw in comp_lower for kw in monitoring_keywords):
                return True
        return False

    def _has_dr_region(self) -> bool:
        """Check if DR region components exist (by region config or naming)."""
        dr_keywords = {"dr-", "disaster", "backup-region", "standby-region"}
        for comp in self.graph.components.values():
            comp_lower = comp.id.lower() + " " + comp.name.lower()
            if any(kw in comp_lower for kw in dr_keywords):
                return True
            # Check region config
            region_cfg = getattr(comp, "region", None)
            if region_cfg is not None:
                if region_cfg.dr_target_region:
                    return True
                if not region_cfg.is_primary:
                    return True
        return False

    def _has_auth_waf(self) -> bool:
        """Check if auth/WAF components exist."""
        auth_keywords = {"auth", "waf", "firewall", "gateway", "oauth", "iam", "keycloak"}
        for comp in self.graph.components.values():
            comp_lower = comp.id.lower() + " " + comp.name.lower()
            if any(kw in comp_lower for kw in auth_keywords):
                return True
        return False

    def _circuit_breaker_coverage(self) -> tuple[int, int]:
        """Return (edges_with_cb, total_edges)."""
        all_edges = self.graph.all_dependency_edges()
        if not all_edges:
            return 0, 0
        cb_count = sum(1 for e in all_edges if e.circuit_breaker.enabled)
        return cb_count, len(all_edges)

    def _has_autoscaling(self) -> bool:
        """Check if any component has autoscaling enabled."""
        for comp in self.graph.components.values():
            if comp.autoscaling.enabled:
                return True
        return False

    def _build_report(self, framework: str, checks: list[ComplianceCheck]) -> ComplianceReport:
        """Build a ComplianceReport from a list of checks."""
        passed = sum(1 for c in checks if c.status == "pass")
        failed = sum(1 for c in checks if c.status == "fail")
        partial = sum(1 for c in checks if c.status == "partial")
        total = len(checks)
        pct = (passed + partial * 0.5) / total * 100.0 if total > 0 else 0.0
        return ComplianceReport(
            framework=framework,
            total_checks=total,
            passed=passed,
            failed=failed,
            partial=partial,
            compliance_percent=round(pct, 1),
            checks=checks,
        )

    # ------------------------------------------------------------------
    # SOC 2 Type II
    # ------------------------------------------------------------------

    def check_soc2(self) -> ComplianceReport:
        """Check SOC 2 Type II Trust Service Criteria.

        Covers: Availability, Security, Processing Integrity.
        """
        checks: list[ComplianceCheck] = []

        # CC6.1 - Logical and Physical Access Controls
        has_auth = self._has_auth_waf()
        checks.append(ComplianceCheck(
            framework="soc2",
            control_id="CC6.1",
            description="Logical and physical access controls",
            status="pass" if has_auth else "fail",
            evidence=f"Auth/WAF component found: {has_auth}",
            recommendation="" if has_auth else "Add authentication or WAF component for access control.",
        ))

        # CC6.6 - System boundaries and encryption
        has_enc = self._has_encryption()
        non_enc = self._has_non_encrypted()
        if has_enc and not non_enc:
            enc_status = "pass"
        elif has_enc:
            enc_status = "partial"
        else:
            enc_status = "fail"
        checks.append(ComplianceCheck(
            framework="soc2",
            control_id="CC6.6",
            description="Encryption of data in transit (TLS)",
            status=enc_status,
            evidence=f"TLS (port 443) detected: {has_enc}. Non-encrypted (port 80) components: {non_enc}",
            recommendation="" if enc_status == "pass" else "Ensure all external-facing components use TLS (port 443).",
        ))

        # CC7.2 - Monitoring and detection
        has_mon = self._has_monitoring()
        checks.append(ComplianceCheck(
            framework="soc2",
            control_id="CC7.2",
            description="System monitoring and anomaly detection",
            status="pass" if has_mon else "fail",
            evidence=f"Monitoring component found: {has_mon}",
            recommendation="" if has_mon else "Deploy monitoring (e.g. otel-collector, Prometheus) for anomaly detection.",
        ))

        # A1.2 - Availability: redundancy and failover
        no_redundancy = self._get_components_without_redundancy()
        has_fo = self._has_failover()
        if not no_redundancy and has_fo:
            avail_status = "pass"
        elif not no_redundancy or has_fo:
            avail_status = "partial"
        else:
            avail_status = "fail"
        checks.append(ComplianceCheck(
            framework="soc2",
            control_id="A1.2",
            description="Availability: redundancy and failover mechanisms",
            status=avail_status,
            evidence=f"Components without redundancy: {no_redundancy}. Failover enabled: {has_fo}",
            recommendation="" if avail_status == "pass" else "Add replicas >= 2 for critical components and enable failover on databases.",
        ))

        # PI1.3 - Processing Integrity: circuit breaker
        cb_count, total_edges = self._circuit_breaker_coverage()
        if total_edges == 0:
            cb_status = "not_applicable"
        elif cb_count == total_edges:
            cb_status = "pass"
        elif cb_count > 0:
            cb_status = "partial"
        else:
            cb_status = "fail"
        checks.append(ComplianceCheck(
            framework="soc2",
            control_id="PI1.3",
            description="Processing integrity: circuit breakers on dependencies",
            status=cb_status,
            evidence=f"Circuit breakers: {cb_count}/{total_edges} edges",
            recommendation="" if cb_status in ("pass", "not_applicable") else "Enable circuit breakers on all dependency edges to prevent cascade failures.",
        ))

        return self._build_report("soc2", checks)

    # ------------------------------------------------------------------
    # ISO 27001
    # ------------------------------------------------------------------

    def check_iso27001(self) -> ComplianceReport:
        """Check ISO 27001 Annex A controls (focus: A.17 business continuity)."""
        checks: list[ComplianceCheck] = []

        # A.17.1.1 - Planning information security continuity
        has_dr = self._has_dr_region()
        has_fo = self._has_failover()
        if has_dr and has_fo:
            bc_status = "pass"
        elif has_dr or has_fo:
            bc_status = "partial"
        else:
            bc_status = "fail"
        checks.append(ComplianceCheck(
            framework="iso27001",
            control_id="A.17.1.1",
            description="Planning information security continuity",
            status=bc_status,
            evidence=f"DR region exists: {has_dr}. Failover enabled: {has_fo}",
            recommendation="" if bc_status == "pass" else "Implement DR region and enable failover for business continuity planning.",
        ))

        # A.17.1.2 - Implementing information security continuity
        no_redundancy = self._get_components_without_redundancy()
        if not no_redundancy:
            redun_status = "pass"
        elif len(no_redundancy) <= len(self.graph.components) // 2:
            redun_status = "partial"
        else:
            redun_status = "fail"
        checks.append(ComplianceCheck(
            framework="iso27001",
            control_id="A.17.1.2",
            description="Implementing redundancy for continuity",
            status=redun_status,
            evidence=f"Components without redundancy: {no_redundancy}",
            recommendation="" if redun_status == "pass" else f"Add replicas >= 2 for: {', '.join(no_redundancy)}",
        ))

        # A.17.2.1 - Availability of information processing facilities
        has_as = self._has_autoscaling()
        checks.append(ComplianceCheck(
            framework="iso27001",
            control_id="A.17.2.1",
            description="Availability of information processing facilities",
            status="pass" if has_as else "partial",
            evidence=f"Autoscaling enabled: {has_as}",
            recommendation="" if has_as else "Enable autoscaling for capacity management during demand spikes.",
        ))

        # A.10.1.1 - Cryptographic controls
        has_enc = self._has_encryption()
        non_enc = self._has_non_encrypted()
        if has_enc and not non_enc:
            enc_status = "pass"
        elif has_enc:
            enc_status = "partial"
        else:
            enc_status = "fail"
        checks.append(ComplianceCheck(
            framework="iso27001",
            control_id="A.10.1.1",
            description="Policy on use of cryptographic controls",
            status=enc_status,
            evidence=f"TLS detected: {has_enc}. Non-encrypted components: {non_enc}",
            recommendation="" if enc_status == "pass" else "Enforce TLS encryption on all components.",
        ))

        # A.12.4.1 - Event logging
        has_mon = self._has_monitoring()
        checks.append(ComplianceCheck(
            framework="iso27001",
            control_id="A.12.4.1",
            description="Event logging and monitoring",
            status="pass" if has_mon else "fail",
            evidence=f"Monitoring component found: {has_mon}",
            recommendation="" if has_mon else "Deploy centralized logging and monitoring (e.g. ELK, Prometheus).",
        ))

        # A.9.1.1 - Access control policy
        has_auth = self._has_auth_waf()
        checks.append(ComplianceCheck(
            framework="iso27001",
            control_id="A.9.1.1",
            description="Access control policy",
            status="pass" if has_auth else "fail",
            evidence=f"Auth/WAF component found: {has_auth}",
            recommendation="" if has_auth else "Implement authentication and access control mechanisms.",
        ))

        return self._build_report("iso27001", checks)

    # ------------------------------------------------------------------
    # PCI DSS
    # ------------------------------------------------------------------

    def _has_pci_scope(self) -> bool:
        """Check if any component is tagged as PCI scope."""
        return any(
            comp.compliance_tags.pci_scope
            for comp in self.graph.components.values()
        )

    def _has_pii_data(self) -> bool:
        """Check if any component is tagged as containing PII."""
        return any(
            comp.compliance_tags.contains_pii
            for comp in self.graph.components.values()
        )

    def _has_audit_logging_tags(self) -> bool:
        """Check if any component has audit_logging compliance tag."""
        return any(
            comp.compliance_tags.audit_logging
            for comp in self.graph.components.values()
        )

    def check_pci_dss(self) -> ComplianceReport:
        """Check PCI DSS Requirements 6 (secure systems) and 10 (tracking/monitoring).

        When ``compliance_tags.pci_scope`` is True on any component, additional
        PCI-specific checks are generated for those components.
        """
        checks: list[ComplianceCheck] = []

        # Req-6.1 - Establish a process to identify security vulnerabilities
        has_mon = self._has_monitoring()
        cb_count, total_edges = self._circuit_breaker_coverage()
        if has_mon and (total_edges == 0 or cb_count > 0):
            vuln_status = "pass"
        elif has_mon or cb_count > 0:
            vuln_status = "partial"
        else:
            vuln_status = "fail"
        checks.append(ComplianceCheck(
            framework="pci_dss",
            control_id="Req-6.1",
            description="Identify and address security vulnerabilities",
            status=vuln_status,
            evidence=f"Monitoring: {has_mon}. Circuit breakers: {cb_count}/{total_edges}",
            recommendation="" if vuln_status == "pass" else "Deploy monitoring and circuit breakers for vulnerability management.",
        ))

        # Req-6.2 - Ensure all system components are protected from known vulnerabilities
        has_auth = self._has_auth_waf()
        has_enc = self._has_encryption()
        if has_auth and has_enc:
            prot_status = "pass"
        elif has_auth or has_enc:
            prot_status = "partial"
        else:
            prot_status = "fail"
        checks.append(ComplianceCheck(
            framework="pci_dss",
            control_id="Req-6.2",
            description="Protect systems from known vulnerabilities",
            status=prot_status,
            evidence=f"Auth/WAF: {has_auth}. Encryption: {has_enc}",
            recommendation="" if prot_status == "pass" else "Implement WAF/auth and enforce TLS encryption.",
        ))

        # Req-6.5 - Address common coding vulnerabilities
        # Check for circuit breakers as error-handling mechanism
        if total_edges == 0:
            coding_status = "not_applicable"
        elif cb_count == total_edges:
            coding_status = "pass"
        elif cb_count > 0:
            coding_status = "partial"
        else:
            coding_status = "fail"
        checks.append(ComplianceCheck(
            framework="pci_dss",
            control_id="Req-6.5",
            description="Address common coding vulnerabilities (error handling)",
            status=coding_status,
            evidence=f"Circuit breakers (error handling): {cb_count}/{total_edges} edges",
            recommendation="" if coding_status in ("pass", "not_applicable") else "Enable circuit breakers for proper error handling on all dependencies.",
        ))

        # Req-10.1 - Audit trails for all system components
        checks.append(ComplianceCheck(
            framework="pci_dss",
            control_id="Req-10.1",
            description="Implement audit trails for system components",
            status="pass" if has_mon else "fail",
            evidence=f"Monitoring/logging component found: {has_mon}",
            recommendation="" if has_mon else "Deploy centralized logging for audit trail compliance.",
        ))

        # Req-10.5 - Secure audit trails
        non_enc = self._has_non_encrypted()
        if has_enc and not non_enc:
            audit_sec_status = "pass"
        elif has_enc:
            audit_sec_status = "partial"
        else:
            audit_sec_status = "fail"
        checks.append(ComplianceCheck(
            framework="pci_dss",
            control_id="Req-10.5",
            description="Secure audit trails so they cannot be altered",
            status=audit_sec_status,
            evidence=f"TLS encryption: {has_enc}. Non-encrypted: {non_enc}",
            recommendation="" if audit_sec_status == "pass" else "Enforce TLS to protect audit trail data in transit.",
        ))

        # Req-10.6 - Review logs and security events
        checks.append(ComplianceCheck(
            framework="pci_dss",
            control_id="Req-10.6",
            description="Review logs and security events regularly",
            status="pass" if has_mon else "fail",
            evidence=f"Monitoring component for log review: {has_mon}",
            recommendation="" if has_mon else "Deploy monitoring to enable regular log review.",
        ))

        # --- PCI scope-specific checks (from compliance_tags) ---
        pci_components = [
            c for c in self.graph.components.values()
            if c.compliance_tags.pci_scope
        ]
        if pci_components:
            # Req-3.4 - Render PAN unreadable: all PCI-scope components need encryption at rest
            all_encrypted = all(c.security.encryption_at_rest for c in pci_components)
            pci_enc_ids = [c.id for c in pci_components if not c.security.encryption_at_rest]
            checks.append(ComplianceCheck(
                framework="pci_dss",
                control_id="Req-3.4",
                description="Render PAN unreadable (encryption at rest for PCI-scope components)",
                status="pass" if all_encrypted else "fail",
                evidence=f"PCI-scope components without encryption_at_rest: {pci_enc_ids}",
                recommendation="" if all_encrypted else f"Enable encryption at rest on PCI-scope components: {', '.join(pci_enc_ids)}",
            ))

            # Req-1.3 - Prohibit direct public access to cardholder data
            all_segmented = all(c.security.network_segmented for c in pci_components)
            pci_seg_ids = [c.id for c in pci_components if not c.security.network_segmented]
            checks.append(ComplianceCheck(
                framework="pci_dss",
                control_id="Req-1.3",
                description="Prohibit direct public access to cardholder data environment",
                status="pass" if all_segmented else "fail",
                evidence=f"PCI-scope components without network segmentation: {pci_seg_ids}",
                recommendation="" if all_segmented else f"Enable network segmentation for PCI-scope components: {', '.join(pci_seg_ids)}",
            ))

        return self._build_report("pci_dss", checks)

    # ------------------------------------------------------------------
    # NIST CSF
    # ------------------------------------------------------------------

    def check_nist_csf(self) -> ComplianceReport:
        """Check NIST Cybersecurity Framework 5 functions.

        Functions: Identify, Protect, Detect, Respond, Recover.
        """
        checks: list[ComplianceCheck] = []

        # --- IDENTIFY ---
        # ID.AM-1 - Asset management: physical devices and systems
        total_comps = len(self.graph.components)
        checks.append(ComplianceCheck(
            framework="nist_csf",
            control_id="ID.AM-1",
            description="Physical devices and systems inventoried",
            status="pass" if total_comps > 0 else "fail",
            evidence=f"Infrastructure graph contains {total_comps} components",
            recommendation="" if total_comps > 0 else "Define infrastructure components in the model.",
        ))

        # ID.AM-2 - Asset management: software platforms and applications
        all_edges = self.graph.all_dependency_edges()
        checks.append(ComplianceCheck(
            framework="nist_csf",
            control_id="ID.AM-2",
            description="Software platforms and applications inventoried",
            status="pass" if total_comps > 0 and len(all_edges) > 0 else "partial" if total_comps > 0 else "fail",
            evidence=f"Components: {total_comps}, Dependencies mapped: {len(all_edges)}",
            recommendation="" if total_comps > 0 else "Map all software components and dependencies.",
        ))

        # --- PROTECT ---
        # PR.AC-1 - Access control: identities and credentials managed
        has_auth = self._has_auth_waf()
        checks.append(ComplianceCheck(
            framework="nist_csf",
            control_id="PR.AC-1",
            description="Identities and credentials managed for access control",
            status="pass" if has_auth else "fail",
            evidence=f"Auth/WAF component found: {has_auth}",
            recommendation="" if has_auth else "Add authentication/authorization components (auth, WAF, OAuth).",
        ))

        # PR.DS-2 - Data-in-transit protection
        has_enc = self._has_encryption()
        non_enc = self._has_non_encrypted()
        if has_enc and not non_enc:
            transit_status = "pass"
        elif has_enc:
            transit_status = "partial"
        else:
            transit_status = "fail"
        checks.append(ComplianceCheck(
            framework="nist_csf",
            control_id="PR.DS-2",
            description="Data-in-transit is protected",
            status=transit_status,
            evidence=f"TLS (port 443): {has_enc}. Non-encrypted (port 80): {non_enc}",
            recommendation="" if transit_status == "pass" else "Enforce TLS encryption on all communication channels.",
        ))

        # --- DETECT ---
        # DE.CM-1 - Network monitoring
        has_mon = self._has_monitoring()
        checks.append(ComplianceCheck(
            framework="nist_csf",
            control_id="DE.CM-1",
            description="Network is monitored to detect potential cybersecurity events",
            status="pass" if has_mon else "fail",
            evidence=f"Monitoring component found: {has_mon}",
            recommendation="" if has_mon else "Deploy network monitoring (Prometheus, Datadog, otel-collector).",
        ))

        # --- RESPOND ---
        # RS.MI-1 - Incidents are contained
        cb_count, total_edges = self._circuit_breaker_coverage()
        if total_edges == 0:
            contain_status = "not_applicable"
        elif cb_count == total_edges:
            contain_status = "pass"
        elif cb_count > 0:
            contain_status = "partial"
        else:
            contain_status = "fail"
        checks.append(ComplianceCheck(
            framework="nist_csf",
            control_id="RS.MI-1",
            description="Incidents are contained (circuit breakers)",
            status=contain_status,
            evidence=f"Circuit breakers: {cb_count}/{total_edges} dependency edges",
            recommendation="" if contain_status in ("pass", "not_applicable") else "Enable circuit breakers on dependencies to contain incident blast radius.",
        ))

        # --- RECOVER ---
        # RC.RP-1 - Recovery plan is executed
        has_fo = self._has_failover()
        has_as = self._has_autoscaling()
        has_dr = self._has_dr_region()
        recovery_count = sum([has_fo, has_as, has_dr])
        if recovery_count >= 2:
            recover_status = "pass"
        elif recovery_count == 1:
            recover_status = "partial"
        else:
            recover_status = "fail"
        checks.append(ComplianceCheck(
            framework="nist_csf",
            control_id="RC.RP-1",
            description="Recovery plan is executed during/after an event",
            status=recover_status,
            evidence=f"Failover: {has_fo}. Autoscaling: {has_as}. DR region: {has_dr}",
            recommendation="" if recover_status == "pass" else "Implement at least two of: failover, autoscaling, DR region.",
        ))

        # RC.IM-1 - Recovery planning includes lessons learned
        no_redundancy = self._get_components_without_redundancy()
        if not no_redundancy and has_fo:
            improve_status = "pass"
        elif not no_redundancy or has_fo:
            improve_status = "partial"
        else:
            improve_status = "fail"
        checks.append(ComplianceCheck(
            framework="nist_csf",
            control_id="RC.IM-1",
            description="Recovery improvements incorporated",
            status=improve_status,
            evidence=f"Components without redundancy: {no_redundancy}. Failover: {has_fo}",
            recommendation="" if improve_status == "pass" else "Ensure all critical components have redundancy and failover.",
        ))

        # --- Compliance tag-driven checks ---

        # PR.DS-1 - Data-at-rest protection for PII components (GDPR/privacy)
        pii_components = [
            c for c in self.graph.components.values()
            if c.compliance_tags.contains_pii
        ]
        if pii_components:
            all_enc_rest = all(c.security.encryption_at_rest for c in pii_components)
            all_enc_transit = all(c.security.encryption_in_transit for c in pii_components)
            pii_ids_no_enc = [c.id for c in pii_components
                              if not c.security.encryption_at_rest or not c.security.encryption_in_transit]
            if all_enc_rest and all_enc_transit:
                pii_status = "pass"
            elif all_enc_rest or all_enc_transit:
                pii_status = "partial"
            else:
                pii_status = "fail"
            checks.append(ComplianceCheck(
                framework="nist_csf",
                control_id="PR.DS-1",
                description="Data-at-rest is protected (PII/GDPR compliance)",
                status=pii_status,
                evidence=f"PII components without full encryption: {pii_ids_no_enc}",
                recommendation="" if pii_status == "pass" else f"Enable encryption at rest and in transit for PII components: {', '.join(pii_ids_no_enc)}",
            ))

        # DE.AE-3 - Audit logging: use compliance_tags.audit_logging
        audit_components = list(self.graph.components.values())
        if audit_components:
            audit_tagged = [c for c in audit_components if c.compliance_tags.audit_logging]
            has_audit_tags = len(audit_tagged) > 0
            # Pass if either monitoring exists OR audit_logging tags are set
            if has_mon and has_audit_tags:
                audit_status = "pass"
            elif has_mon or has_audit_tags:
                audit_status = "partial"
            else:
                audit_status = "fail"
            checks.append(ComplianceCheck(
                framework="nist_csf",
                control_id="DE.AE-3",
                description="Event data aggregated and correlated (audit logging)",
                status=audit_status,
                evidence=f"Monitoring: {has_mon}. Components with audit_logging tag: {len(audit_tagged)}/{len(audit_components)}",
                recommendation="" if audit_status == "pass" else "Enable audit logging on components and deploy centralized monitoring.",
            ))

        return self._build_report("nist_csf", checks)

    # ------------------------------------------------------------------
    # Aggregate
    # ------------------------------------------------------------------

    def check_all(self) -> dict[str, ComplianceReport]:
        """Run all compliance framework checks and return results."""
        return {
            "soc2": self.check_soc2(),
            "iso27001": self.check_iso27001(),
            "pci_dss": self.check_pci_dss(),
            "nist_csf": self.check_nist_csf(),
        }
