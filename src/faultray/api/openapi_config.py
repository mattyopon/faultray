# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

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
        "FaultRay — Zero-risk infrastructure chaos engineering API.\n\n"
        "Simulate infrastructure failures, evaluate resilience, and prove "
        "your system's availability ceiling mathematically.\n\n"
        "## Features\n"
        "- Run 2,000+ chaos scenarios against your infrastructure model\n"
        "- 5 simulation engines (Cascade, Dynamic, Ops, What-If, Capacity)\n"
        "- 3-Layer Availability Limit Model\n"
        "- Cost impact analysis with ROI calculations\n"
        "- Multi-framework compliance assessment (SOC 2, ISO 27001, PCI DSS, DORA)\n"
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
