#!/usr/bin/env python3
"""Custom exceptions for GeoIP2 integration."""
from __future__ import annotations

class GeoIP2Error(Exception):
    """Base class for all GeoIP2-related errors."""

class GeoIP2PathDBError(GeoIP2Error):
    """Database path error (missing DB file, invalid path, etc.)."""
    def __init__(self, message, path):
        super().__init__(message)
        self.path = path

class GeoIP2ConfigError(GeoIP2Error):
    """Configuration error (missing IP, invalid IP, etc.)."""
    def __init__(self, message, key, val):
        super().__init__(message)
        self.error_key = key
        self.error_value = val
