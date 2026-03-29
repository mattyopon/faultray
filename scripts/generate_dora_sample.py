#!/usr/bin/env python3
# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Generate a sample DORA compliance report for a fictional financial institution.

Usage:
    python scripts/generate_dora_sample.py

Outputs:
    docs/samples/dora-compliance-report-sample.html
"""

from __future__ import annotations

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "samples", "dora-compliance-report-sample.html")


def _pillar_data():
    return [
        {
            "name": "ICT Risk Management",
            "articles": "Articles 5-16",
            "status": "Partial",
            "score": 62,
            "findings": [
                "Database lacks automated failover — single point of failure (CRITICAL)",
                "No documented recovery procedures for payment gateway",
                "Cache layer has no replication — data loss risk on failure",
            ],
            "evidence": [
                "FaultRay cascade simulation: DB failure cascades to 7/15 components",
                "Availability ceiling: 99.82% (below 99.95% SLA target)",
            ],
            "gaps": [
                "Art. 6(1): ICT risk management framework incomplete — no availability ceiling analysis",
                "Art. 9(2): Backup and recovery — DB failover not tested",
                "Art. 11: Business continuity — cascade paths not documented",
            ],
            "remediation": [
                "Add database replica with automated failover (1 week, $2,400/yr)",
                "Document and test recovery procedures quarterly",
                "Implement Redis replication for cache layer (3 days, $1,200/yr)",
            ],
        },
        {
            "name": "ICT Incident Reporting",
            "articles": "Articles 17-23",
            "status": "Compliant",
            "score": 88,
            "findings": [
                "Incident classification taxonomy aligned with DORA severity levels",
                "Automated alerting via PagerDuty integration",
            ],
            "evidence": [
                "FaultRay incident cost model: mean estimated loss per incident $42K",
                "Alert coverage: 14/15 components monitored",
            ],
            "gaps": [
                "Art. 19(1): Major ICT incident reporting to authorities — process not formalized",
            ],
            "remediation": [
                "Formalize incident reporting template for regulatory authorities (2 days)",
            ],
        },
        {
            "name": "Digital Operational Resilience Testing",
            "articles": "Articles 24-27",
            "status": "Non-Compliant",
            "score": 35,
            "findings": [
                "No regular resilience testing program in place",
                "No threat-led penetration testing (TLPT) performed",
                "Cascade failure scenarios never tested",
            ],
            "evidence": [
                "FaultRay simulation: 2,847 scenarios tested, 23 critical findings",
                "Blast radius: single DB failure affects 47% of infrastructure",
            ],
            "gaps": [
                "Art. 25(1): ICT testing programme — no annual testing schedule",
                "Art. 26(1): Advanced testing via TLPT — never conducted",
                "Art. 25(3): Proportionality — testing scope undefined",
            ],
            "remediation": [
                "Adopt FaultRay for continuous resilience testing (immediate, $0-$5,988/yr)",
                "Schedule annual TLPT with qualified provider ($50K-$150K)",
                "Establish quarterly cascade simulation reviews",
            ],
        },
        {
            "name": "ICT Third-Party Risk",
            "articles": "Articles 28-44",
            "status": "Partial",
            "score": 55,
            "findings": [
                "3 critical third-party dependencies identified",
                "External SLA chain caps availability at 99.9%",
                "No exit strategy for cloud provider dependency",
            ],
            "evidence": [
                "FaultRay 5-layer model: External SLA layer is binding constraint",
                "Third-party cascade: payment processor failure affects 5 downstream services",
            ],
            "gaps": [
                "Art. 28(2): Proportionality in third-party risk — no tiering of providers",
                "Art. 30(3): Exit strategies — not documented for critical providers",
                "Art. 33: Subcontracting — cloud provider subcontracting chain not mapped",
            ],
            "remediation": [
                "Tier third-party providers by criticality (1 week)",
                "Document exit strategies for top 3 providers (2 weeks)",
                "Request subcontracting disclosures from cloud providers",
            ],
        },
        {
            "name": "Information Sharing",
            "articles": "Article 45",
            "status": "Compliant",
            "score": 82,
            "findings": [
                "Threat intelligence feeds integrated (CVE, CISA)",
                "Internal security awareness program active",
            ],
            "evidence": [
                "FaultRay security feed: auto-generates scenarios from advisories",
            ],
            "gaps": [
                "Art. 45(1): Voluntary sharing arrangements — not participating in FS-ISAC or equivalent",
            ],
            "remediation": [
                "Join FS-ISAC or regional financial ISAC (3 months, ~$5K/yr)",
            ],
        },
    ]


def _generate_html():
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    pillars = _pillar_data()

    overall_score = sum(p["score"] for p in pillars) / len(pillars)
    critical_count = sum(1 for p in pillars if p["status"] == "Non-Compliant")
    partial_count = sum(1 for p in pillars if p["status"] == "Partial")
    compliant_count = sum(1 for p in pillars if p["status"] == "Compliant")

    status_color = {"Compliant": "#22c55e", "Partial": "#eab308", "Non-Compliant": "#ef4444"}

    pillar_rows = ""
    for p in pillars:
        color = status_color.get(p["status"], "#94a3b8")
        findings_html = "".join(f"<li>{f}</li>" for f in p["findings"])
        evidence_html = "".join(f"<li>{e}</li>" for e in p["evidence"])
        gaps_html = "".join(f"<li>{g}</li>" for g in p["gaps"])
        remediation_html = "".join(f"<li>{r}</li>" for r in p["remediation"])

        pillar_rows += f"""
        <div class="pillar">
            <div class="pillar-header">
                <div>
                    <h3>{p["name"]}</h3>
                    <span class="articles">{p["articles"]}</span>
                </div>
                <div class="pillar-score">
                    <span class="status" style="background:{color}">{p["status"]}</span>
                    <span class="score">{p["score"]}/100</span>
                </div>
            </div>
            <div class="pillar-body">
                <div class="section">
                    <h4>Key Findings</h4>
                    <ul>{findings_html}</ul>
                </div>
                <div class="section">
                    <h4>Evidence (FaultRay)</h4>
                    <ul class="evidence">{evidence_html}</ul>
                </div>
                <div class="section">
                    <h4>Compliance Gaps</h4>
                    <ul class="gaps">{gaps_html}</ul>
                </div>
                <div class="section">
                    <h4>Remediation Actions</h4>
                    <ul class="remediation">{remediation_html}</ul>
                </div>
            </div>
        </div>
        """

    cascade_scenarios = [
        ("Primary Database Failure", "Core Banking → Payment Gateway → Trading Engine → Customer Portal → AI Fraud Detection", "7/15 components", "$420,000/yr", "CRITICAL"),
        ("Payment Processor Outage", "Payment Gateway → Core Banking (degraded) → Customer Portal (errors)", "5/15 components", "$280,000/yr", "CRITICAL"),
        ("Cache Layer Failure", "Redis → API responses degrade → Trading Engine latency spike → Circuit breaker trips", "4/15 components", "$180,000/yr", "HIGH"),
        ("Load Balancer Single-Instance", "LB failure → Total service outage for all downstream", "12/15 components", "$156,000/yr", "HIGH"),
        ("AI Fraud Detection Grounding Loss", "Vector DB down → Fraud Agent hallucination probability 78% → False approvals", "3/15 components", "$95,000/yr", "HIGH"),
    ]

    cascade_rows = ""
    for scenario, path, blast, loss, severity in cascade_scenarios:
        sev_color = "#ef4444" if severity == "CRITICAL" else "#eab308"
        cascade_rows += f"""
        <tr>
            <td><span class="severity" style="color:{sev_color}">{severity}</span> {scenario}</td>
            <td class="path">{path}</td>
            <td>{blast}</td>
            <td>{loss}</td>
        </tr>"""

    availability_layers = [
        ("Layer 1: Software", "Deploy downtime, human error, config drift", "99.92%", "3.09 nines"),
        ("Layer 2: Hardware", "MTBF/MTTR, redundancy, failover", "99.98%", "3.70 nines"),
        ("Layer 3: Theoretical", "Packet loss, GC pauses, jitter", "99.97%", "3.52 nines"),
        ("Layer 4: Operational", "Incident response, on-call coverage", "99.88%", "2.92 nines"),
        ("Layer 5: External SLA", "Third-party SLA product", "99.90%", "3.00 nines"),
    ]
    avail_rows = ""
    for layer, desc, avail, nines in availability_layers:
        is_binding = layer == "Layer 4: Operational"
        style = "font-weight:700; color:#ef4444;" if is_binding else ""
        binding_tag = " ← BINDING CONSTRAINT" if is_binding else ""
        avail_rows += f'<tr style="{style}"><td>{layer}</td><td>{desc}</td><td>{avail}{binding_tag}</td><td>{nines}</td></tr>'

    fixes = [
        ("1", "Add DB replica + failover", "Database", "$2,400/yr", "$420,000", "175x", "1 week"),
        ("2", "Redis replication", "Cache", "$1,200/yr", "$180,000", "150x", "3 days"),
        ("3", "LB redundancy", "Load Balancer", "$600/yr", "$156,000", "260x", "3 days"),
        ("4", "On-call coverage expansion", "Operations", "$24,000/yr", "$95,000", "4x", "2 weeks"),
        ("5", "Exit strategy documentation", "Governance", "$0", "Risk reduction", "∞", "2 weeks"),
    ]
    fix_rows = ""
    for num, action, comp, cost, savings, roi, timeline in fixes:
        fix_rows += f"<tr><td>{num}</td><td>{action}</td><td>{comp}</td><td>{cost}</td><td>{savings}</td><td>{roi}</td><td>{timeline}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DORA Compliance Assessment Report — FaultRay</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Inter',sans-serif; color:#1e293b; background:#f8fafc; line-height:1.6; }}
.container {{ max-width:900px; margin:0 auto; padding:40px 24px; }}

/* Cover */
.cover {{ text-align:center; padding:80px 40px; background:linear-gradient(135deg,#0f172a,#1e3a5f); color:white; border-radius:12px; margin-bottom:40px; }}
.cover h1 {{ font-size:28px; margin-bottom:8px; }}
.cover .subtitle {{ font-size:16px; color:#93c5fd; margin-bottom:24px; }}
.cover .sample {{ display:inline-block; padding:6px 16px; background:#ef4444; border-radius:4px; font-size:12px; font-weight:600; letter-spacing:1px; margin-bottom:24px; }}
.cover .meta {{ font-size:13px; color:#94a3b8; }}

/* Executive Summary */
.exec-summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:40px; }}
.metric {{ background:white; border-radius:8px; padding:20px; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
.metric .value {{ font-size:32px; font-weight:700; }}
.metric .label {{ font-size:12px; color:#64748b; margin-top:4px; }}
.metric.critical .value {{ color:#ef4444; }}
.metric.warning .value {{ color:#eab308; }}
.metric.good .value {{ color:#22c55e; }}

/* Sections */
h2 {{ font-size:20px; font-weight:700; margin:40px 0 16px; padding-bottom:8px; border-bottom:2px solid #e2e8f0; }}

/* Pillars */
.pillar {{ background:white; border-radius:8px; margin-bottom:16px; box-shadow:0 1px 3px rgba(0,0,0,0.08); overflow:hidden; }}
.pillar-header {{ display:flex; justify-content:space-between; align-items:center; padding:16px 20px; background:#f1f5f9; }}
.pillar-header h3 {{ font-size:16px; margin:0; }}
.articles {{ font-size:12px; color:#64748b; }}
.pillar-score {{ display:flex; align-items:center; gap:12px; }}
.status {{ padding:4px 10px; border-radius:4px; color:white; font-size:12px; font-weight:600; }}
.score {{ font-size:18px; font-weight:700; }}
.pillar-body {{ padding:16px 20px; }}
.section {{ margin-bottom:12px; }}
.section h4 {{ font-size:13px; font-weight:600; color:#475569; margin-bottom:6px; }}
.section ul {{ padding-left:20px; font-size:13px; }}
.section li {{ margin-bottom:4px; }}
.evidence li {{ color:#3b82f6; }}
.gaps li {{ color:#ef4444; }}
.remediation li {{ color:#22c55e; }}

/* Tables */
table {{ width:100%; border-collapse:collapse; font-size:13px; margin-bottom:24px; }}
th {{ background:#f1f5f9; text-align:left; padding:10px 12px; font-weight:600; border-bottom:2px solid #e2e8f0; }}
td {{ padding:10px 12px; border-bottom:1px solid #f1f5f9; }}
.path {{ font-size:11px; color:#64748b; max-width:300px; }}
.severity {{ font-weight:700; }}

/* Binding */
.binding {{ background:#fef2f2; border-left:4px solid #ef4444; padding:12px 16px; border-radius:4px; margin:12px 0; font-size:13px; }}

/* Footer */
.footer {{ text-align:center; padding:40px; color:#94a3b8; font-size:12px; margin-top:40px; border-top:1px solid #e2e8f0; }}
.footer a {{ color:#3b82f6; text-decoration:none; }}

@media print {{
    body {{ background:white; }}
    .container {{ padding:20px; }}
    .cover {{ page-break-after:always; }}
    h2 {{ page-break-before:always; }}
    .pillar {{ break-inside:avoid; }}
}}
</style>
</head>
<body>
<div class="container">

<div class="cover">
    <div class="sample">SAMPLE REPORT</div>
    <h1>DORA Compliance Assessment Report</h1>
    <div class="subtitle">Digital Operational Resilience Act (EU) 2022/2554</div>
    <p style="font-size:18px;margin:16px 0;">Acme Financial Services Ltd.</p>
    <div class="meta">
        Generated by FaultRay v11.0 | {now}<br>
        Classification: CONFIDENTIAL<br>
        Assessment Type: Automated Resilience Simulation (Zero-Risk)
    </div>
</div>

<h2>Executive Summary</h2>
<div class="exec-summary">
    <div class="metric warning">
        <div class="value">{overall_score:.0f}/100</div>
        <div class="label">Overall DORA Score</div>
    </div>
    <div class="metric critical">
        <div class="value">$1.13M</div>
        <div class="label">Est. Annual Risk</div>
    </div>
    <div class="metric">
        <div class="value">99.82%</div>
        <div class="label">Availability Ceiling</div>
    </div>
    <div class="metric critical">
        <div class="value">23</div>
        <div class="label">Critical Findings</div>
    </div>
</div>

<p>This report presents the results of an automated DORA compliance assessment conducted using FaultRay's zero-risk resilience simulation engine. The assessment covers all 5 DORA pillars across 52 controls, using 2,847 simulated failure scenarios against the production infrastructure topology.</p>

<div class="binding">
    <strong>Key Finding:</strong> The operational layer (on-call coverage, incident response) is the binding availability constraint at 99.88%. The stated SLA target of 99.95% is physically unreachable without improving operational processes — no amount of hardware investment will close this gap.
</div>

<h2>DORA Pillar Assessment</h2>
{pillar_rows}

<h2>Cascade Failure Analysis — Top 5 Scenarios</h2>
<table>
<tr><th>Scenario</th><th>Cascade Path</th><th>Blast Radius</th><th>Annual Loss</th></tr>
{cascade_rows}
</table>

<h2>5-Layer Availability Ceiling Analysis</h2>
<p>FaultRay decomposes system availability into 5 independent constraint layers. The effective availability is bounded by the minimum across all layers.</p>
<table>
<tr><th>Layer</th><th>Factors</th><th>Availability</th><th>Nines</th></tr>
{avail_rows}
</table>
<div class="binding">
    <strong>A<sub>system</sub> = min(L1, L2, L3, L4, L5) = 99.88% (Layer 4: Operational)</strong><br>
    Target SLA: 99.95% — Gap: 0.07% = ~6.1 hours/year of additional downtime risk.
</div>

<h2>Remediation Roadmap</h2>
<table>
<tr><th>#</th><th>Action</th><th>Component</th><th>Annual Cost</th><th>Annual Savings</th><th>ROI</th><th>Timeline</th></tr>
{fix_rows}
</table>
<p><strong>Total Fix Cost:</strong> $28,200/year | <strong>Total Risk Reduction:</strong> $851,000/year | <strong>Overall ROI:</strong> 30x</p>

<h2>Methodology</h2>
<p>This assessment was conducted using FaultRay v11.0, a zero-risk chaos engineering platform that simulates infrastructure failures entirely in computer memory without affecting production systems. The methodology includes:</p>
<ul style="padding-left:20px;font-size:13px;margin:12px 0;">
<li><strong>Graph-Based Cascade Simulation:</strong> Infrastructure modeled as a directed dependency graph with typed edges (required/optional/async). Failure propagation simulated using a Labeled Transition System (LTS) with 8 formal transition rules and proven termination in O(|C|+|E|).</li>
<li><strong>5-Layer Availability Limit Model:</strong> Independent availability ceilings computed for hardware, software, theoretical, operational, and external SLA layers.</li>
<li><strong>AI Agent Cross-Layer Failure Modeling:</strong> Hallucination probability H(a,D,I) computed as a function of infrastructure state for AI-based fraud detection components.</li>
<li><strong>Financial Impact Estimation:</strong> Downtime costs computed from component-level cost-per-hour estimates and simulated MTBF/MTTR.</li>
</ul>
<p style="font-size:13px;margin-top:12px;">Validation: FaultRay's cascade engine has been backtested against 18 real-world cloud incidents (2017-2023) with F1=1.000 for cascade path prediction. Paper: <a href="https://doi.org/10.5281/zenodo.19139911">DOI: 10.5281/zenodo.19139911</a>. US Patent Pending: Application No. 64/010,200.</p>

<h2>Disclaimer</h2>
<p style="font-size:12px;color:#64748b;">This report is generated by automated simulation and does not constitute legal or regulatory compliance advice. The assessment is based on the infrastructure topology model provided and may not reflect all aspects of the organization's ICT environment. Organizations should consult qualified legal and compliance professionals for definitive DORA compliance determinations. Financial estimates are based on industry averages and should be validated against actual organizational data.</p>

<div class="footer">
    Generated by <a href="https://faultray.com">FaultRay</a> — Zero-Risk Chaos Engineering<br>
    <a href="https://github.com/mattyopon/faultray">GitHub</a> |
    <a href="https://doi.org/10.5281/zenodo.19139911">Research Paper</a> |
    <a href="https://faultray.streamlit.app">Live Demo</a><br>
    &copy; 2025-2026 Yutaro Maeda. Patent Pending US 64/010,200.
</div>

</div>
</body>
</html>"""

    return html


def main():
    html = _generate_html()
    os.makedirs(os.path.dirname(HTML_PATH), exist_ok=True)
    with open(HTML_PATH, "w") as f:
        f.write(html)
    print(f"Written: {HTML_PATH}")

    # Also copy to Windows Downloads
    win_path = "/mnt/d/UserFolders/Downloads/dora-compliance-report-sample.html"
    try:
        with open(win_path, "w") as f:
            f.write(html)
        print(f"Written: {win_path}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
