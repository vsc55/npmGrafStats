#!/usr/bin/env python3
"""Log watching module to monitor log files and process new lines."""
from __future__ import annotations

import glob
import os
import threading
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Optional

from connector.influx import InfluxClient, InfluxRecord
from logger import get_logger
from tasks import LogTask, TasksConfig

log = get_logger(__name__)

TAIL_POLL_INTERVAL = 0.2   # seconds between checks for new lines in follow_file
SCAN_INTERVAL = 30.0       # seconds between scans for new log files in watch_logs


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

        log.info("[STOP] Stopping all log threads...")
        self.stop_event.set()

        for t in self.threads:
            log.info("[STOP] Joining thread: %s (alive=%s)", t.name, t.is_alive())
            if t.is_alive():
                t.join()
            log.info("[STOP] Thread finished: %s (alive=%s)", t.name, t.is_alive())

        log.info("[STOP] All threads stopped.")
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
                log.info("[%s] Following: %s", task.description, path)

                # Track inode of the path and the inode of the opened FD
                try:
                    path_ino = os.stat(path).st_ino
                    fd_ino = os.fstat(f.fileno()).st_ino
                except OSError as e:
                    log.error("[%s] Stat error on %s: %s", task.description, path, e)
                    return

                while not self.stop_event.is_set():
                    line = f.readline()
                    if line:
                        self.queue.put(QueueItem(line=line, task=task))
                        continue

                    # No new line: check rotation/truncate
                    try:
                        # Current read position in FD
                        current_pos = f.tell()

                        # Stats of the current path and current FD
                        st_path = os.stat(path)
                        st_fd = os.fstat(f.fileno())

                    except FileNotFoundError:
                        # Path vanished temporarily (during rotation)
                        log.warning(
                            "[%s] File disappeared (rotation in progress?): %s",
                            task.description,
                            path
                        )
                        time.sleep(TAIL_POLL_INTERVAL)
                        continue

                    except OSError as e:
                        log.error("[%s] Stat error on %s: %s", task.description, path, e)
                        time.sleep(TAIL_POLL_INTERVAL)
                        continue


                    # CASE 1: rename rotation (path inode != fd inode) OR path inode changed
                    # Lossless: reopen and read from start of the new file (do NOT seek to end)
                    if st_path.st_ino != st_fd.st_ino or st_path.st_ino != path_ino:
                        log.info(
                            "[%s] Detected rename rotation of %s (old_ino=%s new_ino=%s), reopening from start.",
                            task.description,
                            path,
                            fd_ino,
                            st_path.st_ino,
                        )
                        try:
                            f.close()
                        except Exception: # pylint: disable=broad-exception-caught
                            pass

                        time.sleep(0.2)

                        # Retry reopening the file with a timeout
                        f = None
                        reopen_attempts = 0
                        max_reopen_attempts = 10
                        while not self.stop_event.is_set() and reopen_attempts < max_reopen_attempts:
                            try:
                                f = open(path, "r", encoding="utf-8")
                                # IMPORTANT: read from the beginning to avoid missing lines
                                # written between create and our reopen
                                path_ino = os.stat(path).st_ino
                                fd_ino = os.fstat(f.fileno()).st_ino
                                log.info("[%s] Successfully reopened %s", task.description, path)
                                break  # Success - exit retry loop
                            except Exception as e:  # pylint: disable=broad-exception-caught
                                reopen_attempts += 1
                                log.warning(
                                    "[%s] Error reopening %s (attempt %d/%d): %s",
                                    task.description,
                                    path,
                                    reopen_attempts,
                                    max_reopen_attempts,
                                    e
                                )
                                if f is not None:
                                    try:
                                        f.close()
                                    except Exception: # pylint: disable=broad-exception-caught
                                        pass
                                    f = None
                                if reopen_attempts < max_reopen_attempts:
                                    time.sleep(1.0)

                        if f is None:
                            log.error(
                                "[%s] Failed to reopen %s after %d attempts, stopping file watcher",
                                task.description,
                                path,
                                max_reopen_attempts
                            )
                            return

                        time.sleep(TAIL_POLL_INTERVAL)
                        continue

                    # CASE 2: copytruncate (same inode, but file size smaller than our position)
                    # Lossless: seek to beginning (NOT to end)
                    if st_path.st_size < current_pos:
                        log.info(
                            "[%s] Detected truncation of %s (size=%d < pos=%d), seeking to start.",
                            task.description,
                            path,
                            st_path.st_size,
                            current_pos,
                        )
                        f.seek(0)

                    time.sleep(TAIL_POLL_INTERVAL)


                    # if not line:
                    #     # detected truncate or rotation
                    #     try:
                    #         current_pos = f.tell()
                    #         f.seek(0, os.SEEK_END)
                    #         end_pos = f.tell()
                    #     except OSError as e:
                    #         log.error("[%s] Stat error on %s: %s", task.description, path, e)
                    #         continue

                    #     if end_pos < current_pos:
                    #         log.info(
                    #             "[%s] Detected truncate/rotation of %s, seeking to end.",
                    #             task.description,
                    #             path
                    #         )
                    #         f.seek(0, os.SEEK_END)

                    #     time.sleep(TAIL_POLL_INTERVAL)
                    #     continue

                    # self.queue.put(QueueItem(line=line, task=task))

        except FileNotFoundError:
            log.error("[%s] File disappeared: %s", task.description, path)

        except Exception as e:  # pylint: disable=broad-exception-caught
            log.error("[%s] Error following %s: %s", task.description, path, e)

    def _autoscaler_loop(self) -> None:
        """Autoscaler loop to adjust the number of writer threads based on queue size."""

        while not self.stop_event.is_set():
            q = self.queue.qsize()
            
            with self._lock:
                n = len(self._writer_threads)

            # scale up
            if q > HIGH_Q and n < MAX_WRITERS:
                log.warning(
                    "[Autoscaler] Scaling up writers: Queue=%d, Writers=%d -> %d", q, n, n+1
                )
                self._start_writer()

            # scale down
            elif q < LOW_Q and n > MIN_WRITERS:
                log.warning(
                    "[Autoscaler] Scaling down writers: Queue=%d, Writers=%d -> %d", q, n, n-1
                )

                # send a sentinel -> one writer will stop itself
                self.queue.put(SENTINEL)
                # optional: clean up dead threads
                with self._lock:
                    self._writer_threads = [t for t in self._writer_threads if t.is_alive()]

            time.sleep(1)

    def _start_writer(self):
        name = f"writer-thread-{self._writer_id}"
        self._writer_id += 1
        t = threading.Thread(target=self._writer_loop, name=name, daemon=True)
        t.start()
        with self._lock:
            self._writer_threads.append(t)


    def _writer_loop(self) -> None:
        """Single writer thread that consumes records from the queue and writes to InfluxDB."""
        name = threading.current_thread().name
        log.info("[%s] Writer thread started.", name)
        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                item: QueueItem = self.queue.get(timeout=0.5)
            except Empty:
                continue

            # petición de parada para este hilo
            if item is SENTINEL:
                self.queue.task_done()
                log.info("[%s] Writer thread stopping on sentinel.", name)
                break


            # Validate if the item has the expected attributes
            # If not, log an error and continue to the next item, calling task_done()
            if not isinstance(item, QueueItem):
                log.error("[%s] Invalid item type in queue: %s", name, type(item).__name__)
                self.queue.task_done()
                continue

            if item.task is None:
                log.error("[%s] Queue item missing task", name)
                self.queue.task_done()
                continue

            if not isinstance(item.line, str):
                log.error(
                    "[%s] Queue item line must be string, got: %s",
                    name,
                    type(item.line).__name__
                )
                self.queue.task_done()
                continue

            if len(item.line.strip()) == 0:
                log.debug("[%s] Skipping empty line", name)
                self.queue.task_done()
                continue

            if not hasattr(item.task, "processor") or not callable(item.task.processor):
                log.error("[%s] Task missing processor", name)
                self.queue.task_done()
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

                        log.debug("[Influx] Writing record: %s", rec)
                        self._cli_influx.write_point(rec)

                    except Exception as e:  # pylint: disable=broad-exception-caught
                        log.error("[Influx] Error writing record: %s", e)

            except (ValueError, KeyError, AttributeError) as e:
                # Error in data processing - log and continue
                task_desc = getattr(getattr(item, "task", None), "description", "UNKNOWN_TASK")
                line_text = getattr(item, "line", repr(item))

                log.error("[%s] Data processing error: %s", task_desc, e)
                log.error("Line content: %s", line_text)

            except (MemoryError, SystemExit, KeyboardInterrupt):
                # Error Critical errors - propagate to stop the application
                raise

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Used broad Exception to avoid that an error in a line
                # stops the file following. This will log the error, the thread
                # will end and in the next watch_logs iteration it will be restarted.
                task_desc = getattr(getattr(item, "task", None), "description", "UNKNOWN_TASK")
                log.critical("[%s] Unexpected error: %s", task_desc, e, exc_info=True)

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
                    log.info("[%s] Log task is ENABLED in configuration, watching logs.", desc)
                else:
                    log.info("[%s] Log task is DISABLED in configuration, not watching logs.", desc)

            if last_is_enabled is False:
                time.sleep(SCAN_INTERVAL)
                continue

            # Refresh started dict
            started = self._get_started_dict_for_task(desc)

            # Clean up finished threads
            for path, th in list(started.items()):
                if not th.is_alive():
                    log.info("[%s] Stopped following: %s (thread ended)", desc, path)
                    self._del_started_for_path(desc, path)

            log.debug("[%s] Scanning for log files matching: %s", desc, pattern)
            log.debug("[%s] Already following: %d files", desc, len(started))

            for path in sorted(glob.glob(pattern)):
                if not os.path.isfile(path):
                    log.debug("[%s] Ignoring non-regular file: %s", desc, path)
                    continue

                if path in started:
                    if started[path].is_alive():
                        # log.debug("[%s] Already following: %s", desc, path)
                        continue

                    log.info("[%s] Restarting following: %s", desc, path)
                    self._del_started_for_path(desc, path)

                else:
                    log.info("[%s] Detected new log file: %s", desc, path)

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
            log.info("[STOP][%s] Joining follow thread for: %s (alive=%s)", description, path, th.is_alive())

            if th.is_alive():
                th.join(timeout=5.0)

            log.info("[STOP][%s] Follow thread finished for: %s (alive=%s)", description, path, th.is_alive())
            

        # Clear started dict for this task
        with self._lock:
            self._started[description] = {}
