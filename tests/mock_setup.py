#!/usr/bin/env python3
"""Shared mock setup logic for both subprocess and in-process testing modes.

This module contains the actual mock setup functions that are used by both:
1. Subprocess mode: imported by generated conftest.py
2. In-process mode: imported directly by test code

This approach ensures coverage tracking and eliminates code duplication.
"""

import typing as t
from unittest.mock import Mock
from unittest.mock import patch

from ddtestopt.internal.api_client import AutoTestRetriesSettings
from ddtestopt.internal.api_client import EarlyFlakeDetectionSettings
from ddtestopt.internal.api_client import Settings
from ddtestopt.internal.api_client import TestManagementSettings


class MockConfig:
    """Configuration object for mock setup."""

    def __init__(self, api_client_config: t.Dict[str, t.Any], skippable_items: t.Set[t.Any], known_tests: t.Set[t.Any]):
        self.api_client_config = api_client_config
        self.skippable_items = skippable_items
        self.known_tests = known_tests


def create_mock_objects(config: MockConfig) -> t.Dict[str, t.Any]:
    """Create all mock objects based on configuration.

    Returns:
        Dictionary containing all mock objects
    """
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

    # Create API client mock
    mock_api_client = Mock()
    mock_api_client.get_settings.return_value = Settings(
        early_flake_detection=EarlyFlakeDetectionSettings(
            enabled=config.api_client_config.get("efd_enabled", False),
            slow_test_retries_5s=3,
            slow_test_retries_10s=2,
            slow_test_retries_30s=1,
            slow_test_retries_5m=1,
            faulty_session_threshold=30,
        ),
        test_management=TestManagementSettings(enabled=config.api_client_config.get("test_management_enabled", False)),
        auto_test_retries=AutoTestRetriesSettings(enabled=config.api_client_config.get("auto_retries_enabled", False)),
        known_tests_enabled=config.api_client_config.get("known_tests_enabled", False),
        coverage_enabled=False,
        skipping_enabled=config.api_client_config.get("skipping_enabled", False),
        require_git=False,
        itr_enabled=config.api_client_config.get("skipping_enabled", False),
    )

    mock_api_client.get_known_tests.return_value = config.known_tests
    mock_api_client.get_test_management_properties.return_value = {}
    mock_api_client.get_known_commits.return_value = []
    mock_api_client.send_git_pack_file.return_value = None
    mock_api_client.get_skippable_tests.return_value = (
        config.skippable_items,
        "correlation-123" if config.skippable_items else None,
    )

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
