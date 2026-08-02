from __future__ import annotations

import os
from logging import getLogger
from pathlib import Path

from airflow.dag_processing.bundles.base import BaseDagBundle
from airflow.exceptions import AirflowException

from .client import ReefClient
from .helper import ReefBundleHelper


class ReefDagBundle(BaseDagBundle):
    """
    DAG bundle that takes its DAG files from a Reef server.

    Reef hands out a content signature alongside the bundle version. This bundle keeps track of the
    signature it last extracted; on every `refresh()` it asks Reef for the current one and only
    re-downloads when the two differ. A rollout of new DAGs therefore costs one small request per
    refresh interval, and Airflow is never restarted for it.

    :param reef_url: Where Reef is listening, e.g. `http://reef:8080`. Falls back to the `REEF_URL`
        environment variable when omitted.
    :param timeout: Seconds to wait on a single request to Reef.
    :param max_retries: How many attempts each request gets in total, first try included.
    :param backoff_initial: Seconds to wait before retrying for the first time.
    :param backoff_increment: Extra seconds added to that wait on every further retry.
    """

    supports_versioning = True

    def __init__(
        self,
        *,
        reef_url: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_initial: float = 5,
        backoff_increment: float = 5,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        resolved_url = (reef_url or os.getenv("REEF_URL", "")).rstrip("/")
        if not resolved_url:
            raise AirflowException("reef_url must be provided, or set through the REEF_URL environment variable")
        self.reef_url = resolved_url
        client = ReefClient(
            base_url=self.reef_url,
            timeout=timeout,
            max_retries=max_retries,
            backoff_initial=backoff_initial,
            backoff_increment=backoff_increment,
        )
        self._helper = ReefBundleHelper(
            client=client,
            bundle_dir=self.base_dir,
            logger=getLogger(__name__),
        )

    # ------------------------------------------------------------------
    # BaseDagBundle interface
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        with self.lock():
            self._helper.ensure_bundle_dir()
            self._helper.check_liveness()

        self.refresh()

        super().initialize()

    def get_current_version(self) -> str | None:
        return self._helper.resolve_version(self.version)

    def refresh(self) -> None:
        """Catch the local bundle up with Reef. Only meaningful for an unpinned bundle."""
        with self.lock():
            self._helper.sync(self.reef_url)

    @property
    def path(self) -> Path:
        return self._helper.bundle_dir

    def __repr__(self) -> str:
        return f"<ReefDagBundle(name={self.name!r}, version={self.version!r}, current_signature={self._helper.current_signature!r})>"
