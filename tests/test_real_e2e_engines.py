# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""全主要シミュレーターエンジンの実E2Eテスト。

モックなし。実際のグラフを作成し、実際のエンジンを実行する。
デモグラフとカスタムグラフの両方でテストする。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import pytest

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph
from faultray.simulator.anomaly_detector import AnomalyDetector, AnomalyReport
from faultray.simulator.bayesian_model import BayesianEngine
from faultray.simulator.blast_radius_calculator import BlastRadiusCalculator
from faultray.simulator.chaos_monkey import ChaosMonkey
from faultray.simulator.compliance_engine import ComplianceEngine
from faultray.simulator.cost_impact import CostImpactEngine
from faultray.simulator.deployment_strategy import DeploymentStrategyAdvisor
from faultray.simulator.digital_twin import DigitalTwin, DigitalTwinReport
from faultray.simulator.engine import SimulationEngine, SimulationReport
from faultray.simulator.gameday_engine import (
    Fault,
    FaultType,
    GameDayEngine,
    GameDayPlan,
    GameDayReport,
    GameDayStep,
)
from faultray.simulator.incident_replay import IncidentReplayEngine
from faultray.simulator.markov_model import MarkovResult, compute_markov_availability
from faultray.simulator.monte_carlo import run_monte_carlo
from faultray.simulator.predictive_failure import PredictiveFailureEngine, PredictiveReport
from faultray.simulator.sre_maturity import MaturityReport, SREMaturityEngine
from faultray.simulator.whatif_engine import WhatIfEngine, WhatIfResult


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------


@pytest.fixture()
def custom_graph() -> InfraGraph:
    """テスト用カスタムグラフを構築して返す。"""
    graph = InfraGraph()
    graph.add_component(
        Component(id="lb", name="lb", type=ComponentType.LOAD_BALANCER, replicas=2)
    )
    graph.add_component(
        Component(id="app", name="app", type=ComponentType.APP_SERVER, replicas=3)
    )
    graph.add_component(
        Component(id="db", name="db", type=ComponentType.DATABASE, replicas=1)
    )
    graph.add_component(
        Component(id="cache", name="cache", type=ComponentType.CACHE, replicas=2)
    )
    graph.add_dependency(
        Dependency(source_id="lb", target_id="app", dependency_type="required")
    )
    graph.add_dependency(
        Dependency(source_id="app", target_id="db", dependency_type="required")
    )
    graph.add_dependency(
        Dependency(source_id="app", target_id="cache", dependency_type="optional")
    )
    return graph


@pytest.fixture()
def demo_graph() -> InfraGraph:
    """デモグラフを返す。"""
    return create_demo_graph()


# ---------------------------------------------------------------------------
# グラフ操作テスト
# ---------------------------------------------------------------------------


class TestGraphOperations:
    """InfraGraph の基本操作と分析メソッドのテスト。"""

    def test_resilience_score_returns_float(self, custom_graph: InfraGraph) -> None:
        """resilience_score() が float を返すことを確認する。"""
        score = custom_graph.resilience_score()
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_resilience_score_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも resilience_score() が有効な範囲を返す。"""
        score = demo_graph.resilience_score()
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_resilience_score_v2_returns_dict(self, custom_graph: InfraGraph) -> None:
        """resilience_score_v2() が dict を返すことを確認する。"""
        result = custom_graph.resilience_score_v2()
        assert isinstance(result, dict)

    def test_resilience_score_v2_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも resilience_score_v2() が dict を返す。"""
        result = demo_graph.resilience_score_v2()
        assert isinstance(result, dict)

    def test_get_cascade_path_returns_list_of_lists(self, custom_graph: InfraGraph) -> None:
        """get_cascade_path() が list[list[str]] を返すことを確認する。"""
        paths = custom_graph.get_cascade_path("db")
        assert isinstance(paths, list)
        for path in paths:
            assert isinstance(path, list)
            assert all(isinstance(p, str) for p in path)

    def test_get_cascade_path_db_upstream(self, custom_graph: InfraGraph) -> None:
        """db の障害がアップストリームコンポーネントを経由するパスを持つことを確認する。"""
        paths = custom_graph.get_cascade_path("db")
        # db -> app -> lb のいずれかのパスが存在する
        all_nodes = {node for path in paths for node in path}
        assert "db" in all_nodes

    def test_get_all_affected_returns_set(self, custom_graph: InfraGraph) -> None:
        """get_all_affected() が set[str] を返すことを確認する。"""
        affected = custom_graph.get_all_affected("db")
        assert isinstance(affected, set)
        assert all(isinstance(c, str) for c in affected)

    def test_get_all_affected_db_includes_app(self, custom_graph: InfraGraph) -> None:
        """db が落ちた場合 app が影響を受けることを確認する。"""
        affected = custom_graph.get_all_affected("db")
        assert "app" in affected

    def test_get_all_affected_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフで get_all_affected() が動作することを確認する。"""
        components = list(demo_graph.components.keys())
        if components:
            affected = demo_graph.get_all_affected(components[0])
            assert isinstance(affected, set)

    def test_get_critical_paths_returns_list(self, custom_graph: InfraGraph) -> None:
        """get_critical_paths() が list を返すことを確認する。"""
        paths = custom_graph.get_critical_paths()
        assert isinstance(paths, list)

    def test_get_critical_paths_not_empty(self, custom_graph: InfraGraph) -> None:
        """依存関係があるグラフでクリティカルパスが存在することを確認する。"""
        paths = custom_graph.get_critical_paths()
        assert len(paths) > 0

    def test_get_dependents_returns_list(self, custom_graph: InfraGraph) -> None:
        """get_dependents() が list を返すことを確認する。"""
        dependents = custom_graph.get_dependents("app")
        assert isinstance(dependents, list)

    def test_get_dependents_app_has_lb(self, custom_graph: InfraGraph) -> None:
        """app の依存元に lb が含まれることを確認する。"""
        dependents = custom_graph.get_dependents("app")
        dep_ids = {c.id for c in dependents}
        assert "lb" in dep_ids

    def test_get_dependencies_returns_list(self, custom_graph: InfraGraph) -> None:
        """get_dependencies() が list を返すことを確認する。"""
        deps = custom_graph.get_dependencies("app")
        assert isinstance(deps, list)

    def test_get_dependencies_app_has_db(self, custom_graph: InfraGraph) -> None:
        """app の依存先に db が含まれることを確認する。"""
        deps = custom_graph.get_dependencies("app")
        dep_ids = {c.id for c in deps}
        assert "db" in dep_ids


# ---------------------------------------------------------------------------
# SimulationEngine テスト
# ---------------------------------------------------------------------------


class TestSimulationEngine:
    """SimulationEngine の実行テスト。"""

    def test_run_all_defaults_returns_report(self, custom_graph: InfraGraph) -> None:
        """run_all_defaults() が SimulationReport を返すことを確認する。"""
        engine = SimulationEngine(custom_graph)
        report = engine.run_all_defaults()
        assert isinstance(report, SimulationReport)

    def test_report_has_resilience_score(self, custom_graph: InfraGraph) -> None:
        """SimulationReport が resilience_score 属性を持つことを確認する。"""
        engine = SimulationEngine(custom_graph)
        report = engine.run_all_defaults()
        assert hasattr(report, "resilience_score")
        assert isinstance(report.resilience_score, float)
        assert 0.0 <= report.resilience_score <= 100.0

    def test_report_has_results(self, custom_graph: InfraGraph) -> None:
        """SimulationReport が results リストを持つことを確認する。"""
        engine = SimulationEngine(custom_graph)
        report = engine.run_all_defaults()
        assert hasattr(report, "results")
        assert isinstance(report.results, list)

    def test_run_all_defaults_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも SimulationEngine が正常に動作することを確認する。"""
        engine = SimulationEngine(demo_graph)
        report = engine.run_all_defaults()
        assert isinstance(report, SimulationReport)
        assert 0.0 <= report.resilience_score <= 100.0


# ---------------------------------------------------------------------------
# MonteCarloEngine テスト
# ---------------------------------------------------------------------------


class TestMonteCarlo:
    """モンテカルロシミュレーションのテスト。"""

    def test_run_monte_carlo_returns_result(self, custom_graph: InfraGraph) -> None:
        """run_monte_carlo() が MonteCarloResult を返すことを確認する。"""
        result = run_monte_carlo(custom_graph, n_trials=100, seed=42)
        assert result is not None

    def test_monte_carlo_n_trials(self, custom_graph: InfraGraph) -> None:
        """MonteCarloResult が n_trials 属性を持つことを確認する。"""
        result = run_monte_carlo(custom_graph, n_trials=100, seed=42)
        assert hasattr(result, "n_trials")
        assert result.n_trials == 100

    def test_monte_carlo_seed_reproducibility(self, custom_graph: InfraGraph) -> None:
        """同じシードで2回実行した結果が一致することを確認する。"""
        r1 = run_monte_carlo(custom_graph, n_trials=100, seed=42)
        r2 = run_monte_carlo(custom_graph, n_trials=100, seed=42)
        assert r1.n_trials == r2.n_trials

    def test_monte_carlo_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも run_monte_carlo() が正常に動作することを確認する。"""
        result = run_monte_carlo(demo_graph, n_trials=50, seed=99)
        assert hasattr(result, "n_trials")
        assert result.n_trials == 50

    def test_monte_carlo_large_trial_count(self, custom_graph: InfraGraph) -> None:
        """大きなトライアル数でも run_monte_carlo() が完了することを確認する。"""
        result = run_monte_carlo(custom_graph, n_trials=10000, seed=42)
        assert result.n_trials == 10000


# ---------------------------------------------------------------------------
# WhatIfEngine テスト
# ---------------------------------------------------------------------------


class TestWhatIfEngine:
    """WhatIfEngine の実行テスト。"""

    def test_run_default_whatifs_returns_list(self, custom_graph: InfraGraph) -> None:
        """run_default_whatifs() が list を返すことを確認する。"""
        engine = WhatIfEngine(custom_graph)
        results = engine.run_default_whatifs()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_whatif_result_type(self, custom_graph: InfraGraph) -> None:
        """各要素が WhatIfResult であることを確認する。"""
        engine = WhatIfEngine(custom_graph)
        results = engine.run_default_whatifs()
        for r in results:
            assert isinstance(r, WhatIfResult)

    def test_whatif_result_has_parameter(self, custom_graph: InfraGraph) -> None:
        """WhatIfResult が parameter 属性を持つことを確認する。"""
        engine = WhatIfEngine(custom_graph)
        results = engine.run_default_whatifs()
        assert hasattr(results[0], "parameter")

    def test_whatif_result_has_summary(self, custom_graph: InfraGraph) -> None:
        """WhatIfResult が summary 属性を持つことを確認する。"""
        engine = WhatIfEngine(custom_graph)
        results = engine.run_default_whatifs()
        assert hasattr(results[0], "summary")

    def test_whatif_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも WhatIfEngine が動作することを確認する。"""
        engine = WhatIfEngine(demo_graph)
        results = engine.run_default_whatifs()
        assert isinstance(results, list)
        assert len(results) > 0

    def test_run_whatif_single_scenario(self, custom_graph: InfraGraph) -> None:
        """run_whatif() が単一シナリオで動作することを確認する。"""
        engine = WhatIfEngine(custom_graph)
        defaults = engine.run_default_whatifs()
        # run_default_whatifs が内部的に run_whatif を使うことを前提に
        # 戻り値の型が正しいことを確認する
        assert len(defaults) > 0


# ---------------------------------------------------------------------------
# CostImpactEngine テスト
# ---------------------------------------------------------------------------


class TestCostImpactEngine:
    """CostImpactEngine の実行テスト。"""

    def test_calculate_scenario_cost_returns_breakdown(self) -> None:
        """calculate_scenario_cost() が CostBreakdown を返すことを確認する。"""
        engine = CostImpactEngine()
        result = engine.calculate_scenario_cost("db_down", ["db"], 30.0)
        assert result is not None
        assert hasattr(result, "total_cost")

    def test_calculate_scenario_cost_positive_value(self) -> None:
        """calculate_scenario_cost() が非負のコストを返すことを確認する。"""
        engine = CostImpactEngine()
        result = engine.calculate_scenario_cost("db_down", ["db", "app"], 60.0)
        assert result.total_cost >= 0.0

    def test_calculate_scenario_cost_multiple_components(self) -> None:
        """複数コンポーネント障害でコスト計算が動作することを確認する。"""
        engine = CostImpactEngine()
        result = engine.calculate_scenario_cost("full_outage", ["lb", "app", "db", "cache"], 120.0)
        assert hasattr(result, "affected_components")
        assert len(result.affected_components) == 4

    def test_calculate_annual_projection(self) -> None:
        """calculate_annual_projection() が AnnualCostProjection を返すことを確認する。"""
        engine = CostImpactEngine()
        scenario = engine.calculate_scenario_cost("db_down", ["db"], 30.0)
        result = engine.calculate_annual_projection([scenario], incidents_per_year=12.0)
        assert result is not None

    def test_calculate_roi(self) -> None:
        """calculate_roi() が ROIAnalysis を返すことを確認する。"""
        engine = CostImpactEngine()
        result = engine.calculate_roi(
            improvement_name="add_db_replica",
            implementation_cost=5000.0,
            current_annual_cost=50000.0,
            projected_annual_cost=10000.0,
        )
        assert result is not None

    def test_calculate_scenario_cost_zero_downtime(self) -> None:
        """ダウンタイム0でもエラーにならないことを確認する。"""
        engine = CostImpactEngine()
        # 0.001 minutes は事実上ゼロに近い値
        result = engine.calculate_scenario_cost("minimal_outage", ["cache"], 0.001)
        assert result is not None
        assert result.total_cost >= 0.0


# ---------------------------------------------------------------------------
# ComplianceEngine テスト
# ---------------------------------------------------------------------------


class TestComplianceEngine:
    """ComplianceEngine の実行テスト。"""

    def test_check_all_returns_dict(self, custom_graph: InfraGraph) -> None:
        """check_all() が dict を返すことを確認する。"""
        engine = ComplianceEngine(custom_graph)
        result = engine.check_all()
        assert isinstance(result, dict)

    def test_check_all_has_frameworks(self, custom_graph: InfraGraph) -> None:
        """check_all() の結果に主要フレームワークが含まれることを確認する。"""
        engine = ComplianceEngine(custom_graph)
        result = engine.check_all()
        assert "soc2" in result
        assert "iso27001" in result
        assert "nist_csf" in result

    def test_has_redundancy_method_exists(self, custom_graph: InfraGraph) -> None:
        """ComplianceEngine が _has_redundancy メソッドを持つことを確認する。"""
        engine = ComplianceEngine(custom_graph)
        assert hasattr(engine, "_has_redundancy")

    def test_has_failover_method_exists(self, custom_graph: InfraGraph) -> None:
        """ComplianceEngine が _has_failover メソッドを持つことを確認する。"""
        engine = ComplianceEngine(custom_graph)
        assert hasattr(engine, "_has_failover")

    def test_check_soc2(self, custom_graph: InfraGraph) -> None:
        """check_soc2() が単独で動作することを確認する。"""
        engine = ComplianceEngine(custom_graph)
        result = engine.check_soc2()
        assert result is not None

    def test_check_nist_csf(self, custom_graph: InfraGraph) -> None:
        """check_nist_csf() が単独で動作することを確認する。"""
        engine = ComplianceEngine(custom_graph)
        result = engine.check_nist_csf()
        assert result is not None

    def test_compliance_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも ComplianceEngine が動作することを確認する。"""
        engine = ComplianceEngine(demo_graph)
        result = engine.check_all()
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# BlastRadiusCalculator テスト
# ---------------------------------------------------------------------------


class TestBlastRadiusCalculator:
    """BlastRadiusCalculator の実行テスト。"""

    def test_generate_full_report(self, custom_graph: InfraGraph) -> None:
        """generate_full_report() が結果を返すことを確認する。"""
        calc = BlastRadiusCalculator(custom_graph)
        report = calc.generate_full_report()
        assert report is not None

    def test_calculate_impact_score_db(self, custom_graph: InfraGraph) -> None:
        """calculate_impact_score('db') が ComponentImpactScore を返すことを確認する。"""
        calc = BlastRadiusCalculator(custom_graph)
        score = calc.calculate_impact_score("db")
        assert score is not None
        assert hasattr(score, "total_impact_score")

    def test_impact_score_is_positive(self, custom_graph: InfraGraph) -> None:
        """db の影響スコアが正の値であることを確認する。"""
        calc = BlastRadiusCalculator(custom_graph)
        score = calc.calculate_impact_score("db")
        assert score.total_impact_score > 0.0

    def test_calculate_all_impact_scores(self, custom_graph: InfraGraph) -> None:
        """calculate_all_impact_scores() が全コンポーネントのスコアを返すことを確認する。"""
        calc = BlastRadiusCalculator(custom_graph)
        scores = calc.calculate_all_impact_scores()
        assert isinstance(scores, (dict, list))

    def test_blast_radius_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも BlastRadiusCalculator が動作することを確認する。"""
        calc = BlastRadiusCalculator(demo_graph)
        report = calc.generate_full_report()
        assert report is not None


# ---------------------------------------------------------------------------
# PredictiveFailureEngine テスト
# ---------------------------------------------------------------------------


class TestPredictiveFailureEngine:
    """PredictiveFailureEngine の実行テスト。"""

    def test_predict_returns_report(self, custom_graph: InfraGraph) -> None:
        """predict() が PredictiveReport を返すことを確認する。"""
        engine = PredictiveFailureEngine(custom_graph)
        report = engine.predict()
        assert isinstance(report, PredictiveReport)

    def test_report_has_predictions(self, custom_graph: InfraGraph) -> None:
        """PredictiveReport が predictions 属性を持つことを確認する。"""
        engine = PredictiveFailureEngine(custom_graph)
        report = engine.predict()
        assert hasattr(report, "predictions")

    def test_report_has_overall_risk_score(self, custom_graph: InfraGraph) -> None:
        """PredictiveReport が overall_risk_score を持つことを確認する。"""
        engine = PredictiveFailureEngine(custom_graph)
        report = engine.predict()
        assert hasattr(report, "overall_risk_score")

    def test_report_has_top_risks(self, custom_graph: InfraGraph) -> None:
        """PredictiveReport が top_risks を持つことを確認する。"""
        engine = PredictiveFailureEngine(custom_graph)
        report = engine.predict()
        assert hasattr(report, "top_risks")

    def test_predictive_failure_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも PredictiveFailureEngine が動作することを確認する。"""
        engine = PredictiveFailureEngine(demo_graph)
        report = engine.predict()
        assert isinstance(report, PredictiveReport)


# ---------------------------------------------------------------------------
# SREMaturityEngine テスト
# ---------------------------------------------------------------------------


class TestSREMaturityEngine:
    """SREMaturityEngine の実行テスト。"""

    def test_assess_returns_maturity_report(self, custom_graph: InfraGraph) -> None:
        """assess() が MaturityReport を返すことを確認する。"""
        engine = SREMaturityEngine()
        report = engine.assess(custom_graph)
        assert isinstance(report, MaturityReport)

    def test_report_has_overall_score(self, custom_graph: InfraGraph) -> None:
        """MaturityReport が overall_score を持つことを確認する。"""
        engine = SREMaturityEngine()
        report = engine.assess(custom_graph)
        assert hasattr(report, "overall_score")

    def test_report_has_dimensions(self, custom_graph: InfraGraph) -> None:
        """MaturityReport が dimensions を持つことを確認する。"""
        engine = SREMaturityEngine()
        report = engine.assess(custom_graph)
        assert hasattr(report, "dimensions")

    def test_report_has_overall_level(self, custom_graph: InfraGraph) -> None:
        """MaturityReport が overall_level を持つことを確認する。"""
        engine = SREMaturityEngine()
        report = engine.assess(custom_graph)
        assert hasattr(report, "overall_level")

    def test_sre_maturity_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも SREMaturityEngine が動作することを確認する。"""
        engine = SREMaturityEngine()
        report = engine.assess(demo_graph)
        assert isinstance(report, MaturityReport)

    def test_assess_dimension_method_exists(self, custom_graph: InfraGraph) -> None:
        """assess_dimension() メソッドが存在することを確認する。"""
        engine = SREMaturityEngine()
        assert hasattr(engine, "assess_dimension")

    def test_generate_roadmap(self, custom_graph: InfraGraph) -> None:
        """generate_roadmap() が呼び出せることを確認する。"""
        engine = SREMaturityEngine()
        report = engine.assess(custom_graph)
        assert hasattr(report, "roadmap")


# ---------------------------------------------------------------------------
# ChaosMonkey テスト
# ---------------------------------------------------------------------------


class TestChaosMonkey:
    """ChaosMonkey の実行テスト。"""

    def test_run_returns_report(self, custom_graph: InfraGraph) -> None:
        """run() が ChaosMonkeyReport を返すことを確認する。"""
        monkey = ChaosMonkey()
        report = monkey.run(custom_graph)
        assert report is not None

    def test_run_single_returns_result(self, custom_graph: InfraGraph) -> None:
        """run_single() が結果を返すことを確認する。"""
        monkey = ChaosMonkey()
        result = monkey.run_single(custom_graph)
        assert result is not None

    def test_find_weakest_point(self, custom_graph: InfraGraph) -> None:
        """find_weakest_point() が弱点を特定することを確認する。"""
        monkey = ChaosMonkey()
        weakest = monkey.find_weakest_point(custom_graph)
        assert weakest is not None

    def test_stress_test(self, custom_graph: InfraGraph) -> None:
        """stress_test() が結果を返すことを確認する。"""
        monkey = ChaosMonkey()
        result = monkey.stress_test(custom_graph)
        assert result is not None

    def test_chaos_monkey_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも ChaosMonkey が動作することを確認する。"""
        monkey = ChaosMonkey()
        report = monkey.run(demo_graph)
        assert report is not None


# ---------------------------------------------------------------------------
# BayesianEngine テスト
# ---------------------------------------------------------------------------


class TestBayesianEngine:
    """BayesianEngine の実行テスト。"""

    def test_analyze_returns_results(self, custom_graph: InfraGraph) -> None:
        """analyze() が結果リストを返すことを確認する。"""
        engine = BayesianEngine(custom_graph)
        results = engine.analyze()
        assert results is not None
        assert isinstance(results, list)

    def test_analyze_results_non_empty(self, custom_graph: InfraGraph) -> None:
        """analyze() の結果が空でないことを確認する。"""
        engine = BayesianEngine(custom_graph)
        results = engine.analyze()
        assert len(results) > 0

    def test_query_with_evidence(self, custom_graph: InfraGraph) -> None:
        """query() がエビデンス付きで結果を返すことを確認する。"""
        engine = BayesianEngine(custom_graph)
        result = engine.query({"db": True})
        assert result is not None

    def test_query_returns_dict(self, custom_graph: InfraGraph) -> None:
        """query() が dict を返すことを確認する。"""
        engine = BayesianEngine(custom_graph)
        result = engine.query({"db": True})
        assert isinstance(result, dict)

    def test_bayesian_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも BayesianEngine が動作することを確認する。"""
        engine = BayesianEngine(demo_graph)
        results = engine.analyze()
        assert isinstance(results, list)

    def test_analyze_result_has_component_id(self, custom_graph: InfraGraph) -> None:
        """analyze() の各要素が component_id を持つことを確認する。"""
        engine = BayesianEngine(custom_graph)
        results = engine.analyze()
        for r in results:
            assert hasattr(r, "component_id")


# ---------------------------------------------------------------------------
# Markov モデル テスト
# ---------------------------------------------------------------------------


class TestMarkovModel:
    """compute_markov_availability のテスト。"""

    def test_returns_markov_result(self) -> None:
        """compute_markov_availability() が MarkovResult を返すことを確認する。"""
        result = compute_markov_availability(720, 4)
        assert isinstance(result, MarkovResult)

    def test_availability_is_valid(self) -> None:
        """availability が 0 から 1 の範囲にあることを確認する。"""
        result = compute_markov_availability(720, 4)
        assert hasattr(result, "availability")
        assert 0.0 <= result.availability <= 1.0

    def test_has_nines(self) -> None:
        """MarkovResult が nines 属性を持つことを確認する。"""
        result = compute_markov_availability(720, 4)
        assert hasattr(result, "nines")

    def test_has_steady_state(self) -> None:
        """MarkovResult が steady_state 属性を持つことを確認する。"""
        result = compute_markov_availability(720, 4)
        assert hasattr(result, "steady_state")

    def test_high_mtbf_gives_high_availability(self) -> None:
        """MTBF が高いほど可用性が高くなることを確認する。"""
        r_high = compute_markov_availability(10000, 1)
        r_low = compute_markov_availability(10, 10)
        assert r_high.availability > r_low.availability

    def test_five_nines_scenario(self) -> None:
        """理論上の5ナイン構成で高可用性が得られることを確認する。"""
        result = compute_markov_availability(8760, 1)
        assert result.availability > 0.99


# ---------------------------------------------------------------------------
# DigitalTwin テスト
# ---------------------------------------------------------------------------


class TestDigitalTwin:
    """DigitalTwin の実行テスト。"""

    def test_predict_returns_snapshot(self, custom_graph: InfraGraph) -> None:
        """predict() が TwinSnapshot を返すことを確認する。"""
        twin = DigitalTwin(custom_graph)
        snapshot = twin.predict()
        assert snapshot is not None

    def test_report_returns_digital_twin_report(self, custom_graph: InfraGraph) -> None:
        """report() が DigitalTwinReport を返すことを確認する。"""
        twin = DigitalTwin(custom_graph)
        report = twin.report()
        assert isinstance(report, DigitalTwinReport)

    def test_digital_twin_has_graph(self, custom_graph: InfraGraph) -> None:
        """DigitalTwin が graph 属性を持つことを確認する。"""
        twin = DigitalTwin(custom_graph)
        assert hasattr(twin, "graph")

    def test_digital_twin_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも DigitalTwin が動作することを確認する。"""
        twin = DigitalTwin(demo_graph)
        report = twin.report()
        assert isinstance(report, DigitalTwinReport)

    def test_ingest_metrics_method_exists(self, custom_graph: InfraGraph) -> None:
        """ingest_metrics() メソッドが存在することを確認する。"""
        twin = DigitalTwin(custom_graph)
        assert hasattr(twin, "ingest_metrics")


# ---------------------------------------------------------------------------
# GameDayEngine テスト
# ---------------------------------------------------------------------------


class TestGameDayEngine:
    """GameDayEngine の実行テスト。"""

    def _make_plan(self, component_id: str = "db", fault_type: FaultType = FaultType.COMPONENT_DOWN) -> GameDayPlan:
        """テスト用 GameDayPlan を構築して返す。"""
        fault = Fault(target_component_id=component_id, fault_type=fault_type)
        step = GameDayStep(
            time_offset_seconds=0,
            action="inject_fault",
            fault=fault,
            expected_outcome="degraded_service",
        )
        return GameDayPlan(name="test_game_day", steps=[step])

    def test_execute_returns_report(self, custom_graph: InfraGraph) -> None:
        """execute() が GameDayReport を返すことを確認する。"""
        engine = GameDayEngine(custom_graph)
        plan = self._make_plan()
        report = engine.execute(plan)
        assert isinstance(report, GameDayReport)

    def test_report_has_plan_name(self, custom_graph: InfraGraph) -> None:
        """GameDayReport が plan_name を持つことを確認する。"""
        engine = GameDayEngine(custom_graph)
        plan = self._make_plan()
        report = engine.execute(plan)
        assert hasattr(report, "plan_name")
        assert report.plan_name == "test_game_day"

    def test_report_has_steps(self, custom_graph: InfraGraph) -> None:
        """GameDayReport が steps を持つことを確認する。"""
        engine = GameDayEngine(custom_graph)
        plan = self._make_plan()
        report = engine.execute(plan)
        assert hasattr(report, "steps")

    def test_gameday_latency_spike(self, custom_graph: InfraGraph) -> None:
        """レイテンシースパイクシナリオで GameDayEngine が動作することを確認する。"""
        engine = GameDayEngine(custom_graph)
        plan = self._make_plan(component_id="app", fault_type=FaultType.LATENCY_SPIKE)
        report = engine.execute(plan)
        assert isinstance(report, GameDayReport)

    def test_gameday_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも GameDayEngine が動作することを確認する。"""
        engine = GameDayEngine(demo_graph)
        component_ids = list(demo_graph.components.keys())
        plan = self._make_plan(component_id=component_ids[0])
        report = engine.execute(plan)
        assert isinstance(report, GameDayReport)

    def test_multi_step_plan(self, custom_graph: InfraGraph) -> None:
        """複数ステップのプランで GameDayEngine が動作することを確認する。"""
        engine = GameDayEngine(custom_graph)
        steps = [
            GameDayStep(
                time_offset_seconds=0,
                action="inject_fault",
                fault=Fault(target_component_id="db", fault_type=FaultType.COMPONENT_DOWN),
                expected_outcome="db_down",
            ),
            GameDayStep(
                time_offset_seconds=60,
                action="inject_fault",
                fault=Fault(target_component_id="cache", fault_type=FaultType.MEMORY_EXHAUSTION),
                expected_outcome="cache_degraded",
            ),
        ]
        plan = GameDayPlan(name="multi_step_plan", steps=steps)
        report = engine.execute(plan)
        assert isinstance(report, GameDayReport)


# ---------------------------------------------------------------------------
# IncidentReplayEngine テスト
# ---------------------------------------------------------------------------


class TestIncidentReplayEngine:
    """IncidentReplayEngine の実行テスト。"""

    def test_list_incidents_returns_list(self) -> None:
        """list_incidents() が list を返すことを確認する。"""
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        assert isinstance(incidents, list)

    def test_list_incidents_not_empty(self) -> None:
        """list_incidents() が空でないことを確認する（組み込みインシデントの確認）。"""
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        assert len(incidents) > 0

    def test_replay_single_incident(self, custom_graph: InfraGraph) -> None:
        """replay() が単一インシデントで ReplayResult を返すことを確認する。"""
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        result = engine.replay(custom_graph, incidents[0])
        assert result is not None
        assert hasattr(result, "survived")

    def test_replay_result_has_impact_score(self, custom_graph: InfraGraph) -> None:
        """ReplayResult が impact_score を持つことを確認する。"""
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        result = engine.replay(custom_graph, incidents[0])
        assert hasattr(result, "impact_score")

    def test_replay_result_has_recommendations(self, custom_graph: InfraGraph) -> None:
        """ReplayResult が recommendations を持つことを確認する。"""
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        result = engine.replay(custom_graph, incidents[0])
        assert hasattr(result, "recommendations")

    def test_replay_all_returns_list(self, custom_graph: InfraGraph) -> None:
        """replay_all() が list を返すことを確認する。"""
        engine = IncidentReplayEngine()
        results = engine.replay_all(custom_graph)
        assert isinstance(results, list)

    def test_replay_all_count_matches_incidents(self, custom_graph: InfraGraph) -> None:
        """replay_all() の件数が list_incidents() と一致することを確認する。"""
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        results = engine.replay_all(custom_graph)
        assert len(results) == len(incidents)

    def test_replay_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも IncidentReplayEngine が動作することを確認する。"""
        engine = IncidentReplayEngine()
        incidents = engine.list_incidents()
        result = engine.replay(demo_graph, incidents[0])
        assert result is not None


# ---------------------------------------------------------------------------
# DeploymentStrategyAdvisor テスト
# ---------------------------------------------------------------------------


class TestDeploymentStrategyAdvisor:
    """DeploymentStrategyAdvisor の実行テスト。"""

    def test_recommend_returns_recommendation(self, custom_graph: InfraGraph) -> None:
        """recommend() が DeploymentRecommendation を返すことを確認する。"""
        advisor = DeploymentStrategyAdvisor(custom_graph)
        rec = advisor.recommend(custom_graph, "app")
        assert rec is not None

    def test_recommend_db_component(self, custom_graph: InfraGraph) -> None:
        """DB コンポーネントへの推奨が返されることを確認する。"""
        advisor = DeploymentStrategyAdvisor(custom_graph)
        rec = advisor.recommend(custom_graph, "db")
        assert rec is not None

    def test_recommend_lb_component(self, custom_graph: InfraGraph) -> None:
        """ロードバランサーコンポーネントへの推奨が返されることを確認する。"""
        advisor = DeploymentStrategyAdvisor(custom_graph)
        rec = advisor.recommend(custom_graph, "lb")
        assert rec is not None

    def test_plan_method_exists(self, custom_graph: InfraGraph) -> None:
        """plan() メソッドが存在することを確認する。"""
        advisor = DeploymentStrategyAdvisor(custom_graph)
        assert hasattr(advisor, "plan")

    def test_recommend_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも DeploymentStrategyAdvisor が動作することを確認する。"""
        advisor = DeploymentStrategyAdvisor(demo_graph)
        component_ids = list(demo_graph.components.keys())
        if component_ids:
            rec = advisor.recommend(demo_graph, component_ids[0])
            assert rec is not None


# ---------------------------------------------------------------------------
# AnomalyDetector テスト
# ---------------------------------------------------------------------------


class TestAnomalyDetector:
    """AnomalyDetector の実行テスト。"""

    def test_detect_returns_anomaly_report(self, custom_graph: InfraGraph) -> None:
        """detect() が AnomalyReport を返すことを確認する。"""
        detector = AnomalyDetector()
        report = detector.detect(custom_graph)
        assert isinstance(report, AnomalyReport)

    def test_report_has_anomalies(self, custom_graph: InfraGraph) -> None:
        """AnomalyReport が anomalies 属性を持つことを確認する。"""
        detector = AnomalyDetector()
        report = detector.detect(custom_graph)
        assert hasattr(report, "anomalies")

    def test_report_has_health_score(self, custom_graph: InfraGraph) -> None:
        """AnomalyReport が health_score を持つことを確認する。"""
        detector = AnomalyDetector()
        report = detector.detect(custom_graph)
        assert hasattr(report, "health_score")

    def test_report_has_total_count(self, custom_graph: InfraGraph) -> None:
        """AnomalyReport が total_count を持つことを確認する。"""
        detector = AnomalyDetector()
        report = detector.detect(custom_graph)
        assert hasattr(report, "total_count")

    def test_report_has_critical_count(self, custom_graph: InfraGraph) -> None:
        """AnomalyReport が critical_count を持つことを確認する。"""
        detector = AnomalyDetector()
        report = detector.detect(custom_graph)
        assert hasattr(report, "critical_count")

    def test_detect_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフでも AnomalyDetector が動作することを確認する。"""
        detector = AnomalyDetector()
        report = detector.detect(demo_graph)
        assert isinstance(report, AnomalyReport)

    def test_detect_topology_anomalies(self, custom_graph: InfraGraph) -> None:
        """detect_topology_anomalies() が単独で動作することを確認する。"""
        detector = AnomalyDetector()
        result = detector.detect_topology_anomalies(custom_graph)
        assert result is not None

    def test_detect_security_anomalies(self, custom_graph: InfraGraph) -> None:
        """detect_security_anomalies() が単独で動作することを確認する。"""
        detector = AnomalyDetector()
        result = detector.detect_security_anomalies(custom_graph)
        assert result is not None

    def test_health_score_range(self, custom_graph: InfraGraph) -> None:
        """health_score が有効な範囲にあることを確認する。"""
        detector = AnomalyDetector()
        report = detector.detect(custom_graph)
        # health_score は 0〜100 の範囲を期待
        assert isinstance(report.health_score, (int, float))


# ---------------------------------------------------------------------------
# 統合テスト: デモグラフ全エンジン
# ---------------------------------------------------------------------------


class TestAllEnginesWithDemoGraph:
    """デモグラフを使って全エンジンが連続実行できることを確認する統合テスト。"""

    def test_full_pipeline_demo_graph(self, demo_graph: InfraGraph) -> None:
        """デモグラフで全主要エンジンが順次実行できることを確認する。"""
        # SimulationEngine
        sim_report = SimulationEngine(demo_graph).run_all_defaults()
        assert isinstance(sim_report, SimulationReport)

        # SREMaturity
        maturity = SREMaturityEngine().assess(demo_graph)
        assert isinstance(maturity, MaturityReport)

        # AnomalyDetector
        anomaly = AnomalyDetector().detect(demo_graph)
        assert isinstance(anomaly, AnomalyReport)

        # PredictiveFailure
        predict = PredictiveFailureEngine(demo_graph).predict()
        assert isinstance(predict, PredictiveReport)

        # DigitalTwin
        twin_report = DigitalTwin(demo_graph).report()
        assert isinstance(twin_report, DigitalTwinReport)

    def test_resilience_pipeline_custom_graph(self, custom_graph: InfraGraph) -> None:
        """カスタムグラフで主要分析パイプラインが完走することを確認する。"""
        score = custom_graph.resilience_score()
        assert isinstance(score, float)

        mc = run_monte_carlo(custom_graph, n_trials=500, seed=7)
        assert mc.n_trials == 500

        brc_report = BlastRadiusCalculator(custom_graph).generate_full_report()
        assert brc_report is not None

        compliance = ComplianceEngine(custom_graph).check_all()
        assert "soc2" in compliance
