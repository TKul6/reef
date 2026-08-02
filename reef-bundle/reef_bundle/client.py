from __future__ import annotations

import io
import logging
import time

import requests

_log = logging.getLogger(__name__)


class ReefClientError(Exception):
    """Raised once a Reef request has exhausted every attempt."""


class ReefClient:
    """
    Thin HTTP wrapper over the Reef server's REST API.

    Every call goes through the same retry loop, so a Reef pod that is rolling out - or briefly
    unreachable - does not take the caller down with it. The wait between attempts grows linearly:
    `backoff_initial`, then `backoff_initial + backoff_increment`, and so on.

    :param base_url: Where Reef is listening, e.g. `http://reef:8080`.
    :param timeout: Seconds to wait on a single request before giving up on it.
    :param max_retries: How many attempts each request gets in total, first try included.
    :param backoff_initial: Seconds to wait before retrying for the first time.
    :param backoff_increment: Extra seconds added to that wait on every further retry.
    """

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_initial: float = 0.5,
        backoff_increment: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_initial = backoff_initial
        self.backoff_increment = backoff_increment

    def _send_with_retries(self, url: str, method: str) -> requests.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.request(method=method, url=url, timeout=self.timeout)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                last_exc = e
                if attempt < self.max_retries - 1:
                    wait = self.backoff_initial + self.backoff_increment * attempt
                    _log.warning(f"'{method} {url}' failed (attempt {attempt + 1}/{self.max_retries}); retrying in {wait}s.\n{e}")
                    time.sleep(wait)
                else:
                    _log.error(f"Giving up on '{method} {url}' after {self.max_retries} attempts.\n{e}")
        raise ReefClientError(f"Reef request to {url} failed after {self.max_retries} attempts: {last_exc}") from last_exc

    def _get(self, path: str) -> requests.Response:
        url = f"{self.base_url}{path}"
        return self._send_with_retries(url, "GET")

    def check_liveness(self) -> None:
        """Confirm Reef is answering. Raises `ReefClientError` when it is not."""
        self._get("/api/v1/health")

    def describe_bundle(self) -> dict:
        """Return the bundle metadata Reef reports: its version and its content signature."""
        return self._get("/api/v1/dags/metadata").json()

    def get_bundle_version(self) -> str:
        """Return just the version out of the bundle metadata."""
        metadata = self.describe_bundle()
        return metadata["version"]

    def download_bundle(self) -> io.BytesIO:
        """Pull the gzipped bundle archive down and hand it back as an in-memory buffer."""
        resp = self._get("/api/v1/dags/download")
        return io.BytesIO(resp.content)
