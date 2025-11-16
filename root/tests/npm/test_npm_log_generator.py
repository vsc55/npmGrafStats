#!/usr/bin/env python3
"""Tests para npm.simulator.log_generator.NginxLogGenerator."""
import time
from pathlib import Path
import pytest

from npm.simulator.log_generator import NginxLogGenerator


def test_gen_line_format_basic():
    """ Test basic the format of a generated log line. """
    # pylint: disable=protected-access

    gen = NginxLogGenerator(output="dummy.log")

    # force deterministic choices
    gen.USER_AGENTS = ["UA"]
    gen.REFERRERS = ["-"]

    # force status 200
    def fake_choose_status():
        return 200, gen.STATUS_DISTRIBUTION[200]

    gen._choose_status = fake_choose_status
    gen._choose_method = lambda: "GET"
    gen._choose_host = lambda: "www.example.com"
    gen._choose_path_for_host = lambda host: "/index.html"
    gen._get_client_ip = lambda: "192.0.2.10"

    line = gen._gen_line()

    # basic format checks
    assert line.startswith("[")
    assert " GET " in line
    assert " https " in line or " http " in line
    assert 'www.example.com "/index.html"' in line
    assert "[Client 192.0.2.10]" in line
    assert '[Gzip -]' in line
    assert '"UA"' in line
    # Normal Status header: ] - 200 200 -
    assert "] - 200 200 -" in line
    assert "[Length " in line


def test_gen_line_499_format(tmp_path: Path):
    """ Test the format of a generated log line with status 499. """
    # pylint: disable=protected-access

    gen = NginxLogGenerator(output=str(tmp_path / "test_499.log"))

    gen.USER_AGENTS = ["UA"]
    gen.REFERRERS = ["https://ref.example/"]

    def fake_choose_status():
        return 499, gen.STATUS_DISTRIBUTION[499]

    gen._choose_status = fake_choose_status
    gen._choose_method = lambda: "GET"
    gen._choose_host = lambda: "www.example.com"
    gen._choose_path_for_host = lambda host: "/js/test.js"
    gen._get_client_ip = lambda: "192.0.2.180"
    gen._choose_referrer = lambda host: "https://ref.example/"

    line = gen._gen_line()

    # cabecera especial: - - 499 -
    assert "] - - 499 -" in line
    # length 0 for config
    assert "[Length 0]" in line
    # upstream according to your current implementation: "srv." + host
    assert "[Sent-to srv.example.com]" in line
    # rest of fields present
    assert ' GET ' in line
    assert ' www.example.com "/js/test.js"' in line
    assert "[Client 192.0.2.180]" in line
    assert '"UA"' in line
    assert '"https://ref.example/"' in line


def test_write_line_creates_file(tmp_path: Path):
    """ Test that writing lines creates the output file correctly. """
    # pylint: disable=protected-access

    logfile = tmp_path / "out.log"
    gen = NginxLogGenerator(output=str(logfile))
    gen.debug = False

    gen._write_line("test-line-1\n")
    gen._write_line("test-line-2\n")

    assert logfile.exists()
    content = logfile.read_text(encoding="utf-8").splitlines()
    assert content == ["test-line-1", "test-line-2"]


def test_start_stop_generates_lines(tmp_path: Path):
    """ Test that starting and stopping the generator creates log lines. """
    logfile = tmp_path / "bg.log"
    gen = NginxLogGenerator(output=str(logfile))

    # set speed high for test
    gen.base_interval = 0.01
    gen.min_batch = 1
    gen.max_batch = 2

    gen.start()
    time.sleep(0.05)
    gen.stop()

    assert logfile.exists()
    content = logfile.read_text(encoding="utf-8").splitlines()
    # at least one line generated
    assert len(content) >= 1
