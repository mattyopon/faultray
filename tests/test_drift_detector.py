"""Tests for Dependency Drift Detection Engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.drift_detector import (
    DriftBaseline,
    DriftDetector,
    DriftEvent,
    DriftReport,
    DriftSeverity,
    DriftType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(
    components: list[Component] | None = None,
    dependencies: list[Dependency] | None = None,
) -> InfraGraph:
    """Build an InfraGraph from component/dependency lists."""
    graph = InfraGraph()
    for comp in components or []:
        graph.add_component(comp)
    for dep in dependencies or []:
        graph.add_dependency(dep)
    return graph


def _web_api(
    replicas: int = 3,
    autoscaling: bool = True,
    failover: bool = True,
    failover_health_check_interval: float = 10.0,
    max_connections: int = 1000,
    encryption_at_rest: bool = True,
) -> Component:
    return Component(
        id="web-api",
        name="Web API",
        type=ComponentType.APP_SERVER,
        replicas=replicas,
        autoscaling=AutoScalingConfig(
            enabled=autoscaling, min_replicas=2, max_replicas=10
        ),
        failover=FailoverConfig(
            enabled=failover,
            health_check_interval_seconds=failover_health_check_interval,
        ),
        capacity=Capacity(max_connections=max_connections),
        security=SecurityProfile(encryption_at_rest=encryption_at_rest),
    )


def _postgres(replicas: int = 2, failover: bool = True) -> Component:
    return Component(
        id="postgres",
        name="PostgreSQL",
        type=ComponentType.DATABASE,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover),
    )


def _redis(replicas: int = 2) -> Component:
    return Component(
        id="redis",
        name="Redis Cache",
        type=ComponentType.CACHE,
        replicas=replicas,
    )


def _dep(
    source: str,
    target: str,
    dep_type: str = "requires",
    circuit_breaker: bool = False,
) -> Dependency:
    return Dependency(
        source_id=source,
        target_id=target,
        dependency_type=dep_type,
        circuit_breaker=CircuitBreakerConfig(enabled=circuit_breaker),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def detector() -> DriftDetector:
    return DriftDetector()


@pytest.fixture
def baseline_graph() -> InfraGraph:
    """A well-configured baseline infrastructure."""
    return _make_graph(
        components=[
            _web_api(replicas=3, autoscaling=True, failover=True),
            _postgres(replicas=2, failover=True),
            _redis(replicas=2),
        ],
        dependencies=[
            _dep("web-api", "postgres", circuit_breaker=True),
            _dep("web-api", "redis", dep_type="optional", circuit_breaker=True),
        ],
    )


@pytest.fixture
def degraded_graph() -> InfraGraph:
    """Infrastructure that has drifted from the baseline."""
    return _make_graph(
        components=[
            _web_api(
                replicas=1,
                autoscaling=False,
                failover=False,
                encryption_at_rest=False,
            ),
            _postgres(replicas=1, failover=False),
            _redis(replicas=2),
        ],
        dependencies=[
            _dep("web-api", "postgres", circuit_breaker=False),
            _dep("web-api", "redis", dep_type="optional", circuit_breaker=False),
        ],
    )


# ---------------------------------------------------------------------------
# DriftType and DriftSeverity Enum Tests
# ---------------------------------------------------------------------------


class TestDriftTypeEnum:
    def test_all_values(self):
        """All expected drift types should exist."""
        expected = [
            "replica_reduction",
            "circuit_breaker_disabled",
            "autoscaling_disabled",
            "health_check_removed",
            "failover_disabled",
            "new_spof_introduced",
            "dependency_added",
            "dependency_removed",
            "component_added",
            "component_removed",
            "capacity_reduced",
            "security_weakened",
            "configuration_changed",
        ]
        for val in expected:
            assert DriftType(val) is not None

    def test_string_value(self):
        assert DriftType.REPLICA_REDUCTION == "replica_reduction"
        assert DriftType.FAILOVER_DISABLED.value == "failover_disabled"


class TestDriftSeverityEnum:
    def test_all_values(self):
        expected = ["critical", "high", "medium", "low", "info"]
        for val in expected:
            assert DriftSeverity(val) is not None


# ---------------------------------------------------------------------------
# DriftEvent Dataclass Tests
# ---------------------------------------------------------------------------


class TestDriftEvent:
    def test_creation(self):
        event = DriftEvent(
            drift_type=DriftType.REPLICA_REDUCTION,
            severity=DriftSeverity.HIGH,
            component_id="web-api",
            component_name="Web API",
            field="replicas",
            baseline_value=3,
            current_value=1,
            description="Replicas reduced",
            resilience_impact=-7.0,
            remediation="Restore replicas to 3",
        )
        assert event.drift_type == DriftType.REPLICA_REDUCTION
        assert event.severity == DriftSeverity.HIGH
        assert event.component_id == "web-api"
        assert event.baseline_value == 3
        assert event.current_value == 1
        assert event.resilience_impact == -7.0
        assert event.detected_at is not None

    def test_default_detected_at(self):
        event = DriftEvent(
            drift_type=DriftType.COMPONENT_ADDED,
            severity=DriftSeverity.INFO,
            component_id="new",
            component_name="New",
            field="component",
            baseline_value=None,
            current_value="new",
            description="New component",
            resilience_impact=0.0,
            remediation="",
        )
        assert isinstance(event.detected_at, datetime)


# ---------------------------------------------------------------------------
# DriftReport Tests
# ---------------------------------------------------------------------------


class TestDriftReport:
    def test_to_dict(self):
        report = DriftReport(
            baseline_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            current_timestamp=datetime(2025, 1, 15, tzinfo=timezone.utc),
            total_drifts=2,
            critical_drifts=1,
            high_drifts=1,
            events=[
                DriftEvent(
                    drift_type=DriftType.FAILOVER_DISABLED,
                    severity=DriftSeverity.CRITICAL,
                    component_id="db",
                    component_name="Database",
                    field="failover.enabled",
                    baseline_value=True,
                    current_value=False,
                    description="Failover disabled",
                    resilience_impact=-10.0,
                    remediation="Re-enable failover",
                ),
            ],
            baseline_resilience_score=85.0,
            current_resilience_score=65.0,
            score_delta=-20.0,
            drift_velocity=0.14,
            risk_trend="critical_degradation",
            summary="Detected 2 drift(s).",
        )
        d = report.to_dict()
        assert d["total_drifts"] == 2
        assert d["critical_drifts"] == 1
        assert d["score_delta"] == -20.0
        assert d["risk_trend"] == "critical_degradation"
        assert len(d["events"]) == 1
        assert d["events"][0]["drift_type"] == "failover_disabled"
        assert d["events"][0]["severity"] == "critical"

    def test_to_dict_empty_events(self):
        report = DriftReport(
            baseline_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            current_timestamp=datetime(2025, 1, 2, tzinfo=timezone.utc),
            total_drifts=0,
            critical_drifts=0,
            high_drifts=0,
            events=[],
            baseline_resilience_score=80.0,
            current_resilience_score=80.0,
            score_delta=0.0,
            drift_velocity=0.0,
            risk_trend="stable",
            summary="No drift.",
        )
        d = report.to_dict()
        assert d["events"] == []
        assert d["total_drifts"] == 0


# ---------------------------------------------------------------------------
# DriftBaseline Tests
# ---------------------------------------------------------------------------


class TestDriftBaseline:
    def test_creation(self):
        bl = DriftBaseline(
            infrastructure_id="abc123",
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            components={"web": {"id": "web", "replicas": 3}},
            edges=[{"source_id": "web", "target_id": "db"}],
            resilience_score=75.0,
        )
        assert bl.infrastructure_id == "abc123"
        assert bl.resilience_score == 75.0
        assert "web" in bl.components
        assert len(bl.edges) == 1
        assert bl.genome_hash is None
        assert bl.metadata == {}


# ---------------------------------------------------------------------------
# DriftDetector.save_baseline / load_baseline Tests
# ---------------------------------------------------------------------------


class TestBaselinePersistence:
    def test_save_and_load(self, detector: DriftDetector, baseline_graph: InfraGraph, tmp_path: Path):
        path = tmp_path / "baseline.json"
        baseline = detector.save_baseline(baseline_graph, path)

        assert path.exists()
        assert baseline.infrastructure_id
        assert baseline.resilience_score > 0
        assert len(baseline.components) == 3
        assert len(baseline.edges) == 2

        # Load it back
        loaded = detector.load_baseline(path)
        assert loaded.infrastructure_id == baseline.infrastructure_id
        assert loaded.resilience_score == baseline.resilience_score
        assert len(loaded.components) == 3
        assert len(loaded.edges) == 2

    def test_save_creates_parent_dirs(self, detector: DriftDetector, baseline_graph: InfraGraph, tmp_path: Path):
        path = tmp_path / "subdir" / "nested" / "baseline.json"
        detector.save_baseline(baseline_graph, path)
        assert path.exists()

    def test_load_missing_file(self, detector: DriftDetector, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            detector.load_baseline(tmp_path / "nonexistent.json")

    def test_baseline_json_structure(self, detector: DriftDetector, baseline_graph: InfraGraph, tmp_path: Path):
        path = tmp_path / "baseline.json"
        detector.save_baseline(baseline_graph, path)

        data = json.loads(path.read_text())
        assert data["version"] == "1.0"
        assert "infrastructure_id" in data
        assert "timestamp" in data
        assert "resilience_score" in data
        assert "components" in data
        assert "edges" in data
        assert isinstance(data["components"], dict)
        assert isinstance(data["edges"], list)

    def test_load_baseline_with_unknown_version(self, detector: DriftDetector, tmp_path: Path):
        path = tmp_path / "baseline.json"
        data = {
            "version": "99.0",
            "infrastructure_id": "test",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "resilience_score": 50.0,
            "components": {},
            "edges": [],
        }
        path.write_text(json.dumps(data))
        loaded = detector.load_baseline(path)
        assert loaded.infrastructure_id == "test"


# ---------------------------------------------------------------------------
# DriftDetector.detect Tests — Component Drifts
# ---------------------------------------------------------------------------


class TestDetectComponentDrifts:
    def test_no_drift(self, detector: DriftDetector, baseline_graph: InfraGraph, tmp_path: Path):
        """Identical baseline and current should produce no drifts."""
        path = tmp_path / "baseline.json"
        baseline = detector.save_baseline(baseline_graph, path)
        report = detector.detect(baseline, baseline_graph)

        assert report.total_drifts == 0
        assert report.critical_drifts == 0
        assert report.high_drifts == 0
        assert report.risk_trend in ("stable", "improving")
        assert "No drift" in report.summary

    def test_replica_reduction(self, detector: DriftDetector, tmp_path: Path):
        """Reducing replicas should be detected."""
        original = _make_graph(
            components=[_web_api(replicas=3), _postgres(replicas=2)],
            dependencies=[_dep("web-api", "postgres")],
        )
        reduced = _make_graph(
            components=[_web_api(replicas=1), _postgres(replicas=2)],
            dependencies=[_dep("web-api", "postgres")],
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, reduced)

        replica_events = [
            e for e in report.events
            if e.drift_type == DriftType.REPLICA_REDUCTION
        ]
        assert len(replica_events) >= 1
        assert replica_events[0].component_id == "web-api"
        assert replica_events[0].baseline_value == 3
        assert replica_events[0].current_value == 1

    def test_autoscaling_disabled(self, detector: DriftDetector, tmp_path: Path):
        """Disabling autoscaling should be detected as HIGH severity."""
        original = _make_graph(components=[_web_api(autoscaling=True)])
        modified = _make_graph(components=[_web_api(autoscaling=False)])

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, modified)

        as_events = [
            e for e in report.events
            if e.drift_type == DriftType.AUTOSCALING_DISABLED
        ]
        assert len(as_events) == 1
        assert as_events[0].severity == DriftSeverity.HIGH

    def test_failover_disabled(self, detector: DriftDetector, tmp_path: Path):
        """Disabling failover should be detected as CRITICAL."""
        original = _make_graph(components=[_web_api(failover=True)])
        modified = _make_graph(components=[_web_api(failover=False)])

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, modified)

        fo_events = [
            e for e in report.events
            if e.drift_type == DriftType.FAILOVER_DISABLED
        ]
        assert len(fo_events) == 1
        assert fo_events[0].severity == DriftSeverity.CRITICAL
        assert report.critical_drifts >= 1

    def test_health_check_interval_increased(self, detector: DriftDetector, tmp_path: Path):
        """Significantly increasing health check interval should be detected."""
        original = _make_graph(
            components=[_web_api(failover=True, failover_health_check_interval=10.0)]
        )
        modified = _make_graph(
            components=[_web_api(failover=True, failover_health_check_interval=60.0)]
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, modified)

        hc_events = [
            e for e in report.events
            if e.drift_type == DriftType.HEALTH_CHECK_REMOVED
        ]
        assert len(hc_events) == 1
        assert hc_events[0].baseline_value == 10.0
        assert hc_events[0].current_value == 60.0

    def test_component_removed(self, detector: DriftDetector, tmp_path: Path):
        """Removing a component should be detected."""
        original = _make_graph(
            components=[_web_api(), _postgres(), _redis()],
            dependencies=[
                _dep("web-api", "postgres"),
                _dep("web-api", "redis", dep_type="optional"),
            ],
        )
        reduced = _make_graph(
            components=[_web_api(), _postgres()],
            dependencies=[_dep("web-api", "postgres")],
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, reduced)

        removed = [
            e for e in report.events
            if e.drift_type == DriftType.COMPONENT_REMOVED
        ]
        assert len(removed) == 1
        assert removed[0].component_id == "redis"

    def test_component_added(self, detector: DriftDetector, tmp_path: Path):
        """Adding a component should be detected as INFO."""
        original = _make_graph(components=[_web_api()])
        expanded = _make_graph(components=[_web_api(), _redis()])

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, expanded)

        added = [
            e for e in report.events
            if e.drift_type == DriftType.COMPONENT_ADDED
        ]
        assert len(added) == 1
        assert added[0].component_id == "redis"
        assert added[0].severity == DriftSeverity.INFO

    def test_capacity_reduced(self, detector: DriftDetector, tmp_path: Path):
        """Reducing capacity should be detected."""
        original = _make_graph(
            components=[_web_api(max_connections=1000)]
        )
        reduced = _make_graph(
            components=[_web_api(max_connections=200)]
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, reduced)

        cap_events = [
            e for e in report.events
            if e.drift_type == DriftType.CAPACITY_REDUCED
        ]
        assert len(cap_events) >= 1
        assert any(e.field == "capacity.max_connections" for e in cap_events)

    def test_security_weakened(self, detector: DriftDetector, tmp_path: Path):
        """Disabling security features should be detected."""
        original = _make_graph(
            components=[_web_api(encryption_at_rest=True)]
        )
        weakened = _make_graph(
            components=[_web_api(encryption_at_rest=False)]
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, weakened)

        sec_events = [
            e for e in report.events
            if e.drift_type == DriftType.SECURITY_WEAKENED
        ]
        assert len(sec_events) >= 1
        assert sec_events[0].field == "security.encryption_at_rest"


# ---------------------------------------------------------------------------
# DriftDetector.detect Tests — Edge/Dependency Drifts
# ---------------------------------------------------------------------------


class TestDetectEdgeDrifts:
    def test_dependency_added(self, detector: DriftDetector, tmp_path: Path):
        """Adding a new dependency should be detected."""
        original = _make_graph(
            components=[_web_api(), _postgres()],
            dependencies=[_dep("web-api", "postgres")],
        )
        expanded = _make_graph(
            components=[_web_api(), _postgres(), _redis()],
            dependencies=[
                _dep("web-api", "postgres"),
                _dep("web-api", "redis"),
            ],
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, expanded)

        dep_added = [
            e for e in report.events
            if e.drift_type == DriftType.DEPENDENCY_ADDED
        ]
        assert len(dep_added) == 1

    def test_dependency_removed(self, detector: DriftDetector, tmp_path: Path):
        """Removing a dependency should be detected."""
        original = _make_graph(
            components=[_web_api(), _postgres(), _redis()],
            dependencies=[
                _dep("web-api", "postgres"),
                _dep("web-api", "redis"),
            ],
        )
        reduced = _make_graph(
            components=[_web_api(), _postgres(), _redis()],
            dependencies=[_dep("web-api", "postgres")],
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, reduced)

        dep_removed = [
            e for e in report.events
            if e.drift_type == DriftType.DEPENDENCY_REMOVED
        ]
        assert len(dep_removed) == 1

    def test_circuit_breaker_disabled(self, detector: DriftDetector, tmp_path: Path):
        """Disabling a circuit breaker should be detected."""
        original = _make_graph(
            components=[_web_api(), _postgres()],
            dependencies=[_dep("web-api", "postgres", circuit_breaker=True)],
        )
        modified = _make_graph(
            components=[_web_api(), _postgres()],
            dependencies=[_dep("web-api", "postgres", circuit_breaker=False)],
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, modified)

        cb_events = [
            e for e in report.events
            if e.drift_type == DriftType.CIRCUIT_BREAKER_DISABLED
        ]
        assert len(cb_events) == 1
        assert cb_events[0].severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL)


# ---------------------------------------------------------------------------
# DriftDetector.detect Tests — SPOF Detection
# ---------------------------------------------------------------------------


class TestDetectSPOFs:
    def test_new_spof_introduced(self, detector: DriftDetector, tmp_path: Path):
        """A new component with replicas=1 and dependents should be flagged."""
        original = _make_graph(components=[_web_api()])
        expanded = _make_graph(
            components=[
                _web_api(),
                Component(
                    id="new-service",
                    name="New Service",
                    type=ComponentType.APP_SERVER,
                    replicas=1,
                ),
            ],
            dependencies=[_dep("web-api", "new-service")],
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, expanded)

        spof_events = [
            e for e in report.events
            if e.drift_type == DriftType.NEW_SPOF_INTRODUCED
        ]
        assert len(spof_events) == 1
        assert spof_events[0].component_id == "new-service"
        assert spof_events[0].severity == DriftSeverity.HIGH

    def test_new_component_with_replicas_no_spof(self, detector: DriftDetector, tmp_path: Path):
        """A new component with multiple replicas should not be flagged as SPOF."""
        original = _make_graph(components=[_web_api()])
        expanded = _make_graph(
            components=[
                _web_api(),
                Component(
                    id="new-service",
                    name="New Service",
                    type=ComponentType.APP_SERVER,
                    replicas=3,
                ),
            ],
            dependencies=[_dep("web-api", "new-service")],
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, expanded)

        spof_events = [
            e for e in report.events
            if e.drift_type == DriftType.NEW_SPOF_INTRODUCED
        ]
        assert len(spof_events) == 0


# ---------------------------------------------------------------------------
# DriftDetector — Full Degradation Scenario
# ---------------------------------------------------------------------------


class TestFullDegradation:
    def test_full_degradation(
        self,
        detector: DriftDetector,
        baseline_graph: InfraGraph,
        degraded_graph: InfraGraph,
        tmp_path: Path,
    ):
        """A fully degraded infrastructure should have many critical drifts."""
        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(baseline_graph, path)
        report = detector.detect(baseline, degraded_graph)

        assert report.total_drifts > 0
        assert report.critical_drifts > 0
        assert report.score_delta < 0
        assert report.risk_trend in ("degrading", "critical_degradation")

        # Should detect replica reductions
        replica_events = [
            e for e in report.events
            if e.drift_type == DriftType.REPLICA_REDUCTION
        ]
        assert len(replica_events) >= 1

        # Should detect failover disabled
        fo_events = [
            e for e in report.events
            if e.drift_type == DriftType.FAILOVER_DISABLED
        ]
        assert len(fo_events) >= 1

        # Should detect autoscaling disabled
        as_events = [
            e for e in report.events
            if e.drift_type == DriftType.AUTOSCALING_DISABLED
        ]
        assert len(as_events) >= 1

        # Should detect circuit breaker disabled
        cb_events = [
            e for e in report.events
            if e.drift_type == DriftType.CIRCUIT_BREAKER_DISABLED
        ]
        assert len(cb_events) >= 1


# ---------------------------------------------------------------------------
# DriftDetector.auto_detect_severity Tests
# ---------------------------------------------------------------------------


class TestAutoDetectSeverity:
    def test_failover_disabled_is_critical(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.FAILOVER_DISABLED, True, False
        )
        assert sev == DriftSeverity.CRITICAL

    def test_circuit_breaker_disabled_is_high(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.CIRCUIT_BREAKER_DISABLED, True, False
        )
        assert sev == DriftSeverity.HIGH

    def test_autoscaling_disabled_is_high(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.AUTOSCALING_DISABLED, True, False
        )
        assert sev == DriftSeverity.HIGH

    def test_replica_to_one_is_critical(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.REPLICA_REDUCTION, 3, 1
        )
        assert sev == DriftSeverity.CRITICAL

    def test_replica_halved_is_high(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.REPLICA_REDUCTION, 10, 4
        )
        assert sev == DriftSeverity.HIGH

    def test_replica_minor_reduction_is_medium(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.REPLICA_REDUCTION, 4, 3
        )
        assert sev == DriftSeverity.MEDIUM

    def test_component_added_is_info(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.COMPONENT_ADDED, None, "new-comp"
        )
        assert sev == DriftSeverity.INFO

    def test_component_removed_is_high(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.COMPONENT_REMOVED, "old-comp", None
        )
        assert sev == DriftSeverity.HIGH

    def test_capacity_halved_is_high(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.CAPACITY_REDUCED, 1000, 400
        )
        assert sev == DriftSeverity.HIGH

    def test_capacity_minor_reduction_is_medium(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.CAPACITY_REDUCED, 1000, 800
        )
        assert sev == DriftSeverity.MEDIUM

    def test_new_spof_is_high(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.NEW_SPOF_INTRODUCED, None, 1
        )
        assert sev == DriftSeverity.HIGH

    def test_dependency_added_is_low(self, detector: DriftDetector):
        sev = detector.auto_detect_severity(
            DriftType.DEPENDENCY_ADDED, None, "new-dep"
        )
        assert sev == DriftSeverity.LOW


# ---------------------------------------------------------------------------
# DriftDetector.calculate_resilience_impact Tests
# ---------------------------------------------------------------------------


class TestCalculateResilienceImpact:
    def test_failover_disabled_impact(self, detector: DriftDetector):
        graph = _make_graph(components=[_web_api()])
        event = DriftEvent(
            drift_type=DriftType.FAILOVER_DISABLED,
            severity=DriftSeverity.CRITICAL,
            component_id="web-api",
            component_name="Web API",
            field="failover.enabled",
            baseline_value=True,
            current_value=False,
            description="",
            resilience_impact=0.0,
            remediation="",
        )
        impact = detector.calculate_resilience_impact(event, graph)
        assert impact < 0

    def test_impact_scales_with_dependents(self, detector: DriftDetector):
        graph = _make_graph(
            components=[
                _web_api(),
                Component(id="svc-1", name="Service 1", type=ComponentType.APP_SERVER),
                Component(id="svc-2", name="Service 2", type=ComponentType.APP_SERVER),
                Component(id="svc-3", name="Service 3", type=ComponentType.APP_SERVER),
            ],
            dependencies=[
                _dep("svc-1", "web-api"),
                _dep("svc-2", "web-api"),
                _dep("svc-3", "web-api"),
            ],
        )
        event = DriftEvent(
            drift_type=DriftType.FAILOVER_DISABLED,
            severity=DriftSeverity.CRITICAL,
            component_id="web-api",
            component_name="Web API",
            field="failover.enabled",
            baseline_value=True,
            current_value=False,
            description="",
            resilience_impact=0.0,
            remediation="",
        )
        impact = detector.calculate_resilience_impact(event, graph)
        # With 3 dependents (>2), impact should be amplified
        assert impact < -10.0

    def test_component_added_zero_impact(self, detector: DriftDetector):
        graph = _make_graph(components=[_web_api()])
        event = DriftEvent(
            drift_type=DriftType.COMPONENT_ADDED,
            severity=DriftSeverity.INFO,
            component_id="web-api",
            component_name="Web API",
            field="component",
            baseline_value=None,
            current_value="web-api",
            description="",
            resilience_impact=0.0,
            remediation="",
        )
        impact = detector.calculate_resilience_impact(event, graph)
        assert impact == 0.0


# ---------------------------------------------------------------------------
# DriftDetector.detect_from_file Tests
# ---------------------------------------------------------------------------


class TestDetectFromFile:
    def test_detect_from_yaml(self, detector: DriftDetector, tmp_path: Path):
        """detect_from_file should work with YAML infrastructure files."""
        # Create baseline
        graph = _make_graph(
            components=[_web_api(replicas=3), _postgres()],
            dependencies=[_dep("web-api", "postgres")],
        )
        bl_path = tmp_path / "baseline.json"
        detector.save_baseline(graph, bl_path)

        # Create a modified YAML
        yaml_content = """
components:
  - id: web-api
    name: Web API
    type: app_server
    replicas: 1
  - id: postgres
    name: PostgreSQL
    type: database
    replicas: 2

dependencies:
  - source: web-api
    target: postgres
    type: requires
"""
        yaml_path = tmp_path / "current.yaml"
        yaml_path.write_text(yaml_content)

        report = detector.detect_from_file(bl_path, yaml_path)
        assert report.total_drifts > 0

        # Replica reduction should be detected
        replica_events = [
            e for e in report.events
            if e.drift_type == DriftType.REPLICA_REDUCTION
        ]
        assert len(replica_events) >= 1


# ---------------------------------------------------------------------------
# Risk Trend and Summary Tests
# ---------------------------------------------------------------------------


class TestRiskTrend:
    def test_stable_when_no_drifts(self):
        trend = DriftDetector._determine_risk_trend(0.0, 0, 0, 0)
        assert trend == "stable"

    def test_improving_when_score_increases(self):
        trend = DriftDetector._determine_risk_trend(10.0, 0, 0, 0)
        assert trend == "improving"

    def test_degrading_when_high_drifts(self):
        trend = DriftDetector._determine_risk_trend(-3.0, 0, 2, 5)
        assert trend == "degrading"

    def test_critical_degradation_when_critical_drifts(self):
        trend = DriftDetector._determine_risk_trend(-15.0, 2, 1, 5)
        assert trend == "critical_degradation"

    def test_critical_degradation_from_score_drop(self):
        trend = DriftDetector._determine_risk_trend(-12.0, 0, 0, 3)
        assert trend == "critical_degradation"


class TestBuildSummary:
    def test_no_drift_summary(self):
        summary = DriftDetector._build_summary(0, 0, 0, 80.0, 80.0, 0.0, "stable")
        assert "No drift" in summary
        assert "stable" in summary.lower()

    def test_drift_summary_with_critical(self):
        summary = DriftDetector._build_summary(5, 2, 1, 80.0, 65.0, -15.0, "critical_degradation")
        assert "5 drift" in summary
        assert "2 CRITICAL" in summary
        assert "1 HIGH" in summary
        assert "CRITICAL DEGRADATION" in summary

    def test_summary_includes_score_delta(self):
        summary = DriftDetector._build_summary(3, 0, 1, 85.0, 78.0, -7.0, "degrading")
        assert "85.0" in summary
        assert "78.0" in summary
        assert "-7.0" in summary


# ---------------------------------------------------------------------------
# Event Sorting Tests
# ---------------------------------------------------------------------------


class TestEventSorting:
    def test_events_sorted_by_severity(self, detector: DriftDetector, tmp_path: Path):
        """Events should be sorted by severity (critical first)."""
        original = _make_graph(
            components=[
                _web_api(
                    replicas=3,
                    failover=True,
                    autoscaling=True,
                    encryption_at_rest=True,
                ),
                _postgres(replicas=2, failover=True),
            ],
            dependencies=[_dep("web-api", "postgres", circuit_breaker=True)],
        )
        degraded = _make_graph(
            components=[
                _web_api(
                    replicas=1,
                    failover=False,
                    autoscaling=False,
                    encryption_at_rest=False,
                ),
                _postgres(replicas=1, failover=False),
            ],
            dependencies=[_dep("web-api", "postgres", circuit_breaker=False)],
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, degraded)

        # Verify events are sorted by severity
        severity_order = {
            DriftSeverity.CRITICAL: 0,
            DriftSeverity.HIGH: 1,
            DriftSeverity.MEDIUM: 2,
            DriftSeverity.LOW: 3,
            DriftSeverity.INFO: 4,
        }
        for i in range(len(report.events) - 1):
            current_order = severity_order[report.events[i].severity]
            next_order = severity_order[report.events[i + 1].severity]
            assert current_order <= next_order


# ---------------------------------------------------------------------------
# Edge Case Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_baseline(self, detector: DriftDetector, tmp_path: Path):
        """Empty baseline vs populated current should detect all as additions."""
        empty = _make_graph()
        populated = _make_graph(components=[_web_api(), _postgres()])

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(empty, path)
        report = detector.detect(baseline, populated)

        added = [
            e for e in report.events
            if e.drift_type == DriftType.COMPONENT_ADDED
        ]
        assert len(added) == 2

    def test_populated_baseline_vs_empty_current(self, detector: DriftDetector, tmp_path: Path):
        """Populated baseline vs empty current should detect all as removals."""
        populated = _make_graph(components=[_web_api(), _postgres()])
        empty = _make_graph()

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(populated, path)
        report = detector.detect(baseline, empty)

        removed = [
            e for e in report.events
            if e.drift_type == DriftType.COMPONENT_REMOVED
        ]
        assert len(removed) == 2

    def test_drift_velocity_calculation(self, detector: DriftDetector, tmp_path: Path):
        """Drift velocity should be calculated correctly."""
        graph = _make_graph(components=[_web_api(replicas=3)])
        reduced = _make_graph(components=[_web_api(replicas=1)])

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(graph, path)
        report = detector.detect(baseline, reduced)

        # Drift velocity should be a positive number
        assert report.drift_velocity >= 0

    def test_report_to_dict_serializable(self, detector: DriftDetector, tmp_path: Path):
        """Report.to_dict() output should be JSON-serializable."""
        original = _make_graph(
            components=[_web_api(replicas=3, failover=True)],
        )
        modified = _make_graph(
            components=[_web_api(replicas=1, failover=False)],
        )

        path = tmp_path / "bl.json"
        baseline = detector.save_baseline(original, path)
        report = detector.detect(baseline, modified)

        # This should not raise
        data = report.to_dict()
        json_str = json.dumps(data)
        assert json_str  # non-empty

        # Verify it round-trips
        parsed = json.loads(json_str)
        assert parsed["total_drifts"] == report.total_drifts
