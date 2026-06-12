# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Shared scan lifecycle for the cloud discovery scanners.

Every provider scanner runs the same loop: call each resource scanner,
convert per-service failures into warnings (re-raising only "SDK missing"
style errors), then run post-processing steps with the same warning
treatment. That loop lives here; the scanners keep only provider logic.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

ScannerStep = tuple[str, Callable[[InfraGraph], None]]


class CloudScannerBase:
    """Common warning bookkeeping and scan-loop plumbing for cloud scanners."""

    #: Exceptions from resource scanners that must propagate and abort the
    #: scan (typically a missing provider SDK). Subclasses may override.
    reraise_exceptions: tuple[type[BaseException], ...] = (RuntimeError,)

    def __init__(self) -> None:
        self._warnings: list[str] = []

    def _warn(self, msg: str) -> None:
        """Record *msg* as a scan warning and log it."""
        logger.warning(msg)
        self._warnings.append(msg)

    def _run_scanners(
        self,
        graph: InfraGraph,
        scanners: Sequence[ScannerStep],
        post_processors: Sequence[ScannerStep] = (),
        scan_error_fmt: str = "Failed to scan {name}: {exc}",
    ) -> None:
        """Run resource *scanners* and then *post_processors* against *graph*.

        Failures in individual steps become warnings so one broken service
        does not abort discovery of the rest; ``reraise_exceptions`` (missing
        SDKs etc.) always propagate. ``post_processors`` entries are
        ``(description, fn)`` pairs reported as ``Failed to {description}``.
        """
        for name, scanner_fn in scanners:
            try:
                scanner_fn(graph)
            except self.reraise_exceptions:
                raise
            except Exception as exc:
                self._warn(scan_error_fmt.format(name=name, exc=exc))

        for description, post_fn in post_processors:
            try:
                post_fn(graph)
            except Exception as exc:
                self._warn(f"Failed to {description}: {exc}")
