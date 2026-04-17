# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""War Room Simulation - multi-phase incident response exercise simulator.

Simulates a complete incident response lifecycle from detection through
post-mortem. Models realistic team roles, escalation paths, and
time-to-detect/mitigate/recover metrics.

Usage:
    from faultray.simulator.war_room import WarRoomSimulator
    sim = WarRoomSimulator(graph)
    report = sim.simulate(incident_type="database_outage", team_size=4)
    print(f"MTTD: {report.time_to_detect_minutes}m")
    print(f"MTTM: {report.time_to_mitigate_minutes}m")

CLI:
    faultray war-room model.yaml --incident database_outage --team-size 4
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType

logger = logging.getLogger(__name__)


@dataclass
class WarRoomRole:
    """A role participating in the war room exercise."""

    name: str  # e.g. "Incident Commander", "SRE On-Call", "DBA", "Comms Lead"
    responsibilities: list[str] = field(default_factory=list)
    available_actions: list[str] = field(default_factory=list)


@dataclass
class WarRoomPhase:
    """A phase of the incident response exercise."""

    name: str  # "Detection", "Triage", "Mitigation", "Recovery", "Post-mortem"
    duration_minutes: float = 0.0
    objectives: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)


@dataclass
class WarRoomEvent:
    """An event that occurs during the war room exercise."""

    time_minutes: float
    phase: str
    event_type: str  # "alert_fired", "escalation", "action_taken", "status_update"
    description: str
    role_involved: str
    outcome: str  # "success", "partial", "failed"


@dataclass
class WarRoomReport:
    """Complete war room exercise report."""

    exercise_name: str
    scenario_description: str
    total_duration_minutes: float
    phases: list[WarRoomPhase] = field(default_factory=list)
    events: list[WarRoomEvent] = field(default_factory=list)
    time_to_detect_minutes: float = 0.0
    time_to_mitigate_minutes: float = 0.0
    time_to_recover_minutes: float = 0.0
    roles_involved: list[str] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    score: float = 0.0  # 0-100 (response effectiveness)


# ---------------------------------------------------------------------------
# Incident type definitions
# ---------------------------------------------------------------------------

_INCIDENT_CONFIGS: dict[str, dict] = {
    "database_outage": {
        "description": "Primary database becomes unresponsive due to connection pool exhaustion",
        "target_types": [ComponentType.DATABASE],
        "fault_type": FaultType.CONNECTION_POOL_EXHAUSTION,
        "severity_base": 8.0,
        "detection_difficulty": 0.6,  # 0=easy, 1=hard
        "mitigation_complexity": 0.7,
        "recovery_complexity": 0.5,
    },
    "network_partition": {
        "description": "Network partition isolates a subset of services from the rest",
        "target_types": [ComponentType.APP_SERVER, ComponentType.WEB_SERVER],
        "fault_type": FaultType.NETWORK_PARTITION,
        "severity_base": 7.0,
        "detection_difficulty": 0.5,
        "mitigation_complexity": 0.6,
        "recovery_complexity": 0.4,
    },
    "ddos_attack": {
        "description": "Distributed denial-of-service attack overwhelms the load balancer",
        "target_types": [ComponentType.LOAD_BALANCER, ComponentType.WEB_SERVER],
        "fault_type": FaultType.TRAFFIC_SPIKE,
        "severity_base": 6.0,
        "detection_difficulty": 0.3,
        "mitigation_complexity": 0.5,
        "recovery_complexity": 0.3,
    },
    "cascading_failure": {
        "description": "A cache failure triggers cascading failures across the stack",
        "target_types": [ComponentType.CACHE, ComponentType.APP_SERVER],
        "fault_type": FaultType.COMPONENT_DOWN,
        "severity_base": 9.0,
        "detection_difficulty": 0.7,
        "mitigation_complexity": 0.8,
        "recovery_complexity": 0.6,
    },
    "security_breach": {
        "description": "Unauthorized access detected on a critical service",
        "target_types": [ComponentType.APP_SERVER, ComponentType.DATABASE],
        "fault_type": FaultType.COMPONENT_DOWN,
        "severity_base": 9.5,
        "detection_difficulty": 0.8,
        "mitigation_complexity": 0.9,
        "recovery_complexity": 0.7,
    },
    "data_corruption": {
        "description": "Data integrity issue detected in the primary database",
        "target_types": [ComponentType.DATABASE, ComponentType.STORAGE],
        "fault_type": FaultType.DISK_FULL,
        "severity_base": 8.5,
        "detection_difficulty": 0.9,
        "mitigation_complexity": 0.8,
        "recovery_complexity": 0.9,
    },
    "cloud_region_failure": {
        "description": "Cloud provider region becomes unavailable",
        "target_types": [
            ComponentType.APP_SERVER,
            ComponentType.DATABASE,
            ComponentType.CACHE,
        ],
        "fault_type": FaultType.COMPONENT_DOWN,
        "severity_base": 10.0,
        "detection_difficulty": 0.2,
        "mitigation_complexity": 0.9,
        "recovery_complexity": 0.8,
    },
    "deployment_rollback": {
        "description": "Bad deployment causes service degradation requiring rollback",
        "target_types": [ComponentType.APP_SERVER, ComponentType.WEB_SERVER],
        "fault_type": FaultType.LATENCY_SPIKE,
        "severity_base": 5.0,
        "detection_difficulty": 0.4,
        "mitigation_complexity": 0.3,
        "recovery_complexity": 0.2,
    },
}

# Default roles by team size
_ROLES_BY_SIZE: dict[int, list[WarRoomRole]] = {
    1: [
        WarRoomRole(
            name="SRE On-Call",
            responsibilities=["Detection", "Triage", "Mitigation", "Recovery"],
            available_actions=["acknowledge_alert", "restart_service", "rollback", "scale_up"],
        ),
    ],
    2: [
        WarRoomRole(
            name="Incident Commander",
            responsibilities=["Coordination", "Communication", "Decision-making"],
            available_actions=["escalate", "declare_incident", "update_status"],
        ),
        WarRoomRole(
            name="SRE On-Call",
            responsibilities=["Detection", "Triage", "Mitigation"],
            available_actions=["acknowledge_alert", "restart_service", "rollback", "scale_up"],
        ),
    ],
    3: [
        WarRoomRole(
            name="Incident Commander",
            responsibilities=["Coordination", "Communication", "Decision-making"],
            available_actions=["escalate", "declare_incident", "update_status"],
        ),
        WarRoomRole(
            name="SRE On-Call",
            responsibilities=["Detection", "Triage", "Mitigation"],
            available_actions=["acknowledge_alert", "restart_service", "rollback", "scale_up"],
        ),
        WarRoomRole(
            name="DBA",
            responsibilities=["Database recovery", "Data integrity checks"],
            available_actions=["failover_db", "restore_backup", "run_integrity_check"],
        ),
    ],
    4: [
        WarRoomRole(
            name="Incident Commander",
            responsibilities=["Coordination", "Communication", "Decision-making"],
            available_actions=["escalate", "declare_incident", "update_status"],
        ),
        WarRoomRole(
            name="SRE On-Call",
            responsibilities=["Detection", "Triage", "Mitigation"],
            available_actions=["acknowledge_alert", "restart_service", "rollback", "scale_up"],
        ),
        WarRoomRole(
            name="DBA",
            responsibilities=["Database recovery", "Data integrity checks"],
            available_actions=["failover_db", "restore_backup", "run_integrity_check"],
        ),
        WarRoomRole(
            name="Comms Lead",
            responsibilities=["Stakeholder updates", "Status page", "Customer comms"],
            available_actions=["update_status_page", "notify_stakeholders", "draft_postmortem"],
        ),
    ],
}


class WarRoomSimulator:
    """Simulate incident response exercises against an infrastructure graph.

    Uses the existing simulation engines (CascadeEngine) to model the
    blast radius of incidents and evaluates response effectiveness based
    on infrastructure capabilities (failover, autoscaling, circuit breakers).
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._cascade_engine = CascadeEngine(graph)

    def available_incidents(self) -> list[str]:
        """List incident types that can be simulated."""
        return sorted(_INCIDENT_CONFIGS.keys())

    def simulate(
        self,
        incident_type: str = "database_outage",
        team_size: int = 4,
        has_runbook: bool = True,
    ) -> WarRoomReport:
        """Simulate a complete incident response exercise.

        Parameters
        ----------
        incident_type:
            Type of incident to simulate. See ``available_incidents()``.
        team_size:
            Number of team members (1-4). Larger teams detect and
            respond faster.
        has_runbook:
            Whether the team has a documented runbook for this type
            of incident. Reduces response times.

        Returns
        -------
        WarRoomReport
            Complete exercise report with timing metrics, events, and score.
        """
        if incident_type not in _INCIDENT_CONFIGS:
            raise ValueError(
                f"Unknown incident type '{incident_type}'. "
                f"Available: {self.available_incidents()}"
            )

        config = _INCIDENT_CONFIGS[incident_type]
        team_size = max(1, min(team_size, 4))

        # Determine roles
        roles = self._get_roles(team_size)

        # Find target component(s) matching the incident type
        target_comp = self._find_target_component(config["target_types"])
        if target_comp is None:
            # No matching component; use the first component
            target_comp = next(iter(self.graph.components.values()), None)

        # Run cascade simulation to determine blast radius
        blast_radius = 0
        cascade_severity = 0.0
        if target_comp is not None:
            fault = Fault(
                target_component_id=target_comp.id,
                fault_type=config["fault_type"],
            )
            chain = self._cascade_engine.simulate_fault(fault)
            blast_radius = len(chain.effects)
            cascade_severity = chain.severity

        # Calculate timing based on infrastructure capabilities and team
        detection_time = self._calculate_detection_time(
            config, team_size, has_runbook, target_comp
        )
        triage_time = self._calculate_triage_time(
            config, team_size, has_runbook, blast_radius
        )
        mitigation_time = self._calculate_mitigation_time(
            config, team_size, has_runbook, target_comp
        )
        recovery_time = self._calculate_recovery_time(
            config, team_size, has_runbook, target_comp
        )
        postmortem_time = 15.0  # Fixed 15-minute post-mortem summary

        # Build phases
        phases = self._build_phases(
            detection_time, triage_time, mitigation_time,
            recovery_time, postmortem_time, config
        )

        # Generate events timeline
        events = self._generate_events(
            phases, roles, config, target_comp,
            blast_radius, cascade_severity, has_runbook
        )

        total_duration = sum(p.duration_minutes for p in phases)
        time_to_detect = detection_time
        time_to_mitigate = detection_time + triage_time + mitigation_time
        time_to_recover = time_to_mitigate + recovery_time

        # Calculate lessons learned
        lessons = self._generate_lessons(
            config, target_comp, blast_radius, has_runbook,
            team_size, cascade_severity
        )

        # Calculate overall score
        score = self._calculate_score(
            detection_time, mitigation_time, recovery_time,
            blast_radius, cascade_severity, has_runbook, team_size
        )

        return WarRoomReport(
            exercise_name=f"War Room: {incident_type.replace('_', ' ').title()}",
            scenario_description=config["description"],
            total_duration_minutes=round(total_duration, 1),
            phases=phases,
            events=events,
            time_to_detect_minutes=round(time_to_detect, 1),
            time_to_mitigate_minutes=round(time_to_mitigate, 1),
            time_to_recover_minutes=round(time_to_recover, 1),
            roles_involved=[r.name for r in roles],
            lessons_learned=lessons,
            score=round(score, 1),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_roles(self, team_size: int) -> list[WarRoomRole]:
        """Get appropriate roles for the team size."""
        clamped = max(1, min(team_size, max(_ROLES_BY_SIZE.keys())))
        # Find the closest defined size
        sizes = sorted(_ROLES_BY_SIZE.keys())
        for s in sizes:
            if s >= clamped:
                return _ROLES_BY_SIZE[s]
        return _ROLES_BY_SIZE[sizes[-1]]

    def _find_target_component(self, target_types: list[ComponentType]):
        """Find the best target component for the incident type."""
        for comp_type in target_types:
            for comp in self.graph.components.values():
                if comp.type == comp_type:
                    return comp
        return None

    def _calculate_detection_time(
        self, config: dict, team_size: int, has_runbook: bool, target_comp
    ) -> float:
        """Calculate time to detect the incident in minutes."""
        base = 5.0 + config["detection_difficulty"] * 20.0  # 5-25 min base

        # Team size factor: larger teams notice faster
        team_factor = 1.0 / math.sqrt(team_size)

        # Runbook factor: documented procedures speed up detection
        runbook_factor = 0.7 if has_runbook else 1.0

        # Infrastructure factor: monitoring/alerting reduces detection time
        infra_factor = 1.0
        if target_comp is not None:
            if target_comp.failover.enabled:
                infra_factor *= 0.8  # Health checks detect faster
            if target_comp.autoscaling.enabled:
                infra_factor *= 0.9  # Autoscaling alerts

        return max(1.0, base * team_factor * runbook_factor * infra_factor)

    def _calculate_triage_time(
        self, config: dict, team_size: int, has_runbook: bool, blast_radius: int
    ) -> float:
        """Calculate time to triage and identify root cause in minutes."""
        base = 10.0 + config["mitigation_complexity"] * 15.0  # 10-25 min base

        # Blast radius makes triage harder
        radius_factor = 1.0 + (blast_radius * 0.1)

        # Team factor
        team_factor = 1.0 / math.sqrt(team_size)

        # Runbook factor
        runbook_factor = 0.6 if has_runbook else 1.0

        return max(2.0, base * team_factor * runbook_factor * radius_factor)

    def _calculate_mitigation_time(
        self, config: dict, team_size: int, has_runbook: bool, target_comp
    ) -> float:
        """Calculate time to mitigate the incident in minutes."""
        base = 10.0 + config["mitigation_complexity"] * 30.0  # 10-40 min base

        # Team factor
        team_factor = 1.0 / math.sqrt(team_size)

        # Runbook factor
        runbook_factor = 0.5 if has_runbook else 1.0

        # Infrastructure factor
        infra_factor = 1.0
        if target_comp is not None:
            if target_comp.failover.enabled:
                promo_time = target_comp.failover.promotion_time_seconds / 60.0
                infra_factor *= 0.3  # Failover handles it automatically
                base = max(promo_time, 2.0)
            if target_comp.autoscaling.enabled:
                infra_factor *= 0.5

        return max(1.0, base * team_factor * runbook_factor * infra_factor)

    def _calculate_recovery_time(
        self, config: dict, team_size: int, has_runbook: bool, target_comp
    ) -> float:
        """Calculate time to fully recover in minutes."""
        base = 15.0 + config["recovery_complexity"] * 45.0  # 15-60 min base

        # Team factor
        team_factor = 1.0 / math.sqrt(team_size)

        # Runbook factor
        runbook_factor = 0.6 if has_runbook else 1.0

        # MTTR from operational profile
        if target_comp is not None:
            mttr = target_comp.operational_profile.mttr_minutes
            if mttr > 0:
                base = min(base, mttr)

        # Infrastructure factor
        infra_factor = 1.0
        if target_comp is not None:
            if target_comp.failover.enabled:
                infra_factor *= 0.4
            if target_comp.replicas > 1:
                infra_factor *= 0.6

        return max(2.0, base * team_factor * runbook_factor * infra_factor)

    def _build_phases(
        self,
        detection_time: float,
        triage_time: float,
        mitigation_time: float,
        recovery_time: float,
        postmortem_time: float,
        config: dict,
    ) -> list[WarRoomPhase]:
        """Build the phase list with objectives and success criteria."""
        return [
            WarRoomPhase(
                name="Detection",
                duration_minutes=round(detection_time, 1),
                objectives=[
                    "Alert fires and is acknowledged",
                    "Initial severity assessment",
                ],
                success_criteria=[
                    f"Alert acknowledged within {max(1, int(detection_time))} minutes",
                    "Correct severity level assigned",
                ],
            ),
            WarRoomPhase(
                name="Triage",
                duration_minutes=round(triage_time, 1),
                objectives=[
                    "Identify root cause",
                    "Assess blast radius",
                    "Determine affected services",
                ],
                success_criteria=[
                    "Root cause identified",
                    "Blast radius documented",
                    "Stakeholders notified",
                ],
            ),
            WarRoomPhase(
                name="Mitigation",
                duration_minutes=round(mitigation_time, 1),
                objectives=[
                    "Apply immediate fix to stop impact",
                    "Verify fix effectiveness",
                ],
                success_criteria=[
                    "Impact stopped or significantly reduced",
                    "No new cascading failures",
                ],
            ),
            WarRoomPhase(
                name="Recovery",
                duration_minutes=round(recovery_time, 1),
                objectives=[
                    "Restore full service",
                    "Verify data integrity",
                    "Clear error backlog",
                ],
                success_criteria=[
                    "All services restored to healthy state",
                    "Error rates back to baseline",
                    "No data loss confirmed",
                ],
            ),
            WarRoomPhase(
                name="Post-mortem",
                duration_minutes=round(postmortem_time, 1),
                objectives=[
                    "Document timeline",
                    "Identify lessons learned",
                    "Assign action items",
                ],
                success_criteria=[
                    "Timeline documented",
                    "At least 3 actionable improvements identified",
                    "Action items assigned with owners",
                ],
            ),
        ]

    def _generate_events(
        self,
        phases: list[WarRoomPhase],
        roles: list[WarRoomRole],
        config: dict,
        target_comp,
        blast_radius: int,
        cascade_severity: float,
        has_runbook: bool,
    ) -> list[WarRoomEvent]:
        """Generate a realistic event timeline for the exercise."""
        events: list[WarRoomEvent] = []
        current_time = 0.0
        target_name = target_comp.name if target_comp else "unknown"

        # Find role names
        ic_name = "Incident Commander"
        sre_name = "SRE On-Call"
        dba_name = "DBA"
        comms_name = "Comms Lead"

        role_names = [r.name for r in roles]
        if ic_name not in role_names:
            ic_name = role_names[0]  # Smallest team: single person
        if sre_name not in role_names:
            sre_name = role_names[0]
        if dba_name not in role_names:
            dba_name = sre_name
        if comms_name not in role_names:
            comms_name = ic_name

        # Phase 1: Detection
        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Detection",
            event_type="alert_fired",
            description=f"Alert: {config['description']}",
            role_involved="system",
            outcome="success",
        ))
        current_time += phases[0].duration_minutes * 0.4

        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Detection",
            event_type="action_taken",
            description=f"{sre_name} acknowledges alert for {target_name}",
            role_involved=sre_name,
            outcome="success",
        ))
        current_time += phases[0].duration_minutes * 0.6

        # Phase 2: Triage
        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Triage",
            event_type="escalation",
            description=f"Incident declared - {ic_name} assembles war room",
            role_involved=ic_name,
            outcome="success",
        ))
        current_time += phases[1].duration_minutes * 0.3

        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Triage",
            event_type="status_update",
            description=f"Blast radius assessed: {blast_radius} component(s) affected, "
                        f"severity {cascade_severity:.1f}/10",
            role_involved=sre_name,
            outcome="success" if blast_radius <= 3 else "partial",
        ))
        current_time += phases[1].duration_minutes * 0.4

        if has_runbook:
            events.append(WarRoomEvent(
                time_minutes=round(current_time, 1),
                phase="Triage",
                event_type="action_taken",
                description="Runbook located and being followed",
                role_involved=sre_name,
                outcome="success",
            ))
        else:
            events.append(WarRoomEvent(
                time_minutes=round(current_time, 1),
                phase="Triage",
                event_type="status_update",
                description="No runbook available - improvising response",
                role_involved=sre_name,
                outcome="partial",
            ))
        current_time += phases[1].duration_minutes * 0.3

        # Phase 3: Mitigation
        has_failover = target_comp is not None and target_comp.failover.enabled
        has_autoscale = target_comp is not None and target_comp.autoscaling.enabled

        if has_failover:
            promo = target_comp.failover.promotion_time_seconds
            events.append(WarRoomEvent(
                time_minutes=round(current_time, 1),
                phase="Mitigation",
                event_type="action_taken",
                description=f"Automatic failover triggered for {target_name} "
                            f"(promotion time: {promo}s)",
                role_involved="system",
                outcome="success",
            ))
        elif has_autoscale:
            events.append(WarRoomEvent(
                time_minutes=round(current_time, 1),
                phase="Mitigation",
                event_type="action_taken",
                description=f"Autoscaling triggered for {target_name} - "
                            f"scaling up from {target_comp.replicas} replicas",
                role_involved="system",
                outcome="success",
            ))
        else:
            events.append(WarRoomEvent(
                time_minutes=round(current_time, 1),
                phase="Mitigation",
                event_type="action_taken",
                description=f"Manual intervention required for {target_name} "
                            f"- no automated recovery available",
                role_involved=sre_name,
                outcome="partial",
            ))
        current_time += phases[2].duration_minutes * 0.5

        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Mitigation",
            event_type="status_update",
            description="Mitigation applied - monitoring for effectiveness",
            role_involved=ic_name,
            outcome="success",
        ))
        current_time += phases[2].duration_minutes * 0.5

        # Comms update
        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Mitigation",
            event_type="status_update",
            description="Status page updated - customers notified of partial service disruption",
            role_involved=comms_name,
            outcome="success",
        ))

        # Phase 4: Recovery
        current_time += phases[3].duration_minutes * 0.3
        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Recovery",
            event_type="action_taken",
            description=f"Service restoration in progress for {target_name}",
            role_involved=sre_name,
            outcome="success",
        ))
        current_time += phases[3].duration_minutes * 0.5

        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Recovery",
            event_type="status_update",
            description="All services restored - error rates returning to baseline",
            role_involved=sre_name,
            outcome="success",
        ))
        current_time += phases[3].duration_minutes * 0.2

        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Recovery",
            event_type="status_update",
            description="Status page updated - service fully restored",
            role_involved=comms_name,
            outcome="success",
        ))

        # Phase 5: Post-mortem
        current_time += phases[4].duration_minutes * 0.3
        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Post-mortem",
            event_type="action_taken",
            description="Post-mortem initiated - timeline review",
            role_involved=ic_name,
            outcome="success",
        ))
        current_time += phases[4].duration_minutes * 0.7

        events.append(WarRoomEvent(
            time_minutes=round(current_time, 1),
            phase="Post-mortem",
            event_type="status_update",
            description="Post-mortem complete - action items assigned",
            role_involved=ic_name,
            outcome="success",
        ))

        return events

    def _generate_lessons(
        self,
        config: dict,
        target_comp,
        blast_radius: int,
        has_runbook: bool,
        team_size: int,
        cascade_severity: float,
    ) -> list[str]:
        """Generate lessons learned based on the simulation results."""
        lessons: list[str] = []

        # Infrastructure-related lessons
        if target_comp is not None:
            if not target_comp.failover.enabled:
                lessons.append(
                    f"Enable failover for {target_comp.name} to reduce "
                    "mitigation time and eliminate manual intervention."
                )
            if target_comp.replicas <= 1:
                lessons.append(
                    f"Add replicas to {target_comp.name} to eliminate "
                    "single point of failure."
                )
            if not target_comp.autoscaling.enabled and target_comp.type in (
                ComponentType.APP_SERVER, ComponentType.WEB_SERVER
            ):
                lessons.append(
                    f"Enable autoscaling for {target_comp.name} to handle "
                    "traffic spikes automatically."
                )

        # Blast radius lessons
        if blast_radius > 3:
            lessons.append(
                f"Blast radius of {blast_radius} components is high. "
                "Add circuit breakers to limit cascade propagation."
            )

        # Runbook lessons
        if not has_runbook:
            lessons.append(
                "Create a documented runbook for this incident type "
                "to reduce triage and mitigation time."
            )

        # Team size lessons
        if team_size < 3 and cascade_severity > 5.0:
            lessons.append(
                "Consider increasing on-call team size for high-severity "
                "incidents to improve response time."
            )

        # Cascade severity lessons
        if cascade_severity > 7.0:
            lessons.append(
                "High cascade severity indicates insufficient isolation "
                "between services. Review dependency architecture."
            )

        # General lessons
        if not lessons:
            lessons.append(
                "Infrastructure shows good resilience characteristics. "
                "Continue regular chaos exercises to maintain readiness."
            )

        return lessons

    def _calculate_score(
        self,
        detection_time: float,
        mitigation_time: float,
        recovery_time: float,
        blast_radius: int,
        cascade_severity: float,
        has_runbook: bool,
        team_size: int,
    ) -> float:
        """Calculate overall response effectiveness score (0-100).

        Factors:
        - Detection speed (25 points max)
        - Mitigation speed (25 points max)
        - Recovery speed (20 points max)
        - Blast radius containment (15 points max)
        - Preparation (runbook + team) (15 points max)
        """
        total = len(self.graph.components)

        # Detection score: < 5 min = 25, > 30 min = 0
        if detection_time <= 5:
            detect_score = 25.0
        elif detection_time >= 30:
            detect_score = 0.0
        else:
            detect_score = 25.0 * (1.0 - (detection_time - 5.0) / 25.0)

        # Mitigation score: < 10 min = 25, > 60 min = 0
        if mitigation_time <= 10:
            mitigate_score = 25.0
        elif mitigation_time >= 60:
            mitigate_score = 0.0
        else:
            mitigate_score = 25.0 * (1.0 - (mitigation_time - 10.0) / 50.0)

        # Recovery score: < 15 min = 20, > 120 min = 0
        if recovery_time <= 15:
            recover_score = 20.0
        elif recovery_time >= 120:
            recover_score = 0.0
        else:
            recover_score = 20.0 * (1.0 - (recovery_time - 15.0) / 105.0)

        # Blast radius score: 0 affected = 15, all affected = 0
        if total == 0:
            blast_score = 15.0
        else:
            blast_ratio = blast_radius / total
            blast_score = max(0.0, 15.0 * (1.0 - blast_ratio))

        # Preparation score
        prep_score = 0.0
        if has_runbook:
            prep_score += 10.0
        if team_size >= 4:
            prep_score += 5.0
        elif team_size >= 2:
            prep_score += 3.0
        else:
            prep_score += 1.0

        return max(0.0, min(100.0, detect_score + mitigate_score + recover_score + blast_score + prep_score))
