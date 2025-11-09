#!/usr/bin/env python3
from __future__ import annotations

from typing import Iterable

from config import cfg
from logwatcher import LogTask, InfluxRecord, LineProcessor
from _mod_example.handlers import handle_line

def make_processor(env: str) -> LineProcessor:
    """ Create a line processor with the given environment. """
    def processor(line: str) -> list[InfluxRecord]:
        return handle_line(line, env)
    return processor

def get_log_tasks() -> Iterable[LogTask]:
    """
    Return log tasks for mod_example.
    The main process will collect them through cfg.all_log_tasks.
    """
    tasks: list[LogTask] = []

    if not cfg.mod_example or not cfg.mod_example.enabled:
        return tasks

    tasks.append(
        LogTask(
            pattern=cfg.mod_example.log_pattern,
            description="mod_example",
            processor=make_processor(env="production")
        )
    )

    return tasks
