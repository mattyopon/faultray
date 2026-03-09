"""FastAPI web dashboard for InfraSim."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from infrasim.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    ResourceMetrics,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.engine import SimulationEngine

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_graph: InfraGraph | None = None
_last_report = None

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="InfraSim Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_graph() -> InfraGraph:
    """Return current graph, creating an empty one if needed."""
    global _graph
    if _graph is None:
        _graph = InfraGraph()
    return _graph


def set_graph(graph: InfraGraph) -> None:
    global _graph
    _graph = graph


def build_demo_graph() -> InfraGraph:
    """Build the demo infrastructure graph (mirrors cli.demo)."""
    graph = InfraGraph()

    components = [
        Component(
            id="nginx",
            name="nginx (LB)",
            type=ComponentType.LOAD_BALANCER,
            host="web01",
            port=443,
            replicas=1,
            metrics=ResourceMetrics(cpu_percent=25, memory_percent=30, disk_percent=45),
            capacity=Capacity(max_connections=10000, max_rps=50000),
        ),
        Component(
            id="app-1",
            name="api-server-1",
            type=ComponentType.APP_SERVER,
            host="app01",
            port=8080,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=65, memory_percent=70, disk_percent=55, network_connections=450
            ),
            capacity=Capacity(max_connections=500, connection_pool_size=100, timeout_seconds=30),
        ),
        Component(
            id="app-2",
            name="api-server-2",
            type=ComponentType.APP_SERVER,
            host="app02",
            port=8080,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=60, memory_percent=68, disk_percent=55, network_connections=420
            ),
            capacity=Capacity(max_connections=500, connection_pool_size=100, timeout_seconds=30),
        ),
        Component(
            id="postgres",
            name="PostgreSQL (primary)",
            type=ComponentType.DATABASE,
            host="db01",
            port=5432,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=45, memory_percent=80, disk_percent=72, network_connections=90
            ),
            capacity=Capacity(max_connections=100, max_disk_gb=500),
        ),
        Component(
            id="redis",
            name="Redis (cache)",
            type=ComponentType.CACHE,
            host="cache01",
            port=6379,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=15, memory_percent=60, network_connections=200
            ),
            capacity=Capacity(max_connections=10000),
        ),
        Component(
            id="rabbitmq",
            name="RabbitMQ",
            type=ComponentType.QUEUE,
            host="mq01",
            port=5672,
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=20, memory_percent=40, disk_percent=35, network_connections=50
            ),
            capacity=Capacity(max_connections=1000),
        ),
    ]

    for comp in components:
        graph.add_component(comp)

    dependencies = [
        Dependency(source_id="nginx", target_id="app-1", dependency_type="requires", weight=1.0),
        Dependency(source_id="nginx", target_id="app-2", dependency_type="requires", weight=1.0),
        Dependency(source_id="app-1", target_id="postgres", dependency_type="requires", weight=1.0),
        Dependency(source_id="app-2", target_id="postgres", dependency_type="requires", weight=1.0),
        Dependency(source_id="app-1", target_id="redis", dependency_type="optional", weight=0.7),
        Dependency(source_id="app-2", target_id="redis", dependency_type="optional", weight=0.7),
        Dependency(source_id="app-1", target_id="rabbitmq", dependency_type="async", weight=0.5),
        Dependency(source_id="app-2", target_id="rabbitmq", dependency_type="async", weight=0.5),
    ]

    for dep in dependencies:
        graph.add_dependency(dep)

    return graph


def _report_to_dict(report) -> dict:
    """Convert a SimulationReport to a JSON-serialisable dict."""
    def _result_dict(r):
        return {
            "scenario_id": r.scenario.id,
            "scenario_name": r.scenario.name,
            "scenario_description": r.scenario.description,
            "risk_score": round(r.risk_score, 2),
            "is_critical": r.is_critical,
            "is_warning": r.is_warning,
            "cascade": {
                "trigger": r.cascade.trigger,
                "severity": round(r.cascade.severity, 2),
                "effects": [
                    {
                        "component_id": e.component_id,
                        "component_name": e.component_name,
                        "health": e.health.value,
                        "reason": e.reason,
                        "estimated_time_seconds": e.estimated_time_seconds,
                        "metrics_impact": e.metrics_impact,
                    }
                    for e in r.cascade.effects
                ],
            },
        }

    return {
        "resilience_score": round(report.resilience_score, 1),
        "total_scenarios": len(report.results),
        "critical_count": len(report.critical_findings),
        "warning_count": len(report.warnings),
        "passed_count": len(report.passed),
        "critical": [_result_dict(r) for r in report.critical_findings],
        "warnings": [_result_dict(r) for r in report.warnings],
        "passed": [_result_dict(r) for r in report.passed],
    }


# ---------------------------------------------------------------------------
# HTML routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    graph = get_graph()
    summary = graph.summary()

    report_data = None
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "summary": summary,
        "has_data": len(graph.components) > 0,
        "report": report_data,
    })


@app.get("/components", response_class=HTMLResponse)
async def components_page(request: Request):
    graph = get_graph()
    comps = []
    for comp in graph.components.values():
        deps = graph.get_dependencies(comp.id)
        dependents = graph.get_dependents(comp.id)
        comps.append({
            "id": comp.id,
            "name": comp.name,
            "type": comp.type.value,
            "host": comp.host,
            "port": comp.port,
            "replicas": comp.replicas,
            "utilization": round(comp.utilization(), 1),
            "health": comp.health.value,
            "cpu_percent": comp.metrics.cpu_percent,
            "memory_percent": comp.metrics.memory_percent,
            "disk_percent": comp.metrics.disk_percent,
            "network_connections": comp.metrics.network_connections,
            "max_connections": comp.capacity.max_connections,
            "max_rps": comp.capacity.max_rps,
            "dependencies": [d.name for d in deps],
            "dependents": [d.name for d in dependents],
            "tags": comp.tags,
        })

    return templates.TemplateResponse("components.html", {
        "request": request,
        "components": comps,
        "has_data": len(comps) > 0,
    })


@app.get("/simulation", response_class=HTMLResponse)
async def simulation_page(request: Request):
    report_data = None
    if _last_report is not None:
        report_data = _report_to_dict(_last_report)

    return templates.TemplateResponse("simulation.html", {
        "request": request,
        "report": report_data,
        "has_data": len(get_graph().components) > 0,
    })


@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    return templates.TemplateResponse("graph.html", {
        "request": request,
        "has_data": len(get_graph().components) > 0,
    })


# ---------------------------------------------------------------------------
# JSON API routes
# ---------------------------------------------------------------------------

@app.get("/simulation/run")
async def simulation_run_get():
    """Run simulation and return JSON results (GET endpoint)."""
    global _last_report
    graph = get_graph()
    if not graph.components:
        return JSONResponse({"error": "No infrastructure loaded. Visit /demo first."}, status_code=400)

    engine = SimulationEngine(graph)
    _last_report = engine.run_all_defaults()
    return JSONResponse(_report_to_dict(_last_report))


@app.post("/api/simulate")
async def api_simulate():
    """Run simulation and return JSON results (POST endpoint)."""
    global _last_report
    graph = get_graph()
    if not graph.components:
        return JSONResponse({"error": "No infrastructure loaded. Visit /demo first."}, status_code=400)

    engine = SimulationEngine(graph)
    _last_report = engine.run_all_defaults()
    return JSONResponse(_report_to_dict(_last_report))


@app.get("/api/graph-data")
async def api_graph_data():
    """Return graph data as nodes + edges for D3.js."""
    graph = get_graph()
    data = graph.to_dict()

    nodes = []
    for comp_data in data["components"]:
        comp = graph.get_component(comp_data["id"])
        dependents = graph.get_dependents(comp_data["id"])
        nodes.append({
            "id": comp_data["id"],
            "name": comp_data["name"],
            "type": comp_data["type"],
            "host": comp_data["host"],
            "port": comp_data["port"],
            "replicas": comp_data["replicas"],
            "health": comp_data["health"],
            "utilization": round(comp.utilization(), 1) if comp else 0,
            "dependents_count": len(dependents),
            "cpu_percent": comp_data.get("metrics", {}).get("cpu_percent", 0),
            "memory_percent": comp_data.get("metrics", {}).get("memory_percent", 0),
        })

    edges = []
    for dep_data in data["dependencies"]:
        edges.append({
            "source": dep_data["source_id"],
            "target": dep_data["target_id"],
            "dependency_type": dep_data["dependency_type"],
            "weight": dep_data["weight"],
        })

    return JSONResponse({"nodes": nodes, "edges": edges})


@app.get("/demo")
async def load_demo(request: Request):
    """Load demo infrastructure and redirect to dashboard."""
    global _last_report
    graph = build_demo_graph()
    set_graph(graph)
    _last_report = None

    # Run simulation automatically for the demo
    engine = SimulationEngine(graph)
    _last_report = engine.run_all_defaults()

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=303)
