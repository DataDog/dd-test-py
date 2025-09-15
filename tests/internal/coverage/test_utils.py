"""Tests for ddtestopt.internal.coverage.utils module."""

from unittest.mock import Mock

import pytest

from ddtestopt.internal.coverage.utils import ArgumentError
from ddtestopt.internal.coverage.utils import _get_metas_to_propagate
from ddtestopt.internal.coverage.utils import get_argument_value
from ddtestopt.internal.coverage.utils import set_argument_value


class TestArgumentError:
    """Tests for ArgumentError exception."""

    def test_argument_error_creation(self):
        """Test ArgumentError can be created and raised."""
        error = ArgumentError("test message")
        assert str(error) == "test message"
        assert isinstance(error, Exception)

    def test_argument_error_raise(self):
        """Test ArgumentError can be raised and caught."""
        with pytest.raises(ArgumentError) as exc_info:
            raise ArgumentError("custom error message")

        assert str(exc_info.value) == "custom error message"


class TestGetArgumentValue:
    """Tests for get_argument_value function."""

    def test_get_argument_by_keyword(self):
        """Test getting argument value from kwargs."""
        args = (1, 2, 3)
        kwargs = {"name": "value", "other": "data"}

        result = get_argument_value(args, kwargs, pos=5, kw="name")
        assert result == "value"

    def test_get_argument_by_position(self):
        """Test getting argument value from args when not in kwargs."""
        args = ("first", "second", "third")
        kwargs = {}

        result = get_argument_value(args, kwargs, pos=1, kw="missing")
        assert result == "second"

    def test_keyword_prioritized_over_position(self):
        """Test that keyword arguments are prioritized over positional."""
        args = ("pos_value", "other")
        kwargs = {"target": "kw_value"}

        result = get_argument_value(args, kwargs, pos=0, kw="target")
        assert result == "kw_value"  # Should prefer kwargs

    def test_missing_argument_raises_error(self):
        """Test that missing arguments raise ArgumentError."""
        args = ("only_one",)
        kwargs = {}

        with pytest.raises(ArgumentError) as exc_info:
            get_argument_value(args, kwargs, pos=5, kw="missing")

        assert "missing (at position 5)" in str(exc_info.value)

    def test_optional_missing_argument_returns_none(self):
        """Test that optional missing arguments return None."""
        args = ()
        kwargs = {}

        result = get_argument_value(args, kwargs, pos=0, kw="missing", optional=True)
        assert result is None

    def test_optional_existing_argument_returns_value(self):
        """Test that optional existing arguments return the value."""
        args = ()
        kwargs = {"present": "value"}

        result = get_argument_value(args, kwargs, pos=0, kw="present", optional=True)
        assert result == "value"

    def test_edge_case_empty_args_kwargs(self):
        """Test edge case with empty args and kwargs."""
        with pytest.raises(ArgumentError):
            get_argument_value((), {}, pos=0, kw="anything")

    def test_list_args_instead_of_tuple(self):
        """Test that function works with list args instead of tuple."""
        args = ["first", "second"]
        kwargs = {}

        result = get_argument_value(args, kwargs, pos=1, kw="missing")
        assert result == "second"

    def test_complex_values(self):
        """Test with complex argument values (objects, etc.)."""
        test_object = {"complex": ["nested", "data"]}
        args = (test_object,)
        kwargs = {}

        result = get_argument_value(args, kwargs, pos=0, kw="missing")
        assert result == test_object


class TestSetArgumentValue:
    """Tests for set_argument_value function."""

    def test_set_positional_argument_within_range(self):
        """Test setting positional argument when position is within args length."""
        args = ("first", "second", "third")
        kwargs = {}

        new_args, new_kwargs = set_argument_value(args, kwargs, pos=1, kw="param", value="NEW")

        assert new_args == ("first", "NEW", "third")
        assert new_kwargs == {}

    def test_set_keyword_argument_when_pos_out_of_range(self):
        """Test setting keyword argument when position is out of range."""
        args = ("only_one",)
        kwargs = {"existing": "value"}

        new_args, new_kwargs = set_argument_value(args, kwargs, pos=5, kw="new_param", value="NEW", override_unset=True)

        assert new_args == ("only_one",)
        assert new_kwargs == {"existing": "value", "new_param": "NEW"}

    def test_set_existing_keyword_argument(self):
        """Test setting an existing keyword argument."""
        args = ()
        kwargs = {"param": "old_value", "other": "data"}

        new_args, new_kwargs = set_argument_value(args, kwargs, pos=0, kw="param", value="new_value")

        assert new_args == ()
        assert new_kwargs == {"param": "new_value", "other": "data"}

    def test_error_when_argument_not_settable(self):
        """Test error when argument cannot be set (not in kwargs, pos out of range, no override)."""
        args = ("one",)
        kwargs = {}

        with pytest.raises(ArgumentError) as exc_info:
            set_argument_value(args, kwargs, pos=5, kw="missing", value="NEW")

        assert "missing (at position 5) is invalid" in str(exc_info.value)

    def test_override_unset_allows_new_keyword(self):
        """Test that override_unset=True allows setting new keyword arguments."""
        args = ()
        kwargs = {}

        new_args, new_kwargs = set_argument_value(
            args, kwargs, pos=0, kw="new_param", value="value", override_unset=True
        )

        assert new_args == ()
        assert new_kwargs == {"new_param": "value"}

    def test_tuple_immutability(self):
        """Test that original args tuple is not modified."""
        original_args = ("original", "data")
        original_kwargs = {"original": "dict"}

        new_args, new_kwargs = set_argument_value(original_args, original_kwargs, pos=0, kw="param", value="NEW")

        # Original should be unchanged
        assert original_args == ("original", "data")
        assert original_kwargs == {"original": "dict"}

        # New should be different
        assert new_args == ("NEW", "data")
        assert new_kwargs == {"original": "dict"}

    def test_set_first_position(self):
        """Test setting the first positional argument."""
        args = ("first", "second")
        kwargs = {}

        new_args, new_kwargs = set_argument_value(args, kwargs, pos=0, kw="param", value="REPLACED")

        assert new_args == ("REPLACED", "second")

    def test_set_last_position(self):
        """Test setting the last positional argument."""
        args = ("first", "second", "third")
        kwargs = {}

        new_args, new_kwargs = set_argument_value(args, kwargs, pos=2, kw="param", value="REPLACED")

        assert new_args == ("first", "second", "REPLACED")


class TestGetMetasToPropagate:
    """Tests for _get_metas_to_propagate function."""

    def test_get_metas_with_propagation_keys(self):
        """Test getting metas that should be propagated."""
        mock_context = Mock()
        meta_dict = {
            "_dd.p.key1": "value1",
            "_dd.p.key2": "value2",
            "regular_key": "not_propagated",
            "_dd.other": "not_propagated",
        }
        mock_context._meta = Mock()
        mock_context._meta.items.return_value = list(meta_dict.items())

        result = _get_metas_to_propagate(mock_context)

        expected = [("_dd.p.key1", "value1"), ("_dd.p.key2", "value2")]
        assert sorted(result) == sorted(expected)

    def test_get_metas_no_propagation_keys(self):
        """Test getting metas when there are no propagation keys."""
        mock_context = Mock()
        meta_dict = {"regular_key": "value", "_dd.other": "value", "another": "value"}
        mock_context._meta = Mock()
        mock_context._meta.items.return_value = list(meta_dict.items())

        result = _get_metas_to_propagate(mock_context)

        assert result == []

    def test_get_metas_empty_meta(self):
        """Test getting metas when _meta is empty."""
        mock_context = Mock()
        mock_context._meta = Mock()
        mock_context._meta.items.return_value = []

        result = _get_metas_to_propagate(mock_context)

        assert result == []

    def test_get_metas_non_string_keys_ignored(self):
        """Test that non-string keys are ignored."""
        mock_context = Mock()
        meta_dict = {
            "_dd.p.string_key": "propagated",
            123: "not_propagated",  # non-string key
            ("tuple", "key"): "not_propagated",  # non-string key
        }
        mock_context._meta = Mock()
        mock_context._meta.items.return_value = list(meta_dict.items())

        result = _get_metas_to_propagate(mock_context)

        assert result == [("_dd.p.string_key", "propagated")]

    def test_get_metas_handles_runtime_error(self):
        """Test that function handles dictionary changes during iteration."""
        mock_context = Mock()
        # Simulate dictionary items at time of list() call
        items_snapshot = [("_dd.p.key1", "value1"), ("_dd.p.key2", "value2"), ("regular", "ignored")]
        mock_context._meta.items.return_value = items_snapshot

        result = _get_metas_to_propagate(mock_context)

        expected = [("_dd.p.key1", "value1"), ("_dd.p.key2", "value2")]
        assert sorted(result) == sorted(expected)
