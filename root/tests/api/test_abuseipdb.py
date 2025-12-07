#!/usr/bin/env python3
"""Tests for the AbuseIPDB integration module."""

# pylint: disable=use-implicit-booleaness-not-comparison
# pylint: disable=unused-argument

import json

import pytest
import requests

from api.external.abuseipdb import AbuseIPDB, AbuseIPDBStatusReturn
from api.external.abuseipdb.exceptions import (AbuseIPDBConfigError,
                                               AbuseIPDBNetworkError,
                                               AbuseIPDBRateLimitError,
                                               AbuseIPDBResponseError)
from logger import LogLevel, get_manager

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
    """Check verbose, timeout, debug, show properties."""
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


def test_api_check_http_error_ratelimit(monkeypatch, capsys):
    """HTTP 429 -> AbuseIPDBRateLimitError with rate limit info."""
    # pylint: disable=line-too-long

    abuse = AbuseIPDB()
    abuse.key = "KEY123"
    abuse.ip = "8.8.8.8"

    err_code = 429
    err_detail = "Daily rate limit of 3000 requests exceeded for this endpoint. See headers for additional details."

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
    """checks() invokes check() for each IP and groups the results."""
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
