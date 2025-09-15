"""
API for code coverage collection for use by ddtestopt.

The rest of ddtestopt should only use the interface exposed in this file to set up code coverage and get coverage data.
"""

import contextlib
from pathlib import Path
import typing as t

from ddtestopt.internal.coverage.code import ModuleCodeCollector
import ddtestopt.internal.coverage.installer


def install_coverage(workspace_path):
    ddtestopt.internal.coverage.installer.install(include_paths=[workspace_path], collect_import_time_coverage=True)
    ModuleCodeCollector.start_coverage()


class CoverageData:
    def __init__(self):
        self._covered_lines = None

    def get_coverage_bitmaps(self, relative_to: Path) -> t.Iterable[t.Tuple[str, bytes]]:
        for absolute_path, covered_lines in self._covered_lines.items():
            try:
                relative_path = Path(absolute_path).relative_to(relative_to)
            except ValueError:
                relative_path = absolute_path

            path_str = f"/{str(relative_path)}"
            yield path_str, covered_lines.to_bytes()


@contextlib.contextmanager
def coverage_collection():
    with ModuleCodeCollector.CollectInContext() as coverage_collector:
        coverage_data = CoverageData()
        yield coverage_data
        coverage_data._covered_lines = coverage_collector.get_covered_lines()
