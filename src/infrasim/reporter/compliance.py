"""Generate compliance reports for regulatory frameworks (DORA, SOC2).

DORA (Digital Operational Resilience Act) requires financial institutions to
demonstrate ICT risk management, incident reporting, resilience testing,
third-party risk management, and information sharing.

This module generates HTML reports mapping FaultZero simulation results to
DORA compliance requirements.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from infrasim.ai.analyzer import AIAnalysisReport, AIRecommendation
from infrasim.model.components import ComponentType, HealthStatus
from infrasim.model.graph import InfraGraph
from infrasim.simulator.engine import SimulationReport


def _esc(text: str) -> str:
    """Escape text for safe HTML embedding."""
    return html.escape(str(text))


def _severity_badge(severity: str) -> str:
    """Return an HTML badge for a severity level."""
    colors = {
        "critical": "#dc3545",
        "high": "#fd7e14",
        "medium": "#ffc107",
        "low": "#28a745",
    }
    color = colors.get(severity, "#6c757d")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;">{_esc(severity.upper())}</span>'
    )


def _health_badge(health: HealthStatus) -> str:
    """Return an HTML badge for a health status."""
    colors = {
        HealthStatus.HEALTHY: "#28a745",
        HealthStatus.DEGRADED: "#ffc107",
        HealthStatus.OVERLOADED: "#fd7e14",
        HealthStatus.DOWN: "#dc3545",
    }
    color = colors.get(health, "#6c757d")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;">{_esc(health.value.upper())}</span>'
    )


def generate_dora_report(
    graph: InfraGraph,
    sim_report: SimulationReport,
    ai_report: AIAnalysisReport,
    output_path: Path,
    ops_report: object | None = None,
) -> Path:
    """Generate DORA (Digital Operational Resilience Act) compliance report.

    DORA requires financial institutions to:
    1. ICT risk management framework
    2. ICT-related incident reporting
    3. Digital operational resilience testing
    4. ICT third-party risk management
    5. Information sharing

    Args:
        graph: Infrastructure graph.
        sim_report: Simulation results.
        ai_report: AI analysis report with recommendations.
        output_path: Path to write the HTML report.
        ops_report: Optional operational simulation report.

    Returns:
        The path to the generated HTML file.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total_components = len(graph.components)
    total_scenarios = len(sim_report.results)
    critical_count = len(sim_report.critical_findings)
    warning_count = len(sim_report.warnings)

    # ----- Section 1: ICT Risk Assessment -----
    risk_rows = ""
    for comp in graph.components.values():
        util = comp.utilization()
        dependents = graph.get_dependents(comp.id)
        is_spof = comp.replicas <= 1 and len(dependents) > 0

        risk_level = "Low"
        risk_color = "#28a745"
        if is_spof:
            risk_level = "Critical" if util > 50 else "High"
            risk_color = "#dc3545" if risk_level == "Critical" else "#fd7e14"
        elif util > 80:
            risk_level = "High"
            risk_color = "#fd7e14"
        elif util > 60:
            risk_level = "Medium"
            risk_color = "#ffc107"

        risk_rows += f"""
        <tr>
          <td>{_esc(comp.name)}</td>
          <td>{_esc(comp.type.value)}</td>
          <td>{comp.replicas}</td>
          <td>{util:.0f}%</td>
          <td>{len(dependents)}</td>
          <td style="color:{risk_color};font-weight:bold;">{risk_level}</td>
        </tr>"""

    # ----- Section 2: Resilience Testing Evidence -----
    scenario_rows = ""
    for result in sim_report.results:
        if result.is_critical or result.is_warning:
            affected = len(result.cascade.effects)
            label = "CRITICAL" if result.is_critical else "WARNING"
            color = "#dc3545" if result.is_critical else "#ffc107"
            scenario_rows += f"""
        <tr>
          <td>{_esc(result.scenario.name)}</td>
          <td style="color:{color};font-weight:bold;">{label}</td>
          <td>{result.risk_score:.1f}/10</td>
          <td>{affected}</td>
          <td>{_esc(result.scenario.description[:80])}</td>
        </tr>"""

    passed_count = len(sim_report.passed)

    # ----- Section 3: Third-Party Dependencies -----
    external_rows = ""
    external_count = 0
    for comp in graph.components.values():
        if comp.type == ComponentType.EXTERNAL_API:
            external_count += 1
            dependents = graph.get_dependents(comp.id)
            dep_names = ", ".join(d.name for d in dependents[:5])
            external_rows += f"""
        <tr>
          <td>{_esc(comp.name)}</td>
          <td>{comp.replicas}</td>
          <td>{_esc(dep_names) or "None"}</td>
          <td>{"Yes" if comp.failover.enabled else "No"}</td>
          <td>{"Yes" if comp.autoscaling.enabled else "No"}</td>
        </tr>"""

    # ----- Section 4: Cascade Impact Analysis -----
    cascade_rows = ""
    for result in sim_report.critical_findings[:10]:
        root = result.cascade.effects[0] if result.cascade.effects else None
        root_name = root.component_name if root else "Unknown"
        affected = len(result.cascade.effects)
        down_count = sum(
            1 for e in result.cascade.effects if e.health == HealthStatus.DOWN
        )
        cascade_rows += f"""
        <tr>
          <td>{_esc(root_name)}</td>
          <td>{_esc(result.scenario.name)}</td>
          <td>{affected}</td>
          <td>{down_count}</td>
          <td>{result.risk_score:.1f}/10</td>
        </tr>"""

    # ----- Section 5: Remediation Plan -----
    remediation_rows = ""
    for rec in ai_report.recommendations:
        remediation_rows += f"""
        <tr>
          <td>{_severity_badge(rec.severity)}</td>
          <td>{_esc(rec.title)}</td>
          <td>{_esc(rec.category)}</td>
          <td>{_esc(rec.description[:120])}</td>
          <td>{_esc(rec.remediation[:120])}</td>
          <td>{_esc(rec.estimated_impact)}</td>
          <td>{_esc(rec.effort)}</td>
        </tr>"""

    # ----- Build HTML -----
    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DORA Compliance Report - FaultZero</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.6;
      color: #333;
      max-width: 1200px;
      margin: 0 auto;
      padding: 20px;
      background: #f5f5f5;
    }}
    .header {{
      background: linear-gradient(135deg, #1a237e, #283593);
      color: white;
      padding: 30px;
      border-radius: 8px;
      margin-bottom: 24px;
    }}
    .header h1 {{ font-size: 24px; margin-bottom: 8px; }}
    .header p {{ opacity: 0.9; font-size: 14px; }}
    .section {{
      background: white;
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    .section h2 {{
      font-size: 18px;
      color: #1a237e;
      border-bottom: 2px solid #e8eaf6;
      padding-bottom: 8px;
      margin-bottom: 16px;
    }}
    .section h3 {{
      font-size: 15px;
      color: #333;
      margin-top: 16px;
      margin-bottom: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
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
    tr:hover {{ background: #fafafa; }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 16px;
    }}
    .metric-card {{
      background: #f8f9fa;
      border-radius: 6px;
      padding: 16px;
      text-align: center;
    }}
    .metric-card .value {{
      font-size: 28px;
      font-weight: bold;
      color: #1a237e;
    }}
    .metric-card .label {{
      font-size: 12px;
      color: #666;
      margin-top: 4px;
    }}
    .summary-box {{
      background: #e8eaf6;
      border-left: 4px solid #1a237e;
      padding: 16px;
      border-radius: 0 4px 4px 0;
      margin: 12px 0;
      font-size: 14px;
    }}
    .footer {{
      text-align: center;
      color: #999;
      font-size: 12px;
      padding: 20px 0;
    }}
  </style>
</head>
<body>

<div class="header">
  <h1>DORA Compliance Report</h1>
  <p>Digital Operational Resilience Act (EU 2022/2554)</p>
  <p>Generated: {timestamp} | FaultZero AI Analysis</p>
</div>

<!-- Executive Summary -->
<div class="section">
  <h2>Executive Summary</h2>
  <div class="summary-box">{_esc(ai_report.summary)}</div>
  <div class="metric-grid">
    <div class="metric-card">
      <div class="value">{total_components}</div>
      <div class="label">ICT Components</div>
    </div>
    <div class="metric-card">
      <div class="value">{total_scenarios}</div>
      <div class="label">Scenarios Tested</div>
    </div>
    <div class="metric-card">
      <div class="value">{critical_count}</div>
      <div class="label">Critical Findings</div>
    </div>
    <div class="metric-card">
      <div class="value">{ai_report.estimated_current_nines:.1f}</div>
      <div class="label">Estimated Nines</div>
    </div>
  </div>
  <p><strong>Availability Assessment:</strong> {_esc(ai_report.availability_assessment)}</p>
</div>

<!-- DORA Article 5-16: ICT Risk Management Framework -->
<div class="section">
  <h2>1. ICT Risk Management Framework (DORA Art. 5-16)</h2>
  <p>Assessment of ICT asset risk levels based on infrastructure simulation analysis.</p>
  <table>
    <thead>
      <tr>
        <th>Component</th><th>Type</th><th>Replicas</th>
        <th>Utilization</th><th>Dependents</th><th>Risk Level</th>
      </tr>
    </thead>
    <tbody>{risk_rows}</tbody>
  </table>
</div>

<!-- DORA Article 24-27: Resilience Testing -->
<div class="section">
  <h2>2. Digital Operational Resilience Testing (DORA Art. 24-27)</h2>
  <p>Chaos engineering simulation results demonstrating resilience testing coverage.</p>
  <div class="metric-grid">
    <div class="metric-card">
      <div class="value">{sim_report.resilience_score:.0f}/100</div>
      <div class="label">Resilience Score</div>
    </div>
    <div class="metric-card">
      <div class="value" style="color:#dc3545;">{critical_count}</div>
      <div class="label">Critical Scenarios</div>
    </div>
    <div class="metric-card">
      <div class="value" style="color:#ffc107;">{warning_count}</div>
      <div class="label">Warning Scenarios</div>
    </div>
    <div class="metric-card">
      <div class="value" style="color:#28a745;">{passed_count}</div>
      <div class="label">Passed Scenarios</div>
    </div>
  </div>
  <h3>Scenario Results (Critical and Warning)</h3>
  <table>
    <thead>
      <tr>
        <th>Scenario</th><th>Status</th><th>Risk Score</th>
        <th>Affected</th><th>Description</th>
      </tr>
    </thead>
    <tbody>{scenario_rows}</tbody>
  </table>
</div>

<!-- DORA Article 28-30: Third-Party Risk Management -->
<div class="section">
  <h2>3. ICT Third-Party Risk Management (DORA Art. 28-30)</h2>
  <p>External API and third-party service dependencies analysis.</p>
  {"<p><em>No external API dependencies detected.</em></p>" if external_count == 0 else f'''
  <p>Identified <strong>{external_count}</strong> third-party ICT service provider(s).</p>
  <table>
    <thead>
      <tr>
        <th>Service</th><th>Replicas</th><th>Dependent Components</th>
        <th>Failover</th><th>Autoscaling</th>
      </tr>
    </thead>
    <tbody>{external_rows}</tbody>
  </table>'''}
</div>

<!-- DORA Article 17-23: Incident Impact Analysis -->
<div class="section">
  <h2>4. ICT Incident Impact Analysis (DORA Art. 17-23)</h2>
  <p>Cascade failure analysis showing potential incident propagation paths.</p>
  {"<p><em>No critical cascade scenarios detected.</em></p>" if not cascade_rows else f'''
  <table>
    <thead>
      <tr>
        <th>Root Cause</th><th>Scenario</th><th>Total Affected</th>
        <th>Components DOWN</th><th>Risk Score</th>
      </tr>
    </thead>
    <tbody>{cascade_rows}</tbody>
  </table>'''}
</div>

<!-- Remediation Plan -->
<div class="section">
  <h2>5. Remediation Plan</h2>
  <p>AI-generated recommendations to improve operational resilience.</p>
  <div class="summary-box">{_esc(ai_report.upgrade_path)}</div>
  {"<p><em>No recommendations -- infrastructure meets current standards.</em></p>" if not remediation_rows else f'''
  <table>
    <thead>
      <tr>
        <th>Severity</th><th>Title</th><th>Category</th>
        <th>Description</th><th>Remediation</th>
        <th>Impact</th><th>Effort</th>
      </tr>
    </thead>
    <tbody>{remediation_rows}</tbody>
  </table>'''}
</div>

<!-- Top Risks -->
<div class="section">
  <h2>6. Top Risks Summary</h2>
  <ol>
    {"".join(f"<li>{_esc(risk)}</li>" for risk in ai_report.top_risks)}
  </ol>
</div>

<div class="footer">
  Generated by FaultZero AI Analysis Engine | {timestamp}
</div>

</body>
</html>"""

    output_path = Path(output_path)
    output_path.write_text(report_html, encoding="utf-8")
    return output_path
