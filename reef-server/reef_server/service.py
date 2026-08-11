import hashlib
from logging import Logger
from pathlib import Path

from reef_server.constants import ARCHIVE_FILENAME, CHECKSUM_CHUNK_BYTES, SIGNATURE_FILENAME, SIGNATURE_HEX_LENGTH
from reef_server.errors import ReefServiceError


class ReefService:
    def __init__(self, bundle_dir: Path, bundle_version: str | None, server_version: str | None, logger: Logger) -> None:
        self._archive_path = bundle_dir / ARCHIVE_FILENAME
        self._signature_path = bundle_dir / SIGNATURE_FILENAME
        self._bundle_version = bundle_version
        self._server_version = server_version
        self._logger = logger
        self._signature: str | None = None

    def _checksum_archive(self) -> str:
        # Only reached when the image was built without a signature file. Hashing the archive
        # still yields a value that changes whenever the bundle contents change, so clients
        # keep working - it just costs a full read of the archive on the first request.
        self._logger.warning(f"No {SIGNATURE_FILENAME} found next to the bundle; hashing the archive instead. Rebuild the image to avoid this.")
        digest = hashlib.sha256()
        with open(self._archive_path, "rb") as archive:
            for chunk in iter(lambda: archive.read(CHECKSUM_CHUNK_BYTES), b""):
                digest.update(chunk)
        return digest.hexdigest()[:SIGNATURE_HEX_LENGTH]

    def _load_signature(self) -> str:
        if self._signature_path.is_file():
            self._logger.info(f"Reading the bundle signature from {self._signature_path}")
            return self._signature_path.read_text().strip()
        return self._checksum_archive()

    def _require_bundle_version(self) -> str:
        if not self._bundle_version:
            self._logger.error("Bundle version is unset - provide it through the DAGS_VERSION environment variable")
            raise ReefServiceError(500, "Bundle version is not configured")
        return self._bundle_version

    def _require_archive(self) -> Path:
        if not self._archive_path.is_file():
            self._logger.error(f"No bundle archive at {self._archive_path}")
            raise ReefServiceError(500, f"Bundle archive not found at '{self._archive_path}'")
        return self._archive_path

    def check_liveness(self) -> dict:
        return {"healthy": True}

    def describe_service(self) -> dict:
        if not self._server_version:
            self._logger.error("Server version is unset - provide it through the REEF_SERVER_VERSION environment variable")
            raise ReefServiceError(500, "Server version is not configured")
        return {"serverVersion": self._server_version, "dagsVersion": self._require_bundle_version()}

    def describe_bundle(self) -> dict:
        version = self._require_bundle_version()
        self._require_archive()

        if self._signature is None:
            self._signature = self._load_signature()

        return {"version": version, "signature": self._signature}

    def resolve_bundle_archive(self) -> Path:
        self._require_bundle_version()
        return self._require_archive()

    def evaluate_readiness(self) -> dict:
        # Checks run in order and the first failure short-circuits, so a check that was never
        # reached stays False. Clients read the flags as "confirmed true", not as "known false".
        checks = {"healthy": True, "dags_exists": False, "dags_version_set": False}

        if not self._archive_path.is_file():
            self._logger.fatal(f"Not ready - no bundle archive under '{self._archive_path.parent}'")
            checks["healthy"] = False
            return checks
        checks["dags_exists"] = True

        if not self._bundle_version:
            self._logger.fatal("Not ready - bundle version is unset; provide it through the DAGS_VERSION environment variable.")
            checks["healthy"] = False
            return checks
        checks["dags_version_set"] = True

        return checks
