#!/usr/bin/env python3
"""Tests for utils: debug_msg, format_time, is_ip_in_range."""

# pylint: disable=use-implicit-booleaness-not-comparison
# pylint: disable=unused-argument

import utils

# ---------- format_time ----------

def test_format_time_valid():
    """Convert correctly a log timestamp to ISO 8601."""
    old = "30/May/2023:14:16:48 +0000"
    new = utils.format_time(old)
    assert new == "2023-05-30T14:16:48+00:00"

# ---------- is_ip_in_range ----------

def test_is_ip_in_range_single_ip():
    """The IP should match only that IP."""
    entries = ["192.168.1.10"]
    assert utils.is_ip_in_range("192.168.1.10", entries)
    assert not utils.is_ip_in_range("192.168.1.11", entries)


def test_is_ip_in_range_cidr():
    """Should work with CIDR ranges."""
    entries = ["10.0.0.0/24"]
    assert utils.is_ip_in_range("10.0.0.5", entries)
    assert not utils.is_ip_in_range("10.0.1.5", entries)


def test_is_ip_in_range_explicit_range():
    """Should work with explicit start-end ranges."""
    entries = ["10.0.0.10-10.0.0.20"]
    assert utils.is_ip_in_range("10.0.0.15", entries)
    assert not utils.is_ip_in_range("10.0.0.9", entries)
    assert not utils.is_ip_in_range("10.0.0.21", entries)


def test_is_ip_in_range_ignores_comments_and_empty():
    """Lines that are empty or have comments at the end are correctly ignored."""
    entries = [
        "",
        "# comment line",
        "192.168.1.0/24   # local network",
        "10.0.0.10-10.0.0.20 # range",
    ]
    assert utils.is_ip_in_range("192.168.1.42", entries)
    assert utils.is_ip_in_range("10.0.0.15", entries)
    assert not utils.is_ip_in_range("8.8.8.8", entries)


def test_is_ip_in_range_invalid_entries():
    """Invalid entries should not raise an exception and should be ignored."""
    # Invalid entries in the list → ignored
    entries = [
        "not-an-ip",
        "300.300.300.300/24",
        "10.0.0.1-what",
    ]
    assert not utils.is_ip_in_range("8.8.8.8", entries)

    # Invalid IP as parameter → False
    assert not utils.is_ip_in_range("not-an-ip", ["192.168.0.0/16"])


def test_is_ip_in_range_mixed_entries():
    """
    Should work with mixed list:
      - Single IP
      - CIDR
      - Range explicit
      - Mixed comments
    """
    entries = [
        "192.168.1.10",                 # Single IP
        "10.0.0.0/24",                  # CIDR
        "172.16.5.10-172.16.5.20",      # Range explicit
        " # pure comment",              # pure comment line
        "8.8.8.0/24   # google-ish",    # CIDR and comment
    ]

    # Matches unique IP
    assert utils.is_ip_in_range("192.168.1.10", entries)

    # Matches CIDR 10.0.0.0/24
    assert utils.is_ip_in_range("10.0.0.1", entries)
    assert utils.is_ip_in_range("10.0.1.200", entries) is False

    # Matches range 172.16.5.10-172.16.5.20
    assert utils.is_ip_in_range("172.16.5.15", entries)
    assert utils.is_ip_in_range("172.16.5.9", entries) is False
    assert utils.is_ip_in_range("172.16.5.21", entries) is False

    # Matches 8.8.8.0/24 (comment at the end of the line)
    assert utils.is_ip_in_range("8.8.8.8", entries)

    # Something totally outside
    assert utils.is_ip_in_range("1.1.1.1", entries) is False
