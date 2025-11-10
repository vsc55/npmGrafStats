from unittest.mock import MagicMock
from config import cfg, LogMode
from npm.handlers import handle_line
from connector import influx_client

def test_handle_line_proxy_normal(monkeypatch):
    # Mock Influx client
    write_mock = MagicMock()
    monkeypatch.setattr(
        influx_client, "cli_influx",
        type("X", (), {"write_point": write_mock})()
    )

    # simulamos un log típico
    line = '1.2.3.4 - - [10/Nov/2025:12:00:00 +0000] "GET / HTTP/1.1" 200 123 "-" "Mozilla"'

    # aseguramos modo normal
    cfg.internal_logs = LogMode.FALSE
    cfg.monitoring_logs = LogMode.FALSE

    handle_line(line, "proxy")

    write_mock.assert_called_once()
    args, kwargs = write_mock.call_args

    assert kwargs["measurement"] == "ReverseProxyConnections"
    tags = kwargs["tags"]
    fields = kwargs["fields"]

    assert tags["IP"] == "1.2.3.4"
    assert "Domain" in tags  # puede ser vacío pero existe
    assert fields["metric"] == 1
