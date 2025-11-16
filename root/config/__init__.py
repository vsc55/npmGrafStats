#!/usr/bin/env python3
""" Global configuration for the application. """
from __future__ import annotations
import os
import re
import importlib
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING, Any
from pathlib import Path
from enum import Enum
from urllib.request import urlopen
from utils.external_ip import ExternalIP

if TYPE_CHECKING:
    from npm.config import NpmConfig
    from logwatcher import LogTask
else:
    LogTask = Any # Dummy type for LogTask when not type checking

LogTasksProviderRef = tuple[str, str]  # (module, function_name)

class LogMode(str, Enum):
    """ Enumeration for log modes. """
    TRUE = "TRUE"     # Habilitado
    FALSE = "FALSE"   # Deshabilitado
    ONLY = "ONLY"     # Solo este tipo

    @classmethod
    def from_env(cls, name: str, default: "LogMode" | str = FALSE) -> "LogMode":
        """ Create LogMode from environment variable. """
        # Normalize default
        if isinstance(default, LogMode):
            default_mode = default
        else:
            # if is string --> convert to enum
            default_mode = cls[default.strip().upper()]

        raw = os.getenv(name)
        if raw is None:
            return default_mode

        val = raw.strip().upper()
        return cls.__members__.get(val, default_mode)

class TypeRegex(str, Enum):
    """ Enumeration for regex types. """
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    IP = "ip"
    IP_PRIVATE = "ip_private"
    DOMAIN = "domain"

@dataclasses.dataclass
class Regex:
    """ Regex patterns for IP addresses. """
    @property
    def ipv4(self) -> str:
        """ Regex pattern for IPv4 addresses. """
        return r"([0-9]{1,3}\.){3}[0-9]{1,3}"

    @property
    def ipv6(self) -> str:
        """ Regex pattern for IPv6 addresses. """
        return (
            r"([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|"
            r"([0-9a-fA-F]{1,4}:){1,7}:|"
            r"([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|"
            r"([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|"
            r"([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|"
            r"([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|"
            r"([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|"
            r"[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|"
            r":((:[0-9a-fA-F]{1,4}){1,7}|:)|"
            r"fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|"
            r"::(ffff(:0{1,4}){0,1}:){0,1}"
            r"((25[0-5]|(2[0-4]|1[0-9]|[0-9])\.){3}(25[0-5]|(2[0-4]|1[0-9]|[0-9])))|"
            r"([0-9a-fA-F]{1,4}:){1,4}:"
            r"((25[0-5]|(2[0-4]|1[0-9]|[0-9])\.){3}(25[0-5]|(2[0-4]|1[0-9]|[0-9])))"
    )

    @property
    def ip(self) -> str:
        """ Combined IPv4 and IPv6 regex pattern. """
        return f"({self.ipv4}|{self.ipv6})"

    @property
    def ip_private(self) -> str:
        """ Regex pattern for private IP addresses. """
        return (
            r"(10(?:\.[0-9]{1,3}){3})|"                                             # 10.0.0.0/8
            r"(192\.168(?:\.[0-9]{1,3}){2})|"                                       # 192.168.0.0/16
            r"(172\.(?:1[6-9]|2[0-9]|3[0-1])(?:\.[0-9]{1,3}){2})|"                  # 172.16.0.0–172.31.0.0
            r"(127(?:\.[0-9]{1,3}){3})|"                                            # Loopback
            r"(169\.254(?:\.[0-9]{1,3}){2})|"                                       # Link-local
            r"(100\.(?:6[4-9]|[7-9][0-9]|1[0-1][0-9]|12[0-7])(?:\.[0-9]{1,3}){2})"  # CGNAT 100.64–100.127
        )

    @property
    def domain(self) -> str:
        """
        Regex pattern for domain names. 
        E.g., example.com, sub.example.co.uk
        """
        return r"([a-z0-9\-]*\.){1,3}?[a-z0-9\-]*\.[A-Za-z]{2,6}"

    def search(self, text: str, typeregex: TypeRegex) -> Optional[re.Match]:
        """ Search for a regex pattern in the given text. """
        pattern = self.compile(typeregex)
        return pattern.search(text)

    def fullmatch(self, text: str, typeregex: TypeRegex) -> Optional[re.Match]:
        """ Fullmatch for a regex pattern in the given text. """
        pattern = self.compile(typeregex)
        return pattern.fullmatch(text)

    def compile(self, typeregex: TypeRegex) -> re.Pattern:
        """ Compile and return the regex pattern for the given type. """
        regex_pattern = getattr(self, typeregex.value, None)
        if regex_pattern is None:
            raise ValueError(f"Type of regex not valid: {typeregex}")

        return re.compile(regex_pattern)

@dataclass(frozen=False)
class GlobalConfig:
    """ Global configuration """

    # -------- General settings --------
    debug: bool = False

    # -------- Application version --------
    @property
    def version(self) -> str:
        """ Get the version of the application. """
        return "3.0.0"

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
    monitor_file_path: str = "/monitoringips.txt"
    @property
    def monitor_file_exists(self) -> bool:
        """ Check if Monitor file exists. """
        return os.path.isfile(self.monitor_file_path)

    # -------- InfluxDB connection settings --------
    influxdb: dict = field(
        default_factory=lambda: {
            "host": str,
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


    # -------- RegexIP instance --------
    regex = Regex()
    domain_regex: str = r"([a-z0-9\-]*\.){1,3}?[a-z0-9\-]*\.[A-Za-z]{2,6}"

    # -------- Flags globals --------
    redirection_logs: LogMode = LogMode.TRUE
    internal_logs: LogMode = LogMode.FALSE
    monitoring_logs: LogMode = LogMode.FALSE

    # -------- External IP detection --------
    _external_ip: ExternalIP = field(default_factory=ExternalIP, init=False, repr=False)
    @property
    def external_ip(self) -> str:
        """ Get the external IP of the machine. """
        try:
            return self._external_ip.get_ip() or ""

        except Exception as e: # pylint: disable=broad-except
            if self.debug:
                print(f"Error fetching external IP: {e}", flush=True)

        return ""

    # -------- Sub-config to modules --------
    npm: Optional["NpmConfig"] = None
    # in the future: apache: Optional["ApacheConfig"] = None, etc.

    # ------- Log tasks providers --------
    _log_providers: list[LogTasksProviderRef] = field(default_factory=list)

    def register_log_tasks_provider(self, module: str, func: str) -> None:
        """ Register a log tasks provider. """
        self._log_providers.append((module, func))

    @property
    def all_log_tasks(self) -> list[LogTask]:
        """ Get all log tasks from registered providers. """
        tasks: list["LogTask"] = []
        for module_name, func_name in self._log_providers:
            mod = importlib.import_module(module_name)
            provider = getattr(mod, func_name)
            tasks.extend(provider())
        return tasks

    # ------- Post-initialization --------
    def __post_init__(self):
        pass

    # ------- Locking mechanism to prevent further modifications --------
    _locked: bool = field(init=False, repr=False, default=False)
    def __setattr__(self, name, value):
        if hasattr(self, "_locked") and self._locked:
            raise AttributeError("GlobalConfig is locked and cannot be modified")
        super().__setattr__(name, value)

    def lock(self):
        """Lock the config after initialization."""
        self._locked = True

    def unlock(self):
        """Unlock the config for modifications."""
        self._locked = False


    @staticmethod
    def get_env_int(name: str, default: int, min_value: int | None = None) -> int:
        """ Get an integer value from environment variable with validation. """
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default

        try:
            value = int(raw)
        except ValueError:
            return default

        if min_value is not None and value < min_value:
            return min_value

        return value

    @classmethod
    def build(cls) -> "GlobalConfig":
        """
        Create the global config and load module sub-configs (npm, etc).
        """
        newcfg = cls()
        newcfg.debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes", "on")

        newcfg.redirection_logs = LogMode.from_env("REDIRECTION_LOGS", LogMode.TRUE)
        newcfg.internal_logs = LogMode.from_env("INTERNAL_LOGS", LogMode.FALSE)
        newcfg.monitoring_logs = LogMode.from_env("MONITORING_LOGS", LogMode.FALSE)

        for key, env_name, default in (
            ("host", "INFLUX_HOST", ""),
            ("bucket", "INFLUX_BUCKET", "npmgrafstats"),
            ("org", "INFLUX_ORG", "npmgrafstats"),
            ("token", "INFLUX_TOKEN", ""),
        ):
            newcfg.influxdb[key] = os.getenv(env_name, default)

        newcfg.influxdb_retry_connect = newcfg.get_env_int("INFLUX_RETRY_CONNECT", 10, min_value=0)
        newcfg.influxdb_retry_delay = newcfg.get_env_int("INFLUX_RETRY_DELAY", 5, min_value=0)

        newcfg.api_abuseip_key = os.getenv('ABUSEIP_KEY', "")

        newcfg.geo_asn_db_path = os.getenv('GEO_ASN_DB_PATH') or "/geolite/GeoLite2-ASN.mmdb"
        newcfg.geo_city_db_path = os.getenv('GEO_CITY_DB_PATH') or "/geolite/GeoLite2-City.mmdb"

        try:
            from npm.config import NpmConfig # pylint: disable=import-outside-toplevel
            newcfg.npm = NpmConfig(newcfg)
            newcfg.register_log_tasks_provider("npm.logtasks", "get_log_tasks")

        except ImportError as e:
            raise ImportError("Failed to import npm module for configuration.") from e

        # In the future, you could add more modules:
        # from other_module.logtasks import get_log_tasks as other_get_log_tasks
        # newcfg._log_providers.append(other_get_log_tasks)

        newcfg.lock()
        return newcfg

cfg = GlobalConfig.build()
