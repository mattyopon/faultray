# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Feed-related CLI commands: feed-update, feed-list, feed-sources, feed-clear."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from faultray.cli.main import DEFAULT_MODEL_PATH, InfraGraph, app, console


@app.command()
def feed_update(
    model: Path = typer.Option(DEFAULT_MODEL_PATH, "--model", "-m", help="Model file for component-aware scenario generation"),
    timeout: float = typer.Option(15.0, "--timeout", "-t", help="HTTP timeout per feed (seconds)"),
) -> None:
    """Fetch security news feeds and generate new chaos scenarios.

    Fetches articles from security news RSS/Atom feeds, analyzes them for
    infrastructure incident patterns, and generates chaos scenarios that are
    stored locally for future simulations.

    Examples:
        # Update feeds with default settings
        faultray feed-update

        # Use a specific model for component-aware scenarios
        faultray feed-update --model my-model.json

        # Custom HTTP timeout
        faultray feed-update --timeout 30
    """
    from faultray.feeds.analyzer import analyze_articles, incidents_to_scenarios
    from faultray.feeds.fetcher import fetch_all_feeds
    from faultray.feeds.sources import get_enabled_sources
    from faultray.feeds.store import save_feed_scenarios

    sources = get_enabled_sources()
    console.print(f"[cyan]Fetching {len(sources)} security news feeds...[/]")

    # Fetch all feeds
    articles = asyncio.run(fetch_all_feeds(sources, timeout=timeout))
    console.print(f"  Fetched [bold]{len(articles)}[/] articles from {len(sources)} sources")

    if not articles:
        console.print("[yellow]No articles fetched. Check network connection.[/]")
        return

    # Analyze articles for incident patterns
    console.print("[cyan]Analyzing articles for incident patterns...[/]")
    incidents = analyze_articles(articles)
    console.print(f"  Matched [bold]{len(incidents)}[/] incident patterns")

    if not incidents:
        console.print("[green]No new incident patterns detected.[/]")
        return

    # Show matched patterns
    from rich.table import Table

    table = Table(title="Detected Incident Patterns", show_header=True)
    table.add_column("Pattern", style="cyan", width=30)
    table.add_column("Source", width=20)
    table.add_column("Confidence", width=10)
    table.add_column("Keywords", style="dim")

    for inc in incidents[:20]:  # Show top 20
        conf = inc.confidence
        if conf > 0.7:
            conf_str = f"[green]{conf:.0%}[/]"
        elif conf > 0.4:
            conf_str = f"[yellow]{conf:.0%}[/]"
        else:
            conf_str = f"[dim]{conf:.0%}[/]"

        table.add_row(
            inc.pattern.name,
            inc.article.source_name,
            conf_str,
            ", ".join(inc.matched_keywords[:3]),
        )

    console.print(table)

    # Generate scenarios
    component_ids: list[str] = []
    components = None
    if model.exists():
        graph = InfraGraph.load(model)
        component_ids = list(graph.components.keys())
        components = graph.components
        console.print(f"[cyan]Mapping to infrastructure model ({len(component_ids)} components)...[/]")
    else:
        console.print("[yellow]No model file found. Generating generic scenarios.[/]")
        component_ids = ["generic-target"]

    scenarios = incidents_to_scenarios(incidents, component_ids, components)

    # Save to store
    articles_meta = [
        {
            "title": inc.article.title,
            "link": inc.article.link,
            "source": inc.article.source_name,
            "published": inc.article.published,
            "pattern": inc.pattern.id,
            "confidence": inc.confidence,
        }
        for inc in incidents
    ]
    store_path = save_feed_scenarios(scenarios, articles_meta)

    console.print(f"\n[green]Generated {len(scenarios)} new scenarios from security feeds[/]")
    console.print(f"[dim]Store: {store_path}[/]")
    console.print("\nRun [cyan]faultray simulate[/] to include feed scenarios in simulation.")


@app.command()
def feed_list() -> None:
    """Show stored feed-generated scenarios and statistics.

    Examples:
        # List all stored feed scenarios
        faultray feed-list
    """
    from faultray.feeds.store import get_store_stats, load_store_raw

    stats = get_store_stats()
    raw = load_store_raw()

    if not stats["last_updated"]:
        console.print("[yellow]No feed data yet. Run [cyan]faultray feed-update[/] first.[/]")
        return

    console.print("\n[bold]Feed Scenario Store[/]")
    console.print(f"  Last updated: [cyan]{stats['last_updated']}[/]")
    console.print(f"  Scenarios: [bold]{stats['scenario_count']}[/]")
    console.print(f"  Source articles: [bold]{stats['article_count']}[/]")
    console.print(f"  Store path: [dim]{stats['store_path']}[/]")

    # Show scenarios
    scenarios_data = raw.get("scenarios", [])
    if scenarios_data:
        from rich.table import Table

        table = Table(title="\nStored Scenarios", show_header=True)
        table.add_column("Name", style="cyan", width=35)
        table.add_column("Faults", width=8)
        table.add_column("Traffic", width=8)
        table.add_column("ID", style="dim", width=16)

        for s in scenarios_data:
            traffic = s.get("traffic_multiplier", 1.0)
            traffic_str = f"{traffic}x" if traffic > 1.0 else "normal"
            table.add_row(
                s["name"],
                str(len(s.get("faults", []))),
                traffic_str,
                s["id"][:16],
            )

        console.print(table)

    # Show recent articles
    articles = raw.get("articles", [])
    if articles:
        console.print(f"\n[bold]Recent Source Articles ({len(articles)}):[/]")
        for art in articles[:10]:
            conf = art.get("confidence", 0)
            console.print(
                f"  [{art.get('source', '?')}] {art.get('title', '?')[:70]} "
                f"[dim]({conf:.0%} match)[/]"
            )
        if len(articles) > 10:
            console.print(f"  [dim]... and {len(articles) - 10} more[/]")


@app.command()
def feed_sources() -> None:
    """Show configured feed sources.

    Examples:
        # List all configured feed sources
        faultray feed-sources
    """
    from faultray.feeds.sources import DEFAULT_SOURCES

    from rich.table import Table

    table = Table(title="Security News Feed Sources", show_header=True)
    table.add_column("Name", style="cyan", width=25)
    table.add_column("Type", width=6)
    table.add_column("Status", width=8)
    table.add_column("Tags", style="dim")
    table.add_column("URL", style="dim", width=50)

    for src in DEFAULT_SOURCES:
        status = "[green]ON[/]" if src.enabled else "[red]OFF[/]"
        table.add_row(
            src.name,
            src.feed_type,
            status,
            ", ".join(src.tags),
            src.url[:50],
        )

    console.print(table)
    console.print(f"\n[dim]{len(DEFAULT_SOURCES)} sources configured[/]")


@app.command()
def feed_clear() -> None:
    """Clear all stored feed-generated scenarios.

    Examples:
        # Clear the feed scenario store
        faultray feed-clear
    """
    from faultray.feeds.store import clear_store, get_store_stats

    stats = get_store_stats()
    if not stats["last_updated"]:
        console.print("[yellow]Store is already empty.[/]")
        return

    clear_store()
    console.print(f"[green]Cleared {stats['scenario_count']} feed scenarios.[/]")
