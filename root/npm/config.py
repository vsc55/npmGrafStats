#!/usr/bin/env python3
""" Configuration specific to Nginx Proxy Manager. """
from __future__ import annotations
import os
import glob
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

    _path_logs: str = "/logs"
    _proxy_log_pattern: str = "{self._path_logs}/proxy-host-*_access.log"
    _redir_log_pattern: str = "{self._path_logs}/redirection-host-*_access.log"

    def get_path(self, find: LogsPaths) -> str | None:
        """Return the path to the logs directory."""
        match find:
            case LogsPaths.PATH:
                return self._path_logs
            case LogsPaths.PROXY:
                return self._proxy_log_pattern
            case LogsPaths.REDIRECTION:
                return self._redir_log_pattern
        return None

    @property
    def count_proxy_logs(self) -> int:
        """Return number of proxy log files present."""
        return len(glob.glob(self._proxy_log_pattern)) if os.path.isdir(self._path_logs) else 0

    @property
    def count_redir_logs(self) -> int:
        """Return number of redirection log files present."""
        return len(glob.glob(self._redir_log_pattern)) if os.path.isdir(self._path_logs) else 0
