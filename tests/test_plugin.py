"""Tests for ddtestopt pytest plugin functionality."""

import os
from pathlib import Path
import subprocess
import tempfile
from typing import Dict
from typing import List
from typing import Optional
from unittest.mock import Mock
from unittest.mock import patch

from ddtestopt.internal.api_client import AutoTestRetriesSettings
from ddtestopt.internal.api_client import EarlyFlakeDetectionSettings
from ddtestopt.internal.api_client import Settings
from ddtestopt.internal.api_client import TestManagementSettings
from ddtestopt.internal.pytest.plugin import TestOptPlugin
from ddtestopt.internal.pytest.plugin import nodeid_to_test_ref


class TestNodeIdToTestRef:
    """Tests for nodeid_to_test_ref function."""

    def test_nodeid_with_module_suite_and_name(self) -> None:
        """Test parsing a full nodeid with module, suite and test name."""
        nodeid = "tests/internal/test_example.py::TestClass::test_method"
        result = nodeid_to_test_ref(nodeid)

        assert result.suite.module.name == "tests/internal"
        assert result.suite.name == "test_example.py"
        assert result.name == "TestClass::test_method"

    def test_nodeid_with_suite_and_name_only(self) -> None:
        """Test parsing a nodeid with just suite and test name."""
        nodeid = "test_example.py::test_function"
        result = nodeid_to_test_ref(nodeid)

        assert result.suite.module.name == "."
        assert result.suite.name == "test_example.py"
        assert result.name == "test_function"

    def test_nodeid_fallback_format(self) -> None:
        """Test parsing a nodeid that doesn't match the expected format."""
        nodeid = "some_weird_format"
        result = nodeid_to_test_ref(nodeid)

        assert result.suite.module.name == "."
        assert result.suite.name == "."
        assert result.name == "some_weird_format"


class TestTestOptPlugin:
    """Tests for TestOptPlugin class."""

    def test_plugin_initialization(self) -> None:
        """Test that TestOptPlugin initializes correctly."""
        plugin = TestOptPlugin()

        assert plugin.is_xdist_worker is False

    def test_plugin_with_xdist_worker_input(self) -> None:
        """Test plugin behavior with xdist worker configuration."""
        plugin = TestOptPlugin()

        # Mock session with xdist worker input
        mock_session = Mock()
        mock_config = Mock()
        mock_config.workerinput = {"dd_session_id": "test-session-123"}
        # Mock invocation_params to avoid the join error
        mock_invocation_params = Mock()
        mock_invocation_params.args = ["test_arg1", "test_arg2"]
        mock_config.invocation_params = mock_invocation_params
        mock_session.config = mock_config

        # Mock the session manager and other dependencies
        with patch("ddtestopt.internal.pytest.plugin.SessionManager") as mock_session_manager:
            mock_session_manager.return_value = Mock()
            plugin.pytest_sessionstart(mock_session)

        assert plugin.is_xdist_worker is True


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
        # Mock SessionManager with retry-enabled settings
        with patch("ddtestopt.internal.session_manager.APIClient") as mock_api_client:
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
            mock_api_client.return_value = mock_client

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
                # Mock git tags and platform tags to avoid external dependencies
                with patch("ddtestopt.internal.session_manager.get_git_tags", return_value={}):
                    with patch("ddtestopt.internal.session_manager.get_platform_tags", return_value={}):
                        # Mock the Git class and API calls that happen during initialization
                        with patch("ddtestopt.internal.session_manager.Git") as mock_git:
                            mock_git_instance = Mock()
                            mock_git_instance.get_latest_commits.return_value = ["commit1", "commit2"]
                            # Mock get_filtered_revisions to return a list of strings (revision IDs)
                            mock_git_instance.get_filtered_revisions.return_value = ["rev1", "rev2", "rev3"]
                            # Mock pack_objects to return an empty iterator (no packfiles to send)
                            mock_git_instance.pack_objects.return_value = iter([])
                            mock_git.return_value = mock_git_instance

                            # Mock the API client methods
                            mock_client.get_known_commits.return_value = ["commit1"]
                            mock_client.send_git_pack_file.return_value = None
                            mock_client.get_skippable_tests.return_value = (set(), None)

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
