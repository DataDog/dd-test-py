import os
from pathlib import Path
import re
import typing as t

import pytest

from ddtestopt.ddtrace import install_global_trace_filter
from ddtestopt.ddtrace import trace_context
from ddtestopt.recorder import ModuleRef
from ddtestopt.recorder import SessionManager
from ddtestopt.recorder import SuiteRef
from ddtestopt.recorder import TestRef
from ddtestopt.recorder import TestSession
from ddtestopt.recorder import TestStatus
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


class TestPhase:
    SETUP = "setup"
    CALL = "call"
    TEARDOWN = "teardown"


_ReportGroup = t.Dict[str, pytest.TestReport]


class TestOptPlugin:
    def __init__(self):
        self.enable_ddtrace = True
        self.reports_by_nodeid: t.Dict[str, _ReportGroup] = {}
        self.excinfo_by_report: t.Dict[pytest.TestReport, pytest.ExceptionInfo] = {}

    def pytest_sessionstart(self, session: pytest.Session):
        self.session = TestSession(name="pytest")
        self.session.set_attributes(
            test_command=self._get_test_command(session),
            test_framework="pytest",
            test_framework_version=pytest.__version__,
        )

        self.manager = SessionManager(session=self.session)
        self.manager.start()

        if self.enable_ddtrace:
            install_global_trace_filter(self.manager.writer)

    def pytest_sessionfinish(self, session):
        self.session.finish()
        self.manager.writer.append_event(session_to_event(self.session))
        self.manager.writer.send()
        self.manager.finish()

    def _get_test_command(self, session: pytest.Session) -> str:
        """Extract and re-create pytest session command from pytest config."""
        command = "pytest"
        if invocation_params := getattr(session.config, "invocation_params", None):
            command += " {}".format(" ".join(invocation_params.args))
        if addopts := os.environ.get("PYTEST_ADDOPTS"):
            command += " {}".format(addopts)
        return command

    @pytest.hookimpl(tryfirst=True, hookwrapper=True, specname="pytest_runtest_protocol")
    def pytest_runtest_protocol(self, item, nextitem):
        test_ref = nodeid_to_test_ref(item.nodeid)

        # test_module = self.session.get_child(
        #     name=test_ref.suite.module.name,
        #     or_create=lambda: TestModule(
        #         ...
        #     )
        # )

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

        test.status = self._get_test_status(item.nodeid)
        test.finish()

        self.manager.writer.append_event(test_to_event(test, context))

        if not next_test_ref or test_ref.suite != next_test_ref.suite:
            test_suite.finish()
            self.manager.writer.append_event(suite_to_event(test_suite))

        if not next_test_ref or test_ref.suite.module != next_test_ref.suite.module:
            test_module.finish()
            self.manager.writer.append_event(module_to_event(test_module))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo) -> None:
        """
        Save report and exception information for later use.
        """
        outcome = yield
        report: pytest.TestReport = outcome.get_result()
        self.reports_by_nodeid.setdefault(item.nodeid, {})[call.when] = report
        self.excinfo_by_report[report] = call.excinfo

    def _get_test_status(self, nodeid) -> TestStatus:
        reports_dict = self.reports_by_nodeid.get(nodeid)
        for phase in (TestPhase.SETUP, TestPhase.CALL, TestPhase.TEARDOWN):
            report = reports_dict.get(phase)
            if not report:
                continue
            if report.failed:
                return TestStatus.FAIL
            if report.skipped:
                return TestStatus.SKIP

        return TestStatus.PASS


def pytest_configure(config):
    config.pluginmanager.register(TestOptPlugin())
