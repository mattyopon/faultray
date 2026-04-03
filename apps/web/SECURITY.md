# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 11.x (latest) | Yes |
| 10.x | Critical fixes only |
| < 10.0 | No |

## Reporting a Vulnerability

**Do not open a public GitHub Issue for security vulnerabilities.**

Please report security issues via **private disclosure**:

- **Email**: security@faultray.com
- **Subject**: `[SECURITY] Brief description`
- **GPG key**: Available at https://faultray.com/.well-known/security.txt (planned)

### What to include

1. Description of the vulnerability
2. Steps to reproduce (proof-of-concept if available)
3. Potential impact
4. Any suggested mitigations

### Response timeline

| Stage | Timeline |
|-------|----------|
| Acknowledgement | Within 2 business days |
| Initial assessment | Within 5 business days |
| Fix & CVE assignment (if applicable) | Within 30 days for critical, 90 days for others |
| Public disclosure | After fix is released |

## CVE Process

For vulnerabilities that qualify as CVEs:

1. We will request a CVE ID via [MITRE](https://cveform.mitre.org/) or coordinate with the reporter
2. A [GitHub Security Advisory](https://github.com/mattyopon/faultray-app/security/advisories) will be published
3. A patch release will be tagged and pushed to PyPI/npm simultaneously
4. Credit will be given to the reporter (unless they prefer anonymity)

## Known Security Controls

- All API routes require Supabase JWT authentication
- Row Level Security (RLS) enabled on all Supabase tables
- Stripe webhook signatures verified on `/api/webhooks/stripe`
- Content Security Policy headers set via `next.config.ts`
- Rate limiting: 60 req/min per IP on simulation endpoints
- No secrets in client-side bundles — all keys in environment variables

## Dependency Monitoring

Dependencies are monitored via:
- `npm audit` — run in CI on every PR
- Dependabot alerts (planned — see [LICENSE-02](https://github.com/mattyopon/business-docs))

## Bug Bounty

There is currently no formal bug bounty program. Responsible disclosure is
appreciated and credited in release notes.
