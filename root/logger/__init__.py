""" Module for setting up and retrieving loggers. """
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from doctest import debug
from enum import Enum
from pathlib import Path
from typing import Optional


class LogLevel(Enum):
    """ Enumeration of logging levels. """
    CRITICAL = logging.CRITICAL
    ERROR    = logging.ERROR
    WARNING  = logging.WARNING
    INFO     = logging.INFO
    DEBUG    = logging.DEBUG


class ColorFormatter(logging.Formatter):
    """ Custom formatter to add colors to console log output based on log level. """
    COLORS = {
        logging.DEBUG:    "\033[36m",  # cyan
        logging.INFO:     "\033[32m",  # green
        logging.WARNING:  "\033[33m",  # yellow
        logging.ERROR:    "\033[31m",  # red
        logging.CRITICAL: "\033[41m",  # red background
    }

    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


@dataclass
class LogManager:
    """
    Class to manage logging configuration.
    Provides methods to set up console and file logging with specified formats and levels.

    Example usage Console and File Logging:
        from logger import LogManager, LogLevel

        log_manager = LogManager(
            name="my_app",
            initial_level=LogLevel.DEBUG,
            initial_console_level=LogLevel.INFO,
            initial_file_level=LogLevel.DEBUG,
            logfile="logs/main.log"
        )

        log = log_manager.get_logger()

        log.debug("This is a debug message.")
        log.info("This is an info message.")
        log.warning("This is a warning message.")
        log.error("This is an error message.")
        log.critical("This is a critical message.")
        log.log(LogLevel.DEBUG.value, "This is a log message with custom level.")

        log_manager.console_level = LogLevel.WARNING
        log_manager.file_level = LogLevel.ERROR
        log_manager.level = LogLevel.DEBUG

        log.debug("This debug message will now appear in the file but not on the console.")
        log.info("This info message will now appear in the file but not on the console.")
        log.error("This error message will appear in both the console and the file.")
    
    Example usage Console Only Logging:
        from logger import LogManager, LogLevel
        log_manager = LogManager(
            name="my_console_only_app",
            initial_level=LogLevel.DEBUG,
            initial_console_level=LogLevel.INFO
        )
        log = log_manager.get_logger()
        log.info("This is an info message logged to console only.")
    
    Example usage File Only Logging:
        from logger import LogManager, LogLevel
        log_manager = LogManager(
            name="my_file_only_app",
            initial_level=LogLevel.DEBUG,
            initial_file_level=LogLevel.DEBUG,
            initial_console_level=None,
            logfile="logs/main.log"
        )
        log = log_manager.get_logger()
        log.debug("This is a debug message logged to file only.")
    
    Example usage Multi-File Logging:
        from logger import LogManager, LogLevel
        log_manager = LogManager(
            name="my_multi_file_app",
            initial_level=LogLevel.DEBUG,
            initial_console_level=LogLevel.INFO,
            initial_file_level=LogLevel.DEBUG,
            logfile="logs/main.log"
        )

        log = log_manager.get_logger()
        log_manager.add_file("logs/errors.log", level=LogLevel.ERROR)

        log.debug("Debug → main.log")
        log.error("Error → main.log + errors.log")
    
    Example usage create_logger Static Method:
        from logger import LogManager, LogLevel
        log = LogManager.create_logger(
            name="static_logger_app",
            level=LogLevel.DEBUG,
            console_level=LogLevel.INFO,
            file_level=LogLevel.DEBUG,
            logfile="static_app.log"
        )
        log.info("This is an info message logged using the static method.")
    """

    debug: bool = False

    name: str = "root"
    initial_level: LogLevel = LogLevel.INFO          # Global logger level
    initial_console_level: LogLevel | None = LogLevel.INFO  # Level for console output
    initial_file_level: LogLevel | None = LogLevel.DEBUG    # Level for file output
    logfile: Optional[str] = None

    format_console: str = "%(levelname)s [%(name)s - %(funcName)s:%(lineno)d]: %(message)s"
    format_file: str = "%(asctime)s [%(levelname)s - %(funcName)s:%(lineno)d] %(name)s: %(message)s"
    date_format_file: str = "%Y-%m-%d %H:%M:%S"

    logger: logging.Logger = field(init=False, repr=False)
    _console_level: LogLevel | None = field(init=False, repr=False)
    _file_level: LogLevel | None = field(init=False, repr=False)
    console_handler: Optional[logging.Handler] = field(init=False, repr=False, default=None)
    file_handler: Optional[logging.Handler] = field(init=False, repr=False, default=None)


    # -- Post-initialization --
    def __post_init__(self) -> None:
        self.debug_msg("Initializing LogManager...")

        self.logger = logging.getLogger(self.name)

        self.logger.setLevel(self.initial_level.value)
        self.logger.propagate = False

        self._console_level = self.initial_console_level
        self._file_level = self.initial_file_level

        if not self.logger.handlers and self.initial_console_level is not None:
            self._add_console_handler()
            self.debug_msg("Added console handler.")

        if self.logfile and self.initial_file_level is not None:
            self._add_file_handler(self.logfile)
            self.debug_msg(f"Adding file handler for logfile: {self.logfile}")

        self.debug_msg("LogManager initialized.")


    # --- Public properties ---
    @property
    def level(self) -> LogLevel:
        """ Get the logging level. """
        return LogLevel(self.logger.level)

    @level.setter
    def level(self, level: LogLevel) -> None:
        """ Set the logging level. """
        self.logger.setLevel(level.value)

    @property
    def console_level(self) -> LogLevel | None:
        """ Get the console logging level. """
        return self._console_level

    @console_level.setter
    def console_level(self, lvl: LogLevel | None) -> None:
        """ Set the console logging level. """
        self._console_level = lvl
        if self.console_handler is not None:
            if lvl is None:
                self.debug_msg("Removing console handler.")
                self.logger.removeHandler(self.console_handler)
                self.console_handler = None
            else:
                self.debug_msg(f"Setting console handler level to {lvl}")
                self.console_handler.setLevel(lvl.value)

    @property
    def file_level(self) -> LogLevel | None:
        """ Get the file logging level. """
        return self._file_level

    @file_level.setter
    def file_level(self, lvl: LogLevel | None) -> None:
        """ Set the file logging level. """
        self._file_level = lvl
        if self.file_handler is not None:
            if lvl is None:
                self.debug_msg("Removing file handler.")
                self.logger.removeHandler(self.file_handler)
                self.file_handler = None
            else:
                self.debug_msg(f"Setting file handler level to {lvl}")
                self.file_handler.setLevel(lvl.value)

    # --- Internal methods ---
    def _add_console_handler(self) -> None:
        """ Internal method to add a console handler to the logger. """
        if self._console_level is None:
            return

        fmt = ColorFormatter(self.format_console)

        h = logging.StreamHandler()
        h.setFormatter(fmt)
        h.setLevel(self._console_level.value)

        self.logger.addHandler(h)
        self.console_handler = h

    def _add_file_handler(self, logfile: str, level: LogLevel | None = None) -> None:
        """ Internal method to add a file handler to the logger. """
        if level is None and self._file_level is None:
            return

        fmt = logging.Formatter(
                self.format_file,
                self.date_format_file,
        )
        lvl = level.value if level else self._file_level.value

        try:
            base = Path(__file__).resolve().parent.parent
            logfile = logfile.replace("{workdir}", str(base))
            Path(logfile).parent.mkdir(parents=True, exist_ok=True)

            h = logging.FileHandler(logfile, encoding="utf-8")
            h.setFormatter(fmt)
            h.setLevel(lvl)

            self.logger.addHandler(h)
            self.file_handler = h

        except (FileNotFoundError, PermissionError, OSError) as e:
            print(
                f"[LogManager ERROR] The log file '{logfile}' could not be created or opened: "
                f"{e.__class__.__name__}: {e}",
                flush=True
            )
            # self.logger.error(
            #     "The log file '%s' could not be created or opened: %s: %s",
            #     logfile,
            #     e.__class__.__name__,
            #     e,
            # )


    # --- Public methods ---
    def add_file(self, logfile: str, level: LogLevel | None = None) -> None:
        """ Add a file handler to the logger. """
        self._add_file_handler(logfile, level)

    def get_logger(self) -> logging.Logger:
        """ Get the configured logger. """
        return self.logger

    def debug_msg(self, msg: str) -> None:
        """ Log a debug message if debug is enabled. """
        if self.debug:
            print(f"[LogManager DEBUG] {msg}")

    # -- Static methods --
    @staticmethod
    def get_level_name(level: LogLevel) -> str:
        """ Get the string name of a logging level. """
        return logging.getLevelName(level.value)

    @staticmethod
    def create_manager(
        name: str,
        level: LogLevel = LogLevel.INFO,
        console_level: LogLevel | None = LogLevel.INFO,
        file_level: LogLevel | None = LogLevel.DEBUG,
        logfile: str | None = None,
    ) -> "LogManager":
        """ Create and return a configured LogManager. """
        return LogManager(
            name=name,
            initial_level=level,
            initial_console_level=console_level,
            initial_file_level=file_level,
            logfile=logfile,
        )

    @staticmethod
    def create_logger(
        name: str,
        level: LogLevel = LogLevel.INFO,
        console_level: LogLevel | None = LogLevel.INFO,
        file_level: LogLevel | None = LogLevel.DEBUG,
        logfile: str | None = None,
    ) -> logging.Logger:
        """ Create and return a configured logger. """
        return LogManager.create_manager(
            name=name,
            level=level,
            console_level=console_level,
            file_level=file_level,
            logfile=logfile,
        ).get_logger()


    @staticmethod
    def parse_level_from_env(raw: str, var_name: str) -> LogLevel:
        """Parse a log level from an env var or raise ValueError if invalid."""
        value = raw.strip().upper()
        allowed = ", ".join(LogLevel.__members__.keys())
        try:
            return LogLevel[value]

        except KeyError as exc:
            raise ValueError(
                f"Invalid log level '{raw}' in environment variable {var_name}. "
                f"Allowed values are: {allowed}"
            ) from exc

    # -- Builder class / static method --
    class Builder:
        """
        Builder class for LogManager.

        Example usage:
            from logger import LogManager
            log_manager = LogManager.Builder()\
                .name("my_app")\
                .level(LogLevel.DEBUG)\
                .console(LogLevel.INFO)\
                .file(LogLevel.DEBUG, "logs/app.log")\
                .create()
            
            log = log_manager.get_logger()
            log.info("Worker started")
        """

        debug: bool = False

        def __init__(self) -> None:
            self._name = "root"
            self._level = LogLevel.INFO
            self._console_level = LogLevel.INFO
            self._file_level = LogLevel.DEBUG
            self._logfile = None

        def from_env(self) -> LogManager.Builder:
            """ Load configuration from environment variables. """
            self.debug_msg("Loading LogManager configuration from environment variables.")

            # if (name := os.getenv("LOG_NAME")):
            #     self._name = name

            if (lvl := os.getenv("LOG_LEVEL")):
                self._level = LogManager.parse_level_from_env(lvl, "LOG_LEVEL")

            if (lvl := os.getenv("LOG_CONSOLE_LEVEL")):
                self._console_level = LogManager.parse_level_from_env(lvl, "LOG_CONSOLE_LEVEL")

            if (lvl := os.getenv("LOG_FILE_LEVEL")):
                self._file_level = LogManager.parse_level_from_env(lvl, "LOG_FILE_LEVEL")

            if (file := os.getenv("LOG_FILE")):
                self._logfile = file

            self.debug_msg(
                "Loaded configuration:\n"
                f" - name={self._name}\n"
                f" - level={self._level}\n"
                f" - console_level={self._console_level}\n"
                f" - file_level={self._file_level}\n"
                f" - logfile={self._logfile}\n"
            )
            return self

        def name(self, value: str):
            """ Set the name of the logger. """
            self._name = value
            return self

        def level(self, value: LogLevel):
            """ Set the global logging level. """
            self._level = value
            return self

        def console(self, value: LogLevel | None):
            """ Set the console logging level. """
            self._console_level = value
            return self

        def file(self, value: LogLevel | None, logfile: str | None):
            """ Set the file logging level and logfile path. """
            self._file_level = value
            self._logfile = logfile
            return self

        def create(self) -> LogManager:
            """ Create and return a configured LogManager. """
            return LogManager(
                name=self._name,
                initial_level=self._level,
                initial_console_level=self._console_level,
                initial_file_level=self._file_level,
                logfile=self._logfile,
            )

        def create_logger(self):
            """ Create and return a configured logger. """
            return self.create().get_logger()

        def debug_msg(self, msg: str) -> None:
            """ Log a debug message if debug is enabled. """
            if self.debug:
                print(f"[LogManager.Builder DEBUG] {msg}")

    @classmethod
    def build(cls) -> LogManager.Builder:
        """ Return a LogManager.Builder instance. """
        return cls.Builder()




# Create a global LogManager instance
class _State:
    """ Internal state holder for the global LogManager. """
    manager: LogManager | None = LogManager.build().from_env().create()

def get_logger(name: str | None = None) -> logging.Logger:
    """
    Returns a logger to use in app modules.
    If name is passed, use that; otherwise, return the configured root logger.
    """
    manager = _State.manager
    if manager is None:
        raise RuntimeError("Logging not configured. Global LogManager is None.")

    # Normalize name by stripping whitespace
    clean_name = None if name is None else name.strip()

    if not clean_name:
        return manager.get_logger()

    full_name = f"{manager.name}.{clean_name}"
    return logging.getLogger(full_name)

def get_manager() -> LogManager:
    """ Returns the global LogManager instance. """
    manager = _State.manager
    if manager is None:
        raise RuntimeError("Logging not configured. Global LogManager is None.")

    return manager
