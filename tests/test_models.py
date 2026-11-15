import unittest

from flightbyte import (
    DELIVERY_STATUSES,
    FLIGHT_CHANGE_TYPES,
    FLIGHT_PHASES,
    SUBSCRIPTION_STATUSES,
    WEBHOOK_EVENT_TYPES,
    CreatedSubscription,
    DeliveryRecord,
    FlightSnapshot,
    FlightTime,
    Subscription,
    WebhookEvent,
    best_gate_time,
    is_terminal_phase,
    mask_secret,
)

from .helpers import check_shape, fixture

FLIGHT = fixture("flight.json")
SUBSCRIPTION = fixture("subscription.json")


class FixturesFitTheTypesTest(unittest.TestCase):
    """The fixtures are shaped like the API's JSON; a key the models lack, or a
    required one they have that the fixture does not, fails here."""

    def test_flight(self) -> None:
        self.assertEqual(check_shape(FLIGHT, FlightSnapshot), [])
        flight: FlightSnapshot = FLIGHT
        self.assertEqual(flight["flightKey"], "TK1848:2026-09-08")
        self.assertEqual(flight["departure"].get("delayMinutes"), 15)
        self.assertEqual(flight["arrival"].get("delayMinutes"), -5)
        self.assertIn("gate", flight["arrival"])
        self.assertIsNone(flight["arrival"].get("gate"))
        self.assertNotIn("code", flight["arrival"]["airport"])
        self.assertIsNone(flight["status"].get("arrivalGateDelayMinutes"))
        self.assertIs(flight.get("cached"), True)

    def test_subscription_with_a_change_type_newer_than_this_release(self) -> None:
        self.assertEqual(check_shape(SUBSCRIPTION, Subscription), [])
        self.assertIn("some.future.type", SUBSCRIPTION["events"])
        self.assertNotIn("some.future.type", FLIGHT_CHANGE_TYPES)
        self.assertIsNone(SUBSCRIPTION["lastChangeAt"])

    def test_created_subscription(self) -> None:
        created = {**SUBSCRIPTION, "secret": "whsec_x", "reused": False, "flight": FLIGHT}
        self.assertEqual(check_shape(created, CreatedSubscription), [])
        self.assertEqual(
            check_shape({**SUBSCRIPTION, "reused": False}, CreatedSubscription),
            ["$: CreatedSubscription lacks the required key 'secret'"],
        )

    def test_webhook_events(self) -> None:
        events = [fixture("webhook_test.json"), fixture("webhook_flight_updated.json")]
        for event in events:
            self.assertEqual(check_shape(event, WebhookEvent), [])
        self.assertEqual([e["type"] for e in events], ["subscription.test", "flight.updated"])

    def test_the_check_catches_what_does_not_fit(self) -> None:
        broken = {**FLIGHT, "flightKey": 1, "unknownKey": True}
        del broken["fingerprint"]
        self.assertEqual(
            sorted(check_shape(broken, FlightSnapshot)),
            [
                "$.flightKey: expected a string, got 1",
                "$: FlightSnapshot has no key 'unknownKey'",
                "$: FlightSnapshot lacks the required key 'fingerprint'",
            ],
        )
        record = {
            "eventId": "evt_1",
            "attempt": True,
            "status": "failed",
            "durationMs": 1.5,
            "at": "x",
            "changeTypes": [],
        }
        self.assertEqual(
            check_shape(record, DeliveryRecord),
            ["$.attempt: expected int, got True", "$.durationMs: expected int, got 1.5"],
        )


class HelpersTest(unittest.TestCase):
    def test_is_terminal_phase(self) -> None:
        self.assertEqual(
            [phase for phase in FLIGHT_PHASES if is_terminal_phase(phase)],
            ["arrived", "cancelled", "diverted", "redirected"],
        )
        self.assertFalse(is_terminal_phase("later"))

    def test_best_gate_time_prefers_actual_then_estimated_then_scheduled(self) -> None:
        departs = best_gate_time(FLIGHT["departure"]["times"])
        assert departs is not None
        self.assertEqual(departs.get("local"), "2026-09-08T12:25:00.000")
        arrives = best_gate_time(FLIGHT["arrival"]["times"])
        assert arrives is not None
        self.assertEqual(arrives.get("timezone"), "CEST")
        self.assertIsNone(best_gate_time({}))
        actual: FlightTime = {"utc": "2026-09-08T09:30:00.000Z"}
        self.assertIs(best_gate_time({"actualGate": actual, "scheduledGate": None}), actual)

    def test_mask_secret(self) -> None:
        self.assertEqual(mask_secret("whsec_AbCdEfGhIjKlMnOpQrStUvwxyz"), "whsec_AbCdE...wxyz")
        self.assertEqual(mask_secret("short"), "short")
        self.assertEqual(mask_secret("a" * 15), "a" * 15)

    def test_the_value_lists_have_no_duplicates(self) -> None:
        for values in (
            FLIGHT_PHASES,
            SUBSCRIPTION_STATUSES,
            FLIGHT_CHANGE_TYPES,
            WEBHOOK_EVENT_TYPES,
            DELIVERY_STATUSES,
        ):
            self.assertIsInstance(values, tuple)
            self.assertEqual(len(set(values)), len(values))
        self.assertEqual(len(FLIGHT_CHANGE_TYPES), 23)


if __name__ == "__main__":
    unittest.main()
