#!/usr/bin/env python3
"""Main entry point for the npmGrafStats log collector."""
import os
import sys
import time

from config import cfg
from connector.influx import InfluxClient
from connector.influx.exceptions import InfluxClientConfigError
from connector.influx.fake_server import FakeInfluxServer
from logger import get_logger
from logwatcher import LogWatcherManager
from npm.simulator.log_generator import NginxLogGenerator
from tasks import TasksConfig
from utils import env_bool, env_int, parse_float

log = get_logger(__name__)

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
            log.warning(
                "InfluxDB connection failed. Retrying %s in %d seconds...",
                msg_progress,
                retry_delay
            )
            time.sleep(retry_delay)

            if cli_influx.test_connection():
                break

        if cli_influx.is_available() is False:
            raise ValueError("Failed to connect to InfluxDB after retries")

    return True


def run() -> int:
    """Main function to start log watchers based on configuration."""

    log.info("Starting...")

    fake_server_enable = env_bool("FAKE_SERVER", False)

    fake_client_enable = env_bool("FAKE_CLIENT", False)
    fake_client_file = os.getenv("FAKE_CLIENT_FILE", "")
    fake_client_interval: float = parse_float(os.getenv("FAKE_CLIENT_INTERVAL", None), 5.0)
    fake_client_min_batch: int = env_int("FAKE_CLIENT_MIN_BATCH", 1, 1)
    fake_client_max_batch: int = env_int("FAKE_CLIENT_MAX_BATCH", 8, 1)

    url = cfg.influxdb['url']

    fake_server : FakeInfluxServer | None = None
    fake_clients : NginxLogGenerator | None = None

    if url == "fake" or fake_server_enable:
        fake_server = FakeInfluxServer()
        fake_server.start()
        url = fake_server.url

    if fake_client_enable:
        fake_clients = NginxLogGenerator()
        fake_clients.output = fake_client_file
        fake_clients.base_interval = fake_client_interval # seconds
        fake_clients.min_batch = fake_client_min_batch
        fake_clients.max_batch = fake_client_max_batch

    cli_influx = InfluxClient.create(
        url=url,
        org=cfg.influxdb['org'],
        token=cfg.influxdb['token'],
        bucket=cfg.influxdb['bucket']
    )
    try:
        test_connection(cli_influx)
        log.info("Connected to InfluxDB successfully.")

    except InfluxClientConfigError:
        log.exception("InfluxDB configuration error")
        return 1

    except ValueError:
        log.exception("InfluxDB connection error")
        return 1


    tasks = TasksConfig(config=cfg, auto_discover=True)
    if tasks.count == 0:
        log.info("No log tasks configured, exiting...")
        return 0

    manager = LogWatcherManager(tasks, cli_influx)
    manager.start()

    if manager.threads:
        log.info("Started %d log watcher threads.", len(manager.threads))
    else:
        log.info("No log watcher threads started.")
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

    except Exception:
        log.exception("Error in main loop")
        exit_code = 1
        raise

    finally:
        if fake_clients is not None:
            log.info("[STOP] Stopping fake log clients...")
            fake_clients.stop()
            log.info("[STOP] Fake log clients stopped.")

        manager.stop()

        if fake_server is not None:
            log.info("[STOP] Stopping fake InfluxDB server...")
            fake_server.stop()
            log.info("[STOP] Fake InfluxDB server stopped.")

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
        print("")
        print("  DEBUG                   Enable debug mode")
        print("  LOG_PATH                Path to log file")
        print("  LOG_LEVEL               Global log level")
        print("  LOG_CONSOLE_LEVEL       Console log level")
        print("  LOG_FILE_LEVEL          File log level")
        sys.exit(0)

    sys.exit(run())
