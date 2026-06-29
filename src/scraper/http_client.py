"""
Thin HTTP client wrapping requests.Session.

Single responsibility: reliable GET requests with retries, backoff, and rate limiting.
No parsing, no business logic.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config.loader import ScraperConfig

logger = logging.getLogger(__name__)

_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


class ScraperHTTPError(Exception):
    """Raised when an HTTP request fails after all retries are exhausted."""


class HttpClient:
    """Rate-limited HTTP client with automatic retry and exponential backoff.

    Usage:
        with HttpClient(config.scraper) as client:
            response = client.get("https://example.com")
    """

    def __init__(self, config: ScraperConfig) -> None:
        self._config = config
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": self._config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9",
            }
        )
        retry_strategy = Retry(
            total=self._config.max_retries,
            backoff_factor=self._config.retry_backoff_factor,
            status_forcelist=_RETRY_STATUS_CODES,
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        """Perform a GET request with rate limiting applied before each call.

        Args:
            url: The full URL to fetch.
            params: Optional query parameters.

        Returns:
            The HTTP response object.

        Raises:
            ScraperHTTPError: If the response status indicates a permanent failure.
        """
        time.sleep(self._config.rate_limit_delay)

        logger.debug("GET %s | params=%s", url, params)
        try:
            response = self._session.get(
                url,
                params=params,
                timeout=self._config.request_timeout,
            )
        except requests.RequestException as exc:
            raise ScraperHTTPError(f"Request failed for {url}: {exc}") from exc

        if not response.ok:
            logger.warning(
                "Non-200 response | url=%s | status=%d | body_preview=%.200s",
                url,
                response.status_code,
                response.text,
            )
            raise ScraperHTTPError(
                f"HTTP {response.status_code} for {url}"
            )

        logger.debug("Response OK | url=%s | status=%d | size=%d bytes", url, response.status_code, len(response.content))
        return response

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
