# FaultRay Privacy Policy

> **DRAFT -- Not yet reviewed by legal counsel.**
> This document is a working draft and does not constitute a binding privacy policy until formally reviewed, approved, and published by qualified legal counsel.

**Effective Date:** [To be determined]
**Last Updated:** 2026-03-16

---

## Introduction

This Privacy Policy describes how Yutaro Maeda and FaultRay Contributors ("we," "us," or "the Company") collect, use, store, and protect information when you use the FaultRay platform and related services (collectively, "the Service").

We are committed to protecting your privacy in compliance with:

- **General Data Protection Regulation (GDPR)** -- EU Regulation 2016/679
- **Act on the Protection of Personal Information (APPI)** -- Japan's personal information protection law
- **Digital Operational Resilience Act (DORA)** -- EU Regulation 2022/2554, particularly regarding data processing in financial services contexts

## 1. Information We Collect

### 1.1 Account Information

When you create an account, we collect:

| Data Category | Examples | Legal Basis (GDPR) |
|---------------|----------|---------------------|
| Identity data | Name, username | Contract performance (Art. 6(1)(b)) |
| Contact data | Email address | Contract performance (Art. 6(1)(b)) |
| Authentication data | Hashed password, OAuth tokens | Contract performance (Art. 6(1)(b)) |
| Billing data | Payment method, billing address | Contract performance (Art. 6(1)(b)) |
| Organization data | Company name, team memberships | Contract performance (Art. 6(1)(b)) |

### 1.2 Usage Data

We automatically collect data about how you interact with the Service:

| Data Category | Examples | Legal Basis (GDPR) |
|---------------|----------|---------------------|
| Access logs | IP address, browser type, access timestamps | Legitimate interest (Art. 6(1)(f)) |
| Feature usage | Commands executed, engines used, simulation frequency | Legitimate interest (Art. 6(1)(f)) |
| Performance data | Response times, error rates | Legitimate interest (Art. 6(1)(f)) |
| Device data | Operating system, Python version, CLI version | Legitimate interest (Art. 6(1)(f)) |

### 1.3 Infrastructure Definition Data

When you use the Service, you may provide:

| Data Category | Examples | Legal Basis (GDPR) |
|---------------|----------|---------------------|
| YAML definitions | Component configurations, dependency graphs | Contract performance (Art. 6(1)(b)) |
| Terraform state | Resource configurations, provider settings | Contract performance (Art. 6(1)(b)) |
| Prometheus data | Metric endpoints, target configurations | Contract performance (Art. 6(1)(b)) |
| Simulation results | Resilience scores, risk findings, reports | Contract performance (Art. 6(1)(b)) |

**Important:** Infrastructure definition data may contain sensitive information about your production environment (hostnames, IP addresses, port numbers, capacity figures). We treat all infrastructure definition data as **confidential** regardless of its content.

### 1.4 Information We Do NOT Collect

- We do **not** collect credentials, secrets, or API keys from your infrastructure definitions
- We do **not** access, connect to, or scan your actual production infrastructure
- We do **not** collect financial transaction data from your systems
- Self-hosted (Free/OSS) users: No data is transmitted to our servers

## 2. How We Use Your Information

We use collected information for the following purposes:

| Purpose | Data Used | Legal Basis |
|---------|-----------|-------------|
| Providing the Service | Account, infrastructure definitions, simulation results | Contract performance |
| Account management | Identity, contact, billing | Contract performance |
| Service improvement | Usage data, performance data | Legitimate interest |
| Security and abuse prevention | Access logs, usage patterns | Legitimate interest |
| Customer support | Account, usage data | Contract performance |
| Billing and invoicing | Billing data | Contract performance |
| Legal compliance | All data as required | Legal obligation (Art. 6(1)(c)) |
| Service notifications | Contact data | Legitimate interest |

We do **not** use your data for:

- Training machine learning or AI models (unless you explicitly opt in)
- Advertising or marketing to third parties
- Profiling for purposes unrelated to the Service
- Selling or renting to any third party

## 3. Information Sharing

### 3.1 Third-Party Service Providers

We may share data with trusted service providers who assist in operating the Service:

| Provider Category | Purpose | Data Shared |
|-------------------|---------|-------------|
| Cloud hosting | Infrastructure for SaaS platform | Encrypted infrastructure data, usage data |
| Payment processing | Subscription billing | Billing data (we do not store full card numbers) |
| Email delivery | Transactional emails, notifications | Email address, name |
| Analytics | Service improvement | Anonymized usage data |
| Error monitoring | Bug detection and resolution | Anonymized error logs |

All service providers are bound by data processing agreements (DPAs) that meet GDPR requirements.

### 3.2 Conditions for Sharing

We will **not** share your personal data or infrastructure definitions with third parties except:

- **With your explicit consent**
- **To comply with legal obligations** (court orders, regulatory requirements)
- **To protect our rights** (enforce Terms of Service, prevent fraud)
- **In a business transfer** (merger, acquisition, or asset sale -- you will be notified in advance)
- **In anonymized/aggregated form** (statistical data that cannot identify you or your infrastructure)

### 3.3 International Transfers

If your data is transferred outside your country of residence:

- EU/EEA data: Transfers are protected by Standard Contractual Clauses (SCCs) or adequacy decisions
- Japanese data: Transfers comply with APPI requirements for cross-border data transfer
- We ensure that all recipients provide adequate data protection safeguards

## 4. Data Retention and Deletion

### 4.1 Retention Periods

| Data Category | Retention Period | Basis |
|---------------|-----------------|-------|
| Account information | Duration of account + 30 days | Contract |
| Infrastructure definitions (Free) | Session only (not persisted) | Contract |
| Infrastructure definitions (Pro) | 90 days after last access | Contract |
| Infrastructure definitions (Enterprise) | As specified in agreement | Contract |
| Simulation results (Free) | 7 days | Contract |
| Simulation results (Pro) | 90 days | Contract |
| Simulation results (Enterprise) | As specified in agreement | Contract |
| Usage/access logs | 12 months | Legitimate interest |
| Billing records | 7 years | Legal obligation (tax law) |
| Security incident logs | 3 years | Legal obligation / legitimate interest |

### 4.2 Deletion

- You may request deletion of your data at any time (see Section 6: Your Rights)
- Upon account termination, we delete your data within 30 days
- Some data may be retained longer where required by law (e.g., billing records for tax purposes)
- Backups containing your data are purged within 90 days of deletion

### 4.3 Data Minimization

We follow the principle of data minimization:

- We collect only the data necessary to provide the Service
- Infrastructure definitions processed by the self-hosted version remain entirely on your systems
- Cloud-processed infrastructure data is encrypted at rest and in transit

## 5. Cookie Policy

### 5.1 Cookies We Use

| Cookie Type | Purpose | Duration | Consent Required |
|-------------|---------|----------|-----------------|
| **Strictly Necessary** | Authentication, session management, CSRF protection | Session | No (essential) |
| **Functional** | User preferences, dashboard settings, language selection | 1 year | No (legitimate interest) |
| **Analytics** | Service usage statistics, feature adoption tracking | 12 months | Yes |

### 5.2 Third-Party Cookies

We minimize third-party cookie usage. Currently:

- **Payment processor cookies** (Stripe) for secure payment processing
- **Analytics cookies** (if enabled) for aggregated usage statistics

### 5.3 Managing Cookies

You can manage cookie preferences:

- Through your browser settings
- Through the cookie consent banner on our website
- By contacting us at privacy@faultray.com

Disabling strictly necessary cookies may prevent the Service from functioning properly.

## 6. Your Rights

### 6.1 Rights Under GDPR (EU/EEA Residents)

You have the following rights regarding your personal data:

| Right | Description | How to Exercise |
|-------|-------------|-----------------|
| **Access** (Art. 15) | Obtain a copy of your personal data | Dashboard > Settings > Data Export, or email privacy@faultray.com |
| **Rectification** (Art. 16) | Correct inaccurate personal data | Dashboard > Settings > Profile, or email privacy@faultray.com |
| **Erasure** (Art. 17) | Request deletion of your personal data | Dashboard > Settings > Delete Account, or email privacy@faultray.com |
| **Restriction** (Art. 18) | Restrict processing of your data | Email privacy@faultray.com |
| **Portability** (Art. 20) | Receive your data in a machine-readable format | Dashboard > Settings > Data Export (JSON/YAML/CSV) |
| **Objection** (Art. 21) | Object to processing based on legitimate interest | Email privacy@faultray.com |
| **Withdraw Consent** (Art. 7(3)) | Withdraw previously given consent | Dashboard > Settings > Privacy, or email privacy@faultray.com |
| **Lodge Complaint** | File a complaint with a supervisory authority | Contact your local data protection authority |

### 6.2 Rights Under APPI (Japan Residents)

Under Japan's Act on the Protection of Personal Information, you have the right to:

- Request disclosure of your personal information
- Request correction, addition, or deletion of your personal information
- Request cessation of use or provision to third parties
- File complaints with the Personal Information Protection Commission (PPC)

### 6.3 Response Time

We will respond to all data rights requests within:

- **30 days** for GDPR requests (extendable by 60 days for complex requests, with notification)
- **14 days** for APPI requests

### 6.4 Verification

To protect your privacy, we may require identity verification before processing data rights requests.

## 7. DORA-Related Data Processing

For users in the financial services sector subject to the Digital Operational Resilience Act (DORA), we provide the following additional disclosures:

### 7.1 Data Processing for ICT Risk Management (DORA Article 6)

FaultRay processes infrastructure definition data to support ICT risk identification, protection, detection, response, and recovery activities. Specifically:

- **Risk identification:** Infrastructure topology analysis and single-point-of-failure detection
- **Risk assessment:** Resilience scoring and availability ceiling calculation
- **Risk monitoring:** Continuous simulation against evolving threat scenarios via security feeds

### 7.2 ICT Third-Party Risk (DORA Article 28)

As a provider of ICT services, we commit to:

- Maintaining an information register of all sub-processors
- Providing advance notice of changes to sub-processors
- Supporting your audit and access rights as required by DORA
- Ensuring continuity of critical functions through business continuity planning

### 7.3 Incident Reporting Support (DORA Article 17)

- We maintain incident detection and response capabilities with defined escalation procedures
- Major ICT-related incidents affecting the Service will be reported to affected customers within 24 hours
- We support customers in meeting their 72-hour regulatory reporting obligations by providing timely incident details

### 7.4 Data Processing Agreement

Enterprise customers subject to DORA may request a dedicated Data Processing Agreement (DPA) that includes:

- Detailed sub-processor list
- Security measures and audit provisions
- Incident notification procedures
- Data location and transfer safeguards
- Exit strategy and data portability provisions

## 8. Data Security

### 8.1 Technical Measures

We implement the following security measures to protect your data:

- **Encryption at rest:** AES-256 encryption for all stored data
- **Encryption in transit:** TLS 1.2+ for all network communications
- **Access control:** Role-based access control (RBAC) with principle of least privilege
- **Key management:** Regular cryptographic key rotation
- **Network security:** Firewall rules, intrusion detection, DDoS protection
- **Vulnerability management:** Regular security scanning and patching

### 8.2 Organizational Measures

- Security awareness training for all team members
- Incident response procedures with defined SLAs
- Regular security audits and penetration testing
- Background checks for personnel with access to customer data

### 8.3 Breach Notification

In the event of a personal data breach:

- We will notify affected users within 72 hours of becoming aware of the breach (GDPR Art. 33)
- We will notify the relevant supervisory authority where required
- Notification will include the nature of the breach, likely consequences, and measures taken

## 9. Children's Privacy

The Service is not intended for use by individuals under the age of 18. We do not knowingly collect personal data from children. If we become aware that we have collected data from a child, we will delete it promptly.

## 10. Changes to This Policy

We may update this Privacy Policy from time to time. Changes will be communicated:

- Via email notification for material changes (at least 30 days in advance)
- Via an updated "Last Updated" date at the top of this document
- Via in-app notification for Cloud service users

Continued use of the Service after the effective date of changes constitutes acceptance of the updated policy.

## 11. Contact Information

For questions, concerns, or data rights requests related to this Privacy Policy:

- **Privacy inquiries:** privacy@faultray.com
- **Data protection requests:** dpo@faultray.com
- **General support:** support@faultray.com
- **Website:** [https://faultray.com](https://faultray.com)
- **Repository:** [https://github.com/mattyopon/faultray](https://github.com/mattyopon/faultray)

**Data Controller:**
Yutaro Maeda
FaultRay Contributors
[Address to be specified]
Japan

---

*DRAFT -- This document has not been reviewed by legal counsel. It is provided as a starting point and must be reviewed and approved by a qualified attorney before publication or enforcement. In particular, specific data processing locations, sub-processor lists, and contact addresses must be finalized before this policy can take effect.*
