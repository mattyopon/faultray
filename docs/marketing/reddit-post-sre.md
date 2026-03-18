# Reddit Post — r/sre

---

## Title Options

1. **Tool for proving availability ceilings mathematically before architecture changes — complement to chaos injection, not replacement**

2. **Pre-change resilience analysis: can you actually hit your SLO target with your current architecture?**

3. **We use this alongside fault injection — catches structural issues before they need a real experiment**

Recommended: **#2** — SRE-relevant problem framing, leads with the question practitioners actually ask.

---

## Body Text

Hey r/sre,

I want to share a tool I've been using for pre-change resilience analysis and get some honest feedback from people who do real chaos engineering. I'm going to be upfront about what it is and what it isn't, because this community has seen a lot of "chaos engineering" tools that aren't.

**What it is**

FaultRay is a mathematical simulation tool. It reads your infrastructure definition (YAML or imported from Terraform/tfstate), builds a dependency graph using NetworkX, and exhaustively simulates failure combinations in memory. 2,000+ scenarios: single-component failures, pairwise failures, traffic patterns, cascade chains.

The output is:
- A resilience score (0-100)
- A breakdown of what fails under each scenario
- Identified SPOFs and cascade amplifiers
- A theoretical availability ceiling for the current architecture

**The availability ceiling model**

This is the part I find most useful for SLO work. FaultRay computes a three-layer upper bound:

```
Layer 3 (theoretical):  6.65 nines (99.99997%)
  — Speed of light limits your minimum failover time
Layer 2 (hardware):     5.91 nines (99.999%)
  — Your hardware's MTBF and redundancy level cap it here
Layer 1 (software):     4.00 nines (99.99%)
  — GC pauses, rolling deploys, human error bring it here
```

The useful insight: if your architecture's Layer 1 ceiling is 3.8 nines and your SLO target is 4 nines, no amount of operational excellence closes that gap. You need architectural changes. This gives you that answer before you spend three quarters tuning the wrong things.

**What it is NOT — and why I'm being explicit about this**

This is not fault injection. It doesn't touch your production environment. It doesn't test your application's actual behavior under failure. It doesn't tell you whether your circuit breakers, retries, or fallback logic actually work.

The chaos engineering community (correctly) emphasizes that real experiments on real systems are the gold standard. A simulation that says "your database is a SPOF" is not the same as actually killing the database and watching what happens.

FaultRay's model is only as good as the dependency graph it can extract from your IaC files. If your app has a hidden coupling that isn't expressed in Terraform, FaultRay doesn't know about it.

**Where it fits alongside real chaos engineering**

The way I use it:

1. **Pre-change analysis**: Before making an infrastructure change, run FaultRay to see if the change introduces new failure modes. Much cheaper than running a full chaos experiment for every PR.

2. **Architecture review**: Before building, prove whether the proposed architecture can even reach the target SLO. Catch "this topology cannot hit 99.99%" before six months of engineering.

3. **Hypothesis generation for real experiments**: FaultRay's cascade analysis tells you which components are highest-risk. Use that to prioritize what you actually inject faults into with your real chaos tooling.

4. **Regulated environments**: Some environments (finance, healthcare) can't run real fault injection against production. Mathematical simulation isn't a perfect substitute but it's better than nothing.

**CI integration for infrastructure changes**

We gate infrastructure PRs on resilience score — if a change drops the score below threshold or introduces a CRITICAL finding, the PR fails:

```yaml
- name: FaultRay pre-deploy check
  run: |
    faultray tf-import --dir ./terraform --output model.json
    faultray evaluate -m model.json --threshold 70
```

Exit code 2 on critical findings, exit code 3 on below-threshold.

**Honest limitations**

- Simulation, not injection. Won't catch runtime behavior bugs.
- Model quality depends on IaC completeness. Undeclared dependencies are invisible to it.
- Availability ceiling math uses standard MTBF models — your real hardware may differ.
- Doesn't model application-layer fallbacks (circuit breakers, retry budgets) unless you declare them.

**Links**

```bash
pip install faultray
faultray demo
```

GitHub: https://github.com/mattyopon/faultray
PyPI: https://pypi.org/project/faultray/

Free and open source (BSL 1.1, converts to Apache 2.0 in 2030).

---

**Questions for this community**

1. Do you use any static/pre-change analysis before running actual chaos experiments? If so, what does that look like?
2. The availability ceiling model — is this something you'd find useful in an architecture review, or is it too abstract to be actionable?
3. What's the biggest thing this kind of tool gets wrong that I should be thinking about?

I'm genuinely interested in the pushback from people who do real fault injection. The simulation approach has real limits and I don't want to oversell it.
