"""Unit tests for src/utils/logging_utils.py."""

from __future__ import annotations

import json
import logging

from src.utils.logging_utils import get_logger, get_request_id, set_request_id


class TestRequestId:
    def test_default_request_id(self):
        # Before any set_request_id call, default is "-"
        assert get_request_id() == "-" or isinstance(get_request_id(), str)

    def test_set_and_get_request_id(self):
        set_request_id("abc123")
        assert get_request_id() == "abc123"

    def test_set_request_id_overwrites(self):
        set_request_id("first")
        set_request_id("second")
        assert get_request_id() == "second"


class TestGetLogger:
    def test_returns_logger_instance(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)

    def test_logger_name_matches(self):
        logger = get_logger("my.component")
        assert logger.name == "my.component"

    def test_repeated_calls_same_logger(self):
        a = get_logger("same.name")
        b = get_logger("same.name")
        assert a is b


class TestJsonOutput:
    def test_log_record_is_valid_json(self, capsys):
        """JSON formatter should emit parseable lines."""
        from src.utils.logging_utils import _JsonFormatter

        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert "timestamp" in parsed
        assert "module" in parsed
        assert "request_id" in parsed

    def test_request_id_in_output(self):
        from src.utils.logging_utils import _JsonFormatter

        set_request_id("req-xyz")
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        assert parsed["request_id"] == "req-xyz"
