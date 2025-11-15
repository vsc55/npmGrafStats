#!/usr/bin/env python3
"""Main entry point for the npmGrafStats log collector."""
import sys
import os
import time
import threading

from config import cfg
from logwatcher import start_log_tasks
from connector.influx import InfluxClient
from connector.influx.fake_server import FakeInfluxServer
from utils import debug_msg

FAKE_SERVER_INFLUX = None


def run() -> None:
    """Main function to start log watchers based on configuration."""

    stop_event = threading.Event()

    url = cfg.influxdb['host']
    if cfg.influxdb['host'] == "fake":
        url = FAKE_SERVER_INFLUX.url

    cli_influx = InfluxClient.create(
        url=url,
        org="local-org",
        token="local-token",
        bucket="local-bucket",
        debug=False,
    )

    if cli_influx.test_connection():
        debug_msg("Connected to InfluxDB successfully.")
    else:
        retry_connect = cfg.influxdb_retry_connect
        retry_count = 0
        retry_delay = cfg.influxdb_retry_delay

        while retry_connect == 0 or retry_count < retry_connect:
            retry_count += 1
            msg_retry_total = retry_connect if retry_connect > 0 else "∞"
            msg_progress = f"{retry_count}/{msg_retry_total}"
            print(
                f"InfluxDB connection failed. Retrying {msg_progress} in {retry_delay} seconds...",
                flush=True,
            )
            time.sleep(retry_delay)

            if cli_influx.test_connection():
                print("Connected to InfluxDB successfully.", flush=True)
                break

        if cli_influx.is_available() is False:
            print("Failed to connect to InfluxDB after retries, exiting...", flush=True)
            return 1


    # Get log tasks from npm module or other sources
    tasks = cfg.all_log_tasks
    if not tasks:
        print("No log tasks configured, exiting...", flush=True)
        return 0

    # Start watchers for log tasks
    threads = start_log_tasks(tasks, stop_event, cli_influx)

    if threads:
        print(f"Started {len(threads)} log watcher threads.", flush=True)
    else:
        print("No log watcher threads started.", flush=True)
        return 0

    try:
        while True:
            time.sleep(60)

    except (SystemExit, KeyboardInterrupt):
        stop_event.set()
        print("Stopping log collector...", flush=True)

    except Exception as e:  # pylint: disable=broad-exception-caught
        stop_event.set()
        print(f"Error in main loop: {e}", file=sys.stderr, flush=True)
        return 1

    return 0

if __name__ == "__main__":
    # pylint: disable=line-too-long

    print(f"npmGrafStats Log Collector Version: {cfg.version}", flush=True)

    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("")
        print("Usage: python main.py [--help]")
        print("Options:")
        print("  --help    Show this help message and exit")
        print("")
        print("Env variables can be used to override configuration settings:")
        print("  INFLUX_RETRY_CONNECT    Number of times to retry InfluxDB connection (default: 10)")
        print("  INFLUX_RETRY_DELAY      Delay in seconds between InfluxDB connection retries (default: 5)")
        print("  INFLUX_HOST             InfluxDB host URL (e.g., http://localhost:8086)")
        print("  INFLUX_BUCKET           InfluxDB bucket name")
        print("  INFLUX_ORG              InfluxDB organization name")
        print("  INFLUX_TOKEN            InfluxDB authentication token")
        print("  ABUSEIP_KEY             API key for AbuseIPDB (if used)")
        print("  REDIRECTION_LOGS        Enable redirection logs (default: TRUE)")
        print("  INTERNAL_LOGS           Enable internal logs (default: FALSE)")
        print("  MONITORING_LOGS         Enable monitoring logs (default: FALSE)")
        print("")
        print("  REDIRECTION_LOGS, INTERNAL_LOGS, and MONITORING_LOGS allow (TRUE, FALSE, ONLY)")
        print("")
        sys.exit(0)

    if cfg.influxdb['host'] == "fake":
        debug_mode = os.getenv("DEBUG_SERVER_INFLUX_FAKE", str(cfg.debug)).lower() in ("1", "true", "yes", "on")
        FAKE_SERVER_INFLUX = FakeInfluxServer(debug=debug_mode)
        FAKE_SERVER_INFLUX.start()

    sys.exit(run())
