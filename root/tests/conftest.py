#!/usr/bin/env python3
""" Config tests """
import os

# Disable AbuseIPDB atexit handler during tests
# api.external.abuseipdb.abuseipdb_app.py > save_abuse_instance
os.environ["ABUSEIP_DISABLE_ATEXIT"] = "1"
