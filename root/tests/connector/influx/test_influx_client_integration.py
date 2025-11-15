#!/usr/bin/env python3
"""Optional integration test for InfluxClient against real InfluxDB."""

# pylint: disable=redefined-outer-name

from __future__ import annotations

import os
import pytest

from connector.influx import InfluxClient, InfluxRecord
from connector.influx.exception import InfluxClientConnectionError

INFLUX_HOST = os.getenv("TEST_INFLUX_HOST", "")
INFLUX_ORG = os.getenv("TEST_INFLUX_ORG", "")
INFLUX_TOKEN = os.getenv("TEST_INFLUX_TOKEN", "")
INFLUX_BUCKET = os.getenv("TEST_INFLUX_BUCKET", "")

REQUIRE_INFLUX = os.getenv("TEST_INFLUX_REQUIRED", "0") == "1"

pytestmark = pytest.mark.skipif(
    not (INFLUX_HOST and INFLUX_ORG and INFLUX_TOKEN and INFLUX_BUCKET),
    reason="TEST_INFLUX_* env vars not set; skipping integration tests.",
)

@pytest.fixture(scope="module")
def influx_client():
    """Fixture: InfluxClient connected to real InfluxDB."""
    client = InfluxClient.create(
        url=INFLUX_HOST,
        org=INFLUX_ORG,
        token=INFLUX_TOKEN,
        bucket=INFLUX_BUCKET,
        debug=False,
    )

    if not REQUIRE_INFLUX and not client.is_available():
        pytest.skip("InfluxDB not available; skipping integration tests.")

    yield client
    client.close()


def test_influx_connection_test_integration(influx_client):
    """ Test connection to InfluxDB. """
    # just in case, make it explicit
    assert influx_client.test_connection() is True


def test_influx_connection_and_write_integration(influx_client):
    """ Test writing a point to InfluxDB. """
    rec = InfluxRecord(
        measurement="npmgraf_stats_test",
        tags={"env": "test"},
        fields={"value": 1},
    )

    try:
        influx_client.write_point(rec)

    except InfluxClientConnectionError as e:
        # if the connection drops right now → we consider it "no Influx"
        pytest.skip(f"InfluxDB connection error during write: {e}")
