#!/usr/bin/env python3
"""Nginx Proxy Manager integration package."""
from __future__ import annotations

from typing import Iterable, Literal

from config import GlobalConfig
from connector.influx import InfluxRecord
from tasks import DiscoveryInfo, LineProcessor, ListEnabled, LogTask

from .config import LogsPaths, NpmConfig
from .handlers import handle_line
from .types import LogKind

__version__ = "1.0.0"
__description__ = "Nginx Proxy Manager integration"


def make_processor(mode: LogKind, config: GlobalConfig) -> LineProcessor:
    """ Creates a line processor for the given log mode. """
    def processor(line: str) -> list[InfluxRecord]:
        return handle_line(line, mode, config)
    return processor

def make_is_enabled(mode: LogKind, config: GlobalConfig) -> ListEnabled:
    """ Check if proxy log task is enabled based on the configuration. """
    def enabled() -> bool:
        match mode:
            case "proxy":
                return config.proxy_logs
            case "redirection":
                return config.redirect_logs
            case _:
                return False  # Default to False for unknown modes

    return enabled

def get_log_tasks(config: GlobalConfig) -> Iterable[LogTask]:
    """
    Returns the log tasks that NPM wants to run,
    based on the global configuration.
    """
    tasks: list[LogTask] = []

    # Proxy logs
    tasks.append(
        LogTask(
            pattern=config.npm.get_path(LogsPaths.PROXY),
            description="proxy",
            processor=make_processor("proxy", config),
            enabled=make_is_enabled("proxy", config),
            config=config,
        )
    )

    # Redirection logs
    tasks.append(
        LogTask(
            pattern=config.npm.get_path(LogsPaths.REDIRECTION),
            description="redirection",
            processor=make_processor("redirection", config),
            enabled=make_is_enabled("redirection", config),
            config=config,
        )
    )

    return tasks


def load_config_module(var_module: str | None, config: GlobalConfig, force: bool = False) -> None:
    """ Load NPM configuration into the global config. """
    if var_module is None:
        raise ValueError("Discovery config did not provide a module name.")

    if not hasattr(config, var_module):
        raise AttributeError(
            f"Invalid module '{var_module}' in Discovery config (not in GlobalConfig)."
        )

    if  getattr(config, var_module) is not None and not force:
        return

    config.unlock()
    setattr(config, var_module, NpmConfig(base=config))
    config.lock()


def discovery_module() -> DiscoveryInfo:
    """ Discovery information for the NPM logtasks module. """
    return {
        "status": True,
        "logtasks": True,
        "config": True,
        "config_name": "npm",
        "config_class": "NpmConfig",
        "func_config": "load_config_module",
        "func_logtasks": "get_log_tasks",
    }
