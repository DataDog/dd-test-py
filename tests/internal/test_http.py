"""Tests for ddtestopt.internal.http module."""

import gzip
import json
from unittest.mock import Mock, patch, MagicMock
import pytest
from ddtestopt.internal.http import BackendConnector, FileAttachment, DEFAULT_TIMEOUT_SECONDS


class TestFileAttachment:
    """Tests for FileAttachment dataclass."""

    def test_file_attachment_creation(self):
        """Test FileAttachment creation with all fields."""
        attachment = FileAttachment(
            name="file1",
            filename="test.txt",
            content_type="text/plain",
            data=b"test content"
        )
        
        assert attachment.name == "file1"
        assert attachment.filename == "test.txt"
        assert attachment.content_type == "text/plain"
        assert attachment.data == b"test content"

    def test_file_attachment_optional_filename(self):
        """Test FileAttachment with None filename."""
        attachment = FileAttachment(
            name="field1",
            filename=None,
            content_type="application/octet-stream",
            data=b"binary data"
        )
        
        assert attachment.name == "field1"
        assert attachment.filename is None
        assert attachment.content_type == "application/octet-stream"
        assert attachment.data == b"binary data"


class TestBackendConnector:
    """Tests for BackendConnector class."""

    def test_constants(self):
        """Test module constants."""
        assert DEFAULT_TIMEOUT_SECONDS == 15.0

    @patch('http.client.HTTPSConnection')
    def test_init_default_parameters(self, mock_https_connection):
        """Test BackendConnector initialization with default parameters."""
        connector = BackendConnector(host="api.example.com")
        
        mock_https_connection.assert_called_once_with(
            host="api.example.com", 
            port=443, 
            timeout=DEFAULT_TIMEOUT_SECONDS
        )
        assert connector.default_headers == {"Accept-Encoding": "gzip"}

    @patch('http.client.HTTPSConnection')
    def test_init_custom_parameters(self, mock_https_connection):
        """Test BackendConnector initialization with custom parameters."""
        custom_headers = {"Authorization": "Bearer token"}
        connector = BackendConnector(
            host="custom.example.com",
            port=8080,
            default_headers=custom_headers,
            timeout_seconds=30.0,
            accept_gzip=False
        )
        
        mock_https_connection.assert_called_once_with(
            host="custom.example.com",
            port=8080,
            timeout=30.0
        )
        assert connector.default_headers == {"Authorization": "Bearer token"}

    @patch('http.client.HTTPSConnection')
    def test_init_with_gzip_enabled(self, mock_https_connection):
        """Test BackendConnector initialization with gzip enabled and custom headers."""
        custom_headers = {"User-Agent": "test"}
        connector = BackendConnector(
            host="api.example.com",
            default_headers=custom_headers,
            accept_gzip=True
        )
        
        expected_headers = {
            "User-Agent": "test",
            "Accept-Encoding": "gzip"
        }
        assert connector.default_headers == expected_headers

    @patch('http.client.HTTPSConnection')
    @patch('time.time')
    @patch('ddtestopt.internal.http.log')
    def test_request_success(self, mock_log, mock_time, mock_https_connection):
        """Test successful request without gzip."""
        # Setup mocks
        mock_time.side_effect = [1000.0, 1001.5]  # start_time, end_time
        
        mock_response = Mock()
        mock_response.headers = {}
        mock_response.read.return_value = b"response data"
        
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https_connection.return_value = mock_conn
        
        # Test request
        connector = BackendConnector(host="api.example.com")
        response, response_data = connector.request("GET", "/test", data=None)
        
        # Verify calls
        mock_conn.request.assert_called_once_with(
            "GET", "/test", 
            body=None, 
            headers={"Accept-Encoding": "gzip"}
        )
        assert response == mock_response
        assert response_data == b"response data"
        mock_log.debug.assert_called_once_with(
            "Request to %s %s took %.3f seconds", "GET", "/test", 1.5
        )

    @patch('http.client.HTTPSConnection')
    @patch('time.time')
    @patch('gzip.compress')
    def test_request_with_gzip_compression(self, mock_gzip_compress, mock_time, mock_https_connection):
        """Test request with gzip compression enabled."""
        # Setup mocks
        mock_time.side_effect = [1000.0, 1000.5]
        mock_gzip_compress.return_value = b"compressed data"
        
        mock_response = Mock()
        mock_response.headers = {}
        mock_response.read.return_value = b"response"
        
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https_connection.return_value = mock_conn
        
        # Test request
        connector = BackendConnector(host="api.example.com")
        connector.request("POST", "/test", data=b"test data", send_gzip=True)
        
        # Verify compression was applied
        mock_gzip_compress.assert_called_once_with(b"test data", compresslevel=6)
        mock_conn.request.assert_called_once_with(
            "POST", "/test",
            body=b"compressed data",
            headers={
                "Accept-Encoding": "gzip",
                "Content-Encoding": "gzip"
            }
        )

    @patch('http.client.HTTPSConnection')
    @patch('gzip.open')
    def test_request_with_gzip_response(self, mock_gzip_open, mock_https_connection):
        """Test request handling gzip response."""
        # Setup mocks
        mock_gzip_file = Mock()
        mock_gzip_file.read.return_value = b"decompressed response"
        mock_gzip_open.return_value = mock_gzip_file
        
        mock_response = Mock()
        mock_response.headers = {"Content-Encoding": "gzip"}
        
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https_connection.return_value = mock_conn
        
        # Test request
        connector = BackendConnector(host="api.example.com")
        response, response_data = connector.request("GET", "/test", data=None)
        
        # Verify gzip decompression
        mock_gzip_open.assert_called_once_with(mock_response)
        assert response_data == b"decompressed response"

    @patch('http.client.HTTPSConnection')
    def test_request_with_custom_headers(self, mock_https_connection):
        """Test request with custom headers."""
        mock_response = Mock()
        mock_response.headers = {}
        mock_response.read.return_value = b"response"
        
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https_connection.return_value = mock_conn
        
        # Test request with custom headers
        connector = BackendConnector(host="api.example.com")
        custom_headers = {"Authorization": "Bearer token", "Custom-Header": "value"}
        connector.request("GET", "/test", data=None, headers=custom_headers)
        
        # Verify headers are merged
        expected_headers = {
            "Accept-Encoding": "gzip",
            "Authorization": "Bearer token",
            "Custom-Header": "value"
        }
        mock_conn.request.assert_called_once_with(
            "GET", "/test", body=None, headers=expected_headers
        )

    @patch('http.client.HTTPSConnection')
    @patch('json.dumps')
    @patch('json.loads')
    def test_post_json_success(self, mock_json_loads, mock_json_dumps, mock_https_connection):
        """Test post_json method."""
        # Setup mocks
        mock_json_dumps.return_value = '{"key": "value"}'
        mock_json_loads.return_value = {"result": "success"}
        
        mock_response = Mock()
        mock_response.headers = {}
        mock_response.read.return_value = b'{"result": "success"}'
        
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https_connection.return_value = mock_conn
        
        # Test post_json
        connector = BackendConnector(host="api.example.com")
        data = {"key": "value"}
        response, response_data = connector.post_json("/api/test", data)
        
        # Verify calls
        mock_json_dumps.assert_called_once_with(data)
        mock_conn.request.assert_called_once_with(
            "POST", "/api/test",
            body=b'{"key": "value"}',
            headers={
                "Accept-Encoding": "gzip",
                "Content-Type": "application/json"
            }
        )
        mock_json_loads.assert_called_once_with(b'{"result": "success"}')
        assert response_data == {"result": "success"}

    @patch('http.client.HTTPSConnection')
    @patch('uuid.uuid4')
    def test_post_files_single_file(self, mock_uuid, mock_https_connection):
        """Test post_files method with single file."""
        # Setup mocks
        mock_uuid_obj = Mock()
        mock_uuid_obj.hex = "abcd1234"
        mock_uuid.return_value = mock_uuid_obj
        
        mock_response = Mock()
        mock_response.headers = {}
        mock_response.read.return_value = b"upload success"
        
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https_connection.return_value = mock_conn
        
        # Test post_files
        connector = BackendConnector(host="api.example.com")
        files = [FileAttachment(
            name="file1",
            filename="test.txt",
            content_type="text/plain",
            data=b"file content"
        )]
        
        response, response_data = connector.post_files("/upload", files)
        
        # Verify multipart form data construction
        call_args = mock_conn.request.call_args
        method, path = call_args[0]
        kwargs = call_args[1]
        
        assert method == "POST"
        assert path == "/upload"
        assert "Content-Type" in kwargs["headers"]
        assert "multipart/form-data; boundary=abcd1234" in kwargs["headers"]["Content-Type"]
        
        body = kwargs["body"]
        assert b"--abcd1234" in body
        assert b'Content-Disposition: form-data; name="file1"' in body
        assert b'filename="test.txt"' in body
        assert b"Content-Type: text/plain" in body
        assert b"file content" in body
        assert b"--abcd1234--" in body

    @patch('http.client.HTTPSConnection')
    @patch('uuid.uuid4')
    def test_post_files_no_filename(self, mock_uuid, mock_https_connection):
        """Test post_files method with file without filename."""
        # Setup mocks
        mock_uuid_obj = Mock()
        mock_uuid_obj.hex = "xyz789"
        mock_uuid.return_value = mock_uuid_obj
        
        mock_response = Mock()
        mock_response.headers = {}
        mock_response.read.return_value = b"upload success"
        
        mock_conn = Mock()
        mock_conn.getresponse.return_value = mock_response
        mock_https_connection.return_value = mock_conn
        
        # Test post_files with no filename
        connector = BackendConnector(host="api.example.com")
        files = [FileAttachment(
            name="data",
            filename=None,
            content_type="application/json",
            data=b'{"key": "value"}'
        )]
        
        connector.post_files("/upload", files)
        
        # Verify no filename in multipart data
        call_args = mock_conn.request.call_args
        body = call_args[1]["body"]
        assert b'Content-Disposition: form-data; name="data"' in body
        assert b"filename=" not in body  # Should not contain filename when None

    @patch('http.client.HTTPSConnection')
    @patch('uuid.uuid4')
    def test_post_files_multiple_files(self, mock_uuid, mock_https_connection):
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
            FileAttachment("file2", "doc2.json", "application/json", b"content2")
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