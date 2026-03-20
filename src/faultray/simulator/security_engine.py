# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Security Resilience Engine - simulates attack scenarios and evaluates defenses."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


class AttackType(str, Enum):
    DDOS_VOLUMETRIC = "ddos_volumetric"
    DDOS_APPLICATION = "ddos_application"
    CREDENTIAL_STUFFING = "credential_stuffing"
    SQL_INJECTION = "sql_injection"
    RANSOMWARE = "ransomware"
    SUPPLY_CHAIN = "supply_chain"
    INSIDER_THREAT = "insider_threat"
    ZERO_DAY = "zero_day"
    API_ABUSE = "api_abuse"
    DATA_EXFILTRATION = "data_exfiltration"


# Defense effectiveness matrix: maps (control, attack_type) -> mitigation (0-1).
# Only non-zero entries are stored.
_DEFENSE_MATRIX: dict[str, dict[AttackType, float]] = {
    "waf_protected": {
        AttackType.DDOS_APPLICATION: 0.80,
        AttackType.SQL_INJECTION: 0.90,
        AttackType.API_ABUSE: 0.70,
    },
    "rate_limiting": {
        AttackType.DDOS_VOLUMETRIC: 0.60,
        AttackType.CREDENTIAL_STUFFING: 0.80,
        AttackType.API_ABUSE: 0.85,
    },
    "encryption_at_rest": {
        AttackType.DATA_EXFILTRATION: 0.95,
        AttackType.RANSOMWARE: 0.30,
    },
    "encryption_in_transit": {
        AttackType.DATA_EXFILTRATION: 0.70,
    },
    "network_segmented": {
        # Applied as lateral-movement reduction rather than per-attack mitigation.
        # Handled specially in lateral movement logic.
    },
    "auth_required": {
        AttackType.CREDENTIAL_STUFFING: 0.50,
        AttackType.INSIDER_THREAT: 0.40,
    },
    "ids_monitored": {
        AttackType.ZERO_DAY: 0.30,
        AttackType.INSIDER_THREAT: 0.50,
    },
}

# Network segmentation reduces ALL lateral movement by this factor.
_SEGMENTATION_LATERAL_BLOCK = 0.70


@dataclass
class AttackSimulationResult:
    attack_type: AttackType
    entry_point: str
    compromised_components: list[str]
    blast_radius: int  # number of affected components
    defense_effectiveness: float  # 0-1, how much defenses mitigate
    estimated_downtime_minutes: float
    data_at_risk: bool
    mitigation_recommendations: list[str]


@dataclass
class SecurityReport:
    total_attacks_simulated: int
    attacks_fully_mitigated: int
    attacks_partially_mitigated: int
    attacks_unmitigated: int
    security_resilience_score: float  # 0-100
    worst_case_blast_radius: int
    results: list[AttackSimulationResult]
    score_breakdown: dict[str, float]


class SecurityResilienceEngine:
    """Simulates attack scenarios against an infrastructure graph and scores defenses."""

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate_attack(
        self, attack_type: AttackType, entry_point_id: str
    ) -> AttackSimulationResult:
        """Simulate a single attack of *attack_type* starting at *entry_point_id*."""
        entry = self.graph.get_component(entry_point_id)
        if entry is None:
            return AttackSimulationResult(
                attack_type=attack_type,
                entry_point=entry_point_id,
                compromised_components=[],
                blast_radius=0,
                defense_effectiveness=0.0,
                estimated_downtime_minutes=0.0,
                data_at_risk=False,
                mitigation_recommendations=[f"Component '{entry_point_id}' not found in graph."],
            )


        # 1. Defense effectiveness at the entry point
        defense = self._compute_defense_effectiveness(entry_point_id, attack_type)

        # 2. Lateral movement - BFS through dependencies
        compromised = self._compute_lateral_movement(entry_point_id, attack_type)

        # 3. Blast radius
        blast_radius = len(compromised)

        # 4. Data at risk?
        data_at_risk = any(
            self.graph.get_component(cid) is not None
            and self.graph.get_component(cid).type  # type: ignore[union-attr]
            in (ComponentType.DATABASE, ComponentType.STORAGE)
            for cid in compromised
        )

        # 5. Estimated downtime
        estimated_downtime = self._estimate_downtime(
            attack_type, blast_radius, defense, entry_point_id
        )

        # 6. Recommendations
        recommendations = self._generate_recommendations(
            entry_point_id, attack_type, compromised
        )

        return AttackSimulationResult(
            attack_type=attack_type,
            entry_point=entry_point_id,
            compromised_components=compromised,
            blast_radius=blast_radius,
            defense_effectiveness=defense,
            estimated_downtime_minutes=estimated_downtime,
            data_at_risk=data_at_risk,
            mitigation_recommendations=recommendations,
        )

    def simulate_all_attacks(self) -> SecurityReport:
        """Generate default attack scenarios from the graph and simulate all of them."""
        scenarios = self.generate_default_attack_scenarios()
        results: list[AttackSimulationResult] = []
        for attack_type, entry_point_id in scenarios:
            results.append(self.simulate_attack(attack_type, entry_point_id))

        fully = sum(1 for r in results if r.defense_effectiveness >= 0.8)
        partial = sum(1 for r in results if 0.3 <= r.defense_effectiveness < 0.8)
        unmitigated = sum(1 for r in results if r.defense_effectiveness < 0.3)
        worst_blast = max((r.blast_radius for r in results), default=0)
        score = self.security_resilience_score()
        breakdown = self._score_breakdown()

        return SecurityReport(
            total_attacks_simulated=len(results),
            attacks_fully_mitigated=fully,
            attacks_partially_mitigated=partial,
            attacks_unmitigated=unmitigated,
            security_resilience_score=score,
            worst_case_blast_radius=worst_blast,
            results=results,
            score_breakdown=breakdown,
        )

    def security_resilience_score(self) -> float:
        """Compute an overall security resilience score (0-100).

        Scoring categories (each 0-20, total 0-100):
        - encryption: encryption at rest + in transit coverage
        - access_control: auth + rate limiting coverage
        - network: network segmentation + WAF coverage
        - monitoring: logging + IDS coverage
        - recovery: backup enabled + backup frequency + patch SLA
        """
        breakdown = self._score_breakdown()
        total = sum(breakdown.values())
        return max(0.0, min(100.0, round(total, 1)))

    def generate_default_attack_scenarios(
        self,
    ) -> list[tuple[AttackType, str]]:
        """Auto-generate attack scenarios based on the graph topology.

        Rules:
        - Public-facing (port 443/80): DDoS volumetric, DDoS application, SQL injection, API abuse
        - Database components: SQL injection, data exfiltration, ransomware
        - No auth: credential stuffing
        - No segmentation: supply chain, insider threat
        """
        scenarios: list[tuple[AttackType, str]] = []
        seen: set[tuple[AttackType, str]] = set()

        def _add(at: AttackType, cid: str) -> None:
            key = (at, cid)
            if key not in seen:
                seen.add(key)
                scenarios.append(key)

        for comp in self.graph.components.values():
            # Public-facing components
            if comp.port in (443, 80):
                _add(AttackType.DDOS_VOLUMETRIC, comp.id)
                _add(AttackType.DDOS_APPLICATION, comp.id)
                _add(AttackType.SQL_INJECTION, comp.id)
                _add(AttackType.API_ABUSE, comp.id)

            # Database / storage
            if comp.type in (ComponentType.DATABASE, ComponentType.STORAGE):
                _add(AttackType.SQL_INJECTION, comp.id)
                _add(AttackType.DATA_EXFILTRATION, comp.id)
                _add(AttackType.RANSOMWARE, comp.id)

            # No auth
            if not comp.security.auth_required:
                _add(AttackType.CREDENTIAL_STUFFING, comp.id)

            # No segmentation
            if not comp.security.network_segmented:
                _add(AttackType.SUPPLY_CHAIN, comp.id)
                _add(AttackType.INSIDER_THREAT, comp.id)

        return scenarios

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_defense_effectiveness(
        self, component_id: str, attack_type: AttackType
    ) -> float:
        """Aggregate defense effectiveness at a component for a given attack type.

        Multiple controls combine via ``1 - product(1 - m_i)`` (independent layers).
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            return 0.0

        sec = comp.security
        mitigations: list[float] = []

        for control_name, attack_map in _DEFENSE_MATRIX.items():
            if attack_type not in attack_map:
                continue
            control_enabled = getattr(sec, control_name, False)
            if control_enabled:
                mitigations.append(attack_map[attack_type])

        # Network segmentation provides a blanket mitigation for lateral-movement
        # based attacks; add a small per-entry-point benefit too.
        if sec.network_segmented and attack_type in (
            AttackType.SUPPLY_CHAIN,
            AttackType.INSIDER_THREAT,
            AttackType.ZERO_DAY,
        ):
            mitigations.append(0.40)

        if not mitigations:
            return 0.0

        # Combine: 1 - prod(1 - m_i)
        product = 1.0
        for m in mitigations:
            product *= 1.0 - m
        return round(1.0 - product, 4)

    def _compute_lateral_movement(
        self, entry_point_id: str, attack_type: AttackType
    ) -> list[str]:
        """BFS lateral movement from *entry_point_id*.

        Network segmentation blocks traversal to segmented neighbours with
        probability ``_SEGMENTATION_LATERAL_BLOCK`` (deterministic cut-off for
        reproducibility: if the neighbour is segmented, it is NOT compromised).
        """
        compromised: list[str] = []
        visited: set[str] = set()
        queue: deque[str] = deque([entry_point_id])
        visited.add(entry_point_id)
        compromised.append(entry_point_id)

        while queue:
            current_id = queue.popleft()

            # Traverse both directions: things this component depends on,
            # and things that depend on this component.
            neighbours: list[str] = []
            for dep in self.graph.get_dependencies(current_id):
                neighbours.append(dep.id)
            for dep in self.graph.get_dependents(current_id):
                neighbours.append(dep.id)

            for nid in neighbours:
                if nid in visited:
                    continue
                visited.add(nid)

                neighbour = self.graph.get_component(nid)
                if neighbour is None:
                    continue

                # Network segmentation blocks lateral movement
                if neighbour.security.network_segmented:
                    continue

                compromised.append(nid)
                queue.append(nid)

        return compromised

    def _estimate_downtime(
        self,
        attack_type: AttackType,
        blast_radius: int,
        defense_effectiveness: float,
        entry_point_id: str,
    ) -> float:
        """Estimate downtime in minutes based on attack type and defenses."""
        entry = self.graph.get_component(entry_point_id)

        # Base downtime per attack type (minutes)
        base_downtime: dict[AttackType, float] = {
            AttackType.DDOS_VOLUMETRIC: 60.0,
            AttackType.DDOS_APPLICATION: 45.0,
            AttackType.CREDENTIAL_STUFFING: 30.0,
            AttackType.SQL_INJECTION: 120.0,
            AttackType.RANSOMWARE: 480.0,
            AttackType.SUPPLY_CHAIN: 240.0,
            AttackType.INSIDER_THREAT: 180.0,
            AttackType.ZERO_DAY: 360.0,
            AttackType.API_ABUSE: 30.0,
            AttackType.DATA_EXFILTRATION: 90.0,
        }

        dt = base_downtime.get(attack_type, 60.0)

        # Scale by blast radius (more components = longer recovery)
        total_components = max(len(self.graph.components), 1)
        blast_factor = max(1.0, blast_radius / total_components * 2.0)
        dt *= blast_factor

        # Reduce by defense effectiveness
        dt *= 1.0 - defense_effectiveness * 0.8

        # Backup reduces ransomware recovery
        if attack_type == AttackType.RANSOMWARE and entry is not None:
            if entry.security.backup_enabled:
                # Faster recovery based on backup frequency
                freq = entry.security.backup_frequency_hours
                recovery_factor = min(1.0, freq / 24.0)
                dt *= 0.3 + 0.7 * recovery_factor  # 30%-100% of original

        return round(max(0.0, dt), 1)

    def _generate_recommendations(
        self,
        entry_point_id: str,
        attack_type: AttackType,
        compromised: list[str],
    ) -> list[str]:
        """Generate actionable mitigation recommendations."""
        recommendations: list[str] = []
        entry = self.graph.get_component(entry_point_id)
        if entry is None:
            return recommendations

        sec = entry.security

        # General recommendations based on missing controls
        if not sec.waf_protected and attack_type in (
            AttackType.DDOS_APPLICATION,
            AttackType.SQL_INJECTION,
            AttackType.API_ABUSE,
        ):
            recommendations.append(
                f"Enable WAF on '{entry_point_id}' to mitigate {attack_type.value}."
            )

        if not sec.rate_limiting and attack_type in (
            AttackType.DDOS_VOLUMETRIC,
            AttackType.CREDENTIAL_STUFFING,
            AttackType.API_ABUSE,
        ):
            recommendations.append(
                f"Enable rate limiting on '{entry_point_id}' to mitigate {attack_type.value}."
            )

        if not sec.encryption_at_rest and attack_type in (
            AttackType.DATA_EXFILTRATION,
            AttackType.RANSOMWARE,
        ):
            recommendations.append(
                f"Enable encryption at rest on '{entry_point_id}' to protect data."
            )

        if not sec.encryption_in_transit and attack_type == AttackType.DATA_EXFILTRATION:
            recommendations.append(
                f"Enable encryption in transit on '{entry_point_id}' to prevent eavesdropping."
            )

        if not sec.auth_required and attack_type in (
            AttackType.CREDENTIAL_STUFFING,
            AttackType.INSIDER_THREAT,
        ):
            recommendations.append(
                f"Enforce authentication on '{entry_point_id}'."
            )

        if not sec.ids_monitored and attack_type in (
            AttackType.ZERO_DAY,
            AttackType.INSIDER_THREAT,
        ):
            recommendations.append(
                f"Enable IDS monitoring on '{entry_point_id}' for detection."
            )

        if not sec.backup_enabled and attack_type == AttackType.RANSOMWARE:
            recommendations.append(
                f"Enable backups on '{entry_point_id}' for ransomware recovery."
            )

        # Lateral movement recommendations
        unsegmented = [
            cid
            for cid in compromised
            if cid != entry_point_id
            and self.graph.get_component(cid) is not None
            and not self.graph.get_component(cid).security.network_segmented  # type: ignore[union-attr]
        ]
        if unsegmented:
            recommendations.append(
                f"Segment network for {len(unsegmented)} reachable component(s) "
                f"to limit lateral movement."
            )

        return recommendations

    def _score_breakdown(self) -> dict[str, float]:
        """Compute per-category scores (each 0-20, total 0-100)."""
        components = list(self.graph.components.values())
        n = len(components)
        if n == 0:
            return {
                "encryption": 0.0,
                "access_control": 0.0,
                "network": 0.0,
                "monitoring": 0.0,
                "recovery": 0.0,
            }

        # 1. Encryption (0-20): encryption_at_rest + encryption_in_transit
        enc_rest = sum(1 for c in components if c.security.encryption_at_rest) / n
        enc_transit = sum(1 for c in components if c.security.encryption_in_transit) / n
        encryption_score = (enc_rest * 10.0 + enc_transit * 10.0)

        # 2. Access control (0-20): auth_required + rate_limiting
        auth = sum(1 for c in components if c.security.auth_required) / n
        rate = sum(1 for c in components if c.security.rate_limiting) / n
        access_control_score = (auth * 10.0 + rate * 10.0)

        # 3. Network (0-20): network_segmented + waf_protected
        seg = sum(1 for c in components if c.security.network_segmented) / n
        waf = sum(1 for c in components if c.security.waf_protected) / n
        network_score = (seg * 10.0 + waf * 10.0)

        # 4. Monitoring (0-20): log_enabled + ids_monitored
        log = sum(1 for c in components if c.security.log_enabled) / n
        ids = sum(1 for c in components if c.security.ids_monitored) / n
        monitoring_score = (log * 10.0 + ids * 10.0)

        # 5. Recovery (0-20): backup_enabled + backup_frequency + patch_sla
        backup = sum(1 for c in components if c.security.backup_enabled) / n
        # Frequency: 1h = best (10), 24h = baseline (5), >168h = poor (0)
        freq_scores: list[float] = []
        for c in components:
            if c.security.backup_enabled:
                freq = c.security.backup_frequency_hours
                if freq <= 1:
                    freq_scores.append(10.0)
                elif freq <= 24:
                    freq_scores.append(5.0 + 5.0 * (1.0 - (freq - 1) / 23.0))
                elif freq <= 168:
                    freq_scores.append(5.0 * (1.0 - (freq - 24) / 144.0))
                else:
                    freq_scores.append(0.0)
            else:
                freq_scores.append(0.0)
        avg_freq = sum(freq_scores) / n if n > 0 else 0.0
        # Patch SLA: <=24h = best (5), 72h = baseline (3), >720h = poor (0)
        patch_scores: list[float] = []
        for c in components:
            sla = c.security.patch_sla_hours
            if sla <= 24:
                patch_scores.append(5.0)
            elif sla <= 72:
                patch_scores.append(3.0 + 2.0 * (1.0 - (sla - 24) / 48.0))
            elif sla <= 720:
                patch_scores.append(3.0 * (1.0 - (sla - 72) / 648.0))
            else:
                patch_scores.append(0.0)
        avg_patch = sum(patch_scores) / n if n > 0 else 0.0
        recovery_score = backup * 5.0 + avg_freq + avg_patch

        return {
            "encryption": round(encryption_score, 1),
            "access_control": round(access_control_score, 1),
            "network": round(network_score, 1),
            "monitoring": round(monitoring_score, 1),
            "recovery": round(recovery_score, 1),
        }
