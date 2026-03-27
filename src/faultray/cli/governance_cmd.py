# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI commands for AI Governance assessment and reporting.

Provides sub-commands under ``faultray governance`` for:
- Interactive 25-question self-assessment
- Auto-assessment from infrastructure graph
- Compliance reports per framework (METI v1.1, ISO 42001, AI推進法)
- Cross-framework mapping visualization
"""

from __future__ import annotations

from pathlib import Path

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
        result = _auto_assess(assessor, yaml_file, model)
    else:
        result = _interactive_assess(assessor)

    reporter = GovernanceReporter(result)

    if json_output:
        console.print(reporter.to_json())
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
        console.print(reporter.to_json())
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
        console.print(json_mod.dumps(matrix, ensure_ascii=False, indent=2))
    else:
        reporter = GovernanceReporter()
        reporter.print_cross_mapping()


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

    console.print("[dim]Auto-assessing governance from infrastructure graph...[/]")

    return assessor.assess_auto(
        has_monitoring=has_monitoring,
        has_auth=has_auth,
        has_encryption=has_encryption,
        has_dr=has_dr,
        has_logging=has_logging,
    )
