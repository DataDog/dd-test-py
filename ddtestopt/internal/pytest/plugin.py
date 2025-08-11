from collections import defaultdict
from io import StringIO
import os
from pathlib import Path
import re
import traceback
import typing as t

import pytest
from _pytest.runner import runtestprotocol

from ddtestopt.internal.ddtrace import install_global_trace_filter
from ddtestopt.internal.ddtrace import trace_context
from ddtestopt.internal.recorder import ModuleRef
from ddtestopt.internal.recorder import SessionManager
from ddtestopt.internal.recorder import SuiteRef
from ddtestopt.internal.recorder import Test
from ddtestopt.internal.recorder import TestModule
from ddtestopt.internal.recorder import TestRef
from ddtestopt.internal.recorder import TestSession
from ddtestopt.internal.recorder import TestStatus
from ddtestopt.internal.recorder import TestSuite
from ddtestopt.internal.recorder import TestTag
from ddtestopt.internal.recorder import module_to_event
from ddtestopt.internal.recorder import session_to_event
from ddtestopt.internal.recorder import suite_to_event
from ddtestopt.internal.recorder import test_to_event
from ddtestopt.internal.recorder import RetryHandler


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
        self.reports_by_nodeid: t.Dict[str, _ReportGroup] = defaultdict(lambda: {})
        self.excinfo_by_report: t.Dict[pytest.TestReport, pytest.ExceptionInfo] = {}
        self.tests_by_nodeid: t.Dict[str, Test] = {}

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

    def _discover_test(self, item: pytest.Item, test_ref: TestRef) -> t.Tuple[TestModule, TestSuite, Test]:
        """
        Return the module, suite and test objects for a given test item, creating them if necessary.
        """
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

        return test_module, test_suite, test

    @pytest.hookimpl(tryfirst=True, hookwrapper=True, specname="pytest_runtest_protocol")
    def pytest_runtest_protocol_wrapper(self, item: pytest.Item, nextitem: t.Optional[pytest.Item]) -> None:
        test_ref = nodeid_to_test_ref(item.nodeid)
        next_test_ref = nodeid_to_test_ref(nextitem.nodeid) if nextitem else None

        test_module, test_suite, test = self._discover_test(item, test_ref)
        self.tests_by_nodeid[item.nodeid] = test

        with trace_context(self.enable_ddtrace) as context:
            yield

        if not test.test_runs:
            # No test runs: our pytest_runtest_protocol did not run, some other plugin did it instead.
            # In this case, we create a test run now with the test results of the plugin run as a fallback.
            test_run = test.make_test_run()
            status, tags = self._get_test_outcome(item.nodeid)
            test_run.set_status(status)
            test_run.set_tags(tags)
            test_run.set_context(context)
            test_run.finish()  ## now?
            self.manager.writer.append_event(test_to_event(test_run))

        test.finish()

        if not next_test_ref or test_ref.suite != next_test_ref.suite:
            test_suite.finish()
            self.manager.writer.append_event(suite_to_event(test_suite))

        if not next_test_ref or test_ref.suite.module != next_test_ref.suite.module:
            test_module.finish()
            self.manager.writer.append_event(module_to_event(test_module))

    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: t.Optional[pytest.Item]) -> None:
        test = self.tests_by_nodeid[item.nodeid]
        test_run = test.make_test_run()

        with trace_context(self.enable_ddtrace) as context:
            reports = _make_reports_dict(runtestprotocol(item, nextitem=nextitem, log=False))

        status, tags = self._get_test_outcome(item.nodeid)
        test_run.set_status(status)
        test_run.set_tags(tags)
        test_run.set_context(context)
        test_run.finish() ## now?
        self.manager.writer.append_event(test_to_event(test_run))

        for handler in self.manager.retry_handlers:
            if handler.should_apply(test):
                test_run.set_tags(handler.get_tags_for_test_run(test_run))
                self._do_retries(item, nextitem, test, reports, handler)
                break
        else:
            # No handler applied, finish test normally.
            for when in (TestPhase.SETUP, TestPhase.CALL, TestPhase.TEARDOWN):
                if report := reports.get(when):
                    item.ihook.pytest_runtest_logreport(report=report)


        # if quarantined: set some tags and modify test reports

        # try one of:
        #   - Attempt-to-Fix  (if ...)
        #   - EFD             (if is_new)  ~ should never happen with quarantine
        #   - ATR             (if not is_now and status == FAIL)


        return True

    def _do_retries(self, item: pytest.Item, nextitem: t.Optional[pytest.Item], test: Test, reports: _ReportGroup, handler: RetryHandler) -> None:
        item.ihook.pytest_runtest_logreport(report=reports[TestPhase.SETUP])


        while handler.should_retry(test):
            reports[TestPhase.CALL].outcome = "dd_retry"
            item.ihook.pytest_runtest_logreport(report=reports[TestPhase.CALL])

            test_run = test.make_test_run()

            with trace_context(self.enable_ddtrace) as context:
                reports = _make_reports_dict(runtestprotocol(item, nextitem=nextitem, log=False))

            status, tags = self._get_test_outcome(item.nodeid)
            test_run.set_status(status)
            test_run.set_tags(tags)
            test_run.set_tags(handler.get_tags_for_test_run(test_run))
            test_run.set_context(context)
            test_run.finish() ## now?
            self.manager.writer.append_event(test_to_event(test_run))

        item.ihook.pytest_runtest_logreport(report=reports[TestPhase.CALL])
        item.ihook.pytest_runtest_logreport(report=reports[TestPhase.TEARDOWN])

        test.set_status(handler.get_final_status(test))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo) -> None:
        """
        Save report and exception information for later use.
        """
        outcome = yield
        report: pytest.TestReport = outcome.get_result()
        self.reports_by_nodeid[item.nodeid][call.when] = report
        self.excinfo_by_report[report] = call.excinfo

    def _get_test_outcome(self, nodeid: str) -> t.Tuple[TestStatus, t.Dict[str, str]]:
        """
        Return test status and tags with exception/skip information for a given executed test.

        This methods consumes the test reports and exception information for the specified test, and removes them from
        the dictionaries. XXX
        """
        reports_dict = self.reports_by_nodeid[nodeid] # , {})

        for phase in (TestPhase.SETUP, TestPhase.CALL, TestPhase.TEARDOWN):
            report = reports_dict.get(phase)
            if not report:
                continue

            excinfo = self.excinfo_by_report.get(report, None)
            if report.failed:
                return TestStatus.FAIL, _get_exception_tags(excinfo)
            if report.skipped:
                return TestStatus.SKIP, {TestTag.SKIP_REASON: str(excinfo.value)}

        return TestStatus.PASS, {}


def _make_reports_dict(reports) -> _ReportGroup:
    return {report.when: report for report in reports}

def pytest_configure(config):
    config.pluginmanager.register(TestOptPlugin())


def _get_exception_tags(excinfo: pytest.ExceptionInfo) -> t.Dict[str, str]:
    max_entries = 30
    buf = StringIO()
    # TODO: handle MAX_SPAN_META_VALUE_LEN
    traceback.print_exception(excinfo.type, excinfo.value, excinfo.tb, limit=-max_entries, file=buf)

    return {
        TestTag.ERROR_STACK: buf.getvalue(),
        TestTag.ERROR_TYPE: "%s.%s" % (excinfo.type.__module__, excinfo.type.__name__),
        TestTag.ERROR_MESSAGE: str(excinfo.value),
    }
