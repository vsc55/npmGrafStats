#!/usr/bin/env python3
""" Handles log lines related to reverse proxies and redirections. """
from __future__ import annotations
import re
import ipaddress
from typing import Literal, TypedDict
from enum import Enum
from config import cfg, LogMode, TypeRegex
from utils import debug_msg, is_ip_in_range, format_time
from connector.influx_client import InfluxRecord
from api.external.abuseipdb import AbuseIPDB, AbuseIPDBStatusReturn
from api.external.geoip2 import GeoIP2Client, GeoIP2CityResult, GeoIP2ASNResult

LogKind = Literal["proxy", "redirection"]

class TypeSendRecord(str, Enum):
    """ Enumeration for send record types. """
    LOCAL = "local"
    PUBLIC = "public"

class SendRecord(TypedDict):
    """ Structure for sending IP information records. """
    ip: str
    domain: str
    length: int
    target_ip: str
    asn: bool

def _extract_ips(line: str) -> tuple[str | None, str | None]:
    """
    Extracts the first (outsideip) and second IP (targetip) from the line,
    using the combined regex cfg.regex.ip (IPv4 + IPv6).
    """
    pattern = cfg.regex.compile(TypeRegex.IP)
    matches = list(pattern.finditer(line))

    outside_ip = matches[0].group(0) if len(matches) >= 1 else None
    target_ip = matches[1].group(0) if len(matches) >= 2 else None
    return outside_ip, target_ip

def _extract_domain(line: str) -> str:
    """
    Extracts the domain from the log line.
    """
    m = cfg.regex.search(line, TypeRegex.DOMAIN)
    return m.group(0) if m else ""

def _extract_length(line: str) -> int:
    """
    Extracts the length from the 14th field of the log line.
    Equivalente al bash:
      length=`echo $line | awk -F ' ' '{print$14}' | grep -m1 -o '[[:digit:]]*'`
    """
    parts = line.split()
    if len(parts) >= 14:
        m = re.search(r"\d+", parts[13])
        if m:
            try:
                return int(m.group(0))
            except ValueError:
                return 0
    return 0

def _extract_measurement_time(line: str) -> str:
    """
    Extracts the measurement time from the log line and set it to ISO 8601 format.
    """
    measurement_time = line[1:27] if len(line) > 27 else ""
    measurement_time = format_time(measurement_time)
    return measurement_time or ""

def _is_internal_ip(ip: str) -> bool:
    """
    Returns True if the IP is private (RFC1918) or matches the host's external IP.
    """
    if not ip:
        return False

    # IP privada (usa regex global)
    if cfg.regex.search(ip, TypeRegex.IP_PRIVATE):
        return True

    # IP externa propia
    if ip == cfg.external_ip:
        return True

    return False

def _is_monitoring_ip(ip: str) -> bool:
    """
    Checks if the given IP is in the monitoring exclusion list.
    """
    if not ip or not cfg.monitor_file_exists:
        return False

    try:
        ipaddress.ip_address(ip)
        with open(cfg.monitor_file_path, "r", encoding="utf-8") as f:
            list_ips = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    except ValueError:
        debug_msg(f"[Error] Invalid IP address: {ip}")
        return False

    except FileNotFoundError:
        debug_msg(f"[Error] Monitoring file not found: {cfg.monitor_file_path}")
        return False

    return is_ip_in_range(ip, list_ips)

def _parse_float(value: str, default: float | None = None) -> float | None:
    """
    Tries to parse a string to float, returns None if fails.
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_send_record(
        type_record: TypeSendRecord, record: SendRecord
) -> tuple[dict[str, str], dict[str, object]]:
    """
    Parses the SendRecord and writes the point to InfluxDB.
    """
    ip = record.get("ip", "")
    domain = record.get("domain", "")
    length = int(record.get("length", 0))
    target_ip = record.get("target_ip", "")
    asn_flag = record.get("asn", False)

    # Set default values for tags and fields
    tags = {
        "Domain": domain,
        "IP": ip,
        "Target": target_ip
    }
    fields = tags.copy()
    fields.update({
        "duration": length,
        "metric": 1
    })

    match type_record:
        case TypeSendRecord.LOCAL:
            # No geo/ASN/abuse lookup for local/internal
            pass

        case TypeSendRecord.PUBLIC:

            geo_data = GeoIP2Client.get_city(
                ip,
                db = cfg.geo_city_db_path,
                debug = cfg.debug,
                show=True
            )
            geo_entries  = {
                "key": geo_data["iso_code"],
                "City": geo_data["city"],
                "State": geo_data["state"],
                "Name": geo_data["country"],
                "latitude": _parse_float(geo_data["latitude"], 0.0),
                "longitude": _parse_float(geo_data["longitude"], 0.0),
            }
            tags.update(geo_entries)
            fields.update(geo_entries)

            # For tags, use string values for lat/lon
            tags["latitude"] = str(tags['latitude'])
            tags["longitude"] = str(tags['longitude'])

            if asn_flag:
                asn_data = GeoIP2Client.get_asn(
                    ip,
                    db = cfg.geo_asn_db_path,
                    debug = cfg.debug,
                    show=True
                )
                if asn_data:
                    tags["Asn"] = asn_data["org"]
                    fields["Asn"] = asn_data["org"]

            abuse_result = AbuseIPDB.check(ip, key=cfg.api_abuseip_key, debug=cfg.debug, show=True)
            if abuse_result["status"] is AbuseIPDBStatusReturn.SUCCESS:
                abuse_entries = {
                    "abuseConfidenceScore": abuse_result["data"].get("abuseConfidenceScore") or 0,
                    "totalReports": abuse_result["data"].get("totalReports") or 0,
                }
                tags.update(abuse_entries)
                fields.update(abuse_entries)

        case _:
            pass


    return tags, fields

def handle_line(line: str, mode: LogKind) -> list[InfluxRecord]:
    """
    Implements the logic of:
      - sendips.sh              (mode="proxy")
      - sendredirectionips.sh   (mode="redirection")

    Order of processing:
      1) IP Internal  -> InternalRProxyIPs (if INTERNAL_LOGS != FALSE)
      2) IP Monitoring  -> MonitoringRProxyIPs (if MONITORING_LOGS != FALSE)
      3) Rest of connections:
         - proxy       -> ReverseProxyConnections
         - redirection -> Redirections
    
    Returns:
        list[InfluxRecord]: An empty list (for compatibility with InfluxRecord handler).

    """
    records: list[InfluxRecord] = []

    outside_ip, target_ip = _extract_ips(line)
    domain = _extract_domain(line)
    length = _extract_length(line)
    measurement_time = _extract_measurement_time(line)

    if not outside_ip:
        debug_msg(f"[{mode}] No outside IP found in line")
        return records


    measurement: str | None = None
    send_type: TypeSendRecord | None = None
    send_record: SendRecord | None = None


    # 1) IP internal
    if _is_internal_ip(outside_ip):
        debug_msg(f"[{mode}] Internal IP-Source: {outside_ip} called: {domain}")

        # Igual que el bash: SOLO se manda a InternalRProxyIPs si INTERNAL_LOGS=TRUE,
        # pero NUNCA pasa a Monitoring o ReverseProxy/Redirections.
        if cfg.internal_logs is not LogMode.FALSE:
            measurement = "InternalRProxyIPs"
            send_type = TypeSendRecord.LOCAL
            send_record = {
                "ip": outside_ip,
                "domain": domain,
                "length": length,
                "target_ip": target_ip or "",
                "asn": False,
            }

    # 2) IP Monitoring
    elif _is_monitoring_ip(outside_ip):
        debug_msg(f"[{mode}] An excluded monitoring service checked: {domain}")

        # Igual que el bash: si MONITORING_LOGS=TRUE se envía a MonitoringRProxyIPs,
        # y NUNCA cae al else de conexiones normales.
        if cfg.monitoring_logs is not LogMode.FALSE:
            measurement = "MonitoringRProxyIPs"
            send_type = TypeSendRecord.PUBLIC
            send_record = {
                "ip": outside_ip,
                "domain": domain,
                "length": length,
                "target_ip": target_ip or "",
                "asn": True,
            }

    # 3) Rest of connections
    else:
        if mode == "proxy":
            # sendips.sh: ReverseProxyConnections
            measurement = "ReverseProxyConnections"
            rec_length = length
            rec_target = target_ip or ""
        elif mode == "redirection":
            # sendredirectionips.sh: Redirections, length=0, target="redirect"
            measurement = "Redirections"
            rec_length = 0
            rec_target = "redirect"
        else:
            print(f"[{mode}] Unknown mode, skipping line", file=sys.stderr, flush=True)
            return records

        debug_msg(f"[{mode}] Normal connection: {outside_ip} -> {domain}")
        send_type = TypeSendRecord.PUBLIC
        send_record = {
            "ip": outside_ip,
            "domain": domain,
            "length": rec_length,
            "target_ip": rec_target,
            "asn": True,
        }

    # if measurement and send_type and send_record are set, create the InfluxRecord
    if not (measurement and send_type and send_record):
        return records


    tags, fields = _parse_send_record(send_type, send_record)
    records.append(
        InfluxRecord(
            measurement=measurement,
            tags=tags,
            fields=fields,
            timestamp=measurement_time,
        )
    )
    return records
