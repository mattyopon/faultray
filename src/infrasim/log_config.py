"""Structured logging configuration for FaultZero."""

import logging
import sys


def setup_logging(level: str = "WARNING", json_format: bool = False) -> None:
    """Configure structured logging for FaultZero.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, emit JSON-formatted log lines to stderr.
    """
    root = logging.getLogger("infrasim")
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
