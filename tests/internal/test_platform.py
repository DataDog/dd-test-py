"""Tests for ddtestopt.internal.platform module."""

import platform
from ddtestopt.internal.platform import PlatformTag, get_platform_tags


class TestPlatformTag:
    """Tests for PlatformTag constants."""

    def test_platform_tag_constants(self):
        """Test that PlatformTag constants are defined correctly."""
        assert PlatformTag.OS_ARCHITECTURE == "os.architecture"
        assert PlatformTag.OS_PLATFORM == "os.platform"
        assert PlatformTag.OS_VERSION == "os.version"
        assert PlatformTag.RUNTIME_NAME == "runtime.name"
        assert PlatformTag.RUNTIME_VERSION == "runtime.version"


class TestGetPlatformTags:
    """Tests for get_platform_tags function."""

    def test_get_platform_tags_returns_dict(self):
        """Test that get_platform_tags returns a dictionary."""
        result = get_platform_tags()
        assert isinstance(result, dict)

    def test_get_platform_tags_has_all_keys(self):
        """Test that get_platform_tags returns all expected keys."""
        result = get_platform_tags()
        expected_keys = {
            PlatformTag.OS_ARCHITECTURE,
            PlatformTag.OS_PLATFORM,
            PlatformTag.OS_VERSION,
            PlatformTag.RUNTIME_NAME,
            PlatformTag.RUNTIME_VERSION,
        }
        assert set(result.keys()) == expected_keys

    def test_get_platform_tags_values_are_strings(self):
        """Test that all values returned by get_platform_tags are strings."""
        result = get_platform_tags()
        for value in result.values():
            assert isinstance(value, str)

    def test_get_platform_tags_os_architecture(self):
        """Test that OS architecture is correctly retrieved."""
        result = get_platform_tags()
        assert result[PlatformTag.OS_ARCHITECTURE] == platform.machine()

    def test_get_platform_tags_os_platform(self):
        """Test that OS platform is correctly retrieved."""
        result = get_platform_tags()
        assert result[PlatformTag.OS_PLATFORM] == platform.system()

    def test_get_platform_tags_os_version(self):
        """Test that OS version is correctly retrieved."""
        result = get_platform_tags()
        assert result[PlatformTag.OS_VERSION] == platform.release()

    def test_get_platform_tags_runtime_name(self):
        """Test that runtime name is correctly retrieved."""
        result = get_platform_tags()
        assert result[PlatformTag.RUNTIME_NAME] == platform.python_implementation()

    def test_get_platform_tags_runtime_version(self):
        """Test that runtime version is correctly retrieved."""
        result = get_platform_tags()
        assert result[PlatformTag.RUNTIME_VERSION] == platform.python_version()

    def test_get_platform_tags_no_empty_values(self):
        """Test that no values in platform tags are empty."""
        result = get_platform_tags()
        for key, value in result.items():
            assert value, f"Value for {key} should not be empty"