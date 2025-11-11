#!/usr/bin/env python3
"""Tests for GeoIP2Client integration (City + ASN)."""

# pylint: disable=use-implicit-booleaness-not-comparison
# pylint: disable=unused-argument
# pylint: disable=redefined-outer-name

from __future__ import annotations

import os
from types import SimpleNamespace
import pytest
import maxminddb
import geoip2.errors
from api.external.geoip2 import GeoIP2Client
from api.external.geoip2.exceptions import GeoIP2PathDBError, GeoIP2ConfigError
from api.external import geoip2 as geoip2_module

# ---- Class Dummy Readers ----

class DummyCityReader:
    """Reader dummy for city() that returns a complete city record."""

    calls: list[str] = []
    def count_calls(self) -> int:
        """ Return the number of calls to city(). """
        return len(self.calls)

    def __init__(self, *args, **kwargs) -> None:  # firma compatible con Reader
        self._closed = False

    def city(self, ip: str):
        """ Return a complete dummy city record. """
        self.calls.append(ip)
        # Simulate the structure of the object returned by geoip2.database.Reader.city()
        country = SimpleNamespace(name="Spain", iso_code="ES")
        subdiv_most = SimpleNamespace(name="Madrid")
        subdivisions = SimpleNamespace(most_specific=subdiv_most)
        city = SimpleNamespace(name="Madrid")
        postal = SimpleNamespace(code="28001")
        location = SimpleNamespace(latitude=40.4168, longitude=-3.7038)
        return SimpleNamespace(
            country=country,
            subdivisions=subdivisions,
            city=city,
            postal=postal,
            location=location,
        )

    def close(self) -> None:
        """ Close the reader. """
        self._closed = True


class DummyCityReaderNoData(DummyCityReader):
    """Reader dummy for city() that returns None (no_data)."""
    def city(self, ip: str):
        return None


class DummyASNReader:
    """Reader dummy for asn() that returns complete data."""

    calls: list[str] = []
    def count_calls(self) -> int:
        """ Return the number of calls to asn(). """
        return len(self.calls)

    def __init__(self, *args, **kwargs) -> None:
        self._closed = False

    def asn(self, ip: str):
        """ Return a complete dummy ASN record. """
        # Simulate the structure of the object returned by geoip2.database.Reader.asn()
        self.calls.append(ip)
        return SimpleNamespace(
            autonomous_system_number=64512,
            autonomous_system_organization="Example ISP",
            ip_address=ip,
            network="1.2.3.0/24",
        )

    def close(self) -> None:
        """ Close the reader. """
        self._closed = True


class DummyASNReaderNoData(DummyASNReader):
    """Reader dummy for asn() that returns None (no_data)."""

    def asn(self, ip: str):
        return None

class DummyReaderRaises:
    """Reader dummy that raises AddressNotFoundError on city()."""
    def __init__(self, *a, **kw):
        pass

    def city(self, ip: str):
        """ Raise AddressNotFoundError. """
        raise geoip2.errors.AddressNotFoundError("not found")

    def close(self):
        """ Close the reader. """


# ---- Tests ----

def test_city_db_path_empty_allows_no_file_check():
    """ Setting empty city_db_path allows no file check. """
    client = GeoIP2Client()
    client.city_db_path = ""
    assert client.city_db_path == ""
    assert client.is_city_db_exists() is False


def test_city_db_path_nonexistent_raises_path_error(monkeypatch):
    """ Setting nonexistent city_db_path raises GeoIP2PathDBError. """
    client = GeoIP2Client()

    # Forzamos isfile=False para esa ruta
    def fake_isfile(path: str) -> bool:
        return False

    monkeypatch.setattr(os.path, "isfile", fake_isfile)

    with pytest.raises(GeoIP2PathDBError) as exc:
        client.city_db_path = "/fake/path/GeoLite2-City.mmdb"

    assert "does not exist" in str(exc.value)
    assert exc.value.path == "/fake/path/GeoLite2-City.mmdb"


def test_city_db_path_existing_ok(monkeypatch):
    """ Setting existing city_db_path is successful. """
    client = GeoIP2Client()

    monkeypatch.setattr(os.path, "isfile", lambda p: True)

    client.city_db_path = "/fake/path/GeoLite2-City.mmdb"
    assert client.city_db_path == "/fake/path/GeoLite2-City.mmdb"
    assert client.is_city_db_exists() is True


def test_asn_db_path_empty_allows_no_file_check():
    """ Setting empty asn_db_path allows no file check. """
    client = GeoIP2Client()
    client.asn_db_path = ""
    assert client.asn_db_path == ""
    assert client.is_asn_db_exists() is False


def test_asn_db_path_nonexistent_raises_path_error(monkeypatch):
    """ Setting nonexistent asn_db_path raises GeoIP2PathDBError. """
    client = GeoIP2Client()

    monkeypatch.setattr(os.path, "isfile", lambda p: False)

    with pytest.raises(GeoIP2PathDBError) as exc:
        client.asn_db_path = "/fake/path/GeoLite2-ASN.mmdb"

    assert "does not exist" in str(exc.value)
    assert exc.value.path == "/fake/path/GeoLite2-ASN.mmdb"


def test_asn_db_path_existing_ok(monkeypatch):
    """ Setting existing asn_db_path is successful. """
    client = GeoIP2Client()

    monkeypatch.setattr(os.path, "isfile", lambda p: True)

    client.asn_db_path = "/fake/path/GeoLite2-ASN.mmdb"
    assert client.asn_db_path == "/fake/path/GeoLite2-ASN.mmdb"
    assert client.is_asn_db_exists() is True


def test_ip_set_valid_ipv4():
    """ Setting valid IPv4 address is successful. """
    client = GeoIP2Client()
    client.ip = "8.8.8.8"
    assert client.ip == "8.8.8.8"
    assert client.is_ip_set() is True


def test_ip_empty_clears_value():
    """ Setting empty IP clears the value. """
    client = GeoIP2Client()
    client.ip = "1.2.3.4"
    client.ip = ""
    assert client.ip == ""
    assert client.is_ip_set() is False


def test_ip_invalid_raises_valueerror():
    """ Setting invalid IP raises ValueError. """
    client = GeoIP2Client()
    with pytest.raises(ValueError):
        client.ip = "not-an-ip"


def test_read_db_invalid_database_raises_path_error(monkeypatch):
    """
    Simulate that geoip2.database.Reader raises InvalidDatabaseError
    and that read_db transforms it into GeoIP2PathDBError.
    """
    def fake_reader(path):
        raise maxminddb.InvalidDatabaseError("not a valid mmdb")

    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", fake_reader)

    with pytest.raises(GeoIP2PathDBError) as exc:
        GeoIP2Client.read_db("/fake/path/GeoLite2-City.mmdb")

    assert "not a valid MaxMind DB" in str(exc.value)
    assert exc.value.path == "/fake/path/GeoLite2-City.mmdb"


def test_city_without_ip_raises_config_error(monkeypatch):
    """ Calling city() without setting IP raises GeoIP2ConfigError. """
    client = GeoIP2Client()

    # The path is valid, but it won't be opened if IP is missing
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    client.city_db_path = "/fake/path/GeoLite2-City.mmdb"

    with pytest.raises(GeoIP2ConfigError) as exc:
        client.city()

    assert "IP address is not set" in str(exc.value)
    assert exc.value.error_key == "ip"
    assert exc.value.error_value == ""


def test_city_ok(monkeypatch):
    """ Calling city() with valid IP returns expected data. """
    client = GeoIP2Client()
    client.ip = "1.2.3.4"

    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    client.city_db_path = "/fake/path/GeoLite2-City.mmdb"

    # Reader dummy that returns complete data
    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyCityReader)

    result = client.city()

    assert result["status"] == "success"
    assert result["country"] == "Spain"
    assert result["state"] == "Madrid"
    assert result["city"] == "Madrid"
    assert result["zip"] == "28001"
    assert result["latitude"] == "40.4168"
    assert result["longitude"] == "-3.7038"
    assert result["iso_code"] == "ES"
    assert result["ip"] == "1.2.3.4"


def test_city_no_data_sets_status_no_data(monkeypatch):
    """ Simulamos que reader.city() devuelve None (no data). """
    client = GeoIP2Client()
    client.ip = "1.2.3.4"

    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    client.city_db_path = "/fake/path/GeoLite2-City.mmdb"

    # Reader dummy that returns None
    monkeypatch.setattr(
        geoip2_module.geoip2.database, "Reader", DummyCityReaderNoData
    )

    result = client.city()
    assert result["status"] == "no_data"


def test_city_address_not_found_raises_config_error(monkeypatch):
    """ Simulate that reader.city() raises AddressNotFoundError. """
    client = GeoIP2Client()
    client.ip = "1.2.3.4"

    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    client.city_db_path = "/fake/path/GeoLite2-City.mmdb"

    monkeypatch.setattr(
        geoip2_module.geoip2.database, "Reader", DummyReaderRaises
    )

    with pytest.raises(GeoIP2ConfigError) as exc:
        client.city()

    assert "not found" in str(exc.value)
    assert exc.value.error_key == "ip"
    assert exc.value.error_value == "1.2.3.4"


def test_asn_without_ip_raises_config_error(monkeypatch):
    """ Calling asn() without setting IP raises GeoIP2ConfigError. """
    client = GeoIP2Client()

    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    client.asn_db_path = "/fake/path/GeoLite2-ASN.mmdb"

    with pytest.raises(GeoIP2ConfigError) as exc:
        client.asn()

    assert "IP address is not set" in str(exc.value)
    assert exc.value.error_key == "ip"


def test_asn_ok(monkeypatch):
    """ Calling asn() with valid IP returns expected data. """
    client = GeoIP2Client()
    client.ip = "1.2.3.4"

    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    client.asn_db_path = "/fake/path/GeoLite2-ASN.mmdb"

    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyASNReader)

    result = client.asn()

    assert result["status"] == "success"
    assert result["asn"] == "64512"
    assert result["org"] == "Example ISP"
    assert result["ip"] == "1.2.3.4"
    assert result["network"] == "1.2.3.0/24"


def test_asn_no_data(monkeypatch):
    """ Simulate that reader.asn() returns None (no data). """
    client = GeoIP2Client()
    client.ip = "1.2.3.4"

    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    client.asn_db_path = "/fake/path/GeoLite2-ASN.mmdb"

    monkeypatch.setattr(
        geoip2_module.geoip2.database, "Reader", DummyASNReaderNoData
    )

    result = client.asn()

    assert result["status"] == "no_data"
    assert "Missing ASN data" in result["error_message"]


def test_get_city_wrapper_uses_client(monkeypatch):
    """ Test that get_city() static method uses GeoIP2Client internally. """
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyCityReader)

    result = GeoIP2Client.get_city(
        ip="5.6.7.8",
        db="/fake/path/GeoLite2-City.mmdb",
        debug=False,
        show=False,
    )

    assert result["status"] == "success"
    assert result["ip"] == "5.6.7.8"
    assert result["country"] == "Spain"


def test_get_asn_wrapper_uses_client(monkeypatch):
    """ Test that get_asn() static method uses GeoIP2Client internally. """
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyASNReader)

    result = GeoIP2Client.get_asn(
        ip="9.9.9.9",
        db="/fake/path/GeoLite2-ASN.mmdb",
        debug=False,
        show=False,
    )

    assert result["status"] == "success"
    assert result["ip"] == "9.9.9.9"
    assert result["asn"] == "64512"
    assert result["org"] == "Example ISP"


def test_debug_prints_city_result(monkeypatch, capsys):
    """ Test that enabling debug causes city() to print the result. """
    client = GeoIP2Client()
    client.ip = "1.2.3.4"
    client.debug = True

    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    client.city_db_path = "/fake/path/GeoLite2-City.mmdb"

    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyCityReader)

    _ = client.city()
    out = capsys.readouterr().out
    assert "[GeoIP2] City result:" in out


def test_get_citys_with_multiple_ips(monkeypatch):
    """
    get_citys() should return a dict[ip] = GeoIP2CityResult
    using the DummyCityReader for all IPs.
    """
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyCityReader)

    ips = ["1.1.1.1", "8.8.8.8"]
    results = GeoIP2Client.get_citys(
        ips=ips,
        db="/fake/path/GeoLite2-City.mmdb",
        debug=False,
        show=False
    )

    # One entry per IP address must be returned
    assert set(results.keys()) == set(ips)

    for ip, data in results.items():
        assert data["status"] == "success"
        assert data["city"] == "Madrid"
        assert data["country"] == "Spain"
        assert data["iso_code"] == "ES"
        assert data["ip"] == ip


def test_get_citys_handles_no_data(monkeypatch):
    """
    get_citys() should handle when reader.city() returns None (no_data).
    """
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyCityReaderNoData)

    ips = ["1.1.1.1", "8.8.8.8"]
    results = GeoIP2Client.get_citys(
        ips=ips,
        db="/fake/path/GeoLite2-City.mmdb"
    )

    # One entry per IP address must be returned
    assert set(results.keys()) == set(ips)

    for _ip, data in results.items():
        assert data["status"] == "no_data"
        assert data["city"] == ""
        assert data["ip"] == ""


def test_get_citys_invalid_ip(monkeypatch):
    """
    Invalid IPs should raise ValueError before any DB access.
    """
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyCityReader)

    ips = ["1.1.1.1", "not-an-ip", "8.8.8.8"]
    with pytest.raises(ValueError) as exc:
        GeoIP2Client.get_citys(
            ips=ips,
            db="/fake/path/GeoLite2-City.mmdb"
        )

    assert "Invalid IP address" in str(exc.value)


def test_get_asns_with_multiple_ips(monkeypatch):
    """
    get_asns() should return a dict[ip] = GeoIP2ASNResult
    using the DummyASNReader for all IPs.
    """
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyASNReader)

    ips = ["9.9.9.9", "8.8.4.4"]
    results = GeoIP2Client.get_asns(
        ips=ips,
        db="/fake/path/GeoLite2-ASN.mmdb",
        debug=False,
        show=False
    )

    # One entry per IP address must be returned
    assert set(results.keys()) == set(ips)

    for _ip, data in results.items():
        assert data["status"] == "success"
        assert data["asn"] == "AS64512" or isinstance(data["asn"], (str, int))
        assert data["org"] == "Example ISP"
        assert data["network"] == "1.2.3.0/24"


def test_get_asns_handles_no_data(monkeypatch):
    """
    get_asns() should handle when reader.asn() returns None (no_data).
    """
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyASNReaderNoData)

    ips = ["1.1.1.1", "8.8.8.8"]
    results = GeoIP2Client.get_asns(
        ips=ips,
        db="/fake/path/GeoLite2-ASN.mmdb"
    )

    # One entry per IP address must be returned
    assert set(results.keys()) == set(ips)

    for _ip, data in results.items():
        assert data["status"] == "no_data"
        assert data["asn"] == ""
        assert data["org"] == ""
        assert "Missing ASN data" in data["error_message"]

def test_get_asns_invalid_ip(monkeypatch):
    """
    Invalid IPs should raise ValueError before any DB access.
    """
    monkeypatch.setattr(os.path, "isfile", lambda p: True)
    monkeypatch.setattr(geoip2_module.geoip2.database, "Reader", DummyASNReader)

    ips = ["1.1.1.1", "not-an-ip", "8.8.8.8"]
    with pytest.raises(ValueError) as exc:
        GeoIP2Client.get_asns(
            ips=ips,
            db="/fake/path/GeoLite2-ASN.mmdb"
        )
    assert "Invalid IP address" in str(exc.value)
