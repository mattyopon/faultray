# FaultRay Launch Materials

## ProductHunt

### Tagline (60 chars max)
Zero-risk chaos engineering — prove your infra's availability ceiling

### Description
FaultRay simulates infrastructure failures without touching production. Unlike Gremlin or Chaos Monkey that inject real faults, FaultRay runs 150+ chaos scenarios entirely in memory — proving your system's theoretical availability ceiling mathematically.

**Key features:**
- 5 simulation engines (Static, Dynamic, Ops, What-If, Capacity)
- 3-Layer Availability Limit Model (proves your ceiling: 4.00 → 5.91 → 6.65 nines)
- AI-powered analysis with remediation recommendations
- DORA compliance report generation
- Terraform/Prometheus integration
- Plugin system for custom scenarios
- Slack/PagerDuty notifications

**Who is it for?**
- SRE teams evaluating system resilience
- DevOps engineers planning capacity
- Platform teams validating architecture changes
- Compliance teams needing DORA evidence

**Try it now:**
```
pip install faultray
faultray demo --web
```

### First Comment (maker's comment)
Hi everyone! I'm Yutaro, an infrastructure engineer from Tokyo.

I built FaultRay because I was frustrated with chaos engineering tools that require production access. My team needed to evaluate "what happens if our DB goes down?" without actually breaking things.

FaultRay takes a fundamentally different approach: pure mathematical simulation. You describe your infrastructure in YAML (or import from Terraform), and FaultRay runs 150+ failure scenarios to find your weakest points.

The most unique feature is the 3-Layer Availability Limit Model — it mathematically proves that your architecture's theoretical maximum is, say, 6.65 nines (7 seconds of downtime per year), and that going higher would violate the laws of physics (speed of light limits failover time).

It's completely free and open source (MIT). I'd love your feedback!

- Live demo: https://faultray-demo.fly.dev/
- PyPI: pip install faultray
- GitHub: https://github.com/mattyopon/faultray

---

## Hacker News (Show HN)

### Title
Show HN: FaultRay – Zero-risk chaos engineering that proves your availability ceiling

### Text
I built FaultRay because existing chaos engineering tools (Gremlin, Chaos Monkey, AWS FIS) all inject real faults into real infrastructure. That's scary, expensive, and requires production access.

FaultRay takes a different approach: it models your infrastructure as a dependency graph and simulates 150+ failure scenarios entirely in memory. No agents, no sidecars, no risk.

What makes it unique:

1. **3-Layer Availability Limit Model** — mathematically proves your system's theoretical ceiling:
   - Software limit: 4.00 nines (Ethernet + GC pauses)
   - Hardware limit: 5.91 nines (InfiniBand + GC-free runtimes)
   - Theoretical limit: 6.65 nines (physics: speed of light limits failover)

2. **5 simulation engines** — Static (150+ scenarios), Dynamic (time-stepped with traffic), Ops (30-day operational sim), What-If (parameter sweeps), Capacity (growth forecasting)

3. **AI analysis** — identifies SPOFs, cascade amplifiers, and generates upgrade recommendations with estimated nines improvement

4. **DORA compliance** — auto-generates EU regulatory compliance reports

Tech stack: Python 3.11+, NetworkX, FastAPI, Typer, Pydantic

Try it:
```
pip install faultray
faultray demo --web
```

Live demo: https://faultray-demo.fly.dev/
GitHub: https://github.com/mattyopon/faultray

---

## Reddit r/devops & r/sre

### Title
[Tool] FaultRay: Simulate infrastructure failures without touching production — proves your availability ceiling mathematically

### Body
Hey r/devops,

I've been working on an open-source tool that takes a different approach to chaos engineering. Instead of injecting faults into real infrastructure, FaultRay simulates everything in memory.

You describe your infra in YAML or import from Terraform, and it runs 150+ failure scenarios (single failures, pairwise combinations, traffic spikes, DB-specific issues, cache stampedes, etc.) and tells you exactly what would break and how badly.

**The coolest feature**: It can prove your system's theoretical availability ceiling. For example, "your current architecture maxes out at 4.2 nines no matter what you do — to reach 5 nines, you need to add replicas here and circuit breakers there."

- Free & open source (MIT)
- `pip install faultray`
- Live demo: https://faultray-demo.fly.dev/
- GitHub: https://github.com/mattyopon/faultray

Would love feedback from fellow SREs!
