#!/usr/bin/env python3
"""Handlers for mod_example log lines."""
from __future__ import annotations

from typing import List
from config import GlobalConfig
from utils import debug_msg, format_time, TypeRegex, Regex
from connector.influx import InfluxRecord

def _extract_ip(line: str) -> str | None:
    m = Regex.search_type(line, TypeRegex.IP)
    return m.group(0) if m else None

def _extract_measurement_time(line: str) -> str:
    raw = line[1:27] if len(line) > 27 else ""
    return format_time(raw) or ""

def handle_line(line: str, env: str, config: GlobalConfig) -> List[InfluxRecord]:
    """
    Procesa una línea de logs de mod_example y devuelve
    una lista de InfluxRecord para escribir.
    """

    records: list[InfluxRecord] = []

    if config.debug:
        debug_msg(f"[mod_example] Processing line: {line.strip()}")

    env = env.lower()
    if env not in {"production", "staging"}:
        debug_msg(f"[mod_example] Unsupported environment: {env}")
        return records

    ip = _extract_ip(line)
    if not ip:
        debug_msg("[mod_example] No IP found in line")
        return records

    ts = _extract_measurement_time(line)

    tags = {
        "IP": ip,
    }
    fields = {
        "IP": ip,
        "metric": 1,
    }

    records.append(
        InfluxRecord(
            measurement="mod_exampleConnections",
            tags=tags,
            fields=fields,
            timestamp=ts,
        )
    )

    return records
