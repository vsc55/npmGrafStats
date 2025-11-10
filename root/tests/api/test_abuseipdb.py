#!/usr/bin/env python3
"""Tests for AbuseIPDB integration class."""

# pylint: disable=use-implicit-booleaness-not-comparison
# pylint: disable=unused-argument

from __future__ import annotations
import json
import requests
from api.external.abuseipdb import AbuseIPDB, AbuseIPDBStatusReturn

class DummyResponse:
    """Simple fake Response object with configurable status_code and json()."""

    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        """ Return the preset JSON data. """
        return self._json_data

class BadJsonResponse:
    """Response that raises JSONDecodeError when json() is called."""
    status_code = 200

    def json(self):
        """ Return the preset JSON data. """
        raise json.JSONDecodeError("Invalid JSON", "X", 0)


# --- Tests for base_result() and api_check() validation ---

def test_base_result_defaults():
    """base_result() should return a clean structure with unknowns and no errors."""
    abuse = AbuseIPDB()
    res = abuse.base_result()

    assert res["status"] is AbuseIPDBStatusReturn.UNKNOWN
    assert res["status_code"] == 0
    assert res["error_message"] == ""
    assert res["data"] == {}
    assert res["errors"] == []


def test_base_result_with_status():
    """base_result(status=ERROR) should set the status to ERROR and keep the rest default."""
    abuse = AbuseIPDB()
    res = abuse.base_result(AbuseIPDBStatusReturn.ERROR)

    assert res["status"] is AbuseIPDBStatusReturn.ERROR
    assert res["status_code"] == 0
    assert res["error_message"] == ""
    assert res["data"] == {}
    assert res["errors"] == []


def test_api_check_missing_key():
    """If no API key -> ERROR with code -1."""
    abuse = AbuseIPDB()
    abuse.ip = "8.8.8.8"

    res = abuse.api_check()

    assert res["status"] is AbuseIPDBStatusReturn.ERROR
    assert res["status_code"] == -1
    assert "API key" in res["error_message"]
    # Should not touch data/errors
    assert res["data"] == {}
    assert res["errors"] == []


def test_api_check_missing_ip():
    """If no IP -> ERROR with code -2."""
    abuse = AbuseIPDB()
    abuse.key = "KEY123"

    res = abuse.api_check()

    assert res["status"] is AbuseIPDBStatusReturn.ERROR
    assert res["status_code"] == -2
    assert "IP address is required" in res["error_message"]


def test_check_invalid_ip_format():
    """check() with invalid IP -> ERROR, code -20, without calling requests."""
    res = AbuseIPDB.check("not-an-ip", "KEY123", debug=False, show=False)

    assert res["status"] is AbuseIPDBStatusReturn.ERROR
    assert res["status_code"] == -20
    assert "Invalid IP address" in res["error_message"]
    assert res["data"] == {}
    assert res["errors"] == []


# --- Tests for 200 OK flow with data ---

def test_api_check_success_with_data(monkeypatch):
    """Response 200 with data -> SUCCESS with filled data."""
    def fake_request(method, url, headers, params, timeout):
        assert method == "GET"
        assert "Key" in headers
        assert "ipAddress" in params
        return DummyResponse(
            200,
            {
                "data": {
                    "abuseConfidenceScore": 10,
                    "totalReports": 3,
                }
            },
        )

    monkeypatch.setattr("api.external.abuseipdb.requests.request", fake_request)

    abuse = AbuseIPDB()
    abuse.ip = "8.8.8.8"
    abuse.key = "KEY123"

    res = abuse.api_check()

    assert res["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert res["status_code"] == 200
    assert res["data"]["abuseConfidenceScore"] == 10
    assert res["data"]["totalReports"] == 3
    assert res["errors"] == []
    assert res["error_message"] == ""


def test_api_check_success_no_data_warning(monkeypatch, capsys):
    """200 OK pero data vacía -> WARNING, mensaje de warning y sin error de red."""
    def fake_request(method, url, headers, params, timeout):
        return DummyResponse(200, {"data": {}})

    monkeypatch.setattr("api.external.abuseipdb.requests.request", fake_request)

    abuse = AbuseIPDB()
    abuse.ip = "9.9.9.9"
    abuse.key = "KEY123"
    abuse.show = True  # we want to see the print

    res = abuse.api_check()

    assert res["status"] is AbuseIPDBStatusReturn.WARNING
    assert res["status_code"] == 200
    assert res["data"] == {}
    assert "No data returned from AbuseIPDB" in res["error_message"]

    out = capsys.readouterr().out
    assert "[Warning] AbuseIPDB returned no data for 9.9.9.9" in out



# --- Flow status != 200 with errors ---

def test_api_check_non_200_with_errors(monkeypatch, capsys):
    """HTTP status != 200 with error list -> ERROR, keeps details."""
    def fake_request(method, url, headers, params, timeout):
        return DummyResponse(
            422,
            {
                "errors": [
                    {
                        "detail": "The ip address field is required.",
                        "status": 422,
                    }
                ]
            },
        )

    monkeypatch.setattr("api.external.abuseipdb.requests.request", fake_request)

    abuse = AbuseIPDB()
    abuse.ip = "8.8.8.8"
    abuse.key = "KEY123"
    abuse.show = True

    res = abuse.api_check()

    assert res["status"] is AbuseIPDBStatusReturn.ERROR
    assert res["status_code"] == 422
    assert "AbuseIPDB request failed" in res["error_message"]
    # The detail must have been concatenated
    assert "The ip address field is required." in res["error_message"]
    assert len(res["errors"]) == 1

    out = capsys.readouterr().out
    assert "[Error] AbuseIPDB request for 8.8.8.8: 422" in out
    assert "The ip address field is required." in out



# --- Errors of the network / JSON / unexpected ---

def test_api_check_network_error(monkeypatch, capsys):
    """requests.RequestException -> code -3 and error message."""
    def fake_request(*args, **kwargs):
        raise requests.RequestException("timeout")

    monkeypatch.setattr("api.external.abuseipdb.requests.request", fake_request)

    abuse = AbuseIPDB()
    abuse.ip = "1.1.1.1"
    abuse.key = "KEY123"
    abuse.show = True

    res = abuse.api_check()

    assert res["status"] is AbuseIPDBStatusReturn.ERROR
    assert res["status_code"] == -3
    assert "Network error calling AbuseIPDB" in res["error_message"]

    out = capsys.readouterr().out
    assert "request exception for 1.1.1.1" in out


def test_api_check_json_error(monkeypatch, capsys):
    """json.JSONDecodeError -> code -4 and error message."""
    def fake_request(*_args, **_kwargs):
        return BadJsonResponse()

    monkeypatch.setattr("api.external.abuseipdb.requests.request", fake_request)

    abuse = AbuseIPDB()
    abuse.ip = "8.8.4.4"
    abuse.key = "KEY123"
    abuse.show = True

    res = abuse.api_check()

    assert res["status"] is AbuseIPDBStatusReturn.ERROR
    assert res["status_code"] == -4
    assert "Invalid JSON response from AbuseIPDB" in res["error_message"]

    out = capsys.readouterr().out
    assert "JSON decode error for 8.8.4.4" in out


def test_api_check_unexpected_error(monkeypatch, capsys):
    """ Exception generic -> code -5 and error message. """
    def fake_request(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("api.external.abuseipdb.requests.request", fake_request)

    abuse = AbuseIPDB()
    abuse.ip = "4.4.4.4"
    abuse.key = "KEY123"
    abuse.show = True

    res = abuse.api_check()

    assert res["status"] is AbuseIPDBStatusReturn.ERROR
    assert res["status_code"] == -5
    assert "Unexpected error calling AbuseIPDB" in res["error_message"]

    out = capsys.readouterr().out
    assert "unexpected error for 4.4.4.4" in out



# --- Static checks() for list of IPs ---

def test_checks_mixed_ips(monkeypatch):
    """checks() must process multiple IPs and respect format errors (-20)."""
    def fake_request(method, url, headers, params, timeout):
        # Always return 200 with a simple body
        return DummyResponse(200, {"data": {"abuseConfidenceScore": 0}})

    monkeypatch.setattr("api.external.abuseipdb.requests.request", fake_request)

    ips = ["8.8.8.8", "1.1.1.1", "not-an-ip"]
    results = AbuseIPDB.checks(ips, "KEY123", debug=False, show=False)

    assert len(results) == 3

    # First two valid IPs -> SUCCESS
    assert results[0]["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert results[1]["status"] is AbuseIPDBStatusReturn.SUCCESS

    # The third is an invalid IP -> ERROR -20
    assert results[2]["status"] is AbuseIPDBStatusReturn.ERROR
    assert results[2]["status_code"] == -20
    assert "Invalid IP address" in results[2]["error_message"]


# --- Debug Tests ---

def test_api_check_debug_serializes_enum(monkeypatch, capsys):
    """When debug=true, the result should be valid json and status should be string."""

    # Fake requests.request para no llamar a la API real
    def fake_request(method, url, headers, params, timeout):
        assert method == "GET"
        return DummyResponse(
            200,
            {
                "data": {
                    "abuseConfidenceScore": 0,
                    "totalReports": 0,
                }
            },
        )

    # patch requests.request in abuseipdb class
    monkeypatch.setattr("api.external.abuseipdb.requests.request", fake_request)

    abuse = AbuseIPDB()
    abuse.ip = "8.8.8.8"
    abuse.key = "DUMMY_KEY"
    abuse.debug = True
    abuse.show = False  # so that it doesn't mix error/warning messages

    result = abuse.api_check()

    # Check that the call was successful
    assert result["status"] == AbuseIPDBStatusReturn.SUCCESS
    assert result["status_code"] == 200

    # Capture debug output (stdout)
    out = capsys.readouterr().out.strip()
    assert out, "No output printed in debug mode"

    # must be valid JSON
    debug_obj = json.loads(out)

    # And the status must be a string, not an enum
    assert debug_obj["status"] == "SUCCESS"
    # For safety, ensure that the repr of the Enum does not appear
    assert "AbuseIPDBStatusReturn.SUCCESS" not in out
