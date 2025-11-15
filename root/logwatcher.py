#!/usr/bin/env python3
"""Log watching module to monitor log files and process new lines."""
from __future__ import annotations

import os
import sys
import time
import glob
import threading
from dataclasses import dataclass
from typing import Callable, Iterable
from queue import Queue, Empty

from utils import debug_msg
from connector.influx import InfluxRecord, InfluxClient

LineProcessor = Callable[[str], list[InfluxRecord]]

TAIL_POLL_INTERVAL = 0.2   # seconds between checks for new lines in follow_file
SCAN_INTERVAL = 5.0        # seconds between scans for new log files in watch_logs

@dataclass(frozen=True)
class LogTask:
    """Defines a log watching task."""
    pattern: str             # p.ej. "/logs/proxy-host-*_access.log"
    description: str         # only for logging purposes
    processor: LineProcessor # function handle_line(line)


def follow_file(
        path: str,
        description: str,
        processor: LineProcessor,
        queue: Queue[InfluxRecord],
        stop_event: threading.Event
) -> None:
    """Follow a log file and process new lines as they are added."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            debug_msg(f"[{description}] Following: {path}")

            while not stop_event.is_set():
                line = f.readline()
                if not line:
                    time.sleep(TAIL_POLL_INTERVAL)
                    continue

                try:
                    records = processor(line)

                except Exception as e: # pylint: disable=broad-exception-caught
                    print(
                        f"[{description}] Error processing line: {e}",
                        file=sys.stderr,
                        flush=True
                    )
                    continue

                for rec in records:
                    queue.put(rec)

    except FileNotFoundError:
        print(f"[{description}] {path} disappeared", file=sys.stderr, flush=True)

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"[{description}] Error following {path}: {e}", file=sys.stderr, flush=True)


def influx_writer(
        queue: Queue[InfluxRecord],
        stop_event: threading.Event,
        cli_influx: InfluxClient,
) -> None:
    """Single writer thread that consumes records from the queue and writes to InfluxDB."""
    while not stop_event.is_set() or not queue.empty():
        try:
            rec = queue.get(timeout=0.5)
        except Empty:
            continue

        try:
            cli_influx.write_point(rec)

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(
                f"[Influx] Error writing record: {e}",
                file=sys.stderr,
                flush=True,
            )
        finally:
            queue.task_done()


def watch_logs(
        task: LogTask,
        stop_event: threading.Event,
        cli_influx: InfluxClient,
        queue: Queue[InfluxRecord]
) -> None:
    """Watch log files matching the pattern of a task and start following new ones."""
    started: dict[str, threading.Thread] = {}
    pattern = task.pattern
    description = task.description
    processor = task.processor

    while not stop_event.is_set():
        # Clean up finished threads
        for path, th in list(started.items()):
            if not th.is_alive():
                print(f"[{description}] Stopped following: {path} (thread ended)", flush=True)
                del started[path]

        debug_msg(f"[{description}] Scanning for log files matching: {pattern}")
        debug_msg(f"[{description}] Already following: {len(started)} files")

        for path in sorted(glob.glob(pattern)):
            if not os.path.isfile(path):
                debug_msg(f"[{description}] Ignoring non-regular file: {path}")
                continue

            if path in started:
                if started[path].is_alive():
                    debug_msg(f"[{description}] Already following: {path}")
                    continue

                print(f"[{description}] Restarting following: {path}", flush=True)
                del started[path]

            else:
                print(f"[{description}] Detected new log file: {path}", flush=True)

            t = threading.Thread(
                target=follow_file,
                args=(path, description, processor, queue, stop_event),
                daemon=True,
            )
            t.start()
            started[path] = t

        time.sleep(SCAN_INTERVAL)

def start_log_tasks(
        tasks: Iterable[LogTask],
        stop_event: threading.Event,
        cli_influx: InfluxClient,
) -> list[threading.Thread]:
    """Arranca un thread por LogTask y los devuelve para posible inspección."""
    threads: list[threading.Thread] = []

    # Shared InfluxDB write queue
    queue: Queue[InfluxRecord] = Queue()

    # Start InfluxDB writer thread
    writer_thread = threading.Thread(
        target=influx_writer,
        args=(queue, stop_event, cli_influx),
        daemon=True,
    )
    writer_thread.start()
    threads.append(writer_thread)

    for task in list(tasks): # copy to avoid issues if tasks is modified
        t = threading.Thread(
            target=watch_logs,
            args=(
                task,
                stop_event,
                cli_influx,
                queue
            ),
            daemon=True,
        )
        t.start()
        threads.append(t)

    return threads
