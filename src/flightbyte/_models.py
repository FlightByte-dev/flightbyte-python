"""The shapes the FlightByte API answers with.

Responses are returned exactly as the API sent them, as plain ``dict`` objects:
keys keep the API's own camelCase names, timestamps stay ISO 8601 strings, and
nothing is renamed or dropped. These ``TypedDict`` classes describe them, so a
type checker and your editor know every key. Type names follow the API's
OpenAPI document.

Keys the API may leave out are not required, and values it may send as
``null`` include ``None``, so ``delayMinutes == 0`` and "no delay reading" stay
apart. Read a key that may be missing with ``.get()``.

String enums (phases, statuses, change and event types) are typed as ``str``:
a value the API adds after this release is still a valid string, so nothing
breaks. The values this version knows are listed in ``FLIGHT_PHASES``,
``SUBSCRIPTION_STATUSES``, ``FLIGHT_CHANGE_TYPES``, ``WEBHOOK_EVENT_TYPES`` and
``DELIVERY_STATUSES``.
"""

# Each model with keys the API may leave out is split in two: a base with the
# keys that are always there, and the public class with ``total=False`` for
# the rest. ``typing.NotRequired`` would read better but needs Python 3.11,
# and this package supports 3.10 without depending on typing_extensions.

from typing import Final, TypeAlias, TypedDict

__all__ = [
    "DELIVERY_STATUSES",
    "FLIGHT_CHANGE_TYPES",
    "FLIGHT_PHASES",
    "SUBSCRIPTION_STATUSES",
    "WEBHOOK_EVENT_TYPES",
    "AirportRef",
    "AmbiguousLeg",
    "CarrierRef",
    "CodeshareRef",
    "Country",
    "CountryRef",
    "CreatedSubscription",
    "DeliveryRecord",
    "DeliveryStatus",
    "DurationInfo",
    "EndpointTimes",
    "EquipmentInfo",
    "FlightChange",
    "FlightChangeType",
    "FlightEndpoint",
    "FlightLegRef",
    "FlightPhase",
    "FlightSnapshot",
    "FlightStatusInfo",
    "FlightTime",
    "FlightTimeline",
    "Subscription",
    "SubscriptionPage",
    "SubscriptionStatus",
    "TimelineEntry",
    "WebhookEvent",
    "WebhookEventType",
    "best_gate_time",
    "is_terminal_phase",
]

FlightPhase: TypeAlias = str
"""The coarse lifecycle bucket of a flight; one of ``FLIGHT_PHASES`` or a newer value."""

SubscriptionStatus: TypeAlias = str
"""The lifecycle of a subscription; one of ``SUBSCRIPTION_STATUSES`` or a newer value.

``active`` polls and delivers, ``pending`` waits for the flight to be published
upstream, ``paused`` was paused by you, ``completed`` finished after the flight
did, ``suspended`` was disabled by the API, for example after repeated delivery
failures.
"""

FlightChangeType: TypeAlias = str
"""The kind of change a ``flight.updated`` webhook reports, and what a
subscription's ``events`` filter is made of; one of ``FLIGHT_CHANGE_TYPES`` or
a newer value."""

WebhookEventType: TypeAlias = str
"""The type of a webhook event; one of ``WEBHOOK_EVENT_TYPES`` or a newer value."""

DeliveryStatus: TypeAlias = str
"""The outcome of one webhook delivery attempt; one of ``DELIVERY_STATUSES`` or a newer value."""

FLIGHT_PHASES: Final[tuple[str, ...]] = (
    "scheduled",
    "boarding",
    "departed",
    "en_route",
    "landed",
    "arrived",
    "cancelled",
    "diverted",
    "redirected",
    "unknown",
)
"""Every flight phase this version knows, in the API's order."""

SUBSCRIPTION_STATUSES: Final[tuple[str, ...]] = (
    "active",
    "pending",
    "paused",
    "completed",
    "suspended",
)
"""Every subscription status this version knows."""

FLIGHT_CHANGE_TYPES: Final[tuple[str, ...]] = (
    "status.changed",
    "flight.departed",
    "flight.arrived",
    "flight.cancelled",
    "flight.diverted",
    "flight.reinstated",
    "departure.gate.changed",
    "departure.terminal.changed",
    "arrival.gate.changed",
    "arrival.terminal.changed",
    "arrival.baggage.changed",
    "departure.scheduled.changed",
    "departure.estimated.changed",
    "departure.actual.changed",
    "arrival.scheduled.changed",
    "arrival.estimated.changed",
    "arrival.actual.changed",
    "delay.increased",
    "delay.decreased",
    "aircraft.changed",
    "aircraft.tail.changed",
    "route.changed",
    "codeshares.changed",
)
"""Every flight change type this version knows, in the API's order."""

WEBHOOK_EVENT_TYPES: Final[tuple[str, ...]] = (
    "subscription.created",
    "subscription.activated",
    "subscription.test",
    "subscription.completed",
    "subscription.suspended",
    "flight.updated",
)
"""Every webhook event type this version knows."""

DELIVERY_STATUSES: Final[tuple[str, ...]] = ("delivered", "failed")
"""Every delivery status this version knows."""

_TERMINAL_PHASES: Final = frozenset({"arrived", "cancelled", "diverted", "redirected"})


def is_terminal_phase(phase: FlightPhase) -> bool:
    """Whether the flight is finished: arrived, cancelled, diverted or redirected."""
    return phase in _TERMINAL_PHASES


class CountryRef(TypedDict):
    """A country as it appears inside an airport."""

    code: str
    """ISO 3166-1 alpha-2 code, for example ``TR``."""
    name: str
    """Country name."""
    emoji: str
    """Flag emoji."""
    flagSvg: str
    """Absolute URL of the 4:3 SVG flag."""
    flagSvgSquare: str
    """Absolute URL of the 1:1 SVG flag."""


class Country(CountryRef):
    """A country from the ``/countries`` endpoints."""

    alpha2: str
    """ISO 3166-1 alpha-2 code."""
    hasFlag: bool
    """Whether a flag image exists for the country."""


class _AirportRefRequired(TypedDict):
    iata: str
    """IATA code, for example ``IST``."""
    name: str
    """Airport name."""
    country: CountryRef
    """Country."""


class AirportRef(_AirportRefRequired, total=False):
    """An airport."""

    icao: str | None
    """ICAO code, for example ``LTFM``."""
    code: str | None
    """The upstream's own airport code; it may differ from ``iata``."""
    city: str | None
    """City."""
    state: str | None
    """State or region."""
    timezone: str | None
    """IANA time zone, for example ``Europe/Istanbul``."""


class _FlightTimeRequired(TypedDict):
    utc: str
    """The instant, ISO 8601 in UTC."""


class FlightTime(_FlightTimeRequired, total=False):
    """A point in time, in UTC and in the airport's local time."""

    local: str | None
    """Airport-local wall time without an offset, for example ``2026-09-08T12:10:00.000``.

    Pair it with the airport's time zone.
    """
    timezone: str | None
    """Time zone abbreviation, for example ``EEST``."""


class EndpointTimes(TypedDict, total=False):
    """The gate and runway times of a departure or an arrival."""

    scheduledGate: FlightTime | None
    """Scheduled gate time."""
    estimatedGate: FlightTime | None
    """Estimated gate time."""
    actualGate: FlightTime | None
    """Actual gate time."""
    scheduledRunway: FlightTime | None
    """Scheduled runway time."""
    estimatedRunway: FlightTime | None
    """Estimated runway time."""
    actualRunway: FlightTime | None
    """Actual runway time."""


def best_gate_time(times: EndpointTimes) -> FlightTime | None:
    """The best known gate time: actual, else estimated, else scheduled."""
    for value in (times.get("actualGate"), times.get("estimatedGate"), times.get("scheduledGate")):
        if value is not None:
            return value
    return None


class _FlightEndpointRequired(TypedDict):
    airport: AirportRef
    """The airport."""
    times: EndpointTimes
    """Gate and runway times."""


class FlightEndpoint(_FlightEndpointRequired, total=False):
    """The departure or arrival side of a flight."""

    terminal: str | None
    """Terminal."""
    gate: str | None
    """Gate."""
    baggage: str | None
    """Baggage carousel, on arrival."""
    bestTimeUtc: str | None
    """Best known time in UTC: actual, else estimated, else scheduled."""
    delayMinutes: int | None
    """Gate delay in minutes; negative when early."""


class _CarrierRefRequired(TypedDict):
    iata: str
    """IATA code, for example ``TK``."""
    name: str
    """Airline name."""


class CarrierRef(_CarrierRefRequired, total=False):
    """The marketing carrier."""

    icao: str | None
    """ICAO code, for example ``THY``."""


class CodeshareRef(TypedDict):
    """A codeshare flight number sold on the same flight."""

    carrier: str
    """Carrier code."""
    name: str
    """Carrier name."""
    flightNumber: str
    """Flight number."""


class _FlightStatusInfoRequired(TypedDict):
    code: str
    """Upstream status code: ``S``, ``A``, ``L``, ``C``, ``D``, ``R``, ``U`` or ``NO``."""
    label: str
    """Human-readable status, for example ``Arrived``."""
    phase: FlightPhase
    """The lifecycle phase."""
    delayed: bool
    """Whether the flight is delayed."""
    cancelled: bool
    """Whether the flight is cancelled."""
    diverted: bool
    """Whether the flight is diverted."""


class FlightStatusInfo(_FlightStatusInfoRequired, total=False):
    """The status of a flight."""

    description: str | None
    """Longer description, for example ``On time``."""
    color: str | None
    """Suggested color, for example ``green``."""
    departureGateDelayMinutes: int | None
    """Departure gate delay in minutes."""
    arrivalGateDelayMinutes: int | None
    """Arrival gate delay in minutes."""


class EquipmentInfo(TypedDict, total=False):
    """The aircraft."""

    tailNumber: str | None
    """Registration, for example ``TC-LTP``."""
    iata: str | None
    """IATA aircraft type, for example ``32Q``."""
    name: str | None
    """Aircraft name, for example ``Airbus A321neo``."""
    source: str | None
    """Where the data came from, for example ``Actual``."""


class DurationInfo(TypedDict, total=False):
    """Block times in minutes."""

    scheduledMinutes: int | None
    """Scheduled duration."""
    estimatedMinutes: int | None
    """Estimated duration."""
    actualMinutes: int | None
    """Actual duration."""


class _TimelineEntryRequired(TypedDict):
    occurredAt: str
    """When it happened, ISO 8601."""
    title: str
    """Title, for example ``Time Adjustment``."""
    events: list[str]
    """What changed, as sentences."""


class TimelineEntry(_TimelineEntryRequired, total=False):
    """One entry of a flight's upstream history."""

    source: str | None
    """Source, for example ``Airline``."""


class _FlightLegRefRequired(TypedDict):
    departureIata: str
    """Origin IATA code."""
    arrivalIata: str
    """Destination IATA code."""
    selected: bool
    """Whether this is the leg the snapshot describes."""


class FlightLegRef(_FlightLegRefRequired, total=False):
    """A leg flown under the same flight number on the same date.

    Flight numbers are not unique per day, so the API lists every leg and
    marks the one the snapshot describes with ``selected``.
    """

    providerFlightId: str | None
    """Upstream flight id; pass it as ``flight_id`` to select this leg."""
    carrier: str | None
    """Operating carrier code."""
    scheduledDepartureLocal: str | None
    """Scheduled local departure, ``HH:mm``."""
    scheduledArrivalLocal: str | None
    """Scheduled local arrival, ``HH:mm``."""


class _FlightSnapshotRequired(TypedDict):
    flightKey: str
    """Stable key, for example ``TK1848:2026-09-08`` or ``TK1:2026-09-08@IST-JFK``."""
    carrierCode: str
    """Carrier code from the request, for example ``TK``."""
    flightNumber: str
    """Flight number without leading zeros, for example ``1848``."""
    date: str
    """Local departure date at the origin, ``YYYY-MM-DD``."""
    fetchedAt: str
    """When the API fetched this data from upstream, ISO 8601."""
    carrier: CarrierRef
    """Marketing carrier."""
    codeshares: list[CodeshareRef]
    """Codeshare flight numbers."""
    departure: FlightEndpoint
    """Departure side."""
    arrival: FlightEndpoint
    """Arrival side."""
    status: FlightStatusInfo
    """Status."""
    equipment: EquipmentInfo
    """Aircraft."""
    duration: DurationInfo
    """Block times."""
    timeline: list[TimelineEntry]
    """Upstream history, newest first."""
    alternates: list[FlightLegRef]
    """Every leg flown under this flight number on this date."""
    fingerprint: str
    """Hash over the change-relevant fields."""


class FlightSnapshot(_FlightSnapshotRequired, total=False):
    """Everything known about one flight leg at one moment."""

    providerFlightId: str | None
    """Upstream flight id."""
    operatedBy: str | None
    """Operating carrier name, when different."""
    diverted: FlightEndpoint | None
    """Where the flight actually went, when diverted."""
    cached: bool
    """Whether a lookup was answered from the API's cache.

    Sent with lookups, not inside webhook events.
    """


class FlightTimeline(TypedDict):
    """The response of ``flights.timeline``."""

    flightKey: str
    """The flight's key."""
    count: int
    """The number of entries."""
    data: list[TimelineEntry]
    """History entries, newest first."""


class _SubscriptionRequired(TypedDict):
    id: str
    """Id, for example ``sub_7Kd91mQx0Zb2c3d4e5f6``."""
    status: SubscriptionStatus
    """Lifecycle status."""
    flightKey: str
    """The watched flight's key, for example ``TK1848:2026-09-08``."""
    carrier: str
    """Carrier code."""
    flightNumber: str
    """Flight number."""
    date: str
    """Local departure date at the origin, ``YYYY-MM-DD``."""
    webhookUrl: str
    """Where webhooks are posted."""
    events: list[FlightChangeType]
    """The change types that trigger a webhook."""
    delayThresholdMinutes: int
    """Delay swings smaller than this many minutes are ignored."""
    createdAt: str
    """When it was created, ISO 8601."""
    updatedAt: str
    """When it last changed, ISO 8601."""
    deliveredCount: int
    """Webhooks delivered."""
    failedCount: int
    """Webhook attempts that failed."""
    flightResolved: bool
    """``False`` while the flight is not found upstream yet."""


class _SubscriptionOptional(TypedDict, total=False):
    headers: dict[str, str] | None
    """Extra headers sent with every delivery."""
    metadata: dict[str, str] | None
    """Your own data, echoed back in every webhook."""
    lastPolledAt: str | None
    """When the flight was last polled, ISO 8601."""
    lastChangeAt: str | None
    """When a change was last detected, ISO 8601."""
    lastDeliveryAt: str | None
    """When a webhook was last delivered, ISO 8601."""
    statusReason: str | None
    """Why the subscription was suspended or completed."""


class Subscription(_SubscriptionRequired, _SubscriptionOptional, total=False):
    """A watched flight.

    The API polls it and posts a signed webhook to ``webhookUrl`` whenever
    something about it changes.
    """

    secretHint: str
    """The masked signing secret, for example ``whsec_AbCdE...wxyz``."""
    secret: str
    """The full signing secret.

    Only the creation response carries it; read it again with
    ``subscriptions.secret``.
    """


class _CreatedSubscriptionRequired(_SubscriptionRequired, _SubscriptionOptional):
    secret: str
    """The full webhook signing secret.

    Returned in full only here and from ``subscriptions.secret``; store it
    where your webhook receiver can read it.
    """
    secretHint: str
    """The masked signing secret."""
    reused: bool
    """``True`` when an earlier request with the same idempotency key was replayed.

    Within 24 hours, the original subscription is returned and nothing new is
    created or billed.
    """


class CreatedSubscription(_CreatedSubscriptionRequired, total=False):
    """The response of ``subscriptions.create``.

    It has every key of ``Subscription``, with ``secret`` and ``secretHint``
    always present.
    """

    flight: FlightSnapshot | None
    """The flight as first seen, when it was found. Absent when ``reused``."""


class SubscriptionPage(TypedDict):
    """One page of ``subscriptions.list``."""

    total: int
    """The number of subscriptions matching the filters."""
    limit: int
    """The page size used."""
    offset: int
    """The number of subscriptions skipped."""
    data: list[Subscription]
    """The subscriptions on this page, newest first."""


class _DeliveryRecordRequired(TypedDict):
    eventId: str
    """The delivered event's id."""
    attempt: int
    """Attempt number, starting at 1."""
    status: DeliveryStatus
    """The outcome."""
    durationMs: int
    """How long the attempt took, in milliseconds."""
    at: str
    """When the attempt was made, ISO 8601."""
    changeTypes: list[FlightChangeType]
    """The change types the event carried."""


class DeliveryRecord(_DeliveryRecordRequired, total=False):
    """One webhook delivery attempt."""

    httpStatus: int | None
    """The receiver's HTTP status, when it answered."""
    error: str | None
    """What went wrong, when the attempt failed."""


# ``from`` is a Python keyword, so this one is spelled the functional way.
_FlightChangeRequired = TypedDict(
    "_FlightChangeRequired",
    {
        "type": FlightChangeType,
        "path": str,
        "from": str | int | float | bool | None,
        "to": str | int | float | bool | None,
        "message": str,
    },
)


class FlightChange(_FlightChangeRequired, total=False):
    """One change inside a ``flight.updated`` event.

    Keys: ``type`` (what changed), ``path`` (dotted path into the snapshot,
    for example ``departure.gate``), ``from`` and ``to`` (the old and the new
    value; times are ISO 8601 UTC strings), ``message`` (a sentence describing
    the change) and ``deltaMinutes``.
    """

    deltaMinutes: int | None
    """Signed minute delta, for time changes."""


class _WebhookEventRequired(TypedDict):
    id: str
    """Event id, ``evt_<uuid>``. The same across delivery retries: deduplicate on it."""
    type: WebhookEventType
    """The event type."""
    createdAt: str
    """When the event was created, ISO 8601."""
    subscriptionId: str
    """The subscription it belongs to."""
    flightKey: str
    """The flight's key."""
    changes: list[FlightChange]
    """What changed. Empty except on ``flight.updated``."""


class WebhookEvent(_WebhookEventRequired, total=False):
    """A webhook event, as posted to your receiver and as listed by ``subscriptions.events``."""

    flight: FlightSnapshot | None
    """The flight after the change. Missing on some lifecycle events."""
    previousFetchedAt: str | None
    """When the previous snapshot was fetched, on ``flight.updated``."""
    metadata: dict[str, str] | None
    """The subscription's metadata."""


class _AmbiguousLegRequired(TypedDict):
    origin: str
    """Origin IATA code."""
    destination: str
    """Destination IATA code."""


class AmbiguousLeg(_AmbiguousLegRequired, total=False):
    """One of the legs listed by an ambiguous-flight ``BadRequestError``."""

    carrier: str
    """Operating carrier."""
    scheduledDepartureLocal: str
    """Scheduled local departure, ``HH:mm``."""
    flightId: str
    """Upstream flight id."""
