#!/usr/bin/env python3
"""Unit tests for InfluxClient wrapper."""

from __future__ import annotations

import pytest

import connector.influx as influx_module
from connector.influx import InfluxClient, InfluxRecord
from connector.influx.exceptions import (InfluxClientConfigError,
                                         InfluxClientInitError)


# -------------------- Dummies -------------------- #
class DummyPoint:
    """Fake Point to track tags, fields and time."""

    def __init__(self, measurement: str) -> None:
        self.measurement = measurement
        self.tags = {}
        self.fields = {}
        self.timestamp = None

    def tag(self, key, value): # pylint: disable=missing-function-docstring
        self.tags[key] = value
        return self

    def field(self, key, value): # pylint: disable=missing-function-docstring
        self.fields[key] = value
        return self

    def time(self, ts): # pylint: disable=missing-function-docstring
        self.timestamp = ts
        return self


class DummyWriteApi:
    """Fake WriteApi to record writes."""

    def __init__(self) -> None:
        self.writes = []

    def write(self, bucket, org, record): # pylint: disable=missing-function-docstring
        self.writes.append((bucket, org, record))


class DummyInfluxDBClient:
    """Fake InfluxDBClient returning DummyWriteApi."""

    def __init__(self, url, token, org) -> None:
        self.url = url
        self.token = token
        self.org = org
        self.closed = False
        self.write_api_call_count = 0

    def write_api(self, write_options=None): # pylint: disable=missing-function-docstring
        self.write_api_call_count += 1
        return DummyWriteApi()

    def close(self): # pylint: disable=missing-function-docstring
        self.closed = True


# -------------------- Fixtures -------------------- #

@pytest.fixture
def patched_influx(monkeypatch):
    """
    Patch influxdb_client.InfluxDBClient and Point with dummies.
    This prevents the use of the real library during tests.
    """
    dummy_client_instances = []

    def fake_client(url, token, org):
        client = DummyInfluxDBClient(url, token, org)
        dummy_client_instances.append(client)
        return client

    monkeypatch.setattr(influx_module.influxdb_client, "InfluxDBClient", fake_client)
    monkeypatch.setattr(influx_module.influxdb_client, "Point", DummyPoint)

    return {"clients": dummy_client_instances}


# -------------------- Tests -------------------- #

def test_create_sets_properties():
    """ Test that the create factory method sets properties correctly. """
    client = InfluxClient.create(
        url="http://localhost:8086",
        org="my-org",
        token="my-token",
        bucket="my-bucket"
    )

    assert client.url == "http://localhost:8086"
    assert client.org == "my-org"
    assert client.token == "my-token"
    assert client.bucket == "my-bucket"


def test_ensure_client_missing_config_raises_config_error():
    """ Test that _ensure_client raises InfluxClientConfigError if config is missing. """
    client = InfluxClient()

    with pytest.raises(InfluxClientConfigError) as exc:
        client._ensure_client() # pylint: disable=protected-access

    assert "Missing url/org/token" in str(exc.value)


def test_ensure_client_creates_client_once(patched_influx):
    """ Test that _ensure_client creates the client and write_api only once. """
    # pylint: disable=protected-access

    client = InfluxClient.create(
        url="http://localhost:8086",
        org="my-org",
        token="my-token",
        bucket="my-bucket",
    )

    # First call: creates the client
    client._ensure_client()
    assert client._client is not None
    assert client._write_api is not None
    assert len(patched_influx["clients"]) == 1

    first_client = patched_influx["clients"][0]
    assert first_client.url == "http://localhost:8086"
    assert first_client.org == "my-org"
    assert first_client.token == "my-token"
    assert first_client.write_api_call_count == 1

    # Second call: does not create again
    client._ensure_client()
    assert len(patched_influx["clients"]) == 1
    assert first_client.write_api_call_count == 1  # write_api() was not called again

def test_client_context_yields_client(patched_influx):
    """ Test that the client context manager yields the underlying client. """
    client = InfluxClient.create(
        url="http://localhost:8086",
        org="my-org",
        token="my-token",
        bucket="my-bucket"
    )

    with client.client() as c:
        # c should be the DummyInfluxDBClient
        assert isinstance(c, DummyInfluxDBClient)
        assert c.url == "http://localhost:8086"

    # It does not close automatically
    assert not patched_influx["clients"][0].closed


def test_client_context_raises_init_error_when_client_none(monkeypatch):
    """ Test that the client context manager raises InfluxClientInitError when client is None. """
    client = InfluxClient.create(
        url="http://localhost:8086",
        org="my-org",
        token="my-token",
        bucket="my-bucket",
    )

    def fake_ensure():
        # pylint: disable=protected-access
        client._client = None
        client._write_api = None

    monkeypatch.setattr(client, "_ensure_client", fake_ensure)

    with pytest.raises(InfluxClientInitError) as exc:
        with client.client():
            pass

    assert "not initialized" in str(exc.value)


def test_write_point_missing_bucket_org_raises_config_error(patched_influx):
    """
    Test that write_point raises InfluxClientConfigError if bucket/org are missing.
    """
    client = InfluxClient.create(
        url="http://localhost:8086",
        org="",         # org empty
        token="my-token",
        bucket="",      # bucket empty
    )

    rec = InfluxRecord(
        measurement="m",
        tags={"a": "b"},
        fields={"value": 1},
    )

    with pytest.raises(InfluxClientConfigError) as exc:
        client.write_point(rec)

    assert "Missing bucket/org configuration" in str(exc.value)


def test_write_point_client_not_initialized_raises_init_error(patched_influx):
    """
    Test that if the client is not initialized, write_point raises InfluxClientInitError.
    """
    # pylint: disable=protected-access
    client = InfluxClient.create(
        url="http://localhost:8086",
        org="my-org",
        token="my-token",
        bucket="my-bucket",
    )

    # Force _ensure_client not to create the write_api
    client._client = None
    client._write_api = None

    # But _ensure_client will be called, so we patch it to do nothing
    # does not create anything
    def fake_ensure():
        # does not create anything
        return None

    client._ensure_client = fake_ensure

    rec = InfluxRecord(
        measurement="m",
        tags={"a": "b"},
        fields={"value": 1},
    )

    with pytest.raises(InfluxClientInitError) as exc:
        client.write_point(rec)

    assert "client not initialized" in str(exc.value)


def test_write_point_empty_measurement_or_fields_skip_write(patched_influx):
    """ Test that write_point skips writing if measurement or fields are empty. """
    # pylint: disable=protected-access
    client = InfluxClient.create(
        url="http://localhost:8086",
        org="my-org",
        token="my-token",
        bucket="my-bucket"
    )

    client._ensure_client()
    dummy_client = patched_influx["clients"][0]
    dummy_write_api: DummyWriteApi = client._write_api

    # Case 1: empty measurement
    rec1 = InfluxRecord(measurement="", tags={}, fields={"v": 1})
    client.write_point(rec1)
    assert dummy_write_api.writes == []

    # Case 2: empty fields
    rec2 = InfluxRecord(measurement="m", tags={}, fields={})
    client.write_point(rec2)
    assert dummy_write_api.writes == []  # sigue sin escribir nada


def test_write_point_happy_path_builds_point_and_calls_write(patched_influx):
    """ Test that write_point builds the point correctly and calls write_api.write(). """
    client = InfluxClient.create(
        url="http://localhost:8086",
        org="my-org",
        token="my-token",
        bucket="my-bucket"
    )

    client._ensure_client()
    dummy_client = patched_influx["clients"][0]
    dummy_write_api: DummyWriteApi = client._write_api  # type: ignore[assignment]

    rec = InfluxRecord(
        measurement="http_requests",
        tags={"host": "web01", "env": "test"},
        fields={"latency_ms": 123.4, "status": 200},
        timestamp="2025-11-15T10:20:30Z",
    )

    client.write_point(rec)

    # Se ha hecho exactamente 1 write
    assert len(dummy_write_api.writes) == 1
    bucket, org, point = dummy_write_api.writes[0]

    assert bucket == "my-bucket"
    assert org == "my-org"
    assert isinstance(point, DummyPoint)
    assert point.measurement == "http_requests"
    assert point.tags == {"host": "web01", "env": "test"}
    assert point.fields == {"latency_ms": 123.4, "status": 200}
    assert point.timestamp == "2025-11-15T10:20:30Z"


def test_close_closes_underlying_client(patched_influx):
    """ Test that close() closes the underlying client and resets attributes. """
    client = InfluxClient.create(
        url="http://localhost:8086",
        org="my-org",
        token="my-token",
        bucket="my-bucket"
    )

    client._ensure_client()
    dummy_client = patched_influx["clients"][0]
    assert not dummy_client.closed

    client.close()
    assert dummy_client.closed
    assert client._client is None
    assert client._write_api is None
