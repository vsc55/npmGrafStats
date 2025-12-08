#!/usr/bin/env python3
"""AbuseIPDB application interface."""
import atexit
import os

from api.external.abuseipdb import (AbuseIPDB, AbuseIPDBConfigError,
                                    AbuseIPDBNetworkError,
                                    AbuseIPDBResponseError,
                                    AbuseIPDBStatusReturn)
from logger import get_logger

log = get_logger(__name__)

abuse_ip_global: AbuseIPDB | None = None

def get_abuse_instance(key: str | None = None) -> AbuseIPDB | None:
    """ Return a singleton instance of AbuseIPDB """
    global abuse_ip_global # pylint: disable=global-statement
    if abuse_ip_global is None:
        abuse_ip_global = AbuseIPDB()

    if abuse_ip_global is None:
        log.warning("AbuseIPDB: Could not create AbuseIPDB instance.")
        return None

    if key is not None:
        abuse_ip_global.key = key

    if abuse_ip_global.key is None:
        log.warning("AbuseIPDB: No API key provided.")

    return abuse_ip_global

def checking(ip: str, key: str | None = None) -> dict[str, str]:
    """ Check an IP address against AbuseIPDB and return relevant data """
    abuse = get_abuse_instance(key=key)

    try:
        abuse.ip = ip
    except ValueError:
        log.warning("AbuseIPDB: Invalid IP address '%s' provided.", ip)
        return {}

    try:
        data = abuse.api_check(force_save=True)
    except (AbuseIPDBConfigError, AbuseIPDBNetworkError, AbuseIPDBResponseError):
        log.warning("AbuseIPDB: Error occurred while checking IP '%s'.", ip)
        return {}

    if data["status"] is not AbuseIPDBStatusReturn.SUCCESS:
        log.warning("AbuseIPDB: Unsuccessful status returned for IP '%s'.", ip)
        log.warning("AbuseIPDB: Status details: %s", data)
        return {}

    payload = data.get("data") or {}
    abuse_confidence_score = payload.get("abuseConfidenceScore", 0)
    abuse_total_reports = payload.get("totalReports", 0)

    return {
        "abuseConfidenceScore": str(abuse_confidence_score),
        "totalReports": str(abuse_total_reports),
    }

@atexit.register
def save_abuse_instance() -> None:
    """ Save the AbuseIPDB instance data to disk """
    log.info("Saving AbuseIPDB cache data...")
    abuse = get_abuse_instance()
    if abuse is not None:
        abuse.close()
        log.info("AbuseIPDB cache data saved.")
    else:
        log.warning("AbuseIPDB: No instance to save.")

# only register the atexit if not mode tested
# if not os.getenv("ABUSEIP_DISABLE_ATEXIT"):
#     atexit.register(save_abuse_instance)
