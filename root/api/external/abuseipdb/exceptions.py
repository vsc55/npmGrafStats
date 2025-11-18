#!/usr/bin/env python3
"""Custom exceptions for AbuseIPDB integration."""

from __future__ import annotations
from typing import Any
import requests

class AbuseIPDBError(Exception):
    """Base class for all AbuseIPDB-related errors."""


class AbuseIPDBConfigError(AbuseIPDBError):
    """Configuration error (missing API key, missing IP, invalid IP, etc.)."""


class AbuseIPDBNetworkError(AbuseIPDBError):
    """Network-level errors when calling AbuseIPDB (timeout, DNS, etc.)."""

    def __init__(self, message: str, *, original: Exception | None = None) -> None:
        super().__init__(message)
        self.original = original


class AbuseIPDBResponseError(AbuseIPDBError):
    """
    API responded but with an error (HTTP != 200, invalid JSON, or API-level error).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        api_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.api_errors = api_errors or []


class AbuseIPDBRateLimitError(AbuseIPDBError):
    """Specific error for HTTP 429 Too Many Requests (rate limiting)."""

    def __init__(
        self,
        message: str,
        response: requests.Response | None = None,
        api_errors: list | None = None,
    ):
        super().__init__(message)
        self.status_code = response.status_code if response else None
        self.api_errors = api_errors or []

        # headers = getattr(response, "headers", {}) or {}

        # self.rate_limit = {
        #     "retry_after": int(headers.get("Retry-After", 0) or 0),
        #     "limit": int(headers.get("X-RateLimit-Limit", 0) or 0),
        #     "remaining": int(headers.get("X-RateLimit-Remaining", 0) or 0),
        #     "reset": int(headers.get("X-RateLimit-Reset", 0) or 0),
        # }

        # # Human-readable reset time
        # self.reset_human = (
        #     datetime.fromtimestamp(self.rate_limit["reset"]).isoformat()
        #     if self.rate_limit["reset"]
        #     else "unknown"
        # )

    # def __str__(self) -> str:
    #     # rl = self.rate_limit
    #     # base = super().__str__()
    #     # return (
    #     #     f"{base} "
    #     #     f"(limit={rl['limit']}, remaining={rl['remaining']}, "
    #     #     f"retry_after={rl['retry_after']}, reset={self.reset_human})"
    #     # )
    #     base = super().__str__()
    #     return base
