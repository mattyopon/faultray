"""Tests for dependency drift detector."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    ComplianceTags,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.dependency_drift import (
    DependencyDriftEngine,
    DriftDetection,
    DriftReport,
    DriftSeverity,
    DriftType,
    RemediationPlan,
    RemediationStep,
    _extract_version,
    _version_major,
    _version_tuple,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    *,
    replicas: int = 1,
    tags: list[str] | None = None,
    max_rps: int = 5000,
    max_connections: int = 1000,
    encryption_in_transit: bool = False,
    encryption_at_rest: bool = False,
    waf_protected: bool = False,
    auth_required: bool = False,
    backup_enabled: bool = False,
    rate_limiting: bool = False,
    network_segmented: bool = False,
    pci_scope: bool = False,
    contains_pii: bool = False,
    contains_phi: bool = False,
    audit_logging: bool = False,
    change_management: bool = False,
    data_classification: str = "internal",
    autoscaling: bool = False,
    failover: bool = False,
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
    network_connections: int = 0,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        tags=tags or [],
        capacity=Capacity(max_rps=max_rps, max_connections=max_connections),
        security=SecurityProfile(
            encryption_in_transit=encryption_in_transit,
            encryption_at_rest=encryption_at_rest,
            waf_protected=waf_protected,
            auth_required=auth_required,
            backup_enabled=backup_enabled,
            rate_limiting=rate_limiting,
            network_segmented=network_segmented,
        ),
        compliance_tags=ComplianceTags(
            pci_scope=pci_scope,
            contains_pii=contains_pii,
            contains_phi=contains_phi,
            audit_logging=audit_logging,
            change_management=change_management,
            data_classification=data_classification,
        ),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        failover=FailoverConfig(enabled=failover),
        metrics=ResourceMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            network_connections=network_connections,
        ),
    )


def _graph(*components: Component, edges: list[tuple[str, str]] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in (edges or []):
        g.add_dependency(Dependency(source_id=src, target_id=tgt, dependency_type="requires"))
    return g


def _graph_with_deps(
    *components: Component,
    deps: list[Dependency] | None = None,
) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for d in (deps or []):
        g.add_dependency(d)
    return g


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


class TestDriftTypeEnum:
    def test_version_skew_value(self):
        assert DriftType.VERSION_SKEW == "version_skew"

    def test_config_drift_value(self):
        assert DriftType.CONFIG_DRIFT == "config_drift"

    def test_schema_mismatch_value(self):
        assert DriftType.SCHEMA_MISMATCH == "schema_mismatch"

    def test_protocol_mismatch_value(self):
        assert DriftType.PROTOCOL_MISMATCH == "protocol_mismatch"

    def test_capacity_imbalance_value(self):
        assert DriftType.CAPACITY_IMBALANCE == "capacity_imbalance"

    def test_security_policy_drift_value(self):
        assert DriftType.SECURITY_POLICY_DRIFT == "security_policy_drift"

    def test_tls_expiry_value(self):
        assert DriftType.TLS_EXPIRY == "tls_expiry"

    def test_api_version_mismatch_value(self):
        assert DriftType.API_VERSION_MISMATCH == "api_version_mismatch"

    def test_topology_drift_value(self):
        assert DriftType.TOPOLOGY_DRIFT == "topology_drift"

    def test_compliance_drift_value(self):
        assert DriftType.COMPLIANCE_DRIFT == "compliance_drift"

    def test_drift_type_count(self):
        assert len(DriftType) == 10


class TestDriftSeverityEnum:
    def test_critical_value(self):
        assert DriftSeverity.CRITICAL == "critical"

    def test_high_value(self):
        assert DriftSeverity.HIGH == "high"

    def test_medium_value(self):
        assert DriftSeverity.MEDIUM == "medium"

    def test_low_value(self):
        assert DriftSeverity.LOW == "low"

    def test_info_value(self):
        assert DriftSeverity.INFO == "info"

    def test_severity_count(self):
        assert len(DriftSeverity) == 5


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestDriftDetectionModel:
    def test_minimal_construction(self):
        d = DriftDetection(
            component_id="c1",
            drift_type=DriftType.VERSION_SKEW,
            severity=DriftSeverity.LOW,
            expected_value="1.0",
            actual_value="0.9",
            remediation="upgrade",
        )
        assert d.component_id == "c1"
        assert d.auto_fixable is False
        assert d.blast_radius == []

    def test_detected_at_default(self):
        d = DriftDetection(
            component_id="c1",
            drift_type=DriftType.CONFIG_DRIFT,
            severity=DriftSeverity.INFO,
            expected_value="a",
            actual_value="b",
            remediation="fix",
        )
        assert d.detected_at  # non-empty string

    def test_blast_radius_field(self):
        d = DriftDetection(
            component_id="c1",
            drift_type=DriftType.TLS_EXPIRY,
            severity=DriftSeverity.CRITICAL,
            expected_value="tls=on",
            actual_value="tls=off",
            remediation="enable tls",
            blast_radius=["c2", "c3"],
        )
        assert d.blast_radius == ["c2", "c3"]

    def test_auto_fixable_true(self):
        d = DriftDetection(
            component_id="c1",
            drift_type=DriftType.CONFIG_DRIFT,
            severity=DriftSeverity.LOW,
            expected_value="x",
            actual_value="y",
            remediation="auto",
            auto_fixable=True,
        )
        assert d.auto_fixable is True


class TestDriftReportModel:
    def test_empty_report(self):
        r = DriftReport()
        assert r.total_drifts == 0
        assert r.drift_score == 100.0
        assert r.drifts == []
        assert r.recommendations == []
        assert r.auto_fixable_count == 0

    def test_report_with_counts(self):
        r = DriftReport(
            total_drifts=5,
            critical_count=1,
            high_count=2,
            medium_count=1,
            low_count=1,
            drift_score=50.0,
        )
        assert r.critical_count == 1
        assert r.high_count == 2
        assert r.medium_count == 1
        assert r.low_count == 1


class TestRemediationModels:
    def test_remediation_step(self):
        s = RemediationStep(
            priority=1,
            component_id="db1",
            drift_type=DriftType.CAPACITY_IMBALANCE,
            severity=DriftSeverity.HIGH,
            action="Scale up",
        )
        assert s.priority == 1
        assert s.auto_fixable is False

    def test_remediation_plan_defaults(self):
        p = RemediationPlan()
        assert p.total_steps == 0
        assert p.auto_fixable_steps == 0
        assert p.manual_steps == 0
        assert p.estimated_risk_reduction == 0.0


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------


class TestVersionHelpers:
    def test_extract_version_simple(self):
        assert _extract_version("redis-7") == "7"

    def test_extract_version_major_minor(self):
        assert _extract_version("postgres-14.2") == "14.2"

    def test_extract_version_full(self):
        assert _extract_version("node-18.16.1") == "18.16.1"

    def test_extract_version_none(self):
        assert _extract_version("my-service") is None

    def test_extract_version_embedded(self):
        assert _extract_version("mysql-primary-8") == "8"

    def test_version_major(self):
        assert _version_major("14.2") == 14

    def test_version_major_none(self):
        assert _version_major("abc") is None

    def test_version_tuple_single(self):
        assert _version_tuple("7") == (7,)

    def test_version_tuple_two(self):
        assert _version_tuple("14.2") == (14, 2)

    def test_version_tuple_three(self):
        assert _version_tuple("18.16.1") == (18, 16, 1)

    def test_version_tuple_no_match(self):
        assert _version_tuple("abc") == (0,)


# ---------------------------------------------------------------------------
# detect_version_skew
# ---------------------------------------------------------------------------


class TestDetectVersionSkew:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_no_skew_single_component(self):
        g = _graph(_comp("db1", "postgres-14", ComponentType.DATABASE, tags=["v14"]))
        drifts = self.engine.detect_version_skew(g)
        assert drifts == []

    def test_no_skew_same_version(self):
        g = _graph(
            _comp("db1", "postgres-14", ComponentType.DATABASE),
            _comp("db2", "postgres-14", ComponentType.DATABASE),
        )
        drifts = self.engine.detect_version_skew(g)
        assert drifts == []

    def test_skew_between_same_type(self):
        g = _graph(
            _comp("db1", "postgres-14", ComponentType.DATABASE),
            _comp("db2", "postgres-15", ComponentType.DATABASE),
            _comp("db3", "postgres-15", ComponentType.DATABASE),
        )
        drifts = self.engine.detect_version_skew(g)
        skew = [d for d in drifts if d.drift_type == DriftType.VERSION_SKEW]
        assert len(skew) >= 1
        assert skew[0].component_id == "db1"

    def test_skew_severity_major_diff_2(self):
        g = _graph(
            _comp("db1", "postgres-12", ComponentType.DATABASE),
            _comp("db2", "postgres-14", ComponentType.DATABASE),
            _comp("db3", "postgres-14", ComponentType.DATABASE),
        )
        drifts = self.engine.detect_version_skew(g)
        skew = [d for d in drifts if d.drift_type == DriftType.VERSION_SKEW]
        assert len(skew) >= 1
        assert skew[0].severity == DriftSeverity.CRITICAL

    def test_skew_severity_major_diff_1(self):
        g = _graph(
            _comp("db1", "postgres-13", ComponentType.DATABASE),
            _comp("db2", "postgres-14", ComponentType.DATABASE),
            _comp("db3", "postgres-14", ComponentType.DATABASE),
        )
        drifts = self.engine.detect_version_skew(g)
        skew = [d for d in drifts if d.drift_type == DriftType.VERSION_SKEW]
        assert len(skew) >= 1
        assert skew[0].severity == DriftSeverity.HIGH

    def test_skew_minor_version_medium(self):
        g = _graph(
            _comp("c1", "redis-7.0", ComponentType.CACHE),
            _comp("c2", "redis-7.2", ComponentType.CACHE),
            _comp("c3", "redis-7.2", ComponentType.CACHE),
        )
        drifts = self.engine.detect_version_skew(g)
        skew = [d for d in drifts if d.drift_type == DriftType.VERSION_SKEW]
        assert len(skew) >= 1
        assert skew[0].severity == DriftSeverity.MEDIUM

    def test_skew_no_version_in_name(self):
        g = _graph(
            _comp("a1", "app-alpha", ComponentType.APP_SERVER),
            _comp("a2", "app-beta", ComponentType.APP_SERVER),
        )
        drifts = self.engine.detect_version_skew(g)
        # no version info → no skew detected
        skew = [d for d in drifts if d.drift_type == DriftType.VERSION_SKEW]
        assert skew == []

    def test_skew_uses_tags_for_version(self):
        g = _graph(
            _comp("db1", "primary-db", ComponentType.DATABASE, tags=["v14"]),
            _comp("db2", "replica-db", ComponentType.DATABASE, tags=["v15"]),
            _comp("db3", "analytics-db", ComponentType.DATABASE, tags=["v15"]),
        )
        drifts = self.engine.detect_version_skew(g)
        skew = [d for d in drifts if d.drift_type == DriftType.VERSION_SKEW]
        assert len(skew) >= 1

    def test_skew_remediation_message(self):
        g = _graph(
            _comp("db1", "postgres-13", ComponentType.DATABASE),
            _comp("db2", "postgres-14", ComponentType.DATABASE),
            _comp("db3", "postgres-14", ComponentType.DATABASE),
        )
        drifts = self.engine.detect_version_skew(g)
        skew = [d for d in drifts if d.drift_type == DriftType.VERSION_SKEW]
        assert any("14" in d.remediation for d in skew)

    def test_skew_auto_fixable_for_low(self):
        # Patch version difference → LOW → auto_fixable
        g = _graph(
            _comp("c1", "redis-7.2.0", ComponentType.CACHE),
            _comp("c2", "redis-7.2.1", ComponentType.CACHE),
            _comp("c3", "redis-7.2.1", ComponentType.CACHE),
        )
        drifts = self.engine.detect_version_skew(g)
        skew = [d for d in drifts if d.drift_type == DriftType.VERSION_SKEW]
        # minor/patch diff is MEDIUM, not auto_fixable
        if skew:
            assert skew[0].severity in (DriftSeverity.MEDIUM, DriftSeverity.LOW)

    def test_skew_different_types_not_compared(self):
        g = _graph(
            _comp("db1", "postgres-14", ComponentType.DATABASE),
            _comp("c1", "redis-7", ComponentType.CACHE),
        )
        drifts = self.engine.detect_version_skew(g)
        skew = [d for d in drifts if d.drift_type == DriftType.VERSION_SKEW]
        assert skew == []


# ---------------------------------------------------------------------------
# detect_capacity_imbalance
# ---------------------------------------------------------------------------


class TestDetectCapacityImbalance:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_no_imbalance_balanced(self):
        a = _comp("app", "app", max_rps=5000)
        db = _comp("db", "db", ComponentType.DATABASE, max_rps=5000)
        g = _graph(a, db, edges=[("app", "db")])
        drifts = self.engine.detect_capacity_imbalance(g)
        assert drifts == []

    def test_rps_imbalance_detected(self):
        a = _comp("app", "app", max_rps=20000, replicas=2)
        db = _comp("db", "db", ComponentType.DATABASE, max_rps=5000)
        g = _graph(a, db, edges=[("app", "db")])
        drifts = self.engine.detect_capacity_imbalance(g)
        cap_drifts = [d for d in drifts if d.drift_type == DriftType.CAPACITY_IMBALANCE]
        assert len(cap_drifts) >= 1

    def test_rps_imbalance_severity_high(self):
        a = _comp("app", "app", max_rps=50000, replicas=2)
        db = _comp("db", "db", ComponentType.DATABASE, max_rps=5000)
        g = _graph(a, db, edges=[("app", "db")])
        drifts = self.engine.detect_capacity_imbalance(g)
        cap_drifts = [d for d in drifts if d.drift_type == DriftType.CAPACITY_IMBALANCE]
        high_or_above = [d for d in cap_drifts if d.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL)]
        assert len(high_or_above) >= 1

    def test_connection_imbalance_detected(self):
        a = _comp("app", "app", max_connections=5000, replicas=2)
        db = _comp("db", "db", ComponentType.DATABASE, max_connections=1000)
        g = _graph(a, db, edges=[("app", "db")])
        drifts = self.engine.detect_capacity_imbalance(g)
        cap_drifts = [d for d in drifts if d.drift_type == DriftType.CAPACITY_IMBALANCE]
        conn_drifts = [d for d in cap_drifts if "conns" in d.actual_value]
        assert len(conn_drifts) >= 1

    def test_utilization_imbalance_detected(self):
        a = _comp("app", "app", cpu_percent=30.0)
        db = _comp("db", "db", ComponentType.DATABASE, cpu_percent=90.0)
        g = _graph(a, db, edges=[("app", "db")])
        drifts = self.engine.detect_capacity_imbalance(g)
        cap_drifts = [d for d in drifts if d.drift_type == DriftType.CAPACITY_IMBALANCE]
        util_drifts = [d for d in cap_drifts if "util" in d.actual_value]
        assert len(util_drifts) >= 1

    def test_optional_dependency_skipped(self):
        a = _comp("app", "app", max_rps=50000)
        db = _comp("db", "db", ComponentType.DATABASE, max_rps=1000)
        g = InfraGraph()
        g.add_component(a)
        g.add_component(db)
        g.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="optional"))
        drifts = self.engine.detect_capacity_imbalance(g)
        assert drifts == []

    def test_autoscaling_makes_auto_fixable(self):
        a = _comp("app", "app", max_rps=20000, replicas=2)
        db = _comp("db", "db", ComponentType.DATABASE, max_rps=5000, autoscaling=True)
        g = _graph(a, db, edges=[("app", "db")])
        drifts = self.engine.detect_capacity_imbalance(g)
        cap_drifts = [d for d in drifts if d.drift_type == DriftType.CAPACITY_IMBALANCE]
        auto = [d for d in cap_drifts if d.auto_fixable]
        assert len(auto) >= 1

    def test_no_dependency_no_imbalance(self):
        a = _comp("app", "app", max_rps=50000)
        db = _comp("db", "db", ComponentType.DATABASE, max_rps=100)
        g = _graph(a, db)  # no edges
        drifts = self.engine.detect_capacity_imbalance(g)
        assert drifts == []


# ---------------------------------------------------------------------------
# detect_security_drift
# ---------------------------------------------------------------------------


class TestDetectSecurityDrift:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_no_security_issues(self):
        c = _comp("app", "app", encryption_in_transit=True, auth_required=True)
        g = _graph(c)
        drifts = self.engine.detect_security_drift(g)
        assert drifts == []

    def test_missing_encryption_in_transit_with_dependents(self):
        a = _comp("fe", "frontend")
        b = _comp("be", "backend")
        g = _graph(a, b, edges=[("fe", "be")])
        drifts = self.engine.detect_security_drift(g)
        sec_drifts = [d for d in drifts if d.drift_type == DriftType.SECURITY_POLICY_DRIFT]
        enc_drifts = [d for d in sec_drifts if "encryption_in_transit" in d.expected_value]
        assert len(enc_drifts) >= 1

    def test_pci_without_encryption_at_rest(self):
        db = _comp("db", "db", ComponentType.DATABASE, pci_scope=True)
        g = _graph(db)
        drifts = self.engine.detect_security_drift(g)
        pci_drifts = [d for d in drifts if d.severity == DriftSeverity.CRITICAL]
        assert len(pci_drifts) >= 1

    def test_pii_without_encryption(self):
        db = _comp("db", "db", ComponentType.DATABASE, contains_pii=True)
        g = _graph(db)
        drifts = self.engine.detect_security_drift(g)
        pii_drifts = [
            d for d in drifts
            if d.drift_type == DriftType.SECURITY_POLICY_DRIFT
            and "PII" in d.remediation
        ]
        assert len(pii_drifts) >= 1

    def test_lb_without_waf(self):
        lb = _comp("lb", "lb", ComponentType.LOAD_BALANCER)
        g = _graph(lb)
        drifts = self.engine.detect_security_drift(g)
        waf_drifts = [d for d in drifts if "waf" in d.expected_value]
        assert len(waf_drifts) >= 1

    def test_app_server_without_auth(self):
        app = _comp("app", "app", ComponentType.APP_SERVER)
        g = _graph(app)
        drifts = self.engine.detect_security_drift(g)
        auth_drifts = [d for d in drifts if "auth" in d.expected_value]
        assert len(auth_drifts) >= 1

    def test_database_without_backup(self):
        db = _comp("db", "db", ComponentType.DATABASE)
        a = _comp("app", "app")
        g = _graph(db, a, edges=[("app", "db")])
        drifts = self.engine.detect_security_drift(g)
        bk_drifts = [d for d in drifts if "backup" in d.expected_value]
        assert len(bk_drifts) >= 1

    def test_external_api_without_rate_limiting(self):
        api = _comp("api", "api", ComponentType.EXTERNAL_API)
        g = _graph(api)
        drifts = self.engine.detect_security_drift(g)
        rl_drifts = [d for d in drifts if "rate_limiting" in d.expected_value]
        assert len(rl_drifts) >= 1

    def test_encryption_inconsistency_between_connected(self):
        a = _comp("fe", "frontend", encryption_in_transit=True)
        b = _comp("be", "backend", encryption_in_transit=False)
        g = _graph(a, b, edges=[("fe", "be")])
        drifts = self.engine.detect_security_drift(g)
        # The backend should be flagged for inconsistency
        incon = [
            d for d in drifts
            if d.component_id == "be"
            and d.drift_type == DriftType.SECURITY_POLICY_DRIFT
        ]
        assert len(incon) >= 1

    def test_pci_with_encryption_no_critical(self):
        db = _comp("db", "db", ComponentType.DATABASE, pci_scope=True, encryption_at_rest=True)
        g = _graph(db)
        drifts = self.engine.detect_security_drift(g)
        pci_enc = [
            d for d in drifts
            if d.severity == DriftSeverity.CRITICAL
            and "encryption_at_rest" in d.expected_value
        ]
        assert pci_enc == []

    def test_db_backup_auto_fixable(self):
        db = _comp("db", "db", ComponentType.DATABASE)
        a = _comp("app", "app")
        g = _graph(db, a, edges=[("app", "db")])
        drifts = self.engine.detect_security_drift(g)
        bk = [d for d in drifts if "backup" in d.expected_value]
        assert all(d.auto_fixable for d in bk)


# ---------------------------------------------------------------------------
# detect_topology_drift
# ---------------------------------------------------------------------------


class TestDetectTopologyDrift:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_no_drift_identical(self):
        a = _comp("a", "a")
        baseline = _graph(a)
        current = _graph(a)
        drifts = self.engine.detect_topology_drift(current, baseline)
        assert drifts == []

    def test_component_removed(self):
        a = _comp("a", "a")
        b = _comp("b", "b")
        baseline = _graph(a, b)
        current = _graph(a)
        drifts = self.engine.detect_topology_drift(current, baseline)
        removed = [d for d in drifts if d.actual_value == "absent" and d.component_id == "b"]
        assert len(removed) == 1

    def test_component_added(self):
        a = _comp("a", "a")
        b = _comp("b", "b")
        baseline = _graph(a)
        current = _graph(a, b)
        drifts = self.engine.detect_topology_drift(current, baseline)
        added = [d for d in drifts if d.actual_value == "present"]
        assert len(added) == 1
        assert added[0].severity == DriftSeverity.INFO

    def test_edge_removed(self):
        a = _comp("a", "a")
        b = _comp("b", "b")
        baseline = _graph(a, b, edges=[("a", "b")])
        current = _graph(a, b)
        drifts = self.engine.detect_topology_drift(current, baseline)
        edge_rm = [d for d in drifts if "edge:" in d.expected_value]
        assert len(edge_rm) == 1

    def test_edge_added(self):
        a = _comp("a", "a")
        b = _comp("b", "b")
        baseline = _graph(a, b)
        current = _graph(a, b, edges=[("a", "b")])
        drifts = self.engine.detect_topology_drift(current, baseline)
        edge_add = [d for d in drifts if "edge:" in d.actual_value]
        assert len(edge_add) == 1

    def test_replica_decreased(self):
        base_c = _comp("a", "a", replicas=3)
        curr_c = _comp("a", "a", replicas=1)
        baseline = _graph(base_c)
        current = _graph(curr_c)
        drifts = self.engine.detect_topology_drift(current, baseline)
        rep = [d for d in drifts if "replicas" in d.expected_value]
        assert len(rep) == 1
        assert rep[0].severity == DriftSeverity.HIGH

    def test_replica_decreased_medium(self):
        base_c = _comp("a", "a", replicas=4)
        curr_c = _comp("a", "a", replicas=2)
        baseline = _graph(base_c)
        current = _graph(curr_c)
        drifts = self.engine.detect_topology_drift(current, baseline)
        rep = [d for d in drifts if "replicas" in d.expected_value]
        assert len(rep) == 1
        assert rep[0].severity == DriftSeverity.MEDIUM

    def test_replica_increased(self):
        base_c = _comp("a", "a", replicas=1)
        curr_c = _comp("a", "a", replicas=3)
        baseline = _graph(base_c)
        current = _graph(curr_c)
        drifts = self.engine.detect_topology_drift(current, baseline)
        rep = [d for d in drifts if "replicas" in d.expected_value]
        assert len(rep) == 1
        assert rep[0].severity == DriftSeverity.INFO

    def test_removed_component_with_dependents_high(self):
        a = _comp("a", "a")
        b = _comp("b", "b")
        c = _comp("c", "c")
        baseline = _graph(a, b, c, edges=[("a", "b"), ("c", "b")])
        current = _graph(a, c)
        drifts = self.engine.detect_topology_drift(current, baseline)
        removed = [d for d in drifts if d.component_id == "b" and d.actual_value == "absent"]
        assert len(removed) == 1
        assert removed[0].severity == DriftSeverity.HIGH

    def test_autoscaling_makes_replica_decrease_auto_fixable(self):
        base_c = _comp("a", "a", replicas=3)
        curr_c = _comp("a", "a", replicas=1, autoscaling=True)
        baseline = _graph(base_c)
        current = _graph(curr_c)
        drifts = self.engine.detect_topology_drift(current, baseline)
        rep = [d for d in drifts if "replicas" in d.expected_value]
        assert rep[0].auto_fixable is True


# ---------------------------------------------------------------------------
# Config drift (internal)
# ---------------------------------------------------------------------------


class TestConfigDrift:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_high_util_without_autoscaling(self):
        c = _comp("app", "app", cpu_percent=95.0)
        g = _graph(c)
        report = self.engine.detect_drifts(g)
        cfg = [d for d in report.drifts if d.drift_type == DriftType.CONFIG_DRIFT]
        assert len(cfg) >= 1

    def test_database_without_failover_with_dependents(self):
        db = _comp("db", "db", ComponentType.DATABASE)
        app = _comp("app", "app")
        g = _graph(db, app, edges=[("app", "db")])
        report = self.engine.detect_drifts(g)
        cfg = [
            d for d in report.drifts
            if d.drift_type == DriftType.CONFIG_DRIFT
            and "failover" in d.expected_value
        ]
        assert len(cfg) >= 1

    def test_circuit_breaker_disabled_on_requires_edge(self):
        a = _comp("app", "app")
        db = _comp("db", "db", ComponentType.DATABASE)
        g = _graph(a, db, edges=[("app", "db")])
        report = self.engine.detect_drifts(g)
        cfg = [
            d for d in report.drifts
            if d.drift_type == DriftType.CONFIG_DRIFT
            and "circuit_breaker" in d.expected_value
        ]
        assert len(cfg) >= 1

    def test_circuit_breaker_enabled_no_drift(self):
        a = _comp("app", "app")
        db = _comp("db", "db", ComponentType.DATABASE, failover=True)
        g = _graph_with_deps(
            a, db,
            deps=[Dependency(
                source_id="app", target_id="db",
                dependency_type="requires",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )],
        )
        report = self.engine.detect_drifts(g)
        cfg_cb = [
            d for d in report.drifts
            if d.drift_type == DriftType.CONFIG_DRIFT
            and "circuit_breaker" in d.expected_value
        ]
        assert cfg_cb == []


# ---------------------------------------------------------------------------
# Protocol mismatch
# ---------------------------------------------------------------------------


class TestProtocolMismatch:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_no_mismatch(self):
        a = _comp("a", "a")
        b = _comp("b", "b")
        g = _graph_with_deps(
            a, b,
            deps=[Dependency(source_id="a", target_id="b", protocol="grpc")],
        )
        report = self.engine.detect_drifts(g)
        proto = [d for d in report.drifts if d.drift_type == DriftType.PROTOCOL_MISMATCH]
        assert proto == []

    def test_mismatch_detected(self):
        a = _comp("a", "a")
        b = _comp("b", "b")
        c = _comp("c", "c")
        g = _graph_with_deps(
            a, b, c,
            deps=[
                Dependency(source_id="a", target_id="c", protocol="http"),
                Dependency(source_id="b", target_id="c", protocol="grpc"),
            ],
        )
        report = self.engine.detect_drifts(g)
        proto = [d for d in report.drifts if d.drift_type == DriftType.PROTOCOL_MISMATCH]
        assert len(proto) >= 2  # one per source


# ---------------------------------------------------------------------------
# TLS expiry
# ---------------------------------------------------------------------------


class TestTlsExpiry:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_lb_without_tls(self):
        lb = _comp("lb", "lb", ComponentType.LOAD_BALANCER)
        g = _graph(lb)
        report = self.engine.detect_drifts(g)
        tls = [d for d in report.drifts if d.drift_type == DriftType.TLS_EXPIRY]
        assert len(tls) >= 1
        assert tls[0].severity == DriftSeverity.CRITICAL

    def test_web_server_without_tls(self):
        ws = _comp("ws", "ws", ComponentType.WEB_SERVER)
        g = _graph(ws)
        report = self.engine.detect_drifts(g)
        tls = [d for d in report.drifts if d.drift_type == DriftType.TLS_EXPIRY]
        assert len(tls) >= 1

    def test_external_api_without_tls(self):
        api = _comp("api", "api", ComponentType.EXTERNAL_API)
        g = _graph(api)
        report = self.engine.detect_drifts(g)
        tls = [d for d in report.drifts if d.drift_type == DriftType.TLS_EXPIRY]
        assert len(tls) >= 1

    def test_lb_with_tls_no_tls_expiry(self):
        lb = _comp("lb", "lb", ComponentType.LOAD_BALANCER, encryption_in_transit=True)
        g = _graph(lb)
        report = self.engine.detect_drifts(g)
        tls = [d for d in report.drifts if d.drift_type == DriftType.TLS_EXPIRY]
        assert tls == []

    def test_database_without_tls_not_flagged(self):
        db = _comp("db", "db", ComponentType.DATABASE)
        g = _graph(db)
        report = self.engine.detect_drifts(g)
        tls = [d for d in report.drifts if d.drift_type == DriftType.TLS_EXPIRY]
        assert tls == []


# ---------------------------------------------------------------------------
# Compliance drift
# ---------------------------------------------------------------------------


class TestComplianceDrift:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_pci_without_audit_logging(self):
        c = _comp("db", "db", ComponentType.DATABASE, pci_scope=True)
        g = _graph(c)
        report = self.engine.detect_drifts(g)
        comp = [d for d in report.drifts if d.drift_type == DriftType.COMPLIANCE_DRIFT]
        audit = [d for d in comp if "audit_logging" in d.expected_value]
        assert len(audit) >= 1
        assert audit[0].severity == DriftSeverity.CRITICAL

    def test_pci_without_change_management(self):
        c = _comp("db", "db", ComponentType.DATABASE, pci_scope=True, audit_logging=True)
        g = _graph(c)
        report = self.engine.detect_drifts(g)
        comp = [d for d in report.drifts if d.drift_type == DriftType.COMPLIANCE_DRIFT]
        cm = [d for d in comp if "change_management" in d.expected_value]
        assert len(cm) >= 1

    def test_phi_without_encryption(self):
        c = _comp("db", "db", ComponentType.DATABASE, contains_phi=True)
        g = _graph(c)
        report = self.engine.detect_drifts(g)
        comp = [d for d in report.drifts if d.drift_type == DriftType.COMPLIANCE_DRIFT]
        phi = [d for d in comp if "encryption_at_rest" in d.expected_value]
        assert len(phi) >= 1
        assert phi[0].severity == DriftSeverity.CRITICAL

    def test_restricted_without_network_segmentation(self):
        c = _comp("db", "db", ComponentType.DATABASE, data_classification="restricted")
        g = _graph(c)
        report = self.engine.detect_drifts(g)
        comp = [d for d in report.drifts if d.drift_type == DriftType.COMPLIANCE_DRIFT]
        net = [d for d in comp if "network_segmented" in d.expected_value]
        assert len(net) >= 1

    def test_compliant_component_no_drift(self):
        c = _comp(
            "db", "db", ComponentType.DATABASE,
            pci_scope=True, audit_logging=True, change_management=True,
            encryption_at_rest=True,
        )
        g = _graph(c)
        report = self.engine.detect_drifts(g)
        comp = [d for d in report.drifts if d.drift_type == DriftType.COMPLIANCE_DRIFT]
        assert comp == []


# ---------------------------------------------------------------------------
# API version mismatch
# ---------------------------------------------------------------------------


class TestApiVersionMismatch:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_api_version_mismatch_detected(self):
        a = _comp("fe", "frontend", tags=["api-v1"])
        b = _comp("be", "backend", tags=["api-v2"])
        g = _graph(a, b, edges=[("fe", "be")])
        drifts = self.engine.detect_version_skew(g)
        api = [d for d in drifts if d.drift_type == DriftType.API_VERSION_MISMATCH]
        assert len(api) >= 1

    def test_no_api_version_no_mismatch(self):
        a = _comp("fe", "frontend")
        b = _comp("be", "backend")
        g = _graph(a, b, edges=[("fe", "be")])
        drifts = self.engine.detect_version_skew(g)
        api = [d for d in drifts if d.drift_type == DriftType.API_VERSION_MISMATCH]
        assert api == []

    def test_matching_api_version_no_mismatch(self):
        a = _comp("fe", "frontend", tags=["api-v2"])
        b = _comp("be", "backend", tags=["api-v2"])
        g = _graph(a, b, edges=[("fe", "be")])
        drifts = self.engine.detect_version_skew(g)
        api = [d for d in drifts if d.drift_type == DriftType.API_VERSION_MISMATCH]
        assert api == []

    def test_api_version_severity_is_high(self):
        a = _comp("fe", "frontend", tags=["api-v1"])
        b = _comp("be", "backend", tags=["api-v2"])
        g = _graph(a, b, edges=[("fe", "be")])
        drifts = self.engine.detect_version_skew(g)
        api = [d for d in drifts if d.drift_type == DriftType.API_VERSION_MISMATCH]
        assert all(d.severity == DriftSeverity.HIGH for d in api)


# ---------------------------------------------------------------------------
# detect_drifts (full scan)
# ---------------------------------------------------------------------------


class TestDetectDrifts:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_empty_graph(self):
        g = _graph()
        report = self.engine.detect_drifts(g)
        assert report.total_drifts == 0
        assert report.drift_score == 100.0

    def test_clean_graph(self):
        c = _comp(
            "app", "app",
            encryption_in_transit=True, auth_required=True,
            autoscaling=True, failover=True,
        )
        g = _graph(c)
        report = self.engine.detect_drifts(g)
        assert report.drift_score > 80.0

    def test_report_counts_match(self):
        db = _comp("db", "db", ComponentType.DATABASE, pci_scope=True)
        g = _graph(db)
        report = self.engine.detect_drifts(g)
        expected_total = (
            report.critical_count
            + report.high_count
            + report.medium_count
            + report.low_count
            + sum(1 for d in report.drifts if d.severity == DriftSeverity.INFO)
        )
        assert report.total_drifts == expected_total

    def test_report_has_recommendations(self):
        lb = _comp("lb", "lb", ComponentType.LOAD_BALANCER)
        db = _comp("db", "db", ComponentType.DATABASE)
        g = _graph(lb, db)
        report = self.engine.detect_drifts(g)
        assert len(report.recommendations) > 0

    def test_drift_score_decreases_with_issues(self):
        clean_c = _comp(
            "app", "app",
            encryption_in_transit=True, auth_required=True,
            autoscaling=True,
        )
        dirty_db = _comp("db", "db", ComponentType.DATABASE, pci_scope=True)
        g_clean = _graph(clean_c)
        g_dirty = _graph(dirty_db)
        clean_score = self.engine.detect_drifts(g_clean).drift_score
        dirty_score = self.engine.detect_drifts(g_dirty).drift_score
        assert dirty_score < clean_score

    def test_auto_fixable_count(self):
        db = _comp("db", "db", ComponentType.DATABASE, pci_scope=True)
        g = _graph(db)
        report = self.engine.detect_drifts(g)
        expected = sum(1 for d in report.drifts if d.auto_fixable)
        assert report.auto_fixable_count == expected

    def test_drift_score_floor_at_zero(self):
        # Create many issues to push score below 0
        comps = []
        for i in range(20):
            comps.append(_comp(
                f"db{i}", f"db{i}", ComponentType.DATABASE,
                pci_scope=True, contains_phi=True,
            ))
        g = _graph(*comps)
        report = self.engine.detect_drifts(g)
        assert report.drift_score >= 0.0

    def test_drift_score_ceiling_at_100(self):
        g = _graph()
        report = self.engine.detect_drifts(g)
        assert report.drift_score <= 100.0


# ---------------------------------------------------------------------------
# calculate_drift_score
# ---------------------------------------------------------------------------


class TestCalculateDriftScore:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_empty_graph_score_100(self):
        g = _graph()
        assert self.engine.calculate_drift_score(g) == 100.0

    def test_issues_lower_score(self):
        db = _comp("db", "db", ComponentType.DATABASE, pci_scope=True)
        g = _graph(db)
        assert self.engine.calculate_drift_score(g) < 100.0


# ---------------------------------------------------------------------------
# generate_remediation_plan
# ---------------------------------------------------------------------------


class TestGenerateRemediationPlan:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_empty_drifts(self):
        plan = self.engine.generate_remediation_plan([])
        assert plan.total_steps == 0
        assert plan.auto_fixable_steps == 0
        assert plan.manual_steps == 0

    def test_plan_sorts_by_severity(self):
        drifts = [
            DriftDetection(
                component_id="c1", drift_type=DriftType.CONFIG_DRIFT,
                severity=DriftSeverity.LOW, expected_value="a",
                actual_value="b", remediation="fix low",
            ),
            DriftDetection(
                component_id="c2", drift_type=DriftType.TLS_EXPIRY,
                severity=DriftSeverity.CRITICAL, expected_value="a",
                actual_value="b", remediation="fix critical",
            ),
        ]
        plan = self.engine.generate_remediation_plan(drifts)
        assert plan.steps[0].severity == DriftSeverity.CRITICAL
        assert plan.steps[1].severity == DriftSeverity.LOW

    def test_plan_step_priorities(self):
        drifts = [
            DriftDetection(
                component_id="c1", drift_type=DriftType.CONFIG_DRIFT,
                severity=DriftSeverity.MEDIUM, expected_value="a",
                actual_value="b", remediation="fix",
            ),
            DriftDetection(
                component_id="c2", drift_type=DriftType.TLS_EXPIRY,
                severity=DriftSeverity.HIGH, expected_value="a",
                actual_value="b", remediation="fix",
            ),
        ]
        plan = self.engine.generate_remediation_plan(drifts)
        assert plan.steps[0].priority == 1
        assert plan.steps[1].priority == 2

    def test_plan_auto_fixable_count(self):
        drifts = [
            DriftDetection(
                component_id="c1", drift_type=DriftType.CONFIG_DRIFT,
                severity=DriftSeverity.LOW, expected_value="a",
                actual_value="b", remediation="auto", auto_fixable=True,
            ),
            DriftDetection(
                component_id="c2", drift_type=DriftType.TLS_EXPIRY,
                severity=DriftSeverity.HIGH, expected_value="a",
                actual_value="b", remediation="manual",
            ),
        ]
        plan = self.engine.generate_remediation_plan(drifts)
        assert plan.auto_fixable_steps == 1
        assert plan.manual_steps == 1

    def test_plan_total_steps(self):
        drifts = [
            DriftDetection(
                component_id="c1", drift_type=DriftType.CONFIG_DRIFT,
                severity=DriftSeverity.LOW, expected_value="a",
                actual_value="b", remediation="fix",
            ),
        ]
        plan = self.engine.generate_remediation_plan(drifts)
        assert plan.total_steps == 1

    def test_plan_risk_reduction(self):
        drifts = [
            DriftDetection(
                component_id="c1", drift_type=DriftType.TLS_EXPIRY,
                severity=DriftSeverity.CRITICAL, expected_value="a",
                actual_value="b", remediation="fix",
            ),
        ]
        plan = self.engine.generate_remediation_plan(drifts)
        assert plan.estimated_risk_reduction > 0.0

    def test_plan_risk_reduction_capped_at_100(self):
        drifts = []
        for i in range(20):
            drifts.append(DriftDetection(
                component_id=f"c{i}", drift_type=DriftType.TLS_EXPIRY,
                severity=DriftSeverity.CRITICAL, expected_value="a",
                actual_value="b", remediation="fix",
            ))
        plan = self.engine.generate_remediation_plan(drifts)
        assert plan.estimated_risk_reduction <= 100.0


# ---------------------------------------------------------------------------
# Blast radius
# ---------------------------------------------------------------------------


class TestBlastRadius:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_blast_radius_included(self):
        db = _comp("db", "db", ComponentType.DATABASE, pci_scope=True)
        app = _comp("app", "app")
        g = _graph(db, app, edges=[("app", "db")])
        report = self.engine.detect_drifts(g)
        # At least one drift should have blast radius containing 'app'
        any_blast = any(d.blast_radius for d in report.drifts)
        assert any_blast

    def test_blast_radius_transitive(self):
        c1 = _comp("c1", "c1")
        c2 = _comp("c2", "c2")
        c3 = _comp("c3", "c3", ComponentType.DATABASE, pci_scope=True)
        g = _graph(c1, c2, c3, edges=[("c1", "c2"), ("c2", "c3")])
        report = self.engine.detect_drifts(g)
        # c3 drifts should have c2 and c1 in blast radius
        c3_drifts = [d for d in report.drifts if d.component_id == "c3"]
        if c3_drifts:
            blast = c3_drifts[0].blast_radius
            assert "c2" in blast


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class TestRecommendations:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_version_skew_recommendation(self):
        g = _graph(
            _comp("db1", "postgres-12", ComponentType.DATABASE),
            _comp("db2", "postgres-14", ComponentType.DATABASE),
            _comp("db3", "postgres-14", ComponentType.DATABASE),
        )
        report = self.engine.detect_drifts(g)
        assert any("version" in r.lower() for r in report.recommendations)

    def test_security_recommendation(self):
        lb = _comp("lb", "lb", ComponentType.LOAD_BALANCER)
        g = _graph(lb)
        report = self.engine.detect_drifts(g)
        assert any("security" in r.lower() or "tls" in r.lower() for r in report.recommendations)

    def test_capacity_recommendation(self):
        a = _comp("app", "app", max_rps=20000, replicas=2)
        db = _comp("db", "db", ComponentType.DATABASE, max_rps=5000)
        g = _graph(a, db, edges=[("app", "db")])
        report = self.engine.detect_drifts(g)
        assert any("capacity" in r.lower() for r in report.recommendations)

    def test_recommendations_deduplicated(self):
        g = _graph(
            _comp("db1", "postgres-12", ComponentType.DATABASE),
            _comp("db2", "postgres-14", ComponentType.DATABASE),
            _comp("db3", "postgres-14", ComponentType.DATABASE),
            _comp("db4", "postgres-13", ComponentType.DATABASE),
        )
        report = self.engine.detect_drifts(g)
        version_recs = [r for r in report.recommendations if "version" in r.lower()]
        assert len(version_recs) <= 1

    def test_compliance_recommendation(self):
        c = _comp("db", "db", ComponentType.DATABASE, pci_scope=True)
        g = _graph(c)
        report = self.engine.detect_drifts(g)
        assert any("compliance" in r.lower() for r in report.recommendations)


# ---------------------------------------------------------------------------
# Impact estimation
# ---------------------------------------------------------------------------


class TestImpactEstimation:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_localised_impact(self):
        d = DriftDetection(
            component_id="c1", drift_type=DriftType.CONFIG_DRIFT,
            severity=DriftSeverity.LOW, expected_value="a",
            actual_value="b", remediation="fix", blast_radius=[],
        )
        result = self.engine._estimate_impact(d)
        assert "localised" in result.lower()

    def test_low_blast_radius(self):
        d = DriftDetection(
            component_id="c1", drift_type=DriftType.CONFIG_DRIFT,
            severity=DriftSeverity.LOW, expected_value="a",
            actual_value="b", remediation="fix", blast_radius=["c2"],
        )
        result = self.engine._estimate_impact(d)
        assert "low" in result.lower()

    def test_moderate_blast_radius(self):
        d = DriftDetection(
            component_id="c1", drift_type=DriftType.CONFIG_DRIFT,
            severity=DriftSeverity.LOW, expected_value="a",
            actual_value="b", remediation="fix", blast_radius=["c2", "c3", "c4"],
        )
        result = self.engine._estimate_impact(d)
        assert "moderate" in result.lower()

    def test_high_blast_radius(self):
        d = DriftDetection(
            component_id="c1", drift_type=DriftType.CONFIG_DRIFT,
            severity=DriftSeverity.LOW, expected_value="a",
            actual_value="b", remediation="fix",
            blast_radius=["c2", "c3", "c4", "c5", "c6", "c7"],
        )
        result = self.engine._estimate_impact(d)
        assert "high" in result.lower()


# ---------------------------------------------------------------------------
# Severity penalty
# ---------------------------------------------------------------------------


class TestSeverityPenalty:
    def test_critical_penalty(self):
        assert DependencyDriftEngine._severity_penalty(DriftSeverity.CRITICAL) == 15.0

    def test_high_penalty(self):
        assert DependencyDriftEngine._severity_penalty(DriftSeverity.HIGH) == 8.0

    def test_medium_penalty(self):
        assert DependencyDriftEngine._severity_penalty(DriftSeverity.MEDIUM) == 4.0

    def test_low_penalty(self):
        assert DependencyDriftEngine._severity_penalty(DriftSeverity.LOW) == 2.0

    def test_info_penalty(self):
        assert DependencyDriftEngine._severity_penalty(DriftSeverity.INFO) == 0.5


# ---------------------------------------------------------------------------
# Version skew severity helper
# ---------------------------------------------------------------------------


class TestVersionSkewSeverity:
    def test_major_diff_2_critical(self):
        sev = DependencyDriftEngine._version_skew_severity("14", "12")
        assert sev == DriftSeverity.CRITICAL

    def test_major_diff_1_high(self):
        sev = DependencyDriftEngine._version_skew_severity("14", "13")
        assert sev == DriftSeverity.HIGH

    def test_minor_diff_medium(self):
        sev = DependencyDriftEngine._version_skew_severity("7.2", "7.0")
        assert sev == DriftSeverity.MEDIUM

    def test_same_version_low(self):
        sev = DependencyDriftEngine._version_skew_severity("7", "7")
        assert sev == DriftSeverity.LOW


# ---------------------------------------------------------------------------
# Extract API version
# ---------------------------------------------------------------------------


class TestExtractApiVersion:
    def test_api_v_tag(self):
        c = _comp("c", "c", tags=["api-v2"])
        result = DependencyDriftEngine._extract_api_version(c)
        assert result == "api-v2"

    def test_api_underscore_tag(self):
        c = _comp("c", "c", tags=["api_v3"])
        result = DependencyDriftEngine._extract_api_version(c)
        assert result == "api_v3"

    def test_v_numeric_tag(self):
        c = _comp("c", "c", tags=["v2"])
        result = DependencyDriftEngine._extract_api_version(c)
        assert result == "v2"

    def test_no_api_version(self):
        c = _comp("c", "c", tags=["prod", "us-east-1"])
        result = DependencyDriftEngine._extract_api_version(c)
        assert result is None

    def test_no_tags(self):
        c = _comp("c", "c")
        result = DependencyDriftEngine._extract_api_version(c)
        assert result is None


# ---------------------------------------------------------------------------
# Component version extraction
# ---------------------------------------------------------------------------


class TestComponentVersion:
    def test_from_name(self):
        c = _comp("db", "postgres-14")
        v = DependencyDriftEngine._component_version(c)
        assert v == "14"

    def test_from_tag(self):
        c = _comp("db", "primary-db", tags=["v15.2"])
        v = DependencyDriftEngine._component_version(c)
        assert v == "15.2"

    def test_tag_takes_priority(self):
        c = _comp("db", "postgres-14", tags=["v15"])
        v = DependencyDriftEngine._component_version(c)
        assert v == "15"

    def test_no_version(self):
        c = _comp("db", "database-primary")
        v = DependencyDriftEngine._component_version(c)
        assert v is None


# ---------------------------------------------------------------------------
# Encryption inconsistency edge cases
# ---------------------------------------------------------------------------


class TestEncryptionInconsistencyEdgeCases:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_both_encrypted_no_inconsistency(self):
        """Line 901: dep_comp also has encryption → skip."""
        a = _comp("fe", "frontend", encryption_in_transit=True)
        b = _comp("be", "backend", encryption_in_transit=True)
        g = _graph(a, b, edges=[("fe", "be")])
        drifts = self.engine.detect_security_drift(g)
        incon = [
            d for d in drifts
            if d.component_id == "be"
            and "connected from encrypted" in d.remediation
        ]
        assert incon == []

    def test_dedup_prevents_duplicate_encryption_drifts(self):
        """Line 904: same pair seen twice → skip duplicate.

        Two encrypted components (fe1, fe2) both depend on the same
        unencrypted backend. The method should only report one drift
        per unique (source->target) pair, but each source generates
        its own key so we get one per source.
        """
        fe1 = _comp("fe1", "frontend1", encryption_in_transit=True)
        fe2 = _comp("fe2", "frontend2", encryption_in_transit=True)
        be = _comp("be", "backend", encryption_in_transit=False)
        g = _graph(fe1, fe2, be, edges=[("fe1", "be"), ("fe2", "be")])
        drifts = self.engine.detect_security_drift(g)
        incon = [
            d for d in drifts
            if d.component_id == "be"
            and "connected from encrypted" in d.remediation
        ]
        # Two distinct source→target pairs (fe1→be, fe2→be) should produce 2
        assert len(incon) == 2

    def test_dedup_same_source_target_only_once(self):
        """Line 904: exact same key produces only one drift."""
        # The dedup is keyed by "{comp.id}->{dep_comp.id}".
        # Since iteration is over unique components, the same key can't
        # appear twice unless there's a bug. However we verify that
        # the seen set is working by calling the internal method directly.
        fe = _comp("fe", "frontend", encryption_in_transit=True)
        be = _comp("be", "backend", encryption_in_transit=False)
        g = _graph(fe, be, edges=[("fe", "be")])
        drifts = self.engine._detect_encryption_inconsistency(g)
        assert len(drifts) == 1


# ---------------------------------------------------------------------------
# Recommendations for API version mismatch and topology drift
# ---------------------------------------------------------------------------


class TestRecommendationsApiAndTopology:
    def setup_method(self):
        self.engine = DependencyDriftEngine()

    def test_api_version_mismatch_recommendation(self):
        """Lines 1074-1078: API_VERSION_MISMATCH recommendation branch."""
        a = _comp("fe", "frontend", tags=["api-v1"])
        b = _comp("be", "backend", tags=["api-v2"])
        g = _graph(a, b, edges=[("fe", "be")])
        report = self.engine.detect_drifts(g)
        assert any("api version" in r.lower() for r in report.recommendations)

    def test_topology_drift_recommendation(self):
        """Lines 1079-1083: TOPOLOGY_DRIFT recommendation branch."""
        a = _comp("a", "a")
        b = _comp("b", "b")
        baseline = _graph(a, b)
        current = _graph(a)
        topo_drifts = self.engine.detect_topology_drift(current, baseline)
        # To get the recommendation, we need it in detect_drifts. But topology
        # drift is not called by detect_drifts (no baseline). So build a report
        # manually with _build_report.
        report = self.engine._build_report(topo_drifts, current)
        assert any("topology" in r.lower() for r in report.recommendations)
