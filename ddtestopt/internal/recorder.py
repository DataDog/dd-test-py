from __future__ import annotations

from abc import ABC
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import time
import typing as t

from ddtestopt.internal.git import get_git_tags
from ddtestopt.internal.platform import get_platform_tags
from ddtestopt.internal.utils import TestContext
from ddtestopt.internal.utils import _gen_item_id
from ddtestopt.internal.writer import Event
from ddtestopt.internal.writer import TestOptWriter


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
        self.start_ns: t.Optional[int] = time.time_ns()
        self.duration_ns: t.Optional[int] = None
        self.parent: t.Optional[TestItem] = None
        self.item_id = _gen_item_id()
        self.status: t.Optional[TestStatus] = None
        self.tags: t.Dict[str, str] = {}
        self.metrics: t.Dict[str, t.Union[int, float]] = {}

    def finish(self):
        self.duration_ns = time.time_ns() - self.start_ns

    def is_finished(self) -> bool:
        return self.duration_ns is not None

    def get_status(self) -> TestStatus:
        if self.children: # ꙮ
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

        self.test_runs = []

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


class SessionManager:
    def __init__(self, writer: t.Optional[TestOptWriter] = None, session: t.Optional[TestSession] = None) -> None:
        self.writer = writer or TestOptWriter()
        self.session = session or TestSession(name="test")

        self.retry_handlers = [EarlyFlakeDetectionHandler(), AutoTestRetriesHandler()]

    def start(self) -> None:
        self.writer.add_metadata("*", get_git_tags())
        self.writer.add_metadata("*", get_platform_tags())
        self.writer.add_metadata(
            "*",
            {
                TestTag.TEST_COMMAND: self.session.test_command,
                TestTag.TEST_FRAMEWORK: self.session.test_framework,
                TestTag.TEST_FRAMEWORK_VERSION: self.session.test_framework_version,
                TestTag.COMPONENT: self.session.test_framework,
                TestTag.ENV: os.environ.get("DD_ENV", "none"),
            },
        )

    def finish(self) -> None:
        pass


def test_to_event(test: Test) -> Event:
    return Event(
        version=2,
        type="test",
        content={
            "trace_id": test.trace_id,
            "parent_id": 1,
            "span_id": test.span_id,
            "service": "ddtestopt",
            "resource": test.name,
            "name": "pytest.test",
            "error": 1 if test.status == TestStatus.FAIL else 0,
            "start": test.start_ns,
            "duration": test.duration_ns,
            "meta": {
                **test.tags,
                "span.kind": "test",
                "test.module": test.parent.parent.parent.name,
                "test.module_path": test.parent.parent.parent.module_path,
                "test.name": test.name,
                "test.status": test.get_status().value,
                "test.suite": test.parent.parent.name,
                "test.type": "test",
                "type": "test",
            },
            "metrics": {
                "_dd.py.partial_flush": 1,
                "_dd.top_level": 1,
                "_dd.tracer_kr": 1.0,
                "_sampling_priority_v1": 1,
                **test.metrics,
            },
            "type": "test",
            "test_session_id": test.session_id,
            "test_module_id": test.module_id,
            "test_suite_id": test.suite_id,
        },
    )


def suite_to_event(suite: TestSuite) -> Event:
    return Event(
        version=1,
        type="test_suite_end",
        content={
            "service": "ddtestopt",
            "resource": "pytest.test_suite",
            "name": "pytest.test_suite",
            "error": 0,
            "start": suite.start_ns,
            "duration": suite.duration_ns,
            "meta": {
                **suite.tags,
                "span.kind": "test",
                "test.suite": suite.name,
                "test.status": suite.get_status().value,
                "type": "test_suite_end",
            },
            "metrics": {
                "_dd.py.partial_flush": 1,
                "_dd.tracer_kr": 1.0,
                "_sampling_priority_v1": 1,
                **suite.metrics,
            },
            "type": "test_suite_end",
            "test_session_id": suite.session_id,
            "test_module_id": suite.module_id,
            "test_suite_id": suite.suite_id,
            "itr_correlation_id": "9b237bb3f20ae3a2463e084cfb09219d",
        },
    )


def module_to_event(module: TestModule) -> Event:
    return Event(
        version=1,
        type="test_module_end",
        content={
            "service": "ddtestopt",
            "resource": "pytest.test_module",
            "name": "pytest.test_module",
            "error": 0,
            "start": module.start_ns,
            "duration": module.duration_ns,
            "meta": {
                **module.tags,
                "span.kind": "test",
                "test.module": module.name,
                "test.module_path": module.module_path,
                "test.status": module.get_status().value,
                "type": "test_module_end",
            },
            "metrics": {
                "_dd.py.partial_flush": 1,
                "_dd.tracer_kr": 1.0,
                "_sampling_priority_v1": 1,
                **module.metrics,
            },
            "type": "test_module_end",
            "test_session_id": module.session_id,
            "test_module_id": module.module_id,
        },
    )


def session_to_event(session: TestSession) -> Event:
    return Event(
        version=1,
        type="test_session_end",
        content={
            "service": "ddtestopt",
            "resource": "pytest.test_session",
            "name": "pytest.test_session",
            "error": 0,
            "start": session.start_ns,
            "duration": session.duration_ns,
            "meta": {
                **session.tags,
                "span.kind": "test",
                "test.status": session.get_status().value,
                "type": "test_session_end",
            },
            "metrics": {
                "_dd.py.partial_flush": 1,
                "_dd.top_level": 1,
                "_dd.tracer_kr": 1.0,
                "_sampling_priority_v1": 1,
                **session.metrics,
            },
            "type": "test_session_end",
            "test_session_id": session.session_id,
        },
    )


class RetryHandler:
    pass

class AutoTestRetriesHandler():
    def should_apply(self, test: Test) -> bool:
        return (
            test.last_test_run.get_status() == TestStatus.FAIL
            # and not test.is_new()
        )

    def should_retry(self, test: Test):
        return (
            test.last_test_run.get_status() == TestStatus.FAIL
            and len(test.test_runs) < 6
        )

    def get_final_status(self, test: Test):
        return test.last_test_run.get_status()

    def get_tags_for_test_run(self, test_run: TestRun) -> t.Dict[str, str]:
        if test_run.attempt_number == 0:
            return {}

        return {
            "test.is_retry": "true",
            "test.retry_reason": "auto_test_retry",
        }


class EarlyFlakeDetectionHandler():
    def should_apply(self, test: Test) -> bool:
        return (
            True
            # and test.is_new()
        )

    def should_retry(self, test: Test):
        return (
            test.last_test_run.get_status() != TestStatus.SKIP and
            len(test.test_runs) < 6  # should be based on total time and shenanigans
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
