#!/usr/bin/env python3

import os
from unittest.mock import Mock
from unittest.mock import patch

from _pytest.pytester import Pytester
import pytest

from ddtestopt.internal.session_manager import SessionManager
from ddtestopt.internal.test_data import TestSession
from tests.fixtures import create_fixture_with_nodeids
from tests.fixtures import run_pytest_with_fixture
from tests.mocks import mock_api_client_settings
from tests.mocks import setup_standard_mocks


# Functions moved to tests.mocks for centralization


class TestFeaturesWithMocking:
    """High-level feature tests using pytester with mocked dependencies."""

    @pytest.mark.slow
    def test_simple_plugin_enabled(self, pytester: Pytester) -> None:
        """Test basic plugin functionality without complex dependencies."""
        # Create a simple test file
        pytester.makepyfile(
            """
            def test_simple():
                '''A simple test.'''
                assert True
        """
        )

        # Create simple fixture with default settings
        fixture = create_fixture_with_nodeids()

        # Run test with automatic mode detection
        result = run_pytest_with_fixture(pytester, ["-p", "ddtestopt", "-p", "no:ddtrace", "-v"], fixture)

        # Test should pass
        assert result.ret == 0
        result.assert_outcomes(passed=1)

    @pytest.mark.slow
    def test_retry_functionality_with_pytester(self, pytester: Pytester) -> None:
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

        # Set retry-related environment variables
        pytester._monkeypatch.setenv("DD_CIVISIBILITY_FLAKY_RETRY_COUNT", "2")

        # Create fixture with auto retries enabled
        fixture = create_fixture_with_nodeids(
            auto_retries_enabled=True, env_vars={"DD_CIVISIBILITY_FLAKY_RETRY_COUNT": "2"}
        )

        # Run test with auto retries configuration
        result = run_pytest_with_fixture(pytester, ["-p", "ddtestopt", "-p", "no:ddtrace", "-v", "-s"], fixture)

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
        retry_messages = output.count("test_always_fails RETRY FAILED (Auto Test Retries)")
        assert retry_messages == 3, f"Expected 3 retry messages, got {retry_messages}"

        # Should see the final summary mentioning dd_retry
        assert "dd_retry" in output

        # The test should ultimately fail after all retries
        assert "test_always_fails FAILED" in output
        assert "test_passes PASSED" in output

    @pytest.mark.slow
    def test_early_flake_detection_with_pytester(self, pytester: Pytester) -> None:
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

        # Define the known test for this test scenario using simple nodeid
        known_test_nodeid = "test_efd.py::test_known_test"

        # Create fixture with EFD enabled and known tests
        fixture = create_fixture_with_nodeids(
            efd_enabled=True, known_tests_enabled=True, known_tests=[known_test_nodeid]
        )

        # Run test with EFD configuration
        result = run_pytest_with_fixture(pytester, ["-p", "ddtestopt", "-p", "no:ddtrace", "-v", "-s"], fixture)

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

    @pytest.mark.slow
    def test_intelligent_test_runner_with_pytester(self, pytester: Pytester) -> None:
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

        # Define the skippable test for this test scenario using simple nodeid
        skippable_test_nodeid = "test_itr.py::test_should_be_skipped"

        # Create fixture with skipping enabled
        fixture = create_fixture_with_nodeids(skipping_enabled=True, skippable_items=[skippable_test_nodeid])

        # Run test with ITR configuration
        result = run_pytest_with_fixture(pytester, ["-p", "ddtestopt", "-p", "no:ddtrace", "-v", "-s"], fixture)

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


class TestPytestPluginIntegration:
    """Integration tests for the pytest plugin using pytester for better performance and reliability."""

    @pytest.mark.slow
    def test_basic_test_execution(self, pytester: Pytester) -> None:
        """Test that a basic test runs with the ddtestopt plugin."""
        # Create test file using pytester
        pytester.makepyfile(
            """
            def test_simple():
                '''A simple test that should pass.'''
                assert True

            def test_with_assertion():
                '''A test with a real assertion.'''
                result = 2 + 2
                assert result == 4
            """
        )

        # Create simple fixture with default settings
        fixture = create_fixture_with_nodeids()

        # Run test with automatic mode detection
        result = run_pytest_with_fixture(pytester, ["-p", "ddtestopt", "-p", "no:ddtrace", "-v"], fixture)

        # Check that tests ran successfully
        assert result.ret == 0
        result.assert_outcomes(passed=2)

    @pytest.mark.slow
    def test_failing_test_execution(self, pytester: Pytester) -> None:
        """Test that failing tests are properly handled."""
        # Create test file using pytester
        pytester.makepyfile(
            """
            def test_failing():
                '''A test that should fail.'''
                assert False, "This test should fail"

            def test_passing():
                '''A test that should pass.'''
                assert True
            """
        )

        # Create simple fixture with default settings
        fixture = create_fixture_with_nodeids()

        # Run test with automatic mode detection
        result = run_pytest_with_fixture(pytester, ["-p", "ddtestopt", "-p", "no:ddtrace", "-v"], fixture)

        # Check that one test failed and one passed
        assert result.ret == 1  # pytest exits with 1 when tests fail
        result.assert_outcomes(passed=1, failed=1)

    @pytest.mark.slow
    def test_retry_environment_variables_respected(self, pytester: Pytester) -> None:
        """Test that retry environment variables are properly read by the plugin."""
        # Create test file using pytester
        pytester.makepyfile(
            """
            def test_env_vars():
                '''Test to verify environment variables are read.'''
                import os
                # These should be set by our test environment
                assert os.getenv("DD_CIVISIBILITY_FLAKY_RETRY_ENABLED") == "true"
                assert os.getenv("DD_CIVISIBILITY_FLAKY_RETRY_COUNT") == "2"

            def test_simple_pass():
                '''Simple passing test.'''
                assert True
            """
        )

        # Set retry-related environment variables
        pytester._monkeypatch.setenv("DD_CIVISIBILITY_FLAKY_RETRY_ENABLED", "true")
        pytester._monkeypatch.setenv("DD_CIVISIBILITY_FLAKY_RETRY_COUNT", "2")
        pytester._monkeypatch.setenv("DD_CIVISIBILITY_TOTAL_FLAKY_RETRY_COUNT", "5")

        # Create fixture with environment variables
        fixture = create_fixture_with_nodeids(
            env_vars={
                "DD_CIVISIBILITY_FLAKY_RETRY_ENABLED": "true",
                "DD_CIVISIBILITY_FLAKY_RETRY_COUNT": "2",
                "DD_CIVISIBILITY_TOTAL_FLAKY_RETRY_COUNT": "5",
            }
        )

        # Run test with automatic mode detection
        result = run_pytest_with_fixture(pytester, ["-p", "ddtestopt", "-p", "no:ddtrace", "-v"], fixture)

        # Tests should pass
        assert result.ret == 0
        result.assert_outcomes(passed=2)


class TestRetryHandler:
    """Test auto retry functionality using mocking for unit testing."""

    @pytest.mark.slow
    def test_retry_handler_configuration(self) -> None:
        """Test that AutoTestRetriesHandler is configured correctly with mocked settings."""
        # Use unified mock setup with auto retries enabled
        with patch(
            "ddtestopt.internal.session_manager.APIClient",
            return_value=mock_api_client_settings(auto_retries_enabled=True),
        ), setup_standard_mocks(), patch.dict(
            os.environ,  # Mock environment variables
            {
                "DD_API_KEY": "test-key",
                "DD_CIVISIBILITY_FLAKY_RETRY_ENABLED": "true",
                "DD_CIVISIBILITY_FLAKY_RETRY_COUNT": "3",
                "DD_CIVISIBILITY_TOTAL_FLAKY_RETRY_COUNT": "10",
            },
        ):
            # Create a test session with proper attributes
            test_session = TestSession(name="test")
            test_session.set_attributes(test_command="pytest", test_framework="pytest", test_framework_version="1.0.0")

            # Create session manager with mocked dependencies
            session_manager = SessionManager(session=test_session)
            session_manager.setup_retry_handlers()

            # Check that AutoTestRetriesHandler was added
            from ddtestopt.internal.retry_handlers import AutoTestRetriesHandler

            retry_handlers = session_manager.retry_handlers
            auto_retry_handler = next((h for h in retry_handlers if isinstance(h, AutoTestRetriesHandler)), None)

            assert auto_retry_handler is not None, "AutoTestRetriesHandler should be configured"
            assert auto_retry_handler.max_retries_per_test == 3
            assert auto_retry_handler.max_tests_to_retry_per_session == 10

    def test_retry_handler_logic(self) -> None:
        """Test the retry logic of AutoTestRetriesHandler."""
        from ddtestopt.internal.retry_handlers import AutoTestRetriesHandler
        from ddtestopt.internal.test_data import ModuleRef
        from ddtestopt.internal.test_data import SuiteRef
        from ddtestopt.internal.test_data import Test
        from ddtestopt.internal.test_data import TestRef
        from ddtestopt.internal.test_data import TestStatus

        # Create a mock session manager
        mock_session_manager = Mock()

        # Create AutoTestRetriesHandler
        with patch.dict(
            os.environ,
            {
                "DD_API_KEY": "foobar",
                "DD_CIVISIBILITY_FLAKY_RETRY_COUNT": "2",
                "DD_CIVISIBILITY_TOTAL_FLAKY_RETRY_COUNT": "5",
            },
        ):
            handler = AutoTestRetriesHandler(mock_session_manager)

        # Create a test with a mock parent (suite)
        module_ref = ModuleRef("module")
        suite_ref = SuiteRef(module_ref, "suite")
        test_ref = TestRef(suite_ref, "test_name")

        # Create a mock suite as parent
        mock_suite = Mock()
        mock_suite.ref = suite_ref

        test = Test(test_ref.name, parent=mock_suite)

        # Test should_apply
        assert handler.should_apply(test) is True

        # Create a failing test run
        test_run = test.make_test_run()
        test_run.start()
        test_run.set_status(TestStatus.FAIL)
        test_run.finish()

        # First retry should be allowed
        assert handler.should_retry(test) is True

        # Add another failed run
        test_run2 = test.make_test_run()
        test_run2.start()
        test_run2.set_status(TestStatus.FAIL)
        test_run2.finish()

        # Second retry should be allowed
        assert handler.should_retry(test) is True

        # Add third failed run
        test_run3 = test.make_test_run()
        test_run3.start()
        test_run3.set_status(TestStatus.FAIL)
        test_run3.finish()

        # Should not retry after max attempts
        assert handler.should_retry(test) is False
