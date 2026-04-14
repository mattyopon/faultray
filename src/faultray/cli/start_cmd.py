# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Interactive wizard — the best way to start with FaultRay (faultray start)."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from faultray.cli.main import app, console


# ---------------------------------------------------------------------------
# Choice handlers
# ---------------------------------------------------------------------------

def _handle_quick_demo(con: Console) -> None:
    """Choice 1: Quick Demo — run the built-in demo simulation."""
    con.print("\n[bold cyan]Running Quick Demo...[/]")
    con.print("[dim]Building demo infrastructure and running chaos simulation.[/]\n")

    try:
        from faultray.model.demo import create_demo_graph
        from faultray.simulator.engine import SimulationEngine
        from faultray.reporter.report import print_infrastructure_summary, print_simulation_report

        graph = create_demo_graph()
        print_infrastructure_summary(graph, con)

        con.print("\n[cyan]Running chaos simulation...[/]")
        engine = SimulationEngine(graph)
        report = engine.run_all_defaults()
        print_simulation_report(report, con, graph=graph)

        con.print("\n[bold green]Demo complete! / デモ完了！[/]\n")
        con.print("[bold]Next steps / 次のステップ:[/]")
        con.print("  [cyan]faultray scan --aws[/]       — Scan your real AWS infrastructure / 本番AWSをスキャン")
        con.print("  [cyan]faultray dora-assess[/]      — Check DORA compliance / DORA準拠チェック")
        con.print("  [cyan]faultray serve[/]             — Open web dashboard / Webダッシュボードを起動")
        con.print("  [cyan]faultray start[/]             — Back to this menu / このメニューに戻る")
    except Exception as exc:
        con.print(f"[red]Demo failed: {exc}[/]")
        con.print("[dim]Try: faultray demo[/]")


def _handle_scan_infrastructure(con: Console) -> None:
    """Choice 2: Scan My Infrastructure — provider selection sub-menu."""
    con.print("\n[bold]Select your cloud provider / クラウドプロバイダーを選択:[/]\n")

    providers = Table(show_header=False, box=None, padding=(0, 2))
    providers.add_row("[cyan][1][/]", "☁️ ", "[bold]AWS[/]", "[dim]Amazon Web Services[/]")
    providers.add_row("[cyan][2][/]", "🔷", "[bold]Google Cloud[/]", "[dim]GCP — Google Cloud Platform[/]")
    providers.add_row("[cyan][3][/]", "🔶", "[bold]Azure[/]", "[dim]Microsoft Azure[/]")
    providers.add_row("[cyan][4][/]", "🌸", "[bold]Sakura Cloud[/]", "[dim]さくらのクラウド[/]")
    providers.add_row("[cyan][5][/]", "🐉", "[bold]Alibaba Cloud[/]", "[dim]Aliyun — 阿里云[/]")
    providers.add_row("[cyan][6][/]", "🔴", "[bold]Oracle Cloud[/]", "[dim]OCI — Oracle Cloud Infrastructure[/]")
    providers.add_row("[cyan][7][/]", "🖥️ ", "[bold]On-Premises[/]", "[dim]CSV / NetBox / nmap XML[/]")
    providers.add_row("[cyan][8][/]", "🔄", "[bold]Multi-Cloud[/]", "[dim]複数クラウドを同時スキャン[/]")
    con.print(providers)

    provider_choice = Prompt.ask(
        "\n[bold]Choose provider / プロバイダーを選択[/]",
        choices=["1", "2", "3", "4", "5", "6", "7", "8"],
        default="1",
    )

    provider_map = {
        "1": ("AWS", "faultray scan --aws"),
        "2": ("Google Cloud", "faultray scan --gcp"),
        "3": ("Azure", "faultray scan --azure"),
        "4": ("Sakura Cloud", "faultray scan --sakura --token YOUR_TOKEN --secret YOUR_SECRET"),
        "5": ("Alibaba Cloud", "faultray scan --alibaba --access-key YOUR_KEY --access-secret YOUR_SECRET"),
        "6": ("Oracle Cloud", "faultray scan --oci --compartment YOUR_COMPARTMENT_OCID"),
        "7": ("On-Premises", "faultray scan --onprem"),
        "8": ("Multi-Cloud", "faultray scan --multi --aws --gcp"),
    }

    label, cmd = provider_map[provider_choice]

    con.print(f"\n[bold green]Selected:[/] {label}")
    con.print("\nRun the following command to start scanning:\n")
    con.print(Panel(f"[bold cyan]{cmd}[/]", border_style="cyan", title="Scan Command / スキャンコマンド"))

    # For AWS, attempt direct invocation if boto3 is available
    if provider_choice == "1":
        try:
            import boto3  # noqa: F401
        except ImportError:
            con.print("\n[yellow]boto3 not installed. Install with: pip install boto3[/]")
            return

        region = Prompt.ask("AWS region / リージョン", default="ap-northeast-1")
        profile = Prompt.ask("AWS profile (leave blank for default) / AWSプロファイル", default="")

        con.print(f"\n[cyan]Scanning AWS ({region})...[/]")
        try:
            from faultray.cli.discovery import scan as _scan
            import click

            # Build CLI args and invoke via Click context
            args: list[str] = ["--aws", "--region", region]
            if profile:
                args += ["--profile", profile]
            ctx = click.Context(click.Command("scan"))
            with ctx:
                _scan(
                    output=Path("faultray-model.json"),
                    hostname=None,
                    prometheus_url=None,
                    aws=True,
                    gcp=False,
                    azure=False,
                    k8s=False,
                    sakura=False,
                    alibaba=False,
                    oci=False,
                    onprem=False,
                    multi=False,
                    region=region,
                    profile=profile or None,
                    project=None,
                    subscription=None,
                    resource_group=None,
                    context=None,
                    namespace=None,
                    sakura_token=None,
                    sakura_secret=None,
                    sakura_zone="tk1v",
                    alibaba_access_key=None,
                    alibaba_access_secret=None,
                    alibaba_vpc=None,
                    oci_compartment=None,
                    oci_config_file=None,
                    oci_profile="DEFAULT",
                    netbox_url=None,
                    netbox_token=None,
                    cmdb=None,
                    nmap_xml=None,
                    onprem_region="onprem",
                    save_yaml=None,
                    infer_hidden=False,
                    infer_confidence=0.7,
                )
        except Exception as exc:
            con.print(f"[red]Scan error: {exc}[/]")
            con.print(f"[dim]Try running manually: faultray scan --aws --region {region}[/]")
    else:
        con.print(f"\n[dim]Copy and run the command above to scan {label} infrastructure.[/]")


def _handle_dora_compliance(con: Console) -> None:
    """Choice 3: DORA Compliance Report."""
    model_path = Path("faultray-model.json")
    yaml_candidates = list(Path.cwd().glob("*.yaml")) + list(Path.cwd().glob("*.yml"))

    has_model = model_path.exists()
    has_yaml = bool(yaml_candidates)

    if not has_model and not has_yaml:
        con.print(
            "\n[yellow]No infrastructure model found / インフラモデルが見つかりません[/]\n\n"
            "To generate a DORA compliance report, first create a model:\n\n"
            "  [cyan]faultray demo[/]            — Use demo infrastructure / デモインフラを使う\n"
            "  [cyan]faultray scan --aws[/]      — Scan AWS / AWSをスキャン\n"
            "  [cyan]faultray quickstart[/]      — Generate from template / テンプレートから生成\n"
            "  [cyan]faultray init[/]             — Interactive YAML builder / 対話的YAML作成\n"
        )
        return

    if has_yaml and not has_model:
        yaml_file = yaml_candidates[0]
        con.print(f"\n[cyan]Found YAML model: {yaml_file}[/]")
    else:
        yaml_file = None

    con.print("\n[cyan]Running DORA compliance assessment...[/]\n")
    try:
        from faultray.cli.dora_cmd import dora_assess

        target_yaml = yaml_file or (yaml_candidates[0] if yaml_candidates else None)
        dora_assess(
            yaml_file=target_yaml,
            model=model_path,
            report=None,
            html=None,
            threshold=70,
            json_output=False,
        )

        con.print("\n[bold]To generate a full PDF/HTML report:[/]")
        con.print("  [cyan]faultray dora-assess --html dora-report.html[/]")
        con.print("  [cyan]faultray dora-report[/]")
    except Exception as exc:
        con.print(f"[red]DORA assessment failed: {exc}[/]")
        con.print("[dim]Try: faultray dora-assess[/]")


def _handle_import_terraform(con: Console) -> None:
    """Choice 4: Import Terraform plan/state."""
    con.print("\n[bold]Import Terraform / Terraformインポート[/]\n")
    con.print(
        "FaultRay can parse your Terraform plan JSON or state file\n"
        "to automatically build an infrastructure model.\n"
    )

    path_str = Prompt.ask(
        "Terraform plan JSON path / Terraformプランのパス\n"
        "[dim](e.g. terraform.tfplan.json, terraform.tfstate)[/]",
        default="terraform.tfplan.json",
    )
    tf_path = Path(path_str)

    if not tf_path.exists():
        con.print(
            f"\n[yellow]File not found: {tf_path}[/]\n\n"
            "To generate a Terraform plan JSON, run:\n"
            "  [cyan]terraform plan -out=tfplan[/]\n"
            "  [cyan]terraform show -json tfplan > terraform.tfplan.json[/]\n\n"
            "Then run:\n"
            f"  [cyan]faultray tf-check {tf_path}[/]\n"
        )
        return

    con.print(f"\n[cyan]Importing Terraform plan: {tf_path}[/]\n")
    try:
        from faultray.cli.tf_check import tf_check

        tf_check(
            plan_file=tf_path,
            output=Path("faultray-model.json"),
            save_yaml=None,
            json_output=False,
        )
        con.print("\n[bold green]Import complete![/]")
        con.print("Model saved to [cyan]faultray-model.json[/]")
        con.print("Run [cyan]faultray simulate[/] to analyze your infrastructure.")
    except Exception as exc:
        con.print(f"[red]Import failed: {exc}[/]")
        con.print(f"[dim]Try: faultray tf-check {tf_path}[/]")


def _handle_write_yaml(con: Console) -> None:
    """Choice 5: Write YAML — guided infrastructure definition."""
    con.print("\n[bold]Write YAML / YAMLを作成[/]\n")
    con.print(
        "Choose how you want to define your infrastructure:\n"
    )

    sub = Table(show_header=False, box=None, padding=(0, 2))
    sub.add_row("[cyan][1][/]", "🏗️ ", "[bold]Interactive Wizard[/]", "[dim]対話的ウィザード (faultray init)[/]")
    sub.add_row("[cyan][2][/]", "📄", "[bold]From Template[/]", "[dim]テンプレートから生成 (faultray quickstart)[/]")
    con.print(sub)

    sub_choice = Prompt.ask("\n[bold]Choose / 選択[/]", choices=["1", "2"], default="1")

    if sub_choice == "1":
        con.print("\n[cyan]Starting interactive YAML wizard...[/]\n")
        try:
            from faultray.cli.init_cmd import init as _init
            _init(output=Path("infra.yaml"))
        except Exception as exc:
            con.print(f"[red]Wizard failed: {exc}[/]")
            con.print("[dim]Try: faultray init[/]")
    else:
        con.print("\n[cyan]Starting quickstart template wizard...[/]\n")
        try:
            from faultray.cli.quickstart import quickstart as _quickstart
            _quickstart(output=Path("infra.yaml"), template="", run_sim=True, web=False)
        except Exception as exc:
            con.print(f"[red]Quickstart failed: {exc}[/]")
            con.print("[dim]Try: faultray quickstart[/]")


def _handle_open_dashboard(con: Console) -> None:
    """Choice 6: Open Dashboard — launch web UI."""
    host = "127.0.0.1"
    port = 8080
    url = f"http://{host}:{port}"

    con.print(f"\n[cyan]Starting FaultRay Web Dashboard at [bold]{url}[/]...[/]")
    con.print("[dim]Press Ctrl+C to stop / 停止するには Ctrl+C[/]\n")

    try:
        import uvicorn
    except ImportError:
        con.print("[yellow]uvicorn not installed. Install with: pip install uvicorn[/]")
        con.print("[dim]Then run: faultray serve[/]")
        return

    try:
        import webbrowser
        import threading

        model_path = Path("faultray-model.json")
        from faultray.api.server import set_graph
        from faultray.model.graph import InfraGraph

        if model_path.exists():
            graph = InfraGraph.load(model_path)
            set_graph(graph)
            con.print(f"[green]Model loaded: {model_path}[/]")
        else:
            # Load demo data so the dashboard is functional immediately
            from faultray.model.demo import create_demo_graph
            demo_graph = create_demo_graph()
            set_graph(demo_graph)
            con.print("[yellow]No model file found — loading demo data.[/]")
            con.print("[dim]Scan your infrastructure with: faultray scan --aws[/]")

        # Open browser slightly after server starts
        def _open_browser() -> None:
            import time
            time.sleep(1.5)
            webbrowser.open(url)

        browser_thread = threading.Thread(target=_open_browser, daemon=True)
        browser_thread.start()

        uvicorn.run("faultray.api.server:app", host=host, port=port, log_level="info")
    except Exception as exc:
        con.print(f"[red]Dashboard failed to start: {exc}[/]")
        con.print("[dim]Try: faultray serve[/]")


def _handle_apm_monitoring(con: Console) -> None:
    """Choice 7: APM Monitoring — setup and status sub-menu."""
    con.print(
        Panel(
            "[bold cyan]APM Monitoring[/]\n"
            "[dim]Install once, monitor forever — real-time metrics, anomaly detection, topology auto-discovery\n"
            "一度インストールするだけで永続監視 — リアルタイムメトリクス・異常検知・トポロジー自動検出[/]",
            border_style="cyan",
            title="📡 APM Agent",
        )
    )

    con.print("\n[bold]APM Options / APMオプション:[/]\n")
    sub = Table(show_header=False, box=None, padding=(0, 2))
    sub.add_row("[cyan][1][/]", "⚡", "[bold]Quick Setup[/]",    "[dim]APMエージェントをインストール・起動 / Install and start agent[/]")
    sub.add_row("[cyan][2][/]", "📈", "[bold]Check Status[/]",   "[dim]エージェント状態・メトリクス確認 / View agent status and metrics[/]")
    sub.add_row("[cyan][3][/]", "🌐", "[bold]View Dashboard[/]", "[dim]WebUI でAPMを確認する方法 / How to access APM in web UI[/]")
    con.print(sub)

    apm_choice = Prompt.ask(
        "\n[bold]Choose / 選択[/]",
        choices=["1", "2", "3"],
        default="1",
    )

    if apm_choice == "1":
        # Quick Setup
        con.print("\n[bold cyan]APM Quick Setup / クイックセットアップ[/]\n")
        con.print("[dim]This will create an agent configuration and optionally start monitoring.[/]\n")

        collector_url = Prompt.ask(
            "Collector URL / コレクターURL",
            default="http://localhost:8080",
        )
        api_key = Prompt.ask(
            "API key (optional, press Enter to skip) / APIキー（任意）",
            default="",
        )
        interval_str = Prompt.ask(
            "Collection interval in seconds / 収集間隔（秒）",
            default="15",
        )
        try:
            interval = int(interval_str)
        except ValueError:
            interval = 15

        con.print("\n[cyan]Installing APM agent configuration...[/]")
        try:
            from faultray.cli.apm_cmd import apm_install
            apm_install(
                collector_url=collector_url,
                api_key=api_key,
                config_dir=str(Path.home() / ".faultray"),
                interval=interval,
            )
            con.print("\n[bold green]Configuration installed![/]")
        except Exception as exc:
            con.print(f"[red]Install failed: {exc}[/]")
            con.print("[dim]Try: faultray apm install[/]")
            return

        start_now = Prompt.ask(
            "\nStart agent now? / 今すぐ起動しますか？",
            choices=["y", "n"],
            default="y",
        )
        if start_now == "y":
            con.print("\n[cyan]Starting APM agent in background...[/]")
            con.print("[dim]Run [cyan]faultray apm status[/dim] to verify.[/]")
            con.print("[dim]Run [cyan]faultray apm stop[/dim] to stop the agent.[/]")
            con.print("\n[bold]Or use the interactive wizard:[/]")
            con.print("  [cyan]faultray apm setup[/]")

        con.print("\n[bold]Next steps / 次のステップ:[/]")
        con.print("  [cyan]faultray apm status[/]           — Check agent status / 状態確認")
        con.print("  [cyan]faultray apm agents[/]           — List all registered agents / エージェント一覧")
        con.print("  [cyan]faultray apm metrics <id>[/]     — View metrics / メトリクス確認")
        con.print("  [cyan]faultray apm alerts[/]           — View alerts / アラート確認")
        con.print("  [cyan]faultray apm setup[/]            — Full interactive wizard / 詳細ウィザード")

    elif apm_choice == "2":
        # Check Status
        con.print("\n[bold]APM Agent Status / APMエージェント状態[/]\n")
        try:
            from faultray.cli.apm_cmd import apm_status
            apm_status(config=str(Path.home() / ".faultray" / "agent.yaml"))
        except Exception as exc:
            con.print(f"[yellow]Could not retrieve status: {exc}[/]")

        con.print("\n[dim]Recent metrics require a running collector.[/]")
        con.print("[dim]Run [cyan]faultray apm agents[/dim] to list registered agents.[/]")
        con.print("[dim]Run [cyan]faultray apm metrics <agent-id>[/dim] to view metrics.[/]")

    else:
        # View Dashboard
        con.print(
            Panel(
                "[bold]Access APM in the Web Dashboard / WebダッシュボードでAPMを確認[/]\n\n"
                "1. Start the dashboard:\n"
                "   [cyan]faultray serve[/]\n\n"
                "2. Open your browser to:\n"
                "   [cyan]http://localhost:8080[/]\n\n"
                "3. Navigate to the [bold]APM[/bold] section in the sidebar\n\n"
                "4. Or go directly to:\n"
                "   [cyan]http://localhost:8080/apm[/]\n\n"
                "[dim]The APM dashboard shows real-time metrics, agent topology,\n"
                "anomaly alerts, and historical trends for all connected agents.[/]",
                border_style="cyan",
                title="APM Dashboard",
            )
        )


def _handle_all_commands(con: Console) -> None:
    """Choice 8: Show all available commands."""
    con.print("\n[bold]FaultRay — All Commands / 全コマンド一覧[/]\n")

    # Invoke --help via typer
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "faultray", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            con.print(result.stdout)
        else:
            # Fallback: print static summary
            _print_command_summary(con)
    except Exception:
        _print_command_summary(con)


def _print_command_summary(con: Console) -> None:
    """Print a curated command reference table."""
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Command", style="cyan", width=28)
    table.add_column("Description", width=50)

    rows = [
        # Getting started
        ("faultray start", "Interactive wizard (this menu) / このメニュー"),
        ("faultray demo", "Run demo simulation / デモシミュレーション"),
        ("faultray quickstart", "Generate YAML from template / テンプレートからYAML生成"),
        ("faultray init", "Interactive YAML builder / 対話的YAML作成"),
        # Discovery
        ("faultray scan --aws", "Scan AWS infrastructure / AWSスキャン"),
        ("faultray scan --gcp", "Scan Google Cloud / GCPスキャン"),
        ("faultray scan --azure", "Scan Azure / Azureスキャン"),
        ("faultray scan --k8s", "Scan Kubernetes / K8sスキャン"),
        ("faultray scan --onprem", "Scan on-premises / オンプレスキャン"),
        ("faultray tf-check plan.json", "Import Terraform plan / Terraformインポート"),
        # Simulation
        ("faultray simulate infra.yaml", "Run chaos simulation / カオスシミュレーション"),
        ("faultray ops-sim infra.yaml", "Operational simulation / 運用シミュレーション"),
        ("faultray analyze infra.yaml", "AI-powered analysis / AI分析"),
        # Compliance
        ("faultray dora-assess", "DORA compliance assessment / DORA準拠評価"),
        ("faultray dora-report", "DORA compliance report / DORA準拠レポート"),
        ("faultray score infra.yaml", "Resilience score / レジリエンススコア"),
        # Reporting
        ("faultray report", "Generate HTML report / HTMLレポート生成"),
        ("faultray serve", "Launch web dashboard / Webダッシュボード"),
        ("faultray export", "Export results / 結果エクスポート"),
        # Advanced
        ("faultray advisor", "Remediation advisor / 改善アドバイザー"),
        ("faultray drift", "Infrastructure drift detection / ドリフト検出"),
        ("faultray predict", "Predictive analytics / 予測分析"),
        ("faultray fmea", "FMEA analysis / FMEA分析"),
        # APM
        ("faultray apm setup", "Interactive APM setup wizard / APMセットアップウィザード"),
        ("faultray apm install", "Install APM agent config / APMエージェント設定"),
        ("faultray apm start", "Start APM agent / APMエージェント起動"),
        ("faultray apm stop", "Stop APM agent / APMエージェント停止"),
        ("faultray apm status", "APM agent status / APMエージェント状態"),
        ("faultray apm agents", "List registered agents / エージェント一覧"),
        ("faultray apm metrics <id>", "Query agent metrics / メトリクス照会"),
        ("faultray apm alerts", "View APM alerts / APMアラート確認"),
        ("faultray apm help", "Detailed APM help / APM詳細ヘルプ"),
    ]

    for cmd, desc in rows:
        table.add_row(cmd, desc)

    con.print(table)
    con.print(
        "\n[dim]Full documentation: [cyan]https://github.com/mattyopon/faultray[/][/]"
    )


# ---------------------------------------------------------------------------
# Main start command
# ---------------------------------------------------------------------------

@app.command()
def start() -> None:
    """Interactive wizard — the best way to start with FaultRay. / FaultRay入門ウィザード。

    Guides you through the most common workflows:
    quick demo, infrastructure scanning, DORA compliance,
    Terraform import, YAML authoring, and the web dashboard.

    Examples:
        faultray start
    """
    console.print(Panel.fit(
        "[bold cyan]Welcome to FaultRay[/]\n"
        "[dim]Pre-deployment resilience simulator (research prototype) / デプロイ前レジリエンス事前評価（研究プロトタイプ）[/]",
        border_style="cyan",
    ))

    console.print("\n[bold]What would you like to do? / 何をしますか？[/]\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("[cyan][1][/]", "🚀", "[bold]Quick Demo[/]",             "[dim]30秒でレジリエンスレポートを体験 / 30-second resilience report[/]")
    table.add_row("[cyan][2][/]", "🔍", "[bold]Scan My Infrastructure[/]", "[dim]AWS/GCP/Azure/オンプレを自動スキャン / Auto-scan your cloud[/]")
    table.add_row("[cyan][3][/]", "📋", "[bold]DORA Compliance Report[/]", "[dim]EU DORA準拠レポートを生成 / Generate EU DORA compliance report[/]")
    table.add_row("[cyan][4][/]", "🏗️ ", "[bold]Import Terraform[/]",      "[dim]既存のTerraform plan/stateをインポート / Import existing Terraform[/]")
    table.add_row("[cyan][5][/]", "✏️ ", "[bold]Write YAML[/]",            "[dim]インフラ構成をガイド付きで作成 / Guided infrastructure authoring[/]")
    table.add_row("[cyan][6][/]", "📊", "[bold]Open Dashboard[/]",         "[dim]WebブラウザでダッシュボードUI起動 / Launch web dashboard[/]")
    table.add_row("[cyan][7][/]", "📡", "[bold]APM Monitoring[/]",         "[dim]リアルタイム監視エージェント / Real-time metrics & anomaly detection[/]")
    table.add_row("[cyan][8][/]", "📚", "[bold]All Commands[/]",           "[dim]全コマンド一覧 / Full command reference[/]")
    console.print(table)

    choice = Prompt.ask(
        "\n[bold]Choose / 選択[/]",
        choices=["1", "2", "3", "4", "5", "6", "7", "8"],
        default="1",
    )

    handlers = {
        "1": _handle_quick_demo,
        "2": _handle_scan_infrastructure,
        "3": _handle_dora_compliance,
        "4": _handle_import_terraform,
        "5": _handle_write_yaml,
        "6": _handle_open_dashboard,
        "7": _handle_apm_monitoring,
        "8": _handle_all_commands,
    }

    handler = handlers.get(choice)
    if handler is None:
        console.print("[red]Invalid choice.[/]")
        raise typer.Exit(1)

    try:
        handler(console)
    except (KeyboardInterrupt, typer.Exit):
        raise
    except Exception as exc:
        console.print(f"\n[red]Error: {exc}[/]")
        console.print("[dim]If this keeps happening, please file a bug report.[/]")
        raise typer.Exit(1)
