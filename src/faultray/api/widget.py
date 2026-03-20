# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Embeddable score card widget for external dashboards."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

logger = logging.getLogger(__name__)

widget_router = APIRouter(tags=["widget"])


def _get_score_and_status() -> tuple[float, str, str]:
    """Retrieve current resilience score, status text, and color.

    Returns (score, status_text, color_hex).
    """
    try:
        from faultray.api.server import _last_report, get_graph

        graph = get_graph()
        if not graph.components:
            return 0.0, "No infrastructure loaded", "#8b949e"

        if _last_report is not None:
            score = round(_last_report.resilience_score, 1)
        else:
            score = round(graph.resilience_score(), 1)

        if score >= 80:
            color = "#3fb950"  # green
            status = "Resilient"
        elif score >= 50:
            color = "#d29922"  # yellow
            status = "Needs Attention"
        else:
            color = "#f85149"  # red
            status = "At Risk"

        return score, status, color
    except Exception:
        return 0.0, "Unavailable", "#8b949e"


@widget_router.get("/widget/scorecard", response_class=HTMLResponse)
async def scorecard_widget(project_id: str = "default"):
    """Embeddable HTML widget showing resilience score card.

    Can be embedded via ``<iframe src="/widget/scorecard">``.
    """
    score, status, color = _get_score_and_status()
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:transparent;">
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            padding: 16px; border-radius: 8px;
            background: #0d1117; color: #e6edf3; max-width: 300px;">
    <h3 style="margin: 0 0 8px; color: #58a6ff;">FaultRay</h3>
    <div style="font-size: 2rem; font-weight: bold; color: {color};">{score}/100</div>
    <div style="margin-top: 8px; color: #8b949e;">{status}</div>
    <div style="margin-top: 4px; font-size: 0.75rem; color: #484f58;">Project: {project_id}</div>
</div>
</body>
</html>"""
    return HTMLResponse(html)


@widget_router.get("/widget/badge")
async def badge_endpoint(project_id: str = "default"):
    """Return a JSON badge compatible with shields.io endpoint badge."""
    score, status, _color = _get_score_and_status()

    if score >= 80:
        badge_color = "brightgreen"
    elif score >= 50:
        badge_color = "yellow"
    else:
        badge_color = "red"

    return {
        "schemaVersion": 1,
        "label": "FaultRay",
        "message": f"{score}/100",
        "color": badge_color,
    }


@widget_router.get("/widget/embed.js")
async def embed_script():
    """JavaScript embed script for external dashboards.

    Usage::

        <script src="https://your-faultray-instance/widget/embed.js"></script>
        <div id="faultray-widget"></div>
        <script>
            FaultRay.renderCard(
                document.getElementById('faultray-widget'),
                'https://your-faultray-instance'
            );
        </script>
    """
    js = """\
window.FaultRay = {
    renderCard: function(container, apiUrl, projectId) {
        var iframe = document.createElement('iframe');
        var pid = projectId || 'default';
        iframe.src = apiUrl + '/widget/scorecard?project_id=' + encodeURIComponent(pid);
        iframe.style.border = 'none';
        iframe.style.width = '320px';
        iframe.style.height = '140px';
        iframe.style.borderRadius = '8px';
        container.appendChild(iframe);
    }
};
"""
    return Response(content=js, media_type="application/javascript")
