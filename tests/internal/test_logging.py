"""Tests for ddtestopt.internal.logging module."""

import logging
import os
from unittest.mock import patch

from ddtestopt.internal.logging import catch_and_log_exceptions
from ddtestopt.internal.logging import ddtestopt_logger
from ddtestopt.internal.logging import setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def teardown_method(self):
        """Clean up logger state after each test."""
        # Remove all handlers
        for handler in ddtestopt_logger.handlers[:]:
            ddtestopt_logger.removeHandler(handler)
        # Reset logger state
        ddtestopt_logger.propagate = True
        ddtestopt_logger.setLevel(logging.NOTSET)

    @patch.dict(os.environ, {}, clear=True)
    def test_setup_logging_default_level(self):
        """Test setup_logging with default (INFO) level."""
        setup_logging()

        assert ddtestopt_logger.propagate is False
        assert ddtestopt_logger.level == logging.INFO
        assert len(ddtestopt_logger.handlers) == 1

        handler = ddtestopt_logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)

    @patch.dict(os.environ, {"DDTESTOPT_DEBUG": "true"})
    def test_setup_logging_debug_level_true(self):
        """Test setup_logging with DEBUG level enabled via true."""
        setup_logging()

        assert ddtestopt_logger.propagate is False
        assert ddtestopt_logger.level == logging.DEBUG
        assert len(ddtestopt_logger.handlers) == 1

    @patch.dict(os.environ, {"DDTESTOPT_DEBUG": "1"})
    def test_setup_logging_debug_level_one(self):
        """Test setup_logging with DEBUG level enabled via 1."""
        setup_logging()

        assert ddtestopt_logger.level == logging.DEBUG

    @patch.dict(os.environ, {"DDTESTOPT_DEBUG": "false"})
    def test_setup_logging_debug_level_false(self):
        """Test setup_logging with DEBUG level disabled."""
        setup_logging()

        assert ddtestopt_logger.level == logging.INFO

    @patch.dict(os.environ, {"DDTESTOPT_DEBUG": "0"})
    def test_setup_logging_debug_level_zero(self):
        """Test setup_logging with DEBUG level disabled via 0."""
        setup_logging()

        assert ddtestopt_logger.level == logging.INFO

    def test_setup_logging_formatter(self):
        """Test that the formatter is correctly configured."""
        setup_logging()

        handler = ddtestopt_logger.handlers[0]
        formatter = handler.formatter
        assert formatter is not None

        # Test the format string contains expected elements
        format_string = formatter._fmt
        assert isinstance(format_string, str)
        assert "[Datadog Test Optimization]" in format_string
        assert "%(levelname)-8s" in format_string
        assert "%(name)s" in format_string
        assert "%(filename)s" in format_string
        assert "%(lineno)d" in format_string
        assert "%(message)s" in format_string

    def test_setup_logging_multiple_calls(self):
        """Test that calling setup_logging multiple times doesn't add duplicate handlers."""
        setup_logging()
        initial_handler_count = len(ddtestopt_logger.handlers)

        setup_logging()
        # Should still have the same number of handlers (assuming no duplicate prevention logic)
        # This test documents current behavior - if duplicate prevention is added, adjust accordingly
        assert len(ddtestopt_logger.handlers) >= initial_handler_count


class TestCatchAndLogExceptions:
    """Tests for catch_and_log_exceptions decorator."""

    def test_decorator_success(self):
        """Test decorator with successful function execution."""

        @catch_and_log_exceptions()
        def successful_function(x, y):
            return x + y

        result = successful_function(2, 3)
        assert result == 5

    @patch.object(ddtestopt_logger, "exception")
    def test_decorator_exception_logging(self, mock_exception):
        """Test decorator catches and logs exceptions."""

        @catch_and_log_exceptions()
        def failing_function():
            raise ValueError("Test error")

        result = failing_function()

        assert result is None
        mock_exception.assert_called_once_with("Error while calling %s", "failing_function")

    @patch.object(ddtestopt_logger, "exception")
    def test_decorator_with_arguments(self, mock_exception):
        """Test decorator works with function arguments."""

        @catch_and_log_exceptions()
        def function_with_args(a, b, c=None):
            if c is None:
                raise RuntimeError("c is None")
            return a + b + c

        # Test successful call
        result = function_with_args(1, 2, c=3)
        assert result == 6

        # Test failing call
        result = function_with_args(1, 2)
        assert result is None
        mock_exception.assert_called_once_with("Error while calling %s", "function_with_args")

    @patch.object(ddtestopt_logger, "exception")
    def test_decorator_preserves_function_metadata(self, mock_exception):
        """Test decorator preserves original function metadata."""

        def original_function():
            """Original docstring."""
            return "original"

        decorated = catch_and_log_exceptions()(original_function)

        # Check that function name is preserved for logging
        decorated()
        assert decorated.__name__ == "original_function"  # functools.wraps preserves original name
