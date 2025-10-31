from collections import Counter
import json
import os
from pathlib import Path
import typing as t
from unittest import mock

import pytest

from ddtestpy.internal.ci import CITag
from ddtestpy.internal.env_tags import get_env_tags
from ddtestpy.internal.git import Git
from ddtestpy.internal.git import GitTag
from ddtestpy.internal.utils import _filter_sensitive_info


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "ci"


def _ci_fixtures() -> t.Iterable[t.Tuple[str, int, t.Dict[str, str], t.Dict[str, str]]]:
    for filepath in FIXTURES_DIR.glob("*.json"):
        with open(filepath) as fp:
            for i, [env_vars, expected_tags] in enumerate(json.load(fp)):
                yield filepath.stem, i, env_vars, expected_tags


@pytest.mark.parametrize("name,i,environment,tags", _ci_fixtures())
def test_ci_providers(
    monkeypatch: pytest.MonkeyPatch, name: str, i: int, environment: t.Dict[str, str], tags: t.Dict[str, str]
) -> None:
    """Make sure all provided environment variables from each CI provider are tagged correctly."""
    monkeypatch.setattr(os, "environ", environment)

    extracted_tags = get_env_tags()
    for key, value in tags.items():
        if key == CITag.NODE_LABELS:
            assert Counter(json.loads(extracted_tags[key])) == Counter(json.loads(value))
        elif key == CITag._CI_ENV_VARS:
            assert json.loads(extracted_tags[key]) == json.loads(value)
        else:
            assert extracted_tags[key] == value, "wrong tags in {0} for {1}".format(name, environment)


def test_git_extract_user_info(monkeypatch: pytest.MonkeyPatch, git_repo: str) -> None:
    """Make sure that git commit author/committer name, email, and date are extracted and tagged correctly."""
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.chdir(git_repo)

    tags = get_env_tags()

    assert tags[GitTag.COMMIT_AUTHOR_NAME] == "John Doe"
    assert tags[GitTag.COMMIT_AUTHOR_EMAIL] == "john@doe.com"
    assert tags[GitTag.COMMIT_AUTHOR_DATE] == "2021-01-19T09:24:53-0400"
    assert tags[GitTag.COMMIT_COMMITTER_NAME] == "Jane Doe"
    assert tags[GitTag.COMMIT_COMMITTER_EMAIL] == "jane@doe.com"
    assert tags[GitTag.COMMIT_COMMITTER_DATE] == "2021-01-20T04:37:21-0400"


def test_git_extract_user_info_with_commas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "environ", {})

    with mock.patch.object(
        Git,
        "_git_output",
        return_value="Do, Jo|||jo@do.com|||2021-01-19T09:24:53-0400|||Do, Ja|||ja@do.com|||2021-01-20T04:37:21-0400",
    ):
        tags = get_env_tags()

    assert tags[GitTag.COMMIT_AUTHOR_NAME] == "Do, Jo"
    assert tags[GitTag.COMMIT_AUTHOR_EMAIL] == "jo@do.com"
    assert tags[GitTag.COMMIT_AUTHOR_DATE] == "2021-01-19T09:24:53-0400"
    assert tags[GitTag.COMMIT_COMMITTER_NAME] == "Do, Ja"
    assert tags[GitTag.COMMIT_COMMITTER_EMAIL] == "ja@do.com"
    assert tags[GitTag.COMMIT_COMMITTER_DATE] == "2021-01-20T04:37:21-0400"


def test_git_extract_user_info_error(monkeypatch: pytest.MonkeyPatch, git_repo_empty: str) -> None:
    """When git data is not available, return no tags."""
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.chdir(git_repo_empty)

    tags = get_env_tags()
    assert tags == {}


def test_git_extract_repository_url(monkeypatch: pytest.MonkeyPatch, git_repo: str) -> None:
    """Make sure that the git repository url is extracted properly."""
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.chdir(git_repo)

    expected_repository_url = "git@github.com:test-repo-url.git"
    tags = get_env_tags()

    assert tags[GitTag.REPOSITORY_URL] == expected_repository_url


def test_git_filter_repository_url_valid() -> None:
    """Make sure that git repository urls without sensitive data are not filtered."""
    valid_url_1 = "https://github.com/DataDog/dd-trace-py.git"
    valid_url_2 = "git@github.com:DataDog/dd-trace-py.git"
    valid_url_3 = "ssh://github.com/Datadog/dd-trace-py.git"

    assert _filter_sensitive_info(valid_url_1) == valid_url_1
    assert _filter_sensitive_info(valid_url_2) == valid_url_2
    assert _filter_sensitive_info(valid_url_3) == valid_url_3


def test_git_filter_repository_url_invalid() -> None:
    """Make sure that git repository urls with sensitive data are not filtered."""
    """Make sure that valid git repository urls are not filtered."""

    invalid_url_1 = "https://username:password@github.com/DataDog/dd-trace-py.git"
    invalid_url_2 = "https://username@github.com/DataDog/dd-trace-py.git"

    invalid_url_3 = "ssh://username:password@github.com/DataDog/dd-trace-py.git"
    invalid_url_4 = "ssh://username@github.com/DataDog/dd-trace-py.git"

    assert _filter_sensitive_info(invalid_url_1) == "https://github.com/DataDog/dd-trace-py.git"
    assert _filter_sensitive_info(invalid_url_2) == "https://github.com/DataDog/dd-trace-py.git"

    assert _filter_sensitive_info(invalid_url_3) == "ssh://github.com/DataDog/dd-trace-py.git"
    assert _filter_sensitive_info(invalid_url_4) == "ssh://github.com/DataDog/dd-trace-py.git"
