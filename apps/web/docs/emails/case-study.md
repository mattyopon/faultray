# Day 7: Case Study

**Subject:** How a fintech team discovered a hidden single point of failure

**From:** hello@faultray.com
**To:** {{ user.email }}
**Trigger:** 7 days after signup

---

Hi {{ user.name || "there" }},

Here's a story we hear a lot.

---

## "We thought we had 99.9% availability. We had 99.1%."

A 30-person fintech SRE team was preparing for their Series B due diligence. Their infrastructure looked solid on paper:

- 3-region AWS deployment
- Auto-scaling EC2 groups
- RDS Multi-AZ with read replicas
- CloudFront CDN

Their internal estimate: **99.95% availability**.

Then they ran FaultRay.

---

### What FaultRay Found

**N-Layer Breakdown:**

| Layer | Availability | Nines |
|-------|-------------|-------|
| Hardware | 99.99988% | 5.91 |
| **Software** | **99.1%** | **2.05 ← binding** |
| Theoretical | 99.999978% | 6.65 |
| Operations | 99.99937% | 5.20 |
| External | 99.9986% | 4.85 |

**System Ceiling: 99.1% (software layer is binding)**

The software layer score was dragged down by a single synchronous call to a third-party KYC API — with no circuit breaker and a 30-second timeout. When the KYC API slowed down (which happened 2-3x per month), the entire payment flow stalled.

---

### The Fix

FaultRay's AI Advisor suggested:

1. Add a circuit breaker (Resilience4j) with a 5-second timeout
2. Queue KYC verification asynchronously
3. Return "pending" status to users and complete verification in background

**Time to implement:** 2 days  
**After fix:** Software layer → 99.9991% (4.05 nines)  
**System ceiling:** Now bounded by external dependencies at 99.9986%

---

### The Due Diligence Win

The team presented their FaultRay analysis in their Series B technical review. The slide showed before/after availability ceilings with mathematical proof. Investors asked zero follow-up questions about infrastructure reliability.

---

## Ready to Find Your Hidden SPOFs?

Run a simulation on your real infrastructure today:

👉 [Open Simulator](https://faultray.com/simulate)

If you're on the **Free plan** and want access to AI-powered analysis and DORA reports, consider upgrading to **Pro** — 14-day free trial, no credit card required to start.

👉 [View Pricing](https://faultray.com/pricing)

— The FaultRay Team

---

*[Unsubscribe](https://faultray.com/unsubscribe?token={{ unsubscribe_token }}) | [Privacy Policy](https://faultray.com/privacy)*
