# Tweet Thread — FaultRay

---

## Thread (5-7 tweets)

---

**Tweet 1 — Hook (the problem)**

Have you ever run `terraform apply` and watched production go down?

Added a second AZ, plan looked fine, apply started tearing down the load balancer mid-traffic. 11 minutes to recover.

That incident is why I built FaultRay.

---

**Tweet 2 — The gap in the current workflow**

`terraform plan` shows you *what* changes.

It doesn't show you *what that change does to your system's failure behavior.*

Single points of failure. Cascade paths. Replicas silently removed. Dependency ordering that creates a 90-second outage window.

All invisible until 3am.

---

**Tweet 3 — The solution: one command before apply**

Now I run this before every infrastructure change:

```
faultray tf-plan tfplan
```

It reads the plan, builds a dependency graph, and simulates 2,000+ failure scenarios in memory. Nothing touches production. No agents. No cloud access.

Takes about 3 seconds.

---

**Tweet 4 — Demo output (describe what the screenshot would show)**

Output looks like this:

```
╭────── FaultRay Simulation Report ──────╮
│ Resilience Score: 58/100               │
│ Scenarios tested: 2,147                │
│ Critical: 3  Warning: 14  Passed: 133  │
╰────────────────────────────────────────╯

CRITICAL: aws_db_instance.primary
  Replicas removed by this change: 1 → 0
  Cascade: api_servers → db (total outage)
  Availability ceiling reduced: 4.1 → 3.7 nines
```

That "CRITICAL" caught a cost-optimization change that would have caused a full outage during the replace window.

---

**Tweet 5 — It's also useful for SLO honesty**

FaultRay also computes your architecture's theoretical availability ceiling:

```
Software limit:    4.00 nines (where you probably are)
Hardware limit:    5.91 nines (what your hardware allows)
Theoretical limit: 6.65 nines (physics ceiling)
```

If your SLO target is 99.999% but your architecture tops out at 99.95%, you can't engineer your way there without changing the architecture.

No other tool tells you this.

---

**Tweet 6 — CI integration**

We added it to our GitHub Actions pipeline. Every infrastructure PR now runs resilience simulation. PRs that introduce critical findings or drop below our score threshold don't merge.

The GitHub Action takes ~3 seconds and comments the score directly on the PR.

One yaml block, no new infrastructure, no agents.

---

**Tweet 7 — CTA**

FaultRay is open source and free.

```
pip install faultray
faultray demo
```

GitHub: https://github.com/mattyopon/faultray

Fair warning: it's simulation, not real fault injection. It won't catch everything. But it catches a lot of structural problems before they become incidents.

---

## Notes for Posting

- Post tweets 1-7 as a thread, replying to each previous tweet
- Tweet 4 is the best candidate for an actual screenshot — run `faultray simulate` against a realistic infra.yaml and capture the terminal output
- If you have a GitHub Action running, a screenshot of the PR comment (resilience score + findings summary) performs well
- Thread performs best on Tuesday/Wednesday 9-11am EST or 6-8pm EST
- Hashtags (use sparingly, 1-2 max): `#devops` `#terraform` — avoid `#chaosengineering` as primary tag given the positioning pivot
- Pin a reply with the GitHub link once the thread gets traction
