# FaultRay SaaS Deployment Guide

> **Before deploying**: Run through [DEPLOY_CHECKLIST.md](./DEPLOY_CHECKLIST.md) to verify all environment variables, auth providers, and Supabase configuration.
> This guide covers architecture and step-by-step setup.

## Architecture

```
faultray.com (Vercel)
  ├── / → Landing page
  ├── /dashboard → Dashboard
  ├── /simulate → Simulation runner
  └── /api/proxy → Fly.io FastAPI

api.faultray.com (Fly.io)
  └── FastAPI backend (simulation engine)

Supabase
  ├── Auth (GitHub/Google OAuth)
  ├── PostgreSQL (users, teams, runs)
  └── Row Level Security
```

## Step 1: Supabase Setup

1. Go to https://supabase.com/dashboard and create a new project
2. Run the SQL migration:
   - Go to SQL Editor
   - Paste contents of `supabase/migrations/001_initial_schema.sql`
   - Click Run
3. Configure Auth providers:
   - Go to Authentication > Providers
   - Enable GitHub OAuth:
     - Client ID: `REDACTED_GITHUB_CLIENT_ID`
     - Client Secret: (from .env)
   - Enable Google OAuth:
     - Client ID: `352070354644-...`
     - Client Secret: (from .env)
   - Set Site URL to `https://faultray.com`
   - Add Redirect URLs:
     - `https://faultray.com/auth/callback`
     - `http://localhost:3000/auth/callback`
4. Note your project URL and anon key from Settings > API

## Step 2: Vercel Deployment

1. Import the GitHub repo: https://vercel.com/import/git
   - Select `mattyopon/faultray-app`
2. Set environment variables:
   ```
   NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
   NEXT_PUBLIC_API_URL=https://api.faultray.com
   FAULTRAY_API_URL=https://api.faultray.com
   ```
3. Deploy
4. Set custom domain: `faultray.com`

## Step 3: Fly.io Deployment

```bash
cd /home/user/repos/faultray
flyctl auth login
flyctl deploy
flyctl secrets set \
  FAULTRAY_CORS_ORIGINS=https://faultray.com \
  STRIPE_SECRET_KEY=sk_... \
  JWT_SECRET_KEY=...
```

## Step 4: DNS Configuration (Cloudflare)

1. Change `faultray.com` A/CNAME to point to Vercel:
   - Type: CNAME
   - Name: @
   - Target: cname.vercel-dns.com
   - Proxy: DNS only (grey cloud)
2. Add `api.faultray.com`:
   - Type: CNAME
   - Name: api
   - Target: faultray-demo.fly.dev
   - Proxy: DNS only (grey cloud)

## Environment Variables Reference

| Variable | Where | Description |
|----------|-------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Vercel | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Vercel | Supabase anon key |
| `NEXT_PUBLIC_API_URL` | Vercel | FaultRay API URL |
| `FAULTRAY_API_URL` | Vercel | Server-side API URL |
| `FAULTRAY_CORS_ORIGINS` | Fly.io | Allowed CORS origins |
| `JWT_SECRET_KEY` | Fly.io | JWT signing key |
| `STRIPE_SECRET_KEY` | Fly.io | Stripe secret key |
