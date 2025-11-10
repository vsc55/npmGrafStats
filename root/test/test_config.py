import re
from config import cfg, TypeRegex

def test_regex_ipv4():
    text = "client 192.168.1.10 connected"
    m = cfg.regex.search(text, TypeRegex.IPV4)
    assert m
    assert m.group(0) == "192.168.1.10"

def test_regex_domain():
    text = 'GET / HTTP/1.1" 200 - "https://sub.example.com/path"'
    m = cfg.regex.search(text, TypeRegex.DOMAIN)
    assert m
    assert m.group(0) == "sub.example.com"
