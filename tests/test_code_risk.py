# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for code-level risk analysis engine."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from faultray.model.code_components import (
    AuthorType,
    CodeComponent,
    CodeLanguage,
    ComplexityClass,
    DiffImpact,
    HallucinationRiskProfile,
    RuntimeCostProfile,
)
from faultray.simulator.code_risk_engine import CodeRiskEngine


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestHallucinationRiskProfile:
    """Tests for HallucinationRiskProfile.composite_risk."""

    def test_human_author_minimal_risk(self):
        h = HallucinationRiskProfile(
            author_type=AuthorType.HUMAN,
            base_hallucination_risk=0.01,
        )
        assert h.composite_risk == pytest.approx(0.01, abs=0.001)

    def test_ai_author_higher_base_risk(self):
        h = HallucinationRiskProfile(
            author_type=AuthorType.AI_GPT,
            base_hallucination_risk=0.05,
        )
        assert h.composite_risk > 0.01

    def test_nonexistent_api_increases_risk(self):
        base = HallucinationRiskProfile(
            author_type=AuthorType.AI_CLAUDE,
            base_hallucination_risk=0.03,
        )
        with_api = HallucinationRiskProfile(
            author_type=AuthorType.AI_CLAUDE,
            base_hallucination_risk=0.03,
            uses_nonexistent_api=0.5,
        )
        assert with_api.composite_risk > base.composite_risk

    def test_tests_reduce_risk(self):
        without = HallucinationRiskProfile(
            author_type=AuthorType.AI_GPT,
            base_hallucination_risk=0.05,
            uses_nonexistent_api=0.3,
        )
        with_tests = HallucinationRiskProfile(
            author_type=AuthorType.AI_GPT,
            base_hallucination_risk=0.05,
            uses_nonexistent_api=0.3,
            has_tests=True,
            tests_pass=True,
        )
        assert with_tests.composite_risk < without.composite_risk

    def test_human_review_reduces_risk(self):
        without = HallucinationRiskProfile(
            author_type=AuthorType.AI_CLAUDE,
            base_hallucination_risk=0.03,
            incorrect_error_handling=0.2,
        )
        with_review = HallucinationRiskProfile(
            author_type=AuthorType.AI_CLAUDE,
            base_hallucination_risk=0.03,
            incorrect_error_handling=0.2,
            human_reviewed=True,
        )
        assert with_review.composite_risk < without.composite_risk

    def test_all_mitigations_greatly_reduce_risk(self):
        h = HallucinationRiskProfile(
            author_type=AuthorType.AI_GPT,
            base_hallucination_risk=0.05,
            uses_nonexistent_api=0.5,
            has_tests=True,
            tests_pass=True,
            human_reviewed=True,
            type_checked=True,
        )
        # With all mitigations, even high-risk code should be < 0.05
        assert h.composite_risk < 0.05

    def test_risk_capped_at_1(self):
        h = HallucinationRiskProfile(
            author_type=AuthorType.AI_UNKNOWN,
            base_hallucination_risk=1.0,
            uses_nonexistent_api=1.0,
            wrong_argument_order=1.0,
            incorrect_error_handling=1.0,
            stale_dependency=1.0,
        )
        assert h.composite_risk <= 1.0


class TestDiffImpact:
    """Tests for DiffImpact computed properties."""

    def test_cpu_delta_positive_is_regression(self):
        d = DiffImpact(
            cost_before=RuntimeCostProfile(estimated_cpu_ms_per_call=1.0),
            cost_after=RuntimeCostProfile(estimated_cpu_ms_per_call=5.0),
        )
        assert d.cpu_delta_ms == pytest.approx(4.0)
        assert d.is_regression is True

    def test_cpu_delta_negative_is_improvement(self):
        d = DiffImpact(
            cost_before=RuntimeCostProfile(estimated_cpu_ms_per_call=10.0),
            cost_after=RuntimeCostProfile(estimated_cpu_ms_per_call=2.0),
        )
        assert d.cpu_delta_ms == pytest.approx(-8.0)
        assert d.is_regression is False

    def test_memory_delta(self):
        d = DiffImpact(
            cost_before=RuntimeCostProfile(estimated_memory_mb_per_call=10.0),
            cost_after=RuntimeCostProfile(estimated_memory_mb_per_call=50.0),
        )
        assert d.memory_delta_mb == pytest.approx(40.0)

    def test_io_delta(self):
        d = DiffImpact(
            cost_before=RuntimeCostProfile(estimated_io_calls_per_invocation=2),
            cost_after=RuntimeCostProfile(estimated_io_calls_per_invocation=5),
        )
        assert d.io_delta == 3

    def test_zero_delta_not_regression(self):
        d = DiffImpact(
            cost_before=RuntimeCostProfile(estimated_cpu_ms_per_call=5.0),
            cost_after=RuntimeCostProfile(estimated_cpu_ms_per_call=5.0),
        )
        assert d.is_regression is False


class TestCodeComponent:
    """Tests for CodeComponent computed properties."""

    def test_cpu_load_calculation(self):
        cc = CodeComponent(
            id="test",
            name="test.py",
            runtime_cost=RuntimeCostProfile(estimated_cpu_ms_per_call=10.0),
            calls_per_minute=600,  # 10 calls/sec * 10ms = 100ms/sec = 10% of 1 core
        )
        assert cc.estimated_cpu_load_percent == pytest.approx(10.0, abs=0.1)

    def test_cpu_load_capped_at_100(self):
        cc = CodeComponent(
            id="test",
            name="test.py",
            runtime_cost=RuntimeCostProfile(estimated_cpu_ms_per_call=1000.0),
            calls_per_minute=6000,
        )
        assert cc.estimated_cpu_load_percent == 100.0

    def test_zero_calls_zero_load(self):
        cc = CodeComponent(
            id="test",
            name="test.py",
            runtime_cost=RuntimeCostProfile(estimated_cpu_ms_per_call=100.0),
            calls_per_minute=0,
        )
        assert cc.estimated_cpu_load_percent == 0.0

    def test_risk_score_combines_cpu_and_ai(self):
        # High CPU + high AI = high risk
        high = CodeComponent(
            id="test",
            name="test.py",
            runtime_cost=RuntimeCostProfile(estimated_cpu_ms_per_call=100.0),
            calls_per_minute=6000,
            hallucination_risk=HallucinationRiskProfile(
                author_type=AuthorType.AI_GPT,
                base_hallucination_risk=0.05,
                uses_nonexistent_api=0.5,
            ),
        )
        # Low CPU + human = low risk
        low = CodeComponent(
            id="test2",
            name="test2.py",
            runtime_cost=RuntimeCostProfile(estimated_cpu_ms_per_call=1.0),
            calls_per_minute=10,
            hallucination_risk=HallucinationRiskProfile(
                author_type=AuthorType.HUMAN,
                base_hallucination_risk=0.01,
            ),
        )
        assert high.risk_score > low.risk_score


# ---------------------------------------------------------------------------
# Engine tests
# ---------------------------------------------------------------------------


class TestCodeRiskEngineAnalysis:
    """Tests for CodeRiskEngine analysis functions."""

    @pytest.fixture()
    def engine(self):
        return CodeRiskEngine(repo_path="/home/user/repos/faultray")

    def test_detect_language_python(self, engine):
        assert engine._detect_language("src/main.py") == CodeLanguage.PYTHON

    def test_detect_language_typescript(self, engine):
        assert engine._detect_language("src/app.tsx") == CodeLanguage.TYPESCRIPT
        assert engine._detect_language("src/app.ts") == CodeLanguage.TYPESCRIPT

    def test_detect_language_go(self, engine):
        assert engine._detect_language("cmd/main.go") == CodeLanguage.GO

    def test_detect_language_unknown(self, engine):
        assert engine._detect_language("README.md") == CodeLanguage.UNKNOWN
        assert engine._detect_language("data.json") == CodeLanguage.UNKNOWN

    def test_complexity_constant(self, engine):
        code = "x = 1\ny = 2\nreturn x + y"
        assert engine._estimate_complexity(code) == ComplexityClass.O_1

    def test_complexity_linear(self, engine):
        code = "for item in items:\n    process(item)"
        assert engine._estimate_complexity(code) == ComplexityClass.O_N

    def test_complexity_quadratic(self, engine):
        code = "for i in items:\n    for j in items:\n        compare(i, j)"
        assert engine._estimate_complexity(code) == ComplexityClass.O_N2

    def test_complexity_sort(self, engine):
        code = "result = sorted(items)"
        assert engine._estimate_complexity(code) == ComplexityClass.O_N_LOG_N

    def test_runtime_cost_detects_io(self, engine):
        code = "result = db.query('SELECT 1')\ndata = requests.get(url)"
        cost = engine._estimate_runtime_cost(code, CodeLanguage.PYTHON, ComplexityClass.O_1)
        assert cost.estimated_io_calls_per_invocation >= 2
        assert cost.network_calls_per_invocation >= 1

    def test_runtime_cost_detects_blocking(self, engine):
        code = "time.sleep(5)\nresult = lock.acquire()"
        cost = engine._estimate_runtime_cost(code, CodeLanguage.PYTHON, ComplexityClass.O_1)
        assert cost.is_blocking is True

    def test_hallucination_detects_bare_except(self, engine):
        code = "try:\n    x()\nexcept:\n    pass"
        h = engine._assess_hallucination_risk(code, AuthorType.AI_GPT, "test.py")
        assert h.incorrect_error_handling > 0

    def test_hallucination_clean_code(self, engine):
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        h = engine._assess_hallucination_risk(code, AuthorType.HUMAN, "test.py")
        assert h.composite_risk < 0.02

    def test_ai_author_detection_claude(self, engine):
        messages = {"test.py": ["security fix Co-Authored-By: Claude"]}
        assert engine._detect_ai_author("test.py", messages) == AuthorType.AI_CLAUDE

    def test_ai_author_detection_human(self, engine):
        messages = {"test.py": ["fix bug in parser"]}
        assert engine._detect_ai_author("test.py", messages) == AuthorType.HUMAN

    def test_ai_author_detection_missing_file(self, engine):
        messages = {}
        assert engine._detect_ai_author("test.py", messages) == AuthorType.HUMAN


class TestCodeRiskEngineDiffParsing:
    """Tests for diff parsing including edge cases."""

    @pytest.fixture()
    def engine(self):
        return CodeRiskEngine(repo_path="/home/user/repos/faultray")

    def test_parse_simple_diff(self, engine):
        diff = textwrap.dedent("""\
            diff --git a/src/main.py b/src/main.py
            --- a/src/main.py
            +++ b/src/main.py
            @@ -1,3 +1,5 @@
             existing line
            +new line 1
            +new line 2
            -removed line
        """)
        results = engine._parse_diff(diff)
        assert len(results) == 1
        path, added, removed, added_content, removed_content = results[0]
        assert path == "src/main.py"
        assert added == 2
        assert removed == 1
        assert "new line 1" in added_content
        assert "removed line" in removed_content

    def test_parse_binary_file_skipped(self, engine):
        diff = textwrap.dedent("""\
            diff --git a/image.png b/image.png
            Binary files a/image.png and b/image.png differ
            diff --git a/src/main.py b/src/main.py
            --- a/src/main.py
            +++ b/src/main.py
            @@ -1 +1,2 @@
             existing
            +new
        """)
        results = engine._parse_diff(diff)
        # Binary file should produce 0 added/removed, code file should be parsed
        assert any(r[0] == "src/main.py" and r[1] == 1 for r in results)

    def test_parse_empty_diff(self, engine):
        results = engine._parse_diff("")
        assert results == []

    def test_parse_multiple_files(self, engine):
        diff = textwrap.dedent("""\
            diff --git a/a.py b/a.py
            --- a/a.py
            +++ b/a.py
            @@ -1 +1,2 @@
             x
            +y
            diff --git a/b.py b/b.py
            --- a/b.py
            +++ b/b.py
            @@ -1 +1,3 @@
             a
            +b
            +c
        """)
        results = engine._parse_diff(diff)
        assert len(results) == 2
        assert results[0][1] == 1  # a.py: 1 added
        assert results[1][1] == 2  # b.py: 2 added


class TestCodeRiskEngineIntegration:
    """Integration tests using actual git repo."""

    @pytest.fixture()
    def engine(self):
        return CodeRiskEngine(repo_path="/home/user/repos/faultray")

    def test_empty_diff_returns_zero_risk(self, engine):
        report = engine.analyze_diff("HEAD", "HEAD")
        assert report.overall_risk_score == 0.0
        assert len(report.diff_impacts) == 0

    def test_bad_ref_returns_zero_risk(self, engine):
        report = engine.analyze_diff("nonexistent-branch-xyz", "HEAD")
        assert report.overall_risk_score == 0.0

    def test_analyze_file_existing(self, engine):
        comp = engine.analyze_file("src/faultray/model/graph.py")
        assert comp.language == CodeLanguage.PYTHON
        assert comp.runtime_cost.estimated_cpu_ms_per_call > 0

    def test_analyze_file_nonexistent(self, engine):
        with pytest.raises(FileNotFoundError):
            engine.analyze_file("nonexistent.py")

    def test_report_to_dict_is_json_serializable(self, engine):
        report = engine.analyze_diff("HEAD~1", "HEAD")
        d = report.to_dict()
        json_str = json.dumps(d)
        assert len(json_str) > 0
        parsed = json.loads(json_str)
        assert "overall_risk_score" in parsed

    def test_report_has_recommendations(self, engine):
        report = engine.analyze_diff("HEAD~5", "HEAD")
        # recommendations depend on diff content; may be empty if recent
        # commits have no risky patterns. Verify the field exists and is a list.
        assert isinstance(report.recommendations, list)
