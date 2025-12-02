import logging
import sys

# ANSI escape codes for readable log colors
_COLOR_MAP = {
    logging.DEBUG: "\033[37m",   # white
    logging.INFO: "\033[36m",    # cyan
    logging.WARNING: "\033[33m", # yellow
    logging.ERROR: "\033[31m",   # red
    logging.CRITICAL: "\033[41m" # red background
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    """Inject ANSI colors into log records for better readability."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        color = _COLOR_MAP.get(record.levelno, "")
        if color:
            return f"{color}{message}{_RESET}"
        return message


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Configure and return a logger with consistent formatting and colors.
    This helper avoids duplicate handlers if called multiple times.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    fmt = "[%(asctime)s] [%(name)s] %(levelname)s: %(message)s"
    datefmt = "%H:%M:%S"
    handler.setFormatter(_ColorFormatter(fmt=fmt, datefmt=datefmt))

    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
