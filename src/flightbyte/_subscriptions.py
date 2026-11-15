"""Watched flights and their webhooks."""

from __future__ import annotations

import builtins
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, cast

from ._models import (
    CreatedSubscription,
    DeliveryRecord,
    FlightChangeType,
    Subscription,
    SubscriptionPage,
    SubscriptionStatus,
    WebhookEvent,
)
from ._transport import NOT_GIVEN, NotGiven, Transport, check_header_value, required
from ._util import data_of, string_of

__all__ = ["Subscriptions", "mask_secret"]


class Subscriptions:
    """Watched flights and their webhooks. Reach it as ``client.subscriptions``.

    Every subscription is a billable watched flight.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def create(
        self,
        carrier: str,
        flight_number: str,
        date: str,
        webhook_url: str,
        *,
        origin: str | None = None,
        destination: str | None = None,
        flight_id: str | None = None,
        secret: str | None = None,
        events: Iterable[FlightChangeType] | None = None,
        delay_threshold_minutes: int | None = None,
        headers: Mapping[str, str] | None = None,
        metadata: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> CreatedSubscription:
        """Starts watching a flight.

        The API posts a signed webhook to ``webhook_url``, a public HTTPS URL,
        each time something about the flight changes. The response carries
        the signing secret in full, this once.

        Args:
            carrier: Carrier code, for example ``TK``.
            flight_number: Flight number, for example ``1848``.
            date: Local departure date at the origin, ``YYYY-MM-DD``.
            webhook_url: Where webhooks are posted.
            origin: Selects a leg, when the flight number flies several that day.
            destination: Narrows the leg further.
            flight_id: Selects a leg by its upstream id.
            secret: The webhook signing secret. By default the API generates
                one. Setting the same secret on every subscription lets one
                receiver verify them all.
            events: Change types that trigger a webhook. By default every type does.
            delay_threshold_minutes: Ignore delay swings smaller than this, 1 to 240.
            headers: Extra headers sent with every delivery.
            metadata: Your own data, echoed back in every webhook.
            idempotency_key: Makes retries safe: repeating the request with the
                same key within 24 hours returns the original subscription with
                ``reused: True``, instead of creating and billing a second one.
            timeout: Overrides the client's timeout for this request.

        Raises:
            PaymentRequiredError: No watched flights are left.
            BadRequestError: With ``legs`` set, when the flight number flies
                several legs that day and neither ``origin`` nor ``flight_id``
                chose one.
        """
        body = _without_none(
            {
                "carrier": required("carrier", carrier),
                "flightNumber": required("flight_number", flight_number),
                "date": required("date", date),
                "webhookUrl": required("webhook_url", webhook_url),
                "origin": origin,
                "destination": destination,
                "flightId": flight_id,
                "secret": secret,
                "events": None if events is None else builtins.list(events),
                "delayThresholdMinutes": delay_threshold_minutes,
                "headers": None if headers is None else dict(headers),
                "metadata": None if metadata is None else dict(metadata),
            }
        )
        request_headers = None
        if idempotency_key:
            request_headers = {
                "idempotency-key": check_header_value("idempotency_key", idempotency_key)
            }
        result = self._transport.send(
            "POST", ["subscriptions"], body=body, headers=request_headers, timeout=timeout
        )
        if isinstance(result, dict) and not result.get("secretHint"):
            secret_value = result.get("secret")
            if isinstance(secret_value, str) and secret_value:
                result["secretHint"] = mask_secret(secret_value)
        return cast(CreatedSubscription, result)

    def list(
        self,
        *,
        status: SubscriptionStatus | None = None,
        carrier: str | None = None,
        flight_number: str | None = None,
        date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> SubscriptionPage:
        """One page of your subscriptions, newest first.

        The filters keep subscriptions in that ``status``, for that
        ``carrier``, ``flight_number`` or ``date``. ``limit`` is the page size;
        the API clamps it to 1 to 200 and defaults to 25. ``offset`` is the
        number of subscriptions to skip.
        """
        result = self._transport.send(
            "GET",
            ["subscriptions"],
            query={
                "status": status,
                "carrier": carrier,
                "flightNumber": flight_number,
                "date": date,
                "limit": limit,
                "offset": offset,
            },
            timeout=timeout,
        )
        return cast(SubscriptionPage, result)

    def list_all(
        self,
        *,
        status: SubscriptionStatus | None = None,
        carrier: str | None = None,
        flight_number: str | None = None,
        date: str | None = None,
        offset: int | None = None,
        page_size: int = 200,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> Iterator[Subscription]:
        """Every subscription matching the filters, fetched page by page as you iterate.

        Nothing is sent until the first item is asked for, and nothing more
        once you stop: ``break`` out of the loop and no further page is
        fetched. ``page_size`` is 1 to 200; the default is 200. ``timeout``
        applies to each page::

            for sub in client.subscriptions.list_all(status="active"):
                print(sub["flightKey"])
        """
        next_offset = offset or 0
        while True:
            page = self.list(
                status=status,
                carrier=carrier,
                flight_number=flight_number,
                date=date,
                limit=page_size,
                offset=next_offset,
                timeout=timeout,
            )
            data = page["data"]
            yield from data
            following = page["offset"] + len(data)
            if not data or following >= page["total"]:
                return
            next_offset = following

    def get(self, id: str, *, timeout: float | NotGiven | None = NOT_GIVEN) -> Subscription:
        """One subscription.

        Raises:
            NotFoundError: It does not exist or belongs to another key.
        """
        return cast(Subscription, self._send("GET", id, timeout=timeout))

    def update(
        self,
        id: str,
        *,
        webhook_url: str | None = None,
        events: Iterable[FlightChangeType] | None = None,
        delay_threshold_minutes: int | None = None,
        headers: Mapping[str, str] | None = None,
        metadata: Mapping[str, str] | None = None,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> Subscription:
        """Changes a subscription. Only the arguments you pass change.

        ``webhook_url`` moves deliveries to another URL; ``events`` replaces
        the change type filter; ``delay_threshold_minutes`` replaces the delay
        threshold. ``headers`` and ``metadata`` replace the existing maps; the
        API cannot clear them, so an empty map leaves them as they are.
        """
        body = _without_none(
            {
                "webhookUrl": webhook_url,
                "events": None if events is None else builtins.list(events),
                "delayThresholdMinutes": delay_threshold_minutes,
                "headers": None if headers is None else dict(headers),
                "metadata": None if metadata is None else dict(metadata),
            }
        )
        return cast(Subscription, self._send("PATCH", id, body=body, timeout=timeout))

    def delete(self, id: str, *, timeout: float | NotGiven | None = NOT_GIVEN) -> None:
        """Stops watching the flight and deletes the subscription for good."""
        self._send("DELETE", id, timeout=timeout)

    def pause(self, id: str, *, timeout: float | NotGiven | None = NOT_GIVEN) -> Subscription:
        """Pauses polling and deliveries; ``resume`` picks up where it left off."""
        return cast(Subscription, self._send("POST", id, "pause", timeout=timeout))

    def resume(self, id: str, *, timeout: float | NotGiven | None = NOT_GIVEN) -> Subscription:
        """Resumes a paused or suspended subscription.

        Raises:
            BadRequestError: The subscription is completed and cannot be resumed.
        """
        return cast(Subscription, self._send("POST", id, "resume", timeout=timeout))

    def send_test(self, id: str, *, timeout: float | NotGiven | None = NOT_GIVEN) -> str:
        """Sends a signed ``subscription.test`` webhook and returns its event id."""
        result = self._send("POST", id, "test", timeout=timeout)
        return string_of(result, "eventId", "POST /subscriptions/{id}/test")

    def deliveries(
        self,
        id: str,
        *,
        limit: int | None = None,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> builtins.list[DeliveryRecord]:
        """The latest delivery attempts, newest first.

        ``limit`` is 1 to 100; the API's default is 25.
        """
        result = self._send("GET", id, "deliveries", query={"limit": limit}, timeout=timeout)
        return cast(
            "builtins.list[DeliveryRecord]", data_of(result, "GET /subscriptions/{id}/deliveries")
        )

    def events(
        self,
        id: str,
        *,
        limit: int | None = None,
        timeout: float | NotGiven | None = NOT_GIVEN,
    ) -> builtins.list[WebhookEvent]:
        """The latest events, exactly as they were posted, newest first.

        ``limit`` is 1 to 100; the API's default is 25.
        """
        result = self._send("GET", id, "events", query={"limit": limit}, timeout=timeout)
        return cast(
            "builtins.list[WebhookEvent]", data_of(result, "GET /subscriptions/{id}/events")
        )

    def secret(self, id: str, *, timeout: float | NotGiven | None = NOT_GIVEN) -> str:
        """The full webhook signing secret."""
        result = self._send("GET", id, "secret", timeout=timeout)
        return string_of(result, "secret", "GET /subscriptions/{id}/secret")

    def rotate_secret(self, id: str, *, timeout: float | NotGiven | None = NOT_GIVEN) -> str:
        """Replaces the webhook signing secret and returns the new one.

        Deliveries are signed with it from now on, so update your receiver
        right away.
        """
        result = self._send("POST", id, "secret", "rotate", timeout=timeout)
        return string_of(result, "secret", "POST /subscriptions/{id}/secret/rotate")

    def _send(
        self,
        method: str,
        id: str,
        *rest: str,
        query: dict[str, Any] | None = None,
        body: object = None,
        timeout: float | NotGiven | None,
    ) -> Any:
        return self._transport.send(
            method,
            ["subscriptions", required("id", id), *rest],
            query=query,
            body=body,
            timeout=timeout,
        )


def mask_secret(secret: str) -> str:
    """Masks a signing secret the way the API does.

    The first 11 characters, ``...``, and the last 4. Short secrets are
    returned as they are.
    """
    return secret if len(secret) <= 15 else f"{secret[:11]}...{secret[-4:]}"


def _without_none(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}
