""" Tests for logger module. """
import logging

from logger import LogLevel, LogManager


def test_console_and_file_logging_created(tmp_path):
    """ Test that both console and file handlers are created and work. """
    log_file = tmp_path / "app.log"

    mng = LogManager(
        name="test_app",
        initial_level=LogLevel.DEBUG,
        initial_console_level=LogLevel.INFO,
        initial_file_level=LogLevel.DEBUG,
        logfile=str(log_file),
    )
    logger = mng.get_logger()

    # Crete console and file handlers
    assert mng.console_handler is not None
    assert mng.file_handler is not None
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)

    # Add log something and it is written to file
    logger.info("hello file")
    logger.error("boom")

    text = log_file.read_text(encoding="utf-8")
    assert "hello file" in text
    assert "boom" in text


def test_console_only_logging(tmp_path):
    """ Test that only console handler is created and works. """
    mng = LogManager(
        name="console_only",
        initial_level=LogLevel.DEBUG,
        initial_console_level=LogLevel.INFO,
        initial_file_level=None,
        logfile=None,
    )
    logger = mng.get_logger()

    # Only console
    assert mng.console_handler is not None
    assert mng.file_handler is None
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    assert not any(isinstance(h, logging.FileHandler) for h in logger.handlers)


def test_file_only_logging(tmp_path):
    """ Test that only file handler is created and works. """
    log_file = tmp_path / "only.log"

    mng = LogManager(
        name="file_only",
        initial_level=LogLevel.DEBUG,
        initial_console_level=None,
        initial_file_level=LogLevel.DEBUG,
        logfile=str(log_file),
    )
    logger = mng.get_logger()

    # Only file
    assert mng.console_handler is None
    assert mng.file_handler is not None
    assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    assert not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )

    logger.debug("msg in file only")
    assert "msg in file only" in log_file.read_text(encoding="utf-8")


def test_change_levels_runtime(tmp_path):
    """ Test changing log levels at runtime. """
    log_file = tmp_path / "runtime.log"

    mng = LogManager(
        name="runtime",
        initial_level=LogLevel.DEBUG,
        initial_console_level=LogLevel.INFO,
        initial_file_level=LogLevel.DEBUG,
        logfile=str(log_file),
    )
    logger = mng.get_logger()

    # Level initiales
    assert mng.console_level == LogLevel.INFO
    assert mng.file_level == LogLevel.DEBUG
    assert mng.level == LogLevel.DEBUG

    # Change levels
    mng.console_level = LogLevel.ERROR
    mng.file_level = LogLevel.ERROR
    mng.level = LogLevel.DEBUG  # logger global

    # Check levels in handlers
    assert mng.console_handler.level == LogLevel.ERROR.value
    assert mng.file_handler.level == LogLevel.ERROR.value
    assert logger.level == LogLevel.DEBUG.value


def test_disable_console_and_file(tmp_path):
    """ Test disabling console and file handlers at runtime. """
    log_file = tmp_path / "disable.log"

    mng = LogManager(
        name="disable",
        initial_level=LogLevel.DEBUG,
        initial_console_level=LogLevel.INFO,
        initial_file_level=LogLevel.DEBUG,
        logfile=str(log_file),
    )
    logger = mng.get_logger()

    # Disable console
    assert mng.console_handler is not None
    mng.console_level = None
    assert mng.console_handler is None
    assert not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )

    # Disable file
    assert mng.file_handler is not None
    mng.file_level = None
    assert mng.file_handler is None
    assert logger.handlers == []


def test_add_second_file_with_different_level(tmp_path):
    """ Test adding a second file handler with a different log level. """
    main_log = tmp_path / "main.log"
    err_log = tmp_path / "errors.log"

    mng = LogManager(
        name="multi_file",
        initial_level=LogLevel.DEBUG,
        initial_console_level=None,
        initial_file_level=LogLevel.DEBUG,
        logfile=str(main_log),
    )
    logger = mng.get_logger()

    # Add second file handler with ERROR+ level
    mng.add_file(str(err_log), level=LogLevel.ERROR)

    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 2

    # Log messages
    logger.debug("debug msg")
    logger.error("error msg")

    main_text = main_log.read_text(encoding="utf-8")
    err_text = err_log.read_text(encoding="utf-8")

    # main.log receives debug and error
    assert "debug msg" in main_text
    assert "error msg" in main_text

    # errors.log should only have the error
    assert "error msg" in err_text
    assert "debug msg" not in err_text


def test_create_manager_and_create_logger(tmp_path):
    """ Test creating a LogManager and creating a logger via class method. """
    log_file = tmp_path / "static.log"

    mng = LogManager.create_manager(
        name="via_manager",
        level=LogLevel.DEBUG,
        console_level=LogLevel.INFO,
        file_level=LogLevel.DEBUG,
        logfile=str(log_file),
    )
    logger1 = mng.get_logger()

    logger2 = LogManager.create_logger(
        name="via_logger",
        level=LogLevel.INFO,
        console_level=None,
        file_level=LogLevel.INFO,
        logfile=str(tmp_path / "other.log"),
    )

    assert isinstance(logger1, logging.Logger)
    assert isinstance(logger2, logging.Logger)
    assert logger1.name == "via_manager"
    assert logger2.name == "via_logger"
