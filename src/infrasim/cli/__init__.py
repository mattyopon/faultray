"""CLI package for InfraSim.

Re-exports the Typer ``app`` so that ``infrasim.cli:app`` keeps working as the
entry-point defined in pyproject.toml.  Submodules register their commands by
importing ``app`` from :mod:`infrasim.cli.main` at import time.
"""

from infrasim.cli.main import (  # noqa: F401 — re-export
    _print_dynamic_results,
    app,
)

# Import submodules so that their @app.command() decorators run and the
# commands get registered on the shared ``app`` instance.
import infrasim.cli.admin  # noqa: F401
import infrasim.cli.backtest  # noqa: F401
import infrasim.cli.config_cmd  # noqa: F401
import infrasim.cli.analyze  # noqa: F401
import infrasim.cli.daemon_cmd  # noqa: F401
import infrasim.cli.diff_cmd  # noqa: F401
import infrasim.cli.discovery  # noqa: F401
import infrasim.cli.evaluate  # noqa: F401
import infrasim.cli.feeds  # noqa: F401
import infrasim.cli.ops  # noqa: F401
import infrasim.cli.predictive  # noqa: F401
import infrasim.cli.quickstart  # noqa: F401
import infrasim.cli.simulate  # noqa: F401
import infrasim.cli.history_cmd  # noqa: F401
import infrasim.cli.auto_fix  # noqa: F401
import infrasim.cli.tf_check  # noqa: F401
import infrasim.cli.nl_command  # noqa: F401
import infrasim.cli.genome  # noqa: F401
import infrasim.cli.sla_cmd  # noqa: F401
import infrasim.cli.marketplace_cmd  # noqa: F401
import infrasim.cli.dna_cmd  # noqa: F401
import infrasim.cli.supply_chain_cmd  # noqa: F401
import infrasim.cli.autoscale_cmd  # noqa: F401
import infrasim.cli.replay_cmd  # noqa: F401
import infrasim.cli.drift_cmd  # noqa: F401
import infrasim.cli.advisor_cmd  # noqa: F401

__all__ = ["app", "_print_dynamic_results"]
