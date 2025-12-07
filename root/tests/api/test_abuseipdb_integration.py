#!/usr/bin/env python3
"""Optional integration test for InfluxClient against real InfluxDB."""
from __future__ import annotations

import os

import pytest

from api.external.abuseipdb import AbuseIPDB, AbuseIPDBStatusReturn
from api.external.abuseipdb.exceptions import (AbuseIPDBRateLimitError,
                                               AbuseIPDBResponseError)

ABUSEIP_KEY = os.getenv("TEST_ABUSEIP_KEY", "")

pytestmark = pytest.mark.skipif(
    not (ABUSEIP_KEY),
    reason="TEST_ABUSEIP_KEY env vars not set; skipping integration test.",
)

def test_abuseipdb_connection_and_check_integration():
    """Integration test: connect to AbuseIPDB and check an IP."""

    abuse = AbuseIPDB()
    abuse.key = ABUSEIP_KEY
    abuse.ip = "8.8.8.8"

    try:
        result = abuse.api_check()

    except AbuseIPDBRateLimitError as exc:
        pytest.skip(f"Skipping test because AbuseIPDB rate limit was hit: {exc}")

    except AbuseIPDBResponseError as exc:
        pytest.skip(f"Skipping test due to AbuseIPDB API error: {exc}")

    assert result["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert result["status_code"] == 200
    assert result["errors"] == [] # pylint: disable=use-implicit-booleaness-not-comparison
    assert abuse.last_result == result
