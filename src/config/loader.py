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

_REQUIRED_SECTIONS = ("scraper", "storage", "logging", "cleaner")


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
class CleanerConfig:
    raw_input_dir: str
    clean_output_dir: str
    json_enabled: bool
    csv_enabled: bool
    date_formats: tuple


@dataclass(frozen=True)
class AppConfig:
    scraper: ScraperConfig
    storage: StorageConfig
    logging: LoggingConfig
    cleaner: CleanerConfig


@dataclass(frozen=True)
class ConstructionProgressConfig:
    optimal_min: float
    optimal_max: float
    score_below_optimal: float
    score_in_optimal: float
    score_above_optimal: float
    score_complete: float


@dataclass(frozen=True)
class DelayConfig:
    no_delay_score: float
    moderate_delay_min_days: int
    moderate_delay_max_days: int
    moderate_delay_score: float
    severe_delay_max_days: int
    severe_delay_score: float
    extreme_delay_score: float


@dataclass(frozen=True)
class LocationConfig:
    tier1_districts: tuple
    tier2_districts: tuple
    tier1_score: float
    tier2_score: float
    other_score: float


@dataclass(frozen=True)
class ViabilityConfig:
    active_score: float
    completed_score: float
    lapsed_score: float
    deregistered_score: float
    abeyance_score: float
    unknown_score: float


@dataclass(frozen=True)
class ExtensionConfig:
    scores: tuple          # tuple of (count, score) pairs, sorted by count
    four_plus_score: float


@dataclass(frozen=True)
class ScoringWeights:
    construction_progress: float
    delay_severity: float
    extension_history: float
    project_viability: float
    location: float


@dataclass(frozen=True)
class HardFilterConfig:
    construction_progress_min: float
    construction_progress_max: float
    exclude_lapsed: bool
    exclude_deregistered: bool
    exclude_abeyance: bool
    exclude_if_litigation: bool
    exclude_if_criminal_cases: bool


@dataclass(frozen=True)
class ScoringConfig:
    weights: ScoringWeights
    construction_progress: ConstructionProgressConfig
    delay_severity: DelayConfig
    extension_history: ExtensionConfig
    project_viability: ViabilityConfig
    location: LocationConfig
    hard_filters: HardFilterConfig


@dataclass(frozen=True)
class DevWeights:
    completion_rate: float
    on_time_rate: float
    no_lapse_rate: float
    portfolio_size: float


@dataclass(frozen=True)
class DevThreshold:
    excellent_threshold: float
    poor_threshold: float


@dataclass(frozen=True)
class DevPortfolioThreshold:
    large_threshold: int
    small_threshold: int
    single_score: float


@dataclass(frozen=True)
class DeveloperScoringConfig:
    weights: DevWeights
    completion_rate: DevThreshold
    on_time_rate: DevThreshold
    no_lapse_rate: DevThreshold
    portfolio_size: DevPortfolioThreshold


def load_developer_scoring_config(
    path: str = "config/scoring_rules.yaml",
) -> DeveloperScoringConfig:
    """Load the developer_scoring section from scoring_rules.yaml."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Scoring config not found: {config_path.resolve()}")

    with config_path.open("r", encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh) or {}

    try:
        d = raw["developer_scoring"]
        w = d["weights"]
        return DeveloperScoringConfig(
            weights=DevWeights(
                completion_rate=float(w["completion_rate"]),
                on_time_rate=float(w["on_time_rate"]),
                no_lapse_rate=float(w["no_lapse_rate"]),
                portfolio_size=float(w["portfolio_size"]),
            ),
            completion_rate=DevThreshold(
                excellent_threshold=float(d["completion_rate"]["excellent_threshold"]),
                poor_threshold=float(d["completion_rate"]["poor_threshold"]),
            ),
            on_time_rate=DevThreshold(
                excellent_threshold=float(d["on_time_rate"]["excellent_threshold"]),
                poor_threshold=float(d["on_time_rate"]["poor_threshold"]),
            ),
            no_lapse_rate=DevThreshold(
                excellent_threshold=float(d["no_lapse_rate"]["excellent_threshold"]),
                poor_threshold=float(d["no_lapse_rate"]["poor_threshold"]),
            ),
            portfolio_size=DevPortfolioThreshold(
                large_threshold=int(d["portfolio_size"]["large_threshold"]),
                small_threshold=int(d["portfolio_size"]["small_threshold"]),
                single_score=float(d["portfolio_size"]["single_score"]),
            ),
        )
    except KeyError as exc:
        raise ConfigValidationError(f"Missing developer_scoring config key: {exc}") from exc


def load_scoring_config(path: str = "config/scoring_rules.yaml") -> ScoringConfig:
    """Read scoring_rules.yaml and return a validated ScoringConfig.

    Raises:
        FileNotFoundError: If the file does not exist.
        ConfigValidationError: If required keys are missing.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Scoring config not found: {config_path.resolve()}")

    with config_path.open("r", encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh) or {}

    try:
        s = raw["scoring"]
        w = s["weights"]
        cp = s["construction_progress"]
        ds = s["delay_severity"]
        eh = s["extension_history"]
        pv = s["project_viability"]
        lc = s["location"]

        weights = ScoringWeights(
            construction_progress=float(w["construction_progress"]),
            delay_severity=float(w["delay_severity"]),
            extension_history=float(w["extension_history"]),
            project_viability=float(w["project_viability"]),
            location=float(w["location"]),
        )
        cp_cfg = ConstructionProgressConfig(
            optimal_min=float(cp["optimal_min"]),
            optimal_max=float(cp["optimal_max"]),
            score_below_optimal=float(cp["score_below_optimal"]),
            score_in_optimal=float(cp["score_in_optimal"]),
            score_above_optimal=float(cp["score_above_optimal"]),
            score_complete=float(cp["score_complete"]),
        )
        delay_cfg = DelayConfig(
            no_delay_score=float(ds["no_delay_score"]),
            moderate_delay_min_days=int(ds["moderate_delay_min_days"]),
            moderate_delay_max_days=int(ds["moderate_delay_max_days"]),
            moderate_delay_score=float(ds["moderate_delay_score"]),
            severe_delay_max_days=int(ds["severe_delay_max_days"]),
            severe_delay_score=float(ds["severe_delay_score"]),
            extreme_delay_score=float(ds["extreme_delay_score"]),
        )
        # Extension scores dict {0: 0.30, 1: 0.80, ...} → sorted tuple of (int, float) pairs
        ext_scores_raw = {int(k): float(v) for k, v in eh["scores"].items()}
        ext_cfg = ExtensionConfig(
            scores=tuple(sorted(ext_scores_raw.items())),
            four_plus_score=float(eh["four_plus_score"]),
        )
        viability_cfg = ViabilityConfig(
            active_score=float(pv["active_score"]),
            completed_score=float(pv["completed_score"]),
            lapsed_score=float(pv["lapsed_score"]),
            deregistered_score=float(pv["deregistered_score"]),
            abeyance_score=float(pv["abeyance_score"]),
            unknown_score=float(pv["unknown_score"]),
        )
        location_cfg = LocationConfig(
            tier1_districts=tuple(lc["tier1_districts"]),
            tier2_districts=tuple(lc["tier2_districts"]),
            tier1_score=float(lc["tier1_score"]),
            tier2_score=float(lc["tier2_score"]),
            other_score=float(lc["other_score"]),
        )
        hf = s.get("hard_filters", {})
        hard_filter_cfg = HardFilterConfig(
            construction_progress_min=float(hf.get("construction_progress_min", 0.0)),
            construction_progress_max=float(hf.get("construction_progress_max", 100.0)),
            exclude_lapsed=bool(hf.get("exclude_lapsed", True)),
            exclude_deregistered=bool(hf.get("exclude_deregistered", True)),
            exclude_abeyance=bool(hf.get("exclude_abeyance", True)),
            exclude_if_litigation=bool(hf.get("exclude_if_litigation", False)),
            exclude_if_criminal_cases=bool(hf.get("exclude_if_criminal_cases", False)),
        )
    except KeyError as exc:
        raise ConfigValidationError(f"Missing scoring config key: {exc}") from exc

    return ScoringConfig(
        weights=weights,
        construction_progress=cp_cfg,
        delay_severity=delay_cfg,
        extension_history=ext_cfg,
        project_viability=viability_cfg,
        location=location_cfg,
        hard_filters=hard_filter_cfg,
    )


@dataclass(frozen=True)
class AiConfig:
    model: str
    max_tokens: int
    request_timeout: int
    max_retries: int
    retry_backoff_factor: float
    min_score_for_memo: float
    max_memos_per_run: int
    cache_dir: str
    output_dir: str
    system_prompt: str
    groq_model: str = "llama-3.3-70b-versatile"
    groq_max_tokens: int = 2048


def load_ai_config(path: str = "config/ai_config.yaml") -> AiConfig:
    """Load AI analyst config from ai_config.yaml."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"AI config not found: {config_path.resolve()}")

    with config_path.open("r", encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh) or {}

    try:
        a = raw["ai"]
        return AiConfig(
            model=str(a["model"]),
            max_tokens=int(a["max_tokens"]),
            request_timeout=int(a["request_timeout"]),
            max_retries=int(a["max_retries"]),
            retry_backoff_factor=float(a["retry_backoff_factor"]),
            min_score_for_memo=float(a["min_score_for_memo"]),
            max_memos_per_run=int(a["max_memos_per_run"]),
            cache_dir=str(a["cache_dir"]),
            output_dir=str(a["output_dir"]),
            system_prompt=str(a["system_prompt"]).strip(),
            groq_model=str(a.get("groq_model", "llama-3.3-70b-versatile")),
            groq_max_tokens=int(a.get("groq_max_tokens", 1024)),
        )
    except KeyError as exc:
        raise ConfigValidationError(f"Missing ai config key: {exc}") from exc


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
        cleaner_cfg = CleanerConfig(
            raw_input_dir=raw["cleaner"]["raw_input_dir"],
            clean_output_dir=raw["cleaner"]["clean_output_dir"],
            json_enabled=bool(raw["cleaner"]["json_enabled"]),
            csv_enabled=bool(raw["cleaner"]["csv_enabled"]),
            date_formats=tuple(raw["cleaner"]["date_formats"]),
        )
    except KeyError as exc:
        raise ConfigValidationError(f"Missing required config key: {exc}") from exc

    logger.debug("Config loaded from: %s", config_path.resolve())
    return AppConfig(scraper=scraper_cfg, storage=storage_cfg, logging=logging_cfg, cleaner=cleaner_cfg)
