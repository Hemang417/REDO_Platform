"""
Configures the root logger for the entire application.

Call setup_logging() once at startup (in the entry point script).
All other modules use logging.getLogger(__name__) — no logger is passed around.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from src.config.loader import LoggingConfig

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(config: LoggingConfig) -> None:
    """Configure root logger with console and rotating file handlers.

    Args:
        config: The logging section of AppConfig.
    """
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # handlers filter individually

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Rotating file handler at DEBUG — captures everything for post-mortem analysis
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / config.log_file,
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console handler at configured level (INFO by default)
    if config.console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, config.log_level, logging.INFO))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Silence noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised | file=%s/%s | console_level=%s",
        config.log_dir,
        config.log_file,
        config.log_level,
    )
