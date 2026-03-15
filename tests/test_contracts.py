"""Tests for Resilience Contracts engine."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from infrasim.contracts.engine import (
    ContractEngine,
    ContractRule,
    ContractValidationResult,
    ContractViolation,
    ResilienceContract,
    _count_spofs,
)
from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
)
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_graph() -> InfraGraph:
    """Build a simple 3-component graph: LB -> App -> DB."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=1,
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
    ))
    return graph


def _resilient_graph() -> InfraGraph:
    """Build a well-configured resilient graph."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LB", type=ComponentType.LOAD_BALANCER, replicas=2,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=4),
    ))
    graph.add_component(Component(
        id="app", name="App", type=ComponentType.APP_SERVER, replicas=3,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=6),
    ))
    graph.add_component(Component(
        id="db", name="DB", type=ComponentType.DATABASE, replicas=2,
        failover=FailoverConfig(enabled=True, health_check_interval_seconds=5),
    ))
    graph.add_dependency(Dependency(
        source_id="lb", target_id="app", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    graph.add_dependency(Dependency(
        source_id="app", target_id="db", dependency_type="requires",
        circuit_breaker=CircuitBreakerConfig(enabled=True),
    ))
    return graph


def _write_yaml(data: dict, tmp_path: Path) -> Path:
    """Write a dict as YAML to a temp file and return the path."""
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# ContractRule tests
# ---------------------------------------------------------------------------

class TestContractRule:
    def test_valid_rule(self):
        rule = ContractRule(
            rule_type="min_score",
            target=None,
            operator=">=",
            value=75,
            description="Score >= 75",
        )
        assert rule.rule_type == "min_score"
        assert rule.severity == "error"

    def test_invalid_rule_type(self):
        with pytest.raises(ValueError, match="Unknown rule_type"):
            ContractRule(
                rule_type="nonexistent",
                target=None,
                operator=">=",
                value=0,
                description="bad",
            )

    def test_invalid_operator(self):
        with pytest.raises(ValueError, match="Unknown operator"):
            ContractRule(
                rule_type="min_score",
                target=None,
                operator="~=",
                value=0,
                description="bad",
            )

    def test_invalid_severity(self):
        with pytest.raises(ValueError, match="Unknown severity"):
            ContractRule(
                rule_type="min_score",
                target=None,
                operator=">=",
                value=0,
                description="bad",
                severity="fatal",
            )


# ---------------------------------------------------------------------------
# ContractEngine - load / save
# ---------------------------------------------------------------------------

class TestContractLoadSave:
    def test_load_contract(self, tmp_path):
        data = {
            "name": "Test Contract",
            "version": "2.0",
            "description": "A test contract",
            "metadata": {"author": "Test"},
            "rules": [
                {
                    "type": "min_score",
                    "value": 75,
                    "severity": "error",
                    "description": "Score >= 75",
                },
                {
                    "type": "max_spof",
                    "value": 0,
                    "severity": "error",
                    "description": "No SPOFs",
                },
            ],
        }
        path = _write_yaml(data, tmp_path)
        engine = ContractEngine()
        contract = engine.load_contract(path)

        assert contract.name == "Test Contract"
        assert contract.version == "2.0"
        assert len(contract.rules) == 2
        assert contract.rules[0].rule_type == "min_score"
        assert contract.rules[0].operator == ">="  # default for min_score
        assert contract.rules[1].rule_type == "max_spof"
        assert contract.rules[1].operator == "<="  # default for max_spof

    def test_load_nonexistent(self):
        engine = ContractEngine()
        with pytest.raises(FileNotFoundError):
            engine.load_contract(Path("/nonexistent/contract.yaml"))

    def test_save_and_reload(self, tmp_path):
        contract = ResilienceContract(
            name="Save Test",
            version="1.0",
            description="test",
            rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=80,
                    description="Score >= 80",
                ),
            ],
            metadata={"author": "test"},
        )
        engine = ContractEngine()
        path = tmp_path / "out.yaml"
        engine.save_contract(contract, path)

        assert path.exists()
        loaded = engine.load_contract(path)
        assert loaded.name == "Save Test"
        assert len(loaded.rules) == 1
        assert loaded.rules[0].value == 80

    def test_load_invalid_yaml(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("- just a list", encoding="utf-8")
        engine = ContractEngine()
        with pytest.raises(ValueError, match="Expected YAML mapping"):
            engine.load_contract(path)

    def test_load_missing_type(self, tmp_path):
        data = {"rules": [{"value": 10}]}
        path = _write_yaml(data, tmp_path)
        engine = ContractEngine()
        with pytest.raises(ValueError, match="missing 'type'"):
            engine.load_contract(path)


# ---------------------------------------------------------------------------
# ContractEngine - validate
# ---------------------------------------------------------------------------

class TestContractValidate:
    def test_validate_pass(self):
        graph = _resilient_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Lenient",
            version="1.0",
            description="lenient",
            rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=0,
                    description="Score >= 0",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is True
        assert result.score == 100.0
        assert len(result.violations) == 0

    def test_validate_min_score_fail(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Strict Score",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=999,
                    description="Impossible score",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is False
        assert len(result.violations) == 1
        assert "Resilience score" in result.violations[0].message

    def test_validate_max_spof(self):
        graph = _simple_graph()
        engine = ContractEngine()

        # DB is a SPOF (1 replica, has dependents, no failover)
        contract = ResilienceContract(
            name="No SPOFs",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="max_spof",
                    target=None,
                    operator="<=",
                    value=0,
                    description="No SPOFs allowed",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is False
        assert any("SPOF" in v.message for v in result.violations)

    def test_validate_min_replicas(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Replicas",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="min_replicas",
                    target="database",
                    operator=">=",
                    value=2,
                    description="DB replicas >= 2",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is False
        assert any("db" in v.component_id for v in result.violations)

    def test_validate_min_replicas_pass(self):
        graph = _resilient_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Replicas OK",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="min_replicas",
                    target="database",
                    operator=">=",
                    value=2,
                    description="DB replicas >= 2",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is True

    def test_validate_required_pattern_circuit_breaker(self):
        graph = _simple_graph()  # no CBs
        engine = ContractEngine()
        contract = ResilienceContract(
            name="CB Required",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="required_pattern",
                    target="*",
                    operator=">=",
                    value="circuit_breaker",
                    description="CBs required",
                    severity="warning",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        # warnings, not errors
        assert result.passed is True  # warnings don't block
        assert len(result.warnings) > 0

    def test_validate_max_blast_radius(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Blast Radius",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="max_blast_radius",
                    target=None,
                    operator="<=",
                    value=0.0,  # impossible - DB failure cascades
                    description="Zero blast radius",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        # The DB failure should cascade to app and lb, so blast_radius > 0
        assert result.passed is False

    def test_validate_max_dependency_depth(self):
        graph = _simple_graph()  # depth = 3 (lb->app->db)
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Depth",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="max_dependency_depth",
                    target=None,
                    operator="<=",
                    value=2,
                    description="Max depth 2",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is False

    def test_validate_sla_target(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="SLA",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="sla_target",
                    target=None,
                    operator=">=",
                    value=99.999,  # very high - likely fails
                    description="Five nines",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is False

    def test_validate_warnings_dont_block(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Warning Only",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="max_spof",
                    target=None,
                    operator="<=",
                    value=0,
                    description="No SPOFs",
                    severity="warning",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is True
        assert len(result.warnings) > 0

    def test_validate_compliance_score(self):
        graph = _simple_graph()
        engine = ContractEngine()
        # 2 rules, 1 will fail
        contract = ResilienceContract(
            name="Mixed",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=0,
                    description="Always passes",
                ),
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=999,
                    description="Always fails",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.score == 50.0  # 1/2 passed

    def test_validate_to_dict(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Dict Test",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=0,
                    description="ok",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        d = result.to_dict()
        assert d["contract_name"] == "Dict Test"
        assert d["passed"] is True
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# ContractEngine - generate
# ---------------------------------------------------------------------------

class TestContractGenerate:
    def test_generate_standard(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = engine.generate_default_contract(graph, strictness="standard")
        assert contract.name == "Auto-Generated Resilience Contract"
        assert len(contract.rules) > 0
        assert contract.metadata.get("strictness") == "standard"

    def test_generate_strict(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = engine.generate_default_contract(graph, strictness="strict")
        # Strict should have more rules (e.g. required_pattern)
        rule_types = {r.rule_type for r in contract.rules}
        assert "required_pattern" in rule_types

    def test_generate_relaxed(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = engine.generate_default_contract(graph, strictness="relaxed")
        # Relaxed should have looser thresholds
        min_score_rule = next(
            (r for r in contract.rules if r.rule_type == "min_score"), None,
        )
        assert min_score_rule is not None
        # Relaxed threshold = current - 10 (so it should be lower)
        strict_contract = engine.generate_default_contract(graph, strictness="strict")
        strict_score = next(r for r in strict_contract.rules if r.rule_type == "min_score")
        assert min_score_rule.value <= strict_score.value

    def test_generate_validates_own_infrastructure(self):
        """Generated standard contract should ideally pass on the graph it was generated from."""
        graph = _resilient_graph()
        engine = ContractEngine()
        contract = engine.generate_default_contract(graph, strictness="relaxed")
        result = engine.validate(graph, contract)
        # With relaxed strictness and a resilient graph, it should pass
        assert result.passed is True


# ---------------------------------------------------------------------------
# ContractEngine - diff
# ---------------------------------------------------------------------------

class TestContractDiff:
    def test_diff_identical(self):
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Same",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=75,
                    description="Score",
                ),
            ],
        )
        changes = engine.diff_contracts(contract, contract)
        assert changes == ["No differences found."]

    def test_diff_name_change(self):
        engine = ContractEngine()
        old = ResilienceContract(name="Old", version="1.0", description="", rules=[])
        new = ResilienceContract(name="New", version="1.0", description="", rules=[])
        changes = engine.diff_contracts(old, new)
        assert any("Name changed" in c for c in changes)

    def test_diff_version_change(self):
        engine = ContractEngine()
        old = ResilienceContract(name="C", version="1.0", description="", rules=[])
        new = ResilienceContract(name="C", version="2.0", description="", rules=[])
        changes = engine.diff_contracts(old, new)
        assert any("Version changed" in c for c in changes)

    def test_diff_added_rule(self):
        engine = ContractEngine()
        old = ResilienceContract(name="C", version="1.0", description="", rules=[])
        new = ResilienceContract(
            name="C", version="1.0", description="", rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=75,
                    description="Score",
                ),
            ],
        )
        changes = engine.diff_contracts(old, new)
        assert any("Added rule" in c for c in changes)

    def test_diff_removed_rule(self):
        engine = ContractEngine()
        old = ResilienceContract(
            name="C", version="1.0", description="", rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=75,
                    description="Score",
                ),
            ],
        )
        new = ResilienceContract(name="C", version="1.0", description="", rules=[])
        changes = engine.diff_contracts(old, new)
        assert any("Removed rule" in c for c in changes)

    def test_diff_value_change(self):
        engine = ContractEngine()
        old = ResilienceContract(
            name="C", version="1.0", description="", rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=50,
                    description="Score",
                ),
            ],
        )
        new = ResilienceContract(
            name="C", version="1.0", description="", rules=[
                ContractRule(
                    rule_type="min_score",
                    target=None,
                    operator=">=",
                    value=75,
                    description="Score",
                ),
            ],
        )
        changes = engine.diff_contracts(old, new)
        assert any("value 50 -> 75" in c for c in changes)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_count_spofs_simple(self):
        graph = _simple_graph()
        count = _count_spofs(graph)
        # DB has 1 replica, has dependents (app), no failover => SPOF
        # App has 3 replicas => not a SPOF
        # LB has 2 replicas => not a SPOF
        assert count >= 1

    def test_count_spofs_resilient(self):
        graph = _resilient_graph()
        count = _count_spofs(graph)
        assert count == 0


# ---------------------------------------------------------------------------
# Required failover / health check rules
# ---------------------------------------------------------------------------

class TestAdvancedRules:
    def test_required_failover_fail(self):
        graph = _simple_graph()  # no failover on any component
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Failover",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="required_failover",
                    target="database",
                    operator=">=",
                    value=True,
                    description="DB must have failover",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is False

    def test_required_failover_pass(self):
        graph = _resilient_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Failover",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="required_failover",
                    target="database",
                    operator=">=",
                    value=True,
                    description="DB must have failover",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is True

    def test_required_health_check_fail(self):
        graph = _simple_graph()  # no health checks
        engine = ContractEngine()
        contract = ResilienceContract(
            name="HC",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="required_health_check",
                    target="*",
                    operator=">=",
                    value=True,
                    description="All components must have health checks",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is False

    def test_max_critical_findings(self):
        graph = _simple_graph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Critical",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="max_critical_findings",
                    target=None,
                    operator="<=",
                    value=0,
                    description="No critical findings",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        # simple_graph has SPOFs, so it should fail
        assert result.passed is False

    def test_empty_graph_passes_all(self):
        """An empty graph should trivially pass most rules."""
        graph = InfraGraph()
        engine = ContractEngine()
        contract = ResilienceContract(
            name="Empty",
            version="1.0",
            description="",
            rules=[
                ContractRule(
                    rule_type="max_spof", target=None, operator="<=",
                    value=0, description="",
                ),
                ContractRule(
                    rule_type="max_blast_radius", target=None, operator="<=",
                    value=0.3, description="",
                ),
                ContractRule(
                    rule_type="max_dependency_depth", target=None, operator="<=",
                    value=4, description="",
                ),
            ],
        )
        result = engine.validate(graph, contract)
        assert result.passed is True


# ---------------------------------------------------------------------------
# YAML round-trip integration test
# ---------------------------------------------------------------------------

class TestYAMLRoundTrip:
    def test_full_contract_yaml_roundtrip(self, tmp_path):
        """Load a contract YAML, validate, and verify the full pipeline."""
        contract_data = {
            "name": "Production API Resilience Contract",
            "version": "1.0",
            "description": "Minimum resilience requirements for production API",
            "metadata": {
                "author": "SRE Team",
                "team": "platform",
            },
            "rules": [
                {
                    "type": "min_score",
                    "value": 50,
                    "severity": "error",
                    "description": "Resilience score must be at least 50",
                },
                {
                    "type": "max_spof",
                    "value": 2,
                    "severity": "warning",
                    "description": "Tolerate up to 2 SPOFs",
                },
                {
                    "type": "min_replicas",
                    "target": "database",
                    "value": 1,
                    "severity": "error",
                    "description": "Databases must have at least 1 replica",
                },
                {
                    "type": "max_dependency_depth",
                    "value": 5,
                    "severity": "warning",
                    "description": "Dependency chains should not exceed 5",
                },
            ],
        }
        path = _write_yaml(contract_data, tmp_path)
        engine = ContractEngine()
        contract = engine.load_contract(path)

        graph = _simple_graph()
        result = engine.validate(graph, contract)

        # With lenient rules, simple graph should pass
        assert result.contract.name == "Production API Resilience Contract"
        assert isinstance(result.score, float)
        assert 0 <= result.score <= 100

        # Save and reload
        out = tmp_path / "output.yaml"
        engine.save_contract(contract, out)
        reloaded = engine.load_contract(out)
        assert reloaded.name == contract.name
        assert len(reloaded.rules) == len(contract.rules)
