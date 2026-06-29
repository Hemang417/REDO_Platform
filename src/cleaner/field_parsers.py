"""
Pure functions for parsing individual raw string fields into typed values.

Single responsibility: type coercion only. No business logic, no I/O.
All functions accept str | None and return the typed value or None on failure.
Parsing failures are logged at DEBUG level — callers decide whether to treat
them as fatal.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Canonical date formats tried in order (configured via settings.yaml,
# but this default covers every format seen in MAHARERA's API so far)
_DEFAULT_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
)

# Characters to strip before normalising names
_EXTRA_WHITESPACE = re.compile(r"\s{2,}")


def parse_date(
    value: Optional[str],
    formats: tuple = _DEFAULT_DATE_FORMATS,
    field_name: str = "",
) -> Optional[date]:
    """Parse a raw date string to a Python date object.

    Tries each format in `formats` until one succeeds.
    Returns None for null, empty, or unparseable input.
    """
    if not value or not value.strip():
        return None

    clean = value.strip()

    # Strip trailing time component if present (e.g. "2018-12-31 00:00:00")
    clean = clean.split("T")[0].split(" ")[0]

    for fmt in formats:
        try:
            return datetime.strptime(clean, fmt).date()
        except ValueError:
            continue

    logger.debug("Could not parse date %r for field %r", value, field_name)
    return None


def parse_float(
    value: Optional[str],
    field_name: str = "",
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> Optional[float]:
    """Parse a raw percentage/numeric string to float.

    Returns None for null, empty, or non-numeric input.
    Clamps to [min_val, max_val] if provided.
    """
    if not value or not value.strip():
        return None
    try:
        result = float(value.strip().rstrip("%"))
        if min_val is not None and result < min_val:
            logger.debug("Float %r below min %s for field %r", value, min_val, field_name)
            return min_val
        if max_val is not None and result > max_val:
            logger.debug("Float %r above max %s for field %r", value, max_val, field_name)
            return max_val
        return result
    except (ValueError, TypeError):
        logger.debug("Could not parse float %r for field %r", value, field_name)
        return None


def parse_int(
    value: Optional[str],
    field_name: str = "",
) -> Optional[int]:
    """Parse a raw numeric string to int.

    Returns None for null or non-integer input.
    """
    if not value or not value.strip():
        return None
    try:
        return int(value.strip())
    except (ValueError, TypeError):
        logger.debug("Could not parse int %r for field %r", value, field_name)
        return None


def parse_bool(
    value: Optional[str],
    field_name: str = "",
) -> Optional[bool]:
    """Parse a MAHARERA flag string ("0" / "1" / "true" / "false") to bool.

    Returns None for null or unrecognised input.
    """
    if value is None:
        return None
    clean = value.strip().lower()
    if clean in ("1", "true", "yes"):
        return True
    if clean in ("0", "false", "no"):
        return False
    logger.debug("Could not parse bool %r for field %r", value, field_name)
    return None


def normalise_name(value: Optional[str]) -> str:
    """Strip, collapse internal whitespace, and upper-case a name string.

    Returns empty string for null/empty input.

    MAHARERA data contains names like "MANOJ  AWASTHI" (double space) and
    leading/trailing spaces — this canonicalises them.
    """
    if not value:
        return ""
    return _EXTRA_WHITESPACE.sub(" ", value.strip()).upper()


def normalise_location(value: Optional[str]) -> Optional[str]:
    """Strip and title-case a location field (district / taluka / village).

    Returns None for null/empty input.
    """
    if not value or not value.strip():
        return None
    return value.strip().title()


def compute_delay_days(
    proposed: Optional[date],
    reference: Optional[date] = None,
) -> Optional[int]:
    """Number of days the project is past its proposed completion date.

    Args:
        proposed: The proposed completion date from the API.
        reference: The date to compare against; defaults to today (UTC).

    Returns:
        Positive int if overdue, negative int if ahead of schedule, None if
        either date is missing.
    """
    if proposed is None:
        return None
    ref = reference or date.today()
    return (ref - proposed).days
