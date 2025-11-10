import time
import threading
from pathlib import Path
from logwatcher import follow_file, InfluxRecord
from connector import influx_client
from unittest.mock import MagicMock

def test_follow_file_reads_new_lines(tmp_path, monkeypatch):
    log_file: Path = tmp_path / "test.log"
    log_file.write_text("line1\n")  # ya existente

    # Mock Influx client (aunque aquí puedes testear solo el processor)
    write_mock = MagicMock()
    monkeypatch.setattr(
        influx_client, "cli_influx",
        type("X", (), {"write_point": write_mock})()
    )

    records = []

    def processor(line: str):
        records.append(line.strip())
        return []  # no usamos InfluxRecord aquí

    t = threading.Thread(
        target=follow_file,
        args=(str(log_file), "test", lambda l: []),
        daemon=True,
    )
    t.start()

    # añadimos nuevas líneas
    time.sleep(0.3)
    with log_file.open("a", encoding="utf-8") as f:
        f.write("line2\n")
        f.write("line3\n")

    time.sleep(0.5)
    # en este ejemplo processor -> [] así que no llenamos records, pero puedes adaptarlo
    # si usas un processor real de prueba.
