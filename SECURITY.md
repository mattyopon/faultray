# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 11.x    | ✅ Active support |
| 10.x    | ⚠️ Security fixes only |
| < 10.0  | ❌ End of life |

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email:

📧 **security@faultray.com**

Please include:
- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

### Response Timeline
- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Fix & Disclosure**: Within 30 days (coordinated disclosure)

## Secrets Rotation Policy (#96)

FaultRay holds a small number of long-lived credentials (PyPI Trusted
Publisher OIDC, GHCR tokens, Supabase service role, Stripe webhook
secret). The rotation posture is:

| Secret                         | Default rotation | Breach-triggered rotation SLA |
|--------------------------------|------------------|-------------------------------|
| Supabase service role key      | Annual           | Within **24 hours** of detection |
| Stripe webhook secret          | Annual           | Within **24 hours** of detection |
| GHCR `GITHUB_TOKEN`            | Managed by GitHub (per-job) — no manual rotation | n/a |
| PyPI Trusted Publisher (OIDC)  | Managed by PyPI + GitHub OIDC — no long-lived token | n/a |
| Release signing (sigstore)     | Keyless OIDC per-build (see #95)                  | n/a |

Additional rules:
- **No secret is committed to git.** `gitleaks.yml` pre-commit + CI
  workflow enforces this.
- **Every revocation is logged** as a GitHub Security Advisory whenever
  credentials were *possibly* exposed.
- **Rotation cadence enforcement is currently manual**. An automated
  reminder (GitHub Issue auto-opened quarterly via a scheduled workflow)
  is tracked as a follow-up. Until then, maintainer self-audit at each
  release review is the fallback.

## Incident Response Runbook (#98)

See [`docs/incident-response-runbook.md`](docs/incident-response-runbook.md)
for the structured playbook covering:
- Production outage severity classification (SEV-1..3)
- Data-breach 72-hour GDPR notification window
- Stakeholder escalation matrix
- Post-incident review template

## Security Best Practices

When using FaultRay in production:
- Always run behind a reverse proxy (nginx, Caddy)
- Enable authentication for the web dashboard
- Use API keys for programmatic access
- Keep FaultRay updated to the latest version
- Review the [DORA compliance docs](docs/enterprise/compliance.md)

---

# セキュリティポリシー（日本語）

## 脆弱性の報告

**GitHubのIssuesで脆弱性を報告しないでください。**

📧 **security@faultray.com** にメールで報告してください。

### 対応タイムライン
- **受領確認**: 48時間以内
- **初期評価**: 7日以内
- **修正・公開**: 30日以内（協調的開示）
