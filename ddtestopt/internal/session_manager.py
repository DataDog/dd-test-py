import os
import typing as t

from ddtestopt.internal.git import get_git_tags
from ddtestopt.internal.platform import get_platform_tags
from ddtestopt.internal.retry_handlers import AutoTestRetriesHandler
from ddtestopt.internal.retry_handlers import EarlyFlakeDetectionHandler
from ddtestopt.internal.retry_handlers import RetryHandler
from ddtestopt.internal.test_data import TestSession
from ddtestopt.internal.test_data import TestTag
from ddtestopt.internal.writer import TestOptWriter


class SessionManager:
    def __init__(self, writer: t.Optional[TestOptWriter] = None, session: t.Optional[TestSession] = None) -> None:
        self.writer = writer or TestOptWriter()
        self.session = session or TestSession(name="test")

        self.retry_handlers: t.List[RetryHandler] = [EarlyFlakeDetectionHandler(self), AutoTestRetriesHandler(self)]

    def start(self) -> None:
        self.writer.add_metadata("*", get_git_tags())
        self.writer.add_metadata("*", get_platform_tags())
        self.writer.add_metadata(
            "*",
            {
                TestTag.TEST_COMMAND: self.session.test_command,
                TestTag.TEST_FRAMEWORK: self.session.test_framework,
                TestTag.TEST_FRAMEWORK_VERSION: self.session.test_framework_version,
                TestTag.COMPONENT: self.session.test_framework,
                TestTag.ENV: os.environ.get("DD_ENV", "none"),
            },
        )

    def finish(self) -> None:
        pass
