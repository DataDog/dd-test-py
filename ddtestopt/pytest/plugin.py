import os
import uuid
import msgpack
import re
import pytest
import requests
import typing as t
from ddtestopt.recorder import TestSession, TestModule, TestSuite, Test, ModuleRef, SuiteRef, TestRef, Event
from ddtestopt.recorder import test_to_event, suite_to_event, module_to_event, session_to_event
from ddtestopt.ddtrace import install_global_trace_filter, trace_context

_NODEID_REGEX = re.compile("^(((?P<module>.*)/)?(?P<suite>[^/]*?))::(?P<name>.*?)$")


def nodeid_to_test_ref(nodeid: str) -> TestRef:
    matches = _NODEID_REGEX.match(nodeid)
    module_ref = ModuleRef(matches.group("module"))
    suite_ref = SuiteRef(module_ref, matches.group("suite"))
    test_ref = TestRef(suite_ref, matches.group("name"))
    return test_ref



class TestOptPlugin:
    def __init__(self):
        self.enable_ddtrace = False

    def pytest_sessionstart(self, session):
        self.writer = TestOptWriter()
        self.session = TestSession(name="pytest")

        if self.enable_ddtrace:
            install_global_trace_filter(self.writer)

    def pytest_sessionfinish(self, session):
        self.session.finish()
        self.writer.append_event(session_to_event(self.session))
        self.writer.send()

    @pytest.hookimpl(tryfirst=True, hookwrapper=True, specname="pytest_runtest_protocol")
    def pytest_runtest_protocol(self, item, nextitem):
        test_ref = nodeid_to_test_ref(item.nodeid)
        test_module = self.session.get_or_create_child(test_ref.suite.module.name)
        test_suite = test_module.get_or_create_child(test_ref.suite.name)
        test = test_suite.get_or_create_child(test_ref.name)
        next_test_ref = nodeid_to_test_ref(nextitem.nodeid) if nextitem else None

        with trace_context(self.enable_ddtrace) as context:
            yield

        test.finish()

        self.writer.append_event(test_to_event(test, context))

        if not next_test_ref or test_ref.suite != next_test_ref.suite:
            test_suite.finish()
            self.writer.append_event(suite_to_event(test_suite))

        if not next_test_ref or test_ref.suite.module != next_test_ref.suite.module:
            test_module.finish()
            self.writer.append_event(module_to_event(test_module))


def pytest_configure(config):
    config.pluginmanager.register(TestOptPlugin())


class TestOptWriter:
    def __init__(self):
        self.events: t.List[Event] = []
        self.api_key = os.environ["DD_API_KEY"]

    def append_event(self, event: Event) -> None:
        self.events.append(event)

    def send(self):
        payload = {
            "version": 1,
            "metadata": {
                "*": {
                    "language": "python",
                    "env": "vitor-test-ddtestopt",
                    "runtime-id": uuid.uuid4().hex,
                    "library_version": "0.0.0",
                },
            },
            "events": self.events,
        }
        breakpoint()
        pack = msgpack.packb(payload)
        url = "https://citestcycle-intake.datadoghq.com/api/v2/citestcycle"
        #url = "https://citestcycle-intake.datad0g.com/api/v2/citestcycle"
        response = requests.post(
            url,
            data=pack,
            headers={
                "content-type": "application/msgpack",
                "dd-api-key": self.api_key,
            },
        )
        print(response)
