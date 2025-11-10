import os
from config import GlobalConfig, LogMode
from npm.logtasks import get_log_tasks

def test_get_log_tasks_modes(monkeypatch):
    # Forzamos modos
    monkeypatch.setenv("REDIRECTION_LOGS", "TRUE")

    cfg = GlobalConfig.build()  # instancia nueva local
    # parcheamos cfg global dentro de npm.logtasks
    import npm.logtasks as nl
    nl.cfg = cfg  # type: ignore

    tasks = get_log_tasks()
    descriptions = {t.description for t in tasks}

    assert "proxy" in descriptions
    assert "redirection" in descriptions
