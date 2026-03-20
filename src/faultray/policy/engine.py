# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Policy-as-Code Engine for infrastructure resilience policies.

Provides a simple, safe DSL for defining and evaluating infrastructure
policies against an ``InfraGraph``.  Inspired by OPA/Rego but intentionally
simpler -- no ``eval()`` is used; every condition type maps to an explicit
checker function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PolicySeverity(str, Enum):
    """Severity level of a policy rule."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class PolicyCategory(str, Enum):
    """Functional category of a policy rule."""

    RESILIENCE = "resilience"
    SECURITY = "security"
    COST = "cost"
    COMPLIANCE = "compliance"
    PERFORMANCE = "performance"
    OPERATIONAL = "operational"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PolicyRule:
    """A single policy rule definition."""

    id: str
    name: str
    description: str
    severity: PolicySeverity
    category: PolicyCategory
    condition: str
    message_template: str
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class PolicyViolation:
    """A single violation produced when a component fails a rule."""

    rule_id: str
    rule_name: str
    severity: PolicySeverity
    component_id: str
    component_name: str
    message: str
    remediation: str


@dataclass
class PolicyResult:
    """Evaluation result of a single rule across the graph."""

    rule: PolicyRule
    passed: bool
    violations: list[PolicyViolation]
    components_checked: int


@dataclass
class PolicyReport:
    """Aggregated report for a full policy set evaluation."""

    results: list[PolicyResult]
    total_rules: int
    passed_rules: int
    failed_rules: int
    violations_by_severity: dict[str, int]
    overall_pass: bool
    score: float


@dataclass
class PolicySet:
    """A named, versioned collection of policy rules."""

    name: str
    description: str
    version: str
    rules: list[PolicyRule]


# ---------------------------------------------------------------------------
# Condition checker type
# ---------------------------------------------------------------------------

# A checker receives (graph, component, rule) and returns a list of
# violations (empty == pass).
_CheckerFn = Callable[["InfraGraph", Any, PolicyRule], list[PolicyViolation]]


# ---------------------------------------------------------------------------
# Safe attribute helpers
# ---------------------------------------------------------------------------


def _safe_getattr(obj: Any, dotted_path: str, default: Any = None) -> Any:
    """Resolve a dotted attribute path without using ``eval``.

    Example::

        _safe_getattr(component, "failover.enabled")
        # equivalent to component.failover.enabled
    """
    parts = dotted_path.split(".")
    current = obj
    for part in parts:
        try:
            current = getattr(current, part)
        except AttributeError:
            return default
    return current


# ---------------------------------------------------------------------------
# Built-in checker functions
# ---------------------------------------------------------------------------


def _check_no_spof(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """No single points of failure -- replicas > 1 for components with dependents."""
    dependents = graph.get_dependents(component.id)
    if component.replicas <= 1 and len(dependents) > 0:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' is a single point of failure "
                f"(replicas={component.replicas}, dependents={len(dependents)})",
                remediation="Increase replicas to at least 2 or enable failover.",
            )
        ]
    return []


def _check_min_replicas(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """Minimum 2 replicas for databases."""
    if component.type == ComponentType.DATABASE and component.replicas < 2:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Database '{component.name}' has only {component.replicas} replica(s)",
                remediation="Configure at least 2 replicas for database high availability.",
            )
        ]
    return []


def _check_failover_required(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """Failover enabled for databases and critical services."""
    critical_types = {ComponentType.DATABASE, ComponentType.APP_SERVER}
    if component.type in critical_types and not component.failover.enabled:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' (type={component.type.value}) "
                "does not have failover enabled",
                remediation="Enable failover with appropriate promotion time and health checks.",
            )
        ]
    return []


def _check_encryption_at_rest(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """All databases/storage must have encryption at rest."""
    storage_types = {ComponentType.DATABASE, ComponentType.STORAGE}
    if component.type in storage_types and not component.security.encryption_at_rest:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' does not have encryption at rest enabled",
                remediation="Enable encryption at rest (e.g., AES-256) for data protection.",
            )
        ]
    return []


def _check_encryption_in_transit(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """All components must use TLS (encryption in transit)."""
    if not component.security.encryption_in_transit:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' does not use encryption in transit (TLS)",
                remediation="Enable TLS/SSL for all network communications.",
            )
        ]
    return []


def _check_autoscaling_enabled(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """Autoscaling for web/app servers."""
    scalable_types = {ComponentType.WEB_SERVER, ComponentType.APP_SERVER}
    if component.type in scalable_types and not component.autoscaling.enabled:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' (type={component.type.value}) "
                "does not have autoscaling enabled",
                remediation="Enable autoscaling (HPA/KEDA) with appropriate thresholds.",
            )
        ]
    return []


def _check_max_utilization(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """No component above 80% utilization."""
    util = component.utilization()
    if util > 80.0:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' utilization is {util:.1f}% (threshold: 80%)",
                remediation="Scale up or enable autoscaling to reduce utilization below 80%.",
            )
        ]
    return []


def _check_monitoring_enabled(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """All components must have logging enabled."""
    if not component.security.log_enabled:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' does not have logging/monitoring enabled",
                remediation="Enable logging and monitoring (e.g., Prometheus, CloudWatch).",
            )
        ]
    return []


def _check_backup_required(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """Databases and storage must have backups enabled."""
    backup_types = {ComponentType.DATABASE, ComponentType.STORAGE}
    if component.type in backup_types and not component.security.backup_enabled:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' does not have backups enabled",
                remediation="Enable automated backups with appropriate frequency and retention.",
            )
        ]
    return []


def _check_network_segmented(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """All components must be network segmented."""
    if not component.security.network_segmented:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' is not in a segmented network",
                remediation="Place the component in an appropriate VPC/subnet with security groups.",
            )
        ]
    return []


def _check_auth_required(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """All external-facing components need authentication."""
    external_types = {
        ComponentType.LOAD_BALANCER,
        ComponentType.WEB_SERVER,
        ComponentType.EXTERNAL_API,
    }
    if component.type in external_types and not component.security.auth_required:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"External-facing component '{component.name}' does not require authentication",
                remediation="Enable authentication (OAuth2, API keys, mTLS) for external endpoints.",
            )
        ]
    return []


def _check_max_dependency_depth(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """Dependency chain depth should not exceed 5.

    This is a graph-level check evaluated once per rule, but we anchor
    violations to the deepest component in each over-long path.
    """
    # Only check once (anchor on the first component alphabetically to avoid dupes)
    all_ids = sorted(graph.components.keys())
    if not all_ids or component.id != all_ids[0]:
        return []

    violations: list[PolicyViolation] = []
    critical_paths = graph.get_critical_paths()
    for path in critical_paths:
        if len(path) > 5:
            deepest_id = path[-1]
            deepest = graph.get_component(deepest_id)
            if deepest is None:
                continue
            violations.append(
                PolicyViolation(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    component_id=deepest.id,
                    component_name=deepest.name,
                    message=f"Dependency chain depth is {len(path)} (max allowed: 5). "
                    f"Path: {' -> '.join(path)}",
                    remediation="Reduce dependency chain depth by consolidating services or introducing caching layers.",
                )
            )
    return violations


def _check_circuit_breaker(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """External API dependencies should have circuit breakers."""
    violations: list[PolicyViolation] = []
    deps = graph.get_dependencies(component.id)
    for dep_comp in deps:
        if dep_comp.type == ComponentType.EXTERNAL_API:
            edge = graph.get_dependency_edge(component.id, dep_comp.id)
            if edge and not edge.circuit_breaker.enabled:
                violations.append(
                    PolicyViolation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        component_id=component.id,
                        component_name=component.name,
                        message=f"Component '{component.name}' depends on external API "
                        f"'{dep_comp.name}' without a circuit breaker",
                        remediation="Enable circuit breaker on the dependency edge to the external API.",
                    )
                )
    return violations


def _check_rate_limiting(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """API gateways and external endpoints need rate limiting."""
    rate_limit_types = {
        ComponentType.LOAD_BALANCER,
        ComponentType.EXTERNAL_API,
    }
    if component.type in rate_limit_types and not component.security.rate_limiting:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' (type={component.type.value}) "
                "does not have rate limiting enabled",
                remediation="Enable rate limiting to protect against abuse and DoS attacks.",
            )
        ]
    return []


def _check_change_management(
    graph: InfraGraph, component: Any, rule: PolicyRule
) -> list[PolicyViolation]:
    """All production components need change management."""
    if not component.compliance_tags.change_management:
        return [
            PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                component_id=component.id,
                component_name=component.name,
                message=f"Component '{component.name}' does not have change management enabled",
                remediation="Enable change management process (approval workflows, audit trails).",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Condition -> checker mapping
# ---------------------------------------------------------------------------

_CONDITION_CHECKERS: dict[str, _CheckerFn] = {
    "component.replicas > 1 for components with dependents": _check_no_spof,
    "component.replicas >= 2 for databases": _check_min_replicas,
    "component.failover.enabled == True for critical services": _check_failover_required,
    "component.security.encryption_at_rest == True for storage": _check_encryption_at_rest,
    "component.security.encryption_in_transit == True": _check_encryption_in_transit,
    "component.autoscaling.enabled == True for web/app servers": _check_autoscaling_enabled,
    "component.utilization() <= 80": _check_max_utilization,
    "component.security.log_enabled == True": _check_monitoring_enabled,
    "component.security.backup_enabled == True for storage": _check_backup_required,
    "component.security.network_segmented == True": _check_network_segmented,
    "component.security.auth_required == True for external": _check_auth_required,
    "dependency_depth <= 5": _check_max_dependency_depth,
    "circuit_breaker.enabled for external_api deps": _check_circuit_breaker,
    "component.security.rate_limiting == True for gateways": _check_rate_limiting,
    "component.compliance_tags.change_management == True": _check_change_management,
}


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------


def _builtin_rules() -> list[PolicyRule]:
    """Return the 15 built-in policy rules."""
    return [
        PolicyRule(
            id="no-spof",
            name="No Single Points of Failure",
            description="Components with dependents must have more than 1 replica.",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.RESILIENCE,
            condition="component.replicas > 1 for components with dependents",
            message_template="{component} is a single point of failure",
            tags=["resilience", "availability"],
        ),
        PolicyRule(
            id="min-replicas",
            name="Minimum Database Replicas",
            description="Databases must have at least 2 replicas for high availability.",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.RESILIENCE,
            condition="component.replicas >= 2 for databases",
            message_template="{component} has insufficient replicas",
            tags=["resilience", "database"],
        ),
        PolicyRule(
            id="failover-required",
            name="Failover Required",
            description="Databases and critical services must have failover enabled.",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.RESILIENCE,
            condition="component.failover.enabled == True for critical services",
            message_template="{component} does not have failover enabled",
            tags=["resilience", "failover"],
        ),
        PolicyRule(
            id="encryption-at-rest",
            name="Encryption at Rest",
            description="All databases and storage must have encryption at rest.",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.SECURITY,
            condition="component.security.encryption_at_rest == True for storage",
            message_template="{component} lacks encryption at rest",
            tags=["security", "encryption"],
        ),
        PolicyRule(
            id="encryption-in-transit",
            name="Encryption in Transit",
            description="All components must use TLS for network communications.",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.SECURITY,
            condition="component.security.encryption_in_transit == True",
            message_template="{component} lacks encryption in transit",
            tags=["security", "encryption", "tls"],
        ),
        PolicyRule(
            id="autoscaling-enabled",
            name="Autoscaling Enabled",
            description="Web and application servers should have autoscaling enabled.",
            severity=PolicySeverity.WARNING,
            category=PolicyCategory.PERFORMANCE,
            condition="component.autoscaling.enabled == True for web/app servers",
            message_template="{component} does not have autoscaling enabled",
            tags=["performance", "autoscaling"],
        ),
        PolicyRule(
            id="max-utilization",
            name="Maximum Utilization",
            description="No component should exceed 80% utilization.",
            severity=PolicySeverity.WARNING,
            category=PolicyCategory.PERFORMANCE,
            condition="component.utilization() <= 80",
            message_template="{component} utilization exceeds 80%",
            tags=["performance", "capacity"],
        ),
        PolicyRule(
            id="monitoring-enabled",
            name="Monitoring Enabled",
            description="All components must have logging and monitoring enabled.",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.OPERATIONAL,
            condition="component.security.log_enabled == True",
            message_template="{component} does not have monitoring enabled",
            tags=["operational", "monitoring", "logging"],
        ),
        PolicyRule(
            id="backup-required",
            name="Backup Required",
            description="Databases and storage must have automated backups.",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.RESILIENCE,
            condition="component.security.backup_enabled == True for storage",
            message_template="{component} does not have backups enabled",
            tags=["resilience", "backup", "data-protection"],
        ),
        PolicyRule(
            id="network-segmented",
            name="Network Segmentation",
            description="All components must be deployed in segmented networks.",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.SECURITY,
            condition="component.security.network_segmented == True",
            message_template="{component} is not network segmented",
            tags=["security", "network"],
        ),
        PolicyRule(
            id="auth-required",
            name="Authentication Required",
            description="All external-facing components must require authentication.",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.SECURITY,
            condition="component.security.auth_required == True for external",
            message_template="{component} does not require authentication",
            tags=["security", "authentication"],
        ),
        PolicyRule(
            id="max-dependency-depth",
            name="Maximum Dependency Depth",
            description="Dependency chain depth should not exceed 5 levels.",
            severity=PolicySeverity.WARNING,
            category=PolicyCategory.RESILIENCE,
            condition="dependency_depth <= 5",
            message_template="Dependency chain exceeds maximum depth of 5",
            tags=["resilience", "architecture"],
        ),
        PolicyRule(
            id="circuit-breaker",
            name="Circuit Breaker Required",
            description="External API dependencies should have circuit breakers.",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.RESILIENCE,
            condition="circuit_breaker.enabled for external_api deps",
            message_template="{component} lacks circuit breaker for external dependency",
            tags=["resilience", "circuit-breaker"],
        ),
        PolicyRule(
            id="rate-limiting",
            name="Rate Limiting Required",
            description="API gateways and external endpoints need rate limiting.",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.SECURITY,
            condition="component.security.rate_limiting == True for gateways",
            message_template="{component} does not have rate limiting",
            tags=["security", "rate-limiting"],
        ),
        PolicyRule(
            id="change-management",
            name="Change Management Required",
            description="All production components need change management processes.",
            severity=PolicySeverity.WARNING,
            category=PolicyCategory.COMPLIANCE,
            condition="component.compliance_tags.change_management == True",
            message_template="{component} lacks change management process",
            tags=["compliance", "change-management"],
        ),
    ]


# ---------------------------------------------------------------------------
# PolicyEngine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """Evaluate infrastructure policy rules against an ``InfraGraph``.

    The engine ships with 15 built-in rules covering resilience, security,
    performance, operational, and compliance categories.  Users can also
    create custom rules, load/export policy sets, and merge multiple sets.
    """

    def __init__(self) -> None:
        self._checkers: dict[str, _CheckerFn] = dict(_CONDITION_CHECKERS)
        self._builtin_policy_set = PolicySet(
            name="builtin",
            description="Built-in infrastructure resilience policy set",
            version="1.0.0",
            rules=_builtin_rules(),
        )

    # -- public API --------------------------------------------------------

    def evaluate(
        self,
        graph: InfraGraph,
        policy_set: PolicySet | None = None,
    ) -> PolicyReport:
        """Evaluate all rules in *policy_set* against *graph*.

        If *policy_set* is ``None``, the built-in policy set is used.
        """
        pset = policy_set or self._builtin_policy_set
        results: list[PolicyResult] = []
        for rule in pset.rules:
            if rule.enabled:
                results.append(self.evaluate_rule(graph, rule))

        total_rules = len(results)
        passed_rules = sum(1 for r in results if r.passed)
        failed_rules = total_rules - passed_rules

        # Aggregate violations by severity
        violations_by_severity: dict[str, int] = {}
        for r in results:
            for v in r.violations:
                sev = v.severity.value
                violations_by_severity[sev] = violations_by_severity.get(sev, 0) + 1

        overall_pass = failed_rules == 0
        score = (passed_rules / total_rules * 100.0) if total_rules > 0 else 100.0

        return PolicyReport(
            results=results,
            total_rules=total_rules,
            passed_rules=passed_rules,
            failed_rules=failed_rules,
            violations_by_severity=violations_by_severity,
            overall_pass=overall_pass,
            score=round(score, 2),
        )

    def evaluate_rule(
        self,
        graph: InfraGraph,
        rule: PolicyRule,
    ) -> PolicyResult:
        """Evaluate a single *rule* against every component in *graph*."""
        checker = self._checkers.get(rule.condition)
        if checker is None:
            # Unknown condition -- treat as pass with 0 components checked
            return PolicyResult(
                rule=rule,
                passed=True,
                violations=[],
                components_checked=0,
            )

        violations: list[PolicyViolation] = []
        components = list(graph.components.values())
        for comp in components:
            violations.extend(checker(graph, comp, rule))

        return PolicyResult(
            rule=rule,
            passed=len(violations) == 0,
            violations=violations,
            components_checked=len(components),
        )

    def load_policy_set(self, data: dict) -> PolicySet:
        """Deserialise a ``PolicySet`` from a plain dict (JSON/YAML compatible)."""
        rules: list[PolicyRule] = []
        for rd in data.get("rules", []):
            rules.append(
                PolicyRule(
                    id=rd["id"],
                    name=rd["name"],
                    description=rd.get("description", ""),
                    severity=PolicySeverity(rd["severity"]),
                    category=PolicyCategory(rd["category"]),
                    condition=rd["condition"],
                    message_template=rd.get("message_template", ""),
                    enabled=rd.get("enabled", True),
                    tags=rd.get("tags", []),
                )
            )
        return PolicySet(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            version=data.get("version", "0.0.0"),
            rules=rules,
        )

    def export_policy_set(self, policy_set: PolicySet) -> dict:
        """Serialise a ``PolicySet`` to a plain dict (JSON/YAML compatible)."""
        return {
            "name": policy_set.name,
            "description": policy_set.description,
            "version": policy_set.version,
            "rules": [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "severity": r.severity.value,
                    "category": r.category.value,
                    "condition": r.condition,
                    "message_template": r.message_template,
                    "enabled": r.enabled,
                    "tags": list(r.tags),
                }
                for r in policy_set.rules
            ],
        }

    def get_builtin_policies(self) -> PolicySet:
        """Return the built-in policy set."""
        return self._builtin_policy_set

    def create_custom_rule(
        self,
        id: str,
        name: str,
        description: str,
        condition: str,
        severity: PolicySeverity | str,
        category: PolicyCategory | str,
        message_template: str = "",
        enabled: bool = True,
        tags: list[str] | None = None,
    ) -> PolicyRule:
        """Create a custom ``PolicyRule``.

        *severity* and *category* may be passed as enum members or strings.
        """
        if isinstance(severity, str):
            severity = PolicySeverity(severity)
        if isinstance(category, str):
            category = PolicyCategory(category)
        return PolicyRule(
            id=id,
            name=name,
            description=description,
            severity=severity,
            category=category,
            condition=condition,
            message_template=message_template,
            enabled=enabled,
            tags=tags or [],
        )

    def merge_policy_sets(self, sets: list[PolicySet]) -> PolicySet:
        """Merge multiple ``PolicySet`` instances into one.

        Rules are deduplicated by ``id``; later sets take precedence.
        The merged set's name and description are derived from the inputs.
        """
        if not sets:
            return PolicySet(
                name="empty",
                description="Empty merged policy set",
                version="0.0.0",
                rules=[],
            )

        seen_ids: dict[str, PolicyRule] = {}
        for pset in sets:
            for rule in pset.rules:
                seen_ids[rule.id] = rule

        names = [s.name for s in sets]
        versions = [s.version for s in sets]

        return PolicySet(
            name=" + ".join(names),
            description=f"Merged policy set from: {', '.join(names)}",
            version=max(versions),
            rules=list(seen_ids.values()),
        )

    # -- checker registration (advanced) -----------------------------------

    def register_checker(self, condition: str, fn: _CheckerFn) -> None:
        """Register a custom checker function for a condition string."""
        self._checkers[condition] = fn
