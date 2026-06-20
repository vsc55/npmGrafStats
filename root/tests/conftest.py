#!/usr/bin/env python3
""" Shared pytest fixtures. """
import pytest


@pytest.fixture(autouse=True)
def _clear_geoip_reader_cache():
    """
    The GeoIP2 module caches one MaxMind reader per DB path for the whole
    process. Tests monkeypatch ``geoip2.database.Reader`` with different dummies
    while reusing the same fake path, so the cache must be reset around each test
    to avoid serving a reader created by a previous test.
    """
    from api.external import geoip2 as geoip2_module

    geoip2_module.clear_reader_cache()
    yield
    geoip2_module.clear_reader_cache()
