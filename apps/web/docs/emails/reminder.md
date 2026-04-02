# Day 3: First Simulation Reminder

**Subject:** Have you run your first simulation yet?

**From:** hello@faultray.com
**To:** {{ user.email }}
**Trigger:** 3 days after signup, only if user has NOT run a simulation yet
**Condition:** `simulation_count == 0`

---

Hi {{ user.name || "there" }},

You signed up for FaultRay 3 days ago — but we haven't seen your first simulation yet.

That's okay! It takes less than 5 minutes. Here's the quickest path:

---

## The Fastest Way to Your First Result

If you don't have an `infra.yaml` yet, start with our built-in demo:

```bash
pip install faultray
faultray demo
```

This runs 2,048 chaos scenarios against a sample e-commerce architecture and shows you:

- **Availability Ceiling:** 99.9991% (4.05 nines)
- **Binding Layer:** Software (the weakest link)
- **Top 5 failure modes** with remediation suggestions

No configuration required.

---

## Or Try the Web Simulator

Don't want to use the CLI? Use the interactive web simulator:

👉 [Try the Simulator](https://faultray.com/simulate)

Upload a topology file or paste YAML directly. Results in under 10 seconds.

---

## What Teams Discover in Their First Run

Most teams find that:

1. Their **assumed availability** (e.g., 99.9%) doesn't match the **simulated ceiling**
2. A single under-replicated service is the binding layer bringing the whole system down
3. Simple fixes (adding a replica, adding a cache) can move from 3 nines to 4 nines

This is exactly why we built FaultRay — to surface these issues before your customers discover them.

---

Questions? Just reply to this email — we read every message.

— The FaultRay Team

---

*[Unsubscribe](https://faultray.com/unsubscribe?token={{ unsubscribe_token }}) | [Privacy Policy](https://faultray.com/privacy)*
