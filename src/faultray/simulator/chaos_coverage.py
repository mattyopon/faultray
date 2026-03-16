"""Chaos Coverage Map — coverage analysis for chaos engineering.

Visualises and quantifies how thoroughly chaos testing covers an
infrastructure.  Like code-coverage for chaos engineering: shows which
components have been tested with which failure modes, identifies blind
spots, and tracks coverage improvement over time.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FailureDomain(str, Enum):
    """Broad categories of failure that can be injected."""

    COMPUTE = "compute"
    NETWORK = "network"
    STORAGE = "storage"
    DATABASE = "database"
    DEPENDENCY = "dependency"
    SECURITY = "security"
    CAPACITY = "capacity"
    LATENCY = "latency"


class CoverageStatus(str, Enum):
    """How well a component / domain combination has been tested."""

    TESTED = "tested"
    PARTIALLY_TESTED = "partially_tested"
    UNTESTED = "untested"
    EXCLUDED = "excluded"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class CoverageEntry(BaseModel):
    """Single coverage cell — one component x one failure domain."""

    component_id: str
    failure_domain: FailureDomain
    status: CoverageStatus = CoverageStatus.UNTESTED
    last_tested: Optional[datetime] = None
    test_count: int = 0
    last_result_passed: Optional[bool] = None


class CoverageGap(BaseModel):
    """An identified gap in chaos coverage."""

    component_id: str
    missing_domains: list[FailureDomain]
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    priority: int = 0
    recommendation: str = ""


class CoverageTrend(BaseModel):
    """A point-in-time snapshot of overall coverage."""

    timestamp: datetime
    overall_percent: float
    by_domain: dict[str, float] = Field(default_factory=dict)


class ChaosCoverageReport(BaseModel):
    """Full coverage report returned by the engine."""

    overall_coverage_percent: float = 0.0
    by_component: dict[str, float] = Field(default_factory=dict)
    by_domain: dict[str, float] = Field(default_factory=dict)
    gaps: list[CoverageGap] = Field(default_factory=list)
    trends: list[CoverageTrend] = Field(default_factory=list)
    total_tests_run: int = 0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALL_DOMAINS = list(FailureDomain)
_DOMAIN_COUNT = len(_ALL_DOMAINS)

# Components with many dependents are riskier when untested.
_HIGH_RISK_THRESHOLD = 0.7
_MEDIUM_RISK_THRESHOLD = 0.4


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ChaosCoverageEngine:
    """Tracks and analyses chaos-test coverage across an infrastructure graph."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        # key = (component_id, FailureDomain)
        self._entries: dict[tuple[str, FailureDomain], CoverageEntry] = {}
        self._excluded: set[str] = set()
        self._trends: list[CoverageTrend] = []
        self._total_tests: int = 0

        # Seed entries for every component x domain pair.
        for comp_id in graph.components:
            for domain in _ALL_DOMAINS:
                self._entries[(comp_id, domain)] = CoverageEntry(
                    component_id=comp_id,
                    failure_domain=domain,
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_test(
        self,
        component_id: str,
        domain: FailureDomain,
        passed: bool,
    ) -> None:
        """Record the result of a chaos test."""
        if component_id not in self._graph.components:
            raise KeyError(f"Unknown component: {component_id}")

        key = (component_id, domain)
        entry = self._entries[key]
        entry.test_count += 1
        entry.last_tested = datetime.now(timezone.utc)
        entry.last_result_passed = passed
        entry.status = CoverageStatus.TESTED
        self._total_tests += 1

    def exclude_component(self, component_id: str) -> None:
        """Mark a component as excluded from coverage calculations."""
        if component_id not in self._graph.components:
            raise KeyError(f"Unknown component: {component_id}")
        self._excluded.add(component_id)
        for domain in _ALL_DOMAINS:
            self._entries[(component_id, domain)].status = CoverageStatus.EXCLUDED

    def get_component_coverage(self, component_id: str) -> dict[str, CoverageStatus]:
        """Return per-domain coverage status for a single component."""
        if component_id not in self._graph.components:
            raise KeyError(f"Unknown component: {component_id}")
        result: dict[str, CoverageStatus] = {}
        for domain in _ALL_DOMAINS:
            result[domain.value] = self._entries[(component_id, domain)].status
        return result

    def get_domain_coverage(self, domain: FailureDomain) -> float:
        """Percentage of (non-excluded) components tested for *domain*."""
        active = [
            cid for cid in self._graph.components if cid not in self._excluded
        ]
        if not active:
            return 0.0
        tested = sum(
            1
            for cid in active
            if self._entries[(cid, domain)].status == CoverageStatus.TESTED
        )
        return tested / len(active) * 100.0

    def identify_gaps(self) -> list[CoverageGap]:
        """Return untested areas sorted by descending risk."""
        gaps: list[CoverageGap] = []
        for comp_id in self._graph.components:
            if comp_id in self._excluded:
                continue
            missing: list[FailureDomain] = []
            for domain in _ALL_DOMAINS:
                if self._entries[(comp_id, domain)].status == CoverageStatus.UNTESTED:
                    missing.append(domain)
            if not missing:
                continue

            risk = self._component_risk(comp_id, missing)
            priority = self._risk_to_priority(risk)
            rec = self._build_recommendation(comp_id, missing, risk)
            gaps.append(CoverageGap(
                component_id=comp_id,
                missing_domains=missing,
                risk_score=round(risk, 4),
                priority=priority,
                recommendation=rec,
            ))

        gaps.sort(key=lambda g: (-g.risk_score, g.component_id))
        return gaps

    def calculate_overall_coverage(self) -> float:
        """Overall coverage percentage (tested cells / active cells)."""
        active = [
            cid for cid in self._graph.components if cid not in self._excluded
        ]
        if not active:
            return 0.0
        total_cells = len(active) * _DOMAIN_COUNT
        tested_cells = sum(
            1
            for cid in active
            for d in _ALL_DOMAINS
            if self._entries[(cid, d)].status == CoverageStatus.TESTED
        )
        return tested_cells / total_cells * 100.0

    def snapshot_trend(self) -> CoverageTrend:
        """Capture and store a coverage snapshot for trend tracking."""
        overall = self.calculate_overall_coverage()
        by_domain: dict[str, float] = {}
        for d in _ALL_DOMAINS:
            by_domain[d.value] = round(self.get_domain_coverage(d), 4)
        trend = CoverageTrend(
            timestamp=datetime.now(timezone.utc),
            overall_percent=round(overall, 4),
            by_domain=by_domain,
        )
        self._trends.append(trend)
        return trend

    def generate_report(self) -> ChaosCoverageReport:
        """Build a full coverage report."""
        overall = self.calculate_overall_coverage()

        by_component: dict[str, float] = {}
        for comp_id in self._graph.components:
            if comp_id in self._excluded:
                continue
            tested = sum(
                1
                for d in _ALL_DOMAINS
                if self._entries[(comp_id, d)].status == CoverageStatus.TESTED
            )
            by_component[comp_id] = round(tested / _DOMAIN_COUNT * 100.0, 4)

        by_domain: dict[str, float] = {}
        for d in _ALL_DOMAINS:
            by_domain[d.value] = round(self.get_domain_coverage(d), 4)

        gaps = self.identify_gaps()
        recommendations = self._build_report_recommendations(gaps, overall)

        return ChaosCoverageReport(
            overall_coverage_percent=round(overall, 4),
            by_component=by_component,
            by_domain=by_domain,
            gaps=gaps,
            trends=list(self._trends),
            total_tests_run=self._total_tests,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _component_risk(
        self, comp_id: str, missing: list[FailureDomain]
    ) -> float:
        """Compute a 0-1 risk score based on missing coverage & graph position."""
        missing_ratio = len(missing) / _DOMAIN_COUNT
        dependents = self._graph.get_dependents(comp_id)
        dep_factor = min(len(dependents) / max(len(self._graph.components), 1), 1.0)
        return round(min(1.0, 0.5 * missing_ratio + 0.5 * dep_factor), 4)

    @staticmethod
    def _risk_to_priority(risk: float) -> int:
        """Convert a risk float to a 1-3 priority (1 = highest)."""
        if risk >= _HIGH_RISK_THRESHOLD:
            return 1
        if risk >= _MEDIUM_RISK_THRESHOLD:
            return 2
        return 3

    @staticmethod
    def _build_recommendation(
        comp_id: str,
        missing: list[FailureDomain],
        risk: float,
    ) -> str:
        names = ", ".join(d.value for d in missing)
        if risk >= _HIGH_RISK_THRESHOLD:
            return f"CRITICAL: {comp_id} lacks testing in {names}. Schedule immediately."
        if risk >= _MEDIUM_RISK_THRESHOLD:
            return f"WARNING: {comp_id} missing coverage for {names}. Plan testing soon."
        return f"INFO: {comp_id} could benefit from {names} testing."

    @staticmethod
    def _build_report_recommendations(
        gaps: list[CoverageGap],
        overall: float,
    ) -> list[str]:
        recs: list[str] = []
        if overall < 25.0:
            recs.append(
                "Coverage is very low. Start with high-priority components."
            )
        elif overall < 50.0:
            recs.append("Coverage is below 50%. Focus on critical gaps.")
        elif overall < 75.0:
            recs.append("Good progress. Address remaining gaps to harden resilience.")
        else:
            recs.append("Coverage is strong. Maintain and expand edge-case testing.")

        critical = [g for g in gaps if g.priority == 1]
        if critical:
            recs.append(
                f"{len(critical)} component(s) have critical coverage gaps."
            )
        return recs
