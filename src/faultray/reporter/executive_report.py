# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Executive Summary Report - 1-page C-level summary of infrastructure resilience.

Generates a traffic-light style executive summary with top risks, ROI table,
and key availability metrics suitable for non-technical stakeholders.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from faultray.model.graph import InfraGraph


def _esc(text: str) -> str:
    """Escape text for safe HTML embedding."""
    return html.escape(str(text))


@dataclass
class ExecutiveSummary:
    """One-page executive summary for C-level stakeholders."""

    overall_status: str  # "GREEN", "YELLOW", "RED"
    headline: str  # e.g., "Your infrastructure can survive 98% of failure scenarios"

    # Traffic light indicators
    availability_status: str  # GREEN/YELLOW/RED
    security_status: str
    cost_risk_status: str
    compliance_status: str

    # Key numbers
    scenarios_tested: int = 0
    scenarios_passed_percent: float = 0.0
    estimated_annual_risk: float = 0.0  # $ amount
    slo_achievable: bool = True
    availability_nines: float = 0.0

    # Top 3 risks
    top_risks: list[dict] = field(default_factory=list)  # [{name, impact, recommendation}]

    # ROI table
    roi_items: list[dict] = field(default_factory=list)  # [{action, cost, risk_reduction, roi_percent}]


def _traffic_light(score: float, has_critical: bool = False) -> str:
    """Determine traffic light status from a score and critical flag.

    GREEN: score >= 80, no critical findings
    YELLOW: score 50-79, or any warnings
    RED: score < 50, or any critical findings
    """
    if has_critical or score < 50:
        return "RED"
    if score < 80:
        return "YELLOW"
    return "GREEN"


def _security_score(graph: InfraGraph) -> float:
    """Calculate a security score (0-100) from component SecurityProfile fields."""
    if not graph.components:
        return 0.0
    total = 0.0
    for comp in graph.components.values():
        sec = comp.security
        comp_score = 0.0
        if sec.encryption_at_rest:
            comp_score += 15
        if sec.encryption_in_transit:
            comp_score += 15
        if sec.waf_protected:
            comp_score += 10
        if sec.rate_limiting:
            comp_score += 10
        if sec.auth_required:
            comp_score += 15
        if sec.network_segmented:
            comp_score += 10
        if sec.backup_enabled:
            comp_score += 10
        if sec.log_enabled:
            comp_score += 10
        if sec.ids_monitored:
            comp_score += 5
        total += comp_score
    return total / len(graph.components)


def _compliance_score(compliance_reports: dict | None) -> float:
    """Calculate an average compliance score across all frameworks."""
    if not compliance_reports:
        return 100.0  # No compliance checks = assume compliant
    scores = []
    for report in compliance_reports.values():
        pct = getattr(report, "compliance_percent", 100.0)
        scores.append(pct)
    return sum(scores) / len(scores) if scores else 100.0


def generate_executive_summary(
    graph: InfraGraph,
    static_report=None,
    dynamic_report=None,
    ops_result=None,
    cost_report=None,
    compliance_reports=None,
) -> ExecutiveSummary:
    """Generate a 1-page executive summary from all available analysis results.

    Args:
        graph: Infrastructure graph.
        static_report: Optional SimulationReport from static simulation.
        dynamic_report: Optional DynamicSimulationReport.
        ops_result: Optional OpsSimulationResult.
        cost_report: Optional CostImpactReport.
        compliance_reports: Optional dict of framework -> ComplianceReport.

    Returns:
        An ExecutiveSummary dataclass with all fields populated.
    """
    # --- Scenarios tested / passed ---
    scenarios_tested = 0
    scenarios_passed = 0
    has_critical = False
    resilience_score = graph.resilience_score()

    if static_report is not None:
        results = getattr(static_report, "results", [])
        scenarios_tested += len(results)
        critical_findings = getattr(static_report, "critical_findings", [])
        getattr(static_report, "warnings", [])
        passed = getattr(static_report, "passed", [])
        scenarios_passed += len(passed)
        if critical_findings:
            has_critical = True

    if dynamic_report is not None:
        dyn_results = getattr(dynamic_report, "results", [])
        scenarios_tested += len(dyn_results)
        dyn_critical = sum(1 for r in dyn_results if getattr(r, "is_critical", False))
        dyn_passed = sum(
            1 for r in dyn_results
            if not getattr(r, "is_critical", False) and not getattr(r, "is_warning", False)
        )
        scenarios_passed += dyn_passed
        if dyn_critical > 0:
            has_critical = True

    passed_percent = (scenarios_passed / scenarios_tested * 100.0) if scenarios_tested > 0 else 100.0

    # --- Availability nines ---
    availability_nines = 0.0
    slo_achievable = True
    if ops_result is not None:
        sli_timeline = getattr(ops_result, "sli_timeline", [])
        if sli_timeline:
            avg_avail = sum(p.availability_percent for p in sli_timeline) / len(sli_timeline)
            if avg_avail > 0 and avg_avail < 100.0:
                availability_nines = -math.log10(1.0 - avg_avail / 100.0)
            elif avg_avail >= 100.0:
                availability_nines = 5.0  # Cap at 5 nines
            slo_achievable = avg_avail >= 99.9
    else:
        # Estimate from resilience score
        availability_nines = 2.0 + (resilience_score / 100.0) * 2.0

    # --- Annual risk ---
    estimated_annual_risk = 0.0
    if cost_report is not None:
        estimated_annual_risk = getattr(cost_report, "total_annual_risk", 0.0)

    # --- Traffic light statuses ---
    availability_score = resilience_score
    if ops_result is not None:
        sli_timeline = getattr(ops_result, "sli_timeline", [])
        if sli_timeline:
            avg_avail = sum(p.availability_percent for p in sli_timeline) / len(sli_timeline)
            # Map 99.9+ -> 100, 99.0 -> 80, 95.0 -> 50, <90 -> 0
            if avg_avail >= 99.9:
                availability_score = max(availability_score, 90)
            elif avg_avail >= 99.0:
                availability_score = max(min(availability_score, 90), 70)
            elif avg_avail >= 95.0:
                availability_score = min(availability_score, 60)
            else:
                availability_score = min(availability_score, 40)

    availability_status = _traffic_light(availability_score, has_critical)

    sec_score = _security_score(graph)
    security_has_critical = sec_score < 30
    security_status = _traffic_light(sec_score, security_has_critical)

    cost_score = 80.0
    if estimated_annual_risk > 100000:
        cost_score = 30.0
    elif estimated_annual_risk > 50000:
        cost_score = 50.0
    elif estimated_annual_risk > 10000:
        cost_score = 65.0
    cost_risk_status = _traffic_light(cost_score)

    comp_score = _compliance_score(compliance_reports)
    compliance_has_critical = False
    if compliance_reports:
        for report in compliance_reports.values():
            failed = getattr(report, "failed", 0)
            if failed > 0:
                compliance_has_critical = True
                break
    compliance_status = _traffic_light(comp_score, compliance_has_critical)

    # --- Overall status ---
    statuses = [availability_status, security_status, cost_risk_status, compliance_status]
    if "RED" in statuses:
        overall_status = "RED"
    elif "YELLOW" in statuses:
        overall_status = "YELLOW"
    else:
        overall_status = "GREEN"

    # --- Headline ---
    if overall_status == "GREEN":
        headline = f"Your infrastructure can survive {passed_percent:.0f}% of failure scenarios"
    elif overall_status == "YELLOW":
        headline = (
            f"Infrastructure is at moderate risk -- "
            f"{scenarios_tested - scenarios_passed} scenarios need attention"
        )
    else:
        headline = (
            "Critical infrastructure risks identified -- "
            "immediate action recommended"
        )

    # --- Top 3 risks ---
    top_risks: list[dict] = []

    if static_report is not None:
        critical_findings = getattr(static_report, "critical_findings", [])
        for finding in critical_findings[:3]:
            scenario = getattr(finding, "scenario", None)
            name = getattr(scenario, "name", "Unknown") if scenario else "Unknown"
            cascade = getattr(finding, "cascade", None)
            affected = len(getattr(cascade, "effects", [])) if cascade else 0
            top_risks.append({
                "name": name,
                "impact": f"Affects {affected} components",
                "recommendation": f"Add redundancy to prevent cascade failure from {name}",
            })

    # Fill remaining slots from dynamic report if needed
    if len(top_risks) < 3 and dynamic_report is not None:
        dyn_results = getattr(dynamic_report, "results", [])
        for r in dyn_results:
            if len(top_risks) >= 3:
                break
            if getattr(r, "is_critical", False) or getattr(r, "is_warning", False):
                scenario = getattr(r, "scenario", None)
                name = getattr(scenario, "name", "unknown") if scenario else "unknown"
                severity = getattr(r, "peak_severity", 0.0)
                top_risks.append({
                    "name": name,
                    "impact": f"Peak severity: {severity:.1f}",
                    "recommendation": f"Mitigate {name} scenario risk",
                })

    # Ensure at least some risks are listed
    if not top_risks:
        if not slo_achievable:
            top_risks.append({
                "name": "SLO target unreachable",
                "impact": "Current availability below 99.9% target",
                "recommendation": "Improve redundancy and failover configuration",
            })
        if sec_score < 50:
            top_risks.append({
                "name": "Security gaps detected",
                "impact": f"Security score: {sec_score:.0f}/100",
                "recommendation": "Enable encryption, WAF, and authentication across all components",
            })

    # --- ROI items ---
    roi_items: list[dict] = []

    # Generate ROI items from graph analysis
    for comp in graph.components.values():
        if comp.replicas <= 1 and len(graph.get_dependents(comp.id)) > 0:
            # Estimate cost of adding a replica
            monthly_cost = comp.cost_profile.hourly_infra_cost * 730  # hours/month
            annual_cost = monthly_cost * 12
            # Estimate risk reduction from eliminating SPOF
            risk_reduction = estimated_annual_risk * 0.3 if estimated_annual_risk > 0 else 5000
            roi_percent = ((risk_reduction - annual_cost) / annual_cost * 100) if annual_cost > 0 else 0
            roi_items.append({
                "action": f"Add replica for {comp.name}",
                "cost": round(annual_cost, 2),
                "risk_reduction": round(risk_reduction, 2),
                "roi_percent": round(roi_percent, 1),
            })
            if len(roi_items) >= 5:
                break

    # Sort ROI items by roi_percent descending
    roi_items.sort(key=lambda x: x.get("roi_percent", 0), reverse=True)

    return ExecutiveSummary(
        overall_status=overall_status,
        headline=headline,
        availability_status=availability_status,
        security_status=security_status,
        cost_risk_status=cost_risk_status,
        compliance_status=compliance_status,
        scenarios_tested=scenarios_tested,
        scenarios_passed_percent=round(passed_percent, 1),
        estimated_annual_risk=round(estimated_annual_risk, 2),
        slo_achievable=slo_achievable,
        availability_nines=round(availability_nines, 2),
        top_risks=top_risks[:3],
        roi_items=roi_items,
    )


def _status_color(status: str) -> str:
    """Return CSS color for a traffic light status."""
    return {
        "GREEN": "#28a745",
        "YELLOW": "#ffc107",
        "RED": "#dc3545",
    }.get(status, "#6c757d")


def _status_icon(status: str) -> str:
    """Return a text icon for a traffic light status."""
    return {
        "GREEN": "OK",
        "YELLOW": "WARN",
        "RED": "CRITICAL",
    }.get(status, "?")


def render_executive_html(summary: ExecutiveSummary) -> str:
    """Render the executive summary as a single-page HTML report.

    Args:
        summary: The populated ExecutiveSummary.

    Returns:
        HTML string suitable for writing to a file.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    overall_color = _status_color(summary.overall_status)

    # Traffic light cards
    indicators = [
        ("Availability", summary.availability_status),
        ("Security", summary.security_status),
        ("Cost Risk", summary.cost_risk_status),
        ("Compliance", summary.compliance_status),
    ]
    indicator_html = ""
    for label, status in indicators:
        color = _status_color(status)
        icon = _status_icon(status)
        indicator_html += f"""
        <div class="indicator-card">
          <div class="indicator-light" style="background:{color};"></div>
          <div class="indicator-label">{_esc(label)}</div>
          <div class="indicator-status" style="color:{color};">{_esc(icon)}</div>
        </div>"""

    # Key metrics
    nines_str = f"{summary.availability_nines:.2f}"
    slo_str = "Yes" if summary.slo_achievable else "No"
    slo_color = "#28a745" if summary.slo_achievable else "#dc3545"

    # Top risks
    risks_html = ""
    for i, risk in enumerate(summary.top_risks, 1):
        risks_html += f"""
        <div class="risk-item">
          <div class="risk-number">{i}</div>
          <div class="risk-content">
            <div class="risk-name">{_esc(risk.get('name', ''))}</div>
            <div class="risk-impact">{_esc(risk.get('impact', ''))}</div>
            <div class="risk-rec">{_esc(risk.get('recommendation', ''))}</div>
          </div>
        </div>"""

    # ROI table rows
    roi_rows = ""
    for item in summary.roi_items:
        roi_pct = item.get("roi_percent", 0)
        roi_color = "#28a745" if roi_pct > 0 else "#dc3545"
        roi_rows += f"""
        <tr>
          <td>{_esc(item.get('action', ''))}</td>
          <td>${item.get('cost', 0):,.0f}</td>
          <td>${item.get('risk_reduction', 0):,.0f}</td>
          <td style="color:{roi_color};font-weight:bold;">{roi_pct:+.0f}%</td>
        </tr>"""

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Executive Summary - FaultRay</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.6;
      color: #333;
      max-width: 1000px;
      margin: 0 auto;
      padding: 20px;
      background: #f5f5f5;
    }}
    .header {{
      background: linear-gradient(135deg, {overall_color}, {overall_color}cc);
      color: white;
      padding: 30px;
      border-radius: 8px;
      margin-bottom: 24px;
      text-align: center;
    }}
    .header h1 {{ font-size: 22px; margin-bottom: 8px; }}
    .header .headline {{ font-size: 18px; opacity: 0.95; margin-top: 8px; }}
    .header .status-badge {{
      display: inline-block;
      background: rgba(255,255,255,0.2);
      padding: 4px 16px;
      border-radius: 20px;
      font-size: 14px;
      font-weight: bold;
      margin-top: 12px;
    }}
    .section {{
      background: white;
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 16px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    .section h2 {{
      font-size: 16px;
      color: #1a237e;
      border-bottom: 2px solid #e8eaf6;
      padding-bottom: 6px;
      margin-bottom: 12px;
    }}
    .indicator-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
    }}
    .indicator-card {{
      text-align: center;
      padding: 16px 8px;
      background: #f8f9fa;
      border-radius: 6px;
    }}
    .indicator-light {{
      width: 24px;
      height: 24px;
      border-radius: 50%;
      margin: 0 auto 8px;
    }}
    .indicator-label {{
      font-size: 12px;
      color: #666;
      margin-bottom: 4px;
    }}
    .indicator-status {{
      font-size: 14px;
      font-weight: bold;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}
    .metric-card {{
      background: #f8f9fa;
      border-radius: 6px;
      padding: 14px;
      text-align: center;
    }}
    .metric-card .value {{
      font-size: 26px;
      font-weight: bold;
      color: #1a237e;
    }}
    .metric-card .label {{
      font-size: 11px;
      color: #666;
      margin-top: 4px;
    }}
    .risk-item {{
      display: flex;
      align-items: flex-start;
      padding: 10px 0;
      border-bottom: 1px solid #eee;
    }}
    .risk-item:last-child {{ border-bottom: none; }}
    .risk-number {{
      background: #dc3545;
      color: white;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      font-size: 14px;
      margin-right: 12px;
      flex-shrink: 0;
    }}
    .risk-name {{ font-weight: bold; font-size: 14px; }}
    .risk-impact {{ font-size: 13px; color: #666; }}
    .risk-rec {{ font-size: 12px; color: #1a237e; margin-top: 4px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
      font-size: 13px;
    }}
    th, td {{
      padding: 8px 12px;
      text-align: left;
      border-bottom: 1px solid #eee;
    }}
    th {{
      background: #f5f5f5;
      font-weight: 600;
      color: #555;
    }}
    .footer {{
      text-align: center;
      color: #999;
      font-size: 11px;
      padding: 16px 0;
    }}
  </style>
</head>
<body>

<div class="header">
  <h1>Infrastructure Resilience - Executive Summary</h1>
  <div class="headline">{_esc(summary.headline)}</div>
  <div class="status-badge">Overall Status: {_esc(summary.overall_status)}</div>
</div>

<!-- Traffic Light Indicators -->
<div class="section">
  <h2>Status Overview</h2>
  <div class="indicator-grid">
    {indicator_html}
  </div>
</div>

<!-- Key Metrics -->
<div class="section">
  <h2>Key Metrics</h2>
  <div class="metric-grid">
    <div class="metric-card">
      <div class="value">{summary.scenarios_tested}</div>
      <div class="label">Scenarios Tested</div>
    </div>
    <div class="metric-card">
      <div class="value">{summary.scenarios_passed_percent:.0f}%</div>
      <div class="label">Scenarios Passed</div>
    </div>
    <div class="metric-card">
      <div class="value">{nines_str}</div>
      <div class="label">Availability (Nines)</div>
    </div>
    <div class="metric-card">
      <div class="value" style="color:{slo_color};">{slo_str}</div>
      <div class="label">SLO Achievable (99.9%)</div>
    </div>
    <div class="metric-card">
      <div class="value">${summary.estimated_annual_risk:,.0f}</div>
      <div class="label">Est. Annual Risk</div>
    </div>
  </div>
</div>

<!-- Top Risks -->
<div class="section">
  <h2>Top Risks</h2>
  {risks_html if risks_html else '<p style="color:#28a745;font-weight:bold;">No critical risks identified.</p>'}
</div>

<!-- ROI Table -->
<div class="section">
  <h2>Investment Recommendations (ROI)</h2>
  {"<p><em>No specific investment recommendations at this time.</em></p>" if not roi_rows else f'''
  <table>
    <thead>
      <tr>
        <th>Recommended Action</th>
        <th>Annual Cost</th>
        <th>Risk Reduction</th>
        <th>ROI</th>
      </tr>
    </thead>
    <tbody>{roi_rows}</tbody>
  </table>'''}
</div>

<div class="footer">
  Generated by FaultRay | {timestamp}
</div>

</body>
</html>"""

    return report_html
