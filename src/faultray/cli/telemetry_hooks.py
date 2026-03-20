# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""CLI telemetry integration for FaultRay.

Provides
--------
* ``@track_command`` — Typer command decorator that records command name and
  wall-clock execution time.  Import and apply to any ``@app.command()``
  function **without** modifying ``cli/main.py``.

* ``track_engine_usage(engine_name)`` — call from engine entry-points to
  record which simulation engine was invoked.

* ``install_error_hook()`` — installs ``sys.excepthook`` to capture
  unhandled exception *class names* (never messages or tracebacks).

* ``get_telemetry()`` — returns the initialised global :class:`Telemetry`
  instance, initialising it on first call if needed.

Usage example (in any CLI command module)
-----------------------------------------
::

    from faultray.cli.telemetry_hooks import track_command

    @app.command()
    @track_command
    def simulate(model: Path = DEFAULT_MODEL_PATH):
        ...

All calls are fire-and-forget; if the telemetry backend is unreachable the
command continues normally.
"""

from __future__ import annotations

import functools
import sys
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Module-level telemetry accessor
# ---------------------------------------------------------------------------

_telemetry_initialised: bool = False


def get_telemetry():  # noqa: ANN201  (avoids circular import with full type)
    """Return the global :class:`~faultray.telemetry.Telemetry` instance.

    Initialises it on first call so that the config system has time to load
    before any events are dispatched.
    """
    global _telemetry_initialised  # noqa: PLW0603
    from faultray.telemetry import telemetry, init_telemetry

    if not _telemetry_initialised:
        try:
            init_telemetry()
        except Exception:
            pass  # never crash on telemetry init failure
        _telemetry_initialised = True

    return telemetry


# ---------------------------------------------------------------------------
# @track_command decorator
# ---------------------------------------------------------------------------


def track_command(func: F) -> F:
    """Decorator that tracks CLI command invocations.

    Captures:
    * ``command`` — the function name (which matches the CLI sub-command
      name in Typer, e.g. ``"simulate"``, ``"dora"``)
    * ``execution_time_ms`` — wall-clock time in milliseconds
    * ``success`` — ``True`` if the command returned normally, ``False``
      if it raised an exception (exception is always re-raised)

    No arguments, result values, or exception messages are ever recorded.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        command_name: str = func.__name__
        t0 = time.monotonic()
        success = True
        try:
            return func(*args, **kwargs)
        except Exception:
            success = False
            raise
        finally:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            try:
                tel = get_telemetry()
                tel.track(
                    f"command.{command_name}",
                    {
                        "command": command_name,
                        "execution_time_ms": elapsed_ms,
                        "success": success,
                    },
                )
            except Exception:
                pass  # telemetry must never crash the product

    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Engine usage tracking
# ---------------------------------------------------------------------------


def track_engine_usage(engine_name: str, component_count: int | None = None) -> None:
    """Record that a simulation engine was used.

    Args:
        engine_name: Short identifier, e.g. ``"static"``, ``"dynamic"``,
            ``"ops"``.  Must not contain user-controlled data.
        component_count: Optional number of components in the model.
            Stored as a privacy-safe bucket string (e.g. ``"11-50"``), not
            the raw integer.
    """
    try:
        from faultray.telemetry import _bucket_component_count  # noqa: PLC2701

        tel = get_telemetry()
        props: dict[str, Any] = {"engine": engine_name}
        if component_count is not None:
            props["component_count_bucket"] = _bucket_component_count(component_count)
        tel.track("engine.used", props)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# DORA command tracking
# ---------------------------------------------------------------------------


def track_dora_command(subcommand: str) -> None:
    """Record which DORA subcommand was executed.

    Critical for product-market fit measurement.

    Args:
        subcommand: Short name of the DORA subcommand, e.g. ``"assess"``,
            ``"report"``, ``"benchmark"``.
    """
    try:
        tel = get_telemetry()
        tel.track("dora.command", {"subcommand": subcommand})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Unhandled-exception hook
# ---------------------------------------------------------------------------


def install_error_hook() -> None:
    """Install a ``sys.excepthook`` that records unhandled exception types.

    Only the exception *class name* is collected — never the message,
    arguments, or traceback.  The original ``sys.excepthook`` is always
    called afterwards so the user still sees the normal error output.
    """
    _original_excepthook = sys.excepthook

    def _faultray_excepthook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: Any,
    ) -> None:
        try:
            tel = get_telemetry()
            tel.track(
                "error.unhandled",
                {"exception_type": exc_type.__name__},
            )
            # Best-effort immediate flush so the event is not lost on exit
            tel.flush()
        except Exception:
            pass
        finally:
            _original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _faultray_excepthook


# ---------------------------------------------------------------------------
# Feature / module import tracking
# ---------------------------------------------------------------------------


def track_feature_import(module_name: str) -> None:
    """Record that an optional feature module was imported and used.

    Call this at the top of optional feature modules to track adoption.

    Args:
        module_name: Short module identifier, e.g. ``"ai"``, ``"ci"``,
            ``"marketplace"``.  Must be a hard-coded string, never
            user-controlled.
    """
    try:
        tel = get_telemetry()
        tel.track("feature.imported", {"module": module_name})
    except Exception:
        pass
