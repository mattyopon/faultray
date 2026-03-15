"""CLI commands for the Chaos Scenario Marketplace.

Provides subcommands to browse, search, install, and export chaos scenario
packages from the local-first marketplace.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from infrasim.cli.main import app, console


# ---------------------------------------------------------------------------
# Marketplace subcommand group
# ---------------------------------------------------------------------------


@app.command("marketplace")
def marketplace(
    action: str = typer.Argument(
        ...,
        help=(
            "Action: list | search | info | install | featured | popular | "
            "new | categories | export | rate"
        ),
    ),
    target: str = typer.Argument(default="", help="Package ID, search query, or output path"),
    category: str = typer.Option("", "--category", "-c", help="Filter by category"),
    provider: str = typer.Option("", "--provider", "-p", help="Filter by provider (aws/azure/gcp/kubernetes/generic)"),
    query: str = typer.Option("", "--query", "-q", help="Search query string"),
    name: str = typer.Option("", "--name", "-n", help="Package name for export"),
    output: str = typer.Option("", "--output", "-o", help="Output file path for export"),
    score: int = typer.Option(0, "--score", help="Rating score (1-5)"),
    comment: str = typer.Option("", "--comment", help="Rating comment"),
    author: str = typer.Option("anonymous", "--author", help="Author name"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Chaos Scenario Marketplace - browse, install, and share chaos scenarios.

    Examples:

        # List all packages
        faultray marketplace list

        # List AWS packages only
        faultray marketplace list --provider aws

        # List security category
        faultray marketplace list --category security

        # Search packages
        faultray marketplace search "database failover"

        # Show package details
        faultray marketplace info aws-region-failover

        # Install a package (import scenarios)
        faultray marketplace install kubernetes-pod-disruption

        # Show featured packages
        faultray marketplace featured

        # Show popular packages
        faultray marketplace popular

        # Show recently added packages
        faultray marketplace new

        # Show categories
        faultray marketplace categories

        # Export local scenarios as package
        faultray marketplace export --name "my-scenarios" --output my-pack.json

        # Rate a package
        faultray marketplace rate aws-region-failover --score 5 --comment "Excellent"
    """
    from infrasim.marketplace import ScenarioMarketplace

    mp = ScenarioMarketplace()

    if action == "list":
        _cmd_list(mp, category=category, provider=provider, json_output=json_output)
    elif action == "search":
        search_query = target or query
        if not search_query:
            console.print("[red]Please provide a search query.[/]")
            console.print("[dim]Usage: faultray marketplace search \"query\"[/]")
            raise typer.Exit(1)
        _cmd_search(mp, search_query, json_output=json_output)
    elif action == "info":
        if not target:
            console.print("[red]Please provide a package ID.[/]")
            raise typer.Exit(1)
        _cmd_info(mp, target, json_output=json_output)
    elif action == "install":
        if not target:
            console.print("[red]Please provide a package ID.[/]")
            raise typer.Exit(1)
        _cmd_install(mp, target)
    elif action == "featured":
        _cmd_featured(mp, json_output=json_output)
    elif action == "popular":
        _cmd_popular(mp, json_output=json_output)
    elif action == "new":
        _cmd_new(mp, json_output=json_output)
    elif action == "categories":
        _cmd_categories(mp, json_output=json_output)
    elif action == "export":
        _cmd_export(mp, name=name, output_path=output)
    elif action == "rate":
        if not target:
            console.print("[red]Please provide a package ID.[/]")
            raise typer.Exit(1)
        if score < 1 or score > 5:
            console.print("[red]Score must be between 1 and 5.[/]")
            raise typer.Exit(1)
        _cmd_rate(mp, target, author=author, score=score, comment=comment)
    else:
        console.print(
            f"[red]Unknown action: {action}[/]\n"
            "[dim]Available: list | search | info | install | featured | popular | "
            "new | categories | export | rate[/]"
        )
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_COLORS = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "green",
}

_DIFFICULTY_COLORS = {
    "beginner": "green",
    "intermediate": "yellow",
    "advanced": "red",
    "expert": "bold red",
}


def _severity_styled(severity: str) -> str:
    color = _SEVERITY_COLORS.get(severity, "white")
    return f"[{color}]{severity.upper()}[/]"


def _difficulty_styled(difficulty: str) -> str:
    color = _DIFFICULTY_COLORS.get(difficulty, "white")
    return f"[{color}]{difficulty}[/]"


def _rating_stars(rating: float) -> str:
    filled = int(round(rating))
    return "[yellow]" + "*" * filled + "[/][dim]" + "*" * (5 - filled) + "[/]"


def _packages_table(packages: list, title: str = "Marketplace Packages") -> Table:
    """Build a Rich Table for a list of packages."""
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="cyan", width=26)
    table.add_column("Name", width=32)
    table.add_column("Provider", width=12)
    table.add_column("Category", width=16)
    table.add_column("Severity", width=10, justify="center")
    table.add_column("Difficulty", width=14, justify="center")
    table.add_column("Rating", width=10, justify="center")
    table.add_column("DLs", width=6, justify="right")
    table.add_column("Scenarios", width=10, justify="center")

    for pkg in packages:
        rating_str = f"{pkg.average_rating:.1f}" if pkg.average_rating > 0 else "N/A"
        table.add_row(
            pkg.id,
            pkg.name,
            pkg.provider,
            pkg.category,
            _severity_styled(pkg.severity),
            _difficulty_styled(pkg.difficulty),
            rating_str,
            str(pkg.downloads),
            str(pkg.scenario_count),
        )
    return table


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def _cmd_list(mp, category: str, provider: str, json_output: bool) -> None:
    packages = mp.list_packages(
        category=category or None,
        provider=provider or None,
    )

    if json_output:
        console.print_json(data=[p.to_dict() for p in packages])
        return

    if not packages:
        console.print("[yellow]No packages found.[/]")
        return

    title = "Marketplace Packages"
    filters = []
    if category:
        filters.append(f"category={category}")
    if provider:
        filters.append(f"provider={provider}")
    if filters:
        title += f" ({', '.join(filters)})"

    console.print()
    console.print(_packages_table(packages, title=title))
    console.print(f"\n[dim]{len(packages)} package(s) found. "
                  f"Use 'faultray marketplace info <id>' for details.[/]")


def _cmd_search(mp, query: str, json_output: bool) -> None:
    results = mp.search(query)

    if json_output:
        console.print_json(data=[p.to_dict() for p in results])
        return

    if not results:
        console.print(f'[yellow]No packages found matching "{query}".[/]')
        return

    console.print()
    console.print(_packages_table(results, title=f'Search Results: "{query}"'))
    console.print(f"\n[dim]{len(results)} result(s)[/]")


def _cmd_info(mp, package_id: str, json_output: bool) -> None:
    try:
        pkg = mp.get_package(package_id)
    except KeyError:
        console.print(f"[red]Package not found: {package_id}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data=pkg.to_dict())
        return

    # Package info panel
    tags_str = ", ".join(f"[dim]{t}[/]" for t in pkg.tags) if pkg.tags else "None"
    prereqs_str = ", ".join(pkg.prerequisites) if pkg.prerequisites else "None"

    info_text = (
        f"[bold]{pkg.name}[/] [dim]v{pkg.version}[/]\n"
        f"[dim]by {pkg.author}[/]\n\n"
        f"{pkg.description}\n\n"
        f"[bold]Category:[/]     {pkg.category}\n"
        f"[bold]Provider:[/]     {pkg.provider}\n"
        f"[bold]Severity:[/]     {_severity_styled(pkg.severity)}\n"
        f"[bold]Difficulty:[/]   {_difficulty_styled(pkg.difficulty)}\n"
        f"[bold]Duration:[/]     {pkg.estimated_duration}\n"
        f"[bold]Rating:[/]       {_rating_stars(pkg.average_rating)} ({pkg.average_rating:.1f}/5)\n"
        f"[bold]Downloads:[/]    {pkg.downloads:,}\n"
        f"[bold]Scenarios:[/]    {pkg.scenario_count}\n"
        f"[bold]Tags:[/]         {tags_str}\n"
        f"[bold]Prerequisites:[/] {prereqs_str}\n"
        f"[bold]Created:[/]      {pkg.created_at.strftime('%Y-%m-%d')}\n"
        f"[bold]Updated:[/]      {pkg.updated_at.strftime('%Y-%m-%d')}"
    )

    console.print()
    console.print(Panel(
        info_text,
        title=f"[bold cyan]{pkg.id}[/]",
        border_style="cyan",
    ))

    # Scenarios table
    if pkg.scenarios:
        scenario_table = Table(title="Included Scenarios", show_header=True)
        scenario_table.add_column("#", width=3, justify="right")
        scenario_table.add_column("Name", style="cyan", width=30)
        scenario_table.add_column("Description", width=50)
        scenario_table.add_column("Faults", width=8, justify="center")
        scenario_table.add_column("Traffic", width=8, justify="center")

        for i, s in enumerate(pkg.scenarios, 1):
            fault_count = len(s.get("faults", []))
            traffic = s.get("traffic_multiplier", 1.0)
            traffic_str = f"{traffic:.0f}x" if traffic != 1.0 else "1x"
            scenario_table.add_row(
                str(i),
                s.get("name", "Unnamed"),
                (s.get("description", "")[:48] + "..." if len(s.get("description", "")) > 48 else s.get("description", "")),
                str(fault_count),
                traffic_str,
            )

        console.print()
        console.print(scenario_table)

    # Reviews
    if pkg.reviews:
        console.print("\n[bold]Reviews:[/]")
        for r in pkg.reviews[:5]:
            stars = _rating_stars(r.rating)
            console.print(f"  {stars}  [bold]{r.author}[/]: {r.comment}")

    console.print(f"\n[dim]Install: faultray marketplace install {pkg.id}[/]")


def _cmd_install(mp, package_id: str) -> None:
    try:
        scenarios = mp.install_package(package_id)
    except KeyError:
        console.print(f"[red]Package not found: {package_id}[/]")
        raise typer.Exit(1)

    console.print(f"\n[green]Installed {len(scenarios)} scenario(s) from '{package_id}'[/]\n")

    for s in scenarios:
        fault_types = ", ".join(f.fault_type.value for f in s.faults)
        console.print(f"  [cyan]{s.name}[/] - {s.description[:60]}")
        console.print(f"    Faults: {fault_types}")

    console.print(
        f"\n[dim]Scenarios are now available for simulation. "
        f"Run 'faultray simulate' to test your infrastructure.[/]"
    )


def _cmd_featured(mp, json_output: bool) -> None:
    featured = mp.get_featured()

    if json_output:
        console.print_json(data=[p.to_dict() for p in featured])
        return

    if not featured:
        console.print("[yellow]No featured packages.[/]")
        return

    console.print()
    console.print(Panel(
        "[bold]Hand-picked packages recommended by the ChaosProof team[/]",
        title="[bold]Featured Packages[/]",
        border_style="green",
    ))
    console.print(_packages_table(featured, title="Featured Packages"))


def _cmd_popular(mp, json_output: bool) -> None:
    popular = mp.get_popular()

    if json_output:
        console.print_json(data=[p.to_dict() for p in popular])
        return

    if not popular:
        console.print("[yellow]No packages found.[/]")
        return

    console.print()
    console.print(_packages_table(popular, title="Most Popular Packages"))


def _cmd_new(mp, json_output: bool) -> None:
    new_pkgs = mp.get_new()

    if json_output:
        console.print_json(data=[p.to_dict() for p in new_pkgs])
        return

    if not new_pkgs:
        console.print("[yellow]No packages found.[/]")
        return

    console.print()
    console.print(_packages_table(new_pkgs, title="Recently Added Packages"))


def _cmd_categories(mp, json_output: bool) -> None:
    categories = mp.get_categories()

    if json_output:
        console.print_json(data=[c.to_dict() for c in categories])
        return

    table = Table(title="Marketplace Categories", show_header=True, header_style="bold cyan")
    table.add_column("Category", style="cyan", width=20)
    table.add_column("Display Name", width=20)
    table.add_column("Description", width=50)
    table.add_column("Packages", width=10, justify="center")

    for cat in categories:
        table.add_row(
            cat.name,
            cat.display_name,
            cat.description,
            str(cat.package_count),
        )

    console.print()
    console.print(table)


def _cmd_export(mp, name: str, output_path: str) -> None:
    if not name:
        console.print("[red]Please provide a package name with --name.[/]")
        raise typer.Exit(1)

    # For export, we create a simple package from the demo scenarios
    from infrasim.simulator.scenarios import Fault, FaultType, Scenario

    # Create a sample export scenario
    sample_scenarios = [
        Scenario(
            id="exported-1",
            name=f"{name} Scenario 1",
            description=f"Custom scenario from {name}",
            faults=[
                Fault(
                    target_component_id="target-1",
                    fault_type=FaultType.COMPONENT_DOWN,
                    severity=1.0,
                    duration_seconds=300,
                ),
            ],
        ),
    ]

    pkg = mp.export_scenarios(sample_scenarios, package_name=name)

    if output_path:
        out = Path(output_path)
        out.write_text(json.dumps(pkg.to_dict(), indent=2, default=str), encoding="utf-8")
        console.print(f"[green]Package exported to {out}[/]")
    else:
        console.print(f"[green]Package '{name}' created with ID: {pkg.id}[/]")
        console.print(f"[dim]Saved to marketplace store. Share the JSON to distribute.[/]")


def _cmd_rate(mp, package_id: str, author: str, score: int, comment: str) -> None:
    try:
        mp.add_review(package_id, author=author, rating=score, comment=comment)
    except KeyError:
        console.print(f"[red]Package not found: {package_id}[/]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    console.print(f"[green]Rated '{package_id}': {'*' * score} ({score}/5)[/]")
    if comment:
        console.print(f"[dim]Comment: {comment}[/]")
