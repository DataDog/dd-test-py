"""Tests for ddtestopt.internal.constants module."""

from ddtestopt.internal.constants import (
    DEFAULT_SERVICE_NAME,
    DEFAULT_ENV_NAME,
    DEFAULT_SITE,
    TAG_TRUE,
    TAG_FALSE,
    EMPTY_NAME,
)


class TestConstants:
    """Tests for module constants."""

    def test_default_service_name(self):
        """Test that DEFAULT_SERVICE_NAME is correctly defined."""
        assert DEFAULT_SERVICE_NAME == "test"
        assert isinstance(DEFAULT_SERVICE_NAME, str)

    def test_default_env_name(self):
        """Test that DEFAULT_ENV_NAME is correctly defined."""
        assert DEFAULT_ENV_NAME == "none"
        assert isinstance(DEFAULT_ENV_NAME, str)

    def test_default_site(self):
        """Test that DEFAULT_SITE is correctly defined."""
        assert DEFAULT_SITE == "datadoghq.com"
        assert isinstance(DEFAULT_SITE, str)

    def test_tag_true(self):
        """Test that TAG_TRUE is correctly defined."""
        assert TAG_TRUE == "true"
        assert isinstance(TAG_TRUE, str)

    def test_tag_false(self):
        """Test that TAG_FALSE is correctly defined."""
        assert TAG_FALSE == "false"
        assert isinstance(TAG_FALSE, str)

    def test_empty_name(self):
        """Test that EMPTY_NAME is correctly defined."""
        assert EMPTY_NAME == "."
        assert isinstance(EMPTY_NAME, str)

    def test_boolean_tag_consistency(self):
        """Test that boolean tags are consistent and different."""
        assert TAG_TRUE != TAG_FALSE
        assert TAG_TRUE.lower() == "true"
        assert TAG_FALSE.lower() == "false"

    def test_all_constants_are_strings(self):
        """Test that all constants are string types."""
        constants = [
            DEFAULT_SERVICE_NAME,
            DEFAULT_ENV_NAME,
            DEFAULT_SITE,
            TAG_TRUE,
            TAG_FALSE,
            EMPTY_NAME,
        ]
        for constant in constants:
            assert isinstance(constant, str), f"Constant {constant} is not a string"