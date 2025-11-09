#!/usr/bin/env python3
""" Global configuration for the application. """
from __future__ import annotations
import os
import re
import subprocess
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Callable, Iterable, TYPE_CHECKING, Any
from enum import Enum
from urllib.request import urlopen
from utils.external_ip import ExternalIP

if TYPE_CHECKING:
    from npm.config import NpmConfig
    from npm.logtasks import get_log_tasks
    from logwatcher import LogTask
else:
    LogTask = Any # Dummy type for LogTask when not type checking

LogTasksProvider = Callable[[], Iterable[LogTask]]

class LogMode(str, Enum):
    """ Enumeration for log modes. """
    TRUE = "TRUE"     # Habilitado
    FALSE = "FALSE"   # Deshabilitado
    ONLY = "ONLY"     # Solo este tipo

    @classmethod
    def from_env(cls, name: str, default: "LogMode" = "FALSE") -> "LogMode":
        """ Create LogMode from environment variable. """
        val = os.getenv(name, default).strip().upper()
        return cls[val] if val in cls.__members__ else cls[default]

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
            r"(10([\.][0-9]{1,3}){3})|"
            r"(192\.168([0-9]{1,3}[\.]){2}[0-9]{1,3})|"
            r"(172\.(1[6-9]|2[0-9]|3[0-1])([\.][0-9]{1,3}){2})"
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
        regex_pattern = getattr(self, typeregex.value, None)
        if regex_pattern is None:
            raise ValueError(f"Type of regex not valid: {typeregex}")

        pattern = re.compile(regex_pattern)
        return pattern.search(text)

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
    geo_asn_db_path: str = "/geolite/GeoLite2-ASN.mmdb"
    @property
    def geo_asn_db_exists(self) -> bool:
        """ Check if GeoASN DB exists. """
        return os.path.isfile(self.geo_asn_db_path)

    geo_city_db_path: str = "/geolite/GeoLite2-City.mmdb"
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
            "token": str
        }
    )

    # -------- RegexIP instance --------
    regex = Regex()
    domain_regex: str = r"([a-z0-9\-]*\.){1,3}?[a-z0-9\-]*\.[A-Za-z]{2,6}"

    # -------- Flags globals --------
    redirection_logs: LogMode = LogMode.TRUE
    internal_logs: LogMode = LogMode.FALSE
    monitoring_logs: LogMode = LogMode.FALSE

    # -------- External IP detection --------
    _external_ip: ExternalIP = field(init=False, repr=False, default=None)
    @property
    def external_ip(self) -> str:
        """ Get the external IP of the machine. """
        if self._external_ip is None:
            object.__setattr__(self, "_external_ip", ExternalIP())
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
    _log_providers: list[LogTasksProvider] = field(default_factory=list)

    def register_log_tasks_provider(self, provider: LogTasksProvider) -> None:
        """ Register a log tasks provider. """
        self._log_providers.append(provider)

    @property
    def all_log_tasks(self) -> list[LogTask]:
        """ Get all log tasks from registered providers. """
        tasks: list[LogTask] = []
        for provider in self._log_providers:
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

    @classmethod
    def build(cls) -> "GlobalConfig":
        """
        Create the global config and load module sub-configs (npm, etc).
        """
        newcfg = cls()
        newcfg.redirection_logs = LogMode.from_env("REDIRECTION_LOGS", "TRUE")
        newcfg.internal_logs = LogMode.from_env("INTERNAL_LOGS", "FALSE")
        newcfg.monitoring_logs = LogMode.from_env("MONITORING_LOGS", "FALSE")

        newcfg.influxdb["host"] = os.getenv('INFLUX_HOST') or ""
        newcfg.influxdb["bucket"] = os.getenv('INFLUX_BUCKET') or ""
        newcfg.influxdb["org"] = os.getenv('INFLUX_ORG') or ""
        newcfg.influxdb["token"] = os.getenv('INFLUX_TOKEN') or ""

        newcfg.api_abuseip_key = os.getenv('ABUSEIP_KEY') or ""

        try:
            from npm.config import NpmConfig # pylint: disable=import-outside-toplevel
            from npm.logtasks import get_log_tasks as npm_get_log_tasks # pylint: disable=import-outside-toplevel
            newcfg.npm = NpmConfig(newcfg)
            # newcfg.register_log_tasks_provider(npm_get_log_tasks)
            newcfg._log_providers.append(npm_get_log_tasks)

        except ImportError as e:
            raise ImportError("Failed to import npm module for configuration.") from e

        # In the future, you could add more modules:
        # from other_module.logtasks import get_log_tasks as other_get_log_tasks
        # newcfg._log_providers.append(other_get_log_tasks)

        newcfg.lock()
        return newcfg

cfg = GlobalConfig.build()
