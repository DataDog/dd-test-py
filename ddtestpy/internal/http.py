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
from urllib.parse import ParseResult
from urllib.parse import urlparse
import uuid

from ddtestpy.internal.constants import DEFAULT_AGENT_HOSTNAME
from ddtestpy.internal.constants import DEFAULT_AGENT_PORT
from ddtestpy.internal.constants import DEFAULT_SITE
from ddtestpy.internal.errors import SetupError
from ddtestpy.internal.utils import asbool


DEFAULT_TIMEOUT_SECONDS = 15.0

log = logging.getLogger(__name__)


class BackendConnectorSetup:
    """
    Logic for detecting the backend connection mode (agentless or EVP) and creating new connectors.
    """

    @abstractmethod
    def get_connector_for_subdomain(self, subdomain: str) -> BackendConnector:
        """
        Return a backend connector for the given subdomain (e.g., api, citestcov-intake, citestcycle-intake).

        This method must be implemented for each backend connection mode subclass.
        """
        pass

    @classmethod
    def detect_setup(cls) -> BackendConnectorSetup:
        """
        Detect which backend connection mode to use and return a configured instance of the corresponding subclass.
        """
        if asbool(os.environ.get("DD_CIVISIBILITY_AGENTLESS_ENABLED")):
            log.info("Connecting to backend in agentless mode")
            return cls._detect_agentless_setup()

        else:
            log.info("Connecting to backend through agent in EVP proxy mode")
            return cls._detect_evp_proxy_setup()

    @classmethod
    def _detect_agentless_setup(cls) -> BackendConnectorSetup:
        """
        Detect settings for agentless backend connection mode.
        """
        site = os.environ.get("DD_SITE") or DEFAULT_SITE
        api_key = os.environ.get("DD_API_KEY")

        if not api_key:
            raise SetupError("DD_API_KEY environment variable is not set")

        return BackendConnectorAgentlessSetup(site=site, api_key=api_key)

    @classmethod
    def _detect_evp_proxy_setup(cls) -> BackendConnectorSetup:
        """
        Detect settings for EVP proxy mode backend connection mode.
        """
        agent_url = os.environ.get("DD_TRACE_AGENT_URL")
        if not agent_url:
            agent_host = (
                os.environ.get("DD_TRACE_AGENT_HOSTNAME") or os.environ.get("DD_AGENT_HOST") or DEFAULT_AGENT_HOSTNAME
            )
            agent_port = (
                os.environ.get("DD_TRACE_AGENT_PORT") or os.environ.get("DD_AGENT_PORT") or str(DEFAULT_AGENT_PORT)
            )
            agent_url = f"http://{agent_host}:{agent_port}"

        agent_url = agent_url.rstrip("/")  # Avoid an extra / when concatenating with the base path

        # Get info from agent to check if the agent is there, and which EVP proxy version it supports.
        try:
            connector = BackendConnector(agent_url)
            response, response_data = connector.get_json("/info")
            endpoints = response_data.get("endpoints", [])
            connector.close()
        except Exception as e:
            raise SetupError(f"Error connecting to Datadog agent at {agent_url}: {e}")

        if response.status != 200:
            raise SetupError(
                f"Error connecting to Datadog agent at {agent_url}: status {response.status}, "
                f"response {response_data!r}"
            )

        if "/evp_proxy/v4/" in endpoints:
            return BackendConnectorEVPProxySetup(url=f"{agent_url}/evp_proxy/v4", use_gzip=True)

        if "/evp_proxy/v2/" in endpoints:
            return BackendConnectorEVPProxySetup(url=f"{agent_url}/evp_proxy/v2", use_gzip=False)

        raise SetupError(f"Datadog agent at {agent_url} does not support EVP proxy mode")


class BackendConnectorAgentlessSetup(BackendConnectorSetup):
    def __init__(self, site: str, api_key: str) -> None:
        self.site = site
        self.api_key = api_key

    def get_connector_for_subdomain(self, subdomain: str) -> BackendConnector:
        return BackendConnector(
            url=f"https://{subdomain}.{self.site}",
            default_headers={"dd-api-key": self.api_key},
            use_gzip=True,
        )


class BackendConnectorEVPProxySetup(BackendConnectorSetup):
    def __init__(self, url: str, use_gzip: bool) -> None:
        self.url = url
        self.use_gzip = use_gzip

    def get_connector_for_subdomain(self, subdomain: str) -> BackendConnector:
        return BackendConnector(
            url=self.url,
            default_headers={"X-Datadog-EVP-Subdomain": subdomain},
            use_gzip=self.use_gzip,
        )


class BackendConnector(threading.local):
    def __init__(
        self,
        url: str,
        default_headers: t.Optional[t.Dict[str, str]] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        use_gzip: bool = False,
    ):
        parsed_url = urlparse(url)
        self.conn = self._make_connection(parsed_url, timeout_seconds)
        self.default_headers = default_headers or {}
        self.base_path = parsed_url.path.rstrip("/")
        self.use_gzip = use_gzip
        if self.use_gzip:
            self.default_headers["Accept-Encoding"] = "gzip"

    def close(self) -> None:
        self.conn.close()

    def _make_connection(self, parsed_url: ParseResult, timeout_seconds: float) -> http.client.HTTPConnection:
        if parsed_url.scheme == "http":
            if not parsed_url.hostname:
                raise SetupError(f"No hostname provided in {parsed_url.geturl()}")

            return http.client.HTTPConnection(
                host=parsed_url.hostname, port=parsed_url.port or 80, timeout=timeout_seconds
            )

        if parsed_url.scheme == "https":
            if not parsed_url.hostname:
                raise SetupError(f"No hostname provided in {parsed_url.geturl()}")

            return http.client.HTTPSConnection(
                host=parsed_url.hostname, port=parsed_url.port or 443, timeout=timeout_seconds
            )

        # TODO: Unix domain socket support.

        raise SetupError(f"Unknown scheme {parsed_url.scheme} in {parsed_url.geturl()}")

    # TODO: handle retries
    def request(
        self,
        method: str,
        path: str,
        data: t.Optional[bytes] = None,
        headers: t.Optional[t.Dict[str, str]] = None,
        send_gzip: bool = False,
    ) -> t.Tuple[http.client.HTTPResponse, bytes]:
        full_headers = self.default_headers | (headers or {})

        if send_gzip and self.use_gzip and data is not None:
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

    def get_json(self, path: str, headers: t.Optional[t.Dict[str, str]] = None, send_gzip: bool = False) -> t.Any:
        headers = {"Content-Type": "application/json"} | (headers or {})
        response, response_data = self.request("GET", path=path, headers=headers, send_gzip=send_gzip)
        return response, json.loads(response_data)

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
