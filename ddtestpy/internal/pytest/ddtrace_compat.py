import pytest
import os

from ddtestpy.internal.utils import asbool
from ddtestpy.internal.pytest.plugin import _is_option_true

if asbool(os.getenv("DD_PYTEST_USE_DDTESTPY")):

    def pytest_addoption(parser: pytest.Parser) -> None:
        """Add ddtrace options."""
        group = parser.getgroup("ddtestpy")

        group._addoption(
            "--ddtrace",
            action="store_true",
            dest="ddtrace",
            default=False,
            help="Enable Datadog Test Optimization + tracer features",
        )
        group._addoption(
            "--no-ddtrace",
            action="store_true",
            dest="no-ddtrace",
            default=False,
            help="Disable Datadog Test Optimization + tracer features",
        )
        group._addoption(
            "--ddtrace-patch-all",
            action="store_true",
            dest="ddtrace-patch-all",
            default=False,
            help="Enable all tracer integrations during tests",
        )
        group._addoption(
            "--ddtrace-iast-fail-tests",
            action="store_true",
            dest="ddtrace-iast-fail-tests",
            default=False,
            help="When IAST is enabled, fail tests that have detected vulnerabilities",
        )

        parser.addini("ddtrace", "Enable Datadog Test Optimization + tracer features", type="bool")
        parser.addini("no-ddtrace", "Disable Datadog Test Optimization + tracer features", type="bool")

    def pytest_configure(config: pytest.Config) -> None:
        yes_ddtrace = config.getoption("ddtrace") or config.getini("ddtrace")
        no_ddtrace = config.getoption("no-ddtrace") or config.getini("no-ddtrace")

        if yes_ddtrace and not no_ddtrace:
            from ddtrace.contrib.internal.pytest.ddtestpy_integration import DDTraceHooks
            config.pluginmanager.register(DDTraceHooks())

else:

    from ddtrace.contrib.internal.pytest.plugin import *
