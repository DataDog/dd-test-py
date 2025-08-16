import gzip
import os
import typing as t
import urllib.request
import uuid

import msgpack  # type: ignore

from ddtestopt.internal.test_data import TestItem
from ddtestopt.internal.test_data import TestModule
from ddtestopt.internal.test_data import TestRun
from ddtestopt.internal.test_data import TestSession
from ddtestopt.internal.test_data import TestStatus
from ddtestopt.internal.test_data import TestSuite


class Event(dict):
    pass


TSerializable = t.TypeVar("TSerializable", bound=TestItem)

EventSerializer = t.Callable[[TSerializable], Event]


class TestOptWriter:
    def __init__(self) -> None:
        self.events: t.List[Event] = []
        self.metadata: t.Dict[str, t.Dict[str, str]] = {
            "*": {
                "language": "python",
                "runtime-id": uuid.uuid4().hex,
                "library_version": "0.0.0",
                "_dd.origin": "ciapp-test",
                "_dd.p.dm": "-0",  # what is this?
            },
        }
        self.api_key = os.environ["DD_API_KEY"]
        self.gzip_enabled = True

        self.serializers: t.Dict[t.Type[TestItem], EventSerializer] = {
            TestRun: test_run_to_event,
            TestSuite: suite_to_event,
            TestModule: module_to_event,
            TestSession: session_to_event,
        }

    def put_item(self, item: TestItem) -> None:
        event = self.serializers[type(item)](item)
        self.events.append(event)

    def put_event(self, event: Event) -> None:
        self.events.append(event)

    def add_metadata(self, event_type: str, metadata: t.Dict[str, str]) -> None:
        self.metadata[event_type].update(metadata)

    def send(self):
        payload = {
            "version": 1,
            "metadata": self.metadata,
            "events": self.events,
        }
        pack = msgpack.packb(payload)
        url = "https://citestcycle-intake.datadoghq.com/api/v2/citestcycle"
        # url = "https://citestcycle-intake.datad0g.com/api/v2/citestcycle"
        request = urllib.request.Request(url)
        request.add_header("content-type", "application/msgpack")
        request.add_header("dd-api-key", self.api_key)

        breakpoint()

        if self.gzip_enabled:
            pack = gzip.compress(pack, compresslevel=6)
            request.add_header("Content-Encoding", "gzip")

        response = urllib.request.urlopen(request, data=pack)
        content = response.read()
        print(response, content)

    @classmethod
    def register_serializer(cls, item_type: t.Type[TestItem]) -> t.Callable[[EventSerializer], EventSerializer]:
        def decorator(serializer: EventSerializer) -> EventSerializer:
            cls.serializers[item_type] = serializer
            return serializer

        return decorator


def test_run_to_event(test: TestRun) -> Event:
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
            "error": 1 if test.get_status() == TestStatus.FAIL else 0,
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
