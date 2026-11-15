"""The errors this package raises."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any

from ._models import AmbiguousLeg

__all__ = [
    "APIConnectionError",
    "APIError",
    "AuthenticationError",
    "BadRequestError",
    "FlightByteError",
    "NotFoundError",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "UnexpectedStatusError",
    "UpstreamError",
    "WebhookSignatureError",
]


class FlightByteError(Exception):
    """Base class of every error this package raises."""


class APIConnectionError(FlightByteError):
    """A request got no HTTP response.

    No network, a DNS failure, a refused connection, a TLS failure, or the
    timeout ran out. The underlying error is in ``__cause__``.
    """

    timed_out: bool
    """Whether the client's own timeout ran out."""

    def __init__(self, message: str, *, timed_out: bool = False) -> None:
        super().__init__(message)
        self.timed_out = timed_out


class APIError(FlightByteError):
    """The API answered with a non-2xx status.

    The attributes mirror the API's error body. Catch the subclass for the
    status you want to handle::

        try:
            client.flights.get("TK", "1", "2026-09-08")
        except flightbyte.NotFoundError:
            print("No such flight that day")
        except flightbyte.RateLimitError as err:
            time.sleep(err.retry_after or 5)
    """

    status: int
    """The HTTP status."""
    messages: list[str]
    """Every message the API sent. Validation errors send one per field."""
    body: dict[str, Any]
    """The decoded error body; empty when it was not a JSON object."""
    raw_body: str
    """The body exactly as received."""
    headers: dict[str, str]
    """The response headers, with lower-case names."""

    def __init__(
        self,
        status: int,
        reason: str,
        raw_body: str,
        headers: Mapping[str, str],
    ) -> None:
        body = _decode_body(raw_body)
        messages = _read_messages(body)
        lower_headers = {name.lower(): value for name, value in headers.items()}
        request_id = _string_field(body, "requestId") or lower_headers.get("x-request-id")
        # HTTP/2 and some servers leave the reason empty; the API's own phrase fills in.
        phrase = reason or _string_field(body, "error") or ""
        label = f"{status} {phrase}".strip()
        message = f"{label}: {'; '.join(messages)}" if messages else label
        if request_id:
            message += f" (request {request_id})"
        super().__init__(message)
        self.status = status
        self.messages = messages
        self.body = body
        self.raw_body = raw_body
        self.headers = lower_headers
        self._reason = reason

    def __reduce__(self) -> tuple[Any, ...]:
        # The constructor takes the response, not the message, so pickling
        # (multiprocessing, task queues) needs to be told how to rebuild it.
        return (type(self), (self.status, self._reason, self.raw_body, self.headers))

    @property
    def code(self) -> str | None:
        """A machine-readable reason, when the API sends one.

        For example ``watched_flight_limit`` or ``account_suspended``.
        """
        return _string_field(self.body, "code")

    @property
    def request_id(self) -> str | None:
        """Identifies the request; quote it when contacting support."""
        return _string_field(self.body, "requestId") or self.headers.get("x-request-id")

    @staticmethod
    def from_response(
        status: int,
        reason: str,
        raw_body: str,
        headers: Mapping[str, str],
    ) -> APIError:
        """Builds the subclass for ``status``."""
        return _error_class_for(status)(status, reason, raw_body, headers)


class BadRequestError(APIError):
    """400: the request was invalid.

    When a flight number flies several legs that day and no ``origin`` chose
    one, ``legs`` lists them.
    """

    @property
    def legs(self) -> list[AmbiguousLeg]:
        """The legs to choose from; pass one's ``origin`` or ``flightId`` and try again."""
        legs = self.body.get("legs")
        if not isinstance(legs, list):
            return []
        result: list[AmbiguousLeg] = []
        for item in legs:
            if not isinstance(item, dict):
                continue
            leg: AmbiguousLeg = {
                "origin": _string_field(item, "origin") or "",
                "destination": _string_field(item, "destination") or "",
            }
            carrier = _string_field(item, "carrier")
            departure = _string_field(item, "scheduledDepartureLocal")
            flight_id = _string_field(item, "flightId")
            if carrier is not None:
                leg["carrier"] = carrier
            if departure is not None:
                leg["scheduledDepartureLocal"] = departure
            if flight_id is not None:
                leg["flightId"] = flight_id
            result.append(leg)
        return result


class AuthenticationError(APIError):
    """401: the API key is missing, invalid, revoked or expired."""


class PaymentRequiredError(APIError):
    """402: no watched flights are left.

    ``code`` says why: ``watched_flight_limit`` (the plan's cap),
    ``overage_cap_reached`` (the account's overage cap) or
    ``credits_exhausted`` (prepaid credits used up).
    """

    @property
    def limit(self) -> int | float | None:
        """Watched flights the usage period allows. Not with ``credits_exhausted``."""
        return _number_field(self.body, "limit")

    @property
    def used(self) -> int | float | None:
        """Watched flights created this usage period. Not with ``credits_exhausted``."""
        return _number_field(self.body, "used")

    @property
    def resets_at(self) -> str | None:
        """When the usage period, and so the count, resets, ISO 8601."""
        return _string_field(self.body, "resetsAt")

    @property
    def cap_cents(self) -> int | float | None:
        """The overage cap in US cents; only with ``overage_cap_reached``."""
        return _number_field(self.body, "capCents")

    @property
    def balance(self) -> int | float | None:
        """Prepaid credits left; only with ``credits_exhausted``."""
        return _number_field(self.body, "balance")

    @property
    def expires_at(self) -> str | None:
        """When the credits expire or expired, ISO 8601; only with ``credits_exhausted``."""
        return _string_field(self.body, "expiresAt")


class PermissionDeniedError(APIError):
    """403: the account is suspended or a token lacks the scope.

    ``code`` is ``account_suspended`` or ``insufficient_scope``.
    """


class NotFoundError(APIError):
    """404: the flight did not operate that day, or no such subscription."""


class RateLimitError(APIError):
    """429: a minute, day or month quota is used up."""

    @property
    def window(self) -> str | None:
        """The window that ran out: ``minute``, ``day`` or ``month``."""
        return _string_field(self.body, "window")

    @property
    def retry_after(self) -> int | float | None:
        """How many seconds to wait before retrying.

        From the body's ``retryAfterSeconds``, else the ``Retry-After`` header.
        """
        from_body = _number_field(self.body, "retryAfterSeconds")
        if from_body is not None:
            return from_body
        match = _LEADING_INTEGER.match(self.headers.get("retry-after", ""))
        return int(match.group(1)) if match else None


class ServerError(APIError):
    """5xx: the API failed. ``request_id`` is what support asks for."""


class UpstreamError(ServerError):
    """502: the upstream flight data provider failed.

    Safe to retry after a short wait. It is also a ``ServerError``.
    """


class UnexpectedStatusError(APIError):
    """Any other non-2xx status, including a redirect this client does not follow.

    A redirect is not followed when it points to another origin, or when the
    request was not a GET or HEAD. Its target is in ``location``.
    """

    @property
    def location(self) -> str | None:
        """Where a 3xx pointed, when it did."""
        return self.headers.get("location")


class WebhookSignatureError(FlightByteError):
    """The webhook signature did not verify."""


_STATUS_CLASSES: dict[int, type[APIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    402: PaymentRequiredError,
    403: PermissionDeniedError,
    404: NotFoundError,
    429: RateLimitError,
    502: UpstreamError,
}

_LEADING_INTEGER = re.compile(r"\s*([+-]?[0-9]{1,15})")


def _error_class_for(status: int) -> type[APIError]:
    error_class = _STATUS_CLASSES.get(status)
    if error_class is not None:
        return error_class
    return ServerError if 500 <= status <= 599 else UnexpectedStatusError


def _decode_body(raw_body: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_body)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _read_messages(body: Mapping[str, Any]) -> list[str]:
    message = body.get("message")
    if isinstance(message, str):
        return [message]
    if isinstance(message, list):
        return [item if isinstance(item, str) else json.dumps(item) for item in message]
    return []


def _string_field(mapping: Mapping[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    return value if isinstance(value, str) else None


def _number_field(mapping: Mapping[str, Any], key: str) -> int | float | None:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None
