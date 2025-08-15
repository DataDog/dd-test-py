from abc import ABC
from abc import abstractmethod
from collections import defaultdict
import typing as t

from ddtestopt.internal.test_data import Test
from ddtestopt.internal.test_data import TestRun
from ddtestopt.internal.test_data import TestStatus


if t.TYPE_CHECKING:
    from ddtestopt.internal.session_manager import SessionManager


class RetryHandler(ABC):
    def __init__(self, session_manager: "SessionManager") -> None:
        self.session_manager = session_manager

    @abstractmethod
    def should_apply(self, test: Test) -> bool:
        """
        Return whether this retry policy should be applied to the given test.

        This is called before any test runs have happened, and should consider test properties (such as whether it's
        new), as well as per-session retry limits.

        For each test, the test plugin will try each retry handler in the session's retry handlers list, and use the
        first one for which `should_apply()` returns True. The `should_apply()` check can assume that the retry feature
        is enabled for the current session (otherwise the retry handler would not be in the session's retry handlers
        list).
        """

    @abstractmethod
    def should_retry(self, test: Test) -> bool:
        """
        Return whether one more test run should be performed for the given test.

        This should consider the status of previous runs, as well as number of attempts and per-session retry limits.
        """

    @abstractmethod
    def get_final_status(self, test: Test) -> TestStatus:
        """
        Return the final status to assign to the test, based on the status of all retries.
        """

    @abstractmethod
    def get_tags_for_test_run(self, test_run: TestRun) -> t.Dict[str, str]:
        """
        Return the tags to be added to a given retry test run.
        """


class AutoTestRetriesHandler(RetryHandler):
    def should_apply(self, test: Test) -> bool:
        return (
            False
            # test.last_test_run.get_status() == TestStatus.FAIL
            # and not test.is_new()
        )

    def should_retry(self, test: Test):
        return test.last_test_run.get_status() == TestStatus.FAIL and len(test.test_runs) < 6

    def get_final_status(self, test: Test):
        return test.last_test_run.get_status()

    def get_tags_for_test_run(self, test_run: TestRun) -> t.Dict[str, str]:
        if test_run.attempt_number == 0:
            return {}

        return {
            "test.is_retry": "true",
            "test.retry_reason": "auto_test_retry",
        }


class EarlyFlakeDetectionHandler(RetryHandler):
    def should_apply(self, test: Test) -> bool:
        return (
            True
            # and test.is_new()
        )

    def should_retry(self, test: Test):
        return (
            # test.last_test_run.get_status() != TestStatus.SKIP and
            len(test.test_runs)
            < 6  # should be based on total time and shenanigans
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
