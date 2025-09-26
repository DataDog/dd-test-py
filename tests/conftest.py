"""Configuration for tests."""

import os

import pytest


# Enable pytester plugin for testing pytest plugins
pytest_plugins = ["pytester"]


@pytest.fixture(scope="session", autouse=True)
def set_env() -> None:
    """
    Make sure that we don't send inner tests to Datadog.
    """
    os.environ["DD_API_KEY"] = "test-key"
