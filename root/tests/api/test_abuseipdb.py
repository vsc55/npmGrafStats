#!/usr/bin/env python3
"""Tests for the AbuseIPDB integration module."""

# pylint: disable=use-implicit-booleaness-not-comparison
# pylint: disable=unused-argument

import atexit
import json

import pytest
import requests

from api.external.abuseipdb import AbuseIPDB, AbuseIPDBStatusReturn
from api.external.abuseipdb.exceptions import (AbuseIPDBConfigError,
                                               AbuseIPDBNetworkError,
                                               AbuseIPDBRateLimitError,
                                               AbuseIPDBResponseError)

# ---------------------------------------------------------------------------
# Helpers / Dummy responses
# ---------------------------------------------------------------------------

class DummyResponse:
    """Simple dummy response to simulate requests.Response."""
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        """ Return the preset JSON payload. """
        return self._payload


class DummyBadJSONResponse:
    """Dummy response whose json() raises JSONDecodeError."""
    def __init__(self, status_code: int = 200):
        self.status_code = status_code

    def json(self):
        """ Always raises JSONDecodeError. """
        raise json.JSONDecodeError("Expecting value", "xxx", 0)


@pytest.fixture(autouse=True)
def no_abuseip_atexit():
    """ Disable the AbuseIPDB atexit handler during tests. """
    import api.external.abuseipdb.abuseipdb_app as abuseipdb_app  # pylint: disable=import-outside-toplevel

    # Unregister the atexit handler if it is registered
    try:
        atexit.unregister(abuseipdb_app.save_abuse_instance)
    except AttributeError:
        # Python without unregister -> cannot do it this way
        pass
    except ValueError:
        # handler was not registered -> nothing to do
        pass

    yield
    # No re-register anything: in tests you don't want the atexit to run

# ---------------------------------------------------------------------------
# Tests for properties / basic behaviour
# ---------------------------------------------------------------------------

def test_defaults_and_base_result():
    """Check default values and base_result() structure."""
    abuse = AbuseIPDB()

    # Defaults
    assert abuse.url == "https://api.abuseipdb.com/api/v2/check"
    assert abuse.ip == ""
    assert abuse.key == ""
    assert abuse.timeout == 10
    assert abuse.max_age_in_days == 90
    assert abuse.verbose is False
    assert abuse.last_result == {}

    # base_result
    base = abuse.base_result()
    assert base["status"] is AbuseIPDBStatusReturn.UNKNOWN
    assert base["status_code"] == 0
    assert base["error_message"] == ""
    assert base["data"] == {}
    assert base["errors"] == []


def test_ip_setter_valid_ipv4_and_ipv6():
    """Check valid IPv4 and IPv6 addresses are accepted."""
    abuse = AbuseIPDB()

    abuse.ip = "8.8.8.8"
    assert abuse.ip == "8.8.8.8"
    assert abuse.is_ip_set

    abuse.ip = "2001:4860:4860::8888"
    assert abuse.ip == "2001:4860:4860::8888"
    assert abuse.is_ip_set


def test_ip_setter_invalid_ip_raises():
    """Check invalid IP addresses raise ValueError."""
    abuse = AbuseIPDB()

    with pytest.raises(ValueError):
        abuse.ip = "not-an-ip"


def test_ip_setter_empty_clears_ip():
    """Setting empty string clears IP and is_ip_set is False."""
    abuse = AbuseIPDB()
    abuse.ip = "8.8.8.8"
    assert abuse.is_ip_set

    abuse.ip = ""
    assert abuse.ip == ""
    assert abuse.is_ip_set is False


def test_key_setter_trims_and_is_key_set():
    """Check key setter trims whitespace and is_key_set works."""
    abuse = AbuseIPDB()
    abuse.key = "  KEY123  "
    assert abuse.key == "KEY123"
    assert abuse.is_key_set

    abuse.key = "   "
    assert abuse.key == ""
    assert abuse.is_key_set is False


def test_max_age_in_days_validation():
    """Check max_age_in_days setter validation."""
    abuse = AbuseIPDB()

    abuse.max_age_in_days = 30
    assert abuse.max_age_in_days == 30

    with pytest.raises(ValueError):
        abuse.max_age_in_days = 0

    with pytest.raises(ValueError):
        abuse.max_age_in_days = 366


def test_verbose_and_timeout_and_flags():
    """Check verbose, timeout properties."""
    abuse = AbuseIPDB()
    abuse.verbose = True
    abuse.timeout = 5

    assert abuse.verbose is True
    assert abuse.timeout == 5


# ---------------------------------------------------------------------------
# Tests for the object-oriented API: AbuseIPDB.api_check()
# ---------------------------------------------------------------------------

def test_api_check_success(monkeypatch):
    """api_check -> SUCCESS when status_code=200 and data is present."""
    abuse = AbuseIPDB()
    abuse.key = "KEY123"
    abuse.ip = "8.8.8.8"

    def fake_request(method, url, headers, params, timeout):
        assert method == "GET"
        assert headers["Key"] == "KEY123"
        assert params["ipAddress"] == "8.8.8.8"
        assert params["maxAgeInDays"] == str(abuse.max_age_in_days)
        return DummyResponse(
            200,
            {"data": {"abuseConfidenceScore": 42}, "errors": []},
        )

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    result = abuse.api_check()

    assert result["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert result["status_code"] == 200
    assert result["data"]["abuseConfidenceScore"] == 42
    assert result["errors"] == []
    assert abuse.last_result == result


def test_api_check_warning_no_data(monkeypatch):
    """api_check -> WARNING when status_code=200 but no data."""
    abuse = AbuseIPDB()
    abuse.key = "KEY123"
    abuse.ip = "8.8.8.8"

    def fake_request(*args, **kwargs):
        return DummyResponse(200, {"data": {}, "errors": []})

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    result = abuse.api_check()

    assert result["status"] is AbuseIPDBStatusReturn.WARNING
    assert result["status_code"] == 200
    assert result["data"] == {}
    assert result["error_message"] == "No data returned from AbuseIPDB"


def test_api_check_config_error_no_key():
    """Missing API key -> AbuseIPDBConfigError."""
    abuse = AbuseIPDB()
    abuse.ip = "8.8.8.8"

    with pytest.raises(AbuseIPDBConfigError) as excinfo:
        abuse.api_check()

    assert "API key is required" in str(excinfo.value)


def test_api_check_config_error_no_ip():
    """Missing IP -> AbuseIPDBConfigError."""
    abuse = AbuseIPDB()
    abuse.key = "KEY123"

    with pytest.raises(AbuseIPDBConfigError) as excinfo:
        abuse.api_check()

    assert "IP address is required" in str(excinfo.value)


def test_api_check_network_error(monkeypatch):
    """RequestException -> AbuseIPDBNetworkError."""
    abuse = AbuseIPDB()
    abuse.key = "KEY123"
    abuse.ip = "8.8.8.8"

    def fake_request(*args, **kwargs):
        raise requests.RequestException("Boom")

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    with pytest.raises(AbuseIPDBNetworkError) as excinfo:
        abuse.api_check()

    err = excinfo.value
    assert "Network error calling AbuseIPDB" in str(err)
    assert isinstance(err.original, requests.RequestException)


def test_api_check_json_decode_error(monkeypatch):
    """JSON invalid -> AbuseIPDBResponseError."""
    abuse = AbuseIPDB()
    abuse.key = "KEY123"
    abuse.ip = "8.8.8.8"

    def fake_request(*args, **kwargs):
        return DummyBadJSONResponse(status_code=200)

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    with pytest.raises(AbuseIPDBResponseError) as excinfo:
        abuse.api_check()

    err: AbuseIPDBResponseError = excinfo.value
    assert "Invalid JSON response from AbuseIPDB" in str(err)
    assert err.status_code == 200


def test_api_check_http_error_raises_response_error(monkeypatch):
    """HTTP != 200 -> AbuseIPDBResponseError with api_errors and status_code."""
    abuse = AbuseIPDB()
    abuse.key = "KEY123"
    abuse.ip = "8.8.8.8"

    err_code = 420
    err_detail = "Error detail message"

    def fake_request(*args, **kwargs):
        return DummyResponse(
            err_code,
            {"errors": [{"detail": err_detail, "status": err_code}]}
        )

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    with pytest.raises(AbuseIPDBResponseError) as excinfo:
        abuse.api_check()

    err: AbuseIPDBResponseError = excinfo.value
    assert err.status_code == err_code
    assert err.api_errors[0]["detail"] == err_detail


def test_api_check_http_error_ratelimit(monkeypatch):
    """HTTP 429 -> AbuseIPDBRateLimitError with rate limit info."""
    abuse = AbuseIPDB()
    abuse.key = "KEY123"
    abuse.ip = "8.8.8.8"

    err_code = 429
    err_detail = (
        "Daily rate limit of 3000 requests exceeded for this endpoint. "
        "See headers for additional details."
    )

    def fake_request(*args, **kwargs):
        return DummyResponse(
            err_code,
            {"errors": [{"detail": err_detail, "status": err_code}]}
        )

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    with pytest.raises(AbuseIPDBRateLimitError) as excinfo:
        abuse.api_check()

    err: AbuseIPDBRateLimitError = excinfo.value
    assert err.status_code == err_code
    assert err.api_errors[0]["detail"] == err_detail


# ---------------------------------------------------------------------------
# Tests for the static wrapper AbuseIPDB.check()
# ---------------------------------------------------------------------------

def test_check_invalid_ip_returns_error_result():
    """Invalid IP -> status_code -20 and does not raise exception."""
    result = AbuseIPDB.check("not-an-ip", "KEY123")

    assert result["status"] is AbuseIPDBStatusReturn.ERROR
    assert result["status_code"] == -20
    assert "Invalid IP address" in result["error_message"]


def test_check_config_error_missing_key():
    """Missing key -> translates to status_code -1 via AbuseIPDBConfigError."""
    result = AbuseIPDB.check("8.8.8.8", "")

    assert result["status"] is AbuseIPDBStatusReturn.ERROR
    assert result["status_code"] == -1
    assert "API key is required" in result["error_message"]


def test_check_network_error_maps_to_minus2(monkeypatch):
    """Network errors -> status_code -2."""
    def fake_request(*args, **kwargs):
        raise requests.RequestException("Network down")

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    result = AbuseIPDB.check("8.8.8.8", "KEY123")

    assert result["status"] is AbuseIPDBStatusReturn.ERROR
    assert result["status_code"] == -2
    assert "Network error calling AbuseIPDB" in result["error_message"]


def test_check_response_error_maps_http_status(monkeypatch):
    """HTTP errors -> status_code from HTTP or -3."""
    def fake_request(*args, **kwargs):
        return DummyResponse(
            401,
            {
                "errors": [
                    {"detail": "Authentication failed", "status": 401}
                ]
            },
        )

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    result = AbuseIPDB.check("8.8.8.8", "BADKEY")

    assert result["status"] is AbuseIPDBStatusReturn.ERROR
    assert result["status_code"] == 401
    assert "AbuseIPDB request failed" in result["error_message"]
    assert result["errors"][0]["detail"] == "Authentication failed"


def test_check_success_path(monkeypatch):
    """Happy path via check(): should return SUCCESS just like api_check."""
    def fake_request(*args, **kwargs):
        return DummyResponse(
            200,
            {"data": {"abuseConfidenceScore": 7}, "errors": []},
        )

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    result = AbuseIPDB.check("8.8.8.8", "KEY123")

    assert result["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert result["status_code"] == 200
    assert result["data"]["abuseConfidenceScore"] == 7


# ---------------------------------------------------------------------------
# Tests for AbuseIPDB.checks()
# ---------------------------------------------------------------------------

def test_checks_multiple_ips(monkeypatch):
    """checks() must call API for each IP and return list of results."""
    calls = []

    def fake_request(method, url, headers, params, timeout):
        calls.append(params.get("ipAddress"))
        return DummyResponse(
            200,
            {"data": {"abuseConfidenceScore": 5}, "errors": []},
        )

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    ips = ["8.8.8.8", "1.1.1.1"]
    results = AbuseIPDB.checks(ips, "KEY123")

    assert calls == ips
    assert len(results) == 2
    for res in results:
        assert res["status"] is AbuseIPDBStatusReturn.SUCCESS
        assert res["data"]["abuseConfidenceScore"] == 5


def test_checks_mixed_valid_and_invalid_ip(monkeypatch):
    """checks() should return error -20 for invalid IPs and success for valid ones."""
    def fake_request(method, url, headers, params, timeout):
        return DummyResponse(
            200,
            {"data": {"abuseConfidenceScore": 1}, "errors": []},
        )

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    ips = ["8.8.8.8", "not-an-ip", "1.1.1.1"]
    results = AbuseIPDB.checks(ips, "KEY123")

    assert len(results) == 3

    assert results[0]["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert results[0]["status_code"] == 200

    assert results[1]["status"] is AbuseIPDBStatusReturn.ERROR
    assert results[1]["status_code"] == -20

    assert results[2]["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert results[2]["status_code"] == 200


# ---------------------------------------------------------------------------
# Tests for cache behaviour
# ---------------------------------------------------------------------------

def test_cache_hit_avoids_second_request(monkeypatch):
    """
    Two consecutive calls with the same parameters:
    the second should use the cache and not call the API again.
    """
    abuse = AbuseIPDB()
    abuse.key = "KEY123"
    abuse.ip = "8.8.8.8"

    calls = []

    def fake_request(method, url, headers, params, timeout):
        calls.append(params.get("ipAddress"))
        # Important: include both fields required by get_from_cache
        return DummyResponse(
            200,
            {
                "data": {
                    "abuseConfidenceScore": 10,
                    "totalReports": 1,
                },
                "errors": [],
            },
        )

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    # First call: goes to the API and caches
    result1 = abuse.api_check()
    assert result1["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert calls == ["8.8.8.8"]

    # Second call: should use the cache and not call the API again
    result2 = abuse.api_check()
    assert result2["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert calls == ["8.8.8.8"]  # there is still only one call

def test_cache_expired_entry(monkeypatch):
    """
    If the entry is expired (according to cache_expire),
    it should be removed from the cache and the API should be called again.
    """
    # Force short expiration
    monkeypatch.setenv("ABUSEIP_CACHE_EXPIRE", "1")  # 1 minute

    # Create the object (will read the new expiration value)
    abuse = AbuseIPDB()
    abuse.key = "KEY123"
    abuse.ip = "8.8.8.8"

    # Fake time to control expiration
    def fake_time():
        return fake_time.current

    fake_time.current = 1000.0
    monkeypatch.setattr("api.external.abuseipdb.time.time", fake_time)

    calls = []

    def fake_request(method, url, headers, params, timeout):
        calls.append(params.get("ipAddress"))
        return DummyResponse(
            200,
            {
                "data": {
                    "abuseConfidenceScore": 10,
                    "totalReports": 1,
                },
                "errors": [],
            },
        )

    monkeypatch.setattr(
        "api.external.abuseipdb.requests.request",
        fake_request,
    )

    # First call: goes to the API and caches with timestamp t0
    abuse.api_check()
    assert calls == ["8.8.8.8"]

    # Advance time by more than 60 seconds to expire the cache
    fake_time.current = 1000.0 + 61

    # Second call: should see expired cache and call the API again
    abuse.api_check()
    assert calls == ["8.8.8.8", "8.8.8.8"]

def test_cache_load_and_save_and_clear(monkeypatch, tmp_path):
    """
    Test that cache is saved to disk and loaded back correctly.
    """
    cache_path = tmp_path / "abuseipdb_cache.json"
    monkeypatch.setenv("ABUSEIP_CACHE_FILE", str(cache_path))
    monkeypatch.setenv("ABUSEIP_CACHE_EXPIRE", "60")

    fake_data = {
        "124.85.238.241": {
            "timestamp": 1765206017.218901,
            "data": {
                "ipAddress": "124.85.238.241",
                "isPublic": True,
                "ipVersion": 4,
                "isWhitelisted": None,
                "abuseConfidenceScore": 10,
                "countryCode": "JP",
                "usageType": "Fixed Line ISP",
                "isp": "Open Computer Network",
                "domain": "ocn.ne.jp",
                "hostnames": [],
                "isTor": False,
                "totalReports": 15,
                "numDistinctUsers": 5,
                "lastReportedAt": None
            }
        }
    }

    # First, create an instance and populate the cache and save to disk
    abuse = AbuseIPDB()
    abuse.cache_data = fake_data
    assert abuse.save_cache() is True
    assert cache_path.exists()

    # Second, create a new instance which should load the cache from disk
    abuse2 = AbuseIPDB()
    assert '124.85.238.241' in abuse2.cache_data
    cached_response = abuse2.cache_data['124.85.238.241']
    assert cached_response['data']['abuseConfidenceScore'] == 10
    assert cached_response['data']['totalReports'] == 15

    # Finally, test that clear_cache() empties the cache and updates the file
    assert abuse2.clear_cache() is True
    assert abuse2.cache_data == {}
    assert cache_path.read_text(encoding="utf-8") == "{}"

def test_load_cache_corrupt_file_renamed(monkeypatch, tmp_path):
    """
    If the cache file contains invalid JSON,
    load_cache() should rename it to *.err-... and leave the cache empty.
    """
    cache_path = tmp_path / "abuseipdb_cache.json"
    monkeypatch.setenv("ABUSEIP_CACHE_FILE", str(cache_path))
    monkeypatch.setenv("ABUSEIP_CACHE_EXPIRE", "60")

    cache_path.write_text("{ not json }", encoding="utf-8")

    abuse = AbuseIPDB()

    # After __post_init__ + load_cache(), the internal cache should be empty
    assert abuse.cache_data == {}

    # The original file should have been renamed to *.err-*
    err_files = list(cache_path.parent.glob(cache_path.name + ".err-*"))
    assert len(err_files) == 1

def test_cache_file_is_none(monkeypatch):
    """
    If ABUSEIP_CACHE_FILE is set to empty string,
    The cache file should be None and no disk operations should occur.
    """
    monkeypatch.setenv("ABUSEIP_CACHE_FILE", "")
    monkeypatch.setenv("ABUSEIP_CACHE_EXPIRE", "60")

    abuse = AbuseIPDB(_cache_path=None)
    abuse.cache_path = None

    assert abuse.cache_path is None
    assert abuse.is_cache_active is False
    assert abuse.is_cache_set is False
    assert abuse.load_cache() == {}
    assert abuse.save_cache() is False
    assert abuse.clear_cache() is True
