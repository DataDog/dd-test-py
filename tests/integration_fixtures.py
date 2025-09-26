#!/usr/bin/env python3
"""Simple test fixtures for integration tests.

This module provides a simplified approach to test configuration using plain
Python objects instead of complex serialization/deserialization.
"""

from contextlib import contextmanager
from dataclasses import asdict
from dataclasses import dataclass
import json
import os
import typing as t
from unittest.mock import Mock
from unittest.mock import patch

from _pytest.pytester import Pytester

from ddtestopt.internal.test_data import ModuleRef
from ddtestopt.internal.test_data import SuiteRef
from ddtestopt.internal.test_data import TestRef
from ddtestopt.internal.utils import asbool
from tests.mocks import APIClientMockBuilder
from tests.mocks import BackendConnectorMockBuilder
from tests.mocks import get_mock_git_instance


def nodeid_to_test_ref(nodeid: str) -> TestRef:
    """Convert pytest nodeid to TestRef object.

    Example: "test_file.py::test_name" → TestRef(...)
    """
    if "::" not in nodeid:
        raise ValueError(f"Invalid test nodeid (missing '::'): {nodeid}")

    file_path, test_name = nodeid.split("::", 1)
    module_ref = ModuleRef(".")
    suite_ref = SuiteRef(module_ref, file_path)
    return TestRef(suite_ref, test_name)


def nodeid_to_suite_ref(nodeid: str) -> SuiteRef:
    """Convert pytest nodeid to SuiteRef object.

    Example: "test_file.py" → SuiteRef(...)
    """
    if "::" in nodeid:
        raise ValueError(f"Cannot convert test nodeid to suite: {nodeid}")

    file_path = nodeid
    module_ref = ModuleRef(".")
    return SuiteRef(module_ref, file_path)


@dataclass
class MockFixture:
    """Simple test fixture configuration using pytest nodeids.

    Uses simple strings (pytest nodeids) for much simpler JSON serialization.
    Examples:
    - "test_file.py::test_name" for individual tests
    - "test_file.py" for entire test files/suites
    """

    # API client settings
    skipping_enabled: bool = False
    auto_retries_enabled: bool = False
    efd_enabled: bool = False
    test_management_enabled: bool = False
    known_tests_enabled: bool = False

    # Simple string lists - much easier to serialize/deserialize
    skippable_items: t.Optional[t.List[str]] = None  # pytest nodeids
    known_tests: t.Optional[t.List[str]] = None  # pytest nodeids

    # Environment variables for the test
    env_vars: t.Optional[t.Dict[str, str]] = None

    def __post_init__(self) -> None:
        """Initialize empty containers if None."""
        if self.skippable_items is None:
            self.skippable_items = []
        if self.known_tests is None:
            self.known_tests = []
        if self.env_vars is None:
            self.env_vars = {}

    @property
    def parsed_skippable_items(self) -> t.Set[t.Union[TestRef, SuiteRef]]:
        """Parse skippable nodeids to TestRef/SuiteRef objects."""
        items: t.Set[t.Union[TestRef, SuiteRef]] = set()
        if not self.skippable_items:
            return items

        for nodeid in self.skippable_items:
            if "::" in nodeid:
                # It's a test reference
                items.add(nodeid_to_test_ref(nodeid))
            else:
                # It's a suite/file reference
                items.add(nodeid_to_suite_ref(nodeid))
        return items

    @property
    def parsed_known_tests(self) -> t.Set[TestRef]:
        """Parse known test nodeids to TestRef objects."""
        if not self.known_tests:
            return set()
        return {nodeid_to_test_ref(nodeid) for nodeid in self.known_tests}


def create_patchers(fixture: MockFixture) -> t.List[t.Any]:
    """Create all patch objects.

    Args:
        fixture: MockFixture object with test configuration

    Returns:
        List of patcher objects
    """
    # Create mock git instance using existing helper
    mock_git_instance = get_mock_git_instance()

    # Create mock writer (simple mock, no builder needed for this)
    mock_writer = Mock()
    mock_writer.flush.return_value = None
    mock_writer._send_events.return_value = None

    # Create mock backend connector using builder
    mock_connector = BackendConnectorMockBuilder().build()

    # Create API client mock using builder with fixture configuration
    api_builder = APIClientMockBuilder()

    api_builder.with_skipping_enabled(enabled=fixture.skipping_enabled).with_auto_retries(
        enabled=fixture.auto_retries_enabled
    ).with_early_flake_detection(enabled=fixture.efd_enabled).with_test_management(
        enabled=fixture.test_management_enabled
    ).with_known_tests(
        enabled=fixture.known_tests_enabled, tests=fixture.parsed_known_tests
    ).with_skippable_items(
        fixture.parsed_skippable_items
    )

    mock_api_client = api_builder.build()

    patchers = [
        patch("ddtestopt.internal.session_manager.APIClient", return_value=mock_api_client),
        patch("ddtestopt.internal.session_manager.get_git_tags", return_value={}),
        patch("ddtestopt.internal.session_manager.get_platform_tags", return_value={}),
        patch("ddtestopt.internal.session_manager.Git", return_value=mock_git_instance),
        patch("ddtestopt.internal.http.BackendConnector", return_value=mock_connector),
        patch("ddtestopt.internal.writer.TestOptWriter", return_value=mock_writer),
        patch("ddtestopt.internal.writer.TestCoverageWriter", return_value=mock_writer),
    ]
    return patchers


def start_patchers(fixture: MockFixture) -> t.List[t.Any]:
    """Set up mocks (called from conftest.py).

    This function starts all patches (and leaves them running for the subprocess).

    Args:
        fixture: MockFixture object with test configuration
    """
    patchers = create_patchers(fixture)

    # Start all patches for subprocess mode
    for patcher in patchers:
        patcher.start()

    return patchers


def setup_mocks_for_in_process(fixture: MockFixture) -> t.ContextManager[None]:
    """Set up mocks for in-process execution.

    Args:
        fixture: MockFixture object with test configuration

    Returns:
        Context manager that manages patch lifecycle
    """

    @contextmanager
    def _mock_context() -> t.Generator[t.Any, t.Any, t.Any]:
        patchers = start_patchers(fixture)

        try:
            yield
        finally:
            # Stop all patches
            for patcher in patchers:
                patcher.stop()

    return _mock_context()


# DEV: This is imported inside subprocess conftest
def _setup_subprocess_mocks_from_fixture() -> None:
    """Set up mocks by reading fixture file."""
    fixture_path = os.getenv("DDTESTOPT_FIXTURE_PATH")
    if not fixture_path:
        return

    # Read fixture file and create fixture object
    with open(fixture_path, "r") as f:
        fixture_data = json.load(f)

    fixture = MockFixture(**fixture_data)

    # Set up mocks using the simplified interface
    start_patchers(fixture)


@contextmanager
def _setup_subprocess_mode(pytester: Pytester, fixture: MockFixture) -> t.Generator[None, None, None]:
    """Set up subprocess mode with fixture file."""
    conftest_content = '''#!/usr/bin/env python3
"""Auto-generated conftest.py for fixture-based mocking."""
import sys
from pathlib import Path

# Add parent directory to path for imports
test_dir = Path(__file__).parent.parent
if str(test_dir) not in sys.path:
    sys.path.insert(0, str(test_dir))

from tests.integration_fixtures import _setup_subprocess_mocks_from_fixture

# Set up mocks as early as possible
_setup_subprocess_mocks_from_fixture()
'''

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

    # Create static conftest.py
    pytester.makeconftest(conftest_content)

    yield


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


def run_pytest_with_fixture(
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
