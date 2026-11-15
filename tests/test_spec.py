"""Drift check: the client and its types must line up with the vendored OpenAPI
document (spec/openapi.json).

Refresh the copy with ``python scripts/sync_openapi.py``; if the API added,
renamed or moved anything, these tests say what.
"""

import inspect
import json
import re
import unittest
from collections.abc import Callable
from typing import Any

import flightbyte
from flightbyte import (
    FLIGHT_CHANGE_TYPES,
    FLIGHT_PHASES,
    SUBSCRIPTION_STATUSES,
    FlightByte,
    Flights,
    PaymentRequiredError,
    Subscriptions,
)

from .helpers import ROOT, APITestCase, json_reply

SPEC = json.loads((ROOT / "spec" / "openapi.json").read_text(encoding="utf-8"))
SCHEMAS: dict[str, Any] = SPEC["components"]["schemas"]

OPERATIONS: dict[str, dict[str, Any]] = {
    operation["operationId"]: {"method": method.upper(), "path": path, **operation}
    for path, methods in SPEC["paths"].items()
    for method, operation in methods.items()
    if isinstance(operation, dict) and "operationId" in operation
}

# Operations without a method of their own, and why.
NOT_EXPOSED = {
    "search-flights": "the same lookup as get-flight, with the identifiers in the query string",
    "get-flag": "returns an SVG image; countries.flag_url builds its URL",
}

CALLS: dict[str, tuple[Callable[..., Any], Callable[[FlightByte], Any]]] = {
    "list-countries": (flightbyte.Countries.list, lambda c: c.countries.list()),
    "get-country": (flightbyte.Countries.get, lambda c: c.countries.get("TR")),
    "get-flight": (Flights.get, lambda c: c.flights.get("TK", "1848", "2026-09-08")),
    "flight-timeline": (Flights.timeline, lambda c: c.flights.timeline("TK", "1848", "2026-09-08")),
    "create-subscription": (
        Subscriptions.create,
        lambda c: c.subscriptions.create("TK", "1848", "2026-09-08", "https://example.com/h"),
    ),
    "list-subscriptions": (Subscriptions.list, lambda c: c.subscriptions.list()),
    "get-subscription": (Subscriptions.get, lambda c: c.subscriptions.get("sub_1")),
    "update-subscription": (Subscriptions.update, lambda c: c.subscriptions.update("sub_1")),
    "delete-subscription": (Subscriptions.delete, lambda c: c.subscriptions.delete("sub_1")),
    "pause-subscription": (Subscriptions.pause, lambda c: c.subscriptions.pause("sub_1")),
    "resume-subscription": (Subscriptions.resume, lambda c: c.subscriptions.resume("sub_1")),
    "send-test-event": (Subscriptions.send_test, lambda c: c.subscriptions.send_test("sub_1")),
    "list-deliveries": (Subscriptions.deliveries, lambda c: c.subscriptions.deliveries("sub_1")),
    "list-events": (Subscriptions.events, lambda c: c.subscriptions.events("sub_1")),
    "reveal-secret": (Subscriptions.secret, lambda c: c.subscriptions.secret("sub_1")),
    "rotate-secret": (
        Subscriptions.rotate_secret,
        lambda c: c.subscriptions.rotate_secret("sub_1"),
    ),
}

# Parameters the document lists that are not a keyword argument of the same
# name, and where they went instead.
PARAMETERS_ELSEWHERE = {
    ("create-subscription", "Idempotency-Key"): "idempotency_key",
}

# Schemas that are a request body, checked against a method's arguments.
REQUEST_BODIES: dict[str, Callable[..., Any]] = {
    "CreateSubscriptionDto": Subscriptions.create,
    "UpdateSubscriptionDto": Subscriptions.update,
}
# Schemas that are an error body rather than a model; checked below.
ERROR_BODIES = {"WatchedFlightsUsedUp"}

# Keys the API sends that the document leaves out, and why the types have them.
UNDOCUMENTED_FIELDS = {
    "FlightSnapshot.cached": "lookups say whether the cache answered; the document leaves it out",
    "Subscription.secretHint": "every response but the creation one carries the masked secret",
}
# Keys the document marks required that the types leave optional, and why.
LOOSER_THAN_DOCUMENTED = {
    "Subscription.secret": "only the creation response carries the full secret",
}

# Arguments every method takes that are not part of the API.
CLIENT_ARGUMENTS = {"self", "timeout"}


def snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def path_pattern(template: str) -> str:
    return "^" + re.sub(r"\{[^}]+\}", "[^/]+", template) + "$"


class OperationsTest(APITestCase):
    def test_nothing_is_left_unaccounted_for(self) -> None:
        covered = set(CALLS) | set(NOT_EXPOSED)
        self.assertEqual(sorted(set(OPERATIONS) - covered), [])
        self.assertEqual(sorted(covered - set(OPERATIONS)), [])

    def test_every_operation_is_sent_with_its_method_and_path(self) -> None:
        for operation_id, (_method, call) in CALLS.items():
            with self.subTest(operation_id):
                expected = OPERATIONS[operation_id]
                api = self.start(
                    lambda request: json_reply(200, {"data": [], "secret": "s", "eventId": "e"})
                )
                call(api.client(base_url=f"{api.url}/v1"))
                self.assertEqual(api.last().method, expected["method"])
                self.assertRegex(api.last().path, path_pattern(expected["path"]))

    def test_every_documented_parameter_is_an_argument(self) -> None:
        for operation_id, (method, _call) in CALLS.items():
            with self.subTest(operation_id):
                arguments = set(inspect.signature(method).parameters) - CLIENT_ARGUMENTS
                for parameter in OPERATIONS[operation_id].get("parameters", []):
                    name = parameter["name"]
                    expected = PARAMETERS_ELSEWHERE.get((operation_id, name), snake_case(name))
                    self.assertIn(expected, arguments, f"{name} has no argument")

    def test_get_flag_through_flag_url(self) -> None:
        url = FlightByte("k").countries.flag_url("TR")
        path = url.removeprefix("https://api.flightbyte.dev")
        self.assertRegex(path, path_pattern(OPERATIONS["get-flag"]["path"]))
        documented = {p["name"] for p in OPERATIONS["get-flag"]["parameters"]}
        self.assertEqual(documented, {"file", "shape"})
        self.assertTrue(
            FlightByte("k").countries.flag_url("TR", square=True).endswith("?shape=1x1")
        )


class SchemasTest(unittest.TestCase):
    def test_every_model_schema_has_a_type_with_the_same_keys(self) -> None:
        for schema_name, schema in SCHEMAS.items():
            if schema_name in ERROR_BODIES or schema_name in REQUEST_BODIES:
                continue
            with self.subTest(schema_name):
                model: Any = getattr(flightbyte, schema_name, None)
                assert model is not None, f"flightbyte has no type {schema_name}"
                required = set(model.__required_keys__)
                keys = required | set(model.__optional_keys__)
                documented = set(schema.get("properties", {}))

                self.assertEqual(sorted(documented - keys), [], "keys the API documents")
                extra = [
                    key
                    for key in sorted(keys - documented)
                    if f"{schema_name}.{key}" not in UNDOCUMENTED_FIELDS
                ]
                self.assertEqual(extra, [], "keys the document does not list")
                too_loose = [
                    key
                    for key in schema.get("required", [])
                    if key not in required and f"{schema_name}.{key}" not in LOOSER_THAN_DOCUMENTED
                ]
                self.assertEqual(too_loose, [], "required keys left optional")

    def test_every_request_body_field_is_an_argument(self) -> None:
        for schema_name, method in REQUEST_BODIES.items():
            with self.subTest(schema_name):
                schema = SCHEMAS[schema_name]
                parameters = inspect.signature(method).parameters
                arguments = {
                    name: parameter
                    for name, parameter in parameters.items()
                    if name not in CLIENT_ARGUMENTS | {"id", "idempotency_key"}
                }
                documented = {snake_case(field) for field in schema.get("properties", {})}
                self.assertEqual(sorted(documented ^ set(arguments)), [])
                required = {snake_case(field) for field in schema.get("required", [])}
                without_default = {
                    name
                    for name, parameter in arguments.items()
                    if parameter.default is inspect.Parameter.empty
                }
                self.assertEqual(without_default, required)

    def test_the_402_body_through_payment_required_error(self) -> None:
        base = {"statusCode", "error", "message", "code"}
        fields = set(SCHEMAS["WatchedFlightsUsedUp"]["properties"]) - base
        missing = [f for f in sorted(fields) if not hasattr(PaymentRequiredError, snake_case(f))]
        self.assertEqual(missing, [])


class ValueListsTest(unittest.TestCase):
    def test_phases(self) -> None:
        self.assertEqual(
            list(FLIGHT_PHASES), SCHEMAS["FlightStatusInfo"]["properties"]["phase"]["enum"]
        )

    def test_subscription_statuses(self) -> None:
        self.assertEqual(
            list(SUBSCRIPTION_STATUSES), SCHEMAS["Subscription"]["properties"]["status"]["enum"]
        )

    def test_change_types(self) -> None:
        events = SCHEMAS["CreateSubscriptionDto"]["properties"]["events"]
        self.assertEqual(list(FLIGHT_CHANGE_TYPES), events["items"]["enum"])


if __name__ == "__main__":
    unittest.main()
