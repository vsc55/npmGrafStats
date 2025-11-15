#!/usr/bin/env python3
"""Main entry point for the npmGrafStats log collector."""
import sys
import time
import threading

from config import cfg
from logwatcher import start_log_tasks
from connector.influx import InfluxClient

def run() -> None:
    """Main function to start log watchers based on configuration."""

    stop_event = threading.Event()

    cli_influx = InfluxClient.create(
        url=cfg.influx_url,
        org=cfg.influx_org,
        token=cfg.influx_token,
        bucket=cfg.influx_bucket,
        debug=cfg.debug,
    )
    
    if cli_influx.test_connection():
        print("InfluxDB OK, podemos escribir puntos.")
    else:
        print("No se puede conectar a InfluxDB.")


    # Get log tasks from npm module or other sources
    tasks = cfg.all_log_tasks
    if not tasks:
        print("No log tasks configured, exiting...", flush=True)
        return 0

    # Start watchers for log tasks
    threads = start_log_tasks(tasks, stop_event)

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
    print(f"npmGrafStats Log Collector Version: {cfg.version}", flush=True)

    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("")
        print("Usage: python main.py [--help]")
        print("Options:")
        print("  --help    Show this help message and exit")
        sys.exit(0)

    sys.exit(run())
