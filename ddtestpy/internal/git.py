from dataclasses import dataclass
import logging
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import typing as t


log = logging.getLogger(__name__)


class GitTag:
    # Git Repository URL
    REPOSITORY_URL = "git.repository_url"

    # Git Commit SHA
    COMMIT_SHA = "git.commit.sha"

    # Git Branch
    BRANCH = "git.branch"

    # Git Commit Message
    COMMIT_MESSAGE = "git.commit.message"

    # Git Commit Author Name
    COMMIT_AUTHOR_NAME = "git.commit.author.name"

    # Git Commit Author Email
    COMMIT_AUTHOR_EMAIL = "git.commit.author.email"

    # Git Commit Author Date (UTC)
    COMMIT_AUTHOR_DATE = "git.commit.author.date"

    # Git Commit Committer Name
    COMMIT_COMMITTER_NAME = "git.commit.committer.name"

    # Git Commit Committer Email
    COMMIT_COMMITTER_EMAIL = "git.commit.committer.email"

    # Git Commit Committer Date (UTC)
    COMMIT_COMMITTER_DATE = "git.commit.committer.date"


@dataclass
class _GitSubprocessDetails:
    stdout: str
    stderr: str
    return_code: int


class Git:
    def __init__(self, cwd: t.Optional[str] = None):
        git_command = shutil.which("git")
        if not git_command:
            # Raise this at instantiation time, so that if an instance is successfully initialized, that means `git` is
            # available and we don't have to check for it every time.
            raise RuntimeError("`git` command not found")

        self.git_command: str = git_command
        self.cwd = cwd

    def _call_git(self, args: t.List[str], input_string: t.Optional[str] = None) -> _GitSubprocessDetails:
        git_cmd = [self.git_command, *args]

        process = subprocess.Popen(
            git_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            cwd=self.cwd,
            encoding="utf-8",
            errors="surrogateescape",
        )
        stdout, stderr = process.communicate(input=input_string)

        return _GitSubprocessDetails(stdout=stdout.strip(), stderr=stderr.strip(), return_code=process.returncode)

    def _git_output(self, args: t.List[str]) -> str:
        result = self._call_git(args)
        if result.return_code != 0:
            log.warning("Error calling git %s: %s", " ".join(args), result.stderr)
            return ""
        return result.stdout

    def get_repository_url(self) -> str:
        return self._git_output(["ls-remote", "--get-url"])

    def get_commit_sha(self) -> str:
        return self._git_output(["rev-parse", "HEAD"])

    def get_branch(self) -> str:
        return self._git_output(["rev-parse", "--abbrev-ref", "HEAD"])

    def get_commit_message(self) -> str:
        return self._git_output(["show", "-s", "--format=%s"])

    def get_user_info(self) -> t.Dict[str, str]:
        output = self._git_output(
            ["show", "-s", "--format=%an|||%ae|||%ad|||%cn|||%ce|||%cd", "--date=format:%Y-%m-%dT%H:%M:%S%z"]
        )
        if not output:
            return {}

        author_name, author_email, author_date, committer_name, committer_email, committer_date = output.split("|||")
        return {
            GitTag.COMMIT_AUTHOR_DATE: author_name,
            GitTag.COMMIT_AUTHOR_EMAIL: author_email,
            GitTag.COMMIT_AUTHOR_DATE: author_date,
            GitTag.COMMIT_COMMITTER_NAME: committer_name,
            GitTag.COMMIT_COMMITTER_EMAIL: committer_email,
            GitTag.COMMIT_COMMITTER_DATE: committer_date,
        }

    def get_workspace_path(self) -> str:
        return self._git_output(["rev-parse", "--show-toplevel"])

    def get_latest_commits(self) -> t.List[str]:
        output = self._git_output(["log", "--format=%H", "-n", "1000", '--since="1 month ago"'])
        return output.split("\n") if output else []

    def get_filtered_revisions(self, excluded_commits: t.List[str], included_commits: t.List[str]) -> t.List[str]:
        exclusions = [f"^{sha}" for sha in excluded_commits]
        output = self._git_output(
            [
                "rev-list",
                "--objects",
                "--filter=blob:none",
                '--since="1 month ago"',
                "--no-object-names",
                "HEAD",
                *exclusions,
                *included_commits,
            ]
        )
        return output.split("\n")

    def pack_objects(self, revisions: t.List[str]) -> t.Iterable[Path]:
        base_name = str(random.randint(1, 1000000))
        revisions_text = "\n".join(revisions)

        cwd = Path(self.cwd) if self.cwd is not None else Path.cwd()
        temp_dir_base = Path(tempfile.gettempdir())
        if cwd.stat().st_dev != temp_dir_base.stat().st_dev:
            # `git pack-objects` does not work properly when the target is in a different device.
            # In this case, we create the temporary directory in the current directory as a fallback.
            temp_dir_base = cwd

        with tempfile.TemporaryDirectory(dir=temp_dir_base) as output_dir:
            prefix = f"{output_dir}/{base_name}"
            result = self._call_git(["pack-objects", "--compression=9", "--max-pack-size=3m", prefix], revisions_text)
            if result.return_code != 0:
                log.warning("Error calling git pack-objects: %s", result.stderr)
                return None

            for packfile in Path(output_dir).glob(f"{base_name}*.pack"):
                yield packfile


def get_git_tags() -> t.Dict[str, str]:
    try:
        git = Git()
    except RuntimeError as e:
        log.warning("Error getting git data: %s", e)
        return {}

    tags = {}
    tags[GitTag.REPOSITORY_URL] = git.get_repository_url()
    tags[GitTag.COMMIT_SHA] = git.get_commit_sha()
    tags[GitTag.BRANCH] = git.get_branch()
    tags[GitTag.COMMIT_MESSAGE] = git.get_commit_message()
    tags.update(git.get_user_info())

    return tags


def get_workspace_path() -> Path:
    try:
        return Path(Git().get_workspace_path()).absolute()
    except RuntimeError:
        return Path.cwd()
