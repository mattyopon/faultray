"""Deployment window risk analyzer — assess deployment timing risks.

Evaluates deployment timing based on traffic patterns, team availability,
historical incident data, and change freeze schedules.  Recommends optimal
deployment windows and simulates peak-hour deployment impact.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType, HealthStatus
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WindowRisk(str, Enum):
    """Risk level of a deployment window."""

    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class DeploymentType(str, Enum):
    """Type of deployment being performed."""

    FEATURE_RELEASE = "feature_release"
    HOTFIX = "hotfix"
    INFRASTRUCTURE_CHANGE = "infrastructure_change"
    CONFIG_UPDATE = "config_update"
    DATABASE_MIGRATION = "database_migration"
    DEPENDENCY_UPGRADE = "dependency_upgrade"
    ROLLBACK = "rollback"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class TimeWindow(BaseModel):
    """A deployment time window."""

    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=0, le=23)
    day_of_week: int = Field(ge=0, le=6)  # 0=Mon, 6=Sun
    timezone: str = "UTC"


class WindowAssessment(BaseModel):
    """Full risk assessment for a deployment window."""

    window: TimeWindow
    risk: WindowRisk
    risk_score: float = Field(ge=0, le=100)
    traffic_level: str
    team_availability: float = Field(ge=0, le=1)
    recent_incidents_24h: int = Field(ge=0)
    change_freeze_active: bool
    recommendations: list[str] = Field(default_factory=list)
    optimal_alternative: TimeWindow | None = None


class PeakDeployResult(BaseModel):
    """Result of simulating a deployment during peak traffic."""

    estimated_error_rate_increase: float = Field(ge=0)
    estimated_latency_increase_ms: float = Field(ge=0)
    affected_users_percent: float = Field(ge=0, le=100)
    rollback_risk: float = Field(ge=0, le=100)
    capacity_headroom_percent: float
    safe_to_deploy: bool
    warnings: list[str] = Field(default_factory=list)


class ScheduledDeploy(BaseModel):
    """A scheduled deployment with its recommended window."""

    deploy_type: DeploymentType
    recommended_window: TimeWindow
    risk_score: float = Field(ge=0, le=100)
    priority: int = Field(ge=1)
    estimated_duration_minutes: float = Field(ge=0)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants / lookup tables
# ---------------------------------------------------------------------------

# Relative traffic level by hour (0-23).  Normalised to 0.0-1.0.
_HOURLY_TRAFFIC: list[float] = [
    0.10, 0.08, 0.06, 0.05, 0.05, 0.07,  # 00-05
    0.15, 0.30, 0.55, 0.75, 0.85, 0.90,  # 06-11
    0.80, 0.85, 0.90, 0.95, 1.00, 0.95,  # 12-17
    0.85, 0.75, 0.60, 0.45, 0.30, 0.18,  # 18-23
]

# Day-of-week traffic multiplier (Mon-Sun).
_DAY_MULTIPLIER: list[float] = [
    1.0, 1.0, 1.0, 1.0, 0.95, 0.55, 0.50,
]

# Team availability by hour — assumes core hours 09-17 local.
_TEAM_AVAILABILITY: list[float] = [
    0.10, 0.05, 0.05, 0.05, 0.05, 0.05,  # 00-05
    0.15, 0.30, 0.60, 0.90, 0.95, 0.95,  # 06-11
    0.85, 0.95, 0.95, 0.95, 0.90, 0.70,  # 12-17
    0.40, 0.25, 0.20, 0.15, 0.10, 0.10,  # 18-23
]

# Weekend availability multiplier.
_WEEKEND_AVAIL_MULTIPLIER = 0.3

# Base risk weights by deployment type.
_DEPLOY_TYPE_WEIGHT: dict[DeploymentType, float] = {
    DeploymentType.FEATURE_RELEASE: 1.0,
    DeploymentType.HOTFIX: 0.7,
    DeploymentType.INFRASTRUCTURE_CHANGE: 1.3,
    DeploymentType.CONFIG_UPDATE: 0.4,
    DeploymentType.DATABASE_MIGRATION: 1.5,
    DeploymentType.DEPENDENCY_UPGRADE: 1.1,
    DeploymentType.ROLLBACK: 0.6,
}

# Estimated duration in minutes by deployment type.
_DEPLOY_DURATION: dict[DeploymentType, float] = {
    DeploymentType.FEATURE_RELEASE: 30.0,
    DeploymentType.HOTFIX: 15.0,
    DeploymentType.INFRASTRUCTURE_CHANGE: 45.0,
    DeploymentType.CONFIG_UPDATE: 10.0,
    DeploymentType.DATABASE_MIGRATION: 60.0,
    DeploymentType.DEPENDENCY_UPGRADE: 25.0,
    DeploymentType.ROLLBACK: 10.0,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _traffic_level_for(hour: int, day: int) -> float:
    """Return normalised traffic level (0-1) for a given hour and day."""
    return _HOURLY_TRAFFIC[hour] * _DAY_MULTIPLIER[day]


def _traffic_label(level: float) -> str:
    """Human-readable label for a traffic level."""
    if level < 0.15:
        return "very_low"
    if level < 0.35:
        return "low"
    if level < 0.60:
        return "moderate"
    if level < 0.80:
        return "high"
    return "peak"


def _team_avail(hour: int, day: int) -> float:
    """Return normalised team availability for hour + day."""
    base = _TEAM_AVAILABILITY[hour]
    if day >= 5:  # weekend
        base *= _WEEKEND_AVAIL_MULTIPLIER
    return min(base, 1.0)


def _risk_from_score(score: float) -> WindowRisk:
    """Map a numeric risk score (0-100) to a WindowRisk enum."""
    if score < 20:
        return WindowRisk.LOW
    if score < 40:
        return WindowRisk.MODERATE
    if score < 60:
        return WindowRisk.ELEVATED
    if score < 80:
        return WindowRisk.HIGH
    return WindowRisk.CRITICAL


def _graph_health_penalty(graph: InfraGraph) -> float:
    """Return a penalty (0-30) based on current graph component health."""
    penalty = 0.0
    for comp in graph.components.values():
        if comp.health == HealthStatus.DOWN:
            penalty += 10.0
        elif comp.health == HealthStatus.OVERLOADED:
            penalty += 6.0
        elif comp.health == HealthStatus.DEGRADED:
            penalty += 3.0
    return min(penalty, 30.0)


def _spof_count(graph: InfraGraph) -> int:
    """Count single-points-of-failure (single-replica components)."""
    return sum(
        1 for c in graph.components.values()
        if c.replicas == 1 and c.type != ComponentType.DNS
    )


def _graph_complexity(graph: InfraGraph) -> float:
    """Return a complexity factor (0-10) based on graph size."""
    n = len(graph.components)
    if n <= 3:
        return 1.0
    if n <= 10:
        return 3.0
    if n <= 25:
        return 5.0
    return min(10.0, 5.0 + (n - 25) * 0.1)


def _incident_penalty(count: int) -> float:
    """Return a penalty (0-25) for recent incidents."""
    if count == 0:
        return 0.0
    if count <= 2:
        return 8.0
    if count <= 5:
        return 15.0
    return 25.0


def _window_span_hours(window: TimeWindow) -> int:
    """Return the number of hours in a window (handles wrap-around)."""
    if window.end_hour > window.start_hour:
        return window.end_hour - window.start_hour
    if window.end_hour == window.start_hour:
        return 1
    return 24 - window.start_hour + window.end_hour


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DeploymentWindowEngine:
    """Stateless engine for deployment window risk analysis."""

    # -- public API ---------------------------------------------------------

    def calculate_risk_score(
        self,
        graph: InfraGraph,
        window: TimeWindow,
        deploy_type: DeploymentType,
    ) -> float:
        """Return a risk score (0-100) for the given window + deployment type."""
        traffic = _traffic_level_for(window.start_hour, window.day_of_week)
        avail = _team_avail(window.start_hour, window.day_of_week)

        # Base traffic risk (0-30)
        traffic_risk = traffic * 30.0

        # Inverse-availability risk (0-20)
        avail_risk = (1.0 - avail) * 20.0

        # Deploy-type weight (scale 0.4-1.5 → 0-15)
        weight = _DEPLOY_TYPE_WEIGHT.get(deploy_type, 1.0)
        type_risk = weight * 10.0

        # Infrastructure health penalty (0-30)
        health_risk = _graph_health_penalty(graph)

        # SPOF penalty (0-10)
        spofs = _spof_count(graph)
        spof_risk = min(spofs * 3.0, 10.0)

        # Complexity
        complexity_risk = _graph_complexity(graph) * 0.5

        raw = traffic_risk + avail_risk + type_risk + health_risk + spof_risk + complexity_risk
        return min(max(round(raw, 2), 0.0), 100.0)

    def check_change_freeze(
        self,
        window: TimeWindow,
        freeze_windows: list[TimeWindow],
    ) -> bool:
        """Return True when *window* overlaps any freeze window."""
        for fw in freeze_windows:
            if fw.day_of_week != window.day_of_week:
                continue
            # Build hour-sets for both windows to handle wrap-around.
            win_hours = self._hour_set(window)
            freeze_hours = self._hour_set(fw)
            if win_hours & freeze_hours:
                return True
        return False

    def assess_window(
        self,
        graph: InfraGraph,
        window: TimeWindow,
        deploy_type: DeploymentType,
        *,
        recent_incidents_24h: int = 0,
        freeze_windows: list[TimeWindow] | None = None,
    ) -> WindowAssessment:
        """Produce a full WindowAssessment for the given parameters."""
        freeze_windows = freeze_windows or []
        freeze_active = self.check_change_freeze(window, freeze_windows)

        score = self.calculate_risk_score(graph, window, deploy_type)

        # Boost score for incidents.
        score = min(score + _incident_penalty(recent_incidents_24h), 100.0)

        # Boost score when freeze is active.
        if freeze_active:
            score = min(score + 20.0, 100.0)

        traffic = _traffic_level_for(window.start_hour, window.day_of_week)
        avail = _team_avail(window.start_hour, window.day_of_week)

        risk = _risk_from_score(score)
        recs = self._build_recommendations(
            risk, traffic, avail, freeze_active, recent_incidents_24h, deploy_type, graph,
        )

        optimal = None
        if risk in (WindowRisk.HIGH, WindowRisk.CRITICAL):
            optimal = self.find_optimal_window(graph, deploy_type)

        return WindowAssessment(
            window=window,
            risk=risk,
            risk_score=score,
            traffic_level=_traffic_label(traffic),
            team_availability=round(avail, 2),
            recent_incidents_24h=recent_incidents_24h,
            change_freeze_active=freeze_active,
            recommendations=recs,
            optimal_alternative=optimal,
        )

    def find_optimal_window(
        self,
        graph: InfraGraph,
        deploy_type: DeploymentType,
        constraints: dict[str, object] | None = None,
    ) -> TimeWindow:
        """Search weekdays for the lowest-risk 1-hour window.

        *constraints* may include:
        - ``min_availability`` (float): minimum team availability (default 0.5).
        - ``max_traffic`` (float): maximum normalised traffic level (default 0.5).
        - ``allowed_days`` (list[int]): days of week to consider (default 0-4).
        """
        constraints = constraints or {}
        min_avail: float = float(constraints.get("min_availability", 0.3))
        max_traffic: float = float(constraints.get("max_traffic", 0.8))
        allowed_days: list[int] = list(constraints.get("allowed_days", [0, 1, 2, 3, 4]))  # type: ignore[arg-type]

        best_score = 200.0
        best_window: TimeWindow | None = None

        # Also track the best unconstrained candidate in case no window
        # satisfies both min_avail and max_traffic.
        fallback_score = 200.0
        fallback_window: TimeWindow | None = None

        for day in allowed_days:
            for hour in range(24):
                tw = TimeWindow(start_hour=hour, end_hour=(hour + 1) % 24, day_of_week=day)
                sc = self.calculate_risk_score(graph, tw, deploy_type)

                # Track fallback (best score on allowed days, ignoring avail/traffic).
                if sc < fallback_score:
                    fallback_score = sc
                    fallback_window = tw

                traffic = _traffic_level_for(hour, day)
                avail = _team_avail(hour, day)
                if avail < min_avail:
                    continue
                if traffic > max_traffic:
                    continue

                if sc < best_score:
                    best_score = sc
                    best_window = tw

        if best_window is not None:
            return best_window
        if fallback_window is not None:
            return fallback_window
        # Absolute fallback — should never be reached when allowed_days is non-empty.
        return TimeWindow(start_hour=10, end_hour=11, day_of_week=allowed_days[0] if allowed_days else 1)

    def estimate_rollback_window(
        self,
        graph: InfraGraph,
        deploy_type: DeploymentType,
    ) -> float:
        """Estimate time (minutes) available for a safe rollback.

        The window is based on deployment type duration, graph complexity,
        and whether failover mechanisms exist.
        """
        base_duration = _DEPLOY_DURATION.get(deploy_type, 30.0)

        # Failover-enabled components speed up rollback.
        total = len(graph.components)
        if total == 0:
            return base_duration

        failover_fraction = sum(
            1 for c in graph.components.values() if c.failover.enabled
        ) / total

        complexity = _graph_complexity(graph)

        # Rollback window = base * (1 + failover_benefit - complexity_penalty)
        failover_benefit = failover_fraction * 0.5
        complexity_penalty = complexity * 0.03
        factor = max(1.0 + failover_benefit - complexity_penalty, 0.3)
        return round(base_duration * factor, 1)

    def simulate_deploy_during_peak(
        self,
        graph: InfraGraph,
        deploy_type: DeploymentType,
    ) -> PeakDeployResult:
        """Simulate the impact of deploying during peak traffic (hour 16, weekday)."""
        peak_window = TimeWindow(start_hour=16, end_hour=17, day_of_week=2)
        score = self.calculate_risk_score(graph, peak_window, deploy_type)

        total = len(graph.components)
        if total == 0:
            return PeakDeployResult(
                estimated_error_rate_increase=0.0,
                estimated_latency_increase_ms=0.0,
                affected_users_percent=0.0,
                rollback_risk=0.0,
                capacity_headroom_percent=100.0,
                safe_to_deploy=True,
                warnings=[],
            )

        weight = _DEPLOY_TYPE_WEIGHT.get(deploy_type, 1.0)

        # Error rate increase based on score and deploy weight.
        error_increase = round(score * weight * 0.02, 2)

        # Latency increase.
        health_pen = _graph_health_penalty(graph)
        latency_increase = round((score + health_pen) * weight * 1.5, 1)

        # Affected users (higher traffic → more users).
        traffic = _traffic_level_for(16, 2)
        affected = round(min(traffic * score * 0.8, 100.0), 1)

        # Rollback risk.
        rollback_risk = round(min(score * 1.1, 100.0), 1)

        # Capacity headroom — look at average utilisation across components.
        utilizations = [c.utilization() for c in graph.components.values()]
        avg_util = sum(utilizations) / total if utilizations else 0.0
        headroom = round(max(100.0 - avg_util - score * 0.3, 0.0), 1)

        warnings: list[str] = []
        if affected > 30:
            warnings.append("High user impact expected during peak")
        if headroom < 20:
            warnings.append("Low capacity headroom during deployment")
        if health_pen > 10:
            warnings.append("Unhealthy components increase deployment risk")
        if _spof_count(graph) > 0:
            warnings.append("Single points of failure present in graph")
        if deploy_type == DeploymentType.DATABASE_MIGRATION:
            warnings.append("Database migrations during peak are high risk")

        safe = score < 50 and headroom > 15 and health_pen < 10

        return PeakDeployResult(
            estimated_error_rate_increase=error_increase,
            estimated_latency_increase_ms=latency_increase,
            affected_users_percent=affected,
            rollback_risk=rollback_risk,
            capacity_headroom_percent=headroom,
            safe_to_deploy=safe,
            warnings=warnings,
        )

    def recommend_deployment_schedule(
        self,
        graph: InfraGraph,
        deploys: list[DeploymentType],
    ) -> list[ScheduledDeploy]:
        """Build a prioritised deployment schedule for multiple deployments.

        Lower-risk deployments go first; each subsequent deployment gets a
        distinct window to avoid contention.
        """
        if not deploys:
            return []

        scored: list[tuple[DeploymentType, float, TimeWindow]] = []
        for dt in deploys:
            tw = self.find_optimal_window(graph, dt)
            sc = self.calculate_risk_score(graph, tw, dt)
            scored.append((dt, sc, tw))

        # Sort by risk (ascending) so lowest risk deploys first.
        scored.sort(key=lambda t: t[1])

        schedule: list[ScheduledDeploy] = []
        used_slots: set[tuple[int, int]] = set()  # (day, hour)

        for priority, (dt, sc, tw) in enumerate(scored, start=1):
            # If the slot is taken, nudge to next available hour.
            tw = self._find_free_slot(tw, used_slots, graph, dt)
            duration = _DEPLOY_DURATION.get(dt, 30.0)

            notes: list[str] = []
            risk = _risk_from_score(sc)
            if risk in (WindowRisk.HIGH, WindowRisk.CRITICAL):
                notes.append("Consider postponing or additional review")
            if dt == DeploymentType.DATABASE_MIGRATION:
                notes.append("Ensure backup before migration")
            if _spof_count(graph) > 0:
                notes.append("SPOFs present — rollback plan required")

            schedule.append(ScheduledDeploy(
                deploy_type=dt,
                recommended_window=tw,
                risk_score=sc,
                priority=priority,
                estimated_duration_minutes=duration,
                notes=notes,
            ))
            used_slots.add((tw.day_of_week, tw.start_hour))

        return schedule

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _hour_set(window: TimeWindow) -> set[int]:
        """Return the set of hours covered by *window*."""
        if window.end_hour > window.start_hour:
            return set(range(window.start_hour, window.end_hour))
        if window.end_hour == window.start_hour:
            return {window.start_hour}
        # Wrap-around midnight.
        return set(range(window.start_hour, 24)) | set(range(0, window.end_hour))

    def _find_free_slot(
        self,
        preferred: TimeWindow,
        used: set[tuple[int, int]],
        graph: InfraGraph,
        deploy_type: DeploymentType,
    ) -> TimeWindow:
        """Return *preferred* if free, else nudge to next free hour."""
        day = preferred.day_of_week
        hour = preferred.start_hour
        for _ in range(24):
            if (day, hour) not in used:
                return TimeWindow(
                    start_hour=hour,
                    end_hour=(hour + 1) % 24,
                    day_of_week=day,
                    timezone=preferred.timezone,
                )
            hour = (hour + 1) % 24
        # All hours taken — fall back to next day.
        next_day = (day + 1) % 7
        return TimeWindow(
            start_hour=preferred.start_hour,
            end_hour=preferred.end_hour,
            day_of_week=next_day,
            timezone=preferred.timezone,
        )

    @staticmethod
    def _build_recommendations(
        risk: WindowRisk,
        traffic: float,
        avail: float,
        freeze_active: bool,
        incidents: int,
        deploy_type: DeploymentType,
        graph: InfraGraph,
    ) -> list[str]:
        """Build a list of deployment recommendations."""
        recs: list[str] = []

        if freeze_active:
            recs.append("Change freeze is active — postpone if possible")

        if traffic > 0.80:
            recs.append("Deploying during peak traffic — consider off-peak window")

        if avail < 0.3:
            recs.append("Low team availability — ensure on-call coverage")

        if incidents > 0:
            recs.append(f"{incidents} recent incident(s) — extra caution advised")

        if risk in (WindowRisk.HIGH, WindowRisk.CRITICAL):
            recs.append("High risk — require additional approvals")

        if deploy_type == DeploymentType.DATABASE_MIGRATION:
            recs.append("Take a database backup before migration")

        if deploy_type == DeploymentType.INFRASTRUCTURE_CHANGE:
            recs.append("Verify rollback procedure before proceeding")

        if _spof_count(graph) > 0:
            recs.append("Address single points of failure before deployment")

        health_pen = _graph_health_penalty(graph)
        if health_pen > 10:
            recs.append("Resolve unhealthy components before deploying")

        if risk == WindowRisk.LOW and not freeze_active and incidents == 0:
            recs.append("Conditions are favorable for deployment")

        return recs
