<p align="center">
  <h1 align="center">FaultRay</h1>
  <p align="center"><strong>DORA-aligned Resilience Research Prototype — Without Touching Production</strong></p>
</p>

<p align="center">
  <a href="https://pypi.org/project/faultray/"><img src="https://img.shields.io/pypi/v/faultray" alt="PyPI"></a>
  <a href="https://pypi.org/project/faultray/"><img src="https://img.shields.io/pypi/dm/faultray" alt="Downloads"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License"></a>
  <a href="https://doi.org/10.5281/zenodo.19139911"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.19139911.svg" alt="DOI"></a>
  <a href="https://github.com/mattyopon/faultray/actions/workflows/ci.yml"><img src="https://github.com/mattyopon/faultray/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://faultray.com/demo"><img src="https://img.shields.io/badge/demo-live-brightgreen" alt="Live Demo"></a>
  <a href="https://github.com/mattyopon/faultray"><img src="https://img.shields.io/badge/resilience-72%2F100-green" alt="Resilience Score"></a>
  <a href="https://github.com/mattyopon/faultray/actions/workflows/ci.yml"><img src="https://img.shields.io/badge/tests-31%2C000%2B%20passed-brightgreen" alt="Tests"></a>
</p>

<p align="center">
  <strong>☁️ <a href="https://faultray.com">Try FaultRay Cloud</a> — No setup required &nbsp;|&nbsp; <a href="https://faultray.com/demo">Live Demo</a></strong>
</p>

---

**DORA pre-audit resilience evidence for critical financial services.**

FaultRay helps EU financial institutions walk into a DORA pre-audit prepared with a sanitized, no-production-access resilience evidence pack for one critical service. The pack is designed to make resilience assumptions, failure scenarios, observed gaps, and remediation priorities easier to review before formal audit or supervisory conversations. Under the hood, FaultRay is an open-source resilience and fault-injection simulator, used here as decision-support tooling for practical pre-audit preparation.

### DORA Resilience Evidence Sprint

The DORA Resilience Evidence Sprint is a fixed-scope engagement for one critical service, delivered in 5 business days using sanitized data only: no production access, no PII, and no customer data required. The output is a DORA-mapped resilience evidence pack that helps operational-resilience and ICT-risk teams organize service context, test assumptions, failure scenarios, findings, and next steps against relevant DORA articles. Price: $2,500, with 50% upfront.

Book a 20-minute scoping call: https://faultray.com/evidence-sprint

Prefer self-serve? You can generate an evidence pack yourself with `faultray report dora --service <name>` (see the [evidence-pack template](docs/sales/dora-evidence-pack-template.md)).

Note: FaultRay is decision-support and pre-audit tooling; it is not legal advice, not a DORA certification, not a guarantee of compliance, and does not replace TLPT or auditor sign-off.

---

The rest of this README covers the open-source toolkit: install, usage, and features.

FaultRay simulates **hundreds to thousands of failure scenarios** entirely in memory to estimate structural resilience limits from dependency models — before deployment. Built as a **research prototype** to support DORA-aligned pre-audit preparation for financial institutions, without touching production systems.

> ⚠️ **Scope note:** FaultRay is a research prototype. Outputs are intended for internal pre-audit review, design-time analysis, and CI/CD gating. They are **not** validated substitutes for formal regulatory audit evidence or independent legal/technical review. Validation to date is retrospective; forward-looking predictive accuracy is still under evaluation.

## Screenshots

<table>
  <tr>
    <td><img src="docs/screenshots/dashboard.png" alt="Dashboard" width="400"><br><sub>Resilience Dashboard</sub></td>
    <td><img src="docs/screenshots/heatmap.png" alt="Heatmap" width="400"><br><sub>Failure Heatmap</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/topology.png" alt="Topology" width="400"><br><sub>Dependency Topology</sub></td>
    <td><img src="docs/screenshots/cost-analysis.png" alt="Cost Analysis" width="400"><br><sub>Financial Impact Analysis</sub></td>
  </tr>
  <tr>
    <td colspan="2"><img src="docs/screenshots/compliance.png" alt="Compliance" width="400"><br><sub>DORA Compliance Dashboard</sub></td>
  </tr>
</table>

## Demo

```bash
pip install faultray
faultray demo
```

```
Building demo infrastructure...
╭────────────────────────────────────────────────────╮
│ Metric           │ Value                           │
│ Components       │ 9                               │
│ Dependencies     │ 12                              │
│ Resilience Score │ 50.0/100                        │
╰────────────────────────────────────────────────────╯

Running chaos simulation...

╭────────── FaultRay Chaos Simulation Report ──────────╮
│ Resilience Score: 50/100                             │
│ Scenarios tested: 255                                │
│ Critical: 21  Warning: 84  Passed: 150               │
╰──────────────────────────────────────────────────────╯

  Generate HTML report: faultray simulate --html report.html
  Generate DORA evidence: faultray dora evidence infra.yaml
```

## Why Financial Institutions Choose FaultRay

Traditional chaos engineering tools (Gremlin, Steadybit, AWS FIS) inject real failures into running systems. FaultRay **complements** — not replaces — those runtime tools by moving structural resilience checks earlier into design and CI/CD. Your trading systems stay online. Your payment rails keep running. You get structured evidence packages for internal review and pre-audit preparation.

| | Gremlin | Steadybit | AWS FIS | **FaultRay** |
|---|---|---|---|---|
| Approach | Fault injection | Fault injection (with safety) | Fault injection | **Model-based simulation** |
| Positioning | Runtime validation | Runtime validation | Runtime validation | **Pre-deployment / design-time** |
| Production fault injection | Yes (controlled) | Yes (controlled) | Yes (controlled) | **None (simulation only)** |
| Setup (simulation) | Agent per host | Agent per host | AWS only | **`pip install`** (CLI only; APM agent optional) |
| DORA support | Reporting available | Reporting available | CloudWatch logs | **Pre-audit evidence drafts (research prototype)** |
| AI agent testing | No | No | No | **Yes (modeled)** |
| Cost | $$$$ | $$$ | $$ | **Free tier / Enterprise** |

> Use FaultRay **before** deployment for structural analysis; use runtime chaos engineering **where** live operational validation is required.

## DORA Compliance — All 5 Pillars

FaultRay outputs are designed to **help teams prepare** for DORA-related internal review, mapped against the EU Digital Operational Resilience Act (Regulation EU 2022/2554, fully effective since January 17, 2025). DORA non-compliance carries regulatory fines up to 2% of global annual turnover — this is a statement about the regulation, not a guarantee that FaultRay outputs satisfy it. Evidence generated by FaultRay is a **research-prototype draft** for internal use; formal audit compliance requires independent legal and technical review.

### Full DORA Command Suite

```bash
# Pillar 1: ICT Risk Management (Articles 5-16)
faultray dora assess model.json              # 52-control compliance check
faultray dora risk-assessment model.json     # Comprehensive risk evaluation
faultray dora gap-analysis model.json        # Control gaps + remediation

# Pillar 2: Incident Management (Articles 17-23)
faultray dora incident-assess model.json     # Incident readiness evaluation

# Pillar 3: Resilience Testing (Articles 24-27)
faultray simulate --model model.json --json  # chaos scenario simulation
faultray dora test-plan model.json           # Generate resilience test plan
faultray dora tlpt-readiness model.json      # TLPT preparation assessment

# Pillar 4: Third-Party Risk (Articles 28-30)
faultray dora concentration-risk model.json  # ICT concentration risk (HHI)
faultray dora register model.json            # RTS 2024/1774 register

# Pillar 5: Information Sharing (Article 45)
# Integrated threat intelligence from CVE/CISA advisories

# Evidence & Reporting
faultray dora evidence model.json            # Audit-ready evidence package
faultray dora report model.json              # HTML report for regulators
faultray dora rts-export model.json --format csv  # Machine-readable export
```

### What Regulators See

FaultRay generates timestamped, signed evidence packages that map every finding to specific DORA articles and RTS requirements:

- **RTS 2024/1774** — ICT Risk Management Framework details
- **ITS 2024/2956** — Register of Information templates
- **RTS 2025/301** — Incident reporting content and timelines

## Quick Start

### 1. Terraform Safety Net (CI/CD Integration)

```bash
terraform plan -out=plan.out
terraform show -json plan.out > plan.json
faultray tf-check plan.json --fail-on-regression --min-score 60
```

```yaml
# .github/workflows/terraform.yml
- name: Resilience Gate
  run: |
    pip install faultray
    terraform show -json plan.out > plan.json
    faultray tf-check plan.json --fail-on-regression --min-score 60
```

### 2. GitHub Action (Marketplace)

Add FaultRay to any CI/CD pipeline with our official GitHub Action:

```yaml
# .github/workflows/resilience.yml
name: Resilience Check
on: [pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: mattyopon/faultray@v1
        with:
          plan-file: plan.json
          min-score: 60
          fail-on-regression: true
          financial: true
```

Or use it with a YAML infrastructure definition:

```yaml
      - uses: mattyopon/faultray@v1
        with:
          yaml-file: infra.yaml
          financial: true
          cost-per-hour: 25000
```

Available inputs:

| Input | Description | Default |
|---|---|---|
| `plan-file` | Path to Terraform plan JSON file | `''` |
| `yaml-file` | Path to infrastructure YAML file | `''` |
| `min-score` | Minimum resilience score (0-100). Fails if below. | `0` |
| `fail-on-regression` | Fail if resilience score drops from baseline | `false` |
| `financial` | Include financial impact analysis | `false` |
| `cost-per-hour` | Default cost per hour of downtime (USD) | `10000` |

### 3. Define Your Infrastructure

```yaml
# infra.yaml
components:
  - id: api-gateway
    type: load_balancer
    replicas: 2
  - id: trading-engine
    type: app_server
    replicas: 3
  - id: market-data
    type: database
    replicas: 1   # ← FaultRay flags this as SPOF

dependencies:
  - source: api-gateway
    target: trading-engine
    type: requires
  - source: trading-engine
    target: market-data
    type: requires
```

```bash
faultray load infra.yaml
faultray simulate --html report.html
```

### 4. AI Agent Testing

```bash
faultray agent assess ai-workflow.yaml     # Risk assessment
faultray agent scenarios ai-workflow.yaml  # What could go wrong?
```

Simulates AI-specific failures: hallucination cascades, context overflow, LLM rate limiting, token exhaustion, tool failures, agent loops, prompt injection.

### Sensitivity Ratchet Simulation

Measure how much damage the **sensitivity ratchet** prevents. The ratchet is a security mechanism where an agent's outbound permissions narrow irreversibly once it accesses data above a certain sensitivity threshold (PUBLIC < INTERNAL < CONFIDENTIAL < RESTRICTED < TOP_SECRET).

```bash
faultray agent ratchet                        # Run all built-in scenarios
faultray agent ratchet --scenario exfiltration  # Single scenario
faultray agent ratchet --json                 # Machine-readable output
```

Built-in scenarios:
- **exfiltration** — Agent reads classified data then tries to send externally
- **cross-agent** — Agent A passes classified data to Agent B who attempts external send
- **escalation** — Agent gradually accesses higher-sensitivity data

Each scenario runs twice (with and without the ratchet) and reports an **effectiveness score** showing how much data-leak damage the ratchet prevents.

### 5. Continuous Compliance Monitoring

```bash
faultray compliance-monitor model.json --framework dora  # DORA
faultray compliance-monitor model.json --framework soc2  # SOC 2
faultray compliance-monitor model.json --framework pci   # PCI DSS
```

Tracks compliance trends over 90 days with automated drift detection.

## APM — Application Performance Monitoring

FaultRay includes a lightweight APM agent that collects real-time host metrics and feeds them to the FaultRay collector for anomaly detection, alerting, and topology-aware analysis.

```bash
# One-command interactive setup
faultray apm setup

# Or manual setup
faultray apm install --collector http://localhost:8080
faultray apm start
faultray apm status
```

### Architecture

```
Your Hosts                          FaultRay Server
┌────────────────────────────┐      ┌──────────────────────────────┐
│  APM Agent  (each host)    │      │  Collector  faultray serve   │
│  ─────────────────────     │      │  ─────────────────────────── │
│  Collects every 15s:       │─────▶│  Time-Series DB              │
│  • CPU utilization         │ HTTP │  Anomaly Detection (Z-score) │
│  • Memory usage            │      │  Alert Rules Engine          │
│  • Disk usage              │      │  Web Dashboard  :8080/apm    │
│  • Network I/O             │      └──────────────────────────────┘
│  • Process count           │
│  • TCP connections         │
└────────────────────────────┘
```

### Metrics Collected

| Metric | Description |
|---|---|
| `cpu_percent` | CPU utilization across all cores |
| `memory_percent` | RAM usage (used / total) |
| `disk_percent` | Root disk usage |
| `net_bytes_sent` | Network bytes sent |
| `net_bytes_recv` | Network bytes received |
| `process_count` | Number of running processes |
| `tcp_connections` | Active TCP connections |

### Integration with Simulation

APM real-baseline data feeds directly into chaos simulations:

```bash
# Capture baseline metrics
faultray apm metrics <agent-id> --json > baseline.json

# Run simulation using real topology
faultray simulate infra.yaml

# Correlate simulation results with APM alerts
faultray apm alerts --severity critical
```

## Resilience Badge

Show your infrastructure resilience score in your README:

```bash
faultray badge infra.yaml
```

Output:

```
[![Resilience Score](https://img.shields.io/badge/resilience-72%2F100-green)](https://github.com/mattyopon/faultray)
```

Which renders as: ![Resilience Score](https://img.shields.io/badge/resilience-72%2F100-green)

The badge color adjusts automatically based on your score:

| Score | Color |
|-------|-------|
| 80-100 | Bright green |
| 60-79 | Green |
| 40-59 | Yellow |
| 20-39 | Orange |
| 0-19 | Red |

For raw URL output (no markdown wrapping):

```bash
faultray badge infra.yaml --url
```

## Key Features

| Feature | Description |
|---|---|
| **5-Layer Availability Model** | Model-based estimate of your structural uptime ceiling from declared topology — e.g., "your 99.99% SLA looks structurally infeasible given this dependency graph" |
| **5 Simulation Engines** | Cascade, Dynamic, Ops, What-If, Capacity |
| **DORA Compliance Suite (Research Prototype)** | 52 controls, 5 pillars — generates draft evidence packages for internal pre-audit review (not a substitute for formal audit evidence) |
| **Cascade Failure Analysis** | Graph-based blast radius mapping with containment scoring |
| **SPOF Detection** | Graph-based identification of single points of failure from declared dependencies (requires engineering review of results) |
| **AI Agent Testing** | 7 agent-specific fault types (hallucination, loops, etc.) |
| **Terraform Integration** | Pre-apply impact analysis as a CI/CD gate |
| **Third-Party Risk** | ICT concentration risk analysis (Herfindahl-Hirschman Index) |
| **Multi-Framework Compliance** | SOC 2, ISO 27001, PCI DSS 4.0, NIST CSF, DORA, HIPAA, GDPR |
| **APM Agent** | Install once, monitor forever — real-time metrics, anomaly detection, topology auto-discovery |
| **Comprehensive CLI** | From `faultray demo` to `faultray war-room` — covers simulation, DORA assessment, agent analysis, reporting, and dashboard workflows |

## The 5-Layer Availability Model

Most SLA claims are aspirational. FaultRay **estimates** what's structurally achievable from declared topology — result quality depends on how completely your dependencies are defined:

| Layer | What It Measures | Financial Impact |
|---|---|---|
| L1: Software | Deploy downtime, human error, config drift | Operational uptime ceiling |
| L2: Hardware | MTBF/MTTR × redundancy × failover | Physical infrastructure limits |
| L3: Theoretical | Network loss, GC pauses, jitter | Unreachable upper bound |
| L4: Operational | Incident rate × response time, on-call coverage | Team capacity constraints |
| L5: External SLA | ∏(third-party SLAs) | Vendor dependency floor |

**Result**: A model-based availability ceiling estimate. If your declared infrastructure graph implies 99.95% max but you're promising 99.99%, FaultRay surfaces the gap early — as a directional signal for engineering review, not a regulatory verdict.

## Who It's For

**Best for**
- Teams with Terraform or YAML-defined infrastructure
- Regulated environments (finance, healthcare) needing pre-deployment resilience review
- Engineering teams adding resilience gates to CI/CD
- AI agent platforms modeling LLM / tool / orchestrator dependencies

**Not ideal for**
- Environments with undocumented or drifting dependencies (results depend on model fidelity)
- Teams expecting runtime behavior replay from live production traffic
- Audit teams seeking stand-alone formal compliance evidence
- Operators needing minute-level outage duration precision (downtime outputs are directional, not operationally precise)

## Research & Patent

FaultRay's core algorithms are described in a peer-reviewable paper and protected by a US patent application.

**Paper:**
> Maeda, Y. (2026). *FaultRay: In-Memory Infrastructure Resilience Simulation with Graph-Based Cascade Analysis, Multi-Layer Availability Limits, and AI Agent Failure Modeling.* Zenodo. [DOI: 10.5281/zenodo.19139911](https://doi.org/10.5281/zenodo.19139911)

**Patent:**
> US Provisional Patent Application No. 64/010,200 (filed March 19, 2026)

```bibtex
@misc{maeda2026faultray,
  author    = {Maeda, Yutaro},
  title     = {FaultRay: In-Memory Infrastructure Resilience Simulation},
  year      = {2026},
  doi       = {10.5281/zenodo.19139911},
  publisher = {Zenodo}
}
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
```

## Community

- [Contributing Guide](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## License

Apache License 2.0 — see [LICENSE](LICENSE).

> **License Transition (2026-04-11):** FaultRay was relicensed from BSL 1.1 to Apache 2.0.
> - v11.1.0 and earlier: BSL 1.1 (yanked on PyPI)
> - v11.2.0 and later: Apache 2.0 (recommended)
