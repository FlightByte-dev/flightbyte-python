"""The FlightByte client."""

from __future__ import annotations

import urllib.parse
from datetime import date, datetime, tzinfo
from typing import Final

from ._countries import Countries
from ._flights import Flights
from ._rate_limit import RateLimit
from ._subscriptions import Subscriptions
from ._transport import Transport, check_header_value, check_timeout
from ._version import __version__

__all__ = ["FlightByte"]


class FlightByte:
    """A client for the FlightByte API. Create one and share it.

    ::

        import os
        from flightbyte import FlightByte

        client = FlightByte(api_key=os.environ["FLIGHTBYTE_API_KEY"])
        flight = client.flights.get("TK", "1848", "2026-09-08")
        print(flight["status"]["label"])

    A client is safe to share across threads. It keeps no connection open, so
    there is nothing to close.

    Keep API keys on a server you control. A key shipped inside a browser or
    mobile app can be extracted by anyone who has the app.

    Args:
        api_key: Your API key, sent as ``x-api-key``.
        base_url: The API root. Defaults to ``FlightByte.DEFAULT_BASE_URL``.
        timeout: Bounds each request, response body included, in seconds.
            ``None`` or ``0`` turns it off. Defaults to 30. Every method takes
            a ``timeout`` of its own too.
        user_agent: Put in front of this package's own user agent, for example
            ``my-app/1.2``.

    Raises:
        TypeError: ``api_key`` is not a string.
        ValueError: ``api_key`` is empty, or another argument is invalid.
    """

    DEFAULT_BASE_URL: Final = "https://api.flightbyte.dev/v1"
    """The production API root."""

    flights: Flights
    """Flight lookups."""
    subscriptions: Subscriptions
    """Watched flights and their webhooks."""
    countries: Countries
    """Countries and flags."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float | None = 30.0,
        user_agent: str | None = None,
    ) -> None:
        if not isinstance(api_key, str):
            raise TypeError("flightbyte: api_key is required and must be a string.")
        key = check_header_value("api_key", api_key.strip())
        if not key:
            raise ValueError("flightbyte: api_key is required.")

        own_agent = f"flightbyte-python/{__version__}"
        prefix = (user_agent or "").strip()
        agent = check_header_value("user_agent", f"{prefix} {own_agent}" if prefix else own_agent)

        self._transport = Transport(
            api_key=key,
            base_url=_check_base_url(self.DEFAULT_BASE_URL if base_url is None else base_url),
            timeout=check_timeout("timeout", timeout),
            user_agent=agent,
        )
        self.flights = Flights(self._transport)
        self.subscriptions = Subscriptions(self._transport)
        self.countries = Countries(self._transport)

    @property
    def base_url(self) -> str:
        """The API root this client talks to."""
        return self._transport.base_url

    @property
    def timeout(self) -> float | None:
        """The timeout of each request, in seconds, or ``None`` when there is none."""
        return self._transport.timeout

    @property
    def last_rate_limit(self) -> RateLimit | None:
        """The quota state from the latest response that reported one.

        ``None`` before any did. It is immutable, so reading it never changes
        what the client or another thread sees.
        """
        return self._transport.last_rate_limit

    def __repr__(self) -> str:
        return f"FlightByte(base_url={self.base_url!r})"

    @staticmethod
    def format_date(value: date | datetime, tz: str | tzinfo | None = None) -> str:
        """Formats ``value`` as the ``YYYY-MM-DD`` the API expects for flight dates.

        Pass the origin airport's time zone, an IANA name such as
        ``Europe/Istanbul`` or a ``tzinfo``, to get the date there. Without
        one, a ``datetime`` keeps its own date; a naive one is read as local
        time when converted. A ``date`` is formatted as it is.

        On Windows, IANA names need the ``tzdata`` package, or pass a ``tzinfo``.
        """
        if isinstance(value, datetime):
            if tz is not None:
                value = value.astimezone(_zone(tz))
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        raise TypeError("flightbyte: format_date takes a date or a datetime.")


def _zone(tz: str | tzinfo) -> tzinfo:
    if isinstance(tz, tzinfo):
        return tz
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(
            f"flightbyte: unknown time zone {tz!r}. On Windows, install the tzdata package."
        ) from error


def _check_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("flightbyte: base_url must be a string.")
    text = value.strip()
    try:
        parts = urllib.parse.urlsplit(text)
        parts.port  # noqa: B018 - raises ValueError for a port that is not a number
    except ValueError as error:
        raise ValueError(f"flightbyte: base_url {value!r} is not a URL.") from error
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError(f"flightbyte: base_url {value!r} must be an http or https URL.")
    if parts.query or parts.fragment or "?" in text or "#" in text:
        raise ValueError(f"flightbyte: base_url {value!r} must not have a query or fragment.")
    return text.rstrip("/")
