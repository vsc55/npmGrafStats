#!/usr/bin/env python3
""" Utility functions for AbuseIPDB integration. """
from __future__ import annotations

import ipaddress
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TypedDict

import requests

from logger import LogLevel, get_logger

from .exceptions import (AbuseIPDBConfigError, AbuseIPDBNetworkError,
                         AbuseIPDBRateLimitError, AbuseIPDBResponseError)

if sys.platform != "win32":
    import fcntl
else:
    fcntl = None


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

    def __post_init__(self):
        self.cache_path = os.environ.get(
            "ABUSEIP_CACHE_FILE",
            self._cache_path or "/data/abuseipdb_cache.json"
        )

        # Set cache expiration from environment or default
        # Is necessary to avoid garbage coming from environment like for example "280  #Comment"
        default_expire = 2880  # 48 hours
        raw = os.environ.get("ABUSEIP_CACHE_EXPIRE", str(self._cache_expire or default_expire))
        try:
            self.cache_expire = int(raw)
        except ValueError:
            log.warning("Invalid ABUSEIP_CACHE_EXPIRE=%r, using default %d", raw, default_expire)
            self.cache_expire = default_expire

        self.load_cache()

    def close(self) -> None:
        """ Close the AbuseIPDB instance and save cache. """
        self.save_cache()

    def __enter__(self):
        """ Support for With statement context management. """
        return self

    def __exit__(self, exc_type, exc, tb):
        """ Support for With statement context management. """
        self.save_cache()


    # ----- Cache -----
    _cache_data: dict[str, Any] = field(default_factory=dict)
    @property
    def cache_data(self) -> dict[str, Any]:
        """Get the cache data"""
        return self._cache_data

    @cache_data.setter
    def cache_data(self, value: dict[str, Any]) -> None:
        """Set the cache data"""
        self._cache_data = value

    _cache_expire: int | None = None
    @property
    def cache_expire(self) -> int | None:
        """Get the cache expiration time in minutes"""
        return self._cache_expire

    @cache_expire.setter
    def cache_expire(self, value: int | None) -> None:
        """Set the cache expiration time in minutes"""
        self._cache_expire = value

    @property
    def is_cache_expire_set(self) -> bool:
        """Check if the cache expiration is set"""
        return self._cache_expire is not None and self._cache_expire > 0

    _cache_path: str | None = None
    @property
    def cache_path(self) -> str | None:
        """Get the cache file path"""
        if self._cache_path is None:
            return None

        base = Path(__file__).resolve().parent.parent.parent.parent
        path = self._cache_path.replace("{workdir}", str(base))
        return str(Path(path))

    @cache_path.setter
    def cache_path(self, value: str | None) -> None:
        """Set the cache file path"""
        if value is not None:
            value = value.strip()
        self._cache_path = value

    @property
    def is_cache_set(self) -> bool:
        """Check if the cache path is set"""
        path = self.cache_path
        return path is not None and path.strip() != ""

    @property
    def is_cache_exist(self) -> bool:
        """Check if the cache file exists"""
        return self.is_cache_set and os.path.isfile(self.cache_path)

    @property
    def is_cache_active(self) -> bool:
        """Check if the cache is active (path set and expiration > 0)"""
        return self.is_cache_set and self.is_cache_expire_set


    # ----- API URL -----
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

    # ----- Cache Methods -----
    def clear_cache(self) -> bool:
        """
        Clear the AbuseIPDB cache.
        If is_cache_set is False, only clears in-memory cache.
        If the exception occurs during file operations, returns and not cleans the in-memory cache.
        """
        if self.is_cache_set is False:
            log.warning("AbuseIPDB cache path is not set; cannot clean cache file, only memory.")
        else:
            try:
                with open(self.cache_path, 'w', encoding='utf-8') as cache_file:
                    if fcntl:
                        fcntl.flock(cache_file.fileno(), fcntl.LOCK_EX)
                    json.dump({}, cache_file)
                    if fcntl:
                        fcntl.flock(cache_file.fileno(), fcntl.LOCK_UN)

            except Exception: # pylint: disable=broad-except
                log.exception("Failed to clear AbuseIPDB cache at %s", self.cache_path)
                return False

        self.cache_data = {}
        log.debug("AbuseIPDB cache cleared at %s", self.cache_path)
        return True

    def load_cache(self) -> dict[str, Any] | None:
        """ Load the AbuseIPDB cache from file. """
        if self.is_cache_set is False:
            log.warning("AbuseIPDB cache path is not set; cannot load cache.")

        elif self.is_cache_exist is False:
            log.warning("AbuseIPDB cache file does not exist at %s", self.cache_path)

        else:
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as cache_file:
                    if fcntl:
                        fcntl.flock(cache_file.fileno(), fcntl.LOCK_SH)
                    cache_data = json.load(cache_file)
                    if fcntl:
                        fcntl.flock(cache_file.fileno(), fcntl.LOCK_UN)

                log.debug("AbuseIPDB cache loaded from %s", self.cache_path)
                self.cache_data = cache_data
                return cache_data

            except FileNotFoundError:
                log.warning("AbuseIPDB cache file not found at %s", self.cache_path)

            except (json.JSONDecodeError, IOError, OSError):
                log.exception("Failed to load AbuseIPDB cache from %s", self.cache_path)

                p = Path(self.cache_path)
                p_error = p.parent / (p.name + ".err-" + datetime.now().strftime("%Y%m%d%H%M%S%f"))
                try:
                    os.rename(p, p_error)
                    log.info("Renamed corrupt cache file to %s", p_error)

                except OSError:
                    log.exception("Failed to rename corrupt cache file '%s' to '%s'", p, p_error)

                except Exception: # pylint: disable=broad-except
                    log.exception(
                        "Unexpected error renaming corrupt cache file '%s' to '%s'",
                        p, p_error
                    )

        self.cache_data = {}
        return {}

    def save_cache(self, cache_data: Optional[dict[str, Any]] = None) -> bool:
        """ Save the AbuseIPDB cache to file. """

        # if self.cache_path == r"\data\abuseipdb_cache.json":
        #     log.error(
        #         "DEBUG: save_cache con ruta por defecto llamado desde:\n%s",
        #         "".join(traceback.format_stack(limit=10)),
        #     )

        if self.is_cache_set is False:
            log.warning("AbuseIPDB cache path is not set; cannot save cache.")
            return False

        if cache_data is None:
            cache_data = self.cache_data

        if cache_data is None:
            log.warning("AbuseIPDB cache data is None; cannot save cache.")
            return False

        try:
            with open(self.cache_path, 'w', encoding='utf-8') as cache_file:
                if fcntl:
                    fcntl.flock(cache_file.fileno(), fcntl.LOCK_EX)
                json.dump(cache_data, cache_file, indent=4)
                if fcntl:
                    fcntl.flock(cache_file.fileno(), fcntl.LOCK_UN)

            log.debug("AbuseIPDB cache saved to %s", self.cache_path)
            return True

        except (IOError, OSError):
            log.exception("Error saving cache to '%s'", self.cache_path)

        except Exception: # pylint: disable=broad-except
            log.exception("Unexpected error saving cache to '%s'", self.cache_path)

        return False

    def add_to_cache(
            self,
            data: Any,
            ip_address: str | None = None,
            force_save: bool = False
    ) -> bool:
        """ Add data to the AbuseIPDB cache. """
        if not self.is_cache_active:
            log.info("AbuseIPDB cache is not active; cannot add to cache.")
            return False

        if ip_address is None:
            ip_address = self.ip

        if ip_address is None or ip_address.strip() == "":
            log.warning("AbuseIPDB cache add requested with empty IP address")
            return False

        current_time = time.time()
        self.cache_data[ip_address] = {
            'timestamp': current_time,
            'data': data
        }

        if force_save:
            self.save_cache()

        return True

    def get_from_cache(
            self,
            current_time: float | None = None,
            ip_address: str | None = None,
            force_load: bool = False,
            force_save: bool = False
    ) -> Any | None:
        """ Retrieve data from the AbuseIPDB cache if valid. """
        if not self.is_cache_active:
            log.info("AbuseIPDB cache is not active")
            return None

        if not self.cache_data:
            log.info("AbuseIPDB cache is empty")
            return None

        if ip_address is None:
            ip_address = self.ip

        if ip_address is None or ip_address.strip() == "":
            log.warning("AbuseIPDB cache requested with empty IP address")
            return None

        if force_load:
            self.load_cache()

        entry = self.cache_data.get(ip_address)
        if not entry:
            log.debug("AbuseIPDB cache entry for IP %s not found", ip_address)
            return None

        entry_time = entry.get("timestamp", 0)
        if entry_time is None:
            log.warning("AbuseIPDB cache entry for IP %s has no timestamp", ip_address)
            return None

        assert self.cache_expire is not None
        if current_time is None:
            current_time = time.time()

        if current_time - entry_time >= self.cache_expire * 60:
            log.debug("AbuseIPDB cache expired for IP: %s", ip_address)
            self.del_from_cache(ip_address, force_save=force_save)
            return None

        data = entry.get("data", None)
        if data is None:
            log.warning("AbuseIPDB cache entry for %s has no data", ip_address)
            return None

        for need in ['abuseConfidenceScore', 'totalReports']:
            if need not in data:
                log.warning("AbuseIPDB cache entry for %s missing '%s'", ip_address, need)
                return None

        return data

    def del_from_cache(
            self,
            ip_address: str | None = None,
            force_save: bool = False
    ) -> bool:
        """ Delete data from the AbuseIPDB cache. """
        if not self.is_cache_active:
            log.info("AbuseIPDB cache is not active; cannot delete from cache.")
            return False

        if ip_address is None:
            ip_address = self.ip

        if ip_address is None or ip_address.strip() == "":
            log.warning("AbuseIPDB cache delete requested with empty IP address")
            return False

        if ip_address in self.cache_data:
            del self.cache_data[ip_address]
            log.info("AbuseIPDB cache entry for IP %s deleted", ip_address)

            if force_save:
                self.save_cache()

            return True

        log.info("AbuseIPDB cache entry for IP %s not found; nothing to delete", ip_address)
        return True

    # ---- Check Method -----
    def api_check(self, force_load: bool = False, force_save: bool = False) -> AbuseIPDBResult:
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

        data_cache = self.get_from_cache(force_load=force_load)
        if data_cache is not None:
            log.debug("AbuseIPDB cache HIT for IP: %s", self.ip)
            result: AbuseIPDBResult = self.base_result(AbuseIPDBStatusReturn.SUCCESS)
            result["status_code"] = 200
            result["data"] = data_cache
            result["errors"] = []
            return result

        log.debug("AbuseIPDB cache MISS for IP: %s", self.ip)
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
            # Launch exception for HTTP error codes
            # response.raise_for_status()

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
                self.add_to_cache(data, force_save=force_save)

            case 429:
                err_msg = errors[0].get("detail", "Unknown detail") if errors else "Unknown error"
                raise AbuseIPDBRateLimitError(err_msg, response=response, api_errors=errors)

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
        with AbuseIPDB() as abuse:
            abuse.key = key

            for ip in ips:
                try:
                    abuse.ip = ip
                except ValueError as ve:
                    base = abuse.base_result(AbuseIPDBStatusReturn.ERROR)
                    base['status_code'] = -20
                    base['error_message'] = str(ve)
                    results.append(base)
                    continue

                try:
                    results.append(abuse.api_check())

                except AbuseIPDBConfigError as e:
                    base = abuse.base_result(AbuseIPDBStatusReturn.ERROR)
                    base["status_code"] = -1
                    base["error_message"] = str(e)
                    results.append(base)

                except AbuseIPDBNetworkError as e:
                    base = abuse.base_result(AbuseIPDBStatusReturn.ERROR)
                    base["status_code"] = -2
                    base["error_message"] = str(e)
                    results.append(base)

                except AbuseIPDBResponseError as e:
                    base = abuse.base_result(AbuseIPDBStatusReturn.ERROR)
                    base["status_code"] = e.status_code or -3
                    base["error_message"] = str(e)
                    base["errors"] = e.api_errors
                    results.append(base)

        return results

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
            -30 : No result returned from AbuseIPDB check
        """
        results: list[AbuseIPDBResult] = AbuseIPDB.checks([ip], key)
        if not results:
            return {
                'status': AbuseIPDBStatusReturn.ERROR,
                'status_code': -30,
                'error_message': 'No result returned from AbuseIPDB check',
                'data': {},
                'errors': []
            }

        return results[0]
