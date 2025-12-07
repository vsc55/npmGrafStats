#!/usr/bin/env python3
""" Global configuration for the application. """
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from logger import get_logger
from utils import env_bool, env_int
from utils.external_ip import ExternalIP

if TYPE_CHECKING:
    from npm.config import NpmConfig

log = get_logger(__name__)

@dataclass(frozen=False)
class GlobalConfig:
    """ Global configuration """

    # -------- Sub-config to modules --------
    npm: Optional["NpmConfig"] = None
    # in the future: apache: Optional["ApacheConfig"] = None, etc.


    # ------- Post-initialization --------
    def __post_init__(self):
        log.debug("GlobalConfig initialized")


    # -------- Application version --------
    @property
    def version(self) -> str:
        """ Get the version of the application. """
        return "3.0.0"

    # -------- Flags globals --------
    proxy_logs: bool = True
    redirect_logs: bool = True
    public_logs: bool = True   # Must be True for normal operation
    internal_logs: bool = False
    monitoring_logs: bool = False

    # -------- GeoIP/ASN/City database paths --------
    _geo_asn_db_path: str = field(init=False, repr=False, default="/geolite/GeoLite2-ASN.mmdb")
    @property
    def geo_asn_db_path(self) -> str:
        """ Get the GeoASN DB path. """
        base = Path(__file__).resolve().parent.parent
        path = self._geo_asn_db_path.replace("{workdir}", str(base))
        return str(Path(path))

    @geo_asn_db_path.setter
    def geo_asn_db_path(self, value: str) -> None:
        self._geo_asn_db_path = value

    @property
    def geo_asn_db_exists(self) -> bool:
        """ Check if GeoASN DB exists. """
        return os.path.isfile(self.geo_asn_db_path)


    _geo_city_db_path: str = field(init=False, repr=False, default="/geolite/GeoLite2-City.mmdb")
    @property
    def geo_city_db_path(self) -> str:
        """ Get the GeoCity DB path. """
        base = Path(__file__).resolve().parent.parent
        path = self._geo_city_db_path.replace("{workdir}", str(base))
        return str(Path(path))

    @geo_city_db_path.setter
    def geo_city_db_path(self, value: str) -> None:
        self._geo_city_db_path = value

    @property
    def geo_city_db_exists(self) -> bool:
        """ Check if GeoCity DB exists. """
        return os.path.isfile(self.geo_city_db_path)

    # -------- abuseipdb.com key --------
    api_abuseip_key: str = ""

    # ------- Monitoring IPs file path --------
    _monitor_file_path: str = field(init=False, repr=False, default="/monitoringips.txt")
    @property
    def monitor_file_path(self) -> str:
        """ Get the Monitor file path. """
        base = Path(__file__).resolve().parent.parent
        path = self._monitor_file_path.replace("{workdir}", str(base))
        return str(Path(path))

    @monitor_file_path.setter
    def monitor_file_path(self, value: str) -> None:
        self._monitor_file_path = value

    @property
    def monitor_file_exists(self) -> bool:
        """ Check if Monitor file exists. """
        return os.path.isfile(self.monitor_file_path)

    # -------- InfluxDB connection settings --------
    influxdb: dict = field(
        default_factory=lambda: {
            "url": str,
            "bucket": str,
            "org": str,
            "token": str,
        }
    )

    _influxdb_retry_connect: int = field(init=False, repr=False, default=10)
    @property
    def influxdb_retry_connect(self) -> int:
        """ Get the InfluxDB retry connect count. """
        return self._influxdb_retry_connect

    @influxdb_retry_connect.setter
    def influxdb_retry_connect(self, value: int) -> None:
        value = int(value)
        if value < 0:
            raise ValueError("retry_connect must be ≥ 0")
        self._influxdb_retry_connect = value

    _influxdb_retry_delay: int = field(init=False, repr=False, default=5)
    @property
    def influxdb_retry_delay(self) -> int:
        """ Get the InfluxDB retry delay in seconds. """
        return self._influxdb_retry_delay

    @influxdb_retry_delay.setter
    def influxdb_retry_delay(self, value: int) -> None:
        value = int(value)
        if value < 1:
            raise ValueError("retry_delay must be ≥ 1")
        self._influxdb_retry_delay = value

    # -------- External IP detection --------
    _external_ip: ExternalIP = field(default_factory=ExternalIP, init=False, repr=False)
    @property
    def external_ip(self) -> str:
        """ Get the external IP of the machine. """
        try:
            return self._external_ip.get_ip() or ""

        except Exception: # pylint: disable=broad-except
            log.exception("Error fetching external IP")

        return ""

    # ------- Locking mechanism to prevent further modifications --------
    _locked: bool = field(init=False, repr=False, default=False)
    def __setattr__(self, name, value):
        if hasattr(self, "_locked") and self._locked:
            raise AttributeError("GlobalConfig is locked and cannot be modified")
        super().__setattr__(name, value)

    def lock(self):
        """Lock the config after initialization."""
        # self._locked = True

    def unlock(self):
        """Unlock the config for modifications."""
        self._locked = False


    @classmethod
    def build(cls) -> GlobalConfig:
        """
        Create the global config and load module sub-configs (npm, etc).
        """
        log.debug("Building GlobalConfig...")
        newcfg = cls()

        newcfg.proxy_logs = env_bool("PROXY_LOGS", True)
        newcfg.redirect_logs = env_bool("REDIRECT_LOGS", True)
        newcfg.public_logs = env_bool("PUBLIC_LOGS", True)   # Must be True for normal operation
        newcfg.internal_logs = env_bool("INTERNAL_LOGS", False)
        newcfg.monitoring_logs = env_bool("MONITORING_LOGS", False)

        newcfg.monitor_file_path = os.getenv('MONITORING_FILE_PATH', "/monitoringips.txt")

        for key, env_name, default in (
            ("url", "INFLUX_URL", ""),
            ("bucket", "INFLUX_BUCKET", "npmgrafstats"),
            ("org", "INFLUX_ORG", "npmgrafstats"),
            ("token", "INFLUX_TOKEN", ""),
        ):
            newcfg.influxdb[key] = os.getenv(env_name, default)

        newcfg.influxdb_retry_connect = env_int("INFLUX_RETRY_CONNECT", 10, 0)
        newcfg.influxdb_retry_delay = env_int("INFLUX_RETRY_DELAY", 5, 0)

        newcfg.api_abuseip_key = os.getenv('ABUSEIP_KEY', "")

        newcfg.geo_asn_db_path = os.getenv('GEO_ASN_DB_PATH', "/geolite/GeoLite2-ASN.mmdb")
        newcfg.geo_city_db_path = os.getenv('GEO_CITY_DB_PATH', "/geolite/GeoLite2-City.mmdb")

        log.debug(
            "Config:\n"
            " - proxy_logs=%s\n"
            " - redirect_logs=%s\n"
            " - public_logs=%s\n"
            " - internal_logs=%s\n"
            " - monitoring_logs=%s\n"
            " - geo_asn_db_path=%s (exists=%s)\n"
            " - geo_city_db_path=%s (exists=%s)\n"
            " - monitor_file_path=%s (exists=%s)\n"
            " - influxdb=%s\n"
            " - influxdb_retry_connect=%s\n"
            " - influxdb_retry_delay=%s\n\n",
            newcfg.proxy_logs,
            newcfg.redirect_logs,
            newcfg.public_logs,
            newcfg.internal_logs,
            newcfg.monitoring_logs,
            newcfg.geo_asn_db_path,
            newcfg.geo_asn_db_exists,
            newcfg.geo_city_db_path,
            newcfg.geo_city_db_exists,
            newcfg.monitor_file_path,
            newcfg.monitor_file_exists,
            "newcfg.influxdb",
            newcfg.influxdb_retry_connect,
            newcfg.influxdb_retry_delay
        )

        newcfg.lock()
        log.debug("GlobalConfig built successfully.")
        return newcfg

cfg = GlobalConfig.build()
