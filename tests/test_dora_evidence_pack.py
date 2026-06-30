"""Tests for the per-service DORA evidence pack renderer."""

from __future__ import annotations

import pytest

from faultray.model.components import (
    Component,
    ComponentType,
    FailoverConfig,
    HealthStatus,
)
from faultray.model.demo import create_demo_graph
from faultray.model.graph import Dependency, InfraGraph
from faultray.reporter.dora_evidence_pack import (
    _service_critical_findings,
    _service_neighborhood,
    _spof_components,
    _third_party_deps,
    build_evidence_pack_markdown,
    evidence_pack_to_print_html,
    load_template,
)
from faultray.simulator.cascade import CascadeChain, CascadeEffect
from faultray.simulator.engine import ScenarioResult, SimulationEngine, SimulationReport
from faultray.simulator.scenarios import Fault, FaultType, Scenario


def _build(service: str = "postgres", **kwargs) -> str:
    graph = create_demo_graph()
    report = SimulationEngine(graph).run_all_defaults()
    return build_evidence_pack_markdown(graph, report, service, **kwargs)


def test_evidence_pack_substitutes_all_tokens() -> None:
    markdown = _build(
        "postgres",
        institution="Acme Bank EU",
        rto_target="2h",
        rpo_target="15m",
    )
    # No unsubstituted placeholder tokens should remain.
    import re

    leftover = re.findall(r"\{[A-Z_]+\}", markdown)
    assert leftover == [], f"unsubstituted tokens: {leftover}"
    assert "Acme Bank EU" in markdown
    assert "2h" in markdown
    assert "15m" in markdown


def test_evidence_pack_covers_all_required_articles() -> None:
    markdown = _build("postgres")
    for article in ("Article 11", "Article 12", "Article 24", "Article 25", "Article 28", "Article 30"):
        assert article in markdown, f"missing {article}"
    # Honesty / scope language must be present.
    assert "not legal advice" in markdown.lower()
    assert "TLPT" in markdown


def test_evidence_pack_includes_grounded_appendix() -> None:
    markdown = _build("postgres")
    assert "Appendix A" in markdown
    assert "Blast-radius" in markdown
    assert "Fault-injection scenario results" in markdown


def test_evidence_pack_resolves_service_by_name() -> None:
    # Demo component "postgres" has name "PostgreSQL".
    graph = create_demo_graph()
    report = SimulationEngine(graph).run_all_defaults()
    by_name = build_evidence_pack_markdown(graph, report, "PostgreSQL")
    assert "DORA Pre-Audit Resilience Evidence Pack" in by_name


def test_evidence_pack_unknown_service_raises() -> None:
    graph = create_demo_graph()
    report = SimulationEngine(graph).run_all_defaults()
    with pytest.raises(ValueError, match="not found"):
        build_evidence_pack_markdown(graph, report, "does-not-exist-xyz")


def test_print_html_wraps_markdown_safely() -> None:
    html = evidence_pack_to_print_html("# Title\n<script>alert(1)</script>", title="T <x>")
    assert "<!DOCTYPE html>" in html
    # Raw markdown angle brackets must be escaped, not live HTML.
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_template_ships_as_package_data() -> None:
    """The template must load via importlib.resources (as from an installed wheel).

    load_template() reads ``faultray.reporter.templates`` package data and does
    NOT depend on the repo ``docs/`` tree or the current working directory, so
    this regression cannot be masked by a source-tree-only path.
    """
    text = load_template()
    assert text.lstrip().startswith("# DORA Pre-Audit Resilience Evidence Pack")
    # Placeholder tokens the renderer substitutes must be present in the shipped
    # template (proves we packaged the canonical version, not a stale stub).
    for token in ("{SERVICE_NAME}", "{RESILIENCE_SCORE}", "{SPOF_COUNT}"):
        assert token in text


def test_appendix_includes_findings_on_selected_service() -> None:
    """A critical finding on the chosen service is surfaced in Appendix A.5.

    Guards the ScenarioResult field-path fix: findings are matched via
    ``scenario.faults[*].target_component_id`` and ``cascade.effects[*].component_id``,
    not non-existent flat attributes.
    """
    graph = create_demo_graph()
    report = SimulationEngine(graph).run_all_defaults()
    comp = graph.get_component("postgres")
    matched = _service_critical_findings(report, comp)
    assert matched, "expected demo postgres to have critical findings touching it"
    markdown = build_evidence_pack_markdown(graph, report, "postgres")
    assert "Critical findings touching this service" in markdown
    assert f"touching this service: {len(matched)}." in markdown


def _critical_targeting(name: str, target_id: str) -> ScenarioResult:
    """Build a synthetic CRITICAL ScenarioResult whose fault targets *target_id*."""
    chain = CascadeChain(trigger=target_id, total_components=1)
    chain.effects.append(CascadeEffect(
        component_id=target_id,
        component_name=target_id,
        health=HealthStatus.DOWN,
        reason="down",
    ))
    fault = Fault(target_component_id=target_id, fault_type=FaultType.COMPONENT_DOWN)
    scenario = Scenario(id=f"s-{name}", name=name, description=name, faults=[fault])
    # risk_score >= 7.0 => is_critical
    return ScenarioResult(scenario=scenario, cascade=chain, risk_score=9.0)


def test_exec_summary_count_is_service_scoped_not_global() -> None:
    """The headline CRITICAL_FINDINGS_COUNT must reflect ONLY findings touching
    the selected service, not the global simulation total."""
    graph = InfraGraph()
    graph.add_component(Component(id="svc-target", name="Target", type=ComponentType.APP_SERVER))
    graph.add_component(Component(id="svc-other", name="Other", type=ComponentType.APP_SERVER))

    # 2 criticals on the target, 3 on an unrelated service => global 5, scoped 2.
    results = (
        [_critical_targeting(f"t{i}", "svc-target") for i in range(2)]
        + [_critical_targeting(f"o{i}", "svc-other") for i in range(3)]
    )
    report = SimulationReport(results=results, resilience_score=50.0)

    scoped = len(_service_critical_findings(report, graph.get_component("svc-target")))
    assert scoped == 2
    assert len(report.critical_findings) == 5  # global is strictly larger

    markdown = build_evidence_pack_markdown(graph, report, "svc-target")
    # The exec-summary metrics table row carries the service-scoped count, not 5.
    assert "| Critical Findings Count | 2 |" in markdown
    assert "| Critical Findings Count | 5 |" not in markdown


def test_spof_register_excludes_failover_enabled_single_replica() -> None:
    """A replicas==1 component with failover.enabled is NOT a SPOF (managed
    Multi-AZ datastore); a replicas==1 component without failover IS."""
    g = InfraGraph()
    g.add_component(Component(
        id="ha-db", name="HA DB", type=ComponentType.DATABASE,
        replicas=1, failover=FailoverConfig(enabled=True),
    ))
    g.add_component(Component(
        id="solo-db", name="Solo DB", type=ComponentType.DATABASE, replicas=1,
    ))
    g.add_component(Component(id="app", name="App", type=ComponentType.APP_SERVER, replicas=2))
    g.add_dependency(Dependency(source_id="app", target_id="ha-db", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="solo-db", dependency_type="requires"))

    spof_ids = {c.id for c in _spof_components(g)}
    assert "ha-db" not in spof_ids, "failover-enabled single-replica must not be a SPOF"
    assert "solo-db" in spof_ids, "single-replica without failover must be a SPOF"


def test_report_dora_pdf_with_html_output_keeps_both_files(tmp_path) -> None:
    """`report dora --output x.html --pdf` must not overwrite the Markdown pack
    with the print-ready HTML: the companion HTML goes to a distinct path."""
    from typer.testing import CliRunner

    from faultray.cli import app

    model = tmp_path / "model.yaml"
    model.write_text(
        "components:\n"
        "  - id: svc\n"
        "    name: Svc\n"
        "    type: app_server\n"
        "  - id: db\n"
        "    name: DB\n"
        "    type: database\n"
        "dependencies:\n"
        "  - source: svc\n"
        "    target: db\n"
        "    type: requires\n",
        encoding="utf-8",
    )
    out = tmp_path / "pack.html"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["report", "dora", str(model), "--service", "svc", "--output", str(out), "--pdf"],
    )
    assert result.exit_code == 0, result.output

    companion = tmp_path / "pack.print.html"
    assert out.exists(), "the Markdown pack (--output path) must survive"
    assert companion.exists(), "the print-ready HTML companion must be written"
    md_text = out.read_text(encoding="utf-8")
    html_text = companion.read_text(encoding="utf-8")
    assert md_text != html_text
    # The --output file is the raw Markdown pack; the companion is wrapped HTML.
    assert md_text.lstrip().startswith("# DORA Pre-Audit Resilience Evidence Pack")
    assert "<!DOCTYPE html>" in html_text


def _payment_graph() -> InfraGraph:
    """A small payment topology: an external_api processor + a neighbor singleton
    DB, plus an unrelated singleton DB in a separate branch."""
    g = InfraGraph()
    g.add_component(Component(id="payment", name="Payment", type=ComponentType.APP_SERVER, replicas=2))
    g.add_component(Component(id="processor", name="Card Processor", type=ComponentType.EXTERNAL_API, replicas=1))
    g.add_component(Component(id="ledger-db", name="Ledger DB", type=ComponentType.DATABASE, replicas=1))
    g.add_component(Component(id="other-app", name="Other", type=ComponentType.APP_SERVER, replicas=2))
    g.add_component(Component(id="unrelated-db", name="Unrelated DB", type=ComponentType.DATABASE, replicas=1))
    g.add_dependency(Dependency(source_id="payment", target_id="processor", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="payment", target_id="ledger-db", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="other-app", target_id="unrelated-db", dependency_type="requires"))
    return g


def test_selected_external_api_service_listed_as_third_party() -> None:
    """When the SELECTED service is itself a third-party type (external_api), it
    must appear in the Art.28/30 third-party list (FIX B)."""
    g = _payment_graph()
    proc = g.get_component("processor")
    ids = {c.id for c in _third_party_deps(g, proc)}
    assert "processor" in ids, "selected external_api must be in the third-party list"

    report = SimulationEngine(g).run_all_defaults()
    markdown = build_evidence_pack_markdown(g, report, "processor")
    # A.3 must NOT claim there are no third-party dependencies.
    assert "Card Processor" in markdown
    assert "No external/third-party dependencies were detected" not in markdown


def test_spof_register_scoped_to_service_neighborhood() -> None:
    """SPOFs in the pack are scoped to the selected service's neighborhood; an
    unrelated singleton in a separate branch is excluded (FIX C)."""
    g = _payment_graph()
    payment = g.get_component("payment")
    nbr = _service_neighborhood(g, payment)
    assert "unrelated-db" not in nbr

    scoped = {c.id for c in _spof_components(g, nbr)}
    assert "ledger-db" in scoped, "in-neighborhood singleton must be a SPOF"
    assert "unrelated-db" not in scoped, "unrelated singleton must NOT be attributed"

    report = SimulationEngine(g).run_all_defaults()
    markdown = build_evidence_pack_markdown(g, report, "payment")
    assert "Unrelated DB" not in markdown


def test_third_party_walked_transitively() -> None:
    """A third party reached via a TRANSITIVE dependency chain
    (api-gateway -> auth-adapter -> external-idp) must be surfaced for the
    selected api-gateway service (round-4 item 1)."""
    g = InfraGraph()
    g.add_component(Component(id="api-gateway", name="Gateway", type=ComponentType.LOAD_BALANCER, replicas=2))
    g.add_component(Component(id="auth-adapter", name="Auth Adapter", type=ComponentType.APP_SERVER, replicas=2))
    g.add_component(Component(id="external-idp", name="External IdP", type=ComponentType.EXTERNAL_API, replicas=1))
    g.add_dependency(Dependency(source_id="api-gateway", target_id="auth-adapter", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="auth-adapter", target_id="external-idp", dependency_type="requires"))

    gw = g.get_component("api-gateway")
    ids = {c.id for c in _third_party_deps(g, gw)}
    assert "external-idp" in ids, "transitive external_api must be surfaced"

    report = SimulationEngine(g).run_all_defaults()
    md = build_evidence_pack_markdown(g, report, "api-gateway")
    assert "External IdP" in md
    assert "No external/third-party dependencies were detected" not in md


def test_optional_only_singleton_not_a_spof() -> None:
    """A single-replica component reached only via an optional/async edge is NOT
    a SPOF (round-4 item 2), reusing the canonical analyzer predicate."""
    g = InfraGraph()
    g.add_component(Component(id="app", name="App", type=ComponentType.APP_SERVER, replicas=2))
    g.add_component(Component(id="req-db", name="Req DB", type=ComponentType.DATABASE, replicas=1))
    g.add_component(Component(id="opt-cache", name="Opt Cache", type=ComponentType.CACHE, replicas=1))
    g.add_dependency(Dependency(source_id="app", target_id="req-db", dependency_type="requires"))
    g.add_dependency(Dependency(source_id="app", target_id="opt-cache", dependency_type="optional"))

    spof_ids = {c.id for c in _spof_components(g)}
    assert "req-db" in spof_ids, "requires-singleton must be a SPOF"
    assert "opt-cache" not in spof_ids, "optional-only singleton must NOT be a SPOF"


def test_appendix_a5_counts_are_service_scoped() -> None:
    """A.5 critical/warning counts must be service-scoped, not global
    (round-4 item 3)."""
    from faultray.reporter.dora_evidence_pack import _result_touches
    from faultray.simulator.cascade import CascadeChain, CascadeEffect
    from faultray.simulator.engine import ScenarioResult, SimulationReport
    from faultray.simulator.scenarios import Fault, FaultType, Scenario

    g = InfraGraph()
    g.add_component(Component(id="svc-target", name="Target", type=ComponentType.APP_SERVER))
    g.add_component(Component(id="svc-other", name="Other", type=ComponentType.APP_SERVER))

    def crit(name, target):
        chain = CascadeChain(trigger=target, total_components=1)
        chain.effects.append(CascadeEffect(component_id=target, component_name=target,
                                           health=HealthStatus.DOWN, reason="down"))
        fault = Fault(target_component_id=target, fault_type=FaultType.COMPONENT_DOWN)
        scen = Scenario(id=f"s-{name}", name=name, description=name, faults=[fault])
        return ScenarioResult(scenario=scen, cascade=chain, risk_score=9.0)

    results = [crit("t0", "svc-target")] + [crit(f"o{i}", "svc-other") for i in range(4)]
    report = SimulationReport(results=results, resilience_score=50.0)
    assert len(report.critical_findings) == 5
    assert sum(_result_touches(r, "svc-target") for r in report.critical_findings) == 1

    md = build_evidence_pack_markdown(g, report, "svc-target")
    # A.5 row reports the SERVICE-SCOPED count (1), not the global 5.
    assert "| Critical findings touching this service | 1 |" in md
    assert "| Critical findings touching this service | 5 |" not in md
