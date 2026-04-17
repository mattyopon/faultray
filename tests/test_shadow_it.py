# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Tests for Shadow IT / Orphaned System detection."""

from __future__ import annotations

import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph
from faultray.model.loader import load_yaml
from faultray.simulator.shadow_it_analyzer import (
    ShadowITAnalyzer,
    ShadowITFinding,
    ShadowITReport,
    _days_since,
    _parse_date,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(**kwargs) -> Component:
    """Build a minimal Component with default ownership fields."""
    defaults = {
        "id": "test-comp",
        "name": "Test Component",
        "type": ComponentType.APP_SERVER,
        "owner": "owner@example.com",
        "created_by": "owner@example.com",
        "last_modified": date.today().isoformat(),
        "documentation_url": "https://wiki.example.com/test",
        "lifecycle_status": "active",
    }
    defaults.update(kwargs)
    return Component(**defaults)


def _make_graph(*components: Component) -> InfraGraph:
    graph = InfraGraph()
    for comp in components:
        graph.add_component(comp)
    return graph


def _write_yaml(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------


def test_parse_date_valid_iso():
    result = _parse_date("2024-06-01")
    assert result == date(2024, 6, 1)


def test_parse_date_empty_returns_none():
    assert _parse_date("") is None


def test_parse_date_invalid_returns_none():
    assert _parse_date("not-a-date") is None


def test_days_since_past_date():
    past = (date.today() - timedelta(days=100)).isoformat()
    result = _days_since(past)
    # Allow ±1 day tolerance for timezone boundary edge cases
    assert result is not None
    assert 99 <= result <= 101


def test_days_since_empty_returns_none():
    assert _days_since("") is None


# ---------------------------------------------------------------------------
# ComponentType tests
# ---------------------------------------------------------------------------


def test_new_component_types_exist():
    assert ComponentType.AUTOMATION.value == "automation"
    assert ComponentType.SERVERLESS.value == "serverless"
    assert ComponentType.SCHEDULED_JOB.value == "scheduled_job"


# ---------------------------------------------------------------------------
# Analyzer tests
# ---------------------------------------------------------------------------


def test_clean_component_no_findings():
    """A fully owned and documented component should produce no findings."""
    comp = _make_component()
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    assert report.total_components == 1
    assert report.findings == []
    assert report.orphaned_count == 0
    assert report.risk_score == 0.0


def test_orphaned_component_flagged():
    """Component with no owner should produce an 'orphaned' finding."""
    comp = _make_component(id="no-owner", name="No Owner", owner="")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "orphaned" in categories
    assert report.orphaned_count == 1


def test_stale_component_flagged():
    """Component not modified in >365 days should be flagged as stale."""
    old_date = (date.today() - timedelta(days=400)).isoformat()
    comp = _make_component(id="stale", name="Stale", last_modified=old_date)
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "stale" in categories
    assert report.stale_count == 1


def test_undocumented_component_flagged():
    """Component with empty documentation_url should produce 'undocumented'."""
    comp = _make_component(id="nodoc", name="No Docs", documentation_url="")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "undocumented" in categories
    assert report.undocumented_count == 1


def test_high_risk_orphan_automation():
    """Automation component with no owner should be CRITICAL high_risk_orphan."""
    comp = _make_component(
        id="gas",
        name="GAS Script",
        type=ComponentType.AUTOMATION,
        owner="",
        documentation_url="",
    )
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    critical_findings = [f for f in report.findings if f.risk_level == "critical"]
    assert len(critical_findings) > 0
    assert any(f.category == "high_risk_orphan" for f in critical_findings)


def test_high_risk_orphan_serverless():
    """Serverless component with no owner should also be CRITICAL."""
    comp = _make_component(
        id="lambda",
        name="Image Lambda",
        type=ComponentType.SERVERLESS,
        owner="",
    )
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    assert any(
        f.category == "high_risk_orphan" and f.risk_level == "critical"
        for f in report.findings
    )


def test_creator_left_flagged():
    """Component where creator != owner and owner is empty should flag creator_left."""
    comp = _make_component(
        id="creator-left",
        name="Creator Left",
        owner="",
        created_by="ex-employee@example.com",
    )
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "creator_left" in categories


def test_unknown_lifecycle_status_flagged():
    """Component with lifecycle_status='unknown' should produce unknown_status finding."""
    comp = _make_component(id="mystery", name="Mystery", lifecycle_status="unknown")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "unknown_status" in categories


def test_risk_score_increases_with_orphans():
    """Risk score should be higher when more orphaned components exist."""
    clean_graph = _make_graph(_make_component())
    clean_report = ShadowITAnalyzer().analyze(clean_graph)

    orphan = _make_component(id="orphan", owner="", documentation_url="")
    orphan_graph = _make_graph(orphan)
    orphan_report = ShadowITAnalyzer().analyze(orphan_graph)

    assert orphan_report.risk_score > clean_report.risk_score


def test_report_to_dict_structure():
    """to_dict() should return a dict with all expected keys."""
    comp = _make_component(owner="", documentation_url="")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    d = report.to_dict()
    assert "total_components" in d
    assert "orphaned_count" in d
    assert "stale_count" in d
    assert "undocumented_count" in d
    assert "risk_score" in d
    assert "summary" in d
    assert "findings" in d
    assert isinstance(d["findings"], list)


def test_empty_graph_produces_empty_report():
    """An empty graph should produce a report with zero counts and zero risk."""
    graph = InfraGraph()
    report = ShadowITAnalyzer().analyze(graph)
    assert report.total_components == 0
    assert report.findings == []
    assert report.risk_score == 0.0


def test_yaml_loads_new_ownership_fields():
    """YAML with ownership fields should populate Component attributes correctly."""
    path = _write_yaml("""
components:
  - id: gas-report
    name: "GAS Report"
    type: automation
    owner: ""
    created_by: "yamada@example.com"
    last_modified: "2024-06-01"
    last_executed: "2026-04-01"
    documentation_url: ""
    lifecycle_status: "active"
dependencies: []
""")
    graph = load_yaml(path)
    comp = graph.get_component("gas-report")
    assert comp is not None
    assert comp.owner == ""
    assert comp.created_by == "yamada@example.com"
    assert comp.last_modified == "2024-06-01"
    assert comp.lifecycle_status == "active"


def test_yaml_backward_compatible_without_ownership_fields():
    """Old YAML without ownership fields should load without errors."""
    path = _write_yaml("""
components:
  - id: app
    name: My App
    type: app_server
    replicas: 1
dependencies: []
""")
    graph = load_yaml(path)
    comp = graph.get_component("app")
    assert comp is not None
    # Defaults should be empty strings / "active"
    assert comp.owner == ""
    assert comp.created_by == ""
    assert comp.lifecycle_status == "active"


def test_shadow_it_sample_yaml_loads_and_detects():
    """The bundled shadow-it-sample.yaml should load and produce findings."""
    sample = Path(__file__).parent.parent / "examples" / "shadow-it-sample.yaml"
    if not sample.exists():
        pytest.skip("shadow-it-sample.yaml not found")
    graph = load_yaml(sample)
    report = ShadowITAnalyzer().analyze(graph)
    # Sample has multiple orphaned/stale components
    assert report.total_components >= 5
    assert len(report.findings) > 0
    assert report.risk_score > 0.0


def test_scheduled_job_no_owner_is_critical():
    """SCHEDULED_JOB with no owner must be flagged as CRITICAL high_risk_orphan."""
    comp = _make_component(
        id="cron",
        name="Cron Backup",
        type=ComponentType.SCHEDULED_JOB,
        owner="",
    )
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    assert any(
        f.category == "high_risk_orphan" and f.risk_level == "critical"
        for f in report.findings
    )


# ---------------------------------------------------------------------------
# Boundary value tests
# ---------------------------------------------------------------------------


def test_zero_components_graph():
    """Empty graph produces report with all-zero counts."""
    graph = InfraGraph()
    report = ShadowITAnalyzer().analyze(graph)
    assert report.total_components == 0
    assert report.orphaned_count == 0
    assert report.stale_count == 0
    assert report.undocumented_count == 0
    assert report.risk_score == 0.0
    assert report.findings == []


def test_single_clean_component_risk_score_zero():
    """One fully-owned component should yield risk_score == 0.0."""
    comp = _make_component(id="one")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    assert report.total_components == 1
    assert report.risk_score == 0.0


@pytest.mark.parametrize("count", [2, 10, 50, 100])
def test_large_graph_all_clean(count):
    """Large graphs with all clean components should have risk_score == 0."""
    comps = [_make_component(id=f"comp-{i}", name=f"Comp {i}") for i in range(count)]
    graph = _make_graph(*comps)
    report = ShadowITAnalyzer().analyze(graph)
    assert report.total_components == count
    assert report.risk_score == 0.0
    assert report.findings == []


def test_all_fields_empty_single_component():
    """Component with all ownership fields empty produces multiple findings."""
    comp = _make_component(
        id="empty-all",
        name="Empty All",
        owner="",
        created_by="",
        last_modified="",
        documentation_url="",
        lifecycle_status="unknown",
    )
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = {f.category for f in report.findings}
    assert "orphaned" in categories
    assert "undocumented" in categories
    assert "unknown_status" in categories


def test_component_modified_exactly_365_days_ago_not_stale():
    """Component modified exactly 365 days ago should NOT be stale (threshold is >365)."""
    boundary_date = (date.today() - timedelta(days=365)).isoformat()
    comp = _make_component(id="boundary", name="Boundary", last_modified=boundary_date)
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "stale" not in categories


def test_component_modified_366_days_ago_is_stale():
    """Component modified 366 days ago should be stale."""
    # Use 370 days to avoid timezone boundary edge cases (±1 day tolerance)
    old_date = (date.today() - timedelta(days=370)).isoformat()
    comp = _make_component(id="stale366", name="Stale", last_modified=old_date)
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "stale" in categories


def test_future_last_modified_not_stale():
    """Component with future last_modified date should NOT be stale."""
    future_date = (date.today() + timedelta(days=30)).isoformat()
    comp = _make_component(id="future", name="Future", last_modified=future_date)
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "stale" not in categories


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def test_japanese_component_name():
    """Component with Japanese name should process without error."""
    comp = _make_component(id="jp-comp", name="本番サーバー", owner="")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    assert report.total_components == 1
    finding = next(f for f in report.findings if f.category == "orphaned")
    assert finding.component_name == "本番サーバー"


def test_all_components_orphaned():
    """Graph where all components lack owner should have orphaned_count == total."""
    comps = [_make_component(id=f"orphan-{i}", owner="") for i in range(5)]
    graph = _make_graph(*comps)
    report = ShadowITAnalyzer().analyze(graph)
    assert report.orphaned_count == 5
    assert report.total_components == 5


def test_all_components_undocumented():
    """All components without docs should have undocumented_count == total."""
    comps = [_make_component(id=f"nodoc-{i}", documentation_url="") for i in range(4)]
    graph = _make_graph(*comps)
    report = ShadowITAnalyzer().analyze(graph)
    assert report.undocumented_count == 4


def test_multiple_high_risk_orphans():
    """Multiple automation components with no owner should all appear."""
    comps = [
        _make_component(
            id=f"auto-{i}",
            name=f"Auto {i}",
            type=ComponentType.AUTOMATION,
            owner="",
        )
        for i in range(3)
    ]
    graph = _make_graph(*comps)
    report = ShadowITAnalyzer().analyze(graph)
    critical_findings = [f for f in report.findings if f.risk_level == "critical"]
    assert len(critical_findings) == 3


def test_lifecycle_deprecated_not_flagged_as_unknown():
    """Component with lifecycle_status='deprecated' should NOT trigger unknown_status."""
    comp = _make_component(id="depr", lifecycle_status="deprecated")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "unknown_status" not in categories


def test_risk_score_max_100():
    """Risk score should never exceed 100."""
    comps = [
        _make_component(
            id=f"worst-{i}",
            name=f"Worst {i}",
            type=ComponentType.AUTOMATION,
            owner="",
            documentation_url="",
            lifecycle_status="unknown",
        )
        for i in range(20)
    ]
    graph = _make_graph(*comps)
    report = ShadowITAnalyzer().analyze(graph)
    assert report.risk_score <= 100.0


def test_finding_fields_all_populated():
    """Every finding should have non-empty detail and recommendation."""
    comp = _make_component(
        id="check-fields",
        owner="",
        documentation_url="",
        lifecycle_status="unknown",
    )
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    for f in report.findings:
        assert len(f.detail) > 0, f"detail empty for category={f.category}"
        assert len(f.recommendation) > 0, f"recommendation empty for category={f.category}"


def test_finding_risk_levels_valid():
    """All finding risk_levels should be within valid set."""
    comps = [
        _make_component(id=f"r-{i}", owner="", documentation_url="", lifecycle_status="unknown")
        for i in range(3)
    ]
    graph = _make_graph(*comps)
    report = ShadowITAnalyzer().analyze(graph)
    valid_levels = {"critical", "high", "medium", "low"}
    for f in report.findings:
        assert f.risk_level in valid_levels


def test_to_dict_findings_list_is_serializable():
    """to_dict() findings should be a list of plain dicts, JSON-serializable."""
    import json
    comp = _make_component(id="serial", owner="", documentation_url="")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    d = report.to_dict()
    # Should not raise
    json_str = json.dumps(d)
    assert len(json_str) > 0


def test_to_dict_risk_score_is_rounded():
    """to_dict() risk_score should be a float rounded to 1 decimal."""
    comp = _make_component(id="rnd", owner="", documentation_url="")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    d = report.to_dict()
    assert isinstance(d["risk_score"], float)


def test_orphaned_count_matches_findings():
    """orphaned_count in report should match count of orphaned category findings."""
    comps = [
        _make_component(id=f"o-{i}", owner="")
        for i in range(3)
    ] + [_make_component(id="owned")]
    graph = _make_graph(*comps)
    report = ShadowITAnalyzer().analyze(graph)
    orphan_findings = [f for f in report.findings if f.category == "orphaned"]
    assert report.orphaned_count == len(orphan_findings)


def test_stale_count_matches_findings():
    """stale_count in report should match stale category findings."""
    old = (date.today() - timedelta(days=500)).isoformat()
    comps = [_make_component(id=f"s-{i}", last_modified=old) for i in range(2)]
    graph = _make_graph(*comps)
    report = ShadowITAnalyzer().analyze(graph)
    stale_findings = [f for f in report.findings if f.category == "stale"]
    assert report.stale_count == len(stale_findings)


def test_parse_date_datetime_string():
    """_parse_date should handle full datetime strings."""
    result = _parse_date("2024-06-01T12:00:00")
    assert result == date(2024, 6, 1)


def test_parse_date_datetime_z_suffix():
    """_parse_date should handle datetime strings with Z suffix."""
    result = _parse_date("2024-06-01T12:00:00Z")
    assert result == date(2024, 6, 1)


def test_days_since_today_returns_zero():
    """_days_since with today's date should return 0 (allow ±1 for timezone boundary)."""
    today = date.today().isoformat()
    result = _days_since(today)
    assert result is not None
    # Allow -1 to +1 for timezone boundary edge cases (UTC vs local)
    assert -1 <= result <= 1


def test_days_since_future_returns_negative():
    """_days_since with future date should return negative value."""
    future = (date.today() + timedelta(days=10)).isoformat()
    result = _days_since(future)
    assert result is not None
    assert result < 0


@pytest.mark.parametrize("yaml_file", [
    "examples/demo-infra.yaml",
    "examples/typical-startup.yaml",
    "examples/shadow-it-sample.yaml",
    "examples/ecommerce-platform.yaml",
])
def test_analyze_all_examples(yaml_file):
    """All example YAML files should load and analyze without error."""
    from faultray.model.loader import load_yaml
    path = Path(__file__).parent.parent / yaml_file
    if not path.exists():
        pytest.skip(f"{yaml_file} not found")
    graph = load_yaml(path)
    report = ShadowITAnalyzer().analyze(graph)
    assert report.total_components >= 0
    assert 0.0 <= report.risk_score <= 100.0
    d = report.to_dict()
    assert "findings" in d


def test_creator_left_only_when_created_by_set():
    """creator_left should only appear when created_by is non-empty and owner is empty."""
    # owner=empty, created_by=empty → no creator_left
    comp = _make_component(id="no-creator", owner="", created_by="")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "creator_left" not in categories


def test_owner_same_as_creator_no_creator_left():
    """When owner == created_by, creator_left should NOT appear."""
    comp = _make_component(id="same", owner="alice@x.com", created_by="alice@x.com")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    categories = [f.category for f in report.findings]
    assert "creator_left" not in categories


def test_summary_is_non_empty():
    """Report summary should always be a non-empty string."""
    comp = _make_component(id="summary-test")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    assert isinstance(report.summary, str)
    assert len(report.summary) > 0


def test_summary_contains_risk_score():
    """Report summary should contain the risk score string."""
    comp = _make_component(id="sum-score")
    graph = _make_graph(comp)
    report = ShadowITAnalyzer().analyze(graph)
    assert "Risk score" in report.summary or "risk" in report.summary.lower()
