"""Tests for IaCGenerator.dry_run() -- diff preview without file writes."""

from __future__ import annotations


from faultray.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.remediation.iac_generator import IaCGenerator


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
# Collision-safe sanitized identifiers
# ---------------------------------------------------------------------------


def test_escape_hcl_value_neutralizes_template_delimiters() -> None:
    from faultray.remediation.iac_generator import _escape_hcl_value

    # ${...} interpolation and %{...} directives must be made literal so a
    # crafted component name can't make terraform evaluate functions/vars.
    assert _escape_hcl_value('${file("/etc/passwd")}') == '$${file(\\"/etc/passwd\\")}'
    assert _escape_hcl_value("%{ for x in y }") == "%%{ for x in y }"
    # The escaped output contains no live template introducer.
    out = _escape_hcl_value("${var.secret}")
    assert "${" not in out.replace("$${", "")
    # Existing quote/newline escaping still applies.
    assert _escape_hcl_value('a"b') == 'a\\"b'


def test_terraform_generator_hcl_escape_neutralizes_template_delimiters() -> None:
    # The autopilot terraform generator's _hcl_escape feeds attacker-influenced
    # values (e.g. the app name from a requirements doc heading) into HCL
    # double-quoted literals, so it must neutralise ${ / %{ like its sibling.
    from faultray.autopilot.terraform_generator import _hcl_escape

    assert _hcl_escape('${file("/etc/passwd")}') == '$${file(\\"/etc/passwd\\")}'
    assert _hcl_escape("%{ for x in y }") == "%%{ for x in y }"
    out = _hcl_escape("${var.secret}")
    assert "${" not in out.replace("$${", "")
    assert _hcl_escape('a"b') == 'a\\"b'


def test_collision_safe_ids_disambiguates_and_is_stable() -> None:
    from faultray.remediation.iac_generator import _collision_safe_ids

    m = _collision_safe_ids(["api.prod", "api/prod", "db-1"])
    assert m["db-1"] == "db-1"                    # non-colliding keeps bare form
    assert m["api.prod"] != m["api/prod"]         # colliding ids disambiguated
    assert m["api.prod"].startswith("api_prod_")
    assert m["api/prod"].startswith("api_prod_")
    # Deterministic: same input set -> same mapping (stable across runs).
    assert _collision_safe_ids(["db-1", "api/prod", "api.prod"]) == m


def test_generate_no_duplicate_resource_addresses_on_id_collision() -> None:
    import re as _re

    from faultray.remediation.iac_generator import IaCGenerator

    # "db.1" and "db/1" both sanitize to "db_1"; without disambiguation both
    # databases would emit the SAME terraform resource address.
    g = _simple_graph([
        _make_component("db.1", ComponentType.DATABASE, replicas=1),
        _make_component("db/1", ComponentType.DATABASE, replicas=1),
    ])
    plan = IaCGenerator(g).generate()
    addr_re = _re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"')
    addresses = [
        f"{m.group(1)}.{m.group(2)}"
        for f in plan.files
        if f.path.endswith(".tf")
        for m in addr_re.finditer(f.content)
    ]
    assert addresses, "expected terraform resources to be generated"
    # No duplicate addresses that `terraform apply`/targeted rollback collide on.
    assert len(set(addresses)) == len(addresses), f"duplicate addresses: {sorted(addresses)}"


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
