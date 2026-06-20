#!/usr/bin/env python3
"""AbuseIPDB application interface."""

import ipaddress

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
    if abuse is None:
        log.warning("AbuseIPDB: No instance available; skipping check for '%s'.", ip)
        return {}

    # If no API key is configured, the feature is simply disabled. Skip quietly
    # instead of calling the API once per public IP and logging a warning each
    # time (which would flood the log).
    if not abuse.is_key_set:
        log.debug("AbuseIPDB: No API key configured; skipping check for '%s'.", ip)
        return {}

    # Validate the IP locally without mutating the shared singleton's state.
    # The instance is used concurrently by many writer threads, so setting
    # abuse.ip here would race with other threads; pass the IP per-call instead.
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        log.warning("AbuseIPDB: Invalid IP address '%s' provided.", ip)
        return {}

    try:
        # Do not force a disk save per IP here: writing+fsync'ing the whole cache
        # file on every new IP (from many writer threads) is very expensive. The
        # cache is flushed periodically from the main loop and on exit (atexit).
        data = abuse.api_check(ip=ip)
    except AbuseIPDBConfigError as e:
        # Almost always a missing/empty ABUSEIP_KEY.
        log.warning("AbuseIPDB: Configuration error checking IP '%s': %s", ip, e)
        return {}
    except AbuseIPDBNetworkError as e:
        log.warning(
            "AbuseIPDB: Network error checking IP '%s': %s", ip, e.original or e
        )
        return {}
    except AbuseIPDBResponseError as e:
        # e.g. 401 invalid key, 422 invalid IP. Surface status + API detail.
        detail = e.api_errors[0].get("detail") if e.api_errors else str(e)
        log.warning(
            "AbuseIPDB: API error checking IP '%s' (status=%s): %s",
            ip, e.status_code, detail
        )
        return {}

    if data["status"] is not AbuseIPDBStatusReturn.SUCCESS:
        log.warning("AbuseIPDB: Unsuccessful status returned for IP '%s'.", ip)
        log.warning("AbuseIPDB: Status details: %s", data)
        return {}

    payload = data.get("data") or {}
    abuse_confidence_score = payload.get("abuseConfidenceScore", 0)
    abuse_total_reports = payload.get("totalReports", 0)

    return {
        "abuse_confidence_score": str(abuse_confidence_score),
        "abuse_total_reports": str(abuse_total_reports),
    }

def save_abuse_instance() -> None:
    """ Save the AbuseIPDB instance data to disk """
    log.info("Saving AbuseIPDB cache data...")
    abuse = get_abuse_instance()
    if abuse is not None:
        abuse.maybe_save_cache()
        log.info("AbuseIPDB cache data saved successfully.")
    else:
        log.warning("AbuseIPDB: No instance to save.")
