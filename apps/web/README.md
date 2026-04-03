# FaultRay SaaS — Next.js Frontend

The web application for [faultray.com](https://faultray.com) — chaos engineering SaaS that mathematically proves your system's availability ceiling without touching production.

> **Try it now**: [faultray.com](https://faultray.com) — Free tier, no credit card required.

## Tech Stack

- **Framework**: Next.js 16 (App Router)
- **Auth**: Supabase (GitHub OAuth + Google OAuth)
- **Payments**: Stripe (Pro / Business plans)
- **Styling**: Tailwind CSS
- **Simulation engine**: Python (faultray v11) via API routes

## Development Setup

```bash
git clone https://github.com/mattyopon/faultray-app.git
cd faultray-app
npm install
cp .env.example .env.local  # fill in keys
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Required environment variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side admin key |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | Stripe publishable key |
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `NEXT_PUBLIC_API_URL` | Python engine URL (leave empty to use local mock) |

## Commands

```bash
npm run dev        # Start dev server
npm run build      # Production build
npm run typecheck  # tsc --noEmit
npm run lint       # ESLint
npm test           # Vitest unit tests
npx playwright test # E2E tests
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## Links

- **SaaS**: [faultray.com](https://faultray.com)
- **Core engine (Python)**: [github.com/mattyopon/faultray](https://github.com/mattyopon/faultray)
- **PyPI**: [pypi.org/project/faultray](https://pypi.org/project/faultray/)
- **Pricing**: [faultray.com/pricing](https://faultray.com/pricing)
- **Changelog**: [faultray.com/changelog](https://faultray.com/changelog)
