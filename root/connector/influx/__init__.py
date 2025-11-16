#!/usr/bin/env python3
""" InfluxDB v2 client wrapper """
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional
import threading
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS
from connector.influx.exceptions import (
    InfluxClientConfigError,
    InfluxClientInitError,
    InfluxClientConnectionError
)

@dataclass(frozen=True)
class InfluxRecord:
    """Single point to write into InfluxDB."""
    measurement: str
    tags: dict[str, str]
    fields: dict[str, object]
    timestamp: Optional[str] = None  # RFC3339 (e.g. "2025-11-15T10:20:30Z")

class InfluxClient:
    """
    Minimal, thread-safe wrapper for writing points to InfluxDB.
    """

    def __init__(self) -> None:
        self._debug: bool = False
        self._url: str = ""
        self._org: str = ""
        self._token: str = ""
        self._bucket: str = ""

        self._client: influxdb_client.InfluxDBClient | None = None
        self._write_api: influxdb_client.WriteApi | None = None
        self._lock = threading.Lock()


    # ---- Propierties for configuration ----
    @property
    def url(self) -> str:
        """ URL of the InfluxDB instance. """
        return self._url
    @url.setter
    def url(self, value: str) -> None:
        self._url = value.strip()

    @property
    def org(self) -> str:
        """ Organization name in InfluxDB. """
        return self._org
    @org.setter
    def org(self, value: str) -> None:
        self._org = value.strip()

    @property
    def token(self) -> str:
        """ Authentication token for InfluxDB. """
        return self._token
    @token.setter
    def token(self, value: str) -> None:
        self._token = value.strip()

    @property
    def bucket(self) -> str:
        """ Bucket name in InfluxDB. """
        return self._bucket
    @bucket.setter
    def bucket(self, value: str) -> None:
        self._bucket = value.strip()

    @property
    def debug(self) -> bool:
        """ Enable or disable debug mode. """
        return self._debug
    @debug.setter
    def debug(self, value: bool) -> None:
        self._debug = value


    # ---------- Factory ----------
    @staticmethod
    def create(
        url: str, org: str, token: str, bucket: str, *, debug: bool = True
    ) -> "InfluxClient":
        """
        Factory method to build a configured client.
        Args:
            url: URL of the InfluxDB instance.
            org: Organization name in InfluxDB.
            token: Authentication token for InfluxDB.
            bucket: Bucket name in InfluxDB.
            debug: Enable debug mode (default: True).
        Returns:
            InfluxClient: Configured InfluxClient instance.
        """
        client = InfluxClient()
        client.debug = debug
        client.url = url
        client.org = org
        client.token = token
        client.bucket = bucket
        return client


    # ---------- Internals ----------
    def _log(self, msg: str) -> None:
        """ Log a debug message if debug mode is enabled. """
        if self.debug:
            print(f"[InfluxClient] {msg}", flush=True)


    def _ensure_client(self) -> None:
        """Lazy, thread-safe creation of the underlying client + write_api."""
        if self._client is not None and self._write_api is not None:
            return

        with self._lock:
            if self._client is not None and self._write_api is not None:
                return

            if not (self.url and self.org and self.token):
                raise InfluxClientConfigError("Missing url/org/token configuration.")

            self._log(f"Creating client url={self.url} org={self.org} bucket={self.bucket}")
            self._client = influxdb_client.InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org
            )
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)


    # ---------- Context ----------
    @contextmanager
    def client(self):
        """
        Context manager yielding the underlying InfluxDBClient.

        Raises:
            InfluxClientConfigError: if url/org/token are not set.
            InfluxClientInitError: if client/write_api creation failed.
        """
        self._ensure_client()

        if self._client is None:
            raise InfluxClientInitError("InfluxDB client not initialized.")

        try:
            yield self._client
        finally:
            # Keep connection open for reuse
            pass

    # ---------- Test connection ----------
    def is_available(self) -> bool:
        """
        Check if InfluxDB is available.
        Uses test_connection() internally.
        Returns:
            bool: True if InfluxDB is reachable, False otherwise.
        """
        return self.test_connection()


    def test_connection(self) -> bool:
        """
        Test connection to InfluxDB by calling `ping()`.

        Returns:
            bool: True if `ping()` responds correctly, False if there is a connection error.

        Raises:
            InfluxClientConfigError:  if url/org/token are not set.
            InfluxClientInitError: if the client could not be initialized.
        """
        self._ensure_client()

        if self._client is None:
            raise InfluxClientInitError("InfluxDB client not initialized.")

        try:
            ok = bool(self._client.ping())
            if not ok:
                self._log("Ping to InfluxDB returned False.")
            else:
                self._log("Ping to InfluxDB OK.")
            return ok

        except Exception as e:  # pylint: disable=broad-exception-caught
            self._log(f"Ping to InfluxDB failed: {e}")
            return False

    # ---------- Public API ----------
    def write_point(self, rec: InfluxRecord) -> None:
        """
        Write a single point to InfluxDB.

        Args:
            rec: InfluxRecord with measurement, tags, fields, timestamp.

        Raises:
            InfluxClientConfigError: if bucket/org are not configured.
            InfluxClientInitError: if the client or write_api are not initialized.
        """
        if not (self.bucket and self.org):
            raise InfluxClientConfigError("Missing bucket/org configuration.")

        self._ensure_client()
        if self._client is None or self._write_api is None:
            raise InfluxClientInitError("InfluxDB client not initialized.")

        tags = dict(rec.tags or {})
        fields = dict(rec.fields or {})
        if not rec.measurement or not fields:
            self._log("Empty measurement or fields; skipping write.")
            return

        point = influxdb_client.Point(rec.measurement)
        for k, v in tags.items():
            point.tag(k, v)

        for k, v in fields.items():
            point.field(k, v)

        if rec.timestamp:
            point.time(rec.timestamp)

        self._log(
            f"write -> measurement={rec.measurement} "
            f"tags={tags} fields={fields} ts={rec.timestamp or 'now'}"
        )

        try:
            self._write_api.write(bucket=self.bucket, org=self.org, record=point)

        except Exception as e:
            raise InfluxClientConnectionError(
                "Failed to write point",
                url=self.url,
                org=self.org,
                bucket=self.bucket,
                original_exc=e,
            ) from e

    def close(self) -> None:
        """Close the underlying client."""
        with self._lock:
            if self._client is not None:
                self._log("Closing client.")
                self._client.close()
            self._client = None
            self._write_api = None
