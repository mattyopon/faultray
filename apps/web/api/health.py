"""FaultRay health check + admin check + admin plan switch.

GET /api/health -> { status, engine, version }
POST /api/health:
  { "email": "..." } -> { is_admin }
  { "action": "switch-plan", "email": "...", "plan": "pro" } -> { ok, plan }
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request


def _is_admin(email: str) -> bool:
    admin_emails = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]
    return email.strip().lower() in admin_emails


def _switch_plan(email: str, plan: str) -> dict:
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        return {"error": "Supabase not configured"}
    if plan not in ("free", "pro", "business"):
        return {"error": f"Invalid plan: {plan}"}
    data = json.dumps({"plan": plan}).encode()
    req = urllib.request.Request(
        f"{supabase_url}/rest/v1/profiles?email=eq.{email}",
        data=data, method="PATCH",
        headers={"Content-Type": "application/json", "apikey": service_key,
                 "Authorization": f"Bearer {service_key}", "Prefer": "return=representation"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        if result:
            return {"ok": True, "plan": result[0].get("plan", plan)}
        return {"error": "Profile not found"}
    except Exception as e:
        return {"error": str(e)}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            import faultray
            version = faultray.__version__
        except Exception:
            version = "unknown"
        self._json(200, {"status": "ok", "engine": "faultray", "version": version})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except (json.JSONDecodeError, ValueError):
            self._json(400, {"error": "Invalid JSON"})
            return
        action = body.get("action", "admin-check")
        email = body.get("email", "").strip().lower()
        if not email:
            self._json(400, {"error": "Missing email"})
            return
        if action == "admin-check":
            self._json(200, {"is_admin": _is_admin(email)})
        elif action == "switch-plan":
            if not _is_admin(email):
                self._json(403, {"error": "Not authorized"})
                return
            result = _switch_plan(email, body.get("plan", ""))
            self._json(400 if "error" in result else 200, result)
        else:
            self._json(200, {"is_admin": _is_admin(email)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, status, data):
        body = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
