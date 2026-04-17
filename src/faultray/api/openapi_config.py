# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""OpenAPI configuration for FaultRay API."""
from __future__ import annotations


OPENAPI_TAGS = [
    {
        "name": "simulation",
        "description": "Run chaos simulations and retrieve results",
    },
    {
        "name": "infrastructure",
        "description": "Manage infrastructure models and components",
    },
    {
        "name": "reports",
        "description": "Generate and retrieve simulation reports",
    },
    {
        "name": "compliance",
        "description": "Compliance assessment and reporting",
    },
    {
        "name": "cost",
        "description": "Cost impact analysis and ROI calculations",
    },
    {
        "name": "security",
        "description": "Security resilience assessment",
    },
    {
        "name": "health",
        "description": "Service health and status",
    },
]

OPENAPI_CONFIG = {
    "title": "FaultRay API",
    "description": (
        "FaultRay — Pre-deployment resilience simulation API (research prototype).\n\n"
        "Simulate infrastructure failures from declared topology, evaluate "
        "structural resilience, and estimate your system's model-based "
        "availability ceiling — complements runtime chaos engineering.\n\n"
        "## Features\n"
        "- Run thousands of chaos scenarios against your declared infrastructure model\n"
        "- 5 simulation engines (Cascade, Dynamic, Ops, What-If, Capacity)\n"
        "- 3-Layer Availability Limit Model (model-based estimate)\n"
        "- Cost impact analysis with illustrative ROI calculations\n"
        "- Research-prototype mappings to SOC 2 / ISO 27001 / PCI DSS / DORA frameworks (not audit-certified)\n"
        "- Security resilience scoring\n"
        "- Multi-region DR evaluation\n\n"
        "## Authentication\n"
        "API key authentication via `X-API-Key` header or OAuth2.\n\n"
        "## Rate Limiting\n"
        "60 requests per minute per API key."
    ),
    "version": "10.3.0",
    "contact": {
        "name": "FaultRay Support",
        "url": "https://faultray.com",
        "email": "support@faultray.com",
    },
    "license_info": {
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    "docs_url": "/docs",
    "redoc_url": "/redoc",
    "openapi_url": "/openapi.json",
}
