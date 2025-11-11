#!/usr/bin/env python3
"""Custom exceptions for AbuseIPDB integration."""

from __future__ import annotations
from typing import Any

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
