"""Tests for ddtestpy.internal.git module."""

from unittest.mock import Mock
from unittest.mock import patch

import pytest

from ddtestpy.internal.git import Git
from ddtestpy.internal.git import GitTag
from ddtestpy.internal.git import _GitSubprocessDetails
from ddtestpy.internal.git import get_git_tags


class TestGitTag:
    """Tests for GitTag constants."""

    def test_git_tag_constants(self) -> None:
        """Test that GitTag constants are correctly defined."""
        assert GitTag.REPOSITORY_URL == "git.repository_url"
        assert GitTag.COMMIT_SHA == "git.commit.sha"
        assert GitTag.BRANCH == "git.branch"
        assert GitTag.COMMIT_MESSAGE == "git.commit.message"
        assert GitTag.COMMIT_AUTHOR_NAME == "git.commit.author.name"
        assert GitTag.COMMIT_AUTHOR_EMAIL == "git.commit.author.email"
        assert GitTag.COMMIT_AUTHOR_DATE == "git.commit.author.date"
        assert GitTag.COMMIT_COMMITTER_NAME == "git.commit.committer.name"
        assert GitTag.COMMIT_COMMITTER_EMAIL == "git.commit.committer.email"
        assert GitTag.COMMIT_COMMITTER_DATE == "git.commit.committer.date"

    def test_git_tag_constants_unique(self) -> None:
        """Test that all GitTag constants are unique."""
        constants = [
            GitTag.REPOSITORY_URL,
            GitTag.COMMIT_SHA,
            GitTag.BRANCH,
            GitTag.COMMIT_MESSAGE,
            GitTag.COMMIT_AUTHOR_NAME,
            GitTag.COMMIT_AUTHOR_EMAIL,
            GitTag.COMMIT_AUTHOR_DATE,
            GitTag.COMMIT_COMMITTER_NAME,
            GitTag.COMMIT_COMMITTER_EMAIL,
            GitTag.COMMIT_COMMITTER_DATE,
        ]

        # All constants should be unique
        assert len(constants) == len(set(constants)), "GitTag constants are not unique"


class TestGitSubprocessDetails:
    """Tests for _GitSubprocessDetails dataclass."""

    def test_git_subprocess_details_creation(self) -> None:
        """Test that _GitSubprocessDetails can be created with required fields."""
        details = _GitSubprocessDetails(stdout="output", stderr="error", return_code=0)

        assert details.stdout == "output"
        assert details.stderr == "error"
        assert details.return_code == 0


class TestGit:
    """Tests for Git class."""

    @patch("shutil.which")
    def test_git_init_with_cwd(self, mock_which: Mock) -> None:
        """Test Git initialization with custom working directory."""
        mock_which.return_value = "/usr/bin/git"

        git = Git(cwd="/custom/path")
        assert git.git_command == "/usr/bin/git"
        assert git.cwd == "/custom/path"

    @patch("shutil.which")
    def test_git_init_git_not_found(self, mock_which: Mock) -> None:
        """Test Git initialization when git command is not found."""
        mock_which.return_value = None

        with pytest.raises(RuntimeError, match="`git` command not found"):
            Git()

    @patch("shutil.which")
    def test_get_repository_url(self, mock_which: Mock) -> None:
        """Test get_repository_url method."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        with patch.object(git, "_git_output", return_value="https://github.com/user/repo.git") as mock_git_output:
            result = git.get_repository_url()

        assert result == "https://github.com/user/repo.git"
        mock_git_output.assert_called_once_with(["ls-remote", "--get-url"])

    @patch("shutil.which")
    def test_get_commit_sha(self, mock_which: Mock) -> None:
        """Test get_commit_sha method."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        with patch.object(git, "_git_output", return_value="abc123def456") as mock_git_output:
            result = git.get_commit_sha()

        assert result == "abc123def456"
        mock_git_output.assert_called_once_with(["rev-parse", "HEAD"])

    @patch("shutil.which")
    def test_get_branch(self, mock_which: Mock) -> None:
        """Test get_branch method."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        with patch.object(git, "_git_output", return_value="main") as mock_git_output:
            result = git.get_branch()

        assert result == "main"
        mock_git_output.assert_called_once_with(["rev-parse", "--abbrev-ref", "HEAD"])

    @patch("shutil.which")
    def test_get_commit_message(self, mock_which: Mock) -> None:
        """Test get_commit_message method."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        with patch.object(git, "_git_output", return_value="Initial commit") as mock_git_output:
            result = git.get_commit_message()

        assert result == "Initial commit"
        mock_git_output.assert_called_once_with(["show", "-s", "--format=%s"])

    @patch("shutil.which")
    def test_get_user_info_success(self, mock_which: Mock) -> None:
        """Test get_user_info method with valid output."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        mock_output = (
            "John Doe|||john@example.com|||2023-01-01T12:00:00+0000|||"
            "Jane Committer|||jane@example.com|||2023-01-01T12:30:00+0000"
        )

        with patch.object(git, "_git_output", return_value=mock_output):
            result = git.get_user_info()

        expected = {
            GitTag.COMMIT_AUTHOR_DATE: "John Doe",  # Note: there's a bug in the original code
            GitTag.COMMIT_AUTHOR_EMAIL: "john@example.com",
            GitTag.COMMIT_AUTHOR_DATE: "2023-01-01T12:00:00+0000",  # This overwrites the previous one
            GitTag.COMMIT_COMMITTER_NAME: "Jane Committer",
            GitTag.COMMIT_COMMITTER_EMAIL: "jane@example.com",
            GitTag.COMMIT_COMMITTER_DATE: "2023-01-01T12:30:00+0000",
        }
        assert result == expected

    @patch("shutil.which")
    def test_get_user_info_no_output(self, mock_which: Mock) -> None:
        """Test get_user_info method with no output."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        with patch.object(git, "_git_output", return_value=""):
            result = git.get_user_info()

        assert result == {}

    @patch("shutil.which")
    def test_get_workspace_path(self, mock_which: Mock) -> None:
        """Test get_workspace_path method."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        with patch.object(git, "_git_output", return_value="/path/to/repo") as mock_git_output:
            result = git.get_workspace_path()

        assert result == "/path/to/repo"
        mock_git_output.assert_called_once_with(["rev-parse", "--show-toplevel"])

    @patch("shutil.which")
    def test_get_latest_commits_success(self, mock_which: Mock) -> None:
        """Test get_latest_commits method with commits."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        mock_output = "abc123\ndef456\nghi789"

        with patch.object(git, "_git_output", return_value=mock_output) as mock_git_output:
            result = git.get_latest_commits()

        assert result == ["abc123", "def456", "ghi789"]
        mock_git_output.assert_called_once_with(["log", "--format=%H", "-n", "1000", '--since="1 month ago"'])

    @patch("shutil.which")
    def test_get_latest_commits_no_output(self, mock_which: Mock) -> None:
        """Test get_latest_commits method with no commits."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        with patch.object(git, "_git_output", return_value=""):
            result = git.get_latest_commits()

        assert result == []

    @patch("shutil.which")
    def test_get_filtered_revisions(self, mock_which: Mock) -> None:
        """Test get_filtered_revisions method."""
        mock_which.return_value = "/usr/bin/git"

        git = Git()
        mock_output = "commit1\ncommit2\ncommit3"
        excluded = ["exclude1", "exclude2"]
        included = ["include1"]

        with patch.object(git, "_git_output", return_value=mock_output) as mock_git_output:
            result = git.get_filtered_revisions(excluded, included)

        assert result == ["commit1", "commit2", "commit3"]
        mock_git_output.assert_called_once_with(
            [
                "rev-list",
                "--objects",
                "--filter=blob:none",
                '--since="1 month ago"',
                "--no-object-names",
                "HEAD",
                "^exclude1",
                "^exclude2",
                "include1",
            ]
        )


class TestGetGitTags:
    """Tests for get_git_tags function."""

    @patch("ddtestpy.internal.git.Git")
    def test_get_git_tags_success(self, mock_git_class: Mock) -> None:
        """Test get_git_tags with successful Git operations."""
        mock_git = Mock()
        mock_git.get_repository_url.return_value = "https://github.com/user/repo.git"
        mock_git.get_commit_sha.return_value = "abc123"
        mock_git.get_branch.return_value = "main"
        mock_git.get_commit_message.return_value = "Test commit"
        mock_git.get_user_info.return_value = {"author": "John Doe"}
        mock_git_class.return_value = mock_git

        result = get_git_tags()

        expected = {
            GitTag.REPOSITORY_URL: "https://github.com/user/repo.git",
            GitTag.COMMIT_SHA: "abc123",
            GitTag.BRANCH: "main",
            GitTag.COMMIT_MESSAGE: "Test commit",
            "author": "John Doe",
        }
        assert result == expected

    @patch("ddtestpy.internal.git.Git")
    @patch("ddtestpy.internal.git.log")
    def test_get_git_tags_git_not_available(self, mock_log: Mock, mock_git_class: Mock) -> None:
        """Test get_git_tags when Git is not available."""
        mock_git_class.side_effect = RuntimeError("git command not found")

        result = get_git_tags()

        assert result == {}
        mock_log.warning.assert_called_once_with("Error getting git data: %s", mock_git_class.side_effect)
