"""Tests for ddtestpy.internal.http module."""

from unittest.mock import Mock
from unittest.mock import patch

from ddtestpy.internal.http import DEFAULT_TIMEOUT_SECONDS
from ddtestpy.internal.http import BackendConnector
from ddtestpy.internal.http import FileAttachment


class TestBackendConnector:
    """Tests for BackendConnector class."""

    def test_constants(self) -> None:
        """Test module constants."""
        assert DEFAULT_TIMEOUT_SECONDS == 15.0

    @patch("http.client.HTTPSConnection")
    def test_init_default_parameters(self, mock_https_connection: Mock) -> None:
        """Test BackendConnector initialization with default parameters."""
        connector = BackendConnector(host="api.example.com")

        mock_https_connection.assert_called_once_with(host="api.example.com", port=443, timeout=DEFAULT_TIMEOUT_SECONDS)
        assert connector.default_headers == {"Accept-Encoding": "gzip"}

    @patch("http.client.HTTPSConnection")
    @patch("uuid.uuid4")
    def test_post_files_multiple_files(self, mock_uuid: Mock, mock_https_connection: Mock) -> None:
        """Test post_files method with multiple files."""
        # Setup mocks
        mock_uuid_obj = Mock()
        mock_uuid_obj.hex = "boundary123"
        mock_uuid.return_value = mock_uuid_obj

        mock_response = Mock()
        mock_response.headers = {}
        mock_response.read.return_value = b"upload success"

        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https_connection.return_value = mock_conn

        # Test post_files with multiple files
        connector = BackendConnector(host="api.example.com")
        files = [
            FileAttachment("file1", "doc1.txt", "text/plain", b"content1"),
            FileAttachment("file2", "doc2.json", "application/json", b"content2"),
        ]

        connector.post_files("/upload", files)

        # Verify both files are in the body
        call_args = mock_conn.request.call_args
        body = call_args[1]["body"]

        # Check for both files
        assert b'name="file1"' in body
        assert b'name="file2"' in body
        assert b"content1" in body
        assert b"content2" in body
        assert body.count(b"--boundary123") == 3  # 2 file separators + 1 end
