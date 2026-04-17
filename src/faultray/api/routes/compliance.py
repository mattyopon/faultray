# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Compliance and DORA-related API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from faultray.api.routes._shared import (
    get_graph,
    templates,
)
from faultray.api.routes._shared import _require_permission

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/compliance", response_class=HTMLResponse)
async def compliance_page(request: Request):
    graph = get_graph()
    return templates.TemplateResponse(request, "compliance.html", {
        "has_data": len(graph.components) > 0,
    })


@router.get("/api/compliance/{framework}", response_class=JSONResponse)
async def api_compliance_check(
    framework: str,
    user=Depends(_require_permission("view_results")),
):
    """Return compliance check results for the given framework.

    Supported frameworks: soc2, pci-dss, hipaa, iso27001.
    """
    graph = get_graph()
    if not graph.components:
        return JSONResponse(
            {"error": "No infrastructure loaded. Visit /demo first."},
            status_code=400,
        )

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

        if framework == "pci-dss":
            check["pci_scope"] = ct.pci_scope
            check["waf_protected"] = sec.waf_protected
            check["network_segmented"] = sec.network_segmented
        elif framework == "hipaa":
            check["contains_phi"] = ct.contains_phi
            check["access_control"] = sec.auth_required
        elif framework == "soc2":
            check["change_management"] = ct.change_management
            check["monitoring"] = sec.log_enabled
        elif framework == "iso27001":
            check["ids_monitored"] = sec.ids_monitored
            check["patch_sla_hours"] = sec.patch_sla_hours

        checks.append(check)

    total_checks = 0
    passed_checks = 0
    for check in checks:
        for key, val in check.items():
            if key in ("component_id", "component_name", "data_classification",
                       "patch_sla_hours"):
                continue
            total_checks += 1
            if val is True:
                passed_checks += 1

    compliance_pct = (
        round(passed_checks / total_checks * 100, 1)
        if total_checks > 0
        else 0.0
    )

    return JSONResponse({
        "framework": framework,
        "compliance_percent": compliance_pct,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "components": checks,
    })


# ---------------------------------------------------------------------------
# Security page
# ---------------------------------------------------------------------------

@router.get("/security", response_class=HTMLResponse)
async def security_page(request: Request):
    graph = get_graph()
    return templates.TemplateResponse(request, "security.html", {
        "has_data": len(graph.components) > 0,
    })


@router.get("/cost", response_class=HTMLResponse)
async def cost_page(request: Request):
    graph = get_graph()
    return templates.TemplateResponse(request, "cost.html", {
        "has_data": len(graph.components) > 0,
    })
