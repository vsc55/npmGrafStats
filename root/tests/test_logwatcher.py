#!/usr/bin/env python3
"""Tests for logwatcher module."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from logwatcher import LogTask, LogWatcherManager, QueueItem


class FakeInfluxClient:
    """Fake Influx client to test writing records."""
    def __init__(self):
        self.records = []

    def write_point(self, rec):
        """Simulate writing a point to InfluxDB by storing it in a list."""
        self.records.append(rec)

    def write_points(self, recs):
        """Simulate a batched write by storing all records in order."""
        self.records.extend(recs)


def test_writer_loop_writes_records_to_influx():
    """Test that the writer loop correctly writes records to InfluxDB."""
    cli = FakeInfluxClient()
    mgr = LogWatcherManager(tasks=[], cli_influx=cli)

    class FakeTask:
        """ Task Facke to simulate log processing. """
        description = "fake-task"

        def processor(self, line: str):
            """ the return value of processor is what is sent to write_point, so"""
            return [line]

    # Put a "record" in the queue
    item = QueueItem(task=FakeTask(), line="record-1")
    mgr.queue.put(item)

    # Set stop_event so it exits when the queue is empty
    mgr.stop_event.set()

    t = threading.Thread(target=mgr._writer_loop, name="writer-test")
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

    from config import cfg
    cli = FakeInfluxClient()
    task = LogTask(
        pattern=str(log_file),
        description="test-log",
        processor=processor,
        enabled=lambda: True,
        config=cfg,
    )
    mgr = LogWatcherManager(tasks=[task], cli_influx=cli)


    # Launch writer loop
    writer_thread = threading.Thread(
        target=mgr._writer_loop,
        name="writer-thread-test",
        daemon=True,
    )
    writer_thread.start()


    # Launch the follower in a thread
    follower_thread  = threading.Thread(
        target=mgr._follow_file,
        args=(str(log_file), task),
        name="follower-thread-test",
        daemon=True,
    )
    follower_thread .start()


    # Give a small margin for it to seek to the end
    time.sleep(0.1)

    # Write a new line to the log
    with log_file.open("a", encoding="utf-8") as f:
        f.write("hello world\n")
        f.flush()
        os.fsync(f.fileno())

    # Wait for the follower to put something in the queue
    start = time.time()
    timeout = 2.0
    while time.time() - start < timeout and not processed_records:
        time.sleep(0.05)

    mgr.stop_event.set()
    writer_thread.join(timeout=1.0)
    follower_thread.join(timeout=1.0)

    # Check
    assert processed_records == ["rec:hello world"]
    assert cli.records == ["rec:hello world"]


def test_started_paths_snapshot_return_immutable_copy():
    """Test that started_paths_snapshot returns an independent copy of started paths."""
    from config import cfg
    cli = FakeInfluxClient()
    task = LogTask(
        pattern="/tmp/*.log",
        description="desc",
        processor=lambda _: [],
        enabled=lambda: True,
        config=cfg,
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


@pytest.mark.skipif(os.name == "nt", reason="Rename rotation test relies on POSIX inode semantics")
def test_follow_file_detects_rename_rotation(tmp_path: Path):
    """Test that the follower detects rename log rotation."""
    log_file = tmp_path / "test.log"
    log_file.write_text("", encoding="utf-8")

    processed_records = []

    def processor(line: str):
        rec = f"rec:{line.strip()}"
        processed_records.append(rec)
        return [rec]

    from config import cfg
    cli = FakeInfluxClient()
    task = LogTask(
        pattern=str(log_file),
        description="test-log",
        processor=processor,
        enabled=lambda: True,
        config=cfg,
    )
    mgr = LogWatcherManager(tasks=[task], cli_influx=cli)

    writer_thread = threading.Thread(
        target=mgr._writer_loop,
        name="writer-thread-test",
        daemon=True
    )
    writer_thread.start()

    follower_thread = threading.Thread(
        target=mgr._follow_file,
        args=(str(log_file), task),
        name="follower-thread-test",
        daemon=True,
    )
    follower_thread.start()

    time.sleep(0.1)

    # --- ROTATION (rename) ---
    rotated = tmp_path / "test.log.1"
    os.rename(log_file, rotated)
    # Create the new file with the original name
    log_file.write_text("", encoding="utf-8")

    # Write to the NEW log file
    with log_file.open("a", encoding="utf-8") as f:
        f.write("line-after-rename\n")
        f.flush()
        os.fsync(f.fileno())

    start = time.time()
    timeout = 2.0
    while time.time() - start < timeout and "rec:line-after-rename" not in processed_records:
        time.sleep(0.05)

    mgr.stop_event.set()
    writer_thread.join(timeout=1.0)
    follower_thread.join(timeout=1.0)

    assert "rec:line-after-rename" in processed_records
    assert "rec:line-after-rename" in cli.records


@pytest.mark.skipif(os.name == "nt", reason="Truncate semantics differ on Windows")
def test_follow_file_detects_copytruncate(tmp_path: Path):
    """Test that the follower detects copytruncate log rotation."""
    log_file = tmp_path / "test.log"
    log_file.write_text("", encoding="utf-8")

    processed_records = []

    def processor(line: str):
        rec = f"rec:{line.strip()}"
        processed_records.append(rec)
        return [rec]

    from config import cfg
    cli = FakeInfluxClient()
    task = LogTask(
        pattern=str(log_file),
        description="test-log",
        processor=processor,
        enabled=lambda: True,
        config=cfg,
    )
    mgr = LogWatcherManager(tasks=[task], cli_influx=cli)

    writer_thread = threading.Thread(
        target=mgr._writer_loop,
        name="writer-thread-test",
        daemon=True
    )
    writer_thread.start()

    follower_thread = threading.Thread(
        target=mgr._follow_file,
        args=(str(log_file), task),
        name="follower-thread-test",
        daemon=True,
    )
    follower_thread.start()

    time.sleep(0.1)

    # First line
    with log_file.open("a", encoding="utf-8") as f:
        f.write("before-truncate\n")
        f.flush()
        os.fsync(f.fileno())

    start = time.time()
    while time.time() - start < 2.0 and "rec:before-truncate" not in processed_records:
        time.sleep(0.05)

    # --- copytruncate simulation ---
    with log_file.open("r+", encoding="utf-8") as f:
        f.truncate(0)
        f.flush()
        os.fsync(f.fileno())

    with log_file.open("a", encoding="utf-8") as f:
        f.write("after-truncate\n")
        f.flush()
        os.fsync(f.fileno())

    start = time.time()
    while time.time() - start < 2.0 and "rec:after-truncate" not in processed_records:
        time.sleep(0.05)

    mgr.stop_event.set()
    writer_thread.join(timeout=1.0)
    follower_thread.join(timeout=1.0)

    assert "rec:before-truncate" in processed_records
    assert "rec:after-truncate" in processed_records
