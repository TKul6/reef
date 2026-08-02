from __future__ import annotations

import io
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from reef_bundle.client import ReefClient, ReefClientError

BASE_URL = "http://reef:8080"


@pytest.fixture
def client() -> ReefClient:
    return ReefClient(base_url=BASE_URL, timeout=5, max_retries=3, backoff_initial=0, backoff_increment=0)


def _mock_response(status_code: int = 200, json_data: dict | None = None, content: bytes = b"") -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.content = content
    resp.json.return_value = json_data or {}
    resp.raise_for_status.return_value = None
    return resp


def test_check_liveness_calls_the_health_route(client):
    resp = _mock_response(200)
    with patch("requests.request", return_value=resp) as mock_req:
        client.check_liveness()
        mock_req.assert_called_once_with(method="GET", url=f"{BASE_URL}/api/v1/health", timeout=5)


def test_check_liveness_raises_on_error_status(client):
    resp = _mock_response(500)
    resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
    with patch("requests.request", return_value=resp):
        with pytest.raises(ReefClientError):
            client.check_liveness()


def test_describe_bundle_calls_the_metadata_route(client):
    resp = _mock_response(200, json_data={"version": "1.2.3", "signature": "a3f9c1d2e4b5"})
    with patch("requests.request", return_value=resp) as mock_req:
        client.describe_bundle()
        mock_req.assert_called_once_with(method="GET", url=f"{BASE_URL}/api/v1/dags/metadata", timeout=5)


def test_describe_bundle_returns_parsed_json(client):
    payload = {"version": "1.2.3", "signature": "a3f9c1d2e4b5"}
    resp = _mock_response(200, json_data=payload)
    with patch("requests.request", return_value=resp):
        assert client.describe_bundle() == payload


def test_describe_bundle_raises_when_the_request_fails(client):
    with patch("requests.request", side_effect=requests.ConnectionError("unreachable")):
        with pytest.raises(ReefClientError):
            client.describe_bundle()


def test_get_bundle_version_returns_the_version_string(client):
    version = "42.0.1"
    resp = _mock_response(200, json_data={"version": version, "signature": "a3f9c1d2e4b5"})
    with patch("requests.request", return_value=resp):
        assert client.get_bundle_version() == version


def test_get_bundle_version_raises_when_the_version_is_absent(client):
    resp = _mock_response(200, json_data={})
    with patch("requests.request", return_value=resp):
        with pytest.raises(KeyError):
            client.get_bundle_version()


def test_download_bundle_calls_the_download_route(client):
    resp = _mock_response(200, content=b"\x1f\x8b\x08stand-in-for-a-gzip-stream")
    with patch("requests.request", return_value=resp) as mock_req:
        client.download_bundle()
        mock_req.assert_called_once_with(method="GET", url=f"{BASE_URL}/api/v1/dags/download", timeout=5)


def test_download_bundle_returns_the_body_as_a_buffer(client):
    archive = b"\x1f\x8b\x08stand-in-for-a-gzip-stream"
    resp = _mock_response(200, content=archive)
    with patch("requests.request", return_value=resp):
        result = client.download_bundle()
        assert isinstance(result, io.BytesIO)
        assert result.read() == archive


def test_download_bundle_raises_when_the_request_fails(client):
    with patch("requests.request", side_effect=requests.Timeout("timed out")):
        with pytest.raises(ReefClientError):
            client.download_bundle()


def test_retry_succeeds_on_the_second_attempt(client):
    version = "1.0.0"
    good_resp = _mock_response(200, json_data={"version": version})
    with patch("requests.request", side_effect=[requests.ConnectionError("down"), good_resp]):
        assert client.get_bundle_version() == version


def test_retry_gives_up_once_every_attempt_is_spent(client):
    err = requests.ConnectionError("always down")
    with patch("requests.request", side_effect=[err, err, err]) as mock_req:
        with pytest.raises(ReefClientError) as exc_info:
            client.check_liveness()
        assert "3 attempts" in str(exc_info.value)
        assert mock_req.call_count == 3


def test_retry_wait_grows_with_each_attempt():
    client = ReefClient(base_url=BASE_URL, max_retries=3, backoff_initial=1.0, backoff_increment=0.5)
    err = requests.ConnectionError("down")
    good_resp = _mock_response(200)
    with patch("requests.request", side_effect=[err, err, good_resp]):
        with patch("time.sleep") as mock_sleep:
            client.check_liveness()
            assert mock_sleep.call_args_list == [call(1.0), call(1.5)]
            
