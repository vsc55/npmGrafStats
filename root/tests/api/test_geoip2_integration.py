#!/usr/bin/env python3
"""Integration tests for GeoIP2Client with real MaxMind DBs (if present)."""

# pylint: disable=import-outside-toplevel
# pylint: disable=redefined-outer-name

from __future__ import annotations

from pathlib import Path

import pytest

from api.external.geoip2 import GeoIP2Client

DEBUG_TEST = False  # Set true dumping results to stdout

@pytest.fixture(scope="session")
def geoip2_paths_fixture() -> dict[str, Path]:
    """
    Return paths to the GeoIP2 DBs in tests/data.
    No stop if they don't exist, tests can decide to skip.
    """
    base = Path(__file__).resolve().parents[1] / "data"
    return {
        "city": base / "GeoLite2-City.mmdb",
        "asn": base / "GeoLite2-ASN.mmdb",
    }

@pytest.mark.integration
def test_city_with_real_db(geoip2_paths_fixture):
    """ Test GeoIP2Client.city() with real GeoLite2 City DB. """
    if not geoip2_paths_fixture["city"].is_file():
        pytest.skip(f"GeoLite2 City DB not found in {geoip2_paths_fixture['city']}")

    client = GeoIP2Client()
    client.city_db_path = str(geoip2_paths_fixture["city"])
    client.ip = "8.8.8.8"

    result = client.city()

    if DEBUG_TEST:
        from pprint import pprint
        pprint(result)
        # {
        #     'city': '',
        #     'country': 'United States',
        #     'ip': '8.8.8.8',
        #     'iso_code': 'US',
        #     'latitude': '37.751',
        #     'longitude': '-97.822',
        #     'state': '',
        #     'status': 'success',
        #     'zip': ''
        # }

    assert result["status"] in ("success", "no_data")
    assert result["ip"] == "8.8.8.8"
    assert result['country'] == 'United States'
    assert result['iso_code'] == 'US'


@pytest.mark.integration
def test_asn_with_real_db(geoip2_paths_fixture):
    """ Test GeoIP2Client.asn() with real GeoLite2 ASN DB. """
    if not geoip2_paths_fixture["asn"].is_file():
        pytest.skip(f"GeoLite2 ASN DB not found in {geoip2_paths_fixture['asn']}")

    client = GeoIP2Client()
    client.asn_db_path = str(geoip2_paths_fixture["asn"])
    client.ip = "8.8.8.8"

    result = client.asn()

    if DEBUG_TEST:
        from pprint import pprint
        pprint(result)
        # {
        #     'asn': '15169',
        #     'error_message': '',
        #     'ip': '8.8.8.8',
        #     'network': '8.8.8.0/24',
        #     'org': 'GOOGLE',
        #     'status': 'success'
        # }

    assert result["status"] == "success"
    assert result["org"] is not None
    assert result["asn"] == "15169"
    assert result["ip"] == "8.8.8.8"
    assert result["network"] == "8.8.8.0/24"
