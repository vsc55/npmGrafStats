#!/usr/bin/env python3
""" Handles log lines related to reverse proxies and redirections. """
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Any, Optional, TypedDict

from api.external.abuseipdb.abuseipdb_app import checking
from api.external.geoip2 import GeoIP2Client
from api.external.geoip2.exceptions import GeoIP2ConfigError, GeoIP2PathDBError
from config import GlobalConfig
from connector.influx import InfluxRecord
from logger import get_logger
from utils import Regex, TypeRegex, format_time, is_ip_in_range, parse_float

from .types import LogKind, TypeSendRecord

log = get_logger(__name__)


@dataclass
class ParsedRecord:
    """ Parsed record structure for tags and fields. """
    tags: dict[str, str]
    fields: dict[str, object]

class SendRecord(TypedDict):
    """ Structure for sending IP information records. """
    ip: str
    domain: str
    length: int
    target: str
    asn: bool
    status_code: str
    upstream_statuscode: str
    upstream_cache_statuscode: str
    method: str
    scheme: str
    uri: str
    agent: str


class HandlersNPM:
    """ NPM Handlers class to manage log processing with configuration. """

    def __init__(self, line: str, mode: LogKind, config: GlobalConfig) -> None:
        self.config = config
        self.line = line
        self.mode = mode


    def normalize_nginx_str(self, value: str | None, default: str | None = "") -> str | None:
        """ Normalizes NGINX log fields, converting None or '-' to default string. """
        if value in (None, "-"):
            return default
        return value

    def normalize_nginx_int(self, value: str | None, default: int | None = 0) -> int | None:
        """ Normalizes NGINX log fields, converting None or '-' to default integer. """
        if value in (None, "-"):
            return default
        return int(value)

    def normalize_nginx_time(self, value: str | None) -> str:
        """ Normalizes NGINX log time fields to ISO 8601 format or empty string. """
        if not value or value == "-":
            return ""
        return format_time(value) or ""

    def normalize_nginx_ip(self, value: str | None, default: str | None = None) -> str | None:
        """ Normalizes NGINX log IP fields, extracting the first valid IP or returning default. """
        if value in (None, "-"):
            return default

        pattern = Regex.compile_type(TypeRegex.IP)
        matches = [m.group(0) for m in pattern.finditer(value)]

        return matches[0] if len(matches) > 0 else None

    def normalize_nginx_domain(self, value: str | None, default: str | None = None) -> str | None:
        """
        Normalizes NGINX log domain fields, extracting the first valid domain or returning default.
        """
        if value in (None, "-"):
            return default

        pattern = Regex.compile_type(TypeRegex.DOMAIN)
        matches = [m.group(0) for m in pattern.finditer(value)]

        return matches[0] if len(matches) > 0 else None

    def search_in_line(self, line: Optional[str] = None) -> dict[str, str]:
        """ Returns basic info about the handler. """
        if line is None:
            line = self.line

        log_regex = re.compile(
            r'^\[(?P<time_local>[^\]]+)\]\s+'
            r'(?:(?P<upstream_cache_status>\S+)\s+(?P<upstream_status>\S+)\s+)?'  # only proxy
            r'(?P<status>\d{3})\s+-\s+'
            r'(?P<method>\S+)\s+'
            r'(?P<scheme>\S+)\s+'
            r'(?P<host>\S+)\s+'
            r'"(?P<uri>[^"]+)"\s+'
            r'\[Client\s+(?P<client>[^\]]+)\]\s+'
            r'\[Length\s+(?P<length>[^\]]+)\]\s+'
            r'\[Gzip\s+(?P<gzip>[^\]]+)\]'
            r'(?:\s+\[Sent-to\s+(?P<sent_to>[^\]]+)\])?\s*'  # only proxy
            r'"(?P<user_agent>[^"]*)"\s+'
            r'"(?P<referer>[^"]*)"'
        )

        data: dict[str, str] = {}
        m = log_regex.match(line)
        if m:
            data = m.groupdict()
            log.debug("Parsed log data: %s", data)

        time_local: str = self.normalize_nginx_time(data.get("time_local"))

        upstream_cache_statuscode: str = self.normalize_nginx_str(data.get("upstream_cache_status"))
        upstream_statuscode: str = self.normalize_nginx_str(data.get("upstream_status"))
        statuscode: str = self.normalize_nginx_str(data.get("status"))

        method: str = self.normalize_nginx_str(data.get("method"))
        scheme: str = self.normalize_nginx_str(data.get("scheme"))
        host: str = self.normalize_nginx_domain(data.get("host"))
        uri: str = self.normalize_nginx_str(data.get("uri"))

        client_ip = self.normalize_nginx_ip(data.get("client"), None)
        length: int = self.normalize_nginx_int(data.get("length"), 0)
        sent_to_ip = self.normalize_nginx_ip(data.get("sent_to"), None)
        sent_to_domain = self.normalize_nginx_domain(data.get("sent_to"), None)
        agent: str = self.normalize_nginx_str(data.get("user_agent"))

        sent_to = sent_to_ip if sent_to_ip else sent_to_domain

        return {
            "outside_ip": client_ip,
            "target": sent_to,
            "target_ip": sent_to_ip,
            "target_domain": sent_to_domain,
            "measurement_time": time_local,
            "upstream_cache_statuscode": upstream_cache_statuscode,
            "upstream_statuscode": upstream_statuscode,
            "status_code": statuscode,
            "method": method,
            "scheme": scheme,
            "domain": host,
            "uri": uri,
            "length": length,
            "agent": agent,
        }

    def is_internal_ip(self, ip: str) -> bool:
        """
        Returns True if the IP is private (RFC1918) or matches the host's external IP.
        """
        if not ip:
            return False

        # IP privada (usa regex global)
        if  Regex.fullmatch_type(ip, TypeRegex.IP_PRIVATE):
            return True

        # If the IP address is the same as our public IP address, we assume this
        # public IP address as local.
        if ip == self.config.external_ip:
            return True

        return False

    def is_monitoring_ip(self, ip: str) -> bool:
        """
        Checks if the given IP is in the monitoring exclusion list.
        """
        if not ip or not self.config.monitor_file_exists:
            return False

        path = self.config.monitor_file_path
        try:
            ipaddress.ip_address(ip)
            with open(path, "r", encoding="utf-8") as f:
                list_ips = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        except ValueError:
            log.error("Invalid IP address: %s", ip)
            return False

        except FileNotFoundError:
            log.error("Monitoring file not found: %s", path)
            return False

        return is_ip_in_range(ip, list_ips)

    def _get_geoip2city(self, ip: str) -> dict[str, str | float]:
        """ Returns a GeoIP2Client instance. """

        try:
            db = self.config.geo_city_db_path
            geo_data = GeoIP2Client.get_city(ip, db)
            geo_return: dict[str, str | float] = {
                "key": geo_data["iso_code"],
                "city": geo_data["city"],
                "state": geo_data["state"],
                "name": geo_data["country"],
                "latitude": parse_float(geo_data["latitude"], 0.0),
                "longitude": parse_float(geo_data["longitude"], 0.0),
            }

        except (GeoIP2PathDBError, GeoIP2ConfigError):
            log.warning("GeoIP2 City lookup failed for IP '%s'", ip)
            geo_return = {}
            # geo_return : dict[str, str | float] = {
            #     "key": "",
            #     "City": "",
            #     "State": "",
            #     "Name": "",
            #     "latitude": 0.0,
            #     "longitude": 0.0
            # }

        return geo_return

    def _get_geoip2asn(self, ip: str, asn_flag: bool) -> dict[str, object]:
        """ Returns a GeoIP2Client ASN instance. """
        if not asn_flag:
            return {}

        try:
            db = self.config.geo_asn_db_path
            data = GeoIP2Client.get_asn(ip, db)

        except (GeoIP2PathDBError, GeoIP2ConfigError):
            log.warning("GeoIP2 ASN lookup failed for IP '%s'", ip)
            return {
                "asn": 0,
                "org": "Unknown",
            }

        return data

    def _get_abuseipdb(self, ip: str) -> dict[str, int]:
        """ Returns AbuseIPDB data for the given IP. """
        abuse_return = checking(ip)
        return abuse_return

    def _rename_keys_title_case(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Renames dictionary keys using Python's built-in str.title().

        Examples:
            'statuscode'     -> 'Statuscode'
            'user_agent'     -> 'User_Agent'
            'geo.location'   -> 'Geo.Location'
            'USER.NAME_test' -> 'User.Name_Test'
        """
        return {k.title(): v for k, v in data.items()}

    def parse_send_record(self, type_record: TypeSendRecord, record: SendRecord) -> ParsedRecord:
        """
        Parses the SendRecord and writes the point to InfluxDB.
        """
        ip = record.get("ip", "")
        domain = record.get("domain", "")
        length = int(record.get("length", 0))
        target = record.get("target", "")
        asn_flag = record.get("asn", False)
        status_code: str = record.get("status_code", "")
        upstream_statuscode: str = record.get("upstream_statuscode", "")
        upstream_cache_statuscode: str = record.get("upstream_cache_statuscode", "")
        method: str = record.get("method", "")
        scheme: str = record.get("scheme", "")
        uri: str = record.get("uri", "")
        agent: str = record.get("agent", "")

        # Set default values for tags and fields
        tags = {
            "domain": domain,
            "ip": ip,
            "target": target,
            "statuscode": status_code,
            "upstream_statuscode": upstream_statuscode,
            "upstream_cache_statuscode": upstream_cache_statuscode,
            "method": method,
            "scheme": scheme,
            "agent": agent,
        }
        fields = tags.copy()
        fields.update({
            "domain": domain,
            "ip": ip,
            "target": target,
            "statuscode": status_code,
            "upstream_statuscode": upstream_statuscode,
            "upstream_cache_statuscode": upstream_cache_statuscode,
            "method": method,
            "scheme": scheme,
            "agent": agent,
            "uri": uri,
            "length": length,
            "metric": 1
        })

        match type_record:
            case TypeSendRecord.LOCAL:
                # No geo/ASN/abuse lookup for local/internal
                pass

            case TypeSendRecord.PUBLIC:
                geo_city_data = self._get_geoip2city(ip)
                if geo_city_data:
                    tags.update(geo_city_data)
                    fields.update(geo_city_data)

                    # For tags, use string values for lat/lon
                    tags["latitude"] = str(tags['latitude'])
                    tags["longitude"] = str(tags['longitude'])

                asn_data = self._get_geoip2asn(ip, asn_flag)
                if asn_data:
                    tags["asn"] = asn_data["org"]
                    fields["asn"] = asn_data["org"]

                abuse_result = self._get_abuseipdb(ip)
                if abuse_result:
                    tags.update(abuse_result)
                    fields.update(abuse_result)

            case _:
                pass

        # Rename keys from tags to title case
        tags = self._rename_keys_title_case(tags)

        return ParsedRecord(tags=tags, fields=fields)


def handle_line(line: str, mode: LogKind, config: GlobalConfig) -> list[InfluxRecord]:
    """ Handles a log line and returns InfluxDB records. """

    records: list[InfluxRecord] = []

    handlers = HandlersNPM(line, mode, config)
    result_line = handlers.search_in_line()

    outside_ip = result_line["outside_ip"]
    target = result_line["target"]
    domain = result_line["domain"]
    length = result_line["length"]
    measurement_time = result_line["measurement_time"]

    log.debug(
        "Parsed line - outside_ip: %s, target: %s, domain: %s, length: %d, measurement_time: %s",
        outside_ip,
        target,
        domain,
        length,
        measurement_time,
    )

    if not outside_ip:
        log.warning("[%s] No outside IP found in line", mode)
        return records

    measurement: str | None = None
    send_type: TypeSendRecord | None = None
    send_record: SendRecord | None = None

    rec_length = length
    rec_target = target
    rec_asn = True

    # 1) IP internal
    if handlers.is_internal_ip(outside_ip):
        # Same as bash: only if INTERNAL_LOGS=TRUE it's sent to InternalRProxyIPs,
        # and NEVER to Monitoring or ReverseProxy/Redirections.

        if config.internal_logs is False:
            log.info("[%s] Internal IP-Source: %s called: %s, skipping", mode, outside_ip, domain)
            return records

        log.info("[%s] Internal IP-Source: %s called: %s", mode, outside_ip, domain)
        measurement = "InternalRProxyIPs"
        send_type = TypeSendRecord.LOCAL
        rec_asn = False

    # 2) IP Monitoring
    elif handlers.is_monitoring_ip(outside_ip):
        # Same as bash: if MONITORING_LOGS=TRUE it's sent to MonitoringRProxyIPs,
        # and NEVER falls to the else of normal connections.

        if config.monitoring_logs is False:
            log.info("[%s] Monitoring IP-Source: %s called: %s, skipping", mode, outside_ip, domain)
            return records

        log.info("[%s] An excluded monitoring service checked: %s", mode, domain)
        measurement = "MonitoringRProxyIPs"
        send_type = TypeSendRecord.PUBLIC

    # 3) Rest of connections (public IPs)
    else:
         # Only process public IPs if PUBLIC_LOGS=TRUE
        if config.public_logs is False:
            log.info("[%s] Skipping public IP (PUBLIC_LOGS disabled): %s", mode, outside_ip)
            return records

        if mode == "proxy":
            measurement = "ReverseProxyConnections"
            rec_length = length
            rec_target = target

        elif mode == "redirection":
            measurement = "Redirections"
            rec_length = 0
            rec_target = "redirect"

        else:
            log.warning("[%s] Unknown mode, skipping line", mode)
            return records

        log.info("[%s] Normal connection: %s -> %s", mode, outside_ip, domain)
        send_type = TypeSendRecord.PUBLIC

    # if measurement and send_type are set, create the InfluxRecord
    if not (measurement and send_type):
        return records

    send_record = {
        "ip": outside_ip,
        "domain": domain,
        "length": rec_length,
        "target": rec_target,
        "asn": rec_asn,
        "status_code": result_line["status_code"],
        "upstream_statuscode": result_line["upstream_statuscode"],
        "upstream_cache_statuscode": result_line["upstream_cache_statuscode"],
        "method": result_line["method"],
        "scheme": result_line["scheme"],
        "uri": result_line["uri"],
        "agent": result_line["agent"],
    }

    rec = handlers.parse_send_record(send_type, send_record)
    records.append(
        InfluxRecord(
            measurement=measurement,
            tags=rec.tags,
            fields=rec.fields,
            timestamp=measurement_time,
        )
    )
    return records
