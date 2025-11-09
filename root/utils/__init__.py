#!/usr/bin/env python3
""" Utility functions for npmGrafStats. """
from __future__ import annotations
from typing import Any
from typing import TYPE_CHECKING
import ipaddress

def debug_msg(message: str):
    """ Print debug message if debug mode is enabled. """
    from config import cfg # pylint: disable=import-outside-toplevel
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
