from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import json
import logging
import typing as t
import urllib.request
import uuid

from ddtestopt.internal.test_data import ModuleRef
from ddtestopt.internal.test_data import SuiteRef
from ddtestopt.internal.test_data import TestRef


log = logging.getLogger(__name__)


class APIClient:
    def __init__(
        self,
        site: str,
        api_key: str,
        service: str,
        env: str,
        repository_url: str,
        commit_sha: str,
        branch: str,
        configurations: t.Dict[str, str],
    ) -> None:
        self.site = site
        self.api_key = api_key
        self.service = service
        self.env = env
        self.repository_url = repository_url
        self.commit_sha = commit_sha
        self.branch = branch
        self.configurations = configurations

        self.base_url = f"https://api.{self.site}"

    def get_settings(self) -> Settings:
        url = f"{self.base_url}/api/v2/libraries/tests/services/setting"
        request = urllib.request.Request(url)
        request.add_header("content-type", "application/json")
        request.add_header("dd-api-key", self.api_key)

        request_data = {
            "data": {
                "id": str(uuid.uuid4()),
                "type": "ci_app_test_service_libraries_settings",
                "attributes": {
                    "test_level": "suite",
                    "service": self.service,
                    "env": self.env,
                    "repository_url": self.repository_url,
                    "sha": self.commit_sha,
                    "branch": self.branch,
                    "configurations": self.configurations,
                },
            }
        }

        try:
            response = urllib.request.urlopen(request, json.dumps(request_data).encode("utf-8"))
            response_data = json.load(response)
            attributes = response_data["data"]["attributes"]
            return Settings.from_attributes(attributes)

        except Exception:
            log.exception("Error getting settings from API (%s)", url)
            return Settings()

    def get_known_tests(self) -> t.Set[TestRef]:
        url = f"{self.base_url}/api/v2/ci/libraries/tests"
        request = urllib.request.Request(url)
        request.add_header("content-type", "application/json")
        request.add_header("dd-api-key", self.api_key)
        request.add_header("Accept-Encoding", "gzip")

        request_data = {
            "data": {
                "id": str(uuid.uuid4()),
                "type": "ci_app_libraries_tests_request",
                "attributes": {
                    "service": self.service,
                    "env": self.env,
                    "repository_url": self.repository_url,
                    "configurations": self.configurations,
                },
            }
        }

        try:
            # response = urllib.request.urlopen(request, json.dumps(request_data).encode("utf-8"))
            # if response.headers.get("Content-Encoding") == "gzip":
            #     response_data = json.load(gzip.open(response))
            # else:
            #     response_data = json.load(response)
            response_data = json.load(
                open("/home/vitor.dearaujo/dd/test-optimization-python/tests/simple_known_tests_response.json")
            )  # DEBUG

            tests_data = response_data["data"]["attributes"]["tests"]
            known_test_ids = set()

            for module, suites in tests_data.items():
                module_ref = ModuleRef(module)
                for suite, tests in suites.items():
                    suite_ref = SuiteRef(module_ref, suite)
                    for test in tests:
                        known_test_ids.add(TestRef(suite_ref, test))

            return known_test_ids

        except Exception:
            log.exception("Error getting known tests from API (%s)", url)
            return set()


@dataclass
class EarlyFlakeDetectionSettings:
    enabled: bool = False
    slow_test_retries_5s: int = 10
    slow_test_retries_10s: int = 5
    slow_test_retries_30s: int = 3
    slow_test_retries_5m: int = 2
    faulty_session_threshold: int = 30

    @classmethod
    def from_attributes(cls, efd_attributes: t.Dict[str, t.Any]) -> EarlyFlakeDetectionSettings:
        efd_settings = cls(
            enabled=efd_attributes["enabled"],
            slow_test_retries_5s=efd_attributes["slow_test_retries"]["5s"],
            slow_test_retries_10s=efd_attributes["slow_test_retries"]["10s"],
            slow_test_retries_30s=efd_attributes["slow_test_retries"]["30s"],
            slow_test_retries_5m=efd_attributes["slow_test_retries"]["5m"],
            faulty_session_threshold=efd_attributes["faulty_session_threshold"],
        )
        return efd_settings


@dataclass
class AutoTestRetriesSettings:
    enabled: bool = False


@dataclass
class Settings:
    early_flake_detection: EarlyFlakeDetectionSettings = field(default_factory=EarlyFlakeDetectionSettings)
    auto_test_retries: AutoTestRetriesSettings = field(default_factory=AutoTestRetriesSettings)
    known_tests_enabled: bool = False

    @classmethod
    def from_attributes(cls, attributes) -> Settings:
        if efd_attributes := attributes.get("early_flake_detection"):
            efd_settings = EarlyFlakeDetectionSettings.from_attributes(efd_attributes)

        atr_enabled = bool(attributes.get("flaky_test_retries_enabled"))
        known_tests_enabled = bool(attributes.get("known_tests_enabled"))

        settings = cls(
            early_flake_detection=efd_settings,
            auto_test_retries=AutoTestRetriesSettings(enabled=atr_enabled),
            known_tests_enabled=known_tests_enabled,
        )

        return settings
