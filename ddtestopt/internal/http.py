import gzip
import http.client
import json
import logging
import threading
import time
import typing as t


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

    # TODO: handle retries
    def request(
        self,
        method: str,
        path: str,
        data: t.Optional[bytes],
        headers: t.Optional[t.Dict[str, str]] = None,
        send_gzip: bool = False,
    ) -> t.Any:
        full_headers = self.default_headers | (headers or {})

        if send_gzip:
            data = gzip.compress(data, compresslevel=6)
            full_headers["Content-Encoding"] = "gzip"

        start_time = time.time()
        self.conn.request(method, path, body=data, headers=full_headers)
        elapsed_time = time.time() - start_time
        log.debug("Request to %s %s took %.3f seconds", method, path, elapsed_time)

        response = self.conn.getresponse()
        if response.headers.get("Content-Encoding") == "gzip":
            response_data = gzip.open(response).read()
        else:
            response_data = response.read()

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
