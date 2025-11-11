#!/usr/bin/env python3
"""
GeoIP2 local database integration.
"""

from __future__ import annotations
import ipaddress
from dataclasses import dataclass, field
from typing import TypedDict, Any, Optional
import os

import geoip2.database
import geoip2.errors
import maxminddb

from api.external.geoip2.exceptions import (
    GeoIP2ConfigError,
    GeoIP2PathDBError
)


class GeoIP2CityResult(TypedDict, total=False):
    """Structured result for City lookup."""
    country: str
    state: str
    city: str
    zip: str
    latitude: str
    longitude: str
    iso_code: str
    ip: str
    status: str
    error_message: str

class GeoIP2ASNResult(TypedDict, total=False):
    """Structured result for ASN lookup."""
    asn: str
    org: str
    ip: str
    network: str
    status: str
    error_message: str

@dataclass
class GeoIP2Client:
    """
    Client for GeoIP2 City and ASN lookups.
    """
    # --- Path to City DB ---
    _city_db_path: str = field(default="")
    @property
    def city_db_path(self) -> str:
        """Get the City DB path."""
        return self._city_db_path

    @city_db_path.setter
    def city_db_path(self, value: str | None) -> None:
        """Set the City DB path."""
        if value is None or value == "":
            self._city_db_path = ""
            return

        if value and not os.path.isfile(value):
            raise GeoIP2PathDBError("City DB file does not exist", value)
        self._city_db_path = value

    def is_city_db_exists(self) -> bool:
        """Check if City DB file exists."""
        return bool(self.city_db_path and os.path.isfile(self.city_db_path))


    # --- Path to ASN DB ---
    _asn_db_path: str = field(default="")
    @property
    def asn_db_path(self) -> str:
        """Get the ASN DB path."""
        return self._asn_db_path

    @asn_db_path.setter
    def asn_db_path(self, value: str | None) -> None:
        """Set the ASN DB path."""
        if value is None or value == "":
            self._asn_db_path = ""
            return

        if value and not os.path.isfile(value):
            raise GeoIP2PathDBError("ASN DB file does not exist", value)
        self._asn_db_path = value

    def is_asn_db_exists(self) -> bool:
        """Check if ASN DB file exists."""
        return bool(self.asn_db_path and os.path.isfile(self.asn_db_path))


    # --- IP Address ---
    _ip : str = field(default="")
    @property
    def ip(self) -> str:
        """Get the IP address."""
        return self._ip.strip()

    @ip.setter
    def ip(self, value: str | None) -> None:
        """Set the IP address."""
        if value is None or value.strip() == "":
            self._ip = ""
            return

        value = value.strip()
        try:
            ipaddress.ip_address(value)
        except ValueError as ve:
            raise ValueError(f"Invalid IP address: {value}") from ve

        self._ip = value

    def is_ip_set(self) -> bool:
        """Check if IP address is set."""
        return self.ip != ""


    # ----- Debug -----
    _debug: bool = field(default=False)
    @property
    def debug(self) -> bool:
        """Get the debug flag"""
        return self._debug

    @debug.setter
    def debug(self, value: bool) -> None:
        """Set the debug flag"""
        self._debug = value

    def _debug_print(self, msg: str) -> None:
        if self.debug:
            print(msg, flush=True)


    # ----- Show -----
    _show: bool = field(default=True)
    @property
    def show(self) -> bool:
        """Get the show flag"""
        return self._show

    @show.setter
    def show(self, value: bool) -> None:
        """Set the show flag"""
        self._show = value

    # ---- Base Structures ----
    def _base_city(self, ip: str = None, status: str = "fail") -> GeoIP2CityResult:
        """Get base structure for City result."""
        return {
            "country": "",
            "state": "",
            "city": "",
            "zip": "",
            "latitude": "",
            "longitude": "",
            "iso_code": "",
            "ip": ip or self.ip,
            "status": status,
        }

    def _base_asn(self, status: str = "fail") -> GeoIP2ASNResult:
        """Get base structure for ASN result."""
        return {
            "asn": "",
            "org": "",
            "ip": "",
            "network": "",
            "status": status,
            "error_message": "",
        }

    @staticmethod
    def read_db(db_path: str) -> geoip2.database.Reader:
        """
        Open a GeoIP2 database and return the reader object.

        Args:
            db_path: Path to the MaxMind DB file.

        Returns:
            geoip2.database.Reader: Reader object for the database.

        Raises:
            GeoIP2PathDBError: If the database file is not found, not accessible,
                               or not a valid MaxMind DB.
        
        More info:
            https://geoip2.readthedocs.io/en/latest/#geoip2.database.Reader
        """
        try:
            reader_db = geoip2.database.Reader(db_path)
            return reader_db

        except FileNotFoundError as fnfe:
            raise GeoIP2PathDBError("DB file not found", db_path) from fnfe

        except PermissionError as pe:
            raise GeoIP2PathDBError("DB file not accessible (forbidden)", db_path) from pe

        except maxminddb.InvalidDatabaseError as ide:
            raise GeoIP2PathDBError("DB file is not a valid MaxMind DB", db_path) from ide


    def city(self) -> GeoIP2CityResult:
        """
        Get GeoIP2 City information for a given IP.

        Returns:
            GeoIP2CityResult: Structured result with city information.
        Raises:
            GeoIP2ConfigError: If IP is not set, invalid, or not found in City DB.
            GeoIP2PathDBError: If the City DB file is missing, inaccessible, or invalid.

        More Info:
            https://geoip2.readthedocs.io/en/latest/#geoip2.database.Reader.city
        """
        if self.is_ip_set() is False:
            raise GeoIP2ConfigError("IP address is not set", "ip", self.ip)

        geo_info: GeoIP2CityResult = self._base_city()
        reader_db = self.read_db(self.city_db_path)
        data_city = None
        try:
            data_city = reader_db.city(self.ip)
            if data_city is None:
                geo_info["status"] = "no_data"
            else:
                geo_info["country"] = data_city.country.name or ""
                geo_info["state"] = data_city.subdivisions.most_specific.name or ""
                geo_info["city"] = data_city.city.name or ""
                geo_info["zip"] = data_city.postal.code or ""
                geo_info["latitude"] = str(data_city.location.latitude or "")
                geo_info["longitude"] = str(data_city.location.longitude or "")
                geo_info["iso_code"] = data_city.country.iso_code or ""
                geo_info["status"] = "success"

        except ValueError as ve:
            raise GeoIP2ConfigError("Invalid IP address", "ip", self.ip) from ve

        except geoip2.errors.AddressNotFoundError as ane:
            raise GeoIP2ConfigError("IP address not found in City DB", "ip", self.ip) from ane

        finally:
            if reader_db is not None:
                reader_db.close()

        self._debug_print(f"[GeoIP2] City result: {geo_info}")
        return geo_info


    def asn(self) -> GeoIP2ASNResult:
        """
        Get ASN information (organization) for a given IP.
        """
        if self.is_ip_set() is False:
            raise GeoIP2ConfigError("IP address is not set", "ip", self.ip)

        asn_info = self._base_asn()
        reader_db = self.read_db(self.asn_db_path)
        data_asn = reader_db.asn(self.ip)
        reader_db.close()

        if data_asn is None:
            asn_info["status"] = "no_data"
            asn_info["error_message"] = "Missing ASN data"
            self._debug_print(f"[GeoIP2] No ASN data for IP {self.ip} in ASN database")
        else:
            asn_info["asn"] = str(data_asn.autonomous_system_number) or ""
            asn_info["org"] = data_asn.autonomous_system_organization or ""
            asn_info["ip"] = str(data_asn.ip_address) or ""
            asn_info["network"] = str(data_asn.network) or ""
            asn_info["status"] = "success"

        self._debug_print(f"[GeoIP2] ASN result: {asn_info}")
        return asn_info

    @staticmethod
    def get_city(
        ip: str, db: str, *, debug: bool = False, show: bool = True
    ) -> GeoIP2CityResult:
        """  Get GeoIP2 City information for a given IP address. """
        client = GeoIP2Client()
        client.ip = ip
        client.city_db_path = db
        client.debug = debug
        client.show = show
        return client.city()

    @staticmethod
    def get_asn(
        ip: str, db: str, *, debug: bool = False, show: bool = True
    ) -> GeoIP2ASNResult:
        """ Get ASN information for a given IP address. """
        client = GeoIP2Client()
        client.ip = ip
        client.asn_db_path = db
        client.debug = debug
        client.show = show
        return client.asn()
