"""Configuration for tests."""

import os
import subprocess
import typing as t

import pytest


# Enable pytester plugin for testing pytest plugins
pytest_plugins = ["pytester"]


@pytest.fixture(scope="session", autouse=True)
def set_env() -> None:
    """
    Make sure that we don't send inner tests to Datadog.
    """
    os.environ["DD_API_KEY"] = "test-key"


@pytest.fixture
def git_repo_empty(tmpdir: t.Any) -> str:
    """Create temporary empty git directory, meaning no commits/users/repository-url to extract (error)."""
    cwd = str(tmpdir)
    version = subprocess.check_output("git version", shell=True)
    # decode "git version 2.28.0" to (2, 28, 0)
    decoded_version = tuple(int(n) for n in version.decode().strip().split(" ")[-1].split(".") if n.isdigit())
    if decoded_version >= (2, 28):
        # versions starting from 2.28 can have a different initial branch name
        # configured in ~/.gitconfig
        subprocess.check_output("git init --initial-branch=master", cwd=cwd, shell=True)
    else:
        # versions prior to 2.28 will create a master branch by default
        subprocess.check_output("git init", cwd=cwd, shell=True)
    return cwd


@pytest.fixture
def git_repo(git_repo_empty: str) -> str:
    """Create temporary git directory, with one added file commit with a unique author and committer."""
    cwd = git_repo_empty
    subprocess.check_output('git remote add origin "git@github.com:test-repo-url.git"', cwd=cwd, shell=True)
    # Set temporary git directory to not require gpg commit signing
    subprocess.check_output("git config --local commit.gpgsign false", cwd=cwd, shell=True)
    # Set committer user to be "Jane Doe"
    subprocess.check_output('git config --local user.name "Jane Doe"', cwd=cwd, shell=True)
    subprocess.check_output('git config --local user.email "jane@doe.com"', cwd=cwd, shell=True)
    subprocess.check_output("touch tmp.py", cwd=cwd, shell=True)
    subprocess.check_output("git add tmp.py", cwd=cwd, shell=True)
    # Override author to be "John Doe"
    subprocess.check_output(
        'GIT_COMMITTER_DATE="2021-01-20T04:37:21-0400" git commit --date="2021-01-19T09:24:53-0400" '
        '-m "this is a commit msg" --author="John Doe <john@doe.com>" --no-edit',
        cwd=cwd,
        shell=True,
    )
    return cwd
