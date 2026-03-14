"""Privacy-respecting, opt-in usage analytics.

Telemetry is disabled by default.  Users must explicitly opt in before any
data is collected.  Even when enabled, data is only stored locally until
``flush()`` is called.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class Telemetry:
    """Opt-in, privacy-respecting usage analytics."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._events: list[dict] = []

    def track(self, event: str, properties: dict | None = None) -> None:
        """Track an event locally. Only sent if user opts in."""
        if not self.enabled:
            return
        self._events.append({
            "event": event,
            "properties": properties or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def flush(self) -> list[dict]:
        """Send events to analytics backend (stub -- just logs).

        Returns the list of events that were flushed (for testing).
        """
        flushed: list[dict] = []
        if self._events:
            logger.info("Telemetry: %d events tracked", len(self._events))
            flushed = list(self._events)
            self._events.clear()
        return flushed

    @property
    def event_count(self) -> int:
        """Number of pending events."""
        return len(self._events)

    def enable(self) -> None:
        """Enable telemetry collection."""
        self.enabled = True

    def disable(self) -> None:
        """Disable telemetry collection and clear pending events."""
        self.enabled = False
        self._events.clear()


# Global instance -- disabled by default
telemetry = Telemetry(enabled=False)
