import hashlib
from unittest.mock import Mock

import pytest

from reef_server.constants import ARCHIVE_FILENAME, SIGNATURE_FILENAME
from reef_server.errors import ReefServiceError
from reef_server.service import ReefService

BUNDLE_VERSION = "1.0.0"
SERVER_VERSION = "1.0.0"
ARCHIVE_CONTENT = b"fake-tar-content"
SIGNATURE_FILE_CONTENT = "12345-1"


def _make_service(tmp_path, *, bundle_version: str | None = BUNDLE_VERSION, server_version: str | None = SERVER_VERSION) -> tuple[ReefService, Mock]:
    logger_mock = Mock(name="logger")
    service = ReefService(
        bundle_dir=tmp_path,
        bundle_version=bundle_version,
        server_version=server_version,
        logger=logger_mock,
    )
    return service, logger_mock


def test_liveness_returns_ok(tmp_path):
    # Arrange
    service, _ = _make_service(tmp_path)

    # Act
    result = service.check_liveness()

    # Assert
    assert result == {"healthy": True}


def test_describe_service_returns_server_and_bundle_versions(tmp_path):
    # Arrange
    service, logger_mock = _make_service(tmp_path)

    # Act
    result = service.describe_service()

    # Assert
    assert result == {"serverVersion": SERVER_VERSION, "dagsVersion": BUNDLE_VERSION}
    logger_mock.error.assert_not_called()


def test_describe_service_raises_when_server_version_unset(tmp_path):
    # Arrange
    service, logger_mock = _make_service(tmp_path, server_version=None)

    # Act
    with pytest.raises(ReefServiceError) as exc_info:
        service.describe_service()

    # Assert
    assert exc_info.value.status_code == 500
    logger_mock.error.assert_called_once()


def test_describe_service_raises_when_bundle_version_unset(tmp_path):
    # Arrange
    service, logger_mock = _make_service(tmp_path, bundle_version=None)

    # Act
    with pytest.raises(ReefServiceError) as exc_info:
        service.describe_service()

    # Assert
    assert exc_info.value.status_code == 500
    logger_mock.error.assert_called_once()


def test_describe_bundle_returns_valid_object(tmp_path):
    # Arrange
    (tmp_path / ARCHIVE_FILENAME).write_bytes(ARCHIVE_CONTENT)
    (tmp_path / SIGNATURE_FILENAME).write_text(f"{SIGNATURE_FILE_CONTENT}\n")
    service, logger_mock = _make_service(tmp_path)

    # Act
    result = service.describe_bundle()

    # Assert
    assert result == {"version": BUNDLE_VERSION, "signature": SIGNATURE_FILE_CONTENT}
    logger_mock.error.assert_not_called()


def test_describe_bundle_falls_back_to_checksum_when_signature_file_missing(tmp_path):
    # Arrange
    (tmp_path / ARCHIVE_FILENAME).write_bytes(ARCHIVE_CONTENT)
    expected_signature = hashlib.sha256(ARCHIVE_CONTENT).hexdigest()[:12]
    service, logger_mock = _make_service(tmp_path)

    # Act
    result = service.describe_bundle()

    # Assert
    assert result == {"version": BUNDLE_VERSION, "signature": expected_signature}
    logger_mock.error.assert_not_called()


def test_describe_bundle_caches_the_signature_across_calls(tmp_path):
    # Arrange
    signature_file = tmp_path / SIGNATURE_FILENAME
    (tmp_path / ARCHIVE_FILENAME).write_bytes(ARCHIVE_CONTENT)
    signature_file.write_text(SIGNATURE_FILE_CONTENT)
    service, _ = _make_service(tmp_path)

    # Act
    first = service.describe_bundle()
    signature_file.write_text("a-later-signature")
    second = service.describe_bundle()

    # Assert - the archive is immutable for the life of the process, so the file is read once
    assert first == second == {"version": BUNDLE_VERSION, "signature": SIGNATURE_FILE_CONTENT}


def test_describe_bundle_raises_when_version_unset(tmp_path):
    # Arrange
    service, _ = _make_service(tmp_path, bundle_version=None)

    # Act
    with pytest.raises(ReefServiceError) as exc_info:
        service.describe_bundle()

    # Assert
    assert exc_info.value.status_code == 500


def test_describe_bundle_raises_when_archive_not_found(tmp_path):
    # Arrange
    service, logger_mock = _make_service(tmp_path)

    # Act
    with pytest.raises(ReefServiceError) as exc_info:
        service.describe_bundle()

    # Assert
    assert exc_info.value.status_code == 500
    logger_mock.error.assert_called_once()


def test_resolve_bundle_archive_returns_archive_path(tmp_path):
    # Arrange
    archive_file = tmp_path / ARCHIVE_FILENAME
    archive_file.write_bytes(b"")
    service, logger_mock = _make_service(tmp_path)

    # Act
    result = service.resolve_bundle_archive()

    # Assert
    assert result == archive_file
    logger_mock.error.assert_not_called()


def test_resolve_bundle_archive_raises_when_bundle_version_unset(tmp_path):
    # Arrange
    service, logger_mock = _make_service(tmp_path, bundle_version=None)

    # Act
    with pytest.raises(ReefServiceError) as exc_info:
        service.resolve_bundle_archive()

    # Assert
    assert exc_info.value.status_code == 500
    logger_mock.error.assert_called_once()


def test_resolve_bundle_archive_raises_when_archive_not_found(tmp_path):
    # Arrange
    service, logger_mock = _make_service(tmp_path)

    # Act
    with pytest.raises(ReefServiceError) as exc_info:
        service.resolve_bundle_archive()

    # Assert
    assert exc_info.value.status_code == 500
    logger_mock.error.assert_called_once()


def test_readiness_returns_healthy_when_ok(tmp_path):
    # Arrange
    (tmp_path / ARCHIVE_FILENAME).write_bytes(b"")
    service, logger_mock = _make_service(tmp_path)

    # Act
    checks = service.evaluate_readiness()

    # Assert
    assert checks == {"healthy": True, "dags_exists": True, "dags_version_set": True}
    logger_mock.error.assert_not_called()


def test_readiness_returns_unhealthy_when_archive_not_found(tmp_path):
    # Arrange
    service, logger_mock = _make_service(tmp_path)

    # Act
    checks = service.evaluate_readiness()

    # Assert
    assert checks == {"healthy": False, "dags_exists": False, "dags_version_set": False}
    logger_mock.error.assert_called_once()


def test_readiness_returns_unhealthy_when_bundle_version_unset(tmp_path):
    # Arrange
    (tmp_path / ARCHIVE_FILENAME).write_bytes(b"")
    service, logger_mock = _make_service(tmp_path, bundle_version=None)

    # Act
    checks = service.evaluate_readiness()

    # Assert
    assert checks == {"healthy": False, "dags_exists": True, "dags_version_set": False}
    logger_mock.error.assert_called_once()
