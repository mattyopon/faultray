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

## Security Best Practices

When using FaultRay in production:
- Always run behind a reverse proxy (nginx, Caddy)
- Enable authentication for the web dashboard
- Use API keys for programmatic access
- Keep FaultRay updated to the latest version
- Review the [DORA compliance docs](docs/enterprise/compliance.md)

## Supply-chain integrity (#95)

Every published release ships three cryptographic signals:

1. **CycloneDX SBOM** — `.cdx.json` for Python dist + Docker image
2. **SLSA v1 build provenance** — attested via `actions/attest-build-provenance`
3. **Sigstore cosign signature** — keyless OIDC signing for Docker images

See [`docs/release-verification.md`](docs/release-verification.md) for
step-by-step verification commands (`gh attestation verify`, `cosign verify`).

---

# セキュリティポリシー（日本語）

## 脆弱性の報告

**GitHubのIssuesで脆弱性を報告しないでください。**

📧 **security@faultray.com** にメールで報告してください。

### 対応タイムライン
- **受領確認**: 48時間以内
- **初期評価**: 7日以内
- **修正・公開**: 30日以内（協調的開示）
