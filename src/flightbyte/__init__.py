"""The official Python client for the FlightByte flight status API.

Look flights up, watch them with signed webhooks and verify every delivery::

    import os
    from flightbyte import FlightByte

    client = FlightByte(api_key=os.environ["FLIGHTBYTE_API_KEY"])
    flight = client.flights.get("TK", "1848", "2026-09-08")
    print(flight["status"]["label"], flight["departure"].get("gate"))

Webhooks are verified with ``Webhook.construct_event``. Every error is a
``FlightByteError``.
"""

from ._client import FlightByte
from ._countries import Countries
from ._errors import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    FlightByteError,
    NotFoundError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnexpectedStatusError,
    UpstreamError,
    WebhookSignatureError,
)
from ._flights import Flights
from ._models import (
    DELIVERY_STATUSES,
    FLIGHT_CHANGE_TYPES,
    FLIGHT_PHASES,
    SUBSCRIPTION_STATUSES,
    WEBHOOK_EVENT_TYPES,
    AirportRef,
    AmbiguousLeg,
    CarrierRef,
    CodeshareRef,
    Country,
    CountryRef,
    CreatedSubscription,
    DeliveryRecord,
    DeliveryStatus,
    DurationInfo,
    EndpointTimes,
    EquipmentInfo,
    FlightChange,
    FlightChangeType,
    FlightEndpoint,
    FlightLegRef,
    FlightPhase,
    FlightSnapshot,
    FlightStatusInfo,
    FlightTime,
    FlightTimeline,
    Subscription,
    SubscriptionPage,
    SubscriptionStatus,
    TimelineEntry,
    WebhookEvent,
    WebhookEventType,
    best_gate_time,
    is_terminal_phase,
)
from ._rate_limit import RateLimit, RateLimitWindow
from ._subscriptions import Subscriptions, mask_secret
from ._transport import NOT_GIVEN, NotGiven
from ._version import __version__
from ._webhook import Webhook, WebhookPayload

__all__ = [
    "DELIVERY_STATUSES",
    "FLIGHT_CHANGE_TYPES",
    "FLIGHT_PHASES",
    "NOT_GIVEN",
    "SUBSCRIPTION_STATUSES",
    "WEBHOOK_EVENT_TYPES",
    "APIConnectionError",
    "APIError",
    "AirportRef",
    "AmbiguousLeg",
    "AuthenticationError",
    "BadRequestError",
    "CarrierRef",
    "CodeshareRef",
    "Countries",
    "Country",
    "CountryRef",
    "CreatedSubscription",
    "DeliveryRecord",
    "DeliveryStatus",
    "DurationInfo",
    "EndpointTimes",
    "EquipmentInfo",
    "FlightByte",
    "FlightByteError",
    "FlightChange",
    "FlightChangeType",
    "FlightEndpoint",
    "FlightLegRef",
    "FlightPhase",
    "FlightSnapshot",
    "FlightStatusInfo",
    "FlightTime",
    "FlightTimeline",
    "Flights",
    "NotFoundError",
    "NotGiven",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "RateLimit",
    "RateLimitError",
    "RateLimitWindow",
    "ServerError",
    "Subscription",
    "SubscriptionPage",
    "SubscriptionStatus",
    "Subscriptions",
    "TimelineEntry",
    "UnexpectedStatusError",
    "UpstreamError",
    "Webhook",
    "WebhookEvent",
    "WebhookEventType",
    "WebhookPayload",
    "WebhookSignatureError",
    "__version__",
    "best_gate_time",
    "is_terminal_phase",
    "mask_secret",
]
