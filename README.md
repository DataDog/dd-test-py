# Datadog Test Optimization for Python

<img align="right" src="https://user-images.githubusercontent.com/6321485/167082083-53f6e48f-1843-4708-9b98-587c94f7ddb3.png" alt="bits python" width="200px"/>

Datadog's Python Library for instrumenting your tests.

## Features

- [Test Optimization](https://docs.datadoghq.com/tests/) - collect metrics and results for your tests
- [Flaky Test Management](https://docs.datadoghq.com/tests/flaky_management/) - track, triage, and remediate flaky tests across your organization. Quarantine or disable problematic tests to keep known flakes from breaking builds, and create cases and Jira issues to track work toward fixes.
- [Auto Test Retries](https://docs.datadoghq.com/tests/flaky_tests/auto_test_retries/?tab=python) - retrying failing tests up to N times to avoid failing your build due to flaky tests
- [Early Flake Detection](https://docs.datadoghq.com/tests/flaky_tests/early_flake_detection/?tab=python) - Datadog’s test flakiness solution that identifies flakes early by running newly added tests multiple times
- [Test Impact Analysis](https://docs.datadoghq.com/tests/test_impact_analysis/) - save time by selectively running only tests affected by code changes
- [Test Health](https://docs.datadoghq.com/tests/test_health) - The Test Health dashboard provides analytics to help teams manage and optimize their testing in CI. This includes sections showing the current impact of test flakiness and how Test Optimization is mitigating these problems.
- [Inspect your tests' logs in Datadog](https://docs.datadoghq.com/tests/correlate_logs_and_tests)
- [Enhance developer workflows](https://docs.datadoghq.com/tests/developer_workflows)
- [Add custom measures to your tests](https://docs.datadoghq.com/tests/guides/add_custom_measures/?tab=python)
- [Browser tests integration with Datadog RUM](https://docs.datadoghq.com/tests/browser_tests)

## Setup

- [Test Optimization setup](https://docs.datadoghq.com/tests/setup/python/?tab=cloudciprovideragentless)
- [Test Impact Analysis setup](https://docs.datadoghq.com/tests/test_impact_analysis/setup/python/?tab=cloudciprovideragentless) (Test Optimization setup is required before setting up Test Impact Analysis)

## Upgrade from ddtrace

If you used [Test Optimization for Python](https://docs.datadoghq.com/tests/setup/python/) with [ddtrace](https://github.com/datadog/dd-trace-py), check out our [upgrade guide](/docs/UpgradeGuide.md).

## Contributing

See our [contributing guidelines](/CONTRIBUTING.md).

## Code of Conduct

Everyone interacting in the `dd-test-py` project's codebases, issue trackers, chat rooms and mailing lists is expected to follow the [code of conduct](/CODE_OF_CONDUCT.md).
