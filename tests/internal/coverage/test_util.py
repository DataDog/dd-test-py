"""Tests for ddtestopt.internal.coverage.util module."""

from ddtestopt.internal.coverage.util import collapse_ranges


class TestCollapseRanges:
    """Tests for collapse_ranges function."""

    def test_empty_list(self):
        """Test collapse_ranges with empty list."""
        result = collapse_ranges([])
        assert result == []

    def test_single_number(self):
        """Test collapse_ranges with single number."""
        result = collapse_ranges([5])
        assert result == [(5, 5)]

    def test_consecutive_numbers(self):
        """Test collapse_ranges with consecutive numbers."""
        result = collapse_ranges([1, 2, 3, 4, 5])
        assert result == [(1, 5)]

    def test_non_consecutive_numbers(self):
        """Test collapse_ranges with non-consecutive numbers."""
        result = collapse_ranges([1, 3, 5, 7])
        assert result == [(1, 1), (3, 3), (5, 5), (7, 7)]

    def test_mixed_ranges(self):
        """Test collapse_ranges with mixed consecutive and non-consecutive numbers."""
        result = collapse_ranges([1, 2, 3, 5, 6, 7, 9])
        expected = [(1, 3), (5, 7), (9, 9)]
        assert result == expected

    def test_multiple_ranges(self):
        """Test collapse_ranges with multiple separate ranges."""
        result = collapse_ranges([1, 2, 4, 5, 6, 8, 9, 11, 12, 13, 14])
        expected = [(1, 2), (4, 6), (8, 9), (11, 14)]
        assert result == expected

    def test_two_consecutive_numbers(self):
        """Test collapse_ranges with just two consecutive numbers."""
        result = collapse_ranges([10, 11])
        assert result == [(10, 11)]

    def test_two_non_consecutive_numbers(self):
        """Test collapse_ranges with two non-consecutive numbers."""
        result = collapse_ranges([10, 15])
        assert result == [(10, 10), (15, 15)]

    def test_large_gap(self):
        """Test collapse_ranges with large gaps between numbers."""
        result = collapse_ranges([1, 100, 101, 200])
        expected = [(1, 1), (100, 101), (200, 200)]
        assert result == expected

    def test_example_from_docstring(self):
        """Test the specific example from the function's docstring."""
        result = collapse_ranges([1, 2, 3, 5, 6, 7, 9])
        expected = [(1, 3), (5, 7), (9, 9)]
        assert result == expected

    def test_end_with_single_number(self):
        """Test collapse_ranges ending with a single isolated number."""
        result = collapse_ranges([1, 2, 3, 10])
        expected = [(1, 3), (10, 10)]
        assert result == expected

    def test_start_with_single_number(self):
        """Test collapse_ranges starting with a single isolated number."""
        result = collapse_ranges([1, 5, 6, 7])
        expected = [(1, 1), (5, 7)]
        assert result == expected

    def test_alternating_pattern(self):
        """Test collapse_ranges with alternating single numbers and pairs."""
        result = collapse_ranges([1, 3, 4, 6, 8, 9])
        expected = [(1, 1), (3, 4), (6, 6), (8, 9)]
        assert result == expected

    def test_long_consecutive_sequence(self):
        """Test collapse_ranges with a long consecutive sequence."""
        numbers = list(range(1, 21))  # 1 through 20
        result = collapse_ranges(numbers)
        assert result == [(1, 20)]

    def test_negative_numbers(self):
        """Test collapse_ranges with negative numbers."""
        result = collapse_ranges([-5, -4, -3, -1, 0, 1])
        expected = [(-5, -3), (-1, 1)]
        assert result == expected

    def test_mixed_positive_negative(self):
        """Test collapse_ranges with mix of positive and negative numbers."""
        result = collapse_ranges([-2, -1, 1, 2, 3, 5])
        expected = [(-2, -1), (1, 3), (5, 5)]
        assert result == expected
