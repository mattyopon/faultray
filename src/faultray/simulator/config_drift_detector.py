"""Configuration Drift Detector Engine.

Detects and analyses configuration drift across infrastructure components.
Supports multiple drift types (parameter, version, schema, secret-rotation),
baseline comparison, cross-environment consistency checks, severity scoring
based on parameter criticality, drift clustering, time-series tracking,
auto-remediation recommendations, configuration dependency graphs, drift
risk assessment, and compliance mapping.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from faultray.model.components import Component, Dependency
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DriftCategory(str, Enum):
    """High-level drift categories."""

    PARAMETER = "parameter"
    VERSION = "version"
    SCHEMA = "schema"
    SECRET_ROTATION = "secret_rotation"


class DriftSeverity(str, Enum):
    """Severity of a detected drift."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ComplianceFramework(str, Enum):
    """Compliance frameworks that may be violated by drift."""

    SOC2 = "soc2"
    PCI_DSS = "pci_dss"
    HIPAA = "hipaa"
    GDPR = "gdpr"
    ISO27001 = "iso27001"
    NIST = "nist"
    CIS = "cis"


class RemediationStrategy(str, Enum):
    """Recommended remediation strategies."""

    RESTORE_BASELINE = "restore_baseline"
    ACCEPT_CURRENT = "accept_current"
    ESCALATE = "escalate"
    AUTO_FIX = "auto_fix"
    MANUAL_REVIEW = "manual_review"
    ROTATE_SECRET = "rotate_secret"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DriftItem:
    """A single configuration drift finding."""

    component_id: str
    parameter_path: str
    category: DriftCategory
    severity: DriftSeverity
    baseline_value: Any
    current_value: Any
    description: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    criticality_weight: float = 1.0
    compliance_violations: list[ComplianceFramework] = field(default_factory=list)
    remediation: RemediationStrategy = RemediationStrategy.MANUAL_REVIEW
    remediation_detail: str = ""
    risk_score: float = 0.0


@dataclass
class DriftCluster:
    """A group of correlated drift items."""

    cluster_id: str
    component_ids: list[str] = field(default_factory=list)
    items: list[DriftItem] = field(default_factory=list)
    root_cause_hypothesis: str = ""
    aggregate_severity: DriftSeverity = DriftSeverity.INFO
    aggregate_risk: float = 0.0


@dataclass
class DriftTimeSeries:
    """Time-series tracking for drift velocity."""

    component_id: str
    parameter_path: str
    first_detected: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_detected: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    observation_count: int = 1
    drift_velocity: float = 0.0  # changes per day


@dataclass
class ConfigDependency:
    """Edge in the configuration dependency graph."""

    source_component_id: str
    source_parameter: str
    target_component_id: str
    target_parameter: str
    relationship: str = "depends_on"


@dataclass
class CrossEnvDrift:
    """Drift between two environments for the same component/parameter."""

    component_id: str
    parameter_path: str
    env_a_name: str
    env_a_value: Any
    env_b_name: str
    env_b_value: Any
    severity: DriftSeverity = DriftSeverity.MEDIUM
    acceptable: bool = False


@dataclass
class DriftRiskAssessment:
    """Impact assessment of unresolved drift on reliability."""

    component_id: str
    total_risk_score: float = 0.0
    reliability_impact: str = ""
    blast_radius: int = 0
    estimated_mttr_increase_minutes: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class BaselineSnapshot:
    """Golden configuration baseline for comparison."""

    snapshot_id: str
    timestamp: datetime
    component_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DriftReport:
    """Full drift analysis report."""

    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    total_drifts: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    items: list[DriftItem] = field(default_factory=list)
    clusters: list[DriftCluster] = field(default_factory=list)
    cross_env_drifts: list[CrossEnvDrift] = field(default_factory=list)
    risk_assessments: list[DriftRiskAssessment] = field(default_factory=list)
    compliance_summary: dict[str, int] = field(default_factory=dict)
    overall_risk_score: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "total_drifts": self.total_drifts,
            "severity_counts": {
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
                "info": self.info_count,
            },
            "overall_risk_score": round(self.overall_risk_score, 2),
            "compliance_summary": self.compliance_summary,
            "summary": self.summary,
            "items": [
                {
                    "component_id": it.component_id,
                    "parameter_path": it.parameter_path,
                    "category": it.category.value,
                    "severity": it.severity.value,
                    "baseline_value": _safe_serialize(it.baseline_value),
                    "current_value": _safe_serialize(it.current_value),
                    "description": it.description,
                    "risk_score": round(it.risk_score, 2),
                    "compliance_violations": [
                        c.value for c in it.compliance_violations
                    ],
                    "remediation": it.remediation.value,
                }
                for it in self.items
            ],
            "clusters": [
                {
                    "cluster_id": cl.cluster_id,
                    "component_ids": cl.component_ids,
                    "item_count": len(cl.items),
                    "aggregate_severity": cl.aggregate_severity.value,
                    "aggregate_risk": round(cl.aggregate_risk, 2),
                    "root_cause_hypothesis": cl.root_cause_hypothesis,
                }
                for cl in self.clusters
            ],
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Parameter criticality weights — higher means more severe if drifted
_CRITICALITY: dict[str, float] = {
    "replicas": 9.0,
    "failover.enabled": 10.0,
    "autoscaling.enabled": 8.0,
    "autoscaling.min_replicas": 6.0,
    "autoscaling.max_replicas": 6.0,
    "capacity.max_rps": 7.0,
    "capacity.max_connections": 6.0,
    "capacity.max_memory_mb": 5.0,
    "capacity.max_disk_gb": 4.0,
    "capacity.timeout_seconds": 5.0,
    "failover.promotion_time_seconds": 6.0,
    "failover.health_check_interval_seconds": 5.0,
    "health": 8.0,
    "security.encryption_at_rest": 7.0,
    "security.encryption_in_transit": 7.0,
    "security.auth_required": 8.0,
    "security.backup_enabled": 6.0,
    "security.rate_limiting": 5.0,
    "security.waf_protected": 5.0,
    "parameters": 3.0,
    "tags": 2.0,
}

# Which compliance frameworks care about which parameters
_COMPLIANCE_MAP: dict[str, list[ComplianceFramework]] = {
    "security.encryption_at_rest": [
        ComplianceFramework.PCI_DSS,
        ComplianceFramework.HIPAA,
        ComplianceFramework.SOC2,
        ComplianceFramework.ISO27001,
    ],
    "security.encryption_in_transit": [
        ComplianceFramework.PCI_DSS,
        ComplianceFramework.HIPAA,
        ComplianceFramework.SOC2,
        ComplianceFramework.ISO27001,
    ],
    "security.auth_required": [
        ComplianceFramework.SOC2,
        ComplianceFramework.PCI_DSS,
        ComplianceFramework.NIST,
    ],
    "security.backup_enabled": [
        ComplianceFramework.SOC2,
        ComplianceFramework.ISO27001,
    ],
    "security.rate_limiting": [
        ComplianceFramework.NIST,
        ComplianceFramework.CIS,
    ],
    "security.waf_protected": [
        ComplianceFramework.PCI_DSS,
        ComplianceFramework.NIST,
    ],
    "failover.enabled": [
        ComplianceFramework.SOC2,
        ComplianceFramework.ISO27001,
    ],
    "replicas": [
        ComplianceFramework.SOC2,
    ],
}

# Fields to extract from a Component for baseline / comparison
_EXTRACTORS: list[tuple[str, Any]] = [
    ("replicas", lambda c: c.replicas),
    ("capacity.max_rps", lambda c: c.capacity.max_rps),
    ("capacity.max_connections", lambda c: c.capacity.max_connections),
    ("capacity.max_memory_mb", lambda c: c.capacity.max_memory_mb),
    ("capacity.max_disk_gb", lambda c: c.capacity.max_disk_gb),
    ("capacity.timeout_seconds", lambda c: c.capacity.timeout_seconds),
    ("autoscaling.enabled", lambda c: c.autoscaling.enabled),
    ("autoscaling.min_replicas", lambda c: c.autoscaling.min_replicas),
    ("autoscaling.max_replicas", lambda c: c.autoscaling.max_replicas),
    ("failover.enabled", lambda c: c.failover.enabled),
    ("failover.promotion_time_seconds", lambda c: c.failover.promotion_time_seconds),
    (
        "failover.health_check_interval_seconds",
        lambda c: c.failover.health_check_interval_seconds,
    ),
    ("health", lambda c: c.health.value),
    ("security.encryption_at_rest", lambda c: c.security.encryption_at_rest),
    ("security.encryption_in_transit", lambda c: c.security.encryption_in_transit),
    ("security.auth_required", lambda c: c.security.auth_required),
    ("security.backup_enabled", lambda c: c.security.backup_enabled),
    ("security.rate_limiting", lambda c: c.security.rate_limiting),
    ("security.waf_protected", lambda c: c.security.waf_protected),
    ("parameters", lambda c: c.parameters),
    ("tags", lambda c: sorted(c.tags)),
]


def _safe_serialize(val: Any) -> Any:
    """Make a value JSON-serializable."""
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    if isinstance(val, dict):
        return {k: _safe_serialize(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_safe_serialize(v) for v in val]
    return str(val)


def _extract_config(comp: Component) -> dict[str, Any]:
    """Extract a flat config dict from a Component."""
    return {path: getter(comp) for path, getter in _EXTRACTORS}


def _compute_snapshot_id(graph: InfraGraph) -> str:
    """Deterministic short hash for a graph snapshot."""
    parts: list[str] = []
    for cid in sorted(graph.components):
        comp = graph.components[cid]
        cfg = _extract_config(comp)
        parts.append(f"{cid}:{cfg}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _classify_category(path: str, baseline_val: Any, current_val: Any) -> DriftCategory:
    """Heuristically classify which drift category a field change falls under."""
    if path.startswith("security.") or path == "tags":
        return DriftCategory.SCHEMA
    if path == "parameters":
        # If a specific key looks like a version string, classify as VERSION
        if isinstance(baseline_val, dict) and isinstance(current_val, dict):
            for key in set(baseline_val) | set(current_val):
                val_b = str(baseline_val.get(key, ""))
                val_c = str(current_val.get(key, ""))
                if val_b != val_c and any(
                    v in key.lower() for v in ("version", "ver", "release")
                ):
                    return DriftCategory.VERSION
            return DriftCategory.PARAMETER
        return DriftCategory.PARAMETER
    if "secret" in path.lower() or "rotation" in path.lower():
        return DriftCategory.SECRET_ROTATION
    return DriftCategory.PARAMETER


def _severity_from_criticality(weight: float) -> DriftSeverity:
    """Map a criticality weight to a severity level."""
    if weight >= 9.0:
        return DriftSeverity.CRITICAL
    if weight >= 7.0:
        return DriftSeverity.HIGH
    if weight >= 5.0:
        return DriftSeverity.MEDIUM
    if weight >= 3.0:
        return DriftSeverity.LOW
    return DriftSeverity.INFO


def _pick_remediation(
    path: str, category: DriftCategory, severity: DriftSeverity
) -> tuple[RemediationStrategy, str]:
    """Choose a remediation strategy and produce a human-readable detail."""
    if category == DriftCategory.SECRET_ROTATION:
        return (
            RemediationStrategy.ROTATE_SECRET,
            f"Rotate the secret for '{path}' and update all consumers.",
        )
    if severity == DriftSeverity.CRITICAL:
        return (
            RemediationStrategy.RESTORE_BASELINE,
            f"Restore '{path}' to baseline value immediately — critical risk.",
        )
    if severity == DriftSeverity.HIGH:
        return (
            RemediationStrategy.ESCALATE,
            f"Escalate '{path}' drift to the owning team for prompt resolution.",
        )
    if path.startswith("security."):
        return (
            RemediationStrategy.RESTORE_BASELINE,
            f"Security parameter '{path}' should match baseline.",
        )
    if severity in (DriftSeverity.MEDIUM,):
        return (
            RemediationStrategy.AUTO_FIX,
            f"Auto-fix '{path}' by applying the baseline value.",
        )
    return (
        RemediationStrategy.ACCEPT_CURRENT,
        f"Low-risk drift on '{path}' — consider accepting current value.",
    )


def _severity_rank(sev: DriftSeverity) -> int:
    return {
        DriftSeverity.CRITICAL: 4,
        DriftSeverity.HIGH: 3,
        DriftSeverity.MEDIUM: 2,
        DriftSeverity.LOW: 1,
        DriftSeverity.INFO: 0,
    }.get(sev, 0)


def _max_severity(*sevs: DriftSeverity) -> DriftSeverity:
    """Return the highest severity among the given values."""
    if not sevs:
        return DriftSeverity.INFO
    return max(sevs, key=_severity_rank)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ConfigDriftDetector:
    """Stateless engine for detecting and analysing configuration drift.

    Public API
    ----------
    - create_baseline        : snapshot a graph as the golden config
    - compare_to_baseline    : find drifts between baseline and current graph
    - compare_environments   : cross-environment drift detection
    - cluster_drifts         : group related drifts
    - track_drift_timeseries : build time-series data from repeated scans
    - build_config_dependency_graph : derive config dependency edges
    - assess_drift_risk      : per-component risk assessment
    - map_compliance         : compliance violation mapping
    - generate_report        : full drift report
    """

    # -- baseline management ------------------------------------------------

    def create_baseline(self, graph: InfraGraph) -> BaselineSnapshot:
        """Snapshot the current graph as the golden baseline."""
        now = datetime.now(timezone.utc)
        configs: dict[str, dict[str, Any]] = {}
        for cid, comp in graph.components.items():
            configs[cid] = _extract_config(comp)
        return BaselineSnapshot(
            snapshot_id=_compute_snapshot_id(graph),
            timestamp=now,
            component_configs=configs,
            metadata={
                "total_components": len(graph.components),
                "resilience_score": graph.resilience_score(),
            },
        )

    # -- baseline comparison ------------------------------------------------

    def compare_to_baseline(
        self,
        baseline: BaselineSnapshot,
        current: InfraGraph,
    ) -> list[DriftItem]:
        """Compare the current graph against a saved baseline and return drifts."""
        items: list[DriftItem] = []
        current_configs: dict[str, dict[str, Any]] = {}
        for cid, comp in current.components.items():
            current_configs[cid] = _extract_config(comp)

        all_ids = set(baseline.component_configs) | set(current_configs)
        for cid in sorted(all_ids):
            b_cfg = baseline.component_configs.get(cid)
            c_cfg = current_configs.get(cid)

            if b_cfg is None:
                # New component — not in baseline
                items.append(
                    DriftItem(
                        component_id=cid,
                        parameter_path="__component__",
                        category=DriftCategory.SCHEMA,
                        severity=DriftSeverity.LOW,
                        baseline_value=None,
                        current_value=cid,
                        description=f"Component '{cid}' added (not in baseline).",
                        criticality_weight=2.0,
                        risk_score=5.0,
                        remediation=RemediationStrategy.MANUAL_REVIEW,
                        remediation_detail="Review whether the new component needs baseline inclusion.",
                    )
                )
                continue

            if c_cfg is None:
                # Removed component — was in baseline
                items.append(
                    DriftItem(
                        component_id=cid,
                        parameter_path="__component__",
                        category=DriftCategory.SCHEMA,
                        severity=DriftSeverity.HIGH,
                        baseline_value=cid,
                        current_value=None,
                        description=f"Component '{cid}' removed (was in baseline).",
                        criticality_weight=8.0,
                        risk_score=40.0,
                        remediation=RemediationStrategy.ESCALATE,
                        remediation_detail="Verify the removal was intentional.",
                    )
                )
                continue

            # Both exist — compare field-by-field
            items.extend(self._compare_configs(cid, b_cfg, c_cfg))

        return items

    def _compare_configs(
        self,
        component_id: str,
        baseline_cfg: dict[str, Any],
        current_cfg: dict[str, Any],
    ) -> list[DriftItem]:
        """Compare two config dicts field-by-field."""
        drifts: list[DriftItem] = []
        all_keys = set(baseline_cfg) | set(current_cfg)
        for key in sorted(all_keys):
            b_val = baseline_cfg.get(key)
            c_val = current_cfg.get(key)
            if b_val == c_val:
                continue
            weight = _CRITICALITY.get(key, 3.0)
            category = _classify_category(key, b_val, c_val)
            severity = _severity_from_criticality(weight)
            violations = _COMPLIANCE_MAP.get(key, [])
            # Upgrade severity if compliance is violated
            if violations and _severity_rank(severity) < _severity_rank(DriftSeverity.HIGH):
                severity = DriftSeverity.HIGH
            risk = weight * (1.0 + len(violations) * 0.5)
            rem, rem_detail = _pick_remediation(key, category, severity)
            drifts.append(
                DriftItem(
                    component_id=component_id,
                    parameter_path=key,
                    category=category,
                    severity=severity,
                    baseline_value=b_val,
                    current_value=c_val,
                    description=f"'{key}' drifted from {b_val!r} to {c_val!r}.",
                    criticality_weight=weight,
                    compliance_violations=violations,
                    risk_score=round(risk, 2),
                    remediation=rem,
                    remediation_detail=rem_detail,
                )
            )
        return drifts

    # -- cross-environment comparison ---------------------------------------

    def compare_environments(
        self,
        environments: dict[str, InfraGraph],
        *,
        reference_env: str | None = None,
        acceptable_diffs: set[str] | None = None,
    ) -> list[CrossEnvDrift]:
        """Detect drift across environments (e.g. dev / staging / prod).

        If *reference_env* is given, every other env is compared to it.
        Otherwise all unique pairs are compared.
        """
        acceptable_diffs = acceptable_diffs or set()
        results: list[CrossEnvDrift] = []
        env_configs: dict[str, dict[str, dict[str, Any]]] = {}
        for env_name, graph in environments.items():
            env_configs[env_name] = {
                cid: _extract_config(comp) for cid, comp in graph.components.items()
            }

        env_names = sorted(environments)
        pairs: list[tuple[str, str]] = []
        if reference_env and reference_env in env_names:
            for other in env_names:
                if other != reference_env:
                    pairs.append((reference_env, other))
        else:
            for i, a in enumerate(env_names):
                for b in env_names[i + 1 :]:
                    pairs.append((a, b))

        for env_a, env_b in pairs:
            cfgs_a = env_configs.get(env_a, {})
            cfgs_b = env_configs.get(env_b, {})
            all_cids = set(cfgs_a) | set(cfgs_b)
            for cid in sorted(all_cids):
                cfg_a = cfgs_a.get(cid, {})
                cfg_b = cfgs_b.get(cid, {})
                all_keys = set(cfg_a) | set(cfg_b)
                for key in sorted(all_keys):
                    val_a = cfg_a.get(key)
                    val_b = cfg_b.get(key)
                    if val_a == val_b:
                        continue
                    weight = _CRITICALITY.get(key, 3.0)
                    sev = _severity_from_criticality(weight)
                    is_acceptable = key in acceptable_diffs
                    results.append(
                        CrossEnvDrift(
                            component_id=cid,
                            parameter_path=key,
                            env_a_name=env_a,
                            env_a_value=val_a,
                            env_b_name=env_b,
                            env_b_value=val_b,
                            severity=sev,
                            acceptable=is_acceptable,
                        )
                    )
        return results

    # -- drift clustering ---------------------------------------------------

    def cluster_drifts(self, items: list[DriftItem]) -> list[DriftCluster]:
        """Group drift items by component and category into clusters.

        Correlated drifts (same component or same category across
        tightly-coupled components) are grouped together.
        """
        if not items:
            return []

        # First pass: group by (component_id, category)
        groups: dict[tuple[str, str], list[DriftItem]] = defaultdict(list)
        for it in items:
            groups[(it.component_id, it.category.value)].append(it)

        clusters: list[DriftCluster] = []
        for idx, ((comp_id, cat_val), group_items) in enumerate(
            sorted(groups.items())
        ):
            comp_ids = sorted({it.component_id for it in group_items})
            agg_sev = _max_severity(*(it.severity for it in group_items))
            agg_risk = sum(it.risk_score for it in group_items)
            hypothesis = self._hypothesize_root_cause(cat_val, group_items)
            clusters.append(
                DriftCluster(
                    cluster_id=f"cluster-{idx:03d}",
                    component_ids=comp_ids,
                    items=group_items,
                    root_cause_hypothesis=hypothesis,
                    aggregate_severity=agg_sev,
                    aggregate_risk=round(agg_risk, 2),
                )
            )

        return clusters

    @staticmethod
    def _hypothesize_root_cause(
        category_value: str, items: list[DriftItem]
    ) -> str:
        """Produce a root-cause hypothesis for a cluster."""
        if category_value == DriftCategory.SECRET_ROTATION.value:
            return "Secret rotation may be overdue or inconsistent."
        if category_value == DriftCategory.VERSION.value:
            return "Version drift suggests staggered or incomplete rollout."
        paths = {it.parameter_path for it in items}
        if any("security" in p for p in paths):
            return "Security configuration may have been relaxed inadvertently."
        if any("failover" in p or "autoscaling" in p for p in paths):
            return "Resilience features were likely modified during maintenance."
        return "Configuration was changed outside the standard change process."

    # -- time-series tracking -----------------------------------------------

    def track_drift_timeseries(
        self,
        history: list[tuple[datetime, list[DriftItem]]],
    ) -> list[DriftTimeSeries]:
        """Build time-series data from repeated drift scans.

        *history* is a list of ``(scan_timestamp, drift_items)`` pairs,
        ordered chronologically.
        """
        tracking: dict[tuple[str, str], DriftTimeSeries] = {}
        for ts, items in history:
            for it in items:
                key = (it.component_id, it.parameter_path)
                if key not in tracking:
                    tracking[key] = DriftTimeSeries(
                        component_id=it.component_id,
                        parameter_path=it.parameter_path,
                        first_detected=ts,
                        last_detected=ts,
                        observation_count=1,
                    )
                else:
                    entry = tracking[key]
                    entry.last_detected = ts
                    entry.observation_count += 1

        # Calculate velocity (observations / elapsed_days)
        for entry in tracking.values():
            elapsed = (entry.last_detected - entry.first_detected).total_seconds()
            days = elapsed / 86400.0 if elapsed > 0 else 1.0
            entry.drift_velocity = round(entry.observation_count / days, 4)

        return sorted(tracking.values(), key=lambda e: e.drift_velocity, reverse=True)

    # -- configuration dependency graph -------------------------------------

    def build_config_dependency_graph(
        self, graph: InfraGraph
    ) -> list[ConfigDependency]:
        """Derive config-level dependencies from the infrastructure graph.

        For every infrastructure dependency edge we record which upstream
        parameters logically affect the downstream service.
        """
        deps: list[ConfigDependency] = []
        for edge in graph.all_dependency_edges():
            source_comp = graph.get_component(edge.source_id)
            target_comp = graph.get_component(edge.target_id)
            if source_comp is None or target_comp is None:
                continue

            # Timeout / retry on the caller must accommodate the target's latency
            deps.append(
                ConfigDependency(
                    source_component_id=edge.source_id,
                    source_parameter="capacity.timeout_seconds",
                    target_component_id=edge.target_id,
                    target_parameter="capacity.timeout_seconds",
                    relationship="timeout_must_exceed",
                )
            )
            # Capacity: the caller's max_rps shouldn't exceed what the target
            # can serve
            deps.append(
                ConfigDependency(
                    source_component_id=edge.source_id,
                    source_parameter="capacity.max_rps",
                    target_component_id=edge.target_id,
                    target_parameter="capacity.max_rps",
                    relationship="capacity_must_not_exceed",
                )
            )
        return deps

    # -- risk assessment ----------------------------------------------------

    def assess_drift_risk(
        self,
        items: list[DriftItem],
        graph: InfraGraph,
    ) -> list[DriftRiskAssessment]:
        """Assess reliability impact per component from unresolved drifts."""
        by_comp: dict[str, list[DriftItem]] = defaultdict(list)
        for it in items:
            by_comp[it.component_id].append(it)

        assessments: list[DriftRiskAssessment] = []
        for cid, comp_items in sorted(by_comp.items()):
            total_risk = sum(it.risk_score for it in comp_items)
            blast = 0
            comp = graph.get_component(cid)
            if comp is not None:
                blast = len(graph.get_all_affected(cid))

            # MTTR increase estimate: 5 min per medium, 10 per high, 20 per crit
            mttr_incr = 0.0
            for it in comp_items:
                if it.severity == DriftSeverity.CRITICAL:
                    mttr_incr += 20.0
                elif it.severity == DriftSeverity.HIGH:
                    mttr_incr += 10.0
                elif it.severity == DriftSeverity.MEDIUM:
                    mttr_incr += 5.0
                else:
                    mttr_incr += 1.0

            recs: list[str] = []
            if any(it.severity == DriftSeverity.CRITICAL for it in comp_items):
                recs.append(f"Resolve critical drifts on '{cid}' immediately.")
            if blast > 2:
                recs.append(
                    f"'{cid}' affects {blast} downstream components — prioritise."
                )
            if total_risk > 30:
                recs.append(
                    f"High aggregate risk ({total_risk:.1f}) on '{cid}' — review config."
                )

            reliability = "low"
            if total_risk >= 40:
                reliability = "critical"
            elif total_risk >= 20:
                reliability = "high"
            elif total_risk >= 10:
                reliability = "moderate"

            assessments.append(
                DriftRiskAssessment(
                    component_id=cid,
                    total_risk_score=round(total_risk, 2),
                    reliability_impact=reliability,
                    blast_radius=blast,
                    estimated_mttr_increase_minutes=round(mttr_incr, 1),
                    recommendations=recs,
                )
            )
        return assessments

    # -- compliance mapping -------------------------------------------------

    def map_compliance(
        self, items: list[DriftItem]
    ) -> dict[str, list[DriftItem]]:
        """Map drift items to the compliance frameworks they violate.

        Returns a dict keyed by framework value with the list of offending
        drift items.
        """
        mapping: dict[str, list[DriftItem]] = defaultdict(list)
        for it in items:
            for fw in it.compliance_violations:
                mapping[fw.value].append(it)
        return dict(mapping)

    # -- full report --------------------------------------------------------

    def generate_report(
        self,
        items: list[DriftItem],
        graph: InfraGraph,
        *,
        cross_env_drifts: list[CrossEnvDrift] | None = None,
    ) -> DriftReport:
        """Produce a comprehensive drift analysis report."""
        clusters = self.cluster_drifts(items)
        assessments = self.assess_drift_risk(items, graph)
        compliance = self.map_compliance(items)

        crit = sum(1 for it in items if it.severity == DriftSeverity.CRITICAL)
        high = sum(1 for it in items if it.severity == DriftSeverity.HIGH)
        med = sum(1 for it in items if it.severity == DriftSeverity.MEDIUM)
        low = sum(1 for it in items if it.severity == DriftSeverity.LOW)
        info = sum(1 for it in items if it.severity == DriftSeverity.INFO)
        overall_risk = sum(it.risk_score for it in items)

        # Build summary
        summary = self._build_summary(len(items), crit, high, overall_risk)

        comp_summary = {fw: len(its) for fw, its in compliance.items()}

        report = DriftReport(
            total_drifts=len(items),
            critical_count=crit,
            high_count=high,
            medium_count=med,
            low_count=low,
            info_count=info,
            items=items,
            clusters=clusters,
            cross_env_drifts=cross_env_drifts or [],
            risk_assessments=assessments,
            compliance_summary=comp_summary,
            overall_risk_score=round(overall_risk, 2),
            summary=summary,
        )
        return report

    @staticmethod
    def _build_summary(total: int, crit: int, high: int, risk: float) -> str:
        if total == 0:
            return "No configuration drift detected. All parameters match baseline."
        parts = [f"Detected {total} configuration drift(s)."]
        if crit > 0:
            parts.append(f"{crit} CRITICAL.")
        if high > 0:
            parts.append(f"{high} HIGH.")
        parts.append(f"Overall risk score: {risk:.1f}.")
        if crit > 0:
            parts.append("Immediate remediation required.")
        elif high > 0:
            parts.append("Prompt attention recommended.")
        else:
            parts.append("Monitor and address at next change window.")
        return " ".join(parts)
