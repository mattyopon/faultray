# FaultRay

> Pre-deployment resilience simulation (research prototype). Estimate your availability ceiling from declared topology, without touching production.

## What is FaultRay?

FaultRay simulates infrastructure failures without touching production. It builds a mathematical model of your infrastructure and runs thousands of failure scenarios to identify single points of failure, cascade risks, and availability ceilings — all without any real-world impact.

Unlike traditional chaos engineering tools that inject real faults into live systems, FaultRay operates entirely on a virtual model. This means you can evaluate resilience during design reviews, CI/CD pipelines, and pre-deployment checks.

## Key Features

- **Zero-risk simulation** — No production impact, ever
- **5-layer infrastructure model** — Compute, storage, network, DNS, CDN
- **150+ failure scenarios** — SPOF detection, cascade analysis, regional outages
- **Resilience scoring** — Quantified 0-100 score with actionable recommendations
- **Cloud-native scanning** — Auto-import from AWS, GCP, Azure, Kubernetes
- **Terraform integration** — Scan IaC before deployment
- **CI/CD integration** — Gate deployments on resilience thresholds
- **Insurance-grade scoring** — Compliance and risk assessment reports

## Quick Start

```bash
pip install faultray
faultray quickstart
```

This generates a sample infrastructure model and runs a basic simulation, producing a resilience report in seconds.

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Cloud Scanner   │────▶│  5-Layer Model    │────▶│  Simulation     │
│  (AWS/GCP/Azure) │     │  (Graph-based)    │     │  Engine         │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
┌─────────────────┐     ┌──────────────────┐              │
│  Reports &       │◀────│  Risk Scoring     │◀─────────────┘
│  Dashboards      │     │  Engine           │
└─────────────────┘     └──────────────────┘
```

## Next Steps

- [Installation](getting-started/installation.md) — Install FaultRay in your environment
- [Quick Start](getting-started/quickstart.md) — Get up and running in 5 minutes
- [How It Works](concepts/how-it-works.md) — Understand the simulation engine
- [CLI Reference](cli/commands.md) — Full command-line documentation
