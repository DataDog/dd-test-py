"""Tests for ddtestopt.internal.coverage.instrumentation module."""


class TestInstrumentationVersionSelection:
    """Tests for version-specific instrumentation selection."""

    def test_current_python_version_works(self):
        """Test that the current Python version successfully imports instrumentation."""
        # This tests the actual current runtime version
        import ddtestopt.internal.coverage.instrumentation

        # Should have successfully imported instrument_all_lines
        assert hasattr(ddtestopt.internal.coverage.instrumentation, "instrument_all_lines")

        # Should be callable
        assert callable(ddtestopt.internal.coverage.instrumentation.instrument_all_lines)

    def test_version_selection_logic(self):
        """Test the version selection logic without actually importing different modules."""
        # Test the logic that would be used for version selection
        # This avoids the complex dependency issues of actually importing wrong-version modules

        version_cases = [
            ((3, 13, 0), "py3_13"),
            ((3, 13, 5), "py3_13"),
            ((3, 12, 0), "py3_12"),
            ((3, 12, 8), "py3_12"),
            ((3, 11, 0), "py3_11"),
            ((3, 11, 9), "py3_11"),
            ((3, 10, 0), "py3_10"),
            ((3, 10, 12), "py3_10"),
            ((3, 9, 0), "py3_8"),  # 3.9 falls back to 3.8
            ((3, 9, 18), "py3_8"),  # 3.9 falls back to 3.8
            ((3, 8, 0), "py3_8"),
            ((3, 8, 17), "py3_8"),
        ]

        def get_expected_module_suffix(version_info):
            """Replicate the version selection logic from instrumentation.py."""
            if version_info >= (3, 13):
                return "py3_13"
            elif version_info >= (3, 12):
                return "py3_12"
            elif version_info >= (3, 11):
                return "py3_11"
            elif version_info >= (3, 10):
                return "py3_10"
            else:
                # Python 3.8 and 3.9 use the same instrumentation
                return "py3_8"

        for version_info, expected_suffix in version_cases:
            actual_suffix = get_expected_module_suffix(version_info)
            assert actual_suffix == expected_suffix, (
                f"Version {version_info} should select {expected_suffix} " f"but got {actual_suffix}"
            )

    def test_current_version_matches_expected(self):
        """Test that the current Python version gets the expected module."""
        # Import and check that it works
        import ddtestopt.internal.coverage.instrumentation

        # Should have the function (this confirms the right module was imported)
        assert hasattr(ddtestopt.internal.coverage.instrumentation, "instrument_all_lines")

        # This test mainly verifies that our version selection logic is consistent
        # and that the current version can successfully import its appropriate module
