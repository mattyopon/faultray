"""Failure injection scheduler — automated chaos experiment scheduling.

Schedules and manages recurring chaos experiments against infrastructure,
with blackout windows, gradual escalation, and automatic result tracking.
Like a Chaos Calendar but with intelligent scheduling and escalation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


class InjectionType(str, Enum):
    """Types of failure injection."""

    COMPONENT_KILL = "component_kill"
    LATENCY_SPIKE = "latency_spike"
    CPU_STRESS = "cpu_stress"
    MEMORY_PRESSURE = "memory_pressure"
    NETWORK_PARTITION = "network_partition"
    DISK_FULL = "disk_full"
    DEPENDENCY_TIMEOUT = "dependency_timeout"
    TRAFFIC_FLOOD = "traffic_flood"


class ScheduleFrequency(str, Enum):
    """How often to run the injection."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class EscalationLevel(str, Enum):
    """Chaos escalation level — start gentle, increase over time."""

    CANARY = "canary"       # Single replica, low impact
    PARTIAL = "partial"     # Some replicas, moderate impact
    FULL = "full"           # Full component, high impact
    CASCADING = "cascading"  # Full + dependent components


@dataclass
class BlackoutWindow:
    """Time window during which injections are suppressed."""

    name: str
    start_hour: int  # 0-23 UTC
    end_hour: int    # 0-23 UTC
    days_of_week: list[int]  # 0=Mon, 6=Sun. Empty = all days
    reason: str


@dataclass
class InjectionTarget:
    """Target specification for an injection."""

    component_id: str
    component_name: str
    injection_type: InjectionType
    parameters: dict[str, Any] = field(default_factory=dict)
    duration_seconds: int = 60
    escalation: EscalationLevel = EscalationLevel.CANARY


@dataclass
class ScheduledInjection:
    """A scheduled failure injection."""

    id: str
    name: str
    description: str
    target: InjectionTarget
    frequency: ScheduleFrequency
    enabled: bool = True
    next_run: str = ""
    last_run: str = ""
    run_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    auto_escalate: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class InjectionResult:
    """Result of a single injection run."""

    injection_id: str
    injection_name: str
    timestamp: str
    target_component: str
    injection_type: str
    escalation_level: str
    passed: bool
    blast_radius: int  # number of affected components
    recovery_time_seconds: int
    observations: list[str]


@dataclass
class SchedulerReport:
    """Report on the injection scheduler state."""

    scheduled_injections: list[ScheduledInjection]
    total_scheduled: int
    active_count: int
    paused_count: int
    blackout_windows: list[BlackoutWindow]
    next_injections: list[dict]  # next 5 scheduled
    recent_results: list[InjectionResult]
    pass_rate: float
    coverage_score: float  # % of components with scheduled injections
    recommendations: list[str]


# Default blackout windows
_DEFAULT_BLACKOUTS = [
    BlackoutWindow(
        name="Business Hours Peak",
        start_hour=9,
        end_hour=17,
        days_of_week=[0, 1, 2, 3, 4],  # Mon-Fri
        reason="Avoid peak business hours",
    ),
    BlackoutWindow(
        name="Month End",
        start_hour=0,
        end_hour=23,
        days_of_week=[],  # checked separately by date
        reason="Avoid financial close periods",
    ),
]

# Injection type applicability by component type
_APPLICABLE_INJECTIONS: dict[ComponentType, list[InjectionType]] = {
    ComponentType.WEB_SERVER: [
        InjectionType.COMPONENT_KILL, InjectionType.LATENCY_SPIKE,
        InjectionType.CPU_STRESS, InjectionType.TRAFFIC_FLOOD,
    ],
    ComponentType.APP_SERVER: [
        InjectionType.COMPONENT_KILL, InjectionType.LATENCY_SPIKE,
        InjectionType.CPU_STRESS, InjectionType.MEMORY_PRESSURE,
    ],
    ComponentType.DATABASE: [
        InjectionType.COMPONENT_KILL, InjectionType.LATENCY_SPIKE,
        InjectionType.DISK_FULL, InjectionType.MEMORY_PRESSURE,
    ],
    ComponentType.CACHE: [
        InjectionType.COMPONENT_KILL, InjectionType.MEMORY_PRESSURE,
    ],
    ComponentType.QUEUE: [
        InjectionType.COMPONENT_KILL, InjectionType.LATENCY_SPIKE,
        InjectionType.DISK_FULL,
    ],
    ComponentType.LOAD_BALANCER: [
        InjectionType.COMPONENT_KILL, InjectionType.LATENCY_SPIKE,
        InjectionType.TRAFFIC_FLOOD,
    ],
    ComponentType.STORAGE: [
        InjectionType.COMPONENT_KILL, InjectionType.DISK_FULL,
        InjectionType.LATENCY_SPIKE,
    ],
    ComponentType.DNS: [
        InjectionType.COMPONENT_KILL, InjectionType.LATENCY_SPIKE,
    ],
    ComponentType.EXTERNAL_API: [
        InjectionType.DEPENDENCY_TIMEOUT, InjectionType.LATENCY_SPIKE,
    ],
    ComponentType.CUSTOM: [
        InjectionType.COMPONENT_KILL, InjectionType.LATENCY_SPIKE,
    ],
}


class InjectionScheduler:
    """Schedule and manage automated chaos experiments."""

    def __init__(self) -> None:
        self._injections: dict[str, ScheduledInjection] = {}
        self._blackouts: list[BlackoutWindow] = list(_DEFAULT_BLACKOUTS)
        self._results: list[InjectionResult] = []
        self._next_id = 1

    def auto_schedule(
        self,
        graph: InfraGraph,
        frequency: ScheduleFrequency = ScheduleFrequency.WEEKLY,
        escalation: EscalationLevel = EscalationLevel.CANARY,
    ) -> list[ScheduledInjection]:
        """Automatically create injection schedules for all components."""
        created: list[ScheduledInjection] = []

        for comp in graph.components.values():
            applicable = _APPLICABLE_INJECTIONS.get(
                comp.type, [InjectionType.COMPONENT_KILL]
            )
            # Pick the most relevant injection type
            injection_type = applicable[0]

            inj = self.schedule(
                name=f"Auto: {injection_type.value} on {comp.name}",
                description=f"Automated {injection_type.value} injection for {comp.name}",
                target=InjectionTarget(
                    component_id=comp.id,
                    component_name=comp.name,
                    injection_type=injection_type,
                    duration_seconds=60,
                    escalation=escalation,
                ),
                frequency=frequency,
            )
            created.append(inj)

        return created

    def schedule(
        self,
        name: str,
        description: str,
        target: InjectionTarget,
        frequency: ScheduleFrequency,
        enabled: bool = True,
        auto_escalate: bool = True,
        tags: list[str] | None = None,
    ) -> ScheduledInjection:
        """Schedule a new injection."""
        inj_id = f"inj-{self._next_id:04d}"
        self._next_id += 1

        now = datetime.now(timezone.utc)
        next_run = self._calculate_next_run(now, frequency)

        inj = ScheduledInjection(
            id=inj_id,
            name=name,
            description=description,
            target=target,
            frequency=frequency,
            enabled=enabled,
            next_run=next_run.isoformat(),
            auto_escalate=auto_escalate,
            tags=tags or [],
        )
        self._injections[inj_id] = inj
        return inj

    def unschedule(self, injection_id: str) -> bool:
        """Remove a scheduled injection."""
        if injection_id in self._injections:
            del self._injections[injection_id]
            return True
        return False

    def pause(self, injection_id: str) -> bool:
        """Pause a scheduled injection."""
        if injection_id in self._injections:
            self._injections[injection_id].enabled = False
            return True
        return False

    def resume(self, injection_id: str) -> bool:
        """Resume a paused injection."""
        if injection_id in self._injections:
            self._injections[injection_id].enabled = True
            return True
        return False

    def simulate_injection(
        self,
        graph: InfraGraph,
        injection_id: str,
    ) -> InjectionResult | None:
        """Simulate running an injection against the graph."""
        inj = self._injections.get(injection_id)
        if inj is None:
            return None

        comp = graph.get_component(inj.target.component_id)
        if comp is None:
            return None

        # Simulate the injection
        observations: list[str] = []
        blast_radius = 0
        passed = True
        recovery_time = 30

        target = inj.target
        affected = graph.get_all_affected(target.component_id)
        blast_radius = len(affected)

        if target.injection_type == InjectionType.COMPONENT_KILL:
            if comp.replicas <= 1:
                passed = False
                observations.append(f"{comp.name} has no replicas — service outage")
                recovery_time = 300
            else:
                observations.append(f"{comp.name} survived — {comp.replicas - 1} replicas remaining")
                recovery_time = 10

        elif target.injection_type == InjectionType.LATENCY_SPIKE:
            if comp.capacity.timeout_seconds < 5:
                observations.append(f"{comp.name} may timeout with added latency")
                passed = False
            else:
                observations.append(f"{comp.name} timeout ({comp.capacity.timeout_seconds}s) provides margin")

        elif target.injection_type in (InjectionType.CPU_STRESS, InjectionType.MEMORY_PRESSURE):
            util = comp.utilization()
            if util > 70:
                passed = False
                observations.append(f"{comp.name} already at {util:.0f}% — stress will cause overload")
            else:
                headroom = 100 - util
                observations.append(f"{comp.name} has {headroom:.0f}% headroom")

        elif target.injection_type == InjectionType.DISK_FULL:
            if comp.security.backup_enabled:
                observations.append(f"{comp.name} has backups — data recoverable")
            else:
                passed = False
                observations.append(f"{comp.name} has no backups — potential data loss")

        elif target.injection_type == InjectionType.DEPENDENCY_TIMEOUT:
            deps = graph.get_dependents(target.component_id)
            for dep in deps:
                edge = graph.get_dependency_edge(dep.id, target.component_id)
                if edge and edge.circuit_breaker.enabled:
                    observations.append(f"{dep.name} has circuit breaker — will trip")
                else:
                    passed = False
                    observations.append(f"{dep.name} lacks circuit breaker — will hang")

        elif target.injection_type == InjectionType.TRAFFIC_FLOOD:
            if comp.autoscaling.enabled:
                observations.append(f"{comp.name} will autoscale to handle traffic")
            elif comp.replicas > 2:
                observations.append(f"{comp.name} has {comp.replicas} replicas to absorb load")
            else:
                passed = False
                observations.append(f"{comp.name} cannot handle traffic spike")

        elif target.injection_type == InjectionType.NETWORK_PARTITION:
            if comp.failover.enabled:
                observations.append(f"{comp.name} has failover — will switch to backup")
            else:
                passed = False
                observations.append(f"{comp.name} isolated with no failover")

        if blast_radius > 3:
            observations.append(f"WARNING: Blast radius of {blast_radius} components")
            if blast_radius > 5:
                passed = False

        result = InjectionResult(
            injection_id=injection_id,
            injection_name=inj.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            target_component=comp.name,
            injection_type=target.injection_type.value,
            escalation_level=target.escalation.value,
            passed=passed,
            blast_radius=blast_radius,
            recovery_time_seconds=recovery_time,
            observations=observations,
        )

        # Update injection stats
        inj.run_count += 1
        if passed:
            inj.pass_count += 1
        else:
            inj.fail_count += 1
        inj.last_run = result.timestamp

        # Auto-escalate if passing consistently
        if inj.auto_escalate and passed and inj.pass_count >= 3:
            self._escalate(inj)

        self._results.append(result)
        return result

    def is_in_blackout(self, dt: datetime | None = None) -> bool:
        """Check if the given time falls within a blackout window."""
        if dt is None:
            dt = datetime.now(timezone.utc)
        hour = dt.hour
        weekday = dt.weekday()

        for window in self._blackouts:
            if window.days_of_week and weekday not in window.days_of_week:
                continue
            if window.start_hour <= hour < window.end_hour:
                return True
        return False

    def add_blackout(self, window: BlackoutWindow) -> None:
        """Add a blackout window."""
        self._blackouts.append(window)

    def remove_blackout(self, name: str) -> bool:
        """Remove a blackout window by name."""
        original_count = len(self._blackouts)
        self._blackouts = [w for w in self._blackouts if w.name != name]
        return len(self._blackouts) < original_count

    def get_report(self, graph: InfraGraph) -> SchedulerReport:
        """Generate a report on the scheduler state."""
        injections = list(self._injections.values())
        active = sum(1 for i in injections if i.enabled)
        paused = sum(1 for i in injections if not i.enabled)

        # Next injections
        sorted_inj = sorted(
            [i for i in injections if i.enabled and i.next_run],
            key=lambda i: i.next_run,
        )
        next_five = [
            {"id": i.id, "name": i.name, "next_run": i.next_run}
            for i in sorted_inj[:5]
        ]

        # Pass rate
        total_runs = sum(i.run_count for i in injections)
        total_passes = sum(i.pass_count for i in injections)
        pass_rate = (total_passes / total_runs * 100) if total_runs > 0 else 0

        # Coverage
        targeted_components = {i.target.component_id for i in injections}
        total_components = len(graph.components)
        coverage = (
            len(targeted_components) / total_components * 100
            if total_components > 0
            else 0
        )

        # Recommendations
        recommendations = self._generate_recommendations(
            graph, injections, pass_rate, coverage
        )

        return SchedulerReport(
            scheduled_injections=injections,
            total_scheduled=len(injections),
            active_count=active,
            paused_count=paused,
            blackout_windows=self._blackouts,
            next_injections=next_five,
            recent_results=self._results[-10:],
            pass_rate=round(pass_rate, 1),
            coverage_score=round(coverage, 1),
            recommendations=recommendations,
        )

    def _calculate_next_run(
        self, now: datetime, frequency: ScheduleFrequency
    ) -> datetime:
        """Calculate the next run time based on frequency."""
        deltas = {
            ScheduleFrequency.DAILY: timedelta(days=1),
            ScheduleFrequency.WEEKLY: timedelta(weeks=1),
            ScheduleFrequency.BIWEEKLY: timedelta(weeks=2),
            ScheduleFrequency.MONTHLY: timedelta(days=30),
            ScheduleFrequency.QUARTERLY: timedelta(days=90),
        }
        return now + deltas[frequency]

    def _escalate(self, inj: ScheduledInjection) -> None:
        """Escalate the injection to the next level."""
        levels = [
            EscalationLevel.CANARY,
            EscalationLevel.PARTIAL,
            EscalationLevel.FULL,
            EscalationLevel.CASCADING,
        ]
        current_idx = levels.index(inj.target.escalation)
        if current_idx < len(levels) - 1:
            inj.target.escalation = levels[current_idx + 1]

    def _generate_recommendations(
        self,
        graph: InfraGraph,
        injections: list[ScheduledInjection],
        pass_rate: float,
        coverage: float,
    ) -> list[str]:
        """Generate recommendations for the chaos schedule."""
        recs: list[str] = []

        if coverage < 50:
            recs.append(
                f"Coverage is {coverage:.0f}% — schedule injections for "
                f"more components to improve resilience validation"
            )

        if pass_rate < 70 and pass_rate > 0:
            recs.append(
                f"Pass rate is {pass_rate:.0f}% — address failing injections "
                f"before escalating chaos level"
            )

        # Check for untested component types
        tested_types = {
            graph.get_component(i.target.component_id).type
            for i in injections
            if graph.get_component(i.target.component_id) is not None
        }
        all_types = {c.type for c in graph.components.values()}
        untested = all_types - tested_types
        if untested:
            type_names = ", ".join(t.value for t in untested)
            recs.append(f"Component types not covered: {type_names}")

        # Check for stuck escalation
        stuck = [
            i for i in injections
            if i.pass_count > 5 and i.target.escalation == EscalationLevel.CANARY
        ]
        if stuck:
            recs.append(
                f"{len(stuck)} injection(s) consistently passing at CANARY "
                f"level — consider manual escalation"
            )

        return recs
