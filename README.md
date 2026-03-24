<p align="center">
  <h1 align="center">FaultRay</h1>
  <p align="center"><strong>Zero-Risk Chaos Engineering — Simulate, Don't Break</strong></p>
</p>

<p align="center">
  <a href="https://pypi.org/project/faultray/"><img src="https://img.shields.io/pypi/v/faultray" alt="PyPI"></a>
  <a href="https://pypi.org/project/faultray/"><img src="https://img.shields.io/pypi/dm/faultray" alt="Downloads"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-BSL%201.1-orange.svg" alt="License"></a>
  <a href="https://doi.org/10.5281/zenodo.19139911"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.19139911.svg" alt="DOI"></a>
  <a href="https://github.com/mattyopon/ai-agent-security-suite"><img src="https://img.shields.io/badge/Part%20of-AI%20Agent%20Security%20Suite-blueviolet" alt="Part of AI Agent Security Suite"></a>
</p>

---

FaultRay builds a mathematical model of your infrastructure and simulates **2,000+ failure scenarios** entirely in memory. Nothing gets touched. Nothing breaks. You just get answers.

```bash
pip install faultray
faultray demo
```

```
╭────────── FaultRay Chaos Simulation Report ──────────╮
│ Resilience Score: 36/100                             │
│ Scenarios tested: 2,000+                             │
│ Critical: 7  Warning: 66  Passed: 77                 │
╰──────────────────────────────────────────────────────╯
```

## Quick Start

### Terraform Safety Net (most common use case)

```bash
terraform plan -out=plan.out
terraform show -json plan.out > plan.json
faultray tf-check plan.json --fail-on-regression --min-score 60
```

```yaml
# .github/workflows/terraform.yml
- name: Check Terraform Plan
  run: |
    pip install faultray
    terraform show -json plan.out > plan.json
    faultray tf-check plan.json --fail-on-regression --min-score 60
```

### Define Your Infrastructure

```yaml
# infra.yaml
components:
  - id: nginx
    type: load_balancer
    replicas: 2
  - id: api
    type: app_server
    replicas: 3
  - id: postgres
    type: database
    replicas: 1   # ← FaultRay flags this as SPOF

dependencies:
  - source: nginx
    target: api
    type: requires
  - source: api
    target: postgres
    type: requires
```

```bash
faultray load infra.yaml
faultray simulate --html report.html
```

### AI Agent Testing

```bash
faultray agent assess ai-workflow.yaml    # Risk assessment
faultray agent scenarios ai-workflow.yaml # What could go wrong?
```

Simulates AI-specific failures: hallucination cascades, context overflow, LLM rate limiting, token exhaustion, tool failures, agent loops, prompt injection.

### Docker

```bash
docker compose up web                          # Web dashboard
docker compose --profile demo up demo          # Demo mode
```

## Key Features

| Feature | Description |
|---|---|
| **5 Simulation Engines** | Cascade, Dynamic, Ops, What-If, Capacity |
| **5-Layer Availability Model** | Mathematical proof of your uptime ceiling |
| **AI Agent Testing** | 7 agent-specific fault types (hallucination, loops, etc.) |
| **Terraform Integration** | Pre-apply impact analysis in CI/CD |
| **Compliance** | SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR |
| **Security Feed** | Auto-generate scenarios from CVE/CISA advisories |
| **100+ CLI Commands** | From `faultray demo` to `faultray war-room` |

## How It Compares

| | Gremlin | Steadybit | AWS FIS | **FaultRay** |
|---|---|---|---|---|
| Approach | Breaks production | Breaks production | Breaks production | **Math simulation** |
| Risk | Medium-High | Medium | Medium | **Zero** |
| Setup | Agent per host | Agent per host | AWS only | **`pip install`** |
| AI agent testing | No | No | No | **Yes** |
| Cost | $$$$ | $$$ | $$ | **Free / OSS** |

## Research & Patent

FaultRay's core algorithms are described in a peer-reviewable paper and protected by a US patent application.

**Paper:**
> Maeda, Y. (2026). *FaultRay: In-Memory Infrastructure Resilience Simulation with Graph-Based Cascade Analysis, Multi-Layer Availability Limits, and AI Agent Failure Modeling.* Zenodo. [DOI: 10.5281/zenodo.19139911](https://doi.org/10.5281/zenodo.19139911)

**Patent:**
> US Provisional Patent Application No. 64/010,200 (filed March 19, 2026)
> Status: Provisional patent filed. Full utility patent filing deadline: March 19, 2027.

**Citation:**

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

BSL 1.1 — see [LICENSE](LICENSE). Converts to Apache 2.0 on 2030-03-17.
