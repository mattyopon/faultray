"""Tests for chaos_correlation module — Chaos Correlation Engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from faultray.simulator.chaos_correlation import (
    ChaosCorrelationEngine,
    Correlation,
    CorrelationReport,
    CorrelationType,
    EmergentPattern,
    ExperimentResult,
    HiddenDependency,
    _jaccard_similarity,
    _overlap_ratio,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> datetime:
    return datetime.now(timezone.utc)


def _make_result(
    experiment_id: str = "exp-1",
    target: str = "svc-a",
    failure_type: str = "latency",
    severity: float = 0.5,
    affected: list[str] | None = None,
    impact: float = 50.0,
    recovery: float = 60.0,
    success: bool = True,
) -> ExperimentResult:
    return ExperimentResult(
        experiment_id=experiment_id,
        timestamp=_ts(),
        target_component=target,
        failure_type=failure_type,
        severity=severity,
        affected_components=affected or [],
        impact_score=impact,
        recovery_time_seconds=recovery,
        success=success,
    )


# ===================================================================
# CorrelationType enum
# ===================================================================


class TestCorrelationType:
    def test_causal_value(self):
        assert CorrelationType.CAUSAL.value == "causal"

    def test_temporal_value(self):
        assert CorrelationType.TEMPORAL.value == "temporal"

    def test_amplifying_value(self):
        assert CorrelationType.AMPLIFYING.value == "amplifying"

    def test_masking_value(self):
        assert CorrelationType.MASKING.value == "masking"

    def test_independent_value(self):
        assert CorrelationType.INDEPENDENT.value == "independent"

    def test_all_members(self):
        members = {m.value for m in CorrelationType}
        assert members == {"causal", "temporal", "amplifying", "masking", "independent"}

    def test_str_enum(self):
        assert isinstance(CorrelationType.CAUSAL, str)


# ===================================================================
# ExperimentResult model
# ===================================================================


class TestExperimentResult:
    def test_basic_creation(self):
        r = _make_result()
        assert r.experiment_id == "exp-1"
        assert r.target_component == "svc-a"

    def test_defaults(self):
        r = ExperimentResult(
            experiment_id="x",
            target_component="c",
            failure_type="crash",
            severity=0.5,
            impact_score=10.0,
            recovery_time_seconds=5.0,
        )
        assert r.affected_components == []
        assert r.success is True
        assert r.timestamp.tzinfo is not None

    def test_severity_bounds_zero(self):
        r = _make_result(severity=0.0)
        assert r.severity == 0.0

    def test_severity_bounds_one(self):
        r = _make_result(severity=1.0)
        assert r.severity == 1.0

    def test_impact_score_bounds_zero(self):
        r = _make_result(impact=0.0)
        assert r.impact_score == 0.0

    def test_impact_score_bounds_max(self):
        r = _make_result(impact=100.0)
        assert r.impact_score == 100.0

    def test_recovery_time_zero(self):
        r = _make_result(recovery=0.0)
        assert r.recovery_time_seconds == 0.0

    def test_success_false(self):
        r = _make_result(success=False)
        assert r.success is False

    def test_affected_components_list(self):
        r = _make_result(affected=["a", "b", "c"])
        assert r.affected_components == ["a", "b", "c"]

    def test_failure_type(self):
        r = _make_result(failure_type="crash")
        assert r.failure_type == "crash"


# ===================================================================
# Correlation model
# ===================================================================


class TestCorrelationModel:
    def test_creation(self):
        c = Correlation(
            source_experiment="a",
            target_experiment="b",
            correlation_type=CorrelationType.CAUSAL,
            strength=0.8,
            confidence=0.9,
            description="test",
        )
        assert c.source_experiment == "a"
        assert c.target_experiment == "b"
        assert c.correlation_type == CorrelationType.CAUSAL

    def test_defaults(self):
        c = Correlation(
            source_experiment="a",
            target_experiment="b",
            correlation_type=CorrelationType.TEMPORAL,
            strength=0.5,
            confidence=0.5,
        )
        assert c.description == ""


# ===================================================================
# HiddenDependency model
# ===================================================================


class TestHiddenDependencyModel:
    def test_creation(self):
        h = HiddenDependency(
            component_a="x",
            component_b="y",
            evidence_count=3,
            correlation_strength=0.7,
            discovery_method="jaccard",
        )
        assert h.component_a == "x"
        assert h.component_b == "y"
        assert h.evidence_count == 3

    def test_defaults(self):
        h = HiddenDependency(
            component_a="x",
            component_b="y",
            correlation_strength=0.5,
        )
        assert h.evidence_count == 0
        assert h.discovery_method == ""


# ===================================================================
# EmergentPattern model
# ===================================================================


class TestEmergentPatternModel:
    def test_creation(self):
        p = EmergentPattern(
            name="cascade",
            description="desc",
            involved_experiments=["e1", "e2"],
            frequency=2,
            risk_multiplier=1.5,
            recommended_action="fix it",
        )
        assert p.name == "cascade"
        assert p.frequency == 2
        assert len(p.pattern_id) > 0

    def test_defaults(self):
        p = EmergentPattern(name="test")
        assert p.description == ""
        assert p.involved_experiments == []
        assert p.frequency == 0
        assert p.risk_multiplier == 1.0
        assert p.recommended_action == ""

    def test_auto_pattern_id(self):
        p1 = EmergentPattern(name="a")
        p2 = EmergentPattern(name="b")
        assert p1.pattern_id != p2.pattern_id


# ===================================================================
# CorrelationReport model
# ===================================================================


class TestCorrelationReportModel:
    def test_creation(self):
        rpt = CorrelationReport(
            total_experiments_analyzed=5,
            coverage_score=80.0,
        )
        assert rpt.total_experiments_analyzed == 5
        assert rpt.coverage_score == 80.0

    def test_defaults(self):
        rpt = CorrelationReport()
        assert rpt.correlations == []
        assert rpt.hidden_dependencies == []
        assert rpt.emergent_patterns == []
        assert rpt.total_experiments_analyzed == 0
        assert rpt.coverage_score == 0.0


# ===================================================================
# Helper functions
# ===================================================================


class TestJaccardSimilarity:
    def test_identical_sets(self):
        assert _jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets(self):
        assert _jaccard_similarity({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        assert _jaccard_similarity({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)

    def test_empty_both(self):
        assert _jaccard_similarity(set(), set()) == 0.0

    def test_one_empty(self):
        assert _jaccard_similarity({"a"}, set()) == 0.0

    def test_subset(self):
        assert _jaccard_similarity({"a"}, {"a", "b"}) == 0.5


class TestOverlapRatio:
    def test_identical(self):
        assert _overlap_ratio({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint(self):
        assert _overlap_ratio({"a"}, {"b"}) == 0.0

    def test_partial(self):
        # intersection={b}, min(2,2)=2, ratio=0.5
        assert _overlap_ratio({"a", "b"}, {"b", "c"}) == pytest.approx(0.5)

    def test_empty_first(self):
        assert _overlap_ratio(set(), {"a"}) == 0.0

    def test_empty_second(self):
        assert _overlap_ratio({"a"}, set()) == 0.0

    def test_both_empty(self):
        assert _overlap_ratio(set(), set()) == 0.0

    def test_subset(self):
        assert _overlap_ratio({"a"}, {"a", "b"}) == 1.0


# ===================================================================
# ChaosCorrelationEngine — add_result / add_results
# ===================================================================


class TestEngineAddResults:
    def test_init_empty(self):
        engine = ChaosCorrelationEngine()
        assert engine.results == []

    def test_add_single(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result())
        assert len(engine.results) == 1

    def test_add_multiple_singles(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1"))
        engine.add_result(_make_result("e2"))
        assert len(engine.results) == 2

    def test_add_batch(self):
        engine = ChaosCorrelationEngine()
        engine.add_results([_make_result("e1"), _make_result("e2"), _make_result("e3")])
        assert len(engine.results) == 3

    def test_add_batch_empty(self):
        engine = ChaosCorrelationEngine()
        engine.add_results([])
        assert len(engine.results) == 0

    def test_add_single_and_batch(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1"))
        engine.add_results([_make_result("e2"), _make_result("e3")])
        assert len(engine.results) == 3

    def test_results_returns_copy(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result())
        results = engine.results
        results.clear()
        assert len(engine.results) == 1


# ===================================================================
# ChaosCorrelationEngine — find_correlations
# ===================================================================


class TestFindCorrelations:
    def test_no_results(self):
        engine = ChaosCorrelationEngine()
        assert engine.find_correlations() == []

    def test_single_result(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result())
        assert engine.find_correlations() == []

    def test_no_overlap(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["x"]))
        engine.add_result(_make_result("e2", affected=["y"]))
        assert engine.find_correlations() == []

    def test_causal_same_target(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", target="svc-a", affected=["x", "y"]))
        engine.add_result(_make_result("e2", target="svc-a", affected=["x", "z"]))
        corrs = engine.find_correlations()
        assert len(corrs) >= 1
        assert corrs[0].correlation_type == CorrelationType.CAUSAL

    def test_temporal_same_affected(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="svc-a", affected=["x", "y"], impact=50.0)
        )
        engine.add_result(
            _make_result("e2", target="svc-b", affected=["x", "y"], impact=50.0)
        )
        corrs = engine.find_correlations()
        assert len(corrs) >= 1
        assert corrs[0].correlation_type == CorrelationType.TEMPORAL

    def test_amplifying_large_impact_diff(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="svc-a", affected=["x", "y"], impact=10.0)
        )
        engine.add_result(
            _make_result("e2", target="svc-b", affected=["x", "y"], impact=80.0)
        )
        corrs = engine.find_correlations()
        assert len(corrs) >= 1
        assert corrs[0].correlation_type == CorrelationType.AMPLIFYING

    def test_masking_target_in_affected(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result(
                "e1", target="svc-a", affected=["svc-b", "x"], impact=50.0
            )
        )
        engine.add_result(
            _make_result("e2", target="svc-b", affected=["x"], impact=50.0)
        )
        corrs = engine.find_correlations()
        assert len(corrs) >= 1
        assert corrs[0].correlation_type == CorrelationType.MASKING

    def test_correlation_strength_bounded(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b", "c"]))
        engine.add_result(_make_result("e2", affected=["a", "b", "c"]))
        corrs = engine.find_correlations()
        for c in corrs:
            assert 0.0 <= c.strength <= 1.0

    def test_correlation_confidence_bounded(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", severity=1.0, affected=["a", "b"]))
        engine.add_result(_make_result("e2", severity=1.0, affected=["a", "b"]))
        corrs = engine.find_correlations()
        for c in corrs:
            assert 0.0 <= c.confidence <= 1.0

    def test_correlation_has_description(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b"]))
        engine.add_result(_make_result("e2", affected=["a", "b"]))
        corrs = engine.find_correlations()
        assert len(corrs) >= 1
        assert "e1" in corrs[0].description
        assert "e2" in corrs[0].description

    def test_below_overlap_threshold(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b", "c", "d"]))
        engine.add_result(_make_result("e2", affected=["e", "f", "g", "h"]))
        assert engine.find_correlations() == []

    def test_three_experiments_pairwise(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", target="s1", affected=["a", "b"]))
        engine.add_result(_make_result("e2", target="s2", affected=["a", "b"]))
        engine.add_result(_make_result("e3", target="s3", affected=["a", "b"]))
        corrs = engine.find_correlations()
        # C(3,2) = 3 pairs
        assert len(corrs) == 3

    def test_empty_affected_no_correlation(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=[]))
        engine.add_result(_make_result("e2", affected=[]))
        assert engine.find_correlations() == []

    def test_correlation_source_and_target(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("alpha", affected=["x", "y"]))
        engine.add_result(_make_result("beta", affected=["x", "y"]))
        corrs = engine.find_correlations()
        assert corrs[0].source_experiment == "alpha"
        assert corrs[0].target_experiment == "beta"


# ===================================================================
# ChaosCorrelationEngine — discover_hidden_dependencies
# ===================================================================


class TestDiscoverHiddenDependencies:
    def test_no_results(self):
        engine = ChaosCorrelationEngine()
        assert engine.discover_hidden_dependencies() == []

    def test_single_result(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result(affected=["a", "b"]))
        assert engine.discover_hidden_dependencies() == []

    def test_pair_appears_once_not_enough(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b"]))
        engine.add_result(_make_result("e2", affected=["c", "d"]))
        assert engine.discover_hidden_dependencies() == []

    def test_pair_appears_multiple_times(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["db", "cache"]))
        engine.add_result(_make_result("e2", affected=["db", "cache"]))
        engine.add_result(_make_result("e3", affected=["db", "cache"]))
        deps = engine.discover_hidden_dependencies()
        assert len(deps) >= 1
        dep = deps[0]
        assert dep.component_a == "cache"
        assert dep.component_b == "db"
        assert dep.evidence_count == 3

    def test_jaccard_below_threshold(self):
        engine = ChaosCorrelationEngine()
        # a,b appear together in 2 experiments
        engine.add_result(_make_result("e1", affected=["a", "b"]))
        engine.add_result(_make_result("e2", affected=["a", "b"]))
        # but a also appears alone in many experiments, lowering Jaccard
        engine.add_result(_make_result("e3", affected=["a"]))
        engine.add_result(_make_result("e4", affected=["a"]))
        engine.add_result(_make_result("e5", affected=["a"]))
        engine.add_result(_make_result("e6", affected=["a"]))
        deps = engine.discover_hidden_dependencies()
        # Jaccard for (a,b): exps_a={e1,e2,e3,e4,e5,e6}, exps_b={e1,e2}
        # jaccard = 2/6 = 0.333 < 0.4 => no dependency
        assert len(deps) == 0

    def test_discovery_method(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b"]))
        engine.add_result(_make_result("e2", affected=["a", "b"]))
        deps = engine.discover_hidden_dependencies()
        assert len(deps) >= 1
        assert deps[0].discovery_method == "jaccard_co_occurrence"

    def test_correlation_strength_bounded(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b"]))
        engine.add_result(_make_result("e2", affected=["a", "b"]))
        deps = engine.discover_hidden_dependencies()
        for d in deps:
            assert 0.0 <= d.correlation_strength <= 1.0

    def test_empty_affected_components(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=[]))
        engine.add_result(_make_result("e2", affected=[]))
        assert engine.discover_hidden_dependencies() == []

    def test_single_affected_component(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a"]))
        engine.add_result(_make_result("e2", affected=["a"]))
        # Single component — no pairs
        assert engine.discover_hidden_dependencies() == []

    def test_multiple_pairs_discovered(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b", "c"]))
        engine.add_result(_make_result("e2", affected=["a", "b", "c"]))
        deps = engine.discover_hidden_dependencies()
        # a-b, a-c, b-c all appear together twice with jaccard=1.0
        assert len(deps) == 3


# ===================================================================
# ChaosCorrelationEngine — detect_emergent_patterns
# ===================================================================


class TestDetectEmergentPatterns:
    def test_no_results(self):
        engine = ChaosCorrelationEngine()
        assert engine.detect_emergent_patterns() == []

    def test_single_result(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result())
        assert engine.detect_emergent_patterns() == []

    def test_cascade_pattern(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b", "c"]))
        engine.add_result(_make_result("e2", affected=["d", "e", "f"]))
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "cascade_failure" in names

    def test_cascade_requires_3_affected(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b"]))
        engine.add_result(_make_result("e2", affected=["c", "d"]))
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "cascade_failure" not in names

    def test_cascade_requires_2_experiments(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b", "c"]))
        engine.add_result(_make_result("e2", affected=["d"]))
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "cascade_failure" not in names

    def test_split_brain_pattern(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="svc-a", affected=["shared-db"])
        )
        engine.add_result(
            _make_result("e2", target="svc-b", affected=["shared-db"])
        )
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "split_brain" in names

    def test_split_brain_no_shared_affected(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", target="svc-a", affected=["x"]))
        engine.add_result(_make_result("e2", target="svc-b", affected=["y"]))
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "split_brain" not in names

    def test_thundering_herd_pattern(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", impact=80.0, recovery=10.0, affected=["a"])
        )
        engine.add_result(
            _make_result("e2", impact=70.0, recovery=5.0, affected=["b"])
        )
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "thundering_herd" in names

    def test_thundering_herd_needs_high_impact(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", impact=30.0, recovery=5.0, affected=["a"])
        )
        engine.add_result(
            _make_result("e2", impact=20.0, recovery=5.0, affected=["b"])
        )
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "thundering_herd" not in names

    def test_thundering_herd_needs_fast_recovery(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", impact=80.0, recovery=60.0, affected=["a"])
        )
        engine.add_result(
            _make_result("e2", impact=70.0, recovery=120.0, affected=["b"])
        )
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "thundering_herd" not in names

    def test_thundering_herd_needs_2_experiments(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", impact=80.0, recovery=5.0, affected=["a"])
        )
        engine.add_result(
            _make_result("e2", impact=20.0, recovery=60.0, affected=["b"])
        )
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "thundering_herd" not in names

    def test_multiple_patterns_detected(self):
        engine = ChaosCorrelationEngine()
        # cascade (3+ affected) + thundering herd (high impact + fast recovery)
        engine.add_result(
            _make_result(
                "e1",
                target="svc-a",
                affected=["a", "b", "c"],
                impact=80.0,
                recovery=5.0,
            )
        )
        engine.add_result(
            _make_result(
                "e2",
                target="svc-b",
                affected=["d", "e", "f"],
                impact=90.0,
                recovery=10.0,
            )
        )
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "cascade_failure" in names
        assert "thundering_herd" in names

    def test_cascade_risk_multiplier(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b", "c"], impact=50.0))
        engine.add_result(_make_result("e2", affected=["d", "e", "f"], impact=50.0))
        patterns = engine.detect_emergent_patterns()
        cascade = [p for p in patterns if p.name == "cascade_failure"][0]
        assert cascade.risk_multiplier == pytest.approx(1.5)

    def test_cascade_involved_experiments(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b", "c"]))
        engine.add_result(_make_result("e2", affected=["d", "e", "f"]))
        patterns = engine.detect_emergent_patterns()
        cascade = [p for p in patterns if p.name == "cascade_failure"][0]
        assert "e1" in cascade.involved_experiments
        assert "e2" in cascade.involved_experiments

    def test_cascade_has_recommended_action(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b", "c"]))
        engine.add_result(_make_result("e2", affected=["d", "e", "f"]))
        patterns = engine.detect_emergent_patterns()
        cascade = [p for p in patterns if p.name == "cascade_failure"][0]
        assert len(cascade.recommended_action) > 0

    def test_split_brain_risk_multiplier(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="svc-a", affected=["shared"])
        )
        engine.add_result(
            _make_result("e2", target="svc-b", affected=["shared"])
        )
        patterns = engine.detect_emergent_patterns()
        sb = [p for p in patterns if p.name == "split_brain"][0]
        assert sb.risk_multiplier == 1.5

    def test_thundering_herd_risk_multiplier(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", impact=80.0, recovery=5.0, affected=["a"])
        )
        engine.add_result(
            _make_result("e2", impact=70.0, recovery=5.0, affected=["b"])
        )
        patterns = engine.detect_emergent_patterns()
        herd = [p for p in patterns if p.name == "thundering_herd"][0]
        assert herd.risk_multiplier == 2.0

    def test_patterns_have_descriptions(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result(
                "e1", target="svc-a", affected=["a", "b", "c"], impact=80.0, recovery=5.0,
            )
        )
        engine.add_result(
            _make_result(
                "e2", target="svc-b", affected=["d", "e", "f"], impact=70.0, recovery=5.0,
            )
        )
        patterns = engine.detect_emergent_patterns()
        for p in patterns:
            assert len(p.description) > 0

    def test_split_brain_same_target_no_detection(self):
        """Split-brain requires different targets."""
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="svc-a", affected=["shared"])
        )
        engine.add_result(
            _make_result("e2", target="svc-a", affected=["shared"])
        )
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "split_brain" not in names


# ===================================================================
# ChaosCorrelationEngine — calculate_coverage
# ===================================================================


class TestCalculateCoverage:
    def test_no_results_no_components(self):
        engine = ChaosCorrelationEngine()
        assert engine.calculate_coverage([]) == 0.0

    def test_no_results_with_components(self):
        engine = ChaosCorrelationEngine()
        assert engine.calculate_coverage(["a", "b"]) == 0.0

    def test_full_coverage(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result(target="a", affected=["b"]))
        assert engine.calculate_coverage(["a", "b"]) == 100.0

    def test_partial_coverage(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result(target="a", affected=[]))
        assert engine.calculate_coverage(["a", "b"]) == 50.0

    def test_zero_coverage(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result(target="x", affected=[]))
        assert engine.calculate_coverage(["a", "b"]) == 0.0

    def test_coverage_includes_target(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result(target="a", affected=[]))
        assert engine.calculate_coverage(["a"]) == 100.0

    def test_coverage_includes_affected(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result(target="x", affected=["a"]))
        assert engine.calculate_coverage(["a"]) == 100.0

    def test_coverage_with_extra_tested(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result(target="a", affected=["b", "c"]))
        # Only a and b are in all_components; c is extra tested but not counted
        assert engine.calculate_coverage(["a", "b"]) == 100.0

    def test_empty_components_list(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result(target="a", affected=["b"]))
        assert engine.calculate_coverage([]) == 0.0

    def test_coverage_multiple_experiments(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", target="a", affected=[]))
        engine.add_result(_make_result("e2", target="b", affected=[]))
        assert engine.calculate_coverage(["a", "b", "c"]) == pytest.approx(200 / 3)

    def test_all_components_affected(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result(target="a", affected=["b", "c", "d", "e"])
        )
        assert engine.calculate_coverage(["a", "b", "c", "d", "e"]) == 100.0


# ===================================================================
# ChaosCorrelationEngine — generate_report
# ===================================================================


class TestGenerateReport:
    def test_empty_report(self):
        engine = ChaosCorrelationEngine()
        report = engine.generate_report([])
        assert report.total_experiments_analyzed == 0
        assert report.coverage_score == 0.0
        assert report.correlations == []
        assert report.hidden_dependencies == []
        assert report.emergent_patterns == []

    def test_report_with_data(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="a", affected=["x", "y", "z"], impact=50.0)
        )
        engine.add_result(
            _make_result("e2", target="b", affected=["x", "y", "z"], impact=50.0)
        )
        report = engine.generate_report(["a", "b", "x", "y", "z"])
        assert report.total_experiments_analyzed == 2
        assert report.coverage_score == 100.0
        assert len(report.correlations) >= 1

    def test_report_type(self):
        engine = ChaosCorrelationEngine()
        report = engine.generate_report([])
        assert isinstance(report, CorrelationReport)

    def test_report_coverage_with_components(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result(target="a", affected=[]))
        report = engine.generate_report(["a", "b"])
        assert report.coverage_score == 50.0

    def test_report_experiment_count(self):
        engine = ChaosCorrelationEngine()
        engine.add_results([_make_result(f"e{i}") for i in range(5)])
        report = engine.generate_report([])
        assert report.total_experiments_analyzed == 5

    def test_report_includes_correlations(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", target="s", affected=["a", "b"]))
        engine.add_result(_make_result("e2", target="s", affected=["a", "b"]))
        report = engine.generate_report([])
        assert len(report.correlations) >= 1

    def test_report_includes_hidden_deps(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b"]))
        engine.add_result(_make_result("e2", affected=["a", "b"]))
        report = engine.generate_report([])
        assert len(report.hidden_dependencies) >= 1

    def test_report_includes_patterns(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="s1", affected=["a", "b", "c"])
        )
        engine.add_result(
            _make_result("e2", target="s2", affected=["d", "e", "f"])
        )
        report = engine.generate_report([])
        assert len(report.emergent_patterns) >= 1


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    def test_two_identical_results(self):
        engine = ChaosCorrelationEngine()
        r = _make_result("e1", affected=["a", "b"])
        engine.add_result(r)
        engine.add_result(r)
        corrs = engine.find_correlations()
        assert len(corrs) >= 1

    def test_all_components_affected_in_all(self):
        engine = ChaosCorrelationEngine()
        all_c = ["a", "b", "c", "d", "e"]
        engine.add_result(_make_result("e1", affected=all_c))
        engine.add_result(_make_result("e2", affected=all_c))
        corrs = engine.find_correlations()
        assert len(corrs) >= 1

    def test_very_low_severity(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", severity=0.01, affected=["a", "b"])
        )
        engine.add_result(
            _make_result("e2", severity=0.01, affected=["a", "b"])
        )
        corrs = engine.find_correlations()
        assert len(corrs) >= 1

    def test_very_high_severity(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", severity=1.0, affected=["a", "b"])
        )
        engine.add_result(
            _make_result("e2", severity=1.0, affected=["a", "b"])
        )
        corrs = engine.find_correlations()
        assert len(corrs) >= 1

    def test_zero_recovery_time(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", recovery=0.0, affected=["a"])
        )
        report = engine.generate_report(["a"])
        assert report.total_experiments_analyzed == 1

    def test_very_large_recovery_time(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", recovery=86400.0, affected=["a"])
        )
        report = engine.generate_report(["a"])
        assert report.total_experiments_analyzed == 1

    def test_mix_success_and_failure(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", success=True, affected=["a"]))
        engine.add_result(_make_result("e2", success=False, affected=["a"]))
        corrs = engine.find_correlations()
        assert len(corrs) >= 1

    def test_many_experiments(self):
        engine = ChaosCorrelationEngine()
        for i in range(20):
            engine.add_result(
                _make_result(f"e{i}", target=f"svc-{i % 5}", affected=["shared"])
            )
        report = engine.generate_report([f"svc-{i}" for i in range(5)] + ["shared"])
        assert report.total_experiments_analyzed == 20

    def test_duplicate_affected_components(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "a", "b"]))
        engine.add_result(_make_result("e2", affected=["a", "b", "b"]))
        corrs = engine.find_correlations()
        assert len(corrs) >= 1

    def test_thundering_herd_boundary_impact_50(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", impact=50.0, recovery=30.0, affected=["a"])
        )
        engine.add_result(
            _make_result("e2", impact=50.0, recovery=30.0, affected=["b"])
        )
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "thundering_herd" in names

    def test_thundering_herd_boundary_recovery_30(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", impact=60.0, recovery=30.0, affected=["a"])
        )
        engine.add_result(
            _make_result("e2", impact=60.0, recovery=31.0, affected=["b"])
        )
        patterns = engine.detect_emergent_patterns()
        herd = [p for p in patterns if p.name == "thundering_herd"]
        # e2 has recovery 31 > 30, so only e1 qualifies — needs 2
        assert len(herd) == 0

    def test_cascade_boundary_2_affected(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b"]))
        engine.add_result(_make_result("e2", affected=["c", "d"]))
        patterns = engine.detect_emergent_patterns()
        cascade = [p for p in patterns if p.name == "cascade_failure"]
        assert len(cascade) == 0

    def test_cascade_boundary_3_affected(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", affected=["a", "b", "c"]))
        engine.add_result(_make_result("e2", affected=["d", "e", "f"]))
        patterns = engine.detect_emergent_patterns()
        cascade = [p for p in patterns if p.name == "cascade_failure"]
        assert len(cascade) == 1

    def test_masking_reverse_direction(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="svc-a", affected=["x"], impact=50.0)
        )
        engine.add_result(
            _make_result("e2", target="svc-b", affected=["svc-a", "x"], impact=50.0)
        )
        corrs = engine.find_correlations()
        assert len(corrs) >= 1
        assert corrs[0].correlation_type == CorrelationType.MASKING

    def test_split_brain_with_empty_affected(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", target="svc-a", affected=[]))
        engine.add_result(_make_result("e2", target="svc-b", affected=[]))
        patterns = engine.detect_emergent_patterns()
        names = [p.name for p in patterns]
        assert "split_brain" not in names

    def test_split_brain_description_contains_targets(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="svc-a", affected=["shared"])
        )
        engine.add_result(
            _make_result("e2", target="svc-b", affected=["shared"])
        )
        patterns = engine.detect_emergent_patterns()
        sb = [p for p in patterns if p.name == "split_brain"][0]
        assert "svc-a" in sb.description
        assert "svc-b" in sb.description

    def test_thundering_herd_has_recommended_action(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", impact=80.0, recovery=5.0, affected=["a"])
        )
        engine.add_result(
            _make_result("e2", impact=70.0, recovery=5.0, affected=["b"])
        )
        patterns = engine.detect_emergent_patterns()
        herd = [p for p in patterns if p.name == "thundering_herd"][0]
        assert len(herd.recommended_action) > 0

    def test_split_brain_has_recommended_action(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="svc-a", affected=["shared"])
        )
        engine.add_result(
            _make_result("e2", target="svc-b", affected=["shared"])
        )
        patterns = engine.detect_emergent_patterns()
        sb = [p for p in patterns if p.name == "split_brain"][0]
        assert len(sb.recommended_action) > 0


# ===================================================================
# Integration / realistic scenarios
# ===================================================================


class TestRealisticScenarios:
    def test_microservice_cascade(self):
        """Simulate a microservice cascade failure scenario."""
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result(
                "db-failure",
                target="postgres",
                failure_type="crash",
                severity=0.9,
                affected=["user-svc", "order-svc", "payment-svc"],
                impact=85.0,
                recovery=120.0,
            )
        )
        engine.add_result(
            _make_result(
                "cache-failure",
                target="redis",
                failure_type="eviction",
                severity=0.6,
                affected=["user-svc", "session-svc", "order-svc"],
                impact=60.0,
                recovery=30.0,
            )
        )
        report = engine.generate_report(
            ["postgres", "redis", "user-svc", "order-svc", "payment-svc", "session-svc"]
        )
        assert report.total_experiments_analyzed == 2
        assert report.coverage_score == 100.0
        assert len(report.correlations) >= 1

    def test_independent_experiments(self):
        """Experiments on completely different components."""
        engine = ChaosCorrelationEngine()
        engine.add_result(
            _make_result("e1", target="frontend", affected=["cdn"])
        )
        engine.add_result(
            _make_result("e2", target="backend", affected=["database"])
        )
        corrs = engine.find_correlations()
        assert len(corrs) == 0

    def test_full_coverage_scenario(self):
        engine = ChaosCorrelationEngine()
        components = ["api", "db", "cache", "queue", "worker"]
        for comp in components:
            engine.add_result(_make_result(f"test-{comp}", target=comp, affected=[]))
        assert engine.calculate_coverage(components) == 100.0

    def test_zero_coverage_scenario(self):
        engine = ChaosCorrelationEngine()
        engine.add_result(_make_result("e1", target="unrelated", affected=[]))
        assert engine.calculate_coverage(["api", "db", "cache"]) == 0.0
