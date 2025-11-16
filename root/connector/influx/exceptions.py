#!/usr/bin/env python3
""" InfluxDB v2 client wrapper """
from __future__ import annotations

class InfluxClientError(Exception):
    """Base class for all InfluxClient-related errors."""

class InfluxClientConfigError(InfluxClientError):
    """Configuration error (missing URL, org, token, etc.)."""

class InfluxClientInitError(InfluxClientError):
    """Initialization error (client creation failed, etc.)."""

class InfluxClientConnectionError(InfluxClientError):
    """Connection error (unable to connect to InfluxDB)."""
    def __init__(
        self,
        message: str,
        *,
        url: str | None = None,
        org: str | None = None,
        bucket: str | None = None,
        original_exc: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.url = url
        self.org = org
        self.bucket = bucket
        self.original_exc = original_exc

    def __str__(self) -> str:
        base = super().__str__()
        ctx = []

        if self.url:
            ctx.append(f"url={self.url}")
        if self.org:
            ctx.append(f"org={self.org}")
        if self.bucket:
            ctx.append(f"bucket={self.bucket}")
        if self.original_exc:
            ctx.append(f"cause={type(self.original_exc).__name__}: {self.original_exc}")

        if ctx:
            return f"{base} ({', '.join(ctx)})"
        return base
