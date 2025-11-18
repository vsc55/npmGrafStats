#!/usr/bin/env python3
""" Utility functions for npmGrafStats. """
from __future__ import annotations

import dataclasses
import ipaddress
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

TRUTHY = ("1", "true", "yes", "on")

def debug_msg(message: str):
    """ Print debug message if debug mode is enabled. """
    from config import cfg  # pylint: disable=import-outside-toplevel
    if cfg.debug:
        print(message, flush=True)


def format_time(oldtime: str) -> str | None:
    """
    Convert a timestamp from Apache/Nginx log format:
        '30/May/2023:14:16:48 +0000'
    to ISO 8601 format accepted by InfluxDB:
        '2023-05-30T14:16:48+00:00'

    Conversion details:
    - Day:    oldtime[0:2]          -> '30'
    - Month:  oldtime[3:6]          -> 'May' (mapped to '05')
    - Year:   oldtime[7:11]         -> '2023'
    - Time:   oldtime[12:20]        -> '14:16:48'
    - TZ:     oldtime[21:24] + ':' + oldtime[24:26] -> '+00:00'

    The output follows ISO 8601 / RFC3339 format, which is fully compatible
    with InfluxDBClient timestamps.
    """

    if oldtime is None or len(oldtime) < 26:
        debug_msg(f"Invalid time format: '{oldtime}'")
        return None

    month_map = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
        'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
        'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    year = oldtime[7:11].strip()
    month = month_map.get(oldtime[3:6].strip(), '01')
    day = oldtime[0:2].strip()
    datetime_part = oldtime[12:20].strip()
    tz_hour = oldtime[21:24].strip()
    tz_min = oldtime[24:26].strip()

    newtime = f"{year}-{month}-{day}T{datetime_part}{tz_hour}:{tz_min}"
    debug_msg(f"Transformed time from '{oldtime}' to '{newtime}'")

    return newtime


def is_ip_in_range(ip: str, list_entries: list[str]) -> bool:
    """
    Check if the given IP address matches any entry from a preloaded monitoring list.

    The entries in the list can be:
      - Single IP:           "192.168.1.10"
      - CIDR block:          "10.0.0.0/24"
      - Explicit IP range:   "10.0.0.1-10.0.0.20"
    Lines starting with '#' or empty strings should be filtered out beforehand,
    but the function will ignore them if still present.

    Example usage:
        >>> entries = [
        ...     "10.0.0.0/24",
        ...     "10.0.0.1-10.0.0.20",
        ...     "192.168.1.10"
        ... ]
        >>> is_ip_in_range("10.0.0.15", entries)
        True

    Args:
        ip (str): IP address to check.
        list_entries (list[str]): List of strings representing IPs, CIDRs, or ranges.

    Returns:
        bool: True if the IP matches any CIDR, range, or individual IP in the list.
    """
    if not ip:
        return False

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        debug_msg(f"[is_ip_in_range] Invalid IP address: {ip}")
        return False

    for entry in list_entries:
        entry = entry.split("#", 1)[0].strip()
        if not entry:
            continue

        # Case 1: explicit range (e.g., 10.0.0.1-10.0.0.20)
        if "-" in entry:
            try:
                start_str, end_str = entry.split("-", 1)
                start_ip = ipaddress.ip_address(start_str.strip())
                end_ip = ipaddress.ip_address(end_str.strip())
                if start_ip <= addr <= end_ip:
                    return True
            except ValueError:
                debug_msg(f"[is_ip_in_range] Invalid range entry: {entry}")
                continue

        # Case 2: CIDR or single IP
        else:
            try:
                network = ipaddress.ip_network(entry, strict=False)
                if addr in network:
                    return True
            except ValueError:
                debug_msg(f"[is_ip_in_range] Invalid network entry: {entry}")
                continue

    return False


def env_bool(name: str, default: bool = False) -> bool:
    """Get boolean value from environment variable."""
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    return str(val).lower() in TRUTHY


def env_int(name: str, default: int, min_value: Optional[int] = None) -> int:
    """Get integer value from environment variable, with optional minimum."""
    raw = os.getenv(name)
    raw = raw.strip() if raw is not None else None

    if raw is None or not re.fullmatch(r"-?\d+", raw):
        value = default
    else:
        value = int(raw)

    if min_value is not None and value < min_value:
        return min_value

    return value


def parse_float(value: str, default: float | None = None) -> float | None:
    """
    Tries to parse a string to float, returns None if fails.
    """
    try:
        return float(value)

    except (ValueError, TypeError):
        return default


class TypeRegex(str, Enum):
    """ Enumeration for regex types. """
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    IP = "ip"
    IP_PRIVATE = "ip_private"
    DOMAIN = "domain"

@dataclasses.dataclass
class Regex:
    """ Regex patterns for IP addresses. """
    @property
    def ipv4(self) -> str:
        """ Regex pattern for IPv4 addresses. """
        return r"([0-9]{1,3}\.){3}[0-9]{1,3}"

    @property
    def ipv6(self) -> str:
        """ Regex pattern for IPv6 addresses. """
        return (
            r"([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|"
            r"([0-9a-fA-F]{1,4}:){1,7}:|"
            r"([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|"
            r"([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|"
            r"([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|"
            r"([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|"
            r"([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|"
            r"[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|"
            r":((:[0-9a-fA-F]{1,4}){1,7}|:)|"
            r"fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|"
            r"::(ffff(:0{1,4}){0,1}:){0,1}"
            r"((25[0-5]|(2[0-4]|1[0-9]|[0-9])\.){3}(25[0-5]|(2[0-4]|1[0-9]|[0-9])))|"
            r"([0-9a-fA-F]{1,4}:){1,4}:"
            r"((25[0-5]|(2[0-4]|1[0-9]|[0-9])\.){3}(25[0-5]|(2[0-4]|1[0-9]|[0-9])))"
    )

    @property
    def ip(self) -> str:
        """ Combined IPv4 and IPv6 regex pattern. """
        return f"({self.ipv4}|{self.ipv6})"

    @property
    def ip_private(self) -> str:
        """ Regex pattern for private IP addresses. """
        return (
            # 10.0.0.0/8
            r"(10(?:\.[0-9]{1,3}){3})|"
            # 192.168.0.0/16
            r"(192\.168(?:\.[0-9]{1,3}){2})|"
            # 172.16.0.0–172.31.0.0
            r"(172\.(?:1[6-9]|2[0-9]|3[0-1])(?:\.[0-9]{1,3}){2})|"
            # Loopback
            r"(127(?:\.[0-9]{1,3}){3})|"
            # Link-local
            r"(169\.254(?:\.[0-9]{1,3}){2})|"
            # CGNAT 100.64–100.127
            r"(100\.(?:6[4-9]|[7-9][0-9]|1[0-1][0-9]|12[0-7])(?:\.[0-9]{1,3}){2})"
        )

    @property
    def domain(self) -> str:
        """
        Regex pattern for domain names. 
        E.g., example.com, sub.example.co.uk
        """
        return r"([a-z0-9\-]*\.){1,3}?[a-z0-9\-]*\.[A-Za-z]{2,6}"

    def search(self, text: str, typeregex: TypeRegex) -> Optional[re.Match]:
        """ Search for a regex pattern in the given text. """
        pattern = self.compile(typeregex)
        return pattern.search(text)

    def fullmatch(self, text: str, typeregex: TypeRegex) -> Optional[re.Match]:
        """ Fullmatch for a regex pattern in the given text. """
        pattern = self.compile(typeregex)
        return pattern.fullmatch(text)

    def compile(self, typeregex: TypeRegex) -> re.Pattern:
        """ Compile and return the regex pattern for the given type. """
        regex_pattern = getattr(self, typeregex.value, None)
        if regex_pattern is None:
            raise ValueError(f"Type of regex not valid: {typeregex}")

        return re.compile(regex_pattern)

    @staticmethod
    def search_type(line: str, typeregex: TypeRegex) -> Optional[re.Match]:
        """
        Static method to search for a regex pattern in the given line.
        """
        regex = Regex()
        return regex.search(line, typeregex)

    @staticmethod
    def compile_type(typeregex: TypeRegex) -> re.Pattern:
        """
        Static method to compile and return the regex pattern for the given type.
        """
        regex = Regex()
        return regex.compile(typeregex)

    @staticmethod
    def fullmatch_type(line: str, typeregex: TypeRegex) -> Optional[re.Match]:
        """
        Static method to fullmatch for a regex pattern in the given line.
        """
        regex = Regex()
        return regex.fullmatch(line, typeregex)
