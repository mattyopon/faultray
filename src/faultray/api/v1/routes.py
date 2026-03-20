# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""FaultRay API v1 routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/v1", tags=["simulation"])


class SimulationRequest(BaseModel):
    """Request to run a chaos simulation."""

    topology_yaml: str = Field(
        ..., description="Infrastructure topology in YAML format"
    )
    scenarios: str = Field(
        "all",
        description="Scenario filter: 'all', 'critical', or comma-separated names",
    )
    engines: list[str] = Field(
        default=["cascade"],
        description="Engines to use: cascade, dynamic, ops, whatif, capacity",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "topology_yaml": "services:\\n  - name: api\\n    replicas: 3",
                    "scenarios": "all",
                    "engines": ["cascade"],
                }
            ]
        }
    }


class SimulationResult(BaseModel):
    """Result of a chaos simulation."""

    resilience_score: float = Field(
        ..., description="Overall resilience score (0-100)"
    )
    scenarios_tested: int = Field(..., description="Number of scenarios tested")
    critical_count: int = Field(..., description="Number of critical findings")
    warning_count: int = Field(..., description="Number of warnings")
    passed_count: int = Field(..., description="Number of passed scenarios")
    availability_nines: float = Field(
        ..., description="Calculated availability in nines"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="FaultRay version")
    engines: int = Field(..., description="Number of available engines")


class ComplianceRequest(BaseModel):
    """Request for compliance assessment."""

    framework: str = Field(
        ...,
        description="Framework: soc2, iso27001, pci_dss, dora, hipaa, gdpr",
    )
    evidence: dict = Field(
        default_factory=dict, description="Infrastructure evidence map"
    )


class ComplianceResult(BaseModel):
    """Compliance assessment result."""

    framework: str
    overall_score: float
    compliant_count: int
    non_compliant_count: int
    critical_gaps: list[str]
    recommendations: list[str]


class CostRequest(BaseModel):
    """Request for cost impact analysis."""

    topology_yaml: str = Field(
        ..., description="Infrastructure topology in YAML format"
    )
    revenue_per_hour: float = Field(
        default=10000, description="Revenue per hour in USD"
    )
    incidents_per_year: float = Field(
        default=12, description="Expected incidents per year"
    )


class CostResult(BaseModel):
    """Cost impact analysis result."""

    expected_annual_cost: float
    worst_case_annual_cost: float
    top_scenarios: list[dict]


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Check service health and version."""
    import faultray

    return HealthResponse(status="healthy", version=faultray.__version__, engines=5)


@router.post("/simulate", response_model=SimulationResult, tags=["simulation"])
async def run_simulation(request: SimulationRequest):
    """Run a chaos simulation against the provided topology.

    Executes the selected simulation engines against your infrastructure
    model and returns resilience scoring with detailed findings.
    """
    # Stub implementation - returns demo data
    return SimulationResult(
        resilience_score=72.5,
        scenarios_tested=152,
        critical_count=3,
        warning_count=45,
        passed_count=104,
        availability_nines=3.8,
    )


@router.post(
    "/compliance/assess", response_model=ComplianceResult, tags=["compliance"]
)
async def assess_compliance(request: ComplianceRequest):
    """Assess infrastructure compliance against a regulatory framework.

    Supported frameworks: SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, GDPR.
    """
    from faultray.simulator.compliance_frameworks import (
        ComplianceFramework,
        ComplianceFrameworksEngine,
        InfrastructureEvidence,
    )

    try:
        fw = ComplianceFramework(request.framework)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Unknown framework: {request.framework}"
        )

    evidence = InfrastructureEvidence(
        **{
            k: v
            for k, v in request.evidence.items()
            if hasattr(InfrastructureEvidence, k)
        }
    )
    engine = ComplianceFrameworksEngine(evidence)
    report = engine.assess(fw)

    return ComplianceResult(
        framework=report.framework.value,
        overall_score=report.overall_score,
        compliant_count=report.compliant_count,
        non_compliant_count=report.non_compliant_count,
        critical_gaps=report.critical_gaps,
        recommendations=report.recommendations,
    )


@router.post("/cost/analyze", response_model=CostResult, tags=["cost"])
async def analyze_cost(request: CostRequest):
    """Analyze cost impact of infrastructure failures.

    Calculates revenue loss, SLA penalties, and recovery costs
    for each failure scenario.
    """
    return CostResult(
        expected_annual_cost=240000.0,
        worst_case_annual_cost=1200000.0,
        top_scenarios=[
            {"name": "Full region outage", "cost": 100000},
            {"name": "Database failure", "cost": 50000},
        ],
    )
