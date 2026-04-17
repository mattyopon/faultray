# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI commands for FaultRay APM agent management.

Provides: install, start, stop, status, agents, metrics, alerts subcommands.
"""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from faultray.cli.main import app, console

apm_app = typer.Typer(
    name="apm",
    help="APM agent — install, start, stop, and query application performance metrics",
    no_args_is_help=True,
)
app.add_typer(apm_app, name="apm")


# ---------------------------------------------------------------------------
# Agent lifecycle commands
# ---------------------------------------------------------------------------


@apm_app.command("install")
def apm_install(
    collector_url: str = typer.Option(
        "http://localhost:8080", "--collector", "-c", help="Collector server URL"
    ),
    api_key: str = typer.Option("", "--api-key", "-k", help="API key for auth"),
    config_dir: str = typer.Option(
        str(Path.home() / ".faultray"),
        "--config-dir",
        help="Directory for agent config",
    ),
    interval: int = typer.Option(15, "--interval", "-i", help="Collection interval (seconds)"),
) -> None:
    """Install the FaultRay APM agent configuration. / APMエージェント設定をインストール。

    Creates a YAML configuration file under ~/.faultray/agent.yaml with
    the specified collector URL, API key, and collection interval.

    APMエージェントの設定ファイルを ~/.faultray/agent.yaml に作成します。

    Examples:
        faultray apm install
        faultray apm install --collector http://faultray.internal:8080
        faultray apm install --api-key sk_xxxx --interval 30
        faultray apm install --config-dir /etc/faultray --interval 60

    See also:
        faultray apm start    — Start the agent after installing
        faultray apm status   — Check if the agent is running
        faultray apm setup    — Interactive guided setup wizard
    """
    import yaml

    from faultray.apm.models import AgentConfig

    config = AgentConfig(
        collector_url=collector_url,
        api_key=api_key,
        collect_interval_seconds=interval,
        pid_file=str(Path(config_dir) / "agent.pid"),
        log_file=str(Path(config_dir) / "agent.log"),
    )

    config_path = Path(config_dir) / "agent.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    console.print(f"[green]Agent configuration written to:[/] {config_path}")
    console.print(f"[dim]Agent ID: {config.agent_id}[/]")
    console.print(f"[dim]Collector: {collector_url}[/]")
    console.print(f"[dim]Interval: {interval}s[/]")
    console.print()
    console.print("[bold]Start the agent with:[/]")
    console.print(f"  faultray apm start --config {config_path}")


@apm_app.command("start")
def apm_start(
    config: str = typer.Option(
        str(Path.home() / ".faultray" / "agent.yaml"),
        "--config",
        "-f",
        help="Path to agent config YAML",
    ),
    foreground: bool = typer.Option(False, "--foreground", "-F", help="Run in foreground"),
) -> None:
    """Start the FaultRay APM agent. / APMエージェントを起動。

    By default starts as a background daemon. Use --foreground for debugging
    or when running inside a container / supervisor process.

    デフォルトはバックグラウンドデーモンとして起動します。
    デバッグ時やコンテナ内では --foreground を使用してください。

    Examples:
        faultray apm start
        faultray apm start --foreground
        faultray apm start --config /etc/faultray/agent.yaml
        faultray apm start --foreground --config ~/.faultray/agent.yaml

    See also:
        faultray apm install  — Create config before starting
        faultray apm stop     — Stop the running agent
        faultray apm status   — Check agent status
        faultray apm setup    — Interactive guided setup wizard
    """
    from faultray.apm.agent import APMAgent, load_agent_config

    agent_config = load_agent_config(config)

    # Check if already running
    pid_path = Path(agent_config.pid_file)
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            console.print(
                f"[yellow]Agent already running (PID {pid}). "
                f"Stop it first with: faultray apm stop[/]"
            )
            raise typer.Exit(1)
        except (OSError, ValueError):
            pid_path.unlink(missing_ok=True)

    agent = APMAgent(agent_config)

    if foreground:
        console.print(
            Panel(
                f"[bold green]FaultRay APM Agent[/]\n"
                f"ID: {agent_config.agent_id}\n"
                f"Collector: {agent_config.collector_url}\n"
                f"Interval: {agent_config.collect_interval_seconds}s\n"
                f"Press Ctrl+C to stop.",
                title="APM Agent",
            )
        )
        agent.start()
    else:
        # Fork to background
        console.print(f"[green]Starting APM agent (id={agent_config.agent_id})...[/]")
        try:
            pid = os.fork()
        except AttributeError:
            # Windows — run in foreground
            console.print("[yellow]Background mode not supported on this OS. Running in foreground.[/]")
            agent.start()
            return

        if pid > 0:
            console.print(f"[green]Agent started in background (PID {pid})[/]")
            return
        else:
            # Child process
            os.setsid()
            sys.stdin.close()
            agent.start()
            sys.exit(0)


@apm_app.command("stop")
def apm_stop(
    config: str = typer.Option(
        str(Path.home() / ".faultray" / "agent.yaml"),
        "--config",
        "-f",
        help="Path to agent config YAML",
    ),
) -> None:
    """Stop the running FaultRay APM agent. / 実行中のAPMエージェントを停止。

    Sends SIGTERM to the agent process and removes the PID file.
    If the agent is not running, a warning is shown.

    実行中のエージェントプロセスにSIGTERMを送信し、PIDファイルを削除します。

    Examples:
        faultray apm stop
        faultray apm stop --config /etc/faultray/agent.yaml

    See also:
        faultray apm start   — Start the agent
        faultray apm status  — Check if agent is running before stopping
    """
    import yaml

    config_path = Path(config)
    pid_file = str(Path.home() / ".faultray" / "agent.pid")

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        pid_file = data.get("pid_file", pid_file)

    pid_path = Path(pid_file)
    if not pid_path.exists():
        console.print("[yellow]No running agent found (PID file missing).[/]")
        raise typer.Exit(1)

    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Sent SIGTERM to agent (PID {pid})[/]")
        pid_path.unlink(missing_ok=True)
    except (OSError, ValueError) as e:
        console.print(f"[red]Could not stop agent: {e}[/]")
        pid_path.unlink(missing_ok=True)
        raise typer.Exit(1)


@apm_app.command("status")
def apm_status(
    config: str = typer.Option(
        str(Path.home() / ".faultray" / "agent.yaml"),
        "--config",
        "-f",
        help="Path to agent config YAML",
    ),
) -> None:
    """Show the status of the APM agent. / APMエージェントの状態を表示。

    Reads the PID file to determine if the agent is running and shows
    configuration details including agent ID, collector URL, and interval.

    PIDファイルを参照してエージェントの状態を確認し、
    エージェントID・コレクターURL・収集間隔などの設定を表示します。

    Examples:
        faultray apm status
        faultray apm status --config /etc/faultray/agent.yaml

    See also:
        faultray apm start   — Start the agent if not running
        faultray apm stop    — Stop the running agent
        faultray apm agents  — List all agents registered with the collector
    """
    import yaml

    config_path = Path(config)
    pid_file = str(Path.home() / ".faultray" / "agent.pid")

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        pid_file = data.get("pid_file", pid_file)

    pid_path = Path(pid_file)
    if not pid_path.exists():
        console.print("[yellow]Agent is not running (no PID file).[/]")
        return

    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, 0)
        console.print(f"[green]Agent is running (PID {pid})[/]")

        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            console.print(f"  Agent ID:  {data.get('agent_id', 'unknown')}")
            console.print(f"  Collector: {data.get('collector_url', 'unknown')}")
            console.print(f"  Interval:  {data.get('collect_interval_seconds', '?')}s")
    except (OSError, ValueError):
        console.print("[red]Agent PID file exists but process is not running.[/]")
        pid_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Query commands (talk to collector API)
# ---------------------------------------------------------------------------


@apm_app.command("agents")
def apm_list_agents(
    server: str = typer.Option("http://localhost:8080", "--server", "-s", help="FaultRay server URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List all registered APM agents. / 登録済みAPMエージェントを一覧表示。

    Queries the FaultRay collector for all known agents, showing their
    hostname, IP address, status, last seen timestamp, and OS info.

    FaultRayコレクターに登録されているすべてのエージェントを照会し、
    ホスト名・IPアドレス・状態・最終確認時刻・OS情報を表示します。

    Examples:
        faultray apm agents
        faultray apm agents --server http://faultray:8080
        faultray apm agents --json
        faultray apm agents --server http://faultray:8080 --json

    See also:
        faultray apm metrics <agent-id>  — View metrics for a specific agent
        faultray apm alerts              — View alerts across all agents
        faultray apm status              — Check local agent status
    """
    import httpx

    try:
        resp = httpx.get(f"{server}/api/apm/agents", timeout=10.0)
        agents = resp.json()
    except Exception as e:
        console.print(f"[red]Could not connect to server: {e}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data=agents)
        return

    if not agents:
        console.print("[yellow]No agents registered.[/]")
        return

    table = Table(title="Registered APM Agents", show_header=True)
    table.add_column("Agent ID", width=14)
    table.add_column("Hostname", width=20)
    table.add_column("IP", width=15)
    table.add_column("Status", width=10, justify="center")
    table.add_column("Last Seen", width=22)
    table.add_column("OS", width=20)

    for a in agents:
        status_style = "green" if a.get("status") == "running" else "red"
        table.add_row(
            a.get("agent_id", ""),
            a.get("hostname", ""),
            a.get("ip_address", ""),
            f"[{status_style}]{a.get('status', 'unknown')}[/]",
            a.get("last_seen", "")[:19],
            a.get("os_info", ""),
        )

    console.print(table)


@apm_app.command("metrics")
def apm_metrics(
    agent_id: str = typer.Argument(..., help="Agent ID to query"),
    metric: str = typer.Option(None, "--metric", "-m", help="Specific metric name"),
    server: str = typer.Option("http://localhost:8080", "--server", "-s", help="FaultRay server URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Query metrics for an APM agent. / APMエージェントのメトリクスを照会。

    Retrieves aggregated time-series metrics for the specified agent.
    Available metrics include cpu_percent, memory_percent, disk_percent,
    net_bytes_sent, net_bytes_recv, process_count, and tcp_connections.

    指定したエージェントの集計済み時系列メトリクスを取得します。
    利用可能なメトリクス: cpu_percent, memory_percent, disk_percent,
    net_bytes_sent, net_bytes_recv, process_count, tcp_connections

    Examples:
        faultray apm metrics agent123
        faultray apm metrics agent123 --metric cpu_percent
        faultray apm metrics agent123 --metric memory_percent --json
        faultray apm metrics agent123 --server http://faultray:8080

    See also:
        faultray apm agents   — List agent IDs first
        faultray apm alerts   — View threshold-based alerts
    """
    import httpx

    params: dict[str, str] = {}
    if metric:
        params["metric_name"] = metric

    try:
        resp = httpx.get(
            f"{server}/api/apm/agents/{agent_id}/metrics",
            params=params,
            timeout=10.0,
        )
        data = resp.json()
    except Exception as e:
        console.print(f"[red]Could not connect to server: {e}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data=data)
        return

    if not data:
        console.print(f"[yellow]No metrics found for agent {agent_id}.[/]")
        return

    table = Table(title=f"Metrics for {agent_id}", show_header=True)
    table.add_column("Metric", width=25)
    table.add_column("Value", width=15, justify="right")
    table.add_column("Samples", width=10, justify="right")
    table.add_column("Bucket", width=15)

    for d in data:
        table.add_row(
            d.get("metric_name", ""),
            f"{d.get('value', 0):.2f}",
            str(d.get("sample_count", 0)),
            str(d.get("bucket_epoch", "")),
        )

    console.print(table)


@apm_app.command("alerts")
def apm_alerts(
    agent_id: str = typer.Option(None, "--agent", "-a", help="Filter by agent ID"),
    severity: str = typer.Option(None, "--severity", help="Filter by severity"),
    server: str = typer.Option("http://localhost:8080", "--server", "-s", help="FaultRay server URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List APM alerts. / APMアラートを一覧表示。

    Shows threshold-based alerts fired by the APM anomaly detection engine.
    Alerts are classified as critical, warning, or info severity.

    APM異常検知エンジンが発火したしきい値ベースのアラートを表示します。
    アラートはcritical・warning・infoの3段階で分類されます。

    Examples:
        faultray apm alerts
        faultray apm alerts --severity critical
        faultray apm alerts --agent agent123
        faultray apm alerts --severity warning --json
        faultray apm alerts --server http://faultray:8080

    See also:
        faultray apm metrics <agent-id>  — View raw metrics for an agent
        faultray apm agents              — List all registered agents
    """
    import httpx

    params: dict[str, str] = {}
    if agent_id:
        params["agent_id"] = agent_id
    if severity:
        params["severity"] = severity

    try:
        resp = httpx.get(f"{server}/api/apm/alerts", params=params, timeout=10.0)
        data = resp.json()
    except Exception as e:
        console.print(f"[red]Could not connect to server: {e}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data=data)
        return

    if not data:
        console.print("[green]No alerts.[/]")
        return

    table = Table(title="APM Alerts", show_header=True)
    table.add_column("Severity", width=10, justify="center")
    table.add_column("Rule", width=18)
    table.add_column("Agent", width=14)
    table.add_column("Metric", width=18)
    table.add_column("Value", width=10, justify="right")
    table.add_column("Threshold", width=10, justify="right")
    table.add_column("Fired At", width=20)

    severity_colors = {"critical": "bold red", "warning": "yellow", "info": "blue"}

    for a in data:
        sev = a.get("severity", "info")
        color = severity_colors.get(sev, "white")
        table.add_row(
            f"[{color}]{sev.upper()}[/]",
            a.get("rule_name", ""),
            a.get("agent_id", ""),
            a.get("metric_name", ""),
            f"{a.get('metric_value', 0):.1f}",
            f"{a.get('threshold', 0):.1f}",
            a.get("fired_at", "")[:19],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Onboarding commands
# ---------------------------------------------------------------------------


@apm_app.command("report")
def apm_report(
    config: str = typer.Option(
        str(Path.home() / ".faultray" / "agent.yaml"),
        "--config",
        "-f",
        help="Path to agent config YAML (used to locate the report directory)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON"),
) -> None:
    """Show the latest auto-discovery simulation report. / 自動シミュレーションレポートを表示。

    Reads the most recent report written by the agent's discovery loop from
    ``~/.faultray/auto-report.json`` (or the directory derived from the agent
    config PID file location) and renders it as a Rich table.

    エージェントの自動検出ループが書き込んだ最新レポートを読み込み、
    Rich テーブルとして表示します。

    Examples:
        faultray apm report
        faultray apm report --json
        faultray apm report --config /etc/faultray/agent.yaml

    See also:
        faultray apm start   — Start the agent (generates reports periodically)
        faultray apm status  — Check if agent is running
    """
    import yaml

    # Determine report path from config
    config_path = Path(config)
    pid_file = str(Path.home() / ".faultray" / "agent.pid")

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        pid_file = data.get("pid_file", pid_file)

    report_path = Path(pid_file).parent / "auto-report.json"

    if not report_path.exists():
        console.print(
            f"[yellow]No simulation report found at {report_path}.[/]\n"
            "Start the agent and wait for the first discovery cycle to complete."
        )
        raise typer.Exit(1)

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        console.print(f"[red]Failed to read report: {exc}[/]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(data=report)
        return

    # Summary panel
    score = report.get("score", 0)
    avail = report.get("availability_estimate", "unknown")
    ts = report.get("timestamp", "")[:19]
    score_color = "green" if score >= 80 else ("yellow" if score >= 50 else "red")

    console.print(
        Panel(
            f"[bold]Resilience Score:[/] [{score_color}]{score}/100[/]\n"
            f"[bold]Availability Estimate:[/] {avail}\n"
            f"[bold]Components Analyzed:[/] {report.get('components_analyzed', 0)}\n"
            f"[bold]Dependencies Analyzed:[/] {report.get('dependencies_analyzed', 0)}\n"
            f"[bold]Total Scenarios:[/] {report.get('total_scenarios', 0)}\n"
            f"[bold]Critical:[/] [red]{report.get('critical_count', 0)}[/]   "
            f"[bold]Warning:[/] [yellow]{report.get('warning_count', 0)}[/]\n"
            f"[dim]Generated: {ts}[/]",
            title="Auto-Simulation Report",
            border_style=score_color,
        )
    )

    # SPOFs table
    spofs = report.get("spofs", [])
    if spofs:
        spof_table = Table(title="Single Points of Failure", show_header=True)
        spof_table.add_column("Component ID", style="red")
        spof_table.add_column("Name")
        spof_table.add_column("Type")
        spof_table.add_column("Replicas", justify="right")
        spof_table.add_column("Dependents", justify="right")
        for s in spofs:
            spof_table.add_row(
                s.get("id", ""),
                s.get("name", ""),
                s.get("type", ""),
                str(s.get("replicas", 1)),
                str(len(s.get("dependents", []))),
            )
        console.print(spof_table)
    else:
        console.print("[green]No single points of failure detected.[/]")

    # Top risks table
    top_risks = report.get("top_risks", [])
    if top_risks:
        risk_table = Table(title="Top Risk Scenarios", show_header=True)
        risk_table.add_column("Scenario", width=35)
        risk_table.add_column("Risk Score", justify="right")
        risk_table.add_column("Critical", justify="center")
        for r in top_risks:
            critical_flag = "[red]YES[/]" if r.get("is_critical") else "[dim]no[/]"
            risk_table.add_row(
                r.get("scenario_name", ""),
                f"{r.get('risk_score', 0):.2f}",
                critical_flag,
            )
        console.print(risk_table)

    # Recommendations
    recs = report.get("recommendations", [])
    if recs:
        console.print("\n[bold cyan]Recommendations:[/]")
        for i, rec in enumerate(recs, 1):
            console.print(f"  {i}. {rec}")


@apm_app.command("setup")
def apm_setup() -> None:
    """Interactive APM setup wizard — the easiest way to get started. / APMセットアップウィザード。

    Walks you through the complete APM onboarding experience:
    server configuration, agent installation, startup, and verification.

    APMのオンボーディングを対話的にガイドします:
    サーバー設定・エージェントインストール・起動・動作確認。

    Examples:
        faultray apm setup

    See also:
        faultray apm install  — Non-interactive install
        faultray apm start    — Start the agent directly
        faultray apm help     — Architecture overview and all commands
    """
    from rich.prompt import Prompt

    # Welcome panel
    console.print()
    console.print(
        Panel(
            "[bold cyan]FaultRay APM Setup Wizard[/]\n"
            "[dim]Real-time metrics, anomaly detection, topology auto-discovery\n"
            "リアルタイムメトリクス・異常検知・トポロジー自動検出[/]\n\n"
            "This wizard will guide you through:\n"
            "  [cyan]Step 1[/]  Configure collector server\n"
            "  [cyan]Step 2[/]  Set collection interval\n"
            "  [cyan]Step 3[/]  Install agent configuration\n"
            "  [cyan]Step 4[/]  Start the agent\n"
            "  [cyan]Step 5[/]  What's next",
            border_style="cyan",
            title="📡 APM Setup",
        )
    )

    # Step 1: Server configuration
    console.print("\n[bold cyan]Step 1 / ステップ1[/] — Configure Collector Server / コレクターサーバー設定\n")
    console.print(
        "[dim]The collector server receives metrics from all your APM agents.\n"
        "コレクターサーバーはすべてのAPMエージェントからメトリクスを受信します。[/]\n"
    )

    collector_url = Prompt.ask(
        "Collector URL / コレクターURL",
        default="http://localhost:8080",
    )
    api_key = Prompt.ask(
        "API key (optional, press Enter to skip) / APIキー（任意）",
        default="",
    )

    # Step 2: Collection interval
    console.print("\n[bold cyan]Step 2 / ステップ2[/] — Collection Interval / 収集間隔\n")

    metrics_table = Table(show_header=True, header_style="bold cyan")
    metrics_table.add_column("Metric / メトリクス", width=22)
    metrics_table.add_column("Description / 説明", width=44)
    metrics_table.add_row("cpu_percent",     "CPU utilization across all cores / 全コアのCPU使用率")
    metrics_table.add_row("memory_percent",  "RAM usage (used / total) / RAM使用率")
    metrics_table.add_row("disk_percent",    "Root disk usage / ルートディスク使用率")
    metrics_table.add_row("net_bytes_sent",  "Network bytes sent / ネットワーク送信バイト数")
    metrics_table.add_row("net_bytes_recv",  "Network bytes received / ネットワーク受信バイト数")
    metrics_table.add_row("process_count",   "Number of running processes / 実行中プロセス数")
    metrics_table.add_row("tcp_connections", "Active TCP connections / アクティブTCP接続数")
    console.print(metrics_table)
    console.print()

    interval_str = Prompt.ask(
        "Collection interval in seconds (15–300) / 収集間隔（15〜300秒）",
        default="15",
    )
    try:
        interval = max(5, min(300, int(interval_str)))
    except ValueError:
        interval = 15
        console.print("[yellow]Invalid value, using default: 15s[/]")

    # Step 3: Install configuration
    console.print("\n[bold cyan]Step 3 / ステップ3[/] — Install Configuration / 設定をインストール\n")
    import yaml as _yaml

    from faultray.apm.models import AgentConfig

    config_dir_path = Path.home() / ".faultray"
    config = AgentConfig(
        collector_url=collector_url,
        api_key=api_key,
        collect_interval_seconds=interval,
        pid_file=str(config_dir_path / "agent.pid"),
        log_file=str(config_dir_path / "agent.log"),
    )

    config_path = config_dir_path / "agent.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    console.print(f"[green]Configuration written to:[/] {config_path}")
    console.print(f"[dim]  Agent ID:  {config.agent_id}[/]")
    console.print(f"[dim]  Collector: {collector_url}[/]")
    console.print(f"[dim]  Interval:  {interval}s[/]")

    # Step 4: Start agent
    console.print("\n[bold cyan]Step 4 / ステップ4[/] — Start Agent / エージェント起動\n")

    start_mode = Prompt.ask(
        "How would you like to start the agent? / 起動方法を選択してください\n"
        "  [cyan]1[/] Background daemon (recommended) / バックグラウンドデーモン（推奨）\n"
        "  [cyan]2[/] Foreground (for debugging) / フォアグラウンド（デバッグ用）\n"
        "  [cyan]3[/] Skip for now / 今はスキップ\n"
        "Choice / 選択",
        choices=["1", "2", "3"],
        default="1",
    )

    if start_mode in ("1", "2"):
        foreground = start_mode == "2"
        console.print()
        try:
            apm_start(config=str(config_path), foreground=foreground)
        except SystemExit:
            pass
        except Exception as exc:
            console.print(f"[yellow]Could not start agent automatically: {exc}[/]")
            console.print(f"[dim]Start manually with: faultray apm start --config {config_path}[/]")
    else:
        console.print(
            f"[dim]Start later with: faultray apm start --config {config_path}[/]"
        )

    # Step 5: What's next
    console.print()
    console.print(
        Panel(
            "[bold green]Setup complete! / セットアップ完了！[/]\n\n"
            "[bold]Useful commands / よく使うコマンド:[/]\n\n"
            f"  [cyan]faultray apm status[/]               Check if agent is running\n"
            f"  [cyan]faultray apm agents[/]               List registered agents\n"
            f"  [cyan]faultray apm metrics {config.agent_id[:8]}...[/]  View metrics\n"
            f"  [cyan]faultray apm alerts[/]               View anomaly alerts\n"
            f"  [cyan]faultray apm stop[/]                 Stop the agent\n\n"
            "[bold]Web Dashboard / Webダッシュボード:[/]\n"
            "  [cyan]faultray serve[/]  →  http://localhost:8080/apm\n\n"
            "[bold]Docs / ドキュメント:[/]\n"
            "  [cyan]faultray apm help[/]                  Architecture & all commands\n"
            "  [cyan]docs/guides/apm-quickstart.md[/]      Full quickstart guide",
            border_style="green",
            title="Step 5: What's Next",
        )
    )


@apm_app.command("help")
def apm_help() -> None:
    """Show detailed APM help with architecture overview and all commands. / APM詳細ヘルプ。

    Displays the APM architecture diagram, all available subcommands with
    examples, common workflows, and troubleshooting tips.

    APMのアーキテクチャ図・全サブコマンド・典型的なワークフロー・
    トラブルシューティングのヒントを表示します。

    Examples:
        faultray apm help

    See also:
        faultray apm setup   — Interactive guided setup wizard
        faultray apm --help  — Typer built-in help (subcommand list only)
    """
    # Architecture diagram
    console.print()
    console.print(
        Panel(
            "[bold cyan]FaultRay APM Architecture[/]\n\n"
            "  ┌─────────────────────────────────────────────────────┐\n"
            "  │  Your Hosts / あなたのサーバー                        │\n"
            "  │                                                      │\n"
            "  │  ┌───────────┐    ┌───────────┐    ┌───────────┐   │\n"
            "  │  │ APM Agent │    │ APM Agent │    │ APM Agent │   │\n"
            "  │  │  (host-1) │    │  (host-2) │    │  (host-3) │   │\n"
            "  │  └─────┬─────┘    └─────┬─────┘    └─────┬─────┘   │\n"
            "  └────────┼────────────────┼────────────────┼──────────┘\n"
            "           │ metrics (HTTP) │                │\n"
            "           └────────────────┼────────────────┘\n"
            "                           ▼\n"
            "               ┌─────────────────────┐\n"
            "               │  FaultRay Collector  │\n"
            "               │  faultray serve      │\n"
            "               └──────────┬──────────┘\n"
            "                          │\n"
            "              ┌───────────┴───────────┐\n"
            "              │                       │\n"
            "              ▼                       ▼\n"
            "    ┌─────────────────┐    ┌─────────────────────┐\n"
            "    │  Time-Series DB │    │  Anomaly Detection  │\n"
            "    │  (SQLite/PG)    │    │  (Z-score + rules)  │\n"
            "    └─────────────────┘    └─────────────────────┘\n"
            "              │\n"
            "              ▼\n"
            "    ┌─────────────────────────┐\n"
            "    │  Web Dashboard / API    │\n"
            "    │  http://localhost:8080  │\n"
            "    └─────────────────────────┘",
            border_style="cyan",
            title="📡 APM Architecture",
        )
    )

    # All commands table
    console.print("\n[bold cyan]All APM Commands / 全APMコマンド[/]\n")

    cmd_table = Table(show_header=True, header_style="bold cyan")
    cmd_table.add_column("Command / コマンド", style="cyan", width=38)
    cmd_table.add_column("Description / 説明", width=46)

    cmd_rows = [
        ("faultray apm setup",                 "Interactive setup wizard / 対話的セットアップウィザード"),
        ("faultray apm install",               "Install agent config / 設定ファイルを作成"),
        ("faultray apm install -c <url>",      "Install with custom collector URL"),
        ("faultray apm install -k <key>",      "Install with API key authentication"),
        ("faultray apm install -i <secs>",     "Set collection interval (default 15s)"),
        ("faultray apm start",                 "Start agent (background) / バックグラウンド起動"),
        ("faultray apm start --foreground",    "Start agent (foreground) / フォアグラウンド起動"),
        ("faultray apm stop",                  "Stop agent / エージェント停止"),
        ("faultray apm status",                "Show agent status / 状態確認"),
        ("faultray apm agents",                "List all registered agents / エージェント一覧"),
        ("faultray apm agents --json",         "JSON output / JSON形式で出力"),
        ("faultray apm metrics <agent-id>",    "Query metrics / メトリクス照会"),
        ("faultray apm metrics <id> -m cpu",   "Query specific metric / 特定メトリクス照会"),
        ("faultray apm alerts",                "List all alerts / 全アラート一覧"),
        ("faultray apm alerts --severity critical", "Filter by severity / 深刻度でフィルタ"),
        ("faultray apm alerts --agent <id>",   "Filter by agent / エージェントでフィルタ"),
        ("faultray apm help",                  "This help screen / このヘルプ画面"),
    ]
    for cmd, desc in cmd_rows:
        cmd_table.add_row(cmd, desc)
    console.print(cmd_table)

    # Common workflows
    console.print("\n[bold cyan]Common Workflows / 典型的なワークフロー[/]\n")

    console.print("[bold]1. First-time setup / 初回セットアップ[/]")
    console.print("   [cyan]faultray apm setup[/]                    # Interactive wizard")
    console.print("   [cyan]faultray apm status[/]                   # Verify running")
    console.print()

    console.print("[bold]2. Manual setup / 手動セットアップ[/]")
    console.print("   [cyan]faultray apm install --collector http://faultray:8080[/]")
    console.print("   [cyan]faultray apm start[/]")
    console.print("   [cyan]faultray apm status[/]")
    console.print()

    console.print("[bold]3. Monitoring / 監視[/]")
    console.print("   [cyan]faultray apm agents[/]                   # List all agents")
    console.print("   [cyan]faultray apm metrics <agent-id>[/]       # View metrics")
    console.print("   [cyan]faultray apm alerts --severity critical[/]  # Check alerts")
    console.print()

    console.print("[bold]4. Chaos + APM integration / カオスシミュレーションとの統合[/]")
    console.print("   [cyan]faultray simulate infra.yaml[/]          # Run simulation")
    console.print("   [cyan]faultray apm metrics <id> --json[/]      # Capture real baseline")
    console.print("   [cyan]faultray analyze infra.yaml[/]           # AI-powered analysis")
    console.print()

    # Troubleshooting
    console.print("\n[bold cyan]Troubleshooting / トラブルシューティング[/]\n")

    trouble_table = Table(show_header=True, header_style="bold yellow")
    trouble_table.add_column("Problem / 問題", width=34)
    trouble_table.add_column("Solution / 解決策", width=48)

    trouble_rows = [
        ("Agent won't start",           "Check: faultray apm status  |  rm ~/.faultray/agent.pid"),
        ("Already running error",       "Stop first: faultray apm stop  then restart"),
        ("No metrics in dashboard",     "Verify collector URL matches: faultray apm status"),
        ("Connection refused",          "Ensure faultray serve is running on collector host"),
        ("Permission denied on PID",    "rm ~/.faultray/agent.pid  then retry"),
        ("High CPU from agent",         "Increase interval: faultray apm install -i 60"),
        ("Agent exits immediately",     "Use --foreground to see error output"),
        ("エージェントが起動しない",        "faultray apm status を確認、agent.pid を削除して再試行"),
    ]
    for prob, sol in trouble_rows:
        trouble_table.add_row(prob, sol)
    console.print(trouble_table)

    console.print(
        "\n[dim]Full documentation: [cyan]docs/guides/apm-quickstart.md[/][/]"
        "\n[dim]CLI reference:      [cyan]docs/cli/apm-commands.md[/][/]"
        "\n[dim]GitHub:             [cyan]https://github.com/mattyopon/faultray[/][/]\n"
    )
