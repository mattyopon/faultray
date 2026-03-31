"""FaultRay Projects CRUD backend.

Routes:
  GET  /api/projects           -> list all projects
  GET  /api/projects?id={id}   -> get single project with simulation runs
  POST /api/projects           -> create project
  PATCH /api/projects?id={id}  -> update project
  DELETE /api/projects?id={id} -> delete project
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


# ---------------------------------------------------------------------------
# Demo data (used when Supabase is not configured)
# ---------------------------------------------------------------------------

def _get_demo_projects():
    return [
        {
            "id": "demo-prod-aws",
            "team_id": "demo-team",
            "name": "Production AWS",
            "description": "Primary production infrastructure on AWS us-east-1",
            "topology_yaml": None,
            "topology_type": "aws_scan",
            "status": "active",
            "created_at": _ago(86400 * 30),
            "updated_at": _ago(3600),
            "last_score": 87.4,
            "last_run_at": _ago(3600),
            "run_count": 14,
        },
        {
            "id": "demo-staging-k8s",
            "team_id": "demo-team",
            "name": "Staging K8s",
            "description": "Kubernetes staging cluster for pre-production validation",
            "topology_yaml": None,
            "topology_type": "k8s_scan",
            "status": "active",
            "created_at": _ago(86400 * 20),
            "updated_at": _ago(86400),
            "last_score": 72.1,
            "last_run_at": _ago(86400),
            "run_count": 8,
        },
        {
            "id": "demo-dr-site",
            "team_id": "demo-team",
            "name": "DR Site",
            "description": "Disaster recovery site on AWS us-west-2",
            "topology_yaml": None,
            "topology_type": "terraform",
            "status": "active",
            "created_at": _ago(86400 * 10),
            "updated_at": _ago(86400 * 2),
            "last_score": 91.8,
            "last_run_at": _ago(86400 * 2),
            "run_count": 5,
        },
    ]


def _get_demo_runs(project_id: str):
    base_runs = [
        {
            "id": 1001,
            "project_id": project_id,
            "created_at": _ago(3600),
            "overall_score": 87.4,
            "availability_estimate": "99.97%",
            "engine_type": "full",
            "scenarios_passed": 142,
            "scenarios_failed": 10,
            "total_scenarios": 152,
            "critical_failures": [
                {"scenario": "Database failover", "impact": "Service degradation", "severity": "HIGH"},
                {"scenario": "Cache miss storm", "impact": "Latency spike", "severity": "MEDIUM"},
            ],
            "suggestions": [
                {"title": "Add read replicas", "description": "Add 2 read replicas to reduce load", "impact": "HIGH", "effort": "MEDIUM"},
            ],
        },
        {
            "id": 1000,
            "project_id": project_id,
            "created_at": _ago(86400),
            "overall_score": 84.1,
            "availability_estimate": "99.95%",
            "engine_type": "full",
            "scenarios_passed": 138,
            "scenarios_failed": 14,
            "total_scenarios": 152,
            "critical_failures": [],
            "suggestions": [],
        },
        {
            "id": 999,
            "project_id": project_id,
            "created_at": _ago(86400 * 3),
            "overall_score": 79.6,
            "availability_estimate": "99.9%",
            "engine_type": "full",
            "scenarios_passed": 131,
            "scenarios_failed": 21,
            "total_scenarios": 152,
            "critical_failures": [],
            "suggestions": [],
        },
    ]
    return base_runs


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _supabase_configured() -> bool:
    return bool(
        os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )


def _supabase_request(method: str, table: str, params: str = "", body=None):
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        return None
    url = f"{supabase_url}/rest/v1/{table}{params}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Prefer": "return=representation",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def _handle_list_projects():
    if not _supabase_configured():
        return 200, _get_demo_projects()
    projects = _supabase_request("GET", "projects", "?order=updated_at.desc")
    if projects is None:
        return 200, _get_demo_projects()
    # Enrich with run stats
    for project in projects:
        runs = _supabase_request(
            "GET", "simulation_runs",
            f"?project_id=eq.{project['id']}&order=created_at.desc&limit=1"
        )
        if runs:
            project["last_score"] = runs[0].get("overall_score")
            project["last_run_at"] = runs[0].get("created_at")
        count_resp = _supabase_request(
            "GET", "simulation_runs",
            f"?project_id=eq.{project['id']}&select=id"
        )
        project["run_count"] = len(count_resp) if count_resp else 0
    return 200, projects


def _handle_get_project(project_id: str):
    if not _supabase_configured():
        projects = _get_demo_projects()
        project = next((p for p in projects if p["id"] == project_id), None)
        if not project:
            return 404, {"error": "Project not found"}
        runs = _get_demo_runs(project_id)
        return 200, {**project, "runs": runs}

    projects = _supabase_request("GET", "projects", f"?id=eq.{project_id}&limit=1")
    if not projects:
        return 404, {"error": "Project not found"}
    project = projects[0]
    runs = _supabase_request(
        "GET", "simulation_runs",
        f"?project_id=eq.{project_id}&order=created_at.desc&limit=50"
    ) or []
    if runs:
        project["last_score"] = runs[0].get("overall_score")
        project["last_run_at"] = runs[0].get("created_at")
    project["run_count"] = len(runs)
    return 200, {**project, "runs": runs}


def _handle_create_project(body: dict):
    name = body.get("name", "").strip()
    if not name:
        return 400, {"error": "'name' is required"}
    if not _supabase_configured():
        new_project = {
            "id": f"demo-{name.lower().replace(' ', '-')}-{int(datetime.now(timezone.utc).timestamp())}",
            "team_id": "demo-team",
            "name": name,
            "description": body.get("description", ""),
            "topology_yaml": body.get("topology_yaml"),
            "topology_type": body.get("topology_type", "manual"),
            "status": "active",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "last_score": None,
            "last_run_at": None,
            "run_count": 0,
        }
        return 201, new_project
    record = {
        "name": name,
        "description": body.get("description", ""),
        "topology_yaml": body.get("topology_yaml"),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    result = _supabase_request("POST", "projects", "", record)
    if not result:
        return 500, {"error": "Failed to create project"}
    created = result[0] if isinstance(result, list) else result
    return 201, {**created, "run_count": 0, "last_score": None, "last_run_at": None}


def _handle_update_project(project_id: str, body: dict):
    if not _supabase_configured():
        return 200, {"ok": True, "id": project_id, "demo": True}
    patch = {"updated_at": _now_iso()}
    for field in ("name", "description", "topology_yaml", "status"):
        if field in body:
            patch[field] = body[field]
    result = _supabase_request("PATCH", "projects", f"?id=eq.{project_id}", patch)
    if result is None:
        return 500, {"error": "Failed to update project"}
    updated = result[0] if isinstance(result, list) and result else patch
    return 200, updated


def _handle_delete_project(project_id: str):
    if not _supabase_configured():
        return 200, {"ok": True, "id": project_id, "demo": True}
    _supabase_request("DELETE", "projects", f"?id=eq.{project_id}")
    return 200, {"ok": True, "id": project_id}


# ---------------------------------------------------------------------------
# Handler class
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            project_id = query.get("id", [None])[0]

            if project_id:
                status, data = _handle_get_project(project_id)
            else:
                status, data = _handle_list_projects()
            self._json(status, data)
        except Exception as e:
            self._json(500, {"error": f"Projects GET error: {e}"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except (json.JSONDecodeError, ValueError):
            self._json(400, {"error": "Invalid JSON"})
            return
        try:
            status, data = _handle_create_project(body)
            self._json(status, data)
        except Exception as e:
            self._json(500, {"error": f"Projects POST error: {e}"})

    def do_PATCH(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except (json.JSONDecodeError, ValueError):
            self._json(400, {"error": "Invalid JSON"})
            return
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            project_id = query.get("id", [None])[0]
            if not project_id:
                self._json(400, {"error": "Missing ?id= parameter"})
                return
            status, data = _handle_update_project(project_id, body)
            self._json(status, data)
        except Exception as e:
            self._json(500, {"error": f"Projects PATCH error: {e}"})

    def do_DELETE(self):
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            project_id = query.get("id", [None])[0]
            if not project_id:
                self._json(400, {"error": "Missing ?id= parameter"})
                return
            status, data = _handle_delete_project(project_id)
            self._json(status, data)
        except Exception as e:
            self._json(500, {"error": f"Projects DELETE error: {e}"})

    def _json(self, status: int, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
