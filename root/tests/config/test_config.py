#!/usr/bin/env python3
""" Unit tests for configuration regex patterns."""
import importlib
import pytest
import config
from utils import Regex, TypeRegex

@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Clean environment before each test."""
    for var in [
        "PROXY_LOGS",
        "REDIRECT_LOGS", 
        "INTERNAL_LOGS",
        "MONITORING_LOGS",
        "PUBLIC_LOGS",
        "INFLUX_URL",
        "INFLUX_BUCKET",
        "INFLUX_ORG",
        "INFLUX_TOKEN",
        "ABUSEIP_KEY",
    ]:
        monkeypatch.delenv(var, raising=False)
    yield

def test_regex_ipv4():
    """ Test regex for IPv4 addresses. """
    text = "client 192.168.1.10 connected"
    m = Regex.search_type(text, TypeRegex.IPV4)
    assert m
    assert m.group(0) == "192.168.1.10"

def test_regex_ipv6():
    """ Test regex for IPv6 addresses. """
    text = "client 2001:0db8:85a3:0000:0000:8a2e:0370:7334 connected"
    m = Regex.search_type(text, TypeRegex.IPV6)
    assert m
    assert m.group(0) == "2001:0db8:85a3:0000:0000:8a2e:0370:7334"

def test_regex_domain():
    """ Test regex for domain names. """
    text = 'GET / HTTP/1.1" 200 - "https://sub.example.com/path"'
    m = Regex.search_type(text, TypeRegex.DOMAIN)
    assert m
    assert m.group(0) == "sub.example.com"

def test_env_log_modes(monkeypatch):
    """Ensure log modes are correctly loaded from environment variables."""
    monkeypatch.setenv("REDIRECT_LOGS", "true")
    monkeypatch.setenv("INTERNAL_LOGS", "true")
    monkeypatch.setenv("MONITORING_LOGS", "false")
    monkeypatch.setenv("PUBLIC_LOGS", "true")

    importlib.reload(config)
    cfg = config.cfg

    assert cfg.redirect_logs is True
    assert cfg.internal_logs is True
    assert cfg.monitoring_logs is False
    assert cfg.public_logs is True

def test_env_influx_and_abuseip(monkeypatch):
    """Ensure InfluxDB and AbuseIP key load correctly from environment."""
    monkeypatch.setenv("INFLUX_URL", "http://influx.local:8086")
    monkeypatch.setenv("INFLUX_BUCKET", "test_bucket")
    monkeypatch.setenv("INFLUX_ORG", "acme")
    monkeypatch.setenv("INFLUX_TOKEN", "secret123")
    monkeypatch.setenv("ABUSEIP_KEY", "XYZKEY")

    importlib.reload(config)
    cfg = config.cfg

    assert cfg.influxdb["url"] == "http://influx.local:8086"
    assert cfg.influxdb["bucket"] == "test_bucket"
    assert cfg.influxdb["org"] == "acme"
    assert cfg.influxdb["token"] == "secret123"
    assert cfg.api_abuseip_key == "XYZKEY"
