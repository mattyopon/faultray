# FaultRay Launch Materials

## ProductHunt

### Tagline (60 chars max)
Pre-deployment resilience simulation (research prototype)

### Description
FaultRay simulates infrastructure failures without touching production. Unlike Gremlin or Chaos Monkey, which inject real faults at runtime, FaultRay runs thousands of chaos scenarios entirely in memory — giving you a model-based estimate of your system's structural availability ceiling, with a traceable dependency on your declared topology. Research prototype; complements runtime chaos engineering, it does not replace it.

**Key features:**
- 5 simulation engines (Cascade, Dynamic, Ops, What-If, Capacity)
- 3-Layer Availability Limit Model — estimates Software/Hardware/Theoretical ceilings from declared topology
- AI-assisted analysis with remediation suggestions (v11.0: AI agent resilience via MCP)
- DORA-aligned evidence drafts (research prototype; not a substitute for audit-certified evidence)
- Terraform Safety Net — pre-deploy blast radius analysis before `terraform apply`
- Terraform / Prometheus integration
- Plugin system for custom scenarios
- Slack / PagerDuty notifications

**Who is it for?**
- SRE teams evaluating structural resilience
- DevOps engineers planning capacity and dependency changes
- Platform teams validating architecture changes before deploy
- Compliance teams preparing internal DORA-review material (not formal audit output)

**Try it now:**
```
pip install faultray
faultray demo --web
```

### First Comment (maker's comment)
Hi everyone! I'm Yutaro, an infrastructure engineer from Tokyo.

I built FaultRay because I was frustrated with chaos engineering tools that require production access. My team needed to evaluate "what happens if our DB goes down?" without actually breaking things.

FaultRay takes a different approach: model-based simulation. You describe your infrastructure in YAML (or import from Terraform), and FaultRay runs thousands of failure scenarios to surface likely weak points. It's a **research prototype** — result quality depends on how completely your topology is defined, and outputs should be reviewed by your engineering team.

The feature I find most useful is the 3-Layer Availability Limit Model — it **estimates**, from your declared topology, an upper bound such as "your architecture can't cleanly exceed 6.65 nines without changing these dependencies." That's a model-based signal for design review, not a prediction of actual uptime.

v11.0 adds AI agent resilience via MCP: plug FaultRay directly into your AI agents and CI pipelines. Also introducing Terraform Safety Net — pre-deploy blast-radius analysis before `terraform apply` ever runs.

FaultRay (v11.2.0+) is Apache 2.0. I'd love your feedback!

- Live demo: https://faultray.com/demo
- PyPI: pip install faultray
- GitHub: https://github.com/mattyopon/faultray

---

## Hacker News (Show HN)

### Title
Show HN: FaultRay – pre-deployment resilience simulation (research prototype)

### Text
I built FaultRay because existing chaos engineering tools (Gremlin, Chaos Monkey, AWS FIS) all inject real faults into real infrastructure. That's scary, expensive, and requires production access.

FaultRay takes a different approach: it models your infrastructure as a dependency graph and simulates thousands of failure scenarios entirely in memory. No fault injection, no production agents, no live blast radius. It is a **research prototype**, meant to complement runtime chaos engineering, not replace it.

What makes it distinct:

1. **3-Layer Availability Limit Model** — estimates, from your declared topology, an upper bound for:
   - Software limit (example: ~4.00 nines given Ethernet + GC pauses)
   - Hardware limit (example: ~5.91 nines given InfiniBand + GC-free runtimes)
   - Theoretical limit (example: ~6.65 nines bounded by speed-of-light failover time)
   These are illustrative numbers; your actual ceiling depends on how your topology is declared.

2. **5 simulation engines** — Cascade (thousands of scenarios), Dynamic (time-stepped with traffic), Ops (30-day operational sim), What-If (parameter sweeps), Capacity (growth forecasting).

3. **AI-assisted analysis** — identifies SPOFs, cascade amplifiers, and suggests upgrade candidates ranked by estimated nines improvement; v11.0 exposes a 12-tool MCP server for AI-agent / CI integration.

4. **DORA-aligned evidence drafts** — generates research-prototype evidence packages for internal EU DORA review. Not a substitute for audit-certified compliance evidence.

5. **Terraform Safety Net** — pre-deploy blast radius analysis; integrates with Overmind and AWS Resilience Hub.

Tech stack: Python 3.11+, NetworkX, FastAPI, Typer, Pydantic.

Try it:
```
pip install faultray
faultray demo --web
```

Live demo: https://faultray.com/demo
GitHub: https://github.com/mattyopon/faultray

---

## Reddit r/devops & r/sre

### Title
[Tool] FaultRay: simulate infrastructure failures without touching production — pre-deploy resilience estimation, research prototype

### Body
Hey r/devops,

I've been working on an open-source tool that takes a different approach to chaos engineering. Instead of injecting faults into real infrastructure, FaultRay simulates everything in memory.

You describe your infra in YAML or import from Terraform, and it runs thousands of failure scenarios (single failures, pairwise combinations, traffic spikes, DB-specific issues, cache stampedes, etc.) and estimates what would likely break and how badly — as a model-based signal, not a guarantee.

**The feature I find most useful**: it gives a model-based estimate of your system's structural availability ceiling. For example, "your current architecture appears to cap out around 4.2 nines given this declared topology — to reach 5 nines you'd likely need to add replicas here and circuit breakers there." It's a design-review signal, not a prediction of measured uptime.

**v11.0 highlights**: AI agent resilience via MCP (12-tool server for AI-agent / CI integration), and Terraform Safety Net — pre-deploy blast radius analysis before `terraform apply`.

- Apache 2.0 (current releases v11.2.0+; earlier BSL-1.1 releases are yanked)
- `pip install faultray`
- Live demo: https://faultray.com/demo
- GitHub: https://github.com/mattyopon/faultray

Would love feedback from fellow SREs! Caveat: research prototype — results depend on how completely your topology is declared, and are intended for engineering review, not as formal compliance evidence.
