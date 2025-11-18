#!/usr/bin/env python3
""" Utility module to get and cache the external IP address. """
import time
from typing import Optional
from urllib.request import urlopen


class ExternalIP:
    """Class to manage external IP detection with caching and TTL."""
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ip: Optional[str] = None
        self._last_update: Optional[float] = None  # epoch time
        self._ttl = ttl_seconds

    def _detect_external_ip(self) -> Optional[str]:
        try:
            with urlopen("https://ifconfig.me/ip", timeout=5) as response:
                ip = response.read().decode("utf-8").strip()
                return ip or None

        except Exception as e:
            raise ValueError("Error detecting external IP") from e

    def _needs_refresh(self) -> bool:
        if self._ip is None or self._last_update is None:
            return True
        return (time.time() - self._last_update) > self._ttl

    def get_ip(self, force: bool = False) -> Optional[str]:
        """
        - if not ip is cached → fetch it.
        - If ip is cached and TTL has not expired → return cached.
        - If TTL has expired or force=True → fetch it.
        """
        if force or self._needs_refresh():
            ip = self._detect_external_ip()
            if ip is not None:
                self._ip = ip
                self._last_update = time.time()
        return self._ip
