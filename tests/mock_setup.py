#!/usr/bin/env python3
"""Shared mock setup logic for both subprocess and in-process testing modes.

This module contains the actual mock setup functions that are used by both:
1. Subprocess mode: imported by generated conftest.py
2. In-process mode: imported directly by test code

This approach ensures coverage tracking and eliminates code duplication.
Now uses builders from mocks.py for consistent mock creation.
"""

import typing as t
from unittest.mock import Mock
from unittest.mock import patch


class MockConfig:
    """Configuration object for mock setup."""

    def __init__(self, api_client_config: t.Dict[str, t.Any], skippable_items: t.Set[t.Any], known_tests: t.Set[t.Any]):
        self.api_client_config = api_client_config
        self.skippable_items = skippable_items
        self.known_tests = known_tests


def create_mock_objects(config: MockConfig) -> t.Dict[str, t.Any]:
    """Create all mock objects based on configuration using builders from mocks.py.

    Returns:
        Dictionary containing all mock objects
    """
    # Import builders from mocks.py to avoid import cycles at module level
    from tests.mocks import APIClientMockBuilder
    from tests.mocks import BackendConnectorMockBuilder
    from tests.mocks import get_mock_git_instance

    # Create mock git instance using existing helper
    mock_git_instance = get_mock_git_instance()

    # Create mock writer (simple mock, no builder needed for this)
    mock_writer = Mock()
    mock_writer.flush.return_value = None
    mock_writer._send_events.return_value = None

    # Create mock backend connector using builder
    mock_connector = BackendConnectorMockBuilder().build()

    # Create API client mock using builder with configuration
    api_builder = APIClientMockBuilder()

    api_builder.with_skipping_enabled(
        enabled=config.api_client_config.get("skipping_enabled", False)
    ).with_auto_retries(enabled=config.api_client_config.get("auto_retries_enabled", False)).with_early_flake_detection(
        enabled=config.api_client_config.get("efd_enabled", False)
    ).with_test_management(
        enabled=config.api_client_config.get("test_management_enabled", False)
    ).with_known_tests(
        enabled=config.api_client_config.get("known_tests_enabled", False), tests=config.known_tests
    ).with_skippable_items(
        config.skippable_items
    )

    mock_api_client = api_builder.build()

    return {
        "mock_git_instance": mock_git_instance,
        "mock_writer": mock_writer,
        "mock_connector": mock_connector,
        "mock_api_client": mock_api_client,
    }


def create_patchers(mock_objects: t.Dict[str, t.Any]) -> t.List[t.Any]:
    """Create all patch objects.

    Args:
        mock_objects: Dictionary of mock objects from create_mock_objects()

    Returns:
        List of patcher objects
    """
    patchers = [
        patch("ddtestopt.internal.session_manager.APIClient", return_value=mock_objects["mock_api_client"]),
        patch("ddtestopt.internal.session_manager.get_git_tags", return_value={}),
        patch("ddtestopt.internal.session_manager.get_platform_tags", return_value={}),
        patch("ddtestopt.internal.session_manager.Git", return_value=mock_objects["mock_git_instance"]),
        patch("ddtestopt.internal.http.BackendConnector", return_value=mock_objects["mock_connector"]),
        patch("ddtestopt.internal.writer.TestOptWriter", return_value=mock_objects["mock_writer"]),
        patch("ddtestopt.internal.writer.TestCoverageWriter", return_value=mock_objects["mock_writer"]),
    ]
    return patchers


def setup_mocks_for_subprocess(config: MockConfig) -> None:
    """Set up mocks for subprocess execution (called from conftest.py).

    This function starts all patches and leaves them running for the subprocess.
    """
    mock_objects = create_mock_objects(config)
    patchers = create_patchers(mock_objects)

    # Start all patches for subprocess mode
    for patcher in patchers:
        patcher.start()


def setup_mocks_for_in_process(config: MockConfig) -> t.ContextManager[None]:
    """Set up mocks for in-process execution.

    Returns:
        Context manager that manages patch lifecycle
    """
    from contextlib import contextmanager

    @contextmanager
    def _mock_context() -> t.Generator[t.Any, t.Any, t.Any]:
        mock_objects = create_mock_objects(config)
        patchers = create_patchers(mock_objects)

        # Start all patches
        for patcher in patchers:
            patcher.start()

        try:
            yield
        finally:
            # Stop all patches
            for patcher in patchers:
                patcher.stop()

    return _mock_context()
