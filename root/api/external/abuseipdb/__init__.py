#!/usr/bin/env python3
""" Utility functions for AbuseIPDB integration. """
from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

import requests

from logger import LogLevel, get_logger

from .exceptions import (AbuseIPDBConfigError, AbuseIPDBNetworkError,
                         AbuseIPDBRateLimitError, AbuseIPDBResponseError)

log = get_logger(__name__)

class AbuseIPDBResult(TypedDict, total=False):
    """ Structured result for AbuseIPDB checks. """
    status: "AbuseIPDBStatusReturn"
    status_code: int
    error_message: str
    data: dict[str, Any]
    errors: list[dict[str, Any]]

class AbuseIPDBStatusReturn(Enum):
    """ Status codes for AbuseIPDB results. """
    UNKNOWN = 0
    SUCCESS = 1
    ERROR   = 2
    WARNING = 3

@dataclass(frozen=False)
class AbuseIPDB:
    """
    AbuseIPDB API integration class.
    
    API Documentation: https://docs.abuseipdb.com/

    Results Example - 200 OK:
    {
        "data": {
            "ipAddress": "8.8.8.8",
            "isPublic": true,
            "ipVersion": 4,
            "isWhitelisted": true,
            "abuseConfidenceScore": 0,
            "countryCode": "US",
            "usageType": "Content Delivery Network",
            "isp": "Google LLC",
            "domain": "google.com",
            "hostnames": [
                "dns.google"
            ],
            "isTor": false,
            "totalReports": 171,
            "numDistinctUsers": 52,
            "lastReportedAt": "2025-11-10T03:35:49+00:00"
        }
    }

    Results Example - 422 Unprocessable Entity (invalid IP):
    {
        "errors": [
            {
                "detail": "The ip address field is required.",
                "status": 422,
                "source": {
                    "parameter": "ipAddress"
                }
            }
        ]
    }

    Result Example - 401 Unauthorized (invalid API key):
    {
        "errors": [
            {
                "detail": "Authentication failed. Your API key is either missing, incorrect, 
                           or revoked. Note: The APIv2 key differs from the APIv1 key.",
                "status": 401
            }
        ]
    }
    """
    _url : str = field(default="https://api.abuseipdb.com/api/v2/check")
    @property
    def url(self) -> str:
        """Get the AbuseIPDB API URL"""
        return self._url

    # ----- IP Address -----
    _ip : str = field(default="")
    @property
    def ip(self) -> str:
        """Get the IP address"""
        return self._ip

    @ip.setter
    def ip(self, value: str | None) -> None:
        """Set the IP address"""
        if value is None or value.strip() == "":
            self._ip = ""
            return

        value = value.strip()
        try:
            ipaddress.ip_address(value)
        except ValueError as ve:
            raise ValueError(f"Invalid IP address: {value}") from ve

        self._ip = value

    @property
    def is_ip_set(self) -> bool:
        """Check if the IP address is set"""
        return self._ip.strip() != ""


    # ----- API Key -----
    _key : str = field(default="")
    @property
    def key(self) -> str:
        """Get the API key"""
        return self._key

    @key.setter
    def key(self, value: str | None) -> None:
        """Set the API key"""
        if value is None:
            value = ""

        self._key = value.strip()

    @property
    def is_key_set(self) -> bool:
        """Check if the API key is set"""
        return self._key.strip() != ""


    # ----- Timeout -----
    _timeout: int = field(default=10)
    @property
    def timeout(self) -> int:
        """Get the timeout value"""
        return self._timeout

    @timeout.setter
    def timeout(self, value: int) -> None:
        """Set the timeout value"""
        self._timeout = value


    # ----- Max Age In Days -----
    _max_age_in_days: int = field(default=90)
    @property
    def max_age_in_days(self) -> int:
        """Get the max age in days"""
        return self._max_age_in_days

    @max_age_in_days.setter
    def max_age_in_days(self, value: int) -> None:
        """Set the max age in days"""
        if value < 1 or value > 365:
            raise ValueError("max_age_in_days must be between 1 and 365")

        self._max_age_in_days = value


    # ----- Verbose -----
    _verbose: bool = field(default=False)
    @property
    def verbose(self) -> bool:
        """Get the verbose flag"""
        return self._verbose

    @verbose.setter
    def verbose(self, value: bool) -> None:
        """Set the verbose flag"""
        self._verbose = value


    # ----- Last Result -----
    _last_result: AbuseIPDBResult = field(default_factory=dict)
    @property
    def last_result(self) -> AbuseIPDBResult:
        """Get the last result"""
        return self._last_result


    # ----- base result -----
    def _base_result(self) -> AbuseIPDBResult:
        """Create a base result structure"""
        return {
            'status': AbuseIPDBStatusReturn.UNKNOWN,
            'status_code': 0,
            'error_message': '',
            'data': {},
            'errors': []
        }

    def base_result(self, status: AbuseIPDBStatusReturn | None = None) -> AbuseIPDBResult:
        """Get a base result structure"""
        base = self._base_result()
        if status is not None:
            base['status'] = status
        return base


    # ---- Check Method -----
    def api_check(self) -> AbuseIPDBResult:
        """ 
        Check the IP address against AbuseIPDB.

        Returns:
            AbuseIPDBResult: Structured result with status, codes, data and errors.
                             Only SUCCESS and WARNING statuses are returned here;
                             ERROR status is raised as exceptions.

        Raises:
            AbuseIPDBConfigError: Missing configuration (API key, IP address).
            AbuseIPDBNetworkError: Error during network request (timeout, DNS, etc.).
            AbuseIPDBResponseError: Invalid response from API (HTTP error, invalid JSON, etc.).
        """
        result : AbuseIPDBResult = self.base_result()

        if not self.is_key_set:
            raise AbuseIPDBConfigError("AbuseIPDB API key is required")

        if not self.is_ip_set:
            raise AbuseIPDBConfigError("IP address is required")

        response: requests.Response | None = None
        try:
            response = requests.request(
                method = 'GET',
                url = self.url,
                headers ={
                    'Accept': 'application/json',
                    'Key': self.key
                },
                params = {
                    'ipAddress': self.ip,
                    'maxAgeInDays': str(self.max_age_in_days),
                    # Only include if verbose is True
                    **({'verbose': ''} if self.verbose else {})
                },
                timeout = self.timeout
            )

        except requests.RequestException as re:
            log.exception("AbuseIPDB request exception for %s", self.ip)
            raise AbuseIPDBNetworkError("Network error calling AbuseIPDB", original=re) from re

        response_json: dict[str, Any] = {}
        try:
            response_json = response.json()

        except json.JSONDecodeError as je:
            log.exception("AbuseIPDB JSON decode error for %s", self.ip)
            raise AbuseIPDBResponseError(
                "Invalid JSON response from AbuseIPDB",
                status_code=response.status_code,
            ) from je

        errors = response_json.get("errors", []) or []
        data = response_json.get("data", {}) or {}


        match response.status_code:
            case 200:
                # status_code == 200 → SUCCESS or WARNING
                result: AbuseIPDBResult = self.base_result(AbuseIPDBStatusReturn.SUCCESS)
                result["status_code"] = response.status_code
                result["data"] = data
                result["errors"] = errors

            case 429:
                err_msg = errors[0].get("detail", "Unknown detail") if errors else "Unknown error"
                raise AbuseIPDBRateLimitError(
                    err_msg,
                    response=response,
                    api_errors=errors,
                )

            case _:
                log.error("AbuseIPDB request for %s: %s", self.ip, response.status_code)
                for err in errors:
                    detail = err.get("detail", "No detail provided")
                    log.error("  [AbuseIPDB Error] %s", detail)

                raise AbuseIPDBResponseError(
                    "AbuseIPDB request failed",
                    status_code=response.status_code,
                    api_errors=errors,
                )

        if not data:
            result["status"] = AbuseIPDBStatusReturn.WARNING
            result["error_message"] = "No data returned from AbuseIPDB"
            log.warning("AbuseIPDB returned no data for %s", self.ip)

        if log.isEnabledFor(LogLevel.DEBUG.value):
            debug_result = dict(result)
            status = debug_result.get("status")

            if isinstance(status, AbuseIPDBStatusReturn):
                debug_result["status"] = status.name

            log.debug(
                "AbuseIPDB result for %s: %s",
                self.ip,
                json.dumps(debug_result, indent=4, sort_keys=True)
            )

        self._last_result = result
        return result


    @staticmethod
    def check(ip: str, key: str) -> AbuseIPDBResult:
        """
        Static method to check an IP address against AbuseIPDB.
        Args:
            ip (str): The IP address to check.
            key (str): The API key for AbuseIPDB.
        Returns:
            AbuseIPDBResult: Structured result with status, codes, data and errors.

            Error Codes:
            -1  : Configuration error (missing API key, missing IP, etc.)
            -2  : Network error during request
            -3  : API response error (HTTP error, invalid JSON, etc.)
            -20 : Invalid IP address format
        """
        abuseipdb = AbuseIPDB()
        abuseipdb.key = key

        try:
            abuseipdb.ip = ip
        except ValueError as ve:
            base = abuseipdb.base_result(AbuseIPDBStatusReturn.ERROR)
            base['status_code'] = -20
            base['error_message'] = str(ve)
            return base

        try:
            return abuseipdb.api_check()

        except AbuseIPDBConfigError as e:
            base = abuseipdb.base_result(AbuseIPDBStatusReturn.ERROR)
            base["status_code"] = -1
            base["error_message"] = str(e)
            return base

        except AbuseIPDBNetworkError as e:
            base = abuseipdb.base_result(AbuseIPDBStatusReturn.ERROR)
            base["status_code"] = -2
            base["error_message"] = str(e)
            return base

        except AbuseIPDBResponseError as e:
            base = abuseipdb.base_result(AbuseIPDBStatusReturn.ERROR)
            base["status_code"] = e.status_code or -3
            base["error_message"] = str(e)
            base["errors"] = e.api_errors
            return base

    @staticmethod
    def checks(ips: list[str], key: str) -> list[AbuseIPDBResult]:
        """
        Static method to check multiple IP addresses against AbuseIPDB.
        Args:
            ips (list[str]): The list of IP addresses to check.
            key (str): The API key for AbuseIPDB.
        Returns:
            list[AbuseIPDBResult]: List of structured results for each IP.

            Error Codes:
            -1  : Configuration error (missing API key, missing IP, etc.)
            -2  : Network error during request
            -3  : API response error (HTTP error, invalid JSON, etc.)
            -20 : Invalid IP address format
        """
        results: list[AbuseIPDBResult] = []
        for ip in ips:
            result = AbuseIPDB.check(ip, key)
            results.append(result)
        return results
