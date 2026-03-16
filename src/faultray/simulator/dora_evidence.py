"""DORA (Digital Operational Resilience Act) Compliance Evidence Engine.

Automatically generates audit-ready evidence for EU financial regulation DORA
(effective January 2025). Maps chaos test results to DORA articles and generates
structured audit trails.

Covers Articles 11, 24, 25, 26, and 28 of DORA regulation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


class DORAArticle(str, Enum):
    """DORA regulation articles relevant to ICT resilience testing."""

    ARTICLE_11 = "article_11"  # ICT Risk Management - Testing
    ARTICLE_24 = "article_24"  # General Requirements for Testing
    ARTICLE_25 = "article_25"  # TLPT (Threat-Led Penetration Testing)
    ARTICLE_26 = "article_26"  # Requirements for Testers
    ARTICLE_28 = "article_28"  # Third-Party ICT Risk Management


class TestClassification(str, Enum):
    """Classification of test types under DORA."""

    BASIC_TESTING = "basic_testing"
    ADVANCED_TESTING = "advanced_testing"
    TLPT = "tlpt"  # Threat-Led Penetration Testing


class EvidenceStatus(str, Enum):
    """Compliance status for a DORA control."""

    COMPLIANT = "compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    NON_COMPLIANT = "non_compliant"
    NOT_APPLICABLE = "not_applicable"


class DORAControl(BaseModel):
    """A single DORA compliance control."""

    article: DORAArticle
    control_id: str
    description: str
    test_requirements: list[str] = Field(default_factory=list)


class EvidenceRecord(BaseModel):
    """An audit evidence record from a chaos test."""

    control_id: str
    timestamp: datetime
    test_type: str
    test_description: str
    result: str  # pass, fail, partial
    severity: str  # critical, high, medium, low
    remediation_required: bool = False
    artifacts: list[str] = Field(default_factory=list)


class DORAGapAnalysis(BaseModel):
    """Gap analysis for a single DORA control."""

    control_id: str
    status: EvidenceStatus
    gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    risk_score: float = 0.0  # 0.0 (no risk) to 1.0 (critical risk)


class DORAComplianceReport(BaseModel):
    """Complete DORA compliance report."""

    overall_status: EvidenceStatus
    article_results: dict[str, EvidenceStatus] = Field(default_factory=dict)
    gap_analyses: list[DORAGapAnalysis] = Field(default_factory=list)
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    report_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    next_review_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(days=90)
    )


# Built-in DORA controls (24 controls across 5 articles)
_DORA_CONTROLS: list[dict] = [
    # Article 11 - ICT Risk Management Testing (6 controls)
    {"article": "article_11", "control_id": "DORA-11.01", "description": "ICT systems and tools are periodically tested for resilience", "test_requirements": ["Periodic resilience testing", "Test coverage of critical systems"]},
    {"article": "article_11", "control_id": "DORA-11.02", "description": "Vulnerability assessments and scans are performed", "test_requirements": ["Vulnerability scanning", "Security assessment"]},
    {"article": "article_11", "control_id": "DORA-11.03", "description": "Network security tests are conducted", "test_requirements": ["Network security testing", "Firewall validation"]},
    {"article": "article_11", "control_id": "DORA-11.04", "description": "Compatibility and performance testing under stress", "test_requirements": ["Stress testing", "Performance benchmarks"]},
    {"article": "article_11", "control_id": "DORA-11.05", "description": "Scenario-based tests including failover and switchover", "test_requirements": ["Failover testing", "Switchover testing", "DR simulation"]},
    {"article": "article_11", "control_id": "DORA-11.06", "description": "Source code reviews where applicable", "test_requirements": ["Code review", "Static analysis"]},
    # Article 24 - General Requirements for Testing (5 controls)
    {"article": "article_24", "control_id": "DORA-24.01", "description": "Testing programme is risk-based and proportionate", "test_requirements": ["Risk-based test planning", "Proportionality assessment"]},
    {"article": "article_24", "control_id": "DORA-24.02", "description": "Testing covers all critical ICT systems", "test_requirements": ["Critical system identification", "Test completeness"]},
    {"article": "article_24", "control_id": "DORA-24.03", "description": "Test results are documented and reported", "test_requirements": ["Test documentation", "Result reporting"]},
    {"article": "article_24", "control_id": "DORA-24.04", "description": "Identified issues are remediated in a timely manner", "test_requirements": ["Remediation tracking", "Timeline adherence"]},
    {"article": "article_24", "control_id": "DORA-24.05", "description": "Testing frequency is adequate for risk profile", "test_requirements": ["Test scheduling", "Frequency validation"]},
    # Article 25 - TLPT (5 controls)
    {"article": "article_25", "control_id": "DORA-25.01", "description": "TLPT covers critical or important functions", "test_requirements": ["Critical function mapping", "TLPT scope definition"]},
    {"article": "article_25", "control_id": "DORA-25.02", "description": "TLPT simulates real-world attack techniques", "test_requirements": ["Attack simulation", "TTPs coverage"]},
    {"article": "article_25", "control_id": "DORA-25.03", "description": "TLPT includes live production systems", "test_requirements": ["Production system testing", "Live environment coverage"]},
    {"article": "article_25", "control_id": "DORA-25.04", "description": "TLPT is performed at least every three years", "test_requirements": ["TLPT scheduling", "Three-year cycle"]},
    {"article": "article_25", "control_id": "DORA-25.05", "description": "TLPT results are reviewed by management", "test_requirements": ["Management review", "Executive sign-off"]},
    # Article 26 - Requirements for Testers (4 controls)
    {"article": "article_26", "control_id": "DORA-26.01", "description": "Testers have appropriate qualifications", "test_requirements": ["Tester certification", "Qualification verification"]},
    {"article": "article_26", "control_id": "DORA-26.02", "description": "Testers are independent from the tested entity", "test_requirements": ["Independence verification", "Conflict of interest check"]},
    {"article": "article_26", "control_id": "DORA-26.03", "description": "Testers maintain professional standards", "test_requirements": ["Professional standards", "Ethical conduct"]},
    {"article": "article_26", "control_id": "DORA-26.04", "description": "Testers carry professional indemnity insurance", "test_requirements": ["Insurance verification", "Liability coverage"]},
    # Article 28 - Third-Party ICT Risk (4 controls)
    {"article": "article_28", "control_id": "DORA-28.01", "description": "Third-party ICT providers are assessed for risk", "test_requirements": ["Third-party risk assessment", "Provider evaluation"]},
    {"article": "article_28", "control_id": "DORA-28.02", "description": "Concentration risk from third parties is managed", "test_requirements": ["Concentration risk analysis", "Provider diversification"]},
    {"article": "article_28", "control_id": "DORA-28.03", "description": "Contractual arrangements include resilience requirements", "test_requirements": ["Contract review", "SLA verification"]},
    {"article": "article_28", "control_id": "DORA-28.04", "description": "Exit strategies for critical third-party services", "test_requirements": ["Exit strategy", "Transition planning"]},
]


def _build_controls() -> list[DORAControl]:
    """Build the list of DORA controls from the static definition."""
    return [DORAControl(**c) for c in _DORA_CONTROLS]


class DORAEvidenceEngine:
    """DORA Compliance Evidence Engine.

    Evaluates an InfraGraph against DORA regulation articles and generates
    audit-ready evidence, gap analyses, and compliance reports.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self.controls = _build_controls()

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify_test(
        self, scenario_name: str, involves_third_party: bool = False
    ) -> TestClassification:
        """Classify a test scenario per DORA test categories."""
        name_lower = scenario_name.lower()
        tlpt_keywords = {"tlpt", "penetration", "red team", "attack", "threat-led"}
        advanced_keywords = {
            "failover", "switchover", "disaster", "cascade", "chaos",
            "stress", "performance", "load", "recovery",
        }
        if any(kw in name_lower for kw in tlpt_keywords):
            return TestClassification.TLPT
        if any(kw in name_lower for kw in advanced_keywords):
            return TestClassification.ADVANCED_TESTING
        if involves_third_party:
            return TestClassification.ADVANCED_TESTING
        return TestClassification.BASIC_TESTING

    # ------------------------------------------------------------------
    # Control evaluation helpers
    # ------------------------------------------------------------------

    def _has_redundancy(self) -> bool:
        for c in self.graph.components.values():
            if c.replicas >= 2:
                return True
        return False

    def _has_failover(self) -> bool:
        for c in self.graph.components.values():
            if c.failover.enabled:
                return True
        return False

    def _has_monitoring(self) -> bool:
        keywords = {"monitoring", "prometheus", "grafana", "otel", "datadog"}
        for c in self.graph.components.values():
            combined = (c.id + " " + c.name).lower()
            if any(kw in combined for kw in keywords):
                return True
        return False

    def _has_third_party(self) -> bool:
        for c in self.graph.components.values():
            if c.type == ComponentType.EXTERNAL_API:
                return True
        return False

    def _third_party_count(self) -> int:
        return sum(
            1 for c in self.graph.components.values()
            if c.type == ComponentType.EXTERNAL_API
        )

    def _component_count(self) -> int:
        return len(self.graph.components)

    def _unhealthy_count(self) -> int:
        return sum(
            1 for c in self.graph.components.values()
            if c.health != HealthStatus.HEALTHY
        )

    # ------------------------------------------------------------------
    # Evaluate a single control
    # ------------------------------------------------------------------

    def evaluate_control(self, control: DORAControl) -> DORAGapAnalysis:
        """Evaluate a single DORA control against the infrastructure graph."""
        gaps: list[str] = []
        recommendations: list[str] = []
        risk = 0.0

        n_comps = self._component_count()
        if n_comps == 0:
            return DORAGapAnalysis(
                control_id=control.control_id,
                status=EvidenceStatus.NOT_APPLICABLE,
                gaps=["No components in graph"],
                recommendations=["Add infrastructure components to evaluate"],
                risk_score=0.0,
            )

        article = control.article

        if article == DORAArticle.ARTICLE_11:
            has_red = self._has_redundancy()
            has_fo = self._has_failover()
            has_mon = self._has_monitoring()
            unhealthy = self._unhealthy_count()
            if not has_red:
                gaps.append("No redundancy detected")
                recommendations.append("Add replicas >= 2 for critical components")
                risk += 0.3
            if not has_fo:
                gaps.append("No failover configured")
                recommendations.append("Enable failover for databases and critical services")
                risk += 0.3
            if not has_mon:
                gaps.append("No monitoring detected")
                recommendations.append("Deploy monitoring (Prometheus, Datadog, etc.)")
                risk += 0.2
            if unhealthy > 0:
                gaps.append(f"{unhealthy} component(s) not healthy")
                recommendations.append("Investigate and remediate unhealthy components")
                risk += 0.2

        elif article == DORAArticle.ARTICLE_24:
            has_red = self._has_redundancy()
            has_fo = self._has_failover()
            if not has_red and not has_fo:
                gaps.append("No resilience mechanisms configured")
                recommendations.append("Implement redundancy and failover")
                risk += 0.5
            elif not has_red or not has_fo:
                gaps.append("Partial resilience coverage")
                recommendations.append("Ensure both redundancy and failover are configured")
                risk += 0.25

        elif article == DORAArticle.ARTICLE_25:
            # TLPT requires production-like environment + critical functions
            has_red = self._has_redundancy()
            has_fo = self._has_failover()
            if not has_red:
                gaps.append("TLPT requires redundant systems for safe testing")
                recommendations.append("Add redundancy before TLPT execution")
                risk += 0.4
            if not has_fo:
                gaps.append("TLPT requires failover capability")
                recommendations.append("Enable failover to support TLPT scenarios")
                risk += 0.3

        elif article == DORAArticle.ARTICLE_26:
            # Tester requirements - evaluated at process level, light infra checks
            has_mon = self._has_monitoring()
            if not has_mon:
                gaps.append("No monitoring to validate tester activities")
                recommendations.append("Deploy monitoring for audit trail of testing activities")
                risk += 0.3

        elif article == DORAArticle.ARTICLE_28:
            tp_count = self._third_party_count()
            if tp_count == 0:
                return DORAGapAnalysis(
                    control_id=control.control_id,
                    status=EvidenceStatus.NOT_APPLICABLE,
                    gaps=[],
                    recommendations=[],
                    risk_score=0.0,
                )
            if tp_count > n_comps * 0.5:
                gaps.append(f"High third-party concentration: {tp_count}/{n_comps}")
                recommendations.append("Reduce dependency on third-party providers")
                risk += 0.5
            else:
                risk += 0.1  # some third-party risk always exists

        risk = min(risk, 1.0)

        if not gaps:
            status = EvidenceStatus.COMPLIANT
        elif risk >= 0.5:
            status = EvidenceStatus.NON_COMPLIANT
        else:
            status = EvidenceStatus.PARTIALLY_COMPLIANT

        return DORAGapAnalysis(
            control_id=control.control_id,
            status=status,
            gaps=gaps,
            recommendations=recommendations,
            risk_score=round(risk, 2),
        )

    # ------------------------------------------------------------------
    # Evidence generation
    # ------------------------------------------------------------------

    def generate_evidence(
        self, scenarios_run: list[dict]
    ) -> list[EvidenceRecord]:
        """Create evidence records from test scenario results.

        Each scenario dict should have keys: name, result, severity, description
        (all optional with defaults).
        """
        records: list[EvidenceRecord] = []
        now = datetime.now(timezone.utc)
        for i, scenario in enumerate(scenarios_run):
            name = scenario.get("name", f"scenario_{i}")
            result = scenario.get("result", "pass")
            severity = scenario.get("severity", "medium")
            description = scenario.get("description", name)
            involves_tp = scenario.get("involves_third_party", False)
            classification = self.classify_test(name, involves_tp)
            # Map to relevant control
            if classification == TestClassification.TLPT:
                control_id = "DORA-25.01"
            elif involves_tp:
                control_id = "DORA-28.01"
            elif classification == TestClassification.ADVANCED_TESTING:
                control_id = "DORA-11.05"
            else:
                control_id = "DORA-24.01"
            records.append(EvidenceRecord(
                control_id=control_id,
                timestamp=now,
                test_type=classification.value,
                test_description=description,
                result=result,
                severity=severity,
                remediation_required=(result != "pass"),
                artifacts=[f"evidence/{name.replace(' ', '_')}.json"],
            ))
        return records

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------

    def gap_analysis(self) -> list[DORAGapAnalysis]:
        """Run gap analysis across all 24 DORA controls."""
        return [self.evaluate_control(c) for c in self.controls]

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(
        self, scenarios_run: list[dict]
    ) -> DORAComplianceReport:
        """Generate a complete DORA compliance report."""
        gaps = self.gap_analysis()
        evidence = self.generate_evidence(scenarios_run)

        # Aggregate per-article status
        article_statuses: dict[str, list[EvidenceStatus]] = {}
        for g in gaps:
            # Extract article from control_id prefix
            ctrl = next(
                (c for c in self.controls if c.control_id == g.control_id), None
            )
            if ctrl:
                art = ctrl.article.value
                article_statuses.setdefault(art, []).append(g.status)

        article_results: dict[str, EvidenceStatus] = {}
        for art, statuses in article_statuses.items():
            if all(s == EvidenceStatus.NOT_APPLICABLE for s in statuses):
                article_results[art] = EvidenceStatus.NOT_APPLICABLE
            elif all(s == EvidenceStatus.COMPLIANT for s in statuses):
                article_results[art] = EvidenceStatus.COMPLIANT
            elif all(
                s in (EvidenceStatus.COMPLIANT, EvidenceStatus.NOT_APPLICABLE)
                for s in statuses
            ):
                article_results[art] = EvidenceStatus.COMPLIANT
            elif any(s == EvidenceStatus.NON_COMPLIANT for s in statuses):
                article_results[art] = EvidenceStatus.NON_COMPLIANT
            else:
                article_results[art] = EvidenceStatus.PARTIALLY_COMPLIANT

        # Overall status
        all_statuses = list(article_results.values())
        if not all_statuses:
            overall = EvidenceStatus.NOT_APPLICABLE
        elif all(s == EvidenceStatus.NOT_APPLICABLE for s in all_statuses):
            overall = EvidenceStatus.NOT_APPLICABLE
        elif all(
            s in (EvidenceStatus.COMPLIANT, EvidenceStatus.NOT_APPLICABLE)
            for s in all_statuses
        ):
            overall = EvidenceStatus.COMPLIANT
        elif any(s == EvidenceStatus.NON_COMPLIANT for s in all_statuses):
            overall = EvidenceStatus.NON_COMPLIANT
        else:
            overall = EvidenceStatus.PARTIALLY_COMPLIANT

        return DORAComplianceReport(
            overall_status=overall,
            article_results=article_results,
            gap_analyses=gaps,
            evidence_records=evidence,
        )

    # ------------------------------------------------------------------
    # Audit export
    # ------------------------------------------------------------------

    def export_audit_package(self) -> dict:
        """Export all evidence and analysis as a structured audit package."""
        gaps = self.gap_analysis()
        return {
            "framework": "DORA",
            "version": "2022/2554",
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "controls": [c.model_dump() for c in self.controls],
            "gap_analyses": [g.model_dump() for g in gaps],
            "total_controls": len(self.controls),
            "compliant_count": sum(
                1 for g in gaps if g.status == EvidenceStatus.COMPLIANT
            ),
            "non_compliant_count": sum(
                1 for g in gaps if g.status == EvidenceStatus.NON_COMPLIANT
            ),
            "partially_compliant_count": sum(
                1 for g in gaps
                if g.status == EvidenceStatus.PARTIALLY_COMPLIANT
            ),
            "not_applicable_count": sum(
                1 for g in gaps if g.status == EvidenceStatus.NOT_APPLICABLE
            ),
        }
