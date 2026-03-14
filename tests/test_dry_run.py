"""Tests for IaCGenerator.dry_run() -- diff preview without file writes."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.remediation.iac_generator import IaCGenerator, RemediationPlan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    port: int = 8080,
    replicas: int = 1,
    autoscaling: AutoScalingConfig | None = None,
    failover: FailoverConfig | None = None,
    security: SecurityProfile | None = None,
    region: RegionConfig | None = None,
    **kwargs,
) -> Component:
    return Component(
        id=cid,
        name=cid.replace("_", " ").title(),
        type=ctype,
        port=port,
        replicas=replicas,
        autoscaling=autoscaling or AutoScalingConfig(),
        failover=failover or FailoverConfig(),
        security=security or SecurityProfile(),
        region=region or RegionConfig(),
        **kwargs,
    )


def _simple_graph(components: list[Component]) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_returns_string(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        preview = gen.dry_run(plan)
        assert isinstance(preview, str)
        assert len(preview) > 0

    def test_dry_run_shows_plus_prefixed_lines(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        preview = gen.dry_run(plan)
        lines = preview.splitlines()
        plus_lines = [l for l in lines if l.startswith("+ ")]
        assert len(plus_lines) > 0, "Dry run should show '+' prefixed lines for additions"

    def test_dry_run_shows_plan_summary(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        preview = gen.dry_run(plan)
        assert "to add" in preview
        assert "to change" in preview
        assert "to destroy" in preview

    def test_dry_run_shows_score_change(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        preview = gen.dry_run(plan)
        assert "Resilience score:" in preview

    def test_dry_run_shows_cost(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        preview = gen.dry_run(plan)
        assert "monthly cost" in preview.lower()

    def test_dry_run_empty_plan_returns_no_changes(self):
        # Well-configured component -> no remediations
        db = _make_component(
            "db", ComponentType.DATABASE, port=5432, replicas=3,
            security=SecurityProfile(
                encryption_at_rest=True, backup_enabled=True,
                waf_protected=True, network_segmented=True,
                encryption_in_transit=True,
            ),
            region=RegionConfig(dr_target_region="us-west-2"),
        )
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        preview = gen.dry_run(plan)
        assert "No changes" in preview

    def test_dry_run_includes_file_paths(self):
        db = _make_component("my_db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        preview = gen.dry_run(plan)
        for f in plan.files:
            assert f.path in preview, f"Dry run should mention file path: {f.path}"

    def test_dry_run_shows_phase_headers(self):
        # Create components triggering multiple phases
        db = _make_component(
            "db", ComponentType.DATABASE, port=5432, replicas=1,
            security=SecurityProfile(encryption_at_rest=False, backup_enabled=False),
        )
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate(target_score=100.0)

        preview = gen.dry_run(plan)
        assert "Phase 1" in preview
