#!/usr/bin/env python3
"""Log watching module to monitor log files and process new lines."""
from __future__ import annotations

import glob
import os
import sys
import threading
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Optional

from connector.influx import InfluxClient, InfluxRecord
from tasks import LogTask, TasksConfig
from utils import debug_msg

TAIL_POLL_INTERVAL = 0.2   # seconds between checks for new lines in follow_file
SCAN_INTERVAL = 5.0        # seconds between scans for new log files in watch_logs


# Autoscaling writer thread parameters
MIN_WRITERS = 4
MAX_WRITERS = 48
HIGH_Q = 100      # if exceeds this, add more writer threads
LOW_Q  = 100      # if below this, remove writer threads
SENTINEL = object()  # marker to signal writer threads to stop


@dataclass
class QueueItem:
    """Item in the log processing queue."""
    line: Optional[str] = None
    task: Optional[LogTask] = None

class LogWatcherManager:
    """Manages multiple log watching tasks and a single InfluxDB writer."""

    def __init__(self, tasks: TasksConfig, cli_influx: InfluxClient) -> None:
        self._tasks = tasks
        self._cli_influx = cli_influx

        self.stop_event = threading.Event()
        self.queue: Queue[QueueItem] = Queue()
        self.threads: list[threading.Thread] = []
        self._running = False

        self._started: dict[str, dict[str, threading.Thread]] = {}
        self._lock = threading.Lock()

        self._writer_threads: list[threading.Thread] = []
        self._writer_id = 0

    # --- Public methods ---
    def start(self) -> None:
        """Start writer + watchers."""
        if self._running:
            return
        self._running = True

        # Autoscaling writers (influx and processing)
        for _ in range(MIN_WRITERS):
            self._start_writer()

        threading.Thread(
            target=self._autoscaler_loop,
            name="influx-writer-autoscaler",
            daemon=True
        ).start()

        # Watchers
        for task in list(self._tasks.tasks):
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
        try:
            with open(path, "r", encoding="utf-8") as f:
                f.seek(0, os.SEEK_END)
                debug_msg(f"[{task.description}] Following: {path}")

                while not self.stop_event.is_set():
                    line = f.readline()
                    if not line:
                        time.sleep(TAIL_POLL_INTERVAL)
                        continue

                    self.queue.put(QueueItem(line=line, task=task))

        except FileNotFoundError:
            print(f"[{task.description}] {path} disappeared", file=sys.stderr, flush=True)

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"[{task.description}] Error following {path}: {e}", file=sys.stderr, flush=True)


    def _autoscaler_loop(self) -> None:
        """Autoscaler loop to adjust the number of writer threads based on queue size."""

        while not self.stop_event.is_set():
            q = self.queue.qsize()
            n = len(self._writer_threads)

            # scale up
            if q > HIGH_Q and n < MAX_WRITERS:
                print(
                    f"[Autoscaler] Scaling up writers: Queue={q}, Writers={n} -> {n+1}",
                    flush=True
                )
                self._start_writer()

            # scale down
            elif q < LOW_Q and n > MIN_WRITERS:
                print(
                    f"[Autoscaler] Scaling down writers: Queue={q}, Writers={n} -> {n-1}",
                    flush=True
                )
                # send a sentinel -> one writer will stop itself
                self.queue.put(SENTINEL)
                # optional: clean up dead threads
                self._writer_threads = [t for t in self._writer_threads if t.is_alive()]

            time.sleep(1)

    def _start_writer(self):
        name = f"writer-thread-{self._writer_id}"
        self._writer_id += 1
        t = threading.Thread(target=self._writer_loop, name=name, daemon=True)
        t.start()
        self._writer_threads.append(t)


    def _writer_loop(self) -> None:
        """Single writer thread that consumes records from the queue and writes to InfluxDB."""
        name = threading.current_thread().name
        debug_msg(f"[{name}] Writer thread started.")
        print(f"[{name}] Writer thread started.", flush=True)
        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                item: QueueItem = self.queue.get(timeout=0.5)
            except Empty:
                continue

            # petición de parada para este hilo
            if item is SENTINEL:
                self.queue.task_done()
                print(f"[{name}] Writer thread stopping on sentinel.", flush=True)
                break


            # Validate if the item has the expected attributes
            if not hasattr(item, "task") or not hasattr(item, "line"):
                print(
                    f"[{name}] Invalid item in queue: {type(item)!r} {item!r}",
                    file=sys.stderr,
                    flush=True,
                )
                # skip processing, the finally will do task_done()
                continue

            try:
                records: list[InfluxRecord] = item.task.processor(item.line)
                for rec in records:
                    try:
                        # TODO: Debug Speed test
                        # print(
                        #   f"[Influx] Writing record - Queue: {self.queue.qsize()} - Threads: {len(self._writer_threads)}",
                        #   flush=True
                        # )

                        debug_msg(f"[Influx] Writing record: {rec}")
                        self._cli_influx.write_point(rec)

                    except Exception as e:  # pylint: disable=broad-exception-caught
                        print(f"[Influx] Error writing record: {e}", file=sys.stderr, flush=True)

            # Used broad Exception to avoid that an error in a line
            # stops the file following. This will log the error, the thread
            # will end and in the next watch_logs iteration it will be restarted.
            except Exception as e:  # pylint: disable=broad-exception-caught
                task_desc = getattr(getattr(item, "task", None), "description", "UNKNOWN_TASK")
                line_text = getattr(item, "line", repr(item))

                print(
                    f"[{task_desc}] Error processing line: {e}",
                    file=sys.stderr,
                    flush=True
                )
                print(line_text, file=sys.stderr, flush=True)

            finally:
                self.queue.task_done()


    def _get_started_dict_for_task(self, description: str) -> dict[str, threading.Thread]:
        """Get or create the started dict for a given task description."""
        with self._lock:
            return self._started.setdefault(description, {})


    def _del_started_for_path(self, desc: str, path: str) -> None:
        """Delete the started entry for a given path."""
        with self._lock:
            # Another thread may have already removed it
            try:
                del self._started[desc][path]
            except KeyError:
                pass


    def _watch_logs(self, task: LogTask) -> None:
        """Watch log files matching the pattern of a task and start following new ones."""
        pattern = task.pattern
        desc = task.description
        last_is_enabled = None

        while not self.stop_event.is_set():
            if last_is_enabled != task.enabled():
                last_is_enabled = task.enabled()
                if last_is_enabled:
                    print(
                        f"[{desc}] Log task is ENABLED in configuration, watching logs.",
                        flush=True
                    )
                else:
                    print(
                        f"[{desc}] Log task is DISABLED in configuration, not watching logs.",
                        flush=True
                    )

            if last_is_enabled is False:
                time.sleep(SCAN_INTERVAL)
                continue

            # Refresh started dict
            started = self._get_started_dict_for_task(desc)

            # Clean up finished threads
            for path, th in list(started.items()):
                if not th.is_alive():
                    print(f"[{desc}] Stopped following: {path} (thread ended)", flush=True)
                    self._del_started_for_path(desc, path)

            debug_msg(f"[{desc}] Scanning for log files matching: {pattern}")
            debug_msg(f"[{desc}] Already following: {len(started)} files")

            for path in sorted(glob.glob(pattern)):
                if not os.path.isfile(path):
                    debug_msg(f"[{desc}] Ignoring non-regular file: {path}")
                    continue

                if path in started:
                    if started[path].is_alive():
                        debug_msg(f"[{desc}] Already following: {path}")
                        continue

                    print(f"[{desc}] Restarting following: {path}", flush=True)
                    self._del_started_for_path(desc, path)

                else:
                    print(f"[{desc}] Detected new log file: {path}", flush=True)

                t = threading.Thread(
                    target=self._follow_file,
                    args=(path, task),
                    daemon=False,
                    name=f"follow-{desc}-{os.path.basename(path)}",
                )
                t.start()
                with self._lock:
                    self._started[desc][path] = t

            time.sleep(SCAN_INTERVAL)

        self._stop_all_started(desc)


    def _stop_all_started(self, description: str) -> None:
        """Kill all watch_logs threads for a given task description."""
        started = self._get_started_dict_for_task(description)
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
