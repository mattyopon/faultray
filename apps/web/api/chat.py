"""FaultRay AI advisor chat + health check endpoint (merged).

POST /api/chat    Body: { "message": "..." } -> AI advice
GET  /api/health  -> { status, engine, version }  (rewritten to /api/chat)
POST /api/health  -> admin check / plan switch     (rewritten to /api/chat)
"""

from http.server import BaseHTTPRequestHandler
import json


KNOWLEDGE_BASE = {
    "availability": "FaultRay calculates availability using a 3-layer model: Hardware (physical redundancy), Software (application resilience), and Theoretical (mathematical upper bound). The final score is the minimum of these three layers, as a system is only as reliable as its weakest link.",
    "replicas": "Adding replicas improves availability by providing failover capacity. The relationship is roughly logarithmic - going from 1 to 2 replicas has the biggest impact. For databases, consider read replicas for read-heavy workloads and multi-primary for write-heavy workloads.",
    "circuit breaker": "Circuit breakers prevent cascading failures by detecting failing downstream services and short-circuiting requests. Implement with three states: Closed (normal), Open (failing, return fallback), Half-Open (testing recovery). Libraries: resilience4j (Java), Polly (.NET), pybreaker (Python).",
    "failover": "Automatic failover reduces MTTR (Mean Time To Repair). For databases, configure promotion time under 30 seconds. For application servers, use health checks with 10-second intervals. Always test failover procedures with chaos engineering.",
    "compliance": "FaultRay supports DORA, SOC2, ISO27001, PCI-DSS, HIPAA, and GDPR frameworks. Each framework has specific controls related to system resilience, disaster recovery, and business continuity.",
    "score": "The FaultRay resilience score (0-100) represents your infrastructure's ability to withstand failures. Score breakdown: 90-100 (Excellent), 70-89 (Good), 50-69 (Needs Work), 0-49 (Critical). The score is derived from 2,000+ chaos scenarios.",
}


def _generate_response(message: str) -> dict:
    """Generate an AI response based on the message."""
    message_lower = message.lower()

    # Match against knowledge base
    best_match = None
    best_score = 0
    for key, value in KNOWLEDGE_BASE.items():
        keywords = key.split()
        match_count = sum(1 for kw in keywords if kw in message_lower)
        if match_count > best_score:
            best_score = match_count
            best_match = value

    if best_match and best_score > 0:
        response = best_match
    elif "how" in message_lower and "improv" in message_lower:
        response = (
            "To improve your resilience score, focus on these high-impact areas:\n\n"
            "1. **Add redundancy** - Increase replicas for critical components (databases, caches)\n"
            "2. **Implement circuit breakers** - Prevent cascading failures between services\n"
            "3. **Reduce failover time** - Automate database promotion and service recovery\n"
            "4. **Add health checks** - Monitor all components with appropriate intervals\n"
            "5. **Multi-region deployment** - Protect against regional outages\n\n"
            "Use the What-if Analysis page to simulate the impact of each change before implementing."
        )
    elif "what" in message_lower and "faultray" in message_lower:
        response = (
            "FaultRay is a zero-risk chaos engineering platform that tests your infrastructure's "
            "resilience through pure simulation. It runs 2,000+ failure scenarios against your "
            "infrastructure topology without touching production. Key features include:\n\n"
            "- 3-Layer Availability Model (Hardware/Software/Theoretical)\n"
            "- FMEA (Failure Mode and Effects Analysis)\n"
            "- Compliance assessment (DORA, SOC2, ISO27001, etc.)\n"
            "- What-if analysis for parameter tuning\n"
            "- Attack surface analysis\n"
            "- Cost/ROI analysis for improvements"
        )
    else:
        response = (
            "I can help you understand your infrastructure resilience. Try asking about:\n\n"
            "- How to improve your resilience score\n"
            "- Availability calculations and the 3-layer model\n"
            "- Replica and redundancy strategies\n"
            "- Circuit breaker patterns\n"
            "- Failover configuration\n"
            "- Compliance frameworks (DORA, SOC2, etc.)\n"
            "- Score breakdown and interpretation"
        )

    return {
        "response": response,
        "sources": ["FaultRay Knowledge Base", "Infrastructure Best Practices"],
        "suggested_actions": [
            {"label": "Run Simulation", "href": "/simulate"},
            {"label": "View Score Detail", "href": "/score-detail"},
            {"label": "What-if Analysis", "href": "/whatif"},
        ],
    }


# ---------------------------------------------------------------------------
# Health check helpers (merged from health.py)
# ---------------------------------------------------------------------------

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


def _is_health_path(path: str) -> bool:
    return "/health" in path


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Health check (rewritten from /api/health)
        try:
            import faultray
            version = faultray.__version__
        except Exception:
            version = "unknown"
        self._send_json(200, {"status": "ok", "engine": "faultray", "version": version})

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError):
            self._send_error(400, "Invalid JSON")
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # Health/admin routes (rewritten from /api/health)
        if _is_health_path(path):
            action = data.get("action", "admin-check")
            email = data.get("email", "").strip().lower()
            if not email:
                self._send_json(400, {"error": "Missing email"})
                return
            if action == "admin-check":
                self._send_json(200, {"is_admin": _is_admin(email)})
            elif action == "switch-plan":
                if not _is_admin(email):
                    self._send_json(403, {"error": "Not authorized"})
                    return
                result = _switch_plan(email, data.get("plan", ""))
                self._send_json(400 if "error" in result else 200, result)
            else:
                self._send_json(200, {"is_admin": _is_admin(email)})
            return

        # Chat route
        message = data.get("message", "")
        if not message:
            self._send_error(400, "Missing 'message' in request body")
            return
        try:
            result = _generate_response(message)
            self._send_json(200, result)
        except Exception as e:
            self._send_error(500, f"Chat error: {e}")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_error(self, status: int, message: str):
        self._send_json(status, {"error": {"message": message}})

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
