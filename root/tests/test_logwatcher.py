#!/usr/bin/env python3
"""Tests for logwatcher module."""
from __future__ import annotations

import os
import time
import threading
from pathlib import Path

import pytest

from logwatcher import LogWatcherManager, LogTask

class FakeInfluxClient:
    """Cliente Influx falso para testear las escrituras."""
    def __init__(self):
        self.records = []

    def write_point(self, rec):
        self.records.append(rec)


def test_writer_loop_writes_records_to_influx():
    """Test that the writer loop correctly writes records to InfluxDB."""
    cli = FakeInfluxClient()
    mgr = LogWatcherManager(tasks=[], cli_influx=cli)

    # Put a "record" in the queue
    mgr.queue.put("record-1")
    # Set stop_event so it exits when the queue is empty
    mgr.stop_event.set()

    t = threading.Thread(target=mgr._writer_loop)
    t.start()
    t.join(timeout=1.0)

    assert cli.records == ["record-1"]


def test_follow_file_processes_new_lines(tmp_path: Path):
    """Test that following a file processes new lines added to it."""

    # Create an empty log file
    log_file = tmp_path / "test.log"
    log_file.write_text("", encoding="utf-8")

    processed_records = []

    def processor(line: str):
        rec = f"rec:{line.strip()}"
        processed_records.append(rec)
        # The actual type of influx record doesn't matter for this test.
        return [rec]

    cli = FakeInfluxClient()
    task = LogTask(
        pattern=str(log_file),
        description="test-log",
        processor=processor,
    )
    mgr = LogWatcherManager(tasks=[task], cli_influx=cli)

    # Launch the follower in a thread
    t = threading.Thread(
        target=mgr._follow_file,
        args=(str(log_file), task),
        daemon=True,
    )
    t.start()

    # Give a small margin for it to seek to the end
    time.sleep(0.1)

    # Write a new line to the log
    with log_file.open("a", encoding="utf-8") as f:
        f.write("hello world\n")
        f.flush()
        os.fsync(f.fileno())

    # Wait for the follower to put something in the queue
    start = time.time()
    while time.time() - start < 2.0 and mgr.queue.empty():
        time.sleep(0.05)

    mgr.stop_event.set()
    t.join(timeout=1.0)

    assert processed_records == ["rec:hello world"]
    # The queue should contain the same "record"
    assert not mgr.queue.empty()
    rec = mgr.queue.get_nowait()
    assert rec == "rec:hello world"


def test_started_paths_snapshot_return_immutable_copy():
    """Test that started_paths_snapshot returns an independent copy of started paths."""
    cli = FakeInfluxClient()
    task = LogTask(
        pattern="/tmp/*.log",
        description="desc",
        processor=lambda _: [],
    )
    mgr = LogWatcherManager(tasks=[task], cli_influx=cli)

    # Simulate already started paths
    with mgr._lock:
        mgr._started["desc"] = {
            "/tmp/a.log": threading.Thread(),
            "/tmp/b.log": threading.Thread(),
        }

    snapshot = mgr.started_paths_snapshot()

    # The snapshot should contain the paths, but be independent of the internal dict
    assert set(snapshot["desc"]) == {"/tmp/a.log", "/tmp/b.log"}

    # If we modify the snapshot, it should not affect the internal one
    snapshot["desc"].append("/tmp/c.log")
    assert "/tmp/c.log" not in mgr._started["desc"]
