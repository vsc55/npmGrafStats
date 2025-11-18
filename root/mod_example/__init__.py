#!/usr/bin/env python3
""" Example integration package. """
from __future__ import annotations

from typing import Iterable, Literal
from tasks import LogTask, LineProcessor, ListEnabled, DiscoveryInfo
from connector.influx import InfluxRecord
from config import GlobalConfig
from .config import ModExampleConfig
from .handlers import handle_line


__version__ = "1.0.0"
__description__ = "Example integration package."


def make_processor(env: str, config: GlobalConfig) -> LineProcessor:
    """ Excample line processor with the given environment. """
    def processor(line: str) -> list[InfluxRecord]:
        return handle_line(line, env, config)
    return processor

def make_is_enabled(mode: str, config: GlobalConfig) -> ListEnabled:
    """ Example check if log task is enabled based on the configuration. """
    def enabled() -> bool:
        match mode:
            case "MODE1":
                return config.mod_example.mode1_enabled

            case "MODE2":
                return config.mod_example.mode2_enabled

            case _:
                return False  # Default to False for unknown modes

    return enabled

def get_log_tasks(config: GlobalConfig) -> Iterable[LogTask]:
    """
    Returns the log tasks that NPM wants to run,
    based on the global configuration.
    """
    tasks: list[LogTask] = []

    # Task 1
    tasks.append(
        LogTask(
            pattern="/tmp/mod_example1_*.log",
            description="mod_example1",
            processor=make_processor("production1", config),
            enabled=make_is_enabled("MODE1", config),
            config=config,
        )
    )

    # Task 2
    tasks.append(
        LogTask(
            pattern="/tmp/mod_example2_*.log",
            description="mode_example2",
            processor=make_processor("production2", config),
            enabled=make_is_enabled("MODE2", config),
            config=config,
        )
    )

    return tasks


def load_config_module(var_module: str | None, config: GlobalConfig, force: bool = False) -> None:
    """
    Load the module configuration into the global config.
    Parameters:
        config: The global configuration object.
        force: If True, forces reloading the configuration even if it already exists.

    Note: To load the configuration, you need to add an instance variable in GlobalConfig,
          so you can set it with your configuration and add your configuration in TYPE_CHECKING.

          Example (config/__init__.py):
            ......
            if TYPE_CHECKING:
                from npm.config import NpmConfig
                from mod_example.config import ModExampleConfig  # 👈 New
            ......
            class GlobalConfig:
            ......
                npm: Optional["NpmConfig"] = None
                mod_example: Optional["ModExampleConfig"] = None  # 👈 New
            ......          
    """
    if var_module is None:
        raise ValueError("Discovery config did not provide a module name.")

    if not hasattr(config, var_module):
        raise AttributeError(
            f"Invalid module '{var_module}' in Discovery config (not in GlobalConfig)."
        )

    if  getattr(config, var_module) is not None and not force:
        return

    config.unlock()
    setattr(config, var_module, ModExampleConfig(base=config))
    config.lock()


def discovery_module() -> DiscoveryInfo:
    """ Discovery information about this module. """
    return {
        "status": False,
        "logtasks": False,
        "config": False,
        "config_name": "mod_example",
        "config_class": "ModExampleConfig",
        "func_config": "load_config_module",
        "func_logtasks": "get_log_tasks",
    }
