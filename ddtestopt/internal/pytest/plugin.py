from collections import defaultdict
from io import StringIO
import logging
import os
from pathlib import Path
import re
import traceback
import typing as t

from _pytest.runner import runtestprotocol
import pluggy
import pytest

from ddtestopt.internal.ddtrace import install_global_trace_filter
from ddtestopt.internal.ddtrace import trace_context
from ddtestopt.internal.logging import catch_and_log_exceptions
from ddtestopt.internal.logging import setup_logging
from ddtestopt.internal.retry_handlers import RetryHandler
from ddtestopt.internal.session_manager import SessionManager
from ddtestopt.internal.test_data import ModuleRef
from ddtestopt.internal.test_data import SuiteRef
from ddtestopt.internal.test_data import Test
from ddtestopt.internal.test_data import TestModule
from ddtestopt.internal.test_data import TestRef
from ddtestopt.internal.test_data import TestRun
from ddtestopt.internal.test_data import TestSession
from ddtestopt.internal.test_data import TestStatus
from ddtestopt.internal.test_data import TestSuite
from ddtestopt.internal.test_data import TestTag
from ddtestopt.internal.utils import TestContext


_NODEID_REGEX = re.compile("^(((?P<module>.*)/)?(?P<suite>[^/]*?))::(?P<name>.*?)$")
DISABLED_BY_TEST_MANAGEMENT_REASON = "Flaky test is disabled by Datadog"

log = logging.getLogger(__name__)


# The tuple pytest expects as the `longrepr` field of reports for failed or skipped tests.
_Longrepr = t.Tuple[
    # 1st field: pathname of the test file
    str,
    # 2nd field: line number.
    int,
    # 3rd field: skip reason.
    str,
]


# The tuple pytest expects as the output of the `pytest_report_teststatus` hook.
_ReportTestStatus = t.Tuple[
    # 1st field: the status category in which the test will be counted in the final stats (X passed, Y failed, etc).
    # Usually this is the same as report.outcome, but does not have to be! For example if a report has report.outcome =
    # "skipped" but `pytest_report_teststatus` returns "quarantined" as the first tuple item here, the test will be
    # counted as "quarantined" in the final stats.
    str,
    # 2nd field: the short (single-character) representation of the test status (e.g., "F" for failed tests).
    str,
    # 3rd field: the long representation of the test status (e.g., "FAILED" for failed tests). It can be either:
    t.Union[
        # - a simple string; or
        str,
        # - a tuple (text, properties_dict), where the properties_dict can contain properties such as {"blue": True}.
        #   These properties are also applied to the short representation.
        t.Tuple[str, t.Dict[str, bool]],
    ],
]
# The `pytest_report_teststatus` hook can return a tuple of empty strings ("", "", ""), in which case the test report is
# not logged at all. On the other, if the hook returns `None`, the next hook will be tried (so you can return `None` if
# you want the default pytest log output).


def nodeid_to_test_ref(nodeid: str) -> TestRef:
    matches = _NODEID_REGEX.match(nodeid)

    if matches:
        module_ref = ModuleRef(matches.group("module") or ".")
        suite_ref = SuiteRef(module_ref, matches.group("suite") or ".")
        test_ref = TestRef(suite_ref, matches.group("name"))
        return test_ref

    else:
        # Fallback to considering the whole nodeid as the test name.
        module_ref = ModuleRef(".")
        suite_ref = SuiteRef(module_ref, ".")
        test_ref = TestRef(suite_ref, nodeid)
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
    """
    pytest plugin for test optimization.
    """

    def __init__(self) -> None:
        self.enable_ddtrace = True  # TODO: make it configurable via command line.
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
        self.manager.writer.put_item(self.session)
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

        def _on_new_module(module: TestModule) -> None:
            module.set_location(module_path=_get_module_path_from_item(item))

        def _on_new_suite(suite: TestSuite) -> None:
            pass

        def _on_new_test(test: Test) -> None:
            path, start_line, _test_name = item.reportinfo()
            test.set_location(path=path, start_line=start_line)

        return self.manager.discover_test(
            test_ref,
            on_new_module=_on_new_module,
            on_new_suite=_on_new_suite,
            on_new_test=_on_new_test,
        )

    @pytest.hookimpl(tryfirst=True, hookwrapper=True, specname="pytest_runtest_protocol")
    def pytest_runtest_protocol_wrapper(
        self, item: pytest.Item, nextitem: t.Optional[pytest.Item]
    ) -> t.Generator[None, None, None]:
        test_ref = nodeid_to_test_ref(item.nodeid)
        next_test_ref = nodeid_to_test_ref(nextitem.nodeid) if nextitem else None

        test_module, test_suite, test = self._discover_test(item, test_ref)
        self.tests_by_nodeid[item.nodeid] = test

        if test.is_disabled() and not test.is_attempt_to_fix():
            item.add_marker(pytest.mark.skip(reason=DISABLED_BY_TEST_MANAGEMENT_REASON))
        elif test.is_quarantined() or (test.is_disabled() and test.is_attempt_to_fix()):
            # A test that is disabled and attempt-to-fix will run, but a failure does not break the pipeline (i.e., it
            # is effectively quarantined). We may want to present it in a different way in the output though.
            item.user_properties += [("dd_quarantined", True)]

        with trace_context(self.enable_ddtrace) as context:
            yield

        if not test.test_runs:
            # No test runs: our pytest_runtest_protocol did not run. This can happen if some other plugin (such as
            # `flaky` or `rerunfailures`) did it instead, or if there is a user-defined `pytest_runtest_protocol` in
            # `conftest.py`. In this case, we create a test run now with the test results of the plugin run as a
            # fallback, but we are unable to do retries in this case.
            log.debug(
                "Test Optimization pytest_runtest_protocol did not run for %s; "
                "perhaps some plugin or conftest.py has overridden it",
                item.nodeid,
            )
            test_run = test.make_test_run()
            status, tags = self._get_test_outcome(item.nodeid)
            test_run.set_status(status)
            test_run.set_tags(tags)
            test_run.set_context(context)
            test_run.finish()
            self.manager.writer.put_item(test_run)

        test.finish()

        if not next_test_ref or test_ref.suite != next_test_ref.suite:
            test_suite.finish()
            self.manager.writer.put_item(test_suite)

        if not next_test_ref or test_ref.suite.module != next_test_ref.suite.module:
            test_module.finish()
            self.manager.writer.put_item(test_module)

    @catch_and_log_exceptions()
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: t.Optional[pytest.Item]) -> bool:
        self._do_test_runs(item, nextitem)
        return True  # Do not run other pytest_runtest_protocol hooks after this one.

    def _do_one_test_run(
        self, item: pytest.Item, nextitem: t.Optional[pytest.Item], context: TestContext
    ) -> t.Tuple[TestRun, _ReportGroup]:
        test = self.tests_by_nodeid[item.nodeid]
        test_run = test.make_test_run()
        reports = _make_reports_dict(runtestprotocol(item, nextitem=nextitem, log=False))
        status, tags = self._get_test_outcome(item.nodeid)
        test_run.set_status(status)
        test_run.set_tags(tags)
        test_run.set_context(context)

        return test_run, reports

    def _do_test_runs(self, item: pytest.Item, nextitem: t.Optional[pytest.Item]) -> None:
        test = self.tests_by_nodeid[item.nodeid]
        retry_handler = self._check_applicable_retry_handlers(test)

        with trace_context(self.enable_ddtrace) as context:
            test_run, reports = self._do_one_test_run(item, nextitem, context)

        if retry_handler and retry_handler.should_retry(test):
            self._do_retries(item, nextitem, test, retry_handler, reports)
        else:
            if test.is_quarantined() or test.is_disabled():
                self._mark_test_reports_as_quarantined(item, reports)
            self._log_test_reports(item, reports)
            test_run.finish()
            self.manager.writer.put_item(test_run)

    def _do_retries(self, item, nextitem, test, retry_handler, reports):
        # Save failure/skip representation to put into the final report.
        # TODO: for flaky tests, we currently don't show the longrepr (because the final report has `passed` status).
        longrepr = self._extract_longrepr(reports)

        # Log initial attempt.
        self._mark_test_reports_as_retry(reports, retry_handler)
        self._log_test_report(item, reports, TestPhase.SETUP)
        self._log_test_report(item, reports, TestPhase.CALL)

        test_run = test.last_test_run
        test_run.set_tags(retry_handler.get_tags_for_test_run(test_run))
        test_run.finish()
        self.manager.writer.put_item(test_run)

        should_retry = True

        while should_retry:
            with trace_context(self.enable_ddtrace) as context:
                test_run, reports = self._do_one_test_run(item, nextitem, context)

            should_retry = retry_handler.should_retry(test)
            test_run.set_tags(retry_handler.get_tags_for_test_run(test_run))
            self._mark_test_reports_as_retry(reports, retry_handler)

            if not self._log_test_report(item, reports, TestPhase.CALL):
                self._log_test_report(item, reports, TestPhase.SETUP)

            test_run.finish()

        final_status, final_tags = retry_handler.get_final_status(test)
        test.set_status(final_status)
        test_run.set_tags(final_tags)

        for test_run in test.test_runs:
            self.manager.writer.put_item(test_run)

        # Log final status.
        final_report = self._make_final_report(item, final_status, longrepr)
        if test.is_quarantined() or test.is_disabled():
            self._mark_test_report_as_quarantined(item, final_report)
        item.ihook.pytest_runtest_logreport(report=final_report)

        # Log teardown. There should be just one teardown logged for all of the retries, because the junitxml plugin
        # closes the <testcase> element when teardown is logged.
        teardown_report = reports.get(TestPhase.TEARDOWN)
        if test.is_quarantined() or test.is_disabled():
            self._mark_test_report_as_quarantined(item, teardown_report)
        item.ihook.pytest_runtest_logreport(report=teardown_report)

    def _check_applicable_retry_handlers(self, test: Test) -> t.Optional[RetryHandler]:
        for handler in self.manager.retry_handlers:
            if handler.should_apply(test):
                return handler

        return None

    def _extract_longrepr(self, reports: _ReportGroup) -> t.Any:
        # The call longrepr is more interesting for us, if available.
        for when in (TestPhase.CALL, TestPhase.SETUP, TestPhase.TEARDOWN):
            if report := reports.get(when):
                if report.longrepr:
                    return report.longrepr

        return None

    def _mark_test_reports_as_retry(self, reports: _ReportGroup, retry_handler: RetryHandler) -> None:
        if not self._mark_test_report_as_retry(reports, retry_handler, TestPhase.CALL):
            self._mark_test_report_as_retry(reports, retry_handler, TestPhase.SETUP)

    def _mark_test_report_as_quarantined(self, item: pytest.Item, report: pytest.TestReport) -> None:
        # For junitxml, probably the least confusing way to report a quarantined test is as skipped.
        # In `pytest_runtest_logreport`, we can still identify the test as quarantined via the `dd_quarantined`
        # user property.
        if report.when == TestPhase.TEARDOWN:
            report.outcome = "passed"
        else:
            # TODO: distinguish quarantine vs disabled
            longrepr: _Longrepr = (str(item.path), item.location[1], "Quarantined")
            report.longrepr = longrepr
            report.outcome = "skipped"

    def _mark_test_reports_as_quarantined(self, item: pytest.Item, reports: _ReportGroup) -> None:
        if call_report := reports.get(TestPhase.CALL):
            self._mark_test_report_as_quarantined(item, call_report)
            reports[TestPhase.SETUP].outcome = "passed"
            reports[TestPhase.TEARDOWN].outcome = "passed"
        else:
            setup_report = reports.get(TestPhase.SETUP)
            self._mark_test_report_as_quarantined(item, setup_report)
            reports[TestPhase.TEARDOWN].outcome = "passed"

    def _mark_test_report_as_retry(self, reports: _ReportGroup, retry_handler: RetryHandler, when: str) -> bool:
        if call_report := reports.get(when):
            call_report.user_properties += [
                ("dd_retry_outcome", call_report.outcome),
                ("dd_retry_reason", retry_handler.get_pretty_name()),
            ]
            call_report.outcome = "dd_retry"  # type: ignore
            return True

        return False

    def _log_test_report(self, item: pytest.Item, reports: _ReportGroup, when: str) -> bool:
        if report := reports.get(when):
            item.ihook.pytest_runtest_logreport(report=report)
            return True

        return False

    def _log_test_reports(self, item: pytest.Item, reports: _ReportGroup) -> None:
        for when in (TestPhase.SETUP, TestPhase.CALL, TestPhase.TEARDOWN):
            if report := reports.get(when):
                item.ihook.pytest_runtest_logreport(report=report)

    def _make_final_report(self, item: pytest.Item, final_status: TestStatus, longrepr: t.Any) -> pytest.TestReport:
        outcomes = {
            TestStatus.PASS: "passed",
            TestStatus.FAIL: "failed",
            TestStatus.SKIP: "skipped",
        }

        final_report = pytest.TestReport(
            nodeid=item.nodeid,
            location=item.location,
            keywords={k: 1 for k in item.keywords},
            when=TestPhase.CALL,  # type: ignore
            longrepr=longrepr,
            outcome=outcomes.get(final_status, str(final_status)),  # type: ignore
            user_properties=item.user_properties,
        )

        return final_report

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(
        self, item: pytest.Item, call: pytest.CallInfo
    ) -> t.Generator[None, pluggy.Result, None]:
        """
        Save report and exception information for later use.
        """
        outcome = yield
        report: pytest.TestReport = outcome.get_result()
        self.reports_by_nodeid[item.nodeid][call.when] = report
        self.excinfo_by_report[report] = call.excinfo

    def pytest_report_teststatus(self, report: pytest.TestReport) -> t.Optional[_ReportTestStatus]:
        if retry_outcome := _get_user_property(report, "dd_retry_outcome"):
            retry_reason = _get_user_property(report, "dd_retry_reason")
            return ("dd_retry", "R", f"RETRY {retry_outcome.upper()} ({retry_reason})")

        if _get_user_property(report, "dd_quarantined"):
            if report.when == TestPhase.TEARDOWN:
                return ("quarantined", "Q", ("QUARANTINED", {"blue": True}))
            else:
                return ("", "", "")

        return None

    def _get_test_outcome(self, nodeid: str) -> t.Tuple[TestStatus, t.Dict[str, str]]:
        """
        Return test status and tags with exception/skip information for a given executed test.

        This methods consumes the test reports and exception information for the specified test, and removes them from
        the dictionaries.
        """
        # TODO: handle xfail/xpass.
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


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_load_initial_conftests(
    early_config: pytest.Config, parser: pytest.Parser, args: t.List[str]
) -> t.Generator[None, None, None]:
    setup_logging()
    yield


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
    user_properties = getattr(report, "user_properties", [])  # pytest.CollectReport does not have `user_properties`.

    for key, value in user_properties:
        if key == user_property:
            return value

    return None
