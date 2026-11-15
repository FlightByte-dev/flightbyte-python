"""Verifying and decoding the webhooks FlightByte posts to your receiver."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import time
from datetime import datetime
from typing import Final, TypeAlias, cast

from ._errors import FlightByteError, WebhookSignatureError
from ._models import WebhookEvent

__all__ = ["Webhook", "WebhookPayload"]

WebhookPayload: TypeAlias = bytes | bytearray | memoryview | str
"""The payload as received: the raw body, before any JSON parsing."""

_TIMESTAMP: Final = re.compile(r"[0-9]{1,15}")
_SIGNATURE: Final = re.compile(r"[0-9a-f]{64}")


class Webhook:
    """Verifies and decodes the webhooks FlightByte posts to your receiver.

    Each delivery carries an ``x-flightbyte-signature`` header of the form
    ``t=<unix seconds>,v1=<hex>``, where the hex is HMAC-SHA256 of
    ``"<t>.<raw body>"`` keyed with the subscription's signing secret.

    Every method takes the body exactly as received, as bytes, before any JSON
    parsing: ``request.get_data()`` in Flask, ``request.body`` in Django,
    ``await request.body()`` in FastAPI and Starlette. Keep the signing secret
    on your server.
    """

    SIGNATURE_HEADER: Final = "x-flightbyte-signature"
    """Header carrying the signature."""
    TIMESTAMP_HEADER: Final = "x-flightbyte-timestamp"
    """Header carrying the signing time, in unix seconds."""
    EVENT_ID_HEADER: Final = "x-flightbyte-event-id"
    """Header carrying the event id."""
    EVENT_TYPE_HEADER: Final = "x-flightbyte-event-type"
    """Header carrying the event type."""
    SUBSCRIPTION_ID_HEADER: Final = "x-flightbyte-subscription-id"
    """Header carrying the subscription id."""
    DELIVERY_ATTEMPT_HEADER: Final = "x-flightbyte-delivery-attempt"
    """Header carrying the delivery attempt number, starting at 1."""
    DEFAULT_TOLERANCE: Final = 300
    """How far the signing time may be from now by default, in seconds: 5 minutes."""

    def __init__(self) -> None:
        raise TypeError("flightbyte: Webhook only has static methods; call Webhook.verify(...).")

    @staticmethod
    def verify(
        payload: WebhookPayload,
        signature: str | None,
        secret: str,
        *,
        tolerance: float = DEFAULT_TOLERANCE,
        now: datetime | float | None = None,
    ) -> None:
        """Checks ``signature`` against the raw body ``payload`` and the subscription's ``secret``.

        Args:
            payload: The body exactly as received. JSON parsed and serialised
                again no longer matches the signature.
            signature: The ``x-flightbyte-signature`` header, or ``None`` when
                the request had none.
            secret: The subscription's signing secret.
            tolerance: How far the signing time may be from now, in seconds.
                ``0`` skips the check. Defaults to 300, as on the API.
            now: The time to check against instead of now, as a ``datetime``
                or unix seconds. Useful in tests.

        Raises:
            WebhookSignatureError: The signature does not verify.
            ValueError: ``secret`` is empty. Anyone can sign with an empty
                key, so it usually means the secret was not configured.
        """
        key = _secret_key(secret)
        body = _payload_bytes(payload)
        timestamp, signatures = _parse_signature(signature)

        if tolerance > 0:
            current = math.floor(_seconds(now) if now is not None else time.time())
            signed_at = int(timestamp)
            # Compared against both edges, so an extreme timestamp cannot slip through.
            if signed_at < current - tolerance or signed_at > current + tolerance:
                raise WebhookSignatureError(
                    "The signature timestamp is outside the tolerance window."
                )

        expected = _hmac_hex(key, timestamp, body).encode("ascii")
        matched = False
        for candidate in signatures:
            # Every candidate is compared, in constant time, so the time taken
            # says nothing about which one matched or how much of it did.
            if _SIGNATURE.fullmatch(candidate) and hmac.compare_digest(
                candidate.encode("ascii"), expected
            ):
                matched = True
        if not matched:
            raise WebhookSignatureError("The signature does not match the payload.")

    @staticmethod
    def is_valid(
        payload: WebhookPayload,
        signature: str | None,
        secret: str,
        *,
        tolerance: float = DEFAULT_TOLERANCE,
        now: datetime | float | None = None,
    ) -> bool:
        """Whether ``signature`` verifies; see ``Webhook.verify``.

        Raises:
            ValueError: ``secret`` is empty.
        """
        try:
            Webhook.verify(payload, signature, secret, tolerance=tolerance, now=now)
        except WebhookSignatureError:
            return False
        return True

    @staticmethod
    def construct_event(
        payload: WebhookPayload,
        signature: str | None,
        secret: str,
        *,
        tolerance: float = DEFAULT_TOLERANCE,
        now: datetime | float | None = None,
    ) -> WebhookEvent:
        """Verifies the signature, then decodes the event.

        Raises:
            WebhookSignatureError: The signature does not verify.
            FlightByteError: The verified body is not a webhook event.
            ValueError: ``secret`` is empty.
        """
        Webhook.verify(payload, signature, secret, tolerance=tolerance, now=now)
        try:
            event = json.loads(_payload_bytes(payload))
        except ValueError as error:
            raise FlightByteError("The webhook body is not JSON.") from error
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("id"), str)
            or not isinstance(event.get("type"), str)
        ):
            raise FlightByteError("The webhook body is not a FlightByte event.")
        return cast(WebhookEvent, event)

    @staticmethod
    def sign(
        payload: WebhookPayload,
        secret: str,
        timestamp: datetime | float | None = None,
    ) -> str:
        """Signs ``payload`` the way the API does and returns the ``x-flightbyte-signature`` value.

        ``timestamp`` is the signing time, as a ``datetime`` or unix seconds;
        it defaults to now. Useful for testing your receiver.

        Raises:
            ValueError: ``secret`` is empty.
        """
        key = _secret_key(secret)
        body = _payload_bytes(payload)
        seconds = str(math.floor(_seconds(timestamp) if timestamp is not None else time.time()))
        return f"t={seconds},v1={_hmac_hex(key, seconds, body)}"


def _parse_signature(header: str | None) -> tuple[str, list[str]]:
    """Splits ``t=<seconds>,v1=<hex>[,v1=<hex>...]``."""
    if not isinstance(header, str) or not header.strip():
        raise WebhookSignatureError("The signature header is missing.")
    timestamp: str | None = None
    signatures: list[str] = []
    for part in header.split(","):
        index = part.find("=")
        if index <= 0:
            continue
        key = part[:index].strip()
        value = part[index + 1 :].strip()
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value.lower())
    # [0-9] and not \d, which also matches digits from other scripts.
    if timestamp is None or not _TIMESTAMP.fullmatch(timestamp):
        raise WebhookSignatureError("The signature header has no valid timestamp.")
    if not signatures:
        raise WebhookSignatureError("The signature header has no v1 signature.")
    return timestamp, signatures


def _secret_key(secret: str) -> bytes:
    if not isinstance(secret, str):
        raise TypeError("flightbyte: the webhook signing secret must be a string.")
    if not secret.strip():
        raise ValueError(
            "flightbyte: the webhook signing secret is empty. Anyone can sign with an "
            "empty key; set the subscription's secret."
        )
    return secret.encode("utf-8")


def _payload_bytes(payload: WebhookPayload) -> bytes:
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return bytes(payload)
    raise TypeError(
        "flightbyte: the webhook payload must be the raw body as bytes or str, "
        f"not {type(payload).__name__}. Pass the body before any JSON parsing."
    )


def _hmac_hex(key: bytes, timestamp: str, body: bytes) -> str:
    return hmac.new(key, timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()


def _seconds(value: datetime | float) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("flightbyte: a time must be a datetime or unix seconds.")
    return float(value)
