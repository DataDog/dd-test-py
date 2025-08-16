import logging
import os
import typing as t

from ddtestopt.internal.api_client import APIClient
from ddtestopt.internal.git import GitTag
from ddtestopt.internal.git import get_git_tags
from ddtestopt.internal.platform import get_platform_tags
from ddtestopt.internal.retry_handlers import AutoTestRetriesHandler
from ddtestopt.internal.retry_handlers import EarlyFlakeDetectionHandler
from ddtestopt.internal.retry_handlers import RetryHandler
from ddtestopt.internal.test_data import TestSession
from ddtestopt.internal.test_data import TestTag
from ddtestopt.internal.writer import TestOptWriter


log = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, writer: t.Optional[TestOptWriter] = None, session: t.Optional[TestSession] = None) -> None:
        self.git_tags = get_git_tags()
        self.platform_tags = get_platform_tags()
        self.service = os.environ.get("DD_SERVICE")
        self.env = os.environ.get("DD_ENV")
        self.site = os.environ.get("DD_SITE") or "datadoghq.com"
        self.api_key = os.environ["DD_API_KEY"]

        self.api_client = APIClient(
            site=self.site,
            api_key=self.api_key,
            service=self.service,
            env=self.env,
            repository_url=self.git_tags[GitTag.REPOSITORY_URL],
            commit_sha=self.git_tags[GitTag.COMMIT_SHA],
            branch=self.git_tags[GitTag.BRANCH],
            configurations=self.platform_tags,
        )
        self.settings = self.api_client.get_settings()

        # DEBUG
        self.settings.early_flake_detection.enabled = True
        self.settings.known_tests_enabled = True
        #######

        self.known_tests = self.api_client.get_known_tests() if self.settings.known_tests_enabled else set()

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
                TestTag.ENV: self.env or "none",
            },
        )

    def finish(self) -> None:
        pass
