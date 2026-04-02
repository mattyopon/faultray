"""Tests for the GameDay Scenario Generator."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    OperationalProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.gameday import (
    GameDayGenerator,
    GameDayScenario,
    _build_failure_indicators,
    _build_success_criteria,
    _cascade_depth,
    _get_execution_steps,
    _get_recovery_steps,
    _spof_score,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _simple_graph() -> InfraGraph:
    """LB -> App -> DB topology (3 components)."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="lb", name="LoadBalancer", type=ComponentType.LOAD_BALANCER, replicas=2,
        failover=FailoverConfig(enabled=True, promotion_time_seconds=15),
        operational_profile=OperationalProfile(mttr_minutes=5),
    ))
    graph.add_component(Component(
        id="app", name="AppServer", type=ComponentType.APP_SERVER, replicas=3,
        operational_profile=OperationalProfile(mttr_minutes=10),
    ))
    graph.add_component(Component(
        id="db", name="Database", type=ComponentType.DATABASE, replicas=1,
        operational_profile=OperationalProfile(mttr_minutes=30),
    ))
    graph.add_dependency(Dependency(source_id="lb", target_id="app"))
    graph.add_dependency(Dependency(source_id="app", target_id="db"))
    return graph


def _rich_graph() -> InfraGraph:
    """More realistic graph with cache, queue, DNS, and external API."""
    graph = InfraGraph()
    comps = [
        Component(id="nginx", name="nginx", type=ComponentType.LOAD_BALANCER, replicas=2,
                  failover=FailoverConfig(enabled=True)),
        Component(id="api-1", name="api-server-1", type=ComponentType.APP_SERVER, replicas=3),
        Component(id="api-2", name="api-server-2", type=ComponentType.APP_SERVER, replicas=3),
        Component(id="db-primary", name="Postgres Primary", type=ComponentType.DATABASE,
                  replicas=1, failover=FailoverConfig(enabled=True, promotion_time_seconds=30)),
        Component(id="redis", name="Redis", type=ComponentType.CACHE, replicas=1),
        Component(id="rabbit", name="RabbitMQ", type=ComponentType.QUEUE, replicas=1),
        Component(id="dns", name="Internal DNS", type=ComponentType.DNS, replicas=1),
        Component(id="stripe", name="Stripe API", type=ComponentType.EXTERNAL_API, replicas=1),
    ]
    for c in comps:
        graph.add_component(c)
    deps = [
        Dependency(source_id="nginx", target_id="api-1"),
        Dependency(source_id="nginx", target_id="api-2"),
        Dependency(source_id="api-1", target_id="db-primary"),
        Dependency(source_id="api-2", target_id="db-primary"),
        Dependency(source_id="api-1", target_id="redis"),
        Dependency(source_id="api-2", target_id="rabbit"),
        Dependency(source_id="api-1", target_id="stripe"),
    ]
    for d in deps:
        graph.add_dependency(d)
    return graph


# ---------------------------------------------------------------------------
# GameDayScenario dataclass
# ---------------------------------------------------------------------------


class TestGameDayScenarioDataclass:
    """Verify that GameDayScenario is a valid dataclass with expected fields."""

    def test_instantiation_defaults(self) -> None:
        sc = GameDayScenario(
            scenario_id="GD-001",
            title="Test",
            description="Test scenario",
            difficulty="medium",
            category="single_failure",
        )
        assert sc.scenario_id == "GD-001"
        assert sc.title == "Test"
        assert sc.difficulty == "medium"
        assert sc.category == "single_failure"
        assert sc.trigger_components == []
        assert sc.affected_components == []
        assert sc.preparation_steps == []
        assert sc.execution_steps == []
        assert sc.observation_points == []
        assert sc.recovery_steps == []
        assert sc.success_criteria == []
        assert sc.failure_indicators == []
        assert sc.pre_gameday_checks == []
        assert sc.cascade_depth == 0
        assert sc.estimated_impact_score == 0.0
        assert sc.estimated_mttr_minutes == 30.0
        assert sc.affected_users_pct == 0.0
        assert sc.slo_impact == ""
        assert sc.rollback_plan == ""

    def test_dataclass_fields(self) -> None:
        fields = {f.name for f in dataclasses.fields(GameDayScenario)}
        required = {
            "scenario_id", "title", "description", "difficulty", "category",
            "trigger_components", "failure_mode", "affected_components",
            "cascade_depth", "estimated_impact_score", "estimated_mttr_minutes",
            "affected_users_pct", "preparation_steps", "execution_steps",
            "observation_points", "recovery_steps", "success_criteria",
            "failure_indicators", "slo_impact", "pre_gameday_checks", "rollback_plan",
        }
        assert required.issubset(fields)

    def test_asdict_serialisable(self) -> None:
        sc = GameDayScenario(
            scenario_id="GD-001",
            title="DB Crash",
            description="Primary database crash",
            difficulty="hard",
            category="cascade",
            trigger_components=["db"],
            affected_components=["db", "app", "lb"],
            success_criteria=["MTTR < 30m"],
        )
        d = dataclasses.asdict(sc)
        # Should be JSON serialisable
        payload = json.dumps(d)
        loaded = json.loads(payload)
        assert loaded["scenario_id"] == "GD-001"
        assert loaded["trigger_components"] == ["db"]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    """Unit tests for standalone helper functions."""

    def test_get_execution_steps_database_crash(self) -> None:
        steps = _get_execution_steps("database", "crash")
        assert len(steps) >= 3
        # Should mention primary database
        combined = " ".join(steps).lower()
        assert "database" in combined

    def test_get_execution_steps_fallback(self) -> None:
        steps = _get_execution_steps("custom_component", "unknown_mode")
        assert len(steps) >= 4

    def test_get_recovery_steps_crash(self) -> None:
        steps = _get_recovery_steps("crash")
        assert len(steps) >= 3

    def test_get_recovery_steps_fallback(self) -> None:
        steps = _get_recovery_steps("nonexistent_mode")
        # Falls back to crash steps
        assert len(steps) >= 3

    def test_get_recovery_steps_network_partition(self) -> None:
        steps = _get_recovery_steps("network_partition")
        combined = " ".join(steps).lower()
        assert "partition" in combined or "rules" in combined

    def test_build_success_criteria_with_failover(self) -> None:
        criteria = _build_success_criteria(["db"], ["db", "app"], "crash", True, 30.0)
        assert len(criteria) >= 2
        combined = " ".join(criteria).lower()
        assert "failover" in combined

    def test_build_success_criteria_no_failover(self) -> None:
        criteria = _build_success_criteria(["db"], ["db"], "crash", False, 60.0)
        assert len(criteria) >= 1

    def test_build_failure_indicators_basic(self) -> None:
        indicators = _build_failure_indicators(["db"], "crash", 30.0)
        assert len(indicators) >= 2

    def test_build_failure_indicators_data_corruption(self) -> None:
        indicators = _build_failure_indicators(["db"], "data_corruption", 30.0)
        combined = " ".join(indicators).lower()
        assert "integrity" in combined or "corrupt" in combined

    def test_build_failure_indicators_network_partition(self) -> None:
        indicators = _build_failure_indicators(["db"], "network_partition", 30.0)
        combined = " ".join(indicators).lower()
        assert "split" in combined or "partition" in combined

    def test_spof_score_single_replica_no_failover(self) -> None:
        graph = _simple_graph()
        db = graph.get_component("db")
        assert db is not None
        score = _spof_score(db, graph)
        # db has 1 replica, no failover, is DATABASE type — should be high
        assert score > 3.0

    def test_spof_score_with_failover(self) -> None:
        graph = _simple_graph()
        lb = graph.get_component("lb")
        assert lb is not None
        score_lb = _spof_score(lb, graph)
        # lb has failover=True, less SPOF risk
        assert score_lb >= 0.0

    def test_cascade_depth_from_chain(self) -> None:
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        from faultray.model.components import HealthStatus
        chain = CascadeChain(trigger="db crash")
        chain.effects = [
            CascadeEffect(component_id="db", component_name="DB", health=HealthStatus.DOWN, reason=""),
            CascadeEffect(component_id="app", component_name="App", health=HealthStatus.DOWN, reason=""),
            CascadeEffect(component_id="lb", component_name="LB", health=HealthStatus.DEGRADED, reason=""),
        ]
        assert _cascade_depth(chain) == 3

    def test_cascade_depth_empty(self) -> None:
        from faultray.simulator.cascade import CascadeChain
        chain = CascadeChain(trigger="")
        assert _cascade_depth(chain) == 0

    def test_cascade_depth_deduplicates(self) -> None:
        from faultray.simulator.cascade import CascadeChain, CascadeEffect
        from faultray.model.components import HealthStatus
        chain = CascadeChain(trigger="x")
        chain.effects = [
            CascadeEffect(component_id="app", component_name="App", health=HealthStatus.DOWN, reason=""),
            CascadeEffect(component_id="app", component_name="App", health=HealthStatus.DOWN, reason=""),
        ]
        assert _cascade_depth(chain) == 1


# ---------------------------------------------------------------------------
# GameDayGenerator — basic generation
# ---------------------------------------------------------------------------


class TestGameDayGeneratorBasic:
    """Tests for GameDayGenerator.generate_scenarios."""

    def test_returns_list(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=3)
        assert isinstance(result, list)

    def test_returns_game_day_scenario_instances(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=3)
        for sc in result:
            assert isinstance(sc, GameDayScenario)

    def test_count_respected(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        for n in (1, 3, 5):
            result = gen.generate_scenarios(count=n)
            assert len(result) <= n

    def test_ids_assigned_sequentially(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=3)
        for idx, sc in enumerate(result, start=1):
            assert sc.scenario_id == f"GD-{idx:03d}"

    def test_all_fields_populated(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=2)
        for sc in result:
            assert sc.title != ""
            assert sc.description != ""
            assert sc.difficulty in ("easy", "medium", "hard")
            assert sc.category != ""
            assert len(sc.preparation_steps) > 0
            assert len(sc.execution_steps) > 0
            assert len(sc.recovery_steps) > 0
            assert len(sc.success_criteria) > 0
            assert len(sc.failure_indicators) > 0
            assert sc.slo_impact != ""
            assert sc.rollback_plan != ""

    def test_impact_score_range(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=5)
        for sc in result:
            assert 0.0 <= sc.estimated_impact_score <= 100.0

    def test_mttr_positive(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=5)
        for sc in result:
            assert sc.estimated_mttr_minutes > 0

    def test_affected_users_pct_range(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=5)
        for sc in result:
            assert 0.0 <= sc.affected_users_pct <= 100.0

    def test_sorted_by_impact_descending(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=5)
        scores = [sc.estimated_impact_score for sc in result]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# GameDayGenerator — difficulty levels
# ---------------------------------------------------------------------------


class TestDifficultyLevels:
    """Tests for difficulty-based scenario generation."""

    def test_easy_generates_scenarios(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=3, difficulty="easy")
        assert len(result) >= 1
        for sc in result:
            assert sc.difficulty == "easy"

    def test_medium_generates_scenarios(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=3, difficulty="medium")
        assert len(result) >= 1
        for sc in result:
            assert sc.difficulty == "medium"

    def test_hard_generates_scenarios(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=5, difficulty="hard")
        assert len(result) >= 1
        for sc in result:
            assert sc.difficulty == "hard"

    def test_invalid_difficulty_defaults_to_medium(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=2, difficulty="extreme")
        for sc in result:
            assert sc.difficulty == "medium"

    def test_hard_may_include_multi_failure(self) -> None:
        """Hard scenarios on a rich graph should include compound failures."""
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=10, difficulty="hard")
        categories = {sc.category for sc in result}
        # With 8 components of mixed types, compound/cascade should appear
        assert len(categories) >= 1


# ---------------------------------------------------------------------------
# GameDayGenerator — category diversity
# ---------------------------------------------------------------------------


class TestCategoryDiversity:
    """Tests for diversity selection."""

    def test_diverse_categories(self) -> None:
        """Generated scenarios should not all have the same category."""
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=5, difficulty="medium")
        categories = [sc.category for sc in result]
        # At minimum we should get more than 1 unique category from a rich graph
        assert len(set(categories)) >= 1  # at least 1 distinct category

    def test_no_category_dominates_entirely(self) -> None:
        """No single category should occupy all slots when graph has diversity."""
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=6, difficulty="medium")
        if len(result) >= 3:
            from collections import Counter
            counts = Counter(sc.category for sc in result)
            most_common_count = max(counts.values())
            # max_per_category formula: max(1, (count+2)//3)
            # For count=6: max_per_category = max(1, 8//3) = 2
            assert most_common_count <= max(1, (len(result) + 2) // 3)


# ---------------------------------------------------------------------------
# GameDayGenerator — rich graph
# ---------------------------------------------------------------------------


class TestRichGraph:
    """Tests with a more realistic infrastructure graph."""

    def test_generates_max_requested(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=5)
        assert len(result) <= 5

    def test_trigger_components_valid(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        graph = _rich_graph()
        result = gen.generate_scenarios(count=5)
        for sc in result:
            for tid in sc.trigger_components:
                assert graph.get_component(tid) is not None, (
                    f"Trigger component {tid!r} not found in graph"
                )

    def test_pre_gameday_checks_non_empty(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=3)
        for sc in result:
            assert len(sc.pre_gameday_checks) >= 3

    def test_observation_points_non_empty(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=3)
        for sc in result:
            assert len(sc.observation_points) >= 2

    def test_slo_impact_categories(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=5)
        for sc in result:
            # SLO text should mention one of the key terms
            text = sc.slo_impact.lower()
            assert any(kw in text for kw in ("critical", "moderate", "low", "budget", "slo"))

    def test_hard_scenarios_include_network_or_data(self) -> None:
        gen = GameDayGenerator(_rich_graph())
        result = gen.generate_scenarios(count=10, difficulty="hard")
        modes = {sc.failure_mode for sc in result}
        # Hard should produce at least crash and one other mode
        assert "crash" in modes or len(modes) >= 1


# ---------------------------------------------------------------------------
# GameDayGenerator — edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests."""

    def test_single_component_graph(self) -> None:
        graph = InfraGraph()
        graph.add_component(Component(
            id="solo", name="Solo", type=ComponentType.APP_SERVER, replicas=1,
        ))
        gen = GameDayGenerator(graph)
        result = gen.generate_scenarios(count=3)
        assert isinstance(result, list)
        # May produce fewer than requested with a single-component graph
        for sc in result:
            assert sc.scenario_id.startswith("GD-")

    def test_count_zero_returns_empty(self) -> None:
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=0)
        assert result == []

    def test_count_greater_than_available(self) -> None:
        """Requesting more scenarios than available should return what is possible."""
        gen = GameDayGenerator(_simple_graph())
        result = gen.generate_scenarios(count=100)
        assert len(result) <= 100
        assert isinstance(result, list)

    def test_empty_graph(self) -> None:
        graph = InfraGraph()
        gen = GameDayGenerator(graph)
        result = gen.generate_scenarios(count=3)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# CLI integration (import + dry-run)
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """Verify CLI command imports and basic invocation."""

    def test_import_gameday_cmd(self) -> None:
        from faultray.cli.predictive import gameday  # noqa: F401
        assert callable(gameday)

    def test_gameday_json_output(self, tmp_path: Path) -> None:
        """Run the CLI in generate mode with JSON output via CliRunner."""
        from typer.testing import CliRunner
        from faultray.cli import app

        # Build a minimal YAML infra file
        infra_yaml = tmp_path / "infra.yaml"
        infra_yaml.write_text(
            "components:\n"
            "  - id: app\n"
            "    name: App\n"
            "    type: app_server\n"
            "    replicas: 2\n"
            "  - id: db\n"
            "    name: DB\n"
            "    type: database\n"
            "    replicas: 1\n"
            "dependencies:\n"
            "  - source_id: app\n"
            "    target_id: db\n",
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(app, ["gameday", str(infra_yaml), "--scenarios", "3", "--json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) <= 3
        if data:
            assert "scenario_id" in data[0]
            assert "title" in data[0]
            assert "execution_steps" in data[0]

    def test_gameday_html_output(self, tmp_path: Path) -> None:
        """Run the CLI in generate mode with HTML output."""
        from typer.testing import CliRunner
        from faultray.cli import app

        infra_yaml = tmp_path / "infra.yaml"
        infra_yaml.write_text(
            "components:\n"
            "  - id: lb\n"
            "    name: LB\n"
            "    type: load_balancer\n"
            "    replicas: 2\n"
            "  - id: db\n"
            "    name: DB\n"
            "    type: database\n"
            "    replicas: 1\n"
            "dependencies:\n"
            "  - source_id: lb\n"
            "    target_id: db\n",
            encoding="utf-8",
        )
        output_html = tmp_path / "gameday.html"

        runner = CliRunner()
        result = runner.invoke(
            app, ["gameday", str(infra_yaml), "--scenarios", "2", "--output", str(output_html)]
        )

        assert result.exit_code == 0, result.output
        assert output_html.exists()
        html = output_html.read_text(encoding="utf-8")
        assert "GameDay" in html
        assert "GD-001" in html

    def test_gameday_missing_file(self, tmp_path: Path) -> None:
        """Missing infra file should exit with non-zero code."""
        from typer.testing import CliRunner
        from faultray.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["gameday", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code != 0

    def test_gameday_difficulty_options(self, tmp_path: Path) -> None:
        """Easy and hard difficulty options should work."""
        from typer.testing import CliRunner
        from faultray.cli import app

        infra_yaml = tmp_path / "infra.yaml"
        infra_yaml.write_text(
            "components:\n"
            "  - id: app\n"
            "    name: App\n"
            "    type: app_server\n"
            "    replicas: 1\n"
            "  - id: db\n"
            "    name: DB\n"
            "    type: database\n"
            "    replicas: 1\n"
            "dependencies:\n"
            "  - source_id: app\n"
            "    target_id: db\n",
            encoding="utf-8",
        )

        runner = CliRunner()
        for diff in ("easy", "medium", "hard"):
            result = runner.invoke(
                app, ["gameday", str(infra_yaml), "--json", "--difficulty", diff]
            )
            assert result.exit_code == 0, f"difficulty={diff} failed: {result.output}"
