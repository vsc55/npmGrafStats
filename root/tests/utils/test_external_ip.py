#!/usr/bin/env python3
"""Tests for ExternalIP cache and TTL logic."""

# pylint: disable=unused-argument

import pytest
import utils.external_ip as ext_mod
from utils.external_ip import ExternalIP

class FakeResponse:
    """Mock response object for urlopen."""
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_external_ip_first_call_hits_network(monkeypatch):
    """Test external IP retrieval on first call hits the network."""
    calls = {"n": 0}

    def fake_urlopen(url, timeout=5):
        calls["n"] += 1
        return FakeResponse(b"8.8.8.8")

    monkeypatch.setattr(ext_mod, "urlopen", fake_urlopen)

    ext = ExternalIP(ttl_seconds=3600)
    ip = ext.get_ip()

    assert ip == "8.8.8.8"
    assert calls["n"] == 1


def test_external_ip_uses_cache_within_ttl(monkeypatch):
    """Test external IP retrieval uses cache within TTL."""
    calls = {"n": 0}

    def fake_urlopen(url, timeout=5):
        calls["n"] += 1
        return FakeResponse(b"1.2.3.4")

    monkeypatch.setattr(ext_mod, "urlopen", fake_urlopen)

    # congelamos el tiempo
    base_time = 1_000_000.0
    monkeypatch.setattr(ext_mod.time, "time", lambda: base_time)

    ext = ExternalIP(ttl_seconds=60)

    ip1 = ext.get_ip()
    # avanzamos 30s (< TTL)
    monkeypatch.setattr(ext_mod.time, "time", lambda: base_time + 30)
    ip2 = ext.get_ip()

    assert ip1 == "1.2.3.4"
    assert ip2 == "1.2.3.4"
    assert calls["n"] == 1  # solo una llamada → la segunda usa caché


def test_external_ip_refresh_after_ttl(monkeypatch):
    """Test external IP retrieval refreshes after TTL expires."""
    calls = {"n": 0}

    def fake_urlopen(url, timeout=5):
        calls["n"] += 1
        # devolvemos algo distinto según llamada
        return FakeResponse(b"10.0.0.1" if calls["n"] == 1 else b"10.0.0.2")

    monkeypatch.setattr(ext_mod, "urlopen", fake_urlopen)

    base_time = 2_000_000.0
    monkeypatch.setattr(ext_mod.time, "time", lambda: base_time)

    ext = ExternalIP(ttl_seconds=60)

    ip1 = ext.get_ip()
    # avanzamos más que el TTL
    monkeypatch.setattr(ext_mod.time, "time", lambda: base_time + 120)
    ip2 = ext.get_ip()

    assert ip1 == "10.0.0.1"
    assert ip2 == "10.0.0.2"
    assert calls["n"] == 2  # dos llamadas → la segunda refresca


def test_external_ip_force_refresh(monkeypatch):
    """Test external IP retrieval with forced refresh."""
    calls = {"n": 0}

    def fake_urlopen(url, timeout=5):
        calls["n"] += 1
        return FakeResponse(b"9.9.9.9")

    monkeypatch.setattr(ext_mod, "urlopen", fake_urlopen)

    base_time = 3_000_000.0
    monkeypatch.setattr(ext_mod.time, "time", lambda: base_time)

    ext = ExternalIP(ttl_seconds=3600)

    ip1 = ext.get_ip()
    ip2 = ext.get_ip(force=True)  # fuerza refresco aunque no haya pasado TTL

    assert ip1 == "9.9.9.9"
    assert ip2 == "9.9.9.9"
    assert calls["n"] == 2  # se ha llamado dos veces gracias a force=True


def test_external_ip_raises_on_error(monkeypatch):
    """Test external IP retrieval raises an error on network failure."""
    def fake_urlopen(url, timeout=5):
        raise TimeoutError("boom")

    monkeypatch.setattr(ext_mod, "urlopen", fake_urlopen)

    ext = ExternalIP()

    with pytest.raises(ValueError, match="Error detecting external IP"):
        ext.get_ip(force=True)
