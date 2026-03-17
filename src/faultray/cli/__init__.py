"""CLI package for FaultRay.

Re-exports the Typer ``app`` so that ``faultray.cli:app`` keeps working as the
entry-point defined in pyproject.toml.  Submodules register their commands by
importing ``app`` from :mod:`faultray.cli.main` at import time.
"""

from faultray.cli.main import (  # noqa: F401 — re-export
    _print_dynamic_results,
    app,
)

# Import submodules so that their @app.command() decorators run and the
# commands get registered on the shared ``app`` instance.
import faultray.cli.admin  # noqa: F401
import faultray.cli.backtest  # noqa: F401
import faultray.cli.config_cmd  # noqa: F401
import faultray.cli.analyze  # noqa: F401
import faultray.cli.daemon_cmd  # noqa: F401
import faultray.cli.diff_cmd  # noqa: F401
import faultray.cli.discovery  # noqa: F401
import faultray.cli.evaluate  # noqa: F401
import faultray.cli.feeds  # noqa: F401
import faultray.cli.ops  # noqa: F401
import faultray.cli.predictive  # noqa: F401
import faultray.cli.quickstart  # noqa: F401
import faultray.cli.simulate  # noqa: F401
import faultray.cli.history_cmd  # noqa: F401
import faultray.cli.auto_fix  # noqa: F401
import faultray.cli.tf_check  # noqa: F401
import faultray.cli.nl_command  # noqa: F401
import faultray.cli.genome  # noqa: F401
import faultray.cli.sla_cmd  # noqa: F401
import faultray.cli.marketplace_cmd  # noqa: F401
import faultray.cli.dna_cmd  # noqa: F401
import faultray.cli.supply_chain_cmd  # noqa: F401
import faultray.cli.autoscale_cmd  # noqa: F401
import faultray.cli.replay_cmd  # noqa: F401
import faultray.cli.drift_cmd  # noqa: F401
import faultray.cli.advisor_cmd  # noqa: F401
import faultray.cli.timeline_cmd  # noqa: F401
import faultray.cli.benchmark_cmd  # noqa: F401
import faultray.cli.twin_cmd  # noqa: F401
import faultray.cli.calendar_cmd  # noqa: F401
import faultray.cli.evidence_cmd  # noqa: F401
import faultray.cli.export_cmd  # noqa: F401
import faultray.cli.fuzz_cmd  # noqa: F401
import faultray.cli.replay_timeline_cmd  # noqa: F401
import faultray.cli.slo_budget_cmd  # noqa: F401
import faultray.cli.ask_cmd  # noqa: F401
import faultray.cli.runbook_cmd  # noqa: F401
import faultray.cli.deps_cmd  # noqa: F401
import faultray.cli.git_track_cmd  # noqa: F401
import faultray.cli.graph_export_cmd  # noqa: F401
import faultray.cli.heatmap_cmd  # noqa: F401
import faultray.cli.report_cmd  # noqa: F401
import faultray.cli.contract_cmd  # noqa: F401
import faultray.cli.canary_cmd  # noqa: F401
import faultray.cli.multienv_cmd  # noqa: F401
import faultray.cli.cost_attr_cmd  # noqa: F401
import faultray.cli.plugin_cmd  # noqa: F401
import faultray.cli.topology_diff_cmd  # noqa: F401
import faultray.cli.optimizer_cmd  # noqa: F401
import faultray.cli.anomaly_cmd  # noqa: F401
import faultray.cli.sre_maturity_cmd  # noqa: F401
import faultray.cli.postmortem_cmd  # noqa: F401
import faultray.cli.env_compare_cmd  # noqa: F401
import faultray.cli.template_cmd  # noqa: F401
import faultray.cli.team_cmd  # noqa: F401
import faultray.cli.compliance_monitor_cmd  # noqa: F401
import faultray.cli.gate_cmd  # noqa: F401
import faultray.cli.war_room_cmd  # noqa: F401
import faultray.cli.cost_optimize_cmd  # noqa: F401
import faultray.cli.antipattern_cmd  # noqa: F401
import faultray.cli.ab_test_cmd  # noqa: F401
import faultray.cli.fmea_cmd  # noqa: F401
import faultray.cli.monkey_cmd  # noqa: F401
import faultray.cli.import_metrics_cmd  # noqa: F401
import faultray.cli.budget_cmd  # noqa: F401
import faultray.cli.velocity_cmd  # noqa: F401
import faultray.cli.attack_surface_cmd  # noqa: F401
import faultray.cli.score_cmd  # noqa: F401
import faultray.cli.cost_impact_cmd  # noqa: F401
import faultray.cli.init_cmd  # noqa: F401
import faultray.cli.agent_cmd  # noqa: F401

__all__ = ["app", "_print_dynamic_results"]
