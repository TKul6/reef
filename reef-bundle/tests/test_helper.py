from __future__ import annotations

import io
import tarfile
from logging import Logger
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from reef_bundle.client import ReefClient, ReefClientError
from reef_bundle.helper import ReefBundleError, ReefBundleHelper

REEF_URL = "http://reef:8080"


def _make_tar_gz(files: dict[str, bytes] | None = None) -> io.BytesIO:
    """Build an in-memory .tar.gz holding the given {filename: content} entries."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in (files or {"dag.py": b"# dag"}).items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    buf.seek(0)
    return buf


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock(spec=ReefClient)


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock(spec=Logger)


@pytest.fixture
def helper(tmp_path: Path, mock_client: MagicMock, mock_logger: MagicMock) -> ReefBundleHelper:
    return ReefBundleHelper(client=mock_client, bundle_dir=tmp_path / "dags", logger=mock_logger)


# ---------------------------------------------------------------------------
# ensure_bundle_dir - the directory is created on demand and reused when present
# ---------------------------------------------------------------------------


def test_ensure_bundle_dir_creates_the_directory_when_it_is_missing(helper: ReefBundleHelper) -> None:
    # Arrange
    assert not helper.bundle_dir.exists()

    # Act
    helper.ensure_bundle_dir()

    # Assert
    assert helper.bundle_dir.is_dir()


def test_ensure_bundle_dir_leaves_an_existing_directory_alone(helper: ReefBundleHelper) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)

    # Act
    helper.ensure_bundle_dir()  # should not raise

    # Assert
    assert helper.bundle_dir.is_dir()


# ---------------------------------------------------------------------------
# clear_bundle_dir - the contents go, the directory itself stays
# ---------------------------------------------------------------------------


def test_clear_bundle_dir_removes_files_and_subdirectories(helper: ReefBundleHelper) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    (helper.bundle_dir / "dag.py").write_text("# dag")
    (helper.bundle_dir / "subdir").mkdir()
    (helper.bundle_dir / "subdir" / "nested.py").write_text("# nested")

    # Act
    helper.clear_bundle_dir()

    # Assert
    assert list(helper.bundle_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# extract_archive - a real gzipped tar is unpacked, anything else is rejected
# ---------------------------------------------------------------------------


def test_extract_archive_unpacks_the_archive_contents(helper: ReefBundleHelper) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    buf = _make_tar_gz({"dag.py": b"# hello"})

    # Act
    helper.extract_archive(buf)

    # Assert
    assert (helper.bundle_dir / "dag.py").read_bytes() == b"# hello"


def test_extract_archive_raises_on_something_that_is_not_an_archive(helper: ReefBundleHelper) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    buf = io.BytesIO(b"not a valid tar")

    # Act & Assert
    with pytest.raises(ReefBundleError, match="Could not extract the bundle archive"):
        helper.extract_archive(buf)


# ---------------------------------------------------------------------------
# check_liveness - a pass-through to the client, errors included
# ---------------------------------------------------------------------------


def test_check_liveness_delegates_to_the_client(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Act
    helper.check_liveness()

    # Assert
    mock_client.check_liveness.assert_called_once_with()


def test_check_liveness_lets_the_client_error_through(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Arrange
    mock_client.check_liveness.side_effect = ReefClientError("unreachable")

    # Act & Assert
    with pytest.raises(ReefClientError):
        helper.check_liveness()


# ---------------------------------------------------------------------------
# resolve_version - a pinned version wins outright, otherwise Reef is asked
# ---------------------------------------------------------------------------


def test_resolve_version_returns_the_pinned_version_without_asking_reef(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Act
    result = helper.resolve_version("1.2.3")

    # Assert
    assert result == "1.2.3"
    mock_client.get_bundle_version.assert_not_called()


def test_resolve_version_asks_reef_when_nothing_is_pinned(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Arrange
    mock_client.get_bundle_version.return_value = "9.0.0"

    # Act
    result = helper.resolve_version(None)

    # Assert
    assert result == "9.0.0"
    mock_client.get_bundle_version.assert_called_once_with()


def test_resolve_version_returns_none_and_logs_when_reef_cannot_answer(
    helper: ReefBundleHelper, mock_client: MagicMock, mock_logger: MagicMock
) -> None:
    # Arrange
    mock_client.get_bundle_version.side_effect = ReefClientError("down")

    # Act
    result = helper.resolve_version(None)

    # Assert
    assert result is None
    mock_logger.error.assert_called_once()
    assert "Could not read the bundle version" in mock_logger.error.call_args[0][0]


# ---------------------------------------------------------------------------
# sync - the signature decides whether an archive is fetched at all
# ---------------------------------------------------------------------------


def test_sync_downloads_and_extracts_on_a_new_signature(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    buf = _make_tar_gz({"dag.py": b"# new"})
    mock_client.describe_bundle.return_value = {"signature": "abc123"}
    mock_client.download_bundle.return_value = buf

    # Act
    helper.sync(REEF_URL)

    # Assert
    assert helper.current_signature == "abc123"
    mock_client.download_bundle.assert_called_once_with()
    assert (helper.bundle_dir / "dag.py").read_bytes() == b"# new"


def test_sync_skips_the_download_when_the_signature_is_unchanged(helper: ReefBundleHelper, mock_client: MagicMock, mock_logger: MagicMock) -> None:
    # Arrange
    helper.current_signature = "abc123"
    mock_client.describe_bundle.return_value = {"signature": "abc123"}

    # Act
    helper.sync(REEF_URL)

    # Assert
    mock_client.download_bundle.assert_not_called()
    mock_logger.info.assert_called_once()
    assert "already current" in mock_logger.info.call_args[0][0]


def test_sync_empties_the_directory_before_extracting(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    stale = helper.bundle_dir / "stale.py"
    stale.write_text("# stale")

    buf = _make_tar_gz({"new_dag.py": b"# new"})
    mock_client.describe_bundle.return_value = {"signature": "newSig"}
    mock_client.download_bundle.return_value = buf

    # Act
    helper.sync(REEF_URL)

    # Assert
    assert not stale.exists()
    assert (helper.bundle_dir / "new_dag.py").exists()


def test_sync_records_the_new_signature_afterwards(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    mock_client.describe_bundle.return_value = {"signature": "v2"}
    mock_client.download_bundle.return_value = _make_tar_gz()

    # Act
    helper.sync(REEF_URL)

    # Assert
    assert helper.current_signature == "v2"


def test_sync_says_where_the_bundle_came_from(helper: ReefBundleHelper, mock_client: MagicMock, mock_logger: MagicMock) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    mock_client.describe_bundle.return_value = {"signature": "fresh"}
    mock_client.download_bundle.return_value = _make_tar_gz()

    # Act
    helper.sync(REEF_URL)

    # Assert
    mock_logger.info.assert_called_once()
    log_msg = mock_logger.info.call_args[0][0]
    assert "Fetching" in log_msg
    assert REEF_URL in log_msg


# ---------------------------------------------------------------------------
# sync / _recover_local_signature - the signature left on disk by an earlier
# extraction is consulted before anything is downloaded
# ---------------------------------------------------------------------------


def test_sync_recovers_the_signature_from_disk_and_skips_the_download(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    (helper.bundle_dir / ReefBundleHelper.SIGNATURE_FILENAME).write_text("abc123")
    mock_client.describe_bundle.return_value = {"signature": "abc123"}

    # Act
    helper.sync(REEF_URL)

    # Assert
    assert helper.current_signature == "abc123"
    mock_client.download_bundle.assert_not_called()


def test_sync_downloads_anyway_when_the_signature_on_disk_is_stale(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    (helper.bundle_dir / ReefBundleHelper.SIGNATURE_FILENAME).write_text("old-sig\n")
    mock_client.describe_bundle.return_value = {"signature": "new-sig"}
    mock_client.download_bundle.return_value = _make_tar_gz()

    # Act
    helper.sync(REEF_URL)

    # Assert
    assert helper.current_signature == "new-sig"
    mock_client.download_bundle.assert_called_once_with()


def test_sync_copes_with_no_signature_file_at_all(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Arrange
    helper.bundle_dir.mkdir(parents=True)
    mock_client.describe_bundle.return_value = {"signature": "new-sig"}
    mock_client.download_bundle.return_value = _make_tar_gz()

    # Act
    helper.sync(REEF_URL)

    # Assert
    assert helper.current_signature == "new-sig"
    mock_client.download_bundle.assert_called_once_with()


def test_sync_copes_with_the_bundle_directory_not_existing_yet(helper: ReefBundleHelper, mock_client: MagicMock) -> None:
    # Arrange
    mock_client.describe_bundle.return_value = {"signature": "new-sig"}
    mock_client.download_bundle.return_value = _make_tar_gz()

    # Act
    helper.sync(REEF_URL)

    # Assert
    assert helper.current_signature == "new-sig"
    mock_client.download_bundle.assert_called_once_with()
