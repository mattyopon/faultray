# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""DORA pre-audit resilience evidence pack (per critical service).

This module renders a *decision-support* evidence pack for ONE critical
service, built from sanitized model data and FaultRay simulation output. It is
the outcome the "DORA Resilience Evidence Sprint" delivers: a single,
audit-ready Markdown (and optionally print-ready HTML) document that maps
FaultRay findings to the relevant DORA articles.

It deliberately REUSES the existing reporter / compliance infrastructure
(:class:`~faultray.simulator.engine.SimulationEngine`,
:class:`~faultray.simulator.compliance_monitor.ComplianceMonitor`) rather than
introducing a parallel reporting stack. The static prose lives in the template
at ``docs/sales/dora-evidence-pack-template.md``; this code only fills it in.

Honest scope: this is decision-support tooling, NOT legal advice, NOT a DORA
certification, and NOT a replacement for threat-led penetration testing (TLPT)
or an auditor's sign-off.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from importlib.resources import files

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import SimulationReport

# Component types that represent ICT third-party / external dependencies for
# the purposes of DORA Article 28 (third-party risk) discussion.
_THIRD_PARTY_TYPES = frozenset(
    {
        ComponentType.EXTERNAL_API,
        ComponentType.LLM_ENDPOINT,
        ComponentType.DNS,
    }
)

# The canonical template is shipped as package data so it is available from an
# installed wheel (wheels package only ``src/faultray`` — the repo ``docs/``
# tree is NOT included). The copy under ``docs/sales/`` remains the human-facing
# sales document, but the CLI loads from here via importlib.resources.
_TEMPLATE_PACKAGE = "faultray.reporter.templates"
_TEMPLATE_NAME = "dora_evidence_pack_template.md"


def _md_cell(text: object) -> str:
    """Make a value safe to drop into a single Markdown table cell.

    Pipes break table layout and angle brackets enable HTML injection in
    Markdown renderers; neutralize both. Newlines are flattened to spaces.
    """
    s = str(text)
    return (
        s.replace("|", "\\|")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _find_service(graph: InfraGraph, service: str) -> Component | None:
    """Resolve *service* to a component by id (exact), then name (case-insensitive)."""
    comp = graph.get_component(service)
    if comp is not None:
        return comp
    lowered = service.strip().lower()
    for candidate in graph.components.values():
        if candidate.name.strip().lower() == lowered:
            return candidate
    # Last resort: unique substring match on name or id.
    matches = [
        c
        for c in graph.components.values()
        if lowered in c.name.lower() or lowered in c.id.lower()
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def load_template() -> str:
    """Return the evidence-pack template text shipped as package data.

    Uses :func:`importlib.resources.files` so it resolves correctly from an
    installed wheel regardless of the current working directory. Raises
    ``ValueError`` if the packaged template is missing.
    """
    resource = files(_TEMPLATE_PACKAGE) / _TEMPLATE_NAME
    try:
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise ValueError(
            f"Evidence-pack template not found as package data "
            f"({_TEMPLATE_PACKAGE}/{_TEMPLATE_NAME})."
        ) from exc


def _third_party_deps(graph: InfraGraph, component: Component) -> list[Component]:
    """ICT third parties relevant to *component* for Art. 28 / 30 evidence.

    Walks the selected service's TRANSITIVE dependency chain and returns every
    third-party-typed component reached (e.g. an ``external_api`` payment
    processor or external IdP), plus the selected component ITSELF when it is a
    third-party type. So ``--service api-gateway`` with
    ``api-gateway -> auth-adapter -> external-idp`` surfaces ``external-idp``,
    and a pack scoped to an external service never wrongly reports "no third
    parties".
    """
    found: list[Component] = []
    seen: set[str] = set()
    if component.type in _THIRD_PARTY_TYPES:
        found.append(component)
    seen.add(component.id)
    # Depth-first over transitive dependencies (successors).
    stack = [component.id]
    visited: set[str] = {component.id}
    while stack:
        cur = stack.pop()
        for dep in graph.get_dependencies(cur):
            if dep.id in visited:
                continue
            visited.add(dep.id)
            stack.append(dep.id)
            if dep.type in _THIRD_PARTY_TYPES and dep.id not in seen:
                found.append(dep)
                seen.add(dep.id)
    return found


def _service_neighborhood(graph: InfraGraph, component: Component) -> set[str]:
    """Component ids in the selected service's dependency neighborhood.

    The selected service, everything it transitively DEPENDS ON (its supply
    chain), and everything in its blast radius (transitive dependents). This is
    the set whose single-points-of-failure are materially relevant to the
    selected service; unrelated singletons elsewhere in the graph are excluded.
    """
    nbr: set[str] = {component.id}
    nbr |= graph.get_all_affected(component.id)  # dependents (blast radius)
    # Transitive dependencies (successors) reached via the dependency edges.
    stack = [component.id]
    while stack:
        cur = stack.pop()
        for dep in graph.get_dependencies(cur):
            if dep.id not in nbr:
                nbr.add(dep.id)
                stack.append(dep.id)
    return nbr


def _spof_components(
    graph: InfraGraph, neighborhood: set[str] | None = None
) -> list[Component]:
    """Single points of failure relevant to the selected service.

    REUSES the canonical detector (``FaultRayAnalyzer._detect_spofs``) so the
    pack is consistent-by-construction with the rest of the app: a SPOF is a
    single-replica component, with failover NOT enabled, that has at least one
    ``requires`` dependent (optional/async-only singletons are excluded).

    When *neighborhood* is given, the result is intersected with it so a
    per-service pack does not misattribute unrelated singletons elsewhere in the
    graph to the selected service.
    """
    from faultray.ai.analyzer import FaultRayAnalyzer

    recs = FaultRayAnalyzer()._detect_spofs(graph)
    spofs: list[Component] = []
    for rec in recs:
        cid = rec.component_id
        if neighborhood is not None and cid not in neighborhood:
            continue
        comp = graph.get_component(cid)
        if comp is not None:
            spofs.append(comp)
    return spofs


def _result_touches(result, cid: str) -> bool:
    """True when a scenario result's fault target or cascade touches *cid*.

    A :class:`~faultray.simulator.engine.ScenarioResult` carries no flat
    ``component_id``: the injected faults live on ``result.scenario.faults`` and
    the downstream impact on ``result.cascade.effects``. A result is relevant
    when *cid* is the faulted/target component OR appears among the cascade
    effects.
    """
    faults = getattr(result.scenario, "faults", None) or []
    if any(getattr(f, "target_component_id", None) == cid for f in faults):
        return True
    effects = getattr(result.cascade, "effects", None) or []
    return any(getattr(e, "component_id", None) == cid for e in effects)


def _service_scoped(results, component: Component) -> list:
    """Filter *results* to those whose fault/cascade touches *component*."""
    cid = component.id
    return [r for r in results if _result_touches(r, cid)]


def _service_critical_findings(report: SimulationReport, component: Component):
    """Critical findings whose fault target or cascade touches *component*."""
    return _service_scoped(report.critical_findings, component)


def build_evidence_pack_markdown(
    graph: InfraGraph,
    sim_report: SimulationReport,
    service: str,
    *,
    institution: str = "Your Organization",
    prepared_by: str = "FaultRay",
    engagement_id: str = "",
    rto_target: str = "TBD",
    rpo_target: str = "TBD",
) -> str:
    """Render the per-service DORA evidence pack as Markdown.

    Loads the static template and substitutes the per-engagement placeholder
    tokens with values derived from the model and the simulation report. Raises
    ``ValueError`` if *service* cannot be resolved or the template is missing.
    """
    component = _find_service(graph, service)
    if component is None:
        known = ", ".join(sorted(c.name or c.id for c in graph.components.values())[:20])
        raise ValueError(
            f"Service {service!r} not found in model. Known services: {known}"
        )

    template = load_template()

    blast_radius = graph.get_all_affected(component.id)
    third_parties = _third_party_deps(graph, component)
    # SPOFs are scoped to THIS service's dependency neighborhood so unrelated
    # singletons elsewhere in the graph are not attributed to the selected
    # service (the same neighborhood the service-scoped findings live in).
    neighborhood = _service_neighborhood(graph, component)
    spofs = _spof_components(graph, neighborhood)
    service_criticals = _service_critical_findings(sim_report, component)

    score = getattr(sim_report, "resilience_score", 0.0)
    engagement = engagement_id or f"FR-{datetime.now(timezone.utc):%Y%m%d}"

    substitutions = {
        "{SERVICE_NAME}": _md_cell(component.name or component.id),
        "{INSTITUTION_NAME}": _md_cell(institution),
        "{REPORT_DATE}": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "{PREPARED_BY}": _md_cell(prepared_by),
        "{ENGAGEMENT_ID}": _md_cell(engagement),
        "{RESILIENCE_SCORE}": f"{score:.1f}/100",
        # Per-service pack: the headline finding count must be SERVICE-SCOPED
        # (faults targeting or cascading to this service), not the global
        # simulation total, otherwise it attributes other services' findings to
        # the selected one.
        "{CRITICAL_FINDINGS_COUNT}": str(len(service_criticals)),
        "{SPOF_COUNT}": str(len(spofs)),
        "{RTO_TARGET}": _md_cell(rto_target),
        "{RPO_TARGET}": _md_cell(rpo_target),
    }

    rendered = template
    for token, value in substitutions.items():
        rendered = rendered.replace(token, value)

    # Append a machine-derived appendix from the actual model/simulation so the
    # pack is grounded in this engagement's data, not just the static template.
    rendered += _evidence_appendix(
        component=component,
        sim_report=sim_report,
        blast_radius=blast_radius,
        third_parties=third_parties,
        spofs=spofs,
        service_criticals=service_criticals,
    )
    return rendered


def _evidence_appendix(
    *,
    component: Component,
    sim_report: SimulationReport,
    blast_radius: set[str],
    third_parties: list[Component],
    spofs: list[Component],
    service_criticals: list,
) -> str:
    """Build the data-grounded appendix appended to the rendered template."""
    lines: list[str] = []
    lines.append("\n\n---\n")
    lines.append("## Appendix A — Engagement evidence (from this model & simulation)\n")
    lines.append(
        "_Derived automatically from the sanitized infrastructure model and "
        "FaultRay simulation output. No production access or PII was used._\n"
    )

    # Service profile
    lines.append("\n### A.1 Critical service profile\n")
    lines.append("| Attribute | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Service | {_md_cell(component.name or component.id)} |")
    lines.append(f"| Component type | {_md_cell(component.type.value)} |")
    lines.append(f"| Replicas | {_md_cell(component.replicas)} |")
    lines.append(f"| Failover configured | {_md_cell(bool(getattr(component.failover, 'enabled', False)))} |")
    lines.append(
        f"| Downstream blast radius (components) | {_md_cell(len(blast_radius))} |"
    )

    # Blast radius / dependency map (Art. 11 / testing)
    lines.append("\n### A.2 Blast-radius & dependency map\n")
    if blast_radius:
        lines.append(
            f"A failure of **{_md_cell(component.name or component.id)}** "
            f"propagates to {len(blast_radius)} downstream component(s):\n"
        )
        for cid in sorted(blast_radius)[:30]:
            lines.append(f"- {_md_cell(cid)}")
    else:
        lines.append(
            "No downstream dependents were identified for this service in the model."
        )

    # ICT third-party (Art. 28 / 30)
    lines.append("\n### A.3 ICT third-party & concentration (Art. 28 / 30)\n")
    if third_parties:
        lines.append("| Third-party dependency | Type |")
        lines.append("| --- | --- |")
        for tp in third_parties:
            lines.append(f"| {_md_cell(tp.name or tp.id)} | {_md_cell(tp.type.value)} |")
        lines.append(
            "\n_FaultRay surfaces these external dependencies to inform "
            "Article 28 third-party risk review and Article 30 contractual "
            "scoping. It does not assess legal contract text._"
        )
    else:
        lines.append(
            "No external/third-party dependencies were detected directly upstream "
            "of this service in the model."
        )

    # SPOF / concentration register
    lines.append("\n### A.4 Single-points-of-failure register\n")
    if spofs:
        lines.append("| Component | Type | Replicas |")
        lines.append("| --- | --- | --- |")
        for s in spofs[:30]:
            lines.append(
                f"| {_md_cell(s.name or s.id)} | {_md_cell(s.type.value)} | "
                f"{_md_cell(s.replicas)} |"
            )
    else:
        lines.append("No single-replica components with dependents were identified.")

    # Scenario testing results (Art. 24). The total scenarios run is a genuine
    # whole-programme figure; the finding counts are SERVICE-SCOPED so other
    # services' findings are not attributed to the selected service.
    service_warnings = _service_scoped(sim_report.warnings, component)
    lines.append("\n### A.5 Fault-injection scenario results (Art. 24)\n")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(
        f"| Scenarios tested (whole programme) | {_md_cell(len(sim_report.results))} |"
    )
    lines.append(
        f"| Critical findings touching this service | {_md_cell(len(service_criticals))} |"
    )
    lines.append(
        f"| Warnings touching this service | {_md_cell(len(service_warnings))} |"
    )
    if service_criticals:
        lines.append(
            f"\n**Critical findings touching this service: "
            f"{len(service_criticals)}.** See the full simulation report for "
            "scenario detail."
        )

    lines.append(
        "\n\n_This appendix is decision-support evidence, not legal advice or a "
        "DORA certification, and does not replace TLPT or auditor sign-off._\n"
    )
    return "\n".join(lines)


def evidence_pack_to_print_html(markdown_text: str, *, title: str) -> str:
    """Wrap the evidence-pack Markdown in a minimal print-ready HTML page.

    Mirrors the repository convention used by the other reporters: the output
    is meant to be opened in a browser and saved as PDF via Ctrl+P. The
    Markdown is rendered verbatim inside a styled ``<pre>`` block so no extra
    Markdown-parsing dependency is required.
    """
    safe_title = html.escape(title)
    safe_body = html.escape(markdown_text)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{safe_title}</title>"
        "<style>"
        "body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "max-width:880px;margin:2rem auto;padding:0 1.5rem;color:#1a1a1a;}"
        "pre{white-space:pre-wrap;word-wrap:break-word;font-family:inherit;"
        "font-size:0.95rem;line-height:1.5;}"
        "@media print{body{margin:0;}}"
        "</style></head><body><pre>"
        f"{safe_body}"
        "</pre></body></html>\n"
    )
