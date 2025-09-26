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


class BackendConnector(threading.local):
    def __init__(
        self,
        host: str,
        port: int = 443,
        default_headers: t.Optional[t.Dict[str, str]] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        accept_gzip: bool = True,
    ):
        self.conn = http.client.HTTPSConnection(host=host, port=port, timeout=timeout_seconds)
        self.default_headers = default_headers or {}
        if accept_gzip:
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

        if send_gzip:
            data = gzip.compress(data, compresslevel=6)
            full_headers["Content-Encoding"] = "gzip"

        start_time = time.time()

        self.conn.request(method, path, body=data, headers=full_headers)

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


@dataclass
class FileAttachment:
    name: str
    filename: t.Optional[str]
    content_type: str
    data: bytes
