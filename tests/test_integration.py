#!/usr/bin/env python3

from unittest.mock import Mock
from unittest.mock import patch

from _pytest.monkeypatch import MonkeyPatch
from _pytest.pytester import Pytester

from ddtestopt.internal.api_client import AutoTestRetriesSettings
from ddtestopt.internal.api_client import EarlyFlakeDetectionSettings
from ddtestopt.internal.api_client import Settings
from ddtestopt.internal.api_client import TestManagementSettings
from ddtestopt.internal.test_data import ModuleRef
from ddtestopt.internal.test_data import SuiteRef
from ddtestopt.internal.test_data import TestRef


class TestFeaturesWithMocking:
    def test_simple_plugin_enabled(self, pytester: Pytester, monkeypatch: MonkeyPatch) -> None:
        # def test_simple_plugin_enabled(self, pytester: Pytester) -> None:
        """Test basic plugin functionality without complex dependencies."""
        # Create a simple test file
        pytester.makepyfile(
            """
            def test_simple():
                '''A simple test.'''
                assert True
        """
        )

        # Mock all the API and environment dependencies
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            # Set up mock API client
            mock_client = Mock()
            mock_client.get_settings.return_value = Settings(
                early_flake_detection=EarlyFlakeDetectionSettings(),
                test_management=TestManagementSettings(),
                auto_test_retries=AutoTestRetriesSettings(),
                known_tests_enabled=False,
                coverage_enabled=False,
                skipping_enabled=False,
                require_git=False,
                itr_enabled=False,
            )
            mock_client.get_known_tests.return_value = set()
            mock_client.get_test_management_properties.return_value = {}
            mock_client.get_known_commits.return_value = []
            mock_client.send_git_pack_file.return_value = None
            mock_client.get_skippable_tests.return_value = (set(), None)
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

                        # Set environment variables for retry configuration
                        monkeypatch.setenv("DD_API_KEY", "test-key")

                        result = pytester.runpytest("-p", "ddtestopt", "-v")

        # Test should pass
        assert result.ret == 0
        result.assert_outcomes(passed=1)

    def test_retry_functionality_with_pytester(self, pytester: Pytester, monkeypatch: MonkeyPatch) -> None:
        """Test that failing tests are retried when auto retry is enabled."""
        # Create a test file with a failing test
        pytester.makepyfile(
            test_failing="""
            def test_always_fails():
                '''A test that always fails to test retry behavior.'''
                assert False, "This test always fails"

            def test_passes():
                '''A test that passes.'''
                assert True
        """
        )

        # Mock all the API and environment dependencies
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            # Set up mock API client
            mock_client = Mock()
            mock_client.get_settings.return_value = Settings(
                early_flake_detection=EarlyFlakeDetectionSettings(),
                test_management=TestManagementSettings(),
                auto_test_retries=AutoTestRetriesSettings(enabled=True),
                known_tests_enabled=False,
                coverage_enabled=False,
                skipping_enabled=False,
                require_git=False,
                itr_enabled=False,
            )
            mock_client.get_known_tests.return_value = set()
            mock_client.get_test_management_properties.return_value = {}
            mock_client.get_known_commits.return_value = []
            mock_client.send_git_pack_file.return_value = None
            mock_client.get_skippable_tests.return_value = (set(), None)
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

                        # Set environment variables for retry configuration
                        monkeypatch.setenv("DD_API_KEY", "test-key")
                        monkeypatch.setenv("DD_CIVISIBILITY_FLAKY_RETRY_COUNT", "2")

                        # Run pytest with the ddtestopt plugin enabled
                        result = pytester.runpytest("-p", "ddtestopt", "-v", "-s")

        # Check that the test failed after retries
        assert result.ret == 1  # Exit code 1 indicates test failures

        # Verify outcomes: the failing test should show as failed, passing test as passed
        result.assert_outcomes(passed=1, failed=1)

        # Check the output for retry indicators
        output = result.stdout.str()

        # Look for test execution lines - should see multiple attempts for the failing test
        assert "test_always_fails" in output
        assert "test_passes" in output

        # Verify that retries happened - should see "RETRY FAILED (Auto Test Retries)" messages
        # DEV: We configured DD_CIVISIBILITY_FLAKY_RETRY_COUNT=2
        # BUT the plugin will show 3 retry attempts (as it includes the initial attempt)
        retry_messages = output.count("RETRY FAILED (Auto Test Retries)")
        assert retry_messages == 3, f"Expected 3 retry messages, got {retry_messages}"

        # Should see the final summary mentioning dd_retry
        assert "dd_retry" in output

        # The test should ultimately fail after all retries
        assert "test_always_fails FAILED" in output
        assert "test_passes PASSED" in output

    def test_early_flake_detection_with_pytester(self, pytester: Pytester, monkeypatch: MonkeyPatch) -> None:
        """Test that EarlyFlakeDetection retries new failing tests."""
        # Create a test file with a new failing test
        pytester.makepyfile(
            test_efd="""
            def test_new_flaky():
                '''A new test that fails initially but should be retried by EFD.'''
                assert False, "This new test fails"

            def test_known_test():
                '''A known test that passes.'''
                assert True
        """
        )

        # Mock all the API and environment dependencies
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            # Set up mock API client with EFD enabled
            mock_client = Mock()
            mock_client.get_settings.return_value = Settings(
                early_flake_detection=EarlyFlakeDetectionSettings(
                    enabled=True,
                    slow_test_retries_5s=3,
                    slow_test_retries_10s=2,
                    slow_test_retries_30s=1,
                    slow_test_retries_5m=1,
                    faulty_session_threshold=30,
                ),
                test_management=TestManagementSettings(),
                auto_test_retries=AutoTestRetriesSettings(enabled=False),
                known_tests_enabled=True,  # Enable known tests for EFD logic
                coverage_enabled=False,
                skipping_enabled=False,
                require_git=False,
                itr_enabled=False,
            )

            # Set up known tests - only include the "known" test
            from ddtestopt.internal.test_data import ModuleRef
            from ddtestopt.internal.test_data import SuiteRef
            from ddtestopt.internal.test_data import TestRef

            known_suite = SuiteRef(ModuleRef("."), "test_efd.py")
            known_test_ref = TestRef(known_suite, "test_known_test")
            mock_client.get_known_tests.return_value = {known_test_ref}

            mock_client.get_test_management_properties.return_value = {}
            mock_client.get_known_commits.return_value = []
            mock_client.send_git_pack_file.return_value = None
            mock_client.get_skippable_tests.return_value = (set(), None)
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

                        # Set environment variables
                        monkeypatch.setenv("DD_API_KEY", "test-key")

                        # Run pytest with the ddtestopt plugin enabled
                        result = pytester.runpytest("-p", "ddtestopt", "-v", "-s")

        # Check that the test failed after EFD retries
        assert result.ret == 1  # Exit code 1 indicates test failures

        # Verify outcomes: the failing test should show as failed, passing test as passed
        result.assert_outcomes(passed=1, failed=1)

        # Check the output for EFD retry indicators
        output = result.stdout.str()

        # Verify that EFD retries happened - should see "RETRY FAILED (Early Flake Detection)" messages
        flaky_efd_retry_messages = output.count("test_efd.py::test_new_flaky RETRY FAILED (Early Flake Detection)")
        assert flaky_efd_retry_messages == 4, f"Expected 4 EFD retry messages, got {flaky_efd_retry_messages}"

        known_test_efd_retry_messages = output.count(
            "test_efd.py::test_known_test RETRY FAILED (Early Flake Detection)"
        )
        assert known_test_efd_retry_messages == 0, f"Expected 0 EFD retry messages, got {known_test_efd_retry_messages}"

        # Should see the final summary mentioning dd_retry
        assert "dd_retry" in output

        # The new test should ultimately fail after EFD retries
        assert "test_new_flaky FAILED" in output
        assert "test_known_test PASSED" in output

    def test_intelligent_test_runner_with_pytester(self, pytester: Pytester, monkeypatch: MonkeyPatch) -> None:
        """Test that IntelligentTestRunner skips tests marked as skippable."""
        # Create a test file with multiple tests
        pytester.makepyfile(
            test_itr="""
            def test_should_be_skipped():
                '''A test that should be skipped by ITR.'''
                assert False

            def test_should_run():
                '''A test that should run normally.'''
                assert True
        """
        )

        # Mock all the API and environment dependencies
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            # Set up mock API client with ITR enabled
            mock_client = Mock()
            mock_client.get_settings.return_value = Settings(
                early_flake_detection=EarlyFlakeDetectionSettings(),
                test_management=TestManagementSettings(),
                auto_test_retries=AutoTestRetriesSettings(enabled=False),
                known_tests_enabled=False,
                coverage_enabled=False,
                skipping_enabled=True,  # Enable test skipping
                require_git=False,
                itr_enabled=True,  # Enable ITR
            )

            mock_client.get_known_tests.return_value = set()
            mock_client.get_test_management_properties.return_value = {}
            mock_client.get_known_commits.return_value = []
            mock_client.send_git_pack_file.return_value = None

            # Set up skippable tests - mark one test as skippable

            skippable_suite = SuiteRef(ModuleRef("."), "test_itr.py")
            skippable_test_ref = TestRef(skippable_suite, "test_should_be_skipped")
            mock_client.get_skippable_tests.return_value = ({skippable_test_ref}, "correlation-123")

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

                        # Set environment variables
                        monkeypatch.setenv("DD_API_KEY", "test-key")

                        # Run pytest with the ddtestopt plugin enabled
                        result = pytester.runpytest("-p", "ddtestopt", "-v", "-s")

        # Check that tests completed successfully
        assert result.ret == 0  # Exit code 0 indicates success

        # Verify outcomes: one test skipped by ITR, one test passed
        result.assert_outcomes(passed=1, skipped=1)

        # Check the output for ITR skip indicators
        output = result.stdout.str()

        # Verify that ITR skipped the test with the correct reason
        assert "SKIPPED" in output
        # The reason might be truncated in the output, so check for the beginning of the message
        assert "Skipped by Datadog" in output

        # The skippable test should be marked as skipped, the other should pass
        assert "test_should_be_skipped SKIPPED" in output
        assert "test_should_run PASSED" in output
