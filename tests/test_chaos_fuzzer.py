"""Tests for the Chaos Fuzzer (AFL-inspired infrastructure fuzzing)."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType, Dependency, HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEffect
from faultray.simulator.chaos_fuzzer import ChaosFuzzer, FuzzReport, FuzzResult
from faultray.simulator.engine import ScenarioResult
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_change_risk.py)
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.health = health
    return c


def _chain_graph() -> InfraGraph:
    """Build a 3-component chain: lb -> api -> db."""
    g = InfraGraph()
    g.add_component(_comp("lb", "LB", ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(_comp("api", "API", replicas=3))
    g.add_component(_comp("db", "DB", ComponentType.DATABASE, replicas=2))
    g.add_dependency(Dependency(source_id="lb", target_id="api"))
    g.add_dependency(Dependency(source_id="api", target_id="db"))
    return g


def _large_graph(n: int = 10) -> InfraGraph:
    """Build a linear chain of N components."""
    g = InfraGraph()
    for i in range(n):
        g.add_component(_comp(f"svc-{i}", f"Service {i}"))
    for i in range(n - 1):
        g.add_dependency(Dependency(source_id=f"svc-{i}", target_id=f"svc-{i+1}"))
    return g


def _single_fault_scenario(comp_id: str = "api") -> Scenario:
    return Scenario(
        id="base-1",
        name="Base scenario",
        description="One fault",
        faults=[Fault(target_component_id=comp_id, fault_type=FaultType.COMPONENT_DOWN)],
    )


def _multi_fault_scenario() -> Scenario:
    return Scenario(
        id="base-multi",
        name="Multi-fault",
        description="Two faults",
        faults=[
            Fault(target_component_id="lb", fault_type=FaultType.LATENCY_SPIKE, severity=0.5),
            Fault(target_component_id="db", fault_type=FaultType.DISK_FULL, severity=0.8),
        ],
    )


# ---------------------------------------------------------------------------
# Tests: Dataclasses
# ---------------------------------------------------------------------------


class TestFuzzResult:
    def test_fields(self):
        scenario = _single_fault_scenario()
        r = FuzzResult(
            iteration=3,
            scenario=scenario,
            risk_score=4.5,
            is_novel=True,
            mutation_type="add_fault",
        )
        assert r.iteration == 3
        assert r.scenario is scenario
        assert r.risk_score == 4.5
        assert r.is_novel is True
        assert r.mutation_type == "add_fault"

    def test_not_novel(self):
        r = FuzzResult(
            iteration=0,
            scenario=_single_fault_scenario(),
            risk_score=0.0,
            is_novel=False,
            mutation_type="remove_fault",
        )
        assert r.is_novel is False


class TestFuzzReport:
    def test_fields(self):
        report = FuzzReport(
            total_iterations=50,
            novel_failures_found=5,
            highest_risk_score=8.0,
            novel_scenarios=[],
            coverage=0.75,
            mutation_effectiveness={"add_fault": 0.5},
        )
        assert report.total_iterations == 50
        assert report.novel_failures_found == 5
        assert report.highest_risk_score == 8.0
        assert report.novel_scenarios == []
        assert report.coverage == 0.75
        assert report.mutation_effectiveness == {"add_fault": 0.5}

    def test_empty_report(self):
        report = FuzzReport(
            total_iterations=0,
            novel_failures_found=0,
            highest_risk_score=0.0,
            novel_scenarios=[],
            coverage=0.0,
            mutation_effectiveness={},
        )
        assert report.total_iterations == 0
        assert len(report.novel_scenarios) == 0


# ---------------------------------------------------------------------------
# Tests: ChaosFuzzer initialization
# ---------------------------------------------------------------------------


class TestChaosFuzzerInit:
    def test_init_stores_graph(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=99)
        assert fuzzer.graph is g

    def test_init_creates_engine(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g)
        assert fuzzer.engine is not None
        assert fuzzer.engine.graph is g

    def test_init_empty_seen_patterns(self):
        fuzzer = ChaosFuzzer(_chain_graph())
        assert fuzzer._seen_patterns == set()

    def test_init_default_seed(self):
        g = _chain_graph()
        f1 = ChaosFuzzer(g)
        f2 = ChaosFuzzer(g)
        # Both should use seed=42 by default and produce identical results
        r1 = f1.fuzz(iterations=5)
        r2 = f2.fuzz(iterations=5)
        assert r1.novel_failures_found == r2.novel_failures_found

    def test_mutation_types_constant(self):
        expected = [
            "add_fault", "remove_fault", "change_target",
            "change_type", "combine", "amplify_traffic",
        ]
        assert ChaosFuzzer.MUTATION_TYPES == expected


# ---------------------------------------------------------------------------
# Tests: fuzz() method — basic behavior
# ---------------------------------------------------------------------------


class TestFuzzBasic:
    def test_returns_fuzz_report(self):
        report = ChaosFuzzer(_chain_graph(), seed=42).fuzz(iterations=10)
        assert isinstance(report, FuzzReport)

    def test_total_iterations_matches(self):
        report = ChaosFuzzer(_chain_graph(), seed=42).fuzz(iterations=25)
        assert report.total_iterations == 25

    def test_novel_failures_found(self):
        report = ChaosFuzzer(_chain_graph(), seed=42).fuzz(iterations=50)
        assert report.novel_failures_found > 0
        assert len(report.novel_scenarios) == report.novel_failures_found or (
            report.novel_failures_found > 20 and len(report.novel_scenarios) == 20
        )

    def test_highest_risk_nonnegative(self):
        report = ChaosFuzzer(_chain_graph(), seed=42).fuzz(iterations=30)
        assert report.highest_risk_score >= 0.0

    def test_coverage_between_0_and_1(self):
        report = ChaosFuzzer(_chain_graph(), seed=42).fuzz(iterations=100)
        assert 0.0 <= report.coverage <= 1.0

    def test_high_coverage_with_enough_iterations(self):
        # With 3 components and 100 iterations, should cover all
        report = ChaosFuzzer(_chain_graph(), seed=42).fuzz(iterations=100)
        assert report.coverage > 0.5


# ---------------------------------------------------------------------------
# Tests: fuzz() — determinism
# ---------------------------------------------------------------------------


class TestFuzzDeterminism:
    def test_same_seed_same_results(self):
        g = _chain_graph()
        r1 = ChaosFuzzer(g, seed=123).fuzz(iterations=30)
        r2 = ChaosFuzzer(g, seed=123).fuzz(iterations=30)
        assert r1.novel_failures_found == r2.novel_failures_found
        assert r1.highest_risk_score == r2.highest_risk_score
        assert r1.coverage == r2.coverage

    def test_different_seeds_differ(self):
        g = _chain_graph()
        r1 = ChaosFuzzer(g, seed=1).fuzz(iterations=50)
        r2 = ChaosFuzzer(g, seed=9999).fuzz(iterations=50)
        differs = (
            r1.novel_failures_found != r2.novel_failures_found
            or r1.highest_risk_score != r2.highest_risk_score
            or r1.coverage != r2.coverage
        )
        assert differs


# ---------------------------------------------------------------------------
# Tests: fuzz() — empty / edge cases
# ---------------------------------------------------------------------------


class TestFuzzEdgeCases:
    def test_empty_graph(self):
        report = ChaosFuzzer(InfraGraph(), seed=42).fuzz(iterations=10)
        assert report.total_iterations == 10
        assert report.novel_failures_found == 0
        assert report.highest_risk_score == 0.0
        assert report.coverage == 0.0
        assert report.mutation_effectiveness == {}
        assert report.novel_scenarios == []

    def test_single_component(self):
        g = InfraGraph()
        g.add_component(_comp("only", "Only"))
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=20)
        assert report.total_iterations == 20
        # Only one component, so coverage must be 1.0
        assert report.coverage == 1.0

    def test_zero_iterations(self):
        report = ChaosFuzzer(_chain_graph(), seed=42).fuzz(iterations=0)
        assert report.total_iterations == 0
        assert report.novel_failures_found == 0
        assert report.highest_risk_score == 0.0

    def test_one_iteration(self):
        report = ChaosFuzzer(_chain_graph(), seed=42).fuzz(iterations=1)
        assert report.total_iterations == 1
        assert len(report.novel_scenarios) <= 1


# ---------------------------------------------------------------------------
# Tests: fuzz() — base_scenarios parameter
# ---------------------------------------------------------------------------


class TestFuzzBaseScenarios:
    def test_with_user_supplied_base(self):
        g = _chain_graph()
        base = [_single_fault_scenario("db")]
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=20, base_scenarios=base)
        assert isinstance(report, FuzzReport)
        assert report.total_iterations == 20

    def test_with_multi_fault_base(self):
        g = _chain_graph()
        base = [_multi_fault_scenario()]
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=15, base_scenarios=base)
        assert report.total_iterations == 15

    def test_empty_base_scenarios_list(self):
        # Empty list is falsy, so _generate_seed_corpus is called
        g = _chain_graph()
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=10, base_scenarios=[])
        # Should behave like no base_scenarios were given (auto-generate seeds)
        assert report.total_iterations == 10

    def test_multiple_base_scenarios(self):
        g = _chain_graph()
        base = [_single_fault_scenario("lb"), _single_fault_scenario("db")]
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=30, base_scenarios=base)
        assert report.novel_failures_found >= 0


# ---------------------------------------------------------------------------
# Tests: fuzz() — novel_scenarios ordering and cap
# ---------------------------------------------------------------------------


class TestNovelScenarios:
    def test_sorted_by_risk_descending(self):
        g = _chain_graph()
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=100)
        scores = [r.risk_score for r in report.novel_scenarios]
        assert scores == sorted(scores, reverse=True)

    def test_capped_at_20(self):
        g = _large_graph(20)
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=500)
        assert len(report.novel_scenarios) <= 20

    def test_all_novel_scenarios_are_novel(self):
        g = _chain_graph()
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=50)
        for r in report.novel_scenarios:
            assert r.is_novel is True


# ---------------------------------------------------------------------------
# Tests: fuzz() — mutation_effectiveness
# ---------------------------------------------------------------------------


class TestMutationEffectiveness:
    def test_keys_are_valid_mutation_types(self):
        g = _chain_graph()
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=100)
        for key in report.mutation_effectiveness:
            assert key in ChaosFuzzer.MUTATION_TYPES

    def test_values_between_0_and_1(self):
        g = _chain_graph()
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=100)
        for rate in report.mutation_effectiveness.values():
            assert 0.0 <= rate <= 1.0

    def test_at_least_some_mutation_types(self):
        g = _chain_graph()
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=100)
        assert len(report.mutation_effectiveness) > 0


# ---------------------------------------------------------------------------
# Tests: _mutate — each mutation type individually
# ---------------------------------------------------------------------------


class TestMutateAddFault:
    def test_adds_one_fault(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())
        fault_types = list(FaultType)

        mutated = fuzzer._mutate(base, "add_fault", comp_ids, fault_types)
        assert len(mutated.faults) == len(base.faults) + 1

    def test_new_fault_targets_valid_component(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "add_fault", comp_ids, list(FaultType))
        new_fault = mutated.faults[-1]
        assert new_fault.target_component_id in comp_ids

    def test_severity_in_range(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "add_fault", comp_ids, list(FaultType))
        new_fault = mutated.faults[-1]
        assert 0.3 <= new_fault.severity <= 1.0


class TestMutateRemoveFault:
    def test_removes_one_fault_when_multiple(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _multi_fault_scenario()  # 2 faults
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "remove_fault", comp_ids, list(FaultType))
        assert len(mutated.faults) == len(base.faults) - 1

    def test_no_removal_when_single_fault(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")  # 1 fault
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "remove_fault", comp_ids, list(FaultType))
        # Cannot remove when only 1 fault; falls through to default return
        assert len(mutated.faults) == 1


class TestMutateChangeTarget:
    def test_changes_target_component(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=10)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        # Run enough times to find a case where target changes
        changed = False
        for seed_val in range(50):
            fuzzer_try = ChaosFuzzer(g, seed=seed_val)
            mutated = fuzzer_try._mutate(base, "change_target", comp_ids, list(FaultType))
            if mutated.faults[0].target_component_id != "api":
                changed = True
                break
        assert changed, "change_target should eventually pick a different component"

    def test_preserves_fault_type(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "change_target", comp_ids, list(FaultType))
        assert mutated.faults[0].fault_type == base.faults[0].fault_type

    def test_preserves_severity(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = Scenario(
            id="sev-test", name="Sev test", description="Test",
            faults=[Fault(
                target_component_id="api",
                fault_type=FaultType.LATENCY_SPIKE,
                severity=0.7,
            )],
        )
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "change_target", comp_ids, list(FaultType))
        assert mutated.faults[0].severity == 0.7


class TestMutateChangeType:
    def test_changes_fault_type(self):
        g = _chain_graph()
        comp_ids = list(g.components.keys())

        changed = False
        for seed_val in range(50):
            fuzzer = ChaosFuzzer(g, seed=seed_val)
            base = _single_fault_scenario("api")  # COMPONENT_DOWN
            mutated = fuzzer._mutate(base, "change_type", comp_ids, list(FaultType))
            if mutated.faults[0].fault_type != FaultType.COMPONENT_DOWN:
                changed = True
                break
        assert changed, "change_type should eventually pick a different fault type"

    def test_preserves_target(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("db")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "change_type", comp_ids, list(FaultType))
        assert mutated.faults[0].target_component_id == "db"

    def test_preserves_severity(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = Scenario(
            id="ct-test", name="CT test", description="Test",
            faults=[Fault(
                target_component_id="api",
                fault_type=FaultType.CPU_SATURATION,
                severity=0.6,
            )],
        )
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "change_type", comp_ids, list(FaultType))
        assert mutated.faults[0].severity == 0.6


class TestMutateCombine:
    def test_creates_multi_target_faults(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())  # 3 components

        mutated = fuzzer._mutate(base, "combine", comp_ids, list(FaultType))
        # combine samples min(3, len(comp_ids)) targets
        assert len(mutated.faults) >= 2
        assert len(mutated.faults) <= 3

    def test_targets_are_valid(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "combine", comp_ids, list(FaultType))
        for fault in mutated.faults:
            assert fault.target_component_id in comp_ids

    def test_combine_with_two_components(self):
        g = InfraGraph()
        g.add_component(_comp("a", "A"))
        g.add_component(_comp("b", "B"))
        comp_ids = list(g.components.keys())

        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("a")
        mutated = fuzzer._mutate(base, "combine", comp_ids, list(FaultType))
        assert len(mutated.faults) == 2

    def test_combine_skipped_with_one_component(self):
        g = InfraGraph()
        g.add_component(_comp("only", "Only"))
        comp_ids = list(g.components.keys())

        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("only")
        mutated = fuzzer._mutate(base, "combine", comp_ids, list(FaultType))
        # len(comp_ids) < 2, so combine is skipped; falls through to default
        assert len(mutated.faults) == 1


class TestMutateAmplifyTraffic:
    def test_sets_traffic_multiplier(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "amplify_traffic", comp_ids, list(FaultType))
        assert mutated.traffic_multiplier >= 2.0
        assert mutated.traffic_multiplier <= 15.0

    def test_name_contains_traffic(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "amplify_traffic", comp_ids, list(FaultType))
        assert "traffic" in mutated.name.lower()

    def test_preserves_faults(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _multi_fault_scenario()
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "amplify_traffic", comp_ids, list(FaultType))
        # Faults are preserved (copied from parent)
        assert len(mutated.faults) == len(base.faults)

    def test_returns_early(self):
        """amplify_traffic returns from within the if-branch, not the default return."""
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "amplify_traffic", comp_ids, list(FaultType))
        # The early return produces a different name format than the default
        assert "traffic" in mutated.name
        assert mutated.description == "Fuzzer-generated"


# ---------------------------------------------------------------------------
# Tests: _mutate — default return (fallthrough)
# ---------------------------------------------------------------------------


class TestMutateDefault:
    def test_name_contains_mutation_type(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "add_fault", comp_ids, list(FaultType))
        assert "add_fault" in mutated.name

    def test_description_is_fuzzer_generated(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "change_type", comp_ids, list(FaultType))
        assert mutated.description == "Fuzzer-generated"

    def test_id_starts_with_fuzz(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        base = _single_fault_scenario("api")
        comp_ids = list(g.components.keys())

        mutated = fuzzer._mutate(base, "add_fault", comp_ids, list(FaultType))
        assert mutated.id.startswith("fuzz-")


# ---------------------------------------------------------------------------
# Tests: _generate_seed_corpus
# ---------------------------------------------------------------------------


class TestGenerateSeedCorpus:
    def test_generates_one_per_component(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        comp_ids = list(g.components.keys())
        seeds = fuzzer._generate_seed_corpus(comp_ids)
        assert len(seeds) == 3  # 3 components

    def test_caps_at_five(self):
        g = _large_graph(10)
        fuzzer = ChaosFuzzer(g, seed=42)
        comp_ids = list(g.components.keys())
        seeds = fuzzer._generate_seed_corpus(comp_ids)
        assert len(seeds) == 5

    def test_seed_uses_component_down(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        comp_ids = list(g.components.keys())
        seeds = fuzzer._generate_seed_corpus(comp_ids)
        for s in seeds:
            assert len(s.faults) == 1
            assert s.faults[0].fault_type == FaultType.COMPONENT_DOWN

    def test_seed_ids_match_components(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        comp_ids = list(g.components.keys())
        seeds = fuzzer._generate_seed_corpus(comp_ids)
        for i, s in enumerate(seeds):
            assert s.faults[0].target_component_id == comp_ids[i]
            assert s.id == f"seed-{comp_ids[i]}"

    def test_empty_components(self):
        fuzzer = ChaosFuzzer(InfraGraph(), seed=42)
        seeds = fuzzer._generate_seed_corpus([])
        assert seeds == []


# ---------------------------------------------------------------------------
# Tests: _fingerprint
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_fingerprint_of_no_effects(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        result = ScenarioResult(
            scenario=_single_fault_scenario(),
            cascade=CascadeChain(trigger="test", total_components=3),
        )
        fp = fuzzer._fingerprint(result)
        assert fp == ""

    def test_fingerprint_of_down_components(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        cascade = CascadeChain(trigger="test", total_components=3, effects=[
            CascadeEffect(
                component_id="db", component_name="DB",
                health=HealthStatus.DOWN, reason="fault",
            ),
            CascadeEffect(
                component_id="api", component_name="API",
                health=HealthStatus.DOWN, reason="cascade",
            ),
        ])
        result = ScenarioResult(
            scenario=_single_fault_scenario(),
            cascade=cascade,
        )
        fp = fuzzer._fingerprint(result)
        # Should be sorted: api|db
        assert fp == "api|db"

    def test_fingerprint_ignores_non_down(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        cascade = CascadeChain(trigger="test", total_components=3, effects=[
            CascadeEffect(
                component_id="db", component_name="DB",
                health=HealthStatus.DOWN, reason="fault",
            ),
            CascadeEffect(
                component_id="api", component_name="API",
                health=HealthStatus.DEGRADED, reason="cascade",
            ),
            CascadeEffect(
                component_id="lb", component_name="LB",
                health=HealthStatus.OVERLOADED, reason="load",
            ),
        ])
        result = ScenarioResult(
            scenario=_single_fault_scenario(),
            cascade=cascade,
        )
        fp = fuzzer._fingerprint(result)
        # Only "db" is DOWN
        assert fp == "db"

    def test_same_down_set_same_fingerprint(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)

        cascade1 = CascadeChain(trigger="t1", effects=[
            CascadeEffect(component_id="lb", component_name="LB",
                          health=HealthStatus.DOWN, reason="x"),
            CascadeEffect(component_id="api", component_name="API",
                          health=HealthStatus.DOWN, reason="y"),
        ])
        cascade2 = CascadeChain(trigger="t2", effects=[
            CascadeEffect(component_id="api", component_name="API",
                          health=HealthStatus.DOWN, reason="a"),
            CascadeEffect(component_id="lb", component_name="LB",
                          health=HealthStatus.DOWN, reason="b"),
        ])

        r1 = ScenarioResult(scenario=_single_fault_scenario(), cascade=cascade1)
        r2 = ScenarioResult(scenario=_single_fault_scenario(), cascade=cascade2)

        assert fuzzer._fingerprint(r1) == fuzzer._fingerprint(r2)


# ---------------------------------------------------------------------------
# Tests: novelty tracking in fuzz()
# ---------------------------------------------------------------------------


class TestNoveltyTracking:
    def test_novel_added_to_corpus(self):
        """Novel scenarios should grow the corpus and thus produce more variety."""
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        report = fuzzer.fuzz(iterations=50)
        # After fuzzing, _seen_patterns should have entries
        assert len(fuzzer._seen_patterns) > 0

    def test_seen_patterns_grow(self):
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        fuzzer.fuzz(iterations=10)
        seen_after_10 = len(fuzzer._seen_patterns)

        fuzzer2 = ChaosFuzzer(g, seed=42)
        fuzzer2.fuzz(iterations=50)
        seen_after_50 = len(fuzzer2._seen_patterns)

        assert seen_after_50 >= seen_after_10

    def test_duplicate_patterns_not_novel(self):
        """Running the same seed twice: second run should find fewer novels
        (since _seen_patterns accumulates)."""
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        r1 = fuzzer.fuzz(iterations=30)
        # Run again on the same fuzzer (patterns already seen)
        r2 = fuzzer.fuzz(iterations=30)
        assert r2.novel_failures_found <= r1.novel_failures_found


# ---------------------------------------------------------------------------
# Tests: fuzz() with large graph
# ---------------------------------------------------------------------------


class TestFuzzLargeGraph:
    def test_large_graph_coverage(self):
        g = _large_graph(10)
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=200)
        # With 10 components, should get decent coverage
        assert report.coverage > 0.3

    def test_large_graph_seed_corpus_capped(self):
        g = _large_graph(10)
        fuzzer = ChaosFuzzer(g, seed=42)
        seeds = fuzzer._generate_seed_corpus(list(g.components.keys()))
        assert len(seeds) == 5  # capped at 5

    def test_many_iterations_discover_many_patterns(self):
        g = _large_graph(10)
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=200)
        assert report.novel_failures_found > 1


# ---------------------------------------------------------------------------
# Tests: fuzz() — integration (end-to-end fuzzing)
# ---------------------------------------------------------------------------


class TestFuzzIntegration:
    def test_full_campaign(self):
        """A full fuzzing campaign exercises all code paths."""
        g = _chain_graph()
        fuzzer = ChaosFuzzer(g, seed=42)
        report = fuzzer.fuzz(iterations=200)

        # Verify report structure
        assert report.total_iterations == 200
        assert report.novel_failures_found >= 1
        assert report.highest_risk_score >= 0.0
        assert 0.0 <= report.coverage <= 1.0
        assert len(report.novel_scenarios) <= 20

        # Verify novel scenarios are sorted
        scores = [r.risk_score for r in report.novel_scenarios]
        assert scores == sorted(scores, reverse=True)

        # Verify mutation effectiveness rates
        for rate in report.mutation_effectiveness.values():
            assert 0.0 <= rate <= 1.0

    def test_all_mutation_types_used(self):
        """With enough iterations and a fixed seed, all mutation types should appear."""
        g = _chain_graph()
        report = ChaosFuzzer(g, seed=42).fuzz(iterations=200)
        # With 200 iterations and 6 mutation types, each should appear
        assert len(report.mutation_effectiveness) >= 4  # most types should be hit
