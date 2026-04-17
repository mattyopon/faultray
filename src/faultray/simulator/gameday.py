# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""GameDay Scenario Generator — auto-generate realistic quarterly GameDay scenarios.

Analyses the infrastructure topology to find the most vulnerable component
combinations and produces ready-to-run GameDay exercise plans with preparation
steps, execution steps, observation points, recovery steps, and go/no-go criteria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain
from faultray.simulator.engine import SimulationEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class GameDayScenario:
    """A single GameDay exercise scenario."""

    scenario_id: str                    # GD-001
    title: str                          # "Primary Database Failover"
    description: str                    # Detailed explanation
    difficulty: str                     # easy / medium / hard
    category: str                       # single_failure / cascade / multi_region /
                                        # data_loss / network_partition /
                                        # load_surge / cache_flush

    # Fault definition
    trigger_components: list[str] = field(default_factory=list)
    failure_mode: str = "crash"         # crash / degraded / network_partition /
                                        # data_corruption / load_surge

    # Expected impact
    affected_components: list[str] = field(default_factory=list)
    cascade_depth: int = 0
    estimated_impact_score: float = 0.0  # 0-100
    estimated_mttr_minutes: float = 30.0
    affected_users_pct: float = 0.0

    # Test procedure
    preparation_steps: list[str] = field(default_factory=list)
    execution_steps: list[str] = field(default_factory=list)
    observation_points: list[str] = field(default_factory=list)
    recovery_steps: list[str] = field(default_factory=list)

    # Pass/fail criteria
    success_criteria: list[str] = field(default_factory=list)
    failure_indicators: list[str] = field(default_factory=list)
    slo_impact: str = ""

    # Recommendations
    pre_gameday_checks: list[str] = field(default_factory=list)
    rollback_plan: str = ""


# ---------------------------------------------------------------------------
# Step templates
# ---------------------------------------------------------------------------

_PREP_COMMON = [
    "Notify on-call team and stakeholders of GameDay window.",
    "Enable enhanced monitoring and alert silencing for the test window.",
    "Confirm rollback runbook is accessible to all participants.",
    "Verify staging environment baseline health (all green).",
]

_OBS_COMMON = [
    "Application error rate (target: < 1% baseline).",
    "Latency p99 on critical endpoints.",
    "Alert firing rate and on-call notification latency.",
    "Log stream for cascading error messages.",
]

# (ComponentType.value, failure_mode) -> execution step list
_EXECUTION_TEMPLATES: dict[tuple[str, str], list[str]] = {
    ("database", "crash"): [
        "Identify the primary database instance in the topology.",
        "Execute controlled shutdown: `sudo systemctl stop postgresql` (or equivalent).",
        "Start the MTTR stopwatch.",
        "Monitor replica promotion (expected: automatic within failover_timeout seconds).",
        "Verify application reconnection to the new primary.",
        "Confirm write traffic is accepted by the promoted replica.",
    ],
    ("database", "network_partition"): [
        "Identify the network segment hosting the primary database.",
        "Apply iptables rules to drop traffic: `iptables -A INPUT -s <db_ip> -j DROP`.",
        "Start the MTTR stopwatch.",
        "Observe split-brain detection and quorum behaviour.",
        "Verify application falls back to read replica or returns 503 gracefully.",
        "Remove iptables rules to restore connectivity.",
    ],
    ("database", "data_corruption"): [
        "Snapshot the database before test for rollback.",
        "Introduce a controlled data anomaly on a test table.",
        "Start the MTTR stopwatch.",
        "Trigger integrity checks and verify alerts fire.",
        "Restore from snapshot and verify data consistency.",
    ],
    ("load_balancer", "crash"): [
        "Identify the active load balancer instance.",
        "Stop the LB process: `sudo systemctl stop nginx` (or equivalent).",
        "Start the MTTR stopwatch.",
        "Observe traffic failover to the standby LB.",
        "Verify DNS update or floating-IP reassignment completes.",
        "Confirm all upstream health checks pass on the standby.",
    ],
    ("load_balancer", "degraded"): [
        "Simulate 50% packet loss on the LB interface: `tc qdisc add dev eth0 root netem loss 50%`.",
        "Start the MTTR stopwatch.",
        "Monitor traffic distribution to backend instances.",
        "Verify circuit breakers trip appropriately.",
        "Remove tc rules: `tc qdisc del dev eth0 root`.",
    ],
    ("app_server", "crash"): [
        "Identify a subset of app server instances (start with 1 of N).",
        "Kill the application process: `kill -9 <pid>` or stop the container.",
        "Start the MTTR stopwatch.",
        "Monitor LB health check detection (expected: within health_check_interval).",
        "Verify remaining instances absorb traffic without error spike.",
        "Restart the killed instance and verify it rejoins the pool.",
    ],
    ("app_server", "load_surge"): [
        "Prepare load test tool (k6, locust, or wrk) targeting the application.",
        "Ramp traffic to 2x nominal RPS over 5 minutes.",
        "Start the MTTR stopwatch.",
        "Monitor autoscaler response time and new instance readiness.",
        "Observe whether queue depth or latency exceeds SLO thresholds.",
        "Ramp traffic back down and verify scale-down cooldown behaviour.",
    ],
    ("cache", "crash"): [
        "Identify the primary cache node.",
        "Stop the cache service: `sudo systemctl stop redis` (or equivalent).",
        "Start the MTTR stopwatch.",
        "Monitor cache-miss rate spike and DB query load increase.",
        "Verify application degrades gracefully (no hard errors).",
        "Restart cache and verify warm-up latency is acceptable.",
    ],
    ("cache", "data_corruption"): [
        "Select a small key namespace for corruption.",
        "Flush only that namespace: `redis-cli DEL <key_pattern*>`.",
        "Observe cache stampede behaviour and DB saturation.",
        "Verify single-flight or request-coalescing protection kicks in.",
    ],
    ("queue", "crash"): [
        "Identify the message broker primary node.",
        "Stop the broker: `sudo systemctl stop rabbitmq-server` (or equivalent).",
        "Start the MTTR stopwatch.",
        "Monitor producer backpressure and consumer lag metrics.",
        "Verify messages are durably queued and not lost after restart.",
        "Restart the broker and confirm consumers resume processing.",
    ],
    ("dns", "crash"): [
        "Identify the internal DNS resolver(s).",
        "Block DNS port 53 traffic: `iptables -A OUTPUT -p udp --dport 53 -j DROP`.",
        "Start the MTTR stopwatch.",
        "Monitor new connection establishment failures.",
        "Verify applications that cache DNS records survive longer.",
        "Restore DNS and observe resolution recovery time.",
    ],
    ("external_api", "degraded"): [
        "Identify all consumer services for this external dependency.",
        "Inject simulated 2000ms latency on the outbound path via proxy or tc.",
        "Start the MTTR stopwatch.",
        "Monitor timeout escalation and circuit breaker state changes.",
        "Verify graceful degradation: feature toggle or fallback response.",
        "Remove latency injection and verify circuit breaker recovery.",
    ],
}

_RECOVERY_TEMPLATES: dict[str, list[str]] = {
    "crash": [
        "Restart the failed component and confirm it rejoins healthy state.",
        "Verify all dependent services have reconnected.",
        "Confirm no data loss by running integrity checks.",
        "Review post-incident metrics for anomalies.",
    ],
    "degraded": [
        "Remove the injected network impairment (tc qdisc / iptables rules).",
        "Confirm latency and error rate return to baseline.",
        "Review circuit breaker state — ensure CLOSED before marking done.",
    ],
    "network_partition": [
        "Remove firewall rules that created the partition.",
        "Confirm all nodes have re-joined the cluster.",
        "Verify no split-brain state persists.",
        "Review consensus logs for unexpected elections.",
    ],
    "data_corruption": [
        "Restore from the pre-test snapshot.",
        "Run full data integrity checks.",
        "Verify checksums / hashes on critical tables.",
        "Confirm audit logs captured the anomaly.",
    ],
    "load_surge": [
        "Ramp traffic back to nominal.",
        "Verify autoscaler scale-down cooldown completes.",
        "Confirm no runaway processes or leaked connections.",
    ],
    "cache_flush": [
        "Allow cache to warm up organically or trigger pre-warm job.",
        "Monitor DB query rate returning to baseline.",
        "Verify p99 latency normalises within SLO.",
    ],
}


def _get_execution_steps(comp_type: str, failure_mode: str) -> list[str]:
    """Return execution steps for a component type and failure mode."""
    key = (comp_type, failure_mode)
    if key in _EXECUTION_TEMPLATES:
        return list(_EXECUTION_TEMPLATES[key])
    # Fallback generic steps
    return [
        f"Identify the target component: {comp_type}.",
        f"Apply failure mode '{failure_mode}' using the appropriate tool.",
        "Start the MTTR stopwatch.",
        "Observe system behaviour and record metrics.",
        "Verify dependent components respond as expected.",
        "Restore the component to healthy state.",
    ]


def _get_recovery_steps(failure_mode: str) -> list[str]:
    """Return recovery steps for a failure mode."""
    return list(_RECOVERY_TEMPLATES.get(failure_mode, _RECOVERY_TEMPLATES["crash"]))


def _build_success_criteria(
    trigger_ids: list[str],
    affected_ids: list[str],
    failure_mode: str,
    has_failover: bool,
    mttr_minutes: float,
) -> list[str]:
    criteria = []
    if has_failover:
        criteria.append(
            f"Automatic failover completes within {int(mttr_minutes * 0.5)} minutes."
        )
    criteria.append(
        f"Full service restoration (MTTR) achieved within {int(mttr_minutes)} minutes."
    )
    criteria.append("No unplanned data loss or corruption detected.")
    criteria.append("All monitoring alerts fired and on-call was notified within 5 minutes.")
    if len(affected_ids) > 2:
        criteria.append("Cascading impact contained — less than 50% of services affected.")
    return criteria


def _build_failure_indicators(
    trigger_ids: list[str],
    failure_mode: str,
    estimated_mttr_minutes: float,
) -> list[str]:
    indicators = [
        f"MTTR exceeds {int(estimated_mttr_minutes * 2)} minutes.",
        "No automatic recovery or failover observed — manual intervention required immediately.",
        "Data loss or corruption detected after recovery.",
        "On-call alert not received within 10 minutes of fault injection.",
    ]
    if failure_mode in ("data_corruption",):
        indicators.append("Integrity check reports inconsistencies after recovery.")
    if failure_mode in ("network_partition",):
        indicators.append("Split-brain condition persists after partition healed.")
    return indicators


# ---------------------------------------------------------------------------
# Scoring utilities
# ---------------------------------------------------------------------------


def _spof_score(comp: Component, graph: InfraGraph) -> float:
    """Heuristic SPOF score: higher = more dangerous if this component fails.

    Factors:
    - Number of direct dependents (upstream components that need it)
    - Single replica with no failover
    - Component type criticality weight
    """
    dependents = graph.get_dependents(comp.id)
    dependent_count = len(dependents)

    is_spof = comp.replicas <= 1 and not comp.failover.enabled
    spof_weight = 2.0 if is_spof else 1.0

    type_weights: dict[ComponentType, float] = {
        ComponentType.DATABASE: 3.0,
        ComponentType.DNS: 3.0,
        ComponentType.LOAD_BALANCER: 2.5,
        ComponentType.QUEUE: 2.0,
        ComponentType.CACHE: 1.5,
        ComponentType.APP_SERVER: 1.2,
        ComponentType.WEB_SERVER: 1.2,
        ComponentType.STORAGE: 1.8,
        ComponentType.EXTERNAL_API: 1.5,
        ComponentType.AGENT_ORCHESTRATOR: 2.0,
    }
    type_w = type_weights.get(comp.type, 1.0)

    return (dependent_count + 1) * spof_weight * type_w


def _cascade_depth(chain: CascadeChain) -> int:
    """Estimate cascade depth from a CascadeChain."""
    return len({e.component_id for e in chain.effects})


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


class GameDayGenerator:
    """Generate quarterly GameDay exercise scenarios from an InfraGraph.

    Uses the existing SimulationEngine to run all single-fault and
    multi-fault scenarios, then ranks results by impact score and selects
    a diverse set covering different scenario categories.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._engine = SimulationEngine(graph)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_scenarios(
        self,
        count: int = 5,
        difficulty: str = "medium",
    ) -> list[GameDayScenario]:
        """Generate a ranked list of GameDay scenarios.

        Parameters
        ----------
        count:
            Number of scenarios to return.
        difficulty:
            ``easy``, ``medium``, or ``hard``.  Controls which scenario
            categories are included and minimum cascade depth.

        Returns
        -------
        list[GameDayScenario]
            Scenarios sorted by estimated impact score descending.
        """
        difficulty = difficulty.lower()
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"

        # 1. Enumerate candidate scenarios for the difficulty level
        candidates = self._build_candidate_scenarios(difficulty)

        # 2. Run simulation and score each candidate
        scored: list[tuple[float, GameDayScenario]] = []
        for scenario in candidates:
            gd = self._evaluate_candidate(scenario, difficulty)
            if gd is not None:
                scored.append((gd.estimated_impact_score, gd))

        # 3. Sort by score descending
        scored.sort(key=lambda t: t[0], reverse=True)

        # 4. Select diverse scenarios (no duplicate categories if possible)
        selected = self._select_diverse(scored, count)

        # 5. Assign sequential IDs
        for idx, sc in enumerate(selected, start=1):
            sc.scenario_id = f"GD-{idx:03d}"

        return selected

    # ------------------------------------------------------------------
    # Internal — candidate generation
    # ------------------------------------------------------------------

    def _build_candidate_scenarios(self, difficulty: str) -> list[Scenario]:
        """Build Scenario objects to simulate based on difficulty."""
        comps = self.graph.components
        scenarios: list[Scenario] = []

        # --- Easy: single component with failover, cache flush, single AZ ---
        if difficulty in ("easy", "medium", "hard"):
            for cid, comp in comps.items():
                scenarios.append(Scenario(
                    id=f"single-{cid}",
                    name=f"Single failure: {comp.name}",
                    description=f"Complete failure of {comp.name}",
                    faults=[Fault(
                        target_component_id=cid,
                        fault_type=FaultType.COMPONENT_DOWN,
                        severity=1.0,
                    )],
                ))
            # Cache flush
            for cid, comp in comps.items():
                if comp.type == ComponentType.CACHE:
                    scenarios.append(Scenario(
                        id=f"cache-flush-{cid}",
                        name=f"Cache flush: {comp.name}",
                        description=f"Full cache eviction on {comp.name}",
                        faults=[Fault(
                            target_component_id=cid,
                            fault_type=FaultType.MEMORY_EXHAUSTION,
                            severity=0.8,
                        )],
                    ))

        # --- Medium: SPOF failures, cascades, load surge ---
        if difficulty in ("medium", "hard"):
            for cid, comp in comps.items():
                if comp.replicas <= 1 and not comp.failover.enabled:
                    # SPOF scenario
                    scenarios.append(Scenario(
                        id=f"spof-{cid}",
                        name=f"SPOF failure: {comp.name}",
                        description=f"Single point of failure — no redundancy on {comp.name}",
                        faults=[Fault(
                            target_component_id=cid,
                            fault_type=FaultType.COMPONENT_DOWN,
                            severity=1.0,
                        )],
                    ))
            # Load surge
            for cid, comp in comps.items():
                if comp.type in (ComponentType.APP_SERVER, ComponentType.WEB_SERVER,
                                 ComponentType.LOAD_BALANCER):
                    scenarios.append(Scenario(
                        id=f"surge-{cid}",
                        name=f"Traffic surge: {comp.name}",
                        description=f"2x traffic load on {comp.name}",
                        faults=[Fault(
                            target_component_id=cid,
                            fault_type=FaultType.TRAFFIC_SPIKE,
                            severity=0.9,
                        )],
                        traffic_multiplier=2.0,
                    ))
            # Network partition on databases
            for cid, comp in comps.items():
                if comp.type == ComponentType.DATABASE:
                    scenarios.append(Scenario(
                        id=f"netpart-{cid}",
                        name=f"Network partition: {comp.name}",
                        description=f"Network partition isolating {comp.name}",
                        faults=[Fault(
                            target_component_id=cid,
                            fault_type=FaultType.NETWORK_PARTITION,
                            severity=1.0,
                        )],
                    ))

        # --- Hard: compound failures, multi-component, data corruption ---
        if difficulty == "hard":
            # Compound: two critical components fail simultaneously
            critical_types = {
                ComponentType.DATABASE, ComponentType.LOAD_BALANCER,
                ComponentType.QUEUE, ComponentType.DNS,
            }
            critical_ids = [
                cid for cid, comp in comps.items()
                if comp.type in critical_types
            ]
            for a, b in combinations(critical_ids[:8], 2):  # cap at 28 combos
                scenarios.append(Scenario(
                    id=f"compound-{a}-{b}",
                    name=f"Compound failure: {comps[a].name} + {comps[b].name}",
                    description=(
                        f"Simultaneous failure of {comps[a].name} and {comps[b].name}"
                    ),
                    faults=[
                        Fault(target_component_id=a, fault_type=FaultType.COMPONENT_DOWN),
                        Fault(target_component_id=b, fault_type=FaultType.COMPONENT_DOWN),
                    ],
                ))
            # Data corruption on databases
            for cid, comp in comps.items():
                if comp.type in (ComponentType.DATABASE, ComponentType.STORAGE):
                    scenarios.append(Scenario(
                        id=f"datacorrupt-{cid}",
                        name=f"Data corruption: {comp.name}",
                        description=f"Data integrity failure on {comp.name}",
                        faults=[Fault(
                            target_component_id=cid,
                            fault_type=FaultType.DISK_FULL,
                            severity=1.0,
                        )],
                    ))
            # Retry storm
            for cid, comp in comps.items():
                if comp.type in (ComponentType.APP_SERVER, ComponentType.WEB_SERVER):
                    scenarios.append(Scenario(
                        id=f"retrystorm-{cid}",
                        name=f"Retry storm: {comp.name}",
                        description=(
                            f"Connection pool exhaustion triggering retry storm on {comp.name}"
                        ),
                        faults=[Fault(
                            target_component_id=cid,
                            fault_type=FaultType.CONNECTION_POOL_EXHAUSTION,
                            severity=0.9,
                        )],
                        traffic_multiplier=1.5,
                    ))

        return scenarios

    # ------------------------------------------------------------------
    # Internal — simulation & scoring
    # ------------------------------------------------------------------

    def _evaluate_candidate(
        self,
        scenario: Scenario,
        difficulty: str,
    ) -> GameDayScenario | None:
        """Run simulation and build a GameDayScenario from the result."""
        result = self._engine.run_scenario(scenario)
        if result.error:
            return None

        chain = result.cascade
        affected_ids = [e.component_id for e in chain.effects]
        cascade_d = _cascade_depth(chain)
        impact_score = min(100.0, result.risk_score * 10.0)

        # Determine primary trigger component
        trigger_ids = [f.target_component_id for f in scenario.faults]
        primary_id = trigger_ids[0] if trigger_ids else ""
        primary_comp = self.graph.get_component(primary_id)

        if primary_comp is None:
            return None

        comp_type = primary_comp.type.value
        has_failover = primary_comp.failover.enabled
        mttr = primary_comp.operational_profile.mttr_minutes

        # Map fault type to failure_mode label
        fault_type = scenario.faults[0].fault_type if scenario.faults else FaultType.COMPONENT_DOWN
        failure_mode = self._fault_to_mode(fault_type, len(scenario.faults))

        # Category
        category = self._determine_category(
            scenario, difficulty, cascade_d, failure_mode
        )

        # Affected user percentage heuristic: proportional to cascade spread
        total = max(len(self.graph.components), 1)
        affected_pct = min(100.0, len(affected_ids) / total * 100.0)

        # Build scenario title
        if len(trigger_ids) > 1:
            names = " + ".join(
                (self.graph.get_component(tid) or primary_comp).name
                for tid in trigger_ids[:2]
            )
            title = f"Compound failure: {names}"
        else:
            action_label = {
                "crash": "Failure",
                "degraded": "Degradation",
                "network_partition": "Network Partition",
                "data_corruption": "Data Corruption",
                "load_surge": "Traffic Surge",
                "cache_flush": "Cache Flush",
            }.get(failure_mode, "Failure")
            title = f"{action_label}: {primary_comp.name}"

        gd = GameDayScenario(
            scenario_id="GD-000",  # will be assigned later
            title=title,
            description=scenario.description,
            difficulty=difficulty,
            category=category,
            trigger_components=trigger_ids,
            failure_mode=failure_mode,
            affected_components=affected_ids,
            cascade_depth=cascade_d,
            estimated_impact_score=impact_score,
            estimated_mttr_minutes=max(mttr, 5.0),
            affected_users_pct=affected_pct,
        )

        # Build steps
        gd.preparation_steps = list(_PREP_COMMON) + [
            f"Confirm {primary_comp.name} is reachable and healthy.",
            "Baseline metrics: record current RPS, error rate, and p99 latency.",
        ]

        gd.execution_steps = _get_execution_steps(comp_type, failure_mode)

        gd.observation_points = list(_OBS_COMMON) + [
            f"Health state of {primary_comp.name} — expected transition to {failure_mode}.",
        ]
        if affected_ids:
            gd.observation_points.append(
                f"Downstream components: {', '.join(affected_ids[:5])} — monitor for cascade."
            )

        gd.recovery_steps = _get_recovery_steps(failure_mode)

        gd.success_criteria = _build_success_criteria(
            trigger_ids, affected_ids, failure_mode, has_failover, max(mttr, 5.0)
        )
        gd.failure_indicators = _build_failure_indicators(
            trigger_ids, failure_mode, mttr
        )

        gd.slo_impact = self._estimate_slo_impact(impact_score, cascade_d)

        gd.pre_gameday_checks = [
            "All participants have read and acknowledged the rollback runbook.",
            f"Snapshot / backup of {primary_comp.name} taken within the last hour.",
            "Monitoring dashboards confirmed showing correct baseline metrics.",
            "War room channel opened and all stakeholders are present.",
        ]
        if has_failover:
            gd.pre_gameday_checks.append(
                f"Failover target for {primary_comp.name} is healthy and lag is < 10s."
            )

        gd.rollback_plan = (
            f"Restore {primary_comp.name} from the pre-test snapshot and restart the service. "
            "If automated failover did not occur, promote the replica manually. "
            "Verify all dependent services reconnect within 5 minutes."
        )

        return gd

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _fault_to_mode(self, fault_type: FaultType, fault_count: int) -> str:
        """Map FaultType to a human-readable failure_mode."""
        mapping: dict[FaultType, str] = {
            FaultType.COMPONENT_DOWN: "crash",
            FaultType.LATENCY_SPIKE: "degraded",
            FaultType.CPU_SATURATION: "degraded",
            FaultType.MEMORY_EXHAUSTION: "crash",
            FaultType.DISK_FULL: "data_corruption",
            FaultType.CONNECTION_POOL_EXHAUSTION: "degraded",
            FaultType.NETWORK_PARTITION: "network_partition",
            FaultType.TRAFFIC_SPIKE: "load_surge",
        }
        if fault_count > 1:
            return "crash"  # compound faults default to crash mode
        return mapping.get(fault_type, "crash")

    def _determine_category(
        self,
        scenario: Scenario,
        difficulty: str,
        cascade_d: int,
        failure_mode: str,
    ) -> str:
        """Determine the scenario category label."""
        if failure_mode == "data_corruption":
            return "data_loss"
        if failure_mode == "network_partition":
            return "network_partition"
        if failure_mode == "load_surge":
            return "load_surge"
        if failure_mode == "cache_flush":
            return "cache_flush"
        if len(scenario.faults) > 1:
            return "multi_failure"
        if cascade_d >= 3:
            return "cascade"
        if difficulty == "easy":
            return "single_failure"
        return "single_failure" if cascade_d <= 1 else "cascade"

    def _estimate_slo_impact(self, impact_score: float, cascade_d: int) -> str:
        """Generate a human-readable SLO impact estimate."""
        if impact_score >= 70:
            minutes_down = cascade_d * 5 + 15
            return (
                f"Critical — estimated {minutes_down}-{minutes_down * 2} minutes of degraded "
                "or unavailable service. Monthly error budget likely exhausted."
            )
        if impact_score >= 40:
            return (
                "Moderate — partial degradation expected for affected user segments. "
                "Error budget consumption: 20-40% of monthly allowance."
            )
        return (
            "Low — localised impact with graceful degradation. "
            "Error budget consumption: < 10% of monthly allowance."
        )

    def _select_diverse(
        self,
        scored: list[tuple[float, GameDayScenario]],
        count: int,
    ) -> list[GameDayScenario]:
        """Select up to `count` scenarios with category diversity."""
        selected: list[GameDayScenario] = []
        seen_categories: dict[str, int] = {}
        max_per_category = max(1, (count + 2) // 3)  # allow at most ~1/3 per category

        for _, sc in scored:
            if len(selected) >= count:
                break
            cat_count = seen_categories.get(sc.category, 0)
            if cat_count < max_per_category:
                selected.append(sc)
                seen_categories[sc.category] = cat_count + 1

        # If we still need more, fill without diversity constraint
        if len(selected) < count:
            added_ids = {id(s) for s in selected}
            for _, sc in scored:
                if len(selected) >= count:
                    break
                if id(sc) not in added_ids:
                    selected.append(sc)
                    added_ids.add(id(sc))

        return selected
