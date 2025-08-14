from collections import defaultdict
from io import StringIO
import os
from pathlib import Path
import re
import traceback
import typing as t

from _pytest.runner import runtestprotocol
import pytest

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
from ddtestopt.internal.utils import TestContext


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
            test_run.finish()
            self.manager.writer.append_event(test_to_event(test_run))

        test.finish()

        if not next_test_ref or test_ref.suite != next_test_ref.suite:
            test_suite.finish()
            self.manager.writer.append_event(suite_to_event(test_suite))

        if not next_test_ref or test_ref.suite.module != next_test_ref.suite.module:
            test_module.finish()
            self.manager.writer.append_event(module_to_event(test_module))

    def _do_one_test_run(self, item: pytest.Item, nextitem: t.Optional[pytest.Item], context: TestContext) -> None:
        test = self.tests_by_nodeid[item.nodeid]
        test_run = test.make_test_run()
        reports = _make_reports_dict(runtestprotocol(item, nextitem=nextitem, log=False))
        status, tags = self._get_test_outcome(item.nodeid)
        test_run.set_status(status)
        test_run.set_tags(tags)
        test_run.set_context(context)

        return test_run, reports

    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: t.Optional[pytest.Item]) -> None:
        self._do_test_runs(item, nextitem)
        return True  # Do not run other pytest_runtest_protocol hooks after this one.

    def _do_test_runs(self, item: pytest.Item, nextitem: t.Optional[pytest.Item]) -> None:
        test = self.tests_by_nodeid[item.nodeid]
        retry_handler = self._check_applicable_retry_handlers(test)

        with trace_context(self.enable_ddtrace) as context:
            test_run, reports = self._do_one_test_run(item, nextitem, context)

        if retry_handler and retry_handler.should_retry(test):
            self._do_retries(item, nextitem, test, retry_handler, reports)
        else:
            self._log_test_reports(item, reports)
            test_run.finish()
            self.manager.writer.append_event(test_to_event(test_run))

    def _do_retries(self, item, nextitem, test, retry_handler, reports):
        # Save failure/skip representation to put into the final report.
        # TODO: for flaky tests, we currently don't show the longrepr (because the final report has `passed` status).
        longrepr = self._extract_longrepr(reports)

        # Log initial attempt.
        self._mark_test_reports_as_retry(reports)
        self._log_test_report(item, reports, TestPhase.SETUP)
        self._log_test_report(item, reports, TestPhase.CALL)

        test_run = test.last_test_run
        test_run.set_tags(retry_handler.get_tags_for_test_run(test_run))
        test_run.finish()
        self.manager.writer.append_event(test_to_event(test_run))

        should_retry = True

        while should_retry:
            with trace_context(self.enable_ddtrace) as context:
                test_run, reports = self._do_one_test_run(item, nextitem, context)

            should_retry = retry_handler.should_retry(test)
            test_run.set_tags(retry_handler.get_tags_for_test_run(test_run))
            self._mark_test_reports_as_retry(reports)
            if not self._log_test_report(item, reports, TestPhase.CALL):
                self._log_test_report(item, reports, TestPhase.SETUP)
            test_run.finish()
            self.manager.writer.append_event(test_to_event(test_run))

        final_status = retry_handler.get_final_status(test)
        test.set_status(final_status)

        # Log final status.
        final_report = self._make_final_report(item, final_status, longrepr)
        item.ihook.pytest_runtest_logreport(report=final_report)

        # Log teardown.
        self._log_test_report(item, reports, TestPhase.TEARDOWN)

    def _check_applicable_retry_handlers(self, test: Test):
        for handler in self.manager.retry_handlers:
            if handler.should_apply(test):
                return handler

        return None

    def _extract_longrepr(self, reports: _ReportGroup):
        # The call longrepr is more interesting for us, if available.
        for when in (TestPhase.CALL, TestPhase.SETUP, TestPhase.TEARDOWN):
            if report := reports.get(when):
                if report.longrepr:
                    return report.longrepr

        return None

    def _mark_test_reports_as_retry(self, reports: _ReportGroup):
        if call_report := reports.get(TestPhase.CALL):
            call_report.user_properties += [("dd_retry_outcome", call_report.outcome)]
            call_report.outcome = "dd_retry"

        elif setup_report := reports.get(TestPhase.SETUP):
            setup_report.user_properties += [("dd_retry_outcome", setup_report.outcome)]
            setup_report.outcome = "dd_retry"

    def _log_test_report(self, item: pytest.Item, reports: _ReportGroup, when: str):
        if report := reports.get(when):
            item.ihook.pytest_runtest_logreport(report=report)
            return True

        return False

    def _log_test_reports(self, item: pytest.Item, reports: _ReportGroup):
        for when in (TestPhase.SETUP, TestPhase.CALL, TestPhase.TEARDOWN):
            if report := reports.get(when):
                item.ihook.pytest_runtest_logreport(report=report)

    def _make_final_report(self, item, final_status, longrepr):
        outcomes = {
            TestStatus.PASS: "passed",
            TestStatus.FAIL: "failed",
            TestStatus.SKIP: "skipped",
        }

        final_report = pytest.TestReport(
            nodeid=item.nodeid,
            location=item.location,
            keywords={k: 1 for k in item.keywords},
            when=TestPhase.CALL,
            longrepr=longrepr,
            outcome=outcomes.get(final_status, "???"),
        )

        return final_report

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo) -> None:
        """
        Save report and exception information for later use.
        """
        outcome = yield
        report: pytest.TestReport = outcome.get_result()
        self.reports_by_nodeid[item.nodeid][call.when] = report
        self.excinfo_by_report[report] = call.excinfo

    def pytest_report_teststatus(self, report: pytest.TestReport):
        if retry_outcome := _get_user_property(report, "dd_retry_outcome"):
            return ("dd_retry", "r", f"retry: {retry_outcome}")

    def _get_test_outcome(self, nodeid: str) -> t.Tuple[TestStatus, t.Dict[str, str]]:
        """
        Return test status and tags with exception/skip information for a given executed test.

        This methods consumes the test reports and exception information for the specified test, and removes them from
        the dictionaries.
        """
        reports_dict = self.reports_by_nodeid.pop(nodeid, None)

        for phase in (TestPhase.SETUP, TestPhase.CALL, TestPhase.TEARDOWN):
            report = reports_dict.get(phase)
            if not report:
                continue

            excinfo = self.excinfo_by_report.pop(report, None)
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


def _get_user_property(report: pytest.TestReport, user_property: str):
    for key, value in report.user_properties:
        if key == user_property:
            return value

    return None
