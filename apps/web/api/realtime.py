"""FaultRay realtime endpoint — merges apm + projects + chat + health.

Routes:
  GET  /api/apm/agents              -> list all agents
  GET  /api/apm/agents/{id}/metrics -> metrics for an agent
  GET  /api/apm/alerts              -> list alerts (optional ?severity= filter)
  GET  /api/apm/stats               -> aggregate stats
  POST /api/apm/metrics             -> ingest metrics batch
  POST /api/apm/agents/register     -> register new agent
  POST /api/apm/agents/{id}/heartbeat -> update heartbeat
  POST /api/apm/purge               -> purge old data

  GET  /api/projects           -> list all projects
  GET  /api/projects?id={id}   -> get single project with simulation runs
  POST /api/projects           -> create project
  PATCH /api/projects?id={id}  -> update project
  DELETE /api/projects?id={id} -> delete project

  POST /api/chat    Body: { "message": "..." } -> AI advice
  GET  /api/health  -> { status, engine, version }
  POST /api/health  -> admin check / plan switch

Path routing uses the request path to determine which handler to call.
"""

from http.server import BaseHTTPRequestHandler
import hmac
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta

_logger = logging.getLogger("faultray.realtime")

# Cap the request body so a spoofed/oversized Content-Length cannot exhaust
# memory before validation runs.
_MAX_BODY_BYTES = 1024 * 1024  # 1 MB


# ---------------------------------------------------------------------------
# APIVULN-02: Input sanitization helpers for Supabase PostgREST query params
# ---------------------------------------------------------------------------

_SAFE_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_SAFE_AGENT_ID_RE = re.compile(r"^[0-9a-zA-Z_\-]{1,64}$")
_SAFE_SEVERITY_RE = re.compile(r"^(critical|high|medium|low|warning|info)$", re.IGNORECASE)
_SAFE_METRIC_NAME_RE = re.compile(r"^[0-9a-zA-Z_\-.]{1,64}$")
_SAFE_POSITIVE_INT_RE = re.compile(r"^\d{1,6}$")


def _sanitize_agent_id(value: str) -> str | None:
    """Return value if safe, else None."""
    return value if _SAFE_AGENT_ID_RE.match(value) else None


def _sanitize_uuid(value: str) -> str | None:
    return value if _SAFE_UUID_RE.match(value) else None


def _sanitize_severity(value: str) -> str | None:
    return value.lower() if _SAFE_SEVERITY_RE.match(value) else None


def _sanitize_metric_name(value: str) -> str | None:
    return value if _SAFE_METRIC_NAME_RE.match(value) else None


def _sanitize_limit(value: str, default: int = 60, maximum: int = 200) -> int:
    if _SAFE_POSITIVE_INT_RE.match(value):
        return min(int(value), maximum)
    return default


# ===========================================================================
# APM — data and helpers
# ===========================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _get_demo_agents():
    return [
        {
            "agent_id": "agent-001",
            "hostname": "web-server-01",
            "ip_address": "10.0.1.10",
            "status": "running",
            "os_info": "Ubuntu 22.04",
            "version": "1.0.0",
            "labels": {},
            "registered_at": _ago(86400 * 7),
            "last_seen": _ago(15),
            "cpu_percent": 34.2,
            "memory_percent": 61.8,
            "disk_percent": 45.0,
        },
        {
            "agent_id": "agent-002",
            "hostname": "api-server-02",
            "ip_address": "10.0.1.11",
            "status": "running",
            "os_info": "Ubuntu 22.04",
            "version": "1.0.0",
            "labels": {},
            "registered_at": _ago(86400 * 7),
            "last_seen": _ago(8),
            "cpu_percent": 72.5,
            "memory_percent": 85.3,
            "disk_percent": 62.1,
        },
        {
            "agent_id": "agent-003",
            "hostname": "db-server-01",
            "ip_address": "10.0.1.20",
            "status": "degraded",
            "os_info": "Debian 12",
            "version": "1.0.0",
            "labels": {},
            "registered_at": _ago(86400 * 14),
            "last_seen": _ago(45),
            "cpu_percent": 91.3,
            "memory_percent": 78.2,
            "disk_percent": 88.7,
        },
        {
            "agent_id": "agent-004",
            "hostname": "cache-server-01",
            "ip_address": "10.0.1.30",
            "status": "offline",
            "os_info": "CentOS 8",
            "version": "1.0.0",
            "labels": {},
            "registered_at": _ago(86400 * 30),
            "last_seen": _ago(600),
            "cpu_percent": None,
            "memory_percent": None,
            "disk_percent": None,
        },
    ]


def _get_demo_alerts(severity_filter=None):
    alerts = [
        {
            "id": "alert-001",
            "agent_id": "agent-003",
            "severity": "CRITICAL",
            "rule_name": "high_cpu",
            "metric_name": "cpu_percent",
            "metric_value": 91.3,
            "threshold": 90.0,
            "message": "CPU usage 91.3% exceeds critical threshold 90%",
            "fired_at": _ago(300),
            "resolved_at": None,
        },
        {
            "id": "alert-002",
            "agent_id": "agent-003",
            "severity": "WARNING",
            "rule_name": "high_disk",
            "metric_name": "disk_percent",
            "metric_value": 88.7,
            "threshold": 80.0,
            "message": "Disk usage 88.7% exceeds warning threshold 80%",
            "fired_at": _ago(1200),
            "resolved_at": None,
        },
        {
            "id": "alert-003",
            "agent_id": "agent-002",
            "severity": "WARNING",
            "rule_name": "high_memory",
            "metric_name": "memory_percent",
            "metric_value": 85.3,
            "threshold": 80.0,
            "message": "Memory usage 85.3% exceeds warning threshold 80%",
            "fired_at": _ago(600),
            "resolved_at": None,
        },
        {
            "id": "alert-004",
            "agent_id": "agent-004",
            "severity": "CRITICAL",
            "rule_name": "agent_offline",
            "metric_name": None,
            "metric_value": None,
            "threshold": None,
            "message": "Agent cache-server-01 has been offline for >5 minutes",
            "fired_at": _ago(540),
            "resolved_at": None,
        },
    ]
    if severity_filter:
        # Demo data stores severities uppercase (CRITICAL/WARNING) while callers
        # pass the raw query value (e.g. 'critical'); compare case-insensitively.
        sev = str(severity_filter).upper()
        alerts = [a for a in alerts if a["severity"].upper() == sev]
    return alerts


def _get_demo_metrics(agent_id: str, metric_filter=None):
    import math
    now = datetime.now(timezone.utc)
    points = []
    metrics_config = {
        "cpu_percent": lambda i: round(50 + 20 * math.sin(i * 0.3) + (i % 3) * 2, 1),
        "memory_usage_percent": lambda i: round(60 + 10 * math.cos(i * 0.2), 1),
        "net_bytes_sent": lambda i: round(30 + 25 * math.sin(i * 0.15) + (i % 5) * 3, 1),
    }
    for name, fn in metrics_config.items():
        if metric_filter and name != metric_filter:
            continue
        for i in range(24):
            t = now - timedelta(minutes=i * 5)
            points.append({
                "metric_name": name,
                "value": fn(i),
                "sample_count": 1,
                "bucket_epoch": int(t.timestamp()),
            })
    return points


def _get_demo_stats():
    return {
        "total_agents": 4,
        "running": 2,
        "degraded": 1,
        "offline": 1,
        "total_alerts": 4,
        "critical_alerts": 2,
        "warning_alerts": 2,
        "info_alerts": 0,
        "avg_cpu_percent": 52.0,
        "avg_memory_percent": 61.0,
        "avg_disk_percent": 51.9,
        "metrics_last_hour": 240,
        "generated_at": _now_iso(),
    }


def _apm_supabase_configured() -> bool:
    return bool(
        os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )


def _apm_supabase_request(method: str, table: str, params: str = "", body=None):
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


def _validate_api_key(headers) -> bool:
    expected = os.environ.get("FAULTRAY_APM_API_KEY", "")
    # RT-01 fix: if the key is not configured, deny all access rather than
    # allowing it.  An unconfigured key is a misconfiguration, not a signal
    # to skip authentication.
    if not expected:
        return False
    provided = headers.get("X-API-Key", "")
    # Constant-time compare — a plain == leaks the key length/prefix to a
    # timing oracle.
    return hmac.compare_digest(provided, expected)


def _bearer_token(headers):
    """Extract the Bearer token from the Authorization header, or None."""
    auth = headers.get("Authorization") or headers.get("authorization") or ""
    if auth.startswith("Bearer "):
        token = auth[len("Bearer "):].strip()
        return token or None
    return None


def _resolve_user_id(headers):
    """Validate the caller's Supabase access token and return their user id.

    Uses the GoTrue ``/auth/v1/user`` endpoint so no JWT signing secret is
    required — the anon key (already in the function env) plus the user's
    token is enough. Returns None for a missing or invalid token.
    """
    token = _bearer_token(headers)
    if not token:
        return None
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    if not supabase_url or not anon_key:
        return None
    req = urllib.request.Request(
        f"{supabase_url}/auth/v1/user",
        method="GET",
        headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception:
        return None
    uid = data.get("id") if isinstance(data, dict) else None
    return uid if isinstance(uid, str) and _sanitize_uuid(uid) else None


def _resolve_user(headers):
    """Validate the caller's Supabase access token and return the verified
    user dict ({"id", "email", ...}) from GoTrue ``/auth/v1/user``, or None.

    Authorization decisions MUST use this verified identity — never a
    client-supplied email/id from the request body (SEC U33).
    """
    token = _bearer_token(headers)
    if not token:
        return None
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    anon_key = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    if not supabase_url or not anon_key:
        return None
    req = urllib.request.Request(
        f"{supabase_url}/auth/v1/user",
        method="GET",
        headers={"apikey": anon_key, "Authorization": f"Bearer {token}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception:
        return None
    return data if isinstance(data, dict) and data.get("id") else None


def _user_team_ids(user_id: str) -> list:
    """Resolve every team the user belongs to (owned or member).

    Uses the service-role client; ``user_id`` is already validated as a UUID.
    Resolution covers ``teams.owner_id`` because the signup trigger creates a
    personal team for each user but does not populate ``team_members``.
    """
    team_ids = set()
    owned = _proj_supabase_request("GET", "teams", f"?owner_id=eq.{user_id}&select=id")
    for row in owned or []:
        if row.get("id"):
            team_ids.add(row["id"])
    member = _proj_supabase_request(
        "GET", "team_members", f"?user_id=eq.{user_id}&select=team_id"
    )
    for row in member or []:
        if row.get("team_id"):
            team_ids.add(row["team_id"])
    return [tid for tid in team_ids if _sanitize_uuid(str(tid))]


def _apm_list_agents():
    if not _apm_supabase_configured():
        return 200, _get_demo_agents()
    agents = _apm_supabase_request("GET", "apm_agents", "?order=last_seen.desc")
    if agents is None:
        return 200, _get_demo_agents()
    return 200, agents


def _apm_agent_metrics(agent_id: str, query_params: dict):
    metric_name = query_params.get("metric_name", [None])[0]
    if not _apm_supabase_configured():
        return 200, _get_demo_metrics(agent_id, metric_name)
    # APIVULN-02 fix: sanitize all user-controlled query params before use in URL
    safe_agent_id = _sanitize_agent_id(agent_id)
    if not safe_agent_id:
        return 400, {"error": "Invalid agent_id format"}
    raw_limit = query_params.get("limit", ["60"])[0]
    safe_limit = _sanitize_limit(raw_limit, default=60, maximum=200)
    params = f"?agent_id=eq.{safe_agent_id}&order=collected_at.desc&limit={safe_limit}"
    if metric_name:
        safe_metric_name = _sanitize_metric_name(metric_name)
        # Reject an invalid filter rather than silently dropping it and returning
        # ALL metrics for the agent (over-disclosure of unrequested data).
        if not safe_metric_name:
            return 400, {"error": "Invalid metric_name format"}
        params += f"&metric_name=eq.{safe_metric_name}"
    metrics = _apm_supabase_request("GET", "apm_metrics", params)
    if metrics is None:
        return 200, _get_demo_metrics(agent_id)
    return 200, metrics


def _apm_list_alerts(query_params: dict):
    severity = query_params.get("severity", [None])[0]
    if not _apm_supabase_configured():
        return 200, _get_demo_alerts(severity)
    params = "?order=fired_at.desc&limit=100"
    if severity:
        # APIVULN-02 fix: validate severity before embedding in URL. Reject an
        # invalid filter rather than silently dropping it and returning ALL
        # alerts (over-disclosure of unrequested data).
        safe_severity = _sanitize_severity(severity)
        if not safe_severity:
            return 400, {"error": "Invalid severity filter"}
        params += f"&severity=eq.{safe_severity}"
    alerts = _apm_supabase_request("GET", "apm_alerts", params)
    if alerts is None:
        return 200, _get_demo_alerts(severity)
    return 200, alerts


def _apm_stats():
    if not _apm_supabase_configured():
        return 200, _get_demo_stats()
    agents = _apm_supabase_request("GET", "apm_agents", "")
    alerts = _apm_supabase_request("GET", "apm_alerts", "?resolved_at=is.null")
    if agents is None:
        return 200, _get_demo_stats()
    total = len(agents)
    running = sum(1 for a in agents if a.get("status") == "running")
    degraded = sum(1 for a in agents if a.get("status") == "degraded")
    offline = sum(1 for a in agents if a.get("status") == "offline")
    critical_alerts = 0
    warning_alerts = 0
    info_alerts = 0
    if alerts:
        critical_alerts = sum(1 for a in alerts if a.get("severity", "").upper() == "CRITICAL")
        warning_alerts = sum(1 for a in alerts if a.get("severity", "").upper() == "WARNING")
        info_alerts = sum(1 for a in alerts if a.get("severity", "").upper() == "INFO")
    return 200, {
        "total_agents": total,
        "running": running,
        "degraded": degraded,
        "offline": offline,
        "total_alerts": len(alerts) if alerts else 0,
        "critical_alerts": critical_alerts,
        "warning_alerts": warning_alerts,
        "info_alerts": info_alerts,
        "generated_at": _now_iso(),
    }


def _apm_ingest_metrics(body: dict, headers) -> tuple:
    if not _validate_api_key(headers):
        return 401, {"error": "Invalid or missing X-API-Key"}
    if not _apm_supabase_configured():
        return 200, {"ok": True, "inserted": 0, "demo": True}
    metrics = body.get("metrics", [])
    if not isinstance(metrics, list):
        return 400, {"error": "'metrics' must be a list"}
    if not metrics:
        return 200, {"ok": True, "inserted": 0}
    result = _apm_supabase_request("POST", "apm_metrics", "", metrics)
    inserted = len(result) if result else 0
    return 200, {"ok": True, "inserted": inserted}


def _apm_register_agent(body: dict, headers) -> tuple:
    if not _validate_api_key(headers):
        return 401, {"error": "Invalid or missing X-API-Key"}
    agent_id = body.get("agent_id", "")
    hostname = body.get("hostname", "")
    # A non-string value (number/object/null) would crash on .strip(); reject it.
    if not isinstance(agent_id, str) or not isinstance(hostname, str):
        return 400, {"error": "'agent_id' and 'hostname' must be strings"}
    agent_id = agent_id.strip()
    hostname = hostname.strip()
    if not agent_id or not hostname:
        return 400, {"error": "'agent_id' and 'hostname' are required"}
    # Enforce the same agent_id format the read/heartbeat paths require, so a
    # registration can't create a record those paths later reject (orphaned row).
    if not _sanitize_agent_id(agent_id):
        return 400, {"error": "Invalid agent_id format"}
    if not _apm_supabase_configured():
        return 200, {"ok": True, "agent_id": agent_id, "demo": True}
    record = {
        "agent_id": agent_id,
        "hostname": hostname,
        "ip_address": body.get("ip_address"),
        "os_info": body.get("os_info"),
        "version": body.get("version"),
        "labels": body.get("labels", {}),
        "status": "running",
        "last_seen": _now_iso(),
    }
    _apm_supabase_request("POST", "apm_agents", "?on_conflict=agent_id", record)
    return 200, {"ok": True, "agent_id": agent_id}


def _apm_heartbeat(agent_id: str, body: dict, headers) -> tuple:
    if not _validate_api_key(headers):
        return 401, {"error": "Invalid or missing X-API-Key"}
    if not _apm_supabase_configured():
        return 200, {"ok": True, "agent_id": agent_id, "demo": True}
    # APIVULN-02: agent_id arrives from the URL path — sanitize before it is
    # embedded in the PostgREST filter, matching the other APM read paths.
    safe_agent_id = _sanitize_agent_id(agent_id)
    if not safe_agent_id:
        return 400, {"error": "Invalid agent_id format"}
    patch = {"last_seen": _now_iso()}
    if "status" in body:
        # Constrain to the known enum; aggregations (_apm_stats) assume a bounded
        # vocabulary, and an arbitrary/oversized string would corrupt counts.
        if body["status"] not in ("running", "degraded", "offline"):
            return 400, {"error": "Invalid status"}
        patch["status"] = body["status"]
    for field in ("cpu_percent", "memory_percent", "disk_percent"):
        if field in body:
            patch[field] = body[field]
    _apm_supabase_request("PATCH", "apm_agents", f"?agent_id=eq.{safe_agent_id}", patch)
    return 200, {"ok": True, "agent_id": safe_agent_id}


def _apm_purge(body: dict, headers) -> tuple:
    if not _validate_api_key(headers):
        return 401, {"error": "Invalid or missing X-API-Key"}
    if not _apm_supabase_configured():
        return 200, {"ok": True, "demo": True}
    # older_than_days is untrusted: a non-numeric string raises ValueError and a
    # null/list/dict raises TypeError. Validate and bound it to a sane range.
    raw_days = body.get("older_than_days", 7)
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        return 400, {"error": "'older_than_days' must be an integer"}
    if days < 0 or days > 36500:
        return 400, {"error": "'older_than_days' is out of range"}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    _apm_supabase_request("DELETE", "apm_metrics", f"?collected_at=lt.{cutoff}")
    return 200, {"ok": True, "purged_before": cutoff}


# ===========================================================================
# PROJECTS — data and helpers
# ===========================================================================

def _proj_supabase_configured() -> bool:
    return bool(
        os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )


def _proj_supabase_request(method: str, table: str, params: str = "", body=None):
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
    return [
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


def _proj_list(team_ids):
    # team_ids is None in demo mode (Supabase unconfigured); otherwise a list
    # of the caller's team UUIDs (possibly empty) used to scope the query.
    if team_ids is None:
        return 200, _get_demo_projects()
    if not team_ids:
        return 200, []
    in_list = ",".join(team_ids)
    projects = _proj_supabase_request(
        "GET", "projects", f"?team_id=in.({in_list})&order=updated_at.desc"
    )
    if projects is None:
        return 200, []
    for project in projects:
        runs = _proj_supabase_request(
            "GET", "simulation_runs",
            f"?project_id=eq.{project['id']}&order=created_at.desc&limit=1",
        )
        if runs:
            project["last_score"] = runs[0].get("overall_score")
            project["last_run_at"] = runs[0].get("created_at")
        count_resp = _proj_supabase_request(
            "GET", "simulation_runs",
            f"?project_id=eq.{project['id']}&select=id",
        )
        project["run_count"] = len(count_resp) if count_resp else 0
    return 200, projects


def _proj_get(project_id: str, team_ids):
    # SUPA-01 / APIVULN-02 fix: validate project_id before embedding in URL query
    safe_project_id = _sanitize_uuid(project_id)
    if not safe_project_id:
        return 400, {"error": "Invalid project_id format (must be UUID)"}
    if team_ids is None:  # demo mode
        projects = _get_demo_projects()
        project = next((p for p in projects if p["id"] == safe_project_id), None)
        if not project:
            return 404, {"error": "Project not found"}
        runs = _get_demo_runs(safe_project_id)
        return 200, {**project, "runs": runs}
    projects = _proj_supabase_request("GET", "projects", f"?id=eq.{safe_project_id}&limit=1")
    if not projects:
        return 404, {"error": "Project not found"}
    project = projects[0]
    # Tenant guard: a project outside the caller's team(s) must look identical
    # to one that does not exist (no existence oracle).
    if project.get("team_id") not in team_ids:
        return 404, {"error": "Project not found"}
    runs = _proj_supabase_request(
        "GET", "simulation_runs",
        f"?project_id=eq.{safe_project_id}&order=created_at.desc&limit=50",
    ) or []
    if runs:
        project["last_score"] = runs[0].get("overall_score")
        project["last_run_at"] = runs[0].get("created_at")
    project["run_count"] = len(runs)
    return 200, {**project, "runs": runs}


def _proj_owned_by(safe_project_id: str, team_ids) -> bool:
    """True if the project belongs to one of the caller's teams."""
    rows = _proj_supabase_request(
        "GET", "projects", f"?id=eq.{safe_project_id}&select=team_id&limit=1"
    )
    return bool(rows) and rows[0].get("team_id") in team_ids


def _proj_create(body: dict, team_ids):
    name = body.get("name", "")
    if not isinstance(name, str):
        return 400, {"error": "'name' must be a string"}
    name = name.strip()
    if not name:
        return 400, {"error": "'name' is required"}
    if team_ids is None:  # demo mode
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
    if not team_ids:
        return 403, {"error": "No team is associated with this account"}
    # Stamp the owner's team so the row is scoped (and visible) to them. The
    # previous code left team_id NULL, which is why every project was orphaned
    # and only reachable through the unfiltered service-role list.
    record = {
        "name": name,
        "description": body.get("description", ""),
        "topology_yaml": body.get("topology_yaml"),
        "team_id": team_ids[0],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    result = _proj_supabase_request("POST", "projects", "", record)
    if not result:
        return 500, {"error": "Failed to create project"}
    created = result[0] if isinstance(result, list) else result
    return 201, {**created, "run_count": 0, "last_score": None, "last_run_at": None}


def _proj_update(project_id: str, body: dict, team_ids):
    safe_project_id = _sanitize_uuid(project_id)
    if not safe_project_id:
        return 400, {"error": "Invalid project_id format (must be UUID)"}
    if team_ids is None:  # demo mode
        return 200, {"ok": True, "id": safe_project_id, "demo": True}
    if not _proj_owned_by(safe_project_id, team_ids):
        return 404, {"error": "Project not found"}
    patch = {"updated_at": _now_iso()}
    for field in ("name", "description", "topology_yaml", "status"):
        if field in body:
            patch[field] = body[field]
    result = _proj_supabase_request("PATCH", "projects", f"?id=eq.{safe_project_id}", patch)
    if result is None:
        return 500, {"error": "Failed to update project"}
    updated = result[0] if isinstance(result, list) and result else patch
    return 200, updated


def _proj_delete(project_id: str, team_ids):
    safe_project_id = _sanitize_uuid(project_id)
    if not safe_project_id:
        return 400, {"error": "Invalid project_id format (must be UUID)"}
    if team_ids is None:  # demo mode
        return 200, {"ok": True, "id": safe_project_id, "demo": True}
    if not _proj_owned_by(safe_project_id, team_ids):
        return 404, {"error": "Project not found"}
    _proj_supabase_request("DELETE", "projects", f"?id=eq.{safe_project_id}")
    return 200, {"ok": True, "id": safe_project_id}


# ===========================================================================
# CHAT — knowledge base and response
# ===========================================================================

KNOWLEDGE_BASE = {
    "availability": "FaultRay calculates availability using a 3-layer model: Hardware (physical redundancy), Software (application resilience), and Theoretical (mathematical upper bound). The final score is the minimum of these three layers, as a system is only as reliable as its weakest link.",
    "replicas": "Adding replicas improves availability by providing failover capacity. The relationship is roughly logarithmic - going from 1 to 2 replicas has the biggest impact. For databases, consider read replicas for read-heavy workloads and multi-primary for write-heavy workloads.",
    "circuit breaker": "Circuit breakers prevent cascading failures by detecting failing downstream services and short-circuiting requests. Implement with three states: Closed (normal), Open (failing, return fallback), Half-Open (testing recovery). Libraries: resilience4j (Java), Polly (.NET), pybreaker (Python).",
    "failover": "Automatic failover reduces MTTR (Mean Time To Repair). For databases, configure promotion time under 30 seconds. For application servers, use health checks with 10-second intervals. Always test failover procedures with chaos engineering.",
    "compliance": "FaultRay supports DORA, SOC2, ISO27001, PCI-DSS, HIPAA, and GDPR frameworks. Each framework has specific controls related to system resilience, disaster recovery, and business continuity.",
    "score": "The FaultRay resilience score (0-100) represents your infrastructure's ability to withstand failures. Score breakdown: 90-100 (Excellent), 70-89 (Good), 50-69 (Needs Work), 0-49 (Critical). The score is derived from 2,000+ chaos scenarios.",
}


def _generate_chat_response(message: str) -> dict:
    """Generate an AI response based on the message."""
    message_lower = message.lower()
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
            "FaultRay is a research-prototype pre-deployment resilience simulation platform "
            "that analyses your infrastructure's structural resilience through model-based "
            "simulation. It runs thousands of failure scenarios against your declared "
            "infrastructure topology without touching production. Result accuracy depends on "
            "how completely your topology is declared. Key features include:\n\n"
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


# ===========================================================================
# HEALTH — admin helpers
# ===========================================================================

def _is_admin(email: str) -> bool:
    admin_emails = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]
    return email.strip().lower() in admin_emails


_SAFE_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _sanitize_email(email: str) -> str | None:
    """Return URL-encoded email if format is safe, else None."""
    cleaned = email.strip().lower()
    if _SAFE_EMAIL_RE.match(cleaned):
        return urllib.parse.quote(cleaned, safe="")
    return None


def _switch_plan(email: str, plan: str) -> dict:
    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        return {"error": "Supabase not configured"}
    if plan not in ("free", "pro", "business"):
        return {"error": f"Invalid plan: {plan}"}
    # SUPA-01 / APIVULN-02 fix: sanitize and URL-encode email before embedding in query
    safe_email = _sanitize_email(email)
    if not safe_email:
        return {"error": "Invalid email format"}
    data = json.dumps({"plan": plan}).encode()
    req = urllib.request.Request(
        f"{supabase_url}/rest/v1/profiles?email=eq.{safe_email}",
        data=data,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Prefer": "return=representation",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        if result:
            return {"ok": True, "plan": result[0].get("plan", plan)}
        return {"error": "Profile not found"}
    except Exception:
        _logger.exception("Plan switch failed")
        return {"error": "Plan update failed"}


# ===========================================================================
# Handler — routes by path
# ===========================================================================

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            query = parse_qs(parsed.query)

            if "/apm" in path:
                self._handle_apm_get(path, query)
            elif "/projects" in path:
                self._handle_projects_get(query)
            elif "/health" in path:
                self._handle_health_get()
            else:
                # Default: health check
                self._handle_health_get()

        except Exception:
            _logger.exception("Realtime GET failed")
            self._json(500, {"error": "Internal server error"})

    def _read_json_body(self):
        """Read and JSON-parse the request body with a size cap.

        Returns (body, error). On error, the response has already been sent and
        the caller must return. Caps Content-Length BEFORE reading so a spoofed/
        oversized/negative length cannot exhaust memory or block on read-to-EOF.
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._json(400, {"error": "Invalid Content-Length header"})
            return None, True
        if length < 0:
            self._json(400, {"error": "Invalid Content-Length header"})
            return None, True
        if length > _MAX_BODY_BYTES:
            self._json(413, {"error": "Request body too large"})
            return None, True
        try:
            raw = self.rfile.read(length) if length else b""
            return (json.loads(raw) if raw else {}), False
        except (json.JSONDecodeError, ValueError):
            self._json(400, {"error": "Invalid JSON"})
            return None, True

    def do_POST(self):
        body, err = self._read_json_body()
        if err:
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # Wrap dispatch so any unhandled error (e.g. a network failure resolving
        # the caller) returns a JSON 500 instead of aborting the connection.
        try:
            if "/apm" in path:
                self._handle_apm_post(path, body)
            elif "/projects" in path:
                self._handle_projects_post(body)
            elif "/health" in path:
                self._handle_health_post(body)
            elif "/chat" in path:
                self._handle_chat_post(body)
            else:
                # Default: chat
                self._handle_chat_post(body)
        except Exception:
            _logger.exception("Realtime POST failed")
            self._json(500, {"error": "Internal server error"})

    def do_PATCH(self):
        body, err = self._read_json_body()
        if err:
            return
        try:
            team_ids, err = self._project_team_scope()
            if err:
                self._json(*err)
                return
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            project_id = query.get("id", [None])[0]
            if not project_id:
                self._json(400, {"error": "Missing ?id= parameter"})
                return
            status, data = _proj_update(project_id, body, team_ids)
            self._json(status, data)
        except Exception:
            self._json(500, {"error": "Project update failed"})

    def do_DELETE(self):
        try:
            team_ids, err = self._project_team_scope()
            if err:
                self._json(*err)
                return
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            project_id = query.get("id", [None])[0]
            if not project_id:
                self._json(400, {"error": "Missing ?id= parameter"})
                return
            status, data = _proj_delete(project_id, team_ids)
            self._json(status, data)
        except Exception:
            self._json(500, {"error": "Project deletion failed"})

    # -----------------------------------------------------------------------
    # APM
    # -----------------------------------------------------------------------

    def _handle_apm_get(self, path: str, query: dict):
        # APM data has no tenant column (global infra monitoring). Require the
        # shared API key once real data is configured so agent hostnames/IPs
        # and metrics are not world-readable; POST handlers already enforce it.
        if _apm_supabase_configured() and not _validate_api_key(self.headers):
            self._json(401, {"error": "Invalid or missing X-API-Key"})
            return
        if path == "/api/apm/agents":
            status, data = _apm_list_agents()
            self._json(status, data)
        elif "/metrics" in path and "/agents/" in path:
            after_agents = path.split("/agents/", 1)[1]
            agent_id = after_agents.replace("/metrics", "")
            status, data = _apm_agent_metrics(agent_id, query)
            self._json(status, data)
        elif path == "/api/apm/alerts":
            status, data = _apm_list_alerts(query)
            self._json(status, data)
        elif path == "/api/apm/stats":
            status, data = _apm_stats()
            self._json(status, data)
        else:
            self._json(404, {"error": f"Unknown APM endpoint: {path}"})

    def _handle_apm_post(self, path: str, body: dict):
        if path == "/api/apm/metrics":
            status, data = _apm_ingest_metrics(body, self.headers)
            self._json(status, data)
        elif path == "/api/apm/agents/register":
            status, data = _apm_register_agent(body, self.headers)
            self._json(status, data)
        elif "/heartbeat" in path and "/agents/" in path:
            after_agents = path.split("/agents/", 1)[1]
            agent_id = after_agents.replace("/heartbeat", "")
            status, data = _apm_heartbeat(agent_id, body, self.headers)
            self._json(status, data)
        elif path == "/api/apm/purge":
            status, data = _apm_purge(body, self.headers)
            self._json(status, data)
        else:
            self._json(404, {"error": f"Unknown APM endpoint: {path}"})

    # -----------------------------------------------------------------------
    # Projects
    # -----------------------------------------------------------------------

    def _project_team_scope(self):
        """Resolve the caller's team scope for the /api/projects endpoints.

        Returns ``(team_ids, error)``:
          - ``error`` is None on success, or ``(status, body)`` to return.
          - ``team_ids`` is None in demo mode (Supabase unconfigured),
            otherwise the list of the caller's team UUIDs.
        """
        if not _proj_supabase_configured():
            return None, None
        user_id = _resolve_user_id(self.headers)
        if not user_id:
            return None, (401, {"error": "Authentication required"})
        return _user_team_ids(user_id), None

    def _handle_projects_get(self, query: dict):
        team_ids, err = self._project_team_scope()
        if err:
            self._json(*err)
            return
        project_id = query.get("id", [None])[0]
        if project_id:
            status, data = _proj_get(project_id, team_ids)
        else:
            status, data = _proj_list(team_ids)
        self._json(status, data)

    def _handle_projects_post(self, body: dict):
        team_ids, err = self._project_team_scope()
        if err:
            self._json(*err)
            return
        try:
            status, data = _proj_create(body, team_ids)
            self._json(status, data)
        except Exception:
            self._json(500, {"error": "Project creation failed"})

    # -----------------------------------------------------------------------
    # Chat
    # -----------------------------------------------------------------------

    def _handle_chat_post(self, data: dict):
        message = data.get("message", "")
        # _generate_chat_response calls message.lower(); a non-string truthy value
        # (number/object) would raise. Require a non-empty string.
        if not isinstance(message, str) or not message.strip():
            self._json(400, {"error": {"message": "Missing 'message' in request body"}})
            return
        try:
            result = _generate_chat_response(message)
            self._json(200, result)
        except Exception as e:
            self._json(500, {"error": {"message": f"Chat error: {e}"}})

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------

    def _handle_health_get(self):
        try:
            import faultray
            version = faultray.__version__
        except Exception:
            version = "unknown"
        self._json(200, {"status": "ok", "engine": "faultray", "version": version})

    def _handle_health_post(self, data: dict):
        # SEC (U33): authorization MUST be derived from the verified session,
        # never from a client-supplied email. We verify the caller's Supabase
        # access token and use the email embedded in it; the request-body
        # `email` is ignored. This removes both the unauthenticated, service-
        # role plan mutation and the admin-enumeration oracle.
        user = _resolve_user(self.headers)
        caller_email = str((user or {}).get("email", "")).strip().lower()
        if not caller_email:
            self._json(401, {"error": "Authentication required"})
            return
        action = data.get("action", "admin-check")
        is_admin = _is_admin(caller_email)
        if action == "admin-check":
            # Authenticated caller learns only their OWN admin status.
            self._json(200, {"is_admin": is_admin})
        elif action == "switch-plan":
            if not is_admin:
                self._json(403, {"error": "Not authorized"})
                return
            # Operate only on the authenticated admin's own account.
            result = _switch_plan(caller_email, data.get("plan", ""))
            self._json(400 if "error" in result else 200, result)
        else:
            self._json(200, {"is_admin": is_admin})

    # -----------------------------------------------------------------------
    # Shared helpers
    # -----------------------------------------------------------------------

    def _json(self, status: int, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        allowed_origin = os.environ.get("FAULTRAY_ALLOWED_ORIGIN", "https://faultray.com")
        self.send_header("Access-Control-Allow-Origin", allowed_origin)
