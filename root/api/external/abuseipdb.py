#!/usr/bin/env python3
""" Utility functions for AbuseIPDB integration. """
from __future__ import annotations
import json
import ipaddress
from dataclasses import dataclass, field
from enum import Enum
from typing import TypedDict, Any
import requests

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


    # ----- Debug -----
    _debug: bool = field(default=False)
    @property
    def debug(self) -> bool:
        """Get the debug flag"""
        return self._debug

    @debug.setter
    def debug(self, value: bool) -> None:
        """Set the debug flag"""
        self._debug = value


    # ----- Show -----
    _show: bool = field(default=True)
    @property
    def show(self) -> bool:
        """Get the show flag"""
        return self._show

    @show.setter
    def show(self, value: bool) -> None:
        """Set the show flag"""
        self._show = value


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

            Error Codes:
            -1 : API key is missing
            -2 : IP address is missing
            -3 : Network error during request
            -4 : JSON decode error during request
            -5 : Unexpected error during request
        """
        result : AbuseIPDBResult = self.base_result()

        if not self.is_key_set:
            result['status'] = AbuseIPDBStatusReturn.ERROR
            result['status_code'] = -1
            result['error_message'] = 'AbuseIPDB API key is required'

        elif not self.is_ip_set:
            result['status'] = AbuseIPDBStatusReturn.ERROR
            result['status_code'] = -2
            result['error_message'] = 'IP address is required'

        response: requests.Response | None = None
        response_json: dict[str, Any] = {}
        if result['status'] != AbuseIPDBStatusReturn.ERROR:
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
                response_json = response.json()

            except requests.RequestException as re:
                result['status'] = AbuseIPDBStatusReturn.ERROR
                result['status_code'] = -3
                result['error_message'] = f"Network error calling AbuseIPDB: {re}"
                if self.show:
                    print(
                        f"[Error] AbuseIPDB request exception for {self.ip}: {str(re)}",
                        flush=True
                    )

            except json.JSONDecodeError as je:
                result['status'] = AbuseIPDBStatusReturn.ERROR
                result['status_code'] = -4
                result['error_message'] = f"Invalid JSON response from AbuseIPDB: {je}"
                if self.show:
                    print(
                        f"[Error] AbuseIPDB JSON decode error for {self.ip}: {str(je)}",
                        flush=True
                    )

            except Exception as e: # pylint: disable=broad-except
                result['status'] = AbuseIPDBStatusReturn.ERROR
                result['status_code'] = -5
                result['error_message'] = f"Unexpected error calling AbuseIPDB: {e}"
                if self.show:
                    print(
                        f"[Error] AbuseIPDB unexpected error for {self.ip}: {str(e)}",
                        flush=True
                    )

        if result['status'] != AbuseIPDBStatusReturn.ERROR and response is not None:
            result['status_code'] = response.status_code
            result['errors'] = response_json.get("errors", []) or []
            result['data'] = response_json.get("data", {}) or {}

            if response.status_code == 200:
                result['status'] = AbuseIPDBStatusReturn.SUCCESS

                if not result["data"]:
                    result['status'] = AbuseIPDBStatusReturn.WARNING
                    result['error_message'] = 'No data returned from AbuseIPDB'
                    if self.show:
                        print(f"[Warning] AbuseIPDB returned no data for {self.ip}", flush=True)

            else:
                result['status'] = AbuseIPDBStatusReturn.ERROR
                result['error_message'] = 'AbuseIPDB request failed'
                if self.show:
                    print(
                        f"[Error] AbuseIPDB request for {self.ip}: {response.status_code}",
                        flush=True
                    )

                for error in result["errors"]:
                    err_detail = error.get("detail", "No detail provided")
                    err_status = error.get("status", "Unknown")
                    result['error_message'] += f" (Status {err_status}: {err_detail})"
                    if self.show:
                        print(f"  [AbuseIPDB Error] {err_detail}", flush=True)

        if self.debug:
            debug_result = {
                **result,
                "status": result["status"].name
                if isinstance(result["status"], AbuseIPDBStatusReturn)
                else result["status"]
            }
            print(json.dumps(debug_result, indent=4, sort_keys=True), flush=True)

        self._last_result = result
        return result

    @staticmethod
    def check(ip: str, key: str, debug: bool = False, show: bool = True) -> AbuseIPDBResult:
        """
        Static method to check an IP address against AbuseIPDB.
        Args:
            ip (str): The IP address to check.
            key (str): The API key for AbuseIPDB.
            debug (bool): Whether to print debug information.
            show (bool): Whether to print errors to stdout.
        Returns:
            AbuseIPDBResult: Structured result with status, codes, data and errors.

            Error Codes:
            -1  : API key is missing
            -2  : IP address is missing
            -3  : Network error during request
            -4  : JSON decode error during request
            -5  : Unexpected error during request
            -20 : Invalid IP address format
        """
        abuseipdb = AbuseIPDB()
        try:
            abuseipdb.ip = ip
        except ValueError as ve:
            base = abuseipdb.base_result(AbuseIPDBStatusReturn.ERROR)
            base['status_code'] = -20
            base['error_message'] = str(ve)
            return base

        abuseipdb.key = key
        abuseipdb.debug = debug
        abuseipdb.show = show
        return abuseipdb.api_check()

    @staticmethod
    def checks(
        ips: list[str], key: str, debug: bool = False, show: bool = True
    ) -> list[AbuseIPDBResult]:
        """
        Static method to check multiple IP addresses against AbuseIPDB.
        Args:
            ips (list[str]): The list of IP addresses to check.
            key (str): The API key for AbuseIPDB.
            debug (bool): Whether to print debug information.
            show (bool): Whether to print errors to stdout.
        Returns:
            list[AbuseIPDBResult]: List of structured results for each IP.

            Error Codes:
            -1  : API key is missing
            -2  : IP address is missing
            -3  : Network error during request
            -4  : JSON decode error during request
            -5  : Unexpected error during request
            -20 : Invalid IP address format
        """
        results: list[AbuseIPDBResult] = []
        for ip in ips:
            result = AbuseIPDB.check(ip, key, debug, show)
            results.append(result)
        return results
