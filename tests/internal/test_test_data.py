"""Tests for ddtestopt.internal.test_data module."""

from unittest.mock import patch

import pytest

from ddtestopt.internal.constants import DEFAULT_SERVICE_NAME
from ddtestopt.internal.test_data import ModuleRef
from ddtestopt.internal.test_data import SuiteRef
from ddtestopt.internal.test_data import TestItem
from ddtestopt.internal.test_data import TestRef
from ddtestopt.internal.test_data import TestStatus


class TestModuleRef:
    """Tests for ModuleRef dataclass."""

    def test_module_ref_creation(self):
        """Test that ModuleRef can be created with a name."""
        module = ModuleRef(name="test_module")
        assert module.name == "test_module"

    def test_module_ref_immutable(self):
        """Test that ModuleRef is frozen/immutable."""
        module = ModuleRef(name="test_module")
        with pytest.raises(Exception):  # FrozenInstanceError in newer Python
            module.name = "new_name"

    def test_module_ref_equality(self):
        """Test ModuleRef equality based on name."""
        module1 = ModuleRef(name="test_module")
        module2 = ModuleRef(name="test_module")
        module3 = ModuleRef(name="different_module")

        assert module1 == module2
        assert module1 != module3


class TestSuiteRef:
    """Tests for SuiteRef dataclass."""

    def test_suite_ref_creation(self):
        """Test that SuiteRef can be created with module and name."""
        module = ModuleRef(name="test_module")
        suite = SuiteRef(module=module, name="test_suite")

        assert suite.module == module
        assert suite.name == "test_suite"

    def test_suite_ref_immutable(self):
        """Test that SuiteRef is frozen/immutable."""
        module = ModuleRef(name="test_module")
        suite = SuiteRef(module=module, name="test_suite")

        with pytest.raises(Exception):  # FrozenInstanceError
            suite.name = "new_name"


class TestTestRef:
    """Tests for TestRef dataclass."""

    def test_test_ref_creation(self):
        """Test that TestRef can be created with suite and name."""
        module = ModuleRef(name="test_module")
        suite = SuiteRef(module=module, name="test_suite")
        test = TestRef(suite=suite, name="test_function")

        assert test.suite == suite
        assert test.name == "test_function"

    def test_test_ref_immutable(self):
        """Test that TestRef is frozen/immutable."""
        module = ModuleRef(name="test_module")
        suite = SuiteRef(module=module, name="test_suite")
        test = TestRef(suite=suite, name="test_function")

        with pytest.raises(Exception):  # FrozenInstanceError
            test.name = "new_name"


class TestTestStatus:
    """Tests for TestStatus enum."""

    def test_test_status_values(self):
        """Test that TestStatus enum has correct values."""
        assert TestStatus.PASS.value == "pass"
        assert TestStatus.FAIL.value == "fail"
        assert TestStatus.SKIP.value == "skip"

    def test_test_status_comparison(self):
        """Test TestStatus enum comparison."""
        assert TestStatus.PASS == TestStatus.PASS
        assert TestStatus.PASS != TestStatus.FAIL
        assert TestStatus.FAIL != TestStatus.SKIP


class MockTestItem(TestItem):
    """Mock TestItem for testing."""

    ChildClass = None

    def __init__(self, name: str, parent=None):
        super().__init__(name, parent)


class TestTestItem:
    """Tests for TestItem class."""

    def test_test_item_creation(self):
        """Test that TestItem can be created with name and parent."""
        parent = MockTestItem(name="parent")
        item = MockTestItem(name="test_item", parent=parent)

        assert item.name == "test_item"
        assert item.parent == parent
        assert item.children == {}
        assert item.start_ns is None
        assert item.duration_ns is None
        assert item.status is None
        assert item.tags == {}
        assert item.metrics == {}
        assert item.service == DEFAULT_SERVICE_NAME
        assert isinstance(item.item_id, int)

    def test_test_item_start_with_default_time(self):
        """Test TestItem.start() with default time."""
        item = MockTestItem(name="test_item")

        with patch("time.time_ns", return_value=1000000000):
            item.start()

        assert item.start_ns == 1000000000

    def test_test_item_start_with_custom_time(self):
        """Test TestItem.start() with custom time."""
        item = MockTestItem(name="test_item")
        custom_time = 2000000000

        item.start(start_ns=custom_time)
        assert item.start_ns == custom_time

    def test_ensure_started_when_not_started(self):
        """Test ensure_started() when item hasn't been started."""
        item = MockTestItem(name="test_item")
        assert item.start_ns is None

        with patch("time.time_ns", return_value=1000000000):
            item.ensure_started()

        assert item.start_ns == 1000000000

    def test_ensure_started_when_already_started(self):
        """Test ensure_started() when item is already started."""
        item = MockTestItem(name="test_item")
        item.start_ns = 500000000

        item.ensure_started()
        assert item.start_ns == 500000000  # Should remain unchanged

    def test_finish(self):
        """Test TestItem.finish() method."""
        item = MockTestItem(name="test_item")
        item.start_ns = 1000000000

        with patch("time.time_ns", return_value=2000000000):
            item.finish()

        assert item.duration_ns == 1000000000  # 2000000000 - 1000000000

    def test_is_finished(self):
        """Test TestItem.is_finished() method."""
        item = MockTestItem(name="test_item")
        assert not item.is_finished()

        item.duration_ns = 1000000000
        assert item.is_finished()

    def test_seconds_so_far(self):
        """Test TestItem.seconds_so_far() method."""
        item = MockTestItem(name="test_item")
        item.start_ns = 1000000000

        with patch("time.time_ns", return_value=3000000000):
            seconds = item.seconds_so_far()

        assert seconds == 2.0  # (3000000000 - 1000000000) / 1e9

    def test_set_status(self):
        """Test TestItem.set_status() method."""
        item = MockTestItem(name="test_item")

        item.set_status(TestStatus.PASS)
        assert item.status == TestStatus.PASS

        item.set_status(TestStatus.FAIL)
        assert item.status == TestStatus.FAIL

    def test_get_status_explicit(self):
        """Test TestItem.get_status() when status is explicitly set."""
        item = MockTestItem(name="test_item")
        item.set_status(TestStatus.PASS)

        assert item.get_status() == TestStatus.PASS

    def test_set_service(self):
        """Test TestItem.set_service() method."""
        item = MockTestItem(name="test_item")
        assert item.service == DEFAULT_SERVICE_NAME

        item.set_service("custom_service")
        assert item.service == "custom_service"

    def test_get_status_from_children_no_children(self):
        """Test _get_status_from_children when there are no children."""
        item = MockTestItem(name="test_item")

        # When no children, total_count is 0, and status_counts[SKIP] is also 0, so 0 == 0 returns SKIP
        status = item._get_status_from_children()
        assert status == TestStatus.SKIP

    def test_get_status_from_children_with_fail(self):
        """Test _get_status_from_children when children have failures."""
        parent = MockTestItem(name="parent")
        child1 = MockTestItem(name="child1", parent=parent)
        child2 = MockTestItem(name="child2", parent=parent)

        child1.set_status(TestStatus.PASS)
        child2.set_status(TestStatus.FAIL)

        parent.children["child1"] = child1
        parent.children["child2"] = child2

        status = parent._get_status_from_children()
        assert status == TestStatus.FAIL

    def test_get_status_from_children_all_skip(self):
        """Test _get_status_from_children when all children are skipped."""
        parent = MockTestItem(name="parent")
        child1 = MockTestItem(name="child1", parent=parent)
        child2 = MockTestItem(name="child2", parent=parent)

        child1.set_status(TestStatus.SKIP)
        child2.set_status(TestStatus.SKIP)

        parent.children["child1"] = child1
        parent.children["child2"] = child2

        status = parent._get_status_from_children()
        assert status == TestStatus.SKIP

    def test_get_status_from_children_mixed_pass_skip(self):
        """Test _get_status_from_children with mix of pass and skip."""
        parent = MockTestItem(name="parent")
        child1 = MockTestItem(name="child1", parent=parent)
        child2 = MockTestItem(name="child2", parent=parent)

        child1.set_status(TestStatus.PASS)
        child2.set_status(TestStatus.SKIP)

        parent.children["child1"] = child1
        parent.children["child2"] = child2

        status = parent._get_status_from_children()
        assert status == TestStatus.PASS
