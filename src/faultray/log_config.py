# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Structured logging configuration for FaultRay."""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Get a properly configured logger for a module.

    Returns a logger under the ``faultray`` namespace so that all module
    loggers are children of the root ``faultray`` logger configured by
    :func:`setup_logging`.
    """
    return logging.getLogger(f"faultray.{name}")


def setup_logging(level: str = "WARNING", json_format: bool = False) -> None:
    """Configure structured logging for FaultRay.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, emit JSON-formatted log lines to stderr.
    """
    root = logging.getLogger("faultray")
    root.setLevel(getattr(logging, level.upper(), logging.WARNING))

    # Avoid adding duplicate handlers on repeated calls
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    if json_format:
        formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s",'
            '"module":"%(name)s","message":"%(message)s"}'
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    handler.setFormatter(formatter)
    root.addHandler(handler)
