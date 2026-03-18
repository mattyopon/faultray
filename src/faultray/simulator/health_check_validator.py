"""Health Check Validation Engine.

Validates health check configurations against infrastructure topology,
detects common anti-patterns, simulates flapping behaviour, and provides
recommendations for robust health checking strategies.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class HealthCheckType(str, Enum):
    """Supported health check probe types."""

    HTTP = "http"
    TCP = "tcp"
    GRPC = "grpc"
    EXEC = "exec"
    STARTUP = "startup"
    LIVENESS = "liveness"
    READINESS = "readiness"


class AntiPattern(str, Enum):
    """Known health-check anti-patterns."""

    CHECK_TOO_SIMPLE = "check_too_simple"
    CHECK_TOO_COMPLEX = "check_too_complex"
    CASCADING_FAILURE = "cascading_failure"
    THUNDERING_HERD_ON_RECOVERY = "thundering_herd_on_recovery"
    MISSING_DEPENDENCY_CHECK = "missing_dependency_check"
    TIMEOUT_TOO_SHORT = "timeout_too_short"
    TIMEOUT_TOO_LONG = "timeout_too_long"
    INTERVAL_TOO_FREQUENT = "interval_too_frequent"
    NO_STARTUP_PROBE = "no_startup_probe"
    SHARED_ENDPOINT = "shared_endpoint"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class HealthCheckConfig(BaseModel):
    """Configuration for a single health check probe."""

    check_type: HealthCheckType
    endpoint: str
    interval_seconds: float
    timeout_seconds: float
    failure_threshold: int
    success_threshold: int
    checks_dependencies: bool
    includes_deep_check: bool


class HealthCheckAssessment(BaseModel):
    """Assessment result for a single component's health check configuration."""

    component_id: str
    config: HealthCheckConfig
    anti_patterns: list[AntiPattern] = Field(default_factory=list)
    risk_score: float = 0.0
    false_positive_risk: str = "low"
    false_negative_risk: str = "low"
    cascade_risk: bool = False
    recommendations: list[str] = Field(default_factory=list)


class FlappingResult(BaseModel):
    """Result of a flapping simulation for a health check."""

    component_id: str
    flap_count: int = 0
    flap_risk: str = "low"
    mean_time_between_flaps_seconds: float = 0.0
    steady_state_seconds: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class HealthCheckFailureResult(BaseModel):
    """Result of simulating a health-check failure for a component."""

    component_id: str
    affected_components: list[str] = Field(default_factory=list)
    cascade_depth: int = 0
    estimated_detection_seconds: float = 0.0
    estimated_recovery_seconds: float = 0.0
    risk_score: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Thresholds used by detection heuristics
_MIN_REASONABLE_TIMEOUT = 2.0  # seconds
_MAX_REASONABLE_TIMEOUT = 30.0  # seconds
_MIN_REASONABLE_INTERVAL = 5.0  # seconds
_DEEP_CHECK_COMPLEXITY_THRESHOLD = 3  # if checking > N deps → complex

# Risk-score weights per anti-pattern
_ANTI_PATTERN_WEIGHTS: dict[AntiPattern, float] = {
    AntiPattern.CHECK_TOO_SIMPLE: 10.0,
    AntiPattern.CHECK_TOO_COMPLEX: 15.0,
    AntiPattern.CASCADING_FAILURE: 25.0,
    AntiPattern.THUNDERING_HERD_ON_RECOVERY: 20.0,
    AntiPattern.MISSING_DEPENDENCY_CHECK: 12.0,
    AntiPattern.TIMEOUT_TOO_SHORT: 15.0,
    AntiPattern.TIMEOUT_TOO_LONG: 10.0,
    AntiPattern.INTERVAL_TOO_FREQUENT: 8.0,
    AntiPattern.NO_STARTUP_PROBE: 10.0,
    AntiPattern.SHARED_ENDPOINT: 12.0,
}

# Recommended check types per component type
_RECOMMENDED_CHECK_TYPES: dict[ComponentType, HealthCheckType] = {
    ComponentType.LOAD_BALANCER: HealthCheckType.HTTP,
    ComponentType.WEB_SERVER: HealthCheckType.HTTP,
    ComponentType.APP_SERVER: HealthCheckType.HTTP,
    ComponentType.DATABASE: HealthCheckType.TCP,
    ComponentType.CACHE: HealthCheckType.TCP,
    ComponentType.QUEUE: HealthCheckType.TCP,
    ComponentType.STORAGE: HealthCheckType.HTTP,
    ComponentType.DNS: HealthCheckType.TCP,
    ComponentType.EXTERNAL_API: HealthCheckType.HTTP,
    ComponentType.CUSTOM: HealthCheckType.HTTP,
    ComponentType.AI_AGENT: HealthCheckType.HTTP,
    ComponentType.LLM_ENDPOINT: HealthCheckType.HTTP,
    ComponentType.TOOL_SERVICE: HealthCheckType.HTTP,
    ComponentType.AGENT_ORCHESTRATOR: HealthCheckType.HTTP,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class HealthCheckValidationEngine:
    """Validates health check configurations against an infrastructure graph.

    Detects anti-patterns, estimates detection times, simulates flapping and
    health-check failures, and recommends optimal configurations.
    """

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_health_check(
        self,
        graph: InfraGraph,
        component_id: str,
        config: HealthCheckConfig,
    ) -> HealthCheckAssessment:
        """Validate a single component's health check configuration.

        Parameters
        ----------
        graph:
            The infrastructure dependency graph.
        component_id:
            ID of the component being checked.
        config:
            The health check configuration to validate.

        Returns
        -------
        HealthCheckAssessment
            Detailed assessment including detected anti-patterns, risk score,
            false-positive/negative risk, cascade risk and recommendations.
        """
        anti_patterns = self.detect_anti_patterns(config)

        # Enrich with graph-aware anti-patterns
        comp = graph.get_component(component_id)
        deps = self._safe_get_dependencies(graph, component_id)
        dependents = self._safe_get_dependents(graph, component_id)

        # Missing dependency check: component has dependencies but config
        # does not check them and does not include deep check
        if deps and not config.checks_dependencies and not config.includes_deep_check:
            if AntiPattern.MISSING_DEPENDENCY_CHECK not in anti_patterns:
                anti_patterns.append(AntiPattern.MISSING_DEPENDENCY_CHECK)

        # Cascading failure: deep check + many dependents
        if config.checks_dependencies and len(dependents) > 2:
            if AntiPattern.CASCADING_FAILURE not in anti_patterns:
                anti_patterns.append(AntiPattern.CASCADING_FAILURE)

        # Shared endpoint: if the same endpoint is used for liveness/readiness
        # (heuristic: readiness or liveness with deep check = shared risk)
        if config.check_type in (HealthCheckType.LIVENESS, HealthCheckType.READINESS):
            if config.includes_deep_check:
                if AntiPattern.SHARED_ENDPOINT not in anti_patterns:
                    anti_patterns.append(AntiPattern.SHARED_ENDPOINT)

        # Calculate risk score
        risk_score = self._calculate_risk_score(anti_patterns, graph, component_id)

        # False-positive / false-negative assessment
        false_positive_risk = self._assess_false_positive_risk(config)
        false_negative_risk = self._assess_false_negative_risk(config, deps)

        # Cascade risk
        cascade_risk = (
            AntiPattern.CASCADING_FAILURE in anti_patterns
            or len(dependents) > 3
        )

        # Recommendations
        recommendations = self._generate_recommendations(
            anti_patterns, config, comp, deps, dependents,
        )

        return HealthCheckAssessment(
            component_id=component_id,
            config=config,
            anti_patterns=anti_patterns,
            risk_score=risk_score,
            false_positive_risk=false_positive_risk,
            false_negative_risk=false_negative_risk,
            cascade_risk=cascade_risk,
            recommendations=recommendations,
        )

    def detect_anti_patterns(
        self,
        config: HealthCheckConfig,
    ) -> list[AntiPattern]:
        """Detect anti-patterns in a health check configuration.

        This method performs *config-only* analysis (no graph required).

        Parameters
        ----------
        config:
            The health check configuration to analyse.

        Returns
        -------
        list[AntiPattern]
            Detected anti-patterns.
        """
        patterns: list[AntiPattern] = []

        # CHECK_TOO_SIMPLE: no deep check, no dependency check, basic type
        if (
            not config.includes_deep_check
            and not config.checks_dependencies
            and config.check_type in (HealthCheckType.TCP, HealthCheckType.EXEC)
        ):
            patterns.append(AntiPattern.CHECK_TOO_SIMPLE)

        # CHECK_TOO_COMPLEX: deep check + dependency check + short interval
        if (
            config.includes_deep_check
            and config.checks_dependencies
            and config.interval_seconds < _MIN_REASONABLE_INTERVAL
        ):
            patterns.append(AntiPattern.CHECK_TOO_COMPLEX)

        # TIMEOUT_TOO_SHORT
        if config.timeout_seconds < _MIN_REASONABLE_TIMEOUT:
            patterns.append(AntiPattern.TIMEOUT_TOO_SHORT)

        # TIMEOUT_TOO_LONG
        if config.timeout_seconds > _MAX_REASONABLE_TIMEOUT:
            patterns.append(AntiPattern.TIMEOUT_TOO_LONG)

        # INTERVAL_TOO_FREQUENT
        if config.interval_seconds < _MIN_REASONABLE_INTERVAL:
            patterns.append(AntiPattern.INTERVAL_TOO_FREQUENT)

        # THUNDERING_HERD_ON_RECOVERY: low success_threshold + frequent interval
        if config.success_threshold <= 1 and config.interval_seconds < _MIN_REASONABLE_INTERVAL:
            patterns.append(AntiPattern.THUNDERING_HERD_ON_RECOVERY)

        # NO_STARTUP_PROBE: liveness or readiness without startup
        if config.check_type in (HealthCheckType.LIVENESS, HealthCheckType.READINESS):
            # We cannot know if a separate startup probe exists from config alone,
            # so flag when failure_threshold is low (risky without startup probe).
            if config.failure_threshold <= 1:
                patterns.append(AntiPattern.NO_STARTUP_PROBE)

        return patterns

    def simulate_flapping(
        self,
        graph: InfraGraph,
        component_id: str,
        config: HealthCheckConfig,
    ) -> FlappingResult:
        """Simulate health-check flapping behaviour.

        Estimates how likely a check is to cause oscillating healthy/unhealthy
        states based on interval, timeout, thresholds, and the component's
        operational profile.

        Parameters
        ----------
        graph:
            The infrastructure dependency graph.
        component_id:
            ID of the component.
        config:
            The health check configuration.

        Returns
        -------
        FlappingResult
            Flapping simulation result.
        """
        comp = graph.get_component(component_id)

        # Base flap cycle time: time for one failure-then-recovery cycle
        failure_detection_time = config.interval_seconds * config.failure_threshold
        recovery_detection_time = config.interval_seconds * config.success_threshold
        cycle_time = failure_detection_time + recovery_detection_time

        # Flap propensity factors
        propensity = 0.0

        # Short timeout relative to interval → more false failures
        if config.timeout_seconds < config.interval_seconds * 0.3:
            propensity += 0.3

        # Very frequent checks amplify noise
        if config.interval_seconds < _MIN_REASONABLE_INTERVAL:
            propensity += 0.2

        # Low failure threshold → quick to declare unhealthy
        if config.failure_threshold <= 1:
            propensity += 0.25

        # Low success threshold → quick to declare healthy
        if config.success_threshold <= 1:
            propensity += 0.15

        # Deep check with dependency check → affected by transient dep issues
        if config.checks_dependencies and config.includes_deep_check:
            propensity += 0.1

        # Component operational profile
        if comp:
            mttr = comp.operational_profile.mttr_minutes * 60  # seconds
            if mttr > 0 and cycle_time > 0:
                # If cycle time is very short relative to MTTR, component may
                # oscillate during recovery
                if cycle_time < mttr * 0.1:
                    propensity += 0.15

        propensity = min(1.0, propensity)

        # Estimate flap count over a 1-hour window
        if cycle_time > 0:
            max_possible_flaps = int(3600 / cycle_time)
        else:
            max_possible_flaps = 0

        flap_count = int(max_possible_flaps * propensity)

        # Steady-state time: how long until flapping settles
        steady_state = cycle_time * (config.failure_threshold + config.success_threshold)
        if propensity > 0.5:
            steady_state *= 2.0

        # Risk classification
        if flap_count >= 10:
            flap_risk = "high"
        elif flap_count >= 3:
            flap_risk = "medium"
        else:
            flap_risk = "low"

        mean_time_between_flaps = cycle_time if flap_count > 0 else 0.0

        recommendations: list[str] = []
        if flap_risk == "high":
            recommendations.append(
                "Increase failure_threshold to reduce flapping sensitivity."
            )
            recommendations.append(
                "Consider adding a startup probe to avoid flapping during boot."
            )
        if flap_risk in ("high", "medium"):
            recommendations.append(
                "Increase interval_seconds to reduce noise from transient issues."
            )

        return FlappingResult(
            component_id=component_id,
            flap_count=flap_count,
            flap_risk=flap_risk,
            mean_time_between_flaps_seconds=mean_time_between_flaps,
            steady_state_seconds=steady_state,
            recommendations=recommendations,
        )

    def estimate_detection_time(
        self,
        config: HealthCheckConfig,
        failure_type: str,
    ) -> float:
        """Estimate time-to-detect for a given failure type.

        Parameters
        ----------
        config:
            The health check configuration.
        failure_type:
            Type of failure: ``"crash"``, ``"hang"``, ``"degraded"``,
            ``"network_partition"``, ``"dependency_failure"``, or
            ``"resource_exhaustion"``.

        Returns
        -------
        float
            Estimated seconds until the health check detects the failure.
        """
        base_detection = config.interval_seconds * config.failure_threshold

        multipliers: dict[str, float] = {
            "crash": 1.0,  # immediate detection on next check
            "hang": 1.2,   # may need timeout to expire
            "degraded": 2.0,  # subtle, may need multiple checks
            "network_partition": 1.5,
            "dependency_failure": 1.8 if config.checks_dependencies else 3.0,
            "resource_exhaustion": 2.5,
        }

        multiplier = multipliers.get(failure_type, 1.5)

        detection_time = base_detection * multiplier

        # If timeout is too short, some failures may need extra cycles
        if config.timeout_seconds < _MIN_REASONABLE_TIMEOUT:
            detection_time *= 1.3

        # If not checking dependencies, dependency failures take longer
        if failure_type == "dependency_failure" and not config.checks_dependencies:
            detection_time += config.interval_seconds * 2

        return detection_time

    def recommend_health_check(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> HealthCheckConfig:
        """Recommend an optimal health check configuration for a component.

        Uses the component type, dependency count, and topology position to
        generate a reasonable default configuration.

        Parameters
        ----------
        graph:
            The infrastructure dependency graph.
        component_id:
            ID of the component.

        Returns
        -------
        HealthCheckConfig
            Recommended configuration.
        """
        comp = graph.get_component(component_id)
        deps = self._safe_get_dependencies(graph, component_id)
        dependents = self._safe_get_dependents(graph, component_id)

        # Choose check type based on component type
        comp_type = comp.type if comp else ComponentType.CUSTOM
        check_type = _RECOMMENDED_CHECK_TYPES.get(comp_type, HealthCheckType.HTTP)

        # Base interval: more dependents → more careful (longer interval)
        if len(dependents) > 5:
            interval = 30.0
        elif len(dependents) > 2:
            interval = 15.0
        else:
            interval = 10.0

        # Timeout: based on component type
        if comp_type in (ComponentType.DATABASE, ComponentType.EXTERNAL_API):
            timeout = 10.0
        elif comp_type in (ComponentType.CACHE, ComponentType.DNS):
            timeout = 5.0
        else:
            timeout = 5.0

        # Failure threshold: higher for components with many dependents
        if len(dependents) > 5:
            failure_threshold = 5
        elif len(dependents) > 2:
            failure_threshold = 3
        else:
            failure_threshold = 3

        # Success threshold
        success_threshold = 2

        # Should check dependencies?
        # Only for readiness-style checks, and only if there are deps
        checks_deps = bool(deps) and len(deps) <= _DEEP_CHECK_COMPLEXITY_THRESHOLD

        # Deep check only if few dependencies and not too many dependents
        includes_deep = bool(deps) and len(deps) <= 2 and len(dependents) <= 3

        # For databases, prefer TCP checks with dependency-aware settings
        if comp_type == ComponentType.DATABASE:
            check_type = HealthCheckType.TCP
            checks_deps = False
            includes_deep = False

        # Build recommended endpoint
        if check_type == HealthCheckType.HTTP:
            endpoint = "/healthz"
        elif check_type == HealthCheckType.TCP:
            port = comp.port if comp and comp.port else 8080
            endpoint = f":{port}"
        elif check_type == HealthCheckType.GRPC:
            endpoint = "grpc://localhost/health"
        else:
            endpoint = "/healthz"

        return HealthCheckConfig(
            check_type=check_type,
            endpoint=endpoint,
            interval_seconds=interval,
            timeout_seconds=timeout,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            checks_dependencies=checks_deps,
            includes_deep_check=includes_deep,
        )

    def validate_all_checks(
        self,
        graph: InfraGraph,
        configs: dict[str, HealthCheckConfig],
    ) -> list[HealthCheckAssessment]:
        """Validate health checks for multiple components.

        Parameters
        ----------
        graph:
            The infrastructure dependency graph.
        configs:
            Mapping of component_id to HealthCheckConfig.

        Returns
        -------
        list[HealthCheckAssessment]
            Assessment for each component, sorted by risk score descending.
        """
        assessments: list[HealthCheckAssessment] = []
        for comp_id, config in configs.items():
            assessment = self.validate_health_check(graph, comp_id, config)
            assessments.append(assessment)

        # Check for shared endpoint anti-pattern across components
        endpoint_users: dict[str, list[str]] = {}
        for comp_id, config in configs.items():
            key = f"{config.check_type.value}:{config.endpoint}"
            endpoint_users.setdefault(key, []).append(comp_id)

        for key, users in endpoint_users.items():
            if len(users) > 1:
                for assessment in assessments:
                    if assessment.component_id in users:
                        if AntiPattern.SHARED_ENDPOINT not in assessment.anti_patterns:
                            assessment.anti_patterns.append(AntiPattern.SHARED_ENDPOINT)
                            assessment.recommendations.append(
                                f"Health check endpoint is shared with {len(users) - 1} "
                                "other component(s). Use unique endpoints per component."
                            )
                            # Recalculate risk score
                            assessment.risk_score = self._calculate_risk_score(
                                assessment.anti_patterns, graph, assessment.component_id,
                            )

        assessments.sort(key=lambda a: a.risk_score, reverse=True)
        return assessments

    def simulate_health_check_failure(
        self,
        graph: InfraGraph,
        component_id: str,
    ) -> HealthCheckFailureResult:
        """Simulate what happens when a component's health check fails.

        Uses the graph to determine cascade impact, detection time, and
        recovery time.

        Parameters
        ----------
        graph:
            The infrastructure dependency graph.
        component_id:
            ID of the component whose health check has failed.

        Returns
        -------
        HealthCheckFailureResult
            Simulation result including affected components and risk score.
        """
        comp = graph.get_component(component_id)
        affected = self._safe_get_all_affected(graph, component_id)
        dependents = self._safe_get_dependents(graph, component_id)

        # Cascade depth via BFS
        cascade_depth = 0
        if affected:
            # Find the longest path from this component
            paths = graph.get_cascade_path(component_id)
            if paths:
                cascade_depth = max(len(p) - 1 for p in paths)
            else:
                cascade_depth = 1 if affected else 0

        # Estimated detection time based on failover config
        if comp and comp.failover.enabled:
            detection_seconds = (
                comp.failover.health_check_interval_seconds
                * comp.failover.failover_threshold
            )
        else:
            # Default estimate: 30 seconds
            detection_seconds = 30.0

        # Estimated recovery time
        if comp and comp.failover.enabled:
            recovery_seconds = comp.failover.promotion_time_seconds
        elif comp and comp.autoscaling.enabled:
            recovery_seconds = float(comp.autoscaling.scale_up_delay_seconds)
        else:
            recovery_seconds = comp.operational_profile.mttr_minutes * 60.0 if comp else 1800.0

        # Risk score: based on number of affected components and cascade depth
        total_components = len(graph.components)
        if total_components > 0:
            impact_ratio = len(affected) / total_components
        else:
            impact_ratio = 0.0

        risk_score = min(100.0, impact_ratio * 60.0 + cascade_depth * 10.0)

        recommendations: list[str] = []
        if cascade_depth > 2:
            recommendations.append(
                "Deep cascade detected. Add circuit breakers to limit blast radius."
            )
        if len(affected) > total_components * 0.5 and total_components > 0:
            recommendations.append(
                "Health check failure affects >50% of components. "
                "Consider adding redundancy or failover."
            )
        if not (comp and comp.failover.enabled):
            recommendations.append(
                "Enable failover to reduce detection and recovery time."
            )
        if len(dependents) > 3:
            recommendations.append(
                "Many components depend on this service. "
                "Consider a readiness probe to prevent traffic during recovery."
            )

        return HealthCheckFailureResult(
            component_id=component_id,
            affected_components=sorted(affected),
            cascade_depth=cascade_depth,
            estimated_detection_seconds=detection_seconds,
            estimated_recovery_seconds=recovery_seconds,
            risk_score=risk_score,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_get_dependents(graph: InfraGraph, component_id: str) -> list:
        """Get dependents, returning [] if component is not in the graph."""
        if component_id not in graph.components:
            return []
        return graph.get_dependents(component_id)

    @staticmethod
    def _safe_get_dependencies(graph: InfraGraph, component_id: str) -> list:
        """Get dependencies, returning [] if component is not in the graph."""
        if component_id not in graph.components:
            return []
        return graph.get_dependencies(component_id)

    @staticmethod
    def _safe_get_all_affected(graph: InfraGraph, component_id: str) -> set[str]:
        """Get all affected components, returning empty set if not in graph."""
        if component_id not in graph.components:
            return set()
        return graph.get_all_affected(component_id)

    def _calculate_risk_score(
        self,
        anti_patterns: list[AntiPattern],
        graph: InfraGraph,
        component_id: str,
    ) -> float:
        """Calculate a risk score (0-100) from anti-patterns and topology."""
        score = 0.0
        for ap in anti_patterns:
            score += _ANTI_PATTERN_WEIGHTS.get(ap, 5.0)

        # Topology amplifier: more dependents → higher risk
        dependents = self._safe_get_dependents(graph, component_id)
        if len(dependents) > 5:
            score *= 1.5
        elif len(dependents) > 2:
            score *= 1.2

        return min(100.0, score)

    def _assess_false_positive_risk(self, config: HealthCheckConfig) -> str:
        """Assess the risk of false-positive health check failures."""
        risk_factors = 0

        if config.timeout_seconds < _MIN_REASONABLE_TIMEOUT:
            risk_factors += 2
        if config.interval_seconds < _MIN_REASONABLE_INTERVAL:
            risk_factors += 1
        if config.failure_threshold <= 1:
            risk_factors += 2
        if config.checks_dependencies and config.includes_deep_check:
            risk_factors += 1

        if risk_factors >= 4:
            return "high"
        elif risk_factors >= 2:
            return "medium"
        return "low"

    def _assess_false_negative_risk(
        self,
        config: HealthCheckConfig,
        deps: list,
    ) -> str:
        """Assess the risk of false-negative (missed failure) health checks."""
        risk_factors = 0

        if not config.includes_deep_check and not config.checks_dependencies:
            risk_factors += 1
        if config.timeout_seconds > _MAX_REASONABLE_TIMEOUT:
            risk_factors += 1
        if config.interval_seconds > 60.0:
            risk_factors += 2
        if deps and not config.checks_dependencies:
            risk_factors += 1
        if config.check_type in (HealthCheckType.TCP,):
            # TCP only checks connectivity, not application health
            risk_factors += 1

        if risk_factors >= 4:
            return "high"
        elif risk_factors >= 2:
            return "medium"
        return "low"

    def _generate_recommendations(
        self,
        anti_patterns: list[AntiPattern],
        config: HealthCheckConfig,
        comp,
        deps: list,
        dependents: list,
    ) -> list[str]:
        """Generate actionable recommendations based on detected issues."""
        recs: list[str] = []

        if AntiPattern.CHECK_TOO_SIMPLE in anti_patterns:
            recs.append(
                "Health check is too simple. Add application-level checks "
                "(e.g., HTTP endpoint returning application status)."
            )

        if AntiPattern.CHECK_TOO_COMPLEX in anti_patterns:
            recs.append(
                "Health check is too complex. Separate liveness and readiness "
                "probes; liveness should be lightweight."
            )

        if AntiPattern.CASCADING_FAILURE in anti_patterns:
            recs.append(
                "Dependency-checking health probe on a highly-depended-upon "
                "component can cause cascading failures. Use a simple liveness "
                "probe and a separate readiness probe for dependency checks."
            )

        if AntiPattern.THUNDERING_HERD_ON_RECOVERY in anti_patterns:
            recs.append(
                "Low success threshold with frequent checks may cause "
                "thundering herd on recovery. Increase success_threshold "
                "and interval_seconds."
            )

        if AntiPattern.MISSING_DEPENDENCY_CHECK in anti_patterns:
            recs.append(
                "Component has dependencies but the health check does not "
                "verify them. Add a readiness probe that checks critical "
                "dependencies."
            )

        if AntiPattern.TIMEOUT_TOO_SHORT in anti_patterns:
            recs.append(
                f"Timeout of {config.timeout_seconds}s is too short. "
                f"Set timeout to at least {_MIN_REASONABLE_TIMEOUT}s to "
                "avoid false positives from transient latency."
            )

        if AntiPattern.TIMEOUT_TOO_LONG in anti_patterns:
            recs.append(
                f"Timeout of {config.timeout_seconds}s is too long. "
                f"Keep timeout under {_MAX_REASONABLE_TIMEOUT}s to ensure "
                "timely failure detection."
            )

        if AntiPattern.INTERVAL_TOO_FREQUENT in anti_patterns:
            recs.append(
                f"Check interval of {config.interval_seconds}s is too frequent. "
                f"Use at least {_MIN_REASONABLE_INTERVAL}s to reduce load "
                "and noise."
            )

        if AntiPattern.NO_STARTUP_PROBE in anti_patterns:
            recs.append(
                "No startup probe detected (low failure threshold with "
                "liveness/readiness check). Add a startup probe to avoid "
                "killing containers during initialization."
            )

        if AntiPattern.SHARED_ENDPOINT in anti_patterns:
            recs.append(
                "Liveness/readiness probe includes deep checks. Separate "
                "liveness (simple) from readiness (deep) endpoints."
            )

        return recs
