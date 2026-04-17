# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for AI Governance assessment and reporting.

Provides sub-commands under ``faultray governance`` for:
- Interactive 25-question self-assessment
- Auto-assessment from infrastructure graph
- Compliance reports per framework (METI v1.1, ISO 42001, AI推進法)
- Cross-framework mapping visualization
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.governance.assessor import GovernanceAssessor
    from faultray.governance.models import AssessmentResult

import typer

from faultray.cli.main import app, console

governance_app = typer.Typer(
    name="governance",
    help="AI Governance assessment (METI v1.1 / ISO 42001 / AI推進法)",
    no_args_is_help=True,
)
app.add_typer(governance_app)


@governance_app.command("assess")
def governance_assess(
    auto: bool = typer.Option(
        False, "--auto",
        help="Auto-assess from infrastructure graph instead of interactive questionnaire.",
    ),
    yaml_file: Path = typer.Option(
        None, "--yaml", "-y",
        help="Path to infrastructure YAML model (for --auto mode).",
    ),
    model: Path = typer.Option(
        None, "--model", "-m",
        help="Path to infrastructure JSON model (for --auto mode).",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Run AI governance maturity assessment.

    Interactive mode (default): answer 25 questions about your AI governance posture.
    Auto mode (--auto): derive governance signals from infrastructure graph.

    Examples:
        faultray governance assess
        faultray governance assess --auto --yaml infra.yaml
    """
    from faultray.governance.assessor import GovernanceAssessor
    from faultray.governance.reporter import GovernanceReporter

    assessor = GovernanceAssessor()

    if auto:
        result = _auto_assess(assessor, yaml_file, model, quiet=json_output)
    else:
        result = _interactive_assess(assessor)

    reporter = GovernanceReporter(result)

    if json_output:
        console.print_json(reporter.to_json())
    else:
        reporter.print_rich()


@governance_app.command("report")
def governance_report(
    framework: str = typer.Option(
        None, "--framework", "-f",
        help="Framework: meti-v1.1, iso42001, ai-promotion. Omit for all.",
    ),
    all_frameworks: bool = typer.Option(
        False, "--all",
        help="Show all 3 frameworks.",
    ),
    output: Path = typer.Option(
        None, "--output", "-o",
        help="Output file path (JSON or PDF based on extension).",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Generate AI governance compliance report.

    Examples:
        faultray governance report --framework meti-v1.1
        faultray governance report --framework iso42001
        faultray governance report --framework ai-promotion
        faultray governance report --all
        faultray governance report --all --output report.json
        faultray governance report --all --output report.pdf
    """
    from faultray.governance.frameworks import GovernanceFramework
    from faultray.governance.reporter import GovernanceReporter

    reporter = GovernanceReporter()

    fw = None
    if framework and not all_frameworks:
        try:
            fw = GovernanceFramework(framework)
        except ValueError:
            console.print(
                f"[red]Unknown framework: '{framework}'[/]\n"
                "[dim]Valid: meti-v1.1, iso42001, ai-promotion[/]"
            )
            raise typer.Exit(1)

    if output is not None:
        ext = output.suffix.lower()
        if ext == ".pdf":
            ok = reporter.to_pdf(output)
            if ok:
                console.print(f"[green]PDF report written to {output}[/]")
            else:
                console.print("[yellow]fpdf2 not installed — install with: pip install fpdf2[/]")
        else:
            reporter.to_json(output)
            console.print(f"[green]JSON report written to {output}[/]")
    elif json_output:
        console.print_json(reporter.to_json())
    else:
        reporter.print_rich(framework=fw)


@governance_app.command("cross-map")
def governance_cross_map(
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Show cross-mapping between METI, ISO 42001, and AI推進法 frameworks.

    Example:
        faultray governance cross-map
    """
    from faultray.governance.frameworks import get_coverage_matrix
    from faultray.governance.reporter import GovernanceReporter

    if json_output:
        import json as json_mod

        matrix = get_coverage_matrix()
        console.print_json(json_mod.dumps(matrix, ensure_ascii=False, indent=2))
    else:
        reporter = GovernanceReporter()
        reporter.print_cross_mapping()


# ---------------------------------------------------------------------------
# Sub-Typers for nested commands
# ---------------------------------------------------------------------------

ai_registry_app = typer.Typer(
    name="ai-registry",
    help="AI System Registry management.",
    no_args_is_help=True,
)
governance_app.add_typer(ai_registry_app)

evidence_app = typer.Typer(
    name="evidence",
    help="Evidence management with audit trail.",
    no_args_is_help=True,
)
governance_app.add_typer(evidence_app)

policy_app = typer.Typer(
    name="policy",
    help="AI governance policy generation.",
    no_args_is_help=True,
)
governance_app.add_typer(policy_app)


# ---------------------------------------------------------------------------
# Gap Analysis
# ---------------------------------------------------------------------------


@governance_app.command("gap-analysis")
def governance_gap_analysis(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Run gap analysis on latest assessment.

    Runs auto-assessment first, then performs multi-framework gap analysis
    with improvement roadmap.

    Example:
        faultray governance gap-analysis
    """
    import json as json_mod

    from faultray.governance.assessor import GovernanceAssessor
    from faultray.governance.gap_analyzer import analyze_gaps

    assessor = GovernanceAssessor()
    result = assessor.assess_auto()
    gap_report = analyze_gaps(result)

    if json_output:
        from dataclasses import asdict
        console.print_json(json_mod.dumps(asdict(gap_report), ensure_ascii=False, indent=2))
    else:
        console.print("\n[bold cyan]Gap Analysis Report[/]")
        console.print(f"Total requirements: {gap_report.total_requirements}")
        console.print(f"[green]Compliant: {gap_report.compliant}[/]")
        console.print(f"[yellow]Partial: {gap_report.partial}[/]")
        console.print(f"[red]Non-compliant: {gap_report.non_compliant}[/]")

        if gap_report.multi_framework_impact.get("summary"):
            s = gap_report.multi_framework_impact["summary"]
            console.print("\n[bold]Multi-framework impact:[/]")
            console.print(f"  ISO 42001 requirements impacted: {s.get('iso_requirements_impacted', 0)}")
            console.print(f"  AI推進法 requirements impacted: {s.get('act_requirements_impacted', 0)}")

        # Show roadmap summary
        rm = gap_report.roadmap
        if rm.phase1:
            console.print(f"\n[bold red]Phase 1 (1-3ヶ月): {len(rm.phase1)} items[/]")
        if rm.phase2:
            console.print(f"[bold yellow]Phase 2 (3-6ヶ月): {len(rm.phase2)} items[/]")
        if rm.phase3:
            console.print(f"[bold green]Phase 3 (6-12ヶ月): {len(rm.phase3)} items[/]")


@governance_app.command("roadmap")
def governance_roadmap(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show improvement roadmap based on gap analysis.

    Example:
        faultray governance roadmap
    """
    import json as json_mod

    from faultray.governance.assessor import GovernanceAssessor
    from faultray.governance.gap_analyzer import analyze_gaps

    assessor = GovernanceAssessor()
    result = assessor.assess_auto()
    gap_report = analyze_gaps(result)
    rm = gap_report.roadmap

    if json_output:
        from dataclasses import asdict
        console.print_json(json_mod.dumps(asdict(rm), ensure_ascii=False, indent=2))
    else:
        console.print("\n[bold cyan]Improvement Roadmap[/]\n")
        for phase_label, items in [
            ("Phase 1 (1-3ヶ月): 安全性・セキュリティ・プライバシー", rm.phase1),
            ("Phase 2 (3-6ヶ月): ガバナンス体制・アカウンタビリティ", rm.phase2),
            ("Phase 3 (6-12ヶ月): 全要件充足と継続的改善", rm.phase3),
        ]:
            if items:
                console.print(f"[bold]{phase_label}[/]")
                for item in items:
                    console.print(f"  [{item.req_id}] {item.title}")
                    for a in item.actions:
                        console.print(f"    - {a}")
                console.print()


# ---------------------------------------------------------------------------
# AI Registry commands
# ---------------------------------------------------------------------------


@ai_registry_app.command("list")
def ai_registry_list(
    org_id: str = typer.Option("default", "--org", help="Organization ID."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List registered AI systems.

    Example:
        faultray governance ai-registry list --org myorg
    """
    import json as json_mod
    from dataclasses import asdict

    from faultray.governance.ai_registry import list_ai_systems

    systems = list_ai_systems(org_id)

    if json_output:
        console.print_json(json_mod.dumps([asdict(s) for s in systems], indent=2))
    else:
        if not systems:
            console.print("[dim]No AI systems registered.[/]")
            return
        for s in systems:
            risk_color = {"high": "red", "unacceptable": "red", "limited": "yellow"}.get(s.risk_level, "green")
            console.print(f"  [{risk_color}]{s.risk_level:12s}[/] {s.name} ({s.ai_type}) - {s.department}")


@ai_registry_app.command("add")
def ai_registry_add(
    name: str = typer.Option(..., "--name", help="AI system name."),
    org_id: str = typer.Option("default", "--org", help="Organization ID."),
    department: str = typer.Option("", "--dept", help="Department."),
    ai_type: str = typer.Option("other", "--type", help="AI type: generative/predictive/classification/recommendation/other."),
    vendor: str = typer.Option("", "--vendor", help="Vendor name."),
    model_name: str = typer.Option("", "--model-name", help="Model name (e.g. GPT-4)."),
    purpose: str = typer.Option("", "--purpose", help="Purpose description."),
    risk_level: str = typer.Option("minimal", "--risk", help="Risk level: unacceptable/high/limited/minimal."),
) -> None:
    """Register a new AI system.

    Example:
        faultray governance ai-registry add --name "Customer Chatbot" --type generative --vendor OpenAI
    """
    from faultray.governance.ai_registry import AISystem, register_ai_system

    system = AISystem(
        name=name,
        org_id=org_id,
        department=department,
        ai_type=ai_type,
        vendor=vendor,
        model_name=model_name,
        purpose=purpose,
        risk_level=risk_level,
    )
    sys_id = register_ai_system(system)
    console.print(f"[green]Registered AI system: {name} (ID: {sys_id})[/]")
    console.print(f"  Risk level: {system.risk_level}")


# ---------------------------------------------------------------------------
# Evidence commands
# ---------------------------------------------------------------------------


@evidence_app.command("list")
def evidence_list(
    req_id: str = typer.Option(None, "--req", help="Filter by requirement ID."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List evidence records.

    Example:
        faultray governance evidence list
        faultray governance evidence list --req C01-R01
    """
    import json as json_mod
    from dataclasses import asdict

    from faultray.governance.evidence_manager import list_evidence

    records = list_evidence(req_id)

    if json_output:
        console.print_json(json_mod.dumps([asdict(r) for r in records], indent=2))
    else:
        if not records:
            console.print("[dim]No evidence records found.[/]")
            return
        for r in records:
            console.print(f"  [{r.requirement_id}] {r.description} ({r.file_path})")


@evidence_app.command("add")
def evidence_add(
    req_id: str = typer.Option(..., "--req", help="Requirement ID (e.g. C01-R01)."),
    description: str = typer.Option(..., "--desc", help="Evidence description."),
    file_path: str = typer.Option(..., "--file", help="Path to evidence file."),
    registered_by: str = typer.Option("", "--by", help="Who is registering."),
) -> None:
    """Register an evidence file.

    Example:
        faultray governance evidence add --req C01-R01 --desc "AI policy doc" --file policy.pdf
    """
    from faultray.governance.evidence_manager import register_evidence

    record = register_evidence(req_id, description, file_path, registered_by)
    console.print(f"[green]Evidence registered: {record.id} for {req_id}[/]")
    if record.file_hash:
        console.print(f"  SHA-256: {record.file_hash[:16]}...")


@evidence_app.command("verify")
def evidence_verify() -> None:
    """Verify the audit hash chain integrity.

    Example:
        faultray governance evidence verify
    """
    from faultray.governance.evidence_manager import verify_chain

    is_valid = verify_chain()
    if is_valid:
        console.print("[green]Audit hash chain: VALID[/]")
    else:
        console.print("[red]Audit hash chain: TAMPERED — integrity violation detected![/]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Policy commands
# ---------------------------------------------------------------------------


@policy_app.command("generate")
def policy_generate(
    policy_type: str = typer.Option(..., "--type", help="Policy type: ai_usage/risk_management/ethics/data_management/incident_response."),
    org_name: str = typer.Option("株式会社サンプル", "--org-name", help="Organization name."),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path."),
) -> None:
    """Generate a single policy document.

    Example:
        faultray governance policy generate --type ai_usage --org-name "株式会社ABC"
    """
    from faultray.governance.policy_generator import generate_policy

    try:
        doc = generate_policy(policy_type, org_name)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    if output:
        output.write_text(doc.content, encoding="utf-8")
        console.print(f"[green]Policy written to {output}[/]")
    else:
        console.print(doc.content)


@policy_app.command("generate-all")
def policy_generate_all(
    org_name: str = typer.Option("株式会社サンプル", "--org-name", help="Organization name."),
    output_dir: Path = typer.Option(None, "--output-dir", "-d", help="Output directory."),
) -> None:
    """Generate all 5 policy documents.

    Example:
        faultray governance policy generate-all --org-name "株式会社ABC" -d ./policies/
    """
    from faultray.governance.policy_generator import generate_all_policies

    docs = generate_all_policies(org_name)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        for doc in docs:
            fp = output_dir / f"{doc.policy_type}.md"
            fp.write_text(doc.content, encoding="utf-8")
            console.print(f"[green]  {fp}[/]")
        console.print(f"\n[green]Generated {len(docs)} policy documents.[/]")
    else:
        for doc in docs:
            console.print(f"\n{'=' * 60}")
            console.print(doc.content)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _interactive_assess(assessor: "GovernanceAssessor") -> "AssessmentResult":
    """Run interactive 25-question assessment."""
    from faultray.governance.frameworks import METI_QUESTIONS

    console.print("\n[bold cyan]AI Governance Self-Assessment (25 Questions)[/]")
    console.print("[dim]Each question has 5 options (0-4). Select the number that best matches.[/]\n")

    answers: dict[str, int] = {}

    for i, q in enumerate(METI_QUESTIONS, 1):
        console.print(f"[bold]Q{i}. {q.text}[/]")
        for j, opt in enumerate(q.options):
            console.print(f"  [{j}] {opt}")

        while True:
            try:
                raw = typer.prompt(f"  Select (0-{len(q.options) - 1})", default="0")
                idx = int(raw)
                if 0 <= idx < len(q.options):
                    answers[q.question_id] = idx
                    break
                console.print(f"[red]  Please enter 0-{len(q.options) - 1}[/]")
            except (ValueError, KeyError):
                console.print(f"[red]  Please enter 0-{len(q.options) - 1}[/]")
        console.print()

    return assessor.assess(answers)


def _auto_assess(
    assessor: "GovernanceAssessor",
    yaml_file: Path | None,
    model: Path | None,
    quiet: bool = False,
) -> "AssessmentResult":
    """Auto-assess governance from infrastructure model."""
    from faultray.cli.main import _load_graph_for_analysis, DEFAULT_MODEL_PATH

    model_path = model or DEFAULT_MODEL_PATH
    graph = _load_graph_for_analysis(model_path, yaml_file)

    # Derive signals from graph
    has_monitoring = any(
        kw in (c.id + " " + c.name).lower()
        for c in graph.components.values()
        for kw in ("otel", "monitoring", "prometheus", "grafana", "datadog")
    )
    has_auth = any(
        kw in (c.id + " " + c.name).lower()
        for c in graph.components.values()
        for kw in ("auth", "waf", "firewall", "gateway", "oauth", "iam")
    )
    has_encryption = any(c.port == 443 for c in graph.components.values())
    has_dr = any(
        getattr(c, "region", None) is not None
        and (getattr(getattr(c, "region", None), "dr_target_region", None) or not getattr(getattr(c, "region", None), "is_primary", True))
        for c in graph.components.values()
    )
    has_logging = any(c.security.log_enabled for c in graph.components.values())

    if not quiet:
        console.print("[dim]Auto-assessing governance from infrastructure graph...[/]")

    return assessor.assess_auto(
        has_monitoring=has_monitoring,
        has_auth=has_auth,
        has_encryption=has_encryption,
        has_dr=has_dr,
        has_logging=has_logging,
    )
