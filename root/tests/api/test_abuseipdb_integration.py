#!/usr/bin/env python3
"""Optional integration test for InfluxClient against real InfluxDB."""
from __future__ import annotations

import os
import pytest

from api.external.abuseipdb import (
    AbuseIPDB,
    AbuseIPDBStatusReturn,
)

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
    abuse.show = False  # no output during test

    result = abuse.api_check()

    assert result["status"] is AbuseIPDBStatusReturn.SUCCESS
    assert result["status_code"] == 200
    assert result["errors"] == [] # pylint: disable=use-implicit-booleaness-not-comparison
    assert abuse.last_result == result
