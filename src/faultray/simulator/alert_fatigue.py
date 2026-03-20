# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Alert Fatigue Analyzer — detect alert fatigue risk and optimize alert quality.

Analyzes alert configurations for fatigue risk by examining actionability,
duplication, noise ratios, and threshold appropriateness.  Provides
recommendations to reduce operator fatigue and improve signal-to-noise ratio.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AlertSeverity(str, Enum):
    """Alert severity level."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


class FatigueRisk(str, Enum):
    """Overall fatigue risk classification."""

    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AlertConfig(BaseModel):
    """Configuration for a single alert rule."""

    id: str
    name: str
    severity: AlertSeverity
    component_id: str
    threshold: float
    evaluation_window_minutes: int
    notification_channels: list[str] = Field(default_factory=list)
    is_actionable: bool = True
    auto_resolve: bool = False
    suppression_minutes: int = 0


class AlertStormResult(BaseModel):
    """Result of an alert storm simulation."""

    total_alerts_generated: int = 0
    peak_alerts_per_minute: int = 0
    unique_alerts: int = 0
    duplicate_alerts: int = 0
    cascade_depth: int = 0
    affected_components: list[str] = Field(default_factory=list)
    storm_duration_minutes: int = 0
    fatigue_risk: FatigueRisk = FatigueRisk.NONE


class FatigueAssessment(BaseModel):
    """Full fatigue risk assessment result."""

    total_alerts: int = 0
    actionable_ratio: float = 0.0
    estimated_daily_alerts: int = 0
    fatigue_risk: FatigueRisk = FatigueRisk.NONE
    noise_alerts: list[str] = Field(default_factory=list)
    duplicate_groups: list[list[str]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    optimal_threshold_adjustments: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Estimated daily trigger rates per evaluation window (rough heuristic).
# Shorter windows trigger more often.
_DAILY_TRIGGER_MULTIPLIER: dict[int, float] = {
    1: 60.0,
    5: 20.0,
    10: 10.0,
    15: 6.0,
    30: 3.0,
    60: 1.5,
}
_DEFAULT_TRIGGER_MULTIPLIER = 1.0

# Severity weights for response time estimation (minutes per alert).
_SEVERITY_RESPONSE_WEIGHT: dict[AlertSeverity, float] = {
    AlertSeverity.CRITICAL: 15.0,
    AlertSeverity.WARNING: 5.0,
    AlertSeverity.INFO: 1.0,
    AlertSeverity.DEBUG: 0.5,
}


def _trigger_multiplier(window_minutes: int) -> float:
    """Return estimated daily trigger multiplier for the given evaluation window."""
    if window_minutes in _DAILY_TRIGGER_MULTIPLIER:
        return _DAILY_TRIGGER_MULTIPLIER[window_minutes]
    # Interpolate: shorter window -> more triggers
    if window_minutes <= 0:
        return 60.0
    if window_minutes >= 60:
        return max(0.5, 60.0 / window_minutes)
    # Linear interpolation between known points
    sorted_keys = sorted(_DAILY_TRIGGER_MULTIPLIER.keys())
    for i in range(len(sorted_keys) - 1):
        lo, hi = sorted_keys[i], sorted_keys[i + 1]
        if lo <= window_minutes <= hi:
            lo_val = _DAILY_TRIGGER_MULTIPLIER[lo]
            hi_val = _DAILY_TRIGGER_MULTIPLIER[hi]
            ratio = (window_minutes - lo) / (hi - lo)
            return lo_val + (hi_val - lo_val) * ratio
    return _DEFAULT_TRIGGER_MULTIPLIER  # pragma: no cover


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class AlertFatigueEngine:
    """Analyze alert configurations for fatigue risk and optimize alert quality."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess_fatigue(self, alerts: list[AlertConfig]) -> FatigueAssessment:
        """Perform a full fatigue risk assessment on the given alert set."""
        if not alerts:
            return FatigueAssessment()

        total = len(alerts)
        actionable_count = sum(1 for a in alerts if a.is_actionable)
        actionable_ratio = actionable_count / total if total > 0 else 0.0

        noise_alerts = [a.id for a in alerts if not a.is_actionable]

        # Estimate daily alerts
        estimated_daily = self._estimate_daily_alerts(alerts)

        # Detect duplicates
        duplicate_groups = self.detect_duplicate_alerts(alerts)

        # Determine fatigue risk level
        fatigue_risk = self._classify_fatigue_risk(
            total_alerts=total,
            actionable_ratio=actionable_ratio,
            estimated_daily=estimated_daily,
            duplicate_groups=duplicate_groups,
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            alerts=alerts,
            actionable_ratio=actionable_ratio,
            estimated_daily=estimated_daily,
            duplicate_groups=duplicate_groups,
            noise_alerts=noise_alerts,
        )

        # Compute optimal threshold adjustments
        optimal_adjustments = self._compute_threshold_adjustments(alerts)

        return FatigueAssessment(
            total_alerts=total,
            actionable_ratio=round(actionable_ratio, 4),
            estimated_daily_alerts=estimated_daily,
            fatigue_risk=fatigue_risk,
            noise_alerts=noise_alerts,
            duplicate_groups=duplicate_groups,
            recommendations=recommendations,
            optimal_threshold_adjustments=optimal_adjustments,
        )

    def detect_duplicate_alerts(self, alerts: list[AlertConfig]) -> list[list[str]]:
        """Detect groups of alerts that are likely duplicates.

        Alerts are considered duplicates when they target the same component
        with the same severity and similar thresholds (within 20%).
        """
        if not alerts:
            return []

        groups: list[list[str]] = []
        used: set[str] = set()

        for i, a in enumerate(alerts):
            if a.id in used:
                continue
            group = [a.id]
            used.add(a.id)

            for j in range(i + 1, len(alerts)):
                b = alerts[j]
                if b.id in used:
                    continue
                if self._are_duplicate(a, b):
                    group.append(b.id)
                    used.add(b.id)

            if len(group) > 1:
                groups.append(group)

        return groups

    def recommend_thresholds(
        self,
        graph: InfraGraph,
        alerts: list[AlertConfig],
    ) -> dict[str, float]:
        """Recommend optimal threshold adjustments based on infrastructure graph.

        For each alert, considers the component's current utilization and
        topology position to recommend a threshold that reduces noise while
        maintaining coverage.

        Returns a mapping of alert ID to recommended threshold.
        """
        recommendations: dict[str, float] = {}
        if not alerts:
            return recommendations

        for alert in alerts:
            comp = graph.get_component(alert.component_id)
            if comp is None:
                continue

            # Base: current threshold
            current = alert.threshold
            utilization = comp.utilization()

            # If the threshold is too close to current utilization, raise it
            # to reduce false positives.
            if current > 0 and utilization > 0:
                headroom = current - utilization
                if headroom < current * 0.1:
                    # Less than 10% headroom — too noisy
                    recommended = min(100.0, utilization + current * 0.2)
                    recommendations[alert.id] = round(recommended, 2)
                elif headroom > current * 0.5:
                    # Too much headroom — threshold could be tightened
                    recommended = max(1.0, utilization + current * 0.15)
                    recommendations[alert.id] = round(recommended, 2)

            # If component has many dependents, lower the threshold
            # (it's more critical and needs earlier warning).
            dependents = graph.get_dependents(alert.component_id)
            if len(dependents) >= 3 and alert.severity != AlertSeverity.CRITICAL:
                recommended = recommendations.get(alert.id, current)
                adjusted = recommended * 0.85
                recommendations[alert.id] = round(max(1.0, adjusted), 2)

        return recommendations

    def simulate_alert_storm(
        self,
        graph: InfraGraph,
        alerts: list[AlertConfig],
        failure_scenario: str,
    ) -> AlertStormResult:
        """Simulate an alert storm triggered by a failure scenario.

        ``failure_scenario`` is a component ID that experiences a failure.
        The simulation traces which alerts would fire based on cascade effects.
        """
        if not alerts or not failure_scenario:
            return AlertStormResult()

        # Find all affected components
        comp = graph.get_component(failure_scenario)
        if comp is None:
            # Component not in graph — no cascade possible
            return AlertStormResult()

        affected = graph.get_all_affected(failure_scenario)
        affected.add(failure_scenario)

        # Find alerts that would trigger
        triggered_alerts: list[AlertConfig] = []
        for alert in alerts:
            if alert.component_id in affected:
                triggered_alerts.append(alert)

        if not triggered_alerts:
            return AlertStormResult(
                affected_components=sorted(affected),
            )

        # Detect duplicates among triggered alerts
        duplicate_groups = self.detect_duplicate_alerts(triggered_alerts)
        duplicate_count = sum(len(g) - 1 for g in duplicate_groups)
        unique_count = len(triggered_alerts) - duplicate_count

        # Estimate cascade depth
        cascade_depth = 0
        if failure_scenario in {c.id for c in graph.components.values()}:
            paths = graph.get_cascade_path(failure_scenario)
            if paths:
                cascade_depth = max(len(p) for p in paths)

        # Estimate storm intensity
        # Shorter evaluation windows trigger faster
        peak_per_minute = 0
        for alert in triggered_alerts:
            window = alert.evaluation_window_minutes
            if window <= 1:
                peak_per_minute += 5
            elif window <= 5:
                peak_per_minute += 2
            else:
                peak_per_minute += 1

        # Storm duration based on suppression and auto-resolve settings
        has_suppression = any(a.suppression_minutes > 0 for a in triggered_alerts)
        has_auto_resolve = any(a.auto_resolve for a in triggered_alerts)

        if has_suppression and has_auto_resolve:
            storm_minutes = 15
        elif has_suppression or has_auto_resolve:
            storm_minutes = 30
        else:
            storm_minutes = 60

        total_generated = len(triggered_alerts) * max(1, storm_minutes // 10)

        # Determine storm fatigue risk
        if total_generated > 100 or peak_per_minute > 20:
            storm_risk = FatigueRisk.SEVERE
        elif total_generated > 50 or peak_per_minute > 10:
            storm_risk = FatigueRisk.HIGH
        elif total_generated > 20 or peak_per_minute > 5:
            storm_risk = FatigueRisk.MODERATE
        elif total_generated > 5:
            storm_risk = FatigueRisk.LOW
        else:
            storm_risk = FatigueRisk.NONE

        return AlertStormResult(
            total_alerts_generated=total_generated,
            peak_alerts_per_minute=peak_per_minute,
            unique_alerts=unique_count,
            duplicate_alerts=duplicate_count,
            cascade_depth=cascade_depth,
            affected_components=sorted(affected),
            storm_duration_minutes=storm_minutes,
            fatigue_risk=storm_risk,
        )

    def calculate_signal_to_noise(self, alerts: list[AlertConfig]) -> float:
        """Calculate signal-to-noise ratio for the alert set.

        A higher value means better signal quality.
        Returns a value between 0.0 and 1.0.

        Factors:
        - Ratio of actionable alerts (positive signal)
        - Duplicate groups reduce signal quality
        - Auto-resolve and suppression improve quality
        - Severity distribution (too many criticals = noise)
        """
        if not alerts:
            return 0.0

        total = len(alerts)

        # Factor 1: Actionable ratio (weight 0.4)
        actionable_count = sum(1 for a in alerts if a.is_actionable)
        actionable_ratio = actionable_count / total

        # Factor 2: Duplication penalty (weight 0.2)
        duplicate_groups = self.detect_duplicate_alerts(alerts)
        duplicate_count = sum(len(g) - 1 for g in duplicate_groups)
        duplication_ratio = 1.0 - (duplicate_count / total) if total > 0 else 1.0

        # Factor 3: Suppression/auto-resolve coverage (weight 0.2)
        managed_count = sum(
            1 for a in alerts if a.auto_resolve or a.suppression_minutes > 0
        )
        managed_ratio = managed_count / total

        # Factor 4: Severity distribution (weight 0.2)
        # Ideal: mostly warning/info, few critical
        critical_count = sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL)
        critical_ratio = critical_count / total
        # Penalty for too many criticals (> 30% is noisy)
        severity_score = max(0.0, 1.0 - max(0.0, critical_ratio - 0.3) * 2.0)

        snr = (
            actionable_ratio * 0.4
            + duplication_ratio * 0.2
            + managed_ratio * 0.2
            + severity_score * 0.2
        )

        return round(max(0.0, min(1.0, snr)), 4)

    def optimize_alert_set(self, alerts: list[AlertConfig]) -> list[AlertConfig]:
        """Return an optimized copy of the alert set.

        Optimization steps:
        1. Remove non-actionable alerts (noise)
        2. Merge duplicate groups (keep the one with the best config)
        3. Adjust suppression for alerts without it
        4. Set auto_resolve for info/debug alerts
        """
        if not alerts:
            return []

        # Step 1: Filter actionable
        working = [a.model_copy() for a in alerts if a.is_actionable]

        # If all were filtered, keep all but mark them for improvement
        if not working:
            working = [a.model_copy() for a in alerts]

        # Step 2: Remove duplicates (keep first in each group)
        duplicate_groups = self.detect_duplicate_alerts(working)
        ids_to_remove: set[str] = set()
        for group in duplicate_groups:
            # Keep the first, remove the rest
            for alert_id in group[1:]:
                ids_to_remove.add(alert_id)

        working = [a for a in working if a.id not in ids_to_remove]

        # Step 3: Add suppression to alerts that lack it
        for alert in working:
            if alert.suppression_minutes == 0:
                if alert.severity == AlertSeverity.CRITICAL:
                    alert.suppression_minutes = 5
                elif alert.severity == AlertSeverity.WARNING:
                    alert.suppression_minutes = 15
                elif alert.severity == AlertSeverity.INFO:
                    alert.suppression_minutes = 30
                else:  # DEBUG
                    alert.suppression_minutes = 60

        # Step 4: Auto-resolve for info/debug
        for alert in working:
            if alert.severity in (AlertSeverity.INFO, AlertSeverity.DEBUG):
                alert.auto_resolve = True

        return working

    def estimate_response_time(self, alerts: list[AlertConfig]) -> float:
        """Estimate average response time in minutes based on alert volume and severity.

        Takes into account:
        - Number of daily alerts
        - Severity-weighted response effort
        - Suppression and auto-resolve reducing burden
        """
        if not alerts:
            return 0.0

        estimated_daily = self._estimate_daily_alerts(alerts)
        if estimated_daily == 0:
            return 0.0

        # Calculate severity-weighted total effort
        total_effort = 0.0
        for alert in alerts:
            weight = _SEVERITY_RESPONSE_WEIGHT.get(alert.severity, 5.0)

            # Reduce effort if auto-resolve or suppression is configured
            if alert.auto_resolve:
                weight *= 0.3
            if alert.suppression_minutes > 0:
                weight *= 0.7

            if not alert.is_actionable:
                weight *= 0.5

            total_effort += weight

        avg_effort_per_alert = total_effort / len(alerts) if alerts else 0.0

        # Response time increases logarithmically with daily volume
        # More alerts = more context switching = slower per-alert response
        import math
        volume_factor = 1.0 + math.log1p(estimated_daily) * 0.3

        response_time = avg_effort_per_alert * volume_factor

        return round(max(0.0, response_time), 2)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _estimate_daily_alerts(self, alerts: list[AlertConfig]) -> int:
        """Estimate total daily alert volume."""
        total = 0.0
        for alert in alerts:
            multiplier = _trigger_multiplier(alert.evaluation_window_minutes)
            # Non-actionable alerts tend to fire more
            if not alert.is_actionable:
                multiplier *= 1.5
            # Suppression reduces actual alerts
            if alert.suppression_minutes > 0:
                suppression_factor = max(
                    0.1, 1.0 - alert.suppression_minutes / 60.0
                )
                multiplier *= suppression_factor
            # Auto-resolve reduces sustained alerts
            if alert.auto_resolve:
                multiplier *= 0.5

            total += multiplier

        return max(0, int(total))

    def _classify_fatigue_risk(
        self,
        total_alerts: int,
        actionable_ratio: float,
        estimated_daily: int,
        duplicate_groups: list[list[str]],
    ) -> FatigueRisk:
        """Classify the overall fatigue risk level."""
        score = 0

        # Volume scoring
        if estimated_daily > 200:
            score += 4
        elif estimated_daily > 100:
            score += 3
        elif estimated_daily > 50:
            score += 2
        elif estimated_daily > 20:
            score += 1

        # Actionable ratio scoring
        if actionable_ratio < 0.3:
            score += 3
        elif actionable_ratio < 0.5:
            score += 2
        elif actionable_ratio < 0.7:
            score += 1

        # Duplication scoring
        total_duplicates = sum(len(g) - 1 for g in duplicate_groups)
        if total_duplicates > 10:
            score += 3
        elif total_duplicates > 5:
            score += 2
        elif total_duplicates > 2:
            score += 1

        # Total alerts count
        if total_alerts > 50:
            score += 2
        elif total_alerts > 20:
            score += 1

        # Map score to risk level
        if score >= 8:
            return FatigueRisk.SEVERE
        if score >= 6:
            return FatigueRisk.HIGH
        if score >= 4:
            return FatigueRisk.MODERATE
        if score >= 2:
            return FatigueRisk.LOW
        return FatigueRisk.NONE

    def _generate_recommendations(
        self,
        alerts: list[AlertConfig],
        actionable_ratio: float,
        estimated_daily: int,
        duplicate_groups: list[list[str]],
        noise_alerts: list[str],
    ) -> list[str]:
        """Generate actionable recommendations to reduce fatigue."""
        recs: list[str] = []

        if actionable_ratio < 0.5:
            recs.append(
                f"Only {actionable_ratio:.0%} of alerts are actionable. "
                "Review and remove or convert non-actionable alerts."
            )

        if estimated_daily > 100:
            recs.append(
                f"Estimated {estimated_daily} daily alerts is too high. "
                "Consider increasing evaluation windows or thresholds."
            )

        if duplicate_groups:
            total_dups = sum(len(g) - 1 for g in duplicate_groups)
            recs.append(
                f"Found {len(duplicate_groups)} duplicate alert group(s) "
                f"({total_dups} redundant alerts). Consolidate duplicate rules."
            )

        if noise_alerts:
            recs.append(
                f"{len(noise_alerts)} alert(s) are non-actionable: "
                f"{', '.join(noise_alerts[:5])}. "
                "Remove or convert to logs/metrics."
            )

        # Check for missing suppression
        no_suppression = [a for a in alerts if a.suppression_minutes == 0]
        if no_suppression:
            recs.append(
                f"{len(no_suppression)} alert(s) have no suppression window. "
                "Add suppression to prevent alert storms."
            )

        # Check for info/debug without auto-resolve
        info_debug_manual = [
            a for a in alerts
            if a.severity in (AlertSeverity.INFO, AlertSeverity.DEBUG)
            and not a.auto_resolve
        ]
        if info_debug_manual:
            recs.append(
                f"{len(info_debug_manual)} info/debug alert(s) lack auto-resolve. "
                "Enable auto-resolve for low-severity alerts."
            )

        # Check for very short evaluation windows
        short_window = [a for a in alerts if a.evaluation_window_minutes < 5]
        if short_window:
            recs.append(
                f"{len(short_window)} alert(s) have evaluation windows under 5 minutes. "
                "Short windows cause excessive alert volume."
            )

        # Check notification channel diversity
        all_channels: set[str] = set()
        for a in alerts:
            all_channels.update(a.notification_channels)
        critical_alerts = [a for a in alerts if a.severity == AlertSeverity.CRITICAL]
        for ca in critical_alerts:
            if len(ca.notification_channels) < 2:
                recs.append(
                    f"Critical alert '{ca.id}' uses only {len(ca.notification_channels)} "
                    "notification channel(s). Add multiple channels for critical alerts."
                )
                break  # One recommendation is enough

        return recs

    def _compute_threshold_adjustments(
        self, alerts: list[AlertConfig],
    ) -> dict[str, float]:
        """Compute optimal threshold adjustments based on alert configuration."""
        adjustments: dict[str, float] = {}

        for alert in alerts:
            if not alert.is_actionable:
                # Non-actionable alerts should have higher thresholds
                adjustments[alert.id] = round(alert.threshold * 1.5, 2)
            elif alert.evaluation_window_minutes < 5 and alert.threshold < 50:
                # Short window + low threshold = noisy
                adjustments[alert.id] = round(alert.threshold * 1.3, 2)

        return adjustments

    def _are_duplicate(self, a: AlertConfig, b: AlertConfig) -> bool:
        """Check if two alerts are likely duplicates."""
        if a.component_id != b.component_id:
            return False
        if a.severity != b.severity:
            return False
        # Check threshold similarity (within 20%)
        if a.threshold > 0 and b.threshold > 0:
            ratio = min(a.threshold, b.threshold) / max(a.threshold, b.threshold)
            if ratio < 0.8:
                return False
        return True
