"""Tests for Custom Scoring Engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.scoring import (
    CustomScoringEngine,
    CustomScoringResult,
    ScoringRule,
    _check_backup_coverage,
    _check_cb_coverage,
    _check_encryption_coverage,
    _check_failover_coverage,
    _check_max_chain_depth,
    _check_max_utilization,
    _check_min_replicas,
    _check_no_public_database,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_graph(*components, dependencies=None) -> InfraGraph:
    """Build an InfraGraph from component kwargs."""
    graph = InfraGraph()
    for comp in components:
        graph.add_component(comp)
    for dep in (dependencies or []):
        graph.add_dependency(dep)
    return graph


def _make_component(
    comp_id: str,
    comp_type: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    failover: bool = False,
    encryption: bool = False,
    backup: bool = False,
    port: int = 0,
    cpu_percent: float = 0.0,
) -> Component:
    """Build a Component with common test parameters."""
    return Component(
        id=comp_id,
        name=comp_id,
        type=comp_type,
        replicas=replicas,
        port=port,
        failover=FailoverConfig(enabled=failover),
        security=SecurityProfile(
            encryption_at_rest=encryption,
            backup_enabled=backup,
        ),
        metrics=ResourceMetrics(cpu_percent=cpu_percent),
    )


# ===================================================================
# Built-in check functions
# ===================================================================


class TestMinReplicas:
    """Tests for _check_min_replicas()."""

    def test_all_databases_replicated(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, replicas=3),
            _make_component("db2", ComponentType.DATABASE, replicas=2),
        )
        score = _check_min_replicas(graph, {"component_type": "database", "min": 2})
        assert score == 100.0

    def test_some_databases_not_replicated(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, replicas=3),
            _make_component("db2", ComponentType.DATABASE, replicas=1),
        )
        score = _check_min_replicas(graph, {"component_type": "database", "min": 2})
        assert score == 50.0  # 1 of 2 passes

    def test_no_databases_returns_100(self):
        graph = _make_graph(
            _make_component("app1", ComponentType.APP_SERVER, replicas=1),
        )
        score = _check_min_replicas(graph, {"component_type": "database", "min": 2})
        assert score == 100.0

    def test_empty_graph(self):
        graph = InfraGraph()
        score = _check_min_replicas(graph, {"component_type": "database", "min": 2})
        assert score == 100.0


class TestMaxUtilization:
    """Tests for _check_max_utilization()."""

    def test_all_under_threshold(self):
        graph = _make_graph(
            _make_component("app1", cpu_percent=50.0),
            _make_component("app2", cpu_percent=60.0),
        )
        score = _check_max_utilization(graph, {"max_percent": 80})
        assert score == 100.0

    def test_some_over_threshold(self):
        graph = _make_graph(
            _make_component("app1", cpu_percent=50.0),
            _make_component("app2", cpu_percent=90.0),
        )
        score = _check_max_utilization(graph, {"max_percent": 80})
        assert score == 50.0  # 1 of 2 passes

    def test_empty_graph(self):
        graph = InfraGraph()
        score = _check_max_utilization(graph, {"max_percent": 80})
        assert score == 100.0


class TestEncryptionCoverage:
    """Tests for _check_encryption_coverage()."""

    def test_all_encrypted(self):
        graph = _make_graph(
            _make_component("app1", encryption=True),
            _make_component("app2", encryption=True),
        )
        score = _check_encryption_coverage(graph, {"min_percent": 100})
        assert score == 100.0

    def test_half_encrypted(self):
        graph = _make_graph(
            _make_component("app1", encryption=True),
            _make_component("app2", encryption=False),
        )
        score = _check_encryption_coverage(graph, {"min_percent": 100})
        assert score == 50.0

    def test_none_encrypted(self):
        graph = _make_graph(
            _make_component("app1", encryption=False),
        )
        score = _check_encryption_coverage(graph, {"min_percent": 100})
        assert score == 0.0


class TestFailoverCoverage:
    """Tests for _check_failover_coverage()."""

    def test_all_with_failover(self):
        graph = _make_graph(
            _make_component("app1", failover=True),
            _make_component("app2", failover=True),
        )
        score = _check_failover_coverage(graph, {"min_percent": 100})
        assert score == 100.0

    def test_none_with_failover(self):
        graph = _make_graph(
            _make_component("app1", failover=False),
        )
        score = _check_failover_coverage(graph, {"min_percent": 100})
        assert score == 0.0


class TestCBCoverage:
    """Tests for _check_cb_coverage()."""

    def test_all_edges_with_cb(self):
        graph = _make_graph(
            _make_component("app1"),
            _make_component("db1", ComponentType.DATABASE),
            dependencies=[
                Dependency(
                    source_id="app1", target_id="db1",
                    circuit_breaker=CircuitBreakerConfig(enabled=True),
                ),
            ],
        )
        score = _check_cb_coverage(graph, {"min_percent": 100})
        assert score == 100.0

    def test_no_edges_returns_100(self):
        graph = _make_graph(_make_component("app1"))
        score = _check_cb_coverage(graph, {"min_percent": 100})
        assert score == 100.0

    def test_no_cb_on_edges(self):
        graph = _make_graph(
            _make_component("app1"),
            _make_component("db1", ComponentType.DATABASE),
            dependencies=[
                Dependency(source_id="app1", target_id="db1"),
            ],
        )
        score = _check_cb_coverage(graph, {"min_percent": 100})
        assert score == 0.0


class TestBackupCoverage:
    """Tests for _check_backup_coverage()."""

    def test_all_with_backup(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, backup=True),
            _make_component("db2", ComponentType.DATABASE, backup=True),
        )
        score = _check_backup_coverage(
            graph, {"component_type": "database", "min_percent": 100}
        )
        assert score == 100.0

    def test_none_with_backup(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, backup=False),
        )
        score = _check_backup_coverage(
            graph, {"component_type": "database", "min_percent": 100}
        )
        assert score == 0.0


class TestMaxChainDepth:
    """Tests for _check_max_chain_depth()."""

    def test_shallow_chain(self):
        graph = _make_graph(
            _make_component("lb", ComponentType.LOAD_BALANCER),
            _make_component("app", ComponentType.APP_SERVER),
            dependencies=[
                Dependency(source_id="lb", target_id="app"),
            ],
        )
        score = _check_max_chain_depth(graph, {"max_depth": 5})
        assert score == 100.0

    def test_empty_graph(self):
        graph = InfraGraph()
        score = _check_max_chain_depth(graph, {"max_depth": 5})
        assert score == 100.0


class TestNoPublicDatabase:
    """Tests for _check_no_public_database()."""

    def test_db_on_standard_port(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, port=5432),
        )
        score = _check_no_public_database(graph, {})
        assert score == 100.0  # 5432 not in default forbidden list

    def test_db_on_public_port(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, port=443),
        )
        score = _check_no_public_database(graph, {})
        assert score == 0.0

    def test_no_databases(self):
        graph = _make_graph(_make_component("app1"))
        score = _check_no_public_database(graph, {})
        assert score == 100.0


# ===================================================================
# CustomScoringEngine
# ===================================================================


class TestCustomScoringEngine:
    """Tests for CustomScoringEngine."""

    def test_evaluate_all_pass(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, replicas=3, encryption=True),
        )
        rules = [
            ScoringRule(
                name="DB Replicas",
                description="DBs must have >= 2 replicas",
                check_fn="min_replicas",
                params={"component_type": "database", "min": 2},
                weight=1.0,
            ),
            ScoringRule(
                name="Encryption",
                description="All components encrypted",
                check_fn="encryption_coverage",
                params={"min_percent": 100},
                weight=1.0,
            ),
        ]
        engine = CustomScoringEngine(graph, rules)
        result = engine.evaluate()

        assert isinstance(result, CustomScoringResult)
        assert result.total_score == 100.0
        assert len(result.rules) == 2
        assert all(r["passed"] for r in result.rules)

    def test_evaluate_partial_pass(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, replicas=1),
        )
        rules = [
            ScoringRule(
                name="DB Replicas",
                description="DBs must have >= 2 replicas",
                check_fn="min_replicas",
                params={"component_type": "database", "min": 2},
                weight=2.0,
            ),
        ]
        engine = CustomScoringEngine(graph, rules)
        result = engine.evaluate()

        assert result.total_score == 0.0
        assert result.rules[0]["passed"] is False

    def test_weighted_scoring(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, replicas=3, encryption=True),
            _make_component("db2", ComponentType.DATABASE, replicas=1, encryption=True),
        )
        rules = [
            ScoringRule(
                name="DB Replicas",
                description="",
                check_fn="min_replicas",
                params={"component_type": "database", "min": 2},
                weight=2.0,
            ),
            ScoringRule(
                name="Encryption",
                description="",
                check_fn="encryption_coverage",
                params={"min_percent": 100},
                weight=1.0,
            ),
        ]
        engine = CustomScoringEngine(graph, rules)
        result = engine.evaluate()

        # min_replicas: 1/2 = 50.0 (weight 2)
        # encryption: 2/2 = 100.0 (weight 1)
        # weighted = (50*2 + 100*1) / 3 = 66.67
        expected = (50.0 * 2 + 100.0 * 1) / 3
        assert abs(result.weighted_score - round(expected, 1)) < 0.2

    def test_unknown_check_function(self):
        graph = _make_graph(_make_component("app1"))
        rules = [
            ScoringRule(
                name="Bad Rule",
                description="",
                check_fn="nonexistent_check",
                weight=1.0,
            ),
        ]
        engine = CustomScoringEngine(graph, rules)
        result = engine.evaluate()

        assert len(result.rules) == 1
        assert "error" in result.rules[0]
        assert result.rules[0]["score"] == 0.0

    def test_empty_rules(self):
        graph = _make_graph(_make_component("app1"))
        engine = CustomScoringEngine(graph, rules=[])
        result = engine.evaluate()

        assert result.total_score == 0.0
        assert result.rules == []


# ===================================================================
# CustomScoringEngine.from_yaml
# ===================================================================


class TestFromYaml:
    """Tests for from_yaml()."""

    def test_load_valid_yaml(self, tmp_path):
        yaml_content = """
model_name: "test-policy"
rules:
  - name: "All databases replicated"
    check: min_replicas
    params:
      component_type: database
      min: 2
    weight: 2.0
    description: "Databases must have at least 2 replicas"
  - name: "No high utilization"
    check: max_utilization
    params:
      max_percent: 80
    weight: 1.0
  - name: "Full encryption"
    check: encryption_coverage
    params:
      min_percent: 100
    weight: 1.5
"""
        config_path = tmp_path / "scoring-policy.yaml"
        config_path.write_text(yaml_content)

        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, replicas=3, encryption=True),
        )
        engine = CustomScoringEngine.from_yaml(graph, config_path)

        assert engine.model_name == "test-policy"
        assert len(engine.rules) == 3
        assert engine.rules[0].name == "All databases replicated"
        assert engine.rules[0].weight == 2.0
        assert engine.rules[0].check_fn == "min_replicas"
        assert engine.rules[0].params["component_type"] == "database"

    def test_missing_check_field_raises(self, tmp_path):
        yaml_content = """
rules:
  - name: "Bad rule"
    weight: 1.0
"""
        config_path = tmp_path / "bad-policy.yaml"
        config_path.write_text(yaml_content)

        graph = _make_graph(_make_component("app1"))
        with pytest.raises(ValueError, match="missing 'check'"):
            CustomScoringEngine.from_yaml(graph, config_path)

    def test_yaml_evaluate_integration(self, tmp_path):
        yaml_content = """
rules:
  - name: "Backup coverage"
    check: backup_coverage
    params:
      component_type: database
      min_percent: 100
    weight: 1.0
"""
        config_path = tmp_path / "policy.yaml"
        config_path.write_text(yaml_content)

        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, backup=True),
            _make_component("db2", ComponentType.DATABASE, backup=True),
        )
        engine = CustomScoringEngine.from_yaml(graph, config_path)
        result = engine.evaluate()

        assert result.total_score == 100.0
        assert result.rules[0]["passed"] is True

    def test_invalid_yaml_top_level(self, tmp_path):
        yaml_content = "- just a list"
        config_path = tmp_path / "invalid.yaml"
        config_path.write_text(yaml_content)

        graph = _make_graph(_make_component("app1"))
        with pytest.raises(ValueError, match="Expected YAML mapping"):
            CustomScoringEngine.from_yaml(graph, config_path)

    def test_invalid_rules_not_list(self, tmp_path):
        yaml_content = """
rules: "not a list"
"""
        config_path = tmp_path / "bad.yaml"
        config_path.write_text(yaml_content)

        graph = _make_graph(_make_component("app1"))
        with pytest.raises(ValueError, match="'rules' must be a list"):
            CustomScoringEngine.from_yaml(graph, config_path)

    def test_invalid_rule_entry_not_dict(self, tmp_path):
        yaml_content = """
rules:
  - "just a string"
"""
        config_path = tmp_path / "bad.yaml"
        config_path.write_text(yaml_content)

        graph = _make_graph(_make_component("app1"))
        with pytest.raises(ValueError, match="must be a mapping"):
            CustomScoringEngine.from_yaml(graph, config_path)

    def test_model_name_defaults_to_filename(self, tmp_path):
        yaml_content = """
rules:
  - name: "test"
    check: min_replicas
    params: {component_type: database, min: 1}
"""
        config_path = tmp_path / "my-policy.yaml"
        config_path.write_text(yaml_content)

        graph = _make_graph(_make_component("app1"))
        engine = CustomScoringEngine.from_yaml(graph, config_path)
        assert engine.model_name == "my-policy"


# ===================================================================
# Additional edge case tests for built-in checks
# ===================================================================


class TestFilterComponentsByType:
    """Tests for _filter_components_by_type helper."""

    def test_unknown_type_returns_empty(self):
        from faultray.scoring import _filter_components_by_type
        graph = _make_graph(_make_component("app1"))
        result = _filter_components_by_type(graph, "nonexistent_type")
        assert result == []

    def test_empty_type_returns_all(self):
        from faultray.scoring import _filter_components_by_type
        graph = _make_graph(
            _make_component("app1"),
            _make_component("db1", ComponentType.DATABASE),
        )
        result = _filter_components_by_type(graph, "")
        assert len(result) == 2


class TestMinReplicasExtended:
    def test_empty_type_checks_all_components(self):
        graph = _make_graph(
            _make_component("app1", replicas=3),
            _make_component("db1", ComponentType.DATABASE, replicas=1),
        )
        score = _check_min_replicas(graph, {"component_type": "", "min": 2})
        assert score == 50.0  # 1/2 passes


class TestEncryptionCoverageExtended:
    def test_zero_min_percent(self):
        graph = _make_graph(_make_component("app1", encryption=False))
        score = _check_encryption_coverage(graph, {"min_percent": 0})
        assert score == 100.0

    def test_empty_graph(self):
        graph = InfraGraph()
        score = _check_encryption_coverage(graph, {"min_percent": 100})
        assert score == 100.0


class TestFailoverCoverageExtended:
    def test_empty_graph(self):
        graph = InfraGraph()
        score = _check_failover_coverage(graph, {"min_percent": 100})
        assert score == 100.0

    def test_zero_min_percent(self):
        graph = _make_graph(_make_component("app1", failover=False))
        score = _check_failover_coverage(graph, {"min_percent": 0})
        assert score == 100.0


class TestCBCoverageExtended:
    def test_zero_min_percent(self):
        graph = _make_graph(
            _make_component("app1"),
            _make_component("db1", ComponentType.DATABASE),
            dependencies=[Dependency(source_id="app1", target_id="db1")],
        )
        score = _check_cb_coverage(graph, {"min_percent": 0})
        assert score == 100.0


class TestBackupCoverageExtended:
    def test_no_type_filter_checks_all(self):
        graph = _make_graph(
            _make_component("app1", backup=True),
            _make_component("db1", ComponentType.DATABASE, backup=False),
        )
        score = _check_backup_coverage(graph, {"min_percent": 100})
        assert score == 50.0

    def test_zero_min_percent(self):
        graph = _make_graph(_make_component("app1", backup=False))
        score = _check_backup_coverage(graph, {"min_percent": 0})
        assert score == 100.0

    def test_empty_graph(self):
        graph = InfraGraph()
        score = _check_backup_coverage(graph, {"min_percent": 100})
        assert score == 100.0


class TestMaxChainDepthExtended:
    def test_deep_chain(self):
        graph = _make_graph(
            _make_component("a", ComponentType.LOAD_BALANCER),
            _make_component("b", ComponentType.APP_SERVER),
            _make_component("c", ComponentType.APP_SERVER),
            _make_component("d", ComponentType.DATABASE),
            dependencies=[
                Dependency(source_id="a", target_id="b"),
                Dependency(source_id="b", target_id="c"),
                Dependency(source_id="c", target_id="d"),
            ],
        )
        # Chain depth of 4, max_depth=2 -> over by 2 -> 100 - 2*20 = 60
        score = _check_max_chain_depth(graph, {"max_depth": 2})
        assert score <= 60.0


class TestNoPublicDatabaseExtended:
    def test_custom_forbidden_ports_as_string(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, port=3306),
        )
        score = _check_no_public_database(graph, {"forbidden_ports": "3306,5432"})
        assert score == 0.0

    def test_multiple_dbs_some_violating(self):
        graph = _make_graph(
            _make_component("db1", ComponentType.DATABASE, port=5432),
            _make_component("db2", ComponentType.DATABASE, port=443),
        )
        score = _check_no_public_database(graph, {})
        assert score == 50.0  # 1 of 2 violating


class TestCustomScoringEngineExtended:
    def test_evaluate_with_exception_in_check(self):
        """Check function that raises should score 0."""
        graph = _make_graph(_make_component("app1"))
        rules = [
            ScoringRule(
                name="Test",
                description="desc",
                check_fn="max_chain_depth",
                weight=1.0,
                params={"max_depth": "not_a_number"},  # will cause int() to fail
            ),
        ]
        engine = CustomScoringEngine(graph, rules)
        result = engine.evaluate()
        # The check should fail gracefully with score 0
        assert result.rules[0]["score"] == 0.0
