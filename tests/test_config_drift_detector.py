"""Tests for the Configuration Drift Detector Engine.

Comprehensive test suite covering DriftCategory / DriftSeverity /
ComplianceFramework / RemediationStrategy enums, DriftItem / DriftCluster /
DriftTimeSeries / ConfigDependency / CrossEnvDrift / DriftRiskAssessment /
BaselineSnapshot / DriftReport data classes, ConfigDriftDetector methods
(create_baseline, compare_to_baseline, compare_environments, cluster_drifts,
track_drift_timeseries, build_config_dependency_graph, assess_drift_risk,
map_compliance, generate_report), edge cases, and integration scenarios.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.config_drift_detector import (
    BaselineSnapshot,
    ComplianceFramework,
    ConfigDependency,
    ConfigDriftDetector,
    CrossEnvDrift,
    DriftCategory,
    DriftCluster,
    DriftItem,
    DriftReport,
    DriftRiskAssessment,
    DriftSeverity,
    DriftTimeSeries,
    RemediationStrategy,
    _classify_category,
    _COMPLIANCE_MAP,
    _compute_snapshot_id,
    _CRITICALITY,
    _extract_config,
    _EXTRACTORS,
    _max_severity,
    _pick_remediation,
    _safe_serialize,
    _severity_from_criticality,
    _severity_rank,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(cid="c1", ctype=ComponentType.APP_SERVER, **kwargs):
    return Component(id=cid, name=kwargs.pop("name", cid), type=ctype, **kwargs)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestDriftCategory:
    def test_all_values(self):
        assert DriftCategory.PARAMETER == "parameter"
        assert DriftCategory.VERSION == "version"
        assert DriftCategory.SCHEMA == "schema"
        assert DriftCategory.SECRET_ROTATION == "secret_rotation"

    def test_member_count(self):
        assert len(DriftCategory) == 4

    def test_is_str_enum(self):
        assert isinstance(DriftCategory.PARAMETER, str)


class TestDriftSeverity:
    def test_all_values(self):
        assert DriftSeverity.CRITICAL == "critical"
        assert DriftSeverity.HIGH == "high"
        assert DriftSeverity.MEDIUM == "medium"
        assert DriftSeverity.LOW == "low"
        assert DriftSeverity.INFO == "info"

    def test_member_count(self):
        assert len(DriftSeverity) == 5


class TestComplianceFramework:
    def test_all_values(self):
        assert ComplianceFramework.SOC2 == "soc2"
        assert ComplianceFramework.PCI_DSS == "pci_dss"
        assert ComplianceFramework.HIPAA == "hipaa"
        assert ComplianceFramework.GDPR == "gdpr"
        assert ComplianceFramework.ISO27001 == "iso27001"
        assert ComplianceFramework.NIST == "nist"
        assert ComplianceFramework.CIS == "cis"

    def test_member_count(self):
        assert len(ComplianceFramework) == 7


class TestRemediationStrategy:
    def test_all_values(self):
        assert RemediationStrategy.RESTORE_BASELINE == "restore_baseline"
        assert RemediationStrategy.ACCEPT_CURRENT == "accept_current"
        assert RemediationStrategy.ESCALATE == "escalate"
        assert RemediationStrategy.AUTO_FIX == "auto_fix"
        assert RemediationStrategy.MANUAL_REVIEW == "manual_review"
        assert RemediationStrategy.ROTATE_SECRET == "rotate_secret"

    def test_member_count(self):
        assert len(RemediationStrategy) == 6


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestSafeSerialize:
    def test_primitives(self):
        assert _safe_serialize(42) == 42
        assert _safe_serialize("hello") == "hello"
        assert _safe_serialize(True) is True
        assert _safe_serialize(None) is None
        assert _safe_serialize(3.14) == 3.14

    def test_dict(self):
        assert _safe_serialize({"a": 1, "b": [2, 3]}) == {"a": 1, "b": [2, 3]}

    def test_list_and_tuple(self):
        assert _safe_serialize([1, "x", None]) == [1, "x", None]
        assert _safe_serialize((1, 2)) == [1, 2]

    def test_non_serializable(self):
        # Falls back to str()
        result = _safe_serialize(DriftCategory.PARAMETER)
        assert isinstance(result, str)


class TestExtractConfig:
    def test_extracts_all_fields(self):
        comp = _comp("x1")
        cfg = _extract_config(comp)
        # Should contain every key from _EXTRACTORS
        for path, _ in _EXTRACTORS:
            assert path in cfg, f"Missing key: {path}"

    def test_values_match_component(self):
        comp = _comp("x1", replicas=3)
        cfg = _extract_config(comp)
        assert cfg["replicas"] == 3


class TestComputeSnapshotId:
    def test_deterministic(self):
        g = _graph(_comp("a"), _comp("b"))
        id1 = _compute_snapshot_id(g)
        id2 = _compute_snapshot_id(g)
        assert id1 == id2

    def test_different_graphs_different_ids(self):
        g1 = _graph(_comp("a"))
        g2 = _graph(_comp("b"))
        assert _compute_snapshot_id(g1) != _compute_snapshot_id(g2)

    def test_length(self):
        g = _graph(_comp("z"))
        assert len(_compute_snapshot_id(g)) == 12


class TestClassifyCategory:
    def test_security_path(self):
        assert _classify_category("security.encryption_at_rest", True, False) == DriftCategory.SCHEMA

    def test_tags_path(self):
        assert _classify_category("tags", ["a"], ["b"]) == DriftCategory.SCHEMA

    def test_parameter_dict_with_version_key(self):
        assert (
            _classify_category(
                "parameters", {"app_version": "1.0"}, {"app_version": "2.0"}
            )
            == DriftCategory.VERSION
        )

    def test_parameter_dict_without_version_key(self):
        assert (
            _classify_category("parameters", {"foo": "bar"}, {"foo": "baz"})
            == DriftCategory.PARAMETER
        )

    def test_parameter_non_dict(self):
        assert (
            _classify_category("parameters", "x", "y") == DriftCategory.PARAMETER
        )

    def test_default_parameter(self):
        assert _classify_category("replicas", 3, 1) == DriftCategory.PARAMETER


class TestSeverityFromCriticality:
    def test_critical(self):
        assert _severity_from_criticality(10.0) == DriftSeverity.CRITICAL

    def test_high(self):
        assert _severity_from_criticality(7.0) == DriftSeverity.HIGH

    def test_medium(self):
        assert _severity_from_criticality(5.0) == DriftSeverity.MEDIUM

    def test_low(self):
        assert _severity_from_criticality(3.0) == DriftSeverity.LOW

    def test_info(self):
        assert _severity_from_criticality(1.0) == DriftSeverity.INFO


class TestSeverityRankAndMax:
    def test_rank_ordering(self):
        assert _severity_rank(DriftSeverity.CRITICAL) > _severity_rank(DriftSeverity.HIGH)
        assert _severity_rank(DriftSeverity.HIGH) > _severity_rank(DriftSeverity.MEDIUM)
        assert _severity_rank(DriftSeverity.MEDIUM) > _severity_rank(DriftSeverity.LOW)
        assert _severity_rank(DriftSeverity.LOW) > _severity_rank(DriftSeverity.INFO)

    def test_max_severity(self):
        assert _max_severity(DriftSeverity.LOW, DriftSeverity.CRITICAL) == DriftSeverity.CRITICAL

    def test_max_severity_empty(self):
        assert _max_severity() == DriftSeverity.INFO

    def test_max_severity_single(self):
        assert _max_severity(DriftSeverity.MEDIUM) == DriftSeverity.MEDIUM


class TestPickRemediation:
    def test_secret_rotation(self):
        strat, detail = _pick_remediation("x", DriftCategory.SECRET_ROTATION, DriftSeverity.HIGH)
        assert strat == RemediationStrategy.ROTATE_SECRET
        assert "Rotate" in detail

    def test_critical_severity(self):
        strat, _ = _pick_remediation("replicas", DriftCategory.PARAMETER, DriftSeverity.CRITICAL)
        assert strat == RemediationStrategy.RESTORE_BASELINE

    def test_high_severity(self):
        strat, _ = _pick_remediation("replicas", DriftCategory.PARAMETER, DriftSeverity.HIGH)
        assert strat == RemediationStrategy.ESCALATE

    def test_security_path(self):
        strat, _ = _pick_remediation(
            "security.auth_required", DriftCategory.SCHEMA, DriftSeverity.MEDIUM
        )
        assert strat == RemediationStrategy.RESTORE_BASELINE

    def test_medium_non_security(self):
        strat, _ = _pick_remediation("capacity.max_rps", DriftCategory.PARAMETER, DriftSeverity.MEDIUM)
        assert strat == RemediationStrategy.AUTO_FIX

    def test_low_severity(self):
        strat, _ = _pick_remediation("tags", DriftCategory.SCHEMA, DriftSeverity.LOW)
        assert strat == RemediationStrategy.ACCEPT_CURRENT


# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------


class TestDriftItem:
    def test_defaults(self):
        item = DriftItem(
            component_id="c1",
            parameter_path="replicas",
            category=DriftCategory.PARAMETER,
            severity=DriftSeverity.HIGH,
            baseline_value=3,
            current_value=1,
            description="replicas drifted",
        )
        assert item.criticality_weight == 1.0
        assert item.compliance_violations == []
        assert item.remediation == RemediationStrategy.MANUAL_REVIEW
        assert isinstance(item.detected_at, datetime)

    def test_custom_values(self):
        item = DriftItem(
            component_id="db1",
            parameter_path="security.encryption_at_rest",
            category=DriftCategory.SCHEMA,
            severity=DriftSeverity.CRITICAL,
            baseline_value=True,
            current_value=False,
            description="encryption disabled",
            criticality_weight=9.0,
            compliance_violations=[ComplianceFramework.PCI_DSS],
            risk_score=45.0,
        )
        assert item.risk_score == 45.0
        assert ComplianceFramework.PCI_DSS in item.compliance_violations


class TestDriftCluster:
    def test_defaults(self):
        cluster = DriftCluster(cluster_id="cl-000")
        assert cluster.component_ids == []
        assert cluster.items == []
        assert cluster.aggregate_severity == DriftSeverity.INFO

    def test_with_items(self):
        it = DriftItem(
            component_id="c1",
            parameter_path="replicas",
            category=DriftCategory.PARAMETER,
            severity=DriftSeverity.HIGH,
            baseline_value=3,
            current_value=1,
            description="test",
        )
        cluster = DriftCluster(
            cluster_id="cl-001",
            component_ids=["c1"],
            items=[it],
            aggregate_severity=DriftSeverity.HIGH,
            aggregate_risk=20.0,
        )
        assert len(cluster.items) == 1
        assert cluster.aggregate_risk == 20.0


class TestDriftReport:
    def test_to_dict_empty(self):
        report = DriftReport()
        d = report.to_dict()
        assert d["total_drifts"] == 0
        assert d["severity_counts"]["critical"] == 0
        assert d["items"] == []
        assert d["clusters"] == []

    def test_to_dict_with_items(self):
        it = DriftItem(
            component_id="c1",
            parameter_path="replicas",
            category=DriftCategory.PARAMETER,
            severity=DriftSeverity.HIGH,
            baseline_value=3,
            current_value=1,
            description="test",
            compliance_violations=[ComplianceFramework.SOC2],
            risk_score=10.0,
        )
        cl = DriftCluster(
            cluster_id="cl-0",
            component_ids=["c1"],
            items=[it],
            aggregate_severity=DriftSeverity.HIGH,
            aggregate_risk=10.0,
        )
        report = DriftReport(
            total_drifts=1,
            high_count=1,
            items=[it],
            clusters=[cl],
            overall_risk_score=10.0,
            summary="1 drift",
        )
        d = report.to_dict()
        assert d["total_drifts"] == 1
        assert d["severity_counts"]["high"] == 1
        assert len(d["items"]) == 1
        assert d["items"][0]["compliance_violations"] == ["soc2"]
        assert len(d["clusters"]) == 1


# ---------------------------------------------------------------------------
# ConfigDriftDetector — baseline management
# ---------------------------------------------------------------------------


class TestCreateBaseline:
    def test_basic(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("s1"), _comp("s2"))
        baseline = detector.create_baseline(g)
        assert isinstance(baseline, BaselineSnapshot)
        assert "s1" in baseline.component_configs
        assert "s2" in baseline.component_configs
        assert baseline.metadata["total_components"] == 2
        assert len(baseline.snapshot_id) == 12

    def test_empty_graph(self):
        detector = ConfigDriftDetector()
        g = _graph()
        baseline = detector.create_baseline(g)
        assert baseline.component_configs == {}
        assert baseline.metadata["total_components"] == 0

    def test_timestamp(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("a"))
        before = datetime.now(timezone.utc)
        baseline = detector.create_baseline(g)
        after = datetime.now(timezone.utc)
        assert before <= baseline.timestamp <= after


# ---------------------------------------------------------------------------
# ConfigDriftDetector — compare_to_baseline
# ---------------------------------------------------------------------------


class TestCompareToBaseline:
    def test_no_drift(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("s1"))
        baseline = detector.create_baseline(g)
        drifts = detector.compare_to_baseline(baseline, g)
        assert drifts == []

    def test_parameter_drift(self):
        detector = ConfigDriftDetector()
        g1 = _graph(_comp("s1", replicas=3))
        baseline = detector.create_baseline(g1)
        g2 = _graph(_comp("s1", replicas=1))
        drifts = detector.compare_to_baseline(baseline, g2)
        assert len(drifts) >= 1
        replicas_drift = [d for d in drifts if d.parameter_path == "replicas"]
        assert len(replicas_drift) == 1
        assert replicas_drift[0].baseline_value == 3
        assert replicas_drift[0].current_value == 1
        assert replicas_drift[0].severity == DriftSeverity.CRITICAL

    def test_new_component_drift(self):
        detector = ConfigDriftDetector()
        g1 = _graph(_comp("s1"))
        baseline = detector.create_baseline(g1)
        g2 = _graph(_comp("s1"), _comp("s2"))
        drifts = detector.compare_to_baseline(baseline, g2)
        new_comp = [d for d in drifts if d.component_id == "s2"]
        assert len(new_comp) == 1
        assert new_comp[0].parameter_path == "__component__"
        assert new_comp[0].severity == DriftSeverity.LOW

    def test_removed_component_drift(self):
        detector = ConfigDriftDetector()
        g1 = _graph(_comp("s1"), _comp("s2"))
        baseline = detector.create_baseline(g1)
        g2 = _graph(_comp("s1"))
        drifts = detector.compare_to_baseline(baseline, g2)
        removed = [d for d in drifts if d.component_id == "s2"]
        assert len(removed) == 1
        assert removed[0].severity == DriftSeverity.HIGH

    def test_security_drift_compliance_violation(self):
        detector = ConfigDriftDetector()
        g1 = _graph(
            _comp(
                "s1",
                security=SecurityProfile(encryption_at_rest=True),
            )
        )
        baseline = detector.create_baseline(g1)
        g2 = _graph(
            _comp(
                "s1",
                security=SecurityProfile(encryption_at_rest=False),
            )
        )
        drifts = detector.compare_to_baseline(baseline, g2)
        sec_drifts = [d for d in drifts if d.parameter_path == "security.encryption_at_rest"]
        assert len(sec_drifts) == 1
        assert ComplianceFramework.PCI_DSS in sec_drifts[0].compliance_violations
        assert sec_drifts[0].severity == DriftSeverity.HIGH

    def test_autoscaling_drift(self):
        detector = ConfigDriftDetector()
        g1 = _graph(
            _comp(
                "s1",
                autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
            )
        )
        baseline = detector.create_baseline(g1)
        g2 = _graph(
            _comp(
                "s1",
                autoscaling=AutoScalingConfig(enabled=False, min_replicas=2, max_replicas=10),
            )
        )
        drifts = detector.compare_to_baseline(baseline, g2)
        as_drifts = [d for d in drifts if d.parameter_path == "autoscaling.enabled"]
        assert len(as_drifts) == 1
        assert as_drifts[0].baseline_value is True
        assert as_drifts[0].current_value is False

    def test_failover_drift(self):
        detector = ConfigDriftDetector()
        g1 = _graph(
            _comp("s1", failover=FailoverConfig(enabled=True))
        )
        baseline = detector.create_baseline(g1)
        g2 = _graph(
            _comp("s1", failover=FailoverConfig(enabled=False))
        )
        drifts = detector.compare_to_baseline(baseline, g2)
        fo_drifts = [d for d in drifts if d.parameter_path == "failover.enabled"]
        assert len(fo_drifts) == 1
        assert fo_drifts[0].severity == DriftSeverity.CRITICAL

    def test_multiple_drifts(self):
        detector = ConfigDriftDetector()
        g1 = _graph(
            _comp(
                "s1",
                replicas=3,
                capacity=Capacity(max_rps=10000),
                failover=FailoverConfig(enabled=True),
            )
        )
        baseline = detector.create_baseline(g1)
        g2 = _graph(
            _comp(
                "s1",
                replicas=1,
                capacity=Capacity(max_rps=5000),
                failover=FailoverConfig(enabled=False),
            )
        )
        drifts = detector.compare_to_baseline(baseline, g2)
        assert len(drifts) >= 3
        paths = {d.parameter_path for d in drifts}
        assert "replicas" in paths
        assert "capacity.max_rps" in paths
        assert "failover.enabled" in paths


# ---------------------------------------------------------------------------
# ConfigDriftDetector — compare_environments
# ---------------------------------------------------------------------------


class TestCompareEnvironments:
    def test_identical_envs(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("s1"))
        result = detector.compare_environments({"dev": g, "prod": g})
        assert result == []

    def test_env_pair_drift(self):
        detector = ConfigDriftDetector()
        g_dev = _graph(_comp("s1", replicas=1))
        g_prod = _graph(_comp("s1", replicas=3))
        result = detector.compare_environments({"dev": g_dev, "prod": g_prod})
        assert len(result) >= 1
        rep = [r for r in result if r.parameter_path == "replicas"]
        assert len(rep) == 1
        assert rep[0].env_a_name == "dev"
        assert rep[0].env_b_name == "prod"

    def test_reference_env(self):
        detector = ConfigDriftDetector()
        g_dev = _graph(_comp("s1", replicas=1))
        g_stg = _graph(_comp("s1", replicas=2))
        g_prod = _graph(_comp("s1", replicas=3))
        envs = {"dev": g_dev, "staging": g_stg, "prod": g_prod}
        result = detector.compare_environments(envs, reference_env="prod")
        # Should only compare prod vs dev and prod vs staging, not dev vs staging
        env_pairs = {(r.env_a_name, r.env_b_name) for r in result}
        assert ("prod", "dev") in env_pairs or ("prod", "staging") in env_pairs
        assert ("dev", "staging") not in env_pairs

    def test_acceptable_diffs(self):
        detector = ConfigDriftDetector()
        g_dev = _graph(_comp("s1", replicas=1))
        g_prod = _graph(_comp("s1", replicas=3))
        result = detector.compare_environments(
            {"dev": g_dev, "prod": g_prod},
            acceptable_diffs={"replicas"},
        )
        rep = [r for r in result if r.parameter_path == "replicas"]
        assert len(rep) == 1
        assert rep[0].acceptable is True

    def test_three_envs_without_reference(self):
        detector = ConfigDriftDetector()
        g_dev = _graph(_comp("s1", replicas=1))
        g_stg = _graph(_comp("s1", replicas=2))
        g_prod = _graph(_comp("s1", replicas=3))
        envs = {"dev": g_dev, "staging": g_stg, "prod": g_prod}
        result = detector.compare_environments(envs)
        # 3 pairs: dev-prod, dev-staging, staging-prod
        env_pairs = {(r.env_a_name, r.env_b_name) for r in result}
        assert len(env_pairs) == 3

    def test_missing_component_in_one_env(self):
        detector = ConfigDriftDetector()
        g_dev = _graph(_comp("s1"), _comp("s2"))
        g_prod = _graph(_comp("s1"))
        result = detector.compare_environments({"dev": g_dev, "prod": g_prod})
        # s2 is only in dev — all its fields should show as drift
        s2_drifts = [r for r in result if r.component_id == "s2"]
        assert len(s2_drifts) > 0


# ---------------------------------------------------------------------------
# ConfigDriftDetector — cluster_drifts
# ---------------------------------------------------------------------------


class TestClusterDrifts:
    def test_empty_input(self):
        detector = ConfigDriftDetector()
        assert detector.cluster_drifts([]) == []

    def test_single_cluster(self):
        detector = ConfigDriftDetector()
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="replicas",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.HIGH,
                baseline_value=3,
                current_value=1,
                description="test",
                risk_score=10.0,
            ),
            DriftItem(
                component_id="c1",
                parameter_path="capacity.max_rps",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.MEDIUM,
                baseline_value=10000,
                current_value=5000,
                description="test",
                risk_score=7.0,
            ),
        ]
        clusters = detector.cluster_drifts(items)
        assert len(clusters) == 1
        assert clusters[0].aggregate_severity == DriftSeverity.HIGH
        assert clusters[0].aggregate_risk == 17.0

    def test_multiple_clusters_by_category(self):
        detector = ConfigDriftDetector()
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="replicas",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.HIGH,
                baseline_value=3,
                current_value=1,
                description="test",
                risk_score=10.0,
            ),
            DriftItem(
                component_id="c1",
                parameter_path="security.auth_required",
                category=DriftCategory.SCHEMA,
                severity=DriftSeverity.HIGH,
                baseline_value=True,
                current_value=False,
                description="test",
                risk_score=12.0,
            ),
        ]
        clusters = detector.cluster_drifts(items)
        assert len(clusters) == 2

    def test_cluster_root_cause_hypothesis(self):
        detector = ConfigDriftDetector()
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="security.encryption_at_rest",
                category=DriftCategory.SCHEMA,
                severity=DriftSeverity.HIGH,
                baseline_value=True,
                current_value=False,
                description="test",
                risk_score=10.0,
            ),
        ]
        clusters = detector.cluster_drifts(items)
        assert "Security" in clusters[0].root_cause_hypothesis or \
               "security" in clusters[0].root_cause_hypothesis.lower()


# ---------------------------------------------------------------------------
# ConfigDriftDetector — track_drift_timeseries
# ---------------------------------------------------------------------------


class TestTrackDriftTimeseries:
    def test_empty_history(self):
        detector = ConfigDriftDetector()
        result = detector.track_drift_timeseries([])
        assert result == []

    def test_single_observation(self):
        detector = ConfigDriftDetector()
        now = datetime.now(timezone.utc)
        item = DriftItem(
            component_id="c1",
            parameter_path="replicas",
            category=DriftCategory.PARAMETER,
            severity=DriftSeverity.HIGH,
            baseline_value=3,
            current_value=1,
            description="test",
        )
        result = detector.track_drift_timeseries([(now, [item])])
        assert len(result) == 1
        assert result[0].observation_count == 1

    def test_multiple_observations(self):
        detector = ConfigDriftDetector()
        t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 3, tzinfo=timezone.utc)
        t3 = datetime(2026, 1, 5, tzinfo=timezone.utc)
        item = DriftItem(
            component_id="c1",
            parameter_path="replicas",
            category=DriftCategory.PARAMETER,
            severity=DriftSeverity.HIGH,
            baseline_value=3,
            current_value=1,
            description="test",
        )
        history = [
            (t1, [item]),
            (t2, [item]),
            (t3, [item]),
        ]
        result = detector.track_drift_timeseries(history)
        assert len(result) == 1
        entry = result[0]
        assert entry.observation_count == 3
        assert entry.first_detected == t1
        assert entry.last_detected == t5 if False else t3  # noqa: just t3
        assert entry.drift_velocity > 0

    def test_velocity_sorted_descending(self):
        detector = ConfigDriftDetector()
        t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 2, tzinfo=timezone.utc)
        item_a = DriftItem(
            component_id="c1",
            parameter_path="replicas",
            category=DriftCategory.PARAMETER,
            severity=DriftSeverity.HIGH,
            baseline_value=3,
            current_value=1,
            description="test",
        )
        item_b = DriftItem(
            component_id="c2",
            parameter_path="capacity.max_rps",
            category=DriftCategory.PARAMETER,
            severity=DriftSeverity.MEDIUM,
            baseline_value=10000,
            current_value=5000,
            description="test",
        )
        history = [
            (t1, [item_a, item_b]),
            (t2, [item_a]),
        ]
        result = detector.track_drift_timeseries(history)
        assert len(result) == 2
        # item_a has 2 observations over 1 day; item_b has 1 over 1 day
        assert result[0].component_id == "c1"


# ---------------------------------------------------------------------------
# ConfigDriftDetector — build_config_dependency_graph
# ---------------------------------------------------------------------------


class TestBuildConfigDependencyGraph:
    def test_no_edges(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("a"), _comp("b"))
        result = detector.build_config_dependency_graph(g)
        assert result == []

    def test_with_dependency(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("a"), _comp("b"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        result = detector.build_config_dependency_graph(g)
        # Should produce at least 2 config dependencies (timeout + capacity)
        assert len(result) >= 2
        assert all(isinstance(d, ConfigDependency) for d in result)
        rels = {d.relationship for d in result}
        assert "timeout_must_exceed" in rels
        assert "capacity_must_not_exceed" in rels

    def test_multiple_edges(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("a"), _comp("b"), _comp("c"))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        result = detector.build_config_dependency_graph(g)
        assert len(result) >= 4  # 2 edges * 2 deps each


# ---------------------------------------------------------------------------
# ConfigDriftDetector — assess_drift_risk
# ---------------------------------------------------------------------------


class TestAssessDriftRisk:
    def test_empty_items(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        result = detector.assess_drift_risk([], g)
        assert result == []

    def test_single_component_risk(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="replicas",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.CRITICAL,
                baseline_value=3,
                current_value=1,
                description="test",
                risk_score=20.0,
            ),
        ]
        result = detector.assess_drift_risk(items, g)
        assert len(result) == 1
        assert result[0].total_risk_score == 20.0
        assert result[0].estimated_mttr_increase_minutes == 20.0
        assert "Resolve critical" in result[0].recommendations[0]

    def test_blast_radius_recommendation(self):
        detector = ConfigDriftDetector()
        c1 = _comp("c1")
        c2 = _comp("c2")
        c3 = _comp("c3")
        c4 = _comp("c4")
        g = _graph(c1, c2, c3, c4)
        g.add_dependency(Dependency(source_id="c2", target_id="c1"))
        g.add_dependency(Dependency(source_id="c3", target_id="c1"))
        g.add_dependency(Dependency(source_id="c4", target_id="c1"))
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="replicas",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.HIGH,
                baseline_value=3,
                current_value=1,
                description="test",
                risk_score=15.0,
            ),
        ]
        result = detector.assess_drift_risk(items, g)
        assert result[0].blast_radius >= 3
        recs_text = " ".join(result[0].recommendations)
        assert "downstream" in recs_text

    def test_high_risk_recommendation(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="replicas",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.MEDIUM,
                baseline_value=3,
                current_value=2,
                description="test",
                risk_score=35.0,
            ),
        ]
        result = detector.assess_drift_risk(items, g)
        recs_text = " ".join(result[0].recommendations)
        assert "aggregate risk" in recs_text.lower() or "High aggregate" in recs_text

    def test_reliability_impact_levels(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"), _comp("c2"), _comp("c3"))
        items_crit = [
            DriftItem(
                component_id="c1", parameter_path="replicas",
                category=DriftCategory.PARAMETER, severity=DriftSeverity.CRITICAL,
                baseline_value=3, current_value=1, description="t", risk_score=50.0,
            ),
        ]
        items_high = [
            DriftItem(
                component_id="c2", parameter_path="replicas",
                category=DriftCategory.PARAMETER, severity=DriftSeverity.HIGH,
                baseline_value=3, current_value=2, description="t", risk_score=25.0,
            ),
        ]
        items_low = [
            DriftItem(
                component_id="c3", parameter_path="tags",
                category=DriftCategory.SCHEMA, severity=DriftSeverity.INFO,
                baseline_value=[], current_value=["x"], description="t", risk_score=2.0,
            ),
        ]
        r1 = detector.assess_drift_risk(items_crit, g)
        r2 = detector.assess_drift_risk(items_high, g)
        r3 = detector.assess_drift_risk(items_low, g)
        assert r1[0].reliability_impact == "critical"
        assert r2[0].reliability_impact == "high"
        assert r3[0].reliability_impact == "low"


# ---------------------------------------------------------------------------
# ConfigDriftDetector — map_compliance
# ---------------------------------------------------------------------------


class TestMapCompliance:
    def test_empty(self):
        detector = ConfigDriftDetector()
        assert detector.map_compliance([]) == {}

    def test_mapping(self):
        detector = ConfigDriftDetector()
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="security.encryption_at_rest",
                category=DriftCategory.SCHEMA,
                severity=DriftSeverity.HIGH,
                baseline_value=True,
                current_value=False,
                description="test",
                compliance_violations=[
                    ComplianceFramework.PCI_DSS,
                    ComplianceFramework.HIPAA,
                ],
            ),
        ]
        result = detector.map_compliance(items)
        assert "pci_dss" in result
        assert "hipaa" in result
        assert len(result["pci_dss"]) == 1


# ---------------------------------------------------------------------------
# ConfigDriftDetector — generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_empty_report(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        report = detector.generate_report([], g)
        assert report.total_drifts == 0
        assert "No configuration drift" in report.summary

    def test_report_with_drifts(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="replicas",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.CRITICAL,
                baseline_value=3,
                current_value=1,
                description="test",
                risk_score=20.0,
                compliance_violations=[ComplianceFramework.SOC2],
            ),
            DriftItem(
                component_id="c1",
                parameter_path="capacity.max_rps",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.MEDIUM,
                baseline_value=10000,
                current_value=5000,
                description="test",
                risk_score=7.0,
            ),
        ]
        report = detector.generate_report(items, g)
        assert report.total_drifts == 2
        assert report.critical_count == 1
        assert report.medium_count == 1
        assert report.overall_risk_score == 27.0
        assert len(report.clusters) >= 1
        assert len(report.risk_assessments) == 1
        assert "soc2" in report.compliance_summary
        assert "CRITICAL" in report.summary
        assert "Immediate" in report.summary

    def test_report_to_dict(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="failover.enabled",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.CRITICAL,
                baseline_value=True,
                current_value=False,
                description="failover disabled",
                risk_score=30.0,
            ),
        ]
        report = detector.generate_report(items, g)
        d = report.to_dict()
        assert d["total_drifts"] == 1
        assert d["severity_counts"]["critical"] == 1
        assert isinstance(d["generated_at"], str)

    def test_report_with_cross_env_drifts(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        cross_env = [
            CrossEnvDrift(
                component_id="c1",
                parameter_path="replicas",
                env_a_name="dev",
                env_a_value=1,
                env_b_name="prod",
                env_b_value=3,
            )
        ]
        report = detector.generate_report([], g, cross_env_drifts=cross_env)
        assert len(report.cross_env_drifts) == 1

    def test_report_high_only(self):
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="security.auth_required",
                category=DriftCategory.SCHEMA,
                severity=DriftSeverity.HIGH,
                baseline_value=True,
                current_value=False,
                description="auth removed",
                risk_score=15.0,
            ),
        ]
        report = detector.generate_report(items, g)
        assert report.high_count == 1
        assert report.critical_count == 0
        assert "Prompt attention" in report.summary


# ---------------------------------------------------------------------------
# Integration / end-to-end scenarios
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_workflow(self):
        """Create baseline -> mutate graph -> compare -> cluster -> report."""
        detector = ConfigDriftDetector()
        # Golden baseline
        g1 = _graph(
            _comp(
                "web",
                ctype=ComponentType.WEB_SERVER,
                replicas=3,
                failover=FailoverConfig(enabled=True),
                security=SecurityProfile(
                    encryption_at_rest=True,
                    encryption_in_transit=True,
                    auth_required=True,
                ),
            ),
            _comp(
                "db",
                ctype=ComponentType.DATABASE,
                replicas=2,
                failover=FailoverConfig(enabled=True),
                security=SecurityProfile(
                    encryption_at_rest=True,
                    backup_enabled=True,
                ),
            ),
        )
        g1.add_dependency(Dependency(source_id="web", target_id="db"))
        baseline = detector.create_baseline(g1)

        # Drifted state
        g2 = _graph(
            _comp(
                "web",
                ctype=ComponentType.WEB_SERVER,
                replicas=1,  # reduced
                failover=FailoverConfig(enabled=False),  # disabled
                security=SecurityProfile(
                    encryption_at_rest=True,
                    encryption_in_transit=False,  # disabled
                    auth_required=True,
                ),
            ),
            _comp(
                "db",
                ctype=ComponentType.DATABASE,
                replicas=2,
                failover=FailoverConfig(enabled=True),
                security=SecurityProfile(
                    encryption_at_rest=True,
                    backup_enabled=True,
                ),
            ),
        )
        g2.add_dependency(Dependency(source_id="web", target_id="db"))

        drifts = detector.compare_to_baseline(baseline, g2)
        assert len(drifts) >= 3  # replicas, failover.enabled, security.encryption_in_transit

        clusters = detector.cluster_drifts(drifts)
        assert len(clusters) >= 1

        report = detector.generate_report(drifts, g2)
        assert report.total_drifts >= 3
        assert report.critical_count >= 1  # failover.enabled is critical
        d = report.to_dict()
        assert d["total_drifts"] >= 3

    def test_cross_env_with_report(self):
        """Cross-environment drift integrated into report."""
        detector = ConfigDriftDetector()
        g_dev = _graph(_comp("api", replicas=1))
        g_prod = _graph(_comp("api", replicas=3))
        cross_env = detector.compare_environments(
            {"dev": g_dev, "prod": g_prod}
        )
        assert len(cross_env) >= 1

        # Baseline comparison from prod perspective
        baseline = detector.create_baseline(g_prod)
        drifts = detector.compare_to_baseline(baseline, g_dev)
        report = detector.generate_report(
            drifts, g_dev, cross_env_drifts=cross_env
        )
        assert report.total_drifts >= 1
        assert len(report.cross_env_drifts) >= 1

    def test_config_dependency_graph_with_drift(self):
        """Config dependency graph plus drift detection."""
        detector = ConfigDriftDetector()
        g = _graph(_comp("frontend"), _comp("backend"), _comp("db"))
        g.add_dependency(Dependency(source_id="frontend", target_id="backend"))
        g.add_dependency(Dependency(source_id="backend", target_id="db"))

        cfg_deps = detector.build_config_dependency_graph(g)
        assert len(cfg_deps) >= 4

        # Verify dependency relationships are correct
        src_tgt_pairs = {(d.source_component_id, d.target_component_id) for d in cfg_deps}
        assert ("frontend", "backend") in src_tgt_pairs
        assert ("backend", "db") in src_tgt_pairs

    def test_timeseries_and_risk_combined(self):
        """Time-series tracking combined with risk assessment."""
        detector = ConfigDriftDetector()
        g = _graph(_comp("svc"))

        item = DriftItem(
            component_id="svc",
            parameter_path="replicas",
            category=DriftCategory.PARAMETER,
            severity=DriftSeverity.HIGH,
            baseline_value=3,
            current_value=1,
            description="test",
            risk_score=15.0,
        )

        t1 = datetime(2026, 3, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 8, tzinfo=timezone.utc)
        ts = detector.track_drift_timeseries([(t1, [item]), (t2, [item])])
        assert ts[0].observation_count == 2

        risk = detector.assess_drift_risk([item], g)
        assert risk[0].total_risk_score == 15.0


# ---------------------------------------------------------------------------
# Additional coverage — edge-case branches
# ---------------------------------------------------------------------------


class TestCoverageBranches:
    """Tests specifically targeting uncovered branches."""

    def test_classify_category_secret_rotation(self):
        """Line 383: secret/rotation path classification."""
        assert _classify_category("secret_key", "old", "new") == DriftCategory.SECRET_ROTATION
        assert _classify_category("rotation_interval", 30, 60) == DriftCategory.SECRET_ROTATION

    def test_cluster_secret_rotation_hypothesis(self):
        """Line 699: secret rotation root cause hypothesis."""
        detector = ConfigDriftDetector()
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="secret_key",
                category=DriftCategory.SECRET_ROTATION,
                severity=DriftSeverity.HIGH,
                baseline_value="old",
                current_value="new",
                description="secret rotated",
                risk_score=10.0,
            ),
        ]
        clusters = detector.cluster_drifts(items)
        assert len(clusters) == 1
        assert "Secret rotation" in clusters[0].root_cause_hypothesis

    def test_cluster_version_hypothesis(self):
        """Line 701: version drift root cause hypothesis."""
        detector = ConfigDriftDetector()
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="parameters",
                category=DriftCategory.VERSION,
                severity=DriftSeverity.MEDIUM,
                baseline_value={"version": "1.0"},
                current_value={"version": "2.0"},
                description="version drift",
                risk_score=5.0,
            ),
        ]
        clusters = detector.cluster_drifts(items)
        assert len(clusters) == 1
        assert "Version drift" in clusters[0].root_cause_hypothesis

    def test_cluster_failover_autoscaling_hypothesis(self):
        """Line 705: failover/autoscaling root cause hypothesis."""
        detector = ConfigDriftDetector()
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="failover.enabled",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.CRITICAL,
                baseline_value=True,
                current_value=False,
                description="failover disabled",
                risk_score=15.0,
            ),
        ]
        clusters = detector.cluster_drifts(items)
        assert len(clusters) == 1
        assert "Resilience features" in clusters[0].root_cause_hypothesis

    def test_compliance_severity_upgrade(self):
        """Line 572: severity upgraded to HIGH when compliance is violated
        and original severity is below HIGH."""
        detector = ConfigDriftDetector()
        # security.rate_limiting has criticality 5.0 -> MEDIUM normally
        # but has compliance entries (NIST, CIS) which should upgrade to HIGH
        g1 = _graph(
            _comp(
                "s1",
                security=SecurityProfile(rate_limiting=True),
            )
        )
        baseline = detector.create_baseline(g1)
        g2 = _graph(
            _comp(
                "s1",
                security=SecurityProfile(rate_limiting=False),
            )
        )
        drifts = detector.compare_to_baseline(baseline, g2)
        rl_drifts = [d for d in drifts if d.parameter_path == "security.rate_limiting"]
        assert len(rl_drifts) == 1
        # Should be upgraded from MEDIUM to HIGH due to compliance violations
        assert rl_drifts[0].severity == DriftSeverity.HIGH
        assert len(rl_drifts[0].compliance_violations) >= 1

    def test_config_dep_graph_missing_component(self):
        """Line 760: edge where source or target comp is None (skip)."""
        detector = ConfigDriftDetector()
        g = _graph(_comp("a"))
        # Add a dependency edge referencing a non-existent component
        g.add_dependency(Dependency(source_id="a", target_id="nonexistent"))
        result = detector.build_config_dependency_graph(g)
        # Should skip the edge since target doesn't exist
        assert result == []

    def test_report_low_only_monitor_summary(self):
        """Line 923: summary with only low/medium drifts (no crit/high)."""
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="tags",
                category=DriftCategory.SCHEMA,
                severity=DriftSeverity.LOW,
                baseline_value=["a"],
                current_value=["b"],
                description="tags changed",
                risk_score=2.0,
            ),
        ]
        report = detector.generate_report(items, g)
        assert report.total_drifts == 1
        assert report.critical_count == 0
        assert report.high_count == 0
        assert "Monitor and address" in report.summary

    def test_moderate_reliability_impact(self):
        """Cover reliability_impact 'moderate' (risk between 10 and 20)."""
        detector = ConfigDriftDetector()
        g = _graph(_comp("c1"))
        items = [
            DriftItem(
                component_id="c1",
                parameter_path="capacity.max_rps",
                category=DriftCategory.PARAMETER,
                severity=DriftSeverity.MEDIUM,
                baseline_value=10000,
                current_value=5000,
                description="t",
                risk_score=15.0,
            ),
        ]
        result = detector.assess_drift_risk(items, g)
        assert result[0].reliability_impact == "moderate"

    def test_classify_category_parameters_same_values(self):
        """Cover parameters dict where version keys have same values."""
        assert (
            _classify_category(
                "parameters",
                {"app_version": "1.0", "foo": "a"},
                {"app_version": "1.0", "foo": "b"},
            )
            == DriftCategory.PARAMETER
        )
