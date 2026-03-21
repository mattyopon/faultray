---
title: How We Simulate 2,000+ Infrastructure Failures Without Touching Production
published: false
description: FaultRay scores your infrastructure resilience before terraform apply — catching cascade risks, SPOFs, and availability ceiling violations in seconds.
tags: chaosengineering, devops, python, terraform
cover_image:
---

It is 2am. Your pager fires. A `terraform apply` that "just changed a timeout" has taken down the payment service, the order queue, and half the API layer. The plan output looked clean. The PR had two approvals. And yet here you are, staring at a cascade failure that nobody predicted.

This is the scenario that led us to build FaultRay.

## The problem with breaking things to test things

The standard chaos engineering playbook, pioneered by Netflix's Chaos Monkey in 2011 and continued by tools like Gremlin, Steadybit, and AWS FIS, follows a simple premise: inject real faults into real systems, observe what breaks, fix it.

This works, but it has structural limitations:

- **It requires a production-like environment.** Staging is always out of sync. The failure you test in staging may not match what happens in prod.
- **It tests scenarios you think of.** You write the experiments. You choose what to break. The failures you did not imagine are the ones that page you.
- **It cannot answer the ceiling question.** No amount of fault injection will tell you that your architecture physically cannot reach 99.99% uptime, because your external SLA chain caps you at 99.9%.
- **Regulated industries cannot use it.** Banks, healthcare systems, and government agencies are not going to randomly kill production processes to see what happens.

## A different approach: simulate, don't break

FaultRay takes a fundamentally different path. Instead of injecting faults into running systems, it builds a dependency graph of your infrastructure and simulates over 2,000 failure scenarios entirely in memory. Nothing is deployed. Nothing is touched. You get a resilience score, a list of single points of failure, and a map of every cascade path — in seconds.

The most common integration point is the Terraform pipeline. After `terraform plan`, you export the plan as JSON and run:

```bash
terraform plan -out=plan.out
terraform show -json plan.out > plan.json
faultray tf-check plan.json
```

```
╭──────────── FaultRay Terraform Guard ────────────╮
│                                                   │
│  Score Before: 72/100                             │
│  Score After:  45/100  (-27 points)               │
│                                                   │
│  NEW RISKS:                                       │
│  - Database is now a single point of failure      │
│  - Cache has no replication (data loss risk)      │
│                                                   │
│  Recommendation: HIGH RISK - Review Required      │
│                                                   │
╰───────────────────────────────────────────────────╯
```

FaultRay models what your infrastructure looks like *before* and *after* the planned change, runs the full simulation against both states, and shows you the delta. Not "this is risky" but "this specific change drops your score by 27 points and introduces a new SPOF."

### CI/CD integration in 2 lines

```yaml
# .github/workflows/terraform.yml
- name: Check Terraform Plan
  run: |
    pip install faultray
    faultray tf-check plan.json --fail-on-regression --min-score 60
```

`--fail-on-regression` fails the job if the resilience score drops at all. `--min-score 60` fails if the resulting score is below your threshold. The job blocks the merge. The 2am page never happens.

## The math behind the score

This is the part that might interest you if you have read this far. FaultRay is not a heuristic engine. It is built on formal methods with proven properties.

### 5-Layer Availability Limit Model

Most teams set SLO targets (99.99%, four nines) without knowing whether their architecture can physically reach them. FaultRay computes five independent availability ceilings:

```
Layer 1: Software Limit     → Deployment downtime, human error, config drift
Layer 2: Hardware Limit     → Component MTBF, MTTR, redundancy, failover time
Layer 3: Theoretical Limit  → Irreducible physical noise (packet loss, GC, jitter)
Layer 4: Operational Limit  → Incident response time, team size, on-call coverage
Layer 5: External SLA Chain → Product of all third-party dependency SLAs
```

Your system's availability ceiling is:

```
A_system = min(L1, L2, L3, L4, L5)
```

If Layer 5 says your external SLA chain caps you at 99.9% (three nines), it does not matter that your hardware can do five nines. The bottleneck is the weakest layer. FaultRay surfaces this before you spend months over-engineering the wrong layer.

### LTS-based cascade engine

The cascade simulator implements a Labeled Transition System (LTS) formalized as a 4-tuple `S = (H, L, T, V)`:

- `H`: health map (component to status)
- `L`: accumulated latency map
- `T`: elapsed time
- `V`: visited set (monotonically growing)

The system has four proven properties:

1. **Monotonicity** — health can only worsen during a simulation run
2. **Causality** — a component fails only if a dependency has failed
3. **Circuit breaker correctness** — a tripped circuit breaker stops cascade at that edge
4. **Termination** — the engine terminates in O(|V| + |E|) for acyclic graphs; a depth limit of 20 guarantees termination for cyclic graphs

These properties mean the simulation is deterministic and complete. It will find every reachable failure state, and it will always halt. The full formal specification is in the [paper](https://doi.org/10.5281/zenodo.19139911).

### AI agent hallucination model

FaultRay v11 introduced failure modeling for AI agent systems. The core model computes hallucination probability as a function of three variables:

```
H(a, D, I)
```

Where `a` is the agent, `D` is the set of data sources, and `I` is the infrastructure state. When a data source goes DOWN, the agent's hallucination probability increases proportionally to its dependency weight on that source:

```
If source d is HEALTHY:    h_d = h0
If source d is DOWN:       h_d = h0 + (1 - h0) * w(d)
If source d is DEGRADED:   h_d = h0 + (1 - h0) * w(d) * delta
```

This captures a failure mode that traditional chaos tools cannot model: your LLM endpoint stays up, your agent keeps responding, but its answers become unreliable because the grounding data it depends on is gone. The agent does not throw an error. It hallucinates. FaultRay quantifies the probability and traces the cascade through multi-agent chains.

## Validation: 18 real-world incidents

We backtested FaultRay against 18 documented public cloud incidents (AWS, GCP, Azure outages with known root causes and blast radii). The engine was given the pre-incident topology, told which component failed, and asked to predict which downstream services would be affected.

Results: **F1 = 1.000** across all 18 incidents.

We should be honest about what this means and what it does not. The topologies were constructed post-hoc from incident reports. We knew the architecture because the post-mortems described it. This validates that the cascade engine correctly propagates failures through a known graph. It does not validate topology discovery from real Terraform state, which is a harder and less controlled problem. The backtest methodology and all 18 incidents are documented in the paper.

## Try it

```bash
pip install faultray
faultray demo
```

The demo runs a simulation against a sample infrastructure (load balancer, app servers, database, cache, queue) and outputs a full resilience report. Add `--web` for an interactive D3.js dependency graph in your browser.

To analyze your own infrastructure, define it in YAML:

```yaml
components:
  - id: nginx
    type: load_balancer
    replicas: 2
  - id: api
    type: app_server
    replicas: 3
  - id: postgres
    type: database
    replicas: 1  # FaultRay will flag this

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

Or import directly from Terraform state with `faultray tf-import`.

## Links

- **GitHub:** [github.com/mattyopon/faultray](https://github.com/mattyopon/faultray)
- **Paper (DOI):** [doi.org/10.5281/zenodo.19139911](https://doi.org/10.5281/zenodo.19139911)
- **PyPI:** [pypi.org/project/faultray](https://pypi.org/project/faultray/)

FaultRay is licensed under BSL 1.1, converting to Apache 2.0 in 2030. Contributions and feedback are welcome.
