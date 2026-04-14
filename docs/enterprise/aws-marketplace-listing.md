# AWS Marketplace Listing — FaultRay

Prepared: 2026-03-17
Status: DRAFT (not submitted)

---

## 1. Product Title

**FaultRay — Pre-Deployment Infrastructure & AI Agent Resilience Simulation (Research Prototype)**

### Short Description (max 200 characters)

Simulate thousands of infrastructure failure scenarios from declared topology without touching production. Estimate your availability ceiling via a model-based approach. No production fault injection. No sidecars. Research prototype.

---

## 2. Full Description (AWS Marketplace Format)

### Overview

FaultRay is a research-prototype pre-deployment resilience simulation platform that models infrastructure failures from your declared topology — without injecting faults into production systems. Unlike runtime chaos tools (Gremlin, Steadybit, AWS FIS) that inject real faults into live systems, FaultRay models your declared dependency graph in memory, runs thousands of failure scenarios across 5 simulation engines, and estimates your system's structural availability ceiling using a patented 3-Layer Availability Limit Model. Result accuracy depends on how completely your topology is declared; FaultRay complements runtime chaos engineering rather than replacing it.

### How It Works

FaultRay ingests your infrastructure topology from YAML definitions, Terraform state files, Prometheus targets, or live AWS account scanning (EC2, RDS, ElastiCache, ELB/ALB/NLB, S3, Route 53, CloudFront, ECS/EKS, Lambda, SQS/SNS). It builds a NetworkX-powered dependency graph, then executes simulations across five engines:

1. **Cascade Engine** — Models fault propagation through dependency graphs, identifying single points of failure, compound failures, and cascade paths.
2. **Dynamic Engine** — Time-stepped simulation with 10 traffic pattern models (DDoS, diurnal, flash crowd, growth trend, etc.) over configurable durations.
3. **Ops Engine** — Long-running operational simulation (days to weeks) with SLO tracking, incident generation, and deployment event modeling.
4. **What-If Engine** — Parameter sweep analysis for fault tolerance sensitivity across multiple dimensions.
5. **Capacity Engine** — Growth forecasting with resource exhaustion prediction, HA guards (min 2 replicas), and quorum guards (min 3 for clustered systems).

### AI Agent Resilience (v11.0)

FaultRay extends chaos simulation to AI agent systems. It models agents, LLM endpoints, tool services, and orchestrators as first-class components in the dependency graph. Seven agent-specific fault types are simulated: hallucination, context overflow, LLM rate limiting, token exhaustion, tool failure, agent loops, and prompt injection. Cross-layer analysis detects when infrastructure failures (e.g., database outage) cascade into agent hallucinations.

### Compliance & Governance

Built-in research-prototype mapping for SOC 2 Type II, ISO 27001, PCI DSS, DORA, HIPAA, and GDPR. Generates evidence drafts from simulation results with gap analysis and remediation recommendations. Outputs are intended for internal pre-audit review and design-time analysis — **not** a substitute for audit-certified compliance evidence; independent legal and technical review is required before any formal compliance use.

### Deployment

Available as a Python CLI tool (`pip install faultray`), Docker container, or FastAPI-powered web dashboard with D3.js interactive dependency graphs.

---

## 3. Highlights (Bullet Points)

- **No production fault injection** — Model-based simulation with no runtime agents, sidecars, or fault injection. Runs entirely in memory from declared topology.
- **Thousands of auto-generated scenarios** — 30 categories of failure scenarios generated from your declared topology, including compound and triple failures.
- **3-Layer Availability Limit Model** — Model-based estimation of your system's structural availability ceiling; accuracy depends on topology fidelity.
- **5 integrated simulation engines** — Cascade, Dynamic, Ops, What-If, and Capacity engines for structural resilience analysis.
- **AI Agent Resilience** — Model agent hallucinations, LLM rate limits, prompt injection, and cross-layer cascades for AI/ML workloads.
- **AWS native integration** — Auto-scan EC2, RDS, ElastiCache, ELB, S3, Route 53, CloudFront, ECS/EKS, Lambda, SQS/SNS.
- **Terraform & Prometheus** — Import from tfstate, analyze tf plan impact, auto-discover from Prometheus targets.
- **Research-prototype compliance mapping** — SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR research mapping with evidence-draft generation (not audit-certified).

---

## 4. Product Categories

- **Primary**: DevOps > Testing
- **Secondary**: Security > Compliance
- **Additional**:
  - Infrastructure Software > Infrastructure as Code
  - Machine Learning > ML Operations
  - DevOps > Monitoring

---

## 5. Pricing Tiers

### Tier 1: Free (Community Edition)

- **Price**: $0/month
- **Includes**:
  - CLI tool with all 5 simulation engines
  - Up to 20 components per topology
  - YAML infrastructure loading
  - HTML report generation
  - Community support (GitHub Issues)

### Tier 2: Pro

- **Price**: $499/month (SaaS subscription via AWS Marketplace)
- **Includes**:
  - Everything in Free
  - Unlimited components
  - Terraform state import & plan analysis
  - Prometheus auto-discovery
  - AWS account scanning (all supported services)
  - AI Agent Resilience simulation (PREDICT / ADOPT / MANAGE)
  - Web dashboard with D3.js interactive graphs
  - Security feed integration (CISA, NVD, CVE auto-scenarios)
  - Cost Impact Engine & Predictive Engine
  - Multi-Region DR simulation
  - REST API & Python SDK access
  - Email support (48h SLA)

### Tier 3: Enterprise

- **Price**: $2,499/month (SaaS subscription, or custom annual contract via Private Offer)
- **Includes**:
  - Everything in Pro
  - Multi-tenant dashboard with OAuth2 (GitHub/Google) + RBAC
  - Compliance Engine (SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR)
  - CI/CD integration (GitHub Actions marketplace action)
  - Slack & PagerDuty notifications
  - SARIF export for security tool integration
  - SSO / SAML integration
  - Dedicated support (24h SLA, dedicated Slack channel)
  - Custom SLA with uptime guarantee
  - Annual contract & volume discounts available via AWS Private Offers

### Pricing Model Recommendation

**SaaS Contracts with consumption-based dimensions:**
- Base subscription fee (monthly or annual)
- Additional dimension: number of components scanned (for usage-based billing flexibility)

---

## 6. Support Information

### Support Channels

| Tier | Channel | Response SLA |
|------|---------|-------------|
| Free | GitHub Issues | Best effort |
| Pro | Email (support@faultray.com) | 48 business hours |
| Enterprise | Dedicated Slack + Email | 24 business hours |
| Enterprise (Critical) | Phone escalation | 4 business hours |

### Documentation

- Getting Started Guide: https://faultray.com/docs/getting-started
- API Reference: https://faultray.com/docs/api
- CLI Reference: https://faultray.com/docs/cli/commands
- AWS Integration Guide: https://faultray.com/docs/integrations/aws

### Refund Policy

AWS Marketplace standard refund policy applies. Free tier available for evaluation with no commitment.

---

## 7. Technical Requirements

### Runtime Requirements

- Python 3.11+ (CLI/SDK)
- Docker (container deployment)
- No additional infrastructure required — runs in memory

### AWS Integration Requirements

- IAM role with read-only access to scanned services (ec2:Describe*, rds:Describe*, etc.)
- Boto3 credentials configured (AWS CLI profile, environment variables, or IAM role)
- Optional: Terraform state file access, Prometheus endpoint access

### Network Requirements

- Outbound HTTPS (443) for:
  - AWS API calls (infrastructure scanning)
  - Security feed updates (CISA, NVD)
  - LLM API endpoints (if using AI-powered analysis)
- Web dashboard: configurable port (default 8000)

### Supported Platforms

- Linux (x86_64, ARM64)
- macOS (Intel, Apple Silicon)
- Windows (WSL2 recommended)
- Docker (official image available)

### Compatibility

- Terraform 1.0+
- Prometheus 2.x
- Kubernetes 1.24+ (for K8s scanning)
- AWS regions: all commercial regions supported

---

## 8. Seller Registration Checklist

### Documents & Information Required

- [ ] AWS account in good standing
- [ ] Business entity registration in eligible jurisdiction (US, EU, Japan, UK, Australia, etc.)
- [ ] Tax documentation (W-9 for US / W-8 for non-US sellers)
- [ ] US-based bank account accepting USD disbursements (or eligible jurisdiction bank)
- [ ] Bank account verification completed
- [ ] Company legal name, address, website
- [ ] Valid non-alias email address for seller account
- [ ] IAM role configured (not root credentials) for Management Portal access
- [ ] Product logo (120x120 and 250x250 PNG)
- [ ] EULA or standard AWS contract selection
- [ ] Privacy policy URL
- [ ] Support contact information

### KYC Requirements (if applicable)

- Required for selling to EMEA customers
- Required for Republic of Korea transactions
- Required if using UK-based bank accounts

---

## 9. AWS Marketplace Fee Structure (as of January 2024)

| Listing Type | Fee |
|-------------|-----|
| SaaS (public offer) | 3% |
| SaaS (private offer < $1M) | 3% |
| SaaS (private offer $1M-$10M) | 2% |
| SaaS (private offer >= $10M) | 1.5% |
| SaaS (all renewals) | 1.5% |
| Server/AMI (public) | 20% |
| Container (public) | 20% |
| Channel Partner Private Offer | +0.5% uplift |

**FaultRay recommendation**: SaaS listing at 3% fee (vs. 20% for AMI/Container).

---

## 10. Approval Timeline Estimate

| Phase | Duration |
|-------|----------|
| Seller account setup & verification | 3-5 business days |
| SaaS integration (Entitlement/Subscription API) | 2-4 weeks (engineering) |
| Product listing submission & review | 1-5 business days (AI-powered review can be 30 min) |
| End-to-end (setup to live) | 4-8 weeks typical |

---

## 11. Listing Type Analysis: SaaS vs AMI vs Container

### Recommendation: SaaS Listing

For FaultRay, **SaaS** is the optimal listing type. Here is the analysis:

### SaaS (RECOMMENDED)

| Factor | Assessment |
|--------|-----------|
| **Fee** | 3% (vs 20% for AMI/Container) |
| **Architecture fit** | FaultRay is a CLI + FastAPI web server. SaaS allows users to subscribe and access via faultray.com or API |
| **User experience** | Single subscription, instant access, no EC2 instance management |
| **Updates** | Centrally managed — users always get latest version |
| **Multi-tenancy** | Already supported (OAuth2, RBAC, API keys) |
| **Billing flexibility** | Supports SaaS contracts + consumption-based pricing |
| **AWS spend commitment** | Counts toward customer AWS spend commits if deployed on AWS |
| **"Deployed on AWS" badge** | Achievable if FaultRay SaaS backend runs entirely on AWS |

### AMI (NOT recommended)

| Factor | Assessment |
|--------|-----------|
| **Fee** | 20% — significantly higher |
| **Architecture fit** | Poor — FaultRay is a Python CLI tool, not a traditional server application that needs a dedicated EC2 instance |
| **User experience** | Customer must launch/manage EC2 instance, configure security groups, handle updates |
| **Updates** | Customer must update AMI manually |
| **Maintenance** | Seller must maintain AMI across regions and instance types |
| **Use case** | Better suited for database appliances, firewalls, or monolithic server applications |

### Container (NOT recommended for primary listing)

| Factor | Assessment |
|--------|-----------|
| **Fee** | 20% — same as AMI |
| **Architecture fit** | Partial fit — FaultRay has a Docker image, but the 20% fee makes this inferior to SaaS |
| **User experience** | Customer deploys to ECS/EKS, more DevOps overhead |
| **Updates** | Better than AMI (container pulls), but still customer-managed |
| **Consideration** | Could be a secondary listing for customers who require on-premises/VPC deployment |

### Decision Matrix

| Criterion | Weight | SaaS | AMI | Container |
|-----------|--------|------|-----|-----------|
| Listing fee | 30% | 10 | 2 | 2 |
| Architecture fit | 25% | 9 | 3 | 7 |
| User experience | 20% | 9 | 4 | 5 |
| Update management | 15% | 10 | 3 | 7 |
| Enterprise flexibility | 10% | 8 | 6 | 7 |
| **Weighted Score** | | **9.35** | **3.25** | **5.10** |

**Conclusion**: SaaS listing is the clear winner for FaultRay. The 3% fee (vs 20%), natural SaaS architecture (FastAPI web server + CLI), existing multi-tenancy support, and centralized update management all favor this approach. A Container listing could be considered as a future secondary option for customers with strict data-residency requirements.

---

## 12. Technical Integration Requirements (SaaS)

To list as SaaS on AWS Marketplace, FaultRay must integrate:

1. **AWS Marketplace Metering Service** — Report usage (e.g., components scanned) for consumption-based billing
2. **AWS Marketplace Entitlement Service** — Verify customer subscription tier and entitlements
3. **SaaS Customer Onboarding** — Handle registration redirect from AWS Marketplace to faultray.com
4. **AWS SaaS Subscription API** — Process subscribe/unsubscribe lifecycle events via SNS notifications

### Estimated Engineering Effort

| Task | Effort |
|------|--------|
| Metering Service integration | 3-5 days |
| Entitlement Service integration | 2-3 days |
| Customer onboarding flow | 3-5 days |
| SNS lifecycle event handling | 2-3 days |
| Testing & validation | 3-5 days |
| **Total** | **2-3 weeks** |

---

## Sources

- [AWS Marketplace Seller Eligibility](https://docs.aws.amazon.com/marketplace/latest/userguide/seller-eligibility.html)
- [AWS Marketplace Listing Fees](https://docs.aws.amazon.com/marketplace/latest/userguide/listing-fees.html)
- [SaaS Product Guidelines](https://docs.aws.amazon.com/marketplace/latest/userguide/saas-guidelines.html)
- [Getting Started as a Seller](https://docs.aws.amazon.com/marketplace/latest/userguide/user-guide-for-sellers.html)
- [AWS Marketplace Listing Requirements Checklist 2025](https://www.awssome.io/blog/aws-marketplace-listing-requirements-checklist-2025)
- [Complete Guide to AWS Marketplace (2026)](https://clazar.io/guides/aws-marketplace)
- [How to List SaaS on AWS Marketplace (2025)](https://labra.io/how-to-list-your-saas-on-aws-marketplace-step-by-step-guide-for-2025/)
- [Cloud Marketplace Fees 2025](https://labra.io/cloud-marketplace-fees-2025-aws-microsoft-azure-google-cloud-platform-revenue-shares-and-cost-saving-tips/)
- [AWS Marketplace Solution Types](https://invisory.co/resources/blog/aws-marketplace-solution-types-ami-container-and-more/)
