#!/usr/bin/env python3
"""Simple test fixtures for integration tests.

This module provides a simplified approach to test configuration using plain
Python objects instead of complex serialization/deserialization.
"""

from contextlib import contextmanager
from dataclasses import asdict
import json
import os
import typing as t

from _pytest.pytester import Pytester

from ddtestopt.internal.utils import asbool
from tests.mock_setup import MockFixture
from tests.mock_setup import setup_mocks_for_in_process


def create_fixture_with_nodeids(
    skipping_enabled: bool = False,
    auto_retries_enabled: bool = False,
    efd_enabled: bool = False,
    test_management_enabled: bool = False,
    known_tests_enabled: bool = False,
    skippable_items: t.Optional[t.List[str]] = None,
    known_tests: t.Optional[t.List[str]] = None,
    env_vars: t.Optional[t.Dict[str, str]] = None,
) -> MockFixture:
    """Create a MockFixture directly with pytest nodeids (much simpler API).

    Examples:
    - skippable_items=["test_file.py::test_name", "other_file.py"]
    - known_tests=["test_file.py::test_function"]
    """
    return MockFixture(
        skipping_enabled=skipping_enabled,
        auto_retries_enabled=auto_retries_enabled,
        efd_enabled=efd_enabled,
        test_management_enabled=test_management_enabled,
        known_tests_enabled=known_tests_enabled,
        skippable_items=skippable_items or [],
        known_tests=known_tests or [],
        env_vars=env_vars or {},
    )


def get_subprocess_test_mode() -> bool:
    """Get the test execution mode from environment variable.

    Set _DDTESTOPT_SUBPROCESS_TEST_MODE=1 to force subprocess execution.
    Set _DDTESTOPT_SUBPROCESS_TEST_MODE=0 to force in-process execution.
    """
    return asbool(os.getenv("_DDTESTOPT_SUBPROCESS_TEST_MODE", "0"))


@contextmanager
def setup_test_mode_with_fixture(
    pytester: Pytester,
    fixture: MockFixture,
    subprocess_mode: t.Optional[bool] = None,
) -> t.Generator[None, None, None]:
    """Set up test environment with the given fixture.

    This is the main entry point that handles both subprocess and in-process modes.
    """
    if subprocess_mode is None:
        subprocess_mode = get_subprocess_test_mode()

    if subprocess_mode:
        # Subprocess mode: create fixture file and static conftest.py
        with _setup_subprocess_mode(pytester, fixture):
            yield
    else:
        # In-process mode: use context manager
        with setup_mocks_for_in_process(fixture):
            yield


@contextmanager
def _setup_subprocess_mode(pytester: Pytester, fixture: MockFixture) -> t.Generator[None, None, None]:
    """Set up subprocess mode with fixture file."""
    # Create fixture file in test directory
    fixture_path = pytester.makefile(".json", fixture=json.dumps(asdict(fixture)))

    # Set environment variable to point to fixture file
    pytester._monkeypatch.setenv("DDTESTOPT_FIXTURE_PATH", str(fixture_path))

    # Set standard test environment variables
    pytester._monkeypatch.setenv("DD_API_KEY", "test-api-key")
    pytester._monkeypatch.setenv("DD_SERVICE", "test-service")
    pytester._monkeypatch.setenv("DD_ENV", "test-env")

    if fixture.env_vars:
        # Set additional environment variables from fixture
        for key, value in fixture.env_vars.items():
            pytester._monkeypatch.setenv(key, value)

    # Create static conftest.py (will be created later)
    _create_static_conftest(pytester)

    yield


def _create_static_conftest(pytester: Pytester) -> None:
    """Create static conftest.py that reads fixture files."""
    conftest_content = '''#!/usr/bin/env python3
"""Auto-generated conftest.py for fixture-based mocking."""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
test_dir = Path(__file__).parent.parent
if str(test_dir) not in sys.path:
    sys.path.insert(0, str(test_dir))

from tests.mock_setup import _setup_subprocess_mocks_from_fixture

# Set up mocks as early as possible
_setup_subprocess_mocks_from_fixture()
'''
    pytester.makeconftest(conftest_content)


def run_test_with_fixture(
    pytester: Pytester,
    pytest_args: t.List[str],
    fixture: MockFixture,
    subprocess_mode: t.Optional[bool] = None,
) -> t.Any:
    """Run a test with the given fixture configuration.

    This is the main utility function that replaces run_test_with_mocks.
    """
    with setup_test_mode_with_fixture(pytester, fixture, subprocess_mode):
        if subprocess_mode:
            return pytester.runpytest_subprocess(*pytest_args)
        else:
            return pytester.runpytest(*pytest_args)
