import atexit
import logging
import os
import re
import typing as t

from ddtestopt.internal.api_client import APIClient
from ddtestopt.internal.api_client import TestProperties
from ddtestopt.internal.constants import DEFAULT_ENV_NAME
from ddtestopt.internal.constants import DEFAULT_SERVICE_NAME
from ddtestopt.internal.constants import DEFAULT_SITE
from ddtestopt.internal.git import Git
from ddtestopt.internal.git import GitTag
from ddtestopt.internal.git import get_git_tags
from ddtestopt.internal.platform import get_platform_tags
from ddtestopt.internal.retry_handlers import AttemptToFixHandler
from ddtestopt.internal.retry_handlers import AutoTestRetriesHandler
from ddtestopt.internal.retry_handlers import EarlyFlakeDetectionHandler
from ddtestopt.internal.retry_handlers import RetryHandler
from ddtestopt.internal.test_data import SuiteRef
from ddtestopt.internal.test_data import Test
from ddtestopt.internal.test_data import TestModule
from ddtestopt.internal.test_data import TestRef
from ddtestopt.internal.test_data import TestSession
from ddtestopt.internal.test_data import TestSuite
from ddtestopt.internal.test_data import TestTag
from ddtestopt.internal.utils import asbool
from ddtestopt.internal.writer import TestCoverageWriter
from ddtestopt.internal.writer import TestOptWriter


log = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, writer: t.Optional[TestOptWriter] = None, session: t.Optional[TestSession] = None) -> None:
        self.git_tags = get_git_tags()
        self.platform_tags = get_platform_tags()
        self.collected_tests: t.Set[TestRef] = set()
        self.skippable_items: t.Set[t.Union[SuiteRef, TestRef]] = set()
        self.itr_correlation_id: t.Optional[str] = None

        self.is_user_provided_service: bool

        dd_service = os.environ.get("DD_SERVICE")
        if dd_service:
            self.is_user_provided_service = True
            self.service = dd_service
        else:
            self.is_user_provided_service = False
            self.service = _get_service_name_from_git_repo(self.git_tags) or DEFAULT_SERVICE_NAME

        self.env = os.environ.get("DD_ENV") or DEFAULT_ENV_NAME
        self.site = os.environ.get("DD_SITE") or DEFAULT_SITE
        self.api_key = os.environ.get("DD_API_KEY")

        if not self.api_key:
            raise RuntimeError("DD_API_KEY environment variable is not set")

        self.api_client = APIClient(
            site=self.site,
            api_key=self.api_key,
            service=self.service,
            env=self.env,
            git_tags=self.git_tags,
            configurations=self.platform_tags,
        )
        self.settings = self.api_client.get_settings()
        self.known_tests = self.api_client.get_known_tests() if self.settings.known_tests_enabled else set()
        self.test_properties = (
            self.api_client.get_test_management_properties() if self.settings.test_management.enabled else {}
        )
        self.upload_git_data_and_get_skippable_tests()  # ꙮ

        # TODO: close connection after fetching stuff

        # Retry handlers must be set up after collection phase for EFD faulty session logic to work.
        self.retry_handlers: t.List[RetryHandler] = []

        self.writer = writer or TestOptWriter(site=self.site, api_key=self.api_key)
        self.coverage_writer = TestCoverageWriter(site=self.site, api_key=self.api_key)
        self.session = session or TestSession(name="test")
        self.session.set_service(self.service)

        self.writer.add_metadata("*", self.git_tags)
        self.writer.add_metadata("*", self.platform_tags)
        self.writer.add_metadata(
            "*",
            {
                TestTag.TEST_COMMAND: self.session.test_command,
                TestTag.TEST_FRAMEWORK: self.session.test_framework,
                TestTag.TEST_FRAMEWORK_VERSION: self.session.test_framework_version,
                TestTag.COMPONENT: self.session.test_framework,
                TestTag.ENV: self.env,
            },
        )

        if self.itr_correlation_id:
            self.writer.add_metadata("test", {"itr_correlation_id": self.itr_correlation_id})

    def finish_collection(self):
        self.setup_retry_handlers()

    def setup_retry_handlers(self):
        if self.settings.test_management.enabled:
            self.retry_handlers.append(AttemptToFixHandler(self))

        if self.settings.early_flake_detection.enabled:
            if self.known_tests:
                # TODO: handle parametrized tests specially. Currently each parametrized version is counted as a
                # separate test.
                new_tests = self.collected_tests - self.known_tests
                total_tests = len(new_tests) + len(self.known_tests)
                new_tests_percentage = len(new_tests) / total_tests * 100
                is_faulty_session = (
                    len(self.known_tests) > self.settings.early_flake_detection.faulty_session_threshold
                    and new_tests_percentage > self.settings.early_flake_detection.faulty_session_threshold
                )
                if is_faulty_session:
                    log.info("Not enabling Early Flake Detection: too many new tests")
                else:
                    self.retry_handlers.append(EarlyFlakeDetectionHandler(self))
            else:
                log.info("Not enabling Early Flake Detection: no known tests")

        if self.settings.auto_test_retries.enabled and asbool(os.getenv("DD_CIVISIBILITY_FLAKY_RETRY_ENABLED", "true")):
            self.retry_handlers.append(AutoTestRetriesHandler(self))

    def start(self) -> None:
        self.writer.start()
        self.coverage_writer.start()
        atexit.register(self.finish)

    def finish(self) -> None:
        atexit.unregister(self.finish)
        self.writer.finish()
        self.coverage_writer.finish()

    def discover_test(
        self,
        test_ref: TestRef,
        on_new_module: t.Callable[[TestModule], None],
        on_new_suite: t.Callable[[TestSuite], None],
        on_new_test: t.Callable[[Test], None],
    ) -> t.Tuple[TestModule, TestSuite, Test]:
        """
        Return the module, suite and test objects for a given test reference, creating them if necessary.

        When a new module, suite or test is discovered, the corresponding `on_new_*` callback is invoked. This can be
        used to perform test framework specific initialization (such as setting pathnames from data colleced by the
        framework).
        """
        test_module, created = self.session.get_or_create_child(test_ref.suite.module.name)
        if created:
            try:
                on_new_module(test_module)
            except:
                log.exception("Error during discovery of module %s", test_module)

        test_suite, created = test_module.get_or_create_child(test_ref.suite.name)
        if created:
            try:
                on_new_suite(test_suite)
            except:
                log.exception("Error during discovery of suite %s", test_suite)

        test, created = test_suite.get_or_create_child(test_ref.name)
        if created:
            try:
                self.collected_tests.add(test_ref)
                is_new = len(self.known_tests) > 0 and test_ref not in self.known_tests
                test_properties = self.test_properties.get(test_ref) or TestProperties()
                test.set_attributes(
                    is_new=is_new,
                    is_quarantined=test_properties.quarantined,
                    is_disabled=test_properties.disabled,
                    is_attempt_to_fix=test_properties.attempt_to_fix,
                )
                on_new_test(test)
            except:
                log.exception("Error during discovery of test %s", test)

        return test_module, test_suite, test

    def upload_git_data_and_get_skippable_tests(self):
        git = Git()
        latest_commits = git.get_latest_commits()
        backend_commits = self.api_client.get_known_commits(latest_commits)
        commits_not_in_backend = list(set(latest_commits) - set(backend_commits))

        revisions_to_send = git.get_filtered_revisions(
            excluded_commits=backend_commits, included_commits=commits_not_in_backend
        )

        for packfile in git.pack_objects(revisions_to_send):
            self.api_client.send_git_pack_file(packfile)

        self.skippable_items, self.itr_correlation_id = self.api_client.get_skippable_tests()


def _get_service_name_from_git_repo(git_tags: t.Dict[str, str]) -> t.Optional[str]:
    repo_name = git_tags.get(GitTag.REPOSITORY_URL)
    if repo_name and (m := re.match(r".*/([^/]+)(?:.git)/?", repo_name)):
        return m.group(1).lower()
    else:
        return None
