# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI package for FaultRay.

Re-exports the Typer ``app`` so that ``faultray.cli:app`` keeps working as the
entry-point defined in pyproject.toml.  Submodules register their commands by
importing ``app`` from :mod:`faultray.cli.main` at import time.

Command modules are discovered and loaded lazily: they are imported the first
time the CLI is actually invoked (not at ``import`` time).  If a single command
module has a bug, other commands still work — the broken module is skipped with
a warning.
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

from faultray.cli.main import (  # noqa: F401 — re-export
    _print_dynamic_results,
    app,
)

logger = logging.getLogger(__name__)

_CLI_DIR = Path(__file__).parent
_commands_loaded = False

# Canonical load order — preserves the original registration sequence so that
# when two modules define the same command name the later one wins (matching
# the previous eager-import behaviour).  Any *new* modules added to the cli/
# directory will be auto-discovered and appended alphabetically.
_KNOWN_MODULES: list[str] = [
    "admin",
    "backtest",
    "config_cmd",
    "analyze",
    "daemon_cmd",
    "diff_cmd",
    "discovery",
    "evaluate",
    "feeds",
    "ops",
    "predictive",
    "quickstart",
    "simulate",
    "history_cmd",
    "auto_fix",
    "tf_check",
    "nl_command",
    "genome",
    "sla_cmd",
    "marketplace_cmd",
    "dna_cmd",
    "supply_chain_cmd",
    "autoscale_cmd",
    "replay_cmd",
    "drift_cmd",
    "advisor_cmd",
    "timeline_cmd",
    "benchmark_cmd",
    "twin_cmd",
    "calendar_cmd",
    "evidence_cmd",
    "export_cmd",
    "fuzz_cmd",
    "replay_timeline_cmd",
    "slo_budget_cmd",
    "ask_cmd",
    "runbook_cmd",
    "deps_cmd",
    "git_track_cmd",
    "graph_export_cmd",
    "heatmap_cmd",
    "report_cmd",
    "contract_cmd",
    "canary_cmd",
    "multienv_cmd",
    "cost_attr_cmd",
    "plugin_cmd",
    "topology_diff_cmd",
    "optimizer_cmd",
    "anomaly_cmd",
    "sre_maturity_cmd",
    "postmortem_cmd",
    "env_compare_cmd",
    "template_cmd",
    "team_cmd",
    "compliance_monitor_cmd",
    "gate_cmd",
    "war_room_cmd",
    "cost_optimize_cmd",
    "antipattern_cmd",
    "ab_test_cmd",
    "fmea_cmd",
    "monkey_cmd",
    "import_metrics_cmd",
    "budget_cmd",
    "velocity_cmd",
    "attack_surface_cmd",
    "score_cmd",
    "cost_impact_cmd",
    "init_cmd",
    "agent_cmd",
]


def _register_commands() -> None:
    """Import CLI command modules so their ``@app.command()`` decorators run.

    Modules are loaded in the canonical order defined by ``_KNOWN_MODULES``,
    followed by any newly-added modules discovered via filesystem glob.

    Each module is imported inside its own ``try`` / ``except`` block so that
    a broken module does not prevent the rest of the CLI from working.
    """
    global _commands_loaded  # noqa: PLW0603
    if _commands_loaded:
        return
    _commands_loaded = True

    known_set = set(_KNOWN_MODULES)

    # Discover any new modules not in the explicit list.
    extra: list[str] = []
    for cmd_file in sorted(_CLI_DIR.glob("*.py")):
        if cmd_file.name.startswith("_") or cmd_file.name == "main.py":
            continue
        stem = cmd_file.stem
        if stem not in known_set:
            extra.append(stem)

    for stem in (*_KNOWN_MODULES, *extra):
        module_name = f"faultray.cli.{stem}"
        if module_name in sys.modules:
            continue
        try:
            importlib.import_module(module_name)
        except Exception:
            logger.warning(
                "Failed to load CLI command module %s",
                module_name,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Lazy loading hook
# ---------------------------------------------------------------------------
# We patch ``typer.main.get_command`` so that command modules are imported just
# before Typer builds the Click command tree.  ``get_command`` is called by both
# ``Typer.__call__`` (production entry-point) and ``CliRunner.invoke`` (tests).
#
# ``typer.testing`` imports ``get_command`` as a local name at its own import
# time, so we must also patch that reference.  We handle both the case where
# ``typer.testing`` is already imported and where it is imported later (via a
# lightweight ``sys.meta_path`` hook that removes itself after first use).
# ---------------------------------------------------------------------------

import typer.main as _typer_main  # noqa: E402

_original_get_command = _typer_main.get_command


def _lazy_get_command(typer_instance: object, *args: object, **kwargs: object) -> object:
    """Load all CLI command modules before Typer resolves commands."""
    _register_commands()
    return _original_get_command(typer_instance, *args, **kwargs)


_typer_main.get_command = _lazy_get_command  # type: ignore[assignment]


def _patch_typer_testing() -> bool:
    """Patch ``typer.testing._get_command`` if the module is loaded. Returns True if patched."""
    mod = sys.modules.get("typer.testing")
    if mod is not None and getattr(mod, "_get_command", None) is not _lazy_get_command:
        mod._get_command = _lazy_get_command  # type: ignore[attr-defined]
        return True
    return False


# Patch now if already imported.
if not _patch_typer_testing():
    # Otherwise, install a one-shot import hook.
    class _PatchTyperTesting:
        """One-shot meta-path hook: patches typer.testing after it is imported."""

        def find_module(self, fullname: str, path: object = None) -> object:  # noqa: ANN401
            if fullname == "typer.testing":
                return self
            return None

        def load_module(self, fullname: str) -> object:  # noqa: ANN401
            sys.meta_path.remove(self)  # one-shot: remove before re-importing
            mod = importlib.import_module(fullname)
            _patch_typer_testing()
            return mod

    sys.meta_path.insert(0, _PatchTyperTesting())  # type: ignore[arg-type]


__all__ = ["app", "_print_dynamic_results"]
