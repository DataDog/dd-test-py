"""Configuration for tests."""

# Enable pytester plugin for testing pytest plugins
pytest_plugins = ["pytester"]

import pytest
import os


@pytest.fixture(scope="session", autouse=True)
def set_env():
    os.environ["DD_API_KEY"] = "test-key"
