# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""MCP (Model Context Protocol) server for FaultRay.

Exposes FaultRay's infrastructure simulation and resilience analysis tools
via the MCP protocol, enabling Claude Desktop, Cursor, Windsurf, and other
MCP-capable AI assistants to interact with your infrastructure directly.

Transport: stdio (default for Claude Desktop / Claude Code)

Entry point:
    python -m faultray.mcp_server
    uvx faultray[mcp]  (if installed with mcp extra)
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional MCP import — fail gracefully if mcp package not installed
# ---------------------------------------------------------------------------
try:
    from mcp.server.fastmcp import FastMCP
    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MCP_AVAILABLE = False
    FastMCP = None  # type: ignore[assignment,misc]

from faultray import __version__
from faultray.model.graph import InfraGraph
from faultray.simulator.mcp_bridge import MCPBridge, MCPRequest, MCPToolName

# ---------------------------------------------------------------------------
# Module-level state — current active InfraGraph
# ---------------------------------------------------------------------------

_current_graph: InfraGraph | None = None
_current_graph_source: str = ""  # human-readable label (file path or "inline YAML")


def _get_graph() -> InfraGraph | None:
    """Return the currently loaded InfraGraph (may be None)."""
    return _current_graph


def _set_graph(graph: InfraGraph | None, source: str = "") -> None:
    """Replace the active InfraGraph."""
    global _current_graph, _current_graph_source
    _current_graph = graph
    _current_graph_source = source


def _require_graph() -> InfraGraph:
    """Return the current graph or raise a descriptive RuntimeError."""
    graph = _get_graph()
    if graph is None:
        raise RuntimeError(
            "No infrastructure loaded. "
            "Use load_infrastructure(yaml_content) or load_infrastructure_file(file_path) first."
        )
    return graph


def _bridge() -> MCPBridge:
    """Return an MCPBridge bound to the current graph."""
    return MCPBridge(_require_graph())


def _call_bridge(tool_name: MCPToolName, params: dict[str, Any]) -> str:
    """Execute a bridge tool and return a JSON string result.

    Returns a plain-text error string (not JSON) on failure so the AI
    assistant sees a human-readable message rather than an exception trace.
    """
    try:
        bridge = _bridge()
    except RuntimeError as exc:
        return f"Error: {exc}"
    resp = bridge.execute(MCPRequest(tool_name=tool_name, parameters=params))
    if not resp.success:
        return f"Error: {resp.error or f'Tool {tool_name} failed'}"
    return json.dumps(resp.result, indent=2, default=str)


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

if not _MCP_AVAILABLE:
    raise ImportError(
        "The 'mcp' package is required to run the FaultRay MCP server.\n"
        "Install it with:  pip install 'faultray[mcp]'\n"
        "Or separately:    pip install mcp"
    )

mcp: FastMCP = FastMCP("faultray")


# ===========================================================================
# TOOLS — infrastructure loading
# ===========================================================================


@mcp.tool()
def load_infrastructure(yaml_content: str) -> str:
    """Load an infrastructure definition from a YAML string and set it as the active graph.

    The YAML must have a ``components`` list (each with ``id``, ``name``, ``type``)
    and an optional ``dependencies`` list.  Once loaded, all analysis tools operate
    on this infrastructure until a new one is loaded.

    Args:
        yaml_content: Full YAML text of the infrastructure definition.

    Returns:
        A summary of the loaded infrastructure (component count, resilience score).
    """

    import yaml as _yaml

    from faultray.errors import ValidationError
    from faultray.model.loader import load_yaml

    # Parse via a StringIO-backed temp approach: write to a temp file or use
    # the loader's internal raw path.  The loader only accepts a Path, so we
    # create a temporary file.
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(yaml_content)
            tmp_path = Path(tmp.name)

        graph = load_yaml(tmp_path)
        tmp_path.unlink(missing_ok=True)
    except FileNotFoundError as exc:
        return f"Error: {exc}"
    except ValidationError as exc:
        return f"Validation error: {exc}"
    except _yaml.YAMLError as exc:
        return f"YAML parse error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error loading infrastructure: {exc}"

    _set_graph(graph, "inline YAML")
    summary = graph.summary()
    score = round(graph.resilience_score(), 1)
    return (
        f"Infrastructure loaded successfully.\n"
        f"  Components : {summary['total_components']}\n"
        f"  Dependencies : {summary['total_dependencies']}\n"
        f"  Resilience score : {score}/100\n"
        f"  Source : inline YAML"
    )


@mcp.tool()
def load_infrastructure_file(file_path: str) -> str:
    """Load an infrastructure definition from a YAML file on disk.

    Args:
        file_path: Absolute or relative path to the infrastructure YAML file.

    Returns:
        A summary of the loaded infrastructure (component count, resilience score).
    """
    import yaml as _yaml

    from faultray.errors import ValidationError
    from faultray.model.loader import load_yaml

    path = Path(file_path).expanduser().resolve()
    try:
        graph = load_yaml(path)
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except ValidationError as exc:
        return f"Validation error in {path.name}: {exc}"
    except _yaml.YAMLError as exc:
        return f"YAML parse error in {path.name}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error loading {path.name}: {exc}"

    _set_graph(graph, str(path))
    summary = graph.summary()
    score = round(graph.resilience_score(), 1)
    return (
        f"Infrastructure loaded from '{path.name}'.\n"
        f"  Components : {summary['total_components']}\n"
        f"  Dependencies : {summary['total_dependencies']}\n"
        f"  Resilience score : {score}/100\n"
        f"  Source : {path}"
    )


# ===========================================================================
# TOOLS — core analysis (delegates to MCPBridge)
# ===========================================================================


@mcp.tool()
def simulate(component_id: str, failure_type: str = "down") -> str:
    """Simulate a component failure and show the cascade impact across dependent services.

    Args:
        component_id: ID of the component to fail (e.g. ``aws_lb.main``).
        failure_type: One of ``down``, ``degraded``, or ``overloaded``.

    Returns:
        JSON with affected components, cascade paths, and impact count.
    """
    return _call_bridge(
        MCPToolName.SIMULATE,
        {"component_id": component_id, "failure_type": failure_type},
    )


@mcp.tool()
def analyze_resilience() -> str:
    """Analyze overall infrastructure resilience and return a detailed score breakdown.

    Returns:
        JSON with resilience score (0-100), dimensional breakdown, and actionable
        recommendations ranked by impact.
    """
    return _call_bridge(MCPToolName.ANALYZE_RESILIENCE, {})


@mcp.tool()
def find_spof() -> str:
    """Find all single points of failure (SPOFs) in the infrastructure.

    A SPOF is any component with replicas <= 1 that has one or more dependents.
    Eliminating SPOFs is the highest-leverage resilience improvement.

    Returns:
        JSON list of SPOFs with component type, dependent count, and dependent IDs.
    """
    return _call_bridge(MCPToolName.FIND_SPOF, {})


@mcp.tool()
def what_if(component_id: str, change: str, value: int = 2) -> str:
    """Evaluate a hypothetical infrastructure change before applying it.

    Useful for answering "What happens to resilience if I scale out the API servers?"
    or "How much does enabling failover on the database improve the score?"

    Args:
        component_id: ID of the component to modify.
        change: One of ``add_replicas``, ``enable_failover``, or ``enable_autoscaling``.
        value: New value for the change (e.g. replica count for ``add_replicas``).

    Returns:
        JSON with current score, projected description, and change metadata.
    """
    return _call_bridge(
        MCPToolName.WHAT_IF,
        {"component_id": component_id, "change": change, "value": value},
    )


@mcp.tool()
def check_compliance(framework: str) -> str:
    """Check infrastructure compliance against a regulatory/security framework.

    Args:
        framework: One of ``soc2``, ``iso27001``, ``pci_dss``, or ``nist_csf``.

    Returns:
        JSON with per-control pass/fail results and overall compliance percentage.
    """
    return _call_bridge(MCPToolName.CHECK_COMPLIANCE, {"framework": framework})


@mcp.tool()
def recommend_chaos(max_experiments: int = 5) -> str:
    """Recommend chaos experiments based on the current infrastructure topology.

    Experiments are ranked by priority (high/medium/low) based on SPOF status
    and downstream dependency count.

    Args:
        max_experiments: Maximum number of experiments to return (default 5).

    Returns:
        JSON list of recommended chaos experiments with rationale.
    """
    return _call_bridge(MCPToolName.RECOMMEND_CHAOS, {"max_experiments": max_experiments})


@mcp.tool()
def predict_change_risk(component_id: str, change_type: str, description: str = "") -> str:
    """Predict the risk level of a proposed infrastructure change.

    Risk is derived from the component's downstream dependency count — the more
    services depend on it, the riskier any change becomes.

    Args:
        component_id: Component being changed.
        change_type: Type of change (e.g. ``instance_type``, ``db_upgrade``, ``config_update``).
        description: Optional human-readable description of the change.

    Returns:
        JSON with risk level (low/medium/high), dependent count, and context.
    """
    return _call_bridge(
        MCPToolName.PREDICT_CHANGE_RISK,
        {"component_id": component_id, "change_type": change_type, "description": description},
    )


@mcp.tool()
def generate_report(format: str = "summary") -> str:  # noqa: A002
    """Generate a resilience report for the current infrastructure.

    Args:
        format: ``summary`` (default) or ``detailed`` (includes score breakdown
                and full recommendations list).

    Returns:
        JSON report with resilience score, summary statistics, and optional detail.
    """
    return _call_bridge(MCPToolName.GENERATE_REPORT, {"format": format})


# ===========================================================================
# TOOLS — Terraform-specific
# ===========================================================================


@mcp.tool()
def tf_check(plan_json_path: str, min_score: float = 60.0) -> str:
    """Check a Terraform plan's resilience impact before applying it.

    Parses the JSON output of ``terraform show -json <plan>`` and calculates
    before/after resilience scores, new risks introduced, and a go/no-go
    recommendation.

    Typical workflow:
        terraform plan -out=plan.out
        terraform show -json plan.out > plan.json
        # Then ask Claude: tf_check("plan.json")

    Args:
        plan_json_path: Path to the ``terraform show -json`` output file.
        min_score: Minimum acceptable after-plan resilience score (default 60.0).
                   Returns a warning if the post-plan score falls below this.

    Returns:
        Human-readable + JSON analysis: score delta, new risks, recommendation.
    """
    from faultray.integrations.terraform_provider import TerraformFaultRayProvider

    path = Path(plan_json_path).expanduser().resolve()
    if not path.exists():
        return f"Error: Plan file not found: {path}"

    try:
        provider = TerraformFaultRayProvider()
        analysis = provider.analyze_plan(path)
    except Exception as exc:  # noqa: BLE001
        return f"Error analyzing Terraform plan: {exc}"

    score_warning = ""
    if analysis.score_after < min_score:
        score_warning = (
            f"\nWARNING: Post-plan score {analysis.score_after} is below minimum {min_score}."
        )

    result = {
        "plan_file": analysis.plan_file,
        "resources_added": analysis.resources_added,
        "resources_changed": analysis.resources_changed,
        "resources_destroyed": analysis.resources_destroyed,
        "score_before": analysis.score_before,
        "score_after": analysis.score_after,
        "score_delta": analysis.score_delta,
        "new_risks": analysis.new_risks,
        "resolved_risks": analysis.resolved_risks,
        "recommendation": analysis.recommendation,
        "min_score_check": "PASS" if analysis.score_after >= min_score else "FAIL",
        "changes_summary": [
            {"address": c["address"], "actions": c["actions"], "risk_level": c["risk_level"]}
            for c in analysis.changes[:10]  # top 10 changes by risk
        ],
    }

    delta_str = f"+{analysis.score_delta}" if analysis.score_delta >= 0 else str(analysis.score_delta)
    header = (
        f"Terraform Plan Resilience Analysis\n"
        f"  Score: {analysis.score_before} → {analysis.score_after} ({delta_str})\n"
        f"  Recommendation: {analysis.recommendation}\n"
        f"  Added: {analysis.resources_added}  Changed: {analysis.resources_changed}  "
        f"Destroyed: {analysis.resources_destroyed}{score_warning}\n\n"
    )
    return header + json.dumps(result, indent=2)


@mcp.tool()
def dora_assess(yaml_path: str) -> str:
    """Run a quick DORA compliance assessment on an infrastructure YAML file.

    Checks the infrastructure against DORA (Digital Operational Resilience Act)
    key requirements: redundancy, failover, and overall resilience score thresholds.

    Args:
        yaml_path: Path to the infrastructure YAML file to assess.

    Returns:
        DORA compliance summary with pass/fail per control and overall readiness.
    """
    from faultray.model.loader import load_yaml

    path = Path(yaml_path).expanduser().resolve()
    try:
        graph = load_yaml(path)
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except Exception as exc:  # noqa: BLE001
        return f"Error loading infrastructure: {exc}"

    bridge = MCPBridge(graph)
    bridge.execute(MCPRequest(tool_name=MCPToolName.CHECK_COMPLIANCE, parameters={"framework": "iso27001"}))

    score = round(graph.resilience_score(), 1)
    summary = graph.summary()

    # DORA-specific thresholds
    dora_score_ok = score >= 70.0
    dora_redundancy = all(c.replicas >= 2 for c in graph.components.values()) if graph.components else False
    dora_failover = all(c.failover.enabled for c in graph.components.values()) if graph.components else False

    checks = [
        {"control": "resilience_score_>=70", "status": "PASS" if dora_score_ok else "FAIL",
         "evidence": f"Score is {score}/100"},
        {"control": "all_components_redundant", "status": "PASS" if dora_redundancy else "FAIL",
         "evidence": "All replicas >= 2" if dora_redundancy else "Some components lack redundancy"},
        {"control": "failover_enabled", "status": "PASS" if dora_failover else "FAIL",
         "evidence": "All failover enabled" if dora_failover else "Some components lack failover"},
    ]

    passed = sum(1 for c in checks if c["status"] == "PASS")
    result = {
        "file": str(path),
        "framework": "DORA",
        "components": summary["total_components"],
        "resilience_score": score,
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "compliance_percent": round(passed / len(checks) * 100, 1),
        "verdict": "COMPLIANT" if passed == len(checks) else "GAPS FOUND",
    }

    return json.dumps(result, indent=2)


# ===========================================================================
# RESOURCES
# ===========================================================================


@mcp.resource("faultray://version")
def resource_version() -> str:
    """Current FaultRay version."""
    return f"FaultRay v{__version__}"


@mcp.resource("faultray://tools")
def resource_tools() -> str:
    """List of all available FaultRay MCP tools with descriptions."""
    tools = [
        ("load_infrastructure", "Load infra YAML string and set as active graph"),
        ("load_infrastructure_file", "Load infra YAML from a file path"),
        ("simulate", "Simulate a component failure and show cascade impact"),
        ("analyze_resilience", "Full resilience score breakdown and recommendations"),
        ("find_spof", "Find all single points of failure"),
        ("what_if", "Evaluate a hypothetical change (add replicas, enable failover)"),
        ("check_compliance", "Check compliance: soc2 / iso27001 / pci_dss / nist_csf"),
        ("recommend_chaos", "Recommend chaos experiments ranked by priority"),
        ("predict_change_risk", "Predict risk level of a proposed change"),
        ("generate_report", "Generate a resilience report (summary or detailed)"),
        ("tf_check", "Analyze a Terraform plan JSON for resilience impact"),
        ("dora_assess", "Quick DORA compliance assessment from a YAML file"),
    ]
    lines = [f"FaultRay v{__version__} — Available MCP Tools", "=" * 50]
    for name, desc in tools:
        lines.append(f"  {name:<30} {desc}")
    return "\n".join(lines)


@mcp.resource("faultray://infrastructure")
def resource_infrastructure() -> str:
    """Summary of the currently loaded infrastructure graph."""
    graph = _get_graph()
    if graph is None:
        return (
            "No infrastructure loaded.\n"
            "Use load_infrastructure() or load_infrastructure_file() to load one."
        )
    summary = graph.summary()
    score = round(graph.resilience_score(), 1)
    v2 = graph.resilience_score_v2()

    lines = [
        f"Active Infrastructure: {_current_graph_source or 'unknown source'}",
        f"  Components   : {summary['total_components']}",
        f"  Dependencies : {summary['total_dependencies']}",
        f"  Score        : {score}/100",
        "",
        "Component breakdown:",
    ]
    type_counts: dict[str, int] = {}
    for comp in graph.components.values():
        type_counts[comp.type.value] = type_counts.get(comp.type.value, 0) + 1
    for ctype, count in sorted(type_counts.items()):
        lines.append(f"  {ctype:<20} {count}")

    if v2.get("recommendations"):
        lines.append("")
        lines.append("Top recommendations:")
        for rec in v2["recommendations"][:3]:
            lines.append(f"  - {rec}")

    return "\n".join(lines)


# ===========================================================================
# PROMPTS
# ===========================================================================


@mcp.prompt()
def resilience_review() -> str:
    """Template prompt for reviewing infrastructure resilience with FaultRay."""
    return textwrap.dedent("""\
        You are a Site Reliability Engineer reviewing infrastructure resilience with FaultRay.

        Follow this workflow:
        1. Load the infrastructure:
           - If the user has a YAML file: use load_infrastructure_file(file_path)
           - If they paste YAML: use load_infrastructure(yaml_content)
        2. Run analyze_resilience() to get the overall score and recommendations.
        3. Run find_spof() to identify single points of failure.
        4. For each critical SPOF, use simulate(component_id) to show blast radius.
        5. Use what_if() to show how adding replicas or enabling failover improves the score.
        6. Use recommend_chaos() to suggest chaos experiments.
        7. Summarize findings and prioritize the top 3 improvements.

        Be specific and actionable. Quote component IDs and score numbers directly.
    """)


@mcp.prompt()
def terraform_review() -> str:
    """Template prompt for reviewing a Terraform plan for resilience safety."""
    return textwrap.dedent("""\
        You are a DevOps engineer reviewing a Terraform plan for resilience and safety.

        Follow this workflow:
        1. Ask the user for the path to their terraform plan JSON file
           (generated with: terraform show -json plan.out > plan.json)
        2. Run tf_check(plan_json_path) to analyze the plan.
        3. Highlight:
           - Score delta (before → after resilience score)
           - Any new risks introduced by the plan
           - Resources being destroyed (high risk)
           - The overall recommendation (safe / review recommended / high risk)
        4. If risks are found, suggest mitigations using what_if() on the affected components.
        5. If the infrastructure YAML is available, also run dora_assess() for compliance check.

        Be concise. Flag CRITICAL items first, then WARNINGS, then suggestions.
    """)


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> None:  # pragma: no cover
    """Run the FaultRay MCP server over stdio transport."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
