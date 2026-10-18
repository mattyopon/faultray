# Day 14: Pro Trial Offer

**Subject:** Your 2-week FaultRay trial — what have you discovered?

**From:** hello@faultray.com
**To:** {{ user.email }}
**Trigger:** 14 days after signup
**Variants:**
  - A: User has run simulations → highlight value seen, offer upgrade
  - B: User has not run simulations → offer a live onboarding call

---

## Variant A — User has run at least 1 simulation

**Subject:** You've run {{ simulation_count }} simulations — ready to unlock everything?

---

Hi {{ user.name || "there" }},

You've been using FaultRay for 2 weeks and run **{{ simulation_count }} simulation(s)**. That's a great start.

Here's what Pro unlocks that you don't have yet:

| Feature | Free | Pro |
|---------|------|-----|
| Simulations / month | 5 | 100 |
| Components | 5 | 50 |
| DORA report export (PDF) | — | ✓ |
| AI-powered root cause analysis | — | ✓ |
| 99.9% Uptime SLA | — | ✓ |
| Email support (24h) | — | ✓ |

---

### Special Offer: Annual Plan Save 20%

| Plan | Monthly | Annual (20% off) |
|------|---------|-----------------|
| Pro | $299/mo | $239/mo (billed $2,869/yr) |

[**Upgrade to Pro — Start Free Trial →**](https://faultray.com/pricing)

No commitment. Cancel anytime. Your existing simulations carry over.

---

## Variant B — User has NOT run a simulation

**Subject:** 2 weeks in — let's get you your first result together

---

Hi {{ user.name || "there" }},

It's been 2 weeks since you joined FaultRay, and we noticed you haven't run a simulation yet.

Life gets busy. We get it.

That's why we're offering a **free 20-minute onboarding call** where we'll:

1. Help you define your first topology file
2. Run a live simulation against your architecture
3. Walk you through the results together

No sales pitch. Just getting you to value, fast.

👉 [Book a Free Onboarding Call](https://faultray.com/contact)

---

### Or Try Our Quickstart Template

If you'd rather go at your own pace, download a ready-made topology template for your stack:

- [AWS 3-tier web app template](https://github.com/mattyopon/faultray/blob/main/examples/aws-3tier.yaml)
- [Kubernetes microservices template](https://github.com/mattyopon/faultray/blob/main/examples/k8s-microservices.yaml)
- [Single-region startup template](https://github.com/mattyopon/faultray/blob/main/examples/startup-simple.yaml)

Run it in under 2 minutes:

```bash
pip install faultray
curl -O https://raw.githubusercontent.com/mattyopon/faultray/main/examples/aws-3tier.yaml
faultray run --topology aws-3tier.yaml
```

---

We're rooting for you. Let us know how we can help.

— The FaultRay Team

---

*Questions? Just reply to this email.*
*[Unsubscribe](https://faultray.com/unsubscribe?token={{ unsubscribe_token }}) | [Privacy Policy](https://faultray.com/privacy) | [Terms of Service](https://faultray.com/terms)*
