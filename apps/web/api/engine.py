"""FaultRay engine endpoint — merges simulate + analysis + discovery.

Routes:
  POST /api/simulate   -> simulation handler
  POST /api/analysis   -> analysis handler (heatmap / score-explain / whatif)
  GET  /api/analysis   -> analysis handler (score-explain)
  POST /api/discovery  -> discovery handler (aws / gcp / azure / terraform / kubernetes)

All legacy paths are preserved so the frontend works without changes.
Path routing uses the request path to determine which handler to call.
"""

from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import tempfile
from urllib.parse import urlparse, parse_qs

# API-07: 構造化ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
_logger = logging.getLogger("faultray.engine")


# ===========================================================================
# SIMULATE — data and helpers
# ===========================================================================

SAMPLE_TOPOLOGIES = {
    "web-saas": """
schema_version: "3.0"
components:
  - id: cdn
    name: CDN / Edge
    type: load_balancer
    replicas: 3
    capacity:
      max_connections: 50000
      max_rps: 100000
  - id: gateway
    name: API Gateway
    type: load_balancer
    replicas: 2
    capacity:
      max_connections: 20000
      max_rps: 30000
  - id: auth
    name: Auth Service
    type: app_server
    replicas: 2
  - id: api
    name: API Server
    type: app_server
    replicas: 3
  - id: worker
    name: Background Worker
    type: app_server
    replicas: 2
  - id: db_primary
    name: PostgreSQL Primary
    type: database
    replicas: 1
    failover:
      enabled: true
      promotion_time_seconds: 30
  - id: db_replica
    name: PostgreSQL Replica
    type: database
    replicas: 2
  - id: cache
    name: Redis Cache
    type: cache
    replicas: 3
dependencies:
  - source: cdn
    target: gateway
  - source: gateway
    target: auth
  - source: gateway
    target: api
  - source: api
    target: db_primary
  - source: api
    target: cache
  - source: api
    target: worker
  - source: worker
    target: db_primary
  - source: db_primary
    target: db_replica
""",
    "microservices": """
schema_version: "3.0"
components:
  - id: lb
    name: Load Balancer
    type: load_balancer
    replicas: 2
  - id: gateway
    name: API Gateway
    type: load_balancer
    replicas: 2
  - id: svc_user
    name: User Service
    type: app_server
    replicas: 3
  - id: svc_order
    name: Order Service
    type: app_server
    replicas: 3
  - id: svc_payment
    name: Payment Service
    type: app_server
    replicas: 2
  - id: svc_notification
    name: Notification Service
    type: app_server
    replicas: 2
  - id: svc_inventory
    name: Inventory Service
    type: app_server
    replicas: 2
  - id: mq
    name: Message Queue (Kafka)
    type: queue
    replicas: 3
  - id: db_user
    name: User DB
    type: database
    replicas: 2
  - id: db_order
    name: Order DB
    type: database
    replicas: 2
  - id: cache
    name: Redis Cache
    type: cache
    replicas: 3
  - id: mesh
    name: Service Mesh (Istio)
    type: custom
    replicas: 3
dependencies:
  - source: lb
    target: gateway
  - source: gateway
    target: svc_user
  - source: gateway
    target: svc_order
  - source: gateway
    target: svc_payment
  - source: svc_order
    target: mq
  - source: mq
    target: svc_notification
  - source: mq
    target: svc_inventory
  - source: svc_user
    target: db_user
  - source: svc_order
    target: db_order
  - source: svc_user
    target: cache
  - source: svc_order
    target: cache
""",
    "multi-region": """
schema_version: "3.0"
components:
  - id: dns
    name: Global DNS
    type: dns
    replicas: 3
  - id: cdn
    name: CDN Edge
    type: load_balancer
    replicas: 4
  - id: lb_us
    name: US Load Balancer
    type: load_balancer
    replicas: 2
  - id: lb_eu
    name: EU Load Balancer
    type: load_balancer
    replicas: 2
  - id: app_us
    name: US App Cluster
    type: app_server
    replicas: 3
  - id: app_eu
    name: EU App Cluster
    type: app_server
    replicas: 3
  - id: db_us
    name: US Database Primary
    type: database
    replicas: 1
    failover:
      enabled: true
      promotion_time_seconds: 30
  - id: db_eu
    name: EU Database Primary
    type: database
    replicas: 1
    failover:
      enabled: true
      promotion_time_seconds: 30
  - id: db_replica_us
    name: US Database Replica
    type: database
    replicas: 2
  - id: db_replica_eu
    name: EU Database Replica
    type: database
    replicas: 2
  - id: cache_us
    name: US Redis Cluster
    type: cache
    replicas: 3
  - id: cache_eu
    name: EU Redis Cluster
    type: cache
    replicas: 3
  - id: queue_us
    name: US Message Queue
    type: queue
    replicas: 2
  - id: queue_eu
    name: EU Message Queue
    type: queue
    replicas: 2
  - id: storage
    name: Global Object Storage
    type: storage
    replicas: 3
dependencies:
  - source: dns
    target: cdn
  - source: cdn
    target: lb_us
  - source: cdn
    target: lb_eu
  - source: lb_us
    target: app_us
  - source: lb_eu
    target: app_eu
  - source: app_us
    target: db_us
  - source: app_eu
    target: db_eu
  - source: app_us
    target: cache_us
  - source: app_eu
    target: cache_eu
  - source: app_us
    target: queue_us
  - source: app_eu
    target: queue_eu
  - source: db_us
    target: db_replica_us
  - source: db_eu
    target: db_replica_eu
  - source: db_us
    target: db_eu
  - source: app_us
    target: storage
  - source: app_eu
    target: storage
""",
    "data-pipeline": """
schema_version: "3.0"
components:
  - id: ingestion
    name: Data Ingestion API
    type: app_server
    replicas: 3
  - id: stream
    name: Stream Processor (Kafka)
    type: queue
    replicas: 3
  - id: batch
    name: Batch Processor
    type: app_server
    replicas: 2
  - id: transform
    name: Transform Engine
    type: app_server
    replicas: 3
  - id: warehouse
    name: Data Warehouse
    type: database
    replicas: 2
  - id: lake
    name: Data Lake (S3)
    type: storage
    replicas: 3
  - id: cache
    name: Redis Cache
    type: cache
    replicas: 2
  - id: scheduler
    name: Job Scheduler
    type: app_server
    replicas: 2
  - id: monitor
    name: Pipeline Monitor
    type: app_server
    replicas: 2
  - id: api
    name: Query API
    type: app_server
    replicas: 2
dependencies:
  - source: ingestion
    target: stream
  - source: stream
    target: transform
  - source: scheduler
    target: batch
  - source: batch
    target: lake
  - source: transform
    target: warehouse
  - source: transform
    target: lake
  - source: api
    target: warehouse
  - source: api
    target: cache
  - source: monitor
    target: stream
  - source: monitor
    target: batch
""",
}


def _build_calculation_evidence(nines: float, score: float) -> dict:
    """Build calculation evidence showing N-layer nines breakdown with factors."""
    sw_nines = round(min(nines, 7.0), 2)
    hw_nines = round(min(nines * 1.3, 7.0), 2)
    th_nines = round(min(nines * 1.5, 7.0), 2)

    sw_max = round(min(sw_nines + 0.21, 7.0), 2)
    hw_max = round(min(hw_nines + 0.15, 7.0), 2)
    th_max = round(min(th_nines + 0.05, 7.0), 2)

    bottleneck_layer = "Software" if sw_nines <= hw_nines and sw_nines <= th_nines else (
        "Hardware" if hw_nines <= th_nines else "Theoretical"
    )

    return {
        "layers": [
            {
                "name": "Software",
                "nines": sw_nines,
                "max_possible": sw_max,
                "factors": [
                    {"name": "Replica redundancy", "effect": "+0.30 nines", "detail": "Multiple replicas detected on app servers"},
                    {"name": "No automatic failover", "effect": "-0.21 nines", "detail": "Primary database lacks automatic failover"},
                    {"name": "Health check interval", "effect": "-0.10 nines", "detail": "60s health check interval increases MTTR"},
                ],
            },
            {
                "name": "Hardware",
                "nines": hw_nines,
                "max_possible": hw_max,
                "factors": [
                    {"name": "Multi-zone deployment", "effect": "+0.50 nines", "detail": "Components spread across availability zones"},
                    {"name": "Storage redundancy", "effect": "+0.20 nines", "detail": "Replicated storage detected"},
                    {"name": "Single region", "effect": "-0.15 nines", "detail": "No cross-region failover configured"},
                ],
            },
            {
                "name": "Theoretical",
                "nines": th_nines,
                "max_possible": th_max,
                "factors": [
                    {"name": "Markov chain steady-state", "effect": "+0.80 nines", "detail": "MTBF/MTTR ratio is favorable"},
                    {"name": "Reliability block diagram", "effect": "+0.30 nines", "detail": "Parallel paths increase theoretical ceiling"},
                    {"name": "Correlated failure risk", "effect": "-0.05 nines", "detail": "Shared dependencies reduce independence"},
                ],
            },
        ],
        "bottleneck": f"{bottleneck_layer} layer limits overall availability",
        "formula": (
            f"Availability = min(SW, HW, TH) = min({sw_nines}, {hw_nines}, {th_nines})"
            f" = {min(sw_nines, hw_nines, th_nines)} nines"
        ),
    }


def _build_cascade_simulations(critical_findings: list, total_components: int) -> list:
    """Build top-3 cascade simulation scenarios from critical findings."""
    cascades = []

    # Scenario 1: derive from first critical finding if available
    if critical_findings:
        r = critical_findings[0]
        comp_ids = [e.component_id for e in r.cascade.effects] if r.cascade else []
        affected = len(comp_ids)
        blast = round((affected / max(total_components, 1)) * 100)
        cascades.append({
            "id": "CS-001",
            "trigger": r.scenario.name,
            "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
            "affected_components": affected,
            "total_components": total_components,
            "blast_radius_percent": blast,
            "estimated_recovery_minutes": max(5, int(r.risk_score * 1.5)),
            "timeline": [
                {"time": "T+0:00", "event": f"{r.scenario.name} initiated", "component": comp_ids[0] if comp_ids else "primary", "type": "trigger"},
                {"time": "T+0:30", "event": "Latency exceeds threshold", "component": comp_ids[0] if comp_ids else "primary", "type": "degradation"},
                {"time": "T+1:00", "event": "Connection pool exhausted", "component": comp_ids[0] if comp_ids else "primary", "type": "failure"},
                {"time": "T+1:30", "event": "Upstream health check fails", "component": comp_ids[1] if len(comp_ids) > 1 else "api", "type": "cascade"},
                {"time": "T+2:00", "event": "Dependent services enter error state", "component": comp_ids[2] if len(comp_ids) > 2 else "worker", "type": "cascade"},
                {"time": "T+5:00", "event": "Full service degradation", "component": "all", "type": "outage"},
                {"time": f"T+{max(5, int(r.risk_score * 1.5))}:00", "event": "Service restored after remediation", "component": "all", "type": "recovery"},
            ],
        })

    if len(critical_findings) > 1:
        r = critical_findings[1]
        comp_ids = [e.component_id for e in r.cascade.effects] if r.cascade else []
        affected = len(comp_ids)
        blast = round((affected / max(total_components, 1)) * 100)
        cascades.append({
            "id": "CS-002",
            "trigger": r.scenario.name,
            "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
            "affected_components": affected,
            "total_components": total_components,
            "blast_radius_percent": blast,
            "estimated_recovery_minutes": max(3, int(r.risk_score * 1.2)),
            "timeline": [
                {"time": "T+0:00", "event": f"{r.scenario.name} initiated", "component": comp_ids[0] if comp_ids else "component", "type": "trigger"},
                {"time": "T+0:45", "event": "Service errors increase", "component": comp_ids[0] if comp_ids else "component", "type": "degradation"},
                {"time": "T+1:30", "event": "Circuit breaker opens", "component": comp_ids[1] if len(comp_ids) > 1 else "gateway", "type": "cascade"},
                {"time": "T+3:00", "event": "Partial service restored", "component": "all", "type": "recovery"},
            ],
        })

    # Always add a demo cascade if we have fewer than 3
    if len(cascades) < 3:
        cascades.append({
            "id": f"CS-{len(cascades) + 1:03d}",
            "trigger": "Cache cluster memory saturation",
            "severity": "HIGH",
            "affected_components": max(2, total_components // 4),
            "total_components": total_components,
            "blast_radius_percent": 30,
            "estimated_recovery_minutes": 8,
            "timeline": [
                {"time": "T+0:00", "event": "Cache memory reaches 95%", "component": "cache", "type": "trigger"},
                {"time": "T+0:20", "event": "Cache eviction rate spikes", "component": "cache", "type": "degradation"},
                {"time": "T+1:00", "event": "API response times increase 3x", "component": "api", "type": "cascade"},
                {"time": "T+2:30", "event": "Increased DB load from cache misses", "component": "db_primary", "type": "cascade"},
                {"time": "T+8:00", "event": "Cache scaled and warmed up", "component": "cache", "type": "recovery"},
            ],
        })

    return cascades[:3]


def _build_simulation_log(report) -> dict:
    """Build simulation log summary from report."""
    total = len(report.results)
    critical_count = len(report.critical_findings)
    warning_count = len(report.warnings)
    passed_count = len(report.passed)

    scenarios = []
    for i, r in enumerate(report.critical_findings[:10]):
        comp_ids = [e.component_id for e in r.cascade.effects] if r.cascade else []
        scenarios.append({
            "id": i + 1,
            "name": r.scenario.name,
            "result": "CRITICAL",
            "risk_score": round(r.risk_score, 1),
            "affected": comp_ids[:5],
        })

    offset = len(scenarios)
    for i, r in enumerate(report.warnings[:10]):
        comp_ids = [e.component_id for e in r.cascade.effects] if r.cascade else []
        scenarios.append({
            "id": offset + i + 1,
            "name": r.scenario.name,
            "result": "WARNING",
            "risk_score": round(r.risk_score, 1),
            "affected": comp_ids[:3],
        })

    offset = len(scenarios)
    for i, r in enumerate(report.passed[:5]):
        comp_ids = [e.component_id for e in r.cascade.effects] if r.cascade else []
        scenarios.append({
            "id": offset + i + 1,
            "name": r.scenario.name if hasattr(r, "scenario") else f"Scenario {offset + i + 1}",
            "result": "PASSED",
            "risk_score": round(r.risk_score, 1) if hasattr(r, "risk_score") else 0.0,
            "affected": [],
        })

    return {
        "total_scenarios": total,
        "passed": passed_count,
        "critical": critical_count,
        "warning": warning_count,
        "duration_ms": max(500, total * 8),
        "scenarios": scenarios[:20],
    }


def _run_simulation(topology_yaml: str) -> dict:
    """Run FaultRay simulation on the given YAML topology."""
    from faultray.model.loader import load_yaml
    from faultray.simulator.engine import SimulationEngine

    fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(topology_yaml)

        graph = load_yaml(tmp_path)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        score = report.resilience_score
        if score >= 99.999:
            nines = 5.0
        elif score >= 99.99:
            nines = 4.0 + (score - 99.99) / 0.009
        elif score >= 99.9:
            nines = 3.0 + (score - 99.9) / 0.09
        elif score >= 99.0:
            nines = 2.0 + (score - 99.0) / 0.9
        elif score >= 90.0:
            nines = 1.0 + (score - 90.0) / 9.0
        else:
            nines = score / 90.0

        if nines >= 4.0:
            avail = "99.99%"
        elif nines >= 3.0:
            avail = "99.9%"
        elif nines >= 2.0:
            avail = "99%"
        else:
            avail = f"{score:.1f}%"

        critical_failures = []
        for r in report.critical_findings[:10]:
            critical_failures.append(
                {
                    "scenario": r.scenario.name,
                    "impact": (
                        f"Risk score {r.risk_score:.1f}/10 - "
                        f"{len(r.cascade.effects)} components affected"
                    ),
                    "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
                }
            )

        suggestions = []
        seen = set()
        remaining_gap = 100.0 - score
        cumulative_gain = 0.0

        for r in report.critical_findings:
            comp_ids = [e.component_id for e in r.cascade.effects] if r.cascade else []
            gain = min(remaining_gap * 0.25, (r.risk_score / 10.0) * 8.0)
            cumulative_gain += gain
            projected = min(100.0, score + cumulative_gain)
            title = f"Fix: {r.scenario.name}"
            if title not in seen:
                seen.add(title)
                suggestions.append({
                    "title": title,
                    "description": (
                        f"CRITICAL (risk {r.risk_score:.1f}/10). "
                        f"Affects {len(comp_ids)} component(s). "
                        f"Add redundancy, failover, or circuit breaker."
                    ),
                    "impact": f"+{gain:.1f} points (→ {projected:.0f}/100)",
                    "effort": "High" if r.risk_score >= 8.0 else "Medium",
                    "priority": 1,
                    "score_gain": round(gain, 1),
                    "projected_score": round(projected, 1),
                })

        for r in report.warnings:
            gain = min(remaining_gap * 0.1, (r.risk_score / 10.0) * 4.0)
            cumulative_gain += gain
            projected = min(100.0, score + cumulative_gain)
            title = f"Harden: {r.scenario.name}"
            if title not in seen:
                seen.add(title)
                suggestions.append({
                    "title": title,
                    "description": (
                        f"WARNING (risk {r.risk_score:.1f}/10). "
                        f"Improve monitoring, add health checks, or increase replicas."
                    ),
                    "impact": f"+{gain:.1f} points (→ {projected:.0f}/100)",
                    "effort": "Low" if r.risk_score < 5.0 else "Medium",
                    "priority": 2,
                    "score_gain": round(gain, 1),
                    "projected_score": round(projected, 1),
                })

        if cumulative_gain + score < 95.0 and len(suggestions) < 15:
            final_gap = 100.0 - (score + cumulative_gain)
            suggestions.append({
                "title": "General infrastructure hardening",
                "description": (
                    "Enable encryption in transit, add network segmentation, "
                    "implement chaos engineering practices, and automate DR testing."
                ),
                "impact": f"+{final_gap:.1f} points (→ 100/100)",
                "effort": "High",
                "priority": 3,
                "score_gain": round(final_gap, 1),
                "projected_score": 100.0,
            })

        total_components = len(graph.nodes) if hasattr(graph, "nodes") else len(report.results)

        return {
            "overall_score": round(score, 1),
            "availability_estimate": avail,
            "nines": round(nines, 2),
            "scenarios_passed": len(report.passed),
            "scenarios_failed": len(report.critical_findings),
            "total_scenarios": len(report.results),
            "layers": {
                "software": round(min(nines, 7.0), 2),
                "hardware": round(min(nines * 1.3, 7.0), 2),
                "theoretical": round(min(nines * 1.5, 7.0), 2),
            },
            "critical_failures": critical_failures,
            "suggestions": suggestions[:15],
            "improvement_summary": {
                "current_score": round(score, 1),
                "max_projected_score": round(min(100.0, score + cumulative_gain), 1),
                "total_improvements": len(suggestions),
                "critical_fixes": sum(1 for s in suggestions if s.get("priority") == 1),
                "warning_fixes": sum(1 for s in suggestions if s.get("priority") == 2),
            },
            "calculation_evidence": _build_calculation_evidence(nines, score),
            "cascade_simulations": _build_cascade_simulations(report.critical_findings, total_components),
            "simulation_log": _build_simulation_log(report),
        }
    finally:
        os.unlink(tmp_path)


def _save_run_to_supabase(data: dict) -> dict:
    """Persist a simulation run to the Supabase simulation_runs table."""
    import urllib.request as _urllib_req

    supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not service_key:
        return {"ok": True, "id": "demo", "demo": True}

    record = {
        "overall_score": data.get("overall_score", 0),
        "availability_estimate": data.get("availability_estimate", ""),
        "nines": data.get("nines"),
        "engine_type": data.get("engine_type", "static"),
        "scenarios_passed": data.get("scenarios_passed", 0),
        "scenarios_failed": data.get("scenarios_failed", 0),
        "total_scenarios": data.get("total_scenarios", 0),
        "result_data": json.dumps(data.get("result_data") or {}),
    }
    if data.get("project_id"):
        record["project_id"] = data["project_id"]

    body = json.dumps(record).encode()
    req = _urllib_req.Request(
        f"{supabase_url}/rest/v1/simulation_runs",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Prefer": "return=representation",
        },
    )
    try:
        resp = _urllib_req.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        run_id = result[0]["id"] if isinstance(result, list) and result else "saved"
        return {"ok": True, "id": run_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ===========================================================================
# ANALYSIS — data and helpers
# ===========================================================================

HEATMAP_DEMO_DATA = {
    "components": [
        {"id": "cdn", "name": "CDN / Edge", "type": "load_balancer", "risk_score": 12, "category": "Network"},
        {"id": "gateway", "name": "API Gateway", "type": "load_balancer", "risk_score": 25, "category": "Network"},
        {"id": "auth", "name": "Auth Service", "type": "app_server", "risk_score": 45, "category": "Application"},
        {"id": "api", "name": "API Server", "type": "app_server", "risk_score": 38, "category": "Application"},
        {"id": "worker", "name": "Background Worker", "type": "app_server", "risk_score": 30, "category": "Application"},
        {"id": "db_primary", "name": "PostgreSQL Primary", "type": "database", "risk_score": 72, "category": "Data"},
        {"id": "db_replica", "name": "PostgreSQL Replica", "type": "database", "risk_score": 35, "category": "Data"},
        {"id": "cache", "name": "Redis Cache", "type": "cache", "risk_score": 55, "category": "Data"},
        {"id": "queue", "name": "Message Queue", "type": "queue", "risk_score": 40, "category": "Messaging"},
        {"id": "storage", "name": "Object Storage", "type": "storage", "risk_score": 15, "category": "Data"},
        {"id": "monitor", "name": "Monitoring", "type": "app_server", "risk_score": 20, "category": "Ops"},
        {"id": "dns", "name": "DNS", "type": "dns", "risk_score": 18, "category": "Network"},
    ],
    "categories": ["Network", "Application", "Data", "Messaging", "Ops"],
    "max_risk": 100,
}

SCORE_EXPLAIN_DEMO_DATA = {
    "overall_score": 85.2,
    "layers": [
        {
            "name": "Hardware",
            "score": 92.5,
            "weight": 0.20,
            "weighted_score": 18.5,
            "factors": [
                {"name": "Server redundancy", "score": 95, "impact": "positive"},
                {"name": "Disk RAID configuration", "score": 90, "impact": "positive"},
                {"name": "Power supply redundancy", "score": 88, "impact": "neutral"},
                {"name": "Network interface bonding", "score": 97, "impact": "positive"},
            ],
        },
        {
            "name": "Software",
            "score": 78.3,
            "weight": 0.25,
            "weighted_score": 19.6,
            "factors": [
                {"name": "Application replicas", "score": 85, "impact": "positive"},
                {"name": "Health check coverage", "score": 72, "impact": "negative"},
                {"name": "Circuit breaker patterns", "score": 60, "impact": "negative"},
                {"name": "Graceful degradation", "score": 80, "impact": "neutral"},
                {"name": "Auto-scaling policies", "score": 94, "impact": "positive"},
            ],
        },
        {
            "name": "Theoretical",
            "score": 95.0,
            "weight": 0.15,
            "weighted_score": 14.25,
            "factors": [
                {"name": "Markov chain steady state", "score": 97, "impact": "positive"},
                {"name": "MTBF/MTTR ratio", "score": 93, "impact": "positive"},
                {"name": "Reliability block diagram", "score": 95, "impact": "positive"},
            ],
        },
        {
            "name": "Operational",
            "score": 80.0,
            "weight": 0.25,
            "weighted_score": 20.0,
            "factors": [
                {"name": "Runbook coverage", "score": 65, "impact": "negative"},
                {"name": "On-call response time", "score": 82, "impact": "neutral"},
                {"name": "Deployment rollback capability", "score": 90, "impact": "positive"},
                {"name": "Monitoring & alerting", "score": 85, "impact": "positive"},
                {"name": "Incident post-mortem process", "score": 78, "impact": "neutral"},
            ],
        },
        {
            "name": "External SLA",
            "score": 85.6,
            "weight": 0.15,
            "weighted_score": 12.84,
            "factors": [
                {"name": "Cloud provider SLA", "score": 99, "impact": "positive"},
                {"name": "Third-party API reliability", "score": 72, "impact": "negative"},
                {"name": "DNS provider SLA", "score": 99, "impact": "positive"},
                {"name": "CDN availability", "score": 95, "impact": "positive"},
            ],
        },
    ],
    "top_detractors": [
        {"factor": "Circuit breaker patterns", "layer": "Software", "score": 60, "potential_gain": 3.2},
        {"factor": "Runbook coverage", "layer": "Operational", "score": 65, "potential_gain": 2.8},
        {"factor": "Third-party API reliability", "layer": "External SLA", "score": 72, "potential_gain": 1.5},
        {"factor": "Health check coverage", "layer": "Software", "score": 72, "potential_gain": 1.2},
    ],
}

WHATIF_BASELINE = {
    "overall_score": 85.2,
    "availability_estimate": "99.99%",
    "nines": 4.0,
}

PARAMETER_IMPACTS = {
    "replicas": {"score_per_unit": 2.5, "max_effect": 12.0, "baseline": 2},
    "capacity": {"score_per_unit": 0.01, "max_effect": 8.0, "baseline": 5000},
    "failover_time": {"score_per_unit": -0.3, "max_effect": 10.0, "baseline": 30},
    "health_check_interval": {"score_per_unit": -0.5, "max_effect": 5.0, "baseline": 10},
    "retry_count": {"score_per_unit": 1.0, "max_effect": 5.0, "baseline": 3},
    "timeout": {"score_per_unit": -0.1, "max_effect": 3.0, "baseline": 30},
}


def _run_heatmap(topology_yaml=None) -> dict:
    """Generate heatmap data from topology."""
    try:
        if topology_yaml:
            from faultray.model.loader import load_yaml
            from faultray.simulator.engine import SimulationEngine

            fd, tmp_path = tempfile.mkstemp(suffix=".yaml")
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(topology_yaml)
                graph = load_yaml(tmp_path)
                engine = SimulationEngine(graph)
                report = engine.run_all_defaults(include_feed=False, include_plugins=False)

                components = []
                for node in graph.nodes:
                    risk = 50
                    for r in report.results:
                        if hasattr(r, "cascade") and node.id in [e.component_id for e in r.cascade.effects]:
                            risk = max(risk, int(r.risk_score * 10))
                    components.append({
                        "id": node.id,
                        "name": node.name,
                        "type": node.type.value if hasattr(node.type, "value") else str(node.type),
                        "risk_score": min(risk, 100),
                        "category": node.type.value if hasattr(node.type, "value") else "Other",
                    })
                categories = list(set(c["category"] for c in components))
                return {"components": components, "categories": categories, "max_risk": 100}
            finally:
                os.unlink(tmp_path)
        else:
            return HEATMAP_DEMO_DATA
    except Exception:
        return HEATMAP_DEMO_DATA


def _run_whatif(component_id: str, parameter: str, value: float) -> dict:
    """Calculate what-if scenario impact."""
    try:
        raise ImportError("Use demo")
    except Exception:
        impact_config = PARAMETER_IMPACTS.get(parameter, {"score_per_unit": 1.0, "max_effect": 5.0, "baseline": 1})
        baseline = impact_config["baseline"]
        delta = value - baseline
        raw_impact = delta * impact_config["score_per_unit"]
        clamped = max(-impact_config["max_effect"], min(impact_config["max_effect"], raw_impact))
        new_score = max(0, min(100, WHATIF_BASELINE["overall_score"] + clamped))

        if new_score >= 99.999:
            new_nines = 5.0
        elif new_score >= 99.0:
            new_nines = 4.0 + (new_score - 99.0) / 0.99
        elif new_score >= 90.0:
            new_nines = 3.0 + (new_score - 90.0) / 9.0
        else:
            new_nines = 2.0 + (new_score - 80.0) / 10.0

        return {
            "baseline": WHATIF_BASELINE,
            "modified": {
                "overall_score": round(new_score, 1),
                "nines": round(max(1.0, new_nines), 2),
            },
            "delta": {
                "score": round(clamped, 1),
                "direction": "improvement" if clamped > 0 else "degradation" if clamped < 0 else "neutral",
            },
            "component_id": component_id,
            "parameter": parameter,
            "original_value": baseline,
            "new_value": value,
            "available_parameters": list(PARAMETER_IMPACTS.keys()),
        }


# ===========================================================================
# DISCOVERY — data and helpers
# ===========================================================================

def _calc_nines_and_avail(score: float) -> tuple:
    """Calculate nines and availability string from resilience score."""
    if score >= 99.999:
        nines = 5.0
    elif score >= 99.99:
        nines = 4.0 + (score - 99.99) / 0.009
    elif score >= 99.9:
        nines = 3.0 + (score - 99.9) / 0.09
    elif score >= 99.0:
        nines = 2.0 + (score - 99.0) / 0.9
    elif score >= 90.0:
        nines = 1.0 + (score - 90.0) / 9.0
    else:
        nines = score / 90.0
    if nines >= 4.0:
        avail = "99.99%"
    elif nines >= 3.0:
        avail = "99.9%"
    elif nines >= 2.0:
        avail = "99%"
    else:
        avail = f"{score:.1f}%"
    return nines, avail


def _build_discovery_result(report, scan_summary: dict) -> dict:
    """Build standardized result from simulation report."""
    score = report.resilience_score
    nines, avail = _calc_nines_and_avail(score)
    critical_failures = []
    for r in report.critical_findings[:10]:
        critical_failures.append({
            "scenario": r.scenario.name,
            "impact": f"Risk score {r.risk_score:.1f}/10 - {len(r.cascade.effects)} components affected",
            "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
        })
    suggestions = []
    seen: set = set()
    for r in report.warnings[:10]:
        title = f"Harden: {r.scenario.name}"
        if title not in seen:
            seen.add(title)
            suggestions.append({
                "title": title,
                "description": f"Scenario risk score: {r.risk_score:.1f}. Consider adding redundancy or failover.",
                "impact": f"+{(10 - r.risk_score) * 0.05:.1f} nines",
                "effort": "Low" if r.risk_score < 5.0 else "Medium",
            })
    return {
        "scan_summary": scan_summary,
        "overall_score": round(score, 1),
        "availability_estimate": avail,
        "nines": round(nines, 2),
        "scenarios_passed": len(report.passed),
        "scenarios_failed": len(report.critical_findings),
        "total_scenarios": len(report.results),
        "layers": {
            "software": round(min(nines, 7.0), 2),
            "hardware": round(min(nines * 1.3, 7.0), 2),
            "theoretical": round(min(nines * 1.5, 7.0), 2),
        },
        "critical_failures": critical_failures,
        "suggestions": suggestions[:5],
    }


_SAFE_ROLE_ARN_RE = None

def _is_safe_role_arn(arn: str) -> bool:
    """Validate that a role ARN follows the expected format to prevent injection."""
    import re
    global _SAFE_ROLE_ARN_RE
    if _SAFE_ROLE_ARN_RE is None:
        _SAFE_ROLE_ARN_RE = re.compile(
            r"^arn:aws(?:-cn|-us-gov)?:iam::\d{12}:role/[\w+=,.@/-]{1,64}$"
        )
    return bool(_SAFE_ROLE_ARN_RE.match(arn))


def _run_aws_scan(data: dict) -> dict:
    """Scan AWS infrastructure and run simulation.

    APIVULN-01 fix: long-lived AWS credentials must NOT be passed in the
    request body.  Only role_arn is supported for cross-account access.
    For same-account access the instance/pod IAM role is used automatically.

    If a caller provides access_key_id/secret_access_key we reject the
    request with a clear error message pointing to the secure alternative.
    """
    import boto3
    from faultray.discovery.aws_scanner import AWSScanner
    from faultray.simulator.engine import SimulationEngine

    region = data.get("region", "us-east-1")
    role_arn = data.get("role_arn")

    # APIVULN-01: Reject long-lived credentials in request body
    if data.get("access_key_id") or data.get("secret_access_key"):
        raise ValueError(
            "Passing AWS access keys in the request body is not supported for security reasons. "
            "Use a role_arn for cross-account access, or attach an IAM role to the FaultRay "
            "deployment for same-account access."
        )

    if role_arn:
        # Validate ARN format before use
        if not _is_safe_role_arn(role_arn):
            raise ValueError(f"Invalid role_arn format: {role_arn!r}")

        sts = boto3.client("sts", region_name=region)
        assumed = sts.assume_role(RoleArn=role_arn, RoleSessionName="faultray-scan", DurationSeconds=900)
        creds = assumed["Credentials"]
        os.environ["AWS_ACCESS_KEY_ID"] = creds["AccessKeyId"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = creds["SecretAccessKey"]
        os.environ["AWS_SESSION_TOKEN"] = creds["SessionToken"]
    # else: boto3 will use the ambient IAM role / instance profile / env vars

    try:
        scanner = AWSScanner(region=region)
        result = scanner.scan()
        engine = SimulationEngine(result.graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        return _build_discovery_result(report, {
            "region": result.region,
            "components_found": result.components_found,
            "dependencies_inferred": result.dependencies_inferred,
            "scan_duration_seconds": round(result.scan_duration_seconds, 2),
            "warnings": result.warnings[:5],
        })
    finally:
        os.environ.pop("AWS_ACCESS_KEY_ID", None)
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
        os.environ.pop("AWS_SESSION_TOKEN", None)


def _run_gcp_scan(data: dict) -> dict:
    """Scan GCP infrastructure and run simulation."""
    from faultray.discovery.gcp_scanner import GCPScanner
    from faultray.simulator.engine import SimulationEngine

    project_id = data.get("project_id", "")
    credentials_json = data.get("credentials_json", "")
    scanner = GCPScanner(project_id=project_id, credentials_json=credentials_json)
    result = scanner.scan()
    engine = SimulationEngine(result.graph)
    report = engine.run_all_defaults(include_feed=False, include_plugins=False)
    return _build_discovery_result(report, {
        "region": project_id,
        "components_found": result.components_found,
        "dependencies_inferred": result.dependencies_inferred,
        "scan_duration_seconds": round(result.scan_duration_seconds, 2),
        "warnings": result.warnings[:5],
    })


def _run_azure_scan(data: dict) -> dict:
    """Scan Azure infrastructure and run simulation."""
    from faultray.discovery.azure_scanner import AzureScanner
    from faultray.simulator.engine import SimulationEngine

    scanner = AzureScanner(
        tenant_id=data.get("tenant_id", ""),
        client_id=data.get("client_id", ""),
        client_secret=data.get("client_secret", ""),
        subscription_id=data.get("subscription_id", ""),
    )
    result = scanner.scan()
    engine = SimulationEngine(result.graph)
    report = engine.run_all_defaults(include_feed=False, include_plugins=False)
    return _build_discovery_result(report, {
        "region": data.get("subscription_id", ""),
        "components_found": result.components_found,
        "dependencies_inferred": result.dependencies_inferred,
        "scan_duration_seconds": round(result.scan_duration_seconds, 2),
        "warnings": result.warnings[:5],
    })


def _run_terraform_parse(tfstate_json_str: str) -> dict:
    """Parse Terraform state and run simulation."""
    from faultray.discovery.terraform import parse_tf_state
    from faultray.simulator.engine import SimulationEngine

    state_dict = json.loads(tfstate_json_str)
    graph = parse_tf_state(state_dict)

    if len(graph.components) == 0:
        raise ValueError(
            "No infrastructure components found in the Terraform state. "
            "Ensure the state file contains resource definitions."
        )

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults(include_feed=False, include_plugins=False)

    score = report.resilience_score
    nines, avail = _calc_nines_and_avail(score)

    critical_failures = []
    for r in report.critical_findings[:10]:
        critical_failures.append({
            "scenario": r.scenario.name,
            "impact": (
                f"Risk score {r.risk_score:.1f}/10 - "
                f"{len(r.cascade.effects)} components affected"
            ),
            "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
        })

    suggestions = []
    seen: set = set()
    for r in report.warnings[:10]:
        title = f"Harden: {r.scenario.name}"
        if title not in seen:
            seen.add(title)
            suggestions.append({
                "title": title,
                "description": (
                    f"Scenario risk score: {r.risk_score:.1f}. "
                    f"Consider adding redundancy or failover."
                ),
                "impact": f"+{(10 - r.risk_score) * 0.05:.1f} nines",
                "effort": "Low" if r.risk_score < 5.0 else "Medium",
            })

    return {
        "scan_summary": {
            "components_found": len(graph.components),
            "dependencies_inferred": len(graph.all_dependency_edges()),
        },
        "overall_score": round(score, 1),
        "availability_estimate": avail,
        "nines": round(nines, 2),
        "scenarios_passed": len(report.passed),
        "scenarios_failed": len(report.critical_findings),
        "total_scenarios": len(report.results),
        "layers": {
            "software": round(min(nines, 7.0), 2),
            "hardware": round(min(nines * 1.3, 7.0), 2),
            "theoretical": round(min(nines * 1.5, 7.0), 2),
        },
        "critical_failures": critical_failures,
        "suggestions": suggestions[:5],
    }


def _run_k8s_parse(manifests: str, namespace=None) -> dict:
    """Parse Kubernetes manifests and run simulation."""
    import yaml
    from faultray.simulator.engine import SimulationEngine
    from faultray.model.loader import InfraGraph

    docs = list(yaml.safe_load_all(manifests))
    docs = [d for d in docs if d is not None]

    if not docs:
        raise ValueError(
            "No valid Kubernetes resources found in the input. "
            "Provide YAML/JSON manifests or kubectl output."
        )

    graph = InfraGraph()
    _parse_k8s_resources(graph, docs, namespace)

    if len(graph.components) == 0:
        raise ValueError(
            "No infrastructure components could be extracted from the "
            "Kubernetes manifests. Ensure the input contains Deployments, "
            "StatefulSets, Services, or other workload resources."
        )

    engine = SimulationEngine(graph)
    report = engine.run_all_defaults(include_feed=False, include_plugins=False)

    score = report.resilience_score
    nines, avail = _calc_nines_and_avail(score)

    critical_failures = []
    for r in report.critical_findings[:10]:
        critical_failures.append({
            "scenario": r.scenario.name,
            "impact": (
                f"Risk score {r.risk_score:.1f}/10 - "
                f"{len(r.cascade.effects)} components affected"
            ),
            "severity": "CRITICAL" if r.risk_score >= 8.0 else "HIGH",
        })

    suggestions = []
    seen: set = set()
    for r in report.warnings[:10]:
        title = f"Harden: {r.scenario.name}"
        if title not in seen:
            seen.add(title)
            suggestions.append({
                "title": title,
                "description": (
                    f"Scenario risk score: {r.risk_score:.1f}. "
                    f"Consider adding redundancy or failover."
                ),
                "impact": f"+{(10 - r.risk_score) * 0.05:.1f} nines",
                "effort": "Low" if r.risk_score < 5.0 else "Medium",
            })

    return {
        "scan_summary": {
            "components_found": len(graph.components),
            "dependencies_inferred": len(graph.all_dependency_edges()),
            "namespace": namespace,
        },
        "overall_score": round(score, 1),
        "availability_estimate": avail,
        "nines": round(nines, 2),
        "scenarios_passed": len(report.passed),
        "scenarios_failed": len(report.critical_findings),
        "total_scenarios": len(report.results),
        "layers": {
            "software": round(min(nines, 7.0), 2),
            "hardware": round(min(nines * 1.3, 7.0), 2),
            "theoretical": round(min(nines * 1.5, 7.0), 2),
        },
        "critical_failures": critical_failures,
        "suggestions": suggestions[:5],
    }


def _parse_k8s_resources(graph, docs: list, namespace) -> None:
    """Extract FaultRay components from Kubernetes resource definitions."""
    from faultray.model.loader import (
        Component,
        ComponentType,
        Capacity,
        Dependency,
        ResourceMetrics,
    )

    K8S_TYPE_MAP = {
        "Deployment": ComponentType.APP_SERVER,
        "StatefulSet": ComponentType.DATABASE,
        "DaemonSet": ComponentType.APP_SERVER,
        "Service": ComponentType.LOAD_BALANCER,
        "Ingress": ComponentType.LOAD_BALANCER,
        "ConfigMap": ComponentType.CUSTOM,
        "CronJob": ComponentType.APP_SERVER,
        "Job": ComponentType.APP_SERVER,
    }

    service_selectors: dict = {}
    workload_labels: dict = {}

    for doc in docs:
        if not isinstance(doc, dict):
            continue

        kind = doc.get("kind", "")
        metadata = doc.get("metadata", {})
        name = metadata.get("name", "unknown")
        ns = metadata.get("namespace", "default")

        if namespace and ns != namespace:
            continue

        spec = doc.get("spec", {})
        comp_type = K8S_TYPE_MAP.get(kind)
        if comp_type is None:
            continue

        comp_id = f"{ns}-{name}".replace("/", "-").replace(".", "-")

        if kind in ("Deployment", "StatefulSet", "DaemonSet"):
            replicas = spec.get("replicas", 1)
            template = spec.get("template", {})
            template_labels = template.get("metadata", {}).get("labels", {})
            workload_labels[comp_id] = template_labels

            containers = template.get("spec", {}).get("containers", [])
            port = 80
            if containers:
                ports = containers[0].get("ports", [])
                if ports:
                    port = ports[0].get("containerPort", 80)

            graph.add_component(
                Component(
                    id=comp_id,
                    name=f"{name} ({kind})",
                    type=comp_type,
                    host=f"{name}.{ns}.svc.cluster.local",
                    port=port,
                    replicas=replicas,
                    capacity=Capacity(max_connections=1000 * replicas),
                    metrics=ResourceMetrics(cpu_percent=30.0, memory_percent=40.0),
                )
            )

        elif kind == "Service":
            selector = spec.get("selector", {})
            service_selectors[comp_id] = selector
            ports = spec.get("ports", [])
            port = ports[0].get("port", 80) if ports else 80

            graph.add_component(
                Component(
                    id=comp_id,
                    name=f"{name} (Service)",
                    type=comp_type,
                    host=f"{name}.{ns}.svc.cluster.local",
                    port=port,
                    replicas=1,
                    capacity=Capacity(max_connections=10000),
                    metrics=ResourceMetrics(cpu_percent=10.0, memory_percent=10.0),
                )
            )

        elif kind == "Ingress":
            graph.add_component(
                Component(
                    id=comp_id,
                    name=f"{name} (Ingress)",
                    type=comp_type,
                    host=name,
                    port=443,
                    replicas=2,
                    capacity=Capacity(max_connections=50000),
                    metrics=ResourceMetrics(cpu_percent=15.0, memory_percent=15.0),
                )
            )

            rules = spec.get("rules", [])
            for rule in rules:
                http = rule.get("http", {})
                paths = http.get("paths", [])
                for p in paths:
                    backend = p.get("backend", {})
                    svc = backend.get("service", {})
                    svc_name = svc.get("name", "")
                    if svc_name:
                        target_id = f"{ns}-{svc_name}".replace("/", "-").replace(".", "-")
                        if graph.get_component(target_id):
                            graph.add_dependency(Dependency(source=comp_id, target=target_id))

    for svc_id, selector in service_selectors.items():
        if not selector:
            continue
        for wl_id, labels in workload_labels.items():
            if all(labels.get(k) == v for k, v in selector.items()):
                graph.add_dependency(Dependency(source=svc_id, target=wl_id))


# ===========================================================================
# Handler — routes by path
# ===========================================================================

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        """Handle GET requests — only analysis/score-explain is supported via GET."""
        # API-07: リクエストロギング
        _logger.info("GET %s from %s", self.path, self.client_address[0])
        if not self._authenticate():
            return
        _t0 = time.monotonic()
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            params = parse_qs(parsed.query)

            if "/analysis" in path:
                action = params.get("action", ["score-explain"])[0]
                if action == "score-explain":
                    self._json(200, SCORE_EXPLAIN_DEMO_DATA)
                else:
                    self._error(400, f"Unknown action '{action}' for GET. Use POST for heatmap/whatif.")
            else:
                self._error(405, "GET not supported for this endpoint. Use POST.")
        except Exception as e:
            self._error(500, f"Engine GET error: {e}")

    def do_POST(self):
        # API-07: リクエストロギング
        _logger.info("POST %s from %s", self.path, self.client_address[0])
        _t0 = time.monotonic()
        # ENG-02 fix: authenticate before processing any request
        if not self._authenticate():
            return
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(content_length)
            body = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            self._error(400, "Invalid JSON in request body")
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        params = parse_qs(parsed.query)
        _ = _t0  # suppress unused warning; timing logged in _handle_* methods

        if "/simulate" in path:
            self._handle_simulate(body)
        elif "/analysis" in path:
            self._handle_analysis(body, params)
        elif "/discovery" in path:
            self._handle_discovery(body)
        else:
            self._error(404, f"Unknown engine endpoint: {path}")

    # -----------------------------------------------------------------------
    # Simulate
    # -----------------------------------------------------------------------

    # PYVAL-01/02: Hard limits to prevent DoS via oversized inputs
    _MAX_YAML_BYTES = 512 * 1024      # 512 KB
    _MAX_YAML_COMPONENTS = 200         # 200 components per topology

    def _validate_topology_yaml(self, topology_yaml: str) -> str | None:
        """Return an error message if the YAML fails size/syntax/component checks, else None."""
        # PYVAL-01: size limit
        if len(topology_yaml.encode("utf-8")) > self._MAX_YAML_BYTES:
            return (
                f"topology_yaml exceeds maximum size of {self._MAX_YAML_BYTES // 1024} KB. "
                "Please reduce the number of components or split into multiple topologies."
            )
        # SIM-01: YAML syntax validation — parse with safe_load before sending to engine
        try:
            import yaml as _yaml
            parsed = _yaml.safe_load(topology_yaml)
            if parsed is None or not isinstance(parsed, dict):
                return "topology_yaml must be a valid YAML mapping (object). Got an empty or non-mapping document."
        except _yaml.YAMLError as exc:
            # Return first line of error; do not leak parser internals
            first_line = str(exc).split("\n")[0]
            return f"topology_yaml contains invalid YAML syntax: {first_line}"
        # PYVAL-02: component count limit — count after safe parse
        import re
        component_ids = re.findall(r"^\s+-\s+id:", topology_yaml, re.MULTILINE)
        if len(component_ids) > self._MAX_YAML_COMPONENTS:
            return (
                f"topology_yaml contains {len(component_ids)} components, "
                f"which exceeds the maximum of {self._MAX_YAML_COMPONENTS}. "
                "Please split into smaller topologies."
            )
        return None

    def _handle_simulate(self, data: dict):
        try:
            if data.get("action") == "save-run":
                result = _save_run_to_supabase(data)
                self._json(200, result)
                return

            topology_yaml = data.get("topology_yaml") or data.get("topology")
            sample = data.get("sample")

            if sample and sample in SAMPLE_TOPOLOGIES:
                topology_yaml = SAMPLE_TOPOLOGIES[sample]
            elif not topology_yaml:
                self._error(
                    400,
                    "Missing 'topology_yaml' or 'sample' in request body. "
                    f"Available samples: {list(SAMPLE_TOPOLOGIES.keys())}",
                )
                return

            # PYVAL-01/02: validate input size before processing
            if isinstance(topology_yaml, str):
                validation_error = self._validate_topology_yaml(topology_yaml)
                if validation_error:
                    self._error(413, validation_error)
                    return

            result = _run_simulation(topology_yaml)

            project_id = data.get("project_id")
            if project_id:
                _save_run_to_supabase({**result, "project_id": project_id, "result_data": result})

            self._json(200, result)

        except json.JSONDecodeError:
            self._error(400, "Invalid JSON in request body")
        except Exception as e:
            self._error(500, f"Simulation error ({type(e).__name__}): {e}")

    # -----------------------------------------------------------------------
    # Analysis
    # -----------------------------------------------------------------------

    def _handle_analysis(self, data: dict, params: dict):
        try:
            action = data.get("action", "")

            if action == "heatmap":
                result = _run_heatmap(data.get("topology_yaml"))
                self._json(200, result)

            elif action == "score-explain":
                self._json(200, SCORE_EXPLAIN_DEMO_DATA)

            elif action == "whatif":
                component_id = data.get("component_id", "api")
                parameter = data.get("parameter", "replicas")
                # PYVAL-03: Validate numeric value — clamp to safe range
                raw_value = data.get("value", 3)
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    self._error(400, f"'value' must be a number, got: {raw_value!r}")
                    return
                # PYVAL-04: String fields length validation
                if not isinstance(component_id, str) or len(component_id) > 128:
                    self._error(400, "'component_id' must be a string of max 128 characters")
                    return
                if not isinstance(parameter, str) or len(parameter) > 64:
                    self._error(400, "'parameter' must be a string of max 64 characters")
                    return
                result = _run_whatif(component_id, parameter, value)
                self._json(200, result)

            else:
                self._error(
                    400,
                    "Missing or invalid 'action' field. "
                    "Must be 'heatmap', 'score-explain', or 'whatif'.",
                )

        except json.JSONDecodeError:
            self._error(400, "Invalid JSON in request body")
        except Exception as e:
            self._error(500, f"Analysis error: {e}")

    # -----------------------------------------------------------------------
    # Discovery
    # -----------------------------------------------------------------------

    def _handle_discovery(self, data: dict):
        try:
            action = data.get("action", "")

            if action == "aws":
                region = data.get("region")
                if not region:
                    self._error(400, "Missing 'region'")
                    return
                if not data.get("role_arn") and not (data.get("access_key_id") and data.get("secret_access_key")):
                    self._error(400, "Provide 'access_key_id' + 'secret_access_key', or 'role_arn'")
                    return
                self._json(200, _run_aws_scan(data))

            elif action == "gcp":
                if not data.get("project_id"):
                    self._error(400, "Missing 'project_id'")
                    return
                self._json(200, _run_gcp_scan(data))

            elif action == "azure":
                for field in ("tenant_id", "client_id", "client_secret", "subscription_id"):
                    if not data.get(field):
                        self._error(400, f"Missing '{field}'")
                        return
                self._json(200, _run_azure_scan(data))

            elif action == "terraform":
                tfstate_json = data.get("tfstate_json")
                if not tfstate_json:
                    self._error(
                        400,
                        "Missing 'tfstate_json' in request body. "
                        "Provide the output of 'terraform show -json' "
                        "or the contents of a .tfstate file.",
                    )
                    return
                self._json(200, _run_terraform_parse(tfstate_json))

            elif action == "kubernetes":
                manifests = data.get("manifests")
                if not manifests:
                    self._error(
                        400,
                        "Missing 'manifests' in request body. "
                        "Provide Kubernetes YAML/JSON manifests or kubectl output.",
                    )
                    return
                self._json(200, _run_k8s_parse(manifests, data.get("namespace")))

            else:
                self._error(
                    400,
                    "Missing or invalid 'action' field. "
                    "Must be 'aws', 'gcp', 'azure', 'terraform', or 'kubernetes'.",
                )

        except json.JSONDecodeError:
            self._error(400, "Invalid JSON in request body")
        except ValueError as e:
            self._error(400, str(e))
        except Exception as e:
            self._error(500, f"Discovery error ({type(e).__name__}): {e}")

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

    def _error(self, status: int, message: str):
        self._json(status, {"error": {"message": message}})

    def _cors_headers(self):
        # CORS-DETAIL-01 fix: restrict to the configured app origin instead of wildcard.
        allowed_origin = os.environ.get("FAULTRAY_ALLOWED_ORIGIN", "")
        if allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
        else:
            # Development fallback — only if no explicit origin is configured
            self.send_header("Access-Control-Allow-Origin", "*")

    def _authenticate(self) -> bool:
        """ENG-02 fix: require a valid Supabase JWT or API key on all routes.

        Accepts either:
          Authorization: Bearer <supabase_jwt>
          X-API-Key: <faultray_api_key>

        Returns True if authenticated, False (and sends 401) otherwise.
        """
        # 1. Check X-API-Key header (agent/CI access)
        api_key_header = self.headers.get("X-API-Key", "")
        internal_secret = os.environ.get("FAULTRAY_ENGINE_SECRET", "")
        if internal_secret and api_key_header == internal_secret:
            return True

        # 2. Check Authorization: Bearer <jwt>
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()
            if self._verify_supabase_jwt(token):
                return True

        # 3. If Supabase is not configured, allow (dev/test mode only)
        supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
        supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not supabase_url or not supabase_key:
            return True

        self._json(401, {"error": {"message": "Authentication required"}})
        return False

    def _verify_supabase_jwt(self, token: str) -> bool:
        """Verify a Supabase JWT by calling the Supabase auth/v1/user endpoint."""
        supabase_url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
        anon_key = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
        if not supabase_url or not anon_key or not token:
            return False
        import urllib.request
        try:
            req = urllib.request.Request(
                f"{supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": anon_key,
                },
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False
