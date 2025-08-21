import logging
import os
import re
import typing as t

from ddtestopt.internal.api_client import APIClient
from ddtestopt.internal.api_client import TestProperties
from ddtestopt.internal.constants import DEFAULT_ENV_NAME
from ddtestopt.internal.constants import DEFAULT_SERVICE_NAME
from ddtestopt.internal.constants import DEFAULT_SITE
from ddtestopt.internal.git import GitTag
from ddtestopt.internal.git import get_git_tags
from ddtestopt.internal.platform import get_platform_tags
from ddtestopt.internal.retry_handlers import AutoTestRetriesHandler
from ddtestopt.internal.retry_handlers import EarlyFlakeDetectionHandler
from ddtestopt.internal.retry_handlers import RetryHandler
from ddtestopt.internal.test_data import Test
from ddtestopt.internal.test_data import TestModule
from ddtestopt.internal.test_data import TestRef
from ddtestopt.internal.test_data import TestSession
from ddtestopt.internal.test_data import TestSuite
from ddtestopt.internal.test_data import TestTag
from ddtestopt.internal.writer import TestOptWriter


log = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, writer: t.Optional[TestOptWriter] = None, session: t.Optional[TestSession] = None) -> None:
        self.git_tags = get_git_tags()
        self.platform_tags = get_platform_tags()

        self.is_user_provided_service: bool

        dd_service = os.environ.get("DD_SERVICE")
        if dd_service:
            self.service = dd_service
            self.is_user_provided_service = True
        else:
            self.is_user_provided_service = False
            self.service = _get_service_name_from_git_repo(self.git_tags) or DEFAULT_SERVICE_NAME

        self.env = os.environ.get("DD_ENV") or DEFAULT_ENV_NAME
        self.site = os.environ.get("DD_SITE") or DEFAULT_SITE
        self.api_key = os.environ["DD_API_KEY"]

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
            self.api_client.get_test_management_tests() if self.settings.test_management.enabled else {}
        )
        self.retry_handlers: t.List[RetryHandler] = []

        if self.settings.early_flake_detection.enabled:
            if self.known_tests:
                self.retry_handlers.append(EarlyFlakeDetectionHandler(self))
            else:
                log.info("No known tests, not enabling Early Flake Detection")

        if self.settings.auto_test_retries.enabled:
            self.retry_handlers.append(AutoTestRetriesHandler(self))

        self.writer = writer or TestOptWriter(site=self.site, api_key=self.api_key)
        self.session = session or TestSession(name="test")
        self.session.set_service(self.service)

    def start(self) -> None:
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

    def discover_test(
        self,
        test_ref: TestRef,
        on_new_module: t.Callable[[TestModule], None],
        on_new_suite: t.Callable[[TestSuite], None],
        on_new_test: t.Callable[[Test], None],
    ) -> t.Tuple[TestModule, TestSuite, Test]:
        """
        Return the module, suite and test objects for a given test reference, creating them if necessary.
        """
        test_module, created = self.session.get_or_create_child(test_ref.suite.module.name)
        if created:
            try:
                on_new_module(test_module)
            except:
                log.exception("Error during module discovery")

        test_suite, created = test_module.get_or_create_child(test_ref.suite.name)
        if created:
            try:
                on_new_suite(test_suite)
            except:
                log.exception("Error during suite discovery")

        test, created = test_suite.get_or_create_child(test_ref.name)
        if created:
            try:
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
                log.exception("Error during test discovery")

        return test_module, test_suite, test

    def finish(self) -> None:
        pass


def _get_service_name_from_git_repo(git_tags: t.Dict[str, str]) -> t.Optional[str]:
    repo_name = git_tags.get(GitTag.REPOSITORY_URL)
    if repo_name and (m := re.match(r".*/([^/]+)(?:.git)/?", repo_name)):
        return m.group(1).lower()
    else:
        return None
