import logging
import os
import threading
import typing as t
import uuid

import msgpack  # type: ignore

from ddtestopt.internal.http import BackendConnector
from ddtestopt.internal.test_data import TestItem
from ddtestopt.internal.test_data import TestModule
from ddtestopt.internal.test_data import TestRun
from ddtestopt.internal.test_data import TestSession
from ddtestopt.internal.test_data import TestStatus
from ddtestopt.internal.test_data import TestSuite


log = logging.getLogger(__name__)


class Event(dict):
    pass


TSerializable = t.TypeVar("TSerializable", bound=TestItem)

EventSerializer = t.Callable[[TSerializable], Event]


class TestOptWriter:
    def __init__(self, site: str, api_key: str) -> None:
        self.site = site
        self.api_key = api_key

        self.lock = threading.RLock()
        self.should_finish = threading.Event()
        self.flush_interval_seconds = 60
        self.events: t.List[Event] = []
        self.metadata: t.Dict[str, t.Dict[str, str]] = {
            "*": {
                "language": "python",
                "runtime-id": uuid.uuid4().hex,
                "library_version": "0.0.0",
                "_dd.origin": "ciapp-test",
                "_dd.p.dm": "-0",  # what is this?
            },
            "test": {
                "_dd.library_capabilities.early_flake_detection": "1",
                "_dd.library_capabilities.auto_test_retries": "1",
                "_dd.library_capabilities.test_impact_analysis": "1",
                "_dd.library_capabilities.test_management.quarantine": "1",
                "_dd.library_capabilities.test_management.disable": "1",
                "_dd.library_capabilities.test_management.attempt_to_fix": "4",
            },
        }
        self.api_key = os.environ["DD_API_KEY"]
        self.connector = BackendConnector(
            host=f"citestcycle-intake.{self.site}",
            default_headers={"dd-api-key": self.api_key},
        )

        self.serializers: t.Dict[t.Type[TestItem], EventSerializer] = {
            TestRun: test_run_to_event,
            TestSuite: suite_to_event,
            TestModule: module_to_event,
            TestSession: session_to_event,
        }

    def put_item(self, item: TestItem) -> None:
        event = self.serializers[type(item)](item)
        self.put_event(event)

    def put_event(self, event: Event) -> None:
        # TODO: compute/estimate payload size as events are inserted, and force a push once we reach a certain size.
        with self.lock:
            self.events.append(event)

    def pop_events(self) -> t.List[Event]:
        with self.lock:
            events = self.events
            self.events = []

        return events

    def add_metadata(self, event_type: str, metadata: t.Dict[str, str]) -> None:
        self.metadata[event_type].update(metadata)

    def start(self):
        self.task = threading.Thread(target=self._periodic_task)
        self.task.start()

    def finish(self):
        log.debug("Waiting for writer thread to finish")
        self.should_finish.set()
        self.task.join()
        log.debug("Writer thread finished")

    def _periodic_task(self):
        while True:
            self.should_finish.wait(timeout=self.flush_interval_seconds)
            log.debug("Flushing events in background task")
            self.flush()

            if self.should_finish.is_set():
                break

        log.debug("Exiting background task")

    def flush(self):
        if events := self.pop_events():
            log.debug("Sending %d events", len(events))
            self._send_events(events)

    def _send_events(self, events: t.List[Event]):
        payload = {
            "version": 1,
            "metadata": self.metadata,
            "events": events,
        }
        pack = msgpack.packb(payload)
        response, response_data = self.connector.request(
            "POST", "/api/v2/citestcycle", data=pack, headers={"Content-Type": "application/msgpack"}, send_gzip=True
        )


def test_run_to_event(test_run: TestRun) -> Event:
    return Event(
        version=2,
        type="test",
        content={
            "trace_id": test_run.trace_id,
            "parent_id": 1,
            "span_id": test_run.span_id,
            "service": test_run.service,
            "resource": test_run.name,
            "name": "pytest.test",
            "error": 1 if test_run.get_status() == TestStatus.FAIL else 0,
            "start": test_run.start_ns,
            "duration": test_run.duration_ns,
            "meta": {
                **test_run.parent.tags,
                **test_run.tags,
                "span.kind": "test",
                "test.module": test_run.parent.parent.parent.name,
                "test.module_path": test_run.parent.parent.parent.module_path,
                "test.name": test_run.name,
                "test.status": test_run.get_status().value,
                "test.suite": test_run.parent.parent.name,
                "test.type": "test",
                "type": "test",
            },
            "metrics": {
                "_dd.py.partial_flush": 1,
                "_dd.top_level": 1,
                "_dd.tracer_kr": 1.0,
                "_sampling_priority_v1": 1,
                **test_run.metrics,
            },
            "type": "test",
            "test_session_id": test_run.session_id,
            "test_module_id": test_run.module_id,
            "test_suite_id": test_run.suite_id,
        },
    )


def suite_to_event(suite: TestSuite) -> Event:
    return Event(
        version=1,
        type="test_suite_end",
        content={
            "service": suite.service,
            "resource": suite.name,
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
            "itr_correlation_id": "9b237bb3f20ae3a2463e084cfb09219d",  # ꙮ
        },
    )


def module_to_event(module: TestModule) -> Event:
    return Event(
        version=1,
        type="test_module_end",
        content={
            "service": module.service,
            "resource": module.name,
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
            "service": session.service,
            "resource": session.name,
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


CoverageEvent = Event


class TestCoverageWriter:
    def __init__(self, site: str, api_key: str) -> None:
        self.site = site
        self.api_key = api_key

        self.lock = threading.RLock()
        self.should_finish = threading.Event()
        self.flush_interval_seconds = 60
        self.events: t.List[CoverageEvent] = []

        self.api_key = os.environ["DD_API_KEY"]
        self.connector = BackendConnector(
            host=f"citestcov-intake.{self.site}",
            default_headers={"dd-api-key": self.api_key},
        )

    def put_coverage(self, test_run: TestRun, coverage_data) -> None:
        event = CoverageEvent(
            test_session_id=test_run.session_id,
            test_suite_id=test_run.suite_id,
            span_id=test_run.span_id,
            files={pathname: coverage.to_bytes() for pathname, coverage in coverage_data.items()},
        )
        self.put_event(event)

    def put_event(self, event: CoverageEvent) -> None:
        # TODO: compute/estimate payload size as events are inserted, and force a push once we reach a certain size.
        with self.lock:
            self.events.append(event)

    def pop_events(self) -> t.List[Event]:
        with self.lock:
            events = self.events
            self.events = []

        return events

    def start(self):
        self.task = threading.Thread(target=self._periodic_task)
        self.task.start()

    def finish(self):
        log.debug("Waiting for writer thread to finish")
        self.should_finish.set()
        self.task.join()
        log.debug("Writer thread finished")

    def _periodic_task(self):
        while True:
            self.should_finish.wait(timeout=self.flush_interval_seconds)
            log.debug("Flushing events in background task")
            self.flush()

            if self.should_finish.is_set():
                break

        log.debug("Exiting background task")

    def flush(self):
        if events := self.pop_events():
            log.debug("Sending %d events", len(events))
            self._send_events(events)

    def _send_events(self, events: t.List[CoverageEvent]):
        boundary = uuid.uuid4().hex
        boundary_bytes = boundary.encode("utf-8")
        content_type = f"multipart/form-data; boundary={boundary}"

        coverage_data = msgpack.packb({"version": 2, "coverages": events})

        body_lines = self._build_coverage_attachment(boundary_bytes, coverage_data)
        body_lines += self._build_json_attachment(boundary_bytes)
        body_lines += [b"--%s--" % boundary_bytes]
        body = b"\r\n".join(body_lines)

        response, response_data = self.connector.request(
            "POST", "/api/v2/citestcov", data=body, headers={"Content-Type": content_type}, send_gzip=True
        )

    def _build_coverage_attachment(self, boundary_bytes: bytes, coverage_data: bytes):
        return [
            b"--%s" % boundary_bytes,
            b'Content-Disposition: form-data; name="coverage1"; filename="coverage1.msgpack"',
            b"Content-Type: application/msgpack",
            b"",
            coverage_data,
        ]

    def _build_json_attachment(self, boundary_bytes: bytes) -> t.List[bytes]:
        return [
            b"--%s" % boundary_bytes,
            b'Content-Disposition: form-data; name="event"; filename="event.json"',
            b"Content-Type: application/json",
            b"",
            b'{"dummy":true}',
        ]
