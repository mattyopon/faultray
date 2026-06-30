# DORA Pre-Audit Resilience Evidence Pack: {SERVICE_NAME}

| Metadata | Value |
|---|---|
| Institution | {INSTITUTION_NAME} |
| Critical Service | {SERVICE_NAME} |
| Report Date | {REPORT_DATE} |
| Prepared By | {PREPARED_BY} |
| Engagement ID | {ENGAGEMENT_ID} |

## About this pack

This evidence pack is built from **sanitized engagement data only**. FaultRay requires **no production access** and processes **no PII** for this work. The pack provides model-based, decision-support evidence to help {INSTITUTION_NAME} prepare for a DORA pre-audit of {SERVICE_NAME}; it is **not legal advice**, **not a DORA certification**, and **not a guarantee of compliance**.

## Executive Summary

FaultRay simulated resilience failure modes for {SERVICE_NAME} using sanitized dependency, architecture, recovery, and third-party input data. The results provide a pre-audit view of service dependencies, likely blast radius, simulated recovery behavior, and prioritized resilience gaps for operational-resilience and ICT-risk review.

| Metric | Value |
|---|---:|
| Resilience Score | {RESILIENCE_SCORE} |
| Critical Findings Count | {CRITICAL_FINDINGS_COUNT} |
| RTO Target | {RTO_TARGET} |
| RPO Target | {RPO_TARGET} |
| Single Points of Failure Count | {SPOF_COUNT} |

## What's in this Evidence Pack

1. **Critical Service Dependency Map & Blast-Radius Analysis** — A sanitized dependency graph showing key systems, infrastructure, data stores, integrations, and likely impact propagation paths for {SERVICE_NAME}.
2. **Fault-Injection / Chaos Scenario Catalogue & Results** — A catalogue of simulated component, infrastructure, network, data, and third-party failure scenarios with observed model outcomes.
3. **Single Points of Failure & Concentration Register** — A register of modeled technical, operational, and supplier concentration risks that may materially affect service continuity.
4. **RTO/RPO Validation Against Simulated Recovery** — A comparison of target RTO/RPO values against simulated recovery timelines, dependency restoration order, and modeled data-loss exposure.
5. **Backup & Restoration Evidence Summary** — A summary of backup, restoration, replication, and data-recovery assumptions provided for the engagement and how they performed in simulation.
6. **ICT Third-Party Dependency & Concentration Analysis** — A view of material ICT third-party services, downstream dependencies, and simulated effects of provider or concentration failures.
7. **Severe-but-Plausible Scenario Testing Results** — Results from modeled severe-but-plausible resilience scenarios relevant to operational disruption, recovery sequencing, and service degradation.
8. **Recovery & Response Playbook Gap Analysis** — A review of modeled recovery paths against provided response procedures, escalation paths, ownership, and decision points.
9. **Remediation Backlog Prioritised by Blast Radius** — A prioritized list of resilience improvements ranked by simulated service impact, dependency criticality, and recovery-risk reduction.
10. **DORA Article Mapping & Evidence Index** — A traceability index mapping FaultRay outputs to selected DORA operational-resilience themes for pre-audit preparation.

## DORA Article Mapping

| DORA Article | What FaultRay evidences | Artifact in this pack |
|---|---|---|
| Article 11 (Response & recovery) | FaultRay evidences modeled response and recovery dependencies, likely outage propagation, simulated recovery sequencing, and gaps between provided playbooks and modeled failure paths. It does not prove live operational execution, validate team performance in production, or certify that response procedures will succeed. | Critical Service Dependency Map & Blast-Radius Analysis; Fault-Injection / Chaos Scenario Catalogue & Results; RTO/RPO Validation Against Simulated Recovery; Recovery & Response Playbook Gap Analysis |
| Article 12 (Backup policies & restoration) | FaultRay evidences the backup, restoration, replication, and recovery assumptions supplied for the engagement and tests them against simulated service-disruption scenarios. It does not replace live restore testing, backup-control validation, policy approval, or operational attestation. | Backup & Restoration Evidence Summary; RTO/RPO Validation Against Simulated Recovery; Severe-but-Plausible Scenario Testing Results |
| Article 24 (Testing of ICT tools & systems / digital operational resilience testing programme) | FaultRay provides structured model-based resilience scenarios and results that can support a digital operational resilience testing programme. It does not replace required live testing, production failover exercises, control testing, penetration testing, or management sign-off. | Fault-Injection / Chaos Scenario Catalogue & Results; Severe-but-Plausible Scenario Testing Results; DORA Article Mapping & Evidence Index |
| Article 25 (Advanced testing / TLPT context) | FaultRay provides scenario inputs, dependency context, critical service scoping, and severe-but-plausible impact analysis to support advanced testing and TLPT preparation. It is not a replacement for threat-led penetration testing by accredited testers and does not perform live adversarial testing. | Critical Service Dependency Map & Blast-Radius Analysis; Severe-but-Plausible Scenario Testing Results; Remediation Backlog Prioritised by Blast Radius |
| Article 28 (ICT third-party risk) | FaultRay evidences modeled ICT third-party dependencies, provider concentration, and simulated outage impact on {SERVICE_NAME}. It does not assess third-party control effectiveness, provider regulatory compliance, or assurance evidence beyond supplied sanitized inputs. | ICT Third-Party Dependency & Concentration Analysis; Single Points of Failure & Concentration Register; Critical Service Dependency Map & Blast-Radius Analysis |
| Article 30 (Key contractual provisions) | FaultRay surfaces third-party dependencies, concentration points, recovery expectations, and operational-impact findings that can inform contract review. It does not assess legal contract text, determine contractual adequacy, or provide legal advice. | ICT Third-Party Dependency & Concentration Analysis; RTO/RPO Validation Against Simulated Recovery; DORA Article Mapping & Evidence Index |

## Methodology & Limitations

- FaultRay uses **sanitized input data** provided for the engagement, such as architecture summaries, dependency inventories, service metadata, recovery objectives, backup assumptions, ICT third-party information, and response-playbook excerpts.
- Simulations are **model-based** and use dependency-graph analysis, fault-injection scenarios, blast-radius modeling, and recovery-sequence assumptions.
- Results depend on the completeness, accuracy, and timeliness of the sanitized inputs supplied by {INSTITUTION_NAME}.
- FaultRay requires **no production access**, does **not** connect to live systems, and processes **no PII** for this evidence pack.
- This work does **not** replace live TLPT, penetration testing, production failover testing, live restore testing, legal review, regulatory interpretation, auditor sign-off, or management accountability for DORA compliance.

## Next Steps

To convert this template into a completed pre-audit evidence pack for {SERVICE_NAME}, book the fixed-scope **DORA Resilience Evidence Sprint**:

- Duration: **5 business days**
- Inputs: **sanitized data only**
- Access: **no production access required**
- Data handling: **no PII**
- Fee: **$2,500**
- Payment: **50% upfront**

Schedule a scoping call: https://faultray.com/evidence-sprint

---

FaultRay provides decision-support evidence for DORA pre-audit preparation; it is not legal advice, not a certification body, and not a guarantee of compliance.
