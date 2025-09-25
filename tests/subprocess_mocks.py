#!/usr/bin/env python3
"""Subprocess mocking utilities for test_integration.py refactoring.

This module provides utilities to set up mocks in pytest subprocesses when using
pytester.runpytest_subprocess(). It works by:

1. Serializing mock configuration to environment variables
2. Creating a conftest.py file that reads these variables and sets up mocks
3. Providing helper functions to generate the necessary conftest content
"""

import json
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
    """Deserialize a TestRef from a dictionary."""
    module_ref = ModuleRef(data["module_name"])
    suite_ref = SuiteRef(module_ref, data["suite_name"])
    return TestRef(suite_ref, data["test_name"])


def _deserialize_suite_ref(data: t.Dict[str, str]) -> SuiteRef:
    """Deserialize a SuiteRef from a dictionary."""
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
    """Generate conftest.py content for subprocess mocking."""
    return '''#!/usr/bin/env python3
"""Auto-generated conftest.py for subprocess mocking."""

import json
import os
from unittest.mock import Mock, patch
import pytest

# Import the mock utilities we need
import sys
from pathlib import Path

# Add the parent directory to the path so we can import our test utilities
test_dir = Path(__file__).parent.parent
if str(test_dir) not in sys.path:
    sys.path.insert(0, str(test_dir))

from ddtestopt.internal.test_data import ModuleRef, SuiteRef, TestRef
from ddtestopt.internal.api_client import AutoTestRetriesSettings
from ddtestopt.internal.api_client import EarlyFlakeDetectionSettings
from ddtestopt.internal.api_client import Settings
from ddtestopt.internal.api_client import TestManagementSettings


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
    """Set up mocks based on environment variables."""
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

    # Create mock API client
    mock_api_client = Mock()
    mock_api_client.get_settings.return_value = Settings(
        early_flake_detection=EarlyFlakeDetectionSettings(
            enabled=api_config.get('efd_enabled', False),
            slow_test_retries_5s=3,
            slow_test_retries_10s=2,
            slow_test_retries_30s=1,
            slow_test_retries_5m=1,
            faulty_session_threshold=30,
        ),
        test_management=TestManagementSettings(enabled=api_config.get('test_management_enabled', False)),
        auto_test_retries=AutoTestRetriesSettings(enabled=api_config.get('auto_retries_enabled', False)),
        known_tests_enabled=api_config.get('known_tests_enabled', False),
        coverage_enabled=False,
        skipping_enabled=api_config.get('skipping_enabled', False),
        require_git=False,
        itr_enabled=api_config.get('skipping_enabled', False),
    )

    mock_api_client.get_known_tests.return_value = known_tests
    mock_api_client.get_test_management_properties.return_value = {}
    mock_api_client.get_known_commits.return_value = []
    mock_api_client.send_git_pack_file.return_value = None
    mock_api_client.get_skippable_tests.return_value = (
        skippable_items,
        "correlation-123" if skippable_items else None,
    )

    # Create mock git instance
    mock_git_instance = Mock()
    mock_git_instance.get_latest_commits.return_value = []
    mock_git_instance.get_filtered_revisions.return_value = []
    mock_git_instance.pack_objects.return_value = iter([])

    # Create mock writer
    mock_writer = Mock()
    mock_writer.flush.return_value = None
    mock_writer._send_events.return_value = None

    # Create mock backend connector
    mock_connector = Mock()
    mock_connector.post_json.return_value = (Mock(), {})
    mock_connector.request.return_value = (Mock(), {})
    mock_connector.post_files.return_value = (Mock(), {})

    # Apply all the patches
    patcher1 = patch("ddtestopt.internal.session_manager.APIClient", return_value=mock_api_client)
    patcher2 = patch("ddtestopt.internal.session_manager.get_git_tags", return_value={})
    patcher3 = patch("ddtestopt.internal.session_manager.get_platform_tags", return_value={})
    patcher4 = patch("ddtestopt.internal.session_manager.Git", return_value=mock_git_instance)
    patcher5 = patch("ddtestopt.internal.http.BackendConnector", return_value=mock_connector)
    patcher6 = patch("ddtestopt.internal.writer.TestOptWriter", return_value=mock_writer)
    patcher7 = patch("ddtestopt.internal.writer.TestCoverageWriter", return_value=mock_writer)

    # Start all patches
    patcher1.start()
    patcher2.start()
    patcher3.start()
    patcher4.start()
    patcher5.start()
    patcher6.start()
    patcher7.start()


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


# Convenience functions for common test scenarios


def setup_basic_subprocess_mocks(pytester: Pytester) -> None:
    """Set up basic mocks for simple test execution."""
    config = create_subprocess_mock_config()
    setup_subprocess_environment(pytester, config)


def setup_retry_subprocess_mocks(pytester: Pytester) -> None:
    """Set up mocks for auto retry functionality testing."""
    config = create_subprocess_mock_config(auto_retries_enabled=True)
    setup_subprocess_environment(pytester, config)


def setup_efd_subprocess_mocks(pytester: Pytester, known_tests: t.Optional[t.Set[TestRef]] = None) -> None:
    """Set up mocks for Early Flake Detection testing."""
    config = create_subprocess_mock_config(efd_enabled=True, known_tests_enabled=True, known_tests=known_tests or set())
    setup_subprocess_environment(pytester, config)


def setup_itr_subprocess_mocks(
    pytester: Pytester, skippable_items: t.Optional[t.Set[t.Union[TestRef, SuiteRef]]] = None
) -> None:
    """Set up mocks for Intelligent Test Runner testing."""
    config = create_subprocess_mock_config(skipping_enabled=True, skippable_items=skippable_items or set())
    setup_subprocess_environment(pytester, config)
