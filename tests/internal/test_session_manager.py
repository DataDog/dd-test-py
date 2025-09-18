"""Regression tests for SessionManager.is_skippable_test() method changes."""

import os
import typing as t
from unittest.mock import Mock
from unittest.mock import patch

from ddtestopt.internal.api_client import AutoTestRetriesSettings
from ddtestopt.internal.api_client import EarlyFlakeDetectionSettings
from ddtestopt.internal.api_client import Settings
from ddtestopt.internal.api_client import TestManagementSettings
from ddtestopt.internal.session_manager import SessionManager
from ddtestopt.internal.test_data import ModuleRef
from ddtestopt.internal.test_data import SuiteRef
from ddtestopt.internal.test_data import TestRef
from ddtestopt.internal.test_data import TestSession


class TestSessionManagerIsSkippableTest:
    """Test the new is_skippable_test method in SessionManager."""

    def setup_method(self) -> None:
        """Set up test environment and mocks."""
        self.test_env = {"DD_API_KEY": "test-api-key", "DD_SERVICE": "test-service", "DD_ENV": "test-env"}

    def create_session_manager(
        self, skipping_enabled: bool = True, skippable_items: t.Optional[t.Set[t.Union[TestRef, SuiteRef]]] = None
    ) -> SessionManager:
        """Create a SessionManager with mocked dependencies."""
        if skippable_items is None:
            skippable_items = set()

        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            # Mock API client
            mock_client = Mock()
            mock_client.get_settings.return_value = Settings(
                early_flake_detection=EarlyFlakeDetectionSettings(),
                test_management=TestManagementSettings(),
                auto_test_retries=AutoTestRetriesSettings(),
                known_tests_enabled=False,
                coverage_enabled=False,
                skipping_enabled=skipping_enabled,
                require_git=False,
                itr_enabled=False,
            )
            mock_client.get_known_tests.return_value = set()
            mock_client.get_test_management_properties.return_value = {}
            mock_client.get_known_commits.return_value = []
            mock_client.send_git_pack_file.return_value = None
            mock_client.get_skippable_tests.return_value = (skippable_items, None)
            mock_api_client.return_value = mock_client

            # Mock git and platform dependencies
            with patch("ddtestopt.internal.session_manager.get_git_tags", return_value={}):
                with patch("ddtestopt.internal.session_manager.get_platform_tags", return_value={}):
                    with patch("ddtestopt.internal.session_manager.Git") as mock_git:
                        # Mock Git instance
                        mock_git_instance = Mock()
                        mock_git_instance.get_latest_commits.return_value = []
                        mock_git_instance.get_filtered_revisions.return_value = []
                        mock_git_instance.pack_objects.return_value = iter([])
                        mock_git.return_value = mock_git_instance

                        # Mock environment variables
                        with patch.dict(os.environ, self.test_env):
                            # Create a test session with proper attributes
                            test_session = TestSession(name="test")
                            test_session.set_attributes(
                                test_command="pytest", test_framework="pytest", test_framework_version="1.0.0"
                            )

                            # Create session manager
                            session_manager = SessionManager(session=test_session)

                            # Manually set skippable_items since they get set during initialization
                            session_manager.skippable_items = skippable_items

                            return session_manager

    def test_skipping_disabled_returns_false(self) -> None:
        """Test that is_skippable_test returns False when skipping is disabled."""
        # Create test references
        module_ref = ModuleRef("test_module")
        suite_ref = SuiteRef(module_ref, "test_suite.py")
        test_ref = TestRef(suite_ref, "test_function")

        # Create session manager with skipping disabled
        session_manager = self.create_session_manager(
            skipping_enabled=False, skippable_items={test_ref}  # Even if test is in skippable_items
        )

        # Should return False because skipping is disabled
        assert session_manager.is_skippable_test(test_ref) is False

    def test_test_in_skippable_items_returns_true(self) -> None:
        """Test that is_skippable_test returns True when test is in skippable_items."""
        # Create test references
        module_ref = ModuleRef("test_module")
        suite_ref = SuiteRef(module_ref, "test_suite.py")
        test_ref = TestRef(suite_ref, "test_function")

        # Create session manager with test in skippable_items
        session_manager = self.create_session_manager(skipping_enabled=True, skippable_items={test_ref})

        # Should return True because test is in skippable_items
        assert session_manager.is_skippable_test(test_ref) is True

    def test_suite_in_skippable_items_returns_true(self) -> None:
        """Test that is_skippable_test returns True when test's suite is in skippable_items."""
        # Create test references
        module_ref = ModuleRef("test_module")
        suite_ref = SuiteRef(module_ref, "test_suite.py")
        test_ref = TestRef(suite_ref, "test_function")

        # Create session manager with suite in skippable_items (but not the individual test)
        session_manager = self.create_session_manager(skipping_enabled=True, skippable_items={suite_ref})

        # Should return True because test's suite is in skippable_items
        assert session_manager.is_skippable_test(test_ref) is True

    def test_both_test_and_suite_in_skippable_items_returns_true(self) -> None:
        """Test that is_skippable_test returns True when both test and suite are in skippable_items."""
        # Create test references
        module_ref = ModuleRef("test_module")
        suite_ref = SuiteRef(module_ref, "test_suite.py")
        test_ref = TestRef(suite_ref, "test_function")

        # Create session manager with both test and suite in skippable_items
        session_manager = self.create_session_manager(skipping_enabled=True, skippable_items={test_ref, suite_ref})

        # Should return True
        assert session_manager.is_skippable_test(test_ref) is True

    def test_neither_test_nor_suite_in_skippable_items_returns_false(self) -> None:
        """Test that is_skippable_test returns False when neither test nor suite is in skippable_items."""
        # Create test references
        module_ref = ModuleRef("test_module")
        suite_ref = SuiteRef(module_ref, "test_suite.py")
        test_ref = TestRef(suite_ref, "test_function")

        # Create different test/suite that are not the ones we're testing
        other_module_ref = ModuleRef("other_module")
        other_suite_ref = SuiteRef(other_module_ref, "other_suite.py")
        other_test_ref = TestRef(other_suite_ref, "other_function")

        # Create session manager with different test/suite in skippable_items
        session_manager = self.create_session_manager(
            skipping_enabled=True, skippable_items={other_test_ref, other_suite_ref}
        )

        # Should return False because neither our test nor suite is in skippable_items
        assert session_manager.is_skippable_test(test_ref) is False

    def test_empty_skippable_items_returns_false(self) -> None:
        """Test that is_skippable_test returns False when skippable_items is empty."""
        # Create test references
        module_ref = ModuleRef("test_module")
        suite_ref = SuiteRef(module_ref, "test_suite.py")
        test_ref = TestRef(suite_ref, "test_function")

        # Create session manager with empty skippable_items
        session_manager = self.create_session_manager(skipping_enabled=True, skippable_items=set())

        # Should return False because skippable_items is empty
        assert session_manager.is_skippable_test(test_ref) is False

    def test_different_test_same_suite_name_different_module(self) -> None:
        """Test that suite matching is exact (including module)."""
        # Create test references
        module_ref1 = ModuleRef("module1")
        module_ref2 = ModuleRef("module2")
        suite_ref1 = SuiteRef(module_ref1, "test_suite.py")
        suite_ref2 = SuiteRef(module_ref2, "test_suite.py")  # Same suite name, different module
        test_ref = TestRef(suite_ref1, "test_function")

        # Create session manager with suite from different module in skippable_items
        session_manager = self.create_session_manager(
            skipping_enabled=True, skippable_items={suite_ref2}  # Different module, same suite name
        )

        # Should return False because the suite is from a different module
        assert session_manager.is_skippable_test(test_ref) is False

    def test_multiple_tests_same_skippable_suite(self) -> None:
        """Test that multiple tests from the same skippable suite are all skippable."""
        # Create test references
        module_ref = ModuleRef("test_module")
        suite_ref = SuiteRef(module_ref, "test_suite.py")
        test_ref1 = TestRef(suite_ref, "test_function1")
        test_ref2 = TestRef(suite_ref, "test_function2")
        test_ref3 = TestRef(suite_ref, "test_function3")

        # Create session manager with suite in skippable_items
        session_manager = self.create_session_manager(skipping_enabled=True, skippable_items={suite_ref})

        # All tests from the same suite should be skippable
        assert session_manager.is_skippable_test(test_ref1) is True
        assert session_manager.is_skippable_test(test_ref2) is True
        assert session_manager.is_skippable_test(test_ref3) is True
