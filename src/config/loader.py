"""
Loads config/settings.yaml into typed, frozen dataclasses.

All application code receives config via constructor injection — no global state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_REQUIRED_SECTIONS = ("scraper", "storage", "logging")


class ConfigValidationError(Exception):
    """Raised when settings.yaml is missing required keys."""


@dataclass(frozen=True)
class ScraperConfig:
    base_url: str
    detail_base_url: str
    start_page: int
    end_page: Optional[int]
    request_timeout: int
    rate_limit_delay: float
    max_retries: int
    retry_backoff_factor: float
    user_agent: str
    checkpoint_interval: int


@dataclass(frozen=True)
class StorageConfig:
    raw_output_dir: str
    json_enabled: bool
    csv_enabled: bool


@dataclass(frozen=True)
class LoggingConfig:
    log_dir: str
    log_file: str
    log_level: str
    console_enabled: bool
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class AppConfig:
    scraper: ScraperConfig
    storage: StorageConfig
    logging: LoggingConfig


def load_config(path: str = "config/settings.yaml") -> AppConfig:
    """Read settings.yaml and return a validated, frozen AppConfig.

    Args:
        path: Path to the YAML config file, relative to CWD or absolute.

    Returns:
        Fully populated AppConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ConfigValidationError: If required sections or keys are missing.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path.resolve()}")

    with config_path.open("r", encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh) or {}

    for section in _REQUIRED_SECTIONS:
        if section not in raw:
            raise ConfigValidationError(f"Missing required config section: '{section}'")

    try:
        scraper_cfg = ScraperConfig(
            base_url=raw["scraper"]["base_url"],
            detail_base_url=raw["scraper"]["detail_base_url"],
            start_page=int(raw["scraper"]["start_page"]),
            end_page=raw["scraper"].get("end_page"),  # None means "all pages"
            request_timeout=int(raw["scraper"]["request_timeout"]),
            rate_limit_delay=float(raw["scraper"]["rate_limit_delay"]),
            max_retries=int(raw["scraper"]["max_retries"]),
            retry_backoff_factor=float(raw["scraper"]["retry_backoff_factor"]),
            user_agent=raw["scraper"]["user_agent"],
            checkpoint_interval=int(raw["scraper"]["checkpoint_interval"]),
        )

        storage_cfg = StorageConfig(
            raw_output_dir=raw["storage"]["raw_output_dir"],
            json_enabled=bool(raw["storage"]["json_enabled"]),
            csv_enabled=bool(raw["storage"]["csv_enabled"]),
        )

        logging_cfg = LoggingConfig(
            log_dir=raw["logging"]["log_dir"],
            log_file=raw["logging"]["log_file"],
            log_level=raw["logging"]["log_level"].upper(),
            console_enabled=bool(raw["logging"]["console_enabled"]),
            max_bytes=int(raw["logging"]["max_bytes"]),
            backup_count=int(raw["logging"]["backup_count"]),
        )
    except KeyError as exc:
        raise ConfigValidationError(f"Missing required config key: {exc}") from exc

    logger.debug("Config loaded from: %s", config_path.resolve())
    return AppConfig(scraper=scraper_cfg, storage=storage_cfg, logging=logging_cfg)
