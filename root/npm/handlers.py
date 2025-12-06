#!/usr/bin/env python3
""" Handles log lines related to reverse proxies and redirections. """
from __future__ import annotations

import ipaddress
import re
import sys
from dataclasses import dataclass
from typing import Optional, TypedDict

from api.external.abuseipdb import AbuseIPDB, AbuseIPDBStatusReturn
from api.external.geoip2 import GeoIP2Client
from api.external.geoip2.exceptions import GeoIP2ConfigError, GeoIP2PathDBError
from config import GlobalConfig
from connector.influx import InfluxRecord
from utils import (Regex, TypeRegex, debug_msg, format_time, is_ip_in_range,
                   parse_float)

from .types import LogKind, TypeSendRecord


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
    target_ip: str
    asn: bool

class HandlersNPM:
    """ NPM Handlers class to manage log processing with configuration. """

    def __init__(self, line: str, mode: LogKind, config: GlobalConfig) -> None:
        self.config = config
        self.line = line
        self.mode = mode

    @property
    def debug(self) -> bool:
        """ Returns the debug setting from the configuration. """
        return self.config.debug


    def search_in_line(self, line: Optional[str] = None) -> dict[str, str]:
        """ Returns basic info about the handler. """
        if line is None:
            line = self.line


        log_regex = re.compile(
            r'^\[(?P<time_local>[^\]]+)\]\s+'
            r'(?:(?P<upstream_cache_status>\S+)\s+(?P<upstream_status>\S+)\s+)?'  # opcional (proxy)
            r'(?P<status>\d{3})\s+-\s+'
            r'(?P<method>\S+)\s+'
            r'(?P<scheme>\S+)\s+'
            r'(?P<host>\S+)\s+'
            r'"(?P<uri>[^"]+)"\s+'
            r'\[Client\s+(?P<client>[^\]]+)\]\s+'
            r'\[Length\s+(?P<length>[^\]]+)\]\s+'
            r'\[Gzip\s+(?P<gzip>[^\]]+)\]'
            r'(?:\s+\[Sent-to\s+(?P<sent_to>[^\]]+)\])?\s*'  # opcional (solo proxy)
            r'"(?P<user_agent>[^"]*)"\s+'
            r'"(?P<referer>[^"]*)"'
        )

        data: dict[str, str] = {}
        m = log_regex.match(line)
        if m:
            data = m.groupdict()
            # print(data)

        method = data.get("method", "")
        scheme = data.get("scheme", "")
        uri = data.get("uri", "")
        agent = data.get("user_agent", "")

        outside_ip, target_ip = self.extract_ips(line)
        return {
            "outside_ip": outside_ip,
            "target_ip": target_ip,
            "domain": self.extract_domain(line),
            "length": self.extract_length(line),
            "measurement_time": self.extract_measurement_time(line),
            "status_code": self.extract_status_code(line),
            "method": method,
            "scheme": scheme,
            "uri": uri,
            "agent": agent,
        }


    def extract_status_code(self, line: Optional[str] = None) -> int | None:
        """
        Extracts the status code from the log line.
        """
        if line is None:
            line = self.line

        parts: list[str] = line.strip().split()
        if len(parts) >= 4:
            m = re.search(r"\d+", parts[3])
            if m:
                return int(m.group(0))
        return None

    def extract_ips(self, line: Optional[str] = None) -> tuple[str | None, str | None]:
        """
        Extracts the outside IP and target IP from the log line.
        """
        if line is None:
            line = self.line

        pattern = Regex.compile_type(TypeRegex.IP)
        matches = [m.group(0) for m in pattern.finditer(line)]

        outside_ip = matches[0] if len(matches) > 0 else None
        target_ip = matches[1] if len(matches) > 1 else None
        return outside_ip, target_ip

    def extract_domain(self, line: Optional[str] = None) -> str:
        """
        Extracts the domain from the log line.
        """
        if line is None:
            line = self.line

        m = Regex.search_type(line, TypeRegex.DOMAIN)
        return m.group(0) if m else ""

    def extract_length(self, line: Optional[str] = None) -> int:
        """
        Extracts the length from the 14th field of the log line.
        Equivalente al bash:
        length=`echo $line | awk -F ' ' '{print$14}' | grep -m1 -o '[[:digit:]]*'`
        """
        if line is None:
            line = self.line

        parts = line.strip().split()
        if len(parts) >= 14:
            m = re.search(r"\d+", parts[13])
            if m:
                return int(m.group(0))
        return 0

    def extract_measurement_time(self, line: Optional[str] = None) -> str:
        """
        Extracts the measurement time from the log line and set it to ISO 8601 format.
        """
        if line is None:
            line = self.line

        measurement_time = line[1:27] if len(line) > 27 else ""
        measurement_time = format_time(measurement_time)
        return measurement_time or ""

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
            debug_msg(f"[Error] Invalid IP address: {ip}")
            return False

        except FileNotFoundError:
            debug_msg(f"[Error] Monitoring file not found: {path}")
            return False

        return is_ip_in_range(ip, list_ips)

    def _get_geoip2city(self, ip: str) -> dict[str, str | float]:
        """ Returns a GeoIP2Client instance. """

        try:
            db = self.config.geo_city_db_path
            geo_data = GeoIP2Client.get_city(ip, db, debug = self.debug, show=True)
            geo_return: dict[str, str | float] = {
                "key": geo_data["iso_code"],
                "City": geo_data["city"],
                "State": geo_data["state"],
                "Name": geo_data["country"],
                "latitude": parse_float(geo_data["latitude"], 0.0),
                "longitude": parse_float(geo_data["longitude"], 0.0),
            }

        except (GeoIP2PathDBError, GeoIP2ConfigError) as e:
            print(f"[Warn] GeoIP2 City lookup failed for IP {ip}: {e}", file=sys.stderr, flush=True)
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
            data = GeoIP2Client.get_asn(ip, db, debug = self.debug, show=True)

        except (GeoIP2PathDBError, GeoIP2ConfigError) as e:
            print(f"[Warn] GeoIP2 ASN lookup failed for IP {ip}: {e}", file=sys.stderr, flush=True)
            return {
                "asn": 0,
                "org": "Unknown",
            }

        return data

    def _get_abuseipdb(self, ip: str) -> dict[str, int]:
        """ Returns AbuseIPDB data for the given IP. """
        abuse_key = self.config.api_abuseip_key
        abuse_result = AbuseIPDB.check(ip, key=abuse_key, debug=self.debug, show=True)
        if abuse_result["status"] is AbuseIPDBStatusReturn.SUCCESS:
            abuse_confidence_score = abuse_result["data"].get("abuseConfidenceScore", 0)
            abuse_total_reports = abuse_result["data"].get("totalReports", 0)
            abuse_return = {
                "abuseConfidenceScore": str(abuse_confidence_score),
                "totalReports": str(abuse_total_reports),
            }
            return abuse_return

        return {}

    def parse_send_record(self, type_record: TypeSendRecord, record: SendRecord) -> ParsedRecord:
        """
        Parses the SendRecord and writes the point to InfluxDB.
        """
        ip = record.get("ip", "")
        domain = record.get("domain", "")
        length = int(record.get("length", 0))
        target_ip = record.get("target_ip", "")
        asn_flag = record.get("asn", False)
        status_code: int | None = record.get("status_code", None)
        method: str = record.get("method", "")
        scheme: str = record.get("scheme", "")
        uri: str = record.get("uri", "")
        agent: str = record.get("agent", "")

        # Set default values for tags and fields
        tags = {
            "Domain": domain,
            "IP": ip,
            "Target": target_ip
        }
        fields = tags.copy()
        fields.update({
            "length": length,
            "statuscode": status_code,
            "method": method,
            "scheme": scheme,
            "uri": uri,
            "agent": agent,
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
                    tags["Asn"] = asn_data["org"]
                    fields["Asn"] = asn_data["org"]

                abuse_result = self._get_abuseipdb(ip)
                if abuse_result:
                    tags.update(abuse_result)
                    fields.update(abuse_result)

            case _:
                pass

        return ParsedRecord(tags=tags, fields=fields)


def handle_line(line: str, mode: LogKind, config: GlobalConfig) -> list[InfluxRecord]:
    """ Handles a log line and returns InfluxDB records. """

    records: list[InfluxRecord] = []

    handlers = HandlersNPM(line, mode, config)
    result_line = handlers.search_in_line()

    outside_ip = result_line["outside_ip"]
    target_ip = result_line["target_ip"] or ""
    domain = result_line["domain"]
    length = result_line["length"]
    measurement_time = result_line["measurement_time"]

    debug_msg(
        f"[DEBUG] Parsed line - outside_ip: {outside_ip}, "
        f"target_ip: {target_ip}, domain: {domain}, "
        f"length: {length}, measurement_time: {measurement_time}"
    )

    if not outside_ip:
        debug_msg(f"[{mode}] No outside IP found in line")
        return records

    measurement: str | None = None
    send_type: TypeSendRecord | None = None
    send_record: SendRecord | None = None

    rec_length = length
    rec_target = target_ip
    rec_asn = True

    # 1) IP internal
    if handlers.is_internal_ip(outside_ip):
        # Igual que el bash: SOLO se manda a InternalRProxyIPs si INTERNAL_LOGS=TRUE,
        # pero NUNCA pasa a Monitoring o ReverseProxy/Redirections.

        if config.internal_logs is False:
            debug_msg(f"[{mode}] Internal IP-Source: {outside_ip} called: {domain}, skipping")
            return records

        debug_msg(f"[{mode}] Internal IP-Source: {outside_ip} called: {domain}")
        measurement = "InternalRProxyIPs"
        send_type = TypeSendRecord.LOCAL
        rec_asn = False

    # 2) IP Monitoring
    elif handlers.is_monitoring_ip(outside_ip):
        # Same as bash: if MONITORING_LOGS=TRUE it's sent to MonitoringRProxyIPs,
        # and NEVER falls to the else of normal connections.

        if config.monitoring_logs is False:
            debug_msg(f"[{mode}] Monitoring IP-Source: {outside_ip} called: {domain}, skipping")
            return records

        debug_msg(f"[{mode}] An excluded monitoring service checked: {domain}")
        measurement = "MonitoringRProxyIPs"
        send_type = TypeSendRecord.PUBLIC

    # 3) Rest of connections (public IPs)
    else:
         # Only process public IPs if PUBLIC_LOGS=TRUE
        if config.public_logs is False:
            debug_msg(f"[{mode}] Skipping public IP (PUBLIC_LOGS disabled): {outside_ip}")
            return records

        if mode == "proxy":
            measurement = "ReverseProxyConnections"
            rec_length = length
            rec_target = target_ip

        elif mode == "redirection":
            measurement = "Redirections"
            rec_length = 0
            rec_target = "redirect"

        else:
            print(f"[{mode}] Unknown mode, skipping line", file=sys.stderr, flush=True)
            return records

        debug_msg(f"[{mode}] Normal connection: {outside_ip} -> {domain}")
        send_type = TypeSendRecord.PUBLIC

    # if measurement and send_type are set, create the InfluxRecord
    if not (measurement and send_type):
        return records

    send_record = {
        "ip": outside_ip,
        "domain": domain,
        "length": rec_length,
        "target_ip": rec_target,
        "asn": rec_asn,
        "status_code": result_line["status_code"],
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
