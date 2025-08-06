from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import os
import time
import typing as t

from ddtestopt.utils import TestContext
from ddtestopt.utils import _gen_item_id


class Event(dict):
    pass


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
        self.start: t.Optional[int] = time.time_ns()
        self.duration: t.Optional[int] = None
        self.parent: t.Optional[TestItem] = None
        self.item_id = _gen_item_id()
        self.status: TestStatus = TestStatus.FAIL
        self.tags: t.Dict[str, str] = {}
        self.metrics: t.Dict[str, t.Union[int, float]] = {}

    def finish(self):
        self.duration = time.time_ns() - self.start

    def get_or_create_child(self, name):
        created = False
        if name not in self.children:
            created = True
            child = self.ChildClass(name=name)
            child.parent = self
            self.children[name] = child
        return self.children[name], created


class Test(TestItem):
    def __init__(self, name: str):
        super().__init__(name)
        self.span_id = self.item_id
        self.trace_id = _gen_item_id()

    def set_attributes(self, path: Path, start_line: int):
        self.tags["test.source.file"] = str(path)
        self.metrics["test.source.start"] = start_line

    @property
    def suite_id(self):
        return self.parent.item_id

    @property
    def module_id(self):
        return self.parent.parent.item_id

    @property
    def session_id(self):
        return self.parent.parent.parent.item_id


class TestSuite(TestItem):
    ChildClass = Test

    @property
    def suite_id(self):
        return self.item_id

    @property
    def module_id(self):
        return self.parent.item_id

    @property
    def session_id(self):
        return self.parent.parent.item_id


class TestModule(TestItem):
    ChildClass = TestSuite

    @property
    def module_id(self):
        return self.item_id

    @property
    def session_id(self):
        return self.parent.item_id

    def set_attributes(self, module_path: Path):
        self.module_path = str(module_path)


class TestSession(TestItem):
    ChildClass = TestModule

    @property
    def session_id(self):
        return self.item_id


class SessionManager:
    def __init__(self):
        self.service = os.getenv("DD_SERVICE", "test")
        self.env = os.getenv("DD_ENV", "none")

def test_to_event(test: Test, context: TestContext) -> Event:
    return Event(
        version=2,
        type="test",
        content={
            "trace_id": context.trace_id,
            "parent_id": 1,
            "span_id": context.span_id,
            "service": "ddtestopt",
            "resource": test.name,
            "name": "pytest.test",
            "error": 1 if test.status == TestStatus.FAIL else 0,
            "start": test.start,
            "duration": test.duration,
            "meta": {
                **GENERIC_METADATA,
                **test.tags,
                "test.itr.forced_run": "false",
                "test.itr.unskippable": "false",
                "test.module": test.parent.parent.name,
                "test.module_path": test.parent.parent.module_path,
                "test.name": test.name,
                "test.skipped_by_itr": "false",
                "test.status": "fail",
                "test.suite": test.parent.name,
                "test.type": "test",
                "type": "test",
            },
            "metrics": {
                "_dd.py.partial_flush": 1,
                "_dd.top_level": 1,
                "_dd.tracer_kr": 1.0,
                "_sampling_priority_v1": 1,
                "process_id": 8871,
                **test.metrics,
            },
            "type": "test",
            "test_session_id": test.session_id,
            "test_module_id": test.module_id,
            "test_suite_id": test.suite_id,
        },
    )


def suite_to_event(suite: TestSuite):
    return Event(
        version=1,
        type="test_suite_end",
        content={
            "service": "ddtestopt",
            "resource": "pytest.test_suite",
            "name": "pytest.test_suite",
            "error": 0,
            "start": suite.start,
            "duration": suite.duration,
            "meta": {
                **GENERIC_METADATA,
                **suite.tags,
                "test.suite": suite.name,
                "type": "test_suite_end",
            },
            "metrics": {
                "_dd.py.partial_flush": 1,
                "_dd.tracer_kr": 1.0,
                "_sampling_priority_v1": 1,
                "test.itr.tests_skipping.count": 0,
                **suite.metrics,

            },
            "type": "test_suite_end",
            "test_session_id": suite.session_id,
            "test_module_id": suite.module_id,
            "test_suite_id": suite.suite_id,
            "itr_correlation_id": "9b237bb3f20ae3a2463e084cfb09219d",
        },
    )


def module_to_event(module: TestModule):
    return Event(
        version=1,
        type="test_module_end",
        content={
            "service": "ddtestopt",
            "resource": "pytest.test_module",
            "name": "pytest.test_module",
            "error": 0,
            "start": module.start,
            "duration": module.duration,
            "meta": {
                **GENERIC_METADATA,
                **module.tags,
                "test.code_coverage.enabled": "true",
                "test.itr.forced_run": "false",
                "test.itr.tests_skipping.enabled": "true",
                "test.itr.tests_skipping.tests_skipped": "false",
                "test.itr.tests_skipping.type": "suite",
                "test.itr.unskippable": "false",
                "test.module": module.name,
                "test.module_path": module.module_path,
                "test.skipped_by_itr": "false",
                "test.status": "fail",
                "type": "test_module_end",
            },
            "metrics": {
                "_dd.py.partial_flush": 1,
                "_dd.tracer_kr": 1.0,
                "_sampling_priority_v1": 1,
                "test.itr.tests_skipping.count": 0,
                **module.metrics,
            },
            "type": "test_module_end",
            "test_session_id": module.session_id,
            "test_module_id": module.module_id,
        },
    )


def session_to_event(session: TestSession):
    return Event(
        version=1,
        type="test_session_end",
        content={
            "service": "ddtestopt",
            "resource": "pytest.test_session",
            "name": "pytest.test_session",
            "error": 0,
            "start": session.start,
            "duration": session.duration,
            "meta": {
                **GENERIC_METADATA,
                **session.tags,
                "test.code_coverage.enabled": "true",
                "test.itr.forced_run": "false",
                "test.itr.tests_skipping.enabled": "true",
                "test.itr.tests_skipping.tests_skipped": "false",
                "test.itr.tests_skipping.type": "suite",
                "test.itr.unskippable": "false",
                "test.skipped_by_itr": "false",
                "test.status": "fail",
                "test.test_management.enabled": "true",
                "type": "test_session_end",
            },
            "metrics": {
                "_dd.py.partial_flush": 1,
                "_dd.top_level": 1,
                "_dd.tracer_kr": 1.0,
                "_sampling_priority_v1": 1,
                "process_id": 8871,
                "test.itr.tests_skipping.count": 0,
                **session.metrics,
            },
            "type": "test_session_end",
            "test_session_id": session.session_id,
        },
    )


GENERIC_METADATA = {
    "_dd.origin": "ciapp-test",
    "_dd.p.dm": "-0",
    "_dd.p.tid": "6887857000000000",  ###
    "ci.workspace_path": "/home/vitor.dearaujo/test-repos/some-repo",
    "component": "pytest",
    "env": "vitor-test-ddtestopt",
    "git.branch": "master",
    "git.commit.author.date": "2025-05-19T16:25:30+0000",
    "git.commit.author.email": "vitor.dearaujo@datadoghq.com",
    "git.commit.author.name": "Vítor De Araújo",
    "git.commit.committer.date": "2025-05-19T16:25:30+0000",
    "git.commit.committer.email": "vitor.dearaujo@datadoghq.com",
    "git.commit.committer.name": "Vítor De Araújo",
    "git.commit.message": "skippable",
    "git.commit.sha": "f1f19359a53f53d783f019ea3d472b25cd292390",
    "git.repository_url": "github.com:vitor-de-araujo/some-repo.git",
    "language": "python",
    "library_version": "3.12.0.dev22+g61670b7c4d.d20250723",
    "os.architecture": "x86_64",
    "os.platform": "Linux",
    "os.version": "6.8.0-47-generic",
    "runtime-id": "b73b8b7815a84b848e2238bbe3af4538",
    "runtime.name": "CPython",
    "runtime.version": "3.10.14",
    "span.kind": "test",
    "test.codeowners": '["@DataDog/apm-core-python"]',
    "test.command": "pytest --ddtrace tests/xdist/1/test_xdist_1.py",
    "test.framework": "pytest",
    "test.framework_version": "8.3.4",
}
