# Day 1: Welcome to FaultRay

**Subject:** Welcome to FaultRay — let's estimate your infrastructure's resilience

**From:** hello@faultray.com
**To:** {{ user.email }}
**Trigger:** Immediately after account creation

---

Hi {{ user.name || "there" }},

Welcome to **FaultRay** — the pre-deployment resilience simulation platform (research prototype) that lets you estimate your system's structural availability ceiling from declared topology, without touching production.

You're now on the **{{ plan.name }}** plan. Here's what you can do right now:

---

## Get Started in 3 Steps

### Step 1 — Install the CLI

```bash
pip install faultray
```

### Step 2 — Define your topology

Create `infra.yaml` with your services:

```yaml
topology:
  name: my-saas-platform
  services:
    - name: api-gateway
      replicas: 3
      dependencies: [auth, database]
    - name: database
      replicas: 2
```

### Step 3 — Run your first simulation

```bash
faultray run --topology infra.yaml
```

You'll get an availability score, failure heatmap, and N-Layer breakdown in seconds.

---

## Explore the Dashboard

Log in to your dashboard to:

- **Run simulations** with 2,000+ pre-built chaos scenarios
- **View DORA metrics** and compliance status
- **Analyze failure modes** with our AI Advisor

👉 [Open your Dashboard](https://faultray.com/dashboard)

---

## Need Help?

- **Documentation:** [github.com/mattyopon/faultray/blob/main/docs/](https://github.com/mattyopon/faultray/blob/main/docs/)
- **Book a demo:** [faultray.com/contact](https://faultray.com/contact)
- **Email support:** hello@faultray.com

We're excited to have you. Let's make your infrastructure bulletproof.

— The FaultRay Team

---

*You're receiving this because you signed up at faultray.com.*
*[Unsubscribe](https://faultray.com/unsubscribe?token={{ unsubscribe_token }}) | [Privacy Policy](https://faultray.com/privacy)*
