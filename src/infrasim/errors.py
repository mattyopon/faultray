"""ChaosProof exception hierarchy.

All custom exceptions inherit from :class:`ChaosProofError` so callers can
catch the entire family with a single ``except ChaosProofError``.

For backward compatibility the leaf classes also inherit from the stdlib
exception they replace (``ValueError``, ``KeyError``, ``RuntimeError``)
so existing ``except`` handlers continue to work.
"""


class ChaosProofError(Exception):
    """Base exception for all ChaosProof errors."""


class ComponentNotFoundError(ChaosProofError, KeyError):
    """Raised when a component ID is not found in the graph."""


class ValidationError(ChaosProofError, ValueError):
    """Raised when input validation fails (YAML, parameters, etc.)."""


class ConfigurationError(ChaosProofError, ValueError):
    """Raised when configuration is missing or invalid."""


class ExternalServiceError(ChaosProofError, RuntimeError):
    """Raised when an external service (AWS/GCP/Prometheus) fails."""


class SimulationError(ChaosProofError, RuntimeError):
    """Raised when a simulation engine encounters an unrecoverable error."""


class PluginError(ChaosProofError):
    """Raised when a plugin fails to load or execute."""
