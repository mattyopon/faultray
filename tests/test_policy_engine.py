"""Comprehensive tests for the Policy-as-Code Engine.

Targets 99%+ coverage of ``faultray.policy.engine``.
"""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
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
from faultray.policy.engine import (
    PolicyCategory,
    PolicyEngine,
    PolicyReport,
    PolicyResult,
    PolicyRule,
    PolicySet,
    PolicySeverity,
    PolicyViolation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    **kwargs,
) -> Component:
    return Component(id=cid, name=cid, type=ctype, replicas=replicas, **kwargs)


def _empty_graph() -> InfraGraph:
    return InfraGraph()


def _simple_graph() -> InfraGraph:
    """Graph with app -> db dependency, minimal settings."""
    g = InfraGraph()
    g.add_component(_make_component("app", ComponentType.APP_SERVER, replicas=1))
    g.add_component(_make_component("db", ComponentType.DATABASE, replicas=1))
    g.add_dependency(Dependency(source_id="app", target_id="db"))
    return g


def _secure_graph() -> InfraGraph:
    """Graph where every component is well-configured -- should pass most rules."""
    g = InfraGraph()
    sec = SecurityProfile(
        encryption_at_rest=True,
        encryption_in_transit=True,
        waf_protected=True,
        rate_limiting=True,
        auth_required=True,
        network_segmented=True,
        backup_enabled=True,
        log_enabled=True,
    )
    comp_tags = ComplianceTags(change_management=True)

    g.add_component(
        Component(
            id="lb",
            name="load-balancer",
            type=ComponentType.LOAD_BALANCER,
            replicas=2,
            security=sec,
            compliance_tags=comp_tags,
            failover=FailoverConfig(enabled=True),
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=5),
        )
    )
    g.add_component(
        Component(
            id="app",
            name="app-server",
            type=ComponentType.APP_SERVER,
            replicas=3,
            security=sec,
            compliance_tags=comp_tags,
            failover=FailoverConfig(enabled=True),
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        )
    )
    g.add_component(
        Component(
            id="db",
            name="database",
            type=ComponentType.DATABASE,
            replicas=2,
            security=sec,
            compliance_tags=comp_tags,
            failover=FailoverConfig(enabled=True),
        )
    )
    g.add_dependency(Dependency(source_id="lb", target_id="app"))
    g.add_dependency(Dependency(source_id="app", target_id="db"))
    return g


# ===========================================================================
# 1. Enum tests
# ===========================================================================


class TestPolicySeverityEnum:
    def test_values(self):
        assert PolicySeverity.INFO.value == "info"
        assert PolicySeverity.WARNING.value == "warning"
        assert PolicySeverity.ERROR.value == "error"
        assert PolicySeverity.CRITICAL.value == "critical"

    def test_count(self):
        assert len(PolicySeverity) == 4

    def test_from_string(self):
        assert PolicySeverity("info") is PolicySeverity.INFO
        assert PolicySeverity("critical") is PolicySeverity.CRITICAL


class TestPolicyCategoryEnum:
    def test_values(self):
        assert PolicyCategory.RESILIENCE.value == "resilience"
        assert PolicyCategory.SECURITY.value == "security"
        assert PolicyCategory.COST.value == "cost"
        assert PolicyCategory.COMPLIANCE.value == "compliance"
        assert PolicyCategory.PERFORMANCE.value == "performance"
        assert PolicyCategory.OPERATIONAL.value == "operational"

    def test_count(self):
        assert len(PolicyCategory) == 6


# ===========================================================================
# 2. Data class construction
# ===========================================================================


class TestPolicyRuleDataclass:
    def test_defaults(self):
        r = PolicyRule(
            id="r1",
            name="Rule 1",
            description="desc",
            severity=PolicySeverity.INFO,
            category=PolicyCategory.COST,
            condition="cond",
            message_template="msg",
        )
        assert r.enabled is True
        assert r.tags == []

    def test_custom_fields(self):
        r = PolicyRule(
            id="r2",
            name="Rule 2",
            description="desc",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.SECURITY,
            condition="cond",
            message_template="msg",
            enabled=False,
            tags=["sec", "enc"],
        )
        assert r.enabled is False
        assert r.tags == ["sec", "enc"]


class TestPolicyViolationDataclass:
    def test_fields(self):
        v = PolicyViolation(
            rule_id="r1",
            rule_name="Rule 1",
            severity=PolicySeverity.ERROR,
            component_id="c1",
            component_name="comp1",
            message="msg",
            remediation="fix",
        )
        assert v.rule_id == "r1"
        assert v.severity == PolicySeverity.ERROR
        assert v.remediation == "fix"


class TestPolicyResultDataclass:
    def test_pass(self):
        rule = PolicyRule(
            id="r",
            name="R",
            description="",
            severity=PolicySeverity.INFO,
            category=PolicyCategory.COST,
            condition="c",
            message_template="",
        )
        r = PolicyResult(rule=rule, passed=True, violations=[], components_checked=5)
        assert r.passed is True
        assert r.components_checked == 5

    def test_fail(self):
        rule = PolicyRule(
            id="r",
            name="R",
            description="",
            severity=PolicySeverity.INFO,
            category=PolicyCategory.COST,
            condition="c",
            message_template="",
        )
        v = PolicyViolation(
            rule_id="r",
            rule_name="R",
            severity=PolicySeverity.INFO,
            component_id="c1",
            component_name="C1",
            message="bad",
            remediation="fix",
        )
        r = PolicyResult(rule=rule, passed=False, violations=[v], components_checked=1)
        assert r.passed is False
        assert len(r.violations) == 1


class TestPolicyReportDataclass:
    def test_fields(self):
        report = PolicyReport(
            results=[],
            total_rules=10,
            passed_rules=8,
            failed_rules=2,
            violations_by_severity={"error": 2},
            overall_pass=False,
            score=80.0,
        )
        assert report.total_rules == 10
        assert report.score == 80.0
        assert report.overall_pass is False


class TestPolicySetDataclass:
    def test_fields(self):
        ps = PolicySet(name="test", description="desc", version="1.0.0", rules=[])
        assert ps.name == "test"
        assert ps.rules == []


# ===========================================================================
# 3. Built-in policies
# ===========================================================================


class TestBuiltinPolicies:
    def test_builtin_count(self):
        engine = PolicyEngine()
        ps = engine.get_builtin_policies()
        assert len(ps.rules) == 15

    def test_builtin_ids(self):
        engine = PolicyEngine()
        ps = engine.get_builtin_policies()
        ids = {r.id for r in ps.rules}
        expected = {
            "no-spof",
            "min-replicas",
            "failover-required",
            "encryption-at-rest",
            "encryption-in-transit",
            "autoscaling-enabled",
            "max-utilization",
            "monitoring-enabled",
            "backup-required",
            "network-segmented",
            "auth-required",
            "max-dependency-depth",
            "circuit-breaker",
            "rate-limiting",
            "change-management",
        }
        assert ids == expected

    def test_all_builtin_enabled(self):
        engine = PolicyEngine()
        ps = engine.get_builtin_policies()
        assert all(r.enabled for r in ps.rules)

    def test_all_builtin_have_tags(self):
        engine = PolicyEngine()
        ps = engine.get_builtin_policies()
        for r in ps.rules:
            assert len(r.tags) > 0, f"Rule {r.id} has no tags"

    def test_severity_distribution(self):
        engine = PolicyEngine()
        ps = engine.get_builtin_policies()
        sevs = {r.severity for r in ps.rules}
        assert PolicySeverity.CRITICAL in sevs
        assert PolicySeverity.ERROR in sevs
        assert PolicySeverity.WARNING in sevs

    def test_category_distribution(self):
        engine = PolicyEngine()
        ps = engine.get_builtin_policies()
        cats = {r.category for r in ps.rules}
        assert PolicyCategory.RESILIENCE in cats
        assert PolicyCategory.SECURITY in cats
        assert PolicyCategory.PERFORMANCE in cats
        assert PolicyCategory.OPERATIONAL in cats
        assert PolicyCategory.COMPLIANCE in cats

    def test_builtin_policy_set_metadata(self):
        engine = PolicyEngine()
        ps = engine.get_builtin_policies()
        assert ps.name == "builtin"
        assert ps.version == "1.0.0"
        assert "Built-in" in ps.description


# ===========================================================================
# 4. Individual rule evaluation (pass and fail)
# ===========================================================================


class TestNoSpofRule:
    def test_fail_single_replica_with_dependents(self):
        engine = PolicyEngine()
        g = _simple_graph()  # db has 1 replica, app depends on db
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "no-spof")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed
        # db has a dependent (app)
        assert any(v.component_id == "db" for v in result.violations)

    def test_pass_multiple_replicas(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER, replicas=2))
        g.add_component(_make_component("db", ComponentType.DATABASE, replicas=3))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "no-spof")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_single_replica_no_dependents(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER, replicas=1))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "no-spof")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestMinReplicasRule:
    def test_fail_database_single_replica(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("db", ComponentType.DATABASE, replicas=1))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "min-replicas")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed
        assert len(result.violations) == 1
        assert "1 replica" in result.violations[0].message

    def test_pass_database_two_replicas(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("db", ComponentType.DATABASE, replicas=2))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "min-replicas")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_non_database_single_replica(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER, replicas=1))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "min-replicas")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestFailoverRequiredRule:
    def test_fail_database_no_failover(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("db", ComponentType.DATABASE, replicas=2))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "failover-required")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_fail_app_server_no_failover(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "failover-required")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_with_failover(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="db",
                name="db",
                type=ComponentType.DATABASE,
                replicas=2,
                failover=FailoverConfig(enabled=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "failover-required")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_cache_no_failover(self):
        """Cache is not a critical type, so no failover required."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("cache", ComponentType.CACHE))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "failover-required")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestEncryptionAtRestRule:
    def test_fail_database_no_encryption(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("db", ComponentType.DATABASE))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-at-rest")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_fail_storage_no_encryption(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("s3", ComponentType.STORAGE))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-at-rest")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_with_encryption(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="db",
                name="db",
                type=ComponentType.DATABASE,
                security=SecurityProfile(encryption_at_rest=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-at-rest")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_non_storage_type(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-at-rest")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestEncryptionInTransitRule:
    def test_fail_no_tls(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-in-transit")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_with_tls(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                security=SecurityProfile(encryption_in_transit=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-in-transit")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestAutoscalingEnabledRule:
    def test_fail_app_server_no_autoscaling(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "autoscaling-enabled")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_fail_web_server_no_autoscaling(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("web", ComponentType.WEB_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "autoscaling-enabled")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_with_autoscaling(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "autoscaling-enabled")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_database_no_autoscaling(self):
        """Databases are not expected to have autoscaling in this rule."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("db", ComponentType.DATABASE))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "autoscaling-enabled")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestMaxUtilizationRule:
    def test_fail_high_utilization(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                metrics=ResourceMetrics(cpu_percent=95.0),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "max-utilization")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed
        assert "95.0%" in result.violations[0].message

    def test_pass_low_utilization(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                metrics=ResourceMetrics(cpu_percent=50.0),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "max-utilization")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_at_exactly_80(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                metrics=ResourceMetrics(cpu_percent=80.0),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "max-utilization")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestMonitoringEnabledRule:
    def test_fail_no_logging(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "monitoring-enabled")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_with_logging(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                security=SecurityProfile(log_enabled=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "monitoring-enabled")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestBackupRequiredRule:
    def test_fail_database_no_backup(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("db", ComponentType.DATABASE))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "backup-required")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_fail_storage_no_backup(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("s3", ComponentType.STORAGE))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "backup-required")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_with_backup(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="db",
                name="db",
                type=ComponentType.DATABASE,
                security=SecurityProfile(backup_enabled=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "backup-required")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_non_storage_type(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "backup-required")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestNetworkSegmentedRule:
    def test_fail_not_segmented(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "network-segmented")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_segmented(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                security=SecurityProfile(network_segmented=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "network-segmented")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestAuthRequiredRule:
    def test_fail_lb_no_auth(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("lb", ComponentType.LOAD_BALANCER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "auth-required")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_fail_web_server_no_auth(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("web", ComponentType.WEB_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "auth-required")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_fail_external_api_no_auth(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("ext", ComponentType.EXTERNAL_API))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "auth-required")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_with_auth(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="lb",
                name="lb",
                type=ComponentType.LOAD_BALANCER,
                security=SecurityProfile(auth_required=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "auth-required")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_internal_component_no_auth(self):
        """Internal-only components (e.g. database) do not require auth in this rule."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("db", ComponentType.DATABASE))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "auth-required")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestMaxDependencyDepthRule:
    def test_fail_deep_chain(self):
        """Build a chain of depth 7 (a -> b -> c -> d -> e -> f -> g)."""
        engine = PolicyEngine()
        g = InfraGraph()
        ids = ["a", "b", "c", "d", "e", "f", "g"]
        for cid in ids:
            g.add_component(_make_component(cid, ComponentType.APP_SERVER))
        for i in range(len(ids) - 1):
            g.add_dependency(Dependency(source_id=ids[i], target_id=ids[i + 1]))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "max-dependency-depth")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed
        assert any("7" in v.message for v in result.violations)

    def test_pass_short_chain(self):
        """Chain of depth 3 -- under the limit of 5."""
        engine = PolicyEngine()
        g = InfraGraph()
        for cid in ["a", "b", "c"]:
            g.add_component(_make_component(cid, ComponentType.APP_SERVER))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="b", target_id="c"))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "max-dependency-depth")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_exactly_5(self):
        """Chain of depth 5 -- at the limit."""
        engine = PolicyEngine()
        g = InfraGraph()
        ids = ["a", "b", "c", "d", "e"]
        for cid in ids:
            g.add_component(_make_component(cid, ComponentType.APP_SERVER))
        for i in range(len(ids) - 1):
            g.add_dependency(Dependency(source_id=ids[i], target_id=ids[i + 1]))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "max-dependency-depth")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestCircuitBreakerRule:
    def test_fail_external_dep_no_cb(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        g.add_component(_make_component("ext", ComponentType.EXTERNAL_API))
        g.add_dependency(Dependency(source_id="app", target_id="ext"))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "circuit-breaker")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed
        assert result.violations[0].component_id == "app"

    def test_pass_external_dep_with_cb(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        g.add_component(_make_component("ext", ComponentType.EXTERNAL_API))
        g.add_dependency(
            Dependency(
                source_id="app",
                target_id="ext",
                circuit_breaker=CircuitBreakerConfig(enabled=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "circuit-breaker")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_internal_dep_no_cb(self):
        """Circuit breaker rule only targets external API deps."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        g.add_component(_make_component("db", ComponentType.DATABASE))
        g.add_dependency(Dependency(source_id="app", target_id="db"))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "circuit-breaker")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestRateLimitingRule:
    def test_fail_lb_no_rate_limit(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("lb", ComponentType.LOAD_BALANCER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "rate-limiting")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_fail_external_api_no_rate_limit(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("ext", ComponentType.EXTERNAL_API))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "rate-limiting")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_with_rate_limit(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="lb",
                name="lb",
                type=ComponentType.LOAD_BALANCER,
                security=SecurityProfile(rate_limiting=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "rate-limiting")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_pass_app_server_no_rate_limit(self):
        """App servers are not required to have rate limiting in this rule."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "rate-limiting")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


class TestChangeManagementRule:
    def test_fail_no_change_mgmt(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "change-management")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed

    def test_pass_with_change_mgmt(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                compliance_tags=ComplianceTags(change_management=True),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "change-management")
        result = engine.evaluate_rule(g, rule)
        assert result.passed


# ===========================================================================
# 5. Full evaluation (evaluate method)
# ===========================================================================


class TestEvaluateFullGraph:
    def test_empty_graph_all_pass(self):
        """An empty graph has no components, so no rules can fail."""
        engine = PolicyEngine()
        report = engine.evaluate(_empty_graph())
        assert report.overall_pass is True
        assert report.score == 100.0
        assert report.failed_rules == 0

    def test_secure_graph_many_pass(self):
        """A well-configured graph should pass most rules."""
        engine = PolicyEngine()
        report = engine.evaluate(_secure_graph())
        # The secure graph has all security/compliance/failover configured
        assert report.passed_rules > report.failed_rules
        assert report.score > 50.0

    def test_simple_graph_has_failures(self):
        """A minimal graph should fail multiple rules."""
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        assert report.overall_pass is False
        assert report.failed_rules > 0
        assert report.score < 100.0

    def test_report_structure(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        assert isinstance(report, PolicyReport)
        assert report.total_rules == report.passed_rules + report.failed_rules
        assert isinstance(report.violations_by_severity, dict)
        assert isinstance(report.results, list)
        for r in report.results:
            assert isinstance(r, PolicyResult)
            assert isinstance(r.rule, PolicyRule)

    def test_violations_have_remediation(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        for result in report.results:
            for v in result.violations:
                assert v.remediation != "", f"Violation for {v.rule_id} has empty remediation"

    def test_violations_have_component_info(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        for result in report.results:
            for v in result.violations:
                assert v.component_id != ""
                assert v.component_name != ""

    def test_total_rules_matches_enabled(self):
        engine = PolicyEngine()
        ps = engine.get_builtin_policies()
        enabled_count = sum(1 for r in ps.rules if r.enabled)
        report = engine.evaluate(_simple_graph(), ps)
        assert report.total_rules == enabled_count

    def test_evaluate_with_custom_policy_set(self):
        engine = PolicyEngine()
        custom = PolicySet(
            name="custom",
            description="Test",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="custom-1",
                    name="Custom Rule",
                    description="Check encryption in transit",
                    severity=PolicySeverity.WARNING,
                    category=PolicyCategory.SECURITY,
                    condition="component.security.encryption_in_transit == True",
                    message_template="No TLS",
                ),
            ],
        )
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        report = engine.evaluate(g, custom)
        assert report.total_rules == 1
        assert report.failed_rules == 1


# ===========================================================================
# 6. Score calculation
# ===========================================================================


class TestScoreCalculation:
    def test_all_pass_100(self):
        engine = PolicyEngine()
        report = engine.evaluate(_empty_graph())
        assert report.score == 100.0

    def test_score_formula(self):
        """Score should be passed_rules / total_rules * 100."""
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        expected = round(report.passed_rules / report.total_rules * 100, 2)
        assert report.score == expected

    def test_single_rule_pass_score_100(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                security=SecurityProfile(encryption_in_transit=True),
            )
        )
        ps = PolicySet(
            name="single",
            description="",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="tls",
                    name="TLS",
                    description="",
                    severity=PolicySeverity.ERROR,
                    category=PolicyCategory.SECURITY,
                    condition="component.security.encryption_in_transit == True",
                    message_template="",
                ),
            ],
        )
        report = engine.evaluate(g, ps)
        assert report.score == 100.0
        assert report.overall_pass is True

    def test_single_rule_fail_score_0(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        ps = PolicySet(
            name="single",
            description="",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="tls",
                    name="TLS",
                    description="",
                    severity=PolicySeverity.ERROR,
                    category=PolicyCategory.SECURITY,
                    condition="component.security.encryption_in_transit == True",
                    message_template="",
                ),
            ],
        )
        report = engine.evaluate(g, ps)
        assert report.score == 0.0
        assert report.overall_pass is False


# ===========================================================================
# 7. Disabled rules
# ===========================================================================


class TestDisabledRules:
    def test_disabled_rule_skipped(self):
        engine = PolicyEngine()
        ps = PolicySet(
            name="test",
            description="",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="disabled-rule",
                    name="Disabled",
                    description="",
                    severity=PolicySeverity.CRITICAL,
                    category=PolicyCategory.SECURITY,
                    condition="component.security.encryption_in_transit == True",
                    message_template="",
                    enabled=False,
                ),
            ],
        )
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        report = engine.evaluate(g, ps)
        assert report.total_rules == 0
        assert report.score == 100.0  # No rules evaluated => 100%

    def test_mix_enabled_disabled(self):
        engine = PolicyEngine()
        ps = PolicySet(
            name="test",
            description="",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="enabled-rule",
                    name="Enabled",
                    description="",
                    severity=PolicySeverity.ERROR,
                    category=PolicyCategory.SECURITY,
                    condition="component.security.encryption_in_transit == True",
                    message_template="",
                    enabled=True,
                ),
                PolicyRule(
                    id="disabled-rule",
                    name="Disabled",
                    description="",
                    severity=PolicySeverity.CRITICAL,
                    category=PolicyCategory.SECURITY,
                    condition="component.security.encryption_at_rest == True for storage",
                    message_template="",
                    enabled=False,
                ),
            ],
        )
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                security=SecurityProfile(encryption_in_transit=True),
            )
        )
        report = engine.evaluate(g, ps)
        assert report.total_rules == 1
        assert report.passed_rules == 1


# ===========================================================================
# 8. Policy set loading and exporting (round-trip)
# ===========================================================================


class TestLoadExportPolicySet:
    def test_round_trip(self):
        engine = PolicyEngine()
        original = engine.get_builtin_policies()
        exported = engine.export_policy_set(original)
        loaded = engine.load_policy_set(exported)

        assert loaded.name == original.name
        assert loaded.version == original.version
        assert loaded.description == original.description
        assert len(loaded.rules) == len(original.rules)

        for orig_rule, loaded_rule in zip(original.rules, loaded.rules):
            assert loaded_rule.id == orig_rule.id
            assert loaded_rule.name == orig_rule.name
            assert loaded_rule.severity == orig_rule.severity
            assert loaded_rule.category == orig_rule.category
            assert loaded_rule.condition == orig_rule.condition
            assert loaded_rule.enabled == orig_rule.enabled
            assert loaded_rule.tags == orig_rule.tags

    def test_export_structure(self):
        engine = PolicyEngine()
        ps = engine.get_builtin_policies()
        data = engine.export_policy_set(ps)
        assert "name" in data
        assert "version" in data
        assert "description" in data
        assert "rules" in data
        assert isinstance(data["rules"], list)
        for rd in data["rules"]:
            assert "id" in rd
            assert "severity" in rd
            assert "category" in rd
            assert "condition" in rd

    def test_load_minimal(self):
        engine = PolicyEngine()
        data = {
            "name": "minimal",
            "version": "0.1.0",
            "rules": [
                {
                    "id": "r1",
                    "name": "Rule 1",
                    "severity": "warning",
                    "category": "cost",
                    "condition": "some_condition",
                },
            ],
        }
        ps = engine.load_policy_set(data)
        assert ps.name == "minimal"
        assert len(ps.rules) == 1
        assert ps.rules[0].severity == PolicySeverity.WARNING
        assert ps.rules[0].category == PolicyCategory.COST
        assert ps.rules[0].enabled is True  # default
        assert ps.rules[0].tags == []  # default
        assert ps.rules[0].description == ""  # default

    def test_load_empty_rules(self):
        engine = PolicyEngine()
        data = {"rules": []}
        ps = engine.load_policy_set(data)
        assert ps.name == "unnamed"
        assert ps.version == "0.0.0"
        assert ps.rules == []

    def test_load_with_all_fields(self):
        engine = PolicyEngine()
        data = {
            "name": "full",
            "description": "Fully specified",
            "version": "2.0.0",
            "rules": [
                {
                    "id": "r1",
                    "name": "Rule 1",
                    "description": "A rule",
                    "severity": "critical",
                    "category": "security",
                    "condition": "cond",
                    "message_template": "msg",
                    "enabled": False,
                    "tags": ["a", "b"],
                },
            ],
        }
        ps = engine.load_policy_set(data)
        r = ps.rules[0]
        assert r.id == "r1"
        assert r.description == "A rule"
        assert r.severity == PolicySeverity.CRITICAL
        assert r.enabled is False
        assert r.tags == ["a", "b"]

    def test_export_preserves_disabled(self):
        engine = PolicyEngine()
        ps = PolicySet(
            name="test",
            description="",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="r1",
                    name="R",
                    description="",
                    severity=PolicySeverity.INFO,
                    category=PolicyCategory.COST,
                    condition="c",
                    message_template="",
                    enabled=False,
                    tags=["x"],
                ),
            ],
        )
        data = engine.export_policy_set(ps)
        assert data["rules"][0]["enabled"] is False
        assert data["rules"][0]["tags"] == ["x"]


# ===========================================================================
# 9. Policy set merging
# ===========================================================================


class TestMergePolicySets:
    def test_merge_empty(self):
        engine = PolicyEngine()
        merged = engine.merge_policy_sets([])
        assert merged.name == "empty"
        assert merged.rules == []

    def test_merge_single(self):
        engine = PolicyEngine()
        ps = PolicySet(
            name="A",
            description="Set A",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="r1",
                    name="Rule 1",
                    description="",
                    severity=PolicySeverity.INFO,
                    category=PolicyCategory.COST,
                    condition="c",
                    message_template="",
                ),
            ],
        )
        merged = engine.merge_policy_sets([ps])
        assert len(merged.rules) == 1
        assert merged.rules[0].id == "r1"

    def test_merge_deduplicates_by_id(self):
        engine = PolicyEngine()
        ps1 = PolicySet(
            name="A",
            description="",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="r1",
                    name="Rule 1 v1",
                    description="",
                    severity=PolicySeverity.INFO,
                    category=PolicyCategory.COST,
                    condition="c",
                    message_template="",
                ),
            ],
        )
        ps2 = PolicySet(
            name="B",
            description="",
            version="2.0.0",
            rules=[
                PolicyRule(
                    id="r1",
                    name="Rule 1 v2",
                    description="",
                    severity=PolicySeverity.CRITICAL,
                    category=PolicyCategory.SECURITY,
                    condition="c2",
                    message_template="",
                ),
            ],
        )
        merged = engine.merge_policy_sets([ps1, ps2])
        assert len(merged.rules) == 1
        # Later set takes precedence
        assert merged.rules[0].name == "Rule 1 v2"
        assert merged.rules[0].severity == PolicySeverity.CRITICAL

    def test_merge_combines_unique_rules(self):
        engine = PolicyEngine()
        ps1 = PolicySet(
            name="A",
            description="",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="r1",
                    name="Rule 1",
                    description="",
                    severity=PolicySeverity.INFO,
                    category=PolicyCategory.COST,
                    condition="c",
                    message_template="",
                ),
            ],
        )
        ps2 = PolicySet(
            name="B",
            description="",
            version="1.0.0",
            rules=[
                PolicyRule(
                    id="r2",
                    name="Rule 2",
                    description="",
                    severity=PolicySeverity.ERROR,
                    category=PolicyCategory.RESILIENCE,
                    condition="c2",
                    message_template="",
                ),
            ],
        )
        merged = engine.merge_policy_sets([ps1, ps2])
        assert len(merged.rules) == 2
        ids = {r.id for r in merged.rules}
        assert ids == {"r1", "r2"}

    def test_merge_name_and_version(self):
        engine = PolicyEngine()
        ps1 = PolicySet(name="A", description="", version="1.0.0", rules=[])
        ps2 = PolicySet(name="B", description="", version="2.0.0", rules=[])
        merged = engine.merge_policy_sets([ps1, ps2])
        assert merged.name == "A + B"
        assert merged.version == "2.0.0"
        assert "A" in merged.description
        assert "B" in merged.description


# ===========================================================================
# 10. Custom rule creation
# ===========================================================================


class TestCreateCustomRule:
    def test_create_with_enums(self):
        engine = PolicyEngine()
        rule = engine.create_custom_rule(
            id="custom-1",
            name="Custom Rule",
            description="A custom rule",
            condition="component.security.encryption_in_transit == True",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.SECURITY,
        )
        assert rule.id == "custom-1"
        assert rule.severity == PolicySeverity.ERROR
        assert rule.category == PolicyCategory.SECURITY
        assert rule.enabled is True
        assert rule.tags == []

    def test_create_with_strings(self):
        engine = PolicyEngine()
        rule = engine.create_custom_rule(
            id="custom-2",
            name="Custom Rule 2",
            description="desc",
            condition="cond",
            severity="warning",
            category="cost",
        )
        assert rule.severity == PolicySeverity.WARNING
        assert rule.category == PolicyCategory.COST

    def test_create_with_tags(self):
        engine = PolicyEngine()
        rule = engine.create_custom_rule(
            id="custom-3",
            name="Custom Rule 3",
            description="desc",
            condition="cond",
            severity=PolicySeverity.INFO,
            category=PolicyCategory.COMPLIANCE,
            tags=["tag1", "tag2"],
        )
        assert rule.tags == ["tag1", "tag2"]

    def test_create_disabled(self):
        engine = PolicyEngine()
        rule = engine.create_custom_rule(
            id="custom-4",
            name="Custom Rule 4",
            description="desc",
            condition="cond",
            severity=PolicySeverity.INFO,
            category=PolicyCategory.OPERATIONAL,
            enabled=False,
        )
        assert rule.enabled is False

    def test_create_with_message_template(self):
        engine = PolicyEngine()
        rule = engine.create_custom_rule(
            id="custom-5",
            name="Custom Rule 5",
            description="desc",
            condition="cond",
            severity=PolicySeverity.CRITICAL,
            category=PolicyCategory.RESILIENCE,
            message_template="{component} has an issue",
        )
        assert rule.message_template == "{component} has an issue"


# ===========================================================================
# 11. Severity filtering in report
# ===========================================================================


class TestSeverityFiltering:
    def test_violations_by_severity_counts(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        # Verify violations_by_severity is populated correctly
        total_violations = sum(report.violations_by_severity.values())
        actual_violations = sum(len(r.violations) for r in report.results)
        assert total_violations == actual_violations

    def test_violation_severities_match_rules(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        for result in report.results:
            for v in result.violations:
                assert v.severity == result.rule.severity

    def test_filter_results_by_severity(self):
        """Users can filter results by severity from the report."""
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        critical_results = [
            r for r in report.results if r.rule.severity == PolicySeverity.CRITICAL
        ]
        assert len(critical_results) > 0
        for r in critical_results:
            assert r.rule.severity == PolicySeverity.CRITICAL


# ===========================================================================
# 12. Category filtering in report
# ===========================================================================


class TestCategoryFiltering:
    def test_filter_results_by_category(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        security_results = [
            r for r in report.results if r.rule.category == PolicyCategory.SECURITY
        ]
        resilience_results = [
            r for r in report.results if r.rule.category == PolicyCategory.RESILIENCE
        ]
        assert len(security_results) > 0
        assert len(resilience_results) > 0

    def test_all_categories_covered(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        categories = {r.rule.category for r in report.results}
        # All 5 non-COST categories should be represented in built-in rules
        assert PolicyCategory.RESILIENCE in categories
        assert PolicyCategory.SECURITY in categories
        assert PolicyCategory.PERFORMANCE in categories
        assert PolicyCategory.OPERATIONAL in categories
        assert PolicyCategory.COMPLIANCE in categories


# ===========================================================================
# 13. Unknown condition handling
# ===========================================================================


class TestUnknownCondition:
    def test_unknown_condition_passes(self):
        engine = PolicyEngine()
        rule = PolicyRule(
            id="unknown",
            name="Unknown",
            description="",
            severity=PolicySeverity.INFO,
            category=PolicyCategory.COST,
            condition="some.unknown.condition == True",
            message_template="",
        )
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        result = engine.evaluate_rule(g, rule)
        assert result.passed is True
        assert result.components_checked == 0
        assert result.violations == []


# ===========================================================================
# 14. Register custom checker
# ===========================================================================


class TestRegisterChecker:
    def test_custom_checker(self):
        engine = PolicyEngine()

        def my_checker(graph, comp, rule):
            if comp.replicas < 5:
                return [
                    PolicyViolation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        component_id=comp.id,
                        component_name=comp.name,
                        message=f"{comp.name} has fewer than 5 replicas",
                        remediation="Add more replicas.",
                    )
                ]
            return []

        engine.register_checker("component.replicas >= 5", my_checker)
        rule = engine.create_custom_rule(
            id="min-5-replicas",
            name="Min 5 Replicas",
            description="Need 5+ replicas",
            condition="component.replicas >= 5",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.RESILIENCE,
        )
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER, replicas=2))
        result = engine.evaluate_rule(g, rule)
        assert not result.passed
        assert len(result.violations) == 1

    def test_custom_checker_pass(self):
        engine = PolicyEngine()

        def my_checker(graph, comp, rule):
            if comp.replicas < 5:
                return [
                    PolicyViolation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        component_id=comp.id,
                        component_name=comp.name,
                        message=f"{comp.name} has fewer than 5 replicas",
                        remediation="Add more replicas.",
                    )
                ]
            return []

        engine.register_checker("component.replicas >= 5", my_checker)
        rule = engine.create_custom_rule(
            id="min-5-replicas",
            name="Min 5 Replicas",
            description="Need 5+ replicas",
            condition="component.replicas >= 5",
            severity=PolicySeverity.ERROR,
            category=PolicyCategory.RESILIENCE,
        )
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER, replicas=5))
        result = engine.evaluate_rule(g, rule)
        assert result.passed


# ===========================================================================
# 15. Violations by severity aggregation
# ===========================================================================


class TestViolationsBySeverity:
    def test_multiple_severity_levels(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        # The simple graph should trigger violations at multiple severity levels
        assert len(report.violations_by_severity) >= 1

    def test_severity_keys_are_strings(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        for key in report.violations_by_severity.keys():
            assert isinstance(key, str)

    def test_severity_values_are_positive(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        for val in report.violations_by_severity.values():
            assert val > 0


# ===========================================================================
# 16. Components checked count
# ===========================================================================


class TestComponentsChecked:
    def test_single_component(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-in-transit")
        result = engine.evaluate_rule(g, rule)
        assert result.components_checked == 1

    def test_multiple_components(self):
        engine = PolicyEngine()
        g = _simple_graph()  # 2 components
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-in-transit")
        result = engine.evaluate_rule(g, rule)
        assert result.components_checked == 2

    def test_empty_graph(self):
        engine = PolicyEngine()
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-in-transit")
        result = engine.evaluate_rule(_empty_graph(), rule)
        assert result.components_checked == 0
        assert result.passed is True


# ===========================================================================
# 17. Overall pass/fail semantics
# ===========================================================================


class TestOverallPassFail:
    def test_overall_pass_when_all_pass(self):
        engine = PolicyEngine()
        # Use an empty policy set (no rules) => all pass trivially
        ps = PolicySet(name="empty", description="", version="1.0.0", rules=[])
        report = engine.evaluate(_simple_graph(), ps)
        assert report.overall_pass is True

    def test_overall_fail_when_any_fails(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        # simple_graph has many policy violations
        assert report.overall_pass is False

    def test_overall_pass_secure_subset(self):
        """Evaluate only encryption-in-transit on a component with TLS enabled."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                security=SecurityProfile(encryption_in_transit=True),
            )
        )
        ps = PolicySet(
            name="tls-only",
            description="",
            version="1.0.0",
            rules=[
                next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-in-transit"),
            ],
        )
        report = engine.evaluate(g, ps)
        assert report.overall_pass is True
        assert report.score == 100.0


# ===========================================================================
# 18. Violation message content
# ===========================================================================


class TestViolationMessages:
    def test_no_spof_message(self):
        engine = PolicyEngine()
        g = _simple_graph()
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "no-spof")
        result = engine.evaluate_rule(g, rule)
        for v in result.violations:
            assert "single point of failure" in v.message
            assert "replicas=" in v.message

    def test_encryption_message(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("db", ComponentType.DATABASE))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "encryption-at-rest")
        result = engine.evaluate_rule(g, rule)
        assert len(result.violations) == 1
        assert "encryption at rest" in result.violations[0].message

    def test_utilization_message_contains_percent(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(
            Component(
                id="app",
                name="app",
                type=ComponentType.APP_SERVER,
                metrics=ResourceMetrics(cpu_percent=90.0),
            )
        )
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "max-utilization")
        result = engine.evaluate_rule(g, rule)
        assert len(result.violations) == 1
        assert "90.0%" in result.violations[0].message

    def test_remediation_is_actionable(self):
        engine = PolicyEngine()
        report = engine.evaluate(_simple_graph())
        for result in report.results:
            for v in result.violations:
                # Remediation should contain action verbs
                assert len(v.remediation) > 10, f"Remediation for {v.rule_id} is too short"


# ===========================================================================
# 19. Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_graph_with_only_external_api(self):
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("ext", ComponentType.EXTERNAL_API))
        report = engine.evaluate(g)
        assert isinstance(report, PolicyReport)

    def test_graph_with_all_component_types(self):
        engine = PolicyEngine()
        g = InfraGraph()
        for ct in ComponentType:
            g.add_component(_make_component(ct.value, ct))
        report = engine.evaluate(g)
        assert report.total_rules == 15

    def test_multiple_violations_same_rule(self):
        """Multiple components can violate the same rule."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("db1", ComponentType.DATABASE, replicas=1))
        g.add_component(_make_component("db2", ComponentType.DATABASE, replicas=1))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "min-replicas")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed
        assert len(result.violations) == 2

    def test_dependency_depth_no_dependencies(self):
        """Graph with no dependencies should pass the depth check."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("a", ComponentType.APP_SERVER))
        g.add_component(_make_component("b", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "max-dependency-depth")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_circuit_breaker_no_deps(self):
        """Component with no dependencies should pass circuit breaker check."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "circuit-breaker")
        result = engine.evaluate_rule(g, rule)
        assert result.passed

    def test_multiple_external_deps_multiple_violations(self):
        """Component depending on two external APIs without CB triggers two violations."""
        engine = PolicyEngine()
        g = InfraGraph()
        g.add_component(_make_component("app", ComponentType.APP_SERVER))
        g.add_component(_make_component("ext1", ComponentType.EXTERNAL_API))
        g.add_component(_make_component("ext2", ComponentType.EXTERNAL_API))
        g.add_dependency(Dependency(source_id="app", target_id="ext1"))
        g.add_dependency(Dependency(source_id="app", target_id="ext2"))
        rule = next(r for r in engine.get_builtin_policies().rules if r.id == "circuit-breaker")
        result = engine.evaluate_rule(g, rule)
        assert not result.passed
        assert len(result.violations) == 2


# ===========================================================================
# 20. _safe_getattr helper
# ===========================================================================


class TestSafeGetattr:
    def test_simple_attr(self):
        from faultray.policy.engine import _safe_getattr

        comp = _make_component("app", ComponentType.APP_SERVER, replicas=3)
        assert _safe_getattr(comp, "replicas") == 3

    def test_nested_attr(self):
        from faultray.policy.engine import _safe_getattr

        comp = Component(
            id="app",
            name="app",
            type=ComponentType.APP_SERVER,
            failover=FailoverConfig(enabled=True),
        )
        assert _safe_getattr(comp, "failover.enabled") is True

    def test_missing_attr(self):
        from faultray.policy.engine import _safe_getattr

        comp = _make_component("app", ComponentType.APP_SERVER)
        assert _safe_getattr(comp, "nonexistent.attr") is None

    def test_missing_attr_with_default(self):
        from faultray.policy.engine import _safe_getattr

        comp = _make_component("app", ComponentType.APP_SERVER)
        assert _safe_getattr(comp, "nonexistent", "fallback") == "fallback"

    def test_deep_nested(self):
        from faultray.policy.engine import _safe_getattr

        comp = Component(
            id="app",
            name="app",
            type=ComponentType.APP_SERVER,
            security=SecurityProfile(encryption_at_rest=True),
        )
        assert _safe_getattr(comp, "security.encryption_at_rest") is True
