
#!/usr/bin/env python3
""" Types for NPM integration. """
from typing import Literal
from enum import Enum

LogKind = Literal["proxy", "redirection"]

class TypeSendRecord(str, Enum):
    """ Enumeration for send record types. """
    LOCAL = "local"
    PUBLIC = "public"
