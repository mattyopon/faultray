"""Tests for the telemetry module."""

from __future__ import annotations



class TestTelemetry:
    """Test the Telemetry class."""

    def test_disabled_by_default(self):
        from faultray.telemetry import Telemetry

        t = Telemetry()
        assert t.enabled is False
        assert t.event_count == 0

    def test_track_when_disabled_does_nothing(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=False)
        t.track("test_event", {"key": "value"})
        assert t.event_count == 0

    def test_track_when_enabled_records_event(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=True)
        t.track("simulation_run", {"scenarios": 42})
        assert t.event_count == 1

    def test_track_multiple_events(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=True)
        t.track("event_1")
        t.track("event_2", {"detail": "abc"})
        t.track("event_3")
        assert t.event_count == 3

    def test_event_has_timestamp(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=True)
        t.track("test_event")
        # timestamp is stored inside the properties dict
        assert "timestamp" in t._events[0]["properties"]
        assert "T" in t._events[0]["properties"]["timestamp"]  # ISO format

    def test_event_has_properties(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=True)
        t.track("scan", {"provider": "azure", "components": 10})
        evt = t._events[0]
        assert evt["event"] == "scan"
        assert evt["properties"]["provider"] == "azure"
        assert evt["properties"]["components"] == 10

    def test_flush_clears_events(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=True)
        t.track("event_1")
        t.track("event_2")
        flushed = t.flush()
        assert len(flushed) == 2
        assert t.event_count == 0

    def test_flush_empty_returns_empty(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=True)
        flushed = t.flush()
        assert flushed == []

    def test_enable_method(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=False)
        t.enable()
        assert t.enabled is True
        t.track("event")
        assert t.event_count == 1

    def test_disable_clears_pending(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=True)
        t.track("event_1")
        t.track("event_2")
        t.disable()
        assert t.enabled is False
        assert t.event_count == 0

    def test_global_instance_disabled(self):
        from faultray.telemetry import telemetry

        assert telemetry.enabled is False

    def test_track_with_none_properties(self):
        from faultray.telemetry import Telemetry

        t = Telemetry(enabled=True)
        t.track("event", None)
        # Properties always contain at least the common session fields
        # (anonymous_id, faultray_version, python_version, os_type, timestamp)
        props = t._events[0]["properties"]
        assert isinstance(props, dict)
        assert "timestamp" in props
        assert "python_version" in props
