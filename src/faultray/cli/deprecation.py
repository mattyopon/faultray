# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""CLI deprecation warning mechanism (#86).

Provides a small helper so CLI commands / options can be marked
deprecated and a visible warning surfaces on every call until the
planned removal version.

Usage::

    from faultray.cli.deprecation import deprecated_command

    @app.command()
    @deprecated_command(
        reason="Use `faultray financial run` instead",
        removed_in="12.0.0",
    )
    def old_financial():
        ...

Suppress with ``FAULTRAY_SUPPRESS_DEPRECATION=1`` in scripts.
"""

from __future__ import annotations

import functools
import os
import sys
import warnings
from collections.abc import Callable
from typing import Any


class FaultRayDeprecationWarning(DeprecationWarning):
    """Dedicated warning class so users can filter FaultRay-only signals."""


def deprecated_command(
    *, reason: str, removed_in: str, name: str | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a CLI command function to emit a deprecation warning.

    Args:
        reason: Short rationale + replacement path ("Use ``foo`` instead").
        removed_in: Target removal version (SemVer). Informational only —
            we do not auto-disable at this version; that is a manual op.
        name: Override the command label in the warning message. Defaults
            to the decorated function's ``__name__``.
    """
    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        label = name or fn.__name__

        @functools.wraps(fn)
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            if not _is_deprecation_suppressed():
                _emit_warning(
                    f"CLI command '{label}' is deprecated and will be "
                    f"removed in v{removed_in}. {reason}"
                )
            return fn(*args, **kwargs)

        # Attach metadata for CHANGELOG / help generators.
        _wrapped.__faultray_deprecated__ = {       # type: ignore[attr-defined]
            "reason": reason,
            "removed_in": removed_in,
            "name": label,
        }
        return _wrapped

    return _wrap


def warn_deprecated_option(
    option_name: str, *, reason: str, removed_in: str
) -> None:
    """Imperative form for deprecating an option (when the decorator does
    not fit, e.g. the option is parsed conditionally).

    Usage::

        if args.old_flag is not None:
            warn_deprecated_option(
                "--old-flag",
                reason="Use --new-flag instead",
                removed_in="12.0.0",
            )
    """
    if _is_deprecation_suppressed():
        return
    _emit_warning(
        f"CLI option '{option_name}' is deprecated and will be removed in "
        f"v{removed_in}. {reason}"
    )


def _is_deprecation_suppressed() -> bool:
    return os.environ.get("FAULTRAY_SUPPRESS_DEPRECATION", "").lower() in (
        "1", "true", "yes"
    )


def _emit_warning(message: str) -> None:
    # stderr so it does not pollute JSON output captured from stdout.
    print(f"\x1b[33m[DEPRECATION]\x1b[0m {message}", file=sys.stderr)
    warnings.warn(message, FaultRayDeprecationWarning, stacklevel=3)
