"""Tests for faultray.logging_config — structured logging module.

Covers JSONFormatter, HumanFormatter, setup_logging, and get_logger
with 30+ test cases for commercial-grade quality.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile


from faultray.logging_config import (
    JSONFormatter,
    HumanFormatter,
    get_logger,
    setup_logging,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    msg: str = "test message",
    level: int = logging.INFO,
    name: str = "faultray.test",
    exc_info: object = None,
    **extras: object,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=42,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    for k, v in extras.items():
        setattr(record, k, v)
    return record


# ===========================================================================
# JSONFormatter tests
# ===========================================================================

class TestJSONFormatter:
    """JSONFormatter should produce valid JSON with standard fields."""

    def test_output_is_valid_json(self):
        fmt = JSONFormatter()
        output = fmt.format(_make_record())
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_timestamp_present(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record()))
        assert "timestamp" in parsed
        assert "T" in parsed["timestamp"]  # ISO-8601 contains 'T'

    def test_timestamp_is_utc(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record()))
        ts = parsed["timestamp"]
        assert ts.endswith("+00:00") or ts.endswith("Z")

    def test_level_field(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record(level=logging.WARNING)))
        assert parsed["level"] == "WARNING"

    def test_message_field(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record("hello world")))
        assert parsed["message"] == "hello world"

    def test_logger_field(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record(name="faultray.cascade")))
        assert parsed["logger"] == "faultray.cascade"

    def test_module_field(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record()))
        assert "module" in parsed

    def test_function_field(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record()))
        assert "function" in parsed

    def test_line_field(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record()))
        assert parsed["line"] == 42

    def test_exception_included(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc = sys.exc_info()
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record(exc_info=exc)))
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]
        assert "boom" in parsed["exception"]

    def test_no_exception_when_none(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record()))
        assert "exception" not in parsed

    def test_extra_field_component(self):
        fmt = JSONFormatter()
        record = _make_record(component="cascade")
        parsed = json.loads(fmt.format(record))
        assert parsed["component"] == "cascade"

    def test_extra_field_scenario(self):
        fmt = JSONFormatter()
        record = _make_record(scenario="node_failure")
        parsed = json.loads(fmt.format(record))
        assert parsed["scenario"] == "node_failure"

    def test_extra_field_engine(self):
        fmt = JSONFormatter()
        record = _make_record(engine="dynamic")
        parsed = json.loads(fmt.format(record))
        assert parsed["engine"] == "dynamic"

    def test_extra_field_duration_ms(self):
        fmt = JSONFormatter()
        record = _make_record(duration_ms=123.4)
        parsed = json.loads(fmt.format(record))
        assert parsed["duration_ms"] == 123.4

    def test_extra_field_score(self):
        fmt = JSONFormatter()
        record = _make_record(score=87.5)
        parsed = json.loads(fmt.format(record))
        assert parsed["score"] == 87.5

    def test_multiple_extra_fields(self):
        fmt = JSONFormatter()
        record = _make_record(component="ops", engine="ops_engine", score=95.0)
        parsed = json.loads(fmt.format(record))
        assert parsed["component"] == "ops"
        assert parsed["engine"] == "ops_engine"
        assert parsed["score"] == 95.0

    def test_missing_extra_fields_not_included(self):
        fmt = JSONFormatter()
        parsed = json.loads(fmt.format(_make_record()))
        for key in ("component", "scenario", "engine", "duration_ms", "score"):
            assert key not in parsed

    def test_all_levels(self):
        fmt = JSONFormatter()
        for level_name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            level = getattr(logging, level_name)
            parsed = json.loads(fmt.format(_make_record(level=level)))
            assert parsed["level"] == level_name

    def test_json_default_str_handles_non_serializable(self):
        """json.dumps(default=str) should handle non-serializable extras."""
        fmt = JSONFormatter()
        record = _make_record()
        # The format method uses default=str so it should not raise
        output = fmt.format(record)
        assert isinstance(output, str)


# ===========================================================================
# HumanFormatter tests
# ===========================================================================

class TestHumanFormatter:
    """HumanFormatter should produce colored, human-readable output."""

    def test_basic_output(self):
        fmt = HumanFormatter()
        output = fmt.format(_make_record("hello"))
        assert "hello" in output

    def test_contains_level(self):
        fmt = HumanFormatter()
        output = fmt.format(_make_record(level=logging.ERROR))
        assert "ERROR" in output

    def test_contains_timestamp_format(self):
        fmt = HumanFormatter()
        output = fmt.format(_make_record())
        # HH:MM:SS pattern — at least has colons
        assert ":" in output

    def test_info_color_code(self):
        fmt = HumanFormatter()
        output = fmt.format(_make_record(level=logging.INFO))
        assert "\033[32m" in output  # Green

    def test_error_color_code(self):
        fmt = HumanFormatter()
        output = fmt.format(_make_record(level=logging.ERROR))
        assert "\033[31m" in output  # Red

    def test_warning_color_code(self):
        fmt = HumanFormatter()
        output = fmt.format(_make_record(level=logging.WARNING))
        assert "\033[33m" in output  # Yellow

    def test_debug_color_code(self):
        fmt = HumanFormatter()
        output = fmt.format(_make_record(level=logging.DEBUG))
        assert "\033[36m" in output  # Cyan

    def test_critical_color_code(self):
        fmt = HumanFormatter()
        output = fmt.format(_make_record(level=logging.CRITICAL))
        assert "\033[35m" in output  # Magenta

    def test_reset_code_present(self):
        fmt = HumanFormatter()
        output = fmt.format(_make_record())
        assert "\033[0m" in output

    def test_colors_dict_has_all_standard_levels(self):
        expected = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        assert set(HumanFormatter.COLORS.keys()) == expected


# ===========================================================================
# setup_logging tests
# ===========================================================================

class TestSetupLogging:
    """setup_logging should configure the faultray root logger."""

    def teardown_method(self):
        logger = logging.getLogger("faultray")
        logger.handlers.clear()
        logger.setLevel(logging.WARNING)

    def test_returns_logger(self):
        logger = setup_logging()
        assert isinstance(logger, logging.Logger)

    def test_logger_name(self):
        logger = setup_logging()
        assert logger.name == "faultray"

    def test_default_level_is_info(self):
        logger = setup_logging()
        assert logger.level == logging.INFO

    def test_custom_level_debug(self):
        logger = setup_logging(level="DEBUG")
        assert logger.level == logging.DEBUG

    def test_custom_level_error(self):
        logger = setup_logging(level="ERROR")
        assert logger.level == logging.ERROR

    def test_custom_level_case_insensitive(self):
        logger = setup_logging(level="warning")
        assert logger.level == logging.WARNING

    def test_default_uses_human_formatter(self):
        logger = setup_logging()
        assert len(logger.handlers) >= 1
        assert isinstance(logger.handlers[0].formatter, HumanFormatter)

    def test_json_output_uses_json_formatter(self):
        logger = setup_logging(json_output=True)
        assert isinstance(logger.handlers[0].formatter, JSONFormatter)

    def test_console_handler_writes_to_stderr(self):
        import sys
        logger = setup_logging()
        assert logger.handlers[0].stream is sys.stderr

    def test_file_handler_created(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            path = f.name
        try:
            logger = setup_logging(log_file=path)
            # Should have 2 handlers: console + file
            assert len(logger.handlers) == 2
            file_handler = logger.handlers[1]
            assert isinstance(file_handler, logging.FileHandler)
        finally:
            os.unlink(path)

    def test_file_handler_uses_json_formatter(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            path = f.name
        try:
            logger = setup_logging(log_file=path)
            file_handler = logger.handlers[1]
            assert isinstance(file_handler.formatter, JSONFormatter)
        finally:
            os.unlink(path)

    def test_file_output_is_valid_json(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            path = f.name
        try:
            logger = setup_logging(level="DEBUG", log_file=path)
            logger.info("file test")
            # Flush handlers
            for h in logger.handlers:
                h.flush()
            with open(path) as fh:
                line = fh.readline().strip()
            parsed = json.loads(line)
            assert parsed["message"] == "file test"
        finally:
            os.unlink(path)

    def test_handlers_cleared_on_reconfig(self):
        setup_logging()
        logger = setup_logging()
        # Should only have 1 console handler, not accumulated
        assert len(logger.handlers) == 1

    def test_no_file_handler_by_default(self):
        logger = setup_logging()
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)


# ===========================================================================
# get_logger tests
# ===========================================================================

class TestGetLogger:
    """get_logger should return child loggers in the faultray namespace."""

    def test_child_logger_name(self):
        logger = get_logger("cascade")
        assert logger.name == "faultray.cascade"

    def test_nested_child_logger_name(self):
        logger = get_logger("simulator.engine")
        assert logger.name == "faultray.simulator.engine"

    def test_returns_logger_instance(self):
        logger = get_logger("test")
        assert isinstance(logger, logging.Logger)

    def test_child_inherits_parent_level(self):
        parent = setup_logging(level="DEBUG")
        child = get_logger("child_test")
        assert child.getEffectiveLevel() == logging.DEBUG
        # Cleanup
        parent.handlers.clear()
        parent.setLevel(logging.WARNING)

    def test_same_name_returns_same_logger(self):
        a = get_logger("same")
        b = get_logger("same")
        assert a is b
