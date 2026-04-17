# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Privacy-respecting, opt-in usage analytics for FaultRay.

Design principles
-----------------
* **Disabled by default** — no data leaves the machine until the user
  explicitly opts in via ``faultray config set telemetry.enabled true``
  or ``FAULTRAY_TELEMETRY=1``.
* **GDPR / APPI compliant** — only aggregate, non-identifying data is
  collected.  No IP addresses, no file paths, no component names, no
  simulation result content.
* **Non-blocking** — all network calls happen in a background daemon
  thread; they never slow down the CLI.
* **Graceful failure** — every external call is guarded; if the backend
  is unreachable the product continues normally.
* **Rate-limited** — at most MAX_EVENTS_PER_SESSION events per process
  lifetime to prevent accidental spam.

Backends
--------
1. **PostHog** (primary, optional dependency ``posthog-python``).
2. **Local JSONL file** — ``~/.faultray/telemetry.jsonl`` — used when
   PostHog is not configured or as a pre-flush buffer.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import platform
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_EVENTS_PER_SESSION: int = 100
FLUSH_INTERVAL_SECONDS: int = 60

_FAULTRAY_DIR: Path = Path.home() / ".faultray"
_TELEMETRY_ID_FILE: Path = _FAULTRAY_DIR / "telemetry_id"
_LOCAL_JSONL_FILE: Path = _FAULTRAY_DIR / "telemetry.jsonl"

# First-run notice shown once when the user has not yet seen the telemetry
# opt-in prompt (stored as a sentinel file).
_NOTICE_SHOWN_FILE: Path = _FAULTRAY_DIR / ".telemetry_notice_shown"

_FIRST_RUN_NOTICE = """\
╔══════════════════════════════════════════════════════════════════╗
║  FaultRay Anonymous Usage Analytics                             ║
║                                                                  ║
║  FaultRay collects anonymous usage data to improve the product. ║
║  No personal data, infrastructure details, file paths or        ║
║  simulation results are ever collected.                         ║
║                                                                  ║
║  What IS collected:                                              ║
║    • CLI command names (not arguments)                           ║
║    • FaultRay / Python / OS version                              ║
║    • Command execution time and component count (bucketed)       ║
║    • Exception class names (not messages or tracebacks)          ║
║                                                                  ║
║  To opt in:   faultray config set telemetry.enabled true         ║
║  To opt out:  faultray config set telemetry.enabled false        ║
║               (or set env var FAULTRAY_TELEMETRY=0)              ║
║                                                                  ║
║  Telemetry is DISABLED by default.                               ║
╚══════════════════════════════════════════════════════════════════╝
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bucket_component_count(count: int) -> str:
    """Return a privacy-safe bucket string for a component count."""
    if count <= 10:
        return "1-10"
    if count <= 50:
        return "11-50"
    if count <= 200:
        return "51-200"
    return "200+"


def _get_or_create_anonymous_id() -> str:
    """Return a stable, random anonymous install UUID.

    The UUID is generated once and stored in ``~/.faultray/telemetry_id``.
    It contains no identifying information.
    """
    try:
        _FAULTRAY_DIR.mkdir(parents=True, exist_ok=True)
        if _TELEMETRY_ID_FILE.exists():
            stored = _TELEMETRY_ID_FILE.read_text().strip()
            if stored:
                return stored
        new_id = str(uuid.uuid4())
        _TELEMETRY_ID_FILE.write_text(new_id)
        return new_id
    except Exception:
        # Fall back to an in-process random ID that won't persist
        return str(uuid.uuid4())


def _show_first_run_notice() -> None:
    """Print the one-time privacy notice if it has not been shown before."""
    try:
        if _NOTICE_SHOWN_FILE.exists():
            return
        print(_FIRST_RUN_NOTICE, file=sys.stderr)
        _FAULTRAY_DIR.mkdir(parents=True, exist_ok=True)
        _NOTICE_SHOWN_FILE.touch()
    except Exception:
        pass


def _session_common_properties() -> dict[str, Any]:
    """Return session-level properties that are safe to collect."""
    try:
        from faultray import __version__ as fr_version
    except Exception:
        fr_version = "unknown"

    return {
        "faultray_version": fr_version,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "os_type": platform.system(),  # e.g. "Linux", "Darwin", "Windows"
    }


# ---------------------------------------------------------------------------
# PostHog backend (optional)
# ---------------------------------------------------------------------------


def _try_import_posthog() -> Any:  # returns posthog module or None
    try:
        import posthog  # type: ignore[import-untyped]
        return posthog
    except ImportError:
        return None


def _send_posthog(
    api_key: str,
    endpoint: str,
    anonymous_id: str,
    event: str,
    properties: dict[str, Any],
) -> None:
    """Send a single event to PostHog.  Errors are swallowed silently."""
    posthog = _try_import_posthog()
    if posthog is None:
        return
    try:
        posthog.api_key = api_key
        posthog.host = endpoint
        posthog.capture(
            distinct_id=anonymous_id,
            event=event,
            properties=properties,
        )
        posthog.flush()
    except Exception as exc:
        logger.debug("PostHog send failed (silenced): %s", exc)


# ---------------------------------------------------------------------------
# Local JSONL fallback
# ---------------------------------------------------------------------------


def _append_to_local_jsonl(record: dict[str, Any]) -> None:
    """Append a JSON-serialisable record to the local JSONL file."""
    try:
        _FAULTRAY_DIR.mkdir(parents=True, exist_ok=True)
        with _LOCAL_JSONL_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Local JSONL write failed (silenced): %s", exc)


# ---------------------------------------------------------------------------
# Core Telemetry class
# ---------------------------------------------------------------------------


class Telemetry:
    """Privacy-first, opt-in usage analytics.

    All state is protected by a lock so the class is safe to call from
    multiple threads (e.g. background flush thread + main thread).
    """

    def __init__(self, enabled: bool = False) -> None:
        self._enabled: bool = enabled
        self._lock: threading.Lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._session_count: int = 0  # total events tracked this session
        self._anonymous_id: str | None = None
        self._flush_thread: threading.Thread | None = None
        self._stop_flush: threading.Event = threading.Event()

        # Config cache (populated lazily on first track/flush call)
        self._posthog_api_key: str = ""
        self._posthog_endpoint: str = "https://app.posthog.com"
        self._local_fallback: bool = True
        self._config_loaded: bool = False

        # Register atexit flush so events are sent on clean process exit
        atexit.register(self._atexit_flush)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        with self._lock:
            self._enabled = value

    def enable(self) -> None:
        """Enable telemetry collection and start background flush thread."""
        with self._lock:
            self._enabled = True
        self._ensure_flush_thread()

    def disable(self) -> None:
        """Disable telemetry and discard pending events."""
        with self._lock:
            self._enabled = False
            self._events.clear()
        self._stop_flush_thread()

    def track(self, event: str, properties: dict[str, Any] | None = None) -> None:
        """Track a single event.

        The call returns immediately — any I/O happens in a background thread.
        If telemetry is disabled this is a no-op.

        Args:
            event: Short event name, e.g. ``"command.simulate"``.
            properties: Optional dict of **non-identifying** metadata.
        """
        if not self._enabled:
            return
        with self._lock:
            if self._session_count >= MAX_EVENTS_PER_SESSION:
                return  # rate limit reached
            self._load_config_once()
            props = dict(self._get_anonymous_id_props())
            props.update(_session_common_properties())
            props["timestamp"] = datetime.now(timezone.utc).isoformat()
            if properties:
                # Sanitise: only allow safe scalar types
                props.update(self._sanitise_properties(properties))
            record = {"event": event, "properties": props}
            self._events.append(record)
            self._session_count += 1

        self._ensure_flush_thread()

    def flush(self) -> list[dict[str, Any]]:
        """Flush pending events to the configured backend(s).

        Returns the list of events that were flushed (useful for tests).
        This method is intentionally synchronous so it can be called from
        the background thread or from tests.
        """
        with self._lock:
            if not self._events:
                return []
            events = list(self._events)
            self._events.clear()

        flushed: list[dict[str, Any]] = []
        for record in events:
            try:
                self._dispatch(record)
                flushed.append(record)
            except Exception as exc:
                logger.debug("Telemetry dispatch error (silenced): %s", exc)

        if flushed:
            logger.debug("Telemetry: flushed %d events", len(flushed))
        return flushed

    @property
    def event_count(self) -> int:
        """Number of events pending in the local buffer."""
        with self._lock:
            return len(self._events)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(
        self,
        *,
        enabled: bool | None = None,
        posthog_api_key: str | None = None,
        posthog_endpoint: str | None = None,
        local_fallback: bool | None = None,
    ) -> None:
        """Programmatic configuration, typically called at startup."""
        with self._lock:
            if enabled is not None:
                self._enabled = enabled
            if posthog_api_key is not None:
                self._posthog_api_key = posthog_api_key
            if posthog_endpoint is not None:
                self._posthog_endpoint = posthog_endpoint
            if local_fallback is not None:
                self._local_fallback = local_fallback

        if self._enabled:
            self._ensure_flush_thread()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_config_once(self) -> None:
        """Load settings from FaultRay config (called with lock held)."""
        if self._config_loaded:
            return
        self._config_loaded = True
        try:
            from faultray.config import get_config
            cfg = get_config()
            tel = cfg.telemetry  # type: ignore[attr-defined]
            self._posthog_api_key = str(tel.get("api_key", "") or "")
            self._posthog_endpoint = str(
                tel.get("endpoint", "https://app.posthog.com") or "https://app.posthog.com"
            )
            self._local_fallback = bool(tel.get("local_fallback", True))
        except Exception as exc:
            logger.debug("Telemetry: could not load config (%s), using defaults", exc)

    def _get_anonymous_id_props(self) -> dict[str, str]:
        """Return ``{"anonymous_id": "<uuid>"}``; cached after first call."""
        if self._anonymous_id is None:
            self._anonymous_id = _get_or_create_anonymous_id()
        return {"anonymous_id": self._anonymous_id}

    @staticmethod
    def _sanitise_properties(props: dict[str, Any]) -> dict[str, Any]:
        """Keep only safe scalar values from a properties dict.

        Drops any value that is not a str, int, float, or bool so that
        paths, large objects, or other PII cannot accidentally leak.
        """
        safe: dict[str, Any] = {}
        for key, value in props.items():
            if isinstance(value, (str, int, float, bool)):
                safe[key] = value
        return safe

    def _dispatch(self, record: dict[str, Any]) -> None:
        """Send one event record to the appropriate backend(s)."""
        event = record["event"]
        props = record["properties"]

        if self._posthog_api_key:
            _send_posthog(
                api_key=self._posthog_api_key,
                endpoint=self._posthog_endpoint,
                anonymous_id=props.get("anonymous_id", "anonymous"),
                event=event,
                properties=props,
            )
        elif self._local_fallback:
            _append_to_local_jsonl(record)

    def _ensure_flush_thread(self) -> None:
        """Start the background flush thread if not already running."""
        with self._lock:
            if (
                self._flush_thread is not None
                and self._flush_thread.is_alive()
            ):
                return
            self._stop_flush.clear()
            t = threading.Thread(
                target=self._flush_loop,
                name="faultray-telemetry-flush",
                daemon=True,
            )
            self._flush_thread = t
        # Start outside the lock to avoid potential deadlock
        t.start()

    def _stop_flush_thread(self) -> None:
        """Signal the flush thread to stop."""
        self._stop_flush.set()

    def _flush_loop(self) -> None:
        """Background loop: flush every FLUSH_INTERVAL_SECONDS seconds."""
        while not self._stop_flush.wait(timeout=FLUSH_INTERVAL_SECONDS):
            try:
                self.flush()
            except Exception as exc:
                logger.debug("Telemetry flush loop error (silenced): %s", exc)

    def _atexit_flush(self) -> None:
        """Flush remaining events on clean process exit."""
        if not self._enabled:
            return
        try:
            self.flush()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Module-level initialisation
# ---------------------------------------------------------------------------


def _build_global_telemetry() -> Telemetry:
    """Read environment + config and return a configured Telemetry instance."""
    # Environment variable overrides everything
    env_val = os.environ.get("FAULTRAY_TELEMETRY", "").strip()
    if env_val in ("1", "true", "yes"):
        env_enabled: bool | None = True
    elif env_val in ("0", "false", "no"):
        env_enabled = False
    else:
        env_enabled = None

    instance = Telemetry(enabled=False)

    # Try to load from config file
    try:
        from faultray.config import get_config
        cfg = get_config()
        # Ensure the telemetry section exists on the config object
        if not hasattr(cfg, "telemetry"):
            # Config predates telemetry section — treat as disabled
            tel_cfg: dict[str, Any] = {}
        else:
            tel_cfg = cfg.telemetry  # type: ignore[attr-defined]

        cfg_enabled: bool = bool(tel_cfg.get("enabled", False))
        api_key: str = str(tel_cfg.get("api_key", "") or "")
        endpoint: str = str(tel_cfg.get("endpoint", "https://app.posthog.com") or "https://app.posthog.com")
        local_fallback: bool = bool(tel_cfg.get("local_fallback", True))
    except Exception:
        cfg_enabled = False
        api_key = ""
        endpoint = "https://app.posthog.com"
        local_fallback = True

    # Environment always wins
    final_enabled = env_enabled if env_enabled is not None else cfg_enabled

    instance.configure(
        enabled=final_enabled,
        posthog_api_key=api_key,
        posthog_endpoint=endpoint,
        local_fallback=local_fallback,
    )
    # Mark config as already loaded to avoid a second load on first track()
    instance._config_loaded = True  # noqa: SLF001

    return instance


# Global singleton — disabled by default; re-initialised at CLI startup via
# ``init_telemetry()``.
telemetry: Telemetry = Telemetry(enabled=False)


def init_telemetry() -> Telemetry:
    """Initialise (or reinitialise) the global telemetry instance.

    Call this once at CLI startup after the config system is available.
    Shows the one-time privacy notice if it has not been displayed before.
    Returns the global instance for convenience.
    """
    global telemetry  # noqa: PLW0603
    _show_first_run_notice()
    telemetry = _build_global_telemetry()
    return telemetry
