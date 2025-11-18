#!/usr/bin/env python3
"""Main entry point for the npmGrafStats log collector."""
import os
import sys
import time

from config import cfg
from connector.influx import InfluxClient
from connector.influx.exceptions import InfluxClientConfigError
from connector.influx.fake_server import FakeInfluxServer
from logwatcher import LogWatcherManager
from npm.simulator.log_generator import NginxLogGenerator
from tasks import TasksConfig
from utils import debug_msg, env_bool, env_int, parse_float


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


def run() -> int:
    """Main function to start log watchers based on configuration."""

    fake_server_enable = env_bool("FAKE_SERVER", False)
    fake_server_debug = env_bool("FAKE_SERVER_DEBUG", cfg.debug)

    fake_client_enable = env_bool("FAKE_CLIENT", False)
    fake_client_debug = env_bool("FAKE_CLIENT_DEBUG", cfg.debug)
    fake_client_file = os.getenv("FAKE_CLIENT_FILE", "")
    fake_client_interval: float =  parse_float(os.getenv("FAKE_CLIENT_INTERVAL", None), 5.0)
    fake_client_min_batch: int =   env_int("FAKE_CLIENT_MIN_BATCH", 1, 1)
    fake_client_max_batch: int =  env_int("FAKE_CLIENT_MAX_BATCH", 8, 1)

    url = cfg.influxdb['url']

    fake_server : FakeInfluxServer | None = None
    fake_clients : NginxLogGenerator | None = None

    if url == "fake" or fake_server_enable:
        fake_server = FakeInfluxServer(debug=fake_server_debug)
        fake_server.start()
        url = fake_server.url

    if fake_client_enable:
        fake_clients = NginxLogGenerator(debug=fake_client_debug)
        fake_clients.output = fake_client_file
        fake_clients.base_interval = fake_client_interval # seconds
        fake_clients.min_batch = fake_client_min_batch
        fake_clients.max_batch = fake_client_max_batch

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


    tasks = TasksConfig(config=cfg, auto_discover=True)
    if tasks.count == 0:
        print("No log tasks configured, exiting...", flush=True)
        return 0

    manager = LogWatcherManager(tasks, cli_influx)
    manager.start()

    if manager.threads:
        print(f"Started {len(manager.threads)} log watcher threads.", flush=True)
    else:
        print("No log watcher threads started.", flush=True)
        return 0

    if fake_clients is not None:
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

    except Exception as e:
        print(f"Error in main loop: {e}", file=sys.stderr, flush=True)
        exit_code = 1
        raise

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
        print("  INFLUX_URL              InfluxDB host URL (e.g., http://localhost:8086)")
        print("  INFLUX_BUCKET           InfluxDB bucket name (default: npmgrafstats)")
        print("  INFLUX_ORG              InfluxDB organization name (default: npmgrafstats)")
        print("  INFLUX_TOKEN            InfluxDB authentication token")
        print("")
        print("  ABUSEIP_KEY             API key for AbuseIPDB (if used)")
        print("")
        print("  PROXY_LOGS              Enable proxy logs")
        print("  REDIRECT_LOGS           Enable redirection logs")
        print("  MONITORING_LOGS         Enable monitoring logs")
        print("  PUBLIC_LOGS             Enable public logs")
        print("  INTERNAL_LOGS           Enable internal logs")
        print("")
        print("  GEO_ASN_DB_PATH         Path to GeoIP ASN database file")
        print("  GEO_CITY_DB_PATH        Path to GeoIP City database file")
        sys.exit(0)

    sys.exit(run())
