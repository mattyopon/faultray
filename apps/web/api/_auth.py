"""Shared authentication for the Python serverless API handlers.

Factored out of ``engine.py`` so that ``compliance.py`` and ``reports.py``
enforce the *same* gate instead of silently serving unauthenticated. Call
:func:`authenticate` as the first line of every ``do_GET``/``do_POST``: it
returns ``True`` when the caller is authenticated and otherwise writes a 401
and returns ``False``.

Accepted credentials (mirrors engine.py, fail-closed):
  * ``X-API-Key: <FAULTRAY_ENGINE_SECRET>``         — internal/agent/CI access
  * ``Authorization: Bearer <supabase_jwt>``        — end-user access
  * unconfigured-Supabase dev mode ONLY when ``FAULTRAY_ALLOW_UNAUTHENTICATED=1``
    is explicitly set (never in production) — so a missing/failed secret fetch
    can never silently disable auth.
"""

from __future__ import annotations

import hmac
import json
import os
import urllib.request


def _verify_supabase_jwt(token: str) -> bool:
    """Verify a Supabase JWT against the auth/v1/user endpoint."""
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    anon_key = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    if not supabase_url or not anon_key or not token:
        return False
    try:
        req = urllib.request.Request(
            f"{supabase_url}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": anon_key},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def is_authenticated(headers) -> bool:
    """Return ``True`` iff *headers* carry a valid API key or Supabase JWT."""
    api_key_header = headers.get("X-API-Key", "") or ""
    internal_secret = os.environ.get("FAULTRAY_ENGINE_SECRET", "")
    if internal_secret and hmac.compare_digest(api_key_header, internal_secret):
        return True

    auth_header = headers.get("Authorization", "") or ""
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):].strip()
        if _verify_supabase_jwt(token):
            return True

    # Fail-closed dev escape hatch: only when Supabase is unconfigured AND an
    # explicit opt-in is set. Never fail open on missing config alone.
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if (not supabase_url or not supabase_key) and \
            os.environ.get("FAULTRAY_ALLOW_UNAUTHENTICATED") == "1":
        return True

    return False


def authenticate(handler) -> bool:
    """Enforce auth on a ``BaseHTTPRequestHandler``.

    Returns ``True`` when authenticated. Otherwise writes a self-contained 401
    JSON response (using only ``send_response``/``send_header``/``wfile`` so it
    is independent of each handler's bespoke ``_json``/``_send_json`` helper)
    and returns ``False`` — the caller should ``return`` immediately.
    """
    if is_authenticated(handler.headers):
        return True
    body = json.dumps({"error": {"message": "Authentication required"}}).encode("utf-8")
    handler.send_response(401)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    allowed_origin = os.environ.get("FAULTRAY_ALLOWED_ORIGIN", "")
    if allowed_origin:
        handler.send_header("Access-Control-Allow-Origin", allowed_origin)
    handler.end_headers()
    handler.wfile.write(body)
    return False
