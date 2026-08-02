from __future__ import annotations

import os
import shutil
import tarfile
from logging import Logger, getLogger
from pathlib import Path

from .client import ReefClient


class ReefBundleError(Exception):
    """Raised when the bundle cannot be brought into a usable state."""


class ReefBundleHelper:
    """
    Everything the Reef bundle does, minus the Airflow base class.

    Owns the local bundle directory, the archive extraction, and the signature bookkeeping that
    decides whether a download is needed at all. Airflow is deliberately absent from this file, so
    the whole flow can be exercised with a mock `ReefClient` and a `tmp_path` - no scheduler, no
    HTTP, no environment.

    :param client: Client used to talk to Reef.
    :param bundle_dir: Local directory the DAG files are extracted into.
    :param logger: Logger to write through; a module logger is used when none is given.
    """

    SIGNATURE_FILENAME = "dags_version.txt"

    def __init__(self, client: ReefClient, bundle_dir: Path, logger: Logger | None = None) -> None:
        self._client = client
        self._bundle_dir = bundle_dir
        self.current_signature: str | None = None
        self._log = logger or getLogger(__name__)

    def _recover_local_signature(self) -> str | None:
        """
        Pull back whatever signature `dags_version.txt` in the bundle directory carries.

        A worker may well start up against a bundle directory that some earlier extraction has
        already populated - over a shared volume, for instance - long before this helper holds a
        `current_signature` of its own. Whatever that extraction left behind reflects the code
        genuinely sitting on disk, so it beats assuming the directory is empty.

        None comes back when the file is absent, blank, or cannot be read.
        """
        signature_file = self._bundle_dir / self.SIGNATURE_FILENAME
        if not signature_file.is_file():
            self._log.debug(f"No signature file at {signature_file}")
            return None

        try:
            local_signature = signature_file.read_text().strip()
        except OSError as e:
            self._log.warning(f"Could not read the signature file {signature_file}: {e}")
            return None

        if not local_signature:
            self._log.debug(f"Signature file {signature_file} is empty")
            return None

        self._log.info(f"Recovered signature '{local_signature}' from {signature_file}")
        return local_signature

    @property
    def bundle_dir(self) -> Path:
        """The spot on disk the DAG files occupy."""
        return self._bundle_dir

    def ensure_bundle_dir(self) -> None:
        """Make the bundle directory if it is not there yet, and reject a path that is no directory at all."""
        if not self._bundle_dir.exists():
            os.makedirs(self._bundle_dir)
        if not self._bundle_dir.is_dir():
            raise ReefBundleError(f"Bundle path {self._bundle_dir} exists but is not a directory")

    def clear_bundle_dir(self) -> None:
        """Clear out everything inside the bundle directory while keeping the directory itself."""
        if self._bundle_dir.exists():
            for entry in self._bundle_dir.iterdir():
                if entry.is_file() or entry.is_symlink():
                    entry.unlink()
                elif entry.is_dir():
                    shutil.rmtree(entry)

    def extract_archive(self, buffer) -> None:
        """Expand the gzipped tar archive held in *buffer* out into the bundle directory."""
        try:
            with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
                tar.extractall(path=str(self._bundle_dir))
        except tarfile.TarError as e:
            raise ReefBundleError(f"Could not extract the bundle archive: {e}") from e

    def resolve_version(self, pinned_version: str | None) -> str | None:
        """
        Settle which version this bundle currently sits on.

        A pinned version takes precedence outright and spends no request - Airflow workers pin
        precisely so a task executes against the DAG code it was scheduled with instead of the
        newest available. Short of that the question goes to Reef, which yields None if it has no
        answer to give.
        """
        if pinned_version:
            return pinned_version
        try:
            return self._client.get_bundle_version()
        except Exception as e:
            self._log.error(f"Could not read the bundle version from Reef. {e}")
            return None

    def sync(self, reef_url: str) -> None:
        """
        Reconcile the local bundle directory with whatever Reef is handing out.

        `current_signature` is weighed against the remote signature. Where the two disagree, the
        signature on disk gets a look first, as it may turn out to be the right one already - see
        `_recover_local_signature`. A download follows only for a signature still stale after that,
        and the directory is wiped before the fresh archive is unpacked into it.

        :param reef_url: Good for nothing beyond naming the bundle's origin in the log lines.
        """
        metadata = self._client.describe_bundle()
        remote_signature = metadata.get("signature")

        if self.current_signature != remote_signature:
            self._log.debug(
                f"In-memory signature ({self.current_signature!r}) differs from the remote one "
                f"({remote_signature!r}); checking {self.SIGNATURE_FILENAME}"
            )
            local_signature = self._recover_local_signature()
            if local_signature is not None:
                self.current_signature = local_signature

        if self.current_signature == remote_signature:
            self._log.info(f"Bundle signature {remote_signature} is already current; skipping download")
            return

        self._log.info(f"Fetching bundle {remote_signature} from {reef_url}")
        buffer = self._client.download_bundle()
        self.clear_bundle_dir()
        self.extract_archive(buffer)
        self.current_signature = remote_signature

    def check_liveness(self) -> None:
        """Have the client verify that Reef is answering."""
        self._client.check_liveness()
