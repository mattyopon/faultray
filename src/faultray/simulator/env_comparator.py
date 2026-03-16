"""Multi-Environment Comparison Engine.

Compare resilience, security, and cost across dev/staging/prod environments.
Detects configuration drift and provides actionable recommendations to
achieve environment parity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EnvironmentProfile:
    """Profile summarising a single environment's posture."""

    name: str  # "dev", "staging", "prod"
    graph: InfraGraph
    resilience_score: float
    security_score: float
    cost_monthly: float
    component_count: int


@dataclass
class EnvComparisonResult:
    """Result of comparing multiple environments."""

    environments: list[EnvironmentProfile] = field(default_factory=list)
    drift_detected: bool = False
    drift_details: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    parity_score: float = 0.0  # 0-100


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _security_score(graph: InfraGraph) -> float:
    """Calculate a security score (0-100) from component security profiles."""
    if not graph.components:
        return 0.0

    total = 0.0
    count = 0

    for comp in graph.components.values():
        sec = comp.security
        score = 0.0
        checks = 0

        # Encryption
        if sec.encryption_at_rest:
            score += 1
        checks += 1
        if sec.encryption_in_transit:
            score += 1
        checks += 1

        # Access control
        if sec.waf_protected:
            score += 1
        checks += 1
        if sec.rate_limiting:
            score += 1
        checks += 1
        if sec.auth_required:
            score += 1
        checks += 1

        # Network
        if sec.network_segmented:
            score += 1
        checks += 1

        # Backup
        if sec.backup_enabled:
            score += 1
        checks += 1

        # Monitoring
        if sec.log_enabled:
            score += 1
        checks += 1
        if sec.ids_monitored:
            score += 1
        checks += 1

        total += (score / checks * 100.0) if checks > 0 else 0.0
        count += 1

    return round(total / count, 1) if count > 0 else 0.0


def _cost_monthly(graph: InfraGraph) -> float:
    """Estimate monthly cost from component cost profiles."""
    total = 0.0
    for comp in graph.components.values():
        hourly = comp.cost_profile.hourly_infra_cost
        monthly_contract = comp.cost_profile.monthly_contract_value
        # Use monthly_contract_value if set, otherwise compute from hourly
        if monthly_contract > 0:
            total += monthly_contract
        elif hourly > 0:
            total += hourly * 730  # ~average hours in a month
    return round(total, 2)


# ---------------------------------------------------------------------------
# EnvironmentComparator
# ---------------------------------------------------------------------------


class EnvironmentComparator:
    """Compare resilience, security, and cost across environments."""

    def __init__(self) -> None:
        pass

    # ----- public API -----

    def compare(self, envs: dict[str, InfraGraph]) -> EnvComparisonResult:
        """Compare multiple environments for configuration drift.

        Args:
            envs: Mapping of environment name (e.g. "prod") to InfraGraph.

        Returns:
            An ``EnvComparisonResult`` containing profiles, drift details,
            parity score, and recommendations.
        """
        if len(envs) < 2:
            logger.warning("Need at least 2 environments to compare")
            return EnvComparisonResult()

        profiles: list[EnvironmentProfile] = []
        for name, graph in envs.items():
            profiles.append(EnvironmentProfile(
                name=name,
                graph=graph,
                resilience_score=graph.resilience_score(),
                security_score=_security_score(graph),
                cost_monthly=_cost_monthly(graph),
                component_count=len(graph.components),
            ))

        # Collect drift from all pairs (each pair checked once)
        all_drift: list[dict] = []
        names = list(envs.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                pair_drift = self.detect_drift(
                    envs[names[i]], envs[names[j]],
                    env_a_name=names[i], env_b_name=names[j],
                )
                all_drift.extend(pair_drift)

        drift_detected = len(all_drift) > 0
        parity_score = self._calculate_parity(profiles)
        recommendations = self._generate_recommendations(profiles, all_drift)

        return EnvComparisonResult(
            environments=profiles,
            drift_detected=drift_detected,
            drift_details=all_drift,
            recommendations=recommendations,
            parity_score=round(parity_score, 1),
        )

    def detect_drift(
        self,
        env_a: InfraGraph,
        env_b: InfraGraph,
        *,
        env_a_name: str = "env_a",
        env_b_name: str = "env_b",
    ) -> list[dict]:
        """Detect configuration differences between two environments.

        Returns a list of dicts each with keys:
        ``component``, ``field``, ``<env_a_name>_value``, ``<env_b_name>_value``.
        """
        drift: list[dict] = []
        a_ids = set(env_a.components.keys())
        b_ids = set(env_b.components.keys())

        # Components missing from one side
        for cid in sorted(a_ids - b_ids):
            drift.append({
                "component": cid,
                "field": "existence",
                f"{env_a_name}_value": "present",
                f"{env_b_name}_value": "missing",
            })

        for cid in sorted(b_ids - a_ids):
            drift.append({
                "component": cid,
                "field": "existence",
                f"{env_a_name}_value": "missing",
                f"{env_b_name}_value": "present",
            })

        # Shared components - compare key config fields
        for cid in sorted(a_ids & b_ids):
            ca = env_a.components[cid]
            cb = env_b.components[cid]

            if ca.replicas != cb.replicas:
                drift.append({
                    "component": cid,
                    "field": "replicas",
                    f"{env_a_name}_value": ca.replicas,
                    f"{env_b_name}_value": cb.replicas,
                })

            if ca.type != cb.type:
                drift.append({
                    "component": cid,
                    "field": "type",
                    f"{env_a_name}_value": ca.type.value,
                    f"{env_b_name}_value": cb.type.value,
                })

            if ca.failover.enabled != cb.failover.enabled:
                drift.append({
                    "component": cid,
                    "field": "failover",
                    f"{env_a_name}_value": ca.failover.enabled,
                    f"{env_b_name}_value": cb.failover.enabled,
                })

            if ca.autoscaling.enabled != cb.autoscaling.enabled:
                drift.append({
                    "component": cid,
                    "field": "autoscaling",
                    f"{env_a_name}_value": ca.autoscaling.enabled,
                    f"{env_b_name}_value": cb.autoscaling.enabled,
                })

            # Security profile diffs
            sec_a = ca.security
            sec_b = cb.security
            for attr in (
                "encryption_at_rest", "encryption_in_transit", "waf_protected",
                "rate_limiting", "auth_required", "network_segmented",
                "backup_enabled",
            ):
                va = getattr(sec_a, attr)
                vb = getattr(sec_b, attr)
                if va != vb:
                    drift.append({
                        "component": cid,
                        "field": f"security.{attr}",
                        f"{env_a_name}_value": va,
                        f"{env_b_name}_value": vb,
                    })

            # Capacity diffs
            if ca.capacity.max_rps != cb.capacity.max_rps:
                drift.append({
                    "component": cid,
                    "field": "capacity.max_rps",
                    f"{env_a_name}_value": ca.capacity.max_rps,
                    f"{env_b_name}_value": cb.capacity.max_rps,
                })

        return drift

    # ----- private helpers -----

    def _calculate_parity(self, profiles: list[EnvironmentProfile]) -> float:
        """Compute parity score (0-100) across environment profiles.

        100 means all environments are identical in resilience, security and
        component count; 0 means they are completely different.
        """
        if len(profiles) < 2:
            return 100.0

        # Compute spread for each metric (normalised to 0-1)
        resilience_scores = [p.resilience_score for p in profiles]
        security_scores = [p.security_score for p in profiles]
        counts = [float(p.component_count) for p in profiles]

        spreads: list[float] = []
        for values in (resilience_scores, security_scores, counts):
            max_v = max(values)
            min_v = min(values)
            if max_v == 0:
                spreads.append(0.0)
            else:
                spreads.append((max_v - min_v) / max(max_v, 1.0))

        avg_spread = sum(spreads) / len(spreads) if spreads else 0.0
        return max(0.0, 100.0 - avg_spread * 100.0)

    def _generate_recommendations(
        self,
        profiles: list[EnvironmentProfile],
        drift_details: list[dict],
    ) -> list[str]:
        recs: list[str] = []

        # Resilience gap
        sorted_p = sorted(profiles, key=lambda p: p.resilience_score)
        weakest = sorted_p[0]
        strongest = sorted_p[-1]

        if strongest.resilience_score - weakest.resilience_score > 15:
            recs.append(
                f"'{weakest.name}' resilience ({weakest.resilience_score:.1f}) "
                f"is significantly lower than '{strongest.name}' "
                f"({strongest.resilience_score:.1f}). Align redundancy and "
                f"failover settings."
            )

        # Security gap
        sorted_s = sorted(profiles, key=lambda p: p.security_score)
        if sorted_s[-1].security_score - sorted_s[0].security_score > 20:
            recs.append(
                f"'{sorted_s[0].name}' has lower security posture "
                f"({sorted_s[0].security_score:.0f}) compared to "
                f"'{sorted_s[-1].name}' ({sorted_s[-1].security_score:.0f}). "
                f"Review security configurations."
            )

        # Missing components
        missing = [d for d in drift_details if d["field"] == "existence"]
        if missing:
            recs.append(
                f"{len(missing)} component(s) exist in one environment but "
                f"not another. Ensure all environments have matching "
                f"component sets."
            )

        # Replica drifts
        replica_drifts = [d for d in drift_details if d["field"] == "replicas"]
        if replica_drifts:
            recs.append(
                f"{len(replica_drifts)} component(s) have different replica "
                f"counts across environments. Verify this is intentional."
            )

        # Security config drifts
        sec_drifts = [d for d in drift_details if d["field"].startswith("security.")]
        if sec_drifts:
            recs.append(
                f"{len(sec_drifts)} security setting(s) differ across "
                f"environments. Security parity is important for consistent "
                f"protection."
            )

        # Deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for r in recs:
            if r not in seen:
                seen.add(r)
                unique.append(r)
        return unique
