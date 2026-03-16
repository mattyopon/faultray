"""CLI commands for Scenario Templates Library and Template Gallery."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

template_app = typer.Typer(
    name="template",
    help="Manage pre-built infrastructure scenario templates and gallery.",
    no_args_is_help=True,
)
app.add_typer(template_app, name="template")


@template_app.command("list")
def template_list(
    category: str = typer.Option(
        None, "--category", "-c",
        help="Filter by category (e.g. microservices, web_application, data_pipeline).",
    ),
) -> None:
    """List all available templates including gallery templates.

    Example:
        faultray template list
        faultray template list --category microservices
    """
    from faultray.templates.gallery import TemplateGallery

    gallery = TemplateGallery()
    templates = gallery.list_templates(category=category)

    if not templates:
        console.print("[yellow]No templates found.[/]")
        if category:
            console.print(f"[dim]Try without --category filter, or check category name: {category}[/]")
        raise typer.Exit(0)

    table = Table(title="Template Gallery", show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", width=24)
    table.add_column("Name", width=38)
    table.add_column("Category", width=18)
    table.add_column("Difficulty", width=14)
    table.add_column("Score", justify="right", width=7)
    table.add_column("Cost/mo", width=16)

    for t in templates:
        # Difficulty badge color
        diff_colors = {
            "starter": "green",
            "intermediate": "yellow",
            "advanced": "red",
            "expert": "bold red",
        }
        diff_color = diff_colors.get(t.difficulty, "white")
        table.add_row(
            t.id,
            t.name,
            t.category.value,
            f"[{diff_color}]{t.difficulty}[/]",
            f"{t.resilience_score:.0f}",
            t.estimated_monthly_cost,
        )

    console.print()
    console.print(table)
    console.print("\n[dim]Use: faultray template info <id>  |  faultray template use <id> --output my-infra.yaml[/]")
    console.print()

    # Also list YAML-based templates
    from faultray.templates import list_templates as list_yaml_templates

    yaml_templates = list_yaml_templates()
    if yaml_templates:
        yaml_table = Table(title="YAML Templates (legacy)", show_header=True, header_style="bold dim")
        yaml_table.add_column("Name", style="cyan", width=18)
        yaml_table.add_column("File", width=28)
        for yt in yaml_templates:
            yaml_table.add_row(yt["name"], yt["file"])
        console.print(yaml_table)
        console.print()


@template_app.command("info")
def template_info(
    template_id: str = typer.Argument(
        ...,
        help="Template ID (e.g. 'ha-web-3tier', 'microservices-k8s').",
    ),
) -> None:
    """Show detailed information about a template.

    Example:
        faultray template info ha-web-3tier
        faultray template info microservices-k8s
    """
    from faultray.templates.gallery import TemplateGallery

    gallery = TemplateGallery()
    try:
        t = gallery.get_template(template_id)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    # Header
    console.print()
    console.print(Panel(
        f"[bold]{t.name}[/]\n\n{t.description}",
        title=f"Template: {t.id}",
        border_style="cyan",
    ))

    # Info table
    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column("Key", style="bold", width=24)
    info_table.add_column("Value", width=50)

    info_table.add_row("Category", t.category.value)
    info_table.add_row("Architecture", t.architecture_style)
    info_table.add_row("Target Availability", f"{t.target_nines} nines ({_nines_to_pct(t.target_nines)})")
    info_table.add_row("Est. Monthly Cost", t.estimated_monthly_cost)
    info_table.add_row("Resilience Score", f"{t.resilience_score:.0f}/100")
    info_table.add_row("Difficulty", t.difficulty)
    info_table.add_row("Cloud Provider", t.cloud_provider)
    info_table.add_row("Components", str(len(t.components)))
    info_table.add_row("Dependencies", str(len(t.edges)))
    if t.compliance:
        info_table.add_row("Compliance", ", ".join(t.compliance))
    if t.tags:
        info_table.add_row("Tags", ", ".join(t.tags))

    console.print(info_table)

    # Components
    console.print("\n[bold]Components:[/]")
    comp_table = Table(show_header=True, header_style="bold")
    comp_table.add_column("ID", style="cyan", width=20)
    comp_table.add_column("Name", width=30)
    comp_table.add_column("Type", width=15)
    comp_table.add_column("Replicas", justify="right", width=10)
    for c in t.components:
        comp_table.add_row(c["id"], c["name"], c["type"], str(c.get("replicas", 1)))
    console.print(comp_table)

    # Best practices
    if t.best_practices:
        console.print("\n[bold]Best Practices:[/]")
        for bp in t.best_practices:
            console.print(f"  [green]*[/] {bp}")

    # Mermaid diagram
    if t.diagram_mermaid:
        console.print("\n[bold]Architecture Diagram (Mermaid):[/]")
        console.print(Panel(t.diagram_mermaid, border_style="dim"))

    console.print()


@template_app.command("use")
def template_use(
    name: str = typer.Argument(
        ...,
        help="Template ID or legacy name (e.g. 'ha-web-3tier', 'web-app').",
    ),
    output: Path = typer.Option(
        None, "--output", "-o",
        help="Output path for the generated YAML file.",
    ),
) -> None:
    """Instantiate a template as a YAML file for customization.

    Supports both gallery templates (by ID) and legacy YAML templates (by name).

    Example:
        faultray template use ha-web-3tier --output my-infra.yaml
        faultray template use microservices-k8s -o k8s-setup.yaml
        faultray template use web-app -o legacy.yaml
    """
    # Try gallery first
    from faultray.templates.gallery import TemplateGallery

    gallery = TemplateGallery()
    try:
        yaml_content = gallery.to_yaml(name)
        if output is None:
            output = Path(f"{name.replace('-', '_')}.yaml")
        output.write_text(yaml_content, encoding="utf-8")
        console.print(f"[green]Gallery template '{name}' written to {output}[/]")
        console.print(f"[dim]Load with: faultray load {output}[/]")
        return
    except KeyError:
        pass

    # Fall back to legacy YAML templates
    from faultray.templates import TEMPLATES, get_template_path

    if name not in TEMPLATES:
        console.print(f"[red]Unknown template: '{name}'[/]")
        # Show available options
        gallery_ids = [t.id for t in gallery.list_templates()]
        legacy_ids = list(TEMPLATES.keys())
        console.print(f"[dim]Gallery templates: {', '.join(gallery_ids)}[/]")
        console.print(f"[dim]Legacy templates: {', '.join(legacy_ids)}[/]")
        raise typer.Exit(1)

    src = get_template_path(name)
    if not src.exists():
        console.print(f"[red]Template file missing: {src}[/]")
        raise typer.Exit(1)

    if output is None:
        output = Path(f"{name.replace('-', '_')}.yaml")

    shutil.copy2(src, output)
    console.print(f"[green]Template '{name}' written to {output}[/]")
    console.print(f"[dim]Load with: faultray load {output}[/]")


@template_app.command("compare")
def template_compare(
    template_id: str = typer.Argument(
        ...,
        help="Template ID to compare against.",
    ),
    model: Path = typer.Argument(
        ...,
        help="Path to your infrastructure YAML file.",
    ),
) -> None:
    """Compare your infrastructure against a reference template.

    Example:
        faultray template compare ha-web-3tier my-infra.yaml
    """
    from faultray.model.loader import load_yaml
    from faultray.templates.gallery import TemplateGallery

    gallery = TemplateGallery()

    try:
        user_graph = load_yaml(model)
    except Exception as e:
        console.print(f"[red]Error loading {model}: {e}[/]")
        raise typer.Exit(1)

    try:
        comparison = gallery.compare_with(template_id, user_graph)
    except KeyError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    # Display comparison
    console.print()
    console.print(Panel(
        f"Comparing your infrastructure vs [cyan]{comparison['template_name']}[/]",
        title="Template Comparison",
        border_style="cyan",
    ))

    # Score comparison
    score_table = Table(show_header=True, header_style="bold", title="Score Comparison")
    score_table.add_column("Metric", width=28)
    score_table.add_column("Your Infra", justify="right", width=15)
    score_table.add_column("Template", justify="right", width=15)
    score_table.add_column("Gap", justify="right", width=10)

    score_table.add_row(
        "Overall Score",
        f"{comparison['user_score']:.1f}",
        f"{comparison['template_score']:.1f}",
        _format_gap(comparison['score_gap']),
    )

    for key in comparison["user_breakdown"]:
        user_val = comparison["user_breakdown"][key]
        tmpl_val = comparison["template_breakdown"][key]
        gap = tmpl_val - user_val
        score_table.add_row(
            key.replace("_", " ").title(),
            f"{user_val:.1f}",
            f"{tmpl_val:.1f}",
            _format_gap(gap),
        )

    console.print(score_table)

    # Feature comparison
    feat = comparison["feature_comparison"]
    feat_table = Table(show_header=True, header_style="bold", title="Feature Comparison")
    feat_table.add_column("Feature", width=24)
    feat_table.add_column("Your Infra", justify="right", width=15)
    feat_table.add_column("Template", justify="right", width=15)

    for feature_name, vals in feat.items():
        feat_table.add_row(
            feature_name.replace("_", " ").title(),
            str(vals["user"]),
            str(vals["template"]),
        )

    console.print(feat_table)

    # Component comparison
    comp = comparison["component_comparison"]
    console.print(f"\n[bold]Components:[/] Your infra: {comp['user_count']}  |  Template: {comp['template_count']}")
    if comp["missing_types"]:
        console.print(f"  [yellow]Missing types:[/] {', '.join(comp['missing_types'])}")
    if comp["extra_types"]:
        console.print(f"  [green]Extra types:[/] {', '.join(comp['extra_types'])}")

    # Recommendations
    if comparison["recommendations"]:
        console.print("\n[bold]Recommendations:[/]")
        for rec in comparison["recommendations"]:
            console.print(f"  [yellow]*[/] {rec}")

    console.print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nines_to_pct(nines: float) -> str:
    """Convert availability nines to percentage string."""
    pct = 100.0 - (100.0 / (10 ** nines))
    return f"{pct:.{max(0, int(nines) - 1)}f}%"


def _format_gap(gap: float) -> str:
    """Format a score gap with color."""
    if gap > 0:
        return f"[red]-{gap:.1f}[/]"
    elif gap < 0:
        return f"[green]+{abs(gap):.1f}[/]"
    return "[dim]0.0[/]"
