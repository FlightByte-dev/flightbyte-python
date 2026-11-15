"""The quota state the API sends in ``X-RateLimit-*`` response headers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

__all__ = ["RateLimit", "RateLimitWindow"]

_INTEGER = re.compile(r"[0-9]{1,18}")


@dataclass(frozen=True)
class RateLimitWindow:
    """One quota window, from the ``X-RateLimit-*`` response headers."""

    limit: int
    """Requests the window allows."""
    remaining: int
    """Requests left in the window."""
    reset_at: datetime | None
    """When the window resets, in UTC, or ``None`` when not reported."""


@dataclass(frozen=True)
class RateLimit:
    """The quota state sent with a response.

    A window the key has no limit on is ``None``; keys without limits get no
    headers at all. It is immutable, so the client can hand the same object to
    every caller and none of them can change what the others see.
    """

    minute: RateLimitWindow | None
    """The per-minute window."""
    day: RateLimitWindow | None
    """The per-day window."""
    month: RateLimitWindow | None
    """The per-month window."""


def parse_rate_limit(headers: Mapping[str, str]) -> RateLimit | None:
    """Reads the quota headers, with lower-case names, or returns ``None`` when there are none."""
    minute = _parse_window(headers, "minute")
    day = _parse_window(headers, "day")
    month = _parse_window(headers, "month")
    if minute is None and day is None and month is None:
        return None
    return RateLimit(minute=minute, day=day, month=month)


def _parse_window(headers: Mapping[str, str], name: str) -> RateLimitWindow | None:
    limit = _parse_integer(headers.get(f"x-ratelimit-limit-{name}"))
    remaining = _parse_integer(headers.get(f"x-ratelimit-remaining-{name}"))
    if limit is None or remaining is None:
        return None
    reset = _parse_integer(headers.get(f"x-ratelimit-reset-{name}"))
    reset_at = None
    if reset is not None:
        try:
            reset_at = datetime.fromtimestamp(reset, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            reset_at = None
    return RateLimitWindow(limit=limit, remaining=remaining, reset_at=reset_at)


def _parse_integer(value: str | None) -> int | None:
    if value is None:
        return None
    value = value.strip()
    # [0-9] and not \d, which also matches digits from other scripts; at most
    # 18 of them, so int() stays cheap and the value fits a 64-bit integer.
    return int(value) if _INTEGER.fullmatch(value) else None
