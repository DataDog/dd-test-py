"""
API for code coverage collection for use by ddtestopt.

The rest of ddtestopt should only use the interface exposed in this file to set up code coverage and get coverage data.
"""

import dataclasses
import contextlib
import ddtestopt.internal.coverage.installer
from ddtestopt.internal.coverage.code import ModuleCodeCollector


def install_coverage(workspace_path):
    ddtestopt.internal.coverage.installer.install(include_paths=[workspace_path], collect_import_time_coverage=True)
    ModuleCodeCollector.start_coverage()


class CoverageData:
    def __init__(self):
        self._covered_lines = None

    def get_covered_lines(self):
        return self._covered_lines


@contextlib.contextmanager
def coverage_collection():
    with ModuleCodeCollector.CollectInContext() as coverage_collector:
        coverage_data = CoverageData()
        yield coverage_data
        coverage_data._covered_lines = coverage_collector.get_covered_lines()
