"""Flight lookups."""

from __future__ import annotations

from typing import cast

from ._models import FlightSnapshot, FlightTimeline
from ._transport import NOT_GIVEN, NotGiven, Transport, required

__all__ = ["Flights"]


class Flights:
    """Flight lookups. Reach it as ``client.flights``."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def get(
        self,
        carrier: str,
        flight_number: str,
        date: str,
        *,
        origin: str | None = None,
        destination: str | None = None,
        flight_id: str | None = None,
        refresh: bool = False,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> FlightSnapshot:
        """Looks a flight up.

        The API upper-cases the carrier and strips leading zeros from the
        flight number. ``date`` is the local departure date at the origin,
        ``YYYY-MM-DD``; ``FlightByte.format_date`` makes one.

        A flight number can fly several legs on one date. The snapshot lists
        them all in ``alternates``; pass ``origin`` (and optionally
        ``destination``) or a leg's ``flight_id`` to choose one. ``refresh``
        skips the API's cache and asks upstream.

        Raises:
            NotFoundError: The flight did not operate that day.
        """
        result = self._transport.send(
            "GET",
            _flight_path(carrier, flight_number, date),
            query={
                "origin": origin,
                "destination": destination,
                "flightId": flight_id,
                "refresh": "true" if refresh else None,
            },
            timeout=timeout,
        )
        return cast(FlightSnapshot, result)

    def timeline(
        self,
        carrier: str,
        flight_number: str,
        date: str,
        *,
        origin: str | None = None,
        destination: str | None = None,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> FlightTimeline:
        """The flight's change history as recorded by the API, newest first."""
        result = self._transport.send(
            "GET",
            [*_flight_path(carrier, flight_number, date), "timeline"],
            query={"origin": origin, "destination": destination},
            timeout=timeout,
        )
        return cast(FlightTimeline, result)


def _flight_path(carrier: str, flight_number: str, date: str) -> list[str]:
    return [
        "flights",
        required("carrier", carrier),
        required("flight_number", flight_number),
        required("date", date),
    ]
