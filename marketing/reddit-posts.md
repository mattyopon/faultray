# FaultRay Reddit Posts

---

## 1. r/devops

**Title:** We built a Terraform pre-apply resilience checker -- catches SPOFs and cascade risks before you hit apply

**Body:**

We kept running into the same problem: `terraform plan` looks clean, PR gets approved, `terraform apply` runs, and then something falls over at 2am because a replica count got set to 1 or a new dependency created a cascade path nobody noticed.

So we built a tool that scores your infrastructure's resilience before and after a Terraform change, and flags the delta. It runs entirely in memory -- no agents, no production access needed, no credentials beyond what Terraform already has.

```bash
terraform plan -out=plan.out
terraform show -json plan.out > plan.json
faultray tf-check plan.json
```

```
+--------------------------------------------------+
|  FaultRay Terraform Guard                        |
|                                                  |
|  Score Before: 72/100                            |
|  Score After:  45/100  (-27 points)              |
|                                                  |
|  NEW RISKS:                                      |
|  - Database is now a single point of failure     |
|  - Cache has no replication (data loss risk)     |
|                                                  |
|  Recommendation: HIGH RISK - Review Required     |
+--------------------------------------------------+
```

CI/CD integration is two lines:

```yaml
- name: Check Terraform Plan
  run: |
    pip install faultray
    terraform show -json plan.out > plan.json
    faultray tf-check plan.json --fail-on-regression --min-score 60
```

`--fail-on-regression` fails the job if the resilience score drops at all. `--min-score 60` sets a floor. It works with any Terraform-managed infra (AWS, GCP, Azure, on-prem) because it reasons about the topology in the plan JSON, not cloud APIs.

What it actually catches: removing replicas you meant to keep, adding dependencies that create cascade paths, timeout changes that break health check chains, accidentally making a replicated service single-instance.

It also does broader chaos simulation -- 2,000+ failure scenarios against your infra definition, availability ceiling modeling, capacity forecasting. But the Terraform guard is the most immediately useful thing.

**Limitations worth noting:** The simulation is only as good as the model. It reasons about topology and redundancy, not application-level logic. It will not catch a bad SQL migration or a race condition. It is also relatively new, so rough edges exist.

```
pip install faultray && faultray demo
```

GitHub: https://github.com/mattyopon/faultray

Happy to answer questions about the approach.

---

## 2. r/sre

**Title:** Tool that mathematically proves your availability ceiling -- validated against 18 real cloud incidents (AWS, GCP, Azure, Meta, Cloudflare)

**Body:**

I have been thinking about a problem that comes up repeatedly in SRE: teams set SLO targets (say 99.99%) without knowing whether their architecture can physically reach that number. You end up burning engineering effort trying to close a gap that cannot be closed without structural changes.

FaultRay is a tool that computes your system's theoretical availability ceiling using a 5-layer limit model. Each layer represents an independent constraint:

- Hardware limit (component MTBF/MTTR)
- Software limit (deployment frequency, human error rates)
- Theoretical limit (redundancy topology math)
- Operational limit (incident response coverage, on-call depth)
- External SLA cascading (third-party SLA products)

Your actual ceiling is the minimum across all layers. If your external dependencies cap you at 99.9% but your SLO target is 99.99%, that is a structural problem no amount of on-call heroics will fix.

The tool runs 2,000+ failure scenarios in memory against a dependency graph model of your infrastructure. No production access, no fault injection, no risk. It uses a cascade propagation engine formalized as a Labeled Transition System over a 4-tuple state space, which gives you deterministic replay and formal correctness properties.

We validated the cascade prediction engine against 18 real-world cloud incidents spanning 2017-2023: AWS US-East-1 (2021), S3 outage (2017), Meta BGP (2021), Cloudflare (2022), GCP (2019), Azure (2023), CrowdStrike (2024), Fastly (2021), DynamoDB (2015), and others. Cascade path prediction achieved F1 = 1.000 across all 18 incidents. Severity accuracy averaged 0.819. Downtime estimation is the weakest point -- mean absolute error is high, especially for prolonged incidents like OVH and Roblox. We are still calibrating that.

It integrates with Terraform (analyze plan JSON before apply), Prometheus (auto-discover topology from targets), and generates compliance reports for DORA, SOC 2, ISO 27001.

The approach also extends to AI agent failure modeling if you are running LLM-based agents in production, but the core value for SRE is the availability limit analysis and cascade prediction.

**What it is not:** a replacement for actual game days or production chaos experiments. It tells you what your architecture can theoretically withstand. You still need to verify that your actual implementation matches the model.

```
pip install faultray && faultray demo
```

GitHub: https://github.com/mattyopon/faultray

Paper with formal proofs: https://github.com/mattyopon/faultray/tree/main/paper

---

## 3. r/MachineLearning

**Title:** Cross-layer failure model for AI agents: quantifying hallucination probability as a function of infrastructure health

**Body:**

We have been working on a formal model for how infrastructure failures propagate through AI agent systems and cause compound failures that are qualitatively different from traditional software failures.

The core contribution is a hallucination probability function H(a, D, I) that quantifies how an agent's hallucination risk changes as a function of three variables: agent configuration (a), data source health (D), and infrastructure state (I). When all grounding sources are healthy, H reduces to the agent's baseline hallucination rate h_0(a). As data sources degrade or go down, H increases monotonically -- the key insight being that infrastructure failures do not just cause downtime for agents, they cause agents to produce confident but wrong outputs because their grounding data becomes unavailable or stale.

The model defines a 4-layer cascade:

1. Infrastructure layer: component failure (database down, cache degraded)
2. Data availability layer: reduced data quality for agent grounding
3. Agent behavior layer: elevated H(a,D,I), degraded reasoning
4. Downstream impact layer: incorrect outputs consumed by users or other agents

For agent-to-agent chains, the compound hallucination probability grows -- when agent a1 feeds output to agent a2, a2's effective hallucination risk incorporates a1's output reliability. This models the "telephone game" effect in multi-agent orchestration systems.

We also define a 10-mode failure taxonomy specific to AI agents: hallucination, context overflow, LLM rate limiting, token exhaustion, tool failure, agent loops, prompt injection, confidence miscalibration, chain-of-thought collapse, and output amplification. Each mode maps to a health state (degraded, down, overloaded) with distinct propagation characteristics.

The practical implementation runs as an open-source tool (FaultRay) that simulates these failure scenarios against a YAML-defined agent architecture. You define your agents, their LLM endpoints, tool dependencies, and orchestration patterns, and it runs 2,000+ scenarios to identify cascade paths and single points of failure.

We validated the underlying cascade engine against 18 real cloud incidents (2017-2023) with F1 = 1.000 for cascade path prediction. The AI agent layer is newer and has not been validated against production agent incidents at the same scale -- that is a limitation we are upfront about. The formal properties (monotonicity, boundedness, compositionality) of H(a,D,I) are proven in the paper.

This is not a monitoring tool or an eval framework. It is specifically about modeling how infrastructure failures interact with AI-specific failure modes at the architectural level, before deployment.

Paper (arXiv, cs.SE/cs.DC): https://github.com/mattyopon/faultray/tree/main/paper

```
pip install faultray && faultray demo
```

GitHub: https://github.com/mattyopon/faultray

Interested in feedback, especially from anyone running multi-agent systems in production and seeing these failure patterns.
