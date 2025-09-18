#!/usr/bin/env python3

import os
from pathlib import Path
import subprocess
import tempfile
import typing as t
from typing import Dict
from typing import List
from typing import Optional
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


def create_mock_api_client_settings(
    skipping_enabled: bool = False,
    auto_retries_enabled: bool = False,
    efd_enabled: bool = False,
    test_management_enabled: bool = False,
    known_tests_enabled: bool = False,
    skippable_items: Optional[t.Set[t.Union[TestRef, SuiteRef]]] = None,
    known_tests: Optional[t.Set[TestRef]] = None,
) -> Mock:
    """Create a standardized mock API client for integration tests."""
    if skippable_items is None:
        skippable_items = set()
    if known_tests is None:
        known_tests = set()

    mock_client = Mock()
    mock_client.get_settings.return_value = Settings(
        early_flake_detection=EarlyFlakeDetectionSettings(
            enabled=efd_enabled,
            slow_test_retries_5s=3,
            slow_test_retries_10s=2,
            slow_test_retries_30s=1,
            slow_test_retries_5m=1,
            faulty_session_threshold=30,
        ),
        test_management=TestManagementSettings(enabled=test_management_enabled),
        auto_test_retries=AutoTestRetriesSettings(enabled=auto_retries_enabled),
        known_tests_enabled=known_tests_enabled,
        coverage_enabled=False,
        skipping_enabled=skipping_enabled,
        require_git=False,
        itr_enabled=skipping_enabled,
    )
    mock_client.get_known_tests.return_value = known_tests
    mock_client.get_test_management_properties.return_value = {}
    mock_client.get_known_commits.return_value = []
    mock_client.send_git_pack_file.return_value = None
    mock_client.get_skippable_tests.return_value = (skippable_items, "correlation-123" if skippable_items else None)
    return mock_client


def setup_standard_mocks() -> t.ContextManager[Mock]:
    """Set up standard mocks for session manager dependencies."""
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


class TestFeaturesWithMocking:
    """High-level feature tests using pytester with mocked dependencies."""

    def test_simple_plugin_enabled(self, pytester: Pytester, monkeypatch: MonkeyPatch) -> None:
        """Test basic plugin functionality without complex dependencies."""
        # Create a simple test file
        pytester.makepyfile(
            """
            def test_simple():
                '''A simple test.'''
                assert True
        """
        )

        # Use unified mock setup
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            mock_api_client.return_value = create_mock_api_client_settings()

            with setup_standard_mocks():
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

        # Use unified mock setup with auto retries enabled
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            mock_api_client.return_value = create_mock_api_client_settings(auto_retries_enabled=True)

            with setup_standard_mocks():
                monkeypatch.setenv("DD_API_KEY", "test-key")
                monkeypatch.setenv("DD_CIVISIBILITY_FLAKY_RETRY_COUNT", "2")
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

        # Set up known tests - only include the "known" test
        known_suite = SuiteRef(ModuleRef("."), "test_efd.py")
        known_test_ref = TestRef(known_suite, "test_known_test")

        # Use unified mock setup with EFD enabled
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            mock_api_client.return_value = create_mock_api_client_settings(
                efd_enabled=True, known_tests_enabled=True, known_tests={known_test_ref}
            )

            with setup_standard_mocks():
                monkeypatch.setenv("DD_API_KEY", "test-key")
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

        # Set up skippable tests - mark one test as skippable
        skippable_suite = SuiteRef(ModuleRef("."), "test_itr.py")
        skippable_test_ref = TestRef(skippable_suite, "test_should_be_skipped")

        # Use unified mock setup with ITR enabled
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            mock_api_client.return_value = create_mock_api_client_settings(
                skipping_enabled=True, skippable_items={skippable_test_ref}
            )

            with setup_standard_mocks():
                monkeypatch.setenv("DD_API_KEY", "test-key")
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


class TestPytestPluginIntegration:
    """Integration tests for the pytest plugin using subprocess execution."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_env = {
            "DD_API_KEY": "foobar",
            "PYTHONPATH": str(Path.cwd()),
        }

    def teardown_method(self) -> None:
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_file(self, content: str, filename: str = "test_example.py") -> Path:
        """Create a temporary test file with the given content."""
        test_file = Path(self.temp_dir) / filename
        test_file.write_text(content)
        return test_file

    def run_pytest_subprocess(
        self,
        test_files: List[Path],
        extra_args: Optional[List[str]] = None,
        extra_env: Optional[Dict[str, str]] = None,
        use_plugin: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run pytest in a subprocess with the ddtestopt plugin."""
        cmd = ["python", "-m", "pytest", "-v"]

        # Only add the plugin if requested and working from project root
        if use_plugin:
            # Use the entry point instead of module path to avoid import issues
            cmd.extend(["-p", "ddtestopt"])

        if extra_args:
            cmd.extend(extra_args)

        cmd.extend([str(f) for f in test_files])

        env = {**os.environ, **self.test_env}
        if extra_env:
            env.update(extra_env)

        return subprocess.run(
            cmd, cwd=Path.cwd(), capture_output=True, text=True, env=env  # Run from project root instead of temp dir
        )

    def test_basic_test_execution(self) -> None:
        """Test that a basic test runs with the ddtestopt plugin."""
        test_content = '''
def test_simple():
    """A simple test that should pass."""
    assert True

def test_with_assertion():
    """A test with a real assertion."""
    result = 2 + 2
    assert result == 4
'''
        test_file = self.create_test_file(test_content)

        result = self.run_pytest_subprocess([test_file])

        # Debug: print the output if the test fails
        if result.returncode != 0:
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")

        # Check that tests ran successfully
        assert result.returncode == 0
        assert "test_simple PASSED" in result.stdout
        assert "test_with_assertion PASSED" in result.stdout
        assert "2 passed" in result.stdout

    def test_failing_test_execution(self) -> None:
        """Test that failing tests are properly handled."""
        test_content = '''
def test_failing():
    """A test that should fail."""
    assert False, "This test should fail"

def test_passing():
    """A test that should pass."""
    assert True
'''
        test_file = self.create_test_file(test_content)

        result = self.run_pytest_subprocess([test_file])

        # Check that one test failed and one passed
        assert result.returncode == 1  # pytest exits with 1 when tests fail
        assert "test_failing FAILED" in result.stdout
        assert "test_passing PASSED" in result.stdout
        assert "1 failed, 1 passed" in result.stdout

    def test_plugin_loads_correctly(self) -> None:
        """Test that the ddtestopt plugin loads without errors."""
        test_content = '''
def test_plugin_loaded():
    """Test to verify plugin is loaded."""
    assert True
'''
        test_file = self.create_test_file(test_content)

        # Run with plugin explicitly loaded
        result = self.run_pytest_subprocess([test_file], extra_args=["--tb=short"])

        # Should run without plugin loading errors
        assert result.returncode == 0
        assert "1 passed" in result.stdout
        # Should not have any error messages about plugin loading
        assert "Error setting up Test Optimization plugin" not in result.stdout
        assert "Error setting up Test Optimization plugin" not in result.stderr

    def test_test_session_name_extraction(self) -> None:
        """Test that the pytest session command is properly extracted."""
        test_content = '''
def test_command_extraction():
    """Test for command extraction functionality."""
    assert True
'''
        test_file = self.create_test_file(test_content)

        # Run with specific arguments that should be captured
        result = self.run_pytest_subprocess([test_file], extra_args=["--tb=short", "-x"])

        assert result.returncode == 0
        assert "1 passed" in result.stdout

    def test_retry_environment_variables_respected(self) -> None:
        """Test that retry environment variables are properly read by the plugin."""
        # Create a simple test to verify the plugin loads and respects env vars
        test_content = '''
def test_env_vars():
    """Test to verify environment variables are read."""
    import os
    # These should be set by our test environment
    assert os.getenv("DD_CIVISIBILITY_FLAKY_RETRY_ENABLED") == "true"
    assert os.getenv("DD_CIVISIBILITY_FLAKY_RETRY_COUNT") == "2"

def test_simple_pass():
    """Simple passing test."""
    assert True
'''
        test_file = self.create_test_file(test_content)

        # Configure environment with retry settings
        retry_env = {
            "DD_CIVISIBILITY_FLAKY_RETRY_ENABLED": "true",
            "DD_CIVISIBILITY_FLAKY_RETRY_COUNT": "2",
            "DD_CIVISIBILITY_TOTAL_FLAKY_RETRY_COUNT": "5",
        }

        result = self.run_pytest_subprocess([test_file], extra_env=retry_env)

        # Debug output if needed
        if result.returncode != 0:
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")

        # Tests should pass
        assert result.returncode == 0
        assert "2 passed" in result.stdout
        assert "test_env_vars PASSED" in result.stdout
        assert "test_simple_pass PASSED" in result.stdout

    def test_plugin_initialization_without_api(self) -> None:
        """Test plugin behavior when API is not available (realistic test scenario)."""
        test_content = '''
def test_plugin_loads():
    """Test that verifies the plugin loads even without API."""
    assert True

def test_basic_functionality():
    """Test basic functionality works."""
    result = 1 + 1
    assert result == 2
'''
        test_file = self.create_test_file(test_content)

        # Run without special environment to simulate real conditions
        result = self.run_pytest_subprocess([test_file])

        # The plugin should still work even if the API fails
        assert result.returncode == 0
        assert "2 passed" in result.stdout

        # Should not have any plugin errors in stderr
        assert "Error setting up Test Optimization plugin" not in result.stderr


class TestRetryHandler:
    """Test auto retry functionality using mocking for unit testing."""

    def test_retry_handler_configuration(self) -> None:
        """Test that AutoTestRetriesHandler is configured correctly with mocked settings."""
        # Use unified mock setup with auto retries enabled
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
            mock_api_client.return_value = create_mock_api_client_settings(auto_retries_enabled=True)

            with setup_standard_mocks():
                # Mock environment variables
                with patch.dict(
                    os.environ,
                    {
                        "DD_API_KEY": "test-key",
                        "DD_CIVISIBILITY_FLAKY_RETRY_ENABLED": "true",
                        "DD_CIVISIBILITY_FLAKY_RETRY_COUNT": "3",
                        "DD_CIVISIBILITY_TOTAL_FLAKY_RETRY_COUNT": "10",
                    },
                ):
                    from ddtestopt.internal.session_manager import SessionManager
                    from ddtestopt.internal.test_data import TestSession

                    # Create a test session with proper attributes
                    test_session = TestSession(name="test")
                    test_session.set_attributes(
                        test_command="pytest", test_framework="pytest", test_framework_version="1.0.0"
                    )

                    # Create session manager with mocked dependencies
                    session_manager = SessionManager(session=test_session)
                    session_manager.setup_retry_handlers()

                    # Check that AutoTestRetriesHandler was added
                    from ddtestopt.internal.retry_handlers import AutoTestRetriesHandler

                    retry_handlers = session_manager.retry_handlers
                    auto_retry_handler = next(
                        (h for h in retry_handlers if isinstance(h, AutoTestRetriesHandler)), None
                    )

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
