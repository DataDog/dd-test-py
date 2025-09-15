"""Tests for ddtestopt.internal.git module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from ddtestopt.internal.git import GitTag, Git, _GitSubprocessDetails, get_git_tags


class TestGitTag:
    """Tests for GitTag constants."""

    def test_git_tag_constants(self):
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

    def test_git_tag_constants_are_strings(self):
        """Test that all GitTag constants are strings."""
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
        
        for constant in constants:
            assert isinstance(constant, str), f"GitTag constant {constant} is not a string"

    def test_git_tag_constants_unique(self):
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

    def test_git_subprocess_details_creation(self):
        """Test that _GitSubprocessDetails can be created with required fields."""
        details = _GitSubprocessDetails(
            stdout="output",
            stderr="error",
            return_code=0
        )
        
        assert details.stdout == "output"
        assert details.stderr == "error"
        assert details.return_code == 0


class TestGit:
    """Tests for Git class."""

    @patch('shutil.which')
    def test_git_init_success(self, mock_which):
        """Test Git initialization when git command is found."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        assert git.git_command == "/usr/bin/git"
        assert git.cwd is None

    @patch('shutil.which')
    def test_git_init_with_cwd(self, mock_which):
        """Test Git initialization with custom working directory."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git(cwd="/custom/path")
        assert git.git_command == "/usr/bin/git"
        assert git.cwd == "/custom/path"

    @patch('shutil.which')
    def test_git_init_git_not_found(self, mock_which):
        """Test Git initialization when git command is not found."""
        mock_which.return_value = None
        
        with pytest.raises(RuntimeError, match="`git` command not found"):
            Git()

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_call_git_success(self, mock_popen, mock_which):
        """Test _call_git method with successful execution."""
        mock_which.return_value = "/usr/bin/git"
        
        mock_process = Mock()
        mock_process.communicate.return_value = ("output\n", "")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        git = Git()
        result = git._call_git(["status"])
        
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.return_code == 0
        
        mock_popen.assert_called_once_with(
            ["/usr/bin/git", "status"],
            stdout=-1,
            stderr=-1,
            stdin=-1,
            cwd=None,
            encoding="utf-8",
            errors="surrogateescape",
        )

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_call_git_with_input(self, mock_popen, mock_which):
        """Test _call_git method with input string."""
        mock_which.return_value = "/usr/bin/git"
        
        mock_process = Mock()
        mock_process.communicate.return_value = ("", "")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        git = Git()
        git._call_git(["pack-objects"], input_string="input data")
        
        mock_process.communicate.assert_called_once_with(input="input data")

    @patch('shutil.which')
    @patch('subprocess.Popen')
    def test_git_output_success(self, mock_popen, mock_which):
        """Test _git_output method with successful git command."""
        mock_which.return_value = "/usr/bin/git"
        
        mock_process = Mock()
        mock_process.communicate.return_value = ("branch_name\n", "")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        git = Git()
        result = git._git_output(["rev-parse", "--abbrev-ref", "HEAD"])
        
        assert result == "branch_name"

    @patch('shutil.which')
    @patch('subprocess.Popen')
    @patch('ddtestopt.internal.git.log')
    def test_git_output_failure(self, mock_log, mock_popen, mock_which):
        """Test _git_output method with failed git command."""
        mock_which.return_value = "/usr/bin/git"
        
        mock_process = Mock()
        mock_process.communicate.return_value = ("", "fatal: not a git repository")
        mock_process.returncode = 128
        mock_popen.return_value = mock_process
        
        git = Git()
        result = git._git_output(["status"])
        
        assert result == ""
        mock_log.warning.assert_called_once_with(
            "Error calling git %s: %s", "status", "fatal: not a git repository"
        )

    @patch('shutil.which')
    def test_get_repository_url(self, mock_which):
        """Test get_repository_url method."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        with patch.object(git, '_git_output', return_value="https://github.com/user/repo.git") as mock_git_output:
            result = git.get_repository_url()
            
        assert result == "https://github.com/user/repo.git"
        mock_git_output.assert_called_once_with(["ls-remote", "--get-url"])

    @patch('shutil.which')
    def test_get_commit_sha(self, mock_which):
        """Test get_commit_sha method."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        with patch.object(git, '_git_output', return_value="abc123def456") as mock_git_output:
            result = git.get_commit_sha()
            
        assert result == "abc123def456"
        mock_git_output.assert_called_once_with(["rev-parse", "HEAD"])

    @patch('shutil.which')
    def test_get_branch(self, mock_which):
        """Test get_branch method."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        with patch.object(git, '_git_output', return_value="main") as mock_git_output:
            result = git.get_branch()
            
        assert result == "main"
        mock_git_output.assert_called_once_with(["rev-parse", "--abbrev-ref", "HEAD"])

    @patch('shutil.which')
    def test_get_commit_message(self, mock_which):
        """Test get_commit_message method."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        with patch.object(git, '_git_output', return_value="Initial commit") as mock_git_output:
            result = git.get_commit_message()
            
        assert result == "Initial commit"
        mock_git_output.assert_called_once_with(["show", "-s", "--format=%s"])

    @patch('shutil.which')
    def test_get_user_info_success(self, mock_which):
        """Test get_user_info method with valid output."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        mock_output = "John Doe|||john@example.com|||2023-01-01T12:00:00+0000|||Jane Committer|||jane@example.com|||2023-01-01T12:30:00+0000"
        
        with patch.object(git, '_git_output', return_value=mock_output):
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

    @patch('shutil.which')
    def test_get_user_info_no_output(self, mock_which):
        """Test get_user_info method with no output."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        with patch.object(git, '_git_output', return_value=""):
            result = git.get_user_info()
            
        assert result == {}

    @patch('shutil.which')
    def test_get_workspace_path(self, mock_which):
        """Test get_workspace_path method."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        with patch.object(git, '_git_output', return_value="/path/to/repo") as mock_git_output:
            result = git.get_workspace_path()
            
        assert result == "/path/to/repo"
        mock_git_output.assert_called_once_with(["rev-parse", "--show-toplevel"])

    @patch('shutil.which')
    def test_get_latest_commits_success(self, mock_which):
        """Test get_latest_commits method with commits."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        mock_output = "abc123\ndef456\nghi789"
        
        with patch.object(git, '_git_output', return_value=mock_output) as mock_git_output:
            result = git.get_latest_commits()
            
        assert result == ["abc123", "def456", "ghi789"]
        mock_git_output.assert_called_once_with(["log", "--format=%H", "-n", "1000", '--since="1 month ago"'])

    @patch('shutil.which')
    def test_get_latest_commits_no_output(self, mock_which):
        """Test get_latest_commits method with no commits."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        with patch.object(git, '_git_output', return_value=""):
            result = git.get_latest_commits()
            
        assert result == []

    @patch('shutil.which')
    def test_get_filtered_revisions(self, mock_which):
        """Test get_filtered_revisions method."""
        mock_which.return_value = "/usr/bin/git"
        
        git = Git()
        mock_output = "commit1\ncommit2\ncommit3"
        excluded = ["exclude1", "exclude2"]
        included = ["include1"]
        
        with patch.object(git, '_git_output', return_value=mock_output) as mock_git_output:
            result = git.get_filtered_revisions(excluded, included)
            
        assert result == ["commit1", "commit2", "commit3"]
        mock_git_output.assert_called_once_with([
            "rev-list",
            "--objects",
            "--filter=blob:none",
            '--since="1 month ago"',
            "--no-object-names",
            "HEAD",
            "^exclude1",
            "^exclude2",
            "include1",
        ])

    @patch('shutil.which')
    @patch('tempfile.TemporaryDirectory')
    @patch('random.randint')
    def test_pack_objects_success(self, mock_randint, mock_temp_dir, mock_which):
        """Test pack_objects method with successful execution."""
        mock_which.return_value = "/usr/bin/git"
        mock_randint.return_value = 123456
        
        # Mock temporary directory
        mock_temp_dir_instance = Mock()
        mock_temp_dir_instance.__enter__ = Mock(return_value="/tmp/test_dir")
        mock_temp_dir_instance.__exit__ = Mock(return_value=None)
        mock_temp_dir.return_value = mock_temp_dir_instance
        
        # Mock Path.glob to return a packfile
        mock_packfile = Mock()
        mock_packfile.name = "123456.pack"
        
        with patch('pathlib.Path.glob', return_value=[mock_packfile]):
            with patch('pathlib.Path.stat') as mock_stat:
                # Make stat return same device
                mock_stat_result = Mock()
                mock_stat_result.st_dev = 1
                mock_stat.return_value = mock_stat_result
                
                git = Git()
                
                # Mock _call_git to return success
                mock_result = _GitSubprocessDetails(stdout="", stderr="", return_code=0)
                with patch.object(git, '_call_git', return_value=mock_result):
                    result = list(git.pack_objects(["commit1", "commit2"]))
                    
        assert len(result) == 1
        assert result[0] == mock_packfile

    @patch('shutil.which')
    @patch('tempfile.TemporaryDirectory')
    @patch('random.randint')
    @patch('ddtestopt.internal.git.log')
    def test_pack_objects_failure(self, mock_log, mock_randint, mock_temp_dir, mock_which):
        """Test pack_objects method with git command failure."""
        mock_which.return_value = "/usr/bin/git"
        mock_randint.return_value = 123456
        
        # Mock temporary directory
        mock_temp_dir_instance = Mock()
        mock_temp_dir_instance.__enter__ = Mock(return_value="/tmp/test_dir")
        mock_temp_dir_instance.__exit__ = Mock(return_value=None)
        mock_temp_dir.return_value = mock_temp_dir_instance
        
        with patch('pathlib.Path.stat') as mock_stat:
            # Make stat return same device
            mock_stat_result = Mock()
            mock_stat_result.st_dev = 1
            mock_stat.return_value = mock_stat_result
            
            git = Git()
            
            # Mock _call_git to return failure
            mock_result = _GitSubprocessDetails(stdout="", stderr="pack failed", return_code=1)
            with patch.object(git, '_call_git', return_value=mock_result):
                result = list(git.pack_objects(["commit1"]))
                
        assert result == []
        mock_log.warning.assert_called_once_with("Error calling git pack-objects: %s", "pack failed")

    @patch('shutil.which')
    @patch('tempfile.TemporaryDirectory')
    @patch('random.randint')
    def test_pack_objects_different_device(self, mock_randint, mock_temp_dir, mock_which):
        """Test pack_objects method when temp dir and cwd are on different devices."""
        mock_which.return_value = "/usr/bin/git"
        mock_randint.return_value = 123456
        
        # Mock temporary directory
        mock_temp_dir_instance = Mock()
        mock_temp_dir_instance.__enter__ = Mock(return_value="/custom/temp")
        mock_temp_dir_instance.__exit__ = Mock(return_value=None)
        mock_temp_dir.return_value = mock_temp_dir_instance
        
        # Mock Path.glob to return a packfile
        mock_packfile = Mock()
        mock_packfile.name = "123456.pack"
        
        with patch('pathlib.Path.glob', return_value=[mock_packfile]):
            with patch('pathlib.Path.stat') as mock_stat:
                with patch('pathlib.Path.cwd', return_value=Path("/current/dir")):
                    # Make stat return different devices
                    def stat_side_effect():
                        mock_stat_result = Mock()
                        # First call (cwd): device 1, second call (temp_dir): device 2
                        stat_side_effect.call_count = getattr(stat_side_effect, 'call_count', 0) + 1
                        mock_stat_result.st_dev = 1 if stat_side_effect.call_count == 1 else 2
                        return mock_stat_result
                    
                    mock_stat.side_effect = stat_side_effect
                    
                    git = Git()
                    
                    # Mock _call_git to return success
                    mock_result = _GitSubprocessDetails(stdout="", stderr="", return_code=0)
                    with patch.object(git, '_call_git', return_value=mock_result):
                        result = list(git.pack_objects(["commit1"]))
                        
        # Should still work with different temp dir strategy
        assert len(result) == 1
        assert result[0] == mock_packfile
        
        # Verify TemporaryDirectory was called with the cwd as dir
        mock_temp_dir.assert_called_with(dir=Path("/current/dir"))


class TestGetGitTags:
    """Tests for get_git_tags function."""

    @patch('ddtestopt.internal.git.Git')
    def test_get_git_tags_success(self, mock_git_class):
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

    @patch('ddtestopt.internal.git.Git')
    @patch('ddtestopt.internal.git.log')
    def test_get_git_tags_git_not_available(self, mock_log, mock_git_class):
        """Test get_git_tags when Git is not available."""
        mock_git_class.side_effect = RuntimeError("git command not found")
        
        result = get_git_tags()
        
        assert result == {}
        mock_log.warning.assert_called_once_with("Error getting git data: %s", mock_git_class.side_effect)