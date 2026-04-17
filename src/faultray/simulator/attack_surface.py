# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Attack Surface Analyzer.

Maps the complete attack surface of infrastructure by identifying:
- External entry points (internet-facing components)
- Lateral movement paths (how an attacker could move between components)
- High-value targets (databases, secrets stores)
- Attack chains (sequences of exploits)
- Defense depth per attack path
- Blast radius of a security breach

This is different from the security_engine which scores defensive posture.
This module thinks like an attacker - what could they reach?
"""

from __future__ import annotations

import re as _re
from collections import deque
from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EntryPoint:
    """An externally-reachable component that could serve as an attack ingress."""

    component_id: str
    component_name: str
    exposure_type: str  # "internet", "internal_network", "vpn", "api"
    protocol: str  # "http", "https", "tcp", "grpc"
    attack_vectors: list[str] = field(default_factory=list)
    defense_score: float = 0.0  # 0-1, how well defended


@dataclass
class LateralMovePath:
    """A path an attacker could take from an entry point to a target."""

    source: str
    path: list[str] = field(default_factory=list)
    target: str = ""
    hops: int = 0
    defense_barriers: int = 0
    difficulty: str = "moderate"  # trivial/easy/moderate/hard/very_hard
    description: str = ""


@dataclass
class HighValueTarget:
    """A component that an attacker would prioritise compromising."""

    component_id: str
    component_name: str
    value_type: str  # "data_store", "auth_service", "payment", "pii", "secrets"
    risk_score: float = 0.0  # 0-10
    reachable_from: list[str] = field(default_factory=list)
    min_hops: int = 999
    defense_depth: int = 0


@dataclass
class AttackChain:
    """A named sequence of exploitation steps."""

    name: str = ""
    steps: list[tuple[str, str]] = field(default_factory=list)
    likelihood: str = "medium"  # high/medium/low
    impact: str = "medium"  # critical/high/medium/low
    mitigations: list[str] = field(default_factory=list)


@dataclass
class AttackSurfaceReport:
    """Complete attack surface analysis report."""

    entry_points: list[EntryPoint] = field(default_factory=list)
    lateral_paths: list[LateralMovePath] = field(default_factory=list)
    high_value_targets: list[HighValueTarget] = field(default_factory=list)
    attack_chains: list[AttackChain] = field(default_factory=list)
    total_attack_surface_score: float = 0.0  # 0-100, lower is better
    external_exposure: int = 0
    avg_defense_depth: float = 0.0
    weakest_path: LateralMovePath | None = None
    most_exposed_target: HighValueTarget | None = None
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise the report to a JSON-friendly dictionary."""
        return {
            "entry_points": [
                {
                    "component_id": ep.component_id,
                    "component_name": ep.component_name,
                    "exposure_type": ep.exposure_type,
                    "protocol": ep.protocol,
                    "attack_vectors": ep.attack_vectors,
                    "defense_score": round(ep.defense_score, 2),
                }
                for ep in self.entry_points
            ],
            "lateral_paths": [
                {
                    "source": lp.source,
                    "path": lp.path,
                    "target": lp.target,
                    "hops": lp.hops,
                    "defense_barriers": lp.defense_barriers,
                    "difficulty": lp.difficulty,
                    "description": lp.description,
                }
                for lp in self.lateral_paths
            ],
            "high_value_targets": [
                {
                    "component_id": ht.component_id,
                    "component_name": ht.component_name,
                    "value_type": ht.value_type,
                    "risk_score": round(ht.risk_score, 1),
                    "reachable_from": ht.reachable_from,
                    "min_hops": ht.min_hops,
                    "defense_depth": ht.defense_depth,
                }
                for ht in self.high_value_targets
            ],
            "attack_chains": [
                {
                    "name": ac.name,
                    "steps": [{"component": s[0], "action": s[1]} for s in ac.steps],
                    "likelihood": ac.likelihood,
                    "impact": ac.impact,
                    "mitigations": ac.mitigations,
                }
                for ac in self.attack_chains
            ],
            "total_attack_surface_score": round(self.total_attack_surface_score, 1),
            "external_exposure": self.external_exposure,
            "avg_defense_depth": round(self.avg_defense_depth, 1),
            "weakest_path": (
                {
                    "source": self.weakest_path.source,
                    "path": self.weakest_path.path,
                    "target": self.weakest_path.target,
                    "hops": self.weakest_path.hops,
                    "difficulty": self.weakest_path.difficulty,
                }
                if self.weakest_path
                else None
            ),
            "most_exposed_target": (
                {
                    "component_id": self.most_exposed_target.component_id,
                    "component_name": self.most_exposed_target.component_name,
                    "value_type": self.most_exposed_target.value_type,
                    "risk_score": round(self.most_exposed_target.risk_score, 1),
                }
                if self.most_exposed_target
                else None
            ),
            "recommendations": self.recommendations,
        }


# ---------------------------------------------------------------------------
# Constants for entry-point / target heuristics
# ---------------------------------------------------------------------------

_INTERNET_FACING_TYPES = {
    ComponentType.LOAD_BALANCER,
    ComponentType.DNS,
}

_EXTERNAL_TYPES = {
    ComponentType.EXTERNAL_API,
}

_INTERNET_FACING_NAME_TOKENS = {"public", "external", "api", "gateway", "cdn", "edge", "ingress"}
_HVT_DB_TYPE = {ComponentType.DATABASE}
_HVT_AUTH_TOKENS = {"auth", "identity", "login", "iam", "oauth", "sso"}
_HVT_PAYMENT_TOKENS = {"payment", "stripe", "billing", "checkout", "pay"}
_HVT_PII_TOKENS = {"user", "customer", "profile", "personal", "account"}
_HVT_SECRETS_TOKENS = {"secret", "vault", "kms", "key", "cert", "credential"}

_WORD_BOUNDARY_CACHE: dict[str, _re.Pattern] = {}


def _token_matches(token: str, text: str) -> bool:
    """Check if *token* appears in *text* as a whole word or delimited segment.

    Uses word-boundary regex so that 'sso' matches 'sso-proxy' but not
    'processor'.
    """
    pattern = _WORD_BOUNDARY_CACHE.get(token)
    if pattern is None:
        pattern = _re.compile(r'(?:^|[\W_])' + _re.escape(token) + r'(?:$|[\W_])')
        _WORD_BOUNDARY_CACHE[token] = pattern
    return pattern.search(text) is not None


_ATTACK_VECTORS_BY_TYPE = {
    ComponentType.LOAD_BALANCER: ["DDoS", "SSL stripping", "Request smuggling"],
    ComponentType.DNS: ["DNS spoofing", "DNS amplification", "Cache poisoning"],
    ComponentType.WEB_SERVER: ["XSS", "CSRF", "Directory traversal"],
    ComponentType.APP_SERVER: ["SQL injection", "RCE", "API abuse", "SSRF"],
    ComponentType.DATABASE: ["SQL injection", "Credential theft", "Data exfiltration"],
    ComponentType.CACHE: ["Cache poisoning", "Data leakage"],
    ComponentType.QUEUE: ["Message injection", "Queue flooding"],
    ComponentType.STORAGE: ["Data exfiltration", "Ransomware"],
    ComponentType.EXTERNAL_API: ["Supply chain attack", "API key theft", "Man-in-the-middle"],
    ComponentType.CUSTOM: ["Unknown vectors"],
}

_DIFFICULTY_THRESHOLDS = [
    # (max_barriers, difficulty)
    (0, "trivial"),
    (1, "easy"),
    (2, "moderate"),
    (4, "hard"),
    (999, "very_hard"),
]


def _classify_difficulty(barriers: int) -> str:
    for max_b, label in _DIFFICULTY_THRESHOLDS:
        if barriers <= max_b:
            return label
    return "very_hard"


def _defense_score_for_component(comp) -> float:
    """Calculate a 0-1 defense score from the SecurityProfile."""
    sec = comp.security
    controls = [
        sec.encryption_at_rest,
        sec.encryption_in_transit,
        sec.waf_protected,
        sec.rate_limiting,
        sec.auth_required,
        sec.network_segmented,
        sec.backup_enabled,
        sec.log_enabled,
        sec.ids_monitored,
    ]
    return sum(1 for c in controls if c) / max(len(controls), 1)


# ---------------------------------------------------------------------------
# AttackSurfaceAnalyzer
# ---------------------------------------------------------------------------


class AttackSurfaceAnalyzer:
    """Analyse the attack surface of an InfraGraph."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, graph: InfraGraph) -> AttackSurfaceReport:
        """Run the full attack-surface analysis and return a report."""
        entry_points = self.find_entry_points(graph)
        lateral_paths = self.find_lateral_paths(graph, entry_points)
        high_value_targets = self.find_high_value_targets(graph, entry_points, lateral_paths)
        attack_chains = self.generate_attack_chains(graph, entry_points, high_value_targets, lateral_paths)

        # Aggregate stats
        external_exposure = sum(1 for ep in entry_points if ep.exposure_type == "internet")

        # Average defense depth to high-value targets
        depths = [ht.defense_depth for ht in high_value_targets]
        avg_defense_depth = sum(depths) / max(len(depths), 1) if depths else 0.0

        # Weakest path = fewest barriers
        weakest_path: LateralMovePath | None = None
        if lateral_paths:
            weakest_path = min(lateral_paths, key=lambda p: p.defense_barriers)

        # Most exposed target = highest risk score
        most_exposed: HighValueTarget | None = None
        if high_value_targets:
            most_exposed = max(high_value_targets, key=lambda t: t.risk_score)

        # Attack surface score (0-100, lower is better)
        score = self._calculate_surface_score(
            entry_points, lateral_paths, high_value_targets, avg_defense_depth, graph
        )

        recommendations = self._generate_recommendations(
            entry_points, lateral_paths, high_value_targets, weakest_path, most_exposed
        )

        return AttackSurfaceReport(
            entry_points=entry_points,
            lateral_paths=lateral_paths,
            high_value_targets=high_value_targets,
            attack_chains=attack_chains,
            total_attack_surface_score=score,
            external_exposure=external_exposure,
            avg_defense_depth=avg_defense_depth,
            weakest_path=weakest_path,
            most_exposed_target=most_exposed,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Entry Point Detection
    # ------------------------------------------------------------------

    def find_entry_points(self, graph: InfraGraph) -> list[EntryPoint]:
        entry_points: list[EntryPoint] = []
        for comp in graph.components.values():
            exposure = self._classify_exposure(comp)
            if exposure is None:
                continue

            protocol = self._infer_protocol(comp)
            vectors = list(_ATTACK_VECTORS_BY_TYPE.get(comp.type, ["Unknown"]))
            defense = _defense_score_for_component(comp)

            entry_points.append(EntryPoint(
                component_id=comp.id,
                component_name=comp.name,
                exposure_type=exposure,
                protocol=protocol,
                attack_vectors=vectors,
                defense_score=defense,
            ))

        return entry_points

    # ------------------------------------------------------------------
    # Lateral Movement
    # ------------------------------------------------------------------

    def find_lateral_paths(
        self,
        graph: InfraGraph,
        entry_points: list[EntryPoint] | None = None,
    ) -> list[LateralMovePath]:
        if entry_points is None:
            entry_points = self.find_entry_points(graph)

        paths: list[LateralMovePath] = []
        {ep.component_id for ep in entry_points}

        for ep in entry_points:
            # BFS from entry point following dependency edges (both directions for reachability)
            visited: set[str] = set()
            queue: deque[tuple[str, list[str]]] = deque()
            queue.append((ep.component_id, [ep.component_id]))
            visited.add(ep.component_id)

            while queue:
                current, path = queue.popleft()
                # Follow forward dependencies (what this component depends on)
                for dep_comp in graph.get_dependencies(current):
                    if dep_comp.id not in visited:
                        visited.add(dep_comp.id)
                        new_path = path + [dep_comp.id]
                        barriers = self.calculate_defense_depth(graph, ep.component_id, dep_comp.id, new_path)
                        difficulty = _classify_difficulty(barriers)

                        lmp = LateralMovePath(
                            source=ep.component_id,
                            path=new_path,
                            target=dep_comp.id,
                            hops=len(new_path) - 1,
                            defense_barriers=barriers,
                            difficulty=difficulty,
                            description=f"{ep.component_name} -> {dep_comp.name} ({len(new_path) - 1} hops)",
                        )
                        paths.append(lmp)
                        queue.append((dep_comp.id, new_path))

                # Also follow dependents (reverse edges: who depends on this)
                for dep_comp in graph.get_dependents(current):
                    if dep_comp.id not in visited:
                        visited.add(dep_comp.id)
                        new_path = path + [dep_comp.id]
                        barriers = self.calculate_defense_depth(graph, ep.component_id, dep_comp.id, new_path)
                        difficulty = _classify_difficulty(barriers)

                        lmp = LateralMovePath(
                            source=ep.component_id,
                            path=new_path,
                            target=dep_comp.id,
                            hops=len(new_path) - 1,
                            defense_barriers=barriers,
                            difficulty=difficulty,
                            description=f"{ep.component_name} -> {dep_comp.name} ({len(new_path) - 1} hops)",
                        )
                        paths.append(lmp)
                        queue.append((dep_comp.id, new_path))

        return paths

    # ------------------------------------------------------------------
    # High-Value Targets
    # ------------------------------------------------------------------

    def find_high_value_targets(
        self,
        graph: InfraGraph,
        entry_points: list[EntryPoint] | None = None,
        lateral_paths: list[LateralMovePath] | None = None,
    ) -> list[HighValueTarget]:
        if entry_points is None:
            entry_points = self.find_entry_points(graph)
        if lateral_paths is None:
            lateral_paths = self.find_lateral_paths(graph, entry_points)

        targets: list[HighValueTarget] = []

        for comp in graph.components.values():
            value_type = self._classify_value(comp)
            if value_type is None:
                continue

            # Find which entry points can reach this target
            reachable_from: list[str] = []
            min_hops = 999
            min_defense_depth = 999

            for lp in lateral_paths:
                if lp.target == comp.id:
                    if lp.source not in reachable_from:
                        reachable_from.append(lp.source)
                    if lp.hops < min_hops:
                        min_hops = lp.hops
                    if lp.defense_barriers < min_defense_depth:
                        min_defense_depth = lp.defense_barriers

            # Risk score: higher when easily reachable from many entry points
            risk_score = self._calculate_target_risk(
                comp, reachable_from, min_hops, min_defense_depth
            )

            targets.append(HighValueTarget(
                component_id=comp.id,
                component_name=comp.name,
                value_type=value_type,
                risk_score=risk_score,
                reachable_from=reachable_from,
                min_hops=min_hops if min_hops < 999 else 0,
                defense_depth=min_defense_depth if min_defense_depth < 999 else 0,
            ))

        return targets

    # ------------------------------------------------------------------
    # Attack Chains
    # ------------------------------------------------------------------

    def generate_attack_chains(
        self,
        graph: InfraGraph,
        entry_points: list[EntryPoint] | None = None,
        high_value_targets: list[HighValueTarget] | None = None,
        lateral_paths: list[LateralMovePath] | None = None,
    ) -> list[AttackChain]:
        if entry_points is None:
            entry_points = self.find_entry_points(graph)
        if high_value_targets is None:
            high_value_targets = self.find_high_value_targets(graph, entry_points)
        if lateral_paths is None:
            lateral_paths = self.find_lateral_paths(graph, entry_points)

        chains: list[AttackChain] = []
        {ep.component_id for ep in entry_points}
        {ht.component_id for ht in high_value_targets}
        {ht.component_id: ht for ht in high_value_targets}

        # 1. External to Database chain
        db_targets = [ht for ht in high_value_targets if ht.value_type == "data_store"]
        for db in db_targets:
            for ep_id in db.reachable_from:
                ep_comp = graph.get_component(ep_id)
                db_comp = graph.get_component(db.component_id)
                if ep_comp and db_comp:
                    chains.append(AttackChain(
                        name="External to Database",
                        steps=[
                            (ep_comp.name, "Exploit entry point"),
                            ("intermediate", "Lateral movement through services"),
                            (db_comp.name, "Access database / exfiltrate data"),
                        ],
                        likelihood="high" if db.min_hops <= 2 else "medium",
                        impact="critical",
                        mitigations=[
                            "Add network segmentation between tiers",
                            "Enable encryption at rest on database",
                            "Implement database activity monitoring",
                            "Use prepared statements / parameterised queries",
                        ],
                    ))
                    break  # One chain per DB target is enough

        # 2. Supply Chain Attack
        ext_apis = [
            c for c in graph.components.values()
            if c.type == ComponentType.EXTERNAL_API
        ]
        for ext in ext_apis:
            dependents = graph.get_dependents(ext.id)
            if dependents:
                steps = [
                    (ext.name, "Compromise external dependency"),
                ]
                for dep in dependents[:2]:
                    steps.append((dep.name, "Propagate malicious payload"))
                # Find if any HVT is downstream
                for ht in high_value_targets:
                    if ht.component_id in {d.id for d in dependents}:
                        steps.append((ht.component_name, f"Reach {ht.value_type}"))
                        break

                chains.append(AttackChain(
                    name="Supply Chain Attack",
                    steps=steps,
                    likelihood="medium",
                    impact="high",
                    mitigations=[
                        "Implement dependency pinning and verification",
                        "Monitor external API behaviour for anomalies",
                        "Apply circuit breakers on external dependencies",
                        "Use allow-list for expected API responses",
                    ],
                ))

        # 3. Privilege Escalation
        auth_targets = [ht for ht in high_value_targets if ht.value_type == "auth_service"]
        for auth in auth_targets:
            for ep_id in auth.reachable_from:
                ep_comp = graph.get_component(ep_id)
                auth_comp = graph.get_component(auth.component_id)
                if ep_comp and auth_comp:
                    chains.append(AttackChain(
                        name="Privilege Escalation",
                        steps=[
                            (ep_comp.name, "Gain initial low-privilege access"),
                            (auth_comp.name, "Exploit auth service for elevated privileges"),
                            ("admin", "Access administrative functions"),
                        ],
                        likelihood="medium" if auth.defense_depth >= 2 else "high",
                        impact="critical",
                        mitigations=[
                            "Enforce least-privilege access controls",
                            "Implement multi-factor authentication",
                            "Add anomaly detection on privilege changes",
                            "Regularly audit access permissions",
                        ],
                    ))
                    break

        # 4. Data Exfiltration
        pii_targets = [ht for ht in high_value_targets if ht.value_type in ("pii", "data_store")]
        for pii in pii_targets[:2]:
            for ep_id in pii.reachable_from[:1]:
                ep_comp = graph.get_component(ep_id)
                pii_comp = graph.get_component(pii.component_id)
                if ep_comp and pii_comp:
                    chains.append(AttackChain(
                        name="Data Exfiltration",
                        steps=[
                            (ep_comp.name, "Compromise entry point"),
                            (pii_comp.name, "Access data store"),
                            ("exfil", "Exfiltrate data via side channel"),
                        ],
                        likelihood="medium",
                        impact="critical" if pii.value_type == "pii" else "high",
                        mitigations=[
                            "Enable data loss prevention (DLP)",
                            "Monitor egress traffic for anomalies",
                            "Encrypt sensitive data at rest",
                            "Implement data access audit logging",
                        ],
                    ))
                    break

        return chains

    # ------------------------------------------------------------------
    # Defense Depth Calculation
    # ------------------------------------------------------------------

    def calculate_defense_depth(
        self,
        graph: InfraGraph,
        source: str,
        target: str,
        path: list[str] | None = None,
    ) -> int:
        """Count defense barriers along a path between source and target."""
        if path is None:
            path = [source, target]

        barriers = 0
        for i, node_id in enumerate(path):
            comp = graph.get_component(node_id)
            if comp is None:
                continue

            # Count security controls as barriers
            sec = comp.security
            if sec.auth_required:
                barriers += 1
            if sec.network_segmented:
                barriers += 1
            if sec.waf_protected and i == 0:
                barriers += 1

            # Check circuit breakers on edges entering this component
            if i > 0:
                prev_id = path[i - 1]
                edge = graph.get_dependency_edge(prev_id, node_id)
                if edge is None:
                    edge = graph.get_dependency_edge(node_id, prev_id)
                if edge and edge.circuit_breaker.enabled:
                    barriers += 1

        return barriers

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_exposure(comp) -> str | None:
        """Determine if a component is externally exposed and how."""
        name_lower = comp.name.lower()
        id_lower = comp.id.lower()
        combined = name_lower + " " + id_lower

        if comp.type in _INTERNET_FACING_TYPES:
            return "internet"
        if comp.type in _EXTERNAL_TYPES:
            return "api"
        if any(_token_matches(tok, combined) for tok in _INTERNET_FACING_NAME_TOKENS):
            return "internet"
        return None

    @staticmethod
    def _infer_protocol(comp) -> str:
        port = comp.port
        if port == 443:
            return "https"
        if port in (80, 8080, 8000, 3000):
            return "http"
        if port == 0:
            return "https"  # default assumption for modern infra
        return "tcp"

    @staticmethod
    def _classify_value(comp) -> str | None:
        """Classify whether a component is a high-value target."""
        name_lower = comp.name.lower()
        id_lower = comp.id.lower()
        combined = name_lower + " " + id_lower

        if comp.type in _HVT_DB_TYPE:
            return "data_store"
        # Check payment before auth because some payment names could
        # accidentally match short auth tokens (e.g., "sso" in "processor").
        if any(_token_matches(tok, combined) for tok in _HVT_PAYMENT_TOKENS):
            return "payment"
        if any(_token_matches(tok, combined) for tok in _HVT_AUTH_TOKENS):
            return "auth_service"
        if any(_token_matches(tok, combined) for tok in _HVT_SECRETS_TOKENS):
            return "secrets"
        if any(_token_matches(tok, combined) for tok in _HVT_PII_TOKENS):
            return "pii"
        return None

    @staticmethod
    def _calculate_target_risk(
        comp, reachable_from: list[str], min_hops: int, min_defense_depth: int
    ) -> float:
        """Calculate risk score (0-10) for a high-value target."""
        score = 5.0  # base risk

        # More entry points that can reach it -> higher risk
        score += min(3.0, len(reachable_from) * 0.75)

        # Fewer hops -> higher risk
        if min_hops <= 1:
            score += 2.0
        elif min_hops <= 2:
            score += 1.0

        # Fewer defense barriers -> higher risk
        if min_defense_depth == 0:
            score += 2.0
        elif min_defense_depth == 1:
            score += 1.0

        # Own defense score reduces risk
        own_defense = _defense_score_for_component(comp)
        score -= own_defense * 3.0

        return max(0.0, min(10.0, score))

    @staticmethod
    def _calculate_surface_score(
        entry_points: list[EntryPoint],
        lateral_paths: list[LateralMovePath],
        high_value_targets: list[HighValueTarget],
        avg_defense_depth: float,
        graph: InfraGraph,
    ) -> float:
        """Calculate total attack surface score (0-100, lower is better)."""
        if not graph.components:
            return 0.0

        score = 0.0
        total_components = len(graph.components)

        # Entry point exposure (0-30)
        internet_count = sum(1 for ep in entry_points if ep.exposure_type == "internet")
        exposure_ratio = internet_count / max(total_components, 1)
        score += min(30.0, exposure_ratio * 100)

        # Easy lateral paths (0-30)
        easy_paths = sum(1 for lp in lateral_paths if lp.difficulty in ("trivial", "easy"))
        path_ratio = easy_paths / max(len(lateral_paths), 1) if lateral_paths else 0
        score += path_ratio * 30

        # Reachable high-value targets (0-25)
        reachable_hvt = sum(1 for ht in high_value_targets if len(ht.reachable_from) > 0)
        hvt_ratio = reachable_hvt / max(len(high_value_targets), 1) if high_value_targets else 0
        score += hvt_ratio * 25

        # Low defense depth penalty (0-15)
        if avg_defense_depth < 1:
            score += 15
        elif avg_defense_depth < 2:
            score += 10
        elif avg_defense_depth < 3:
            score += 5

        return max(0.0, min(100.0, score))

    @staticmethod
    def _generate_recommendations(
        entry_points: list[EntryPoint],
        lateral_paths: list[LateralMovePath],
        high_value_targets: list[HighValueTarget],
        weakest_path: LateralMovePath | None,
        most_exposed: HighValueTarget | None,
    ) -> list[str]:
        recs: list[str] = []

        # Weak entry points
        weak_eps = [ep for ep in entry_points if ep.defense_score < 0.4]
        if weak_eps:
            names = ", ".join(ep.component_name for ep in weak_eps[:3])
            recs.append(
                f"Harden entry points with low defense scores: {names}. "
                "Add WAF, rate limiting, and authentication."
            )

        # Trivial paths
        trivial = [lp for lp in lateral_paths if lp.difficulty in ("trivial", "easy")]
        if trivial:
            recs.append(
                f"{len(trivial)} lateral movement paths have trivial/easy difficulty. "
                "Add network segmentation and authentication barriers."
            )

        # Weakest path
        if weakest_path and weakest_path.defense_barriers == 0:
            recs.append(
                f"Path from {weakest_path.source} to {weakest_path.target} has zero defense barriers. "
                "Add circuit breakers, auth requirements, or network segmentation."
            )

        # Most exposed target
        if most_exposed and most_exposed.risk_score >= 7:
            recs.append(
                f"High-value target '{most_exposed.component_name}' ({most_exposed.value_type}) "
                f"has risk score {most_exposed.risk_score:.1f}/10. "
                "Reduce exposure by adding defense layers or limiting reachability."
            )

        # HVTs with no defense
        undefended = [ht for ht in high_value_targets if ht.defense_depth == 0 and len(ht.reachable_from) > 0]
        if undefended:
            names = ", ".join(ht.component_name for ht in undefended[:3])
            recs.append(
                f"High-value targets with zero defense depth: {names}. "
                "These are directly reachable from entry points with no barriers."
            )

        if not recs:
            recs.append("Attack surface is well-defended. Continue monitoring for new exposure.")

        return recs
