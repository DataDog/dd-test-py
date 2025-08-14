from __future__ import annotations

from abc import ABC
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import time
import typing as t

from ddtestopt.internal.utils import TestContext
from ddtestopt.internal.utils import _gen_item_id


@dataclass
class ModuleRef:
    name: str


@dataclass
class SuiteRef:
    module: ModuleRef
    name: str


@dataclass
class TestRef:
    suite: SuiteRef
    name: str


class TestStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class TestItem(ABC):
    ChildClass: t.Type[TestItem]

    def __init__(self, name: str):
        self.name = name
        self.children: t.Dict[str, TestItem] = {}
        self.start_ns: int = time.time_ns()
        self.duration_ns: t.Optional[int] = None
        self.parent: t.Optional[TestItem] = None
        self.item_id = _gen_item_id()
        self.status: TestStatus = TestStatus.FAIL
        self.tags: t.Dict[str, str] = {}
        self.metrics: t.Dict[str, t.Union[int, float]] = {}

    def finish(self):
        self.duration_ns = time.time_ns() - self.start_ns

    def is_finished(self) -> bool:
        return self.duration_ns is not None

    def get_status(self) -> TestStatus:
        if self.children:  # ꙮ
            self.status = self._get_status_from_children()
        return self.status

    def set_status(self, status: TestStatus) -> None:
        self.status = status

    def _get_status_from_children(self) -> TestStatus:
        status_counts: t.Dict[TestStatus, int] = defaultdict(lambda: 0)
        total_count = 0

        for child in self.children.values():
            status = child.get_status()
            if status:
                status_counts[status] += 1
                total_count += 1

        if status_counts[TestStatus.FAIL] > 0:
            return TestStatus.FAIL

        if status_counts[TestStatus.SKIP] == total_count:
            return TestStatus.SKIP

        return TestStatus.PASS

    def get_or_create_child(self, name: str) -> t.Tuple[TestItem, bool]:
        created = False

        if name not in self.children:
            created = True
            child = self.ChildClass(name=name)
            child.parent = self
            self.children[name] = child

        return self.children[name], created

    def set_tags(self, tags: t.Dict[str, str]) -> None:
        self.tags.update(tags)


class TestRun(TestItem):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.span_id: t.Optional[int] = None
        self.trace_id: t.Optional[int] = None
        self.attempt_number: int = 0

    def set_context(self, context: TestContext) -> None:
        self.span_id = context.span_id
        self.trace_id = context.trace_id

    @property
    def suite_id(self) -> str:
        return self.parent.parent.item_id

    @property
    def module_id(self) -> str:
        return self.parent.parent.parent.item_id

    @property
    def session_id(self) -> str:
        return self.parent.parent.parent.parent.item_id


class Test(TestItem):
    ChildClass = TestRun

    def __init__(self, name: str) -> None:
        super().__init__(name)

        self.test_runs: t.List[TestRun] = []

    def set_attributes(self, path: Path, start_line: int) -> None:
        self.tags["test.source.file"] = str(path)
        self.metrics["test.source.start"] = start_line

    @property
    def suite_id(self) -> str:
        return self.parent.item_id

    @property
    def module_id(self) -> str:
        return self.parent.parent.item_id

    @property
    def session_id(self) -> str:
        return self.parent.parent.parent.item_id

    def make_test_run(self):
        test_run = TestRun(name=self.name)
        test_run.parent = self
        test_run.attempt_number = len(self.test_runs)
        self.test_runs.append(test_run)
        return test_run

    @property
    def last_test_run(self):
        return self.test_runs[-1]


class TestSuite(TestItem):
    ChildClass = Test

    @property
    def suite_id(self) -> str:
        return self.item_id

    @property
    def module_id(self) -> str:
        return self.parent.item_id

    @property
    def session_id(self) -> str:
        return self.parent.parent.item_id


class TestModule(TestItem):
    ChildClass = TestSuite

    @property
    def module_id(self) -> str:
        return self.item_id

    @property
    def session_id(self) -> str:
        return self.parent.item_id

    def set_attributes(self, module_path: Path) -> None:
        self.module_path = str(module_path)


class TestSession(TestItem):
    ChildClass = TestModule

    @property
    def session_id(self) -> str:
        return self.item_id

    def set_attributes(self, test_command: str, test_framework: str, test_framework_version: str) -> None:
        self.command = test_command
        self.test_command = test_command
        self.test_framework = test_framework
        self.test_framework_version = test_framework_version


class TestTag:
    COMPONENT = "component"
    TEST_COMMAND = "test.command"
    TEST_FRAMEWORK = "test.framework"
    TEST_FRAMEWORK_VERSION = "test.framework_version"

    ENV = "env"

    ERROR_STACK = "error.stack"
    ERROR_TYPE = "error.type"
    ERROR_MESSAGE = "error.message"

    SKIP_REASON = "test.skip_reason"


class RetryHandler:
    pass


class AutoTestRetriesHandler:
    def should_apply(self, test: Test) -> bool:
        return (
            False
            # test.last_test_run.get_status() == TestStatus.FAIL
            # and not test.is_new()
        )

    def should_retry(self, test: Test):
        return test.last_test_run.get_status() == TestStatus.FAIL and len(test.test_runs) < 6

    def get_final_status(self, test: Test):
        return test.last_test_run.get_status()

    def get_tags_for_test_run(self, test_run: TestRun) -> t.Dict[str, str]:
        if test_run.attempt_number == 0:
            return {}

        return {
            "test.is_retry": "true",
            "test.retry_reason": "auto_test_retry",
        }


class EarlyFlakeDetectionHandler:
    def should_apply(self, test: Test) -> bool:
        return (
            True
            # and test.is_new()
        )

    def should_retry(self, test: Test):
        return (
            # test.last_test_run.get_status() != TestStatus.SKIP and
            len(test.test_runs)
            < 6  # should be based on total time and shenanigans
        )

    def get_final_status(self, test: Test):
        status_counts: t.Dict[TestStatus, int] = defaultdict(lambda: 0)
        total_count = 0

        for test_run in test.test_runs:
            status_counts[test_run.get_status()] += 1
            total_count += 1

        if status_counts[TestStatus.PASS] > 0:
            return TestStatus.PASS

        if status_counts[TestStatus.FAIL] > 0:
            return TestStatus.FAIL

        return TestStatus.SKIP

    def get_tags_for_test_run(self, test_run: TestRun) -> t.Dict[str, str]:
        if test_run.attempt_number == 0:
            return {}

        return {
            "test.is_retry": "true",
            "test.retry_reason": "early_flake_detection",
        }
