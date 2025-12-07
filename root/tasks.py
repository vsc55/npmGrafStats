#!/usr/bin/env python3
""" Manages log tasks from various providers. """
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TypedDict

from config import GlobalConfig
from connector.influx import InfluxRecord
from logger import get_logger

log = get_logger(__name__)

LogTasksProviderRef = tuple[str, str, str]  # (package, module, function_name)

LineProcessor = Callable[[str], list[InfluxRecord]]
ListEnabled = Callable[[], bool]

@dataclass(frozen=True)
class LogTask:
    """Defines a log watching task."""
    pattern: str               # p.ej. "/logs/proxy-host-*_access.log"
    description: str           # only for logging purposes
    processor: LineProcessor   # function handle_line(line)
    enabled: ListEnabled       # function to check if the task is enabled
    config: GlobalConfig       # global configuration

class DiscoveryInfo(TypedDict):
    """ Information returned by discovery_module function. """
    status: bool        # Whether the module is enabled by default (default True)
    logtasks: bool      # Whether the module provides log tasks (default True)
    config: bool        # Whether the module provides configuration (default True)
    config_name: str    # Name of the configuration section
    config_class: str   # Name of the configuration class
    func_config: str    # Function to load configuration (default "load_config_module")
    func_logtasks: str  # Function to get log tasks (default "get_log_tasks")

@dataclass(frozen=False)
class TasksConfig:
    """ Configuration for log tasks providers. """

    _log_providers: list[LogTasksProviderRef] = field(default_factory=list)
    tasks: list[LogTask] = field(init=False, default_factory=list)
    config: GlobalConfig | None = None
    auto_discover: bool = True

    def __post_init__(self) -> None:
        """ Post-initialization tasks. """
        if self.auto_discover:
            self.discover_providers()


    def _gen_package_module_full(self, package: str, module: str) -> str:
        """ Generate full module name from package and module. """
        return f"{package}.{module}" if module else package


    def discover_providers(self) -> None:
        """ Discover and register log tasks providers from the 'logtasks_providers' package. """
        if self.config is None:
            raise ValueError("GlobalConfig is not set in TasksConfig.")

        # TODO: Consider merging existing tasks instead of clearing them.
        self.clean()

        base_dir = Path(__file__).parent
        for _, package, ispkg in pkgutil.iter_modules([str(base_dir)]):
            if not ispkg:
                continue

            # We can use only the package name to search for the function, or we can define
            # a specific module with the variable "module_name" in which to search for that
            # function.
            # Load: <package> or <package>.<module>
            module_name = ""
            full_name = self._gen_package_module_full(package, module_name)

            try:
                module = importlib.import_module(full_name)

            except ImportError:
                continue  # If a module from the package isspecified and it does not
                          # exist, it is ignored.

            func_discovery = getattr(module, "discovery_module", None)
            if callable(func_discovery) is False:
                continue  # No discovery_modules function, skip.

            info_mod = func_discovery()
            if not info_mod.get("status", True):
                log.warning(
                    "Skipping module %s in package %s: disabled from discovery.",
                    full_name,
                    package
                )
                continue  # Module disabled from discovery.

            # Actions to be taken by discovery.
            actions = [
                {
                    "state": "config",
                    "func_key": "func_config",
                    "default": "load_config_module",
                    "handler": lambda f, a, *args, **kwargs: f(
                        kwargs["info"].get("config_name", None),
                        self.config,
                        force=True
                    ),
                },
                {
                    "state": "logtasks",
                    "func_key": "func_logtasks",
                    "default": "get_log_tasks",
                    "handler": lambda f, *args, **kwargs: self.tasks.extend(f(config=self.config)),
                },
            ]

            for a in actions:
                if not info_mod.get(a["state"], True):
                    log.warning(
                        "Skipping %s for module %s in package %s",
                        a["state"],
                        full_name,
                        package
                    )
                    continue

                func_name = info_mod.get(a["func_key"], a["default"])
                func = getattr(module, func_name, None)

                if callable(func):
                    a["handler"](
                        func,
                        a,
                        info=info_mod,
                        package=package,
                        module=module_name,
                        func=func_name
                    )
                    self._log_providers.append((package, module_name, func_name))


    def clean(self) -> None:
        """ Clear all registered log tasks. """
        self.tasks.clear()

    @property
    def count(self) -> int:
        """ Get the total number of log tasks. """
        return len(self.tasks)
