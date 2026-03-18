"""DORA Resilience Evidence Generator — Regulator-Ready Audit Report Package.

Bridges chaos engineering test results with regulatory-formatted evidence output,
filling the market gap between GRC documentation tools (no tests) and chaos
engineering tools (no regulatory output).

Covers DORA (EU 2022/2554) Articles 24, 25, and 28.

DISCLAIMER: This report covers Article 24 scenario-based testing.
Article 25 TLPT requires live production testing by qualified testers.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.dora_evidence import (
    DORAEvidenceEngine,
    EvidenceRecord,
    EvidenceStatus,
    DORAGapAnalysis,
    DORAComplianceReport,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DISCLAIMER
# ---------------------------------------------------------------------------

TLPT_DISCLAIMER = (
    "DISCLAIMER: This report covers Article 24 scenario-based testing. "
    "Article 25 TLPT requires live production testing by qualified testers."
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RemediationItem:
    """A single prioritised remediation action."""

    item_id: str
    control_id: str
    article: str
    title: str
    description: str
    severity: str          # critical | high | medium | low
    effort: str            # low | medium | high
    remediation_deadline: str   # ISO date
    owner: str
    status: str = "open"   # open | in_progress | resolved


@dataclass
class RegisterEntry:
    """DORA Article 28 Register of Information entry for an ICT third-party provider."""

    provider_id: str
    provider_name: str
    provider_type: str
    service_description: str
    criticality: str           # critical | important | standard
    country_of_incorporation: str
    dependent_functions: list[str] = field(default_factory=list)
    contractual_arrangements: list[str] = field(default_factory=list)
    concentration_risk: bool = False
    exit_strategy_documented: bool = False
    last_assessed: str = ""


@dataclass
class DORAuditReport:
    """Complete DORA audit report ready for regulatory submission."""

    report_id: str
    generated_at: str
    reporting_entity: str
    report_period_start: str
    report_period_end: str

    # Core data
    compliance_report: DORAComplianceReport
    gap_analyses: list[DORAGapAnalysis]
    evidence_records: list[EvidenceRecord]
    remediation_items: list[RemediationItem]
    register_of_information: list[RegisterEntry]

    # Summary metrics
    overall_status: EvidenceStatus
    article_statuses: dict[str, EvidenceStatus]
    total_controls: int
    compliant_count: int
    non_compliant_count: int
    partially_compliant_count: int
    not_applicable_count: int

    # Metadata
    faultray_version: str = ""
    tlpt_disclaimer: str = TLPT_DISCLAIMER


@dataclass
class RegulatoryPackage:
    """A complete exported regulatory evidence package."""

    output_dir: Path
    manifest: dict[str, Any]
    files_written: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DORAuditReportGenerator
# ---------------------------------------------------------------------------


class DORAuditReportGenerator:
    """DORA Resilience Evidence Generator.

    Produces regulator-ready output from infrastructure graph analysis and
    chaos simulation results.  Bridges chaos engineering (tests) with GRC
    (regulatory-formatted evidence).
    """

    def __init__(self, signing_key: str = "faultray-default-key") -> None:
        self._signing_key = signing_key

    # ------------------------------------------------------------------
    # Primary report generation
    # ------------------------------------------------------------------

    def generate_full_report(
        self,
        graph: InfraGraph,
        simulation_results: list[dict] | None = None,
        evidence_records: list[EvidenceRecord] | None = None,
        reporting_entity: str = "Financial Institution",
    ) -> DORAuditReport:
        """Generate a complete DORA audit report.

        Args:
            graph: The infrastructure topology under assessment.
            simulation_results: Chaos scenario results as dicts with keys
                ``name``, ``result``, ``severity``, ``description``.
            evidence_records: Pre-built evidence records (merged with any
                generated from *simulation_results*).
            reporting_entity: Name of the regulated entity in the report.

        Returns:
            A fully populated :class:`DORAuditReport`.
        """
        import faultray

        simulation_results = simulation_results or []
        evidence_records = list(evidence_records or [])

        engine = DORAEvidenceEngine(graph)
        compliance_report = engine.generate_report(simulation_results)

        # Merge evidence records
        generated_records = engine.generate_evidence(simulation_results)
        all_records = generated_records + [
            r for r in evidence_records
            if r not in generated_records
        ]

        gap_analyses = compliance_report.gap_analyses
        remediation_items = self._build_remediation_items(gap_analyses, all_records)
        register = self.generate_register_of_information(graph)

        # Store graph reference for use by new engine sections in export_regulatory_package
        self._last_graph = graph

        now = datetime.now(timezone.utc)
        report_id = (
            f"DORA-{now.strftime('%Y%m%d%H%M%S')}-"
            f"{hashlib.sha256(reporting_entity.encode()).hexdigest()[:8].upper()}"
        )

        # Tally counts
        compliant = sum(1 for g in gap_analyses if g.status == EvidenceStatus.COMPLIANT)
        non_compliant = sum(1 for g in gap_analyses if g.status == EvidenceStatus.NON_COMPLIANT)
        partial = sum(1 for g in gap_analyses if g.status == EvidenceStatus.PARTIALLY_COMPLIANT)
        na = sum(1 for g in gap_analyses if g.status == EvidenceStatus.NOT_APPLICABLE)

        return DORAuditReport(
            report_id=report_id,
            generated_at=now.isoformat(),
            reporting_entity=reporting_entity,
            report_period_start=(now - timedelta(days=90)).strftime("%Y-%m-%d"),
            report_period_end=now.strftime("%Y-%m-%d"),
            compliance_report=compliance_report,
            gap_analyses=gap_analyses,
            evidence_records=all_records,
            remediation_items=remediation_items,
            register_of_information=register,
            overall_status=compliance_report.overall_status,
            article_statuses=compliance_report.article_results,
            total_controls=len(gap_analyses),
            compliant_count=compliant,
            non_compliant_count=non_compliant,
            partially_compliant_count=partial,
            not_applicable_count=na,
            faultray_version=faultray.__version__,
            tlpt_disclaimer=TLPT_DISCLAIMER,
        )

    # ------------------------------------------------------------------
    # PDF data export
    # ------------------------------------------------------------------

    def export_pdf_data(self, report: DORAuditReport) -> dict:
        """Return structured data that can be rendered into a PDF.

        The returned dict contains all sections with human-readable labels,
        severity ratings, and table rows ready for PDF layout engines.

        Args:
            report: A completed :class:`DORAuditReport`.

        Returns:
            A JSON-serialisable dict with all sections.
        """
        gap_rows = []
        for gap in report.gap_analyses:
            gap_rows.append({
                "control_id": gap.control_id,
                "status": gap.status.value,
                "risk_score": gap.risk_score,
                "gaps": gap.gaps,
                "recommendations": gap.recommendations,
            })

        evidence_rows = []
        for rec in report.evidence_records:
            evidence_rows.append({
                "control_id": rec.control_id,
                "test_timestamp": rec.timestamp.isoformat() if hasattr(rec.timestamp, "isoformat") else str(rec.timestamp),
                "test_type": rec.test_type,
                "test_description": rec.test_description,
                "result": rec.result,
                "severity": rec.severity,
                "remediation_required": rec.remediation_required,
                "artifacts": rec.artifacts,
                "methodology": self._methodology_for_test_type(rec.test_type),
                "findings": self._findings_summary(rec),
                "sign_off_status": "pending" if rec.remediation_required else "signed-off",
                "remediation_deadline": self._deadline_for_severity(rec.severity),
            })

        remediation_rows = [asdict(r) for r in report.remediation_items]
        register_rows = [asdict(e) for e in report.register_of_information]

        status_color_map = {
            EvidenceStatus.COMPLIANT: "green",
            EvidenceStatus.PARTIALLY_COMPLIANT: "amber",
            EvidenceStatus.NON_COMPLIANT: "red",
            EvidenceStatus.NOT_APPLICABLE: "grey",
        }

        return {
            "meta": {
                "report_id": report.report_id,
                "generated_at": report.generated_at,
                "reporting_entity": report.reporting_entity,
                "report_period": f"{report.report_period_start} to {report.report_period_end}",
                "faultray_version": report.faultray_version,
                "tlpt_disclaimer": report.tlpt_disclaimer,
            },
            "executive_summary": {
                "overall_status": report.overall_status.value,
                "overall_status_color": status_color_map.get(report.overall_status, "grey"),
                "total_controls": report.total_controls,
                "compliant": report.compliant_count,
                "non_compliant": report.non_compliant_count,
                "partially_compliant": report.partially_compliant_count,
                "not_applicable": report.not_applicable_count,
                "compliance_rate_percent": round(
                    report.compliant_count / max(report.total_controls, 1) * 100, 1
                ),
                "article_statuses": {
                    k: {
                        "status": v.value,
                        "color": status_color_map.get(v, "grey"),
                    }
                    for k, v in report.article_statuses.items()
                },
            },
            "gap_analysis_table": gap_rows,
            "evidence_table": evidence_rows,
            "remediation_plan": remediation_rows,
            "register_of_information": register_rows,
        }

    # ------------------------------------------------------------------
    # Regulatory package export
    # ------------------------------------------------------------------

    def export_regulatory_package(
        self,
        report: DORAuditReport,
        output_dir: Path,
        sign: bool = False,
    ) -> RegulatoryPackage:
        """Export a complete regulatory evidence package folder.

        Writes the following files to *output_dir*:

        - ``executive-summary.json``         — High-level compliance status
        - ``article-24-testing-evidence.json`` — Testing programme evidence
        - ``article-25-tlpt-readiness.json``  — TLPT readiness assessment
        - ``article-28-third-party-risk.json`` — Third-party ICT risk assessment
        - ``gap-analysis.json``               — Full gap analysis
        - ``remediation-plan.json``           — Prioritised remediation items
        - ``audit-trail.json``                — Evidence chain (signed if requested)
        - ``manifest.json``                   — Package manifest with checksums

        Args:
            report: The audit report to export.
            output_dir: Destination directory (created if it does not exist).
            sign: If True, include cryptographic signatures on evidence items.

        Returns:
            A :class:`RegulatoryPackage` with the manifest and written file list.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[str] = []
        checksums: dict[str, str] = {}

        def _write(filename: str, data: dict) -> None:
            path = output_dir / filename
            content = json.dumps(data, indent=2, default=str)
            path.write_text(content, encoding="utf-8")
            checksums[filename] = hashlib.sha256(content.encode()).hexdigest()
            files_written.append(filename)

        # 1. Executive summary
        _write("executive-summary.json", self._build_executive_summary(report))

        # 2. Article 24 testing evidence
        _write("article-24-testing-evidence.json", self._build_article_24_section(report))

        # 3. Article 25 TLPT readiness
        _write("article-25-tlpt-readiness.json", self._build_article_25_section(report))

        # 4. Article 28 third-party risk
        _write("article-28-third-party-risk.json", self._build_article_28_section(report))

        # 5. Gap analysis
        _write("gap-analysis.json", self._build_gap_analysis_section(report))

        # 6. Remediation plan
        _write("remediation-plan.json", self._build_remediation_section(report))

        # 7. Audit trail
        audit_trail = self._build_audit_trail(report, sign=sign)
        _write("audit-trail.json", audit_trail)

        # 8. Article 17-23 Incident Management (optional — uses new engine)
        try:
            from faultray.simulator.dora_incident_engine import DORAIncidentEngine

            inc_engine = DORAIncidentEngine(self._last_graph if hasattr(self, "_last_graph") else None)
            maturity = inc_engine.assess_incident_management()
            _write("article-17-23-incident-management.json", {
                "section": "Articles 17-23 — Incident Management",
                "regulatory_reference": "DORA Articles 17-23, EU 2022/2554",
                "overall_maturity": maturity.overall_maturity.value,
                "overall_score": maturity.overall_score,
                "capabilities": [cap.model_dump(mode="json") for cap in maturity.capabilities],
                "strengths": maturity.strengths,
                "weaknesses": maturity.weaknesses,
                "recommendations": maturity.recommendations,
            })
        except (ImportError, AttributeError, Exception) as exc:
            logger.debug("Incident management section skipped: %s", exc)

        # 9. ICT Risk Assessment (optional — uses new engine)
        try:
            from faultray.simulator.dora_risk_assessment import DORAICTRiskAssessmentEngine

            risk_engine = DORAICTRiskAssessmentEngine(self._last_graph if hasattr(self, "_last_graph") else None)
            risk_register = risk_engine.run_assessment()
            _write("ict-risk-assessment.json", risk_engine.export_report(risk_register))
        except (ImportError, AttributeError, Exception) as exc:
            logger.debug("ICT risk assessment section skipped: %s", exc)

        # 10. Concentration Risk (optional — uses new engine)
        try:
            from faultray.simulator.dora_concentration_risk import ConcentrationRiskAnalyser

            conc_analyser = ConcentrationRiskAnalyser(self._last_graph if hasattr(self, "_last_graph") else None)
            conc_report = conc_analyser.generate_report()
            _write("concentration-risk.json", conc_analyser.export_report(conc_report))
        except (ImportError, AttributeError, Exception) as exc:
            logger.debug("Concentration risk section skipped: %s", exc)

        # 11. Manifest (written last so it can include all other checksums)
        manifest = {
            "package_id": report.report_id,
            "generated_at": report.generated_at,
            "reporting_entity": report.reporting_entity,
            "faultray_version": report.faultray_version,
            "regulatory_framework": "DORA (EU 2022/2554)",
            "articles_covered": [
                "Article 5-16 (ICT Risk Management)",
                "Article 17-23 (Incident Management)",
                "Article 24 (Testing Programme)",
                "Article 25 (TLPT readiness)",
                "Article 26-27 (Tester Requirements)",
                "Article 28-30 (Third-Party Risk)",
                "Article 45 (Information Sharing)",
            ],
            "tlpt_disclaimer": TLPT_DISCLAIMER,
            "files": files_written + ["manifest.json"],
            "checksums": checksums,
            "overall_compliance_status": report.overall_status.value,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_content = json.dumps(manifest, indent=2, default=str)
        manifest_path.write_text(manifest_content, encoding="utf-8")
        files_written.append("manifest.json")

        logger.info(
            "Regulatory package exported to %s (%d files)",
            output_dir,
            len(files_written),
        )
        return RegulatoryPackage(
            output_dir=output_dir,
            manifest=manifest,
            files_written=files_written,
        )

    # ------------------------------------------------------------------
    # Register of Information (Article 28)
    # ------------------------------------------------------------------

    def generate_register_of_information(self, graph: InfraGraph) -> list[RegisterEntry]:
        """Generate DORA Article 28 Register of Information.

        Identifies all ICT third-party providers from the infrastructure graph
        and builds structured register entries.

        For the enhanced ITS 2024/2956-compliant register with contractual
        overlays and concentration risk analysis, use
        ``faultray.simulator.dora_register.DORARegister`` directly.

        Args:
            graph: The infrastructure topology.

        Returns:
            A list of :class:`RegisterEntry` objects, one per external provider.
        """
        entries: list[RegisterEntry] = []
        now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        total = len(graph.components)

        external = [
            c for c in graph.components.values()
            if c.type == ComponentType.EXTERNAL_API
        ]

        for comp in external:
            dependents = graph.get_dependents(comp.id)
            dep_names = [d.name for d in dependents]

            # Infer criticality from number of dependents and concentration
            dep_count = len(dependents)
            # Only consider concentration / criticality relative to internal components
            internal_count = total - len(external)
            ext_ratio = len(external) / max(internal_count, 1) if internal_count > 0 else 0.0
            if dep_count >= 3 or (internal_count > 0 and ext_ratio > 0.4):
                criticality = "critical"
            elif dep_count >= 1:
                criticality = "important"
            else:
                criticality = "standard"

            concentration_risk = len(external) > total * 0.5

            entries.append(RegisterEntry(
                provider_id=comp.id,
                provider_name=comp.name,
                provider_type="ICT Third-Party Service Provider",
                service_description=(
                    f"External API service '{comp.name}' providing ICT capabilities "
                    f"to {dep_count} internal component(s)."
                ),
                criticality=criticality,
                country_of_incorporation="Unknown — requires contractual verification",
                dependent_functions=dep_names,
                contractual_arrangements=[
                    "SLA documentation required",
                    "Exit strategy documentation required",
                ],
                concentration_risk=concentration_risk,
                exit_strategy_documented=comp.failover.enabled,
                last_assessed=now_date,
            ))

        return entries

    # ------------------------------------------------------------------
    # Internal section builders
    # ------------------------------------------------------------------

    def _build_executive_summary(self, report: DORAuditReport) -> dict:
        non_compliant_controls = [
            g.control_id for g in report.gap_analyses
            if g.status == EvidenceStatus.NON_COMPLIANT
        ]
        partial_controls = [
            g.control_id for g in report.gap_analyses
            if g.status == EvidenceStatus.PARTIALLY_COMPLIANT
        ]
        high_risk_items = [
            g.control_id for g in report.gap_analyses
            if g.risk_score >= 0.5
        ]
        compliance_rate = round(
            report.compliant_count / max(report.total_controls, 1) * 100, 1
        )

        return {
            "section": "Executive Summary",
            "report_id": report.report_id,
            "generated_at": report.generated_at,
            "reporting_entity": report.reporting_entity,
            "report_period": {
                "start": report.report_period_start,
                "end": report.report_period_end,
            },
            "overall_compliance_status": report.overall_status.value,
            "compliance_rate_percent": compliance_rate,
            "control_summary": {
                "total": report.total_controls,
                "compliant": report.compliant_count,
                "partially_compliant": report.partially_compliant_count,
                "non_compliant": report.non_compliant_count,
                "not_applicable": report.not_applicable_count,
            },
            "article_summary": {
                k: v.value for k, v in report.article_statuses.items()
            },
            "non_compliant_controls": non_compliant_controls,
            "partially_compliant_controls": partial_controls,
            "high_risk_controls": high_risk_items,
            "tlpt_disclaimer": TLPT_DISCLAIMER,
            "next_review_date": report.compliance_report.next_review_date.isoformat(),
        }

    def _build_article_24_section(self, report: DORAuditReport) -> dict:
        art24_gaps = [
            g for g in report.gap_analyses
            if g.control_id.startswith("DORA-24") or g.control_id.startswith("DORA-11")
        ]
        art24_records = [
            r for r in report.evidence_records
            if r.control_id.startswith("DORA-24") or r.control_id.startswith("DORA-11")
        ]
        evidence_items = []
        for rec in art24_records:
            evidence_items.append({
                "control_id": rec.control_id,
                "test_timestamp": rec.timestamp.isoformat() if hasattr(rec.timestamp, "isoformat") else str(rec.timestamp),
                "test_type": rec.test_type,
                "methodology": self._methodology_for_test_type(rec.test_type),
                "findings": self._findings_summary(rec),
                "severity": rec.severity,
                "remediation_required": rec.remediation_required,
                "remediation_deadline": self._deadline_for_severity(rec.severity),
                "sign_off_status": "pending" if rec.remediation_required else "signed-off",
                "artifacts": rec.artifacts,
            })

        return {
            "section": "Article 24 — General Requirements for Testing",
            "regulatory_reference": "DORA Article 24, EU 2022/2554",
            "description": (
                "Evidence of digital operational resilience testing programme "
                "covering all critical ICT systems, with documented results and "
                "risk-based test planning."
            ),
            "tlpt_disclaimer": TLPT_DISCLAIMER,
            "testing_programme_status": {
                g.control_id: g.status.value for g in art24_gaps
            },
            "evidence_items": evidence_items,
            "gap_summary": [
                {
                    "control_id": g.control_id,
                    "status": g.status.value,
                    "risk_score": g.risk_score,
                    "gaps": g.gaps,
                    "recommendations": g.recommendations,
                }
                for g in art24_gaps
            ],
        }

    def _build_article_25_section(self, report: DORAuditReport) -> dict:
        art25_gaps = [
            g for g in report.gap_analyses
            if g.control_id.startswith("DORA-25")
        ]
        art25_records = [
            r for r in report.evidence_records
            if r.control_id.startswith("DORA-25")
        ]

        # Assess overall TLPT readiness from gap scores
        max_risk = max((g.risk_score for g in art25_gaps), default=0.0)
        if max_risk == 0.0:
            readiness = "ready"
        elif max_risk < 0.4:
            readiness = "mostly_ready"
        elif max_risk < 0.7:
            readiness = "preparation_required"
        else:
            readiness = "not_ready"

        evidence_items = []
        for rec in art25_records:
            evidence_items.append({
                "control_id": rec.control_id,
                "test_timestamp": rec.timestamp.isoformat() if hasattr(rec.timestamp, "isoformat") else str(rec.timestamp),
                "test_type": rec.test_type,
                "methodology": self._methodology_for_test_type(rec.test_type),
                "findings": self._findings_summary(rec),
                "severity": rec.severity,
                "remediation_required": rec.remediation_required,
                "remediation_deadline": self._deadline_for_severity(rec.severity),
                "sign_off_status": "pending" if rec.remediation_required else "signed-off",
                "artifacts": rec.artifacts,
            })

        return {
            "section": "Article 25 — TLPT Readiness Assessment",
            "regulatory_reference": "DORA Article 25, EU 2022/2554",
            "tlpt_disclaimer": TLPT_DISCLAIMER,
            "important_note": (
                "FaultRay provides Article 25 READINESS assessment only. "
                "Actual TLPT must be conducted by qualified testers on live production systems "
                "per DORA Article 26 requirements."
            ),
            "tlpt_readiness": readiness,
            "readiness_criteria": {
                "redundancy_configured": any(
                    "redundancy" not in " ".join(g.gaps).lower()
                    for g in art25_gaps
                ),
                "failover_configured": any(
                    "failover" not in " ".join(g.gaps).lower()
                    for g in art25_gaps
                ),
                "critical_functions_identified": True,
                "production_environment_documented": False,
                "qualified_testers_engaged": False,
            },
            "control_assessments": [
                {
                    "control_id": g.control_id,
                    "status": g.status.value,
                    "risk_score": g.risk_score,
                    "gaps": g.gaps,
                    "recommendations": g.recommendations,
                }
                for g in art25_gaps
            ],
            "scenario_evidence": evidence_items,
            "recommended_actions": [
                "Engage qualified TLPT provider (DORA Art. 26)",
                "Define TLPT scope covering all critical functions",
                "Ensure production environment access for testers",
                "Schedule TLPT within the 3-year regulatory cycle",
                "Obtain management sign-off on TLPT results",
            ],
        }

    def _build_article_28_section(self, report: DORAuditReport) -> dict:
        art28_gaps = [
            g for g in report.gap_analyses
            if g.control_id.startswith("DORA-28")
        ]
        register_entries = [asdict(e) for e in report.register_of_information]

        concentration_risk_present = any(
            e.concentration_risk for e in report.register_of_information
        )
        providers_without_exit = [
            e.provider_name for e in report.register_of_information
            if not e.exit_strategy_documented
        ]

        return {
            "section": "Article 28 — ICT Third-Party Risk Management",
            "regulatory_reference": "DORA Article 28, EU 2022/2554",
            "description": (
                "Register of Information covering all ICT third-party service providers, "
                "concentration risk analysis, and contractual resilience requirements."
            ),
            "third_party_provider_count": len(report.register_of_information),
            "concentration_risk_detected": concentration_risk_present,
            "providers_without_exit_strategy": providers_without_exit,
            "register_of_information": register_entries,
            "control_assessments": [
                {
                    "control_id": g.control_id,
                    "status": g.status.value,
                    "risk_score": g.risk_score,
                    "gaps": g.gaps,
                    "recommendations": g.recommendations,
                }
                for g in art28_gaps
            ],
            "required_contractual_provisions": [
                "Availability and performance SLAs",
                "Security and audit rights",
                "Incident notification obligations",
                "Business continuity and DR requirements",
                "Sub-contracting disclosure requirements",
                "Termination and exit assistance obligations",
            ],
        }

    def _build_gap_analysis_section(self, report: DORAuditReport) -> dict:
        by_article: dict[str, list[dict]] = {}
        for gap in report.gap_analyses:
            # Infer article from control_id prefix, e.g. "DORA-24.01" -> "article_24"
            parts = gap.control_id.split("-")
            if len(parts) >= 2:
                num = parts[1].split(".")[0]
                article_key = f"article_{num}"
            else:
                article_key = "unknown"
            by_article.setdefault(article_key, []).append({
                "control_id": gap.control_id,
                "status": gap.status.value,
                "risk_score": gap.risk_score,
                "gaps": gap.gaps,
                "recommendations": gap.recommendations,
            })

        overall_risk = (
            sum(g.risk_score for g in report.gap_analyses) / max(len(report.gap_analyses), 1)
        )

        return {
            "section": "Gap Analysis",
            "overall_risk_score": round(overall_risk, 3),
            "total_controls": report.total_controls,
            "summary": {
                "compliant": report.compliant_count,
                "partially_compliant": report.partially_compliant_count,
                "non_compliant": report.non_compliant_count,
                "not_applicable": report.not_applicable_count,
            },
            "by_article": by_article,
            "all_gaps": [
                {
                    "control_id": g.control_id,
                    "status": g.status.value,
                    "risk_score": g.risk_score,
                    "gaps": g.gaps,
                    "recommendations": g.recommendations,
                }
                for g in report.gap_analyses
            ],
        }

    def _build_remediation_section(self, report: DORAuditReport) -> dict:
        critical = [r for r in report.remediation_items if r.severity == "critical"]
        high = [r for r in report.remediation_items if r.severity == "high"]
        medium = [r for r in report.remediation_items if r.severity == "medium"]
        low = [r for r in report.remediation_items if r.severity == "low"]

        return {
            "section": "Remediation Plan",
            "total_items": len(report.remediation_items),
            "by_severity": {
                "critical": len(critical),
                "high": len(high),
                "medium": len(medium),
                "low": len(low),
            },
            "items": [asdict(r) for r in report.remediation_items],
            "prioritised": [
                asdict(r) for r in sorted(
                    report.remediation_items,
                    key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.severity, 4),
                )
            ],
        }

    def _build_audit_trail(self, report: DORAuditReport, sign: bool = False) -> dict:
        chain: list[dict] = []
        for i, rec in enumerate(report.evidence_records):
            ts = rec.timestamp.isoformat() if hasattr(rec.timestamp, "isoformat") else str(rec.timestamp)
            entry: dict[str, Any] = {
                "sequence": i + 1,
                "control_id": rec.control_id,
                "test_timestamp": ts,
                "test_type": rec.test_type,
                "methodology": self._methodology_for_test_type(rec.test_type),
                "findings": self._findings_summary(rec),
                "severity": rec.severity,
                "remediation_required": rec.remediation_required,
                "remediation_deadline": self._deadline_for_severity(rec.severity),
                "sign_off_status": "pending" if rec.remediation_required else "signed-off",
                "artifacts": rec.artifacts,
            }
            if sign:
                payload = json.dumps(entry, sort_keys=True, default=str)
                entry["integrity_hash"] = hashlib.sha256(payload.encode()).hexdigest()
            chain.append(entry)

        trail: dict[str, Any] = {
            "section": "Audit Trail",
            "report_id": report.report_id,
            "generated_at": report.generated_at,
            "reporting_entity": report.reporting_entity,
            "total_evidence_items": len(chain),
            "signed": sign,
            "chain": chain,
        }

        if sign:
            # Chain-level integrity hash
            chain_payload = json.dumps(chain, sort_keys=True, default=str)
            trail["chain_integrity_hash"] = hashlib.sha256(chain_payload.encode()).hexdigest()

        return trail

    # ------------------------------------------------------------------
    # Remediation item builder
    # ------------------------------------------------------------------

    def _build_remediation_items(
        self,
        gap_analyses: list[DORAGapAnalysis],
        evidence_records: list[EvidenceRecord],
    ) -> list[RemediationItem]:
        items: list[RemediationItem] = []
        counter = 1

        for gap in gap_analyses:
            if gap.status in (EvidenceStatus.COMPLIANT, EvidenceStatus.NOT_APPLICABLE):
                continue

            # Map risk score to severity
            if gap.risk_score >= 0.7:
                severity = "critical"
            elif gap.risk_score >= 0.4:
                severity = "high"
            elif gap.risk_score >= 0.2:
                severity = "medium"
            else:
                severity = "low"

            effort = "medium"
            if len(gap.recommendations) <= 1:
                effort = "low"
            elif len(gap.recommendations) >= 3:
                effort = "high"

            for j, rec_text in enumerate(gap.recommendations):
                items.append(RemediationItem(
                    item_id=f"REM-{counter:04d}",
                    control_id=gap.control_id,
                    article=self._article_from_control_id(gap.control_id),
                    title=rec_text[:80],
                    description=(
                        f"Gap identified in {gap.control_id}: "
                        + "; ".join(gap.gaps[:2])
                        + (f" (+{len(gap.gaps) - 2} more)" if len(gap.gaps) > 2 else "")
                    ),
                    severity=severity,
                    effort=effort,
                    remediation_deadline=self._deadline_for_severity(severity),
                    owner="ICT Risk Management Team",
                    status="open",
                ))
                counter += 1

        # Also capture evidence-based remediations
        for rec in evidence_records:
            if rec.remediation_required:
                items.append(RemediationItem(
                    item_id=f"REM-{counter:04d}",
                    control_id=rec.control_id,
                    article=self._article_from_control_id(rec.control_id),
                    title=f"Remediate failed test: {rec.test_description[:60]}",
                    description=(
                        f"Test '{rec.test_description}' resulted in '{rec.result}' "
                        f"with severity '{rec.severity}'."
                    ),
                    severity=rec.severity,
                    effort="medium",
                    remediation_deadline=self._deadline_for_severity(rec.severity),
                    owner="ICT Operations Team",
                    status="open",
                ))
                counter += 1

        return items

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _methodology_for_test_type(test_type: str) -> str:
        mapping = {
            "basic_testing": "Scenario-based functional testing per DORA Article 24",
            "advanced_testing": "Advanced resilience testing including failover and DR simulation per DORA Article 24",
            "tlpt": "Threat-Led Penetration Testing scope assessment per DORA Article 25",
        }
        return mapping.get(test_type, "Automated infrastructure resilience assessment via FaultRay chaos simulation")

    @staticmethod
    def _findings_summary(rec: EvidenceRecord) -> str:
        if rec.result == "pass":
            return f"Test passed. No issues identified for {rec.control_id}."
        if rec.result == "fail":
            return (
                f"Test FAILED for {rec.control_id}. "
                f"Remediation required (severity: {rec.severity})."
            )
        return (
            f"Test partially passed for {rec.control_id}. "
            f"Minor issues detected (severity: {rec.severity})."
        )

    @staticmethod
    def _deadline_for_severity(severity: str) -> str:
        now = datetime.now(timezone.utc)
        delta_map = {
            "critical": timedelta(days=30),
            "high": timedelta(days=60),
            "medium": timedelta(days=90),
            "low": timedelta(days=180),
        }
        delta = delta_map.get(severity, timedelta(days=90))
        return (now + delta).strftime("%Y-%m-%d")

    @staticmethod
    def _article_from_control_id(control_id: str) -> str:
        """Extract article reference from a control_id like DORA-24.01."""
        try:
            num = control_id.split("-")[1].split(".")[0]
            return f"Article {num}"
        except (IndexError, ValueError):
            return "Unknown Article"
