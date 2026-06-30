# FaultRay — Procurement & Vendor-Risk Pack (DORA Resilience Evidence Sprint)

## 1. Security & Compliance One-Pager

FaultRay provides a **DORA pre-audit infrastructure resilience simulator** for financial institutions preparing evidence for digital operational resilience reviews. The **DORA Resilience Evidence Sprint** is a fixed-scope, 5-business-day engagement that produces a resilience evidence pack for **one critical service**.

The Sprint is designed to be procurement-light and low-friction: FaultRay uses only a **sanitized topology/dependency description supplied by the client**. FaultRay does **not** connect to production, does **not** scan systems, does **not** require credentials, and does **not** process PII, secrets, or customer records.

| Attribute | Value |
|---|---|
| Service | DORA Resilience Evidence Sprint |
| Purpose | Decision-support and pre-audit preparation for one critical service |
| Duration | 5 business days |
| Fee | $2,500 total; 50% upfront, 50% on delivery |
| Operator model | Solo founder / single-operator delivery model |
| Processing model | In-memory dependency/fault-injection simulation using sanitized topology supplied by the client |
| Production access | None. FaultRay does not connect to, scan, or access production systems for the Sprint |
| Data accepted | Sanitized architecture, dependency, service, third-party, and resilience metadata only |
| Data not accepted | No PII, no end-customer records, no live production data, no credentials, no secrets, no tokens, no private keys |
| Hosting & region posture | Engagement work can be performed on EU-based infrastructure and/or locally, as agreed before kickoff |
| Encryption in transit | TLS used for web, application, and file-transfer channels where applicable |
| Encryption at rest | Sanitized engagement files are stored in encrypted cloud storage or encrypted local storage where used |
| Access controls | Single-operator access model; least-privilege access; MFA enabled on core business, development, and hosting tooling where supported |
| Secrets handling | Client secrets are not accepted; FaultRay operational secrets, where used, are stored in protected tooling or provider-managed secret/configuration facilities |
| Audit integrity | Evidence packs support a tamper-evident audit chain using HMAC-SHA256 chain hashing so pack integrity can be verified |
| Logging / evidence trail | Scenario assumptions, model inputs, simulation outputs, and integrity metadata can be included in the evidence pack |
| Retention & deletion | Sanitized inputs and working files deleted on request or within 30 days after delivery unless otherwise agreed in writing |
| Privacy / DPA | Draft privacy policy / DPA available at `/legal/privacy-policy`; enterprise DPA available on request; draft pending legal review |
| SOC 2 | Not certified — controls described below / on roadmap |
| ISO 27001 | Not certified — controls described below / on roadmap |
| PCI DSS | Not certified — no cardholder data accepted |
| Third-party security certifications | Not certified — controls described below |
| Penetration test attestation | None currently — on roadmap / available on request when performed |
| Insurance | No stated insurance currently |

**Procurement summary:** This is a small, fixed-price, short-duration, non-invasive engagement with no production access, no system integration, no PII, no credentials, and no customer records.

---

## 2. Vendor Security Questionnaire (SIG-lite / DDQ) — Pre-Filled

| # | Question | Answer |
|---:|---|---|
| 1 | What is FaultRay? | FaultRay is a DORA pre-audit infrastructure resilience simulator that helps produce a resilience evidence pack for one critical service. |
| 2 | What engagement is being purchased? | The DORA Resilience Evidence Sprint: fixed scope, 5 business days, $2,500 total, 50% upfront and 50% on delivery. |
| 3 | What is the company / operating model? | FaultRay is operated by a solo founder. Controls are process-based and single-operator; no headcount or large-team controls are implied. |
| 4 | What data does FaultRay process? | Sanitized topology and dependency metadata supplied by the client, such as service components, dependencies, failure scenarios, RTO/RPO assumptions, and third-party dependency notes. |
| 5 | Does FaultRay process PII? | No end-customer PII is accepted. Minimal business-contact details for engagement coordination may be processed. |
| 6 | Does FaultRay process customer records or regulated production data? | No. Customer records, transaction data, account data, claims data, trading data, policy data, production logs, and live data are out of scope and must not be provided. |
| 7 | Does FaultRay require production access? | No. FaultRay does not connect to, scan, or access production systems for the Sprint. |
| 8 | Does FaultRay require credentials, secrets, keys, or tokens? | No. Credentials, passwords, API tokens, private keys, certificates, and other secrets are not accepted. |
| 9 | How does the simulator work? | FaultRay models the sanitized topology in memory and runs dependency/fault-injection simulations against that model. |
| 10 | Is any agent, connector, scanner, or integration installed? | No. The Sprint does not require agents, API integrations, network access, or deployment into client environments. |
| 11 | Where is data processed or hosted? | Engagement work can be performed on EU-based infrastructure and/or locally, as agreed with the client before kickoff. |
| 12 | What sub-processors or cloud providers are used? | Typical support services may include a cloud hosting provider, document/file storage provider, email/calendar provider, communications tooling, and invoicing/payment tooling. A current list is available on request. |
| 13 | Is data encrypted in transit? | Yes. TLS is used for web, application, and file-transfer channels where applicable. |
| 14 | Is data encrypted at rest? | Sanitized engagement artifacts are stored using encrypted cloud storage or encrypted local storage where used. |
| 15 | How is access controlled? | Single-operator access model with least-privilege access. MFA is enabled on core business, development, and hosting tooling where supported. |
| 16 | How are administrative accounts managed? | Administrative access is limited to the solo operator and used only as needed for delivery, maintenance, support, and security tasks. |
| 17 | How are secrets managed? | Client secrets are not accepted. FaultRay operational secrets, where used, are stored in protected tooling or provider-managed secret/configuration facilities. |
| 18 | What logging and audit controls are available? | Evidence packs support tamper-evident integrity verification using HMAC-SHA256 chain hashing. Scenario assumptions, model inputs, outputs, and integrity metadata can be included in the pack. |
| 19 | How is vulnerability management handled? | Process-based vulnerability management is performed by the solo operator. Dependencies and runtime components are reviewed and updated periodically, with critical security patches prioritized when identified. |
| 20 | Is dependency scanning performed? | Process-based dependency review/scanning is used where tooling supports it. No third-party attestation is currently available. |
| 21 | Describe the secure SDLC. | Solo-founder, process-based SDLC using version control, functional testing, dependency review, least-privilege operational practices, and manual review before release. |
| 22 | What is the incident response process? | Security issues can be reported to security@faultray.com. FaultRay will triage, contain, investigate, remediate as appropriate, and notify affected clients. |
| 23 | What breach notification timeline is offered? | FaultRay will notify affected clients without undue delay after confirming a relevant security incident, targeting within 72 hours where feasible and legally appropriate. |
| 24 | What is the business continuity posture? | Key-person risk exists because FaultRay is solo-founder operated. This is mitigated by the short fixed-scope engagement, limited data footprint, no production dependency, and delivery of standalone artifacts. |
| 25 | What is the data retention and deletion policy? | Sanitized inputs and working files are deleted on request or within 30 days after delivery unless otherwise agreed in writing. |
| 26 | Is a DPA available? | A draft privacy policy / DPA is available at `/legal/privacy-policy`; an enterprise DPA can be requested. The draft is pending legal review. |
| 27 | Is there a right to audit? | FaultRay will respond to reasonable vendor-risk questionnaires and provide available control descriptions for this Sprint. On-site audits or formal third-party assurance reports are not currently available. |
| 28 | What certifications, penetration tests, and insurance are available? | SOC 2: Not certified — controls described below / on roadmap. ISO 27001: Not certified — controls described below / on roadmap. PCI DSS: Not certified — no cardholder data accepted. Third-party security certifications: Not certified — controls described below. Penetration testing: none currently — on roadmap / available on request when performed. Insurance: no stated insurance currently. |

---

## 3. Data Processing & DPA Summary

The DORA Resilience Evidence Sprint is designed around **data minimization**. FaultRay processes only the sanitized inputs the financial institution supplies for the engagement.

### Roles

- The financial institution is the **controller** for any personal data it provides.
- FaultRay acts as a **processor** for limited engagement-related data.
- The Sprint is intended to use **sanitized, non-production topology and dependency information only**.

### Data processed

FaultRay may process:

- Sanitized architecture and dependency descriptions for one critical service.
- Sanitized service, system, application, infrastructure, and third-party dependency labels.
- Sanitized resilience assumptions, failure scenarios, RTO/RPO targets, and operational dependency notes.
- Business-contact details for engagement coordination, such as:
  - name;
  - work email address;
  - job title / role;
  - company name;
  - meeting notes related to the Sprint.

### Data not accepted

FaultRay does not require and does not accept:

- End-customer PII.
- Customer records.
- Account, transaction, payment, trading, claims, policy, or similar regulated records.
- Production logs or live production data.
- Credentials, passwords, API tokens, private keys, certificates, or secrets.
- Production system access.

### DPA / privacy documentation

A draft privacy policy / DPA is available at the app’s `/legal/privacy-policy` page. An enterprise DPA can be requested. The current document should be treated as a draft pending legal review and may be replaced by a mutually agreed enterprise DPA.

---

## 4. Sprint Data-Flow & Scope Statement

### Sprint data flow

1. **Client provides sanitized inputs**  
   The client supplies a sanitized architecture/dependency description for one critical service. Inputs must exclude PII, customer records, live data, production logs, credentials, secrets, tokens, keys, and passwords.

2. **FaultRay models the topology in memory**  
   FaultRay models the supplied sanitized topology using its in-memory dependency/fault-injection engine. FaultRay does not connect to or scan production systems.

3. **FaultRay runs simulations**  
   FaultRay runs agreed resilience and dependency-failure simulations against the in-memory model.

4. **FaultRay produces the evidence pack**  
   FaultRay prepares a DORA pre-audit resilience evidence pack in Markdown/PDF format, including assumptions, scenario results, findings, DORA article mapping, and remediation backlog.

5. **FaultRay delivers the pack to the client**  
   The evidence pack is delivered to the named client contact through an agreed delivery channel.

6. **Inputs are deleted**  
   Sanitized inputs and working files are deleted on request or within 30 days after delivery unless otherwise agreed in writing.

### IN-SCOPE

- One critical service selected by the client.
- Sanitized topology/dependency model.
- In-memory dependency/fault-injection simulation.
- Fault-injection scenario results.
- Single point of failure analysis.
- Third-party concentration analysis.
- RTO/RPO discussion based on supplied targets and assumptions.
- DORA pre-audit mapping to Articles 11, 12, 24, 25, 28, and 30.
- Risk-prioritized remediation backlog.
- Evidence pack in Markdown/PDF format.
- Tamper-evident audit-chain metadata using HMAC-SHA256 chain hashing where applicable.
- Readout call.

### OUT-OF-SCOPE

- Production access.
- Production scanning.
- Live data processing.
- PII or end-customer data processing.
- Customer records.
- Production logs.
- Credentials, passwords, secrets, tokens, private keys, or certificates.
- Penetration testing.
- Vulnerability scanning.
- TLPT execution.
- Legal opinions or legal advice.
- DORA certification.
- Compliance guarantee.
- Auditor, regulator, legal, or management sign-off.
- Remediation implementation.
- Ongoing monitoring or managed service.

---

## 5. Fixed-Scope Statement of Work / Order Form

### Order form

| Field | Details |
|---|---|
| Engagement name | DORA Resilience Evidence Sprint |
| Client legal name | `{client_legal_name}` |
| Client contact | `{client_contact}` |
| Vendor | FaultRay |
| Scope | One critical service; sanitized inputs only; no production access; no PII; no credentials or secrets |
| Timeline | 5 business days from kickoff and receipt of required sanitized inputs |
| Total fee | $2,500 |
| Payment schedule | 50% upfront; 50% on delivery |
| Security contact | security@faultray.com |

### Scope summary

FaultRay will perform a fixed-scope, 5-business-day DORA pre-audit resilience evidence Sprint for **one critical service** selected by the client.

The client will provide a sanitized architecture/dependency description. FaultRay will model that topology in memory, run fault-injection and resilience simulations, analyze visible resilience risks, and produce an evidence pack for internal decision-support and pre-audit preparation.

FaultRay will not access production systems, process PII, collect credentials, process customer records, perform penetration testing, provide legal advice, certify DORA compliance, or replace TLPT or auditor sign-off.

### Deliverables

1. **Kickoff session**  
   30–60 minute kickoff to confirm the selected critical service, named client contact, input format, assumptions, timeline, and scope boundaries.

2. **Sanitized topology model**  
   Documented model of the supplied sanitized service topology, including key systems, dependencies, infrastructure components, third parties, and assumptions.

3. **Fault-injection scenario set**  
   Defined scenario set for the selected service, such as dependency outage, degraded third-party service, infrastructure-zone failure, operational recovery delay, and concentration-risk scenarios.

4. **Fault-injection scenario results**  
   Simulation outputs showing likely impact paths, affected dependencies, recovery considerations, and evidence-ready observations.

5. **SPOF & third-party concentration analysis**  
   Identification of visible single points of failure, dependency concentration risks, third-party reliance, and resilience gaps based on the sanitized model.

6. **RTO/RPO discussion**  
   Discussion of supplied RTO/RPO targets against scenario outputs, including assumptions, gaps, and questions for internal validation.

7. **DORA article mapping**  
   Practical pre-audit mapping of evidence and observations to DORA Articles 11, 12, 24, 25, 28, and 30.

8. **Risk-prioritized remediation backlog**  
   Concise backlog of recommended remediation and evidence-improvement actions, prioritized by likely resilience and audit-readiness impact.

9. **Evidence pack PDF / Markdown**  
   Final evidence pack in Markdown and/or PDF format, including assumptions, scenario outputs, analysis, DORA mapping, remediation backlog, and tamper-evident HMAC-SHA256 audit-chain information where applicable.

10. **Readout call**  
   30–60 minute readout call to walk through findings, assumptions, limitations, and recommended next steps.

### Timeline

| Day | Activity |
|---:|---|
| Day 1 | Kickoff; confirm one critical service; receive sanitized inputs; validate assumptions, scope, and exclusions |
| Day 2 | Build sanitized topology model; clarify dependencies and resilience assumptions with client contact |
| Day 3 | Run in-memory fault-injection scenarios; capture scenario outputs and impact paths |
| Day 4 | Analyze SPOFs, third-party concentration risks, RTO/RPO implications, and DORA article mapping |
| Day 5 | Finalize evidence pack; deliver Markdown/PDF; conduct or schedule readout call |

### Fees and payment terms

| Item | Amount |
|---|---:|
| Total fixed fee | $2,500 |
| Upfront payment due at signature / before kickoff | $1,250 |
| Final payment due on delivery | $1,250 |

Payment method: invoice, bank transfer, card, or another mutually agreed payment method.

Payment terms: upfront payment due before kickoff; final invoice due on delivery, Net 7 unless otherwise agreed in writing.

### Assumptions and client responsibilities

The client will:

- Select **one critical service** for the Sprint.
- Provide a named business and/or technical contact.
- Provide sanitized topology and dependency inputs by Day 1.
- Ensure all provided materials exclude PII, customer records, live production data, production logs, credentials, secrets, passwords, tokens, keys, and certificates.
- Provide or confirm relevant RTO/RPO targets, if available.
- Provide sanitized or generic third-party dependency information where needed for concentration analysis.
- Respond promptly to clarification questions during the 5-business-day Sprint.
- Attend the kickoff and readout calls.
- Review the evidence pack for factual accuracy.
- Use the deliverables as decision-support and pre-audit preparation only.

### Acceptance criteria

The Sprint is accepted when FaultRay delivers the final evidence pack in Markdown and/or PDF format covering:

- the selected critical service;
- sanitized topology model;
- fault-injection scenario results;
- SPOF and third-party concentration analysis;
- RTO/RPO discussion;
- DORA Articles 11, 12, 24, 25, 28, and 30 mapping;
- remediation backlog;
- assumptions and limitations;
- tamper-evident audit-chain information using HMAC-SHA256 chain hashing where applicable.

Minor factual corrections or formatting corrections may be requested within 5 business days of delivery. Additional services, additional critical services, expanded scenarios, production access, penetration testing, legal review, implementation support, or ongoing monitoring are outside this fixed scope and require a separate order.

### Important disclaimer

The DORA Resilience Evidence Sprint provides decision-support and pre-audit preparation only. It is **not legal advice**, **not a DORA certification**, **not a compliance guarantee**, **not TLPT**, and **not a replacement for auditor, regulator, legal, or management sign-off**.

### Signature blocks

**Client**

Client legal name: `{client_legal_name}`

Client contact: `{client_contact}`

Authorized signer: __________________________________

Name: _____________________________________________

Title: _____________________________________________

Date: _____________________________________________


**FaultRay**

Authorized signer: __________________________________

Name: _____________________________________________

Title: _____________________________________________

Date: _____________________________________________

---

## 6. Why This Is Low-Risk for Procurement

- **Small fixed price:** $2,500 total with no open-ended services commitment.
- **Short engagement:** 5 business days with clear deliverables and acceptance criteria.
- **No production access:** FaultRay does not connect to, scan, or access production systems.
- **No PII:** End-customer PII and customer records are explicitly out of scope.
- **No credentials or secrets:** The Sprint does not require passwords, tokens, keys, certificates, or other secrets.
- **No system integration:** No agent deployment, API integration, network access, firewall change, or infrastructure change is required.
- **Data-minimized:** Only sanitized topology and dependency metadata are used.
- **Deletable inputs:** Sanitized inputs and working files are deleted on request or within 30 days after delivery unless otherwise agreed.
- **Tamper-evident outputs:** Evidence packs can include HMAC-SHA256 chain hashing to support integrity verification.
- **Clear scope:** The Sprint is explicitly pre-audit decision-support, not legal advice, certification, TLPT, penetration testing, or auditor sign-off.
- **Low residual vendor risk:** The engagement is limited, non-invasive, commercially capped, and designed to avoid regulated production data.

---

*Honest disclaimer: FaultRay’s DORA Resilience Evidence Sprint is decision-support / pre-audit preparation only — not legal advice, not a DORA certification, not a compliance guarantee, and not a replacement for TLPT or auditor sign-off. Security contact: security@faultray.com.*
