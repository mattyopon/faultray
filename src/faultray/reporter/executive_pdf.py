# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Executive PDF-Style HTML Report Generator.

Generates a visually stunning, print-optimized HTML report designed for
executive audiences. Includes:
- Executive summary with traffic-light scoring
- Financial impact analysis
- Trend charts (CSS-only, no JavaScript needed for printing)
- Compliance overview
- Risk heat map
- Actionable recommendations with effort/impact matrix
- Benchmarking comparison
- Appendix with technical details

Designed to be printed to PDF via browser or wkhtmltopdf.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone

from faultray.ai.analyzer import AIAnalysisReport
from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationReport


def _esc(text: str) -> str:
    """Escape text for safe HTML embedding."""
    return html.escape(str(text))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReportSection:
    """A section of the executive report."""

    title: str
    content_html: str
    page_break_before: bool = False


@dataclass
class ExecutiveReport:
    """Complete executive report data."""

    title: str
    company_name: str
    assessment_date: datetime
    prepared_by: str
    executive_summary: str
    resilience_grade: str  # A+ through F
    resilience_score: float
    financial_risk: str  # estimated annual risk $
    key_findings: list[str] = field(default_factory=list)
    recommendation_count: int = 0
    compliance_status: dict[str, float] = field(default_factory=dict)
    sections: list[ReportSection] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Grade calculation
# ---------------------------------------------------------------------------


def _score_to_grade(score: float) -> str:
    """Convert a resilience score (0-100) to a letter grade."""
    if score >= 95:
        return "A+"
    elif score >= 90:
        return "A"
    elif score >= 85:
        return "A-"
    elif score >= 80:
        return "B+"
    elif score >= 75:
        return "B"
    elif score >= 70:
        return "B-"
    elif score >= 65:
        return "C+"
    elif score >= 60:
        return "C"
    elif score >= 55:
        return "C-"
    elif score >= 50:
        return "D+"
    elif score >= 45:
        return "D"
    elif score >= 40:
        return "D-"
    else:
        return "F"


def _grade_color(grade: str) -> str:
    """Return CSS color for a grade."""
    if grade.startswith("A"):
        return "#28a745"
    elif grade.startswith("B"):
        return "#5cb85c"
    elif grade.startswith("C"):
        return "#ffc107"
    elif grade.startswith("D"):
        return "#fd7e14"
    else:
        return "#dc3545"


def _traffic_light_class(score: float) -> str:
    """Return CSS class for traffic light based on score (0-100)."""
    if score >= 80:
        return "status-green"
    elif score >= 50:
        return "status-yellow"
    else:
        return "status-red"


def _traffic_light_label(score: float) -> str:
    """Return text label for traffic light."""
    if score >= 80:
        return "Passed"
    elif score >= 50:
        return "Needs Attention"
    else:
        return "Critical"


# ---------------------------------------------------------------------------
# Executive Report Generator
# ---------------------------------------------------------------------------


class ExecutiveReportGenerator:
    """Generate executive PDF-style HTML reports."""

    def __init__(self) -> None:
        self._report: ExecutiveReport | None = None
        self._graph: InfraGraph | None = None
        self._sim_report: SimulationReport | None = None
        self._ai_report: AIAnalysisReport | None = None
        self._compliance_snapshots: dict | None = None

    def generate(
        self,
        graph: InfraGraph,
        sim_report: SimulationReport,
        ai_report: AIAnalysisReport,
        company_name: str = "Your Organization",
        prepared_by: str = "FaultRay AI Engine",
    ) -> str:
        """Generate a complete executive HTML report.

        Args:
            graph: Infrastructure graph.
            sim_report: Simulation results.
            ai_report: AI analysis report with recommendations.
            company_name: Company name for the report.
            prepared_by: Name of assessor.

        Returns:
            Complete self-contained HTML string.
        """
        self._graph = graph
        self._sim_report = sim_report
        self._ai_report = ai_report

        # Build compliance snapshots
        self._compliance_snapshots = self._assess_compliance(graph)

        # Calculate resilience grade
        resilience_score = sim_report.resilience_score
        grade = _score_to_grade(resilience_score)

        # Build key findings
        key_findings = []
        if sim_report.critical_findings:
            key_findings.append(
                f"{len(sim_report.critical_findings)} critical vulnerability"
                f"{'ies' if len(sim_report.critical_findings) != 1 else 'y'} detected"
            )
        spof_count = self._count_spofs(graph)
        if spof_count > 0:
            key_findings.append(f"{spof_count} single point{'s' if spof_count != 1 else ''} of failure identified")
        if ai_report.top_risks:
            for risk in ai_report.top_risks[:3]:
                key_findings.append(risk)

        # Calculate financial risk
        annual_risk = self._estimate_annual_risk(graph, sim_report)
        financial_risk = f"${annual_risk:,.0f}"

        # Build executive summary text
        executive_summary = ai_report.summary

        # Build compliance status dict
        compliance_status = {}
        for fw_name, snapshot in self._compliance_snapshots.items():
            compliance_status[fw_name] = snapshot["percentage"]

        now = datetime.now(timezone.utc)
        self._report = ExecutiveReport(
            title="Infrastructure Resilience Assessment",
            company_name=company_name,
            assessment_date=now,
            prepared_by=prepared_by,
            executive_summary=executive_summary,
            resilience_grade=grade,
            resilience_score=resilience_score,
            financial_risk=financial_risk,
            key_findings=key_findings,
            recommendation_count=len(ai_report.recommendations),
            compliance_status=compliance_status,
        )

        # Build all sections
        sections_html = []
        sections_html.append(self._build_cover_page())
        sections_html.append(self._build_executive_summary())
        sections_html.append(self._build_risk_overview())
        sections_html.append(self._build_financial_impact())
        sections_html.append(self._build_compliance_section())
        sections_html.append(self._build_recommendations())
        sections_html.append(self._build_effort_impact_matrix())
        sections_html.append(self._build_trend_section())
        sections_html.append(self._build_appendix())

        body_content = "\n".join(sections_html)

        return self._wrap_html(body_content)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _count_spofs(self, graph: InfraGraph) -> int:
        """Count single points of failure."""
        count = 0
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                count += 1
        return count

    def _estimate_annual_risk(self, graph: InfraGraph, sim_report: SimulationReport) -> float:
        """Estimate annual financial risk from simulation results."""
        # Base cost calculation from component cost profiles
        total_revenue_per_minute = sum(
            c.cost_profile.revenue_per_minute for c in graph.components.values()
        )
        if total_revenue_per_minute == 0:
            total_revenue_per_minute = 100.0  # Default assumption

        # Estimate downtime hours from critical findings
        critical_count = len(sim_report.critical_findings)
        warning_count = len(sim_report.warnings)

        # Assume each critical finding = ~4h downtime/year, warning = ~1h
        estimated_downtime_hours = critical_count * 4.0 + warning_count * 1.0
        annual_risk = estimated_downtime_hours * total_revenue_per_minute * 60.0

        return round(annual_risk, 2)

    def _assess_compliance(self, graph: InfraGraph) -> dict:
        """Run a basic compliance assessment for the report."""
        try:
            from faultray.simulator.compliance_monitor import ComplianceMonitor
            monitor = ComplianceMonitor()
            snapshots = monitor.assess_all(graph)
            result = {}
            for fw, snapshot in snapshots.items():
                result[fw.value] = {
                    "percentage": snapshot.compliance_percentage,
                    "compliant": snapshot.compliant,
                    "partial": snapshot.partial,
                    "non_compliant": snapshot.non_compliant,
                    "total": snapshot.total_controls,
                }
            return result
        except Exception:
            # Fallback to basic compliance engine
            try:
                from faultray.simulator.compliance_engine import ComplianceEngine
                engine = ComplianceEngine(graph)
                reports = engine.check_all()
                result = {}
                for fw_name, report in reports.items():
                    result[fw_name] = {
                        "percentage": report.compliance_percent,
                        "compliant": report.passed,
                        "partial": report.partial,
                        "non_compliant": report.failed,
                        "total": report.total_checks,
                    }
                return result
            except Exception:
                return {}

    def _sla_achievement(self) -> float:
        """Calculate SLA achievement percentage."""
        if not self._sim_report:
            return 100.0
        total = len(self._sim_report.results)
        if total == 0:
            return 100.0
        passed = len(self._sim_report.passed)
        return round(passed / total * 100.0, 2)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_cover_page(self) -> str:
        """Build the cover page HTML."""
        r = self._report
        grade_color = _grade_color(r.resilience_grade)
        date_str = r.assessment_date.strftime("%B %d, %Y")

        return f"""
<div class="page cover-page">
  <div class="cover-content">
    <div class="cover-logo">[LOGO]</div>
    <h1 class="cover-company">{_esc(r.company_name)}</h1>
    <h2 class="cover-title">{_esc(r.title)}</h2>
    <div class="cover-date">{_esc(date_str)}</div>
    <div class="cover-grade-container">
      <div class="cover-grade" style="background-color: {grade_color};">{_esc(r.resilience_grade)}</div>
      <div class="cover-grade-label">Resilience Grade</div>
    </div>
    <div class="cover-prepared">Prepared by: {_esc(r.prepared_by)}</div>
    <div class="cover-confidential">CONFIDENTIAL - For authorized recipients only</div>
  </div>
</div>"""

    def _build_executive_summary(self) -> str:
        """Build the executive summary page."""
        r = self._report
        grade_color = _grade_color(r.resilience_grade)

        # Traffic light grid
        areas = [
            ("Redundancy", self._sim_report.resilience_score if self._sim_report else 0),
            ("Security", self._calculate_security_score()),
            ("Availability", self._sla_achievement()),
            ("Compliance", self._avg_compliance()),
        ]
        traffic_grid = ""
        for label, score in areas:
            css_class = _traffic_light_class(score)
            tl_label = _traffic_light_label(score)
            traffic_grid += f"""
      <div class="traffic-card {css_class}">
        <div class="traffic-dot"></div>
        <div class="traffic-label">{_esc(label)}</div>
        <div class="traffic-status">{_esc(tl_label)}</div>
        <div class="traffic-score">{score:.0f}%</div>
      </div>"""

        # Key findings list
        findings_html = ""
        for finding in r.key_findings[:5]:
            findings_html += f"<li>{_esc(finding)}</li>\n"

        self._estimate_annual_risk(self._graph, self._sim_report) if self._graph and self._sim_report else 0
        sla_pct = self._sla_achievement()

        return f"""
<div class="page">
  <h2 class="section-title">Executive Summary</h2>

  <div class="summary-text">{_esc(r.executive_summary)}</div>

  <div class="traffic-grid">
    {traffic_grid}
  </div>

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-value" style="color: {grade_color};">{r.resilience_score:.0f}</div>
      <div class="kpi-label">Resilience Score</div>
      <div class="kpi-sublabel">out of 100</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">{_esc(r.financial_risk)}</div>
      <div class="kpi-label">Est. Annual Risk</div>
      <div class="kpi-sublabel">downtime cost</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">{len(self._sim_report.critical_findings) if self._sim_report else 0}</div>
      <div class="kpi-label">Critical Findings</div>
      <div class="kpi-sublabel">requiring action</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-value">{sla_pct:.1f}%</div>
      <div class="kpi-label">SLA Achievement</div>
      <div class="kpi-sublabel">scenarios passed</div>
    </div>
  </div>

  <h3>Key Findings</h3>
  <ul class="findings-list">
    {findings_html}
  </ul>
</div>"""

    def _build_risk_overview(self) -> str:
        """Build the risk overview page with CSS-only bar chart."""
        if not self._graph or not self._sim_report:
            return '<div class="page"><h2 class="section-title">Risk Overview</h2><p>No data available.</p></div>'

        # Build CSS-only bar chart for risk per component
        risk_bars = ""
        components_data = []
        for comp in self._graph.components.values():
            dependents = self._graph.get_dependents(comp.id)
            util = comp.utilization()
            is_spof = comp.replicas <= 1 and len(dependents) > 0

            risk_val = 0.0
            if is_spof:
                risk_val = 70.0 + min(30.0, util * 0.3)
            elif util > 80:
                risk_val = 50.0 + (util - 80) * 2.0
            elif util > 60:
                risk_val = 30.0 + (util - 60)
            elif len(dependents) > 0 and comp.replicas < 3:
                risk_val = 20.0
            else:
                risk_val = 10.0
            risk_val = min(100.0, risk_val)
            components_data.append((comp.name, risk_val, comp.type.value, is_spof))

        components_data.sort(key=lambda x: x[1], reverse=True)

        for name, risk, ctype, is_spof in components_data[:10]:
            bar_color = "#dc3545" if risk >= 70 else "#fd7e14" if risk >= 40 else "#ffc107" if risk >= 20 else "#28a745"
            spof_tag = ' <span class="spof-badge">SPOF</span>' if is_spof else ""
            risk_bars += f"""
      <div class="risk-bar-row">
        <div class="risk-bar-label">{_esc(name)}{spof_tag}</div>
        <div class="risk-bar-track">
          <div class="risk-bar-fill" style="width: {risk:.0f}%; background: {bar_color};"></div>
        </div>
        <div class="risk-bar-value">{risk:.0f}%</div>
      </div>"""

        # Top 5 risks list
        top_risks_html = ""
        if self._ai_report and self._ai_report.top_risks:
            for i, risk in enumerate(self._ai_report.top_risks[:5], 1):
                top_risks_html += f"""
      <div class="top-risk-item">
        <span class="top-risk-num">{i}</span>
        <span class="top-risk-text">{_esc(risk)}</span>
      </div>"""

        spof_count = self._count_spofs(self._graph)

        return f"""
<div class="page">
  <h2 class="section-title">Risk Overview</h2>

  <div class="risk-summary-grid">
    <div class="risk-summary-card risk-card-critical">
      <div class="risk-summary-value">{len(self._sim_report.critical_findings)}</div>
      <div class="risk-summary-label">Critical</div>
    </div>
    <div class="risk-summary-card risk-card-warning">
      <div class="risk-summary-value">{len(self._sim_report.warnings)}</div>
      <div class="risk-summary-label">Warnings</div>
    </div>
    <div class="risk-summary-card risk-card-passed">
      <div class="risk-summary-value">{len(self._sim_report.passed)}</div>
      <div class="risk-summary-label">Passed</div>
    </div>
    <div class="risk-summary-card risk-card-spof">
      <div class="risk-summary-value">{spof_count}</div>
      <div class="risk-summary-label">SPOFs</div>
    </div>
  </div>

  <h3>Risk by Component</h3>
  <div class="risk-chart">
    {risk_bars}
  </div>

  <h3>Top Risks</h3>
  <div class="top-risks">
    {top_risks_html if top_risks_html else '<p class="no-data">No significant risks identified.</p>'}
  </div>
</div>"""

    def _build_financial_impact(self) -> str:
        """Build the financial impact analysis page."""
        if not self._graph or not self._sim_report:
            return '<div class="page"><h2 class="section-title">Financial Impact</h2><p>No data available.</p></div>'

        total_revenue_per_minute = sum(
            c.cost_profile.revenue_per_minute for c in self._graph.components.values()
        )
        if total_revenue_per_minute == 0:
            total_revenue_per_minute = 100.0

        cost_per_hour = total_revenue_per_minute * 60.0
        annual_risk = self._estimate_annual_risk(self._graph, self._sim_report)

        # Calculate improvement cost estimate
        spof_count = self._count_spofs(self._graph)
        improvement_cost = 0.0
        for comp in self._graph.components.values():
            if comp.replicas <= 1 and len(self._graph.get_dependents(comp.id)) > 0:
                improvement_cost += comp.cost_profile.hourly_infra_cost * 730 * 12  # annual cost of extra replica

        roi = ((annual_risk - improvement_cost) / improvement_cost * 100) if improvement_cost > 0 else 0

        return f"""
<div class="page">
  <h2 class="section-title">Financial Impact Analysis</h2>

  <div class="financial-grid">
    <div class="financial-card">
      <div class="financial-icon">&#9202;</div>
      <div class="financial-value">${cost_per_hour:,.0f}</div>
      <div class="financial-label">Cost of Downtime</div>
      <div class="financial-sublabel">per hour</div>
    </div>
    <div class="financial-card">
      <div class="financial-icon">&#9888;</div>
      <div class="financial-value">${annual_risk:,.0f}</div>
      <div class="financial-label">Annual Downtime Risk</div>
      <div class="financial-sublabel">estimated cost</div>
    </div>
    <div class="financial-card">
      <div class="financial-icon">&#128736;</div>
      <div class="financial-value">${improvement_cost:,.0f}</div>
      <div class="financial-label">Improvement Cost</div>
      <div class="financial-sublabel">to fix {spof_count} SPOFs</div>
    </div>
    <div class="financial-card">
      <div class="financial-icon">&#128200;</div>
      <div class="financial-value">{roi:+.0f}%</div>
      <div class="financial-label">ROI</div>
      <div class="financial-sublabel">on improvements</div>
    </div>
  </div>

  <h3>Downtime Cost Breakdown</h3>
  <table class="data-table">
    <thead>
      <tr>
        <th>Metric</th>
        <th>Value</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>Revenue per minute at risk</td><td>${total_revenue_per_minute:,.2f}</td></tr>
      <tr><td>Hourly cost of downtime</td><td>${cost_per_hour:,.0f}</td></tr>
      <tr><td>Critical vulnerabilities</td><td>{len(self._sim_report.critical_findings)}</td></tr>
      <tr><td>Estimated annual downtime hours</td><td>{annual_risk / cost_per_hour:.1f}h</td></tr>
      <tr><td>Estimated annual risk</td><td>${annual_risk:,.0f}</td></tr>
      <tr><td>Cost to remediate SPOFs</td><td>${improvement_cost:,.0f}</td></tr>
      <tr><td>Net benefit of improvements</td><td>${max(0, annual_risk - improvement_cost):,.0f}</td></tr>
    </tbody>
  </table>
</div>"""

    def _build_compliance_section(self) -> str:
        """Build the compliance status page with CSS-only progress bars."""
        if not self._compliance_snapshots:
            return '<div class="page"><h2 class="section-title">Compliance Status</h2><p>No compliance data available.</p></div>'

        progress_bars = ""
        gaps_html = ""
        avg_readiness = 0.0
        count = 0

        framework_labels = {
            "dora": "DORA",
            "soc2": "SOC 2",
            "iso27001": "ISO 27001",
            "pci_dss": "PCI DSS",
            "nist_csf": "NIST CSF",
            "hipaa": "HIPAA",
        }

        for fw_name, data in sorted(self._compliance_snapshots.items()):
            pct = data["percentage"]
            avg_readiness += pct
            count += 1
            bar_color = "#28a745" if pct >= 80 else "#ffc107" if pct >= 50 else "#dc3545"
            display_name = framework_labels.get(fw_name, fw_name.upper())

            progress_bars += f"""
      <div class="compliance-bar-row">
        <div class="compliance-fw-name">{_esc(display_name)}</div>
        <div class="compliance-bar-track">
          <div class="compliance-bar-fill" style="width: {pct:.0f}%; background: {bar_color};"></div>
        </div>
        <div class="compliance-bar-pct">{pct:.0f}%</div>
      </div>"""

            # Key gaps per framework
            nc = data.get("non_compliant", 0)
            if nc > 0:
                gaps_html += f"""
      <div class="compliance-gap">
        <strong>{_esc(display_name)}</strong>: {nc} non-compliant control{'s' if nc != 1 else ''}
      </div>"""

        avg_readiness = avg_readiness / count if count > 0 else 0

        return f"""
<div class="page">
  <h2 class="section-title">Compliance Status</h2>

  <div class="audit-readiness">
    <div class="audit-readiness-value">{avg_readiness:.0f}%</div>
    <div class="audit-readiness-label">Average Audit Readiness</div>
  </div>

  <h3>Framework Compliance</h3>
  <div class="compliance-bars">
    {progress_bars}
  </div>

  <h3>Key Gaps</h3>
  <div class="compliance-gaps">
    {gaps_html if gaps_html else '<p class="no-data">No critical compliance gaps detected.</p>'}
  </div>
</div>"""

    def _build_recommendations(self) -> str:
        """Build the recommendations page."""
        if not self._ai_report or not self._ai_report.recommendations:
            return '<div class="page"><h2 class="section-title">Recommendations</h2><p>No recommendations at this time.</p></div>'

        recs_html = ""
        for i, rec in enumerate(self._ai_report.recommendations, 1):
            sev_color = {
                "critical": "#dc3545",
                "high": "#fd7e14",
                "medium": "#ffc107",
                "low": "#28a745",
            }.get(rec.severity, "#6c757d")

            recs_html += f"""
      <div class="rec-item">
        <div class="rec-header">
          <span class="rec-number">{i}</span>
          <span class="rec-severity" style="background: {sev_color};">{_esc(rec.severity.upper())}</span>
          <span class="rec-title">{_esc(rec.title)}</span>
          <span class="rec-effort">Effort: {_esc(rec.effort)}</span>
        </div>
        <div class="rec-body">
          <p class="rec-desc">{_esc(rec.description)}</p>
          <p class="rec-action"><strong>Action:</strong> {_esc(rec.remediation)}</p>
          <p class="rec-impact"><strong>Impact:</strong> {_esc(rec.estimated_impact)}</p>
        </div>
      </div>"""

        return f"""
<div class="page">
  <h2 class="section-title">Recommendations</h2>
  <p class="section-subtitle">{len(self._ai_report.recommendations)} recommendations prioritized by severity and impact.</p>
  <div class="recommendations-list">
    {recs_html}
  </div>
</div>"""

    def _build_effort_impact_matrix(self) -> str:
        """Build the effort/impact 2x2 matrix."""
        if not self._ai_report or not self._ai_report.recommendations:
            return ""

        # Categorize recommendations into quadrants
        quick_wins: list[str] = []
        strategic: list[str] = []
        nice_to_have: list[str] = []
        reconsider: list[str] = []

        for rec in self._ai_report.recommendations:
            is_high_impact = rec.severity in ("critical", "high")
            is_low_effort = rec.effort in ("low",)

            if is_low_effort and is_high_impact:
                quick_wins.append(rec.title)
            elif not is_low_effort and is_high_impact:
                strategic.append(rec.title)
            elif is_low_effort and not is_high_impact:
                nice_to_have.append(rec.title)
            else:
                reconsider.append(rec.title)

        def _list_items(items: list[str], max_items: int = 4) -> str:
            if not items:
                return "<em>None</em>"
            html_items = ""
            for item in items[:max_items]:
                html_items += f"<li>{_esc(item)}</li>"
            if len(items) > max_items:
                html_items += f"<li><em>+{len(items) - max_items} more</em></li>"
            return f"<ul>{html_items}</ul>"

        return f"""
<div class="page">
  <h2 class="section-title">Effort / Impact Matrix</h2>
  <p class="section-subtitle">Prioritize improvements by effort required and expected impact.</p>

  <div class="matrix-container">
    <div class="matrix-y-label">IMPACT</div>
    <div class="matrix-grid">
      <div class="matrix-cell matrix-quick-wins">
        <div class="matrix-cell-title">Quick Wins</div>
        <div class="matrix-cell-subtitle">Do These First</div>
        {_list_items(quick_wins)}
      </div>
      <div class="matrix-cell matrix-strategic">
        <div class="matrix-cell-title">Strategic</div>
        <div class="matrix-cell-subtitle">Plan & Execute</div>
        {_list_items(strategic)}
      </div>
      <div class="matrix-cell matrix-nice">
        <div class="matrix-cell-title">Nice to Have</div>
        <div class="matrix-cell-subtitle">When Resources Allow</div>
        {_list_items(nice_to_have)}
      </div>
      <div class="matrix-cell matrix-reconsider">
        <div class="matrix-cell-title">Reconsider</div>
        <div class="matrix-cell-subtitle">Low Priority</div>
        {_list_items(reconsider)}
      </div>
    </div>
    <div class="matrix-x-label">EFFORT</div>
  </div>
</div>"""

    def _build_trend_section(self) -> str:
        """Build the trend section with CSS-only mini charts."""
        if not self._sim_report:
            return ""

        # Build a simple CSS-only trend visualization
        nines = self._ai_report.estimated_current_nines if self._ai_report else 2.0
        max_nines = self._ai_report.theoretical_max_nines if self._ai_report else 4.0

        upgrade_path = self._ai_report.upgrade_path if self._ai_report else ""

        return f"""
<div class="page">
  <h2 class="section-title">Resilience Trend & Outlook</h2>

  <div class="trend-grid">
    <div class="trend-card">
      <h4>Current Availability</h4>
      <div class="trend-big-number">{nines:.1f}</div>
      <div class="trend-unit">nines</div>
      <div class="trend-bar-container">
        <div class="trend-bar" style="width: {min(100, nines / 5.0 * 100):.0f}%; background: #1a73e8;"></div>
      </div>
      <div class="trend-scale">0 nines &mdash; 5 nines</div>
    </div>
    <div class="trend-card">
      <h4>Achievable Availability</h4>
      <div class="trend-big-number">{max_nines:.1f}</div>
      <div class="trend-unit">nines (with improvements)</div>
      <div class="trend-bar-container">
        <div class="trend-bar" style="width: {min(100, max_nines / 5.0 * 100):.0f}%; background: #28a745;"></div>
      </div>
      <div class="trend-scale">0 nines &mdash; 5 nines</div>
    </div>
  </div>

  <div class="upgrade-path-box">
    <h4>Upgrade Path</h4>
    <p>{_esc(upgrade_path)}</p>
  </div>
</div>"""

    def _build_appendix(self) -> str:
        """Build the technical appendix."""
        if not self._graph or not self._sim_report:
            return ""

        # Component inventory table
        comp_rows = ""
        for comp in self._graph.components.values():
            dependents = self._graph.get_dependents(comp.id)
            self._graph.get_dependencies(comp.id)
            health_color = {
                HealthStatus.HEALTHY: "#28a745",
                HealthStatus.DEGRADED: "#ffc107",
                HealthStatus.OVERLOADED: "#fd7e14",
                HealthStatus.DOWN: "#dc3545",
            }.get(comp.health, "#6c757d")

            comp_rows += f"""
        <tr>
          <td>{_esc(comp.name)}</td>
          <td>{_esc(comp.type.value)}</td>
          <td>{comp.replicas}</td>
          <td>{comp.utilization():.0f}%</td>
          <td style="color: {health_color}; font-weight: bold;">{_esc(comp.health.value)}</td>
          <td>{len(dependents)}</td>
          <td>{"Yes" if comp.failover.enabled else "No"}</td>
          <td>{"Yes" if comp.autoscaling.enabled else "No"}</td>
        </tr>"""

        # Scenario results table
        scenario_rows = ""
        for result in self._sim_report.results[:20]:
            color = "#dc3545" if result.is_critical else "#ffc107" if result.is_warning else "#28a745"
            label = "CRITICAL" if result.is_critical else "WARNING" if result.is_warning else "PASSED"
            affected = len(result.cascade.effects)
            scenario_rows += f"""
        <tr>
          <td>{_esc(result.scenario.name[:40])}</td>
          <td style="color: {color}; font-weight: bold;">{label}</td>
          <td>{result.risk_score:.1f}</td>
          <td>{affected}</td>
        </tr>"""

        return f"""
<div class="page">
  <h2 class="section-title">Appendix: Technical Details</h2>

  <h3>Component Inventory</h3>
  <table class="data-table data-table-sm">
    <thead>
      <tr>
        <th>Component</th><th>Type</th><th>Replicas</th><th>Util.</th>
        <th>Health</th><th>Dependents</th><th>Failover</th><th>Autoscale</th>
      </tr>
    </thead>
    <tbody>{comp_rows}</tbody>
  </table>

  <h3>Scenario Results (Top {min(20, len(self._sim_report.results))})</h3>
  <table class="data-table data-table-sm">
    <thead>
      <tr>
        <th>Scenario</th><th>Status</th><th>Risk Score</th><th>Affected</th>
      </tr>
    </thead>
    <tbody>{scenario_rows}</tbody>
  </table>

  <div class="appendix-footer">
    <p>Generated by FaultRay AI Analysis Engine | {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
    <p>Total scenarios tested: {len(self._sim_report.results)} | Resilience score: {self._sim_report.resilience_score:.1f}/100</p>
  </div>
</div>"""

    # ------------------------------------------------------------------
    # Helpers for score calculation
    # ------------------------------------------------------------------

    def _calculate_security_score(self) -> float:
        """Calculate a security score 0-100."""
        if not self._graph or not self._graph.components:
            return 0.0
        total = 0.0
        for comp in self._graph.components.values():
            sec = comp.security
            s = 0.0
            if sec.encryption_at_rest:
                s += 15
            if sec.encryption_in_transit:
                s += 15
            if sec.waf_protected:
                s += 10
            if sec.rate_limiting:
                s += 10
            if sec.auth_required:
                s += 15
            if sec.network_segmented:
                s += 10
            if sec.backup_enabled:
                s += 10
            if sec.log_enabled:
                s += 10
            if sec.ids_monitored:
                s += 5
            total += s
        return total / len(self._graph.components)

    def _avg_compliance(self) -> float:
        """Return average compliance percentage across all frameworks."""
        if not self._compliance_snapshots:
            return 0.0
        pcts = [d["percentage"] for d in self._compliance_snapshots.values()]
        return sum(pcts) / len(pcts) if pcts else 0.0

    # ------------------------------------------------------------------
    # HTML wrapper with CSS
    # ------------------------------------------------------------------

    def _wrap_html(self, body_content: str) -> str:
        """Wrap body content with HTML head, CSS styles, and structure."""
        r = self._report
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(r.title)} - {_esc(r.company_name)}</title>
  <style>
    /* Reset & Base */
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, 'Helvetica Neue', Arial, sans-serif;
      line-height: 1.5;
      color: #2c3e50;
      background: #ffffff;
      font-size: 11pt;
    }}

    /* Print styles */
    @media print {{
      body {{ background: white; }}
      .page {{ page-break-after: always; break-after: page; }}
      .page:last-child {{ page-break-after: avoid; break-after: avoid; }}
      @page {{
        size: A4;
        margin: 15mm 20mm;
        @top-right {{ content: "{_esc(r.company_name)} - Confidential"; font-size: 8pt; color: #999; }}
        @bottom-center {{ content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #999; }}
      }}
    }}

    /* Screen styles */
    @media screen {{
      body {{ background: #e8e8e8; }}
      .page {{
        max-width: 210mm;
        min-height: 297mm;
        margin: 20px auto;
        padding: 30px 40px;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      }}
    }}

    /* Page */
    .page {{ padding: 30px 40px; position: relative; }}

    /* Cover Page */
    .cover-page {{
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      background: linear-gradient(135deg, #1a237e 0%, #283593 50%, #1565c0 100%);
      color: white;
    }}
    .cover-content {{ padding: 60px 40px; }}
    .cover-logo {{ font-size: 14pt; color: rgba(255,255,255,0.7); margin-bottom: 40px; letter-spacing: 2px; }}
    .cover-company {{ font-size: 28pt; font-weight: 700; margin-bottom: 12px; letter-spacing: 1px; }}
    .cover-title {{ font-size: 16pt; font-weight: 300; margin-bottom: 30px; opacity: 0.9; }}
    .cover-date {{ font-size: 12pt; margin-bottom: 40px; opacity: 0.8; }}
    .cover-grade-container {{ margin: 30px 0; }}
    .cover-grade {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 100px;
      height: 100px;
      border-radius: 50%;
      font-size: 32pt;
      font-weight: 700;
      color: white;
      margin-bottom: 10px;
    }}
    .cover-grade-label {{ font-size: 11pt; opacity: 0.8; }}
    .cover-prepared {{ font-size: 10pt; margin-top: 40px; opacity: 0.7; }}
    .cover-confidential {{
      font-size: 9pt;
      margin-top: 40px;
      padding: 8px 20px;
      border: 1px solid rgba(255,255,255,0.3);
      border-radius: 4px;
      letter-spacing: 1px;
      text-transform: uppercase;
      opacity: 0.6;
    }}

    /* Section titles */
    .section-title {{
      font-size: 16pt;
      color: #1a237e;
      border-bottom: 3px solid #1a237e;
      padding-bottom: 8px;
      margin-bottom: 20px;
    }}
    .section-subtitle {{ color: #666; font-size: 10pt; margin-bottom: 16px; }}
    h3 {{ font-size: 12pt; color: #333; margin: 20px 0 10px; }}
    h4 {{ font-size: 11pt; color: #1a237e; margin-bottom: 8px; }}

    /* Summary text */
    .summary-text {{
      background: #f0f4ff;
      border-left: 4px solid #1a237e;
      padding: 14px 18px;
      margin-bottom: 20px;
      font-size: 10pt;
      border-radius: 0 4px 4px 0;
    }}

    /* Traffic light grid */
    .traffic-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }}
    .traffic-card {{
      text-align: center;
      padding: 14px 10px;
      border-radius: 6px;
      border: 1px solid #e0e0e0;
    }}
    .traffic-dot {{
      width: 20px;
      height: 20px;
      border-radius: 50%;
      margin: 0 auto 8px;
    }}
    .status-green .traffic-dot {{ background: #28a745; }}
    .status-yellow .traffic-dot {{ background: #ffc107; }}
    .status-red .traffic-dot {{ background: #dc3545; }}
    .status-green {{ border-color: #28a745; }}
    .status-yellow {{ border-color: #ffc107; }}
    .status-red {{ border-color: #dc3545; }}
    .traffic-label {{ font-size: 9pt; color: #666; }}
    .traffic-status {{ font-size: 10pt; font-weight: 600; }}
    .status-green .traffic-status {{ color: #28a745; }}
    .status-yellow .traffic-status {{ color: #b8860b; }}
    .status-red .traffic-status {{ color: #dc3545; }}
    .traffic-score {{ font-size: 9pt; color: #999; margin-top: 2px; }}

    /* KPI grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }}
    .kpi-card {{
      text-align: center;
      padding: 16px 8px;
      background: #f8f9fa;
      border-radius: 6px;
    }}
    .kpi-value {{ font-size: 22pt; font-weight: 700; color: #1a237e; }}
    .kpi-label {{ font-size: 9pt; color: #555; margin-top: 4px; }}
    .kpi-sublabel {{ font-size: 8pt; color: #999; }}

    /* Findings list */
    .findings-list {{ padding-left: 20px; }}
    .findings-list li {{ margin-bottom: 6px; font-size: 10pt; }}

    /* Risk overview */
    .risk-summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }}
    .risk-summary-card {{
      text-align: center;
      padding: 16px;
      border-radius: 6px;
      color: white;
    }}
    .risk-card-critical {{ background: #dc3545; }}
    .risk-card-warning {{ background: #fd7e14; }}
    .risk-card-passed {{ background: #28a745; }}
    .risk-card-spof {{ background: #6f42c1; }}
    .risk-summary-value {{ font-size: 24pt; font-weight: 700; }}
    .risk-summary-label {{ font-size: 9pt; opacity: 0.9; }}

    /* Risk bar chart */
    .risk-chart {{ margin: 10px 0; }}
    .risk-bar-row {{
      display: flex;
      align-items: center;
      margin-bottom: 6px;
    }}
    .risk-bar-label {{
      width: 160px;
      font-size: 9pt;
      text-align: right;
      padding-right: 10px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .risk-bar-track {{
      flex: 1;
      height: 16px;
      background: #f0f0f0;
      border-radius: 3px;
      overflow: hidden;
    }}
    .risk-bar-fill {{
      height: 100%;
      border-radius: 3px;
      transition: width 0.3s;
    }}
    .risk-bar-value {{
      width: 40px;
      text-align: right;
      font-size: 9pt;
      color: #666;
      padding-left: 8px;
    }}
    .spof-badge {{
      background: #dc3545;
      color: white;
      font-size: 7pt;
      padding: 1px 4px;
      border-radius: 2px;
      margin-left: 4px;
      vertical-align: middle;
    }}

    /* Top risks */
    .top-risk-item {{
      display: flex;
      align-items: flex-start;
      padding: 8px 0;
      border-bottom: 1px solid #eee;
    }}
    .top-risk-num {{
      background: #dc3545;
      color: white;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 9pt;
      font-weight: 700;
      margin-right: 10px;
      flex-shrink: 0;
    }}
    .top-risk-text {{ font-size: 10pt; }}

    /* Financial grid */
    .financial-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 20px;
    }}
    .financial-card {{
      text-align: center;
      padding: 18px 10px;
      background: #f8f9fa;
      border-radius: 6px;
      border: 1px solid #e0e0e0;
    }}
    .financial-icon {{ font-size: 18pt; margin-bottom: 6px; }}
    .financial-value {{ font-size: 16pt; font-weight: 700; color: #1a237e; }}
    .financial-label {{ font-size: 9pt; color: #555; margin-top: 4px; }}
    .financial-sublabel {{ font-size: 8pt; color: #999; }}

    /* Data tables */
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      margin: 10px 0;
      font-size: 9pt;
    }}
    .data-table th, .data-table td {{
      padding: 7px 10px;
      text-align: left;
      border-bottom: 1px solid #e0e0e0;
    }}
    .data-table th {{
      background: #f5f5f5;
      font-weight: 600;
      color: #555;
      font-size: 8pt;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .data-table-sm {{ font-size: 8pt; }}
    .data-table-sm th, .data-table-sm td {{ padding: 4px 8px; }}

    /* Compliance bars */
    .compliance-bars {{ margin: 10px 0; }}
    .compliance-bar-row {{
      display: flex;
      align-items: center;
      margin-bottom: 8px;
    }}
    .compliance-fw-name {{
      width: 100px;
      font-size: 9pt;
      font-weight: 600;
      text-align: right;
      padding-right: 12px;
    }}
    .compliance-bar-track {{
      flex: 1;
      height: 20px;
      background: #f0f0f0;
      border-radius: 4px;
      overflow: hidden;
    }}
    .compliance-bar-fill {{
      height: 100%;
      border-radius: 4px;
    }}
    .compliance-bar-pct {{
      width: 45px;
      text-align: right;
      font-size: 10pt;
      font-weight: 700;
      padding-left: 10px;
    }}
    .compliance-gap {{
      padding: 6px 12px;
      background: #fff3cd;
      border-left: 3px solid #ffc107;
      margin-bottom: 6px;
      font-size: 9pt;
      border-radius: 0 4px 4px 0;
    }}
    .audit-readiness {{
      text-align: center;
      margin-bottom: 20px;
    }}
    .audit-readiness-value {{
      font-size: 36pt;
      font-weight: 700;
      color: #1a237e;
    }}
    .audit-readiness-label {{
      font-size: 10pt;
      color: #666;
    }}

    /* Recommendations */
    .recommendations-list {{ margin: 10px 0; }}
    .rec-item {{
      border: 1px solid #e0e0e0;
      border-radius: 6px;
      margin-bottom: 10px;
      overflow: hidden;
    }}
    .rec-header {{
      display: flex;
      align-items: center;
      padding: 8px 12px;
      background: #f8f9fa;
      gap: 8px;
    }}
    .rec-number {{
      background: #1a237e;
      color: white;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 9pt;
      font-weight: 700;
      flex-shrink: 0;
    }}
    .rec-severity {{
      color: white;
      padding: 2px 8px;
      border-radius: 3px;
      font-size: 8pt;
      font-weight: 700;
    }}
    .rec-title {{ font-size: 10pt; font-weight: 600; flex: 1; }}
    .rec-effort {{ font-size: 8pt; color: #666; }}
    .rec-body {{ padding: 10px 12px; font-size: 9pt; }}
    .rec-desc {{ margin-bottom: 6px; color: #555; }}
    .rec-action {{ margin-bottom: 4px; }}
    .rec-impact {{ color: #1a237e; }}

    /* Effort/Impact Matrix */
    .matrix-container {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
    }}
    .matrix-y-label {{
      writing-mode: vertical-lr;
      transform: rotate(180deg);
      font-size: 9pt;
      font-weight: 700;
      color: #666;
      letter-spacing: 2px;
    }}
    .matrix-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-rows: 1fr 1fr;
      gap: 8px;
      width: 100%;
      max-width: 500px;
    }}
    .matrix-cell {{
      padding: 14px;
      border-radius: 6px;
      min-height: 120px;
    }}
    .matrix-cell ul {{ padding-left: 16px; margin-top: 6px; font-size: 8pt; }}
    .matrix-cell li {{ margin-bottom: 3px; }}
    .matrix-cell-title {{ font-size: 10pt; font-weight: 700; }}
    .matrix-cell-subtitle {{ font-size: 8pt; color: rgba(0,0,0,0.5); margin-bottom: 4px; }}
    .matrix-quick-wins {{ background: #d4edda; border: 2px solid #28a745; }}
    .matrix-strategic {{ background: #cce5ff; border: 2px solid #1a73e8; }}
    .matrix-nice {{ background: #f8f9fa; border: 1px solid #dee2e6; }}
    .matrix-reconsider {{ background: #fff3cd; border: 1px solid #ffc107; }}
    .matrix-x-label {{
      text-align: center;
      font-size: 9pt;
      font-weight: 700;
      color: #666;
      letter-spacing: 2px;
      margin-top: 6px;
    }}

    /* Trend section */
    .trend-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 20px;
    }}
    .trend-card {{
      padding: 20px;
      background: #f8f9fa;
      border-radius: 6px;
      text-align: center;
    }}
    .trend-big-number {{ font-size: 36pt; font-weight: 700; color: #1a237e; }}
    .trend-unit {{ font-size: 10pt; color: #666; margin-bottom: 12px; }}
    .trend-bar-container {{
      height: 8px;
      background: #e0e0e0;
      border-radius: 4px;
      overflow: hidden;
      margin: 8px 20px;
    }}
    .trend-bar {{ height: 100%; border-radius: 4px; }}
    .trend-scale {{ font-size: 8pt; color: #999; }}
    .upgrade-path-box {{
      background: #e8f5e9;
      border-left: 4px solid #28a745;
      padding: 14px 18px;
      border-radius: 0 4px 4px 0;
      font-size: 10pt;
    }}

    /* Appendix */
    .appendix-footer {{
      margin-top: 30px;
      padding-top: 16px;
      border-top: 1px solid #e0e0e0;
      text-align: center;
      font-size: 9pt;
      color: #999;
    }}

    /* Utilities */
    .no-data {{ color: #28a745; font-weight: 600; font-size: 10pt; }}
  </style>
</head>
<body>
{body_content}
</body>
</html>"""
