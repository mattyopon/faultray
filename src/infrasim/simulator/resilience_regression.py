"""Resilience regression detector — CI/CD integration for resilience checks.

Detects resilience regressions between infrastructure versions by comparing
key metrics: resilience score, SPOF count, dependency depth, redundancy
coverage, etc. Returns pass/fail with exit codes for CI/CD integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from infrasim.model.components import ComponentType
from infrasim.model.graph import InfraGraph


class RegressionSeverity(str, Enum):
    """Severity of a regression."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class CheckResult(str, Enum):
    """Result of a regression check."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class RegressionCheck:
    """Definition of a single regression check."""

    id: str
    name: str
    description: str
    severity: RegressionSeverity
    metric: str  # name of the metric being checked
    direction: str  # "higher_is_better" or "lower_is_better"
    threshold_percent: float  # max allowed regression %


@dataclass
class CheckOutcome:
    """Result of a single regression check."""

    check: RegressionCheck
    result: CheckResult
    baseline_value: float
    current_value: float
    delta: float
    delta_percent: float
    message: str


@dataclass
class RegressionReport:
    """Full regression detection report."""

    outcomes: list[CheckOutcome]
    overall_result: CheckResult
    passed_count: int
    failed_count: int
    warned_count: int
    skipped_count: int
    summary: str
    exit_code: int  # 0 = pass, 1 = fail, 2 = warn


@dataclass
class InfraSnapshot:
    """Snapshot of infrastructure metrics for comparison."""

    resilience_score: float
    component_count: int
    spof_count: int
    avg_replicas: float
    max_dependency_depth: int
    failover_coverage: float  # 0-100
    encryption_coverage: float  # 0-100
    monitoring_coverage: float  # 0-100
    avg_utilization: float
    single_points_of_failure: list[str]
    external_dependency_count: int


_DEFAULT_CHECKS = [
    RegressionCheck(
        id="resilience-score",
        name="Resilience Score",
        description="Overall resilience score must not decrease significantly",
        severity=RegressionSeverity.CRITICAL,
        metric="resilience_score",
        direction="higher_is_better",
        threshold_percent=5.0,
    ),
    RegressionCheck(
        id="spof-count",
        name="SPOF Count",
        description="Number of single points of failure must not increase",
        severity=RegressionSeverity.CRITICAL,
        metric="spof_count",
        direction="lower_is_better",
        threshold_percent=0.0,  # No new SPOFs allowed
    ),
    RegressionCheck(
        id="avg-replicas",
        name="Average Replicas",
        description="Average replica count must not decrease",
        severity=RegressionSeverity.WARNING,
        metric="avg_replicas",
        direction="higher_is_better",
        threshold_percent=10.0,
    ),
    RegressionCheck(
        id="max-depth",
        name="Max Dependency Depth",
        description="Maximum dependency chain depth must not increase",
        severity=RegressionSeverity.WARNING,
        metric="max_dependency_depth",
        direction="lower_is_better",
        threshold_percent=0.0,
    ),
    RegressionCheck(
        id="failover-coverage",
        name="Failover Coverage",
        description="Failover coverage must not decrease",
        severity=RegressionSeverity.WARNING,
        metric="failover_coverage",
        direction="higher_is_better",
        threshold_percent=5.0,
    ),
    RegressionCheck(
        id="encryption-coverage",
        name="Encryption Coverage",
        description="Encryption coverage must not decrease",
        severity=RegressionSeverity.WARNING,
        metric="encryption_coverage",
        direction="higher_is_better",
        threshold_percent=5.0,
    ),
    RegressionCheck(
        id="monitoring-coverage",
        name="Monitoring Coverage",
        description="Monitoring coverage must not decrease",
        severity=RegressionSeverity.INFO,
        metric="monitoring_coverage",
        direction="higher_is_better",
        threshold_percent=10.0,
    ),
    RegressionCheck(
        id="avg-utilization",
        name="Average Utilization",
        description="Average utilization must not increase excessively",
        severity=RegressionSeverity.INFO,
        metric="avg_utilization",
        direction="lower_is_better",
        threshold_percent=15.0,
    ),
]


class ResilientRegressionDetector:
    """Detect resilience regressions between infrastructure versions."""

    def __init__(
        self,
        checks: list[RegressionCheck] | None = None,
    ):
        self._checks = checks or list(_DEFAULT_CHECKS)

    def snapshot(self, graph: InfraGraph) -> InfraSnapshot:
        """Take a snapshot of current infrastructure metrics."""
        components = list(graph.components.values())
        if not components:
            return InfraSnapshot(
                resilience_score=100.0,
                component_count=0,
                spof_count=0,
                avg_replicas=0,
                max_dependency_depth=0,
                failover_coverage=100.0,
                encryption_coverage=100.0,
                monitoring_coverage=100.0,
                avg_utilization=0,
                single_points_of_failure=[],
                external_dependency_count=0,
            )

        # Resilience score
        resilience_score = graph.resilience_score()

        # SPOF analysis
        spofs: list[str] = []
        for comp in components:
            dependents = graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                spofs.append(comp.name)

        # Average replicas
        avg_replicas = sum(c.replicas for c in components) / len(components)

        # Max dependency depth (BFS)
        max_depth = 0
        for comp in components:
            depth = self._calculate_depth(graph, comp.id)
            max_depth = max(max_depth, depth)

        # Failover coverage
        critical = [
            c for c in components
            if c.type in (ComponentType.DATABASE, ComponentType.APP_SERVER, ComponentType.WEB_SERVER)
        ]
        failover_count = sum(1 for c in critical if c.failover.enabled)
        failover_coverage = (
            failover_count / len(critical) * 100 if critical else 100
        )

        # Encryption coverage
        encrypted = sum(
            1 for c in components
            if c.security.encryption_at_rest or c.security.encryption_in_transit
        )
        encryption_coverage = encrypted / len(components) * 100

        # Monitoring coverage
        monitored = sum(
            1 for c in components if c.security.log_enabled
        )
        monitoring_coverage = monitored / len(components) * 100

        # Average utilization
        avg_util = sum(c.utilization() for c in components) / len(components)

        # External dependencies
        ext_count = sum(
            1 for c in components if c.type == ComponentType.EXTERNAL_API
        )

        return InfraSnapshot(
            resilience_score=round(resilience_score, 1),
            component_count=len(components),
            spof_count=len(spofs),
            avg_replicas=round(avg_replicas, 2),
            max_dependency_depth=max_depth,
            failover_coverage=round(failover_coverage, 1),
            encryption_coverage=round(encryption_coverage, 1),
            monitoring_coverage=round(monitoring_coverage, 1),
            avg_utilization=round(avg_util, 1),
            single_points_of_failure=spofs,
            external_dependency_count=ext_count,
        )

    def compare(
        self,
        baseline: InfraSnapshot,
        current: InfraSnapshot,
    ) -> RegressionReport:
        """Compare two snapshots and detect regressions."""
        outcomes: list[CheckOutcome] = []

        for check in self._checks:
            outcome = self._evaluate_check(check, baseline, current)
            outcomes.append(outcome)

        passed = sum(1 for o in outcomes if o.result == CheckResult.PASS)
        failed = sum(1 for o in outcomes if o.result == CheckResult.FAIL)
        warned = sum(1 for o in outcomes if o.result == CheckResult.WARN)
        skipped = sum(1 for o in outcomes if o.result == CheckResult.SKIP)

        if failed > 0:
            overall = CheckResult.FAIL
            exit_code = 1
        elif warned > 0:
            overall = CheckResult.WARN
            exit_code = 2
        else:
            overall = CheckResult.PASS
            exit_code = 0

        summary_parts = []
        if failed:
            summary_parts.append(f"{failed} FAILED")
        if warned:
            summary_parts.append(f"{warned} WARNED")
        summary_parts.append(f"{passed} passed")
        summary = ", ".join(summary_parts)

        return RegressionReport(
            outcomes=outcomes,
            overall_result=overall,
            passed_count=passed,
            failed_count=failed,
            warned_count=warned,
            skipped_count=skipped,
            summary=summary,
            exit_code=exit_code,
        )

    def check_graph(
        self,
        baseline_graph: InfraGraph,
        current_graph: InfraGraph,
    ) -> RegressionReport:
        """Convenience method: snapshot both graphs and compare."""
        baseline = self.snapshot(baseline_graph)
        current = self.snapshot(current_graph)
        return self.compare(baseline, current)

    def add_check(self, check: RegressionCheck) -> None:
        """Add a custom regression check."""
        self._checks.append(check)

    def get_checks(self) -> list[RegressionCheck]:
        """Return all configured checks."""
        return list(self._checks)

    def format_report(self, report: RegressionReport) -> str:
        """Format report as readable text."""
        lines = ["Resilience Regression Report", "=" * 40, ""]

        for outcome in report.outcomes:
            icon = {"pass": "✅", "fail": "❌", "warn": "⚠️", "skip": "⏭️"}.get(
                outcome.result.value, "?"
            )
            lines.append(
                f"{icon} {outcome.check.name}: {outcome.message} "
                f"({outcome.baseline_value} → {outcome.current_value}, "
                f"{outcome.delta_percent:+.1f}%)"
            )

        lines.append("")
        lines.append(f"Result: {report.overall_result.value.upper()}")
        lines.append(f"Summary: {report.summary}")
        lines.append(f"Exit code: {report.exit_code}")

        return "\n".join(lines)

    def _evaluate_check(
        self,
        check: RegressionCheck,
        baseline: InfraSnapshot,
        current: InfraSnapshot,
    ) -> CheckOutcome:
        """Evaluate a single regression check."""
        baseline_val = getattr(baseline, check.metric, None)
        current_val = getattr(current, check.metric, None)

        if baseline_val is None or current_val is None:
            return CheckOutcome(
                check=check,
                result=CheckResult.SKIP,
                baseline_value=0,
                current_value=0,
                delta=0,
                delta_percent=0,
                message=f"Metric '{check.metric}' not available",
            )

        delta = current_val - baseline_val
        if baseline_val != 0:
            delta_percent = (delta / abs(baseline_val)) * 100
        else:
            delta_percent = 0 if delta == 0 else 100

        # Determine if this is a regression
        is_regression = False
        if check.direction == "higher_is_better":
            # Regression if current < baseline - threshold
            if delta_percent < -check.threshold_percent:
                is_regression = True
        else:  # lower_is_better
            # Regression if current > baseline + threshold
            if delta_percent > check.threshold_percent:
                is_regression = True

        if is_regression:
            if check.severity == RegressionSeverity.CRITICAL:
                result = CheckResult.FAIL
            else:
                result = CheckResult.WARN
            message = f"REGRESSION: {check.name} changed by {delta_percent:+.1f}%"
        else:
            result = CheckResult.PASS
            if delta_percent > 0 and check.direction == "higher_is_better":
                message = f"Improved by {delta_percent:+.1f}%"
            elif delta_percent < 0 and check.direction == "lower_is_better":
                message = f"Improved by {abs(delta_percent):.1f}%"
            else:
                message = f"No significant change ({delta_percent:+.1f}%)"

        return CheckOutcome(
            check=check,
            result=result,
            baseline_value=baseline_val,
            current_value=current_val,
            delta=round(delta, 2),
            delta_percent=round(delta_percent, 1),
            message=message,
        )

    def _calculate_depth(self, graph: InfraGraph, component_id: str) -> int:
        """Calculate max dependency depth from a component."""
        visited: set[str] = set()
        max_depth = 0

        def _dfs(cid: str, depth: int) -> None:
            nonlocal max_depth
            if cid in visited:
                return
            visited.add(cid)
            max_depth = max(max_depth, depth)
            for dep in graph.get_dependencies(cid):
                _dfs(dep.id, depth + 1)

        _dfs(component_id, 0)
        return max_depth
