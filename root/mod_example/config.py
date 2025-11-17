#!/usr/bin/env python3
""" Configuration base for mod_example. """
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import GlobalConfig

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
