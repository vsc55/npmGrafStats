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


class LogWatcherManager:
    """Manages multiple log watching tasks and a single InfluxDB writer."""

    def __init__(self, tasks: Iterable[LogTask], cli_influx: InfluxClient) -> None:
        self._tasks = list(tasks)
        self._cli_influx = cli_influx

        self.stop_event = threading.Event()
        self.queue: Queue[InfluxRecord] = Queue()
        self.threads: list[threading.Thread] = []
        self._running = False

        # started[description][path] = Thread
        self._started: dict[str, dict[str, threading.Thread]] = {}
        self._lock = threading.Lock()

    # --- Public methods ---
    def start(self) -> None:
        """Start writer + watchers."""
        if self._running:
            return
        self._running = True

        # Writer InfluxDB thread
        writer_thread = threading.Thread(
            target=self._writer_loop,
            daemon=True,
            name="influx-writer",
        )
        writer_thread.start()
        self.threads.append(writer_thread)

        # Watchers
        for task in self._tasks:
            t = threading.Thread(
                target=self._watch_logs,
                args=(task,),
                daemon=True,
                name=f"watch-logs-{task.description}",
            )
            t.start()
            self.threads.append(t)
            time.sleep(0.5) # stagger thread starts


    def stop(self) -> None:
        """Signal all threads to stop and join them."""
        if not self._running:
            return

        print("[STOP] Stopping all log threads...", flush=True)
        self.stop_event.set()

        for t in self.threads:
            print(f"[STOP] Joining thread: {t.name} (alive={t.is_alive()})", flush=True)
            if t.is_alive():
                t.join()
            print(f"[STOP] Thread finished: {t.name} (alive={t.is_alive()})", flush=True)

        print("[STOP] All threads stopped.", flush=True)
        self._running = False


    def started_paths_snapshot(self) -> dict[str, list[str]]:
        """Return a snapshot of currently started log paths per task description."""
        with self._lock:
            return {
                desc: list(paths.keys())
                for desc, paths in self._started.items()
            }


    # --- Internal methods ---
    def _follow_file(self, path: str, task: LogTask) -> None:
        """Follow a log file and process new lines as they are added."""
        description = task.description
        processor = task.processor

        try:
            with open(path, "r", encoding="utf-8") as f:
                f.seek(0, os.SEEK_END)
                debug_msg(f"[{description}] Following: {path}")

                while not self.stop_event.is_set():
                    line = f.readline()
                    if not line:
                        time.sleep(TAIL_POLL_INTERVAL)
                        continue

                    try:
                        records = processor(line)

                    # Used broad Exception to avoid that an error in a line
                    # stops the file following. This will log the error, the thread
                    # will end and in the next watch_logs iteration it will be restarted.
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        print(
                            f"[{description}] Error processing line: {e}",
                            file=sys.stderr,
                            flush=True
                        )
                        continue

                    for rec in records:
                        self.queue.put(rec)

        except FileNotFoundError:
            print(f"[{description}] {path} disappeared", file=sys.stderr, flush=True)

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"[{description}] Error following {path}: {e}", file=sys.stderr, flush=True)


    def _writer_loop(self) -> None:
        """Single writer thread that consumes records from the queue and writes to InfluxDB."""
        debug_msg("[Influx] Writer thread started.")
        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                rec = self.queue.get(timeout=0.5)
            except Empty:
                continue

            try:
                debug_msg(f"[Influx] Writing record: {rec}")
                self._cli_influx.write_point(rec)
            except Exception as e:  # pylint: disable=broad-exception-caught
                print(
                    f"[Influx] Error writing record: {e}",
                    file=sys.stderr,
                    flush=True,
                )
            finally:
                self.queue.task_done()


    def _get_started_dict_for_task(self, description: str) -> dict[str, threading.Thread]:
        """Get or create the started dict for a given task description."""
        with self._lock:
            return self._started.setdefault(description, {})

    def _del_started_for_path(self, started: dict[str, threading.Thread], path: str) -> None:
        """Delete the started entry for a given path."""
        with self._lock:
            # Another thread may have touched on the dict, just in case
            if path in started:
                del started[path]


    def _watch_logs(self, task: LogTask) -> None:
        """Watch log files matching the pattern of a task and start following new ones."""
        # started: dict[str, threading.Thread] = {}
        pattern = task.pattern
        description = task.description

        # dict[path] = Thread for this task description
        started = self._get_started_dict_for_task(description)

        while not self.stop_event.is_set():
            # Clean up finished threads
            for path, th in list(started.items()):
                if not th.is_alive():
                    print(f"[{description}] Stopped following: {path} (thread ended)", flush=True)
                    self._del_started_for_path(started, path)

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
                    self._del_started_for_path(started, path)

                else:
                    print(f"[{description}] Detected new log file: {path}", flush=True)

                t = threading.Thread(
                    target=self._follow_file,
                    args=(path, task),
                    daemon=False,
                    name=f"follow-{description}-{os.path.basename(path)}",
                )
                t.start()
                started[path] = t
                with self._lock:
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

        # Clear started dict for this task
        with self._lock:
            self._started[description] = {}
