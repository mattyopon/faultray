# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Compliance evidence HTML report generator.

Produces a printable HTML document that can be exported to PDF via
a browser's Print dialog (Ctrl+P -> Save as PDF).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from faultray.model.graph import InfraGraph

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_SUPPORTED_FRAMEWORKS = ("soc2", "iso27001", "dora", "fisc", "pci_dss", "nist_csf")


def _pct_class(pct: float) -> str:
    """Return a CSS class name based on compliance percentage."""
    if pct >= 80.0:
        return "pct-green"
    if pct >= 50.0:
        return "pct-yellow"
    return "pct-red"


def generate_compliance_html(
    graph: InfraGraph,
    frameworks: list[str],
    output_path: Path,
    org_name: str = "Your Organization",
) -> None:
    """Generate a printable HTML compliance evidence report.

    Args:
        graph: The infrastructure graph to assess.
        frameworks: List of framework identifiers to include.
                    Supported values: "soc2", "iso27001", "dora", "fisc",
                    "pci_dss", "nist_csf".
        output_path: Destination file path for the HTML output.
        org_name: Organisation name shown in the report header.
    """
    from faultray import __version__

    assessment_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Run compliance checks for each requested framework.
    framework_summaries: list[dict] = []
    framework_details: list[dict] = []

    for fw in frameworks:
        fw_lower = fw.lower()
        report = _run_framework(graph, fw_lower)
        if report is None:
            continue

        checks_data = [
            {
                "control_id": chk.control_id,
                "description": chk.description,
                "status": chk.status,
                "evidence": chk.evidence,
                "recommendation": chk.recommendation,
            }
            for chk in report.checks
        ]

        framework_summaries.append({
            "framework": fw_lower,
            "compliance_pct": f"{report.compliance_percent:.1f}",
            "pct_class": _pct_class(report.compliance_percent),
            "passed": report.passed,
            "partial": report.partial,
            "failed": report.failed,
            "total": report.total_checks,
        })

        framework_details.append({
            "framework": fw_lower,
            "compliance_pct": f"{report.compliance_percent:.1f}",
            "passed": report.passed,
            "partial": report.partial,
            "failed": report.failed,
            "checks": checks_data,
        })

    # Build component rows.
    components = [
        {
            "id": comp.id,
            "name": comp.name,
            "type": comp.type.value,
            "replicas": comp.replicas,
            "host": comp.host,
            "port": comp.port,
        }
        for comp in graph.components.values()
    ]

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("compliance_report.html")

    html = template.render(
        org_name=org_name,
        assessment_date=assessment_date,
        frameworks=[fw.lower() for fw in frameworks],
        total_components=len(graph.components),
        framework_summaries=framework_summaries,
        framework_details=framework_details,
        components=components,
        faultray_version=__version__,
    )

    output_path.write_text(html, encoding="utf-8")


def _run_framework(graph: InfraGraph, fw: str):  # type: ignore[return]
    """Run a compliance check for *fw* and return a ComplianceReport, or None."""
    from faultray.simulator.compliance_engine import ComplianceEngine

    engine = ComplianceEngine(graph)

    if fw == "soc2":
        return engine.check_soc2()
    if fw == "iso27001":
        return engine.check_iso27001()
    if fw in ("dora", "fisc"):
        # DORA/FISC are not in the lightweight ComplianceEngine; use the
        # monitoring-based ComplianceMonitor for richer data when available,
        # falling back to the closest available check.
        try:
            from faultray.simulator.compliance_monitor import (
                ComplianceFramework,
                ComplianceMonitor,
            )

            fw_enum = ComplianceFramework.DORA if fw == "dora" else None
            if fw_enum is None:
                # FISC is not in ComplianceFramework; map to NIST_CSF as closest
                fw_enum = ComplianceFramework.NIST_CSF

            monitor = ComplianceMonitor()
            monitor.track(graph)
            snapshot = monitor.assess(graph, fw_enum)

            # Convert ComplianceSnapshot → ComplianceReport-like object so the
            # template rendering code path stays uniform.
            class _SnapshotAdapter:
                def __init__(self, snap, fw_name: str) -> None:
                    self.framework = fw_name
                    self.total_checks = snap.total_controls
                    self.passed = snap.compliant
                    self.failed = snap.non_compliant
                    self.partial = snap.partial
                    self.compliance_percent = snap.compliance_percentage

                    from faultray.simulator.compliance_engine import ComplianceCheck

                    self.checks = [
                        ComplianceCheck(
                            framework=fw_name,
                            control_id=ctrl.control_id,
                            description=ctrl.title,
                            status=(
                                "pass"
                                if ctrl.status.value == "compliant"
                                else "partial"
                                if ctrl.status.value == "partial"
                                else "not_applicable"
                                if ctrl.status.value == "not_applicable"
                                else "fail"
                            ),
                            evidence="; ".join(ctrl.evidence) if ctrl.evidence else "—",
                            recommendation=(
                                "; ".join(ctrl.remediation[:2]) if ctrl.remediation else ""
                            ),
                        )
                        for ctrl in snap.controls
                    ]

            return _SnapshotAdapter(snapshot, fw)

        except Exception:  # noqa: BLE001
            # Graceful fallback: use nist_csf as a proxy
            return engine.check_nist_csf()

    if fw == "pci_dss":
        return engine.check_pci_dss()
    if fw == "nist_csf":
        return engine.check_nist_csf()

    return None
