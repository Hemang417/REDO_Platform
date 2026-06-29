"""Tests for the config loader."""

import os
import tempfile

import pytest
import yaml

from src.config.loader import (
    AppConfig,
    ConfigValidationError,
    load_config,
)


def _write_config(data: dict, tmp_dir: str) -> str:
    path = os.path.join(tmp_dir, "settings.yaml")
    with open(path, "w") as fh:
        yaml.dump(data, fh)
    return path


VALID_CONFIG = {
    "scraper": {
        "base_url": "https://example.com/list",
        "detail_base_url": "https://example.com/detail",
        "start_page": 1,
        "end_page": None,
        "request_timeout": 30,
        "rate_limit_delay": 1.5,
        "max_retries": 3,
        "retry_backoff_factor": 2.0,
        "user_agent": "test/1.0",
        "checkpoint_interval": 100,
    },
    "storage": {
        "raw_output_dir": "output/raw",
        "json_enabled": True,
        "csv_enabled": True,
    },
    "logging": {
        "log_dir": "logs",
        "log_file": "scraper.log",
        "log_level": "INFO",
        "console_enabled": True,
        "max_bytes": 10485760,
        "backup_count": 5,
    },
    "cleaner": {
        "raw_input_dir": "output/raw",
        "clean_output_dir": "output/clean",
        "json_enabled": True,
        "csv_enabled": True,
        "date_formats": ["%Y-%m-%d", "%d/%m/%Y"],
    },
}


def test_load_valid_config():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_config(VALID_CONFIG, tmp)
        config = load_config(path)

    assert isinstance(config, AppConfig)
    assert config.scraper.base_url == "https://example.com/list"
    assert config.scraper.start_page == 1
    assert config.scraper.end_page is None
    assert config.scraper.rate_limit_delay == 1.5
    assert config.storage.json_enabled is True
    assert config.logging.log_level == "INFO"


def test_config_is_frozen():
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_config(VALID_CONFIG, tmp)
        config = load_config(path)

    with pytest.raises((TypeError, AttributeError)):
        config.scraper.start_page = 99  # frozen dataclass should reject this


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_config("does_not_exist.yaml")


def test_missing_scraper_section():
    bad_config = {k: v for k, v in VALID_CONFIG.items() if k != "scraper"}
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_config(bad_config, tmp)
        with pytest.raises(ConfigValidationError, match="scraper"):
            load_config(path)


def test_missing_key_inside_section():
    bad_config = {**VALID_CONFIG, "scraper": {k: v for k, v in VALID_CONFIG["scraper"].items() if k != "base_url"}}
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_config(bad_config, tmp)
        with pytest.raises(ConfigValidationError):
            load_config(path)


def test_end_page_can_be_integer():
    config_data = {**VALID_CONFIG, "scraper": {**VALID_CONFIG["scraper"], "end_page": 10}}
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_config(config_data, tmp)
        config = load_config(path)
    assert config.scraper.end_page == 10
