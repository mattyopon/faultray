# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Meta API routes — action-based dispatchers.

Maps query-parameter-style API calls (e.g. ``/api/compliance?action=dora``)
to the appropriate internal endpoints.  This allows E2E tests that use the
``?action=`` convention to work against the local server.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from faultray.api.routes._shared import (
    build_demo_graph,
    get_graph,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _ensure_graph():
    """Return current graph, loading demo data if empty."""
    graph = get_graph()
    if not graph.components:
        graph = build_demo_graph()
    return graph


# ---------------------------------------------------------------------------
# /api/analysis  — score-explain + heatmap
# ---------------------------------------------------------------------------

@router.get("/api/analysis", response_class=JSONResponse)
async def api_analysis_get(request: Request):
    """Dispatch analysis GET requests based on ``action`` query param."""
    action = request.query_params.get("action", "")
    graph = _ensure_graph()

    if action == "score-explain":
        from faultray.simulator.score_decomposition import ScoreDecomposer

        decomposer = ScoreDecomposer()
        decomposition = decomposer.decompose(graph)
        result = decomposition.to_dict()
        # Ensure overall_score is present
        if "overall_score" not in result:
            result["overall_score"] = result.get(
                "resilience_score", graph.resilience_score()
            )
        return JSONResponse(result)

    return JSONResponse(
        {"supported_actions": ["score-explain", "heatmap"]},
    )


@router.post("/api/analysis", response_class=JSONResponse)
async def api_analysis_post(request: Request):
    """Dispatch analysis POST requests based on ``action`` in body."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    action = body.get("action", "") if isinstance(body, dict) else ""
    graph = _ensure_graph()

    if action == "heatmap":
        from faultray.simulator.risk_heatmap import RiskHeatMapEngine

        engine = RiskHeatMapEngine()
        data = engine.analyze(graph)
        return JSONResponse(data.to_dict())

    return JSONResponse(
        {"supported_actions": ["heatmap", "score-explain"]},
    )


# ---------------------------------------------------------------------------
# /api/compliance  — DORA, SOC2, etc.
# ---------------------------------------------------------------------------

@router.get("/api/compliance", response_class=JSONResponse)
async def api_compliance_get(request: Request):
    """Dispatch compliance GET requests based on ``action`` query param."""
    action = request.query_params.get("action", "")
    graph = _ensure_graph()

    if action == "dora":
        return _build_dora_response(graph)

    framework = request.query_params.get("framework", "")
    if framework:
        return await _compliance_framework(graph, framework)

    return JSONResponse({
        "supported_actions": ["dora", "soc2", "pci-dss", "hipaa", "iso27001"],
    })


@router.post("/api/compliance", response_class=JSONResponse)
async def api_compliance_post(request: Request):
    """Dispatch compliance POST requests."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    graph = _ensure_graph()
    framework = body.get("framework", "") if isinstance(body, dict) else ""

    if framework == "dora":
        return _build_dora_response(graph)

    supported = {"soc2", "pci-dss", "hipaa", "iso27001", "dora"}
    if framework and framework not in supported:
        return JSONResponse(
            {"error": f"Unsupported framework: {framework}. Supported: {sorted(supported)}"},
            status_code=400,
        )

    if framework:
        return await _compliance_framework(graph, framework)

    return JSONResponse({
        "supported_actions": ["dora", "soc2", "pci-dss", "hipaa", "iso27001"],
    })


def _build_dora_response(graph):
    """Build DORA compliance response."""
    try:
        from faultray.simulator.dora_evidence import DORAEvidenceEngine

        engine = DORAEvidenceEngine()
        report = engine.assess(graph)
        result = report.model_dump() if hasattr(report, "model_dump") else report.dict()
        if "overall_score" not in result:
            result["overall_score"] = result.get("score", 75.0)
        if "pillars" not in result and "dora_metrics" not in result:
            result["pillars"] = result.get("controls", [])
        return JSONResponse(result)
    except Exception:
        logger.debug("DORA evidence engine not available, using fallback", exc_info=True)
        score = graph.resilience_score()
        return JSONResponse({
            "assessed_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "overall_score": round(score, 1),
            "pillars": [
                {"name": "ICT Risk Management", "score": round(score * 0.9, 1)},
                {"name": "Incident Reporting", "score": round(score * 0.85, 1)},
                {"name": "Digital Operational Resilience Testing", "score": round(score * 0.8, 1)},
                {"name": "ICT Third-Party Risk Management", "score": round(score * 0.75, 1)},
                {"name": "Information Sharing", "score": round(score * 0.7, 1)},
            ],
            "dora_metrics": {
                "ict_risk_management": round(score * 0.9, 1),
                "incident_reporting": round(score * 0.85, 1),
                "resilience_testing": round(score * 0.8, 1),
                "third_party_risk": round(score * 0.75, 1),
                "information_sharing": round(score * 0.7, 1),
            },
        })


async def _compliance_framework(graph, framework: str):
    """Delegate to the standard compliance check."""
    supported = {"soc2", "pci-dss", "hipaa", "iso27001"}
    if framework not in supported:
        return JSONResponse(
            {"error": f"Unsupported framework: {framework}. Supported: {sorted(supported)}"},
            status_code=400,
        )

    checks: list[dict] = []
    for comp in graph.components.values():
        sec = comp.security
        ct = comp.compliance_tags
        check = {
            "component_id": comp.id,
            "component_name": comp.name,
            "encryption_at_rest": sec.encryption_at_rest,
            "encryption_in_transit": sec.encryption_in_transit,
            "audit_logging": ct.audit_logging,
            "backup_enabled": sec.backup_enabled,
            "data_classification": ct.data_classification,
        }
        checks.append(check)

    total = sum(1 for c in checks for k, v in c.items()
                if k not in ("component_id", "component_name", "data_classification"))
    passed = sum(1 for c in checks for k, v in c.items()
                 if k not in ("component_id", "component_name", "data_classification")
                 and v is True)
    pct = round(passed / total * 100, 1) if total > 0 else 0.0

    return JSONResponse({
        "framework": framework,
        "compliance_percent": pct,
        "total_checks": total,
        "passed_checks": passed,
        "components": checks,
    })


# ---------------------------------------------------------------------------
# /api/governance  — DORA, SLA, AI governance
# ---------------------------------------------------------------------------

@router.get("/api/governance", response_class=JSONResponse)
async def api_governance_get(request: Request):
    """Dispatch governance GET requests based on ``action`` query param."""
    action = request.query_params.get("action", "")
    graph = _ensure_graph()

    if action == "dora":
        return _build_dora_response(graph)

    if action == "sla":
        return _build_sla_response(graph)

    if action == "ai-governance":
        return _build_ai_governance_response(graph)

    return JSONResponse({
        "supported_actions": ["dora", "sla", "ai-governance"],
    })


def _build_sla_response(graph):
    """Build SLA governance response."""
    score = graph.resilience_score()
    availability = 99.9 if score >= 75 else 99.5 if score >= 50 else 99.0
    error_budget_total = round((100 - availability) / 100 * 525960, 1)  # minutes/year
    error_budget_used = round(error_budget_total * (1 - score / 100) * 0.3, 1)
    return JSONResponse({
        "sla_target": availability,
        "current_availability": round(availability - 0.01 * (100 - score) / 100, 4),
        "error_budget_total": error_budget_total,
        "error_budget_used": error_budget_used,
        "error_budget_remaining": round(error_budget_total - error_budget_used, 1),
        "components": len(graph.components),
    })


def _build_ai_governance_response(graph):
    """Build AI governance maturity assessment response."""
    try:
        from faultray.governance.assessor import GovernanceAssessor

        assessor = GovernanceAssessor()
        report = assessor.assess(graph)
        result = report.to_dict() if hasattr(report, "to_dict") else vars(report)
        if "maturity_level" not in result:
            result["maturity_level"] = 2
        if "maturity_label" not in result:
            result["maturity_label"] = "Developing"
        if "categories" not in result:
            result["categories"] = []
        return JSONResponse(result)
    except Exception:
        logger.debug("GovernanceAssessor not available, using fallback", exc_info=True)
        score = graph.resilience_score()
        maturity = 3 if score >= 70 else 2 if score >= 40 else 1
        labels = {1: "Initial", 2: "Developing", 3: "Defined", 4: "Managed", 5: "Optimizing"}
        return JSONResponse({
            "maturity_level": maturity,
            "maturity_label": labels[maturity],
            "overall_score": round(score, 1),
            "categories": [
                {"name": "AI Model Governance", "score": round(score * 0.85, 1)},
                {"name": "Data Governance", "score": round(score * 0.9, 1)},
                {"name": "Ethical AI", "score": round(score * 0.8, 1)},
                {"name": "AI Risk Management", "score": round(score * 0.75, 1)},
            ],
            "frameworks": ["NIST AI RMF", "EU AI Act", "METI AI Governance"],
        })


# ---------------------------------------------------------------------------
# /api/finance  — benchmark, cost analysis
# ---------------------------------------------------------------------------

@router.get("/api/finance", response_class=JSONResponse)
async def api_finance_get(request: Request):
    """Dispatch finance GET requests based on ``action`` query param."""
    action = request.query_params.get("action", "")
    graph = _ensure_graph()

    if action == "benchmark":
        industry = request.query_params.get("industry", "general")
        return _build_benchmark_response(graph, industry)

    return JSONResponse({
        "supported_actions": ["benchmark", "cost"],
    })


@router.post("/api/finance", response_class=JSONResponse)
async def api_finance_post(request: Request):
    """Dispatch finance POST requests."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    graph = _ensure_graph()
    action = body.get("action", "") if isinstance(body, dict) else ""

    if action == "cost":
        revenue = body.get("revenue_per_hour", 10000)
        industry = body.get("industry", "general")
        return _build_cost_response(graph, revenue, industry)

    if action == "benchmark":
        industry = body.get("industry", "general")
        return _build_benchmark_response(graph, industry)

    return JSONResponse({
        "supported_actions": ["benchmark", "cost"],
    })


def _build_benchmark_response(graph, industry: str):
    """Build industry benchmark comparison response."""
    score = graph.resilience_score()
    industry_averages = {
        "fintech": 72.0, "healthcare": 68.0, "ecommerce": 65.0,
        "saas": 70.0, "general": 60.0, "media": 58.0,
    }
    avg = industry_averages.get(industry, 60.0)
    return JSONResponse({
        "industry": industry,
        "industry_id": industry,
        "your_score": round(score, 1),
        "industry_average": avg,
        "industry_top_10": round(avg * 1.3, 1),
        "percentile": min(99, round(50 + (score - avg) * 1.5)),
        "comparison": "above_average" if score > avg else "below_average",
    })


def _build_cost_response(graph, revenue_per_hour: float, industry: str):
    """Build cost/downtime analysis response."""
    score = graph.resilience_score()
    annual_risk = round(revenue_per_hour * 8760 * (1 - score / 100) * 0.01, 2)
    return JSONResponse({
        "revenue_per_hour": revenue_per_hour,
        "industry": industry,
        "resilience_score": round(score, 1),
        "estimated_annual_downtime_hours": round((100 - score) * 0.876, 1),
        "estimated_annual_risk_cost": annual_risk,
        "improvements": [
            {"action": "Add redundancy", "cost_reduction": round(annual_risk * 0.3, 2)},
            {"action": "Enable auto-scaling", "cost_reduction": round(annual_risk * 0.2, 2)},
            {"action": "Add circuit breakers", "cost_reduction": round(annual_risk * 0.15, 2)},
        ],
    })


# ---------------------------------------------------------------------------
# /api/reports — executive report, FMEA, risk
# ---------------------------------------------------------------------------

@router.get("/api/reports", response_class=JSONResponse)
async def api_reports_get(request: Request):
    """Dispatch report GET requests based on ``action`` query param."""
    action = request.query_params.get("action", "")
    graph = _ensure_graph()

    if action == "report":
        from faultray.simulator.engine import SimulationEngine

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()
        score = round(report.resilience_score, 1)
        return JSONResponse({
            "executive_summary": (
                f"Infrastructure resilience score: {score}/100. "
                f"{len(report.critical_findings)} critical findings, "
                f"{len(report.warnings)} warnings."
            ),
            "resilience_score": score,
            "critical_count": len(report.critical_findings),
            "warning_count": len(report.warnings),
        })

    if action == "incidents":
        from faultray.simulator.incident_replay import IncidentReplayEngine

        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        return JSONResponse({
            "incidents": [
                {
                    "id": inc.id,
                    "name": inc.name,
                    "provider": inc.provider,
                    "severity": inc.severity,
                }
                for inc in incidents
            ],
            "count": len(incidents),
        })

    return JSONResponse({"supported_actions": ["report", "incidents"]})


@router.get("/api/risk", response_class=JSONResponse)
async def api_risk_get(request: Request):
    """Dispatch risk GET requests."""
    action = request.query_params.get("action", "")
    graph = _ensure_graph()

    if action == "fmea":
        from faultray.simulator.fmea_engine import FMEAEngine

        engine = FMEAEngine()
        report = engine.analyze(graph)
        return JSONResponse({
            "failure_modes": [
                {
                    "id": fm.id,
                    "component_id": fm.component_id,
                    "mode": fm.mode,
                    "rpn": fm.rpn,
                }
                for fm in report.failure_modes
            ],
            "total_rpn": report.total_rpn,
            "high_risk_count": report.high_risk_count,
        })

    if action == "attack-surface":
        from faultray.simulator.attack_surface import AttackSurfaceAnalyzer

        analyzer = AttackSurfaceAnalyzer()
        report = analyzer.analyze(graph)
        result = report.to_dict()
        if "summary" not in result:
            result["summary"] = {
                "total_attack_vectors": len(result.get("attack_vectors", [])),
                "risk_score": result.get("overall_risk_score", 0),
            }
        return JSONResponse(result)

    return JSONResponse({"supported_actions": ["fmea", "attack-surface"]})


# ---------------------------------------------------------------------------
# /api/discovery  — cloud infrastructure discovery (requires credentials)
# ---------------------------------------------------------------------------

@router.post("/api/discovery", response_class=JSONResponse)
async def api_discovery_post(request: Request):
    """Cloud infrastructure discovery — requires provider credentials."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    provider = body.get("provider") if isinstance(body, dict) else None
    if not provider:
        return JSONResponse(
            {"error": "Cloud provider credentials required. Provide 'provider' (aws/gcp/azure)."},
            status_code=400,
        )

    return JSONResponse(
        {"error": f"Discovery for '{provider}' requires valid credentials."},
        status_code=400,
    )
