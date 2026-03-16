# FaultRay Terms of Service

> **DRAFT -- Not yet reviewed by legal counsel.**
> This document is a working draft and does not constitute a binding legal agreement until formally reviewed, approved, and published by qualified legal counsel.

**Effective Date:** [To be determined]
**Last Updated:** 2026-03-16

---

## 1. Description of Service

FaultRay ("the Service") is a zero-risk infrastructure chaos simulation platform provided by Yutaro Maeda and FaultRay Contributors ("we," "us," or "the Company"). The Service enables users to:

- Define infrastructure topologies using YAML, Terraform, or cloud provider integrations
- Run mathematical chaos simulations across multiple failure scenarios
- Analyze resilience scores, availability ceilings, and cascade failure risks
- Access simulation results through a CLI, REST API, or web dashboard

The Service is offered as:

- **FaultRay Open Source (MIT License):** A self-hosted, open-source tool available at no cost
- **FaultRay Cloud (SaaS):** A managed cloud service with additional features, offered under the subscription tiers described in Section 3

## 2. Account Registration and Usage Conditions

### 2.1 Eligibility

To use the Service, you must:

- Be at least 18 years old or the age of majority in your jurisdiction
- Provide accurate and complete registration information
- Maintain the security of your account credentials

### 2.2 Account Responsibilities

You are responsible for:

- All activity that occurs under your account
- Keeping your login credentials confidential
- Promptly notifying us of any unauthorized use of your account
- Ensuring that your use of the Service complies with all applicable laws and regulations

### 2.3 Acceptable Use

You agree not to:

- Use the Service to test, attack, or interfere with third-party infrastructure without authorization
- Reverse engineer, decompile, or disassemble any proprietary component of the Service
- Attempt to circumvent usage limits, rate limits, or access controls
- Use the Service for any unlawful purpose or in violation of any applicable regulations
- Resell, sublicense, or redistribute the SaaS platform without prior written consent

### 2.4 API Usage

API access is subject to rate limits as defined by your subscription tier. Exceeding these limits may result in temporary throttling or suspension of API access.

## 3. Pricing and Payment

### 3.1 Subscription Tiers

| Feature | **Free** | **Pro** | **Enterprise** |
|---------|----------|---------|----------------|
| Simulation scenarios | Up to 500 | Up to 5,000 | Unlimited |
| Simulation engines | Cascade only | All 5 engines | All 5 engines |
| Infrastructure components | Up to 10 | Up to 100 | Unlimited |
| Web dashboard | Basic | Full | Full + custom branding |
| API access | Limited | Full | Full + priority |
| Terraform integration | Read-only | Full | Full |
| Compliance reports | -- | SOC 2, ISO 27001 | SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR |
| Security feed | -- | Standard | Real-time + custom feeds |
| Support | Community | Email (48h SLA) | Dedicated (4h SLA) + Slack |
| SSO / SAML | -- | -- | Included |
| Multi-tenant | -- | -- | Included |
| SLA guarantee | -- | 99.9% | 99.99% |

### 3.2 Billing

- Pro and Enterprise subscriptions are billed monthly or annually, at the customer's choice
- Annual subscriptions receive a discount as specified on the pricing page
- All fees are quoted in USD unless otherwise specified
- Taxes (including consumption tax, VAT, and sales tax) are additional where applicable

### 3.3 Free Tier

The Free tier is provided at no cost and may be subject to usage limitations. We reserve the right to modify Free tier limits with 30 days' notice.

### 3.4 Refunds

- Monthly subscriptions: No refunds for partial months
- Annual subscriptions: Pro-rated refund available within the first 30 days of the subscription term
- Enterprise subscriptions: Refund terms as specified in the individual Enterprise agreement

### 3.5 Price Changes

We may modify pricing with at least 30 days' advance notice. Price changes will take effect at the start of the next billing cycle following the notice period.

## 4. Intellectual Property

### 4.1 Ownership

- The FaultRay software, including its source code, documentation, simulation engines, algorithms, trademarks, and trade dress, is owned by Yutaro Maeda and FaultRay Contributors
- The FaultRay open-source components are licensed under the MIT License
- Proprietary SaaS components (including but not limited to the multi-tenant dashboard, compliance engine, and enterprise features) are not covered by the MIT License and remain the exclusive property of the Company

### 4.2 User Content

- You retain all ownership rights to the infrastructure definitions, configuration files, and other data you upload to or create within the Service ("User Content")
- You grant us a limited, non-exclusive license to process your User Content solely for the purpose of providing the Service
- We will not use your User Content for training machine learning models, marketing purposes, or any purpose other than delivering the Service, unless you provide explicit consent

### 4.3 Feedback

Any suggestions, ideas, or feedback you provide regarding the Service may be used by us without restriction or obligation to you.

## 5. Data Handling

### 5.1 Infrastructure Definition Data

Infrastructure definitions you provide (YAML files, Terraform state, Prometheus configurations) are:

- Processed in memory during simulation and not persisted beyond the session (self-hosted / Free tier)
- Stored in encrypted form on our servers for Cloud tier users, subject to our [Privacy Policy](privacy-policy.md)
- Never shared with third parties without your explicit consent

### 5.2 Simulation Results

- Simulation results (resilience scores, findings, reports) are stored for your access according to your subscription tier's retention period
- Free tier: 7-day retention
- Pro tier: 90-day retention
- Enterprise tier: Custom retention as specified in your agreement

### 5.3 Data Location

- Cloud service data is processed and stored in data centers located in [to be specified]
- Enterprise customers may request specific data residency requirements

### 5.4 Data Export

You may export your data at any time through the CLI, API, or dashboard. We support export in JSON, YAML, HTML, and CSV formats.

### 5.5 Data Deletion

Upon account termination or at your request, we will delete your data within 30 days, except where retention is required by law.

## 6. Disclaimers

### 6.1 Simulation Results

**IMPORTANT:** FaultRay simulation results are provided for informational and planning purposes only. Specifically:

- Simulation results represent **mathematical models** and do not guarantee actual system behavior
- Resilience scores, availability ceilings, and risk assessments are **theoretical estimates** based on the model you provide
- The accuracy of results depends on the accuracy and completeness of the infrastructure definition you supply
- FaultRay does not test real infrastructure and cannot account for factors not represented in the model (e.g., undocumented dependencies, transient network conditions, human error)

### 6.2 No Warranty

THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE" WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT.

### 6.3 Limitation of Liability

TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL THE COMPANY BE LIABLE FOR:

- Any indirect, incidental, special, consequential, or punitive damages
- Any loss of profits, data, business, or goodwill
- Any damages arising from reliance on simulation results
- Any damages exceeding the total amount paid by you in the twelve (12) months preceding the claim

### 6.4 Indemnification

You agree to indemnify and hold harmless the Company from any claims, damages, or expenses arising from your use of the Service, your violation of these Terms, or your infringement of any third-party rights.

## 7. Service Interruption and Termination

### 7.1 Service Availability

- We strive to maintain high availability but do not guarantee uninterrupted access
- Scheduled maintenance will be announced at least 48 hours in advance
- SLA-covered downtime and credit provisions apply only to Pro and Enterprise tiers as defined in Section 3

### 7.2 Suspension

We may suspend your access to the Service if:

- You violate these Terms of Service
- Your account has unpaid balances exceeding 30 days
- Your use poses a security risk to the Service or other users
- Required by law or regulatory order

### 7.3 Termination by You

You may terminate your account at any time by:

- Using the account deletion feature in the dashboard
- Contacting support at support@faultray.com

### 7.4 Termination by Us

We may terminate the Service or your account with 90 days' written notice. In the event of termination:

- You will have 30 days to export your data
- Prepaid annual subscriptions will be refunded on a pro-rated basis
- Free tier accounts may be terminated with 30 days' notice

### 7.5 Effect of Termination

Upon termination:

- Your right to access the Service ceases immediately
- We will delete your data within 30 days, except where legally required to retain it
- Sections 4 (Intellectual Property), 6 (Disclaimers), 8 (Governing Law), and 9 (Dispute Resolution) survive termination

## 8. Governing Law

These Terms of Service shall be governed by and construed in accordance with the laws of Japan, without regard to its conflict of law provisions.

## 9. Dispute Resolution

### 9.1 Negotiation

The parties shall first attempt to resolve any dispute through good-faith negotiation within 30 days of written notice of the dispute.

### 9.2 Jurisdiction

Any dispute that cannot be resolved through negotiation shall be submitted to the exclusive jurisdiction of the Tokyo District Court (Tokyo Chiho Saibansho) as the court of first instance.

### 9.3 Language

In the event of any discrepancy between translations of these Terms, the English version shall prevail. Legal proceedings shall be conducted in Japanese unless otherwise agreed by both parties.

## 10. General Provisions

### 10.1 Modifications

We may update these Terms from time to time. Material changes will be communicated via email or in-app notification at least 30 days before taking effect. Continued use of the Service after the effective date constitutes acceptance of the modified Terms.

### 10.2 Severability

If any provision of these Terms is found to be unenforceable, the remaining provisions shall continue in full force and effect.

### 10.3 Entire Agreement

These Terms, together with the Privacy Policy and any applicable subscription agreement, constitute the entire agreement between you and the Company regarding the Service.

### 10.4 Assignment

You may not assign your rights or obligations under these Terms without our prior written consent. We may assign our rights and obligations without restriction.

### 10.5 Waiver

Failure to enforce any provision of these Terms shall not constitute a waiver of that provision.

## 11. Contact Information

For questions about these Terms of Service:

- **Email:** legal@faultray.com
- **Website:** [https://faultray.com](https://faultray.com)
- **Repository:** [https://github.com/mattyopon/faultray](https://github.com/mattyopon/faultray)

---

*DRAFT -- This document has not been reviewed by legal counsel. It is provided as a starting point and must be reviewed and approved by a qualified attorney before publication or enforcement.*
