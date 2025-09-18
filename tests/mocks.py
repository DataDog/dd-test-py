#!/usr/bin/env python3
"""Improved mock utilities for test optimization framework testing.

This module provides flexible and easy-to-use mock builders and utilities
for testing the ddtestopt framework. The design emphasizes:
- Builder pattern for flexible mock construction
- Centralized default configurations
- Simplified session manager creation
- Utility functions for common patterns
"""

import os
from pathlib import Path
import typing as t
from unittest.mock import Mock
from unittest.mock import patch

from ddtestopt.internal.api_client import AutoTestRetriesSettings
from ddtestopt.internal.api_client import EarlyFlakeDetectionSettings
from ddtestopt.internal.api_client import Settings
from ddtestopt.internal.api_client import TestManagementSettings
from ddtestopt.internal.api_client import TestProperties
from ddtestopt.internal.session_manager import SessionManager
from ddtestopt.internal.test_data import ModuleRef
from ddtestopt.internal.test_data import SuiteRef
from ddtestopt.internal.test_data import TestModule
from ddtestopt.internal.test_data import TestRef
from ddtestopt.internal.test_data import TestRun
from ddtestopt.internal.test_data import TestSession
from ddtestopt.internal.test_data import TestStatus
from ddtestopt.internal.test_data import TestSuite


class MockDefaults:
    """Centralized default configurations for mocks."""

    @staticmethod
    def settings(
        skipping_enabled: bool = True,
        early_flake_detection: bool = False,
        test_management: bool = False,
        auto_test_retries: bool = False,
        known_tests_enabled: bool = False,
        coverage_enabled: bool = False,
        require_git: bool = False,
        itr_enabled: bool = False,
    ) -> Settings:
        """Create default Settings object."""
        return Settings(
            early_flake_detection=EarlyFlakeDetectionSettings(enabled=early_flake_detection),
            test_management=TestManagementSettings(enabled=test_management),
            auto_test_retries=AutoTestRetriesSettings(enabled=auto_test_retries),
            known_tests_enabled=known_tests_enabled,
            coverage_enabled=coverage_enabled,
            skipping_enabled=skipping_enabled,
            require_git=require_git,
            itr_enabled=itr_enabled,
        )

    @staticmethod
    def test_environment() -> t.Dict[str, str]:
        """Create default test environment variables."""
        return {"DD_API_KEY": "test-api-key", "DD_SERVICE": "test-service", "DD_ENV": "test-env"}

    @staticmethod
    def test_session(name: str = "test") -> TestSession:
        """Create default test session."""
        session = TestSession(name=name)
        session.set_attributes(test_command="pytest", test_framework="pytest", test_framework_version="1.0.0")
        return session


# =============================================================================
# MOCK BUILDERS
# =============================================================================


class SessionManagerMockBuilder:
    """Builder for creating SessionManager mocks with flexible configuration."""

    def __init__(self) -> None:
        self._settings = MockDefaults.settings()
        self._skippable_items: t.Set[t.Union[TestRef, SuiteRef]] = set()
        self._test_properties: t.Dict[TestRef, TestProperties] = {}
        self._known_tests: t.Set[TestRef] = set()
        self._known_commits: t.List[str] = []
        self._workspace_path = "/fake/workspace"
        self._retry_handlers: t.List[Mock] = []

    def with_settings(self, settings: Settings) -> "SessionManagerMockBuilder":
        """Set custom settings."""
        self._settings = settings
        return self

    def with_skipping_enabled(self, enabled: bool) -> "SessionManagerMockBuilder":
        """Enable or disable test skipping."""
        self._settings = Settings(
            early_flake_detection=self._settings.early_flake_detection,
            test_management=self._settings.test_management,
            auto_test_retries=self._settings.auto_test_retries,
            known_tests_enabled=self._settings.known_tests_enabled,
            coverage_enabled=self._settings.coverage_enabled,
            skipping_enabled=enabled,
            require_git=self._settings.require_git,
            itr_enabled=self._settings.itr_enabled,
        )
        return self

    def with_skippable_items(self, items: t.Set[t.Union[TestRef, SuiteRef]]) -> "SessionManagerMockBuilder":
        """Set skippable test/suite items."""
        self._skippable_items = items
        return self

    def with_test_properties(self, properties: t.Dict[TestRef, TestProperties]) -> "SessionManagerMockBuilder":
        """Set test properties."""
        self._test_properties = properties
        return self

    def with_known_tests(self, tests: t.Set[TestRef]) -> "SessionManagerMockBuilder":
        """Set known tests."""
        self._known_tests = tests
        return self

    def with_workspace_path(self, path: str) -> "SessionManagerMockBuilder":
        """Set workspace path."""
        self._workspace_path = path
        return self

    def build_mock(self) -> Mock:
        """Build a Mock SessionManager object."""
        mock_manager = Mock(spec=SessionManager)

        # Configure basic attributes
        mock_manager.settings = self._settings
        mock_manager.skippable_items = self._skippable_items
        mock_manager.test_properties = self._test_properties
        mock_manager.workspace_path = self._workspace_path
        mock_manager.retry_handlers = self._retry_handlers

        # Configure methods
        def mock_is_skippable_test(test_ref: TestRef) -> bool:
            if not mock_manager.settings.skipping_enabled:
                return False
            return test_ref in self._skippable_items or test_ref.suite in self._skippable_items

        mock_manager.is_skippable_test = mock_is_skippable_test
        mock_manager.discover_test.return_value = (Mock(), Mock(), Mock())
        mock_manager.writer = Mock()
        mock_manager.coverage_writer = Mock()

        return mock_manager

    def build_real_with_mocks(self, test_env: t.Optional[t.Dict[str, str]] = None) -> SessionManager:
        """Build a real SessionManager with mocked dependencies.

        NOTE: This creates the SessionManager with mocked dependencies during initialization.
        The mocks are cleaned up after creation, so this assumes SessionManager doesn't
        make further API calls after __init__.
        """
        if test_env is None:
            test_env = MockDefaults.test_environment()

        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            # Configure API client mock
            mock_client = Mock()
            mock_client.get_settings.return_value = self._settings
            mock_client.get_known_tests.return_value = self._known_tests
            mock_client.get_test_management_properties.return_value = self._test_properties
            mock_client.get_known_commits.return_value = self._known_commits
            mock_client.send_git_pack_file.return_value = None
            mock_client.get_skippable_tests.return_value = (self._skippable_items, None)
            mock_api_client.return_value = mock_client

            # Mock other dependencies
            patches: t.List[t.ContextManager[t.Any]] = [
                patch("ddtestopt.internal.session_manager.get_git_tags", return_value={}),
                patch("ddtestopt.internal.session_manager.get_platform_tags", return_value={}),
                patch("ddtestopt.internal.session_manager.Git"),
                patch.dict(os.environ, test_env),
            ]

            with patches[0], patches[1], patches[2] as mock_git, patches[3]:
                # Configure Git mock
                mock_git_instance = Mock()
                mock_git_instance.get_latest_commits.return_value = []
                mock_git_instance.get_filtered_revisions.return_value = []
                mock_git_instance.pack_objects.return_value = iter([])
                mock_git.return_value = mock_git_instance

                # Create session manager
                test_session = MockDefaults.test_session()
                session_manager = SessionManager(session=test_session)
                session_manager.skippable_items = self._skippable_items

                return session_manager


class TestMockBuilder:
    """Builder for creating Test mocks with flexible configuration."""

    def __init__(self, test_ref: TestRef):
        self._test_ref = test_ref
        self._is_attempt_to_fix = False
        self._is_disabled = False
        self._is_quarantined = False
        self._test_runs: t.List[Mock] = []
        self._start_ns = 1000000000
        self._last_test_run = Mock()

    def as_attempt_to_fix(self, is_attempt: bool = True) -> "TestMockBuilder":
        """Set whether this is an attempt to fix."""
        self._is_attempt_to_fix = is_attempt
        return self

    def as_disabled(self, is_disabled: bool = True) -> "TestMockBuilder":
        """Set this test as disabled."""
        self._is_disabled = is_disabled
        return self

    def as_quarantined(self, is_quarantined: bool = True) -> "TestMockBuilder":
        """Set whether this test is quarantined."""
        self._is_quarantined = is_quarantined
        return self

    def with_test_runs(self, test_runs: t.List[Mock]) -> "TestMockBuilder":
        """Set test runs."""
        self._test_runs = test_runs
        return self

    def build(self) -> Mock:
        """Build the Test mock."""
        mock_test = Mock()
        mock_test.ref = self._test_ref
        mock_test.is_attempt_to_fix.return_value = self._is_attempt_to_fix
        mock_test.is_disabled.return_value = self._is_disabled
        mock_test.is_quarantined.return_value = self._is_quarantined
        mock_test.test_runs = self._test_runs
        mock_test.start_ns = self._start_ns
        mock_test.last_test_run = self._last_test_run
        return mock_test


class PytestItemMockBuilder:
    """Builder for creating pytest.Item mocks with flexible configuration."""

    def __init__(self, nodeid: str):
        self._nodeid = nodeid
        self._user_properties: t.List[t.Tuple[str, t.Any]] = []
        self._keywords: t.Dict[str, t.Any] = {}
        self._path = Mock()
        self._location = ("/fake/path.py", 10, "test_name")
        self._additional_attrs: t.Dict[str, t.Any] = {}

    def with_user_properties(self, properties: t.List[t.Tuple[str, t.Any]]) -> "PytestItemMockBuilder":
        """Set user properties."""
        self._user_properties = properties
        return self

    def with_keywords(self, keywords: t.Dict[str, t.Any]) -> "PytestItemMockBuilder":
        """Set keywords."""
        self._keywords = keywords
        return self

    def with_location(self, path: str, lineno: int, testname: str) -> "PytestItemMockBuilder":
        """Set test location info."""
        self._location = (path, lineno, testname)
        return self

    def with_attribute(self, name: str, value: t.Any) -> "PytestItemMockBuilder":
        """Add additional attribute."""
        self._additional_attrs[name] = value
        return self

    def build(self) -> Mock:
        """Build the pytest.Item mock."""
        mock_item = Mock()
        mock_item.nodeid = self._nodeid
        mock_item.add_marker = Mock()
        mock_item.reportinfo.return_value = self._location
        mock_item.path = self._path
        mock_item.path.absolute.return_value.parent = Path(self._location[0]).parent
        mock_item.user_properties = self._user_properties
        mock_item.keywords = self._keywords
        mock_item.location = self._location

        # Add any additional attributes
        for name, value in self._additional_attrs.items():
            setattr(mock_item, name, value)

        return mock_item


# =============================================================================
# UTILITY FUNCTIONS FOR TEST DATA CREATION
# =============================================================================


class TestDataFactory:
    """Factory for creating test data objects."""

    @staticmethod
    def create_test_ref(
        module_name: str = "test_module", suite_name: str = "test_suite.py", test_name: str = "test_function"
    ) -> TestRef:
        """Create a TestRef with sensible defaults."""
        module_ref = ModuleRef(module_name)
        suite_ref = SuiteRef(module_ref, suite_name)
        return TestRef(suite_ref, test_name)

    @staticmethod
    def create_suite_ref(module_name: str = "test_module", suite_name: str = "test_suite.py") -> SuiteRef:
        """Create a SuiteRef with sensible defaults."""
        module_ref = ModuleRef(module_name)
        return SuiteRef(module_ref, suite_name)

    @staticmethod
    def create_module_ref(module_name: str = "test_module") -> ModuleRef:
        """Create a ModuleRef with sensible defaults."""
        return ModuleRef(module_name)


# =============================================================================
# API CLIENT MOCK BUILDERS
# =============================================================================


class APIClientMockBuilder:
    """Builder for creating APIClient mocks with comprehensive network call prevention."""

    def __init__(self) -> None:
        self._skipping_enabled = False
        self._auto_retries_enabled = False
        self._efd_enabled = False
        self._test_management_enabled = False
        self._known_tests_enabled = False
        self._skippable_items: t.Set[t.Union[TestRef, SuiteRef]] = set()
        self._known_tests: t.Set[TestRef] = set()

    def with_skipping_enabled(self, enabled: bool = True) -> "APIClientMockBuilder":
        """Enable/disable test skipping."""
        self._skipping_enabled = enabled
        return self

    def with_early_flake_detection(self, enabled: bool = True) -> "APIClientMockBuilder":
        """Enable/disable early flake detection."""
        self._efd_enabled = enabled
        return self

    def with_auto_retries(self, enabled: bool = True) -> "APIClientMockBuilder":
        """Enable/disable auto retries."""
        self._auto_retries_enabled = enabled
        return self

    def with_test_management(self, enabled: bool = True) -> "APIClientMockBuilder":
        """Enable/disable test management."""
        self._test_management_enabled = enabled
        return self

    def with_known_tests(
        self, enabled: bool = True, tests: t.Optional[t.Set[TestRef]] = None
    ) -> "APIClientMockBuilder":
        """Configure known tests."""
        self._known_tests_enabled = enabled
        if tests is not None:
            self._known_tests = tests
        return self

    def with_skippable_items(self, items: t.Set[t.Union[TestRef, SuiteRef]]) -> "APIClientMockBuilder":
        """Set skippable test items."""
        self._skippable_items = items
        return self

    def build(self) -> Mock:
        """Build the APIClient mock with comprehensive mocking."""
        mock_client = Mock()

        # Mock all API methods to prevent real HTTP calls
        mock_client.get_settings.return_value = Settings(
            early_flake_detection=EarlyFlakeDetectionSettings(
                enabled=self._efd_enabled,
                slow_test_retries_5s=3,
                slow_test_retries_10s=2,
                slow_test_retries_30s=1,
                slow_test_retries_5m=1,
                faulty_session_threshold=30,
            ),
            test_management=TestManagementSettings(enabled=self._test_management_enabled),
            auto_test_retries=AutoTestRetriesSettings(enabled=self._auto_retries_enabled),
            known_tests_enabled=self._known_tests_enabled,
            coverage_enabled=False,
            skipping_enabled=self._skipping_enabled,
            require_git=False,
            itr_enabled=self._skipping_enabled,
        )

        mock_client.get_known_tests.return_value = self._known_tests
        mock_client.get_test_management_properties.return_value = {}
        mock_client.get_known_commits.return_value = []
        mock_client.send_git_pack_file.return_value = None
        mock_client.get_skippable_tests.return_value = (
            self._skippable_items,
            "correlation-123" if self._skippable_items else None,
        )

        return mock_client


class BackendConnectorMockBuilder:
    """Builder for creating BackendConnector mocks that prevent real HTTP calls."""

    def __init__(self) -> None:
        self._post_json_responses: t.Dict[str, t.Any] = {}
        self._request_responses: t.Dict[str, t.Any] = {}
        self._post_files_responses: t.Dict[str, t.Any] = {}

    def with_post_json_response(self, endpoint: str, response_data: t.Any) -> "BackendConnectorMockBuilder":
        """Mock a specific POST JSON endpoint response."""
        self._post_json_responses[endpoint] = response_data
        return self

    def with_request_response(self, method: str, path: str, response_data: t.Any) -> "BackendConnectorMockBuilder":
        """Mock a specific HTTP request response."""
        self._request_responses[f"{method}:{path}"] = response_data
        return self

    def build(self) -> Mock:
        """Build the BackendConnector mock."""
        from ddtestopt.internal.http import BackendConnector

        mock_connector = Mock(spec=BackendConnector)

        # Mock methods to prevent real HTTP calls
        def mock_post_json(endpoint: str, data: t.Any) -> t.Tuple[Mock, t.Any]:
            if endpoint in self._post_json_responses:
                return Mock(), self._post_json_responses[endpoint]
            return Mock(), {}

        def mock_request(method: str, path: str, **kwargs: t.Any) -> t.Tuple[Mock, t.Any]:
            key = f"{method}:{path}"
            if key in self._request_responses:
                return Mock(), self._request_responses[key]
            return Mock(), {}

        def mock_post_files(path: str, files: t.Any, **kwargs: t.Any) -> t.Tuple[Mock, t.Dict[str, t.Any]]:
            return Mock(), {}

        mock_connector.post_json.side_effect = mock_post_json
        mock_connector.request.side_effect = mock_request
        mock_connector.post_files.side_effect = mock_post_files

        return mock_connector


# =============================================================================
# TEST DATA OBJECT BUILDERS
# =============================================================================


class TestRunMockBuilder:
    """Builder for creating TestRun mocks with flexible configuration."""

    def __init__(self, test_ref: TestRef):
        self._test_ref = test_ref
        self._status: t.Optional[TestStatus] = None
        self._start_ns = 1000000000
        self._duration_ns = 500000000  # 0.5s
        self._error_message: t.Optional[str] = None
        self._error_type: t.Optional[str] = None
        self._skip_reason: t.Optional[str] = None

    def with_status(self, status: "TestStatus") -> "TestRunMockBuilder":
        """Set the test status."""
        self._status = status
        return self

    def with_passing(self) -> "TestRunMockBuilder":
        """Set test as passing."""
        self._status = TestStatus.PASS
        return self

    def with_failing(
        self, error_type: str = "AssertionError", error_message: str = "Test failed"
    ) -> "TestRunMockBuilder":
        """Set test as failing with error details."""
        self._status = TestStatus.FAIL
        self._error_type = error_type
        self._error_message = error_message
        return self

    def with_skipped(self, reason: str = "Test skipped") -> "TestRunMockBuilder":
        """Set test as skipped with reason."""
        self._status = TestStatus.SKIP
        self._skip_reason = reason
        return self

    def with_timing(self, start_ns: int, duration_ns: int) -> "TestRunMockBuilder":
        """Set test timing."""
        self._start_ns = start_ns
        self._duration_ns = duration_ns
        return self

    def build(self) -> Mock:
        """Build the TestRun mock."""
        # Default to PASS if no status set
        if self._status is None:
            self._status = TestStatus.PASS

        test_run = Mock(spec=TestRun)
        test_run.ref = self._test_ref
        test_run.start_ns = self._start_ns
        test_run.duration_ns = self._duration_ns
        test_run.end_ns = self._start_ns + self._duration_ns
        test_run.get_status.return_value = self._status
        test_run.error_message = self._error_message
        test_run.error_type = self._error_type
        test_run.skip_reason = self._skip_reason

        # Create mock parent hierarchy
        test_run.parent = Mock()  # TestSuite
        test_run.parent.ref = self._test_ref.suite
        test_run.parent.parent = Mock()  # TestModule
        test_run.parent.parent.ref = self._test_ref.suite.module
        test_run.parent.parent.parent = Mock()  # TestSession
        test_run.parent.parent.parent.name = "test_session"

        return test_run


class TestSuiteMockBuilder:
    """Builder for creating TestSuite mocks with flexible configuration."""

    def __init__(self, suite_ref: SuiteRef):
        self._suite_ref = suite_ref
        self._status: t.Optional[TestStatus] = None
        self._start_ns = 1000000000
        self._duration_ns = 2000000000  # 2s

    def with_status(self, status: "TestStatus") -> "TestSuiteMockBuilder":
        """Set the suite status."""
        self._status = status
        return self

    def with_timing(self, start_ns: int, duration_ns: int) -> "TestSuiteMockBuilder":
        """Set suite timing."""
        self._start_ns = start_ns
        self._duration_ns = duration_ns
        return self

    def build(self) -> Mock:
        """Build the TestSuite mock."""
        # Default to PASS if no status set
        if self._status is None:
            self._status = TestStatus.PASS

        suite = Mock(spec=TestSuite)
        suite.ref = self._suite_ref
        suite.start_ns = self._start_ns
        suite.duration_ns = self._duration_ns
        suite.end_ns = self._start_ns + self._duration_ns
        suite.get_status.return_value = self._status

        # Create mock parent hierarchy
        suite.parent = Mock()  # TestModule
        suite.parent.ref = self._suite_ref.module
        suite.parent.parent = Mock()  # TestSession
        suite.parent.parent.name = "test_session"

        return suite


class TestModuleMockBuilder:
    """Builder for creating TestModule mocks with flexible configuration."""

    def __init__(self, module_ref: ModuleRef):
        self._module_ref = module_ref
        self._status: t.Optional[TestStatus] = None
        self._start_ns = 1000000000
        self._duration_ns = 5000000000  # 5s

    def with_status(self, status: "TestStatus") -> "TestModuleMockBuilder":
        """Set the module status."""
        self._status = status
        return self

    def with_timing(self, start_ns: int, duration_ns: int) -> "TestModuleMockBuilder":
        """Set module timing."""
        self._start_ns = start_ns
        self._duration_ns = duration_ns
        return self

    def build(self) -> Mock:
        """Build the TestModule mock."""
        # Default to PASS if no status set
        if self._status is None:
            self._status = TestStatus.PASS

        module = Mock(spec=TestModule)
        module.ref = self._module_ref
        module.start_ns = self._start_ns
        module.duration_ns = self._duration_ns
        module.end_ns = self._start_ns + self._duration_ns
        module.get_status.return_value = self._status

        # Create mock parent
        module.parent = Mock()  # TestSession
        module.parent.name = "test_session"

        return module


class TestSessionDataMockBuilder:
    """Builder for creating TestSession mocks with flexible configuration."""

    def __init__(self, name: str = "test_session"):
        self._name = name
        self._status: t.Optional[TestStatus] = None
        self._start_ns = 1000000000
        self._duration_ns = 10000000000  # 10s

    def with_status(self, status: "TestStatus") -> "TestSessionDataMockBuilder":
        """Set the session status."""
        self._status = status
        return self

    def with_timing(self, start_ns: int, duration_ns: int) -> "TestSessionDataMockBuilder":
        """Set session timing."""
        self._start_ns = start_ns
        self._duration_ns = duration_ns
        return self

    def build(self) -> Mock:
        """Build the TestSession mock."""
        # Default to PASS if no status set
        if self._status is None:
            self._status = TestStatus.PASS

        session = Mock(spec=TestSession)
        session.name = self._name
        session.start_ns = self._start_ns
        session.duration_ns = self._duration_ns
        session.end_ns = self._start_ns + self._duration_ns
        session.get_status.return_value = self._status

        return session


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def session_manager_mock() -> "SessionManagerMockBuilder":
    """Create a SessionManagerMockBuilder with defaults."""
    return SessionManagerMockBuilder()


def mocked_test(test_ref: TestRef) -> TestMockBuilder:
    """Create a TestMockBuilder for the given test reference."""
    return TestMockBuilder(test_ref)


def pytest_item_mock(nodeid: str) -> PytestItemMockBuilder:
    """Create a PytestItemMockBuilder for the given nodeid."""
    return PytestItemMockBuilder(nodeid)


def mock_test_run(test_ref: TestRef) -> TestRunMockBuilder:
    """Create a TestRunMockBuilder with the given test reference."""
    return TestRunMockBuilder(test_ref)


def mock_test_suite(suite_ref: SuiteRef) -> TestSuiteMockBuilder:
    """Create a TestSuiteMockBuilder with the given suite reference."""
    return TestSuiteMockBuilder(suite_ref)


def mock_test_module(module_ref: ModuleRef) -> TestModuleMockBuilder:
    """Create a TestModuleMockBuilder with the given module reference."""
    return TestModuleMockBuilder(module_ref)


def mock_test_session(name: str = "test_session") -> TestSessionDataMockBuilder:
    """Create a TestSessionDataMockBuilder with the given name."""
    return TestSessionDataMockBuilder(name)


def mock_api_client_settings(
    skipping_enabled: bool = False,
    auto_retries_enabled: bool = False,
    efd_enabled: bool = False,
    test_management_enabled: bool = False,
    known_tests_enabled: bool = False,
    skippable_items: t.Optional[t.Set[t.Union[TestRef, SuiteRef]]] = None,
    known_tests: t.Optional[t.Set[TestRef]] = None,
) -> Mock:
    """Create a comprehensive API client mock - convenience function."""
    builder: "APIClientMockBuilder" = APIClientMockBuilder()

    if skipping_enabled:
        builder = builder.with_skipping_enabled()
    if auto_retries_enabled:
        builder = builder.with_auto_retries()
    if efd_enabled:
        builder = builder.with_early_flake_detection()
    if test_management_enabled:
        builder = builder.with_test_management()
    if known_tests_enabled:
        builder = builder.with_known_tests(enabled=True, tests=known_tests)
    if skippable_items:
        builder = builder.with_skippable_items(skippable_items)

    return builder.build()


def mock_backend_connector() -> "BackendConnectorMockBuilder":
    """Create a BackendConnectorMockBuilder."""
    return BackendConnectorMockBuilder()


def setup_standard_mocks() -> t.ContextManager[t.Any]:
    """Create comprehensive mocks that prevent any real network calls."""
    return patch.multiple(
        "ddtestopt.internal.session_manager",
        get_git_tags=Mock(return_value={}),
        get_platform_tags=Mock(return_value={}),
        Git=Mock(
            return_value=Mock(
                get_latest_commits=Mock(return_value=[]),
                get_filtered_revisions=Mock(return_value=[]),
                pack_objects=Mock(return_value=iter([])),
            )
        ),
    )


def network_mocks() -> t.ContextManager[t.Any]:
    """Create comprehensive mocks that prevent ALL network calls at multiple levels."""
    from contextlib import ExitStack

    def _create_stack() -> t.ContextManager[t.Any]:
        stack = ExitStack()

        # Mock the session manager dependencies
        stack.enter_context(
            patch.multiple(
                "ddtestopt.internal.session_manager",
                get_git_tags=Mock(return_value={}),
                get_platform_tags=Mock(return_value={}),
                Git=Mock(
                    return_value=Mock(
                        get_latest_commits=Mock(return_value=[]),
                        get_filtered_revisions=Mock(return_value=[]),
                        pack_objects=Mock(return_value=iter([])),
                    )
                ),
            )
        )

        # Mock the HTTP connector to prevent any real HTTP calls
        mock_connector = mock_backend_connector().build()
        stack.enter_context(patch("ddtestopt.internal.http.BackendConnector", return_value=mock_connector))

        # Mock the API client constructor to ensure our mock is used
        stack.enter_context(patch("ddtestopt.internal.session_manager.APIClient"))

        # Mock the writer to prevent any HTTP calls from the writer
        mock_writer = Mock()
        mock_writer.flush.return_value = None
        mock_writer._send_events.return_value = None
        stack.enter_context(patch("ddtestopt.internal.writer.TestOptWriter", return_value=mock_writer))
        stack.enter_context(patch("ddtestopt.internal.writer.TestCoverageWriter", return_value=mock_writer))

        return stack

    return _create_stack()
