# Incident Response Runbook (#98)

> Referenced from [SECURITY.md](../SECURITY.md). Covers production
> outage + data breach + misuse scenarios for FaultRay (both the OSS
> tool and the faultray.com SaaS).

## 1. Severity classification

| Severity | Criterion | Examples |
|---|---|---|
| **SEV-1** | User-facing SaaS outage >5 min OR data breach OR critical CVE in-wild | faultray.com 500s for all users / Supabase data exfiltration / unsigned release published |
| **SEV-2** | Partial outage OR high-severity CVE not in-wild OR RLS policy break | Login flow broken but dashboard OK / `admin.py` route leaks info |
| **SEV-3** | Minor degradation / cosmetic | `/status` page stale / Japanese email template breaks |

SEV-1 triggers the **72-hour GDPR notification window** if personal data
was (or could have been) accessed. See §4.

## 2. Detection → Ack

- **Discovery signal**: GH Security Advisory / `security@faultray.com`
  email / user report / CI alert / uptime monitor alert.
- **Ack SLA**: 48 h for email report (per SECURITY.md), 15 min for
  CI/uptime alert.
- First responder **opens a private GitHub Security Advisory** (SEV-1/2)
  or a regular issue (SEV-3) and pings `@mattyopon` in the thread.

## 3. Triage (first 2 hours for SEV-1)

1. **Scope the blast radius**
   - Which artifact? (PyPI wheel / Docker image / SaaS tenant)
   - Which versions?
   - How many users affected?
2. **Stop the bleed**
   - SaaS outage → roll back Vercel deployment (`vercel rollback`)
   - Leaked secret → rotate immediately (see SECURITY.md rotation SLA)
   - Malicious release → `pypi` yank, `ghcr` delete-tag
3. **Preserve evidence**
   - Capture relevant logs (Vercel runtime logs, Supabase audit log,
     GitHub Actions run logs)
   - Copy to `~/security-incidents/<date>/`

## 4. Breach notification (GDPR 72h clock)

If personal data was (or could have been) read, modified, or exfiltrated:

- **Start the 72-hour clock** from the moment awareness was reached.
- Draft **data-subject notification** with:
  - What data categories were involved
  - Likely consequences
  - Mitigations already in place
  - Contact for further questions (security@faultray.com)
- File with EU supervisory authority (for EU users) via
  [edpb.europa.eu](https://edpb.europa.eu/) within 72 h.
- File with PPC (for Japanese users) per APPI §22-2.

## 5. Stakeholder escalation matrix

| Role | When engaged | How |
|---|---|---|
| Maintainer (`@mattyopon`) | Always | GitHub Security Advisory + email |
| Legal counsel | SEV-1 with data loss | Email (TBD) |
| Paying SaaS customers | SEV-1 lasting >30 min | Status page update + direct email |
| OSS users | Supply-chain compromise (release pulled) | GH Security Advisory + release notes |
| PyPI / GHCR security | Supply-chain compromise | Contact forms on each platform |

## 6. Post-incident review (PIR)

Within **5 business days** of closing a SEV-1 or SEV-2:

- Open a `postmortem/<date>-<slug>.md` draft under `docs/postmortems/`
  using the template below.
- Review in a ≤30 min maintainer meeting.
- Land the PIR as a PR — *always blameless*.

### PIR template

```
# <Date> – <title>

**Severity**: SEV-1 / SEV-2
**Duration**: <start> → <end> (<minutes>)
**Impact**: <user-facing summary, numbers where available>

## Timeline
(UTC)
- HH:MM — <event>
- ...

## Root cause
<1-3 paragraphs, technical>

## What went well
- ...

## What went poorly
- ...

## Action items
| # | Description | Owner | Due |
|---|---|---|---|
| 1 | ... | @mattyopon | YYYY-MM-DD |
```

## 7. Related docs

- Vulnerability disclosure — [SECURITY.md](../SECURITY.md)
- Release signing / SBOM — [release-verification.md](release-verification.md) (#95)
- Secrets rotation SLA — SECURITY.md §Secrets Rotation Policy (#96)
