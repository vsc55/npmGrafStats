#!/usr/bin/env python3
"""Main entry point for the npmGrafStats log collector."""
import sys
import os
import time

from config import cfg
from logwatcher import LogWatcherManager
from connector.influx import InfluxClient
from connector.influx.exceptions import InfluxClientConfigError
from connector.influx.fake_server import FakeInfluxServer
from npm.simulator.log_generator import NginxLogGenerator
from utils import debug_msg

TRUTHY = ("1", "true", "yes", "on")

def test_connection(cli_influx: InfluxClient) -> bool:
    """Test connection to InfluxDB."""
    if not cli_influx.test_connection():
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
                break

        if cli_influx.is_available() is False:
            raise ValueError("Failed to connect to InfluxDB after retries")

    return True


def env_bool(name: str, default: bool = False) -> bool:
    """Get boolean value from environment variable."""
    val = os.getenv(name)
    if val is None:
        return bool(default)
    return str(val).lower() in TRUTHY


def run() -> None:
    """Main function to start log watchers based on configuration."""

    url = cfg.influxdb['host']

    fake_server : FakeInfluxServer | None = None
    fake_clients : NginxLogGenerator | None = None

    fake_server_debug = env_bool("DEBUG_SERVER_INFLUX_FAKE", cfg.debug)
    npm_log_fake_clients = env_bool("NPM_LOG_FAKE_CLIENTS", fake_server_debug)
    npm_log_fake_clients_debug = env_bool("NPM_LOG_FAKE_CLIENTS_DEBUG", cfg.debug)
    npm_log_fake_clients_file = os.getenv("NPM_LOG_FAKE_CLIENTS_FILE", "")

    if url == "fake":
        fake_server = FakeInfluxServer(debug=fake_server_debug)
        fake_server.start()
        url = fake_server.url

        if npm_log_fake_clients:
            fake_clients = NginxLogGenerator(debug=npm_log_fake_clients_debug)
            fake_clients.output = npm_log_fake_clients_file
            fake_clients.base_interval = 5.0 # seconds
            fake_clients.min_batch = 1
            fake_clients.max_batch = 5

    cli_influx = InfluxClient.create(
        url=url,
        org=cfg.influxdb['org'],
        token=cfg.influxdb['token'],
        bucket=cfg.influxdb['bucket'],
        debug=cfg.debug
    )

    try:
        test_connection(cli_influx)
        debug_msg("Connected to InfluxDB successfully.")

    except InfluxClientConfigError as e:
        print(f"{e}, exiting...", flush=True)
        return 1

    except ValueError as e:
        print(f"{e}, exiting...", flush=True)
        return 1

    # Get log tasks from npm module or other sources
    tasks = cfg.all_log_tasks
    if not tasks:
        print("No log tasks configured, exiting...", flush=True)
        return 0

    manager = LogWatcherManager(tasks, cli_influx)
    manager.start()

    if manager.threads:
        print(f"Started {len(manager.threads)} log watcher threads.", flush=True)
    else:
        print("No log watcher threads started.", flush=True)
        return 0

    if not fake_clients is None:
        fake_clients.start()

    exit_code = 0
    try:
        while True:
            time.sleep(60)
            # Simulate StopAll
            # raise KeyboardInterrupt

    except KeyboardInterrupt:
        exit_code = 0

    except SystemExit as e:
        exit_code = e.code if e.code is not None else 0

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error in main loop: {e}", file=sys.stderr, flush=True)
        exit_code = 1

    finally:
        if fake_clients is not None:
            print("[STOP] Stopping fake log clients...", flush=True)
            fake_clients.stop()
            print("[STOP] Fake log clients stopped.", flush=True)

        manager.stop()

        if fake_server is not None:
            print("[STOP] Stopping fake InfluxDB server...", flush=True)
            fake_server.stop()
            print("[STOP] Fake InfluxDB server stopped.", flush=True)

    return exit_code

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
        print("  INFLUX_BUCKET           InfluxDB bucket name (default: npmgrafstats)")
        print("  INFLUX_ORG              InfluxDB organization name (default: npmgrafstats)")
        print("  INFLUX_TOKEN            InfluxDB authentication token")
        print("  ABUSEIP_KEY             API key for AbuseIPDB (if used)")
        print("  REDIRECTION_LOGS        Enable redirection logs (default: TRUE)")
        print("  INTERNAL_LOGS           Enable internal logs (default: FALSE)")
        print("  MONITORING_LOGS         Enable monitoring logs (default: FALSE)")
        print("")
        print("  REDIRECTION_LOGS, INTERNAL_LOGS, and MONITORING_LOGS allow (TRUE, FALSE, ONLY)")
        print("")
        sys.exit(0)

    sys.exit(run())
