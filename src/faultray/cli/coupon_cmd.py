# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for coupon code management.

Subcommands:
    faultray coupon create   — generate a new coupon (admin)
    faultray coupon redeem   — apply a coupon (user)
    faultray coupon list     — show all coupons (admin)
    faultray coupon revoke   — invalidate a coupon (admin)
"""

from __future__ import annotations


import typer
from rich.table import Table

from faultray.cli.main import app, console

coupon_app = typer.Typer(
    name="coupon",
    help="Manage coupon codes for temporary tier access.",
    no_args_is_help=True,
)
app.add_typer(coupon_app, name="coupon")


@coupon_app.command("create")
def coupon_create(
    tier: str = typer.Option(
        ...,
        "--tier",
        "-t",
        help="Pricing tier to grant: pro, business, or enterprise.",
    ),
    days: int = typer.Option(
        30,
        "--days",
        "-d",
        help="Number of days the coupon is valid after redemption.",
    ),
    max_uses: int = typer.Option(
        0,
        "--max-uses",
        "-u",
        help="Maximum number of redemptions (0 = unlimited).",
    ),
    note: str = typer.Option(
        "",
        "--note",
        "-n",
        help="Optional memo attached to the coupon.",
    ),
) -> None:
    """Generate a new coupon code (admin)."""
    from faultray.coupon import create_coupon

    try:
        coupon = create_coupon(tier=tier, days=days, max_uses=max_uses, note=note)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    uses_label = str(coupon.max_uses) if coupon.max_uses > 0 else "unlimited"
    console.print(f"\n[bold green]{coupon.code}[/]")
    console.print(
        f"  Tier: [cyan]{coupon.tier}[/]  |  "
        f"Valid for: [cyan]{coupon.days} days[/]  |  "
        f"Max uses: [cyan]{uses_label}[/]"
    )
    if coupon.note:
        console.print(f"  Note: {coupon.note}")
    console.print(f"  Expires at: {coupon.expires_at}")


@coupon_app.command("redeem")
def coupon_redeem(
    code: str = typer.Argument(
        ...,
        help="Coupon code to redeem (e.g. FRAY-A1B2-C3D4-E5F6).",
    ),
) -> None:
    """Apply a coupon code to activate tier access (user)."""
    from faultray.coupon import redeem_coupon

    try:
        redeemed = redeem_coupon(code)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        f"\n[bold green]Coupon applied![/] "
        f"[cyan]{redeemed.tier.capitalize()}[/] tier active until "
        f"[bold]{redeemed.active_until[:10]}[/]"
    )


@coupon_app.command("list")
def coupon_list() -> None:
    """Show all coupons in the registry (admin)."""
    from faultray.coupon import list_coupons

    coupons = list_coupons()
    if not coupons:
        console.print("[yellow]No coupons found in ~/.faultray/coupons.json[/]")
        return

    table = Table(title="Coupon Registry", show_lines=False)
    table.add_column("Code", style="bold")
    table.add_column("Tier", style="cyan")
    table.add_column("Days Left", justify="right")
    table.add_column("Uses", justify="right")
    table.add_column("Status")
    table.add_column("Note")

    for coupon in coupons:
        if coupon.revoked:
            status = "[red]revoked[/]"
        elif not coupon.is_valid():
            status = "[yellow]expired[/]"
        else:
            status = "[green]active[/]"

        uses_label = (
            f"{coupon.current_uses}/{coupon.max_uses}"
            if coupon.max_uses > 0
            else f"{coupon.current_uses}/∞"
        )
        table.add_row(
            coupon.code,
            coupon.tier,
            str(coupon.days_remaining()),
            uses_label,
            status,
            coupon.note,
        )

    console.print(table)


@coupon_app.command("revoke")
def coupon_revoke(
    code: str = typer.Argument(
        ...,
        help="Coupon code to revoke (e.g. FRAY-A1B2-C3D4-E5F6).",
    ),
) -> None:
    """Invalidate a coupon so it can no longer be redeemed (admin)."""
    from faultray.coupon import revoke_coupon

    try:
        coupon = revoke_coupon(code)
    except ValueError as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[yellow]Revoked:[/] [bold]{coupon.code}[/]")
