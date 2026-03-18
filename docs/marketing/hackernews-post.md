# Hacker News Post — FaultRay

---

## Title Options (Show HN format, under 80 chars)

1. **Show HN: FaultRay – Run 2,000 failure scenarios on your terraform plan before apply**
   (79 chars)

2. **Show HN: FaultRay – Simulate infrastructure failures without touching production**
   (83 chars — slightly over, trim if needed)

3. **Show HN: FaultRay – Check terraform plan impact before apply, zero risk**
   (75 chars)

4. **Show HN: FaultRay – "what happens if my DB dies?" without killing your DB**
   (77 chars)

Recommended: **#1** or **#3**. Both are concrete, specific, and answer "what does this do?" immediately.

---

## Body Text

Have you ever run `terraform apply` and watched your production go down?

I have. We added a second availability zone, the plan looked fine, the code review passed, and then apply started tearing down the load balancer mid-traffic because of a dependency ordering issue nobody had modeled out. The cascade took 11 minutes to recover.

That incident is why I built FaultRay.

---

**What it does**

FaultRay reads your infrastructure definition (YAML, or imported directly from `terraform plan` / `tfstate`) and builds a dependency graph in memory. Then it simulates 2,000+ failure scenarios — single component failures, pairwise combinations, traffic spikes, cascade paths — and tells you what would break and how badly, before you touch anything in production.

The workflow I use now:

```bash
terraform plan -out=tfplan

faultray tf-plan tfplan          # analyze the planned changes
# or
faultray tf-import --dir .       # import current state

faultray simulate --json results.json

terraform apply                  # only if faultray is happy
```

That's the whole thing. No agents to install on hosts. No production access needed. Nothing runs in your cloud. It's pure in-memory simulation.

---

**What it catches**

- Single points of failure your plan introduces (e.g., removing a replica, consolidating subnets)
- Components whose failure cascades to total outage vs. degraded service
- Dependency cycles that create split-brain scenarios under partial failure
- Changes that reduce your theoretical availability ceiling (it models this as a number — "your current architecture maxes out at 4.2 nines regardless of what else you do")

---

**What it doesn't catch**

To be honest about the limitations: this is simulation, not real fault injection. The model is a graph of your declared dependencies plus some heuristics for component behavior. It won't catch:

- Bugs in your application code
- Races and timing issues that only appear under real load
- Failures in third-party services you didn't model
- Anything that requires observing actual runtime behavior

For that, you still want real chaos tooling (Gremlin, AWS FIS, etc.) in a staging environment. FaultRay is the check you run *before* that — especially before you apply changes to infrastructure that's already running.

It catches a lot of structural issues before they happen. It doesn't replace runtime testing.

---

**The availability ceiling model**

One feature I haven't seen elsewhere: FaultRay computes a theoretical maximum availability for your current architecture using a three-layer model:

```
Layer 3 (theoretical): 6.65 nines — physics limits failover speed
Layer 2 (hardware):    5.91 nines — your hardware's MTBF limits it here
Layer 1 (software):    4.00 nines — GC pauses, human error, deploys
```

If your SLO target is 99.999% but your architecture can physically reach 99.95%, you can spend six months tuning and still never close the gap. This tells you that before you start.

---

**Quick start**

```bash
pip install faultray
faultray demo               # run against a sample infrastructure
faultray demo --web         # with a web dashboard at localhost:8000
```

Or if you have a terraform directory:

```bash
faultray tf-import --dir ./terraform --output model.json
faultray simulate -m model.json
```

---

**Stack and license**

Python 3.11+, NetworkX for the dependency graph, FastAPI for the web dashboard, Typer for the CLI. BSL 1.1 (converts to Apache 2.0 in 2030).

GitHub: https://github.com/mattyopon/faultray
PyPI: https://pypi.org/project/faultray/

Happy to answer questions about the simulation model, the availability math, or how the terraform import works. Would genuinely appreciate any pushback on the approach — especially from people who've done real chaos engineering and think I'm missing something.
