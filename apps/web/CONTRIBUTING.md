# Contributing to FaultRay

Thank you for considering a contribution to FaultRay.

## Development Setup

```bash
git clone https://github.com/mattyopon/faultray-app.git
cd faultray-app
npm install
cp .env.local.example .env.local  # fill in Supabase + Stripe keys
npm run dev
```

## Branch Conventions

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready releases only |
| `develop` | Integration branch — all PRs target this |
| `feat/*` | New features |
| `fix/*` | Bug fixes |
| `chore/*` | Tooling, dependencies, config |

## Pull Request Guidelines

- **Target branch**: `develop` (never `main` directly)
- **PR title**: `[type]: short description` — e.g. `feat: add changelog page`
- **PR description**: Summarize what changed and why
- **Review wait time**: Allow 2 business days for review response
- **DCO sign-off**: Not currently required, but appreciated
- **Squash on merge**: Preferred to keep history clean

## Required Checks Before Opening PR

```bash
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm test            # vitest
```

All three must pass. PRs that fail CI will not be reviewed.

## Test Coverage Requirements

- New features must include at least one unit test
- Bug fixes must include a regression test
- Target: 80%+ line coverage on new code
- Run: `npm run test -- --coverage`

## Code Style

- TypeScript strict mode (`"strict": true` in tsconfig.json)
- No `any` types without a comment explaining why
- No `console.log` in production code — use server-side logging
- Tailwind utility classes only — no raw CSS unless unavoidable
- Server Components by default — add `"use client"` only when needed

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add simulation timeout handling
fix: prevent double-submit on simulate button
docs: update CONTRIBUTING.md
chore: upgrade next to 15.3
```

## Reporting Bugs

Open a GitHub Issue with:
1. Steps to reproduce
2. Expected behavior
3. Actual behavior
4. Browser/OS/Node version

For **security vulnerabilities**, see [SECURITY.md](SECURITY.md) — do not open public issues.
