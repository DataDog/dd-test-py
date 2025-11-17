from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
import gzip
import http.client
import io
import json
import logging
import os
import threading
import time
import typing as t
import urllib.parse
import uuid

from ddtestpy.internal.constants import DEFAULT_SITE
from ddtestpy.internal.utils import asbool


DEFAULT_TIMEOUT_SECONDS = 15.0

log = logging.getLogger(__name__)


@dataclass
class FileAttachment:
    name: str
    filename: t.Optional[str]
    content_type: str
    data: bytes


class BackendConnectorSetup:
    @abstractmethod
    def get_connector_for_subdomain(self, subdomain: str) -> BackendConnector: ...

    @classmethod
    def detect_setup(cls) -> BackendConnectorSetup:
        if asbool(os.environ.get("DD_CIVISIBILITY_AGENTLESS_ENABLED")):
            log.debug("Connecting to backend in agentless mode")
            return cls._detect_agentless_setup()

        else:
            log.debug("Connecting to backend through agent in EVP proxy mode")
            return cls._detect_evp_proxy_setup()

    @classmethod
    def _detect_agentless_setup(cls) -> BackendConnectorSetup:
        site = os.environ.get("DD_SITE") or DEFAULT_SITE
        api_key = os.environ.get("DD_API_KEY")

        if not api_key:
            raise RuntimeError("DD_API_KEY environment variable is not set")

        return BackendConnectorAgentlessSetup(site=site, api_key=api_key)

    @classmethod
    def _detect_evp_proxy_setup(cls) -> BackendConnectorSetup:
        agent_url = os.environ.get("DD_TRACE_AGENT_URL")
        if not agent_url:
            agent_host = os.environ.get("DD_TRACE_AGENT_HOSTNAME") or os.environ.get("DD_AGENT_HOST") or "localhost"
            agent_port = os.environ.get("DD_TRACE_AGENT_PORT") or os.environ.get("DD_AGENT_PORT") or "8126"
            agent_url = f"http://{agent_host}:{agent_port}"

        try:
            url = urllib.parse.urlparse(agent_url)
            conn = http.client.HTTPConnection(host=url.hostname, port=url.port)
            conn.request("GET", "/info")
            response = conn.getresponse()
            response_body = response.read()
            response.close()
        except Exception as e:
            raise RuntimeError(f"Error connecting to Datadog agent at {agent_url}: {e}")

        if response.status != 200:
            raise RuntimeError(
                f"Error connecting to Datadog agent at {agent_url}: status {response.status}, "
                f"response {response_body!r}"
            )

        response_data = json.loads(response_body)
        endpoints = response_data.get("endpoints", [])

        if "/evp_proxy/v4/" in endpoints:
            return BackendConnectorEVPProxySetup(
                host=url.hostname, port=url.port, base_path="/evp_proxy/v4/", use_gzip=True
            )

        if "/evp_proxy/v2/" in endpoints:
            return BackendConnectorEVPProxySetup(
                host=url.hostname, port=url.port, base_path="/evp_proxy/v2/", use_gzip=False
            )

        raise RuntimeError(f"Datadog agent at {agent_url} does not support EVP proxy mode")


class BackendConnectorAgentlessSetup(BackendConnectorSetup):
    def __init__(self, site: str, api_key: str) -> None:
        self.site = site
        self.port = 443
        self.api_key = api_key

    def get_connector_for_subdomain(self, subdomain: str) -> BackendConnector:
        return BackendConnector(
            host=f"{subdomain}.{self.site}",
            port=self.port,
            http_class=http.client.HTTPSConnection,
            default_headers={"dd-api-key": self.api_key},
        )


class BackendConnectorEVPProxySetup(BackendConnectorSetup):
    def __init__(self, host: str, port: int, base_path: str, use_gzip: bool) -> None:
        self.host = host
        self.port = port
        self.base_path = base_path
        self.use_gzip = use_gzip

    def get_connector_for_subdomain(self, subdomain: str) -> BackendConnector:
        return BackendConnector(
            host=self.host,
            port=self.port,
            http_class=http.client.HTTPConnection,
            default_headers={"X-Datadog-EVP-Subdomain": subdomain},
            backend_supports_gzip_requests=self.use_gzip,
            accept_gzip_responses=self.use_gzip,
            base_path=self.base_path,
        )


class BackendConnector(threading.local):
    def __init__(
        self,
        host: str,
        port: int = 443,
        http_class: t.Type[http.client.HTTPConnection] = http.client.HTTPSConnection,
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
