#!/usr/bin/env python3

from _pytest.pytester import Pytester
import pytest


class TestSimpleParametrized:

    @pytest.mark.parametrize("plugin_enabled", [True, False])
    def test_simple_plugin_no_api_key(self, pytester: Pytester, plugin_enabled: bool) -> None:
        """Test basic plugin functionality without complex dependencies."""
        # Create a simple test file
        pytester.makepyfile(
            """
            def test_simple():
                '''A simple test.'''
                assert True
        """
        )

        # Disable the ddtestopt plugin to avoid initialization issues
        result = pytester.runpytest("-p", "ddtestopt" if plugin_enabled else "no:ddtestopt", "-v")

        # Test should pass
        assert result.ret == 0
        result.assert_outcomes(passed=1)
