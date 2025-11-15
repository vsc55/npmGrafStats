#!/usr/bin/env python3
""" Configuration specific to Nginx Proxy Manager. """
from __future__ import annotations

import os
import glob
from pathlib import Path
from dataclasses import dataclass
from typing import TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from config import GlobalConfig

class LogsPaths(str, Enum):
    """ Enumeration for log file types. """
    PATH = 0
    PROXY = 1
    REDIRECTION = 2

@dataclass
class NpmConfig:
    """ Configuration specific to Nginx Proxy Manager. """
    base: "GlobalConfig"

    _path_logs: str = os.getenv("NPM_LOGS_PATH", "/logs")
    _proxy_log_pattern: str = "proxy-host-*_access.log"
    _redir_log_pattern: str = "redirection-host-*_access.log"

    def get_path(self, find: LogsPaths) -> str | None:
        """Return the path to the logs directory."""
        base = Path(__file__).resolve().parent.parent

        match find:
            case LogsPaths.PATH:
                raw = self._path_logs
                path =  raw.replace("{workdir}", str(base))
                return str(Path(path))

            case LogsPaths.PROXY:
                return str(Path(self.get_path(LogsPaths.PATH)) / self._proxy_log_pattern)

            case LogsPaths.REDIRECTION:
                return str(Path(self.get_path(LogsPaths.PATH)) / self._redir_log_pattern)
        return None

    def count_logs(self, type_log: LogsPaths) -> int:
        """Count the number of log files of a given type."""
        dir_path = self.get_path(LogsPaths.PATH)
        log_path = self.get_path(type_log)

        if not os.path.isdir(dir_path):
            return 0

        return len(glob.glob(log_path))
