"""
This module is meant to be used as a replacement for ddtrace's pytest entry point.

If the DD_USE_DDTESTPY environment variable is set to true, we handle ddtrace's pytest plugin options (such as --ddtrace
and --ddtrace-patch-all), so we can function as a replacement for the old ddtrace pytest plugin.

If DD_USE_DDTESTPY is set to false (the default), we import all functions from the old ddtrace entry point (effectively
exposing the old ddtrace entry point in the new location).

In the future, we will switch the default value of DD_USE_DDTESTPY to true, concluding the transition to the new plugin.
"""

import logging
import os

import pytest

from ddtestpy.internal.utils import asbool


log = logging.getLogger(__name__)


if asbool(os.getenv("DD_USE_DDTESTPY")):

    def pytest_addoption(parser: pytest.Parser) -> None:
        """Add ddtrace options."""
        from ddtestpy.internal.pytest.plugin import TestOptPlugin

        TestOptPlugin.should_handle_ddtrace_options = True

        group = parser.getgroup("ddtestpy")

        group.addoption(
            "--ddtrace",
            action="store_true",
            dest="ddtrace",
            default=False,
            help="Enable Datadog Test Optimization + tracer features",
        )
        group.addoption(
            "--no-ddtrace",
            action="store_true",
            dest="no-ddtrace",
            default=False,
            help="Disable Datadog Test Optimization + tracer features (overrides --ddtrace)",
        )
        group.addoption(
            "--ddtrace-patch-all",
            action="store_true",
            dest="ddtrace-patch-all",
            default=False,
            help="Enable all tracer integrations during tests",
        )
        group.addoption(
            "--ddtrace-iast-fail-tests",
            action="store_true",
            dest="ddtrace-iast-fail-tests",
            default=False,
            help="When IAST is enabled, fail tests that have detected vulnerabilities",
        )

        parser.addini("ddtrace", "Enable Datadog Test Optimization + tracer features", type="bool")
        parser.addini(
            "no-ddtrace", "Disable Datadog Test Optimization + tracer features (overrides 'ddtrace')", type="bool"
        )
        parser.addini("ddtrace-patch-all", "Enable all tracer integrations during tests", type="bool")

    def pytest_configure(config: pytest.Config) -> None:
        yes_ddtrace = config.getoption("ddtrace") or config.getini("ddtrace")
        no_ddtrace = config.getoption("no-ddtrace") or config.getini("no-ddtrace")

        if yes_ddtrace and not no_ddtrace:
            # Importing from ddtrace.* has side effects (such as setting a global tracer); we should only import ddtrace
            # if --ddtrace or equivalent is used.
            #
            # `DDTraceHooks` is used to provide ddtrace-specific initialization unrelated to Test Optimization that used
            # to happen in ddtrace's pytest plugin (such as IAST features).
            try:
                from ddtrace.contrib.internal.pytest.ddtestpy_integration import DDTraceHooks  # type: ignore
            except ImportError:
                log.warning("DD_USE_DDTESTPY used but ddtrace version does not provide ddtestpy integration")
            else:
                config.pluginmanager.register(DDTraceHooks())

else:
    # Behave like the old entry point.
    from ddtrace.contrib.internal.pytest.plugin import *  # noqa: F403
