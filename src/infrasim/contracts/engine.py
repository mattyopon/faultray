"""Resilience Contracts - Define resilience requirements as code.

Resilience Contracts are machine-readable definitions of what resilience
properties an infrastructure MUST have. They're like SLOs, but specifically
for infrastructure resilience.

Example contract:
  min_resilience_score: 75
  max_spof_count: 0
  min_replicas:
    database: 2
    server: 3
  required_patterns:
    - circuit_breaker
    - autoscaling
  max_blast_radius: 0.3
  sla_target: 99.95

When violations are detected, contracts can:
- Block CI/CD pipelines
- Send alerts
- Generate compliance evidence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from infrasim.model.components import ComponentType
from infrasim.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

VALID_RULE_TYPES = {
    "min_score",
    "max_spof",
    "min_replicas",
    "required_pattern",
    "max_blast_radius",
    "sla_target",
    "max_critical_findings",
    "required_failover",
    "required_health_check",
    "max_dependency_depth",
}

VALID_OPERATORS = {">=", "<=", "==", "!=", ">", "<"}
VALID_SEVERITIES = {"error", "warning", "info"}


@dataclass
class ContractRule:
    """A single resilience contract rule."""

    rule_type: str  # min_score, max_spof, min_replicas, ...
    target: str | None  # component ID or type (e.g. "database"), or None / "*"
    operator: str  # >=, <=, ==, !=, >, <
    value: Any  # threshold value
    description: str
    severity: str = "error"  # error, warning, info

    def __post_init__(self) -> None:
        if self.rule_type not in VALID_RULE_TYPES:
            raise ValueError(
                f"Unknown rule_type '{self.rule_type}'. "
                f"Valid types: {sorted(VALID_RULE_TYPES)}"
            )
        if self.operator not in VALID_OPERATORS:
            raise ValueError(
                f"Unknown operator '{self.operator}'. "
                f"Valid operators: {sorted(VALID_OPERATORS)}"
            )
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Unknown severity '{self.severity}'. "
                f"Valid severities: {sorted(VALID_SEVERITIES)}"
            )


@dataclass
class ContractViolation:
    """A single violation detected during contract validation."""

    rule: ContractRule
    actual_value: Any
    message: str
    component_id: str | None = None
    severity: str = "error"


@dataclass
class ResilienceContract:
    """A collection of resilience rules representing the contract."""

    name: str
    version: str
    description: str
    rules: list[ContractRule]
    metadata: dict = field(default_factory=dict)


@dataclass
class ContractValidationResult:
    """Result of validating a contract against an InfraGraph."""

    contract: ResilienceContract
    passed: bool
    violations: list[ContractViolation]
    warnings: list[ContractViolation]
    score: float  # compliance percentage (0-100)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON output."""
        return {
            "contract_name": self.contract.name,
            "contract_version": self.contract.version,
            "passed": self.passed,
            "compliance_score": round(self.score, 1),
            "error_count": len(self.violations),
            "warning_count": len(self.warnings),
            "violations": [
                {
                    "rule_type": v.rule.rule_type,
                    "severity": v.severity,
                    "expected": v.rule.value,
                    "actual": v.actual_value,
                    "message": v.message,
                    "component_id": v.component_id,
                }
                for v in self.violations
            ],
            "warnings": [
                {
                    "rule_type": w.rule.rule_type,
                    "severity": w.severity,
                    "expected": w.rule.value,
                    "actual": w.actual_value,
                    "message": w.message,
                    "component_id": w.component_id,
                }
                for w in self.warnings
            ],
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Operator helper
# ---------------------------------------------------------------------------

def _compare(actual: float, operator: str, expected: float) -> bool:
    """Evaluate ``actual <op> expected``."""
    if operator == ">=":
        return actual >= expected
    elif operator == "<=":
        return actual <= expected
    elif operator == "==":
        return actual == expected
    elif operator == "!=":
        return actual != expected
    elif operator == ">":
        return actual > expected
    elif operator == "<":
        return actual < expected
    return False


# ---------------------------------------------------------------------------
# Default operator per rule type
# ---------------------------------------------------------------------------

_DEFAULT_OPERATOR: dict[str, str] = {
    "min_score": ">=",
    "max_spof": "<=",
    "min_replicas": ">=",
    "required_pattern": ">=",  # coverage >= 1 (i.e. present)
    "max_blast_radius": "<=",
    "sla_target": ">=",
    "max_critical_findings": "<=",
    "required_failover": ">=",
    "required_health_check": ">=",
    "max_dependency_depth": "<=",
}


# ---------------------------------------------------------------------------
# Contract Engine
# ---------------------------------------------------------------------------

class ContractEngine:
    """Loads, validates, generates, saves and diffs resilience contracts."""

    # ---- Load / Save -------------------------------------------------------

    def load_contract(self, path: Path) -> ResilienceContract:
        """Load a resilience contract from a YAML file.

        Expected YAML format::

            name: "My Contract"
            version: "1.0"
            description: "Minimum resilience requirements"
            metadata:
              author: "SRE Team"
            rules:
              - type: min_score
                value: 75
                severity: error
                description: "Resilience score >= 75"
        """
        if not path.exists():
            raise FileNotFoundError(f"Contract file not found: {path}")

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(
                f"Expected YAML mapping at top level, got {type(raw).__name__}"
            )

        return self._parse_contract(raw)

    def _parse_contract(self, raw: dict) -> ResilienceContract:
        """Parse a contract from a raw dict (deserialized YAML)."""
        name = raw.get("name", "Unnamed Contract")
        version = str(raw.get("version", "1.0"))
        description = raw.get("description", "")
        metadata = raw.get("metadata", {})

        raw_rules = raw.get("rules", [])
        if not isinstance(raw_rules, list):
            raise ValueError("'rules' must be a list")

        rules: list[ContractRule] = []
        for idx, entry in enumerate(raw_rules):
            if not isinstance(entry, dict):
                raise ValueError(f"Rule entry {idx} must be a mapping")

            rule_type = entry.get("type", "")
            if not rule_type:
                raise ValueError(f"Rule entry {idx} is missing 'type'")

            # Infer default operator from rule type if not specified
            default_op = _DEFAULT_OPERATOR.get(rule_type, ">=")
            operator = entry.get("operator", default_op)

            rules.append(ContractRule(
                rule_type=rule_type,
                target=entry.get("target"),
                operator=operator,
                value=entry.get("value"),
                description=entry.get("description", f"Rule {idx}: {rule_type}"),
                severity=entry.get("severity", "error"),
            ))

        return ResilienceContract(
            name=name,
            version=version,
            description=description,
            rules=rules,
            metadata=metadata,
        )

    def save_contract(self, contract: ResilienceContract, path: Path) -> None:
        """Serialize a contract to YAML and write to *path*."""
        data: dict[str, Any] = {
            "name": contract.name,
            "version": contract.version,
            "description": contract.description,
        }
        if contract.metadata:
            data["metadata"] = contract.metadata

        data["rules"] = []
        for rule in contract.rules:
            rule_dict: dict[str, Any] = {
                "type": rule.rule_type,
                "value": rule.value,
                "severity": rule.severity,
                "description": rule.description,
            }
            if rule.target:
                rule_dict["target"] = rule.target
            if rule.operator != _DEFAULT_OPERATOR.get(rule.rule_type, ">="):
                rule_dict["operator"] = rule.operator
            data["rules"].append(rule_dict)

        path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    # ---- Validate ----------------------------------------------------------

    def validate(
        self,
        graph: InfraGraph,
        contract: ResilienceContract,
    ) -> ContractValidationResult:
        """Validate an InfraGraph against a ResilienceContract.

        Returns a :class:`ContractValidationResult` with all violations.
        """
        violations: list[ContractViolation] = []
        warnings: list[ContractViolation] = []

        for rule in contract.rules:
            rule_violations = self._check_rule(graph, rule)
            for v in rule_violations:
                if v.severity == "error":
                    violations.append(v)
                else:
                    warnings.append(v)

        total_rules = len(contract.rules)
        error_rules = len({id(v.rule) for v in violations})
        if total_rules > 0:
            compliance = ((total_rules - error_rules) / total_rules) * 100.0
        else:
            compliance = 100.0

        passed = len(violations) == 0

        return ContractValidationResult(
            contract=contract,
            passed=passed,
            violations=violations,
            warnings=warnings,
            score=compliance,
        )

    def _check_rule(
        self,
        graph: InfraGraph,
        rule: ContractRule,
    ) -> list[ContractViolation]:
        """Dispatch rule validation to the appropriate checker."""
        handler = _RULE_HANDLERS.get(rule.rule_type)
        if handler is None:
            logger.warning("No handler for rule type '%s'", rule.rule_type)
            return []
        return handler(graph, rule)

    # ---- Generate default contract -----------------------------------------

    def generate_default_contract(
        self,
        graph: InfraGraph,
        strictness: str = "standard",
    ) -> ResilienceContract:
        """Auto-generate a resilience contract based on the current graph state.

        *strictness* can be ``"relaxed"``, ``"standard"``, or ``"strict"``.
        """
        rules: list[ContractRule] = []

        # Resilience score threshold
        current_score = graph.resilience_score()
        score_thresholds = {
            "relaxed": max(0, current_score - 10),
            "standard": max(0, current_score - 5),
            "strict": max(0, current_score),
        }
        min_score = score_thresholds.get(strictness, score_thresholds["standard"])
        rules.append(ContractRule(
            rule_type="min_score",
            target=None,
            operator=">=",
            value=round(min_score, 1),
            description=f"Resilience score must be at least {round(min_score, 1)}",
            severity="error",
        ))

        # SPOF count
        spof_count = _count_spofs(graph)
        max_spof_values = {
            "relaxed": max(spof_count, 2),
            "standard": max(spof_count, 0),
            "strict": 0,
        }
        max_spof = max_spof_values.get(strictness, 0)
        rules.append(ContractRule(
            rule_type="max_spof",
            target=None,
            operator="<=",
            value=max_spof,
            description=f"No more than {max_spof} single points of failure",
            severity="error" if strictness == "strict" else "warning",
        ))

        # Min replicas per type — databases always need redundancy
        db_comps = [
            c for c in graph.components.values()
            if c.type == ComponentType.DATABASE
        ]
        if db_comps:
            min_db = {"relaxed": 1, "standard": 2, "strict": 2}
            rules.append(ContractRule(
                rule_type="min_replicas",
                target="database",
                operator=">=",
                value=min_db.get(strictness, 2),
                description="Databases must have redundancy",
                severity="error",
            ))

        server_comps = [
            c for c in graph.components.values()
            if c.type in (ComponentType.APP_SERVER, ComponentType.WEB_SERVER)
        ]
        if server_comps:
            min_srv = {"relaxed": 1, "standard": 2, "strict": 3}
            rules.append(ContractRule(
                rule_type="min_replicas",
                target="app_server",
                operator=">=",
                value=min_srv.get(strictness, 2),
                description="Application servers should be replicated",
                severity="warning",
            ))

        # Max blast radius
        blast_values = {"relaxed": 0.5, "standard": 0.3, "strict": 0.2}
        rules.append(ContractRule(
            rule_type="max_blast_radius",
            target=None,
            operator="<=",
            value=blast_values.get(strictness, 0.3),
            description="No single failure should affect too many components",
            severity="error",
        ))

        # Max dependency depth
        depth_values = {"relaxed": 6, "standard": 4, "strict": 3}
        rules.append(ContractRule(
            rule_type="max_dependency_depth",
            target=None,
            operator="<=",
            value=depth_values.get(strictness, 4),
            description="Dependency chains should not be too deep",
            severity="warning",
        ))

        # Required patterns (strict only)
        if strictness == "strict":
            rules.append(ContractRule(
                rule_type="required_pattern",
                target="*",
                operator=">=",
                value="circuit_breaker",
                description="All dependency edges should have circuit breakers",
                severity="warning",
            ))
            rules.append(ContractRule(
                rule_type="required_pattern",
                target="*",
                operator=">=",
                value="autoscaling",
                description="All components should have autoscaling enabled",
                severity="warning",
            ))

        return ResilienceContract(
            name="Auto-Generated Resilience Contract",
            version="1.0",
            description=f"Generated with strictness={strictness} based on current infrastructure state",
            rules=rules,
            metadata={
                "generated": True,
                "strictness": strictness,
                "generated_at": datetime.utcnow().isoformat(),
            },
        )

    # ---- Diff contracts ----------------------------------------------------

    def diff_contracts(
        self,
        old: ResilienceContract,
        new: ResilienceContract,
    ) -> list[str]:
        """Compare two contracts and return a list of human-readable changes."""
        changes: list[str] = []

        if old.name != new.name:
            changes.append(f"Name changed: '{old.name}' -> '{new.name}'")
        if old.version != new.version:
            changes.append(f"Version changed: '{old.version}' -> '{new.version}'")

        old_rules = {self._rule_key(r): r for r in old.rules}
        new_rules = {self._rule_key(r): r for r in new.rules}

        # Rules added
        for key in new_rules:
            if key not in old_rules:
                r = new_rules[key]
                changes.append(
                    f"+ Added rule: {r.rule_type}"
                    f" (target={r.target}, value={r.value}, severity={r.severity})"
                )

        # Rules removed
        for key in old_rules:
            if key not in new_rules:
                r = old_rules[key]
                changes.append(
                    f"- Removed rule: {r.rule_type}"
                    f" (target={r.target}, value={r.value}, severity={r.severity})"
                )

        # Rules modified
        for key in old_rules:
            if key in new_rules:
                o = old_rules[key]
                n = new_rules[key]
                if o.value != n.value:
                    changes.append(
                        f"~ Rule {o.rule_type} (target={o.target}): "
                        f"value {o.value} -> {n.value}"
                    )
                if o.severity != n.severity:
                    changes.append(
                        f"~ Rule {o.rule_type} (target={o.target}): "
                        f"severity {o.severity} -> {n.severity}"
                    )
                if o.operator != n.operator:
                    changes.append(
                        f"~ Rule {o.rule_type} (target={o.target}): "
                        f"operator {o.operator} -> {n.operator}"
                    )

        if not changes:
            changes.append("No differences found.")

        return changes

    @staticmethod
    def _rule_key(rule: ContractRule) -> str:
        """Create a stable key for matching rules across contracts."""
        return f"{rule.rule_type}::{rule.target or '*'}"


# ---------------------------------------------------------------------------
# Rule validation handlers
# ---------------------------------------------------------------------------

def _count_spofs(graph: InfraGraph) -> int:
    """Count components that are single points of failure."""
    count = 0
    for comp in graph.components.values():
        dependents = graph.get_dependents(comp.id)
        if comp.replicas <= 1 and len(dependents) > 0 and not comp.failover.enabled:
            count += 1
    return count


def _check_min_score(graph: InfraGraph, rule: ContractRule) -> list[ContractViolation]:
    """Check minimum resilience score."""
    actual = graph.resilience_score()
    expected = float(rule.value)
    if not _compare(actual, rule.operator, expected):
        return [ContractViolation(
            rule=rule,
            actual_value=round(actual, 1),
            message=f"Resilience score is {actual:.1f}, expected {rule.operator} {expected}",
            severity=rule.severity,
        )]
    return []


def _check_max_spof(graph: InfraGraph, rule: ContractRule) -> list[ContractViolation]:
    """Check maximum single-point-of-failure count."""
    actual = _count_spofs(graph)
    expected = int(rule.value)
    if not _compare(actual, rule.operator, expected):
        return [ContractViolation(
            rule=rule,
            actual_value=actual,
            message=f"Found {actual} SPOF(s), expected {rule.operator} {expected}",
            severity=rule.severity,
        )]
    return []


def _check_min_replicas(graph: InfraGraph, rule: ContractRule) -> list[ContractViolation]:
    """Check minimum replica count for components of a given type."""
    violations: list[ContractViolation] = []
    target = rule.target or "*"
    expected = int(rule.value)

    for comp in graph.components.values():
        # Match by type name or wildcard
        if target != "*":
            try:
                target_type = ComponentType(target)
            except ValueError:
                # Try matching as a prefix (e.g. "server" matches "app_server", "web_server")
                target_lower = target.lower()
                if target_lower not in comp.type.value.lower():
                    continue
            else:
                if comp.type != target_type:
                    continue

        if not _compare(comp.replicas, rule.operator, expected):
            violations.append(ContractViolation(
                rule=rule,
                actual_value=comp.replicas,
                message=(
                    f"Component '{comp.id}' ({comp.type.value}) has {comp.replicas} replica(s), "
                    f"expected {rule.operator} {expected}"
                ),
                component_id=comp.id,
                severity=rule.severity,
            ))

    return violations


def _check_required_pattern(graph: InfraGraph, rule: ContractRule) -> list[ContractViolation]:
    """Check that a required resilience pattern is present."""
    violations: list[ContractViolation] = []
    pattern = str(rule.value).lower()

    if pattern == "circuit_breaker":
        edges = graph.all_dependency_edges()
        if edges:
            missing = [e for e in edges if not e.circuit_breaker.enabled]
            if missing:
                violations.append(ContractViolation(
                    rule=rule,
                    actual_value=f"{len(edges) - len(missing)}/{len(edges)} edges covered",
                    message=(
                        f"{len(missing)} of {len(edges)} dependency edges "
                        f"lack circuit breakers"
                    ),
                    severity=rule.severity,
                ))

    elif pattern == "autoscaling":
        comps = list(graph.components.values())
        missing = [c for c in comps if not c.autoscaling.enabled]
        if missing:
            violations.append(ContractViolation(
                rule=rule,
                actual_value=f"{len(comps) - len(missing)}/{len(comps)} components covered",
                message=(
                    f"{len(missing)} of {len(comps)} components "
                    f"lack autoscaling"
                ),
                severity=rule.severity,
            ))

    elif pattern == "failover":
        comps = list(graph.components.values())
        missing = [c for c in comps if not c.failover.enabled]
        if missing:
            violations.append(ContractViolation(
                rule=rule,
                actual_value=f"{len(comps) - len(missing)}/{len(comps)} components covered",
                message=(
                    f"{len(missing)} of {len(comps)} components "
                    f"lack failover"
                ),
                severity=rule.severity,
            ))

    elif pattern == "retry":
        edges = graph.all_dependency_edges()
        if edges:
            missing = [e for e in edges if not e.retry_strategy.enabled]
            if missing:
                violations.append(ContractViolation(
                    rule=rule,
                    actual_value=f"{len(edges) - len(missing)}/{len(edges)} edges covered",
                    message=(
                        f"{len(missing)} of {len(edges)} dependency edges "
                        f"lack retry strategies"
                    ),
                    severity=rule.severity,
                ))

    else:
        logger.warning("Unknown required pattern: '%s'", pattern)

    return violations


def _check_max_blast_radius(
    graph: InfraGraph, rule: ContractRule,
) -> list[ContractViolation]:
    """Check that no single component failure affects more than X% of components."""
    violations: list[ContractViolation] = []
    total = len(graph.components)
    if total == 0:
        return violations

    threshold = float(rule.value)

    for comp in graph.components.values():
        affected = graph.get_all_affected(comp.id)
        blast_ratio = len(affected) / total
        if not _compare(blast_ratio, rule.operator, threshold):
            violations.append(ContractViolation(
                rule=rule,
                actual_value=round(blast_ratio, 3),
                message=(
                    f"Failure of '{comp.id}' affects {len(affected)}/{total} components "
                    f"({blast_ratio:.1%}), threshold {rule.operator} {threshold:.1%}"
                ),
                component_id=comp.id,
                severity=rule.severity,
            ))

    return violations


def _check_sla_target(graph: InfraGraph, rule: ContractRule) -> list[ContractViolation]:
    """Check SLA target achievability using the resilience score as a proxy.

    A resilience score of 100 maps roughly to 99.999% SLA; lower scores
    proportionally reduce achievable SLA.
    """
    target_sla = float(rule.value)  # e.g. 99.95
    score = graph.resilience_score()

    # Map score 0-100 -> SLA 99.0 - 99.999
    estimated_sla = 99.0 + (score / 100.0) * 0.999
    estimated_sla = min(estimated_sla, 99.999)

    if not _compare(estimated_sla, rule.operator, target_sla):
        return [ContractViolation(
            rule=rule,
            actual_value=round(estimated_sla, 3),
            message=(
                f"Estimated achievable SLA is {estimated_sla:.3f}%, "
                f"target is {rule.operator} {target_sla}%"
            ),
            severity=rule.severity,
        )]
    return []


def _check_max_critical_findings(
    graph: InfraGraph, rule: ContractRule,
) -> list[ContractViolation]:
    """Check max critical findings (SPOFs + high blast radius components)."""
    # Count critical findings: SPOFs
    spof_count = _count_spofs(graph)

    # Count components with blast radius > 50%
    total = len(graph.components)
    high_blast = 0
    if total > 0:
        for comp in graph.components.values():
            affected = graph.get_all_affected(comp.id)
            if len(affected) / total > 0.5:
                high_blast += 1

    critical_count = spof_count + high_blast
    expected = int(rule.value)

    if not _compare(critical_count, rule.operator, expected):
        return [ContractViolation(
            rule=rule,
            actual_value=critical_count,
            message=(
                f"Found {critical_count} critical finding(s) "
                f"({spof_count} SPOFs + {high_blast} high-blast-radius), "
                f"expected {rule.operator} {expected}"
            ),
            severity=rule.severity,
        )]
    return []


def _check_required_failover(
    graph: InfraGraph, rule: ContractRule,
) -> list[ContractViolation]:
    """Check that target components have failover enabled."""
    violations: list[ContractViolation] = []
    target = rule.target or "*"

    for comp in graph.components.values():
        if target != "*":
            try:
                target_type = ComponentType(target)
            except ValueError:
                if target.lower() not in comp.type.value.lower():
                    continue
            else:
                if comp.type != target_type:
                    continue

        if not comp.failover.enabled:
            violations.append(ContractViolation(
                rule=rule,
                actual_value=False,
                message=f"Component '{comp.id}' ({comp.type.value}) has no failover",
                component_id=comp.id,
                severity=rule.severity,
            ))

    return violations


def _check_required_health_check(
    graph: InfraGraph, rule: ContractRule,
) -> list[ContractViolation]:
    """Check that target components have health check interval configured.

    A component "has health checks" if failover is enabled with a
    health_check_interval_seconds > 0.
    """
    violations: list[ContractViolation] = []
    target = rule.target or "*"

    for comp in graph.components.values():
        if target != "*":
            try:
                target_type = ComponentType(target)
            except ValueError:
                if target.lower() not in comp.type.value.lower():
                    continue
            else:
                if comp.type != target_type:
                    continue

        has_hc = (
            comp.failover.enabled
            and comp.failover.health_check_interval_seconds > 0
        )
        if not has_hc:
            violations.append(ContractViolation(
                rule=rule,
                actual_value=False,
                message=f"Component '{comp.id}' ({comp.type.value}) has no health check",
                component_id=comp.id,
                severity=rule.severity,
            ))

    return violations


def _check_max_dependency_depth(
    graph: InfraGraph, rule: ContractRule,
) -> list[ContractViolation]:
    """Check maximum dependency chain depth."""
    critical_paths = graph.get_critical_paths()
    if not critical_paths:
        return []

    actual_depth = len(critical_paths[0])
    expected = int(rule.value)

    if not _compare(actual_depth, rule.operator, expected):
        return [ContractViolation(
            rule=rule,
            actual_value=actual_depth,
            message=(
                f"Maximum dependency chain depth is {actual_depth}, "
                f"expected {rule.operator} {expected}"
            ),
            severity=rule.severity,
        )]
    return []


# Handler dispatch table
_RULE_HANDLERS = {
    "min_score": _check_min_score,
    "max_spof": _check_max_spof,
    "min_replicas": _check_min_replicas,
    "required_pattern": _check_required_pattern,
    "max_blast_radius": _check_max_blast_radius,
    "sla_target": _check_sla_target,
    "max_critical_findings": _check_max_critical_findings,
    "required_failover": _check_required_failover,
    "required_health_check": _check_required_health_check,
    "max_dependency_depth": _check_max_dependency_depth,
}
