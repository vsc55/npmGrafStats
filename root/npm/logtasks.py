#!/usr/bin/env python3
""" Defines the log tasks for NPM based on configuration. """
from __future__ import annotations
from typing import Iterable

from config import LogMode, cfg
from logwatcher import LogTask, LineProcessor
from npm.handlers import handle_line, LogKind
from npm.config import LogsPaths
from connector.influx import InfluxRecord

def make_processor(mode: LogKind) -> LineProcessor:
    """ Creates a line processor for the given log mode. """
    def processor(line: str) -> list[InfluxRecord]:
        return handle_line(line, mode)
    return processor

def get_log_tasks() -> Iterable[LogTask]:
    """
    Returns the log tasks that NPM wants to run,
    based on the global configuration.
    """
    tasks: list[LogTask] = []

    # Reverse Proxy logs
    if cfg.redirection_logs in (LogMode.TRUE, LogMode.FALSE):
        tasks.append(
            LogTask(
                pattern=cfg.npm.get_path(LogsPaths.PROXY),
                description="proxy",
                processor=make_processor("proxy"),
            )
        )

    # Redirection logs
    if cfg.redirection_logs in (LogMode.TRUE, LogMode.ONLY):
        tasks.append(
            LogTask(
                pattern=cfg.npm.get_path(LogsPaths.REDIRECTION),
                description="redirection",
                processor=make_processor("redirection"),
            )
        )

    return tasks
