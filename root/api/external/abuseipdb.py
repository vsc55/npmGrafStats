#!/usr/bin/env python3
""" Utility functions for AbuseIPDB integration. """
import json
import requests
from config import cfg


def is_abuseipdb_key_configured() -> bool:
    """
    Check if the AbuseIPDB API key is configured.
    Returns:
        bool: True if the API key is set, False otherwise.
    """
    abuseip_key = cfg.api_abuseip_key
    return bool(abuseip_key)

def check_abuseipdb(ip_address: str) -> dict:
    """
    Check an IP address against AbuseIPDB.
    Args:
        ip_address (str): The IP address to check.
    Returns:
        dict: The response data from AbuseIPDB.
    """
    abuseip_key = cfg.api_abuseip_key
    if not abuseip_key:
        return {}

    timeout = 10
    url = 'https://api.abuseipdb.com/api/v2/check'
    headers = {
        'Accept': 'application/json',
        'Key': abuseip_key
    }
    params  = {
        'ipAddress': ip_address,
        'maxAgeInDays': '90'
    }

    response = requests.request(
        method='GET',
        url=url,
        headers=headers,
        params=params,
        timeout=timeout
    )

    data = response.json().get("data", {}) or {}
    if response.status_code != 200:
        print(f"[Error] AbuseIPDB request for {ip_address}: {response.status_code}", flush=True)
    else:
        if not data:
            print(f"[Warning] AbuseIPDB returned no data for {ip_address}", flush=True)

    if cfg.debug:
        print(json.dumps(data, indent=4, sort_keys=True), flush=True)

    return data
