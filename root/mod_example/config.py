#!/usr/bin/env python3
""" Configuration base for mod_example. """
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from logger import get_logger

if TYPE_CHECKING:
    from config import GlobalConfig

log = get_logger(__name__)

@dataclass
class ModExampleConfig:
    """Configuration specific to mod_example."""
    base: "GlobalConfig"

    log_pattern: str = "/logs/example-*.log"

    enabled: bool = True

    @property
    def is_enabled(self) -> bool:
        """ Return whether the module is enabled. """
        return self.enabled
