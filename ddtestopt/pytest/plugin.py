from pathlib import Path
import re

import pytest

from ddtestopt.ddtrace import install_global_trace_filter
from ddtestopt.ddtrace import trace_context
from ddtestopt.recorder import ModuleRef
from ddtestopt.recorder import SessionManager
from ddtestopt.recorder import SuiteRef
from ddtestopt.recorder import TestRef
from ddtestopt.recorder import TestSession
from ddtestopt.recorder import module_to_event
from ddtestopt.recorder import session_to_event
from ddtestopt.recorder import suite_to_event
from ddtestopt.recorder import test_to_event


_NODEID_REGEX = re.compile("^(((?P<module>.*)/)?(?P<suite>[^/]*?))::(?P<name>.*?)$")


def nodeid_to_test_ref(nodeid: str) -> TestRef:
    matches = _NODEID_REGEX.match(nodeid)
    module_ref = ModuleRef(matches.group("module"))
    suite_ref = SuiteRef(module_ref, matches.group("suite"))
    test_ref = TestRef(suite_ref, matches.group("name"))
    return test_ref


def _get_module_path_from_item(item: pytest.Item) -> Path:
    try:
        item_path = getattr(item, "path", None)
        if item_path is not None:
            return item.path.absolute().parent
        return Path(item.module.__file__).absolute().parent
    except Exception:  # noqa: E722
        return Path.cwd()


class TestOptPlugin:
    def __init__(self):
        self.enable_ddtrace = True

    def pytest_sessionstart(self, session):
        self.session = TestSession(name="pytest")
        self.manager = SessionManager(session=self.session)
        self.manager.start()

        if self.enable_ddtrace:
            install_global_trace_filter(self.manager.writer)

    def pytest_sessionfinish(self, session):
        self.session.finish()
        self.manager.writer.append_event(session_to_event(self.session))
        self.manager.writer.send()
        self.manager.finish()

    @pytest.hookimpl(tryfirst=True, hookwrapper=True, specname="pytest_runtest_protocol")
    def pytest_runtest_protocol(self, item, nextitem):
        test_ref = nodeid_to_test_ref(item.nodeid)

        test_module, created = self.session.get_or_create_child(test_ref.suite.module.name)
        if created:
            test_module.set_attributes(module_path=_get_module_path_from_item(item))

        test_suite, created = test_module.get_or_create_child(test_ref.suite.name)
        # if created:
        #     test_suite.set_attributes(...)

        test, created = test_suite.get_or_create_child(test_ref.name)
        if created:
            path, start_line, _test_name = item.reportinfo()
            test.set_attributes(path=path, start_line=start_line)

        next_test_ref = nodeid_to_test_ref(nextitem.nodeid) if nextitem else None

        with trace_context(self.enable_ddtrace) as context:
            yield

        test.finish()

        self.manager.writer.append_event(test_to_event(test, context))

        if not next_test_ref or test_ref.suite != next_test_ref.suite:
            test_suite.finish()
            self.manager.writer.append_event(suite_to_event(test_suite))

        if not next_test_ref or test_ref.suite.module != next_test_ref.suite.module:
            test_module.finish()
            self.manager.writer.append_event(module_to_event(test_module))


def pytest_configure(config):
    config.pluginmanager.register(TestOptPlugin())
