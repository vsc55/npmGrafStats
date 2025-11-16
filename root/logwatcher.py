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
                daemon=False,
                name=f"follow-{description}-{os.path.basename(path)}",
            )
            t.start()
            started[path] = t

        time.sleep(SCAN_INTERVAL)

    # Stop all started follow threads
    for path, th in list(started.items()):
        print(
            f"[STOP][{description}] Joining follow thread for: {path} (alive={th.is_alive()})",
            flush=True
        )
        if th.is_alive():
            th.join(timeout=5.0)
        print(
            f"[STOP][{description}] Follow thread finished for: {path} (alive={th.is_alive()})",
            flush=True
        )



class LogWatcherManager:
    """Encapsula la gestión de hilos de log + writer de Influx."""

    def __init__(self, tasks: Iterable[LogTask], cli_influx: InfluxClient) -> None:
        self._tasks = list(tasks)
        self._cli_influx = cli_influx

        self.stop_event = threading.Event()
        self.queue: Queue[InfluxRecord] = Queue()
        self.threads: list[threading.Thread] = []
        self._started = False

    # --- Public methods ---
    def start(self) -> None:
        """Start writer + watchers."""
        if self._started:
            return
        self._started = True

        # Writer
        writer_thread = threading.Thread(
            target=influx_writer,
            args=(self.queue, self.stop_event, self._cli_influx),
            daemon=True,
            name="influx-writer",
        )
        writer_thread.start()
        self.threads.append(writer_thread)

        # Watchers
        for task in self._tasks:
            t = threading.Thread(
                target=watch_logs,
                args=(task, self.stop_event, self.queue),
                daemon=True,
                name=f"watch-logs-{task.description}",
            )
            t.start()
            self.threads.append(t)

    def stop(self) -> None:
        """Signal all threads to stop and join them."""
        if not self._started:
            return

        print("[STOP] Stopping all log threads...", flush=True)
        self.stop_event.set()

        for t in self.threads:
            print(f"[STOP] Joining thread: {t.name} (alive={t.is_alive()})", flush=True)
            if t.is_alive():
                t.join()
            print(f"[STOP] Thread finished: {t.name} (alive={t.is_alive()})", flush=True)

        print("[STOP] All threads stopped.", flush=True)
        self._started = False
