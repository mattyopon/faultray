# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""FaultRay exception hierarchy.

All custom exceptions inherit from :class:`FaultRayError` so callers can
catch the entire family with a single ``except FaultRayError``.

For backward compatibility the leaf classes also inherit from the stdlib
exception they replace (``ValueError``, ``KeyError``, ``RuntimeError``)
so existing ``except`` handlers continue to work.
"""


class FaultRayError(Exception):
    """Base exception for all FaultRay errors."""


class ComponentNotFoundError(FaultRayError, KeyError):
    """Raised when a component ID is not found in the graph."""


class ValidationError(FaultRayError, ValueError):
    """Raised when input validation fails (YAML, parameters, etc.)."""


class ConfigurationError(FaultRayError, ValueError):
    """Raised when configuration is missing or invalid."""


class ExternalServiceError(FaultRayError, RuntimeError):
    """Raised when an external service (AWS/GCP/Prometheus) fails."""


class SimulationError(FaultRayError, RuntimeError):
    """Raised when a simulation engine encounters an unrecoverable error."""


class PluginError(FaultRayError):
    """Raised when a plugin fails to load or execute."""
