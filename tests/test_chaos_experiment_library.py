"""Tests for chaos_experiment_library module — Chaos Experiment Template Library."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.chaos_experiment_library import (
    ChaosExperimentLibraryEngine,
    CoverageReport,
    Difficulty,
    ExperimentCategory,
    ExperimentPlan,
    ExperimentPlanEntry,
    ExperimentRecommendation,
    ExperimentTemplate,
    PrerequisiteCheck,
    _BUILTIN_TEMPLATES,
    _COMPONENT_CATEGORY_RELEVANCE,
    _TEMPLATE_INDEX,
    _check_prerequisite,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str = "",
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
    *,
    failover: bool = False,
    autoscaling: bool = False,
    backup: bool = False,
    rate_limiting: bool = False,
    encryption_at_rest: bool = False,
    encryption_in_transit: bool = False,
    network_segmented: bool = False,
) -> Component:
    return Component(
        id=cid,
        name=name or cid,
        type=ctype,
        replicas=replicas,
        health=health,
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling, min_replicas=1, max_replicas=4 if autoscaling else 1),
        security=SecurityProfile(
            backup_enabled=backup,
            rate_limiting=rate_limiting,
            encryption_at_rest=encryption_at_rest,
            encryption_in_transit=encryption_in_transit,
            network_segmented=network_segmented,
        ),
    )


def _dep(src: str, tgt: str, *, cb: bool = False) -> Dependency:
    return Dependency(
        source_id=src,
        target_id=tgt,
        circuit_breaker=CircuitBreakerConfig(enabled=cb),
    )


def _graph(*comps: Component, deps: list[Dependency] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    for d in deps or []:
        g.add_dependency(d)
    return g


def _make_template(
    tid: str = "test-001",
    name: str = "Test Template",
    category: ExperimentCategory = ExperimentCategory.AVAILABILITY,
    difficulty: Difficulty = Difficulty.BEGINNER,
    **kwargs,
) -> ExperimentTemplate:
    defaults = dict(
        id=tid,
        name=name,
        category=category,
        difficulty=difficulty,
        description="A test template.",
        hypothesis="System handles this.",
        steady_state="All healthy.",
        injection_method="Inject something.",
        expected_outcome="Graceful handling.",
        rollback_steps=["Undo"],
        applicable_component_types=["app_server"],
        estimated_duration_minutes=10,
        blast_radius="single node",
        prerequisites=[],
        tags=["test"],
    )
    defaults.update(kwargs)
    return ExperimentTemplate(**defaults)


# ===========================================================================
# Enum tests
# ===========================================================================


class TestExperimentCategory:
    def test_all_values(self):
        expected = {"availability", "latency", "data", "security", "capacity", "dependency", "state", "configuration"}
        assert {e.value for e in ExperimentCategory} == expected

    def test_str_enum(self):
        assert ExperimentCategory.AVAILABILITY == "availability"
        assert isinstance(ExperimentCategory.LATENCY, str)

    def test_member_count(self):
        assert len(ExperimentCategory) == 8

    def test_from_value(self):
        assert ExperimentCategory("security") == ExperimentCategory.SECURITY


class TestDifficulty:
    def test_all_values(self):
        expected = {"beginner", "intermediate", "advanced", "expert"}
        assert {e.value for e in Difficulty} == expected

    def test_str_enum(self):
        assert Difficulty.BEGINNER == "beginner"
        assert isinstance(Difficulty.EXPERT, str)

    def test_member_count(self):
        assert len(Difficulty) == 4

    def test_from_value(self):
        assert Difficulty("expert") == Difficulty.EXPERT


# ===========================================================================
# ExperimentTemplate model tests
# ===========================================================================


class TestExperimentTemplate:
    def test_create_minimal(self):
        t = _make_template()
        assert t.id == "test-001"
        assert t.name == "Test Template"
        assert t.category == ExperimentCategory.AVAILABILITY
        assert t.difficulty == Difficulty.BEGINNER

    def test_all_fields_populated(self):
        t = _make_template(
            description="desc",
            hypothesis="hyp",
            steady_state="ss",
            injection_method="im",
            expected_outcome="eo",
            rollback_steps=["a", "b"],
            applicable_component_types=["database", "cache"],
            estimated_duration_minutes=30,
            blast_radius="cluster",
            prerequisites=["monitoring"],
            tags=["a", "b"],
        )
        assert t.rollback_steps == ["a", "b"]
        assert t.applicable_component_types == ["database", "cache"]
        assert t.estimated_duration_minutes == 30
        assert t.blast_radius == "cluster"
        assert t.prerequisites == ["monitoring"]
        assert t.tags == ["a", "b"]

    def test_empty_lists(self):
        t = _make_template(rollback_steps=[], prerequisites=[], tags=[])
        assert t.rollback_steps == []
        assert t.prerequisites == []
        assert t.tags == []

    def test_serialization_round_trip(self):
        t = _make_template()
        data = t.model_dump()
        t2 = ExperimentTemplate(**data)
        assert t2 == t

    def test_json_round_trip(self):
        t = _make_template()
        json_str = t.model_dump_json()
        t2 = ExperimentTemplate.model_validate_json(json_str)
        assert t2.id == t.id


# ===========================================================================
# ExperimentRecommendation model tests
# ===========================================================================


class TestExperimentRecommendation:
    def test_create(self):
        tmpl = _make_template()
        rec = ExperimentRecommendation(
            template=tmpl,
            target_component="web-1",
            relevance_score=0.85,
            reason="High relevance",
            priority="critical",
        )
        assert rec.target_component == "web-1"
        assert rec.relevance_score == 0.85
        assert rec.priority == "critical"

    def test_relevance_score_bounds_low(self):
        with pytest.raises(Exception):
            ExperimentRecommendation(
                template=_make_template(),
                target_component="x",
                relevance_score=-0.1,
                reason="r",
                priority="low",
            )

    def test_relevance_score_bounds_high(self):
        with pytest.raises(Exception):
            ExperimentRecommendation(
                template=_make_template(),
                target_component="x",
                relevance_score=1.1,
                reason="r",
                priority="low",
            )

    def test_relevance_score_zero(self):
        rec = ExperimentRecommendation(
            template=_make_template(),
            target_component="x",
            relevance_score=0.0,
            reason="r",
            priority="low",
        )
        assert rec.relevance_score == 0.0

    def test_relevance_score_one(self):
        rec = ExperimentRecommendation(
            template=_make_template(),
            target_component="x",
            relevance_score=1.0,
            reason="r",
            priority="low",
        )
        assert rec.relevance_score == 1.0

    def test_default_relevance_score(self):
        rec = ExperimentRecommendation(
            template=_make_template(),
            target_component="x",
            reason="r",
            priority="low",
        )
        assert rec.relevance_score == 0.0


# ===========================================================================
# ExperimentPlan model tests
# ===========================================================================


class TestExperimentPlan:
    def test_empty_plan(self):
        plan = ExperimentPlan()
        assert plan.entries == []
        assert plan.total_estimated_minutes == 0
        assert plan.categories_covered == []
        assert plan.components_covered == []

    def test_plan_with_entries(self):
        entry = ExperimentPlanEntry(
            order=1,
            template=_make_template(),
            target_component="web-1",
            reason="reason",
            priority="high",
        )
        plan = ExperimentPlan(
            entries=[entry],
            total_estimated_minutes=10,
            categories_covered=["availability"],
            components_covered=["web-1"],
        )
        assert len(plan.entries) == 1
        assert plan.total_estimated_minutes == 10


# ===========================================================================
# PrerequisiteCheck model tests
# ===========================================================================


class TestPrerequisiteCheck:
    def test_all_met(self):
        pc = PrerequisiteCheck(
            template_id="t1",
            satisfied=True,
            met=["monitoring", "replicas > 1"],
            unmet=[],
        )
        assert pc.satisfied is True

    def test_some_unmet(self):
        pc = PrerequisiteCheck(
            template_id="t1",
            satisfied=False,
            met=["monitoring"],
            unmet=["replicas > 1"],
        )
        assert pc.satisfied is False

    def test_with_warnings(self):
        pc = PrerequisiteCheck(
            template_id="t1",
            warnings=["expert level"],
        )
        assert len(pc.warnings) == 1


# ===========================================================================
# CoverageReport model tests
# ===========================================================================


class TestCoverageReport:
    def test_empty(self):
        cr = CoverageReport()
        assert cr.total_components == 0
        assert cr.coverage_percent == 0.0

    def test_full_coverage(self):
        cr = CoverageReport(
            total_components=3,
            covered_components=3,
            coverage_percent=100.0,
            categories_tested=["availability", "latency"],
            categories_untested=[],
        )
        assert cr.coverage_percent == 100.0


# ===========================================================================
# Built-in template library tests
# ===========================================================================


class TestBuiltinTemplates:
    def test_minimum_count(self):
        assert len(_BUILTIN_TEMPLATES) >= 20

    def test_all_categories_covered(self):
        cats = {t.category for t in _BUILTIN_TEMPLATES}
        for cat in ExperimentCategory:
            assert cat in cats, f"Category {cat.value} not covered"

    def test_unique_ids(self):
        ids = [t.id for t in _BUILTIN_TEMPLATES]
        assert len(ids) == len(set(ids))

    def test_index_matches_list(self):
        assert len(_TEMPLATE_INDEX) == len(_BUILTIN_TEMPLATES)
        for t in _BUILTIN_TEMPLATES:
            assert _TEMPLATE_INDEX[t.id] is t

    def test_all_have_rollback_steps(self):
        for t in _BUILTIN_TEMPLATES:
            assert len(t.rollback_steps) > 0, f"Template {t.id} missing rollback steps"

    def test_all_have_applicable_types(self):
        for t in _BUILTIN_TEMPLATES:
            assert len(t.applicable_component_types) > 0, f"Template {t.id} missing applicable types"

    def test_all_have_positive_duration(self):
        for t in _BUILTIN_TEMPLATES:
            assert t.estimated_duration_minutes > 0, f"Template {t.id} has zero duration"

    def test_all_have_description(self):
        for t in _BUILTIN_TEMPLATES:
            assert len(t.description) > 0

    def test_all_have_hypothesis(self):
        for t in _BUILTIN_TEMPLATES:
            assert len(t.hypothesis) > 0

    def test_all_have_tags(self):
        for t in _BUILTIN_TEMPLATES:
            assert len(t.tags) > 0

    def test_difficulty_distribution(self):
        diffs = {d: 0 for d in Difficulty}
        for t in _BUILTIN_TEMPLATES:
            diffs[t.difficulty] += 1
        # At least one template per difficulty
        for d, count in diffs.items():
            assert count >= 1, f"No template for difficulty {d.value}"

    def test_component_type_relevance_map_complete(self):
        for ct in ComponentType:
            assert ct.value in _COMPONENT_CATEGORY_RELEVANCE


# ===========================================================================
# Engine — constructor tests
# ===========================================================================


class TestEngineInit:
    def test_default_templates(self):
        engine = ChaosExperimentLibraryEngine()
        assert engine.template_count >= 20

    def test_custom_templates(self):
        ts = [_make_template("c1"), _make_template("c2")]
        engine = ChaosExperimentLibraryEngine(templates=ts)
        assert engine.template_count == 2

    def test_empty_templates(self):
        engine = ChaosExperimentLibraryEngine(templates=[])
        assert engine.template_count == 0

    def test_templates_property_returns_copy(self):
        engine = ChaosExperimentLibraryEngine()
        t1 = engine.templates
        t2 = engine.templates
        assert t1 == t2
        assert t1 is not t2  # distinct list objects


# ===========================================================================
# Engine — list_templates
# ===========================================================================


class TestListTemplates:
    def test_no_filter(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.list_templates()
        assert len(result) == engine.template_count

    def test_filter_by_category(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.list_templates(category=ExperimentCategory.AVAILABILITY)
        assert len(result) > 0
        assert all(t.category == ExperimentCategory.AVAILABILITY for t in result)

    def test_filter_by_difficulty(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.list_templates(difficulty=Difficulty.BEGINNER)
        assert len(result) > 0
        assert all(t.difficulty == Difficulty.BEGINNER for t in result)

    def test_filter_both(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.list_templates(
            category=ExperimentCategory.AVAILABILITY,
            difficulty=Difficulty.BEGINNER,
        )
        assert len(result) > 0
        for t in result:
            assert t.category == ExperimentCategory.AVAILABILITY
            assert t.difficulty == Difficulty.BEGINNER

    def test_filter_no_match(self):
        engine = ChaosExperimentLibraryEngine(templates=[
            _make_template(category=ExperimentCategory.DATA, difficulty=Difficulty.EXPERT),
        ])
        result = engine.list_templates(category=ExperimentCategory.LATENCY)
        assert result == []

    def test_filter_category_none_difficulty_set(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.list_templates(difficulty=Difficulty.EXPERT)
        assert all(t.difficulty == Difficulty.EXPERT for t in result)

    def test_each_category_returns_results(self):
        engine = ChaosExperimentLibraryEngine()
        for cat in ExperimentCategory:
            result = engine.list_templates(category=cat)
            assert len(result) >= 1, f"No templates for {cat.value}"


# ===========================================================================
# Engine — get_template
# ===========================================================================


class TestGetTemplate:
    def test_existing(self):
        engine = ChaosExperimentLibraryEngine()
        t = engine.get_template("avail-001")
        assert t is not None
        assert t.id == "avail-001"

    def test_non_existing(self):
        engine = ChaosExperimentLibraryEngine()
        assert engine.get_template("non-existent") is None

    def test_all_builtin_retrievable(self):
        engine = ChaosExperimentLibraryEngine()
        for tmpl in _BUILTIN_TEMPLATES:
            assert engine.get_template(tmpl.id) is not None

    def test_custom_engine(self):
        t = _make_template("custom-1")
        engine = ChaosExperimentLibraryEngine(templates=[t])
        assert engine.get_template("custom-1") is not None
        assert engine.get_template("avail-001") is None


# ===========================================================================
# Engine — filter_by_component_type
# ===========================================================================


class TestFilterByComponentType:
    def test_app_server(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("app_server")
        assert len(result) > 0
        for t in result:
            assert "app_server" in [a.lower() for a in t.applicable_component_types]

    def test_database(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("database")
        assert len(result) > 0

    def test_case_insensitive(self):
        engine = ChaosExperimentLibraryEngine()
        r1 = engine.filter_by_component_type("APP_SERVER")
        r2 = engine.filter_by_component_type("app_server")
        assert len(r1) == len(r2)

    def test_no_match(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("nonexistent_type")
        assert result == []

    def test_cache(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("cache")
        assert len(result) > 0

    def test_queue(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("queue")
        assert len(result) > 0

    def test_dns(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("dns")
        assert len(result) > 0

    def test_load_balancer(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("load_balancer")
        assert len(result) > 0

    def test_external_api(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("external_api")
        assert len(result) > 0

    def test_storage(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("storage")
        assert len(result) > 0

    def test_web_server(self):
        engine = ChaosExperimentLibraryEngine()
        result = engine.filter_by_component_type("web_server")
        assert len(result) > 0


# ===========================================================================
# Engine — recommend_experiments
# ===========================================================================


class TestRecommendExperiments:
    def test_empty_graph(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph()
        recs = engine.recommend_experiments(g)
        assert recs == []

    def test_single_component(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("app1", ctype=ComponentType.APP_SERVER))
        recs = engine.recommend_experiments(g)
        assert len(recs) > 0
        assert all(r.target_component == "app1" for r in recs)

    def test_multiple_components(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(
            _comp("app1", ctype=ComponentType.APP_SERVER),
            _comp("db1", ctype=ComponentType.DATABASE),
        )
        recs = engine.recommend_experiments(g)
        targets = {r.target_component for r in recs}
        assert "app1" in targets
        assert "db1" in targets

    def test_sorted_by_relevance_descending(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(
            _comp("app1", ctype=ComponentType.APP_SERVER),
            _comp("db1", ctype=ComponentType.DATABASE),
        )
        recs = engine.recommend_experiments(g)
        scores = [r.relevance_score for r in recs]
        assert scores == sorted(scores, reverse=True)

    def test_relevance_scores_in_bounds(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(
            _comp("app1", ctype=ComponentType.APP_SERVER),
            _comp("cache1", ctype=ComponentType.CACHE),
        )
        recs = engine.recommend_experiments(g)
        for r in recs:
            assert 0.0 <= r.relevance_score <= 1.0

    def test_degraded_component_higher_score(self):
        engine = ChaosExperimentLibraryEngine()
        g_healthy = _graph(_comp("a1", ctype=ComponentType.APP_SERVER, health=HealthStatus.HEALTHY))
        g_degraded = _graph(_comp("a1", ctype=ComponentType.APP_SERVER, health=HealthStatus.DEGRADED))
        recs_h = engine.recommend_experiments(g_healthy)
        recs_d = engine.recommend_experiments(g_degraded)
        avg_h = sum(r.relevance_score for r in recs_h) / max(len(recs_h), 1)
        avg_d = sum(r.relevance_score for r in recs_d) / max(len(recs_d), 1)
        assert avg_d > avg_h

    def test_overloaded_component_higher_score(self):
        engine = ChaosExperimentLibraryEngine()
        g_h = _graph(_comp("a1", ctype=ComponentType.APP_SERVER, health=HealthStatus.HEALTHY))
        g_o = _graph(_comp("a1", ctype=ComponentType.APP_SERVER, health=HealthStatus.OVERLOADED))
        recs_h = engine.recommend_experiments(g_h)
        recs_o = engine.recommend_experiments(g_o)
        avg_h = sum(r.relevance_score for r in recs_h) / max(len(recs_h), 1)
        avg_o = sum(r.relevance_score for r in recs_o) / max(len(recs_o), 1)
        assert avg_o > avg_h

    def test_high_dependency_boost(self):
        engine = ChaosExperimentLibraryEngine()
        app = _comp("app1", ctype=ComponentType.APP_SERVER)
        deps_comps = [_comp(f"dep{i}", ctype=ComponentType.EXTERNAL_API) for i in range(6)]
        dep_edges = [_dep("app1", f"dep{i}") for i in range(6)]
        g = _graph(app, *deps_comps, deps=dep_edges)
        recs = engine.recommend_experiments(g)
        app_recs = [r for r in recs if r.target_component == "app1"]
        assert len(app_recs) > 0

    def test_reason_populated(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER))
        recs = engine.recommend_experiments(g)
        for r in recs:
            assert len(r.reason) > 0

    def test_priority_populated(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER))
        recs = engine.recommend_experiments(g)
        valid = {"critical", "high", "medium", "low"}
        for r in recs:
            assert r.priority in valid

    def test_reason_mentions_single_replica_for_availability(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER, replicas=1))
        recs = engine.recommend_experiments(g)
        avail_recs = [r for r in recs if r.template.category == ExperimentCategory.AVAILABILITY]
        assert any("Single replica" in r.reason for r in avail_recs)

    def test_reason_mentions_downstream(self):
        engine = ChaosExperimentLibraryEngine()
        app = _comp("app1", ctype=ComponentType.APP_SERVER)
        db = _comp("db1", ctype=ComponentType.DATABASE)
        g = _graph(app, db, deps=[_dep("db1", "app1")])  # db1 depends on app1
        recs = engine.recommend_experiments(g)
        app_recs = [r for r in recs if r.target_component == "app1"]
        assert any("downstream" in r.reason.lower() for r in app_recs)


# ===========================================================================
# Engine — generate_experiment_plan
# ===========================================================================


class TestGenerateExperimentPlan:
    def test_empty_graph(self):
        engine = ChaosExperimentLibraryEngine()
        plan = engine.generate_experiment_plan(_graph())
        assert plan.entries == []
        assert plan.total_estimated_minutes == 0

    def test_single_component_plan(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("app1", ctype=ComponentType.APP_SERVER))
        plan = engine.generate_experiment_plan(g, max_experiments=5)
        assert len(plan.entries) <= 5
        assert plan.total_estimated_minutes > 0

    def test_max_experiments_respected(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(
            _comp("a1", ctype=ComponentType.APP_SERVER),
            _comp("d1", ctype=ComponentType.DATABASE),
            _comp("c1", ctype=ComponentType.CACHE),
        )
        plan = engine.generate_experiment_plan(g, max_experiments=3)
        assert len(plan.entries) <= 3

    def test_entries_have_order(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER))
        plan = engine.generate_experiment_plan(g, max_experiments=5)
        orders = [e.order for e in plan.entries]
        assert orders == list(range(1, len(plan.entries) + 1))

    def test_categories_covered(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(
            _comp("a1", ctype=ComponentType.APP_SERVER),
            _comp("d1", ctype=ComponentType.DATABASE),
        )
        plan = engine.generate_experiment_plan(g, max_experiments=20)
        assert len(plan.categories_covered) > 0

    def test_components_covered(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(
            _comp("a1", ctype=ComponentType.APP_SERVER),
            _comp("d1", ctype=ComponentType.DATABASE),
        )
        plan = engine.generate_experiment_plan(g, max_experiments=20)
        assert len(plan.components_covered) > 0

    def test_total_minutes_sums_correctly(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER))
        plan = engine.generate_experiment_plan(g)
        expected = sum(e.template.estimated_duration_minutes for e in plan.entries)
        assert plan.total_estimated_minutes == expected

    def test_plan_with_max_one(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER))
        plan = engine.generate_experiment_plan(g, max_experiments=1)
        assert len(plan.entries) == 1

    def test_plan_entries_have_reason(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER))
        plan = engine.generate_experiment_plan(g, max_experiments=3)
        for entry in plan.entries:
            assert len(entry.reason) > 0

    def test_plan_entries_have_priority(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER))
        plan = engine.generate_experiment_plan(g, max_experiments=3)
        for entry in plan.entries:
            assert entry.priority in {"critical", "high", "medium", "low"}


# ===========================================================================
# Engine — validate_prerequisites
# ===========================================================================


class TestValidatePrerequisites:
    def test_no_prerequisites(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=[])
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True
        assert result.met == []
        assert result.unmet == []

    def test_monitoring_satisfied(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["monitoring"])
        g = _graph(_comp("a1", health=HealthStatus.HEALTHY))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True
        assert "monitoring" in result.met

    def test_replicas_unmet(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["replicas > 1"])
        g = _graph(_comp("a1", replicas=1))
        result = engine.validate_prerequisites(g, tmpl, component_id="a1")
        assert result.satisfied is False
        assert "replicas > 1" in result.unmet

    def test_replicas_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["replicas > 1"])
        g = _graph(_comp("a1", replicas=3))
        result = engine.validate_prerequisites(g, tmpl, component_id="a1")
        assert result.satisfied is True
        assert "replicas > 1" in result.met

    def test_circuit_breaker_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["circuit breaker enabled"])
        g = _graph(
            _comp("a1"),
            _comp("a2"),
            deps=[_dep("a1", "a2", cb=True)],
        )
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_circuit_breaker_unmet(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["circuit breaker enabled"])
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is False

    def test_failover_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["failover configured"])
        g = _graph(_comp("a1", failover=True))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_failover_unmet(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["failover configured"])
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is False

    def test_autoscaling_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["autoscaling enabled"])
        g = _graph(_comp("a1", autoscaling=True))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_autoscaling_unmet(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["autoscaling enabled"])
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is False

    def test_backup_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["backup enabled"])
        g = _graph(_comp("a1", backup=True))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_backup_unmet(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["backup enabled"])
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is False

    def test_load_balancer_in_path_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["load balancer in path"])
        g = _graph(_comp("lb1", ctype=ComponentType.LOAD_BALANCER))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_load_balancer_in_path_unmet(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["load balancer in path"])
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is False

    def test_rate_limiting_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["rate limiting enabled"])
        g = _graph(_comp("a1", rate_limiting=True))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_encryption_at_rest_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["encryption at rest"])
        g = _graph(_comp("a1", encryption_at_rest=True))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_encryption_in_transit_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["encryption in transit"])
        g = _graph(_comp("a1", encryption_in_transit=True))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_network_segmentation_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["network segmentation"])
        g = _graph(_comp("a1", network_segmented=True))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_rollback_always_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["rollback procedure documented"])
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_health_check_met(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["health check configured"])
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_unknown_prerequisite_passes(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["some-unknown-prereq"])
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is True

    def test_multiple_prereqs_mixed(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["monitoring", "failover configured", "replicas > 1"])
        g = _graph(_comp("a1", replicas=1))
        result = engine.validate_prerequisites(g, tmpl, component_id="a1")
        assert result.satisfied is False
        assert "monitoring" in result.met
        assert "failover configured" in result.unmet
        assert "replicas > 1" in result.unmet

    def test_empty_graph_warning(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template()
        g = _graph()
        result = engine.validate_prerequisites(g, tmpl)
        assert any("no components" in w.lower() for w in result.warnings)

    def test_advanced_warning(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(difficulty=Difficulty.ADVANCED)
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert any("advanced" in w.lower() for w in result.warnings)

    def test_expert_warning(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(difficulty=Difficulty.EXPERT)
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert any("expert" in w.lower() for w in result.warnings)

    def test_beginner_no_difficulty_warning(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(difficulty=Difficulty.BEGINNER)
        g = _graph(_comp("a1"))
        result = engine.validate_prerequisites(g, tmpl)
        assert not any("beginner" in w.lower() for w in result.warnings)

    def test_replicas_global_fallback(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["replicas > 1"])
        g = _graph(_comp("a1", replicas=3))
        result = engine.validate_prerequisites(g, tmpl)
        # No component_id -> checks any component in graph
        assert result.satisfied is True


# ===========================================================================
# Engine — estimate_coverage
# ===========================================================================


class TestEstimateCoverage:
    def test_no_experiments(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"), _comp("d1", ctype=ComponentType.DATABASE))
        report = engine.estimate_coverage(g, [])
        assert report.total_components == 2
        assert report.covered_components == 0
        assert report.coverage_percent == 0.0
        assert len(report.categories_untested) == 8

    def test_full_coverage(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        # Run experiments covering all 8 categories
        experiments = []
        for cat in ExperimentCategory:
            tmpl = engine.list_templates(category=cat)[0]
            experiments.append((tmpl.id, "a1"))
        report = engine.estimate_coverage(g, experiments)
        assert report.covered_components == 1
        assert report.coverage_percent == 100.0
        assert report.categories_untested == []

    def test_partial_coverage(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"), _comp("d1", ctype=ComponentType.DATABASE))
        experiments = [("avail-001", "a1")]
        report = engine.estimate_coverage(g, experiments)
        assert report.covered_components == 1
        assert report.coverage_percent == 50.0
        assert "availability" in report.categories_tested
        assert len(report.categories_untested) == 7

    def test_unknown_template_ignored(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        experiments = [("nonexistent-tmpl", "a1")]
        report = engine.estimate_coverage(g, experiments)
        assert report.covered_components == 0

    def test_component_not_in_graph(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        experiments = [("avail-001", "not-in-graph")]
        report = engine.estimate_coverage(g, experiments)
        assert report.covered_components == 0
        assert report.coverage_percent == 0.0

    def test_empty_graph(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph()
        report = engine.estimate_coverage(g, [])
        assert report.total_components == 0
        assert report.coverage_percent == 0.0

    def test_component_coverage_dict(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        experiments = [("avail-001", "a1"), ("lat-001", "a1")]
        report = engine.estimate_coverage(g, experiments)
        assert "a1" in report.component_coverage
        assert "availability" in report.component_coverage["a1"]
        assert "latency" in report.component_coverage["a1"]

    def test_recommendations_for_uncovered_categories(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        experiments = [("avail-001", "a1")]
        report = engine.estimate_coverage(g, experiments)
        assert len(report.recommendations) > 0
        assert any("categories" in r.lower() for r in report.recommendations)

    def test_recommendations_for_uncovered_components(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"), _comp("d1", ctype=ComponentType.DATABASE))
        experiments = [("avail-001", "a1")]
        report = engine.estimate_coverage(g, experiments)
        assert any("d1" in r for r in report.recommendations)

    def test_duplicate_experiments_counted_once(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        experiments = [("avail-001", "a1"), ("avail-001", "a1")]
        report = engine.estimate_coverage(g, experiments)
        assert report.covered_components == 1
        # Category should appear only once
        assert report.component_coverage["a1"].count("availability") == 1

    def test_multiple_categories_same_component(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        experiments = [
            ("avail-001", "a1"),
            ("lat-001", "a1"),
            ("sec-001", "a1"),
        ]
        report = engine.estimate_coverage(g, experiments)
        assert len(report.component_coverage["a1"]) == 3


# ===========================================================================
# _check_prerequisite standalone tests
# ===========================================================================


class TestCheckPrerequisite:
    def test_monitoring_with_healthy(self):
        g = _graph(_comp("a1", health=HealthStatus.HEALTHY))
        assert _check_prerequisite("monitoring", g, None) is True

    def test_monitoring_all_down(self):
        g = _graph(_comp("a1", health=HealthStatus.DOWN))
        assert _check_prerequisite("monitoring", g, None) is False

    def test_observability_alias(self):
        g = _graph(_comp("a1"))
        assert _check_prerequisite("observability enabled", g, None) is True

    def test_replicas_with_component_id(self):
        g = _graph(_comp("a1", replicas=2))
        assert _check_prerequisite("replicas > 1", g, "a1") is True

    def test_replicas_component_not_found_fallback(self):
        g = _graph(_comp("a1", replicas=2))
        # Unknown component → falls back to any-component check
        assert _check_prerequisite("replicas > 1", g, "unknown") is True

    def test_circuit_breaker_no_edges(self):
        g = _graph(_comp("a1"))
        assert _check_prerequisite("circuit breaker enabled", g, None) is False

    def test_unknown_prereq_passes(self):
        g = _graph(_comp("a1"))
        assert _check_prerequisite("xyz-unknown", g, None) is True

    def test_empty_graph_monitoring(self):
        g = _graph()
        assert _check_prerequisite("monitoring", g, None) is False


# ===========================================================================
# Engine — priority_from_score
# ===========================================================================


class TestPriorityFromScore:
    def test_critical(self):
        assert ChaosExperimentLibraryEngine._priority_from_score(0.9) == "critical"
        assert ChaosExperimentLibraryEngine._priority_from_score(0.8) == "critical"

    def test_high(self):
        assert ChaosExperimentLibraryEngine._priority_from_score(0.7) == "high"
        assert ChaosExperimentLibraryEngine._priority_from_score(0.6) == "high"

    def test_medium(self):
        assert ChaosExperimentLibraryEngine._priority_from_score(0.5) == "medium"
        assert ChaosExperimentLibraryEngine._priority_from_score(0.4) == "medium"

    def test_low(self):
        assert ChaosExperimentLibraryEngine._priority_from_score(0.3) == "low"
        assert ChaosExperimentLibraryEngine._priority_from_score(0.0) == "low"

    def test_boundary_08(self):
        assert ChaosExperimentLibraryEngine._priority_from_score(0.8) == "critical"

    def test_boundary_06(self):
        assert ChaosExperimentLibraryEngine._priority_from_score(0.6) == "high"

    def test_boundary_04(self):
        assert ChaosExperimentLibraryEngine._priority_from_score(0.4) == "medium"

    def test_boundary_039(self):
        assert ChaosExperimentLibraryEngine._priority_from_score(0.39) == "low"


# ===========================================================================
# Integration / complex graph tests
# ===========================================================================


class TestComplexGraphScenarios:
    def _build_complex_graph(self) -> InfraGraph:
        lb = _comp("lb1", ctype=ComponentType.LOAD_BALANCER, replicas=2)
        web = _comp("web1", ctype=ComponentType.WEB_SERVER, replicas=3)
        app = _comp("app1", ctype=ComponentType.APP_SERVER, replicas=2, failover=True)
        db = _comp("db1", ctype=ComponentType.DATABASE, replicas=2, failover=True, backup=True)
        cache = _comp("cache1", ctype=ComponentType.CACHE, replicas=2)
        queue = _comp("queue1", ctype=ComponentType.QUEUE)
        ext = _comp("ext1", ctype=ComponentType.EXTERNAL_API)
        deps = [
            _dep("lb1", "web1"),
            _dep("web1", "app1"),
            _dep("app1", "db1", cb=True),
            _dep("app1", "cache1"),
            _dep("app1", "queue1"),
            _dep("app1", "ext1", cb=True),
        ]
        return _graph(lb, web, app, db, cache, queue, ext, deps=deps)

    def test_complex_graph_recommendations(self):
        engine = ChaosExperimentLibraryEngine()
        g = self._build_complex_graph()
        recs = engine.recommend_experiments(g)
        assert len(recs) > 10
        targets = {r.target_component for r in recs}
        assert len(targets) >= 5

    def test_complex_graph_plan(self):
        engine = ChaosExperimentLibraryEngine()
        g = self._build_complex_graph()
        plan = engine.generate_experiment_plan(g, max_experiments=10)
        assert len(plan.entries) == 10
        assert plan.total_estimated_minutes > 0

    def test_complex_graph_coverage_progression(self):
        engine = ChaosExperimentLibraryEngine()
        g = self._build_complex_graph()
        # Start with no coverage
        r0 = engine.estimate_coverage(g, [])
        assert r0.coverage_percent == 0.0
        # Run one experiment
        r1 = engine.estimate_coverage(g, [("avail-001", "app1")])
        assert r1.coverage_percent > 0.0
        # Run more
        exps = [("avail-001", "app1"), ("lat-001", "web1"), ("data-001", "db1")]
        r2 = engine.estimate_coverage(g, exps)
        assert r2.coverage_percent > r1.coverage_percent

    def test_complex_graph_prerequisites(self):
        engine = ChaosExperimentLibraryEngine()
        g = self._build_complex_graph()
        # avail-002 requires failover + monitoring + replicas > 1
        tmpl = engine.get_template("avail-002")
        assert tmpl is not None
        result = engine.validate_prerequisites(g, tmpl, component_id="app1")
        # app1 has replicas=2, failover=True, so most should be met
        assert "failover configured" in result.met
        assert "replicas > 1" in result.met
        assert "monitoring" in result.met

    def test_all_component_types_get_recommendations(self):
        engine = ChaosExperimentLibraryEngine()
        g = self._build_complex_graph()
        recs = engine.recommend_experiments(g)
        rec_targets = {r.target_component for r in recs}
        for comp_id in g.components:
            assert comp_id in rec_targets, f"No recommendations for {comp_id}"

    def test_plan_deduplicates(self):
        engine = ChaosExperimentLibraryEngine()
        g = self._build_complex_graph()
        plan = engine.generate_experiment_plan(g, max_experiments=50)
        seen = set()
        for entry in plan.entries:
            key = (entry.template.id, entry.target_component)
            assert key not in seen, f"Duplicate entry {key}"
            seen.add(key)


# ===========================================================================
# Edge case tests
# ===========================================================================


class TestEdgeCases:
    def test_graph_single_dns(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("dns1", ctype=ComponentType.DNS))
        recs = engine.recommend_experiments(g)
        assert len(recs) > 0

    def test_graph_single_storage(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("s1", ctype=ComponentType.STORAGE))
        recs = engine.recommend_experiments(g)
        assert len(recs) > 0

    def test_graph_single_custom(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("c1", ctype=ComponentType.CUSTOM))
        recs = engine.recommend_experiments(g)
        # custom type may have limited but non-zero recs
        assert isinstance(recs, list)

    def test_down_component_monitoring_prereq(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["monitoring"])
        g = _graph(_comp("a1", health=HealthStatus.DOWN))
        result = engine.validate_prerequisites(g, tmpl)
        assert result.satisfied is False

    def test_max_experiments_zero(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        plan = engine.generate_experiment_plan(g, max_experiments=0)
        assert plan.entries == []

    def test_coverage_with_all_templates(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        experiments = [(t.id, "a1") for t in _BUILTIN_TEMPLATES]
        report = engine.estimate_coverage(g, experiments)
        assert report.covered_components == 1
        assert report.coverage_percent == 100.0
        assert len(report.categories_untested) == 0

    def test_custom_engine_recommend(self):
        tmpl = _make_template(
            applicable_component_types=["database"],
            category=ExperimentCategory.DATA,
        )
        engine = ChaosExperimentLibraryEngine(templates=[tmpl])
        g = _graph(_comp("d1", ctype=ComponentType.DATABASE))
        recs = engine.recommend_experiments(g)
        assert len(recs) == 1
        assert recs[0].template.id == "test-001"

    def test_custom_engine_no_match(self):
        tmpl = _make_template(applicable_component_types=["database"])
        engine = ChaosExperimentLibraryEngine(templates=[tmpl])
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER))
        recs = engine.recommend_experiments(g)
        assert recs == []

    def test_coverage_categories_sorted(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1"))
        experiments = [("lat-001", "a1"), ("avail-001", "a1")]
        report = engine.estimate_coverage(g, experiments)
        assert report.categories_tested == sorted(report.categories_tested)
        assert report.categories_untested == sorted(report.categories_untested)

    def test_many_components(self):
        engine = ChaosExperimentLibraryEngine()
        comps = [_comp(f"c{i}", ctype=ComponentType.APP_SERVER) for i in range(20)]
        g = _graph(*comps)
        recs = engine.recommend_experiments(g)
        assert len(recs) > 20

    def test_plan_large_max(self):
        engine = ChaosExperimentLibraryEngine()
        g = _graph(_comp("a1", ctype=ComponentType.APP_SERVER))
        plan = engine.generate_experiment_plan(g, max_experiments=1000)
        # Should not exceed available unique (template, component) pairs
        app_templates = engine.filter_by_component_type("app_server")
        assert len(plan.entries) <= len(app_templates)

    def test_validate_prerequisites_no_component_id(self):
        engine = ChaosExperimentLibraryEngine()
        tmpl = _make_template(prerequisites=["replicas > 1"])
        g = _graph(_comp("a1", replicas=1), _comp("a2", replicas=2))
        result = engine.validate_prerequisites(g, tmpl)
        # Falls back to any-component check — a2 has replicas=2
        assert result.satisfied is True

    def test_build_reason_general_applicability(self):
        # With a component that has no special conditions
        reason = ChaosExperimentLibraryEngine._build_reason(
            _make_template(), object(), _graph()
        )
        assert reason == "General applicability"
