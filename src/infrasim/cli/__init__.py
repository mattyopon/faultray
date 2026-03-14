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
import infrasim.cli.analyze  # noqa: F401
import infrasim.cli.discovery  # noqa: F401
import infrasim.cli.evaluate  # noqa: F401
import infrasim.cli.feeds  # noqa: F401
import infrasim.cli.ops  # noqa: F401
import infrasim.cli.predictive  # noqa: F401
import infrasim.cli.simulate  # noqa: F401

__all__ = ["app", "_print_dynamic_results"]
