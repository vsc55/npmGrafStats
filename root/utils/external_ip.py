#!/usr/bin/env python3
""" Utility module to get and cache the external IP address. """
import time
import urllib.error
from typing import Optional
from urllib.request import urlopen

from logger import get_logger

log = get_logger(__name__)

URLS = [
    "https://checkip.amazonaws.com",
    "https://ifconfig.me/ip",
    "https://api.ipify.org",
]

TIMEOUT_URLOPEN = 5  # seconds

class ExternalIP:
    """Class to manage external IP detection with caching and TTL."""
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ip: Optional[str] = None
        self._last_update: Optional[float] = None  # epoch time
        self._ttl = ttl_seconds

    def _detect_external_ip(self) -> Optional[str]:
        last_err: Exception | None = None
        for url in URLS:
            try:
                with urlopen(url, timeout=TIMEOUT_URLOPEN) as r:
                    ip = r.read().decode("utf-8").strip()
                    if ip:
                        log.debug("Detected external IP from %s: %s", url, ip)
                        return ip

            except TimeoutError as e:
                last_err = e
                log.warning("External IP timeout (%s seconds) via %s", TIMEOUT_URLOPEN, url)

            except urllib.error.URLError as e:
                last_err = e
                log.warning("External IP failed via %s: %r", url, e)

        if last_err:
            raise last_err
        return None

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
