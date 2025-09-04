import json
import typing as t
import http.client
import time
import logging
import threading

log = logging.getLogger(__name__)


class BackendConnector:
    def __init__(self, host: str, port: int = 443, default_headers: t.Optional[t.Dict[str, str]] = None):
        self.local = threading.local()
        self.local.conn = http.client.HTTPSConnection(host, port)
        self.default_headers = default_headers or {}

    # def request(method: str, path: str, data: t.Any, headers: t.Optional[t.Dict[str, str]] = None):
    #     headers = self.default_headers + (headers or {})
    #     self.conn.request(method, path, body=data, headers)
    #     response = self.get_response()
    #     response_data = response.read()
    #     return response_data

    def post_json(self, path: str, data: t.Any, headers: t.Optional[t.Dict[str, str]] = None) -> t.Any:
        conn = self.local.conn
        all_headers = {
            **self.default_headers,
            "content-type": "application/json",
            **(headers or {}),
        }
        encoded_data = json.dumps(data).encode("utf-8")

        start_time = time.time()
        conn.request("POST", path, body=encoded_data, headers=all_headers)
        elapsed_time = time.time() - start_time
        log.debug("Request to %s took %.3f seconds", path, elapsed_time)

        response = conn.getresponse()
        response_data = json.loads(response.read())
        return response, response_data

        # if response.headers.get("Content-Encoding") == "gzip":
        #     response_data = json.load(gzip.open(response))
        # else:
        #     response_data = json.load(response)
