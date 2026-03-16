"""Security Chaos Engineering — compound failure + attack simulation.

Combines chaos engineering (infrastructure failures) with security attack
simulation to answer: "What happens when your system is under attack AND
experiencing failures simultaneously?"
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType, HealthStatus, SecurityProfile
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AttackType(str, Enum):
    DDOS = "ddos"
    AUTH_BYPASS = "auth_bypass"
    CERT_EXPIRY = "cert_expiry"
    DNS_POISONING = "dns_poisoning"
    DATA_EXFILTRATION = "data_exfiltration"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    SUPPLY_CHAIN_ATTACK = "supply_chain_attack"
    API_ABUSE = "api_abuse"
    CREDENTIAL_STUFFING = "credential_stuffing"
    MAN_IN_THE_MIDDLE = "man_in_the_middle"


class SecurityPosture(str, Enum):
    HARDENED = "hardened"
    STANDARD = "standard"
    WEAK = "weak"
    COMPROMISED = "compromised"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CompoundScenario(BaseModel):
    """A scenario combining an infrastructure failure with a security attack."""

    failure_type: str
    attack_type: AttackType
    simultaneous: bool = True
    attack_severity: float = Field(default=0.5, ge=0.0, le=1.0)
    failure_severity: float = Field(default=0.5, ge=0.0, le=1.0)


class SecurityResilienceScore(BaseModel):
    """Resilience scores from a compound scenario simulation."""

    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    attack_resistance: float = Field(default=0.0, ge=0.0, le=100.0)
    failure_containment: float = Field(default=0.0, ge=0.0, le=100.0)
    compound_risk: float = Field(default=0.0, ge=0.0, le=100.0)
    exposure_window_minutes: float = Field(default=0.0, ge=0.0)


class AttackSurfaceChange(BaseModel):
    """How a failure changes a component's attack surface."""

    component_id: str
    normal_attack_surface: float = Field(default=0.0, ge=0.0, le=1.0)
    degraded_attack_surface: float = Field(default=0.0, ge=0.0, le=1.0)
    increase_percent: float = 0.0
    vulnerabilities_exposed: list[str] = Field(default_factory=list)


class SecurityChaosReport(BaseModel):
    """Full report from a security chaos engineering run."""

    compound_scenarios_tested: int = 0
    highest_risk_scenario: str = ""
    security_resilience: SecurityResilienceScore = Field(
        default_factory=SecurityResilienceScore
    )
    attack_surface_changes: list[AttackSurfaceChange] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Weights for security profile fields → posture scoring
# ---------------------------------------------------------------------------

_SECURITY_FIELD_WEIGHTS: dict[str, float] = {
    "encryption_at_rest": 1.0,
    "encryption_in_transit": 1.0,
    "waf_protected": 1.0,
    "rate_limiting": 1.0,
    "auth_required": 1.5,
    "network_segmented": 1.5,
    "backup_enabled": 0.5,
    "log_enabled": 0.5,
    "ids_monitored": 1.0,
}

_MAX_SECURITY_WEIGHT = sum(_SECURITY_FIELD_WEIGHTS.values())

# Attack → which defences are most relevant (field → effectiveness 0-1)
_ATTACK_DEFENSE_MAP: dict[AttackType, dict[str, float]] = {
    AttackType.DDOS: {"waf_protected": 0.7, "rate_limiting": 0.9},
    AttackType.AUTH_BYPASS: {"auth_required": 0.8, "ids_monitored": 0.5},
    AttackType.CERT_EXPIRY: {"encryption_in_transit": 0.9, "log_enabled": 0.3},
    AttackType.DNS_POISONING: {"network_segmented": 0.6, "ids_monitored": 0.5},
    AttackType.DATA_EXFILTRATION: {"encryption_at_rest": 0.8, "encryption_in_transit": 0.6, "network_segmented": 0.5},
    AttackType.PRIVILEGE_ESCALATION: {"auth_required": 0.7, "network_segmented": 0.6, "ids_monitored": 0.5},
    AttackType.SUPPLY_CHAIN_ATTACK: {"network_segmented": 0.5, "ids_monitored": 0.4, "log_enabled": 0.3},
    AttackType.API_ABUSE: {"rate_limiting": 0.8, "waf_protected": 0.6, "auth_required": 0.5},
    AttackType.CREDENTIAL_STUFFING: {"rate_limiting": 0.8, "auth_required": 0.6, "ids_monitored": 0.4},
    AttackType.MAN_IN_THE_MIDDLE: {"encryption_in_transit": 0.9, "network_segmented": 0.5},
}

# Failure type → which security fields become weakened
_FAILURE_EXPOSURE_MAP: dict[str, list[str]] = {
    "node_failure": ["network_segmented", "ids_monitored", "log_enabled"],
    "network_partition": ["encryption_in_transit", "network_segmented", "waf_protected"],
    "disk_failure": ["encryption_at_rest", "backup_enabled", "log_enabled"],
    "memory_exhaustion": ["rate_limiting", "waf_protected", "ids_monitored"],
    "cpu_overload": ["rate_limiting", "waf_protected", "auth_required"],
    "dns_failure": ["network_segmented", "waf_protected"],
    "certificate_expiry": ["encryption_in_transit", "auth_required"],
    "dependency_timeout": ["auth_required", "rate_limiting"],
    "cascade_failure": ["network_segmented", "ids_monitored", "log_enabled", "waf_protected"],
}

# All known failure types
_FAILURE_TYPES = list(_FAILURE_EXPOSURE_MAP.keys())


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SecurityChaosEngine:
    """Simulates compound infrastructure-failure + security-attack scenarios."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess_security_posture(self, component_id: str) -> SecurityPosture:
        """Assess the security posture of a component based on its SecurityProfile."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return SecurityPosture.COMPROMISED

        score = self._security_profile_score(comp.security)

        if score >= 0.75:
            return SecurityPosture.HARDENED
        if score >= 0.45:
            return SecurityPosture.STANDARD
        if score >= 0.20:
            return SecurityPosture.WEAK
        return SecurityPosture.COMPROMISED

    def simulate_compound(
        self, scenario: CompoundScenario, target_id: str
    ) -> SecurityResilienceScore:
        """Simulate a combined attack + failure against *target_id*."""
        comp = self.graph.get_component(target_id)
        if comp is None:
            return SecurityResilienceScore(
                overall_score=0.0,
                attack_resistance=0.0,
                failure_containment=0.0,
                compound_risk=100.0,
                exposure_window_minutes=0.0,
            )

        # Attack resistance: how well defences counter the attack
        attack_resistance = self._compute_attack_resistance(comp, scenario.attack_type)
        # Scale by attack severity
        attack_resistance *= 1.0 - scenario.attack_severity * 0.4

        # Failure containment: how well the component tolerates the failure
        failure_containment = self._compute_failure_containment(comp, scenario.failure_type)
        failure_containment *= 1.0 - scenario.failure_severity * 0.4

        # Compound risk: amplification when both happen simultaneously
        if scenario.simultaneous:
            compound_risk = (
                (1.0 - attack_resistance / 100.0)
                * (1.0 - failure_containment / 100.0)
                * 100.0
            )
        else:
            compound_risk = (
                max(1.0 - attack_resistance / 100.0, 1.0 - failure_containment / 100.0)
                * 50.0
            )

        # Overall score: weighted combination
        overall = (
            attack_resistance * 0.35
            + failure_containment * 0.35
            + (100.0 - compound_risk) * 0.30
        )

        # Exposure window: how long the component is vulnerable (minutes)
        base_window = 30.0 * scenario.failure_severity + 20.0 * scenario.attack_severity
        posture = self.assess_security_posture(target_id)
        posture_factor = {
            SecurityPosture.HARDENED: 0.5,
            SecurityPosture.STANDARD: 1.0,
            SecurityPosture.WEAK: 1.8,
            SecurityPosture.COMPROMISED: 3.0,
        }[posture]
        exposure_window = base_window * posture_factor

        return SecurityResilienceScore(
            overall_score=round(max(0.0, min(100.0, overall)), 2),
            attack_resistance=round(max(0.0, min(100.0, attack_resistance)), 2),
            failure_containment=round(max(0.0, min(100.0, failure_containment)), 2),
            compound_risk=round(max(0.0, min(100.0, compound_risk)), 2),
            exposure_window_minutes=round(max(0.0, exposure_window), 2),
        )

    def calculate_attack_surface_change(
        self, component_id: str, failure_type: str
    ) -> AttackSurfaceChange:
        """Calculate how a failure changes the attack surface of a component."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return AttackSurfaceChange(
                component_id=component_id,
                normal_attack_surface=1.0,
                degraded_attack_surface=1.0,
                increase_percent=0.0,
                vulnerabilities_exposed=["component_not_found"],
            )

        normal_surface = 1.0 - self._security_profile_score(comp.security)
        exposed_fields = _FAILURE_EXPOSURE_MAP.get(failure_type, [])

        # Build a "degraded" security profile: fields exposed by the failure are
        # treated as disabled.
        degraded_data = comp.security.model_dump()
        vulnerabilities: list[str] = []
        for field_name in exposed_fields:
            if degraded_data.get(field_name, False) is True:
                degraded_data[field_name] = False
                vulnerabilities.append(f"{failure_type}_disables_{field_name}")

        degraded_profile = SecurityProfile(**degraded_data)
        degraded_surface = 1.0 - self._security_profile_score(degraded_profile)

        if normal_surface > 0:
            increase_pct = ((degraded_surface - normal_surface) / normal_surface) * 100.0
        elif degraded_surface > 0:
            increase_pct = 100.0
        else:
            increase_pct = 0.0

        return AttackSurfaceChange(
            component_id=component_id,
            normal_attack_surface=round(max(0.0, min(1.0, normal_surface)), 4),
            degraded_attack_surface=round(max(0.0, min(1.0, degraded_surface)), 4),
            increase_percent=round(increase_pct, 2),
            vulnerabilities_exposed=vulnerabilities,
        )

    def find_critical_combinations(self) -> list[CompoundScenario]:
        """Find the most dangerous attack + failure combinations for the graph."""
        scenarios: list[CompoundScenario] = []
        for comp in self.graph.components.values():
            posture = self.assess_security_posture(comp.id)
            if posture in (SecurityPosture.WEAK, SecurityPosture.COMPROMISED):
                for attack in AttackType:
                    for failure in _FAILURE_TYPES:
                        scenarios.append(
                            CompoundScenario(
                                failure_type=failure,
                                attack_type=attack,
                                simultaneous=True,
                                attack_severity=0.8,
                                failure_severity=0.8,
                            )
                        )
            else:
                # For hardened/standard components, only test high-impact combos
                for attack in (AttackType.DDOS, AttackType.DATA_EXFILTRATION, AttackType.SUPPLY_CHAIN_ATTACK):
                    scenarios.append(
                        CompoundScenario(
                            failure_type="cascade_failure",
                            attack_type=attack,
                            simultaneous=True,
                            attack_severity=0.7,
                            failure_severity=0.7,
                        )
                    )

        return scenarios

    def generate_report(
        self, scenarios: list[CompoundScenario]
    ) -> SecurityChaosReport:
        """Run all compound scenarios and produce a full report."""
        if not scenarios:
            return SecurityChaosReport()

        all_scores: list[tuple[CompoundScenario, SecurityResilienceScore]] = []
        surface_changes: dict[str, AttackSurfaceChange] = {}

        for scenario in scenarios:
            for comp in self.graph.components.values():
                score = self.simulate_compound(scenario, comp.id)
                all_scores.append((scenario, score))

                key = f"{comp.id}:{scenario.failure_type}"
                if key not in surface_changes:
                    change = self.calculate_attack_surface_change(
                        comp.id, scenario.failure_type
                    )
                    surface_changes[key] = change

        if not all_scores:
            return SecurityChaosReport(compound_scenarios_tested=len(scenarios))

        # Find highest-risk scenario (lowest overall_score)
        worst_scenario, worst_score = min(
            all_scores, key=lambda x: x[1].overall_score
        )
        highest_risk_desc = (
            f"{worst_scenario.attack_type.value}+{worst_scenario.failure_type}"
        )

        # Aggregate resilience score: average of all simulation scores
        avg_overall = sum(s.overall_score for _, s in all_scores) / len(all_scores)
        avg_attack = sum(s.attack_resistance for _, s in all_scores) / len(all_scores)
        avg_containment = sum(s.failure_containment for _, s in all_scores) / len(all_scores)
        avg_compound = sum(s.compound_risk for _, s in all_scores) / len(all_scores)
        max_exposure = max(s.exposure_window_minutes for _, s in all_scores)

        resilience = SecurityResilienceScore(
            overall_score=round(max(0.0, min(100.0, avg_overall)), 2),
            attack_resistance=round(max(0.0, min(100.0, avg_attack)), 2),
            failure_containment=round(max(0.0, min(100.0, avg_containment)), 2),
            compound_risk=round(max(0.0, min(100.0, avg_compound)), 2),
            exposure_window_minutes=round(max_exposure, 2),
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            all_scores, list(surface_changes.values())
        )

        return SecurityChaosReport(
            compound_scenarios_tested=len(scenarios),
            highest_risk_scenario=highest_risk_desc,
            security_resilience=resilience,
            attack_surface_changes=list(surface_changes.values()),
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _security_profile_score(profile: SecurityProfile) -> float:
        """Compute a normalised 0-1 score from a SecurityProfile."""
        total = 0.0
        for field_name, weight in _SECURITY_FIELD_WEIGHTS.items():
            if getattr(profile, field_name, False):
                total += weight
        return total / _MAX_SECURITY_WEIGHT

    def _compute_attack_resistance(
        self, comp: Component, attack_type: AttackType
    ) -> float:
        """Compute attack resistance (0-100) for a component against an attack."""
        defenses = _ATTACK_DEFENSE_MAP.get(attack_type, {})
        if not defenses:
            return 50.0  # unknown attack, assume moderate resistance

        sec = comp.security
        effectiveness = 0.0
        total_weight = 0.0

        for field_name, eff in defenses.items():
            total_weight += eff
            if getattr(sec, field_name, False):
                effectiveness += eff

        if total_weight == 0:
            return 50.0

        return (effectiveness / total_weight) * 100.0

    def _compute_failure_containment(
        self, comp: Component, failure_type: str
    ) -> float:
        """Compute failure containment (0-100) for a component."""
        score = 50.0  # base

        # Replicas improve containment
        if comp.replicas > 1:
            score += min(20.0, (comp.replicas - 1) * 10.0)

        # Failover improves containment
        if comp.failover.enabled:
            score += 15.0

        # Backup improves containment for disk/data failures
        if comp.security.backup_enabled and failure_type in ("disk_failure", "cascade_failure"):
            score += 10.0

        # Network segmentation limits blast radius
        if comp.security.network_segmented:
            score += 5.0

        return min(100.0, score)

    def _generate_recommendations(
        self,
        all_scores: list[tuple[CompoundScenario, SecurityResilienceScore]],
        surface_changes: list[AttackSurfaceChange],
    ) -> list[str]:
        """Generate recommendations based on simulation results."""
        recs: list[str] = []

        # Low overall resilience
        avg_overall = sum(s.overall_score for _, s in all_scores) / max(len(all_scores), 1)
        if avg_overall < 40:
            recs.append(
                "Overall security resilience is critically low. "
                "Prioritise enabling encryption, authentication, and network segmentation."
            )
        elif avg_overall < 60:
            recs.append(
                "Security resilience is below acceptable thresholds. "
                "Review compound failure scenarios and harden weak components."
            )

        # Large attack surface increases
        large_increases = [
            sc for sc in surface_changes if sc.increase_percent > 50
        ]
        if large_increases:
            ids = ", ".join(sc.component_id for sc in large_increases[:3])
            recs.append(
                f"Components with >50% attack surface increase during failures: {ids}. "
                "Add redundant security controls."
            )

        # High exposure windows
        high_exposure = [
            s for _, s in all_scores if s.exposure_window_minutes > 60
        ]
        if high_exposure:
            recs.append(
                f"{len(high_exposure)} scenario(s) have exposure windows exceeding 60 minutes. "
                "Reduce MTTR and enable automated failover."
            )

        if not recs:
            recs.append(
                "Security resilience is adequate. Continue monitoring and testing regularly."
            )

        return recs
