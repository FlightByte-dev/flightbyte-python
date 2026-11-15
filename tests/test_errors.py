import pickle
import unittest
from typing import Any

from flightbyte import (
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

from .helpers import APITestCase, Reply, json_reply


class ErrorTestCase(APITestCase):
    def fail_with(self, status: int, body: Any, headers: dict[str, str] | None = None) -> APIError:
        api = self.start(lambda request: json_reply(status, body, headers))
        with self.assertRaises(APIError) as caught:
            api.client().subscriptions.get("sub_1")
        return caught.exception


class StatusMappingTest(ErrorTestCase):
    def test_each_status_has_its_class(self) -> None:
        cases: list[tuple[int, type[APIError]]] = [
            (400, BadRequestError),
            (401, AuthenticationError),
            (402, PaymentRequiredError),
            (403, PermissionDeniedError),
            (404, NotFoundError),
            (409, UnexpectedStatusError),
            (422, UnexpectedStatusError),
            (429, RateLimitError),
            (500, ServerError),
            (502, UpstreamError),
            (503, ServerError),
        ]
        for status, error_class in cases:
            with self.subTest(status=status):
                error = self.fail_with(status, {"statusCode": status, "message": "x"})
                self.assertIs(type(error), error_class)
                self.assertIsInstance(error, FlightByteError)
                self.assertIsInstance(error, Exception)
                self.assertEqual(error.status, status)

    def test_a_502_is_a_server_error_too(self) -> None:
        self.assertIsInstance(self.fail_with(502, {}), ServerError)

    def test_none_of_them_shadow_a_builtin(self) -> None:
        import builtins

        import flightbyte

        shadowed = [name for name in flightbyte.__all__ if hasattr(builtins, name)]
        self.assertEqual(shadowed, [])
        self.assertFalse(issubclass(APIConnectionError, ConnectionError))


class ErrorBodyTest(ErrorTestCase):
    def test_reads_every_message_and_the_request_id(self) -> None:
        error = self.fail_with(
            400,
            {
                "statusCode": 400,
                "error": "Bad Request",
                "message": ["carrier must be 2 or 3 characters", "date must be YYYY-MM-DD"],
                "requestId": "req_123",
            },
        )
        self.assertEqual(
            error.messages, ["carrier must be 2 or 3 characters", "date must be YYYY-MM-DD"]
        )
        self.assertEqual(error.request_id, "req_123")
        self.assertEqual(error.body["error"], "Bad Request")
        self.assertEqual(
            str(error),
            "400 Bad Request: carrier must be 2 or 3 characters; date must be YYYY-MM-DD "
            "(request req_123)",
        )

    def test_uses_the_api_phrase_when_the_reason_is_empty(self) -> None:
        error = APIError.from_response(404, "", '{"error":"Not Found","message":"No flight"}', {})
        self.assertEqual(str(error), "404 Not Found: No flight")
        self.assertEqual(str(APIError.from_response(418, "", "", {})), "418")

    def test_lists_the_legs_of_an_ambiguous_flight(self) -> None:
        error = self.fail_with(
            400,
            {
                "statusCode": 400,
                "message": "TK1 flies 2 legs on 2026-09-08; pass origin to choose one.",
                "legs": [
                    {
                        "origin": "IST",
                        "destination": "JFK",
                        "carrier": "TK",
                        "scheduledDepartureLocal": "07:00",
                        "flightId": "1",
                    },
                    {"origin": "JFK", "destination": "IST", "scheduledDepartureLocal": "21:00"},
                    "junk",
                ],
            },
        )
        assert isinstance(error, BadRequestError)
        self.assertEqual(
            error.legs,
            [
                {
                    "origin": "IST",
                    "destination": "JFK",
                    "carrier": "TK",
                    "scheduledDepartureLocal": "07:00",
                    "flightId": "1",
                },
                {"origin": "JFK", "destination": "IST", "scheduledDepartureLocal": "21:00"},
            ],
        )
        self.assertEqual(BadRequestError(400, "", '{"legs": "no"}', {}).legs, [])

    def test_reads_the_reason_a_watched_flight_was_refused(self) -> None:
        capped = self.fail_with(
            402,
            {
                "statusCode": 402,
                "code": "overage_cap_reached",
                "message": "No watched flights left.",
                "limit": 10,
                "used": 10,
                "resetsAt": "2026-10-01T00:00:00.000Z",
                "capCents": 500,
            },
        )
        assert isinstance(capped, PaymentRequiredError)
        self.assertEqual(capped.code, "overage_cap_reached")
        self.assertEqual(
            [capped.limit, capped.used, capped.resets_at, capped.cap_cents],
            [10, 10, "2026-10-01T00:00:00.000Z", 500],
        )
        self.assertIsNone(capped.balance)

        credits = self.fail_with(
            402,
            {
                "statusCode": 402,
                "code": "credits_exhausted",
                "message": "No credits left.",
                "balance": 0,
                "expiresAt": "2027-01-01T00:00:00.000Z",
            },
        )
        assert isinstance(credits, PaymentRequiredError)
        self.assertEqual(credits.code, "credits_exhausted")
        self.assertEqual(credits.balance, 0)
        self.assertEqual(credits.expires_at, "2027-01-01T00:00:00.000Z")
        self.assertIsNone(credits.limit)

    def test_ignores_numbers_that_are_not_numbers(self) -> None:
        error = PaymentRequiredError(402, "", '{"limit": true, "used": "3", "capCents": null}', {})
        self.assertEqual([error.limit, error.used, error.cap_cents], [None, None, None])

    def test_reads_how_long_to_wait_from_the_body_or_the_retry_after_header(self) -> None:
        from_body = self.fail_with(429, {"window": "minute", "retryAfterSeconds": 12})
        assert isinstance(from_body, RateLimitError)
        self.assertEqual(from_body.window, "minute")
        self.assertEqual(from_body.retry_after, 12)
        from_header = self.fail_with(429, {"message": "slow down"}, {"retry-after": "30"})
        assert isinstance(from_header, RateLimitError)
        self.assertEqual(from_header.retry_after, 30)
        unknown = self.fail_with(429, {})
        assert isinstance(unknown, RateLimitError)
        self.assertIsNone(unknown.retry_after)
        dated = RateLimitError(429, "", "", {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        self.assertIsNone(dated.retry_after)

    def test_copes_with_a_body_that_is_not_json(self) -> None:
        api = self.start(
            lambda request: Reply(
                503, b"<html>Service Unavailable</html>", {"x-request-id": "req_from_header"}
            )
        )
        with self.assertRaises(ServerError) as caught:
            api.client().countries.list()
        error = caught.exception
        self.assertEqual(error.messages, [])
        self.assertEqual(error.body, {})
        self.assertEqual(error.raw_body, "<html>Service Unavailable</html>")
        self.assertEqual(error.request_id, "req_from_header")
        self.assertEqual(error.headers["x-request-id"], "req_from_header")
        self.assertEqual(str(error), "503 Service Unavailable (request req_from_header)")

    def test_carries_the_code_of_a_suspended_account(self) -> None:
        error = self.fail_with(
            403, {"message": "This account is suspended.", "code": "account_suspended"}
        )
        self.assertIsInstance(error, PermissionDeniedError)
        self.assertEqual(error.code, "account_suspended")


class PickleTest(unittest.TestCase):
    """Errors cross process boundaries: multiprocessing, Celery, RQ."""

    def test_every_error_survives_pickling(self) -> None:
        body = '{"message": "slow down", "retryAfterSeconds": 3, "requestId": "req_1"}'
        api_error = APIError.from_response(429, "Too Many Requests", body, {"Retry-After": "9"})
        copy = pickle.loads(pickle.dumps(api_error))
        self.assertIs(type(copy), RateLimitError)
        self.assertEqual(str(copy), str(api_error))
        self.assertEqual(copy.retry_after, 3)
        self.assertEqual(copy.headers, {"retry-after": "9"})

        connection = pickle.loads(pickle.dumps(APIConnectionError("no route", timed_out=True)))
        self.assertTrue(connection.timed_out)
        self.assertEqual(str(connection), "no route")

        signature = pickle.loads(pickle.dumps(WebhookSignatureError("bad")))
        self.assertEqual(str(signature), "bad")


if __name__ == "__main__":
    unittest.main()
