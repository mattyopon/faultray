# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for AWS Resilience Hub pre-deploy bridge.

Positions FaultRay as "AWS Resilience Hub for Terraform Plan" — score your
infrastructure resilience BEFORE deployment by analyzing a terraform plan.

Commands:
    faultray resilience-hub predict <plan.json> [--policy policy.yaml] [--json] [--html]
    faultray resilience-hub compare <plan.json> --live-assessment hub-export.json [--json]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from faultray.cli.main import app, console

# Sub-application registered under the "resilience-hub" command group
resilience_hub_app = typer.Typer(
    name="resilience-hub",
    help=(
        "AWS Resilience Hub pre-deploy bridge. "
        "Score infrastructure resilience from a Terraform plan BEFORE deployment."
    ),
    no_args_is_help=True,
)
app.add_typer(resilience_hub_app, name="resilience-hub")


# ---------------------------------------------------------------------------
# predict
# ---------------------------------------------------------------------------

@resilience_hub_app.command("predict")
def predict(
    plan_file: Path = typer.Argument(
        ..., help="Path to Terraform plan JSON file (terraform show -json output)"
    ),
    policy_file: Optional[Path] = typer.Option(
        None, "--policy",
        help="Path to resilience policy YAML defining RTO/RPO targets",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON in Resilience Hub format"),
    html_output: bool = typer.Option(False, "--html", help="Output HTML report"),
    app_name: str = typer.Option(
        "terraform-app", "--app-name",
        help="Application name for the assessment",
    ),
    min_score: float = typer.Option(
        60.0, "--min-score",
        help="Minimum resiliency score that maps to MeetsPolicy",
    ),
    fail_on_breach: bool = typer.Option(
        False, "--fail-on-breach",
        help="Exit with code 1 if the policy status is PolicyBreached",
    ),
) -> None:
    """Predict AWS Resilience Hub score from a Terraform plan (pre-deploy).

    Analyzes the Terraform plan to build a pre-deployment resilience assessment
    that mirrors the output format of AWS Resilience Hub. Use this in CI/CD to
    gate deployments before the infrastructure is created.

    Examples:
        # Basic prediction
        faultray resilience-hub predict plan.json

        # With a custom policy file and JSON output (for CI/CD)
        faultray resilience-hub predict plan.json --policy policy.yaml --json

        # Fail the pipeline if the predicted score is below policy
        faultray resilience-hub predict plan.json --fail-on-breach

        # Named application
        faultray resilience-hub predict plan.json --app-name my-api
    """
    from faultray.integrations.aws_resilience_hub_bridge import (
        AWSResilienceHubBridge,
    )

    if not plan_file.exists():
        console.print(f"[red]Plan file not found: {plan_file}[/]")
        raise typer.Exit(1)

    if not json_output and not html_output:
        console.print(
            f"[cyan]Analyzing Terraform plan for Resilience Hub prediction: {plan_file}...[/]"
        )

    # Load policy
    policy = _load_policy(policy_file, min_score)

    bridge = AWSResilienceHubBridge(policy=policy)

    # Parse plan
    try:
        plan_json = _load_json_file(plan_file)
    except Exception as exc:
        console.print(f"[red]Failed to read plan file: {exc}[/]")
        raise typer.Exit(1)

    # Run assessment
    try:
        assessment = bridge.from_terraform_plan(plan_json)
        assessment.app_name = app_name
    except Exception as exc:
        console.print(f"[red]Assessment failed: {exc}[/]")
        raise typer.Exit(1)

    # Serialize to Resilience Hub format
    hub_output = bridge.to_resilience_hub_format(assessment)

    if json_output:
        console.print_json(data=hub_output)
    elif html_output:
        _print_html_report(hub_output)
    else:
        _print_prediction_report(assessment, hub_output)

    # Gate: fail on policy breach
    if fail_on_breach and hub_output["complianceStatus"] == "PolicyBreached":
        if not json_output:
            console.print(
                f"\n[red]POLICY BREACHED: predicted resiliency score "
                f"{hub_output['resiliencyScore']:.1f} is below "
                f"threshold {min_score:.1f}[/]"
            )
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

@resilience_hub_app.command("compare")
def compare(
    plan_file: Path = typer.Argument(
        ..., help="Path to Terraform plan JSON file used for the original prediction"
    ),
    live_assessment_file: Path = typer.Option(
        ..., "--live-assessment",
        help="Path to the actual AWS Resilience Hub assessment export (JSON)",
    ),
    policy_file: Optional[Path] = typer.Option(
        None, "--policy",
        help="Path to resilience policy YAML (should match the original prediction)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON comparison report"),
    min_score: float = typer.Option(
        60.0, "--min-score",
        help="Minimum score threshold (should match original prediction)",
    ),
) -> None:
    """Compare a pre-deploy FaultRay prediction against an actual Resilience Hub assessment.

    After deploying infrastructure, export the AWS Resilience Hub assessment and
    use this command to measure how accurate FaultRay's pre-deploy prediction was.
    This helps you tune FaultRay's scoring for your specific infrastructure patterns.

    Examples:
        # Basic comparison
        faultray resilience-hub compare plan.json --live-assessment hub-export.json

        # JSON output for reporting
        faultray resilience-hub compare plan.json --live-assessment hub-export.json --json
    """
    from faultray.integrations.aws_resilience_hub_bridge import AWSResilienceHubBridge

    if not plan_file.exists():
        console.print(f"[red]Plan file not found: {plan_file}[/]")
        raise typer.Exit(1)

    if not live_assessment_file.exists():
        console.print(f"[red]Live assessment file not found: {live_assessment_file}[/]")
        raise typer.Exit(1)

    if not json_output:
        console.print(
            "[cyan]Comparing FaultRay prediction against Resilience Hub assessment...[/]"
        )

    policy = _load_policy(policy_file, min_score)
    bridge = AWSResilienceHubBridge(policy=policy)

    # Load plan and live assessment
    try:
        plan_json = _load_json_file(plan_file)
        hub_assessment = _load_json_file(live_assessment_file)
    except Exception as exc:
        console.print(f"[red]Failed to read input files: {exc}[/]")
        raise typer.Exit(1)

    # Build pre-deploy prediction
    try:
        assessment = bridge.from_terraform_plan(plan_json)
    except Exception as exc:
        console.print(f"[red]Failed to build pre-deploy assessment: {exc}[/]")
        raise typer.Exit(1)

    # Compare
    try:
        report = bridge.compare_with_live(assessment, hub_assessment)
    except Exception as exc:
        console.print(f"[red]Comparison failed: {exc}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data={
            "pre_deploy_score": report.pre_deploy_score,
            "live_score": report.live_score,
            "score_delta": report.score_delta,
            "prediction_accuracy": report.prediction_accuracy,
            "policy_status_match": report.policy_status_match,
            "disruption_deltas": report.disruption_deltas,
            "missed_risks": report.missed_risks,
            "extra_risks": report.extra_risks,
            "summary": report.summary,
        })
    else:
        _print_comparison_report(report)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _load_policy(
    policy_file: Path | None, min_score: float
) -> "ResiliencyPolicy":  # noqa: F821
    """Load a ResiliencyPolicy from a YAML file, or return the default."""
    from faultray.integrations.aws_resilience_hub_bridge import ResiliencyPolicy

    if policy_file is None:
        return ResiliencyPolicy(
            policy_name="FaultRay-Default",
            description="Default policy (override with --policy)",
            min_score_threshold=min_score,
        )

    if not policy_file.exists():
        console.print(f"[red]Policy file not found: {policy_file}[/]")
        raise typer.Exit(1)

    try:
        import yaml  # type: ignore[import]
        with policy_file.open() as fh:
            data = yaml.safe_load(fh) or {}
    except ImportError:
        console.print(
            "[yellow]PyYAML not installed — falling back to default policy.[/]"
        )
        return ResiliencyPolicy(
            policy_name="FaultRay-Default",
            min_score_threshold=min_score,
        )
    except Exception as exc:
        console.print(f"[red]Failed to load policy YAML: {exc}[/]")
        raise typer.Exit(1)

    from faultray.integrations.aws_resilience_hub_bridge import DisruptionType

    rto_raw = data.get("rto_seconds", {})
    rpo_raw = data.get("rpo_seconds", {})

    rto: dict[DisruptionType, int] = {}
    rpo: dict[DisruptionType, int] = {}

    for dt in DisruptionType:
        key = dt.value
        if key in rto_raw:
            rto[dt] = int(rto_raw[key])
        if key in rpo_raw:
            rpo[dt] = int(rpo_raw[key])

    return ResiliencyPolicy(
        policy_name=data.get("policy_name", "custom-policy"),
        description=data.get("description", ""),
        rto_seconds=rto if rto else ResiliencyPolicy.__dataclass_fields__["rto_seconds"].default_factory(),  # type: ignore[attr-defined]
        rpo_seconds=rpo if rpo else ResiliencyPolicy.__dataclass_fields__["rpo_seconds"].default_factory(),  # type: ignore[attr-defined]
        min_score_threshold=float(data.get("min_score_threshold", min_score)),
    )


def _load_json_file(path: Path) -> dict:
    """Load and parse a JSON file."""
    content = path.read_text(encoding="utf-8", errors="replace")
    return json.loads(content)


def _print_prediction_report(assessment: "PreDeployAssessment", hub_output: dict) -> None:  # noqa: F821
    """Print a Resilience Hub-style prediction report using Rich formatting."""
    from rich.panel import Panel
    from rich.table import Table

    score = hub_output["resiliencyScore"]
    status = hub_output["complianceStatus"]

    if status == "MeetsPolicy":
        status_color = "green"
        status_label = "[green][bold]MEETS POLICY[/bold][/]"
    elif status == "PolicyBreached":
        status_color = "red"
        status_label = "[red][bold]POLICY BREACHED[/bold][/]"
    else:
        status_color = "dim"
        status_label = "[dim]NOT ASSESSED[/dim]"

    if score >= 80:
        score_color = "green"
    elif score >= 60:
        score_color = "yellow"
    else:
        score_color = "red"

    summary = (
        f"[bold]Application:[/] {hub_output['appName']}\n"
        f"[bold]Source:[/] {hub_output['planSource']}\n\n"
        f"[bold]Resiliency Score:[/] [{score_color}][bold]{score:.1f} / 100[/bold][/]\n"
        f"[bold]Policy Status:[/] {status_label}\n"
        f"[bold]Resources analyzed:[/] {hub_output['resourceCount']}"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold]FaultRay — AWS Resilience Hub Pre-Deploy Prediction[/]",
        border_style=status_color,
    ))

    # Disruption table
    disruption = hub_output.get("disruptionResiliency", {})
    if disruption:
        table = Table(title="Disruption Resilience Breakdown", show_header=True)
        table.add_column("Disruption Type", style="cyan", width=18)
        table.add_column("Score", justify="right", width=8)
        table.add_column("Est. RTO", justify="right", width=12)
        table.add_column("Est. RPO", justify="right", width=12)
        table.add_column("Status", justify="center", width=16)

        for disruption_type, data in disruption.items():
            d_score = data["score"]
            if d_score >= 80:
                d_color = "green"
            elif d_score >= 60:
                d_color = "yellow"
            else:
                d_color = "red"

            d_status = data["policyStatus"]
            if d_status == "MeetsPolicy":
                d_status_str = "[green]MeetsPolicy[/]"
            elif d_status == "PolicyBreached":
                d_status_str = "[red]PolicyBreached[/]"
            else:
                d_status_str = "[dim]NotAssessed[/]"

            rto_mins = data["rtoInSecs"] // 60
            rpo_mins = data["rpoInSecs"] // 60

            table.add_row(
                disruption_type,
                f"[{d_color}]{d_score:.1f}[/]",
                f"{rto_mins}m",
                f"{rpo_mins}m",
                d_status_str,
            )

        console.print()
        console.print(table)

    # Recommendations
    recommendations = hub_output.get("recommendations", [])
    if recommendations:
        console.print("\n[bold]Recommendations:[/]")
        high = [r for r in recommendations if r.get("severity") == "HIGH"]
        medium = [r for r in recommendations if r.get("severity") == "MEDIUM"]
        low = [r for r in recommendations if r.get("severity") == "LOW"]

        for rec in high:
            console.print(
                f"  [red][HIGH][/] [{rec['disruptionType']}] {rec['recommendation']}"
            )
        for rec in medium:
            console.print(
                f"  [yellow][MED][/]  [{rec['disruptionType']}] {rec['recommendation']}"
            )
        for rec in low:
            console.print(
                f"  [dim][LOW][/]  [{rec['disruptionType']}] {rec['recommendation']}"
            )


def _print_comparison_report(report: "ComparisonReport") -> None:  # noqa: F821
    """Print a comparison report between pre-deploy prediction and live assessment."""
    from rich.panel import Panel
    from rich.table import Table

    accuracy_pct = report.prediction_accuracy * 100
    if accuracy_pct >= 90:
        accuracy_color = "green"
    elif accuracy_pct >= 70:
        accuracy_color = "yellow"
    else:
        accuracy_color = "red"

    delta = report.score_delta
    if abs(delta) <= 5:
        delta_str = f"[green]{delta:+.1f}[/]"
    elif abs(delta) <= 10:
        delta_str = f"[yellow]{delta:+.1f}[/]"
    else:
        delta_str = f"[red]{delta:+.1f}[/]"

    policy_match_str = (
        "[green]YES[/]" if report.policy_status_match else "[red]NO[/]"
    )

    summary = (
        f"[bold]Pre-deploy prediction:[/] {report.pre_deploy_score:.1f}\n"
        f"[bold]Live Resilience Hub score:[/] {report.live_score:.1f}\n"
        f"[bold]Score delta:[/] {delta_str} "
        f"[dim](positive = FaultRay was optimistic)[/]\n\n"
        f"[bold]Prediction accuracy:[/] "
        f"[{accuracy_color}][bold]{accuracy_pct:.0f}%[/bold][/]\n"
        f"[bold]Policy status match:[/] {policy_match_str}"
    )

    console.print()
    console.print(Panel(
        summary,
        title="[bold]FaultRay vs Resilience Hub — Comparison Report[/]",
        border_style=accuracy_color,
    ))

    # Per-disruption delta table
    if report.disruption_deltas:
        table = Table(title="Per-Disruption Score Delta", show_header=True)
        table.add_column("Disruption Type", style="cyan", width=18)
        table.add_column("FaultRay", justify="right", width=10)
        table.add_column("Live Hub", justify="right", width=10)
        table.add_column("Delta", justify="right", width=8)

        pre = report.pre_deploy_assessment
        pre_disruption = {
            ds.disruption_type.value: ds.score for ds in pre.disruption_scores
        }
        live_disruption = report.live_hub_assessment.get("disruptionResiliency", {})

        for dtype, delta_val in report.disruption_deltas.items():
            pre_val = pre_disruption.get(dtype, 0.0)
            live_val = float(live_disruption.get(dtype, {}).get("score", 0.0))
            d_color = "green" if abs(delta_val) <= 5 else ("yellow" if abs(delta_val) <= 10 else "red")
            table.add_row(
                dtype,
                f"{pre_val:.1f}",
                f"{live_val:.1f}",
                f"[{d_color}]{delta_val:+.1f}[/]",
            )

        console.print()
        console.print(table)

    # Missed risks
    if report.missed_risks:
        console.print("\n[bold yellow]Risks missed by FaultRay (found by Hub):[/]")
        for risk in report.missed_risks:
            console.print(f"  [yellow]-[/] {risk}")

    # Extra risks (FaultRay false positives)
    if report.extra_risks:
        console.print("\n[bold dim]Risks only in FaultRay (not found by Hub):[/]")
        for risk in report.extra_risks:
            console.print(f"  [dim]-[/] {risk}")

    console.print(f"\n[dim]{report.summary}[/]")


def _print_html_report(hub_output: dict) -> None:
    """Print a minimal HTML report of the Resilience Hub prediction."""
    score = hub_output["resiliencyScore"]
    status = hub_output["complianceStatus"]
    app_name = hub_output["appName"]

    if status == "MeetsPolicy":
        status_color = "#22c55e"
    elif status == "PolicyBreached":
        status_color = "#ef4444"
    else:
        status_color = "#6b7280"

    disruption_rows = ""
    for dtype, data in hub_output.get("disruptionResiliency", {}).items():
        d_score = data["score"]
        d_color = "#22c55e" if d_score >= 80 else ("#eab308" if d_score >= 60 else "#ef4444")
        disruption_rows += (
            f"<tr>"
            f"<td>{dtype}</td>"
            f"<td style='color:{d_color}'>{d_score:.1f}</td>"
            f"<td>{data['rtoInSecs'] // 60}m</td>"
            f"<td>{data['rpoInSecs'] // 60}m</td>"
            f"<td>{data['policyStatus']}</td>"
            f"</tr>\n"
        )

    rec_items = ""
    for rec in hub_output.get("recommendations", []):
        sev_colors = {"HIGH": "#ef4444", "MEDIUM": "#eab308", "LOW": "#6b7280"}
        sev_color = sev_colors.get(rec.get("severity", "LOW"), "#6b7280")
        rec_items += (
            f"<li><span style='color:{sev_color}'>[{rec.get('severity','LOW')}]</span> "
            f"[{rec.get('disruptionType','General')}] {rec.get('recommendation','')}</li>\n"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FaultRay Resilience Hub Prediction — {app_name}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ color: #1e40af; }}
  .score {{ font-size: 3rem; font-weight: bold; color: {status_color}; }}
  .status {{ font-size: 1.25rem; color: {status_color}; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 0.5rem 1rem; text-align: left; }}
  th {{ background: #f3f4f6; }}
  ul {{ line-height: 2; }}
</style>
</head>
<body>
<h1>FaultRay — AWS Resilience Hub Pre-Deploy Prediction</h1>
<p><strong>Application:</strong> {app_name}</p>
<p class="score">{score:.1f} / 100</p>
<p class="status">{status}</p>
<p><strong>Resources analyzed:</strong> {hub_output['resourceCount']}</p>

<h2>Disruption Resilience Breakdown</h2>
<table>
  <thead><tr><th>Disruption</th><th>Score</th><th>Est. RTO</th><th>Est. RPO</th><th>Status</th></tr></thead>
  <tbody>{disruption_rows}</tbody>
</table>

<h2>Recommendations</h2>
<ul>{rec_items}</ul>

<footer><small>Generated by FaultRay (Pre-Deploy AWS Resilience Hub Bridge)</small></footer>
</body>
</html>"""

    console.print(html)
