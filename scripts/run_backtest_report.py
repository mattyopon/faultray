#!/usr/bin/env python3
"""Run FaultRay backtest against 18 historical public incidents and generate accuracy report.

Builds representative infrastructure graphs for each incident, converts
HistoricalIncident records into RealIncident objects expected by BacktestEngine,
runs the cascade simulation, and outputs both JSON and Markdown reports.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure the project source is importable
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root / "src"))

from faultray.model.components import (
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.backtest_engine import BacktestEngine, RealIncident
from faultray.simulator.incident_db import HISTORICAL_INCIDENTS
from faultray.simulator.incident_replay import HistoricalIncident

# ---------------------------------------------------------------------------
# Service name -> (ComponentType, component_id) mapping
# ---------------------------------------------------------------------------

SERVICE_TO_COMPONENT: dict[str, tuple[str, str]] = {
    # AWS
    "ec2": ("app_server", "app_server"),
    "rds": ("database", "primary_db"),
    "aurora": ("database", "primary_db"),
    "elasticache": ("cache", "redis"),
    "redis": ("cache", "redis"),
    "s3": ("storage", "s3_storage"),
    "lambda": ("app_server", "lambda_fn"),
    "sqs": ("queue", "message_queue"),
    "cloudwatch": ("external_api", "monitoring"),
    "ecs": ("app_server", "container_service"),
    "alb": ("load_balancer", "main_lb"),
    "nlb": ("load_balancer", "main_lb"),
    "cloudfront": ("load_balancer", "cdn"),
    "route53": ("dns", "dns_resolver"),
    "dynamodb": ("database", "dynamo_db"),
    "kinesis": ("queue", "event_stream"),
    "ebs": ("storage", "block_storage"),
    "api_gateway": ("external_api", "api_gw"),
    # GCP
    "compute_engine": ("app_server", "gce_instance"),
    "cloud_sql": ("database", "cloud_sql"),
    "gke": ("app_server", "k8s_cluster"),
    "cloud_lb": ("load_balancer", "gcp_lb"),
    "gcs": ("storage", "gcs_storage"),
    # Azure
    "azure_vm": ("app_server", "azure_vm"),
    "azure_sql": ("database", "azure_sql"),
    "azure_storage": ("storage", "azure_blob"),
    "azure_lb": ("load_balancer", "azure_lb"),
    "azure_ad": ("app_server", "identity_service"),
    # Generic / cross-provider
    "cdn": ("load_balancer", "cdn"),
    "dns": ("dns", "dns_resolver"),
    "api": ("app_server", "api_gateway"),
    "web": ("web_server", "web_frontend"),
    "database": ("database", "primary_db"),
    "cache": ("cache", "redis"),
    "queue": ("queue", "message_queue"),
    "storage": ("storage", "object_storage"),
    "lb": ("load_balancer", "main_lb"),
    "bgp": ("dns", "bgp_router"),
    "load_balancer": ("load_balancer", "main_lb"),
    "server": ("app_server", "app_server"),
}

_COMP_TYPE_MAP: dict[str, ComponentType] = {
    "load_balancer": ComponentType.LOAD_BALANCER,
    "web_server": ComponentType.WEB_SERVER,
    "app_server": ComponentType.APP_SERVER,
    "database": ComponentType.DATABASE,
    "cache": ComponentType.CACHE,
    "queue": ComponentType.QUEUE,
    "storage": ComponentType.STORAGE,
    "dns": ComponentType.DNS,
    "external_api": ComponentType.EXTERNAL_API,
}

# Component ordering for automatic dependency wiring
_TIER_ORDER = [
    ComponentType.DNS,
    ComponentType.LOAD_BALANCER,
    ComponentType.WEB_SERVER,
    ComponentType.APP_SERVER,
    ComponentType.EXTERNAL_API,
    ComponentType.DATABASE,
    ComponentType.CACHE,
    ComponentType.QUEUE,
    ComponentType.STORAGE,
]


def _tier_rank(ct: ComponentType) -> int:
    try:
        return _TIER_ORDER.index(ct)
    except ValueError:
        return 99


# ---------------------------------------------------------------------------
# Build infrastructure graph for a given incident
# ---------------------------------------------------------------------------


def build_cloud_infra_graph(
    services: list[str], provider: str, regions: list[str]
) -> InfraGraph:
    """Build a representative InfraGraph from the incident's affected services.

    Creates components for each unique service with sensible defaults, then
    wires up dependencies following the typical LB -> App -> DB/Cache/Queue
    pattern.
    """
    graph = InfraGraph()
    created_ids: dict[str, Component] = {}  # component_id -> Component

    region = regions[0] if regions else ""

    for svc in services:
        mapping = SERVICE_TO_COMPONENT.get(svc)
        if not mapping:
            continue
        type_str, comp_id = mapping

        # Avoid duplicates (e.g. ec2 and server both map to app_server)
        if comp_id in created_ids:
            continue

        comp_type = _COMP_TYPE_MAP[type_str]
        comp = Component(
            id=comp_id,
            name=f"{comp_id} ({svc})",
            type=comp_type,
            host=f"{comp_id}.internal",
            port=_default_port(comp_type),
            replicas=1,
            metrics=ResourceMetrics(
                cpu_percent=40,
                memory_percent=50,
                disk_percent=30,
                network_connections=100,
            ),
            capacity=Capacity(
                max_connections=1000,
                max_rps=5000,
                connection_pool_size=100,
                timeout_seconds=30,
            ),
            region=RegionConfig(region=region),
        )
        graph.add_component(comp)
        created_ids[comp_id] = comp

    # Wire dependencies: upstream components depend on downstream ones
    sorted_comps = sorted(created_ids.values(), key=lambda c: _tier_rank(c.type))

    # Identify tiers
    upstream_tier: list[Component] = []  # DNS, LB, Web
    app_tier: list[Component] = []       # App, External API
    data_tier: list[Component] = []      # DB, Cache, Queue, Storage

    for c in sorted_comps:
        rank = _tier_rank(c.type)
        if rank <= _TIER_ORDER.index(ComponentType.WEB_SERVER):
            upstream_tier.append(c)
        elif rank <= _TIER_ORDER.index(ComponentType.EXTERNAL_API):
            app_tier.append(c)
        else:
            data_tier.append(c)

    # upstream -> app dependencies
    for up in upstream_tier:
        for app in app_tier:
            graph.add_dependency(Dependency(
                source_id=up.id,
                target_id=app.id,
                dependency_type="requires",
                weight=1.0,
            ))

    # app -> data dependencies
    for app in app_tier:
        for data in data_tier:
            dep_type = "requires"
            if data.type == ComponentType.CACHE:
                dep_type = "optional"
            elif data.type == ComponentType.QUEUE:
                dep_type = "async"
            graph.add_dependency(Dependency(
                source_id=app.id,
                target_id=data.id,
                dependency_type=dep_type,
                weight=1.0 if dep_type == "requires" else 0.7,
            ))

    # If no app tier, connect upstream directly to data
    if not app_tier:
        for up in upstream_tier:
            for data in data_tier:
                graph.add_dependency(Dependency(
                    source_id=up.id,
                    target_id=data.id,
                    dependency_type="requires",
                    weight=1.0,
                ))

    # Chain within upstream tier (dns -> lb -> web)
    for i in range(len(upstream_tier) - 1):
        graph.add_dependency(Dependency(
            source_id=upstream_tier[i].id,
            target_id=upstream_tier[i + 1].id,
            dependency_type="requires",
            weight=1.0,
        ))

    return graph


def _default_port(ct: ComponentType) -> int:
    return {
        ComponentType.LOAD_BALANCER: 443,
        ComponentType.WEB_SERVER: 80,
        ComponentType.APP_SERVER: 8080,
        ComponentType.DATABASE: 5432,
        ComponentType.CACHE: 6379,
        ComponentType.QUEUE: 5672,
        ComponentType.STORAGE: 443,
        ComponentType.DNS: 53,
        ComponentType.EXTERNAL_API: 443,
    }.get(ct, 8080)


# ---------------------------------------------------------------------------
# Convert HistoricalIncident -> RealIncident
# ---------------------------------------------------------------------------


def convert_incident(
    hist: HistoricalIncident, graph: InfraGraph
) -> RealIncident:
    """Map a HistoricalIncident to a RealIncident compatible with BacktestEngine."""

    # Map affected_services to component IDs that exist in the graph
    actual_affected: list[str] = []
    failed_component: str = ""

    for svc in hist.affected_services:
        mapping = SERVICE_TO_COMPONENT.get(svc)
        if not mapping:
            continue
        _, comp_id = mapping
        if comp_id in graph.components:
            actual_affected.append(comp_id)
            if not failed_component:
                failed_component = comp_id

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for cid in actual_affected:
        if cid not in seen:
            seen.add(cid)
            deduped.append(cid)
    actual_affected = deduped

    if not failed_component and graph.components:
        failed_component = next(iter(graph.components))

    return RealIncident(
        incident_id=hist.id,
        timestamp=hist.date.isoformat(),
        failed_component=failed_component,
        actual_affected_components=actual_affected,
        actual_downtime_minutes=hist.duration.total_seconds() / 60,
        actual_severity=hist.severity,
        root_cause=hist.root_cause,
    )


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------


def generate_markdown_report(
    summary: dict,
    results: list,
    output_path: Path,
) -> None:
    """Generate a Markdown report from backtest results."""
    lines: list[str] = []
    lines.append("# FaultRay Backtest Accuracy Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Total Incidents: {summary['total_incidents']}")
    lines.append("")

    # Overall summary
    lines.append("## Overall Accuracy Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Avg Precision | {summary['avg_precision']:.3f} |")
    lines.append(f"| Avg Recall | {summary['avg_recall']:.3f} |")
    lines.append(f"| Avg F1 Score | {summary['avg_f1']:.3f} |")
    lines.append(f"| Avg Severity Accuracy | {summary['avg_severity_accuracy']:.3f} |")
    lines.append(f"| Avg Downtime MAE (min) | {summary['avg_downtime_mae_minutes']:.2f} |")
    lines.append(f"| Avg Confidence | {summary['avg_confidence']:.3f} |")
    lines.append("")

    # Per-incident table
    lines.append("## Per-Incident Results")
    lines.append("")
    lines.append("| Incident ID | Component | Precision | Recall | F1 | Sev Acc | DT MAE | Confidence |")
    lines.append("|-------------|-----------|-----------|--------|----|---------|--------|------------|")
    for r in summary.get("per_incident", []):
        lines.append(
            f"| {r['incident_id']} "
            f"| {r['component']} "
            f"| {r['precision']:.3f} "
            f"| {r['recall']:.3f} "
            f"| {r['f1']:.3f} "
            f"| {r['severity_accuracy']:.3f} "
            f"| {r['downtime_mae']:.1f} "
            f"| {r['confidence']:.3f} |"
        )
    lines.append("")

    # Calibration recommendations
    calibration = summary.get("calibration", {})
    if calibration:
        lines.append("## Calibration Recommendations")
        lines.append("")
        for key, val in calibration.items():
            lines.append(f"- **{key}**: {val}")
        lines.append("")

    # Detailed results
    lines.append("## Detailed Results")
    lines.append("")
    for r in results:
        inc = r.incident
        lines.append(f"### {inc.incident_id}")
        lines.append("")
        lines.append(f"- **Failed Component**: {inc.failed_component}")
        lines.append(f"- **Actual Affected**: {', '.join(inc.actual_affected_components)}")
        lines.append(f"- **Predicted Affected**: {', '.join(r.predicted_affected)}")
        lines.append(f"- **Actual Severity**: {inc.actual_severity}")
        lines.append(f"- **Predicted Severity**: {r.predicted_severity}")
        lines.append(f"- **Actual Downtime**: {inc.actual_downtime_minutes:.0f} min")
        lines.append(f"- **Predicted Downtime**: {r.predicted_downtime_minutes:.1f} min")
        lines.append(f"- **Precision**: {r.precision:.3f} | **Recall**: {r.recall:.3f} | **F1**: {r.f1_score:.3f}")
        if r.details:
            tp = r.details.get("true_positives", [])
            fp = r.details.get("false_positives", [])
            fn = r.details.get("false_negatives", [])
            if tp:
                lines.append(f"- **True Positives**: {', '.join(tp)}")
            if fp:
                lines.append(f"- **False Positives**: {', '.join(fp)}")
            if fn:
                lines.append(f"- **False Negatives**: {', '.join(fn)}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Markdown report written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    results_all = []

    print(f"Running backtest against {len(HISTORICAL_INCIDENTS)} historical incidents...")
    print("=" * 70)

    for incident in HISTORICAL_INCIDENTS:
        graph = build_cloud_infra_graph(
            incident.affected_services,
            incident.provider,
            incident.affected_regions,
        )
        real_incident = convert_incident(incident, graph)

        print(f"\n[{incident.id}] {incident.name}")
        print(f"  Provider: {incident.provider} | Severity: {incident.severity}")
        print(f"  Services: {', '.join(incident.affected_services)}")
        print(f"  Graph components: {len(graph.components)} | Edges: {len(graph.all_dependency_edges())}")
        print(f"  Failed component: {real_incident.failed_component}")
        print(f"  Actual affected: {real_incident.actual_affected_components}")

        engine = BacktestEngine(graph)
        results = engine.run_backtest([real_incident])
        results_all.extend(results)

        for r in results:
            print(f"  Predicted affected: {r.predicted_affected}")
            print(f"  Precision: {r.precision:.3f} | Recall: {r.recall:.3f} | F1: {r.f1_score:.3f}")
            print(f"  Severity Accuracy: {r.severity_accuracy:.3f}")
            print(f"  Confidence: {r.prediction_confidence:.3f}")

    print("\n" + "=" * 70)
    print("Generating summary...")

    # Use a dummy engine for summary (any graph works, summary only uses results)
    dummy_engine = BacktestEngine(InfraGraph())
    summary = dummy_engine.summary(results_all)

    # Print summary
    print(f"\n{'=' * 70}")
    print("BACKTEST SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total incidents:        {summary['total_incidents']}")
    print(f"Avg Precision:          {summary['avg_precision']:.3f}")
    print(f"Avg Recall:             {summary['avg_recall']:.3f}")
    print(f"Avg F1 Score:           {summary['avg_f1']:.3f}")
    print(f"Avg Severity Accuracy:  {summary['avg_severity_accuracy']:.3f}")
    print(f"Avg Downtime MAE (min): {summary['avg_downtime_mae_minutes']:.2f}")
    print(f"Avg Confidence:         {summary['avg_confidence']:.3f}")

    if summary.get("calibration"):
        print(f"\nCalibration recommendations:")
        for k, v in summary["calibration"].items():
            print(f"  {k}: {v}")

    # Save JSON report
    docs_dir = _project_root / "docs"
    docs_dir.mkdir(exist_ok=True)

    json_path = docs_dir / "backtest-results.json"
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nJSON report written to: {json_path}")

    # Save Markdown report
    md_path = docs_dir / "backtest-results.md"
    generate_markdown_report(summary, results_all, md_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
