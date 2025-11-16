#!/usr/bin/env python3
"""Tests for the FakeInfluxServer."""
import urllib.request
import urllib.error
import pytest

from connector.influx.fake_server import FakeInfluxServer


def test_server_not_started_raises_on_url_and_port():
    """ Test that accessing url and port properties before starting raises RuntimeError. """
    srv = FakeInfluxServer()

    with pytest.raises(RuntimeError):
        _ = srv.url

    with pytest.raises(RuntimeError):
        _ = srv.get_port

    # host is always available
    assert srv.get_host == "127.0.0.1"
    assert srv.is_running is False


def test_server_start_and_ping_and_stop():
    """ Test starting the server, pinging it, and stopping it. """
    srv = FakeInfluxServer()
    try:
        srv.start()

        assert srv.is_running is True
        assert isinstance(srv.get_port, int)
        assert srv.get_port > 0
        assert srv.url.startswith("http://")

        # /ping -> 204
        req = urllib.request.Request(f"{srv.url}/ping", method="GET")
        with urllib.request.urlopen(req) as resp:  # nosec B310 (tests only)
            assert resp.status == 204

        # ruta inexistente -> 404
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f"{srv.url}/nope")  # nosec B310
        assert excinfo.value.code == 404

    finally:
        srv.stop()
        assert srv.is_running is False


def test_write_endpoint_post_returns_204():
    """ Test that POST to /api/v2/write returns 204. """
    srv = FakeInfluxServer()
    try:
        srv.start()

        data = b"measurement,tag=value field=1i"
        req = urllib.request.Request(
            f"{srv.url}/api/v2/write?org=test&bucket=test",
            data=data,
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:  # nosec B310
            assert resp.status == 204

    finally:
        srv.stop()


def test_post_to_invalid_path_returns_404():
    """ Test that POST to an invalid path returns 404. """
    srv = FakeInfluxServer()
    try:
        srv.start()

        data = b"whatever"
        req = urllib.request.Request(
            f"{srv.url}/invalid",
            data=data,
            method="POST",
        )

        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(req)  # nosec B310
        assert excinfo.value.code == 404

    finally:
        srv.stop()


def test_start_is_idempotent():
    """ Test that starting the server multiple times does not change the port or cause errors. """
    srv = FakeInfluxServer()
    try:
        srv.start()
        first_port = srv.get_port
        srv.start()  # no debe romper ni cambiar el puerto
        assert srv.get_port == first_port
    finally:
        srv.stop()


def test_context_manager_starts_and_stops():
    """ Test that using FakeInfluxServer as a context manager starts and stops the server. """
    with FakeInfluxServer() as srv:
        assert srv.is_running is True
        assert srv.get_host == "127.0.0.1"

        # /ping inside the with works
        with urllib.request.urlopen(f"{srv.url}/ping") as resp:  # nosec B310
            assert resp.status == 204

    # outside the with the server is stopped
    assert srv.is_running is False
