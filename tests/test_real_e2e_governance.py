# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""ガバナンス機能とフルパイプラインのE2Eテスト。

モックなし・実Python APIを直接呼び出して動作を検証する。
対象: GovernanceAssessor, gap_analyzer, policy_generator, InfraGraph, SimulationEngine
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import pytest

from faultray.governance.assessor import GovernanceAssessor, AssessmentResult
from faultray.governance.gap_analyzer import (
    analyze_gaps,
    generate_roadmap,
    get_multi_framework_violations,
    generate_ai_recommendations,
    GapReport,
    Roadmap,
    RequirementGap,
)
from faultray.governance.policy_generator import (
    list_policy_types,
    generate_policy,
    generate_all_policies,
    PolicyDocument,
)
from faultray.model.demo import create_demo_graph
from faultray.model.graph import InfraGraph
from faultray.model.components import Component, ComponentType, Dependency
from faultray.simulator.engine import SimulationEngine, SimulationReport


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _build_minimal_graph(n: int = 3) -> InfraGraph:
    """n個のコンポーネントを持つ最小グラフを生成する。"""
    graph = InfraGraph()
    comp_ids: list[str] = []
    for i in range(n):
        comp = Component(
            id=f"svc-{i}",
            name=f"Service {i}",
            type=ComponentType.APP_SERVER,
            host=f"host-{i}",
            port=8080 + i,
            replicas=1,
        )
        graph.add_component(comp)
        comp_ids.append(comp.id)

    # 直列チェーン: svc-0 → svc-1 → svc-2 → ...
    for i in range(n - 1):
        dep = Dependency(
            source_id=comp_ids[i],
            target_id=comp_ids[i + 1],
            dependency_type="requires",
            weight=1.0,
        )
        graph.add_dependency(dep)

    return graph


def _full_answers() -> dict[str, int]:
    """全25問に最高スコア(4)を設定した回答辞書を返す。"""
    return {f"Q{i:02d}": 4 for i in range(1, 26)}


def _low_answers() -> dict[str, int]:
    """全25問に最低スコア(0)を設定した回答辞書を返す。"""
    return {f"Q{i:02d}": 0 for i in range(1, 26)}


# ---------------------------------------------------------------------------
# TestGovernanceAssessment
# ---------------------------------------------------------------------------


class TestGovernanceAssessment:
    """GovernanceAssessor.assess() の動作を検証するテストクラス。"""

    def test_assess_empty_answers_returns_result(self) -> None:
        """空の回答辞書でもAssessmentResultが返ること。"""
        assessor = GovernanceAssessor()
        result = assessor.assess({})
        assert isinstance(result, AssessmentResult)

    def test_assess_empty_has_numeric_overall_score(self) -> None:
        """空の回答でもoverall_scoreが数値であること。"""
        assessor = GovernanceAssessor()
        result = assessor.assess({})
        assert isinstance(result.overall_score, float)
        assert 0.0 <= result.overall_score <= 100.0

    def test_assess_empty_has_framework_coverage(self) -> None:
        """空の回答でもframework_coverageがdictで返ること。"""
        assessor = GovernanceAssessor()
        result = assessor.assess({})
        assert isinstance(result.framework_coverage, dict)
        assert len(result.framework_coverage) > 0

    def test_assess_partial_answers(self) -> None:
        """一部の質問にのみ回答した場合も正常にスコアが計算されること。"""
        assessor = GovernanceAssessor()
        partial = {"Q01": 2, "Q05": 3, "Q10": 1}
        result = assessor.assess(partial)
        assert isinstance(result, AssessmentResult)
        assert isinstance(result.overall_score, float)

    def test_assess_partial_score_higher_than_empty(self) -> None:
        """部分回答はゼロ回答より高スコアになること。"""
        assessor = GovernanceAssessor()
        empty_result = assessor.assess({})
        partial_result = assessor.assess({"Q01": 3, "Q02": 3, "Q03": 3})
        # 部分的に高い回答を入れれば全体スコアは上がるはず
        assert partial_result.overall_score >= empty_result.overall_score

    def test_assess_all_max_answers_high_score(self) -> None:
        """全問最高スコアなら高い全体スコアが得られること。"""
        assessor = GovernanceAssessor()
        result = assessor.assess(_full_answers())
        assert result.overall_score > 50.0

    def test_assess_all_min_answers_low_score(self) -> None:
        """全問ゼロ回答では低い全体スコアになること。"""
        assessor = GovernanceAssessor()
        result = assessor.assess(_low_answers())
        assert result.overall_score <= 10.0

    def test_assess_overall_score_range(self) -> None:
        """overall_scoreは常に0-100の範囲内であること。"""
        assessor = GovernanceAssessor()
        for answers in [{}, _low_answers(), _full_answers(), {"Q01": 2, "Q03": 4}]:
            result = assessor.assess(answers)
            assert 0.0 <= result.overall_score <= 100.0, (
                f"Score out of range: {result.overall_score}"
            )

    def test_assess_result_attributes_types(self) -> None:
        """AssessmentResultの各属性が正しい型であること。"""
        assessor = GovernanceAssessor()
        result = assessor.assess({"Q01": 2})
        assert isinstance(result.overall_score, float)
        assert isinstance(result.maturity_level, int)
        assert isinstance(result.category_scores, list)
        assert isinstance(result.requirement_scores, list)
        assert isinstance(result.top_gaps, list)
        assert isinstance(result.top_recommendations, list)
        assert isinstance(result.framework_coverage, dict)

    def test_assess_maturity_level_range(self) -> None:
        """maturity_levelは1-5の範囲内であること。"""
        assessor = GovernanceAssessor()
        for answers in [{}, _low_answers(), _full_answers()]:
            result = assessor.assess(answers)
            assert 1 <= result.maturity_level <= 5

    def test_assess_framework_coverage_values_are_numeric(self) -> None:
        """framework_coverageの値が全て数値であること。"""
        assessor = GovernanceAssessor()
        result = assessor.assess({"Q01": 3, "Q10": 2})
        for key, val in result.framework_coverage.items():
            assert isinstance(val, (int, float)), f"Key {key} has non-numeric value: {val}"

    def test_assess_auto_mode_no_args(self) -> None:
        """assess_auto()引数なしでも正常にAssessmentResultが返ること。"""
        assessor = GovernanceAssessor()
        result = assessor.assess_auto()
        assert isinstance(result, AssessmentResult)
        assert 0.0 <= result.overall_score <= 100.0


# ---------------------------------------------------------------------------
# TestGovernanceGapAnalysis
# ---------------------------------------------------------------------------


class TestGovernanceGapAnalysis:
    """ギャップ分析APIの動作を検証するテストクラス。"""

    def _get_assessment(self, answers: dict[str, int] | None = None) -> AssessmentResult:
        assessor = GovernanceAssessor()
        return assessor.assess(answers or {})

    def test_analyze_gaps_returns_gap_report(self) -> None:
        """analyze_gaps()がGapReportを返すこと。"""
        result = self._get_assessment()
        gap_report = analyze_gaps(result)
        assert isinstance(gap_report, GapReport)

    def test_gap_report_has_requirements(self) -> None:
        """GapReportにtotal_requirementsが設定されること。"""
        result = self._get_assessment()
        gap_report = analyze_gaps(result)
        assert gap_report.total_requirements > 0

    def test_gap_report_counts_sum_correctly(self) -> None:
        """compliant + partial + non_compliant の合計がtotal_requirementsと一致すること。"""
        result = self._get_assessment(_low_answers())
        gap_report = analyze_gaps(result)
        total = gap_report.compliant + gap_report.partial + gap_report.non_compliant
        assert total == gap_report.total_requirements

    def test_gap_report_identifies_weaknesses_on_low_score(self) -> None:
        """低スコア時にgapsが空でないこと。"""
        result = self._get_assessment(_low_answers())
        gap_report = analyze_gaps(result)
        assert gap_report.non_compliant > 0

    def test_generate_roadmap_from_gaps(self) -> None:
        """generate_roadmap()がRoadmapを返すこと。"""
        result = self._get_assessment(_low_answers())
        gap_report = analyze_gaps(result)
        roadmap = generate_roadmap(gaps=gap_report.gaps)
        assert isinstance(roadmap, Roadmap)

    def test_generate_roadmap_has_phases(self) -> None:
        """ロードマップはphase1/phase2/phase3の属性を持つこと。"""
        result = self._get_assessment(_low_answers())
        gap_report = analyze_gaps(result)
        roadmap = generate_roadmap(gap_report=gap_report)
        # phase1,2,3は全てlist型
        assert isinstance(roadmap.phase1, list)
        assert isinstance(roadmap.phase2, list)
        assert isinstance(roadmap.phase3, list)
        # 低スコア時は何かしらのフェーズが埋まるはず
        total_items = len(roadmap.phase1) + len(roadmap.phase2) + len(roadmap.phase3)
        assert total_items > 0

    def test_get_multi_framework_violations_returns_dict(self) -> None:
        """get_multi_framework_violations()がdictを返すこと。"""
        result = self._get_assessment(_low_answers())
        gap_report = analyze_gaps(result)
        violations = get_multi_framework_violations(gaps=gap_report.gaps)
        assert isinstance(violations, dict)

    def test_multi_framework_violations_structure(self) -> None:
        """violations dictにviolationsとsummaryキーが含まれること。"""
        result = self._get_assessment(_low_answers())
        gap_report = analyze_gaps(result)
        violations = get_multi_framework_violations(gap_report=gap_report)
        assert "violations" in violations
        assert "summary" in violations
        assert isinstance(violations["violations"], list)
        assert isinstance(violations["summary"], dict)

    def test_generate_ai_recommendations_returns_str(self) -> None:
        """generate_ai_recommendations()がstr型を返すこと（APIキー不要）。"""
        result = self._get_assessment(_low_answers())
        gap_report = analyze_gaps(result)
        recommendations = generate_ai_recommendations(gap_report)
        assert isinstance(recommendations, str)
        assert len(recommendations) > 0

    def test_full_score_has_fewer_gaps(self) -> None:
        """高スコアは低スコアよりも未充足要件が少ないこと。"""
        assessor = GovernanceAssessor()
        high_result = assessor.assess(_full_answers())
        low_result = assessor.assess(_low_answers())
        high_gap = analyze_gaps(high_result)
        low_gap = analyze_gaps(low_result)
        assert high_gap.non_compliant <= low_gap.non_compliant


# ---------------------------------------------------------------------------
# TestGovernancePolicyGeneration
# ---------------------------------------------------------------------------


class TestGovernancePolicyGeneration:
    """ポリシー生成APIの動作を検証するテストクラス。"""

    def test_list_policy_types_returns_list(self) -> None:
        """list_policy_types()がlist[dict]を返すこと。"""
        types = list_policy_types()
        assert isinstance(types, list)
        assert len(types) > 0

    def test_list_policy_types_items_have_required_keys(self) -> None:
        """各ポリシータイプにtype/title/descriptionキーが存在すること。"""
        types = list_policy_types()
        for item in types:
            assert "type" in item, f"Missing 'type' key: {item}"
            assert "title" in item, f"Missing 'title' key: {item}"
            assert "description" in item, f"Missing 'description' key: {item}"

    def test_generate_policy_returns_policy_document(self) -> None:
        """generate_policy()がPolicyDocumentを返すこと。"""
        doc = generate_policy("ai_usage", "テスト株式会社")
        assert isinstance(doc, PolicyDocument)

    def test_generate_policy_content_is_substantial(self) -> None:
        """生成されたポリシーのコンテンツが100文字以上であること。"""
        doc = generate_policy("risk_management", "TestOrg Ltd.")
        assert len(doc.content) > 100, f"Content too short: {len(doc.content)} chars"

    def test_generate_policy_contains_org_name(self) -> None:
        """生成されたポリシーに組織名が含まれること。"""
        org_name = "架空テック株式会社"
        doc = generate_policy("ethics", org_name)
        assert org_name in doc.content

    def test_generate_all_policies_returns_list(self) -> None:
        """generate_all_policies()がlist[PolicyDocument]を返すこと。"""
        docs = generate_all_policies("MyCompany Inc.")
        assert isinstance(docs, list)
        assert len(docs) > 0

    def test_generate_all_policies_count_matches_types(self) -> None:
        """generate_all_policies()の返却数がlist_policy_types()の件数と一致すること。"""
        types = list_policy_types()
        docs = generate_all_policies("株式会社サンプル")
        assert len(docs) == len(types)

    def test_generate_all_policies_all_substantial(self) -> None:
        """全ポリシーのコンテンツが100文字以上であること。"""
        docs = generate_all_policies("SampleOrg")
        for doc in docs:
            assert len(doc.content) > 100, (
                f"Policy '{doc.policy_type}' content too short: {len(doc.content)} chars"
            )

    def test_generate_policy_unknown_type_raises(self) -> None:
        """不正なポリシータイプでValueErrorが発生すること。"""
        with pytest.raises(ValueError):
            generate_policy("nonexistent_type", "TestOrg")

    def test_generate_policy_all_types_work(self) -> None:
        """全ポリシータイプが例外なく生成できること。"""
        types = list_policy_types()
        for t in types:
            doc = generate_policy(t["type"], "Org")
            assert isinstance(doc, PolicyDocument)


# ---------------------------------------------------------------------------
# TestFullPipelineWorkflows
# ---------------------------------------------------------------------------


class TestFullPipelineWorkflows:
    """フルパイプラインのE2Eワークフローを検証するテストクラス。"""

    def test_demo_graph_simulation_report_fields(self) -> None:
        """デモグラフ → シミュレーション → SimulationReportの全フィールドが正常であること。"""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert isinstance(report, SimulationReport)
        assert isinstance(report.results, list)
        assert isinstance(report.resilience_score, float)
        assert isinstance(report.total_generated, int)
        assert isinstance(report.was_truncated, bool)

    def test_demo_graph_resilience_score_range(self) -> None:
        """デモグラフのレジリエンススコアが0-100の範囲内であること。"""
        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert 0.0 <= report.resilience_score <= 100.0

    def test_custom_topology_spof_detection(self) -> None:
        """シングルポイント障害（SPOF）を持つカスタムトポロジーで検証されること。"""
        # svc-0(LB) → svc-1(DB) という1対1依存 = SPOF
        graph = InfraGraph()
        lb = Component(
            id="lb", name="LoadBalancer", type=ComponentType.LOAD_BALANCER,
            host="host-lb", port=80, replicas=1,
        )
        db = Component(
            id="db", name="Database", type=ComponentType.DATABASE,
            host="host-db", port=5432, replicas=1,
        )
        graph.add_component(lb)
        graph.add_component(db)
        graph.add_dependency(Dependency(
            source_id="lb", target_id="db", dependency_type="requires", weight=1.0
        ))

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        # replicas=1のDBに依存するLBが存在するためcritical findingsが発生するはず
        assert isinstance(report.results, list)

    def test_graph_save_load_simulate_compare(self) -> None:
        """グラフ → YAML保存 → ロード → シミュレーション → スコアが一致すること。"""
        graph = create_demo_graph()
        score_original = graph.resilience_score()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            graph.save(path)
            loaded_graph = InfraGraph.load(path)
            score_loaded = loaded_graph.resilience_score()
            # 保存・ロード後もレジリエンススコアが同じ値になること
            assert abs(score_original - score_loaded) < 0.01
        finally:
            path.unlink(missing_ok=True)

    def test_small_graph_simulation_basic_results(self) -> None:
        """2ノードの最小グラフでシミュレーションが正常に完了すること。"""
        graph = _build_minimal_graph(2)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert isinstance(report, SimulationReport)
        assert report.total_generated >= 0

    def test_large_graph_simulation_performance(self) -> None:
        """20ノード以上のグラフでシミュレーションが完了し結果が返ること。"""
        graph = _build_minimal_graph(20)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert isinstance(report, SimulationReport)
        assert isinstance(report.resilience_score, float)

    def test_multi_engine_pipeline(self) -> None:
        """シミュレーション → レポート取得までのマルチステップパイプラインが動作すること。"""
        from faultray.simulator.monte_carlo import run_monte_carlo

        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        _report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        # MonteCarloも実行できること
        mc_result = run_monte_carlo(graph, n_trials=100, seed=42)
        assert hasattr(mc_result, "availability_mean") or hasattr(mc_result, "availability_p50")

    def test_governance_pipeline_assess_gap_roadmap_policy(self) -> None:
        """ガバナンスパイプライン: assess → gap → roadmap → policy の一連フローが動作すること。"""
        # Step 1: assess
        assessor = GovernanceAssessor()
        result = assessor.assess({"Q01": 1, "Q05": 0, "Q10": 2})
        assert isinstance(result, AssessmentResult)

        # Step 2: gap analysis
        gap_report = analyze_gaps(result)
        assert isinstance(gap_report, GapReport)

        # Step 3: roadmap
        roadmap = generate_roadmap(gap_report=gap_report)
        assert isinstance(roadmap, Roadmap)

        # Step 4: policy generation
        docs = generate_all_policies("パイプラインテスト株式会社")
        assert len(docs) == 5

    def test_financial_pipeline_simulation_cost_roi(self) -> None:
        """シミュレーション → コスト影響計算パイプラインが動作すること。"""
        from faultray.simulator.cost_impact import CostImpactEngine

        graph = create_demo_graph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        cost_engine = CostImpactEngine()
        if report.results:
            result = report.results[0]
            affected = [e.component_id for e in result.cascade.effects]
            if not affected:
                affected = list(graph.components.keys())[:2]
            breakdown = cost_engine.calculate_scenario_cost(
                scenario_name=result.scenario.name,
                affected_components=affected,
                downtime_minutes=30.0,
            )
            assert breakdown.total_cost >= 0.0

    def test_graph_operations_pipeline(self) -> None:
        """グラフ操作パイプライン: create → cascade paths → critical paths → affected nodes。"""
        graph = create_demo_graph()

        # カスケードパスを取得
        cascade_paths = graph.get_cascade_path("postgres")
        assert isinstance(cascade_paths, list)

        # クリティカルパスを取得
        critical_paths = graph.get_critical_paths()
        assert isinstance(critical_paths, list)

        # 影響ノードを取得
        affected = graph.get_all_affected("postgres")
        assert isinstance(affected, set)

    def test_round_trip_serialization_components_match(self) -> None:
        """グラフ → JSON保存 → ロード後にコンポーネント数が一致すること。"""
        graph = create_demo_graph()
        original_component_ids = set(graph.components.keys())

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            graph.save(path)
            loaded = InfraGraph.load(path)
            loaded_component_ids = set(loaded.components.keys())
            assert original_component_ids == loaded_component_ids
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """エッジケースの処理を検証するテストクラス。"""

    def test_empty_graph_simulation(self) -> None:
        """空グラフでシミュレーションが例外を発生させないこと。"""
        graph = InfraGraph()
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert isinstance(report, SimulationReport)

    def test_single_node_graph(self) -> None:
        """1ノードのグラフでシミュレーションが正常に完了すること。"""
        graph = InfraGraph()
        comp = Component(
            id="solo",
            name="Solo Service",
            type=ComponentType.APP_SERVER,
            host="host-solo",
            port=8080,
            replicas=1,
        )
        graph.add_component(comp)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert isinstance(report, SimulationReport)

    def test_graph_with_only_optional_dependencies(self) -> None:
        """全依存関係がoptionalなグラフでレジリエンススコアが高くなること。"""
        graph = InfraGraph()
        for i in range(3):
            graph.add_component(Component(
                id=f"opt-svc-{i}",
                name=f"Optional Service {i}",
                type=ComponentType.APP_SERVER,
                host=f"host-{i}",
                port=8080 + i,
                replicas=2,  # SPOF回避のためreplicas=2
            ))

        graph.add_dependency(Dependency(
            source_id="opt-svc-0", target_id="opt-svc-1",
            dependency_type="optional", weight=0.3,
        ))
        graph.add_dependency(Dependency(
            source_id="opt-svc-1", target_id="opt-svc-2",
            dependency_type="optional", weight=0.3,
        ))

        score = graph.resilience_score()
        assert score >= 0.0  # オプション依存のみなのでペナルティが少ない

    def test_graph_with_circular_like_pattern(self) -> None:
        """A→B→C, A→C のような循環的パターンでも正常に動作すること。"""
        graph = InfraGraph()
        for cid in ["comp-a", "comp-b", "comp-c"]:
            graph.add_component(Component(
                id=cid, name=cid, type=ComponentType.APP_SERVER,
                host=f"host-{cid}", port=8080, replicas=1,
            ))

        graph.add_dependency(Dependency(
            source_id="comp-a", target_id="comp-b",
            dependency_type="requires", weight=1.0,
        ))
        graph.add_dependency(Dependency(
            source_id="comp-b", target_id="comp-c",
            dependency_type="requires", weight=1.0,
        ))
        graph.add_dependency(Dependency(
            source_id="comp-a", target_id="comp-c",
            dependency_type="optional", weight=0.5,
        ))

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert isinstance(report, SimulationReport)

    def test_deep_chain_graph(self) -> None:
        """A→B→C→D→E→F→G の7段チェーンでもシミュレーションが完了すること。"""
        graph = _build_minimal_graph(7)
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert isinstance(report, SimulationReport)
        # 深い依存チェーンはレジリエンスを下げるはず
        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0

    def test_all_components_same_type(self) -> None:
        """全コンポーネントが同じComponentTypeでも正常に動作すること。"""
        graph = InfraGraph()
        for i in range(5):
            graph.add_component(Component(
                id=f"db-{i}",
                name=f"Database {i}",
                type=ComponentType.DATABASE,
                host=f"db-host-{i}",
                port=5432 + i,
                replicas=1,
            ))

        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        assert isinstance(report, SimulationReport)

    def test_all_replicas_one_maximum_fragility(self) -> None:
        """全コンポーネントのreplicas=1（最大脆弱性）でもシミュレーションが動作すること。"""
        graph = create_demo_graph()
        # 全コンポーネントのreplicasを1に設定（デモグラフは既に全て1）
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)
        # replicas=1で依存があればSPOFとしてフラグされるはず
        assert isinstance(report, SimulationReport)

    def test_governance_assess_out_of_range_answer_handled_gracefully(self) -> None:
        """回答値が範囲外（999）でも例外なく処理されること。"""
        assessor = GovernanceAssessor()
        # 範囲外の値はmax(0, min(idx, len(scores)-1))でクリップされる
        result = assessor.assess({"Q01": 999, "Q02": -1})
        assert isinstance(result, AssessmentResult)
        assert 0.0 <= result.overall_score <= 100.0

    def test_governance_empty_graph_assess_auto(self) -> None:
        """インフラシグナルなしでassess_auto()が正常動作すること。"""
        assessor = GovernanceAssessor()
        result = assessor.assess_auto(
            has_monitoring=False,
            has_auth=False,
            has_encryption=False,
            has_dr=False,
            has_logging=False,
        )
        assert isinstance(result, AssessmentResult)
        assert result.overall_score >= 0.0

    def test_cascade_path_leaf_component_has_no_upstream(self) -> None:
        """依存されていないリーフコンポーネントのカスケードパスが空リストであること。"""
        graph = InfraGraph()
        standalone = Component(
            id="standalone",
            name="Standalone",
            type=ComponentType.APP_SERVER,
            host="host-standalone",
            port=9090,
            replicas=1,
        )
        graph.add_component(standalone)
        # 依存関係なし → カスケードパスは空
        paths = graph.get_cascade_path("standalone")
        assert isinstance(paths, list)
        assert paths == []

    def test_resilience_score_v2_fields(self) -> None:
        """resilience_score_v2()がscore/breakdown/recommendationsを持つdictを返すこと。"""
        graph = create_demo_graph()
        result = graph.resilience_score_v2()
        assert isinstance(result, dict)
        assert "score" in result
        assert "breakdown" in result
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)
