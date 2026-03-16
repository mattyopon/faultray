"""Incident Response Simulator - evaluates and models incident response processes.

Simulates complete incident response workflows including severity classification,
escalation chain modeling, MTTR estimation, communication planning, runbook
coverage, on-call fatigue analysis, war room coordination, post-incident review
generation, timeline reconstruction, and automation opportunity scoring.

Usage:
    from faultray.simulator.incident_response_simulator import (
        IncidentResponseSimulator,
    )
    sim = IncidentResponseSimulator(graph)
    result = sim.simulate_incident("db1", severity=SeverityLevel.SEV2)
    print(result.mttr_estimate_minutes)
    print(result.escalation_chain)

CLI:
    faultray incident-response model.yaml --component db1 --severity SEV2
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SeverityLevel(str, Enum):
    """Incident severity levels from most critical to least."""

    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"
    SEV5 = "SEV5"


class EscalationAction(str, Enum):
    """Actions that can be taken during escalation."""

    PAGE_ONCALL = "page_oncall"
    NOTIFY_TEAM_LEAD = "notify_team_lead"
    NOTIFY_ENGINEERING_MANAGER = "notify_engineering_manager"
    NOTIFY_VP_ENGINEERING = "notify_vp_engineering"
    NOTIFY_CTO = "notify_cto"
    ASSEMBLE_WAR_ROOM = "assemble_war_room"
    NOTIFY_STAKEHOLDERS = "notify_stakeholders"
    NOTIFY_CUSTOMERS = "notify_customers"
    EXECUTIVE_BRIEFING = "executive_briefing"


class IncidentCategory(str, Enum):
    """Categorization of incident types for pattern detection."""

    INFRASTRUCTURE = "infrastructure"
    APPLICATION = "application"
    DATABASE = "database"
    NETWORK = "network"
    SECURITY = "security"
    CAPACITY = "capacity"
    DEPLOYMENT = "deployment"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


class RecoveryActionType(str, Enum):
    """Types of recovery actions."""

    RESTART_SERVICE = "restart_service"
    FAILOVER = "failover"
    SCALE_UP = "scale_up"
    ROLLBACK_DEPLOY = "rollback_deploy"
    RESTORE_BACKUP = "restore_backup"
    DRAIN_TRAFFIC = "drain_traffic"
    CLEAR_CACHE = "clear_cache"
    ROTATE_CREDENTIALS = "rotate_credentials"
    PATCH_CONFIG = "patch_config"
    MANUAL_INTERVENTION = "manual_intervention"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EscalationStep:
    """A single step in an escalation chain."""

    level: int
    action: EscalationAction
    target_role: str
    trigger_condition: str
    time_threshold_minutes: float
    expected_response_minutes: float


@dataclass
class EscalationChain:
    """Complete escalation chain for an incident."""

    severity: SeverityLevel
    steps: list[EscalationStep] = field(default_factory=list)
    total_escalation_time_minutes: float = 0.0
    auto_escalate: bool = True


@dataclass
class CommunicationPlan:
    """Communication plan for incident notification."""

    stakeholder: str
    channel: str
    delay_minutes: float
    message_template: str
    priority: int  # 1=highest


@dataclass
class CommunicationEffectiveness:
    """Effectiveness assessment for the communication plan."""

    plans: list[CommunicationPlan] = field(default_factory=list)
    average_notification_delay_minutes: float = 0.0
    max_notification_delay_minutes: float = 0.0
    coverage_score: float = 0.0  # 0-100
    gaps: list[str] = field(default_factory=list)


@dataclass
class RunbookCoverage:
    """Assessment of runbook coverage for failure modes."""

    component_id: str
    component_name: str
    failure_modes: list[str] = field(default_factory=list)
    covered_modes: list[str] = field(default_factory=list)
    uncovered_modes: list[str] = field(default_factory=list)
    coverage_percent: float = 0.0


@dataclass
class RunbookCoverageReport:
    """Aggregate runbook coverage across all components."""

    per_component: list[RunbookCoverage] = field(default_factory=list)
    overall_coverage_percent: float = 0.0
    total_failure_modes: int = 0
    total_covered: int = 0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class OnCallFatigueMetrics:
    """Metrics for on-call fatigue analysis."""

    component_id: str
    component_name: str
    estimated_alerts_per_week: float = 0.0
    estimated_pages_per_night: float = 0.0
    rotation_gap_hours: float = 0.0
    fatigue_score: float = 0.0  # 0-100, higher = worse
    risk_level: str = "low"  # low, medium, high, critical


@dataclass
class OnCallFatigueReport:
    """Aggregate on-call fatigue report."""

    per_component: list[OnCallFatigueMetrics] = field(default_factory=list)
    total_estimated_weekly_alerts: float = 0.0
    average_fatigue_score: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class RecoveryAction:
    """A single recovery action with dependencies."""

    action_id: str
    action_type: RecoveryActionType
    component_id: str
    description: str
    estimated_minutes: float
    depends_on: list[str] = field(default_factory=list)
    can_automate: bool = False
    automation_complexity: str = "medium"  # low, medium, high


@dataclass
class RecoveryPlan:
    """Ordered plan of recovery actions."""

    actions: list[RecoveryAction] = field(default_factory=list)
    critical_path_minutes: float = 0.0
    parallel_groups: list[list[str]] = field(default_factory=list)
    total_actions: int = 0


@dataclass
class AutomationOpportunity:
    """An opportunity to automate a manual incident response step."""

    action_id: str
    description: str
    current_manual_time_minutes: float
    estimated_automated_time_minutes: float
    time_savings_minutes: float
    complexity: str  # low, medium, high
    priority_score: float  # 0-100
    recommendation: str


@dataclass
class AutomationReport:
    """Report on automation opportunities."""

    opportunities: list[AutomationOpportunity] = field(default_factory=list)
    total_manual_time_minutes: float = 0.0
    total_potential_savings_minutes: float = 0.0
    automation_coverage_percent: float = 0.0


@dataclass
class IncidentPattern:
    """A detected pattern in incident categorization."""

    category: IncidentCategory
    affected_component_ids: list[str] = field(default_factory=list)
    common_failure_modes: list[str] = field(default_factory=list)
    estimated_frequency_per_month: float = 0.0
    average_mttr_minutes: float = 0.0
    pattern_description: str = ""


@dataclass
class PIRTemplate:
    """Post-Incident Review / Correction of Errors template."""

    incident_id: str
    title: str
    severity: SeverityLevel
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str = ""
    timeline_entries: list[str] = field(default_factory=list)
    root_cause: str = ""
    contributing_factors: list[str] = field(default_factory=list)
    impact_description: str = ""
    affected_components: list[str] = field(default_factory=list)
    mitigation_steps: list[str] = field(default_factory=list)
    action_items: list[dict[str, str]] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    five_whys: list[str] = field(default_factory=list)
    detection_effectiveness: str = ""
    response_effectiveness: str = ""


@dataclass
class TimelineEntry:
    """A single entry in an incident timeline."""

    timestamp_offset_minutes: float
    phase: str
    description: str
    actor: str
    action_type: str


@dataclass
class IncidentTimelineReconstruction:
    """Reconstructed incident timeline."""

    entries: list[TimelineEntry] = field(default_factory=list)
    total_duration_minutes: float = 0.0
    time_to_detect_minutes: float = 0.0
    time_to_acknowledge_minutes: float = 0.0
    time_to_mitigate_minutes: float = 0.0
    time_to_resolve_minutes: float = 0.0


@dataclass
class MTTREstimate:
    """MTTR estimation result."""

    component_id: str
    base_mttr_minutes: float
    adjusted_mttr_minutes: float
    team_factor: float
    automation_factor: float
    runbook_factor: float
    complexity_factor: float
    breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class IncidentResponseResult:
    """Complete result from an incident response simulation."""

    severity: SeverityLevel
    category: IncidentCategory
    affected_component_id: str
    affected_component_ids: list[str] = field(default_factory=list)
    mttr_estimate: MTTREstimate | None = None
    escalation_chain: EscalationChain | None = None
    communication_effectiveness: CommunicationEffectiveness | None = None
    recovery_plan: RecoveryPlan | None = None
    timeline: IncidentTimelineReconstruction | None = None
    pir_template: PIRTemplate | None = None
    automation_report: AutomationReport | None = None
    overall_readiness_score: float = 0.0  # 0-100


# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

_SEVERITY_ESCALATION_MINUTES: dict[SeverityLevel, float] = {
    SeverityLevel.SEV1: 5.0,
    SeverityLevel.SEV2: 15.0,
    SeverityLevel.SEV3: 30.0,
    SeverityLevel.SEV4: 60.0,
    SeverityLevel.SEV5: 120.0,
}

_BASE_MTTR_BY_TYPE: dict[str, float] = {
    ComponentType.LOAD_BALANCER.value: 10.0,
    ComponentType.WEB_SERVER.value: 15.0,
    ComponentType.APP_SERVER.value: 20.0,
    ComponentType.DATABASE.value: 45.0,
    ComponentType.CACHE.value: 8.0,
    ComponentType.QUEUE.value: 15.0,
    ComponentType.STORAGE.value: 60.0,
    ComponentType.DNS.value: 20.0,
    ComponentType.EXTERNAL_API.value: 0.0,
    ComponentType.CUSTOM.value: 30.0,
}

_COMPONENT_TYPE_CATEGORY: dict[str, IncidentCategory] = {
    ComponentType.DATABASE.value: IncidentCategory.DATABASE,
    ComponentType.LOAD_BALANCER.value: IncidentCategory.NETWORK,
    ComponentType.DNS.value: IncidentCategory.NETWORK,
    ComponentType.WEB_SERVER.value: IncidentCategory.APPLICATION,
    ComponentType.APP_SERVER.value: IncidentCategory.APPLICATION,
    ComponentType.CACHE.value: IncidentCategory.INFRASTRUCTURE,
    ComponentType.QUEUE.value: IncidentCategory.INFRASTRUCTURE,
    ComponentType.STORAGE.value: IncidentCategory.INFRASTRUCTURE,
    ComponentType.EXTERNAL_API.value: IncidentCategory.THIRD_PARTY,
    ComponentType.CUSTOM.value: IncidentCategory.UNKNOWN,
}

_FAILURE_MODES_BY_TYPE: dict[str, list[str]] = {
    ComponentType.LOAD_BALANCER.value: [
        "health_check_failure",
        "connection_timeout",
        "ssl_certificate_expiry",
        "backend_pool_exhaustion",
        "config_error",
    ],
    ComponentType.WEB_SERVER.value: [
        "process_crash",
        "oom_kill",
        "high_latency",
        "connection_refused",
        "config_error",
    ],
    ComponentType.APP_SERVER.value: [
        "process_crash",
        "oom_kill",
        "deadlock",
        "thread_pool_exhaustion",
        "dependency_timeout",
        "config_error",
    ],
    ComponentType.DATABASE.value: [
        "connection_pool_exhaustion",
        "replication_lag",
        "disk_full",
        "corruption",
        "lock_contention",
        "slow_query",
        "failover_failure",
    ],
    ComponentType.CACHE.value: [
        "eviction_storm",
        "connection_refused",
        "memory_full",
        "split_brain",
    ],
    ComponentType.QUEUE.value: [
        "queue_full",
        "consumer_lag",
        "message_loss",
        "connection_failure",
        "partition_rebalance",
    ],
    ComponentType.STORAGE.value: [
        "disk_full",
        "io_timeout",
        "corruption",
        "permission_error",
        "replication_failure",
    ],
    ComponentType.DNS.value: [
        "resolution_failure",
        "propagation_delay",
        "ttl_misconfiguration",
        "zone_transfer_failure",
    ],
    ComponentType.EXTERNAL_API.value: [
        "rate_limit",
        "api_deprecation",
        "auth_failure",
        "timeout",
    ],
    ComponentType.CUSTOM.value: [
        "unknown_failure",
        "config_error",
        "resource_exhaustion",
    ],
}

_RECOVERY_ACTIONS_BY_TYPE: dict[str, list[tuple[RecoveryActionType, str, float, bool]]] = {
    ComponentType.LOAD_BALANCER.value: [
        (RecoveryActionType.RESTART_SERVICE, "Restart load balancer process", 3.0, True),
        (RecoveryActionType.DRAIN_TRAFFIC, "Drain traffic from unhealthy backend", 2.0, True),
        (RecoveryActionType.PATCH_CONFIG, "Update LB configuration", 5.0, False),
    ],
    ComponentType.APP_SERVER.value: [
        (RecoveryActionType.RESTART_SERVICE, "Restart application service", 5.0, True),
        (RecoveryActionType.SCALE_UP, "Scale up replicas", 8.0, True),
        (RecoveryActionType.ROLLBACK_DEPLOY, "Rollback to previous version", 10.0, True),
        (RecoveryActionType.CLEAR_CACHE, "Clear application cache", 2.0, True),
    ],
    ComponentType.DATABASE.value: [
        (RecoveryActionType.FAILOVER, "Initiate database failover", 5.0, True),
        (RecoveryActionType.RESTORE_BACKUP, "Restore from latest backup", 30.0, False),
        (RecoveryActionType.PATCH_CONFIG, "Adjust connection pool settings", 5.0, False),
        (RecoveryActionType.MANUAL_INTERVENTION, "Manual data integrity check", 20.0, False),
    ],
    ComponentType.CACHE.value: [
        (RecoveryActionType.RESTART_SERVICE, "Restart cache service", 2.0, True),
        (RecoveryActionType.CLEAR_CACHE, "Flush and rebuild cache", 5.0, True),
        (RecoveryActionType.SCALE_UP, "Add cache replicas", 8.0, True),
    ],
    ComponentType.QUEUE.value: [
        (RecoveryActionType.RESTART_SERVICE, "Restart queue broker", 5.0, True),
        (RecoveryActionType.SCALE_UP, "Scale consumers", 5.0, True),
        (RecoveryActionType.DRAIN_TRAFFIC, "Drain dead letter queue", 3.0, True),
    ],
    ComponentType.STORAGE.value: [
        (RecoveryActionType.RESTORE_BACKUP, "Restore from backup", 45.0, False),
        (RecoveryActionType.MANUAL_INTERVENTION, "Verify data integrity", 30.0, False),
        (RecoveryActionType.PATCH_CONFIG, "Expand storage volume", 10.0, True),
    ],
    ComponentType.WEB_SERVER.value: [
        (RecoveryActionType.RESTART_SERVICE, "Restart web server", 3.0, True),
        (RecoveryActionType.SCALE_UP, "Scale up instances", 8.0, True),
        (RecoveryActionType.ROLLBACK_DEPLOY, "Rollback web deploy", 10.0, True),
    ],
    ComponentType.DNS.value: [
        (RecoveryActionType.PATCH_CONFIG, "Update DNS records", 10.0, False),
        (RecoveryActionType.MANUAL_INTERVENTION, "Clear DNS cache globally", 15.0, False),
    ],
    ComponentType.EXTERNAL_API.value: [
        (RecoveryActionType.MANUAL_INTERVENTION, "Contact external provider", 60.0, False),
        (RecoveryActionType.PATCH_CONFIG, "Switch to fallback endpoint", 5.0, True),
    ],
    ComponentType.CUSTOM.value: [
        (RecoveryActionType.RESTART_SERVICE, "Restart service", 10.0, True),
        (RecoveryActionType.MANUAL_INTERVENTION, "Manual investigation", 30.0, False),
    ],
}


# ---------------------------------------------------------------------------
# Main Simulator
# ---------------------------------------------------------------------------


class IncidentResponseSimulator:
    """Simulates and evaluates incident response processes for an
    infrastructure graph.

    Provides comprehensive analysis of:
    - Severity classification and escalation rules
    - MTTR estimation based on incident type, team, and automation
    - Escalation chain modeling and timing
    - Communication plan effectiveness
    - Runbook coverage assessment
    - On-call fatigue analysis
    - Recovery action dependency ordering
    - Automation opportunity scoring
    - Incident categorization and pattern detection
    - Post-incident review template generation
    - Incident timeline reconstruction
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    # ------------------------------------------------------------------
    # Top-level simulation
    # ------------------------------------------------------------------

    def simulate_incident(
        self,
        component_id: str,
        severity: SeverityLevel = SeverityLevel.SEV3,
        team_size: int = 3,
        automation_level: float = 0.2,
        has_runbook: bool = False,
    ) -> IncidentResponseResult:
        """Run a complete incident response simulation for a component.

        Parameters
        ----------
        component_id:
            ID of the component experiencing the incident.
        severity:
            Severity level of the incident.
        team_size:
            Number of engineers on the response team.
        automation_level:
            Fraction of response that is automated (0.0-1.0).
        has_runbook:
            Whether a runbook exists for this type of failure.

        Returns
        -------
        IncidentResponseResult
            Comprehensive incident response simulation result.
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            raise ValueError(
                f"Component '{component_id}' not found in the graph."
            )

        automation_level = max(0.0, min(1.0, automation_level))
        team_size = max(1, team_size)

        category = self.categorize_incident(component_id)
        affected_ids = self._get_affected_components(component_id)
        severity = self.classify_severity(component_id, severity)

        mttr = self.estimate_mttr(
            component_id,
            team_size=team_size,
            automation_level=automation_level,
            has_runbook=has_runbook,
        )

        escalation = self.build_escalation_chain(severity)

        comm_eff = self.assess_communication_effectiveness(
            severity, team_size
        )

        recovery = self.build_recovery_plan(component_id, affected_ids)

        timeline = self.reconstruct_timeline(
            component_id,
            severity,
            team_size=team_size,
            automation_level=automation_level,
            has_runbook=has_runbook,
        )

        pir = self.generate_pir_template(
            component_id,
            severity,
            affected_ids,
            mttr,
            timeline,
        )

        automation_report = self.score_automation_opportunities(
            recovery
        )

        readiness = self._calculate_readiness_score(
            comp,
            has_runbook,
            automation_level,
            team_size,
            escalation,
            comm_eff,
        )

        return IncidentResponseResult(
            severity=severity,
            category=category,
            affected_component_id=component_id,
            affected_component_ids=affected_ids,
            mttr_estimate=mttr,
            escalation_chain=escalation,
            communication_effectiveness=comm_eff,
            recovery_plan=recovery,
            timeline=timeline,
            pir_template=pir,
            automation_report=automation_report,
            overall_readiness_score=round(readiness, 1),
        )

    # ------------------------------------------------------------------
    # Severity classification
    # ------------------------------------------------------------------

    def classify_severity(
        self,
        component_id: str,
        base_severity: SeverityLevel = SeverityLevel.SEV3,
    ) -> SeverityLevel:
        """Classify or adjust severity based on blast radius and component
        criticality.

        Rules:
        - If blast radius > 50% of total components -> escalate by 1 level
        - If the component has no replicas and is required -> escalate by 1
        - External API outage with no fallback -> maintain severity
        - Minimum severity is SEV5, maximum is SEV1
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            return base_severity

        sev_order = [
            SeverityLevel.SEV1,
            SeverityLevel.SEV2,
            SeverityLevel.SEV3,
            SeverityLevel.SEV4,
            SeverityLevel.SEV5,
        ]
        current_idx = sev_order.index(base_severity)

        affected = self.graph.get_all_affected(component_id)
        total = len(self.graph.components)

        if total > 0 and len(affected) > total * 0.5:
            current_idx = max(0, current_idx - 1)

        dependents = self.graph.get_dependents(component_id)
        has_required_dependents = False
        for dep_comp in dependents:
            edge = self.graph.get_dependency_edge(dep_comp.id, component_id)
            if edge and edge.dependency_type == "requires":
                has_required_dependents = True
                break

        if comp.replicas <= 1 and has_required_dependents:
            current_idx = max(0, current_idx - 1)

        return sev_order[current_idx]

    # ------------------------------------------------------------------
    # MTTR estimation
    # ------------------------------------------------------------------

    def estimate_mttr(
        self,
        component_id: str,
        team_size: int = 3,
        automation_level: float = 0.2,
        has_runbook: bool = False,
    ) -> MTTREstimate:
        """Estimate Mean Time To Recovery for a component incident.

        Factors:
        - Base MTTR from component type
        - Team size factor (more people = faster, with diminishing returns)
        - Automation level (higher automation = faster)
        - Runbook availability (reduces diagnosis time)
        - Complexity factor from dependency depth
        """
        comp = self.graph.get_component(component_id)
        if comp is None:
            raise ValueError(f"Component '{component_id}' not found.")

        base = _BASE_MTTR_BY_TYPE.get(comp.type.value, 30.0)

        # Use operational profile if set
        if comp.operational_profile.mttr_minutes > 0:
            base = comp.operational_profile.mttr_minutes

        # Team factor: diminishing returns via sqrt
        team_factor = 1.0 / math.sqrt(max(1, team_size))

        # Automation factor: 0.0 automation = 1.0x, 1.0 automation = 0.2x
        automation_factor = 1.0 - (automation_level * 0.8)

        # Runbook factor
        runbook_factor = 0.6 if has_runbook else 1.0

        # Complexity factor from dependency depth
        affected = self.graph.get_all_affected(component_id)
        depth = len(affected)
        complexity_factor = 1.0 + (depth * 0.1)

        # Failover / replica factor
        infra_factor = 1.0
        if comp.failover.enabled:
            infra_factor *= 0.4
        if comp.replicas > 1:
            infra_factor *= 0.7

        adjusted = base * team_factor * automation_factor * runbook_factor * complexity_factor * infra_factor
        adjusted = max(1.0, adjusted)

        return MTTREstimate(
            component_id=component_id,
            base_mttr_minutes=round(base, 1),
            adjusted_mttr_minutes=round(adjusted, 1),
            team_factor=round(team_factor, 3),
            automation_factor=round(automation_factor, 3),
            runbook_factor=round(runbook_factor, 3),
            complexity_factor=round(complexity_factor, 3),
            breakdown={
                "base": round(base, 1),
                "team_factor": round(team_factor, 3),
                "automation_factor": round(automation_factor, 3),
                "runbook_factor": round(runbook_factor, 3),
                "complexity_factor": round(complexity_factor, 3),
                "infra_factor": round(infra_factor, 3),
                "adjusted": round(adjusted, 1),
            },
        )

    # ------------------------------------------------------------------
    # Escalation chain
    # ------------------------------------------------------------------

    def build_escalation_chain(
        self,
        severity: SeverityLevel,
    ) -> EscalationChain:
        """Build an escalation chain based on severity level.

        SEV1: Immediate page -> team lead -> eng manager -> VP -> CTO
        SEV2: Page oncall -> team lead -> eng manager -> stakeholders
        SEV3: Notify oncall -> team lead
        SEV4: Notify oncall
        SEV5: Log and track
        """
        steps: list[EscalationStep] = []
        base_time = _SEVERITY_ESCALATION_MINUTES[severity]

        if severity in (SeverityLevel.SEV1, SeverityLevel.SEV2,
                        SeverityLevel.SEV3, SeverityLevel.SEV4,
                        SeverityLevel.SEV5):
            steps.append(EscalationStep(
                level=1,
                action=EscalationAction.PAGE_ONCALL,
                target_role="On-Call Engineer",
                trigger_condition="Incident detected",
                time_threshold_minutes=0.0,
                expected_response_minutes=min(base_time, 5.0),
            ))

        if severity in (SeverityLevel.SEV1, SeverityLevel.SEV2,
                        SeverityLevel.SEV3):
            steps.append(EscalationStep(
                level=2,
                action=EscalationAction.NOTIFY_TEAM_LEAD,
                target_role="Team Lead",
                trigger_condition="No resolution within threshold",
                time_threshold_minutes=base_time,
                expected_response_minutes=base_time * 0.5,
            ))

        if severity in (SeverityLevel.SEV1, SeverityLevel.SEV2):
            steps.append(EscalationStep(
                level=3,
                action=EscalationAction.NOTIFY_ENGINEERING_MANAGER,
                target_role="Engineering Manager",
                trigger_condition="Escalation from team lead",
                time_threshold_minutes=base_time * 2,
                expected_response_minutes=base_time,
            ))
            steps.append(EscalationStep(
                level=4,
                action=EscalationAction.NOTIFY_STAKEHOLDERS,
                target_role="Stakeholders",
                trigger_condition="Impact confirmed",
                time_threshold_minutes=base_time * 2,
                expected_response_minutes=0.0,
            ))

        if severity == SeverityLevel.SEV1:
            steps.append(EscalationStep(
                level=5,
                action=EscalationAction.NOTIFY_VP_ENGINEERING,
                target_role="VP of Engineering",
                trigger_condition="Critical incident not resolved",
                time_threshold_minutes=base_time * 3,
                expected_response_minutes=base_time * 0.5,
            ))
            steps.append(EscalationStep(
                level=6,
                action=EscalationAction.ASSEMBLE_WAR_ROOM,
                target_role="War Room",
                trigger_condition="SEV1 declared",
                time_threshold_minutes=base_time * 0.5,
                expected_response_minutes=base_time,
            ))
            steps.append(EscalationStep(
                level=7,
                action=EscalationAction.EXECUTIVE_BRIEFING,
                target_role="CTO",
                trigger_condition="SEV1 > 30 minutes",
                time_threshold_minutes=30.0,
                expected_response_minutes=10.0,
            ))

        total_time = sum(s.time_threshold_minutes + s.expected_response_minutes for s in steps)

        return EscalationChain(
            severity=severity,
            steps=steps,
            total_escalation_time_minutes=round(total_time, 1),
            auto_escalate=severity in (SeverityLevel.SEV1, SeverityLevel.SEV2),
        )

    # ------------------------------------------------------------------
    # Communication effectiveness
    # ------------------------------------------------------------------

    def assess_communication_effectiveness(
        self,
        severity: SeverityLevel,
        team_size: int = 3,
    ) -> CommunicationEffectiveness:
        """Assess communication plan effectiveness for an incident.

        Evaluates notification delays, coverage, and identifies gaps.
        """
        plans: list[CommunicationPlan] = []
        gaps: list[str] = []

        # Internal engineering team
        plans.append(CommunicationPlan(
            stakeholder="Engineering Team",
            channel="Slack #incidents",
            delay_minutes=1.0,
            message_template="Incident detected: {component} - {severity}",
            priority=1,
        ))

        # On-call
        plans.append(CommunicationPlan(
            stakeholder="On-Call Engineer",
            channel="PagerDuty",
            delay_minutes=0.5,
            message_template="ALERT: {component} incident - {severity}",
            priority=1,
        ))

        if severity in (SeverityLevel.SEV1, SeverityLevel.SEV2):
            plans.append(CommunicationPlan(
                stakeholder="Engineering Leadership",
                channel="Email + Slack DM",
                delay_minutes=10.0,
                message_template="Incident escalation: {severity} - {impact}",
                priority=2,
            ))
            plans.append(CommunicationPlan(
                stakeholder="Status Page",
                channel="Status Page API",
                delay_minutes=15.0,
                message_template="We are investigating reports of {issue}",
                priority=2,
            ))

        if severity == SeverityLevel.SEV1:
            plans.append(CommunicationPlan(
                stakeholder="Customer Support",
                channel="Slack #support-escalations",
                delay_minutes=5.0,
                message_template="Customer-facing incident: {severity}",
                priority=1,
            ))
            plans.append(CommunicationPlan(
                stakeholder="Executive Team",
                channel="Email + Phone",
                delay_minutes=20.0,
                message_template="Critical incident briefing: {summary}",
                priority=3,
            ))

        # Identify gaps
        if team_size < 2:
            gaps.append("Single-person team cannot handle communication and mitigation simultaneously")

        if severity in (SeverityLevel.SEV1, SeverityLevel.SEV2):
            if not any(p.stakeholder == "Customer Support" for p in plans) and severity == SeverityLevel.SEV2:
                gaps.append("No customer support notification for SEV2 incidents")

        if severity == SeverityLevel.SEV1:
            max_delay = max(p.delay_minutes for p in plans) if plans else 0
            if max_delay > 30:
                gaps.append(f"Maximum notification delay of {max_delay} minutes is too high for SEV1")

        delays = [p.delay_minutes for p in plans]
        avg_delay = sum(delays) / len(delays) if delays else 0.0
        max_delay = max(delays) if delays else 0.0

        # Coverage: based on how many stakeholder types are notified
        expected_stakeholders = 2  # minimum: engineering + oncall
        if severity in (SeverityLevel.SEV1, SeverityLevel.SEV2):
            expected_stakeholders = 4
        if severity == SeverityLevel.SEV1:
            expected_stakeholders = 6

        actual = len(plans)
        coverage = min(100.0, (actual / max(1, expected_stakeholders)) * 100.0)

        return CommunicationEffectiveness(
            plans=plans,
            average_notification_delay_minutes=round(avg_delay, 1),
            max_notification_delay_minutes=round(max_delay, 1),
            coverage_score=round(coverage, 1),
            gaps=gaps,
        )

    # ------------------------------------------------------------------
    # Runbook coverage assessment
    # ------------------------------------------------------------------

    def assess_runbook_coverage(self) -> RunbookCoverageReport:
        """Assess runbook coverage across all components.

        Determines which failure modes have runbook coverage based on
        component configuration (team.runbook_coverage_percent and
        team.automation_percent).
        """
        per_component: list[RunbookCoverage] = []
        total_modes = 0
        total_covered = 0

        for comp in self.graph.components.values():
            failure_modes = _FAILURE_MODES_BY_TYPE.get(comp.type.value, ["unknown_failure"])
            coverage_pct = comp.team.runbook_coverage_percent / 100.0

            num_covered = max(0, int(len(failure_modes) * coverage_pct))
            covered = failure_modes[:num_covered]
            uncovered = failure_modes[num_covered:]

            cov_pct = (len(covered) / len(failure_modes) * 100.0) if failure_modes else 0.0

            per_component.append(RunbookCoverage(
                component_id=comp.id,
                component_name=comp.name,
                failure_modes=failure_modes,
                covered_modes=covered,
                uncovered_modes=uncovered,
                coverage_percent=round(cov_pct, 1),
            ))

            total_modes += len(failure_modes)
            total_covered += len(covered)

        overall = (total_covered / total_modes * 100.0) if total_modes > 0 else 0.0

        recommendations: list[str] = []
        for rc in per_component:
            if rc.coverage_percent < 50.0:
                recommendations.append(
                    f"Component '{rc.component_name}' has only {rc.coverage_percent}% "
                    f"runbook coverage. Priority modes to document: "
                    f"{', '.join(rc.uncovered_modes[:3])}"
                )

        if overall < 70.0:
            recommendations.append(
                f"Overall runbook coverage is {overall:.1f}%. "
                "Target at least 70% coverage for critical failure modes."
            )

        return RunbookCoverageReport(
            per_component=per_component,
            overall_coverage_percent=round(overall, 1),
            total_failure_modes=total_modes,
            total_covered=total_covered,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # On-call fatigue analysis
    # ------------------------------------------------------------------

    def analyze_oncall_fatigue(self) -> OnCallFatigueReport:
        """Analyze on-call fatigue based on component alert profiles.

        Uses component operational profiles and team configuration to
        estimate alert volume, night-time pages, and rotation gaps.
        """
        per_component: list[OnCallFatigueMetrics] = []
        total_weekly_alerts = 0.0

        for comp in self.graph.components.values():
            mtbf = comp.operational_profile.mtbf_hours
            if mtbf <= 0:
                # No MTBF data; assume moderate alert rate
                estimated_alerts_week = 2.0
            else:
                # Alerts per week = 168 hours / MTBF
                estimated_alerts_week = 168.0 / mtbf

            # Night pages are a fraction of total alerts
            pages_per_night = estimated_alerts_week / 7.0 * 0.3

            # Rotation gap: if coverage < 24h, there are gaps
            coverage_hours = comp.team.oncall_coverage_hours
            rotation_gap = max(0.0, 24.0 - coverage_hours)

            # Fatigue score: composite of alerts, night pages, gaps
            fatigue = min(100.0, (
                estimated_alerts_week * 3.0
                + pages_per_night * 20.0
                + rotation_gap * 2.0
            ))

            if fatigue >= 75.0:
                risk_level = "critical"
            elif fatigue >= 50.0:
                risk_level = "high"
            elif fatigue >= 25.0:
                risk_level = "medium"
            else:
                risk_level = "low"

            per_component.append(OnCallFatigueMetrics(
                component_id=comp.id,
                component_name=comp.name,
                estimated_alerts_per_week=round(estimated_alerts_week, 1),
                estimated_pages_per_night=round(pages_per_night, 2),
                rotation_gap_hours=round(rotation_gap, 1),
                fatigue_score=round(fatigue, 1),
                risk_level=risk_level,
            ))

            total_weekly_alerts += estimated_alerts_week

        avg_fatigue = (
            sum(m.fatigue_score for m in per_component) / len(per_component)
            if per_component
            else 0.0
        )

        recommendations: list[str] = []
        for m in per_component:
            if m.risk_level == "critical":
                recommendations.append(
                    f"CRITICAL: Component '{m.component_name}' fatigue score {m.fatigue_score}. "
                    "Reduce alert noise or increase team rotation."
                )
            elif m.risk_level == "high":
                recommendations.append(
                    f"HIGH: Component '{m.component_name}' fatigue score {m.fatigue_score}. "
                    "Review alert thresholds and add automation."
                )
            if m.rotation_gap_hours > 0:
                recommendations.append(
                    f"Component '{m.component_name}' has {m.rotation_gap_hours}h "
                    "rotation gap. Consider expanding on-call coverage."
                )

        return OnCallFatigueReport(
            per_component=per_component,
            total_estimated_weekly_alerts=round(total_weekly_alerts, 1),
            average_fatigue_score=round(avg_fatigue, 1),
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Incident categorization and pattern detection
    # ------------------------------------------------------------------

    def categorize_incident(self, component_id: str) -> IncidentCategory:
        """Categorize an incident based on the affected component type."""
        comp = self.graph.get_component(component_id)
        if comp is None:
            return IncidentCategory.UNKNOWN
        return _COMPONENT_TYPE_CATEGORY.get(
            comp.type.value, IncidentCategory.UNKNOWN
        )

    def detect_patterns(self) -> list[IncidentPattern]:
        """Detect potential incident patterns from infrastructure topology.

        Identifies clusters of related components that share failure modes
        and estimates incident frequency from MTBF data.
        """
        category_groups: dict[IncidentCategory, list[Component]] = {}
        for comp in self.graph.components.values():
            cat = _COMPONENT_TYPE_CATEGORY.get(
                comp.type.value, IncidentCategory.UNKNOWN
            )
            category_groups.setdefault(cat, []).append(comp)

        patterns: list[IncidentPattern] = []

        for cat, components in category_groups.items():
            component_ids = [c.id for c in components]

            all_modes: list[str] = []
            for c in components:
                modes = _FAILURE_MODES_BY_TYPE.get(c.type.value, [])
                all_modes.extend(modes)
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique_modes: list[str] = []
            for m in all_modes:
                if m not in seen:
                    seen.add(m)
                    unique_modes.append(m)

            # Estimate frequency from MTBF
            mtbf_values = [c.operational_profile.mtbf_hours for c in components if c.operational_profile.mtbf_hours > 0]
            if mtbf_values:
                avg_mtbf = sum(mtbf_values) / len(mtbf_values)
                freq_per_month = (730.0 / avg_mtbf) * len(components)
            else:
                freq_per_month = len(components) * 0.5

            # Average MTTR
            mttr_values = [
                _BASE_MTTR_BY_TYPE.get(c.type.value, 30.0)
                for c in components
            ]
            avg_mttr = sum(mttr_values) / len(mttr_values) if mttr_values else 30.0

            patterns.append(IncidentPattern(
                category=cat,
                affected_component_ids=component_ids,
                common_failure_modes=unique_modes[:5],
                estimated_frequency_per_month=round(freq_per_month, 1),
                average_mttr_minutes=round(avg_mttr, 1),
                pattern_description=(
                    f"{cat.value.title()} incidents affecting "
                    f"{len(components)} component(s) with "
                    f"{len(unique_modes)} failure mode(s)."
                ),
            ))

        return patterns

    # ------------------------------------------------------------------
    # Recovery plan and dependency ordering
    # ------------------------------------------------------------------

    def build_recovery_plan(
        self,
        component_id: str,
        affected_ids: list[str] | None = None,
    ) -> RecoveryPlan:
        """Build a recovery plan with dependency-ordered actions.

        The plan considers:
        - Recovery actions specific to component type
        - Dependency ordering (recover dependencies before dependents)
        - Parallel execution where dependencies allow
        """
        if affected_ids is None:
            affected_ids = [component_id]

        all_ids = [component_id] + [
            aid for aid in affected_ids if aid != component_id
        ]

        actions: list[RecoveryAction] = []
        action_counter = 0

        # Determine dependency order: recover leaf nodes first
        ordered_ids = self._dependency_ordered_components(all_ids)

        for cid in ordered_ids:
            comp = self.graph.get_component(cid)
            if comp is None:
                continue

            type_actions = _RECOVERY_ACTIONS_BY_TYPE.get(
                comp.type.value,
                [(RecoveryActionType.MANUAL_INTERVENTION, "Manual recovery", 30.0, False)],
            )

            deps_in_plan = [
                a.action_id for a in actions
                if a.component_id in [
                    d.id for d in self.graph.get_dependencies(cid)
                    if d.id in all_ids
                ]
            ]

            for action_type, desc, est_min, can_auto in type_actions:
                action_counter += 1
                aid = f"action_{action_counter}"
                actions.append(RecoveryAction(
                    action_id=aid,
                    action_type=action_type,
                    component_id=cid,
                    description=f"{desc} ({comp.name})",
                    estimated_minutes=est_min,
                    depends_on=deps_in_plan[:],
                    can_automate=can_auto,
                    automation_complexity="low" if can_auto else "high",
                ))

        # Calculate critical path
        critical_path = self._calculate_critical_path(actions)

        # Identify parallel groups
        parallel_groups = self._identify_parallel_groups(actions)

        return RecoveryPlan(
            actions=actions,
            critical_path_minutes=round(critical_path, 1),
            parallel_groups=parallel_groups,
            total_actions=len(actions),
        )

    # ------------------------------------------------------------------
    # Automation opportunity scoring
    # ------------------------------------------------------------------

    def score_automation_opportunities(
        self,
        recovery_plan: RecoveryPlan,
    ) -> AutomationReport:
        """Score automation opportunities from a recovery plan.

        Identifies manual steps that could be automated and estimates
        time savings.
        """
        opportunities: list[AutomationOpportunity] = []
        total_manual = 0.0
        total_savings = 0.0

        for action in recovery_plan.actions:
            if action.can_automate:
                automated_time = action.estimated_minutes * 0.2
            else:
                automated_time = action.estimated_minutes * 0.7

            savings = action.estimated_minutes - automated_time
            total_manual += action.estimated_minutes

            # Priority score: weighted by savings and inverse complexity
            complexity_weight = {"low": 1.0, "medium": 0.6, "high": 0.3}.get(
                action.automation_complexity, 0.5
            )
            priority = min(100.0, savings * complexity_weight * 5.0)

            if action.can_automate:
                recommendation = (
                    f"Automate '{action.description}' to save "
                    f"~{savings:.0f} minutes per incident."
                )
            else:
                recommendation = (
                    f"Consider partial automation for '{action.description}'. "
                    f"Manual steps take {action.estimated_minutes:.0f} minutes."
                )

            opportunities.append(AutomationOpportunity(
                action_id=action.action_id,
                description=action.description,
                current_manual_time_minutes=round(action.estimated_minutes, 1),
                estimated_automated_time_minutes=round(automated_time, 1),
                time_savings_minutes=round(savings, 1),
                complexity=action.automation_complexity,
                priority_score=round(priority, 1),
                recommendation=recommendation,
            ))
            total_savings += savings

        # Sort by priority descending
        opportunities.sort(key=lambda o: o.priority_score, reverse=True)

        automatable_count = sum(1 for a in recovery_plan.actions if a.can_automate)
        coverage = (
            automatable_count / recovery_plan.total_actions * 100.0
            if recovery_plan.total_actions > 0
            else 0.0
        )

        return AutomationReport(
            opportunities=opportunities,
            total_manual_time_minutes=round(total_manual, 1),
            total_potential_savings_minutes=round(total_savings, 1),
            automation_coverage_percent=round(coverage, 1),
        )

    # ------------------------------------------------------------------
    # Timeline reconstruction
    # ------------------------------------------------------------------

    def reconstruct_timeline(
        self,
        component_id: str,
        severity: SeverityLevel,
        team_size: int = 3,
        automation_level: float = 0.2,
        has_runbook: bool = False,
    ) -> IncidentTimelineReconstruction:
        """Reconstruct an estimated incident timeline.

        Generates a realistic sequence of events from detection through
        resolution based on severity, team capability, and automation.
        """
        comp = self.graph.get_component(component_id)
        comp_name = comp.name if comp else component_id

        base_time = _SEVERITY_ESCALATION_MINUTES[severity]
        team_factor = 1.0 / math.sqrt(max(1, team_size))
        auto_factor = 1.0 - (automation_level * 0.5)
        runbook_factor = 0.7 if has_runbook else 1.0

        # Detection phase
        detect_time = max(1.0, base_time * 0.5 * auto_factor)
        # Acknowledgment
        ack_time = detect_time + max(0.5, base_time * 0.2 * team_factor)
        # Triage / diagnosis
        triage_end = ack_time + max(2.0, base_time * 1.0 * team_factor * runbook_factor)
        # Mitigation applied
        mitigate_time = triage_end + max(1.0, base_time * 0.8 * team_factor * auto_factor)
        # Full resolution
        resolve_time = mitigate_time + max(2.0, base_time * 0.5 * runbook_factor)

        entries: list[TimelineEntry] = []

        entries.append(TimelineEntry(
            timestamp_offset_minutes=0.0,
            phase="Detection",
            description=f"Monitoring alert fired for {comp_name}",
            actor="Monitoring System",
            action_type="alert",
        ))

        entries.append(TimelineEntry(
            timestamp_offset_minutes=round(detect_time, 1),
            phase="Detection",
            description=f"Alert detected and routed to on-call",
            actor="Alert Router",
            action_type="notification",
        ))

        entries.append(TimelineEntry(
            timestamp_offset_minutes=round(ack_time, 1),
            phase="Acknowledgment",
            description="On-call engineer acknowledges incident",
            actor="On-Call Engineer",
            action_type="acknowledgment",
        ))

        entries.append(TimelineEntry(
            timestamp_offset_minutes=round(ack_time + 1.0, 1),
            phase="Triage",
            description=f"Begin investigation of {comp_name}",
            actor="On-Call Engineer",
            action_type="investigation",
        ))

        if has_runbook:
            entries.append(TimelineEntry(
                timestamp_offset_minutes=round(ack_time + 2.0, 1),
                phase="Triage",
                description="Runbook located and being followed",
                actor="On-Call Engineer",
                action_type="runbook",
            ))

        if severity in (SeverityLevel.SEV1, SeverityLevel.SEV2):
            entries.append(TimelineEntry(
                timestamp_offset_minutes=round(ack_time + 3.0, 1),
                phase="Escalation",
                description=f"Incident escalated to {severity.value} war room",
                actor="Incident Commander",
                action_type="escalation",
            ))

        entries.append(TimelineEntry(
            timestamp_offset_minutes=round(triage_end, 1),
            phase="Triage",
            description="Root cause identified",
            actor="On-Call Engineer",
            action_type="diagnosis",
        ))

        entries.append(TimelineEntry(
            timestamp_offset_minutes=round(mitigate_time, 1),
            phase="Mitigation",
            description=f"Mitigation applied to {comp_name}",
            actor="On-Call Engineer",
            action_type="mitigation",
        ))

        entries.append(TimelineEntry(
            timestamp_offset_minutes=round(resolve_time, 1),
            phase="Resolution",
            description="Service fully restored and verified",
            actor="On-Call Engineer",
            action_type="resolution",
        ))

        entries.append(TimelineEntry(
            timestamp_offset_minutes=round(resolve_time + 5.0, 1),
            phase="Post-Incident",
            description="Post-incident review scheduled",
            actor="Incident Commander",
            action_type="scheduling",
        ))

        return IncidentTimelineReconstruction(
            entries=entries,
            total_duration_minutes=round(resolve_time + 5.0, 1),
            time_to_detect_minutes=round(detect_time, 1),
            time_to_acknowledge_minutes=round(ack_time, 1),
            time_to_mitigate_minutes=round(mitigate_time, 1),
            time_to_resolve_minutes=round(resolve_time, 1),
        )

    # ------------------------------------------------------------------
    # PIR / COE template generation
    # ------------------------------------------------------------------

    def generate_pir_template(
        self,
        component_id: str,
        severity: SeverityLevel,
        affected_ids: list[str],
        mttr: MTTREstimate,
        timeline: IncidentTimelineReconstruction,
    ) -> PIRTemplate:
        """Generate a Post-Incident Review (PIR) / Correction of Errors
        (COE) template.

        Includes timeline, five whys, impact analysis, and action items.
        """
        comp = self.graph.get_component(component_id)
        comp_name = comp.name if comp else component_id
        comp_type = comp.type.value if comp else "unknown"

        now = datetime.now(timezone.utc)

        # Build timeline entries
        tl_entries = [
            f"T+{e.timestamp_offset_minutes:.1f}m: [{e.phase}] {e.description}"
            for e in timeline.entries
        ]

        # Five whys analysis
        five_whys = self._generate_five_whys(component_id, comp_type)

        # Contributing factors
        factors = self._identify_contributing_factors(component_id)

        # Action items
        action_items = self._generate_action_items(
            component_id, severity, affected_ids
        )

        # Lessons learned
        lessons = self._generate_lessons_learned(
            component_id, severity, affected_ids, mttr
        )

        # Impact description
        impact = (
            f"Incident affected {len(affected_ids)} component(s). "
            f"Estimated MTTR: {mttr.adjusted_mttr_minutes} minutes. "
            f"Severity: {severity.value}."
        )

        # Detection and response effectiveness
        detect_eff = "Good" if timeline.time_to_detect_minutes < 10 else "Needs improvement"
        response_eff = "Good" if mttr.adjusted_mttr_minutes < 30 else "Needs improvement"

        # Mitigation steps
        mitigation_steps = self._generate_mitigation_steps(component_id)

        return PIRTemplate(
            incident_id=f"INC-{comp_name.upper().replace(' ', '-')}-{now.strftime('%Y%m%d')}",
            title=f"{severity.value} Incident: {comp_name} ({comp_type})",
            severity=severity,
            generated_at=now,
            summary=(
                f"A {severity.value} incident occurred on component "
                f"'{comp_name}' ({comp_type}), affecting "
                f"{len(affected_ids)} component(s). "
                f"The incident was resolved in approximately "
                f"{mttr.adjusted_mttr_minutes} minutes."
            ),
            timeline_entries=tl_entries,
            root_cause=f"Root cause was identified in component '{comp_name}' ({comp_type}).",
            contributing_factors=factors,
            impact_description=impact,
            affected_components=affected_ids,
            mitigation_steps=mitigation_steps,
            action_items=action_items,
            lessons_learned=lessons,
            five_whys=five_whys,
            detection_effectiveness=detect_eff,
            response_effectiveness=response_eff,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_affected_components(self, component_id: str) -> list[str]:
        """Get all transitively affected component IDs."""
        affected = self.graph.get_all_affected(component_id)
        return [component_id] + sorted(affected)

    def _dependency_ordered_components(
        self, component_ids: list[str]
    ) -> list[str]:
        """Order components so dependencies come before dependents.

        Leaf nodes (no further dependencies within the set) come first.
        """
        id_set = set(component_ids)
        ordered: list[str] = []
        visited: set[str] = set()

        def _visit(cid: str) -> None:
            if cid in visited or cid not in id_set:
                return
            visited.add(cid)
            # Visit dependencies first
            deps = self.graph.get_dependencies(cid)
            for dep in deps:
                if dep.id in id_set:
                    _visit(dep.id)
            ordered.append(cid)

        for cid in component_ids:
            _visit(cid)

        return ordered

    def _calculate_critical_path(
        self, actions: list[RecoveryAction]
    ) -> float:
        """Calculate the critical path duration through recovery actions."""
        if not actions:
            return 0.0

        action_map = {a.action_id: a for a in actions}
        earliest_finish: dict[str, float] = {}

        def _finish_time(aid: str) -> float:
            if aid in earliest_finish:
                return earliest_finish[aid]
            action = action_map[aid]
            if not action.depends_on:
                earliest_finish[aid] = action.estimated_minutes
            else:
                max_dep = max(
                    _finish_time(d) for d in action.depends_on
                    if d in action_map
                ) if any(d in action_map for d in action.depends_on) else 0.0
                earliest_finish[aid] = max_dep + action.estimated_minutes
            return earliest_finish[aid]

        return max(_finish_time(a.action_id) for a in actions)

    def _identify_parallel_groups(
        self, actions: list[RecoveryAction]
    ) -> list[list[str]]:
        """Group actions that can be executed in parallel."""
        if not actions:
            return []

        action_map = {a.action_id: a for a in actions}
        groups: list[list[str]] = []

        remaining = set(a.action_id for a in actions)
        completed: set[str] = set()

        while remaining:
            # Find actions whose dependencies are all completed
            ready = [
                aid for aid in remaining
                if all(
                    d in completed or d not in action_map
                    for d in action_map[aid].depends_on
                )
            ]
            if not ready:
                # Break cycle if there is one
                ready = [next(iter(remaining))]

            groups.append(sorted(ready))
            completed.update(ready)
            remaining -= set(ready)

        return groups

    def _generate_five_whys(
        self, component_id: str, comp_type: str
    ) -> list[str]:
        """Generate a five-whys analysis template."""
        comp = self.graph.get_component(component_id)
        comp_name = comp.name if comp else component_id

        whys = [
            f"Why did the incident occur? The {comp_type} component "
            f"'{comp_name}' experienced a failure.",
        ]

        # Check for single point of failure
        if comp and comp.replicas <= 1:
            whys.append(
                f"Why was there a single point of failure? "
                f"'{comp_name}' has only {comp.replicas} replica(s) "
                "with no redundancy."
            )
            whys.append(
                "Why was redundancy not configured? "
                "Infrastructure review did not flag this component as critical."
            )
        else:
            whys.append(
                f"Why did the failure propagate? Dependencies on "
                f"'{comp_name}' were not properly isolated."
            )
            whys.append(
                "Why were dependencies not isolated? Circuit breakers "
                "or bulkheads were not configured."
            )

        # Check monitoring
        if comp and comp.team.mean_acknowledge_time_minutes > 10:
            whys.append(
                "Why was detection slow? Monitoring thresholds are too "
                "conservative or alerting is not properly configured."
            )
        else:
            whys.append(
                "Why was the impact not contained earlier? "
                "Automated remediation was not in place."
            )

        whys.append(
            "Why was automated remediation not in place? "
            "The team has not yet invested in runbook automation "
            "for this failure mode."
        )

        return whys

    def _identify_contributing_factors(
        self, component_id: str
    ) -> list[str]:
        """Identify contributing factors for an incident."""
        comp = self.graph.get_component(component_id)
        factors: list[str] = []

        if comp is None:
            return ["Component not found in infrastructure graph."]

        if comp.replicas <= 1:
            factors.append("Single point of failure (no replicas)")

        if not comp.failover.enabled:
            factors.append("No failover configured")

        if not comp.autoscaling.enabled:
            factors.append("No autoscaling configured")

        if comp.team.runbook_coverage_percent < 50:
            factors.append(
                f"Low runbook coverage ({comp.team.runbook_coverage_percent}%)"
            )

        if comp.team.automation_percent < 30:
            factors.append(
                f"Low automation level ({comp.team.automation_percent}%)"
            )

        dependents = self.graph.get_dependents(component_id)
        if len(dependents) > 3:
            factors.append(
                f"High fan-in ({len(dependents)} dependents) increases blast radius"
            )

        if not factors:
            factors.append("No significant contributing factors identified")

        return factors

    def _generate_action_items(
        self,
        component_id: str,
        severity: SeverityLevel,
        affected_ids: list[str],
    ) -> list[dict[str, str]]:
        """Generate action items for the post-incident review."""
        comp = self.graph.get_component(component_id)
        items: list[dict[str, str]] = []

        if comp is None:
            return items

        if comp.replicas <= 1:
            items.append({
                "action": f"Add replicas to {comp.name}",
                "owner": "Infrastructure Team",
                "priority": "P1",
                "deadline": "2 weeks",
            })

        if not comp.failover.enabled:
            items.append({
                "action": f"Configure failover for {comp.name}",
                "owner": "SRE Team",
                "priority": "P1",
                "deadline": "2 weeks",
            })

        if comp.team.runbook_coverage_percent < 70:
            items.append({
                "action": f"Create runbook for {comp.name} failure modes",
                "owner": "On-Call Team",
                "priority": "P2",
                "deadline": "4 weeks",
            })

        if comp.team.automation_percent < 50:
            items.append({
                "action": f"Automate recovery procedures for {comp.name}",
                "owner": "Platform Team",
                "priority": "P2",
                "deadline": "6 weeks",
            })

        if len(affected_ids) > 3:
            items.append({
                "action": "Add circuit breakers to limit blast radius",
                "owner": "Architecture Team",
                "priority": "P1",
                "deadline": "3 weeks",
            })

        if severity in (SeverityLevel.SEV1, SeverityLevel.SEV2):
            items.append({
                "action": "Review and improve monitoring and alerting",
                "owner": "Observability Team",
                "priority": "P1",
                "deadline": "2 weeks",
            })

        return items

    def _generate_lessons_learned(
        self,
        component_id: str,
        severity: SeverityLevel,
        affected_ids: list[str],
        mttr: MTTREstimate,
    ) -> list[str]:
        """Generate lessons learned from the incident."""
        comp = self.graph.get_component(component_id)
        lessons: list[str] = []

        if comp is None:
            return lessons

        if mttr.adjusted_mttr_minutes > 30:
            lessons.append(
                f"MTTR of {mttr.adjusted_mttr_minutes} minutes exceeds the "
                "30-minute target. Invest in automation and runbooks."
            )

        if comp.replicas <= 1:
            lessons.append(
                "Single points of failure significantly increase incident "
                "impact. All critical components should have redundancy."
            )

        if len(affected_ids) > 3:
            lessons.append(
                "Large blast radius indicates tight coupling. "
                "Implement circuit breakers and graceful degradation."
            )

        if severity in (SeverityLevel.SEV1, SeverityLevel.SEV2):
            lessons.append(
                "High-severity incidents require documented escalation "
                "procedures and regular war room drills."
            )

        if not lessons:
            lessons.append(
                "Incident response was effective. Continue regular "
                "chaos engineering exercises to maintain readiness."
            )

        return lessons

    def _generate_mitigation_steps(
        self, component_id: str
    ) -> list[str]:
        """Generate mitigation steps for the incident."""
        comp = self.graph.get_component(component_id)
        steps: list[str] = []

        if comp is None:
            return ["Investigate and resolve manually."]

        type_actions = _RECOVERY_ACTIONS_BY_TYPE.get(
            comp.type.value,
            [(RecoveryActionType.MANUAL_INTERVENTION, "Manual recovery", 30.0, False)],
        )

        for action_type, desc, est_min, can_auto in type_actions:
            prefix = "[Automated] " if can_auto else "[Manual] "
            steps.append(f"{prefix}{desc} (est. {est_min:.0f} min)")

        return steps

    def _calculate_readiness_score(
        self,
        comp: Component,
        has_runbook: bool,
        automation_level: float,
        team_size: int,
        escalation: EscalationChain,
        comm_eff: CommunicationEffectiveness,
    ) -> float:
        """Calculate overall incident response readiness score (0-100).

        Factors:
        - Infrastructure resilience (replicas, failover, autoscaling): 25 pts
        - Runbook & automation coverage: 25 pts
        - Team readiness (size, coverage, ack time): 25 pts
        - Communication & escalation effectiveness: 25 pts
        """
        # Infrastructure score (0-25)
        infra_score = 5.0  # base
        if comp.replicas > 1:
            infra_score += 8.0
        if comp.failover.enabled:
            infra_score += 7.0
        if comp.autoscaling.enabled:
            infra_score += 5.0

        # Runbook & automation score (0-25)
        runbook_score = 0.0
        if has_runbook:
            runbook_score += 12.0
        runbook_score += automation_level * 13.0

        # Team score (0-25)
        team_score = min(25.0, (
            min(10.0, team_size * 3.0)
            + min(8.0, (comp.team.oncall_coverage_hours / 24.0) * 8.0)
            + max(0.0, 7.0 - comp.team.mean_acknowledge_time_minutes * 0.7)
        ))

        # Communication score (0-25)
        comm_score = comm_eff.coverage_score * 0.25

        total = infra_score + runbook_score + team_score + comm_score
        return max(0.0, min(100.0, total))
