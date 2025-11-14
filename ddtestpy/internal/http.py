from __future__ import annotations

from dataclasses import dataclass
import gzip
import http.client
import io
import json
import logging
import threading
import time
import typing as t
import uuid


DEFAULT_TIMEOUT_SECONDS = 15.0

log = logging.getLogger(__name__)


@dataclass
class FileAttachment:
    name: str
    filename: t.Optional[str]
    content_type: str
    data: bytes


class BackendConnector(threading.local):
    def __init__(
        self,
        host: str,
        port: int = 443,
        http_class: t.type[http.client.HTTPSConnection] = http.client.HTTPSConnection,
        default_headers: t.Optional[t.Dict[str, str]] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        backend_supports_gzip_requests: bool = True,
        accept_gzip_responses: bool = True,
        base_path: str = "",
    ):
        self.conn = http_class(host=host, port=port, timeout=timeout_seconds)
        self.default_headers = default_headers or {}
        self.base_path = base_path
        self.backend_supports_gzip_requests = backend_supports_gzip_requests
        if accept_gzip_responses:
            self.default_headers["Accept-Encoding"] = "gzip"

    def close(self) -> None:
        self.conn.close()

    # TODO: handle retries
    def request(
        self,
        method: str,
        path: str,
        data: bytes,
        headers: t.Optional[t.Dict[str, str]] = None,
        send_gzip: bool = False,
    ) -> t.Tuple[http.client.HTTPResponse, bytes]:
        full_headers = self.default_headers | (headers or {})

        if send_gzip and self.backend_supports_gzip_requests:
            data = gzip.compress(data, compresslevel=6)
            full_headers["Content-Encoding"] = "gzip"

        start_time = time.time()

        self.conn.request(method, self.base_path + path, body=data, headers=full_headers)

        response = self.conn.getresponse()
        if response.headers.get("Content-Encoding") == "gzip":
            response_data = gzip.open(response).read()
        else:
            response_data = response.read()

        elapsed_time = time.time() - start_time

        log.debug("Request to %s %s took %.3f seconds", method, path, elapsed_time)
        # log.debug("Request headers %s, data %s", full_headers, data)
        # log.debug("Response status %s, data %s", response.status, response_data)

        return response, response_data

    def post_json(
        self, path: str, data: t.Any, headers: t.Optional[t.Dict[str, str]] = None, send_gzip: bool = False
    ) -> t.Any:
        headers = {"Content-Type": "application/json"} | (headers or {})
        encoded_data = json.dumps(data).encode("utf-8")
        response, response_data = self.request(
            "POST", path=path, data=encoded_data, headers=headers, send_gzip=send_gzip
        )
        return response, json.loads(response_data)

    def post_files(
        self,
        path: str,
        files: t.List[FileAttachment],
        headers: t.Optional[t.Dict[str, str]] = None,
        send_gzip: bool = False,
    ) -> t.Tuple[http.client.HTTPResponse, bytes]:
        boundary = uuid.uuid4().hex
        boundary_bytes = boundary.encode("utf-8")
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"} | (headers or {})
        body = io.BytesIO()

        for attachment in files:
            body.write(b"--%s\r\n" % boundary_bytes)
            body.write(b'Content-Disposition: form-data; name="%s"' % attachment.name.encode("utf-8"))
            if attachment.filename:
                body.write(b'; filename="%s"' % attachment.filename.encode("utf-8"))
            body.write(b"\r\n")
            body.write(b"Content-Type: %s\r\n" % attachment.content_type.encode("utf-8"))
            body.write(b"\r\n")
            body.write(attachment.data)
            body.write(b"\r\n")

        body.write(b"--%s--\r\n" % boundary_bytes)

        return self.request("POST", path=path, data=body.getvalue(), headers=headers, send_gzip=send_gzip)

    @classmethod
    def make_evp_proxy_connector(cls, host: str, port: int = 8126) -> BackendConnector:
        return cls(
            host=host,
            port=port,
            http_class=http.client.HTTPConnection,
            default_headers={"X-Datadog-EVP-Subdomain": "api"},
            backend_supports_gzip_requests=False,
            accept_gzip_responses=False,
            base_path="/evp_proxy/v4",
        )
