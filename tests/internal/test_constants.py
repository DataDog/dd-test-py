"""Tests for ddtestopt.internal.constants module."""

import ddtestopt.internal.constants as constants_module
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

    def test_default_env_name(self):
        """Test that DEFAULT_ENV_NAME is correctly defined."""
        assert DEFAULT_ENV_NAME == "none"

    def test_default_site(self):
        """Test that DEFAULT_SITE is correctly defined."""
        assert DEFAULT_SITE == "datadoghq.com"

    def test_tag_true(self):
        """Test that TAG_TRUE is correctly defined."""
        assert TAG_TRUE == "true"

    def test_tag_false(self):
        """Test that TAG_FALSE is correctly defined."""
        assert TAG_FALSE == "false"

    def test_empty_name(self):
        """Test that EMPTY_NAME is correctly defined."""
        assert EMPTY_NAME == "."

    def test_boolean_tag_consistency(self):
        """Test that boolean tags are consistent and different."""
        assert TAG_TRUE != TAG_FALSE

    def test_all_constants_have_unique_values(self):
        """Test that all constants have unique values."""
        all_constants = [
            DEFAULT_SERVICE_NAME,
            DEFAULT_ENV_NAME,
            DEFAULT_SITE,
            TAG_TRUE,
            TAG_FALSE,
            EMPTY_NAME,
        ]
        
        # All values should be unique
        assert len(all_constants) == len(set(all_constants)), (
            f"Constants have duplicate values: {all_constants}"
        )

    def test_all_module_constants_are_covered(self):
        """Test that all module-level constants are included in our tests.
        
        This test will fail if a new constant is added without being included
        in the expected constants list.
        """
        # Get all uppercase attributes from the constants module (convention for constants)
        module_constants = [
            name for name in dir(constants_module) 
            if name.isupper() and not name.startswith('_')
        ]
        
        # Expected constants that should be in the module
        expected_constants = [
            'DEFAULT_SERVICE_NAME',
            'DEFAULT_ENV_NAME', 
            'DEFAULT_SITE',
            'TAG_TRUE',
            'TAG_FALSE',
            'EMPTY_NAME',
        ]
        
        # Sort both lists for consistent comparison
        module_constants.sort()
        expected_constants.sort()
        
        assert module_constants == expected_constants, (
            f"Module constants don't match expected constants.\n"
            f"Module has: {module_constants}\n" 
            f"Expected: {expected_constants}\n"
            f"Missing: {set(expected_constants) - set(module_constants)}\n"
            f"Extra: {set(module_constants) - set(expected_constants)}"
        )

    def test_constant_values_are_sensible(self):
        """Test that constant values make sense for their purpose."""
        # Default values should be non-empty
        assert DEFAULT_SERVICE_NAME  # Should be truthy
        assert DEFAULT_ENV_NAME     # Should be truthy
        assert DEFAULT_SITE         # Should be truthy
        
        # Boolean tags should be lowercase strings
        assert TAG_TRUE.lower() == TAG_TRUE
        assert TAG_FALSE.lower() == TAG_FALSE
        
        # Empty name should be a single character placeholder
        assert len(EMPTY_NAME) == 1