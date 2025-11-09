#!/usr/bin/env python3
""" Module to send data to InfluxDB. """
from __future__ import annotations
from typing import Mapping, Any
from contextlib import contextmanager
from dataclasses import dataclass
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from config import cfg
from utils import debug_msg

@dataclass(frozen=True)
class InfluxRecord:
    """Single point to write into InfluxDB."""
    measurement: str
    tags: dict[str, str]
    fields: dict[str, object]
    timestamp: str | None = None

class InfluxClient:
    """Client to send data to InfluxDB."""

    def __init__(self) -> None:
        self._client: influxdb_client.InfluxDBClient | None = None
        self._write_api = None

    def _ensure_client(self) -> None:
        """Create the InfluxDB client if not already created."""
        if self._client is not None:
            return

        host = cfg.influxdb["host"] or ""
        org = cfg.influxdb["org"] or ""
        token = cfg.influxdb["token"] or ""

        if not all([host, org, token]):
            debug_msg("InfluxDB configuration is incomplete. Client not created.")
            return

        self._client = influxdb_client.InfluxDBClient(
            url=host,
            token=token,
            org=org,
        )
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

    @contextmanager
    def client(self) -> Any:
        """Context manager for InfluxDB client."""
        self._ensure_client()
        try:
            yield self._client
        finally:
            # No close the conexion, to keep connection alive - reuse
            pass

    def write_point(
        self,
        measurement: str,
        tags: Mapping[str, str] | None = None,
        fields: Mapping[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> None:
        """
        Write a single point to InfluxDB.
        - measurement: name of the metric
        - tags: dict of tags (key/value strings)
        - fields: dict of fields (numeric/string/bool values)
        - timestamp: RFC3339 string or similar (optional; if None use now)
        """
        bucket = cfg.influxdb["bucket"] or ""
        org = cfg.influxdb["org"] or ""
        if not all([bucket, org]):
            print("[Error] InfluxDB bucket/org configuration is incomplete. Point not written.")
            return

        self._ensure_client()
        if self._client is None or self._write_api is None:
            print("[Error] InfluxDB client is not configured. Point not written.")
            return

        tags = tags or {}
        fields = fields or {}

        point = influxdb_client.Point(measurement)

        for k, v in tags.items():
            point.tag(k, v)

        for k, v in fields.items():
            point.field(k, v)

        if timestamp:
            point.time(timestamp)

        debug_msg(f"Writing point to InfluxDB: measurement={measurement}")
        debug_msg(f"  tags={tags}")
        debug_msg(f"  fields={fields}")
        if timestamp:
            debug_msg(f"  time={timestamp}")

        self._write_api.write(bucket=bucket, org=org, record=point)

    def close(self) -> None:
        """Close the InfluxDB client."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._write_api = None

cli_influx = InfluxClient()
