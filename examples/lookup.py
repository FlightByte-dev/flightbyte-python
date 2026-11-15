"""Looks a flight up and prints its status.

    pip install -e .
    FLIGHTBYTE_API_KEY=frk_live_... python examples/lookup.py TK 1848 2026-09-08

FLIGHTBYTE_BASE_URL points it at another API root, for example a local one.
"""

import os
import sys

from flightbyte import BadRequestError, FlightByte, FlightByteError, NotFoundError, best_gate_time


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: python examples/lookup.py <carrier> <flight number> <YYYY-MM-DD>",
            file=sys.stderr,
        )
        return 1
    carrier, flight_number, date = argv

    api_key = os.environ.get("FLIGHTBYTE_API_KEY")
    if not api_key:
        print("Set FLIGHTBYTE_API_KEY to your API key.", file=sys.stderr)
        return 1

    client = FlightByte(api_key=api_key, base_url=os.environ.get("FLIGHTBYTE_BASE_URL"))

    try:
        flight = client.flights.get(carrier, flight_number, date)
    except NotFoundError:
        print("No such flight on that date.", file=sys.stderr)
        return 1
    except BadRequestError as error:
        if not error.legs:
            print(error, file=sys.stderr)
            return 1
        print("This flight number flies several legs that day:", file=sys.stderr)
        for leg in error.legs:
            at = leg.get("scheduledDepartureLocal", "?")
            print(f"  {leg['origin']} → {leg['destination']} at {at}", file=sys.stderr)
        return 1
    except FlightByteError as error:
        print(error, file=sys.stderr)
        return 1

    def dash(value: object) -> object:
        return "-" if value is None else value

    departure, arrival = flight["departure"], flight["arrival"]
    print(f"{flight['flightKey']}  {departure['airport']['iata']} → {arrival['airport']['iata']}")
    print(f"Status     {flight['status']['label']} ({flight['status']['phase']})")
    departs = best_gate_time(departure["times"])
    if departs:
        gate = dash(departure.get("gate"))
        print(f"Departure  {departs.get('local')} {dash(departs.get('timezone'))}, gate {gate}")
    arrives = best_gate_time(arrival["times"])
    if arrives:
        baggage = dash(arrival.get("baggage"))
        print(
            f"Arrival    {arrives.get('local')} {dash(arrives.get('timezone'))}, baggage {baggage}"
        )
    if departure.get("delayMinutes"):
        print(f"Delay      {departure['delayMinutes']} min")
    rate_limit = client.last_rate_limit
    if rate_limit and rate_limit.minute:
        minute = rate_limit.minute
        print(f"Quota      {minute.remaining} of {minute.limit} left this minute")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
