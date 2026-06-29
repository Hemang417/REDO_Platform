"""
Playwright-based session manager for MAHARERA's authenticated API.

MAHARERA's detail data is behind a CAPTCHA. The architecture:
1. setup_session() opens a visible Chrome window for the operator to solve the CAPTCHA once.
2. The CAPTCHA grants a JSESSIONID and triggers the SPA to call authenticatePublic,
   which issues a short-lived JWT (valid ~100 minutes per observation).
3. The JWT is captured and saved to config/maharera_token.json.
4. All subsequent detail API calls use that JWT with the standard HttpClient (requests).
5. When the JWT expires, the operator re-runs setup_session().

This module is called ONCE per scraper run. It does not handle per-project fetches.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, BrowserContext, Page

logger = logging.getLogger(__name__)

_CAPTCHA_URL = "https://maharerait.maharashtra.gov.in/public/project/view/1"
_AUTH_ENDPOINT = "/api/maha-rera-login-service/login/authenticatePublic"
_STATE_FILE = "config/maharera_browser_state.json"
_TOKEN_FILE = "config/maharera_token.json"

# Timeout for the operator to solve the CAPTCHA (90 seconds)
_CAPTCHA_TIMEOUT_MS = 90_000


class SessionSetupError(Exception):
    """Raised when the browser session cannot be established."""


def setup_session() -> str:
    """Open a visible Chrome window, wait for the operator to solve the CAPTCHA,
    capture the JWT, and save it to config/maharera_token.json.

    Returns:
        The JWT access token string.

    Raises:
        SessionSetupError: If CAPTCHA is not solved within the timeout or
                           the JWT cannot be captured.
    """
    logger.info("Opening browser for CAPTCHA setup. Operator must solve within 90 seconds.")
    captured_jwt: dict = {}

    def on_response(response) -> None:
        if _AUTH_ENDPOINT in response.url and response.status == 200:
            try:
                data = response.json()
                token = data.get("responseObject", {}).get("accessToken")
                if token:
                    captured_jwt["token"] = token
                    captured_jwt["full_response"] = data
                    logger.info("JWT captured from authenticatePublic response")
            except Exception as exc:
                logger.debug("Could not parse auth response: %s", exc)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.on("response", on_response)

        page.goto(_CAPTCHA_URL, timeout=60_000)
        logger.info("Browser open. Waiting for CAPTCHA to be solved...")

        try:
            # Wait for Submit button to disappear (= CAPTCHA solved)
            page.wait_for_selector(
                "button:has-text('Submit')",
                state="hidden",
                timeout=_CAPTCHA_TIMEOUT_MS,
            )
            logger.info("CAPTCHA solved. Waiting for page load...")
            page.wait_for_timeout(5_000)
        except Exception:
            logger.warning("CAPTCHA solve timeout. Proceeding with whatever was captured.")

        # Save browser state (cookies + localStorage) for potential reuse
        context.storage_state(path=_STATE_FILE)
        logger.debug("Browser state saved to %s", _STATE_FILE)

        browser.close()

    if "token" not in captured_jwt:
        raise SessionSetupError(
            "JWT was not captured. The CAPTCHA may not have been solved, "
            "or the authenticatePublic call did not complete."
        )

    _save_token(captured_jwt["full_response"])
    return captured_jwt["token"]


def load_token() -> Optional[str]:
    """Load a previously saved JWT from disk.

    Returns:
        The JWT access token string, or None if the file does not exist.
    """
    token_path = Path(_TOKEN_FILE)
    if not token_path.exists():
        return None
    try:
        with token_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("responseObject", {}).get("accessToken")
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.warning("Could not load token from %s: %s", _TOKEN_FILE, exc)
        return None


def _save_token(auth_response: dict) -> None:
    """Persist the full authenticatePublic response to disk."""
    token_path = Path(_TOKEN_FILE)
    with token_path.open("w", encoding="utf-8") as fh:
        json.dump(auth_response, fh, indent=2, default=str)
    logger.info("JWT saved to %s", _TOKEN_FILE)
