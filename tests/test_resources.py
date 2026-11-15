import json
import unittest
from collections.abc import Callable
from typing import Any

from flightbyte import FlightByte, ServerError

from .helpers import APITestCase, Recorded, Reply, fixture, json_reply

FLIGHT = fixture("flight.json")
SUBSCRIPTION = fixture("subscription.json")


class FlightsTest(APITestCase):
    def test_get_sends_the_identifiers_in_the_path_and_the_rest_in_the_query(self) -> None:
        api = self.start(lambda request: json_reply(200, FLIGHT))
        result = api.client().flights.get(
            "TK",
            "1848",
            "2026-09-08",
            origin="IST",
            destination="CDG",
            flight_id="1407084032",
            refresh=True,
        )
        sent = api.last()
        self.assertEqual(sent.method, "GET")
        self.assertEqual(sent.path, "/v1/flights/TK/1848/2026-09-08")
        self.assertEqual(
            sent.query,
            {"origin": "IST", "destination": "CDG", "flightId": "1407084032", "refresh": "true"},
        )
        self.assertEqual(result, FLIGHT)

    def test_get_sends_no_query_when_nothing_optional_is_set(self) -> None:
        api = self.start(lambda request: json_reply(200, FLIGHT))
        api.client().flights.get("TK", "1848", "2026-09-08", refresh=False, origin="")
        self.assertEqual(api.last().raw_query, "")

    def test_timeline_reads_the_history(self) -> None:
        body = {"flightKey": "TK1848:2026-09-08", "count": 1, "data": FLIGHT["timeline"]}
        api = self.start(lambda request: json_reply(200, body))
        result = api.client().flights.timeline("TK", "1848", "2026-09-08", origin="IST")
        self.assertEqual(api.last().path, "/v1/flights/TK/1848/2026-09-08/timeline")
        self.assertEqual(api.last().raw_query, "origin=IST")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["data"][0]["title"], "Time Adjustment")


class SubscriptionsTest(APITestCase):
    def test_create_posts_the_body_and_the_idempotency_key_and_masks_the_secret(self) -> None:
        without_hint = {k: v for k, v in SUBSCRIPTION.items() if k != "secretHint"}
        reply = {
            **without_hint,
            "secret": "whsec_AbCdEfGhIjKlMnOpQrStUvwxyz",
            "reused": False,
            "flight": FLIGHT,
        }
        api = self.start(lambda request: json_reply(201, reply))
        created = api.client().subscriptions.create(
            "TK",
            "1848",
            "2026-09-08",
            "https://example.com/hooks/flights",
            origin="IST",
            events=("flight.departed", "departure.gate.changed"),
            delay_threshold_minutes=10,
            headers={"x-team": "ops"},
            metadata={"booking": "42"},
            idempotency_key="booking-42",
        )
        sent = api.last()
        self.assertEqual(sent.method, "POST")
        self.assertEqual(sent.path, "/v1/subscriptions")
        self.assertEqual(sent.headers["idempotency-key"], "booking-42")
        self.assertEqual(sent.headers["content-type"], "application/json")
        self.assertEqual(
            sent.json(),
            {
                "carrier": "TK",
                "flightNumber": "1848",
                "date": "2026-09-08",
                "webhookUrl": "https://example.com/hooks/flights",
                "origin": "IST",
                "events": ["flight.departed", "departure.gate.changed"],
                "delayThresholdMinutes": 10,
                "headers": {"x-team": "ops"},
                "metadata": {"booking": "42"},
            },
        )
        self.assertEqual(created["secretHint"], "whsec_AbCdE...wxyz")
        self.assertIs(created["reused"], False)
        flight = created.get("flight")
        assert flight is not None
        self.assertEqual(flight["flightKey"], "TK1848:2026-09-08")

    def test_create_sends_only_what_was_set_including_a_zero(self) -> None:
        api = self.start(lambda request: json_reply(201, {"id": "sub_1", "secret": "s"}))
        api.client().subscriptions.create(
            carrier="TK",
            flight_number="1848",
            date="2026-09-08",
            webhook_url="https://example.com/h",
            delay_threshold_minutes=0,
        )
        self.assertEqual(
            api.last().body,
            b'{"carrier":"TK","flightNumber":"1848","date":"2026-09-08",'
            b'"webhookUrl":"https://example.com/h","delayThresholdMinutes":0}',
        )
        self.assertNotIn("idempotency-key", api.last().headers)

    def test_create_keeps_the_hint_the_api_sent(self) -> None:
        reply = {"id": "sub_1", "secret": "whsec_AbCdEfGhIjKlMnOp", "secretHint": "from-api"}
        api = self.start(lambda request: json_reply(201, reply))
        created = api.client().subscriptions.create("TK", "1", "2026-09-08", "https://e.test/h")
        self.assertEqual(created["secretHint"], "from-api")

    def test_create_refuses_a_number_json_cannot_carry(self) -> None:
        api = self.start()
        with self.assertRaises(ValueError):
            api.client().subscriptions.create(
                "TK",
                "1",
                "2026-09-08",
                "https://e.test/h",
                delay_threshold_minutes=float("nan"),  # type: ignore[arg-type]
            )
        self.assertEqual(api.calls, [])

    def test_create_sends_text_that_is_not_ascii(self) -> None:
        api = self.start(lambda request: json_reply(201, {"id": "sub_1", "secret": "s"}))
        api.client().subscriptions.create(
            "TK", "1", "2026-09-08", "https://e.test/h", metadata={"city": "İstanbul 🇹🇷"}
        )
        self.assertEqual(api.last().json()["metadata"], {"city": "İstanbul 🇹🇷"})

    def test_list_sends_the_filters(self) -> None:
        page = {"total": 1, "limit": 5, "offset": 10, "data": [SUBSCRIPTION]}
        api = self.start(lambda request: json_reply(200, page))
        result = api.client().subscriptions.list(
            status="active",
            carrier="TK",
            flight_number="1848",
            date="2026-09-08",
            limit=5,
            offset=10,
        )
        self.assertEqual(
            api.last().query,
            {
                "status": "active",
                "carrier": "TK",
                "flightNumber": "1848",
                "date": "2026-09-08",
                "limit": "5",
                "offset": "10",
            },
        )
        self.assertEqual(len(result["data"]), 1)


def pages(total: int) -> Callable[[Recorded], Reply]:
    def reply(request: Recorded) -> Reply:
        limit = int(request.query["limit"])
        offset = int(request.query.get("offset", 0))
        count = max(0, min(limit, total - offset))
        data = [{"id": f"sub_{offset + i}"} for i in range(count)]
        return json_reply(200, {"total": total, "limit": limit, "offset": offset, "data": data})

    return reply


class ListAllTest(APITestCase):
    def test_walks_every_page(self) -> None:
        api = self.start(pages(5))
        subscriptions = api.client().subscriptions.list_all(page_size=2, status="active")
        self.assertEqual(
            [sub["id"] for sub in subscriptions], ["sub_0", "sub_1", "sub_2", "sub_3", "sub_4"]
        )
        self.assertEqual(len(api.calls), 3)
        self.assertEqual(api.last().query, {"status": "active", "limit": "2", "offset": "4"})

    def test_sends_nothing_until_asked_and_nothing_more_after_a_break(self) -> None:
        api = self.start(pages(5))
        iterator = api.client().subscriptions.list_all(page_size=2)
        self.assertEqual(api.calls, [])
        for _sub in iterator:
            break
        self.assertEqual(len(api.calls), 1)

    def test_uses_200_a_page_by_default_and_starts_at_the_offset(self) -> None:
        api = self.start(pages(0))
        self.assertEqual(list(api.client().subscriptions.list_all()), [])
        self.assertEqual(api.last().query, {"limit": "200", "offset": "0"})
        api.reply = pages(12)
        ids = [sub["id"] for sub in api.client().subscriptions.list_all(offset=10)]
        self.assertEqual(ids, ["sub_10", "sub_11"])

    def test_ends_on_an_error(self) -> None:
        api = self.start(lambda request: json_reply(500, {"statusCode": 500, "message": "boom"}))
        with self.assertRaises(ServerError):
            list(api.client().subscriptions.list_all())


ACTIONS: list[dict[str, Any]] = [
    {
        "name": "get",
        "reply": SUBSCRIPTION,
        "call": lambda c: c.subscriptions.get("sub_1"),
        "method": "GET",
        "path": "/v1/subscriptions/sub_1",
        "result": SUBSCRIPTION,
    },
    {
        "name": "update",
        "reply": SUBSCRIPTION,
        "call": lambda c: c.subscriptions.update(
            "sub_1",
            webhook_url="https://example.com/new",
            events=["flight.cancelled"],
            delay_threshold_minutes=30,
        ),
        "method": "PATCH",
        "path": "/v1/subscriptions/sub_1",
        "body": b'{"webhookUrl":"https://example.com/new","events":["flight.cancelled"],'
        b'"delayThresholdMinutes":30}',
    },
    {
        "name": "update with maps",
        "reply": SUBSCRIPTION,
        "call": lambda c: c.subscriptions.update("sub_1", headers={"a": "1"}, metadata={}),
        "method": "PATCH",
        "path": "/v1/subscriptions/sub_1",
        "body": b'{"headers":{"a":"1"},"metadata":{}}',
    },
    {
        "name": "update with nothing",
        "reply": SUBSCRIPTION,
        "call": lambda c: c.subscriptions.update("sub_1"),
        "method": "PATCH",
        "path": "/v1/subscriptions/sub_1",
        "body": b"{}",
    },
    {
        "name": "delete",
        "reply": None,
        "call": lambda c: c.subscriptions.delete("sub_1"),
        "method": "DELETE",
        "path": "/v1/subscriptions/sub_1",
        "result": None,
    },
    {
        "name": "pause",
        "reply": SUBSCRIPTION,
        "call": lambda c: c.subscriptions.pause("sub_1"),
        "method": "POST",
        "path": "/v1/subscriptions/sub_1/pause",
        "result": SUBSCRIPTION,
    },
    {
        "name": "resume",
        "reply": SUBSCRIPTION,
        "call": lambda c: c.subscriptions.resume("sub_1"),
        "method": "POST",
        "path": "/v1/subscriptions/sub_1/resume",
        "result": SUBSCRIPTION,
    },
    {
        "name": "send_test",
        "reply": {"eventId": "evt_1"},
        "call": lambda c: c.subscriptions.send_test("sub_1"),
        "method": "POST",
        "path": "/v1/subscriptions/sub_1/test",
        "result": "evt_1",
    },
    {
        "name": "deliveries",
        "reply": {
            "count": 1,
            "data": [
                {
                    "eventId": "evt_1",
                    "attempt": 2,
                    "status": "failed",
                    "httpStatus": 500,
                    "error": "HTTP 500",
                    "durationMs": 120,
                    "at": "2026-09-08T09:10:00.000Z",
                    "changeTypes": ["departure.gate.changed"],
                }
            ],
        },
        "call": lambda c: c.subscriptions.deliveries("sub_1", limit=10),
        "method": "GET",
        "path": "/v1/subscriptions/sub_1/deliveries",
        "query": "limit=10",
    },
    {
        "name": "events",
        "reply": {"count": 1, "data": [fixture("webhook_flight_updated.json")]},
        "call": lambda c: c.subscriptions.events("sub_1"),
        "method": "GET",
        "path": "/v1/subscriptions/sub_1/events",
        "result": [fixture("webhook_flight_updated.json")],
    },
    {
        "name": "secret",
        "reply": {"secret": "whsec_x"},
        "call": lambda c: c.subscriptions.secret("sub_1"),
        "method": "GET",
        "path": "/v1/subscriptions/sub_1/secret",
        "result": "whsec_x",
    },
    {
        "name": "rotate_secret",
        "reply": {"secret": "whsec_y"},
        "call": lambda c: c.subscriptions.rotate_secret("sub_1"),
        "method": "POST",
        "path": "/v1/subscriptions/sub_1/secret/rotate",
        "result": "whsec_y",
    },
]


class SubscriptionActionsTest(APITestCase):
    def test_each_action(self) -> None:
        for action in ACTIONS:
            with self.subTest(action["name"]):
                reply = action["reply"]
                api = self.start(
                    lambda request: Reply(204) if reply is None else json_reply(201, reply)  # noqa: B023
                )
                client: FlightByte = api.client()
                value = action["call"](client)
                sent = api.last()
                self.assertEqual(sent.method, action["method"])
                self.assertEqual(sent.path, action["path"])
                self.assertEqual(sent.raw_query, action.get("query", ""))
                self.assertEqual(sent.body, action.get("body"))
                if "result" in action:
                    self.assertEqual(value, action["result"])

    def test_a_missing_value_in_the_answer_is_an_error(self) -> None:
        from flightbyte import FlightByteError

        api = self.start(lambda request: json_reply(200, {"unexpected": True}))
        with self.assertRaisesRegex(FlightByteError, "Expected eventId from POST"):
            api.client().subscriptions.send_test("sub_1")
        with self.assertRaisesRegex(FlightByteError, "Expected secret from GET"):
            api.client().subscriptions.secret("sub_1")


class CountriesTest(APITestCase):
    TR = {  # noqa: RUF012
        "code": "TR",
        "alpha2": "TR",
        "name": "Türkiye",
        "emoji": "🇹🇷",
        "hasFlag": True,
        "flagSvg": "https://api.flightbyte.dev/v1/flags/tr.svg",
        "flagSvgSquare": "https://api.flightbyte.dev/v1/flags/tr.svg?shape=1x1",
    }

    def test_list_unwraps_the_data(self) -> None:
        api = self.start(lambda request: json_reply(200, {"count": 1, "data": [self.TR]}))
        self.assertEqual(api.client().countries.list(lang="tr"), [self.TR])
        self.assertEqual(api.last().path, "/v1/countries")
        self.assertEqual(api.last().raw_query, "lang=tr")

    def test_get_reads_one_country(self) -> None:
        api = self.start(lambda request: json_reply(200, self.TR))
        self.assertEqual(api.client().countries.get("TR"), self.TR)
        self.assertEqual(api.last().path, "/v1/countries/TR")
        self.assertEqual(api.last().raw_query, "")

    def test_flag_url_builds_the_url_without_a_request(self) -> None:
        api = self.start()
        client = api.client()
        self.assertEqual(client.countries.flag_url("TR"), f"{api.url}/v1/flags/tr.svg")
        self.assertEqual(
            client.countries.flag_url("TR", square=True), f"{api.url}/v1/flags/tr.svg?shape=1x1"
        )
        self.assertEqual(api.calls, [])
        self.assertEqual(
            FlightByte("k").countries.flag_url("fr"), "https://api.flightbyte.dev/v1/flags/fr.svg"
        )

    def test_responses_come_back_exactly_as_sent(self) -> None:
        raw = json.dumps({"count": 1, "data": [{**self.TR, "addedLater": {"x": [1, None]}}]})
        api = self.start(lambda request: json_reply(200, raw))
        self.assertEqual(api.client().countries.list()[0]["addedLater"], {"x": [1, None]})  # type: ignore[typeddict-item]


if __name__ == "__main__":
    unittest.main()
