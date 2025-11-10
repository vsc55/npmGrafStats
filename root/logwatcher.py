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
from config import cfg
from connector.influx_client import cli_influx, InfluxRecord

# LineHandler = Callable[[str], None]
LineProcessor = Callable[[str], list[InfluxRecord]]

@dataclass(frozen=True)
class LogTask:
    """Defines a log watching task."""
    pattern: str             # p.ej. "/logs/proxy-host-*_access.log"
    description: str         # only for logging purposes
    processor: LineProcessor # function handle_line(line)

def follow_file(path: str, description: str, processor: LineProcessor) -> None:
    """Follow a log file and process new lines as they are added."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            print(f"[{description}] Following: {path}", flush=True)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.2)
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
                    try:
                        cli_influx.write_point(
                            measurement=rec.measurement,
                            tags=rec.tags,
                            fields=rec.fields,
                            timestamp=rec.timestamp,
                        )
                    except Exception as e: # pylint: disable=broad-exception-caught
                        print(
                            f"[{description}] Error writing to Influx: {e}",
                            file=sys.stderr,
                            flush=True
                        )

    except FileNotFoundError:
        print(f"[{description}] {path} disappeared", file=sys.stderr, flush=True)

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"[{description}] Error following {path}: {e}", file=sys.stderr, flush=True)


def watch_logs(task: LogTask, stop_event: threading.Event) -> None:
    """Watch log files matching the pattern of a task and start following new ones."""
    started: set[str] = set()
    pattern = task.pattern
    description = task.description
    processor = task.processor

    while not stop_event.is_set():
        if cfg.debug:
            print(f"[{description}] Scanning for log files matching: {pattern}", flush=True)
            print(f"[{description}] Already following: {len(started)} files", flush=True)

        for path in sorted(glob.glob(pattern)):
            if path in started:
                if cfg.debug:
                    print(f"[{description}] Already following: {path}", flush=True)
                continue

            if not os.path.isfile(path):
                if cfg.debug:
                    print(f"[{description}] Ignoring non-regular file: {path}", flush=True)
                continue

            print(f"[{description}] Detected log file: {path}", flush=True)
            t = threading.Thread(
                target=follow_file,
                args=(path, description, processor),
                daemon=True,
            )
            t.start()
            started.add(path)

        time.sleep(5.0)

def start_log_tasks(
        tasks: Iterable[LogTask], stop_event: threading.Event
) -> list[threading.Thread]:
    """Arranca un thread por LogTask y los devuelve para posible inspección."""
    threads: list[threading.Thread] = []

    for task in tasks:
        t = threading.Thread(
            target=watch_logs,
            args=(task, stop_event),
            daemon=True,
        )
        t.start()
        threads.append(t)

    return threads
