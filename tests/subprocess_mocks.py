#!/usr/bin/env python3
"""Unified mocking utilities for test_integration.py.

This module provides utilities to set up mocks for both subprocess and in-process
pytest execution modes. It supports:

1. Subprocess mode: Serializing mock configuration to environment variables and
   creating a conftest.py file that sets up mocks in the subprocess
2. In-process mode: Using traditional context managers for mocking

The interface is designed to be mode-agnostic, allowing tests to switch between
execution modes with minimal changes.

CONSOLIDATION NOTE: This module now uses builders from tests/mocks.py internally
via tests/mock_setup.py to eliminate code duplication and ensure consistent
mock behavior across all test modes.
"""

from contextlib import contextmanager
import json
import os
import sys
import typing as t

from _pytest.pytester import Pytester

from ddtestopt.internal.test_data import ModuleRef
from ddtestopt.internal.test_data import SuiteRef
from ddtestopt.internal.test_data import TestRef


class SubprocessMockConfig:
    """Configuration for mocks in subprocess environment."""

    def __init__(self) -> None:
        self.api_client_config = {
            "skipping_enabled": False,
            "auto_retries_enabled": False,
            "efd_enabled": False,
            "test_management_enabled": False,
            "known_tests_enabled": False,
        }
        self.skippable_items: t.Set[t.Union[TestRef, SuiteRef]] = set()
        self.known_tests: t.Set[TestRef] = set()
        self.environment_vars: t.Dict[str, str] = {}

    def with_skipping_enabled(self, enabled: bool = True) -> "SubprocessMockConfig":
        """Enable/disable test skipping."""
        self.api_client_config["skipping_enabled"] = enabled
        return self

    def with_auto_retries_enabled(self, enabled: bool = True) -> "SubprocessMockConfig":
        """Enable/disable auto retries."""
        self.api_client_config["auto_retries_enabled"] = enabled
        return self

    def with_early_flake_detection(self, enabled: bool = True) -> "SubprocessMockConfig":
        """Enable/disable early flake detection."""
        self.api_client_config["efd_enabled"] = enabled
        return self

    def with_test_management(self, enabled: bool = True) -> "SubprocessMockConfig":
        """Enable/disable test management."""
        self.api_client_config["test_management_enabled"] = enabled
        return self

    def with_known_tests(
        self, enabled: bool = True, tests: t.Optional[t.Set[TestRef]] = None
    ) -> "SubprocessMockConfig":
        """Configure known tests."""
        self.api_client_config["known_tests_enabled"] = enabled
        if tests is not None:
            self.known_tests = tests
        return self

    def with_skippable_items(self, items: t.Set[t.Union[TestRef, SuiteRef]]) -> "SubprocessMockConfig":
        """Set skippable test items."""
        self.skippable_items = items
        return self

    def with_environment_vars(self, env_vars: t.Dict[str, str]) -> "SubprocessMockConfig":
        """Set additional environment variables."""
        self.environment_vars.update(env_vars)
        return self


def _serialize_test_ref(test_ref: TestRef) -> t.Dict[str, str]:
    """Serialize a TestRef to a dictionary."""
    return {
        "type": "TestRef",
        "module_name": test_ref.suite.module.name,
        "suite_name": test_ref.suite.name,
        "test_name": test_ref.name,
    }


def _serialize_suite_ref(suite_ref: SuiteRef) -> t.Dict[str, str]:
    """Serialize a SuiteRef to a dictionary."""
    return {
        "type": "SuiteRef",
        "module_name": suite_ref.module.name,
        "suite_name": suite_ref.name,
    }


def _deserialize_test_ref(data: t.Dict[str, str]) -> TestRef:
    """Deserialize a TestRef from a dictionary.

    Note: This function is duplicated in the generated conftest.py content
    for subprocess mocking. The duplication is necessary because conftest.py
    needs self-contained deserialization functions.
    """
    module_ref = ModuleRef(data["module_name"])
    suite_ref = SuiteRef(module_ref, data["suite_name"])
    return TestRef(suite_ref, data["test_name"])


def _deserialize_suite_ref(data: t.Dict[str, str]) -> SuiteRef:
    """Deserialize a SuiteRef from a dictionary.

    Note: This function is duplicated in the generated conftest.py content
    for subprocess mocking. The duplication is necessary because conftest.py
    needs self-contained deserialization functions.
    """
    module_ref = ModuleRef(data["module_name"])
    return SuiteRef(module_ref, data["suite_name"])


def serialize_mock_config(config: SubprocessMockConfig) -> t.Dict[str, str]:
    """Serialize mock configuration to environment variables."""
    env_vars = {}

    # Serialize API client config
    env_vars["DDTESTOPT_MOCK_API_CONFIG"] = json.dumps(config.api_client_config)

    # Serialize skippable items
    skippable_data = []
    for item in config.skippable_items:
        if isinstance(item, TestRef):
            skippable_data.append(_serialize_test_ref(item))
        elif isinstance(item, SuiteRef):
            skippable_data.append(_serialize_suite_ref(item))
    env_vars["DDTESTOPT_MOCK_SKIPPABLE_ITEMS"] = json.dumps(skippable_data)

    # Serialize known tests
    known_tests_data = [_serialize_test_ref(test_ref) for test_ref in config.known_tests]
    env_vars["DDTESTOPT_MOCK_KNOWN_TESTS"] = json.dumps(known_tests_data)

    # Add additional environment variables
    env_vars.update(config.environment_vars)

    # Add standard test environment variables
    env_vars.update(
        {
            "DD_API_KEY": "test-api-key",
            "DD_SERVICE": "test-service",
            "DD_ENV": "test-env",
            "DDTESTOPT_SUBPROCESS_MOCKING": "true",
        }
    )

    return env_vars


def generate_conftest_content() -> str:
    """Generate conftest.py content for subprocess mocking using importable modules."""
    return '''#!/usr/bin/env python3
"""Auto-generated conftest.py for subprocess mocking."""

import json
import os
import pytest

# Import the mock utilities we need
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our test utilities
test_dir = Path(__file__).parent.parent
if str(test_dir) not in sys.path:
    sys.path.insert(0, str(test_dir))

from ddtestopt.internal.test_data import ModuleRef, SuiteRef, TestRef
from tests.mock_setup import MockConfig, setup_mocks_for_subprocess


def _deserialize_test_ref(data):
    """Deserialize a TestRef from a dictionary."""
    module_ref = ModuleRef(data['module_name'])
    suite_ref = SuiteRef(module_ref, data['suite_name'])
    return TestRef(suite_ref, data['test_name'])


def _deserialize_suite_ref(data):
    """Deserialize a SuiteRef from a dictionary."""
    module_ref = ModuleRef(data['module_name'])
    return SuiteRef(module_ref, data['suite_name'])


def _setup_subprocess_mocks():
    """Set up mocks based on environment variables using importable module."""
    if not os.getenv('DDTESTOPT_SUBPROCESS_MOCKING'):
        return

    # Parse API client configuration
    api_config_str = os.getenv('DDTESTOPT_MOCK_API_CONFIG', '{}')
    api_config = json.loads(api_config_str)

    # Parse skippable items
    skippable_items_str = os.getenv('DDTESTOPT_MOCK_SKIPPABLE_ITEMS', '[]')
    skippable_items_data = json.loads(skippable_items_str)
    skippable_items = set()
    for item_data in skippable_items_data:
        if item_data['type'] == 'TestRef':
            skippable_items.add(_deserialize_test_ref(item_data))
        elif item_data['type'] == 'SuiteRef':
            skippable_items.add(_deserialize_suite_ref(item_data))

    # Parse known tests
    known_tests_str = os.getenv('DDTESTOPT_MOCK_KNOWN_TESTS', '[]')
    known_tests_data = json.loads(known_tests_str)
    known_tests = {_deserialize_test_ref(test_data) for test_data in known_tests_data}

    # Create configuration object and set up mocks using importable module
    config = MockConfig(api_config, skippable_items, known_tests)
    setup_mocks_for_subprocess(config)


# Set up mocks as early as possible
_setup_subprocess_mocks()


@pytest.fixture(autouse=True)
def ensure_mocks_are_active():
    """Ensure mocks are active for all tests."""
    # This fixture runs for every test, ensuring mocks stay active
    pass
'''


def create_subprocess_mock_config(**kwargs: t.Any) -> SubprocessMockConfig:
    """Create a SubprocessMockConfig with sensible defaults."""
    config = SubprocessMockConfig()

    # Apply any provided configuration
    if "skipping_enabled" in kwargs:
        config.with_skipping_enabled(kwargs["skipping_enabled"])
    if "auto_retries_enabled" in kwargs:
        config.with_auto_retries_enabled(kwargs["auto_retries_enabled"])
    if "efd_enabled" in kwargs:
        config.with_early_flake_detection(kwargs["efd_enabled"])
    if "test_management_enabled" in kwargs:
        config.with_test_management(kwargs["test_management_enabled"])
    if "known_tests_enabled" in kwargs:
        config.with_known_tests(kwargs["known_tests_enabled"], kwargs.get("known_tests"))
    if "skippable_items" in kwargs:
        config.with_skippable_items(kwargs["skippable_items"])
    if "environment_vars" in kwargs:
        config.with_environment_vars(kwargs["environment_vars"])

    return config


def setup_subprocess_environment(pytester: Pytester, config: SubprocessMockConfig) -> None:
    """Set up the subprocess environment with mocks."""
    # Serialize configuration to environment variables
    env_vars = serialize_mock_config(config)

    # Set environment variables using pytester's mechanism
    for key, value in env_vars.items():
        pytester._monkeypatch.setenv(key, value)

    # Create conftest.py in the test directory
    pytester.makeconftest(generate_conftest_content())


# =============================================================================
# SHARED MOCK SETUP LOGIC (Using importable modules)
# =============================================================================

# Mock setup logic is now in mock_setup.py for better coverage tracking


# =============================================================================
# IN-PROCESS MOCKING SYSTEM (Uses shared logic)
# =============================================================================


@contextmanager
def _setup_in_process_mocks(config: SubprocessMockConfig) -> t.Generator[t.Any, t.Any, t.Any]:
    """Set up mocks for in-process testing using importable module."""
    from tests.mock_setup import MockConfig
    from tests.mock_setup import setup_mocks_for_in_process

    # Convert SubprocessMockConfig to MockConfig
    mock_config = MockConfig(
        api_client_config=config.api_client_config,
        skippable_items=config.skippable_items,
        known_tests=config.known_tests,
    )

    # Use the importable module for mock setup
    with setup_mocks_for_in_process(mock_config):
        yield


# =============================================================================
# UNIFIED INTERFACE - SUPPORTS BOTH MODES
# =============================================================================


def as_bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1")


def get_subprocess_test_mode() -> bool:
    """Get the test execution mode from environment variable or ddtrace plugin detection.

    Auto-detection logic:
    1. If _DDTESTOPT_SUBPROCESS_TEST_MODE is explicitly set, use that value
    2. If ddtrace pytest plugin is active, use subprocess mode for isolation
    3. Otherwise, default to in-process mode for speed

    Set _DDTESTOPT_SUBPROCESS_TEST_MODE=true to force subprocess execution.
    Set _DDTESTOPT_SUBPROCESS_TEST_MODE=false to force in-process execution.
    """
    # Check for explicit environment variable first
    env_val = os.getenv("_DDTESTOPT_SUBPROCESS_TEST_MODE")
    if env_val is not None:
        return as_bool(env_val)

    # Check if the ddtrace pytest plugin is imported and active
    # Check if ddtrace plugin is loaded but not disabled
    if "ddtrace" in sys.modules:
        # The plugin module is loaded, now check if it's active
        # Look at sys.argv to see if ddtrace was explicitly disabled
        cmdline = " ".join(sys.argv)
        pytest_addopts = os.getenv("PYTEST_ADDOPTS", "")
        return "--ddtrace" in cmdline or "--ddtrace" in pytest_addopts

    # Default to in-process mode
    return False


def setup_test_mocks(
    pytester: Pytester, subprocess_mode: t.Optional[bool] = None, **config_kwargs: t.Any
) -> t.Optional[t.ContextManager[None]]:
    """Unified interface for setting up test mocks.

    Args:
        pytester: The pytest Pytester instance
        mode: Either "subprocess" or "in-process". If None, uses DDTESTOPT_TEST_MODE env var
        **config_kwargs: Configuration options for the mocks

    Returns:
        None for subprocess mode, context manager for in-process mode

    Example:
        # Subprocess mode (new)
        setup_test_mocks(pytester, mode="subprocess")
        result = pytester.runpytest_subprocess("-p", "ddtestopt", "-v")

        # In-process mode (original)
        with setup_test_mocks(pytester, mode="in-process"):
            result = pytester.runpytest("-p", "ddtestopt", "-v")

        # Environment-controlled mode
        # Set DDTESTOPT_TEST_MODE=in-process before running tests
        context = setup_test_mocks(pytester)  # Uses env var
        if context:
            with context:
                result = pytester.runpytest("-p", "ddtestopt", "-v")
        else:
            result = pytester.runpytest_subprocess("-p", "ddtestopt", "-v")
    """
    if subprocess_mode is None:
        subprocess_mode = get_subprocess_test_mode()

    config = create_subprocess_mock_config(**config_kwargs)

    if subprocess_mode:
        setup_subprocess_environment(pytester, config)
        return None

    return _setup_in_process_mocks(config)


# =============================================================================
# CONVENIENCE FUNCTIONS - SUPPORT BOTH MODES
# =============================================================================


def setup_basic_mocks(
    pytester: Pytester, subprocess_mode: t.Optional[bool] = None
) -> t.Optional[t.ContextManager[None]]:
    """Set up basic mocks for simple test execution."""
    return setup_test_mocks(pytester, subprocess_mode=subprocess_mode)


def setup_retry_mocks(
    pytester: Pytester, subprocess_mode: t.Optional[bool] = None
) -> t.Optional[t.ContextManager[None]]:
    """Set up mocks for auto retry functionality testing."""
    return setup_test_mocks(pytester, subprocess_mode=subprocess_mode, auto_retries_enabled=True)


def setup_efd_mocks(
    pytester: Pytester, subprocess_mode: t.Optional[bool] = None, known_tests: t.Optional[t.Set[TestRef]] = None
) -> t.Optional[t.ContextManager[None]]:
    """Set up mocks for Early Flake Detection testing."""
    return setup_test_mocks(
        pytester,
        subprocess_mode=subprocess_mode,
        efd_enabled=True,
        known_tests_enabled=True,
        known_tests=known_tests or set(),
    )


def setup_itr_mocks(
    pytester: Pytester,
    subprocess_mode: t.Optional[bool] = None,
    skippable_items: t.Optional[t.Set[t.Union[TestRef, SuiteRef]]] = None,
) -> t.Optional[t.ContextManager[None]]:
    """Set up mocks for Intelligent Test Runner testing."""
    return setup_test_mocks(
        pytester, subprocess_mode=subprocess_mode, skipping_enabled=True, skippable_items=skippable_items or set()
    )


# =============================================================================
# UTILITY FUNCTIONS FOR DUAL-MODE EXECUTION
# =============================================================================


def run_test_with_mocks(
    pytester: Pytester, pytest_args: t.List[str], subprocess_mode: t.Optional[bool] = None, **mock_config: t.Any
) -> t.Any:
    """Run a test with appropriate mocking based on the mode.

    This utility function handles the conditional execution pattern:
    - For subprocess mode: sets up mocks and runs runpytest_subprocess()
    - For in-process mode: uses context manager and runs runpytest()

    Args:
        pytester: The pytest Pytester instance
        pytest_args: Arguments to pass to pytest
        mode: Test execution mode (if None, uses environment variable)
        **mock_config: Mock configuration options

    Returns:
        The result from pytester.runpytest() or pytester.runpytest_subprocess()

    Example:
        # Simple usage - mode determined by environment
        result = run_test_with_mocks(pytester, ["-p", "ddtestopt", "-v"])

        # With specific configuration
        result = run_test_with_mocks(
            pytester,
            ["-p", "ddtestopt", "-v"],
            auto_retries_enabled=True
        )
    """
    if subprocess_mode is None:
        subprocess_mode = get_subprocess_test_mode()

    context = setup_test_mocks(pytester, subprocess_mode=subprocess_mode, **mock_config)

    if context is not None:
        # In-process mode
        with context:
            return pytester.runpytest(*pytest_args)
    else:
        # Subprocess mode
        return pytester.runpytest_subprocess(*pytest_args)


# =============================================================================
# BACKWARD COMPATIBILITY - SUBPROCESS-ONLY FUNCTIONS
# =============================================================================


def setup_basic_subprocess_mocks(pytester: Pytester) -> None:
    """Set up basic mocks for simple test execution (subprocess only)."""
    setup_test_mocks(pytester, subprocess_mode=True)


def setup_retry_subprocess_mocks(pytester: Pytester) -> None:
    """Set up mocks for auto retry functionality testing (subprocess only)."""
    setup_test_mocks(pytester, subprocess_mode=True, auto_retries_enabled=True)


def setup_efd_subprocess_mocks(pytester: Pytester, known_tests: t.Optional[t.Set[TestRef]] = None) -> None:
    """Set up mocks for Early Flake Detection testing (subprocess only)."""
    setup_test_mocks(
        pytester, subprocess_mode=True, efd_enabled=True, known_tests_enabled=True, known_tests=known_tests or set()
    )


def setup_itr_subprocess_mocks(
    pytester: Pytester, skippable_items: t.Optional[t.Set[t.Union[TestRef, SuiteRef]]] = None
) -> None:
    """Set up mocks for Intelligent Test Runner testing (subprocess only)."""
    setup_test_mocks(pytester, subprocess_mode=True, skipping_enabled=True, skippable_items=skippable_items or set())
