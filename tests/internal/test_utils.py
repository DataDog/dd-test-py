"""Tests for ddtestpy.internal.utils module."""

from ddtestpy.internal.utils import TestContext
from ddtestpy.internal.utils import _gen_item_id
from ddtestpy.internal.utils import asbool


class TestGenItemId:
    """Tests for _gen_item_id function."""

    def test_gen_item_id_within_range(self) -> None:
        """Test that _gen_item_id returns a value within the expected range."""
        result = _gen_item_id()
        assert 1 <= result <= (1 << 64) - 1

    def test_gen_item_id_randomness(self) -> None:
        """Test that _gen_item_id returns different values on multiple calls."""
        results = [_gen_item_id() for _ in range(100)]
        # Should have at least some variance (very unlikely to be all the same)
        assert len(set(results)) >= 99


class TestAsbool:
    """Tests for asbool function."""

    def test_asbool_with_none(self) -> None:
        """Test asbool with None returns False."""
        assert asbool(None) is False

    def test_asbool_with_true_bool(self) -> None:
        """Test asbool with True boolean returns True."""
        assert asbool(True) is True

    def test_asbool_with_false_bool(self) -> None:
        """Test asbool with False boolean returns False."""
        assert asbool(False) is False

    def test_asbool_with_true_string(self) -> None:
        """Test asbool with 'true' string returns True."""
        assert asbool("true") is True

    def test_asbool_with_true_string_uppercase(self) -> None:
        """Test asbool with 'TRUE' string returns True."""
        assert asbool("TRUE") is True

    def test_asbool_with_true_string_mixed_case(self) -> None:
        """Test asbool with 'TrUe' string returns True."""
        assert asbool("TrUe") is True

    def test_asbool_with_one_string(self) -> None:
        """Test asbool with '1' string returns True."""
        assert asbool("1") is True

    def test_asbool_with_false_string(self) -> None:
        """Test asbool with 'false' string returns False."""
        assert asbool("false") is False

    def test_asbool_with_zero_string(self) -> None:
        """Test asbool with '0' string returns False."""
        assert asbool("0") is False

    def test_asbool_with_empty_string(self) -> None:
        """Test asbool with empty string returns False."""
        assert asbool("") is False

    def test_asbool_with_arbitrary_string(self) -> None:
        """Test asbool with arbitrary string returns False."""
        assert asbool("hello") is False


class TestTestContext:
    """Tests for TestContext dataclass."""

    def test_test_context_creation(self) -> None:
        """Test that TestContext can be created with span_id and trace_id."""
        span_id = 12345
        trace_id = 67890
        context = TestContext(span_id=span_id, trace_id=trace_id)

        assert context.span_id == span_id
        assert context.trace_id == trace_id

    def test_test_context_equality(self) -> None:
        """Test that TestContext instances with same values are equal."""
        context1 = TestContext(span_id=123, trace_id=456)
        context2 = TestContext(span_id=123, trace_id=456)
        context3 = TestContext(span_id=123, trace_id=789)

        assert context1 == context2
        assert context1 != context3
